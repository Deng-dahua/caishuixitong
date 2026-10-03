# -*- coding: utf-8 -*-
"""银行收款性质（唯一权威 engine/bank_nature）与收入口径 —— 单元 + 接线测试。

背景（用户 2026-10-03 质询）：
  报告把「全部贷方 8,371,659.92 元」当收入去比销项开票 7,035,008.58 元，
  凭空得出 133.7 万差额并写成"存在未确认收入的资金入账"。用户直接问：
  **"是不是所有的银行流水的收款都是与收入相关？"** —— 不是。

本文件锁死四件事：
  ① 分类正确：借款/往来/保证金/退税/结息等非经营性收款不得计入收入口径；
  ② 规则表驱动：每个类目都必须有 nature 标注（新增类目只改数据表，不改代码）；
  ③ 判不出必须"待判定"（绝不默认算作经营性收入）；
  ④ 接线：凭证/发票/银行三源对比里银行侧取值**必须**等于权威函数的经营性收款合计
     （防"改了权威但生产链路没走到"这类静默失效）。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _tx(cp, summary, credit, **kw):
    d = {"counterparty": cp, "summary": summary, "credit": credit, "debit": 0.0,
         "date": "2025-06-30"}
    d.update(kw)
    return d


# ── ① 分类：什么算收入，什么不算 ─────────────────────────────────────────────
class TestReceiptNatures:
    def test_operating_receipts(self):
        """客户货款、第三方平台回款＝经营性（第三方平台是资金通道，回款仍是销售收入）。"""
        from engine.bank_nature import classify_credit, OPERATING
        assert classify_credit(_tx("某某科技有限公司", "货款", 1_000_000))[1] == OPERATING
        assert classify_credit(_tx("支付宝（中国）网络技术有限公司", "收款", 5_000))[1] == OPERATING

    @pytest.mark.parametrize("cp,summary", [
        ("某关联集团有限公司", "往来款"),
        ("某某银行深圳分行", "借款放款"),
        ("某某建设公司", "投标保证金"),
        ("国家金库深圳市分库", "退税"),
        ("某某保险公司", "理赔款"),
        ("某某财政局", "专项资金补助"),
    ])
    def test_non_operating_receipts_not_income(self, cp, summary):
        """★ 核心命题：这些收款**与收入无关**，不得计入收入口径。

        它们是本项假线索的来源：把关联方往来/保证金/退税当成收入，
        与开票额比对后差额会被读成"隐匿未开票收入"。
        """
        from engine.bank_nature import classify_credit, NON_OPERATING
        assert classify_credit(_tx(cp, summary, 800_000))[1] == NON_OPERATING

    def test_unknown_goes_to_undetermined_never_income(self):
        """③ 判不出必须"待判定"——不得默认算作经营性收入（那是替企业认收入）。"""
        from engine.bank_nature import classify_credit, UNDETERMINED
        label, nature = classify_credit(_tx("李昭阳", "转存", 97_000))
        assert nature == UNDETERMINED

    def test_income_scope_excludes_non_operating(self):
        """收入口径 = 经营性收款；非经营性/待判定都必须被排除。"""
        from engine.bank_nature import classify_receipts
        res = classify_receipts([
            _tx("某某科技有限公司", "货款", 800_000),
            _tx("某关联集团有限公司", "往来款", 1_289_200),
            _tx("某某建设公司", "保证金", 65_000),
            _tx("李昭阳", "转存", 202_000),
        ])
        assert res["operating"] == pytest.approx(800_000)
        assert res["non_operating"] == pytest.approx(1_354_200)
        assert res["undetermined"] == pytest.approx(202_000)
        assert res["total"] == pytest.approx(2_356_200)
        # 口径说明必须把"剔除了什么、什么还没定"写出来
        from engine.bank_nature import income_scope_note
        note = income_scope_note(res)
        assert "经营性收款" in note and "非经营性" in note
        assert "待判定" in note
        assert "**" not in note, "报告正文不得出现 markdown 强调符"

    def test_bank_interest_correction_is_non_operating(self):
        """极小金额有零有整的空文本收款＝银行结息，纠错入「银行内部款项」且性质为非经营性。"""
        from engine.bank_nature import classify_receipts
        res = classify_receipts([_tx("", "", 9.62, remark=""), _tx("", "", 47.26, remark="")])
        assert res["operating"] == 0
        assert res["non_operating"] == pytest.approx(56.88)
        assert res["corrections"], "纠错必须留痕（供报告说明），不得静默改判"


# ── ② 规则表驱动：新增类目只改数据表 ─────────────────────────────────────────
class TestRuleTableDriven:
    def test_every_rule_declares_nature(self):
        """每个收款类目都必须标注 nature —— 漏标就会被当成"待判定"，
        报告里会出现"性质待判定"的莫名收款。新增类目时先补这一行数据。"""
        from engine.bank_nature import receipt_rules
        miss = [r.get("label") for r in receipt_rules() if not str(r.get("nature") or "").strip()]
        assert not miss, "以下类目未标注 nature（请在 industry_data.json 收款分类规则补一行）：%s" % miss

    def test_nature_values_are_canonical(self):
        from engine.bank_nature import receipt_rules, OPERATING, NON_OPERATING, UNDETERMINED
        allowed = {OPERATING, NON_OPERATING, UNDETERMINED}
        bad = [(r.get("label"), r.get("nature")) for r in receipt_rules()
               if str(r.get("nature") or "") not in allowed]
        assert not bad, "性质取值非法：%s" % bad

    def test_config_change_takes_effect_without_code_change(self, monkeypatch):
        """改数据表 → 分类随之改变（证明判据在数据里，不在代码分支里）。"""
        import engine.bank_nature as bn
        fake = {"rules": [
            {"label": "特殊补贴", "summaries": ["特殊扶持"], "nature": bn.OPERATING},
            {"label": "其它", "is_default": True, "nature": bn.UNDETERMINED},
        ]}
        monkeypatch.setattr(bn, "_receipt_cfg", lambda: fake)
        label, nature = bn.classify_credit(_tx("某单位", "特殊扶持", 1000))
        assert (label, nature) == ("特殊补贴", bn.OPERATING)

    def test_unavailable_rules_fall_back_and_say_so(self, monkeypatch):
        """③ 规则未标性质 ⇒ 不可用：不得静默按经营性算，须回退并如实说明。"""
        import engine.bank_nature as bn
        monkeypatch.setattr(bn, "_receipt_cfg", lambda: {})
        res = bn.classify_receipts([_tx("某某科技有限公司", "货款", 1000)])
        assert res["available"] is False
        assert bn.operating_credit_total([_tx("某某科技有限公司", "货款", 1000)]) == 1000
        assert "不可用" in bn.income_scope_note(res)


# ── ③ 接线：三源对比的银行侧必须走权威函数 ───────────────────────────────────
class TestWiring:
    def test_bank_side_equals_authoritative_operating_total(self):
        """端到端断言：`_domain_voucher_invoice_revenue_compare` 用的银行金额
        **必须**等于权威函数的经营性收款合计。

        为什么要有这条：源码级闸门只能证明"函数被引用了"，
        证明不了"这笔钱真的按性质取过" —— 本项目的血泪教训。
        """
        from engine.bank_nature import operating_credit_total
        from engine.domain_analysis import _domain_voucher_invoice_revenue_compare
        bank = [
            _tx("某某科技有限公司", "货款", 800_000),
            _tx("某关联集团有限公司", "往来款", 1_289_200),
            _tx("某某建设公司", "保证金", 65_000),
            _tx("李昭阳", "转存", 202_000),
        ]
        sal = [{"total": 848_000.0}]   # 800,000 × 1.06 = 848,000（口径吻合）
        rev = {"invoiced": 0.0, "uninvoiced": 0.0, "unspecified": 800_000.0,
               "total": 800_000.0, "rows": 12}
        out = _domain_voucher_invoice_revenue_compare(rev, sal, bank)
        overview = [f for f in out if f.get("type") == "收入三源对比总览"][0]
        # 明细里银行侧数字只能是经营性收款，绝不能是全部贷方 2,356,200
        assert "800,000.00" in overview["detail"]
        assert "2,356,200.00" not in overview["detail"]
        assert operating_credit_total(bank) == pytest.approx(800_000)
        # 口径与待判定必须写进正文（不静默）
        assert "非经营性" in overview["description"]
        assert "待判定" in overview["description"]

    def test_scope_conversion_prevents_false_gap(self):
        """账载收入(不含税) vs 销项发票(含税) 是**口径差**，不是"少计收入"。"""
        from engine.domain_analysis import _domain_voucher_invoice_revenue_compare
        rev = {"invoiced": 6_636_800.57, "uninvoiced": 0.0, "unspecified": 0.0,
               "total": 6_636_800.57, "rows": 26}
        out = _domain_voucher_invoice_revenue_compare(rev, [{"total": 7_035_008.58}], [])
        types = [f.get("type") for f in out]
        assert "凭证开票收入与发票金额不一致" not in types, (
            "6% 税额差额被当成「凭证与发票不一致」（假阳性）")
        overview = [f for f in out if f.get("type") == "收入三源对比总览"][0]
        assert "口径" in overview["description"]

    def test_unlabelled_summary_is_not_counted_as_uninvoiced(self):
        """摘要未标注开票口径的，不得默认算作未开票收入（旧实现的根因）。"""
        import inspect
        from engine import pipeline as _pl
        src = inspect.getsource(_pl)
        assert 'voucher_revenue["unspecified"]' in src, "凭证收入必须单列「未标注」口径"


# ── ④ 含税/不含税口径换算（唯一权威 engine/tax_rates） ───────────────────────
class TestTaxRateScope:
    def test_nearest_rate_wins(self):
        """必须取**最接近**的法定率：6% 曾被相邻的 5% 抢先命中（|0.06-0.05|≤容差）。"""
        from engine.tax_rates import match_tax_inclusive
        r = match_tax_inclusive(6_636_800.57, 7_035_008.58)
        assert r["matched"] and r["rate"] == pytest.approx(0.06)
        assert abs(r["diff"]) < 0.05

    def test_unexplainable_gap_is_not_scope(self):
        from engine.tax_rates import match_tax_inclusive
        assert match_tax_inclusive(100.0, 150.0)["matched"] is False

    def test_rate_table_single_source(self):
        """monthly_reconcile 的税率表必须是 tax_rates 的转发（不得各写一份）。"""
        import engine.monthly_reconcile as mr
        from engine.tax_rates import CANON_RATES, RATE_TOL
        assert mr._CANON_RATES == CANON_RATES
        assert mr._RATE_TOL == RATE_TOL

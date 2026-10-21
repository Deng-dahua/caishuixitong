# -*- coding: utf-8 -*-
"""资金流 × 发票流**柔性匹配引擎**测试（2026-10-21）。

覆盖用户验收标准三条 + 三维聚合 + 资产负债表调节 + 未匹配四分类。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.fund_invoice_flexible import (           # noqa: E402
    CLS_ADVANCE, CLS_NON_OP, CLS_SUSPECT, CLS_TAIL,
    aggregate_by_object, classify_unmatched, reconcile_income, run_flexible_matching,
)


class TestAcceptanceCustomerA:
    """验收①：客户 A 本月开票 100 万、本月只打款 3 笔共 60 万
    ⇒ 不应直接判"账外收入"，应提示"存在应收账款 40 万"。"""

    def _data(self):
        return {
            "sal_invs": [{"buyer": "客户A有限公司", "amount": 1000000, "date": "2026-03-10"}],
            "bank_txs": [
                {"counterparty": "客户A有限公司", "credit": 200000, "date": "2026-03-12",
                 "summary": "货款"},
                {"counterparty": "客户A有限公司", "credit": 200000, "date": "2026-03-20",
                 "summary": "货款"},
                {"counterparty": "客户A有限公司", "credit": 200000, "date": "2026-03-28",
                 "summary": "货款"},
            ],
            "tax_declarations": [{"sales_amount": 1000000, "period": "2026-03"}],
            "accounts_receivable": [
                {"客户名称": "客户A有限公司", "应收金额": 1000000, "已收金额": 600000,
                 "未收金额": 400000, "账龄": "20天", "开票日期": "2026-03-10"},
            ],
        }

    def test_桶级聚合识别差额与应收(self):
        data = self._data()
        b = aggregate_by_object(data["sal_invs"], data["bank_txs"], side="sale")
        key = [k for k in b if "客户A" in k][0]
        bucket = b[key]
        assert bucket["invoice_total"] == 1000000
        assert bucket["flow_total"] == 600000
        assert bucket["diff"] == -400000            # 收款 < 开票 40 万
        assert bucket["matched"] is False           # 差额 40% > 25% 容忍度

    def test_调节后差额被应收解释_不触发(self):
        r = reconcile_income(self._data())
        assert r["available"] is True
        assert r["declared"] == 1000000
        # 预期收款 = 100万 − 40万(应收增加) = 60万，与实际 60 万吻合
        assert r["expected_cash"] == 600000
        assert abs(r["residual"]) <= 1        # 残差≈0
        assert r["within_tolerance"] is True
        assert "应收账款增加" in r["detail"]

    def test_不是账外收入结论(self):
        res = run_flexible_matching(self._data(), side="sale")
        assert "账外收入" not in res["verdict"]
        # 应提示存在待解释差额（多为应收/预收）
        assert res["metrics"]["gap_object_count"] == 1
        assert res["reconcile"]["within_tolerance"] is True

    def test_部分收款不算未匹配流入(self):
        """★ 语义边界：客户A有开票 ⇒ 其 60 万收款属该发票的收款（部分），
        **不得**算成"未匹配流入"（否则凭空造 60 万账外流入）。"""
        res = run_flexible_matching(self._data(), side="sale")
        assert res["metrics"]["unmatched_total"] == 0, \
            "有开票对象的收款不得计入未匹配流入"
        # 差额应作为"有开票但收款不足"的对象单列（应收挂账）
        over = res["unmatched"]["over_invoiced"]
        assert len(over) == 1 and over[0]["gap"] == -400000


class TestAcceptanceCustomerB:
    """验收②：客户 B 上月开票 50 万、本月开票 50 万，本月收一笔 100 万
    ⇒ 应成功对应到两张发票，不产生异常。"""

    def _data(self):
        return {
            "sal_invs": [
                {"buyer": "客户B公司", "amount": 500000, "date": "2026-02-20"},
                {"buyer": "客户B公司", "amount": 500000, "date": "2026-03-05"},
            ],
            "bank_txs": [
                {"counterparty": "客户B公司", "credit": 1000000, "date": "2026-03-25",
                 "summary": "合并付款 结算款"},
            ],
            "tax_declarations": [{"sales_amount": 1000000, "period": "2026-03"}],
        }

    def test_一对多合并付款被桶级匹配(self):
        data = self._data()
        b = aggregate_by_object(data["sal_invs"], data["bank_txs"], side="sale")
        key = [k for k in b if "客户B" in k][0]
        bucket = b[key]
        assert bucket["invoice_total"] == 1000000    # 两张发票合计
        assert bucket["flow_total"] == 1000000       # 一笔流水
        assert bucket["matched"] is True             # 桶级吻合 ⇒ 不报异常

    def test_跨期窗口吸收了上月发票(self):
        """上月发票在「发票最晚日+90 天」窗口内 ⇒ 本月收款仍能匹配。"""
        data = self._data()
        b = aggregate_by_object(data["sal_invs"], data["bank_txs"], side="sale")
        key = [k for k in b if "客户B" in k][0]
        assert b[key]["in_window"] == 1
        assert b[key]["out_window"] == 0

    def test_无异常结论(self):
        res = run_flexible_matching(self._data(), side="sale")
        assert res["metrics"]["suspect_count"] == 0
        assert res["verdict"] in ("三维聚合匹配未见异常", "存在待解释差额（多为应收/预收）")


class TestObjectAggregation:
    def test_名称容错_省市前缀与后缀(self):
        b = aggregate_by_object(
            [{"buyer": "广东XX科技有限公司", "amount": 100, "date": "2026-01-10"}],
            [{"counterparty": "XX科技有限公司", "credit": 100, "date": "2026-01-11"}],
            side="sale")
        assert len(b) == 1, "省前缀/后缀差异应归同一桶"
        assert list(b.values())[0]["matched"] is True

    def test_采购侧只看借方(self):
        b = aggregate_by_object(
            [{"seller": "供应商甲", "amount": 100000, "date": "2026-01-10"}],
            [{"counterparty": "供应商甲", "debit": 100000, "date": "2026-01-11"},
             {"counterparty": "供应商甲", "credit": 999999, "date": "2026-01-12"}],
            side="purchase")
        assert list(b.values())[0]["flow_total"] == 100000, "采购侧不得把贷方计入"


class TestReconcile:
    def test_预收解释收款大于申报(self):
        """先收款后开票：预收账款增加 ⇒ 预期现金多于申报，差额被解释。"""
        r = reconcile_income({
            "tax_declarations": [{"sales_amount": 500000}],
            "bank_txs": [{"counterparty": "新客户", "credit": 800000, "date": "2026-03-01"}],
            "trial_balance": [{"科目名称": "预收账款", "期末余额": 300000}],
        })
        assert r["explained_by"]["advance_available"] is True
        assert r["expected_cash"] == 800000          # 50万 + 预收30万
        assert r["within_tolerance"] is True

    def test_调节项缺失如实跳过_不臆测为0(self):
        r = reconcile_income({
            "tax_declarations": [{"sales_amount": 1000000}],
            "bank_txs": [{"counterparty": "某客户", "credit": 1000000, "date": "2026-03-01"}],
        })
        assert r["skipped"], "应收/预收都取不到 ⇒ 必须如实记入 skipped"
        assert any("应收账款" in s for s in r["skipped"])

    def test_无申报表_不可用(self):
        r = reconcile_income({"bank_txs": [{"credit": 100}]})
        assert r["available"] is False
        assert "未取得申报销售额" in r["verdict_hint"]


class TestUnmatchedClassification:
    def test_四类拆分(self):
        data = {
            "sal_invs": [{"buyer": "老客户甲", "amount": 100000, "date": "2026-02-01"}],
            "bank_txs": [
                # 预收性质：摘要含预付款
                {"counterparty": "新客户乙", "credit": 300000, "date": "2026-03-01",
                 "summary": "预付款"},
                # 非经营流水：摘要含借款
                {"counterparty": "某公司", "credit": 200000, "date": "2026-03-02",
                 "summary": "借款"},
                # 真正异常：大额、非个人、无发票无合同
                {"counterparty": "神秘公司", "credit": 800000, "date": "2026-03-03",
                 "summary": "转账"},
            ],
        }
        r = classify_unmatched(data, side="sale")
        cats = r["categories"]
        assert cats[CLS_ADVANCE]["count"] >= 1, "预付款应归【预收性质】"
        assert cats[CLS_NON_OP]["count"] >= 1, "借款应归【非经营流水】"
        assert cats[CLS_SUSPECT]["count"] >= 1, "大额无凭证应归【真正异常】"

    def test_个人大额不判真正异常(self):
        """对方为自然人 ⇒ 不属【真正异常】（另有个税/公私混同规则管）。"""
        data = {"sal_invs": [], "bank_txs": [
            {"counterparty": "张三", "credit": 900000, "date": "2026-03-03", "summary": "转账"}]}
        r = classify_unmatched(data, side="sale")
        assert r["categories"][CLS_SUSPECT]["count"] == 0

    def test_大额阈值以下不判异常(self):
        data = {"sal_invs": [], "bank_txs": [
            {"counterparty": "小公司", "credit": 100000, "date": "2026-03-03", "summary": "转账"}]}
        r = classify_unmatched(data, side="sale", large_amount=500000)
        assert r["categories"][CLS_SUSPECT]["count"] == 0

    def test_已匹配的不进未匹配(self):
        data = {
            "sal_invs": [{"buyer": "客户A", "amount": 100000, "date": "2026-03-01"}],
            "bank_txs": [{"counterparty": "客户A", "credit": 100000, "date": "2026-03-05",
                          "summary": "货款"}],
        }
        r = classify_unmatched(data, side="sale")
        assert r["unmatched_count"] == 0, "桶级已吻合 ⇒ 该对象流水不算未匹配"


class TestTopLevel:
    def test_无资料_available_false(self):
        res = run_flexible_matching({}, side="sale")
        assert res["available"] is False
        assert res["verdict"] == "资料缺失待核"

    def test_指标齐备(self):
        res = run_flexible_matching({
            "sal_invs": [{"buyer": "X", "amount": 100, "date": "2026-01-01"}],
            "bank_txs": [{"counterparty": "X", "credit": 100, "date": "2026-01-02"}],
        }, side="sale")
        for k in ("object_count", "matched_object_count", "gap_object_count",
                  "unmatched_total", "suspect_count"):
            assert k in res["metrics"], "缺指标 %s" % k


class TestWiringGate:
    """接线闸门契约（防能力空转 / 话术回退硬判）。"""

    def test_闸门接入run_checks(self):
        src = (ROOT / "tools" / "audit_consistency.py").read_text(encoding="utf-8")
        assert "+ check_flexible_matching_wiring()" in src, "闸门未接入 run_checks"

    def test_闸门正例通过(self):
        from tools.audit_consistency import check_flexible_matching_wiring
        assert check_flexible_matching_wiring() == [], "柔性匹配闸门应无问题"

    def test_pipeline_真实调用存在(self):
        import re
        src = (ROOT / "engine" / "pipeline.py").read_text(encoding="utf-8")
        src = re.sub(r'"""(?:.|\n)*?"""', " ", src)
        src = re.sub(r"#[^\n]*", "", src)
        assert re.search(r"\brun_flexible_matching\s*\(", src), "pipeline 无真实调用"
        assert "fund_invoice_matching" in src, "结果未写入 comprehensive"

    def test_话术不含硬判措辞(self):
        """报告话术不得再出现"未匹配到银行流水"这类暗示账外收入的硬判措辞。"""
        for rel in ("engine/verified_rule_engine.py", "engine/revenue_authenticity.py"):
            t = (ROOT / rel).read_text(encoding="utf-8")
            assert "未匹配到银行流水或第三方平台" not in t, "%s 仍是硬判话术" % rel
            assert "未匹配到银行或第三方平台收款" not in t, "%s 仍是硬判话术" % rel
            assert "尚未在本次" in t, "%s 未改为建议性措辞" % rel
# -*- coding: utf-8 -*-
"""泛化测试：新能力必须对**任意企业/行业/科目组合**成立，不得只在公司1 有效。

用户判据（原话）：「修改方案必须站在"适用所有行业/所有企业/所有同类场景"的角度，
不得针对用户举的那个具体例子写特例。判据：改动应当用**通用规则/数据表/优先级**表达，
新增一个同类对象时只需加一行数据，不需要改逻辑分支。」

因此这里**不测公司1 的具体数字**，而是用三组完全不同的合成企业（服务业/餐饮/制造），
断言：① 分类结论只由「账上科目」决定，与**企业名、行业**无关；
② 同一批科目换名字结论不变；③ 结论随科目变化（证明判据在数据里，不在代码分支里）。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _v(acct, obj, debit=0.0, credit=0.0):
    return {"account": "0000", "account_name": "%s/%s" % (acct, obj),
            "debit": debit, "credit": credit}


def _tx(cp, credit, summary="收款"):
    return {"counterparty": cp, "summary": summary, "credit": credit, "debit": 0.0}


# ── ① 三行业同构：结论只跟"科目"走，与行业/企业名无关 ─────────────────────────
class TestSameAccountsDifferentIndustries:
    CASES = [
        ("A广告传媒有限公司", "服务业", "应收账款", "客户款"),
        ("B餐饮管理有限公司", "餐饮业", "应收账款", "团餐款"),
        ("C精密制造有限公司", "制造业", "应收账款", "货款"),
    ]

    @pytest.mark.parametrize("company,industry,acct,label", CASES)
    def test_operating_when_receivable(self, company, industry, acct, label):
        """三家不同行业：客户款挂「应收账款」⇒ 一律经营性收款。"""
        from engine.bank_nature import build_ledger_index, classify_receipts
        vs = [_v(acct, company, debit=1_000_000.0)]
        r = classify_receipts([_tx(company, 1_000_000.0, label)], vs)
        assert r["operating"] == pytest.approx(1_000_000.0)
        assert r["undetermined"] == 0
        assert r["evidence_stats"]["序时账科目"] == pytest.approx(1_000_000.0)

    @pytest.mark.parametrize("company,industry,acct,label", CASES)
    def test_non_operating_when_other_payable(self, company, industry, acct, label):
        """同一批企业：款项挂「其他应付款」⇒ 一律非经营性（与行业无关）。"""
        from engine.bank_nature import build_ledger_index, classify_receipts
        vs = [_v("其他应付款", company, credit=800_000.0)]
        r = classify_receipts([_tx(company, 800_000.0, "往来款")], vs)
        assert r["non_operating"] == pytest.approx(800_000.0)
        assert r["operating"] == 0

    def test_deposit_card_is_operating_receipt(self):
        """餐饮业储值卡「预收账款」＝经营性收款（先收款后开票），不得因为"还没开票"判成隐匿。"""
        from engine.bank_nature import build_ledger_index, classify_receipts
        vs = [_v("预收账款", "某单位储值卡", credit=500_000.0)]
        r = classify_receipts([_tx("某单位储值卡", 500_000.0, "储值")], vs)
        assert r["operating"] == pytest.approx(500_000.0)


# ── ② 结论随科目变，而不随名字变 ─────────────────────────────────────────────
class TestConclusionFollowsAccountsNotNames:
    def test_same_name_different_account_flips(self):
        """同一个对手方名：挂应收账款→经营性；挂其他应付款→非经营性。

        这条直接证明"判据在账上科目，不在企业名/关键词"。
        """
        from engine.bank_nature import build_ledger_index, classify_receipts
        name = "某某科技有限公司"
        tx = _tx(name, 600_000.0, "货款")   # 摘要写"货款"（旧逻辑会判经营性）

        # 传**原始凭证行**（与生产链路一致）；索引由权威函数内部构建
        r1 = classify_receipts([tx], [_v("应收账款", name, debit=600_000.0)])
        r2 = classify_receipts([tx], [_v("其他应付款", name, credit=600_000.0)])
        assert r1["operating"] == pytest.approx(600_000.0)
        assert r2["non_operating"] == pytest.approx(600_000.0)

    def test_new_account_type_only_needs_one_data_row(self, monkeypatch):
        """新增一个同类科目**只加一行数据**即可生效 —— 不改逻辑分支。"""
        import engine.bank_nature as bn
        cfg = dict(bn._receipt_cfg())
        an = dict(cfg.get("account_natures") or {})
        an["未确认融资费用"] = "非经营性"          # ← 只加这一行
        cfg["account_natures"] = an
        monkeypatch.setattr(bn, "_receipt_cfg", lambda: cfg)
        assert bn.account_nature_of("未确认融资费用/某融资租赁") == "非经营性"

    def test_unmapped_account_is_undetermined_not_guessed(self, monkeypatch):
        """未登记的科目 ⇒ 待判定（不得默认算经营性收入）。"""
        import engine.bank_nature as bn
        cfg = dict(bn._receipt_cfg())
        cfg["account_natures"] = {"应收账款": "经营性"}
        monkeypatch.setattr(bn, "_receipt_cfg", lambda: cfg)
        assert bn.account_nature_of("长期待摊费用/某项目") is None


# ── ③ 推演层：与具体企业无关，按红线编号/通用框架触发 ────────────────────────
class TestLadderGenerality:
    def test_pack_redlines_get_ladder_others_empty(self):
        """契约（2026-10-03 反转）：**有专属推演包才产出**；没有就返回空，
        不得套模板念条目（用户："这段内容特别多余，删掉！！！为什么每个疑点都会有这段内容？"）。"""
        from engine.inference_ladder import ladder_for_suspicion
        for rid in ("RL-VAT-006", "RL-FUND-002", "RL-INC-002"):
            sec = ladder_for_suspicion({"redline_id": rid, "redline_name": "任意名"})
            assert sec["bullets"], rid
        for rid in ("RL-COST-003", "RL-NEW-999"):
            assert ladder_for_suspicion({"redline_id": rid, "redline_name": "任意名"}) == {}, rid

    def test_revenue_gap_works_for_any_amounts(self):
        """差集推演对任意金额/任意方向都成立（餐饮、制造同样适用）。"""
        from engine.inference_ladder import revenue_gap_reasoning
        for inv, bank in ((500_000, 300_000), (300_000, 500_000), (1_000_000, 1_000_000)):
            r = revenue_gap_reasoning(inv, bank)
            assert r["direction"]
            assert r["unexplained"] >= 0

    def test_channel_logic_is_data_driven(self, monkeypatch):
        """渠道逻辑来自数据表：改数据即改结论（证明不是写死在代码里的话术）。"""
        import engine.inference_ladder as il
        lib = {"收入差集": {"收款大于开票": [{"解释": "自定义解释", "科目": "—",
                                     "性质": "正常商业信用", "佐证": ["X"]}]},
               "渠道逻辑": {"公账收款": {"推论": "自定义渠道结论"}},
               "通用推演": {"框架": ["① 自定义框架"]}}
        monkeypatch.setattr(il, "_LADDERS", lib)
        r = il.revenue_gap_reasoning(100_000.0, 400_000.0)   # 差额需越过默认容差(1000)
        assert r["channel_note"] == "自定义渠道结论"
        assert any("自定义解释" in str(e.get("解释")) for e in r["explanations"])

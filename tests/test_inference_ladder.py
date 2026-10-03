# -*- coding: utf-8 -*-
"""点→面推演层（engine/inference_ladder）与"读账定性质"的测试。

用户 2026-10-03 两条要求：
  ①「是不是有开票未收款的应收账款，是不是有收款未开票的预收账款？」
     → 差集必须翻译成会计实质（应收/预收/往来），并落到"哪份资料能区分"。
  ②「如果你是老板，你会傻逼到未开票收入用公司公账来收款吗？」
     → 渠道逻辑必须写进报告：公账收款不能用来隐匿收入。
  ③「这种点到面的推断分析要接进一键分析按钮、每次生成报告都触发」
     → 每条疑点都要有推演段（本文件锁"每条都有"）。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ── ① 差集 → 会计实质 ────────────────────────────────────────────────────────
class TestRevenueGapReasoning:
    def test_invoice_more_than_receipts_is_receivable(self):
        """开票 > 收款 ⇒ 第一解释是应收账款（赊销），不是隐匿收入。"""
        from engine.inference_ladder import revenue_gap_reasoning
        r = revenue_gap_reasoning(1_000_000, 800_000, ar_movement=200_000)
        assert r["direction"] == "开票大于收款"
        assert r["explained_by"] == pytest.approx(200_000)
        assert r["unexplained"] == 0
        assert any("应收账款" in str(e.get("科目")) for e in r["explanations"])

    def test_receipts_more_than_invoice_is_advance_or_payable(self):
        """收款 > 开票 ⇒ 第一解释是预收账款/往来款，且必须给出渠道逻辑限制。"""
        from engine.inference_ladder import revenue_gap_reasoning
        r = revenue_gap_reasoning(1_000_000, 1_300_000, advance_movement=300_000)
        assert r["direction"] == "收款大于开票"
        assert any("预收账款" in str(e.get("科目")) for e in r["explanations"])
        assert "不会用公司公账" in r["channel_note"], "必须写明公账收款的渠道逻辑限制"
        assert r["unexplained"] == 0

    def test_unexplained_remainder_is_not_guessed(self):
        """账内科目解释不了的部分 ⇒ 记为未解释差额要求举证，不得默认算作违规。"""
        from engine.inference_ladder import revenue_gap_reasoning
        r = revenue_gap_reasoning(1_000_000, 1_500_000)
        assert r["unexplained"] == pytest.approx(500_000)
        assert "企业举证" in r["text"]

    def test_close_amounts_need_no_explanation(self):
        from engine.inference_ladder import revenue_gap_reasoning
        r = revenue_gap_reasoning(1_000_000, 1_000_500)
        assert r["direction"] == "基本吻合" and r["unexplained"] == 0

    def test_open_item_movement_reads_account_name_not_code(self):
        """应收账款净增必须按**科目名**读（旧代码读 account 编码 → 恒 0）。"""
        from engine.inference_ladder import open_item_movement
        vs = [{"account": "1122-00001", "account_name": "应收账款/某某公司",
               "debit": 1000.0, "credit": 0.0},
              {"account": "1122-00001", "account_name": "应收账款/某某公司",
               "debit": 0.0, "credit": 400.0},
              {"account": "2203", "account_name": "预收账款/某客户", "debit": 0.0, "credit": 300.0}]
        mv = open_item_movement(vs)
        assert mv["ar_movement"] == pytest.approx(600.0)
        assert mv["advance_movement"] == pytest.approx(300.0)


# ── ② 一条疑点一条推演段（"每次都触发"） ────────────────────────────────────
class TestLadderForSuspicion:
    def test_every_suspicion_gets_bullets(self):
        """任何疑点都必须产出推演段（有专属推演包用专属，没有退到通用框架）。"""
        from engine.inference_ladder import ladder_for_suspicion
        for s in ({"redline_id": "RL-VAT-006", "redline_name": "未开票收入长期为零"},
                  {"redline_id": "RL-XXX-999", "redline_name": "某未知疑点"}):
            sec = ladder_for_suspicion(s)
            assert sec["bullets"], s
            assert sec["heading"].startswith("六")

    def test_redline_pack_used_when_available(self):
        from engine.inference_ladder import ladder_for_suspicion
        sec = ladder_for_suspicion({"redline_id": "RL-FUND-002", "redline_name": "资金回流"})
        joined = " ".join(sec["bullets"])
        assert "借款合同" in joined or "配对" in joined

    def test_lateral_reasoning_takes_precedence(self):
        from engine.inference_ladder import revenue_gap_reasoning, ladder_for_suspicion
        lat = revenue_gap_reasoning(1_000_000, 1_300_000, advance_movement=300_000)
        sec = ladder_for_suspicion({"redline_id": "RL-VAT-006"}, lat)
        assert "预收账款" in " ".join(sec["bullets"])


# ── ③ 读账定性质（科目优先于关键词） ────────────────────────────────────────
class TestLedgerNature:
    def test_account_nature_longest_match(self):
        from engine.bank_nature import account_nature_of
        assert account_nature_of("应收账款/某某公司") == "经营性"
        assert account_nature_of("其他应付款/初永伟") == "非经营性"
        assert account_nature_of("预收账款/某客户") == "经营性"
        assert account_nature_of("没见过的科目") is None

    def test_ledger_beats_keywords(self):
        """账上挂「其他应付款」的个人收款，不得因为"名字像企业"而被当成经营收款。"""
        from engine.bank_nature import build_ledger_index, classify_credit
        ledger = build_ledger_index([
            {"account": "2241", "account_name": "其他应付款/某某科技有限公司",
             "debit": 0.0, "credit": 500000.0},
        ])
        label, nature = classify_credit(
            {"counterparty": "某某科技有限公司", "summary": "货款", "credit": 500000.0},
            ledger=ledger)
        assert label == "序时账-其他应付款"
        assert nature == "非经营性"

    def test_undetermined_when_no_ledger_and_no_keyword(self):
        from engine.bank_nature import classify_receipts
        r = classify_receipts([{"counterparty": "李昭阳", "summary": "转存", "credit": 100000.0}])
        assert r["undetermined"] == pytest.approx(100000.0)
        assert r["evidence_stats"]["未判定"] == pytest.approx(100000.0)

    def test_evidence_stats_disclose_source(self):
        """报告要能说清"这一笔是读账得出的还是猜摘要得出的"。"""
        from engine.bank_nature import build_ledger_index, classify_receipts
        vs = [{"account": "1122", "account_name": "应收账款/客户甲", "debit": 80000.0, "credit": 0.0}]
        r = classify_receipts([{"counterparty": "客户甲", "summary": "收款", "credit": 80000.0}], vs)
        assert r["has_ledger"] is True
        assert r["evidence_stats"]["序时账科目"] == pytest.approx(80000.0)
        assert r["undetermined"] == 0

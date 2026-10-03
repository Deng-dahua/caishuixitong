# -*- coding: utf-8 -*-
"""资金回流（VR025 → RL-FUND-002）准入口径 —— 规模 vs 整数特征、回流配对。

用户 2026-10-03 的两条指正：
  ①「RL-FUND-002 用"整万"当准入门槛偏窄，会漏报非整数的可疑金额
     （账上真实存在 1,071,343.80 这类）」
     → 口径：**规模决定要不要查，整数特征只作证据**；
  ②「"回流"目前只看该对象有没有转入，没做金额/时间配对，要件②③没有独立证据」
     → 口径：要件②＝金额接近配对、要件③＝配对发生在付款后短期内；**配不上就不认领**。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SPEC = {"id": "VR025", "name": "资金回流与公私混同检测",
        "required_sources": ["银行流水"], "limitations": "", "category": "资金"}


def _tx(cp, debit=0.0, credit=0.0, date="2025-03-10", summary="转存"):
    return {"counterparty": cp, "debit": debit, "credit": credit,
            "date": date, "summary": summary}


def _run(rows):
    from engine.verified_rule_engine import _scan_fund_recirculation
    return _scan_fund_recirculation({"bank_txs": rows, "pur_invs": [], "target_entity": {}}, SPEC)


def _hits(res):
    return [h["index"] for h in res[0]["constituent_hits"]] if res else []


# ── ① 规模门槛：非整数的大额往来不得被"整万"挡在门外 ─────────────────────────
class TestScaleNotRoundness:
    def test_non_round_large_outflow_still_raised(self):
        """1,071,343.80（非整万）必须进入检查范围——旧实现下它一笔都进不了 big_out。"""
        res = _run([_tx("李昭阳", debit=1_071_343.80)])
        assert res, "非整数大额转出被静默漏报（整万当门槛）"
        # ★ 规模门槛与"是否回流"是两件事：本用例只锁"不许因非整万而漏报"，
        #   单向转出按新契约不认领要件（见 TestRecirculationPairing）
        assert res[0]["level"] == "待核验" and _hits(res) == []
        assert "整数特征仅作证据" in res[0]["detail"] or "未见整数金额特征" in res[0]["detail"]

    def test_round_feature_is_evidence_not_gate(self):
        from engine.verified_rule_engine import _is_round_amount
        assert _is_round_amount(600000) is True
        assert _is_round_amount(1_071_343.80) is False

    def test_below_scale_floor_not_raised(self):
        """规模不到（单笔＜10万且累计＜50万）不得仅凭"整数"立此项。"""
        res = _run([_tx("张某", debit=30000.0, date="2025-03-01"),
                    _tx("张某", debit=30000.0, date="2025-03-02")])
        assert not res


# ── ② 回流配对：要件②③必须有独立证据 ─────────────────────────────────────────
class TestRecirculationPairing:
    def test_matched_pair_claims_constituents_1_2_3(self):
        res = _run([_tx("王某", debit=600000, date="2025-03-10"),
                    _tx("王某", credit=597000, date="2025-03-18")])
        assert _hits(res) == [1, 2, 3]
        txt = res[0]["detail"]
        assert "配对" in txt and "间隔8天" in txt

    def test_unpaired_single_direction_not_claimed(self):
        """只转出不转入：只说"单向大额转出"，不得认领要件②③（"回流"未成立）。"""
        res = _run([_tx("李某", debit=800000, date="2025-03-10")])
        # ★ 契约收紧：单向转出**不认领任何要件**（要件①要求"回流至本企业"，不是"转出"）
        assert _hits(res) == []
        assert "单向" in res[0]["detail"]

    def test_amount_far_apart_not_claimed(self):
        res = _run([_tx("赵某", debit=600000, date="2025-03-10"),
                    _tx("赵某", credit=100000, date="2025-03-18")])
        assert _hits(res) == []   # 金额差 83%：不构成"金额接近"，不得认领要件①②③

    def test_outside_time_window_not_claimed(self):
        res = _run([_tx("钱某", debit=600000, date="2025-01-05"),
                    _tx("钱某", credit=600000, date="2025-07-24")])
        assert _hits(res) == []   # 间隔 200 天：不在短期窗口内

    def test_inflow_before_outflow_not_claimed(self):
        """先收后付不是回流（时间方向必须"先转出、后转入"）。"""
        res = _run([_tx("孙某", credit=600000, date="2025-03-01"),
                    _tx("孙某", debit=600000, date="2025-03-10")])
        assert _hits(res) == []   # 先收后付：方向不符"付款后回流"

    def test_pairing_prefers_closest_amount(self):
        from engine.verified_rule_engine import _pair_recirculation_flows
        out = [{"date": "2025-03-10", "amount": 600000.0}]
        ins = [{"date": "2025-03-11", "amount": 570000.0},
               {"date": "2025-03-12", "amount": 599000.0}]
        pairs = _pair_recirculation_flows(out, ins)
        assert len(pairs) == 1
        assert pairs[0]["in_amount"] == pytest.approx(599000.0)

    def test_each_inflow_used_once(self):
        """一笔转入不得被多笔转出重复配对（否则配对数是虚的）。"""
        from engine.verified_rule_engine import _pair_recirculation_flows
        out = [{"date": "2025-03-10", "amount": 500000.0},
               {"date": "2025-03-11", "amount": 500000.0}]
        ins = [{"date": "2025-03-12", "amount": 500000.0}]
        assert len(_pair_recirculation_flows(out, ins)) == 1


# ── ③ 口径参数集中（改口径只改一处） ─────────────────────────────────────────
def test_scale_params_single_source():
    import engine.verified_rule_engine as v
    assert v._LARGE_TX_FLOOR == 100000.0
    assert v._PERSON_TX_TOTAL_FLOOR == 500000.0
    assert v._RECIRCULATE_WINDOW_DAYS == 30

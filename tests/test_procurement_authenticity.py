# -*- coding: utf-8 -*-
"""采购来源真实性核验（engine/procurement_authenticity）的测试。

背景（用户）："虽然供应商的范围有新的定义（＝成本类），**采购来源的真实性还是值得严谨的查一查**，
这是一个很好的疑点，就得看**如何证实**采购来源的真实性。"
→ 判据必须**全部可证伪**（每条都能由某份资料/外部数据证实或排除），且**不得产生噪声**。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _inv(seller, no, amount, date="2025-03-10"):
    return {"seller": seller, "invoice_no": no, "total": amount, "amount": amount, "date": date}


def _tx(cp, debit):
    return {"counterparty": cp, "debit": debit, "credit": 0.0, "date": "2025-03-20"}


class TestVerdicts:
    def test_no_anomaly_returns_empty(self):
        """有票有付款、金额不顶额、无同日同额 ⇒ **不得产出任何线索**（宁缺勿滥）。"""
        from engine.procurement_authenticity import verify_procurement_authenticity
        pur = [_inv("某某广告有限公司", "A1", 300000.0)]
        bank = [_tx("某某广告有限公司", 300000.0)]
        r = verify_procurement_authenticity(pur, bank, cost_only=False)
        assert r["facts"] == []
        assert "未检出" in r["note"]

    def test_z1_no_payment_is_flagged(self):
        """有票无付款（金额达门槛）⇒ 产出 Z1，并给出**可证实资料**。"""
        from engine.procurement_authenticity import verify_procurement_authenticity
        r = verify_procurement_authenticity([_inv("某某服务有限公司", "B1", 600000.0)], [], cost_only=False)
        codes = [f["code"] for f in r["facts"]]
        assert "Z1" in codes
        f = [x for x in r["facts"] if x["code"] == "Z1"][0]
        assert f["可证实资料"], "必须写清**用什么资料能证实/排除**（可证伪是这条判据的生命线）"
        assert f["需核实"] and len(f["需核实"]) >= 10, "必须写清要核实什么"

    def test_z3_same_day_same_amount_needs_materiality(self):
        """同日同额须**达金额门槛**才算线索 —— 30 元的保险、100 元的京东不算（噪声）。"""
        from engine.procurement_authenticity import verify_procurement_authenticity
        tiny = [_inv("某保险公司", "T1", 30.0), _inv("某保险公司", "T2", 30.0, "2025-01-12")]
        assert verify_procurement_authenticity(tiny, [], cost_only=False)["facts"] == []
        big = [_inv("某服务有限公司", "D1", 60000.0, "2025-03-10"),
               _inv("某服务有限公司", "D2", 60000.0, "2025-03-10")]
        assert any(f["code"] == "Z3" for f in verify_procurement_authenticity(big, [], cost_only=False)["facts"])


class TestNearLimitJudge:
    def test_only_tax_control_limits(self):
        """顶额只针对**税控限额档位**（1万/10万/100万），不是"任意整数"。"""
        from engine.procurement_authenticity import _near_limit
        assert _near_limit(69600) is None          # 凑整 ≠ 顶额
        assert _near_limit(680000) is None
        assert _near_limit(99999) == pytest.approx(99999.99)
        assert _near_limit(99000) == pytest.approx(99999.99)

    def test_above_limit_is_not_near_limit(self):
        """**超过**限额不是"顶额"（旧判据差额为负也通过 ⇒ 任何金额都命中）。"""
        from engine.procurement_authenticity import _near_limit
        assert _near_limit(1000000) is None
        assert _near_limit(500000) is None


class TestScope:
    def test_payment_matching_uses_full_invoice_set(self):
        """票↔款匹配（Z2）必须用**全量**发票 —— 实测教训：用"成本类"收窄集合会把
        已开票的销方误报成"无该主体开票"（林超攀明明开了 60 万的票）。"""
        import inspect
        from engine import procurement_authenticity as pa
        src = inspect.getsource(pa.verify_procurement_authenticity)
        assert "_all_sellers" in src, "Z2 必须基于全量销方集合"


class TestCostScope:
    def test_cost_scope_filters_expense_counterparties(self):
        """成本类口径：期间费用类对手方（保险/餐饮/京东）不参与采购来源形态线索。

        `cost_only=True`（默认）下，若这些票被判为费用/待核，则不产出形态线索；
        `cost_only=False` 时同样数据才可能命中——两者差异即为口径生效的证明。
        """
        from engine.procurement_authenticity import verify_procurement_authenticity
        pur = [_inv("某保险股份有限公司", "P1", 60000.0, "2025-03-10"),
               _inv("某保险股份有限公司", "P2", 60000.0, "2025-03-10")]
        r_default = verify_procurement_authenticity(pur, [], industry=["广告", "传媒"])
        r_all = verify_procurement_authenticity(pur, [], industry=["广告", "传媒"], cost_only=False)
        assert len(r_all["facts"]) >= len(r_default["facts"])

# -*- coding: utf-8 -*-
"""成本费用口径补强测试（2026-09-15）。

覆盖：
A) financial_analyzer ①-2「取得发票 vs 成本费用合计」——触发与去重；
B) structure_mismatch_detector `_check_cost_goods_structure`「成本结构与行业差异」——触发/门槛/行业未命中；
   以及 `_AGRI_INDUSTRY` 白名单修正（"林"不再误伤"吉林"）。
"""

import unittest

from engine.financial_analyzer import _check_tax_audit_indicators
from engine.structure_mismatch_detector import (
    _check_agri_input_mismatch,
    _check_cost_goods_structure,
)


class _Ctx:
    def __init__(self, industry):
        self.company_profile = {"industry": industry}
        self.industry_profile = None


def _indicators(income, pur_invs):
    return _check_tax_audit_indicators({}, income, [], [], pur_invs, None, None)


class CostExpenseCoverageTest(unittest.TestCase):
    def test_total_cost_expense_coverage_fires(self):
        # cost 口径 0.85（① 不报），含期间费用后合计覆盖率 0.708 < 0.8 → ①-2 触发
        income = {"revenue": 2000000, "cost": 1000000,
                  "selling_expense": 100000, "admin_expense": 100000, "finance_expense": 0}
        pur = [{"amount": 850000}]
        hits = [f for f in _indicators(income, pur) if f.get("indicator") == "purchase_invoice_match_total"]
        self.assertEqual(len(hits), 1)
        self.assertIn("成本费用合计", hits[0]["type"])

    def test_dedup_when_cost_only_fires(self):
        # cost 口径 0.70（① 已报）→ ①-2 不再重复输出
        income = {"revenue": 2000000, "cost": 1000000,
                  "selling_expense": 100000, "admin_expense": 100000, "finance_expense": 0}
        pur = [{"amount": 700000}]
        hits = [f for f in _indicators(income, pur) if f.get("indicator") == "purchase_invoice_match_total"]
        self.assertEqual(len(hits), 0)


class CostGoodsStructureTest(unittest.TestCase):
    def test_garden_seedling_share_too_high(self):
        ctx = _Ctx("景观园林工程")
        pur = [{"goods": "苗木（香樟）", "amount": 800000},
               {"goods": "沙子", "amount": 100000}]
        hits = _check_cost_goods_structure(pur, ctx)
        self.assertTrue(hits)
        self.assertTrue(any("成本结构" in h["type"] for h in hits))
        self.assertTrue(all(h["level"] == "待核验" for h in hits))

    def test_industry_unmatched_no_output(self):
        ctx = _Ctx("信息技术服务")
        pur = [{"goods": "苗木", "amount": 800000}]
        self.assertEqual(_check_cost_goods_structure(pur, ctx), [])

    def test_below_amount_threshold_no_output(self):
        ctx = _Ctx("景观园林工程")
        pur = [{"goods": "苗木", "amount": 100000}]  # 合计 < 50 万门槛
        self.assertEqual(_check_cost_goods_structure(pur, ctx), [])

    def test_building_gravel_share_too_low(self):
        ctx = _Ctx("建筑工程")
        pur = [{"goods": "钢材", "amount": 900000}]  # 砂石占比 0，明显低于参考区间
        hits = _check_cost_goods_structure(pur, ctx)
        self.assertTrue(hits)


class AgriIndustryWhitelistTest(unittest.TestCase):
    def test_jilin_no_longer_skipped(self):
        # 旧白名单含裸"林"，"吉林…"会被误判为涉农而跳过；修正后应正常提示
        ctx = _Ctx("吉林贸易有限公司")
        pur = [{"goods": "农产品", "amount": 200000}]
        hits = _check_agri_input_mismatch(pur, ctx)
        self.assertTrue(hits)

    def test_garden_still_skipped(self):
        # 园林本身与农产品相关，仍应跳过（不误报）
        ctx = _Ctx("景观园林工程")
        pur = [{"goods": "农产品", "amount": 200000}]
        self.assertEqual(_check_agri_input_mismatch(pur, ctx), [])


if __name__ == "__main__":
    unittest.main()

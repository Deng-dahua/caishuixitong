# -*- coding: utf-8 -*-
"""收入真实性（账外收入嫌疑）三维度能力测试（2026-09-14 新增）。

覆盖：ar_aging 三态、revenue_authenticity 综合裁定三态、VR018 方向重构
（申报>开票=未开票收入已申报合法 / 开票>申报=漏报待核）。
"""

import unittest

from engine.ar_aging import run_ar_aging_check
from engine.revenue_authenticity import run_revenue_authenticity_check


class ArAgingTest(unittest.TestCase):
    def test_no_data_available_false(self):
        res = run_ar_aging_check({"accounts_receivable": []})
        self.assertFalse(res["available"])
        self.assertEqual(res["verdict"], "资料缺失待核")

    def test_unreceived_and_long_aging(self):
        data = {"accounts_receivable": [
            {"客户名称": "甲公司", "应收金额": 100000, "已收金额": 20000,
             "未收金额": 80000, "账龄": "400天", "开票日期": "2025-01-15"},
            {"客户名称": "乙公司", "应收金额": 50000, "已收金额": 0,
             "未收金额": 50000, "账龄": "200天", "开票日期": "2025-06-01"},
        ]}
        res = run_ar_aging_check(data, base_date="2026-09-14")
        self.assertTrue(res["available"])
        m = res["metrics"]
        self.assertAlmostEqual(m["ar_unreceived_total"], 130000.0, places=1)
        self.assertEqual(m["ar_long_aging_count"], 1)       # 仅甲公司超 365 天
        self.assertEqual(m["ar_max_aging_days"], 400)
        self.assertEqual(m["ar_customers_with_unreceived"], 2)

    def test_trial_balance_fallback(self):
        data = {"accounts_receivable": [],
                "trial_balance": [{"科目名称": "应收账款", "期末余额": 300000}]}
        res = run_ar_aging_check(data, base_date="2026-09-14")
        self.assertTrue(res["available"])
        self.assertTrue(res["metrics"].get("ar_from_trial_balance"))
        self.assertAlmostEqual(res["metrics"]["ar_unreceived_total"], 300000.0, places=1)
        self.assertEqual(res["metrics"]["ar_customers"], 0)  # 无客户明细


class RevenueAuthenticityTest(unittest.TestCase):
    def test_no_data_available_false(self):
        res = run_revenue_authenticity_check({})
        self.assertFalse(res["available"])
        self.assertEqual(res["verdict"], "资料缺失待核")

    def test_person_inflow_to_personal_account(self):
        # 银行收款明显超过申报，且部分经个人账户归集 → 账外收入嫌疑铁证
        data = {
            "sal_invs": [{"amount": 1000000, "buyer": "丙", "date": "2026-01-15"}],
            "bank_txs": [{"credit": 1200000, "counterparty": "张三"}],
            "tax_declarations": [{"sales_amount": 800000, "period": "2026-01"}],
        }
        res = run_revenue_authenticity_check(data, base_date="2026-09-14")
        self.assertTrue(res["available"])
        self.assertIn("账外收入嫌疑", res["verdict"])
        self.assertTrue(res["metrics"]["start_signal"])
        self.assertGreater(res["metrics"]["person_inflow_amount"], 0)

    def test_declared_gt_invoiced_is_benign(self):
        # 申报>开票：未开票收入已依法申报，不构成账外嫌疑
        data = {
            "sal_invs": [{"amount": 800000, "buyer": "丙", "date": "2026-01-15"}],
            "bank_txs": [{"credit": 200000, "counterparty": "丁公司"}],
            "tax_declarations": [{"sales_amount": 1000000, "period": "2026-01"}],
        }
        res = run_revenue_authenticity_check(data, base_date="2026-09-14")
        d1 = res["dimensions"]["invoice_vs_declaration"]
        self.assertTrue(d1["declared_gt_invoiced"])
        self.assertNotIn("账外收入嫌疑", res["verdict"])

    def test_unmatched_long_aging_is_suspicion(self):
        # 开票未收回，且应收长期挂账 → 账外收入嫌疑（疑虚构）
        data = {
            "sal_invs": [{"amount": 1000000, "buyer": "戊", "date": "2025-01-10"}],
            "bank_txs": [{"credit": 100000, "counterparty": "戊公司"}],  # 仅收回少量
            "tax_declarations": [{"sales_amount": 1000000, "period": "2026-01"}],
            "accounts_receivable": [
                {"客户名称": "戊公司", "应收金额": 1000000, "已收金额": 100000,
                 "未收金额": 900000, "账龄": "500天", "开票日期": "2025-01-10"},
            ],
        }
        res = run_revenue_authenticity_check(data, base_date="2026-09-14")
        self.assertIn("账外收入嫌疑", res["verdict"])
        self.assertGreater(res["metrics"]["ar_long_aging_count"], 0)


class VR018DirectionTest(unittest.TestCase):
    def _spec(self):
        return {"id": "VR018", "name": "申报-开票差额",
                "required_sources": ["tax_declarations", "sal_invs"],
                "layer": "通用基础规则", "status": "verified_executable_screening",
                "limitation": "x"}

    def test_declared_gt_invoiced_is_info(self):
        # 申报>开票：未开票收入已申报，合法 → 信息级，不构成账外嫌疑
        from engine.verified_rule_engine import _scan_vat_declaration_sales_gap
        data = {
            "tax_declarations": [{"sales_amount": 1000000, "period": "2026-01"}],
            "sal_invs": [{"amount": 800000, "date": "2026-01-15"}],
        }
        hits = _scan_vat_declaration_sales_gap(data, self._spec())
        self.assertEqual(len(hits), 1)
        f = hits[0]
        self.assertEqual(f["level"], "信息")
        self.assertIn("不构成账外收入嫌疑", f["detail"])

    def test_invoiced_gt_declared_is_investigation(self):
        # 开票>申报：漏报方向 → 调查优先级
        from engine.verified_rule_engine import _scan_vat_declaration_sales_gap
        data = {
            "tax_declarations": [{"sales_amount": 800000, "period": "2026-01"}],
            "sal_invs": [{"amount": 1000000, "date": "2026-01-15"}],
        }
        hits = _scan_vat_declaration_sales_gap(data, self._spec())
        self.assertEqual(len(hits), 1)
        f = hits[0]
        self.assertEqual(f["priority"], "调查优先级")
        self.assertIn("开票>申报", f["detail"])


if __name__ == "__main__":
    unittest.main()

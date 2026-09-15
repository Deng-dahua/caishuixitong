# -*- coding: utf-8 -*-
"""跨文件逐月对等勾稽测试（2026-09-15）。

覆盖：收入三方逐月一致 / 某月不一致 / 工资+个税多方一致 / 单源不报 / 无数据不报。
"""

import unittest

from engine.monthly_reconcile import run_cross_period_reconcile


def _types(findings):
    return [f["type"] for f in findings]


class RevenueReconcileTest(unittest.TestCase):
    def _data(self, sal_inv_amount=245827.02):
        return {
            "vouchers": [{"date": "2026-01-15", "account": "主营业务收入", "credit": 245827.02}],
            "sal_invs": [{"date": "2026-01-20", "amount": sal_inv_amount}],
            "tax_declarations": [{"period": "2026-01", "sales_amount": 245827.02,
                                  "_declaration_type": "vat"}],
        }

    def test_three_sources_equal(self):
        f = run_cross_period_reconcile(self._data())
        self.assertTrue(any("对等勾稽一致：收入多源对等" in t for t in _types(f)))
        self.assertFalse(any("不匹配" in t for t in _types(f)))

    def test_month_mismatch_flagged(self):
        f = run_cross_period_reconcile(self._data(sal_inv_amount=300000))
        self.assertTrue(any("收入多源对等" in t and "不匹配" in t and "2026-01" in t for t in _types(f)))


class WageReconcileTest(unittest.TestCase):
    def test_salary_vs_voucher_equal(self):
        data = {
            "salaries": [{"name": "张三", "gross": 74000, "tax": 938.8,
                          "period_start": "2026-01-01"}],
            "vouchers": [
                {"date": "2026-01-31", "account": "应付职工薪酬", "credit": 74000},
                {"date": "2026-01-31", "account": "应交个人所得税", "credit": 938.8},
            ],
        }
        f = run_cross_period_reconcile(data)
        self.assertTrue(any("工资多源对等" in t for t in _types(f)))
        self.assertTrue(any("个税三源对等" in t for t in _types(f)))

    def test_single_source_no_finding(self):
        # 只有工资表、无个税申报/序时账 → 不足两方，不输出
        data = {"salaries": [{"name": "张三", "gross": 74000, "period_start": "2026-01-01"}]}
        f = run_cross_period_reconcile(data)
        self.assertEqual(f, [])

    def test_no_data(self):
        self.assertEqual(run_cross_period_reconcile({}), [])


class VATAndLedgerReconcileTest(unittest.TestCase):
    def test_input_vat_reconcile(self):
        # 进项发票税额 / 抵扣认证税额 / 序时账进项税额(借方) 三方一致
        data = {
            "pur_invs": [{"date": "2025-01-10", "tax": 1000}],
            "input_vat_deductions": [{"date": "2025-01-10", "deductible_tax": 1000}],
            "vouchers": [{"month_no": "1", "account": "22210105",
                          "account_name": "应交税费/应交增值税/进项税额", "debit": 1000, "credit": 0}],
        }
        types = [f["type"] for f in run_cross_period_reconcile(data)]
        self.assertTrue(any("进项税额对等" in t for t in types))

    def test_ledger_reconcile_flag(self):
        from engine.monthly_reconcile import run_ledger_reconcile
        vouchers = [{"account": "600102", "debit": 0, "credit": 100000}]
        tb = [{"code": "6001", "name": "主营业务收入", "current_debit": 0, "current_credit": 90000}]
        f = run_ledger_reconcile(vouchers, tb)
        self.assertEqual(len(f), 1)
        self.assertIn("账账不符", f[0]["type"])

    def test_ledger_reconcile_equal_no_output(self):
        from engine.monthly_reconcile import run_ledger_reconcile
        vouchers = [{"account": "600102", "debit": 0, "credit": 1000}]
        tb = [{"code": "6001", "name": "主营业务收入", "current_debit": 0, "current_credit": 1000}]
        self.assertEqual(run_ledger_reconcile(vouchers, tb), [])


if __name__ == "__main__":
    unittest.main()

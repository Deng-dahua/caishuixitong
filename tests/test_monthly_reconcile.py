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


class ARAPReconcileTest(unittest.TestCase):
    def test_ar_equal(self):
        # 开具发票不含税 = 序时账应收账款借方 → 一致
        data = {
            "sal_invs": [{"date": "2025-01-20", "amount": 500000}],
            "vouchers": [{"month_no": "1", "account": "1122",
                          "account_name": "应收账款", "debit": 500000, "credit": 0}],
        }
        types = [f["type"] for f in run_cross_period_reconcile(data)]
        self.assertTrue(any("应收账款发生额对等" in t for t in types))
        self.assertFalse(any("不匹配" in t for t in types))

    def test_ap_mismatch_flagged(self):
        # 取得发票 300000 ≠ 应付账款贷方 280000 → 待核
        data = {
            "pur_invs": [{"date": "2025-02-10", "amount": 300000}],
            "vouchers": [{"month_no": "2", "account": "2202",
                          "account_name": "应付账款", "debit": 0, "credit": 280000}],
        }
        types = [f["type"] for f in run_cross_period_reconcile(data)]
        self.assertTrue(any("应付账款发生额对等" in t and "不匹配" in t and "2025-02" in t
                            for t in types))

    def test_ar_single_source_no_output(self):
        # 只有开票、无序时账 → 不足两方不报
        data = {"sal_invs": [{"date": "2025-01-20", "amount": 500000}]}
        self.assertEqual(run_cross_period_reconcile(data), [])


class RateConsistencyTest(unittest.TestCase):
    def test_revenue_rate_consistent(self):
        # 主营业务收入 1000000，销项税额 130000 → 13% 一致
        data = {
            "sal_invs": [{"date": "2025-01-20", "amount": 1000000}],
            "vouchers": [
                {"month_no": "1", "account": "6001", "account_name": "主营业务收入",
                 "debit": 0, "credit": 1000000},
                {"month_no": "1", "account": "22210102",
                 "account_name": "应交税费/应交增值税/销项税额", "debit": 0, "credit": 130000},
            ],
        }
        types = [f["type"] for f in run_cross_period_reconcile(data)]
        self.assertTrue(any("收入税价配比" in t for t in types))
        self.assertFalse(any("异常" in t for t in types))

    def test_revenue_rate_anomaly_flagged(self):
        # 主营业务收入 1000000，销项税额 170000 → 17% 偏离常见税率 → 待核
        data = {
            "sal_invs": [{"date": "2025-01-20", "amount": 1000000}],
            "vouchers": [
                {"month_no": "1", "account": "6001", "account_name": "主营业务收入",
                 "debit": 0, "credit": 1000000},
                {"month_no": "1", "account": "22210102",
                 "account_name": "应交税费/应交增值税/销项税额", "debit": 0, "credit": 170000},
            ],
        }
        types = [f["type"] for f in run_cross_period_reconcile(data)]
        self.assertTrue(any("收入税价配比" in t and "异常" in t for t in types))

    def test_purchase_rate_consistent(self):
        # 取得发票不含税 800000，进项税额 104000 → 13% 一致
        data = {
            "pur_invs": [{"date": "2025-01-10", "amount": 800000}],
            "vouchers": [{"month_no": "1", "account": "22210101",
                          "account_name": "应交税费/应交增值税/进项税额",
                          "debit": 104000, "credit": 0}],
        }
        types = [f["type"] for f in run_cross_period_reconcile(data)]
        self.assertTrue(any("采购税价配比" in t for t in types))


class FixedAssetReconcileTest(unittest.TestCase):
    def _tb(self, fa_debit, dep_credit):
        return [
            {"code": "1601", "name": "固定资产", "close_debit": fa_debit, "close_credit": 0},
            {"code": "1602", "name": "累计折旧", "close_debit": 0, "close_credit": dep_credit},
        ]

    def test_fa_equal(self):
        # 清单原值 1000000 / 累计折旧 200000 ↔ 余额表 1601借1000000 / 1602贷200000
        data = {
            "fixed_assets": [
                {"资产原值": 600000, "累计折旧": 120000},
                {"原值": 400000, "累计折旧": 80000},
            ],
            "trial_balance": self._tb(1000000, 200000),
        }
        types = [f["type"] for f in run_cross_period_reconcile(data)]
        self.assertTrue(any("固定资产原值勾稽" in t for t in types))
        self.assertTrue(any("累计折旧勾稽" in t for t in types))

    def test_fa_mismatch_flagged(self):
        # 清单原值 1000000 ↔ 余额表 1601借 900000 → 待核
        data = {
            "fixed_assets": [{"原值": 1000000, "累计折旧": 200000}],
            "trial_balance": self._tb(900000, 200000),
        }
        types = [f["type"] for f in run_cross_period_reconcile(data)]
        self.assertTrue(any("固定资产原值勾稽" in t and "不一致" in t for t in types))

    def test_fa_net_plus_dep_fallback(self):
        # 仅给净值+累计折旧（无原值列）→ 回推原值 = 净值+折旧
        from engine.monthly_reconcile import _fixed_asset_series
        gross, accum = _fixed_asset_series([
            {"净值": 480000, "累计折旧": 120000},
            {"净值": 320000, "累计折旧": 80000},
        ])
        self.assertAlmostEqual(gross, 1000000.0)
        self.assertAlmostEqual(accum, 200000.0)


if __name__ == "__main__":
    unittest.main()

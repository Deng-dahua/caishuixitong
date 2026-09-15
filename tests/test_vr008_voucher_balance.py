# -*- coding: utf-8 -*-
"""VR008 同一凭证借贷不平 —— 分组键月份兜底测试（2026-09-15）。

背景：序时账常只有"记账月份"（纯月序 1~12）而无完整日期。原实现直接
`_month(row["date"])`（需≥6位数字，否则返回空串）→ 分组键退化为 ("", 凭证号)，
**跨月同号凭证被合并**：既可能凭空造出不平，也可能正负相抵掩盖真实不平。
"""

import unittest

from engine.verified_rule_engine import (
    VERIFIED_RULE_CATALOG,
    _scan_voucher_balance,
    _voucher_month,
)

_SPEC = next(s for s in VERIFIED_RULE_CATALOG if s["id"] == "VR008")


class VoucherMonthTest(unittest.TestCase):
    def test_full_date(self):
        self.assertEqual(_voucher_month({"date": "2025-01-15"}), "202501")

    def test_bare_month_no(self):
        """无完整日期时回退记账月份，纯月序补零"""
        self.assertEqual(_voucher_month({"month_no": "1"}), "01")
        self.assertEqual(_voucher_month({"记账月份": "12"}), "12")

    def test_missing_returns_empty(self):
        self.assertEqual(_voucher_month({}), "")


class VoucherBalanceScanTest(unittest.TestCase):
    def test_balanced_no_finding(self):
        data = {"vouchers": [
            {"month_no": "1", "voucher_no": "记-1", "debit": 100, "credit": 0},
            {"month_no": "1", "voucher_no": "记-1", "debit": 0, "credit": 100},
        ]}
        self.assertEqual(_scan_voucher_balance(data, _SPEC), [])

    def test_same_voucher_no_across_months_not_merged(self):
        """关键用例：1月记-1 差 +10、2月记-1 差 -10。

        正确：按月份分开判定 → 2 张不平。
        旧缺陷：月份为空被合并成一组 → 190/190 相抵为 0 → 漏报。
        """
        data = {"vouchers": [
            {"month_no": "1", "voucher_no": "记-1", "debit": 100, "credit": 90},
            {"month_no": "2", "voucher_no": "记-1", "debit": 90, "credit": 100},
        ]}
        res = _scan_voucher_balance(data, _SPEC)
        self.assertEqual(len(res), 1)
        self.assertIn("有2张凭证", res[0]["detail"])

    def test_empty_voucher_no_skipped(self):
        data = {"vouchers": [
            {"month_no": "1", "voucher_no": "", "debit": 100, "credit": 0},
        ]}
        self.assertEqual(_scan_voucher_balance(data, _SPEC), [])

    def test_real_imbalance_reported(self):
        data = {"vouchers": [
            {"month_no": "3", "voucher_no": "记-7", "debit": 5000, "credit": 0},
        ]}
        res = _scan_voucher_balance(data, _SPEC)
        self.assertEqual(len(res), 1)
        self.assertIn("03月", res[0]["detail"])


if __name__ == "__main__":
    unittest.main()

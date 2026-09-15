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
    _row_month,
    _infer_year_from_months,
    _monthly_amount,
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


class RowMonthConvergenceTest(unittest.TestCase):
    """2026-09-15 收敛修复：把「按月聚合」类 VR 规则统一接上月份兜底。"""

    def test_row_month_full_date(self):
        self.assertEqual(_row_month({"date": "2025-03-08"}), "202503")

    def test_row_month_bare_no_no_hint(self):
        """无年份提示：纯月序只补零为 MM（至少保证同源按月聚合不丢数据）"""
        self.assertEqual(_row_month({"month_no": "3"}), "03")
        self.assertEqual(_row_month({"记账月份": "12"}), "12")

    def test_row_month_bare_no_with_hint(self):
        """有年份提示：纯月序展开成 YYYYMM（与申报表/发票对齐，跨源比对可用）"""
        self.assertEqual(_row_month({"month_no": "3"}, "2025"), "202503")
        self.assertEqual(_row_month({"记账月份": "1"}, "2024"), "202401")

    def test_infer_year_from_months(self):
        self.assertEqual(_infer_year_from_months(["202501", "202502", "202503"]), "2025")
        self.assertEqual(_infer_year_from_months(["03", "03", "12"]), "")  # 无 4 位年份

    def test_monthly_amount_keeps_bare_month_rows(self):
        """关键回归：旧实现 `_month(row['date'])` 在记账月份-only 行上返回空串、
        被 `if month:` 静默丢弃（整月数据丢失）。新实现 `_row_month` 返回 MM，应保留。"""
        rows = [
            {"month_no": "3", "credit": 100.0},
            {"month_no": "3", "credit": 50.0},
            {"month_no": "5", "credit": 200.0},
        ]
        totals = _monthly_amount(rows, lambda r: r["credit"])
        # 不应被丢弃：03 月累计 150、05 月累计 200
        self.assertAlmostEqual(totals.get("03", 0.0), 150.0)
        self.assertAlmostEqual(totals.get("05", 0.0), 200.0)

    def test_monthly_amount_aligns_to_invoice_year(self):
        """跨源对齐：发票有完整 YYYYMM，银行/序时账只有记账月份 → 按推断年份展开对齐。"""
        invoices = [{"invoice_date": "2025-03-10", "amount": 1000.0}]
        bank = [{"month_no": "3", "credit": 800.0}]
        inv_total = _monthly_amount(invoices, lambda r: r["amount"])
        year_hint = _infer_year_from_months(inv_total.keys())
        bank_total = _monthly_amount(bank, lambda r: r["credit"], year_hint=year_hint)
        # 银行 03 月应被对齐到 202503，与发票同键
        self.assertAlmostEqual(bank_total.get("202503", 0.0), 800.0)


if __name__ == "__main__":
    unittest.main()

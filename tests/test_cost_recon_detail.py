# -*- coding: utf-8 -*-
"""主营业务成本「两口径勾稽明细」回归测试（engine/cost_recon_detail.py）。

测试的是**派生规则**，不针对任何具体企业：
  · 发票类目口径构成取自 pipeline 已算好的 core 拆分（单一权威，不重跑 classify）；
  · 账面口径构成 = 序时账 6401 本期借方发生额（期末结转的贷方行不计入）；
  · 差异 = 发票口径 − 账面口径，并给出归因与可核资料；
  · **无论是否超阈值都产出**（合规留痕）；
  · 取不到的数据明说「未取得」，不静默顶替。
"""
import unittest

from engine.cost_recon_detail import build_cost_recon_detail


def _rd(inv_total=1000000.0, book_total=1010000.0, with_inv=True, with_book=True):
    es = {}
    if with_inv:
        es["biz_cost_classification"] = {
            "core_cost_amount": inv_total, "core_cost_count": 3,
            "core_goods_breakdown": [
                {"goods": "原料A", "count": 2, "amount": 700000.0},
                {"goods": "原料B", "count": 1, "amount": 300000.0},
            ],
            "core_cost_supplier_breakdown": [{"seller": "甲供应商", "count": 3, "amount": inv_total}],
            "core_cost_invoices": [
                {"inv_no": "INV001", "date": "2025-01-05", "seller": "甲供应商",
                 "goods": "原料A", "amount": 700000.0, "tax": 91000.0},
                {"inv_no": "INV002", "date": "2025-01-09", "seller": "甲供应商",
                 "goods": "原料B", "amount": 300000.0, "tax": 39000.0},
            ],
            "industry_basis": "制造业",
        }
    frs = []
    if with_book:
        frs.append({"type": "voucher", "_rows": [
            {"account": "6401", "account_name": "主营业务成本", "debit": book_total * 0.6,
             "credit": 0, "voucher_no": "记-1", "summary": "收到发票", "month_no": "1"},
            {"account": "6401", "account_name": "主营业务成本", "debit": book_total * 0.4,
             "credit": 0, "voucher_no": "记-2", "summary": "支付业务款", "month_no": "2"},
            {"account": "6401", "account_name": "主营业务成本", "debit": 0,
             "credit": book_total, "voucher_no": "记-9", "summary": "结转期间损益", "month_no": "12"},
        ]})
        frs.append({"type": "trial_balance", "_rows": [
            {"code": "6401", "name": "主营业务成本", "current_debit": book_total},
        ]})
    return {"engine_status": es, "file_results": frs}


class TestCostReconDetail(unittest.TestCase):

    def test_two_sided_breakdown(self):
        d = build_cost_recon_detail(_rd())
        self.assertTrue(d["available"])
        self.assertEqual(d["invoice_total"], 1000000.0)
        self.assertEqual(d["book_total"], 1010000.0)
        self.assertEqual(d["diff"], -10000.0)
        # 发票类目构成来自 core 拆分（单一权威）
        self.assertEqual(len(d["by_goods"]), 2)
        self.assertEqual(len(d["by_supplier"]), 1)
        # 账面按凭证号归集；期末结转（借方 0）不计入
        self.assertEqual(len(d["by_voucher"]), 2)
        self.assertEqual(d["trial_balance_check"], 1010000.0)

    def test_emitted_within_threshold(self):
        """阈值内也必须照出（合规留痕）——此前只有超阈值才有内容。"""
        d = build_cost_recon_detail(_rd(inv_total=1000000.0, book_total=1010000.0))
        self.assertTrue(d["available"])
        self.assertEqual(d["status"], "两口径基本吻合")
        self.assertTrue(d["paragraphs"])

    def test_itemized_lists_present(self):
        """逐张/逐笔清单（导出附件）必须随明细一并产出。"""
        d = build_cost_recon_detail(_rd())
        self.assertEqual(len(d["invoice_rows"]), 2)
        self.assertEqual(d["invoice_rows"][0]["inv_no"], "INV001")
        self.assertEqual(d["invoice_rows"][0]["goods"], "原料A")
        # 逐笔：两笔借方；期末结转账面行（借方 0）不计
        self.assertEqual(len(d["book_rows"]), 2)
        self.assertEqual(d["book_rows"][0]["voucher_no"], "记-1")

    def test_attribution_present(self):
        d = build_cost_recon_detail(_rd())
        self.assertTrue(d["attribution"])
        for a in d["attribution"]:
            self.assertTrue(a.get("cause") and a.get("evidence"))

    def test_missing_data_is_declared(self):
        """两侧都没有 → available False 且 status=未取得，不得用默认值顶替。"""
        d = build_cost_recon_detail(_rd(with_inv=False, with_book=False))
        self.assertFalse(d["available"])
        self.assertEqual(d["status"], "未取得")

    def test_book_only(self):
        d = build_cost_recon_detail(_rd(with_inv=False, with_book=True))
        self.assertTrue(d["available"])
        self.assertEqual(d["status"], "发票口径未取得")

    def test_no_crash_on_empty(self):
        d = build_cost_recon_detail({})
        self.assertFalse(d["available"])
        self.assertEqual(d["paragraphs"], [])


if __name__ == "__main__":
    unittest.main()

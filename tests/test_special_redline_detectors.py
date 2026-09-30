"""特定/专项风险红线探测器单测：零误报 + 命中即产出 + 归属有效 + 打封印标。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.special_redline_detectors import run_special_redline_detection, SPECS
from engine import tax_redlines


class SpecialRedlineDetectorTests(unittest.TestCase):
    def test_empty_or_blank_data_produces_no_findings(self):
        """零数据必须零误报。"""
        self.assertEqual(run_special_redline_detection({}), [])
        self.assertEqual(run_special_redline_detection({"vouchers": [], "bank_txs": []}), [])
        self.assertEqual(
            run_special_redline_detection({"vouchers": [{"摘要": "正常业务", "金额": 1}]}),
            [],
        )

    def test_signals_produce_findings_with_valid_redline_id(self):
        data = {
            "vouchers": [{"摘要": "暂估入库 原材料", "科目": "原材料", "金额": 100}],
            "bank_txs": [{"摘要": "向非居民企业支付特许权使用费", "付款": 5000}],
            "balances": [{"科目名称": "其他应付款", "期末贷方": 80000}],
        }
        found = run_special_redline_detection(data)
        ids = {f["redline_id"] for f in found}
        self.assertIn("RL-COST-001", ids)
        self.assertIn("RL-SPT-006", ids)
        self.assertIn("RL-INC-004", ids)
        for f in found:
            self.assertIn(f["redline_id"], {s["redline_id"] for s in SPECS})
            self.assertTrue(f.get("_scenario_governed"), "必须打封印标否则被 seal 丢弃")
            self.assertIn("待核", f["type"])

    def test_declared_keyword_suppresses_false_positive(self):
        """已见对应税种申报记录 → 不再置疑。"""
        data = {
            "vouchers": [{"科目": "房屋建筑物", "金额": 1}],
            "tax_declarations": [{"税种": "房产税", "金额": 100}],
        }
        found = run_special_redline_detection(data)
        self.assertNotIn("RL-OTH-002", {f["redline_id"] for f in found})

    def test_forex_goods_import_not_false_positive(self):
        """进口付汇（美元）≠ 向非居民支付境内所得，不应误报源泉扣缴义务。"""
        data = {
            "bank_txs": [{"摘要": "境外支付货款 付汇 USD", "付款": 9000}],
            "pur_invs": [{"品名": "进口原材料", "价税合计": 9000}],
        }
        ids = {f["redline_id"] for f in run_special_redline_detection(data)}
        self.assertNotIn("RL-SPT-006", ids)

    def test_every_spec_declares_existing_redline(self):
        valid = {r["id"] for r in tax_redlines.REDLINES}
        self.assertTrue(SPECS, "SPECS 不应为空")
        for s in SPECS:
            self.assertIn(s["redline_id"], valid, f"{s['redline_id']} 不是有效红线 id")
            self.assertTrue(s.get("signals"), f"{s['redline_id']} 缺少 signals")
            self.assertTrue(s.get("needs"), f"{s['redline_id']} 缺少 needs(需补资料)")


if __name__ == "__main__":
    unittest.main()

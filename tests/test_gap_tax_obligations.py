"""小微税种/费义务探测器单测：零误报 + 命中产出 + 已申报抑制。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.gap_tax_obligations import run_gap_tax_obligation_detection as RUN, SPECS


class GapTaxObligationTests(unittest.TestCase):
    def test_empty_data_no_findings(self):
        self.assertEqual(RUN({}), [])
        self.assertEqual(RUN({"vouchers": [{"摘要": "正常采购", "金额": 1}]}), [])

    def test_ad_service_triggers_culture_fee(self):
        data = {"sal_invs": [{"goods": "广告服务费", "amount": 100000}]}
        found = RUN(data)
        taxes = {f["tax_type"] for f in found}
        self.assertIn("文化事业建设费", taxes)
        for f in found:
            self.assertTrue(f.get("_scenario_governed"), "必须打封印标")
            self.assertIn("待核", f["type"])

    def test_declared_keyword_suppresses(self):
        data = {
            "sal_invs": [{"goods": "广告服务费", "amount": 100000}],
            "tax_declarations": [{"税种": "文化事业建设费", "金额": 3000}],
        }
        self.assertNotIn("文化事业建设费",
                         {f["tax_type"] for f in RUN(data)})

    def test_all_specs_have_needs_and_signals(self):
        self.assertTrue(SPECS)
        for s in SPECS:
            self.assertTrue(s.get("signals"), f"{s.get('topic')} 缺 signals")
            self.assertTrue(s.get("needs"), f"{s.get('topic')} 缺 needs")


if __name__ == "__main__":
    unittest.main()

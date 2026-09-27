# -*- coding: utf-8 -*-
"""潜在税额影响测算（engine/tax_impact.py）回归测试。

铁律：取不到金额 → 未量化；绝不用默认值顶数。税率与假设须标注。
"""
import unittest

from engine.tax_impact import (
    estimate_tax, extract_amount, extract_amount_from_problem,
    build_tax_impact_summary,
)


class TestTaxImpact(unittest.TestCase):

    def test_estimate_by_tax(self):
        r = estimate_tax(1000000.0, ["增值税", "企业所得税"])
        d = {i["tax"]: i["amount"] for i in r["items"]}
        self.assertEqual(d["增值税"], 130000.0)
        self.assertEqual(d["企业所得税"], 250000.0)
        self.assertIn("城建税及教育费附加", d)          # 随增值税附征
        self.assertEqual(r["total"], 395600.0)
        self.assertIn("测算", r["note"])
        self.assertIn("不构成核定", r["note"])

    def test_untaxed_tax_type_skipped(self):
        r = estimate_tax(1000000.0, ["不存在的税种"])
        self.assertFalse(r["available"])
        self.assertIsNone(r["total"])

    def test_not_quantified_when_no_amount(self):
        r = estimate_tax(None, ["增值税"])
        self.assertFalse(r["available"])
        self.assertIn("未量化", r["note"])
        self.assertEqual(r["items"], [])

    def test_extract_only_anchored_amounts(self):
        self.assertEqual(extract_amount("涉及金额 1,234,567.89 元")["amount"], 1234567.89)
        self.assertEqual(extract_amount("两者差异 -182,749.81元")["amount"], 182749.81)
        # 无金额关键词 / 不是金额单位 → 不认（避免把毛利率、单价当敞口）
        self.assertIsNone(extract_amount("毛利率 16.5%（行业30%~65%）"))
        self.assertIsNone(extract_amount("涉及金额 50 元"))   # < 1000 元

    def test_extract_from_problem_scans_narrative(self):
        p = {"narrative_paragraphs": [
            {"text": "经检查，本企业触发税务风险指标。", "bullets": [], "tail": ""},
            {"text": "本项涉及金额 2,000,000.00 元。", "bullets": [], "tail": ""}]}
        self.assertEqual(extract_amount_from_problem(p)["amount"], 2000000.0)

    def test_summary(self):
        probs = [{"tax_impact": estimate_tax(1000000.0, ["增值税"])},
                 {"tax_impact": {"available": False}}]
        s = build_tax_impact_summary(probs)
        self.assertEqual(s["quantified"], 1)
        self.assertEqual(s["total_items"], 2)
        self.assertGreater(s["total"], 0)
        self.assertTrue(any(x["tax"] == "增值税" for x in s["by_tax"]))


if __name__ == "__main__":
    unittest.main()

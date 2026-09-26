# -*- coding: utf-8 -*-
"""「一、本轮检查总体结论」生成器（engine/overall_conclusion.py）回归测试。

测试的是**派生规则**，不针对任何具体企业写特例：
  · 数字（份数/项数/各等级计数）必须取实测 —— 增删一条发现即随之变化；
  · 点名清单必须来自 findings 的 title，不得写死；
  · 涉嫌方向只在真实 suspect 中出现时才列（数据驱动）；
  · 措辞：结论词用「风险事项」，不把已确认事实降格成"待核实"；不输出 Markdown 记号。
"""
import unittest

from engine.overall_conclusion import build_overall_conclusion


def _p(seq, title, level, taxes=None, suspect=None, grade="待核"):
    return {
        "seq": seq,
        "title": title,
        "risk_level": level,
        "taxes": taxes or [],
        "suspect": suspect or "",
        "conclusion_grade": grade,
    }


def _rd(problems, further=None, files=3, cats=2, te=None):
    return {
        "files_count": files,
        "file_results": [{"type": "t%d" % i} for i in range(cats)],
        "target_entity": te or {},
        "enterprise_readable_report": {
            "confirmed_problems": problems,
            "further_checks": further or [],
        },
    }


class TestOverallConclusionDerivation(unittest.TestCase):

    def test_counts_are_derived_from_findings(self):
        probs = [
            _p(1, "A", "高风险", ["增值税"]),
            _p(2, "B", "中风险", ["企业所得税"]),
            _p(3, "C", "中风险", ["企业所得税"]),
            _p(4, "D", "低风险", []),
        ]
        oc = build_overall_conclusion(_rd(probs, further=[{"seq": 5}]))
        self.assertEqual(oc["counts"]["total"], 4)
        self.assertEqual(oc["counts"]["further"], 1)
        self.assertEqual(oc["counts"]["by_level"]["高风险"], 1)
        self.assertEqual(oc["counts"]["by_level"]["中风险"], 2)
        self.assertEqual(oc["counts"]["by_level"]["低风险"], 1)
        # 税种计数
        tt = {t["name"]: t["count"] for t in oc["tax_types"]}
        self.assertEqual(tt.get("企业所得税"), 2)
        self.assertEqual(tt.get("增值税"), 1)

    def test_counts_follow_data_when_findings_change(self):
        """增删一条发现，数字与点名清单必须随之变化（证明非写死模板）。"""
        base = [_p(1, "甲", "高风险"), _p(2, "乙", "中风险")]
        oc1 = build_overall_conclusion(_rd(base))
        oc2 = build_overall_conclusion(_rd(base + [_p(3, "丙", "中风险")]))
        self.assertEqual(oc1["counts"]["total"], 2)
        self.assertEqual(oc2["counts"]["total"], 3)
        joined1 = "".join(oc1["paragraphs"])
        joined2 = "".join(oc2["paragraphs"])
        self.assertNotIn("丙", joined1)
        self.assertIn("丙", joined2)

    def test_tier_items_come_from_titles(self):
        probs = [_p(1, "红字冲销与作废发票比例异常：细节", "高风险"),
                 _p(2, "工资表人数与社保参保人数不符", "中风险")]
        oc = build_overall_conclusion(_rd(probs))
        tiers = {t["level"]: t for t in oc["tiers"]}
        # 点名用主标题（去掉「：」后的说明）
        self.assertIn("红字冲销与作废发票比例异常", tiers["高风险"]["items"])
        self.assertNotIn("红字冲销与作废发票比例异常：细节", tiers["高风险"]["items"])

    def test_directions_are_data_driven(self):
        probs = [_p(1, "A", "高风险", suspect="涉嫌隐匿收入、虚开发票")]
        oc = build_overall_conclusion(_rd(probs))
        self.assertIn("隐匿收入", oc["directions"])
        self.assertIn("虚开发票", oc["directions"])
        # 未出现的方向不得凭空列出
        self.assertNotIn("转移利润", oc["directions"])

    def test_no_markdown_and_no_zero_downdraft(self):
        probs = [_p(1, "A", "高风险"), _p(2, "B", "中风险")]
        oc = build_overall_conclusion(_rd(probs))
        joined = "".join(oc["paragraphs"])
        self.assertNotIn("**", joined)
        # verified==0 时不得出现"已核定 0 项"这种从 0 起步的说法
        self.assertNotIn("已核定 0 项", joined)
        # 结论词用"风险事项"，不把已确认事实降格为"待核实事项"
        self.assertIn("风险事项", joined)
        self.assertNotIn("待核实事项", joined)

    def test_conflict_between_registered_and_invoice_is_surfaced(self):
        te = {
            "industry": "广告传媒",
            "_industry_source": "销项发票品名推断",
            "_industry_confidence": "高",
            "industry_registered": "商贸",
            "_industry_candidates": {"工商登记": "商贸", "销项发票品名推断": "广告传媒"},
        }
        oc = build_overall_conclusion(_rd([_p(1, "A", "中风险")], te=te))
        self.assertTrue(oc["conflict"])
        self.assertIn("广告传媒", oc["conflict"])
        self.assertIn("商贸", oc["conflict"])
        self.assertIn("广告传媒", "".join(oc["paragraphs"]))

    def test_empty_findings_is_safe(self):
        oc = build_overall_conclusion(_rd([]))
        self.assertEqual(oc["counts"]["total"], 0)
        self.assertTrue(oc["paragraphs"])  # 至少仍有编制声明
        self.assertNotIn("None", "".join(oc["paragraphs"]))


if __name__ == "__main__":
    unittest.main()

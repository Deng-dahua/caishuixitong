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


class TestEditorialStandard(unittest.TestCase):
    """用户 2026-09-26 复核意见 → 固化为编辑标准（防回退）。"""

    def _oc(self):
        probs = [_p(1, "甲", "高风险", ["增值税", "企业所得税"]),
                 _p(2, "乙", "中风险", ["增值税"]),
                 _p(3, "丙", "待核验", ["印花税"], suspect="涉嫌隐匿收入"),
                 _p(4, "丁", "低风险", [])]
        te = {"industry": "广告传媒", "_industry_source": "销项发票品名推断",
              "industry_registered": "商贸",
              "_industry_candidates": {"工商登记": "商贸", "销项发票品名推断": "广告传媒"}}
        return build_overall_conclusion(_rd(probs, te=te))

    def test_industry_is_measure_basis_with_fact_and_view(self):
        """★ 2026-09-27 用户口径：总述只给"检查分析的事实 + 由此提出的观点"，
        不再写"待核实"式免责语，也不写"见某章/本章不展开"式引导。"""
        j = "".join(self._oc()["paragraphs"])
        self.assertIn("按销项发票品名指向", j)
        self.assertIn("来源：", j)                 # 事实：口径 + 来源
        self.assertIn("不一致", j)                 # 观点：两口径不一致
        self.assertNotIn("待核实", j)
        self.assertNotIn("本章不展开", j)
        self.assertNotIn("按「广告传媒」认定", j)

    def test_no_heavy_qualifier_wording(self):
        oc = self._oc()
        j = "".join(oc["paragraphs"]) + oc["conflict"]
        self.assertNotIn("变名开票", j)
        self.assertIn("开票品名与实际经营是否一致", j)

    def test_pending_verify_is_status_not_level(self):
        j = "".join(self._oc()["paragraphs"])
        self.assertIn("不参与风险等级排序", j)
        self.assertIn("风险等级按", j)              # 分级依据必须写明

    def test_tax_stats_labeled_as_relation_count(self):
        self.assertIn("事项—税种关联次数", "".join(self._oc()["paragraphs"]))

    def test_directions_are_softened(self):
        j = "".join(self._oc()["paragraphs"])
        # ★ 2026-09-27 用户口径："涉嫌"已含待核实，不再写"（待核实）"
        self.assertIn("可能涉及的涉嫌方向", j)
        self.assertNotIn("涉嫌方向（待核实）", j)
        self.assertNotIn("已指向的", j)

    def test_items_are_pending_risk_items_with_disclaimer(self):
        j = "".join(self._oc()["paragraphs"])
        # ★ 2026-09-27 用户口径：用「涉嫌风险事项」，"涉嫌"本身即含待核实
        self.assertIn("涉嫌风险事项", j)
        self.assertIn("尚不构成违法定性", j)
        self.assertNotIn("共确认", j)
        self.assertNotIn("待核实风险事项", j)


    def test_no_markdown_asterisks_in_any_paragraph(self):
        """纯文本段落不得含 Markdown 记号（曾漏出 `**加粗**` 的星号）。"""
        self.assertNotIn("*", "".join(self._oc()["paragraphs"]))


class TestChapterNoDuplication(unittest.TestCase):
    """★ 2026-09-27：单章内部**同一事实只说一遍**（防回退成"摘要+详情"两段拼接）。

    用户两次驳回的正是"同类事实章内说两三遍"（份数/类数、各等级项数、类型分布、
    税种、行业口径）。此处把"不重复"固化为**可执行不变式**，改坏即红。
    """

    def _oc(self):
        probs = [
            _p(1, "红字冲销与作废发票比例异常", "高风险", ["增值税", "企业所得税"]),
            _p(2, "个人账户收取经营性款项", "高风险", ["增值税"]),
            _p(3, "资金回流", "高风险", ["企业所得税"]),
            _p(4, "工资表人数与社保参保人数不符", "中风险", ["个人所得税"]),
            _p(5, "数字特征异常", "中风险", ["企业所得税"]),
            _p(6, "有进无销", "待核验", [], suspect="涉嫌隐匿收入"),
            _p(7, "固定资产取得、投用与折旧不匹配", "低风险", []),
        ]
        return build_overall_conclusion(_rd(probs, further=[{"seq": 8}]))

    def test_total_count_stated_once(self):
        j = "".join(self._oc()["paragraphs"])
        self.assertEqual(j.count("识别并列示"), 1,
                         "事项总数只应在「检查范围与结果概览」出现一次")

    def test_risk_total_not_standalone(self):
        P = self._oc()["paragraphs"]
        standalone = [p for p in P if p.startswith("本轮识别并列示")]
        self.assertEqual(standalone, [], "「风险总量」应并入概览，不得再单列一段")

    def test_each_level_count_heading_once(self):
        P = self._oc()["paragraphs"]
        for lvl in ("高风险", "中风险", "低风险"):
            heads = [p for p in P if p.startswith(lvl + " ") and "项：" in p]
            self.assertEqual(len(heads), 1,
                             "%s 清单标题应只出现一次（各级项数不得重复报）" % lvl)

    def test_no_bare_pending_phrase(self):
        j = "".join(self._oc()["paragraphs"])
        self.assertNotIn("待核实事项", j)
        self.assertNotIn("待核实风险事项", j)   # ★ 2026-09-27 改用「涉嫌风险事项」
        self.assertIn("涉嫌风险事项", j)

    def test_section_markers_present(self):
        j = "".join(self._oc()["paragraphs"])
        for marker in ("检查范围与结果概览", "按风险性质归纳", "风险等级评定",
                       "企业整体风险综合评价", "对企业纳税遵从情况的总体看法",
                       "监管态度与后续处理建议"):
            self.assertIn(marker, j)
        # ★ 2026-09-27：边界声明已归第六章「报告性质和使用说明」，本章不再重复
        self.assertNotIn("边界声明", j)


if __name__ == "__main__":
    unittest.main()

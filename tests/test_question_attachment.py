# -*- coding: utf-8 -*-
"""契约：风险检查询问必须挂到对应疑点；资料缺口不得在询问清单里重复（2026-10-06）。

用户原话：
  「待企业澄清事项（其余事项）…这些内容为什么存在？又为什么会呈现在这里？
    难道不应该在分析出的疑点中呈现吗？而且这些内容是否在报告中已经重复了？」

诊断结论（两条根因 + 一条附带缺陷）：
  A **归属表漂移**：「进项，应转出未转出」被登记为"无对应疑点"，但 `input_voucher_report`
    自 2026-10-05 起已由 `STANDALONE_RISK_REPORTS` 立为独立风险事项
    「进项异常凭证：不得抵扣用途未作进项转出」（同一税额 3,996.91 元）
    ⇒ 同一风险在报告里出现两次。
  B **资料缺口两处各写一套**：`data_overview["missing"]` 生成的「资料·…」询问与
    `material_readiness` 逐项重复；且「资料·存货与余额表缺失」还在要求**服务型**企业补
    「期末存货盘点表、出入库台账」——正是 `material_readiness.not_applicable` 已判**不适用**的资料。
  C 原挂载逻辑**静默丢失**：命中归属表但本轮无匹配疑点时，既不挂载也不落 `unattached`。
"""
import unittest


class TestQuestionThemeAttachment(unittest.TestCase):

    def test_attached_when_target_problem_exists(self):
        """阳性：有归属且疑点存在 ⇒ 整条挂到该疑点，且不进残余清单。"""
        from engine.report_layout import attach_question_themes, QUESTION_THEME_TO_PROBLEM
        theme = "资金，未开票敞口"
        kw = QUESTION_THEME_TO_PROBLEM[theme]
        probs = [{"title": "银行收款大于申报收入：存在账外收入嫌疑", "seq": 3}]
        th = {"theme": theme, "severity": "高",
              "questions": [{"question": "请说明……", "basis": "b", "materials": ["m"]}]}
        n, un = attach_question_themes([th], probs)
        self.assertEqual(n, 1)
        self.assertEqual(un, [])
        self.assertEqual(probs[0]["questions"][0]["theme"], theme)

    def test_unattached_kept_when_no_mapping(self):
        """阴性A：无归属 ⇒ 必须原样留在残余清单（不得消失）。"""
        from engine.report_layout import attach_question_themes
        th = {"theme": "某个尚无归属的主题", "severity": "低", "questions": [{"question": "q"}]}
        n, un = attach_question_themes([th], [{"title": "任意疑点", "seq": 1}])
        self.assertEqual(n, 0)
        self.assertEqual(len(un), 1)
        self.assertIs(un[0], th)

    def test_not_silently_dropped_when_target_absent(self):
        """阴性B（原实现缺陷）：归属表命中、但本轮不存在该疑点 ⇒ 必须退回残余清单。

        旧实现走完 for 循环既不挂载也不 append ⇒ 这条询问在报告**任何地方都看不到**。
        """
        from engine.report_layout import attach_question_themes
        th = {"theme": "资金，未开票敞口", "severity": "高", "questions": [{"question": "q"}]}
        n, un = attach_question_themes([th], [{"title": "毫不相干的疑点", "seq": 9}])
        self.assertEqual(n, 0)
        self.assertEqual(len(un), 1, "找不到目标疑点时不得静默丢弃该询问")

    def test_input_voucher_theme_maps_to_standalone_problem(self):
        """「进项，应转出未转出」必须能挂上独立风险事项「进项异常凭证…」。

        事故复现路径：该风险事项**由 `_promote_standalone_reports` 在函数末尾产生**，
        而挂载必须发生在其**之后** —— 顺序错了归属表写对也不生效。
        """
        from engine.report_layout import (
            attach_question_themes, question_theme_target, STANDALONE_RISK_REPORTS,
        )
        kw = question_theme_target("进项，应转出未转出")
        self.assertTrue(kw, "该主题必须有归属（不得再落到报告末尾）")
        title = STANDALONE_RISK_REPORTS["input_voucher_report"]
        self.assertIn(kw, title, "归属关键词必须能在该独立风险事项标题中命中")
        probs = [{"title": title, "seq": 36}]
        n, un = attach_question_themes(
            [{"theme": "进项，应转出未转出", "severity": "中", "questions": [{"question": "q"}]}],
            probs)
        self.assertEqual((n, un), (1, []))

    def test_theme_normalization_handles_separator_and_parens(self):
        """主题分隔符（·/，）与括注必须归一（否则映射表按短名登记会失配）。"""
        from engine.report_layout import question_theme_target
        self.assertTrue(question_theme_target("进项·应转出未转出"))
        self.assertTrue(question_theme_target("进项，应转出未转出"))
        # 带括注的写法（实测主题常带补充说明）
        self.assertTrue(question_theme_target("进项，双向往来主体（未发现对开特征）"))

    def test_no_material_theme_in_question_catalog(self):
        """资料缺口不得进询问清单 —— 唯一权威是 `material_readiness`。"""
        from engine.report_layout import QUESTION_THEME_TO_PROBLEM
        bad = [k for k in QUESTION_THEME_TO_PROBLEM if str(k).strip().startswith("资料")]
        self.assertEqual(bad, [], "『资料』类主题应由 material_readiness 承载，不得登记为询问")


class TestInspectionQuestionsNoMaterialThemes(unittest.TestCase):
    """询问引擎**不再生成**资料类主题（否则与资料齐备性重复，且绕过业态剔除）。"""

    def test_material_gap_not_emitted_as_question(self):
        from engine.inspection_questions import run_inspection_questions
        out = run_inspection_questions(
            comprehensive={}, company_name="测试公司",
            data_overview={"missing": ["企业所得税申报表", "资产负债表", "合同文件"],
                           "present": ["增值税申报表"]},
            unconfirmed_findings=[])
        themes = [str(t.get("theme") or "") for t in (out.get("themes") or [])]
        self.assertFalse([t for t in themes if t.startswith("资料")],
                         f"资料缺口不得再由询问清单承载，实测仍生成：{themes}")


class TestFamilyAliasAnswersThemeAttachment(unittest.TestCase):
    """★ 2026-10-06 事故：**同族合并**把归属表指向的疑点并入族主事项，族主标题不同
    ⇒ 归属关键词匹配不上 ⇒ 5 条询问主题**全部退回残余章**，与风险事项重复呈现
    （实测：资金·私户收款性质 / 资金·关联闭环 / 进项·双向往来主体 /
      虚开·同额凑数 / 虚开·双向往来主体）。

    修法：`finding_families` 合并时登记 `_family_aliases`（族主标题 ∪ 被并入项标题），
    归属匹配改用「标题 ∪ 别名」。这样**归属表一行都不用改**，也不必为
    "合并后标题长什么样"写特例。
    """

    @staticmethod
    def _mk(seq, title, rname, amt, lv):
        return {"seq": seq, "title": title, "risk_level": lv, "taxes": ["增值税"],
                "redline_name": rname, "finding_type": rname,
                "tax_impact": {"total": amt}, "narrative_paragraphs": []}

    def test_merge_registers_aliases(self):
        from engine.finding_families import merge_families
        probs = [self._mk(1, "工资表人数与社保参保人数不符", "工资表列支人数与社保参保人数存在差异", 0, "高风险"),
                 self._mk(2, "公私混同发薪", "私户支付薪酬", 100000, "中风险")]
        merge_families(probs)
        leads = [p for p in probs if p.get("family_members")]
        self.assertTrue(leads, "用例未触发同族合并（用例无效）")
        lead = leads[0]
        self.assertTrue(lead.get("_family_aliases"), "未登记同族别名")
        self.assertIn("公私混同发薪", lead["_family_aliases"])

    def test_theme_attaches_via_alias(self):
        from engine.finding_families import merge_families
        from engine.report_layout import attach_question_themes
        probs = [self._mk(1, "工资表人数与社保参保人数不符", "工资表列支人数与社保参保人数存在差异", 0, "高风险"),
                 self._mk(2, "公私混同发薪", "私户支付薪酬", 100000, "中风险")]
        merge_families(probs)
        lead = [p for p in probs if p.get("family_members")][0]
        self.assertNotIn("公私混同发薪", str(lead.get("title") or ""),
                         "族主标题若已含关键词，则本用例验证不到别名机制")
        n, un = attach_question_themes(
            [{"theme": "资金·私户收款性质", "severity": "高", "questions": [{"question": "q"}]}],
            probs)
        self.assertEqual(n, 1, "询问主题未挂上（同族别名未参与归属匹配）")
        self.assertFalse(un)
        self.assertTrue(lead.get("questions"), "询问未挂到族主事项")

    def test_no_alias_means_no_match(self):
        """反向锁：**没有**别名时（族主标题不含关键词）必须如实退回 unattached，不得硬挂。"""
        from engine.report_layout import attach_question_themes
        probs = [{"seq": 1, "title": "完全无关的族主标题", "narrative_paragraphs": []}]
        n, un = attach_question_themes(
            [{"theme": "资金·私户收款性质", "severity": "高", "questions": [{"question": "q"}]}],
            probs)
        self.assertEqual(n, 0)
        self.assertEqual(len(un), 1)


if __name__ == "__main__":
    unittest.main()

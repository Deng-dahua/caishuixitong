# -*- coding: utf-8 -*-
"""GAP-22 行业模板与导出链一致性（2026-10-18）。

原差距：`report_template`（行业模板）只作用于"一键分析"链，**不作用于导出链** ——
行业适配在导出件里失效，而且**没有任何地方说明这件事**，用户从导出件里看不出
"行业适配到底生没生效"。

为什么不是"直接把模板接进导出链"：
  两套文档模型章节口径不同 ——
    · 一键分析报告 = 9 章（`report_template.BASE_SECTIONS`：报告定位/风险事项/…）
    · 导出文档模型 = 12 节（`report_views.SECTIONS`：cover/disclaimer/project/…）
  强行按 9 章名重排 12 节，等于**把章节名当键硬套**，必然错位。
所以按差距清单给的第二个选项落地：**如实声明**，并把行业适配信息照实列出。

判据：
  ① `build_document` 产物必带 `template_meta`（含 `applied` 与 `reason`）；
  ② 声明必须出现在**报告正文**（免责声明章），四种格式都能看到；
  ③ 行业匹配上 ⇒ 写出行业与模板重点；匹配不上 ⇒ 明说"按通用结构、不冒用别行业模板"；
  ④ 取不到模板信息 ⇒ 明说"不可得"，不留空。
"""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import report_service as RSVC                             # noqa: E402
from engine import report_template as RT                              # noqa: E402


class TemplateMetaTests(unittest.TestCase):
    def test_meta_shape_for_matched_industry(self):
        meta, decl = RSVC._industry_template_meta("制造业")
        self.assertEqual(meta["industry"], "制造业")
        self.assertTrue(meta["matched"], "制造业应有模板")
        self.assertFalse(meta["applied"], "导出链不重排章节 ⇒ applied 必须是 False（如实）")
        self.assertTrue(meta["reason"], "必须给出原因，不能只标 False")
        self.assertIn("12 节", meta["reason"])
        self.assertTrue(meta["emphasis"], "应列出该行业模板重点")
        self.assertTrue(meta["sections"], "应列出该模板的章节顺序（供对照）")

    def test_declaration_states_both_ends(self):
        """声明必须同时说明"本导出件怎么装配"和"行业模板在哪生效"。"""
        _, decl = RSVC._industry_template_meta("制造业")
        self.assertIn("行业模板口径", decl)
        self.assertIn("12 节", decl)
        self.assertIn("一键分析", decl)
        self.assertIn("制造业", decl)

    def test_unmatched_industry_says_general_not_borrowed(self):
        meta, decl = RSVC._industry_template_meta("某个不存在的行业XYZ")
        self.assertFalse(meta["matched"])
        self.assertIn("未匹配", decl)
        self.assertIn("通用结构", decl)
        self.assertIn("不冒用", decl)

    def test_empty_industry_is_honest(self):
        meta, decl = RSVC._industry_template_meta("")
        self.assertFalse(meta["matched"])
        self.assertIn("通用结构", decl)

    def test_failure_is_not_silent(self):
        """模板信息取不到 ⇒ 明说"不可得"（不得留空，也不得假装已应用）。"""
        import engine.report_template as RT2
        orig = RT2.template_of

        def _boom(*a, **k):
            raise RuntimeError("模板库坏了")
        RT2.template_of = _boom
        try:
            meta, decl = RSVC._industry_template_meta("制造业")
        finally:
            RT2.template_of = orig
        self.assertFalse(meta["applied"])
        self.assertIn("不可得", meta["reason"])
        self.assertIn("读取失败", decl)


class DocumentCarriesTemplateMetaTests(unittest.TestCase):
    def test_build_document_source_sets_it(self):
        src = open(os.path.join(ROOT, "engine", "report_service.py"),
                   encoding="utf-8").read()
        self.assertIn('"template_meta": _tpl_meta', src)
        self.assertIn('_tpl_meta, _tpl_decl = _industry_template_meta(', src)
        self.assertIn('ctx["template_declaration"] = _tpl_decl', src)

    def test_declaration_rendered_in_disclaimer_section(self):
        """声明必须挂进**免责声明章**（四种格式都渲染 blocks ⇒ 一处接入处处可见）。"""
        src = open(os.path.join(ROOT, "engine", "report_service.py"),
                   encoding="utf-8").read()
        i = src.find("def _sec_disclaimer")
        seg = src[i:i + 1400]
        self.assertIn("template_declaration", seg,
                      "声明未挂进免责声明章 ⇒ 导出件里看不到")
        self.assertIn("_block_note(", seg)

    def test_no_second_implementation(self):
        """`行业模板口径` 文案只许出现在唯一实现里。"""
        import glob
        hits = []
        for p in glob.glob(os.path.join(ROOT, "engine", "*.py")):
            s = open(p, encoding="utf-8", errors="ignore").read()
            if "行业模板口径" in s:
                hits.append(os.path.basename(p))
        self.assertEqual(sorted(hits), ["report_service.py"],
                         "文案出现第二处实现：%s" % hits)


class DeclaredInDisclaimerBehaviourTests(unittest.TestCase):
    """行为级：真的调 `_sec_disclaimer`，断言声明**出现在这一章的块里**。

    ★ 只查源码里有没有 `_block_note(` 是**假判据**（本轮反向验证抓出来的：
      把 `if decl:` 改成 `if False:` 仍然 11 passed）。
    """

    def _ctx(self, industry):
        meta, decl = RSVC._industry_template_meta(industry)
        return {
            "disclaimer": {
                "identity_line": "身份声明：本报告由系统自动生成。",
                "non_enforcement_note": "非执法文书", "security_level": "内部",
                "security_restriction": "限内部", "security_retention": "三年",
                "authorization": "授权说明",
            },
            "template_declaration": decl,
        }

    def test_declaration_block_present(self):
        blocks = RSVC._sec_disclaimer(self._ctx("制造业"))
        self.assertTrue(blocks, "免责声明章不得为空")
        texts = []
        for b in blocks:
            texts.append(str(b.get("text") or ""))
            for it in (b.get("items") or []):
                texts.append(str(it.get("v") or ""))
        joined = "\n".join(texts)
        self.assertIn("行业模板口径", joined,
                      "行业模板声明未出现在免责声明章正文 ⇒ 导出件里看不到")
        self.assertIn("12 节", joined)

    def test_no_declaration_when_absent(self):
        """没有声明时不制造噪音。"""
        ctx = self._ctx("制造业")
        ctx["template_declaration"] = ""
        blocks = RSVC._sec_disclaimer(ctx)
        joined = "\n".join(str(b.get("text") or "") for b in blocks)
        self.assertNotIn("行业模板口径", joined)


class TemplateModuleContractTests(unittest.TestCase):
    def test_base_sections_are_the_9_chapters(self):
        """模板侧口径仍是 9 章 —— 若哪天改成 12 节，本声明的措辞要一起改。"""
        self.assertEqual(len(RT.BASE_SECTIONS), 9)
        self.assertEqual(len(set(RT.BASE_SECTIONS)), 9, "章节名不得重复")

    def test_views_sections_are_the_12_sections(self):
        from engine import report_views as VIEWS
        self.assertEqual(len(VIEWS.SECTIONS), 12)

    def test_two_taxonomies_really_differ(self):
        """两套章节名不该有交集 —— 有交集说明有人开始"混用"，声明措辞会被误解。"""
        from engine import report_views as VIEWS
        overlap = set(RT.BASE_SECTIONS) & set(VIEWS.SECTION_CN.values())
        self.assertEqual(overlap, set(),
                         "两套章节名出现交集：%s（须重新审视 GAP-22 结论）" % overlap)


if __name__ == "__main__":
    unittest.main()

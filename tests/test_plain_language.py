"""大白话翻译层单测（engine/plain_language.py）。

★ 政策口径（用户 2026-09-27）：**行业专有名词保持原样、直接用**（虚开 / 增值税 /
  企业所得税 / 主营业务成本 / 销项发票 / 进项发票 / 勾稽 / 红字冲销 / 序时账 / 科目余额表 …），
  本层**只**改「系统/报告语言」与「通用公文/口语词」。

覆盖：
- 行业专有名词**原样保留**
- 系统/报告语言照常白话化（监管盲区/疑点/穿透/核查/须→需要/本项为→这项属于…）
- 长词优先（待核不误伤待核实；疑点信号不被拆成"可疑的地方信号"）
- 法规引用保护（《增值税暂行条例》等不被改动）
- 文件名保护（用户实际上传文件名不被翻译）
- 幂等性（已白话文本重复转换不产生二次伤害）
"""
from __future__ import annotations

import unittest

from engine.plain_language import to_plain


class PlainLanguageTests(unittest.TestCase):
    def test_industry_terms_kept_verbatim(self):
        """★ 用户口径：行业专有名词保持原样，直接使用（不改大白话）。"""
        for s in ("销项发票", "进项发票", "虚开", "增值税", "企业所得税",
                  "主营业务成本", "勾稽", "红字冲销", "序时账", "科目余额表",
                  "进项税额转出", "借贷不平", "资金回流", "增值税专用发票"):
            self.assertEqual(to_plain(s), s, s)
        line = "销项发票与进项发票勾稽不平衡，存在虚开、主营业务成本异常"
        self.assertEqual(to_plain(line), line)

    def test_system_language_still_plain(self):
        """系统/报告语言（非行业术语）仍要说人话。"""
        self.assertEqual(to_plain("监管盲区提示"), "看不到的死角提示")
        self.assertEqual(to_plain("核查"), "检查")
        self.assertEqual(to_plain("核验"), "核实")
        self.assertIn("顺藤摸瓜追查", to_plain("资金穿透"))
        # ★ "疑点"是稽查术语、也是报告条目名（疑点1/疑点2）→ 保留不改
        self.assertEqual(to_plain("存在疑点"), "存在疑点")
        self.assertEqual(to_plain("涉嫌疑点"), "涉嫌疑点")

    def test_long_word_priority_no_mangling(self):
        # "待核实"中的"待核"不得被二次替换
        self.assertEqual(to_plain("本项为待核实事项"), "这项属于待核实事项")
        self.assertEqual(to_plain("本项为待核事项"), "这项属于待核实事项")
        # "疑点信号"不得被拆成"可疑的地方信号"
        self.assertEqual(to_plain("确认疑点信号"), "确认可疑信号")

    def test_sentence_patterns(self):
        self.assertEqual(to_plain("异常偏低"), "明显偏低，不正常")
        self.assertEqual(to_plain("显著高于行业上限"), "明显高于行业上限")
        self.assertEqual(to_plain("须核验真实性"), "需要核实真实性")
        self.assertEqual(to_plain("不得仅凭占比判定"), "不能只凭占比判定")

    def test_legal_shield(self):
        text = "依据《中华人民共和国增值税暂行条例》第十九条及国家税务总局公告2011年第40号处理"
        self.assertEqual(to_plain(text), text)

    def test_idempotent(self):
        once = to_plain("本项为待核事项，须补充资料，销项偏低")
        twice = to_plain(once)
        self.assertEqual(once, twice)

    def test_numbers_preserved(self):
        out = to_plain("销项收入合计245,827.02元，毛利率13.3%")
        self.assertIn("245,827.02", out)
        self.assertIn("13.3%", out)

    def test_non_text_safe(self):
        self.assertEqual(to_plain(None), "")
        self.assertEqual(to_plain(""), "")
        self.assertEqual(to_plain(123), 123)


class WalkStringsInplaceTests(unittest.TestCase):
    """报告最终出口的遍历必须**迭代 + 去环**。

    回归背景：主流程最终出口原用**递归**遍历整份报告，遇到报告对象里的循环引用/
    深层嵌套会抛 `maximum recursion depth exceeded`，被 except 静默吞掉 →
    标点规范化与"说人话"替换**从未真正生效**（实测产出日志可见 "[标点规范化] 跳过"）。
    此处用行为断言锁死：含循环引用也能完成、替换生效、枚举键不被改。
    """

    def test_cycle_and_shared_subtree_safe(self):
        from engine.plain_language import walk_strings_inplace, to_plain_obj
        a = {"title": "本项为待核事项，须补充资料"}          # 系统语言 → 会被白话化
        b = {"parent": a, "detail": "监管盲区提示，核查疑点"}  # 系统语言
        a["child"] = b                 # a -> b -> a 形成循环引用
        root = {"a": a, "list": [b, a, {"note": "核验真实性"}], "level": "高风险"}
        walk_strings_inplace(root, lambda s, k: to_plain_obj(s, k))
        self.assertIn("这项属于待核实事项", a["title"])
        self.assertIn("看不到的死角", b["detail"])
        self.assertIn("检查", b["detail"])
        self.assertEqual(root["level"], "高风险")   # 枚举键不被替换

    def test_list_strings_replaced(self):
        from engine.plain_language import walk_strings_inplace, to_plain_obj
        root = {"items": ["核验", "监管盲区"]}
        walk_strings_inplace(root, lambda s, k: to_plain_obj(s, k))
        self.assertEqual(root["items"][0], "核实")
        self.assertEqual(root["items"][1], "看不到的死角")

    def test_industry_terms_not_touched_by_walk(self):
        """整报告遍历时，行业专有名词同样保持原样。"""
        from engine.plain_language import walk_strings_inplace, to_plain_obj
        root = {"detail": "销项发票与进项发票勾稽不平衡，虚开、主营业务成本",
                "note": "须核查真实性"}
        walk_strings_inplace(root, lambda s, k: to_plain_obj(s, k))
        self.assertEqual(root["detail"], "销项发票与进项发票勾稽不平衡，虚开、主营业务成本")
        self.assertEqual(root["note"], "需要检查真实性")


class FilenameShieldTests(unittest.TestCase):
    """用户实际上传文件的名称不得被翻译（否则与真实文件对不上，"可自证来源"失效）。"""

    def test_filename_preserved(self):
        from engine.plain_language import to_plain
        for fn in ("2025年序时账.xlsx", "2025年科目余额表.xlsx",
                   "猩猩织光_北京_商贸有限公司_2026年1账期_进项发票列表.xlsx",
                   "AI账务系统银行1.xlsx"):
            self.assertEqual(to_plain(fn), fn, fn)

    def test_prose_still_plain_when_filename_present(self):
        from engine.plain_language import to_plain
        out = to_plain("2025年序时账.xlsx并核查疑点")
        self.assertIn("2025年序时账.xlsx", out)      # 文件名保留
        self.assertIn("检查", out)                    # 系统语言照常白话化
        self.assertIn("疑点", out)                    # 行业术语保留


class SkipKeyTests(unittest.TestCase):
    """键黑名单：前端枚举/ID 值不动；但 risk_level_basis 是**散文**，必须能白话化。"""

    def test_skip_key_rules(self):
        from engine.plain_language import _plain_skip_key
        for k in ("level", "verdict", "evidence_tier", "fact_id", "scene_fact_id",
                  "finding_type", "release_status", "risk_level"):
            self.assertTrue(_plain_skip_key(k), k)
        for k in ("risk_level_basis", "detail", "description", "suggestion", "source_docs"):
            self.assertFalse(_plain_skip_key(k), k)


if __name__ == "__main__":
    unittest.main()

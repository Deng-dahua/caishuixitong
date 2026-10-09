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
        # ★★ 2026-10-06 契约变更（**两次都踩同一个坑**）：
        #   第一次：通俗化把「待核/待核验」改写成 **「待核实」**——那正是用户禁用的词
        #           ⇒ 改为「尚需核实」。
        #   第二次（本次）：**「尚需核实」同样是禁用词**（用户："报告永远不能出现
        #           待核实/尚需核实"），而且这个 pass 跑在报告构建**之后**（`main` 末刻
        #           全量遍历）⇒ 构建器刚清洗干净，这里又把它变回禁用词
        #           （实测产物 210 处「尚需核实」，而构建器日志写着"已替换 208 处"）。
        #   ⇒ 通俗化层的**目标词必须落在禁用词之外**：统一用**行动指引**「须核对」。
        self.assertEqual(to_plain("本项为待核实事项"), "这项属于须核对事项")
        # ★ 2026-10-08（条款 B4 契约变更）：「待核事项」是**结论用语权威术语**
        #   （`config/conclusion_grades.json::term_authority` 四词之一），
        #   通俗化层**必须豁免**、不得改写为"须核对事项"（否则报告与权威术语表漂移）。
        self.assertEqual(to_plain("本项为待核事项"), "这项属于待核事项")
        # "疑点信号"不得被拆成"可疑的地方信号"
        self.assertEqual(to_plain("确认疑点信号"), "确认可疑信号")

    def test_plainifier_never_emits_forbidden_vague_words(self):
        """★ 不变量：通俗化层**不得产出任何禁用模糊词**（否则下游永远追不上它）。

        事故：本 pass 位于报告构建**之后**，若它产出的词在禁用表里，
        `enterprise_report` 末尾的清洗**已经跑完**，没人再兜得住。
        """
        from engine.plain_language import to_plain
        # ⚠ 「待核线索：」是**受保护的结构标识**（降级疑点身份）；
        #   「待核事项」是**结论用语权威术语**（条款 B4）⇒ 判据一律走唯一实现
        #   `vague_hits`（内部已豁免权威术语），不再裸扫词表（否则术语会被误判）。
        from engine.report_wording import vague_hits, _PROTECTED_PREFIXES
        samples = ["本项为待核实事项", "本项为待核事项", "本项为待核验事项",
                   "现状：待核实", "税负待核", "两者均为待核验事实"]
        for s in samples:
            out = to_plain(s)
            for p in _PROTECTED_PREFIXES:
                out = out.replace(p, "")
            bad = vague_hits(out)
            self.assertFalse(bad, "通俗化产出禁用词 %s：%r → %r" % (bad, s, out))

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
        # ★ 2026-10-08（条款 B4）：「待核事项」是权威术语 ⇒ 通俗化只改句式，不改术语本身。
        self.assertIn("这项属于待核事项", a["title"])
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

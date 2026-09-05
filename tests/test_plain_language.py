"""大白话翻译层单测（engine/plain_language.py）。

覆盖：
- 术语替换（销项/进项/勾稽/监管盲区/红冲/私户等高频词）
- 句式优化（须→需要、本项为→这项属于、异常偏低→明显偏低）
- 长词优先（待核不误伤待核实；疑点信号不被拆成"可疑的地方信号"）
- 法规引用保护（《增值税暂行条例》等不被改动）
- 幂等性（已白话文本重复转换不产生二次伤害）
"""
from __future__ import annotations

import unittest

from engine.plain_language import to_plain


class PlainLanguageTests(unittest.TestCase):
    def test_core_terms(self):
        self.assertEqual(to_plain("销项收入合计100元"), "开票收入合计100元")
        self.assertEqual(to_plain("进项发票缺失"), "收进来的进货发票缺失")
        self.assertEqual(to_plain("账表勾稽比对"), "账表互相对账核对比对")

    def test_blind_spot_and_funds(self):
        self.assertEqual(to_plain("监管盲区提示"), "税务看不到的死角提示")
        self.assertIn("个人银行账户", to_plain("私户支付"))
        self.assertIn("公司银行账户", to_plain("对公账户代发"))

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


if __name__ == "__main__":
    unittest.main()

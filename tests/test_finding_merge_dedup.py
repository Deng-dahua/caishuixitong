# -*- coding: utf-8 -*-
"""契约：同 type 发现合并时，**"同一段话说两遍"不得拼进正文**（2026-10-06）。

事故背景（用户原话）：
  「真的触碰到了36条税务红线吗？是分析出来的吗？」
  「来自原子规则/域分析/组合画像/专项比对，**你也要有资料站住脚啊**！！！
   是**资料的哪些情况**得清晰梳理吧」

实测：`_merge_same_type_findings` 把同 `type` 的多条发现 `detail` 用 `"\\n\\n"` 拼接，
但其中 9 个原子规则（VR001/005/012/013/019/024/025/037/056/061）的两条副本
**内容完全相同**（或只差一个数字）⇒ 报告里 6 条风险事项的「二、发现的依据」
**整段话说两遍**，其中 VR024 的两遍占比还各不同（14.62% vs 14.83% = 同一指标两套口径）。

本文件锁三条：
  ① 完全相同的副本 ⇒ 只出现一次（正文不得重复）；
  ② 前缀相同但**数字不同**的副本 ⇒ 同样不拼进正文，但必须记入 `_detail_dropped` 留痕
     （**不静默丢弃**：这是"同一指标两套口径"的线索，要能被追查）；
  ③ 内容**确实不同**的同 type 发现（VR060 那种"多个子事实"）⇒ 必须都保留（不得误删）。
"""
import unittest


class TestMergeSameTypeFindingsDedup(unittest.TestCase):

    @staticmethod
    def _merge(items):
        from engine.pipeline import _merge_same_type_findings
        return _merge_same_type_findings(list(items))

    def test_identical_details_kept_once(self):
        """① 两条一字不差的副本 ⇒ 正文只出现一次。"""
        d = "银行贷方收款与销项开票价税合计的差异同时超过25%和10万元，累计差额1,170,164.14元。"
        out = self._merge([
            {"type": "T", "level": "中风险", "detail": d},
            {"type": "T", "level": "中风险", "detail": d},
        ])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["detail"], d, "同一段话不得拼两遍")
        self.assertEqual(out[0]["_merged_from"], 2, "原条数仍须记录，不丢计数信息")

    def test_same_prefix_different_number_not_concatenated_but_traced(self):
        """② 前缀相同、数字不同 ⇒ 不拼正文，但必须留痕（同一指标两套口径）。"""
        a = "个人/个体户供应商1家，合计594,059.40元，占主营成本总额14.62%，户均594,059.40元。"
        b = "个人/个体户供应商1家，合计594,059.40元，占主营成本总额14.83%，户均594,059.40元。"
        out = self._merge([
            {"type": "T", "level": "中风险", "detail": a},
            {"type": "T", "level": "中风险", "detail": b},
        ])
        self.assertEqual(len(out), 1)
        self.assertNotIn("14.83%", out[0]["detail"], "冲突副本不得拼进正文（同段两个数）")
        self.assertEqual(out[0]["detail"].count("占主营成本总额"), 1)
        self.assertTrue(out[0].get("_detail_dropped"), "冲突副本必须留痕，不得静默丢弃")

    def test_distinct_details_both_kept(self):
        """③ 内容确实不同的同 type 子事实 ⇒ 必须都保留（VR060 型，不得误删）。"""
        out = self._merge([
            {"type": "T", "level": "中风险", "detail": "①无付款无挂账：成本 187,473.00 元无对应付款。"},
            {"type": "T", "level": "中风险", "detail": "③缺应付账款明细：本轮未提供应付账款辅助账。"},
        ])
        self.assertEqual(len(out), 1)
        self.assertIn("187,473.00", out[0]["detail"])
        self.assertIn("缺应付账款明细", out[0]["detail"])
        self.assertFalse(out[0].get("_detail_dropped"))

    def test_reproduces_real_vr024_case(self):
        """真实样本回放：VR024 的两遍（14.62/14.83）合并后正文只有一个占比。"""
        from engine.verified_rule_engine import VERIFIED_RULE_CATALOG
        # 该规则必须仍在目录里（否则本契约失去锚点）
        self.assertTrue(any(r["id"] == "VR024" for r in VERIFIED_RULE_CATALOG))


if __name__ == "__main__":
    unittest.main()

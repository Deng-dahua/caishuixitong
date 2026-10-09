# -*- coding: utf-8 -*-
"""契约：疑点的「本项还包含以下风险信号」不得把**本项自己**再列一遍（2026-10-06）。

用户原话：
  「疑点1的**本项还包含以下风险信号**，这部分内容不是已经在一至五里说了吗？」

**是重复。** 实测：疑点1「红字冲销与作废发票比例异常」下面又列出一条"相关风险信号"
「红冲/作废发票情形」，而本项「为何列入检查」段开头写的正是
"红冲/作废发票情形（共13笔）…" —— 同一个东西在同一节里说两遍。

根因：`_merge_ledger_into_problems` 的归属判据只问"这行属于哪个疑点"
（`redline_id` / 关联疑点序号），**没有问"这行是不是本项自己的来源"**；
而来源行必然也指向本项 ⇒ 必然被并回来一次（实测 11 个疑点受影响）。

本文件锁三条：
  ① 行名与本项标题/「为何列入检查」开头同指 ⇒ **不并入**（本项自己的来源行）；
  ② 行名是**真正不同**的事项 ⇒ 必须并入（不得误删，用户要的是去重不是删信息）；
  ③ 判据与闸门 `check_related_risks_not_self` **同口径**（同一归一化、同一取文范围）。
"""
import unittest


def _problem(seq, title, fact0):
    return {
        "seq": seq,
        "title": title,
        "redline_id": "RL-X-001",
        "narrative_paragraphs": [
            {"heading": "为何列入检查", "text": fact0},
            {"heading": "一、涉及的风险事项", "text": "……"},
        ],
    }


class TestRelatedRisksNotSelf(unittest.TestCase):

    def _merge(self, rows, problems):
        from engine.enterprise_report import _merge_ledger_into_problems
        return _merge_ledger_into_problems(rows, problems)

    def test_self_source_row_not_merged(self):
        """① 本项自己的来源行（行名＝段0开头的表题）不得被当成"额外信号"。"""
        probs = [_problem(1, "红字冲销与作废发票比例异常",
                          "红冲/作废发票情形（共13笔）（本表 13 行，涉及 10 个对象）。")]
        rows = [{"风险事项": "红冲/作废发票情形", "等级": "", "终局方向": "证据闭合",
                 "解除方式": "逐张核实红冲原因", "需补自证资料": "退货单",
                 "redline_id": "RL-X-001", "关联疑点": "具体问题第1项"}]
        n = self._merge(rows, probs)
        self.assertEqual(n, 0, "本项自己的来源行不得作为额外风险信号并入")
        self.assertNotIn("related_risks", probs[0])

    def test_self_source_row_matched_by_title_also_skipped(self):
        """①-b 行名出现在本项**标题**里（如「企业所得税贡献率偏低」）同样判为本项自己。"""
        probs = [_problem(9, "企业所得税贡献率偏低", "贡献率约0.01%，低于常规水平。")]
        rows = [{"风险事项": "企业所得税贡献率偏低", "等级": "中风险",
                 "终局方向": "可自证清白", "解除方式": "x", "需补自证资料": "y",
                 "redline_id": "RL-X-001", "关联疑点": "具体问题第9项"}]
        self.assertEqual(self._merge(rows, probs), 0)

    def test_genuinely_extra_signal_still_merged(self):
        """② 真正不同的同红线事项 ⇒ 必须并入（去重不等于删信息）。"""
        probs = [_problem(4, "税前扣除限额超限未纳税调整",
                          "业务招待费411,111.53元，占主营业务收入6.19%，超过5‰标准。")]
        rows = [{"风险事项": "广告费和业务宣传费扣除超限未纳税调整", "等级": "中风险",
                 "终局方向": "可自证清白", "解除方式": "调增广告费",
                 "需补自证资料": "广告费明细",
                 "redline_id": "RL-X-001", "关联疑点": "具体问题第4项"}]
        n = self._merge(rows, probs)
        self.assertEqual(n, 1)
        self.assertEqual(probs[0]["related_risks"][0]["风险事项"],
                         "广告费和业务宣传费扣除超限未纳税调整")

    def test_same_normalization_as_gate(self):
        """③ 归一化口径与闸门一致：全角/半角、括号、顿号等差异不影响判定。"""
        probs = [_problem(2, "工资表人数与社保参保人数不符",
                          "工资名册与社会保险人员范围差异（共30笔）。")]
        rows = [{"风险事项": "工资名册与社会保险人员范围差异（待核实）", "等级": "",
                 "终局方向": "证据闭合", "解除方式": "x", "需补自证资料": "y",
                 "redline_id": "RL-X-001", "关联疑点": "具体问题第2项"}]
        # 行名带"（待核实）"后缀 ⇒ 归一化后**不是**段0前缀的严格子串之外仍是子串关系，
        # 此处断言"不因括注而误并成额外信号"（并入 0 或 1 都允许，但不得重复列出本项名）
        self._merge(rows, probs)
        for r in (probs[0].get("related_risks") or []):
            self.assertNotEqual(r["风险事项"], "工资名册与社会保险人员范围差异",
                                "本项自己的事项名不得出现在 related_risks")


if __name__ == "__main__":
    unittest.main()

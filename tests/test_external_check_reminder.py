# -*- coding: utf-8 -*-
"""外部数据核验待办项的口径回归（2026-10-02）。

背景（用户复核疑点5 实测的两处硬伤）：
  ① 明细表语义错位 —— 「需外部数据核验：关联交易的同期资料与关联申报（共8笔）」
     表下挂的是「全年最大额银行流水 + 0 元高频交易对方」，与"同期资料与关联申报"毫无关系。
     根因：这类发现的文案里必然出现"银行/供应商/客户"等词，被 pipeline 的
     _enrich_evidence_rows 通用关键词兜底按词抓行（**按词猜证据**）。
  ② 触红与「涉及第 无 条构成要件」正面冲突 —— argumentation 只看线索链终端信号就把
     外部核验项判成「已触碰税务违规红线（资料不足）」，而报告同项下一段写
     「经核对，本企业涉及上述第 无 条构成要件」。

本文件把两处口径锁死，且**都必须做反向验证**（破坏→必须变红）。
"""
import unittest

from engine.argumentation import (
    _VERDICT_EXTERNAL, build_argumentation, is_external_check_finding,
)
from engine.clue_chain import build_clue_chain
from engine.evidence_chain import build_evidence_chain
from engine.external_check_reminder import (
    _EXT_SAMPLE_BRANCH, build_external_check_reminders,
)
from engine.tax_redlines import get_redline


def _inv(direction, inv_no, goods, amount, opposite, date):
    if direction == "销项":
        return {"direction": "销项", "inv_no": inv_no, "发票号码": inv_no,
                "goods": goods, "amount": amount,
                "buyer": opposite, "销方名称": "本公司", "date": date}
    return {"direction": "进项", "inv_no": inv_no, "发票号码": inv_no,
            "goods": goods, "amount": amount,
            "seller": opposite, "销方名称": opposite, "date": date}


class TestExternalCheckFindingIdentity(unittest.TestCase):
    """外部核验项的识别口径（单一权威，pipeline/报告层都复用它）"""

    def test_category_and_type_prefix_are_both_recognized(self):
        a = is_external_check_finding({"category": "外部核验"})
        b = is_external_check_finding({"type": "需外部数据核验：供应商工商登记"})
        c = is_external_check_finding({"category": "外部核验", "type": "采购成本异常"})
        d = is_external_check_finding({"type": "采购成本异常"})
        self.assertTrue(a and b and c)
        self.assertFalse(d, "普通发现不得被判成外部核验项")

    def test_non_dict_is_not_external(self):
        self.assertFalse(is_external_check_finding(None))
        self.assertFalse(is_external_check_finding({"category": ""}))


class TestExternalCheckVerdict(unittest.TestCase):
    """外部核验项：有信号也不判触红，走独立裁决档"""

    def setUp(self):
        self.rl = get_redline("RL-CIT-001")
        self.finding = {
            "type": "需外部数据核验：关联交易的同期资料与关联申报",
            "category": "外部核验",
            "detail": "发现既为供应商又为客户的主体2家，存在关联交易迹象。",
            "level": "待核验",
            "redline_id": "RL-CIT-001",
        }
        clue = build_clue_chain(self.finding, self.rl)
        clue["terminal_signal"] = "既为供应商又为客户的主体2家"
        self.ev = build_evidence_chain(self.finding, self.rl,
                                       available_materials=["进项发票", "销项发票"])
        self.arg = build_argumentation(self.finding, self.rl, clue, self.ev)

    def test_verdict_is_the_external_tier(self):
        self.assertEqual(self.arg["verdict"], _VERDICT_EXTERNAL)
        self.assertFalse(self.arg["redline_hit"],
                         "外部数据未取得 ⇒ 要件无从核对 ⇒ 不得判触红")

    def test_claim_does_not_claim_redline_touch(self):
        """结论主张不得写成「触碰红线 + 红线 suspect 罪名」"""
        self.assertNotIn("触碰红线", self.arg["claim"])
        self.assertIn("外部数据", self.arg["claim"], "须写明结论取决于外部核验")
        self.assertNotIn("虚开发票", self.arg["claim"])

    def test_verdict_tail_says_not_self_determined(self):
        self.assertIn("不属于本轮能自行定论", self.arg["reasoning"])

    def test_confidence_not_floored_at_sixty(self):
        """触红项有 0.60 置信地板；外部核验项不是触红项，不得套地板"""
        self.assertLess(self.arg["confidence"], 0.60,
                        "外部核验项不得因'有信号'被顶到触红项的置信地板")

    def test_reverse_strip_category_falls_back_to_redline_hit(self):
        """反向验证：把外部核验声明摘掉 ⇒ 必须回到旧的触红口径（否则本测试是假的）"""
        f2 = dict(self.finding)
        f2.pop("category")
        f2["type"] = "关联交易异常"
        arg2 = build_argumentation(f2, self.rl,
                                   build_clue_chain(f2, self.rl), self.ev)
        self.assertTrue(arg2["redline_hit"], "摘掉外部核验声明后应恢复触红判定")
        self.assertNotEqual(arg2["verdict"], _VERDICT_EXTERNAL)


class TestExternalCheckEvidenceScope(unittest.TestCase):
    """外部核验项的证据行口径：由探测器声明采样分支，pipeline 只按分支取行"""

    def setUp(self):
        self.sal = [
            _inv("销项", "S1", "广告服务", 1000.0, "丙公司", "2025-03-01"),
            _inv("销项", "S2", "广告服务", 2000.0, "甲公司", "2025-04-01"),
        ]
        self.pur = [
            _inv("进项", "P1", "服务费", 500.0, "甲公司", "2025-02-01"),
            _inv("进项", "P2", "广告制作费", 900.0, "乙公司", "2025-05-01"),
        ]
        self.bank = [
            {"transaction_serial_no": "B1", "date": "2025-01-05", "summary": "货款",
             "debit": 300000.0, "credit": 0, "counterparty": "甲公司"},
            {"transaction_serial_no": "B2", "date": "2025-01-06", "summary": "备用金",
             "debit": 0, "credit": 200000.0, "counterparty": "张伟"},
        ]
        self.fs = build_external_check_reminders(
            self.sal, self.pur, self.bank, None, None, None)
        self.by_type = {f["type"]: f for f in self.fs}

    def test_related_party_declares_entity_branch(self):
        f = self.by_type["需外部数据核验：关联交易的同期资料与关联申报"]
        scope = f.get("evidence_scope") or {}
        self.assertEqual(scope.get("branch"), "entity_invoices")
        self.assertEqual(sorted(scope.get("entities") or []), ["甲公司"])

    def test_personal_payee_declares_personal_counterparty_branch(self):
        f = self.by_type["需外部数据核验：对私资金往来对象实名与性质"]
        scope = f.get("evidence_scope") or {}
        self.assertEqual(scope.get("branch"), "entity_bank_txs")
        self.assertEqual(scope.get("entities"), ["张伟"],
                         "只锁个人往来户，不是「金额最大的银行流水」")

    def test_supplier_declares_top_purchase_branch(self):
        top = _EXT_SAMPLE_BRANCH.get("ext_supplier_verify") or {}
        self.assertEqual(top.get("branch"), "top_pur_invoices")

    def test_reverse_drop_branch_declaration(self):
        """反向验证：分支声明被摘掉 ⇒ 外部核验项不应声明 evidence_scope"""
        from engine import external_check_reminder as ecr
        _orig = ecr._EXT_SAMPLE_BRANCH
        try:
            ecr._EXT_SAMPLE_BRANCH = {}
            fs = ecr.build_external_check_reminders(
                self.sal, self.pur, self.bank, None, None, None)
            self.assertFalse([f for f in fs if f.get("evidence_scope")],
                             "摘掉分支表后不应再有 evidence_scope 声明")
        finally:
            ecr._EXT_SAMPLE_BRANCH = _orig


class TestExternalCheckEvidenceRows(unittest.TestCase):
    """经过 pipeline 采样后，外部核验项的明细行必须语义对齐"""

    @classmethod
    def setUpClass(cls):
        from engine import pipeline
        sal = [
            _inv("销项", "S1", "广告服务", 1000.0, "丙公司", "2025-03-01"),
            _inv("销项", "S2", "广告服务", 2000.0, "甲公司", "2025-04-01"),
        ]
        pur = [
            _inv("进项", "P1", "服务费", 500.0, "甲公司", "2025-02-01"),
            _inv("进项", "P2", "广告制作费", 900.0, "乙公司", "2025-05-01"),
        ]
        bank = [
            {"transaction_serial_no": "B1", "date": "2025-01-05", "summary": "货款",
             "debit": 300000.0, "credit": 0, "counterparty": "甲公司"},
            {"transaction_serial_no": "B2", "date": "2025-01-06", "summary": "备用金",
             "debit": 0, "credit": 200000.0, "counterparty": "张伟"},
        ]
        cls.fs = build_external_check_reminders(sal, pur, bank, None, None, None)
        pipeline._enrich_evidence_rows(cls.fs, bank, sal + pur, [], [],
                                       company_name="本公司")

    def test_related_party_rows_are_only_that_entity(self):
        f = {x["type"]: x for x in self.fs}[
            "需外部数据核验：关联交易的同期资料与关联申报"]
        rows = f.get("evidence_rows") or []
        self.assertTrue(rows, "外部核验项也应有语义对齐的证据行")
        for r in rows:
            self.assertIn("发票", r["source"]),
            self.assertEqual(r["counterparty"], "甲公司",
                             "关联交易项只能挂既购又销主体的实际购销发票，"
                             "不得挂'最大额银行流水'或'0 元高频交易对方'")

    def test_no_bank_row_in_related_party_table(self):
        f = {x["type"]: x for x in self.fs}[
            "需外部数据核验：关联交易的同期资料与关联申报"]
        for r in (f.get("evidence_rows") or []):
            self.assertNotEqual(r["source"], "银行流水",
                                "同期资料核验表下不得出现银行流水行")

    def test_personal_row_is_the_personal_counterparty(self):
        f = {x["type"]: x for x in self.fs}[
            "需外部数据核验：对私资金往来对象实名与性质"]
        rows = f.get("evidence_rows") or []
        self.assertTrue(rows)
        for r in rows:
            self.assertEqual(r["counterparty"], "张伟")


class TestSampledTableScopeNote(unittest.TestCase):
    """抽样明细表不得自称「全量」"""

    def test_truncated_rows_use_sampled_wording(self):
        from engine.enterprise_report import _finding_detail_tables
        f = {"type": "需外部数据核验：关联交易的同期资料与关联申报",
             "evidence_rows_truncated": True,
             "evidence_rows_scope": "只取与本项结论真正相关的原始行，最多8笔",
             "evidence_rows": [
                 {"source": "销项发票", "ref_id": "S%d" % i, "ref_label": "广告服务",
                  "amount": 100.0, "counterparty": "甲公司", "date": "2025-03-01", "note": "销项"}
                 for i in range(3)]}
        t = (_finding_detail_tables(f) or [{}])[0]
        self.assertIn("抽样", t.get("title", ""), "截断的明细表标题须标「抽样」")
        self.assertIn("抽样", t.get("scope_note", ""),
                      "口径说明不得再自称「基础逐笔明细（全量）」")
        self.assertNotIn("（全量）", t.get("scope_note", ""))

    def test_uncapped_rows_keep_full_wording(self):
        from engine.enterprise_report import _finding_detail_tables
        f = {"type": "有工资无社保",
             "evidence_rows": [
                 {"source": "工资表", "ref_id": "A", "ref_label": "行政", "amount": 5000.0,
                  "counterparty": "", "date": "", "note": ""},
                 {"source": "工资表", "ref_id": "B", "ref_label": "财务", "amount": 5000.0,
                  "counterparty": "", "date": "", "note": ""}]}
        t = (_finding_detail_tables(f) or [{}])[0]
        self.assertIn("（全量）", t.get("scope_note", ""))


class TestConclusionAssertionConsistency(unittest.TestCase):
    """「四、本项结论及理由」的触红断言必须跟随「要件有没有被认定」（用户复核疑点5）。"""

    NAME = "关联交易异常：购销闭环与六员重叠"

    @staticmethod
    def _reasoning():
        from engine.argumentation import _VERDICT_HIT_PENDING
        return ("本企业触碰红线，即%s，涉嫌通过关联企业转移利润、虚开发票。"
                "判断本项是否成立，要看这几项标准是否同时满足：与本企业存在人员重叠的上下游企业。"
                "本轮从所报资料中直接核对到的事实是：既为供应商又为客户的主体2家。"
                "综合以上，本项结论是%s，判断可信度约56%%（中等）。这一项既不认定违法，也不予排除。"
                % (TestConclusionAssertionConsistency.NAME, _VERDICT_HIT_PENDING))

    def test_zero_participant_strips_touch_redline_opening(self):
        from engine.enterprise_report import sanitize_conclusion_assertion as f
        out = f(self._reasoning(), self.NAME, set())
        self.assertNotIn("本企业触碰红线，即", out)
        self.assertIn("未认定到任何一条构成要件", out)
        self.assertIn("不等于已触碰红线", out)

    def test_zero_participant_strips_touch_redline_tail(self):
        """只改首句不算修好：段尾「本项结论是<触红裁决>」同样要中性化。"""
        from engine.argumentation import _VERDICT_HIT_PENDING
        from engine.enterprise_report import sanitize_conclusion_assertion as f
        out = f(self._reasoning(), self.NAME, set())
        self.assertNotIn(_VERDICT_HIT_PENDING, out)

    def test_with_participant_keeps_touch_redline(self):
        from engine.argumentation import _VERDICT_HIT_PENDING
        from engine.enterprise_report import sanitize_conclusion_assertion as f
        out = f(self._reasoning(), self.NAME, {"1"})
        self.assertIn("本企业触碰红线，即", out)
        self.assertIn(_VERDICT_HIT_PENDING, out)

    def test_other_redline_opening_not_touched(self):
        from engine.enterprise_report import sanitize_conclusion_assertion as f
        out = f(self._reasoning(), "另一个疑点名", set())
        self.assertEqual(out, self._reasoning())

    def test_argument_body_survives(self):
        """改写只动首句/裁决句，原论证正文必须整段保留（不得只留一句套话）。"""
        from engine.enterprise_report import sanitize_conclusion_assertion as f
        out = f(self._reasoning(), self.NAME, set())
        self.assertIn("判断本项是否成立，要看这几项标准是否同时满足", out)
        self.assertIn("本轮从所报资料中直接核对到的事实是", out)

    def test_no_redline_name_mismatch_crash(self):
        from engine.enterprise_report import sanitize_conclusion_assertion as f
        self.assertIsInstance(f("", self.NAME, set()), str)
        self.assertIsInstance(f("本企业触碰红线，即", self.NAME, set()), str)


class TestTailAssertionNeutralization(unittest.TestCase):
    """段尾触红断言中性化（2026-10-02 第二轮）。

    第一轮只改掉了「本项结论是<触红裁决>」，段尾那句
    「已经触碰税务红线，但材料还不够齐全…」仍在 —— 同一段里
    「逐条要件尚未认定成立」＋「已经触碰税务红线」正面冲突，正是用户贴出来的那两句。
    """

    NAME = "关联交易异常：购销闭环与六员重叠"

    @staticmethod
    def _reasoning():
        from engine.argumentation import _VERDICT_HIT_PENDING, _TAIL_HIT_PENDING
        return ("本企业触碰红线「%s」，涉嫌通过关联企业转移利润。"
                "判断本项是否成立，要看这几项标准是否同时满足。"
                "综合以上，本项结论是%s，判断可信度约60%%（中等）。%s"
                % (TestTailAssertionNeutralization.NAME, _VERDICT_HIT_PENDING, _TAIL_HIT_PENDING))

    def test_tail_sentence_replaced(self):
        from engine.argumentation import _TAIL_HIT_ANCHOR, neutralize_assertion_when_no_constituent as f
        out = f(self._reasoning(), self.NAME)
        self.assertNotIn(_TAIL_HIT_ANCHOR, out, "段尾触红断言未中性化")
        self.assertNotIn("已触碰税务违规红线", out, "段中裁决未中性化")
        self.assertIn("暂不作出触碰红线的结论", out)
        self.assertIn("既不认定违法，也不予排除", out, "中性化后必须保留原承诺")

    def test_anchor_survives_upstream_plain_language(self):
        """★ 锚点容错：上游 to_plain 会把「补证」改写成「补充资料」。

        逐字比对 `_TAIL_HIT_PENDING` 常量会**静默失效**（实测报告里是
        「待补充资料后判断」，常量是「待补证后判断」→ 一次也没替换成功）。
        """
        from engine.argumentation import _TAIL_HIT_ANCHOR, neutralize_assertion_when_no_constituent as f
        broken = self._reasoning().replace("补证", "补充资料")
        self.assertNotEqual(broken, self._reasoning())
        out = f(broken, self.NAME)
        self.assertNotIn(_TAIL_HIT_ANCHOR, out, "上游改写后锚点失效，段尾触红断言逃逸")
        self.assertNotIn("已触碰税务违规红线", out)

    def test_idempotent(self):
        from engine.argumentation import neutralize_assertion_when_no_constituent as f
        once = f(self._reasoning(), self.NAME)
        self.assertEqual(f(once, self.NAME), once)

    def test_no_touch_opening_left_untouched(self):
        from engine.argumentation import neutralize_assertion_when_no_constituent as f
        other = ("本企业触碰红线，即另一个疑点名，涉嫌X。"
                 "综合以上，本项结论是已触碰税务违规红线（资料不足，待补充资料后判断）。")
        self.assertEqual(f(other, self.NAME), other, "非本红线的触红开场被误伤")

    def test_none_and_empty_safe(self):
        from engine.argumentation import neutralize_assertion_when_no_constituent as f
        self.assertEqual(f(None, self.NAME), "")
        self.assertEqual(f("", self.NAME), "")

    def test_redline_engine_wires_neutralizer(self):
        """接线断言：产出侧（`redline_engine` 落案卷时）必须真的调用净化。

        报告侧调用太晚 —— 那时文本已被 `plain_language.to_plain` 改写，锚点会失效。
        """
        import io
        import os
        import re
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "engine", "redline_engine.py")
        src = io.open(p, encoding="utf-8").read()
        self.assertIn("neutralize_assertion_when_no_constituent", src,
                      "产出侧未接净化：矛盾文本会原样进报告")
        # 判据必须取自唯一权威 constituent_checkpoint（不另立一份口径）
        self.assertIn("participating_indices", src,
                      "未用唯一权威 constituent_checkpoint 判定「要件是否认定」")
        self.assertIn("build_constituent_checkpoints", src)
        # 净化必须**有前置判据之后**才执行（不是无条件替换，也不是永不执行）
        _i = src.find('_arg["reasoning"] = _neu(')
        _j = src.find("participating_indices as _pind")
        self.assertTrue(0 <= _j < _i, "净化调用必须先取得参与认定结论")
        self.assertIn("if _cp == 0:", src, "净化未以「零要件认定」为条件（会误伤真触红项）")


if __name__ == "__main__":
    unittest.main()

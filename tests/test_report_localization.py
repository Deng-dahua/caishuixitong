# -*- coding: utf-8 -*-
"""报告「关键信息中文化、去英文」契约测试（2026-09-12）。

用户要求：一键分析报告突出具体问题、突出关键核心信息、不得出现英文表述。
本测试锁死三条渲染链的中文化行为，防止回退：

1. enterprise_report._humanize_observed —— 把引擎原始观测值
   （salary_person_count=6、province_breakdown={广东:{'count':29…}} 等）
   转为中文可读、剔除 JSON 碎片、相邻重复去重。
2. enterprise_report._label_source / argumentation._zh_source —— 数据源标识
   （salaries/social_security/bank_txs 等 17 种）转中文，不得进入报告正文。
3. 未知 snake_case 键兜底：整键可译则译，不可译则连「键=」一并剔除，
   只保留数值，绝不残留英文单词。

铁律：数字、金额、百分比、公司名、法规名逐字保留，只改键名与噪音。
"""
from __future__ import annotations

import unittest

from engine.enterprise_report import (
    _humanize_observed,
    _label_source,
    _dedup_observed,
    _clue_narrative,
    _clue_table,
    _translate_key,
    _translate_metric_keys,
)
from engine.argumentation import _zh_source


class HumanizeObservedTests(unittest.TestCase):
    def test_core_person_metrics(self):
        self.assertEqual(
            _humanize_observed("salary_person_count=6，social_person_count=5，salary_only_count=1"),
            "工资表人数=6；社保参保人数=5；有工资无社保人数=1",
        )

    def test_cost_metrics(self):
        self.assertEqual(
            _humanize_observed("core_cost_total=3985048.28，unpaid_amount=372828.42，unpaid_ratio=0.0936"),
            "主营成本总额=3985048.28；未匹配付款金额=372828.42；未付款占比=0.0936",
        )

    def test_json_fragment_stripped(self):
        # 姓名后的半角逗号、JSON 引号/大括号应被清理，键名中文化
        out = _humanize_observed(
            "matches=[{'name': '初永伟,', 'amount': 12345.67}, {'name': '李昭阳,', 'amount': 8900.0}]"
        )
        self.assertIn("初永伟", out)
        self.assertIn("李昭阳", out)
        self.assertIn("金额", out)
        self.assertNotIn("matches", out)
        self.assertNotIn("{", out)
        self.assertNotIn("'", out)

    def test_province_breakdown(self):
        out = _humanize_observed(
            "province_breakdown={'广东': {'count': 29, 'amount': 123}, '河南': {'count': 4, 'amount': 45}}"
        )
        self.assertIn("广东", out)
        self.assertIn("河南", out)
        self.assertNotIn("breakdown", out)
        self.assertNotIn("count", out)

    def test_financial_precise_keys(self):
        self.assertEqual(
            _humanize_observed("gross_margin_pct=7.2，purchase_sales_ratio=1.4"),
            "毛利率=7.2；购销比=1.4",
        )

    def test_generic_token_fallback(self):
        out = _humanize_observed("customer_top3_ratio=0.65，circular_supplier_count=4，fund_loop_amount=882300.5")
        self.assertNotIn("customer", out)
        self.assertNotIn("supplier", out)
        self.assertNotIn("fund", out)
        self.assertIn("0.65", out)
        self.assertIn("4", out)
        self.assertIn("882300.5", out)

    def test_unknown_key_dropped_keep_number(self):
        # 完全无法翻译的键，连「键=」一起剔除，只保留数值
        out = _humanize_observed("some_unknown_xyz=99，anotherkey=5")
        self.assertNotIn("unknown", out)
        self.assertNotIn("anotherkey", out)
        self.assertIn("99", out)
        self.assertIn("5", out)


class SourceLabelTests(unittest.TestCase):
    def test_known_sources(self):
        for en, zh in [
            ("salaries", "工资表"),
            ("social_security", "社保明细"),
            ("bank_txs", "银行流水"),
            ("pur_invs", "进项发票"),
            ("sal_invs", "销项发票"),
            ("vouchers", "记账凭证"),
            ("trial_balance", "科目余额表"),
            ("bom", "物料清单"),
        ]:
            self.assertEqual(_label_source(en), zh, f"{en} 未中文化")
            self.assertEqual(_zh_source(en), zh, f"{en} 论证链未中文化")

    def test_composite_source(self):
        self.assertEqual(_zh_source("salaries、social_security"), "工资表、社保明细")

    def test_unknown_source_passthrough(self):
        self.assertEqual(_label_source(""), "")
        self.assertEqual(_label_source("无"), "无")


class ClueRenderTests(unittest.TestCase):
    def _clue(self):
        return {
            "nodes": [
                {"step": 1, "source": "salaries", "action": "统计工资表人数", "observed": "salary_person_count=6"},
                {"step": 2, "source": "social_security", "action": "统计社保参保人数", "observed": "social_person_count=5"},
                {"step": 3, "source": "salaries", "action": "交叉比对",
                 "observed": "salary_person_count=6，social_person_count=5，salary_only_count=1"},
            ]
        }

    def test_narrative_has_no_english(self):
        out = _clue_narrative(self._clue())
        self.assertIn("工资表", out)
        self.assertIn("社保明细", out)
        self.assertNotIn("salaries", out)
        self.assertNotIn("social_security", out)

    def test_table_source_localized(self):
        t = _clue_table(self._clue())
        for row in t["rows"]:
            self.assertNotIn("salaries", row["使用资料"])
            self.assertNotIn("social_security", row["使用资料"])


class DedupTests(unittest.TestCase):
    def test_adjacent_dup_collapsed(self):
        out = _dedup_observed(["salary_person_count=6", "salary_person_count=6", "salary_person_count=7"])
        self.assertEqual(out, ["工资表人数=6", "同上", "工资表人数=7"])


class MetricKeyLocalizationTests(unittest.TestCase):
    """专项能力章节 metrics 键中文化（bank_flow/fund_loop 实测暴露的缺口）。

    背景：引擎产出规范 snake_case 键（corporate_receipt 等），但 _WORD_CN
    词表缺词元时会译出「corporate收款」这类半中半英键名进报告。
    """

    def test_bank_flow_keys_fully_localized(self):
        for en, zh in [
            ("flow_receipt", "流收款"), ("flow_pay", "流付款"),
            ("corporate_receipt", "对公收款"), ("personal_receipt", "个人收款"),
            ("third_party_receipt", "第三方收款"), ("nonsales_receipt", "非销售收款"),
            ("reported_income", "申报收入"), ("declared_side", "已申报口径"),
            ("declared_value", "已申报值"), ("uninvoiced_gap", "未开票缺口"),
            ("uninvoiced_gap_after_nonsales", "未开票缺口后非销售"),
            ("unmatched_corporate_receipt", "未匹配对公收款"),
        ]:
            got = _translate_key(en)
            self.assertEqual(got, zh, f"{en} 译错")
            self.assertFalse(
                any("a" <= c.lower() <= "z" for c in got),
                f"{en} 翻译后仍含英文：{got}",
            )

    def test_fund_loop_keys(self):
        for en in ["direct回流金额", "indirect回流金额", "direct回流parties", "related组"]:
            got = _translate_key(en)
            self.assertFalse(
                any("a" <= c.lower() <= "z" for c in got),
                f"{en} 翻译后仍含英文：{got}",
            )

    def test_short_tokens_do_not_pollute_chinese(self):
        # 短词元（in/out/al/s/e）不得污染中文键（曾把 personal 打成「个人al」）
        for k in ["进合计", "销合计", "进出率", "前三大客户占比", "银行流水收款", "流收款"]:
            self.assertEqual(_translate_key(k), k, f"{k} 被误改")

    def test_null_metric_dropped(self):
        # None/空串指标无信息量，剔除而非渲染成 "null"
        out = _translate_metric_keys({"申报收入": None, "销项": 100, "空串": "", "零": 0})
        self.assertNotIn("申报收入", out)
        self.assertNotIn("空串", out)
        self.assertEqual(out["销项"], 100)
        self.assertEqual(out["零"], 0)

    def test_metric_key_localized_recursively(self):
        out = _translate_metric_keys({"corporate_receipt": 1, "rows": [{"declared_side": "x"}]})
        self.assertIn("对公收款", out)
        # 嵌套 dict 的键同样中文化（rows 键自身也译作「行」）
        nested = out.get("行") or out.get("rows")
        self.assertIsNotNone(nested, f"未找到嵌套列表，实际键：{list(out)}")
        self.assertIn("已申报口径", nested[0])


class TestNaturalizeReportText(unittest.TestCase):
    """报告正文自然化契约（2026-09-12 用户要求）：

    给企业看的报告不出现【主张】【线索】【依据】等内部字段标记，
    也不出现 RL-PAY-001 这类红线编号，一律自然表述。
    """

    def test_internal_field_tags_removed(self):
        from engine.enterprise_report import _naturalize_report_text
        cases = [
            "【主张】本企业触碰红线。",
            "【线索】从工资表读到人数。",
            "【依据】构成要件是……",
            "【证据】已有3项。",
            "【反证】企业可申辩。",
            "【裁决】本项成立。",
            "【线索链】怎么发现的。",
            "【证据链】要什么证据。",
        ]
        for c in cases:
            got = _naturalize_report_text(c)
            self.assertNotIn("【", got, f"未净化：{c} → {got}")
            self.assertNotIn("】", got, f"未净化：{c} → {got}")

    def test_redline_id_stripped_from_text(self):
        from engine.enterprise_report import _naturalize_report_text
        got = _naturalize_report_text("RL-PAY-001 工资表人数与社保参保人数不符")
        self.assertNotRegex(got, r"RL-[A-Z]+-\d+")
        self.assertIn("工资表人数与社保参保人数不符", got)

    def test_inline_redline_id_in_sentence_stripped(self):
        from engine.enterprise_report import _naturalize_report_text
        got = _naturalize_report_text(
            "经检查，本企业触碰税务红线 RL-PTY-001「采购成本无对公付款资金证据」，涉嫌虚列成本。"
        )
        self.assertNotRegex(got, r"RL-[A-Z]+-\d+")
        # 不得出现「税务红线红线」这类叠加重复
        self.assertNotIn("税务红线红线", got)
        self.assertIn("触碰税务红线「采购成本无对公付款资金证据」", got)

    def test_redline_name_without_id_preserved(self):
        from engine.enterprise_report import _naturalize_report_text
        # 标题形式（红线名本身不含编号）必须原样保留
        self.assertEqual(
            _naturalize_report_text("工资表人数与社保参保人数不符"),
            "工资表人数与社保参保人数不符",
        )

    def test_output_gate_neutralizes_whole_report(self):
        from engine.enterprise_report import _zh_normalize_obj
        rep = {
            "confirmed_problems": [{
                "title": "RL-PAY-001 工资表人数与社保参保人数不符",
                "narrative_paragraphs": [{"text": "【主张】本企业触碰红线 RL-PAY-001。"}],
            }],
        }
        out = _zh_normalize_obj(rep)
        blob = str(out)
        self.assertNotIn("【", blob)
        self.assertNotRegex(blob, r"RL-[A-Z]+-\d+")

    def test_numeric_thousand_separator_preserved(self):
        from engine.enterprise_report import _humanize_observed
        got = _humanize_observed("涉及金额7,747,329.31元")
        self.assertIn("7,747,329.31", got, f"千分位逗号被破坏：{got}")

    def test_source_alias_localized_no_empty_duns(self):
        from engine.enterprise_report import _humanize_observed
        got = _humanize_observed(
            "已读取资料：人员薪酬、voucher、salary、purchase_invoice、sales_invoice、social_security"
        )
        self.assertNotIn("、、", got, f"残留空顿号：{got}")
        for zh in ("记账凭证", "工资表", "进项发票", "销项发票", "社保明细"):
            self.assertIn(zh, got, f"{zh} 未译出：{got}")


if __name__ == "__main__":
    unittest.main()

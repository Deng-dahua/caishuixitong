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


if __name__ == "__main__":
    unittest.main()

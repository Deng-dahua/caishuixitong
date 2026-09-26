# -*- coding: utf-8 -*-
"""风险等级重排（按证据强度）回归测试 —— 2026-09-26 用户复核后决定。

背景：红线的风险等级原本由**其聚合的底层 finding 严重度**反推
（`tax_redlines.py` 本身无 level 字段），出现倒挂——
直接证据（资金回流/私户收款/银行收款>申报收入）被列中风险，
而结果指标（长期亏损仍持续经营）被列高风险。

原则（本测试锁死）：
  ① 只覆盖**已逐项论证**的红线，未登记的保持原逻辑（不得批量改等级）；
  ② 每条必须有**依据文本**（潜在税额/涉及金额/证据缺口/是否涉及虚开或偷税/补证紧迫性）；
  ③ 键用红线编号（稳定），不用显示名。
"""
import unittest

from engine.tax_redlines import RISK_LEVEL_BASIS, risk_level_basis


class TestRiskLevelRecalibration(unittest.TestCase):

    def test_direct_evidence_of_concealed_revenue_is_high(self):
        """隐匿收入的**直接证据** → 高风险。"""
        for rid in ("RL-FUND-002", "RL-INC-002", "RL-INC-001"):
            self.assertEqual(risk_level_basis(rid)["level"], "高风险", rid)

    def test_result_indicator_is_downgraded(self):
        """结果指标指向性弱于直接资金证据 → 由高风险下调为中风险。"""
        self.assertEqual(risk_level_basis("RL-CIT-004")["level"], "中风险")

    def test_single_indicator_is_mid(self):
        """单一指标（正常经营亦可能触发）→ 中风险，不列高风险。"""
        self.assertEqual(risk_level_basis("RL-VAT-006")["level"], "中风险")

    def test_every_entry_has_basis_text(self):
        """每条都必须写明依据，否则等于凭感觉调级。"""
        for rid, item in RISK_LEVEL_BASIS.items():
            self.assertTrue(item.get("level"), rid)
            self.assertTrue(item.get("basis"), "%s 缺少依据文本" % rid)
            self.assertGreaterEqual(len(item["basis"]), 20, "%s 依据过短" % rid)

    def test_not_registered_keeps_original_logic(self):
        """未登记的红线不得被改动（返回 None = 沿用原逻辑）。"""
        self.assertIsNone(risk_level_basis("RL-XXX-999"))
        self.assertIsNone(risk_level_basis(""))

    def test_scope_is_deliberately_narrow(self):
        """本轮只论证了 5 条；规模失控说明有人在批量调级（必须复核）。"""
        self.assertLessEqual(len(RISK_LEVEL_BASIS), 12)


if __name__ == "__main__":
    unittest.main()

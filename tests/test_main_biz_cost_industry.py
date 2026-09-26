# -*- coding: utf-8 -*-
"""主营业务成本识别 —— 行业口径回归测试（2026-09-26 用户指令）。

用户指令：**行业（由销项发票判定）应当定义"什么算该行业的成本性投入"**，
据此把进项发票区分为「主营业务成本」与「期间费用」；
**判不出来不得默认判成本**。
"""
import unittest

from engine.industry_resolver import core_inputs_for
from engine.main_biz_cost import (
    get_active_industry, identify_main_biz_cost, set_active_industry,
)


def _inv(goods, amount=1000.0):
    return {"goods": goods, "amount": amount}


class TestCoreInputsData(unittest.TestCase):
    """行业 → 核心投入：服务/流通类用显式表，制造/加工/贸易类用 product_chains。"""

    def test_service_industry_from_explicit_table(self):
        kws = core_inputs_for("广告传媒")
        self.assertIn("广告发布", kws)
        self.assertIn("媒体投放", kws)

    def test_manufacturing_industry_from_product_chains(self):
        kws = core_inputs_for("纺织制造")
        self.assertTrue(any(k in kws for k in ("纱", "棉", "坯布")))

    def test_invoice_category_name_tolerated(self):
        # 传发票分类名（"广告服务"）也应能取到该行业的核心投入
        self.assertTrue(core_inputs_for("广告服务"))

    def test_unknown_industry_returns_empty(self):
        self.assertEqual(core_inputs_for("绝无此行业XYZ"), [])
        self.assertEqual(core_inputs_for(""), [])


class TestIndustryAwareClassification(unittest.TestCase):

    def test_core_input_beats_generic_expense_keywords(self):
        """★ 广告公司的「广告发布/媒体投放」是主营成本，不得被通用费用表判成重大费用。"""
        r = identify_main_biz_cost([_inv("*广告服务*媒体投放", 100000)], [], industry="广告传媒")
        self.assertEqual(len(r["core_cost_invs"]), 1)
        self.assertEqual(len(r["major_expense_invs"]), 0)

    def test_daily_reimbursement_still_expense(self):
        r = identify_main_biz_cost([_inv("*餐饮服务*餐费", 200)], [], industry="广告传媒")
        self.assertEqual(len(r["minor_expense_invs"]), 1)
        self.assertEqual(len(r["core_cost_invs"]), 0)

    def test_unmatched_goes_pending_not_cost(self):
        """★ 有行业口径但判不出归属 → 待核，**不再默认判成本**。

        注意：需多张发票构成总采购额，否则单张必然满足「≥总采购额5%」而被判成本——
        该用例本身要检验的是"未命中任何依据"的项。
        """
        pur = [_inv("*甲材料*采购", 100000),
               _inv("*乙材料*采购", 50000),
               _inv("*其他*杂项未知", 1000)]
        r = identify_main_biz_cost(pur, [], industry="广告传媒")
        self.assertEqual(len(r["pending_cost_invs"]), 1)
        self.assertEqual(len(r["core_cost_invs"]), 2)
        self.assertIn("待核", r["core_cost_basis"]["*其他*杂项未知"])

    def test_no_industry_keeps_legacy_fallback_but_flagged(self):
        """无行业口径 → 保留旧兜底（归入成本），但必须如实标注为兜底（不再静默）。"""
        pur = [_inv("*甲材料*采购", 100000),
               _inv("*乙材料*采购", 50000),
               _inv("*其他*杂项未知", 1000)]
        r = identify_main_biz_cost(pur, [], industry="")
        self.assertEqual(len(r["pending_cost_invs"]), 0)
        self.assertEqual(len(r["core_cost_invs"]), 3)
        self.assertIn("兜底", r["core_cost_basis"]["*其他*杂项未知"])

    def test_basis_is_self_documenting(self):
        r = identify_main_biz_cost([_inv("*设计服务*平面设计", 50000)], [], industry="广告传媒")
        self.assertIn("行业核心投入", r["core_cost_basis"]["*设计服务*平面设计"])
        self.assertEqual(r["industry_basis"], "广告传媒")

    def test_empty_input_has_new_keys(self):
        r = identify_main_biz_cost([], [], industry="广告传媒")
        for k in ("core_cost_invs", "major_expense_invs", "minor_expense_invs",
                  "pending_cost_invs", "core_cost_basis", "industry_basis"):
            self.assertIn(k, r)


class TestActiveIndustryInjection(unittest.TestCase):
    """单一注入点：管道解析出行业后注入，调用点无需逐个透传。"""

    def setUp(self):
        self._old = get_active_industry()

    def tearDown(self):
        set_active_industry(self._old)

    def test_injection_applies_when_arg_absent(self):
        set_active_industry("广告传媒")
        r = identify_main_biz_cost([_inv("*广告服务*媒体投放", 100000)], [])
        self.assertEqual(len(r["core_cost_invs"]), 1)
        self.assertEqual(r["industry_basis"], "广告传媒")

    def test_explicit_arg_overrides_injection(self):
        set_active_industry("纺织制造")
        r = identify_main_biz_cost([_inv("*广告服务*媒体投放", 100000)], [], industry="广告传媒")
        self.assertEqual(r["industry_basis"], "广告传媒")


if __name__ == "__main__":
    unittest.main()

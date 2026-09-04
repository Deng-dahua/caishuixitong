# -*- coding: utf-8 -*-
"""TaxAuditAgent.perceive 进销品名匹配率回归测试。

核心场景（与 VR033 同源，第二对矛盾「服务费 vs 货物销售」）：
平台运营商开出的服务费发票（税码 3 开头 / 品名含『专业技术服务』等）本质非货物，
若计入进销品名匹配率，会把「货物采购 + 服务销售」算作 100% 不匹配，误触发
「进销品名不匹配 → 虚开」假设。perceive 必须把它们排除出 goods_match_ratio 计算。
"""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.agi_pipeline import TaxAuditAgent


def _ctx():
    """构造一个最小可用的 ctx（perceive 只用 company_profile / financial_snapshot + 若干 getattr）。"""
    return types.SimpleNamespace(
        company_profile={},
        financial_snapshot={},
    )


class TestPerceiveGoodsMatchServiceExclusion(unittest.TestCase):
    def test_service_sales_excluded_from_match_ratio(self):
        """货物销售(宠物食品) 命中 货物采购(宠物食品)，另有平台服务费销售 → 匹配率应为 1.0（满配），
        而非被服务费稀释成 0.5（误判进销品名背离）。"""
        agent = TaxAuditAgent()
        invoices = [
            {"goods": "宠物食品", "direction": "sales", "tax_code": "1030000000000000000"},
            # 平台技术服务费：税码 3 开头，属服务费，应剔除
            {"goods": "研发和技术服务*专业技术服务", "direction": "sales", "tax_code": "3040000000000000000"},
            {"goods": "宠物食品", "direction": "purchase", "tax_code": "1030000000000000000"},
        ]
        res = agent.perceive([], invoices, [], [], _ctx())
        self.assertEqual(res.get("goods_match_ratio"), 1.0)
        self.assertEqual(res.get("goods_mismatch_ratio"), 0.0)

    def test_real_goods_divergence_still_detected(self):
        """纯货物变名（销售 A、采购 B，无服务费发票）→ 匹配率 0.0，服务费剔除不掩盖真实背离。"""
        agent = TaxAuditAgent()
        invoices = [
            {"goods": "服装", "direction": "sales", "tax_code": "1030000000000000000"},
            {"goods": "五金配件", "direction": "purchase", "tax_code": "1030000000000000000"},
        ]
        res = agent.perceive([], invoices, [], [], _ctx())
        self.assertEqual(res.get("goods_match_ratio"), 0.0)
        self.assertEqual(res.get("goods_mismatch_ratio"), 1.0)

    def test_only_service_invoices_no_false_mismatch(self):
        """全部为服务费发票（无货物）→ 不应触发品名不匹配，匹配率回退 1.0。"""
        agent = TaxAuditAgent()
        invoices = [
            {"goods": "广告服务*服务费", "direction": "sales", "tax_code": "3060000000000000000"},
            {"goods": "研发和技术服务*技术服务费", "direction": "purchase", "tax_code": "3040000000000000000"},
        ]
        res = agent.perceive([], invoices, [], [], _ctx())
        self.assertEqual(res.get("goods_match_ratio"), 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

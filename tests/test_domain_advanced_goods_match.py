# -*- coding: utf-8 -*-
"""_domain_advanced_rules 规则3「购销品名匹配度检测」回归测试。

核心场景（与 VR033 / agi_pipeline.perceive 同源，第二对矛盾「服务费 vs 货物销售」）：
服务费发票（平台结算/纯服务业）本质非货物，若计入购销品名匹配度，会把「货物采购 + 服务销售」
算作品名无重叠、误触发「购销售商品种不匹配」——纯电商 B2C 经平台结算的正常模式被误判为虚开/进销脱节。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import domain_analysis as DA


def _adv(sal, pur):
    """以空 bank/salaries/社保/凭证/inventory 调用 _domain_advanced_rules，仅触发规则3。"""
    return DA._domain_advanced_rules([], sal, pur, [], [], [], None)


class TestDomainAdvancedGoodsMatchServiceExclusion(unittest.TestCase):
    def test_service_fee_sales_no_false_mismatch(self):
        """货物采购（宠物食品）+ 平台服务费销售（税码 3 开头）→ 不得误报「购销售商品种不匹配」。"""
        sal = [{"goods": "研发和技术服务*专业技术服务", "tax_code": "3040000000000000000"}]
        pur = [{"goods": "宠物食品*猫粮", "tax_code": "1030000000000000000"}]
        types = [f.get("type") for f in _adv(sal, pur)]
        self.assertNotIn("购销售商品种不匹配", types,
                         "服务费销售+货物采购是电商平台结算正常模式，不应误报品名不匹配")

    def test_goods_to_goods_divergence_still_fires(self):
        """纯货物变名（进五金、销服装，无重叠）→ 仍应触发「购销售商品种不匹配」。"""
        sal = [{"goods": "服装*上衣", "tax_code": "1030000000000000000"},
               {"goods": "服装*裤子", "tax_code": "1030000000000000000"}]
        pur = [{"goods": "五金*螺丝", "tax_code": "1030000000000000000"},
               {"goods": "五金*螺母", "tax_code": "1030000000000000000"}]
        types = [f.get("type") for f in _adv(sal, pur)]
        self.assertIn("购销售商品种不匹配", types, "货物→货物品名无重叠应正常触发品名不匹配")


if __name__ == "__main__":
    unittest.main(verbosity=2)

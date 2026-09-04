# -*- coding: utf-8 -*-
"""phase1 初查客户集中度回归测试：须剔除平台服务商（天猫/阿里妈妈），
避免把服务费发票购方误标为『前3大客户』、虚增 ctx.customer_concentration 并误触发『客户高度集中』。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import phase1_triage as PT


class _MockCtx:
    def __init__(self):
        self.customer_concentration = 0.0
        self.supplier_concentration = 0.0
        self.flags = []
        self.industry_profile = {}

    def add_flag(self, level, ftype, detail, stage):
        self.flags.append((level, ftype, detail, stage))


class TestPhase1CustomerConcentration(unittest.TestCase):
    def test_excludes_platform_operators(self):
        """平台运营商为最大购方时，集中度须基于真实客户计算（剔除平台）。"""
        ctx = _MockCtx()
        sal = [
            {"buyer": "浙江天猫技术有限公司", "amount": 254000.0},
            {"buyer": "杭州阿里妈妈软件服务有限公司", "amount": 187000.0},
            {"buyer": "真实客户A", "amount": 100000.0},
            {"buyer": "真实客户B", "amount": 80000.0},
            {"buyer": "真实客户C", "amount": 60000.0},
            {"buyer": "真实客户D", "amount": 40000.0},
        ]
        PT._detect_customer_concentration(ctx, sal)
        # 真实客户合计 280000；前3 = 240000 → 85.7%（若含平台则 541000/720000=75.1%，不触发）
        self.assertAlmostEqual(ctx.customer_concentration, 240000 / 280000 * 100, places=1,
            msg="前3真实客户占比应≈85.7%，而非含平台的75.1%")
        flag_types = [f[1] for f in ctx.flags]
        self.assertIn("客户高度集中", flag_types, "真实客户高度集中(85.7%>80%)应触发——证明平台已被剔除")

    def test_platform_only_no_false_concentration(self):
        """纯平台服务费销项：无真实客户，不得误报客户集中度。"""
        ctx = _MockCtx()
        sal = [
            {"buyer": "浙江天猫技术有限公司", "amount": 254000.0},
            {"buyer": "杭州阿里妈妈软件服务有限公司", "amount": 187000.0},
        ]
        PT._detect_customer_concentration(ctx, sal)
        self.assertEqual(ctx.customer_concentration, 0.0, "纯平台销项无真实客户，集中度应为0")
        self.assertEqual(len(ctx.flags), 0, "不得误触发『客户高度集中』")


if __name__ == "__main__":
    unittest.main(verbosity=2)

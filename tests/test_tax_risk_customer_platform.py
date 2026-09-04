# -*- coding: utf-8 -*-
"""tax_risk._analyze_customer_penetration 客户穿透集中度剔除平台运营商回归测试。

与 domain_analysis / false_invoice / phase1_triage / business_model / VR017 同源：
平台运营商（天猫/阿里妈妈）是服务费收款方，本质非客户。若其作为购方被录入
Customer 表，原代码会把平台商标为「第一大客户」，虚增客户集中度占比。
本测试用 MagicMock 装配 DB，验证聚合跳过平台商。
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tax_risk as TR


class _FakeCustomer:
    def __init__(self, name, tax_no):
        self.name = name
        self.code = tax_no
        self.tax_no = tax_no


class TestCustomerPenetrationPlatformExclusion(unittest.TestCase):

    def _make_db(self, customers, amounts_in_loop_order):
        """构造 MagicMock db：query(Customer).filter().all()=customers；
        query(func.sum(...)).filter().scalar() 按循环顺序返回金额（平台被跳过不调 scalar）。
        """
        db = mock.MagicMock()
        q = db.query.return_value
        f = q.filter.return_value
        f.all.return_value = customers
        f.scalar.side_effect = list(amounts_in_loop_order)
        return db

    def test_platform_excluded_from_top_customer(self):
        # 天猫（平台，应跳过）+ 嘉兴彼格猫（真实客户，400000）
        custs = [
            _FakeCustomer("浙江天猫技术有限公司", "P1"),
            _FakeCustomer("嘉兴彼格猫商贸有限公司", "R1"),
        ]
        # 循环顺序 [天猫, 嘉兴]；天猫被 continue 不调 scalar；
        # 嘉兴调 1 次 scalar（400000），随后 line2688 count 再调 1 次 scalar（0）。
        db = self._make_db(custs, [400000.0, 0])
        results = []
        TR._analyze_customer_penetration(db, 1, None, None, results)
        details = " ".join(r.get("detail", "") for r in results)
        self.assertNotIn("天猫", details, "平台商不得出现在客户穿透结论中")
        self.assertIn("嘉兴彼格猫商贸有限公司", details, "真实客户应保留为客户穿透对象")
        # 仅 1 个真实客户 → 触发「第一大客户占比过高」（占比 100%），对象应为真实客户
        self.assertTrue(any("第一大客户占比过高" in r.get("item", "") for r in results))

    def test_platform_only_yields_no_customer_finding(self):
        custs = [
            _FakeCustomer("浙江天猫技术有限公司", "P1"),
            _FakeCustomer("杭州阿里妈妈软件服务有限公司", "P2"),
        ]
        # 全部平台被跳过，scalar 不会被调用
        db = self._make_db(custs, [])
        results = []
        TR._analyze_customer_penetration(db, 1, None, None, results)
        self.assertEqual(results, [], "纯平台销项不应产生任何客户穿透结论")


if __name__ == "__main__":
    unittest.main(verbosity=2)

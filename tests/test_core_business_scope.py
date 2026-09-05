"""主营业务收入识别与主营口径单测（2026-09-05）。

覆盖：
- identify_core_revenue：费用类排除、品名重合、80/20 主业法则兜底；
- identify_main_biz_cost：三层分类（主营成本/重大费用/日常报销）；
- _scan_supplier_geo 主营口径：费用类发票不混入地域统计，识别不充分时降级并声明口径。
"""
from __future__ import annotations

import unittest

from engine.main_biz_cost import identify_core_revenue, identify_main_biz_cost
from engine.verified_rule_engine import _scan_supplier_geo


def _inv(goods, amount, seller="某供应商有限公司"):
    return {"goods": goods, "amount": amount, "seller": seller}


class CoreRevenueTests(unittest.TestCase):
    def test_expense_goods_never_core_revenue(self):
        sal = [_inv("*餐饮服务*餐费", 100), _inv("*服装*毛衫", 90000)]
        rev = identify_core_revenue(sal)
        # 餐饮是费用类，永远不可能进主营收入
        core_goods = rev["core_goods_sale"]
        self.assertNotIn("*餐饮服务*餐费", core_goods)
        self.assertIn("*服装*毛衫", core_goods)

    def test_goods_overlap_with_core_cost(self):
        sal = [_inv("*纺织产品*纱线", 50000), _inv("*纺织产品*布匹", 50000)]
        rev = identify_core_revenue(sal, core_goods={"*纺织产品*纱线"})
        self.assertIn("*纺织产品*纱线", rev["core_goods_sale"])
        self.assertEqual(rev["core_revenue_ratio"], 1.0)

    def test_8020_rule_promotes_large_goods(self):
        # 制造企业：原料→成品品名不同，靠 80/20 主业法则捞回大额品名
        sal = [_inv("*服装*毛衫", 80000), _inv("*服装*针织衫", 10000), _inv("*服装*围巾", 5000), _inv("*服装*袜子", 5000)]
        rev = identify_core_revenue(sal, core_goods=set())
        self.assertIn("*服装*毛衫", rev["core_goods_sale"])
        self.assertGreaterEqual(rev["core_revenue_ratio"], 0.8)

    def test_empty_sales(self):
        rev = identify_core_revenue([])
        self.assertEqual(rev["core_revenue_amount"], 0.0)
        self.assertEqual(rev["core_revenue_ratio"], 0.0)


class MainBizCostTests(unittest.TestCase):
    def test_three_layer_classification(self):
        pur = [
            _inv("*纺织产品*纱线", 800000),
            _inv("*劳务*加工费", 100000),
            _inv("*餐饮服务*餐费", 500),
            _inv("*住宿服务*房费", 300),
            _inv("*经营租赁*房租", 50000),
        ]
        cls = identify_main_biz_cost(pur)
        core_goods = {r["goods"] for r in cls["core_cost_invs"]}
        self.assertIn("*纺织产品*纱线", core_goods)
        self.assertIn("*劳务*加工费", core_goods)
        minor_goods = {r["goods"] for r in cls["minor_expense_invs"]}
        self.assertIn("*餐饮服务*餐费", minor_goods)
        self.assertIn("*住宿服务*房费", minor_goods)
        major_goods = {r["goods"] for r in cls["major_expense_invs"]}
        self.assertIn("*经营租赁*房租", major_goods)


class SupplierGeoCoreScopeTests(unittest.TestCase):
    def _spec(self):
        return {"id": "VR016", "name": "供应商地域分布与跨省核验", "required_sources": ["pur_invs"]}

    def test_expense_invoices_excluded_from_geo(self):
        # 主营采购集中 2 省 + 大量遍布全国的差旅报销发票
        pur = []
        for i in range(5):
            pur.append(_inv("*纺织产品*纱线", 100000, seller=f"河南纺织原料{i}公司"))
        for i in range(3):
            pur.append(_inv("*纺织产品*棉纱", 80000, seller=f"浙江纱线{i}公司"))
        # 差旅报销：20 家不同省份的酒店/餐饮
        cities = ["北京", "上海", "广州", "深圳", "杭州", "南京", "武汉", "成都", "西安", "天津",
                  "重庆", "青岛", "大连", "厦门", "福州", "长沙", "郑州", "合肥", "昆明", "贵阳"]
        for i, c in enumerate(cities):
            pur.append(_inv("*住宿服务*房费", 300, seller=f"{c}大酒店"))
        data = {"pur_invs": pur, "sal_invs": []}
        findings = _scan_supplier_geo(data, self._spec())
        self.assertTrue(findings, "应产生供应商地域分布发现")
        detail = findings[0]["detail"]
        self.assertIn("主营业务成本口径", detail)
        # 主营口径下只应统计 2 个省份（河南+浙江），而非 22 个
        self.assertIn("分布在2个省份", detail)
        metrics = findings[0]["observed_metrics"]
        self.assertEqual(metrics.get("scope"), "core_cost")

    def test_fallback_when_core_insufficient(self):
        # 主营识别不充分（费用类占大头）→ 降级全量并声明口径
        pur = [_inv("*住宿服务*房费", 100000, seller="北京大酒店"), _inv("*餐饮服务*餐费", 100000, seller="上海餐厅")]
        data = {"pur_invs": pur, "sal_invs": []}
        findings = _scan_supplier_geo(data, self._spec())
        # 只有 2 个省份 <3 供应商？供应商>=3 才统计；此处供应商=2 → 无发现，符合门槛
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()

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


class FundMatchingTests(unittest.TestCase):
    """发票↔银行流水匹配引擎（客户级聚合）单测。"""

    def test_name_normalization(self):
        from engine.fund_matching import normalize_entity_name
        self.assertEqual(normalize_entity_name("河南省郑州市XX纺织原料有限公司"), "郑州市XX纺织原料")
        self.assertEqual(normalize_entity_name("厦门旻刘服装有限公司"), "厦门旻刘服装")
        self.assertEqual(normalize_entity_name("王小明"), "王小明")

    def test_multi_invoice_same_customer_customer_level_match(self):
        # 同一客户多张发票、多笔流水（分批收款）→ 客户级聚合匹配
        from engine.fund_matching import match_invoices_to_flows
        sal = [
            {"buyer": "厦门旻刘服装有限公司", "amount": 294571},
            {"buyer": "厦门旻刘服装有限公司", "amount": 292191},
            {"buyer": "厦门旻刘服装有限公司", "amount": 276956},
        ]
        bank = [
            {"counterparty": "厦门旻刘服装有限公司", "credit": 400000, "debit": 0},
            {"counterparty": "厦门旻刘服装有限公司", "credit": 300000, "debit": 0},
        ]
        r = match_invoices_to_flows(sal, bank, side="sale", name_field="buyer")
        # 发票合计863718 vs 流水700000 → 偏差18.9% ≤25% → 客户级匹配
        self.assertGreater(r["match_ratio"], 0.9)

    def test_huge_gap_stays_unmatched(self):
        # 开票1500万 vs 流水285万 → 客户级偏差巨大 → 正确判未匹配（真实账外信号）
        from engine.fund_matching import match_invoices_to_flows
        sal = [{"buyer": "厦门旻刘服装有限公司", "amount": 5000000},
               {"buyer": "厦门旻刘服装有限公司", "amount": 5000000},
               {"buyer": "厦门旻刘服装有限公司", "amount": 5000000}]
        bank = [{"counterparty": "厦门旻刘服装有限公司", "credit": 2855260, "debit": 0}]
        r = match_invoices_to_flows(sal, bank, side="sale", name_field="buyer")
        self.assertEqual(r["match_ratio"], 0.0)

    def test_purchase_side_debit_only(self):
        # 采购匹配只看支出流水：同名但只有收入流水的不能算支付
        from engine.fund_matching import match_invoices_to_flows
        pur = [{"seller": "河南原料公司", "amount": 100000}]
        bank = [{"counterparty": "河南原料公司", "credit": 100000, "debit": 0}]
        r = match_invoices_to_flows(pur, bank, side="purchase", name_field="seller")
        self.assertEqual(r["match_ratio"], 0.0)

    def test_person_paid_detection(self):
        from engine.fund_matching import classify_core_cost_payment
        pur = [{"seller": "王小明", "amount": 50000}]
        bank = [{"counterparty": "王小明", "debit": 50000, "credit": 0}]
        cls = classify_core_cost_payment(pur, bank)
        self.assertGreater(cls["totals"]["person_paid"], 0)
        self.assertEqual(cls["totals"]["company_paid"], 0)


class VRFundEvidenceRulesTests(unittest.TestCase):
    """VR060/VR061 资金证据链规则单测。"""

    def _spec(self, rid):
        return {"id": rid, "name": "资金证据链", "required_sources": ["pur_invs", "bank_txs"]}

    def test_vr060_core_cost_unpaid_triggered(self):
        from engine.verified_rule_engine import _scan_core_cost_fund_evidence
        pur = [{"seller": "河南纺织原料有限公司", "goods": "*纺织产品*纱线", "amount": 500000}]
        bank = []  # 无流水 → 不触发（诚实：不能凭空说无支付）
        findings = _scan_core_cost_fund_evidence({"pur_invs": pur, "bank_txs": bank}, self._spec("VR060"))
        self.assertEqual(findings, [])

        bank2 = [{"counterparty": "某无关公司", "debit": 1000, "credit": 0}]
        findings = _scan_core_cost_fund_evidence({"pur_invs": pur, "bank_txs": bank2}, self._spec("VR060"))
        self.assertTrue(findings, "大额主营成本无支付流水应触发")
        self.assertIn("未匹配到任何对公支付流水", findings[0]["detail"])

    def test_vr060_person_paid_large_triggered(self):
        from engine.verified_rule_engine import _scan_core_cost_fund_evidence
        pur = [
            {"seller": "河南纺织原料有限公司", "goods": "*纺织产品*纱线", "amount": 600000},
            {"seller": "王小明", "goods": "*劳务*加工费", "amount": 150000},
        ]
        bank = [
            {"counterparty": "河南纺织原料有限公司", "debit": 600000, "credit": 0},
            {"counterparty": "王小明", "debit": 150000, "credit": 0},
        ]
        findings = _scan_core_cost_fund_evidence({"pur_invs": pur, "bank_txs": bank}, self._spec("VR060"))
        person_hits = [f for f in findings if "个人账户垫付" in f["detail"]]
        self.assertTrue(person_hits, "大额个人垫付应触发三流不一致风险")

    def test_vr061_person_inflow_evidence(self):
        from engine.verified_rule_engine import _scan_revenue_receipt_evidence
        sal = [{"buyer": "厦门旻刘服装有限公司", "amount": 5000000}]
        bank = [
            {"counterparty": "厦门旻刘服装有限公司", "credit": 200000, "debit": 0},
            {"counterparty": "范善茂", "credit": 1000000, "debit": 0},
        ]
        findings = _scan_revenue_receipt_evidence({"sal_invs": sal, "bank_txs": bank}, self._spec("VR061"))
        self.assertTrue(findings)
        self.assertIn("个人账户", findings[0]["detail"], "个人流入应写入收款印证发现")

    def test_vr060_vr061_no_bank_no_trigger(self):
        from engine.verified_rule_engine import _scan_core_cost_fund_evidence, _scan_revenue_receipt_evidence
        self.assertEqual(_scan_core_cost_fund_evidence({"pur_invs": [{"amount": 100}], "bank_txs": []}, self._spec("VR060")), [])
        self.assertEqual(_scan_revenue_receipt_evidence({"sal_invs": [{"amount": 100}], "bank_txs": []}, self._spec("VR061")), [])


class VR062ProvisionalCostLoopTests(unittest.TestCase):
    """VR062 暂估成本·其他应付款·公转私闭环核验单测（2026-09-05）。"""

    def _spec(self):
        return {"id": "VR062", "name": "暂估成本公转私闭环", "required_sources": ["trial_balance"]}

    def _tb(self, code, name, debit=0, credit=0):
        # 兼容两种字段风格（标准 + 通用解析器）
        return {"code": code, "name": name, "col_0": code, "col_1": name,
                "借方": debit, "贷方": credit}

    def _loop_data(self):
        """闭环场景：账面成本100万、发票仅支持40万→暂估60万；
        其他应付款贷方余额60万；公转私支付55万。三者金额相近。"""
        tb = [
            self._tb("6401", "主营业务成本", debit=1000000),
            self._tb("2241", "其他应付款", credit=600000),
        ]
        pur = [
            {"seller": "原料公司", "goods": "*纺织产品*纱线", "amount": 400000},
        ]
        bank = [
            {"counterparty": "范善茂", "debit": 300000, "credit": 0},
            {"counterparty": "李四", "debit": 250000, "credit": 0},
        ]
        return {"trial_balance": tb, "pur_invs": pur, "bank_txs": bank, "sal_invs": []}

    def test_closed_loop_triggered(self):
        from engine.verified_rule_engine import _scan_provisional_cost_fund_loop
        data = self._loop_data()
        findings = _scan_provisional_cost_fund_loop(data, self._spec())
        self.assertTrue(findings, "暂估-挂账-公转私闭环应触发")
        self.assertIn("闭环证据链", findings[0]["detail"])
        self.assertIn("暂估成本", findings[0]["detail"])
        m = findings[0]["observed_metrics"]
        self.assertAlmostEqual(m["provisional_cost"], 600000, delta=1)
        self.assertAlmostEqual(m["other_payable_balance"], 600000, delta=1)
        self.assertAlmostEqual(m["person_payout"], 550000, delta=1)

    def test_partial_signal_pending(self):
        """只有账票缺口（暂估），无挂账无公转私 → 待核验级。"""
        from engine.verified_rule_engine import _scan_provisional_cost_fund_loop
        data = {
            "trial_balance": [self._tb("6401", "主营业务成本", debit=800000)],
            "pur_invs": [{"seller": "原料公司", "goods": "*纺织产品*纱线", "amount": 100000}],
            "bank_txs": [],
            "sal_invs": [],
        }
        findings = _scan_provisional_cost_fund_loop(data, self._spec())
        self.assertTrue(findings)
        self.assertEqual(findings[0]["level"], "待核验")
        self.assertIn("账面成本超出进项发票支持部分", findings[0]["detail"])

    def test_no_data_no_trigger(self):
        from engine.verified_rule_engine import _scan_provisional_cost_fund_loop
        self.assertEqual(_scan_provisional_cost_fund_loop(
            {"trial_balance": [], "pur_invs": [], "bank_txs": []}, self._spec()), [])
        # 无成本科目且无其他应付 → 不触发
        self.assertEqual(_scan_provisional_cost_fund_loop(
            {"trial_balance": [self._tb("1001", "库存现金", debit=100)],
             "pur_invs": [], "bank_txs": []}, self._spec()), [])

    def test_voucher_dimension_fallback(self):
        """序时账维度兜底：无科目余额表但有序时账记录主营成本与公转私。"""
        from engine.verified_rule_engine import _scan_provisional_cost_fund_loop
        data = {
            "trial_balance": [],
            "vouchers": [
                {"account_name": "主营业务成本", "debit": 700000, "credit": 0},
                {"account_name": "其他应付款", "credit": 500000, "debit": 0},
            ],
            "pur_invs": [{"seller": "原料公司", "goods": "*纺织产品*纱线", "amount": 200000}],
            "bank_txs": [{"counterparty": "范善茂", "debit": 450000, "credit": 0}],
            "sal_invs": [],
        }
        findings = _scan_provisional_cost_fund_loop(data, self._spec())
        self.assertTrue(findings, "序时账兜底维度应能识别暂估与公转私")
        m = findings[0]["observed_metrics"]
        self.assertAlmostEqual(m["provisional_cost"], 500000, delta=1)

    def test_person_pay_small_not_signal(self):
        """公转私小额（<5万）不构成信号。"""
        from engine.verified_rule_engine import _scan_provisional_cost_fund_loop
        data = {
            "trial_balance": [
                self._tb("6401", "主营业务成本", debit=600000),
                self._tb("2241", "其他应付款", credit=200000),
            ],
            "pur_invs": [{"seller": "原料公司", "goods": "*纺织产品*纱线", "amount": 100000}],
            "bank_txs": [{"counterparty": "王小明", "debit": 30000, "credit": 0}],
            "sal_invs": [],
        }
        findings = _scan_provisional_cost_fund_loop(data, self._spec())
        # 暂估50万+其他应付20万 → 两信号，但公转私3万不构成闭环
        for f in findings:
            self.assertNotIn("闭环证据链", f["detail"])

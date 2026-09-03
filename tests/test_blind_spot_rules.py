# -*- coding: utf-8 -*-
"""VR055/056/057 监管盲区清扫规则回归测试。

覆盖：
1) 原子规则层：run_verified_rules 在猩猩织光式数据上触发三条规则，B2B 对照不误报；
2) 场景执行层：execute_scenario_methodology 通过共同事实门将 VR055/056 落到 findings；
3) 配置层：三条规则已注册进 VERIFIED_RULE_CATALOG / _SCANNERS / COMMON_FACT_CONTRACTS。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import verified_rule_engine as V
from engine import scenario_execution as SE


def _company3_data():
    """模拟猩猩织光：4 人工资同为 7000、个税已缴 0、社保基数倒挂、平台销项+支付宝收款。"""
    return {
        "salaries": [
            {"name": "张帅", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
            {"name": "范雪", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
            {"name": "董师超", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
            {"name": "李宪洲", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
        ],
        "social_security": [
            {"name": "张帅", "base": 7162.0},
            {"name": "范雪", "base": 7162.0},
            {"name": "董师超", "base": 7162.0},
            {"name": "李宪洲", "base": 7162.0},
        ],
        "sal_invs": [
            {"buyer": "浙江天猫技术有限公司", "amount": 2852.81, "tax": 171.17, "total": 3023.98},
            {"buyer": "杭州阿里妈妈软件服务有限公司", "amount": 4998.8, "tax": 299.93, "total": 5298.73},
        ],
        "bank_txs": [
            {"counterparty": "支付宝支付科技有限公司", "credit": 8000.0, "debit": 0.0, "summary": "提现"},
        ],
        "target_entity": {"name": "猩猩织光宠物用品有限公司"},
    }


def _company3_service_fee_data():
    """猩猩织光真实场景：平台运营商购方开『研发和技术服务*专业技术服务』服务费发票（tax_code 304…，6%），
    支付宝归集结算 B2C 宠物食品款。用于验证 VR057 不把服务费发票误算『账外收入敞口』、不把平台商当客户。"""
    return {
        "salaries": [
            {"name": "张帅", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
            {"name": "范雪", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
            {"name": "董师超", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
            {"name": "李宪洲", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
        ],
        "sal_invs": [
            # 平台运营商服务费发票（tax_code 以 3 开头 = 营改增服务，非货物销售）
            {"buyer": "浙江天猫技术有限公司", "goods": "*研发和技术服务*专业技术服务",
             "tax_code": "3040105000000000000", "amount": 2852.81, "tax": 171.17, "total": 3023.98},
            {"buyer": "杭州阿里妈妈软件服务有限公司", "goods": "*研发和技术服务*专业技术服务",
             "tax_code": "3040105000000000000", "amount": 4998.8, "tax": 299.93, "total": 5298.73},
            # 真实 B2C 宠物食品（货物，tax_code 以 1 开头），购方为个人，经支付宝归集
            {"buyer": "杨华（个人）", "goods": "*饲料*宠物食品", "tax_code": "1030104010000000000",
             "amount": 1200.0, "tax": 108.0, "total": 1308.0},
        ],
        "bank_txs": [
            {"counterparty": "支付宝支付科技有限公司", "credit": 8000.0, "debit": 0.0, "summary": "提现"},
        ],
        "target_entity": {"name": "猩猩织光宠物用品有限公司"},
    }


def _b2b_data():
    """B2B 制造对照：工资差异化、对公代发、无平台。"""
    return {
        "salaries": [
            {"name": "王经理", "salary": 18500.0, "net": 14020.0, "acc_paid": 1020.0},
            {"name": "李工", "salary": 12300.0, "net": 9520.0, "acc_paid": 430.0},
            {"name": "赵会计", "salary": 9800.0, "net": 7600.0, "acc_paid": 210.0},
            {"name": "钱销售", "salary": 8600.0, "net": 6700.0, "acc_paid": 90.0},
            {"name": "孙采购", "salary": 9100.0, "net": 7100.0, "acc_paid": 150.0},
        ],
        "sal_invs": [
            {"buyer": "苏州某某制造有限公司", "amount": 120000.0, "tax": 15600.0, "total": 135600.0},
        ],
        "bank_txs": [
            {"counterparty": "工商银行代发工资", "credit": 0.0, "debit": 59300.0, "summary": "工资代发2026-01"},
        ],
        "target_entity": {"name": "某精密制造有限公司"},
    }


def _personal_data():
    """模拟直面个人消费者的零售/餐饮：个人码+老板个人卡收款、均额工资个税为0、无个人侧结算单。"""
    return {
        "salaries": [
            {"name": "张帅", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
            {"name": "范雪", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
            {"name": "董师超", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
            {"name": "李宪洲", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
        ],
        "vouchers": [
            {"summary": "收销售款_微信（个人）", "debit": 12000.0, "credit": 0.0},
            {"summary": "收销售款_老板支付宝", "debit": 8000.0, "credit": 0.0},
        ],
        "bank_txs": [
            {"counterparty": "微信零钱", "credit": 5000.0, "debit": 0.0, "summary": "个人码提现"},
            {"counterparty": "实际控制人卡_王某", "credit": 20000.0, "debit": 0.0, "summary": "个人卡收营业款"},
        ],
        "target_entity": {"name": "某某电商科技有限公司"},
    }


def _cash_data():
    """模拟农贸/餐饮现金密集型：序时账现金收款（库存现金入账腿），无现金日记账佐证。"""
    return {
        "vouchers": [
            {"summary": "收现_摊位零售", "account_name": "库存现金", "debit": 15000.0, "credit": 0.0},
            {"summary": "收现_零售", "account_name": "库存现金", "debit": 8000.0, "credit": 0.0},
        ],
        "target_entity": {"name": "某某农贸有限公司", "scope": "农产品批发零售、农贸市场的摊位租赁与管理"},
    }


def _cash_intensive_no_ledger_data():
    """模拟现金密集型小吃店：序时账无现金收款记录、未提供现金日记账 → 盲区提示。"""
    return {
        "vouchers": [
            {"summary": "付房租", "account_name": "银行存款", "debit": 0.0, "credit": 20000.0},
        ],
        "target_entity": {"name": "某某小吃店", "scope": "小吃、快餐、餐饮服务"},
    }


def _rule_ids_from_findings(se_result):
    ids = set()
    for f in (se_result.get("findings") or []):
        for o in (f.get("observations") or []):
            if isinstance(o, dict):
                ids.add(o.get("rule_id"))
    return ids


class TestVR055WageSplitting(unittest.TestCase):
    def test_vr055_fires_on_uniform_wages(self):
        res = V.run_verified_rules(_company3_data())
        hits = [f for f in res["findings"] if f["rule_id"] == "VR055"]
        self.assertEqual(len(hits), 1, "猩猩织光式均额工资应触发 VR055")
        f = hits[0]
        self.assertEqual(f["finding_status"], "clue_pending_investigation")
        self.assertIn("demand_docs", f["observed_metrics"])
        self.assertTrue(any("私户" in d for d in f["observed_metrics"]["demand_docs"]))

    def test_vr055_not_fired_on_diverse_wages(self):
        res = V.run_verified_rules(_b2b_data())
        hits = [f for f in res["findings"] if f["rule_id"] == "VR055"]
        self.assertEqual(len(hits), 0, "差异化工资不应触发 VR055")


class TestVR056MixedPayroll(unittest.TestCase):
    def test_vr056_blind_spot_when_no_bank(self):
        data = _company3_data()
        data.pop("bank_txs", None)
        res = V.run_verified_rules(data)
        hits = [f for f in res["findings"] if f["rule_id"] == "VR056"]
        self.assertEqual(len(hits), 1, "无银行流水应触发 VR056 监管盲区提示")
        self.assertEqual(hits[0]["finding_status"], "data_quality_limitation")
        self.assertIn("未提供任何银行流水", hits[0]["detail"])

    def test_vr056_gap_branch_when_bank_present(self):
        res = V.run_verified_rules(_company3_data())
        hits = [f for f in res["findings"] if f["rule_id"] == "VR056"]
        self.assertEqual(len(hits), 1, "公户工资支出远低于账面应发应触发 VR056 拆分嫌疑")
        self.assertIn("unexplained_gap", hits[0]["observed_metrics"])


class TestVR057ThirdPartyBlindspot(unittest.TestCase):
    def test_vr057_fires_on_platform_sales(self):
        res = V.run_verified_rules(_company3_data())
        hits = [f for f in res["findings"] if f["rule_id"] == "VR057"]
        self.assertEqual(len(hits), 1, "天猫/支付宝收款应触发 VR057 平台盲区")
        self.assertIn("demand_docs", hits[0]["observed_metrics"])

    def test_vr057_silent_on_b2b(self):
        res = V.run_verified_rules(_b2b_data())
        hits = [f for f in res["findings"] if f["rule_id"] == "VR057"]
        self.assertEqual(len(hits), 0, "无平台销售的 B2B 不应触发 VR057")


class TestVR058PersonalCollection(unittest.TestCase):
    def test_vr058_fires_on_personal_collection(self):
        res = V.run_verified_rules(_personal_data())
        hits = [f for f in res["findings"] if f["rule_id"] == "VR058"]
        self.assertEqual(len(hits), 1, "个人码+老板个人卡收款应触发 VR058 盲区")
        f = hits[0]
        self.assertIn("demand_docs", f["observed_metrics"])
        self.assertTrue(any("个人码" in d for d in f["observed_metrics"]["demand_docs"]))
        self.assertTrue(any("个人卡" in d for d in f["observed_metrics"]["demand_docs"]))

    def test_vr058_not_fired_on_third_party_platform_only(self):
        # VR057（企业第三方平台）数据不应误触发 VR058（个人码），两规则口径互斥
        res = V.run_verified_rules(_company3_data())
        hits = [f for f in res["findings"] if f["rule_id"] == "VR058"]
        self.assertEqual(len(hits), 0, "仅企业第三方平台收款不应触发 VR058")

    def test_vr058_not_fired_on_b2b(self):
        res = V.run_verified_rules(_b2b_data())
        hits = [f for f in res["findings"] if f["rule_id"] == "VR058"]
        self.assertEqual(len(hits), 0, "差异化工资+对公代发的 B2B 不应触发 VR058")

    def test_vr058_wage_split_linkage(self):
        res = V.run_verified_rules(_personal_data())
        hits = [f for f in res["findings"] if f["rule_id"] == "VR058"]
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0]["observed_metrics"]["wage_split_linkage"], "均额工资应联动 VR058 个税逃漏线索")


class TestVR059CashBlindspot(unittest.TestCase):
    def test_vr059_fires_on_cash_voucher(self):
        res = V.run_verified_rules(_cash_data())
        hits = [f for f in res["findings"] if f["rule_id"] == "VR059"]
        self.assertEqual(len(hits), 1, "序时账现金收款应触发 VR059 盲区")
        f = hits[0]
        self.assertIn("demand_docs", f["observed_metrics"])
        self.assertTrue(any("现金日记账" in d for d in f["observed_metrics"]["demand_docs"]))
        self.assertTrue(any("取现" in d for d in f["observed_metrics"]["demand_docs"]))

    def test_vr059_blind_spot_when_cash_intensive_no_ledger(self):
        res = V.run_verified_rules(_cash_intensive_no_ledger_data())
        hits = [f for f in res["findings"] if f["rule_id"] == "VR059"]
        self.assertEqual(len(hits), 1, "现金密集型行业无现金记录应触发 VR059 盲区提示")
        self.assertEqual(hits[0]["finding_status"], "data_quality_limitation")
        self.assertTrue(hits[0]["observed_metrics"]["cash_intensive_blindspot"])

    def test_vr059_not_fired_on_b2b(self):
        # B2B 制造无 vouchers（required_sources 缺失）→ 规则被跳过，不误报
        res = V.run_verified_rules(_b2b_data())
        hits = [f for f in res["findings"] if f["rule_id"] == "VR059"]
        self.assertEqual(len(hits), 0, "无 vouchers 的 B2B 不应触发 VR059")

    def test_vr059_not_fired_on_personal_code_only(self):
        # 个人码收款（VR058 口径）不应误触发 VR059 现金盲区
        res = V.run_verified_rules(_personal_data())
        hits = [f for f in res["findings"] if f["rule_id"] == "VR059"]
        self.assertEqual(len(hits), 0, "仅个人码收款（无现金摘要+非现金密集型名号）不应触发 VR059")


class TestScenarioSurfacing(unittest.TestCase):
    """端到端：三条规则经共同事实门落到 scenario_execution.findings。"""
    def test_surfaced_via_common_gate(self):
        se = SE.execute_scenario_methodology("宠物用品零售", file_results=None, engine_data=_company3_data())
        ids = _rule_ids_from_findings(se)
        self.assertIn("VR055", ids, "VR055 应经共同事实门进入 findings")
        self.assertIn("VR056", ids, "VR056 应经共同事实门进入 findings")
        self.assertIn("VR057", ids, "VR057 应进入 findings")

    def test_vr058_surfaced_via_common_gate(self):
        se = SE.execute_scenario_methodology("餐饮零售", file_results=None, engine_data=_personal_data())
        ids = _rule_ids_from_findings(se)
        self.assertIn("VR058", ids, "VR058 应经共同事实门进入 findings")

    def test_vr059_surfaced_via_common_gate(self):
        se = SE.execute_scenario_methodology("农贸零售", file_results=None, engine_data=_cash_data())
        ids = _rule_ids_from_findings(se)
        self.assertIn("VR059", ids, "VR059 应经共同事实门进入 findings")

    def test_b2b_control_not_flagged(self):
        se = SE.execute_scenario_methodology("通用设备制造", file_results=None, engine_data=_b2b_data())
        ids = _rule_ids_from_findings(se)
        self.assertNotIn("VR055", ids)
        self.assertNotIn("VR057", ids)
        self.assertNotIn("VR058", ids)
        self.assertNotIn("VR059", ids)


class TestConfiguration(unittest.TestCase):
    def test_registered_in_catalog_and_scanners(self):
        catalog_ids = {c["id"] for c in V.VERIFIED_RULE_CATALOG}
        for rid in ("VR055", "VR056", "VR057", "VR058", "VR059"):
            self.assertIn(rid, catalog_ids, f"{rid} 应在 VERIFIED_RULE_CATALOG")
            self.assertIn(rid, V._SCANNERS, f"{rid} 应在 _SCANNERS")
            self.assertTrue(callable(V._SCANNERS[rid]))

    def test_wired_into_common_fact_contracts(self):
        contracts = SE.COMMON_FACT_CONTRACTS
        self.assertIn("VR055", contracts["COMMON-EMPLOYMENT-COVERAGE"]["rule_ids"])
        self.assertIn("VR056", contracts["COMMON-PERSONNEL-FUND-FLOW"]["rule_ids"])
        self.assertIn("VR057", contracts["COMMON-REVENUE-RECONCILIATION"]["rule_ids"])
        self.assertIn("VR058", contracts["COMMON-REVENUE-RECONCILIATION"]["rule_ids"])
        self.assertIn("VR059", contracts["COMMON-REVENUE-RECONCILIATION"]["rule_ids"])


class TestPlatformServiceFeeClassification(unittest.TestCase):
    """回归：平台运营商服务费发票不得误算『账外收入敞口』，平台商不得当『客户』。"""

    def test_classifier_identifies_service_fee(self):
        service_inv = {"buyer": "浙江天猫技术有限公司", "goods": "*研发和技术服务*专业技术服务",
                       "tax_code": "3040105000000000000"}
        goods_inv = {"buyer": "杨华（个人）", "goods": "*饲料*宠物食品", "tax_code": "1030104010000000000"}
        self.assertTrue(V._invoice_is_service_fee(service_inv), "服务费发票（tax_code 3 开头）应判为服务费")
        self.assertFalse(V._invoice_is_service_fee(goods_inv), "宠物食品（tax_code 1 开头）不应判为服务费")

    def test_is_platform_operator(self):
        self.assertTrue(V._is_platform_operator("浙江天猫技术有限公司"))
        self.assertTrue(V._is_platform_operator("杭州阿里妈妈软件服务有限公司"))
        self.assertFalse(V._is_platform_operator("杨华（个人）"))
        self.assertFalse(V._is_platform_operator("苏州某某制造有限公司"))

    def test_vr057_excludes_service_fee_from_divergence(self):
        res = V.run_verified_rules(_company3_service_fee_data())
        hits = [f for f in res["findings"] if f["rule_id"] == "VR057"]
        self.assertEqual(len(hits), 1, "支付宝收款仍应触发 VR057 第三方平台盲区")
        m = hits[0]["observed_metrics"]
        self.assertEqual(m["platform_sales_count"], 0, "服务费发票不得计入『平台对消费者销售』")
        self.assertEqual(m["service_fee_invoice_count"], 2, "应识别 2 张平台服务费发票")
        self.assertIsNone(m["divergence_amount"], "服务费发票不得算出虚假账外收入敞口（divergence）")
        self.assertIn("品名与经营主体不匹配", hits[0]["detail"], "应提示服务费发票品名与主体不匹配待证疑点")

    def test_related_party_graph_relabels_platform_operator(self):
        try:
            from main import _build_related_party_graph
        except Exception as e:  # main 导入较重，环境不可用时跳过而非失败
            self.skipTest(f"main 模块不可用：{e}")
        report_data = {
            "target_entity": {"name": "猩猩织光宠物用品有限公司"},
            "all_findings": [],
            "material_intel": {"发票": {"销项客户明细": [
                {"名称": "浙江天猫技术有限公司", "金额": "23688.03"},
                {"名称": "杭州阿里妈妈软件服务有限公司", "金额": "17375.55"},
                {"名称": "王颖（个人）", "金额": "45000.00"},
            ], "进项供应商明细": []}},
        }
        g = _build_related_party_graph(report_data)
        roles = {n["name"]: n["role"] for n in g["core_customers"]}
        self.assertEqual(roles.get("浙江天猫技术有限公司"), "平台服务商", "天猫应标『平台服务商』而非『客户』")
        self.assertEqual(roles.get("杭州阿里妈妈软件服务有限公司"), "平台服务商")
        self.assertEqual(roles.get("王颖（个人）"), "客户", "真实个人客户应保留『客户』")
        # 平台服务商不计入『客户集中度』风险；真实个人客户占比高仍应正常标风险
        risk_types = [r["type"] for r in g["risks"]]
        self.assertIn("客户高度集中", risk_types, "真实个人客户高度集中仍应提示")


if __name__ == "__main__":
    unittest.main(verbosity=2)

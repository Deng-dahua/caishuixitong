from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class WholesaleRetailScenarioContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(
            (STATIC / "wholesale_retail_scenario_contracts.json").read_text(encoding="utf-8")
        )

    def test_seven_scenes_have_complete_five_chain_contracts(self):
        scenes = self.payload["scenarios"]
        self.assertEqual(len(scenes), 7)
        self.assertEqual({scene["id"] for scene in scenes}, {f"RET-{n:02d}" for n in range(1, 8)})
        for scene in scenes:
            self.assertEqual(scene["maturity"], "M2.5_boundary_tested")
            for key in ("doubt", "clue_chain", "evidence_chain", "analysis_chain", "domain_collaboration"):
                self.assertIn(key, scene)
            self.assertGreaterEqual(len(scene["clue_chain"]["steps"]), 4)
            self.assertGreaterEqual(len(scene["evidence_chain"]["fact_elements"]), 5)
            self.assertGreaterEqual(len(scene["evidence_chain"]["opposing_sources"]), 4)
            self.assertGreaterEqual(len(scene["analysis_chain"]["reasoning"]), 5)
            self.assertGreaterEqual(len(scene["domain_collaboration"]["partners"]), 4)
            self.assertEqual(
                {case["case"] for case in scene["validation_cases"]},
                {"positive", "negative", "ambiguous"},
            )

    def test_legacy_absorption_is_traceable_unique_and_not_released(self):
        absorbed = []
        for scene in self.payload["scenarios"]:
            migration = scene["legacy_absorption"]
            self.assertGreater(len(migration["legacy_rule_ids"]), 0)
            self.assertEqual(
                migration["absorption_status"],
                "absorbed_into_scene_contract_not_released",
            )
            self.assertTrue(migration.get("absorption_reason"))
            self.assertTrue(migration.get("boundary"))
            absorbed.extend(migration["legacy_rule_ids"])
        self.assertEqual(len(absorbed), 63)
        self.assertEqual(len(absorbed), len(set(absorbed)))

    def test_sources_and_forbidden_outputs_keep_current_policy_boundaries(self):
        self.assertGreaterEqual(len(self.payload["official_sources"]), 10)
        self.assertTrue(all(source["url"].startswith("https://") for source in self.payload["official_sources"]))
        self.assertIn("自动立案", self.payload["common_contract"]["forbidden_outputs"])
        self.assertTrue(any("2026" in source["effective_period"] for source in self.payload["official_sources"]))


class WholesaleRetailScenarioPlannerTests(unittest.TestCase):
    def test_plan_routes_retail_sources_and_preserves_findings(self):
        from engine.scenario_methodology import build_scenario_review_plan

        files = [
            {"type": "generic_data", "file": "门店SKU进销存盘点调拨.xlsx"},
            {"type": "generic_data", "file": "全渠道订单支付平台结算.xlsx"},
            {"type": "generic_data", "file": "退货退款红字发票.xlsx"},
            {"type": "generic_data", "file": "返利促销代销联营协议.xlsx"},
            {"type": "generic_data", "file": "会员储值积分核销.xlsx"},
            {"type": "bank_statement", "file": "聚合支付收款码银行流水.xlsx"},
            {"type": "voucher", "file": "零售收入成本会计凭证.xlsx"},
            {"type": "tax_return", "file": "增值税企业所得税申报.xlsx"},
            {"type": "sales_invoice", "file": "蓝红销售发票.xlsx"},
        ]
        findings = [{"type": "订单支付结算差异", "detail": "平台结算与已签收订单待核"}]
        before = copy.deepcopy(findings)
        plan = build_scenario_review_plan("F 批发和零售业", files, findings)

        self.assertTrue(plan["applicable"])
        self.assertEqual(plan["industry_code"], "F")
        self.assertEqual(plan["contract_asset"], "wholesale_retail_scenario_contracts")
        self.assertEqual(plan["scene_count"], 7)
        by_id = {scene["scene_id"]: scene for scene in plan["scenes"]}
        self.assertEqual(by_id["RET-02"]["status"], "资料就绪_待人工核验")
        self.assertGreaterEqual(by_id["RET-02"]["candidate_signal_count"], 1)
        self.assertEqual(findings, before)


class WholesaleRetailScenarioIntegrationTests(unittest.TestCase):
    def test_coverage_discloses_four_m25_industries_without_claiming_m3(self):
        from engine.methodology_coverage import build_methodology_coverage

        report = build_methodology_coverage(STATIC)
        self.assertEqual(report["version"], "1.4.0")
        self.assertEqual(report["inventory"]["rewritten_m25_scenarios"], 31)
        retail = next(row for row in report["industry_matrix"] if row["code"] == "F")
        self.assertEqual(retail["rewritten_m25_scenarios"], 7)
        self.assertEqual(retail["verified_specific_rules"], 0)
        self.assertIn("待脱敏真实样本验证", retail["state"])
        rewrite = report["candidate_governance"]["rewrite_program"]["summary"]
        self.assertEqual(rewrite["absorbed_into_scene_contract"], 63)
        self.assertEqual(rewrite["queued_not_rewritten"] + rewrite["absorbed_into_scene_contract"], 1720)
        self.assertEqual(rewrite["released_from_legacy_library"], 0)

    def test_api_frontend_and_cache_publish_guarded_retail_contract(self):
        main_text = (ROOT / "main.py").read_text(encoding="utf-8")
        frontend = (STATIC / "js" / "tax-pipeline-pages.js").read_text(encoding="utf-8")
        index = (STATIC / "index.html").read_text(encoding="utf-8")

        self.assertIn('"wholesale_retail_scenario_contracts": "wholesale_retail_scenario_contracts.json"', main_text)
        self.assertIn("wholesale_retail_scenario_contracts.json", main_text)
        self.assertIn("/api/methodology/assets/wholesale_retail_scenario_contracts", frontend)
        self.assertIn("批发零售业真实场景五链配套重写", frontend)
        self.assertIn("已吸收进场景未放行", frontend)
        self.assertIn("tax-pipeline-pages.js?v=2026080207", index)


if __name__ == "__main__":
    unittest.main()

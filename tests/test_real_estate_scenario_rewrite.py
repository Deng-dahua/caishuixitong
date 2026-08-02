from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class RealEstateScenarioContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(
            (STATIC / "real_estate_scenario_contracts.json").read_text(encoding="utf-8")
        )

    def test_eight_scenes_use_one_id_across_all_five_method_layers(self):
        scenes = self.payload["scenarios"]
        self.assertEqual(len(scenes), 8)
        self.assertEqual({scene["id"] for scene in scenes}, {f"REA-{n:02d}" for n in range(1, 9)})
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

    def test_contract_requires_local_policy_and_forbids_price_only_findings(self):
        self.assertGreaterEqual(len(self.payload["official_sources"]), 9)
        common = self.payload["common_contract"]
        self.assertIn("local_document_no", common["local_policy_keys"])
        self.assertIn("clearance_unit", common["project_keys"])
        self.assertIn("自动立案", common["forbidden_outputs"])
        self.assertTrue(any("地方" in boundary for boundary in self.payload["release_boundary"]))


class RealEstateScenarioPlannerTests(unittest.TestCase):
    def test_plan_routes_real_estate_and_preserves_findings(self):
        from engine.scenario_methodology import build_scenario_review_plan

        files = [
            {"type": "contract", "file": "商品房预售合同及补充协议.docx"},
            {"type": "generic_data", "file": "土地规划预售许可和楼盘房源表.xlsx"},
            {"type": "bank_statement", "file": "监管账户按揭收退款流水.xlsx"},
            {"type": "tax_return", "file": "增值税预缴和土地增值税清算申报.xlsx"},
            {"type": "voucher", "file": "房地产项目开发成本核算凭证.xlsx"},
            {"type": "sales_invoice", "file": "商品房销售发票.xlsx"},
        ]
        findings = [{"type": "商品房预售款预缴差异", "detail": "房源收款与预缴期间待核"}]
        before = copy.deepcopy(findings)
        plan = build_scenario_review_plan("K 房地产开发业", files, findings)

        self.assertTrue(plan["applicable"])
        self.assertEqual(plan["industry_code"], "K")
        self.assertEqual(plan["contract_asset"], "real_estate_scenario_contracts")
        self.assertEqual(plan["scene_count"], 8)
        by_id = {scene["scene_id"]: scene for scene in plan["scenes"]}
        self.assertEqual(by_id["REA-02"]["status"], "资料就绪_待人工核验")
        self.assertGreaterEqual(by_id["REA-02"]["candidate_signal_count"], 1)
        self.assertEqual(findings, before)


class RealEstateScenarioIntegrationTests(unittest.TestCase):
    def test_coverage_discloses_three_m25_industries_without_claiming_m3(self):
        from engine.methodology_coverage import build_methodology_coverage

        report = build_methodology_coverage(STATIC)
        self.assertEqual(report["inventory"]["rewritten_m25_scenarios"], 55)
        real_estate = next(row for row in report["industry_matrix"] if row["code"] == "K")
        self.assertEqual(real_estate["rewritten_m25_scenarios"], 8)
        self.assertEqual(real_estate["verified_specific_rules"], 0)
        self.assertIn("待脱敏真实样本验证", real_estate["state"])

    def test_pipeline_api_and_frontend_use_guarded_real_estate_contract(self):
        main_text = (ROOT / "main.py").read_text(encoding="utf-8")
        pipeline = (ROOT / "engine" / "pipeline.py").read_text(encoding="utf-8")
        frontend = (STATIC / "js" / "tax-pipeline-pages.js").read_text(encoding="utf-8")
        index = (STATIC / "index.html").read_text(encoding="utf-8")

        self.assertIn('"real_estate_scenario_contracts": "real_estate_scenario_contracts.json"', main_text)
        scenario_block = pipeline.split("# ═══ 场景主键制方法论", 1)[1].split("# ═══ 规则深度字段消费", 1)[0]
        self.assertNotIn("all_findings.append", scenario_block)
        self.assertNotIn("all_findings.extend", scenario_block)
        self.assertIn("/api/methodology/assets/real_estate_scenario_contracts", frontend)
        self.assertIn("房地产开发业真实场景五链配套重写", frontend)
        self.assertIn("tax-pipeline-pages.js?v=2026080301", index)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class ConstructionScenarioContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(
            (STATIC / "construction_scenario_contracts.json").read_text(encoding="utf-8")
        )

    def test_eight_scenes_use_one_id_across_all_five_method_layers(self):
        scenes = self.payload["scenarios"]
        self.assertEqual(len(scenes), 8)
        self.assertEqual({scene["id"] for scene in scenes}, {f"CON-{n:02d}" for n in range(1, 9)})
        for scene in scenes:
            self.assertEqual(scene["maturity"], "M2.5_boundary_tested")
            for key in (
                "doubt",
                "clue_chain",
                "evidence_chain",
                "analysis_chain",
                "domain_collaboration",
            ):
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

    def test_contract_separates_policy_period_and_forbids_automatic_findings(self):
        self.assertGreaterEqual(len(self.payload["official_sources"]), 8)
        self.assertTrue(
            all(source["url"].startswith("https://") for source in self.payload["official_sources"])
        )
        common = self.payload["common_contract"]
        self.assertIn("policy_period", common["time_keys"])
        self.assertIn("project_id", common["project_keys"])
        self.assertIn("自动立案", common["forbidden_outputs"])
        self.assertIn("资料不足_未启动", common["allowed_states"])
        self.assertIn("事实充分支持_待审理", common["allowed_states"])


class ConstructionScenarioPlannerTests(unittest.TestCase):
    def test_plan_routes_building_industry_and_preserves_findings(self):
        from engine.scenario_methodology import build_scenario_review_plan

        files = [
            {"type": "contract", "file": "施工总包及分包合同.docx"},
            {"type": "generic_data", "file": "工程项目进度结算及监理确认.xlsx"},
            {"type": "tax_return", "file": "跨地区项目增值税预缴及申报表.xlsx"},
            {"type": "sales_invoice", "file": "工程款发票.xlsx"},
            {"type": "bank_statement", "file": "工程款银行流水.xlsx"},
            {"type": "voucher", "file": "项目收入成本凭证.xlsx"},
            {"type": "salary", "file": "实名考勤工资专户表.xlsx"},
            {"type": "inventory", "file": "甲供材料领退料台账.xlsx"},
        ]
        findings = [{"type": "跨地区项目预缴差异", "detail": "项目台账与申报抵减待核"}]
        before = copy.deepcopy(findings)
        plan = build_scenario_review_plan("E 建筑业", files, findings)

        self.assertTrue(plan["applicable"])
        self.assertEqual(plan["industry_code"], "E")
        self.assertEqual(plan["contract_asset"], "construction_scenario_contracts")
        self.assertEqual(plan["scene_count"], 8)
        by_id = {scene["scene_id"]: scene for scene in plan["scenes"]}
        self.assertEqual(by_id["CON-01"]["status"], "资料就绪_待人工核验")
        self.assertGreaterEqual(by_id["CON-01"]["candidate_signal_count"], 1)
        self.assertEqual(findings, before)
        self.assertNotIn("all_findings", plan)


class ConstructionScenarioIntegrationTests(unittest.TestCase):
    def test_coverage_discloses_two_m25_industries_without_claiming_m3(self):
        from engine.methodology_coverage import build_methodology_coverage

        report = build_methodology_coverage(STATIC)
        self.assertEqual(report["inventory"]["rewritten_m25_scenarios"], 24)
        manufacturing = next(row for row in report["industry_matrix"] if row["code"] == "C")
        construction = next(row for row in report["industry_matrix"] if row["code"] == "E")
        self.assertEqual(manufacturing["rewritten_m25_scenarios"], 8)
        self.assertEqual(construction["rewritten_m25_scenarios"], 8)
        self.assertEqual(construction["verified_specific_rules"], 0)
        self.assertIn("待脱敏真实样本验证", construction["state"])

    def test_pipeline_api_and_frontend_use_guarded_construction_contract(self):
        main_text = (ROOT / "main.py").read_text(encoding="utf-8")
        pipeline = (ROOT / "engine" / "pipeline.py").read_text(encoding="utf-8")
        frontend = (STATIC / "js" / "tax-pipeline-pages.js").read_text(encoding="utf-8")
        index = (STATIC / "index.html").read_text(encoding="utf-8")

        self.assertIn(
            '"construction_scenario_contracts": "construction_scenario_contracts.json"',
            main_text,
        )
        scenario_block = pipeline.split("# ═══ 场景主键制方法论", 1)[1].split(
            "# ═══ 规则深度字段消费", 1
        )[0]
        self.assertNotIn("all_findings.append", scenario_block)
        self.assertNotIn("all_findings.extend", scenario_block)
        self.assertIn("scenario_methodology.get('scene_count', 0)", scenario_block)
        self.assertIn("/api/methodology/assets/construction_scenario_contracts", frontend)
        self.assertIn("建筑业真实场景五链配套重写", frontend)
        self.assertIn("tax-pipeline-pages.js?v=2026080206", index)


if __name__ == "__main__":
    unittest.main()

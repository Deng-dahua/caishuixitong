from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class ManufacturingScenarioContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(
            (STATIC / "manufacturing_scenario_contracts.json").read_text(encoding="utf-8")
        )

    def test_eight_scenes_use_one_id_across_all_five_method_layers(self):
        scenes = self.payload["scenarios"]
        self.assertEqual(len(scenes), 8)
        self.assertEqual({scene["id"] for scene in scenes}, {f"MFG-{n:02d}" for n in range(1, 9)})
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

    def test_contract_has_policy_periods_lineage_and_explicit_forbidden_outputs(self):
        self.assertGreaterEqual(len(self.payload["official_sources"]), 7)
        self.assertTrue(all(source["url"].startswith("https://") for source in self.payload["official_sources"]))
        common = self.payload["common_contract"]
        self.assertIn("file_sha256", common["source_lineage"])
        self.assertIn("自动立案", common["forbidden_outputs"])
        self.assertIn("资料不足_未启动", common["allowed_states"])
        self.assertIn("事实充分支持_待审理", common["allowed_states"])


class ScenarioPlannerTests(unittest.TestCase):
    def test_unrewritten_industry_does_not_receive_another_industry_plan(self):
        from engine.scenario_methodology import build_scenario_review_plan

        plan = build_scenario_review_plan("住宿和餐饮业", file_results=[], findings=[])
        self.assertFalse(plan["applicable"])
        self.assertEqual(plan["status"], "不适用")
        self.assertEqual(plan["scenes"], [])

    def test_plan_reports_source_gates_without_creating_findings(self):
        from engine.scenario_methodology import build_scenario_review_plan

        files = [
            {"type": "inventory", "file": "生产工单及进销存.xlsx"},
            {"type": "sales_invoice", "file": "销项发票.xlsx"},
            {"type": "bank_statement", "file": "银行流水.xlsx"},
            {"type": "voucher", "file": "记账凭证.xlsx"},
            {"type": "contract", "file": "销售及委外合同.docx"},
        ]
        findings = [{"type": "投入产出数量差异", "detail": "BOM与完工数量待核"}]
        before = copy.deepcopy(findings)
        plan = build_scenario_review_plan("C 制造业", files, findings)
        self.assertTrue(plan["applicable"])
        self.assertEqual(plan["scene_count"], 8)
        by_id = {scene["scene_id"]: scene for scene in plan["scenes"]}
        self.assertEqual(by_id["MFG-01"]["status"], "资料就绪_待人工核验")
        self.assertGreaterEqual(by_id["MFG-01"]["candidate_signal_count"], 1)
        self.assertEqual(findings, before)
        self.assertNotIn("all_findings", plan)
        self.assertIn("候选信号只用于确定核验顺序", by_id["MFG-01"]["candidate_signal_boundary"])


class ScenarioIntegrationTests(unittest.TestCase):
    def test_coverage_discloses_m25_without_claiming_m3(self):
        from engine.methodology_coverage import build_methodology_coverage

        report = build_methodology_coverage(STATIC)
        self.assertEqual(report["inventory"]["rewritten_m25_scenarios"], 55)
        manufacturing = next(row for row in report["industry_matrix"] if row["code"] == "C")
        self.assertEqual(manufacturing["rewritten_m25_scenarios"], 8)
        self.assertEqual(manufacturing["verified_specific_rules"], 0)
        self.assertIn("待脱敏真实样本验证", manufacturing["state"])

    def test_pipeline_and_frontend_use_guarded_scenario_contract(self):
        main_text = (ROOT / "main.py").read_text(encoding="utf-8")
        pipeline = (ROOT / "engine" / "pipeline.py").read_text(encoding="utf-8")
        frontend = (STATIC / "js" / "tax-pipeline-pages.js").read_text(encoding="utf-8")
        index = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn(
            '"manufacturing_scenario_contracts": "manufacturing_scenario_contracts.json"',
            main_text,
        )
        self.assertIn("build_scenario_review_plan", pipeline)
        self.assertIn('comprehensive["scenario_methodology"]', pipeline)
        scenario_block = pipeline.split("# ═══ 场景主键制方法论", 1)[1].split(
            "# ═══ 规则深度字段消费", 1
        )[0]
        self.assertNotIn("all_findings.append", scenario_block)
        self.assertNotIn("all_findings.extend", scenario_block)
        self.assertIn("/api/methodology/assets/manufacturing_scenario_contracts", frontend)
        self.assertIn("制造业真实场景五链配套重写", frontend)
        self.assertIn("tax-pipeline-pages.js?v=2026080301", index)


if __name__ == "__main__":
    unittest.main()

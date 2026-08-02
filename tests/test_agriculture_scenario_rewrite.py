from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class AgricultureScenarioContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(
            (STATIC / "agriculture_scenario_contracts.json").read_text(encoding="utf-8")
        )

    def test_eight_agriculture_scenes_have_complete_five_chain_contracts(self):
        scenes = self.payload["scenarios"]
        self.assertEqual(len(scenes), 8)
        self.assertEqual({scene["id"] for scene in scenes}, {f"AGR-{n:02d}" for n in range(1, 9)})
        for scene in scenes:
            self.assertEqual(scene["maturity"], "M2.5_boundary_tested")
            for key in ("doubt", "clue_chain", "evidence_chain", "analysis_chain", "domain_collaboration"):
                self.assertIn(key, scene)
            self.assertGreaterEqual(len(scene["clue_chain"]["steps"]), 5)
            self.assertGreaterEqual(len(scene["evidence_chain"]["fact_elements"]), 6)
            self.assertGreaterEqual(len(scene["evidence_chain"]["opposing_sources"]), 5)
            self.assertGreaterEqual(len(scene["analysis_chain"]["reasoning"]), 7)
            self.assertGreaterEqual(len(scene["domain_collaboration"]["partners"]), 5)
            self.assertEqual(
                {case["case"] for case in scene["validation_cases"]},
                {"positive", "negative", "ambiguous"},
            )

    def test_absorption_is_selective_unique_and_traceable(self):
        absorbed = []
        no_direct_match = set()
        for scene in self.payload["scenarios"]:
            migration = scene["legacy_absorption"]
            ids = migration["legacy_rule_ids"]
            if ids:
                self.assertEqual(
                    migration["absorption_status"],
                    "absorbed_into_scene_contract_not_released",
                )
                absorbed.extend(ids)
            else:
                self.assertEqual(migration["absorption_status"], "no_direct_legacy_match_new_contract")
                no_direct_match.add(scene["id"])
            self.assertTrue(migration["absorption_reason"])
            self.assertTrue(migration["boundary"])
        self.assertEqual(no_direct_match, {"AGR-04", "AGR-07"})
        self.assertEqual(len(absorbed), 34)
        self.assertEqual(len(absorbed), len(set(absorbed)))

        earlier_ids = set()
        for path in STATIC.glob("*_scenario_contracts.json"):
            if path.name == "agriculture_scenario_contracts.json":
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            earlier_ids.update(
                legacy_id
                for scene in payload.get("scenarios", [])
                for legacy_id in scene.get("legacy_absorption", {}).get("legacy_rule_ids", [])
            )
        self.assertTrue(set(absorbed).isdisjoint(earlier_ids))

    def test_current_agriculture_sources_and_safety_boundaries_are_present(self):
        sources = {source["id"]: source for source in self.payload["official_sources"]}
        for source_id in (
            "SRC-AGR-VAT-RULES", "SRC-AGR-VAT-TRANSITION", "SRC-AGR-VAT-DEDUCTION",
            "SRC-AGR-CIT-48", "SRC-AGR-COOP-LAW", "SRC-AGR-LAND-FLOW",
            "SRC-AGR-FISCAL-FUNDS", "SRC-AGR-INSURANCE", "SRC-AGR-BIO-ASSET",
        ):
            self.assertIn(source_id, sources)
            self.assertTrue(sources[source_id]["url"].startswith("https://"))
        forbidden = self.payload["common_contract"]["forbidden_outputs"]
        self.assertIn("以理论亩产直接核定收入", forbidden)
        self.assertIn("把补贴或保险赔款一律视为免税", forbidden)


class AgricultureScenarioPlannerTests(unittest.TestCase):
    def test_plan_routes_agriculture_and_preserves_findings(self):
        from engine.scenario_methodology import build_scenario_review_plan

        files = [
            {"type": "generic_data", "file": "农产品收购发票农户交付过磅台账.xlsx"},
            {"type": "inventory", "file": "农产品入库加工投料.xlsx"},
            {"type": "bank_statement", "file": "农户分户付款银行流水.xlsx"},
            {"type": "tax_return", "file": "农产品进项抵扣申报表.xlsx"},
        ]
        findings = [{"type": "农产品收购核定扣除差异", "detail": "收购发票与过磅付款待核"}]
        before = copy.deepcopy(findings)
        plan = build_scenario_review_plan("A 农、林、牧、渔业", files, findings)

        self.assertTrue(plan["applicable"])
        self.assertEqual(plan["industry_code"], "A")
        self.assertEqual(plan["contract_asset"], "agriculture_scenario_contracts")
        self.assertEqual(plan["scene_count"], 8)
        by_id = {scene["scene_id"]: scene for scene in plan["scenes"]}
        self.assertEqual(by_id["AGR-03"]["status"], "资料就绪_待人工核验")
        self.assertGreaterEqual(by_id["AGR-03"]["candidate_signal_count"], 1)
        self.assertEqual(findings, before)


class AgricultureScenarioIntegrationTests(unittest.TestCase):
    def test_coverage_and_rewrite_ledger_disclose_agriculture_without_claiming_m3(self):
        from engine.methodology_coverage import build_methodology_coverage

        report = build_methodology_coverage(STATIC)
        self.assertEqual(report["version"], "1.6.0")
        self.assertEqual(report["inventory"]["rewritten_m25_scenarios"], 47)
        agriculture = next(row for row in report["industry_matrix"] if row["code"] == "A")
        self.assertEqual(agriculture["rewritten_m25_scenarios"], 8)
        self.assertEqual(agriculture["verified_specific_rules"], 0)
        self.assertIn("待脱敏真实样本验证", agriculture["state"])
        rewrite = report["candidate_governance"]["rewrite_program"]["summary"]
        self.assertEqual(rewrite["absorbed_into_scene_contract"], 140)
        self.assertEqual(rewrite["queued_not_rewritten"], 1580)
        self.assertEqual(rewrite["released_from_legacy_library"], 0)

    def test_api_frontend_and_cache_publish_guard_agriculture_contract(self):
        main_text = (ROOT / "main.py").read_text(encoding="utf-8")
        frontend = (STATIC / "js" / "tax-pipeline-pages.js").read_text(encoding="utf-8")
        index = (STATIC / "index.html").read_text(encoding="utf-8")

        self.assertIn('"agriculture_scenario_contracts": "agriculture_scenario_contracts.json"', main_text)
        self.assertIn("/api/methodology/assets/agriculture_scenario_contracts", frontend)
        self.assertIn("农林牧渔业真实场景五链配套重写", frontend)
        self.assertIn("农林牧渔业边界", frontend)
        self.assertIn("tax-pipeline-pages.js?v=2026080209", index)


if __name__ == "__main__":
    unittest.main()

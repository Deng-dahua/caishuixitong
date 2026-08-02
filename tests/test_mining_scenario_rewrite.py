from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class MiningScenarioContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(
            (STATIC / "mining_scenario_contracts.json").read_text(encoding="utf-8")
        )

    def test_eight_mining_scenes_have_complete_five_chain_contracts(self):
        scenes = self.payload["scenarios"]
        self.assertEqual(len(scenes), 8)
        self.assertEqual({scene["id"] for scene in scenes}, {f"MIN-{n:02d}" for n in range(1, 9)})
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
        self.assertEqual(no_direct_match, {"MIN-04", "MIN-06"})
        self.assertEqual(len(absorbed), 27)
        self.assertEqual(len(absorbed), len(set(absorbed)))
        legacy_rules = json.loads(
            (STATIC / "tax_risk_rules_local_export.json").read_text(encoding="utf-8")
        )
        self.assertTrue(set(absorbed).issubset({str(rule["id"]) for rule in legacy_rules}))

        earlier_ids = set()
        for path in STATIC.glob("*_scenario_contracts.json"):
            if path.name == "mining_scenario_contracts.json":
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            earlier_ids.update(
                legacy_id
                for scene in payload.get("scenarios", [])
                for legacy_id in scene.get("legacy_absorption", {}).get("legacy_rule_ids", [])
            )
        self.assertTrue(set(absorbed).isdisjoint(earlier_ids))

    def test_current_mining_sources_and_safety_boundaries_are_present(self):
        sources = {source["id"]: source for source in self.payload["official_sources"]}
        for source_id in (
            "SRC-MIN-MRL", "SRC-MIN-MRL-RULES", "SRC-MIN-RESOURCE-LAW",
            "SRC-MIN-RESOURCE-34", "SRC-MIN-RESOURCE-14", "SRC-MIN-RESOURCE-2025",
            "SRC-MIN-PROCEEDS-2023", "SRC-MIN-PROCEEDS-2026", "SRC-MIN-SAFETY",
        ):
            self.assertIn(source_id, sources)
            self.assertTrue(sources[source_id]["url"].startswith("https://"))
        referenced_sources = {
            source_id
            for scene in self.payload["scenarios"]
            for source_id in scene["policy_source_ids"]
        }
        self.assertTrue(referenced_sources.issubset(sources))
        self.assertIn("2026-08-01", sources["SRC-MIN-PROCEEDS-2026"]["effective_period"])
        forbidden = self.payload["common_contract"]["forbidden_outputs"]
        self.assertIn("以许可证产能直接推定实际开采量", forbidden)
        self.assertIn("忽略品位水分和计量不确定性", forbidden)
        self.assertIn("自动认定少缴资源税", forbidden)


class MiningScenarioPlannerTests(unittest.TestCase):
    def test_plan_routes_mining_resource_tax_and_preserves_findings(self):
        from engine.scenario_methodology import build_scenario_review_plan

        files = [
            {"type": "generic_data", "file": "采矿许可证矿区储量动用生产班报.xlsx"},
            {"type": "inventory", "file": "原矿选矿精矿地磅堆场台账.xlsx"},
            {"type": "contract", "file": "矿产品销售运杂费结算合同.xlsx"},
            {"type": "tax_return", "file": "资源税应税矿产品外购扣减申报表.xlsx"},
        ]
        findings = [{"type": "资源税原矿选矿销售额差异", "detail": "外购扣减和运杂费资料待核"}]
        before = copy.deepcopy(findings)
        plan = build_scenario_review_plan("B 采矿业", files, findings)

        self.assertTrue(plan["applicable"])
        self.assertEqual(plan["industry_code"], "B")
        self.assertEqual(plan["contract_asset"], "mining_scenario_contracts")
        self.assertEqual(plan["scene_count"], 8)
        by_id = {scene["scene_id"]: scene for scene in plan["scenes"]}
        self.assertEqual(by_id["MIN-03"]["status"], "资料就绪_待人工核验")
        self.assertGreaterEqual(by_id["MIN-03"]["candidate_signal_count"], 1)
        self.assertEqual(findings, before)


class MiningScenarioIntegrationTests(unittest.TestCase):
    def test_coverage_and_rewrite_ledger_disclose_mining_without_claiming_m3(self):
        from engine.methodology_coverage import build_methodology_coverage

        report = build_methodology_coverage(STATIC)
        self.assertEqual(report["version"], "1.7.0")
        self.assertEqual(report["inventory"]["rewritten_m25_scenarios"], 55)
        mining = next(row for row in report["industry_matrix"] if row["code"] == "B")
        self.assertEqual(mining["rewritten_m25_scenarios"], 8)
        self.assertEqual(mining["verified_specific_rules"], 0)
        self.assertIn("待脱敏真实样本验证", mining["state"])
        rewrite = report["candidate_governance"]["rewrite_program"]["summary"]
        self.assertEqual(rewrite["absorbed_into_scene_contract"], 167)
        self.assertEqual(rewrite["queued_not_rewritten"], 1553)
        self.assertEqual(rewrite["released_from_legacy_library"], 0)

    def test_api_frontend_and_cache_publish_guard_mining_contract(self):
        main_text = (ROOT / "main.py").read_text(encoding="utf-8")
        frontend = (STATIC / "js" / "tax-pipeline-pages.js").read_text(encoding="utf-8")
        index = (STATIC / "index.html").read_text(encoding="utf-8")

        self.assertIn('"mining_scenario_contracts": "mining_scenario_contracts.json"', main_text)
        self.assertIn("/api/methodology/assets/mining_scenario_contracts", frontend)
        self.assertIn("采矿业真实场景五链配套重写", frontend)
        self.assertIn("采矿业边界", frontend)
        self.assertIn("tax-pipeline-pages.js?v=2026080301", index)


if __name__ == "__main__":
    unittest.main()

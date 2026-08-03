from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class CanonicalMethodologyCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from engine.methodology_catalog import (
            SCENARIO_FILES,
            load_canonical_catalog,
            load_flat_analysis,
            load_flat_clues,
            load_flat_evidence,
            load_flat_rules,
            load_industry_review,
            load_reviewed_scenario_contracts,
            methodology_inventory,
        )

        cls.scenario_files = SCENARIO_FILES
        cls.catalog = load_canonical_catalog()
        cls.review = load_industry_review()
        cls.payloads = {
            code: load_reviewed_scenario_contracts(code) for code in SCENARIO_FILES
        }
        cls.scenarios = [
            scene
            for payload in cls.payloads.values()
            for scene in payload.get("scenarios", [])
        ]
        cls.rules = load_flat_rules()
        cls.clues = load_flat_clues()
        cls.evidence = load_flat_evidence()
        cls.analysis = load_flat_analysis()
        cls.inventory = methodology_inventory()

    def test_retired_assets_are_not_part_of_release(self):
        retired = (
            "tax_risk_rules_local_export.json",
            "cross_domain_clues.json",
            "cross_domain_evidence.json",
            "cross_domain_analysis.json",
        )
        for filename in retired:
            self.assertFalse((STATIC / filename).exists(), filename)
        self.assertFalse((ROOT / "engine" / "candidate_rule_governance.py").exists())

    def test_catalog_is_unique_complete_and_source_anchored(self):
        modules = self.catalog["modules"]
        raw_rules = [rule for module in modules for rule in module["rules"]]
        self.assertEqual(len(modules), 20)
        self.assertEqual(len(raw_rules), 67)
        self.assertEqual(len({module["id"] for module in modules}), len(modules))
        self.assertEqual(len({rule["id"] for rule in raw_rules}), len(raw_rules))

        source_ids = {source["id"] for source in self.catalog["official_sources"]}
        self.assertIn("SRC-PROCEDURE-52", source_ids)
        self.assertIn("SRC-VAT-LAW-2026", source_ids)
        self.assertIn("SRC-EINVOICE", source_ids)
        for source in self.catalog["official_sources"]:
            self.assertTrue(source["url"].startswith("https://"))
        for module in modules:
            self.assertTrue(module["activation_gate"])
            self.assertTrue(module["clue_paths"])
            self.assertTrue(module["evidence_plan"]["supporting"])
            self.assertTrue(module["evidence_plan"]["opposing"])
            self.assertTrue(module["evidence_plan"]["insufficient_when"])
            self.assertTrue(module["analysis_tests"])
            self.assertTrue(module["validation_cases"])
            self.assertTrue(set(module["source_refs"]).issubset(source_ids))
            for rule in module["rules"]:
                self.assertRegex(rule["id"], r"^[A-Z]+-\d{2}-R\d{2}$")
                self.assertTrue(rule["fact_hypothesis"])
                self.assertTrue(rule["required_fields"])
                self.assertIn("excludes", rule)

    def test_flat_assets_are_integrated_review_contracts(self):
        self.assertEqual(len(self.rules), 67)
        self.assertEqual(len(self.clues), 27)
        self.assertEqual(len(self.evidence), 20)
        self.assertEqual(len(self.analysis), 20)
        for rule in self.rules:
            self.assertEqual(rule["type"], "authoritative_review_contract")
            self.assertIsNone(rule["threshold"])
            self.assertTrue(rule["human_review_required"])
            self.assertFalse(rule["automatic_determination_allowed"])
            combined = json.dumps(rule, ensure_ascii=False)
            for unsafe in ("认定偷税", "构成虚开", "建议处罚", "移送公安", "定性成立"):
                self.assertNotIn(unsafe, combined)

    def test_industry_counts_follow_business_need_not_a_template(self):
        expected = {
            "A": 11,
            "B": 9,
            "C": 10,
            "E": 9,
            "F": 9,
            "K": 10,
            "OVERLAY-PLATFORM": 11,
        }
        self.assertEqual(self.inventory["industry_scenario_counts"], expected)
        self.assertEqual(self.inventory["industry_scenarios"], 69)
        self.assertEqual(self.inventory["clue_depths"], [4, 5, 6, 7])
        self.assertEqual(self.inventory["validation_depths"], [3, 4, 5, 6])
        self.assertGreater(len({len(s["analysis_chain"]["reasoning"]) for s in self.scenarios}), 1)

    def test_every_scene_has_a_complete_five_chain_contract(self):
        self.assertEqual(len(self.scenarios), 69)
        for scene in self.scenarios:
            revision = scene.get("methodology_revision") or {}
            self.assertTrue(revision.get("depth_rationale"), scene.get("id"))
            self.assertTrue((scene.get("doubt") or {}).get("target_fact"), scene.get("id"))
            self.assertTrue((scene.get("clue_chain") or {}).get("steps"), scene.get("id"))
            evidence = scene.get("evidence_chain") or {}
            self.assertTrue(evidence.get("supporting_sources"), scene.get("id"))
            self.assertTrue(evidence.get("opposing_sources"), scene.get("id"))
            self.assertTrue((scene.get("analysis_chain") or {}).get("reasoning"), scene.get("id"))
            self.assertTrue((scene.get("domain_collaboration") or {}).get("lead"), scene.get("id"))
            self.assertTrue(scene.get("validation_cases"), scene.get("id"))
            self.assertTrue((scene.get("report_contract") or {}).get("forbidden"), scene.get("id"))
            encoded = json.dumps(scene, ensure_ascii=False)
            self.assertNotIn("legacy_absorption", encoded)
            self.assertNotIn("已吸收", encoded)

    def test_review_reassesses_every_existing_scene_and_adds_real_gaps(self):
        self.assertEqual(len(self.review["review_addenda"]), 55)
        self.assertEqual(len(self.review["additional_scenario_specs"]), 14)
        self.assertEqual(
            len({item["scene_id"] for item in self.review["review_addenda"]}),
            55,
        )
        self.assertEqual(
            len({item["id"] for item in self.review["additional_scenario_specs"]}),
            14,
        )
        for item in self.review["additional_scenario_specs"]:
            self.assertTrue(item["reason"])
            self.assertGreaterEqual(len(item["clue_stages"]), 5)
            self.assertTrue(item["supporting"])
            self.assertTrue(item["opposing"])
            self.assertTrue(item["analysis"])
            self.assertGreaterEqual(len(item["cases"]), 4)

    def test_runtime_and_frontend_use_only_the_current_catalog(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        pipeline = (ROOT / "engine" / "pipeline.py").read_text(encoding="utf-8")
        page = (STATIC / "js" / "tax-risk-rules.js").read_text(encoding="utf-8")
        scenarios = (STATIC / "js" / "tax-pipeline-pages.js").read_text(encoding="utf-8")
        for retired_name in (
            "tax_risk_rules_local_export.json",
            "cross_domain_clues.json",
            "cross_domain_evidence.json",
            "cross_domain_analysis.json",
        ):
            self.assertNotIn(retired_name, main)
            self.assertNotIn(retired_name, pipeline)
        self.assertIn("load_flat_rules", main)
        self.assertIn("canonical_catalog", main)
        self.assertIn("canonical_catalog", page)
        self.assertNotIn("1720条候选规则重写迁移账册", scenarios)
        self.assertNotIn("legacy_absorption", scenarios)

    def test_scenario_plan_uses_observed_signals_only_for_ordering(self):
        source = (ROOT / "engine" / "scenario_methodology.py").read_text(encoding="utf-8")
        self.assertIn("observed_signal_count", source)
        self.assertIn("观察信号只用于确定核验顺序", source)
        self.assertNotIn("candidate_signal_count", source)


if __name__ == "__main__":
    unittest.main()

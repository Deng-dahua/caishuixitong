from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class CandidateRuleRewriteLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = json.loads(
            (STATIC / "tax_risk_rules_local_export.json").read_text(encoding="utf-8")
        )
        cls.contracts = json.loads(
            (STATIC / "wholesale_retail_scenario_contracts.json").read_text(encoding="utf-8")
        )
        cls.platform_contracts = json.loads(
            (STATIC / "platform_scenario_contracts.json").read_text(encoding="utf-8")
        )
        cls.agriculture_contracts = json.loads(
            (STATIC / "agriculture_scenario_contracts.json").read_text(encoding="utf-8")
        )

    def test_all_legacy_rules_are_preserved_and_queued_not_released(self):
        from engine.candidate_rule_governance import build_absorption_map, build_candidate_rewrite_ledger

        absorption_map = build_absorption_map([
            self.contracts, self.platform_contracts, self.agriculture_contracts
        ])
        ledger = build_candidate_rewrite_ledger(
            self.rules, offset=0, limit=200, absorption_map=absorption_map
        )
        summary = ledger["summary"]
        self.assertEqual(summary["legacy_rules"], 1720)
        self.assertEqual(summary["legacy_rules_preserved"], 1720)
        self.assertEqual(summary["absorbed_into_scene_contract"], 140)
        self.assertEqual(summary["queued_not_rewritten"], 1580)
        self.assertEqual(summary["released_from_legacy_library"], 0)
        self.assertEqual(ledger["returned"], 200)
        self.assertTrue(ledger["has_more"])
        self.assertEqual(len({row["rewrite_id"] for row in ledger["records"]}), 200)
        self.assertTrue(all(row["legacy_preserved"] for row in ledger["records"]))
        self.assertTrue(all(row["release_status"] == "candidate_not_executable" for row in ledger["records"]))

    def test_rewrite_program_is_scenario_based_and_not_one_to_one(self):
        from engine.candidate_rule_governance import build_absorption_map, build_candidate_governance

        governance = build_candidate_governance(
            self.rules,
            absorption_map=build_absorption_map([
                self.contracts, self.platform_contracts, self.agriculture_contracts
            ]),
        )
        program = governance["rewrite_program"]
        self.assertEqual([phase["id"] for phase in program["phases"]], ["G0", "G1", "G2", "G3", "G4", "G5"])
        self.assertIn("不追求与旧库一一对应", program["positioning"])
        self.assertTrue(any("多条旧规则可以归并" in item for item in program["invariants"]))
        self.assertEqual(program["summary"]["absorbed_into_scene_contract"], 140)
        self.assertEqual(program["summary"]["released_from_legacy_library"], 0)

    def test_read_only_api_and_frontend_expose_paginated_ledger(self):
        main_text = (ROOT / "main.py").read_text(encoding="utf-8")
        frontend = (STATIC / "js" / "tax-pipeline-pages.js").read_text(encoding="utf-8")
        self.assertIn('@app.get("/api/methodology/rewrite-ledger")', main_text)
        self.assertIn("build_candidate_rewrite_ledger", main_text)
        self.assertIn("/api/methodology/rewrite-ledger?offset=0&limit=40", frontend)
        self.assertIn("1720条候选规则重写迁移账册", frontend)
        self.assertIn("已吸收进场景未放行", frontend)
        self.assertIn("旧库直接放行", frontend)


if __name__ == "__main__":
    unittest.main()

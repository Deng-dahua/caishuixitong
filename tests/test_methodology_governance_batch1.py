from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class CandidateGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = json.loads(
            (STATIC / "tax_risk_rules_local_export.json").read_text(encoding="utf-8-sig")
        )

    def test_all_legacy_rules_are_candidates_with_truthful_governance(self):
        from engine.candidate_rule_governance import build_candidate_governance

        report = build_candidate_governance(self.rules)
        summary = report["summary"]
        self.assertEqual(summary["candidate_rules"], 1720)
        self.assertEqual(summary["official_provenance_recorded"], 0)
        self.assertEqual(summary["source_missing"], 1541)
        self.assertEqual(summary["author_or_model_only"], 179)
        self.assertEqual(summary["production_executable_rules_in_candidate_library"], 0)
        self.assertEqual(summary["candidate_field_contracts_present"], 0)
        self.assertEqual(summary["raw_rules_requiring_language_neutralisation"], 1720)
        self.assertEqual(summary["normalised_duplicate_rule_count"], 13)
        self.assertGreaterEqual(len(report["release_gate"]), 6)

    def test_read_only_rule_response_is_annotated_and_neutralised(self):
        from engine.methodology_assets import prepare_methodology_asset

        prepared = prepare_methodology_asset("rules", self.rules)
        self.assertEqual(len(prepared), len(self.rules))
        self.assertTrue(all(rule["_governance"]["release_status"] == "candidate_not_executable" for rule in prepared))
        text = json.dumps(prepared, ensure_ascii=False)
        for unsafe in ("铁证", "自动立案", "移送公安", "定性成立", "认定为偷税"):
            self.assertNotIn(unsafe, text)


class IndustryPackTests(unittest.TestCase):
    def test_priority_packs_have_field_contracts_and_stop_conditions(self):
        payload = json.loads(
            (STATIC / "industry_methodology_packs.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(payload["packs"]), 5)
        self.assertEqual(sum(len(pack["scenarios"]) for pack in payload["packs"]), 39)
        self.assertEqual(
            {pack["industry_code"] for pack in payload["packs"]},
            {"C", "E", "F", "K", "OVERLAY-PLATFORM"},
        )
        for pack in payload["packs"]:
            self.assertEqual(pack["maturity"], "M2_scene_defined")
            self.assertEqual(pack["scene_count"], len(pack["scenarios"]))
            self.assertGreaterEqual(len(pack["official_sources"]), 2)
            self.assertTrue(all(source["url"].startswith("https://") for source in pack["official_sources"]))
            for scene in pack["scenarios"]:
                self.assertEqual(scene["maturity"], "M2_scene_defined")
                self.assertGreaterEqual(len(scene["required_sources"]), 4)
                self.assertGreaterEqual(len(scene["field_contract"]), 6)
                self.assertGreaterEqual(len(scene["investigation_path"]), 4)
                self.assertGreaterEqual(len(scene["opposing_evidence"]), 4)
                self.assertGreaterEqual(len(scene["stop_conditions"]), 3)

    def test_coverage_exposes_staged_scenarios_without_claiming_execution(self):
        from engine.methodology_coverage import build_methodology_coverage

        report = build_methodology_coverage(STATIC)
        self.assertEqual(report["inventory"]["priority_industry_packs"], 5)
        self.assertEqual(report["inventory"]["staged_m2_industry_scenarios"], 39)
        matrix = {item["code"]: item for item in report["industry_matrix"]}
        self.assertEqual(matrix["C"]["staged_m2_scenarios"], 8)
        self.assertEqual(matrix["E"]["staged_m2_scenarios"], 8)
        self.assertEqual(matrix["F"]["staged_m2_scenarios"], 7)
        self.assertEqual(matrix["K"]["staged_m2_scenarios"], 8)
        self.assertTrue(all(item["verified_specific_rules"] == 0 for item in matrix.values()))


class GovernanceControlTests(unittest.TestCase):
    def test_analysis_cannot_open_an_enforcement_case(self):
        from engine.enforcement_procedure import (
            EnforcementState,
            _active_procedures,
            get_or_create_procedure,
            on_finding_confirmed,
        )

        company_id = "governance-test-company"
        _active_procedures.pop(company_id, None)
        self.assertIsNone(on_finding_confirmed(company_id, "finding-1", "多源材料待人工复核"))
        self.assertEqual(get_or_create_procedure(company_id).current_state, EnforcementState.IDLE)
        _active_procedures.pop(company_id, None)

    def test_legacy_model_promotion_endpoints_are_disabled(self):
        main_text = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("candidate_review_required", main_text)
        self.assertIn("disabled_by_methodology_governance", main_text)
        self.assertIn("retired_from_product", main_text)
        self.assertIn("禁止用更新时间戳冒充政策核验", main_text)

    def test_candidate_chains_and_private_writing_standard_are_not_runtime_capabilities(self):
        from engine.memory import TAX_BURDEN_RULES

        pipeline_text = (ROOT / "engine" / "pipeline.py").read_text(encoding="utf-8")
        self.assertIn("LEGACY_CANDIDATE_CHAIN_EXECUTION_ENABLED = False", pipeline_text)
        self.assertNotIn('domain_results.append({"domain": "跨域线索链"', pipeline_text)
        self.assertNotIn("rule_precise_writing", TAX_BURDEN_RULES)

    def test_frontend_uses_guarded_chain_assets_and_industry_packs(self):
        rule_ui = (STATIC / "js" / "tax-risk-rules.js").read_text(encoding="utf-8")
        method_ui = (STATIC / "js" / "tax-pipeline-pages.js").read_text(encoding="utf-8")
        self.assertIn("/api/methodology/assets/' + assetName", rule_ui)
        self.assertNotIn("fetch('/static/' + fname", rule_ui)
        self.assertIn("/api/methodology/assets/industry_packs", method_ui)
        self.assertIn("候选规则治理实况", method_ui)
        self.assertIn("第一批重点行业专项包", method_ui)


if __name__ == "__main__":
    unittest.main()

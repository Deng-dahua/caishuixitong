from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VerifiedRuleEngineTests(unittest.TestCase):
    def test_bank_invoice_gap_is_reproducible_clue_not_conclusion(self):
        from engine.verified_rule_engine import run_verified_rules

        result = run_verified_rules({
            "bank_txs": [
                {"date": "2026-01-10", "credit": 300000},
                {"date": "2026-02-10", "credit": 400000},
            ],
            "sal_invs": [
                {"date": "2026-01-12", "total": 100000},
                {"date": "2026-02-12", "total": 150000},
            ],
        })
        finding = next(item for item in result["findings"] if item["rule_id"] == "VR001")
        self.assertEqual(finding["finding_status"], "clue_pending_investigation")
        self.assertEqual(finding["independent_source_count"], 2)
        self.assertTrue(finding["required_human_review"])
        combined = json.dumps(finding, ensure_ascii=False)
        for unsafe in ("认定偷税", "构成虚开", "建议处罚", "移送公安", "定性成立"):
            self.assertNotIn(unsafe, combined)

    def test_duplicate_invoice_is_data_quality_limitation(self):
        from engine.verified_rule_engine import run_verified_rules

        result = run_verified_rules({
            "sal_invs": [
                {"inv_code": "A", "inv_no": "1001", "amount": 10},
                {"inv_code": "A", "inv_no": "1001", "amount": 10},
            ]
        })
        finding = next(item for item in result["findings"] if item["rule_id"] == "VR003")
        self.assertEqual(finding["finding_status"], "data_quality_limitation")
        self.assertEqual(finding["level"], "信息")
        self.assertIn("重复上传", finding["limitations"])

    def test_missing_sources_do_not_trigger(self):
        from engine.verified_rule_engine import run_verified_rules

        result = run_verified_rules({})
        self.assertEqual(result["findings"], [])
        self.assertTrue(all(item["status"] == "not_run_missing_data" for item in result["executions"]))

    def test_invoice_arithmetic_check_needs_comparable_rows(self):
        from engine.verified_rule_engine import run_verified_rules

        result = run_verified_rules({
            "sal_invs": [
                {"inv_no": "1", "amount": 100, "tax": 13, "total": 150},
                {"inv_no": "2", "amount": 200, "tax": 26, "total": 226},
                {"inv_no": "3", "amount": 300, "tax": 39, "total": 339},
            ]
        })
        finding = next(item for item in result["findings"] if item["rule_id"] == "VR010")
        self.assertEqual(finding["finding_status"], "data_quality_limitation")
        self.assertEqual(finding["observed_metrics"]["comparable_count"], 3)


class CoverageGovernanceTests(unittest.TestCase):
    def test_coverage_report_separates_candidates_from_verified_rules(self):
        from engine.methodology_coverage import build_methodology_coverage

        report = build_methodology_coverage(ROOT / "static")
        inventory = report["inventory"]
        self.assertEqual(inventory["candidate_rules"], 1720)
        self.assertEqual(inventory["verified_executable_rules"], 13)
        self.assertGreaterEqual(inventory["candidate_rules_missing_provenance"], 1500)
        self.assertGreaterEqual(inventory["dominant_analysis_structure_count"], 1600)
        self.assertEqual(len(report["industry_matrix"]), 20)
        self.assertEqual(len(report["industry_profiles"]), 20)
        self.assertGreaterEqual(len(report["data_capability_matrix"]), 12)
        self.assertTrue(any(item["code"] == "T" for item in report["industry_matrix"]))
        self.assertTrue(all(len(item["cross_checks"]) >= 3 for item in report["industry_profiles"]))
        self.assertTrue(all(item["verified_specific_rules"] == 0 for item in report["industry_matrix"]))
        self.assertTrue(any(gap["priority"] == "P0" for gap in report["gap_register"]))

    def test_chain_playbooks_cover_investigation_evidence_and_analysis(self):
        payload = json.loads(
            (ROOT / "static" / "methodology_chain_playbooks.json").read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(len(payload["playbooks"]), 13)
        for playbook in payload["playbooks"]:
            self.assertGreaterEqual(len(playbook["investigation_sequence"]), 5)
            self.assertGreaterEqual(len(playbook["evidence_minimum"]), 4)
            self.assertGreaterEqual(len(playbook["analysis_questions"]), 4)
            self.assertGreaterEqual(len(playbook["alternative_explanations"]), 4)
            self.assertGreaterEqual(len(playbook["stop_conditions"]), 3)

    def test_text_mentions_never_create_evidence_grade(self):
        from engine.rule_gate import auto_grade_determination, scan_extended_thresholds

        finding = {"evidence": "银行、发票、合同、申报资料均应核验"}
        auto_grade_determination([finding])
        self.assertEqual(finding["evidence_grade"], "来源未核验")
        self.assertEqual(finding["independent_source_count"], 0)
        rule = {"id": 1, "threshold": "差额>10%且金额>5万"}
        self.assertEqual(scan_extended_thresholds({}, [rule], {}), [])


if __name__ == "__main__":
    unittest.main()

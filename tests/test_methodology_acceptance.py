from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MethodologyAcceptanceTests(unittest.TestCase):
    def test_evidence_states_never_enable_automatic_determination(self):
        from engine.methodology_acceptance import (
            EVIDENCE_STATE_OUTCOMES,
            evaluate_acceptance_case,
        )

        for state, expected in EVIDENCE_STATE_OUTCOMES.items():
            result = evaluate_acceptance_case({
                "evidence_state": state,
                "expected": expected,
                "facts": "可定位到具体主体、事项和期间的验收事实",
                "required_assertions": ["主体", "事项", "期间", "人工复核"],
            })
            self.assertTrue(result["passed"], state)
            self.assertTrue(result["required_human_review"], state)
            self.assertFalse(result["automatic_determination_allowed"], state)

    def test_report_gate_blocks_malformed_legal_reference(self):
        from engine.report_standards import apply_report_standards

        report = {
            "target_entity": {"name": "脱敏测试企业"},
            "_methodology_applied": {"portfolio_acceptance_status": "passed"},
            "all_findings": [{
                "fact_id": "CASE-001",
                "type": "待核事实",
                "detail": "原始资料存在待核差异",
                "policy_ref": "税收征收管理法第61720条",
                "tax_impact": "依据第61720条直接处罚",
            }],
        }
        apply_report_standards(report)
        finding = report["all_findings"][0]
        self.assertNotIn("policy_ref", finding)
        self.assertNotIn("law_ref", finding)
        self.assertNotIn("1720", finding["tax_impact"])
        self.assertEqual(report["_blocked_legal_reference_count"], 1)
        self.assertEqual(report["release_status"], "草稿_待人工复核")
        self.assertIn("RQ4", report["_report_standards_check"]["passed_ids"])

    def test_supported_fact_requires_evidence_rebuttal_and_amount_workpaper(self):
        from engine.report_standards import apply_report_standards

        report = {
            "target_entity": {"name": "脱敏测试企业"},
            "_methodology_applied": {"portfolio_acceptance_status": "passed"},
            "all_findings": [{
                "fact_id": "CASE-002",
                "type": "收入期间待核",
                "conclusion_state": "事实充分支持_待审理",
                "policy_ref": "按事实期间取得的官方有效依据",
                "tax_impact": "待复算",
            }],
        }
        apply_report_standards(report)
        failed = set(report["_report_standards_check"]["failed_ids"])
        self.assertTrue({"RQ6", "RQ7"}.issubset(failed))
        self.assertEqual(report["release_status"], "草稿_待人工复核")

    def test_one_click_pipeline_has_no_retired_threshold_rule_scan(self):
        source = (ROOT / "engine" / "pipeline.py").read_text(encoding="utf-8")
        self.assertNotIn("from engine.threshold_scanner import", source)
        self.assertNotIn('"_rule_match_mode": "threshold_scan"', source)
        self.assertNotIn("threshold主动扫描", source)


if __name__ == "__main__":
    unittest.main()


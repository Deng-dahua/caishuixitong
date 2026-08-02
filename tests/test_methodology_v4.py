from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MethodologyFrameworkTests(unittest.TestCase):
    def test_framework_has_real_workflow_and_broad_coverage(self):
        framework = json.loads(
            (ROOT / "static" / "methodology_framework.json").read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(len(framework["workflow"]), 10)
        self.assertGreaterEqual(len(framework["business_domains"]), 14)
        self.assertGreaterEqual(len(framework["industry_coverage"]), 20)
        self.assertGreaterEqual(len(framework["tax_coverage"]), 6)
        self.assertGreaterEqual(len(framework["data_sources"]), 7)
        scenario_count = sum(
            len(group["paths"]) for group in framework["cross_domain_scenarios"]
        )
        self.assertGreaterEqual(scenario_count, 35)
        self.assertIn("not_claimed", framework["public_capability_boundary"])
        evidence_rules = "".join(framework["evidence_model"]["rules"])
        analysis_fields = framework["chain_contracts"]["analysis"]["required_fields"]
        self.assertIn("支持证据和反向证据", evidence_rules)
        self.assertIn("竞争性解释", analysis_fields)

    def test_every_rule_has_type_safe_three_chain_assets(self):
        rules = json.loads(
            (ROOT / "static" / "tax_risk_rules_local_export.json").read_text(encoding="utf-8-sig")
        )
        clue = json.loads(
            (ROOT / "static" / "cross_domain_clues.json").read_text(encoding="utf-8-sig")
        )
        evidence_payload = json.loads(
            (ROOT / "static" / "cross_domain_evidence.json").read_text(encoding="utf-8-sig")
        )
        analysis_payload = json.loads(
            (ROOT / "static" / "cross_domain_analysis.json").read_text(encoding="utf-8-sig")
        )
        evidence = evidence_payload["evidence_chains"]
        analysis = analysis_payload["analysis_chains"]
        expected_ids = {int(rule["id"]) for rule in rules}
        self.assertEqual(len(expected_ids), 1720)
        for chains in (clue, evidence, analysis):
            self.assertEqual({int(chain["rule_id"]) for chain in chains}, expected_ids)
            self.assertTrue(all(chain.get("steps") for chain in chains))
            self.assertTrue(all(
                step.get("op") in {"aggregate", "compare", "query", "conclude"}
                for chain in chains for step in chain["steps"]
            ))
            self.assertTrue(all(
                any(step.get("op") == "conclude" for step in chain["steps"])
                for chain in chains
            ))

    def test_loader_accepts_text_and_matches_official_sources(self):
        from engine.methodology_loader import get_relevant_laws, match_methodology

        methods = match_methodology("银行收款与销项发票、申报收入存在差异")
        laws = get_relevant_laws("增值税发票和收入完整性待核事项")
        method_ids = {method.get("id") for method in methods}
        self.assertIn("D06", method_ids)
        self.assertIn("D07", method_ids)
        self.assertTrue(any("税务稽查案件办理程序" in law["name"] for law in laws))
        self.assertTrue(any("增值税" in law["name"] for law in laws))


class ChainExecutionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.clue = {
            "id": "clue-1", "rule_id": 1,
            "steps": [
                {"step": 1, "op": "query", "source": "bank_txs", "filters": {"amount": {">": 0}}, "output": "clue_rows"},
                {"step": 2, "op": "conclude", "conditions": [
                    {"if": "clue_rows exists", "conclusion": "异常线索", "detail": "需要核验"}
                ], "output": "findings_clue"},
            ],
        }
        self.evidence = {
            "id": "evid-1", "rule_id": 1, "min_evidence": 2,
            "steps": [
                {"step": 1, "op": "query", "source": "bank_txs", "filters": {"amount": {">": 0}}, "output": "bank_rows"},
                {"step": 2, "op": "query", "source": "sal_invs", "filters": {"amount": {">": 0}}, "output": "invoice_rows"},
                {"step": 3, "op": "conclude", "conditions": [
                    {"if": "bank_rows exists", "conclusion": "银行侧异常", "detail": "收款记录需要复核。"},
                    {"if": "invoice_rows exists", "conclusion": "发票侧异常", "detail": "开票记录需要复核。"}
                ], "output": "findings_evidence"},
            ],
        }
        self.analysis = {
            "id": "alc-1", "rule_id": 1,
            "steps": [
                {"step": 1, "op": "conclude", "conditions": [
                    {"if": "bank_rows exists", "allow_plain_exists": True, "conclusion": "综合定性成立", "detail": "构成偷税，移送公安。"}
                ], "output": "findings_analysis"},
            ],
        }

    def test_chain_index_is_type_isolated(self):
        from engine.chain_executor import _build_chain_index, _find_chain

        _build_chain_index([self.clue], [self.evidence], [self.analysis])
        self.assertEqual(_find_chain([self.clue], 1, "clue")["id"], "clue-1")
        self.assertEqual(_find_chain([self.evidence], 1, "evidence")["id"], "evid-1")
        self.assertEqual(_find_chain([self.analysis], 1, "analysis")["id"], "alc-1")

    def test_evidence_gate_blocks_analysis_when_sources_are_not_independent(self):
        from engine.chain_executor import _build_chain_index, run_chains_for_rule

        _build_chain_index([self.clue], [self.evidence], [self.analysis])
        result = run_chains_for_rule(
            1, [self.clue], [self.evidence], [self.analysis],
            {"bank_txs": [{"amount": 1}], "sal_invs": []},
        )
        self.assertEqual(result["evidence"]["status"], "single_source_or_insufficient")
        self.assertEqual(result["evidence"]["evidence_dimension_count"], 1)
        self.assertEqual(result["evidence"]["independent_source_count"], 1)
        self.assertEqual(result["analysis"]["status"], "blocked_by_evidence")
        self.assertEqual(result["analysis"]["findings"], [])

    def test_two_sources_allow_review_but_never_automatic_legal_conclusion(self):
        from engine.chain_executor import _build_chain_index, run_chains_for_rule

        _build_chain_index([self.clue], [self.evidence], [self.analysis])
        result = run_chains_for_rule(
            1, [self.clue], [self.evidence], [self.analysis],
            {"bank_txs": [{"amount": 1}], "sal_invs": [{"amount": 1}]},
        )
        self.assertTrue(result["evidence"]["ready_for_analysis"])
        self.assertEqual(result["evidence"]["evidence_dimension_count"], 2)
        self.assertEqual(result["evidence"]["independent_source_count"], 2)
        self.assertEqual(result["analysis"]["status"], "ready_for_human_review")
        combined = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("定性成立", combined)
        self.assertNotIn("认定为偷税", combined)
        self.assertNotIn("移送公安", combined)
        for finding in result["analysis"]["findings"]:
            self.assertTrue(finding["required_human_review"])
            self.assertEqual(finding["conclusion_scope"], "screening_and_review_only")

    def test_methodology_guard_changes_missing_data_to_limitation(self):
        from engine.methodology_guardrails import review_finding

        finding = review_finding({
            "type": "缺少银行流水",
            "level": "极高风险",
            "score": 9,
            "detail": "资料不足，建议追缴并处以罚款。",
        })
        self.assertEqual(finding["level"], "信息")
        self.assertLessEqual(finding["score"], 2)
        self.assertEqual(finding["finding_status"], "insufficient_data")
        self.assertNotIn("处以罚款", finding["detail"])

    def test_procedure_and_privacy_commands_are_scoped(self):
        from engine.methodology_guardrails import neutralise_methodology_text

        raw = (
            "突击检查，隔离询问并封存手机和电脑防止串供；"
            "调取实际控制人全部银行账户流水。"
        )
        safe = neutralise_methodology_text(raw)
        for unsafe in ("突击检查", "隔离询问", "封存手机", "全部银行账户流水"):
            self.assertNotIn(unsafe, safe)
        self.assertIn("法定程序", safe)
        self.assertIn("特定账户、期间和交易资料", safe)


class FrontendMethodologyAlignmentTests(unittest.TestCase):
    def test_frontend_uses_shared_framework(self):
        source = (ROOT / "static" / "js" / "tax-pipeline-pages.js").read_text(
            encoding="utf-8"
        )
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("/api/methodology/assets/framework", source)
        self.assertIn("十四个专业业务域", source)
        self.assertIn("二十类行业大类与专项业务场景", source)
        self.assertIn("十一环节作业规程与强制停点", source)
        self.assertIn('"framework": "methodology_framework.json"', main)
        self.assertIn("prepare_methodology_asset", main)

    def test_methodology_guard_is_mandatory_before_report_publication(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        pipeline = main[
            main.index("def _execute_tax_risk_analysis"):
            main.index("def _analysis_progress")
        ]
        guard_call = pipeline.index("_apply_methodology_stage(report_data)")
        report_call = pipeline.index("_apply_report_compilation_stage(report_data)")
        persist_call = pipeline.index("_persist_one_click_result(company_id, result)")
        self.assertLess(guard_call, report_call)
        self.assertLess(report_call, persist_call)
        self.assertNotIn('"methodology_enrichment"] = {\n                "status": "degraded"', pipeline)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class BusinessApiAlignmentTests(unittest.TestCase):
    def test_one_click_analysis_uses_one_ordered_backend_flow(self):
        root = Path(__file__).resolve().parents[1]
        main_source = (root / "main.py").read_text(encoding="utf-8")
        pipeline_source = (root / "engine" / "pipeline.py").read_text(
            encoding="utf-8"
        )

        unified_start = main_source.index(
            "def _execute_tax_risk_analysis(company_id, db, progress_callback=None):"
        )
        unified_end = main_source.index(
            "\ndef _analysis_progress", unified_start
        )
        unified = main_source[unified_start:unified_end]
        ordered_calls = (
            "result = _run_analyze(",
            "_inject_agi_into_report(report_data, company_id)",
            "_apply_engine_hub_stage(",
            "_apply_methodology_stage(report_data)",
            "_apply_report_compilation_stage(report_data)",
            "_persist_one_click_result(company_id, result)",
        )
        positions = [unified.index(call) for call in ordered_calls]
        self.assertEqual(positions, sorted(positions))

        worker_start = main_source.index(
            "def _run_analysis_thread(task_id, company_id, user_id):"
        )
        worker_end = main_source.index(
            '\n@app.post("/api/tax-risk-docs/analyze-start")', worker_start
        )
        worker = main_source[worker_start:worker_end]
        self.assertIn("set_current_user_id(user_id)", worker)
        self.assertIn("_execute_tax_risk_analysis(", worker)
        self.assertNotIn("result = _run_analyze(", worker)
        self.assertNotIn("_append_analysis_history(", worker)

        sync_start = main_source.index(
            '\n@app.post("/api/tax-risk-docs/analyze")'
        )
        sync_end = main_source.index(
            "\ndef _inject_agi_into_report", sync_start
        )
        sync_endpoint = main_source[sync_start:sync_end]
        self.assertIn(
            "return _execute_tax_risk_analysis(company_id, db)",
            sync_endpoint,
        )
        self.assertNotIn("_run_analyze(company_id, db)", sync_endpoint)
        self.assertNotIn("apply_report_standards", sync_endpoint)

        self.assertNotIn("_last_analysis_cache", pipeline_source)
        self.assertIn('"user_id": request_user_id', main_source)
        self.assertIn(
            'requested_task.get("user_id") != session.user_id',
            main_source,
        )

    def test_one_click_flow_runs_each_required_stage_once(self):
        root = Path(__file__).resolve().parents[1]
        script = textwrap.dedent(
            """
            from unittest.mock import patch

            import main

            calls = []
            raw_result = {
                "ok": True,
                "report": {
                    "all_findings": [],
                    "pipeline_log": [],
                    "comprehensive": {},
                },
            }

            def run_engine(*args, **kwargs):
                calls.append("analysis")
                return raw_result

            def inject(report, company_id):
                calls.append("engine_report")
                return report

            def scenario_boundary(report):
                calls.append("scenario_boundary")
                return {"status": "completed"}

            def engine_hub(report, result):
                calls.append("engine_hub")
                return {"status": "completed"}

            def methodology(report):
                calls.append("methodology")
                return {"status": "completed"}

            def compilation(report):
                calls.append("report_compilation")
                report["compiled"] = True
                return report, {"status": "completed"}

            def persist(company_id, result):
                calls.append("persist")

            with patch(
                "engine.self_learning._load_correction_rules",
                return_value=[],
            ), patch(
                "engine.self_learning.apply_cross_company_synthesis",
                return_value={},
            ), patch.object(
                main, "_run_analyze", side_effect=run_engine
            ), patch.object(
                main, "_enforce_scenario_execution_boundary", side_effect=scenario_boundary
            ), patch.object(
                main, "_inject_agi_into_report", side_effect=inject
            ), patch.object(
                main, "_apply_engine_hub_stage", side_effect=engine_hub
            ), patch.object(
                main, "_apply_methodology_stage", side_effect=methodology
            ), patch.object(
                main,
                "_apply_report_compilation_stage",
                side_effect=compilation,
            ), patch.object(
                main, "_persist_one_click_result", side_effect=persist
            ):
                result = main._execute_tax_risk_analysis(7, object())

            assert result["ok"] is True
            assert result["report"]["compiled"] is True
            assert result["report"]["_one_click_pipeline"]["status"] == "completed"
            assert calls == [
                "analysis",
                "scenario_boundary",
                "engine_report",
                "engine_hub",
                "methodology",
                "report_compilation",
                "persist",
            ], calls

            calls.clear()
            with patch(
                "engine.self_learning._load_correction_rules",
                return_value=[],
            ), patch(
                "engine.self_learning.apply_cross_company_synthesis",
                return_value={},
            ), patch.object(
                main, "_run_analyze", return_value=raw_result
            ), patch.object(
                main, "_enforce_scenario_execution_boundary", side_effect=scenario_boundary
            ), patch.object(
                main, "_inject_agi_into_report", side_effect=inject
            ), patch.object(
                main, "_apply_engine_hub_stage", side_effect=engine_hub
            ), patch.object(
                main, "_apply_methodology_stage", side_effect=methodology
            ), patch.object(
                main,
                "_apply_report_compilation_stage",
                side_effect=RuntimeError("quality gate failed"),
            ), patch.object(
                main, "_persist_one_click_result", side_effect=persist
            ):
                failed = main._execute_tax_risk_analysis(7, object())

            assert failed["ok"] is False
            assert "quality gate failed" in failed["message"]
            assert "persist" not in calls
            """
        )
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment.update(
                {
                    "APP_DATA_DIR": directory,
                    "APP_COOKIE_SECURE": "0",
                    "APP_ALLOWED_ORIGINS": "http://testserver",
                    "APP_ADMIN_USERNAME": "businessadmin",
                    "APP_ADMIN_PASSWORD": "Business-Test-2026!",
                    "APP_LLM_MASTER_KEY": base64.urlsafe_b64encode(
                        bytes(range(32))
                    ).decode("ascii"),
                }
            )
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=120,
            )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_report_loader_runs_inside_its_own_closure(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "static" / "js" / "report-modules.js").read_text(
            encoding="utf-8"
        )
        loader_call = source.index("_loadServerConfig();")
        first_closure_end = source.index("})();")
        self.assertLess(loader_call, first_closure_end)
        self.assertEqual(source.count("_loadServerConfig();"), 1)

    def test_period_defaults_before_optional_toolbar_lookup(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "static" / "js" / "core.js").read_text(
            encoding="utf-8"
        )
        function_start = source.index("async function loadCurrentPeriod()")
        function_end = source.index("\n}\n\nfunction periodToDateRange", function_start)
        function_body = source[function_start:function_end]
        default_assignment = function_body.index(
            "currentPeriod = (saved && /^\\d{4}-\\d{2}$/.test(saved))"
        )
        optional_toolbar_exit = function_body.index("if (!yearSel) return;")
        self.assertLess(default_assignment, optional_toolbar_exit)
        self.assertIn(
            "String(now.getMonth() + 1).padStart(2, '0')",
            function_body,
        )

    def test_system_stat_replacement_preserves_async_page_nodes(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "static" / "js" / "core.js").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(
            "pageDiv.innerHTML = applySysStats(pageDiv.innerHTML",
            source,
        )
        self.assertIn(
            "_applySystemStatsWithoutRebuilding(pageDiv);",
            source,
        )

    def test_report_feedback_is_scoped_and_requires_explicit_activation(self):
        root = Path(__file__).resolve().parents[1]
        script = textwrap.dedent(
            """
            import json

            from engine import self_learning
            from runtime_storage import CORRECTION_RULES

            for _ in range(3):
                result = self_learning.record_correction(
                    finding_type="银行收款与申报差异",
                    company_id=7,
                    industry="广告服务",
                    biz_model="项目制",
                    original_risk="高风险",
                    corrected_risk="待补证",
                    reason="需先区分借款、注资、退款和经营收款",
                )
                assert result["recorded"] is True
                assert result["auto_apply"] is False

            rules = json.loads(CORRECTION_RULES.read_text(encoding="utf-8"))
            assert len(rules) == 1
            assert rules[0]["company_id"] == 7
            assert rules[0]["correction_count"] == 3
            assert rules[0]["status"] == "candidate"

            finding = {
                "type": "银行收款与申报差异",
                "level": "高风险",
            }
            assert self_learning.apply_correction_rules(
                [finding], "广告服务", "项目制", company_id=7
            ) == 0

            sync = self_learning.manual_sync_corrections_to_modules()
            assert sync["activated"] == 1
            assert self_learning.apply_correction_rules(
                [finding], "广告服务", "项目制", company_id=8
            ) == 0
            assert self_learning.apply_correction_rules(
                [finding], "广告服务", "项目制", company_id=7
            ) == 1
            assert finding["level"] == "高风险"
            assert finding["_original_level"] == "高风险"
            assert finding["_auto_corrected"] is True
            assert finding["_suggested_level"] == "待补证"
            """
        )
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment["APP_DATA_DIR"] = directory
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=120,
            )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

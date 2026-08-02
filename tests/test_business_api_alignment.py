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

    def test_bank_and_journal_contracts_match_the_frontend(self):
        root = Path(__file__).resolve().parents[1]
        script = textwrap.dedent(
            """
            from collections import Counter

            from fastapi.testclient import TestClient

            from database import Company, SessionLocal
            from main import app

            with TestClient(app) as client:
                login = client.post(
                    "/api/auth/login",
                    json={
                        "username": "businessadmin",
                        "password": "Business-Test-2026!",
                    },
                )
                assert login.status_code == 200, login.text
                csrf = client.cookies.get("csrf_token")
                headers = {"X-CSRF-Token": csrf}

                db = SessionLocal()
                try:
                    company = Company(
                        name="业务接口回归测试公司",
                        uscc="91440300TESTALIGN01",
                    )
                    db.add(company)
                    db.commit()
                    db.refresh(company)
                    company_id = company.id
                finally:
                    db.close()

                selected = client.post(
                    "/api/auth/select-company",
                    headers=headers,
                    json={"company_id": company_id},
                )
                assert selected.status_code == 200, selected.text

                created_bank = client.post(
                    f"/api/bank-configs?company_id={company_id}",
                    headers=headers,
                    json={
                        "bank_name": "测试银行",
                        "account_number": "62220001",
                        "account_name": "回归测试账户",
                    },
                )
                assert created_bank.status_code == 200, created_bank.text
                bank_id = created_bank.json()["id"]

                banks = client.get(
                    f"/api/bank-configs?company_id={company_id}"
                )
                assert banks.status_code == 200, banks.text
                assert banks.json()[0]["bank_name"] == "测试银行"

                updated_bank = client.put(
                    f"/api/bank-configs/{bank_id}?company_id={company_id}",
                    headers=headers,
                    json={"account_name": "更新后的账户"},
                )
                assert updated_bank.status_code == 200, updated_bank.text

                entry_payloads = [
                    {
                        "entry_date": "2026-07-30",
                        "period": "2026-07",
                        "voucher_word": "记",
                        "voucher_no": 1,
                        "summary": "银行存款",
                        "account_code": "1002",
                        "account_name": "银行存款",
                        "debit_amount": 100,
                        "credit_amount": 0,
                    },
                    {
                        "entry_date": "2026-07-30",
                        "period": "2026-07",
                        "voucher_word": "记",
                        "voucher_no": 1,
                        "summary": "主营业务收入",
                        "account_code": "6001",
                        "account_name": "主营业务收入",
                        "debit_amount": 0,
                        "credit_amount": 100,
                    },
                ]
                entry_ids = []
                for payload in entry_payloads:
                    created = client.post(
                        f"/api/journal-entries?company_id={company_id}",
                        headers=headers,
                        json=payload,
                    )
                    assert created.status_code == 200, created.text
                    entry_ids.append(created.json()["id"])

                entries = client.get(
                    f"/api/journal-entries?company_id={company_id}"
                    "&skip=0&limit=100"
                )
                assert entries.status_code == 200, entries.text
                assert entries.json()["total"] == 2
                assert len(entries.json()["items"]) == 2

                voucher = client.get(
                    f"/api/journal-entries/by-voucher"
                    f"?company_id={company_id}&voucher_word=记&voucher_no=1"
                )
                assert voucher.status_code == 200, voucher.text
                assert voucher.json()["entry_count"] == 2
                assert voucher.json()["is_balanced"] is True

                item = client.get(
                    f"/api/journal-entries/{entry_ids[0]}"
                    f"?company_id={company_id}"
                )
                assert item.status_code == 200, item.text
                assert item.json()["account_code"] == "1002"

                updated_entry = client.put(
                    f"/api/journal-entries/{entry_ids[0]}"
                    f"?company_id={company_id}",
                    headers=headers,
                    json={"summary": "更新后的摘要"},
                )
                assert updated_entry.status_code == 200, updated_entry.text

                accounts = client.get(
                    f"/api/accounts?company_id={company_id}"
                )
                assert accounts.status_code == 200, accounts.text

                profit_loss = client.get(
                    f"/api/reports/profit-loss?company_id={company_id}"
                    "&period_from=2026-07&period_to=2026-07"
                )
                assert profit_loss.status_code == 200, profit_loss.text
                assert profit_loss.json()["period_from"] == "2026-07"
                assert profit_loss.json()["period_to"] == "2026-07"
                assert profit_loss.json()["items"]

                deleted_entries = client.post(
                    f"/api/journal-entries/batch-delete"
                    f"?company_id={company_id}",
                    headers=headers,
                    json={"ids": entry_ids},
                )
                assert deleted_entries.status_code == 200, deleted_entries.text
                assert deleted_entries.json()["count"] == 2

                deleted_bank = client.delete(
                    f"/api/bank-configs/{bank_id}?company_id={company_id}",
                    headers=headers,
                )
                assert deleted_bank.status_code == 200, deleted_bank.text
                assert client.get(
                    f"/api/bank-configs?company_id={company_id}"
                ).json() == []

                route_counts = Counter()
                for route in app.routes:
                    for method in getattr(route, "methods", set()):
                        route_counts[(method, route.path)] += 1
                expected_once = {
                    ("GET", "/api/bank-configs"),
                    ("POST", "/api/bank-configs"),
                    ("PUT", "/api/bank-configs/{config_id}"),
                    ("DELETE", "/api/bank-configs/{config_id}"),
                    ("GET", "/api/journal-entries"),
                    ("POST", "/api/journal-entries"),
                    ("GET", "/api/journal-entries/by-voucher"),
                    ("GET", "/api/journal-entries/{entry_id}"),
                    ("PUT", "/api/journal-entries/{entry_id}"),
                    ("DELETE", "/api/journal-entries/{entry_id}"),
                    ("POST", "/api/journal-entries/batch-delete"),
                    ("GET", "/api/agi/status"),
                }
                for key in expected_once:
                    assert route_counts[key] == 1, (key, route_counts[key])
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

    def test_dashboard_capabilities_are_fused_into_responsible_modules(self):
        root = Path(__file__).resolve().parents[1]
        dashboard = (root / "static" / "js" / "dashboard.js").read_text(
            encoding="utf-8"
        )
        core = (root / "static" / "js" / "core.js").read_text(
            encoding="utf-8"
        )
        main = (root / "main.py").read_text(encoding="utf-8")
        index = (root / "static" / "index.html").read_text(encoding="utf-8")
        engine_hub = (root / "static" / "js" / "engine-hub.js").read_text(
            encoding="utf-8"
        )
        engine_dashboard = (
            root / "static" / "js" / "tax-engine-dashboard.js"
        ).read_text(encoding="utf-8")
        knowledge_hub = (
            root / "static" / "js" / "tax-knowledge-hub.js"
        ).read_text(encoding="utf-8")
        methodology = (
            root / "static" / "js" / "tax-pipeline-pages.js"
        ).read_text(encoding="utf-8")
        risk_rules = (
            root / "static" / "js" / "tax-risk-rules.js"
        ).read_text(encoding="utf-8")
        standards = (
            root / "static" / "js" / "tax-report-standards.js"
        ).read_text(encoding="utf-8")
        rights = (root / "static" / "js" / "tax-rights-hub.js").read_text(
            encoding="utf-8"
        )

        for page, label in (
            ("engine-hub", "🧠 智能引擎中枢"),
            ("methodology", "📖 稽查方法论"),
            ("report-standards", "📖 报告编制要求"),
            ("taxpayer-rights", "🎁 税收权益保障"),
        ):
            self.assertIn(f"{{page:'{page}', label:'{label}'", dashboard)

        for legacy_page in (
            "file-parsing",
            "pipeline-analyze",
            "tax-risk-rules-list",
            "domain-panel",
            "tax-incentives",
            "chains-page",
            "evidence-page",
            "analysis-page",
            "compact-clues",
            "knowledge-hub",
            "engine-dashboard",
            "quality-system",
            "ai-rules",
            "tax-agi",
            "analyze-logs",
            "auditor-handbook",
            "feedback-template",
            "correction-rules",
        ):
            self.assertNotIn(f"page:'{legacy_page}'", dashboard)

        for section_id in (
            "overview",
            "knowledge",
            "dashboard",
            "quality",
            "rules",
            "agi",
            "logs",
            "corrections",
        ):
            self.assertIn(f"id:'{section_id}'", engine_hub)
        self.assertIn("知识驱动 · 受控推理 · 持续进化", engine_hub)
        self.assertIn("智能引擎中枢汇聚税务知识", engine_hub)
        self.assertNotIn("本页不再保留", engine_hub)
        self.assertNotIn("本区说明", engine_hub)
        self.assertIn('data-engine-layout="executive"', engine_hub)
        self.assertIn('class="engine-unified-shell"', engine_hub)
        self.assertIn('class="engine-toc-title">页面目录</div>', engine_hub)
        self.assertIn(".engine-section-body .agi-toc{display:none!important}", engine_hub)
        self.assertIn("renderKnowledgeHubIntegrated", engine_hub)
        self.assertIn("renderEngineDashboardIntegrated", engine_hub)
        self.assertNotIn('class="eh-tabs"', engine_hub)
        self.assertNotIn('id="engine-hub-workspace"', engine_hub)
        self.assertIn(
            "function renderKnowledgeHubIntegrated(container)",
            knowledge_hub,
        )
        self.assertIn(
            "KNOWLEDGE_HUB_GROUPS.forEach(function(group)",
            knowledge_hub,
        )
        self.assertIn(
            "function renderEngineDashboardIntegrated(container)",
            engine_dashboard,
        )
        for panel_id in ("status", "rules", "brain", "quality", "methods", "details"):
            self.assertIn(f"id:'{panel_id}'", engine_dashboard)
        methodology_start = methodology.index(
            "var METHODOLOGY_PAGE_SECTIONS"
        )
        methodology_end = methodology.index(
            "function _renderMethodologyGuide",
            methodology_start,
        )
        active_methodology = methodology[methodology_start:methodology_end]
        for section_id in (
            "overview",
            "guide",
            "files",
            "rules",
            "domains",
            "results",
            "chains",
            "handbook",
        ):
            self.assertIn(f"id:'{section_id}'", active_methodology)
        for view_id in ("compact", "clues", "evidence", "analysis"):
            self.assertIn(
                f'id="methodology-chain-{view_id}"',
                active_methodology,
            )
        for renderer in (
            "_renderMethodologyOverview",
            "_renderMethodologyGuide",
            "renderFileParsingPage",
            "renderTaxRiskRules",
            "renderUnifiedDomainPanel",
            "renderAnalyzePage",
            "renderMethodologyChainsIntegrated",
            "_renderMethodologyPracticeManual",
        ):
            self.assertIn(renderer, active_methodology)
        self.assertIn("程序规范 · 证据闭环 · 审慎判断", active_methodology)
        self.assertIn("稽查方法论以主体与期间确认", active_methodology)
        self.assertIn('data-method-layout="executive"', active_methodology)
        self.assertIn('class="method-layout"', active_methodology)
        self.assertIn(".method-mount .au-toc,.method-mount .fp-toc{display:none!important}", active_methodology)
        self.assertNotIn("本页把原", active_methodology)
        self.assertNotIn('class="method-tabs"', active_methodology)
        self.assertNotIn('id="methodology-workspace"', active_methodology)
        self.assertNotIn("data-method-section", active_methodology)
        self.assertIn(
            "_renderMethodologyResultSnapshot",
            methodology,
        )
        self.assertIn(
            "最近一次执行快照与复核队列",
            methodology,
        )
        self.assertIn(
            "模型评分、规则命中和链路匹配只负责排序与提示",
            methodology,
        )
        analyze_start = methodology.index("function renderAnalyzePage")
        analyze_end = methodology.index(
            "async function toggleDomainDetail",
            analyze_start,
        )
        active_results = methodology[analyze_start:analyze_end]
        self.assertNotIn('id="analyze-body"', active_results)
        self.assertIn(
            "当前账套暂无最近一次一键稽查结果",
            active_results,
        )

        domain_start = methodology.index("function renderUnifiedDomainPanelV4")
        domain_end = methodology.index(
            "function _renderMethodologyOverview", domain_start
        )
        active_domains = methodology[domain_start:domain_end]
        self.assertIn("十四个专业业务域及输出合同", active_domains)
        self.assertIn("统一放行规则", active_domains)
        self.assertIn("跨域协同场景库", active_domains)
        self.assertIn("全税费种协同范围", active_domains)
        self.assertNotIn("1720条", active_domains)
        self.assertNotIn("系统性造假", active_domains)
        self.assertIn(
            '@app.get("/api/methodology/assets/{asset_name}")',
            main,
        )
        for asset_name in ("rules", "clues", "evidence", "analysis", "framework", "playbooks"):
            self.assertIn(
                f"'/api/methodology/assets/{asset_name}",
                methodology + risk_rules,
            )
        self.assertIn('"industry_profiles": "industry_audit_profiles.json"', main)
        for protected_asset in (
            "tax_risk_rules_local_export",
            "cross_domain_clues",
            "cross_domain_evidence",
            "cross_domain_analysis",
        ):
            self.assertNotIn(
                f"fetch('/static/{protected_asset}.json",
                methodology + risk_rules,
            )
        self.assertIn(
            '_asset_items(_json.load(f), "evidence_chains"',
            main,
        )
        self.assertIn(
            '"analysis_chains",\n                    "chains",',
            main,
        )

        guide_start = methodology.index("function _renderMethodologyGuide")
        guide_end = methodology.index(
            "// 方法论面板内的紧凑线索链渲染",
            guide_start,
        )
        active_guide = methodology[guide_start:guide_end]
        for required_text in (
            "事实、证据、测算与法律适用分别复核",
            "系统只提供结构化复核，不作行政认定",
            "风险评分仅用于安排核验顺序",
            "候选规则与正式规则分库管理",
        ):
            self.assertIn(required_text, active_guide)
        for unsafe_text in (
            "差额即逃税证据",
            "虚开现形",
            "从“可能有”到“就是有”",
            "系统永远紧跟最新法规",
            "建议稽查频率",
        ):
            self.assertNotIn(unsafe_text, active_guide)

        self.assertIn("window._engineHubSection = 'knowledge';", core)
        self.assertIn(
            "case 'rs-pipeline':\n"
            "      window._engineHubSection = 'quality';\n"
            "      navigateTo('engine-hub');",
            core,
        )
        self.assertIn(
            "case 'agi-schedule':\n"
            "      window._engineHubSection = 'agi';\n"
            "      navigateTo('engine-hub');",
            core,
        )
        self.assertIn("window._methodologySection = 'files';", core)
        self.assertIn("window._reportSection = 'rpt-8';", core)
        self.assertIn("case 'taxpayer-rights':", core)
        self.assertIn("navigateTo('taxpayer-rights');", core)

        self.assertIn("税收优惠是对纳税人合法权益的主动保护", rights)
        self.assertIn("税收优惠与权益保障", index)
        self.assertIn("tax-rights-hub.js?v=2026073101", index)
        self.assertIn("app.css?v=2026073034", index)
        self.assertIn("chat.js?v=2026073101", index)
        self.assertIn("#main{margin-left:0;padding:3px}", index)
        self.assertIn(".content-area{padding:4px}", index)
        self.assertIn("engine-hub.js?v=2026073033", index)
        self.assertIn("tax-knowledge-hub.js?v=2026073018", index)
        self.assertIn("tax-engine-dashboard.js?v=2026073019", index)
        self.assertIn("tax-risk-rules.js?v=2026080203", index)
        self.assertIn("tax-pipeline-pages.js?v=2026080203", index)
        self.assertIn("system-logs.js?v=2026073101", index)
        self.assertIn("core.js?v=2026073021", index)
        self.assertIn("tax-report-standards.js?v=2026073032", index)
        self.assertNotIn("tax-feedback-template.js", index)

        self.assertNotIn("page:'report-spec'", dashboard)
        self.assertIn(
            "case 'report-spec':\n"
            "      window._reportSection = 'rpt-7';\n"
            "      navigateTo('report-standards');",
            core,
        )
        self.assertIn("事实清晰 · 证据可溯 · 编审一致", standards)
        self.assertIn("报告编制要求以文种和授权为起点", standards)
        self.assertIn('data-report-single-page="true"', standards)
        self.assertIn("编制全过程审核", standards)
        self.assertIn("常见误判的归因与复核矩阵", standards)
        self.assertIn("受控反馈", standards)
        self.assertNotIn("本页把原", standards)
        self.assertNotIn("REPORT_COMPILATION_SECTIONS", standards)
        self.assertNotIn("report-tabs", standards)
        self.assertNotIn("renderFeedbackTemplate", standards)
        self.assertNotIn("整体不少于2000字", standards)
        self.assertNotIn("税稽字〔YYYY〕第XXX号", standards)
        self.assertNotIn("累计1次即", standards)
        for section_id in range(1, 11):
            self.assertIn(f"id: 'rpt-{section_id}'", standards)
        for legacy_id in range(1, 10):
            self.assertIn(f"'rs-{legacy_id}':", standards)

        rules_start = methodology.index("function renderAiRules(container)")
        rules_end = methodology.index(
            "// ═══════════ 核心数据资产页面",
            rules_start,
        )
        active_rules = methodology[rules_start:rules_end]
        self.assertIn("事实与证据边界", active_rules)
        self.assertIn("数据安全与租户隔离", active_rules)
        self.assertIn("人工复核与输出规范", active_rules)
        self.assertNotIn("做事要狠", active_rules)
        self.assertNotIn("自作主张", active_rules)

        quality_start = methodology.index(
            "function renderQualitySystem(container)"
        )
        quality_end = methodology.index(
            "function loadMethodologies()",
            quality_start,
        )
        active_quality = methodology[quality_start:quality_end]
        for gate in (
            "输入与资料门禁",
            "规则与适用性门禁",
            "证据闭环门禁",
            "推理与红队门禁",
            "法律、金额与报告门禁",
            "运行、安全与审计门禁",
        ):
            self.assertIn(gate, active_quality)

    def test_correction_learning_section_is_complete_and_private(self):
        root = Path(__file__).resolve().parents[1]
        correction_ui = (
            root / "static" / "js" / "correction-rules.js"
        ).read_text(encoding="utf-8")
        index = (root / "static" / "index.html").read_text(encoding="utf-8")
        main = (root / "main.py").read_text(encoding="utf-8")
        storage = (root / "runtime_storage.py").read_text(encoding="utf-8")
        learning = (root / "engine" / "self_learning.py").read_text(
            encoding="utf-8"
        )
        coordinator = (
            root / "engine" / "agents" / "coordinator.py"
        ).read_text(encoding="utf-8")
        agi_router = (root / "routers" / "agi.py").read_text(encoding="utf-8")
        core = (root / "static" / "js" / "core.js").read_text(encoding="utf-8")

        self.assertIn("function renderCRHList(rules, filter)", correction_ui)
        self.assertIn("function filterCRH(filter)", correction_ui)
        self.assertIn("_crhEscape(itemReason)", correction_ui)
        self.assertIn("当前筛选条件下没有规则", correction_ui)
        self.assertIn("correction-rules.js?v=2026073019", index)

        self.assertIn("CORRECTION_RULES = DATA_DIR /", storage)
        self.assertIn("CONTENT_FEEDBACK = DATA_DIR /", storage)
        self.assertIn("ARCHIVED_CORRECTION_RULES = DATA_DIR /", storage)
        self.assertIn("LEARNING_AGENT_WEIGHTS = DATA_DIR /", storage)
        self.assertIn("raw_rules = read_json(CORRECTION_RULES, [])", main)
        self.assertIn("elif isinstance(raw_rules, list):", main)
        self.assertIn("_find_correction_rule(rules, fingerprint)", main)
        self.assertIn("_CORRECTIONS_PATH = CORRECTION_RULES", learning)
        self.assertIn("self._corrections_path = LEARNING_AGENT_WEIGHTS", coordinator)
        self.assertIn(
            'result["knowledge_base"] = get_kb().get_full_knowledge()',
            agi_router,
        )
        self.assertIn(
            'result["corrections"] = get_correction_rule_summary()',
            agi_router,
        )
        self.assertIn("var agiVersion =", core)
        self.assertIn("var correctionTotal =", core)
        for broken_metric in (
            "vundefined",
            "1514规则",
            "21720条协商规则",
            "最近101720条",
        ):
            self.assertNotIn(broken_metric, core)
        self.assertNotIn(
            'os.path.join("static", "user_corrections.json")',
            main,
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

    def test_module_pages_use_compact_outer_gutters(self):
        root = Path(__file__).resolve().parents[1]
        app_css = (root / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            '#content-area > [id^="page-"] { padding: 8px; max-width: 1680px;',
            app_css,
        )
        self.assertIn(".rights-shell, .kh-wrap,", app_css)
        self.assertIn(
            '#content-area > [id^="page-"] > [style*="margin:0 auto"]',
            app_css,
        )
        self.assertIn(
            "#page-chat { padding: 8px !important; max-width: 1680px !important; }",
            app_css,
        )

        expected_desktop = "padding:36px clamp(8px,1.1vw,18px) 56px;"
        for relative_path in (
            "static/js/engine-hub.js",
            "static/js/tax-pipeline-pages.js",
            "static/js/tax-report-standards.js",
        ):
            source = (root / relative_path).read_text(encoding="utf-8")
            self.assertIn("max-width:1680px;", source, msg=relative_path)
            self.assertIn(expected_desktop, source, msg=relative_path)

        methodology = (
            root / "static" / "js" / "tax-pipeline-pages.js"
        ).read_text(encoding="utf-8")
        chain_selector = (
            ".method-mount .rr,.method-mount .cl,.method-mount .ev,"
            ".method-mount .alc{"
        )
        self.assertIn(chain_selector, methodology)
        chain_override = methodology.split(chain_selector, 1)[1].split("}", 1)[0]
        for declaration in (
            "width:100%!important;",
            "max-width:none!important;",
            "margin:0!important;",
            "padding:0!important",
        ):
            self.assertIn(declaration, chain_override)

        chat = (root / "static" / "js" / "chat.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("grid-template-columns:240px minmax(0,1fr) 280px;", chat)
        self.assertIn("height:calc(100vh - 72px);", chat)
        self.assertNotIn("margin:-20px", chat)

    def test_tables_and_support_pages_use_executive_layouts(self):
        root = Path(__file__).resolve().parents[1]
        rules = (root / "static" / "js" / "tax-risk-rules.js").read_text(
            encoding="utf-8"
        )
        methodology = (
            root / "static" / "js" / "tax-pipeline-pages.js"
        ).read_text(encoding="utf-8")
        chat = (root / "static" / "js" / "chat.js").read_text(
            encoding="utf-8"
        )
        rights = (
            root / "static" / "js" / "tax-rights-hub.js"
        ).read_text(encoding="utf-8")
        logs = (root / "static" / "js" / "system-logs.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('class="rr-table rr-rule-table"', rules)
        self.assertIn(".rr-rule-table{min-width:1160px", rules)
        self.assertIn(
            '<colgroup><col style="width:6%"><col style="width:28%">'
            '<col style="width:14%"><col style="width:10%">'
            '<col style="width:7%"><col style="width:7%">'
            '<col style="width:7%"><col style="width:12%">'
            '<col style="width:9%"></colgroup>',
            rules,
        )
        self.assertEqual(
            methodology.count(
                'class="rr-table method-chain-table"><colgroup>'
            ),
            3,
        )
        self.assertIn(".method-chain-table{min-width:840px", methodology)
        self.assertIn(
            '<colgroup><col style="width:6%"><col style="width:40%">'
            '<col style="width:12%"><col style="width:10%">'
            '<col style="width:18%"><col style="width:14%"></colgroup>',
            methodology,
        )

        self.assertIn(".cq-main-header{", chat)
        self.assertIn("font-size:14px;line-height:1.85", chat)
        self.assertIn("@media(max-width:820px)", chat)

        self.assertIn("class=\"rights-kicker\"", rights)
        self.assertIn(".rights-incentive-list{", rights)
        self.assertIn("max-width:1680px;", rights)

        self.assertIn("class=\"log-shell\"", logs)
        self.assertIn(".log-table{width:100%;min-width:1200px", logs)
        self.assertIn(
            '<colgroup><col style="width:15%"><col style="width:10%">'
            '<col style="width:19%"><col style="width:14%">'
            '<col style="width:7%"><col style="width:8%">'
            '<col style="width:12%"><col style="width:9%">'
            '<col style="width:6%"></colgroup>',
            logs,
        )
        self.assertIn("操作留痕 · 责任追踪 · 异常定位", logs)


if __name__ == "__main__":
    unittest.main()

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
        self.assertIn("单页融合 · 全量能力 · 闭环治理", engine_hub)
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
        for section_id in (
            "guide",
            "files",
            "results",
            "rules",
            "domains",
            "chains",
            "handbook",
        ):
            self.assertIn(f"id:'{section_id}'", methodology)
        for view_id in ("clues", "evidence", "analysis", "compact"):
            self.assertIn(f"{view_id}:", methodology)

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
        self.assertIn("window._reportStandardsSection = 'review';", core)
        self.assertIn("case 'taxpayer-rights':", core)
        self.assertIn("navigateTo('taxpayer-rights');", core)

        self.assertIn("税收优惠是对纳税人合法权益的主动保护", rights)
        self.assertIn("税收优惠与权益保障", index)
        self.assertIn("tax-rights-hub.js?v=2026073017", index)
        for script in (
            "tax-engine-dashboard.js",
            "engine-hub.js",
            "core.js",
            "tax-pipeline-pages.js",
            "tax-knowledge-hub.js",
        ):
            self.assertIn(f"{script}?v=2026073018", index)

        self.assertNotIn("page:'report-spec'", dashboard)
        self.assertIn(
            "case 'report-spec':\n      navigateTo('report-standards');",
            core,
        )
        self.assertNotIn("九、详细出具规范", standards)
        self.assertNotIn('id="rs2-static"', standards)
        self.assertNotIn("renderReportSpecStatic();", standards)
        self.assertIn("不再保留两套章节或拼接式结构", standards)
        self.assertIn("render: 'renderFeedbackTemplate'", standards)
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


if __name__ == "__main__":
    unittest.main()

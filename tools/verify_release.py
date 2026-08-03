"""Offline release checks; no business data or network access is required."""
from __future__ import annotations

import ast
import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SENSITIVE_NAMES = {
    "api_key.json", "sessions.json", "access_logs.jsonl", "accounting.db",
    "last_analysis_cache.json", "analysis_history.json",
    "user_corrections.json", "deleted_correction_rules.json",
    "_deleted_correction_rules.json", "content_feedback.json",
    "learning_agent_weights.json",
}
PRODUCTION_PYTHON = [
    "security.py", "security_web.py", "runtime_storage.py", "llm_config.py",
    "llm_credentials.py", "llm_providers.py", "request_context.py",
    "manage_users.py", "database.py", "main.py", "chat.py", "archives.py",
    "engine/llm_client.py", "engine/pipeline.py", "engine/self_learning.py",
    "engine/agi_pipeline.py", "engine/rule_discovery.py",
    "engine/scenario_methodology.py", "engine/methodology_coverage.py",
    "engine/methodology_catalog.py", "engine/methodology_portfolio.py",
    "engine/methodology_acceptance.py", "engine/methodology_assets.py",
    "engine/report_standards.py",
    "engine/agents/coordinator.py",
    "tools/migrate_llm_credentials.py",
]


def check(condition: bool, message: str, failures: list[str]) -> None:
    print(("PASS " if condition else "FAIL ") + message)
    if not condition:
        failures.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="allow mutable runtime files only inside the private data directory",
    )
    args = parser.parse_args()
    failures: list[str] = []
    present_sensitive = [
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.is_file() and path.name.lower() in SENSITIVE_NAMES
        and not (args.runtime and path.is_relative_to(ROOT / "data"))
    ]
    sensitive_message = (
        "runtime contains no secrets/data outside the private data directory"
        if args.runtime
        else "release contains no runtime secrets/data"
    )
    check(not present_sensitive, sensitive_message, failures)

    for relative in PRODUCTION_PYTHON:
        path = ROOT / relative
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            valid = True
        except (OSError, SyntaxError):
            valid = False
        check(valid, f"syntax: {relative}", failures)

    security_source = (ROOT / "security.py").read_text(encoding="utf-8")
    web_source = (ROOT / "security_web.py").read_text(encoding="utf-8")
    llm_source = (ROOT / "llm_config.py").read_text(encoding="utf-8")
    credential_source = (ROOT / "llm_credentials.py").read_text(encoding="utf-8")
    provider_source = (ROOT / "llm_providers.py").read_text(encoding="utf-8")
    request_context_source = (ROOT / "request_context.py").read_text(encoding="utf-8")
    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    pipeline_source = (ROOT / "engine" / "pipeline.py").read_text(encoding="utf-8")
    report_standard_source = (ROOT / "engine" / "report_standards.py").read_text(encoding="utf-8")
    chat_source = (ROOT / "chat.py").read_text(encoding="utf-8")
    llm_client_source = (ROOT / "engine" / "llm_client.py").read_text(encoding="utf-8")
    core_source = (ROOT / "static" / "js" / "core.js").read_text(encoding="utf-8")
    index_source = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    company_picker_source = (ROOT / "static" / "select-company.html").read_text(encoding="utf-8")
    new_company_source = (ROOT / "static" / "new-company.html").read_text(encoding="utf-8")
    knowledge_source = (ROOT / "engine" / "knowledge_base.py").read_text(encoding="utf-8")
    check("hashlib.scrypt" in security_source, "passwords use scrypt", failures)
    check(
        "from engine.threshold_scanner import" not in pipeline_source
        and '"_rule_match_mode": "threshold_scan"' not in pipeline_source
        and "threshold主动扫描" not in pipeline_source
        and "1720" not in pipeline_source,
        "one-click analysis does not execute the retired threshold rule scan",
        failures,
    )
    check(
        "_MALFORMED_POLICY_RE" in report_standard_source
        and 'release_status"] = "草稿_待人工复核"' in report_standard_source
        and "automatic_determination_allowed" in report_standard_source,
        "report gate blocks malformed law references and automatic determination",
        failures,
    )
    check("csrf_is_valid" in web_source, "unsafe requests enforce CSRF", failures)
    check("can_access_company" in web_source, "tenant authorization is centralized", failures)
    check(
        "get_current_user_id" in llm_source
        and "get_default_credential" in llm_source
        and "LLM_API_KEY" not in llm_source
        and "api_key.json" not in llm_source,
        "LLM configuration is resolved from the authenticated user only",
        failures,
    )
    check(
        "AESGCM" in credential_source
        and "APP_LLM_MASTER_KEY" in credential_source
        and "_associated_data" in credential_source,
        "per-user LLM credentials use authenticated encryption",
        failures,
    )
    check(
        "UNIQUE(user_id, provider)" in credential_source
        and "llm_credential_audit" in credential_source
        and "secret_last4" in credential_source,
        "credential ownership, masking and audit records are persisted",
        failures,
    )
    check(
        "base_url" not in main_source[
            main_source.find("class LLMCredentialCreate"):
            main_source.find("class LLMCredentialRotate")
        ]
        and "https://" in provider_source,
        "LLM provider endpoints are fixed by an allowlist",
        failures,
    )
    check(
        "set_current_user_id" in web_source
        and "reset_current_user_id" in web_source
        and "ContextVar" in request_context_source,
        "request identity is propagated and reset for model calls",
        failures,
    )
    check(
        "LLM_CONFIG =" not in chat_source
        and "llm = LLMClient()" not in llm_client_source
        and "return LLMClient()" in llm_client_source,
        "model clients do not retain another user's credential",
        failures,
    )
    check('allow_origins=["*"]' not in main_source, "wildcard CORS is absent", failures)
    check('host="0.0.0.0"' not in main_source, "default server is loopback-only", failures)
    check("X-Content-Type-Options" in web_source, "security headers are enabled", failures)
    check(
        "/api/auth/me" in core_source and "selected_company_id" in core_source,
        "frontend identity and tenant selection use the server session",
        failures,
    )
    check(
        "coUsccEl && co" in core_source and "coUscc && co" not in core_source,
        "application startup tenant rendering is valid",
        failures,
    )
    check(
        "if (registrationView)" in core_source
        and "if (companyPickView)" in core_source
        and "if (appView)" in core_source,
        "application startup tolerates removed legacy view containers",
        failures,
    )
    check(
        "/api/auth/me" in index_source and "getCookie('company_id')" not in index_source,
        "sidebar does not depend on readable identity cookies",
        failures,
    )
    check(
        "X-CSRF-Token" in company_picker_source and "X-CSRF-Token" in new_company_source,
        "standalone tenant pages attach CSRF tokens",
        failures,
    )
    check(
        "status.has_key" in company_picker_source and "data.key" not in company_picker_source,
        "LLM status UI never requests or renders the secret",
        failures,
    )
    check(
        "/api/me/llm-credentials" in company_picker_source
        and "/api/llm/providers" in company_picker_source
        and "管理我的模型" in company_picker_source
        and "X-CSRF-Token" in company_picker_source,
        "tenant picker provides CSRF-protected per-user model management",
        failures,
    )
    check(
        "DATA_DIR" in knowledge_source
        and not (ROOT / "static" / "tax_agi_knowledge.json").exists(),
        "mutable AGI knowledge is stored outside the static web root",
        failures,
    )

    retired_assets = [
        "static/tax_risk_rules_local_export.json",
        "static/cross_domain_clues.json",
        "static/cross_domain_evidence.json",
        "static/cross_domain_analysis.json",
        "engine/candidate_rule_governance.py",
    ]
    check(
        not any((ROOT / relative).exists() for relative in retired_assets),
        "superseded rule and chain assets are absent",
        failures,
    )

    sys.path.insert(0, str(ROOT))
    try:
        from engine.methodology_catalog import (
            SCENARIO_FILES,
            load_canonical_catalog,
            load_reviewed_scenario_contracts,
            methodology_inventory,
        )
        from engine.methodology_acceptance import run_portfolio_acceptance
        from engine.methodology_portfolio import load_methodology_portfolio

        catalog = load_canonical_catalog()
        inventory = methodology_inventory()
        modules = catalog.get("modules", [])
        rules = [rule for module in modules for rule in module.get("rules", [])]
        portfolio = load_methodology_portfolio()
        acceptance = run_portfolio_acceptance()
        scenarios = [
            scene
            for code in SCENARIO_FILES
            for scene in load_reviewed_scenario_contracts(code).get("scenarios", [])
        ]
        catalog_valid = (
            catalog.get("version") == "3.0.0"
            and len(modules) == 20
            and len(rules) == 67
            and len({rule.get("id") for rule in rules}) == len(rules)
            and all(rule.get("fact_hypothesis") for rule in rules)
            and all(rule.get("required_fields") for rule in rules)
            and all("excludes" in rule for rule in rules)
        )
        scene_valid = (
            portfolio.get("version") == "3.1.0"
            and len(portfolio.get("contracts", [])) == 23
            and len(scenarios) == 161
            and all("legacy_absorption" not in scene for scene in scenarios)
            and all("已吸收" not in json.dumps(scene, ensure_ascii=False) for scene in scenarios)
            and all("1720条" not in json.dumps(scene, ensure_ascii=False) for scene in scenarios)
            and all((scene.get("clue_chain") or {}).get("steps") for scene in scenarios)
            and all((scene.get("evidence_chain") or {}).get("supporting_sources") for scene in scenarios)
            and all((scene.get("evidence_chain") or {}).get("opposing_sources") for scene in scenarios)
            and all((scene.get("analysis_chain") or {}).get("reasoning") for scene in scenarios)
            and all(scene.get("validation_cases") for scene in scenarios)
            and all(len(scene.get("acceptance_cases") or []) == 5 for scene in scenarios)
            and all((scene.get("policy_applicability") or {}).get("status") == "case_time_verification_required" for scene in scenarios)
            and acceptance.get("status") == "passed"
            and acceptance.get("passed_scene_count") == 161
            and acceptance.get("acceptance_case_count") == 805
            and inventory.get("rules") == 228
            and inventory.get("clue_paths") == 188
            and inventory.get("evidence_plans") == 181
            and inventory.get("analysis_plans") == 181
            and len(inventory.get("clue_depths", [])) >= 5
            and len(inventory.get("validation_depths", [])) >= 4
        )
    except Exception:
        catalog_valid = False
        scene_valid = False
    check(catalog_valid, "canonical methodology catalog passes structural review", failures)
    check(scene_valid, "industry scenarios use complete variable-depth contracts", failures)

    if failures:
        print(f"\n{len(failures)} check(s) failed.")
        return 1
    print("\nAll release checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

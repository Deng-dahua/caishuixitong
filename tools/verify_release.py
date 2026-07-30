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
    chat_source = (ROOT / "chat.py").read_text(encoding="utf-8")
    llm_client_source = (ROOT / "engine" / "llm_client.py").read_text(encoding="utf-8")
    core_source = (ROOT / "static" / "js" / "core.js").read_text(encoding="utf-8")
    index_source = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    company_picker_source = (ROOT / "static" / "select-company.html").read_text(encoding="utf-8")
    new_company_source = (ROOT / "static" / "new-company.html").read_text(encoding="utf-8")
    knowledge_source = (ROOT / "engine" / "knowledge_base.py").read_text(encoding="utf-8")
    check("hashlib.scrypt" in security_source, "passwords use scrypt", failures)
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

    rule_report = ROOT / "reports" / "rule_quality_report.json"
    if rule_report.exists():
        result = json.loads(rule_report.read_text(encoding="utf-8")).get("result")
        check(result == "pass", "rule structure audit passes", failures)
    else:
        check(False, "rule audit report exists", failures)

    if failures:
        print(f"\n{len(failures)} check(s) failed.")
        return 1
    print("\nAll release checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

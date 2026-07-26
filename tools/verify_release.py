"""Offline release checks; no business data or network access is required."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SENSITIVE_NAMES = {
    "api_key.json", "sessions.json", "access_logs.jsonl", "accounting.db",
    "last_analysis_cache.json", "analysis_history.json",
}
PRODUCTION_PYTHON = [
    "security.py", "security_web.py", "runtime_storage.py", "llm_config.py",
    "manage_users.py", "database.py", "main.py", "chat.py", "archives.py",
    "engine/llm_client.py", "engine/pipeline.py",
]


def check(condition: bool, message: str, failures: list[str]) -> None:
    print(("PASS " if condition else "FAIL ") + message)
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    present_sensitive = [
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.is_file() and path.name.lower() in SENSITIVE_NAMES
    ]
    check(not present_sensitive, "release contains no runtime secrets/data", failures)

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
    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    check("hashlib.scrypt" in security_source, "passwords use scrypt", failures)
    check("csrf_is_valid" in web_source, "unsafe requests enforce CSRF", failures)
    check("can_access_company" in web_source, "tenant authorization is centralized", failures)
    check("LLM_API_KEY" in llm_source and "api_key.json" not in llm_source, "LLM secret is environment-only", failures)
    check('allow_origins=["*"]' not in main_source, "wildcard CORS is absent", failures)
    check('host="0.0.0.0"' not in main_source, "default server is loopback-only", failures)
    check("X-Content-Type-Options" in web_source, "security headers are enabled", failures)

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

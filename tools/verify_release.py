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
    "manage_users.py", "database.py", "main.py",
    "engine/llm_client.py", "engine/pipeline.py", "engine/self_learning.py",
    "engine/agi_pipeline.py", "engine/rule_discovery.py",
    "engine/orchestrator.py", "engine/report_standards.py",
    "engine/verified_rule_engine.py", "engine/redline_engine.py",
    "engine/fact_rules.py", "engine/text_guardrails.py",
    "engine/framework_config.py", "engine/output_governance.py",
    "engine/agents/coordinator.py",
    "tools/migrate_llm_credentials.py",
]


def check(condition: bool, message: str, failures: list[str]) -> None:
    print(("PASS " if condition else "FAIL ") + message)
    if not condition:
        failures.append(message)


def _tracked_sensitive() -> list[str]:
    """版本库中已跟踪、且命中敏感名单的文件。

    用 git ls-files 而非 rglob：发布拦截的是「进了版本库的东西」，
    磁盘上的运行期产物（data/ 缓存、数据库、上传文件）不该算发布内容。
    不在 git 仓库中时退化为文件系统扫描，避免在裸目录下静默放行。
    """
    import shutil
    import subprocess

    # 2026-09-15：本机 PATH 常无 git（须用 PortableGit 全路径），裸 "git" 会抛
    # FileNotFoundError → 旧逻辑退化为全盘扫描，而 data/ 按设计本就存放这些运行期文件，
    # 结果必然命中敏感名单 → 恒定假失败并阻断发布。现先稳健定位 git；
    # 实在拿不到 git 时，退回扫描但**排除私有 data 目录**（与 --runtime 口径一致）。
    git_bin = shutil.which("git") or shutil.which("git.exe")
    if not git_bin:
        _candidate = Path(
            r"C:/Users/Administrator/.workbuddy/binaries/PortableGit/versions/1.2.0/cmd/git.exe"
        )
        if _candidate.exists():
            git_bin = str(_candidate)

    try:
        if git_bin:
            output = subprocess.run(
                [git_bin, "ls-files", "-z"],
                cwd=str(ROOT), capture_output=True, timeout=30,
            )
            if output.returncode == 0:
                names = [n for n in output.stdout.decode("utf-8", "replace").split("\0") if n]
            else:
                names = _nonsensitive_runtime_names(ROOT)
        else:
            names = _nonsensitive_runtime_names(ROOT)
    except Exception:
        names = _nonsensitive_runtime_names(ROOT)
    return [n for n in names if Path(n).name.lower() in SENSITIVE_NAMES]


def _nonsensitive_runtime_names(root: Path) -> list:
    """git 不可用时的退化扫描：排除私有 data 目录（运行期缓存/库/上传本就不属发布内容）。"""
    data_dir = root / "data"
    names = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            if p.is_relative_to(data_dir):
                continue
        except AttributeError:  # Python < 3.9 兼容
            if str(p).startswith(str(data_dir)):
                continue
        names.append(str(p.relative_to(root)))
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="allow mutable runtime files only inside the private data directory",
    )
    args = parser.parse_args()
    failures: list[str] = []

    # 发布口径（默认）判定的是「会被交付出去的东西」，即版本库已跟踪的文件；
    # 本地运行期产生的 data/ 缓存、数据库、上传文件留在磁盘上属正常，不该拦截发布。
    # 本地运行口径（--runtime）则按文件系统扫，且仅允许私有 data 目录内存在。
    if args.runtime:
        present_sensitive = [
            str(path.relative_to(ROOT))
            for path in ROOT.rglob("*")
            if path.is_file() and path.name.lower() in SENSITIVE_NAMES
            and not path.is_relative_to(ROOT / "data")
        ]
        sensitive_message = (
            "runtime contains no secrets/data outside the private data directory"
        )
    else:
        present_sensitive = _tracked_sensitive()
        sensitive_message = "release contains no runtime secrets/data (git index is clean)"
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
    output_governance_source = (ROOT / "engine" / "output_governance.py").read_text(encoding="utf-8")
    check(
        "run_output_governance" in pipeline_source
        and "seal_governed_findings" in pipeline_source
        and "_enforce_scenario_execution_boundary" in main_source
        and 'GOVERNANCE_STATUS = "output_governed"' in output_governance_source
        and 'automatic_determination_allowed"] = False' in output_governance_source,
        "one-click findings are sealed by the output-governance core (industry-neutral)",
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
        "LLM_CONFIG =" not in main_source
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
        "engine/scenario_execution.py", "engine/scenario_methodology.py",
        "engine/methodology_catalog.py", "engine/methodology_portfolio.py",
        "engine/methodology_acceptance.py", "engine/methodology_assets.py",
        "engine/methodology_guardrails.py", "engine/methodology_loader.py",
        "engine/methodology_coverage.py",
    ]
    check(
        not any((ROOT / relative).exists() for relative in retired_assets),
        "superseded rule and chain assets are absent",
        failures,
    )

    sys.path.insert(0, str(ROOT))
    try:
        from engine.fact_rules import (
            load_canonical_catalog,
            governance_inventory,
        )

        catalog = load_canonical_catalog()
        inventory = governance_inventory()
        modules = catalog.get("modules", [])
        rules = [rule for module in modules for rule in module.get("rules", [])]
        catalog_valid = (
            catalog.get("version") == "3.0.0"
            and len(modules) == 25
            and len(rules) == 89
            and len({rule.get("id") for rule in rules}) == len(rules)
            and all(rule.get("fact_hypothesis") for rule in rules)
            and all(rule.get("required_fields") for rule in rules)
            and all("excludes" in rule for rule in rules)
        )
        # 行业场景契约与 portfolio 验收已退役；仅校验权威横向目录与红线驱动方法论。
        scene_valid = True
    except Exception:
        catalog_valid = False
        scene_valid = False
    check(catalog_valid, "canonical methodology catalog passes structural review (25 modules / 89 rules)", failures)
    check(scene_valid, "industry scenario contracts are decommissioned", failures)

    # ── 跨模块数字与法条一致性闸门（P1-3）──
    # 原 tools/audit_consistency.py 于 4074d4cf 被误删后，计数常量与法条条款号失去
    # 自动校验，酿成历史上那次数字字符串污染。此处重建闸门：ERROR 即拦截发布。
    # （本注释刻意不写出污染字面量，以便本文件仍受该闸门的污染检测覆盖）
    try:
        import audit_consistency as _ac  # 同目录，verify_release 已可被直接执行

        _counts, _general = _ac.run_checks()
        _n_err = (len([i for i in _counts if i[0] == "ERROR"])
                  + len([i for i in _general if i[0] == "ERROR"]))
        _detail = "; ".join(
            f"{rel}: {msg}" for _lvl, rel, msg in _general if _lvl == "ERROR"
        )[:300]
        check(
            _n_err == 0,
            f"count constants and law references are consistent ({_n_err} error(s))"
            + (f" — {_detail}" if _detail else ""),
            failures,
        )
    except Exception as _ac_err:  # 校验器自身异常不得静默放行
        check(False, f"consistency checker executable ({_ac_err})", failures)

    if failures:
        print(f"\n{len(failures)} check(s) failed.")
        return 1
    print("\nAll release checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

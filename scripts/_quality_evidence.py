# -*- coding: utf-8 -*-
"""META-QUALITY 阶段 4~12 的**统一事实取证器**（2026-10-17）。

为什么要一个统一取证器：
  · 这些阶段（可观测性/安全/灾备/文档/CI-CD/伦理/冗余/习惯）的判断，
    本质都是"系统里**有没有**这个东西、在**哪些**模块有"。逐条 grep 既慢又不可复核；
  · 本脚本一次扫描全库，把事实写成 `_quality/EVIDENCE_BASE.json`，
    每个阶段的报告都**只引用这份证据**，做到"结论可回溯到行号"。

★ 纪律：
  ① 只统计**代码/配置/文档的真实存在**，不统计注释里"提到"的字样（AST + 去注释）；
  ② 每项证据都带 `file:line`，报告里可直接核；
  ③ 区分「声明」与「实现」：有函数名 ≠ 有实现（`_bk` 备份文件、`docs` 里的示例一律排除）。
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import subprocess
from collections import defaultdict
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "元质量_20261016" / "_quality"


def _py_files(product_only: bool = False) -> List[pathlib.Path]:
    """生效中的 Python 源文件（排除虚拟环境、备份、归档）。

    ★ 2026-10-17：必须区分**产品代码**与**验证/工具脚本**。
      根目录有 60+ 个 `_verify_*.py`（自检脚本），它们大量 `print`。
      若不区分，会把"工具脚本的 print"算成"产品没有日志"之外的噪音，
      导致可观测性/冗余等结论失真。
    """
    out = []
    for pat in ("*.py", "engine/*.py"):
        for p in ROOT.glob(pat):
            s = str(p).replace("\\", "/")
            if any(x in s for x in ("/.venv/", "/baseline/", "/_bk", "/trash/", "/__pycache__/")):
                continue
            if p.name.startswith("_bk"):
                continue
            if product_only and (p.name.startswith("_verify") or p.name.startswith("_probe")):
                continue
            out.append(p)
    return sorted(set(out))


_STRIP_CACHE: Dict[str, str] = {}


def _strip_prose(src: str) -> str:
    """抹掉**行注释**与**真正的 docstring**（保留换行 ⇒ 行号不变）。

    ★ 为什么不能用"正则抹所有三引号字符串"：本项目大量 DDL 写在模块级三引号常量里
      （形如 _DDL_X = <三引号>CREATE TABLE IF NOT EXISTS ... <三引号>），
      一刀切抹掉会把**真实建表语句**当成注释丢掉（第一版就这么漏了 17 张表）。
    ★ 为什么仍要抹：注释里写"绝不 os.remove"不能被当成真实调用
      （本项目审计闸门 check_delete_exits 踩过同样的坑）。
    ★ 性能：tokenize 对 300+ 文件太慢（实测超时）⇒ 改 AST 定位 docstring + 简化注释规则。
    """
    key = str(hash(src))
    if key in _STRIP_CACHE:
        return _STRIP_CACHE[key]
    lines = src.split("\n")
    # ① docstring：一次 parse 拿到精确行区间
    try:
        tree = ast.parse(src)
        spans = []
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list) or not body:
                continue
            first = body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                spans.append((first.lineno, first.end_lineno or first.lineno))
        for a, b in spans:
            for i in range(a - 1, min(b, len(lines))):
                lines[i] = " " * len(lines[i])
    except (SyntaxError, ValueError):
        pass
    # ② 注释：只认「行首可选空白 + #」或「≥2 空格 + #」（字符串里的 '#' 前通常无空格或仅 1 个）
    for i, ln in enumerate(lines):
        m = re.search(r"(^\s*#)|(\s{2,}#)", ln)
        if m:
            cut = m.start() if m.group(1) else m.start() + len(m.group(2)) - len(m.group(2).lstrip())
            lines[i] = ln[:cut]
    out = "\n".join(lines)
    _STRIP_CACHE[key] = out
    return out


def _grep(patterns: List[str], files: List[pathlib.Path], *, limit: int = 0) -> List[Dict[str, Any]]:
    """在**去注释**后的源码里找匹配，返回 [{file, line, text}]。"""
    rx = re.compile("|".join("(?:%s)" % p for p in patterns), re.I)
    hits = []
    for f in files:
        raw = f.read_text(encoding="utf-8", errors="replace")
        masked = _strip_prose(raw).split("\n")
        for i, ln in enumerate(masked, 1):
            if rx.search(ln):
                hits.append({"file": f.relative_to(ROOT).as_posix(), "line": i,
                             "text": raw.split("\n")[i - 1].strip()[:150]})
                if limit and len(hits) >= limit:
                    return hits
    return hits


def _routes(files: List[pathlib.Path]) -> List[Dict[str, Any]]:
    """全部 HTTP 路由（方法 + 路径 + 前缀 + 文件:行）。"""
    out = []
    rx = re.compile(r'@(app|router)\.(get|post|put|patch|delete)\(\s*"([^"]+)"')
    pref = {}
    for f in files:
        t = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'APIRouter\(\s*prefix\s*=\s*"([^"]+)"', t)
        if m:
            pref[f.name] = m.group(1)
    for f in files:
        raw = f.read_text(encoding="utf-8", errors="replace")
        # ★ 必须用**抹过注释**的文本扫描：本项目在注释里保留"原装饰器在这里"的说明
        #   （如 main.py 记录 /api/agi/report/export 曾误挂），
        #   用原文扫描会把注释当成路由注册 ⇒ 产出**假冗余**（第一版就报了这条假重复）。
        masked = _strip_prose(raw).split("\n")
        for i, ln in enumerate(masked, 1):
            m = rx.search(ln)
            if m:
                path = m.group(3)
                p = pref.get(f.name, "")
                out.append({"method": m.group(2).upper(),
                            "path": (p + path) if p and not path.startswith(p) else path,
                            "raw_path": path, "file": f.relative_to(ROOT).as_posix(), "line": i})
    return out


def _tables(files: List[pathlib.Path]) -> Dict[str, Any]:
    """真实数据表：ORM `__tablename__`（class 内）+ 运行期 DDL。"""
    orm: Dict[str, List[str]] = defaultdict(list)
    ddl: Dict[str, List[str]] = defaultdict(list)
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for st in node.body:
                    if (isinstance(st, ast.Assign)
                            and any(getattr(t, "id", "") == "__tablename__" for t in st.targets)
                            and isinstance(st.value, ast.Constant)):
                        orm[str(st.value.value)].append("%s:%s" % (f.relative_to(ROOT).as_posix(), node.lineno))
        # ★ 必须扫**全文**：多数 DDL 写在模块级常量里（如 `_DDL_DOCUMENTS = """CREATE TABLE ..."""`），
        #   只在 `execute(...)` 的实参里找会漏掉 17 张表（第一版就漏了，导致 41≠真实数量）。
        raw = f.read_text(encoding="utf-8", errors="replace")
        masked = _strip_prose(raw)
        for m in re.finditer(r"CREATE TABLE IF NOT EXISTS\s+([a-z_]+)", masked):
            ddl[m.group(1)].append(f.relative_to(ROOT).as_posix())
    return {
        "orm": {k: sorted(set(v)) for k, v in sorted(orm.items())},
        "ddl": {k: sorted(set(v)) for k, v in sorted(ddl.items())},
        "both": sorted(set(orm) & set(ddl)),
        "all": sorted(set(orm) | set(ddl)),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    all_files = _py_files()
    files = _py_files(product_only=True)          # 产品代码（阶段 4~12 的判定基准）
    tool_files = [f for f in all_files if f not in files]
    ev: Dict[str, Any] = {
        "product_files": len(files),
        "tool_files": len(tool_files),
        "generated_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        "python_files": len(files),
        "python_lines": sum(len(f.read_text(encoding="utf-8", errors="replace").split("\n")) for f in files),
    }

    # ── 路由与表 ────────────────────────────────────────────────────────────
    routes = _routes(files)
    ev["routes"] = {"total": len(routes), "by_method": dict(
        sorted({m: sum(1 for r in routes if r["method"] == m) for m in {r["method"] for r in routes}}.items()))}
    ev["routes_list"] = routes
    ev["tables"] = _tables(files)

    # ── 阶段 6：可观测性 ────────────────────────────────────────────────────
    ev["observability"] = {
        "health_endpoints": _grep([r'@(app|router)\.get\("/[a-z/-]*(health|ready|live)[a-z/-]*"'], files),
        "logger_calls": _grep([r"logger\.(info|warning|error|debug|exception)\("], files),
        "logger_modules": sorted({h["file"] for h in _grep([r"logging\.getLogger"], files)}),
        "trace_id": _grep([r"trace_id|X-Request-ID|request_id"], files),
        "metrics": _grep([r"prometheus|['\"]/metrics['\"]|cpu_percent|memory_info|psutil"], files),
        "alerting": _grep([r"告警|alert_manager|smtplib|sendmail|webhook"], files),
        "audit": _grep([r"audit_log|ACT_.*=|_audit\("], files),
        "access_log_middleware": _grep([r"access\.jsonl|访问日志|middleware.*log"], files),
    }
    # ★ 2026-10-17：打印 vs 日志的对比 —— 项目大量用 print 而非 logging，
    #   直接影响"日志能否被采集/分级/检索"。这是可观测性评估的核心事实，必须量化。
    _prints = _grep([r"\bprint\("], files)
    ev["observability"]["print_calls"] = _prints
    ev["observability"]["print_vs_logger"] = {
        "print": len(_prints),
        "logger": len(ev["observability"]["logger_calls"]),
        "print_files": len({h["file"] for h in _prints}),
        "logger_files": len(ev["observability"]["logger_modules"]),
    }
    ev["observability"]["per_file"] = {}   # 由下段填充
    # 逐模块统计（按文件）
    per_file = defaultdict(lambda: {"logger": 0, "audit": 0, "trace": 0, "health": 0})
    for key, tag in (("logger_calls", "logger"), ("audit", "audit"), ("trace_id", "trace"),
                     ("health_endpoints", "health")):
        for h in ev["observability"][key]:
            per_file[h["file"]][tag] += 1
    ev["observability"]["per_file"] = dict(sorted(per_file.items()))

    # ── 阶段 7：安全合规 ────────────────────────────────────────────────────
    ev["security"] = {
        "auth": _grep([r"def login|authenticate\(|create_session\(|verify_password"], files),
        "mfa": _grep([r"\bmfa\b|totp|two_factor|双因子|二次验证|otp"], files),
        "rbac": _grep([r"require_permission\(|_require_perm\(|role_permissions|rbac"], files),
        "data_scope": _grep([r"can_access_company|company_ids|_visible_company|数据范围|tenant_id"], files),
        "https_hsts": _grep([r"Strict-Transport-Security|hsts|Secure;|COOKIE_SECURE"], files),
        "at_rest_crypto": _grep([r"fernet|cipher|encrypt|AES|加密存储"], files),
        "masking": _grep([r"mask|脱敏|masked|\*{3,}"], files),
        "csrf": _grep([r"csrf_token|csrf_is_valid|X-CSRF"], files),
        "xss": _grep([r"escapeHtml|html\.escape|bleach|sanitize|textContent\s*="], files),
        "sql_injection": _grep([r"f['\"]SELECT|f['\"]INSERT|f['\"]UPDATE|f['\"]DELETE|\+\s*['\"]\s*WHERE"], files),
        "param_binding": _grep([r"\?\)|:p\b|:\w+\b.*\{|text\("], files),
        "backup": _grep([r"backup|备份"], files),
        "watermark": _grep([r"watermark|水印"], files),
        "pipl_dsll": _grep([r"个人信息保护法|数据安全法|PIPL|DSL|隐私政策"], files),
    }

    # ── 阶段 9：灾难恢复 ────────────────────────────────────────────────────
    ev["dr"] = {
        "backup": _grep([r"backup|备份"], files),
        "restore": _grep([r"restore|恢复(?!默认)|rollback"], files),
        "circuit_breaker": _grep([r"circuit|熔断|breaker|CircuitBreaker"], files),
        "retry": _grep([r"retry|重试|max_retries|backoff"], files),
        "degrade": _grep([r"degrade|降级|fallback"], files),
        "rate_limit": _grep([r"rate_limit|限流|throttle|ratelimit"], files),
        "idempotent": _grep([r"idempot|幂等|Idempotency-Key"], files),
        "atomic_write": _grep([r"atomic_write|os\.replace"], files),
        "graceful_shutdown": _grep([r"lifespan|shutdown|signal\.SIGTERM"], files),
    }

    # ── 阶段 11：CI/CD ──────────────────────────────────────────────────────
    ci_dirs = [d for d in (".github", ".gitlab-ci.yml", "Jenkinsfile", ".travis.yml",
                           "azure-pipelines.yml", ".circleci") if (ROOT / d).exists()]
    hooks = ROOT / ".git" / "hooks"
    custom_hooks = [p.name for p in hooks.iterdir() if p.is_file() and not p.name.endswith(".sample")] \
        if hooks.is_dir() else []
    try:
        tags = subprocess.run(["git", "tag", "--list"], cwd=str(ROOT), capture_output=True,
                              text=True, timeout=20).stdout.split()
        branches = subprocess.run(["git", "branch", "--list"], cwd=str(ROOT), capture_output=True,
                                  text=True, timeout=20).stdout.split()
        log = subprocess.run(["git", "log", "--oneline", "-5"], cwd=str(ROOT), capture_output=True,
                             text=True, timeout=20).stdout.strip().split("\n")
    except (OSError, subprocess.SubprocessError):
        tags, branches, log = [], [], []
    ev["cicd"] = {
        "ci_dirs": ci_dirs,
        "custom_git_hooks": custom_hooks,
        "git_tags": tags,
        "git_branches": [b.strip("* ") for b in branches if b.strip("* ")],
        "recent_commits": log,
        "scripts_verify": sorted(p.name for p in (ROOT / "scripts").glob("*verify*.py")) if (ROOT / "scripts").is_dir() else [],
        "tools_audit": sorted(p.name for p in (ROOT / "tools").glob("*.py")) if (ROOT / "tools").is_dir() else [],
        "start_scripts": sorted(p.name for p in ROOT.glob("start*.bat")),
    }

    # ── 阶段 10：文档知识 ───────────────────────────────────────────────────
    docs = [p for p in ROOT.rglob("*.md") if not any(
        x in str(p).replace("\\", "/") for x in ("/.venv/", "/baseline/", "/trash/", "/_bk"))]
    docinfo = []
    for p in docs:
        rel = p.relative_to(ROOT).as_posix()
        txt = p.read_text(encoding="utf-8", errors="replace")
        docinfo.append({"file": rel, "lines": txt.count("\n") + 1, "chars": len(txt)})
    readme = [d for d in docinfo if d["file"].lower() in ("readme.md", "readme.txt")]
    openapi = _grep([r"openapi|swagger|/docs.*FastAPI\("], files, limit=50)
    ev["docs"] = {
        "md_count": len(docs),
        "total_lines": sum(d["lines"] for d in docinfo),
        "readme": readme,
        "openapi_swagger": openapi,
        "top_files": sorted(docinfo, key=lambda x: -x["lines"])[:15],
        "has_changelog": [d["file"] for d in docinfo if re.search(r"changelog|变更日志|变更记录|版本变更", d["file"], re.I)],
        "deploy_docs": [d["file"] for d in docinfo if re.search(r"部署|deploy|install|安装", d["file"], re.I)],
        "ops_docs": [d["file"] for d in docinfo if re.search(r"运维|ops|故障|排障|troubleshoot", d["file"], re.I)],
        "user_docs": [d["file"] for d in docinfo if re.search(r"用户手册|使用手册|操作指南|user.?guide|manual", d["file"], re.I)],
        "design_docs": [d["file"] for d in docinfo if re.search(r"设计|design|架构|architecture", d["file"], re.I)],
    }

    # ── 阶段 12：伦理合规 ───────────────────────────────────────────────────
    ev["ethics"] = {
        "disclaimer": _grep([r"免责|disclaimer|不构成.{0,8}意见|仅供参考"], files),
        "explainability": _grep([r"依据|basis|legal_citation|evidence_chain|rationale"], files),
        "human_review": _grep([r"人工复核|manual_review|review_states|复核"], files),
        "bias_guard": _grep([r"偏见|bias|公平|fairness|歧视"], files),
        "consent": _grep([r"知情|consent|同意"], files),
        "data_source_legal": _grep([r"官方|税务总局|fgk|legal_catalog|来源页"], files),
        "privacy_min": _grep([r"最小必要|minimal|脱敏|掩码"], files),
    }

    # ── 阶段 5：冗余（候选线索，最终判定需人工确认）─────────────────────────
    ev["redundancy_hints"] = {
        # 同名函数在多个文件重复定义（真实热点，后续阶段 5 逐条判定）
        "dup_function_names": _dup_functions(all_files),
        "dup_route_paths": _dup_routes(routes),
        "similar_modules": _similar_modules(all_files),
    }

    (OUT / "EVIDENCE_BASE.json").write_text(
        json.dumps(ev, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── 控制台摘要（便于人工快速判读）───────────────────────────────────────
    o = ev["observability"]
    print("Python 文件 %d / 行 %d / 路由 %d / 表 %d"
          % (ev["python_files"], ev["python_lines"], len(routes), len(ev["tables"]["all"])))
    print("可观测性：健康检查 %d 处｜日志调用 %d 处（%d 模块）｜trace %d 处｜指标 %d 处｜告警 %d 处｜审计 %d 处"
          % (len(o["health_endpoints"]), len(o["logger_calls"]), len(o["logger_modules"]),
             len(o["trace_id"]), len(o["metrics"]), len(o["alerting"]), len(o["audit"])))
    print("安全：MFA %d｜CSRF %d｜脱敏 %d｜SQL 拼接(可疑) %d｜参数绑定 %d｜备份 %d｜水印 %d｜PIPL/DSL %d"
          % (len(ev["security"]["mfa"]), len(ev["security"]["csrf"]), len(ev["security"]["masking"]),
             len(ev["security"]["sql_injection"]), len(ev["security"]["param_binding"]),
             len(ev["security"]["backup"]), len(ev["security"]["watermark"]), len(ev["security"]["pipl_dsll"])))
    print("灾备：备份 %d｜恢复 %d｜熔断 %d｜重试 %d｜降级 %d｜限流 %d｜幂等 %d｜原子写 %d"
          % (len(ev["dr"]["backup"]), len(ev["dr"]["restore"]), len(ev["dr"]["circuit_breaker"]),
             len(ev["dr"]["retry"]), len(ev["dr"]["degrade"]), len(ev["dr"]["rate_limit"]),
             len(ev["dr"]["idempotent"]), len(ev["dr"]["atomic_write"])))
    print("CI/CD：CI 配置 %s｜自定义 hooks %s｜tag %d｜verify 脚本 %d｜审计工具 %d"
          % (ci_dirs or "无", custom_hooks or "无", len(tags), len(ev["cicd"]["scripts_verify"]),
             len(ev["cicd"]["tools_audit"])))
    print("文档：md %d 篇 / %d 行｜README %d｜OpenAPI %d 处"
          % (ev["docs"]["md_count"], ev["docs"]["total_lines"], len(readme), len(openapi)))
    print("伦理：免责 %d｜可解释 %d｜人工复核 %d｜偏见守卫 %d｜知情 %d"
          % (len(ev["ethics"]["disclaimer"]), len(ev["ethics"]["explainability"]),
             len(ev["ethics"]["human_review"]), len(ev["ethics"]["bias_guard"]), len(ev["ethics"]["consent"])))
    print("\n证据已写入", OUT / "EVIDENCE_BASE.json")
    return 0


def _dup_functions(files: List[pathlib.Path]) -> List[Dict[str, Any]]:
    """同一函数名在多个文件里都有**顶层定义**（冗余的首要嫌疑）。"""
    where: Dict[str, List[str]] = defaultdict(list)
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                where[node.name].append("%s:%d" % (f.relative_to(ROOT).as_posix(), node.lineno))
    dups = []
    for name, locs in where.items():
        fileset = {l.split(":")[0] for l in locs}
        if len(fileset) >= 2:
            dups.append({"name": name, "count": len(locs), "files": sorted(fileset)})
    return sorted(dups, key=lambda x: (-x["count"], x["name"]))


def _dup_routes(routes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """同一 (method, path) 注册了多次（重复注册 = 真冗余/冲突）。"""
    key: Dict[str, List[str]] = defaultdict(list)
    for r in routes:
        key["%s %s" % (r["method"], r["path"])].append("%s:%d" % (r["file"], r["line"]))
    return [{"route": k, "count": len(v), "locs": v} for k, v in key.items() if len(v) > 1]


def _similar_modules(files: List[pathlib.Path]) -> List[Dict[str, Any]]:
    """模块名相近（同义/近义命名）——冗余的次要嫌疑，供阶段 5 人工判定。"""
    stems = sorted({f.stem.lstrip("_") for f in files})
    groups: Dict[str, List[str]] = defaultdict(list)
    for s in stems:
        for kw in ("redline", "review", "risk", "report", "legal", "rule", "project", "document",
                   "industry", "material", "audit", "user", "role", "verify", "score"):
            if kw in s:
                groups[kw].append(s)
                break
    return [{"theme": k, "modules": sorted(set(v)), "count": len(set(v))}
            for k, v in sorted(groups.items()) if len(set(v)) >= 3]


if __name__ == "__main__":
    raise SystemExit(main())

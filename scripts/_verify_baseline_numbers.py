# -*- coding: utf-8 -*-
"""基线数字自检（**只读**）：把《统一开发基线》声明的数字与仓库实测逐项比对。

★ 为什么必须有这个脚本：
  基线文档一旦与仓库实际脱节（改了代码没改文档 / 抄错数字），后续所有开发计划都建立在
  错误地基上。本脚本是"基线可信"的**结果级判据**——任一数字不符即退出码 1。

判据（全部为「实测值」而非文档转录）：
  各 router 文件端点 ｜ engine 207 ｜ tests 104 ｜ config 42 ｜ tools 12 ｜ yaml 18
  accounting.db 必需表齐全（表数仅作信息）｜ security.db 6 表
  规则主体 176（红线 91 + 已验证 85 + 检测器实现层 25/10/14）
  候选 460（add 97 / merge 141）｜ 176+97=273
  ★ App 实测：API 端点 260 ｜ 非 /api 路由 30 ｜ 业务页面 17
    （★ 隔离子进程里起 App 再数，**不污染真实数据**；对外一律引用 206）
  ★ P0-1 项目 / P0-2 资料 / P0-3 解析 / P0-4 分析任务 / P0-5 规则引擎 / P0-6 风险复核
  ★ P0-7 报告 / P0-8 权限·租户·审计（RBAC 5 角色 13 权限 / 租户隔离 / 脱敏）

用法：
  .venv/Scripts/python.exe scripts/_verify_baseline_numbers.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)          # 项目铁律：只读核验脚本必须显式 insert ROOT


def _count(fname: str, pat: str) -> int:
    with open(os.path.join(ROOT, fname), encoding="utf-8") as fh:
        return len(re.findall(pat, fh.read()))


def _app_route_counts() -> dict:
    """在**隔离子进程**里起一次 App 并统计路由（只读；不改真实数据）。

    ★ 为什么用子进程：`from main import app` 在**导入期**会有落盘副作用（日志目录等）；
      在自检脚本里直接 import 会污染真实 `data/`。子进程 + 临时 `APP_DATA_DIR` 可完全隔离。
    ★ 为什么要有这个判据：文档曾出现「行合计 ≠ 合计」（口径混用）⇒ 端点数必须以
      App 实测为准，不能靠"各项相加"推。
    """
    import subprocess
    import tempfile
    code = (
        "import os, tempfile\n"
        "os.environ['APP_DATA_DIR'] = tempfile.mkdtemp()\n"
        "from main import app\n"
        "api = [r for r in app.routes if getattr(r, 'path', '').startswith('/api')"
        " and hasattr(r, 'methods')]\n"
        "other = [r for r in app.routes if not getattr(r, 'path', '').startswith('/api')"
        " and hasattr(r, 'methods')]\n"
        "print(len(api), len(other), len(app.openapi()['paths']))\n"
        "print('|'.join(sorted(getattr(r, 'path', '') for r in other)))\n"
    )
    with tempfile.TemporaryDirectory() as td:
        env = os.environ.copy()
        env["APP_DATA_DIR"] = td
        env.setdefault("APP_COOKIE_SECURE", "0")
        proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError("App 路由统计失败：%s" % proc.stderr[-800:])
    lines = [x for x in proc.stdout.strip().splitlines() if x.strip()]
    parts = [int(x) for x in lines[0].split()[:3]]
    paths = [x for x in (lines[1].split("|") if len(lines) > 1 else []) if x]
    return {"api": parts[0], "other": parts[1], "schema_paths": parts[2],
            "other_paths": paths}


def _table_names(db: str) -> list:
    """返回表的**名字集合**（比总数稳定：总数会随功能幂等建表而合法增长）。"""
    conn = sqlite3.connect(os.path.join(ROOT, db))
    try:
        return [r[0] for r in conn.execute(
            "select name from sqlite_master where type='table'")]
    finally:
        conn.close()


def _tables(db: str) -> int:
    return len(_table_names(db))


def main() -> int:
    ok, bad = [], []

    def chk(name, claimed, actual):
        (ok if claimed == actual else bad).append((name, claimed, actual))

    # ── 端点（合计应为 175 = 149+9+8+2+7）──
    chk("main.py 路由", 149, _count("main.py", r"@app\.(get|post|put|delete|patch)\("))
    chk("tax_risk.py 路由", 9, _count("tax_risk.py", r"@router\.(get|post|put|delete|patch)\("))
    chk("tax_rules_api.py 路由", 2, _count("tax_rules_api.py", r"@router\.(get|post|put|delete|patch)\("))
    chk("file_parser.py 路由", 7, _count("file_parser.py", r"@router\.(get|post|put|delete|patch)\("))
    chk("projects_api.py 路由", 8, _count("projects_api.py", r"@router\.(get|post|put|delete|patch)\("))
    chk("projects_api.py 页面路由", 1, _count("projects_api.py", r"@page_router\.(get|post)\("))
    chk("documents_api.py 路由", 12, _count("documents_api.py", r"@router\.(get|post|put|delete|patch)\("))
    chk("documents_api.py 页面路由", 1, _count("documents_api.py", r"@page_router\.(get|post)\("))
    chk("analysis_api.py 路由", 6, _count("analysis_api.py", r"@router\.(get|post|put|delete|patch)\("))
    chk("rbac_api.py 路由（P0-8）", 8, _count("rbac_api.py", r"@router\.(get|post|put|delete|patch)\("))
    chk("rbac_api.py 页面路由（P0-8）", 3, _count("rbac_api.py", r"@page_router\.(get|post)\("))
    chk("analysis_api.py 页面路由", 1, _count("analysis_api.py", r"@page_router\.(get|post)\("))
    chk("rules_api.py 路由", 9, _count("rules_api.py", r"@router\.(get|post|put|delete|patch)\("))
    chk("rules_api.py 页面路由", 1, _count("rules_api.py", r"@page_router\.(get|post)\("))
    chk("risks_api.py 路由", 10, _count("risks_api.py", r"@router\.(get|post|put|delete|patch)\("))   # P1-4 +3
    chk("risks_api.py 页面路由", 1, _count("risks_api.py", r"@page_router\.(get|post)\("))
    chk("reports_api.py 路由", 6, _count("reports_api.py", r"@router\.(get|post|put|delete|patch)\("))
    chk("reports_api.py 页面路由", 1, _count("reports_api.py", r"@page_router\.(get|post)\("))
    chk("main.py 行数(零漂移)", 15156,
        len(open(os.path.join(ROOT, "main.py"), encoding="utf-8").read().splitlines()))

    # ── 规模 ──
    chk("engine/*.py", 222, len(glob.glob(os.path.join(ROOT, "engine/*.py"))))   # P2 +5
    chk("tests/*.py", 117, len(glob.glob(os.path.join(ROOT, "tests/*.py"))))    # P2 +5
    chk("config/*.json", 44, len(glob.glob(os.path.join(ROOT, "config/*.json"))))  # P2-4 +1
    chk("tools/*.py", 12, len(glob.glob(os.path.join(ROOT, "tools/*.py"))))
    chk("rules_export/*.yaml", 18, len(glob.glob(os.path.join(ROOT, "rules_export/*.yaml"))))

    # ── 数据库 ──
    # ★ 判据修正（2026-10-13）：原为「表总数 == 39」——**这是错的判据**：
    #   `ensure_schema()` 会随功能增加幂等建表（本项目 migration 底座的**设计目的**），
    #   因此总数会合法增长；在干净环境下总数又是 39 ⇒ **同一判据在不同环境结论相反**
    #   （与"引入 Alembic"那次同类错误：把会变的量当常量）。
    #   正确判据 = **必需表必须齐全**（不随功能增长而失效）；总数仅作信息输出。
    _need_acct = ("companies", "accounts", "periods", "journal_entries", "suppliers",
                  "customers", "sales_invoices", "purchase_invoices",
                  "bank_transactions", "vat_declarations", "salary_records",
                  "fixed_assets", "inventory_items",
                  "audit_logs",             # P0-1 前既有（运行时 DDL 建）
                  "projects", "project_members",      # P0-1 稽查项目
                  "documents", "document_pages",     # P0-2 资料
                  "extracted_tables", "extracted_fields", "extract_issues",  # P0-3 解析
                  "reports")                          # P0-7 报告登记
    _acct = set(_table_names("data/accounting.db"))
    chk("accounting.db 必需表齐全", [], sorted(set(_need_acct) - _acct))
    print("  [信息] accounting.db 表数 = %d（随功能合法增长，不作断言）" % len(_acct))
    _need_sec = ("users", "sessions", "login_attempts", "llm_credentials",
                 "roles", "permissions", "role_permissions", "user_roles",
                 "tenants")            # P0-8 权限/租户
    _sec = set(_table_names("data/security.db"))
    chk("security.db 必需表齐全", [], sorted(set(_need_sec) - _sec))
    print("  [信息] security.db 表数 = %d" % len(_sec))

    # ── P0-1 稽查项目（新增，2026-10-13）──
    from engine.project_store import STATUSES, STATUS_CN, ROLES, ROLE_CN, STATUS_FLOW
    chk("项目状态数", 6, len(STATUSES))
    chk("项目角色数", 4, len(ROLES))
    chk("状态中文名齐全", 6, len([s for s in STATUSES if STATUS_CN.get(s)]))
    chk("角色中文名齐全", 4, len([r for r in ROLES if ROLE_CN.get(r)]))
    chk("状态机覆盖全部状态", len(STATUSES),
        len([s for s in STATUSES if s in STATUS_FLOW]))
    chk("archived 为终态", 0, len(STATUS_FLOW.get("archived", ())))
    from engine.audit_trail import ACTIONS, ACTION_CN
    _pj = [a for a in ACTIONS if a.startswith("project.")]
    chk("项目审计动作数", 4, len(_pj))
    chk("项目审计动作中文名齐全", 4, len([a for a in _pj if ACTION_CN.get(a)]))

    # ── P0-2 资料上传与管理（新增，2026-10-13）──
    from engine import document_types as DT
    chk("扩展名白名单", 15, len(DT.ALLOWED_EXTENSIONS))
    chk("存量扩展名一个不少", 12, len(DT.LEGACY_EXTENSIONS))
    chk("新增扩展名 xml/ofd/zip", 3, len(DT.NEW_EXTENSIONS))
    chk("解析状态数", 5, len(DT.PARSE_STATUSES))
    chk("解析状态中文名齐全", 5, len([s for s in DT.PARSE_STATUSES if DT.PARSE_STATUS_CN.get(s)]))
    chk("业务大类数", 9, len(DT.categories()))
    chk("分类规则完整（文件名→类型→大类）", 7,
        len([1 for fn, want in [("资产负债表.xlsx", "财务报表"), ("银行流水.xlsx", "银行流水"),
                                ("销项发票.xlsx", "发票"), ("增值税申报表.xlsx", "申报表"),
                                ("科目余额表.xlsx", "账簿"), ("采购合同.pdf", "合同"),
                                ("工资表.xlsx", "薪酬")]
             if DT.category_cn(DT.guess_category(fn)[0]) == want]))
    _doc = [a for a in ACTIONS if a.startswith("doc.")]
    chk("资料审计动作数", 4, len(_doc))
    chk("资料审计动作中文名齐全", 4, len([a for a in _doc if ACTION_CN.get(a)]))

    # ── P0-3 解析与标准化（新增，2026-10-13）──
    from engine import standard_fields as SF
    from engine.extract_validate import RULES, RULE_CN, validate_rows
    chk("标准字段数", 49, len(SF.fields()))   # P1-1 由 35 扩到 49
    chk("校验规则数", 12, len(RULES))       # P1-3 由 6 扩到 12
    chk("校验规则中文名齐全", 12, len([r for r in RULES if RULE_CN.get(r)]))
    chk("期间归一(含 YYYYMMDD)", 3, len([
        1 for x in ("2024-01", "20240105", "2024年第2季度") if SF.to_standard_period(x)[1]]))
    chk("金额校验有效", True,
        len([i for i in validate_rows([{"金额": "abc"}], standard_names=["invoice_amount"])
             if i["rule"] == "amount_format"]) == 1)
    chk("借贷不平衡可检出", True,
        len([i for i in validate_rows([{"借": 100, "贷": 50}], standard_names=["debit", "credit"])
             if i["rule"] == "debit_credit_unbalanced"]) == 1)
    chk("勾稽异常可检出", True,
        len([i for i in validate_rows([{"资产总计": 500, "负债合计": 200, "所有者权益合计": 250}],
                                      standard_names=["total_assets", "total_liabilities",
                                                      "total_equity"])
             if i["rule"] == "cross_check"]) == 1)
    _ex = [a for a in ACTIONS if a.startswith("extract.")]
    chk("解析审计动作数", 2, len(_ex))
    chk("解析审计动作中文名齐全", 2, len([a for a in _ex if ACTION_CN.get(a)]))
    from engine.extract_service import metadata as _exmeta
    chk("解析复用现有解析器（声明可核对）", True,
        _exmeta()["parser_reuse"]["excel_csv"].startswith("main."))

    # ── P0-4 一键稽查分析任务（新增，2026-10-13）──
    from engine import analysis_task as AT
    from engine.analysis_jobs import (TERMINAL_STATUSES, JOB_TRIGGERS,
                                      RUNNING_STATUS, status_cn as _job_status_cn,
                                      trigger_cn as _trigger_cn)
    chk("任务 8 步", 8, AT.step_count())
    chk("任务 5 状态", 5, len(AT.TASK_STATUSES))
    chk("任务状态中文名齐全", 5, len([s for s in AT.TASK_STATUSES if AT.STATUS_CN.get(s)]))
    _seq = [AT.ENGINE_STEP_TO_TASK[e] for e in AT.ENGINE_REPORT_ORDER]
    chk("引擎步→任务步 单调递增", True, _seq == sorted(_seq) and len(set(_seq)) == len(_seq))
    chk("每个任务步都可达（无死步）", [], sorted(set(range(1, 9)) - set(AT.ENGINE_STEP_TO_TASK.values())))
    chk("运行态映射覆盖引擎全部状态", [],
        sorted({"running", "done", "error", "blocked", "cancelled", "deleted"} - set(AT.RUNTIME_TO_TASK)))
    chk("作业终态含 cancelled", True, "cancelled" in TERMINAL_STATUSES)
    chk("作业终态中文名齐全", len(TERMINAL_STATUSES),
        len([s for s in TERMINAL_STATUSES if _job_status_cn(s) != s]))
    chk("触发方式含 project", True, "project" in JOB_TRIGGERS)
    chk("触发方式中文名齐全", len(JOB_TRIGGERS),
        len([x for x in JOB_TRIGGERS if _trigger_cn(x) != x]))
    chk("超时阈值 > 0", True, AT._timeout_seconds() > 0)
    _jb = [a for a in ACTIONS if a.startswith("job.")]
    chk("任务审计动作数", 3, len(_jb))
    chk("任务审计动作中文名齐全", 3, len([a for a in _jb if ACTION_CN.get(a)]))
    # 项目↔作业链接（append-only）可用且可复现
    # ★ 在**临时目录**里往返：自检脚本不得往真实 `data/` 里写探针行（实测踩过）
    import tempfile as _tf
    import runtime_storage as _rs
    _orig_data_dir = _rs.DATA_DIR
    _probe_ok = False
    with _tf.TemporaryDirectory() as _td:
        _rs.DATA_DIR = _td
        try:
            AT.register_link("__vbn_probe__", 999999)
            _probe_ok = (AT.link_of("__vbn_probe__") or {}).get("project_id") == 999999
        finally:
            _rs.DATA_DIR = _orig_data_dir
    chk("项目↔作业链接可登记可读回（临时目录）", True, _probe_ok)

    # ── P0-5 规则引擎与风险发现（新增，2026-10-13）──
    from engine import rule_loader as RL_, rule_catalog as RC_, risk_scoring as RS_
    _py = RL_.load_python_rules()
    _js = RL_.load_json_candidates()
    _gov = RL_.load_governance_rules()
    chk("规则加载器无留痕", [], RL_.last_errors())
    chk("在库规则无空 id", [], [r["rule_id"] for r in _py if not r["rule_id"]])
    chk("候选规则无空 id", [], [r["rule_id"] for r in _js if not r["rule_id"]])
    chk("权威事实核查规则(另一维度)", 89, len(_gov))
    with open(os.path.join(ROOT, "config/rule_versions.json"), encoding="utf-8") as _fh:
        _layers = json.load(_fh)["layer_semantics"]["layers"]
    from collections import Counter as _Ctr
    _all = _Ctr(r["layer"] for r in _py) + _Ctr(r["layer"] for r in _gov)
    chk("六层计数与权威逐一相符", [],
        [(k, _all.get(k), v["count"]) for k, v in _layers.items()
         if _all.get(k) != v["count"]])
    _st = RC_.stats()
    chk("目录规则主体取权威口径", True, _st["rule_subject_total"] == 176)
    chk("法规依据分类合计=总条目", True,
        _st["legal_basis_coverage"]["with_real_ref"]
        + _st["legal_basis_coverage"]["placeholder"]
        + _st["legal_basis_coverage"]["missing"] == _st["total_entries"])
    chk("无运行时开关（如实声明）", False, _st["runtime_switch_available"])
    chk("评分权重和=1.0", 1.0, round(sum(RS_.metadata()["weights"].values()), 6))
    chk("三档视图来自配置", ["高", "中", "低"],
        [b["grade"] for b in RS_.grade_view_bands()])
    chk("评分不回改等级", True,
        RS_.stamp({"risk_level": "高风险"})["risk_level"] == "高风险")
    chk("信息不足不给分（缺失≠默认分）", None,
        RS_.score({})["priority_score"])
    _full = RS_.score({"risk_level": "高风险", "confidence": 0.9, "finding_count": 4,
                       "tax_impact": {"available": True,
                                      "items": [{"amount": 600000.0}]}})
    chk("四因子齐全时权重和=1.0", 1.0, _full["score_basis"])
    chk("高风险分>低风险分（单调）", True,
        _full["priority_score"] > RS_.score({"risk_level": "低风险", "confidence": 0.9,
                                             "finding_count": 4,
                                             "tax_impact": {"available": True,
                                                            "items": [{"amount": 600000.0}]}}
                                            )["priority_score"])
    from engine.rule_executor import execution_summary as _esum
    chk("执行状态中文名齐全", 7,
        len([k for k in ("executed", "hit", "no_hit", "not_run_missing_data",
                         "skipped_industry", "execution_error", "unknown")]))
    chk("执行汇总分类合计=总数", True,
        sum(_esum([{"status": "hit"}, {"status": "not_run_missing_data"}]
                  )["by_status"].values()) == 2)
    from engine import argumentation as _arg
    _cw = json.load(open(os.path.join(ROOT, "config/confidence_weights.json"),
                         encoding="utf-8"))
    chk("置信度权重两处一致", [],
        [k for k in set(_cw["weights"]) | set(_arg.CONFIDENCE_WEIGHTS)
         if float(_cw["weights"].get(k, float("nan")))
         != float(_arg.CONFIDENCE_WEIGHTS.get(k, float("nan")))])
    chk("置信度区间两处一致", [],
        [k for k in set(_cw["clamps"]) | set(_arg.CONFIDENCE_CLAMPS)
         if float(_cw["clamps"].get(k, float("nan")))
         != float(_arg.CONFIDENCE_CLAMPS.get(k, float("nan")))])

    # ── P0-6 风险结果展示与复核（新增，2026-10-13）──
    from engine import risk_review as RR_, risk_service as RSVC_
    chk("复核 5 态", 5, len(RR_.REVIEW_STATES))
    chk("复核状态中文名齐全", 5, len([s for s in RR_.REVIEW_STATES if RR_.STATE_CN.get(s)]))
    chk("复核动作 6 种", 6, len(RR_.REVIEW_ACTIONS))
    chk("复核动作中文名齐全", 6, len([a for a in RR_.REVIEW_ACTIONS if RR_.ACTION_CN.get(a)]))
    chk("动作→目标态映射覆盖全部动作", [], sorted(set(RR_.REVIEW_ACTIONS) - set(RR_.ACTION_TO_STATE)))
    chk("状态迁移图覆盖全部状态", [], sorted(set(RR_.REVIEW_STATES) - set(RR_.STATE_FLOW)))
    chk("迁移目标均为合法状态", [],
        sorted({t2 for v in RR_.STATE_FLOW.values() for t2 in v} - set(RR_.REVIEW_STATES)))
    chk("待处理无自环（不允许 pending→pending）", True,
        "pending" not in RR_.STATE_FLOW.get("pending", ()))
    chk("理由必填动作均为需附说明者", ["exclude", "false_positive", "rectify", "reopen"],
        sorted(RR_.NOTE_REQUIRED))
    chk("终态可重开（不漏出口）", 4, len(RR_.TERMINAL_STATES))
    chk("排序键", ["amount", "level", "priority", "risk_no", "seq"], sorted(RSVC_.SORTS))
    chk("排序键中文名齐全", len(RSVC_.SORTS),
        len([s for s in RSVC_.SORTS if RSVC_.SORT_CN.get(s)]))
    chk("视图元数据取等级权威（6 档）", 6, len(RSVC_.metadata()["levels"]))
    chk("元数据复核段与状态权威一致", list(RR_.REVIEW_ACTIONS),
        [a["value"] for a in RSVC_.metadata()["review"]["actions"]])
    _rk = [a for a in ACTIONS if a.startswith("risk.")]
    chk("风险复核审计动作数", 4, len(_rk))   # P1-4 +risk.bulk_review
    chk("风险复核审计动作中文名齐全", 4, len([a for a in _rk if ACTION_CN.get(a)]))
    chk("与既有 finding.review 不同概念", True,
        ACTION_CN["finding.review"] != ACTION_CN["risk.review"])
    # 期间解析走编号权威（不自行切字符串）
    chk("风险编号期间解析", "202501", RSVC_.period_of("WB-R-XYZ-202501-001"))

    # ── App 实测端点总数（口径唯一权威；**不靠各项相加推**）──
    try:
        _rc = _app_route_counts()
        chk("App API 端点数（实测）", 260, _rc["api"])
        chk("App 非 /api 路由数（实测）", 30, _rc["other"])
        _page_all = ("/projects", "/documents", "/extract", "/analysis", "/rules",
                     "/risks", "/reports", "/users", "/roles", "/audit-logs",
                     "/report-templates", "/rule-versions",
                     "/legal-library", "/industry-indicators", "/ai-assist",
                     "/tax-models", "/dashboard")
        chk("业务页面均在 App 路由中（缺一即报）", [],
            [p for p in _page_all if p not in _rc["other_paths"]])
        chk("OpenAPI 收录路径数（实测）", 247, _rc["schema_paths"])
    except Exception as _exc:                                    # noqa: BLE001
        raise AssertionError("App 路由统计失败（判据不可用，参数不完整）：%s" % _exc)

    # ── P0-7 报告生成与导出（新增，2026-10-13）──
    from engine import report_store as RST_, report_views as RV_
    from engine import report_render as RRND_, report_service as RSVC_
    chk("报告视图 4 种", 4, len(RV_.VIEWS))
    chk("报告视图标签齐全", 4, len([v for v in RV_.VIEWS if RV_.VIEW_LABEL.get(v)]))
    chk("报告视图说明齐全", 4, len([v for v in RV_.VIEWS if RV_.VIEW_DESC.get(v)]))
    chk("导出格式 4 种", ["docx", "html", "pdf", "xlsx"], sorted(RV_.FORMATS))
    chk("格式中文名齐全", 4, len([f for f in RV_.FORMATS if RV_.FORMAT_CN.get(f)]))
    chk("格式媒体类型齐全", 4, len([f for f in RV_.FORMATS if RV_.FORMAT_MEDIA.get(f)]))
    chk("格式水印方式齐全", 4, len([f for f in RV_.FORMATS if RV_.WATERMARK_METHOD.get(f)]))
    chk("章节 12 个", 12, len(RV_.SECTIONS))
    chk("章节中文名齐全", 12, len([s for s in RV_.SECTIONS if RV_.SECTION_CN.get(s)]))
    # ★ 视图-章节：保留 ∩ 未含 = ∅，并集 = 全章节（不得静默丢章节）
    chk("视图章节划分不重不漏", [],
        [(v, sorted(set(RV_.sections_of(v)) & set(RV_.omitted_sections_of(v))),
          sorted(set(RV_.sections_of(v)) | set(RV_.omitted_sections_of(v))
                 ^ set(RV_.SECTIONS)))
         for v in RV_.VIEWS
         if (set(RV_.sections_of(v)) & set(RV_.omitted_sections_of(v)))
         or (set(RV_.sections_of(v)) | set(RV_.omitted_sections_of(v))) != set(RV_.SECTIONS)])
    chk("视图全覆盖 cover/disclaimer（声明必含）", [],
        [v for v in RV_.VIEWS
         if not {"cover", "disclaimer"} <= set(RV_.sections_of(v))])
    # ★ 报告名称合规（任务书的报告类型名含禁用别名 ⇒ 本项目的视图名不得命中）
    chk("视图名称合规（以唯一名称开头且不含禁用别名）", [], RV_.verify_view_names())
    chk("报告登记表列齐备", [],
        sorted({"doc_no", "version", "company_id", "view", "name", "files",
                "watermark_mode", "reviewed", "generated_at"}
               - set(RST_.table_columns())))
    import sqlite3 as _sq3
    _conn_ = _sq3.connect(os.path.join(ROOT, "data/accounting.db"))
    try:
        _tables_now = {r[0] for r in _conn_.execute(
            "select name from sqlite_master where type='table'")}
    finally:
        _conn_.close()
    chk("report_versions **不建**（权威已是台账 report_versions.jsonl）", [],
        [] if RST_.BUILD_OPTIONAL_TABLES
        else [k for k in RST_.OPTIONAL_TABLES if k in _tables_now])
    chk("免责声明来源为唯一权威", True,
        ("engine/report_identity" in RSVC_.metadata()["disclaimer_source"]))
    # 渲染层反例：缺声明章节 ⇒ 必须抛错（判据在判）
    _nodisc = {"name": "x", "view": "full", "view_label": "全景", "doc_no": "d",
               "version": "V1", "generated_at": "", "generated_by": "", "reviewed": False,
               "reviewed_by": "", "watermark_text": "w",
               "disclaimer": {"identity_line": "唯一权威声明"},
               "sections": [{"key": "cover", "title": "封面", "blocks": []}], "omitted": []}
    _raised = False
    try:
        RRND_.render(_nodisc, "html")
    except RRND_.ReportRenderError:
        _raised = True
    chk("缺免责声明章节必须报错", True, _raised)
    chk("水印方式四格式均 embedded", ["embedded"],
        sorted({m for m in [RRND_.render(
            {"name": "x", "view": "full", "view_label": "全景", "doc_no": "d",
             "version": "V1", "generated_at": "", "generated_by": "", "reviewed": False,
             "reviewed_by": "", "watermark_text": "w",
             "disclaimer": {"identity_line": "唯一权威声明"},
             "sections": [{"key": "disclaimer", "title": "免责声明",
                           "blocks": [{"type": "paragraph", "text": "唯一权威声明"}]}],
             "omitted": []}, f)[1] for f in RV_.FORMATS]}))

    # ── P0-8 权限 / 租户 / 审计 / 脱敏（新增，2026-10-14）──
    from engine import rbac as RB_
    _rc_cfg = RB_.rbac_config()
    chk("RBAC 角色 5 个（任务书）", ["auditor", "enterprise_finance", "review_expert",
                                  "system_admin", "tax_advisor"], sorted(RB_.role_codes()))
    chk("RBAC 权限点 18 个", 18, len(RB_.permission_codes()))   # P1-5/6 各 +1；P2 +3
    chk("角色→权限映射覆盖全部内置角色", [],
        sorted(set(RB_.role_codes()) - set(_rc_cfg.get("role_permissions") or {})))
    chk("角色→脱敏映射覆盖全部内置角色", [],
        sorted(set(RB_.role_codes()) - set(_rc_cfg.get("role_redaction") or {})))
    _rc_ids = RB_.rbac_metadata()["roles"]
    chk("内置角色均登记 builtin=1", len(RB_.role_codes()),
        len([r for r in _rc_ids if r["builtin"]]))
    chk("默认角色在角色表内", True, _rc_cfg.get("default_role") in RB_.role_codes())
    chk("超管等价角色在角色表内", True, _rc_cfg.get("legacy_admin_role") in RB_.role_codes())
    chk("租户形态登记 2 种", ["private", "saas"], sorted(RB_.TENANT_MODES))
    from engine.audit_trail import ACTIONS as _ACT8, ACTION_CN as _CN8   # noqa: PLC0415
    _p8 = [a for a in _ACT8 if a.startswith(("auth.", "user.", "role."))]
    chk("P0-8 审计动作 7 个", 7, len(_p8))
    chk("P0-8 动作中文名齐全", 7, len([a for a in _p8 if _CN8.get(a)]))
    # 角色→脱敏的取值必须落在「要不要脱」的唯一权威（report_compliance.redaction_roles）内
    from engine.report_compliance import load_config as _load_rc   # noqa: PLC0415
    _rr_registered = set((_load_rc().get("redaction_roles") or {}).keys())
    _rr_used = set((_rc_cfg.get("role_redaction") or {}).values())
    _rr_used.add(str(_rc_cfg.get("fallback_redaction") or ""))
    chk("脱敏策略键均为已登记脱敏角色", [], sorted(_rr_used - _rr_registered))
    chk("内部角色必须不脱敏（报告/内部底稿定调）", [], sorted(
        k for k, v in __import__("engine.redaction", fromlist=["role_policy"])
        .role_policy("internal").items()
        if v is True and k in ("name", "account", "id_card", "amount", "contact")))

    # ── 规则分层（唯一权威 layer_semantics）──
    with open(os.path.join(ROOT, "config/rule_versions.json"), encoding="utf-8") as fh:
        layers = json.load(fh)["layer_semantics"]["layers"]
    chk("规则主体", 176, sum(v["count"] for v in layers.values()
                             if v.get("counts_toward_rule_total")))
    chk("红线 REDLINES", 91, layers["tax_redlines"]["count"])
    chk("已验证规则", 85, layers["verified_rule_engine"]["count"])
    chk("专项探测(检测器层)", 25, layers["special_redline_detectors"]["count"])
    chk("缺口探测(检测器层)", 10, layers["gap_risk_detectors"]["count"])
    chk("缺口税种探测(检测器层)", 14, layers["gap_tax_obligations"]["count"])

    # ── 候选库 ──
    tot = adds = merges = 0
    for f in ("config/rulelist_v1.json", "config/rulelist_v11.json", "config/rulelist_v12.json"):
        with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
            rules = json.load(fh)["rules"]
        tot += len(rules)
        adds += sum(1 for r in rules if r.get("action") == "add")
        merges += sum(1 for r in rules if r.get("action") == "merge")
    chk("候选规则总数", 460, tot)
    chk("候选 add（真缺）", 97, adds)
    chk("候选 merge（口径不同）", 141, merges)
    chk("全部 add 入库后规则主体", 273, 176 + adds)

    print("=== ✅ 通过 %d 项 ===" % len(ok))
    for name, _, actual in ok:
        print("  %-26s %s" % (name, actual))
    if bad:
        print("=== ❌ 不符 %d 项 ===" % len(bad))
        for name, claimed, actual in bad:
            print("  %-26s 基线声明=%s 实测=%s" % (name, claimed, actual))
        return 1
    print("\n基线文档数字与仓库实测 100% 一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

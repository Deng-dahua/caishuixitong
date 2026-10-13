# -*- coding: utf-8 -*-
"""基线数字自检（**只读**）：把《统一开发基线》声明的数字与仓库实测逐项比对。

★ 为什么必须有这个脚本：
  基线文档一旦与仓库实际脱节（改了代码没改文档 / 抄错数字），后续所有开发计划都建立在
  错误地基上。本脚本是"基线可信"的**结果级判据**——任一数字不符即退出码 1。

判据（全部为「实测值」而非文档转录）：
  端点 149/9/2/7 ｜ engine 190 ｜ tests 98 ｜ config 38 ｜ tools 12 ｜ yaml 18
  accounting.db 39 表 ｜ security.db 6 表
  规则主体 176（红线 91 + 已验证 85 + 检测器实现层 25/10/14）
  候选 460（add 97 / merge 141）｜ 176+97=273
  ★ P0-1 稽查项目（2026-10-13 新增）：projects/project_members 两表 + 8 个 API 端点 + 6 状态 + 4 角色
    + 4 个审计动作 + 页面路由 /projects

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
    chk("analysis_api.py 页面路由", 1, _count("analysis_api.py", r"@page_router\.(get|post)\("))
    chk("main.py 行数(零漂移)", 15156,
        len(open(os.path.join(ROOT, "main.py"), encoding="utf-8").read().splitlines()))

    # ── 规模 ──
    chk("engine/*.py", 201, len(glob.glob(os.path.join(ROOT, "engine/*.py"))))
    chk("tests/*.py", 102, len(glob.glob(os.path.join(ROOT, "tests/*.py"))))
    chk("config/*.json", 40, len(glob.glob(os.path.join(ROOT, "config/*.json"))))
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
                  "extracted_tables", "extracted_fields", "extract_issues")  # P0-3 解析
    _acct = set(_table_names("data/accounting.db"))
    chk("accounting.db 必需表齐全", [], sorted(set(_need_acct) - _acct))
    print("  [信息] accounting.db 表数 = %d（随功能合法增长，不作断言）" % len(_acct))
    _need_sec = ("users", "sessions", "login_attempts", "llm_credentials")
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
    chk("标准字段数", 35, len(SF.fields()))
    chk("校验规则数", 6, len(RULES))
    chk("校验规则中文名齐全", 6, len([r for r in RULES if RULE_CN.get(r)]))
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

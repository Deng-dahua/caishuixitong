# -*- coding: utf-8 -*-
"""解析产物（P0-3）**数据库底座**：`extracted_tables` / `extracted_fields` / `extract_issues`。

★ migration 方式：沿用项目既有底座（`audit_trail.ensure_schema` 同一模式）——
  幂等建表 + 幂等加列 + 索引 + `inspector` 守卫，按 engine 身份缓存。**不引入 Alembic**。

★★ 为什么只建这 3 张表（任务书点了 4 张，第 4 张已存在等价物）
  任务书：「数据表 extracted_tables、financial_data、tax_returns、invoices（**沿用现有**，缺失用 migration 补）」。

  | 任务书表名 | 处置 | 依据 |
  |---|---|---|
  | `extracted_tables` | ✅ **新建**（本模块） | 现有确无"解析产物登记"这一概念 |
  | `extracted_fields` | ✅ **新建**（本模块） | "标准化到统一字段"的载体；含 `standard_field` + **来源行号** ⇒ 满足"可回链原始文件" |
  | `extract_issues` | ✅ **新建**（本模块） | 校验异常清单（6 类规则的结果落点），现有无 |
  | `financial_data` | ❌ **沿用现有** | 现有已有语义等价的**结构化落库表**：`accounts` / `journal_entries` / `periods`（科目、凭证、期间）。再造一张 `financial_data` 会形成"一个概念两处存放" |
  | `tax_returns` | ❌ **沿用现有** | 现有已有 `vat_declarations` / `social_security_declarations` / `housing_fund_declarations` / `cultural_construction_fee_declarations`（按税种/费种分表） |
  | `invoices` | ❌ **沿用现有** | 现有已有 `sales_invoices` / `purchase_invoices` / `bookkeeping_invoices` / `input_vat_deductions` |

  ⇒ 标准化的**落点**是「`extracted_fields` 登记标准字段 + 值 + 来源」，
    再按域回填/回链到上述**现有业务表**；**不新建三张同义表**（新增同义表 = 多头维护）。
  ⚠ 若业务确需同名独立表，本文件的 `OPTIONAL_TABLES` 已给出 DDL（**加一行即建**），
    但默认不建 —— 见交付报告「需用户裁定」项。

★ 回链：`extracted_fields.source_ref` 记 `{sheet, row, col, raw_value}`，
  `extracted_tables.document_id` → `documents.id`（P0-2）⇒ **任何标准值可回溯到原文件的具体单元格**。
"""
from __future__ import annotations

import threading
from typing import Dict, List, Optional, Tuple

_DDL_EXTRACTED_TABLES = """
CREATE TABLE IF NOT EXISTS extracted_tables (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id  INTEGER NOT NULL,
    project_id   INTEGER,
    company_id   INTEGER,
    sheet_name   TEXT,
    doc_type     TEXT,
    confidence   REAL DEFAULT 0,
    detect_source TEXT,
    header       TEXT,
    row_count    INTEGER DEFAULT 0,
    col_count    INTEGER DEFAULT 0,
    rows_json    TEXT,
    parse_status TEXT DEFAULT 'success',
    parsed_at    TEXT
)
"""

_DDL_EXTRACTED_FIELDS = """
CREATE TABLE IF NOT EXISTS extracted_fields (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id    INTEGER NOT NULL,
    table_id       INTEGER,
    project_id     INTEGER,
    company_id     INTEGER,
    standard_field TEXT NOT NULL,
    field_cn       TEXT,
    domain         TEXT,
    value_text     TEXT,
    value_amount   REAL,
    value_period   TEXT,
    source_ref     TEXT,
    confidence     REAL DEFAULT 0,
    corrected      INTEGER DEFAULT 0,
    corrected_by   TEXT,
    corrected_at   TEXT,
    original_value TEXT
)
"""

_DDL_EXTRACT_ISSUES = """
CREATE TABLE IF NOT EXISTS extract_issues (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id   INTEGER NOT NULL,
    table_id      INTEGER,
    project_id    INTEGER,
    company_id    INTEGER,
    rule          TEXT NOT NULL,
    severity      TEXT DEFAULT 'warning',
    message       TEXT,
    detail_json   TEXT,
    status        TEXT DEFAULT 'open',
    resolved_by   TEXT,
    resolved_at   TEXT,
    created_at    TEXT
)
"""

_IDX = (
    "CREATE INDEX IF NOT EXISTS ix_extracted_tables_doc ON extracted_tables (document_id)",
    "CREATE INDEX IF NOT EXISTS ix_extracted_fields_doc ON extracted_fields (document_id, standard_field)",
    "CREATE INDEX IF NOT EXISTS ix_extracted_fields_project ON extracted_fields (project_id, domain)",
    "CREATE INDEX IF NOT EXISTS ix_extract_issues_doc ON extract_issues (document_id, rule, status)",
)

#: 幂等加列声明
_WANT_COLUMNS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "extracted_tables": (
        ("project_id", "INTEGER"), ("company_id", "INTEGER"), ("sheet_name", "TEXT"),
        ("doc_type", "TEXT"), ("confidence", "REAL"), ("detect_source", "TEXT"),
        ("header", "TEXT"), ("row_count", "INTEGER"), ("col_count", "INTEGER"),
        ("rows_json", "TEXT"), ("parse_status", "TEXT"), ("parsed_at", "TEXT"),
    ),
    "extracted_fields": (
        ("table_id", "INTEGER"), ("project_id", "INTEGER"), ("company_id", "INTEGER"),
        ("field_cn", "TEXT"), ("domain", "TEXT"), ("value_text", "TEXT"),
        ("value_amount", "REAL"), ("value_period", "TEXT"), ("source_ref", "TEXT"),
        ("confidence", "REAL"), ("corrected", "INTEGER"), ("corrected_by", "TEXT"),
        ("corrected_at", "TEXT"), ("original_value", "TEXT"),
    ),
    "extract_issues": (
        ("table_id", "INTEGER"), ("project_id", "INTEGER"), ("company_id", "INTEGER"),
        ("rule", "TEXT"), ("severity", "TEXT"), ("message", "TEXT"),
        ("detail_json", "TEXT"), ("status", "TEXT"), ("resolved_by", "TEXT"),
        ("resolved_at", "TEXT"), ("created_at", "TEXT"),
    ),
}

#: ★ 任务书点名、但**默认不建**的 3 张表（现有已有语义等价表）。
#: 若业务确需独立表：把对应 DDL 从注释中启用即可（**加一行，不改逻辑分支**）。
OPTIONAL_TABLES: Dict[str, str] = {
    "financial_data": (
        "CREATE TABLE IF NOT EXISTS financial_data (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "document_id INTEGER, project_id INTEGER, company_id INTEGER, period TEXT, "
        "account_code TEXT, account_name TEXT, amount REAL, standard_field TEXT, "
        "source_ref TEXT, created_at TEXT)"
    ),
    "tax_returns": (
        "CREATE TABLE IF NOT EXISTS tax_returns (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "document_id INTEGER, project_id INTEGER, company_id INTEGER, period TEXT, "
        "tax_type TEXT, taxable_amount REAL, tax_payable REAL, source_ref TEXT, created_at TEXT)"
    ),
    "invoices": (
        "CREATE TABLE IF NOT EXISTS invoices (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "document_id INTEGER, project_id INTEGER, company_id INTEGER, direction TEXT, "
        "invoice_no TEXT, invoice_date TEXT, buyer TEXT, seller TEXT, amount REAL, "
        "tax REAL, total REAL, source_ref TEXT, created_at TEXT)"
    ),
}
#: 是否建可选表（默认 False ⇒ **沿用现有同义表**；置 True 即建，不影响既有逻辑）
BUILD_OPTIONAL_TABLES = False

_SCHEMA_READY_ENGINE: Optional[int] = None
_SCHEMA_LOCK = threading.Lock()


def _default_engine():
    from database import engine as _engine            # noqa: PLC0415
    return _engine


def ensure_schema(engine=None) -> None:
    """**幂等**建表 + 幂等加列 + 索引。可在任何时候重复调用。"""
    global _SCHEMA_READY_ENGINE
    eng = engine if engine is not None else _default_engine()
    if _SCHEMA_READY_ENGINE == id(eng):
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY_ENGINE == id(eng):
            return
        from sqlalchemy import inspect as _inspect, text as _text   # noqa: PLC0415
        with eng.begin() as conn:
            conn.execute(_text(_DDL_EXTRACTED_TABLES))
            conn.execute(_text(_DDL_EXTRACTED_FIELDS))
            conn.execute(_text(_DDL_EXTRACT_ISSUES))
            if BUILD_OPTIONAL_TABLES:
                for _ddl in OPTIONAL_TABLES.values():
                    conn.execute(_text(_ddl))
            for tbl, cols in _WANT_COLUMNS.items():
                have = {c["name"] for c in _inspect(conn).get_columns(tbl)}
                for cname, ctype in cols:
                    if cname not in have:
                        conn.execute(_text(
                            "ALTER TABLE %s ADD COLUMN %s %s" % (tbl, cname, ctype)))
            for sql in _IDX:
                conn.execute(_text(sql))
        _SCHEMA_READY_ENGINE = id(eng)


def reset_cache() -> None:
    """仅供测试：清掉"已就绪"缓存。"""
    global _SCHEMA_READY_ENGINE
    _SCHEMA_READY_ENGINE = None


def table_columns(engine=None, table: str = "extracted_tables") -> List[str]:
    """只读：返回某表当前列名（供闸门/测试断言 schema 与声明一致）。"""
    from sqlalchemy import inspect as _inspect        # noqa: PLC0415
    eng = engine if engine is not None else _default_engine()
    ensure_schema(eng)
    with eng.connect() as conn:
        return [c["name"] for c in _inspect(conn).get_columns(table)]

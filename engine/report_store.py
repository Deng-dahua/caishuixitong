# -*- coding: utf-8 -*-
"""报告交付物登记（P0-7）的**数据库底座**：幂等建表 + 幂等加列 + 索引。

★★ 为什么不引入 alembic（与项目既有裁定一致，勿改）
  `engine/audit_trail.py` 已把「**幂等建表 + 幂等加列**」确立为本项目的 **migration 底座**。
  本模块**沿用同一模式**（第三个实例，前两个是 `audit_trail` / `project_store`）：
    · 表不存在 ⇒ `CREATE TABLE IF NOT EXISTS`（列与顺序**逐字固定**）；
    · 新列缺失 ⇒ `ALTER TABLE ... ADD COLUMN`（SQLite 安全、向后兼容）；
    · 索引缺失 ⇒ `CREATE INDEX IF NOT EXISTS`；
    · `inspector` 守卫幂等；按 **engine 身份**缓存。

★★ 关于任务书要求的 `reports` / `report_versions` 两张表（**如实说明**）

| 任务书 | 本模块处理 | 理由 |
|---|---|---|
| `reports` | ✅ **建**（本模块 `_DDL_REPORTS`） | 这是**新概念**：一次"生成"产出的**交付物实例**（视图/格式/文件路径/水印方式）—— 全项目**无**等价载体 |
| `report_versions` | ❌ **不建**（DDL 放在 `OPTIONAL_TABLES`，加一行即建） | 版本/文书编号的**唯一权威已存在** = `data/report_versions.jsonl`（`engine/report_compliance` 的 append-only 台账，字段含 `doc_no`/`version`/`company_id`/`reviewed`/`analysis_id`）。再建一张表存同一批字段 ⇒ **一个概念两处存放**（本项目明令禁止，P0-3 已有先例：`financial_data` 等亦未建） |

⇒ 两表**关系**：`reports.doc_no` 是**指向**版本台账的指针（外键式引用），
  **不复制**台账字段 —— 版本信息一律回台账读（`report_compliance` 仍是唯一权威）。

★ 租户边界：沿用 `company_id`（与 `SessionContext.can_access_company()` 同一口径）。
"""
from __future__ import annotations

import threading
from typing import Dict, List

# --------------------------------------------------------------------------
# DDL（列与顺序**逐字固定**；新增列一律走下方"幂等加列"，不改本串）
# --------------------------------------------------------------------------
_DDL_REPORTS = """
CREATE TABLE IF NOT EXISTS reports (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_no         TEXT,                 -- ★ 台账行指针之一：(doc_no, version) 共同标识台账那一行（非副本）
    version        TEXT,                 -- ★ 台账行指针之二（见上）
    project_id     INTEGER,
    company_id     INTEGER NOT NULL,
    view           TEXT NOT NULL,        -- 视图（全景/分税种专项/管理层摘要/税务自查）
    name           TEXT,                 -- 报告名称（= canonical（视图标签），由 report_compliance 下发）
    period_start   TEXT,
    period_end     TEXT,
    reviewed       INTEGER DEFAULT 0,    -- 人工复核标识
    reviewed_by    TEXT,
    watermark_mode TEXT,                 -- embedded / sidecar（如实）
    watermark_text TEXT,
    formats        TEXT,                 -- JSON 数组：已产出的格式
    files          TEXT,                 -- JSON 对象：{格式: 相对路径}
    section_count  INTEGER DEFAULT 0,
    finding_count  INTEGER DEFAULT 0,
    tax_count      INTEGER DEFAULT 0,
    omitted_sections TEXT,               -- JSON 数组：本视图未含的章节（**如实登记，不静默**）
    generated_at   TEXT,
    generated_by   TEXT,
    analysis_id    TEXT,                 -- 回指分析作业（P0-4）
    change_note    TEXT,
    status         TEXT DEFAULT 'ready'  -- ready / failed
)
"""

_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_reports_company ON reports(company_id, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_reports_project ON reports(project_id, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_reports_doc_no ON reports(doc_no)",
)

#: 可选表（**默认不建**）。任务书点名 `report_versions` —— 其权威已是
#: `data/report_versions.jsonl`（`engine/report_compliance`）⇒ 不建同义表。
#: 若业务确需同名独立表：`BUILD_OPTIONAL_TABLES = True` 或调用 `ensure_optional()`。
OPTIONAL_TABLES: Dict[str, str] = {
    "report_versions": (
        "CREATE TABLE IF NOT EXISTS report_versions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, doc_no TEXT, company_id TEXT, "
        "doc_name TEXT, edition_kind TEXT, version TEXT, generated_at TEXT, "
        "generator TEXT, system_version TEXT, reviewed INTEGER, "
        "redaction_role TEXT, change_note TEXT, analysis_id TEXT)"
    ),
}

#: 是否建可选表（★ 唯一开关；置 True 即建，不改任何逻辑分支）
BUILD_OPTIONAL_TABLES = False

_SCHEMA_LOCK = threading.RLock()
_SCHEMA_READY_ENGINE = None


def _default_engine():
    from database import engine as _engine          # noqa: PLC0415
    return _engine


def ensure_schema(engine=None) -> None:
    """**幂等**建表 + 幂等加列 + 索引。**可在任何时候重复调用**。"""
    global _SCHEMA_READY_ENGINE
    eng = engine if engine is not None else _default_engine()
    if _SCHEMA_READY_ENGINE == id(eng):
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY_ENGINE == id(eng):
            return
        from sqlalchemy import inspect as _inspect, text as _text   # noqa: PLC0415
        with eng.begin() as conn:
            conn.execute(_text(_DDL_REPORTS))
            # ── 幂等加列（历史上新增的列在此逐条判存在；新列一律 ADD COLUMN）──
            _want = (
                ("doc_no", "TEXT"), ("version", "TEXT"),
                ("project_id", "INTEGER"), ("name", "TEXT"),
                ("period_start", "TEXT"), ("period_end", "TEXT"),
                ("reviewed", "INTEGER"), ("reviewed_by", "TEXT"),
                ("watermark_mode", "TEXT"), ("watermark_text", "TEXT"),
                ("files", "TEXT"), ("section_count", "INTEGER"),
                ("finding_count", "INTEGER"), ("tax_count", "INTEGER"),
                ("omitted_sections", "TEXT"), ("generated_at", "TEXT"),
                ("generated_by", "TEXT"), ("analysis_id", "TEXT"),
                ("change_note", "TEXT"), ("status", "TEXT"),
            )
            _have = {c["name"] for c in _inspect(conn).get_columns("reports")}
            for _cname, _ctype in _want:
                if _cname not in _have:
                    conn.execute(_text(
                        "ALTER TABLE reports ADD COLUMN %s %s" % (_cname, _ctype)))
            for _sql in _IDX:
                conn.execute(_text(_sql))
            if BUILD_OPTIONAL_TABLES:
                for _sql in OPTIONAL_TABLES.values():
                    conn.execute(_text(_sql))
        _SCHEMA_READY_ENGINE = id(eng)


def ensure_optional(engine=None) -> List[str]:
    """建**可选表**（默认不建）。返回已建表名（供显式声明用途）。"""
    eng = engine if engine is not None else _default_engine()
    from sqlalchemy import text as _text                          # noqa: PLC0415
    ensure_schema(eng)
    with eng.begin() as conn:
        for _sql in OPTIONAL_TABLES.values():
            conn.execute(_text(_sql))
    return sorted(OPTIONAL_TABLES)


def reset_cache() -> None:
    """仅供测试：清掉"已就绪"缓存，使下一次 `ensure_schema` 真跑一遍。"""
    global _SCHEMA_READY_ENGINE
    _SCHEMA_READY_ENGINE = None


def table_columns(engine=None, table: str = "reports") -> List[str]:
    """只读：返回某表当前列名（供闸门/测试断言 schema 与声明一致）。"""
    from sqlalchemy import inspect as _inspect                    # noqa: PLC0415
    eng = engine if engine is not None else _default_engine()
    ensure_schema(eng)
    with eng.connect() as conn:
        return [c["name"] for c in _inspect(conn).get_columns(table)]

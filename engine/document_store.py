# -*- coding: utf-8 -*-
"""资料（P0-2）**数据库底座**：`documents` / `document_pages` 两表 + 索引。

★ migration 方式：沿用项目既有底座（与 `engine/audit_trail.py`、`engine/project_store.py`
  同一模式）—— **幂等建表 + 幂等加列 + 索引 + `inspector` 守卫**，按 engine 身份缓存。
  **不引入 Alembic**（见 `audit_trail.py` 的既有裁定：与"不擅自更换技术栈"冲突）。

★ 对象存储：**本项目无对象存储**（`requirements.lock` 无 minio/boto3/oss2）。
  任务书「MinIO / S3 / OSS（**以现有为准**）」⇒ **以现有为准 = 本地文件系统**，
  路径唯一权威 = `runtime_storage.company_upload_dir(company_id)`（`data/uploads/<cid>/`）。
  **不引入对象存储 SDK**（那会新增依赖、并造成"一份资料两个存放地"）。

★ 与既有资料清单的关系（**避免两套清单**）
  既有 `/api/tax-risk-docs/*` 用**内存列表 + 磁盘扫描**维护资料清单，落盘目录
  `data/uploads/<cid>/`、文件名 `{cid}_{docid}_{原名}`。
  本模块的 `documents` 表是**新增的结构化登记**，但：
    · **同一目录**（复用 `company_upload_dir`）、**同一编号空间**（复用既有 `_tax_doc_counter`）、
      **同一命名规范** ⇒ 不产生"两份资料"；
    · 新接口上传的文件**同时登记进既有清单**（由 `document_service._bridge_to_legacy` 完成）
      ⇒ 一键分析**仍能看到**新上传的资料（否则会造成"传了但分析看不到"的功能缺口）。
  既有清单的内存侧不改（零风险），两侧通过"同一目录 + 同一编号 + 桥接登记"保持一致。
"""
from __future__ import annotations

import threading
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# DDL（只增不改：新列一律 ADD COLUMN）
# --------------------------------------------------------------------------
_DDL_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id     INTEGER,
    company_id     INTEGER,
    doc_id         INTEGER,
    filename       TEXT,
    original_name  TEXT NOT NULL,
    ext            TEXT,
    size           INTEGER DEFAULT 0,
    md5            TEXT,
    sha256         TEXT,
    doc_type       TEXT,
    category       TEXT DEFAULT 'other',
    classify_by    TEXT DEFAULT 'auto',
    parse_status   TEXT DEFAULT 'pending',
    page_count     INTEGER DEFAULT 0,
    storage_path   TEXT,
    uploaded_by    TEXT,
    uploaded_at    TEXT,
    updated_at     TEXT,
    note           TEXT
)
"""

_DDL_DOCUMENT_PAGES = """
CREATE TABLE IF NOT EXISTS document_pages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    page_no     INTEGER NOT NULL,
    char_count  INTEGER DEFAULT 0,
    excerpt     TEXT,
    status      TEXT DEFAULT 'pending',
    created_at  TEXT
)
"""

_IDX = (
    "CREATE INDEX IF NOT EXISTS ix_documents_company_uploaded "
    "ON documents (company_id, uploaded_at)",
    "CREATE INDEX IF NOT EXISTS ix_documents_project_category "
    "ON documents (project_id, category)",
    "CREATE INDEX IF NOT EXISTS ix_documents_md5 ON documents (md5)",
    "CREATE INDEX IF NOT EXISTS ix_documents_sha256 ON documents (sha256)",
    "CREATE INDEX IF NOT EXISTS ix_document_pages_doc ON document_pages (document_id, page_no)",
)

#: 幂等加列声明（历史上新增的列在此逐条判存在；新列一律 ADD COLUMN）
_WANT_COLUMNS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "documents": (
        ("project_id", "INTEGER"), ("company_id", "INTEGER"), ("doc_id", "INTEGER"),
        ("filename", "TEXT"), ("ext", "TEXT"), ("size", "INTEGER"),
        ("md5", "TEXT"), ("sha256", "TEXT"), ("doc_type", "TEXT"),
        ("category", "TEXT"), ("classify_by", "TEXT"), ("parse_status", "TEXT"),
        ("page_count", "INTEGER"), ("storage_path", "TEXT"),
        ("uploaded_by", "TEXT"), ("uploaded_at", "TEXT"), ("updated_at", "TEXT"),
        ("note", "TEXT"),
    ),
    "document_pages": (
        ("char_count", "INTEGER"), ("excerpt", "TEXT"),
        ("status", "TEXT"), ("created_at", "TEXT"),
    ),
}

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
            conn.execute(_text(_DDL_DOCUMENTS))
            conn.execute(_text(_DDL_DOCUMENT_PAGES))
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
    """仅供测试：清掉"已就绪"缓存，使下一次 `ensure_schema` 真跑一遍。"""
    global _SCHEMA_READY_ENGINE
    _SCHEMA_READY_ENGINE = None


def table_columns(engine=None, table: str = "documents") -> List[str]:
    """只读：返回某表当前列名（供闸门/测试断言 schema 与声明一致）。"""
    from sqlalchemy import inspect as _inspect        # noqa: PLC0415
    eng = engine if engine is not None else _default_engine()
    ensure_schema(eng)
    with eng.connect() as conn:
        return [c["name"] for c in _inspect(conn).get_columns(table)]

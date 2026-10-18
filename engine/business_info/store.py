# -*- coding: utf-8 -*-
"""`sys_company_info` 工商信息表（**落库 + 缓存**的唯一实现）。

为什么一张表兼两用
------------------
用户要求「查缓存，命中就直接返回」且「写入本系统数据库」。工商信息本身是
**低频变更的静态档案**（名称/资本/经营范围），把它做成缓存表即可：
同一条记录既回答"这家企业登记的是什么"，也回答"上次什么时候查到的"。

★ 与既有 `companies` 表的关系：`companies` 是**账套**（分析主体），有外键级联与
  一堆业务字段；本表是**工商档案快照**，只记录"外部/本地查询到的登记事实"。
  两者**不合并**：查询失败不得污染账套（用户明确要求"不能阻断项目创建"）。
★ 时间只用 `runtime_storage.now_cst()`（唯一时间权威）。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

TABLE = "sys_company_info"

_DDL = """
CREATE TABLE IF NOT EXISTS sys_company_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    tax_id TEXT,
    legal_representative TEXT,
    registered_capital REAL,
    capital_unit TEXT,
    established_date TEXT,
    registration_status TEXT,
    registered_address TEXT,
    company_type TEXT,
    business_scope TEXT,
    source TEXT,
    source_detail TEXT,
    confidence REAL DEFAULT 0,
    notes_json TEXT,
    fetched_at TEXT,
    project_id INTEGER,
    updated_at TEXT
)
"""

#: 后续扩展列（老库自动补齐，幂等）
_WANT = (
    ("source_detail", "TEXT"),
    ("confidence", "REAL DEFAULT 0"),
    ("project_id", "INTEGER"),
)


def _conf(v: Any) -> float:
    """置信度 → float（走 `engine.numparse` 的唯一数字口径）。"""
    from engine.business_info.dto import to_float               # noqa: PLC0415
    return to_float(v)


def name_key(name: Any) -> str:
    """检索键：去所有空白、全角转半角、去括号差异 ⇒ 同一企业只有一个键。"""
    from engine.business_info.dto import _s                     # noqa: PLC0415
    s = _s(name)
    for ch in (" ", "\u3000", "（", "）", "(", ")", "·", "・"):
        s = s.replace(ch, "")
    return s.upper()


def _engine_or_default(engine: Any = None) -> Any:
    if engine is not None:
        return engine
    from database import engine as _e                            # noqa: PLC0415
    return _e


def ensure_schema(engine: Any = None) -> None:
    """建表 + 补列（幂等）。★ 任何访问本表前必须先调用（表是按需建的）。"""
    from sqlalchemy import text as _text                          # noqa: PLC0415
    eng = _engine_or_default(engine)
    with eng.begin() as conn:
        conn.execute(_text(_DDL))
        conn.execute(_text(
            "CREATE INDEX IF NOT EXISTS ix_sys_company_info_key ON sys_company_info(name_key)"))
        conn.execute(_text(
            "CREATE INDEX IF NOT EXISTS ix_sys_company_info_tax ON sys_company_info(tax_id)"))
        have = {str(r[1]) for r in conn.execute(_text("PRAGMA table_info(sys_company_info)"))}
        for col, typ in _WANT:
            if col not in have:
                conn.execute(_text("ALTER TABLE sys_company_info ADD COLUMN %s %s" % (col, typ)))


def has_table(engine: Any = None) -> bool:
    from sqlalchemy import text as _text                          # noqa: PLC0415
    eng = _engine_or_default(engine)
    try:
        with eng.connect() as conn:
            return bool(conn.execute(_text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"
            ), {"t": TABLE}).first())
    except Exception:                                             # noqa: BLE001
        return False


def get(name: str, engine: Any = None) -> Optional[Dict[str, Any]]:
    """按名称取**最新一条**记录；无则 None。"""
    if not has_table(engine):
        return None
    from sqlalchemy import text as _text                          # noqa: PLC0415
    eng = _engine_or_default(engine)
    with eng.connect() as conn:
        row = conn.execute(_text(
            "SELECT * FROM sys_company_info WHERE name_key=:k ORDER BY id DESC LIMIT 1"
        ), {"k": name_key(name)}).first()
    if not row:
        return None
    d = dict(row._mapping)
    try:
        d["notes"] = json.loads(d.pop("notes_json", None) or "[]")
    except Exception:                                             # noqa: BLE001
        d["notes"] = []
    return d


def get_by_tax_id(tax_id: str, engine: Any = None) -> Optional[Dict[str, Any]]:
    if not has_table(engine):
        return None
    from sqlalchemy import text as _text                          # noqa: PLC0415
    eng = _engine_or_default(engine)
    with eng.connect() as conn:
        row = conn.execute(_text(
            "SELECT * FROM sys_company_info WHERE UPPER(tax_id)=:t ORDER BY id DESC LIMIT 1"
        ), {"t": str(tax_id or "").upper()}).first()
    return dict(row._mapping) if row else None


def upsert(profile: Any, *, project_id: Optional[int] = None,
           engine: Any = None) -> Dict[str, Any]:
    """写入/更新一条工商档案（按 `name_key` 唯一）。返回落库后的行。

    `profile` 为 `engine.business_info.dto.CompanyProfile`（也接受同构 dict）。
    """
    from runtime_storage import now_cst                          # noqa: PLC0415
    from sqlalchemy import text as _text                          # noqa: PLC0415
    ensure_schema(engine)
    eng = _engine_or_default(engine)
    d = profile.to_dict() if hasattr(profile, "to_dict") else dict(profile or {})
    name = str(d.get("name") or "").strip()
    if not name:
        raise ValueError("企业名称为空，拒绝落库")
    k = name_key(name)
    now = now_cst()
    vals = {
        "name": name, "name_key": k,
        "tax_id": d.get("tax_id"), "legal_representative": d.get("legal_representative"),
        "registered_capital": d.get("registered_capital"),
        "capital_unit": d.get("capital_unit") or "万元",
        "established_date": d.get("established_date"),
        "registration_status": d.get("registration_status"),
        "registered_address": d.get("registered_address"),
        "company_type": d.get("company_type"),
        "business_scope": d.get("business_scope"),
        "source": d.get("source") or "", "source_detail": d.get("source_detail") or "",
        "confidence": _conf(d.get("confidence")),
        "notes_json": json.dumps(d.get("notes") or [], ensure_ascii=False),
        "fetched_at": now, "project_id": project_id, "updated_at": now,
    }
    with eng.begin() as conn:
        cur = conn.execute(_text(
            "SELECT id FROM sys_company_info WHERE name_key=:k ORDER BY id DESC LIMIT 1"),
            {"k": k}).first()
        if cur:
            sets = ", ".join("%s=:%s" % (c, c) for c in vals if c != "name_key")
            conn.execute(_text("UPDATE sys_company_info SET %s WHERE id=:rid" % sets),
                         {**vals, "rid": int(cur[0])})
            rid = int(cur[0])
        else:
            cols = ", ".join(vals)
            marks = ", ".join(":" + c for c in vals)
            r = conn.execute(_text(
                "INSERT INTO sys_company_info (%s) VALUES (%s)" % (cols, marks)), vals)
            rid = int(getattr(r, "lastrowid", 0) or 0)
        row = conn.execute(_text("SELECT * FROM sys_company_info WHERE id=:i"),
                           {"i": rid}).first()
    return dict(row._mapping) if row else {}


def link_project(name: str, project_id: int, engine: Any = None) -> bool:
    """把已落库的工商档案关联到稽查项目（用户要求"关联当前稽查项目"）。"""
    if not has_table(engine):
        return False
    from runtime_storage import now_cst                          # noqa: PLC0415
    from sqlalchemy import text as _text                          # noqa: PLC0415
    eng = _engine_or_default(engine)
    with eng.begin() as conn:
        r = conn.execute(_text(
            "UPDATE sys_company_info SET project_id=:p, updated_at=:t WHERE name_key=:k"),
            {"p": int(project_id), "t": now_cst(), "k": name_key(name)})
    return bool(getattr(r, "rowcount", 0))


def list_recent(limit: int = 20, engine: Any = None) -> List[Dict[str, Any]]:
    if not has_table(engine):
        return []
    from sqlalchemy import text as _text                          # noqa: PLC0415
    eng = _engine_or_default(engine)
    with eng.connect() as conn:
        rows = conn.execute(_text(
            "SELECT id, name, tax_id, registration_status, source, fetched_at, project_id "
            "FROM sys_company_info ORDER BY id DESC LIMIT :n"), {"n": int(limit)}).all()
    return [dict(r._mapping) for r in rows]


def age_hours(row: Dict[str, Any], now: Optional[Any] = None) -> Optional[float]:
    """距 `fetched_at` 的小时数；解析不出 ⇒ None（**不当作新鲜**）。

    ★ `runtime_storage.now_cst()` 是 **ISO8601 带时区**（`2026-10-18T20:13:51+08:00`），
      不是 `"%Y-%m-%d %H:%M:%S"`。实测踩过：按后者解析恒失败 ⇒ `age_hours` 永远 None
      ⇒ **缓存永远不命中**（等于没做缓存，还每查一次都打一次外网）。
      这里用 `fromisoformat` 并把无时区值按北京时间补全，再按 UTC 差值算。
    """
    from datetime import datetime, timedelta, timezone
    s = str((row or {}).get("fetched_at") or "").strip()
    if not s:
        return None
    t: Optional[datetime] = None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:                                             # noqa: BLE001
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                t = datetime.strptime(s[:len(fmt) + 2].strip(), fmt)
                break
            except Exception:                                     # noqa: BLE001
                t = None
    if t is None:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone(timedelta(hours=8)))
    base = now or datetime.now(timezone.utc)
    if getattr(base, "tzinfo", None) is None:
        base = base.replace(tzinfo=timezone.utc)
    return max(0.0, (base - t).total_seconds() / 3600.0)


__all__ = ["TABLE", "ensure_schema", "has_table", "get", "get_by_tax_id", "upsert",
           "link_project", "list_recent", "name_key", "age_hours"]

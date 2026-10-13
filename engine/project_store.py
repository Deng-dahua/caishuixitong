# -*- coding: utf-8 -*-
"""稽查项目（P0-1）的**数据库底座**：幂等建表 + 幂等加列 + 索引。

★★ 为什么不引入 alembic（与项目既有裁定一致，勿改）
  `engine/audit_trail.py` 已把「**幂等建表 + 幂等加列**」确立为本项目的 **migration 底座**：
  「不引入 alembic：§6 要求'变更走 migration'，而换栈式引入 alembic 与'不擅自更换技术栈'
   冲突，故用'幂等建表 + 幂等加列'实现同一目的」。

  本模块**沿用同一模式**（不是另立一套）：
    · 表不存在      ⇒ `CREATE TABLE IF NOT EXISTS`（列与顺序**逐字固定**）；
    · 新列缺失      ⇒ `ALTER TABLE ... ADD COLUMN`（SQLite 安全、向后兼容）；
    · 索引缺失      ⇒ `CREATE INDEX IF NOT EXISTS`；
    · `inspector` 守卫幂等；按 **engine 身份**缓存（热路径只做一次）。
  ⇒ 任务书「数据库变更必须通过 migration」= **走本模块**，不手工改库、不绕过。

★ 命名歧义警告（勿混淆）
  既有代码里 `projects` 一词专指**研发项目**（`engine/rd_audit.py` 的 `rd_data["projects"]`、
  `main.py` 的**局部变量**），那是**研发费用加计扣除**的辅助账数据，**不是实体表**。
  本模块的 `projects` 表是**稽查项目**实体 —— 两者语义无关、命名空间不同（表名 vs JSON 字段）。

★ 租户边界
  沿用现有 `company_id`（=`SessionContext.can_access_company()` 的同一口径），
  **不引入新的租户/租户成员表**（RBAC 暂缓）。跨租户一律**不可见**。
"""
from __future__ import annotations

import threading
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# 状态机（★ 唯一权威：新增一个状态只改这里一处 + STATUS_CN 一行）
# --------------------------------------------------------------------------
#: 项目状态（任务书六态）
STATUSES: Tuple[str, ...] = (
    "draft",       # 草稿
    "uploading",   # 资料上传中
    "analyzing",   # 分析中
    "reviewing",   # 待复核
    "reported",    # 已报告
    "archived",    # 已归档
)

#: 状态中文名（★ 与 STATUSES 一一对应；面向界面/导出，**不得出现英文码**）
STATUS_CN: Dict[str, str] = {
    "draft": "草稿",
    "uploading": "资料上传中",
    "analyzing": "分析中",
    "reviewing": "待复核",
    "reported": "已报告",
    "archived": "已归档",
}

#: 允许的状态迁移（★ 唯一权威）。任务书未规定迁移规则 ⇒ 按业务合理性定义并在此声明：
#:   · 正常推进：draft → uploading → analyzing → reviewing → reported → archived
#:   · 有限回退：analyzing → uploading（补资料）、reviewing → analyzing（重跑）、
#:               reported → reviewing（复核后回退）
#:   · `archived` 为**终态**，不可再迁出（要复检须新建项目）
#: 非法迁移 ⇒ Service 抛 `ValueError`，接口回 400，**不静默接受**。
STATUS_FLOW: Dict[str, Tuple[str, ...]] = {
    "draft": ("uploading", "archived"),
    "uploading": ("analyzing", "draft", "archived"),
    "analyzing": ("reviewing", "uploading", "archived"),
    "reviewing": ("reported", "analyzing", "archived"),
    "reported": ("archived", "reviewing"),
    "archived": (),
}

#: 项目成员角色（★ 唯一权威）
ROLES: Tuple[str, ...] = ("owner", "reviewer", "member", "viewer")

ROLE_CN: Dict[str, str] = {
    "owner": "创建人",
    "reviewer": "复核人",
    "member": "成员",
    "viewer": "只读",
}

#: 有**写权限**（改项目 / 加成员 / 删项目）的角色；`viewer` 只读。
WRITE_ROLES: Tuple[str, ...] = ("owner", "reviewer", "member")

#: 项目编号前缀（生成可读编号，如 `PJ-20261013-0001`）
CODE_PREFIX = "PJ"

# --------------------------------------------------------------------------
# DDL（表结构**只增不改**：新列一律 ADD COLUMN）
# --------------------------------------------------------------------------
_DDL_PROJECTS = """
CREATE TABLE IF NOT EXISTS projects (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id        INTEGER,
    code              TEXT,
    name              TEXT NOT NULL,
    taxpayer_id       TEXT,
    industry          TEXT,
    region            TEXT,
    period_start      TEXT,
    period_end        TEXT,
    tax_scopes        TEXT,
    status            TEXT NOT NULL DEFAULT 'draft',
    remark            TEXT,
    owner_id          INTEGER,
    owner_name        TEXT,
    created_at        TEXT,
    updated_at        TEXT
)
"""

_DDL_PROJECT_MEMBERS = """
CREATE TABLE IF NOT EXISTS project_members (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL,
    user_id     INTEGER,
    user_name   TEXT,
    role        TEXT NOT NULL DEFAULT 'member',
    created_at  TEXT
)
"""

_IDX = (
    "CREATE INDEX IF NOT EXISTS ix_projects_company_status "
    "ON projects (company_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_projects_company_updated "
    "ON projects (company_id, updated_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_project_members_project_user "
    "ON project_members (project_id, user_id)",
    "CREATE INDEX IF NOT EXISTS ix_project_members_user "
    "ON project_members (user_id)",
)

#: 幂等缓存（按 engine 身份）
_SCHEMA_READY_ENGINE: Optional[int] = None
_SCHEMA_LOCK = threading.Lock()


def _default_engine():
    from database import engine as _engine          # noqa: PLC0415
    return _engine


def ensure_schema(engine=None) -> None:
    """**幂等**建表 + 幂等加列 + 索引。**可在任何时候重复调用**。

    与 `engine/audit_trail.ensure_schema()` 同一模式：
      · 表不存在 ⇒ 建；新列缺失 ⇒ `ALTER TABLE ADD COLUMN`；索引缺失 ⇒ 建；
      · 用 `inspector` 守卫，**重复调用无副作用**；
      · 按 engine 身份缓存 ⇒ 热路径只做一次（避免每次读写都抢 SQLite 写锁）。
    """
    global _SCHEMA_READY_ENGINE
    eng = engine if engine is not None else _default_engine()
    if _SCHEMA_READY_ENGINE == id(eng):
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY_ENGINE == id(eng):
            return
        from sqlalchemy import inspect as _inspect, text as _text   # noqa: PLC0415
        with eng.begin() as conn:
            conn.execute(_text(_DDL_PROJECTS))
            conn.execute(_text(_DDL_PROJECT_MEMBERS))
            # ── 幂等加列（历史上新增的列在此逐条判存在；新列一律 ADD COLUMN）──
            _want = {
                "projects": (
                    ("code", "TEXT"), ("taxpayer_id", "TEXT"), ("industry", "TEXT"),
                    ("region", "TEXT"), ("period_start", "TEXT"), ("period_end", "TEXT"),
                    ("tax_scopes", "TEXT"), ("remark", "TEXT"),
                    ("owner_id", "INTEGER"), ("owner_name", "TEXT"),
                    ("created_at", "TEXT"), ("updated_at", "TEXT"),
                ),
                "project_members": (
                    ("user_name", "TEXT"),
                ),
            }
            for _tbl, _cols in _want.items():
                _have = {c["name"] for c in _inspect(conn).get_columns(_tbl)}
                for _cname, _ctype in _cols:
                    if _cname not in _have:
                        conn.execute(_text(
                            "ALTER TABLE %s ADD COLUMN %s %s" % (_tbl, _cname, _ctype)))
            for _sql in _IDX:
                conn.execute(_text(_sql))
        _SCHEMA_READY_ENGINE = id(eng)


def reset_cache() -> None:
    """仅供测试：清掉"已就绪"缓存，使下一次 `ensure_schema` 真跑一遍。"""
    global _SCHEMA_READY_ENGINE
    _SCHEMA_READY_ENGINE = None


def table_columns(engine=None, table: str = "projects") -> List[str]:
    """只读：返回某表当前列名（供闸门/测试断言 schema 与声明一致）。"""
    from sqlalchemy import inspect as _inspect        # noqa: PLC0415
    eng = engine if engine is not None else _default_engine()
    ensure_schema(eng)
    with eng.connect() as conn:
        return [c["name"] for c in _inspect(conn).get_columns(table)]

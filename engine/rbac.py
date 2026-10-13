# -*- coding: utf-8 -*-
"""RBAC / 租户 / 脱敏映射 的**唯一权威**（P0-8）。

## 这一层解决什么问题

系统此前只有**两个**粗粒度角色（`users.role ∈ {admin, user}`）与**账套级**数据权限
（`SessionContext.allowed_company_ids`）：既回答不了「谁能复核风险、谁只能看」，
也没有组织（租户）这一层。P0-8 补齐后，权限由**三层**共同决定，且三层各有唯一权威：

  ① **功能权限（RBAC）** —— 本模块 `rbac_allows()`（唯一判定点）。
     角色、权限点、角色→权限映射的**数据**来自 `config/rbac.json`（唯一数据表）；
     本模块只加载 + 薄转发，**不硬编码任何角色/权限字面量**。
  ② **数据权限（账套）** —— `security.SessionContext.can_access_company()`（既有权威，未改动）。
  ③ **项目权限（成员）** —— `engine/project_service._can_write()`（P0-1 既有权威，未改动）。

## 铁律

- **`users.role` 是遗留兼容位，不是角色体系**：它是 `CHECK(role IN ('admin','user'))`
  的两值列（`security.py` 建表时就带约束，SQLite 无法 `ALTER ... CHECK`）。
  P0-8 **不改它**（改了会让既有 `is_admin` 判定、`security_web` 守卫、历史数据全部失配），
  而是把它**解释**为：
    · `role='admin'` ⇒ 等价持有 `system_admin`（超管，**全部权限**）；
    · `role='user'`  ⇒ 由 `user_roles` 表决定其细粒度角色；无记录 ⇒ `default_role`。
  这样 `SessionContext.is_admin`、`security_web._ADMIN_PATHS` 等既有行为**零改动**即兼容。

- **角色→脱敏**：本模块只做**映射**（RBAC 角色 ⇒ `report_compliance.json::redaction_roles`
  里已登记的键）。「要不要脱、脱哪几项」的唯一权威仍在 `config/report_compliance.json`，
  本模块**不得**再写一套脱敏规则（`engine/redaction.py` 才是「怎么脱」的权威）。

- **表结构与幂等**：`ensure_rbac_schema()` 幂等建表 + 幂等加列（本项目 migration 底座，
  不引入 alembic）。建表落在 `security.db`（与 `users` 同库 —— 角色是身份的一部分）。

- **绝不静默**：未知角色/未知权限一律**拒绝**（`rbac_allows` 返回 False），
  且 `require_permission()` 抛带 403 的业务异常；不返回"默认放行"。
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

#: 通配符权限（系统管理员的 `role_permissions` 值）
ALL_PERMISSIONS = "*"

#: 角色范围（scope）——决定该角色能否跨租户
SCOPE_TENANT = "tenant"
SCOPE_PLATFORM = "platform"

#: 租户形态（与 `config/rbac.json::tenant_modes` 的键一一对应）
TENANT_MODES: Tuple[str, ...] = ("saas", "private")


class RbacError(Exception):
    """权限/角色业务异常：携带 HTTP 状态码，由 API 层**原样转发**。"""

    def __init__(self, message: str, status: int = 403):
        super().__init__(message)
        self.message = message
        self.status = int(status)


# ── 配置（唯一数据表）────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_PATH = _ROOT / "config" / "rbac.json"

_CFG_CACHE: Optional[Dict[str, Any]] = None
_CFG_MTIME: float = -1.0
_CFG_LOCK = threading.RLock()


def rbac_config() -> Dict[str, Any]:
    """读 `config/rbac.json`（按 mtime 缓存；文件变更自动重载）。"""
    global _CFG_CACHE, _CFG_MTIME
    with _CFG_LOCK:
        try:
            mtime = _CONFIG_PATH.stat().st_mtime
        except OSError:
            mtime = -1.0
        if _CFG_CACHE is not None and mtime == _CFG_MTIME:
            return _CFG_CACHE
        with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise RbacError("config/rbac.json 结构非法（应为对象）", 500)
        _CFG_CACHE, _CFG_MTIME = data, mtime
        return data


def reload_rbac_config() -> Dict[str, Any]:
    """清缓存并重读（供测试/闸门；运行期由 mtime 自动生效）。"""
    global _CFG_CACHE, _CFG_MTIME
    with _CFG_LOCK:
        _CFG_CACHE, _CFG_MTIME = None, -1.0
    return rbac_config()


def permission_codes() -> List[str]:
    """全部权限点（顺序 = 配置声明顺序）。"""
    return [str(p.get("code") or "") for p in (rbac_config().get("permissions") or [])
            if p.get("code")]


def role_codes() -> List[str]:
    """全部**内置**角色码（自定义角色在库中，另行查询）。"""
    return [str(r.get("code") or "") for r in (rbac_config().get("roles") or [])
            if r.get("code")]


def _expanded_role_permissions() -> Dict[str, List[str]]:
    """角色 → 权限码列表（把 `*` 展开为全部权限点；未知权限码**保留并留待闸门报错**）。"""
    cfg = rbac_config()
    mapping = cfg.get("role_permissions") or {}
    all_codes = permission_codes()
    out: Dict[str, List[str]] = {}
    for role, perms in mapping.items():
        vals = [str(x) for x in (perms or [])]
        out[str(role)] = list(all_codes) if ALL_PERMISSIONS in vals else list(dict.fromkeys(vals))
    return out


def redaction_role_of_code(role_code: str) -> str:
    """RBAC 角色码 → 脱敏策略键（缺省 `fallback_redaction`，**最严**）。"""
    cfg = rbac_config()
    mapping = cfg.get("role_redaction") or {}
    val = mapping.get(str(role_code or ""))
    if val:
        return str(val)
    return str(cfg.get("fallback_redaction") or "external")


# ── 表结构（migration 底座）─────────────────────────────────────────────────

_RBAC_DDL = """
CREATE TABLE IF NOT EXISTS roles (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'tenant',
    builtin INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS permissions (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    group_code TEXT NOT NULL DEFAULT '',
    group_name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS role_permissions (
    role_code TEXT NOT NULL,
    perm_code TEXT NOT NULL,
    PRIMARY KEY (role_code, perm_code)
);
CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER NOT NULL,
    role_code TEXT NOT NULL,
    granted_at INTEGER NOT NULL,
    granted_by INTEGER,
    PRIMARY KEY (user_id, role_code)
);
CREATE INDEX IF NOT EXISTS ix_user_roles_user ON user_roles(user_id);
CREATE TABLE IF NOT EXISTS tenants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'saas',
    status TEXT NOT NULL DEFAULT 'active',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
"""

#: 已就绪的库路径（**按 DB 路径缓存**：测试会把 SECURITY_DB 指向临时库 ⇒ 换库必须重建）
_READY_DB: Optional[str] = None
_READY_LOCK = threading.RLock()


def _security_db() -> str:
    from security import SECURITY_DB          # noqa: PLC0415
    return str(SECURITY_DB)


def _rbac_connect():
    """薄转发 `security._connect()`（身份库连接唯一实现，避免第二套连接口径）。"""
    from security import _connect             # noqa: PLC0415
    return _connect()


def ensure_rbac_schema(*, force: bool = False) -> None:
    """幂等建表 + 内置角色/权限同步。**可在任何时候重复调用**。

    ★ 只同步 `config/rbac.json` 声明的**内置**角色（`builtin=1`）；
      自定义角色（`builtin=0`）及其权限映射**原样保留**，不被覆盖。
    """
    global _READY_DB
    db = _security_db()
    if not force and _READY_DB == db:
        return
    with _READY_LOCK:
        if not force and _READY_DB == db:
            return
        with _rbac_connect() as conn:
            conn.executescript(_RBAC_DDL)
            _sync_builtin_principals(conn)
        _READY_DB = db


def _sync_builtin_principals(conn) -> None:
    """把配置里的内置角色/权限 upsert 进库（幂等；自定义行不动）。"""
    now = int(time.time())
    cfg = rbac_config()

    for p in (cfg.get("permissions") or []):
        code = str(p.get("code") or "")
        if not code:
            continue
        conn.execute(
            "INSERT INTO permissions (code, name, group_code, group_name, description, sort_order) "
            "VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET name=excluded.name, group_code=excluded.group_code, "
            "group_name=excluded.group_name, description=excluded.description, "
            "sort_order=excluded.sort_order",
            (code, str(p.get("name") or code), str(p.get("group_code") or ""),
             str(p.get("group") or ""), str(p.get("description") or ""),
             int(p.get("sort") or 0)),
        )

    for r in (cfg.get("roles") or []):
        code = str(r.get("code") or "")
        if not code:
            continue
        conn.execute(
            "INSERT INTO roles (code, name, scope, builtin, description, sort_order, "
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET name=excluded.name, scope=excluded.scope, "
            "builtin=excluded.builtin, description=excluded.description, "
            "sort_order=excluded.sort_order, updated_at=excluded.updated_at",
            (code, str(r.get("name") or code), str(r.get("scope") or SCOPE_TENANT),
             int(r.get("builtin") or 0), str(r.get("description") or ""),
             int(r.get("sort") or 0), now, now),
        )

    # 内置角色 → 权限（先删后插，保证与配置逐字一致；只动内置角色）
    expanded = _expanded_role_permissions()
    builtin = set(role_codes())
    for role, perms in expanded.items():
        if role not in builtin:
            continue
        conn.execute("DELETE FROM role_permissions WHERE role_code=?", (role,))
        for perm in perms:
            conn.execute(
                "INSERT OR IGNORE INTO role_permissions (role_code, perm_code) VALUES (?,?)",
                (role, perm),
            )

    # 默认租户（幂等）
    dt = cfg.get("default_tenant") or {}
    if dt.get("code"):
        conn.execute(
            "INSERT INTO tenants (code, name, mode, status, created_at, updated_at) "
            "VALUES (?,?,?,'active',?,?) ON CONFLICT(code) DO NOTHING",
            (str(dt["code"]), str(dt.get("name") or dt["code"]),
             str(dt.get("mode") or "saas"), now, now),
        )


# ── 查询 ─────────────────────────────────────────────────────────────────────

def default_tenant_id() -> Optional[int]:
    """默认租户 id（配置 `default_tenant.code` 对应行；不存在 ⇒ None）。"""
    ensure_rbac_schema()
    code = str((rbac_config().get("default_tenant") or {}).get("code") or "")
    if not code:
        return None
    with _rbac_connect() as conn:
        row = conn.execute("SELECT id FROM tenants WHERE code=?", (code,)).fetchone()
    return int(row["id"]) if row else None


def tenant_row(tenant_id: Any) -> Optional[Dict[str, Any]]:
    ensure_rbac_schema()
    try:
        tid = int(tenant_id)
    except Exception:                          # noqa: BLE001
        return None
    with _rbac_connect() as conn:
        row = conn.execute("SELECT * FROM tenants WHERE id=?", (tid,)).fetchone()
    return dict(row) if row else None


def list_tenants() -> List[Dict[str, Any]]:
    ensure_rbac_schema()
    with _rbac_connect() as conn:
        rows = conn.execute("SELECT * FROM tenants ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def create_tenant(code: str, name: str, mode: str = "saas") -> int:
    """新建租户（幂等：code 已存在 ⇒ 返回既有 id）。"""
    ensure_rbac_schema()
    c = str(code or "").strip()
    if not c:
        raise RbacError("租户编码不能为空", 400)
    m = str(mode or "saas")
    if m not in TENANT_MODES:
        raise RbacError("租户形态非法：%s（合法：%s）" % (m, "、".join(TENANT_MODES)), 400)
    now = int(time.time())
    with _rbac_connect() as conn:
        row = conn.execute("SELECT id FROM tenants WHERE code=?", (c,)).fetchone()
        if row:
            return int(row["id"])
        cur = conn.execute(
            "INSERT INTO tenants (code, name, mode, status, created_at, updated_at) "
            "VALUES (?,?,?,'active',?,?)",
            (c, str(name or c), m, now, now),
        )
        return int(cur.lastrowid)


def role_rows() -> List[Dict[str, Any]]:
    """全部角色（含自定义），按 sort_order 排序。"""
    ensure_rbac_schema()
    with _rbac_connect() as conn:
        rows = conn.execute(
            "SELECT * FROM roles ORDER BY sort_order, code").fetchall()
    return [dict(r) for r in rows]


def permission_rows() -> List[Dict[str, Any]]:
    ensure_rbac_schema()
    with _rbac_connect() as conn:
        rows = conn.execute(
            "SELECT * FROM permissions ORDER BY sort_order, code").fetchall()
    return [dict(r) for r in rows]


def role_permission_rows(role_code: str) -> List[str]:
    ensure_rbac_schema()
    with _rbac_connect() as conn:
        rows = conn.execute(
            "SELECT perm_code FROM role_permissions WHERE role_code=? ORDER BY perm_code",
            (str(role_code),)).fetchall()
    return [str(r["perm_code"]) for r in rows]


def role_exists(role_code: str) -> bool:
    ensure_rbac_schema()
    with _rbac_connect() as conn:
        return conn.execute("SELECT 1 FROM roles WHERE code=?",
                            (str(role_code),)).fetchone() is not None


def user_role_codes(user_id: Any) -> List[str]:
    """用户在 `user_roles` 里的角色码（不含由 `users.role='admin'` 隐含的超管）。"""
    ensure_rbac_schema()
    try:
        uid = int(user_id)
    except Exception:                          # noqa: BLE001
        return []
    with _rbac_connect() as conn:
        rows = conn.execute(
            "SELECT role_code FROM user_roles WHERE user_id=? ORDER BY role_code",
            (uid,)).fetchall()
    return [str(r["role_code"]) for r in rows]


def assign_user_roles(user_id: Any, role_codes_seq: Sequence[str],
                      granted_by: Any = None) -> List[str]:
    """覆盖式指派用户角色（**唯一写入点**）。未登记角色码 ⇒ 400（不静默接受）。"""
    ensure_rbac_schema()
    try:
        uid = int(user_id)
    except Exception:                          # noqa: BLE001
        raise RbacError("user_id 非法", 400)
    wanted: List[str] = []
    for code in (role_codes_seq or []):
        c = str(code or "").strip()
        if not c or c in wanted:
            continue
        if not role_exists(c):
            raise RbacError("角色不存在：%s（合法角色见 /api/v1/roles）" % c, 400)
        wanted.append(c)
    now = int(time.time())
    try:
        gb = int(granted_by) if granted_by is not None else None
    except Exception:                          # noqa: BLE001
        gb = None
    with _rbac_connect() as conn:
        conn.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
        for c in wanted:
            conn.execute(
                "INSERT OR IGNORE INTO user_roles (user_id, role_code, granted_at, granted_by) "
                "VALUES (?,?,?,?)", (uid, c, now, gb))
    return wanted


# ── 角色写入（POST /api/v1/roles）────────────────────────────────────────────

def create_role(code: str, name: str, permissions_seq: Sequence[str],
                scope: str = SCOPE_TENANT, description: str = "") -> Dict[str, Any]:
    """新建**自定义**角色（`builtin=0`）。内置角色码不可占用（防覆盖配置权威）。"""
    ensure_rbac_schema()
    c = str(code or "").strip()
    if not c:
        raise RbacError("角色编码不能为空", 400)
    if c in set(role_codes()):
        raise RbacError("角色编码 %s 为内置角色，不可重建（如需调整请改 config/rbac.json）" % c, 400)
    sc = str(scope or SCOPE_TENANT)
    if sc not in (SCOPE_TENANT, SCOPE_PLATFORM):
        raise RbacError("角色范围非法：%s（合法：tenant、platform）" % sc, 400)
    known = set(permission_codes())
    perms: List[str] = []
    for p in (permissions_seq or []):
        pc = str(p or "").strip()
        if not pc or pc in perms:
            continue
        if pc not in known:
            raise RbacError("权限码不存在：%s（合法权限见 /api/v1/roles 的 permissions）" % pc, 400)
        perms.append(pc)
    now = int(time.time())
    with _rbac_connect() as conn:
        if conn.execute("SELECT 1 FROM roles WHERE code=?", (c,)).fetchone():
            raise RbacError("角色编码已存在：%s" % c, 409)
        conn.execute(
            "INSERT INTO roles (code, name, scope, builtin, description, sort_order, "
            " created_at, updated_at) VALUES (?,?,?,0,?,?,?,?)",
            (c, str(name or c), sc, str(description or ""), 900, now, now))
        for pc in perms:
            conn.execute("INSERT OR IGNORE INTO role_permissions (role_code, perm_code) VALUES (?,?)",
                         (c, pc))
    return {"code": c, "name": str(name or c), "scope": sc, "builtin": 0,
            "permissions": perms}


# ── 会话级判定（唯一判定点）─────────────────────────────────────────────────

def _is_legacy_admin(session: Any) -> bool:
    """`users.role='admin'` ⇒ 超管。优先用 `SessionContext.is_admin`（既有权威）。"""
    val = getattr(session, "is_admin", None)
    if isinstance(val, bool):
        return val
    return str(getattr(session, "role", "")) == "admin"


def session_role_codes(session: Any) -> FrozenSet[str]:
    """会话实际生效的角色码集合（含由 `users.role='admin'` 隐含的超管）。"""
    if _is_legacy_admin(session):
        return frozenset({str(rbac_config().get("legacy_admin_role") or "system_admin")})
    codes = user_role_codes(getattr(session, "user_id", None))
    if not codes:
        fallback = str(rbac_config().get("default_role") or "")
        codes = [fallback] if fallback else []
    return frozenset(codes)


def session_permission_codes(session: Any) -> FrozenSet[str]:
    """会话**功能权限**集合（RBAC 唯一出口）。

    · 超管（`users.role='admin'` 或持有 `system_admin`）⇒ 全部权限；
    · 其余 ⇒ 其全部角色的权限并集；
    · 会话为空 ⇒ 空集（**不放行**）。
    """
    if session is None:
        return frozenset()
    cfg = rbac_config()
    admin_role = str(cfg.get("legacy_admin_role") or "system_admin")
    roles = session_role_codes(session)
    if _is_legacy_admin(session):
        return frozenset(permission_codes())
    if admin_role in roles:
        return frozenset(permission_codes())
    expanded = _expanded_role_permissions()
    perms: set = set()
    for code in roles:
        if code in expanded:
            perms.update(expanded[code])
            continue
        perms.update(role_permission_rows(code))       # 自定义角色：以库为准
    return frozenset(perms)


def rbac_allows(session: Any, permission: str) -> bool:
    """**权限判定的唯一入口**：会话是否具备某权限（未知权限 ⇒ False，绝不放行）。"""
    p = str(permission or "")
    if not p:
        return False
    return p in session_permission_codes(session)


def require_permission(session: Any, permission: str) -> None:
    """不具备 ⇒ 抛 `RbacError(403)`（消息里带上角色，便于自查；不泄露数据）。"""
    if rbac_allows(session, permission):
        return
    raise RbacError(
        "无权执行该操作（需要权限：%s；当前角色：%s）"
        % (permission, "、".join(sorted(session_role_codes(session))) or "无"),
        403)


def redaction_role_of(session: Any) -> str:
    """会话 → 脱敏策略键。多角色时取**最严**（脱敏项最多）的一套。

    ★ 「脱哪几项」由 `engine.redaction.role_policy()` 给出（唯一权威），
      本函数只比较各候选策略的**严格程度**，不自行解释脱敏项语义。
    """
    from engine.redaction import REDACTION_ITEMS, role_policy as _rp    # noqa: PLC0415
    cfg = rbac_config()
    best: Optional[Tuple[int, str]] = None
    for code in sorted(session_role_codes(session)):
        key = redaction_role_of_code(code)
        policy = _rp(key)
        strictness = sum(1 for it in REDACTION_ITEMS if policy.get(it))
        if best is None or strictness > best[0]:
            best = (strictness, key)
    if best is not None:
        return best[1]
    return str(cfg.get("fallback_redaction") or "external")


def mask_for_session(session: Any, obj: Any,
                     counter: Optional[Dict[str, int]] = None) -> Any:
    """按会话角色**原地**脱敏一个对象（薄转发 `engine.redaction.redact_obj`）。

    ★ 「怎么脱」的唯一权威在 `engine/redaction.py`；本函数只负责把
      「当前会话 ⇒ 哪套策略」这一步收敛，避免各接口各判一次角色。
    """
    from engine.redaction import redact_obj as _ro       # noqa: PLC0415
    return _ro(obj, redaction_role_of(session), counter)


def tenant_id_of(session: Any) -> Optional[int]:
    """会话所属租户 id（`SessionContext.tenant_id`；未设置 ⇒ 默认租户）。"""
    val = getattr(session, "tenant_id", None)
    if val is None:
        return default_tenant_id()
    try:
        return int(val)
    except Exception:                          # noqa: BLE001
        return None


def visible_tenant_ids(session: Any) -> Optional[FrozenSet[int]]:
    """可见租户集合；`None` = **不限**（超管）。

    租户隔离的**功能层**判据：非超管只能看到本租户的用户/组织数据。
    （**业务数据**的隔离仍由账套级 `allowed_company_ids` 与项目成员承担，二者不互相替代。）
    """
    if session is None:
        return frozenset()
    if _is_legacy_admin(session):
        return None
    tid = tenant_id_of(session)
    return frozenset({tid}) if tid is not None else frozenset()


def rbac_metadata() -> Dict[str, Any]:
    """角色/权限字典（供前端下拉与角色页；**唯一权威**来自本模块 + 配置表）。"""
    cfg = rbac_config()
    return {
        "roles": [
            {"code": r["code"], "name": r["name"], "scope": r["scope"],
             "builtin": bool(r["builtin"]), "description": r["description"],
             "permission_count": len(role_permission_rows(r["code"]))}
            for r in role_rows()
        ],
        "permissions": [
            {"code": p["code"], "name": p["name"], "group": p["group_name"],
             "group_code": p["group_code"], "description": p["description"]}
            for p in permission_rows()
        ],
        "role_permissions": {r["code"]: sorted(role_permission_rows(r["code"]))
                             for r in role_rows()},
        "role_redaction": dict(cfg.get("role_redaction") or {}),
        "fallback_redaction": str(cfg.get("fallback_redaction") or "external"),
        "tenant_modes": dict(cfg.get("tenant_modes") or {}),
        "default_role": str(cfg.get("default_role") or ""),
        "default_tenant_id": default_tenant_id(),
        "masked_user_fields": list(cfg.get("masked_user_fields") or []),
        "masked_audit_fields": list(cfg.get("masked_audit_fields") or []),
    }


__all__ = [
    "ALL_PERMISSIONS", "SCOPE_TENANT", "SCOPE_PLATFORM", "TENANT_MODES", "RbacError",
    "rbac_config", "reload_rbac_config", "permission_codes", "role_codes",
    "redaction_role_of_code",
    "ensure_rbac_schema", "default_tenant_id", "tenant_row", "list_tenants",
    "create_tenant", "role_rows", "permission_rows", "role_permission_rows",
    "role_exists", "user_role_codes", "assign_user_roles", "create_role",
    "session_role_codes", "session_permission_codes", "rbac_allows",
    "require_permission", "redaction_role_of", "mask_for_session",
    "tenant_id_of", "visible_tenant_ids", "rbac_metadata",
]

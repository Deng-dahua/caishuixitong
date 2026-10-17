"""Local authentication, authorization and session storage.

Only password hashes and token hashes are persisted.  Raw session and CSRF
tokens exist solely in the browser cookies for the lifetime of a session.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from runtime_storage import SECURITY_DB


PASSWORD_MIN_LENGTH = 12
SESSION_TTL_SECONDS = int(os.environ.get("APP_SESSION_TTL_SECONDS", "28800"))

#: ── P0-1（2026-10-17）：会话读取**不再每请求写库** ──────────────────────
#: 根因：`get_session()` 由鉴权中间件在**每个请求**上调用（`security_web.py`），
#: 原实现每次都要 `DELETE FROM sessions WHERE expires_at<=?`
#: 再 `UPDATE sessions SET last_seen=?` —— 即**每个请求两次写事务**。
#: 在 WAL + 多连接 + 外部进程并发访问下会抛
#: `sqlite3.OperationalError: attempt to write a readonly database`，
#: 表现为 `/api/auth/me` 随机 500，用户端看到按钮短暂消失、页面数据不全
#: （阶段 3 实测：7 次 500，跨 3/19 模块**随机**出现）。
#:
#: 修法（语义不变、可观测）：
#:   ① 过期判定改为 **SQL 显式比较 `expires_at > now`** —— 过期会话**永远**被拒绝，
#:      不依赖"那次 DELETE 有没有跑"（原先靠 DELETE 淘汰，节流后必须补上这条，
#:      否则清理周期内的过期会话会被放行，属**安全回归**）；
#:   ② 过期会话清理：每进程最多每 `_SWEEP_INTERVAL_SECONDS` 秒一次；
#:   ③ `last_seen` 写库：每会话最多每 `_TOUCH_INTERVAL_SECONDS` 秒一次
#:      （该字段**无任何消费点**，仅为留痕，节流不改变任何行为）；
#:   ④ 上述写操作**失败不影响会话读取**（读是主路径），但**必须留日志**，不许静默。
_SWEEP_INTERVAL_SECONDS = float(os.environ.get("APP_SESSION_SWEEP_INTERVAL_SECONDS", "60"))
_TOUCH_INTERVAL_SECONDS = float(os.environ.get("APP_SESSION_TOUCH_INTERVAL_SECONDS", "60"))

_session_state_lock = threading.Lock()
_last_sweep_at = 0.0
_last_touch_at: Dict[str, float] = {}
_session_write_failures = 0          # 只用于可观测（测试与运维据此判断是否在降级）

logger = logging.getLogger(__name__)
COOKIE_SECURE = os.environ.get("APP_COOKIE_SECURE", "1") not in {"0", "false", "False"}
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@\-\u4e00-\u9fff]{2,64}$")
_PUBLIC_ASSET_EXTENSIONS = {
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".map",
}
_PROTECTED_STATIC_EXTENSIONS = {
    ".json", ".jsonl", ".db", ".sqlite", ".sqlite3", ".csv", ".xlsx",
    ".xls", ".pdf", ".doc", ".docx", ".zip", ".bak", ".log",
}


@dataclass(frozen=True)
class SessionContext:
    user_id: int
    username: str
    role: str
    allowed_company_ids: frozenset[int]
    selected_company_id: Optional[int]
    csrf_hash: str
    expires_at: int
    #: P0-8 新增：会话所属租户（组织）。加在**末尾且带默认值** ⇒ 既有构造调用
    #: （一律关键字实参）保持可用；`None` 表示"未指定"，由 `engine/rbac` 回落到默认租户。
    tenant_id: Optional[int] = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def can_access_company(self, company_id: int) -> bool:
        return self.is_admin or int(company_id) in self.allowed_company_ids


@contextmanager
def _connect():
    Path(SECURITY_DB).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(SECURITY_DB), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    # ★ 2026-10-17（P0-1 根因之二）：**不在每个连接上切 journal_mode**。
    #   `PRAGMA journal_mode=WAL` 在库已是 WAL 时通常是读，但在
    #   「另一连接正在 checkpoint / 有未提交事务 / 有外部进程持有」时，切模式要拿**排他锁**
    #   ⇒ 失败即抛 `sqlite3.OperationalError: attempt to write a readonly database`。
    #   而 `_connect()` 是**每次鉴权、每次读写**都调用的（`get_session` 由中间件每请求调）
    #   ⇒ 高频撞锁，表现为 `/api/auth/me`、`create_user` 等**随机 500**。
    #   实测证据（2026-10-17）：同时跑两个 uvicorn 指向同一 `security.db` 时，
    #   `create_user` 直接 500；清理为单实例后立即恢复 201。
    #   ⇒ WAL 只在 `init_security_db()` 里设一次；连接级只保留必要项。
    connection.execute("PRAGMA busy_timeout=10000")     # 争用时等待而非立即失败
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_security_db() -> None:
    with _connect() as connection:
        # ★ WAL 在**初始化时设一次**即可（连接级不再切，见 `_connect` 的说明）。
        #   失败不影响可用性（默认 journal 模式也能工作），但**不静默**：留日志。
        try:
            connection.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error as exc:
            logger.warning("[会话] 无法切换到 WAL（继续用默认 journal 模式）：%s", exc)
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                company_ids TEXT NOT NULL DEFAULT '[]',
                active INTEGER NOT NULL DEFAULT 1,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                csrf_hash TEXT NOT NULL,
                selected_company_id INTEGER,
                created_at INTEGER NOT NULL,
                last_seen INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                client_fingerprint TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS ix_sessions_expires_at ON sessions(expires_at);
            CREATE TABLE IF NOT EXISTS login_attempts (
                identity_hash TEXT PRIMARY KEY,
                failures INTEGER NOT NULL,
                window_started INTEGER NOT NULL,
                blocked_until INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        _ensure_user_columns(connection)
    _bootstrap_admin_from_environment()
    _ensure_authorization_schema()


def _ensure_authorization_schema() -> None:
    """幂等建立**授权相关表**（roles/permissions/role_permissions/user_roles/tenants）。

    ★ 为什么在这里而不是只在 `engine/rbac.py` 里懒建：身份库的初始化**只有一处**
      （`init_security_db`）。若只在"第一次用到 rbac 时"才建表，会出现
      「库已初始化但授权表缺失」的中间态 —— 自检脚本、离线 CLI（`manage_users.py`）
      看到的就是一个**不完整**的身份库。这里做，`engine/rbac.ensure_rbac_schema()`
      仍保留（幂等、可在换库/测试时重复调用），二者不冲突。
    ★ 失败必须**可见**：授权表建不起来会让所有权限判定失效，绝不静默。
    """
    try:
        from engine.rbac import ensure_rbac_schema as _ensure   # noqa: PLC0415
        _ensure()
    except Exception as exc:                                    # noqa: BLE001
        import sys as _sys
        print("[security] ⚠ 授权表初始化失败（权限判定将不可用）：%r" % (exc,),
              file=_sys.stderr, flush=True)


#: `users` 表在 P0-8 需要追加的列（**只增不删**，幂等补列 = 本项目 migration 底座）。
#: ★ `role` 的两值 `CHECK` 约束**不改**（SQLite 无法 `ALTER ... CHECK`，改动会让
#:   既有 `is_admin` 判定与历史数据失配）；细粒度角色由 `engine/rbac.py` 的
#:   `user_roles` / `role_permissions` 承担，`users.role` 仅保留 'admin'/'user' 语义。
_USER_ADDED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("display_name", "TEXT NOT NULL DEFAULT ''"),
    ("phone", "TEXT NOT NULL DEFAULT ''"),
    ("id_card", "TEXT NOT NULL DEFAULT ''"),
    ("bank_account", "TEXT NOT NULL DEFAULT ''"),
    ("tenant_id", "INTEGER"),
)


def _ensure_user_columns(connection) -> None:
    """幂等补列（旧库升级路径；列序不变、既有列不动）。"""
    existing = {row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()}
    for name, ddl in _USER_ADDED_COLUMNS:
        if name not in existing:
            connection.execute("ALTER TABLE users ADD COLUMN %s %s" % (name, ddl))


def validate_password(password: str) -> None:
    if len(password or "") < PASSWORD_MIN_LENGTH:
        raise ValueError(f"password must be at least {PASSWORD_MIN_LENGTH} characters")
    categories = (
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() for c in password),
    )
    if sum(categories) < 3:
        raise ValueError("password must use at least three character categories")


def hash_password(password: str, *, salt: Optional[bytes] = None,
                  skip_policy_check: bool = False) -> str:
    # ★ 2026-10-15:`skip_policy_check` 仅用于「初始密码=手机号」的账号设置
    #   (手机号 11 位天然过不了 12 位策略;弱初始密由 must_change_password 兜底)。
    #   默认 False ⇒ 既有调用一字不改、策略照常生效。
    if not skip_policy_check:
        validate_password(password)
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=actual_salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return f"scrypt$16384$8$1${actual_salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(digest_hex)),
        )
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (TypeError, ValueError):
        return False


def create_user(
    username: str,
    password: str,
    *,
    role: str = "user",
    company_ids: Iterable[int] = (),
    must_change_password: bool = False,
    display_name: str = "",
    phone: str = "",
    id_card: str = "",
    bank_account: str = "",
    tenant_id: Optional[int] = None,
    skip_policy_check: bool = False,
) -> int:
    """新建用户。

    ★ P0-8：`display_name/phone/id_card/bank_account/tenant_id` 为**追加**参数
      （全部带默认值 ⇒ 既有调用一字不改）。`phone/id_card/bank_account` 是**敏感字段**：
      落库保留原文以便追责，**出参一律由 `engine/rbac.mask_for_session()` 脱敏**。
    ★ `role` 仍只接受 'admin'/'user'（两值 `CHECK` 约束）；细粒度角色由
      `engine/rbac.assign_user_roles()` 写入 `user_roles`。
    """
    normalized = (username or "").strip()
    if not _USERNAME_RE.fullmatch(normalized):
        raise ValueError("username must be 2-64 safe characters")
    if role not in {"admin", "user"}:
        raise ValueError("role must be admin or user")
    allowed = sorted({int(value) for value in company_ids if int(value) > 0})
    try:
        tenant = int(tenant_id) if tenant_id is not None else None
    except (TypeError, ValueError):
        raise ValueError("tenant_id must be an integer")
    now = int(time.time())
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO users
                (username, password_hash, role, company_ids, active,
                 must_change_password, created_at, updated_at,
                 display_name, phone, id_card, bank_account, tenant_id)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized,
                hash_password(password, skip_policy_check=skip_policy_check),
                role,
                json.dumps(allowed),
                int(must_change_password),
                now,
                now,
                str(display_name or "").strip()[:80],
                str(phone or "").strip()[:40],
                str(id_card or "").strip()[:40],
                str(bank_account or "").strip()[:40],
                tenant,
            ),
        )
        return int(cursor.lastrowid)


def reset_password(username: str, password: str, *, revoke_sessions: bool = True) -> None:
    now = int(time.time())
    with _connect() as connection:
        row = connection.execute(
            "SELECT id FROM users WHERE username = ? COLLATE NOCASE",
            ((username or "").strip(),),
        ).fetchone()
        if not row:
            raise ValueError("user not found")
        connection.execute(
            "UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
            (hash_password(password), now, row["id"]),
        )
        if revoke_sessions:
            connection.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))


def list_users() -> list[dict]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT id, username, role, company_ids, active, created_at FROM users ORDER BY id"
        ).fetchall()
    return [
        {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "company_ids": json.loads(row["company_ids"] or "[]"),
            "active": bool(row["active"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


# ── P0-8：用户读取/维护（唯一权威仍是本模块；engine/access_service 只薄转发）─────

#: `users` 可被接口更新的字段白名单（**禁**把任意列名直接拼进 UPDATE）
UPDATABLE_USER_FIELDS: tuple[str, ...] = (
    "display_name", "phone", "id_card", "bank_account", "tenant_id", "role",
)


def _row_to_user(row) -> dict:
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "display_name": row["display_name"] or "",
        "role": row["role"],
        "company_ids": json.loads(row["company_ids"] or "[]"),
        "active": bool(row["active"]),
        "must_change_password": bool(row["must_change_password"]),
        "phone": row["phone"] or "",
        "id_card": row["id_card"] or "",
        "bank_account": row["bank_account"] or "",
        "tenant_id": (int(row["tenant_id"]) if row["tenant_id"] is not None else None),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


_USER_SELECT = (
    "SELECT id, username, display_name, role, company_ids, active, "
    "must_change_password, phone, id_card, bank_account, tenant_id, "
    "created_at, updated_at FROM users"
)


def get_user(user_id: int) -> Optional[dict]:
    with _connect() as connection:
        row = connection.execute(_USER_SELECT + " WHERE id=?", (int(user_id),)).fetchone()
    return _row_to_user(row) if row else None


def find_user(username: str) -> Optional[dict]:
    with _connect() as connection:
        row = connection.execute(
            _USER_SELECT + " WHERE username=? COLLATE NOCASE",
            ((username or "").strip(),)).fetchone()
    return _row_to_user(row) if row else None


def _user_scope_clause(tenant_id, include_inactive: bool,
                       include_null_tenant: bool = False):
    where, params = [], []
    if tenant_id is not None:
        if include_null_tenant:
            # ★ `tenant_id IS NULL` = "未指定组织"的账号（含 `APP_ADMIN_USERNAME` 引导超管），
            #   语义上归属**默认组织** ⇒ 只在查默认组织时并入，绝不并入其他组织（否则泄漏）。
            where.append("(tenant_id = ? OR tenant_id IS NULL)")
        else:
            where.append("tenant_id = ?")
        params.append(int(tenant_id))
    if not include_inactive:
        where.append("active = 1")
    return (" WHERE " + " AND ".join(where)) if where else "", params


def list_users_detailed(*, tenant_id=None, include_inactive: bool = True,
                        limit: int = 500, offset: int = 0,
                        include_null_tenant: bool = False) -> list[dict]:
    """按租户列用户（**租户过滤在此处**；接口层不得各写一套过滤口径）。"""
    clause, params = _user_scope_clause(tenant_id, include_inactive, include_null_tenant)
    sql = _USER_SELECT + clause + " ORDER BY id LIMIT ? OFFSET ?"
    with _connect() as connection:
        rows = connection.execute(sql, params + [int(limit), int(offset)]).fetchall()
    return [_row_to_user(r) for r in rows]


def count_users(*, tenant_id=None, include_inactive: bool = True,
                include_null_tenant: bool = False) -> int:
    clause, params = _user_scope_clause(tenant_id, include_inactive, include_null_tenant)
    with _connect() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM users" + clause,
                                      params).fetchone()[0] or 0)


def set_user_active(user_id: int, active: bool) -> bool:
    """启用/停用（停用即登录被拒，见 `authenticate`）。返回是否命中行。"""
    with _connect() as connection:
        cur = connection.execute(
            "UPDATE users SET active=?, updated_at=? WHERE id=?",
            (1 if active else 0, int(time.time()), int(user_id)))
        return cur.rowcount > 0


def set_user_companies(user_id: int, company_ids: Iterable[int]) -> list[int]:
    """**覆盖式**设置用户的账套授权（数据权限的唯一写入点）。返回最新列表。"""
    allowed = sorted({int(v) for v in (company_ids or []) if int(v) > 0})
    with _connect() as connection:
        connection.execute(
            "UPDATE users SET company_ids=?, updated_at=? WHERE id=?",
            (json.dumps(allowed), int(time.time()), int(user_id)))
    return allowed


def update_user_fields(user_id: int, **fields) -> Optional[dict]:
    """更新白名单字段（其余字段名 ⇒ `ValueError`，**不静默忽略**）。"""
    sets, params = [], []
    for key, value in fields.items():
        if key not in UPDATABLE_USER_FIELDS:
            raise ValueError("不可更新的用户字段：%s" % key)
        if key == "tenant_id":
            params.append(int(value) if value is not None else None)
        elif key == "role":
            if value not in {"admin", "user"}:
                raise ValueError("role must be admin or user")
            params.append(str(value))
        else:
            params.append(str(value or "").strip()[:80])
        sets.append("%s=?" % key)
    if not sets:
        return get_user(user_id)
    sets.append("updated_at=?")
    params.append(int(time.time()))
    with _connect() as connection:
        cur = connection.execute(
            "UPDATE users SET %s WHERE id=?" % ", ".join(sets),
            params + [int(user_id)])
        if cur.rowcount <= 0:
            return None
    return get_user(user_id)


# 2026-09-05 修复：/api/companies 必须能在创建时把账套授权给当前用户（普通用户也能建账套并查看），
# 否则新建账套后选择页始终看不到。前端契约要求创建后立即可访问。
def grant_company_to_user(user_id: int, company_id: int) -> list[int]:
    """把账套加入用户的 allowed_company_ids 列表（去重），返回最新列表。"""
    if int(user_id) <= 0 or int(company_id) <= 0:
        return []
    with _connect() as connection:
        row = connection.execute(
            "SELECT company_ids FROM users WHERE id=?",
            (int(user_id),),
        ).fetchone()
        if not row:
            return []
        current = sorted({
            int(v) for v in json.loads(row["company_ids"] or "[]") if int(v) > 0
        } | {int(company_id)})
        connection.execute(
            "UPDATE users SET company_ids=?, updated_at=? WHERE id=?",
            (json.dumps(current), int(time.time()), int(user_id)),
        )
        return current


# 2026-09-05 修复：/api/companies/{id} DELETE 时也撤销用户对该账套的授权。
def revoke_company_from_user(user_id: int, company_id: int) -> list[int]:
    if int(user_id) <= 0 or int(company_id) <= 0:
        return []
    with _connect() as connection:
        row = connection.execute(
            "SELECT company_ids FROM users WHERE id=?",
            (int(user_id),),
        ).fetchone()
        if not row:
            return []
        current = sorted({
            int(v) for v in json.loads(row["company_ids"] or "[]")
            if int(v) > 0 and int(v) != int(company_id)
        })
        connection.execute(
            "UPDATE users SET company_ids=?, updated_at=? WHERE id=?",
            (json.dumps(current), int(time.time()), int(user_id)),
        )
        return current


# 2026-09-05 修复：删除账套的级联清理——撤销全部用户的授权 + 清除会话选中态，
# 避免选择账套页残留已删除账套的会话状态。
def delete_company_cascade(company_id: int) -> int:
    """删除账套后：从所有用户的 company_ids 中移除该账套，并清空相关会话的选中态。返回受影响用户数。"""
    cid = int(company_id)
    if cid <= 0:
        return 0
    affected = 0
    with _connect() as connection:
        rows = connection.execute("SELECT id, company_ids FROM users").fetchall()
        for row in rows:
            ids = [
                int(v) for v in json.loads(row["company_ids"] or "[]") if int(v) > 0
            ]
            if cid in ids:
                ids.remove(cid)
                connection.execute(
                    "UPDATE users SET company_ids=?, updated_at=? WHERE id=?",
                    (json.dumps(sorted(ids)), int(time.time()), int(row["id"])),
                )
                affected += 1
        connection.execute(
            "UPDATE sessions SET selected_company_id=NULL WHERE selected_company_id=?",
            (cid,),
        )
    return affected


def _identity_hash(username: str, client_ip: str) -> str:
    value = f"{(username or '').casefold()}|{client_ip or 'unknown'}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def login_is_allowed(username: str, client_ip: str) -> tuple[bool, int]:
    identity = _identity_hash(username, client_ip)
    now = int(time.time())
    with _connect() as connection:
        row = connection.execute(
            "SELECT blocked_until FROM login_attempts WHERE identity_hash=?",
            (identity,),
        ).fetchone()
    blocked_until = int(row["blocked_until"]) if row else 0
    return blocked_until <= now, max(0, blocked_until - now)


def record_login_result(username: str, client_ip: str, success: bool) -> None:
    identity = _identity_hash(username, client_ip)
    now = int(time.time())
    with _connect() as connection:
        if success:
            connection.execute("DELETE FROM login_attempts WHERE identity_hash=?", (identity,))
            return
        row = connection.execute(
            "SELECT failures, window_started FROM login_attempts WHERE identity_hash=?",
            (identity,),
        ).fetchone()
        failures = int(row["failures"]) if row and now - int(row["window_started"]) < 900 else 0
        started = int(row["window_started"]) if failures else now
        failures += 1
        blocked_until = now + min(900, 30 * (2 ** max(0, failures - 5))) if failures >= 5 else 0
        connection.execute(
            """
            INSERT INTO login_attempts(identity_hash, failures, window_started, blocked_until)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(identity_hash) DO UPDATE SET
                failures=excluded.failures,
                window_started=excluded.window_started,
                blocked_until=excluded.blocked_until
            """,
            (identity, failures, started, blocked_until),
        )


def authenticate(username: str, password: str) -> Optional[dict]:
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT id, username, password_hash, role, company_ids, active,
                   must_change_password, display_name, tenant_id
            FROM users WHERE username=? COLLATE NOCASE
            """,
            ((username or "").strip(),),
        ).fetchone()
    if not row or not row["active"] or not verify_password(password or "", row["password_hash"]):
        return None
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "display_name": row["display_name"] or "",
        "role": row["role"],
        "company_ids": json.loads(row["company_ids"] or "[]"),
        "must_change_password": bool(row["must_change_password"]),
        "tenant_id": (int(row["tenant_id"]) if row["tenant_id"] is not None else None),
    }


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256((raw_token or "").encode("utf-8")).hexdigest()


def create_session(user: dict, *, client_fingerprint: str = "") -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    now = int(time.time())
    expires = now + SESSION_TTL_SECONDS
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO sessions
                (token_hash, user_id, csrf_hash, selected_company_id,
                 created_at, last_seen, expires_at, client_fingerprint)
            VALUES (?, ?, ?, NULL, ?, ?, ?, ?)
            """,
            (
                _token_hash(token),
                int(user["id"]),
                _token_hash(csrf_token),
                now,
                now,
                expires,
                _token_hash(client_fingerprint) if client_fingerprint else "",
            ),
        )
    return token, csrf_token


def sweep_expired_sessions(now: Optional[int] = None) -> bool:
    """清理过期会话（**低频**：每进程最多每 `_SWEEP_INTERVAL_SECONDS` 秒一次）。

    返回是否真的执行了清理。这是 P0-1 的配套——把原先"每请求都删"改为"定期删"。
    过期会话的**拒绝**不依赖本函数（`get_session` 的 SQL 已显式比较 `expires_at > now`），
    本函数只负责回收磁盘行。
    """
    global _last_sweep_at, _session_write_failures
    moment = float(time.time() if now is None else now)
    with _session_state_lock:
        if moment - _last_sweep_at < _SWEEP_INTERVAL_SECONDS:
            return False
        _last_sweep_at = moment
    try:
        with _connect() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at<=?", (int(moment),))
        return True
    except sqlite3.Error as exc:
        # 失败也**保持节流**（退避语义）：否则每次请求都会重撞同一个错误
        _session_write_failures += 1
        logger.warning("[会话] 过期会话清理未能执行（不影响本次会话读取）：%s", exc)
        return False


def touch_session(token_hash: str, now: Optional[int] = None) -> bool:
    """更新 `last_seen`（**低频**：每会话最多每 `_TOUCH_INTERVAL_SECONDS` 秒一次）。

    返回是否真的写了库。`last_seen` 当前**无任何消费点**（全仓仅此处写、无人读），
    因此节流不改变任何业务行为；保留它是为了留痕。
    """
    global _session_write_failures
    moment = float(time.time() if now is None else now)
    with _session_state_lock:
        if moment - _last_touch_at.get(token_hash, 0.0) < _TOUCH_INTERVAL_SECONDS:
            return False
        _last_touch_at[token_hash] = moment
        # 防止节流缓存无限增长：超过上限时清掉一半最旧的键（只影响"下次多写一次"，无副作用）
        if len(_last_touch_at) > 4096:
            for _k in sorted(_last_touch_at, key=_last_touch_at.get)[:2048]:
                _last_touch_at.pop(_k, None)
    try:
        with _connect() as connection:
            connection.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?",
                               (int(moment), token_hash))
        return True
    except sqlite3.Error as exc:
        _session_write_failures += 1
        logger.warning("[会话] last_seen 未能更新（不影响本次会话读取）：%s", exc)
        return False


def get_session(raw_token: str, *, client_fingerprint: str = "") -> Optional[SessionContext]:
    """按令牌取会话。**主路径只读**（P0-1）——写库是附带的、低频的、失败不阻断。"""
    if not raw_token:
        return None
    now = int(time.time())
    token_hash = _token_hash(raw_token)
    with _connect() as connection:
        # ★ 过期判定必须在 SQL 里显式做：不能依赖"清理任务有没有跑过"
        #   （P0-1 之前靠 `DELETE ... WHERE expires_at<=?` 顺带淘汰；
        #     清理改为低频后，若这里不比较 expires_at，过期会话在清理周期内会被放行）
        row = connection.execute(
            """
            SELECT s.user_id, s.csrf_hash, s.selected_company_id, s.expires_at,
                   s.client_fingerprint, u.username, u.role, u.company_ids, u.active,
                   u.tenant_id
            FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at > ?
            """,
            (token_hash, now),
        ).fetchone()
    if not row or not row["active"]:
        return None
    expected_fingerprint = row["client_fingerprint"] or ""
    actual_fingerprint = _token_hash(client_fingerprint) if client_fingerprint else ""
    if expected_fingerprint and not hmac.compare_digest(expected_fingerprint, actual_fingerprint):
        return None
    # 写操作在读事务之外、且失败不阻断（读是主路径）
    sweep_expired_sessions(now)
    touch_session(token_hash, now)
    return SessionContext(
        user_id=int(row["user_id"]),
        username=row["username"],
        role=row["role"],
        allowed_company_ids=frozenset(json.loads(row["company_ids"] or "[]")),
        selected_company_id=(
            int(row["selected_company_id"]) if row["selected_company_id"] is not None else None
        ),
        csrf_hash=row["csrf_hash"],
        expires_at=int(row["expires_at"]),
        tenant_id=(int(row["tenant_id"]) if row["tenant_id"] is not None else None),
    )


def csrf_is_valid(session: SessionContext, csrf_token: str) -> bool:
    return bool(csrf_token) and hmac.compare_digest(session.csrf_hash, _token_hash(csrf_token))


def select_company(raw_token: str, company_id: int, session: SessionContext) -> bool:
    company = int(company_id)
    if company <= 0 or not session.can_access_company(company):
        return False
    with _connect() as connection:
        connection.execute(
            "UPDATE sessions SET selected_company_id=? WHERE token_hash=?",
            (company, _token_hash(raw_token)),
        )
    return True


def revoke_session(raw_token: str) -> None:
    if raw_token:
        with _connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(raw_token),))


def revoke_all_sessions(username: str) -> int:
    with _connect() as connection:
        cursor = connection.execute(
            """
            DELETE FROM sessions WHERE user_id IN
              (SELECT id FROM users WHERE username=? COLLATE NOCASE)
            """,
            ((username or "").strip(),),
        )
        return int(cursor.rowcount)


def is_public_path(path: str) -> bool:
    # `/api/v1/auth/login` 是 P0-8 新增的登录端点（与既有 `/api/auth/login` 同语义，
    # 同一实现 `security_web.login_handler`）。**必须**登记为公开路径，否则请求会先被
    # 鉴权中间件拦成 401，永远到不了登录处理器。
    # ★ 2026-10-15:/api/auth/register 与 /account-setup 是免登录的账号设置入口
    #   (手机号注册,初始密码=手机号),与登录同语义,必须公开。
    if path in {"/login", "/healthz", "/api/auth/login", "/api/v1/auth/login", "/favicon.ico", "/api/auth/register", "/account-setup"}:
        return True
    if path.startswith("/static/"):
        return Path(path).suffix.lower() in _PUBLIC_ASSET_EXTENSIONS
    return False


def is_protected_static_path(path: str) -> bool:
    return path.startswith("/static/") and Path(path).suffix.lower() in _PROTECTED_STATIC_EXTENSIONS


def normalize_client_ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address((value or "").split(",")[0].strip()))
    except ValueError:
        return "unknown"


def _bootstrap_admin_from_environment() -> None:
    username = os.environ.get("APP_ADMIN_USERNAME", "").strip()
    password = os.environ.get("APP_ADMIN_PASSWORD", "")
    if not username or not password:
        return
    with _connect() as connection:
        exists = connection.execute("SELECT 1 FROM users LIMIT 1").fetchone()
    if not exists:
        create_user(username, password, role="admin")



def change_password_with_old(username: str, old_password: str, new_password: str) -> None:
    """★ 2026-10-15 用户自助修改密码：验证旧密码 ⇒ 写新密码 ⇒ 清 must_change_password
    ⇒ 撤销该用户全部会话（改密后需重新登录）。

    与 `reset_password`（管理员重置：不验旧密、语义为"代设置"）的区别：
    本函数**必须**验证旧密码，且**必须**清 `must_change_password` 标记。"""
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, password_hash FROM users WHERE username = ? COLLATE NOCASE",
            ((username or "").strip(),),
        ).fetchone()
        if not row:
            raise ValueError("user not found")
        if not verify_password(old_password or "", row["password_hash"]):
            raise ValueError("原密码不正确")
        try:
            validate_password(new_password or "")
        except ValueError:
            raise ValueError("新密码强度不足：至少 12 位，且需包含大小写字母/数字/符号中的至少三类")
        connection.execute(
            "UPDATE users SET password_hash=?, must_change_password=0, updated_at=? WHERE id=?",
            (hash_password(new_password), int(time.time()), row["id"]),
        )
        connection.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))


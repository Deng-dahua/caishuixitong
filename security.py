"""Local authentication, authorization and session storage.

Only password hashes and token hashes are persisted.  Raw session and CSRF
tokens exist solely in the browser cookies for the lifetime of a session.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from runtime_storage import SECURITY_DB


PASSWORD_MIN_LENGTH = 12
SESSION_TTL_SECONDS = int(os.environ.get("APP_SESSION_TTL_SECONDS", "28800"))
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
    connection.execute("PRAGMA journal_mode=WAL")
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
    _bootstrap_admin_from_environment()


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


def hash_password(password: str, *, salt: Optional[bytes] = None) -> str:
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
) -> int:
    normalized = (username or "").strip()
    if not _USERNAME_RE.fullmatch(normalized):
        raise ValueError("username must be 2-64 safe characters")
    if role not in {"admin", "user"}:
        raise ValueError("role must be admin or user")
    allowed = sorted({int(value) for value in company_ids if int(value) > 0})
    now = int(time.time())
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO users
                (username, password_hash, role, company_ids, active,
                 must_change_password, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                normalized,
                hash_password(password),
                role,
                json.dumps(allowed),
                int(must_change_password),
                now,
                now,
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
                   must_change_password
            FROM users WHERE username=? COLLATE NOCASE
            """,
            ((username or "").strip(),),
        ).fetchone()
    if not row or not row["active"] or not verify_password(password or "", row["password_hash"]):
        return None
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "role": row["role"],
        "company_ids": json.loads(row["company_ids"] or "[]"),
        "must_change_password": bool(row["must_change_password"]),
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


def get_session(raw_token: str, *, client_fingerprint: str = "") -> Optional[SessionContext]:
    if not raw_token:
        return None
    now = int(time.time())
    with _connect() as connection:
        connection.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
        row = connection.execute(
            """
            SELECT s.user_id, s.csrf_hash, s.selected_company_id, s.expires_at,
                   s.client_fingerprint, u.username, u.role, u.company_ids, u.active
            FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=?
            """,
            (_token_hash(raw_token),),
        ).fetchone()
        if not row or not row["active"]:
            return None
        expected_fingerprint = row["client_fingerprint"] or ""
        actual_fingerprint = _token_hash(client_fingerprint) if client_fingerprint else ""
        if expected_fingerprint and not hmac.compare_digest(expected_fingerprint, actual_fingerprint):
            return None
        connection.execute(
            "UPDATE sessions SET last_seen=? WHERE token_hash=?",
            (now, _token_hash(raw_token)),
        )
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
    if path in {"/login", "/healthz", "/api/auth/login", "/favicon.ico"}:
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

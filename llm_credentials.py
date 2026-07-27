"""Per-user encrypted LLM credential storage.

Each credential is encrypted with AES-GCM and request-specific associated data.
On Windows the deployment launcher stores the AES master key under DPAPI, so
the database and the protected master-key file are both required to decrypt a
user credential.
"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import security
from llm_providers import PROVIDERS, validate_model, validate_provider


_KEY_MIN_LENGTH = 8
_KEY_MAX_LENGTH = 4096
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_DPAPI_PREFIX = b"DP1"
_AES_PREFIX = b"AG1"


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    database = Path(security.SECURITY_DB)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database), timeout=10)
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


def init_llm_credentials_db() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS llm_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                secret_cipher BLOB NOT NULL,
                secret_last4 TEXT NOT NULL DEFAULT '',
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(user_id, provider)
            );
            CREATE INDEX IF NOT EXISTS ix_llm_credentials_user
                ON llm_credentials(user_id);
            CREATE INDEX IF NOT EXISTS ix_llm_credentials_default
                ON llm_credentials(user_id, is_default);
            CREATE TABLE IF NOT EXISTS llm_credential_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                credential_id INTEGER,
                provider TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL,
                outcome TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_llm_credential_audit_user
                ON llm_credential_audit(user_id, created_at);
            """
        )


def _validate_api_key(api_key: str) -> str:
    value = (api_key or "").strip()
    if not (_KEY_MIN_LENGTH <= len(value) <= _KEY_MAX_LENGTH):
        raise ValueError("API Key 长度不正确")
    if _CONTROL_RE.search(value):
        raise ValueError("API Key 含有无效字符")
    return value


def _associated_data(user_id: int, credential_id: int, provider: str) -> bytes:
    return (
        f"caishuixitong|llm-credential|v1|{int(user_id)}|"
        f"{int(credential_id)}|{provider}"
    ).encode("utf-8")


def _dpapi_protect(plaintext: bytes, entropy: bytes) -> bytes:
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    def blob(data: bytes):
        buffer = ctypes.create_string_buffer(data)
        value = DATA_BLOB(
            len(data),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        )
        return value, buffer

    input_blob, input_buffer = blob(plaintext)
    entropy_blob, entropy_buffer = blob(entropy)
    output_blob = DATA_BLOB()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.wintypes.LPCWSTR,
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = ctypes.wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    ok = crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        "Caishuixitong user LLM credential",
        ctypes.byref(entropy_blob),
        None,
        None,
        0x01,
        ctypes.byref(output_blob),
    )
    _ = (input_buffer, entropy_buffer)
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _dpapi_unprotect(ciphertext: bytes, entropy: bytes) -> bytes:
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    def blob(data: bytes):
        buffer = ctypes.create_string_buffer(data)
        value = DATA_BLOB(
            len(data),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        )
        return value, buffer

    input_blob, input_buffer = blob(ciphertext)
    entropy_blob, entropy_buffer = blob(entropy)
    output_blob = DATA_BLOB()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.POINTER(ctypes.wintypes.LPWSTR),
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = ctypes.wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        0x01,
        ctypes.byref(output_blob),
    )
    _ = (input_buffer, entropy_buffer)
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _portable_master_key() -> bytes:
    encoded = os.environ.get("APP_LLM_MASTER_KEY", "").strip()
    try:
        key = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, TypeError):
        key = b""
    if len(key) != 32:
        raise RuntimeError(
            "必须通过 APP_LLM_MASTER_KEY 提供 32 字节主密钥"
        )
    return key


def _protect_secret(secret: str, *, user_id: int, credential_id: int, provider: str) -> bytes:
    plaintext = secret.encode("utf-8")
    associated_data = _associated_data(user_id, credential_id, provider)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_portable_master_key()).encrypt(
        nonce,
        plaintext,
        associated_data,
    )
    return _AES_PREFIX + nonce + ciphertext


def _unprotect_secret(
    ciphertext: bytes,
    *,
    user_id: int,
    credential_id: int,
    provider: str,
) -> str:
    associated_data = _associated_data(user_id, credential_id, provider)
    payload = bytes(ciphertext)
    if payload.startswith(_AES_PREFIX):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = payload[len(_AES_PREFIX):len(_AES_PREFIX) + 12]
        encrypted = payload[len(_AES_PREFIX) + 12:]
        plaintext = AESGCM(_portable_master_key()).decrypt(
            nonce,
            encrypted,
            associated_data,
        )
    elif payload.startswith(_DPAPI_PREFIX):
        if os.name != "nt":
            raise RuntimeError("Windows DPAPI 密钥只能在原 Windows 账户下解密")
        plaintext = _dpapi_unprotect(payload[len(_DPAPI_PREFIX):], associated_data)
    else:
        raise RuntimeError("未知的密钥加密格式")
    return plaintext.decode("utf-8")


def _audit(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    credential_id: Optional[int],
    provider: str,
    action: str,
    outcome: str = "success",
    details: Optional[dict] = None,
) -> None:
    safe_details = details or {}
    connection.execute(
        """
        INSERT INTO llm_credential_audit
            (user_id, credential_id, provider, action, outcome, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id),
            int(credential_id) if credential_id is not None else None,
            provider,
            action,
            outcome,
            json.dumps(safe_details, ensure_ascii=False, separators=(",", ":")),
            int(time.time()),
        ),
    )


def list_credentials(user_id: int) -> list[dict]:
    init_llm_credentials_db()
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, provider, model, secret_last4, is_default, created_at, updated_at
            FROM llm_credentials
            WHERE user_id=?
            ORDER BY is_default DESC, updated_at DESC, id DESC
            """,
            (int(user_id),),
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "provider": row["provider"],
            "provider_name": PROVIDERS.get(row["provider"], {}).get(
                "name", row["provider"]
            ),
            "model": row["model"],
            "last4": row["secret_last4"],
            "is_default": bool(row["is_default"]),
            "created_at": int(row["created_at"]),
            "updated_at": int(row["updated_at"]),
        }
        for row in rows
    ]


def create_or_replace_credential(
    user_id: int,
    *,
    provider: str,
    model: str | None,
    api_key: str,
    set_default: bool = False,
) -> dict:
    init_llm_credentials_db()
    normalized_provider = validate_provider(provider)
    normalized_model = validate_model(normalized_provider, model)
    normalized_key = _validate_api_key(api_key)
    now = int(time.time())

    with _connect() as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE id=? AND active=1",
            (int(user_id),),
        ).fetchone()
        if not user:
            raise ValueError("用户不存在或已停用")

        existing = connection.execute(
            "SELECT id, is_default FROM llm_credentials WHERE user_id=? AND provider=?",
            (int(user_id), normalized_provider),
        ).fetchone()
        has_default = connection.execute(
            "SELECT 1 FROM llm_credentials WHERE user_id=? AND is_default=1",
            (int(user_id),),
        ).fetchone()
        should_default = bool(set_default or not has_default)

        if existing:
            credential_id = int(existing["id"])
            ciphertext = _protect_secret(
                normalized_key,
                user_id=int(user_id),
                credential_id=credential_id,
                provider=normalized_provider,
            )
            connection.execute(
                """
                UPDATE llm_credentials
                SET model=?, secret_cipher=?, secret_last4=?, updated_at=?
                WHERE id=? AND user_id=?
                """,
                (
                    normalized_model,
                    sqlite3.Binary(ciphertext),
                    normalized_key[-4:],
                    now,
                    credential_id,
                    int(user_id),
                ),
            )
            action = "rotated"
        else:
            cursor = connection.execute(
                """
                INSERT INTO llm_credentials
                    (user_id, provider, model, secret_cipher, secret_last4,
                     is_default, created_at, updated_at)
                VALUES (?, ?, ?, X'', ?, 0, ?, ?)
                """,
                (
                    int(user_id),
                    normalized_provider,
                    normalized_model,
                    normalized_key[-4:],
                    now,
                    now,
                ),
            )
            credential_id = int(cursor.lastrowid)
            ciphertext = _protect_secret(
                normalized_key,
                user_id=int(user_id),
                credential_id=credential_id,
                provider=normalized_provider,
            )
            connection.execute(
                "UPDATE llm_credentials SET secret_cipher=? WHERE id=?",
                (sqlite3.Binary(ciphertext), credential_id),
            )
            action = "created"

        if should_default:
            connection.execute(
                "UPDATE llm_credentials SET is_default=0 WHERE user_id=?",
                (int(user_id),),
            )
            connection.execute(
                "UPDATE llm_credentials SET is_default=1 WHERE id=? AND user_id=?",
                (credential_id, int(user_id)),
            )
        _audit(
            connection,
            user_id=int(user_id),
            credential_id=credential_id,
            provider=normalized_provider,
            action=action,
            details={"model": normalized_model, "set_default": should_default},
        )

    return get_credential_status(int(user_id), credential_id)


def get_credential_status(user_id: int, credential_id: int) -> dict:
    credentials = list_credentials(int(user_id))
    for credential in credentials:
        if credential["id"] == int(credential_id):
            return credential
    raise ValueError("未找到该模型凭据")


def get_credential_secret(user_id: int, credential_id: int) -> dict:
    init_llm_credentials_db()
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT id, user_id, provider, model, secret_cipher
            FROM llm_credentials
            WHERE id=? AND user_id=?
            """,
            (int(credential_id), int(user_id)),
        ).fetchone()
    if not row:
        raise ValueError("未找到该模型凭据")
    return {
        "id": int(row["id"]),
        "provider": row["provider"],
        "base_url": PROVIDERS[row["provider"]]["base_url"],
        "model": row["model"],
        "key": _unprotect_secret(
            row["secret_cipher"],
            user_id=int(row["user_id"]),
            credential_id=int(row["id"]),
            provider=row["provider"],
        ),
    }


def get_default_credential(user_id: int) -> Optional[dict]:
    init_llm_credentials_db()
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT id FROM llm_credentials
            WHERE user_id=? AND is_default=1
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()
    if not row:
        return None
    return get_credential_secret(int(user_id), int(row["id"]))


def set_default_credential(user_id: int, credential_id: int) -> dict:
    init_llm_credentials_db()
    now = int(time.time())
    with _connect() as connection:
        row = connection.execute(
            "SELECT provider FROM llm_credentials WHERE id=? AND user_id=?",
            (int(credential_id), int(user_id)),
        ).fetchone()
        if not row:
            raise ValueError("未找到该模型凭据")
        connection.execute(
            "UPDATE llm_credentials SET is_default=0 WHERE user_id=?",
            (int(user_id),),
        )
        connection.execute(
            "UPDATE llm_credentials SET is_default=1, updated_at=? WHERE id=? AND user_id=?",
            (now, int(credential_id), int(user_id)),
        )
        _audit(
            connection,
            user_id=int(user_id),
            credential_id=int(credential_id),
            provider=row["provider"],
            action="default_changed",
        )
    return get_credential_status(int(user_id), int(credential_id))


def delete_credential(user_id: int, credential_id: int) -> None:
    init_llm_credentials_db()
    with _connect() as connection:
        row = connection.execute(
            "SELECT provider, is_default FROM llm_credentials WHERE id=? AND user_id=?",
            (int(credential_id), int(user_id)),
        ).fetchone()
        if not row:
            raise ValueError("未找到该模型凭据")
        connection.execute(
            "DELETE FROM llm_credentials WHERE id=? AND user_id=?",
            (int(credential_id), int(user_id)),
        )
        if bool(row["is_default"]):
            replacement = connection.execute(
                """
                SELECT id FROM llm_credentials
                WHERE user_id=?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (int(user_id),),
            ).fetchone()
            if replacement:
                connection.execute(
                    "UPDATE llm_credentials SET is_default=1 WHERE id=?",
                    (int(replacement["id"]),),
                )
        _audit(
            connection,
            user_id=int(user_id),
            credential_id=int(credential_id),
            provider=row["provider"],
            action="deleted",
        )


def record_test_result(
    user_id: int,
    credential_id: int,
    *,
    provider: str,
    success: bool,
    status_code: Optional[int] = None,
) -> None:
    init_llm_credentials_db()
    with _connect() as connection:
        owned = connection.execute(
            "SELECT 1 FROM llm_credentials WHERE id=? AND user_id=?",
            (int(credential_id), int(user_id)),
        ).fetchone()
        if not owned:
            raise ValueError("未找到该模型凭据")
        _audit(
            connection,
            user_id=int(user_id),
            credential_id=int(credential_id),
            provider=validate_provider(provider),
            action="connection_tested",
            outcome="success" if success else "failed",
            details={"status_code": int(status_code) if status_code else None},
        )


def migrate_legacy_credential(
    *,
    username: str,
    provider: str,
    model: str | None,
    api_key: str,
) -> dict:
    init_llm_credentials_db()
    with _connect() as connection:
        user = connection.execute(
            "SELECT id FROM users WHERE username=? COLLATE NOCASE AND active=1",
            ((username or "").strip(),),
        ).fetchone()
    if not user:
        raise ValueError("迁移目标用户不存在")
    return create_or_replace_credential(
        int(user["id"]),
        provider=provider,
        model=model,
        api_key=api_key,
        set_default=True,
    )

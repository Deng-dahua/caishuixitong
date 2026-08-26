"""Runtime paths and safe file helpers.

All mutable or sensitive files live outside ``static/``.  The location can be
overridden with APP_DATA_DIR; the default is ``<project>/data``.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("APP_DATA_DIR", PROJECT_ROOT / "data")).resolve()
CACHE_DIR = DATA_DIR / "cache"
UPLOAD_DIR = DATA_DIR / "uploads"
LOG_DIR = DATA_DIR / "logs"
SECURITY_DB = DATA_DIR / "security.db"
ACCOUNTING_DB = DATA_DIR / "accounting.db"
CORRECTION_RULES = DATA_DIR / "user_corrections.json"
ARCHIVED_CORRECTION_RULES = DATA_DIR / "deleted_correction_rules.json"
CONTENT_FEEDBACK = DATA_DIR / "content_feedback.json"
LEARNING_AGENT_WEIGHTS = DATA_DIR / "learning_agent_weights.json"

for _directory in (DATA_DIR, CACHE_DIR, UPLOAD_DIR, LOG_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

LAST_ANALYSIS_CACHE = CACHE_DIR / "last_analysis_cache.json"
ANALYSIS_HISTORY = CACHE_DIR / "analysis_history.json"
ACCESS_LOG = LOG_DIR / "access.jsonl"

_json_lock = threading.RLock()
_unsafe_filename = re.compile(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+")


def _move_legacy_private_file(destination: Path, legacy: Path) -> None:
    """Remove mutable data from the public static tree without losing it."""
    if not legacy.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        os.replace(legacy, destination)
        return
    legacy_archive = DATA_DIR / "legacy"
    legacy_archive.mkdir(parents=True, exist_ok=True)
    archived = legacy_archive / legacy.name
    counter = 1
    while archived.exists():
        archived = legacy_archive / f"{legacy.stem}.{counter}{legacy.suffix}"
        counter += 1
    os.replace(legacy, archived)


_move_legacy_private_file(
    CORRECTION_RULES,
    PROJECT_ROOT / "static" / "user_corrections.json",
)
_move_legacy_private_file(
    CONTENT_FEEDBACK,
    PROJECT_ROOT / "static" / "content_feedback.json",
)
_move_legacy_private_file(
    ARCHIVED_CORRECTION_RULES,
    PROJECT_ROOT / "static" / "_deleted_correction_rules.json",
)


def safe_filename(name: str, fallback: str = "upload") -> str:
    """Return a basename that cannot escape its destination directory."""
    basename = Path(str(name or "")).name.replace("\x00", "")
    cleaned = _unsafe_filename.sub("_", basename).strip(" ._")
    if not cleaned:
        cleaned = fallback
    stem, suffix = os.path.splitext(cleaned)
    return f"{stem[:100]}{suffix[:12].lower()}"


def _to_json_safe(value: Any, _seen: set | None = None) -> Any:
    """递归转为可 JSON 序列化结构，遇到循环引用用占位符断开。

    json.dump 的 default= 只能处理「非 JSON 原生类型」，无法处理 dict/list 的
    循环引用（会抛 ValueError: Circular reference detected）。个别企业报告内部
    可能存在自引用（如 comprehensive 的某子结构回指自身），直接 dump 会崩溃。
    这里用 id() 访问集合检测环，把回指位置替换为占位字符串，保证保存永不失败。
    """
    if _seen is None:
        _seen = set()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        vid = id(value)
        if vid in _seen:
            return "<circular reference>"
        _seen.add(vid)
        try:
            return {str(k): _to_json_safe(v, _seen) for k, v in value.items()}
        finally:
            _seen.discard(vid)
    if isinstance(value, (list, tuple, set, frozenset)):
        vid = id(value)
        if vid in _seen:
            return "<circular reference>"
        _seen.add(vid)
        try:
            return [_to_json_safe(v, _seen) for v in value]
        finally:
            _seen.discard(vid)
    # 其余类型：能原生序列化就保留，否则转字符串
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def atomic_write_json(path: os.PathLike[str] | str, value: Any) -> None:
    """Write JSON using fsync + atomic replace so crashes cannot truncate it."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _json_lock:
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=str(destination.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(_to_json_safe(value), handle, ensure_ascii=False, default=str)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, destination)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


def read_json(path: os.PathLike[str] | str, default: Any) -> Any:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def company_upload_dir(company_id: int) -> Path:
    if int(company_id) <= 0:
        raise ValueError("company_id must be positive")
    destination = UPLOAD_DIR / str(int(company_id))
    destination.mkdir(parents=True, exist_ok=True)
    return destination

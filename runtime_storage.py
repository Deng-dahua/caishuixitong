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

for _directory in (DATA_DIR, CACHE_DIR, UPLOAD_DIR, LOG_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

LAST_ANALYSIS_CACHE = CACHE_DIR / "last_analysis_cache.json"
ANALYSIS_HISTORY = CACHE_DIR / "analysis_history.json"
ACCESS_LOG = LOG_DIR / "access.jsonl"

_json_lock = threading.RLock()
_unsafe_filename = re.compile(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+")


def safe_filename(name: str, fallback: str = "upload") -> str:
    """Return a basename that cannot escape its destination directory."""
    basename = Path(str(name or "")).name.replace("\x00", "")
    cleaned = _unsafe_filename.sub("_", basename).strip(" ._")
    if not cleaned:
        cleaned = fallback
    stem, suffix = os.path.splitext(cleaned)
    return f"{stem[:100]}{suffix[:12].lower()}"


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
                json.dump(value, handle, ensure_ascii=False, default=str)
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

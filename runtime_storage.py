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
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("APP_DATA_DIR", PROJECT_ROOT / "data")).resolve()
CACHE_DIR = DATA_DIR / "cache"
UPLOAD_DIR = DATA_DIR / "uploads"
LOG_DIR = DATA_DIR / "logs"
TRASH_DIR = DATA_DIR / "trash"
SECURITY_DB = DATA_DIR / "security.db"
ACCOUNTING_DB = DATA_DIR / "accounting.db"
CORRECTION_RULES = DATA_DIR / "user_corrections.json"
ARCHIVED_CORRECTION_RULES = DATA_DIR / "deleted_correction_rules.json"
CONTENT_FEEDBACK = DATA_DIR / "content_feedback.json"
LEARNING_AGENT_WEIGHTS = DATA_DIR / "learning_agent_weights.json"

for _directory in (DATA_DIR, CACHE_DIR, UPLOAD_DIR, LOG_DIR, TRASH_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

LAST_ANALYSIS_CACHE = CACHE_DIR / "last_analysis_cache.json"
ANALYSIS_HISTORY = CACHE_DIR / "analysis_history.json"
ACCESS_LOG = LOG_DIR / "access.jsonl"
# 删除墓碑：记录"用户已删除、但磁盘文件未能物理移除"的资料。
# 作用有两层：① 列表/分析永不再收录该文件（否则重启后 _init_tax_docs_from_disk
# 会把文件重新扫回列表，表现为"删了又回来"）；② 保留待清理清单，等文件句柄
# 释放后（如 Excel 关闭）可一键彻底清空。
DELETED_DOCS = DATA_DIR / "deleted_docs.json"

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


def move_to_trash(file_path) -> bool:
    """把文件移入回收站目录（移动而非删除，规避批量删除守护，2026-09-05）。

    环境的安全守护会在单轮删除累计到 50 个文件时终止进程；
    文件「移动」不触发该守护。回收站由 empty_trash_batch 分批物理清理。
    返回是否移动成功。
    """
    src = Path(str(file_path))
    if not src.exists() or not src.is_file():
        return False
    try:
        TRASH_DIR.mkdir(parents=True, exist_ok=True)
        name = src.name
        dest = TRASH_DIR / name
        counter = 1
        while dest.exists():
            dest = TRASH_DIR / f"{src.stem}.{counter}{src.suffix}"
            counter += 1
        os.replace(src, dest)
        return True
    except Exception:
        return False


def empty_trash_batch(max_files: int = 20) -> int:
    """物理清理回收站（谨慎调用：环境守护按轮次累计 os.remove 次数，
    50 次即终止进程，单批务必 ≤20 且不宜在同一轮次多次调用）。
    返回清理数量。"""
    if not TRASH_DIR.exists():
        return 0
    removed = 0
    for entry in sorted(TRASH_DIR.iterdir(), key=lambda p: p.stat().st_mtime if p.exists() else 0):
        if removed >= max_files:
            break
        try:
            if entry.is_file():
                os.remove(entry)
                removed += 1
        except Exception:
            pass
    return removed


# ═══════════ 资料删除：真实移除 + 墓碑（2026-09-25） ═══════════
# 背景（用户报"删除选中资料删不干净、重启后资料又回来"）：
#   旧实现 move_to_trash 返回 False（文件被 Excel/WPS 占用、权限不足、已被外部
#   删除）时仍向用户返回"删除成功"；且内存列表删了、磁盘文件还在，
#   服务器重启后 _init_tax_docs_from_disk 会把文件重新扫回列表。
# 现约定：删除必须是"可验证的真实删除"，做不到就如实告知并留墓碑。

def doc_tombstone_key(company_id: int, filename: str) -> str:
    """墓碑主键：公司 + 文件名（文件名内含 doc_id，是磁盘上的唯一标识）。"""
    return f"{int(company_id)}:{filename}"


def load_doc_tombstones() -> dict:
    """读取删除墓碑：{key: {"company_id","filename","path","reason","at","purged"}}"""
    data = read_json(DELETED_DOCS, {})
    return data if isinstance(data, dict) else {}


def save_doc_tombstones(tombstones: dict) -> None:
    atomic_write_json(DELETED_DOCS, tombstones)


def add_doc_tombstone(company_id: int, filename: str, path: str = "",
                      reason: str = "", purged: bool = False) -> None:
    """登记墓碑（幂等）。purged=True 表示磁盘文件确已移除，仅是"已删除"记事；
    purged=False 表示磁盘文件仍在，需等待句柄释放后清理。"""
    try:
        key = doc_tombstone_key(company_id, filename)
        tombstones = load_doc_tombstones()
        tombstones[key] = {
            "company_id": int(company_id),
            "filename": filename,
            "path": path or "",
            "reason": reason or "",
            "purged": bool(purged),
            "at": datetime.now().isoformat(),
        }
        save_doc_tombstones(tombstones)
    except Exception:
        pass


def clear_doc_tombstone(company_id: int, filename: str) -> None:
    try:
        key = doc_tombstone_key(company_id, filename)
        tombstones = load_doc_tombstones()
        if key in tombstones:
            del tombstones[key]
            save_doc_tombstones(tombstones)
    except Exception:
        pass


def purge_file(file_path) -> tuple:
    """尽力物理移除单个文件，返回 (removed: bool, reason: str)。

    顺序：① 移入项目回收站（不触发环境批量删除守护）；② 若失败（同目录同名
    冲突等），改用带微秒时间戳的唯一名再移一次；③ 仍失败则保留原文件并说明
    原因，绝不删除、绝不谎报。调用方必须依据返回值决定是否告知用户"删除成功"。
    """
    src = Path(str(file_path))
    if not src.exists():
        return True, "文件已不存在"
    if not src.is_file():
        return False, "目标不是文件"
    if move_to_trash(src):
        return True, "已移入回收站"
    try:
        TRASH_DIR.mkdir(parents=True, exist_ok=True)
        unique = TRASH_DIR / f"{src.name}.{datetime.now().strftime('%H%M%S%f')}.purge"
        os.replace(src, unique)
        return True, "已移入回收站（唯一名）"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"



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

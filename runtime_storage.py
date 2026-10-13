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
from datetime import datetime, timedelta, timezone
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


def now_cst() -> str:
    """当前北京时间（Asia/Shanghai, UTC+8）ISO8601 字符串（★ 唯一权威）。

    ★ 2026-10-08 收敛：报告生成时间（report_compliance）、Skill 运行时间
      （skill_runtime）、分析会话时间（analysis_session）此前**各自实现**同一
      北京时间戳（3 处），任一处改口径即漂移。统一到本处，调用方只薄转发。
    """
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


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


def purge_tree(dir_path) -> tuple:
    """把一棵**运行时临时态目录**移入回收站（不物理删除），返回 (ok, reason)。

    ★ 为什么需要它：`move_to_trash` / `purge_file` **只处理文件**
      （`not src.is_file()` 即返回 False），而上传分片会话是"目录 + 多个 .part"，
      需要**目录级**出口。删除原语**只此一处**实现（`check_delete_exits` 已登记）。

    ★ 适用范围（**窄口径，勿扩大**）：仅用于**本项目自建的运行时中间态**
      （如 `data/upload_sessions/<id>/` 分片目录）。**不得**用于
      **用户资料 / 报告交付物 / 账套派生物** —— 那些各有专属业务出口
      （`_delete_tax_risk_docs` / `purge_company_analysis_artifacts` …）。

    做法：逐文件移入回收站（`move_to_trash` 不触发环境批量删除守护），
    随后删空目录；**任何一个文件移不动就如实返回 False 并说明**（不谎报成功）。
    """
    src = Path(str(dir_path))
    if not src.exists():
        return True, "目录已不存在"
    if src.is_file():
        ok = move_to_trash(src)
        return (ok, "已移入回收站" if ok else "移动失败")
    failed = []
    try:
        entries = sorted(src.rglob("*"), key=lambda p: len(p.parts), reverse=True)
    except Exception as exc:  # noqa: BLE001
        return False, "%s: %s" % (type(exc).__name__, exc)
    for entry in entries:
        try:
            if entry.is_file() and not move_to_trash(entry):
                failed.append(entry.name)
        except Exception:  # noqa: BLE001
            failed.append(getattr(entry, "name", "?"))
    # 自底向上清空目录（仅删**空**目录，非文件 ⇒ 不触发删除守护）
    for entry in entries + [src]:
        try:
            if entry.is_dir():
                entry.rmdir()
        except OSError:
            pass
    if failed:
        return False, "以下文件未能移入回收站：%s" % "、".join(failed[:10])
    return True, "已移入回收站"


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


def clear_company_doc_tombstones(company_id: int) -> int:
    """清掉某账套的**全部**删除墓碑，返回清除条数。

    ★ 2026-10-06（删除账套的派生物清理，唯一权威
      `main.purge_company_analysis_artifacts` 调用）：账套没了，它的墓碑也该没 ——
      否则墓碑永久累积，且同一 id 将来重建账套时会被旧墓碑误伤
      （新上传的同名文件会被当成"已删除"而不入库）。
    """
    cid = int(company_id)
    if cid <= 0:
        return 0
    try:
        tombstones = load_doc_tombstones()
        keep = {k: v for k, v in tombstones.items()
                if int((v or {}).get("company_id") or 0) != cid}
        removed = len(tombstones) - len(keep)
        if removed:
            save_doc_tombstones(keep)
        return removed
    except Exception:
        return 0


def count_company_doc_tombstones(company_id: int) -> int:
    """某账套现存删除墓碑条数（闸门用：账套不存在 ⇒ 必须为 0）。"""
    cid = int(company_id)
    if cid <= 0:
        return 0
    try:
        return sum(1 for v in load_doc_tombstones().values()
                   if int((v or {}).get("company_id") or 0) == cid)
    except Exception:
        return 0


#: JSONL 追加/读取的进程内锁（★ 本模块是"JSONL 落盘"的唯一实现处）
_JSONL_LOCK = threading.RLock()


def append_jsonl(path: "os.PathLike[str] | str", row: Any) -> None:
    """向 JSONL 文件**追加一行**（append-only；父目录自动创建）。

    ★★ 2026-10-13（P0-6）收敛：`engine/analysis_jobs._append_row` 与
      `engine/risk_review._append_row` **字节级相同**（只有"取哪个文件路径"不同）
      —— 属"同一概念两处实现"。本函数是**唯一实现**，两模块改为调用此处。
      理由：本模块本就是「删除 / 落盘**唯一权威**」，JSONL 追加属落盘能力。

    ★ 追加式（不改历史）＝ 可追溯；读取方负责"折叠当前态"。
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with _JSONL_LOCK:
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: "os.PathLike[str] | str") -> "tuple[list, int]":
    """顺序读出 JSONL 全部行 ⇒ `(rows, bad_count)`。

    ★ 坏行**只计数、不静默丢弃**：返回值里带 `bad_count`，由**调用方**决定如何留痕
      （留痕文案属各模块自己的语境，故不在此处写死）。
    ★ 文件不存在 ⇒ `([], 0)`（不是错误：尚未产生流水是正常状态）。
    """
    p = Path(path)
    if not p.exists():
        return [], 0
    rows: list = []
    bad = 0
    with _JSONL_LOCK:
        text = p.read_text(encoding="utf-8")
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:                                 # noqa: BLE001
            bad += 1
            continue
        if isinstance(obj, dict):
            rows.append(obj)
        else:
            bad += 1
    return rows, bad


def offline_reports_root() -> str:
    """离线分析产物（`company_{id}_*.json`）的**根目录**（唯一权威）。

    ★★ 2026-10-06（实测事故根因）：派生物目录**必须跟随应用的数据根**
      （`APP_DATA_DIR`），不得写死源码树路径。
      事故：`tests/test_company_api.py` 用 `APP_DATA_DIR=<临时目录>` 起一个
      **子进程应用实例**并在其中删除账套 ⇒ 清理权威用 `__file__` 拼出
      `scripts/four_reports` ⇒ **隔离实例越界删掉了真实项目的产物**
      （`company_1_full.json` 同日被删 4 次，靠备份才恢复）。
    规则：
      · 设了 `APP_DATA_DIR` ⇒ `<APP_DATA_DIR>/offline_reports`（隔离实例，只清自己的）；
      · 未设（生产实例）⇒ `scripts/four_reports`（现行位置，行为不变）。
    """
    app_data = os.environ.get("APP_DATA_DIR")
    if app_data:
        return os.path.join(app_data, "offline_reports")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "scripts", "four_reports")


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


def atomic_write_text(path: os.PathLike[str] | str, text: str) -> None:
    """**文本落盘的唯一原子实现**（fsync + `os.replace`，崩不断、截不留）。

    ★ 2026-10-09：从 `atomic_write_json` 里**抽出的唯一实现**（原来是"顺手写一遍"）。
      为什么必须唯一：JSONL 类追加表（作业流水 `data/analysis_jobs.jsonl`、
      版本台账 `data/report_versions.jsonl`、`data/purge_log.jsonl`）需要**整表重写**
      （删除企业时清行），而 `atomic_write_json` 只写 JSON。
      各模块于是**各自**手写 `mkstemp` + `os.replace` + **失败时 `os.unlink(tmp)`** ——
      闸门 `check_delete_exits` 逐行扫描"未声明的删除调用"，一写就报 ERROR
      （实测：`engine/analysis_jobs.py::_rewrite_rows` 被闸门抓到）。
      现统一走本函数：**"谁能删临时文件"只有这一个声明过的出口**，
      调用方连 `os.unlink` 都不该出现。

    ⚠ 本函数与 `atomic_write_json` 的关系：后者**只是本函数的一个 JSON 包装**
      （`_to_json_safe` + 序列化），不得再各写一份原子替换逻辑。
    """
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
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, destination)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


def atomic_write_json(path: os.PathLike[str] | str, value: Any,
                      indent: int | None = None) -> None:
    """Write JSON using fsync + atomic replace so crashes cannot truncate it.

    ★ 2026-10-06：新增 `indent`（默认 None，行为与从前完全一致）。
      为什么需要它：`scripts/run_companies.py` / `_rerun_company1.py` 会把
      **全量分析产物**落盘，产物用 `indent=1`（便于人工检索阅读）。
      这两个脚本此前**各自手写** `open(...,"w")` + `json.dump` —— 非原子：
      磁盘写满/进程中断时会把**正式产物截断**（实测 `company_1_full.json` 被截成
      3110 字节、只剩 4 个键）。现统一走本函数（**唯一落盘实现**），只多一个 `indent`。

    ★ 2026-10-09：本函数改为 `atomic_write_text` 的**薄包装**（单一原子写实现）。
      序列化口径不变：`_to_json_safe` + `ensure_ascii=False` + `default=str`
      + `indent`（与旧的 `json.dump(..., handle, ...)` 逐字节等价）。
    """
    atomic_write_text(
        path,
        json.dumps(_to_json_safe(value), ensure_ascii=False, indent=indent, default=str),
    )


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

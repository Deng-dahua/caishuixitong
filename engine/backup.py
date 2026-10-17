# -*- coding: utf-8 -*-
"""数据备份与恢复（S-10 / D-02，2026-10-17）。

为什么有这个模块
----------------
阶段 7 安全评估的唯一「不符合」项是 **系统没有数据备份功能**（取证到的 7 处
`backup` 全是假阳性：清理残留表、税审规则文本）。阶段 9 演练已经证明
「在线快照 + 恢复」在技术上完全可行（VACUUM INTO 0.04 s、恢复 0.005 s、
integrity ok），**缺的不是能力，是没有人/没有调度在做**。

设计要点
--------
① **在线一致快照**：SQLite 库用 `VACUUM INTO`（不需要停服、不会读到半截事务），
   **不做文件级 copy**（WAL 模式下 copy 主库文件会漏掉 `-wal` 里的未落盘数据）。
② **可验证**：每份备份都写 `manifest.json`（每个文件的 **sha256 + 字节数** +
   库的 `integrity_check` + 行数）。恢复前**必须**先校验 sha256 —— 备份坏了
   绝不能拿去覆盖生产库。
③ **目录跟随 `APP_DATA_DIR`**：备份目录是 `DATA_DIR/backups`（项目铁律：
   派生/台账目录必须跟随，禁硬编码 `data/`）。
④ **轮转走权威删除出口**：过期备份用 `runtime_storage.purge_file`（移入回收站，
   可恢复），**不用 `os.remove`**（铁律）。
⑤ **恢复只做文件级还原 + 校验**，并要求**服务已停**（运行中覆盖 SQLite 文件
   会得到损坏库）。恢复前自动做一份 `pre-restore` 快照当后悔药。

本模块不改变任何业务判定，只做「拷出来 / 放回去」。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime_storage import (ACCOUNTING_DB, DATA_DIR, SECURITY_DB,
                             atomic_write_json, now_cst, purge_file)

#: 备份根目录（跟随 APP_DATA_DIR）
BACKUP_DIR = DATA_DIR / "backups"

#: 默认保留份数（足够回溯两周；可用 APP_BACKUP_KEEP 覆盖）
KEEP = int(os.environ.get("APP_BACKUP_KEEP", "14"))

#: 默认备份间隔（小时）。`APP_BACKUP_INTERVAL_HOURS` 可覆盖（测试用 0 表示每次启动都备）。
INTERVAL_HOURS = float(os.environ.get("APP_BACKUP_INTERVAL_HOURS", "24"))

#: 需要随库一起备份的**状态文件**（相对 DATA_DIR）。缺失即跳过，不报错。
STATE_FILES = (
    "analysis_jobs.jsonl",
    "analysis_task_links.jsonl",
    "report_versions.jsonl",
    "purge_log.jsonl",
    "user_corrections.json",
    "content_feedback.json",
    "deleted_docs.json",
    "learning_agent_weights.json",
)

#: 需要做快照的数据库（顺序即恢复顺序，无依赖关系）
DATABASES = (ACCOUNTING_DB, SECURITY_DB)


def _assert_inside(path: Path) -> Path:
    """**硬护栏**：任何写操作的目标必须落在 `DATA_DIR` 之内。

    ★ 2026-10-17 事故的直接防线。当时 `restore_backup` 用模块级常量
      `SECURITY_DB.parent` 拼目标路径，而该常量在 import 时已固化为真实
      `data/`，导致**测试跑一次就把生产库覆盖了**（6.3 MB → 12 KB）。
      护栏的意义：即使将来有人再写错路径引用，也会**在写之前**抛错。
    """
    root = Path(DATA_DIR).resolve()
    target = Path(path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise RuntimeError(
            "拒绝写入：目标 %s 不在 DATA_DIR(%s) 之内 —— 这是防止"
            "「把备份恢复到别的环境」的硬护栏（2026-10-17 事故）" % (target, root)
        ) from None
    return target


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _integrity(db_path: Path) -> str:
    """SQLite 完整性检查（只读连接；失败返回错误说明，绝不谎报 ok）。"""
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db_path.as_posix(), uri=True, timeout=10)
        try:
            row = con.execute("PRAGMA integrity_check").fetchone()
            return str(row[0]) if row else "unknown"
        finally:
            con.close()
    except Exception as exc:                       # noqa: BLE001
        return "ERROR: %s" % exc


def _row_counts(db_path: Path) -> Dict[str, int]:
    """主要表的行数（恢复后用于核对"数据真的回来了"）。"""
    out: Dict[str, int] = {}
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db_path.as_posix(), uri=True, timeout=10)
        try:
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            for t in tables:
                try:
                    out[t] = int(con.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0])
                except sqlite3.Error:
                    continue
        finally:
            con.close()
    except Exception as exc:                       # noqa: BLE001
        out["_error"] = str(exc)                    # type: ignore[assignment]
    return out


def _snapshot_db(src: Path, dest: Path) -> None:
    """**在线一致快照**：`VACUUM INTO`（读事务快照，不阻塞业务、不受 WAL 影响）。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()                                # 覆盖本次自己的半成品，非用户数据
    con = sqlite3.connect(str(src), timeout=30)
    try:
        con.execute("VACUUM INTO ?", (str(dest),))
    finally:
        con.close()


def create_backup(kind: str = "manual", *, note: str = "") -> Dict[str, Any]:
    """创建一份备份，返回 manifest（含每个文件的 sha256）。

    kind: `daily` / `manual` / `pre-restore`。轮转**只对 daily/manual** 生效，
    `pre-restore` 一定保留（那是恢复失败的后悔药）。
    """
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    folder = BACKUP_DIR / ("%s_%s" % (stamp, kind))
    suffix = 1
    while folder.exists():                           # 同秒内多次备份
        suffix += 1
        folder = BACKUP_DIR / ("%s_%s_%d" % (stamp, kind, suffix))
    folder.mkdir(parents=True, exist_ok=True)

    files: List[Dict[str, Any]] = []
    counts: Dict[str, Any] = {}
    integrity: Dict[str, str] = {}

    # ① 数据库（VACUUM INTO 在线快照）
    for src in DATABASES:
        src = Path(src)
        if not src.exists():
            continue
        dest = folder / src.name
        _snapshot_db(src, dest)
        files.append({"name": src.name, "bytes": dest.stat().st_size,
                      "sha256": _sha256(dest), "kind": "db"})
        counts[src.name] = _row_counts(dest)
        integrity[src.name] = _integrity(dest)

    # ② 状态文件（普通复制；小文件）
    for name in STATE_FILES:
        src = DATA_DIR / name
        if not src.is_file():
            continue
        dest = folder / name
        shutil.copy2(src, dest)
        files.append({"name": name, "bytes": dest.stat().st_size,
                      "sha256": _sha256(dest), "kind": "state"})

    manifest = {
        "folder": folder.name,
        "kind": kind,
        "created_at": now_cst(),
        "created_ts": int(time.time()),
        "note": note,
        "files": files,
        "row_counts": counts,
        "integrity": integrity,
        "uploads": {
            "path": str(DATA_DIR / "uploads"),
            "note": ("业务原件（上传文件）**不在本备份内** —— 它们体量大且不可再生，"
                     "应走文件系统级备份；此处只登记路径与数量，供恢复后核对。"),
            "count": _count_files(DATA_DIR / "uploads"),
        },
        "app_version": _app_version(),
    }
    atomic_write_json(folder / "manifest.json", manifest, indent=1)
    _rotate()
    return manifest


def _count_files(root: Path) -> Optional[int]:
    if not root.is_dir():
        return None
    n = 0
    for _dirpath, _dirnames, filenames in os.walk(root):
        n += len(filenames)
    return n


def _app_version() -> str:
    """系统版本（唯一权威：仓库根的 `VERSION` 文件；无则如实标注 unknown）。"""
    p = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        return (p.read_text(encoding="utf-8").strip() or "unknown")
    except OSError:
        return "unknown"


def list_backups() -> List[Dict[str, Any]]:
    """按时间倒序列出备份（读 manifest；manifest 缺失也列出来并标 damaged）。"""
    if not BACKUP_DIR.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    for d in sorted(BACKUP_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        mf = d / "manifest.json"
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:                            # noqa: BLE001
            total = 0
            for f in d.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
            out.append({"folder": d.name, "kind": "unknown", "created_at": "",
                        "bytes": total, "damaged": True,
                        "note": "manifest 缺失或不可读（备份不完整）"})
            continue
        m["bytes"] = sum(int(f.get("bytes") or 0) for f in m.get("files") or [])
        m["damaged"] = False
        out.append(m)
    return out


def latest_backup() -> Optional[Dict[str, Any]]:
    items = list_backups()
    return items[0] if items else None


def backup_age_hours() -> Optional[float]:
    """最近一份备份距今多少小时（无备份返回 None）。"""
    m = latest_backup()
    if not m:
        return None
    ts = m.get("created_ts")
    if not ts:
        return None
    return max(0.0, (time.time() - float(ts)) / 3600.0)


def is_due() -> bool:
    """是否该做定时备份（无备份 ⇒ 该做；超过间隔 ⇒ 该做）。"""
    age = backup_age_hours()
    if age is None:
        return True
    return age >= INTERVAL_HOURS


def _rotate(keep: Optional[int] = None) -> List[str]:
    """轮转：保留最近 `keep` 份（默认 14），`pre-restore` 永不删除。

    ★ 删除走 `runtime_storage.purge_file`（移入回收站，可恢复），不用 os.remove。
    """
    keep = KEEP if keep is None else keep
    items = [m for m in list_backups()]
    protected = [m for m in items if m.get("kind") == "pre-restore"]
    others = [m for m in items if m.get("kind") != "pre-restore"]
    removed: List[str] = []
    for m in others[keep:]:
        folder = BACKUP_DIR / str(m.get("folder") or "")
        if not folder.is_dir():
            continue
        for f in sorted(folder.rglob("*"), reverse=True):
            if f.is_file():
                ok, _why = purge_file(f)
                if ok:
                    removed.append(f.name)
        for f in sorted(folder.rglob("*"), reverse=True):
            if f.is_dir():
                try:
                    f.rmdir()                        # 只删空目录（内容已进回收站）
                except OSError:
                    pass
        try:
            folder.rmdir()
        except OSError:
            pass
    return removed


def verify_backup(folder_name: str) -> Dict[str, Any]:
    """校验一份备份：逐个文件**重算 sha256** 与 manifest 比对 + 库完整性。

    ★ 恢复前必须先跑这个：**备份坏了绝不能拿去覆盖生产库**。
    """
    folder = BACKUP_DIR / folder_name
    if not folder.is_dir():
        return {"ok": False, "reason": "备份目录不存在：%s" % folder_name}
    mf = folder / "manifest.json"
    try:
        m = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as exc:                        # noqa: BLE001
        return {"ok": False, "reason": "manifest 不可读：%s" % exc}
    problems: List[str] = []
    checked: List[Dict[str, Any]] = []
    for item in m.get("files") or []:
        p = folder / str(item.get("name"))
        if not p.is_file():
            problems.append("文件缺失：%s" % item.get("name"))
            continue
        actual = _sha256(p)
        same = actual == item.get("sha256")
        checked.append({"name": item.get("name"), "sha256_ok": same,
                        "bytes": p.stat().st_size})
        if not same:
            problems.append("sha256 不符：%s（manifest=%s… 实际=%s…）"
                            % (item.get("name"), str(item.get("sha256"))[:12], actual[:12]))
    for db_name in (m.get("integrity") or {}):
        p = folder / db_name
        if p.is_file():
            got = _integrity(p)
            checked.append({"name": db_name, "integrity": got})
            if got != "ok":
                problems.append("完整性检查未通过：%s ⇒ %s" % (db_name, got))
    return {"ok": not problems, "folder": folder_name, "checked": checked,
            "problems": problems, "manifest": m}


def restore_backup(folder_name: str, *, force: bool = False) -> Dict[str, Any]:
    """从备份恢复（**服务必须已停**）。

    顺序（每一步都可回退）：
      ① 校验备份完整性（sha256 + integrity_check）—— 不通过直接拒绝；
      ② 服务在跑就拒绝（`force=True` 可跳过，但调用方必须自行确认风险）；
      ③ 先给**当前**库做一份 `pre-restore` 快照（后悔药）；
      ④ 覆盖库文件 + 状态文件；
      ⑤ 恢复后再次 integrity_check + 行数比对，**如实报告差异**。
    """
    import socket

    verify = verify_backup(folder_name)
    if not verify["ok"]:
        return {"ok": False, "stage": "verify", "problems": verify["problems"],
                "reason": "备份校验未通过 ⇒ 拒绝恢复（不用坏备份覆盖生产库）"}

    if not force and _port_busy(int(os.environ.get("APP_PORT", "8001"))):
        return {"ok": False, "stage": "precheck",
                "reason": "服务仍在运行（端口 %s 可连）⇒ 运行中覆盖 SQLite 文件会损坏库。"
                          "请先停服再恢复。" % os.environ.get("APP_PORT", "8001")}

    folder = BACKUP_DIR / folder_name
    safety = create_backup("pre-restore", note="恢复 %s 之前的自动快照" % folder_name)

    m = verify["manifest"]
    restored: List[str] = []
    cleared: List[str] = []
    for item in m.get("files") or []:
        name = str(item.get("name"))
        # ★★ 目标**一律**由 `DATA_DIR` 派生（2026-10-17 事故教训）：
        #    曾写成 `SECURITY_DB.parent / name` —— 那个常量在 import 时就固化成
        #    **真实 data/**，于是测试里 monkeypatch 了 DATA_DIR 也不生效，
        #    恢复动作**直接写进了生产库**（把 6.3 MB 的业务库覆盖成 12 KB 测试库）。
        #    现在只允许 DATA_DIR 下的路径，且有 `_assert_inside` 硬护栏。
        target = DATA_DIR / name
        _assert_inside(target)
        # 边车文件（`-wal`/`-shm`）必须先清掉，否则旧事务会被重放到刚恢复的库上。
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(target) + suffix)
            if sidecar.exists():
                ok, _why = purge_file(sidecar)
                if ok:
                    cleared.append(sidecar.name)
        shutil.copy2(folder / name, target)
        restored.append(name)

    after: Dict[str, Any] = {"integrity": {}, "row_counts": {}}
    diffs: List[str] = []
    for db_name, before in (m.get("row_counts") or {}).items():
        p = DATA_DIR / db_name
        if not p.is_file():
            continue
        got = _integrity(p)
        now_counts = _row_counts(p)
        after["integrity"][db_name] = got
        after["row_counts"][db_name] = now_counts
        if got != "ok":
            diffs.append("%s 恢复后完整性检查未通过：%s" % (db_name, got))
        for table, n in (before or {}).items():
            if table.startswith("_"):
                continue
            if now_counts.get(table) != n:
                diffs.append("%s.%s 行数 %s ≠ 备份时 %s" % (db_name, table, now_counts.get(table), n))

    return {
        "ok": not diffs,
        "stage": "restored",
        "restored_files": restored,
        "cleared_sidecars": cleared,
        "safety_backup": safety.get("folder"),
        "after": after,
        "diffs": diffs,
        "note": ("恢复后请**重启服务**；`uploads/` 原件不在备份内，需另按文件系统备份恢复。"
                 "若发现问题，用 safety_backup 那份 `pre-restore` 快照回退。"),
    }


def _port_busy(port: int, host: str = "127.0.0.1") -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def ensure_daily_backup(force: bool = False) -> Dict[str, Any]:
    """到点就做每日备份；返回是否执行 + 原因（供启动时调用与健康检查展示）。"""
    if not force and not is_due():
        return {"ran": False, "reason": "距上次备份 %.1f 小时 < %.0f 小时间隔"
                % (backup_age_hours() or 0, INTERVAL_HOURS),
                "latest": (latest_backup() or {}).get("folder")}
    try:
        m = create_backup("daily", note="定时备份")
        return {"ran": True, "folder": m["folder"], "files": len(m["files"])}
    except Exception as exc:                        # noqa: BLE001
        return {"ran": False, "error": "%s: %s" % (type(exc).__name__, exc)}


def summary() -> Dict[str, Any]:
    """备份状态摘要（供管理页与健康检查）。"""
    items = list_backups()
    latest = items[0] if items else None
    return {
        "dir": str(BACKUP_DIR),
        "count": len(items),
        "latest": latest,
        "age_hours": backup_age_hours(),
        "interval_hours": INTERVAL_HOURS,
        "keep": KEEP,
        "due": is_due(),
        "total_bytes": sum(int(m.get("bytes") or 0) for m in items),
        "note": ("备份为**在线一致快照**（VACUUM INTO）；`uploads/` 原件不在其中。"
                 "恢复需先停服，恢复前会自动生成一份 `pre-restore` 后悔药。"),
    }


__all__ = ["BACKUP_DIR", "create_backup", "list_backups", "latest_backup",
           "backup_age_hours", "is_due", "verify_backup", "restore_backup",
           "ensure_daily_backup", "summary"]

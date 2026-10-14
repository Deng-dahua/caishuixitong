# -*- coding: utf-8 -*-
"""服务版本可见化（**唯一权威**）：进程载入的代码 vs 磁盘当前代码。

★ 为什么需要它（2026-10-14 实测事故，两次同根因）
  前端静态文件是**每次请求从磁盘读**（`/` 路由体 = `_read_html("static/index.html")`）；
  而 Python 代码是**进程启动时的快照**（uvicorn 不带 `--reload`）。
  两者一叠加，就出现下面这类**看起来像 bug、实则只是没重启**的症状：
    · 侧边栏是新的，点进去 `{"detail":"Not Found"}`（旧后端没有那些页面路由）；
    · 侧边栏少若干项（旧 `/api/auth/me` 不返回 `permissions`）。
  此前只能靠人肉比对「进程启动时间 vs git 提交时间」——耗时且易误判（本人已错过一次）。

  本模块把结论变成**机器可判**：
    · `boot_snapshot()` —— 进程导入本模块那一刻的源码指纹（= 进程真正载入的版本）；
    · `staleness()`     —— boot 快照 vs **磁盘当前**快照 ⇒ 哪些文件改了/增了/删了；
    · `health_payload()`—— 供 `/healthz` 输出的稳定载荷（前端据此提示「请重启」）。

★ 监控范围只含 **Python 源码**（根目录 `*.py` + `engine/*.py`）：
  前端 / CSS / HTML **不在内** —— 它们本就是每次请求从磁盘读，更新**不需要**重启；
  把它们算进「落后」会制造误报（改个文案就报"请重启"）。
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent

# 磁盘快照缓存（`/healthz` 可能被监控高频调用，避免每次全量 stat + 读盘）
_DISK_TTL_SECONDS = 2.0
_DISK_CACHE: Dict[str, Any] = {"at": 0.0, "val": None}

# 内容哈希缓存：rel -> (mtime_ns, size, digest)。只有 mtime/size 变了才重算哈希。
_HASH_CACHE: Dict[str, Tuple[int, int, str]] = {}


def _now_cst() -> str:
    """北京时间戳（唯一权威 `runtime_storage.now_cst`；不可用时如实回落并标注）。"""
    try:
        from runtime_storage import now_cst                            # noqa: PLC0415
        return str(now_cst())
    except Exception:                                                  # noqa: BLE001
        import datetime as _dt                                          # noqa: PLC0415
        return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def monitor_files() -> List[Path]:
    """被监控的 Python 源文件（进程载入的部分）。**不含** 前端资产。"""
    files: List[Path] = []
    try:
        files.extend(sorted(p for p in ROOT.glob("*.py") if p.is_file()))
        files.extend(sorted(p for p in (ROOT / "engine").glob("*.py") if p.is_file()))
    except OSError:
        pass
    return files


def _digest(path: Path) -> Optional[str]:
    """文件内容摘要（带 (mtime,size) 缓存）。读不到时返回 None（不静默当空串）。"""
    try:
        st = path.stat()
    except OSError:
        return None
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    key = (int(st.st_mtime_ns), int(st.st_size))
    cached = _HASH_CACHE.get(rel)
    if cached and (cached[0], cached[1]) == key:
        return cached[2]
    try:
        h = hashlib.sha1()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        dg = h.hexdigest()[:12]
    except OSError:
        return None
    _HASH_CACHE[rel] = (key[0], key[1], dg)
    return dg


def snapshot() -> Dict[str, Any]:
    """当前磁盘上的源码快照：{files: {rel: digest}, stamp, count, newest_*}。"""
    files: Dict[str, str] = {}
    newest_mtime = 0.0
    newest_file = ""
    for p in monitor_files():
        dg = _digest(p)
        if dg is None:
            continue
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        files[rel] = dg
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue
        if mt > newest_mtime:
            newest_mtime, newest_file = mt, rel
    stamp = hashlib.sha1(repr(sorted(files.items())).encode("utf-8")).hexdigest()[:12]
    return {"files": files, "stamp": stamp, "count": len(files),
            "newest_mtime": newest_mtime, "newest_file": newest_file}


# 进程启动快照：**导入本模块即固定**，之后不再变（= 进程真正载入的代码版本）
_BOOT: Dict[str, Any] = snapshot()
_BOOT_AT: str = _now_cst()
_BOOT_PID: int = os.getpid()


def boot_snapshot() -> Dict[str, Any]:
    return {"stamp": _BOOT["stamp"], "count": _BOOT["count"], "booted_at": _BOOT_AT,
            "pid": _BOOT_PID, "newest_file": _BOOT["newest_file"]}


def _disk_snapshot() -> Dict[str, Any]:
    now = time.time()
    if _DISK_CACHE["val"] is not None and (now - float(_DISK_CACHE["at"])) < _DISK_TTL_SECONDS:
        return _DISK_CACHE["val"]
    val = snapshot()
    _DISK_CACHE["at"] = now
    _DISK_CACHE["val"] = val
    return val


def staleness(*, refresh: bool = False) -> Dict[str, Any]:
    """boot 快照 vs 磁盘当前快照 ⇒ 进程载入的代码是否已被磁盘更新。

    返回：`{stale, changed_files:[{file, change}], changed_count, boot_stamp, disk_stamp, booted_at, monitored_files}`
    `refresh=True` 时绕过磁盘快照缓存（测试/自检用）。
    """
    if refresh:
        _DISK_CACHE["val"] = None
    disk = _disk_snapshot()
    boot_files: Dict[str, str] = _BOOT["files"]
    changed: List[Dict[str, str]] = []
    for rel, dg in sorted(disk["files"].items()):
        if rel not in boot_files:
            changed.append({"file": rel, "change": "新增"})
        elif boot_files[rel] != dg:
            changed.append({"file": rel, "change": "已修改"})
    for rel in sorted(boot_files):
        if rel not in disk["files"]:
            changed.append({"file": rel, "change": "已删除"})
    return {"stale": bool(changed), "changed_files": changed[:20], "changed_count": len(changed),
            "boot_stamp": _BOOT["stamp"], "disk_stamp": disk["stamp"],
            "booted_at": _BOOT_AT, "monitored_files": _BOOT["count"]}


def stale_hint(info: Optional[Dict[str, Any]] = None) -> str:
    """给人看的一句话（前端/错误页复用；不 stale 时空串）。"""
    info = info or staleness()
    if not info.get("stale"):
        return ""
    names = "、".join(x["file"] for x in (info.get("changed_files") or [])[:3])
    more = " 等" if (info.get("changed_count") or 0) > 3 else ""
    return ("服务运行的是**旧代码**（启动于 %s，PID %s）：磁盘上已有 %d 个后端文件更新（%s%s）。"
            "请**重启**服务（关闭当前窗口后重新运行 start8001.bat）再刷新本页。"
            % (_BOOT_AT, _BOOT_PID, info.get("changed_count") or 0, names, more))


def health_payload() -> Dict[str, Any]:
    """`/healthz` 载荷（稳定键；前端据此提示"请重启"）。"""
    info = staleness()
    return {"code": boot_snapshot(),
            "stale": {"stale": info["stale"], "changed_count": info["changed_count"],
                      "changed_files": info["changed_files"],
                      "disk_stamp": info["disk_stamp"], "monitored_files": info["monitored_files"]}}


__all__ = ["ROOT", "monitor_files", "snapshot", "boot_snapshot", "staleness",
           "stale_hint", "health_payload"]

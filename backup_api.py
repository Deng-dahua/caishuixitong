# -*- coding: utf-8 -*-
"""系统备份/恢复 HTTP 接口（S-10 / D-02，2026-10-17）。

为什么需要这组接口
------------------
阶段 7 的唯一「不符合」项是**没有数据备份**；阶段 9 的演练证明技术上完全可行。
本模块把能力**暴露到界面上**（此前能力存在、用户摸不到，正是评估里反复出现的模式）：
  · 看：现在有几份备份、最近一份多久前、共占多少空间；
  · 做：随时"立即备份一份"；
  · 验：对任意一份**重算 sha256 + integrity_check**（备份坏了必须能发现）；
  · 恢复：给出**可执行的命令**；服务在跑时拒绝在运行中覆盖数据库文件。

★ 权限：**仅管理员**（`session.is_admin`，服务端唯一权威）。
  不新增权限点（`config/rbac.json` 未加 `system.manage`）—— 与既有
  `_LEGACY_ADMIN_ONLY` 口径一致，前端用 `data-perm-admin`。
★ 本模块**只调用 engine.backup**，不自己实现快照/校验逻辑（单一权威）。
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from engine import backup as BK

router = APIRouter(prefix="/api/v1/system", tags=["系统备份（S-10）"])
page_router = APIRouter(tags=["系统备份（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _admin(request: Request):
    """只读中间件写入的 session；非管理员一律 403（不泄露是否存在该资源）。"""
    session = getattr(request.state, "auth", None)
    if session is None:
        raise HTTPException(401, "未登录")
    if not session.is_admin:
        raise HTTPException(403, "仅管理员可管理备份")
    return session


@router.get("/backups", summary="备份清单与状态")
def list_backups(request: Request):
    _admin(request)
    s = BK.summary()
    return {
        "summary": s,
        "items": BK.list_backups(),
        "restore_howto": _restore_howto(),
    }


@router.post("/backups", summary="立即备份（在线一致快照）", status_code=201)
def create_backup(request: Request):
    _admin(request)
    try:
        m = BK.create_backup("manual", note="管理员在界面手动触发")
    except Exception as exc:                       # noqa: BLE001
        raise HTTPException(500, "备份失败：%s" % exc) from exc
    return {"ok": True, "folder": m["folder"],
            "files": [{"name": f["name"], "bytes": f["bytes"]} for f in m["files"]],
            "integrity": m["integrity"], "bytes": sum(f["bytes"] for f in m["files"])}


@router.post("/backups/{folder}/verify", summary="校验备份（重算 sha256 + 完整性）")
def verify_backup(folder: str, request: Request):
    _admin(request)
    res = BK.verify_backup(folder)
    if "reason" in res and not res.get("manifest"):
        raise HTTPException(404, res["reason"])
    return res


@router.post("/backups/{folder}/restore", summary="从备份恢复（需先停服）")
def restore_backup(folder: str, request: Request):
    """★ 运行中恢复会损坏库 ⇒ **默认拒绝**，返回可执行命令与注意事项。

    真正的文件替换由 `scripts/backup_cli.py restore <folder>` 在停服状态下完成
    （它自带：校验 → 生成 pre-restore 后悔药 → 覆盖 → 恢复后完整性检查）。
    """
    _admin(request)
    if BK.list_backups() and not any(m.get("folder") == folder for m in BK.list_backups()):
        raise HTTPException(404, "备份不存在：%s" % folder)
    v = BK.verify_backup(folder)
    if not v.get("ok"):
        raise HTTPException(409, "该备份校验未通过，拒绝用于恢复：%s" % v.get("problems"))
    return {
        "ok": False,
        "need_restart": True,
        "reason": ("**运行中不能恢复**：覆盖正在使用的 SQLite 文件会损坏库。"
                   "请先停止服务，再执行下面的命令。"),
        "command": _restore_cmd(folder),
        "howto": _restore_howto(),
        "verify": {"ok": v["ok"], "problems": v["problems"]},
    }


def _restore_cmd(folder: str) -> str:
    py = os.path.join(".venv", "Scripts", "python.exe") if os.name == "nt" else ".venv/bin/python"
    return "%s scripts/backup_cli.py restore %s --yes" % (py, folder)


def _restore_howto() -> list:
    return [
        "① 停服：关闭正在运行的服务窗口（或结束 python -m uvicorn 进程）",
        "② 执行：%s" % _restore_cmd("<备份目录名>"),
        "③ 重启：双击 start8001.bat（守护器会在崩溃时自动拉起）",
        "④ 核对：界面上「备份与恢复」页会显示恢复后行数与备份时是否一致",
        "说明：恢复前会自动生成一份 pre-restore 快照（后悔药）；"
        "uploads/ 原件不在备份内，需按文件系统备份单独恢复。",
    ]


@page_router.get("/backup", response_class=HTMLResponse, include_in_schema=False)
def backup_page():
    path = os.path.join(_ROOT, "static", "backup.html")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"


# --------------------------------------------------------------------------
# O-02（2026-10-17）：运行指标
# --------------------------------------------------------------------------
@router.get("/metrics", summary="运行指标（QPS/延迟分位/错误率/慢请求）")
def get_metrics(request: Request):
    """指标快照。**仅管理员**（内部信息，不做匿名暴露）。

    若将来要用采集器抓取，请在本机放到反向代理后面，不要直接对公网开放。
    """
    _admin(request)
    from engine import metrics as M      # noqa: PLC0415
    from engine import backup as BK2     # noqa: PLC0415

    snap = M.snapshot()
    try:
        snap["backup"] = {"count": BK2.summary()["count"],
                          "age_hours": BK2.summary()["age_hours"],
                          "due": BK2.summary()["due"]}
    except Exception:                    # noqa: BLE001
        pass
    return snap


@router.get("/metrics.txt", summary="运行指标（Prometheus 文本格式）")
def get_metrics_text(request: Request):
    _admin(request)
    from fastapi.responses import PlainTextResponse   # noqa: PLC0415
    from engine import metrics as M                   # noqa: PLC0415

    return PlainTextResponse(M.prometheus_text(), media_type="text/plain; version=0.0.4")

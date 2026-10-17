# -*- coding: utf-8 -*-
"""回收站接口（H-04，2026-10-17）—— **薄转发**，逻辑在 `engine/trash_service.py`。

评估结论：「7 个模块无撤销/回收站入口 —— 后端其实已有 `move_to_trash`（可恢复），
但前端没有『回收站』页面 ⇒ **能力存在、用户摸不到**」。

  GET  /api/v1/system/trash           清单
  POST /api/v1/system/trash/restore   还原一个（回 uploads/<账套>/，推不出则 restored/）
  POST /api/v1/system/trash/empty     分批清空（必须 confirm，单批 ≤20）
  GET  /recycle                       页面

★ 全部**仅管理员**：回收站里是别人删掉的东西，还原/清空都属于管理动作。
★ 本模块**不做删除**，也不自己拼路径 —— 全部转发服务层（单一权威 + 有闸门守护）。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from engine import trash_service as SVC

router = APIRouter(prefix="/api/v1/system", tags=["回收站（H-04）"])
page_router = APIRouter(tags=["回收站（页面）"])

_ROOT = Path(__file__).resolve().parent


def _admin(request: Request):
    s = getattr(request.state, "auth", None)
    if s is None:
        raise HTTPException(401, "未登录")
    if not s.is_admin:
        raise HTTPException(403, "仅管理员可管理回收站")
    return s


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except SVC.TrashError as exc:
        raise HTTPException(exc.status, exc.message) from exc


@router.get("/trash", summary="回收站清单")
def list_trash(request: Request):
    _admin(request)
    return {"ok": True, **_call(SVC.listing)}


class RestoreIn(BaseModel):
    name: str


@router.post("/trash/restore", summary="还原一个文件")
def restore_one(payload: RestoreIn, request: Request):
    _admin(request)
    return {"ok": True, **_call(SVC.restore_one, payload.name)}


class EmptyIn(BaseModel):
    confirm: bool = False
    max_files: int = SVC.MAX_BATCH


@router.post("/trash/empty", summary="清空回收站（分批次，必须确认）")
def empty_trash(payload: EmptyIn, request: Request):
    _admin(request)
    return {"ok": True, **_call(SVC.empty_trash, payload.confirm, payload.max_files)}


@page_router.get("/recycle", response_class=HTMLResponse, include_in_schema=False)
def recycle_page():
    path = _ROOT / "static" / "recycle.html"
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"

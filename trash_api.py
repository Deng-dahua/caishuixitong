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

from engine.api_common import (admin_of, call_boundary, request_perm,
                             require_perm, session_of)

# ★ R-02（2026-10-17）：以下名字是**别名**，逻辑唯一在 engine/api_common。
#   禁止在本文件重新定义（闸门 `check_api_boundary_single_source` 会报错）。
_admin = admin_of

router = APIRouter(prefix="/api/v1/system", tags=["回收站（H-04）"])
page_router = APIRouter(tags=["回收站（页面）"])

_ROOT = Path(__file__).resolve().parent


def _call(fn, *args, **kwargs):
    """业务异常 → HTTP 的**唯一转换点**在 `engine/api_common.call_boundary`；
    本函数只声明「本域该捕获哪一类业务异常」（SVC.TrashError）。"""
    return call_boundary(fn, *args, exc_types=(SVC.TrashError,), **kwargs)


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

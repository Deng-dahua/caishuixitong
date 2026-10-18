# -*- coding: utf-8 -*-
"""知情同意接口与页面（E-01 / E-04）。

  GET  /api/v1/system/consent         条款全文 + 当前用户是否已确认
  POST /api/v1/system/consent/accept  记录确认（留 IP/UA，可审计）
  GET  /consent                       条款页

★ 所有登录用户都可访问（不是管理员专属）：告知的对象就是每个使用数据的人。
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from engine import consent as CS

from engine.api_common import (admin_of, call_boundary, request_perm,
                             require_perm, session_of)

# ★ R-02（2026-10-17）：以下名字是**别名**，逻辑唯一在 engine/api_common。
#   禁止在本文件重新定义（闸门 `check_api_boundary_single_source` 会报错）。
_session = session_of

router = APIRouter(prefix="/api/v1/system", tags=["知情同意（E-01）"])
page_router = APIRouter(tags=["知情同意（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))


@router.get("/consent", summary="条款全文与当前用户确认状态")
def get_consent(request: Request):
    s = _session(request)
    return {"ok": True, **CS.payload(), **CS.status(s.username)}


@router.post("/consent/accept", summary="确认已知悉本告知")
def accept_consent(request: Request):
    s = _session(request)
    ip = getattr(getattr(request, "client", None), "host", "") or ""
    ua = (request.headers.get("user-agent") or "")
    try:
        res = CS.record(s.username, client_ip=ip, user_agent=ua)
    except Exception as exc:                        # noqa: BLE001
        raise HTTPException(500, "记录确认失败：%s" % exc) from exc
    return {"ok": True, **res, "version": CS.CONSENT_VERSION}


@page_router.get("/consent", response_class=HTMLResponse, include_in_schema=False)
def consent_page():
    path = os.path.join(_ROOT, "static", "consent.html")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"

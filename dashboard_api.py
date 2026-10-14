# -*- coding: utf-8 -*-
"""数据大屏 HTTP 接口（P2-5）。

路径前缀 `/api/v1`（**新增**端点专用；既有各模块接口一字未改）。

| 端点 | 说明 |
|---|---|
| `GET /api/v1/dashboard/meta` | 字典（数据来源与读取通道 / 扫描上限 / 口径说明） |
| `GET /api/v1/dashboard/overview` | 全局概览（项目/资料/任务/风险/按项目明细） |
| `GET /api/v1/dashboard/activity?days=` | 最近 N 天留痕按日计数 |
| `GET /dashboard`（页面） | 数据大屏 |

★ 路由顺序铁律：字面量段（`meta`/`overview`/`activity`）与 `{...}` 参数段不共存于同层，
  但顺序仍按防御性写死；闸门 `check_dashboard_wiring` 断言"无同层参数段"与接线完整。
★ 权限：`dashboard.view`（唯一权威 `engine.rbac.rbac_allows`）。
★ 口径：所有明细经既有 Service 层读取（`engine/dashboard.py` 零 SQL）⇒ 租户隔离同源。
"""
from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from engine import dashboard as DASH

router = APIRouter(prefix="/api/v1", tags=["数据大屏与统计（P2-5）"])
page_router = APIRouter(tags=["数据大屏（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _request_perm(request: Request, perm: str):
    auth = getattr(request.state, "auth", None)
    if auth is None:
        raise HTTPException(status_code=401, detail="未登录")
    from engine.rbac import rbac_allows                      # noqa: PLC0415
    if not rbac_allows(auth, perm):
        raise HTTPException(status_code=403, detail="缺少权限：%s" % perm)
    return auth


@router.get("/dashboard/meta", summary="数据大屏字典（来源 / 读取通道 / 扫描上限）")
def dashboard_meta(request: Request) -> Dict[str, Any]:
    _request_perm(request, "dashboard.view")
    return DASH.metadata()


@router.get("/dashboard/overview", summary="全局概览（项目/资料/任务/风险/按项目明细）")
def dashboard_overview(request: Request) -> Dict[str, Any]:
    return DASH.overview(_request_perm(request, "dashboard.view"))


@router.get("/dashboard/activity", summary="最近 N 天操作留痕按日计数")
def dashboard_activity(request: Request, days: int = Query(14)) -> Dict[str, Any]:
    session = _request_perm(request, "dashboard.view")
    return DASH.activity(session, days=max(1, min(int(days or 14), 90)))


@page_router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page():
    """数据大屏（静态 HTML，无服务端模板）。"""
    path = os.path.join(_ROOT, "static", "dashboard.html")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"


__all__ = ["router", "page_router"]

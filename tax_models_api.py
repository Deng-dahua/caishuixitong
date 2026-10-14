# -*- coding: utf-8 -*-
"""多税种深度模型 HTTP 接口（P2-4）。

路径前缀 `/api/v1`（**新增**端点专用；既有测算链路一字未改）。

| 端点 | 说明 |
|---|---|
| `GET /api/v1/tax-models/meta` | 字典（表位置 / 字段说明 / 税种与税率权威来源） |
| `GET /api/v1/tax-models/coverage` | 税种覆盖（本系统分析税种中有多少已登记深度模型） |
| `GET /api/v1/tax-models/cross-tax` | 跨税种模型 |
| `GET /api/v1/tax-models` | 税种 → 深度模型清单（含税率口径与量化能力） |
| `GET /api/v1/tax-models/{tax}` | 单税种详情 |
| `GET /tax-models`（页面） | 多税种深度模型浏览页 |

★ 路由顺序铁律：字面量段（`meta`/`coverage`/`cross-tax`）注册在参数化段 `{tax}` **之前**。
★ 权限：`risk.view`（唯一权威 `engine.rbac.rbac_allows`）。
"""
from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from engine import tax_deep_models as MODELS

router = APIRouter(prefix="/api/v1", tags=["多税种深度模型（P2-4）"])
page_router = APIRouter(tags=["多税种深度模型（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _request_perm(request: Request, perm: str):
    auth = getattr(request.state, "auth", None)
    if auth is None:
        raise HTTPException(status_code=401, detail="未登录")
    from engine.rbac import rbac_allows                      # noqa: PLC0415
    if not rbac_allows(auth, perm):
        raise HTTPException(status_code=403, detail="缺少权限：%s" % perm)
    return auth


# ── 字面量段（必须在前）────────────────────────────────────────────────────
@router.get("/tax-models/meta", summary="多税种深度模型字典")
def tax_models_meta(request: Request) -> Dict[str, Any]:
    _request_perm(request, "risk.view")
    return MODELS.metadata()


@router.get("/tax-models/coverage", summary="税种覆盖（本系统分析税种 → 已登记深度模型）")
def tax_models_coverage(request: Request) -> Dict[str, Any]:
    _request_perm(request, "risk.view")
    return MODELS.coverage()


@router.get("/tax-models/cross-tax", summary="跨税种模型")
def tax_models_cross(request: Request) -> Dict[str, Any]:
    _request_perm(request, "risk.view")
    return MODELS.cross_tax()


@router.get("/tax-models", summary="税种 → 深度模型清单")
def tax_models_list(request: Request) -> Dict[str, Any]:
    _request_perm(request, "risk.view")
    return MODELS.taxes()


# ── 参数化段（必须在后）────────────────────────────────────────────────────
@router.get("/tax-models/{tax}", summary="单税种详情（模型清单 + 税率口径）")
def tax_models_detail(tax: str, request: Request):
    _request_perm(request, "risk.view")
    item = MODELS.tax_detail(tax)
    if item is None:
        raise HTTPException(status_code=404, detail="本表未登记该税种：%s" % tax)
    return item


@page_router.get("/tax-models", response_class=HTMLResponse, include_in_schema=False)
def tax_models_page():
    """多税种深度模型浏览页（静态 HTML，无服务端模板）。"""
    path = os.path.join(_ROOT, "static", "tax_models.html")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"


__all__ = ["router", "page_router"]

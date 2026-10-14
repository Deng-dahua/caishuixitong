# -*- coding: utf-8 -*-
"""行业指标库 HTTP 接口（P2-2）。

路径前缀 `/api/v1`（**新增**端点专用；既有行业对标链路一字未改）。

| 端点 | 说明 |
|---|---|
| `GET /api/v1/industry-indicators/meta` | 字典（数据来源 / 口径警示 / 指标键 / 解析优先级） |
| `GET /api/v1/industry-indicators/stats` | 统计（行业数/指标键/来源分布/未覆盖键） |
| `GET /api/v1/industry-indicators/generic` | 未匹配到行业时的**宽松兜底区间**（单列，口径不混） |
| `GET /api/v1/industry-indicators` | 行业清单（每个行业的基准来源与指标区间） |
| `GET /api/v1/industry-indicators/{industry}` | 单行业详情（登记项原文 + 指标区间） |
| `GET /industry-indicators`（页面） | 行业指标库浏览页 |

★ 路由顺序铁律：字面量段（`meta`/`stats`/`generic`）必须注册在参数化段（`{industry}`）**之前**。
★ 权限：`industry.view`（唯一权威 `engine.rbac.rbac_allows`）。
★ 口径警示单一权威：`BENCHMARK_CAUTION` 由读层薄转发自 `industry_benchmark`，本模块**不再写第二份**。
"""
from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from engine import industry_indicators as IND

router = APIRouter(prefix="/api/v1", tags=["行业指标库（P2-2）"])
page_router = APIRouter(tags=["行业指标库（页面）"])

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
@router.get("/industry-indicators/meta", summary="行业指标库字典（来源 / 口径警示 / 指标键）")
def industry_meta(request: Request) -> Dict[str, Any]:
    _request_perm(request, "industry.view")
    return IND.metadata()


@router.get("/industry-indicators/stats", summary="行业指标库统计（行业数/指标键/来源分布）")
def industry_stats(request: Request) -> Dict[str, Any]:
    _request_perm(request, "industry.view")
    return IND.stats()


@router.get("/industry-indicators/generic", summary="未匹配到行业时的宽松兜底区间")
def industry_generic(request: Request) -> Dict[str, Any]:
    _request_perm(request, "industry.view")
    return IND.generic()


@router.get("/industry-indicators", summary="行业清单（基准来源 + 指标区间）")
def industry_list(request: Request, q: str = Query(None)) -> Dict[str, Any]:
    _request_perm(request, "industry.view")
    return IND.industry_rows(q=q)


# ── 参数化段（必须在后）────────────────────────────────────────────────────
@router.get("/industry-indicators/{industry}", summary="单行业详情（登记项原文 + 指标区间）")
def industry_detail(industry: str, request: Request):
    _request_perm(request, "industry.view")
    item = IND.industry_detail(industry)
    if item is None:
        raise HTTPException(status_code=404, detail="未登记的行业：%s" % industry)
    return item


@page_router.get("/industry-indicators", response_class=HTMLResponse, include_in_schema=False)
def industry_indicators_page():
    """行业指标库浏览页（静态 HTML，无服务端模板）。"""
    path = os.path.join(_ROOT, "static", "industry_indicators.html")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"


__all__ = ["router", "page_router"]

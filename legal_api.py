# -*- coding: utf-8 -*-
"""法规库 HTTP 接口（P2-1）。

路径前缀 `/api/v1`（**新增**端点专用；既有法规引用链路一字未改）。

| 端点 | 说明 |
|---|---|
| `GET /api/v1/legal-library/meta` | 字典（数据来源文件 / 版本状态枚举 / 覆盖口径） |
| `GET /api/v1/legal-library/stats` | 统计（条数/法数/来源分布/版本状态分布/覆盖率） |
| `GET /api/v1/legal-library/laws` | 法清单（条数 + 版本状态） |
| `GET /api/v1/legal-library` | 正文条目检索（法名/条款号/正文关键词 + 分页） |
| `GET /api/v1/legal-library/{law}` | 单部法详情（全部条目 + 版本登记 + 版本括注） |
| `GET /legal-library`（页面） | 法规库浏览/检索页 |

★ 路由顺序铁律：字面量段（`meta`/`stats`/`laws`）必须注册在参数化段（`{law}`）**之前**，
  否则会被路径参数吃掉 ⇒ 静默 404。本模块的注册顺序即以此为准（闸门 `check_legal_library_wiring` 断言）。
★ 权限：`legal.view`（唯一权威 `engine.rbac.rbac_allows`）。
★ 法规库**不硬编码条文**：全部条文来自数据文件，本模块只做透出（见 `engine.legal_library`）。
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from engine import legal_library as LIB

router = APIRouter(prefix="/api/v1", tags=["法规库（P2-1）"])
page_router = APIRouter(tags=["法规库（页面）"])

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
@router.get("/legal-library/meta", summary="法规库字典（来源文件 / 状态枚举 / 覆盖口径）")
def legal_library_meta(request: Request) -> Dict[str, Any]:
    _request_perm(request, "legal.view")
    return LIB.metadata()


@router.get("/legal-library/stats", summary="法规库统计（条数/法数/来源/版本状态/覆盖率）")
def legal_library_stats(request: Request) -> Dict[str, Any]:
    _request_perm(request, "legal.view")
    return LIB.stats()


@router.get("/legal-library/laws", summary="法清单（条数 + 版本状态）")
def legal_library_laws(request: Request, q: Optional[str] = None) -> Dict[str, Any]:
    _request_perm(request, "legal.view")
    return LIB.laws(q=q)


@router.get("/legal-library", summary="正文条目检索（关键词 + 分页）")
def legal_library_entries(request: Request,
                          q: Optional[str] = None,
                          law: Optional[str] = None,
                          only_current: bool = Query(False),
                          page: int = Query(1),
                          page_size: int = Query(50)) -> Dict[str, Any]:
    _request_perm(request, "legal.view")
    return LIB.article_entries(q=q, law=law, only_current=bool(only_current),
                       limit=max(1, min(int(page_size or 50), 200)),
                       offset=max(1, int(page or 1)))


# ── 参数化段（必须在后）────────────────────────────────────────────────────
@router.get("/legal-library/{law}", summary="单部法详情（条目 + 版本登记 + 版本括注）")
def legal_library_law(law: str, request: Request):
    _request_perm(request, "legal.view")
    item = LIB.law_detail(law)
    if item is None:
        raise HTTPException(status_code=404, detail="法规库中无此法：%s" % law)
    return item


@page_router.get("/legal-library", response_class=HTMLResponse, include_in_schema=False)
def legal_library_page():
    """法规库浏览页（静态 HTML，无服务端模板）。"""
    path = os.path.join(_ROOT, "static", "legal_library.html")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"


__all__ = ["router", "page_router"]

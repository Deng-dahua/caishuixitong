# -*- coding: utf-8 -*-
"""AI 辅助分析 HTTP 接口（P2-3）。

路径前缀 `/api/v1`（**新增**端点专用；既有分析链路一字未改）。

| 端点 | 说明 |
|---|---|
| `GET  /api/v1/ai-assist/meta` | 字典（可用性 / 能力清单 / 免责声明 / 禁用词说明） |
| `POST /api/v1/ai-assist/{code}` | 生成辅助内容（**只做辅助，不替代规则**） |
| `GET  /ai-assist`（页面） | AI 辅助工作台 |

★ 路由顺序铁律：字面量段 `meta` 必须注册在参数化段 `{code}` **之前**
  （方法亦不同：GET vs POST，但顺序仍按防御性写死；闸门 `check_ai_assist_wiring` 断言）。
★ 权限：`risk.view`（唯一权威 `engine.rbac.rbac_allows`）——AI 辅助属"看风险"的场景。
★ **约束落地**：响应体原样透出 `role/advisory_only/replaces_rules/disclaimer` 四字段，
  接口层**不得**裁剪（裁剪即等于让前端有机会把它当结论展示）。
"""
from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse

from engine import ai_assist as AI

from engine.api_common import (admin_of, call_boundary, request_perm,
                             require_perm, session_of)

# ★ R-02（2026-10-17）：以下名字是**别名**，逻辑唯一在 engine/api_common。
#   禁止在本文件重新定义（闸门 `check_api_boundary_single_source` 会报错）。
_request_perm = request_perm

router = APIRouter(prefix="/api/v1", tags=["AI 辅助分析（P2-3）"])
page_router = APIRouter(tags=["AI 辅助分析（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))


# ── 字面量段（必须在前）────────────────────────────────────────────────────
@router.get("/ai-assist/meta", summary="AI 辅助字典（可用性 / 能力清单 / 免责声明）")
def ai_assist_meta(request: Request) -> Dict[str, Any]:
    _request_perm(request, "risk.view")
    caps = AI.capabilities()
    return {
        "status": AI.status(),
        "capabilities": caps,
        "advisory_only": True,
        "replaces_rules": False,
        "disclaimer": AI.DISCLAIMER,
    }


# ── 参数化段（必须在后）────────────────────────────────────────────────────
@router.post("/ai-assist/{code}", summary="生成 AI 辅助内容（不替代规则判定）")
def ai_assist_run(code: str, request: Request,
                  payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    """请求体：`{"finding": {...}}` 或 `{"findings": [{...}, ...]}`（按能力而异）。

    ★ 响应**必须**含 `advisory_only=True` / `replaces_rules=False` / `disclaimer`，
      调用方须一并展示。
    """
    _request_perm(request, "risk.view")
    try:
        return AI.assist(code, payload if isinstance(payload, dict) else {})
    except AI.AiAssistError as exc:
        raise HTTPException(status_code=int(exc.status), detail=str(exc.message)) from exc


@page_router.get("/ai-assist", response_class=HTMLResponse, include_in_schema=False)
def ai_assist_page():
    """AI 辅助工作台（静态 HTML，无服务端模板）。"""
    path = os.path.join(_ROOT, "static", "ai_assist.html")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"


__all__ = ["router", "page_router"]

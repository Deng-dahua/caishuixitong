# -*- coding: utf-8 -*-
"""报告模板管理 HTTP 接口（P1-5）。

路径前缀 `/api/v1`（**新增**端点专用；既有报告链路一字未改）。

★ 端点
    GET  /api/v1/report-templates                    模板清单（可含停用项）
    GET  /api/v1/report-templates/meta               字典（章节白名单 / 内置模板 id / 编码规则）
    GET  /api/v1/report-templates/{templateId}       单个模板
    GET  /api/v1/report-templates/{templateId}/versions  变更历史
    POST /api/v1/report-templates/{templateId}       新建/覆盖（版本号自增）
    POST /api/v1/report-templates/{templateId}/disable   停用（仅限自定义/覆盖模板）

★ 路由顺序：`meta` 必须注册在 `{templateId}` **之前**（否则被路径参数吃掉 ⇒ 静默 404）。
★ 权限：读 `report.view`；写 `template.manage`（唯一权威 `engine.rbac.rbac_allows`）。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from engine import template_store as STORE

router = APIRouter(prefix="/api/v1", tags=["报告模板管理（P1-5）"])
page_router = APIRouter(tags=["报告模板管理（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _request_perm(request: Request, perm: str):
    auth = getattr(request.state, "auth", None)
    if auth is None:
        raise HTTPException(status_code=401, detail="未登录")
    from engine.rbac import rbac_allows                      # noqa: PLC0415
    if not rbac_allows(auth, perm):
        raise HTTPException(status_code=403, detail="缺少权限：%s" % perm)
    return auth


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except STORE.TemplateError as exc:
        raise HTTPException(status_code=int(exc.status), detail=str(exc.message)) from exc


@router.get("/report-templates/meta", summary="报告模板字典（章节白名单 / 内置模板 / 编码规则）")
def templates_meta(request: Request) -> Dict[str, Any]:
    _request_perm(request, "report.view")
    return STORE.metadata()


@router.get("/report-templates", summary="报告模板清单")
def list_report_templates(request: Request,
                          include_disabled: bool = Query(False)):
    _request_perm(request, "report.view")
    rows: List[Dict[str, Any]] = STORE.list_templates(include_disabled=bool(include_disabled))
    return {"total": len(rows), "items": rows,
            "builtin_count": len(STORE.builtin_templates()),
            "note": ("有效模板 = 内置（config/report_compliance.json）⊕ 自定义覆盖（台账）；"
                     "停用项默认不列出，可用 include_disabled=true 一并查看。")}


@router.get("/report-templates/{template_id}", summary="单个报告模板")
def get_report_template(template_id: str, request: Request):
    _request_perm(request, "report.view")
    item = STORE.get_template(template_id)
    if item is None:
        raise HTTPException(status_code=404, detail="模板不存在：%s" % template_id)
    return item


@router.get("/report-templates/{template_id}/versions", summary="模板变更历史")
def report_template_versions(template_id: str, request: Request):
    _request_perm(request, "report.view")
    hist = STORE.template_versions(template_id)
    return {"template_id": template_id, "total": len(hist), "items": hist,
            "note": ("变更历史来自 append-only 台账；内置模板在**未覆盖前**历史为空 —— "
                     "空历史不表示模板不存在。")}


@router.post("/report-templates/{template_id}", summary="新建/覆盖报告模板（版本自增）")
def upsert_report_template(template_id: str, request: Request,
                           payload: Dict[str, Any] = Body(default_factory=dict)):
    """请求体：`{label, sections: [...], emphasis?, note?}`。

    ★ `sections` 必须落在 `report_template.BASE_SECTIONS` 白名单内（否则 400）——
      "新增一个章节"必须显式发生在白名单里，不能悄悄出现在某个模板中。
    """
    session = _request_perm(request, "template.manage")
    return _call(STORE.upsert_template, template_id, payload, session, request=request)


@router.post("/report-templates/{template_id}/disable", summary="停用报告模板")
def disable_report_template(template_id: str, request: Request,
                            payload: Dict[str, Any] = Body(default_factory=dict)):
    """停用**自定义/覆盖**模板；内置且未被覆盖的模板**不可停用**（400 并说明原因）。"""
    session = _request_perm(request, "template.manage")
    body = payload if isinstance(payload, dict) else {}
    return _call(STORE.disable_template, template_id, session,
                 request=request, note=str(body.get("note") or ""))


@page_router.get("/report-templates", response_class=HTMLResponse,
                 include_in_schema=False)
def report_templates_page():
    """报告模板管理页（静态 HTML，无服务端模板）。"""
    path = os.path.join(_ROOT, "static", "templates.html")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"


__all__ = ["router", "page_router"]

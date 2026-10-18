# -*- coding: utf-8 -*-
"""P0-7 报告生成与导出 —— HTTP 接口。

路径前缀 `/api/v1`（**新增**端点专用；与 T-3 裁定不冲突：现有端点一字未改）。

| 端点 | 说明 |
|---|---|
| `POST /api/v1/projects/{projectId}/reports` | 生成报告（视图 + 格式 + 复核标识） |
| `GET /api/v1/reports/{reportId}` | 报告详情（登记信息 + 版本台账回读 + 可下载格式） |
| `GET /api/v1/reports/{reportId}/download` | 下载（`?format=pdf|docx|xlsx|html`） |
| `GET /api/v1/reports` | 报告列表（按项目/账套；分页） |
| `GET /api/v1/reports/meta` | 字典（4 视图 / 4 格式 / 12 章节 / 水印方式） |
| `GET /api/v1/reports/versions` | 版本台账（唯一权威 `data/report_versions.jsonl`） |

★ `reportId` = **文书编号 `doc_no`**（版本台账权威，跨系统稳定；兼容 `reports.id`）。
★ 认证：唯一权威 `security_web.enforce_request_security`（`main.auth_middleware` 调用）；
  本模块只读 `request.state.auth`，不重复实现鉴权。
★ 可见性：跨租户 ⇒ **404**（不泄露存在性），与 P0-1~P0-6 同一口径。
★ 免责声明与人工复核标识由**渲染层强制**（缺失即 500 且说明原因，不产报告）。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

from engine import report_service as SVC

from engine.api_common import (admin_of, call_boundary, request_perm,
                             require_perm, session_of)

# ★ R-02（2026-10-17）：以下名字是**别名**，逻辑唯一在 engine/api_common。
#   禁止在本文件重新定义（闸门 `check_api_boundary_single_source` 会报错）。
_require_perm = require_perm
_session = session_of

router = APIRouter(prefix="/api/v1", tags=["报告生成与导出（P0-7）"])

#: 页面路由（**无前缀**）。单独一个 router 是为了让 `main.py` 只需**同一行内**追加一个
#: `include_router` ⇒ 文件行数不变 ⇒ 既有文档中的 `main.py:行号` 引用零漂移。
page_router = APIRouter(tags=["报告生成与导出（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))
_MAX_PAGE_SIZE = 200


@page_router.get("/reports", response_class=HTMLResponse, include_in_schema=False)
def reports_page():
    """报告生成与导出页（静态 HTML，无服务端模板）。

    ★ 资源缺失 ⇒ **明确 500 + 说明**（不把 `FileNotFoundError` 裸抛给调用方）。
    """
    path = os.path.join(_ROOT, "static", "reports.html")
    if not os.path.exists(path):
        raise HTTPException(status_code=500, detail="页面资源缺失：static/reports.html")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    raise HTTPException(status_code=500, detail="页面资源编码无法识别：static/reports.html")


def _svc(fn, *args, **kwargs):
    """调 Service 并把 `ReportServiceError` 转 HTTP 语义。

    ★ 一处收口（Service 侧已有 `_boundary` 统一异常类型；此处只做 HTTP 映射）。
    """
    try:
        return fn(*args, **kwargs)
    except SVC.ReportServiceError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc


def _company_of_project(project_id: int, session: Any) -> int:
    """项目 → 账套（**沿用 P0-1 项目可见性**，不另立口径）。"""
    from engine import risk_service as RISK                       # noqa: PLC0415
    try:
        return RISK.company_of_project(project_id, session)
    except RISK.RiskServiceError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc


# --------------------------------------------------------------------------
# 字典 / 版本台账（★ 必须声明在 `/reports/{report_id}` 之前，否则会被路径参数吃掉）
# --------------------------------------------------------------------------
@router.get("/reports/meta", summary="字典（4 视图 / 4 格式 / 12 章节 / 水印方式）")
def reports_meta(request: Request):
    _session(request)
    return SVC.metadata()


@router.get("/reports/versions", summary="报告版本台账（唯一权威 report_versions.jsonl）")
def report_versions(request: Request, company_id: int = Query(..., ge=1)):
    session = _session(request)
    return _svc(SVC.versions, company_id, session)


@router.get("/reports", summary="报告列表（按项目/账套；分页）")
def list_reports(request: Request,
                 project_id: Optional[int] = Query(None, ge=1),
                 company_id: Optional[int] = Query(None, ge=1),
                 view: Optional[str] = None,
                 page: int = Query(1, ge=1),
                 page_size: int = Query(20, ge=1, le=_MAX_PAGE_SIZE)):
    session = _session(request)
    return _svc(SVC.list_reports, session, project_id=project_id,
                company_id=company_id, view=view, page=page, page_size=page_size)


# --------------------------------------------------------------------------
# 生成
# --------------------------------------------------------------------------
@router.post("/projects/{project_id}/reports", summary="生成报告（视图 + 格式 + 复核标识）")
def generate_report(project_id: int, request: Request,
                    payload: Dict[str, Any] = Body(default_factory=dict)):
    """请求体：

    ```
    {
      "view": "full" | "tax_specific" | "management" | "self_check",
      "formats": ["pdf","docx","xlsx","html"]    # 可省略 ⇒ 全部 4 种
      "reviewed": true|false|null,               # 省略 ⇒ 按账套**实际**处置记录推断
      "reviewed_by": "复核人",
      "reviewed_note": "复核说明",
      "change_note": "本次生成说明"
    }
    ```
    """
    session = _session(request)
    _require_perm(session, "report.generate")
    body = payload if isinstance(payload, dict) else {}
    view = str(body.get("view") or "full")
    fmts = body.get("formats")
    reviewed = body.get("reviewed")
    if isinstance(reviewed, str):
        reviewed = reviewed.strip().lower() in ("1", "true", "yes", "y")
    out = _svc(SVC.generate, project_id, session, view=view, formats=fmts,
               reviewed=reviewed, reviewed_by=str(body.get("reviewed_by") or ""),
               reviewed_note=str(body.get("reviewed_note") or ""),
               change_note=str(body.get("change_note") or ""),
               request=request)
    out["project_id"] = int(project_id)
    out["company_id"] = _company_of_project(project_id, session)
    out["detail_url"] = "/api/v1/reports/%s" % (out.get("doc_no") or out.get("id"))
    out["download_urls"] = {
        f: "/api/v1/reports/%s/download?format=%s" % (out.get("doc_no"), f)
        for f in sorted(out.get("files") or {})}
    return out


# --------------------------------------------------------------------------
# 详情 / 下载
# --------------------------------------------------------------------------
@router.get("/reports/{report_id}", summary="报告详情（含版本台账回读与可下载格式）")
def get_report(report_id: str, request: Request):
    session = _session(request)
    return _svc(SVC.get, report_id, session)


@router.get("/reports/{report_id}/download", summary="下载报告（pdf/docx/xlsx/html）")
def download_report(report_id: str, request: Request, fmt: str = Query("pdf", alias="format")):
    """★ 返回**已落盘的原件**（不重渲染 ⇒ 不产生新版本）。"""
    session = _session(request)
    data, fname, headers = _svc(SVC.download, report_id, session, fmt=fmt,
                                request=request)
    from engine.report_views import FORMAT_MEDIA                    # noqa: PLC0415
    from engine.report_views import validate_format                 # noqa: PLC0415
    media = FORMAT_MEDIA[validate_format(fmt)]
    return Response(content=data, media_type=media, headers=headers)


__all__ = ["router", "page_router"]

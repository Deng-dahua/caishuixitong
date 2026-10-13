# -*- coding: utf-8 -*-
"""解析与标准化 HTTP 接口（P0-3）。

路径前缀 `/api/v1`（**新增**端点专用；现有端点一字未改）。

★ 任务书要求的接口
    GET  /api/v1/documents/{documentId}/extracted      解析结果（表 + 标准字段 + 校验异常）
    PUT  /api/v1/extracted/{id}                        人工校正一个标准字段
  另补（"解析任务异步执行，状态可查"所必需 + 项目级异常清单）：
    POST /api/v1/documents/{documentId}/extract        发起解析（登记 `analysis_jobs` 作业）
    GET  /api/v1/extract/jobs/{jobId}                  作业状态（**复用 analysis_jobs**）
    POST /api/v1/extract/issues/{issueId}/resolve      标记异常已处理
    GET  /api/v1/projects/{projectId}/extract-issues   项目级校验异常清单
    GET  /api/v1/extract/meta                          字典（标准字段 / 规则 / 复用说明）

★ 认证：唯一权威 = `security_web.enforce_request_security`（中间件已做），本模块只读
  `request.state.auth`。
★ 错误语义：400 参数/校正值非法 ｜ 401 未登录 ｜ 404 不存在**或跨租户** ｜ 409 状态冲突。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from engine import extract_service as SVC

router = APIRouter(prefix="/api/v1", tags=["解析与标准化（P0-3）"])

page_router = APIRouter(tags=["解析与标准化（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))


class CorrectIn(BaseModel):
    value: Any = Field(..., description="校正后的值（按标准字段类型归一：金额/期间会校验）")


class ResolveIn(BaseModel):
    status: str = Field("resolved", description="resolved（已处理）/ ignored（确认非问题）")


def _session(request: Request):
    auth = getattr(request.state, "auth", None)
    if auth is None:
        raise HTTPException(status_code=401, detail="未登录")
    return auth


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except SVC.ExtractError as exc:
        raise HTTPException(status_code=int(exc.status), detail=str(exc.message)) from exc


# --------------------------------------------------------------------------
# 字典（★ 注册在通配之前）
# --------------------------------------------------------------------------
@router.get("/extract/meta", summary="解析字典（标准字段 / 校验规则 / 复用说明）")
def extract_meta(request: Request):
    _session(request)
    return SVC.metadata()


@router.get("/extract/jobs/{job_id}", summary="解析作业状态（复用 analysis_jobs）")
def extract_job(job_id: str, request: Request):
    _session(request)
    from engine.analysis_jobs import get_job, status_cn   # noqa: PLC0415
    hit = get_job(job_id)
    if not hit:
        raise HTTPException(status_code=404, detail="作业不存在")
    out = dict(hit)
    out["status_cn"] = status_cn(out.get("status"))
    return out


# --------------------------------------------------------------------------
# 解析结果 / 触发解析
# --------------------------------------------------------------------------
@router.get("/documents/{document_id}/extracted", summary="解析结果（表 / 标准字段 / 校验异常）")
def get_extracted(
    document_id: int,
    request: Request,
    domain: Optional[str] = None,
    only_corrected: Optional[str] = None,
):
    session = _session(request)
    return _call(SVC.get_extracted, document_id, session,
                 domain=domain, only_corrected=only_corrected)


@router.post("/documents/{document_id}/extract", summary="发起解析（解析+标准化+校验）")
def run_extract(document_id: int, request: Request):
    """同步执行解析并返回结果；同时向 `analysis_jobs` 登记作业（状态可查）。

    ★ 为什么同步：单份资料的解析是**秒级**操作（既有 `_parse_excel_structured` 本地执行），
      异步化会引入"点了没反应"的观感问题。作业登记保证**可追溯**与**状态可查**；
      需要真正异步（批量解析）时，复用 `analysis_jobs` 的既有异步链路即可。
    """
    session = _session(request)
    from engine.analysis_jobs import job_finished, job_started   # noqa: PLC0415
    import uuid as _uuid                              # noqa: PLC0415
    job_id = "extract-" + _uuid.uuid4().hex[:12]
    company_id = getattr(session, "selected_company_id", None)
    # ★ 复用既有作业流水（唯一权威）：触发方式用已登记值 `"manual"`；
    #   终态用已登记值 `done` / `error`（**不是** success/failed —— 那两个不在词表里）。
    job_started(company_id, job_id, started_by=getattr(session, "username", ""),
                trigger="manual")
    try:
        res = _call(SVC.parse_document, document_id, session, request=request)
        job_finished(job_id, "done", company_id,
                     findings_count=len(res.get("fields") or []))
        res["job_id"] = job_id
        return res
    except HTTPException as exc:
        job_finished(job_id, "error", company_id, error_message=str(exc.detail)[:200])
        raise


# --------------------------------------------------------------------------
# 人工校正 / 异常处理 / 项目级清单
# --------------------------------------------------------------------------
@router.put("/extracted/{field_id}", summary="人工校正一个标准字段值")
def correct_extracted(field_id: int, payload: CorrectIn, request: Request):
    session = _session(request)
    return _call(SVC.correct_field, field_id, {"value": payload.value}, session,
                 request=request)


@router.post("/extract/issues/{issue_id}/resolve", summary="标记校验异常为已处理/非问题")
def resolve_issue(issue_id: int, payload: ResolveIn, request: Request):
    session = _session(request)
    return _call(SVC.resolve_issue, issue_id, {"status": payload.status}, session,
                 request=request)


@router.get("/projects/{project_id}/extract-issues", summary="项目级校验异常清单")
def list_issues(
    project_id: int,
    request: Request,
    rule: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
):
    session = _session(request)
    return _call(SVC.list_issues, project_id, session,
                 rule=rule, severity=severity, status=status)


# --------------------------------------------------------------------------
# 页面
# --------------------------------------------------------------------------
@page_router.get("/extract", response_class=HTMLResponse, include_in_schema=False)
def extract_page():
    """解析与校正页（静态 HTML，无服务端模板）。"""
    path = os.path.join(_ROOT, "static", "extract.html")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"

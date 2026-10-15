# -*- coding: utf-8 -*-
"""一键稽查分析任务 HTTP 接口（P0-4）。

路径前缀：
  · `/api/v1/projects/{projectId}/analysis-jobs`（**发起**：按项目发车）
  · `/api/v1/analysis-jobs/...`（**查询/取消/重试**：按作业 id）

★ 与既有裁定的关系（勿误判为违反）
  T-3 裁定「`/api/v1` 仅形式要求 ⇒ **不给现有端点加前缀**」。本模块**不触碰任何现有端点**
  （`/api/tax-risk-docs/*` 的同步与异步入口一字未改），只是把**新增**接口挂在 `/api/v1`
  —— 两者不冲突，且满足任务书明确列出的三条路径。

★ 认证：唯一权威 = `security_web.enforce_request_security`（`main.auth_middleware` 调用），
  已在中间件层完成鉴权并写入 `request.state.auth`。本模块**只读**该属性，不重复实现鉴权。

★ 错误语义（由任务层 `AnalysisTaskError.status` 原样转发）
  400 参数/状态非法 ｜ 401 未登录 ｜ 404 作业不存在**或跨租户**（404 而非 403：不泄露存在性）
  ｜ 409 已有同账套任务在跑 / 启动失败。
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from engine import analysis_task as SVC

router = APIRouter(prefix="/api/v1", tags=["稽查分析任务（P0-4）"])

#: 页面路由（**无前缀**）。单独一个 router 是为了让 `main.py` 只需**同一行内**
#: 追加一个 `include_router` ⇒ 文件行数不变 ⇒ 既有文档中的 `main.py:行号` 引用零漂移。
page_router = APIRouter(tags=["稽查分析任务（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))


@page_router.get("/analysis", response_class=HTMLResponse, include_in_schema=False)
def analysis_page():
    """一键稽查分析任务页（静态 HTML，无服务端模板）。"""
    path = os.path.join(_ROOT, "static", "analysis.html")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"


# --------------------------------------------------------------------------
# 请求体（Pydantic ⇒ Swagger 有完整 schema）
# --------------------------------------------------------------------------
class LaunchJobRequest(BaseModel):
    """发起一次稽查分析。"""
    force: bool = Field(False, description="强制重算（跳过「资料未变则复用」的增量短路）")


def _session(request: Request):
    """取当前会话。取不到 ⇒ 401（**不静默放行**）。"""
    auth = getattr(request.state, "auth", None)
    if auth is None:
        raise HTTPException(status_code=401, detail="未登录")
    return auth


def _call(fn, *args, **kwargs):
    """统一把任务层业务异常转成 HTTP（**唯一转换点**，避免各处各写一套）。"""
    try:
        return fn(*args, **kwargs)
    except SVC.AnalysisTaskError as exc:
        raise HTTPException(status_code=int(exc.status), detail=str(exc.message)) from exc


# --------------------------------------------------------------------------
# 元数据（★ 必须注册在 `/{job_id}` 之前，否则 "meta" 会被当成 id）
# --------------------------------------------------------------------------
@router.get("/analysis-jobs/meta", summary="分析任务字典（8 步 / 5 状态 / 触发方式）")
def get_meta(request: Request):
    _session(request)
    return SVC.metadata()


# --------------------------------------------------------------------------
# 发起与历史（按项目）
# --------------------------------------------------------------------------
@router.post("/projects/{project_id}/analysis-jobs", summary="发起稽查分析任务",
             status_code=201)
def launch_job(project_id: int, payload: Optional[LaunchJobRequest] = None,
               request: Request = None):
    session = _session(request)
    force = bool(getattr(payload, "force", False))
    return _call(SVC.launch, project_id, session, force=force, request=request)


@router.get("/projects/{project_id}/analysis-jobs", summary="某项目的任务历史（倒序）")
def list_project_jobs(project_id: int, request: Request,
                      limit: int = Query(50, ge=1, le=200)):
    session = _session(request)
    return _call(SVC.list_for_project, project_id, session, limit=limit)


# --------------------------------------------------------------------------
# 查询 / 取消 / 重试（按作业 id）
# --------------------------------------------------------------------------
@router.get("/analysis-jobs/{job_id}", summary="任务状态（状态/进度/当前步骤/8 步清单）")
def get_job(job_id: str, request: Request):
    session = _session(request)
    return _call(SVC.get, job_id, session)


@router.post("/analysis-jobs/{job_id}/cancel", summary="取消任务（结果不予采用）")
def cancel_job(job_id: str, request: Request):
    session = _session(request)
    return _call(SVC.cancel, job_id, session)


@router.post("/analysis-jobs/{job_id}/retry", summary="重试任务（仅失败/已取消可重试）")
def retry_job(job_id: str, request: Request):
    session = _session(request)
    return _call(SVC.retry, job_id, session, request=request)


@router.delete("/analysis-jobs/{job_id}", summary="删除任务记录（历史清理；运行中不可删，结果/报告不受影响）")
def delete_analysis_job(job_id: str, request: Request):
    session = _session(request)
    return _call(SVC.delete_job, job_id, session)


__all__ = ["router", "page_router"]

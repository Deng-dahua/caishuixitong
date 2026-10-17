# -*- coding: utf-8 -*-
"""稽查项目 HTTP 接口（P0-1）。

路径前缀 `/api/v1/projects`（**新增**端点专用）。

★ 与既有裁定的关系（勿误判为违反）
  用户曾裁定「`/api/v1` 仅形式要求 ⇒ **不给现有 167 个端点加前缀**」（T-3）。
  本模块**不触碰任何现有端点**，只是把**新增**的项目接口挂在 `/api/v1` 下
  —— 两者不冲突，且满足任务书明确列出的 `/api/v1/projects` 路径与
  「接口变更必须向后兼容」（现有路径一字未改）。

★ 认证
  唯一权威 = `security_web.enforce_request_security`（`main.py` 的 `auth_middleware` 调用），
  已在中间件层完成鉴权并写入 `request.state.auth`。本模块**只读**该属性，
  **不重复实现鉴权**（避免第二套口径）。

★ 错误语义（由 Service 层 `ProjectError.status` 原样转发）
  400 参数/状态迁移非法 ｜ 401 未登录 ｜ 403 无写权限 ｜ 404 项目不存在**或跨租户**
  （404 而非 403：**不泄露对象是否存在**，这是租户隔离的一部分）。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from engine import project_service as SVC

router = APIRouter(prefix="/api/v1/projects", tags=["稽查项目（P0-1）"])

#: 页面路由（**无前缀**）。单独一个 router 是为了让 `main.py` 只需**同一行内**
#: 追加一个 `include_router` ⇒ 文件行数不变 ⇒ 既有文档中的 `main.py:行号` 引用零漂移。
page_router = APIRouter(tags=["稽查项目（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))


@page_router.get("/projects", response_class=HTMLResponse, include_in_schema=False)
def projects_page():
    """稽查项目管理页（静态 HTML，无服务端模板）。"""
    path = os.path.join(_ROOT, "static", "projects.html")
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
class ProjectCreate(BaseModel):
    """新建项目。"""
    name: str = Field(..., description="企业名称（项目名）", examples=["示例科技有限公司"])
    taxpayer_id: Optional[str] = Field(None, description="纳税人识别号（统一社会信用代码）")
    industry: Optional[str] = Field(None, description="行业")
    region: Optional[str] = Field(None, description="地区")
    period_start: Optional[str] = Field(None, description="稽查期间起（YYYY-MM-DD）")
    period_end: Optional[str] = Field(None, description="稽查期间止（YYYY-MM-DD）")
    tax_scopes: Optional[List[str]] = Field(None, description="税种范围（数组）")
    status: Optional[str] = Field("draft", description="状态（新建只允许 draft=草稿）")
    remark: Optional[str] = Field(None, description="备注")
    company_id: Optional[int] = Field(None, description="所属账套（租户边界）；缺省用会话选中账套")
    code: Optional[str] = Field(None, description="项目编号（缺省自动生成 PJ-YYYYMMDD-####）")


class ProjectUpdate(BaseModel):
    """修改项目（**全部字段可选**，只更新传入项；`status` 变化须满足状态机）。"""
    name: Optional[str] = None
    taxpayer_id: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    tax_scopes: Optional[List[str]] = None
    status: Optional[str] = Field(None, description="目标状态（须为当前状态的合法后继）")
    remark: Optional[str] = None
    code: Optional[str] = None


class MemberAdd(BaseModel):
    """新增成员或调整既有成员角色（同人重复加入 ⇒ 视为**角色变更**，幂等）。"""
    user_id: Optional[int] = Field(None, description="用户 ID")
    user_name: Optional[str] = Field(None, description="用户姓名（与 user_id 至少给一个）")
    role: Optional[str] = Field("member", description="角色：owner/reviewer/member/viewer")


# --------------------------------------------------------------------------
# 内部
# --------------------------------------------------------------------------
def _session(request: Request):
    """取当前会话。取不到 ⇒ 401（**不静默放行**）。"""
    auth = getattr(request.state, "auth", None)
    if auth is None:
        raise HTTPException(status_code=401, detail="未登录")
    return auth


def _require_perm(session, code: str):
    """写操作的**功能权限点**校验（MQ2-D1）。

    权威：`engine.rbac.rebac_allows()`（经 `require_permission` 抛 403）。
    本函数只做「RbacError → HTTPException」的边界转换，**不自判角色**（否则即第二套口径）。
    """
    from engine.rbac import RbacError, require_permission          # noqa: PLC0415
    try:
        require_permission(session, code)
    except RbacError as exc:
        raise HTTPException(status_code=int(getattr(exc, "status", 403)),
                            detail=str(getattr(exc, "message", exc))) from exc
    return session


def _call(fn, *args, **kwargs):
    """统一把 Service 的业务异常转成 HTTP（**唯一转换点**，避免各处各写一套）。"""
    try:
        return fn(*args, **kwargs)
    except SVC.ProjectError as exc:
        raise HTTPException(status_code=int(exc.status), detail=str(exc.message)) from exc


# --------------------------------------------------------------------------
# 元数据（★ 必须注册在 `/{project_id}` 之前，否则 "meta" 会被当成 id）
# --------------------------------------------------------------------------
@router.get("/meta", summary="项目字典（状态/角色/状态迁移表）")
def get_meta(request: Request):
    _session(request)
    return SVC.metadata()


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------
@router.post("", summary="新建稽查项目", status_code=201)
def create_project(payload: ProjectCreate, request: Request):
    session = _session(request)
    _require_perm(session, "project.write")
    return _call(SVC.create_project, payload.model_dump(), session, request=request)


@router.get("", summary="项目列表（搜索/筛选/分页/排序）")
def list_projects(
    request: Request,
    q: Optional[str] = None,
    status: Optional[str] = None,
    industry: Optional[str] = None,
    company_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "updated_at",
    order: str = "desc",
):
    session = _session(request)
    return _call(SVC.list_projects, session, q=q, status=status, industry=industry,
                 company_id=company_id, page=page, page_size=page_size,
                 sort=sort, order=order)


@router.get("/{project_id}", summary="项目详情（含成员与操作日志）")
def get_project(project_id: int, request: Request):
    session = _session(request)
    return _call(SVC.get_project, project_id, session)


@router.put("/{project_id}", summary="修改项目（含状态迁移）")
def update_project(project_id: int, payload: ProjectUpdate, request: Request):
    session = _session(request)
    _require_perm(session, "project.write")
    return _call(SVC.update_project, project_id, payload.model_dump(exclude_unset=True),
                 session, request=request)


@router.delete("/{project_id}", summary="删除项目（含其成员记录与资料）")
def delete_project(project_id: int, request: Request,
                   cascade: bool = Query(False, description="true=一并删除项目下资料（文件进回收站）")):
    """删除项目。项目下有资料且未传 `cascade=true` ⇒ **409**（要求显式确认，避免误删）。"""
    session = _session(request)
    _require_perm(session, "project.write")
    return _call(SVC.delete_project, project_id, session, request=request, cascade=cascade)


# --------------------------------------------------------------------------
# 成员
# --------------------------------------------------------------------------
@router.get("/{project_id}/members", summary="项目成员列表")
def list_members(project_id: int, request: Request):
    session = _session(request)
    return _call(SVC.list_members, project_id, session)


@router.post("/{project_id}/members", summary="新增成员 / 调整成员角色", status_code=201)
def add_member(project_id: int, payload: MemberAdd, request: Request):
    session = _session(request)
    _require_perm(session, "project.write")
    return _call(SVC.add_member, project_id, payload.model_dump(), session, request=request)

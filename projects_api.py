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

from engine.api_common import (admin_of, call_boundary, request_perm,
                             require_perm, session_of)

# ★ R-02（2026-10-17）：以下名字是**别名**，逻辑唯一在 engine/api_common。
#   禁止在本文件重新定义（闸门 `check_api_boundary_single_source` 会报错）。
_require_perm = require_perm
_session = session_of

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
    """新建项目。

    ★ 2026-10-18（用户要求）：行业/地区/稽查期间等**在建项目这一步收集**，
      并补录企业重点工商信息。后端**不硬性阻断**缺项（兼容 API/历史数据），
      缺失由 `profile_missing` 如实在列表标注「待补全」，不编造默认值。
    """
    name: str = Field(..., description="企业名称（项目名）", examples=["示例科技有限公司"])
    taxpayer_id: Optional[str] = Field(None, description="纳税人识别号（统一社会信用代码）")
    industry: Optional[str] = Field(None, description="行业（取值见 /meta 的 industries）")
    region: Optional[str] = Field(None, description="地区（省/自治区/直辖市，可精确到市）")
    period_start: Optional[str] = Field(None, description="稽查期间起（YYYY-MM-DD）")
    period_end: Optional[str] = Field(None, description="稽查期间止（YYYY-MM-DD）")
    tax_scopes: Optional[List[str]] = Field(None, description="税种范围（数组，取值见 /meta 的 tax_types）")
    status: Optional[str] = Field("draft", description="状态（新建只允许 draft=草稿）")
    remark: Optional[str] = Field(None, description="备注")
    company_id: Optional[int] = Field(None, description="所属账套（租户边界）；缺省用会话选中账套")
    code: Optional[str] = Field(None, description="项目编号（缺省自动生成 PJ-YYYYMMDD-####）")
    # ── 企业重点工商信息（2026-10-18 新增；字段权威 = project_service.PROFILE_FIELDS）──
    legal_representative: Optional[str] = Field(None, description="法定代表人")
    registered_capital: Optional[float] = Field(None, description="注册资本（万元）")
    established_date: Optional[str] = Field(None, description="成立日期（YYYY-MM-DD）")
    registration_status: Optional[str] = Field(None, description="登记状态")
    registered_address: Optional[str] = Field(None, description="注册地址")
    business_scope: Optional[str] = Field(None, description="经营范围")
    company_type: Optional[str] = Field(None, description="公司类型")


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
    legal_representative: Optional[str] = None
    registered_capital: Optional[float] = None
    established_date: Optional[str] = None
    registration_status: Optional[str] = None
    registered_address: Optional[str] = None
    business_scope: Optional[str] = None
    company_type: Optional[str] = None


class MemberAdd(BaseModel):
    """新增成员或调整既有成员角色（同人重复加入 ⇒ 视为**角色变更**，幂等）。"""
    user_id: Optional[int] = Field(None, description="用户 ID")
    user_name: Optional[str] = Field(None, description="用户姓名（与 user_id 至少给一个）")
    role: Optional[str] = Field("member", description="角色：owner/reviewer/member/viewer")


# --------------------------------------------------------------------------
# 内部
# --------------------------------------------------------------------------
def _call(fn, *args, **kwargs):
    """业务异常 → HTTP 的**唯一转换点**在 `engine/api_common.call_boundary`；
    本函数只声明「本域该捕获哪一类业务异常」（SVC.ProjectError）。"""
    return call_boundary(fn, *args, exc_types=(SVC.ProjectError,), **kwargs)


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


@router.get("/{project_id}/profile-suggestions",
            summary="编辑项目页的**自动填列建议**（逐字段：值/来源/不可得原因）")
def project_profile_suggestions(project_id: int, request: Request):
    """返回该项目的逐字段建议值，供「编辑项目」表单**自动填列**。

    ## 为什么要有这个端点（用户 2026-10-19 的要求）

      > 「编辑项目页面下所有的信息都是自动获取自动填列的 …… 而不是甚至一个自动按钮」

    前端一次请求即可拿到：每个字段的**建议值**、**依据来源**（注册地址解析 / 工商档案 /
    分析结果 / 登记机关行政区划码）、以及**推导不出来的原因**（如实说明，不留白让人猜）。

    ## 口径（不另建第二套权威）

      · 派生逻辑唯一实现 = `engine.project_profile_fill`（行业走 `industry_resolver`）；
      · 报告来源唯一权威 = `engine.risk_service.load_payload`（报告载荷，服务落盘的那份）；
      · 工商档案唯一权威 = `engine.business_info.store`；
      · 本端点**只读**，不写任何库（写入由分析完成后的
        `project_service.sync_profile_from_analysis` 统一执行）。

    取不到报告载荷 ⇒ 工商类字段仍给建议（来自工商档案），
    期间/税种等分析类字段如实返回「尚未分析，无法推导」。
    """
    session = _session(request)
    detail = _call(SVC.get_project, project_id, session)
    # ★ `project_service.get_project` 返回的是**项目本身**（不是 `{project: ...}` 包一层）。
    #   兼容两种形状：万一将来改成包一层也不会静默取到空 dict
    #   （首版就写成 `detail.get("project")` ⇒ 拿到 None ⇒ 所有字段都"推导不出"，
    #     接口返回一堆「未能识别」而实际数据齐全 —— 实测抓出来的）。
    project = detail.get("project") if isinstance(detail, dict) and "project" in detail else detail
    project = project if isinstance(project, dict) else {}

    report: Dict[str, Any] = {}
    report_state = "分析结果不可得"
    try:
        from engine.risk_service import load_payload                # noqa: PLC0415
        cid = project.get("company_id")
        if cid:
            got = load_payload(cid, session)
            if got.get("available"):
                report = got.get("payload") or {}
                report_state = "已读取最近一次分析结果"
            else:
                report_state = str(got.get("reason") or "分析结果不可得")
    except Exception as exc:                                        # noqa: BLE001
        report_state = "分析结果读取失败：%s" % exc

    company_row = None
    try:
        from engine.business_info import store as BIZ               # noqa: PLC0415
        tid = str(project.get("taxpayer_id") or "")
        name = str(project.get("name") or "")
        company_row = (BIZ.get_by_tax_id(tid) if tid
                       else (BIZ.get(name) if name else None))
    except Exception:                                               # noqa: BLE001
        company_row = None

    from engine.project_profile_fill import suggest_for_project     # noqa: PLC0415
    out = suggest_for_project(project, report, company_row)
    out["project_id"] = project_id
    out["report_state"] = report_state
    out["company_row_found"] = bool(company_row)
    return out


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

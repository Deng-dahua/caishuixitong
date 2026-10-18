# -*- coding: utf-8 -*-
"""权限 / 用户 / 角色 / 审计日志 HTTP 接口（P0-8）。

路径前缀 `/api/v1`（**新增**端点专用）：

  POST /api/v1/auth/login     登录（与既有 `/api/auth/login` **共用同一实现**）
  GET  /api/v1/users          用户列表（租户隔离 + 敏感字段按角色脱敏）
  POST /api/v1/users          新建用户（含角色指派）
  GET  /api/v1/users/{id}     用户详情
  PUT  /api/v1/users/{id}     修改用户（显示名/联系方式/启停用/角色/组织/账套）
  GET  /api/v1/roles          角色与权限字典
  POST /api/v1/roles          新建自定义角色
  GET  /api/v1/audit-logs     审计日志（租户隔离 + 脱敏）

★ 与既有裁定的关系：用户曾裁定「`/api/v1` 仅形式要求 ⇒ 不给现有端点加前缀」。
  本模块**不触碰任何现有端点**，只把**新增**接口挂在 `/api/v1` 下。

★ 认证：唯一权威 = `security_web.enforce_request_security`（`main.py` 的鉴权中间件），
  已在中间件层完成会话校验并写入 `request.state.auth`；本模块**只读**该属性。
  `/api/v1/auth/login` 已在 `security.is_public_path` 登记为公开路径 ⇒ 中间件放行。

★ 授权：唯一权威 = `engine/rbac.rbac_allows()`（经 `engine/access_service` 的
  `_require()`）。本模块**不自行判断角色**（否则就是第二套口径）。

★ 错误语义：400 参数非法 ｜ 401 未登录 ｜ 403 无权限/跨租户写 ｜ 404 不存在**或跨租户**
  （404 而非 403：不泄露对象是否存在）。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from engine import access_service as SVC

from engine.api_common import (admin_of, call_boundary, request_perm,
                             require_perm, session_of)

# ★ R-02（2026-10-17）：以下名字是**别名**，逻辑唯一在 engine/api_common。
#   禁止在本文件重新定义（闸门 `check_api_boundary_single_source` 会报错）。
_session = session_of

router = APIRouter(prefix="/api/v1", tags=["权限与审计（P0-8）"])

#: 页面路由（**无前缀**）。单独一个 router 是为了让 `main.py` 只需**同一行内**
#: 追加一个 `include_router` ⇒ 文件行数不变 ⇒ 既有文档中的 `main.py:行号` 引用零漂移。
page_router = APIRouter(tags=["权限与审计（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))


@page_router.get("/users", response_class=HTMLResponse, include_in_schema=False)
def users_page():
    """用户管理页（静态 HTML，无服务端模板）。"""
    return _read_page("users.html")


@page_router.get("/roles", response_class=HTMLResponse, include_in_schema=False)
def roles_page():
    """角色管理页。"""
    return _read_page("roles.html")


@page_router.get("/audit-logs", response_class=HTMLResponse, include_in_schema=False)
def audit_logs_page():
    """审计日志页。"""
    return _read_page("audit_logs.html")


def _read_page(filename: str) -> str:
    path = os.path.join(_ROOT, "static", filename)
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"


# --------------------------------------------------------------------------
# 请求体
# --------------------------------------------------------------------------
class LoginPayload(BaseModel):
    """登录请求（与既有 `/api/auth/login` 同体）。"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="口令")


class UserCreate(BaseModel):
    """新建用户。"""
    username: str = Field(..., description="用户名（2-64 位安全字符）")
    password: str = Field(..., description="初始口令（≥12 位、≥3 类字符）")
    display_name: Optional[str] = Field(None, description="显示名")
    roles: Optional[List[str]] = Field(None, description="角色码数组（缺省为默认角色）")
    tenant_id: Optional[int] = Field(None, description="所属组织（缺省=当前会话组织）")
    company_ids: Optional[List[int]] = Field(None, description="可访问账套（数据权限）")
    phone: Optional[str] = Field(None, description="手机号（**出参一律脱敏**）")
    id_card: Optional[str] = Field(None, description="身份证号（**出参一律脱敏**）")
    bank_account: Optional[str] = Field(None, description="银行账号（**出参一律脱敏**）")


class UserUpdate(BaseModel):
    """修改用户（**全部可选**）。"""
    display_name: Optional[str] = None
    phone: Optional[str] = None
    id_card: Optional[str] = None
    bank_account: Optional[str] = None
    tenant_id: Optional[int] = None
    active: Optional[bool] = Field(None, description="启用/停用")
    roles: Optional[List[str]] = Field(None, description="角色码数组（覆盖式）")
    company_ids: Optional[List[int]] = Field(None, description="可访问账套（覆盖式）")


class RoleCreate(BaseModel):
    """新建自定义角色（内置角色不可重建）。"""
    code: str = Field(..., description="角色编码（英文/下划线）")
    name: str = Field(..., description="角色名称（中文）")
    permissions: List[str] = Field(default_factory=list, description="权限点数组")
    scope: Optional[str] = Field("tenant", description="范围：tenant / platform")
    description: Optional[str] = Field(None, description="说明")


# --------------------------------------------------------------------------
# 内部
# --------------------------------------------------------------------------
def _call(fn, *args, **kwargs):
    """业务异常 → HTTP 的**唯一转换点**在 `engine/api_common.call_boundary`；
    本函数只声明「本域该捕获哪一类业务异常」（SVC.AccessError）。"""
    return call_boundary(fn, *args, exc_types=(SVC.AccessError,), **kwargs)


# --------------------------------------------------------------------------
# 认证（与既有 `/api/auth/login` 共用 `security_web.login_handler`）
# --------------------------------------------------------------------------
@router.post("/auth/login", summary="登录（会话 + CSRF Cookie）")
async def login(payload: LoginPayload, request: Request):
    """登录。**注意**：本端点由**同一个** `security_web.login_handler` 处理
    （登录逻辑包括限流、会话、Cookie、留痕都在那里），此处只负责路由挂载。"""
    from security_web import login_handler                # noqa: PLC0415
    return await login_handler(request)


# --------------------------------------------------------------------------
# 用户
# --------------------------------------------------------------------------
@router.get("/users", summary="用户列表（组织隔离 + 敏感字段脱敏）")
def list_users(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    q: Optional[str] = None,
    tenant_id: Optional[int] = None,
    include_inactive: bool = True,
):
    session = _session(request)
    return _call(SVC.list_users, session, page=page, page_size=page_size, q=q,
                 tenant_id=tenant_id, include_inactive=include_inactive)


@router.post("/users", summary="新建用户", status_code=201)
def create_user(payload: UserCreate, request: Request):
    session = _session(request)
    return _call(SVC.create_user, session, payload.model_dump(), request=request)


@router.get("/users/{user_id}", summary="用户详情")
def get_user(user_id: int, request: Request):
    session = _session(request)
    return _call(SVC.get_user, session, user_id)


@router.put("/users/{user_id}", summary="修改用户（启停用/角色/组织/账套）")
def update_user(user_id: int, payload: UserUpdate, request: Request):
    session = _session(request)
    return _call(SVC.update_user, session, user_id,
                 payload.model_dump(exclude_unset=True), request=request)


# --------------------------------------------------------------------------
# 角色
# --------------------------------------------------------------------------
@router.get("/roles", summary="角色与权限字典")
def list_roles(request: Request):
    session = _session(request)
    return _call(SVC.list_roles, session)


@router.post("/roles", summary="新建自定义角色", status_code=201)
def create_role(payload: RoleCreate, request: Request):
    session = _session(request)
    return _call(SVC.create_custom_role, session, payload.model_dump(), request=request)


# --------------------------------------------------------------------------
# 审计日志
# --------------------------------------------------------------------------
@router.get("/audit-logs", summary="审计日志（组织隔离 + 脱敏）")
def list_audit_logs(
    request: Request,
    company_id: Optional[int] = None,
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    session = _session(request)
    return _call(SVC.list_audit_logs, session, company_id=company_id, action=action,
                 user_id=user_id, q=q, date_from=date_from, date_to=date_to,
                 page=page, page_size=page_size)


#: 供自检/文档引用：本模块对外提供的端点路径（**唯一权威**）
ENDPOINTS: tuple[str, ...] = (
    "POST /api/v1/auth/login",
    "GET /api/v1/users",
    "POST /api/v1/users",
    "GET /api/v1/users/{user_id}",
    "PUT /api/v1/users/{user_id}",
    "GET /api/v1/roles",
    "POST /api/v1/roles",
    "GET /api/v1/audit-logs",
)

__all__: List[str] = ["router", "page_router", "ENDPOINTS"]

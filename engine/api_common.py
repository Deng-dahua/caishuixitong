# -*- coding: utf-8 -*-
"""API 层公共边界（R-02，2026-10-17）—— **唯一权威**。

为什么要收敛
------------
阶段 5 冗余检测发现：`_session` 在 **10 个** API 文件各复制一份、`_call` **8 份**、
`_require_perm` **6 份**、`_request_perm` **6 份**。
这不是"代码不好看"的问题 —— 它是**权限口径漂移的机制**：
改一处忘一处，就会出现"某个接口用旧口径判权限"的情况（阶段 2 的 71 个权限缺口正是这么来的）。

本模块只提供四个边界函数，**不实现任何业务判定**：
  · `session_of`   —— 取会话，取不到 401（**不静默放行**）
  · `admin_of`     —— 仅管理员（401/403），依据 `session.is_admin`（服务端唯一权威）
  · `require_perm` —— 功能权限点校验，权威转发 `engine.rbac.require_permission`
  · `request_perm` —— 上者的 request 形态（保留既有错误文案，避免前端依赖被改）
  · `call_boundary`—— 业务异常 → HTTP 的**唯一转换点**

★ 为什么 `call_boundary` 要显式收 `exc_types`：
  各业务域有自己的异常类（`ProjectError`/`RiskError`/…），捕获哪一类是**必要的数据**，
  不能靠"捕获所有 Exception 再看有没有 status 属性"——那会把真正的 500 误转成 400，
  掩盖崩溃（本项目明令禁止静默吞异常）。所以：**逻辑一份，异常类型由调用方声明**。
"""
from __future__ import annotations

from typing import Any, Callable, Tuple

from fastapi import HTTPException, Request

__all__ = ["session_of", "admin_of", "require_perm", "request_perm", "call_boundary"]


def _raw_session(request: Request):
    return getattr(request.state, "auth", None)


def session_of(request: Request):
    """取当前会话。取不到 ⇒ 401（**不静默放行**）。"""
    auth = _raw_session(request)
    if auth is None:
        raise HTTPException(status_code=401, detail="未登录")
    return auth


def admin_of(request: Request):
    """仅管理员。401 未登录 / 403 非管理员。

    依据 `session.is_admin`（服务端唯一权威）——**不看角色名**，
    因为"谁是管理员"由 `security` 判定，前端与其它模块都只读这个布尔量。
    """
    auth = session_of(request)
    if not getattr(auth, "is_admin", False):
        raise HTTPException(status_code=403, detail="仅管理员可执行该操作")
    return auth


def require_perm(session, code: str):
    """功能权限点校验：不具备 ⇒ 403。

    权威：`engine.rbac.require_permission`（抛 `RbacError(403)`）。
    本函数**只做**「RbacError → HTTPException」的边界转换，**不自判角色**（否则即第二套口径）。
    """
    from engine.rbac import RbacError, require_permission   # noqa: PLC0415

    try:
        require_permission(session, code)
    except RbacError as exc:
        raise HTTPException(status_code=int(getattr(exc, "status", 403)),
                            detail=str(getattr(exc, "message", exc))) from exc
    return session


def request_perm(request: Request, perm: str):
    """`require_perm` 的 request 形态（401 优先于 403）。

    ★ 错误文案保持既有口径「缺少权限：%s」——**不改**，以免前端/测试依赖的提示变化。
    """
    auth = session_of(request)
    from engine.rbac import rbac_allows                      # noqa: PLC0415

    if not rbac_allows(auth, perm):
        raise HTTPException(status_code=403, detail="缺少权限：%s" % perm)
    return auth


def call_boundary(fn: Callable, *args, exc_types: Tuple[type, ...], **kwargs) -> Any:
    """调用业务函数，把声明的业务异常统一转成 HTTP（**唯一转换点**）。

    参数
    ----
    exc_types : 该业务域的业务异常类（可传元组）。**必须显式声明**，
                不要用 `(Exception,)` —— 那会把代码缺陷伪装成 4xx。
    """
    try:
        return fn(*args, **kwargs)
    except exc_types as exc:                                 # type: ignore[misc]
        status = int(getattr(exc, "status", 400) or 400)
        detail = getattr(exc, "message", None) or str(exc)
        raise HTTPException(status_code=status, detail=str(detail)) from exc

"""FastAPI request security policy kept separate from the legacy application."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.routing import Match
from request_context import reset_current_user_id, set_current_user_id

from security import (
    COOKIE_SECURE,
    SESSION_TTL_SECONDS,
    authenticate,
    create_session,
    csrf_is_valid,
    get_session,
    is_protected_static_path,
    is_public_path,
    login_is_allowed,
    normalize_client_ip,
    record_login_result,
    revoke_session,
    select_company,
)


_COMPANY_PATH = re.compile(r"^/api/companies/(\d+)(?:/|$)")


def _company_exists(company_id: int) -> bool:
    """账套是否真实存在于业务库（★ 2026-10-15 区分「陈旧引用」与「越权」）。

    数据清空/账套删除后，浏览器可能残留旧 company_id cookie ⇒ 那是陈旧引用，
    应忽略而非 403。判定异常（库不可读等）⇒ 返回 True（保守：仍按存在走
    越权 403 原逻辑，不放宽安全）。不缓存 ⇒ 新建账套立即可判，无安全窗口。"""
    import sqlite3  # noqa: PLC0415 — 本地库轻量读取
    try:
        from database import ACCOUNTING_DB  # noqa: PLC0415
        connection = sqlite3.connect(str(ACCOUNTING_DB), timeout=5)
        try:
            return connection.execute(
                "SELECT 1 FROM companies WHERE id=?", (int(company_id),)
            ).fetchone() is not None
        finally:
            connection.close()
    except Exception:
        return True
_ADMIN_PATHS = ("/api/system-logs",)


def _audit_auth(action: str, *, target: Any = "", detail: Any = "",
                user_id: Any = None, user_name: Any = None) -> None:
    """认证类留痕（薄转发 `engine.audit_trail.record`）。

    ★ 登录**发生在**鉴权之前（此时 `request.state.auth` 尚不存在），故用户身份由
      调用方显式传入；`record()` 自身保证"不抛、不静默" ⇒ 这里不再包 try/except。
    """
    try:
        from engine.audit_trail import record as _record     # noqa: PLC0415
    except Exception:                                        # noqa: BLE001
        return
    _record(action, target=target, detail=detail, user_id=user_id, user_name=user_name)


def _with_security_headers(response, request):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "img-src 'self' data: blob:; font-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
        "connect-src 'self' ws: wss:"
    )
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


async def enforce_request_security(request, call_next):
    path = request.url.path
    if is_protected_static_path(path):
        return JSONResponse({"ok": False, "message": "受保护的静态文件"}, status_code=403)
    if is_public_path(path):
        return _with_security_headers(await call_next(request), request)

    is_api = path.startswith("/api/")
    token = request.cookies.get("auth_token", "")
    fingerprint = request.headers.get("user-agent", "")[:256]
    session = get_session(token, client_fingerprint=fingerprint)
    if not session:
        response = (
            JSONResponse({"ok": False, "message": "请先登录", "code": 401}, status_code=401)
            if is_api
            else RedirectResponse("/login", status_code=302)
        )
        return _with_security_headers(response, request)
    request.state.auth = session

    if any(path.startswith(prefix) for prefix in _ADMIN_PATHS) and not session.is_admin:
        _audit_auth("auth.denied", target=path,
                    detail="仅管理员可访问（角色 %s）" % session.role,
                    user_id=session.user_id, user_name=session.username)
        return _with_security_headers(
            JSONResponse({"ok": False, "message": "仅管理员可执行此操作"}, status_code=403),
            request,
        )

    if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        if not csrf_is_valid(session, request.headers.get("X-CSRF-Token", "")):
            _audit_auth("auth.denied", target=path, detail="CSRF 校验失败",
                        user_id=session.user_id, user_name=session.username)
            return _with_security_headers(
                JSONResponse({"ok": False, "message": "CSRF 校验失败"}, status_code=403),
                request,
            )

    candidate_company_ids: set[int] = set()
    query_company = request.query_params.get("company_id")
    if query_company and query_company.isdigit():
        candidate_company_ids.add(int(query_company))
    path_match = _COMPANY_PATH.match(path)
    if path_match:
        candidate_company_ids.add(int(path_match.group(1)))
    for route in request.app.routes:
        try:
            match, child_scope = route.matches(request.scope)
        except (AttributeError, TypeError):
            continue
        if match is Match.FULL:
            route_company = child_scope.get("path_params", {}).get("company_id")
            if str(route_company or "").isdigit():
                candidate_company_ids.add(int(route_company))
            break

    if (
        request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
        and request.headers.get("content-type", "").lower().startswith("application/json")
    ):
        raw_body = await request.body()
        if raw_body and len(raw_body) <= 1024 * 1024:
            try:
                parsed = json.loads(raw_body)
                if isinstance(parsed, dict) and str(parsed.get("company_id", "")).isdigit():
                    candidate_company_ids.add(int(parsed["company_id"]))
            except (TypeError, ValueError):
                pass

        async def replay_body():
            return {"type": "http.request", "body": raw_body, "more_body": False}

        request._receive = replay_body

    selected_cookie = request.cookies.get("company_id", "")
    if selected_cookie.isdigit():
        candidate_company_ids.add(int(selected_cookie))
    # ★ 2026-10-15:不存在的账套=陈旧引用 ⇒ 忽略（不 403）；存在但无权 ⇒ 维持 403
    _stale_cookie = (
        selected_cookie.isdigit()
        and int(selected_cookie) > 0
        and not _company_exists(int(selected_cookie))
    )
    if any(
        company > 0
        and not session.can_access_company(company)
        and _company_exists(company)
        for company in candidate_company_ids
    ):
        _audit_auth("auth.denied", target=path,
                    detail="越权访问账套 %s" % sorted(candidate_company_ids),
                    user_id=session.user_id, user_name=session.username)
        return _with_security_headers(
            JSONResponse({"ok": False, "message": "无权访问该账套"}, status_code=403),
            request,
        )

    if (
        path == "/api/companies"
        and request.method.upper() != "GET"
        and not session.is_admin
    ):
        _audit_auth("auth.denied", target=path, detail="非管理员尝试管理账套",
                    user_id=session.user_id, user_name=session.username)
        return _with_security_headers(
            JSONResponse({"ok": False, "message": "仅管理员可管理账套"}, status_code=403),
            request,
        )

    # ★ 2026-10-15 账套概念退役（数据清空、项目自持企业身份）：
    #   原「未选账套 ⇒ HTML 页面一律 302 /select-company」守卫删除——
    #   手机号账号登录后直接进系统主页，不再被弹回账套选择页。
    #   账套越权校验（candidate_company_ids → 403）与 API 路径逻辑不受影响。
    user_context_token = set_current_user_id(session.user_id)
    try:
        response = _with_security_headers(await call_next(request), request)
        if _stale_cookie:
            # 清掉数据清空前残留的旧账套 cookie（下次请求起不再携带）
            response.delete_cookie("company_id", path="/")
        return response
    finally:
        reset_current_user_id(user_context_token)


async def login_handler(request):
    """登录**唯一实现**（P0-8 收敛）。

    ★ 此前只有 `/api/auth/login` 一个入口；P0-8 新增 `/api/v1/auth/login`（任务书路径）。
      两个入口**共用本函数**而不是各写一套 —— 否则「限流窗口 / 失败计数 / 会话与 CSRF
      Cookie 名 / 审计动作」会分叉成两套口径。路由差异只在 `main.py` / `rbac_api.py` 的注册处。
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "message": "请求格式错误"}, status_code=400)
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    client_ip = normalize_client_ip(request.client.host if request.client else "")
    allowed, retry_after = login_is_allowed(username, client_ip)
    if not allowed:
        _audit_auth("auth.login_failed", target=username,
                    detail="登录尝试过多，限流 %d 秒" % retry_after, user_name=username)
        return JSONResponse(
            {"ok": False, "message": f"登录尝试过多，请在 {retry_after} 秒后重试"},
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )
    user = authenticate(username, password)
    record_login_result(username, client_ip, bool(user))
    if not user:
        _audit_auth("auth.login_failed", target=username, detail="用户名或密码错误",
                    user_name=username)
        return JSONResponse({"ok": False, "message": "用户名或密码错误"}, status_code=401)
    fingerprint = request.headers.get("user-agent", "")[:256]
    token, csrf_token = create_session(user, client_fingerprint=fingerprint)
    from engine.rbac import session_permission_codes, session_role_codes   # noqa: PLC0415
    from security import SessionContext as _SC                              # noqa: PLC0415
    _probe = _SC(
        user_id=int(user["id"]), username=user["username"], role=user["role"],
        allowed_company_ids=frozenset(int(v) for v in (user.get("company_ids") or [])),
        selected_company_id=None, csrf_hash="", expires_at=0,
        tenant_id=user.get("tenant_id"),
    )
    _roles = sorted(session_role_codes(_probe))
    _perms = sorted(session_permission_codes(_probe))
    _audit_auth("auth.login", target=user["username"],
                detail="登录成功（角色：%s）" % ("、".join(_roles) or "无"),
                user_id=user["id"], user_name=user["username"])
    response = JSONResponse(
        {
            "ok": True,
            "username": user["username"],
            "display_name": user.get("display_name") or "",
            "role": user["role"],
            "roles": _roles,
            "permissions": _perms,
            "tenant_id": user.get("tenant_id"),
            "must_change_password": user["must_change_password"],
        }
    )
    for name, value, http_only in (
        ("auth_token", token, True),
        ("csrf_token", csrf_token, False),
    ):
        response.set_cookie(
            name,
            value,
            httponly=http_only,
            secure=COOKIE_SECURE,
            samesite="strict",
            max_age=SESSION_TTL_SECONDS,
            path="/",
        )
    return response


async def logout_handler(request):
    session = getattr(getattr(request, "state", None), "auth", None)
    if session is not None:
        _audit_auth("auth.logout", target=getattr(session, "username", ""),
                    detail="退出登录", user_id=getattr(session, "user_id", None),
                    user_name=getattr(session, "username", ""))
    revoke_session(request.cookies.get("auth_token", ""))
    response = JSONResponse({"ok": True})
    for name in ("auth_token", "csrf_token", "company_id", "user_name"):
        response.delete_cookie(name, path="/")
    return response


async def select_company_handler(data: dict, request):
    try:
        company_id = int(data.get("company_id", 0))
    except (TypeError, ValueError):
        raise HTTPException(400, "company_id 必须是整数")
    session = request.state.auth
    if not select_company(request.cookies.get("auth_token", ""), company_id, session):
        raise HTTPException(403, "无权访问该账套")
    response = JSONResponse({"ok": True})
    response.set_cookie(
        "company_id",
        str(company_id),
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )
    return response


def auth_me_handler(request):
    session = request.state.auth
    # P0-8：把「当前会话的角色与权限」一并发给前端 —— 菜单/按钮/数据可见性
    # 的唯一依据（前端**不得**自行推断角色，否则又是一处第二权威）。
    try:
        from engine.rbac import (                                    # noqa: PLC0415
            session_permission_codes, session_role_codes,
        )
        roles = sorted(session_role_codes(session))
        permissions = sorted(session_permission_codes(session))
    except Exception:                                                # noqa: BLE001
        roles, permissions = [], []
    return {
        "ok": True,
        "username": session.username,
        "role": session.role,
        "roles": roles,
        "permissions": permissions,
        "tenant_id": getattr(session, "tenant_id", None),
        "company_ids": sorted(session.allowed_company_ids),
        "selected_company_id": session.selected_company_id,
        "expires_at": session.expires_at,
    }

"""FastAPI request security policy kept separate from the legacy application."""
from __future__ import annotations

import json
import os
import re

from fastapi import HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.routing import Match

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
_ADMIN_PATHS = ("/api/apikey", "/api/system-logs")


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
        return _with_security_headers(
            JSONResponse({"ok": False, "message": "仅管理员可执行此操作"}, status_code=403),
            request,
        )

    if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        if not csrf_is_valid(session, request.headers.get("X-CSRF-Token", "")):
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
    if any(company > 0 and not session.can_access_company(company) for company in candidate_company_ids):
        return _with_security_headers(
            JSONResponse({"ok": False, "message": "无权访问该账套"}, status_code=403),
            request,
        )

    if (
        path == "/api/companies"
        and request.method.upper() != "GET"
        and not session.is_admin
    ):
        return _with_security_headers(
            JSONResponse({"ok": False, "message": "仅管理员可管理账套"}, status_code=403),
            request,
        )

    if not selected_cookie and not is_api and path not in {"/select-company", "/new-company"}:
        return _with_security_headers(RedirectResponse("/select-company", status_code=302), request)
    return _with_security_headers(await call_next(request), request)


async def login_handler(request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "message": "请求格式错误"}, status_code=400)
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    client_ip = normalize_client_ip(request.client.host if request.client else "")
    allowed, retry_after = login_is_allowed(username, client_ip)
    if not allowed:
        return JSONResponse(
            {"ok": False, "message": f"登录尝试过多，请在 {retry_after} 秒后重试"},
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )
    user = authenticate(username, password)
    record_login_result(username, client_ip, bool(user))
    if not user:
        return JSONResponse({"ok": False, "message": "用户名或密码错误"}, status_code=401)
    fingerprint = request.headers.get("user-agent", "")[:256]
    token, csrf_token = create_session(user, client_fingerprint=fingerprint)
    response = JSONResponse(
        {
            "ok": True,
            "username": user["username"],
            "role": user["role"],
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
    return {
        "ok": True,
        "username": session.username,
        "role": session.role,
        "company_ids": sorted(session.allowed_company_ids),
        "selected_company_id": session.selected_company_id,
        "expires_at": session.expires_at,
    }

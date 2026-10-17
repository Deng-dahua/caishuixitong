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


# ══════════════════════════════════════════════════════════════════════════════
# 旧路由写端点的**功能权限点**（MQ2-D1 扩展，2026-10-17）
# ══════════════════════════════════════════════════════════════════════════════
# 为什么需要本表：`_ADMIN_PATHS` 只管一个前缀；`/api/v1/*` 各端点在函数内自查；
# 而 `/api/*` 旧路由的写端点此前**只做认证 + 账套数据范围**，没有功能权限点 ——
# 任何登录用户可删除任意账套资料、发起分析、改纠正规则库、改全局巡检配置。
#
# 本表是旧路由写操作的**唯一权威**（与 `_ADMIN_PATHS` 同构、同处一文件）：
# 新增一个端点只需在此加一行，**不改任何逻辑分支**。
#
# · 未登记的写端点 = **有意放行**（公共路径 / 自我服务 / 405 墓桩），不是漏配；
#   `tests/test_legacy_route_permissions.py` 会核对"未登记集合"防漏配。
# · 权限点**必须**取自 `config/rbac.json::permissions`（不新增权限点、不扩模型）。
# · 只读方法（GET/HEAD/OPTIONS）不归本表管辖。
# · 键 = (HTTP 方法, FastAPI **路由模板**) —— 与源码装饰器写法逐字一致，
#   带路径参数的端点写 `{doc_id}` 这类模板（运行时按匹配到的 route 取模板）。
_LEGACY_WRITE_PERMS: tuple = (
    # ── 资料管理：上传 / 删除 / 清理 / OCR ──
    ("POST", "/api/tax-risk-docs/upload", "document.write"),
    ("POST", "/api/tax-risk-docs/batch-delete", "document.write"),
    ("DELETE", "/api/tax-risk-docs/{doc_id}", "document.write"),
    ("POST", "/api/tax-risk-docs/purge-pending", "document.write"),
    ("POST", "/api/tax-risk-docs/ocr", "document.write"),
    # 上轮已补的两处（2026-10-16）—— 纳入本表使其成为唯一权威，
    # main.py 函数体内的同名校验**保留**为冗余保险（双重检查、不重复实现）。
    ("DELETE", "/api/tax-risk-docs/clear-transfer", "document.write"),
    ("DELETE", "/api/tax-risk-docs/report", "report.generate"),
    # ── 分析任务：发起 / 续跑 / 同步兜底 / 政策影响检查 ──
    ("POST", "/api/tax-risk-docs/analyze-start", "analysis.run"),
    ("POST", "/api/tax-risk-docs/analyze-resume", "analysis.run"),
    ("POST", "/api/tax-risk-docs/analyze", "analysis.run"),
    ("POST", "/api/audit/analyze-async/{company_id}", "analysis.run"),
    ("POST", "/api/policy/check", "analysis.run"),
    # ── 风险复核：复核结论 / 预览修改效果 ──
    ("POST", "/api/tax-risk-docs/review", "risk.review"),
    ("POST", "/api/tax-risk-docs/review-single", "risk.review"),
    ("POST", "/api/tax-risk-docs/edit-preview", "risk.review"),
    # 反馈中「会改变结论」的两类（可 adjust 分数 / 会清分析缓存）归复核域。
    ("POST", "/api/audit/feedback", "risk.review"),
    ("POST", "/api/feedback", "risk.review"),
    # ── 整改：复核处置的延伸（高风险发现 → 整改任务）──
    ("POST", "/api/remediation/create", "risk.review"),
    ("PUT", "/api/remediation/{record_id}", "risk.review"),
    ("POST", "/api/remediation/batch-from-findings", "risk.review"),
    # ── 查阅：引擎问答（只读）──
    ("POST", "/api/tax-risk-docs/ask", "risk.view"),
    # ── 报告：工作底稿 / 交付 / LLM 叙事（后者有调用成本）──
    ("POST", "/api/workpaper/generate", "report.generate"),
    ("POST", "/api/compliance/rounds/{round_id}/deliver", "report.generate"),
    ("POST", "/api/audit/generate-narrative", "report.generate"),
    # ── 账套管理（`POST /api/companies` 见 _LEGACY_ADMIN_ONLY，与既有特例一致）──
    ("PUT", "/api/company", "project.write"),
    ("DELETE", "/api/companies/{company_id}", "project.write"),
    ("PUT", "/api/companies/{company_id}/industry", "project.write"),
    ("POST", "/api/companies/{company_id}/auto-detect-industry", "project.write"),
    ("POST", "/api/companies/{company_id}/online-lookup", "project.write"),
    # ── 规则库：解析 / 上传 / 改写 / 刷新 / 相关性检查（与 v1 `rule_versions_api` 同权限点）──
    ("POST", "/api/tax-risk-rules/parse-report", "ruleversion.manage"),
    ("POST", "/api/tax-risk-rules/upload-report", "ruleversion.manage"),
    ("POST", "/api/tax-risk-rules/promote-auto-rule", "ruleversion.manage"),
    ("POST", "/api/tax-risk-rules/update-rule", "ruleversion.manage"),
    ("POST", "/api/tax-risk-rules/batch-refresh", "ruleversion.manage"),
    ("POST", "/api/tax-risk-rules/batch-rewrite", "ruleversion.manage"),
    ("POST", "/api/tax-risk-rules/check-relevance", "ruleversion.manage"),
    # 反馈中「改纠正规则库」的四类（直接改引擎行为）归规则域。
    ("PUT", "/api/feedback/update", "ruleversion.manage"),
    ("DELETE", "/api/feedback/delete", "ruleversion.manage"),
    ("POST", "/api/feedback/restore", "ruleversion.manage"),
    ("POST", "/api/feedback/sync-modules", "ruleversion.manage"),
)

#: **仅管理员**可执行：没有对应业务权限点的**全局运维**端点（改全局状态，
#: 非某账套的业务数据）。复用既有 `session.is_admin` 语义，不新增权限点。
_LEGACY_ADMIN_ONLY: tuple = (
    # 与既有 `/api/companies` 写操作特例一致（既有特例保留，本表反映实际要求）
    ("POST", "/api/companies"),
    ("POST", "/api/industries/refresh-benchmarks"),
    ("DELETE", "/api/pipeline/history"),
    ("POST", "/api/patrol/config"),
    ("POST", "/api/patrol/run"),
    ("POST", "/api/notifications/config"),
    # AGI 遗留端点：子系统名义上移除，但代码仍在跑（`propagate-to-chains`
    # 真的会改全局税务合规指令/线索链/证据链/分析链）⇒ 必须限管理员。
    ("POST", "/api/agi/query"),
    ("POST", "/api/agi/self-check/{company_id}"),
    ("POST", "/api/agi/parallel/toggle"),
    ("POST", "/api/agi/sample"),
    ("POST", "/api/agi/predict"),
    ("POST", "/api/agi/rectify"),
    ("POST", "/api/agi/rectify/update"),
    ("POST", "/api/agi/propagate-to-chains"),
)

#: 哨兵：`_required_legacy_perm()` 用它表示"仅管理员"（而非某个权限点）。
_ADMIN_ONLY = "\x00admin-only"

_LEGACY_PERM_INDEX = {(m, p): perm for m, p, perm in _LEGACY_WRITE_PERMS}
_LEGACY_ADMIN_INDEX = frozenset(_LEGACY_ADMIN_ONLY)


def _required_legacy_perm(method: str, route_path: str):
    """旧路由写端点所需的权限。

    → 权限点字符串 = 需要该权限点；`_ADMIN_ONLY` = 仅管理员；`None` = **有意放行**。
    """
    spec = (str(method or "").upper(), str(route_path or ""))
    if spec in _LEGACY_ADMIN_INDEX:
        return _ADMIN_ONLY
    return _LEGACY_PERM_INDEX.get(spec)


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
    matched_route_path = ""
    for route in request.app.routes:
        try:
            match, child_scope = route.matches(request.scope)
        except (AttributeError, TypeError):
            continue
        if match is Match.FULL:
            route_company = child_scope.get("path_params", {}).get("company_id")
            if str(route_company or "").isdigit():
                candidate_company_ids.add(int(route_company))
            # 记下**路由模板**（含 `{doc_id}` 一类占位），供旧路由权限表查表用。
            matched_route_path = getattr(route, "path", "") or ""
            break

    # ── 旧路由写操作的**功能权限点**校验（MQ2-D1 扩展，2026-10-17）──────────────
    # 位置：认证 ✓ → _ADMIN_PATHS ✓ → CSRF ✓ → **本检查** → 账套数据范围 → 业务。
    # 只读方法不校验；`/api/v1/*` 走各自端点内的 `_require_perm`（不在本表内，
    # 故此处对其为 no-op）；未在表中登记的写端点 = 有意放行（公共/自我服务/墓桩）。
    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        _need = _required_legacy_perm(request.method.upper(), matched_route_path)
        if _need == _ADMIN_ONLY:
            if not session.is_admin:
                _audit_auth("auth.denied", target=path,
                            detail="仅管理员可执行（旧路由运维端点；角色 %s）" % session.role,
                            user_id=session.user_id, user_name=session.username)
                return _with_security_headers(
                    JSONResponse({"ok": False, "message": "仅管理员可执行此操作"}, status_code=403),
                    request,
                )
        elif _need:
            # 延迟导入：避免 security_web 与 engine 包的导入环
            # （与 `main.py::_require_perm` 同一权威 `engine.rbac.require_permission`）。
            from engine.rbac import RbacError, require_permission  # noqa: PLC0415
            try:
                require_permission(session, _need)
            except RbacError as exc:
                _audit_auth("auth.denied", target=path,
                            detail="缺少功能权限点 %s（角色 %s）" % (_need, session.role),
                            user_id=session.user_id, user_name=session.username)
                return _with_security_headers(
                    JSONResponse({"ok": False, "message": str(getattr(exc, "message", exc)),
                                  "required_permission": _need},
                                 status_code=int(getattr(exc, "status", 403))),
                    request,
                )

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


def _consent_required(username: str) -> bool:
    """当前用户是否还没确认最新版《数据处理告知》（E-01）。

    任何异常都按"未确认"返回，但**绝不让它影响登录本身**。
    """
    try:
        from engine import consent as _c          # noqa: PLC0415
        return not _c.is_accepted(username)
    except Exception:                             # noqa: BLE001
        return True


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
        # ★ 2026-10-17：显式**管理员标识**。服务端是"谁是管理员"的**唯一权威**
        #  （`session.is_admin`）；前端据此门控**管理员专用**入口（`data-perm-admin`），
        #  以免前端自行推断角色（那会形成第二权威）。
        #  背景：服务端有若干**仅管理员**端点（`security_web._LEGACY_ADMIN_ONLY`，如
        #  新建/删除账套、全局巡检配置），它们**不对应任何权限点**，故前端无法用
        #  `data-perm="<权限码>"` 表达，需要这个布尔量。
        "is_admin": bool(session.is_admin),
        # ★ E-01（2026-10-17）：知情同意状态。仅"告知"，**不阻断业务**
        #   （读不到同意表时按未确认处理，但不影响登录 —— 告知不该变成可用性故障）。
        "consent_required": _consent_required(session.username),
        "tenant_id": getattr(session, "tenant_id", None),
        "company_ids": sorted(session.allowed_company_ids),
        "selected_company_id": session.selected_company_id,
        "expires_at": session.expires_at,
    }

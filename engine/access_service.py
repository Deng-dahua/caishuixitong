# -*- coding: utf-8 -*-
"""权限、租户、审计的 **Service 层**（P0-8）。

分层（每层都有唯一权威，本模块只**薄转发**）：
  · 身份/会话/口令   → `security.py`（`create_user` / `set_user_active` / `users` 表）
  · 角色/权限/租户   → `engine/rbac.py`（`rbac_allows` / `assign_user_roles` / `visible_tenant_ids`）
  · 审计留痕        → `engine/audit_trail.py::record`（写入唯一入口）与 `list_records`（读取唯一入口）
  · 脱敏            → `engine/redaction.py`（「怎么脱」）+ `report_compliance.redaction_roles`（「是否脱」）
  · 时间            → `runtime_storage.now_cst()`

★ 本模块**不依赖 FastAPI**（函数接受可选 `request` 仅用于留痕取人），可直接被单元测试调用。

★ 边界：本模块只抛 `AccessError`（携带 HTTP 状态码），由 `rbac_api.py` **原样转发**为 HTTP
  响应；**绝不让 `ValueError`/`sqlite3.*` 穿透成 500**（P0-2~P0-7 各踩过一次）。

★ 租户隔离（本模块负责的**组织层**）：
  · `visible_tenant_ids(session)` 为 `None` ⇒ 超管，不限；
  · 否则只能看到**本租户**的用户与留痕（留痕按 `user_id ∈ 本租户成员` 过滤）。
  · ⚠ 业务数据（账套/资料/项目/风险/报告）的隔离仍由 `allowed_company_ids` 与项目成员承担
    （P0-1~P0-7 已落地并有测试），本模块**不另立第二套**业务数据隔离。
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Tuple

MAX_PAGE_SIZE = 200


class AccessError(Exception):
    """权限/租户业务异常：携带 HTTP 状态码，由 API 层原样转发。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = int(status)


# --------------------------------------------------------------------------
# 内部工具
# --------------------------------------------------------------------------
def _cstr(v: Any, *, maxlen: int = 200) -> str:
    return str(v or "").strip()[:maxlen]


def _rbac():
    from engine import rbac as _r                       # noqa: PLC0415
    return _r


def _page_args(page: Any, page_size: Any, *, default_size: int = 20) -> Tuple[int, int]:
    try:
        p = max(1, int(page))
    except (TypeError, ValueError):
        p = 1
    try:
        s = int(page_size)
    except (TypeError, ValueError):
        s = default_size
    return p, max(1, min(s, MAX_PAGE_SIZE))


def _audit(action: str, *, target: Any = "", company_id: Any = None,
           detail: Any = "", request: Any = None) -> None:
    """留痕唯一入口（薄转发 `audit_trail.record`；放在 **Service 层**而非 API 层，
    以保证"不经 HTTP 的调用（单元测试）也留痕"）。"""
    from engine.audit_trail import record as _rec        # noqa: PLC0415
    _rec(action, target=target, company_id=company_id, detail=detail, request=request)


def _require(session: Any, permission: str) -> None:
    """把 `rbac.RbacError` 收敛为本模块的 `AccessError`（边界唯一转换）。"""
    try:
        _rbac().require_permission(session, permission)
    except Exception as exc:                                 # noqa: BLE001
        if exc.__class__.__name__ == "RbacError":
            raise AccessError(str(getattr(exc, "message", exc)),
                              int(getattr(exc, "status", 403))) from exc
        raise


def _has_any(session: Any, permissions: Tuple[str, ...]) -> bool:
    """是否具备其中**任一**权限（用于"两种权限之一即可读"的字典类端点）。"""
    r = _rbac()
    return any(r.rbac_allows(session, p) for p in permissions)


def _visible_tenant(session: Any, tenant_id: Any) -> Optional[int]:
    """求本次查询生效的租户过滤值（**租户隔离的唯一判据**）。"""
    vis = _rbac().visible_tenant_ids(session)
    want = None
    if tenant_id not in (None, ""):
        try:
            want = int(tenant_id)
        except (TypeError, ValueError):
            raise AccessError("tenant_id 非法", 400)
    if vis is None:                                          # 超管：可任选租户
        return want
    if not vis:                                              # 无租户归属 ⇒ 看不到任何组织数据
        return -1
    if want is not None and want not in vis:
        raise AccessError("无权查看其他组织的用户（跨租户被拒绝）", 403)
    return want if want is not None else sorted(vis)[0]


def _visible_actor_ids(session: Any) -> Optional[FrozenSet[int]]:
    """可见留痕的**操作人**集合；`None` = 不限（超管）。

    留痕表（`audit_logs`）只有 `company_id`/`user_id`，没有租户列 ⇒ 用
    「**本租户成员的用户 id 集合**」作为租户边界（成员变更后边界自动跟随，
    不引入第二张映射表）。
    ★ `tenant_id IS NULL` 的账号（含 `APP_ADMIN_USERNAME` 引导超管）**归属默认组织**，
      只在查默认组织时并入 —— 与 `rbac.tenant_id_of()` 的回落口径一致；否则引导超管
      写下的留痕对任何人都不可见（"留了但没人看得到"）。
    """
    from security import list_users_detailed as _lu      # noqa: PLC0415
    r = _rbac()
    vis = r.visible_tenant_ids(session)
    if vis is None:
        return None
    default_tid = r.default_tenant_id()
    ids: set = set()
    for tid in vis:
        if int(tid) < 0:
            continue
        null_ok = (default_tid is not None and int(tid) == int(default_tid))
        ids.update(int(u["id"]) for u in _lu(tenant_id=int(tid), include_inactive=True,
                                             include_null_tenant=null_ok))
    return frozenset(ids)


def _redact_obj_for_session(session: Any, obj: Any, fields: Optional[List[str]] = None,
          counter: Optional[Dict[str, int]] = None) -> Any:
    """按会话角色脱敏（薄转发 `rbac.mask_for_session` / `redaction.redact_text`）。

    `fields` 给定时只对这些字段脱敏（"仅敏感列脱敏"，避免把整行文本都过一遍姓氏表）。
    其中 **整列就是人名**的字段（`config/rbac.json::name_fields`）走
    `redaction.mask_person_name_field`（字段级，无需称谓锚点）；其余走文本级正则。
    """
    r = _rbac()
    if not fields:
        return r.mask_for_session(session, obj, counter)
    from engine.redaction import (                          # noqa: PLC0415
        mask_person_name_field, redact_text, role_policy,
    )
    pol = role_policy(r.redaction_role_of(session))
    name_fields = set(r.rbac_config().get("name_fields") or [])
    for key in fields:
        val = obj.get(key)
        if not isinstance(val, str) or not val:
            continue
        if key in name_fields:
            if not pol.get("name"):
                continue
            new, n = mask_person_name_field(val)
            obj[key] = new
            if n and counter is not None:
                counter["name"] = counter.get("name", 0) + n
        else:
            obj[key] = redact_text(val, pol, counter)
    return obj


# --------------------------------------------------------------------------
# 用户
# --------------------------------------------------------------------------
def list_users(session: Any, *, page: Any = 1, page_size: Any = 20,
               q: Any = None, tenant_id: Any = None,
               include_inactive: bool = True) -> Dict[str, Any]:
    """用户列表（**租户隔离 + 敏感字段按角色脱敏**）。"""
    _require(session, "user.view")
    import security as _sec                              # noqa: PLC0415

    tid = _visible_tenant(session, tenant_id)
    p, size = _page_args(page, page_size)
    default_tid = _rbac().default_tenant_id()
    null_ok = (tid is not None and int(tid) >= 0 and default_tid is not None
               and int(tid) == int(default_tid))
    rows = _sec.list_users_detailed(tenant_id=tid, include_inactive=bool(include_inactive),
                                    limit=MAX_PAGE_SIZE * 5, offset=0,
                                    include_null_tenant=null_ok)
    kw = _cstr(q, maxlen=100)
    if kw:
        rows = [u for u in rows if kw in u["username"]
                or kw in (u.get("display_name") or "")]
    total = len(rows)
    start = (p - 1) * size
    page_rows = rows[start:start + size]

    cfg = _rbac().rbac_config()
    masked_fields = list(cfg.get("masked_user_fields") or [])
    counter: Dict[str, int] = {}
    items: List[Dict[str, Any]] = []
    for u in page_rows:
        item = dict(u)
        item["role_codes"] = _rbac().user_role_codes(u["id"])
        item = _redact_obj_for_session(session, item, fields=masked_fields, counter=counter)
        items.append(item)
    from engine.redaction import redaction_report       # noqa: PLC0415
    return {
        "items": items, "total": total, "page": p, "page_size": size,
        "pages": (total + size - 1) // size if total else 0,
        "redaction_role": _rbac().redaction_role_of(session),
        "redaction_note": redaction_report(_rbac().redaction_role_of(session), counter),
        "tenant_scope": (None if _rbac().visible_tenant_ids(session) is None else tid),
    }


def create_user(session: Any, payload: Dict[str, Any], *, request: Any = None) -> Dict[str, Any]:
    """新建用户（含角色指派与租户/账套归属）。"""
    _require(session, "user.manage")
    import security as _sec                              # noqa: PLC0415
    r = _rbac()

    username = _cstr(payload.get("username"), maxlen=64)
    password = str(payload.get("password") or "")
    if not username:
        raise AccessError("用户名不能为空", 400)
    if not password:
        raise AccessError("初始口令不能为空（至少 %d 位、三类字符）"
                          % _sec.PASSWORD_MIN_LENGTH, 400)

    role_codes = payload.get("roles")
    if role_codes in (None, ""):
        role_codes = [str(r.rbac_config().get("default_role") or "")]
    if isinstance(role_codes, str):
        role_codes = [x for x in role_codes.replace("，", ",").split(",") if x.strip()]
    role_codes = [str(x) for x in (role_codes or []) if str(x).strip()]
    if not role_codes:
        raise AccessError("至少指定一个角色", 400)

    tenant_id = payload.get("tenant_id")
    tid = _visible_tenant(session, tenant_id)
    if tid is not None and int(tid) < 0:
        raise AccessError("当前会话无所属组织，无法创建用户", 403)

    company_ids = payload.get("company_ids") or []
    if isinstance(company_ids, str):
        company_ids = [x for x in company_ids.replace("，", ",").split(",") if x.strip()]
    try:
        companies = [int(x) for x in company_ids]
    except (TypeError, ValueError):
        raise AccessError("company_ids 非法", 400)

    # 超管等价角色 ⇒ `users.role='admin'`（保持 `is_admin` 语义与既有守卫一致）
    legacy_role = "admin" if str(r.rbac_config().get("legacy_admin_role")) in role_codes else "user"
    try:
        uid = _sec.create_user(
            username, password, role=legacy_role, company_ids=companies,
            display_name=_cstr(payload.get("display_name"), maxlen=80),
            phone=_cstr(payload.get("phone"), maxlen=40),
            id_card=_cstr(payload.get("id_card"), maxlen=40),
            bank_account=_cstr(payload.get("bank_account"), maxlen=40),
            tenant_id=(int(tid) if tid is not None and int(tid) >= 0 else None),
        )
    except ValueError as exc:
        raise AccessError(str(exc), 400) from exc
    r.assign_user_roles(uid, role_codes, granted_by=getattr(session, "user_id", None))

    _audit("user.create", target=username, company_id=(companies[0] if companies else None),
           detail="新建用户「%s」（角色：%s；组织：%s；账套 %d 个）"
                  % (username, "、".join(role_codes), tid if tid is not None else "默认",
                     len(companies)),
           request=request)
    return get_user(session, uid)


def get_user(session: Any, user_id: Any) -> Dict[str, Any]:
    """单个用户（受租户隔离；敏感字段脱敏）。"""
    _require(session, "user.view")
    import security as _sec                              # noqa: PLC0415
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        raise AccessError("用户 ID 非法", 400)
    row = _sec.get_user(uid)
    if not row:
        raise AccessError("用户不存在", 404)
    vis = _rbac().visible_tenant_ids(session)
    if vis is not None:
        tid = row.get("tenant_id")
        if tid is None:
            tid = _rbac().default_tenant_id()
        if tid not in vis:
            raise AccessError("用户不存在或无权访问", 404)     # 404：不泄露存在性
    cfg = _rbac().rbac_config()
    item = dict(row)
    item["role_codes"] = _rbac().user_role_codes(uid)
    return _redact_obj_for_session(session, item,
                                    fields=list(cfg.get("masked_user_fields") or []))


def update_user(session: Any, user_id: Any, payload: Dict[str, Any], *,
                request: Any = None) -> Dict[str, Any]:
    """修改用户：显示名/联系方式/启停用/角色/组织/账套（**空 payload 直接返回当前态**）。"""
    _require(session, "user.manage")
    import security as _sec                              # noqa: PLC0415
    r = _rbac()
    current = get_user(session, user_id)
    uid = int(current["id"])
    changed: List[str] = []

    simple = {}
    for key in ("display_name", "phone", "id_card", "bank_account"):
        if key in payload and payload.get(key) is not None:
            simple[key] = _cstr(payload.get(key), maxlen=80)
    if "tenant_id" in payload and payload.get("tenant_id") is not None:
        tid = _visible_tenant(session, payload.get("tenant_id"))
        simple["tenant_id"] = (None if tid is None or int(tid) < 0 else int(tid))
    if "role" in payload and payload.get("role") is not None:
        simple["role"] = _cstr(payload.get("role"), maxlen=10)
    if simple:
        try:
            _sec.update_user_fields(uid, **simple)
        except ValueError as exc:
            raise AccessError(str(exc), 400) from exc
        changed.extend(sorted(simple.keys()))

    if "active" in payload and payload.get("active") is not None:
        active = bool(payload.get("active"))
        if not _sec.set_user_active(uid, active):
            raise AccessError("用户不存在", 404)
        changed.append("active=%s" % ("启用" if active else "停用"))

    if "roles" in payload and payload.get("roles") is not None:
        role_codes = payload.get("roles")
        if isinstance(role_codes, str):
            role_codes = [x for x in role_codes.replace("，", ",").split(",") if x.strip()]
        try:
            r.assign_user_roles(uid, [str(x) for x in (role_codes or [])],
                                granted_by=getattr(session, "user_id", None))
        except Exception as exc:                          # noqa: BLE001
            if exc.__class__.__name__ == "RbacError":
                raise AccessError(str(getattr(exc, "message", exc)),
                                  int(getattr(exc, "status", 400))) from exc
            raise
        changed.append("角色→%s" % "、".join(str(x) for x in (role_codes or [])))

    if "company_ids" in payload and payload.get("company_ids") is not None:
        ids = payload.get("company_ids")
        if isinstance(ids, str):
            ids = [x for x in ids.replace("，", ",").split(",") if x.strip()]
        try:
            _sec.set_user_companies(uid, [int(x) for x in ids])
        except (TypeError, ValueError):
            raise AccessError("company_ids 非法", 400)
        changed.append("账套授权 %d 个" % len(ids))

    if changed:
        _audit("user.update", target=current["username"],
               detail="修改用户「%s」：%s" % (current["username"], "；".join(changed)),
               request=request)
    out = get_user(session, uid)
    out["changed"] = changed
    return out


# --------------------------------------------------------------------------
# 角色
# --------------------------------------------------------------------------
def list_roles(session: Any) -> Dict[str, Any]:
    """角色与权限字典（`user.view` 或 `role.manage` 之一即可读）。"""
    if not _has_any(session, ("user.view", "role.manage")):
        raise AccessError("无权查看角色配置（需要权限：user.view 或 role.manage）", 403)
    data = _rbac().rbac_metadata()
    data["can_manage"] = _rbac().rbac_allows(session, "role.manage")
    data["current_roles"] = sorted(_rbac().session_role_codes(session))
    data["current_permissions"] = sorted(_rbac().session_permission_codes(session))
    return data


def create_custom_role(session: Any, payload: Dict[str, Any], *,
                       request: Any = None) -> Dict[str, Any]:
    """新建自定义角色（内置角色不可重建）。"""
    _require(session, "role.manage")
    r = _rbac()
    code = _cstr(payload.get("code"), maxlen=40)
    name = _cstr(payload.get("name"), maxlen=40)
    if not code:
        raise AccessError("角色编码不能为空", 400)
    if not name:
        raise AccessError("角色名称不能为空", 400)
    perms = payload.get("permissions")
    if isinstance(perms, str):
        perms = [x for x in perms.replace("，", ",").split(",") if x.strip()]
    try:
        created = r.create_role(code, name, [str(x) for x in (perms or [])],
                               scope=_cstr(payload.get("scope"), maxlen=20) or "tenant",
                               description=_cstr(payload.get("description"), maxlen=200))
    except Exception as exc:                              # noqa: BLE001
        if exc.__class__.__name__ == "RbacError":
            raise AccessError(str(getattr(exc, "message", exc)),
                              int(getattr(exc, "status", 400))) from exc
        raise
    _audit("role.create", target=code,
           detail="新建自定义角色「%s」（权限 %d 项）" % (name, len(created["permissions"])),
           request=request)
    return created


# --------------------------------------------------------------------------
# 审计日志
# --------------------------------------------------------------------------
def list_audit_logs(session: Any, *, company_id: Any = None, action: Any = None,
                    user_id: Any = None, q: Any = None,
                    date_from: Any = None, date_to: Any = None,
                    page: Any = 1, page_size: Any = 50) -> Dict[str, Any]:
    """审计日志（**租户隔离**：非超管只看本租户成员的留痕；目标/说明按角色脱敏）。"""
    _require(session, "audit.view")
    from engine.audit_trail import ACTIONS, ACTION_CN, count as _count, list_records as _list  # noqa: PLC0415
    r = _rbac()

    cid: Optional[int] = None
    if company_id not in (None, ""):
        try:
            cid = int(company_id)
        except (TypeError, ValueError):
            raise AccessError("company_id 非法", 400)
        if not session.can_access_company(cid):
            raise AccessError("无权查看该账套的审计日志", 403)

    actor_ids = _visible_actor_ids(session)
    uid_filter: Any = user_id
    if actor_ids is not None and user_id not in (None, ""):
        try:
            if int(user_id) not in actor_ids:
                return {"items": [], "total": 0, "page": 1, "page_size": 0, "pages": 0,
                        "actions": [{"value": a, "label": ACTION_CN.get(a, a)} for a in ACTIONS],
                        "note": "该操作人不在当前组织范围内"}
        except (TypeError, ValueError):
            raise AccessError("user_id 非法", 400)
    p, size = _page_args(page, page_size, default_size=50)
    uid_int = None
    if uid_filter not in (None, ""):
        try:
            uid_int = int(uid_filter)
        except (TypeError, ValueError):
            raise AccessError("user_id 非法", 400)

    if actor_ids is None:
        total = _count(company_id=cid, action=action, user_id=uid_int,
                       q=q, date_from=date_from, date_to=date_to)
        rows = _list(company_id=cid, action=action, user_id=uid_int,
                     q=q, date_from=date_from, date_to=date_to,
                     limit=size, offset=(p - 1) * size)
    else:
        # 非超管：先按条件全量取回，再按「本租户成员」裁剪（成员集合通常很小）
        all_rows = _list(company_id=cid, action=action, user_id=uid_int, q=q,
                         date_from=date_from, date_to=date_to, limit=5000, offset=0)
        kept = [x for x in all_rows if x.get("user_id") in actor_ids]
        total = len(kept)
        rows = kept[(p - 1) * size:(p - 1) * size + size]

    cfg = r.rbac_config()
    masked = list(cfg.get("masked_audit_fields") or [])
    counter: Dict[str, int] = {}
    from engine.redaction import redaction_report           # noqa: PLC0415
    items = [_redact_obj_for_session(session, dict(x), fields=masked, counter=counter)
                 for x in rows]
    return {
        "items": items, "total": total, "page": p, "page_size": size,
        "pages": (total + size - 1) // size if total else 0,
        "actions": [{"value": a, "label": ACTION_CN.get(a, a)} for a in ACTIONS],
        "redaction_role": r.redaction_role_of(session),
        "redaction_note": redaction_report(r.redaction_role_of(session), counter),
    }


__all__ = [
    "AccessError", "MAX_PAGE_SIZE",
    "list_users", "create_user", "get_user", "update_user",
    "list_roles", "create_custom_role", "list_audit_logs",
]

# -*- coding: utf-8 -*-
"""稽查项目（P0-1）**Service 层**：CRUD / 成员 / 状态机 / 权限 / 审计。

分层（三处唯一权威，均**薄转发**，勿另立第二套）：
  · 表结构与状态机  → `engine/project_store.py`（`ensure_schema` / `STATUSES` / `STATUS_FLOW`）
  · 审计留痕        → `engine/audit_trail.py::record`（本模块**只调用**，不自建写库）
  · 时间            → `runtime_storage.now_cst()`（北京时间唯一权威）

权限模型（三层，任务书要求；**单一实现**在本模块 `_visible_sql` / `_can_write`）：
  ① **租户隔离**：`project.company_id` 必须 ∈ `session.allowed_company_ids`（admin 恒真）
     —— 跨租户**一律不可见**（返回 404 而非 403，**不泄露对象是否存在**）；
  ② **可见**：admin OR 同租户（同租户内团队协作，成员用于区分**写**权限）；
  ③ **可写**（改 / 删 / 加成员）：admin OR 项目 `owner` OR 成员且角色 ∈ `WRITE_ROLES`。
     ⚠ 非成员的同租户用户 = **只读**（等效 viewer），**不得**因"同公司"就获得写权限。

★ 本模块**不依赖 FastAPI**：所有函数接受可选 `engine`，故可被单元测试直接调用
  （满足任务书「单元测试：Service 层 CRUD」无需启服务）。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

from engine.project_store import (                       # noqa: PLC0415
    CODE_PREFIX, ROLE_CN, ROLES, STATUS_CN, STATUS_FLOW, STATUSES, WRITE_ROLES,
    ensure_schema,
)


class ProjectError(Exception):
    """业务异常：携带 HTTP 状态码，由 API 层**原样转发**（不在 Service 层造 HTTP 语义）。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = int(status)


# --------------------------------------------------------------------------
# 内部工具
# --------------------------------------------------------------------------
def _engine_or_default(engine):
    if engine is not None:
        return engine
    from database import engine as _engine            # noqa: PLC0415
    return _engine


def _now() -> str:
    from runtime_storage import now_cst               # noqa: PLC0415
    return now_cst()


def _is_admin(session: Any) -> bool:
    return bool(getattr(session, "is_admin", False))


def _allowed_company_ids(session: Any) -> Tuple[int, ...]:
    ids = getattr(session, "allowed_company_ids", ()) or ()
    out: List[int] = []
    for x in ids:
        try:
            out.append(int(x))
        except Exception:                             # noqa: BLE001
            continue
    return tuple(out)


def _visible_sql(session: Any, alias: str = "p") -> Tuple[str, Dict[str, Any]]:
    """**租户隔离的唯一实现**：返回 (SQL 片段, 绑定参数)。

    admin ⇒ 无限制。
    ★ 2026-10-15 口径更新（账套退役、项目自持企业身份）：
      普通用户可见 = **授权账套下的项目 ∪ 我创建的（owner）∪ 我是成员的项目**。
      原「无账套授权 ⇒ 1=0」是账套时代口径——手机号用户授权清单为空，
      导致 create 后按可见性回读自己刚建的项目 ⇒ 404「项目不存在或无权访问」。
    ⚠ 仍不得用「无归属=公共」顶替：`company_id IS NULL` 的项目只对
      owner/成员可见，无关用户依旧不可见（不泄露存在性）。
    """
    if _is_admin(session):
        return "1=1", {}
    ids = _allowed_company_ids(session)
    uid = getattr(session, "user_id", None)
    clauses: List[str] = []
    params: Dict[str, Any] = {}
    if ids:
        keys = []
        for i, cid in enumerate(ids):
            k = "_cid%d" % i
            keys.append(":" + k)
            params[k] = cid
        clauses.append("%s.company_id IN (%s)" % (alias, ", ".join(keys)))
    if uid:
        params["_uid"] = int(uid)
        clauses.append("%s.owner_id = :_uid" % alias)
        clauses.append(
            "EXISTS (SELECT 1 FROM project_members pm "
            "WHERE pm.project_id = %s.id AND pm.user_id = :_uid)" % alias
        )
    if not clauses:                                   # 无 uid 且无授权（理论不可达）⇒ 兜底
        return "1=0", {}
    return "(" + " OR ".join(clauses) + ")", params


def _row_to_project(row: Any) -> Dict[str, Any]:
    m = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    raw_scopes = m.get("tax_scopes")
    scopes: List[str] = []
    if raw_scopes:
        try:
            v = json.loads(raw_scopes)
            if isinstance(v, list):
                scopes = [str(x) for x in v]
        except Exception:                             # noqa: BLE001
            scopes = [s for s in str(raw_scopes).split(",") if s]
    m["tax_scopes"] = scopes
    m["status_cn"] = STATUS_CN.get(str(m.get("status")), str(m.get("status") or ""))
    return m


def _row_to_member(row: Any) -> Dict[str, Any]:
    m = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    m["role_cn"] = ROLE_CN.get(str(m.get("role")), str(m.get("role") or ""))
    return m


def _audit(action: str, *, target: Any, company_id: Any, detail: Any,
           request: Any = None) -> None:
    """留痕**唯一入口**（薄转发 `audit_trail.record`）。

    ★ 不放 `try/except: pass`：`audit_trail.record` 自身已保证"不抛、不静默"，
      外层再吞一次等于把留痕失败藏起来。
    """
    from engine.audit_trail import record as _record   # noqa: PLC0415
    _record(action, target=target, company_id=company_id, detail=detail, request=request)


# --------------------------------------------------------------------------
# 权限
# --------------------------------------------------------------------------
def _member_role(conn, project_id: int, user_id: Any) -> Optional[str]:
    if user_id is None:
        return None
    from sqlalchemy import text as _text              # noqa: PLC0415
    r = conn.execute(_text(
        "SELECT role FROM project_members WHERE project_id=:p AND user_id=:u"
    ), {"p": int(project_id), "u": int(user_id)}).first()
    return str(r[0]) if r else None


def _can_write(conn, session: Any, project_row: Any) -> bool:
    if _is_admin(session):
        return True
    if int(getattr(session, "user_id", 0) or 0) == int(project_row["owner_id"] or 0) \
            and project_row["owner_id"]:
        return True
    role = _member_role(conn, project_row["id"], getattr(session, "user_id", None))
    return bool(role and role in WRITE_ROLES)


def _fetch_visible(conn, session: Any, project_id: Any, *, for_write: bool = False) -> Dict[str, Any]:
    """取一条**当前用户可见**的项目行；不可见 ⇒ 404（不泄露存在性）。

    ★ 返回**普通 dict**（不是 SQLAlchemy `Row`）：`Row` 不支持 `row["status"]` 这种
      字符串索引（实测 `TypeError: tuple indices must be integers or slices, not str`），
      而本模块后续一律用 `row["字段"]` 取值 ⇒ 在**这一处**统一转换，调用方不必各写各的。
    """
    from sqlalchemy import text as _text              # noqa: PLC0415
    try:
        pid = int(project_id)
    except Exception:                                 # noqa: BLE001
        raise ProjectError("项目 ID 非法", 400)
    vis, params = _visible_sql(session)
    params["_pid"] = pid
    row = conn.execute(_text(
        "SELECT * FROM projects p WHERE p.id=:_pid AND %s" % vis), params).first()
    if row is None:
        raise ProjectError("项目不存在或无权访问", 404)
    rec = dict(row._mapping)
    if for_write and not _can_write(conn, session, rec):
        raise ProjectError("无权修改该项目（仅创建人/成员/admin 可写）", 403)
    return rec


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------
def _clean_str(v: Any, *, maxlen: int = 200) -> str:
    return str(v or "").strip()[:maxlen]


def _normalize_scopes(v: Any) -> str:
    """税种范围归一为 JSON 数组字符串（列表/逗号串/None 均接受）。"""
    items: List[str] = []
    if v is None:
        items = []
    elif isinstance(v, (list, tuple, set)):
        items = [_clean_str(x, maxlen=40) for x in v]
    else:
        items = [_clean_str(x, maxlen=40) for x in str(v).replace("，", ",").split(",")]
    items = [x for x in items if x]
    # 去重保序
    seen: set = set()
    uniq: List[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return json.dumps(uniq, ensure_ascii=False)


def _validate_status(status: Any, *, default: Optional[str] = None) -> str:
    s = _clean_str(status, maxlen=20) or (default or "")
    if s not in STATUSES:
        raise ProjectError(
            "状态非法：%s（合法值：%s）" % (s or "(空)", "、".join(STATUS_CN.values())), 400)
    return s


def _validate_role(role: Any) -> str:
    r = _clean_str(role, maxlen=20) or "member"
    if r not in ROLES:
        raise ProjectError(
            "角色非法：%s（合法值：%s）" % (r, "、".join(ROLE_CN.values())), 400)
    return r


def _validate_period(start: Any, end: Any) -> Tuple[str, str]:
    a, b = _clean_str(start, maxlen=20), _clean_str(end, maxlen=20)
    if a and b and a > b:
        raise ProjectError("稽查期间起止颠倒：%s > %s" % (a, b), 400)
    return a, b


# --------------------------------------------------------------------------
# 编号
# --------------------------------------------------------------------------
def _next_code(conn, company_id: Any) -> str:
    """生成可读项目编号 `PJ-YYYYMMDD-####`（同公司同日顺延，冲突则继续顺延）。"""
    from sqlalchemy import text as _text              # noqa: PLC0415
    day = _now()[:10].replace("-", "")
    base = "%s-%s-" % (CODE_PREFIX, day)
    row = conn.execute(_text(
        "SELECT COUNT(*) FROM projects WHERE code LIKE :p"), {"p": base + "%"}).first()
    n = int(row[0] or 0) + 1
    while True:
        code = "%s%04d" % (base, n)
        dup = conn.execute(_text(
            "SELECT 1 FROM projects WHERE code=:c"), {"c": code}).first()
        if not dup:
            return code
        n += 1


# --------------------------------------------------------------------------
# 审计动作（★ 唯一权威在 `engine/audit_trail.py::ACTIONS`；此处仅引用常量名，防拼错）
# --------------------------------------------------------------------------
ACT_PROJECT_CREATE = "project.create"
ACT_PROJECT_UPDATE = "project.update"
ACT_PROJECT_DELETE = "project.delete"
ACT_PROJECT_MEMBER = "project.member_change"


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------
def create_project(payload: Dict[str, Any], session: Any, *, engine=None,
                   request: Any = None) -> Dict[str, Any]:
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415

    name = _clean_str(payload.get("name"), maxlen=200)
    if not name:
        raise ProjectError("企业名称不能为空", 400)
    status = _validate_status(payload.get("status"), default="draft")
    if status != "draft":
        raise ProjectError("新建项目状态只能为「草稿」", 400)
    p_start, p_end = _validate_period(payload.get("period_start"), payload.get("period_end"))

    # 租户归属：显式传入优先；否则用会话选中的账套；两者皆无 ⇒ 拒绝（**不得**用 0 冒充）
    cid = payload.get("company_id")
    if cid in (None, ""):
        cid = getattr(session, "selected_company_id", None)
    cid_int: Optional[int] = None
    if cid not in (None, ""):
        try:
            cid_int = int(cid)
        except Exception:                             # noqa: BLE001
            raise ProjectError("company_id 非法", 400)
    if cid_int is not None and not _is_admin(session) \
            and cid_int not in _allowed_company_ids(session):
        raise ProjectError("无权在该账套下创建项目（跨租户被拒绝）", 403)

    # ★ 2026-10-14 二次调整（用户裁定，账套概念随数据清空退役）：
    # **项目自持企业身份** —— 新建只收「公司名称 + 统一社会信用代码」两项；
    # 行业/地区/期间等信息由**自动分析确定**（分析完成后回填，后续一轮实现），
    # 不再从 companies 带出。若显式传入 company_id 仍按原逻辑做越权校验（兼容）。
    _tid = _clean_str(payload.get("taxpayer_id"), maxlen=40)
    if len(_tid) != 18:
        raise ProjectError("统一社会信用代码必须为 18 位", 400)
    payload["taxpayer_id"] = _tid

    ts = _now()
    uid = getattr(session, "user_id", None)
    uname = _clean_str(getattr(session, "username", ""), maxlen=80)
    with eng.begin() as conn:
        code = _clean_str(payload.get("code"), maxlen=40) or _next_code(conn, cid_int)
        row = conn.execute(_text(
            "INSERT INTO projects (company_id, code, name, taxpayer_id, industry, region, "
            " period_start, period_end, tax_scopes, status, remark, owner_id, owner_name, "
            " created_at, updated_at) "
            "VALUES (:cid,:code,:name,:tid,:ind,:reg,:ps,:pe,:ts,:st,:rm,:oid,:onm,:ca,:ua) "
            "RETURNING id"
        ), {
            "cid": cid_int, "code": code, "name": name,
            "tid": _clean_str(payload.get("taxpayer_id"), maxlen=40),
            "ind": _clean_str(payload.get("industry"), maxlen=60),
            "reg": _clean_str(payload.get("region"), maxlen=60),
            "ps": p_start, "pe": p_end,
            "ts": _normalize_scopes(payload.get("tax_scopes")),
            "st": status, "rm": _clean_str(payload.get("remark"), maxlen=500),
            "oid": uid, "onm": uname, "ca": ts, "ua": ts,
        }).first()
        pid = int(row[0])
        # ★ 创建人自动成为 owner 成员（否则"创建人可写"这条就只能靠 owner_id 单点，成员列表会缺人）
        conn.execute(_text(
            "INSERT OR IGNORE INTO project_members (project_id, user_id, user_name, role, created_at) "
            "VALUES (:p,:u,:n,:r,:ts)"
        ), {"p": pid, "u": uid, "n": uname, "r": "owner", "ts": ts})
    _audit(ACT_PROJECT_CREATE, target=code or name, company_id=cid_int,
           detail="新建稽查项目「%s」（状态：%s）" % (name, STATUS_CN[status]), request=request)
    return get_project(pid, session, engine=eng)


def list_projects(session: Any, *, engine=None, q: Any = None, status: Any = None,
                  industry: Any = None, company_id: Any = None,
                  page: Any = 1, page_size: Any = 20,
                  sort: Any = "updated_at", order: Any = "desc") -> Dict[str, Any]:
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415

    vis, params = _visible_sql(session)
    where = [vis]
    kw = _clean_str(q, maxlen=100)
    if kw:
        where.append("(p.name LIKE :kw OR p.code LIKE :kw OR p.taxpayer_id LIKE :kw)")
        params["kw"] = "%" + kw + "%"
    st = _clean_str(status, maxlen=20)
    if st:
        where.append("p.status = :st")
        params["st"] = _validate_status(st)
    ind = _clean_str(industry, maxlen=60)
    if ind:
        where.append("p.industry = :ind")
        params["ind"] = ind
    cid = _clean_str(company_id, maxlen=20) if company_id not in (None, "") else ""
    if cid:
        try:
            where.append("p.company_id = :cid")
            params["cid"] = int(cid)
        except Exception:                             # noqa: BLE001
            raise ProjectError("company_id 非法", 400)

    # 排序：白名单化（**禁**把用户输入直接拼进 ORDER BY）
    cols = {"updated_at": "p.updated_at", "created_at": "p.created_at",
            "name": "p.name", "status": "p.status", "code": "p.code"}
    order_by = cols.get(_clean_str(sort, maxlen=20), "p.updated_at")
    direction = "ASC" if _clean_str(order, maxlen=4).lower() == "asc" else "DESC"

    try:
        page_i = max(1, int(page))
    except Exception:                                 # noqa: BLE001
        page_i = 1
    try:
        size_i = int(page_size)
    except Exception:                                 # noqa: BLE001
        size_i = 20
    size_i = max(1, min(size_i, 200))
    params["_limit"], params["_offset"] = size_i, (page_i - 1) * size_i

    clause = " AND ".join(where)
    with eng.connect() as conn:
        total = int(conn.execute(_text(
            "SELECT COUNT(*) FROM projects p WHERE " + clause), params).first()[0] or 0)
        rows = conn.execute(_text(
            "SELECT * FROM projects p WHERE " + clause +
            " ORDER BY %s %s, p.id DESC LIMIT :_limit OFFSET :_offset"
            % (order_by, direction)), params).all()
    items = [_row_to_project(r) for r in rows]
    pages = (total + size_i - 1) // size_i if total else 0
    return {"items": items, "total": total, "page": page_i,
            "page_size": size_i, "pages": pages}


def get_project(project_id: Any, session: Any, *, engine=None,
                with_members: bool = True, with_logs: bool = True) -> Dict[str, Any]:
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415
    with eng.connect() as conn:
        row = _fetch_visible(conn, session, project_id)
        out = _row_to_project(row)
        if with_members:
            out["members"] = [_row_to_member(r) for r in conn.execute(_text(
                "SELECT * FROM project_members WHERE project_id=:p ORDER BY "
                "CASE role WHEN 'owner' THEN 0 WHEN 'reviewer' THEN 1 WHEN 'member' THEN 2 "
                "ELSE 3 END, id"), {"p": out["id"]}).all()]
        if with_logs:
            out["logs"] = _project_logs(conn, out["id"], limit=50)
        out["can_write"] = _can_write(conn, session, row)
        out["allowed_next_status"] = list(STATUS_FLOW.get(str(out.get("status")), ()))
        out["allowed_next_status_cn"] = [STATUS_CN.get(s, s)
                                         for s in out["allowed_next_status"]]
    return out


def _project_logs(conn, project_id: int, *, limit: int = 50) -> List[Dict[str, Any]]:
    """项目操作日志：读 `audit_logs` 中 `target` 指向本项目编号的记录（**薄读**，不另建日志表）。"""
    from sqlalchemy import text as _text              # noqa: PLC0415
    prow = conn.execute(_text("SELECT code, name FROM projects WHERE id=:p"),
                        {"p": int(project_id)}).first()
    if not prow:
        return []
    code = str(prow[0] or "")
    if not code:
        return []
    rows = conn.execute(_text(
        "SELECT created_at, user_name, action, detail FROM audit_logs "
        "WHERE target=:c AND action LIKE 'project.%' "
        "ORDER BY id DESC LIMIT :n"), {"c": code, "n": int(limit)}).all()
    from engine.audit_trail import action_cn as _cn    # noqa: PLC0415
    return [{"at": r[0], "by": r[1], "action": r[2], "action_cn": _cn(r[2]),
             "detail": r[3]} for r in rows]


def update_project(project_id: Any, payload: Dict[str, Any], session: Any, *,
                   engine=None, request: Any = None) -> Dict[str, Any]:
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415

    sets, params = [], {"_pid": int(project_id)}
    with eng.begin() as conn:
        row = _fetch_visible(conn, session, project_id, for_write=True)
        old_status = str(row["status"])

        # ★ 2026-10-14 二次调整：项目自持企业身份（不再有账套覆盖回填）；
        # 行业等由自动分析确定，前端表单只提交 name/taxpayer_id。
        if "taxpayer_id" in payload and payload.get("taxpayer_id") is not None \
                and len(_clean_str(payload.get("taxpayer_id"), maxlen=40)) != 18:
            raise ProjectError("统一社会信用代码必须为 18 位", 400)
        simple = (("name", 200), ("taxpayer_id", 40), ("industry", 60),
                  ("region", 60), ("remark", 500), ("code", 40))
        for key, mx in simple:
            if key in payload and payload.get(key) is not None:
                if key == "name" and not _clean_str(payload.get(key)):
                    raise ProjectError("企业名称不能为空", 400)
                sets.append("%s=:%s" % (key, key))
                params[key] = _clean_str(payload.get(key), maxlen=mx)
        if "period_start" in payload or "period_end" in payload:
            ps = payload.get("period_start", row["period_start"])
            pe = payload.get("period_end", row["period_end"])
            ps, pe = _validate_period(ps, pe)
            sets += ["period_start=:ps", "period_end=:pe"]
            params["ps"], params["pe"] = ps, pe
        if "tax_scopes" in payload and payload.get("tax_scopes") is not None:
            sets.append("tax_scopes=:ts")
            params["ts"] = _normalize_scopes(payload.get("tax_scopes"))
        # ── 状态迁移：**必须**合法（非法即 400，不静默接受）──
        if payload.get("status") not in (None, ""):
            new_status = _validate_status(payload.get("status"))
            if new_status != old_status:
                if new_status not in STATUS_FLOW.get(old_status, ()):
                    raise ProjectError(
                        "非法状态迁移：%s → %s（允许：%s）" % (
                            STATUS_CN.get(old_status, old_status),
                            STATUS_CN.get(new_status, new_status),
                            "、".join(STATUS_CN.get(s, s)
                                      for s in STATUS_FLOW.get(old_status, ())) or "无（终态）"),
                        400)
                sets.append("status=:st")
                params["st"] = new_status
        if not sets:
            return get_project(project_id, session, engine=eng)
        sets.append("updated_at=:_ua")
        params["_ua"] = _now()
        conn.execute(_text("UPDATE projects SET %s WHERE id=:_pid" % ", ".join(sets)), params)

    detail = "更新项目字段：%s" % "、".join(
        s.split("=")[0] for s in sets if not s.startswith("updated_at"))
    if payload.get("status") not in (None, ""):
        detail += "｜状态 %s → %s" % (STATUS_CN.get(old_status, old_status),
                                      STATUS_CN.get(str(payload.get("status")), ""))
    _audit(ACT_PROJECT_UPDATE, target=str(row["code"] or row["name"]),
           company_id=row["company_id"], detail=detail, request=request)
    return get_project(project_id, session, engine=eng)


def delete_project(project_id: Any, session: Any, *, engine=None,
                   request: Any = None) -> Dict[str, Any]:
    """删除项目：删 `projects` 行 + 其 `project_members` 行（**成员是项目的从属物**）。

    ⚠ 只删本项目自身数据；**不触碰**账套（`companies`）及其资料/报告派生物
      —— 那些的删除唯一权威是 `main.purge_company_analysis_artifacts`。
    """
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415
    with eng.begin() as conn:
        row = _fetch_visible(conn, session, project_id, for_write=True)
        nm, code, cid = str(row["name"]), str(row["code"] or ""), row["company_id"]
        conn.execute(_text("DELETE FROM project_members WHERE project_id=:p"),
                     {"p": int(row["id"])})
        conn.execute(_text("DELETE FROM projects WHERE id=:p"), {"p": int(row["id"])})
    _audit(ACT_PROJECT_DELETE, target=code or nm, company_id=cid,
           detail="删除稽查项目「%s」（含其成员记录）" % nm, request=request)
    return {"ok": True, "id": int(project_id), "message": "项目已删除"}


# --------------------------------------------------------------------------
# 成员
# --------------------------------------------------------------------------
def list_members(project_id: Any, session: Any, *, engine=None) -> Dict[str, Any]:
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415
    with eng.connect() as conn:
        _fetch_visible(conn, session, project_id)     # 可见性前置（跨租户 404）
        rows = conn.execute(_text(
            "SELECT * FROM project_members WHERE project_id=:p ORDER BY "
            "CASE role WHEN 'owner' THEN 0 WHEN 'reviewer' THEN 1 WHEN 'member' THEN 2 "
            "ELSE 3 END, id"), {"p": int(project_id)}).all()
    return {"items": [_row_to_member(r) for r in rows], "total": len(rows)}


def add_member(project_id: Any, payload: Dict[str, Any], session: Any, *,
               engine=None, request: Any = None) -> Dict[str, Any]:
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415

    role = _validate_role(payload.get("role"))
    uname = _clean_str(payload.get("user_name"), maxlen=80)
    uid = payload.get("user_id")
    if uid in (None, "") and not uname:
        raise ProjectError("成员必须提供 user_id 或 user_name", 400)
    if uid not in (None, ""):
        try:
            uid = int(uid)
        except Exception:                             # noqa: BLE001
            raise ProjectError("user_id 非法", 400)

    with eng.begin() as conn:
        row = _fetch_visible(conn, session, project_id, for_write=True)
        code, cid, nm = str(row["code"] or ""), row["company_id"], str(row["name"])
        dup = conn.execute(_text(
            "SELECT id, role FROM project_members WHERE project_id=:p AND user_id=:u"
        ), {"p": int(row["id"]), "u": uid}).first()
        if dup:
            # 幂等：同人重复加入 ⇒ 视为**角色变更**（而非报错），留痕写明
            old = str(dup[1])
            if old == role:
                return {"ok": True, "id": int(dup[0]), "unchanged": True,
                        "message": "该成员已在项目中（角色未变：%s）" % ROLE_CN.get(old, old)}
            conn.execute(_text(
                "UPDATE project_members SET role=:r WHERE id=:i"), {"r": role, "i": int(dup[0])})
            _audit(ACT_PROJECT_MEMBER, target=code or nm, company_id=cid,
                   detail="成员「%s」角色 %s → %s" % (uname or uid, ROLE_CN.get(old, old),
                                                       ROLE_CN.get(role, role)),
                   request=request)
            return {"ok": True, "id": int(dup[0]), "role": role, "role_cn": ROLE_CN[role]}
        cur = conn.execute(_text(
            "INSERT INTO project_members (project_id, user_id, user_name, role, created_at) "
            "VALUES (:p,:u,:n,:r,:ts) RETURNING id"
        ), {"p": int(row["id"]), "u": uid, "n": uname, "r": role, "ts": _now()}).first()
        new_id = int(cur[0])
    _audit(ACT_PROJECT_MEMBER, target=code or nm, company_id=cid,
           detail="新增成员「%s」（角色：%s）" % (uname or uid, ROLE_CN.get(role, role)),
           request=request)
    return {"ok": True, "id": new_id, "role": role, "role_cn": ROLE_CN[role]}


# --------------------------------------------------------------------------
# 元数据（供前端下拉/字典；**唯一权威**来自 project_store 常量）
# --------------------------------------------------------------------------
def metadata() -> Dict[str, Any]:
    return {
        "statuses": [{"value": s, "label": STATUS_CN[s]} for s in STATUSES],
        "roles": [{"value": r, "label": ROLE_CN[r]} for r in ROLES],
        "status_flow": {s: {"next": list(STATUS_FLOW[s]),
                            "next_cn": [STATUS_CN[x] for x in STATUS_FLOW[s]]}
                        for s in STATUSES},
    }


__all__ = [
    "ProjectError", "create_project", "list_projects", "get_project",
    "update_project", "delete_project", "list_members", "add_member", "metadata",
]

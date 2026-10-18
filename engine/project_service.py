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
# ★ 2026-10-18（用户要求）项目画像字段 —— **单一权威表**
#   背景：新建项目原先只收「名称 + 统一社会信用代码」，行业/地区/稽查期间留空，
#   列表三列长期显示"—"（实测项目 42 全空）。现改为**在建项目这一步收集**。
#   规则：新增一个画像字段 ⇒ 只加一行；建表列（project_store._want）、写入白名单、
#        详情展示、`profile_missing` 判定、`metadata()` 全部自动跟随，不改逻辑分支。
# --------------------------------------------------------------------------
#: (字段名, 中文名, 最大长度, 类型)；类型 ∈ text / capital / date
PROFILE_FIELDS: Tuple[Tuple[str, str, int, str], ...] = (
    ("legal_representative", "法定代表人", 50, "text"),
    ("registered_capital", "注册资本", 0, "capital"),
    ("established_date", "成立日期", 10, "date"),
    ("registration_status", "登记状态", 40, "text"),
    ("registered_address", "注册地址", 200, "text"),
    ("company_type", "公司类型", 40, "text"),
    ("business_scope", "经营范围", 1000, "text"),
)

#: 稽查要素（建项目必填项 —— 前端强校验；后端**不硬性阻断**以兼容 API/历史数据，
#: 缺失由 `profile_missing` 如实标注"待补全"，绝不编造默认值）。
AUDIT_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("industry", "行业"),
    ("region", "地区"),
    ("period_start", "稽查期间起"),
    ("period_end", "稽查期间止"),
    ("tax_scopes", "税种范围"),
)


def _to_capital(v: Any) -> Optional[float]:
    """注册资本（万元）→ float 或 None。空 ⇒ None（**缺失≠0**，不得顶替）。"""
    if v in (None, "", "—"):
        return None
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        from engine.numparse import to_number              # noqa: PLC0415
        n = float(to_number(str(v).replace("万元", "").replace(",", "")) or 0)
    if n < 0:
        raise ProjectError("注册资本不能为负数", 400)
    return round(n, 2)


def _to_date(v: Any, label: str = "日期") -> str:
    """日期归一为 `YYYY-MM-DD`（接受 `2020/1/5`、`20200105`）；空 ⇒ 空串。"""
    s = _clean_str(v, maxlen=20)
    if not s:
        return ""
    import re                                              # noqa: PLC0415
    m = re.match(r"^(\d{4})[-/.年]?(\d{1,2})[-/.月]?(\d{1,2})日?$", s)
    if not m:
        raise ProjectError("%s格式非法：%s（应为 YYYY-MM-DD）" % (label, s), 400)
    y, mo, d = (int(x) for x in m.groups())
    if not (1900 <= y <= 2200 and 1 <= mo <= 12 and 1 <= d <= 31):
        raise ProjectError("%s超出合理范围：%s" % (label, s), 400)
    return "%04d-%02d-%02d" % (y, mo, d)


def _industry_code_of(label: Any) -> str:
    """中文行业名 → `companies.industry_code`（英文键）。

    ★ 映射**唯一来源** = `config/industry_params.json` 的 `industries[]`（label ↔ industry_id），
      禁止在本模块另写一张对照表。未命中 ⇒ 空串（**不猜**，也不塞默认行业）。
    """
    key = _clean_str(label, maxlen=60)
    if not key:
        return ""
    for item in _profile_dicts().get("industries") or []:
        if item.get("value") == key:
            return str(item.get("id") or "")
    return ""


def _profile_value(field: str, kind: str, maxlen: int, raw: Any) -> Any:
    """按类型清洗一个画像字段（写入白名单的唯一实现）。"""
    if kind == "capital":
        return _to_capital(raw)
    if kind == "date":
        return _to_date(raw, "成立日期")
    return _clean_str(raw, maxlen=maxlen)



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


def ensure_company_for_project(session: Any, proj: Dict[str, Any], *, engine=None,
                               request: Any = None) -> int:
    """★ 2026-10-15 账套退役配套：项目**自动绑定内部账套**（本函数 = 单一权威）。

    背景：分析/复核/资料存储引擎链以 company_id 为数据作用域（架构红线，不改引擎）；
    账套已从**用户概念**退役，但保留为**内部实现**——本函数保证「项目必有账套」：
    有 ⇒ 原样返回；无 ⇒ 按项目自持身份（名称+税号）创建内部账套并回填
    projects.company_id。幂等（先按 uscc 复用）；UI 不暴露该账套。

    创建语义与 main.create_company 一致：INSERT companies ⇒ 撤墓碑
    （公司/报告/资料删除墓碑，防「复用 id 被静默拦报告」）⇒ 种子数据
    （init_company_data：科目表/增值税科目/部门/期间——分析基础设施）⇒
    授权给项目 owner（grant_company_to_user）。"""
    from datetime import datetime                     # noqa: PLC0415
    eng = _engine_or_default(engine)
    from sqlalchemy import text as _text              # noqa: PLC0415
    try:
        cid = int(proj.get("company_id") or 0)
    except Exception:                                 # noqa: BLE001
        cid = 0
    if cid > 0:
        return cid
    name = _clean_str(proj.get("name"), maxlen=100) or "未命名项目"
    uscc = _clean_str(proj.get("taxpayer_id"), maxlen=50)

    # ★ 2026-10-18：项目是工商信息的**录入点（权威）**，内部账套是**派生物**。
    #   建内部账套时把画像同步过去，使分析链路（以 company 为作用域）也能取到；
    #   复用已有账套时**只补空、不覆盖**（不冲掉人工维护的数据）。
    _ind_label = _clean_str(proj.get("industry"), maxlen=60)
    _ind_code = _industry_code_of(_ind_label)
    _cap = proj.get("registered_capital")
    _est = _clean_str(proj.get("established_date"), maxlen=10) or None
    _prof_cols = {
        "legal_representative": _clean_str(proj.get("legal_representative"), maxlen=50) or None,
        "registered_capital": (round(float(_cap), 2) if _cap not in (None, "") else None),
        "established_date": _est,
        "address": _clean_str(proj.get("registered_address"), maxlen=200) or None,
        "business_scope": _clean_str(proj.get("business_scope"), maxlen=1000) or None,
        "company_type": _clean_str(proj.get("company_type"), maxlen=40) or None,
        "industry_code": _ind_code or None,
    }

    with eng.begin() as conn:
        if uscc:
            row = conn.execute(_text(
                "SELECT id FROM companies WHERE uscc=:u"), {"u": uscc}).first()
            if row:
                cid = int(row[0])                     # 复用同税号已有账套（幂等）
        if cid <= 0:
            cid = int(conn.execute(_text(
                "INSERT INTO companies (name, uscc, industry_code, registered_capital, "
                " established_date, legal_representative, address, business_scope, "
                " company_type, created_at) "
                "VALUES (:n,:u,:ind,:cap,:est,:lrp,:addr,:scope,:ctype,:ts) RETURNING id"
            ), {"n": name, "u": uscc or None, "ind": _ind_code or None,
                "cap": _prof_cols["registered_capital"], "est": _est,
                "lrp": _prof_cols["legal_representative"],
                "addr": _prof_cols["address"], "scope": _prof_cols["business_scope"],
                "ctype": _prof_cols["company_type"],
                "ts": datetime.now()}).first()[0])
        else:
            # 已有账套：逐列 `COALESCE(现值, 项目值)` ⇒ 只补空，不覆盖
            _sets = ", ".join("%s=COALESCE(%s, :%s)" % (c, c, c)
                              for c in _prof_cols if _prof_cols[c] is not None)
            _vals = {c: v for c, v in _prof_cols.items() if v is not None}
            if _sets:
                _vals["_cid"] = cid
                conn.execute(_text("UPDATE companies SET %s WHERE id=:_cid" % _sets), _vals)
        conn.execute(_text(
            "UPDATE projects SET company_id=:c, updated_at=:ts WHERE id=:p"
        ), {"c": cid, "ts": _now(), "p": int(proj["id"])})

    # 撤墓碑 + 种子数据 + 授权（与 main.create_company 同语义；延迟 import 防循环）
    try:
        import main as _main                          # noqa: PLC0415
        _main._deleted_company_ids.discard(cid)       # noqa: SLF001
        try:
            _main._report_deleted_at.pop(cid, None)   # noqa: SLF001
            _main._analysis_started_at.pop(cid, None)  # noqa: SLF001
        except Exception:                             # noqa: BLE001
            pass
        try:
            from runtime_storage import clear_company_doc_tombstones as _ccdt   # noqa: PLC0415
            _ccdt(cid)
        except Exception:                             # noqa: BLE001
            pass
        from database import SessionLocal, init_company_data   # noqa: PLC0415
        db = SessionLocal()
        try:
            init_company_data(db, cid)
            db.commit()
        finally:
            db.close()
        try:
            from security import grant_company_to_user as _grant   # noqa: PLC0415
            _grant(int(getattr(session, "user_id", None) or 0), cid)
        except Exception:                             # noqa: BLE001 — admin 恒真，授权失败不阻断
            pass
    except Exception:                                 # noqa: BLE001
        _audit(ACT_PROJECT_UPDATE, target=name, company_id=cid,
               detail="⚠ 内部账套 #%s 已绑定，但种子数据/撤墓碑步骤异常（分析前请核对）" % cid,
               request=request)

    _audit(ACT_PROJECT_UPDATE, target=name, company_id=cid,
           detail="自动绑定内部账套 #%s（账套退役后的引擎数据作用域，UI 不暴露）" % cid,
           request=request)
    if isinstance(proj, dict):
        proj["company_id"] = cid
    return cid


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
    # ★ 2026-10-18：注册资本统一为 float|None（SQLite 可能回读 int/None）
    cap = m.get("registered_capital")
    if cap not in (None, ""):
        try:
            m["registered_capital"] = round(float(cap), 2)
        except Exception:                             # noqa: BLE001
            m["registered_capital"] = None
    else:
        m["registered_capital"] = None
    # ★ 缺项如实标注（**不补默认值**）：列表据此显示「待补全」，详情列出缺哪几项
    missing = [label for key, label in AUDIT_FIELDS
               if not (m.get(key) not in (None, "", [], ()))]
    m["profile_missing"] = missing
    m["profile_complete"] = not missing
    m["profile_info_missing"] = [
        label for key, label, _mx, _k in PROFILE_FIELDS
        if m.get(key) in (None, "", 0)]
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
    # ★ 2026-10-15 去重：税号归一化（strip 后大写；USCC 本就是大写字母数字）
    _tid = _tid.upper()
    payload["taxpayer_id"] = _tid

    ts = _now()
    uid = getattr(session, "user_id", None)
    uname = _clean_str(getattr(session, "username", ""), maxlen=80)
    with eng.begin() as conn:
        # ★ 2026-10-15 去重：同一统一社会信用代码只允许一个在库项目
        #   （UPPER() 比较兼容历史大小写混杂数据；报错带已有项目指引）
        _dup = conn.execute(_text(
            "SELECT code, name FROM projects WHERE UPPER(taxpayer_id) = :t LIMIT 1"
        ), {"t": _tid}).first()
        if _dup is not None:
            _dm = _dup._mapping
            raise ProjectError(
                "同一统一社会信用代码的项目已存在：「%s」（编号 %s），不能重复创建，请直接使用原项目"
                % (_dm.get("name") or "（未命名）", _dm.get("code") or "-"), 400)
        code = _clean_str(payload.get("code"), maxlen=40) or _next_code(conn, cid_int)
        # ★ 2026-10-18：企业重点工商信息随项目创建一并落库（画像字段白名单见 PROFILE_FIELDS）
        _prof = {}
        for _f, _cn, _mx, _kind in PROFILE_FIELDS:
            _prof[_f] = _profile_value(_f, _kind, _mx, payload.get(_f))
        row = conn.execute(_text(
            "INSERT INTO projects (company_id, code, name, taxpayer_id, industry, region, "
            " period_start, period_end, tax_scopes, status, remark, owner_id, owner_name, "
            " created_at, updated_at, legal_representative, registered_capital, established_date, "
            " registration_status, registered_address, business_scope, company_type) "
            "VALUES (:cid,:code,:name,:tid,:ind,:reg,:ps,:pe,:ts,:st,:rm,:oid,:onm,:ca,:ua,"
            " :lrp,:cap,:est,:rst,:addr,:scope,:ctype) "
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
            "lrp": _prof["legal_representative"], "cap": _prof["registered_capital"],
            "est": _prof["established_date"], "rst": _prof["registration_status"],
            "addr": _prof["registered_address"], "scope": _prof["business_scope"],
            "ctype": _prof["company_type"],
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
        if "taxpayer_id" in payload and payload.get("taxpayer_id") is not None:
            _utid = _clean_str(payload.get("taxpayer_id"), maxlen=40)
            if len(_utid) != 18:
                raise ProjectError("统一社会信用代码必须为 18 位", 400)
            # ★ 2026-10-15 去重：归一化后查与其他项目（排除自身）的冲突
            _utid = _utid.upper()
            payload["taxpayer_id"] = _utid
            _dup = conn.execute(_text(
                "SELECT code, name FROM projects "
                "WHERE UPPER(taxpayer_id) = :t AND id <> :pid LIMIT 1"
            ), {"t": _utid, "pid": int(project_id)}).first()
            if _dup is not None:
                _dm = _dup._mapping
                raise ProjectError(
                    "统一社会信用代码与已有项目冲突：「%s」（编号 %s），一个代码只能对应一个项目"
                    % (_dm.get("name") or "（未命名）", _dm.get("code") or "-"), 400)
        simple = (("name", 200), ("taxpayer_id", 40), ("industry", 60),
                  ("region", 60), ("remark", 500), ("code", 40))
        for key, mx in simple:
            if key in payload and payload.get(key) is not None:
                if key == "name" and not _clean_str(payload.get(key)):
                    raise ProjectError("企业名称不能为空", 400)
                sets.append("%s=:%s" % (key, key))
                params[key] = _clean_str(payload.get(key), maxlen=mx)
        # ★ 2026-10-18：企业重点工商信息（同一张 PROFILE_FIELDS 表驱动，禁另写一份）
        for key, _cn, mx, kind in PROFILE_FIELDS:
            if key in payload:
                sets.append("%s=:%s" % (key, key))
                params[key] = _profile_value(key, kind, mx, payload.get(key))
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
                   request: Any = None, cascade: bool = False) -> Dict[str, Any]:
    """删除项目：删 `projects` 行 + 其 `project_members` 行，并处置**归属本项目的资料**。

    ★ 2026-10-17（O5）：此前只删 `projects`/`project_members` 两行，
      挂在项目下的 `documents` **原样残留**（实测删项目 10 后仍剩 20 条，
      另有 102 条指向早已不存在的项目 ⇒ 孤儿资料）⇒ 项目删了、资料还在，
      列表按项目过滤查不到、按账套统计却算进去，数据自相矛盾。

    **处置口径（两级，默认不误删）**：
      · 未传 `cascade=True` 且该项目下有资料 ⇒ **409**，并在消息里报数量，
        要求调用方显式确认（前端据此提示"将一并删除 N 份资料"）。
      · `cascade=True` ⇒ 删 `documents` 及其解析子表；**物理文件 `move_to_trash`（可恢复）**，
        **绝不 `os.remove`**（项目铁律：删除优先进回收站）。
      · 报告的删除唯一权威仍是 `main.purge_company_analysis_artifacts`，本函数**不碰**账套与报告。
    """
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415
    from runtime_storage import move_to_trash         # noqa: PLC0415
    with eng.begin() as conn:
        row = _fetch_visible(conn, session, project_id, for_write=True)
        nm, code, cid = str(row["name"]), str(row["code"] or ""), row["company_id"]
        pid = int(row["id"])
        # ★ `documents` 是**运行时按需建表**（`engine.document_store.ensure_schema`），
        #   老库/新库可能根本没有该表 ⇒ 必须先判断表存在，否则 `SELECT` 直接抛
        #   `no such table: documents`，把"删项目"整个打死（2026-10-17 实测：
        #   `test_project_api` 因此失败）。表不存在 ⇒ 语义上就是"该项目没有资料"。
        has_docs = conn.execute(
            _text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents'")
        ).fetchone() is not None
        docs = []
        if has_docs:
            docs = conn.execute(
                _text("SELECT id, storage_path FROM documents WHERE project_id=:p"),
                {"p": pid},
            ).fetchall()
        if docs and not cascade:
            raise ProjectError(
                "项目下还有 %d 份资料，删除项目将**一并删除**这些资料"
                "（可恢复：文件进回收站）。请确认后带 cascade=true 重试。" % len(docs),
                409)
        doc_ids = [int(d[0]) for d in docs]
        paths = [str(d[1] or "") for d in docs]
        if has_docs:
            for table in ("extracted_tables", "extracted_fields",
                          "document_pages", "extract_issues"):
                exists = conn.execute(
                    _text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"),
                    {"t": table},
                ).fetchone() is not None
                if exists:
                    conn.execute(
                        _text("DELETE FROM %s WHERE document_id IN "
                              "(SELECT id FROM documents WHERE project_id=:p)" % table),
                        {"p": pid})
            conn.execute(_text("DELETE FROM documents WHERE project_id=:p"), {"p": pid})
        conn.execute(_text("DELETE FROM project_members WHERE project_id=:p"), {"p": pid})
        conn.execute(_text("DELETE FROM projects WHERE id=:p"), {"p": pid})
    # 物理文件在事务提交后处理（移入回收站，可恢复）
    trashed = 0
    for p in paths:
        if p and move_to_trash(p):
            trashed += 1
    _audit(ACT_PROJECT_DELETE, target=code or nm, company_id=cid,
           detail="删除稽查项目「%s」（含其成员记录%s）"
                  % (nm, "、%d 份资料" % len(doc_ids) if doc_ids else ""),
           request=request)
    return {"ok": True, "id": pid,
            "documents_deleted": len(set(doc_ids)),
            "files_trashed": trashed,
            "message": "项目已删除" + ("，%d 份资料已移入回收站" % trashed if doc_ids else "")}


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
    """项目字典 —— **前端不硬编码任何选项**（单一权威 = 后端 / 数据文件）。

    `industries` 取自 `config/industry_params.json`（行业模型口径，与风险指标/报告模板同一套）；
    `tax_types` 取自 `engine/levy_nature.tax_scope_options()`（税种全表，唯一权威）；
    其余选项取自 `config/project_profile_dicts.json`。
    """
    d = _profile_dicts()
    from engine.levy_nature import tax_scope_options        # noqa: PLC0415
    return {
        "statuses": [{"value": s, "label": STATUS_CN[s]} for s in STATUSES],
        "roles": [{"value": r, "label": ROLE_CN[r]} for r in ROLES],
        "status_flow": {s: {"next": list(STATUS_FLOW[s]),
                            "next_cn": [STATUS_CN[x] for x in STATUS_FLOW[s]]}
                        for s in STATUSES},
        # ── 企业画像 / 稽查要素字典（2026-10-18 新增）──
        "industries": d["industries"],
        "regions": d["regions"],
        "registration_statuses": d["registration_statuses"],
        "company_types": d["company_types"],
        "capital_unit": d["capital_unit"],
        "tax_types": [{"value": x, "label": x} for x in tax_scope_options()],
        "profile_fields": [{"key": k, "label": cn, "kind": kind,
                            "maxlen": mx, "unit": d["capital_unit"] if kind == "capital" else ""}
                           for k, cn, mx, kind in PROFILE_FIELDS],
        "audit_fields": [{"key": k, "label": cn} for k, cn in AUDIT_FIELDS],
        "audit_required": [k for k, _cn in AUDIT_FIELDS],
    }


_PROFILE_DICTS: Dict[str, Any] = {}


def _profile_dicts() -> Dict[str, Any]:
    """读画像字典（**进程内缓存**；数据文件是唯一权威，改文件后重启即生效）。"""
    global _PROFILE_DICTS
    if _PROFILE_DICTS:
        return _PROFILE_DICTS
    import os                                             # noqa: PLC0415
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "config", "project_profile_dicts.json"),
              encoding="utf-8") as fh:
        prof = json.load(fh)
    with open(os.path.join(root, "config", "industry_params.json"),
              encoding="utf-8") as fh:
        ind = json.load(fh)
    _PROFILE_DICTS = {
        "regions": [str(x) for x in (prof.get("regions") or [])],
        "registration_statuses": [str(x) for x in (prof.get("registration_statuses") or [])],
        "company_types": [str(x) for x in (prof.get("company_types") or [])],
        "capital_unit": str(prof.get("capital_unit") or "万元"),
        "industries": [{"value": str(x.get("label") or ""),
                        "id": str(x.get("industry_id") or "")}
                       for x in (ind.get("industries") or []) if x.get("label")],
    }
    return _PROFILE_DICTS


def reset_profile_cache() -> None:
    """仅供测试/热更新：清空字典缓存。"""
    global _PROFILE_DICTS
    _PROFILE_DICTS = {}


__all__ = [
    "ProjectError", "create_project", "list_projects", "get_project",
    "update_project", "delete_project", "list_members", "add_member", "metadata",
    "PROFILE_FIELDS", "AUDIT_FIELDS", "reset_profile_cache",
]

# -*- coding: utf-8 -*-
"""P0-6 风险结果展示与复核 —— HTTP 接口。

路径前缀 `/api/v1`（**新增**端点专用；与 T-3 裁定不冲突：现有端点一字未改）。

| 端点 | 说明 |
|---|---|
| `GET /api/v1/projects/{projectId}/risks` | 项目视角风险列表（筛选/排序/分页） |
| `GET /api/v1/risks/{riskId}` | 风险详情（规则 + 计算过程 + 证据链 + 法规依据 + 建议 + 复核态） |
| `POST /api/v1/risks/{riskId}/review` | 人工处置复核（确认/排除/误报/标记已整改/转人工/重开） |
| `POST /api/v1/risks/{riskId}/comment` | 批注（不改状态） |
| `GET /api/v1/risks/meta` | 字典（状态机/动作/排序键/等级候选） |
| `GET /api/v1/projects/{projectId}/risks/stats` | 风险统计（等级/税种/复核状态/金额分档） |
| `GET /api/v1/rectifications` | 整改台账（按账套） |

★ `riskId` = **风险编号** `risk_no`（`WB-R-{统一社会信用代码}-{期间}-{序号}`，
  唯一权威 `engine/numbering`）—— 它是**跨报告轮次稳定**的身份（数字 `seq` 只是报告内位置）。
  兼容传纯数字 `seq`（此时须带 `company_id`）。

★ 认证：唯一权威 `security_web.enforce_request_security`（`main.auth_middleware` 调用）；
  本模块只读 `request.state.auth`，不重复实现鉴权。
★ 可见性：跨租户 ⇒ **404**（不泄露存在性），与 P0-1/P0-2/P0-3 同一口径。
★ 复核**不改等级**（等级唯一权威 `engine/risk_levels.py`）。
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from engine import risk_review as REVIEW
from engine import risk_service as RISK

router = APIRouter(prefix="/api/v1", tags=["风险结果与复核（P0-6）"])

#: 页面路由（**无前缀**）。单独一个 router 是为了让 `main.py` 只需**同一行内**追加一个
#: `include_router` ⇒ 文件行数不变 ⇒ 既有文档中的 `main.py:行号` 引用零漂移。
page_router = APIRouter(tags=["风险结果与复核（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))

#: 分页上限（与既有接口同量级）
_MAX_PAGE_SIZE = 200


@page_router.get("/risks", response_class=HTMLResponse, include_in_schema=False)
def risks_page():
    """风险结果与复核工作台（静态 HTML，无服务端模板）。

    ★ 资源缺失 ⇒ **明确 500 + 说明**（而不是把 `FileNotFoundError` 直接抛出去变成裸栈）：
      实测（2026-10-13，本页 HTML 尚未创建时）该路由会抛 `FileNotFoundError` ⇒ 调用方只看到
      500 且无原因。此处把"编码问题"与"文件不存在"分开处理，均可解释。
    """
    path = os.path.join(_ROOT, "static", "risks.html")
    if not os.path.exists(path):
        raise HTTPException(status_code=500, detail="页面资源缺失：static/risks.html")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    raise HTTPException(status_code=500, detail="页面资源编码无法识别：static/risks.html")


def _session(request: Request):
    auth = getattr(request.state, "auth", None)
    if auth is None:
        raise HTTPException(status_code=401, detail="未登录")
    return auth


def _svc(fn, *args, **kwargs):
    """调 Service 层并把 `RiskServiceError` / `RiskReviewError` 转成 HTTP 语义。

    ★ 一处收口：否则异常穿透到 FastAPI ⇒ **500**（P0-2/P0-4 各踩过一次同样的坑）。
    """
    try:
        return fn(*args, **kwargs)
    except (RISK.RiskServiceError, REVIEW.RiskReviewError) as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc


def _project_company(project_id: int, session: Any) -> int:
    return _svc(RISK.company_of_project, project_id, session)


# --------------------------------------------------------------------------
# 字典
# --------------------------------------------------------------------------
@router.get("/risks/meta", summary="字典（状态机/动作/排序键/等级候选）")
def risks_meta(request: Request):
    _session(request)
    # ★ 复核状态机字典由 `risk_service.metadata()` **内部**收口（它转发 `risk_review.metadata()`）
    #   ⇒ 本处**不再二次写入** `review` 键（避免同一概念两个写入点）。
    #   P1-4 新增的 `bulk_limit` / `stale_days_default` 已随该链路自动可见。
    return RISK.metadata()


# --------------------------------------------------------------------------
# P1-4 复核看板 / 批量复核（★ 注册在 `/risks/{risk_id}` **之前**，否则会被它吃掉）
# --------------------------------------------------------------------------
@router.get("/risks/review-board", summary="复核看板（各态计数 / 已处置率 / 超期待处理）")
def review_board(request: Request,
                 company_id: Optional[int] = Query(None, ge=1),
                 project_id: Optional[int] = Query(None, ge=1),
                 stale_days: Optional[int] = Query(None, ge=0)):
    """复核看板（P1-4）。

    ★ `risk_nos` 取"该项目/账套的可见风险"：
      · 给 `project_id` ⇒ 项目视角（该账套的全部风险）；
      · 只给 `company_id` ⇒ 账套视角。
    ★ 「从未处置」与「超期」**分开计**（前者无起点，不能算超期）。
    """
    session = _session(request)
    if company_id is not None:
        cid = _svc(RISK.require_company, int(company_id), session)
    elif project_id is not None:
        cid = _project_company(int(project_id), session)
    else:
        raise HTTPException(status_code=400, detail="必须提供 company_id 或 project_id")
    kw: Dict[str, Any] = {}
    if stale_days is not None:
        kw["stale_days"] = int(stale_days)
    out = _svc(REVIEW.review_stats, cid, **kw)
    out["company_id"] = int(cid)
    return out


@router.post("/risks/bulk-review", summary="批量复核（逐条独立执行、逐条如实回报）")
def bulk_review_risks(request: Request,
                      payload: Dict[str, Any] = Body(default_factory=dict)):
    """请求体：`{risk_ids: [...], action, note?, company_id?, project_id?}`。

    ★ **逐条独立执行**：部分失败**不回滚**已成功条目（处置流水为 append-only 台账），
      结果逐条给出 `ok / noop / failed` 三态与原因。超上限 ⇒ 400（请分批）。
    """
    session = _session(request)
    body = payload if isinstance(payload, dict) else {}
    ids = body.get("risk_ids") or body.get("risk_nos") or []
    if not isinstance(ids, (list, tuple)):
        raise HTTPException(status_code=400, detail="risk_ids 必须是数组")
    if not [x for x in ids if str(x or "").strip()]:
        raise HTTPException(status_code=400, detail="risk_ids 不能为空")
    action = str(body.get("action") or "").strip()
    note = str(body.get("note") or "").strip()
    # 账套定位：显式 `company_id` 优先 → `project_id` → 按**首个风险编号**反查可见账套
    #   （批量复核的语义是"同一账套内一批风险"，跨账套批量不属于本接口职责）
    if body.get("company_id") not in (None, ""):
        cid = _svc(RISK.require_company, int(body["company_id"]), session)
    elif body.get("project_id") not in (None, ""):
        cid = _project_company(int(body["project_id"]), session)
    else:
        first = next(str(x).strip() for x in ids if str(x or "").strip())
        cid = _company_of_risk_no(first, session, None)

    out = _svc(REVIEW.bulk_review, list(ids), action, session,
               company_id=cid, note=note, request=request)
    out["company_id"] = int(cid)
    return out


# --------------------------------------------------------------------------
# 列表 / 统计（项目视角）
# --------------------------------------------------------------------------
@router.get("/projects/{project_id}/risks", summary="风险列表（项目视角：筛选/排序/分页）")
def list_project_risks(project_id: int, request: Request,
                       tax: Optional[str] = None,
                       level: Optional[str] = None,
                       state: Optional[str] = None,
                       period: Optional[str] = None,
                       amount_min: Optional[float] = None,
                       amount_max: Optional[float] = None,
                       q: Optional[str] = None,
                       reviewed: Optional[str] = None,
                       sort: str = "priority",
                       order: str = "desc",
                       page: int = Query(1, ge=1),
                       page_size: int = Query(20, ge=1, le=_MAX_PAGE_SIZE)):
    session = _session(request)
    cid = _project_company(project_id, session)
    out = _svc(RISK.list_risks, cid, session, tax=tax or "", level=level or "",
               state=state or "", period=period or "", amount_min=amount_min,
               amount_max=amount_max, q=q or "", reviewed=reviewed or "",
               sort=sort, order=order, page=page, page_size=page_size)
    out["project_id"] = int(project_id)
    return out


@router.get("/projects/{project_id}/risks/stats", summary="风险统计（等级/税种/复核状态/金额分档）")
def project_risk_stats(project_id: int, request: Request):
    session = _session(request)
    cid = _project_company(project_id, session)
    out = _svc(RISK.stats, cid, session)
    out["project_id"] = int(project_id)
    return out


# --------------------------------------------------------------------------
# 详情 / 复核 / 批注
# --------------------------------------------------------------------------
@router.get("/risks/{risk_id}", summary="风险详情（规则+计算过程+证据链+法规依据+建议）")
def get_risk(risk_id: str, request: Request,
             company_id: Optional[int] = Query(None, ge=1)):
    """按风险编号取详情；兼容传纯数字 `seq`（此时须带 `company_id`）。"""
    session = _session(request)
    rid = str(risk_id or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="risk_id 不能为空")
    if rid.isdigit():
        if not company_id:
            raise HTTPException(
                status_code=400,
                detail="按数字序号查询须同时提供 company_id（建议改用风险编号 risk_no）")
        cid = int(company_id)
    else:
        cid = _company_of_risk_no(rid, session, company_id)
    return _svc(RISK.get_risk, rid, cid, session)


def _company_of_risk_no(risk_no: str, session: Any, given: Optional[int]) -> int:
    """风险编号 → 账套。

    ★ 编号里含统一社会信用代码 ⇒ **必须**与调用方声明的账套一致，
      否则同一编号可被用来越界读取他账套数据。校验失败一律 404（不泄露存在性）。
    """
    if given:
        cid = int(given)
        if not _risk_no_belongs(risk_no, cid):
            raise HTTPException(status_code=404, detail="风险事项不存在")
        # 租户隔离仍走 Service（`can_access_company`）
        return cid
    # 未给 company_id ⇒ 在**当前用户可见账套**里找（找不到 ⇒ 404）
    ids = sorted(int(x) for x in (getattr(session, "allowed_company_ids", ()) or ()))
    if getattr(session, "is_admin", False):
        try:
            from runtime_storage import offline_reports_root      # noqa: PLC0415
            import glob as _glob                                  # noqa: PLC0415
            ids = sorted(int(os.path.basename(p).split("_")[1])
                         for p in _glob.glob(os.path.join(offline_reports_root(),
                                                          "company_*_full.json")))
        except Exception:                                          # noqa: BLE001
            ids = ids or []
    for cid in ids:
        if _risk_no_belongs(risk_no, cid):
            return int(cid)
    raise HTTPException(status_code=404, detail="风险事项不存在")


def _risk_no_belongs(risk_no: str, company_id: Any) -> bool:
    """编号归属校验：从 `risk_no` 的 body 段取统一社会信用代码，与账套的 USCC 比对。"""
    try:
        from engine.numbering import NumberingService, load_rules     # noqa: PLC0415
        ns = NumberingService("", "", rules=load_rules())
        parsed = ns.parse(risk_no) or {}
        body = str(parsed.get("body") or "")
        if not body:
            return False
        code = body.split(ns.connector)[0] if ns.connector in body else body
    except Exception:                                                 # noqa: BLE001
        return False
    return _uscc_of(company_id) == code


def _uscc_of(company_id: Any) -> str:
    """账套统一社会信用代码（查 `companies` 表；取不到 ⇒ 空串，调用方据此判 404）。"""
    try:
        import sqlite3                                                # noqa: PLC0415
        from runtime_storage import DATA_DIR                          # noqa: PLC0415
        conn = sqlite3.connect(os.path.join(DATA_DIR, "accounting.db"))
        try:
            row = conn.execute(
                "select uscc from companies where id=?", (int(company_id),)).fetchone()
        finally:
            conn.close()
        return str((row or [""])[0] or "").strip().upper()
    except Exception:                                                 # noqa: BLE001
        return ""


@router.post("/risks/{risk_id}/review", summary="风险复核（确认/排除/误报/标记已整改/转人工/重开）")
def review_risk(risk_id: str, request: Request,
                payload: Dict[str, Any] = Body(default_factory=dict)):
    """请求体：`{action, note?, company_id?, project_id?}`。

    ★ `exclude` / `false_positive` / `rectify` / `reopen` **必须**带 `note`（理由/说明），
      否则 400 —— 本项目不生成"无理由的处置"。
    """
    session = _session(request)
    rid = str(risk_id or "").strip()
    body = payload if isinstance(payload, dict) else {}
    action = str(body.get("action") or "").strip()
    note = str(body.get("note") or "").strip()
    given = body.get("company_id")
    cid = _resolve_company(rid, session, given, body.get("project_id"))
    out = _svc(REVIEW.review, rid, action, session, company_id=cid,
               note=note, request=request)
    out["company_id"] = int(cid)
    return out


@router.post("/risks/{risk_id}/comment", summary="风险批注（不改状态）")
def comment_risk(risk_id: str, request: Request,
                 payload: Dict[str, Any] = Body(default_factory=dict)):
    """请求体：`{text, company_id?, project_id?}`。"""
    session = _session(request)
    rid = str(risk_id or "").strip()
    body = payload if isinstance(payload, dict) else {}
    text = str(body.get("text") or body.get("note") or "").strip()
    cid = _resolve_company(rid, session, body.get("company_id"), body.get("project_id"))
    out = _svc(REVIEW.comment, rid, text, session, company_id=cid, request=request)
    out["company_id"] = int(cid)
    return out


@router.get("/risks/{risk_id}/history", summary="风险处置历史（事件流 + 批注）")
def risk_history(risk_id: str, request: Request,
                 company_id: Optional[int] = Query(None, ge=1),
                 project_id: Optional[int] = Query(None, ge=1)):
    """该风险的**人工处置**事件流（P1-4）。未处置 ⇒ 空列表 + `reviewed=false`。"""
    session = _session(request)
    rid = str(risk_id or "").strip()
    cid = _resolve_company(rid, session, company_id, project_id)
    out = _svc(REVIEW.history, rid, cid)
    out["company_id"] = int(cid)
    return out


def _resolve_company(risk_id: str, session: Any, given: Any,
                     project_id: Any) -> int:
    """定位账套：`company_id` 优先；否则 `project_id`；否则按编号反查可见账套。"""
    if given not in (None, ""):
        cid = _company_of_risk_no(risk_id, session, int(given))
        return cid
    if project_id not in (None, ""):
        return _project_company(int(project_id), session)
    return _company_of_risk_no(risk_id, session, None)


# --------------------------------------------------------------------------
# 整改台账
# --------------------------------------------------------------------------
@router.get("/rectifications", summary="整改台账（按账套）")
def list_rectifications(request: Request,
                        company_id: int = Query(..., ge=1),
                        project_id: Optional[int] = Query(None, ge=1)):
    session = _session(request)
    # 租户隔离：先做一次可见性校验（跨租户 ⇒ 404）
    _svc(RISK.require_company, company_id, session)
    items = REVIEW.rectifications(int(company_id))
    return {"available": True, "company_id": int(company_id),
            "total": len(items), "items": items,
            "state_cn": REVIEW.STATE_CN,
            "note": "整改台账来自复核事件流 `data/risk_reviews.jsonl`（编号权威 engine/numbering）。"}


__all__ = ["router", "page_router"]

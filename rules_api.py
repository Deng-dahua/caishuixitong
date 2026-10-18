# -*- coding: utf-8 -*-
"""P0-5 规则引擎 HTTP 接口：规则库 + 风险发现。

路径前缀 `/api/v1`（**新增**端点专用，与 T-3 裁定不冲突：现有端点一字未改）。

| 端点 | 说明 |
|---|---|
| `GET /api/v1/rules/meta` | 规则库字典（来源/层/税种/开关说明/DSL 边界） |
| `GET /api/v1/rules` | 规则列表（来源/层/税种/关键词/启用态 + 分页） |
| `GET /api/v1/rules/stats` | 统计（分层计数、法规依据覆盖率、规则主体权威值） |
| `GET /api/v1/rules/versions` | 规则版本（唯一权威 `config/rule_versions.json`） |
| `GET /api/v1/rules/{rule_id}` | 规则详情（含原文 raw、法规依据引用、版本登记） |
| `GET /api/v1/risk-findings` | 风险发现列表（按账套读产物载荷；含综合排序分） |
| `GET /api/v1/risk-findings/{seq}` | 风险详情（规则 + 计算过程 + 证据 + 法规依据） |
| `GET /api/v1/rule-executions` | 逐条执行记录（如实含未运行/跳过/异常） |
| `GET /api/v1/risk-scoring/meta` | 评分配置（权重/分段/三档视图） |

★ 认证：唯一权威 `security_web.enforce_request_security`（`main.auth_middleware` 调用），
  本模块只读 `request.state.auth`，不重复实现鉴权。

★ 风险发现的数据来源 = **真实产物载荷**（`runtime_storage.offline_reports_root()` 下的
  `company_{id}_full.json`），**不是**另建一张 findings 表 —— 避免"一个概念两处存放"
  （P0-3 已确立口径）。读不到 ⇒ 如实回 `not_generated`，不返回编造的空列表。
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from engine import rule_catalog as CAT
from engine import rule_executor as EXEC
from engine import risk_scoring as SCORE

from engine.api_common import (admin_of, call_boundary, request_perm,
                             require_perm, session_of)

# ★ R-02（2026-10-17）：以下名字是**别名**，逻辑唯一在 engine/api_common。
#   禁止在本文件重新定义（闸门 `check_api_boundary_single_source` 会报错）。
_session = session_of

router = APIRouter(prefix="/api/v1", tags=["规则引擎（P0-5）"])

#: 页面路由（**无前缀**）。单独一个 router 是为了让 `main.py` 只需**同一行内**
#: 追加一个 `include_router` ⇒ 文件行数不变 ⇒ 既有文档中的 `main.py:行号` 引用零漂移。
page_router = APIRouter(tags=["规则引擎（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))


@page_router.get("/rules", response_class=HTMLResponse, include_in_schema=False)
def rules_page():
    """规则库与风险发现页（静态 HTML，无服务端模板）。"""
    path = os.path.join(_ROOT, "static", "rules.html")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"


def _findings_payload(company_id: Any, session: Any) -> Dict[str, Any]:
    """读该账套的**真实产物载荷**（**薄转发** `risk_service.load_payload`）。

    ★ 2026-10-13（P0-6）收敛：原先本函数自己实现了一份读盘逻辑，与 P0-6 风险视图层**同概念两处**。
      现唯一权威 = `engine/risk_service.load_payload()`（它同时服务规则库页与风险工作台）
      ⇒ 两个页面的取数口径不可能各自漂移。本函数只做 **错误类型翻译**
      （`RiskServiceError` → `HTTPException`），不改任何读盘语义。
    """
    from engine import risk_service as RISK                       # noqa: PLC0415
    try:
        return RISK.load_payload(company_id, session)
    except RISK.RiskServiceError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc


# --------------------------------------------------------------------------
# 规则库
# --------------------------------------------------------------------------
@router.get("/rules/meta", summary="规则库字典（来源/层/税种/开关说明/DSL 边界）")
def rules_meta(request: Request):
    _session(request)
    return CAT.meta()


@router.get("/rules/stats", summary="规则库统计（分层计数 / 法规依据覆盖率）")
def rules_stats(request: Request):
    _session(request)
    return CAT.stats()


@router.get("/rules/versions", summary="规则版本（唯一权威 config/rule_versions.json）")
def rules_versions(request: Request):
    _session(request)
    try:
        return CAT.versions()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/rules", summary="规则列表（来源/层/税种/关键词/启用态/入库处置 + 分页）")
def list_rules(request: Request,
               source: Optional[str] = None,
               layer: Optional[str] = None,
               tax: Optional[str] = None,
               q: Optional[str] = None,
               enabled: Optional[str] = None,
               disposition: Optional[str] = Query(
                   None, description="候选入库处置：kept/merged/stale_status/blocked/pending"),
               page: int = Query(1, ge=1),
               page_size: int = Query(20, ge=1, le=200)):
    _session(request)
    return CAT.list_rules(source=source, layer=layer, tax=tax, q=q,
                          enabled=enabled, disposition=disposition,
                          page=page, page_size=page_size)


@router.get("/rules/{rule_id}", summary="规则详情（含原文与法规依据引用）")
def get_rule(rule_id: str, request: Request):
    _session(request)
    try:
        return CAT.get(rule_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="规则不存在：%s" % rule_id) from None


# --------------------------------------------------------------------------
# 评分配置
# --------------------------------------------------------------------------
@router.get("/risk-scoring/meta", summary="风险综合排序分配置（权重/分段/三档视图）")
def scoring_meta(request: Request):
    _session(request)
    return SCORE.metadata()


# --------------------------------------------------------------------------
# 风险发现与逐条执行（读真实产物载荷）
# --------------------------------------------------------------------------
@router.get("/risk-findings", summary="风险发现列表（按账套；含综合排序分）")
def list_findings(request: Request,
                  company_id: int = Query(..., ge=1),
                  level: Optional[str] = None,
                  q: Optional[str] = None,
                  with_score: bool = True):
    session = _session(request)
    got = _findings_payload(company_id, session)
    if not got.get("available"):
        return {"available": False, "reason": got.get("reason", ""),
                "items": [], "total": 0, "generated_at": ""}
    res = EXEC.collect_from_report(got["payload"])
    items = res["findings"]
    lv = str(level or "").strip()
    if lv:
        items = [x for x in items if x.get("risk_level") == lv]
    kw = str(q or "").strip().lower()
    if kw:
        items = [x for x in items
                 if kw in str(x.get("title") or "").lower()
                 or kw in str(x.get("rule_id") or "").lower()
                 or kw in str(x.get("redline_id") or "").lower()]
    if with_score:
        items = SCORE.stamp_all(items)
    items.sort(key=lambda x: (x.get("priority_score") is None,
                              -(x.get("priority_score") or 0),
                              int(x.get("seq") or 0)))
    return {"available": True, "generated_at": got.get("generated_at", ""),
            "company_id": company_id, "total": len(items),
            "items": items, "execution_summary": res["summary"],
            "note": ("发现读自真实产物载荷 `company_%d_full.json` 的 "
                     "`enterprise_readable_report.confirmed_problems`；"
                     "排序分只作排序、不改等级。" % company_id)}


@router.get("/risk-findings/{seq}", summary="风险详情（规则 + 计算过程 + 证据 + 法规依据）")
def get_finding(seq: int, request: Request, company_id: int = Query(..., ge=1)):
    session = _session(request)
    got = _findings_payload(company_id, session)
    if not got.get("available"):
        raise HTTPException(status_code=404, detail=got.get("reason", "载荷不存在"))
    res = EXEC.collect_from_report(got["payload"])
    hit = None
    for f in res["findings"]:
        if int(f.get("seq") or 0) == int(seq):
            hit = f
            break
    if hit is None:
        raise HTTPException(status_code=404, detail="风险发现不存在：seq=%d" % seq)
    # 规则侧信息（版本 / 法规依据 / 层）—— 有则带上，无则如实空
    rule: Dict[str, Any] = {}
    for rid in (hit.get("rule_id"), hit.get("redline_id")):
        if not rid:
            continue
        try:
            rule = CAT.get(rid)
            break
        except KeyError:
            continue
    return {
        "finding": SCORE.stamp(hit),
        "scoring": SCORE.score(hit),
        "evidences": [e for e in res["evidences"]
                      if int(e.get("finding_seq") or 0) == int(seq)],
        "rule": ({"rule_id": rule.get("rule_id"), "name": rule.get("name"),
                  "layer": rule.get("layer"), "version": rule.get("version"),
                  "version_registered": rule.get("version_registered"),
                  "legal_basis_ref": rule.get("legal_basis_ref"),
                  "source_cn": rule.get("source_cn"),
                  "authority_cn": rule.get("authority_cn")} if rule else {}),
        "rule_found": bool(rule),
        "note": ("规则未在目录中（可能只在发现里出现）⇒ `rule_found=false`，"
                 "不编造法规依据。" if not rule else ""),
    }


@router.get("/rule-executions", summary="逐条执行记录（如实含未运行/跳过/异常）")
def list_executions(request: Request, company_id: int = Query(..., ge=1)):
    session = _session(request)
    got = _findings_payload(company_id, session)
    if not got.get("available"):
        return {"available": False, "reason": got.get("reason", ""),
                "items": [], "summary": EXEC.execution_summary([])}
    res = EXEC.collect_from_report(got["payload"])
    return {"available": True, "company_id": company_id,
            "summary": res["summary"], "items": res["executions"],
            "status_cn": EXEC.EXEC_STATUS_CN}


__all__ = ["router", "page_router"]

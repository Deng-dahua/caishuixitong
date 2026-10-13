# -*- coding: utf-8 -*-
"""解析与标准化增强 HTTP 接口（P1-1）。

路径前缀 `/api/v1`（**新增**端点专用；P0-3 既有端点一字未改）。

★ 本模块提供的端点
    GET  /api/v1/parse/meta                     解析增强字典（49 标准字段 / 上限登记 / 性能说明）
    GET  /api/v1/parse/cap-manifest             行数上限登记清单（源码 ↔ 登记表一致性）
    GET  /api/v1/documents/{documentId}/field-coverage
                                                某份已解析资料的**标准字段覆盖度体检**

★ 认证：唯一权威 = `security_web.enforce_request_security`（中间件已做）。
★ 权限：本模块在**路由层**再判一次（唯一权威 `engine.rbac.rbac_allows`）——
  只读端点要求 `document.view`；不满足返回 403 且**如实说明**（不静默降级）。
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from engine import parse_enhance as PE

router = APIRouter(prefix="/api/v1", tags=["解析与标准化增强（P1-1）"])


def _session(request: Request):
    auth = getattr(request.state, "auth", None)
    if auth is None:
        raise HTTPException(status_code=401, detail="未登录")
    return auth


def _require(request: Request, perm: str) -> Any:
    """功能权限判定（唯一权威 `rbac.rbac_allows`）；不满足 ⇒ 403 且说明缺哪一项。"""
    session = _session(request)
    from engine.rbac import rbac_allows          # noqa: PLC0415
    if not rbac_allows(session, perm):
        raise HTTPException(status_code=403, detail="缺少权限：%s" % perm)
    return session


@router.get("/parse/meta", summary="解析增强字典（标准字段 / 行数上限 / 性能说明）")
def parse_meta(request: Request) -> Dict[str, Any]:
    """标准字段字典 + 解析能力说明（**单一权威**：`engine.standard_fields` + `engine.parse_enhance`）。"""
    _require(request, "document.view")
    from engine import extract_service as SVC      # noqa: PLC0415
    from engine import extract_validate as _EV     # noqa: PLC0415
    base = SVC.metadata()
    cap = PE.manifest()
    return {
        "standard_fields": base.get("standard_fields") or {},
        # ★ `base["rules"]` 是 `[{value,label}]`（P0-3 既有形状，**不改**）；
        #   `validation` 是"规则 → 判定口径说明"（供前端 tooltip 与审计引用）。
        "rules": base.get("rules") or [],
        "validation": {str(r): str(_EV.RULE_CN.get(r, r)) for r in _EV.RULES},
        "validation_notes": _validation_notes(),
        "row_caps": cap["row_caps"],
        "row_cap_consistent": cap["consistent"],
        "row_cap_unregistered": cap["unregistered"],
        "parse_notes": {
            "cursor": "顺序游标增量读（O(n²)→O(n)）；跳转/回退时退回区间读，结果逐元素等价",
            "safe_nrows": "缺 worksheet dimension 的 xlsx（max_row=None）不再崩溃，回退安全行数",
            "truncation": "超过解析上限的行**不再静默丢弃**，由 truncation_note 显式回执",
        },
    }


def _validation_notes() -> Dict[str, str]:
    """规则判定口径说明（唯一来源：`config/standard_fields.json::_validation`）。"""
    import json as _json                           # noqa: PLC0415
    import os as _os                               # noqa: PLC0415
    try:
        path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                             "config", "standard_fields.json")
        with open(path, "r", encoding="utf-8") as fh:
            data = _json.load(fh)
        return {str(k): str(v) for k, v in (data.get("_validation") or {}).items()}
    except Exception:                              # noqa: BLE001
        return {}


@router.get("/parse/cap-manifest", summary="行数上限登记清单（源码 ↔ 登记表一致性）")
def cap_manifest(request: Request) -> Dict[str, Any]:
    """上限登记表与源码实测集合的一致性（供自证与前端呈现）。"""
    _require(request, "document.view")
    return PE.manifest()


@router.get("/documents/{document_id}/field-coverage",
            summary="标准字段覆盖度体检（哪一列没被认出来）")
def field_coverage(document_id: int, request: Request) -> Dict[str, Any]:
    """对某份已解析资料做**只读**覆盖度体检：每个标准字段命中多少行。

    ★ 只读统计，**不下结论**（是否算"缺失"由 `engine.extract_validate` 判）。
    """
    session = _require(request, "document.view")
    from engine import extract_service as SVC      # noqa: PLC0415
    from engine.standard_fields import fields_of_domain, domain_cn   # noqa: PLC0415
    try:
        got = SVC.get_extracted(document_id, session)
    except SVC.ExtractError as exc:
        raise HTTPException(status_code=int(exc.status), detail=str(exc.message)) from exc
    tables = got.get("tables") or []
    out_tables = []
    for t in tables:
        rows = t.get("rows") or []
        dom = str(t.get("domain") or "")
        names = [str(f.get("name")) for f in fields_of_domain(dom)] if dom else []
        if not names:
            names = [str(f.get("name")) for f in
                     (got.get("standard_fields") or {}).get("fields", [])]  # type: ignore[union-attr]
        cov = PE.field_coverage(rows, names) if names else {"rows": len(rows), "fields": {}}
        out_tables.append({
            "table": t.get("table_name") or t.get("name") or "",
            "domain": dom, "domain_cn": t.get("domain_cn") or domain_cn(dom),
            "coverage": cov,
        })
    return {"document_id": int(document_id), "tables": out_tables,
            "table_count": len(out_tables)}


__all__ = ["router"]

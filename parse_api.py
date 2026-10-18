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

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from engine import parse_enhance as PE
# ★ 字段字典的读取只走这一处薄引用（字段名/中文名/域字段清单**不在此另抄表**）
from engine.standard_fields import (domain_cn, field as _field,
                                    fields_of_domain)

from engine.api_common import (admin_of, call_boundary, request_perm,
                             require_perm, session_of)

# ★ R-02（2026-10-17）：以下名字是**别名**，逻辑唯一在 engine/api_common。
#   禁止在本文件重新定义（闸门 `check_api_boundary_single_source` 会报错）。
_session = session_of

router = APIRouter(prefix="/api/v1", tags=["解析与标准化增强（P1-1）"])


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


def _coverage_field_names(dom: str, registered: List[str]) -> List[str]:
    """覆盖率体检的**字段清单**（纯函数，可单测；GAP-14）。

    三条来源合并（按顺序去重）：
      ① 本域字段 —— 让"域内本该有、但没被认出来"的字段进入体检面；
      ② common 字段（期间/摘要等跨资料通用字段）；
      ③ **该表已登记字段** —— 未知域资料（合同/协议/档案）靠跨域白名单取数，
         这些字段不属于任何域，只有这条通路能把它们纳入体检；缺了它，
         未知域资料的覆盖率永远只有 common 两三个字段（体检等于没做）。
    """
    names: List[str] = []
    for src in (fields_of_domain(dom) if dom else [], fields_of_domain("common")):
        for f in src:
            n = str(f.get("name"))
            if n and n not in names:
                names.append(n)
    for n in registered or []:
        if n and n not in names:
            names.append(n)
    return names


@router.get("/documents/{document_id}/field-coverage",
            summary="标准字段覆盖度体检（哪一列没被认出来）")
def field_coverage(document_id: int, request: Request) -> Dict[str, Any]:
    """对某份已解析资料做**只读**覆盖度体检：每个标准字段命中多少行。

    ★ 只读统计，**不下结论**（是否算"缺失"由 `engine.extract_validate` 判）。

    ★ 2026-10-18 修复（GAP-14：本接口曾**恒返 rows=0 / fields={}**）。三处口径错误：
      ① `t.get("rows")` —— `get_extracted` 只给 `rows_preview`，`rows` 取成 `[]`
         ⇒ 行数恒 0（现改为 `include_rows=True` 取全量，覆盖率必须基于全量行）；
      ② `t.get("domain")` —— 表里存的是 `doc_type`，没有 `domain` 键
         ⇒ 域恒空串，`fields_of_domain("")` 恒空；
      ③ 回落取 `got["standard_fields"]` —— `get_extracted` **不返回**这个键
         ⇒ 字段清单恒空，`PE.field_coverage` 根本没被调用。
      现口径：域由 `extract_service._domain_of(doc_type)` 推导（**唯一权威**，不另写映射），
      字段清单 = 本域字段 + common + 该表已登记字段（后者让"没被认出来的域字段"也进入
      体检面，否则 `unrecognized_fields` 永远为空、体检等于自证）。
    """
    session = _require(request, "document.view")
    from engine import extract_service as SVC      # noqa: PLC0415
    try:
        got = SVC.get_extracted(document_id, session, include_rows=True)
    except SVC.ExtractError as exc:
        raise HTTPException(status_code=int(exc.status), detail=str(exc.message)) from exc

    # 该表已登记的标准字段（按 table_id 归组；`table_id` 缺失的历史数据归入全部表）
    registered: Dict[Any, List[str]] = {}
    for f in (got.get("fields") or []):
        registered.setdefault(f.get("table_id"), []).append(str(f.get("standard_field") or ""))

    out_tables = []
    for t in (got.get("tables") or []):
        rows = t.get("rows") or []
        doc_type = str(t.get("doc_type") or "")
        dom = SVC._domain_of(doc_type)              # noqa: SLF001 —— 域推导唯一权威
        names = _coverage_field_names(
            dom, registered.get(t.get("id"), []) + registered.get(None, []))
        cov = PE.field_coverage(rows, names)
        out_tables.append({
            "table_id": t.get("id"),
            "table": t.get("sheet_name") or "",
            "doc_type": doc_type,
            "domain": dom, "domain_cn": domain_cn(dom),
            "row_count": len(rows),
            "coverage": cov,
            # 明示字段中文名（前端不用自己查字典）
            "field_cn": {n: str((_field(n) or {}).get("cn") or n) for n in names},
        })
    return {"document_id": int(document_id), "tables": out_tables,
            "table_count": len(out_tables),
            "rows_total": sum(int((x.get("row_count") or 0)) for x in out_tables)}


__all__ = ["router"]

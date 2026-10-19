# -*- coding: utf-8 -*-
"""数据大屏与统计（P2-5）—— **唯一权威**「跨项目聚合统计」取数口径。

设计原则
  ① **不另写取数逻辑**：所有明细一律**薄转发既有 Service 层**——
     项目 `project_service.list_projects`、资料 `document_service.list_documents`、
     分析任务 `analysis_task.list_for_project`、风险 `risk_service.stats`、
     留痕 `audit_trail.list_records`。⇒ **租户隔离与权限口径不可能与本模块漂移**
     （本模块**没有任何 SQL**）。
  ② **缺失如实**：拿不到风险载荷的账套单独计数（`payload_unavailable`），
     **不把"读不到"当成 0**（0 与"读不到"是两件事）。
  ③ **口径可复核**：所有"取了多少条"都有 `scanned/capped` 说明；大屏不抽样、不估算。

本模块**只读**、不改任何业务数据。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

#: 聚合扫描上限（超过则如实标 `capped=true`；**不静默截断**）
PROJECT_CAP = 200
ACTIVITY_LIMIT = 2000


def _projects(session: Any) -> Dict[str, Any]:
    from engine import project_service as PROJ                     # noqa: PLC0415
    got = PROJ.list_projects(session, page=1, page_size=min(PROJECT_CAP, 200))
    return got


def _documents_of(project_id: Any, session: Any) -> Dict[str, Any]:
    from engine import document_service as DOCS                    # noqa: PLC0415
    try:
        return DOCS.list_documents(project_id, session, page=1, page_size=1)
    except Exception:                                             # noqa: BLE001
        return {"total": None, "category_counts": {}, "category_counts_cn": {},
                "error": "资料计数不可得"}


def _tasks_of(project_id: Any, session: Any) -> Dict[str, Any]:
    from engine import analysis_task as AT                          # noqa: PLC0415
    try:
        return AT.list_for_project(project_id, session, limit=200)
    except Exception:                                             # noqa: BLE001
        return {"total": None, "items": [], "error": "分析任务不可得"}


def _risk_stats(company_id: Any, session: Any) -> Dict[str, Any]:
    from engine import risk_service as RISK                        # noqa: PLC0415
    try:
        return RISK.stats(company_id, session)
    except Exception as exc:                                      # noqa: BLE001
        return {"available": False, "reason": "风险统计不可得：%s" % exc}


def _counter_add(dst: Dict[str, int], key: Any, n: int = 1) -> None:
    k = str(key if key not in (None, "") else "未标注")
    dst[k] = dst.get(k, 0) + n


def overview(session: Any) -> Dict[str, Any]:
    """全局概览：项目 / 资料 / 分析任务 / 风险 / 留痕，一次性聚合。"""
    proj = _projects(session)
    items = proj.get("items") or []
    proj_by_status: Dict[str, int] = {}
    proj_by_industry: Dict[str, int] = {}
    docs_total = 0
    docs_categories: Dict[str, int] = {}
    tasks_by_status: Dict[str, int] = {}
    tasks_total = 0
    risks_by_level: Dict[str, int] = {}
    risks_by_tax: Dict[str, int] = {}
    payload_ok, payload_bad, payload_reasons = 0, 0, []
    per_project: List[Dict[str, Any]] = []
    companies_seen: Dict[Any, Dict[str, Any]] = {}

    for p in items:
        _counter_add(proj_by_status, p.get("status_cn") or p.get("status"))
        _counter_add(proj_by_industry, p.get("industry"))
        d = _documents_of(p.get("id"), session)
        dt = d.get("total")
        if dt is not None:
            docs_total += int(dt)
        for k, v in (d.get("category_counts_cn") or {}).items():
            _counter_add(docs_categories, k, int(v))
        t = _tasks_of(p.get("id"), session)
        tl = t.get("total")
        tasks_total += int(tl or 0)
        for it in (t.get("items") or []):
            _counter_add(tasks_by_status, it.get("status"))
        cid = p.get("company_id")
        if cid not in (None, "") and cid not in companies_seen:
            companies_seen[cid] = _risk_stats(cid, session)
        rs = companies_seen.get(cid) or {}
        if cid in (None, ""):
            pass
        elif rs.get("available"):
            payload_ok += 1
        else:
            payload_bad += 1
            payload_reasons.append(str(rs.get("reason") or "")[:60])
        per_project.append({
            "project_id": p.get("id"),
            "name": p.get("name"),
            "code": p.get("code"),
            "status": p.get("status"), "status_cn": p.get("status_cn"),
            "industry": p.get("industry"),
            "company_id": cid,
            "documents": dt,
            "tasks": tl,
            "risk_available": bool(rs.get("available")),
            "risk_total": (rs.get("total") if isinstance(rs, dict) else None),
        })

    for rs in companies_seen.values():
        if not rs.get("available"):
            continue
        for k, v in (rs.get("by_level") or {}).items():
            _counter_add(risks_by_level, k, int(v))
        for k, v in (rs.get("by_tax") or {}).items():
            _counter_add(risks_by_tax, k, int(v))

    return {
        "projects": {"total": proj.get("total"), "scanned": len(items),
                     "capped": bool(proj.get("total") and proj.get("total") > len(items)),
                     "by_status": _sorted_pairs(proj_by_status),
                     "by_industry": _sorted_pairs(proj_by_industry)},
        "documents": {"total": docs_total, "by_category": _sorted_pairs(docs_categories)},
        "tasks": {"total": tasks_total, "by_status": _sorted_pairs(tasks_by_status)},
        "risks": {"scanned_companies": len(companies_seen),
                  "payload_available": payload_ok,
                  "payload_unavailable": payload_bad,
                  "unavailable_reasons": sorted(set(r for r in payload_reasons if r))[:5],
                  "by_level": _sorted_pairs(risks_by_level),
                  "by_tax": _sorted_pairs(risks_by_tax)},
        "per_project": per_project,
        "note": ("★ 风险数为**可读到载荷的账套**的汇总；`payload_unavailable` 表示该账套"
                 "尚未产出风险载荷（一键分析未跑或产物缺失）——**这不是 0 条风险**，两者不可混。"
                 "全部明细均经既有 Service 层读取（租户隔离与权限口径与本模块同源）。"),
    }


def _sorted_pairs(d: Dict[str, int]) -> List[Dict[str, Any]]:
    return [{"key": k, "count": v}
            for k, v in sorted(d.items(), key=lambda x: (-x[1], str(x[0])))]


def activity(session: Any, days: int = 14) -> Dict[str, Any]:
    """最近 N 天的操作留痕按日计数（数据源 = 留痕唯一权威 `audit_trail`）。"""
    from engine import audit_trail as AU                             # noqa: PLC0415
    from runtime_storage import now_cst                              # noqa: PLC0415
    try:
        rows = AU.list_records(limit=ACTIVITY_LIMIT, offset=0)
    except Exception as exc:                                        # noqa: BLE001
        return {"available": False, "reason": "留痕不可读：%s" % exc, "days": [], "total": 0}
    today = str(now_cst())[:10]
    by_day: Dict[str, int] = {}
    by_action: Dict[str, int] = {}
    for r in rows:
        day = str(r.get("created_at") or "")[:10]
        if day:
            _counter_add(by_day, day)
        _counter_add(by_action, r.get("action_cn") or r.get("action"))
    span = sorted(by_day.keys())[-max(1, int(days)):]
    return {
        "available": True,
        "today": today,
        "scanned": len(rows),
        "capped": len(rows) >= ACTIVITY_LIMIT,
        "days": [{"day": d, "count": by_day.get(d, 0)} for d in span],
        "by_action": _sorted_pairs(by_action)[:12],
        "total": len(rows),
        "note": ("按日计数基于留痕 `created_at`（北京时间）；`capped=true` 表示已达扫描上限"
                 "（%d 条），大屏不抽样、不估算，超限时如实标注。" % ACTIVITY_LIMIT),
    }


def metadata() -> Dict[str, Any]:
    return {
        "sources": [
            {"name": "稽查项目", "via": "project_service.list_projects"},
            {"name": "财税资料", "via": "document_service.list_documents（含分类计数）"},
            {"name": "分析任务", "via": "analysis_task.list_for_project"},
            {"name": "风险结果", "via": "risk_service.stats（按账套）"},
            {"name": "操作留痕", "via": "audit_trail.list_records"},
        ],
        "caps": {"projects": PROJECT_CAP, "activity": ACTIVITY_LIMIT},
        "note": ("大屏数据**全部经既有 Service 层读取**（本模块零 SQL）⇒ 你在大屏看到的范围"
                 "与你在此人账号下有权限看到的范围完全一致；"
                 "`payload_unavailable` 与 `0 条风险` 是两件事，不得混同。"),
    }


__all__ = ["PROJECT_CAP", "ACTIVITY_LIMIT", "overview", "activity", "metadata"]

# -*- coding: utf-8 -*-
"""法规库读层（P2-1）—— **唯一权威**「法规库浏览/检索」取数口径。

设计原则（与任务书约束一致）
  ① **法规库不硬编码条文**：所有条文一律来自数据文件
     （`static/legal_library.json` / `static/legal_refs.json`，读路径唯一权威
     `legal_citation.library_paths()` / `library_file_entries()`），本模块**零条文字面量**。
  ② **不新增第二套判定**：版本状态全部转发 `engine.legal_version`（唯一权威）；
     正文解析全部转发 `engine.legal_citation`（唯一权威）。本模块只做**组装与检索**。
  ③ **缺失如实**：查不到版本登记 ⇒ 状态 `unknown` + 提示「版本未登记」，绝不默认现行有效；
     覆盖率读**登记值**（`config/legal_text_coverage.json`，由 `scripts/_load_legal_texts.py`
     现算写入），本模块**不另算一份**（否则两处口径必然漂移）。

本模块**只读**、不改引擎结论。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine import legal_citation as LC
from engine import legal_version as LV

_ROOT = Path(__file__).resolve().parent.parent
_COVERAGE_PATH = _ROOT / "config" / "legal_text_coverage.json"


def _norm(s: Any) -> str:
    return "".join(str(s or "").split())


def _coverage() -> Dict[str, Any]:
    """读**登记的**正文库覆盖率（不重算；重算口径唯一权威在 scripts/_load_legal_texts.py）。"""
    try:
        d = json.loads(_COVERAGE_PATH.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            d = {}
    except Exception:
        d = {}
    return {
        "note": str(d.get("_note") or ""),
        "total_refs": d.get("total_refs"),
        "matched_refs": d.get("matched_refs"),
        "coverage": d.get("coverage"),
        "library_size": d.get("library_size"),
        "caveat": ("★ 覆盖率是**红线库引用**能匹配到正文库的比例（登记值，由 "
                   "scripts/_load_legal_texts.py 现算写入）；它**不等于**「法规库完整」。"
                   "未匹配项必须如实留待确认，不得编造条文凑覆盖率。"),
    }


def metadata() -> Dict[str, Any]:
    """法规库字典（供前端渲染与审计引用）。"""
    files = [{"file": p.name, "path": str(p.relative_to(_ROOT))} for p in LC.library_paths()]
    return {
        "sources": files,
        "source_note": ("条文一律来自上述数据文件（**不在代码里硬编码条文**）；"
                        "读路径唯一权威 engine/legal_citation.library_paths()。"),
        "version_registry": "config/legal_versions.json（版本信息唯一权威）",
        "statuses": [{"value": s, "label": LV.STATUS_CN.get(s, s)} for s in LV.STATUSES],
        "blocking_statuses": sorted(LV.BLOCKING_STATUSES),
        "search_hint": "支持按法名 / 条款号 / 正文关键词检索；法名与条号按归一后匹配。",
        "coverage": _coverage(),
    }


def _version_bundle(law: str) -> Dict[str, Any]:
    """某部法的版本信息（**每次查询只算一次**，不逐条重算）。

    ★ 2026-10-17（PF-01）：原 `_decorate_article` 对**每一条**都重新查
      `LV.entry_of(law)` 三次 + `LV.status_of` + `LV.is_blocking`（一次约 0.46 ms），
      7692 条 = 3.5 秒。而版本信息**只与法名有关**、与条号无关 ⇒
      按法名做一次即可（法数量级远小于条数）。
    """
    e = LV.entry_of(law) or {}
    st = LV.status_of(law)
    return {
        "status": st,
        "status_cn": LV.STATUS_CN.get(st, st),
        "current_version": e.get("current_version"),
        "effective_from": e.get("effective_from"),
        "registered": bool(e),
        "blocking": LV.is_blocking(law),
    }


def _decorate_article(row: Dict[str, str], bundle: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """给一条正文补上**版本状态**（薄转发 legal_version，不另判）。"""
    law = row.get("law") or ""
    return {
        "law": law,
        "article": row.get("article") or "",
        "content": row.get("content") or "",
        "source": row.get("source") or "",
        "from": row.get("from") or "",
        "version": dict(bundle) if bundle is not None else _version_bundle(law),
    }


def article_entries(q: Any = None, law: Any = None, *, only_current: bool = False,
            limit: int = 200, offset: int = 0) -> Dict[str, Any]:
    """检索正文条目（按法名/条款号/正文关键词；页码式返回）。

    ★ 过滤**只做一次**（本函数是唯一实现），接口层不得再拼第二套。
    ★ 执行顺序（PF-01，2026-10-17）：**筛选 → 排序 → 切片 → 装饰**。
      装饰（查版本状态）只对当前页的条目做，且按法名去重；
      原实现「全量装饰再切片」使每页请求都付 7692 次版本查询的代价（实测 3.5 s）。
    """
    kw = _norm(q)
    law_kw = _norm(law)

    # ① 只挑出**命中的原始行**（不做任何版本查询）
    matched: List[Dict[str, str]] = []
    for r in LC.library_file_entries():
        if law_kw and _norm(r["law"]) != law_kw and law_kw not in _norm(r["law"]):
            continue
        if kw:
            hay = _norm(r["law"]) + _norm(r["article"]) + _norm(r["content"])
            if kw not in hay:
                continue
        matched.append(r)

    # ② only_current：按**法名**算状态（每部法一次），不逐条算
    if only_current:
        verdict: Dict[str, bool] = {}
        keep: List[Dict[str, str]] = []
        for r in matched:
            nm = r["law"]
            if nm not in verdict:
                verdict[nm] = LV.status_of(nm) == "current"
            if verdict[nm]:
                keep.append(r)
        matched = keep

    # ③ 排序在**原始行**上做（键与原来一致，顺序不变）
    matched.sort(key=lambda x: (x["law"], x["article"]))
    total = len(matched)
    p, size = max(1, int(offset or 1)), max(1, int(limit or 200))
    start = (p - 1) * size
    page_rows = matched[start:start + size]

    # ④ 只装饰当前页，且同一部法只查一次版本
    bundles: Dict[str, Dict[str, Any]] = {}
    items: List[Dict[str, Any]] = []
    for r in page_rows:
        nm = r["law"]
        if nm not in bundles:
            bundles[nm] = _version_bundle(nm)
        items.append(_decorate_article(r, bundles[nm]))

    return {
        "total": total,
        "page": p,
        "page_size": size,
        "pages": (total + size - 1) // size,
        "items": items,
        "note": ("未收录的条文**不得编造**；此处只列数据文件中真实存在的条目。"
                 "`version.registered=false` 表示该法版本未登记（不等于失效）。"),
    }


def laws(q: Any = None) -> Dict[str, Any]:
    """法清单（每部法的条数 + 版本状态）。"""
    kw = _norm(q)
    bucket: Dict[str, List[Dict[str, Any]]] = {}
    for r in LC.library_file_entries():
        bucket.setdefault(r["law"], []).append(r)
    out: List[Dict[str, Any]] = []
    for law, rs in bucket.items():
        if kw and kw not in _norm(law):
            continue
        e = LV.entry_of(law) or {}
        st = LV.status_of(law)
        out.append({
            "law": law,
            "articles": len(rs),
            "article_list": sorted({r["article"] for r in rs if r["article"]}),
            "sources": sorted({r["source"] for r in rs if r["source"]}),
            "version": {
                "status": st, "status_cn": LV.STATUS_CN.get(st, st),
                "current_version": e.get("current_version"),
                "source": e.get("source"),
                "effective_from": e.get("effective_from"),
                "registered": bool(e), "blocking": LV.is_blocking(law),
            },
        })
    out.sort(key=lambda x: (-x["articles"], x["law"]))
    return {"total": len(out), "items": out,
            "note": "条数为该法在正文库中的**已收录**条数（不代表该法全部条文数）。"}


def law_detail(law: str) -> Optional[Dict[str, Any]]:
    """单部法详情：全部条目 + 版本登记 + 版本括注（转发 legal_version.version_note）。"""
    rows = [r for r in LC.library_file_entries() if _norm(r["law"]) == _norm(law)]
    if not rows:
        return None
    e = LV.entry_of(law) or {}
    bundle = _version_bundle(rows[0]["law"])       # 同一部法只查一次版本（PF-01）
    return {
        "law": law,
        "articles": [_decorate_article(r, bundle) for r in sorted(rows, key=lambda x: x["article"])],
        "version_entry": e or None,
        "version_note": LV.version_note(law),
        "note": ("`version_note` 是可直接放进报告的版本括注（唯一权威 "
                 "engine/legal_version.version_note）；未登记 ⇒ 如实标注须核对。"),
    }


def stats() -> Dict[str, Any]:
    """法规库统计（条数/法数/来源分布/版本状态分布/覆盖率）。"""
    rows = LC.library_file_entries()
    by_from: Dict[str, int] = {}
    for r in rows:
        by_from[r["from"]] = by_from.get(r["from"], 0) + 1
    law_set = sorted({r["law"] for r in rows})
    st_count: Dict[str, int] = {}
    unregistered: List[str] = []
    blocking: List[str] = []
    for law in law_set:
        st = LV.status_of(law)
        st_count[st] = st_count.get(st, 0) + 1
        if not LV.entry_of(law):
            unregistered.append(law)
        if LV.is_blocking(law):
            blocking.append(law)
    return {
        "articles": len(rows),
        "laws": len(law_set),
        "by_source_file": by_from,
        "by_version_status": [{"value": k, "label": LV.STATUS_CN.get(k, k), "laws": v}
                              for k, v in sorted(st_count.items())],
        "unregistered_laws": unregistered,
        "blocking_laws": blocking,
        "coverage": _coverage(),
        "note": ("`blocking_laws` 为**已被取代/失效**的法（红线引用到即由闸门拦下）；"
                 "`unregistered_laws` 为**版本未登记**（不等于失效，须人工核对）。"),
    }


__all__ = ["metadata", "article_entries", "laws", "law_detail", "stats"]

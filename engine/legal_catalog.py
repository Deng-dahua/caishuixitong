# -*- coding: utf-8 -*-
"""**法规目录 + 法规关系**读层（STEP-EXT-LEGAL-FULL-MATCH 步骤 22）—— 唯一读路径。

★★ **三层结构**（务必分清，项目铁律）：
  ① **目录**（本模块读的 `config/legal_catalog.json`，7564 条）= 三源全量元数据
     （标题/文号/发文机关/发布日期/类型/效力标签/URL）；**不代表已有正文**。
  ② **条款索引**（`config/legal_provisions.json`，131 条）= 已核实条款的定位与标签；
     由 `engine.legal_mapping.provision_index()` 提供。
  ③ **正文**（`static/legal_library.json`，唯一录入权威 `scripts/_load_legal_texts.py`）。
  ⇒ 目录条目 `has_body_in_library=false` 时**只给官方 URL**，**不得**给出条文内容。

★ 关系（`config/legal_relations.json`，2750 条）：`amended`（修订/修正）/
  `abolished`（废止/失效）/ `cited_by`（据以制定/依据）。每条都带 `evidence` 原文可复核；
  解析不出的进 `unresolved`，**不猜**。

★ 只读：不改引擎结论、不写盘。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
_CFG = _ROOT / "config"

_CACHE: Dict[str, Any] = {}


def reset_cache() -> None:
    _CACHE.clear()


def _j(name: str) -> Dict[str, Any]:
    try:
        d = json.loads((_CFG / name).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception as exc:                                     # noqa: BLE001
        return {"_error": str(exc)}


def _cat() -> Dict[str, Any]:
    if "cat" not in _CACHE:
        d = _j("legal_catalog.json")
        d.setdefault("available", bool(d.get("items")))
        _CACHE["cat"] = d
    return _CACHE["cat"]


def _rel() -> Dict[str, Any]:
    if "rel" not in _CACHE:
        d = _j("legal_relations.json")
        d.setdefault("available", bool(d.get("relations")))
        _CACHE["rel"] = d
    return _CACHE["rel"]


def available() -> bool:
    return bool(_cat().get("available"))


def stats() -> Dict[str, Any]:
    c = _cat()
    r = _rel()
    return {
        "available": available(),
        "catalog_total": int(c.get("count") or 0),
        "by_kind": dict(c.get("by_kind") or {}),
        "by_source": dict(c.get("by_source") or {}),
        "with_body": c.get("with_body"),
        "relations_total": int((r.get("stats") or {}).get("total") or 0),
        "relations_by_type": dict((r.get("stats") or {}).get("by_relation") or {}),
        "relation_types": dict(r.get("relation_types") or {}),
        "relation_unresolved": int((r.get("stats") or {}).get("unresolved") or 0),
        "updated": str(c.get("updated") or ""),
        "authority": {"catalog": "config/legal_catalog.json",
                      "relations": "config/legal_relations.json",
                      "body": "static/legal_library.json（唯一录入权威）"},
        "note": ("「目录」= 三源全量元数据，**不代表已有正文**；"
                 "`has_body_in_library=false` 的条目只能点 URL 去官方原文（不编造条文）。"),
    }


def list_documents(*, kind: Any = None, source: Any = None, q: Any = None,
                   year: Any = None, with_body: Any = None,
                   page: int = 1, page_size: int = 50) -> Dict[str, Any]:
    """**全量法规目录**检索（7564 条；按类型/来源/年份/有无正文筛选 + 关键词 + 分页）。"""
    if not available():
        return {"total": 0, "items": [], "available": False,
                "note": "法规目录不可用（`config/legal_catalog.json` 缺失）⇒ 如实为空。"}
    items = _cat().get("items") or []
    kd = str(kind or "").strip()
    if kd:
        items = [x for x in items if str(x.get("kind")) == kd]
    sc = str(source or "").strip()
    if sc:
        items = [x for x in items if str(x.get("source")) == sc]
    yr = str(year or "").strip()
    if yr:
        items = [x for x in items if str(x.get("published_at") or "").startswith(yr)]
    if with_body is not None and str(with_body).strip() != "":
        want = str(with_body).strip().lower() in ("1", "true", "yes", "on")
        items = [x for x in items if bool(x.get("has_body_in_library")) == want]
    kw = "".join(str(q or "").split())
    if kw:
        items = [x for x in items
                 if kw in str(x.get("title")) or kw in str(x.get("doc_no"))
                 or kw in str(x.get("labels")) or kw in str(x.get("tax_policy"))]
    items = sorted(items, key=lambda x: str(x.get("published_at") or ""), reverse=True)
    total = len(items)
    p = max(1, int(page or 1))
    ps = max(1, min(int(page_size or 50), 200))
    return {"total": total, "page": p, "page_size": ps,
            "pages": (total + ps - 1) // ps if total else 0,
            "items": items[(p - 1) * ps: p * ps],
            "kind": kd, "source": sc, "year": yr, "q": str(q or ""),
            "note": ("条目来自 `config/legal_catalog.json`（税务/财税三源全量抓取）；"
                     "`has_body_in_library=false` ⇒ 正文未核实录入，请点 `url` 查官方原文。")}


def document(index: Any = None, *, url: Any = None) -> Dict[str, Any]:
    """单条目录详情（按数组下标或 URL）+ **该法规的关系（废止/修订/依据）**。"""
    if not available():
        return {"found": False, "available": False, "note": "法规目录不可用。"}
    items = _cat().get("items") or []
    d: Optional[Dict[str, Any]] = None
    if url:
        u = str(url)
        d = next((x for x in items if str(x.get("url")) == u), None)
    else:
        try:
            i = int(index)
            if 0 <= i < len(items):
                d = items[i]
        except Exception:                                        # noqa: BLE001
            d = None
    if d is None:
        return {"found": False, "available": True,
                "note": "按给定下标/URL 查不到该目录条目（不近似匹配、不猜测）。"}
    out = dict(d)
    out["found"] = True
    out["relations"] = relations_of(title=d.get("title"), doc_no=d.get("doc_no"))
    out["body_note"] = ("该法规正文**已核实录入**正文库，可在「法规库」页按法名检索条文。"
                        if d.get("has_body_in_library") else
                        "该法规正文**尚未核实录入**正文库 ⇒ 这里不提供条文内容，"
                        "请点 `url` 查看官方原文（不编造条文）。")
    return out


def relations_of(*, title: Any = None, doc_no: Any = None) -> Dict[str, Any]:
    """查某法规的**关系链**（作为主体被废止/修订/依据），并给出双向说明。

    ★ 匹配口径：**标题或文号精确/包含**匹配 `subject_title` / `subject_doc_no`；
      查不到 ⇒ 如实空 + `reason`（**不得**猜测"应该有关系"）。
    """
    r = _rel()
    if not r.get("available"):
        return {"total": 0, "items": [], "available": False,
                "note": "关系表不可用（`config/legal_relations.json` 缺失）⇒ 如实为空。"}
    t = "".join(str(title or "").split())
    dn = "".join(str(doc_no or "").split())
    out: List[Dict[str, Any]] = []
    for x in (r.get("relations") or []):
        st = "".join(str(x.get("subject_title") or "").split())
        sd = "".join(str(x.get("subject_doc_no") or "").split())
        hit = False
        if t and st and (t in st or st in t):
            hit = True
        if not hit and dn and sd and (dn in sd or sd in dn):
            hit = True
        if hit:
            out.append({
                "relation": x.get("relation"), "relation_cn": x.get("relation_cn"),
                "target": x.get("target"), "targets_all": x.get("targets_all") or [],
                "date": x.get("date"), "evidence": x.get("evidence"),
                "basis": x.get("basis"), "source": x.get("source"),
                "subject_title": x.get("subject_title"),
                "subject_doc_no": x.get("subject_doc_no"), "subject_url": x.get("subject_url"),
            })
    out.sort(key=lambda x: (str(x.get("relation") or ""), str(x.get("date") or "")))
    res: Dict[str, Any] = {"total": len(out), "items": out,
                           "relation_types": dict(r.get("relation_types") or {}),
                           "note": ("关系来自 `config/legal_relations.json`"
                                    "（源：fgk 题注 + flk 历史沿革/相关制度）；"
                                    "每条 `evidence` 为原文，可复核。")}
    if not out:
        res["reason"] = ("未查到该法规的关系记录 —— 可能是①该法规的题注未含关系信息，"
                         "或②标题/文号与关系表主体不一致。**如实为空，不推测**。")
    return res


def relations(*, relation: Any = None, q: Any = None,
              page: int = 1, page_size: int = 50) -> Dict[str, Any]:
    """关系表检索（按类型 + 关键词；分页）。"""
    r = _rel()
    if not r.get("available"):
        return {"total": 0, "items": [], "available": False, "note": "关系表不可用。"}
    rows = list(r.get("relations") or [])
    rl = str(relation or "").strip()
    if rl:
        rows = [x for x in rows if str(x.get("relation")) == rl]
    kw = "".join(str(q or "").split())
    if kw:
        rows = [x for x in rows
                if kw in str(x.get("subject_title")) or kw in str(x.get("target"))
                or kw in str(x.get("evidence"))]
    rows.sort(key=lambda x: str(x.get("date") or ""), reverse=True)
    total = len(rows)
    p = max(1, int(page or 1))
    ps = max(1, min(int(page_size or 50), 200))
    return {"total": total, "page": p, "page_size": ps,
            "pages": (total + ps - 1) // ps if total else 0,
            "items": rows[(p - 1) * ps: p * ps],
            "relation": rl, "q": str(q or ""),
            "relation_types": dict(r.get("relation_types") or {}),
            "unresolved_total": int((r.get("stats") or {}).get("unresolved") or 0),
            "note": ("`amended`=修订/修正；`abolished`=废止/失效；`cited_by`=据以制定/依据。"
                     "解析不出的条目进 `unresolved`（`reason` 写明），**不猜**。")}


__all__ = ["available", "reset_cache", "stats", "list_documents", "document",
           "relations_of", "relations"]

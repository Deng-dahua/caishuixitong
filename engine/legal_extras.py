# -*- coding: utf-8 -*-
"""案例 / 解读 / 问答 **材料读层**（STEP-EXT-LEGAL-FULL-MATCH 步骤 19）—— 唯一读路径。

数据权威：`config/legal_materials.json`（由 `scripts/_gen_legal_materials.py` 幂等生成，
关联结论派生自**官方摘要原文的显式引用**，非关键词匹配）。

★★ 粒度如实（防"假精确"）：
  材料与法规的关联**只到「法规」级**（该材料显式引用了某部法）；
  **不能**确证到「条款」级（摘要通常不写条号）⇒ `for_provision()` 返回的
  `granularity="law"`，调用方**不得**把它当作"该案例适用第 N 条"的论断。

★ 缺失如实：材料库不存在 ⇒ `available()=False`，各查询返回空并说明原因，不伪造。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from engine import legal_mapping as LM          # `law_code_of` 唯一实现在此（本模块转发）

_ROOT = Path(__file__).resolve().parent.parent
_PATH = _ROOT / "config" / "legal_materials.json"

_CACHE: Dict[str, Any] = {}


def reset_cache() -> None:
    _CACHE.clear()


def _doc() -> Dict[str, Any]:
    if "doc" in _CACHE:
        return _CACHE["doc"]
    try:
        d = json.loads(_PATH.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            d = {}
    except Exception as exc:                                     # noqa: BLE001
        d = {"_error": str(exc)}
    d.setdefault("available", bool(d.get("materials")))
    _CACHE["doc"] = d
    return d


def available() -> bool:
    return bool(_doc().get("available"))


def law_code_of(provision_id: Any) -> str:
    """条款 ID → 法短码。**转发** `legal_mapping.law_code_of`（唯一实现，防两处漂移）。"""
    return LM.law_code_of(provision_id)


def _by_law() -> Dict[str, List[Dict[str, Any]]]:
    if "by_law" in _CACHE:
        return _CACHE["by_law"]
    idx = {m["material_id"]: m for m in (_doc().get("materials") or [])}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for code, ids in (_doc().get("by_law_code") or {}).items():
        for i in ids:
            m = idx.get(i)
            if m:
                out.setdefault(code, []).append(m)
    _CACHE["by_law"] = out
    return out


def _brief_material(m: Dict[str, Any], law_code: str) -> Dict[str, Any]:
    """轻量形状（列表用）：不带完整摘要，只给定位 + 命中证据。"""
    refs = [h for h in (m.get("matched_refs") or []) if h.get("law_code") == law_code]
    return {
        "material_id": m.get("material_id"),
        "kind": m.get("kind"),
        "title": m.get("title"),
        "published_at": m.get("published_at"),
        "publisher": m.get("publisher"),
        "doc_no": m.get("doc_no"),
        "url": m.get("url"),
        "matched_ref": (refs[0]["matched_ref"] if refs else ""),
        "matched_by": (refs[0]["matched_by"] if refs else ""),
    }


def for_law(law_code: Any, *, kind: Any = None, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """某部法被哪些官方材料**显式引用**（按发布时间倒序；分页）。"""
    code = str(law_code or "")
    if not available():
        return {"total": 0, "items": [], "available": False, "law_code": code,
                "note": "材料库不可用（`config/legal_materials.json` 缺失）⇒ 如实为空，不伪造。"}
    items = [m for m in _by_law().get(code, []) if (not kind or m.get("kind") == kind)]
    items.sort(key=lambda m: str(m.get("published_at") or ""), reverse=True)
    total = len(items)
    off, lim = max(0, int(offset or 0)), max(1, min(int(limit or 20), 200))
    return {"total": total, "law_code": code, "kind": kind or "", "offset": off, "limit": lim,
            "items": [_brief_material(m, code) for m in items[off:off + lim]],
            "granularity": "law",
            "note": "关联粒度=**法规级**（材料显式引用了该法），非条款级。"}


def for_provision(provision_id: Any, *, limit: int = 5, offset: int = 0) -> Dict[str, Any]:
    """某**条款**的相关官方材料（★ 粒度仍是**法规级**，见模块 docstring）。"""
    pid = str(provision_id or "")
    got = for_law(law_code_of(pid), limit=limit, offset=offset)
    got["provision_id"] = pid
    got["note"] = ("材料与法规的关联只到**法规级**（该材料引用了所属法），"
                   "**不等于**该材料适用本条条款 ⇒ 只作参考线索，不得当定性依据。")
    return got


def search(kind: Any = None, q: Any = None, *, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """在材料**标题+摘要**上字面检索（不做语义推断）。"""
    if not available():
        return {"total": 0, "items": [], "available": False,
                "note": "材料库不可用 ⇒ 如实为空。"}
    kw = "".join(str(q or "").split())
    kd = str(kind or "")
    items = []
    for m in (_doc().get("materials") or []):
        if kd and m.get("kind") != kd:
            continue
        if kw and kw not in (str(m.get("title") or "") + str(m.get("snippet") or "")):
            continue
        items.append(m)
    items.sort(key=lambda m: str(m.get("published_at") or ""), reverse=True)
    total = len(items)
    off, lim = max(0, int(offset or 0)), max(1, min(int(limit or 20), 200))
    return {"total": total, "kind": kd, "q": str(q or ""), "offset": off, "limit": lim,
            "items": items[off:off + lim],
            "note": "标题+摘要**字面**检索（不做语义推断）；命中处原文见 `matched_refs`。"}


def stats() -> Dict[str, Any]:
    d = _doc()
    c = dict(d.get("counts") or {})
    c["available"] = available()
    c["updated"] = str(d.get("updated") or "")
    c["authority"] = "config/legal_materials.json"
    c["source"] = str(d.get("source") or "")
    return c


__all__ = ["available", "reset_cache", "for_law", "for_provision", "search", "stats",
           "law_code_of"]

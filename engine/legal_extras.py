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


def _brief(m: Dict[str, Any], *, with_snippet: bool = True) -> Dict[str, Any]:
    """列表用形状（可关掉摘要以控体积）。"""
    out = {
        "material_id": m.get("material_id"), "kind": m.get("kind"),
        "title": m.get("title"), "published_at": m.get("published_at"),
        "publisher": m.get("publisher"), "doc_no": m.get("doc_no"),
        "url": m.get("url"), "source": m.get("source"),
        "related_law_codes": list(m.get("related_law_codes") or []),
        "matched_refs": list(m.get("matched_refs") or []),
        "granularity": m.get("granularity"),
    }
    if with_snippet:
        out["snippet"] = m.get("snippet")
    return out


def list_materials(*, kind: Any = None, q: Any = None, law_code: Any = None,
                   linked: Any = None, page: int = 1, page_size: int = 20,
                   with_snippet: bool = True) -> Dict[str, Any]:
    """**材料列表**（案例/解读/问答；按类型 / 关键词 / 关联法 / 是否已关联筛选 + 分页）。

    ★ 与 `search` 的差别：本函数是**列表页专用**（分页 + 多维筛选 + 可按需关摘要），
      `search` 保留为向后兼容的薄转发。
    """
    if not available():
        return {"total": 0, "items": [], "available": False,
                "note": "材料库不可用（`config/legal_materials.json` 缺失）⇒ 如实为空。"}
    items = list(_doc().get("materials") or [])
    kd = str(kind or "").strip()
    if kd:
        items = [m for m in items if str(m.get("kind")) == kd]
    lc = str(law_code or "").strip()
    if lc:
        items = [m for m in items if lc in (m.get("related_law_codes") or [])]
    if linked is not None and str(linked).strip() != "":
        want = str(linked).strip().lower() in ("1", "true", "yes", "on")
        items = [m for m in items if bool(m.get("related_law_codes")) == want]
    kw = "".join(str(q or "").split())
    if kw:
        items = [m for m in items
                 if kw in str(m.get("title")) or kw in str(m.get("snippet"))
                 or kw in str(m.get("doc_no"))]
    # 类型 → 数量分布（**以筛选后的集合为准**，与列表一致，避免"数字与列表对不上"）
    from collections import Counter
    by_kind = dict(Counter(str(m.get("kind") or "") for m in items).most_common())
    items.sort(key=lambda m: str(m.get("published_at") or ""), reverse=True)
    total = len(items)
    p = max(1, int(page or 1))
    ps = max(1, min(int(page_size or 20), 200))
    return {"total": total, "page": p, "page_size": ps,
            "pages": (total + ps - 1) // ps if total else 0,
            "items": [_brief(m, with_snippet=with_snippet)
                      for m in items[(p - 1) * ps: p * ps]],
            "by_kind": by_kind, "kind": kd, "q": str(q or ""), "law_code": lc,
            "note": ("材料来自三平台官方发布（标题+摘要原文）；"
                     "`related_law_codes` 是材料**显式引用**的法（书名号 / 带法规后缀全名），"
                     "关联**只到法规级**，不代表适用某条款。")}


def material_detail(material_id: Any) -> Dict[str, Any]:
    """单条材料详情（含关联法规的规范名 + 该法**已核实条款** + 引用该法条款的**规则**）。"""
    if not available():
        return {"found": False, "available": False, "note": "材料库不可用。"}
    mid = str(material_id or "")
    m = next((x for x in (_doc().get("materials") or [])
              if str(x.get("material_id")) == mid), None)
    if m is None:
        return {"found": False, "available": True,
                "note": "无此材料 id（不近似匹配、不猜测）。"}
    out = dict(m)
    out["found"] = True
    # 关联法规：法短码 → 规范名 + 已核实条款 + 引用这些条款的规则
    from engine import legal_mapping as LM
    laws: List[Dict[str, Any]] = []
    for code in (m.get("related_law_codes") or []):
        hits = [h for h in (m.get("matched_refs") or [])
                if str((h or {}).get("law_code")) == code]
        laws.append({
            "law_code": code,
            "law_name": (hits[0].get("matched_ref") if hits else code),
            "matched_by": (hits[0].get("matched_by") if hits else ""),
            "rules_using": _rules_of_law(code),
        })
    out["related_laws"] = laws
    out["granularity"] = "law"
    out["granularity_note"] = ("关联**只到法规级**（材料显式引用了该法）；"
                              "**不代表**该材料适用某具体条款 ⇒ 参考线索，不作定性依据。")
    return out


def _rules_of_law(law_code: Any) -> List[Dict[str, Any]]:
    """引用某部法（经其已确证条款）的**规则**清单（反查）。

    ★ 数据链路：规则 → 条款（`legal_mapping`）→ 条款所属法（`law_code_of`）。
      只返回**有可确证条款**的规则；查不到 ⇒ 空列表（如实）。
    """
    if "law_rules" not in _CACHE:
        from engine import legal_mapping as LM                     # noqa: PLC0415
        idx: Dict[str, List[Dict[str, Any]]] = {}
        for m in LM.mapping_rows():                                # 公开入口（不取私有）
            if not m.get("verified"):
                continue
            code = LM.law_code_of(m.get("provision_id"))
            if not code:
                continue
            bucket = idx.setdefault(code, [])
            rid = str(m.get("rule_id") or "")
            if any(x["rule_id"] == rid for x in bucket):
                continue
            bucket.append({"rule_id": rid, "provision_id": m.get("provision_id"),
                           "law": m.get("law"), "article": m.get("article")})
        _CACHE["law_rules"] = idx
    return list(_CACHE["law_rules"].get(str(law_code or ""), []))


def search(kind: Any = None, q: Any = None, *, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """在材料**标题+摘要**上字面检索（**保留原签名**，薄转发 `list_materials`）。"""
    return list_materials(kind=kind, q=q, page=int(offset or 0) + 1,
                          page_size=limit, with_snippet=True)


def stats() -> Dict[str, Any]:
    d = _doc()
    c = dict(d.get("counts") or {})
    c["available"] = available()
    c["updated"] = str(d.get("updated") or "")
    c["authority"] = "config/legal_materials.json"
    c["source"] = str(d.get("source") or "")
    return c


__all__ = ["available", "reset_cache", "for_law", "for_provision", "search",
           "stats", "law_code_of", "list_materials", "material_detail"]

# -*- coding: utf-8 -*-
"""案例 / 解读 / 问答 **材料读层** —— 唯一读路径。

数据权威：`config/legal_materials.json`（由 `scripts/_gen_legal_materials.py` 幂等生成，
关联结论派生自**官方原文的显式引用**，非关键词匹配）。

★★ 粒度**三态如实**（2026-10-15 补采正文后由两态升级为三态；防"假精确"与"假粗糙"）：
  · `granularity="provision"` —— 材料**正文**里出现「法名**紧邻**条号」，且该条款 ID
    在 `config/legal_provisions.json` 中真实存在 ⇒ 关联**到条款级**；
  · `granularity="law"` —— 只确证到「引用了某部法」（正文无「法名紧邻条号」写法）⇒
    **不得**当作"该案例适用第 N 条"的论断；
  · `granularity="none"` —— 连法规引用都未确证 ⇒ 如实留空。
  ★ `for_provision()` **优先**返回条款级命中；无命中才退回法规级，并在 `granularity` 里说明。

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
        "granularity": m.get("granularity"),
        "provision_ids": list(m.get("provision_ids") or []),
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
            "note": ("本查询的关联层级=**法**（材料显式引用了《%s》）；"
                     "每条材料自带更细粒度：`provision`（其正文含「法名紧邻条号」）/"
                     "`law` / `none`，需要条款级请用 `for_provision(条款ID)`。" % code)}


def for_provision(provision_id: Any, *, limit: int = 5, offset: int = 0) -> Dict[str, Any]:
    """某**条款**的相关官方材料。

    ★ 两级优先（2026-10-15）：先取**条款级**命中（材料正文显式引用了该条款 ID），
      无命中才**如实退回**法规级并标 `granularity="law"` —— 不再一律说"只到法规级"。
    """
    pid = str(provision_id or "")
    if not available():
        return {"total": 0, "items": [], "available": False, "provision_id": pid,
                "granularity": "none", "note": "材料库不可用 ⇒ 如实为空，不伪造。"}
    exact = [m for m in (_doc().get("materials") or []) if pid in (m.get("provision_ids") or [])]
    exact.sort(key=lambda m: str(m.get("published_at") or ""), reverse=True)
    if exact:
        off, lim = max(0, int(offset or 0)), max(1, min(int(limit or 5), 200))
        code = law_code_of(pid)
        return {"total": len(exact), "provision_id": pid, "law_code": code,
                "offset": off, "limit": lim,
                "items": [_brief_material(m, code) for m in exact[off:off + lim]],
                "granularity": "provision",
                "note": ("关联粒度=**条款级**：材料正文出现「法名紧邻条号」的显式引用，"
                         "且该条款 ID 已登记。仍属**参考线索**，个案适用与否需人工判断。")}
    got = for_law(law_code_of(pid), limit=limit, offset=offset)
    got["provision_id"] = pid
    got["granularity"] = "law"
    got["note"] = ("**无条款级命中** ⇒ 退回法规级（有材料引用了所属法，但正文未出现"
                   "「法名紧邻本条款号」的写法）⇒ 只作参考线索，**不得**当作"
                   "「该材料适用本条」的依据。")
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
        "provision_ids": list(m.get("provision_ids") or []),
        "content_len": int(m.get("content_len") or 0),
    }
    if with_snippet:
        out["snippet"] = m.get("snippet")
    return out


def list_materials(*, kind: Any = None, q: Any = None, law_code: Any = None,
                   linked: Any = None, granularity: Any = None,
                   provision_id: Any = None,
                   page: int = 1, page_size: int = 20,
                   with_snippet: bool = True) -> Dict[str, Any]:
    """**材料列表**（案例/解读/问答；按类型 / 关键词 / 关联法 / 粒度 / 条款筛选 + 分页）。

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
    pid = str(provision_id or "").strip()
    if pid:
        items = [m for m in items if pid in (m.get("provision_ids") or [])]
    gd = str(granularity or "").strip()
    if gd:
        items = [m for m in items if str(m.get("granularity") or "") == gd]
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
    by_granularity = dict(Counter(str(m.get("granularity") or "") for m in items).most_common())
    items.sort(key=lambda m: str(m.get("published_at") or ""), reverse=True)
    total = len(items)
    p = max(1, int(page or 1))
    ps = max(1, min(int(page_size or 20), 200))
    return {"total": total, "page": p, "page_size": ps,
            "pages": (total + ps - 1) // ps if total else 0,
            "items": [_brief(m, with_snippet=with_snippet)
                      for m in items[(p - 1) * ps: p * ps]],
            "by_kind": by_kind, "by_granularity": by_granularity,
            "kind": kd, "q": str(q or ""), "law_code": lc,
            "granularity": gd, "provision_id": pid,
            "note": ("材料来自三平台官方发布；`related_law_codes` 是材料**显式引用**的法；"
                     "`provision_ids` 仅在正文出现「法名紧邻条号」时才非空 "
                     "（`granularity=provision` 为条款级，`law` 仅法规级，`none` 未确证）。"
                     "跨设备可读正文见 `material_detail().content`。")}


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
    # ★ 条款级命中（2026-10-15 补采正文后）：逐条附「法名 + 条号 + 是否已入正文库」
    from engine import legal_mapping as LM2
    pidx = LM2.provision_index()
    provs: List[Dict[str, Any]] = []
    for p in (m.get("matched_provisions") or []):
        pid = str(p.get("provision_id") or "")
        meta = pidx.get(pid) or {}
        provs.append({**p,
                      "law": meta.get("law") or "",
                      "article_no": meta.get("article_no"),
                      "in_library": bool(p.get("in_library"))})
    out["matched_provisions"] = provs
    out["granularity_note"] = (
        "关联到**条款级**（正文出现「法名紧邻条号」的显式引用，已校验 ID 登记）；"
        "`in_library=false` 表示该条文尚未入正文库（如实暴露，不臆造原文）。"
        if provs else
        "关联**只到法规级**（材料引用了该法，但正文未出现「法名紧邻条号」的写法）"
        "⇒ **不代表**适用某具体条款，只作参考线索。")
    # 正文（跨设备可读；`content_len` 为 0 时说明未采集成功，不留空壳）
    if not out.get("content"):
        out["content"] = _fulltext(mid)
        out["content_len"] = len(out["content"]) or int(m.get("content_len") or 0)
        if not out["content"]:
            out["content_note"] = ("正文未采集（`data/legal_crawl/material_texts/` 无此条产物）"
                                   "⇒ 只提供标题与摘要，不伪造正文。")
        else:
            out["content_source"] = ("data/legal_crawl/material_texts/%s.json（采集层产物，"
                                     "HTML→纯文本，未人工校对）" % mid)
    return out


def _fulltext(material_id: str) -> str:
    """读某条材料的**采集正文**（`data/legal_crawl/material_texts/<mid>.json`）。

    ★ 正文属**采集候选层**（与 `legal_texts/*.json` 同层）⇒ 落 `data/`，不塞进 `config/`
      （2055 条正文会让结论文件膨胀数倍）。取不到 ⇒ 空串（调用方如实说明，不伪造）。
    """
    fp = _ROOT / "data" / "legal_crawl" / "material_texts" / f"{material_id}.json"
    if not fp.exists():
        return ""
    try:
        o = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:                                            # noqa: BLE001
        return ""
    return str(o.get("body") or "") if o.get("ok") else ""


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

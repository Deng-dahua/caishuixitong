# -*- coding: utf-8 -*-
"""法规**专题**读层（STEP-EXT-LEGAL-FULL-MATCH 步骤 22）—— 唯一读路径。

数据权威（全部**只读转发**，本模块零条文、零统计重算）：
  · 专题索引 `config/legal_topic_index.json`（由 `scripts/_gen_legal_topic_index.py` 幂等生成）
  · 法规目录 `config/legal_catalog.json`（索引里存的是它的**下标**，不复制内容）
  · 条款正文本库 → 转发 `legal_library.article_entries` / `legal_citation`
  · 规则⇄条款关联 → 转发 `legal_mapping`
  · 材料 → 转发 `legal_extras`

★★ 缺失如实（防"看起来有其实没有"）：
  · 专题**尚无已确证条款**时，`topic_materials` 返回空 + `reason` 说明
    （"本专题暂无已核实条款 ⇒ 无法按法定位相关材料"），**不得**显示成"无相关材料"；
  · 目录条目**未收录正文**（`has_body_in_library=false`）时原样透传该字段，由前端如实标注。

★ 只读：不改引擎结论、不写盘。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine import legal_extras as LE
from engine import legal_mapping as LM

_ROOT = Path(__file__).resolve().parent.parent
_CFG = _ROOT / "config"
_IDX_PATH = _CFG / "legal_topic_index.json"
_CAT_PATH = _CFG / "legal_catalog.json"
_PROV_PATH = _CFG / "legal_provisions.json"

_CACHE: Dict[str, Any] = {}


def reset_cache() -> None:
    """清空缓存（索引/目录重新生成后调用）。"""
    _CACHE.clear()


def _j(path: Path) -> Dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception as exc:                                     # noqa: BLE001
        return {"_error": str(exc)}


def _idx() -> Dict[str, Any]:
    if "idx" not in _CACHE:
        d = _j(_IDX_PATH)
        d.setdefault("available", bool(d.get("topics")))
        _CACHE["idx"] = d
    return _CACHE["idx"]


def _catalog() -> List[Dict[str, Any]]:
    if "cat" not in _CACHE:
        _CACHE["cat"] = _j(_CAT_PATH).get("items") or []
    return _CACHE["cat"]


def _provs() -> List[Dict[str, Any]]:
    if "prov" not in _CACHE:
        _CACHE["prov"] = _j(_PROV_PATH).get("provisions") or []
    return _CACHE["prov"]


def available() -> bool:
    return bool(_idx().get("available"))


def _topic_of(topic_id: Any) -> Optional[Dict[str, Any]]:
    tid = str(topic_id or "")
    for t in (_idx().get("topics") or []):
        if str(t.get("id")) == tid:
            return t
    return None


def _light(t: Dict[str, Any]) -> Dict[str, Any]:
    """列表用形状：**去掉 `doc_indexes`**（几千个下标，列表不需要）。"""
    out = {k: v for k, v in t.items() if k != "doc_indexes"}
    return out


def list_topics(*, batch: Any = None, status: Any = None,
                q: Any = None) -> Dict[str, Any]:
    """专题列表（含各专题统计；筛选按批次/状态/关键词）。"""
    if not available():
        return {"total": 0, "items": [], "available": False,
                "note": "专题索引不可用（`config/legal_topic_index.json` 缺失）⇒ 如实为空；"
                        "请跑 `scripts/_gen_legal_topic_index.py`。"}
    items = [_light(t) for t in (_idx().get("topics") or [])]
    b = str(batch or "").strip()
    if b:
        items = [x for x in items if str(x.get("batch")) == b]
    st = str(status or "").strip()
    if st:
        items = [x for x in items if str(x.get("status")) == st]
    kw = "".join(str(q or "").split())
    if kw:
        items = [x for x in items
                 if kw in str(x.get("id")) or kw in str(x.get("name"))
                 or kw in str(x.get("scope"))]
    return {"total": len(items), "items": items, "available": True,
            "authority": _idx().get("authority", ""),
            "note": ("`documents_total` 按 `inventory_keywords`（**清单筛选词**）命中目录，"
                     "口径偏宽、含相关外围文件；`provisions_total` 只统计**已核实条款**"
                     "（`config/legal_provisions.json`）；`materials_total` 按法分列求和，"
                     "见 `materials_by_law`。")}


def topic_detail(topic_id: Any) -> Dict[str, Any]:
    """专题详情（含统计与归属清单；法规清单条目另用 `topic_documents` 分页取）。"""
    if not available():
        return {"available": False, "topic_id": str(topic_id or ""),
                "note": "专题索引不可用 ⇒ 如实为空。"}
    t = _topic_of(topic_id)
    if t is None:
        return {"available": True, "found": False, "topic_id": str(topic_id or ""),
                "note": "无此专题 id（索引里不存在）——不猜测、不近似匹配。"}
    out = _light(t)
    out["found"] = True
    out["available"] = True
    # 附带几个可直接渲染的小清单（法规清单走分页端点，避免一次吐几千条）
    out["rule_ids"] = t.get("rule_ids") or []
    out["provision_ids"] = t.get("provision_ids") or []
    out["materials_by_law"] = t.get("materials_by_law") or []
    return out


def topic_documents(topic_id: Any, *, kind: Any = None, q: Any = None,
                    page: int = 1, page_size: int = 50) -> Dict[str, Any]:
    """专题的**法规清单**（按目录下标取原始条目；分页 + 按文件类型/关键词筛选）。"""
    if not available():
        return {"total": 0, "items": [], "available": False,
                "note": "专题索引不可用 ⇒ 如实为空。"}
    t = _topic_of(topic_id)
    if t is None:
        return {"total": 0, "items": [], "found": False,
                "note": "无此专题 id。"}
    cat = _catalog()
    rows: List[Dict[str, Any]] = []
    for i in (t.get("doc_indexes") or []):
        if not isinstance(i, int) or not (0 <= i < len(cat)):
            continue                                              # 下标越界 ⇒ 跳过（不猜）
        d = cat[i]
        rows.append({
            "index": i,
            "title": d.get("title"), "doc_no": d.get("doc_no"),
            "published_at": d.get("published_at"), "issuer": d.get("issuer"),
            "kind": d.get("kind"), "source": d.get("source"),
            "labels": d.get("labels"), "tax_policy": d.get("tax_policy"),
            "url": d.get("url"),
            # ★ 未收录正文时**原样透传 False**，前端须如实标注（不得默认"有正文"）
            "has_body_in_library": bool(d.get("has_body_in_library")),
        })
    kd = str(kind or "").strip()
    if kd:
        rows = [r for r in rows if str(r.get("kind")) == kd]
    kw = "".join(str(q or "").split())
    if kw:
        rows = [r for r in rows
                if kw in str(r.get("title")) or kw in str(r.get("doc_no"))]
    rows.sort(key=lambda r: str(r.get("published_at") or ""), reverse=True)
    total = len(rows)
    p = max(1, int(page or 1))
    ps = max(1, min(int(page_size or 50), 200))
    return {"topic_id": str(topic_id), "total": total, "page": p, "page_size": ps,
            "pages": (total + ps - 1) // ps if total else 0,
            "items": rows[(p - 1) * ps: p * ps],
            "kind": kd, "q": str(q or ""),
            "note": ("清单来自 `config/legal_catalog.json`（三源全量目录）；"
                     "`has_body_in_library=false` 表示**该法规正文尚未核实录入**正文库"
                     "（点 URL 去官方原文），不得编造条文。")}


def topic_provisions(topic_id: Any) -> Dict[str, Any]:
    """专题的**已核实条款**（含正文；未收录正文者如实标注）。"""
    if not available():
        return {"total": 0, "items": [], "available": False, "note": "专题索引不可用。"}
    t = _topic_of(topic_id)
    if t is None:
        return {"total": 0, "items": [], "found": False, "note": "无此专题 id。"}
    ids = set(t.get("provision_ids") or [])
    out: List[Dict[str, Any]] = []
    for p in _provs():
        pid = str(p.get("provision_id") or "")
        if pid not in ids:
            continue
        got = LM.content_of(pid)                                  # ★ 条款正文唯一读法
        out.append({
            "provision_id": pid, "law": p.get("law"), "law_code": p.get("law_code"),
            "article": p.get("article"), "article_no": p.get("article_no"),
            "kind": p.get("kind"), "source": p.get("source"),
            "topic_tags": p.get("topic_tags") or [],
            "content": got.get("content") or "", "has_content": bool(got.get("has_content")),
            "content_source": got.get("content_source", ""),
            "related_rules": LM.rules_of(pid),                    # 反查：该条款被哪些规则引用
        })
    out.sort(key=lambda x: (str(x.get("law") or ""), int(x.get("article_no") or 0)))
    return {"topic_id": str(topic_id), "total": len(out), "items": out,
            "note": ("只列**已核实录入**正文库的条款（`config/legal_provisions.json`）；"
                     "`related_rules` 是该条款被哪些规则引用（关联表反查）。")}


def topic_rules(topic_id: Any) -> Dict[str, Any]:
    """专题的**规则清单**（含层级/版本 + 已确证条款数）。"""
    if not available():
        return {"total": 0, "items": [], "available": False, "note": "专题索引不可用。"}
    t = _topic_of(topic_id)
    if t is None:
        return {"total": 0, "items": [], "found": False, "note": "无此专题 id。"}
    sys_path_hack = __import__("sys").path                             # noqa: N806
    if str(_ROOT) not in sys_path_hack:
        sys_path_hack.insert(0, str(_ROOT))
    from engine import rule_catalog as RC
    out: List[Dict[str, Any]] = []
    for rid in (t.get("rule_ids") or []):
        try:
            g = RC.get(rid)
        except KeyError:
            out.append({"rule_id": rid, "found": False,
                        "note": "规则目录中查不到（索引与规则库不一致，须重跑索引生成器）"})
            continue
        lp = g.get("legal_provisions") or []
        out.append({
            "rule_id": rid, "found": True, "name": g.get("name"),
            "layer": g.get("layer"), "tax": g.get("tax"), "taxes": g.get("taxes") or [],
            "severity": g.get("severity"), "version": g.get("version"),
            "version_registered": g.get("version_registered"),
            "source_cn": g.get("source_cn"), "authority_cn": g.get("authority_cn"),
            "legal_provision_ids": g.get("legal_provision_ids") or [],
            "legal_provisions_n": len(lp),
            "unresolved_n": g.get("legal_unresolved_n") or 0,
        })
    return {"topic_id": str(topic_id), "total": len(out), "items": out,
            "note": ("规则归属口径：①批次规则的 `_topic_id`；②其余规则经**已确证条款**"
                     "所属法反查。`legal_provisions_n` 是已确证到具体条款的条数（含正文）。")}


def topic_materials(topic_id: Any, *, law_code: Any = None,
                    limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """专题的**相关官方材料**（按法分列；指定 `law_code` 则列该法的材料）。

    ★★ 缺失如实：本专题**尚无已确证条款** ⇒ 无法按法定位材料 ⇒ 返回空 + `reason`
      （**不得**渲染成"无相关材料"——那是两件不同的事）。
    """
    if not available():
        return {"total": 0, "items": [], "available": False, "note": "专题索引不可用。"}
    t = _topic_of(topic_id)
    if t is None:
        return {"total": 0, "items": [], "found": False, "note": "无此专题 id。"}
    rows = t.get("materials_by_law") or []
    if not rows:
        return {"topic_id": str(topic_id), "total": 0, "items": [], "by_law": [],
                "reason": ("本专题**暂无已核实条款** ⇒ 无法按法定位相关材料"
                           "（材料关联以法规为锚；无条款即无锚点）。"),
                "note": "如实为空，不代表'没有相关材料'。"}
    lc = str(law_code or "").strip()
    if lc:
        rows = [r for r in rows if str(r.get("law_code")) == lc]
    rows.sort(key=lambda r: -int(r.get("count") or 0))
    off = max(0, int(offset or 0))
    lim = max(1, min(int(limit or 20), 200))
    out: List[Dict[str, Any]] = []
    for r in rows[off:off + lim]:
        got = LE.for_law(r["law_code"], limit=8)
        out.append({"law_code": r["law_code"], "law_name": r["law_name"],
                    "count": r["count"], "kinds": r.get("kinds") or {},
                    "samples": got.get("items") or [],
                    "granularity": got.get("granularity")})
    return {"topic_id": str(topic_id), "total": len(rows), "items": out,
            "by_law": rows,
            "note": ("材料与法规的关联**只到法规级**（材料显式引用了该法），"
                     "不代表其适用本条款 ⇒ 参考线索，不作定性依据。"
                     "`samples` 为前几条示例，完整列表见 `/legal-materials?law_code=`。")}


def stats() -> Dict[str, Any]:
    """专题索引统计（**直接读登记值**，不重算）。"""
    d = _idx()
    tot = dict(d.get("totals") or {})
    tot.update({
        "available": available(),
        "updated": str(d.get("updated") or ""),
        "catalog_total": int(d.get("catalog_total") or 0),
        "authority": str(d.get("authority") or ""),
    })
    return tot


__all__ = ["available", "reset_cache", "list_topics", "topic_detail", "topic_documents",
           "topic_provisions", "topic_rules", "topic_materials", "stats"]

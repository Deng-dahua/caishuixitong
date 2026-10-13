"""P0-5 规则**目录** —— 规则库的唯一读取入口（**只读派生，不改判定、不建同义表**）。

★ 为什么不建 `rules` 表（与任务书「数据表 rules」的差异，**已在交付报告说明**）：
  本项目规则权威有三处且都不可废（Python 执行权威 / JSON 候选权威 / YAML 同源导出），
  把三者塞进一张表会造出**第三份**并立刻产生"表与代码谁为准"的问题（P0-3 已确立
  「一个概念一处存放」原则，`financial_data`/`tax_returns`/`invoices` 当时同样**未建**）。
  故本模块以**只读派生目录**满足"规则库可查、可展示、版本可查"，并把 DDL 备在
  `OPTIONAL_TABLES`（需要时一行开关即建），**不制造第二权威**。

★ 顺带解决的真实缺陷（本轮实测）：
  · 候选库 `legal_basis_ref` **460 条全为占位**（「法规库自动匹配」）⇒ 目录**如实标占位**；
  · Python 侧 **95 条无任何法规依据** ⇒ 目录**如实计 0**，不以占位顶替。

★ 「启用/禁用」的**如实口径**（防假开关）：
  系统在库规则的执行权威是 **Python 常量**（`REDLINES` / `VERIFIED_RULE_CATALOG`），
  **没有运行时开关**（实测 `engine/tax_redlines.py` 与 `verified_rule_engine.py`
  均无 `enabled` 机制）。候选库的 `enabled` 是"是否已接入系统"的事实（导出 `wired: false`）。
  ⇒ 本目录**展示**启用态，并显式返回 `runtime_switch: False`；
    **不提供界面开关**（那会是"点了没反应"的假开关）。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from engine import rule_loader as L

#: 系统在库规则的启用态：**事实**是"全部生效"（无运行时开关）——如实声明，不猜
RUNTIME_SWITCH_AVAILABLE = False

RUNTIME_SWITCH_NOTE = ("系统在库规则（红线 / 已验证规则）的执行权威是 Python 常量，"
                       "**当前没有运行时启用/禁用开关**（实测两库均无 enabled 机制）。"
                       "本页展示的是事实启用态；如需真正的运行时开关，须改判定层，"
                       "属 P0-5 边界之外，需另行裁定。候选清单的 enabled=false 表示"
                       "「尚未接入系统」，不是「被禁用」。")


def _root() -> str:
    """规则仓库根目录 —— **转发** `rule_loader._root`（同一概念不得两份实现）。

    ★ 收敛理由（审计闸门实测）：此前两处**字节级完全一致**（复制粘贴），
      被判为"跨模块真实分歧"；同一取根逻辑只需一处。"""
    return L._root()


# ══════════════════════════════════════════════════════════════════════════
# 目录装配（进程内缓存；新增/改规则后调用 `reset_cache()`）
# ══════════════════════════════════════════════════════════════════════════
_CACHE: Dict[str, Any] = {}


def reset_cache() -> None:
    """清空目录缓存（规则文件或代码变更后调用）。"""
    _CACHE.clear()


def _versions_index() -> Dict[str, Dict[str, Any]]:
    """规则 → 版本登记（唯一权威 `config/rule_versions.json`）。取不到 ⇒ 空表 + 留痕。"""
    path = os.path.join(_root(), "config", "rule_versions.json")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh) or {}
    except Exception as exc:                                 # noqa: BLE001
        L._note("规则版本登记表读取失败：%s" % exc)          # noqa: SLF001
        return {}
    rules = doc.get("rules") or {}
    return rules if isinstance(rules, dict) else {}


def entries(*, refresh: bool = False) -> List[Dict[str, Any]]:
    """全部规则条目（Python + 候选），**每条附版本登记**。"""
    if not refresh and "entries" in _CACHE:
        return _CACHE["entries"]
    vers = _versions_index()
    out: List[Dict[str, Any]] = []
    for rec in L.load_python_rules():
        _stamp_version(rec, vers)
        out.append(rec)
    for rec in L.load_json_candidates():
        _stamp_version(rec, vers)
        out.append(rec)
    # ★ 第六层：权威事实核查规则（**另一维度体系**，独立列示、不得与规则主体相加）
    for rec in L.load_governance_rules():
        _stamp_version(rec, vers)
        out.append(rec)
    _CACHE["entries"] = out
    return out


def _stamp_version(rec: Dict[str, Any], vers: Dict[str, Dict[str, Any]]) -> None:
    """把版本登记并入条目。**未登记 ⇒ 如实标「未登记」**（不伪造版本号）。"""
    v = vers.get(rec["rule_id"]) or {}
    rec["version"] = str(rec.get("version") or v.get("version") or "")
    rec["version_registered"] = bool(v)
    rec["effective_from"] = str(v.get("effective_from") or "")
    rec["changed_note"] = str(v.get("changed_note") or "")
    rec["version_layer"] = str(v.get("layer") or "")
    if not rec["version"]:
        rec["version"] = "未登记"


def layer_of(rec: Dict[str, Any]) -> str:
    """条目所属**层**（前端分组与统计口径的唯一取法）。"""
    return str(rec.get("layer") or "")


# ══════════════════════════════════════════════════════════════════════════
# 查询
# ══════════════════════════════════════════════════════════════════════════
def list_rules(*, source: Any = None, layer: Any = None, q: Any = None,
               tax: Any = None, enabled: Any = None,
               page: Any = 1, page_size: Any = 20) -> Dict[str, Any]:
    """规则列表（筛选 / 搜索 / 分页）。"""
    items = entries()
    s = str(source or "").strip()
    if s:
        items = [r for r in items if r["source_kind"] == s]
    ly = str(layer or "").strip()
    if ly:
        items = [r for r in items if layer_of(r) == ly]
    t = str(tax or "").strip()
    if t:
        items = [r for r in items if t == r["tax"] or t in (r["taxes"] or [])]
    kw = str(q or "").strip().lower()
    if kw:
        items = [r for r in items
                 if kw in r["rule_id"].lower() or kw in r["name"].lower()]
    if enabled is not None and str(enabled).strip() != "":
        want = str(enabled).strip().lower() in ("1", "true", "yes", "on")
        items = [r for r in items if bool(r.get("enabled")) == want]
    try:
        p = max(1, int(page))
    except Exception:                                        # noqa: BLE001
        p = 1
    try:
        ps = max(1, min(int(page_size), 200))
    except Exception:                                        # noqa: BLE001
        ps = 20
    total = len(items)
    return {"items": [_public(r) for r in items[(p - 1) * ps: p * ps]],
            "total": total, "page": p, "page_size": ps,
            "pages": (total + ps - 1) // ps if total else 0}


def _public(rec: Dict[str, Any]) -> Dict[str, Any]:
    """对外形状：**不含 `raw`**（体积大且属实现细节），但保留可追溯所需字段。"""
    out = {k: v for k, v in rec.items() if k != "raw"}
    refs = rec.get("legal_basis_ref") or []
    out["legal_basis_ref"] = refs
    out["legal_basis_placeholder"] = bool(refs) and all(
        x.get("placeholder") for x in refs if isinstance(x, dict))
    out["has_legal_basis"] = bool(refs) and not out["legal_basis_placeholder"]
    out["authority"] = L.AUTHORITY_OF.get(rec["source_kind"], "")
    out["authority_cn"] = L.AUTHORITY_CN.get(out["authority"], "")
    out["source_cn"] = L.SOURCE_CN.get(rec["source_kind"], rec["source_kind"])
    return out


def get(rule_id: Any) -> Dict[str, Any]:
    """规则详情（含 `raw` 原文，可追溯）。"""
    rid = str(rule_id or "")
    for r in entries():
        if r["rule_id"] == rid:
            out = dict(r)
            out["authority"] = L.AUTHORITY_OF.get(r["source_kind"], "")
            out["authority_cn"] = L.AUTHORITY_CN.get(out["authority"], "")
            out["source_cn"] = L.SOURCE_CN.get(r["source_kind"], r["source_kind"])
            return out
    raise KeyError(rid)


def stats() -> Dict[str, Any]:
    """规则库统计（**分层**，与 `layer_semantics` 口径一致；禁拼接重复计数）。"""
    items = entries()
    from collections import Counter
    by_layer = Counter(layer_of(r) for r in items)
    by_kind = Counter(r["source_kind"] for r in items)
    py = [r for r in items if r["source_kind"] == "python"]
    cand = [r for r in items if r["source_kind"] == "json"]
    no_ref = [r for r in items if not (r.get("legal_basis_ref") or [])]
    ph_ref = [r for r in items
              if (r.get("legal_basis_ref") or [])
              and all(x.get("placeholder") for x in r["legal_basis_ref"]
                      if isinstance(x, dict))]
    # ★ 规则主体 = **只认 layer_semantics 的权威口径**（不得把检测器层拼进去）
    subject = _rule_subject_count()
    return {
        "total_entries": len(items),
        "by_layer": dict(by_layer),
        "by_source_kind": dict(by_kind),
        "by_source_kind_cn": {L.SOURCE_CN.get(k, k): v for k, v in by_kind.items()},
        "python_rules": len(py),
        "candidate_rules": len(cand),
        "rule_subject_total": subject,
        "rule_subject_note": ("规则主体条数取自唯一权威 `config/rule_versions.json::"
                              "layer_semantics`（红线 + 已验证）；检测器层是其"
                              "**检测器实现层**，不得拼接计数。"),
        "legal_basis_coverage": {
            "with_real_ref": len(items) - len(no_ref) - len(ph_ref),
            "placeholder": len(ph_ref),
            "missing": len(no_ref),
            "note": ("实测：候选库 460 条 `legal_basis_ref` **全为占位**"
                     "（「法规库自动匹配」）；系统在库规则中另有部分**无任何法规依据**"
                     "（已验证规则与检测器层未登记 legal_basis）⇒ 如实计 0/占位，不以占位顶替。"),
        },
        "runtime_switch_available": RUNTIME_SWITCH_AVAILABLE,
        "runtime_switch_note": RUNTIME_SWITCH_NOTE,
        "loader_errors": L.last_errors(),
    }


def _rule_subject_count() -> int:
    """规则主体条数（唯一权威 `layer_semantics.layers[*].counts_toward_rule_total`）。"""
    path = os.path.join(_root(), "config", "rule_versions.json")
    try:
        with open(path, encoding="utf-8") as fh:
            layers = (json.load(fh) or {}).get("layer_semantics", {}).get("layers", {})
        return int(sum(int(v.get("count") or 0) for v in layers.values()
                       if v.get("counts_toward_rule_total")))
    except Exception as exc:                                 # noqa: BLE001
        L._note("规则主体条数取不到（不回退硬编码）：%s" % exc)   # noqa: SLF001
        return 0


def versions() -> Dict[str, Any]:
    """规则版本信息（唯一权威 `config/rule_versions.json`）。"""
    path = os.path.join(_root(), "config", "rule_versions.json")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh) or {}
    except Exception as exc:                                 # noqa: BLE001
        raise RuntimeError("规则版本登记表读不出来：%s" % exc) from exc
    reg = doc.get("rules") or {}
    from collections import Counter
    return {
        "rule_set_version": str(doc.get("rule_set_version") or ""),
        "history": doc.get("rule_set_history") or [],
        "registered_count": len(reg) if isinstance(reg, dict) else 0,
        "by_version": dict(Counter(str((v or {}).get("version") or "未登记")
                                   for v in (reg.values() if isinstance(reg, dict) else []))),
        "counts": doc.get("counts") or {},
        "layer_semantics": doc.get("layer_semantics") or {},
    }


def meta() -> Dict[str, Any]:
    """规则库字典（前端中文名/选项的唯一来源，不在前端硬编码）。"""
    items = entries()
    layers = sorted({layer_of(r) for r in items})
    taxes = sorted({t for r in items for t in ([r["tax"]] if r["tax"] else []) + (r["taxes"] or [])})
    return {
        "sources": [{"value": k, "label": L.SOURCE_CN[k],
                     "authority": L.AUTHORITY_OF[k],
                     "authority_cn": L.AUTHORITY_CN[L.AUTHORITY_OF[k]]}
                    for k in L.SOURCE_KINDS],
        "layers": [{"value": x, "label": x} for x in layers],
        "taxes": taxes,
        "runtime_switch_available": RUNTIME_SWITCH_AVAILABLE,
        "runtime_switch_note": RUNTIME_SWITCH_NOTE,
        "dsl_scope": L.load_dsl_scope(),
        "loader_errors": L.last_errors(),
    }


__all__ = ["RUNTIME_SWITCH_AVAILABLE", "RUNTIME_SWITCH_NOTE", "reset_cache",
           "entries", "list_rules", "get", "stats", "versions", "meta", "layer_of"]

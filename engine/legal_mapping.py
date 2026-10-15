# -*- coding: utf-8 -*-
"""法规 ⇄ 规则关联读层（STEP-EXT-LEGAL-FULL-MATCH 步骤 11 / 19）—— **唯一读路径**。

设计原则（与项目铁律一致）
  ① **单一权威**：关联事实只来自 `config/legal_mappings.json`（由
     `scripts/_gen_legal_mappings.py` **幂等**生成）；本模块**不重算、不推断**。
  ② **条款原文不另存一份**：正文一律转发 `legal_citation.library_file_entries()`
     （正文库读路径唯一权威）⇒ 两处口径不会漂移；查不到正文 ⇒ `content=""` 且
     `has_content=False`，**绝不编造**。
  ③ **不确定就不报**：`unresolved` 里的是"作者写了引用但无法确证到具体条款"的
     条目 —— 原样暴露（含原因），**不得**当作已核实引用展示。
  ④ **只读**：本模块不改任何引擎结论、不写盘。

用法
  ```python
  from engine import legal_mapping as LM
  LM.provisions_of("RL-AST-001")     # 该规则**已确证**的条款（含正文）
  LM.rules_of("CIT-LAW-011")         # 该条款被哪些规则引用（反查）
  LM.unresolved_of("RL-XXX")         # 无法确证的引用（如实）
  ```
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from engine import legal_citation as LC

_ROOT = Path(__file__).resolve().parent.parent
_MAP_PATH = _ROOT / "config" / "legal_mappings.json"

_CACHE: Dict[str, Any] = {}

#: 条款 ID 尾部条号（`{短码}-{条号:03d}`；★ 短码**自身含 `-`**（如 `TAX-ADMIN-LAW`）
#  ⇒ 只能剥**尾部数字段**，不能按第一个 `-` 切）
_ART_TAIL = re.compile(r"-\d{1,4}$")


def reset_cache() -> None:
    """清空缓存（`config/legal_mappings.json` 变更后调用）。"""
    _CACHE.clear()


def law_code_of(provision_id: Any) -> str:
    """条款 ID → 法短码（**本函数是全项目唯一实现**，`legal_extras` 转发至此）。"""
    return _ART_TAIL.sub("", str(provision_id or ""))


def _norm_key(s: Any) -> str:
    """归一化（去空白 + 去「中华人民共和国」前缀），用于法名对齐。"""
    t = "".join(str(s or "").split())
    return t[7:] if t.startswith("中华人民共和国") else t


def _doc() -> Dict[str, Any]:
    """读关联表原文（进程内缓存）。读不到 ⇒ 空表 + 明确 `available=False`。"""
    if "doc" in _CACHE:
        return _CACHE["doc"]
    try:
        d = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            d = {}
    except Exception as exc:                                     # noqa: BLE001
        d = {"_error": str(exc)}
    d.setdefault("available", "mappings" in d)
    _CACHE["doc"] = d
    return d


def available() -> bool:
    """关联表是否可用（不可用 ⇒ 调用方须**如实降级**，不得伪造）。"""
    return bool(_doc().get("available"))


def _content_index() -> Dict[Tuple[str, str], Dict[str, str]]:
    """`(归一法名, 条号) → 正文条目`（转发正文库读路径，唯一权威）。"""
    if "content" in _CACHE:
        return _CACHE["content"]
    idx: Dict[Tuple[str, str], Dict[str, str]] = {}
    for e in LC.library_file_entries():
        k = (_norm_key(e.get("law")), str(e.get("article") or "").strip())
        if k[0] and k[1] and k not in idx:
            idx[k] = e
    _CACHE["content"] = idx
    return idx


def _by_rule() -> Dict[str, List[Dict[str, Any]]]:
    if "by_rule" in _CACHE:
        return _CACHE["by_rule"]
    out: Dict[str, List[Dict[str, Any]]] = {}
    for m in (_doc().get("mappings") or []):
        rid = str(m.get("rule_id") or "")
        if rid:
            out.setdefault(rid, []).append(m)
    _CACHE["by_rule"] = out
    return out


def _decorate(m: Dict[str, Any]) -> Dict[str, Any]:
    """给一条关联补上**条款原文**（来自正文库；缺失如实标注）。"""
    law = str(m.get("law") or "")
    art = str(m.get("article") or "")
    e = _content_index().get((_norm_key(law), art)) or {}
    content = str(e.get("content") or "")
    return {
        "provision_id": str(m.get("provision_id") or ""),
        "law": law,
        "law_code": str(m.get("law_code") or ""),
        "article": art,
        "content": content,
        "has_content": bool(content),
        "content_source": (str(e.get("source") or "") if content else ""),
        "verified": bool(m.get("verified")),
        "content_sha256": str(m.get("content_sha256") or ""),
        "raw_basis": str(m.get("raw_basis") or ""),
        "authority": "config/legal_mappings.json",
    }


def provisions_of(rule_id: Any) -> List[Dict[str, Any]]:
    """某规则**已确证**的法规条款（含正文；未确证的一律不在此处）。"""
    rid = str(rule_id or "")
    return [_decorate(m) for m in _by_rule().get(rid, []) if m.get("verified")]


def mapping_rows(*, verified_only: bool = False) -> List[Dict[str, Any]]:
    """关联表**逐条原始行**（公开入口，供其它读层反查；避免跨模块取私有 `_doc`）。

    ★ 与 `provisions_of` 的区别：后者按 rule_id 聚合并附正文；本函数给**原始行**，
      调用方自行索引（如"按法短码反查规则"）。
    """
    rows = list(_doc().get("mappings") or [])
    if verified_only:
        rows = [m for m in rows if m.get("verified")]
    return rows


def provision_index() -> Dict[str, Dict[str, Any]]:
    """`provision_id → {law, article, article_no, law_code, kind, topic_tags}`（唯一权威 `config/legal_provisions.json`）。

    ★ 为什么放在这里：本模块是"条款"这一概念的读层入口；专题页/材料页/规则页
      都需要"给我条款 ID，还我法名与条号（再取正文）"⇒ 只应有一份实现。

    ★ 2026-10-15：补返 `article_no`（条款索引本就登记的数字条号）。只**增**键、
      不改既有键语义 ⇒ 既有消费方零影响；材料页要按条号展示，缺它就得各自再解析一遍。
    """
    if "p_index" in _CACHE:
        return _CACHE["p_index"]
    idx: Dict[str, Dict[str, Any]] = {}
    try:
        d = json.loads((_ROOT / "config" / "legal_provisions.json").read_text(encoding="utf-8"))
    except Exception:                                            # noqa: BLE001
        d = {}
    for p in (d.get("provisions") or []):
        pid = str(p.get("provision_id") or "")
        if pid:
            idx[pid] = {"law": str(p.get("law") or ""), "article": str(p.get("article") or ""),
                        "article_no": p.get("article_no"),
                        "law_code": str(p.get("law_code") or ""),
                        "kind": str(p.get("kind") or ""),
                        "topic_tags": list(p.get("topic_tags") or [])}
    _CACHE["p_index"] = idx
    return idx


def content_of(provision_id: Any) -> Dict[str, Any]:
    """条款 ID → **条款正文**（转发正文库读路径，唯一权威；查不到 ⇒ 空 + `has_content=false`）。

    ★ 缺失如实：正文库未收录该条 ⇒ `content=""`，调用方须如实标注，**不得**编造条文，
      也不得用"该法其他条"顶替。
    """
    pid = str(provision_id or "")
    meta = provision_index().get(pid) or {}
    law = str(meta.get("law") or "")
    art = str(meta.get("article") or "")
    if not (law and art):
        # 条款索引里没有 ⇒ 退回关联表（mappings 也带 law/article）
        for m in (_doc().get("mappings") or []):
            if str(m.get("provision_id") or "") == pid:
                law, art = str(m.get("law") or ""), str(m.get("article") or "")
                break
    e = _content_index().get((_norm_key(law), art)) or {}
    content = str(e.get("content") or "")
    return {"provision_id": pid, "law": law, "article": art, "content": content,
            "has_content": bool(content),
            "source": str(e.get("source") or ""),
            "content_source": "static/legal_library.json（经 legal_citation.library_file_entries）"}


def rules_of(provision_id: Any) -> List[str]:
    """某条款被哪些规则引用（反向追溯；来自 `by_provision` 唯一权威）。"""
    pid = str(provision_id or "")
    v = (_doc().get("by_provision") or {}).get(pid) or []
    return [str(x) for x in v]


def unresolved_of(rule_id: Any = None) -> List[Dict[str, Any]]:
    """无法确证到具体条款的引用（**如实暴露**；`rule_id` 为空则返回全部）。"""
    rid = str(rule_id or "")
    out: List[Dict[str, Any]] = []
    for u in (_doc().get("unresolved") or []):
        if rid and str(u.get("rule_id") or "") != rid:
            continue
        out.append(dict(u))
    return out


def for_finding(finding: Dict[str, Any]) -> Dict[str, Any]:
    """给一条**风险发现**取法规依据（步骤 19：发现 → 条款 ID + 条款原文）。

    ★ 规则 id 取值优先级与引擎一致（`rule_id` → `redline_id`），不新增第三套口径。
    ★ 返回值恒有 `provisions`（可能为空列表）与 `source`（取数来源，可追溯）；
      为空时 `note` 说明原因，**不得**用"无依据"静默顶替。
    """
    rid = str((finding or {}).get("rule_id") or (finding or {}).get("redline_id") or "")
    if not available():
        return {"provisions": [], "unresolved": [], "source": "config/legal_mappings.json",
                "note": "关联表不可用（读取失败）⇒ 如实降级，不伪造法规依据。"}
    provs = provisions_of(rid)
    unres = unresolved_of(rid)
    if provs:
        note = ""
    elif unres:
        note = "该规则有 %d 处引用**无法确证到具体条款**（见 unresolved），不得作为定性依据。" % len(unres)
    else:
        note = "该规则**未登记可确证的法规条款**（关联表无此 rule_id）。"
    return {"provisions": provs, "unresolved": unres,
            "source": "config/legal_mappings.json",
            "rule_id": rid, "note": note}


def enrich_finding(finding: Dict[str, Any]) -> Dict[str, Any]:
    """把法规条款**就地并入**发现（`legal_provisions` / `legal_provision_ids`）。

    ★ 只增字段、不改既有字段语义；返回同一个 dict（调用方可直接用返回值）。
    """
    got = for_finding(finding)
    finding["legal_provisions"] = got["provisions"]
    finding["legal_provision_ids"] = [p["provision_id"] for p in got["provisions"] if p["provision_id"]]
    if got["unresolved"]:
        finding["legal_unresolved"] = got["unresolved"]
    if got["note"]:
        finding["legal_provisions_note"] = got["note"]
    return finding


def stats() -> Dict[str, Any]:
    """关联表统计（**直接读登记值**，不重算；与生成器口径一致）。"""
    d = _doc()
    s = dict(d.get("stats") or {})
    s["available"] = available()
    s["updated"] = str(d.get("updated") or "")
    s["note_n"] = len(d.get("note") or "")
    s["authority"] = "config/legal_mappings.json"
    s["content_source"] = "static/legal_library.json（经 legal_citation.library_file_entries）"
    return s


def coverage() -> Dict[str, Any]:
    """**可确证条款的正文覆盖率**（有多少确证条款在正文库里真能找到原文）。"""
    idx = _content_index()
    total = hit = 0
    missing: List[str] = []
    seen: Set[str] = set()
    for m in (_doc().get("mappings") or []):
        if not m.get("verified"):
            continue
        pid = str(m.get("provision_id") or "")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        total += 1
        if (_norm_key(m.get("law")), str(m.get("article") or "")) in idx:
            hit += 1
        else:
            missing.append(pid)
    return {"provisions": total, "with_content": hit,
            "missing_content": sorted(missing),
            "rate": (round(hit / total, 4) if total else None),
            "note": "`with_content` 只统计**正文库里真有原文**的条款；缺失者列于 `missing_content`，不编造。"}


__all__ = ["available", "reset_cache", "law_code_of", "mapping_rows", "provision_index", "content_of",
           "provisions_of", "rules_of", "unresolved_of", "for_finding", "enrich_finding",
           "stats", "coverage"]

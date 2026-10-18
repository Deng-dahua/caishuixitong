# -*- coding: utf-8 -*-
"""法规**分层**的唯一实现（GAP-18，2026-10-18）。

问题
----
法规库实测 7,680 条，但税务口径仅约 774 条（10.1%）；民法典 1,260 条、刑法 505 条、
刑事诉讼法 308 条、民事诉讼法 306 条等**背景法**占八成以上。此前库统计与文档只报
"7,680 条"，读者会把"库很大"当成"税务覆盖很全" —— 这是**用总量掩盖结构**。

口径（全部来自数据，不写死法名）
------------------------------
`config/legal_law_tiers.json`：
  1. `laws` 显式名单（一部法一行）**优先**；
  2. 未登记 ⇒ 按 `rules` 的关键词顺序匹配（先 tax 后 related）；
  3. 仍不命中 ⇒ `background`（**宁可低估，也不把背景法算进税务口径**）。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TIERS_PATH = os.path.join(_ROOT, "config", "legal_law_tiers.json")

TIERS: tuple = ("tax", "related", "background")
TIER_CN: Dict[str, str] = {
    "tax": "税务核心法",
    "related": "涉税相关法",
    "background": "背景法",
}

_CACHE: Dict[str, Any] = {}


def reset_cache() -> None:
    _CACHE.clear()


def config() -> Dict[str, Any]:
    if "cfg" not in _CACHE:
        try:
            with open(_TIERS_PATH, "r", encoding="utf-8") as fh:
                _CACHE["cfg"] = json.load(fh) or {}
        except Exception:                            # noqa: BLE001
            _CACHE["cfg"] = {}
    return _CACHE["cfg"]


def _norm(law: Any) -> str:
    s = str(law or "").strip()
    for p in ("中华人民共和国",):
        if s.startswith(p):
            s = s[len(p):]
    return s.replace(" ", "")


def tier_of(law: Any) -> str:
    """一部法属哪一层（`tax` / `related` / `background`）。"""
    cfg = config()
    name = _norm(law)
    if not name:
        return "background"
    # ① 显式名单（用归一后的名字比较，避免「中华人民共和国」前缀差异漏配）
    for k, v in (cfg.get("laws") or {}).items():
        if _norm(k) == name and str(v) in TIERS:
            return str(v)
    # ② 关键词规则（顺序即优先级）
    for rule in (cfg.get("rules") or []):
        tier = str((rule or {}).get("tier") or "")
        if tier not in TIERS:
            continue
        if any(str(k) in name for k in ((rule or {}).get("any") or [])):
            return tier
    # ③ 兜底：背景法（不夸大税务口径）
    return "background"


def tier_cn(law: Any) -> str:
    return TIER_CN.get(tier_of(law), tier_of(law))


def is_tax_law(law: Any) -> bool:
    return tier_of(law) == "tax"


def library_stats(rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """按层统计条数与法数，并给出**税务口径条数**（供分档披露）。

    返回：
      · `by_tier`     每层 `{tier, label, articles, laws}`
      · `articles`/`laws` 总量
      · `tax_share`   税务核心法条数占全部条数的比例
      · `note`        **明示**"总量不得单独表述为覆盖能力"
    """
    if rows is None:
        from engine.legal_citation import library_file_entries   # noqa: PLC0415
        rows = library_file_entries()
    art: Dict[str, int] = {t: 0 for t in TIERS}
    laws: Dict[str, set] = {t: set() for t in TIERS}
    for r in rows or []:
        t = tier_of((r or {}).get("law"))
        art[t] = art.get(t, 0) + 1
        laws.setdefault(t, set()).add(str((r or {}).get("law") or ""))
    total = len(rows or [])
    tax_n = art.get("tax", 0)
    return {
        "articles": total,
        "laws": len({str((r or {}).get("law") or "") for r in (rows or [])}),
        "by_tier": [{"tier": t, "label": TIER_CN[t], "articles": art.get(t, 0),
                     "laws": len(laws.get(t) or set())} for t in TIERS],
        "tax_articles": tax_n,
        "tax_share": round(tax_n / total, 4) if total else 0.0,
        "note": "★ 总条数**不得单独**作为覆盖能力表述 —— 背景法占多数时总量会掩盖"
                "「税务口径薄」。对外须同时给出 `by_tier`（至少 `tax` 条数与 `tax_share`）。",
    }


def disclosure_line(st: Optional[Dict[str, Any]] = None) -> str:
    """一句**可直接放进报告/文档**的分档披露（唯一写法，避免各处口径不一）。"""
    s = st or library_stats()
    parts = ["%s %d 条" % (x["label"], x["articles"]) for x in s["by_tier"]]
    return ("法规库共 %d 条（%s）；其中税务核心法 %d 条，占 %.1f%%。"
            % (s["articles"], "、".join(parts), s["tax_articles"], s["tax_share"] * 100))


__all__ = ["TIERS", "TIER_CN", "config", "tier_of", "tier_cn", "is_tax_law",
           "library_stats", "disclosure_line", "reset_cache"]

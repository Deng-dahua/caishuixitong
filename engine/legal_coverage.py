# -*- coding: utf-8 -*-
"""「红线库引用 → 法规正文库」**覆盖率** —— 全项目唯一实现。

## 为什么要单独一个模块（2026-10-16）
同一件计算此前有**两处实现**：录入脚本 `_load_legal_texts.py::_write_coverage`
与闸门 `audit_consistency.check_legal_text_coverage`。两处各写一遍正则与比对，
必然会分叉（且分叉后"登记基线"与"现算"用的不是同一把尺子 ⇒ 假绿/假红）。
⇒ 收敛为一份：**登记基线**与**防退化比对**都调 `compute()`。

## 口径
- 覆盖对象：`engine.tax_redlines.REDLINES` 里每条 `legal_basis` 字符串中的**每一处引用**
  （用 `legal_citation.split_citations` 拆 —— 一条引用里可能一句话引两部法，须**分别计入**）。
- 命中判据：正文库里存在该法（按 `canonical_law` 归一）且
  ① 引用未写条号 ⇒ 只要该法有任一条文即命中；或
  ② 写了条号 ⇒ 存在条号前缀/后缀相容的条文。
- **不编造条文**：未命中项**逐条列出**（`unmatched`），不以任何方式"凑覆盖率"。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]


def _an(a: Any) -> str:
    return re.sub(r"\s+", "", str(a or ""))


def library() -> List[Dict[str, Any]]:
    """读正文库（唯一权威 `static/legal_library.json`）。读不到 ⇒ 空表（不臆造）。"""
    p = _ROOT / "static" / "legal_library.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) or []
    except Exception:                                            # noqa: BLE001
        return []


def compute(lib: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """现算覆盖率。

    ★ 2026-10-18（GAP-17）：**指标拆两列**。原口径只有一个 `coverage`，它把
      「只写了法名」（引用可定位）与「连条号都对上」（条号级可核对）混成一个数；
      实测约 36%~40% 的引用只到法名（`split_citations` 129 段中 52 段无条号），
      拿这个数当"合规度"会误导。现口径：

        · `law_coverage`     —— **引用可定位率**：该**法规**在正文库里（不要求对到条）
        · `article_coverage` —— **条号级可核对率**：在写了条号的引用中，条号也真对上
        · `coverage`         —— 兼容旧口径（= `article_coverage` 的"全量分母"版本），
                                 **不得单独作为合规度对外表述**

      分母明示：`total_refs` 全部引用 / `article_total` 写了条号的引用 / `no_article_refs` 未写条号。
    """
    from engine.legal_citation import split_citations
    from engine.legal_version import canonical_law
    from engine.tax_redlines import REDLINES

    lib = library() if lib is None else lib
    idx: Dict[str, set] = {}
    for x in lib:
        idx.setdefault(canonical_law(str(x.get("law") or "")), set()).add(
            _an(x.get("article")))

    tot = hit = 0                     # 旧口径：法名 + 条号都对上
    law_hit = 0                       # 新口径 ①：只要该法规在库
    art_total = 0                     # 写了条号的引用数
    art_hit = 0                       # 写了条号且条号对上
    no_art = 0                        # 未写条号（只能定位到法）
    unmatched: List[Dict[str, Any]] = []
    for r in REDLINES or []:
        lb = (r or {}).get("legal_basis")
        if isinstance(lb, str):
            lb = [lb]
        for item in (lb or []):
            if not isinstance(item, str) or not item.strip():
                continue
            for law, art, _note, _c in split_citations(item):
                tot += 1
                arts = idx.get(canonical_law(law))
                in_lib = bool(arts)
                if in_lib:
                    law_hit += 1
                if not art:
                    no_art += 1
                else:
                    art_total += 1
                ok = in_lib and (
                    not art or any(a.startswith(_an(art)) or _an(art).startswith(a)
                                   for a in arts if a))
                if ok:
                    hit += 1
                    if art:
                        art_hit += 1
                else:
                    unmatched.append({
                        "rule_id": (r or {}).get("id"),
                        "citation": item[:120],
                        "law": law, "article": art,
                        "law_in_library": in_lib,
                        # ★ 区分两种未命中：法都没进库（该补库） vs 条号对不上（该补条文）
                        "miss_kind": ("law_missing" if not in_lib else "article_missing"),
                    })
    return {
        "total_refs": tot,
        # ── 兼容旧键（勿单独宣称为合规度）──
        "matched_refs": hit,
        "coverage": round(hit / tot, 4) if tot else 0.0,
        # ── GAP-17 两列指标 ──
        "law_matched_refs": law_hit,
        "law_coverage": round(law_hit / tot, 4) if tot else 0.0,
        "article_total_refs": art_total,
        "article_matched_refs": art_hit,
        "article_coverage": round(art_hit / art_total, 4) if art_total else 0.0,
        "no_article_refs": no_art,
        "unmatched": unmatched,
        "library_size": len(lib),
    }


def write_registry() -> Dict[str, Any]:
    """现算并**登记**基线（供闸门防退化比对）。返回登记内容。"""
    out = compute()
    doc = {
        "_note": "红线库引用 → 法规正文库（static/legal_library.json）的可匹配覆盖率。"
                 "由 engine/legal_coverage.py **现算**写入（录入脚本与闸门**同一实现**）；"
                 "闸门 check_legal_text_coverage 据此防退化。"
                 "★ 与「版本登记」（config/legal_versions.json）是两件事。"
                 "★ 2026-10-18（GAP-17）：指标**分两列**，禁单一数字表述 —— "
                 "`law_coverage`=引用可定位率（法规在库即可），"
                 "`article_coverage`=条号级可核对率（写了条号且真对上）；"
                 "`coverage` 仅为兼容旧键保留，**不得单独作为合规度对外表述**。"
                 "`unmatched` 逐条列出未命中引用（含 miss_kind）—— 不许以任何方式凑覆盖率。",
        "total_refs": out["total_refs"],
        "matched_refs": out["matched_refs"],
        "coverage": out["coverage"],
        "law_matched_refs": out["law_matched_refs"],
        "law_coverage": out["law_coverage"],
        "article_total_refs": out["article_total_refs"],
        "article_matched_refs": out["article_matched_refs"],
        "article_coverage": out["article_coverage"],
        "no_article_refs": out["no_article_refs"],
        "library_size": out["library_size"],
        "unmatched": out["unmatched"],
    }
    (_ROOT / "config" / "legal_text_coverage.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc

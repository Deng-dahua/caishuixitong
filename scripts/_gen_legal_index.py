# -*- coding: utf-8 -*-
"""生成 `config/legal_provisions.json`（**条款索引**，派生层）与
`config/legal_catalog.json`（**法规目录**，全量元数据索引）。

## 为什么要分「目录」与「条款」
| 层 | 覆盖 | 含正文？ | 权威 |
|---|---|---|---|
| **法规目录** `legal_catalog.json` | **全量**（fgk 5475 + flk 34 + 四类 1150+） | ❌ 只元数据 + 正文 URL | 采集产物（候选） |
| **条款索引** `legal_provisions.json` | **141 条已核实正文** | ❌ 只 sha256 + 标签 | 派生自 `static/legal_library.json` |
| **条文正文** `static/legal_library.json` | 131 条 | ✅**逐字原文** | **唯一录入权威** `_load_legal_texts.py` |

★ 铁律：**不编造条文** —— 抓来的正文一律落 `data/`（候选），
   **不直接进 `legal_library.json`**；须人工核实后由录入器写入。
   故本脚本产出的"条款索引"**只覆盖已核实录入的条文**，覆盖率如实暴露。

用法：
    ./.venv/Scripts/python.exe scripts/_gen_legal_index.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CRAWL = ROOT / "data" / "legal_crawl"

_CN = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def cn2num(s: str) -> int | None:
    """中文条号 → 阿拉伯（取不到 ⇒ None，不猜）。"""
    s = str(s or "").strip()
    if not s:
        return None
    if s == "十":
        return 10
    m = re.match(r"^十(.)$", s)
    if m:
        return 10 + _CN.get(m.group(1), 0)
    m = re.match(r"^(.)十(.)?$", s)
    if m:
        return _CN.get(m.group(1), 0) * 10 + (_CN.get(m.group(2), 0) if m.group(2) else 0)
    if re.match(r"^[零一二三四五六七八九]$", s):
        return _CN[s]
    return None


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _load(p: Path, default: Any = None) -> Any:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def main() -> int:
    lib = _load(ROOT / "static" / "legal_library.json", []) or []
    reg = _load(ROOT / "config" / "legal_law_codes.json", {}) or {}
    topics = (_load(ROOT / "config" / "legal_topics.json", {}) or {}).get("topics") or []

    law_idx: Dict[str, Dict[str, Any]] = {}
    for l in reg.get("laws") or []:
        for k in [l["name"], re.sub(r"^中华人民共和国", "", l["name"])] + list(l.get("aliases") or []):
            if k:
                law_idx[k] = l

    # 专题打标词表（专题 → 词）
    topic_kw: List[Tuple[str, str, List[str]]] = []
    for t in topics:
        kws = (t.get("inventory_keywords") or t.get("keywords") or [])
        if kws:
            topic_kw.append((t["id"], t["name"], [str(k) for k in kws if k]))

    # ── 条款索引（只覆盖已核实正文）──
    provisions: List[Dict[str, Any]] = []
    uncoded: List[str] = []
    for e in lib:
        law = str(e.get("law") or "")
        art = str(e.get("article") or "")
        content = str(e.get("content") or "")
        le = law_idx.get(law) or law_idx.get(re.sub(r"^中华人民共和国", "", law))
        code = (le or {}).get("code") or ""
        m = re.search(r"第([零一二三四五六七八九十百]+)条", art)
        num = cn2num(m.group(1)) if m else None
        pid = ("%s-%03d" % (code, num)) if (code and num) else ""
        if not pid:
            uncoded.append("%s %s" % (law, art))
        tags = [tid for tid, _n, kws in topic_kw if any(k in content or k in law for k in kws)]
        provisions.append({
            "provision_id": pid or None,
            "law": law,
            "law_code": code or None,
            "article": art,
            "article_no": num,
            "kind": (le or {}).get("level") or None,
            "topic_tags": tags,
            "content_sha256": _sha(content),
            "content_len": len(content),
            "source": str(e.get("source") or ""),
        })

    with_pid = [p for p in provisions if p["provision_id"]]
    (ROOT / "config" / "legal_provisions.json").write_text(json.dumps({
        "schema": 1, "updated": "2026-10-15",
        "note": ("★ **条款索引**（派生层）：`provision_id` → 条文定位与标签；"
                 "**不含正文**（正文唯一权威 `static/legal_library.json`，写入走 `_load_legal_texts.py`）。"
                 "`provision_id` = `{法短码}-{条号:03d}`；`content_sha256` 可反向校验指向的条文。"
                 "★ `provision_id` 为 null ⇒ 该条的法名未登记短码或条号解析不出（**如实暴露**）。"),
        "count": len(provisions), "with_provision_id": len(with_pid),
        "uncoded": uncoded,
        "provisions": provisions,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── 法规目录（全量元数据索引）──
    fg = _load(CRAWL / "fgk_files.json", {}) or {}
    cats = _load(CRAWL / "fgk_categories.json", {}) or {}
    flk = _load(CRAWL / "flk_laws.json", {}) or {}
    catalog: List[Dict[str, Any]] = []
    for it in (fg.get("items") or []):
        catalog.append({
            "title": it.get("title"), "doc_no": it.get("doc_no"),
            "published_at": it.get("published_at"), "issuer": it.get("issuer"),
            "kind": it.get("effect_level") or it.get("channel_name"),
            "tax_policy": it.get("tax_policy"), "labels": it.get("labels"),
            "url": it.get("url"), "source": "fgk",
            "has_body_in_library": False,
        })
    for _cat, v in (cats.get("categories") or {}).items():
        for it in (v.get("items") or []):
            catalog.append({
                "title": it.get("title"), "doc_no": it.get("doc_no"),
                "published_at": it.get("published_at"), "issuer": it.get("pub_name"),
                "kind": it.get("category"), "tax_policy": None, "labels": it.get("label"),
                "url": it.get("url"), "source": "fgk-category",
                "has_body_in_library": False,
            })
    for l in (flk.get("laws") or []):
        m = l.get("matched")
        if not m:
            continue
        catalog.append({
            "title": m.get("title"), "doc_no": "", "published_at": m.get("gbrq"),
            "issuer": m.get("zdjg_name"), "kind": m.get("flxz"),
            "tax_policy": None, "labels": None, "url": "",
            "source": "flk", "effect": m.get("sxx_cn"),
            "has_body_in_library": False,
        })
    # 标记哪些条目已有正文入库（按法名匹配条文库）
    lib_laws = {str(e.get("law") or "") for e in lib}
    lib_laws |= {re.sub(r"^中华人民共和国", "", x) for x in lib_laws}
    for c in catalog:
        base = re.sub(r"^中华人民共和国", "", str(c.get("title") or ""))
        c["has_body_in_library"] = base in lib_laws

    from collections import Counter
    (ROOT / "config" / "legal_catalog.json").write_text(json.dumps({
        "schema": 1, "updated": "2026-10-15",
        "note": ("★ **法规目录**（全量元数据索引）：fgk 全量 + flk + 案例/解读/问答/指引。"
                 "**只有元数据与正文 URL，不含条文正文**（正文见 `static/legal_library.json`）。"
                 "`has_body_in_library` 标出该法规是否已有逐条核实的正文入库。"),
        "count": len(catalog),
        "by_source": dict(Counter(c["source"] for c in catalog).most_common()),
        "by_kind": dict(Counter(c.get("kind") or "（未标注）" for c in catalog).most_common()),
        "with_body": sum(1 for c in catalog if c["has_body_in_library"]),
        "items": catalog,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print("条款索引：%d 条（有 provision_id %d，无 %d）"
          % (len(provisions), len(with_pid), len(provisions) - len(with_pid)))
    print("  专题打标：%s" % json.dumps(
        dict(Counter(t for p in provisions for t in p["topic_tags"]).most_common()), ensure_ascii=False))
    if uncoded:
        print("  无 provision_id（如实列出，前 5）：")
        for u in uncoded[:5]:
            print("    -", u)
    print("法规目录：%d 条 | 已有正文入库 %d 条"
          % (len(catalog), sum(1 for c in catalog if c["has_body_in_library"])))
    print("  按源：%s" % json.dumps(dict(Counter(c["source"] for c in catalog).most_common()),
                                  ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

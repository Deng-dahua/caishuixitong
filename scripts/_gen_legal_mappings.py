# -*- coding: utf-8 -*-
"""生成 `config/legal_mappings.json`（**法规 ⇄ 规则双向关联表**，唯一权威）。

## 职责
把规则侧的**法规依据**（红线 `legal_basis` 的 `《法》第X条` 自由文本）解析为
**条款 ID**，并**逐条核实该条款在正文库中确有正文** ⇒ 产出可查询、可验证的双向关联。

## 铁律（决定本脚本的行为）
- **只填可确证者**：`code` 解析成功 **且** 正文库确有该条 ⇒ `verified=true`；
  否则一律进 `unresolved` **并写明原因**（*不确定就不报*，绝不把"猜到的"写成已关联）。
- **双向可查**：正向 `rule_id → provision_id`，反向由本表按 `provision_id` 聚合即得
  （`by_provision` 字段现算，供法规侧反查"哪些规则引用了本条款"）。
- **不编造条文**：`content_sha256` 取自正文库实际条目，可机器复核。

用法（幂等）：
    ./.venv/Scripts/python.exe scripts/_gen_legal_mappings.py
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

OUT = ROOT / "config" / "legal_mappings.json"

# ★★ 2026-10-15 收敛：中文数字解析改用**唯一权威** `engine/cnnum.py`。
#   原私有实现（与 `_gen_legal_index.py` 各写一份）只支持到「九十九」⇒
#   「第一百零三条」等解析不出，会让**可确证的条款映射被误判为不可确证**。
from engine.cnnum import cn_to_int as cn2num        # noqa: E402  （保留旧名，调用点零改动）


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_law_index() -> Dict[str, Dict[str, Any]]:
    """法名/别名 → 法条目（含 code）。"""
    laws = json.loads((ROOT / "config" / "legal_law_codes.json").read_text(encoding="utf-8"))["laws"]
    idx: Dict[str, Dict[str, Any]] = {}
    for l in laws:
        idx[l["name"]] = l
        idx[re.sub(r"^中华人民共和国", "", l["name"])] = l
        for a in (l.get("aliases") or []):
            idx[a] = l
            idx[re.sub(r"^中华人民共和国", "", a)] = l
    return idx


def load_library() -> Dict[Tuple[str, str], Dict[str, Any]]:
    """(法名, 条号) → 正文条目（支持带/不带「中华人民共和国」两种键）。"""
    lib = json.loads((ROOT / "static" / "legal_library.json").read_text(encoding="utf-8"))
    idx: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for e in lib:
        idx[(e["law"], e["article"])] = e
        idx[(re.sub(r"^中华人民共和国", "", e["law"]), e["article"])] = e
    return idx


def parse_ref(raw: str) -> Tuple[str, str, str]:
    """从一条 `legal_basis` 文本里抽 (法名, 条号中文, 剩余说明)。抽不到 ⇒ 空串。"""
    s = str(raw or "")
    m = re.search(r"《(.+?)》", s)
    if m:
        law = m.group(1)
        rest = s[m.end():]
    else:
        # 无书名号：形如「国家税务总局公告2014年第39号（…）」⇒ 取到第一个（或：或：即
        m2 = re.match(r"^([^（(：:，,。]+)", s)
        law = (m2.group(1) if m2 else "").strip()
        rest = s[len(law):]
    am = re.search(r"第([零一二三四五六七八九十百千两]+)条", rest) or \
        re.search(r"第([零一二三四五六七八九十百千两]+)条", s)
    return law, (am.group(1) if am else ""), s


def main() -> int:
    from engine import tax_redlines as TR                     # noqa: PLC0415

    law_idx = load_law_index()
    lib_idx = load_library()

    mappings: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []
    seen = set()

    for r in TR.all_redlines():
        rid = str(r.get("id") or "")
        for raw in (r.get("legal_basis") or []):
            law, art_cn, _ = parse_ref(raw)
            key = (rid, str(raw))
            if key in seen:
                continue
            seen.add(key)
            law_entry = law_idx.get(law) or law_idx.get(re.sub(r"^中华人民共和国", "", law))
            num = cn2num(art_cn) if art_cn else None
            if not law_entry:
                unresolved.append({"rule_id": rid, "raw": str(raw),
                                   "reason": "法名未在 `config/legal_law_codes.json` 登记（或无法名）"})
                continue
            if num is None:
                unresolved.append({"rule_id": rid, "raw": str(raw), "law": law,
                                   "law_code": law_entry["code"],
                                   "reason": "未取到条号（该依据为整法/文号引用，非条款级）"})
                continue
            art_full = "第%s条" % art_cn
            prov = lib_idx.get((law, art_full)) or lib_idx.get((law_entry["name"], art_full))
            if not prov:
                unresolved.append({"rule_id": rid, "raw": str(raw), "law": law,
                                   "law_code": law_entry["code"], "article": art_full,
                                   "reason": "正文库缺该条（`static/legal_library.json` 无此条 ⇒ 待补录）"})
                continue
            mappings.append({
                "rule_id": rid,
                "raw_basis": str(raw),
                "law": law_entry["name"],
                "law_code": law_entry["code"],
                "article": art_full,
                "provision_id": "%s-%03d" % (law_entry["code"], num),
                "verified": True,
                "provision_source": "static/legal_library.json",
                "content_sha256": _sha(prov["content"]),
            })

    # 反向索引：条款 → 引用它的规则（法规侧反查）
    by_provision: Dict[str, List[str]] = {}
    for m in mappings:
        by_provision.setdefault(m["provision_id"], [])
        if m["rule_id"] not in by_provision[m["provision_id"]]:
            by_provision[m["provision_id"]].append(m["rule_id"])

    payload = {
        "schema": 1,
        "updated": "2026-10-15",
        "note": ("★ **法规 ⇄ 规则双向关联表**（唯一权威）。\n"
                 "正向：`mappings[].rule_id → provision_id`；反向：`by_provision[provision_id] → [rule_id…]`。\n"
                 "★ 条款 ID = `{法短码}-{条号:03d}`；法短码唯一权威 `config/legal_law_codes.json`。\n"
                 "★ **只填可确证者**：`verified=true` 的条件是「法短码解析成功」**且**"
                 "「正文库确有该条正文」；其余一律进 `unresolved` 并写明原因（不确定就不报）。\n"
                 "★ `content_sha256` 取自正文库实际条目 → 可机器复核「关联指向的是真条文」。"),
        "rule_side": "engine/tax_redlines.py（RL-* 红线的 legal_basis）",
        "provision_side": "static/legal_library.json（条款正文）× config/legal_law_codes.json（法名短码）",
        "stats": {
            "total_refs": len(mappings) + len(unresolved),
            "verified": len(mappings),
            "unresolved": len(unresolved),
            "distinct_rules": len({m["rule_id"] for m in mappings}),
            "distinct_provisions": len(by_provision),
        },
        "mappings": sorted(mappings, key=lambda x: (x["rule_id"], x["provision_id"])),
        "by_provision": {k: sorted(v) for k, v in sorted(by_provision.items())},
        "unresolved": unresolved,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    st = payload["stats"]
    print("法规⇄规则关联：总引用 %d | 可确证 %d | 不可确证 %d | 涉及规则 %d | 涉及条款 %d"
          % (st["total_refs"], st["verified"], st["unresolved"],
             st["distinct_rules"], st["distinct_provisions"]))
    print("→ %s" % OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

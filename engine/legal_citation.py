# -*- coding: utf-8 -*-
"""法条引用单一权威：把「法名 / 法名+条款号」补全为「《法名》第X条：条文内容」。

用户口径（2026-09-27）：「法定依据要写到**具体哪一条、什么内容**」——只写法名
（如「《发票管理办法》」）或只写条款号（如「《增值税专用发票使用规定》第十四条」）
都不够，必须给出条款号 + 条文内容。

数据源（优先级）：
  1. `static/legal_library.json` —— 法条内容库（法名+条款号 → 内容），人工维护、可复核；
  2. 红线库 `tax_redlines.REDLINES` 的 `legal_basis` 中**已内嵌条文**的条目（`《X》第Y条：内容`），
     自动抽取复用（口径一致，非特例）；
  3. `static/legal_refs.json`（历史法条要点库，短名，如「征管法第63条」）。

解析规则：`《……》（可含公告号）` + `第X条[、第Y条][第Z款]` + `（说明）` + `：内容`。
解析不了或查不到内容的，**原样保留**（绝不臆造法条）。所有条目只读、不改引擎结论。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent

# 条款号：第X条[、第Y条]… [第Z款]
_ART_RE = re.compile(
    r"(第[一二三四五六七八九十百零〇\d]+条"
    r"(?:\s*[、,，]\s*第[一二三四五六七八九十百零〇\d]+条)*"
    r"(?:第[一二三四五六七八九十]+款)?)\s*$"
)
_LIB_CACHE: Optional[Dict[Tuple[str, str], str]] = None


def norm_law(s: str) -> str:
    """法名归一：去《》（），去掉「中华人民共和国」，去空白。"""
    s = str(s or "").replace("《", "").replace("》", "")
    s = s.replace("中华人民共和国", "")
    return re.sub(r"\s+", "", s)


def norm_art(a: str) -> str:
    return re.sub(r"\s+", "", str(a or ""))


def split_citation(s: str) -> Tuple[str, str, str, str]:
    """把一条引用拆成 (法名, 条款号, 括注, 内容)。拆不出的部分留空。

    支持：「《法名》第X条：内容」「《法名》（公告号）第X条」「《法名》第X条、第Y条（说明）」
    「（前缀）《法名》第X条：内容」等写法。
    """
    raw = str(s or "").strip()
    if not raw:
        return "", "", "", ""
    content = ""
    head = raw
    m = re.search(r"[：:]", raw)
    if m:
        head, content = raw[: m.start()], raw[m.end():].strip()
    head = head.strip()
    # ① 法名 = 首个《…》及其后紧跟的（…）；否则退化为取《…》所在片段
    law = ""
    rest = head
    ml = re.match(r"^(.*?《[^》]+》)(（[^（）]+）)?", head)
    if ml:
        law = (ml.group(1) + (ml.group(2) or "")).strip()
        rest = head[ml.end():].strip()
    else:
        law = head
        rest = ""
    # ② 尾部括注（如「（扣缴义务人全员全额扣缴申报）」）
    note = ""
    mn = re.search(r"（[^（）]{1,40}）\s*$", rest)
    if mn:
        note = mn.group(0)
        rest = rest[: mn.start()].strip()
    # ③ 条款号
    art = ""
    ma = _ART_RE.search(rest)
    if ma:
        art = ma.group(1)
        rest = rest[: ma.start()].strip()
    if rest:
        law = (law + rest).strip()
    return norm_law(law), norm_art(art), note, content


def _extract_from_redlines() -> Dict[Tuple[str, str], str]:
    """从红线库 legal_basis 已内嵌条文的条目抽取 (法名, 条款号) → 内容。"""
    out: Dict[Tuple[str, str], str] = {}
    try:
        from engine.tax_redlines import REDLINES
    except Exception:
        return out
    for r in REDLINES or []:
        lb = (r or {}).get("legal_basis")
        if isinstance(lb, str):
            lb = [lb]
        for item in (lb or []):
            if not isinstance(item, str):
                continue
            law, art, _note, content = split_citation(item)
            if law and content:
                out.setdefault((law, art), content)
    return out


def _load_library() -> Dict[Tuple[str, str], str]:
    global _LIB_CACHE
    if _LIB_CACHE is not None:
        return _LIB_CACHE
    lib: Dict[Tuple[str, str], str] = {}
    # ① 法条内容库
    for name in ("legal_library.json", "legal_refs.json"):
        p = _ROOT / "static" / name
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for e in (data if isinstance(data, list) else []):
            if not isinstance(e, dict):
                continue
            content = str(e.get("content") or "").strip()
            if not content:
                continue
            if e.get("law") and e.get("article"):
                lib.setdefault((norm_law(e["law"]), norm_art(e["article"])), content)
            elif e.get("law"):
                # 短名（如「征管法第63条」）→ 拆出条款号
                law, art, _n, _c = split_citation(str(e.get("law")))
                lib.setdefault((law, art), content)
    # ② 红线库内嵌条文（不覆盖①②中已有的同名同条）
    for k, v in _extract_from_redlines().items():
        lib.setdefault(k, v)
    _LIB_CACHE = lib
    return lib


def resolve_citation(s) -> str:
    """把一条引用解析为「《法名》第X条（括注）：内容」；查不到内容时原样返回。"""
    if isinstance(s, dict):  # 数据缺陷兜底：legal_basis 里混入 dict
        s = s.get("article") or s.get("law") or ""
    if not isinstance(s, str) or not s.strip():
        return ""
    raw = s.strip()
    law, art, note, content = split_citation(raw)
    if not law:
        return raw
    lib = _load_library()
    if content:                       # 条目内已内嵌条文
        head = f"《{law}》{art}" if art else f"《{law}》"
        return f"{head}{note}：{content}"
    if art:
        whole = lib.get((law, art))
        if whole:
            return f"《{law}》{art}{note}：{whole}"
        # 多条款并列：「第九条、第十条」→ 逐条拼内容
        parts = [p for p in re.split(r"[、,，]", art) if p.strip()]
        segs = []
        for p in parts:
            c = lib.get((law, norm_art(p)))
            if c:
                segs.append(f"{p}：{c}")
        if segs and len(segs) == len(parts):
            return f"《{law}》" + "；".join(segs) + note
        return raw
    # 裸法名（无条款号）：库中该法恰有一条时补全，否则原样（不臆造条款号）
    cands = [c for (l, _a), c in lib.items() if l == law]
    if len(cands) == 1:
        return f"《{law}》{note}：{cands[0]}"
    return raw


def format_legal_basis(items) -> str:
    """把 legal_basis（list/str）渲染为「…；…」，逐条补全条款号与内容，去重保序。"""
    if isinstance(items, str):
        items = [items]
    out: List[str] = []
    seen = set()
    for it in (items or []):
        t = resolve_citation(it)
        if not t:
            continue
        k = re.sub(r"\s+", "", t)
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return "；".join(out)

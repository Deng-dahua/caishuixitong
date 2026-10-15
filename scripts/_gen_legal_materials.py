# -*- coding: utf-8 -*-
"""案例/解读/问答 → 法规**可确证关联**生成器（STEP-EXT-LEGAL-FULL-MATCH 步骤 19）。

产物 `config/legal_materials.json`（**结论类 ⇒ 放 `config/`**，不放 `data/`）。

★ 为什么"可确证"而不是"关键词匹配"：
  官方材料的**摘要原文**里对法规的引用是**显式的书名号**（如「《税收征收管理法》第六十三条」），
  这是**作者/官方写下的引用**，不是我们的猜测 ⇒ 只认这两类证据：
    ① **书名号内**的法规名（严格）；
    ② 正文中出现的**带法规后缀的完整法名**（「…法」「…条例」「…办法」「…规定」「…公告」），
       且必须与法名规范表（`config/legal_law_codes.json`）**别名精确匹配**。
  **不做**泛关键词/相似度匹配（那会产生"看起来相关"的假关联）。

★ 匹配粒度如实声明：**只能确证到"法规"级**（某材料引用了某部法），
  **不能**确证到"条款"级（材料是否指向第 N 条，摘要往往不写）⇒ 输出字段
  `granularity="law"`，条款级关联**留空待人工**，不猜。

用法：`./.venv/Scripts/python.exe scripts/_gen_legal_materials.py`
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "legal_crawl" / "fgk_categories.json"
LAWS = ROOT / "config" / "legal_law_codes.json"
OUT = ROOT / "config" / "legal_materials.json"

#: 书名号引用（官方摘要里的显式引用）
BOOK_RE = re.compile(r"《([^》]{2,60})》")
#: 带法规后缀的完整法名（用于无书名号的直接提及）
LAW_LIKE_RE = re.compile(r"[\u4e00-\u9fff]{2,30}?(?:法|条例|实施细则|办法|规定|公告|通知|决定|解释)")
#: 实施后缀 —— ★ 必须**向右扩展**：否则「…税收征收管理法**实施细则**」会被截成母法
#   「…税收征收管理法」⇒ **误报一部并未被引用的法**（实测抓到）。
IMPL_SUFFIX_RE = re.compile(r"^(?:实施细则|实施条例|施行细则|暂行条例|实施办法)")


def _norm(s: Any) -> str:
    t = "".join(str(s or "").split())
    return t[7:] if t.startswith("中华人民共和国") else t


def load_alias_index() -> Dict[str, str]:
    """别名 → 法短码（唯一权威 `config/legal_law_codes.json`）。"""
    d = json.loads(LAWS.read_text(encoding="utf-8"))
    idx: Dict[str, str] = {}
    for l in d.get("laws") or []:
        code = str(l.get("code") or "")
        if not code:
            continue
        for name in [l.get("name")] + list(l.get("aliases") or []):
            k = _norm(name)
            if k:
                idx[k] = code
    return idx


def match_laws(text: str, idx: Dict[str, str]) -> List[Dict[str, str]]:
    """从一段文本里抽**显式法规引用**（书名号优先，其次带后缀全名）。

    ★ 两条防误报规则（均为实测踩坑后补）：
      ① 全名提及**只在书名号区间之外**做 —— 书名号内已处理，重复扫会多报；
      ② 全名提及命中后**向右吃下实施后缀**（实施细则/实施条例/…）—— 否则
         「…征收管理法**实施细则**」会被截成母法，凭空多出一部法。
    """
    out: List[Dict[str, str]] = []
    seen: Set[str] = set()

    def _add(raw: str, how: str) -> None:
        key = _norm(raw)
        cand = [key]
        m = re.match(r"^(.+?)(?:第[零一二三四五六七八九十百千]+条.*)$", key)
        if m:
            cand.insert(0, m.group(1))
        for c in cand:
            code = idx.get(c)
            if code:
                if code not in seen:
                    seen.add(code)
                    out.append({"law_code": code, "matched_ref": raw.strip(), "matched_by": how})
                return

    spans: List[tuple] = []
    for m in BOOK_RE.finditer(text):
        spans.append((m.start(), m.end()))
        _add(m.group(1), "书名号引用")

    # 书名号之外的剩余文本（用等长空白替换，保持索引位置可读）
    rest = list(text)
    for s, e in spans:
        for i in range(s, min(e, len(rest))):
            rest[i] = " "
    rest = "".join(rest)
    for m in LAW_LIKE_RE.finditer(rest):
        raw = m.group(0)
        tail = IMPL_SUFFIX_RE.match(rest[m.end():])
        if tail:
            raw = raw + tail.group(0)
        _add(raw, "全名提及")
    return out


def main() -> int:
    if not SRC.exists():
        print("[FATAL] 采集物不存在：%s（先跑 scripts/_crawl_fgk_categories.py）" % SRC)
        return 2
    raw = json.loads(SRC.read_text(encoding="utf-8"))
    idx = load_alias_index()
    print("法名别名索引：%d 条" % len(idx))

    materials: List[Dict[str, Any]] = []
    per_kind: Dict[str, int] = {}
    linked = 0
    by_law: Dict[str, List[str]] = {}
    for kind, cat in (raw.get("categories") or {}).items():
        items = cat.get("items") or []
        per_kind[kind] = len(items)
        for i, x in enumerate(items):
            mid = "MAT-%s-%04d" % ({"案例": "CASE", "解读": "INT", "问答": "FAQ"}.get(kind, "X"), i + 1)
            title = str(x.get("title") or "")
            snippet = str(x.get("snippet") or "")
            hits = match_laws(title + " " + snippet, idx)
            rec: Dict[str, Any] = {
                "material_id": mid,
                "kind": kind,
                "title": title,
                "snippet": snippet,
                "doc_no": str(x.get("doc_no") or ""),
                "publisher": str(x.get("pub_name") or ""),
                "published_at": str(x.get("published_at") or ""),
                "url": str(x.get("url") or ""),
                "source": str(x.get("source") or ""),
                "related_law_codes": [h["law_code"] for h in hits],
                "matched_refs": hits,
                "granularity": "law",
                "granularity_note": ("关联**只到法规级**（材料显式引用了该法）；"
                                     "是否指向具体条款，摘要未写明 ⇒ 条款级留空待人工，不猜。"),
            }
            if hits:
                linked += 1
                for h in hits:
                    by_law.setdefault(h["law_code"], []).append(mid)
            materials.append(rec)

    doc = {
        "schema": 1,
        "source": "data/legal_crawl/fgk_categories.json（三平台官方材料）",
        "authority": ("案例/解读/问答材料的**关联结论**唯一权威（派生自官方摘要原文的"
                      "**显式引用**，非关键词匹配）"),
        "updated": "2026-10-15",
        "counts": {"total": len(materials), "by_kind": per_kind,
                   "linked_to_law": linked, "unlinked": len(materials) - linked,
                   "distinct_law_codes": len(by_law)},
        "materials": materials,
        "by_law_code": {k: sorted(v) for k, v in sorted(by_law.items())},
        "_note": ("★ 只认两类**显式引用**证据：书名号引用 / 带法规后缀的全名提及，"
                  "且须与 `config/legal_law_codes.json` 别名精确匹配。"
                  "**不做**泛关键词或相似度匹配（避免产生假关联）。"
                  "关联粒度=法规级（`granularity=\"law\"`）。"
                  "未匹配到任何法规的材料**照样保留**（`related_law_codes=[]`），不丢数据。"),
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    c = doc["counts"]
    print("材料 %d 条（案例 %d / 解读 %d / 问答 %d）"
          % (c["total"], per_kind.get("案例", 0), per_kind.get("解读", 0), per_kind.get("问答", 0)))
    print("关联到法规：%d 条（未关联 %d 条，如实保留）；涉及 %d 部法"
          % (c["linked_to_law"], c["unlinked"], c["distinct_law_codes"]))
    print("→ %s" % OUT)
    top = sorted(by_law.items(), key=lambda kv: -len(kv[1]))[:8]
    print("引用最多的法：")
    for code, ids in top:
        print("   %-26s %d 条材料" % (code, len(ids)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

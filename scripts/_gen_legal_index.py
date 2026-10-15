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
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CRAWL = ROOT / "data" / "legal_crawl"

# ★★ 2026-10-15 收敛：中文数字解析改用**唯一权威** `engine/cnnum.py`。
#   原私有实现只支持到「九十九」，**「第一百零三条」解析不出** ⇒ 条款索引里
#   整部法全文入库后 1806 条拿不到 `provision_id`（全是第一百条以上）。
#   项目铁律：同一件事不得多头实现（本轮实测同类实现曾有 5 处，行为还不一致）。
from engine.cnnum import cn_to_int as cn2num        # noqa: E402  （保留旧名，调用点零改动）


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _load(p: Path, default: Any = None) -> Any:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def main() -> int:
    lib = _load(ROOT / "static" / "legal_library.json", []) or []
    reg = _load(ROOT / "config" / "legal_law_codes.json", {}) or {}
    topics = (_load(ROOT / "config" / "legal_topics.json", {}) or {}).get("topics") or []

    # ★★ 2026-10-16 修（实测缺陷）：法名索引**必须按 `canonical_law` 归一后建键**。
    #   原实现用**原始字符串**直接比对 ⇒ 登记名「财政部 国家税务总局关于…通知」
    #   与库内名「财政部国家税务总局关于…通知」**只差一个空格**就匹配不上
    #   ⇒ 实测 15 处通知/公告类条文拿不到 `provision_id`（法短码明明已登记）。
    #   归一实现走**唯一权威** `engine.legal_version.canonical_law`（去空白/《》/国名前缀），
    #   不得在此另写一套。
    from engine.legal_version import canonical_law as _cl_law            # noqa: PLC0415

    law_idx: Dict[str, Dict[str, Any]] = {}
    for l in reg.get("laws") or []:
        for k in [l["name"], re.sub(r"^中华人民共和国", "", l["name"])] + list(l.get("aliases") or []):
            if k:
                law_idx[_cl_law(k)] = l

    # 专题打标词表（专题 → 词）
    topic_kw: List[Tuple[str, str, List[str]]] = []
    for t in topics:
        kws = (t.get("inventory_keywords") or t.get("keywords") or [])
        if kws:
            topic_kw.append((t["id"], t["name"], [str(k) for k in kws if k]))

    # ── 条款索引（只覆盖已核实正文）──
    provisions: List[Dict[str, Any]] = []
    uncoded: List[str] = []
    #: **整文条目**（无条号，如"正文"）：按法规级关联，**不臆造**条款 ID
    article_less: List[str] = []
    for e in lib:
        law = str(e.get("law") or "")
        art = str(e.get("article") or "")
        content = str(e.get("content") or "")
        le = law_idx.get(_cl_law(law))
        code = (le or {}).get("code") or ""
        # ── `provision_id` 派生（★ 唯一性由结构保证，见下）────────────────
        #   基础：`{法短码}-{条号:03d}`
        #   必须再带**子定位后缀**，否则不同条文撞号（实测 60 处）：
        #   · 「第X条**之N**」（刑法 53 条）        ⇒ `-Z{N}`
        #     —— 只取 X 时「第十七条」与「第十七条之一」同 ID；
        #   · 「第X条**第N款**」（库内 1 条）        ⇒ `-K{N}`
        #   · 「**附件N**第X条」（库内 1 条）        ⇒ 条号前插 `ATT{N}-`
        #     —— 附件另有独立条号体系，与正文同号不同条。
        m_att = re.search(r"附件([零一二三四五六七八九十百千两0-9]+)", art)
        m = re.search(r"第([零一二三四五六七八九十百千两]+)条(?:之([零一二三四五六七八九十百千两]+))?", art)
        m_k = re.search(r"第([零一二三四五六七八九十百千两]+)款", art)
        num = cn2num(m.group(1)) if m else None
        sub = cn2num(m.group(2)) if (m and m.group(2)) else None
        kuan = cn2num(m_k.group(1)) if m_k else None
        att = m_att.group(1) if m_att else ""
        pid = ""
        if code and num:
            pid = "%s%s%03d" % (code + "-", ("ATT%s-" % att) if att else "", num)
            if sub:
                pid += "-Z%d" % sub
            if kuan:
                pid += "-K%d" % kuan
        if not pid:
            if m:                                   # 有条号却派不出 ⇒ 法名/短码缺口（真缺口）
                uncoded.append("%s %s" % (law, art))
            else:                                   # **整文条目**（无条号，如"正文"）⇒ 按法规级关联
                article_less.append("%s %s" % (law, art))
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
    # ★ 唯一性自检：`provision_id` 是条款级关联的**主键**，撞号即关联错条文。
    _seen: Dict[str, List[str]] = {}
    for p in with_pid:
        _seen.setdefault(p["provision_id"], []).append("%s %s" % (p["law"], p["article"]))
    dup_ids = {k: v for k, v in _seen.items() if len(v) > 1}
    if dup_ids:
        print("!! `provision_id` 撞号 %d 处（条款级关联会指错条文）：%s"
              % (len(dup_ids), list(dup_ids.items())[:5]))
    (ROOT / "config" / "legal_provisions.json").write_text(json.dumps({
        "schema": 1, "updated": "2026-10-16",
        "note": ("★ **条款索引**（派生层）：`provision_id` → 条文定位与标签；"
                 "**不含正文**（正文唯一权威 `static/legal_library.json`，写入走 `_load_legal_texts.py`）。"
                 "`provision_id` = `{法短码}-{条号:03d}`，并带**子定位后缀**保证唯一："
                 "「第X条之N」⇒ `-Z{N}`（刑法 53 条）；「第X条第N款」⇒ `-K{N}`；"
                 "「附件N第X条」⇒ `{短码}-ATT{N}-{X:03d}`（附件另有独立条号体系）。"
                 "`content_sha256` 可反向校验指向的条文。"
                 "★ `provision_id` 为 null 分两类（如实暴露，互不混淆）："
                 "① `uncoded`＝有条号但法名/短码缺口（真缺口）；"
                 "② `article_less`＝**整文条目**（本身无条号，如「正文」）⇒ 按法规级关联。"),
        "count": len(provisions), "with_provision_id": len(with_pid),
        "article_less_count": len(article_less),
        "duplicate_ids": {k: v for k, v in sorted(dup_ids.items())},
        "uncoded": uncoded,
        "article_less": article_less,
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
    # ── 去重（指令 3.3 明确要求：按文号 / URL / 内容去重）──
    #   ★ 实测缺陷（2026-10-15）：`fgk`（法规栏目）与 `fgk-category`（案例/解读/问答栏目）
    #     会抓到**同一篇内容**（如政策问答）⇒ 不去重时目录里同一标题出现 2 次
    #     （实测 540 种标题、多出 561 条）⇒ 前端列表出现重复项。
    #   去重键优先级：URL（最可靠）→ 文号 → 标题+日期。合并时保留"更权威"的一条
    #   （有文号优先 → 法规类 kind 优先 → fgk 原栏目优先），并把来源记为合并来源。
    _REG_KINDS = {"法律", "行政法规", "国务院文件", "税务部门规章", "税务规范性文件",
                  "财税文件", "工作通知", "其他文件"}

    def _key(c: Dict[str, Any]) -> Any:
        # ★ URL 去重须**只取路径**：实测同一内容在两个栏目页给出的 URL 只差**域名**
        #   （`www.chinatax.gov.cn/zcfgk/c100024/c5252370/content.html` vs
        #    `fgk.chinatax.gov.cn/zcfgk/c100024/c5252370/content.html`）
        #   ⇒ 用完整 URL 作键**永远去不掉**（实测 540 种标题重复一条未合并）。
        u = str(c.get("url") or "").strip()
        if u:
            path = urlparse(u).path
            if path:
                return ("path", path)
            return ("url", u)
        dn = str(c.get("doc_no") or "").strip()
        if dn:
            return ("doc_no", dn)
        return ("title", str(c.get("title") or "").strip(),
                str(c.get("published_at") or "").strip())

    def _rank(c: Dict[str, Any]) -> tuple:
        return (1 if str(c.get("doc_no") or "").strip() else 0,
                1 if str(c.get("kind") or "") in _REG_KINDS else 0,
                1 if str(c.get("source")) == "fgk" else 0,
                len(str(c.get("title") or "")))

    _merged: Dict[Any, Dict[str, Any]] = {}
    _dup_n = 0
    for c in catalog:
        k = _key(c)
        old = _merged.get(k)
        if old is None:
            _merged[k] = c
            continue
        _dup_n += 1
        keep, drop = (c, old) if _rank(c) > _rank(old) else (old, c)
        # 合并：保留 `keep` 为主体，把 `drop` 的独有信息补上（来源并记、kind 并记）
        srcs = {s for s in (str(keep.get("source")), str(drop.get("source"))) if s}
        keep = dict(keep)
        keep["source"] = "+".join(sorted(srcs))
        if str(drop.get("kind") or "") and str(drop.get("kind")) != str(keep.get("kind")):
            keep["kind_alt"] = str(drop.get("kind"))
        _merged[k] = keep
    catalog = list(_merged.values())
    if _dup_n:
        print("目录去重：合并 %d 条重复（按 URL/文号/标题+日期）" % _dup_n)

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

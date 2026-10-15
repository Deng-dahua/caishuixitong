# -*- coding: utf-8 -*-
"""生成 `config/legal_relations.json`（**法规关系表**：修订 / 废止 / 引用，唯一权威）。

## 双源（避免单源遗漏）
| 源 | 字段 | 提供的关系 |
|---|---|---|
| fgk 全量清单 | `description`（题注/注释信息，实测 1422 条有值） | 「××年××号修订」「…决定第N次修正」「附件中部分…有废止」 |
| flk 详情 | `lsyg`（历史沿革）、`xgzl`（相关制度） | 同法的**版本链**（bbbs + 公布日期）、相关的国务院令/修改决定 |

## 铁律
- **只登记能从原文描述里确证的关系**；解析不出目标 ⇒ 记 `target_raw` 并标 `unresolved`
  （**不猜、不编造**）。描述原文一律保留在 `evidence` 里，可人工复核。
- 关系类型（数据驱动，新增一类＝加一行）：`amended`（修订/修正）、`abolished`（废止/失效）、
  `cited_by`（据以制定/依据）。

用法：
    ./.venv/Scripts/python.exe scripts/_gen_legal_relations.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CRAWL = ROOT / "data" / "legal_crawl"
OUT = ROOT / "config" / "legal_relations.json"

#: 关系类型识别（**数据驱动**：新增一类＝加一行）——(类型, 正则, 中文名)
REL_PATTERNS: Tuple[Tuple[str, str, str], ...] = (
    ("amended", r"(?:修订|修正|修改)", "修订/修正"),
    ("abolished", r"(?:废止|失效|停止执行)", "废止/失效"),
    ("cited_by", r"(?:根据|依据)", "据以制定/依据"),
)

#: 由**结构化来源**（flk `xgzl` 相关制度）产出的关系类型 —— 不靠正则，故单列。
#  ★ `relation_cn` 必须**只从白名单映射**取值：早前把原始 `busi_type`（"国务院令"/
#    "修改决定"/"审议结果的报告"…）直接当 `relation_cn` ⇒ 关系类型里混进**非关系词**，
#    前端"按关系类型"筛选会出现无意义选项（**错误信息级别**，实测报出）。
EXTRA_RELATION_TYPES: Dict[str, str] = {
    "related": "相关制度",
}

#: 文号形态（用于从描述里抽被引用文件）——★ 两种形态**分开**，勿混
#:   ① 带年份：财税〔2000〕187号 / 国税发〔2000〕187号 / 国家税务总局公告2019年第38号
#:   ② 纯序号：国务院令第499号 / 国家税务总局令第56号（**令号只有 2~4 位，早期常为 3 位**）
#:   ⚠ 2026-10-15 实测踩坑：第一版只写 `\d{4}` 年份 ⇒ 「国务院令第499号」**匹配不到**
#:     （499 是 3 位）⇒ 目标全空。分形态写后修复。
DOC_NO_RE = re.compile(
    r"(?:(?:国务院令|国家税务总局令)\s*第\s*\d{1,4}\s*号"
    r"|(?:国家税务总局公告|财政部\s*税务总局公告|财政部\s*国家税务总局公告)"
    r"\s*\d{4}\s*年第\s*\d+\s*号"
    r"|(?:财税|国税发|国税函|税总发|税总函|发改财金|法释|主席令)"
    r"\s*[〔\[]\s*\d{4}\s*[〕\]]\s*第?\s*\d+\s*号)")
#: 书名号引用
BOOK_RE = re.compile(r"《([^》]{3,60})》")
#: 日期
DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
#: 就近上下文窗口（关系词前后各取这么多字符做目标/日期提取）
_CTX_WIN = 140


def _load(name: str) -> Any:
    p = CRAWL / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def parse_description(text: str) -> List[Dict[str, Any]]:
    """从一条 `description` 解析出关系（**只认能确证的**）。

    ★ 关键：目标与日期在**关系词就近的上下文**里取，而不是取全文第一个 ——
      实测踩坑：一段题注可含多个日期（"2016年…通过 根据2018年…决定修正"），
      取全文首个日期会把"修订"错配到**通过日期**上（实测「环境保护税法」被错配）。
    """
    out: List[Dict[str, Any]] = []
    t = str(text or "").strip()
    if not t:
        return out
    for rel, pat, cn in REL_PATTERNS:
        m = re.search(pat, t)
        if not m:
            continue
        lo = max(0, m.start() - _CTX_WIN)
        hi = min(len(t), m.end() + _CTX_WIN)
        ctx = t[lo:hi]
        # 目标：优先文号（在就近上下文里），其次书名号引用
        docs = DOC_NO_RE.findall(ctx)
        books = BOOK_RE.findall(ctx)
        targets = [d.strip() for d in docs] or [b.strip() for b in books]
        # 日期：就近上下文里**紧随关系词之后**的第一个日期；没有则取上下文里最后一个
        after = ctx[ctx.find(m.group(0)) + len(m.group(0)):]
        dm = DATE_RE.search(after) or DATE_RE.search(ctx)
        date = ("%s-%02d-%02d" % (dm.group(1), int(dm.group(2)), int(dm.group(3)))) if dm else ""
        out.append({
            "relation": rel, "relation_cn": cn,
            "target": targets[0] if targets else "",
            "targets_all": targets,
            "date": date,
            "evidence": t[:400],
            "basis": "fgk.description（题注/注释信息原文）",
            "source": "fgk.chinatax.gov.cn",
        })
    return out


def law_of(title: str, law_codes: Dict[str, Dict[str, Any]]) -> Tuple[str, str]:
    """标题 → (规范法名, 短码)；匹配不到 ⇒ ("", "")。"""
    base = re.sub(r"^中华人民共和国", "", str(title or "")).strip()
    for key in (title, base):
        e = law_codes.get(key)
        if e:
            return e["name"], e["code"]
    return "", ""


def main() -> int:
    fgk = _load("fgk_files.json") or {}
    flk = _load("flk_laws.json") or {}
    reg = json.loads((ROOT / "config" / "legal_law_codes.json").read_text(encoding="utf-8"))
    law_codes: Dict[str, Dict[str, Any]] = {}
    for l in reg["laws"]:
        law_codes[l["name"]] = l
        law_codes[re.sub(r"^中华人民共和国", "", l["name"])] = l
        for a in (l.get("aliases") or []):
            law_codes[a] = l
            law_codes[re.sub(r"^中华人民共和国", "", a)] = l

    relations: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []
    seen = set()

    # ── 源 1：fgk description ──
    n_desc = 0
    for it in (fgk.get("items") or []):
        desc = it.get("description")
        if not desc:
            continue
        n_desc += 1
        name, code = law_of(it.get("title"), law_codes)
        for r in parse_description(desc):
            key = (it.get("title"), r["relation"], r["target"], r["date"])
            if key in seen:
                continue
            seen.add(key)
            rec = {"subject_title": it.get("title"), "subject_law": name,
                   "subject_code": code, "subject_doc_no": it.get("doc_no"),
                   "subject_url": it.get("url"), **r}
            if r["target"] or r["date"]:
                relations.append(rec)
            else:
                rec["unresolved_reason"] = "描述含关系词但未解析出目标文件与日期"
                unresolved.append(rec)

    # ── 源 2：flk lsyg（历史沿革 = 同一部法的版本链）+ xgzl（相关制度）──
    n_flk = 0
    for l in (flk.get("laws") or []):
        m = l.get("matched")
        if not m:
            continue
        n_flk += 1
        hist = l.get("history") or []
        if len(hist) > 1:
            # 历史沿革按公布日期降序 ⇒ 后者是前者的**前身**（版本链）
            for i in range(len(hist) - 1):
                cur, prev = hist[i], hist[i + 1]
                key = (l["law_name"], "amended", prev.get("title"), prev.get("gbrq"))
                if key in seen:
                    continue
                seen.add(key)
                relations.append({
                    "subject_title": m.get("title"), "subject_law": l["law_name"],
                    "subject_code": l.get("law_code") or "", "subject_doc_no": "",
                    "subject_url": "", "relation": "amended", "relation_cn": "修订/修正",
                    # ★ 2026-10-15 修：`relation_cn` 必须**只取白名单映射**。早前这里写死
                    #   "版本更替"，而 fgk 侧同一 `relation` 用"修订/修正" ⇒ 同一关系类型
                    #   出现两个中文名（前端按 relation_cn 分组会裂开）。版本链的说明放
                    #   `note`，不进 `relation_cn`。
                    "note": "同一部法的版本链（flk 历史沿革）",
                    "target": prev.get("title"), "targets_all": [prev.get("title")],
                    "date": prev.get("gbrq") or "",
                    "evidence": "flk 历史沿革：%s（%s）→ %s（%s）" % (
                        cur.get("title"), cur.get("gbrq"), prev.get("title"), prev.get("gbrq")),
                    "basis": "flk.flfgDetails.lsyg（历史沿革）",
                    "source": "flk.npc.gov.cn",
                })
        for x in (l.get("doc_num_from_xgzl") or []):
            key = (l["law_name"], "related", x.get("title"), "")
            if key in seen:
                continue
            seen.add(key)
            relations.append({
                "subject_title": m.get("title"), "subject_law": l["law_name"],
                "subject_code": l.get("law_code") or "", "subject_doc_no": "",
                "subject_url": "",
                # ★ 2026-10-15 修（**错误信息级别**）：早前把 `busi_type`（"国务院令"/"修改决定"）
                #   直接当 `relation_cn` ⇒ 关系类型里混进"国务院令""修改决定""审议结果的报告"
                #   等**非关系词**，前端"按关系类型"筛选会给出无意义选项。
                #   现改为独立一类 `related`（相关制度），原始形态放 `target_type`。
                "relation": "related", "relation_cn": "相关制度",
                "target_type": str(x.get("busi_type") or ""),
                "target": x.get("title"), "targets_all": [x.get("title")],
                "date": "", "evidence": "flk 相关制度：%s（%s / %s）" % (
                    x.get("title"), x.get("busi_type"), x.get("file_type")),
                "basis": "flk.flfgDetails.xgzl（相关制度）",
                "source": "flk.npc.gov.cn",
            })

    from collections import Counter
    by_rel = Counter(r["relation"] for r in relations)
    payload = {
        "schema": 1, "updated": "2026-10-15",
        "note": ("★ **法规关系表**（唯一权威）：修订 / 废止 / 引用。"
                 "双源 = fgk 题注描述 + flk 历史沿革与相关制度。"
                 "**只登记能从原文确证的关系**，解析不出的进 `unresolved`（不猜、不编造）；"
                 "每条 relation 都带 `evidence` 原文，可人工复核。"),
        "relation_types": dict(
            list({r: c for r, _p, c in REL_PATTERNS}.items())
            + list(EXTRA_RELATION_TYPES.items())),
        "sources": {
            "fgk": {"items_scanned": len(fgk.get("items") or []), "with_description": n_desc},
            "flk": {"laws_matched": n_flk},
        },
        "stats": {
            "total": len(relations), "unresolved": len(unresolved),
            "by_relation": dict(by_rel.most_common()),
            "with_target": sum(1 for r in relations if r.get("target")),
            "with_date": sum(1 for r in relations if r.get("date")),
        },
        "relations": relations,
        "unresolved": unresolved[:200],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    st = payload["stats"]
    print("法规关系：%d 条（含目标 %d / 含日期 %d）｜未解析 %d"
          % (st["total"], st["with_target"], st["with_date"], st["unresolved"]))
    print("按类型:", json.dumps(st["by_relation"], ensure_ascii=False))
    print("源：fgk 扫 %d 条（%d 条有 description）｜flk 命中 %d 部"
          % (payload["sources"]["fgk"]["items_scanned"], n_desc, n_flk))
    print("→ %s" % OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

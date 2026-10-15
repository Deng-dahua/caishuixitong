# -*- coding: utf-8 -*-
"""**三源合并总账**：把 fgk 全量 + flk 元数据 + 12366 落成一份可溯源的全库总账。

## 为什么需要"合并总账"
三个数据源**职责不同、互相补位**（实测结论）：
| 源 | 覆盖 | 独有价值 |
|---|---|---|
| **fgk** 税费政策法规库（列表全量遍历） | **5475 条**：法律/行政法规/国务院文件/部门规章/规范性文件/财税文件/工作通知 | **正文**（content.html）+ 文号/发文单位/税费类型/标签 |
| **flk** 国家法律法规数据库 | 34 部（法律 21 / 行政法规 13） | 法律/行政法规的**权威元数据 + 修订链（历史沿革）+ 相关制度**；效力状态 4 档 |
| **12366** 纳税服务平台 | 问答/指引 | 办税口径问答 |

★ 关键实测：fgk **列表遍历能拿到「法律/行政法规」**（法律 75 / 行政法规 65 条），
而**检索接口拿不到**（命中 0）。⇒ 列表遍历是"横向到边"的正解。

## 产出
`data/legal_crawl/legal_corpus_master.json` —— 全库总账（含各源条数、分层统计、逐源清单）
`docs/STEP-EXT-LEGAL-FULL_全库总账_20261015.md` —— 人读版
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CRAWL = ROOT / "data" / "legal_crawl"

#: 指令 3.2 的 14 类文件类型 → 归集口径（数据驱动：新增一类＝加一行）
KIND_MAP: Dict[str, str] = {
    "法律": "法律", "宪法": "法律",
    "行政法规": "行政法规", "国务院文件": "行政法规",
    "司法文件": "司法解释",
    "税务部门规章": "部门规章",
    "税务规范性文件": "规范性文件", "财税文件": "规范性文件",
    "其他文件": "其他文件", "工作通知": "通知", "国务院令": "行政法规",
}


def _j(name: str) -> Any:
    p = CRAWL / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main() -> int:
    fgk = _j("fgk_files.json") or {}
    flk = _j("flk_laws.json") or {}
    t001 = _j("TOPIC-001_inventory.json") or {}
    t001_tg = _j("TOPIC-001_targets.json") or {}
    t001_srch = _j("TOPIC-001_search.json") or {}
    t001_rep = _j("TOPIC-001_report.json") or {}

    fg_items: List[Dict[str, Any]] = fgk.get("items") or []
    fg_eff = Counter((x.get("effect_level") or x.get("channel_name") or "（未标注）") for x in fg_items)
    fg_kind = Counter(KIND_MAP.get(k, k) for k in fg_eff.elements())
    fg_docs = [x for x in fg_items if x.get("doc_no")]
    fg_srcs = Counter(x.get("source") for x in fg_items)

    flk_laws = flk.get("laws") or []
    flk_matched = [x for x in flk_laws if x.get("matched")]
    flk_oos = [x for x in flk_laws if x.get("miss_reason") == "out_of_scope"]
    flk_nf = [x for x in flk_laws if x.get("miss_reason") == "not_found_in_flk"]

    master = {
        "generated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S%z"),
        "note": ("★ **法规全库总账**：三源合并。各源职责不同、互相补位；"
                 "本表只做**统计与索引**，不复制条文（正文各自溯源）。"),
        "sources": [
            {"id": "fgk", "name": "税费政策法规库", "host": "fgk.chinatax.gov.cn",
             "api": "POST https://www.chinatax.gov.cn/getFileListByCodeId",
             "method": "栏目列表全量遍历（**非检索**）",
             "count": len(fg_items), "with_doc_no": len(fg_docs),
             "channels": fgk.get("channels"),
             "by_effect_level": dict(fg_eff.most_common()),
             "by_kind": dict(fg_kind.most_common())},
            {"id": "flk", "name": "国家法律法规数据库（全国人大）", "host": "flk.npc.gov.cn",
             "api": "POST /law-search/search/list + GET /law-search/search/flfgDetails",
             "method": "按法名精确检索（flk 只收法律/行政法规/司法解释）",
             "count": len(flk_matched),
             "out_of_scope": len(flk_oos), "not_found": len(flk_nf),
             "by_level": flk.get("by_level"), "by_effect": flk.get("by_effect"),
             "extra_value": "法律/行政法规的**修订链（history/历史沿革）**与相关制度（xgzl）"},
            {"id": "12366", "name": "12366 纳税服务平台", "host": "12366.chinatax.gov.cn",
             "method": "与 fgk 同站标识（bm29000002）⇒ 问答/指引类随 fgk 栏目一并取得",
             "count": fg_eff.get("政策问答", 0),
             "note": "全库内「政策问答」类 %d 条已含在 fgk 计数中（不重复计）" % fg_eff.get("政策问答", 0),
             "supplement": "另经检索通道补充：解读 %d 条等（见 TOPIC-001_search.json 的 type_dist）"
                           % (t001_rep.get("type_dist") or {}).get("解读", 0)},
        ],
        "union_estimate": {
            "fgk_total": len(fg_items), "flk_laws": len(flk_matched),
            "note": "两源**有交集**（法律/行政法规在两边都有：fgk 给正文、flk 给权威元数据与修订链）"
                    "⇒ 总数不是简单相加；按「法」去重的口径见 legal_law_codes.json（82 部）。",
        },
        "topic_views": {
            "TOPIC-001": {
                "name": t001.get("topic_name"), "hit_total": t001.get("hit_total"),
                "effect_stats": t001.get("effect_stats"),
                "layer_counts": {l["title"]: l["count"] for l in (t001.get("layers") or [])},
                "other_count": len(t001.get("other") or []),
                "targets_matched": t001_tg.get("matched_n"),
                "targets_total": t001_tg.get("targets_n"),
            },
        },
        "_disclaimer": ("★ 本总账是**采集候选**，未逐条人工核实；效力等级/文件类型取自数据源字段"
                        "（**未自行判定**）；空层/未命中一律如实标注，**未编造补全**。"
                        "入库唯一走 `scripts/_load_legal_texts.py`。"),
    }
    (CRAWL / "legal_corpus_master.json").write_text(
        json.dumps(master, ensure_ascii=False, indent=1), encoding="utf-8")

    L = ["# 法规全库总账（STEP-EXT-LEGAL-FULL，2026-10-15）", "",
         "> 三源合并。**各源职责不同、互相补位**；本表只做统计与索引，不复制条文。", "",
         "## 一、各源规模", "",
         "| 源 | 域名 | 取数方式 | 条数 | 备注 |", "|---|---|---|---|---|"]
    for s in master["sources"]:
        L.append("| %s | %s | %s | %s | %s |" % (
            s["name"], s["host"], s["method"],
            s.get("count") if s.get("count") is not None else "见备注",
            s.get("extra_value") or ("含发文字号 %d 条" % s.get("with_doc_no", 0)
                                     if s.get("with_doc_no") else "")))
    L += ["", "## 二、fgk 全量分层（**横向到边**的实证）", "",
          "| 效力等级（库内字段） | 条数 |", "|---|---|"]
    for k, v in (fg_eff.most_common()):
        L.append("| %s | %d |" % (k, v))
    L += ["", "> ★ 实测要点：**fgk 列表遍历能取到「法律 75 / 行政法规 65 / 国务院文件 35」**，"
          "而**检索接口对「刑法/征管法/发票管理办法」命中 0**。"
          "⇒ 「横向到边」必须走列表遍历，不能靠检索。", "",
          "## 三、flk（法律/行政法规权威元数据）", "",
          "| 项目 | 值 |", "|---|---|",
          "| flk 命中 | %d 部 |" % len(flk_matched),
          "| 层级分布 | %s |" % json.dumps(flk.get("by_level"), ensure_ascii=False),
          "| 效力分布 | %s |" % json.dumps(flk.get("by_effect"), ensure_ascii=False),
          "| 不属 flk 范围（部门规章/规范性文件，由 fgk 承担） | %d 部 |" % len(flk_oos),
          "| 应属 flk 范围但未检索到（待人工核查） | %d 部 |" % len(flk_nf), "",
          "## 四、专题视图（TOPIC-001 虚开发票）", "",
          "| 项目 | 值 |", "|---|---|",
          "| 全库命中 | %d 条 |" % (t001.get("hit_total") or 0),
          "| 分层 | %s |" % json.dumps(
              {l["title"]: l["count"] for l in (t001.get("layers") or [])}, ensure_ascii=False),
          "| 定向目标命中 | %s / %s |" % (t001_tg.get("matched_n"), t001_tg.get("targets_n")),
          "| 效力状态分布 | %s |" % json.dumps(t001.get("effect_stats"), ensure_ascii=False),
          "", "---", "", master["_disclaimer"]]
    dp = ROOT / "docs" / "STEP-EXT-LEGAL-FULL_全库总账_20261015.md"
    dp.write_text("\n".join(L), encoding="utf-8")

    print("fgk %d 条（含文号 %d）| flk 命中 %d 部 | TOPIC-001 命中 %d 条"
          % (len(fg_items), len(fg_docs), len(flk_matched), t001.get("hit_total") or 0))
    print("→ %s" % (CRAWL / "legal_corpus_master.json"))
    print("→ %s" % dp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

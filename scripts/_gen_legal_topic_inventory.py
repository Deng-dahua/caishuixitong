# -*- coding: utf-8 -*-
"""从 fgk 全量清单生成**专题法规全量清单 + 效力状态统计**（指令 10.1 / 10.2 / 10.3）。

## 输入 → 输出
输入：`data/legal_crawl/fgk_files.json`（全量 5475 条，含效力等级/文号/发文单位/税费类型/标签）
     `config/legal_topics.json`（专题与关键词）
     `data/legal_crawl/flk_laws.json`（法律/行政法规的官方元数据，可选补强）
输出：
     `data/legal_crawl/<TOPIC>_inventory.json`  专题法规全量清单（分层）
     `data/legal_crawl/<TOPIC>_effect_stats.json` 效力状态统计
     `docs/STEP-EXT-LEGAL-FULL_专题法规清单_<TOPIC>_20261015.md` 人读版汇编

## 口径（**不编造、不遗漏标注**）
- 命中 = 专题**关键词**出现在标题 / 主题标签 / 税费类型 / 文号 任一字段。
- 效力等级直接用 fgk 的 `effect_level`/`channel_name`（**不自行判定**）。
- 命中为空的层级**照实留空**（不补全）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CRAWL = ROOT / "data" / "legal_crawl"

#: 指令 10.2 汇编分层（**数据驱动**：新增一层＝加一行）
LAYERS: List[Dict[str, Any]] = [
    {"key": "law", "title": "一、法律", "levels": ("法律",)},
    {"key": "admin_reg", "title": "二、行政法规", "levels": ("行政法规", "国务院文件")},
    {"key": "dept_rule", "title": "三、部门规章与规范性文件",
     "levels": ("税务部门规章", "税务规范性文件", "财税文件", "其他文件", "工作通知")},
    {"key": "judicial", "title": "四、司法解释", "levels": ("司法解释",)},
    {"key": "joint", "title": "五、联合惩戒", "levels": ("联合发文",)},
]


def _split(v: Any) -> List[str]:
    return [x.strip() for x in str(v or "").replace("，", ",").split(",") if x.strip()]


def load_corpus() -> List[Dict[str, Any]]:
    p = CRAWL / "fgk_files.json"
    if not p.exists():
        print("!! 缺 %s —— 请先跑 scripts/_crawl_fgk_files.py" % p)
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    items = d.get("items") or []
    # 文件类型（司法解释等）来自 flk 的知识不在 fgk 里；此处只用 fgk 自带字段
    for it in items:
        if not it.get("effect_level"):
            it["effect_level"] = it.get("channel_name") or "（未标注）"
    return items


def filter_topic(items: List[Dict[str, Any]], keywords: List[str]) -> List[Dict[str, Any]]:
    """命中 = 关键词出现在 标题 / 主题标签 / 税费类型 / 文号 / 副标题。"""
    out = []
    for it in items:
        blob = " ".join([
            str(it.get("title") or ""), str(it.get("sub_title") or ""),
            str(it.get("labels") or ""), str(it.get("tax_policy") or ""),
            str(it.get("doc_no") or ""),
        ])
        if any(k and k in blob for k in keywords):
            out.append(it)
    return out


def main() -> int:
    topic_id = sys.argv[1] if len(sys.argv) > 1 else "TOPIC-001"
    topics = json.loads((ROOT / "config" / "legal_topics.json").read_text(encoding="utf-8"))
    topic = next((t for t in topics["topics"] if t["id"] == topic_id), None)
    if topic is None:
        print("未登记专题:", topic_id)
        return 2
    corpus = load_corpus()
    if not corpus:
        return 2
    # ★ 清单筛选优先用 `inventory_keywords`（宽），回落检索用 `keywords`（精准）
    #   理由：检索词用于**向数据源提问**（要精准）；在全量库里**圈定专题范围**要用稍宽的词，
    #   否则大幅漏项（实测 TOPIC-001 仅用检索词命中 16 条，笼统含「发票」则 283 条）。
    kws = [k for k in (topic.get("inventory_keywords") or topic.get("keywords") or []) if k]
    kw_kind = "inventory_keywords（清单筛选）" if topic.get("inventory_keywords") else "keywords（检索词）"
    hit = filter_topic(corpus, kws)
    print("专题 %s「%s」%s 共 %d 个 → 全库 %d 条中命中 **%d** 条"
          % (topic_id, topic["name"], kw_kind, len(kws), len(corpus), len(hit)))

    hit.sort(key=lambda x: (x.get("published_at") or "", x.get("title") or ""), reverse=True)
    grouped: Dict[str, List[Dict[str, Any]]] = {l["key"]: [] for l in LAYERS}
    other: List[Dict[str, Any]] = []
    for it in hit:
        lv = it.get("effect_level") or "（未标注）"
        slot = next((l["key"] for l in LAYERS if lv in l["levels"]), None)
        (grouped[slot] if slot else other).append(it)

    from collections import Counter
    eff = Counter((x.get("effect_level") or "（未标注）") for x in hit)
    inv = {
        "topic_id": topic_id, "topic_name": topic["name"],
        "keywords": kws,
        "source": "fgk.chinatax.gov.cn（税费政策法规库，全量列表遍历）",
        "corpus_total": len(corpus), "hit_total": len(hit),
        "layers": [{"key": l["key"], "title": l["title"],
                    "count": len(grouped[l["key"]]),
                    "items": grouped[l["key"]]} for l in LAYERS],
        "other": other,
        "effect_stats": dict(eff.most_common()),
        "_note": "★ 命中=专题关键词命中（标题/主题标签/税费类型/文号）；效力等级**直接用库内字段**，"
                 "不自行判定；空层如实留空。逐条含 URL 可溯源。",
    }
    (CRAWL / ("%s_inventory.json" % topic_id)).write_text(
        json.dumps(inv, ensure_ascii=False, indent=1), encoding="utf-8")
    (CRAWL / ("%s_effect_stats.json" % topic_id)).write_text(
        json.dumps({"topic_id": topic_id, "hit_total": len(hit),
                    "by_effect_level": dict(eff.most_common())},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    # 人读版汇编
    L = ["# 专题法规全量清单 · %s「%s」（2026-10-15）" % (topic_id, topic["name"]), "",
         "> 来源：**税费政策法规库 `fgk.chinatax.gov.cn` 全量列表遍历**（非检索；故**含法律/行政法规**）。",
         "> 全库 %d 条中，按专题关键词命中 **%d 条**。" % (len(corpus), len(hit)),
         "> 检索词：%s" % "、".join(kws), "",
         "## 效力状态统计", "", "| 效力等级 | 数量 |", "|---|---|"]
    for k, v in eff.most_common():
        L.append("| %s | %d |" % (k, v))
    L += ["", "## 分层汇编", ""]
    for l in LAYERS:
        xs = grouped[l["key"]]
        L += ["### %s（%d 条）" % (l["title"], len(xs)), ""]
        if not xs:
            L += ["_（本层命中为 0 —— 如实留空，未补全）_", ""]
            continue
        L += ["| 序号 | 标题 | 文号 | 发文单位 | 发布日期 | URL |", "|---|---|---|---|---|---|"]
        for i, x in enumerate(xs, 1):
            L.append("| %d | %s | %s | %s | %s | [原文](%s) |" % (
                i, (x.get("title") or "")[:60].replace("|", "/"),
                x.get("doc_no") or "—", (x.get("issuer") or "—")[:24],
                x.get("published_at") or "—", x.get("url") or ""))
        L.append("")
    if other:
        L += ["### 其他（效力等级未分层，%d 条）" % len(other), ""]
        for i, x in enumerate(other, 1):
            L.append("%d. %s（%s · %s）" % (i, x.get("title"), x.get("effect_level"),
                                            x.get("published_at") or "—"))
        L.append("")
    L += ["---", "", "**口径声明**：本清单为**采集候选**，未逐条人工核实；"
          "入库仍走 `scripts/_load_legal_texts.py`（人工核实）。效力等级取自库内字段，未自行判定。"]
    dp = ROOT / "docs" / ("STEP-EXT-LEGAL-FULL_专题法规清单_%s_20261015.md" % topic_id.replace("-", ""))
    dp.write_text("\n".join(L), encoding="utf-8")

    print("分层：", {l["title"]: len(grouped[l["key"]]) for l in LAYERS}, "其他", len(other))
    print("→ %s" % (CRAWL / ("%s_inventory.json" % topic_id)))
    print("→ %s" % dp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

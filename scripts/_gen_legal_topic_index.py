# -*- coding: utf-8 -*-
"""生成**专题索引** `config/legal_topic_index.json`（STEP-EXT-LEGAL-FULL-MATCH 步骤 22）。

为什么需要它：专题页要显示"每个专题有多少法规/条款/规则/材料"，若前端每次请求都遍历
7564 条目录 × 20 专题，既慢又重复计算。故**派生**一份索引（结论类 ⇒ 放 `config/`，
不放 `data/`——后者会被清理磁盘带走）。

★ 索引只存**统计 + 条目下标**（指向 `legal_catalog.json` 的 `items` 数组），
  **不复制条目内容** ⇒ 避免同一法规在 20 个专题里各存一份（体积膨胀 + 双份真相）。
  详情由读层 `engine/legal_topics.py` 按下标取原始条目。

★ 归属口径（全部**数据驱动**，不写死专题名）：
  · 法规 → 专题：`legal_topics.inventory_keywords` 命中 `title/doc_no/labels/tax_policy/issuer`
  · 条款 → 专题：`legal_provisions[].topic_tags`（生成器已打标）
  · 规则 → 专题：①批次规则 `_topic_id`；②其余规则经**已确证条款**所属法名反查
  · 材料 → 专题：材料显式引用的法名 ∈ 该专题法规清单

用法：`./.venv/Scripts/python.exe scripts/_gen_legal_topic_index.py`
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config"
OUT = CFG / "legal_topic_index.json"


def _read(name: str) -> Dict[str, Any]:
    p = CFG / name
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception as exc:                                     # noqa: BLE001
        print("[WARN] 读取 %s 失败：%s" % (name, exc))
        return {}


def _norm(s: Any) -> str:
    return "".join(str(s or "").split())


def _law_key(s: Any) -> str:
    """法名归一（去空白 + 去「中华人民共和国」前缀）——与 legal_mapping 同口径。"""
    t = _norm(s)
    return t[7:] if t.startswith("中华人民共和国") else t


#: 文件类型 → 展示分组（**数据驱动**：新增类型只在此加一行）
_KIND_GROUP = {
    "法律": "法规", "行政法规": "法规", "国务院文件": "法规", "税务部门规章": "法规",
    "税务规范性文件": "法规", "财税文件": "法规", "工作通知": "法规", "其他文件": "法规",
    "政策解读": "解读", "解读": "解读", "文字政策解读": "解读",
    "政策问答": "问答", "问答": "问答",
    "案例": "案例", "税案通报": "案例",
}


def _by_group(by_kind: Dict[str, int]) -> Dict[str, int]:
    """按**展示分组**汇总（法规 / 解读 / 问答 / 案例 / 其他）——分组口径唯一处。"""
    out: Dict[str, int] = {}
    for k, v in by_kind.items():
        g = _KIND_GROUP.get(str(k), "其他")
        out[g] = out.get(g, 0) + int(v)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def main() -> int:
    topics_doc = _read("legal_topics.json")
    topics = topics_doc.get("topics") or []
    catalog = (_read("legal_catalog.json").get("items") or [])
    provs = (_read("legal_provisions.json").get("provisions") or [])
    materials = (_read("legal_materials.json").get("materials") or [])
    if not topics or not catalog:
        print("[FATAL] 缺 legal_topics.json 或 legal_catalog.json")
        return 2

    # 规则侧：延迟导入引擎（避免脚本直接跑时 import 失败）
    sys.path.insert(0, str(ROOT))
    from engine import legal_mapping as LM
    from engine import tax_redlines as TR

    rules = TR.all_redlines()

    # ① 法规 → 专题：**核心法登记（core_titles）∪ 关键词命中（inventory_keywords）**
    #   ★ 为什么必须并上 core_titles（实测缺口）：TOPIC-001 的核心依据「刑法/税收征收管理法/
    #     行政处罚法」标题不含"虚开/发票"等词 ⇒ 只靠关键词会**系统性漏掉核心法**。
    #   两者分开记录 `matched_by`（core / keyword），前端可分组"核心法规 / 关联文件"。
    def _main_title(s: Any) -> str:
        t = re.sub(r"[（(][^）)]*[）)]", "", str(s or "")).strip()
        t = t.replace("《", "").replace("》", "")
        return t[7:] if t.startswith("中华人民共和国") else t

    docs_by_topic: Dict[str, List[int]] = {}
    match_by: Dict[str, Dict[int, str]] = {}
    for t in topics:
        kws = [k for k in (t.get("inventory_keywords") or t.get("keywords") or []) if k]
        cores = [c for c in (t.get("core_titles") or []) if c]
        hit: List[int] = []
        mb: Dict[int, str] = {}
        for i, d in enumerate(catalog):
            title_main = _main_title(d.get("title"))
            if cores and any(c in title_main or title_main in c for c in cores):
                hit.append(i)
                mb[i] = "core"
                continue
            hay = " ".join(str(d.get(k) or "") for k in
                           ("title", "doc_no", "labels", "tax_policy", "issuer"))
            if any(k in hay for k in kws):
                hit.append(i)
                mb[i] = "keyword"
        docs_by_topic[t["id"]] = hit
        match_by[t["id"]] = mb

    # ② 条款 → 专题：topic_tags 显式归属（权威）；另按"所属法在专题清单内"补记（标注来源）
    prov_by_topic: Dict[str, List[str]] = {t["id"]: [] for t in topics}
    for p in provs:
        pid = str(p.get("provision_id") or "")
        if not pid:
            continue
        for tag in (p.get("topic_tags") or []):
            if tag in prov_by_topic:
                prov_by_topic[tag].append(pid)
    # 专题清单内的法 → 该法的条款也归入（补记，标注 separate 来源）
    laws_of_topic: Dict[str, Set[str]] = {}
    for t in topics:
        s = set()
        for i in docs_by_topic[t["id"]]:
            s.add(_law_key(catalog[i].get("title")))
        laws_of_topic[t["id"]] = s

    # ③ 规则 → 专题
    rule_by_topic: Dict[str, List[str]] = {t["id"]: [] for t in topics}
    assigned: Set[str] = set()
    for r in rules:                                              # ①批次显式 _topic_id
        tid = str(r.get("_topic_id") or "")
        if tid in rule_by_topic:
            rule_by_topic[tid].append(r["id"])
            assigned.add(r["id"])
    for r in rules:                                              # ②经已确证条款反查
        if r["id"] in assigned:
            continue
        laws = {_law_key(p.get("law")) for p in LM.provisions_of(r["id"])}
        if not laws:
            continue
        # ★ **多归属**：一条规则可同时属多个专题（如 RL-CIT-011 同属企业所得税与税收优惠）。
        #   早前用 `break` 只归第一个命中的专题 ⇒ 专题规则数随专题遍历顺序漂移（实测
        #   TOPIC-002 从 49 掉到 22）—— 那是**顺序依赖的假数字**，必须去掉。
        for t in topics:
            if laws & laws_of_topic[t["id"]]:
                rule_by_topic[t["id"]].append(r["id"])

    # ④ 材料 → 专题：**按法分列**（不做一个笼统的"材料数"）
    #   ★ 为什么改口径（实测）：起初用「材料引用的法名 ⊇/⊆ 专题法规清单标题」包含匹配，
    #     结果 TOPIC-002 报 771 条、TOPIC-004 报 700 条 —— 因为清单里含大量标题带"增值税"
    #     的政策文件，任何书名号含"增值税"的材料都命中 ⇒ **过宽且不可解释**。
    #     现改为：材料归属到**它显式引用的那部法**，专题页按法分列展示
    #     （"发票管理办法 17 条材料"），每个数字都能点开看到是哪几条 —— 可解释、不造假精确。
    law_codes = {str(l.get("code")): str(l.get("name"))
                 for l in (_read("legal_law_codes.json").get("laws") or [])}
    mat_by_law: Dict[str, Dict[str, Any]] = {}
    for m in materials:
        for h in (m.get("matched_refs") or []):
            code = str((h or {}).get("law_code") or "")
            if not code:
                continue
            d = mat_by_law.setdefault(code, {"law_code": code,
                                             "law_name": law_codes.get(code, code),
                                             "count": 0, "kinds": {}})
            d["count"] += 1
            k = str(m.get("kind") or "")
            d["kinds"][k] = d["kinds"].get(k, 0) + 1
    # 法短码 → 该法被材料引用的条数（与专题清单无关，供专题详情按"本专题涉及的法"取用）
    mats_by_law_count = {k: v["count"] for k, v in mat_by_law.items()}

    # ⑤ 组装
    out_topics: List[Dict[str, Any]] = []
    for t in topics:
        tid = t["id"]
        idxs = docs_by_topic[tid]
        by_kind: Dict[str, int] = {}
        with_body = 0
        for i in idxs:
            d = catalog[i]
            k = str(d.get("kind") or "其他")
            by_kind[k] = by_kind.get(k, 0) + 1
            if d.get("has_body_in_library"):
                with_body += 1
        # 本专题**条款**涉及的法 → 这些法被官方材料引用的条数（按法分列，可解释）
        prov_laws = {_law_key(p.get("law"))
                     for p in provs if tid in (p.get("topic_tags") or [])}
        mat_rows: List[Dict[str, Any]] = []
        for _lc, v in mat_by_law.items():
            if _law_key(v["law_name"]) in prov_laws:
                mat_rows.append({"law_code": _lc, "law_name": v["law_name"],
                                 "count": v["count"], "kinds": v["kinds"]})
        mat_rows.sort(key=lambda x: -x["count"])
        core_n = sum(1 for i in idxs if match_by[tid].get(i) == "core")
        out_topics.append({
            "id": tid, "name": t.get("name"), "batch": t.get("batch"),
            "status": t.get("status"), "scope": t.get("scope"),
            "keywords": t.get("keywords") or [],
            "inventory_keywords": t.get("inventory_keywords") or [],
            "core_titles": t.get("core_titles") or [],
            "documents_total": len(idxs),
            "documents_core": core_n,                             # 核心法规条数
            "documents_by_kind": dict(sorted(by_kind.items(), key=lambda kv: -kv[1])),
            "documents_by_group": _by_group(by_kind),              # 法规 vs 解读/问答/案例
            "documents_with_body": with_body,
            "doc_indexes": idxs,
            "doc_core_indexes": [i for i in idxs if match_by[tid].get(i) == "core"],
            "provisions_total": len(set(prov_by_topic[tid])),
            "provision_ids": sorted(set(prov_by_topic[tid])),
            "provision_laws": sorted(prov_laws),
            "rules_total": len(set(rule_by_topic[tid])),
            "rule_ids": sorted(set(rule_by_topic[tid])),
            "materials_by_law": mat_rows,                        # ★ 按法分列
            "materials_total": sum(x["count"] for x in mat_rows),
        })

    doc = {
        "schema": 1,
        "updated": "2026-10-15",
        "authority": ("专题**索引**（派生）。源：config/legal_topics.json（专题定义）、"
                      "config/legal_catalog.json（法规目录）、config/legal_provisions.json"
                      "（条款 topic_tags）、config/legal_mappings.json（规则⇄条款）、"
                      "config/legal_materials.json（材料）"),
        "catalog_total": len(catalog),
        "note": ("★ `doc_indexes` 是 `config/legal_catalog.json::items` 的**下标**，"
                 "本文件**不复制条目内容**（避免同一法规在多专题各存一份、以及双份真相）。"
                 "★ 归属全部数据驱动：法规按 `inventory_keywords` 命中；条款按 `topic_tags`；"
                 "规则按批次 `_topic_id` 或经已确证条款反查；材料按显式引用法名。"),
        "topics": out_topics,
        "totals": {
            "topics": len(out_topics),
            "documents_assigned": sum(len(v) for v in docs_by_topic.values()),
            "rules_assigned": len({r for v in rule_by_topic.values() for r in v}),
            "provisions_tagged": len(prov_by_topic and {p for v in prov_by_topic.values() for p in v}),
        },
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    print("专题索引 → %s" % OUT)
    print("%-11s %-22s %8s %8s %7s %9s" % ("ID", "名称", "法规", "条款", "规则", "材料"))
    for t in out_topics:
        print("%-11s %-22s %8d %8d %7d %9d"
              % (t["id"], t["name"], t["documents_total"], t["provisions_total"],
                 t["rules_total"], t["materials_total"]))
    print()
    print("合计：法规命中 %d 条次（去重 %d）｜规则 %d 条｜条款 %d 条"
          % (doc["totals"]["documents_assigned"],
             len({i for v in docs_by_topic.values() for i in v}),
             doc["totals"]["rules_assigned"], doc["totals"]["provisions_tagged"]))
    # 自检：专题数一致
    bad = [t["id"] for t in out_topics if not t["documents_total"]]
    if bad:
        print("[WARN] 无任何法规命中的专题（关键词待补）：%s" % ", ".join(bad))
    return 0


if __name__ == "__main__":
    sys.exit(main())

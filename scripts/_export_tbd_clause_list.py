# -*- coding: utf-8 -*-
"""只读：从**候选库权威原文**（``config/rulelist_v12.json``）抽取「条件待明确」条目，
按**缺口类型**分档，导出《待业务口径清单》。

为什么以 rulelist_v12.json 为源（而不是报告表格）：
  · 报告 §3 的「条件」列**已截断**（列宽所限），不足以支撑业务判断；
  · ``config/rulelist_v12.json::rules`` 是候选库的**原始登记**（``logic`` 完整、``note`` 写明缺口根因）；
  · ``params`` 段是阈值参数的**集中登记处**（可显示"该参数当前有没有值"）。

本脚本**只做转录与机械分档**，不新增任何口径（禁编造）。

输出：docs/待业务口径清单_条件待明确_20261013.md
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "config", "rulelist_v12.json")
OUT = os.path.join(ROOT, "docs", "待业务口径清单_条件待明确_20261013.md")

SEV_CN = {"high": "高", "medium": "中", "low": "低"}
_RE_DUP = re.compile(r"=\s*[A-Z]{2,6}-\d+")

_BUCKET_MEANING = {
    "A 缺数据源（资料采集）": "候选库标注「无 XX 数据源 / 待资料」⇒ 需**采集端**补资料，非判据问题",
    "B 判据待细化（业务口径）": "候选库标注「判据未定义 / 需先细化」⇒ 需**业务**给可判定命题",
    "C 需建模（现无模型）": "候选库标注「需评分模型（当前不存在）」⇒ 需先建**评分模型**",
    "E 判据可算（缺参数/清单）": "候选库标注「判据其实可算」⇒ **优先可落地**，只差参数/清单/数据",
    "F 企业侧不可算（不适用）": "候选库标注「属 XX 业务 ⇒ 企业侧不可算」⇒ 该规则**不应落地**",
    "R 重复项（应并条）": "候选库标注「= 其他候选（重复）」⇒ 应并入他条，不单独立规则",
    "D 其他（须逐条确认）": "未落入上述各档者，需逐条人工确认",
}


def _base_bucket(note: str) -> str:
    """按 note 原文**机械分档**（不改写原文，只归组）。"""
    n = note or ""
    if "不可算" in n:
        return "F 企业侧不可算（不适用）"
    if ("评分模型" in n) or ("模型" in n and "不存在" in n):
        return "C 需建模（现无模型）"
    if "可算" in n:
        return "E 判据可算（缺参数/清单）"
    if ("重复" in n) or _RE_DUP.search(n):
        return "R 重复项（应并条）"
    if ("细化" in n) or ("定义" in n) or ("无客观判据" in n):
        return "B 判据待细化（业务口径）"
    if ("待资料" in n) or ("数据源" in n) or ("0 命中" in n) or ("全仓 0" in n):
        return "A 缺数据源（资料采集）"
    return "D 其他（须逐条确认）"


def main() -> int:
    d = json.load(open(SRC, encoding="utf-8"))
    params = d.get("params") or {}
    items = [r for r in d["rules"] if str(r.get("status")) == "placeholder"]
    items.sort(key=lambda r: r.get("src", ""))

    # 分档：``note`` 为「同上/同」者 ⇒ **继承前一条**档位（候选库原文即如此书写）
    _last = None
    for r in items:
        _n = str(r.get("note") or "").strip()
        if (not _n) or _n in ("同上", "同", "同前", "同上条"):
            r["_bucket"] = _last or "D 其他（须逐条确认）"
        else:
            r["_bucket"] = _base_bucket(_n)
        _last = r["_bucket"]

    buckets = Counter(r["_bucket"] for r in items)

    def ask(r: dict) -> str:
        logic = str(r.get("logic") or "")
        if "params." in logic:
            key = str(r.get("src"))
            pv = params.get(key)
            if pv:
                return "参数**已登记**：`%s`（**请确认该取值与方向是否采信**）" % json.dumps(
                    pv, ensure_ascii=False)
            return "参数 `params.%s` **未登记取值** ⇒ 请给：①数值与单位 ②方向（超出即风险/偏离即风险）③来源（法定/行业/地区/经验）" % key
        return "**请确认：何种事实成立即触发**（现为存在性表述，未给出可判定的命题）"

    L = []
    L.append("# 待业务口径清单：「条件待明确」条目（%d 条）" % len(items))
    L.append("")
    L.append("> **数据源**：`config/rulelist_v12.json`（候选库原始登记，`status=placeholder`）"
             "——**非**报告表格转录（后者「条件」列已截断）")
    L.append("> **生成脚本**：`scripts/_export_tbd_clause_list.py`（只读、可复现、不新增口径）")
    L.append("")
    L.append("## 一、为什么需要业务口径")
    L.append("")
    L.append("这 %d 条候选规则的**触发条件在候选库原文中即为占位**（`action=specify_first`）。"
             "按项目铁律「**禁编造**」「**缺失≠0**」，系统不得凭推测补全 ⇒ 须先补齐口径方可量化入库。"
             % len(items))
    L.append("")
    L.append("## 二、缺口分档（由 `note` 原文机械归组）")
    L.append("")
    L.append("| 档 | 含义 | 条数 |")
    L.append("|---|---|---|")
    for k in sorted(buckets):
        L.append("| %s | %s | **%d** |" % (k, _BUCKET_MEANING.get(k, ""), buckets[k]))
    L.append("")
    L.append("> ⚠ 分档依据的是候选库 `note` 原文用词，**不是**对口径内容的推断；"
             "`note` 写作「同上／同」者，其档位**继承前一条**（候选库原文即如此书写）。"
             "逐条 `note` 原文见下表末列，可自行复核。")
    L.append("")
    L.append("## 三、逐条清单")
    L.append("")
    for k in sorted(buckets):
        L.append("### %s（%d 条）" % (k, buckets[k]))
        L.append("")
        L.append("| # | 候选 ID | 名称 | 严重度 | 触发条件（完整） | 所需字段 | 建议核查 | 候选库「缺口说明」原文 | 需明确的口径 |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for i, r in enumerate([x for x in items if x["_bucket"] == k], 1):
            L.append("| %d | `%s` | %s | %s | `%s` | %s | %s | %s | %s |"
                     % (i, r.get("src"), r.get("name"), SEV_CN.get(str(r.get("sev")), str(r.get("sev"))),
                        r.get("logic"), "、".join(r.get("inputs") or []),
                        r.get("suggestion") or "", (r.get("note") or "").replace("|", "\\|"), ask(r)))
        L.append("")
    L.append("## 四、回填方式")
    L.append("")
    L.append("· **B 档**：在「需明确的口径」列直接给出可判定的命题/阈值即可（一句亦可）；")
    L.append("· **A 档**：说明可提供哪份资料（或确认「无法取得」⇒ 该规则不落地）；")
    L.append("· **C 档**：需先确认是否建设评分模型（不建 ⇒ 该规则不落地）；")
    L.append("· 口径齐备后，于 `2026.11` 入库时统一登记为正式规则 ID（当前占位 `TBD-<候选id>`）。")

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L) + "\n")
    print("已导出 %d 条 → %s" % (len(items), os.path.relpath(OUT, ROOT)))
    print("分档：", dict(buckets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

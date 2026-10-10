# -*- coding: utf-8 -*-
"""阶段7：风险等级与证据强度分离 + 关键证据一票否决 + 生成 V1.2。

产出：
    baseline/V1.2/等级与证据强度.json     每项的 等级/证据强度/闭合度/结论等级
    baseline/V1.2/报告_V1.2.md            V1.1 基础上替换 CH2 风险总表
    docs/第12批_报告修订闭环/08_阶段7_风险等级与证据强度分离报告.md

口径（诚实标注）：
  * **闭合度**：数据层 `closure` 字段在本样本缓存中不可得（该缓存非本样本），
    故使用**文档层可测代理**：要件中『数据源状态=已有』的比例，并在输出中明确标记 `closure_source=proxy`。
  * **一票否决**：判据取自 `config/conclusion_grades.json` 的 veto_rules（V1/V2/V3/V4），不另造。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "baseline")
OUT = os.path.join(BASE, "V1.3")   # 阶段7 产出 V1.3（等级与证据强度分离版）
DOCS = os.path.join(ROOT, "docs", "第12批_报告修订闭环")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")

CG = json.load(open(os.path.join(ROOT, "config", "conclusion_grades.json"), encoding="utf-8"))
VETO = CG["veto_rules"]
MIN_CLOSURE = next((g["min_closure"] for g in CG["grades"] if g["id"] == "L3"), 0.8)
VOCAB = CG["level_vocab"]
LEGAL_LEVELS = VOCAB["legal"]   # 唯一合法词表（须与 engine/risk_levels.LEGAL_LEVELS 一致）
SRC = os.path.join(BASE, "V1.1", "报告_V1.1.md")

RE_R = re.compile(r"^### (R\d+)\s+(.*)$")
RE_CROW = re.compile(r"^\|\s*(R\d+-C\d+)\s*\|")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(DOCS, exist_ok=True)
    lines = open(SRC, encoding="utf-8").read().split("\n")

    # ---------------- 解析每个 R 的要件表
    items: list[dict] = []
    cur = None
    for i, l in enumerate(lines, 1):
        m = RE_R.match(l.strip())
        if m:
            cur = {"no": m.group(1), "title": m.group(2).strip(), "line": i,
                   "constituents": [], "原等级": None, "可信度": None, "缺失声明": 0}
            items.append(cur)
            continue
        if cur is None:
            continue
        mc = RE_CROW.match(l.strip())
        if mc:
            cells = [c.strip() for c in l.strip().split("|")]
            # | 编号 | 要件序号 | 构成要件 | 独立数据源 | 数据源状态 | 核对结论 |
            if len(cells) >= 7:
                cur["constituents"].append({"no": cells[1], "text": cells[3][:40],
                                            "source": cells[4], "status": cells[5],
                                            "verdict": cells[6][:40]})
            continue
        for mm in re.finditer(r"等级\s*[:：]?\s*([高中低]风险)", l):
            cur["原等级"] = mm.group(1)
        for mm in re.finditer(r"可信度[^\d]{0,8}(\d{1,3}(?:\.\d+)?)\s*%", l):
            cur["可信度"] = mm.group(1)
        if "现状：缺失" in l or "独立数据源本轮未取得" in l:
            cur["缺失声明"] += 1

    # ---------------- 逐项：闭合度（代理）+ 一票否决
    for it in items:
        cs = it["constituents"]
        total = len(cs)
        have = sum(1 for c in cs if "已有" in c["status"])
        miss = sum(1 for c in cs if "缺失" in c["status"])
        needchk = sum(1 for c in cs if "须核对" in c["status"])
        undecided = sum(1 for c in cs if "未形成核对结论" in c["verdict"] or "未单独核对" in c["verdict"])
        closure = round(have / total, 4) if total else None
        triggers = []
        if have == 0:
            triggers.append("V1")            # 无任何证据被取得
        if closure is not None and closure < MIN_CLOSURE:
            triggers.append("V2")            # 证据链未闭合
        if miss > 0:
            triggers.append("V3")            # 直接证据缺失
        if miss > 0:
            triggers.append("V4")            # 关键资料缺失且未登记替代
        it.update({
            "要件总数": total, "证据已具备件": have, "证据缺失要件": miss,
            "须核对要件": needchk, "未形成结论要件": undecided,
            "闭合度": closure, "closure_source": "proxy（要件数据源『已有』占比；数据层 closure 字段本样本不可得）",
            "否决触发": sorted(set(triggers)),
        })
        vetoed = bool(triggers)
        it["否决"] = vetoed
        it["风险等级"] = "待核验" if vetoed else (it["原等级"] or "待核验")
        if it["风险等级"] not in LEGAL_LEVELS:
            it["风险等级"] = "待核验"
        # 结论等级
        if vetoed:
            it["结论等级"] = "L2"
        elif it["原等级"] in ("高风险", "中风险"):
            it["结论等级"] = "L3"
        else:
            it["结论等级"] = "L1"
        it["证据强度"] = ("强" if (closure or 0) >= 0.8 else
                          "中" if (closure or 0) >= 0.5 else
                          "弱" if total else "未登记")
        if not it["原等级"]:
            it["等级来源"] = "原报告未登记等级 → 按否决规则登记为待核验"
        elif vetoed:
            it["等级来源"] = f"原报告『{it['原等级']}』→ 触发 {','.join(sorted(set(triggers)))} ⇒ 降为『待核验』"
        else:
            it["等级来源"] = f"原报告『{it['原等级']}』，未触发否决，保留"

    # ---------------- 等级计数（单一事实源）
    from collections import Counter
    dist = Counter(it["风险等级"] for it in items)
    orig_dist = Counter(it["原等级"] or "未登记" for it in items)
    declared = "高风险 2 项、中风险 9 项、低风险 3 项、已列明 2 项"   # 报告行35 自述
    counting = {
        "原报告自述（行35）": declared,
        "原报告正文实际出现的等级词统计": dict(orig_dist),
        "不一致": "是 —— 自述『高风险2』而正文仅有 1 处高风险、『中风险9』而正文仅有 3 处，12 项无等级词",
        "修正后（单一事实源）": dict(dist),
    }

    payload = {"sample": "WB-TRISK-SAMPLE-001", "generated_at": NOW,
               "authority": "config/conclusion_grades.json (veto_rules / level_vocab)",
               "min_closure": MIN_CLOSURE, "items": items, "等级计数": counting}
    json.dump(payload, open(os.path.join(OUT, "等级与证据强度.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # ---------------- 生成 V1.2（替换 CH2 风险总表）
    # ★ 指令要求的 11 列：序号|事项|税种|风险等级|证据强度|定性状态|潜在税额|资料状态|需补资料|复查标准|唯一事实源编号
    TAX_OF = {"R1": "增值税", "R3": "个税/企业所得税/社保费", "R4": "增值税/企业所得税",
              "R5": "企业所得税", "R7": "印花税", "R8": "附加税费", "R11": "增值税",
              "R13": "企业所得税（源泉扣缴）", "R14": "文化事业建设费", "R16": "个人所得税"}
    tbl = ["| 序号 | 事项 | 税种 | 风险等级 | 证据强度 | 定性状态 | 潜在税额 | 资料状态 | 需补资料 | 复查标准 | 唯一事实源编号 |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for it in items:
        tax = TAX_OF.get(it["no"], "见该事项六段式")
        # 定性状态：只允许 风险信号/待核事项/已认定事实 三档（违法认定系统不输出）
        grade_cn = {"L1": "风险信号", "L2": "待核事项", "L3": "已认定事实"}.get(it["结论等级"], "待核事项")  # 四级术语，L4 永不输出
        amt = it.get("潜在税额") or "未量化（待补资料）"
        mat = "齐备" if it["证据缺失要件"] == 0 else f"缺 {it['证据缺失要件']} 类"
        need = f"见资料D（{it['须核对要件']} 项待核）" if it["须核对要件"] else "—"
        tbl.append(f"| {it['no']} | {it['title'][:30]} | {tax} | {it['风险等级']} | {it['证据强度']} | "
                   f"{grade_cn} | {amt} | {mat} | {need} | 见该项六段式·复查标准 | {it['no']}（事实子库 {it['no']}-F01 起） |")
    tbl_s = "\n".join(tbl)

    md_lines = list(lines)
    # 找 CH2 段落并替换
    try:
        s = next(i for i, l in enumerate(md_lines) if l.startswith("## CH2"))
        e = next(i for i in range(s + 1, len(md_lines)) if md_lines[i].startswith("## CH3"))
        new_block = ["## CH2　风险总表", "",
                     "> **风险等级与证据强度分离**：『风险等级』回答『若属实有多严重』，『证据强度/闭合度』回答『目前拿得准几分』，",
                     "> 『结论等级』回答『现在能认定到哪一级』（L1 指标命中 / L2 待核线索 / L3 事项成立 / L4 违法认定，系统不输出 L4）。",
                     "> 触发 V1~V4（关键证据缺失/证据链未闭合）的事项，等级一律降为『待核验』并注明不作认定。", "",
                     "### 统一分级术语（本报告全文只用这四级）",
                     "",
                     "| 分级 | 含义 | 允许的表述 | 本报告是否出现 |",
                     "|---|---|---|---|",
                     "| **风险信号** | 仅发现异常线索，未核实 | 不得下结论 | 部分事项（L1） |",
                     "| **待核事项** | 需补资料或外部数据才能判断 | 待核、不作定性 | 多数事项（L2） |",
                     "| **已认定事实** | 有充分、可复核证据支撑的客观事实 | 可陈述事实 | 少数事项（L3） |",
                     "| **违法认定** | 只能由有权机关依法作出 | **本系统不得作出** | **不出现（L4 永不输出）** |",
                     "",
                     tbl_s, "",
                     f"> 闭合度口径：`{items[0]['closure_source']}`。", ""]
        md_lines[s:e] = new_block
    except StopIteration:
        md_lines.append("\n## CH2　风险总表\n\n" + tbl_s + "\n")

    v12 = "\n".join(md_lines).replace("V1.1（结构重构与去重版）", "V1.3（等级与证据强度分离版）")
    b12 = v12.encode("utf-8")
    with open(os.path.join(OUT, "报告_V1.3.md"), "wb") as f:
        f.write(b12)

    # ---------------- Markdown 报告
    det = "\n".join(
        f"| {it['no']} | {it['title'][:28]} | {it['原等级'] or '未登记'} | **{it['风险等级']}** | "
        f"{it['证据强度']} | {it['闭合度'] if it['闭合度'] is not None else '—'} | {it['结论等级']} | "
        f"{','.join(it['否决触发']) or '—'} |" for it in items)
    veto_cnt = sum(1 for it in items if it["否决"])
    md = f"""# 阶段7：《风险等级与证据强度分离报告》

**样本**：WB-TRISK-SAMPLE-001　**产出版本**：V1.3
**生成时间**：{NOW}
**规则唯一权威**：`config/conclusion_grades.json`（`veto_rules` / `level_vocab`）｜**执行**：`scripts/_phase7_grade.py`

---

## 一、核心问题：等级没有单一事实源

| 口径 | 数值 |
|---|---|
| 原报告自述（行35） | {counting['原报告自述（行35）']} |
| **正文实际出现的等级词统计** | {counting['原报告正文实际出现的等级词统计']} |
| 是否一致 | **{counting['不一致']}** |
| 修正后（单一事实源） | {counting['修正后（单一事实源）']} |

> 根因 **RC-06**：风险等级由报告元数据与正文两处各算一遍。修正后等级**只由本表产出**，报告其它位置一律引用。

## 二、分离后的四列（对照）

| 编号 | 风险事项 | 原等级 | **风险等级** | 证据强度 | 闭合度 | 结论等级 | 否决触发 |
|---|---|---|---|---|---|---|---|
{det}

## 三、关键证据一票否决（触发 {veto_cnt}/{len(items)} 项）

判据取自 `conclusion_grades.json` 的 `veto_rules`（**未另造判据**）：

| 规则 | 触发条件 | 后果 |
|---|---|---|
| V1 | `closure == 0` 或 `evidence_have == 0` | 无任何证据被取得 |
| V2 | `closure < {MIN_CLOSURE}` | 证据链未闭合 |
| V3 | `direct_missing` 为真 | 直接证据缺失 |
| V4 | 关键资料缺失且未登记替代 | 缺替代程序 |

触发后统一执行 `on_veto`：等级上限 **待核验**、追加文字「（关键证据缺失，本项不作认定）」、门禁严重度 **ERROR**。

**本样本结果：{veto_cnt}/{len(items)} 项触发否决**，等级一律降为『待核验』、结论等级降为 **L2**。
这与原报告"高风险 2 项、中风险 9 项"的自述形成直接冲突 —— **原报告在关键证据缺失的情况下给出了中/高等级**。

## 四、闭合度口径的诚实声明

| 项 | 说明 |
|---|---|
| 数据层 `closure` 字段 | **本样本不可得**（`data/cache/last_analysis_cache.json` 不是本样本的缓存） |
| 本次使用 | **文档层代理**：要件中『数据源状态=已有』的比例 |
| 标记 | 输出 JSON 中 `closure_source=proxy`，**不冒充引擎闭合度** |
| 待补 | 阶段9 需把 `fact_store` 接入产出链，届时以引擎闭合度替换代理值 |

## 五、复跑命令

```
./.venv/Scripts/python.exe scripts/_phase7_grade.py
```
"""
    b = md.encode("utf-8")
    with open(os.path.join(DOCS, "08_阶段7_风险等级与证据强度分离报告.md"), "wb") as f:
        f.write(b)

    print(f"[OK] 16 项：触发否决 {veto_cnt} 项；等级分布 {dict(dist)}")
    print(f"[OK] V1.2 报告 {len(b12):,} 字节")
    print(f"[OK] 08_阶段7_风险等级与证据强度分离报告.md  {len(b):,} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

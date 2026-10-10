# -*- coding: utf-8 -*-
"""阶段4：报告结构重构方案（9 章 + 六段式）——**人工确认点**。

产出：
    baseline/V1.1/结构方案.json        机读版结构（供阶段5 生成时引用）
    docs/第12批_报告修订闭环/05_阶段4_报告结构重构方案.md

本阶段**不改写报告正文**，只出结构方案，等人工确认后再进入阶段5 执行。
"""
from __future__ import annotations

import json
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "baseline")
DOCS = os.path.join(ROOT, "docs", "第12批_报告修订闭环")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")

STRUCT = json.load(open(os.path.join(ROOT, "config", "report_structure.json"), encoding="utf-8"))
RATE = json.load(open(os.path.join(BASE, "阶段1", "重复率.json"), encoding="utf-8"))
ASSIGN = json.load(open(os.path.join(BASE, "阶段3", "编号分配.json"), encoding="utf-8"))


def main() -> int:
    os.makedirs(os.path.join(BASE, "V1.1"), exist_ok=True)
    os.makedirs(DOCS, exist_ok=True)

    ch_tbl = []
    for c in STRUCT["chapters"]:
        pages = f"≤{c['max_pages']} 页" if c.get("max_pages") else "不限"
        secs = "；".join(c["sections"][:4])
        forb = "；".join(c.get("forbid", []))
        ch_tbl.append(
            f"| **{c['no']}** | {c['id']} | {c['title']} | {c['audience']} | {pages} | {c['purpose']} | {secs} | {forb} |")
    ch_s = "\n".join(ch_tbl)

    six = "\n".join(f"| {s['no']} | **{s['cn']}** | {s['rule']} |" for s in STRUCT["six_segment"])
    mp = "\n".join(f"| {m['from']} | → | {m['to']} |" for m in STRUCT["mapping_original_to_new"])

    # 去重后预估（诚实标注为估算，实测在阶段5 后重算）
    o = RATE["整体"]
    fr = RATE["事实重复"]
    est = f"""
### 去重后重复率预估（**估算，非实测**）

| 冗余来源 | 阶段1 实测冗余字数 | 阶段5 处置 | 处置后残留 |
|---|---|---|---|
| 渲染残留（空表行 96 + 空标题 77） | 约 1,900 字 | 全部不渲染 | 0 |
| 套话 ×193（11 类） | 约 6,100 字 | 抽为 S-01~S-11，正文改引用 | 引用串约 200 字 |
| 完全重复（73 组 / 314 处） | 约 11,000 字 | 保留首次，其余改引用 | 引用串约 500 字 |
| 近似重复（33 组 / 133 处） | 约 5,200 字 | 合并为一处 | 引用串约 300 字 |
| 事实超额（{fr['锚点数']} 锚点 / {fr['超额出现次数合计']} 次） | 约 2,100 字 | 事实只在 CH4 出现一次 | 0 |
| **合计** | **{o['冗余字数']:,} 字（{o['重复率']:.2%}）** | — | 约 1,000 字（**≈0.8%**） |

> **口径声明**：上表为按冗余字数占比的**估算**，不是实测。阶段5 执行后必须用
> `scripts/_phase1_diagnose.py` 重跑实测，实测值才是验收依据（阈值：整体≤10%、同章节≤5%、同一事实≤1 次）。
"""

    col = "\n".join(
        f"| {c['cn']} | `{c['authority']}` |" for c in next(
            x for x in STRUCT["chapters"] if x["id"] == "CH2")["columns"])

    md = f"""# 阶段4：《报告结构重构方案》（9 章 + 六段式）

**⚠️ 人工确认点**：本阶段只出结构方案，**未改写任何报告正文**。确认后再进入阶段5 执行去重与改写。

**样本**：WB-TRISK-SAMPLE-001（V1.0 冻结版）
**生成时间**：{NOW}
**结构唯一权威**：`config/report_structure.json`（新增章节/段落只加一行）
**执行**：`scripts/_phase4_structure.py`

---

## 一、为什么要重构（对应根因）

| 根因 | 现状 | 结构上的修复 |
|---|---|---|
| RC-01 四段各自渲染同一事实 | 同一事实最多出现 8 次 | 事实独立成 CH4，各章只引用 F-xxx |
| RC-02 要件正文与表格双写 | 13 项 × 逐字双写 | 要件只在表格呈现一次，正文写结论汇总 |
| RC-03 套话 ×32 | 每个证据项各写一遍 | 抽为 CH8 的 S-01~S-11 |
| RC-07 法条随文重复 | 16 个疑点各引一遍 | 独立成 CH6，正文写「见法规L-xx」 |
| RC-09 无读者分层 | 102 页底稿直给老板 | 新增 CH0 决策摘要 ≤2 页 |
| RC-06 等级与证据强度不分 | 同一套值驱动 | CH2 风险总表分列（见下表） |

## 二、9 章结构

| 章 | 编号 | 标题 | 读者 | 篇幅 | 职责 | 主要小节 | 禁止 |
|---|---|---|---|---|---|---|---|
{ch_s}

## 三、风险总表（CH2）新增字段：等级与证据强度分离

| 列 | 唯一权威 |
|---|---|
{col}

> 原报告用同一套值同时表达「风险有多高」和「证据有多硬」，导致 closure=0 仍给出中/高等级。
> 分离后：**风险等级**回答「若属实有多严重」，**证据强度/闭合度**回答「目前拿得准几分」，**结论等级**回答「现在能认定到哪一级」。

## 四、六段式（CH3 每个风险事项的唯一写法）

| 段 | 名称 | 写作规则 |
|---|---|---|
{six}

> 原报告是「四段式 + 总述/分述双轨」，六段式把「需补资料」与「复查标准」独立成段，
> 并取消「总述/分述」双轨——**同一事实不再有两处完整陈述**。

## 五、原报告 → 新结构的映射（逐条，不丢内容）

| 原位置 | | 新位置 |
|---|---|---|
{mp}

## 六、{est}

## 七、本样本在新结构下的规模预估

| 项 | 原报告 | 新结构（预估） |
|---|---|---|
| 页数 | 102 页 | 对内底稿约 55~65 页 + 对外报告约 8~12 页 |
| 风险事项 | 疑点1~16（编号跳号、末值 18） | R1~R16（连续，max=总数） |
| 事实 | 散落各章，同一事实最多 8 次 | F-001~F-0xx，**每条一次** |
| 资料 | 各疑点重复列出 | D-001~D-{ASSIGN['counts']['D']}（CH5 一次） |
| 法规 | 各疑点重复引用 | L-01~L-{ASSIGN['counts']['L']}（CH6 一次） |
| 声明 | 套话 ×193 | S-01~S-{ASSIGN['counts']['S']}（CH8 一次） |

## 八、需要人工确认的 5 件事

1. **9 章结构**是否采用（特别是 CH0 决策摘要与 CH4 事实库为新增章）。
2. **六段式**是否采用（会把原「总述/分述」双轨与「四段式」改掉）。
3. **事实库 CH4 的呈现粒度**：按阶段3 现算为 {ASSIGN['counts']['F']} 条 TOP 事实（稀有数值锚点），
   是否需要扩充到更细（须先补 `fact_store` 接入产出链，当前 B1 门禁仍为 SKIP）。
4. **对外报告版的脱敏范围**（阶段11 执行）：默认隐去第三方名称、个人姓名、银行账户，保留金额与比例。
5. **是否允许在阶段5 同步生成 V1.1 的 Markdown 中间稿**（便于逐章比对，最终仍导出 DOCX）。

## 九、复跑命令

```
./.venv/Scripts/python.exe scripts/_phase4_structure.py
```
"""
    b = md.encode("utf-8")
    with open(os.path.join(DOCS, "05_阶段4_报告结构重构方案.md"), "wb") as f:
        f.write(b)

    json.dump({"generated_at": NOW, "chapters": [c["id"] for c in STRUCT["chapters"]],
               "six_segment": [s["key"] for s in STRUCT["six_segment"]],
               "status": "待人工确认"},
              open(os.path.join(BASE, "V1.1", "结构方案.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print(f"[OK] 9 章 + 六段式方案已生成，{len(b):,} 字节")
    print(f"[OK] 状态：待人工确认（未改写任何正文）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

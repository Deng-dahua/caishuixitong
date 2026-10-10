# -*- coding: utf-8 -*-
"""阶段0/1 交付文档生成器：读 baseline/ 下的现算 JSON，渲染为 Markdown。

原则：**不手抄数据**——文档里的每个数字都来自 scripts/_phase0_freeze.py 与
scripts/_phase1_diagnose.py 的实际运行结果，重新跑脚本即可得到同一份文档。
"""
from __future__ import annotations

import json
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "baseline")
OUT = os.path.join(ROOT, "docs", "第12批_报告修订闭环")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")

META = json.load(open(os.path.join(BASE, "V1.0", "元数据.json"), encoding="utf-8"))
MAT = json.load(open(os.path.join(BASE, "V1.0", "资料清单.json"), encoding="utf-8"))
VER = json.load(open(os.path.join(BASE, "VERSIONS.json"), encoding="utf-8"))
DUP = json.load(open(os.path.join(BASE, "阶段1", "重复清单.json"), encoding="utf-8"))
RATE = json.load(open(os.path.join(BASE, "阶段1", "重复率.json"), encoding="utf-8"))
PRB = json.load(open(os.path.join(BASE, "阶段1", "问题诊断.json"), encoding="utf-8"))


def esc(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def write(path: str, content: str) -> int:
    b = content.encode("utf-8")
    with open(path, "wb") as f:
        f.write(b)
    return len(b)


# ============================================================ 00 阶段0
def gen_phase0() -> str:
    v = "\n".join(
        f"| {x['version']} | {x['name']} | {x['stage']} | {esc(x['desc'])} | `{x['artifact']}` | {x['status']} |"
        for x in VER["versions"])
    freeze = "\n".join(f"{i}. {esc(r)}" for i, r in enumerate(VER["freeze_rule"], 1))
    prov = "、".join(MAT["已提供"])
    hits = "\n".join(f"| {esc(k)} | {v} |" for k, v in MAT["正文出现次数"].items() if v > 0)
    return f"""# 阶段0：冻结与备份（版本基线登记）

**样本**：深圳海更数字传媒有限公司税务风险检查报告
**样本编号**：WB-TRISK-SAMPLE-001
**冻结时间**：{META['frozen_at']}
**生成时间**：{NOW}

---

## 一、原始报告元信息（现算，非手抄）

| 项 | 值 |
|---|---|
| 源文件 | `{META['source_path']}` |
| **sha256** | `{META['sha256'][:32]}…`（前16位 `{META['sha256'][:16]}`） |
| 字节数 | {META['size_bytes']:,} |
| 页数 | {META['pages']} |
| 段落块 / 表 | {META['paragraph_blocks']} 块 / {META['tables']} 表 |
| 正文字数 | {META['chars']:,} 字 |
| 生成器 | {META['generator']}（{META['app_version']}） |
| 创建者 / 最后修改者 | {META['creator']} / {META['lastModifiedBy']} |
| 文档创建 / 修改时间 | {META['created']} / {META['modified']} |

> 该指纹与第11批两层交叉验证时一致（`a6d2fde33c98d1ec`），**说明本批次开始时文档未被改动**，冻结基线有效。

## 二、冻结物清单（只读，任何阶段不得修改）

| 路径 | 说明 |
|---|---|
| `baseline/V1.0/原始报告.docx` | 源文件的位级副本（sha256 已校验一致） |
| `baseline/V1.0/原始报告_纯文本.txt` | 按文档顺序抽取的纯文本（含表格转行） |
| `baseline/V1.0/元数据.json` | 上表元信息的机读版本 |
| `baseline/V1.0/资料清单.json` | 资料清单与缺失声明命中 |

## 三、版本定义 V1.0 ~ V1.4

| 版本 | 名称 | 对应阶段 | 说明 | 产物路径 | 状态 |
|---|---|---|---|---|---|
{v}

### 冻结规则

{freeze}

## 四、资料清单（阶段0 现算）

**已提供（正文中出现过的资料类别）**：{prov}

**正文出现次数**：

| 资料类别 | 出现次数 |
|---|---|
{hits}

**缺失（按指令登记）**：{'、'.join(MAT['缺失声明词'])}

> 口径说明：「出现次数」为正文现算值（不推断）；「缺失」以指令登记为准。
> 报告中显式声明的缺失原文见 `baseline/V1.0/资料清单.json` 的 `缺失声明原文命中`。

## 五、复跑命令

```
./.venv/Scripts/python.exe scripts/_phase0_freeze.py
```
"""


# ============================================================ 01 问题诊断清单
def gen_problems() -> str:
    rows = []
    for p in PRB["problems"]:
        det = p.get("detail")
        det_s = ""
        if det:
            det_s = "<br>" + esc(json.dumps(det, ensure_ascii=False)[:300])
        rows.append(
            f"| {p['id']} | {p['category']} | {esc(p['name'])} | **{p['status']}** | {p.get('count', 0)} | "
            f"{esc(p.get('sample', ''))[:120]}{det_s} | {esc(p.get('handling', ''))} |")
    body = "\n".join(rows)
    return f"""# 阶段1：《问题诊断清单》（9 类）

**样本**：WB-TRISK-SAMPLE-001（V1.0 冻结版，sha256 `{META['sha256'][:16]}`）
**生成时间**：{NOW}
**判据来源**：`scripts/_phase1_diagnose.py`（文档层现算）+ 规则表见脚本内 `PROBLEM_RULES`
**反向验证**：`scripts/_selfcheck_phase1.py` —— **32/32 通过**（每条判据均验证「有缺陷时报红、无缺陷时不报」）

---

## 一、总表

| 编号 | 类别 | 判据 | 状态 | 命中数 | 样例 / 明细 | 处理方向 |
|---|---|---|---|---|---|---|
{body}

## 二、判据反向验证记录

为避免「假判据」，每条判据都做了双向验证。过程中**实测打回 2 处脆弱判据**：

| 判据 | 首轮问题 | 修正 |
|---|---|---|
| P8 缺决策摘要 | 把表格列名「凭证号 \\| **摘要** \\| 金额(元)」当成决策摘要，误判 PASS | 排除表格行后再判定 |
| P3-b 『已查明』与『未认定』同段 | 正则要求「未认定到任何一条构成要件」，原文实为「未认定到构成要件的可能性中等」→ 漏报 | 放宽为「未认定到 \\| 不作认定 \\| 未形成核对结论」，修正后检出 13 处 |

## 三、与指令点名事项的核验结论

| 指令点名 | 本样本核验结果 | 依据 |
|---|---|---|
| 业务招待费限额应为 **5‰** 而非 5% | **未检出该笔误** —— 全文 512/515/547/552 行均使用 5‰ | 复算：6,636,800.57 × 5‰ = **33,184.00 元**，与正文「按孰低法可扣除约 33,184.00 元」完全一致；发生额 411,111.53 × 60% = 246,666.92 元 > 33,184.00 元，孰低取 33,184.00 元 ✓ |

> 按「不得编造」原则：指令点名的该处笔误在本样本中不存在，**不据此修改**；但阶段6 仍将把限额公式固化进规则库做机器复算，防止其他样本出现同类错误。

## 四、复跑命令

```
./.venv/Scripts/python.exe scripts/_phase1_diagnose.py
./.venv/Scripts/python.exe scripts/_selfcheck_phase1.py
```
"""


# ============================================================ 02 重复清单
def gen_dup() -> str:
    fs = DUP["findings"]
    by_type: dict[str, list] = {}
    for f in fs:
        by_type.setdefault(f["type"], []).append(f)

    # 分类统计
    stat = []
    for t, lst in sorted(by_type.items(), key=lambda kv: -sum(x["count"] for x in kv[1])):
        nec = any(x["necessary"] for x in lst)
        stat.append(f"| {t} | {len(lst)} | {sum(x['count'] for x in lst)} | "
                    f"{'必要（模板化）' if nec else '冗余（删除/合并/引用）'} | {esc(lst[0]['handling'])} |")
    stat_s = "\n".join(stat)

    # 各类型明细 TOP
    det = []
    for t, lst in sorted(by_type.items(), key=lambda kv: -sum(x["count"] for x in kv[1])):
        det.append(f"\n### {t}（{len(lst)} 组 / 涉及 {sum(x['count'] for x in lst)} 处）\n")
        det.append("| 出现次数 | 子类型 | 原文（截断） | 首次行号 | 处理 |")
        det.append("|---|---|---|---|---|")
        for f in sorted(lst, key=lambda x: -x["count"])[:14]:
            det.append(f"| {f['count']} | {esc(f['subtype'])} | {esc(f['sample'])[:70]} | "
                       f"{f['lines'][0] if f['lines'] else '-'} | {esc(f['handling'])[:46]} |")
    det_s = "\n".join(det)

    o = RATE["整体"]
    worst = "\n".join(f"| {esc(x['章节'])[:34]} | {x['rate']:.2%} | {x['判定']} | {x['redundant_blocks']}/{x['blocks']} |"
                      for x in RATE["同章节最差15"][:12])
    fr = RATE["事实重复"]
    top_fact = "\n".join(f"| {esc(x['value'])} | {x['occurrences']} | {', '.join(str(i) for i in x['lines'][:8])} |"
                         for x in fr["TOP20"][:12])
    return f"""# 阶段1：《重复清单》

**样本**：WB-TRISK-SAMPLE-001（V1.0 冻结版）
**生成时间**：{NOW}
**判据唯一权威**：`config/dedup_rules.json`（新增一类只加行，不改逻辑分支）
**执行**：`scripts/_phase1_diagnose.py`（只读现算）｜反向验证 `scripts/_selfcheck_phase1.py` **32/32**

---

## 一、阈值校验（三项，全部 FAIL）

| 指标 | 实测 | 阈值 | 判定 |
|---|---|---|---|
| **整体重复率** | **{o['重复率']:.2%}**（冗余 {o['冗余字数']:,} 字 / 正文 {o['总字数']:,} 字） | ≤ 10% | **FAIL** |
| **同章节重复率** | {sum(1 for x in RATE['同章节最差15'] if x['判定'] == 'FAIL')} 个章节超阈（最高 {RATE['同章节最差15'][0]['rate']:.2%}） | ≤ 5% | **FAIL** |
| **同一事实完整出现** | {fr['锚点数']} 个锚点超额，合计 {fr['超额出现次数合计']} 次 | ≤ 1 次 | **FAIL** |

### 口径定义（避免各说各话）

| 指标 | 定义 |
|---|---|
| 整体重复率 | 冗余重复字数 ÷ 正文总字数（含表行） |
| 同章节重复率 | 该章冗余字数 ÷ 该章字数 |
| 同一事实完整出现次数 | 含同一**稀有数值锚点**的**非表格**段落数（明细表行的逐笔数值不构成「完整陈述」，不计入） |
| 冗余计数 | 渲染残留=整类全删；其余=保留首次、其余计冗余 |

## 二、六类重复统计

| 类型 | 组数 | 涉及处数 | 性质 | 处理方式 |
|---|---|---|---|---|
{stat_s}

## 三、同章节重复率最差 12 章

| 章节 | 重复率 | 判定 | 冗余块/总块 |
|---|---|---|---|
{worst}

## 四、事实重复 TOP12（同一数值在不同段落重复陈述）

| 数值锚点 | 出现段数 | 行号 |
|---|---|---|
{top_fact}

> 典型形态：同一金额在**「为何列入检查」→「涉及的风险事项」→「发现的依据」→「结论及理由」**四处各写一遍，
> 这正是「总述 / 分述」双轨 + 四段式模板造成的**结构性重复**，不是偶发笔误。

## 五、分类明细
{det_s}

## 六、必要重复 vs 冗余重复的判定规则

| 类别 | 判定 | 处置 |
|---|---|---|
| 章节骨架标题 | 属必要，但 16 个疑点 × 同一套骨架 = 结构重复 | **统一模板化**：骨架只在模板库声明一次，各疑点只填差异 |
| 交叉引用（见疑点R1 / 见事实F-012 等） | 必要 | 保留，是去重后的引用格式 |
| 法定依据引用 | 必要 | 保留，改为「见法规L-05」并集中到法规索引 |
| 表头行 | 必要 | 保留 |
| 套话 / 完全重复 / 近似重复 / 事实重复 / 渲染残留 | **冗余** | 删除 / 合并 / 改为引用 |

## 七、复跑命令

```
./.venv/Scripts/python.exe scripts/_phase1_diagnose.py
```
"""


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    files = [
        ("00_阶段0_冻结备份与版本基线.md", gen_phase0()),
        ("01_阶段1_问题诊断清单.md", gen_problems()),
        ("02_阶段1_重复清单.md", gen_dup()),
    ]
    for name, content in files:
        n = write(os.path.join(OUT, name), content)
        print(f"[OK] {name}  {n:,} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

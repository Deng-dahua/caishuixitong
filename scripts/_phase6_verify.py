# -*- coding: utf-8 -*-
"""阶段6：数据与法规校验（机器复算 + 法规版本核验清单）。

产出：
    baseline/V1.2/税务校验.json
    docs/第12批_报告修订闭环/07_阶段6_数据与法规校验报告.md

原则：
  * 每个数字都要能复算；复算不出来就标『未测算』，不填零不顶替。
  * 税率必须有依据；未声明依据的税率不得单独使用。
  * 法规版本只登记**报告自述状态**或标注『待人工核』，不凭空断言现行有效。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "baseline")
OUT = os.path.join(BASE, "V1.2")
DOCS = os.path.join(ROOT, "docs", "第12批_报告修订闭环")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")

LIMITS = json.load(open(os.path.join(ROOT, "config", "tax_limits.json"), encoding="utf-8"))
SRC = os.path.join(BASE, "V1.0", "原始报告_纯文本.txt")

RE_LAW_NAME = re.compile(r"《([^》]{2,60})》")
LAW_HINT = re.compile(r"法$|条例|办法|规定|通知|决定|公告|细则|解释|批复|暂行")
RE_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def D(x) -> Decimal:
    return Decimal(str(x).replace(",", "").replace("元", "").strip())


def q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_table(lines: list[str], header_key: str) -> list[list[str]]:
    """取含 header_key 的表格的数据行。"""
    out = []
    i = 0
    while i < len(lines):
        if header_key in lines[i] and "|" in lines[i]:
            j = i + 1
            while j < len(lines) and lines[j].strip() != "<<TABLE_END>>":
                if "|" in lines[j]:
                    out.append([c.strip() for c in lines[j].split("|")])
                j += 1
            break
        i += 1
    return out


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(DOCS, exist_ok=True)
    lines = open(SRC, encoding="utf-8").read().split("\n")

    # ---------------- 1. 限额表复算
    rows = parse_table(lines, "费用项目")
    checks = []
    for r in rows:
        if len(r) < 7 or not re.match(r"^\d+$", r[0]):
            continue
        item = r[1]
        actual, limit, over = D(r[2]), D(r[3]), D(r[4])
        spec = next((x for x in LIMITS["limits"] if x["name"] == item), None)
        rec = {"项目": item, "账面发生额": str(actual), "报告限额": str(limit),
               "报告超限": str(over), "差异性质": r[5].replace("**", "")[:20], "适用规则": r[6][:60]}
        if spec is None:
            rec["状态"] = "规则未登记"
            checks.append(rec)
            continue
        rec["规则ID"] = spec["id"]
        # 复算限额（基数须显式给出）
        recomputed = None
        basis_note = ""
        if spec["id"] == "CIT-ENT":
            rev = D("6636800.57")   # 报告使用的基数
            a = actual * Decimal(str(spec["ratio_expense"]))
            b = rev * Decimal(str(spec["ratio_revenue"]))
            recomputed = min(a, b)
            basis_note = f"min({actual}×60%={q2(a)}, {rev}×5‰={q2(b)})"
        elif spec["id"] == "CIT-ADV":
            rev = D("6636800.57")
            recomputed = rev * Decimal(str(spec["ratio_revenue"]))
            basis_note = f"{rev}×15%={q2(recomputed)}"
        rec["复算限额"] = str(q2(recomputed)) if recomputed is not None else "未测算"
        rec["复算过程"] = basis_note
        if recomputed is not None:
            rec["限额一致"] = (q2(recomputed) == q2(limit))
            rec["超限一致"] = (q2(actual - q2(recomputed)) == q2(over))
        checks.append(rec)

    # ---------------- 2. 潜在税额口径复算（修正原报告）
    ent = next((c for c in checks if c.get("规则ID") == "CIT-ENT"), None)
    adv = next((c for c in checks if c.get("规则ID") == "CIT-ADV"), None)
    perm = D(ent["报告超限"]) if ent else Decimal(0)
    timing = D(adv["报告超限"]) if adv else Decimal(0)
    std = Decimal(str(LIMITS["rates"]["cit_standard"]["value"]))
    small = Decimal(str(LIMITS["rates"]["cit_small_low_profit"]["value"]))
    impact = {
        "原报告口径": {
            "算式": f"({perm} + {timing}) × 5%",
            "结果": str(q2((perm + timing) * Decimal("0.05"))),
            "问题": [
                "把**永久性差异**（业务招待费，不得结转）与**时间性差异**（广告费，准予结转以后年度）合并计算 —— 时间性差异不产生当期应补税额",
                "税率 5% 未声明依据（小微优惠需先满足并登记适用条件），且报告未登记该企业是否适用",
                "该口径给出的 105,606.89 元既非『当期应补税额』也非『敞口上界』，口径不明",
            ],
        },
        "修正口径_当期敞口（永久性差异×法定税率）": str(q2(perm * std)),
        "修正口径_当期敞口（永久性差异×小微档）": str(q2(perm * small)),
        "修正口径_当期敞口上界（全部差异×法定税率）": str(q2((perm + timing) * std)),
        "递延影响（时间性差异×法定税率，不构成当期敞口）": str(q2(timing * std)),
        "说明": LIMITS["impact_rule"]["note"],
    }

    # ---------------- 3. 法规版本核验清单
    laws: dict[str, dict] = {}
    for i, l in enumerate(lines, 1):
        for m in RE_LAW_NAME.finditer(l):
            nm = m.group(1)
            if not LAW_HINT.search(nm):
                continue
            seg = l.strip()
            rec = laws.setdefault(nm, {"name": nm, "first_line": i, "count": 0,
                                       "自述状态": "", "核验结论": ""})
            rec["count"] += 1
            if "版本未登记" in seg or "须核对现行有效文本" in seg or "引用较早" in seg:
                rec["自述状态"] = "未登记（报告自述须核对）"
            elif "现行有效" in seg:
                rec["自述状态"] = "报告自述现行有效（未经独立核验）"
            else:
                rec["自述状态"] = rec["自述状态"] or "未登记状态"
    for rec in laws.values():
        if "未登记" in rec["自述状态"] or rec["自述状态"] == "未登记状态":
            rec["核验结论"] = "待人工核（须在国家税务总局法规库按适用年度核对现行有效文本）"
        else:
            rec["核验结论"] = "待人工复核（报告自述；本脚本不做版本断言）"

    # ---------------- 4. 基数口径声明检查
    basis = LIMITS["basis_scope"]
    used_main = "主营业务收入" in "\n".join(lines)
    basis_check = {
        "税法基数术语": basis["tax_term"],
        "报告实际使用": "主营业务收入" if used_main else "未确认",
        "严格定义": basis["strict_definition"],
        "状态": "需声明差异影响" if used_main else "待核",
        "说明": basis["risk"],
    }

    payload = {
        "sample": "WB-TRISK-SAMPLE-001", "generated_at": NOW,
        "authority": "config/tax_limits.json",
        "限额复算": checks,
        "潜在税额口径复算": impact,
        "法规版本核验清单": sorted(laws.values(), key=lambda x: x["first_line"]),
        "基数口径检查": basis_check,
    }
    json.dump(payload, open(os.path.join(OUT, "税务校验.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # ---------------- Markdown
    chk_tbl = "\n".join(
        f"| {c['项目']} | {c['账面发生额']} | {c['报告限额']} | {c.get('复算限额','—')} | "
        f"{'✓' if c.get('限额一致') else '✗'} | {c['报告超限']} | {'✓' if c.get('超限一致') else '✗'} | "
        f"{c.get('差异性质','')[:16]} | {c.get('复算过程','')[:44]} |" for c in checks)
    imp_tbl = "\n".join(f"| {k} | {v if isinstance(v,str) else v} |" for k, v in impact.items()
                        if not isinstance(v, list))
    law_tbl = "\n".join(
        f"| L-{k:02d} | {r['name'][:50]} | {r['count']} | {r['自述状态']} | {r['核验结论']} |"
        for k, r in enumerate(sorted(laws.values(), key=lambda x: x["first_line"]), 1))
    prob_tbl = "\n".join(f"- {x}" for x in impact["原报告口径"]["问题"])
    # 先取出含全角括号的键，避免在 f-string 里书写（易漏引号）
    I_STD = impact["修正口径_当期敞口（永久性差异×法定税率）"]
    I_SMALL = impact["修正口径_当期敞口（永久性差异×小微档）"]
    I_DEF = impact["递延影响（时间性差异×法定税率，不构成当期敞口）"]
    I_ORIG = impact["原报告口径"]["结果"]

    md = f"""# 阶段6：《数据与法规校验报告》

**样本**：WB-TRISK-SAMPLE-001（V1.0 冻结版）
**生成时间**：{NOW}
**规则唯一权威**：`config/tax_limits.json`　**执行**：`scripts/_phase6_verify.py`（机器复算）

---

## 一、限额复算（逐个数字重算）

| 项目 | 账面发生额 | 报告限额 | 复算限额 | 限额一致 | 报告超限 | 超限一致 | 差异性质 | 复算过程 |
|---|---|---|---|---|---|---|---|---|
{chk_tbl}

## 二、**头条税额 105,606.89 元的溯源与修正**（本阶段最重要发现）

**溯源**：经复算，105,606.89 = (377,927.53 + 1,734,210.17) × **5%**
= （业务招待费超限 **永久性差异** + 广告费超限 **时间性差异**）× 5%

**问题**：

{prob_tbl}

**修正口径**：

| 口径 | 金额（元） |
|---|---|
{imp_tbl}

> 结论：当期税额敞口应只就**永久性差异**计，**按法定税率 25%** 为 {I_STD} 元；
> 若经核实适用小微优惠，按 5% 为 {I_SMALL} 元。
> 广告费的 {timing} 元超限属**时间性差异**，只形成递延影响（{I_DEF} 元），**不构成当期敞口**。
> 原报告的 {I_ORIG} 元因**混算两类差异 + 未声明税率依据**，不采用。

## 三、限额基数口径检查

| 项 | 值 |
|---|---|
| 税法基数术语 | {basis_check['税法基数术语']} |
| 报告实际使用 | {basis_check['报告实际使用']} |
| 严格定义 | {basis_check['严格定义']} |
| 状态 | **{basis_check['状态']}** |

> {basis_check['说明']}

## 四、法规版本核验清单（{len(laws)} 条）

| 编号 | 法规名称 | 引用次数 | 报告自述状态 | 核验结论 |
|---|---|---|---|---|
{law_tbl}

> **诚实声明**：本脚本**不对法规版本做断言**（不凭空判定某文件现行有效或已废止）。
> 报告中标注『版本未登记，须核对现行有效文本』的，登记为**待人工核**，并给出核验途径
> （国家税务总局法规库按适用年度核对）。阶段7 起，未核版本的法规**不得作为判据**，只作线索。

## 五、复跑命令

```
./.venv/Scripts/python.exe scripts/_phase6_verify.py
```
"""
    b = md.encode("utf-8")
    with open(os.path.join(DOCS, "07_阶段6_数据与法规校验报告.md"), "wb") as f:
        f.write(b)

    ok = sum(1 for c in checks if c.get("限额一致") and c.get("超限一致"))
    print(f"[OK] 限额复算 {len(checks)} 项，一致 {ok} 项")
    print(f"[OK] 原报告口径 {I_ORIG} → 修正：永久性×25% = {I_STD}；永久性×5% = {I_SMALL}；递延 = {I_DEF}")
    print(f"[OK] 法规 {len(laws)} 条（待人工核 {sum(1 for r in laws.values() if '待人工核' in r['核验结论'])} 条）")
    print(f"[OK] 07_阶段6_数据与法规校验报告.md  {len(b):,} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

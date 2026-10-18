# -*- coding: utf-8 -*-
"""GAP-03 补丁：为「无 evidence_chain」的红线补**可执行的**证据链（数据驱动）。

背景
----
`argumentation` 的"反证成立 ⇒ 排除"分支（`rebuttal_ratio >= 0.5`）依赖
`evidence_chain` 里 `role="反证"` 的元素。**没有链 ⇒ 反证元素为空 ⇒ 该分支永不可达**
⇒ 这 36 条红线的任何正当理由都不会改变结论（实测 RL-VAT-018 送 5 项反证仍判"触碰红线"）。

生成规则（**只加数据、不改逻辑**）
--------------------------------
从规则自带的 `required_materials` 派生，不臆造材料名：
  · 直接证据 = 前 3 项
  · 资金证据 = 含「流水/付款/凭证/回单/结算」的第一项（无则跳过）
  · 间接证据 = 第 4~5 项
  · 反证     = 第 6 项起的材料（同族材料既可证成也可证伪，现实就是如此）；
               不足则补一条通用的「企业书面情况说明」
所有 `purpose` 都写清"要证明什么/什么情况下可排除"，不留空壳。

用法：.venv/Scripts/python.exe scripts/_apply_gap03_evidence_chain.py [--check]
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TARGET = ROOT / "engine" / "tax_redlines.py"

_FUND_KEYS = ("流水", "付款", "回单", "结算", "资金")
_GENERIC_REBUTTAL = "企业书面情况说明"

#: 这些规则需要人工撰写证据链（语义特殊，不套模板）
_MANUAL = {"RL-PTY-008"}


def build_chain(rule: dict) -> list:
    mats = [str(m).strip() for m in (rule.get("required_materials") or []) if str(m).strip()]
    name = str(rule.get("name") or "")
    out, used = [], set()

    for m in mats[:3]:
        if m in used:
            continue
        used.add(m)
        out.append({"role": "直接证据", "name": m,
                    "purpose": "核实所涉事实，判断是否满足本项构成要件"})

    fund = next((m for m in mats if m not in used and any(k in m for k in _FUND_KEYS)), "")
    if fund:
        used.add(fund)
        out.append({"role": "资金证据", "name": fund,
                    "purpose": "证明款项实际收付、对手方一致，排除资金回流或挂账"})

    for m in mats:
        if len(out) >= 5:
            break
        if m in used:
            continue
        used.add(m)
        out.append({"role": "间接证据", "name": m,
                    "purpose": "与直接证据相互印证，印证交易链条完整"})

    rebut = [m for m in mats if m not in used][:2]
    for m in rebut:
        out.append({"role": "反证", "name": m,
                    "purpose": "该材料齐备且内容成立时，可排除本项（须人工核验内容）"})
    if len(rebut) < 2:
        out.append({"role": "反证", "name": _GENERIC_REBUTTAL,
                    "purpose": "企业书面说明所述情形成立时，可排除本项（须人工核验内容）"})
    return out


def _blocks(src: str):
    marks = [(m.group(1), m.start()) for m in
             re.finditer(r'"id":\s*"(RL-[A-Z]+-\d+)"', src)]
    return [(rid, pos, marks[i + 1][1] if i + 1 < len(marks) else len(src))
            for i, (rid, pos) in enumerate(marks)]


def main(check_only: bool = False) -> int:
    from engine.tax_redlines import REDLINES

    rules = {r["id"]: r for r in REDLINES}
    todo = [rid for rid, r in rules.items()
            if not r.get("evidence_chain") and rid not in _MANUAL]
    if not todo:
        print("无需补链（全部已有 evidence_chain）")
        return 0

    src = io.open(TARGET, encoding="utf-8").read()
    # ★★ 关键：**必须先收集全部插入点，再按偏移降序一次性应用**。
    #    边插边改会让后续块的 start/end 全部错位 —— 首版正是这样把链插到了
    #    别的规则上（实测 16/17 条错位，靠"首证据 vs required[0]"核对才发现）。
    inserts = []
    for rid, start, end in _blocks(src):
        if rid not in todo:
            continue
        block = src[start:end]
        if '"evidence_chain"' in block:
            continue
        chain = build_chain(rules[rid])
        m = re.search(r'("remedy":\s*"(?:[^"\\]|\\.)*",\s*\n)', block)
        if not m:
            print("✗ %s 找不到 remedy 锚点，跳过" % rid)
            continue
        payload = '        "evidence_chain": %s,\n' % json.dumps(
            chain, ensure_ascii=False, indent=12).replace("\n", "\n        ")
        inserts.append((start + m.end(), payload, rid))

    inserts.sort(key=lambda x: -x[0])          # 从后往前，偏移不失效
    for pos, payload, _rid in inserts:
        src = src[:pos] + payload + src[pos:]

    print("将补 %d 条证据链：%s" % (len(inserts), ",".join(r for _, _, r in inserts)))
    if check_only:
        return 0
    io.open(TARGET, "w", encoding="utf-8").write(src)
    print("已写入", TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--check" in sys.argv))

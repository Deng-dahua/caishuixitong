# -*- coding: utf-8 -*-
"""GAP-03 补丁（第二批）：为缺 `clue_chain` 的红线补线索链。

为什么必须补
----------
`tests/test_redline_methodology.py` 的契约要求每条红线 12 个字段齐全（含 `clue_chain`）。
上一批只补了 `evidence_chain`，导致 36 条规则缺 `clue_chain`（回归暴露）。

`clue_chain` 是"这个疑点怎么从资料里浮现"的逐级可回溯路径，`argumentation` 用它算
`data_completeness`（`has_data` 节点占比）。生成规则（**只加数据、不臆造**）：
  · 步骤 1 = 第①条要件（现象/前提条）
  · 步骤 2..n = 其余要件（取前 3 条）
  · 末步 = "上述情形同时成立 ⇒ 触碰本项红线"
  · `has_data`：该步骤若能在 `required_materials` 里找到对应材料 ⇒ True，否则 False

用法：.venv/Scripts/python.exe scripts/_apply_gap03_clue_chain.py [--check]
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


def build_clue(rule: dict) -> list:
    cs = [str(c) for c in (rule.get("constituents") or []) if str(c).strip()]
    mats = [str(m) for m in (rule.get("required_materials") or []) if str(m).strip()]
    steps = []
    for i, c in enumerate(cs[:3]):
        # 该要件文本里是否出现某个已登记材料的名字（粗略但可核：只用于 has_data 提示）
        has = any(m and (m in c or c[:6] in m) for m in mats) if mats else False
        steps.append({"step": c[:80], "has_data": bool(has)})
    if not steps:
        steps = [{"step": "识别到本项对应的账内信号", "has_data": True}]
    steps.append({"step": "上述情形同时成立 ⇒ 触碰本项红线（是否定性另由证据链决定）",
                  "has_data": False})
    return steps


def _blocks(src: str):
    marks = [(m.group(1), m.start()) for m in
             re.finditer(r'"id":\s*"(RL-[A-Z]+-\d+)"', src)]
    return [(rid, pos, marks[i + 1][1] if i + 1 < len(marks) else len(src))
            for i, (rid, pos) in enumerate(marks)]


def main(check_only: bool = False) -> int:
    from engine.tax_redlines import REDLINES
    rules = {r["id"]: r for r in REDLINES}
    todo = [rid for rid, r in rules.items() if not r.get("clue_chain")]
    if not todo:
        print("无需补线索链")
        return 0

    src = io.open(TARGET, encoding="utf-8").read()
    inserts = []
    for rid, start, end in _blocks(src):
        if rid not in todo:
            continue
        block = src[start:end]
        if '"clue_chain"' in block:
            continue
        payload = '        "clue_chain": %s,\n' % json.dumps(
            build_clue(rules[rid]), ensure_ascii=False, indent=12).replace("\n", "\n        ")
        inserts.append((start, payload, rid))

    inserts.sort(key=lambda x: -x[0])          # 偏移降序，避免错位
    for pos, payload, _rid in inserts:
        src = src[:pos] + payload + src[pos:]

    print("将补 %d 条线索链：%s" % (len(inserts), ",".join(r for _, _, r in inserts)))
    if check_only:
        return 0
    io.open(TARGET, "w", encoding="utf-8").write(src)
    print("已写入", TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--check" in sys.argv))

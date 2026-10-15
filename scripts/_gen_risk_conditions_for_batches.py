# -*- coding: utf-8 -*-
"""为**批次规则**登记触发条件与认定要件（`config/risk_conditions.json`）。

为什么必须登记：闸门 `check_...`（全量产物）要求「已列为疑点的风险指标必须能在配置中
查到认定要件/触发条件」—— 批次规则只在 `tax_redlines.py` 注册、不在本配置登记时，
一旦真跑出疑点即报 ERROR（实测 RL-PAY-009 命中）。

★ 数据来源：批次 JSON 自身（`constituents` / `indicator_constituents` / `signals`），
  **不新造条文**；`is_precondition` 按 `indicator_constituents`（前 N 条为现象/前提条）。
★ 幂等：`risk_code` 已存在则**就地更新**（保持列表顺序不变，避免 diff 噪声）。

用法：`./.venv/Scripts/python.exe scripts/_gen_risk_conditions_for_batches.py`
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config" / "risk_conditions.json"
BATCH_DIR = ROOT / "config" / "rule_batches"


def main() -> int:
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    risks: List[Dict[str, Any]] = cfg.get("risks") or []
    by_code = {str(r.get("risk_code")): r for r in risks if isinstance(r, dict)}

    rules: List[Dict[str, Any]] = []
    for p in sorted(glob.glob(str(BATCH_DIR / "batch_*.json"))):
        rules += json.loads(Path(p).read_text(encoding="utf-8")).get("rules") or []

    added = updated = 0
    for r in rules:
        code = str(r.get("rule_id") or "")
        if not code:
            continue
        cons = [str(c) for c in (r.get("constituents") or [])]
        if not cons:
            print("[WARN] %s 无要件，跳过" % code)
            continue
        pre = {int(i) for i in (r.get("indicator_constituents") or [])}
        sig = [str(s) for s in (r.get("signals") or [])]
        entry = {
            "risk_code": code,
            "name": str(r.get("name") or ""),
            "trigger_conditions": [
                {"id": "T1",
                 "desc": "资料中出现下列任一特征：" + "、".join(sig) if sig
                         else "资料中出现与本题相关的异常特征",
                 "auto": True},
            ],
            "determination_criteria": [
                # ★ `is_precondition` 与红线侧 `indicator_constituents` **同源**：
                #   闸门要求「第 1 条属存在性判据（现象条）⇒ 必须标前提条」，故按 indicator 标注；
                #   同时该现象条的**独立数据源必须本轮可得**（否则产物写「未单独核对」而闸门
                #   要求前提条写「符合情形」）⇒ 由 `_enrich_rule_batches.sources[0]` 追加通用底稿保证。
                {"id": "C%d" % (i + 1), "desc": c, "is_precondition": (i + 1) in pre}
                for i, c in enumerate(cons)
            ],
            "_source": "config/rule_batches（批次规则自动登记；要件文案与红线库一致）",
        }
        if code in by_code:
            old = by_code[code]
            if json.dumps(old, ensure_ascii=False, sort_keys=True) != json.dumps(
                    entry, ensure_ascii=False, sort_keys=True):
                old.clear()
                old.update(entry)
                updated += 1
        else:
            risks.append(entry)
            by_code[code] = entry
            added += 1

    cfg["risks"] = risks
    cfg["updated"] = "2026-10-15"
    CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    print("批次规则 %d 条：新登记 %d、更新 %d；配置总条数 %d → %d"
          % (len(rules), added, updated, len(risks) - added, len(risks)))
    # 自检：每条批次规则都能查到认定要件（★ 需先把仓库根加进 sys.path，
    #      否则脚本直接跑时 `engine` 不可见 —— 实测踩到）
    sys.path.insert(0, str(ROOT))
    from engine.trigger_conditions import determination_criteria_of
    miss = [r["rule_id"] for r in rules
            if not determination_criteria_of(r["rule_id"])]
    print("自检：查不到认定要件的批次规则 %d 条 %s" % (len(miss), miss[:5]))
    return 0 if not miss else 1


if __name__ == "__main__":
    sys.exit(main())

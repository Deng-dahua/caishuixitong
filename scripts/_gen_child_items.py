# -*- coding: utf-8 -*-
"""子项与关联项配置生成器：从**真实全量产物**派生 `config/child_items.json`。

## 为什么从产物派生
"子项清单"在系统里本来就有多处来源：**风险族成员**（`family_members`）、**本项明细表**
（`detail_tables`）、**未被判"符合情形"的构成要件**、**对象级事项**（垫付/代付/往来款…）。
把多处收敛成一份**可手改的配置表**，既满足用户规格的"数据模型字段"，又让
"新增子项自动纳入完整性校验"成立（新增只需加一行）。

## ★ 本版（1.1.0）
- **枚举规则收敛**：规则本体移到**唯一权威** `engine.child_item_completeness.enumerate_children()`，
  本脚本只做"跑一遍 + 落盘"。**门禁 `audit_product()` 调的是同一个函数** ⇒
  "数据里有、配置里没有"必然被机检出来（漏登记 = ERROR），不再靠人工发现。
- **枚举源扩展到绑定发现明细**：`finding_texts()` —— 用户点名的疑点15「个人垫付 116,504.85 元」
  只出现在发现明细里，旧版扫不到 ⇒ 子项根本没进清单。
- **gap 一律写死**（即使状态为"已核对"）：gap 是"没核对时该补什么"的模板，
  留空会让报告端回落到通用套话；规则型缺口（如"须说明对应供应商/笔数/是否已报销冲账"）
  只有枚举时才知道，必须落盘。
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.child_item_completeness import (   # noqa: E402
    _DEFAULT_OPTIONS, analyze_status, enumerate_children, finding_texts, problem_key,
    problem_texts)

_CFG = ROOT / "config" / "child_items.json"


def _existing_options() -> Dict[str, Any]:
    """读旧配置的 `options`（**保留**，不覆盖）—— 用户改过的开关不得被重生成抹掉。"""
    try:
        old = json.loads(_CFG.read_text(encoding="utf-8"))
        o = old.get("options")
        return o if isinstance(o, dict) else {}
    except Exception:                    # 留痕：首次生成时没有旧文件，属正常路径
        return {}


def main() -> int:
    d = json.loads((ROOT / "scripts" / "four_reports" / "company_1_full.json")
                   .read_text(encoding="utf-8", errors="replace"))
    er = d.get("enterprise_readable_report") or d
    risks: List[Dict[str, Any]] = []
    for p in (er.get("confirmed_problems") or []):
        if not isinstance(p, dict):
            continue
        pc = problem_key(p)                           # ← 绑定键（红线 > 规则 > 标题兜底）
        if not pc:
            continue
        blob = problem_texts(p)                       # ← 判据源（与报告端同源）
        enum = enumerate_children(p, extra_texts=finding_texts(d, pc))
        kids: List[Dict[str, Any]] = []
        for c in enum["child_items"]:
            st = analyze_status(c, blob)
            kids.append({"id": c["id"], "desc": c["desc"],
                         "status": st["status"],
                         "conclusion": st["conclusion"] if st["status"] == "已核对" else "",
                         # gap 一律保留（状态回退时立刻有话说；模板缺口不因"当前已核对"而丢失）
                         "gap": st["gap"] or c.get("gap") or "",
                         "_source": c.get("_source")})
        if kids or enum["related_items"]:
            risks.append({"parent_risk_code": pc,
                          "parent_title": str(p.get("title") or "")[:60],
                          "child_items": kids,
                          "related_items": enum["related_items"]})
    out = {
        "schema": 1, "version": "1.1.0", "updated": "2026-10-07",
        "note": ("子项与关联项配置（唯一权威=本文件）。由 scripts/_gen_child_items.py 调 "
                 "engine.child_item_completeness.enumerate_children() 从真实产物派生；"
                 "状态字段初值 = 正文实际分析情况（可复核），人工可逐条修订。"
                 "新增子项只需加一行 ⇒ 自动纳入完整性校验"
                 "（门禁 check_child_item_completeness → audit_product）。"
                 "gap 是「未核对时该补什么」的模板，无论当前状态都保留。"),
        # ★ options：**可配置项**（生成器原样保留旧值，不会被重生成抹掉）
        #   include_criteria：构成要件是否也登记为子项（默认 false，理由见模块 _DEFAULT_OPTIONS）
        "options": {**_DEFAULT_OPTIONS, **_existing_options()},
        "fields": ["parent_risk_code", "parent_title", "child_items", "related_items"],
        "child_fields": ["id", "desc", "status", "conclusion", "gap"],
        "related_fields": ["id", "desc", "analysis_required"],
        "status_vocab": ["已核对", "未核对", "须核对", "资料缺失"],
        "risks": risks,
    }
    p2 = _CFG
    p2.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    nk = sum(len(r["child_items"]) for r in risks)
    nn = sum(1 for r in risks for c in r["child_items"] if c["status"] != "已核对")
    nr = sum(len(r["related_items"]) for r in risks)
    print("已生成 %s：%d 个父疑点；子项 %d 个（其中未核对 %d 个）；关联项 %d 个"
          % (p2.name, len(risks), nk, nn, nr))
    # 按来源分布留痕（"哪些来源贡献了多少子项"必须可见，否则无法判断枚举是否失效）
    by_src: Dict[str, int] = {}
    for r in risks:
        for c in r["child_items"]:
            by_src[str(c.get("_source"))] = by_src.get(str(c.get("_source")), 0) + 1
    print("来源分布：%s" % "｜".join("%s=%d" % (k, v) for k, v in sorted(by_src.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

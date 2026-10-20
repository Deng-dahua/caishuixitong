# -*- coding: utf-8 -*-
"""候选规则**处置执行台账**生成器（2026-10-20，用户三件下一步事项）。

用户 2026-10-20 拍板三件事：
  ① 8 条「应建」开发成检测器（用户原话"数据源都在"）；
  ② 59 条「业务插件」转成「业务触发插件清单」；
  ③ 22 条「重复」更新候选清单状态。

## 本脚本做什么（与 `_gen_rule_adjudications.py` 的分工）
`rule_adjudications.json` 回答"**专业上该怎么办**"（裁定）；本台账回答
"**每一件具体怎么落地**"（执行状态 + 证据）。两者不互相顶替。

## ★ 关键：核实「数据源都在」这个前提（本项目铁律：能力声称必须跑一遍）
用户认为 8 条应建的"数据源都在"。但本项目铁律是**核实能力声称要跑一遍，别信注释**
（声明层偏离实现层是本仓系统性倾向）。逐条实测 `data/accounting.db` 后**发现前提不成立**：
  · CONS-006 称"消费税+增值税申报表均已在库" ⇒ **无消费税申报表**，`vat_declarations` 0 行；
  · IIT-004/018 称"账面应付股利/应付利息" ⇒ **科目表无该科目**，且**无个税申报表**；
  · GEN-007 称"多期申报表" ⇒ 表结构有 `period` 列但 **0 行**；
  · FIN-001/004 称"报表域" ⇒ **无报表表**（数据在产物 JSON，非结构化表）；
  · INV-020 称"发票 remark 列已在库" ⇒ 列**确实存在**（但 0 行）。
⇒ 台账给每条标注 `data_verified`（已核实/部分/不成立）+ `evidence`（实测证据），
  并给出 `action`：可直接开发 / 须先补数据源 / 应改判为别的类别。

## 运行
    python scripts/_gen_rule_dispositions.py     # 写 config/rule_dispositions.json（幂等）
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "config", "rule_dispositions.json")
ADJ = os.path.join(ROOT, "config", "rule_adjudications.json")

#: 8 条「应建」的**实测核实结论**（2026-10-20 逐条跑 data/accounting.db 得出，非推测）
BUILDABLE_VERIFICATION = {
    "CONS-006": {
        "data_verified": "unfounded",
        "evidence": "库中**无消费税申报表**（sqlite_master 无 consum*/excise* 表）；"
                    "vat_declarations 亦无消费税列，且该表 0 行。",
        "action": "须先支持消费税申报表录入/解析（或改判 needs_form / needs_external）",
    },
    "FIN-001": {
        "data_verified": "existing_covered",
        "evidence": "库中**无 balance_sheets/income_statements 表**（报表三要素在产物 JSON 的 "
                    "report 域，非结构化表）；且 engine/extract_validate.py 已有 `cross_check` "
                    "同口径实现（资产负债表不平衡）。",
        "action": "**本候选实为已覆盖** —— 应更新候选清单状态为「已覆盖」，不另建检测器",
    },
    "FIN-004": {
        "data_verified": "partial",
        "evidence": "库中无独立报表表；利润表收入/应收账款变动可从产物 JSON 或科目余额取，"
                    "但无结构化字段可直接联接。",
        "action": "可建**指标类线索**检测（不作违规认定），须先定指标取值口径",
    },
    "FUND-010": {
        "data_verified": "partial",
        "evidence": "库中 accounts 有「预付账款」科目；无独立「科目余额表」表"
                    "（inventory_balances 为存货余额，非全科目）。账龄需从凭证/余额推算。",
        "action": "可建**线索级**检测（挂账≥1年大额预付），须先定账龄推算口径",
    },
    "GEN-007": {
        "data_verified": "partial",
        "evidence": "vat_declarations 有 `period` 列（结构具备），但该表 **0 行** "
                    "⇒ 当前无数据可判；须有申报表数据才能验。",
        "action": "结构就绪、**待数据** —— 可先开发检测器（按所属期序列判应报未报/逾期）",
    },
    "IIT-004": {
        "data_verified": "unfounded",
        "evidence": "库中 accounts **无「应付股利」科目**（`select name from accounts where "
                    "name like '%股利%'` 为空）；**无个税申报表**。",
        "action": "须先补个税申报数据源（或改判 needs_external）",
    },
    "IIT-018": {
        "data_verified": "unfounded",
        "evidence": "库中 accounts **无「应付利息」科目**；**无个税申报表**。"
                    "（与 IIT-004 同链路）",
        "action": "与 IIT-004 合并处置，须先补个税申报数据源",
    },
    "INV-020": {
        "data_verified": "structure_ok",
        "evidence": "sales_invoices / purchase_invoices / bookkeeping_invoices **均有 `remark` 列**"
                    "（实测 PRAGMA table_info 确认），但三表当前 0 行。",
        "action": "**数据源结构成立，可直接开发**检测器（特定票种备注栏必填校验）",
    },
}


def _db_facts() -> dict:
    """跑一遍库，取通用事实（供台账记录证据与可复现）。"""
    facts = {"tables_with_rows": {}, "probe_error": None}
    try:
        from runtime_storage import ACCOUNTING_DB
        con = sqlite3.connect("file:%s?mode=ro" % str(ACCOUNTING_DB).replace("\\", "/"),
                              uri=True)
        try:
            tabs = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            for t in tabs:
                try:
                    n = con.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
                    if n:
                        facts["tables_with_rows"][t] = int(n)
                except sqlite3.Error:
                    continue
        finally:
            con.close()
    except Exception as exc:                                  # noqa: BLE001
        facts["probe_error"] = "%s: %s" % (type(exc).__name__, exc)
    return facts


def main() -> int:
    adj = json.load(open(ADJ, encoding="utf-8"))
    V = adj["verdicts"]

    # ① 8 条应建：裁定 + 实测核实
    buildable = []
    for rid, v in V.items():
        if v.get("verdict") != "buildable":
            continue
        ver = BUILDABLE_VERIFICATION.get(rid, {})
        buildable.append({
            "rule_id": rid,
            "legal": v.get("legal"), "data_claimed": v.get("data"),
            "note": v.get("note"),
            "data_verified": ver.get("data_verified", "unchecked"),
            "evidence": ver.get("evidence", ""),
            "action": ver.get("action", ""),
        })
    buildable.sort(key=lambda x: x["rule_id"])

    # ② 59 条业务插件：转「业务触发插件清单」（按业务域归组）
    #    插件名优先取裁定里显式的 `plugin` 字段；缺失则从 `data` 派生的旧写法兜底
    #    （旧写法如"房地产行业专用"），并**剔除修饰语**（"；…" 之后、前缀"同 X"）使分组干净。
    def _plugin_name(v: dict) -> str:
        n = str(v.get("plugin") or "").strip()
        if not n:
            n = str(v.get("data") or "").strip().split("；")[0].strip()
            if n.startswith("同 ") or not n:
                n = "未归类插件"
            if not n.endswith("插件") and "专用" not in n:
                n = n + "插件"
        return n

    plugins = []
    for rid, v in V.items():
        if v.get("verdict") != "industry_plugin":
            continue
        plugins.append({
            "rule_id": rid,
            "plugin": _plugin_name(v),
            "legal": v.get("legal"),
            "note": v.get("note") or "",
        })
    plugins.sort(key=lambda x: (str(x["plugin"]), x["rule_id"]))

    # 按域归组（便于"企业发生该业务才启用"）
    groups: dict = {}
    for p in plugins:
        groups.setdefault(str(p["plugin"]), []).append(p["rule_id"])

    # ③ 22 条重复：状态（保留对象 + 本条件处置）
    duplicates = []
    for rid, v in V.items():
        if v.get("verdict") != "duplicate":
            continue
        duplicates.append({
            "rule_id": rid,
            "merge_into": v.get("data"),      # 并入/保留对象
            "kept": v.get("note") or "",
            "list_status": "merged_or_retired",   # 候选清单状态：并入或淘汰
        })
    duplicates.sort(key=lambda x: x["rule_id"])

    doc = {
        "schema": 1,
        "generated_by": "scripts/_gen_rule_dispositions.py",
        "generated_at": adj.get("updated", ""),
        "source": "config/rule_adjudications.json（裁定唯一权威）",
        "_note": ("本台账 = 裁定的**执行落地**（每条怎么落地 + 实测证据）。"
                  "★ 8 条应建的『数据源都在』前提已逐条实测核实，"
                  "**部分不成立**（见 data_verified / evidence）。"),
        "buildable": {
            "count": len(buildable),
            "items": buildable,
            "_summary": {
                "可直接开发": [x["rule_id"] for x in buildable
                               if x["data_verified"] in ("structure_ok", "partial")],
                "前提不成立须先补数据源": [x["rule_id"] for x in buildable
                                          if x["data_verified"] == "unfounded"],
                "实为已覆盖": [x["rule_id"] for x in buildable
                               if x["data_verified"] == "existing_covered"],
            },
        },
        "industry_plugins": {
            "count": len(plugins),
            "groups": {k: sorted(v) for k, v in sorted(groups.items())},
            "items": plugins,
            "_usage": ("企业发生该业务/属该行业/属该地域时**才启用**对应插件；"
                       "未发生则从通用库排除（避免对全行业误报）。"),
        },
        "duplicates": {
            "count": len(duplicates),
            "items": duplicates,
            "_usage": "候选清单状态置 merged_or_retired；保留对象见 merge_into。",
        },
        "db_facts": _db_facts(),
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    print("已写 %s" % os.path.relpath(OUT, ROOT))
    print("  应建 %d（可直接开发 %d / 前提不成立 %d / 已覆盖 %d）"
          % (len(buildable),
             len(doc["buildable"]["_summary"]["可直接开发"]),
             len(doc["buildable"]["_summary"]["前提不成立须先补数据源"]),
             len(doc["buildable"]["_summary"]["实为已覆盖"])))
    print("  业务插件 %d（归 %d 个域）" % (len(plugins), len(groups)))
    print("  重复 %d" % len(duplicates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
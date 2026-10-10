# -*- coding: utf-8 -*-
"""改报告文案后的强制检查：`tax_impact` 全量 diff。

项目铁律：`差异/差额/少缴/价税合计/涉及金额` 等是 `tax_impact.extract_amount` 的**语义锚点词**，
改文案会使税额锚定整体漂移。因此**每次改文案后必须**跑本 diff，
**变值项数须为 0**（除非本次就是要改它）。

对比：`scripts/_baseline_before_d2b.json`（改前） vs `scripts/four_reports/company_1_full.json`（改后）。
"""
import io
import json
import os
import sys

BASE = "scripts/_baseline_before_d2c.json"
NOW = "scripts/four_reports/company_1_full.json"


def collect(path):
    d = json.load(io.open(path, "r", encoding="utf-8"))
    out = {}
    for f in (d.get("all_findings") or []):
        if not isinstance(f, dict):
            continue
        key = str(f.get("scene_fact_id") or f.get("fact_id") or f.get("type") or "")
        if not key:
            continue
        ti = f.get("tax_impact")
        if isinstance(ti, dict):
            out[key] = (ti.get("basis"), ti.get("total"), ti.get("available"))
        else:
            out[key] = (None, None, str(ti)[:60] if ti else None)
    return out, d


b, db = collect(BASE)
n, dn = collect(NOW)

changed = []
for k in sorted(set(b) | set(n)):
    if b.get(k) != n.get(k):
        changed.append((k, b.get(k), n.get(k)))

print("改前条目数 =", len(b), "| 改后条目数 =", len(n))
print("tax_impact 变值项数 =", len(changed))
for k, x, y in changed[:20]:
    print("  ·", k[:52])
    print("      改前:", x)
    print("      改后:", y)
if not changed:
    print("  ⇒ 变值 0 项（文案改动未移动任何税额锚点）✓")

# 顺带打印疑点1（RL-VAT-007）的税基，确认仍是 958,396.23
for f in (dn.get("all_findings") or []):
    if isinstance(f, dict) and f.get("redline_id") == "RL-VAT-007":
        ti = f.get("tax_impact")
        if isinstance(ti, dict):
            print("\n疑点1 tax_impact：basis =", ti.get("basis"), "| total =", ti.get("total"))
        break
print("\n综合结论:", str(dn.get("overall_level"))[:50])

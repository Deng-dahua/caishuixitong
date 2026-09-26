import json, sys
sys.path.insert(0, ".")
from engine.enterprise_report import build_enterprise_readable_report

data = json.load(open("scripts/four_reports/company_1_full.json", encoding="utf-8"))
erp = build_enterprise_readable_report(data)

print("=== report_variant ===", erp.get("report_variant"))
print("=== keys present ===", "boss_decision_report" in erp, "working_paper_report" in erp)

# confirmed problems sorted
cp = erp.get("confirmed_problems", [])
print("\n=== confirmed_problems (sorted by level x amount) ===")
for p in cp:
    print(f"  seq={p['seq']:2} | {p['title'][:30]:32} | grade={p['conclusion_grade']}")

# working paper
wp = erp.get("working_paper_report", {})
print("\n=== working_paper_report ===")
print("variant:", wp.get("variant"))
print("all_findings_count:", wp.get("all_findings_count"))
print("by_category count:", len(wp.get("by_category", [])))
for c in wp.get("by_category", []):
    print(f"  {c['category']:18} -> {c['count']} items")
# spot-check one item has raw fields
sample = wp["by_category"][0]["items"][0]
print("\nsample item keys:", list(sample.keys()))
print("sample has evidence_rows:", bool(sample.get("evidence_rows")), "| observed_metrics:", bool(sample.get("observed_metrics")))
# verify 触碰税务红线 relabel
import re
redline_txt = json.dumps(erp.get("confirmed_problems",""), ensure_ascii=False)
print("\n'触碰税务红线' present in confirmed_problems?", "触碰税务红线" in redline_txt)
print("'触发税务风险指标' present?", "触发税务风险指标" in redline_txt)

import json, os

path = "scripts/four_reports/company_1_full.json"
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

print("=== top-level keys ===")
print(list(data.keys()))

erp = data.get("enterprise_readable_report", {}) or {}
print("\n=== enterprise_readable_report keys ===")
print(list(erp.keys()))

findings = data.get("all_findings", []) or []
print("\n=== all_findings count ===", len(findings))

# level distribution
from collections import Counter
lv = Counter(f.get("level") for f in findings if isinstance(f, dict))
print("level distribution:", dict(lv))

grade = Counter(f.get("conclusion_grade") for f in findings if isinstance(f, dict))
print("conclusion_grade distribution:", dict(grade))

# field presence
fields = Counter()
for f in findings:
    if not isinstance(f, dict): continue
    for k in f.keys():
        fields[k]+=1
print("\n=== finding field presence (top 40) ===")
for k,v in fields.most_common(40):
    print(f"  {k}: {v}")

# amount-related fields
print("\n=== amount-related field samples ===")
amt_fields = ["tax_impact","_falsification_penalty","amount","_amount","exposure","penalty","tax_risk_amount","potential_exposure"]
for f in findings[:3]:
    if not isinstance(f, dict): continue
    print("--- finding type:", f.get("type"))
    for af in amt_fields:
        if af in f:
            print(f"  {af} = {repr(f[af])[:120]}")
    print("  observed_metrics keys:", list((f.get("observed_metrics") or {}).keys())[:10])
    print("  evidence_rows count:", len(f.get("evidence_rows") or []))

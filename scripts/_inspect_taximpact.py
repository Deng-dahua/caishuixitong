import json, re
data = json.load(open("scripts/four_reports/company_1_full.json", encoding="utf-8"))
findings = [f for f in (data.get("all_findings") or []) if isinstance(f, dict)]
probs = [f for f in findings if f.get("level") not in ("待核验","信息","低风险")]

print("=== tax_impact samples for confirmed problems ===")
for f in probs:
    ti = f.get("tax_impact")
    print("\nTYPE:", f.get("type"))
    print("  tax_impact:", repr(ti)[:300] if ti else None)

# how many confirmed problems have numeric in tax_impact
num_pat = re.compile(r"[0-9][0-9,]{2,}(?:\.[0-9]+)?")
cnt_num = 0
for f in probs:
    ti = f.get("tax_impact") or ""
    if num_pat.search(ti):
        cnt_num += 1
print("\nconfirmed problems with numeric in tax_impact:", cnt_num, "/", len(probs))

# Check evidence_maturity values
from collections import Counter
em = Counter(f.get("evidence_maturity") for f in findings)
print("evidence_maturity distribution:", dict(em))
em2 = Counter(f.get("_evidence_maturity") for f in findings)
print("_evidence_maturity distribution:", dict(em2))

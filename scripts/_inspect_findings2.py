import json
from collections import Counter

data = json.load(open("scripts/four_reports/company_1_full.json", encoding="utf-8"))
findings = [f for f in (data.get("all_findings") or []) if isinstance(f, dict)]

# Does tax_impact exist anywhere?
print("findings with tax_impact:", sum(1 for f in findings if "tax_impact" in f))
print("findings with _falsification_penalty:", sum(1 for f in findings if "_falsification_penalty" in f))

# redline_summary structure
rs = ((data.get("comprehensive",{}) or {}).get("redline_detection") or {}).get("summary", {})
print("\nredline_summary:", json.dumps(rs, ensure_ascii=False)[:600])

# confirmed problems (non 待核验/信息/低)
probs = [f for f in findings if f.get("level") not in ("待核验","信息","低风险")]
print("\n=== confirmed-problem-level findings:", len(probs))
for f in probs[:8]:
    print("\nTYPE:", f.get("type"), "| level:", f.get("level"), "| grade:", f.get("conclusion_grade"))
    om = f.get("observed_metrics") or {}
    print("  observed_metrics sample:", json.dumps(om, ensure_ascii=False)[:300])
    ev = f.get("evidence_rows") or []
    if ev:
        print("  evidence_rows[0]:", json.dumps(ev[0], ensure_ascii=False)[:300])
    det = f.get("detail") or ""
    print("  detail[:200]:", det[:200])

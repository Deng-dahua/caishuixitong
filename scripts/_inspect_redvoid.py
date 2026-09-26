import json, sys
sys.path.insert(0, ".")
from engine.enterprise_report import _extract_finding_exposure, _is_expo_key
data = json.load(open("scripts/four_reports/company_1_full.json", encoding="utf-8"))
for f in data.get("all_findings", []):
    if not isinstance(f, dict): continue
    if "红冲" in (f.get("type") or "") or "作废" in (f.get("type") or ""):
        print("TYPE:", f.get("type"), "| redline_id:", f.get("redline_id"))
        print("  observed_metrics keys:", list((f.get("observed_metrics") or {}).keys()))
        print("  extract:", _extract_finding_exposure(f))
        print("  detail[:160]:", (f.get("detail") or "")[:160])

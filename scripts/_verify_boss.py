import json, sys
sys.path.insert(0, ".")
from engine.enterprise_report import build_enterprise_readable_report

data = json.load(open("scripts/four_reports/company_1_full.json", encoding="utf-8"))
erp = build_enterprise_readable_report(data)
boss = erp.get("boss_decision_report", {})
print("one_line:", boss.get("one_line_conclusion"))
ro = boss.get("risk_overview", {})
print("total_exposure_max:", ro.get("total_exposure_max"))
print("exposure_note:", ro.get("exposure_note"))
print("\n%-30s %-5s %-5s %-22s %-18s %s" % ("type","lvl","grade","exposure","source","key"))
for r in ro.get("rows", []):
    print("%-28s %-5s %-5s %-22s %-18s %s" % (r['type'][:26], r['level'], r['grade'],
          r['exposure_text'], r['exposure_source'], ""))
# debug: show selected key per finding via re-extract
from engine.enterprise_report import _extract_finding_exposure, _raw_confirmed_findings
print("\n--- debug selected key ---")
for f in _raw_confirmed_findings(data):
    e = _extract_finding_exposure(f)
    print("%-28s -> amount=%-16s key=%-22s src=%s" % (f.get('type','')[:26], str(e['amount']), e['key'], e['source']))

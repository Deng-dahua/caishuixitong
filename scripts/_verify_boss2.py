import json, sys
sys.path.insert(0, ".")
from engine.enterprise_report import build_enterprise_readable_report

data = json.load(open("scripts/four_reports/company_1_full.json", encoding="utf-8"))
erp = build_enterprise_readable_report(data)
boss = erp["boss_decision_report"]
print("one_line:", boss["one_line_conclusion"])
print("exec count:", boss["executive_summary"]["counts"])
print("risk_overview rows:", len(boss["risk_overview"]["rows"]))
print("total_exposure_max:", boss["risk_overview"]["total_exposure_max"])
print("\n%-34s %-5s %-5s %-20s %-12s %s" % ("type","lvl","grade","exposure","src","trig"))
for r in boss["risk_overview"]["rows"]:
    print("%-32s %-5s %-5s %-20s %-12s %s" % (r['type'][:30], r['level'], r['grade'],
          r['exposure_text'], r['exposure_source'], r['triggered_redline']))
print("\nTOP5 count:", len(boss["top5"]))
print("decisions:", [d['item'] for d in boss['decisions_needed']])
# consistency check
print("\nconfirmed_problems (exec) count:", len(erp["confirmed_problems"]))
print("boss confirmed count:", boss["executive_summary"]["counts"]["confirmed"])
print("MATCH:", len(erp["confirmed_problems"]) == boss["executive_summary"]["counts"]["confirmed"])

import json
data = json.load(open("scripts/four_reports/company_1_full.json", encoding="utf-8"))

# domain_summary[25] 资本公积 finding
ds = data.get("domain_summary") or data.get("comprehensive",{}).get("scenario_execution",{}).get("domain_summary")
print("domain_summary type:", type(ds), "len:", len(ds) if isinstance(ds,list) else "n/a")
if isinstance(ds, list):
    d = ds[25]
    print("domain_summary[25] keys:", list(d.keys()))
    print("domain:", d.get("domain"))
    for fnd in d.get("findings",[]):
        print("  FINDING name:", fnd.get("name"), "| type:", fnd.get("type"), "| redline_id:", fnd.get("redline_id"))
        print("   desc:", str(fnd.get("description"))[:200])

# material readiness / file results
def find_key(o, targets, out, depth=0):
    if depth>12: return
    if isinstance(o, dict):
        for k,v in o.items():
            if any(t in k.lower() for t in targets):
                out.append((k, v if not isinstance(v,(dict,list)) else json.dumps(v, ensure_ascii=False)[:200]))
            find_key(v, targets, out, depth+1)
    elif isinstance(o, list):
        for v in o: find_key(v, targets, out, depth+1)
mr=[]
find_key(data, ["material_readiness","file_results","provided_material","material_coverage","materials"], mr)
print("\n--- material-related keys found:", len(mr))
for k,v in mr[:10]:
    print("  ", k, "=", v)

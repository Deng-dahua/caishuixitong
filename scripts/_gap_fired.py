import json
for cid in (1,2,3):
    data = json.load(open(f"scripts/four_reports/company_{cid}_full.json", encoding="utf-8"))
    fired = []
    def walk(o, p=""):
        if isinstance(o, dict):
            if o.get("_gap_obligation") or o.get("_gap_detector"):
                fired.append((o.get("_gap_obligation") or o.get("_gap_detector"), o.get("type"), o.get("redline_id"), p))
            for k,v in o.items(): walk(v, f"{p}/{k}")
        elif isinstance(o, list):
            for i,v in enumerate(o): walk(v, f"{p}[{i}]")
    walk(data)
    print(f"=== company_{cid}: gap-obligation findings fired = {len(fired)}")
    for f in fired:
        print("   ", f[0], "| type:", f[1], "| redline:", f[2])

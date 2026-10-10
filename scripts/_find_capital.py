import json

data = json.load(open("scripts/four_reports/company_1_full.json", encoding="utf-8"))
paths_s = []
paths_g = []

def walk(o, p=""):
    if isinstance(o, dict):
        blob = json.dumps(o, ensure_ascii=False)
        if "实收资本" in blob:
            paths_s.append(p)
        if "资本公积" in blob:
            paths_g.append(p)
        for k, v in o.items():
            walk(v, f"{p}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, f"{p}[{i}]")
    elif isinstance(o, str):
        if "实收资本" in o: paths_s.append(p)
        if "资本公积" in o: paths_g.append(p)

walk(data)
print("实收资本 in", len(paths_s), "nodes; 资本公积 in", len(paths_g), "nodes")
print("\n实收资本 paths (top 12):")
for p in paths_s[:12]: print("  ", p)
print("\n资本公积 paths (top 20):")
for p in paths_g[:20]: print("  ", p)

# Check for trial balance key
def find_keys(o, target, out, depth=0):
    if depth>10: return
    if isinstance(o, dict):
        for k,v in o.items():
            if target in k.lower(): out.append((k, json.dumps(v, ensure_ascii=False)[:120]))
            find_keys(v, target, out, depth+1)
    elif isinstance(o, list):
        for v in o: find_keys(v, target, out, depth+1)
tb=[]
find_keys(data, "trial_balance", tb)
tb2=[]
find_keys(data, "balances", tb2)
print("\ntrial_balance keys:", len(tb), [x[0] for x in tb[:5]])
print("balances keys:", len(tb2), [x[0] for x in tb2[:8]])

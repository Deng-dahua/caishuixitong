import json

def find_fired(redline_id, path):
    data = json.load(open(path, encoding="utf-8"))
    fired = []
    def walk(o, p=""):
        if isinstance(o, dict):
            rid = o.get("redline_id")
            if rid == redline_id:
                fired.append(p)
            for k, v in o.items():
                walk(v, f"{p}/{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{p}[{i}]")
    walk(data)
    return data, fired

for cid in (1,2,3):
    data, fired = find_fired("RL-OTH-007", f"scripts/four_reports/company_{cid}_full.json")
    print(f"=== company_{cid}: fired findings at redline_id=RL-OTH-007 -> {len(fired)}")
    for fp in fired[:5]:
        print("   ", fp)

# Now inspect the gap detector output / _gap_data balances for company_1
print("\n--- company_1: search gap obligations findings ---")
data = json.load(open("scripts/four_reports/company_1_full.json", encoding="utf-8"))
def collect(o, p="", acc=None):
    if acc is None: acc=[]
    if isinstance(o, dict):
        # gap detector findings often have source/method
        if "资金账簿" in json.dumps(o, ensure_ascii=False) or "营业账簿" in json.dumps(o, ensure_ascii=False):
            acc.append((p, o.get("name") or o.get("suspect") or o.get("type")))
        for k,v in o.items():
            collect(v, f"{p}/{k}", acc)
    elif isinstance(o, list):
        for i,v in enumerate(o):
            collect(v, f"{p}[{i}]", acc)
    return acc
hits = collect(data)
print("资金账簿/营业账簿 mentions in report tree:", len(hits))
for h in hits[:8]:
    print("   ", h[0], "|", str(h[1])[:60])

import json
# _fresh_result.json is Sep 29 raw pipeline result (same C1 data)
data = json.load(open("scripts/four_reports/_fresh_result.json", encoding="utf-8"))
print("top keys:", list(data.keys())[:30] if isinstance(data,dict) else type(data))

def find_key(o, target, out, depth=0, path=""):
    if depth>14: return
    if isinstance(o, dict):
        for k,v in o.items():
            if target in k.lower():
                out.append((path+"/"+k, v if not isinstance(v,(dict,list)) else f"<{type(v).__name__} len={len(v)}>"))
            find_key(v, target, out, depth+1, path+"/"+k)
    elif isinstance(o, list):
        for i,v in enumerate(o):
            find_key(v, target, out, depth+1, f"{path}[{i}]")

tb=[]
find_key(data, "trial_balance", tb)
print("\ntrial_balance keys in _fresh_result:", len(tb))
for p,v in tb[:5]:
    print("  ", p, "=", v)

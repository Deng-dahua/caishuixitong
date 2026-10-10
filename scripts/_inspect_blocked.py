import json
data = json.load(open("scripts/four_reports/company_1_full.json", encoding="utf-8"))

# locate analysis_coverage
ac = data.get("analysis_coverage")
if ac is None:
    # search
    def find(obj, key, out, depth=0):
        if depth > 12: return
        if isinstance(obj, dict):
            if key in obj: out.append(obj[key])
            for v in obj.values(): find(v, key, out, depth+1)
        elif isinstance(obj, list):
            for v in obj: find(v, key, out, depth+1)
    out=[]
    find(data, "analysis_coverage", out)
    print("analysis_coverage found:", len(out))
    ac = out[0] if out else None

if ac:
    bi = ac.get("blocked_items")
    print("blocked_items type:", type(bi), "len:", len(bi) if isinstance(bi, list) else "n/a")
    if isinstance(bi, list) and bi:
        print("first blocked item keys:", list(bi[0].keys()))
        print("sample blocked item:", json.dumps(bi[0], ensure_ascii=False)[:300])
        ids = [b.get("id") or b.get("redline_id") for b in bi]
        print("have RL-OTH-007 in blocked ids:", "RL-OTH-007" in ids)
        # how many RL-* ids total
        rl_ids = [i for i in ids if isinstance(i,str) and i.startswith("RL-")]
        print("total RL ids in blocked_items:", len(rl_ids))
        print("sample RL ids:", rl_ids[:10])

import json, sys

for cid in (1, 2, 3):
    path = f"scripts/four_reports/company_{cid}_full.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    hits = []

    def walk(obj, path=""):
        if isinstance(obj, dict):
            rid = obj.get("redline_id")
            if rid == "RL-OTH-007":
                # classify
                kind = "unknown"
                if "blocked_items" in path:
                    kind = "blocked_items"
                elif "findings" in path or "scenario_execution" in path:
                    kind = "FINDING"
                hits.append((kind, path, obj.get("level") or obj.get("suspect") or obj.get("name")))
            for k, v in obj.items():
                walk(v, f"{path}/{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")

    walk(data)
    findings = [h for h in hits if h[0] == "FINDING"]
    blocked = [h for h in hits if h[0] == "blocked_items"]
    print(f"=== company_{cid}: RL-OTH-007 occurrences={len(hits)} findings={len(findings)} blocked_items_entries={len(blocked)}")
    for h in findings:
        print("   FINDING:", h[1], "|", str(h[2])[:80])

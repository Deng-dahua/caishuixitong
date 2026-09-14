import json, os, copy, glob, sys
sys.path.insert(0, r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong")
from engine.verified_rule_engine import _scan_bank_balance_rollforward

TR = r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong\data\uploads\transfer"
TARGET = "03005624788"
spec = {"id": "VR009", "name": "银行流水余额滚动关系不一致", "required_sources": []}

def run(rows):
    return _scan_bank_balance_rollforward({"bank_txs": rows}, spec)

# (1) REAL: 51 rows for 03005624788 across 25 duplicate-loaded files (was 375 false positives)
real_rows = []
for p in sorted(glob.glob(os.path.join(TR, "*.json"))):
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    for r in (d.get("rows", []) if isinstance(d, dict) else []):
        if str(r.get("account") or r.get("account_no") or "") == TARGET:
            real_rows.append(r)
print(f"[1] REAL 03005624788 rows={len(real_rows)} -> findings={len(run(real_rows))}  (expect 0)")

# (2) COMPLETE correct statement (1_7.json 41 rows, balance continuous)
stmt = json.load(open(os.path.join(TR, "1_7.json"), encoding="utf-8"))["rows"]
print(f"[2] complete stmt 41 rows (continuous) -> findings={len(run(stmt))}  (expect 0)")

# (3) COMPLETE stmt where every row carries holding account, balance correct -> 0
good = copy.deepcopy(stmt)
for r in good:
    r["account"] = TARGET
print(f"[3] complete stmt all-account={TARGET} correct -> findings={len(run(good))}  (expect 0)")

# (4) [3] with ONE real balance corruption (row20 +999) -> must detect 1
bad = copy.deepcopy(good)
bad[20]["balance"] = str(float(str(bad[20]["balance"]).replace(",","")) + 999.0)
r4 = run(bad)
print(f"[4] complete stmt with 1 corruption -> findings={len(r4)}  (expect 1)")
if r4:
    print("    keys:", list(r4[0].keys()))

# (5) 3 duplicate copies of [3] -> 0 (dedup removes copies)
print(f"[5] 3 duplicate correct copies -> findings={len(run(good*3))}  (expect 0)")

# (6) 3 duplicate copies of [4] -> 1 (dedup -> 1 copy with break)
r6 = run(bad*3)
print(f"[6] 3 duplicate copies with break -> findings={len(r6)}  (expect 1)")

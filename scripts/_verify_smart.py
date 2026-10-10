import sys, os, json, asyncio
sys.path.insert(0, ".")
os.environ.setdefault("APP_COOKIE_SECURE", "0")
import main
from shared_state import _last_analysis_cache

p = main.LAST_ANALYSIS_CACHE
with open(p, encoding="utf-8") as f:
    disk = json.load(f)
for cid, v in disk.items():
    _last_analysis_cache[int(cid)] = v
print("[cache]", list(_last_analysis_cache.keys()))

r = asyncio.run(main.get_report_intelligence(company_id=1))
print("[ok]", r.get("ok"))
print("[keys]", sorted(list(r.keys())))
tb = r.get("tax_burden") or []
print("[tax_burden 项数]", len(tb))
rev = (r.get("review") or r.get("risk_narrative") or "")
print("[narrative]", str(rev)[:180])

# -*- coding: utf-8 -*-
"""调试：company_1 上 VR005 是否触发、其发现是否带 redline_id/constituent_hits，
以及 RL-PAY-001 疑点的 supporting_findings 与 match_mode。"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import main
from database import SessionLocal

CID = 1
db = SessionLocal()
try:
    res = main._execute_tax_risk_analysis(CID, db)
finally:
    db.close()

rep = res.get("report") or {}
susps = (rep.get("comprehensive") or {}).get("redline_detection") or {}
susps = susps.get("suspicions") or []

print("=== 所有 suspicions 的 redline_id / match_mode / 是否带 constituent_hits ===")
for s in susps:
    if not isinstance(s, dict):
        continue
    rid = s.get("redline_id")
    arg = s.get("argumentation") or {}
    ch = arg.get("constituent_hits") or s.get("constituent_hits") or []
    print(f"  {rid}: mode={s.get('match_mode')} hits={len(ch) if isinstance(ch,list) else 'NA'}")

print("\n=== RL-PAY-001 疑点详情 ===")
for s in susps:
    if isinstance(s, dict) and s.get("redline_id") == "RL-PAY-001":
        print(json.dumps(s, ensure_ascii=False, indent=2)[:2500])

print("\n=== 搜索所有 finding 中 redline_id=RL-PAY-001 的（来自 all_findings）===")
af = rep.get("all_findings") or []
if isinstance(af, dict):
    af = af.get("findings") or []
for f in af:
    if isinstance(f, dict) and f.get("redline_id") == "RL-PAY-001":
        print("  found finding:", json.dumps({k: f.get(k) for k in ("type","domain","redline_id","constituent_hits","detail")}, ensure_ascii=False)[:500])
print("(若上方无任何输出，说明 VR005 本轮未产出 redline_id=RL-PAY-001 的发现)")

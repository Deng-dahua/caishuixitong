# -*- coding: utf-8 -*-
"""只读取证：对当前一键分析缓存里的报告跑四门禁，打印逐门状态与 ERROR 明细。

用法： ./venv/Scripts/python.exe scripts/_gate_status.py [缓存路径]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import quality_gates as qg          # noqa: E402

CACHE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "cache" / "last_analysis_cache.json"
raw = json.loads(CACHE.read_text(encoding="utf-8"))
ent = raw["1"]
rep = ent["report"]["report"]
code = (ent.get("company") or {}).get("code") or (rep.get("identity") or {}).get("taxpayer_id") or ""
period = str((rep.get("identity") or {}).get("period") or "")

from engine.output_variants import report_text_from   # noqa: E402
res = qg.run_all_gates(rep, company_code=code, period=period,
                       render_text=report_text_from(rep))
print("all_passed=%s formal_output_allowed=%s" % (res.get("all_passed"),
                                                  res.get("formal_output_allowed")))
for g in (res.get("gates") or []):
    errs = [f for f in (g.get("findings") or []) if f.get("severity") == "ERROR"]
    warns = [f for f in (g.get("findings") or []) if f.get("severity") != "ERROR"]
    print("\n== %s %s [%s] ERROR=%d WARN/INFO=%d" % (
        g.get("gate"), g.get("cn"), g.get("status"), len(errs), len(warns)))
    for f in errs[:12]:
        print("   E %s %s | %s" % (f.get("check_id"), f.get("layer"), str(f.get("message"))[:130]))
    for f in warns[:6]:
        print("   - %s %s" % (f.get("check_id"), str(f.get("message"))[:110]))
    for s in (g.get("skips") or [])[:6]:
        print("   SKIP %s" % str(s)[:130])

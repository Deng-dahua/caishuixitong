# -*- coding: utf-8 -*-
"""在临时账套上跑一次真实分析，把完整结果 JSON 落到 four_reports/_fresh_result.json，
供离线渲染脚本 _render_report_html.py 验证「全部风险事项台账」章节。
"""
import os, sys, shutil, json

sys.path.insert(0, os.getcwd())
os.chdir(os.getcwd())

src = open("scripts/_scratch_measure.py", encoding="utf-8").read().replace(
    "if __name__", "if False and __name__")
g = {"__name__": "__notmain__",
     "__file__": os.path.abspath("scripts/_scratch_measure.py")}
exec(compile(src, "scripts/_scratch_measure.py", "exec"), g)
g["compose"]()
res = g["run_and_measure"]()

def _sanitize(obj, stack, depth=0):
    if depth > 80:
        return "<<maxdepth>>"
    oid = id(obj)
    if oid in stack:
        return "<<circular>>"
    if isinstance(obj, dict):
        stack.add(oid)
        try:
            return {str(k): _sanitize(v, stack, depth + 1) for k, v in obj.items()}
        finally:
            stack.discard(oid)
    if isinstance(obj, (list, tuple)):
        stack.add(oid)
        try:
            return [_sanitize(v, stack, depth + 1) for v in obj]
        finally:
            stack.discard(oid)
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


out = "scripts/four_reports/_fresh_result.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump({"report": _sanitize(res.get("report") or {}, set())}, f, ensure_ascii=False)
print("dumped:", out, os.path.getsize(out), "bytes")

rep = (res or {}).get("report") or {}
led = (rep.get("enterprise_readable_report") or {}).get("resolution_ledger") or {}
rows = led.get("rows") or []
print("resolution_ledger.total =", led.get("total"), "| rows =", len(rows),
      "| evidence_tiers =", led.get("evidence_tiers"))

shutil.rmtree(g["SCRATCH_DIR"], ignore_errors=True)

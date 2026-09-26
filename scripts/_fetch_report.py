# -*- coding: utf-8 -*-
"""取回 company_1 的分析结果并 dump 结构，供生成可读报告。"""
import json, time, os, sys, urllib.request, urllib.error, http.cookiejar
from collections import Counter

B = "http://127.0.0.1:8001"
CJ = http.cookiejar.CookieJar()
OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJ))
CS = ""


def req(m, p, b=None, t=300):
    r = urllib.request.Request(B + p, data=json.dumps(b).encode() if b is not None else None, method=m)
    r.add_header("Content-Type", "application/json")
    r.add_header("User-Agent", "wb/1.0")
    if CS:
        r.add_header("X-CSRF-Token", CS)
    try:
        with OP.open(r, timeout=t) as x:
            return x.status, json.loads(x.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:400]


st, js = req("POST", "/api/auth/login", {"username": "admin", "password": "Admin@2024caishui"})
CS = next((c.value for c in CJ if c.name == "csrf_token"), "")
print("登录 ok=", js.get("ok"))
st, js = req("POST", "/api/tax-risk-docs/analyze-start?company_id=1", {})
tid = js.get("task_id")
print("task =", tid)
for _ in range(240):
    st, s = req("GET", "/api/tax-risk-docs/analyze-status/" + tid)
    if s.get("status") in ("done", "error"):
        print("结束:", s.get("status"), s.get("progress"))
        break
    time.sleep(2)

st, raw = req("GET", "/api/tax-risk-docs/analyze-result/" + tid)
rep = raw.get("report") or {}
os.makedirs("scripts/four_reports", exist_ok=True)
out = "scripts/four_reports/company_1_api_result.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(raw, f, ensure_ascii=False, indent=1, default=str)
print("已写", out, os.path.getsize(out), "bytes")

print("\n===== report 顶层（可读内容探查）=====")
for k in ("overall_level", "total_risks", "high_risk", "mid_risk", "low_risk", "files_count",
          "hallucination_count", "verified_count", "pending_count"):
    print("  %-20s = %s" % (k, json.dumps(rep.get(k), ensure_ascii=False)[:120]))

te = rep.get("target_entity") or {}
print("  target_entity keys =", list(te.keys())[:16])
print("  target_entity =", json.dumps(te, ensure_ascii=False)[:300])

print("\n  summary_text len =", len(str(rep.get("summary_text") or "")))
print("  summary_text[:400] =", str(rep.get("summary_text") or "")[:400])

err = rep.get("enterprise_readable_report") or {}
print("\n  enterprise_readable_report 章节:", list(err.keys()))
for k, v in list(err.items())[:12]:
    if isinstance(v, dict):
        print("    %-32s title=%s avail=%s" % (k, str(v.get("title"))[:40], v.get("available")))

rc = rep.get("_report_chapters")
print("\n  _report_chapters 类型=", type(rc).__name__, "长度=", len(rc) if hasattr(rc, "__len__") else "-")
if isinstance(rc, list):
    for c in rc[:10]:
        print("    ", json.dumps(c, ensure_ascii=False)[:150])

ds = rep.get("domain_summary") or []
print("\n  domain_summary 域数 =", len(ds))
for d in ds[:8]:
    print("    %-22s findings=%d" % (str(d.get("domain"))[:22], len(d.get("findings") or [])))

af = rep.get("all_findings") or []
print("\n  all_findings =", len(af), " level分布 =", dict(Counter(f.get("level") or "?" for f in af)))
for f in af[:5]:
    print("    [%s] %s" % (f.get("level"), str(f.get("type"))[:44]))

# -*- coding: utf-8 -*-
"""端到端：跑一键分析并 dump 真实结果结构，重点核对 PDF 解析。"""
import json, time, urllib.request, urllib.error, http.cookiejar
from collections import Counter

BASE = "http://127.0.0.1:8001"
CJ = http.cookiejar.CookieJar()
OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJ))
CSRF = ""


def req(method, path, body=None, timeout=180):
    r = urllib.request.Request(BASE + path,
                               data=json.dumps(body).encode() if body is not None else None,
                               method=method)
    r.add_header("Content-Type", "application/json")
    r.add_header("User-Agent", "wb-e2e/1.0")
    if CSRF:
        r.add_header("X-CSRF-Token", CSRF)
    try:
        with OP.open(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500]


st, js = req("POST", "/api/auth/login", {"username": "admin", "password": "Admin@2024caishui"})
CSRF = next((c.value for c in CJ if c.name == "csrf_token"), "")
print("① 登录 ok=%s csrf=%s" % (js.get("ok"), bool(CSRF)))

st, js = req("POST", "/api/tax-risk-docs/analyze-start?company_id=1", {})
tid = js["task_id"]
print("② 任务已启动:", tid)
for i in range(200):
    st, js = req("GET", "/api/tax-risk-docs/analyze-status/" + tid)
    if js.get("status") in ("done", "error"):
        print("   结束: %s progress=%s" % (js.get("status"), js.get("progress")))
        break
    time.sleep(2)

st, raw = req("GET", "/api/tax-risk-docs/analyze-result/" + tid)
print("\n③ 结果顶层键:", list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__)
if not (isinstance(raw, dict) and raw.get("ok")):
    print("   原始:", json.dumps(raw, ensure_ascii=False)[:600]); raise SystemExit(1)

# 汇报主体
body = raw.get("result") if isinstance(raw.get("result"), dict) else raw
print("   汇报主体键:", list(body.keys())[:40])

for k in ("overall_level", "total_risks", "high_risk", "mid_risk", "low_risk", "files_count", "stats"):
    if k in body:
        print("   %-14s = %s" % (k, json.dumps(body.get(k), ensure_ascii=False)[:150]))

fr = body.get("file_results") or []
print("\n④ file_results 条数 =", len(fr))
print("   类型分布 =", dict(Counter((x.get("type") or "?") for x in fr)))
print("\n   ★ PDF 文件解析明细：")
for x in fr:
    fn = str(x.get("file", ""))
    if fn.lower().endswith(".pdf"):
        print("     - %s" % fn)
        print("       type = %s" % x.get("type"))
        for a in (x.get("actions") or [])[:3]:
            print("       · %s" % str(a)[:110])
print("\n   stats =", json.dumps(body.get("stats"), ensure_ascii=False)[:300])

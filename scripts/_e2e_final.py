# -*- coding: utf-8 -*-
"""最终确认：当前运行中的服务，企业1 一键分析结果摘要。"""
import json, time, urllib.request, urllib.error, http.cookiejar
from collections import Counter

BASE = "http://127.0.0.1:8001"
CJ = http.cookiejar.CookieJar()
OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJ))
CSRF = ""


def req(method, path, body=None, timeout=300):
    r = urllib.request.Request(BASE + path,
                               data=json.dumps(body).encode() if body is not None else None,
                               method=method)
    r.add_header("Content-Type", "application/json")
    r.add_header("User-Agent", "wb-final/1.0")
    if CSRF:
        r.add_header("X-CSRF-Token", CSRF)
    try:
        with OP.open(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500]


st, js = req("POST", "/api/auth/login", {"username": "admin", "password": "Admin@2024caishui"})
CSRF = next((c.value for c in CJ if c.name == "csrf_token"), "")
print("登录 ok=%s" % js.get("ok"))

st, js = req("POST", "/api/tax-risk-docs/analyze-start?company_id=1", {})
if not (isinstance(js, dict) and js.get("ok")):
    print("启动失败:", json.dumps(js, ensure_ascii=False)[:300]); raise SystemExit(1)
tid = js["task_id"]
print("任务:", tid)
for i in range(220):
    st, js = req("GET", "/api/tax-risk-docs/analyze-status/" + tid)
    if js.get("status") in ("done", "error"):
        print("结束: %s progress=%s" % (js.get("status"), js.get("progress")))
        break
    time.sleep(2)

st, raw = req("GET", "/api/tax-risk-docs/analyze-result/" + tid)
rep = raw.get("report") or {}
print("\n================ 一键分析结果 ================")
print("  ok            =", raw.get("ok"))
print("  overall_level =", json.dumps(rep.get("overall_level"), ensure_ascii=False))
print("  total_risks   =", rep.get("total_risks"),
      "(高%s/中%s/低%s)" % (rep.get("high_risk"), rep.get("mid_risk"), rep.get("low_risk")))
print("  files_count   =", rep.get("files_count"))
fr = rep.get("file_results") or []
print("  类型分布      =", dict(Counter((x.get("type") or "?") for x in fr)))
print("  findings      =", len(rep.get("all_findings") or []))
print("  stats         =", json.dumps(rep.get("stats"), ensure_ascii=False)[:300])
print("\n  ★ PDF 解析：")
for x in fr:
    if str(x.get("file", "")).lower().endswith(".pdf"):
        print("    - %-14s type=%-8s %s" % (x.get("file"), x.get("type"),
                                            " / ".join(str(a) for a in (x.get("actions") or [])[:1])))

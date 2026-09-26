# -*- coding: utf-8 -*-
"""诊断：只上传工资表时，资料被识别成什么类型、工资域为何未产出。"""
import io
import json
import os
import sys
import time
import uuid
import urllib.error
import urllib.request
import http.cookiejar

B = "http://127.0.0.1:8001"
CID = 1
CJ = http.cookiejar.CookieJar()
OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJ))
CS = ""


def req(m, p, b=None, t=900):
    r = urllib.request.Request(B + p, data=json.dumps(b).encode() if b is not None else None, method=m)
    r.add_header("Content-Type", "application/json")
    if CS:
        r.add_header("X-CSRF-Token", CS)
    try:
        with OP.open(r, timeout=t) as x:
            return x.status, json.loads(x.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:400]


def salary_bytes():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["工资表", "", "", "", ""])
    ws.append(["姓名", "证件号码", "应发工资", "代扣个税", "费款所属期"])
    for nm, idc, pay, tax in (("张三", "440300199001011234", 9500, 195),
                              ("李四", "440300199202022345", 12800, 474),
                              ("王五", "440300199303033456", 7600, 48)):
        ws.append([nm, idc, pay, tax, "2025-01"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


st, js = req("POST", "/api/auth/login", {"username": "admin", "password": "Admin@2024caishui"})
CS = next((c.value for c in CJ if c.name == "csrf_token"), "")

name = f"工资表_{uuid.uuid4().hex[:8]}.xlsx"
boundary = "----wb" + uuid.uuid4().hex
body = io.BytesIO()
body.write(f"--{boundary}\r\n".encode())
body.write(f'Content-Disposition: form-data; name="files"; filename="{name}"\r\n'.encode())
body.write(b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n")
body.write(salary_bytes())
body.write(f"\r\n--{boundary}--\r\n".encode())
r = urllib.request.Request(B + f"/api/tax-risk-docs/upload?company_id={CID}", data=body.getvalue(), method="POST")
r.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
if CS:
    r.add_header("X-CSRF-Token", CS)
with OP.open(r, timeout=300) as x:
    up = json.loads(x.read().decode("utf-8", "replace"))
print("上传:", json.dumps(up, ensure_ascii=False)[:300])

st, lst = req("GET", f"/api/tax-risk-docs/list?company_id={CID}")
hit = next((d for d in (lst if isinstance(lst, list) else []) if d.get("original_name") == name), None)
doc_id = hit["id"] if hit else None
print("doc_id =", doc_id)

st, s = req("POST", f"/api/tax-risk-docs/analyze-start?company_id={CID}&force=1")
tid = s.get("task_id")
stt = {}
for _ in range(450):
    st, stt = req("GET", "/api/tax-risk-docs/analyze-status/" + str(tid))
    if isinstance(stt, dict) and stt.get("status") in ("done", "error"):
        break
    time.sleep(2)
print("分析:", stt.get("status") if isinstance(stt, dict) else stt)

st, raw = req("GET", "/api/tax-risk-docs/analyze-result/" + str(tid))
rep = (raw or {}).get("report") or {}

print("\n=== file_results：类型识别 ===")
for fr in (rep.get("file_results") or []):
    print("  file=%-28s type=%-14s rows=%-5s actions=%s" % (
        str(fr.get("file"))[:28], fr.get("type"), len(fr.get("_rows") or []),
        str(fr.get("actions"))[:160]))

print("\n=== all_findings ===")
for f in (rep.get("all_findings") or []):
    print("  [%s] %s  terminal=%s" % (f.get("level"), f.get("type"), f.get("terminal_state")))

print("\n=== pipeline_log 中工资/社保/宗旨/覆盖相关 ===")
for ln in (rep.get("pipeline_log") or []):
    if any(k in str(ln) for k in ("工资", "社保", "宗旨", "覆盖", "封印", "治理", "剔除", "过滤")):
        print("  ", str(ln)[:220])

print("\n=== domain_summary（域级结果是否保留）===")
for d in (rep.get("domain_summary") or []):
    if not isinstance(d, dict):
        continue
    fs = d.get("findings") or []
    if fs:
        print("  域=%-20s findings=%d  types=%s" % (
            str(d.get("domain"))[:20], len(fs),
            [str(x.get("type"))[:26] for x in fs[:4]]))

print("\n=== 数对照 ===")
print("  report.all_findings =", len(rep.get("all_findings") or []),
      [str(f.get("type"))[:30] for f in (rep.get("all_findings") or [])])
print("  audit_doctrine =", json.dumps({k: (rep.get("audit_doctrine") or {}).get(k)
                                        for k in ("total", "with_resolve", "with_self_proof")},
                                       ensure_ascii=False))
print("  comprehensive.total_risks =", (rep.get("comprehensive") or {}).get("total_risks"))

if doc_id:
    req("POST", "/api/tax-risk-docs/batch-delete", {"company_id": CID, "doc_ids": [doc_id]})
    req("DELETE", f"/api/tax-risk-docs/report?company_id={CID}")
    print("\n[清理] 已移除合成资料与报告")

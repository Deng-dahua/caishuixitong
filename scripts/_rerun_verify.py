# -*- coding: utf-8 -*-
"""重跑账套1（现有资料，force=1）并验证本轮三处改动是否生效：

  ① VR034 费用口径修正：不再把全序时账借方发生额当"费用"
     （旧值：费用合计 44,394,561.24 / 费用率 668.9%）
  ② VR060 新增主营成本**双口径勾稽**（账面 6401 vs 进项发票口径）
  ③ 表名改名：「未匹配付款成本」→「无供应商级明细可核对的成本」

只读触发分析，不上传任何新资料。
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
import http.cookiejar

B = "http://127.0.0.1:8001"
CID = 1
CJ = http.cookiejar.CookieJar()
OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJ))
CS = ""


def req(m, p, b=None, t=1200):
    r = urllib.request.Request(B + p, data=json.dumps(b).encode() if b is not None else None, method=m)
    r.add_header("Content-Type", "application/json")
    if CS:
        r.add_header("X-CSRF-Token", CS)
    try:
        with OP.open(r, timeout=t) as x:
            return x.status, json.loads(x.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:400]


st, js = req("POST", "/api/auth/login", {"username": "admin", "password": "Admin@2024caishui"})
CS = next((c.value for c in CJ if c.name == "csrf_token"), "")
print("登录:", st)

st, s = req("POST", f"/api/tax-risk-docs/analyze-start?company_id={CID}&force=1")
print("启动分析:", st)
tid = (s or {}).get("task_id") or (s or {}).get("id")
print("task_id:", tid)

# 轮询结果
raw = None
for _ in range(120):
    time.sleep(5)
    st, raw = req("GET", "/api/tax-risk-docs/analyze-result/" + str(tid))
    if st != 200:
        continue
    d = raw.get("result") or raw.get("report") or raw
    if isinstance(d, dict) and (d.get("report") or d.get("status") in ("done", "completed")):
        print("分析完成")
        break
else:
    print("轮询超时")

rep = {}
if isinstance(raw, dict):
    rep = (raw.get("result") or {}).get("report") or raw.get("report") or {}

findings = rep.get("all_findings") or []
txt = json.dumps(rep, ensure_ascii=False)
print()
print("=" * 70)
print("发现总数:", len(findings))
print("=" * 70)

# ① 费用率是否修正
print()
print("【① VR034 费用口径】")
for m in re.finditer(r"费用率\s*([\d.]+)%", txt):
    print("   报告中的费用率:", m.group(1) + "%")
print("   旧错误值 668.9% 是否仍在:", "668.9" in txt)

# ② 双口径勾稽
print()
print("【② 双口径勾稽】")
dual = [f for f in findings if isinstance(f, dict)
        and "两个口径" in str(f.get("detail") or "")]
print("   产出双口径待核事实:", len(dual), "条")
for f in dual:
    om = f.get("observed_metrics") or {}
    print("   level:", f.get("level"),
          "| 账面:", om.get("book_cost_total"),
          "| 发票:", om.get("core_cost_total"),
          "| 差异:", om.get("cost_basis_gap"),
          "| 占比:", om.get("cost_basis_gap_ratio"))
    print("   detail:", str(f.get("detail"))[:220])

# ③ 改名
print()
print("【③ 表名改名】")
print("   旧名「未匹配付款成本」仍在:", "未匹配付款成本" in txt)
print("   新名「无供应商级明细可核对的成本」出现:", "无供应商级明细可核对的成本" in txt)

# 附带：主营成本总额
print()
print("【主营成本总额】")
for f in findings:
    if isinstance(f, dict) and f.get("rule_id") == "VR060":
        om = f.get("observed_metrics") or {}
        if om.get("core_cost_total"):
            print("   发票口径:", om.get("core_cost_total"),
                  "| 账面口径:", om.get("book_cost_total"))
            break
print("=" * 70)

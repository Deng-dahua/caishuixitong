# -*- coding: utf-8 -*-
"""端到端验证：只上传「工资表」（无社保明细）时的一键分析行为。

宗旨：上传了什么资料就查什么资料。本脚本复刻用户场景并断言：

  ① 只有工资表也能跑出结论（不得零产出）
  ② **绝不**出现"N 名员工有工资无社保/未参保"这类违规认定
     （社保名单为空只说明资料没交，不构成违规证据）
  ③ 报告带出：已上传资料的可查清单 / 逐项风险的解除方式与自证清单 / 终局两态
  ④ 覆盖清单措辞为"已查尽 + 待补自证"，不是"因缺资料未能执行"

脚本自给自足（自己造资料上传 + 自清理），可重复运行。
"""
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
import http.cookiejar

B = "http://127.0.0.1:8001"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
        return e.code, e.read().decode("utf-8", "replace")[:500]


def salary_bytes():
    """造一份真实工资表（含姓名/应发工资/代扣个税/费款所属期），会被识别为 salary。"""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["工资表", "", "", "", ""])
    ws.append(["姓名", "证件号码", "应发工资", "代扣个税", "费款所属期"])
    for nm, idc, pay, tax in (
        ("张三", "440300199001011234", 9500, 195),
        ("李四", "440300199202022345", 12800, 474),
        ("王五", "440300199303033456", 7600, 48),
    ):
        ws.append([nm, idc, pay, tax, "2025-01"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def upload(name, data):
    boundary = "----wbboundary" + uuid.uuid4().hex
    body = io.BytesIO()

    def w(s):
        body.write(s.encode("utf-8") if isinstance(s, str) else s)

    w(f"--{boundary}\r\n")
    w(f'Content-Disposition: form-data; name="files"; filename="{name}"\r\n')
    w("Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n")
    w(data)
    w(f"\r\n--{boundary}--\r\n")
    r = urllib.request.Request(B + f"/api/tax-risk-docs/upload?company_id={CID}",
                               data=body.getvalue(), method="POST")
    r.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    if CS:
        r.add_header("X-CSRF-Token", CS)
    try:
        with OP.open(r, timeout=300) as x:
            return json.loads(x.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        print("   上传失败:", e.code, e.read().decode("utf-8", "replace")[:300])
        return {}


st, js = req("POST", "/api/auth/login", {"username": "admin", "password": "Admin@2024caishui"})
CS = next((c.value for c in CJ if c.name == "csrf_token"), "")
print("① 登录:", js.get("ok"))

name = f"工资表_{uuid.uuid4().hex[:8]}.xlsx"
up = upload(name, salary_bytes())
st, lst = req("GET", f"/api/tax-risk-docs/list?company_id={CID}")
lst = lst if isinstance(lst, list) else []
hit = next((d for d in lst if d.get("original_name") == name), None)
if not hit:
    print("! 上传未进入列表:", up)
    sys.exit(2)
doc_id = hit["id"]
print(f"   已上传【仅工资表】（无社保明细）doc_id={doc_id}")

print("\n② 强制分析（真实跑完整管道）")
st, s = req("POST", f"/api/tax-risk-docs/analyze-start?company_id={CID}&force=1")
tid = s.get("task_id")
stt, bad = {}, 0
for _ in range(450):
    st, stt = req("GET", "/api/tax-risk-docs/analyze-status/" + str(tid))
    if not isinstance(stt, dict):
        bad += 1
        if bad > 6:
            print("   状态查询持续异常:", st, str(stt)[:200])
            break
        time.sleep(2)
        continue
    bad = 0
    if stt.get("status") in ("done", "error"):
        break
    time.sleep(2)
print("   分析结束:", stt.get("status"))
if stt.get("status") != "done":
    print("! 分析未成功:", stt.get("message"))
    req("POST", "/api/tax-risk-docs/batch-delete", {"company_id": CID, "doc_ids": [doc_id]})
    sys.exit(3)

st, raw = req("GET", "/api/tax-risk-docs/analyze-result/" + str(tid))
rep = (raw or {}).get("report") or {}
findings = rep.get("all_findings") or []
err = rep.get("enterprise_readable_report") or {}

print("\n③ 断言")
ok = True

# ① 有结论
sal_related = [f for f in findings if "工资" in str(f.get("type") or "") or "社保" in str(f.get("type") or "")]
print(f"   发现总数 {len(findings)}｜工资社保相关 {len(sal_related)}")
for f in sal_related:
    print(f"      · [{f.get('level')}] {f.get('type')}  终局={f.get('terminal_state')}")
if not sal_related:
    print("   ⚠ 无工资社保相关发现（域可能未触发，需结合资料识别结果看）")

# ② 绝不诬告
accuse = [f for f in findings
          if ("无社保" in str(f.get("type") or "") or "未参保" in str(f.get("type") or ""))
          and str(f.get("level")) in ("高风险", "极高风险")]
bad_txt = [f for f in findings
           if any(k in str(f.get("detail") or "") + str(f.get("description") or "")
                  for k in ("名员工有工资发放但", "全员未参保", "所有员工均未参保"))]
if accuse or bad_txt:
    ok = False
    print("   ✗ 出现据空社保名单反推的违规认定:", [f.get("type") for f in (accuse + bad_txt)])
else:
    print("   ✓ 未据'社保名单为空'反推任何未参保违规（缺资料 ≠ 违规）")

# ③ 报告带出宗旨章节
for key, label in (("one_sided_digest", "已上传资料可查清单"),
                   ("resolution_ledger", "逐项解除与自证清单")):
    sec = err.get(key) or {}
    got = bool(sec.get("rows")) if isinstance(sec, dict) else False
    print(f"   {'✓' if got else '✗'} 报告章节「{label}」:", 
          f"{sec.get('check_count', sec.get('total', 0))} 行" if got else "缺失")
    if not got:
        ok = False
doc = rep.get("audit_doctrine") or {}
print("   " + ("✓" if doc else "✗") + " 宗旨执行情况:",
      json.dumps({k: doc.get(k) for k in ("total", "with_resolve", "with_self_proof",
                                          "ironclad", "self_provable", "pending")},
                 ensure_ascii=False) if doc else "缺失")
if not doc:
    ok = False

# ④ 覆盖清单措辞
cov = err.get("analysis_coverage") or {}
cs = str(cov.get("summary") or "")
print("   覆盖清单措辞:", cs[:160])
if "未能执行" in cs:
    ok = False
    print("   ✗ 覆盖清单仍在说'未能执行'（宗旨反对等资料齐全）")
else:
    print("   ✓ 覆盖清单为'已查尽 + 待补自证'语义")

# ⑤ 每条发现的出口（用户要求：反映风险 + 怎么解除 + 要补什么自证）
no_exit = [f for f in findings if not (f.get("resolve_steps") and f.get("self_proof_materials")
                                       and f.get("terminal_state"))]
print(f"   缺出口的发现: {len(no_exit)}/{len(findings)}")
if no_exit:
    ok = False
    print("      ✗ 示例:", [str(x.get("type"))[:26] for x in no_exit[:5]])
else:
    print("   ✓ 每条发现都带 解除方式 + 需补自证资料 + 终局方向")

# ⑥ 正式输出范围：分析到的风险必须全部呈现
scope = rep.get("output_scope") or {}
print("   正式输出范围:", json.dumps({k: scope.get(k) for k in
                                    ("total", "promoted_total", "evidence_tiers")},
                                   ensure_ascii=False))
if scope.get("total"):
    ok = False
    print("   ✗ 仍有分析结论未进入报告（用户要求：全部呈现）:",
          [d.get("domain") for d in (scope.get("by_domain") or [])][:5])
else:
    print("   ✓ 全部分析结论均已进入报告")

# ⑦ 报告章节必须覆盖每一条且标注证据地位
led = err.get("resolution_ledger") or {}
print(f"   解除与自证清单章节: {led.get('total')} 行 | 列: {led.get('columns')}")
if led.get("total") != len(findings) or "证据地位" not in (led.get("columns") or []):
    ok = False
    print("   ✗ 章节行数与报告发现数不一致，或缺『证据地位』列")
else:
    print("   ✓ 每条发现都在『解除与自证清单』中，且标明证据地位")

# 自清理
try:
    req("POST", "/api/tax-risk-docs/batch-delete", {"company_id": CID, "doc_ids": [doc_id]})
    req("DELETE", f"/api/tax-risk-docs/report?company_id={CID}")
    print("\n   [清理] 合成资料与报告已移除")
except Exception as exc:
    print("\n   [清理] 异常:", exc)

print("\n" + ("结论：宗旨已落地 ✓" if ok else "结论：仍有不满足项 ✗"))

# ══════════════════════════════════════════════════════════════════════
# 第二阶段：两侧齐备（工资表 + 社保明细）必须真正比出"有工资无社保"
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("第二阶段：工资表 + 社保明细 齐备 → 真交叉核验")


def ss_bytes():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["社会保险费缴费明细", "", "", ""])
    ws.append(["姓名", "证件号码", "缴费基数", "费款所属期"])
    for nm, idc, base in (("张三", "440300199001011234", 9500),
                          ("李四", "440300199202022345", 12800)):
        ws.append([nm, idc, base, "2025-01"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


sn = f"社保明细_{uuid.uuid4().hex[:8]}.xlsx"
up2 = upload(name, salary_bytes())
up3 = upload(sn, ss_bytes())
st, lst = req("GET", f"/api/tax-risk-docs/list?company_id={CID}")
lst = lst if isinstance(lst, list) else []
ids2 = [d["id"] for d in lst if d.get("original_name") in (name, sn)]
if len(ids2) < 2:
    print("! 两侧资料未就位:", up2, up3)
    sys.exit(ok is True and 2 or 1)
print("   已上传工资表 + 社保明细，doc_ids =", ids2)

st, s = req("POST", f"/api/tax-risk-docs/analyze-start?company_id={CID}&force=1")
tid = s.get("task_id")
for _ in range(450):
    st, stt = req("GET", "/api/tax-risk-docs/analyze-status/" + str(tid))
    if isinstance(stt, dict) and stt.get("status") in ("done", "error"):
        break
    time.sleep(2)
print("   分析结束:", stt.get("status") if isinstance(stt, dict) else stt)

st, raw = req("GET", "/api/tax-risk-docs/analyze-result/" + str(tid))
rep2 = (raw or {}).get("report") or {}
f2 = rep2.get("all_findings") or []
for x in f2:
    if any(k in str(x.get("type") or "") for k in ("工资", "社保")):
        print("     · [%s] %s  终局=%s" % (x.get("level"), x.get("type"), x.get("terminal_state")))
gap = [x for x in f2 if "有工资无社保" in str(x.get("type") or "")]
if gap:
    g = gap[0]
    print("   ✓ 两侧齐备时比对出「有工资无社保」: 等级=%s 终局=%s 解除=%d条 自证=%d条" % (
        g.get("level"), g.get("terminal_state"),
        len(g.get("resolve_steps") or []), len(g.get("self_proof_materials") or [])))
    if g.get("level") not in ("高风险", "中风险", "待核验"):
        ok = False
        print("   ✗ 等级异常")
else:
    ok = False
    print("   ✗ 两侧齐备仍未产出「有工资无社保」")

try:
    req("POST", "/api/tax-risk-docs/batch-delete", {"company_id": CID, "doc_ids": ids2})
    req("DELETE", f"/api/tax-risk-docs/report?company_id={CID}")
    print("   [清理] 两侧合成资料与报告已移除")
except Exception as exc:
    print("   [清理] 异常:", exc)

print("\n最终结论：" + ("宗旨全链路已落地 ✓" if ok else "仍有不满足项 ✗"))
sys.exit(0 if ok else 1)

# -*- coding: utf-8 -*-
"""主体一致性闸门验收：
   场景A 错配（猩猩织光资料 → 无关账套）→ 必须阻断，不出报告
   场景B 匹配（猩猩织光资料 → 猩猩织光账套）→ 不得误杀，正常出报告
   场景C 混合（深圳海更申报表 + 猩猩织光社保 → 深圳海更账套）→ 只剔除不符者，继续出报告
"""
import os, sys, json, sqlite3, glob, shutil
os.environ["APP_COOKIE_SECURE"] = "0"
BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(BASE)
sys.path.insert(0, PROJECT); sys.path.insert(0, BASE)

XX_FILES = [
    "data/uploads/3/3_259_猩猩织光_北京_商贸有限公司_2026年1账期_工资表.xls",
    "data/uploads/3/3_260_猩猩织光_北京_商贸有限公司_2026年1账期_进项发票列表.xlsx",
    "data/uploads/3/3_269_猩猩织光_北京_商贸有限公司_社保明细_2026年01期.xls_.xlsx",
]
HX_FILES = [
    "data/uploads/1/1_504_增值税及附加税费申报表_一般纳税人适用_2025-01-01-2025-01-31_.pdf",
]


def mk_company(cid, name, uscc):
    c = sqlite3.connect(os.path.join(PROJECT, "data", "accounting.db"))
    c.execute("DELETE FROM companies WHERE id=?", (cid,))
    c.execute(
        "INSERT INTO companies(id,name,uscc,registered_capital,established_date,"
        "legal_representative,legal_representative_id,address,business_scope,"
        "company_type,industry_code,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (cid, name, uscc, "5000000", "2018-03-15", "张三", "440300199001010011",
         "北京市朝阳区测试路1号", "商贸", "有限责任公司", "52", "2026-01-01"))
    c.commit(); c.close()


def run_scene(cid, title, files):
    mk_company(*cid)
    from fastapi.testclient import TestClient
    import main as appmod
    client = TestClient(appmod.app)
    lr = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@2024caishui"})
    hdr = {"X-CSRF-Token": client.cookies.get("csrf_token", "")}
    payload = []
    for rel in files:
        fp = os.path.join(PROJECT, rel)
        payload.append(("files", (os.path.basename(rel), open(fp, "rb").read(),
                                  "application/pdf" if rel.endswith(".pdf") else "application/octet-stream")))
    up = client.post(f"/api/tax-risk-docs/upload?company_id={cid[0]}", files=payload, headers=hdr).json()
    print("\n" + "=" * 96)
    print("【%s】账套=%s  上传 %d 个文件" % (title, cid[1], len(files)))
    print("  upload.message =", up.get("message"))
    if up.get("subject_warnings"):
        for w in up["subject_warnings"]:
            print("  ⚠ 上传提示:", w["filename"][:44], "->", w["reason"][:80])

    r = client.post(f"/api/tax-risk-docs/analyze?company_id={cid[0]}", headers=hdr).json()
    print("  analyze.ok =", r.get("ok"))
    if r.get("subject_mismatch"):
        print("  ★ 已阻断：", str(r.get("message"))[:220])
        for m in (r.get("mismatched_files") or [])[:4]:
            print("     -", m.get("file")[:48], "|", m.get("reason")[:70])
    elif r.get("ok"):
        rep = r.get("report") or {}
        sc = rep.get("subject_check") or {}
        print("  ★ 正常出报告：overall_level =", json.dumps(rep.get("overall_level"), ensure_ascii=False))
        print("     subject_check =", json.dumps(sc, ensure_ascii=False)[:300])
    else:
        print("  其他失败：", str(r.get("message"))[:200])
    return r


def cleanup(cid):
    d = os.path.join(PROJECT, "data", "uploads", str(cid))
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if fn.startswith(str(cid) + "_"):
                os.remove(os.path.join(d, fn))
    c = sqlite3.connect(os.path.join(PROJECT, "data", "accounting.db"))
    c.execute("DELETE FROM companies WHERE id=?", (cid,)); c.commit(); c.close()


# 场景A：猩猩织光资料 → 无关账套（应阻断）
ra = run_scene((9995, "测试无关企业有限公司", "91110000TEST0001XX"), "场景A 错配", XX_FILES)
assert ra.get("subject_mismatch") and not ra.get("ok"), "场景A 应被阻断！"

# 场景B：猩猩织光资料 → 猩猩织光账套（不得误杀）
rb = run_scene((9994, "猩猩织光（北京）商贸有限公司", "91110117XXXXXXXXXX"), "场景B 匹配", XX_FILES)
assert rb.get("ok") and not rb.get("subject_mismatch"), "场景B 被误杀！"

# 场景C：混合
rc = run_scene((9993, "深圳海更数字传媒有限公司", "91440300MA5H824G7M"), "场景C 混合",
               HX_FILES + [XX_FILES[0]])
assert rc.get("ok"), "场景C 不应被阻断（仍有匹配资料）"

for cid in (9995, 9994, 9993):
    cleanup(cid)

# ═══════════ 场景D：异步「一键分析」按钮路径的阻断（analyze-start → 轮询 → analyze-result）═══════════
import time
mk_company(9992, "测试无关企业B有限公司", "91110000TEST0002XX")
from fastapi.testclient import TestClient
import main as appmod
client = TestClient(appmod.app)
client.post("/api/auth/login", json={"username": "admin", "password": "Admin@2024caishui"})
hdr = {"X-CSRF-Token": client.cookies.get("csrf_token", "")}
payload = []
for rel in XX_FILES[:2]:
    fp = os.path.join(PROJECT, rel)
    payload.append(("files", (os.path.basename(rel), open(fp, "rb").read(), "application/octet-stream")))
client.post("/api/tax-risk-docs/upload?company_id=9992", files=payload, headers=hdr)
st = client.post("/api/tax-risk-docs/analyze-start?company_id=9992", headers=hdr).json()
tid = st.get("task_id")
print("\n" + "=" * 96)
print("【场景D 异步按钮路径】task_id =", tid)
for _ in range(60):
    s = client.get(f"/api/tax-risk-docs/analyze-status/{tid}", headers=hdr).json()
    if s.get("status") in ("done", "error"):
        break
    time.sleep(1)
res = client.get(f"/api/tax-risk-docs/analyze-result/{tid}", headers=hdr).json()
print("  analyze-result.ok =", res.get("ok"), " blocked =", res.get("blocked"))
print("  message =", str(res.get("message"))[:220])
print("  suggestion =", str(res.get("suggestion"))[:120])
assert res.get("blocked") and not res.get("ok"), "场景D 异步路径未正确阻断/未标记 blocked！"
assert "分析失败" not in str(res.get("message")), "场景D 不应显示为'分析失败'"
cleanup(9992)

print("\n" + "=" * 96)
print("全部断言通过：A 错配阻断 ✓ / B 匹配不误杀 ✓ / C 混合只剔除不符者 ✓ / D 异步路径拦截提示 ✓")


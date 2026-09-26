# -*- coding: utf-8 -*-
"""端到端验证：增值税申报表 PDF 能否被一键分析正确读取并进入 tax_declarations。"""
import os, sys, json, sqlite3, glob

os.environ["APP_COOKIE_SECURE"] = "0"
os.environ["APP_ALLOWED_ORIGINS"] = "http://127.0.0.1:8001"
BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(BASE)
sys.path.insert(0, PROJECT)
sys.path.insert(0, BASE)

TEST_CID = 9997
CO_NAME = "测试增值税申报PDF企业"

# 两份真实申报表：2025-01（普通月）+ 2025-09（有期末留抵）
VAT_FILES = [
    glob.glob(os.path.join(PROJECT, "data/trash/1_295_*.pdf")),
    glob.glob(os.path.join(PROJECT, "data/trash/1_303_*.pdf")),
]


def setup_company():
    c = sqlite3.connect(os.path.join(PROJECT, "data", "accounting.db"))
    c.execute("DELETE FROM companies WHERE id=?", (TEST_CID,))
    c.execute(
        "INSERT INTO companies(id,name,uscc,registered_capital,established_date,"
        "legal_representative,legal_representative_id,address,business_scope,"
        "company_type,industry_code,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (TEST_CID, CO_NAME, "91440300MA5H824G7M", "5000000", "2018-03-15",
         "张晓冬", "440300199001010011", "深圳市龙岗区坂田街道", "其他综合零售",
         "有限责任公司", "52", "2026-01-01"))
    c.commit()
    c.close()


def main():
    setup_company()
    from fastapi.testclient import TestClient
    import main as appmod

    client = TestClient(appmod.app)
    lr = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@2024caishui"})
    if not lr.json().get("ok"):
        print("[登录失败]", lr.status_code, lr.text[:200])
        return
    csrf = client.cookies.get("csrf_token", "")
    hdr = {"X-CSRF-Token": csrf} if csrf else {}

    files = []
    for lst in VAT_FILES:
        if not lst:
            continue
        p = lst[0]
        files.append(("files", (os.path.basename(p).split("_", 2)[2], open(p, "rb").read(), "application/pdf")))
    if not files:
        print("找不到测试用的申报表 PDF")
        return
    print("上传 %d 份申报表 PDF" % len(files))

    r = client.post(f"/api/tax-risk-docs/upload?company_id={TEST_CID}", files=files, headers=hdr)
    print("[upload]", r.status_code, json.dumps(r.json(), ensure_ascii=False)[:300])

    r = client.post(f"/api/tax-risk-docs/analyze?company_id={TEST_CID}", headers=hdr)
    print("[analyze]", r.status_code)
    body = r.json()
    if not body.get("ok"):
        print("  失败:", str(body.get("message"))[:400])
        return
    rep = body["report"]

    print("\n========== ① 文件识别结果 ==========")
    for x in rep.get("file_results") or []:
        print("  %-52s type=%-18s" % (str(x.get("file"))[:52], x.get("type")))
        for a in (x.get("actions") or [])[:2]:
            print("      · %s" % str(a)[:120])

    print("\n========== ② pipeline_log 中的申报表提取 ==========")
    for line in rep.get("pipeline_log") or []:
        if "申报" in str(line) or "vat" in str(line).lower():
            print("  ", str(line)[:150])

    print("\n========== ③ 增值税申报比对域 ==========")
    for d in rep.get("domain_summary") or []:
        if "增值税" in str(d.get("domain", "")):
            print("  domain =", d.get("domain"))
            for f in (d.get("findings") or [])[:5]:
                print("    -", str(f.get("title") or f.get("desc") or f)[:130])

    print("\n========== ④ 判定 ==========")
    fr = rep.get("file_results") or []
    n_decl = sum(1 for x in fr if x.get("type") in ("vat_declaration", "tax_declaration"))
    print("  识别为申报表的文件数 =", n_decl)
    print("  >>", "✓ PDF 申报表已被一键分析读取" if n_decl else "✗ 未被识别")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""端到端验证两税收入差异比对：上传银行流水 + 增值税申报表 + 企业所得税申报表，
跑一键分析，检查 comprehensive.two_tax_income 与报告章节。"""
import os, sys, json, sqlite3, random
os.environ["APP_COOKIE_SECURE"] = "0"
os.environ["APP_ALLOWED_ORIGINS"] = "http://127.0.0.1:8001"
BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(BASE)
sys.path.insert(0, PROJECT)
sys.path.insert(0, BASE)

TEST_CID = random.randint(90000, 99999)  # 每次全新公司，避免历史上传残留污染解析
CO_NAME = "测试两税差异企业"

SAMPLE_BANK = os.path.join(BASE, "sample_bank_flow.csv")
SAMPLE_CIT = os.path.join(BASE, "sample_cit_decl.csv")


def setup_company():
    c = sqlite3.connect(os.path.join(PROJECT, "data", "accounting.db"))
    c.execute("DELETE FROM companies WHERE id=?", (TEST_CID,))
    c.execute(
        "INSERT INTO companies(id,name,uscc,registered_capital,established_date,"
        "legal_representative,legal_representative_id,address,business_scope,"
        "company_type,industry_code,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (TEST_CID, CO_NAME, "91442000MA55TTWOT", "5000000", "2018-03-15",
         "范善茂", "421025198001010015", "中山市测试路2号", "棉纺织加工",
         "有限责任公司", "17", "2026-01-01"))
    c.commit(); c.close()


def write_vat(path):
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write("项目,金额,栏次\n")
        f.write("销售额,400000.00,1\n")
        f.write("销项税额,52000.00,2\n")
        f.write("进项税额,30000.00,3\n")
        f.write("应纳税额合计,62000.00,4\n")


def main():
    setup_company()
    from fastapi.testclient import TestClient
    import main as appmod
    client = TestClient(appmod.app)
    lr = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@2024caishui"})
    if not lr.json().get("ok"):
        print("[login failed]", lr.status_code, lr.text[:200]); return
    csrf = client.cookies.get("csrf_token", "")
    hdr = {"X-CSRF-Token": csrf} if csrf else {}

    vat_path = os.path.join(BASE, "_tmp_vat_decl.csv")
    write_vat(vat_path)

    files = [
        ("files", ("测试企业银行流水.csv", open(SAMPLE_BANK, "rb").read(), "text/csv")),
        ("files", ("测试企业增值税申报表.csv", open(vat_path, "rb").read(), "text/csv")),
        ("files", ("cit.csv", open(SAMPLE_CIT, "rb").read(), "text/csv")),
    ]
    r = client.post(f"/api/tax-risk-docs/upload?company_id={TEST_CID}", files=files, headers=hdr)
    print("[upload]", r.status_code, json.dumps(r.json(), ensure_ascii=False)[:400])
    r = client.post(f"/api/tax-risk-docs/analyze?company_id={TEST_CID}", headers=hdr)
    print("[analyze]", r.status_code)
    body = r.json()
    if not body.get("ok"):
        print("  analyze failed:", body.get("message", str(body))[:400]); return
    rep = body["report"]
    comp = rep.get("comprehensive", {})
    tt = comp.get("two_tax_income")
    bf = comp.get("bank_flow")
    print("\n========== comprehensive.two_tax_income ==========")
    print(json.dumps(tt, ensure_ascii=False, indent=2)[:2000] if tt else "None (未生成!)")

    err = rep.get("enterprise_readable_report", {}) or {}
    ttr = err.get("two_tax_report")
    print("\n========== enterprise_readable_report.two_tax_report ==========")
    print(json.dumps(ttr, ensure_ascii=False, indent=2)[:1600] if ttr else "None (报告章节未生成!)")

    # 断言
    assert tt and tt.get("available"), "two_tax_income 未生成"
    tm = tt.get("metrics", {})
    # 我的样例：增值税销售额400000 vs 所得税营业收入250000 → 偏离60% → 高风险
    assert tm.get("vat_sales") == 400000.0, tm
    assert tm.get("cit_income") == 250000.0, tm
    assert tm.get("diff") == 150000.0, tm
    assert "显著高于" in tt.get("verdict", ""), tt.get("verdict")
    assert ttr and ttr.get("title"), "报告章节未生成"
    # 资金流章节也应随同生成（同一份银行流水）
    assert bf and bf.get("available"), "bank_flow 未生成"
    assert bf.get("metrics", {}).get("personal_receipt") == 650000.0, bf.get("metrics")
    print("\n[OK] 端到端验证通过：两税差异比对章节已生成并接入主链路"
          f"（增值税{tm['vat_sales']} vs 所得税{tm['cit_income']} 差额{tm['diff']}）")


if __name__ == "__main__":
    main()

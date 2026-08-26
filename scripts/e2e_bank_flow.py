# -*- coding: utf-8 -*-
"""端到端验证资金流比对：上传银行流水 + 增值税申报表，跑一键分析，检查 comprehensive.bank_flow。"""
import os, sys, json, sqlite3
os.environ["APP_COOKIE_SECURE"] = "0"
os.environ["APP_ALLOWED_ORIGINS"] = "http://127.0.0.1:8001"
BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(BASE)
sys.path.insert(0, PROJECT)
sys.path.insert(0, BASE)

TEST_CID = 9999
CO_NAME = "测试资金流企业"

SAMPLE_BANK = os.path.join(BASE, "sample_bank_flow.csv")


def setup_company():
    c = sqlite3.connect(os.path.join(PROJECT, "data", "accounting.db"))
    c.execute("DELETE FROM companies WHERE id=?", (TEST_CID,))
    c.execute(
        "INSERT INTO companies(id,name,uscc,registered_capital,established_date,"
        "legal_representative,legal_representative_id,address,business_scope,"
        "company_type,industry_code,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (TEST_CID, CO_NAME, "91442000MA55BFLOW", "5000000", "2018-03-15",
         "范善茂", "421025198001010015", "中山市测试路1号", "棉纺织加工",
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
    ]
    r = client.post(f"/api/tax-risk-docs/upload?company_id={TEST_CID}", files=files, headers=hdr)
    print("[upload]", r.status_code, json.dumps(r.json(), ensure_ascii=False)[:240])
    r = client.post(f"/api/tax-risk-docs/analyze?company_id={TEST_CID}", headers=hdr)
    print("[analyze]", r.status_code)
    body = r.json()
    if not body.get("ok"):
        print("  analyze failed:", body.get("message", str(body))[:400]); return
    rep = body["report"]
    comp = rep.get("comprehensive", {})
    bf = comp.get("bank_flow")
    print("\n========== comprehensive.bank_flow ==========")
    print(json.dumps(bf, ensure_ascii=False, indent=2)[:2000] if bf else "None (未生成!)")

    err = rep.get("enterprise_readable_report", {}) or {}
    bfr = err.get("bank_flow_report")
    print("\n========== enterprise_readable_report.bank_flow_report ==========")
    print(json.dumps(bfr, ensure_ascii=False, indent=2)[:1600] if bfr else "None (报告章节未生成!)")

    # 断言（环境里 9999 公司可能累积了历史上传，故只校验确定性的部分）
    assert bf and bf.get("available"), "bank_flow 未生成"
    m = bf.get("metrics", {})
    # 我的样例私户（张伟50万+李娜15万）必须被正确识别计入
    assert m.get("personal_receipt") == 650000.0, m
    assert m.get("uninvoiced_gap") is not None and m["uninvoiced_gap"] > 0, m
    assert ("严重背离" in bf.get("verdict", "") or "异常" in bf.get("verdict", "")), bf.get("verdict")
    assert bfr and bfr.get("title"), "报告章节未生成"
    print("\n[OK] 端到端验证通过：资金流比对章节已生成并接入主链路（私户识别=" + str(m.get("personal_receipt")) + "）")


if __name__ == "__main__":
    main()

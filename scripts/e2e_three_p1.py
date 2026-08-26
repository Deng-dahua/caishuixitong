"""第四阶 P1 三能力端到端验证：上传 进项发票 + 销项发票 + 银行流水，
断言 comprehensive[input_voucher/false_invoice/fund_loop] 与报告章节均生成。"""
import os, sys, json, sqlite3, random
os.environ["APP_COOKIE_SECURE"] = "0"
os.environ["APP_ALLOWED_ORIGINS"] = "http://127.0.0.1:8001"
BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(BASE)
sys.path.insert(0, PROJECT)
sys.path.insert(0, BASE)

TEST_NAME = "测试虚开风险企业"
TEST_USCC = "91442000MA55FAKE01"
COMPANY_ID = random.randint(90000, 99999)

from fastapi.testclient import TestClient
import main as appmod

client = TestClient(appmod.app)
lr = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@2024caishui"})
csrf = client.cookies.get("csrf_token", "")
hdr = {"X-CSRF-Token": csrf} if csrf else {}

# 清理并插入测试公司
c = sqlite3.connect(os.path.join(PROJECT, "data", "accounting.db"))
c.execute("DELETE FROM companies WHERE id=?", (COMPANY_ID,))
c.execute("INSERT INTO companies(id,name,uscc,registered_capital,established_date,legal_representative,"
          "legal_representative_id,address,business_scope,company_type,industry_code,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
          (COMPANY_ID, TEST_NAME, TEST_USCC, 5000000, "2018-03-15", "范善茂", "421025198001010015",
           "中山市", "棉纺织加工", "有限责任公司", "17", "2026-01-01"))
c.commit(); c.close()

files = [
    ("files", ("进项发票.csv", open(os.path.join(BASE, "sample_purchase_invoice.csv"), "rb").read(), "text/csv")),
    ("files", ("销项发票.csv", open(os.path.join(BASE, "sample_sales_invoice.csv"), "rb").read(), "text/csv")),
    ("files", ("bank流水.csv", open(os.path.join(BASE, "sample_bank_flow.csv"), "rb").read(), "text/csv")),
]
up = client.post(f"/api/tax-risk-docs/upload?company_id={COMPANY_ID}", files=files, headers=hdr)
print("[upload]", up.status_code, json.dumps(up.json(), ensure_ascii=False)[:200])

r = client.post(f"/api/tax-risk-docs/analyze?company_id={COMPANY_ID}", headers=hdr)
b = r.json()
assert b.get("ok"), "analyze 失败: " + json.dumps(b, ensure_ascii=False)[:400]
rep = b["report"]
comp = rep.get("comprehensive", {})

# ── 断言 ① 进项异常凭证 ──
iv = comp.get("input_voucher") or {}
assert iv.get("available"), "input_voucher 未 available"
ivm = iv.get("metrics", {})
assert ivm.get("concentration_ratio", 0) > 0.85, ivm
assert ivm.get("should_transfer_out_tax", 0) > 0, ivm
print(f"[断言①] 进项异常凭证: 集中度={ivm['concentration_ratio']:.3f} 应转出={ivm['should_transfer_out_tax']} verdict={iv.get('verdict')}")

# ── 断言 ② 虚开风险网络 ──
fi = comp.get("false_invoice") or {}
assert fi.get("available"), "false_invoice 未 available"
fim = fi.get("metrics", {})
assert fim.get("top3_customer_share", 0) > 0.8, fim
assert fim.get("fund_loop_amount", 0) > 0, fim
print(f"[断言②] 虚开风险网络: 前3客户={fim['top3_customer_share']:.3f} 资金回流={fim['fund_loop_amount']} verdict={fi.get('verdict')}")

# ── 断言 ③ 跨企业资金回流闭环 ──
fl = comp.get("fund_loop") or {}
assert fl.get("available"), "fund_loop 未 available"
flm = fl.get("metrics", {})
assert flm.get("direct_loop_amount", 0) == 60000.0, flm  # 冠茂 收60000/付120000
assert flm.get("circular_amount", 0) >= 60000.0, flm
print(f"[断言③] 资金回流闭环: 直接={flm['direct_loop_amount']} 合计={flm['circular_amount']} verdict={fl.get('verdict')}")

# ── 断言 报告章节 ──
err = rep.get("enterprise_readable_report") or {}
for key, ch in (("input_voucher_report", "十五"), ("false_invoice_report", "十六"), ("fund_loop_report", "十七")):
    sec = err.get(key) or {}
    assert sec.get("title"), f"报告章节 {key} 缺失"
    print(f"[断言④] 报告章节 {ch} ({key}) 存在: {sec['title']}")

print("\n[OK] 第四阶 P1 三能力端到端全部断言通过")

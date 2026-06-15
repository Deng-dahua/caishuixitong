"""
88文件综合税务风险分析报告生成脚本 v2
直接调用分析引擎，生成专业HTML报告
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time

start_time = time.time()
print("=" * 60)
print("88文件综合税务风险分析报告生成器 v2")
print("=" * 60)

from database import SessionLocal, BankTransaction, SalesInvoice, PurchaseInvoice, JournalEntry
from database import SalaryRecord, SocialSecurityDetail, HousingFundDetail, Supplier, Customer, Contract
from sqlalchemy import func, desc, text

db = SessionLocal()
cid = 1

# ========== [1/6] 数据底账 ==========
print("\n[1/6] 加载数据底账...")
data_counts = {}
for tbl, label in [
    ('sales_invoices', '销项发票'), ('purchase_invoices', '进项发票'),
    ('journal_entries', '序时账凭证'), ('bank_transactions', '银行流水'),
    ('salary_records', '工资记录'), ('suppliers', '供应商'),
    ('customers', '客户'), ('contracts', '合同'),
    ('social_security_details', '社保明细'), ('housing_fund_details', '公积金明细'),
]:
    try:
        cnt = db.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
        data_counts[label] = cnt
        if cnt > 0: print(f"  {label}: {cnt}")
    except Exception as e:
        data_counts[label] = 0

# 金额汇总
si_amt = db.execute(text("SELECT COALESCE(SUM(amount),0) FROM sales_invoices WHERE company_id=1")).scalar() or 0
si_tax = db.execute(text("SELECT COALESCE(SUM(tax_amount),0) FROM sales_invoices WHERE company_id=1")).scalar() or 0
pi_amt = db.execute(text("SELECT COALESCE(SUM(amount),0) FROM purchase_invoices WHERE company_id=1")).scalar() or 0
bt_out = db.query(func.sum(BankTransaction.debit_amount)).filter(BankTransaction.company_id==cid).scalar() or 0
bt_in = db.query(func.sum(BankTransaction.credit_amount)).filter(BankTransaction.company_id==cid).scalar() or 0
je_dr = db.query(func.sum(JournalEntry.debit_amount)).filter(JournalEntry.company_id==cid).scalar() or 0
je_cr = db.query(func.sum(JournalEntry.credit_amount)).filter(JournalEntry.company_id==cid).scalar() or 0

totals = {"si_amt": float(si_amt), "si_tax": float(si_tax), "pi_amt": float(pi_amt),
          "bt_out": float(bt_out), "bt_in": float(bt_in),
          "je_dr": float(je_dr), "je_cr": float(je_cr)}
print(f"  销项总额: {float(si_amt):,.2f}  进项总额: {float(pi_amt):,.2f}")
print(f"  银行: 流出={float(bt_out):,.2f}  流入={float(bt_in):,.2f}  净={float(bt_in)-float(bt_out):,.2f}")
print(f"  序时账: 借={float(je_dr):,.2f}  贷={float(je_cr):,.2f}")

# 日期范围
si_dates = db.execute(text("SELECT MIN(invoice_date), MAX(invoice_date) FROM sales_invoices WHERE company_id=1")).fetchone()
bt_dates = db.execute(text("SELECT MIN(transaction_date), MAX(transaction_date) FROM bank_transactions WHERE company_id=1")).fetchone()
je_dates = db.execute(text("SELECT MIN(entry_date), MAX(entry_date) FROM journal_entries WHERE company_id=1")).fetchone()
period_info = {
    "si_from": str(si_dates[0]) if si_dates and si_dates[0] else "N/A",
    "si_to": str(si_dates[1]) if si_dates and si_dates[1] else "N/A",
    "bt_from": str(bt_dates[0]) if bt_dates and bt_dates[0] else "N/A",
    "bt_to": str(bt_dates[1]) if bt_dates and bt_dates[1] else "N/A",
    "je_from": str(je_dates[0]) if je_dates and je_dates[0] else "N/A",
    "je_to": str(je_dates[1]) if je_dates and je_dates[1] else "N/A",
}

# 公司
co = db.execute(text("SELECT name, uscc FROM companies WHERE id=1")).fetchone()
company_info = {"name": co[0] if co else "未知", "tax_no": co[1] if co and co[1] else "未设置"}

# 月度银行流水
monthly_bt = []
for r in db.execute(text("""
    SELECT SUBSTR(transaction_date,1,7), COUNT(*),
           COALESCE(SUM(debit_amount),0), COALESCE(SUM(credit_amount),0)
    FROM bank_transactions WHERE company_id=1 GROUP BY 1 ORDER BY 1
""")).fetchall():
    monthly_bt.append({"month": r[0], "count": r[1], "outflow": float(r[2]), "inflow": float(r[3])})

# 对手方TOP20
top_cps = []
for r in db.execute(text("""
    SELECT counterparty_name, COUNT(*),
           COALESCE(SUM(debit_amount),0), COALESCE(SUM(credit_amount),0)
    FROM bank_transactions WHERE company_id=1
    GROUP BY counterparty_name ORDER BY COUNT(*) DESC LIMIT 20
""")).fetchall():
    top_cps.append({"name": r[0] or "(未命名)", "count": r[1], "outflow": float(r[2]), "inflow": float(r[3])})

# 银行分类（使用 ORM 查询，因为无 counterparty_category 列）
bt_cats = []

# 销项发票明细
si_list = []
for s in db.query(SalesInvoice).filter(SalesInvoice.company_id==cid).all():
    si_list.append({"buyer": s.buyer_name or "N/A", "invoice_no": s.invoice_no or "",
                    "amount": float(s.amount or 0), "tax": float(s.tax_amount or 0),
                    "date": str(s.invoice_date), "tax_rate": str(s.tax_rate or "")})

# 序时账科目
je_accts = []
for r in db.execute(text("""
    SELECT account_code, account_name, COUNT(*),
           COALESCE(SUM(debit_amount),0), COALESCE(SUM(credit_amount),0)
    FROM journal_entries WHERE company_id=1
    GROUP BY account_code, account_name ORDER BY account_code
""")).fetchall():
    je_accts.append({"code": r[0] or "", "name": r[1] or "", "count": r[2],
                     "debit": float(r[3]), "credit": float(r[4])})

# 进项发票
pi_list = []
for s in db.query(PurchaseInvoice).filter(PurchaseInvoice.company_id==cid).all():
    pi_list.append({"seller": s.seller_name or "N/A", "invoice_no": s.invoice_no or "",
                    "amount": float(s.amount or 0), "tax": float(s.tax_amount or 0),
                    "date": str(s.invoice_date), "tax_rate": str(s.tax_rate or "")})

# ========== [2/6] 扫描uploads ==========
print("\n[2/6] 扫描uploads目录...")
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
upload_files = []
if os.path.exists(UPLOAD_DIR):
    for fname in os.listdir(UPLOAD_DIR):
        fpath = os.path.join(UPLOAD_DIR, fname)
        if os.path.isfile(fpath) and not fname.startswith('.'):
            upload_files.append({"name": fname, "path": fpath, "size": os.path.getsize(fpath)})
print(f"  发现 {len(upload_files)} 个文件")

# ========== [3/6] 312规则引擎 ==========
print("\n[3/6] 运行312规则风险引擎...")
risk_results = []
try:
    from tax_risk import get_tax_risk_report
    t0 = time.time()
    risk_data = get_tax_risk_report(company_id=cid, period_from="2020-01", period_to="2026-12", db=db)
    t1 = time.time()
    if risk_data:
        risk_results = risk_data.get("results", [])
        high_r = sum(1 for r in risk_results if str(r.get("level","")).startswith("高"))
        mid_r = sum(1 for r in risk_results if str(r.get("level","")).startswith("中"))
        print(f"  完成({t1-t0:.1f}s): {len(risk_results)}条风险 (高{high_r}/中{mid_r})")
except Exception as e:
    print(f"  312规则引擎异常: {e}")
    import traceback; traceback.print_exc()

# ========== [4/6] 29域分析 ==========
print("\n[4/6] 运行29域分析引擎...")

# 构建分析数据
bank_txs = []
for bt in db.query(BankTransaction).filter(BankTransaction.company_id==cid).all():
    bank_txs.append({
        "date": bt.transaction_date.strftime("%Y%m%d") if hasattr(bt.transaction_date, 'strftime') else str(bt.transaction_date).replace("-", ""),
        "counterparty": bt.counterparty_name or "",
        "debit": float(bt.debit_amount or 0),
        "credit": float(bt.credit_amount or 0),
        "amount": float(bt.amount or 0) if hasattr(bt, 'amount') and bt.amount else 0,
        "summary": bt.summary or "",
        "category": ""
    })

sal_invs = []
for s in db.query(SalesInvoice).filter(SalesInvoice.company_id==cid).all():
    sal_invs.append({
        "buyer": s.buyer_name or "", "inv_no": s.invoice_no or "",
        "amount": float(s.amount or 0), "tax": float(s.tax_amount or 0),
        "date": str(s.invoice_date), "tax_rate": str(s.tax_rate or ""),
        "inv_code": s.invoice_code or ""
    })

pur_invs = []
for s in db.query(PurchaseInvoice).filter(PurchaseInvoice.company_id==cid).all():
    pur_invs.append({
        "seller": s.seller_name or "", "inv_no": s.invoice_no or "",
        "amount": float(s.amount or 0), "tax": float(s.tax_amount or 0),
        "date": str(s.invoice_date), "tax_rate": str(s.tax_rate or ""),
        "inv_code": s.invoice_code or ""
    })

invoices = [{**i, "direction": "销项"} for i in sal_invs] + [{**i, "direction": "进项"} for i in pur_invs]

vouchers = []
for je in db.query(JournalEntry).filter(JournalEntry.company_id==cid).all():
    vouchers.append({
        "date": str(je.entry_date) if je.entry_date else "",
        "summary": je.summary or "", "debit": float(je.debit_amount or 0),
        "credit": float(je.credit_amount or 0),
        "account": je.account_name or "", "account_code": je.account_code or ""
    })

salaries = []
for s in db.query(SalaryRecord).filter(SalaryRecord.company_id==cid).all():
    salaries.append({
        "name": s.employee_name or "",
        "salary": float(s.current_income or 0)
    })

social_security = []
for s in db.query(SocialSecurityDetail).all():
    social_security.append({
        "name": s.employee_name or "", "base": float(s.salary_base or 0),
        "company_amount": float(s.company_amount or 0),
        "personal_amount": float(s.personal_amount or 0),
    })

inventory = []
docs_info = [{"id": i+1, "original_name": f["name"], "size": f["size"]} for i, f in enumerate(upload_files)]

voucher_revenue = {"invoiced": 0.0, "uninvoiced": 0.0, "total": 0.0, "rows": 0}
for v in vouchers:
    acct = str(v.get("account", ""))
    if "主营业务收入" in acct:
        credit = float(v.get("credit", 0))
        if credit <= 0: continue
        summary = str(v.get("summary", ""))
        if "未开票" in summary or "无票" in summary:
            voucher_revenue["uninvoiced"] += credit
        elif "普票" in summary or "专票" in summary or "发票" in summary:
            voucher_revenue["invoiced"] += credit
        else:
            voucher_revenue["uninvoiced"] += credit
        voucher_revenue["total"] += credit
        voucher_revenue["rows"] += 1

from main import (
    _domain_bank_tracking, _domain_profit_analysis, _domain_personal_transactions,
    _domain_supplier_deep, _domain_voucher_anomaly, _domain_inventory_turnover,
    _domain_tax_consistency, _domain_salary_ss_hf_compare, _domain_invoice_lifecycle,
    _domain_contract_comparison, _domain_business_substance, _domain_invoice_deep,
    _domain_document_completeness, _domain_multi_source_cross, _domain_advanced_rules,
    _domain_voucher_invoice_revenue_compare, _domain_revenue_timeline,
    _domain_supplier_profiling, _domain_fund_flow_mapping, _domain_workforce_profiling,
    _domain_triangle_invoice_inventory_payment, _domain_red_void_invoice,
    _domain_profit_cashflow_gap, _domain_temporal_anomaly, _domain_related_party_check,
    _domain_depreciation_match, _domain_industry_benchmark,
    _domain_rule_coverage, _domain_cross_domain_reasoning
)

_has_any = len(bank_txs) + len(invoices) + len(salaries) + len(vouchers) > 0
_has_inv_or_bank = len(invoices) > 0 or len(bank_txs) > 0
_has_bank = len(bank_txs) > 0

domain_results = []

def run_domain(condition, name, fn, *args):
    if not condition:
        return
    t0 = time.time()
    try:
        findings = fn(*args)
        if not isinstance(findings, list): findings = [findings] if findings else []
    except Exception as e:
        findings = []
        import traceback
        print(f"  ⚠ {name}: {e}")
        traceback.print_exc()
    t1 = time.time()
    h = sum(1 for f in findings if str(f.get("level","")).startswith("高"))
    m = sum(1 for f in findings if str(f.get("level","")).startswith("中"))
    for f in findings:
        if "domain" not in f: f["domain"] = name
    domain_results.append({"domain": name, "findings": findings, "high": h, "mid": m, "count": len(findings)})
    elapsed = t1 - t0
    mark = " !!" if h > 0 else (" *" if m > 0 else "")
    print(f"  {name}: {len(findings)}条 H{h} M{m}{mark} ({elapsed:.1f}s)")

run_domain(True if bank_txs else False, "资金全链路追踪", _domain_bank_tracking, bank_txs)
run_domain(True if sal_invs and pur_invs else False, "进销毛利率分析", _domain_profit_analysis, sal_invs, pur_invs, inventory, voucher_revenue)
run_domain(True if sal_invs else False, "个人交易风险", _domain_personal_transactions, sal_invs)
run_domain(True if pur_invs else False, "供应商穿透分析", _domain_supplier_deep, pur_invs)
run_domain(True if vouchers else False, "凭证科目异常", _domain_voucher_anomaly, vouchers)
run_domain(True if inventory else False, "存货周转预警", _domain_inventory_turnover, inventory, sal_invs, pur_invs, bank_txs)
run_domain(True if bank_txs else False, "税务缴纳一致性", _domain_tax_consistency, bank_txs, db, cid)
run_domain(True if salaries or social_security else False, "工资社保比对", _domain_salary_ss_hf_compare, salaries, social_security)
run_domain(True if invoices else False, "发票生命周期", _domain_invoice_lifecycle, invoices)
run_domain(True if _has_any else False, "合同比对分析", _domain_contract_comparison, db, cid, sal_invs, pur_invs)
run_domain(True if _has_inv_or_bank else False, "经营实质分析", _domain_business_substance, db, cid, sal_invs, pur_invs, bank_txs, salaries)
run_domain(True if invoices else False, "发票深度特征", _domain_invoice_deep, invoices)
run_domain(True, "资料完备度评估", _domain_document_completeness, docs_info, bank_txs, sal_invs, pur_invs, salaries, social_security, vouchers, inventory)
run_domain(True if _has_any else False, "多源交叉验证", _domain_multi_source_cross, bank_txs, sal_invs, pur_invs, salaries, social_security, vouchers, inventory, db, cid)
run_domain(True if _has_any else False, "扩展审查规则", _domain_advanced_rules, bank_txs, sal_invs, pur_invs, salaries, social_security, vouchers, inventory)
run_domain(True, "凭证发票收入对比", _domain_voucher_invoice_revenue_compare, voucher_revenue, sal_invs, bank_txs)
run_domain(True if _has_any else False, "收入时间线调查", _domain_revenue_timeline, vouchers, sal_invs, bank_txs)
run_domain(True if _has_inv_or_bank else False, "供应商画像分析", _domain_supplier_profiling, pur_invs, bank_txs)
run_domain(True if _has_bank else False, "资金流向追踪", _domain_fund_flow_mapping, bank_txs, sal_invs, pur_invs)
run_domain(True if _has_any else False, "人员与业务匹配", _domain_workforce_profiling, salaries, voucher_revenue, bank_txs, social_security)
run_domain(True if _has_inv_or_bank else False, "发票存货付款三角验证", _domain_triangle_invoice_inventory_payment, pur_invs, inventory, bank_txs)
run_domain(True if invoices else False, "红冲作废发票追踪", _domain_red_void_invoice, invoices)
run_domain(True if _has_bank else False, "利润现金流矛盾检测", _domain_profit_cashflow_gap, voucher_revenue, bank_txs, pur_invs)
run_domain(True if _has_bank else False, "异常交易时间分析", _domain_temporal_anomaly, bank_txs)
run_domain(True if _has_inv_or_bank else False, "关联交易穿透检测", _domain_related_party_check, sal_invs, pur_invs, bank_txs)
run_domain(True if _has_inv_or_bank else False, "资产折旧费用匹配", _domain_depreciation_match, bank_txs, pur_invs)
run_domain(True if _has_any else False, "行业对标分析", _domain_industry_benchmark, sal_invs, pur_invs, voucher_revenue, salaries, inventory)

# 汇总 all_findings（前27域）
print("\n[5/6] 汇总all_findings并运行后2域...")
all_findings_list = []
for dr in domain_results:
    for f in dr["findings"]:
        all_findings_list.append(f)

# 后2域
t0 = time.time()
try:
    findings28 = _domain_rule_coverage(all_findings_list, bank_txs, sal_invs, pur_invs, vouchers, salaries, social_security, inventory, docs_info)
    h = sum(1 for f in findings28 if str(f.get("level","")).startswith("高"))
    m = sum(1 for f in findings28 if str(f.get("level","")).startswith("中"))
    for f in findings28: f["domain"] = "规则全覆盖验证"; all_findings_list.append(f)
    domain_results.append({"domain": "规则全覆盖验证", "findings": findings28, "high": h, "mid": m, "count": len(findings28)})
    print(f"  规则全覆盖验证: {len(findings28)}条 H{h} M{m} ({time.time()-t0:.1f}s)")
except Exception as e:
    print(f"  ⚠ 规则全覆盖验证: {e}")
    import traceback; traceback.print_exc()

t0 = time.time()
try:
    findings29 = _domain_cross_domain_reasoning(all_findings_list, bank_txs, sal_invs, pur_invs, vouchers, inventory)
    h = sum(1 for f in findings29 if str(f.get("level","")).startswith("高"))
    m = sum(1 for f in findings29 if str(f.get("level","")).startswith("中"))
    for f in findings29: f["domain"] = "跨域关联推理"; all_findings_list.append(f)
    domain_results.append({"domain": "跨域关联推理", "findings": findings29, "high": h, "mid": m, "count": len(findings29)})
    print(f"  跨域关联推理: {len(findings29)}条 H{h} M{m} ({time.time()-t0:.1f}s)")
except Exception as e:
    print(f"  ⚠ 跨域关联推理: {e}")
    import traceback; traceback.print_exc()

# ========== 汇总 ==========
total_findings = len(all_findings_list)
high_count = sum(1 for f in all_findings_list if str(f.get("level","")).startswith("高"))
mid_count = sum(1 for f in all_findings_list if str(f.get("level","")).startswith("中"))
overall = "高风险" if high_count >= 3 else ("中风险" if high_count + mid_count >= 5 else "低风险")

print(f"\n[6/6] 汇总: {total_findings}条发现, 高{high_count} 中{mid_count}, 整体{overall}")

# 按风险等级排序（高风险优先），限制200条
sorted_findings = sorted(all_findings_list, key=lambda f: (
    0 if str(f.get("level","")).startswith("高") else (1 if str(f.get("level","")).startswith("中") else 2),
    -(f.get("score", 0) or 0)
))[:200]

# 域摘要
domain_summary_out = []
for dr in domain_results:
    if dr.get("findings"):
        domain_summary_out.append({
            "name": dr["domain"], "count": dr["count"],
            "high": dr["high"], "mid": dr["mid"],
            "findings": dr["findings"]
        })

# 保存JSON
result = {
    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "company": company_info,
    "data_counts": data_counts,
    "totals": totals,
    "period_info": period_info,
    "overall": overall,
    "total_findings": total_findings,
    "high_count": high_count,
    "mid_count": mid_count,
    "domain_summary": domain_summary_out,
    "risk_results": risk_results,
    "sorted_findings": sorted_findings,
    "top_counterparties": top_cps,
    "bank_categories": bt_cats,
    "monthly_bt": monthly_bt,
    "sales_invoices": si_list,
    "purchase_invoices": pi_list,
    "je_accounts": je_accts,
    "bt_count": len(bank_txs),
    "si_count": len(sal_invs),
    "pi_count": len(pur_invs),
    "je_count": len(vouchers),
    "salary_count": len(salaries),
    "upload_files_count": len(upload_files),
}

with open("report_data.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2, default=str)

elapsed = time.time() - start_time
print(f"\n总耗时: {elapsed:.1f}s")
print(f"数据已保存: report_data.json ({os.path.getsize('report_data.json')/1024:.0f}KB)")

db.close()

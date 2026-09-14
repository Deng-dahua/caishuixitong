# -*- coding: utf-8 -*-
"""VR072/VR073/VR074 新规则验证：注册、正例触发、反例不误报、真实数据回归。"""
import json, os, glob, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
REPO = r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong"
sys.path.insert(0, REPO)
from engine.verified_rule_engine import (_scan_agri_purchase_deduction,
    _scan_travel_toll_input_tax, _scan_bank_book_consistency,
    VERIFIED_RULE_CATALOG, _SCANNERS, run_verified_rules)

spec72 = {"id": "VR072", "name": "农产品收购发票抵扣凭证合规", "required_sources": ["pur_invs"]}
spec73 = {"id": "VR073", "name": "通行费与旅客运输进项抵扣核定异常", "required_sources": ["pur_invs"]}
spec74 = {"id": "VR074", "name": "银行存款账实勾稽异常", "required_sources": ["bank_txs", "trial_balance"]}

# (0) 注册与计数
ids = {s["id"] for s in VERIFIED_RULE_CATALOG}
assert {"VR072", "VR073", "VR074"} <= ids and all(k in _SCANNERS for k in ("VR072", "VR073", "VR074"))
print(f"[0] 注册 OK；catalog={len(VERIFIED_RULE_CATALOG)}   (expect 73)")

# (1) VR072：农产品收购发票 ≥50万、无运输/存货佐证 → 触发
r1 = _scan_agri_purchase_deduction({"pur_invs": [
    {"goods": "*农产品*玉米", "amount": 600000, "tax": 54000},
    {"goods": "*农业*苗木", "amount": 100000, "tax": 9000}]}, spec72)
print(f"[1] VR072 农产品60万+货物无佐证 -> findings={len(r1)}   (expect 1)")
assert len(r1) == 1
# 反例：有运输佐证且抵扣率正常 → 不触发
r1b = _scan_agri_purchase_deduction({"pur_invs": [{"goods": "*农产品*玉米", "amount": 600000, "tax": 54000}],
                                     "transport_contracts": [{"x": 1}]}, spec72)
print(f"[1b] VR072 有运输佐证+9% -> findings={len(r1b)}   (expect 0)")
assert not r1b

# (2) VR073：税额与法定率不符 → 触发；9%/3% 正常 → 不触发
r2 = _scan_travel_toll_input_tax({"pur_invs": [
    {"goods": "*旅客运输*机票", "amount": 10000, "tax": 900},      # 9% 正常
    {"goods": "*通行费*高速公路", "amount": 10000, "tax": 300},     # 3% 正常
    {"goods": "*旅客运输*火车票", "amount": 10000, "tax": 1300}]}, spec73)  # 13% 异常
print(f"[2] VR073 一张13%异常 -> findings={len(r2)}   (expect 1)")
assert len(r2) == 1 and r2[0]["observed_metrics"]["mismatch_rows"] == 1
r2b = _scan_travel_toll_input_tax({"pur_invs": [
    {"goods": "*旅客运输*机票", "amount": 10000, "tax": 900},
    {"goods": "*通行费*高速公路", "amount": 10000, "tax": 300}]}, spec73)
print(f"[2b] VR073 全合规 -> findings={len(r2b)}   (expect 0)")
assert not r2b
# 未抵扣(tax=0)不属本规则
r2c = _scan_travel_toll_input_tax({"pur_invs": [{"goods": "*通行费*高速", "amount": 10000, "tax": 0}]}, spec73)
print(f"[2c] VR073 未抵扣票 -> findings={len(r2c)}   (expect 0)")
assert not r2c

# (3) VR074：账实不符 → 触发；相符 → 不触发
r3 = _scan_bank_book_consistency({
    "bank_txs": [{"statement_id": "A", "date": "20251231", "balance": "1000000"},
                 {"statement_id": "B", "date": "20251231", "balance": "200000"}],
    "trial_balance": [{"科目名称": "1002 银行存款", "期末余额": "500000"}]}, spec74)
print(f"[3] VR074 流水120万 vs 账面50万 -> findings={len(r3)}   (expect 1)")
assert len(r3) == 1
r3b = _scan_bank_book_consistency({
    "bank_txs": [{"statement_id": "A", "date": "20251231", "balance": "500000"}],
    "trial_balance": [{"科目名称": "1002 银行存款", "期末余额": "500000"}]}, spec74)
print(f"[3b] VR074 相符 -> findings={len(r3b)}   (expect 0)")
assert not r3b

# (4) 真实数据回归（按 pipeline 方式打 statement_id）
TR = os.path.join(REPO, "data", "uploads", "transfer")
data = {"pur_invs": [], "bank_txs": [], "trial_balance": [], "sal_invs": [], "vouchers": [],
        "salaries": [], "social_security": [], "inventory": [], "fixed_assets": [],
        "tax_declarations": [], "contracts": [], "bom": [], "transport_contracts": []}
TYPE_MAP = {"purchase_invoice": "pur_invs", "bank_statement": "bank_txs",
            "trial_balance": "trial_balance", "sales_invoice": "sal_invs", "voucher": "vouchers",
            "salary": "salaries", "social_security": "social_security", "inventory": "inventory",
            "fixed_assets": "fixed_assets", "contract": "contracts", "contract_list": "contracts",
            "transport_contract": "transport_contracts"}
DECL = {"vat_declaration", "cit_declaration", "tax_declaration", "individual_tax", "stamp_duty", "tax_payment"}
for p in sorted(glob.glob(os.path.join(TR, "*.json"))):
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    if not isinstance(d, dict):
        continue
    t = d.get("type")
    rows = [r for r in (d.get("rows") or []) if isinstance(r, dict)]
    sid = os.path.basename(p)
    if t == "bank_statement":
        for r in rows:
            r = dict(r); r["statement_id"] = sid; data["bank_txs"].append(r)
    elif t in DECL:
        data["tax_declarations"] += rows if not isinstance(d.get("declaration"), dict) else [d["declaration"]]
    elif t == "bom":
        data["bom"] += rows
    elif t in TYPE_MAP:
        data[TYPE_MAP[t]] += rows
data["declaration"] = data["tax_declarations"]
data["inventory_ledger"] = data["inventory"]
data["target_entity"] = {}; data["company_profile"] = {}
print("\n真实数据：pur_invs=%d bank_txs=%d trial_balance=%d" %
      (len(data["pur_invs"]), len(data["bank_txs"]), len(data["trial_balance"])))
for rid, fn, sp in (("VR072", _scan_agri_purchase_deduction, spec72),
                    ("VR073", _scan_travel_toll_input_tax, spec73),
                    ("VR074", _scan_bank_book_consistency, spec74)):
    res = fn(data, sp)
    print(f"[4] 真实数据 {rid} -> findings={len(res)}")
    if res:
        print("     ", json.dumps(res[0].get("observed_metrics"), ensure_ascii=False)[:300])

res = run_verified_rules(data)
ex = {e["rule_id"]: e["status"] for e in res.get("executions", [])}
print("\nrun_verified_rules 状态：VR072=%s VR073=%s VR074=%s" % (ex.get("VR072"), ex.get("VR073"), ex.get("VR074")))
print("ALL PASS")

# -*- coding: utf-8 -*-
"""接线后诊断：真实数据跑全部原子规则，对比接线前（19 条沉睡）。"""
import json, os, glob, sys, io, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
REPO = r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong"
sys.path.insert(0, REPO)
from engine.verified_rule_engine import VERIFIED_RULE_CATALOG, run_verified_rules

TR = os.path.join(REPO, "data", "uploads", "transfer")

data = {k: [] for k in ["bank_txs", "sal_invs", "pur_invs", "vouchers", "salaries",
                        "social_security", "inventory", "trial_balance", "fixed_assets",
                        "tax_declarations", "contracts", "bom", "transport_contracts"]}
TYPE_MAP = {"bank_statement": "bank_txs", "sales_invoice": "sal_invs",
            "purchase_invoice": "pur_invs", "voucher": "vouchers",
            "salary": "salaries", "social_security": "social_security",
            "inventory": "inventory", "trial_balance": "trial_balance",
            "fixed_assets": "fixed_assets", "contract": "contracts",
            "contract_list": "contracts", "transport_contract": "transport_contracts"}
DECL_TYPES = {"vat_declaration", "cit_declaration", "tax_declaration", "individual_tax",
              "stamp_duty", "tax_payment"}

for p in sorted(glob.glob(os.path.join(TR, "*.json"))):
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    if not isinstance(d, dict):
        continue
    t = d.get("type")
    rows = [r for r in (d.get("rows") or []) if isinstance(r, dict)]
    if t in DECL_TYPES:
        if isinstance(d.get("declaration"), dict):
            data["tax_declarations"].append(d["declaration"])
        else:
            data["tax_declarations"] += [{**r, "_declaration_type": t} for r in rows]
    elif t == "bom":
        data["bom"] += rows
    elif t in TYPE_MAP:
        data[TYPE_MAP[t]] += rows

# 键名对齐（与 pipeline 接线一致）
data["declaration"] = data["tax_declarations"]
data["inventory_ledger"] = data["inventory"]
data["target_entity"] = {}
data["company_profile"] = {}

print("数据源计数：")
for k in sorted(data):
    print(f"  {k}: {len(data[k]) if isinstance(data[k], list) else data[k]}")

res = run_verified_rules(data)
ex = res.get("executions", [])
cnt = collections.Counter(e.get("status") for e in ex)
print(f"\n规则执行：catalog={res.get('catalog_count')}  executions={len(ex)}")
print("状态分布：", dict(cnt))
print("形成发现（findings）：", len(res.get("findings", [])))
print("按规则 id 的发现：", sorted({f.get("rule_id") for f in res.get("findings", [])}))

still = [e for e in ex if e.get("status") == "not_run_missing_data"]
print(f"\n仍沉睡 {len(still)} 条：")
for e in still:
    print(f"  {e['rule_id']}  缺 {e.get('missing_sources')}")

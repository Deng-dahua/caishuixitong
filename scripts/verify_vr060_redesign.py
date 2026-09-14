# -*- coding: utf-8 -*-
"""VR060 重编后：真实数据跑一遍，看分层输出（公司1）。"""
import os, glob, sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
REPO = r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong"
sys.path.insert(0, REPO)
import main
from engine.pipeline import _aggregate_invoices_by_no, _dedupe_cross_file_invoices
from engine.verified_rule_engine import _scan_core_cost_fund_evidence

UP = os.path.join(REPO, "data", "uploads", "1")
data = {"pur_invs": [], "sal_invs": [], "bank_txs": [], "vouchers": [],
        "trial_balance": [], "accounts_payable": []}
for f in sorted(glob.glob(os.path.join(UP, "*"))):
    if not os.path.isfile(f):
        continue
    name = os.path.basename(f)
    ext = os.path.splitext(f)[1].lower()
    try:
        parsed = main._parse_excel_structured(f, ext, name)
    except Exception:
        continue
    if not isinstance(parsed, dict):
        continue
    ft, rows = parsed.get("type"), (parsed.get("rows") or [])
    if ft == "purchase_invoice":
        data["pur_invs"] += _aggregate_invoices_by_no(rows, "进项")
    elif ft == "sales_invoice":
        data["sal_invs"] += _aggregate_invoices_by_no(rows, "销项")
    elif ft == "bank_statement":
        for r in rows:
            if isinstance(r, dict):
                r = dict(r); r["statement_id"] = name
                data["bank_txs"].append(r)
    elif ft == "voucher":
        data["vouchers"] += rows
    elif ft == "trial_balance":
        data["trial_balance"] += rows
    elif ft == "accounts_payable":
        data["accounts_payable"] += rows

data["pur_invs"], _ = _dedupe_cross_file_invoices(data["pur_invs"])
data["sal_invs"], _ = _dedupe_cross_file_invoices(data["sal_invs"])
print("pur=%d sal=%d bank=%d vouchers=%d tb=%d ap=%d" %
      tuple(len(data[k]) for k in ("pur_invs", "sal_invs", "bank_txs", "vouchers",
                                   "trial_balance", "accounts_payable")))

spec = {"id": "VR060", "name": "主营业务成本资金与负债证据链核验",
        "required_sources": ["pur_invs", "bank_txs"]}
for f in _scan_core_cost_fund_evidence(data, spec):
    print("\n" + "─" * 70)
    print("level=%s  priority=%s  status=%s  redline=%s" %
          (f.get("level"), f.get("priority"), f.get("finding_status"), f.get("redline_id")))
    print("detail:", f.get("detail"))
    m = f.get("observed_metrics") or {}
    print("metrics:", json.dumps({k: v for k, v in m.items() if k != "items"}, ensure_ascii=False)[:800])

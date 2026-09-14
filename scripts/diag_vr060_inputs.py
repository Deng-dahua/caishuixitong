# -*- coding: utf-8 -*-
"""忠实复现 VR060 的输入：解析 data/uploads/1 全部文件 -> 聚合并分类 -> 打印未匹配清单。"""
import os, glob, sys, io, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
REPO = r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong"
sys.path.insert(0, REPO)
import main
from engine.pipeline import _aggregate_invoices_by_no, _dedupe_cross_file_invoices
from engine.main_biz_cost import identify_main_biz_cost
from engine.fund_matching import classify_core_cost_payment

UP = os.path.join(REPO, "data", "uploads", "1")
pur, sal, bank = [], [], []
for f in sorted(glob.glob(os.path.join(UP, "*"))):
    if not os.path.isfile(f):
        continue
    name = os.path.basename(f)
    ext = os.path.splitext(f)[1].lower()
    try:
        parsed = main._parse_excel_structured(f, ext, name)
    except Exception as e:
        print("解析失败", name, e)
        continue
    if not isinstance(parsed, dict):
        continue
    ft = parsed.get("type")
    rows = parsed.get("rows") or []
    if ft == "purchase_invoice":
        pur += _aggregate_invoices_by_no(rows, "进项")
    elif ft == "sales_invoice":
        sal += _aggregate_invoices_by_no(rows, "销项")
    elif ft == "bank_statement":
        for r in rows:
            if isinstance(r, dict):
                r = dict(r); r["statement_id"] = name
                bank.append(r)

print(f"pur_invs={len(pur)}  sal_invs={len(sal)}  bank={len(bank)}")
pur, _d1 = _dedupe_cross_file_invoices(pur)
sal, _d2 = _dedupe_cross_file_invoices(sal)
print(f"跨文件去重：进项剔除 {_d1} 行、销项剔除 {_d2} 行 -> pur={len(pur)} sal={len(sal)}")
print("三顾行行数:", sum(1 for r in pur if "三顾行" in str(r.get("seller") or "")),
      [ (r.get('inv_no'), r.get('amount')) for r in pur if '三顾行' in str(r.get('seller') or '')])

cls = identify_main_biz_cost(pur, sal)
core = cls.get("core_cost_invs") or []
evid = classify_core_cost_payment(core, bank)
t = evid["totals"]
print("\n核心成本合计", t.get("total"), "| 未匹配", t.get("unpaid"), "| 对公", t.get("company_paid"))
print("报告值      核心成本 3960319.06 | 未匹配 350651.47 | 对公 2342059.71")
print("\n未匹配（按金额降序，前 12）:")
for e in sorted(evid["unpaid"], key=lambda x: -abs(float(x["row"].get("amount") or 0)))[:12]:
    r = e["row"]
    print(f"   {str(r.get('seller'))[:26]:28} {r.get('amount'):>12}  date={str(r.get('date'))[:10]}  inv_no={str(r.get('inv_no'))[:22]} mode={e.get('pay_mode')}")

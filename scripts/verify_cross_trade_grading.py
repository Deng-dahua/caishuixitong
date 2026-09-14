# -*- coding: utf-8 -*-
"""进销双向（循环开票）分级端到端核验（2026-09-14 纠偏后）。

确认三件事：
  ① 供应链穿透 / 关联方图谱：只有同额对开、或购销品名无关且金额重大才出结论；
  ② 进项章（input_voucher）与虚开章（false_invoice）：metrics 给出分级计数，
     行业常态的双向往来不再被写成「自循环/对开嫌疑」；
  ③ 稽查询问提纲（inspection_questions）：常态双向降为「低」级列示，不作嫌疑询问。

用法：python scripts/verify_cross_trade_grading.py [company_id ...]
"""
import os, sys, io, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
REPO = r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong"
sys.path.insert(0, REPO)
import main
from engine.pipeline import _aggregate_invoices_by_no, _dedupe_cross_file_invoices
from engine.domain_analysis import classify_cross_direction
from engine.input_voucher import run_input_voucher_check
from engine.false_invoice import run_false_invoice_check
from engine.inspection_questions import run_inspection_questions

COMPANIES = {"1": "深圳海更数字传媒有限公司", "3": "北京桦橙佳业商贸有限公司"}


def load(cid):
    up = os.path.join(REPO, "data", "uploads", cid)
    pur, sal = [], []
    for f in sorted(glob.glob(os.path.join(up, "*"))):
        if not os.path.isfile(f):
            continue
        ext = os.path.splitext(f)[1].lower()
        try:
            p = main._parse_excel_structured(f, ext, os.path.basename(f))
        except Exception:
            continue
        if not isinstance(p, dict):
            continue
        if p.get("type") == "purchase_invoice":
            pur += _aggregate_invoices_by_no(p.get("rows") or [], "进项")
        elif p.get("type") == "sales_invoice":
            sal += _aggregate_invoices_by_no(p.get("rows") or [], "销项")
    pur, _ = _dedupe_cross_file_invoices(pur)
    sal, _ = _dedupe_cross_file_invoices(sal)
    return pur, sal


for cid in (sys.argv[1:] or list(COMPANIES)):
    name = COMPANIES.get(cid, "公司" + cid)
    pur, sal = load(cid)
    print("=" * 78)
    print(f"公司{cid} {name}：进项 {len(pur)} 笔 / 销项 {len(sal)} 笔")

    invs = ([dict(r, direction="进项") for r in pur]
            + [dict(r, direction="销项") for r in sal])
    cd = classify_cross_direction(invs)
    print("-" * 78)
    print("【对开分级】mirror=%d unrelated=%d normal=%d"
          % (len(cd["mirror"]), len(cd["unrelated"]), len(cd["normal"])))
    for k in ("mirror", "unrelated", "normal"):
        for i in cd[k]:
            print("  [%s] %s 采购%.2f/销售%.2f 比值%.0f%% 进%s 销%s"
                  % (k, i["name"][:24], i["purchase"], i["sale"], i["ratio"] * 100,
                     i["purchase_cats"], i["sale_cats"]))

    iv = run_input_voucher_check(pur, sal_invs=sal, company_name=name)
    m1 = (iv or {}).get("metrics") or {}
    fi = run_false_invoice_check(sal, pur, company_name=name)
    m2 = (fi or {}).get("metrics") or {}
    print("-" * 78)
    print("【进项章 metrics】circular_supplier_count=%s mirror=%s unrelated=%s"
          % (m1.get("circular_supplier_count"), m1.get("circular_mirror_count"),
             m1.get("circular_unrelated_count")))
    print("【虚开章 metrics】circular_supplier_count=%s mirror=%s unrelated=%s"
          % (m2.get("circular_supplier_count"), m2.get("circular_mirror_count"),
             m2.get("circular_unrelated_count")))
    for tag, res in (("进项章", iv), ("虚开章", fi)):
        sigs = (res or {}).get("signals") or []
        for s in sigs:
            if "自循环" in str(s.get("signal", "")) or "对开" in str(s.get("signal", "")) \
                    or "品名无关" in str(s.get("signal", "")):
                print(f"  [{tag} signal] {s.get('signal')}")

    qs = run_inspection_questions(
        comprehensive={"input_voucher": iv, "false_invoice": fi}, company_name=name)
    themes = (qs or {}).get("themes") or []
    print("-" * 78)
    print("【询问提纲·双向相关】")
    hit = 0
    for t in themes:
        th = str(t.get("theme") or "")
        if any(k in th for k in ("自循环", "双向", "对开")):
            hit += 1
            print("  [%s] %s" % (t.get("severity"), th))
            for q in (t.get("questions") or [])[:2]:
                print("      ", str(q.get("question") or "")[:180])
    if not hit:
        print("   （无双向相关询问 → 未发现对开特征，符合预期）")
print("=" * 78)

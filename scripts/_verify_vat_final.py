# -*- coding: utf-8 -*-
"""VAT 申报表最终验收：按法定公式复核（含上期留抵 + 期末留抵滚动）。"""
import os, sys, glob, re
REPO = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(REPO)
sys.path.insert(0, REPO)
import main

files = sorted(glob.glob(os.path.join(REPO, "data/trash/1_29[5-9]_*.pdf")) +
               glob.glob(os.path.join(REPO, "data/trash/1_30[0-6]_*.pdf")))


def row_val(fp, label, col=6):
    """从申报表原始行取指定列的数值（仅用于验收复核）。"""
    _, rows = main._extract_pdf_tables(fp)
    for r in rows:
        if r and label in str(r[1] if len(r) > 1 else ""):
            s = str(r[col] if col < len(r) else "").strip()
            if re.fullmatch(r"-?[\d,，.]+", s):
                return float(s.replace(",", "").replace("，", ""))
    return None


print("%-8s %12s %11s %11s %11s %11s %11s" % ("所属期", "销售额", "销项税额", "进项税额", "上期留抵", "应补税额", "期末留抵"))
print("-" * 82)
ok = bad = 0
prev_liu = 0.0
for fp in files:
    d = main._parse_pdf_generic(fp, os.path.basename(fp)).get("declaration", {})
    p = d.get("period", "?")
    sa, st, it, pt = (d.get("sales_amount", 0) or 0, d.get("sales_tax", 0) or 0,
                      d.get("input_tax", 0) or 0, d.get("payable_tax", 0) or 0)
    # 法定公式：应抵扣合计 = 进项 + 上期留抵；实际抵扣 = min(应抵扣合计, 销项)
    #           应纳税额 = 销项 - 实际抵扣；期末留抵 = 应抵扣合计 - 实际抵扣
    due = it + prev_liu
    actual = min(due, st)
    exp_pay = round(st - actual, 2)
    exp_liu = round(due - actual, 2)
    sheet_liu = row_val(fp, "期初留抵税额") or row_val(fp, "上期留抵税额")
    pay_ok = abs(pt - exp_pay) < 0.02
    tax_ok = abs(st - sa * 0.06) < 1.5
    ok, bad = (ok + 1, bad) if (pay_ok and tax_ok) else (ok, bad + 1)
    print("%-8s %12s %11s %11s %11s %11s %11s  %s" % (
        p, f"{sa:,.2f}", f"{st:,.2f}", f"{it:,.2f}",
        f"{prev_liu:,.2f}", f"{pt:,.2f}", f"{exp_liu:,.2f}",
        "OK" if (pay_ok and tax_ok) else "×"))
    prev_liu = exp_liu

print("-" * 82)
print("按法定公式复核： %d/12 通过，%d 异常" % (ok, bad))

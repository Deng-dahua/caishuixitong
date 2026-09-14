# -*- coding: utf-8 -*-
"""验证修好：① 取票文件解析出票号（数电发票号码回填 inv_no）；② 同票号重复行不再放大。"""
import glob, os, sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
REPO = r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong"
sys.path.insert(0, REPO)
import main
from engine.pipeline import _aggregate_invoices_by_no

files = sorted(glob.glob(os.path.join(REPO, "data", "uploads", "1", "*取票*.xlsx")))
print("取票文件:", [os.path.basename(f) for f in files])

rows = []
for f in files:
    parsed = main._parse_excel_structured(f, ".xlsx", os.path.basename(f))
    if isinstance(parsed, dict):
        rows += [r for r in (parsed.get("rows") or []) if isinstance(r, dict)]
print(f"\n解析总行数 {len(rows)}")
with_no = sum(1 for r in rows if str(r.get("inv_no") or "").strip())
print(f"有票号的行 {with_no} / {len(rows)}   (修前应为 0)")
assert with_no > 0, "票号仍未解析出来"
print("样例票号:", [r.get("inv_no") for r in rows[:3]])

raw_total = sum(abs(float(r.get("amount") or 0)) for r in rows)
agg = _aggregate_invoices_by_no(rows, "进项")
agg_total = sum(abs(float(r.get("amount") or 0)) for r in agg)
print(f"\n明细行合计 {raw_total:,.2f}  →  按票号聚合去重后 {agg_total:,.2f}   (减少 {raw_total-agg_total:,.2f})")
assert agg_total < raw_total, "去重未生效"

# 三顾行那张票：应只计一次
sg = [r for r in agg if "三顾行" in str(r.get("seller") or "")]
print("\n西安三顾行聚合后:", [(r.get("inv_no"), r.get("amount")) for r in sg])
assert len(sg) == 1 and abs(float(sg[0]["amount"]) - 85049.5) < 0.01, sg

# 统计重复行数量（同票号 + 同签名）
from collections import Counter
c = Counter()
for r in rows:
    inv = str(r.get("inv_no") or "")
    if not inv:
        continue
    c[(inv, str(r.get("goods")), str(r.get("amount")), str(r.get("tax")), str(r.get("total")))] += 1
dups = sum(v - 1 for v in c.values() if v > 1)
print(f"\n完全重复的明细行（同票号+同货物+同额）: {dups} 行，涉及金额 "
      f"{sum(abs(float(k[2])) * (v-1) for k, v in c.items() if v > 1):,.2f}")
print("ALL PASS")

# -*- coding: utf-8 -*-
"""只读探针：在真实账套上核对「银行收款性质」分类与收入口径。

背景：报告把「全部贷方 8,371,659.92」当收入去比开票额，差额被读成隐匿未开票收入。
本脚本核对：按收款性质拆开后，经营性收款是多少、非经营性剔除了什么、还有多少待判定。
"""
import json
import os
import sys
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "scripts"))

from engine.bank_nature import classify_receipts, income_scope_note_with_undetermined_rows  # noqa: E402
from _audit_unfired_redlines import _TYPE2KEY  # noqa: E402

CID = int(sys.argv[1]) if len(sys.argv) > 1 else 1
P = os.path.join(BASE, "scripts", "four_reports", "company_%d_full.json" % CID)

d = json.load(open(P, encoding="utf-8"))
bank, sal = [], []
for f in (d.get("file_results") or []):
    key = _TYPE2KEY.get(str(f.get("type") or ""))
    if key == "bank_txs":
        bank.extend(f.get("_rows") or [])
    elif key == "sal_invs":
        sal.extend(f.get("_rows") or [])

from engine.numparse import to_number  # noqa: E402
inv_total = sum(to_number(i.get("total") or i.get("amount") or 0) for i in sal)

res = classify_receipts(bank)
print("银行行数 %d | 贷方笔数 %d" % (len(bank), res["rows"]))
if bank:
    print("样例键:", sorted(bank[0].keys()))
print("全部贷方合计   %15.2f" % res["total"])
print("经营性收款     %15.2f" % res["operating"])
print("非经营性收款   %15.2f" % res["non_operating"])
print("待判定收款     %15.2f" % res["undetermined"])
print("销项开票合计   %15.2f" % inv_total)
print("—— 旧口径差额(全部贷方-开票) %+.2f" % (res["total"] - inv_total))
print("—— 新口径差额(经营收款-开票) %+.2f" % (res["operating"] - inv_total))
print("分类明细：")
for lab, v in sorted(res["by_label"].items(), key=lambda kv: -kv[1]["amount"]):
    print("   %-16s %-6s %15.2f  (%d笔)" % (lab, v["nature"], v["amount"], v["count"]))
print("纠错留痕 %d 条" % len(res["corrections"]))
for c in res["corrections"][:5]:
    print("   ", c)
print("口径说明：")
print(income_scope_note_with_undetermined_rows(res))

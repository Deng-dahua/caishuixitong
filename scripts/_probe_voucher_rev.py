# -*- coding: utf-8 -*-
"""只读探针：核对「凭证主营业务收入」为何被算成 0.00。

报告写「凭证主营业务收入0.00元（开票0.00+未开票0.00）」，而同页明细表却有一行
「主营业务收入/服务收入 37,735.85」。二者必有一个是错的。
"""
import json
import os
import sys
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "scripts"))

from engine.numparse import to_number  # noqa: E402
from _audit_unfired_redlines import _TYPE2KEY  # noqa: E402

CID = int(sys.argv[1]) if len(sys.argv) > 1 else 1
d = json.load(open(os.path.join(BASE, "scripts", "four_reports", "company_%d_full.json" % CID), encoding="utf-8"))
vouchers = []
for f in (d.get("file_results") or []):
    if _TYPE2KEY.get(str(f.get("type") or "")) == "vouchers":
        vouchers.extend(f.get("_rows") or [])

print("凭证行数", len(vouchers))
if vouchers:
    print("样例键:", sorted(vouchers[0].keys()))
    print("样例行:", json.dumps(vouchers[0], ensure_ascii=False)[:300])

# 旧口径：account 含"主营业务收入" 且 credit>0
old_total = 0.0
old_rows = 0
acct_hits = defaultdict(lambda: {"credit": 0.0, "debit": 0.0, "n": 0})
for v in vouchers:
    acct = str(v.get("account") or v.get("科目") or v.get("account_name") or "")
    if "主营业务收入" in acct or "6001" in acct:
        acct_hits[acct[:30]]["credit"] += to_number(v.get("credit", 0))
        acct_hits[acct[:30]]["debit"] += to_number(v.get("debit", 0))
        acct_hits[acct[:30]]["n"] += 1
print("命中(含主营/6001)的科目：")
for k, v in sorted(acct_hits.items(), key=lambda kv: -kv[1]["credit"]):
    print("   %-32s 贷%14.2f 借%14.2f (%d行)" % (k, v["credit"], v["debit"], v["n"]))

# 找所有"收入"类科目
inc = defaultdict(lambda: {"credit": 0.0, "debit": 0.0, "n": 0})
for v in vouchers:
    acct = str(v.get("account") or v.get("科目") or "")
    if "收入" in acct:
        inc[acct[:34]]["credit"] += to_number(v.get("credit", 0))
        inc[acct[:34]]["debit"] += to_number(v.get("debit", 0))
        inc[acct[:34]]["n"] += 1
print("含「收入」字样的科目（前12）：")
for k, v in sorted(inc.items(), key=lambda kv: -kv[1]["credit"])[:12]:
    print("   %-34s 贷%14.2f 借%14.2f (%d行)" % (k, v["credit"], v["debit"], v["n"]))

# 金额字段可用性
amt_keys = ("amount", "金额", "credit", "贷方", "debit", "借方", "发生额")
for k in amt_keys:
    n = sum(1 for v in vouchers if v.get(k) not in (None, "", 0, "0"))
    print("字段 %-6s 非空行数 %d" % (k, n))

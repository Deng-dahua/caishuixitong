# -*- coding: utf-8 -*-
"""只读探针：销项发票 ↔ 公账收款 的双向差集，按会计实质分流。

用户质询：
 ①「是不是有开票未收款的应收账款，是不是有收款未开票的预收账款？」
 ②「如果你是老板，你会傻逼到未开票收入用公司公账来收款吗？」
  → 公账收款＝留痕。要隐匿的人走个人卡/现金/平台个人账户。
  → 故"公账收款>开票"的第一解释是预收账款/往来款/代收代付，
    不能直接读成"隐匿未开票收入"。
"""
import json
import os
import sys
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "scripts"))

from engine.numparse import to_number                                   # noqa: E402
from engine.verified_rule_engine import _is_round_amount                 # noqa: E402
from _audit_unfired_redlines import _TYPE2KEY                            # noqa: E402

CID = int(sys.argv[1]) if len(sys.argv) > 1 else 1
d = json.load(open(os.path.join(BASE, "scripts", "four_reports", "company_%d_full.json" % CID), encoding="utf-8"))
rows = defaultdict(list)
for f in (d.get("file_results") or []):
    k = _TYPE2KEY.get(str(f.get("type") or ""))
    if k:
        rows[k].extend(f.get("_rows") or [])

sal, vouchers = rows["sal_invs"], rows["vouchers"]
inv_incl = sum(to_number(i.get("total") or i.get("amount") or 0) for i in sal)   # 价税合计
inv_excl = sum(to_number(i.get("amount") or 0) for i in sal)                     # 不含税
print("销项发票：价税合计 = {:,.2f} | 张数 = {}".format(inv_incl, len(sal)))
print("         不含税额 ≈ {:,.2f}".format(inv_excl))

# ── 序时账关键科目（按科目名取，唯一权威 fieldkit.account_label）──
from engine.fieldkit import account_label  # noqa: E402
buckets = defaultdict(lambda: {"debit": 0.0, "credit": 0.0, "n": 0, "names": set()})
WATCH = {
    "主营业务收入": ("收入",),
    "应收账款": ("应收",),
    "预收账款": ("预收",),
    "合同负债": ("合同负债",),
    "应收票据": ("应收票据",),
    "其他应收款": ("其他应收",),
    "其他应付款": ("其他应付",),
    "库存现金": ("库存现金",),
    "银行存款": ("银行存款",),
}
for v in vouchers:
    acct = account_label(v)
    for key, kws in WATCH.items():
        if any(k in acct for k in kws):
            b = buckets[acct if len(acct) < 30 else acct[:30]]
            b["debit"] += to_number(v.get("debit", 0))
            b["credit"] += to_number(v.get("credit", 0))
            b["n"] += 1
            break
print()
print("{:<34}{:>16}{:>16}{:>6}".format("科目", "借方发生额", "贷方发生额", "行数"))
for k, b in sorted(buckets.items(), key=lambda kv: -(kv[1]["debit"] + kv[1]["credit"])):
    print("{:<34}{:>16,.2f}{:>16,.2f}{:>6}".format(k, b["debit"], b["credit"], b["n"]))

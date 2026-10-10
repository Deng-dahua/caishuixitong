# -*- coding: utf-8 -*-
"""只读探针：在真实链路上取证 —— (1) 凭证行字段契约；(2) 012 通道命中量化。不写任何文件。"""
import sys, os, json
ROOT = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(ROOT); sys.path.insert(0, ROOT)

import engine.verified_rule_engine as vre

_captured = {}
_orig = vre.run_verified_rules


def _patched(data, *a, **kw):
    _captured["vouchers"] = data.get("vouchers") or []
    _captured["social_security"] = data.get("social_security") or []
    _captured["salaries"] = data.get("salaries") or []
    return _orig(data, *a, **kw)


vre.run_verified_rules = _patched
try:
    import engine.output_governance as og
    og.run_verified_rules = _patched
except Exception:
    pass

import main
from database import SessionLocal
db = SessionLocal()
try:
    main._execute_tax_risk_analysis(1, db)
finally:
    db.close()

vs = _captured.get("vouchers") or []
print("=== vouchers rows:", len(vs))
if vs:
    keys = {}
    for v in vs:
        for k in v:
            keys[k] = keys.get(k, 0) + 1
    print("keys:", json.dumps(keys, ensure_ascii=False))
    print("sample:", json.dumps(vs[:3], ensure_ascii=False))

# ── 012 通道量化：同一凭证内「存货类科目贷方」×「对外投资/利润分配借方」──
INV = ["库存商品", "产成品", "库存材料", "原材料", "自制半成品", "周转材料",
       "发出商品", "委托加工物资", "材料采购", "受托代销商品", "商品"]
INVD = ["长期股权投资", "对外投资", "交易性金融资产", "其他权益工具投资",
        "债权投资", "其他非流动金融资产"]
DIST = ["利润分配", "未分配利润", "应付股利", "应付利润"]
from collections import defaultdict
by = defaultdict(list)
for v in vs:
    vn = str(v.get("voucher_no") or "").strip()
    if vn:
        by[(str(v.get("month_no") or ""), vn)].append(v)

hits = []
for key, lines in by.items():
    ic = []
    idd = []
    ot = False
    for ln in lines:
        a = str(ln.get("account_name") or ln.get("account") or "")
        cr = vre._number(ln.get("credit"))
        dr = vre._number(ln.get("debit"))
        if any(k in a for k in INV) and cr > 0:
            ic.append((a, cr))
        if any(k in a for k in INVD + DIST) and dr > 0:
            idd.append((a, dr))
        if "销项税额" in a or "应交增值税" in a:
            ot = True
    if ic and idd and not ot:
        hits.append((key, ic, idd))
print("=== 012通道命中凭证:", len(hits))
for h in hits[:20]:
    print("  ", h)

# 存货科目在真实数据里是否存在
inv_accts = sorted({str(v.get("account_name") or "") for v in vs
                    if any(k in str(v.get("account_name") or "") for k in INV)})
print("=== 真实数据中的存货类科目:", inv_accts[:20])

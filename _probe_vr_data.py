# -*- coding: utf-8 -*-
"""只读探针：实测 VR 引擎收到的**全部数据键**规模与字段（决定 6 条待建红线能否建真检测器）。不写文件。"""
import sys, os, json
ROOT = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(ROOT); sys.path.insert(0, ROOT)

import engine.verified_rule_engine as vre

_cap = {}
_orig = vre.run_verified_rules


def _patched(data, *a, **kw):
    _cap["data"] = data
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

d = _cap.get("data") or {}
# ★ 落盘快照，供离线反复分析（避免每次 3 分钟重跑）
try:
    _snap = {k: v for k, v in d.items()}
    with open(os.path.join(ROOT, "_vr_data_snapshot.json"), "w", encoding="utf-8") as f:
        json.dump(_snap, f, ensure_ascii=False, default=str)
    print("[已落盘] _vr_data_snapshot.json")
except Exception as _e:
    print("[落盘失败]", _e)

print("=== VR 数据键规模（非空者标 *）===")
for k in sorted(d):
    v = d[k]
    if isinstance(v, list):
        print("  %-24s list  n=%d %s" % (k, len(v), "*" if v else ""))
    elif isinstance(v, dict):
        print("  %-24s dict  keys=%d %s" % (k, len(v), "*" if v else ""))
    else:
        print("  %-24s %s %r" % (k, type(v).__name__, str(v)[:60]))


def _fields(name):
    v = d.get(name)
    if isinstance(v, list) and v and isinstance(v[0], dict):
        ks = {}
        for it in v:
            for kk in it:
                ks[kk] = ks.get(kk, 0) + 1
        print("  %s 字段: %s" % (name, json.dumps(ks, ensure_ascii=False)[:400]))
        print("  %s 样例: %s" % (name, json.dumps(v[0], ensure_ascii=False)[:400]))


print("\n=== 关键键字段 ===")
for n in ["salaries", "social_security", "bank_txs", "trial_balance", "tax_declarations",
          "declaration", "pur_invs", "sal_invs", "contracts", "fixed_assets",
          "accounts_payable", "accounts_receivable", "inventory_ledger", "inventory",
          "company_profile", "target_entity"]:
    print("---", n)
    _fields(n)

# ── 针对 6 条红线的关键信号探测 ──
vs = d.get("vouchers") or []
def _accts(kw):
    return sorted({str(v.get("account_name") or "") for v in vs if any(k in str(v.get("account_name") or "") for k in kw)})

print("\n=== 6 条红线信号探测 ===")
print("[CIT-009 关联方借款/利息] 科目:", _accts(["借款", "利息", "财务费用", "长期借款", "短期借款"])[:20])
print("[INV-004 进项转出] 科目:", _accts(["进项税额转出", "待认证", "应交税费"])[:20])
print("[SPT-011 核定征收] 申报表字段探测:", json.dumps(
    (d.get("tax_declarations") or [{}])[0], ensure_ascii=False)[:300] if d.get("tax_declarations") else "(空)")
print("[SPT-013 劳务报酬/灵活用工] 科目:", _accts(["劳务", "服务费", "佣金", "灵活用工", "稿酬"])[:20])
bs = d.get("bank_txs") or []
ind = [t for t in bs if isinstance(t, dict) and str(t.get("counterparty") or t.get("对方户名") or "") and
       any(x in str(t.get("summary") or t.get("摘要") or "") for x in ["劳务", "工资", "报酬", "佣金"])]
print("[SPT-013/Pay-003] 银行流水劳务/工资类笔数:", len(ind))

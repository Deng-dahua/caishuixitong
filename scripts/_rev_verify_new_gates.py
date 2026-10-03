# -*- coding: utf-8 -*-
"""反向验证：故意破坏产品，两道新闸门必须变红（否则闸门是假的）。"""
import sys
sys.path.insert(0, 'tools')
import audit_consistency as A

ok = True

# ① 收款性质闸门：让 classify_receipts 把全部贷方当经营性收款（复现旧口径）
import engine.bank_nature as bn
_orig_cls = bn.classify_receipts

def _bad(data):
    r = _orig_cls(data)
    r["operating"] = r["total"]      # 旧口径：全部贷方＝收入
    return r

bn.classify_receipts = _bad
try:
    res = A.check_bank_receipt_nature_single_source()
finally:
    bn.classify_receipts = _orig_cls
hit = any(x[0] == "ERROR" for x in res)
print("[反向①] 旧口径复现 → 闸门判定:", res)
print("        期望 ERROR，实测", "ERROR(通过)" if hit else "未报错(闸门失效!)")
ok = ok and hit

# ② 科目字段闸门：让 account_name 返回科目编码（复现旧实现）
import engine.fieldkit as fk
_orig_an = fk.account_name
fk.account_name = lambda row: str((row or {}).get("account") or "")
try:
    res2 = A.check_voucher_account_field()
finally:
    fk.account_name = _orig_an
hit2 = any(x[0] == "ERROR" for x in res2)
print("[反向②] 科目名读成编码 → 闸门判定:", res2)
print("        期望 ERROR，实测", "ERROR(通过)" if hit2 else "未报错(闸门失效!)")
ok = ok and hit2

print("\n结论:", "两道闸门均能变红（有效）" if ok else "有闸门失效")
sys.exit(0 if ok else 2)

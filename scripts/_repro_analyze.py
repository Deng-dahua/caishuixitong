# -*- coding: utf-8 -*-
"""复现「一键分析失败（分析异常）」，打印真实异常与 traceback。

`_execute_tax_risk_analysis` 把任何异常 catch 成 {"ok":False,"message":"分析异常: ..."}，
故必须在这里原样打印 message + traceback 才能定位。
"""
import os
import sys
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ.setdefault("APP_COOKIE_SECURE", "0")

import main  # noqa: E402

from database import SessionLocal  # noqa: E402
from request_context import set_current_user_id  # noqa: E402

COMPANY = int(os.environ.get("REPRO_COMPANY", "1"))

set_current_user_id(1)  # 必须为 int（request_context 会 int() 转换）
db = SessionLocal()
try:
    res = main._execute_tax_risk_analysis(COMPANY, db)
finally:
    db.close()

print("=" * 70)
print("ok =", res.get("ok"))
print("message =", str(res.get("message"))[:400])
if not res.get("ok"):
    print("-" * 70)
    print(res.get("traceback") or "(无 traceback)")
    print("-" * 70)
else:
    rep = res.get("report") or {}
    print("overall_level =", rep.get("overall_level"))
    print("total_risks   =", rep.get("total_risks"))
print("=" * 70)
sys.exit(0 if res.get("ok") else 1)

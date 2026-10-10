# -*- coding: utf-8 -*-
"""临时：跑 company 2 和 3，确认新红线接线无回归（C4 因 .xls 不可读历史排除）。"""
import sys, os
ROOT = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import run_companies as r
for cid in (2, 3):
    try:
        ok = r.run_one(cid)
        print(f"COMPANY{cid}_OK=", ok, flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"COMPANY{cid}_OK=False", flush=True)
print("C23 DONE")

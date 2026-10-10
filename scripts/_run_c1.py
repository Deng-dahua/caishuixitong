# -*- coding: utf-8 -*-
"""临时：只跑 company 1，快速确认无崩溃 + 新红线接线。"""
import sys, os
ROOT = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import run_companies as r
try:
    ok = r.run_one(1)
    print("COMPANY1_OK=", ok)
except Exception as e:
    import traceback
    traceback.print_exc()
    print("COMPANY1_OK=False")

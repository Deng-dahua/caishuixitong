# -*- coding: utf-8 -*-
"""仅跑公司1全量分析，验证收入真实性能力接入后不崩溃（临时核验脚本）。"""
import sys, os

ROOT = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import scripts.run_four_companies as R

R.run_one(1)

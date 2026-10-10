# -*- coding: utf-8 -*-
"""采集「跨疑点去重（report_pipeline.dedup_report_data）执行前」的报告快照。

用途（P0-2 的 A/B 取证）：把去重前的真实输入落盘，之后可在**同一输入**上
对比"旧去重"与"新去重"的效果，排除输入差异导致的假对比。

做法：monkeypatch `engine.report_pipeline.dedup_report_data`，在真正执行前把
入参深拷一份写盘；**不改变任何业务行为**（仍然照常执行原函数）。
"""
import sys, os, json, traceback

ROOT = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import engine.report_pipeline as rp
from runtime_storage import atomic_write_json

_orig = rp.dedup_report_data
SNAP = os.path.join(ROOT, "scripts", "four_reports", "_pre_dedup_snapshot.json")
_state = {"n": 0}


def _patched(report_data, *, rules=None):
    _state["n"] += 1
    try:
        import copy
        snap = copy.deepcopy(report_data)
        atomic_write_json(SNAP, snap, indent=None)
        print("[SNAP] 已写去重前快照 %s（第 %d 次调用）" % (SNAP, _state["n"]), flush=True)
    except Exception as e:  # noqa: BLE001
        print("[SNAP] 快照失败：%s" % e, flush=True)
        traceback.print_exc()
    return _orig(report_data, rules=rules)


rp.dedup_report_data = _patched

import main  # noqa: E402
from database import SessionLocal, Company  # noqa: E402

db = SessionLocal()
try:
    ids = [int(r.id) for r in db.query(Company.id).order_by(Company.id).all()]
    print("将分析：%r" % ids, flush=True)
    for cid in ids:
        res = main._execute_tax_risk_analysis(cid, db)
        lv = (res or {}).get("overall_level") if isinstance(res, dict) else None
        print("[DONE] company %s overall_level=%r" % (cid, lv), flush=True)
        break   # 只需 company_1 的快照
finally:
    db.close()

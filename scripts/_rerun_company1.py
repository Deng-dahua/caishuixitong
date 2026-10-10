# -*- coding: utf-8 -*-
"""只重跑 **company_1** 并落盘终极产物（不改动 2/3/4 的既有产物）。

为什么单独写：`scripts/run_companies.py` 的 `COMPANY_IDS` 是硬编码 4 家，
跑它会顺带覆盖 company_2/3/4（那三家本轮不在范围内）。本脚本只做 company_1，
`_to_json_safe` 与落盘格式与 `run_companies.py` **完全一致**（同一实现，薄转发）。

用法：
    ./.venv/Scripts/python.exe scripts/_rerun_company1.py
"""
import io
import json
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import main                                                        # noqa: E402
from database import SessionLocal, Company                          # noqa: E402
from runtime_storage import _to_json_safe, atomic_write_json           # noqa: E402

OUT = os.path.join(ROOT, "scripts", "four_reports")
CID = 1


def main_():
    db = SessionLocal()
    try:
        co = db.query(Company).filter(Company.id == CID).first()
        name = co.name if co else "company_%d" % CID
        print("===== COMPANY %d: %s =====" % (CID, name), flush=True)
        result = main._execute_tax_risk_analysis(CID, db)
        if isinstance(result, dict) and "report" in result:
            report = result["report"]
        elif isinstance(result, dict):
            report = result
        else:
            report = None
        if not isinstance(report, dict):
            print("[FATAL] report 不是 dict：%r" % type(report), flush=True)
            return 2
        # ★ 崩溃判据（与本项目既有约定一致）：顶层 overall_level 为 {"ok": false} 即崩
        _lv = report.get("overall_level")
        if isinstance(_lv, dict) and _lv.get("ok") is False:
            print("[FATAL] 顶层 overall_level = %r ⇒ 本轮分析崩溃" % (_lv,), flush=True)
            return 3
        er = report.get("enterprise_readable_report") or {}
        probs = er.get("confirmed_problems") or []
        # ★ 原子落盘：走**唯一落盘实现** `atomic_write_json`（fsync + 原子替换）。
        #   旧写法直接覆盖正式产物，一旦磁盘写满/进程中断，**正式产物会被截断**
        #   （本轮实测踩过：产物被截成 3110 字节、只剩 4 个键）。
        _lv_pre = _lv if not isinstance(_lv, dict) else str(_lv)[:60]
        dst = os.path.join(OUT, "company_%d_full.json" % CID)
        atomic_write_json(dst, report, indent=1)
        print("[OK] overall_level=%s  total_risks=%s  confirmed_problems=%s"
              % (_lv_pre, report.get("total_risks"), len(probs)), flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        print("[ERROR] company %d: %s" % (CID, exc), flush=True)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main_())

# -*- coding: utf-8 -*-
"""复现「一键分析卡在 99%」——本地跑全量 pipeline 并打点，定位卡死位置。

用法（必须托管 venv，因为要 import main / fastapi）：
    C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe scripts/_repro_99.py 1
"""
import os
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

COMPANY_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1
_STALL_LIMIT = float(os.environ.get("REPRO_STALL_LIMIT", "90"))  # 无进展超过 N 秒就报卡点


def main():
    import database
    import main as _main
    from engine.pipeline import _run_analyze

    db = database.SessionLocal()
    last = {"p": -1, "t": time.time(), "msg": ""}
    # ★ 跑完整链路 main._execute_tax_risk_analysis（含 pipeline 之后那十几段无进度回调的后置）：
    #   99% 是 _run_analyze 里 _report(99,…) 设的，卡点几乎都在后置段。
    FULL_PATH = os.environ.get("REPRO_FULL", "1") == "1"

    def _cb(p, msg, step=None, module=None):
        now = time.time()
        _mod = ""
        try:
            from engine import pipeline as _pl
            _mod = getattr(_pl, "_pipeline_current_module", "") or ""
        except Exception:
            _mod = ""
        if p != last["p"]:
            print("[%7.1fs] progress=%-3s step=%s module=%s | %s"
                  % (now - t0, p, step, _mod, msg), flush=True)
            last.update({"p": p, "t": now, "msg": msg})
        else:
            if now - last["t"] > _STALL_LIMIT:
                print("!! 卡在 progress=%s（%6.1fs 无进展）step=%s module=%s | %s"
                      % (p, now - t0, step, _mod, msg), flush=True)
                import threading
                print("!! 线程栈：", flush=True)
                for _fr in (sys._current_frames().get(threading.get_ident()),):
                    if _fr:
                        for _f in traceback.extract_stack(_fr):
                            print("      ", _f.filename.split("\\")[-1],
                                  _f.lineno, _f.name, flush=True)
                    break
                last["t"] = now
        return None

    t0 = time.time()
    print("=== 开始全量分析 company_id=%s（full=%s）===" % (COMPANY_ID, FULL_PATH), flush=True)
    try:
        if FULL_PATH:
            res = _main._execute_tax_risk_analysis(COMPANY_ID, db, progress_callback=_cb)
        else:
            res = _run_analyze(COMPANY_ID, db, progress_callback=_cb)
    except Exception:
        traceback.print_exc()
        res = None
    finally:
        try:
            db.close()
        except Exception:
            pass
    print("=== 结束 %.1fs, result ok=%s ===" % (time.time() - t0, (res or {}).get("ok")), flush=True)
    if res:
        with open(os.path.join(ROOT, "scripts", "_repro_99.out"), "w", encoding="utf-8") as f:
            import json as _json
            _json.dump({"ok": res.get("ok"), "keys": sorted(res.keys())},
                       f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""实证「一键分析卡在 99%」的死锁已消除（2026-10-01 事故复测）。

事故形态：分析其实**跑完了**（报告已落盘），但 `_run_analysis_thread` 在
`with _analysis_lock:` 之内调用 `_write_analysis_checkpoint` → `_is_result_deleted`
再 `with _analysis_lock:` → threading.Lock 不可重入 → 同一线程自死锁 →
状态永远 running、CPU 0%、前端进度停在 99%、报告再也取不到。

本脚本直接复现事故调用形态：**持锁状态下**调用写回路径，必须在超时内返回。
用法（托管 venv）：python scripts/_verify_lock_fix.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TIMEOUT = float(os.environ.get("LOCK_FIX_TIMEOUT", "5"))


def main():
    import main as _main

    fails = []

    # ① 事故原形态：持锁 → 写检查点（内含 _is_result_deleted）
    t0 = time.time()
    try:
        with _main._analysis_lock:
            _main._write_analysis_checkpoint(9999, "verify", "ok")
    except Exception as exc:   # noqa: BLE001
        print("持锁调用 _write_analysis_checkpoint 抛异常: %r" % (exc,))
        fails.append("调用抛异常")
    dur = time.time() - t0
    print("① 持锁状态下 _write_analysis_checkpoint: %.3fs %s"
          % (dur, "✓ 未死锁" if dur < TIMEOUT else "✗ 死锁（>%.0fs）" % TIMEOUT))
    if dur >= TIMEOUT:
        fails.append("持锁调用 _write_analysis_checkpoint 仍死锁")

    # ② 同一形态再走一遍（确认不是偶发抢到锁）
    t0 = time.time()
    with _main._analysis_lock:
        _main._write_analysis_checkpoint(9999, "verify", "ok")
    dur2 = time.time() - t0
    print("② 复跑一次: %.3fs %s" % (dur2, "✓" if dur2 < TIMEOUT else "✗ 死锁"))
    if dur2 >= TIMEOUT:
        fails.append("复跑仍死锁")

    # ③ 直接调 _is_result_deleted（锁外）
    t0 = time.time()
    _res = _main._is_result_deleted(9999)
    dur3 = time.time() - t0
    print("③ 直接 _is_result_deleted: %.3fs → %s" % (dur3, _res))
    if dur3 >= TIMEOUT:
        fails.append("_is_result_deleted 死锁")

    print("\n【%s】%s"
          % (os.path.basename(__file__),
             "死锁已消除，分析可正常收尾" if not fails else "仍有问题：" + "；".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

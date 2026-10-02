# -*- coding: utf-8 -*-
"""反向验证：拆掉闸门 (b) 的自证循环后，它**真的**能抓到「永远拿不到的独立数据源」。

只读验证脚本，最后按字节还原。用法：
    python scripts/_rev_verify_unobtainable_gate.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RL = ROOT / "engine" / "tax_redlines.py"
ECS = ROOT / "engine" / "evidence_chain.py"
BAK = ROOT / "scripts" / "_bak"
PY = sys.executable

BAK.mkdir(parents=True, exist_ok=True)


def _fresh_mtime(p: Path) -> None:
    """把文件时间推到未来，避免同秒 .pyc 让子进程跑旧码。"""
    fut = time.time() + 120
    os.utime(p, (fut, fut))


def run_gate() -> tuple[int, str]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT))
    pr = subprocess.run([PY, str(ROOT / "tools" / "audit_consistency.py")],
                        capture_output=True, text=True, env=env, cwd=str(ROOT))
    out = (pr.stdout or "") + (pr.stderr or "")
    n_err = 0
    for line in out.splitlines():
        if line.strip().startswith("ERROR") and "项" in line:
            try:
                n_err = int(line.split("ERROR")[1].split("项")[0].strip())
            except Exception:
                pass
    return n_err, out


def has_error_text(out: str, needle: str) -> bool:
    return needle in out


def main() -> int:
    rl_orig, ecs_orig = RL.read_bytes(), ECS.read_bytes()
    shutil.copy2(RL, BAK / "tax_redlines.rev_verify.bak")
    shutil.copy2(ECS, BAK / "evidence_chain.rev_verify.bak")
    results = []
    try:
        # ── 基线：应当 ERROR 0（拒收证明走「已知缺口」WARN 分支）──
        n, out = run_gate()
        ok = (n == 0) and has_error_text(out, "已知缺口")
        results.append(("S0 基线", n == 0, "ERROR=%d 且已知缺口被 WARN 点名" % n))
        print("[S0] ERROR=%d  已知缺口点名=%s" % (n, has_error_text(out, "已知缺口")))

        # ── S1：从单一权威里删掉「投料单」别名 → RL-PTY-004 该要件恒 not_checked ──
        ECS.write_bytes(ecs_orig.replace(
            '"进销存台账": ["投料单", "在建工程领用或研发领用记录", "退货单"]'
            .encode("utf-8"),
            '"进销存台账": ["在建工程领用或研发领用记录", "退货单"]'.encode("utf-8")))
        _fresh_mtime(ECS)
        n, out = run_gate()
        fired = (n > 0) and has_error_text(out, "永远拿不到")
        results.append(("S1 删投料单别名", bool(fired), "ERROR=%d" % n))
        print("[S1] ERROR=%d 抓到「永远拿不到」=%s" % (n, fired))
        if not fired:
            print((out or "")[-1500:])
        ECS.write_bytes(ecs_orig)
        _fresh_mtime(ECS)

        # ── S2：把 RL-COST-006 的数据源改回裸「发票」→ 泛型令牌恒判缺失 ──
        RL.write_bytes(rl_orig.replace(
            "成本费用明细账、销项发票或进项发票".encode("utf-8"),
            "成本费用明细账、发票".encode("utf-8")))
        _fresh_mtime(RL)
        n, out = run_gate()
        fired = (n > 0) and has_error_text(out, "永远拿不到")
        results.append(("S2 改回裸「发票」", bool(fired), "ERROR=%d" % n))
        print("[S2] ERROR=%d 抓到「永远拿不到」=%s" % (n, fired))
        if not fired:
            print((out or "")[-1500:])
        RL.write_bytes(rl_orig)
        _fresh_mtime(RL)

        # ── S3：还原后必须回到基线绿 ──
        n, _ = run_gate()
        results.append(("S3 还原回基线", n == 0, "ERROR=%d" % n))
        print("[S3] 还原后 ERROR=%d" % n)

        ok_all = all(r[1] for r in results)
        print("\n=== 结果：%s ===" % ("全部通过" if ok_all else "有 FAIL"))
        for nm, passed, note in results:
            print("  [%s] %s (%s)" % ("PASS" if passed else "FAIL", nm, note))
        return 0 if ok_all else 1
    finally:
        RL.write_bytes(rl_orig)
        ECS.write_bytes(ecs_orig)
        _fresh_mtime(RL)
        _fresh_mtime(ECS)


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""P1-4 反向验证：注入已知缺陷 ⇒ 闸门 `check_review_flow_wiring` **必须报 ERROR**。

★ 子进程逐轮；备份/注入/恢复一律走 **bytes**（保持 CRLF）。

场景：
  S1 基线                                        ⇒ ERROR 0
  S2 `/risks/review-board` 改注册在 `/risks/{risk_id}` 之后 ⇒ ERROR ≥1（静默 404）
  S3 `risk.bulk_review` 未登记进 ACTIONS           ⇒ ERROR ≥1（批量复核无留痕）
  S4 `bulk_review` 改名（能力缺失）                 ⇒ ERROR ≥1
  S5 恢复后                                        ⇒ ERROR 0 且逐字节一致
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")

_PROBE = r'''
import importlib.util, sys, pathlib
root = pathlib.Path.cwd()
spec = importlib.util.spec_from_file_location("ac", root / "tools" / "audit_consistency.py")
m = importlib.util.module_from_spec(spec)
sys.modules["ac"] = m
spec.loader.exec_module(m)
iss = m.check_review_flow_wiring()
errs = [x for x in iss if x[0] == "ERROR"]
print("ERRORS=%d" % len(errs))
for e in errs[:3]:
    print("   -", e[1], "|", e[2][:150])
'''


def run_gate() -> int:
    cp = subprocess.run([PY, "-c", _PROBE], cwd=str(ROOT), capture_output=True,
                        text=True, encoding="utf-8", errors="replace", timeout=300)
    out = (cp.stdout or "") + (cp.stderr or "")
    line = [x for x in out.splitlines() if x.startswith("ERRORS=")]
    if not line:
        print("      [无法解析输出]", out[-400:])
        return -1
    for x in out.splitlines():
        if x.startswith("   - "):
            print("     ", x.strip())
    return int(line[0].split("=")[1])


def inject(rel: str, old: str, new: str) -> None:
    p = ROOT / rel
    raw = p.read_bytes()
    ob, nb = old.encode("utf-8"), new.encode("utf-8")
    n = raw.count(ob)
    assert n >= 1, ("注入锚点未命中", rel, old[:60])
    p.write_bytes(raw.replace(ob, nb))
    print("      注入命中 %d 处" % n)


def main() -> int:
    fails = []
    files = ["risks_api.py", "engine/audit_trail.py", "engine/risk_review.py"]
    orig = {f: (ROOT / f).read_bytes() for f in files}
    md5s = {f: hashlib.md5(v).hexdigest() for f, v in orig.items()}

    print("S1 基线：")
    n = run_gate()
    print("   ERRORS=%d（期望 0）" % n)
    if n != 0:
        fails.append("S1 基线不为 0")

    try:
        print("S2 注入：把 /risks/review-board 字面量改成参数化（模拟注册顺序错）")
        inject("risks_api.py", '"/risks/review-board"', '"/risks/{risk_id}/review-board-x"')
        n = run_gate()
        print("   ERRORS=%d（期望 ≥1）" % n)
        if n < 1:
            fails.append("S2 端点缺失/顺序错竟未被发现")
    finally:
        (ROOT / "risks_api.py").write_bytes(orig["risks_api.py"])

    try:
        print("S3 注入：risk.bulk_review 未登记进 ACTIONS")
        inject("engine/audit_trail.py",
               '    "risk.bulk_review",  # 风险**批量**复核',
               '    # "risk.bulk_review",  # 风险**批量**复核')
        n = run_gate()
        print("   ERRORS=%d（期望 ≥1）" % n)
        if n < 1:
            fails.append("S3 审计动作缺失竟未被发现")
    finally:
        (ROOT / "engine/audit_trail.py").write_bytes(orig["engine/audit_trail.py"])

    try:
        print("S4 注入：bulk_review 改名（能力缺失）")
        inject("engine/risk_review.py", "def bulk_review(", "def _bulk_review_x(")
        n = run_gate()
        print("   ERRORS=%d（期望 ≥1）" % n)
        if n < 1:
            fails.append("S4 能力缺失竟未被发现")
    finally:
        (ROOT / "engine/risk_review.py").write_bytes(orig["engine/risk_review.py"])

    print("S5 恢复后：")
    same = {f: (hashlib.md5((ROOT / f).read_bytes()).hexdigest() == md5s[f]) for f in files}
    print("   逐字节一致：%s" % same)
    if not all(same.values()):
        fails.append("S5 恢复后与原文不一致：%s" % same)
    n = run_gate()
    print("   ERRORS=%d（期望 0）" % n)
    if n != 0:
        fails.append("S5 恢复后仍非 0")

    print()
    if fails:
        print("反向验证 FAILED：")
        for f in fails:
            print("   -", f)
        return 1
    print("反向验证 5/5 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""P1-2 反向验证：注入已知缺陷 ⇒ 闸门 `check_ocr_engine_single_source` **必须报 ERROR**。

★ 子进程逐轮（同进程 `sys.modules` 缓存会导致假绿）。
★ 备份/注入/恢复一律走 **bytes**（保持 CRLF，避免"恢复后 md5 不一致"的假红）。

场景：
  S1 基线                                        ⇒ ERROR 0
  S2 一处 `_OC.record_ocr_run` 退回裸 join        ⇒ ERROR ≥1（治理层被绕过）
  S3 `ENGINES` 删掉 tesseract                     ⇒ ERROR ≥1（可用性回执与实际不符）
  S4 去掉 `app.include_router(ocr_router)`        ⇒ ERROR ≥1（接口不可达）
  S5 恢复后                                       ⇒ ERROR 0 且逐字节一致
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
iss = m.check_ocr_engine_single_source()
errs = [x for x in iss if x[0] == "ERROR"]
print("ERRORS=%d" % len(errs))
for e in errs[:3]:
    print("   -", e[1], "|", e[2][:140])
'''


def run_gate() -> int:
    cp = subprocess.run([PY, "-c", _PROBE], cwd=str(ROOT),
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=300)
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
    files = ["main.py", "engine/ocr_engine.py"]
    orig = {f: (ROOT / f).read_bytes() for f in files}
    md5s = {f: hashlib.md5(v).hexdigest() for f, v in orig.items()}

    print("S1 基线：")
    n = run_gate()
    print("   ERRORS=%d（期望 0）" % n)
    if n != 0:
        fails.append("S1 基线不为 0")

    try:
        print("S2 注入：一处 record_ocr_run 退回裸 join")
        inject("main.py", 'return _OC.record_ocr_run(chunks, "rapidocr")',
               'return "\\n".join(chunks)')
        n = run_gate()
        print("   ERRORS=%d（期望 ≥1）" % n)
        if n < 1:
            fails.append("S2 绕过治理层竟未被发现")
    finally:
        (ROOT / "main.py").write_bytes(orig["main.py"])

    try:
        print("S3 注入：把 tesseract 改名（保持语法合法，专门验证「引擎漏登记」判据）")
        inject("engine/ocr_engine.py",
               '{"name": "tesseract", "priority": 2',
               '{"name": "tesseract_x", "priority": 2')
        n = run_gate()
        print("   ERRORS=%d（期望 ≥1）" % n)
        if n < 1:
            fails.append("S3 引擎漏登记竟未被发现")
    finally:
        (ROOT / "engine/ocr_engine.py").write_bytes(orig["engine/ocr_engine.py"])

    try:
        print("S4 注入：去掉 include_router(ocr_router)")
        inject("main.py", "; app.include_router(ocr_router)", "")
        n = run_gate()
        print("   ERRORS=%d（期望 ≥1）" % n)
        if n < 1:
            fails.append("S4 接线缺失竟未被发现")
    finally:
        (ROOT / "main.py").write_bytes(orig["main.py"])

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

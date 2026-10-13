# -*- coding: utf-8 -*-
"""P1-1 反向验证：注入已知缺陷 ⇒ 闸门**必须报 ERROR**；恢复后逐字节一致。

★ 必须**子进程逐轮**（同进程有 `sys.modules` 缓存 ⇒ 假绿/假红 —— 项目记忆点名的陷阱）。
★ 备份/注入/恢复一律走 **bytes**：仓库文件是 CRLF，`Path.write_text` 会在 Windows
  把 `\\n` 规范成 `\\r\\n`（或反向），导致"恢复后 md5 不一致"的**假红**（实测踩过）。

场景：
  S1 基线（无注入）                          ⇒ ERROR 0
  S2 `ROW_CAPS` 删一个键                      ⇒ ERROR ≥1（登记表与源码不一致）
  S3 `main._get_row_values` 退回逐行区间读     ⇒ ERROR ≥1（O(n²) 回归）
  S4 **全部** `_PE.safe_nrows(...)` 退回 `.max_row`  ⇒ ERROR ≥1（缺 dimension 崩溃）
  S5 恢复后                                    ⇒ ERROR 0 且**逐字节一致**
"""
from __future__ import annotations

import hashlib
import re
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
iss = m.check_row_cap_manifest()
errs = [x for x in iss if x[0] == "ERROR"]
print("ERRORS=%d" % len(errs))
for e in errs[:3]:
    print("   -", e[1], "|", e[2][:140])
'''


def _b(path: Path) -> bytes:
    return path.read_bytes()


def run_gate() -> int:
    cp = subprocess.run([PY, "-c", _PROBE], cwd=str(ROOT),
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=300)
    out = (cp.stdout or "") + (cp.stderr or "")
    line = [x for x in out.splitlines() if x.startswith("ERRORS=")]
    if not line:
        print("      [无法解析输出]", out[-400:])
        return -1
    for x in out.splitlines():
        if x.startswith("   - "):
            print("     ", x.strip())
    return int(line[0].split("=")[1])


def inject_bytes(rel: str, old: str, new: str, *, regex: bool = False) -> None:
    """按字节替换注入（保持原换行符）。"""
    p = ROOT / rel
    raw = p.read_bytes()
    ob, nb = old.encode("utf-8"), new.encode("utf-8")
    if regex:
        pat = re.compile(ob)
        n = len(pat.findall(raw))
        assert n >= 1, ("注入锚点未命中(正则)", rel, old[:60])
        out = pat.sub(nb, raw)
    else:
        n = raw.count(ob)
        assert n >= 1, ("注入锚点未命中", rel, old[:60])
        out = raw.replace(ob, nb)
    p.write_bytes(out)
    print("      注入命中 %d 处" % n)


def main() -> int:
    fails = []
    files = ["engine/parse_enhance.py", "main.py"]
    orig = {f: _b(ROOT / f) for f in files}
    md5s = {f: hashlib.md5(v).hexdigest() for f, v in orig.items()}

    print("S1 基线：")
    n = run_gate()
    print("   ERRORS=%d（期望 0）" % n)
    if n != 0:
        fails.append("S1 基线不为 0")

    try:
        print("S2 注入：ROW_CAPS 删掉 5000 这个键")
        inject_bytes("engine/parse_enhance.py", '    5000: "核心明细表', '    # 5000: "核心明细表')
        n = run_gate()
        print("   ERRORS=%d（期望 ≥1）" % n)
        if n < 1:
            fails.append("S2 上限登记不一致竟未被发现")
    finally:
        (ROOT / "engine/parse_enhance.py").write_bytes(orig["engine/parse_enhance.py"])

    try:
        print("S3 注入：_get_row_values 退回逐行 openpyxl 区间读")
        inject_bytes("main.py",
                     "batch_rows = _PE.iter_rows_range(sheet, batch_start, batch_end)",
                     "batch_rows = list(sheet.iter_rows(min_row=batch_start,"
                     " max_row=batch_end, values_only=True))")
        n = run_gate()
        print("   ERRORS=%d（期望 ≥1）" % n)
        if n < 1:
            fails.append("S3 O(n²) 回归竟未被发现")
    finally:
        (ROOT / "main.py").write_bytes(orig["main.py"])

    try:
        print("S4 注入：全部 _PE.safe_nrows(...) 退回 .max_row（缺 dimension 会崩）")
        inject_bytes("main.py", r"_PE\.safe_nrows\([^)]*\)", "sheet.max_row", regex=True)
        n = run_gate()
        print("   ERRORS=%d（期望 ≥1）" % n)
        if n < 1:
            fails.append("S4 safe_nrows 防御被移除竟未被发现")
    finally:
        (ROOT / "main.py").write_bytes(orig["main.py"])

    print("S5 恢复后：")
    same = {f: (hashlib.md5(_b(ROOT / f)).hexdigest() == md5s[f]) for f in files}
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

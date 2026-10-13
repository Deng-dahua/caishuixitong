# -*- coding: utf-8 -*-
"""P1-3 反向验证：注入已知缺陷 ⇒ 闸门 `check_extract_rules_sync` **必须报 ERROR**。

★ 子进程逐轮；备份/注入/恢复一律走 **bytes**（保持 CRLF）。

场景：
  S1 基线                                    ⇒ ERROR 0
  S2 `RULES` 删一条（如 tax_rate_validity）   ⇒ ERROR ≥1（规则数 < 12 且与配置不同集合）
  S3 `RULE_CN` 删一条中文名                   ⇒ ERROR ≥1（前端会露出英文码）
  S4 配置 `_validation` 删一条                 ⇒ ERROR ≥1（两端不同步）
  S5 恢复后                                   ⇒ ERROR 0 且逐字节一致
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
iss = m.check_extract_rules_sync()
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
    files = ["engine/extract_validate.py", "config/standard_fields.json"]
    orig = {f: (ROOT / f).read_bytes() for f in files}
    md5s = {f: hashlib.md5(v).hexdigest() for f, v in orig.items()}

    print("S1 基线：")
    n = run_gate()
    print("   ERRORS=%d（期望 0）" % n)
    if n != 0:
        fails.append("S1 基线不为 0")

    try:
        print("S2 注入：RULES 删掉 tax_rate_validity")
        inject("engine/extract_validate.py", '    "tax_rate_validity",', '    # "tax_rate_validity",')
        n = run_gate()
        print("   ERRORS=%d（期望 ≥1）" % n)
        if n < 1:
            fails.append("S2 规则被删竟未被发现")
    finally:
        (ROOT / "engine/extract_validate.py").write_bytes(orig["engine/extract_validate.py"])

    try:
        print("S3 注入：RULE_CN 删掉 tax_rate_validity 的中文名")
        inject("engine/extract_validate.py", '    "tax_rate_validity": "税率非标准档位",',
               '    # "tax_rate_validity": "税率非标准档位",')
        n = run_gate()
        print("   ERRORS=%d（期望 ≥1）" % n)
        if n < 1:
            fails.append("S3 缺中文名竟未被发现")
    finally:
        (ROOT / "engine/extract_validate.py").write_bytes(orig["engine/extract_validate.py"])

    try:
        print("S4 注入：配置 _validation 删掉 tax_rate_validity 说明")
        inject("config/standard_fields.json",
               '  "tax_rate_validity": "税率经', '  "_x_tax_rate_validity": "税率经')
        n = run_gate()
        print("   ERRORS=%d（期望 ≥1）" % n)
        if n < 1:
            fails.append("S4 两端不同步竟未被发现")
    finally:
        (ROOT / "config/standard_fields.json").write_bytes(orig["config/standard_fields.json"])

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

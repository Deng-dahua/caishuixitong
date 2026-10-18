# -*- coding: utf-8 -*-
"""反向验证：故意注入缺陷，确认新增判据**真的会变红**（子进程逐轮，避免模块缓存假绿）。

背景（项目铁律）：验收工具自身的假判据最危险。本轮新增 31 项判据，
必须证明它们"不做修复就会红"，否则等于没判。

用法：.venv/Scripts/python.exe scripts/_reverse_verify_meta_audit.py
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
TEST = "tests/test_meta_audit_gap_fixes.py"

#: (名称, 文件, 原串, 注入串, 期望变红的用例)
CASES = [
    ("GAP-10 状态机", "engine/document_types.py",
     '"failed": ("pending", "manual", "success"),',
     '"failed": ("pending", "manual"),',
     "TestParseStatusFlow"),
    ("GAP-06 顶额取数", "engine/invoice_limit_detector.py",
     '    for key in ("amount", "invoice_amount", "金额", "je"):\n        v = inv.get(key)',
     '    for key in ("total",):\n        v = inv.get(key)',
     "TestInvoiceAndContract"),
    ("GAP-03 出罪规则", "engine/tax_redlines.py",
     '"exculpatory": True,',
     '"exculpatory": False,',
     "TestExculpatory"),
    ("GAP-02 时效判定", "engine/law_validity_checker.py",
     'return r["alert"] == "ERROR"',
     'return True',
     "TestLawValidity"),
    ("GAP-04 读取失败", "engine/enterprise_report.py",
     'if _fname and _fname in _failed:',
     'if False:',
     "TestEvidenceAvailability"),
    ("GAP-09 OCR 归一", "main.py",
     "if isinstance(images, (bytes, bytearray, memoryview)):",
     "if False:",
     "TestOcrXml"),
]


def run_pytest() -> tuple[bool, str]:
    p = subprocess.run([PY, "-m", "pytest", TEST, "-q"],
                       cwd=str(ROOT), capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode == 0, out[-800:]


def main() -> int:
    ok, tail = run_pytest()
    print("① 基线（应全绿）:", "PASS" if ok else "FAIL")
    if not ok:
        print(tail)
        return 2

    failures = 0
    for name, rel, old, new, cls in CASES:
        p = ROOT / rel
        src = io.open(p, encoding="utf-8").read()
        if old not in src:
            print("② [%s] ✗ 注入锚点未找到（判据无法验证）: %s" % (name, rel))
            failures += 1
            continue
        backup = src
        try:
            io.open(p, "w", encoding="utf-8").write(src.replace(old, new, 1))
            ok2, tail2 = run_pytest()
            red = (not ok2) and (cls in tail2 or "failed" in tail2)
            print("② [%s] 注入后 %s —— %s" % (name, "变红 ✔" if red else "仍绿 ✗（假判据！）",
                                              cls))
            if not red:
                failures += 1
                print(tail2[-400:])
        finally:
            io.open(p, "w", encoding="utf-8").write(backup)

    ok3, _ = run_pytest()
    print("③ 还原后（应全绿）:", "PASS" if ok3 else "FAIL")
    if not ok3:
        failures += 1
    return 0 if failures == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())

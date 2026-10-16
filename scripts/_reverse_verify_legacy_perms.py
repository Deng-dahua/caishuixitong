# -*- coding: utf-8 -*-
"""旧路由权限守护的**反向验证**（MQ2-D1 扩展，2026-10-17）。

对 `security_web.py` 注入三类已知缺陷，分别期望对应的守护测试**变红**；
每次注入后立即还原并复跑，确认恢复绿。不变红 ⇒ 该判据是假的（同义反复）。

用法：`.venv/Scripts/python.exe scripts/_reverse_verify_legacy_perms.py`
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SW = ROOT / "security_web.py"
TESTS = "tests/test_legacy_route_permissions.py"
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")

CASES = [
    (
        "A 删掉一条登记（应触发『漏配闸门』）",
        '    ("POST", "/api/tax-risk-docs/upload", "document.write"),\n',
        "",
        "test_no_write_endpoint_left_unregistered",
    ),
    (
        "B 把权限点改成不存在的 code（应触发『合法性守护』）",
        '"document.write"',
        '"document.write.NOT_A_REAL_PERM"',
        "test_permission_codes_are_registered",
    ),
    (
        "C 注释掉查表调用（应触发『接线自检』）",
        "        _need = _required_legacy_perm(request.method.upper(), matched_route_path)",
        "        _need = None  # 反向验证：临时断开接线",
        "test_enforcement_is_wired",
    ),
]


def _run(test_id: str) -> tuple:
    proc = subprocess.run(
        [PY, "-m", "pytest", f"{TESTS}::{test_id}", "-q", "-p", "no:randomly"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    original = SW.read_text(encoding="utf-8")
    ok = True
    try:
        for name, needle, repl, test_id in CASES:
            if needle not in original:
                print(f"[跳过] {name} —— 锚点未命中: {needle[:60]!r}")
                ok = False
                continue
            SW.write_text(original.replace(needle, repl, 1), encoding="utf-8")
            code, out = _run(test_id)
            red = code != 0
            print(f"[{'✅' if red else '❌'}] {name}\n      目标测试 {test_id} → {'变红' if red else '仍绿（判据是假的！）'}")
            if not red:
                print("      " + out.strip().splitlines()[-1][:160])
                ok = False
            SW.write_text(original, encoding="utf-8")          # 还原
            code2, _ = _run(test_id)
            print(f"      还原后 → {'恢复绿 ✅' if code2 == 0 else '仍红 ❌'}")
            if code2 != 0:
                ok = False
    finally:
        SW.write_text(original, encoding="utf-8")
        # 全量确认与磁盘一致
        assert SW.read_text(encoding="utf-8") == original, "还原失败！"
    print()
    print("=== 反向验证结论 ===")
    print("三类注入全部能触发对应判据 ✅" if ok else "存在未触发的判据 ❌（判据可能是同义反复）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

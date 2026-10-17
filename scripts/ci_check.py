# -*- coding: utf-8 -*-
"""一键质量门禁（CI-02）。

评估结论：2209 条用例「靠人记得跑」。本脚本把它们变成**一条命令 / 一个 CI 步骤**：

    python scripts/ci_check.py            # 全部检查（默认）
    python scripts/ci_check.py --fast     # 只跑静态门禁（不跑 pytest，约 10 秒）
    python scripts/ci_check.py --version-check

检查项
------
1. **资源版本同步**：`tools/sync_asset_versions.py --check`（改了 js/css 不同步 ⇒ 用户拿旧文件）
2. **前端权限门控**：注入器 `--check` + 闸门测试（漏配即红）
3. **一致性审计**：`tools/audit_consistency.py` —— **ERROR 必须为 0**
4. **版本与变更日志一致**：`VERSION` 首行必须出现在 `CHANGELOG.md` 顶部
5. **全量测试**：`pytest tests/`（不存在 `failed` 则通过；存在则打印清单并以非 0 退出）

★ 任一检查失败 ⇒ 退出码 1（CI 以此判定）。**不吞异常、不跳过失败项**。
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable


def _run(cmd, timeout=1800) -> tuple:
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def check_assets() -> tuple:
    code, out = _run([PY, "tools/sync_asset_versions.py", "--check"])
    return code == 0, ("资源版本已同步" if code == 0 else out.strip()[-600:])


def check_frontend_perms() -> tuple:
    code1, out1 = _run([PY, "scripts/_wire_frontend_perms.py", "--check"])
    code2, out2 = _run([PY, "-m", "pytest", "tests/test_frontend_perm_gate.py", "-q",
                        "-p", "no:randomly"])
    ok = code1 == 0 and code2 == 0
    detail = "门控注入与闸门均通过" if ok else (out1 + out2).strip()[-800:]
    return ok, detail


def check_audit() -> tuple:
    code, out = _run([PY, "tools/audit_consistency.py"])
    m = re.search(r"ERROR (\d+) 项", out)
    errors = int(m.group(1)) if m else None
    if code != 0 or errors is None:
        return False, "审计未正常完成（exit=%s）\n%s" % (code, out.strip()[-800:])
    return errors == 0, "审计 ERROR %d 项 / %s" % (
        errors, (re.search(r"WARN (\d+) 项", out) or ["", "?"])[1])


def check_version() -> tuple:
    vp = ROOT / "VERSION"
    if not vp.is_file():
        return False, "缺少 VERSION 文件（版本唯一权威）"
    version = vp.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    cp = ROOT / "CHANGELOG.md"
    if not cp.is_file():
        return False, "缺少 CHANGELOG.md"
    text = cp.read_text(encoding="utf-8")
    return version in text, ("VERSION=%s，CHANGELOG 已包含" % version
                             if version in text else
                             "VERSION=%s 未出现在 CHANGELOG.md 中" % version)


def check_tests() -> tuple:
    code, out = _run([PY, "-m", "pytest", "tests/", "-q", "--tb=no", "-p", "no:randomly"])
    tail = "\n".join((out or "").strip().splitlines()[-3:])
    m = re.search(r"(\d+) failed", out or "")
    failed = int(m.group(1)) if m else 0
    if code == 0 and failed == 0:
        return True, tail
    fails = [ln.split(" - ")[0] for ln in (out or "").splitlines() if ln.startswith("FAILED")]
    return False, "%s\n失败项（前 10）：\n%s" % (tail, "\n".join(fails[:10]))


def main() -> int:
    ap = argparse.ArgumentParser(description="一键质量门禁")
    ap.add_argument("--fast", action="store_true", help="只跑静态门禁，不跑 pytest")
    ap.add_argument("--version-check", action="store_true", help="只检查 VERSION/CHANGELOG")
    args = ap.parse_args()

    checks = []
    if args.version_check:
        checks = [("版本与变更日志", check_version)]
    elif args.fast:
        checks = [("资源版本同步", check_assets), ("前端权限门控", check_frontend_perms),
                  ("一致性审计", check_audit), ("版本与变更日志", check_version)]
    else:
        checks = [("资源版本同步", check_assets), ("前端权限门控", check_frontend_perms),
                  ("一致性审计", check_audit), ("版本与变更日志", check_version),
                  ("全量测试", check_tests)]

    bad = 0
    for name, fn in checks:
        try:
            ok, detail = fn()
        except Exception as exc:                  # noqa: BLE001
            ok, detail = False, "%s: %s" % (type(exc).__name__, exc)
        print(("[PASS] " if ok else "[FAIL] ") + name + " —— " + detail.splitlines()[0])
        if not ok:
            bad += 1
            for line in detail.splitlines()[1:]:
                print("        " + line)
    print("\n结果：%d 项通过 / %d 项失败" % (len(checks) - bad, bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

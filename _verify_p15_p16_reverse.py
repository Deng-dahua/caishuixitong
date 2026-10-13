# -*- coding: utf-8 -*-
"""P1-5 / P1-6 反向验证：注入已知缺陷 ⇒ 对应闸门**必须报 ERROR**。

★ 子进程逐轮；备份/注入/恢复一律走 **bytes**（保持 CRLF）。

P1-5（`check_template_manage_wiring`）：
  T1 基线 ⇒ 0 ｜ T2 `template_store` 缺 `disable_template` ⇒ ≥1
  T3 内置模板集合与 config 不一致（改名一个内置 id）⇒ ≥1
  T4 去掉 `include_router(templates_router)` ⇒ ≥1 ｜ T5 恢复 ⇒ 0 且逐字节一致

P1-6（`check_rule_version_manage_wiring`）：
  V1 基线 ⇒ 0 ｜ V2 `rule_version_admin` 缺 `rollback` ⇒ ≥1
  V3 **生效版本与配置基线不一致**（让 `published_version` 硬返回一个别值）⇒ ≥1
  V4 去掉 `app.include_router(rule_versions_router)` ⇒ ≥1 ｜ V5 恢复 ⇒ 0 且逐字节一致
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")


def _probe(check_fn: str) -> str:
    return r'''
import importlib.util, sys, pathlib
root = pathlib.Path.cwd()
spec = importlib.util.spec_from_file_location("ac", root / "tools" / "audit_consistency.py")
m = importlib.util.module_from_spec(spec)
sys.modules["ac"] = m
spec.loader.exec_module(m)
iss = getattr(m, "%s")()
errs = [x for x in iss if x[0] == "ERROR"]
print("ERRORS=%%d" %% len(errs))
for e in errs[:3]:
    print("   -", e[1], "|", e[2][:150])
''' % check_fn


def run_gate(check_fn: str) -> int:
    cp = subprocess.run([PY, "-c", _probe(check_fn)], cwd=str(ROOT), capture_output=True,
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


def scenario(tag: str, check_fn: str, files: list, steps: list, fails: list) -> None:
    """steps = [(说明, rel, old, new)]；最后有一条恢复校验。"""
    orig = {f: (ROOT / f).read_bytes() for f in files}
    md5s = {f: hashlib.md5(v).hexdigest() for f, v in orig.items()}

    print("%s 基线：" % tag)
    n = run_gate(check_fn)
    print("   ERRORS=%d（期望 0）" % n)
    if n != 0:
        fails.append("%s 基线不为 0" % tag)

    for desc, rel, old, new in steps:
        try:
            print("%s 注入：%s" % (tag, desc))
            inject(rel, old, new)
            n = run_gate(check_fn)
            print("   ERRORS=%d（期望 ≥1）" % n)
            if n < 1:
                fails.append("%s %s 竟未被发现" % (tag, desc))
        finally:
            (ROOT / rel).write_bytes(orig[rel])

    print("%s 恢复后：" % tag)
    same = {f: (hashlib.md5((ROOT / f).read_bytes()).hexdigest() == md5s[f]) for f in files}
    print("   逐字节一致：%s" % same)
    if not all(same.values()):
        fails.append("%s 恢复后与原文不一致：%s" % (tag, same))
    n = run_gate(check_fn)
    print("   ERRORS=%d（期望 0）" % n)
    if n != 0:
        fails.append("%s 恢复后仍非 0" % tag)


def main() -> int:
    fails: list = []

    scenario(
        "T(P1-5)", "check_template_manage_wiring",
        ["main.py", "engine/template_store.py"],
        [
            ("template_store 缺 disable_template",
             "engine/template_store.py", "def disable_template(", "def _disable_template_x("),
            ("内置模板集合与 config 不一致（只取第一个）",
             "engine/template_store.py", "for tid, t in tpl.items():",
             "for tid, t in list(tpl.items())[:1]:"),
            ("去掉 include_router(templates_router)",
             "main.py", "; app.include_router(templates_router)", ""),
        ], fails)

    scenario(
        "V(P1-6)", "check_rule_version_manage_wiring",
        ["main.py", "engine/rule_version_admin.py", "engine/rule_versions.py"],
        [
            ("rule_version_admin 缺 rollback",
             "engine/rule_version_admin.py", "def rollback_version(", "def _rollback_x("),
            ("未发布时生效版本与配置基线不一致",
             "engine/rule_versions.py",
             'return str(load_versions().get("rule_set_version") or "")',
             'return "2099.99"'),
            ("去掉 include_router(rule_versions_router)",
             "main.py", "; app.include_router(rule_versions_router)", ""),
        ], fails)

    print()
    if fails:
        print("反向验证 FAILED：")
        for f in fails:
            print("   -", f)
        return 1
    print("反向验证 8/8 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

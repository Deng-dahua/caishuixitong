# -*- coding: utf-8 -*-
"""`check_legal_text_coverage` 的**反向验证** —— 防"假闸门"。

★ 教训（2026-10-16 我第一次写这道反向验证时踩到）：**注入方式必须真能触发判据**。
  我第一版把**登记基线抬高**到 0.9999，结果闸门没变红 —— 因为当前覆盖率已是
  **100%**，任何 ≤1 的基线都不可能被"低于" ⇒ **注入无效**（不是闸门坏了）。
  正确做法是**削弱数据**：把某条被红线引用的条文的条号改坏 ⇒ 现算覆盖率下降
  ⇒ 必须低于登记基线 ⇒ 必须报"退化"。

做法（项目铁律：子进程逐轮，避免模块缓存假通过）：
  A 削弱数据（改掉一条被引用条文的条号）⇒ 必须报「退化」；
  B 恢复后 ⇒ 必须归零。

用法：`./.venv/Scripts/python.exe scripts/_verify_coverage_gate_reverse.py`
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "static" / "legal_library.json"

_CHILD = (
    "import sys; sys.path.insert(0, r'%s')\n"
    "from tools.audit_consistency import check_legal_text_coverage as C\n"
    "r = C()\n"
    "print('ISSUES %%d' %% len(r))\n"
    "for _l, _f, _m in r:\n"
    "    print(' -', _m[:130])\n"
) % str(ROOT)


def _gate() -> str:
    r = subprocess.run([sys.executable, "-c", _CHILD], capture_output=True, text=True,
                       cwd=str(ROOT), encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def main() -> int:
    orig = LIB.read_text(encoding="utf-8")
    lib = json.loads(orig)
    # 挑一条**被红线引用**的条文（增值税法实施条例 第三十九条，见 RL-INC-003）
    target = None
    for x in lib:
        if "增值税法实施条例" in str(x.get("law")) and str(x.get("article")) == "第三十九条":
            target = x
            break
    if target is None:
        print("!! 找不到注入目标 ⇒ 跳过（判据依赖具体数据，勿臆造）")
        return 1
    fails = []
    try:
        target["article"] = "第九百九十九条（反向验证注入）"
        LIB.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        out = _gate()
        hit = "退化" in out
        print("[%s] A 削弱数据（被引用条文改号）⇒ 必须报`退化`" % ("变红" if hit else "未变红"))
        if not hit:
            print("     输出：%s" % out.strip()[:240])
            fails.append("A 未报退化")
    finally:
        LIB.write_text(orig, encoding="utf-8")

    out = _gate()
    ok = "ISSUES 0" in out
    print("[%s] B 恢复后必须归零" % ("归零" if ok else "仍报错"))
    if not ok:
        print("     输出：%s" % out.strip()[:240])
        fails.append("B 恢复后仍报错")

    print()
    if fails:
        print("反向验证 **FAIL** —— %s" % "、".join(fails))
        return 1
    print("反向验证 **PASS**：削弱数据变红、恢复归零（判据非空转）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

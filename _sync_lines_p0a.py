# -*- coding: utf-8 -*-
"""精确同步 D 轨道文档中被 P0-A 改动带偏的**行号数字**。

原因（必然副作用）：P0-A 在 `tools/audit_consistency.py::run_checks()` 总链中
**新增一行** `+ check_rule_version_coverage()` ⇒ 其后的调用行号整体 +1。

同步项（权威值由 grep 实测）：
  · 「门禁调用行号」`+ check_trigger_determination_separation()` 12947 → **12948**（3 个文件）
  · 「文档一致性门禁调用行号」`+ check_doc_number_authority()`        12950 → **12951**

带期望命中数断言；替换后复查残留，不符即失败。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "第01批_触发条件与认定要件分离"

# (文件, 旧串, 新串, 期望命中数)
JOBS = [
    ("02_系统配置变更清单.md", "第 **12947** 行", "第 **12948** 行", 1),
    ("02_系统配置变更清单.md", "调用第 **12950** 行", "调用第 **12951** 行", 1),
    ("06_写入系统证据.md", "第 **12947** 行", "第 **12948** 行", 1),
    ("01_Skill设计文档.md", "第 **12947** 行", "第 **12948** 行", 1),
]


def main() -> int:
    ok = True
    for fname, old, new, expect in JOBS:
        p = DOC / fname
        t = p.read_text(encoding="utf-8")
        n = t.count(old)
        if n != expect:
            print("[FAIL] %s：期望命中 %d 次，实际 %d 次（%r）" % (fname, expect, n, old))
            ok = False
            continue
        p.write_text(t.replace(old, new), encoding="utf-8")
        print("[ok] %s：%r → %r（%d 处）" % (fname, old, new, n))

    # 残留复查：旧值不得残留（当前值恰好等于历史旧值 ≠ 残留，故按"旧串是否仍存在"判）
    for fname, old, _new, _e in JOBS:
        left = (DOC / fname).read_text(encoding="utf-8").count(old)
        if left:
            print("[FAIL] %s 仍残留 %d 处 %r" % (fname, left, old))
            ok = False

    # 权威值复核（与文档现值对照）
    audit_py = (ROOT / "tools" / "audit_consistency.py").read_text(encoding="utf-8").splitlines()
    for pat, want in (("+ check_trigger_determination_separation()", 12948),
                      ("+ check_doc_number_authority()", 12951)):
        got = [i + 1 for i, ln in enumerate(audit_py) if ln.strip().startswith(pat)]
        print("[check] %-50s 权威行号 %s（期望 %d）%s"
              % (pat, got, want, "✓" if got == [want] else "✗"))
        if got != [want]:
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

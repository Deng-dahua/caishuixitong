# -*- coding: utf-8 -*-
"""把常驻滚动文件里的「全量回归 passed 1569」同步为权威值 1593（含同次运行耗时）。

★ 权威 = 最近一次**全绿**全量运行的回执 `data/logs/pytest_last_run.json`
  （`passed=1593`，`finished_at=2026-10-09 17:31:58`）；耗时取本次运行输出 318.13s。
只按**精确串**替换，并对每处断言命中数 == 期望数（多一处/少一处都报错）。
不触碰「变更历史」行（如 `1424 → 1553`）与轮次快照文件（R1_Skill修订记录.md）。
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DOC = Path("docs/第01批_触发条件与认定要件分离")

OLD_P = "1569"
NEW_P = "1593"
OLD_D = "146.39s"
NEW_D = "318.13s"

# (文件, 旧串, 新串, 期望命中数)
EDITS = [
    ('05_回归测试报告.md', '| passed | **1569** |', '| passed | **1593** |', 1),
    ('05_回归测试报告.md', '| 耗时 | **146.39s**（与 1569 passed **同一次运行**的实测耗时', '| 耗时 | **318.13s**（与 1593 passed **同一次运行**的实测耗时', 1),
    ('05_回归测试报告.md', '③ 结果（**1569 passed / 0 failed / 4 skipped / 166 subtests**，耗时 146.39s', '③ 结果（**1593 passed / 0 failed / 4 skipped / 166 subtests**，耗时 318.13s', 1),
    ('最小检查集.md', '| ② | 全量 pytest passed | **1569** | `pytest tests/ -q` → `1569 passed, 4 skipped, 166 subtests passed` |', '| ② | 全量 pytest passed | **1593** | `pytest tests/ -q` → `1593 passed, 4 skipped, 166 subtests passed` |', 1),
    ('最小检查集.md', '# 实测：1569 passed, 4 skipped, 166 subtests passed', '# 实测：1593 passed, 4 skipped, 166 subtests passed', 1),
    ('最小检查集.md', '| 结果 | **1569 passed / 0 failed / 4 skipped / 166 subtests passed**（耗时 **146.39s**', '| 结果 | **1593 passed / 0 failed / 4 skipped / 166 subtests passed**（耗时 **318.13s**', 1),
    ('最小检查集.md', '| ③ | 全量 pytest 耗时 | **146.39s**（与 ② **同一次运行**', '| ③ | 全量 pytest 耗时 | **318.13s**（与 ② **同一次运行**', 1),
    ('最小检查集.md', '| 全量回归 | **1569 passed / 0 failed / 4 skipped / 166 subtests**（146.39s） |', '| 全量回归 | **1593 passed / 0 failed / 4 skipped / 166 subtests**（318.13s） |', 1),
    ('最小检查集.md', '| 全量回归 | **1569 passed / 0 failed / 4 skipped / 166 subtests** |', '| 全量回归 | **1593 passed / 0 failed / 4 skipped / 166 subtests** |', 1),
    ('最小检查集.md', '| 5 | 回归测试 | **是**（**1569 passed / 0 failed / 4 skipped / 166 subtests**） |', '| 5 | 回归测试 | **是**（**1593 passed / 0 failed / 4 skipped / 166 subtests**） |', 1),
    ('最终判断.md', '# 实测：1569 passed, 4 skipped, 166 subtests passed', '# 实测：1593 passed, 4 skipped, 166 subtests passed', 1),
    ('最终判断.md', '全量 1569 passed / 0 failed', '全量 1593 passed / 0 failed', 1),
    ('最终判断.md', '全量 1569 passed / 4 skipped / 166 subtests', '全量 1593 passed / 4 skipped / 166 subtests', 1),
    ('最终判断.md', '| 全量回归 | **1569 passed / 0 failed / 4 skipped / 166 subtests**（146.39s） |', '| 全量回归 | **1593 passed / 0 failed / 4 skipped / 166 subtests**（318.13s） |', 1),
    ('最终判断.md', '| 全量回归 | **1569 passed / 0 failed / 4 skipped / 166 subtests** |', '| 全量回归 | **1593 passed / 0 failed / 4 skipped / 166 subtests** |', 1),
    ('最终判断.md', '全量 **1569 passed / 0 failed / 4 skipped / 166 subtests**）', '全量 **1593 passed / 0 failed / 4 skipped / 166 subtests**）', 1),
    ('5个Skill测试用例.md', '全量 1569 passed / 4 skipped / 166 subtests', '全量 1593 passed / 4 skipped / 166 subtests', 1),
    ('5个Skill测试用例.md', '# 实测：1569 passed, 4 skipped, 166 subtests passed', '# 实测：1593 passed, 4 skipped, 166 subtests passed', 1),
    ('5个Skill回归测试报告.md', '# 实测：1569 passed, 4 skipped, 166 subtests passed', '# 实测：1593 passed, 4 skipped, 166 subtests passed', 1),
    ('5个Skill回归测试报告.md', '（`1569 passed`）', '（`1593 passed`）', 1),
    ('5个Skill验收自证.md', '**1569 passed / 4 skipped / 166 subtests**', '**1593 passed / 4 skipped / 166 subtests**', 1),
    ('5个Skill验收自证.md', '# 1569 passed / 4 skipped', '# 1593 passed / 4 skipped', 1),
]

fails = []
applied = 0
for fname, old, new, exp in EDITS:
    p = DOC / fname
    txt = p.read_text(encoding="utf-8")
    n = txt.count(old)
    if n != exp:
        fails.append("%s: 期望命中 %d 次，实际 %d 次 ｜ 串=%r" % (fname, exp, n, old[:60]))
        continue
    p.write_text(txt.replace(old, new), encoding="utf-8")
    applied += 1

print("已应用替换条目: %d / %d" % (applied, len(EDITS)))
if fails:
    print("!! 未应用（命中数不符）:")
    for f in fails:
        print("   -", f)
    sys.exit(1)

import re
bad = []
for fname in sorted({e[0] for e in EDITS}):
    txt = (DOC / fname).read_text(encoding="utf-8")
    for m in re.finditer(r"1569", txt):
        ln = txt[: m.start()].count("\n") + 1
        line = txt.split("\n")[ln - 1]
        if "\u2192" in line:
            continue                                   # 变更历史行，允许
        bad.append("%s:%d ｜ %s" % (fname, ln, line.strip()[:90]))
print("残留「1569」非历史行: %d 处" % len(bad))
for b in bad:
    print("   -", b)

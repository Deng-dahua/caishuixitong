# -*- coding: utf-8 -*-
"""把 D 轨道文档里的「全量回归 passed 1667」同步为权威值 1688（含同次运行耗时）。

★ 权威 = 最近一次**全绿**全量运行回执 `data/logs/pytest_last_run.json`
  （`passed=1688` / `failed=0` / `duration_s=111.52` / `finished_at=2026-10-10 20:02:19`）。
  本轮新增 `tests/test_gap_redline_detectors.py` 21 项（为 6 条「仅兜底」红线建真检测器）
  ⇒ 全绿通过数 1667 → 1688。
★ 只改「计数」与其**同一行耦合**的耗时（"与本次 passed 同次运行"的那一个），
  不改历史区间与含 `→` 的数字演变行。每处断言命中数 == 期望；末尾做残留反查。
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
DOC = Path("docs/第01批_触发条件与认定要件分离")

OLD, NEW = "1667", "1688"
OLD_S, NEW_S = "158.26s", "111.52s"

# (文件, 期望 1667 命中数, 期望 158.26s 命中数)
FILES = [
    ("05_回归测试报告.md", 3, 2),
    ("最小检查集.md", 7, 3),
    ("最终判断.md", 6, 1),
    ("5个Skill回归测试报告.md", 2, 0),
    ("5个Skill测试用例.md", 2, 0),
    ("5个Skill验收自证.md", 2, 0),
]

fails = []
applied = 0
for fname, exp_cnt, exp_sec in FILES:
    p = DOC / fname
    t = p.read_text(encoding="utf-8")
    n_cnt = t.count(OLD)
    n_sec = t.count(OLD_S)
    if n_cnt != exp_cnt:
        fails.append("%s: %s 期望 %d 次，实际 %d 次" % (fname, OLD, exp_cnt, n_cnt))
        continue
    if n_sec != exp_sec:
        fails.append("%s: %s 期望 %d 次，实际 %d 次" % (fname, OLD_S, exp_sec, n_sec))
        continue
    p.write_text(t.replace(OLD, NEW).replace(OLD_S, NEW_S), encoding="utf-8")
    applied += 1

print("已同步文件: %d / %d（%s → %s；耗时 %s → %s）" % (applied, len(FILES), OLD, NEW, OLD_S, NEW_S))
if fails:
    print("!! 未应用/异常:")
    for x in fails:
        print("   -", x)
    sys.exit(1)

bad = []
for fname, _, _ in FILES:
    t = (DOC / fname).read_text(encoding="utf-8")
    for ln, line in enumerate(t.split("\n"), 1):
        if OLD in line or OLD_S in line:
            bad.append("%s:%d ｜ %s" % (fname, ln, line.strip()[:90]))
print("残留旧值: %d 处" % len(bad))
for b in bad:
    print("   -", b)
sys.exit(1 if bad else 0)

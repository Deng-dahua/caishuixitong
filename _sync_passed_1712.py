# -*- coding: utf-8 -*-
"""把 D 轨道文档里的「全量回归 passed 1688」同步为权威值 1712（含同次运行耗时）。

★ 权威 = 最近一次**全绿**全量运行回执 `data/logs/pytest_last_run.json`
  （`passed=1712` / `duration_s=188.35` / `finished_at=2026-10-10 21:18:43`）。
  本轮新增 `tests/test_rulelist_v1.py` 24 项（外部规则清单 V1.0 落地的 12 条）
  ⇒ 全绿通过数 1688 → 1712。
★ 只改「计数」与其同行耦合的耗时；含 `→` 的数字演变行不动。每处断言命中数；末尾残留反查。
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
DOC = Path("docs/第01批_触发条件与认定要件分离")

OLD, NEW = "1688", "1712"
OLD_S, NEW_S = "102.76s", "188.35s"

FILES = [
    ("05_回归测试报告.md", 3, 2),
    ("最小检查集.md", 7, 3),
    ("最终判断.md", 6, 1),
    ("5个Skill回归测试报告.md", 2, 0),
    ("5个Skill测试用例.md", 2, 0),
    ("5个Skill验收自证.md", 2, 0),
]

fails, applied = [], 0
for fname, exp_cnt, exp_sec in FILES:
    p = DOC / fname
    t = p.read_text(encoding="utf-8")
    if t.count(OLD) != exp_cnt:
        fails.append("%s: %s 期望 %d 次，实际 %d 次" % (fname, OLD, exp_cnt, t.count(OLD)))
        continue
    if t.count(OLD_S) != exp_sec:
        fails.append("%s: %s 期望 %d 次，实际 %d 次" % (fname, OLD_S, exp_sec, t.count(OLD_S)))
        continue
    p.write_text(t.replace(OLD, NEW).replace(OLD_S, NEW_S), encoding="utf-8")
    applied += 1

print("已同步文件: %d / %d（%s → %s；耗时 %s → %s）" % (applied, len(FILES), OLD, NEW, OLD_S, NEW_S))
if fails:
    for x in fails:
        print("   !!", x)
    sys.exit(1)

bad = []
for fname, _, _ in FILES:
    t = (DOC / fname).read_text(encoding="utf-8")
    for ln, line in enumerate(t.split("\n"), 1):
        if OLD in line or OLD_S in line:
            bad.append("%s:%d ｜ %s" % (fname, ln, line.strip()[:80]))
print("残留旧值: %d 处" % len(bad))
for b in bad:
    print("   -", b)
sys.exit(1 if bad else 0)

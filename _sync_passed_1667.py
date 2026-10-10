# -*- coding: utf-8 -*-
"""把 D 轨道文档里的「全量回归 passed 1658」同步为权威值 1667。

★ 权威 = 最近一次**全绿**全量运行回执 `data/logs/pytest_last_run.json`
  （`passed=1667` / `failed=0` / `duration_s=180.01` / `finished_at=2026-10-10 12:09:19`）。
  本轮变更（A 轨道 RL-VAT-012 建真检测器切片）新增 `tests/test_vr_redline_declaration.py` 2 项，
  并修复前序会话引入的 12 项文档一致性测试回归 ⇒ 全绿通过数 1658 → 1667。
★ 口径：只改「计数」与其**同一行耦合**的耗时（"与本次 passed 同次运行"的那一个），
  不改历史区间（`55.94–214.90s`）与「变更历史」行（含 `→` 的**数字演变**行）。
★ 每处替换断言命中数 == 期望，多一处/少一处都报错；末尾做**残留反查**。
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
DOC = Path("docs/第01批_触发条件与认定要件分离")

OLD, NEW = "1658", "1667"
OLD_S, NEW_S = "415.9s", "180.01s"

# (文件, 期望 1658 命中数, 期望 415.9s 命中数)
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
    # 保护：出现在含「数字演变箭头」的历史行里的计数不得被改
    for ln, line in enumerate(t.split("\n"), 1):
        if OLD in line and "→" in line and OLD + " passed" not in line:
            fails.append("%s:%d 疑似历史演变行含 %s，已拒绝改：%s" % (fname, ln, OLD, line.strip()[:80]))
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

# 残留反查：不得再有旧值
bad = []
for fname, _, _ in FILES:
    t = (DOC / fname).read_text(encoding="utf-8")
    if OLD in t:
        for ln, line in enumerate(t.split("\n"), 1):
            if OLD in line:
                bad.append("%s:%d ｜ %s" % (fname, ln, line.strip()[:90]))
print("残留「%s」: %d 处" % (OLD, len(bad)))
for b in bad:
    print("   -", b)
sys.exit(1 if bad else 0)

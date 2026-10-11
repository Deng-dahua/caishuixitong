# -*- coding: utf-8 -*-
"""同步 D 轨道文档的「全量回归 passed」与「同次运行耗时」到最新回执真值。

本轮新增 `tests/test_rule_layer_authority.py`（13 项）⇒ 全量 passed 1729 → **1742**。
权威源：`data/logs/pytest_last_run.json`（pytest 会话钩子写回执，唯一权威）。

- passed：6 个文件（逐文件断言行数，不符即失败；次数以**实测**为准）；
- 耗时：仅 `05_回归测试报告.md` 的 **167.20s** → 回执 `duration_s`（口径「与本次 passed 同次运行」）。
  ★ R 系列文档里的 175.09s/62.04s/55.94s 是**历史修订记录**，**不得改**（改了就是篡改留痕）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "第01批_触发条件与认定要件分离"
RECEIPT = ROOT / "data" / "logs" / "pytest_last_run.json"

# (文件, 期望出现次数)——本轮实测得出，不照抄上一版脚本
PASSED_JOBS = [
    ("05_回归测试报告.md", 3),
    ("5个Skill回归测试报告.md", 2),
    ("5个Skill测试用例.md", 2),
    ("5个Skill验收自证.md", 2),
    ("最小检查集.md", 7),
    ("最终判断.md", 6),
]

OLD_PASSED = 1729
OLD_DUR = "167.20s"


def main() -> int:
    rec = json.loads(RECEIPT.read_text(encoding="utf-8"))
    new_passed = int(rec["passed"])
    new_dur = rec.get("duration_s")
    print("[receipt] passed=%s failed=%s duration_s=%s finished_at=%s"
          % (new_passed, rec.get("failed"), new_dur, rec.get("finished_at")))
    if int(rec.get("failed") or 0) != 0:
        print("[FAIL] 回执显示最近一次全量运行有失败，不得同步「passed」到文档")
        return 1
    assert new_passed != OLD_PASSED, "passed 未变，无需同步"

    total = 0
    for fname, expect in PASSED_JOBS:
        p = DOC / fname
        t = p.read_text(encoding="utf-8")
        n = t.count(str(OLD_PASSED))
        if n != expect:
            print("[FAIL] %s：期望 %d 处，实际 %d 处" % (fname, expect, n))
            return 1
        p.write_text(t.replace(str(OLD_PASSED), str(new_passed)), encoding="utf-8")
        total += n
        print("[ok] %s：%s → %s（%d 处）" % (fname, OLD_PASSED, new_passed, n))
    print("[ok] passed 合计替换 %d 处" % total)

    if new_dur:
        p = DOC / "05_回归测试报告.md"
        t = p.read_text(encoding="utf-8")
        n = t.count(OLD_DUR)
        if n:
            p.write_text(t.replace(OLD_DUR, "%.2fs" % float(new_dur)), encoding="utf-8")
            print("[ok] 05_回归测试报告.md：耗时 %s → %.2fs（%d 处）"
                  % (OLD_DUR, float(new_dur), n))
        else:
            print("[warn] 05_回归测试报告.md 未找到 %s（可能已同步）" % OLD_DUR)

    left = sum((DOC / f).read_text(encoding="utf-8").count(str(OLD_PASSED))
               for f, _ in PASSED_JOBS)
    print("[check] 旧 passed %d 残留：%d 处%s" % (OLD_PASSED, left, " ✓" if left == 0 else " ✗"))
    return 0 if left == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

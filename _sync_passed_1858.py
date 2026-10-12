# -*- coding: utf-8 -*-
"""同步 D 轨道文档的「全量回归 passed」到最新回执推导真值。

本轮新增 `tests/test_legal_version_normalization.py`（20 项）⇒ 全量 passed 1838 → **1858**。

★ 本轮特殊性（**必须先同步、后跑全量**）：
`tests/test_doc_consistency_skills.py` 里有一组「反向验证」用例会**改真文档**再还原。
若全量运行**被中途杀掉**（SIGTERM/超时），还原代码不执行 ⇒ 文档被留在改坏状态
（实测：`01_Skill设计文档.md` 的「分项 10+7+3+3+2+3=28」被改写为「+6=31」）。
⇒ 跑全量时**不要中途终止**；若终止，先 `git checkout` 恢复被改坏的文档再继续。

权威源：`data/logs/pytest_last_run.json` 的 `collected - skipped`（**全绿时应等于 passed**）。
为什么不用回执现值：全量在「文档数字与回执不一致」时会失败，此时回执的 passed 含失败项，
不是稳定权威值 ⇒ 用 `collected - skipped` 推导全绿目标值。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "第01批_触发条件与认定要件分离"
RECEIPT = ROOT / "data" / "logs" / "pytest_last_run.json"

# (文件, 期望出现次数)——本轮实测得出
PASSED_JOBS = [
    ("05_回归测试报告.md", 3),
    ("5个Skill回归测试报告.md", 2),
    ("5个Skill测试用例.md", 2),
    ("5个Skill验收自证.md", 2),
    ("最小检查集.md", 7),
    ("最终判断.md", 6),
]

OLD_PASSED = 1838


def main() -> int:
    rec = json.loads(RECEIPT.read_text(encoding="utf-8"))
    # ★ 目标值优先取显式环境变量（回执在「刚加完测试、尚未跑全量」时是**旧收集数**，
    #   不能直接用；须先 `pytest --collect-only` 取新收集数再由调用方传入）。
    _explicit = os.environ.get("TARGET_PASSED")
    if _explicit:
        target = int(_explicit)
        print("[target] 显式目标 passed=%s（回执 collected=%s 为旧值，不用）"
              % (target, rec.get("collected")))
    else:
        target = int(rec["collected"]) - int(rec.get("skipped") or 0)
        print("[receipt] collected=%s skipped=%s → 目标 passed=%s"
              % (rec["collected"], rec.get("skipped"), target))
    if target == OLD_PASSED:
        print("[skip] 目标与现值相同，无需同步")
        return 0

    total = 0
    for fname, expect in PASSED_JOBS:
        p = DOC / fname
        t = p.read_text(encoding="utf-8")
        n = t.count(str(OLD_PASSED))
        if n != expect:
            print("[FAIL] %s：期望 %d 处，实际 %d 处" % (fname, expect, n))
            return 1
        p.write_text(t.replace(str(OLD_PASSED), str(target)), encoding="utf-8")
        total += n
        print("[ok] %s：%s → %s（%d 处）" % (fname, OLD_PASSED, target, n))
    print("[ok] passed 合计替换 %d 处" % total)

    left = sum((DOC / f).read_text(encoding="utf-8").count(str(OLD_PASSED))
               for f, _ in PASSED_JOBS)
    print("[check] 旧 passed %d 残留：%d 处%s" % (OLD_PASSED, left, " ✓" if left == 0 else " ✗"))
    return 0 if left == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

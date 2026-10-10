# -*- coding: utf-8 -*-
"""同步 D 轨道文档里 `tools/audit_consistency.py` 的**函数定义/调用行号**。

★ 权威 = 现算 `grep -n`（2026-10-10 本会话编辑该文件 +52 行 ⇒ 行号整体下移）：
    check_trigger_determination_separation 定义 11490 → 11542；调用 12895 → 12947
    check_doc_number_authority           定义 11956 → 12008；调用 12898 → 12950
★ 每处断言命中数 == 期望，多/少都报错；末尾残留反查。
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
DOC = Path("docs/第01批_触发条件与认定要件分离")

# (文件, 旧, 新, 期望命中数)
EDITS = [
    ("01_Skill设计文档.md", "第 11490 行", "第 11542 行", 1),
    ("01_Skill设计文档.md", "第 12895 行并入总链", "第 12947 行并入总链", 1),
    ("02_系统配置变更清单.md", "第 **11490** 行", "第 **11542** 行", 1),
    ("02_系统配置变更清单.md", "第 **12895** 行", "第 **12947** 行", 1),
    ("02_系统配置变更清单.md", "定义第 **11956** 行、调用第 **12898** 行",
                              "定义第 **12008** 行、调用第 **12950** 行", 1),
    ("03_失败样例测试结果.md", "（第 11490 行）", "（第 11542 行）", 1),
    ("06_写入系统证据.md", "第 **11490** 行", "第 **11542** 行", 1),
    ("06_写入系统证据.md", "第 **12895** 行", "第 **12947** 行", 1),
]

fails, applied = [], 0
for fname, old, newv, exp in EDITS:
    p = DOC / fname
    t = p.read_text(encoding="utf-8")
    n = t.count(old)
    if n != exp:
        fails.append("%s: 期望 %d 次，实际 %d 次 ｜ %r" % (fname, exp, n, old[:60]))
        continue
    p.write_text(t.replace(old, newv), encoding="utf-8")
    applied += 1
print("已应用替换: %d / %d" % (applied, len(EDITS)))
if fails:
    for x in fails:
        print("   !!", x)
    sys.exit(1)

bad = []
for fname in sorted({e[0] for e in EDITS}):
    t = (DOC / fname).read_text(encoding="utf-8")
    for old in ("11490", "12895", "11956", "12898"):
        for ln, line in enumerate(t.split("\n"), 1):
            if old in line:
                bad.append("%s:%d 残留 %s ｜ %s" % (fname, ln, old, line.strip()[:80]))
print("残留旧行号: %d 处" % len(bad))
for b in bad:
    print("   -", b)
sys.exit(1 if bad else 0)

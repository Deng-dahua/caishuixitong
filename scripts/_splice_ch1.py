# -*- coding: utf-8 -*-
"""按锚点把第一章新段落块拼回 engine/overall_conclusion.py（一次性工具，只读源+写回）。

为什么用锚点切片而不是整段 old_string 匹配：被替换区间约 250 行、含大量长中文串，
逐字匹配易因空白/换行差异失败；锚点切片只依赖两个稳定标记。
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / "engine" / "overall_conclusion.py"
BLOCK = ROOT / "scripts" / "_ch1_new_block.txt"
START = "    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550 \u7ec4\u88c5\u6bb5\u843d \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550"
END = "    return {"

src = TARGET.read_text(encoding="utf-8")
if src.count(START) != 1:
    sys.exit("锚点 START 命中 %d 次（应为 1），中止" % src.count(START))
i = src.index(START)
j = src.index(END, i)
new = BLOCK.read_text(encoding="utf-8")
if "def build_overall_conclusion" in new or "cost_recon = _cost_reconciliation" not in new:
    sys.exit("新块自检失败：缺 cost_recon 或误含函数定义")
out = src[:i] + new + src[j:]
TARGET.write_text(out, encoding="utf-8")
print("已拼接：旧区间 %d 字符 → 新块 %d 字符；文件 %d → %d 字符"
      % (j - i, len(new), len(src), len(out)))
print("自检：'def build_overall_conclusion' 出现 %d 次（须为 1）" % out.count("def build_overall_conclusion"))
print("自检：'组装段落' 出现 %d 次（须为 1）" % out.count("组装段落"))

# -*- coding: utf-8 -*-
"""报告口径词频扫描：给定渲染后的 HTML（或结果 JSON），统计关键表达出现次数。

用法：
    python scripts/_scan_report_labels.py [文件路径]

用途：调整报告口径（如"待核实" vs "风险点"）后，快速核对措辞是否按预期出现/消失。
默认扫描 scripts/four_reports/_verify_fresh.html。
"""
import os
import sys

REPO = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(REPO)

PATH = sys.argv[1] if len(sys.argv) > 1 else "scripts/four_reports/_verify_fresh.html"

# 观察词表（顺序即输出顺序）：左列=词，右列=期望（True 应显著出现 / False 应≈0）
WATCH = [
    # 集合/章节级（涉嫌违法违规口径）
    "风险事实（涉嫌违法违规）",
    "风险事项（涉嫌违法违规）",
    "涉嫌违法违规",
    # 逐项级
    "风险点",
    "风险点：",
    # 基线"待核"口径
    "待核事实",
    "待核事项",
    "待核风险",
    "待核线索",
    "待证线索",
    # 合法状态词（无论哪种口径都应保留）
    "待核实",
    "待核验",
    "待核",
    "待人工复核",
    "待确认",
]

with open(PATH, encoding="utf-8", errors="replace") as f:
    text = f.read()

print("filesize:", os.path.getsize(PATH), "bytes")
print("-" * 52)
for w in WATCH:
    print(f"  {text.count(w):>6}  {w}")

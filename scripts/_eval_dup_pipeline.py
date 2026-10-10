# -*- coding: utf-8 -*-
"""只读评估：在**真实产物 report_data** 上重跑「企业易读版生成 → 两轮去重」，打印重复率口径。

用途：改去重/生成逻辑后**快速**看效果（免跑整条一键分析链）。**不做任何判定**——
所有数字都来自唯一权威 `dedup_pipeline.duplicate_rate`；本脚本只负责"把链跑一遍 + 打印"。

⚠ 本脚本是**方向性**评估（在已产出的 report_data 上重跑生成阶段），
  正式验收仍须走 `scripts/run_companies.py`（整链）。

用法：.venv/Scripts/python.exe scripts/_eval_dup_pipeline.py [产物路径] [--blocks]
"""
import sys, os, io, json, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT); sys.path.insert(0, ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from engine import output_variants as ov
from engine.dedup_pipeline import duplicate_rate, split_sections, load_rules, is_necessary
from engine import dupkit

_pos = [a for a in sys.argv[1:] if not a.startswith("--")]
ART = _pos[0] if _pos else "scripts/four_reports/company_1_full.json"
SHOW_BLOCKS = "--blocks" in sys.argv


def _rate(rd, tag):
    t = ov.report_text_from(rd)
    r = duplicate_rate(t.split("\n"))
    print("[%s] 整体=%s  超阈章节=%d  事实重复=%s  阻断=%s"
          % (tag, r["整体"], r["章节统计"]["超阈章节"], r["事实重复"]["判定"], r["阻断"]))
    return r, t


rd = json.load(open(ART, encoding="utf-8"))
r0, _ = _rate(rd, "现状(产物)")

# 1) 重跑「企业易读版报告」生成（含第 1 轮去重 `report_dedup.dedup_report`）
from engine.enterprise_report import build_enterprise_readable_report as _ber
rd["enterprise_readable_report"] = _ber(rd)
r1, _ = _rate(rd, "重跑生成")

# 2) 重跑第 2 轮跨疑点去重
from engine.report_pipeline import dedup_report_data as _drd
_, _log = _drd(rd)
print("    第 2 轮去重处理 %d 条" % len(_log))
r2, txt = _rate(rd, "重跑去重")

print("\n超阈章节名：", r2["章节统计"]["超阈章节名"])
print("\n同章节最差 8：")
for x in r2["同章节最差15"][:8]:
    print("   %-46s 章 %5d 字 / 冗余 %5d 字 → %.1f%%  %s"
          % (str(x["章节"])[:44], x["chars"], x["redundant_chars"], x["rate"] * 100, x["判定"]))

if SHOW_BLOCKS:
    lines = txt.split("\n")
    blocks, sections = split_sections(lines)
    R = load_rules()
    seen_norm, seen_paras, red = {}, [], []
    for i, b in enumerate(blocks):
        if is_necessary(b):
            continue
        nt = dupkit.norm(b)
        if len(nt) >= int(R["norm"]["min_len_for_dup"]) and nt in seen_norm:
            red.append((i, b)); continue
        seen_norm.setdefault(nt, str(i))
        if any(dupkit.is_paragraph_dup(nt, g, rules=R) for g, _ in seen_paras):
            red.append((i, b)); continue
        seen_paras.append((nt, str(i)))
    print("\n冗余块 %d / %d：" % (len(red), len(blocks)))
    for i, b in sorted(red, key=lambda x: -len(x[1]))[:25]:
        print("   [#%d] <%s> %d 字  %s" % (i, str(sections[i])[:26], len(b), b[:70]))

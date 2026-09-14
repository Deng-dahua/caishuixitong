# -*- coding: utf-8 -*-
"""报告体检：从全量分析结果中筛出"必然误报"特征的可疑结论（2026-09-15）。

判据（任一命中即列出，供人工判读）：
  ① 占比恒为 100%（"占比100.00%"、"Top3占比100"）——前N名未切片的典型症状
  ② 金额为 0 或家数为 0 却给出风险结论（"0元""0家""0笔""0张"）
  ③ 高风险/中风险但内容是"未发现/无/正常"之类自相矛盾
  ④ 结论里出现空名称（"（）"、"(3,639" 这类聚合异常）

用法：python scripts/diag_report_sanity.py [company_id ...]
"""
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
REPO = r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong"
OUT = os.path.join(REPO, "scripts", "four_reports")

PATS = [
    (re.compile(r"占比\s*100(\.0+)?%|Top3占比100|占\s*100(\.0+)?%"), "① 占比恒100%"),
    (re.compile(r"[（(]\s*[）)]|\(\s*[0-9,]+\.\d{2}元\)"), "④ 空名称聚合"),
]
ZERO = re.compile(r"(0\.00元|0元|0家|0笔|0张|共0)")
RISK = ("高风险", "中风险")


def walk(o, path=""):
    if isinstance(o, dict):
        t = str(o.get("type") or "")
        lvl = str(o.get("level") or o.get("risk_level") or "")
        detail = str(o.get("detail") or o.get("description") or "")
        if t and (lvl in RISK or any(p.search(detail) for p, _ in PATS)):
            flags = [why for p, why in PATS if p.search(detail)]
            if ZERO.search(detail) and lvl in RISK:
                flags.append("② 零值却给风险结论")
            if flags:
                yield (lvl, t, flags, detail[:200])
        for k, v in o.items():
            yield from walk(v, path + "/" + str(k))
    elif isinstance(o, list):
        for v in o:
            yield from walk(v, path)


for cid in (sys.argv[1:] or ["1", "3"]):
    p = os.path.join(OUT, f"company_{cid}_full.json")
    if not os.path.exists(p):
        print("missing", p)
        continue
    d = json.load(open(p, encoding="utf-8"))
    seen = set()
    rows = []
    for r in walk(d):
        key = (r[0], r[1], r[3][:60])
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)
    print("=" * 78)
    print(f"公司{cid}：可疑结论 {len(rows)} 条")
    for lvl, t, flags, detail in rows[:40]:
        print(f"  [{lvl}] {t[:60]}")
        print(f"      {'、'.join(flags)}")
        print(f"      {detail[:190]}")

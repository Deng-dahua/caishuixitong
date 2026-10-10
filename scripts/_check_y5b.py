# -*- coding: utf-8 -*-
"""核实：疑点5 的「分项扣除限额测算」表里到底有没有金额/读数。

★ 这决定 D6/D6b/D8 是"真修好"还是"被'未产出读数'掩盖"。
"""
import io
import json
import os

ROOT = os.getcwd()
D = json.load(io.open(os.path.join(ROOT, "scripts", "four_reports",
                                  "company_1_full.json"), "r", encoding="utf-8"))
CP = (D.get("enterprise_readable_report") or {}).get("confirmed_problems") or []
p = [x for x in CP if "税前扣除限额" in str(x.get("title") or "")][0]

print("=== 全部表及其内容 ===")
for pi, np_ in enumerate(p.get("narrative_paragraphs") or []):
    for tb in (np_.get("detail_tables") or []):
        print("[para%d] %s（%d 行）" % (pi, str((tb or {}).get("title") or "")[:40],
                                       len((tb or {}).get("rows") or [])))
        for r in ((tb or {}).get("rows") or []):
            print("     ", {k: str(v)[:48] for k, v in (r or {}).items()})
    dt = np_.get("detail_table") or {}
    if dt.get("rows"):
        print("[para%d] detail_table %s（%d 行）" % (pi, str(dt.get("title") or "")[:40],
                                                     len(dt["rows"])))
        for r in dt["rows"]:
            print("     ", {k: str(v)[:48] for k, v in (r or {}).items()})

T = json.dumps(p, ensure_ascii=False)
print()
print("=== 关键金额是否出现在该疑点里 ===")
for w in ("411,111.53", "2,729,730.26", "6,636,800.57", "33,184.00", "995,520.09",
          "业务招待费", "广宣费", "广告费"):
    print("  %-16s %d 次" % (w, T.count(w)))

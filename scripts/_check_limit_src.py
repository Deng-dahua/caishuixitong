# -*- coding: utf-8 -*-
"""决定性验证：`_limit_items_table` 的入参在报告层拿得到吗？

候选来源（都从真跑产物取，不用编造数据）：
  A. `comprehensive.redline_detection` 里该红线的**全部 findings**（引擎层分组）
  B. 报告层疑点对象自带的 `supporting_findings`（若产物里有）
"""
import io
import json
import os
import sys

ROOT = os.getcwd()
sys.path.insert(0, ROOT)
D = json.load(io.open(os.path.join(ROOT, "scripts", "four_reports",
                                  "company_1_full.json"), "r", encoding="utf-8"))
rd = ((D.get("comprehensive") or {}).get("redline_detection") or {})

f5 = []
seen = set()
for k in ("suspicions", "unconfirmed"):
    for it in (rd.get(k) or []):
        if str(it.get("redline_id") or "") != "RL-CIT-007":
            continue
        key = id(it)
        if key in seen:
            continue
        seen.add(key)
        f5.append(it)

print("RL-CIT-007 在 redline_detection 里的条目数 =", len(f5))
for i, it in enumerate(f5):
    nm = str(it.get("finding_type") or it.get("type") or "")[:26]
    om = it.get("observed_metrics") or {}
    print("  [%d] type=%-26s observed_metrics 键数=%d %s"
          % (i, nm, len(om), list(om)[:4]))

from engine.enterprise_report import _limit_items_table
rows = _limit_items_table("RL-CIT-007", f5)
print()
print("A. 用 redline_detection 的 findings 调 _limit_items_table：")
print("   返回", "None" if rows is None else "%d 行" % len(rows.get("rows") or []))
if rows:
    for r in (rows.get("rows") or []):
        print("     ", {k: str(v)[:26] for k, v in (r or {}).items()})

# B. 报告层疑点对象里有没有 supporting_findings
CP = (D.get("enterprise_readable_report") or {}).get("confirmed_problems") or []
p5 = [x for x in CP if "税前扣除限额" in str(x.get("title") or "")]
if p5:
    sf = p5[0].get("supporting_findings")
    print()
    print("B. 报告层疑点对象的 supporting_findings =",
          "无该字段" if sf is None else "%d 条" % len(sf))

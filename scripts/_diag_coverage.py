# -*- coding: utf-8 -*-
"""诊断：跑一次真实分析，查清覆盖清单里「纳税申报表」到底来自哪一部分
（①原子规则 / ②税务指标 / ③税务红线），以及 present（已提供资料类别）实际内容。
"""
import os, sys, shutil
from collections import Counter, defaultdict

sys.path.insert(0, os.getcwd())
os.chdir(os.getcwd())

src = open("scripts/_scratch_measure.py", encoding="utf-8").read().replace(
    "if __name__", "if False and __name__")
g = {"__name__": "__notmain__",
     "__file__": os.path.abspath("scripts/_scratch_measure.py")}
exec(compile(src, "scripts/_scratch_measure.py", "exec"), g)
g["compose"]()
res = g["run_and_measure"]()

rep = (res or {}).get("report") or {}
cov = rep.get("analysis_coverage") or {}
print("\n=== coverage 顶层 ===")
print("total=%s executed=%s blocked=%s" % (
    cov.get("total"), cov.get("executed"), cov.get("blocked")))

blocked_items = cov.get("blocked_items") or []
print("\n=== blocked_items 按 kind 计数 ===")
print(dict(Counter(str(it.get("kind")) for it in blocked_items)))

# 「纳税申报表」出现在哪些部分
print("\n=== 缺失名含「纳税申报表」的 blocked 项，按 kind 归类 ===")
by_kind = defaultdict(list)
for it in blocked_items:
    if "纳税申报表" in (it.get("missing") or []):
        by_kind[str(it.get("kind"))].append(str(it.get("name")))
for k, names in by_kind.items():
    print("  [%s] %d 项，如：%s" % (k, len(names), names[:6]))

print("\n=== missing_sources 分布 ===")
ms = cov.get("missing_sources") or {}
for k, v in sorted(ms.items(), key=lambda kv: -kv[1])[:10]:
    print("   %s: %s 项" % (k, v))

# present 到底是什么
print("\n=== 实际 present（_doc_covered_categories 产出）===")
from engine.enterprise_report import _doc_covered_categories
fr = rep.get("file_results") or []
print("  file_results 中 type 分布:", dict(
    Counter(str(x.get("type")) for x in fr if isinstance(x, dict))))
print("  present =", sorted(_doc_covered_categories({"file_results": fr})))

shutil.rmtree(g["SCRATCH_DIR"], ignore_errors=True)

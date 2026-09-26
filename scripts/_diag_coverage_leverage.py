# -*- coding: utf-8 -*-
"""回答「怎么才能查得更全」：按"补齐某资料能解锁多少检查项"排序。

对覆盖清单里每个被 blocked 的检查项，看它的 missing 列表：
- 若只缺一种资料 → 补这一种即可解锁
- 若缺多种 → 需全部补齐才能解锁
由此得出各类资料的"解锁收益"，给用户明确的补件优先级。
"""
import os, sys, shutil
from collections import defaultdict

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
blocked = cov.get("blocked_items") or []

print("\n" + "=" * 74)
print("覆盖基线：total=%s  executed=%s  blocked=%s"
      % (cov.get("total"), cov.get("executed"), cov.get("blocked")))
print("=" * 74)

# 只缺一种 → 补它即刻解锁
solo_gain = defaultdict(int)
solo_detail = defaultdict(list)
multi = 0
for it in blocked:
    ms = list(it.get("missing") or [])
    if len(ms) == 1:
        solo_gain[ms[0]] += 1
        if len(solo_detail[ms[0]]) < 4:
            solo_detail[ms[0]].append(str(it.get("name"))[:30])
    elif len(ms) > 1:
        multi += 1

print("\n★ 补件优先级（补齐该资料**单独**即可解锁的检查项数）")
print("-" * 74)
for k, v in sorted(solo_gain.items(), key=lambda kv: -kv[1]):
    kinds = sorted({str(i.get("kind")) for i in blocked
                    if (i.get("missing") or []) == [k]})
    print("  %-22s +%3d 项   [%s]" % (k, v, "/".join(kinds)))
    print("        例：%s" % "、".join(solo_detail[k]))

print("\n★ 需多份资料组合才能解锁的检查项：%d 项" % multi)
print("=" * 74)

shutil.rmtree(g["SCRATCH_DIR"], ignore_errors=True)

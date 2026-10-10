# -*- coding: utf-8 -*-
"""2026-10-01：扫描「资料名」在全库（非 scripts/）的出现位置。

用途：改 `material_recognition._SUPP_ENTRIES` 的登记名前，先确认这个名
（旧名 / 新名）还被哪些文件/字段引用，避免改完留下孤儿口径。
只读。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", "output", "reports"}

NAMES = [
    "增值税纳税申报表（含留抵税额）",
    "土地出让/转让合同",
    "土地出让合同",
    "人员身份证与身份信息",
    "人员身份证信息",
    "车辆登记证与行驶证",
    "车辆登记证",
    "股权转让协议及补充协议",
    "过磅单与入库验收单",
    "土地增值税申报表",
    "能耗单据",
    "缴款凭证",
]

hits = {n: [] for n in NAMES}
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    for fn in filenames:
        if not fn.endswith((".py", ".json", ".html", ".md")):
            continue
        if fn.startswith("_") and fn.startswith("_"):
            pass
        p = os.path.join(dirpath, fn)
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        if rel.startswith("scripts/"):
            continue
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                txt = f.read()
        except OSError:
            continue
        for n in NAMES:
            if n in txt:
                hits[n].append(rel)

for n in NAMES:
    locs = hits[n]
    print("【%s】%d 处" % (n, len(locs)))
    for l in sorted(locs):
        print("     ", l)

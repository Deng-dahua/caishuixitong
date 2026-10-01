# -*- coding: utf-8 -*-
"""只读探针：抽样真账套进项发票明细行，看「成本/费用判定」到底能拿到哪些字段。

目的：判断「税收分类编码 / 计量单位」等**结构性证据**在真实数据里是否可得
（可得 ⇒ 可把「货物 vs 服务」第一刀做成有据可查的结构性裁决，而不是关键词猜）。
只读，不改任何产品代码。
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.getcwd())

from engine.domain_analysis import _extract_purchase_invoices  # noqa: E402
from engine.industry_resolver import normalize_industry_name  # noqa: E402

BASES = [("2", "/software"), ("3", "/x"), ("1", "")]
rows_all = []
for cid in ("1", "2", "3"):
    src = os.path.join("data", "uploads", cid)
    if not os.path.isdir(src):
        continue
    try:
        rows = _extract_purchase_invoices(cid) or []
    except Exception as exc:  # noqa: BLE001
        print("company %s 读取失败: %s" % (cid, exc))
        continue
    rows_all.extend(rows)
    print("company %s：进项明细 %d 行" % (cid, len(rows)))

print("合计 %d 行" % len(rows_all))
if not rows_all:
    sys.exit(0)

keys = Counter()
for r in rows_all:
    for k in (r or {}):
        keys[k] += 1
print("\n字段出现次数（总行数 %d）：" % len(rows_all))
for k, n in keys.most_common(40):
    print("  %-18s %d" % (k, n))


def _inv(t):
    return str(t or "")


print("\n=== 含 tax_code / 税收分类编码 的行数 ===")
n_tc = sum(1 for r in rows_all if _inv((r or {}).get("tax_code") or (r or {}).get("税收分类编码")))
print("  tax_code 非空：%d 行" % n_tc)

print("\n=== 前 6 行全字段样例 ===")
for i, r in enumerate(rows_all[:6]):
    print("--- row %d ---" % i)
    for k, v in (r or {}).items():
        print("    %s = %s" % (k, str(v)[:60]))

print("\n=== 单位字段样例（unit/单位/计量单位/规格）===")
seen = set()
for r in rows_all:
    for k in ("unit", "单位", "计量单位", "规格型号", "model", "spec"):
        v = str((r or {}).get(k) or "").strip()
        if v:
            seen.add((k, v[:12]))
    if len(seen) > 40:
        break
for k, v in sorted(seen)[:40]:
    print("  %s = %s" % (k, v))

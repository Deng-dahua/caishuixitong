# -*- coding: utf-8 -*-
"""只读探针：验证进项发票**结构性证据**（tax_code / biz_type / unit）在真实数据里是否可得。

背景（本轮根因之一）：
    main._parse_invoice_sheet 早已把表头映射成 `税收编码→tax_code`、「业务类型」→`biz_type`、
    「计量单位」→`unit`，但 account_classifier（成本/费用唯一权威）**一个都没读**；
    而 domain_analysis / pipeline / verified_rule_engine 读的是中文键「税收分类编码」——
    真实列名是「税收编码」，故这些 `tc.startswith("3")` 判据是**永远为假的死判据**。

本脚本只读，不改任何产品代码。
"""
import collections
import glob
import os
import sys
import warnings

sys.path.insert(0, os.getcwd())
warnings.filterwarnings("ignore")

from engine.workbook import workbook_scope  # noqa: E402
from main import _parse_invoice_sheet  # noqa: E402


def _open_sheet(path):
    ext = os.path.splitext(path)[1].lower()
    kw = ({"data_only": True} if ext == ".xlsx" else {}) if ext == ".xlsx" else {}
    if ext == ".xls":
        with workbook_scope(path) as wb:
            return wb.sheet_by_index(0)
    with workbook_scope(path, **kw) as wb:
        return wb[wb.sheetnames[0]]


stat = collections.Counter()
samples = collections.defaultdict(list)

for cid in ("1", "2", "3"):
    for f in sorted(glob.glob(os.path.join("data", "uploads", cid, "*"))):
        if not f.lower().endswith((".xlsx", ".xls")):
            continue
        try:
            parsed = _parse_invoice_sheet(_open_sheet(f), "进项")
        except Exception:
            parsed = None
        if not parsed:
            continue
        for r in (parsed.get("rows") or []):
            if not isinstance(r, dict):
                continue
            stat["rows"] += 1
            for k in ("tax_code", "biz_type", "unit", "goods", "spec", "qty"):
                v = str(r.get(k) or "").strip()
                if v:
                    stat[k] += 1
            tc = str(r.get("tax_code") or "").strip()
            if tc:
                stat["tc_prefix_" + tc[:1]] += 1
                if len(samples["tc"]) < 8:
                    samples["tc"].append((tc[:19], str(r.get("goods") or "")[:28]))
            bt = str(r.get("biz_type") or "").strip()
            if bt:
                head = bt.split("_", 1)[0].strip()
                stat["bt_head_" + head] += 1
                if len(samples["bt"]) < 10:
                    samples["bt"].append((bt[:30], str(r.get("goods") or "")[:24]))
            u = str(r.get("unit") or "").strip()
            if u:
                if len(samples["unit"]) < 12:
                    samples["unit"].append((u[:8], str(r.get("goods") or "")[:24], tc[:19]))

print("行数 =", stat["rows"])
for k in ("tax_code", "biz_type", "unit", "goods", "spec", "qty"):
    print("  %-9s 非空 = %d" % (k, stat[k]))
print("  税收编码首位:", {k[-1]: v for k, v in stat.items() if k.startswith("tc_prefix_")})
print("  业务类型前缀:", {k[-1]: v for k, v in stat.items() if k.startswith("bt_head_")})
print("\n税收编码样例 (code, 开票项目):")
for x in samples["tc"]:
    print("   ", x)
print("\n业务类型样例 (业务类型, 开票项目):")
for x in samples["bt"]:
    print("   ", x)
print("\n计量单位样例 (单位, 开票项目, 税收编码):")
for x in samples["unit"]:
    print("   ", x)

# -*- coding: utf-8 -*-
"""只读探针：把公司1 的**供应商集中度（CR1/CR3/CR5）与地域分布**算死。

用户质询："疑点24 供应商集中度与地域分布缺乏商业合理性，你也必须充分证据证明
到底是怎么缺乏商业合理性！！！！" —— 先算清事实，再谈判定。
"""
import json, os, sys
from collections import defaultdict
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE); sys.path.insert(0, os.path.join(BASE, 'scripts'))
from engine.fieldkit import invoice_no, seller_name, total as inv_total
from engine.numparse import to_number

P = os.path.join(BASE, 'scripts', 'four_reports', 'company_1_full.json')
d = json.load(open(P, encoding='utf-8'))
rows = []
for f in (d.get('file_results') or []):
    if str(f.get('type') or '') == 'purchase_invoice':
        rows.extend(f.get('_rows') or [])

# 按票号去重（一票多行）
by_inv = {}
for r in rows:
    sn = seller_name(r)
    if not sn: continue
    no = invoice_no(r) or ('__row__%d' % id(r))
    amt = abs(to_number(inv_total(r) or r.get('amount') or 0))
    k = (sn, no)
    if amt > by_inv.get(k, 0.0): by_inv[k] = amt

by_supplier = defaultdict(float)
for (sn, _), v in by_inv.items(): by_supplier[sn] += v
tot = sum(by_supplier.values())
srt = sorted(by_supplier.items(), key=lambda kv: -kv[1])
print('进项发票：%d 张（按票号去重）｜供应商 %d 家｜金额合计 %.2f' % (len(by_inv), len(by_supplier), tot))
print()
print('%-34s %14s %8s' % ('供应商', '金额', '占比'))
for n, v in srt[:8]:
    print('%-34s %14.2f %7.2f%%' % (n[:32], v, v / tot * 100))
print('  ...')
print()
cr = lambda k: sum(v for _, v in srt[:k]) / tot * 100
print('CR1 = %.2f%% | CR3 = %.2f%% | CR5 = %.2f%% | 供应商总数 = %d' % (cr(1), cr(3), cr(5), len(by_supplier)))
print()
# 地域（从名称反推省份）
try:
    from engine.geo_infer import infer_province as _prov
except Exception:
    _prov = None
from collections import Counter
geo = Counter(); geo_amt = defaultdict(float)
for n, v in by_supplier.items():
    p = _prov(n) if _prov else None
    geo[p or '未知'] += 1; geo_amt[p or '未知'] += v
print('地域分布（按金额）：')
for p, v in sorted(geo_amt.items(), key=lambda kv: -kv[1]):
    print('  %-8s %14.2f %7.2f%%  (%d家)' % (p, v, v / tot * 100, geo.get(p, 0)))

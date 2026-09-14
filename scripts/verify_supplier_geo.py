# -*- coding: utf-8 -*-
"""供应商集中度 / 地域分布判据核验（2026-09-14 重编后真实数据回归）。

同时跑两处口径，确认两处不再打架：
  ① VR016   engine.verified_rule_engine._scan_supplier_geo
  ② 供应链穿透 engine.domain_analysis._domain_supply_chain_deep（前3大集中度 / 地域群集）

用法：python scripts/verify_supplier_geo.py [company_id ...]
"""
import os, sys, io, json, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
REPO = r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong"
sys.path.insert(0, REPO)
import main
from engine.pipeline import _aggregate_invoices_by_no, _dedupe_cross_file_invoices
from engine.verified_rule_engine import _scan_supplier_geo, _province_of
from engine.domain_analysis import _domain_supply_chain_deep

COMPANIES = {"1": "深圳海更数字传媒有限公司", "3": "北京桦橙佳业商贸有限公司"}


def load(cid):
    up = os.path.join(REPO, "data", "uploads", cid)
    pur, sal = [], []
    for f in sorted(glob.glob(os.path.join(up, "*"))):
        if not os.path.isfile(f):
            continue
        ext = os.path.splitext(f)[1].lower()
        try:
            p = main._parse_excel_structured(f, ext, os.path.basename(f))
        except Exception:
            continue
        if not isinstance(p, dict):
            continue
        if p.get("type") == "purchase_invoice":
            pur += _aggregate_invoices_by_no(p.get("rows") or [], "进项")
        elif p.get("type") == "sales_invoice":
            sal += _aggregate_invoices_by_no(p.get("rows") or [], "销项")
    pur, _ = _dedupe_cross_file_invoices(pur)
    sal, _ = _dedupe_cross_file_invoices(sal)
    return pur, sal


for cid in (sys.argv[1:] or list(COMPANIES)):
    name = COMPANIES.get(cid, "公司" + cid)
    pur, sal = load(cid)
    print("=" * 78)
    print(f"公司{cid} {name}：进项 {len(pur)} 笔 / 销项 {len(sal)} 笔")
    print("本省判定 _province_of(name) =", _province_of(name))

    # ① VR016
    spec = {"id": "VR016", "name": "供应商集中度与地域分布核验", "required_sources": ["pur_invs"]}
    res = _scan_supplier_geo({"pur_invs": pur, "sal_invs": sal,
                              "target_entity": {"name": name}}, spec)
    print("-" * 78)
    print("【VR016 供应商集中度与地域分布】findings:", len(res))
    for f in res:
        print("  level=%s prio=%s" % (f.get("level"), f.get("priority")))
        print("  detail:", f.get("detail"))
        print("  metrics:", json.dumps(f.get("observed_metrics"), ensure_ascii=False)[:800])
    if not res:
        print("  → 未触发（未满足「金额≥100万 + 异地占比≥60% + 至少一项异常特征」的组合条件）")

    # ② 供应链穿透（集中度 / 名称群集 / 地域群集 / 双向交易）
    invs = ([dict(r, direction="进项") for r in pur]
            + [dict(r, direction="销项") for r in sal])
    fs = _domain_supply_chain_deep(invs, [], {"name": name})
    keys = ("前3大供应商", "地域群集", "名称群集", "单一供应商", "进销双向")
    hit = [f for f in fs if any(k in str(f.get("type", "")) for k in keys)]
    print("-" * 78)
    print("【供应链穿透·集中度与群集类】findings:", len(hit), "/ 全部", len(fs))
    for f in hit:
        print("  [%s] %s" % (f.get("level"), f.get("type")))
        print("      detail:", str(f.get("detail"))[:300])
    if not hit:
        print("  → 未触发（集中度家数不足 / 群集落在本市或低于门槛）")
print("=" * 78)

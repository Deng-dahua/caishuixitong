# -*- coding: utf-8 -*-
"""未触发红线排查：区分「正常沉默（数据无该信号）」与「★有信号却未触发（疑似检测器缺陷）」。

背景（见 caishuixitong-redline-engine skill「齐备性四层口径」）：
  4 家样本公司合计仅 39/89 红线进入 suspicions → 50 条从未触发。
  但「从未触发」≠「缺失」：必须逐条区分：
    · 正常沉默  —— 该公司数据里根本没有该场景的线索（如样本无出口业务 → 出口退税红线不动）
    · ★疑似缺陷 —— 线索（信号）在数据里**存在**，检测器却没产出发现（真漏风险）

判据（可自证来源）：
  · 数据来源：各 `scripts/four_reports/company_*_full.json` 的 `file_results[*]._rows`
    按 `type` 还原为 engine_data 的关键数据源（与 pipeline 的 _gap_data 同源同义）。
  · 信号来源：每条红线的 **`match_hints`**（红线自带的"命中线索"词表）+ 表驱动探测器的 `signals`。
  · 判级：任一样本公司数据命中 hint → 「★待查」（须人工核检测器为何未命中）；
          全部公司都无命中 → 「正常沉默」。
  ⚠ 局限：hint 命中只是**筛查信号**，不等于检测器必须触发（hint 也可能出现在无关上下文）。
    本脚本用于把"未知"收敛为"少数待查项"，最终结论仍须逐条看检测器代码。

用法：python scripts/_audit_unfired_redlines.py [--json out.json]
"""
import json
import os
import re
import sys
from collections import defaultdict, Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.tax_redlines import REDLINES  # noqa: E402

REPORTS = os.path.join(ROOT, "scripts", "four_reports")

# file_results.type → engine_data 键（与 pipeline 内部变量同义）
_TYPE2KEY = {
    "bank_statement": "bank_txs",
    "sales_invoice": "sal_invs",
    "purchase_invoice": "pur_invs",
    "input_vat_deduction": "pur_invs",
    "salary": "salaries",
    "social_security": "social_security",
    "housing_fund": "housing_fund",
    "trial_balance": "balances",
    "voucher": "vouchers",
    "vat_declaration": "tax_declarations",
    "cit_declaration": "tax_declarations",
    "stamp_duty": "tax_declarations",
    "financial_statements": "financial_statements",
    "contract": "contracts",
    "inventory": "inventory",
    "fixed_assets": "fixed_assets",
}


def load_company_data(cid):
    """从报告还原该公司数据 → (data_dict, text_blob)。"""
    p = os.path.join(REPORTS, "company_%d_full.json" % cid)
    if not os.path.exists(p):
        return None, ""
    d = json.load(open(p, encoding="utf-8"))
    data = defaultdict(list)
    for f in (d.get("file_results") or []):
        key = _TYPE2KEY.get(str(f.get("type") or ""))
        if not key:
            continue
        for row in (f.get("_rows") or []):
            data[key].append(row)
    txt = []
    for k, rows in data.items():
        for r in rows:
            if isinstance(r, dict):
                txt.append(" ".join(str(v) for v in r.values()))
            else:
                txt.append(str(r))
    return dict(data), "\n".join(txt)


def fired_ids(cid):
    """该公司进入 suspicions 的红线 id 集合。"""
    p = os.path.join(REPORTS, "company_%d_full.json" % cid)
    if not os.path.exists(p):
        return set()
    d = json.load(open(p, encoding="utf-8"))
    rd = ((d.get("comprehensive") or {}).get("redline_detection")
          or d.get("redline_detection") or {})
    return {x.get("redline_id") for x in (rd.get("suspicions") or []) if x.get("redline_id")}


# 检测器归属（源码中出现 redline_id 字面量的文件）
def detector_owners():
    pat = re.compile(r'redline_id[^\n]{0,8}?(RL-[A-Z0-9-]+)')
    owners = defaultdict(set)
    for base in (os.path.join(ROOT, "engine"), os.path.join(ROOT, "scripts"), ROOT):
        if not os.path.isdir(base):
            continue
        for fn in os.listdir(base):
            if not fn.endswith(".py"):
                continue
            try:
                t = open(os.path.join(base, fn), encoding="utf-8").read()
            except Exception:
                continue
            for m in pat.finditer(t):
                owners[m.group(1)].add(fn)
    return owners


def table_signals():
    """表驱动探测器的信号词表（redline_id → signals）。"""
    out = {}
    for mod_name, attr in (("engine.special_redline_detectors", "SPECS"),
                           ("engine.gap_tax_obligations", "SPECS")):
        try:
            mod = __import__(mod_name, fromlist=[attr])
            for s in getattr(mod, attr):
                rid = s.get("redline_id")
                if not rid:
                    continue
                kws = list(s.get("signals") or []) + list(s.get("presence_signals") or [])
                out.setdefault(rid, []).extend(kws)
        except Exception:
            pass
    return out


def main():
    cids = [1, 2, 3, 4]
    datas, blobs, fired = {}, {}, {}
    for c in cids:
        datas[c], blobs[c] = load_company_data(c)
        blobs[c] = blobs[c] or ""
        fired[c] = fired_ids(c)

    any_fired = set().union(*fired.values()) if fired else set()
    all_ids = [r["id"] for r in REDLINES]
    never = [i for i in all_ids if i not in any_fired]

    owners = detector_owners()
    tbl = table_signals()
    by_id = {r["id"]: r for r in REDLINES}

    print("红线总数 %d｜4 家样本触发过 %d｜从未触发 %d"
          % (len(all_ids), len(any_fired), len(never)))
    print("各公司触发数：%s" % {c: len(fired[c]) for c in cids})
    print()

    to_check, silent = [], []
    for rid in never:
        rl = by_id[rid]
        kws = list(rl.get("match_hints") or []) + list(tbl.get(rid) or [])
        kws = [k for k in dict.fromkeys(kws) if k]
        hits = {}
        for c in cids:
            blob = blobs.get(c) or ""
            h = [k for k in kws if k and k in blob]
            if h:
                hits[c] = h[:3]
        rec = (rid, rl.get("name", ""), sorted(owners.get(rid) or []), kws[:4], hits)
        (to_check if hits else silent).append(rec)

    print("=== ★ 待查：数据里有信号却未触发（%d 条）——疑似检测器缺陷 ===" % len(to_check))
    for rid, name, own, kws, hits in to_check:
        print("  %s | %s" % (rid, name[:40]))
        print("      检测器: %s" % (", ".join(own) or "(无专属检测器/仅兜底)"))
        print("      命中: %s" % json.dumps(hits, ensure_ascii=False))
    print()
    print("=== 正常沉默：全部样本都无该信号（%d 条）===" % len(silent))
    for rid, name, own, kws, hits in silent:
        print("  %s | %s" % (rid, name[:44]))

    out = {
        "never_fired": never,
        "to_check": [{"id": r[0], "name": r[1], "owners": r[2], "hits": r[4]} for r in to_check],
        "silent": [r[0] for r in silent],
        "fired_per_company": {str(c): sorted(fired[c]) for c in cids},
    }
    op = os.path.join(ROOT, "scripts", "_unfired_redlines.json")
    json.dump(out, open(op, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n[OK] 已写出 %s" % op)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""专项探测器「有信号却未触发」真因探针（2026-10-01）

背景：`scripts/_audit_unfired_redlines.py` 用红线自带的 match_hints 做屏幕，
会把「hint 在全部文本里出现」误判成「检测器应该触发」。二者口径不同：
  · 屏幕（hint）      —— 在 all 文本里搜词；
  · 检测器（SPECS）   —— 按 spec 自己的 `source`（sales/purchase/all）取文本，
                         再过 `require` / `decl_keywords` / `mode=absence` 等闸。
所以「屏幕命中但检测器静默」多数是**精度护栏在起作用**（如 RL-VAT-009 只看销售侧），
真正要修的只有「SPECS 里根本没有该 redline」或「信号在 spec 的 source 文本里确实存在却没产出」。

本探针口径（可自证）：
  · 数据源 = `scripts/four_reports/company_*_full.json` 的 file_results._rows 还原
    （复用 `_audit_unfired_redlines.load_company_data`，与 pipeline 的 _gap_data 同源同义）。
  · 执行真实检测器 `run_special_redline_detection(engine_data)`，取实际产出的 redline_id。
  · 对未产出的 redline，逐条打印：spec.source 选中的文本里能否命中 spec.signals、
     require 是否齐、decl_keywords 是否命中（被抑制）。

用法：python scripts/_probe_detector_coverage.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from engine.gap_risk_detectors import _dump  # noqa: E402
from engine.special_redline_detectors import SPECS, run_special_redline_detection  # noqa: E402
from _audit_unfired_redlines import load_company_data  # noqa: E402

COMPANIES = (1, 2, 3, 4)


def spec_texts(data):
    """复刻 run_special_redline_detection 的 texts 构造（保持同源，勿各写一份）。"""
    _NL = chr(10)
    vch = _dump(data.get("vouchers"))
    bal = _dump(data.get("balances"))
    bank = _dump(data.get("bank_txs"))
    invs = _dump(data.get("sal_invs")) + _NL + _dump(data.get("pur_invs"))
    sal = _dump(data.get("salaries"))
    inv = _dump(data.get("inventory"))
    decl = _dump(data.get("tax_declarations"))
    fa = _dump(data.get("fixed_assets"))
    ct = _dump(data.get("contracts"))
    ss = _dump(data.get("social_security"))
    hf = _dump(data.get("housing_fund"))
    _sale = _dump(data.get("sal_invs"))
    _pur = _dump(data.get("pur_invs"))
    return {
        "all": _NL.join([vch, bal, bank, _sale, _pur, sal, inv, decl, fa, ct, ss, hf]),
        "sales": _NL.join([_sale, ct]),
        "purchase": _NL.join([_pur, vch, bal, fa, ct]),
    }


def reason_for(spec, texts, data, fired_by):
    rid = spec["redline_id"]
    if rid in fired_by:
        return "已产出", ""
    src = texts.get(spec.get("source", "all"), texts["all"])
    signals = [k for k in spec.get("signals", []) if k and k in src]
    if not signals:
        # 再确认是否只是「屏幕口径 vs 检测器口径」的差（hint 在 all 里有、source 里没有）
        any_all = [k for k in spec.get("signals", []) if k and k in texts["all"]]
        return "信号未命中（精度护栏）", "all 里有 %s，但 spec.source=%s 里没有" % (
            "、".join(any_all[:4]) or "无", spec.get("source", "all"))
    req = [k for k in spec.get("require", []) if k not in texts["all"]]
    if req:
        return "require 未齐", "缺上下文：" + "、".join(req)
    dl = spec.get("decl_keywords") or []
    blocked = [k for k in dl if k in _dump(data.get("tax_declarations"))]
    if blocked:
        return "被 decl_keywords 抑制", "申报资料里已见：" + "、".join(blocked)
    if spec.get("mode") == "absence":
        pres = [k for k in spec.get("presence_signals", []) if k in texts["all"]]
        akey = spec.get("absence_data_key")
        if not pres:
            return "缺席型未见 presence", ""
        if akey and data.get(akey):
            return "缺席型：资料已提供", ""
    return "★真漏（信号在 source 里却未产出）", "命中：" + "、".join(signals[:4])


def main():
    fired_by_company = {}
    loaded = {}
    for cid in COMPANIES:
        d, _ = load_company_data(cid)
        if not d:
            loaded[cid] = None
            continue
        loaded[cid] = d
        res = run_special_redline_detection(d)
        fired_by_company[cid] = {f.get("redline_id") for f in res}
        print("company %d → 专项探测器产出 %d 条" % (cid, len(res)))
    all_fired = set()
    for s in fired_by_company.values():
        all_fired |= s
    print("\n专项探测器全量命中 redline：%d 条" % len(all_fired))

    print("\n=== 逐 spec 归因 ===")
    for spec in SPECS:
        rows = []
        for cid in COMPANIES:
            d = loaded.get(cid)
            if not d:
                continue
            txts = spec_texts(d)
            fired_here = fired_by_company.get(cid, set())
            why, note = reason_for(spec, txts, d, fired_here)
            rows.append((cid, why, note))
        kinds = {w for _, w, _ in rows}
        if len(kinds) == 1 and "已产出" not in kinds and "★真漏（信号在 source 里却未产出）" not in kinds:
            continue  # 全部同源（都是精度护栏/信号未命中），非本轮重点
        print("\n[%s] %s" % (spec["redline_id"], spec["topic"]))
        for cid, why, note in rows:
            print("   company %d: %s  %s" % (cid, why, note))


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""「资料齐备的检查项，是否真的在引擎里跑了」审计（2026-10-06）。

═══ 为什么需要（用户原话）═══
用户要求「一键分析按钮必须执行100%覆盖率」「能查的全查完即可」，
并追问过：「那 84 项资料齐备的检查，是否都在引擎里真跑了？」

`analysis_coverage.build_coverage()` 的 `executed` 原定义为
`len(items) - len(blocked)`，而 `blocked := missing 非空`、
`missing := 声明的 required_sources 里 engine_data 没数据` ——
它证明的只是「**声明所需资料本轮齐备**」，**不等于**「该项被引擎执行过」。

═══ 本脚本做什么 ═══
对 `company_*_full.json` 逐家复算覆盖清单（与 pipeline 同源同参），
并把结果与 `run_verified_rules()` 的**执行回执**做交叉，断言四条不变量：

  I1 **有回执才算执行**：判为"已执行"的原子规则，回执状态必须 ∈ {triggered,
     completed_not_triggered}。违反 ⇒ 覆盖率虚报。
  I2 **互斥**：同一项不得同时进 `executed_items` 与 `blocked_items`。
  I3 **无孤规则**：`VERIFIED_RULE_CATALOG` 里每条都必须有 `_SCANNERS` 扫描器
     （历史事故：14 项指标 7 项零消费点 —— "看着有这项、实际从不检查"）。
  I4 **业态门槛不虚报**：`_spec_applies_to_entity` 为假的规则不得进分母
     （否则服务业会被算"生产用能耗消耗"这类本业态不适用项）。
  I5 **不得"假缺资料"**：回执证明 `triggered/completed_not_triggered` 的规则，
     不得再出现在 `blocked_items` 里（否则会让企业去补一份"其实已经查过"的资料）。
     ⚠ 例外：不在 `VERIFIED_RULE_CATALOG` 里的循环后兜底规则（如 VR051 取证责令单）
     本就不是覆盖项，不进分母，故不计入本判据。

═══ 数据来源与**已知还原边界**（必须如实标注，否则会自造假缺陷）═══
`file_results[*]._rows` 按 type 还原 → engine_data（复用
`_audit_unfired_redlines.load_company_data`，与 pipeline 的 `_gap_data` 同源同义）。
不来自文件、由 pipeline/context 注入的运行时源按线上语义补齐（见 `_source_aliases`）。
**公司 #1 的复算结果与产物 `analysis_coverage` 逐字相同（174/84/90）**，
即还原保真度经实测校验；#2/#3 产物为 9-30 生成（红线库已从 89 → 91 条），
其旧数字仅供趋势参考，不作结论依据。

═══ 局限 ═══
只覆盖「原子规则 + 税务指标」两段的执行性；**税务红线的可执行性另有权威脚本**
（`_audit_redline_coverage.py` / `_probe_detector_coverage.py`），此处不另造一套判定
—— 避免"同一概念两处实现"。

本脚本**只读**：不改引擎、不写业务数据；唯一写入是 `--json` 输出。

用法：python scripts/_audit_executed_items.py [--json out.json] [--companies 1,2,3]
"""
import argparse
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

REPORTS = os.path.join(ROOT, "scripts", "four_reports")

# file_results.type → engine_data 键（与 `_audit_unfired_redlines` 同一张表，勿各写一份）
from _audit_unfired_redlines import load_company_data  # noqa: E402

#: pipeline/context 注入、**不来自上传文件**的运行时源 —— 还原时必须按线上语义补上
_RUNTIME_DEFAULTS = {
    # engine/context.py:AuditContext.__init__ 的默认画像（非空 dict ⇒ get() 恒为真）
    "company_profile": {"industry": "", "biz_model": "", "scale": "",
                        "has_manufacturing": False, "has_trading": False},
}


def _source_aliases(data):
    """把还原出来的键补齐成 `run_verified_rules` 认得的键（同源同义，仅别名）。"""
    d = dict(data)
    d.setdefault("trial_balance", d.get("balances") or [])
    d.setdefault("inventory_ledger", d.get("inventory") or [])
    d.setdefault("declaration", d.get("tax_declarations") or [])
    for k, v in _RUNTIME_DEFAULTS.items():
        d.setdefault(k, v)
    return d


def build_engine_data(product, cid):
    """从产物还原本轮 engine_data（与 pipeline 同源同参）。"""
    raw, _blob = load_company_data(cid)
    ed = _source_aliases(raw or {})
    ed["invoices"] = list((raw or {}).get("sal_invs") or [])
    ed["target_entity"] = product.get("target_entity") or {}
    try:
        from engine.enterprise_report import _doc_covered_categories
        ed["_available_materials"] = sorted(
            _doc_covered_categories({"file_results": product.get("file_results") or []}))
    except Exception as exc:            # noqa: BLE001 —— 留痕，不静默
        print("  !! _doc_covered_categories 失败: %s" % exc)
        ed["_available_materials"] = []
    return ed


def audit_company(cid):
    p = os.path.join(REPORTS, "company_%d_full.json" % cid)
    if not os.path.exists(p):
        return None
    product = json.load(open(p, encoding="utf-8"))

    from engine.analysis_coverage import build_coverage
    from engine.verified_rule_engine import (
        VERIFIED_RULE_CATALOG, _SCANNERS, _spec_applies_to_entity, run_verified_rules,
    )
    from engine.financial_analyzer import TAX_AUDIT_INDICATORS
    from engine.analysis_coverage import _IND_SRC

    ed = build_engine_data(product, cid)
    vr = run_verified_rules(ed)
    execs = {str(e.get("rule_id")): e for e in (vr.get("executions") or [])}
    cov = build_coverage(ed, executions=vr.get("executions"))
    stale = product.get("analysis_coverage") or {}

    # ── 不变量 ──
    no_scanner = sorted({r["id"] for r in VERIFIED_RULE_CATALOG} - set(_SCANNERS.keys()))
    te = ed.get("target_entity") or {}
    gate_skip = sorted(r["id"] for r in VERIFIED_RULE_CATALOG
                       if not _spec_applies_to_entity(r, te))
    item_ids = {str(it.get("id")) for it in cov["items"] if it.get("kind") == "原子规则"}
    gate_leak = [x for x in gate_skip if x in item_ids]        # I4：行业跳过却进分母
    bad_exec = [it for it in cov["executed_items"]
                if it.get("kind") == "原子规则"
                and str(execs.get(str(it.get("id")), {}).get("status") or "")
                not in ("triggered", "completed_not_triggered")]   # I1
    both = {id(it) for it in cov["executed_items"]} & {id(it) for it in cov["blocked_items"]}  # I2
    # I5：回执说跑过、却被列为"缺资料" ⇒ 会让企业去补一份"其实已查过"的资料
    _ran = {rid for rid, e in execs.items()
            if str(e.get("status") or "") in ("triggered", "completed_not_triggered")}
    _blocked_ids = {str(it.get("id")) for it in cov["blocked_items"]}
    false_missing = sorted((_ran & _blocked_ids) & {r["id"] for r in VERIFIED_RULE_CATALOG})

    # ── 税务指标：逐项给出数据依赖与是否具备判定条件（数据来源 _IND_SRC，勿各写一份）──
    ind_rows = []
    for k, meta in (TAX_AUDIT_INDICATORS or {}).items():
        need = _IND_SRC.get(k) or ["trial_balance"]
        if "__cross_period__" in need:
            ind_rows.append({"id": k, "need": need, "ok": False,
                             "note": "跨期指标：单期资料无法计算（已在覆盖清单声明）"})
            continue
        miss = [s for s in need if not (len(ed.get(s) or []) if not isinstance(ed.get(s), (str, dict))
                                        else bool(ed.get(s)))]
        ind_rows.append({"id": k, "need": need, "ok": not miss,
                         "note": ("缺 " + "/".join(miss)) if miss else "资料齐备"})

    return {
        "company": cid,
        "name": str(te.get("name") or ""),
        "industry": str(te.get("industry") or ""),
        "biz_model": str(te.get("biz_model") or ""),
        "coverage_now": {"total": cov["total"], "executed": cov["executed"],
                         "blocked": cov["blocked"], "not_executed": cov["not_executed"],
                         "ratio": cov["executed_ratio"]},
        "coverage_stale": {"total": stale.get("total"), "executed": stale.get("executed"),
                           "blocked": stale.get("blocked")},
        "run_status_counts": dict(Counter(str(e.get("status")) for e in execs.values())),
        "invariants": {
            "I1_executed_without_receipt": [it.get("id") for it in bad_exec],
            "I2_executed_and_blocked": len(both),
            "I3_catalog_without_scanner": no_scanner,
            "I4_industry_skip_leaked_into_denominator": gate_leak,
            "I5_ran_but_reported_missing": false_missing,
        },
        "not_executed_items": [{"id": it.get("id"), "name": it.get("name"),
                                "basis": it.get("executed_basis")}
                               for it in cov["not_executed_items"]],
        "indicators": ind_rows,
        "blocked_by_kind": dict(Counter(it["kind"] for it in cov["blocked_items"])),
        "executed_by_kind": dict(Counter(it["kind"] for it in cov["executed_items"])),
        "summary_text": cov.get("summary_text") or "",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--companies", default="1,2,3")
    args = ap.parse_args()

    out, bad = [], 0
    for cid in [int(x) for x in args.companies.split(",") if x.strip()]:
        s = audit_company(cid)
        if not s:
            continue
        out.append(s)
        inv = s["invariants"]
        print("=" * 80)
        print("公司 #%d %s｜%s / %s" % (cid, s["name"], s["industry"], s["biz_model"]))
        print("  覆盖清单（现算）: total=%s executed=%s blocked=%s not_executed=%s ratio=%s"
              % (s["coverage_now"]["total"], s["coverage_now"]["executed"],
                 s["coverage_now"]["blocked"], s["coverage_now"]["not_executed"],
                 s["coverage_now"]["ratio"]))
        print("  覆盖清单（产物旧值）: total=%s executed=%s blocked=%s"
              % (s["coverage_stale"]["total"], s["coverage_stale"]["executed"],
                 s["coverage_stale"]["blocked"]))
        print("  执行回执状态分布: %s" % s["run_status_counts"])
        print("  按 kind：executed=%s blocked=%s" % (s["executed_by_kind"], s["blocked_by_kind"]))
        print("  ── 五条不变量 ──")
        for tag, key in (("I1 已执行却无有效回执", "I1_executed_without_receipt"),
                         ("I2 同时记已执行与缺资料", "I2_executed_and_blocked"),
                         ("I3 目录有规则却没有扫描器", "I3_catalog_without_scanner"),
                         ("I4 业态不适用却进分母", "I4_industry_skip_leaked_into_denominator"),
                         ("I5 已跑却报缺资料", "I5_ran_but_reported_missing")):
            v = inv[key]
            n = v if isinstance(v, int) else len(v)
            if n:
                bad += 1
            print("     %-26s %s %s" % (tag, "OK" if not n else "★违反", v or ""))
        if s["not_executed_items"]:
            print("  ★ 资料齐备却未取得执行回执：")
            for it in s["not_executed_items"]:
                print("     - %s %s｜%s" % (it["id"], str(it["name"])[:34], it["basis"]))
        nind = len([r for r in s["indicators"] if not r["ok"]])
        print("  税务指标 14 项：不具备判定条件 %d 项" % nind)
        for r in s["indicators"]:
            if not r["ok"]:
                print("     - %s｜%s" % (r["id"], r["note"]))
    print("=" * 80)
    print("总判定：%s（违反项数 %d）" % ("PASS" if not bad else "FAIL", bad))

    if args.json:
        json.dump(out, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("[OK] 已写出 %s" % args.json)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

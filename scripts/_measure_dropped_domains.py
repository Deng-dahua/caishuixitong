# -*- coding: utf-8 -*-
"""实测：域产出 vs 报告最终发现 —— 找出「算出来了但进不了报告」的域（与工资社保同类）。

背景：报告最终 all_findings 由 `seal_governed_findings(_scenario_execution)` **覆盖**，
只保留 `_scenario_governed=True` 的条目。因此域里 append 的发现**不等于**进了报告。
工资社保域正是这样被吞掉的（域不在 `_objective_domain_keys` 里）。

本脚本用真实资料跑一次全量分析，逐域对照：
    domain_summary 里该域产出了几条  vs  报告 all_findings 里同类型还剩几条
差异即为「被吞掉的发现」。

用法：
    python scripts/_measure_dropped_domains.py [company_id] [--scratch <scratch_cid>]
默认读取 data/uploads/<company_id>/（只读，不移动任何文件）。
"""
import json
import os
import shutil
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)


def run(cid):
    import main
    from database import SessionLocal
    db = SessionLocal()
    try:
        return main._execute_tax_risk_analysis(cid, db)
    finally:
        db.close()


def measure(cid):
    res = run(cid)
    if not isinstance(res, dict) or not res.get("ok"):
        print("! 分析未成功:", json.dumps(res, ensure_ascii=False)[:400] if isinstance(res, dict) else res)
        return None
    rep = res.get("report") or {}
    final = rep.get("all_findings") or []
    final_types = {str(f.get("type") or "") for f in final if isinstance(f, dict)}
    doms = rep.get("domain_summary") or []

    rows = []
    for d in doms:
        if not isinstance(d, dict):
            continue
        fs = [f for f in (d.get("findings") or []) if isinstance(f, dict)]
        if not fs:
            continue
        kept = [f for f in fs if str(f.get("type") or "") in final_types]
        rows.append({
            "domain": str(d.get("domain") or ""),
            "produced": len(fs),
            "kept": len(kept),
            "dropped": len(fs) - len(kept),
            "dropped_types": [str(f.get("type"))[:34] for f in fs
                              if str(f.get("type") or "") not in final_types][:6],
        })
    rows.sort(key=lambda r: -r["dropped"])
    return {"cid": cid, "final_count": len(final), "rows": rows,
            "files": rep.get("files_count"),
            "domain_count": len([r for r in rows])}


def main():
    cid = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
    print(f"以 company_id={cid} 跑全量分析（只读 data/uploads/{cid}/）…")
    try:
        m = measure(cid)
    except Exception:
        print("分析异常：" + traceback.format_exc()[-1200:])
        return 1
    if not m:
        return 1
    print(f"\n报告最终发现 {m['final_count']} 条（文件 {m['files']} 个，涉及 {m['domain_count']} 个域）")
    print("=" * 78)
    print("%-24s %6s %6s %6s  %s" % ("域", "产出", "进报告", "被吞", "被吞的发现（前几项）"))
    print("-" * 78)
    tot_p = tot_d = 0
    for r in m["rows"]:
        tot_p += r["produced"]
        tot_d += r["dropped"]
        flag = "⚠" if r["dropped"] else "✓"
        print("%s %-22s %6d %6d %6d  %s" % (
            flag, r["domain"][:22], r["produced"], r["kept"], r["dropped"],
            "、".join(r["dropped_types"])))
    print("-" * 78)
    print(f"合计：域产出 {tot_p} 条，被吞 {tot_d} 条（{tot_d/max(tot_p,1):.0%}）")
    print("\n注：'被吞'= 域产出的 type 未出现在报告最终 all_findings 中。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

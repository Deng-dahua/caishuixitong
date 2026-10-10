# -*- coding: utf-8 -*-
"""追踪：本轮（company_1）仅靠软匹配(match_mode=matched)触发的红线，其真实来源发现是谁。
目的：为「把 matched 提升为 declared（补 redline_id + constituent_hits）」提供精确接线目标，
避免认领到错误的生产者（认领错生产者→实际发现仍是 matched，白做）。
"""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine.tax_redlines import REDLINES
from engine import verified_rule_engine as vre

_RL_BY_ID = {r["id"]: r for r in REDLINES}


def main():
    import main
    from database import SessionLocal
    db = SessionLocal()
    try:
        res = main._execute_tax_risk_analysis(1, db)
    finally:
        db.close()
    if not isinstance(res, dict) or not res.get("ok"):
        print("! 分析未成功")
        return 2

    rep = res.get("report", {}) or {}
    susps = (rep.get("comprehensive") or {}).get("redline_detection") or {}
    susps = susps.get("suspicions") or []

    print("== 仅靠软匹配触发的红线 → 来源发现（接线目标）==")
    out = []
    for s in susps:
        if not isinstance(s, dict) or s.get("match_mode") != "matched":
            continue
        rid = s.get("redline_id")
        rl = _RL_BY_ID.get(rid, {})
        ncons = len(rl.get("constituents") or [])
        sfs = s.get("supporting_findings") or []
        types = sorted({(f.get("type"), f.get("domain")) for f in sfs if isinstance(f, dict)})
        print(f"\n● {rid}  {s.get('redline_name')}  (要件数={ncons}, verdict={s.get('verdict')})")
        for t, d in types:
            print(f"    来源 type={t!r} domain={d!r}")
        # 候选 VR（名称/关键词重叠）
        cands = []
        for vr in vre.VERIFIED_RULE_CATALOG:
            vn = vr.get("name", "")
            if any(k in vn for k in (rl.get("name", "")[:6],)) or any(
                k in rl.get("name", "") for k in (vn[:6],)):
                cands.append(vr["id"])
        if cands:
            print(f"    候选VR(名称重叠): {cands}")
        out.append({"rid": rid, "name": s.get("redline_name"), "ncons": ncons,
                    "source_types": types, "cand_vr": cands})

    with open("scripts/_trace_matched_sources.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("\n[落盘] scripts/_trace_matched_sources.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

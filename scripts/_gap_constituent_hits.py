# -*- coding: utf-8 -*-
"""跑真实账套（cid=1，company_1 全量资料）一次分析，产出「已检测但无 constituent_hits」的
逐条判定缺口清单。只读运行、不删除任何数据。

输出两类：
  · DETECTED_WIRED  ：触发且已带 constituent_hits 的红线
  · DETECTED_UNWIRED：触发但 constituent_hits 为空/缺失（= 本次要补的缺口）
  · 另列未检测到的红线（供参考，不强制补）。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine.tax_redlines import REDLINES

CID = 1  # company_1 标准账套


def main():
    import main
    from database import SessionLocal
    db = SessionLocal()
    try:
        res = main._execute_tax_risk_analysis(CID, db)
    finally:
        db.close()

    if not isinstance(res, dict) or not res.get("ok"):
        print("! 分析未成功:", json.dumps(res, ensure_ascii=False)[:800] if isinstance(res, dict) else res)
        return 1

    rep = res.get("report") or {}
    # ★ 正确层：报告实际消费的是 comprehensive.redline_detection.suspicions[].argumentation.constituent_hits
    #   （redline_engine 由 finding 顶层 constituent_hits 经 build_argumentation 搬入 argumentation）。
    #   读 all_findings 顶层会误判（部分红线在 suspicion 层才带 hits）。
    susps = (rep.get("comprehensive") or {}).get("redline_detection") or {}
    susps = susps.get("suspicions") or []
    print(f"红线判定 suspicions 数: {len(susps)}")

    def _hits_of(s):
        arg = s.get("argumentation") or {}
        ch = arg.get("constituent_hits") if isinstance(arg, dict) else None
        if not isinstance(ch, list):
            ch = s.get("constituent_hits") or []
        return [c for c in ch if isinstance(c, dict) and c.get("index")]

    wired, unwired = [], []
    for s in susps:
        if not isinstance(s, dict):
            continue
        rid = s.get("redline_id")
        if not rid:
            continue
        ch = _hits_of(s)
        info = {
            "redline_id": rid,
            "level": s.get("conclusion_grade") or (s.get("argumentation") or {}).get("conclusion_grade"),
            "name": s.get("redline_name"),
            "domain": s.get("domain"),
            "hits": len(ch),
        }
        (wired if ch else unwired).append(info)

    by_id = {r["id"]: r for r in REDLINES}
    print("\n=== DETECTED_WIRED（已带逐条判定，%d 条红线）===" % len({w['redline_id'] for w in wired}))
    for w in sorted(wired, key=lambda x: str(x['redline_id'])):
        print(f"  {w['redline_id']:<12} 命中{w['hits']}项 等级={w['level']:<4} {w['name']}")

    print("\n=== DETECTED_UNWIRED（已检测但缺 constituent_hits = 本次缺口，%d 条红线）===" % len({u['redline_id'] for u in unwired}))
    for u in sorted(unwired, key=lambda x: str(x['redline_id'])):
        print(f"  {u['redline_id']:<12} 等级={u['level']:<4} 域={u['domain']} {u['name']}")

    # 参考：未检测到（但代码已接线/未接线）
    detected_ids = {w['redline_id'] for w in wired} | {u['redline_id'] for u in unwired}
    not_detected = [r["id"] for r in REDLINES if r["id"] not in detected_ids]
    print("\n=== 本次账套未检测到的红线（%d 条，供参考）===" % len(not_detected))
    print("  " + "、".join(not_detected))

    # 汇总缺口红线按类别分桶（发票/申报/费用/其他）供优先级
    def bucket(rid):
        p = rid.split("-")[1]
        return {"VAT": "发票类", "PTY": "发票类(平台/其他)", "INC": "申报类", "CIT": "申报类",
                "COST": "费用类", "PAY": "费用类(薪酬)", "FUND": "资金类", "INV": "存货类",
                "AST": "资产类", "SPT": "凭证类", "OTH": "其他类"}.get(p, "其他类")
    from collections import Counter
    bc = Counter(bucket(u["redline_id"]) for u in unwired)
    print("\n=== 缺口按类别（用于 发票>申报>费用 优先级）===")
    for k, v in bc.items():
        print(f"  {k}: {v} 条")

    # ★ 2026-09-29（#448）：真实接线真相 = 运行时 match_mode
    #   declared = 有发现自声明 redline_id（真实检测器）
    #   matched  = 仅靠 match_hints 软匹配触达（发现级信号，未逐要件独立核对）
    mc = Counter(s.get("match_mode") for s in susps if isinstance(s, dict))
    print("\n=== match_mode 分布（declared=真实检测器 / matched=仅软匹配）===")
    print("  ", dict(mc))
    _matched = [s for s in susps if isinstance(s, dict) and s.get("match_mode") == "matched"]
    _mids = sorted({s.get("redline_id") for s in _matched if s.get("redline_id")})
    print("\n=== 仅靠软匹配(matched)触发的红线（#448 优先接线目标，%d 条）===" % len(_mids))
    for _s in sorted(_matched, key=lambda x: str(x.get("redline_id"))):
        print(f"  {_s.get('redline_id'):<12} 域={_s.get('domain')} {_s.get('redline_name')}")
    _declared_ids = sorted({s.get("redline_id") for s in susps
                            if isinstance(s, dict) and s.get("match_mode") == "declared"
                            and s.get("redline_id")})

    # ★ 2026-09-29（#448）：逐要件「独立核对」三态统计 —— 这才是"未接线"的真相口径。
    #   not_checked = 该要件的独立数据源本轮未取得（数据源状态非"已取得"）。
    from engine.constituent_checkpoint import build_constituent_checkpoints
    cc = Counter()
    nc_by_redline = {}
    nc_by_status = Counter()
    for s in susps:
        if not isinstance(s, dict):
            continue
        for cp in build_constituent_checkpoints(s):
            concl = cp.get("_conclusion")
            cc[concl] += 1
            if concl == "not_checked":
                rid = s.get("redline_id")
                nc_by_redline[rid] = nc_by_redline.get(rid, 0) + 1
                nc_by_status[cp.get("数据源状态") or "未知"] += 1
    print("\n=== 逐要件独立核对三态（#448 真实口径）===")
    print("  ", dict(cc))
    print("  not_checked 按数据源状态:", dict(nc_by_status))
    print("  未单独核对要件数 top:", sorted(nc_by_redline.items(), key=lambda kv: -kv[1])[:15])

    # 落盘
    out = {"wired": wired, "unwired": unwired, "not_detected": not_detected,
           "bucket_counts": dict(bc),
           "match_mode_counts": dict(mc),
           "soft_matched_ids": _mids,
           "declared_ids": _declared_ids}
    with open("scripts/_gap_constituent_hits.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("\n[落盘] scripts/_gap_constituent_hits.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

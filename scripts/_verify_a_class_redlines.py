# -*- coding: utf-8 -*-
"""A 类新增 6 条红线验收（2026-09-29）。

端到端验证：
  ① 6 条新红线定义齐全（constituents 末项出罪 / justifications / evidence_chain 含反证 /
     required_materials / legal_basis / remedy / match_hints 均非空）；
  ② 5 个相关闸门对其 0 ERROR（出罪要件覆盖 / 反证对齐 / 准入 / 兜底合法 / 法条时效）；
  ③ 可达性：match_redline_grounded 给定「名称主词 + 部分所需资料」应能命中；
  ④ 端到端：run_redline_detection 对声明 redline_id 的合成发现能产出 suspicion，
     且 constituent_hits 由 _DEFAULT_HIT_INDEX 兜底补齐（报告 (A)+(B) 闭环）。
用法：PYTHONPATH=. python scripts/_verify_a_class_redlines.py
"""
NEW_IDS = ["RL-CIT-008", "RL-CIT-009", "RL-INV-004",
           "RL-VAT-012", "RL-SPT-012", "RL-SPT-013"]
# ★ 与 engine/redline_engine.check_default_hit_index_valid 的 exempt_keys 保持一致（权威判定）
EXEMPT_KEYS = ("不属于", "豁免", "正当情形", "非个人", "合法")


def main():
    from engine.tax_redlines import REDLINES, match_redline_grounded
    from engine.redline_engine import _DEFAULT_HIT_INDEX, run_redline_detection
    import tools.audit_consistency as ac

    by_id = {r["id"]: r for r in REDLINES}
    errs = []

    # ① 结构齐全
    for rid in NEW_IDS:
        if rid not in by_id:
            errs.append(f"{rid} 未进入 REDLINES"); continue
        r = by_id[rid]
        cons = r.get("constituents") or []
        if not cons:
            errs.append(f"{rid} constituents 为空"); continue
        if not any(k in str(cons[-1]) for k in EXEMPT_KEYS):
            errs.append(f"{rid} 末项非出罪要件")
        if not (r.get("justifications") or []):
            errs.append(f"{rid} justifications 为空")
        if not any(isinstance(e, dict) and e.get("role") == "反证"
                   for e in (r.get("evidence_chain") or [])):
            errs.append(f"{rid} evidence_chain 无反证")
        for f in ("required_materials", "legal_basis", "remedy", "match_hints"):
            if not (r.get(f) or []):
                errs.append(f"{rid} 字段 {f} 为空")
        di = _DEFAULT_HIT_INDEX.get(rid)
        if not di:
            errs.append(f"{rid} 未登记 _DEFAULT_HIT_INDEX 兜底")
        elif any(any(k in str(cons[i - 1]) for k in EXEMPT_KEYS) for i in di):
            errs.append(f"{rid} 兜底序号指向出罪要件")

    # ② 闸门 0 ERROR（仅看新红线）
    for fn in (ac.check_constituent_exemption_coverage, ac.check_rebuttal_coverage,
               ac.check_redline_admission, ac.check_default_hit_index_valid,
               ac.check_legal_basis_freshness):
        for (s, f, m) in fn():
            if s == "ERROR" and any(rid in m for rid in NEW_IDS):
                errs.append(f"{fn.__name__}: {m}")

    # ③ 可达性
    for rid in NEW_IDS:
        r = by_id[rid]
        rl, info = match_redline_grounded(
            r["name"], " ".join(r["match_hints"][:2]),
            available_materials=r["required_materials"][:2])
        if not rl or rl["id"] != rid:
            errs.append(f"{rid} 不可达（match_redline_grounded 未命中）")

    # ④ 端到端：声明 redline_id 的合成发现
    for rid in NEW_IDS:
        r = by_id[rid]
        finding = {
            "type": r["name"], "level": "中风险",
            "detail": "本轮检测到该红线相关事实，待企业举证核实。",
            "redline_id": rid,
        }
        try:
            res = run_redline_detection([finding], engine_data={},
                                        material_readiness={"provided": r["required_materials"]})
        except Exception as exc:  # 端到端不应抛异常
            errs.append(f"{rid} run_redline_detection 抛异常: {exc}")
            continue
        sus = [s for s in res.get("suspicions", []) if s.get("redline_id") == rid]
        if not sus:
            errs.append(f"{rid} 未产出 suspicion（可能被标记 unmapped）")
            continue
        ch = sus[0].get("argumentation", {}).get("constituent_hits") or []
        if not ch:
            errs.append(f"{rid} suspicion 无 constituent_hits（兜底未补齐）")

    print(f"[A类] 红线总数={len(REDLINES)}，新红线={len(NEW_IDS)}")
    if errs:
        print("[ERROR] 验收未通过：")
        for e in errs:
            print("  -", e)
        return 1
    print("[OK] A 类 6 条新红线：结构齐全 / 闸门 0 ERROR / 可达 / 端到端产出并兜底补齐 constituent_hits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

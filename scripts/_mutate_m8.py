# -*- coding: utf-8 -*-
"""收尾三处：
  ⑦ 封印去重改用发现身份键唯一权威 findingkit.finding_identity（消掉第二份手写实现）
  ⑧ pipeline：报真实门禁轮数；删除临时 DBG_GATE 探针
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)


def swap(path, pairs):
    p = os.path.join(ROOT, path)
    raw = io.open(p, "r", encoding="utf-8", newline="").read()
    crlf = "\r\n" in raw
    s = raw.replace("\r\n", NL)
    for old, new in pairs:
        if s.count(old) != 1:
            print("!! %s: anchor命中 %d次(应为1): %r" % (path, s.count(old), old[:70]))
            sys.exit(2)
        s = s.replace(old, new, 1)
    if crlf:
        s = s.replace(NL, "\r\n")
    io.open(p, "w", encoding="utf-8", newline="").write(s)
    print("OK %s (%d处)" % (path, len(pairs)))


# ── ⑦ output_governance：封印身份取值收敛 ────────────────────────────
swap("engine/output_governance.py", [
    ("from engine.verified_rule_engine import VERIFIED_RULE_CATALOG, run_verified_rules",
     "from engine.verified_rule_engine import VERIFIED_RULE_CATALOG, run_verified_rules\n"
     "from engine.findingkit import finding_identity  # ★ 发现身份键唯一权威"),
    ('        identity = str(item.get("scene_fact_id") or item.get("fact_id") or item.get("type") or "").strip()',
     '        # ★ 身份取值唯一权威：原先此处手写一份「scene_fact_id/fact_id/type」取值，\n'
     '        #   与 self_learning 门禁跨轮记账各写各的，两边迟早漂移；改用唯一权威。\n'
     '        identity = finding_identity(item)'),
])

# ── ⑧ pipeline：真实轮数 + 删除临时探针 ──────────────────────────────
OLD = '''    gate_passed = True
    gate_rounds = 1
    try:
        from engine.self_learning import run_compliance_gate
        gate_result, all_findings = run_compliance_gate(
            all_findings, pipeline_log, file_results, ctx
        )
        gate_passed = gate_result.get("passed", False)
        result["compliance_gate"] = gate_result
        result["report"]["gate_rounds"] = gate_rounds
        if not gate_passed:
            blocking_count = len(gate_result.get("blocking_violations", []))
            pipeline_log.append(f"[GATE-INFO] 合规门禁{gate_rounds}轮: {blocking_count}项违规已标记，报告仍可输出——底部标注质量警告")
            result["report"]["blocked"] = True
            if os.environ.get("DBG_GATE"):
                _bl = gate_result.get("blocking_violations", []) or []
                import json as _json_dbg
                with open("scripts/_gate_blocking.json", "w", encoding="utf-8") as _fh:
                    _json_dbg.dump({"reason": gate_result.get("blocked_reason", ""),
                                    "n": len(_bl), "items": _bl}, _fh, ensure_ascii=False, indent=1)
            result["report"]["block_reason"] = gate_result.get("blocked_reason", "")
            result["report"]["blocking_violations_count"] = blocking_count
        else:
            pipeline_log.append(f"[GATE-PASS] 合规门禁第{gate_rounds}轮通过 ✓")
    except Exception as e:
        pipeline_log.append(f"[COMPLIANCE] 门禁执行异常: {e}")'''

NEW = '''    gate_passed = True
    gate_rounds = 1
    try:
        from engine.self_learning import run_compliance_gate
        gate_result, all_findings = run_compliance_gate(
            all_findings, pipeline_log, file_results, ctx
        )
        gate_passed = gate_result.get("passed", False)
        # ★ 门禁已接线上自愈+复检（run_compliance_gate 走 _gate_loop），轮数不再恒为 1：
        #   写死 1 会让报告里的"门禁轮数"与真实发生的不符，属于记录失真。
        gate_rounds = int(gate_result.get("rounds", 1) or 1)
        gate_passed = gate_result.get("passed", False)
        result["compliance_gate"] = gate_result
        result["report"]["gate_rounds"] = gate_rounds
        if not gate_passed:
            blocking_count = len(gate_result.get("blocking_violations", []))
            pipeline_log.append(f"[GATE-INFO] 合规门禁{gate_rounds}轮: {blocking_count}项违规已标记，报告仍可输出——底部标注质量警告")
            result["report"]["blocked"] = True
            result["report"]["block_reason"] = gate_result.get("blocked_reason", "")
            result["report"]["blocking_violations_count"] = blocking_count
        else:
            pipeline_log.append(f"[GATE-PASS] 合规门禁{gate_rounds}轮通过 ✓")
    except Exception as e:
        pipeline_log.append(f"[COMPLIANCE] 门禁执行异常: {e}")'''

swap("engine/pipeline.py", [(OLD, NEW)])

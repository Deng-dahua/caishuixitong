# -*- coding: utf-8 -*-
"""把「自动自愈」接回唯一被 pipeline 调用的门禁入口，并让两个入口共用同一循环。

改动点（全部在 engine/self_learning.py）：
  ③ _check_m06_law_reference：违规字典带上 finding_raw，供 `_violation_finding_index`
     按唯一权威重算身份（否则记账与判罚取不到同一把钥匙）。
  ④ 新增 `_gate_loop`：检测 → 可自愈就 auto_heal → 复检，直到放行或无解。**唯一实现**。
  ⑤ run_compliance_gate（pipeline 实际调用的那个）薄转发到 _gate_loop。
  ⑥ run_compliance_gate_blocking 同样薄转发，删除第二份循环。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
SP8 = " " * 8


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


def ind(n):
    return " " * n


OLD_GATE = '''def run_compliance_gate(all_findings, pipeline_log, file_results, ctx):
    """执行事前合规门禁检查"""
    gate = ComplianceGate(all_findings, pipeline_log, file_results, ctx)
    result = gate.check_all()
    if not result["passed"]:
        pipeline_log.append(f"[COMPLIANCE] 门禁未通过: {len(result['violations'])}项违规 — 报告含风险标记")
    if result["auto_fixed"]:
        pipeline_log.append(f"[COMPLIANCE] 自动修复: {', '.join(result['auto_fixed'])}")
    return result, gate.all_findings
'''

NEW_GATE = '''def _gate_loop(all_findings, pipeline_log, file_results, ctx, max_rounds=3):
    """门禁主循环：检测 → 对**可自动修复**的阻断项 auto_heal → 复检，直到放行或无解。

    ★★ 2026-10-04（疑点10-21 合并批次）：本循环是门禁的**唯一实现**。
       事故：`auto_heal` 原本只写在 `run_compliance_gate_blocking` 里，而
       pipeline 实际调用（也是**唯一被接线**）的 `run_compliance_gate` **只检测不修复**
       ⇒ 能被自动补齐的法条/因果链永远补不进报告，可修的阻断项恒为阻断，
       报告因此恒被打「合规门禁阻断：N项阻断性违规」（实测残留 2 项全是可自愈项）。
       修法：两条入口都薄转发到本循环，消除多头，自愈真正接线。

    ★ 与"检测+标记模式"不冲突：本循环只保证**可自愈的**阻断项被修掉；
       修不掉（fixable=False）的照样不通过、报告照样标记风险——只是不再冤枉可修项。
    """
    rounds = 0
    gate_result = None
    for round_num in range(1, max_rounds + 1):
        rounds = round_num
        gate = ComplianceGate(all_findings, pipeline_log, file_results, ctx)
        gate_result = gate.check_all()
        if gate_result["passed"]:
            pipeline_log.append(f"[COMPLIANCE] 门禁第{round_num}轮通过 ✓")
            if gate_result["auto_fixed"]:
                pipeline_log.append("[COMPLIANCE] 自动修复: " + ", ".join(gate_result["auto_fixed"][:10]))
            break
        blocking = gate_result.get("blocking_violations", [])
        pipeline_log.append(f"[COMPLIANCE] 门禁第{round_num}轮不通过: {len(blocking)}项阻断性违规，尝试自动修复...")
        if gate_result.get("can_auto_fix"):
            gate.auto_heal(gate.all_findings)
            all_findings = gate.all_findings
            pipeline_log.append(f"[COMPLIANCE] 自动修复完成，进入第{round_num + 1}轮检查")
            continue
        pipeline_log.append(f"[COMPLIANCE] 门禁阻断: {len(blocking)}项不可自动修复 — 报告禁止输出")
        break
    if gate_result is not None:
        gate_result["rounds"] = rounds
    return gate_result, all_findings, rounds


def run_compliance_gate(all_findings, pipeline_log, file_results, ctx):
    """执行事前合规门禁检查（检测 + **已接线自愈** + 复检）

    pipeline 唯一调用的门禁入口；走 `_gate_loop` 同一条链路，只是把轮数收窄到 2 轮
    （一轮检测 + 一轮自愈复检），避免"检测+标记"语义下白跑太多轮。
    """
    result, all_findings, _rounds = _gate_loop(
        all_findings, pipeline_log, file_results, ctx, max_rounds=2
    )
    if not result["passed"]:
        pipeline_log.append(f"[COMPLIANCE] 门禁仍未通过: {len(result['violations'])}项违规 — 报告含风险标记")
    if result["auto_fixed"]:
        pipeline_log.append(f"[COMPLIANCE] 自动修复: {', '.join(result['auto_fixed'])}")
    return result, all_findings
'''

OLD_BLOCKING_HEAD = '''def run_compliance_gate_blocking(all_findings, pipeline_log, file_results, ctx, max_rounds=3):
    """
    合规门禁阻断版：不通过时自动修复+重试。
    
    返回 (gate_result, all_findings, rounds_used)
    - gate_result["passed"] = True → 报告可以输出
    - gate_result["passed"] = False → 报告禁止输出，需人工复核
    """
    for round_num in range(1, max_rounds + 1):'''

NEW_BLOCKING_HEAD = '''def run_compliance_gate_blocking(all_findings, pipeline_log, file_results, ctx, max_rounds=3):
    """合规门禁阻断版：不通过时自动修复+重试 —— 薄转发到 `_gate_loop`（唯一实现）。

    返回 (gate_result, all_findings, rounds_used)
    - gate_result["passed"] = True → 报告可以输出
    - gate_result["passed"] = False → 报告禁止输出，需人工复核
    """
    return _gate_loop(all_findings, pipeline_log, file_results, ctx, max_rounds=max_rounds)


def _run_compliance_gate_blocking_legacy(all_findings, pipeline_log, file_results, ctx, max_rounds=3):
    """已废弃的旧循环实现，仅留作对照，勿调用。"""
    for round_num in range(1, max_rounds + 1):'''

# 违规字典补 finding_raw（锚点取唯一子串，避免数错缩进）
OLD_VIOL_A = ind(24) + '"rule": "M06-N-依据待核",'
NEW_VIOL_A = OLD_VIOL_A + NL + ind(24) + '"finding_raw": f,'
OLD_VIOL_B = ind(24) + '"rule": "M06-法条引用",'
NEW_VIOL_B = OLD_VIOL_B + NL + ind(24) + '"finding_raw": f,'

swap("engine/self_learning.py", [
    (OLD_VIOL_A, NEW_VIOL_A),
    (OLD_VIOL_B, NEW_VIOL_B),
    (OLD_GATE, NEW_GATE),
    (OLD_BLOCKING_HEAD, NEW_BLOCKING_HEAD),
])

# -*- coding: utf-8 -*-
"""风险检查方法论场景验收与结论边界校准。"""

from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache


ACCEPTANCE_VERSION = "1.0.0"

EVIDENCE_STATE_OUTCOMES = {
    "supported": "事实充分支持_待审理",
    "rebutted": "解释成立_关闭",
    "partial": "事实部分支持_限定范围",
    "contradictory": "存在具体矛盾_待补证",
    "insufficient": "资料不足_未启动",
}

_FORBIDDEN_TEXT = (
    "legacy_absorption",
    "已吸收",
    "候选检索",
    "迁移账册",
)


def evaluate_acceptance_case(case: dict) -> dict:
    """核对显式证据状态与预期边界；不根据自然语言自动定性。"""
    state = str(case.get("evidence_state", ""))
    actual = EVIDENCE_STATE_OUTCOMES.get(state, "")
    failures = []
    if not actual:
        failures.append("未知证据状态")
    if actual != str(case.get("expected", "")):
        failures.append("预期状态与证据状态不一致")
    if not str(case.get("facts", "")).strip():
        failures.append("缺少事实样本")
    if len(case.get("required_assertions") or []) < 4:
        failures.append("验收断言不足")
    return {
        "passed": not failures,
        "evidence_state": state,
        "expected": case.get("expected", ""),
        "actual": actual,
        "required_human_review": True,
        "automatic_determination_allowed": False,
        "failures": failures,
    }


def audit_scene_contract(scene: dict) -> dict:
    """逐场景审计疑点、调查、证据、分析、政策、协同和报告交接。"""
    failures = []
    scene_id = str(scene.get("id", ""))
    applicability = scene.get("applicability") or {}
    doubt = scene.get("doubt") or {}
    clue = scene.get("clue_chain") or {}
    evidence = scene.get("evidence_chain") or {}
    analysis = scene.get("analysis_chain") or {}
    domains = scene.get("domain_collaboration") or {}
    report = scene.get("report_contract") or {}
    policy = scene.get("policy_applicability") or {}
    cases = scene.get("acceptance_cases") or []

    checks = (
        (bool(scene_id and scene.get("name")), "场景身份不完整"),
        (bool(applicability.get("apply_when") and applicability.get("do_not_apply_when")), "适用或停止条件不完整"),
        (bool(applicability.get("required_source_families") and scene.get("source_gates")), "资料门槛不完整"),
        (bool(doubt.get("target_fact") and doubt.get("observed_signal")), "待证事实或观察信号不完整"),
        (len(clue.get("steps") or []) >= 4 and bool(clue.get("terminal")), "调查路径或停止终点不完整"),
        (bool(evidence.get("supporting_sources")), "缺少支持证据来源"),
        (bool(evidence.get("opposing_sources")), "缺少反向证据来源"),
        (bool(evidence.get("quality_checks") and evidence.get("insufficient_when")), "证据质量或不足条件不完整"),
        (bool(analysis.get("reasoning") and analysis.get("tax_boundary")), "分析论证或税法边界不完整"),
        (len(analysis.get("conclusion_ladder") or []) >= 5, "结论阶梯不完整"),
        (bool(domains.get("lead") and domains.get("partners") and domains.get("conflict_rule")), "业务域协同不完整"),
        (bool(report.get("must_state") and report.get("forbidden") and report.get("release_gate")), "报告交接门槛不完整"),
        (policy.get("status") == "case_time_verification_required", "政策时效门槛不完整"),
        (bool(policy.get("required_dimensions") and policy.get("required_source_fields") and policy.get("stop_if")), "政策适用维度不完整"),
    )
    failures.extend(message for passed, message in checks if not passed)

    seen_states = set()
    for case in cases:
        result = evaluate_acceptance_case(case)
        seen_states.add(result["evidence_state"])
        failures.extend(f"{case.get('case', '样本')}：{item}" for item in result["failures"])
    missing_states = set(EVIDENCE_STATE_OUTCOMES) - seen_states
    if missing_states:
        failures.append("缺少证据状态验收：" + "、".join(sorted(missing_states)))

    encoded = json.dumps(scene, ensure_ascii=False)
    for marker in _FORBIDDEN_TEXT:
        if marker in encoded:
            failures.append(f"存在停用历史表述：{marker}")

    return {
        "scene_id": scene_id,
        "passed": not failures,
        "acceptance_case_count": len(cases),
        "evidence_states": sorted(seen_states),
        "failures": failures,
    }


@lru_cache(maxsize=1)
def run_portfolio_acceptance() -> dict:
    """执行全组合验收，供发布检查、接口和页面共同消费。"""
    from engine.methodology_portfolio import load_methodology_portfolio

    portfolio = load_methodology_portfolio()
    scene_results = []
    contract_results = []
    scene_ids = set()
    target_facts = set()
    clue_signatures = set()
    duplicate_ids = []
    duplicate_targets = []
    duplicate_paths = []

    for contract in portfolio.get("contracts", []):
        contract_scenes = []
        for scene in contract.get("scenarios", []):
            result = audit_scene_contract(scene)
            scene_results.append(result)
            contract_scenes.append(result)

            scene_id = str(scene.get("id", ""))
            target = str((scene.get("doubt") or {}).get("target_fact", "")).strip()
            signature = tuple(
                str(step.get("action", "")).strip()
                for step in (scene.get("clue_chain") or {}).get("steps", [])
            )
            if scene_id in scene_ids:
                duplicate_ids.append(scene_id)
            scene_ids.add(scene_id)
            if target in target_facts:
                duplicate_targets.append(scene_id)
            target_facts.add(target)
            if signature in clue_signatures:
                duplicate_paths.append(scene_id)
            clue_signatures.add(signature)

        contract_results.append({
            "code": contract.get("code"),
            "name": contract.get("name"),
            "scene_count": len(contract_scenes),
            "passed_scene_count": sum(item["passed"] for item in contract_scenes),
            "failed_scene_count": sum(not item["passed"] for item in contract_scenes),
        })

    structural_failures = (
        [f"重复场景编号：{item}" for item in duplicate_ids]
        + [f"重复待证事实：{item}" for item in duplicate_targets]
        + [f"重复调查路径：{item}" for item in duplicate_paths]
    )
    failed_scenes = [item for item in scene_results if not item["passed"]]
    state_distribution = Counter(
        state
        for item in scene_results
        for state in item.get("evidence_states", [])
    )
    return {
        "version": ACCEPTANCE_VERSION,
        "portfolio_version": portfolio.get("version"),
        "status": "passed" if not failed_scenes and not structural_failures else "failed",
        "contract_count": len(contract_results),
        "scene_count": len(scene_results),
        "passed_scene_count": sum(item["passed"] for item in scene_results),
        "failed_scene_count": len(failed_scenes),
        "acceptance_case_count": sum(item["acceptance_case_count"] for item in scene_results),
        "evidence_state_distribution": dict(sorted(state_distribution.items())),
        "duplicate_scene_ids": duplicate_ids,
        "duplicate_target_facts": duplicate_targets,
        "duplicate_clue_paths": duplicate_paths,
        "structural_failures": structural_failures,
        "contracts": contract_results,
        "failed_scenes": failed_scenes,
        "decision_boundary": "验收只校准证据状态和输出边界；所有个案结论仍须由有权人员复核。",
    }


def clear_acceptance_cache() -> None:
    run_portfolio_acceptance.cache_clear()


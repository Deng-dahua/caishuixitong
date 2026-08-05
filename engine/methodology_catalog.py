# -*- coding: utf-8 -*-
"""Canonical tax-inspection methodology catalog and reviewed industry contracts.

A signal may start verification, but it may never become a legal conclusion
without the evidence, opposing-evidence and procedure gates.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
CATALOG_FILE = STATIC / "methodology_canonical_catalog.json"
REVIEW_FILE = STATIC / "industry_scenario_review.json"

V2_SCENARIO_FILES = {
    "A": "agriculture_scenario_contracts.json",
    "B": "mining_scenario_contracts.json",
    "C": "manufacturing_scenario_contracts.json",
    "E": "construction_scenario_contracts.json",
    "F": "wholesale_retail_scenario_contracts.json",
    "K": "real_estate_scenario_contracts.json",
    "OVERLAY-PLATFORM": "platform_scenario_contracts.json",
}
ASSET_TO_CODE = {filename.removesuffix(".json"): code for code, filename in V2_SCENARIO_FILES.items()}
SCENARIO_FILES = {
    code: "methodology_portfolio"
    for code in tuple("ABCDEFGHIJKLMNOPQRST")
    + ("OVERLAY-PLATFORM", "OVERLAY-CROSS-BORDER", "OVERLAY-GROUP")
}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


@lru_cache(maxsize=1)
def load_canonical_catalog() -> dict:
    return _read(CATALOG_FILE)


@lru_cache(maxsize=1)
def load_industry_review() -> dict:
    return _read(REVIEW_FILE)


def _source_names(module: dict, catalog: dict) -> str:
    source_map = {item["id"]: item["name"] for item in catalog.get("official_sources", [])}
    return "；".join(source_map.get(ref, ref) for ref in module.get("source_refs", []))


def _module_importance(module_name):
    """根据模块名称推断其风险分析重要性，返回基础分数(0-10)"""
    name_lower = (module_name or "").lower()
    # 资金流和发票是核心领域
    if any(kw in name_lower for kw in ("资金", "收款", "银行", "现金流")):
        return 9
    if any(kw in name_lower for kw in ("发票", "进销", "开票", "虚开")):
        return 9
    if any(kw in name_lower for kw in ("收入", "隐匿", "隐瞒")):
        return 8
    if any(kw in name_lower for kw in ("存货", "库存", "仓储")):
        return 7
    if any(kw in name_lower for kw in ("工资", "社保", "用工", "个税")):
        return 7
    if any(kw in name_lower for kw in ("凭证", "账务", "会计", "科目")):
        return 6
    if any(kw in name_lower for kw in ("合同", "关联", "交易")):
        return 6
    if any(kw in name_lower for kw in ("费用", "成本", "资产")):
        return 5
    if any(kw in name_lower for kw in ("申报", "纳税", "税负")):
        return 5
    return 3  # 默认基础重要性


def _score_to_level(score):
    if score >= 9: return "极高风险"
    if score >= 7: return "高风险"
    if score >= 5: return "中风险"
    if score >= 3: return "低风险"
    return "信息"


@lru_cache(maxsize=1)
def load_flat_rules() -> list[dict]:
    """Return authoritative fact-verification rules in the legacy list shape."""
    catalog = load_canonical_catalog()
    output: list[dict] = []
    for module in catalog.get("modules", []):
        base_score = _module_importance(module.get("name", ""))
        for rule in module.get("rules", []):
            rule_score = base_score
            rule_hypothesis = (rule.get("fact_hypothesis", "") or "").lower()
            if any(kw in rule_hypothesis for kw in ("虚开", "偷税", "隐匿", "骗取")):
                rule_score = min(10, base_score + 2)
            output.append({
                "id": rule["id"],
                "item": rule["fact_hypothesis"],
                "name": rule["fact_hypothesis"],
                "category": module["name"],
                "score": rule_score,
                "level": _score_to_level(rule_score),
                "type": "authoritative_review_contract",
                "maturity": "authoritative_human_review_contract",
                "applicable_condition": "；".join(module.get("activation_gate", [])),
                "required_fields": list(rule.get("required_fields", [])),
                "reasonable_explanations": list(rule.get("excludes", [])),
                "direction": " → ".join(
                    stage
                    for path in module.get("clue_paths", [])
                    for stage in path.get("stages", [])
                ),
                "evidence_requirements": copy.deepcopy(module.get("evidence_plan", {})),
                "analysis_tests": list(module.get("analysis_tests", [])),
                "validation_cases": list(module.get("validation_cases", [])),
                "suggestion": module.get("report_boundary", "完成事实、证据和程序复核后提交人工审理。"),
                "policy_ref": _source_names(module, catalog),
                "source": "税务稽查权威方法论目录",
                "human_review_required": rule_score < 7,
                "automatic_determination_allowed": rule_score >= 7,
                "threshold": None,
            })
    for code in SCENARIO_FILES:
        payload = load_reviewed_scenario_contracts(code)
        for scene in payload.get("scenarios", []):
            doubt = scene.get("doubt") or {}
            evidence = scene.get("evidence_chain") or {}
            analysis = scene.get("analysis_chain") or {}
            scene_score = _module_importance(doubt.get("target_fact", scene.get("name", "")))
            output.append({
                "id": f"{scene['id']}-R",
                "item": doubt.get("target_fact", scene.get("name", "")),
                "name": scene.get("name", ""),
                "category": payload.get("name", code),
                "score": scene_score,
                "level": _score_to_level(scene_score),
                "type": "industry_fact_review_contract",
                "maturity": scene.get("maturity", "M2.5_boundary_tested"),
                "applicable_condition": "；".join(
                    (scene.get("applicability") or {}).get("apply_when", [])
                ),
                "required_fields": list(evidence.get("fact_elements", [])),
                "reasonable_explanations": list(
                    analysis.get("alternatives")
                    or doubt.get("must_exclude")
                    or doubt.get("reasonable_explanations")
                    or []
                ),
                "direction": " → ".join(
                    str(step.get("action", ""))
                    for step in (scene.get("clue_chain") or {}).get("steps", [])
                    if isinstance(step, dict)
                ),
                "evidence_requirements": copy.deepcopy(evidence),
                "analysis_tests": list(analysis.get("reasoning", [])),
                "validation_cases": copy.deepcopy(scene.get("validation_cases", [])),
                "suggestion": (scene.get("clue_chain") or {}).get("terminal", "完成事实、证据和程序复核后提交人工审理。"),
                "policy_ref": "按业务期间的现行有效依据逐项核验",
                "source": "全行业税务稽查方法论场景组合",
                "industry_code": code,
                "scene_id": scene.get("id"),
                "human_review_required": scene_score < 7,
                "automatic_determination_allowed": scene_score >= 7,
                "threshold": None,
            })
    return output


@lru_cache(maxsize=1)
def load_flat_clues() -> list[dict]:
    catalog = load_canonical_catalog()
    output: list[dict] = []
    for module in catalog.get("modules", []):
        for path in module.get("clue_paths", []):
            output.append({
                "id": path["id"],
                "name": f"{module['name']}调查路径",
                "chain_type": "线索链",
                "sub_topic": module["name"],
                "investigation_path": [
                    {"step": index, "domain": module["name"], "action": stage}
                    for index, stage in enumerate(path.get("stages", []), 1)
                ],
                "trigger_boundary": list(module.get("activation_gate", [])),
                "terminal": module.get("report_boundary", ""),
                "executable": False,
                "human_review_required": True,
            })
    for code in SCENARIO_FILES:
        payload = load_reviewed_scenario_contracts(code)
        for scene in payload.get("scenarios", []):
            clue = scene.get("clue_chain") or {}
            output.append({
                "id": f"{scene['id']}-C",
                "name": f"{scene.get('name', '')}调查路径",
                "chain_type": "调查线索链",
                "sub_topic": payload.get("name", code),
                "investigation_path": copy.deepcopy(clue.get("steps", [])),
                "trigger_boundary": list((scene.get("applicability") or {}).get("apply_when", [])),
                "terminal": clue.get("terminal", ""),
                "industry_code": code,
                "scene_id": scene.get("id"),
                "executable": False,
                "human_review_required": True,
            })
    return output


@lru_cache(maxsize=1)
def load_flat_evidence() -> list[dict]:
    output: list[dict] = []
    for module in load_canonical_catalog().get("modules", []):
        plan = module.get("evidence_plan", {})
        output.append({
            "id": f"{module['id']}-E01",
            "name": f"{module['name']}证据要求",
            "chain_type": "证据链",
            "sub_topic": module["name"],
            "fact_elements": sorted({field for rule in module.get("rules", []) for field in rule.get("required_fields", [])}),
            "supporting_sources": list(plan.get("supporting", [])),
            "opposing_sources": list(plan.get("opposing", [])),
            "insufficient_when": list(plan.get("insufficient_when", [])),
            "quality_dimensions": list(load_canonical_catalog().get("common_contract", {}).get("evidence_dimensions", [])),
            "executable": False,
            "human_review_required": True,
        })
    for code in SCENARIO_FILES:
        payload = load_reviewed_scenario_contracts(code)
        for scene in payload.get("scenarios", []):
            plan = scene.get("evidence_chain") or {}
            output.append({
                "id": f"{scene['id']}-E",
                "name": f"{scene.get('name', '')}证据组织方案",
                "chain_type": "证据链",
                "sub_topic": payload.get("name", code),
                "fact_elements": list(plan.get("fact_elements", [])),
                "supporting_sources": list(plan.get("supporting_sources", [])),
                "opposing_sources": list(plan.get("opposing_sources", [])),
                "insufficient_when": list(plan.get("insufficient_when", [])),
                "quality_dimensions": list(load_canonical_catalog().get("common_contract", {}).get("evidence_dimensions", [])),
                "industry_code": code,
                "scene_id": scene.get("id"),
                "executable": False,
                "human_review_required": True,
            })
    return output


@lru_cache(maxsize=1)
def load_flat_analysis() -> list[dict]:
    output: list[dict] = []
    for module in load_canonical_catalog().get("modules", []):
        output.append({
            "id": f"{module['id']}-A01",
            "name": f"{module['name']}分析检验",
            "chain_type": "分析链",
            "sub_topic": module["name"],
            "analysis_tests": list(module.get("analysis_tests", [])),
            "validation_cases": list(module.get("validation_cases", [])),
            "reasoning_path": [
                {"step": index, "action": test}
                for index, test in enumerate(module.get("analysis_tests", []), 1)
            ],
            "suggestion": module.get("report_boundary", ""),
            "executable": False,
            "human_review_required": True,
        })
    for code in SCENARIO_FILES:
        payload = load_reviewed_scenario_contracts(code)
        for scene in payload.get("scenarios", []):
            plan = scene.get("analysis_chain") or {}
            tests = list(plan.get("reasoning", []))
            output.append({
                "id": f"{scene['id']}-A",
                "name": f"{scene.get('name', '')}分析论证方案",
                "chain_type": "分析链",
                "sub_topic": payload.get("name", code),
                "analysis_tests": tests,
                "validation_cases": copy.deepcopy(scene.get("validation_cases", [])),
                "reasoning_path": [
                    {"step": index, "action": test}
                    for index, test in enumerate(tests, 1)
                ],
                "suggestion": plan.get("tax_boundary", ""),
                "industry_code": code,
                "scene_id": scene.get("id"),
                "executable": False,
                "human_review_required": True,
            })
    return output


def _extend_unique(target: list, additions: list) -> None:
    for value in additions or []:
        if value not in target:
            target.append(value)


def _apply_addendum(scene: dict, addendum: dict) -> dict:
    scene = copy.deepcopy(scene)
    scene["methodology_revision"] = {
        "version": "2.0.0",
        "decision": addendum.get("decision", "retain"),
        "depth_rationale": addendum.get("depth_rationale", ""),
        "count_rule": "链深和案例数由本场景的事实、证据和边界决定。",
    }
    clue = scene.setdefault("clue_chain", {})
    steps = clue.setdefault("steps", [])
    for action in addendum.get("clue_additions", []):
        steps.append({
            "step": len(steps) + 1,
            "action": action,
            "join_keys": [],
            "deliverable": "专项深度复审记录",
            "branch_if_missing": "事实部分支持_待补证",
        })
    evidence = scene.setdefault("evidence_chain", {})
    _extend_unique(evidence.setdefault("opposing_sources", []), addendum.get("opposing_evidence_additions", []))
    analysis = scene.setdefault("analysis_chain", {})
    _extend_unique(analysis.setdefault("reasoning", []), addendum.get("analysis_additions", []))
    _extend_unique(scene.setdefault("validation_cases", []), addendum.get("validation_additions", []))
    return scene


def _build_additional_scene(spec: dict) -> dict:
    scene_id = spec["id"]
    clues = list(spec.get("clue_stages", []))
    cases = list(spec.get("cases", []))
    return {
        "id": scene_id,
        "name": spec["name"],
        "maturity": "M2.5_boundary_tested",
        "methodology_revision": {
            "version": "2.0.0",
            "decision": "new_independent_scene",
            "depth_rationale": spec.get("reason", ""),
            "count_rule": "新增场景用于承接无法由既有场景可靠容纳的独立事实。",
        },
        "applicability": {
            "apply_when": [spec.get("reason", "")],
            "do_not_apply_when": ["缺少能够唯一定位本场景业务的主体、期间或交易资料"],
            "required_source_families": list(spec.get("supporting", [])),
        },
        "doubt": {
            "target_fact": f"{spec['name']}涉及的主体、交易、数量金额和申报是否形成可验证闭环",
            "activation": [spec.get("reason", "")],
            "reasonable_explanations": list(spec.get("opposing", [])),
        },
        "clue_chain": {
            "start": clues[0] if clues else "确认适用主体、业务和期间",
            "steps": [
                {
                    "step": index,
                    "action": action,
                    "join_keys": [],
                    "deliverable": f"{scene_id}阶段{index}核验底稿",
                    "branch_if_missing": "待补资料_可初筛",
                }
                for index, action in enumerate(clues, 1)
            ],
            "terminal": "只有支持与反向材料均已评价、剩余差异定位到具体主体事项和期间后，才提交人工审理。",
        },
        "evidence_chain": {
            "fact_elements": ["主体", "业务事项", "期间", "数量金额", "税会申报"],
            "supporting_sources": list(spec.get("supporting", [])),
            "opposing_sources": list(spec.get("opposing", [])),
            "insufficient_when": ["关键主体或期间不明", "只有汇总数据没有原始业务记录", "未取得反向材料"],
        },
        "analysis_chain": {
            "proposition": f"{spec['name']}的剩余差异是否由合法、真实、关联且充分的证据支持",
            "alternatives": list(spec.get("opposing", [])),
            "reasoning": list(spec.get("analysis", [])),
            "conclusion_ladder": ["解释成立_关闭", "资料不足_未启动", "事实部分支持_待补证", "事实充分支持_待审理"],
            "tax_boundary": "先确定事实，再按业务期间的现行有效依据分别判断税费影响；本场景不自动形成违法定性、税额、处罚或移送意见。",
        },
        "domain_collaboration": {
            "lead": "行业业务事实域",
            "partners": [
                {"domain": "主体合同域", "responsibility": "确认主体和权利义务", "handoff": "主体合同清单"},
                {"domain": "实物或服务履约域", "responsibility": "确认真实履约", "handoff": "履约时间线"},
                {"domain": "资金发票域", "responsibility": "确认价款、开票和结算", "handoff": "票款桥接表"},
                {"domain": "财税程序域", "responsibility": "确认申报、依据和程序", "handoff": "税会及程序复核"},
            ],
            "conflict_rule": "域间矛盾不得按多数表决；回到原始来源、权利义务和实际履约逐项解释。",
        },
        "report_contract": {
            "title": f"{spec['name']}核验结果",
            "must_state": ["适用主体期间", "待证事实", "支持与反向证据", "资料缺口", "人工复核状态"],
            "forbidden": ["自动认定违法", "以模型评分代替证据", "自动核定税额处罚或移送"],
        },
        "validation_cases": [
            {
                "case": f"review_case_{index}",
                "facts": case,
                "expected": "按该边界样本核验；证据不足时不得升级结论",
            }
            for index, case in enumerate(cases, 1)
        ],
    }


@lru_cache(maxsize=len(V2_SCENARIO_FILES))
def _load_v2_reviewed_contracts(industry_code: str) -> dict:
    code = str(industry_code or "").upper()
    filename = V2_SCENARIO_FILES[code]
    payload = copy.deepcopy(_read(STATIC / filename))
    review = load_industry_review()
    addenda = {item["scene_id"]: item for item in review.get("review_addenda", [])}
    payload["version"] = "2.0.0"
    payload["effective_date"] = review.get("effective_date")
    payload["positioning"] = (
        str(payload.get("positioning", "")).rstrip("。")
        + "。本版已经逐场景复审调查深度、反向证据和边界样本；不采用固定场景数、固定步骤数或固定案例数。"
    )
    payload["scenarios"] = [
        _apply_addendum(scene, addenda.get(scene.get("id"), {}))
        for scene in payload.get("scenarios", [])
    ]
    payload["scenarios"].extend(
        _build_additional_scene(spec)
        for spec in review.get("additional_scenario_specs", [])
        if spec.get("industry_code") == code
    )
    payload["review_summary"] = {
        "policy": review.get("review_policy", {}),
        "scenario_count": len(payload["scenarios"]),
        "clue_depths": [len(scene.get("clue_chain", {}).get("steps", [])) for scene in payload["scenarios"]],
        "validation_depths": [len(scene.get("validation_cases", [])) for scene in payload["scenarios"]],
    }
    return payload


@lru_cache(maxsize=len(SCENARIO_FILES))
def load_reviewed_scenario_contracts(industry_code: str) -> dict:
    """Return the current v3 full-industry scenario contract."""
    from engine.methodology_portfolio import load_industry_contract

    return load_industry_contract(str(industry_code or "").upper())


def load_reviewed_scenario_asset(asset_name: str) -> dict:
    code = ASSET_TO_CODE[asset_name]
    return load_reviewed_scenario_contracts(code)


def methodology_inventory() -> dict:
    catalog = load_canonical_catalog()
    scenario_payloads = [load_reviewed_scenario_contracts(code) for code in SCENARIO_FILES]
    scenarios = [scene for payload in scenario_payloads for scene in payload.get("scenarios", [])]
    canonical_rule_count = sum(len(module.get("rules", [])) for module in catalog.get("modules", []))
    canonical_clue_count = sum(len(module.get("clue_paths", [])) for module in catalog.get("modules", []))
    canonical_evidence_count = len(catalog.get("modules", []))
    canonical_analysis_count = len(catalog.get("modules", []))
    return {
        "canonical_modules": len(catalog.get("modules", [])),
        "canonical_rules": canonical_rule_count,
        "canonical_clue_paths": canonical_clue_count,
        "canonical_evidence_plans": canonical_evidence_count,
        "canonical_analysis_plans": canonical_analysis_count,
        "industry_fact_contracts": len(scenarios),
        "rules": len(load_flat_rules()),
        "clue_paths": len(load_flat_clues()),
        "evidence_plans": len(load_flat_evidence()),
        "analysis_plans": len(load_flat_analysis()),
        "industry_scenarios": len(scenarios),
        "industry_scenario_counts": {
            code: len(payload.get("scenarios", []))
            for code, payload in zip(SCENARIO_FILES, scenario_payloads)
        },
        "clue_depths": sorted({len(scene.get("clue_chain", {}).get("steps", [])) for scene in scenarios}),
        "validation_depths": sorted({len(scene.get("validation_cases", [])) for scene in scenarios}),
        "domain_collaboration_depths": sorted({len((scene.get("domain_collaboration") or {}).get("partners", [])) for scene in scenarios}),
    }

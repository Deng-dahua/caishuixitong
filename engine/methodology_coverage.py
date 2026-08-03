# -*- coding: utf-8 -*-
"""现行稽查方法论的真实覆盖与质量报告。"""

from __future__ import annotations

from collections import Counter

from engine.methodology_acceptance import run_portfolio_acceptance
from engine.methodology_catalog import load_canonical_catalog, methodology_inventory
from engine.methodology_portfolio import load_methodology_portfolio


def _scene_quality(scene):
    evidence = scene.get("evidence_chain") or {}
    analysis = scene.get("analysis_chain") or {}
    return {
        "scene_id": scene.get("id"),
        "name": scene.get("name"),
        "clue_steps": len((scene.get("clue_chain") or {}).get("steps", [])),
        "supporting_evidence_types": len(evidence.get("supporting_sources", [])),
        "opposing_evidence_types": len(evidence.get("opposing_sources", [])),
        "analysis_tests": len(analysis.get("reasoning", [])),
        "validation_cases": len(scene.get("validation_cases", [])),
        "acceptance_cases": len(scene.get("acceptance_cases", [])),
        "domain_partners": len((scene.get("domain_collaboration") or {}).get("partners", [])),
        "maturity": scene.get("maturity"),
    }


def build_methodology_coverage(static_root=None):
    catalog = load_canonical_catalog()
    portfolio = load_methodology_portfolio()
    inventory = methodology_inventory()
    acceptance = run_portfolio_acceptance()
    industries = []
    all_scenes = []
    for contract in portfolio.get("contracts", []):
        scenes = [_scene_quality(scene) for scene in contract.get("scenarios", [])]
        all_scenes.extend(scenes)
        industries.append({
            "code": contract.get("code"),
            "name": contract.get("name"),
            "scenario_count": len(scenes),
            "clue_depths": sorted({item["clue_steps"] for item in scenes}),
            "validation_depths": sorted({item["validation_cases"] for item in scenes}),
            "domain_depths": sorted({item["domain_partners"] for item in scenes}),
            "state": "已形成完整场景合同；正式结论仍须经过适用性、证据、法律和程序人工复核",
            "scenes": scenes,
        })

    modules = [{
        "id": module.get("id"),
        "name": module.get("name"),
        "purpose": module.get("purpose"),
        "rule_count": len(module.get("rules", [])),
        "clue_path_count": len(module.get("clue_paths", [])),
        "analysis_test_count": len(module.get("analysis_tests", [])),
        "validation_case_count": len(module.get("validation_cases", [])),
        "source_refs": list(module.get("source_refs", [])),
        "report_boundary": module.get("report_boundary"),
    } for module in catalog.get("modules", [])]

    return {
        "version": "3.1.0",
        "positioning": portfolio.get("positioning"),
        "governance": {
            "count_policy": portfolio.get("count_policy"),
            "coverage_basis": portfolio.get("coverage_basis"),
            "common_boundaries": portfolio.get("common_boundaries", []),
        },
        "inventory": inventory,
        "acceptance": acceptance,
        "canonical_modules": modules,
        "industry_matrix": industries,
        "depth_distribution": {
            "clue_steps": dict(sorted(Counter(item["clue_steps"] for item in all_scenes).items())),
            "validation_cases": dict(sorted(Counter(item["validation_cases"] for item in all_scenes).items())),
            "analysis_tests": dict(sorted(Counter(item["analysis_tests"] for item in all_scenes).items())),
            "domain_partners": dict(sorted(Counter(item["domain_partners"] for item in all_scenes).items())),
        },
        "quality_controls": [
            "跨行业共同规则与行业事实合同分层，行业名称本身不触发结论",
            "场景、步骤、反证和样本数量由待证事实与取证难度决定",
            "每个场景同时规定适用、停止、支持证据、反向证据和证据不足条件",
            "调查路径必须能够回到原始资料、源行、经办过程和法定取得程序",
            "事实、会计处理、金额测算、法律评价、审理决定和报告表达分层",
            "一键分析只能生成待核事项、资料缺口、核验底稿和报告移交包",
            "每个场景必须通过充分支持、正常解释、限定范围、证据矛盾和资料不足五类证据状态验收",
            "政策依据必须按事实期间、地区、纳税人身份和程序阶段核验，异常或失效引用不得进入报告",
        ],
        "known_gaps": [
            {"priority": "持续门禁", "gap": "脱敏真实案件验证", "control": "按行业和场景记录确认、撤回、资料不足、反例及程序结果；未经样本验证不得升级为自动结论能力。"},
            {"priority": "逐案门禁", "gap": "地方政策及历史期间", "control": "涉及地方授权、过渡政策或历史期间时，取得业务期间有效全文并完成人工复核。"},
            {"priority": "数据门禁", "gap": "外部和第三方资料权限", "control": "只有权限、来源、对象、期间、取得方式和保全过程明确的数据才进入证据评价。"},
        ],
    }

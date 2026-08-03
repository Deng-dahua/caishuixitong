# -*- coding: utf-8 -*-
"""Coverage report for the authoritative methodology catalog."""

from __future__ import annotations

from collections import Counter

from engine.methodology_catalog import (
    SCENARIO_FILES,
    load_canonical_catalog,
    load_reviewed_scenario_contracts,
    methodology_inventory,
)


INDUSTRY_NAMES = {
    "A": "农、林、牧、渔业",
    "B": "采矿业",
    "C": "制造业",
    "E": "建筑业",
    "F": "批发和零售业",
    "K": "房地产业",
    "OVERLAY-PLATFORM": "平台经济业务叠加层",
}


def _scene_quality(scene):
    clue_steps = len((scene.get("clue_chain") or {}).get("steps", []))
    evidence = scene.get("evidence_chain") or {}
    analysis = scene.get("analysis_chain") or {}
    cases = scene.get("validation_cases") or []
    return {
        "scene_id": scene.get("id"),
        "name": scene.get("name"),
        "decision": (scene.get("methodology_revision") or {}).get("decision"),
        "depth_rationale": (scene.get("methodology_revision") or {}).get("depth_rationale"),
        "clue_steps": clue_steps,
        "supporting_evidence_types": len(evidence.get("supporting_sources", [])),
        "opposing_evidence_types": len(evidence.get("opposing_sources", [])),
        "analysis_tests": len(analysis.get("reasoning", [])),
        "validation_cases": len(cases),
    }


def build_methodology_coverage(static_root=None):
    catalog = load_canonical_catalog()
    inventory = methodology_inventory()
    industries = []
    all_scenes = []
    for code in SCENARIO_FILES:
        payload = load_reviewed_scenario_contracts(code)
        scenes = [_scene_quality(scene) for scene in payload.get("scenarios", [])]
        all_scenes.extend(scenes)
        industries.append({
            "code": code,
            "name": INDUSTRY_NAMES.get(code, payload.get("name", code)),
            "scenario_count": len(scenes),
            "new_scenario_count": sum(item["decision"] == "new_independent_scene" for item in scenes),
            "clue_depths": sorted({item["clue_steps"] for item in scenes}),
            "validation_depths": sorted({item["validation_cases"] for item in scenes}),
            "state": "已逐场景复审；等待脱敏真实案件样本继续提升成熟度",
            "scenes": scenes,
        })

    modules = []
    for module in catalog.get("modules", []):
        modules.append({
            "id": module.get("id"),
            "name": module.get("name"),
            "rule_count": len(module.get("rules", [])),
            "clue_path_count": len(module.get("clue_paths", [])),
            "analysis_test_count": len(module.get("analysis_tests", [])),
            "validation_case_count": len(module.get("validation_cases", [])),
            "source_refs": list(module.get("source_refs", [])),
            "report_boundary": module.get("report_boundary"),
        })

    return {
        "version": "2.0.0",
        "positioning": catalog.get("positioning"),
        "governance": catalog.get("governance"),
        "inventory": inventory,
        "canonical_modules": modules,
        "industry_matrix": industries,
        "depth_distribution": {
            "clue_steps": dict(sorted(Counter(item["clue_steps"] for item in all_scenes).items())),
            "validation_cases": dict(sorted(Counter(item["validation_cases"] for item in all_scenes).items())),
            "analysis_tests": dict(sorted(Counter(item["analysis_tests"] for item in all_scenes).items())),
        },
        "quality_controls": [
            "现行目录只保留完成事实、证据、反向证据和程序合同的内容",
            "规则、线索、证据和分析共同编制，不追求一对一条数或固定总量",
            "每个规则均以可证伪事实命题、必需字段和合理解释表达",
            "每个主题同时保留支持证据、反向证据和证据不足条件",
            "每个行业场景记录其独立深度理由，不按行业等量配置",
            "线索、事实、测算、审理和最终决定严格分层",
        ],
        "known_gaps": [
            {"priority": "P0", "gap": "真实案件样本验证", "control": "所有新增及复审场景在取得合法脱敏样本后记录误报、漏报、反例和程序结果，达到门槛后再提升成熟度。"},
            {"priority": "P0", "gap": "地方政策口径", "control": "涉及地方授权和属地执行口径时，必须取得业务期间的有效全文并由人工复核。"},
            {"priority": "P1", "gap": "尚未编制的行业", "control": "后续行业按业务自然场景从零编制，不复制现有行业的场景数、步骤数或案例数。"},
        ],
    }

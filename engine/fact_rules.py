# -*- coding: utf-8 -*-
"""权威事实核查规则库（权威横向目录版本）。

行业场景契约已由 engine/tax_redlines.py（红线驱动·线索链·证据链·论证链）
替代；本模块只保留来自 methodology_canonical_catalog.json 的权威横向规则，
不再加载、解析或计数任何行业场景契约。

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


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


@lru_cache(maxsize=1)
def load_canonical_catalog() -> dict:
    return _read(CATALOG_FILE)


def _source_names(module: dict, catalog: dict) -> str:
    source_map = {item["id"]: item["name"] for item in catalog.get("official_sources", [])}
    return "；".join(source_map.get(ref, ref) for ref in module.get("source_refs", []))


def _module_importance(module_name):
    name_lower = (module_name or "").lower()
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
    return 3


def _score_to_level(score):
    if score >= 9: return "极高风险"
    if score >= 7: return "高风险"
    if score >= 5: return "中风险"
    if score >= 3: return "低风险"
    return "信息"


@lru_cache(maxsize=1)
def load_flat_rules() -> list:
    catalog = load_canonical_catalog()
    output = []
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
                "source": "税务风险检查权威方法论目录",
                "human_review_required": True,
                "automatic_determination_allowed": False,
                "threshold": None,
            })
    return output


@lru_cache(maxsize=1)
def load_flat_clues() -> list:
    catalog = load_canonical_catalog()
    output = []
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
    return output


@lru_cache(maxsize=1)
def load_flat_evidence() -> list:
    output = []
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
    return output


@lru_cache(maxsize=1)
def load_flat_analysis() -> list:
    output = []
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
    return output


def governance_inventory() -> dict:
    catalog = load_canonical_catalog()
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
        "industry_fact_contracts": 0,
        "rules": len(load_flat_rules()),
        "clue_paths": len(load_flat_clues()),
        "evidence_plans": len(load_flat_evidence()),
        "analysis_plans": len(load_flat_analysis()),
        "industry_scenarios": 0,
        "portfolio_scene_count": 0,
        "portfolio_contract_count": 0,
        "count_semantics": {
            "rules": "权威事实核查规则（横向、行业无关），来自 methodology_canonical_catalog.json",
            "clue_paths": "权威线索链模板数",
            "evidence_plans": "权威证据链模板数",
            "analysis_plans": "权威分析链模板数",
        },
        "industry_scenario_counts": {},
        "clue_depths": [],
        "validation_depths": [],
        "domain_collaboration_depths": [],
    }

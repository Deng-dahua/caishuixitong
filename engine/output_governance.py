# -*- coding: utf-8 -*-
"""正式输出治理（取代原 scenario_execution 的场景驱动执行核心）。

设计原则（与红线驱动方法论一致）：
- 行业无关：不再按行业套场景契约生成"待核事实"，行业场景方法论已由
  engine/tax_redlines.py（红线驱动·线索链·证据链·论证链）替代。
- 原子计算仍是事实来源：直接调用 verified_rule_engine.run_verified_rules，
  其经过验证的原子规则在已上传数据上产生"被观察事实"。
- 正式输出封印保留：只有带 _scenario_governed 标记的发现才能进入正式报告，
  与既有注入/封印逻辑兼容（委外加工、供应链联网、客观域发现均带该标记）。
- 任何输出都不得替代行政认定：禁止自动定性、自动核定税额或移送。
"""

from __future__ import annotations

import copy
from collections import defaultdict
from datetime import datetime
from typing import Any

from engine.verified_rule_engine import VERIFIED_RULE_CATALOG, run_verified_rules


GOVERNANCE_STATUS = "output_governed"
EXECUTION_VERSION = "1.0.0"


def _rule_index() -> dict:
    return {item["id"]: item for item in VERIFIED_RULE_CATALOG}


def _trusted_observation(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    rule_id = str(item.get("rule_id", ""))
    return (
        rule_id in _rule_index()
        and item.get("source_lineage_status") == "observed_from_uploaded_data"
        and item.get("rule_maturity") == "verified_executable_screening"
    )


def _domain_summary(findings: list) -> list:
    grouped = defaultdict(list)
    for finding in findings:
        grouped[finding.get("domain", "待核事实")].append(finding)
    return [
        {
            "domain": domain,
            "count": len(items),
            "high": 0,
            "mid": 0,
            "status": "待人工复核",
            "findings": items,
        }
        for domain, items in sorted(grouped.items())
    ]


def run_output_governance(industry=None, file_results=None, engine_data=None) -> dict:
    engine_data = engine_data or {}
    atomic = run_verified_rules(engine_data)
    raw_observations = atomic.get("findings", [])
    observations = [copy.deepcopy(item) for item in raw_observations if _trusted_observation(item)]
    rejected = len(raw_observations) - len(observations)
    findings = []
    for item in observations:
        item = copy.deepcopy(item)
        item["_scenario_governed"] = True
        item.setdefault("scenario_scope", "common_fact_gate")
        findings.append(item)
    return {
        "version": EXECUTION_VERSION,
        "methodology_version": None,
        "executed_at": datetime.now().isoformat(),
        "governance_status": GOVERNANCE_STATUS,
        "industry_input": str(industry or ""),
        "industry_code": "",
        "industry_resolved": False,
        "status": "待人工复核",
        "decision_boundary": (
            "原子计算只形成观察事实；行业无关红线判定在 redline_detection 阶段完成。"
            "未经证据、政策时效、金额底稿和有权人员审签，不得形成正式结论。"
        ),
        "atomic_rule_version": atomic.get("version"),
        "atomic_rule_count": atomic.get("catalog_count", 0),
        "atomic_executions": copy.deepcopy(atomic.get("executions", [])),
        "trusted_observation_count": len(observations),
        "rejected_observation_count": rejected,
        "available_source_families": [],
        "observed_file_types": [],
        "source_quality_issues": [],
        "industry_scene_count": 0,
        "industry_scenes_assessed": 0,
        "industry_scenes_with_observations": 0,
        "industry_scene_findings": 0,
        "common_fact_findings": len(findings),
        "unmapped_industry_observations": [],
        "scenes": [],
        "review_plan": {},
        "findings": findings,
        "domain_summary": _domain_summary(findings),
        "report_release_allowed": False,
    }


def seal_governed_findings(execution: dict) -> list:
    if not isinstance(execution, dict) or execution.get("governance_status") != GOVERNANCE_STATUS:
        raise ValueError("缺少有效的输出治理结果")
    findings = execution.get("findings", [])
    if not isinstance(findings, list):
        raise ValueError("输出治理结果缺少规范待核事实")
    sealed = []
    identities = set()
    for item in findings:
        if not isinstance(item, dict) or item.get("_scenario_governed") is not True:
            continue
        identity = str(item.get("scene_fact_id") or item.get("fact_id") or item.get("type") or "").strip()
        if not identity or identity in identities:
            continue
        identities.add(identity)
        canonical = copy.deepcopy(item)
        if canonical.get("conclusion_grade") == "已核定":
            canonical["required_human_review"] = True
            canonical["automatic_determination_allowed"] = False
            canonical["report_release_allowed"] = True
            canonical["release_status"] = "已核定_限于所报资料勾稽_待人工确认"
        else:
            canonical["required_human_review"] = True
            canonical["automatic_determination_allowed"] = False
            canonical["report_release_allowed"] = False
            canonical["release_status"] = "草稿_待人工复核"
        sealed.append(canonical)
    return sealed

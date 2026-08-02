# -*- coding: utf-8 -*-
"""候选疑点规则治理。

原有规则库是调查知识，不因字段数量、风险等级或模型生成而自动成为生产规则。
本模块只生成治理状态和整改队列，不改写原始资产，也不作法律有效性判断。
"""

from __future__ import annotations

from collections import Counter, defaultdict
import re


AUTHOR_OR_MODEL_MARKERS = ("人工", "LLM", "智能更新", "模型", "自动生成")
UNSAFE_MARKERS = (
    "铁证", "移送公安", "自动立案", "定性认定", "定性成立", "即可定案",
    "认定为偷税", "构成偷税", "构成虚开", "罚款", "刑事追诉",
)
REQUIRED_PROVENANCE_FIELDS = ("official_url", "checked_at", "effective_period", "reviewer")


def _normalise(value):
    return re.sub(r"[\W_\d]+", "", str(value or "")).lower()


def _duplicate_index(rules):
    groups = defaultdict(list)
    for rule in rules:
        key = _normalise(rule.get("item"))
        if key:
            groups[key].append(str(rule.get("id", "")))
    clusters = {
        key: ids for key, ids in groups.items() if len(ids) > 1
    }
    by_rule = {
        rule_id: ids for ids in clusters.values() for rule_id in ids
    }
    return clusters, by_rule


def _provenance_state(rule):
    provenance = rule.get("provenance")
    if isinstance(provenance, dict) and all(
        str(provenance.get(field, "")).strip() for field in REQUIRED_PROVENANCE_FIELDS
    ):
        return "official_provenance_recorded"
    source = str(rule.get("source", "")).strip()
    if not source:
        return "source_missing"
    if any(marker.lower() in source.lower() for marker in AUTHOR_OR_MODEL_MARKERS):
        return "author_or_model_only"
    return "external_reference_unverified"


def _unsafe_fields(rule):
    fields = []
    for field, value in rule.items():
        if not isinstance(value, str):
            continue
        if any(marker in value for marker in UNSAFE_MARKERS):
            fields.append(field)
    return sorted(fields)


def _governance_for_rule(rule, duplicate_by_rule):
    rule_id = str(rule.get("id", ""))
    provenance_state = _provenance_state(rule)
    duplicate_ids = duplicate_by_rule.get(rule_id, [])
    unsafe_fields = _unsafe_fields(rule)
    has_executable_spec = isinstance(rule.get("executable_spec"), dict)
    flags = []
    if provenance_state != "official_provenance_recorded":
        flags.append("external_provenance_not_verified")
    if not str(rule.get("policy_ref", "")).strip():
        flags.append("policy_reference_missing")
    else:
        flags.append("policy_reference_text_not_period_verified")
    if duplicate_ids:
        flags.append("normalised_title_duplicate_review")
    if unsafe_fields:
        flags.append("raw_text_requires_neutralised_display")
    if not has_executable_spec:
        flags.append("field_contract_not_verified")
    if str(rule.get("level", "")) in ("高风险", "极高风险"):
        flags.append("legacy_risk_grade_not_release_grade")

    maturity = "M0_duplicate_review" if duplicate_ids else "M1_structured_candidate"
    priority = "P0" if unsafe_fields or duplicate_ids else "P1"
    next_action = (
        "先合并或区分重复事项，再补官方来源、适用期间、字段契约、正常解释和测试样本。"
        if duplicate_ids else
        "补官方来源、适用期间、字段契约、计算方法、正常解释及正反测试样本。"
    )
    return {
        "rule_id": rule_id,
        "maturity": maturity,
        "release_status": "candidate_not_executable",
        "provenance_status": provenance_state,
        "policy_validity_status": "not_verified_for_case_period",
        "duplicate_rule_ids": duplicate_ids,
        "unsafe_raw_fields": unsafe_fields,
        "field_contract_status": "present_unreviewed" if has_executable_spec else "missing",
        "legacy_risk_grade": str(rule.get("level", "")),
        "priority": priority,
        "quality_flags": flags,
        "next_action": next_action,
    }


def build_candidate_governance(rules, queue_limit=80):
    """生成全量治理摘要和可排序整改队列。"""
    rules = [rule for rule in (rules or []) if isinstance(rule, dict)]
    duplicate_clusters, duplicate_by_rule = _duplicate_index(rules)
    items = [_governance_for_rule(rule, duplicate_by_rule) for rule in rules]
    source_distribution = Counter(item["provenance_status"] for item in items)
    maturity_distribution = Counter(item["maturity"] for item in items)
    raw_unsafe = sum(bool(item["unsafe_raw_fields"]) for item in items)
    executable_specs = sum(item["field_contract_status"] != "missing" for item in items)
    queue = sorted(
        items,
        key=lambda item: (
            0 if item["priority"] == "P0" else 1,
            -len(item["quality_flags"]),
            int(item["rule_id"]) if item["rule_id"].isdigit() else 10**9,
        ),
    )
    return {
        "version": "1.0.0",
        "positioning": "治理清单只说明候选知识的质量和整改顺序，不把法条文字、模型生成或风险等级当成规则验证。",
        "summary": {
            "candidate_rules": len(rules),
            "official_provenance_recorded": source_distribution.get("official_provenance_recorded", 0),
            "source_missing": source_distribution.get("source_missing", 0),
            "author_or_model_only": source_distribution.get("author_or_model_only", 0),
            "external_reference_unverified": source_distribution.get("external_reference_unverified", 0),
            "policy_reference_period_verified": 0,
            "raw_rules_requiring_language_neutralisation": raw_unsafe,
            "normalised_duplicate_clusters": len(duplicate_clusters),
            "normalised_duplicate_rule_count": sum(len(ids) - 1 for ids in duplicate_clusters.values()),
            "candidate_field_contracts_present": executable_specs,
            "production_executable_rules_in_candidate_library": 0,
        },
        "source_distribution": dict(source_distribution),
        "maturity_distribution": dict(maturity_distribution),
        "duplicate_clusters": list(duplicate_clusters.values()),
        "priority_queue": queue[:max(int(queue_limit or 0), 0)],
        "release_gate": [
            "官方来源、文号、链接、有效期间和核验人齐全",
            "适用主体、税费事项、业务期间和排除情形明确",
            "所需资料、字段语义、关联键、计算方法和容差明确",
            "正例、反例、缺失资料和边界样本通过回归测试",
            "只形成资料质量事项或待核事实，不自动作法律定性",
            "维护人、版本、误报复核、停用条件和回退方案齐全",
        ],
    }


def annotate_candidate_rules(rules):
    """为只读响应逐条附加治理状态；不修改调用方对象。"""
    source_rules = [rule for rule in (rules or []) if isinstance(rule, dict)]
    _, duplicate_by_rule = _duplicate_index(source_rules)
    annotated = []
    for rule in source_rules:
        copied = dict(rule)
        copied["_governance"] = _governance_for_rule(rule, duplicate_by_rule)
        annotated.append(copied)
    return annotated

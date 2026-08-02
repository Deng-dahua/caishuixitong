# -*- coding: utf-8 -*-
"""只读方法论资产的展示适配。

原始规则资产保持可回退；接口响应在内存中加入统一状态并净化自动定性措辞。
"""

from __future__ import annotations

from engine.methodology_guardrails import neutralise_methodology_text


def _adapt(value):
    if isinstance(value, str):
        return neutralise_methodology_text(value)
    if isinstance(value, list):
        return [_adapt(item) for item in value]
    if not isinstance(value, dict):
        return value

    adapted = {}
    for key, item in value.items():
        item = _adapt(item)
        if key == "name" and isinstance(item, str):
            item = item.replace("定性", "专业复核").replace("定案", "人工复核")
        adapted[key] = item
    return adapted


def prepare_methodology_asset(asset_name, payload):
    if asset_name == "rules" and isinstance(payload, list):
        from engine.candidate_rule_governance import annotate_candidate_rules
        payload = annotate_candidate_rules(payload)
    adapted = _adapt(payload)
    if asset_name == "framework":
        return adapted

    def mark(item):
        if not isinstance(item, dict):
            return item
        item["default_review_status"] = "pending_applicability_and_evidence_review"
        item["conclusion_scope"] = "screening_and_review_only"
        item["human_review_required"] = True
        item["procedure_boundary"] = "调查措施须逐项核验法定权限、批准程序、必要性、特定对象和期间，并保障陈述申辩、隐私与数据安全。"
        return item

    if isinstance(adapted, list):
        return [mark(item) for item in adapted]
    if isinstance(adapted, dict):
        for collection_key in ("rules", "items", "chains", "evidence_chains", "analysis_chains", "scenarios"):
            collection = adapted.get(collection_key)
            if isinstance(collection, list):
                adapted[collection_key] = [mark(item) for item in collection]
        return adapted
    return adapted

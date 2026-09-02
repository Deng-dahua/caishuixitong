# -*- coding: utf-8 -*-
"""只读权威方法论资产的展示适配。"""

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
    if str(asset_name or "").endswith("_scenario_contracts"):
        from engine.methodology_catalog import ASSET_TO_CODE, load_reviewed_scenario_contracts
        code = ASSET_TO_CODE.get(str(asset_name or ""))
        if code:
            try:
                # 2026-08-26 审计修复（P1-4）：解析失败时优雅回退到原始 payload，
                # 不中断接口（原实现直接将异常抛出导致 500）。
                payload = load_reviewed_scenario_contracts(code)
            except Exception:
                pass
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
        if asset_name == "portfolio":
            for contract in adapted.get("contracts", []):
                if isinstance(contract, dict):
                    contract["scenarios"] = [mark(item) for item in contract.get("scenarios", [])]
        return adapted
    return adapted

# -*- coding: utf-8 -*-
"""规则增强器 —— 将精写编制标准的23字段全量注入finding

设计原则：
- 每条被触发的疑点规则有23个字段，引擎生成的finding只含type/severity/detail等基础信息
- 本模块将规则的完整23字段"附着"到finding上，使报告能展示完整的疑点知识体系
- 不修改finding已有的字段，只追加 _rule_* 前缀的字段
"""
import json, os

_RULES = None
_RULE_MAP = {}

def _load_rules():
    global _RULES, _RULE_MAP
    if _RULES is not None:
        return
    try:
        from engine.methodology_catalog import load_flat_rules
        _RULES = load_flat_rules()
        for r in _RULES:
            rid = str(r.get("id", ""))
            if rid:
                _RULE_MAP[rid] = r
    except Exception:
        _RULES = []
        _RULE_MAP = {}


def get_rule(rule_id):
    """根据规则ID获取完整的23字段规则数据"""
    _load_rules()
    return _RULE_MAP.get(str(rule_id))


def enrich_finding(finding, rule_id=None):
    """
    将规则的23字段注入finding。

    Args:
        finding: dict, 引擎生成的发现
        rule_id: str/int, 关联的规则ID。如果finding中有rule_id字段则自动提取

    Returns:
        finding (原地修改)
    """
    if rule_id is None:
        rule_id = finding.get("rule_id") or finding.get("id")

    rule = get_rule(rule_id)
    if not rule:
        return finding

    # ═══ 基础字段（9项）═══
    finding["_rule_id"] = rule.get("id")
    finding["_rule_item"] = rule.get("item", "")
    finding["_rule_category"] = rule.get("category", "")
    finding["_rule_level"] = rule.get("level", "")
    finding["_rule_score"] = rule.get("score", "")
    finding["_rule_check_frequency"] = rule.get("check_frequency", "")
    finding["_rule_policy_ref"] = rule.get("policy_ref", "")
    finding["_rule_tax_impact"] = rule.get("tax_impact", "")
    finding["_rule_applicable_condition"] = rule.get("applicable_condition", "")

    # ═══ 来源标记（2项）═══
    finding["_rule_source"] = rule.get("source", "")
    finding["_rule_auto_type"] = rule.get("auto_type", "")

    # ═══ 深度字段（12项）═══
    finding["_rule_direction"] = rule.get("direction", "")
    finding["_rule_drill_questions"] = rule.get("drill_questions", "")
    finding["_rule_phenomena"] = rule.get("phenomena", "")
    finding["_rule_focus"] = rule.get("focus", "")
    finding["_rule_normal_reason"] = rule.get("normal_reason", "")
    finding["_rule_determination"] = rule.get("determination", "")
    finding["_rule_risk_table"] = rule.get("risk_table", "")
    finding["_rule_evidence"] = rule.get("evidence", "")
    finding["_rule_threshold"] = rule.get("threshold", "")
    finding["_rule_action"] = rule.get("action", "")
    finding["_rule_suggestion"] = rule.get("suggestion", "")
    finding["_rule_remedy"] = rule.get("remedy", "")

    # ═══ 兼容旧字段 —— 无 _rule_ 前缀 = 一级字段（与已有代码兼容）═══
    if not finding.get("direction"):
        finding["direction"] = rule.get("direction", "")
    if not finding.get("drill_questions"):
        finding["drill_questions"] = rule.get("drill_questions", "")
    if not finding.get("policy_ref"):
        finding["policy_ref"] = rule.get("policy_ref", "")
    if not finding.get("tax_impact"):
        finding["tax_impact"] = rule.get("tax_impact", "")
    if not finding.get("determination"):
        finding["determination"] = rule.get("determination", "")
    if not finding.get("suggestion"):
        finding["suggestion"] = rule.get("suggestion", "")
    if not finding.get("remedy"):
        finding["remedy"] = rule.get("remedy", "")
    if not finding.get("evidence"):
        finding["evidence"] = rule.get("evidence", "")
    if not finding.get("phenomena"):
        finding["phenomena"] = rule.get("phenomena", "")
    if not finding.get("focus"):
        finding["focus"] = rule.get("focus", "")
    if not finding.get("normal_reason"):
        finding["normal_reason"] = rule.get("normal_reason", "")
    if not finding.get("threshold"):
        finding["threshold"] = rule.get("threshold", "")
    if not finding.get("action"):
        finding["action"] = rule.get("action", "")

    return finding


def enrich_findings(findings, triggered_rule_ids=None):
    """
    批量增强一组findings。根据finding中的rule_id自动匹配规则。

    Args:
        findings: list of dict
        triggered_rule_ids: set/list of rule IDs to pre-filter (optional)
    """
    _load_rules()
    for f in findings:
        if not isinstance(f, dict):
            continue
        rid = f.get("rule_id") or f.get("id")
        if rid and (triggered_rule_ids is None or str(rid) in triggered_rule_ids):
            enrich_finding(f, rid)
    return findings

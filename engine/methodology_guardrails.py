# -*- coding: utf-8 -*-
"""稽查方法论输出门禁。

统一把规则、模型和链路输出限制在“筛查—调查—证据复核—人工审理”边界内。
该模块不删除原始资料，也不判断最终法律责任。
"""

from __future__ import annotations

import re


_DIRECT_REPLACEMENTS = (
    ("封存手机和电脑防止串供", "依法固定与待证事实相关且经批准取得的电子数据，并完整记录提取、校验和交接程序"),
    ("扣押所有开票设备(电脑、税控盘、UKey)、账务资料、银行U盾，并对现场人员进行控制", "经权限、批准和必要性审查后，依法固定与待证事实相关的开票、账务及电子数据；涉及人员的措施由有权机关依法决定"),
    ("查封所有企业的财务资料、电脑、服务器", "经权限、批准和必要性审查后，依法固定与待证事实相关的资料和电子数据"),
    ("封存财务软件服务器和电脑硬盘", "经权限和程序审查后，依法固定与待证事实相关的财务系统电子数据"),
    ("全部银行账户流水", "与待证事实相关且依法获准核验的特定账户、期间和交易资料"),
    ("所有银行账户流水", "与待证事实相关且依法获准核验的特定账户、期间和交易资料"),
    ("隔离询问", "依照法定程序分别询问"),
    ("人员审讯", "依法询问相关人员"),
    ("突击检查", "依法依权限开展现场检查"),
    ("全量资金穿透", "按待证事实、权限和期间开展必要的资金核验"),
    ("防止证据转移", "依法做好证据保全"),
    ("不给思考时间", "保障如实陈述、说明和申辩的权利"),
    ("直接追问", "围绕待证事实询问"),
    ("自认材料", "当事人陈述材料"),
    ("隐匿收入定性成立", "存在收入完整性待核事项"),
    ("虚开发票定性成立", "存在发票与交易真实性待核事项"),
    ("定性成立", "达到提交人工复核条件"),
    ("证据闭环成立", "达到内部多源提示阈值"),
    ("确认线索成立", "形成待核线索"),
    ("认定为偷税", "需由有权人员依法复核相关法律性质"),
    ("认定偷税", "相关法律性质须由有权人员依法复核"),
    ("定性为偷税", "相关法律性质须由有权人员依法复核"),
    ("构成偷税", "是否涉及相关法律责任尚待依法复核"),
    ("依法定性为偷税", "相关法律性质须由有权人员依法复核"),
    ("构成虚开", "是否涉及发票违法尚待依法复核"),
    ("建议追缴", "税款影响须按适用期间和法定程序复核；原模板建议为"),
    ("移送公安", "是否需要行政刑事衔接须由有权机关依法判断"),
    ("按虚开发票立案", "是否达到立案或移送条件须由有权机关依法判断"),
    ("多笔闭环叠加则立案", "多笔闭环只提高核验优先级，立案条件须另行依法判断"),
    ("多维异常是定案", "多维异常提高核验优先级但不能替代审理"),
    ("七维全异常=企业账务大概率全面造假", "七维异常须逐项排除合理解释并提交人工复核"),
    ("三个及以上维度的矛盾通常足以形成认定结论", "三个及以上维度的矛盾可提高调查优先级，但仍须审查来源独立性、反证和程序"),
    ("涉税违法的主观意图明显", "主观状态和客观行为均需结合完整证据依法复核"),
    ("主观故意成立", "主观状态待结合完整证据复核"),
    ("唯一合理解释", "需要重点核验的解释之一"),
    ("两证即可定案", "两个来源可提高核验优先级，但仍须审查来源独立性和证明力"),
    ("单此一条即触发稽查", "单项达到内部筛查阈值"),
    ("铁证级", "多源支持级"),
    ("铁证", "经来源谱系去重的多源材料"),
    ("系统性造假", "多域异常待核"),
    ("全面造假", "多域异常待核"),
    ("即可定案", "可提交人工复核"),
)

_PENALTY_SENTENCE = re.compile(
    r"[^。；\n]*(?:罚款|刑事追诉|追缴少缴|补缴[^。；\n]*滞纳金|立即立案)[^。；\n]*[。；]?"
)


def _clean_text(value):
    if not isinstance(value, str) or not value:
        return value
    cleaned = value
    for old, new in _DIRECT_REPLACEMENTS:
        cleaned = cleaned.replace(old, new)
    cleaned = _PENALTY_SENTENCE.sub(
        "具体税款、滞纳金、处罚或移送后果须依据适用期间、完整事实、证据和法定程序由有权人员复核。",
        cleaned,
    )
    return cleaned


def neutralise_methodology_text(value):
    """供只读方法论资产接口复用的文本边界净化。"""
    return _clean_text(value)


def _alternative_explanations(text):
    groups = []
    if any(word in text for word in ("收款", "银行", "资金", "回流")):
        groups.extend(["借款或还款", "股东投入或资本往来", "代收代付", "退款冲正", "跨期结算或预收款"])
    if any(word in text for word in ("发票", "开票", "进项", "销项")):
        groups.extend(["开票与履约时点差异", "红冲或退货", "第三方付款", "免税或不征税事项", "票面品名与实际业务映射差异"])
    if any(word in text for word in ("存货", "进销", "产能", "能耗", "加工", "物流")):
        groups.extend(["委托加工或外包生产", "在途、退货或盘点差异", "季节性和停工", "客户自提或包价运输", "产品转换和合理损耗"])
    if any(word in text for word in ("工资", "人员", "社保", "个税")):
        groups.extend(["劳务外包或派遣", "兼职或灵活用工", "入离职期间差异", "非工资所得分类", "社保缴费口径差异"])
    if any(word in text for word in ("费用", "成本", "资产")):
        groups.extend(["受益期或资本化差异", "关联方代垫", "暂估和跨期结算", "业务模式造成的结构差异"])
    if not groups:
        groups = ["主体或期间口径差异", "资料缺失或解析误差", "正常商业安排", "政策例外或过渡规则"]
    return list(dict.fromkeys(groups))[:6]


def _evidence_state(finding, combined_text):
    current = finding.get("finding_status")
    if current:
        return current
    if any(word in combined_text for word in ("缺少", "缺失", "无数据", "无法评估", "资料不足")):
        return "insufficient_data"
    cross = finding.get("cross_domain_evidence") or {}
    dimensions = cross.get("dimensions_triggered", []) if isinstance(cross, dict) else []
    if len(dimensions) >= 2 or finding.get("_phase3_cross_validated"):
        return "partially_supported_pending_human_review"
    if finding.get("source_chain") == "analysis":
        return "hypothesis_pending_evidence_review"
    return "clue_pending_investigation"


def review_finding(finding):
    """原地规范一条发现，并返回同一对象以兼容现有流水线。"""
    if not isinstance(finding, dict):
        return finding

    for field in (
        "type", "detail", "description", "how_found", "tax_impact", "suggestion",
        "policy_ref", "determination", "action", "remedy", "focus", "normal_reason",
        "drill_questions", "evidence", "risk_table", "direction", "phenomena",
        "threshold", "applicable_condition",
    ):
        if field in finding:
            finding[field] = _clean_text(finding.get(field))
    for field, value in list(finding.items()):
        if field.startswith("_rule_") and isinstance(value, str):
            finding[field] = _clean_text(value)

    combined = " ".join(str(finding.get(field, "")) for field in (
        "type", "detail", "description", "category", "domain"
    ))
    state = _evidence_state(finding, combined)
    if state == "insufficient_data":
        finding["level"] = "信息"
        try:
            score = float(finding.get("score", 0) or 0)
        except (TypeError, ValueError):
            score = 0
        finding["score"] = min(score, 2)

    finding["finding_status"] = state
    finding["required_human_review"] = True
    finding["legal_review_status"] = "not_verified_for_case_period"
    finding["conclusion_scope"] = "screening_and_review_only"
    finding["alternative_explanations"] = finding.get("alternative_explanations") or _alternative_explanations(combined)
    finding["methodology_controls"] = {
        "source_trace_required": True,
        "applicability_review_required": True,
        "supporting_and_opposing_evidence_required": True,
        "independent_source_lineage_required": True,
        "authority_approval_and_minimum_necessary_scope_required": True,
        "statement_defence_and_privacy_protection_required": True,
        "amount_and_legal_characterisation_separate": True,
        "decision_boundary": "系统输出不得替代行政认定、处理处罚、移送或司法判断。",
    }
    return finding


def review_findings(findings):
    return [review_finding(finding) for finding in findings if isinstance(finding, dict)]


def _clean_review_section(value):
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, list):
        return [_clean_review_section(item) for item in value]
    if isinstance(value, dict):
        if "type" in value and any(key in value for key in ("detail", "description", "level", "score")):
            review_finding(value)
        for key, item in list(value.items()):
            value[key] = _clean_review_section(item)
    return value


def review_report_methodology(report_data):
    """净化报告中的综合判断和域结果，并标明评分用途。"""
    if not isinstance(report_data, dict):
        return report_data
    for key in (
        "all_findings", "domain_results", "comprehensive", "overall_assessment",
        "methodology_summary", "core_issues", "prioritized_actions",
    ):
        if key in report_data:
            report_data[key] = _clean_review_section(report_data[key])

    comprehensive = report_data.get("comprehensive")
    if isinstance(comprehensive, dict):
        assessment = comprehensive.get("overall_assessment")
        if isinstance(assessment, dict):
            assessment["assessment_scope"] = "screening_priority_not_legal_conclusion"
            assessment["assessment_status"] = "pending_human_review"
            assessment["score_usage"] = "仅用于安排资料核验顺序，不决定违法性质、处理处罚或纳税信用。"
    return report_data

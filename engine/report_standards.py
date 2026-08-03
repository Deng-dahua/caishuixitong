# -*- coding: utf-8 -*-
"""报告编制质量门禁：保护事实、证据、政策和人工审理边界。"""

from __future__ import annotations

import re


REPORT_STRUCTURE = {
    "封面": {"title": "涉税风险分析报告", "fields": ["被分析单位", "所属行业", "分析期间", "报告日期", "密级"]},
    "第一章": {"title": "任务、范围与方法", "content": ["任务来源", "资料来源", "分析范围", "方法论", "局限性"]},
    "第二章": {"title": "主体、业务与数据概览", "content": ["主体边界", "经营模式", "资料清单", "数据质量", "政策期间"]},
    "第三章": {"title": "待核事实与资料缺口", "content": ["待核事项", "适用边界", "观察信号", "正常解释", "资料缺口"]},
    "第四章": {"title": "调查路径与业务域协同", "content": ["调查主键", "调查步骤", "分支条件", "域协同", "停止条件"]},
    "第五章": {"title": "证据组织与分析论证", "content": ["证明对象", "支持证据", "反向证据", "证据三性", "竞争解释", "金额复算"]},
    "第六章": {"title": "政策依据与专业复核", "content": ["事实期间", "现行有效依据", "税费要件", "会计处理", "人工复核状态"]},
    "第七章": {"title": "结论边界与附录", "content": ["限定结论", "未决事项", "证据溯源", "政策来源", "分析日志", "审签记录"]},
}


REPORT_QUALITY_RULES = [
    {"id": "RQ1", "rule": "报告必须声明任务和分析范围"},
    {"id": "RQ2", "rule": "报告必须声明资料局限和未覆盖范围"},
    {"id": "RQ3", "rule": "每项发现必须保留人工复核和禁止自动定性边界"},
    {"id": "RQ4", "rule": "异常、损坏或未经核验的法律引用不得进入报告"},
    {"id": "RQ5", "rule": "法律依据必须记录事实期间适用性核验状态"},
    {"id": "RQ6", "rule": "充分支持的事实必须具有可回查的证据来源"},
    {"id": "RQ7", "rule": "充分支持的事实必须处理主要反向解释"},
    {"id": "RQ8", "rule": "确定金额必须具有可复算底稿和口径"},
    {"id": "RQ9", "rule": "报告不得把评分、资料缺失或行业均值写成违法结论"},
    {"id": "RQ10", "rule": "被分析主体必须能够唯一识别"},
    {"id": "RQ11", "rule": "同一待核事实不得重复计数"},
    {"id": "RQ12", "rule": "报告必须记录方法论、场景或调查链的移交状态"},
]


_MALFORMED_POLICY_RE = re.compile(r"(?:第\s*)?\d*1720(?:条|款|项)|(?:^|\D)[123456789]1720条")
_AUTOMATIC_CONCLUSION_TERMS = (
    "系统自动认定",
    "模型认定违法",
    "资料缺失即违法",
    "评分达到即可定案",
    "行业均值即可认定",
)
_SUPPORTED_STATES = {"事实充分支持_待审理", "事实充分支持", "已人工确认"}


def _findings(report_data):
    values = report_data.get("all_findings", report_data.get("findings", []))
    return values if isinstance(values, list) else []


def _has_traceable_evidence(finding):
    evidence = finding.get("evidence") or finding.get("items") or finding.get("evidence_rows")
    if evidence:
        return True
    return bool(finding.get("source_file") or finding.get("source_files") or finding.get("source_rows"))


def _has_opposing_review(finding):
    return bool(
        finding.get("opposing_evidence")
        or finding.get("reasonable_explanations")
        or finding.get("_escape_hatch")
        or finding.get("alternative_explanations")
    )


def _has_amount_workpaper(finding):
    impact = str(finding.get("tax_impact", "") or "")
    if not re.search(r"\d", impact):
        return True
    return bool(
        finding.get("tax_calculation")
        or finding.get("calculation_basis")
        or finding.get("amount_workpaper")
    )


def _methodology_handoff_present(report_data):
    if report_data.get("_methodology_applied") or report_data.get("scenario_methodology"):
        return True
    comprehensive = report_data.get("comprehensive") or {}
    return bool(comprehensive.get("scenario_methodology") or comprehensive.get("methodology_summary"))


def _quality_checks(report_data):
    findings = _findings(report_data)
    supported = [
        item for item in findings
        if str(item.get("conclusion_state", item.get("status", ""))) in _SUPPORTED_STATES
    ]
    policy_items = [item for item in findings if str(item.get("policy_ref", "")).strip()]
    identities = [
        str(item.get("fact_id") or item.get("scene_fact_id") or item.get("type") or "").strip()
        for item in findings
    ]
    nonempty_identities = [item for item in identities if item]
    all_text = "\n".join(
        " ".join(str(item.get(key, "") or "") for key in ("detail", "description", "suggestion", "conclusion"))
        for item in findings
    )
    target = report_data.get("target_entity") or {}
    checks = {
        "RQ1": bool(report_data.get("scope") or report_data.get("analysis_scope")),
        "RQ2": bool(report_data.get("limitations")),
        "RQ3": all(
            item.get("required_human_review") is True
            and item.get("automatic_determination_allowed") is False
            for item in findings
        ),
        "RQ4": all(
            not _MALFORMED_POLICY_RE.search(
                " ".join(str(item.get(key, "") or "") for key in ("policy_ref", "law_ref", "tax_impact", "detail", "description", "suggestion"))
            )
            for item in findings
        ),
        "RQ5": all(str(item.get("policy_validity", "")).strip() for item in policy_items),
        "RQ6": all(_has_traceable_evidence(item) for item in supported),
        "RQ7": all(_has_opposing_review(item) for item in supported),
        "RQ8": all(_has_amount_workpaper(item) for item in supported),
        "RQ9": not any(term in all_text for term in _AUTOMATIC_CONCLUSION_TERMS),
        "RQ10": bool(target.get("name") or report_data.get("company_name")),
        "RQ11": len(nonempty_identities) == len(set(nonempty_identities)),
        "RQ12": _methodology_handoff_present(report_data),
    }
    return checks


def check_report_standards(report_data):
    """逐项执行报告门禁，返回可解释的质量结果。"""
    if not isinstance(report_data, dict) or not report_data:
        return {
            "total": len(REPORT_QUALITY_RULES),
            "passed": 0,
            "failed": len(REPORT_QUALITY_RULES),
            "failed_ids": [item["id"] for item in REPORT_QUALITY_RULES],
            "passed_ids": [],
            "score": f"0/{len(REPORT_QUALITY_RULES)}",
            "details": [{"id": item["id"], "passed": False, "rule": item["rule"]} for item in REPORT_QUALITY_RULES],
        }
    checks = _quality_checks(report_data)
    details = [
        {"id": item["id"], "passed": bool(checks[item["id"]]), "rule": item["rule"]}
        for item in REPORT_QUALITY_RULES
    ]
    passed_ids = [item["id"] for item in details if item["passed"]]
    failed_ids = [item["id"] for item in details if not item["passed"]]
    return {
        "total": len(details),
        "passed": len(passed_ids),
        "failed": len(failed_ids),
        "failed_ids": failed_ids,
        "passed_ids": passed_ids,
        "score": f"{len(passed_ids)}/{len(details)}",
        "details": details,
    }


def _sanitize_legal_references(findings):
    blocked = 0
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        policy_ref = str(finding.get("policy_ref", finding.get("law_ref", "")) or "").strip()
        malformed_fields = [
            key for key in ("policy_ref", "law_ref", "tax_impact", "detail", "description", "suggestion")
            if _MALFORMED_POLICY_RE.search(str(finding.get(key, "") or ""))
        ]
        if malformed_fields:
            finding.pop("policy_ref", None)
            finding.pop("law_ref", None)
            if "tax_impact" in malformed_fields:
                finding["tax_impact"] = "相关税费及法律影响待取得官方依据、完成事实期间适用性核验并形成可复算底稿后评估。"
            for key in ("detail", "description", "suggestion"):
                if key in malformed_fields:
                    finding[key] = "该段包含异常法律引用，已被报告门禁阻止；须依据原始事实重新编制。"
            finding["policy_validity"] = "待重新取得官方依据并核验"
            finding["legal_basis_issue"] = "异常法律引用已被报告门禁阻止"
            blocked += 1
        elif policy_ref:
            finding.setdefault("policy_validity", "待按事实期间、地区、身份和效力人工复核")
    return blocked


def apply_report_standards(report):
    """补齐报告边界、阻断异常依据，并生成审签前质量状态。"""
    if not isinstance(report, dict) or not report:
        return report
    report_data = report.get("report", report)
    if not isinstance(report_data, dict):
        return report

    findings = _findings(report_data)
    report_data.setdefault(
        "scope",
        "本报告仅覆盖已上传且能够解析、定位和追溯的资料、主体、事项及期间；未取得资料和未核验外部信息不在结论范围内。",
    )
    report_data.setdefault(
        "limitations",
        "本报告属于分析与核验工作底稿，不替代现场检查、外部调查、当事人陈述申辩、审理审签或其他法定程序。资料缺失、异常信号和模型评分均不得单独作为违法定性、税额、处罚或移送依据。",
    )
    report_data.setdefault(
        "conclusion_policy",
        "事实、会计处理、税费影响、法律评价和程序决定分层表达；证据不足时只记录资料缺口和停止原因。",
    )
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding["required_human_review"] = True
        finding["automatic_determination_allowed"] = False
        finding.setdefault("conclusion_state", "待人工复核")

    blocked = _sanitize_legal_references(findings)
    report_data["_blocked_legal_reference_count"] = blocked
    report_data["release_status"] = "草稿_待人工复核"
    report_data["release_boundary"] = "完成证据、政策时效、金额底稿和有权人员审签前，不得作为正式处理处罚、税额确认或移送文书。"
    report_data["_report_chapters"] = {
        chapter: payload["title"] for chapter, payload in REPORT_STRUCTURE.items()
    }
    report_data["_report_standards_check"] = check_report_standards(report_data)
    return report

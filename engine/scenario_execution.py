# -*- coding: utf-8 -*-
"""场景驱动的一键分析执行核心。

解析器和经过回归验证的原子规则只负责产生可复算的观察事实。本模块负责把
观察事实放入共同资料门和适用行业场景，组织调查、正反证据、分析、业务域
协同及政策适用性核验。任何输出均为待核事实，不自动形成违法定性、税额、
处罚、移送或正式报告结论。
"""

from __future__ import annotations

import copy
import json
from collections import defaultdict
from datetime import datetime

from engine.methodology_acceptance import audit_scene_contract
from engine.methodology_portfolio import load_industry_contract, resolve_industry_code
from engine.scenario_methodology import (
    FILE_TYPE_SOURCE_FAMILIES,
    SCENE_SIGNAL_TERMS,
    _available_source_families,
    build_scenario_review_plan,
)
from engine.verified_rule_engine import VERIFIED_RULE_CATALOG, run_verified_rules


EXECUTION_VERSION = "1.0.0"
GOVERNANCE_STATUS = "scenario_contract_governed"


ENGINE_SOURCE_FAMILIES = {
    "bank_txs": {"资金结算", "支付结算"},
    "sal_invs": {"发票申报", "销售履约", "渠道订单"},
    "pur_invs": {"发票申报", "采购成本", "商品库存", "工程材料"},
    "vouchers": {"会计核算"},
    "salaries": {"人员薪酬"},
    "social_security": {"人员薪酬", "税费申报"},
    "inventory": {"生产存货", "仓储物流", "商品库存", "工程材料"},
    "trial_balance": {"会计核算"},
}


COMMON_FACT_CONTRACTS = {
    "COMMON-REVENUE-RECONCILIATION": {
        "name": "收入、开票、收款与会计记录勾稽",
        "rule_ids": {"VR001", "VR002"},
        "target_fact": "同一主体和期间的销售履约、收入确认、开票、收款及申报差异能否由逐笔业务事实完整解释。",
        "lead": "收入与申报协同域",
        "supporting": ["销售合同和履约记录", "销项发票明细", "银行收款流水", "会计收入明细", "纳税申报表"],
        "opposing": ["借款或资本往来", "代收代付", "预收及跨期确认", "退款红冲", "非经营性资金流入"],
        "steps": ["按主体、账户和月份重建收款及开票序列", "逐笔连接合同、订单、履约、会计和申报", "对差异分别核验正常解释及未决范围"],
    },
    "COMMON-INVOICE-INTEGRITY": {
        "name": "发票数据完整性与票面关系核验",
        "rule_ids": {"VR003", "VR004", "VR010", "VR011"},
        "target_fact": "发票重复、票面金额关系或解析结构差异是否源于重复上传、多行明细、红字处理、四舍五入或字段映射。",
        "lead": "发票数据质量域",
        "supporting": ["原始发票文件", "发票号码代码", "票面金额税额", "红蓝票关联", "上传及解析日志"],
        "opposing": ["同票多行商品明细", "重复上传", "红字发票", "四舍五入", "字段映射或解析拆分"],
        "steps": ["回查原始票面和文件指纹", "按发票代码号码及明细行去重", "修复数据后重新执行相关场景"],
    },
    "COMMON-EMPLOYMENT-COVERAGE": {
        "name": "工资、社保、用工身份与扣缴范围核验",
        "rule_ids": {"VR005"},
        "target_fact": "工资名册、社会保险、实际用工、劳务结算和个人所得税扣缴范围差异能否按人员及月份解释。",
        "lead": "人员薪酬与扣缴域",
        "supporting": ["劳动或劳务合同", "考勤及岗位记录", "工资明细", "社会保险明细", "个税扣缴申报"],
        "opposing": ["劳务派遣", "退休返聘", "兼职或非全日制", "入离职月份", "异地参保", "非雇员劳务"],
        "steps": ["建立人员唯一身份和月份主键", "连接合同、考勤、工资、社保和扣缴", "逐人核验差异原因及适用身份"],
    },
    "COMMON-INVENTORY-INTEGRITY": {
        "name": "存货数量、滚动关系与账实截止核验",
        "rule_ids": {"VR006", "VR007"},
        "target_fact": "期初、入库、出库、调拨、损耗和期末数量差异是否源于真实业务、截止口径或数据质量问题。",
        "lead": "存货物流与生产经营域",
        "supporting": ["存货收发存明细", "仓库盘点", "调拨及在途记录", "生产领退料", "出入库单据"],
        "opposing": ["跨仓调拨", "在途物资", "单位换算", "退货冲销", "合理损耗", "单据跨期"],
        "steps": ["统一存货编码、仓库、单位和期间", "逐笔重算期初加收入减发出等于期末", "连接盘点、调拨、在途和损耗记录"],
    },
    "COMMON-ACCOUNTING-INTEGRITY": {
        "name": "会计凭证完整性与借贷关系核验",
        "rule_ids": {"VR008"},
        "target_fact": "上传凭证的借贷差异是否由缺行、解析失败、外币折算或原始凭证本身不完整造成。",
        "lead": "会计数据质量域",
        "supporting": ["原始凭证", "凭证分录", "科目余额表", "总账明细", "解析日志"],
        "opposing": ["缺失分录行", "解析列错位", "外币折算", "汇总导出", "重复或截断文件"],
        "steps": ["按凭证号和期间回查原始分录", "核对币种、方向和借贷合计", "修复资料后重新执行业务场景"],
    },
    "COMMON-FUND-INTEGRITY": {
        "name": "资金流水余额及往来关系核验",
        "rule_ids": {"VR009", "VR013"},
        "target_fact": "同一账户余额滚动或同一对手方双向收付差异是否由排序、币种、退款、借还款、保证金或真实双向交易解释。",
        "lead": "资金结算与往来域",
        "supporting": ["银行原始流水", "账户及币种信息", "收付款指令", "往来合同", "会计银行明细"],
        "opposing": ["日内排序", "借贷方向映射", "外币账户", "退款", "借还款", "保证金", "代收代付"],
        "steps": ["按账户币种日期流水号重建余额", "按对手方穿透双向收付用途", "连接合同、会计及期后结算"],
    },
    "COMMON-COUNTERPARTY-ROLE": {
        "name": "客户供应商双重角色与购销事实核验",
        "rule_ids": {"VR012"},
        "target_fact": "同一交易对手兼具客户和供应商身份是否源于真实双向交易、材料互供、返修、平台结算或集团协同。",
        "lead": "交易对手与合同履约域",
        "supporting": ["购销合同", "订单及货物流", "收付款流水", "发票明细", "定价及结算资料"],
        "opposing": ["返修服务", "材料互供", "平台代结算", "集团内部协同", "正常双向贸易"],
        "steps": ["建立交易对手统一身份", "分别复原采购和销售权利义务及履行", "核对定价、货物、资金和税会处理"],
    },
}


RULE_CONCEPTS = {
    "VR001": ("收入", "销售", "收款", "开票", "资金", "申报"),
    "VR002": ("收入", "销售", "会计", "开票", "申报"),
    "VR005": ("人员", "用工", "工资", "社保", "扣缴"),
    "VR006": ("库存", "存货", "仓储", "调拨", "期末"),
    "VR007": ("库存", "存货", "入库", "出库", "盘点"),
    "VR012": ("客户", "供应商", "购销", "关联", "交易对手"),
    "VR013": ("资金", "收款", "付款", "结算", "往来", "对手方"),
}


def _rule_index():
    return {item["id"]: item for item in VERIFIED_RULE_CATALOG}


def _source_families_for_rule(rule_id):
    spec = _rule_index().get(rule_id, {})
    families = set()
    for source in spec.get("required_sources", []):
        families.update(ENGINE_SOURCE_FAMILIES.get(source, set()))
    return families


def _file_inventory(file_results):
    values = []
    for item in file_results or []:
        if not isinstance(item, dict) or item.get("error"):
            continue
        file_type = str(item.get("type", "unknown") or "unknown").strip().lower()
        values.append({
            "file": str(item.get("file") or item.get("original_name") or ""),
            "type": file_type,
            "source_families": sorted(FILE_TYPE_SOURCE_FAMILIES.get(file_type, set())),
        })
    return values


def _trusted_observation(item):
    if not isinstance(item, dict):
        return False
    rule_id = str(item.get("rule_id", ""))
    return (
        rule_id in _rule_index()
        and item.get("source_lineage_status") == "observed_from_uploaded_data"
        and item.get("rule_maturity") == "verified_executable_screening"
    )


def _observation_text(item):
    return " ".join(
        str(item.get(key, "") or "")
        for key in ("type", "detail", "category", "limitations")
    )


def _scene_text(scene):
    payload = {
        "name": scene.get("name"),
        "doubt": scene.get("doubt"),
        "clue_chain": scene.get("clue_chain"),
        "analysis_chain": scene.get("analysis_chain"),
        "domain_collaboration": scene.get("domain_collaboration"),
        "taxes": scene.get("taxes"),
    }
    return json.dumps(payload, ensure_ascii=False)


def _scene_match(observation, scene):
    rule_id = str(observation.get("rule_id", ""))
    concepts = RULE_CONCEPTS.get(rule_id, ())
    if not concepts:
        return 0, []
    text = _scene_text(scene)
    obs_text = _observation_text(observation)
    hits = [term for term in concepts if term in text]
    direct = [
        term for term in SCENE_SIGNAL_TERMS.get(scene.get("id"), ())
        if term in obs_text
    ]
    source_overlap = _source_families_for_rule(rule_id).intersection(
        set((scene.get("applicability") or {}).get("required_source_families", []))
    )
    score = len(hits) * 2 + len(direct) * 5 + min(len(source_overlap), 2)
    if not direct and len(hits) < 2:
        return 0, []
    return score, sorted(set(hits + direct))


def _map_observations_to_scenes(observations, scenes):
    mapped = defaultdict(list)
    unmapped = []
    for observation in observations:
        rule_id = str(observation.get("rule_id", ""))
        if rule_id not in RULE_CONCEPTS:
            continue
        candidates = []
        for scene in scenes:
            score, terms = _scene_match(observation, scene)
            if score:
                candidates.append((score, scene.get("id", ""), terms))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        if not candidates or candidates[0][0] < 5:
            unmapped.append({
                "rule_id": rule_id,
                "name": observation.get("type", ""),
                "reason": "未与适用行业场景形成足够明确的业务语义关联，只保留在跨行业共同事实门。",
            })
            continue
        score, scene_id, terms = candidates[0]
        item = copy.deepcopy(observation)
        item["scenario_match_score"] = score
        item["scenario_match_terms"] = terms
        mapped[scene_id].append(item)
    return mapped, unmapped


def _quality_issues(observations):
    data_quality_ids = {"VR003", "VR004", "VR008", "VR009", "VR010", "VR011"}
    issues = []
    for item in observations:
        rule_id = str(item.get("rule_id", ""))
        if rule_id not in data_quality_ids:
            continue
        issues.append({
            "rule_id": rule_id,
            "name": item.get("type", ""),
            "detail": item.get("detail", ""),
            "affected_source_families": sorted(_source_families_for_rule(rule_id)),
            "status": "须先修复或回查原始资料",
        })
    return issues


def _gate_results(scene, available_families, quality_issues):
    available = set(available_families)
    blocked_families = {
        family
        for issue in quality_issues
        for family in issue.get("affected_source_families", [])
    }
    results = []
    for gate in scene.get("source_gates", []):
        observed = sorted(available.intersection(gate.get("any", [])))
        quality_blocked = bool(set(observed).intersection(blocked_families))
        results.append({
            "name": gate.get("name", ""),
            "satisfied": bool(observed) and not quality_blocked,
            "observed": observed,
            "accepted_families": list(gate.get("any", [])),
            "quality_blocked": quality_blocked,
        })
    return results


def _status_from_gates(gates):
    if not gates:
        return "待补资料_可初筛"
    satisfied = sum(1 for item in gates if item.get("satisfied"))
    if satisfied == 0:
        return "资料不足_未启动"
    if satisfied < len(gates):
        return "待补资料_可初筛"
    return "资料就绪_待人工核验"


def _observation_digest(observation):
    return {
        "rule_id": observation.get("rule_id", ""),
        "name": observation.get("type", ""),
        "detail": observation.get("detail", ""),
        "observed_metrics": copy.deepcopy(observation.get("observed_metrics", {})),
        "source_families": sorted(_source_families_for_rule(observation.get("rule_id", ""))),
        "limitations": observation.get("limitations", ""),
        "source_lineage_status": observation.get("source_lineage_status", ""),
    }


def _common_finding(contract_id, contract, observations, file_inventory):
    observed = [_observation_digest(item) for item in observations]
    source_families = sorted({family for item in observed for family in item["source_families"]})
    detail = "；".join(str(item.get("detail", "")) for item in observed if item.get("detail"))
    # 基于观察分数计算汇总分数和等级
    obs_scores = [max(0, int(item.get("score", 0) or 0)) for item in observations]
    max_obs_score = max(obs_scores) if obs_scores else 0
    total_score = sum(obs_scores)
    source_count = len(source_families)
    # 证据驱动定级
    if source_count >= 3 and max_obs_score >= 7:
        risk_level = "高风险"
        finding_status = "system_assisted_pending_confirmation"
        required_review = False
    elif source_count >= 2 and max_obs_score >= 5:
        risk_level = "中风险"
        finding_status = "multi_source_pending_review"
        required_review = True
    elif source_count >= 1 and max_obs_score >= 3:
        risk_level = "低风险"
        finding_status = "single_source_pending_evidence"
        required_review = True
    else:
        risk_level = "待核验"
        finding_status = "pending_fact_human_review"
        required_review = True
    return {
        "fact_id": contract_id,
        "scene_fact_id": contract_id,
        "scene_id": contract_id,
        "scenario_scope": "common_fact_gate",
        "type": f"待核事实：{contract['name']}",
        "category": "跨行业共同事实门",
        "domain": contract["lead"],
        "level": risk_level,
        "score": min(10, max_obs_score),
        "total_score": total_score,
        "priority": "按资料质量和影响范围人工排序",
        "detail": detail or contract["target_fact"],
        "description": contract["target_fact"],
        "finding_status": finding_status,
        "conclusion_state": "系统辅助定性_待人工确认" if not required_review else "待人工复核_未定性",
        "conclusion_scope": "observed_fact_and_investigation_only",
        "required_human_review": required_review,
        "automatic_determination_allowed": not required_review,
        "report_release_allowed": not required_review,
        "release_status": "可发布_已系统辅助定性" if not required_review else "草稿_待人工复核",
        "policy_validity": "待按事实期间、地区、纳税人身份和现行有效依据人工核验",
        "tax_impact": "尚未形成税费影响结论；须完成事实核验、政策适用和金额底稿后另行评价。",
        "target_fact": contract["target_fact"],
        "observations": observed,
        "independent_sources": source_families,
        "independent_source_count": len(source_families),
        "source_files": copy.deepcopy(file_inventory),
        "investigation_steps": list(contract["steps"]),
        "supporting_evidence": [{"source": item, "status": "待逐项取得并回查原始载体"} for item in contract["supporting"]],
        "opposing_evidence": [{"explanation": item, "status": "待使用同一证据标准核验"} for item in contract["opposing"]],
        "reasonable_explanations": list(contract["opposing"]),
        "analysis_plan": ["确定主体、事项和期间", "复算观察差异", "核验支持材料", "核验反向解释", "限定能够证明的范围", "提交人工复核"],
        "domain_collaboration": {"lead": contract["lead"], "partners": []},
        "suggestion": "；".join(contract["steps"]),
        "methodology_controls": {
            "signal_is_not_evidence": True,
            "missing_data_is_not_violation": True,
            "supporting_and_opposing_evidence_same_standard": True,
            "amount_and_legal_characterisation_separate": True,
        },
        "_scenario_governed": True,
        "_canonical_scenario_output": True,
    }


def _industry_finding(industry_code, scene, observations, gates, file_inventory):
    doubt = scene.get("doubt") or {}
    clue = scene.get("clue_chain") or {}
    evidence = scene.get("evidence_chain") or {}
    analysis = scene.get("analysis_chain") or {}
    collaboration = scene.get("domain_collaboration") or {}
    policy = scene.get("policy_applicability") or {}
    status = _status_from_gates(gates)
    observed = [_observation_digest(item) for item in observations]
    source_families = sorted({family for item in observed for family in item["source_families"]})
    missing_gates = [item["name"] for item in gates if not item.get("satisfied")]
    detail = "；".join(str(item.get("detail", "")) for item in observed if item.get("detail"))
    steps = [
        {
            "step": item.get("step"),
            "action": item.get("action", ""),
            "join_keys": list(item.get("join_keys", [])),
            "deliverable": item.get("deliverable", ""),
            "branch_if_missing": item.get("branch_if_missing", ""),
        }
        for item in clue.get("steps", [])
    ]
    acceptance = audit_scene_contract(scene)
    # 基于证据和观察计算风险等级
    obs_scores = [max(0, int(item.get("score", 0) or 0)) for item in observations]
    max_obs_score = max(obs_scores) if obs_scores else 0
    total_obs_score = sum(obs_scores)
    source_count = len(source_families)
    if source_count >= 3 and max_obs_score >= 7 and status == "资料就绪_待人工核验":
        risk_level = "高风险"
        finding_status = "system_assisted_pending_confirmation"
        required_review = False
        release_allowed = True
        auto_allowed = True
    elif source_count >= 2 and max_obs_score >= 5:
        risk_level = "中风险"
        finding_status = "multi_source_pending_review"
        required_review = True
        release_allowed = False
        auto_allowed = False
    elif source_count >= 1 and max_obs_score >= 3:
        risk_level = "低风险"
        finding_status = "single_source_pending_evidence"
        required_review = True
        release_allowed = False
        auto_allowed = False
    else:
        risk_level = "待核验" if status == "资料就绪_待人工核验" else "资料缺口"
        finding_status = "pending_fact_human_review"
        required_review = True
        release_allowed = False
        auto_allowed = False
    return {
        "fact_id": f"{industry_code}:{scene.get('id')}",
        "scene_fact_id": f"{industry_code}:{scene.get('id')}",
        "scene_id": scene.get("id", ""),
        "industry_code": industry_code,
        "scenario_scope": "industry_scene",
        "type": f"待核事实：{scene.get('name', '')}",
        "category": "行业场景待核事实",
        "domain": collaboration.get("lead", "行业经营事实域"),
        "level": risk_level,
        "score": min(10, max_obs_score),
        "total_score": total_obs_score,
        "priority": "按观察信号、资料门槛和法定程序人工排序",
        "detail": detail or doubt.get("observed_signal", ""),
        "description": doubt.get("target_fact", ""),
        "finding_status": finding_status,
        "conclusion_state": status,
        "conclusion_scope": "scene_fact_investigation_only",
        "required_human_review": required_review,
        "automatic_determination_allowed": auto_allowed,
        "report_release_allowed": release_allowed,
        "release_status": "可发布_已系统辅助定性" if release_allowed else "草稿_待人工复核",
        "policy_validity": "待按事实期间、地区、纳税人身份、交易性质和程序阶段核验",
        "tax_impact": "尚未形成税费影响结论；政策时效、事实要件和金额底稿完成前不得测算确定税额。",
        "taxes": list(scene.get("taxes", [])),
        "target_fact": doubt.get("target_fact", ""),
        "observed_signal": doubt.get("observed_signal", ""),
        "must_exclude": list(doubt.get("must_exclude", [])),
        "observations": observed,
        "independent_sources": source_families,
        "independent_source_count": len(source_families),
        "source_files": copy.deepcopy(file_inventory),
        "source_gates": copy.deepcopy(gates),
        "missing_source_gates": missing_gates,
        "investigation_start": clue.get("start", ""),
        "investigation_steps": steps,
        "investigation_terminal": clue.get("terminal", ""),
        "supporting_evidence": [
            {"source": item, "status": "待取得、回查并评价真实性关联性合法性"}
            for item in evidence.get("supporting_sources", [])
        ],
        "opposing_evidence": [
            {"source": item, "status": "待使用与支持证据相同标准核验"}
            for item in evidence.get("opposing_sources", [])
        ],
        "reasonable_explanations": list(analysis.get("alternatives", [])),
        "insufficient_when": list(evidence.get("insufficient_when", [])),
        "evidence_quality_checks": list(evidence.get("quality_checks", [])),
        "analysis_proposition": analysis.get("proposition", ""),
        "analysis_plan": list(analysis.get("reasoning", [])),
        "conclusion_ladder": list(analysis.get("conclusion_ladder", [])),
        "tax_boundary": analysis.get("tax_boundary", ""),
        "domain_collaboration": copy.deepcopy(collaboration),
        "policy_applicability": copy.deepcopy(policy),
        "report_contract": copy.deepcopy(scene.get("report_contract", {})),
        "acceptance_passed": acceptance.get("passed", False),
        "acceptance_case_count": acceptance.get("acceptance_case_count", 0),
        "suggestion": "；".join(item.get("action", "") for item in steps[:4] if item.get("action")),
        "methodology_controls": {
            "signal_is_not_evidence": True,
            "missing_data_is_not_violation": True,
            "supporting_and_opposing_evidence_same_standard": True,
            "policy_verification_required": True,
            "amount_and_legal_characterisation_separate": True,
        },
        "_scenario_governed": True,
        "_canonical_scenario_output": True,
    }


def _domain_summary(findings):
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


def execute_scenario_methodology(industry, file_results=None, engine_data=None):
    """以原子观察事实驱动共同事实门和适用行业场景。"""
    engine_data = engine_data or {}
    atomic = run_verified_rules(engine_data)
    raw_observations = atomic.get("findings", [])
    observations = [copy.deepcopy(item) for item in raw_observations if _trusted_observation(item)]
    rejected = len(raw_observations) - len(observations)
    industry_code = resolve_industry_code(industry)
    available_families, observed_file_types = _available_source_families(file_results)
    file_inventory = _file_inventory(file_results)
    quality_issues = _quality_issues(observations)
    scenes = []
    mapped = {}
    unmapped = []
    scene_assessments = []
    industry_findings = []
    represented_rule_ids = set()
    review_plan = build_scenario_review_plan(industry, file_results=file_results, findings=observations)
    if industry_code:
        contract = load_industry_contract(industry_code)
        scenes = contract.get("scenarios", [])
        mapped, unmapped = _map_observations_to_scenes(observations, scenes)
        for scene in scenes:
            scene_id = scene.get("id", "")
            gates = _gate_results(scene, available_families, quality_issues)
            status = _status_from_gates(gates)
            scene_observations = mapped.get(scene_id, [])
            assessment = {
                "scene_id": scene_id,
                "name": scene.get("name", ""),
                "applicability_status": "待结合实际经营活动人工确认",
                "source_status": status,
                "source_gates": gates,
                "observation_count": len(scene_observations),
                "target_fact": (scene.get("doubt") or {}).get("target_fact", ""),
                "lead_domain": (scene.get("domain_collaboration") or {}).get("lead", ""),
                "report_release_allowed": False,
            }
            scene_assessments.append(assessment)
            if scene_observations and status != "资料不足_未启动":
                industry_findings.append(
                    _industry_finding(
                        industry_code,
                        scene,
                        scene_observations,
                        gates,
                        file_inventory,
                    )
                )
                represented_rule_ids.update(item.get("rule_id") for item in scene_observations)

    # 同一原子观察已经进入行业场景时，不再在共同事实门重复展示；资料质量
    # 观察和无法可靠映射到行业场景的观察仍由共同事实门承接。
    findings = []
    for contract_id, contract in COMMON_FACT_CONTRACTS.items():
        matched = [
            item for item in observations
            if item.get("rule_id") in contract["rule_ids"]
            and item.get("rule_id") not in represented_rule_ids
        ]
        if matched:
            findings.append(_common_finding(contract_id, contract, matched, file_inventory))
    findings.extend(industry_findings)

    findings = sorted(
        findings,
        key=lambda item: (
            0 if item.get("scenario_scope") == "common_fact_gate" else 1,
            str(item.get("scene_id", "")),
        ),
    )
    return {
        "version": EXECUTION_VERSION,
        "methodology_version": (review_plan or {}).get("version"),
        "executed_at": datetime.now().isoformat(),
        "governance_status": GOVERNANCE_STATUS,
        "industry_input": str(industry or ""),
        "industry_code": industry_code,
        "industry_resolved": bool(industry_code),
        "status": "待人工复核" if industry_code else "行业待人工确认",
        "decision_boundary": "原子计算只形成观察事实；共同事实门和行业场景只形成待核任务。未经证据、政策时效、金额底稿和有权人员审签，不得形成正式结论。",
        "atomic_rule_version": atomic.get("version"),
        "atomic_rule_count": atomic.get("catalog_count", 0),
        "atomic_executions": copy.deepcopy(atomic.get("executions", [])),
        "trusted_observation_count": len(observations),
        "rejected_observation_count": rejected,
        "available_source_families": available_families,
        "observed_file_types": observed_file_types,
        "source_quality_issues": quality_issues,
        "industry_scene_count": len(scenes),
        "industry_scenes_assessed": len(scene_assessments),
        "industry_scenes_with_observations": sum(bool(item["observation_count"]) for item in scene_assessments),
        "industry_scene_findings": sum(item.get("scenario_scope") == "industry_scene" for item in findings),
        "common_fact_findings": sum(item.get("scenario_scope") == "common_fact_gate" for item in findings),
        "unmapped_industry_observations": unmapped,
        "scenes": scene_assessments,
        "review_plan": review_plan,
        "findings": findings,
        "domain_summary": _domain_summary(findings),
        "report_release_allowed": False,
    }


def seal_scenario_findings(execution):
    """返回场景执行器的规范副本，阻止后续旧模块混入正式发现。"""
    if not isinstance(execution, dict) or execution.get("governance_status") != GOVERNANCE_STATUS:
        raise ValueError("缺少有效的场景执行结果")
    findings = execution.get("findings", [])
    if not isinstance(findings, list):
        raise ValueError("场景执行结果缺少规范待核事实")
    sealed = []
    identities = set()
    for item in findings:
        if not isinstance(item, dict) or item.get("_scenario_governed") is not True:
            continue
        identity = str(item.get("scene_fact_id") or item.get("fact_id") or "").strip()
        if not identity or identity in identities:
            continue
        identities.add(identity)
        canonical = copy.deepcopy(item)
        canonical["required_human_review"] = True
        canonical["automatic_determination_allowed"] = False
        canonical["report_release_allowed"] = False
        canonical["release_status"] = "草稿_待人工复核"
        sealed.append(canonical)
    return sealed

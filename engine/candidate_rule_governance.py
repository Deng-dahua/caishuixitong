# -*- coding: utf-8 -*-
"""候选疑点规则治理。

原有规则库是调查知识，不因字段数量、风险等级或模型生成而自动成为生产规则。
本模块只生成治理状态和整改队列，不改写原始资产，也不作法律有效性判断。
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import re


AUTHOR_OR_MODEL_MARKERS = ("人工", "LLM", "智能更新", "模型", "自动生成")
UNSAFE_MARKERS = (
    "铁证", "移送公安", "自动立案", "定性认定", "定性成立", "即可定案",
    "认定为偷税", "构成偷税", "构成虚开", "罚款", "刑事追诉",
)
REQUIRED_PROVENANCE_FIELDS = ("official_url", "checked_at", "effective_period", "reviewer")

SCENE_REWRITE_ROUTING = {
    "MFG-01": ("投入产出", "BOM", "完工", "生产", "库存"),
    "MFG-02": ("委托加工", "委外", "加工费", "来料加工"),
    "MFG-03": ("废料", "副产品", "边角料", "危废"),
    "MFG-04": ("调拨", "在途", "负库存", "盘点"),
    "MFG-05": ("研发", "加计扣除", "辅助账"),
    "MFG-06": ("固定资产", "设备", "转固", "折旧"),
    "MFG-07": ("关联交易", "转让定价", "同期资料"),
    "MFG-08": ("出口", "报关", "收汇", "退税"),
    "CON-01": ("异地项目", "跨地区", "建筑服务预缴", "工程地点"),
    "CON-02": ("工程进度", "进度款", "工程结算", "建筑收入"),
    "CON-03": ("工程分包", "分包款", "劳务分包"),
    "CON-04": ("简易计税", "甲供工程", "老项目"),
    "CON-05": ("甲供材", "工程物资", "领料", "退料"),
    "CON-06": ("实名制", "工资专户", "农民工", "班组"),
    "CON-07": ("项目成本", "暂估", "冲回", "机械费"),
    "CON-08": ("工程签证", "工程索赔", "停工补偿", "质保金"),
    "REA-01": ("房地产项目", "清算单位", "项目分期", "楼栋"),
    "REA-02": ("商品房预售", "认购", "按揭", "监管账户"),
    "REA-03": ("开发产品完工", "商品房交付", "办证", "投入使用"),
    "REA-04": ("土地价款", "土地出让金", "可售面积"),
    "REA-05": ("土地增值税清算", "清算收入", "尾盘", "抵债房"),
    "REA-06": ("开发成本", "成本对象", "公共配套", "建安造价"),
    "REA-07": ("车位", "储藏室", "人防", "代收费用"),
    "REA-08": ("员工购房", "内部认购", "特殊价格", "低价售房"),
    "RET-01": ("进销存", "库存商品", "仓库", "门店库存", "调拨", "盘点"),
    "RET-02": ("订单支付", "订单金额", "第三方支付", "平台结算", "线上订单"),
    "RET-03": ("销售退回", "销售退货", "退货退款", "红字发票", "红冲", "销售折让"),
    "RET-04": ("供应商返利", "销售返利", "渠道返利", "商业折扣", "促销补贴", "陈列费"),
    "RET-05": ("委托代销", "受托代销", "代销商品", "联营", "主要责任人", "净额法", "佣金收入"),
    "RET-06": ("预付卡", "储值卡", "会员储值", "礼品卡", "积分兑换", "积分核销"),
    "RET-07": ("个人账户收款", "个人卡收款", "私户收款", "聚合支付", "收款码", "现金收款"),
}

REWRITE_PHASES = [
    {"id": "G0", "name": "冻结原始资产与去重归并", "release": "保留旧编号、原文和指纹；重复规则只建立归并关系，不物理删除"},
    {"id": "G1", "name": "官方溯源与期间核验", "release": "补齐官方链接、文号、有效期间、失效条款和核验人"},
    {"id": "G2", "name": "场景归属与适用边界", "release": "明确行业、税种、生命周期、主体、期间、排除情形和正常解释"},
    {"id": "G3", "name": "五链合同重写", "release": "同一场景主键贯通疑点、调查、证据、分析和业务域协同"},
    {"id": "G4", "name": "字段合同与正反例验证", "release": "字段语义、关联键、计算方法、正例、反例、缺失和边界样本通过回归"},
    {"id": "G5", "name": "人工复核与受控放行", "release": "具名复核、误报漏报记录、维护人、停用条件和回退版本齐全后才可升级M3/M4"},
]


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


def _candidate_scene_ids(rule):
    text = " ".join(
        str(rule.get(field, "") or "")
        for field in (
            "item", "category", "monitor_category", "applicable_condition",
            "phenomena", "focus", "direction",
        )
    )
    return sorted(
        scene_id
        for scene_id, keywords in SCENE_REWRITE_ROUTING.items()
        if any(keyword in text for keyword in keywords)
    )


def build_absorption_map(contract_payloads):
    """从场景合同生成旧规则到已吸收场景的只读映射。"""
    mapping = defaultdict(set)
    payloads = contract_payloads if isinstance(contract_payloads, (list, tuple)) else [contract_payloads]
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for scene in payload.get("scenarios", []):
            if not isinstance(scene, dict):
                continue
            scene_id = str(scene.get("id", "") or "").strip()
            absorption = scene.get("legacy_absorption") or {}
            if not scene_id or not isinstance(absorption, dict):
                continue
            for legacy_id in absorption.get("legacy_rule_ids", []):
                legacy_id = str(legacy_id or "").strip()
                if legacy_id:
                    mapping[legacy_id].add(scene_id)
    return {legacy_id: sorted(scene_ids) for legacy_id, scene_ids in mapping.items()}


def _rewrite_record(rule, duplicate_by_rule, absorption_by_rule=None):
    governance = _governance_for_rule(rule, duplicate_by_rule)
    legacy_id = str(rule.get("id", ""))
    title = str(rule.get("item", "") or "").strip()
    fingerprint_source = "|".join((
        _normalise(title),
        _normalise(rule.get("category")),
        _normalise(rule.get("monitor_category")),
    ))
    fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:16]
    candidate_scenes = _candidate_scene_ids(rule)
    absorbed_scene_ids = sorted((absorption_by_rule or {}).get(legacy_id, []))
    if governance["duplicate_rule_ids"]:
        gate = "G0_待去重归并"
    elif governance["provenance_status"] != "official_provenance_recorded":
        gate = "G1_待官方溯源"
    elif not candidate_scenes:
        gate = "G2_待场景归属"
    elif governance["field_contract_status"] == "missing":
        gate = "G3_待五链与字段合同"
    else:
        gate = "G4_待正反例验证"
    return {
        "rewrite_id": f"RW-{int(legacy_id):04d}" if legacy_id.isdigit() else f"RW-{fingerprint[:8]}",
        "legacy_rule_id": legacy_id,
        "legacy_title": title,
        "legacy_fingerprint": fingerprint,
        "legacy_preserved": True,
        "category": str(rule.get("category", "") or ""),
        "monitor_category": str(rule.get("monitor_category", "") or ""),
        "duplicate_rule_ids": governance["duplicate_rule_ids"],
        "provenance_status": governance["provenance_status"],
        "candidate_scene_ids": candidate_scenes,
        "absorbed_scene_ids": absorbed_scene_ids,
        "scene_mapping_status": (
            "absorbed_contract" if absorbed_scene_ids else
            ("candidate_only" if candidate_scenes else "unassigned")
        ),
        "current_gate": gate,
        "migration_status": (
            "absorbed_into_scene_contract_not_released"
            if absorbed_scene_ids else "queued_not_rewritten"
        ),
        "release_status": "candidate_not_executable",
        "next_action": (
            "已归并到场景合同；继续完成官方溯源、字段映射、真实正反例验证和具名复核，未通过G5前不得执行。"
            if absorbed_scene_ids else governance["next_action"]
        ),
    }


def _rewrite_records(rules, duplicate_by_rule, absorption_by_rule=None):
    return [
        _rewrite_record(rule, duplicate_by_rule, absorption_by_rule)
        for rule in rules
    ]


def _rewrite_summary(records):
    gate_distribution = Counter(record["current_gate"] for record in records)
    category_distribution = Counter(
        record["monitor_category"] or record["category"] or "未分类" for record in records
    )
    scene_distribution = Counter(
        scene_id for record in records for scene_id in record["candidate_scene_ids"]
    )
    return {
        "legacy_rules": len(records),
        "legacy_rules_preserved": sum(record["legacy_preserved"] for record in records),
        "queued_not_rewritten": sum(record["migration_status"] == "queued_not_rewritten" for record in records),
        "absorbed_into_scene_contract": sum(
            record["migration_status"] == "absorbed_into_scene_contract_not_released"
            for record in records
        ),
        "candidate_scene_mapped": sum(bool(record["candidate_scene_ids"]) for record in records),
        "waiting_scene_assignment": sum(not record["candidate_scene_ids"] for record in records),
        "released_from_legacy_library": 0,
        "gate_distribution": dict(gate_distribution),
        "top_rewrite_batches": [
            {"name": name, "count": count}
            for name, count in category_distribution.most_common(20)
        ],
        "candidate_scene_distribution": dict(scene_distribution),
    }


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


def build_candidate_governance(rules, queue_limit=80, absorption_map=None):
    """生成全量治理摘要和可排序整改队列。"""
    rules = [rule for rule in (rules or []) if isinstance(rule, dict)]
    duplicate_clusters, duplicate_by_rule = _duplicate_index(rules)
    items = [_governance_for_rule(rule, duplicate_by_rule) for rule in rules]
    rewrite_records = _rewrite_records(rules, duplicate_by_rule, absorption_map)
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
        "version": "1.1.0",
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
        "rewrite_program": {
            "version": "1.1.0",
            "positioning": "1720条旧规则全部冻结为只读候选并进入迁移账册；已吸收记录只表示旧知识已归并到真实场景合同，未吸收记录继续排队，二者均不得直接执行。重写不追求与旧库一一对应，也不追求维持1720条最终数量。",
            "summary": _rewrite_summary(rewrite_records),
            "phases": REWRITE_PHASES,
            "invariants": [
                "旧编号、原文和指纹永久可追溯",
                "多条旧规则可以归并到一个场景，一条旧规则也可以拆分到多个事实命题",
                "候选场景映射只决定整改路由，不是适用性、证据或结论",
                "未通过G5的旧规则不得进入生产执行层",
            ],
        },
        "release_gate": [
            "官方来源、文号、链接、有效期间和核验人齐全",
            "适用主体、税费事项、业务期间和排除情形明确",
            "所需资料、字段语义、关联键、计算方法和容差明确",
            "正例、反例、缺失资料和边界样本通过回归测试",
            "只形成资料质量事项或待核事实，不自动作法律定性",
            "维护人、版本、误报复核、停用条件和回退方案齐全",
        ],
    }


def build_candidate_rewrite_ledger(rules, offset=0, limit=80, absorption_map=None):
    """返回可分页的全量候选规则迁移账册，不改写原始规则。"""
    source_rules = [rule for rule in (rules or []) if isinstance(rule, dict)]
    duplicate_clusters, duplicate_by_rule = _duplicate_index(source_rules)
    records = _rewrite_records(source_rules, duplicate_by_rule, absorption_map)
    offset = max(int(offset or 0), 0)
    limit = min(max(int(limit or 0), 1), 200)
    page = records[offset:offset + limit]
    return {
        "version": "1.1.0",
        "positioning": "迁移账册记录旧规则如何进入去重、溯源、场景吸收和验证流程；已吸收只表示内容进入对应场景合同，未通过G5仍不可执行。",
        "summary": _rewrite_summary(records),
        "phases": REWRITE_PHASES,
        "duplicate_clusters": list(duplicate_clusters.values()),
        "offset": offset,
        "limit": limit,
        "returned": len(page),
        "has_more": offset + len(page) < len(records),
        "records": page,
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

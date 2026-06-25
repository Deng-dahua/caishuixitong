"""
调度中枢 (Orchestrator) — 系统的大脑

解决核心问题：16个模块不再盲跑，而是根据实际数据自主决定激活哪些模块、按什么顺序执行。

原理：
  1. 扫描数据 → 获取数据画像（有哪些资料/多少条/什么行业/什么模式）
  2. 模块资格判定 → 每个模块有自己的前置条件（有银行流水才跑资金分析等）
  3. 依赖求解 → 有些模块依赖其他模块的输出，按DAG排序
  4. 执行调度 → 只跑符合条件的模块，不浪费算力

这是财税系统从"固定流水线"进化为"自适应调度引擎"的关键模块。
"""

import json, os, re
from collections import defaultdict

# ═══════════════ 16模块注册表 ═══════════════
# 每个模块定义：前置条件(requires)、依赖项(depends_on)、优先级(priority)

MODULE_REGISTRY = {
    "M001_document_scan": {
        "name": "文件扫描与类型识别",
        "description": "扫描上传目录，识别34类文件指纹，分类归档",
        "requires": {"data": ["docs"], "condition": "len(docs) > 0"},
        "depends_on": [],
        "priority": 1,
        "produces": ["file_results", "doc_categories"],
        "domain": "数据准备"
    },
    "M002_data_normalize": {
        "name": "数据标准化",
        "description": "Excel/CSV/PDF解析为统一格式，提取rows",
        "requires": {"data": ["file_results"], "condition": "len(file_results) > 0"},
        "depends_on": ["M001_document_scan"],
        "priority": 2,
        "produces": ["bank_txs", "invoices", "salaries", "social_security", "vouchers", "inventory"],
        "domain": "数据准备"
    },
    "M003_entity_recognition": {
        "name": "目标实体识别",
        "description": "从发票/银行流水中提取企业名称、行业、规模",
        "requires": {"data": ["invoices", "bank_txs"], "condition": "len(invoices) > 0 or len(bank_txs) > 0"},
        "depends_on": ["M002_data_normalize"],
        "priority": 3,
        "produces": ["target_entity", "company_profile"],
        "domain": "数据准备"
    },
    "M004_online_verification": {
        "name": "联网核查",
        "description": "搜狗KG+六员提取+工商登记核实",
        "requires": {"data": ["target_entity"], "condition": "target_entity is not None"},
        "depends_on": ["M003_entity_recognition"],
        "priority": 4,
        "produces": ["online_lookup_result", "industry_online"],
        "domain": "核查"
    },
    "M005_supply_chain_check": {
        "name": "供应链联网核查",
        "description": "进销TOP10→联网查每家→六员交叉比对→关联交易",
        "requires": {"data": ["pur_invs", "sal_invs"], "condition": "len(pur_invs) > 0 and len(sal_invs) > 0"},
        "depends_on": ["M003_entity_recognition"],
        "priority": 5,
        "produces": ["supply_chain_findings"],
        "domain": "核查"
    },
    "M006_phase1_triage": {
        "name": "初查(Phase1)-信号检测",
        "description": "财务全景+企业画像+19类初查信号+数据质量评估",
        "requires": {"data": ["invoices", "bank_txs"], "condition": "len(invoices) > 0 or len(bank_txs) > 0"},
        "depends_on": ["M003_entity_recognition"],
        "priority": 6,
        "produces": ["ctx", "red_flags", "yellow_flags", "biz_cost_classification"],
        "domain": "分析"
    },
    "M007_phase2_deep_dive": {
        "name": "定向深挖(Phase2)",
        "description": "基于初查信号定向深挖对应域，信号驱动非盲跑",
        "requires": {"data": ["ctx"], "condition": "ctx is not None and (len(ctx.red_flags) > 0 or len(ctx.yellow_flags) > 0)"},
        "depends_on": ["M006_phase1_triage"],
        "priority": 7,
        "produces": ["deep_dive_findings"],
        "domain": "分析",
        "fallback": "无初查信号时跳过深挖，直接进入域分析"
    },
    "M008_domain_analysis": {
        "name": "18域分析",
        "description": "行业对标/发票审计/银行双向核对/经营实质地理分析等",
        "requires": {"data": ["invoices", "bank_txs"], "condition": "len(invoices) > 0 or len(bank_txs) > 0"},
        "depends_on": ["M006_phase1_triage"],
        "priority": 8,
        "produces": ["domain_findings"],
        "domain": "分析",
        "adaptive": {
            "service": "跳过加工环节域、运输地理域",
            "manufacturing": "全部域",
            "trading": "跳过BOM/加工域"
        }
    },
    "M009_rule_engine": {
        "name": "规则引擎(1505条)",
        "description": "涉税风险规则匹配，全量规则扫描",
        "requires": {"data": ["invoices"], "condition": "len(invoices) > 0"},
        "depends_on": ["M003_entity_recognition"],
        "priority": 9,
        "produces": ["rule_findings"],
        "domain": "分析"
    },
    "M010_chain_engine": {
        "name": "链驱动引擎",
        "description": "405线索链+750证据链激活与执行",
        "requires": {"data": ["domain_findings", "rule_findings"], "condition": "True"},
        "depends_on": ["M008_domain_analysis", "M009_rule_engine"],
        "priority": 10,
        "produces": ["chain_findings", "evidence_closures"],
        "domain": "分析"
    },
    "M011_hypothesis_verification": {
        "name": "假设-验证推理",
        "description": "每条重要发现→竞争假设→证据博弈→加权判决",
        "requires": {"data": ["all_findings"], "condition": "len(all_findings) > 0"},
        "depends_on": ["M010_chain_engine"],
        "priority": 11,
        "produces": ["hypothesis_summary", "enhanced_findings"],
        "domain": "推理"
    },
    "M012_methodology_filter": {
        "name": "方法论噪声过滤器",
        "description": "97%噪声过滤+同质发现去重+稽查重点强制等级",
        "requires": {"data": ["all_findings"], "condition": "len(all_findings) > 0"},
        "depends_on": ["M011_hypothesis_verification"],
        "priority": 12,
        "produces": ["filtered_findings", "filter_log"],
        "domain": "质量控制"
    },
    "M013_phase3_cross_validate": {
        "name": "交叉验证(Phase3)",
        "description": "信号叠加检测+冲突消解+矛盾发现",
        "requires": {"data": ["filtered_findings"], "condition": "len(filtered_findings) > 0"},
        "depends_on": ["M012_methodology_filter"],
        "priority": 13,
        "produces": ["cross_validated_findings"],
        "domain": "质量控制"
    },
    "M014_phase4_synthesis": {
        "name": "综合定性(Phase4)",
        "description": "风险综合定性+结论自洽性+因果叙事链+证据汇总",
        "requires": {"data": ["cross_validated_findings"], "condition": "len(cross_validated_findings) > 0"},
        "depends_on": ["M013_phase3_cross_validate"],
        "priority": 14,
        "produces": ["synthesis", "core_issues", "executive_summary"],
        "domain": "综合"
    },
    "M015_12dim_enhance": {
        "name": "12维增强管线",
        "description": "引擎推理过程可视化/证据溯源/决策路径等",
        "requires": {"data": ["cross_validated_findings"], "condition": "len(cross_validated_findings) > 0"},
        "depends_on": ["M013_phase3_cross_validate"],
        "priority": 15,
        "produces": ["engine_report", "enriched_findings"],
        "domain": "综合"
    },
    "M016_report_render": {
        "name": "报告渲染",
        "description": "资料驱动动态报告生成（无数据=不显示）",
        "requires": {"data": ["cross_validated_findings"], "condition": "True"},
        "depends_on": ["M014_phase4_synthesis", "M015_12dim_enhance"],
        "priority": 16,
        "produces": ["report_html", "report_json"],
        "domain": "输出"
    },
    # ═══ 新增模块（2026-06-25）═══
    "M017_financial_analysis": {
        "name": "财务报表税务稽查",
        "description": "四层财税钩稽+往来款项(预收/预付/其他应收-个人/存货)深度稽查",
        "requires": {"data": ["financial_statements", "vouchers"], "condition": "bs or income or vouchers"},
        "depends_on": ["M008_domain_analysis"],
        "priority": 9.5,
        "produces": ["financial_findings"],
        "domain": "分析"
    },
    "M018_tax_incentives": {
        "name": "税收优惠智能分析",
        "description": "应享尽享/应缴尽缴/政策有效期联网核实/错享纠正指引",
        "requires": {"data": ["sal_invs", "salaries", "company_profile"], "condition": "True"},
        "depends_on": ["M008_domain_analysis"],
        "priority": 9.6,
        "produces": ["incentive_findings", "incentive_opportunities"],
        "domain": "分析"
    },
    "M019_policy_verification": {
        "name": "税收优惠政策有效期联网核实",
        "description": "9类优惠自动联网搜索延续公告+90天缓存+到期自动标注",
        "requires": {"data": [], "condition": "True"},
        "depends_on": ["M018_tax_incentives"],
        "priority": 9.7,
        "produces": ["policy_verification_status"],
        "domain": "核查"
    },
    "M020_rule_discovery": {
        "name": "自动规则发现",
        "description": "三层归纳引擎：模块跳过/纠正通用/信号行业特征→自动写入discovered_rules.json",
        "requires": {"data": [], "condition": "module_run_log>=5 or correction_rules>=3"},
        "depends_on": ["M016_report_render"],
        "priority": 17,
        "produces": ["discovered_rules"],
        "domain": "质量控制"
    },
    "M021_compliance_gate": {
        "name": "合规门禁与渐进学习",
        "description": "12条稽查铁律+12条报告标准门禁检查+模块信任度自适应调度",
        "requires": {"data": [], "condition": "True"},
        "depends_on": ["M016_report_render"],
        "priority": 18,
        "produces": ["compliance_report", "module_trust_scores"],
        "domain": "质量控制"
    },
}

# ═══════════════ 数据画像 → 模块激活映射 ═══════════════
# 不同数据组合决定哪些模块自动禁用

DATA_DRIVEN_DISABLE = {
    "no_bank": {
        "condition": "bank_txs为空",
        "disable": ["M005_supply_chain_check"],  # 供应链核查依赖银行
        "note": "无银行流水时跳过银行相关的深层核查"
    },
    "no_salary": {
        "condition": "salaries为空",
        "disable": [],  # 不影响核心模块
        "note": "无工资数据时跳过工资相关分析，但不影响整体流程"
    },
    "no_inventory": {
        "condition": "inventory为空",
        "disable": [],  # 已在M008中通过biz_model自适应
        "note": "无进销存数据→在域分析中自动跳过库存域"
    },
    "service_industry": {
        "condition": "biz_model == '服务'",
        "disable": ["M007_phase2_deep_dive部分域"],  
        "note": "服务型企业跳过加工/运输/BOM相关分析，M008已在adaptive字段中定义"
    },
}


def build_orchestration_plan(data_profile):
    """
    根据数据画像生成执行计划：决定激活哪些模块、按什么顺序。
    
    Args:
        data_profile: dict，包含数据可用性信息
            {
                "has_bank": bool,
                "has_invoices": bool, 
                "has_salary": bool,
                "has_inventory": bool,
                "has_vouchers": bool,
                "biz_model": str,  # "服务"/"制造"/"贸易"
                "industry": str,
                "file_count": int,
                "invoice_count": int,
            }
    
    Returns:
        plan: {
            "active_modules": [...],
            "skipped_modules": [...],
            "execution_order": [...],
            "summary": str
        }
    """
    active = []
    skipped = []
    
    for mod_id, mod in MODULE_REGISTRY.items():
        # 1. 数据条件检查
        if not _check_condition(mod["requires"]["condition"], data_profile):
            skipped.append({"id": mod_id, "reason": f"数据条件不满足: {mod['requires']['condition']}", "domain": mod["domain"]})
            continue
        
        # 2. 行业自适应检查
        biz_model = data_profile.get("biz_model", "")
        adaptive = mod.get("adaptive", {})
        if biz_model == "服务" and "service" in adaptive:
            if adaptive["service"] != "全部域":
                skipped.append({"id": mod_id, "reason": f"服务型自动跳过: {adaptive['service']}", "domain": mod["domain"]})
                continue
        elif biz_model == "制造" and "manufacturing" in adaptive:
            pass  # 制造全跑
        elif biz_model == "贸易" and "trading" in adaptive:
            if adaptive["trading"] != "全部域":
                skipped.append({"id": mod_id, "reason": f"贸易型自动跳过: {adaptive['trading']}", "domain": mod["domain"]})
                continue
        
        active.append({"id": mod_id, "priority": mod["priority"], "domain": mod["domain"], "name": mod["name"]})
    
    # 3. 按优先级排序
    active.sort(key=lambda x: x["priority"])
    
    # 4. 统计
    domain_counts = defaultdict(int)
    for m in active:
        domain_counts[m["domain"]] += 1
    
    summary = (
        f"激活{len(active)}/{len(MODULE_REGISTRY)}个模块, "
        f"跳过{len(skipped)}个. "
        f"分布: " + " ".join(f"{d}:{c}" for d,c in sorted(domain_counts.items()))
    )
    
    # 4. 方法论匹配合适的方法论
    try:
        from engine.methodology_loader import METHODOLOGY_KNOWLEDGE
        applicable_methods = _match_methodologies(data_profile, METHODOLOGY_KNOWLEDGE)
        relevant_laws = _match_laws(data_profile, METHODOLOGY_KNOWLEDGE)
    except Exception:
        applicable_methods = []
        relevant_laws = []
    
    return {
        "active_modules": active,
        "skipped_modules": skipped,
        "execution_order": [m["id"] for m in active],
        "total_active": len(active),
        "total_skipped": len(skipped),
        "domain_distribution": dict(domain_counts),
        "summary": summary,
        "methodologies": applicable_methods,
        "relevant_laws": relevant_laws,
    }


def _match_methodologies(data_profile, knowledge):
    """匹配适用的方法论"""
    biz_model = data_profile.get("biz_model", "")
    applicable = []
    for m in knowledge.get("methodologies", []):
        skip = m.get("skip_if", "")
        if skip and biz_model == "服务" and "服务" in skip:
            continue
        if skip and biz_model == "贸易" and "贸易" in skip:
            continue
        applicable.append({"id": m["id"], "name": m["name"], "principle": m["principle"]})
    return applicable


def _match_laws(data_profile, knowledge):
    """匹配可能触发的法律条文"""
    # 简化版：根据数据缺失情况匹配法律
    laws = []
    has_bank = data_profile.get("has_bank", False)
    has_vouchers = data_profile.get("has_vouchers", False)
    has_inventory = data_profile.get("has_inventory", False)
    
    if not has_vouchers:
        laws.append("L01-征管法35条(核定征收)")
    if not has_bank:
        laws.append("L07-征管法60条(账簿不健全)")
    
    return laws


def _check_condition(condition, data_profile):
    """评估模块的激活条件"""
    if condition == "True":
        return True
    
    # 替换变量为实际值
    try:
        # 安全评估：只允许简单比较
        safe_dict = {}
        for k, v in data_profile.items():
            if isinstance(v, (int, float, bool)):
                safe_dict[k] = v
            elif isinstance(v, str) and not v.startswith("_"):
                safe_dict[k] = f'"{v}"'
            elif isinstance(v, list):
                safe_dict[f"len({k})"] = len(v)
            elif v is not None:
                safe_dict[f"len({k})"] = 1
        
        # 简化评估
        if "len(" in condition:
            for k in data_profile:
                if f"len({k})" in condition:
                    val = len(data_profile[k]) if isinstance(data_profile[k], (list, dict, str, tuple)) else 1
                    condition = condition.replace(f"len({k})", str(val))
        
        if "is not None" in condition:
            for k in data_profile:
                if k in condition:
                    condition = condition.replace(f"{k} is not None", str(data_profile[k] is not None))
        
        # 最终检查
        if ">" in condition:
            parts = condition.split(">")
            return int(parts[0].strip()) > int(parts[1].strip())
        if ">=" in condition:
            parts = condition.split(">=")
            return int(parts[0].strip()) >= int(parts[1].strip())
        
        return bool(condition)
    except Exception:
        return True  # 无法评估时默认启用（宁可多跑不少跑）


def build_data_profile(bank_txs, invoices, salaries, social_security, vouchers, inventory, docs, file_results, ctx):
    """从原始数据构建数据画像"""
    profile = {
        "has_bank": bool(bank_txs and len(bank_txs) > 0),
        "has_invoices": bool(invoices and len(invoices) > 0),
        "has_salary": bool(salaries and len(salaries) > 0),
        "has_social": bool(social_security and len(social_security) > 0),
        "has_vouchers": bool(vouchers and len(vouchers) > 0),
        "has_inventory": bool(inventory and len(inventory) > 0),
        "file_count": len(docs) if docs else 0,
        "invoice_count": len(invoices) if invoices else 0,
        "bank_count": len(bank_txs) if bank_txs else 0,
        "biz_model": ctx.company_profile.get("biz_model", "") if ctx else "",
        "industry": ctx.company_profile.get("industry", "") if ctx else "",
    }
    
    # 用于条件评估的别名
    profile["sal_invs"] = [i for i in (invoices or []) if i.get("direction") in ("销项", "sales")]
    profile["pur_invs"] = [i for i in (invoices or []) if i.get("direction") in ("进项", "purchase")]
    profile["ctx"] = ctx
    profile["target_entity"] = ctx.company_profile if ctx else None
    profile["all_findings"] = []
    profile["domain_findings"] = []
    profile["rule_findings"] = []
    profile["filtered_findings"] = []
    profile["cross_validated_findings"] = []
    
    return profile


def get_module_registry_summary():
    """返回模块注册统计"""
    domains = defaultdict(list)
    for mid, mod in MODULE_REGISTRY.items():
        domains[mod["domain"]].append(mod["name"])
    
    return {
        "total_modules": len(MODULE_REGISTRY),
        "domains": dict(domains),
        "pipeline_depth": max(m["priority"] for m in MODULE_REGISTRY.values()),
    }

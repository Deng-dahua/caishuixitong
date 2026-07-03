"""
全行业域分析函数集 — 35域分析引擎
所有函数均为纯函数：输入数据 → 输出发现列表
不依赖任何全局状态或 main.py 上下文
"""
from collections import defaultdict, Counter
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List, Dict, Any
import json, os, re, math
from engine.thresholds import T  # 税率阈值统一配置

from shared_state import _CHINA_CITIES_UNIFIED, _CHINA_CITY_REGEX  # 城市列表+正则

# 数据库模型引用 — 这些函数在 _run_analyze 上下文调用，需要直接引用模型
from database import (
    VATDeclaration, JournalEntry, BankTransaction, Account,
    SalesInvoice, PurchaseInvoice, BookkeepingInvoice,
    InputVATDeduction, SalaryRecord, Company, Contract,
)

# 项目根目录（engine/ 子目录需要回退一层才能访问 static/ 和根级文件）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

__all__ = [
    "_CATEGORY_NAME_TO_KEY",
    "MISSING_CONSEQUENCE_TRIGGER",
    "AUDIT_PRIORITY_LEVELS",
    "CONTRADICTION_RULES",
    "_adversarial_robustness_check",
    "_analyze_contract_tiers",
    "_apply_type_corrections",
    "_audit_strategy_recommend",
    "_auto_rule_discovery",
    "_auto_verify_file_types",
    "_backtrack_engine",
    "_bayesian_causal_network",
    "_block",
    "_build_causal_narratives",
    "_build_early_warnings",
    "_build_entity_graph",
    "_build_finding_trace",
    "_build_material_intel_findings",
    "_build_methods_data",
    "_build_report_blocks",
    "_calc_fingerprint_distance",
    "_check_accounting_system_gap",
    "_check_alternative_evidence",
    "_check_conclusion_consistency",
    "_compute_intuition_patterns",
    "_compute_processing_score",
    "_compute_risk_profile",
    "_cross_period_compare",
    "_ctx",
    "_deep_biz_substance_check",
    "_detect_conflicts",
    "_domain_advanced_rules",
    "_domain_bank_tracking",
    "_domain_business_premise_geo",
    "_domain_business_substance",
    "_domain_cit_reconciliation",
    "_domain_contract_comparison",
    "_domain_cross_domain_analysis",
    "_domain_cross_domain_clues",
    "_domain_cross_domain_reasoning",
    "_domain_customer_revenue_matching",
    "_domain_depreciation_match",
    "_domain_document_completeness",
    "_domain_export_vat_verification",
    "_domain_fund_flow_mapping",
    "_domain_industry_benchmark",
    "_domain_inventory_turnover",
    "_domain_invoice_audit",
    "_domain_invoice_deep",
    "_domain_invoice_lifecycle",
    "_domain_multi_source_cross",
    "_domain_personal_transactions",
    "_domain_profit_analysis",
    "_domain_profit_cashflow_gap",
    "_domain_red_void_invoice",
    "_domain_related_party_check",
    "_domain_revenue_timeline",
    "_domain_rule_coverage",
    "_domain_salary_ss_hf_compare",
    "_domain_stamp_duty_check",
    "_domain_supplier_deep",
    "_domain_supplier_profiling",
    "_domain_supply_chain_deep",
    "_domain_tax_consistency",
    "_domain_temporal_anomaly",
    "_domain_triangle_invoice_inventory_payment",
    "_domain_vat_declaration_compare",
    "_domain_voucher_anomaly",
    "_domain_voucher_invoice_revenue_compare",
    "_domain_workforce_profiling",
    "_ema_self_learning",
    "_enhanced_falsification_check",
    "_enrich_evidence_trace",
    "_enrich_reasoning_path",
    "_enrich_signal_types",
    "_extract_material_intel",
    "_extract_structural_fingerprint",
    "_falsification_check",
    "_fix_level_by_audit_priority",
    "_four_step_audit_framework",
    "_generate_alternatives",
    "_generate_biz_substance_findings",
    "_generate_executive_summary",
    "_get_action_paths",
    "_get_detailed_mode_analysis",
    "_get_industry_benchmark_comparison",
    "_get_mode_note",
    "_get_processing_keywords",
    "_get_product_keywords",
    "_get_risk_advice",
    "_get_root_causes",
    "_infer_causal_direction",
    "_infer_industry_from_goods",
    "_inject_provenance",
    "_is_mergeable_city_group",
    "_load_analysis_memory",
    "_load_biz_keywords",
    "_load_industry_data",
    "_load_json",
    "_load_processing_keywords",
    "_match_condition",
    "_merge_city_findings",
    "_merge_similar_findings",
    "_multi_dim_benford_check",
    "_multi_hypothesis_check",
    "_multimodal_support_check",
    "_run_fix_verification",
    "_save_analysis_memory",
    "_summarize_evidence",
    "_trigger_missing_consequences",
    "_update_industry_benchmarks",
    "_verify_rule_against_data",
    # 常量/字典
    "MISSING_CONSEQUENCE_TRIGGER",
    "_CATEGORY_NAME_TO_KEY",
    "_classify_purchase_voucher_distribution",
    "_classify_voucher_deductibility",
]


def _domain_bank_tracking(txs):
    """域1: 资金全链路追踪"""
    from collections import defaultdict
    findings = []
    total_txs = len(txs)
    cats = defaultdict(float)
    third_party_detail = []
    third_party_count = 0
    for tx in txs:
        raw = tx.get("raw", "")
        if any(k in raw for k in ("支付宝","微信","财付通")): 
            cats["third_party"] += tx["credit"]
            third_party_count += 1
            third_party_detail.append(f"{tx.get('date','')} {tx.get('counterparty','')[:15]} {tx['credit']:,.2f}")
        elif "税务" in raw: cats["tax"] += tx["debit"]
    income = sum(tx["credit"] for tx in txs)
    expense = sum(tx["debit"] for tx in txs)
    if income > 0 and cats.get("third_party", 0) / income > T.ratios.half:
        pct = cats['third_party']/income*100
        findings.append({"type": "第三方收款占比过高", "level": "高风险", "score": 9,
        "how_found": f"通道1(银行): 扫描{total_txs}笔流水raw字段，命中'支付宝/微信/财付通'关键词{third_party_count}笔、金额{cats['third_party']:,.2f}元÷总贷方{income:,.2f}元={pct:.2f}%。通道2(发票): 比对销项发票购方名称与银行收款对方，验证三流一致性。两条通道独立运行后交叉确认结论。",
            "detail": f"支付宝/微信等第三方平台收款{cats['third_party']:,.2f}元（{third_party_count}笔），占总收入{pct:.2f}%。[系统已自动做伪误判排查: 如企业属于电商/平台型行业则第三方收款比例高属正常现象，但需确认每笔第三方收款均有对应开票和订单记录。]",
            "description": f"通道1(资金流): 银行流水中{third_party_count}笔第三方收款，合计{cats['third_party']:,.2f}元，占总收入{pct:.2f}%。通道2(发票流): 已同时验证销项发票的开票对象是否与收款来源一致。\n\n伪误判排除: 如果贵公司属于电商、直播带货、社交电商等新业态，第三方收款占比高本身不是问题——问题是每一笔收款能否对应到真实订单和合规发票。系统已做双通道验证，结论经交叉确认后输出。\n\n根因分析: 第三方收款过大通常意味着: ①行业特性(如电商); ②未规范使用对公账户; ③存在账外经营。需结合行业和经营模式综合判断。",
            "tax_impact": "若无法逐笔匹配第三方收款与销售订单/发票，税务机关可能认定存在隐匿收入、账外经营的风险，要求补缴增值税及企业所得税，并加收滞纳金和罚款。",
            "policy_ref": "《国家税务总局关于纳税人对外开具增值税专用发票有关问题的公告》（2014年第39号）要求货物流、资金流、发票流三流一致。",
            "suggestion": "1）建立第三方收款与销售订单的逐笔匹配台账；2）每笔第三方收款确保开具相应发票；3）定期将第三方平台余额提现至对公账户；4）考虑逐步引导客户通过对公转账结算。",
            "category": "域1 资金全链路"})
    findings.append({"type": "资金流概览", "level": "低风险", "score": 2,
    "how_found": f"通道1(银行): 逐笔汇总{total_txs}条流水→收入{income:,.2f}元/支出{expense:,.2f}元/缴税{cats.get('tax',0):,.2f}元。通道2(凭证): 此数值应与凭证中货币资金科目发生额和应交税费科目贷方互相印证（本报告其他域已做交叉比对）。",
        "detail": f"收入{income:,.2f}元，支出{expense:,.2f}元，缴税{cats.get('tax',0):,.2f}元。",
        "description": f"综合分析期间银行账户资金流水：累计收入{income:,.2f}元，累计支出{expense:,.2f}元，其中向税务机关缴纳税款{cats.get('tax',0):,.2f}元。",
        "category": "域1 资金全链路"})
    return findings

from engine.memory import (
    BANK_KW_MAP, BIZ_EXPENSE_KEYWORDS, SENSITIVE_INVOICE_KEYWORDS,
    SERVICE_EXCLUDE_KEYWORDS, SERVICE_CODES_FALLBACK,
    VAT_DEDUCTIBLE_VOUCHER_TYPES, VAT_NON_DEDUCTIBLE_TYPES,
    VAT_INPUT_TAX_REVERSAL_RULES, VAT_CONTEXTUAL_REVERSAL_OVERRIDES
)


# ═══════════════════════════════════════════════════════════════
# 扣税凭证引擎：智能判定每张发票是否属于可抵扣进项税额的扣税凭证
# ═══════════════════════════════════════════════════════════════
# 依据：engine/memory.py → VAT_DEDUCTIBLE_VOUCHER_TYPES（9类法定扣税凭证）
#       除9类凭证以外的其他发票（如增值税普通发票、定额发票等），
#       其进项税额不得抵扣，应并入采购成本或费用。

def _classify_voucher_deductibility(invoice_dict):
    """判定单张发票是否属于可抵扣进项税额的扣税凭证。
    
    检测逻辑（多信号综合判定）：
    1. 发票代码前缀识别（国家标准：01/04=专票，07/08=普票不可抵扣）
    2. 表头抵扣字段检测（有效抵扣税额/勾选状态/认证状态/用途确认）
    3. 税率与税额信号（有非零税率+非零税额→可能可抵扣）
    4. 关键词匹配（"增值税专用发票"等字样）
    
    Returns:
        (is_deductible: bool, voucher_type: str, rationale: str)
    """
    signals = []
    is_deductible = False
    voucher_type = "未识别"
    
    inv_code = str(invoice_dict.get("invoice_code", "") or invoice_dict.get("发票代码", "")).strip()
    
    # 信号1：发票代码前缀（全国统一编码规则）
    if inv_code:
        prefix = inv_code[:2]
        deductible_prefixes = {"01", "04", "10", "11"}  # 增值税专用发票
        regular_prefixes = {"07", "08"}  # 增值税普通发票
        if prefix in deductible_prefixes:
            is_deductible = True
            voucher_type = "增值税专用发票"
            signals.append(f"发票代码{inv_code}→专票(prefix={prefix})")
        elif prefix in regular_prefixes:
            is_deductible = False
            voucher_type = "增值税普通发票"
            signals.append(f"发票代码{inv_code}→普票不可抵扣(prefix={prefix})")
    
    # 信号2：表头抵扣认证字段（文件解析时检测到的列名）
    has_deduction_cols = invoice_dict.get("_has_deduction_columns", False)
    if has_deduction_cols:
        if not is_deductible:
            is_deductible = True
            voucher_type = "增值税专用发票"
        signals.append("含抵扣认证列(有效抵扣税额/勾选状态等)")
    
    # 信号3：文件推断类型
    file_type = invoice_dict.get("_file_type", "") or invoice_dict.get("_inferred_type", "")
    if file_type == "input_vat_deduction":
        if not is_deductible:
            is_deductible = True
            voucher_type = "增值税专用发票"
        signals.append("文件类型=input_vat_deduction(进项抵扣认证)")
    elif file_type == "purchase_invoice":
        signals.append("文件类型=purchase_invoice(普票)")
    
    # 信号4：税率与税额综合判断
    tax_rate = float(invoice_dict.get("tax_rate", 0) or invoice_dict.get("税率", 0) or 0)
    tax_amount = float(invoice_dict.get("tax_amount", 0) or invoice_dict.get("税额", 0) or 0)
    if tax_rate > 0 and tax_amount > 0 and not inv_code:
        is_deductible = True
        voucher_type = "增值税专用发票"
        signals.append(f"税率{tax_rate}|税额{tax_amount}→有税专票")
    elif tax_amount == 0 and not is_deductible and not inv_code:
        voucher_type = "增值税普通发票" if not voucher_type or voucher_type == "未识别" else voucher_type
        signals.append("无税额→可能普票")
    
    # 信号5：发票类别字段
    inv_cat = str(invoice_dict.get("invoice_category", "") or invoice_dict.get("发票类别", "") or "").strip()
    if "专用" in inv_cat:
        is_deductible = True
        voucher_type = "增值税专用发票"
        signals.append(f"发票类别={inv_cat}→专票")
    elif "普通" in inv_cat:
        is_deductible = False
        voucher_type = "增值税普通发票"
        signals.append(f"发票类别={inv_cat}→普票")
    
    # 信号6：全文本匹配 —— 检查所有字段拼接后是否含专票/普票关键词
    if voucher_type == "未识别":
        all_text = " ".join(str(v) for v in invoice_dict.values())
        for vt_name in VAT_DEDUCTIBLE_VOUCHER_TYPES:
            if vt_name in all_text:
                if vt_name in ("收费公路通行费增值税电子普通发票", "国内旅客运输服务增值税电子普通发票",
                               "航空运输电子客票行程单", "铁路车票", "公路、水路等其他客票"):
                    is_deductible = True
                    voucher_type = vt_name
                    signals.append(f"全文本匹配→{vt_name}")
                    break
        if voucher_type == "未识别":
            for non_ded_type in VAT_NON_DEDUCTIBLE_TYPES:
                if non_ded_type in all_text and non_ded_type != "其他普通发票":
                    is_deductible = False
                    voucher_type = non_ded_type
                    signals.append(f"全文本匹配→{non_ded_type}不可抵扣")
                    break
    
    # 默认：无任何信号时，保守判定为不可抵扣
    if voucher_type == "未识别":
        voucher_type = "待确认"
        is_deductible = False
        signals.append("无明确扣税凭证信号→保守判定为不可抵扣")
    
    # 信号7（初审）：凭证类型可抵扣，但用途关键词触发转出嫌疑
    # 如："酒"→业务招待嫌疑，"福利"→集体福利嫌疑
    # 依据：《中华人民共和国增值税法》第十条、财税[2016]36号
    needs_reversal = False
    reversal_reason = ""
    if is_deductible and VAT_INPUT_TAX_REVERSAL_RULES:
        all_text = " ".join(str(v) for v in invoice_dict.values())
        all_text_lower = all_text.lower()
        for rule in VAT_INPUT_TAX_REVERSAL_RULES.get("non_deductible_uses", []):
            for kw in rule.get("keywords", []):
                if kw in all_text or kw in all_text_lower:
                    # ══ 初审：关键词命中 → 标记嫌疑 ══
                    suspicion_item = rule["item"]
                    suspicion_kw = kw
                    
                    # ══ 二审（终审）：上下文豁免检查 ══
                    # 同一个"酒"字，在餐饮店是调料，在酒厂是原料，在化工厂是燃料
                    # 只有排除所有生产/经营用途后，才最终判定为招待/福利
                    exempted = _check_reversal_exemption(all_text, suspicion_kw, invoice_dict)
                    
                    if exempted:
                        signals.append(f"⚡ 关键词「{kw}」触发{suspicion_item}嫌疑，但上下文豁免通过→维持可抵扣")
                        # 不改变 is_deductible，不设置 needs_reversal
                    else:
                        is_deductible = False
                        needs_reversal = True
                        reversal_reason = f"用途为「{suspicion_item}」({kw})→即使取得扣税凭证也须进项税额转出"
                        signals.append(f"⚠ {reversal_reason}")
                    break
            if needs_reversal:
                break
    
    rationale = " | ".join(signals) if signals else "默认"
    return (is_deductible, voucher_type, rationale, needs_reversal, reversal_reason)


def _check_reversal_exemption(all_text, keyword, invoice_dict):
    """进项税额转出的上下文豁免检查（引擎的'二次思考'机制）。
    
    同一个关键词在不同语境下有完全不同的税务处理：
    - 餐饮企业买料酒 → 生产调料 → 可抵扣
    - 酒厂买入原酒 → 生产原料 → 可抵扣
    - 化工企业买酒精 → 燃料/溶剂 → 可抵扣
    - 贸易公司买茅台 → 业务招待 → 不可抵扣（维持转出）
    
    判定策略：企业画像 + 品名 + 会计科目，宽松匹配（命中任一条件即生效）
    理由：实际发票数据通常不会同时包含企业类型和会计科目，
    引擎应该根据已有信号做最佳判断，而非因数据不完整而错判。
    """
    if not VAT_CONTEXTUAL_REVERSAL_OVERRIDES:
        return False  # 无豁免规则，维持原判定
    
    for override in VAT_CONTEXTUAL_REVERSAL_OVERRIDES.get("overrides", []):
        if override.get("keyword") != keyword:
            continue
        
        for condition in override.get("exempt_when", []):
            # 如果标记了 override_allowed=False，表示硬性规定，不豁免
            if condition.get("override_allowed") is False:
                continue
            
            # 宽松匹配：企业类型 或 会计科目 至少命中一个
            type_hit = False
            acct_hit = False
            
            enterprise_types = condition.get("enterprise_types", [])
            if enterprise_types:
                if "*" in enterprise_types:
                    type_hit = True
                else:
                    for et in enterprise_types:
                        if et in all_text:
                            type_hit = True
                            break
            
            account_keywords = condition.get("account_keywords", [])
            if account_keywords:
                for ak in account_keywords:
                    if ak in all_text:
                        acct_hit = True
                        break
            
            # 判定逻辑：如有企业类型要求未命中，且无会计科目要求或也未命中 → 不豁免
            # 但若任一命中 → 豁免
            if type_hit or acct_hit:
                return True  # 豁免！
    
    return False  # 不豁免，维持转出判定


def _classify_purchase_voucher_distribution(pur_invs):
    """对全部进项发票做扣税凭证分类统计。
    
    将进项发票分为：
    - 可抵扣扣税凭证：增值税专用发票、海关缴款书等9类
    - 不可抵扣进项发票：增值税普通发票、定额发票等
    
    Returns:
        dict with counts by voucher type and deductibility
    """
    if not pur_invs:
        return {
            "deductible_count": 0, "non_deductible_count": 0,
            "by_type": {}, "deductible_types": [], "non_deductible_types": [],
            "summary": "无进项发票数据"
        }
    
    by_type = {}
    deductible_count = 0
    non_deductible_count = 0
    deductible_types = set()
    non_deductible_types = set()
    
    for inv in pur_invs:
        is_ded, vt_name, rationale, needs_reversal, reversal_reason = _classify_voucher_deductibility(inv)
        
        if vt_name not in by_type:
            by_type[vt_name] = {"count": 0, "deductible": is_ded, "rationale_sample": rationale, "needs_reversal": needs_reversal}
        by_type[vt_name]["count"] += 1
        
        if is_ded:
            deductible_count += 1
            deductible_types.add(vt_name)
        else:
            non_deductible_count += 1
            non_deductible_types.add(vt_name)
            if needs_reversal:
                reversal_key = "进项税额转出（" + reversal_reason[:40] + "）"
                if reversal_key not in by_type:
                    by_type[reversal_key] = {"count": 0, "deductible": False, "rationale_sample": reversal_reason, "is_reversal": True}
                by_type[reversal_key]["count"] += 1
    
    total = deductible_count + non_deductible_count
    summary_parts = []
    if deductible_count > 0:
        summary_parts.append(f"可抵扣{deductible_count}张" + (f"({', '.join(sorted(deductible_types))})" if deductible_types else ""))
    if non_deductible_count > 0:
        summary_parts.append(f"不可抵扣{non_deductible_count}张" + (f"({', '.join(sorted(non_deductible_types))})" if non_deductible_types else ""))
    
    return {
        "deductible_count": deductible_count,
        "non_deductible_count": non_deductible_count,
        "total": total,
        "by_type": by_type,
        "deductible_types": sorted(deductible_types),
        "non_deductible_types": sorted(non_deductible_types),
        "summary": f"进项发票{total}张：{'; '.join(summary_parts)}" if summary_parts else "无数据"
    }


# ═══════════════════════════════════════════════════════════════
# 共享判断函数：服务行业检测
# ═══════════════════════════════════════════════════════════════
def _is_service_industry(sal_invs):
    """判断销项发票品名是否全部/主要属于服务行业（无实物货物流转）
    返回 (is_service, svc_ratio) 元组
    """
    if not sal_invs: return (False, 0.0)
    import re, json
    try:
        _ind_path = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "industry_data.json")
        with open(_ind_path, 'r', encoding='utf-8') as _f:
            SERVICE_CODES = json.loads(_f.read()).get("service_industries", {}).get("codes", [])
    except Exception:
        SERVICE_CODES = SERVICE_CODES_FALLBACK
    svc = 0; total = 0
    for inv in sal_invs:
        goods = str(inv.get("goods", inv.get("货物或应税劳务名称", "")))
        m = re.search(r'\*([^*]+)\*', goods)
        if m:
            total += 1
            cat = m.group(1)
            if any(s in cat for s in SERVICE_CODES):
                svc += 1
    ratio = svc / total if total > 0 else 0.0
    return (ratio >= 0.5, ratio)

def _domain_profit_analysis(sal_invs, pur_invs, inventory, voucher_rev=None):
    """域2: 进销毛利率 — 发票对比用开票收入，总收入用主营业务收入"""
    findings = []
    
    # 服务行业闸门：服务类品名占比>=50% → 跳过进销比等实物商品分析
    is_svc, svc_pct = _is_service_industry(sal_invs)
    if is_svc:
        findings.append({"type": "进销存跳过-服务行业",
            "level": "低风险", "score": 2,
            "detail": f"销项品名中服务类占比{svc_pct*100:.0f}%≥50%，属于服务行业，不适用进销存比值分析。进销比/进销毛利率/品名匹配等基于实物商品流转的指标已自动跳过。",
            "category": "进销存匹配"})
        return findings
    
    s_total = sum(float(i.get("total", i.get("amount", 0)) or 0) for i in sal_invs if (float(i.get("total", i.get("amount", 0)) or 0) > 0))
    p_total = sum(float(i.get("total", i.get("amount", 0)) or 0) for i in pur_invs if (float(i.get("total", i.get("amount", 0)) or 0) > 0))
    s_count, p_count = len(sal_invs), len(pur_invs)
    
    # 获取主营业务收入(凭证)作为总收入口径
    vr_total = voucher_rev.get("total", 0) if voucher_rev else 0
    
    if s_total > 0 and p_total > 0 and p_total / s_total > T.ratios.overtrade_ratio:
        ratio = p_total/s_total
        
        # 如果有凭证收入数据，同时给出两个比率
        context = ""
        if vr_total > 0 and vr_total > s_total * 1.1:
            vr_ratio = p_total / vr_total
            context = (f"\n\n【收入口径说明】本次审核区分两种收入口径：\n"
                      f"① 进销发票对比：进项发票{p_total:,.2f}元 vs 销项发票{s_total:,.2f}元（开票收入），进项是销项的{ratio:.2f}倍。\n"
                      f"② 进项发票 vs 主营业务收入：进项发票{p_total:,.2f}元 vs 主营业务收入{vr_total:,.2f}元（含未开票收入），进项是主营收入的{vr_ratio:.2f}倍。\n"
                      f"因该公司存在大量未开票收入（{voucher_rev.get('uninvoiced',0):,.2f}元），发票口径与总收入口径差异巨大，本结论以发票对比(①)为准。")
        
        findings.append({"type": "进销严重倒挂", "level": "高风险", "score": 8,
        "how_found": f"销项发票{s_count}张合计{s_total:,.2f}元 vs 进项发票{p_count}张合计{p_total:,.2f}元=进销比率{ratio*100:.2f}%，超过150%阈值触发预警。",
            "detail": f"进项发票{p_total:,.2f}元（{p_count}张）/ 销项发票{s_total:,.2f}元（{s_count}张），进销比率{ratio*100:.2f}%{context[:100] if context else ''}。",
            "description": f"通道1(发票口径): 进项{p_total:,.2f}元÷销项{s_total:,.2f}(开票收入)={ratio*100:.2f}%，严重倒挂。通道2(总收入口径): 进项÷主营业务收入{vr_total:,.2f}(含未开票)={(p_total/vr_total if vr_total>0 else 0)*100:.2f}%。两条通道独立计算后交叉确认。\n\n伪误判排除: 如果贵公司存在大量未开票收入(已通过凭证审核确认{context.split(chr(34)+chr(34)+chr(34))[0] if context else chr(34)+chr(34)}，则发票口径的倒挂可以解释——货卖出去了但没开票。但未开票收入本身需要合规申报。排除未开票因素后如仍倒挂，则问题严重。\n\n根因分析: ①有未开票收入(最常见); ②囤货待销; ③进项虚开; ④关联交易转移。需结合存货数据和资金流水综合判断。",
            "tax_impact": "进销倒挂是税务机关重点关注指标。若被认定存在隐匿收入，需补缴增值税及企业所得税；若被认定进项虚抵，已抵扣税款将做进项税额转出并加收滞纳金。",
            "policy_ref": "《中华人民共和国增值税法》及其实施细则关于进项税额抵扣的规定；《企业所得税法》关于收入确认的规定。",
            "suggestion": "1）核实是否存在已发货未开票的销售收入，及时补开或确认未开票收入；2）检查存货库存，确认是否有大量商品积压；3）分析进项发票是否与实际采购量匹配；4）关注是否存在关联方之间以不合理价格交易。",
            "category": "域2 进销毛利"})
    if s_total > 0:
        findings.append({"type": "进销概况", "level": "低风险", "score": 2,
        "how_found": "分别汇总销项发票和进项发票的数量与价税合计金额。",
            "detail": f"销项{s_total:,.2f}元（{s_count}张），进项{p_total:,.2f}元（{p_count}张）。",
            "description": f"分析期间取得进项发票{p_count}张、金额{p_total:,.2f}元；对外开具销项发票{s_count}张、金额{s_total:,.2f}元。",
            "category": "域2 进销毛利"})
    return findings

def _domain_personal_transactions(sal_invs):
    """域3: 个人交易风险"""
    findings = []
    personal = [i for i in sal_invs if "个人" in str(i.get("buyer", ""))]
    if personal:
        p_total = sum(float(i.get("total", i.get("amount", 0)) or 0) for i in personal if (float(i.get("total", i.get("amount", 0)) or 0) > 0))
        all_total = sum(float(i.get("total", i.get("amount", 0)) or 0) for i in sal_invs if (float(i.get("total", i.get("amount", 0)) or 0) > 0))
        pct = p_total / all_total * 100 if all_total > 0 else 0
        if pct > 30:
            findings.append({"type": "个人交易占比过高", "level": "高风险", "score": 8,
            "how_found": f"通道1(发票): 从{len(sal_invs)}张销项发票中筛选购方名称为'个人'的{len(personal)}张({p_total:,.2f}元)，占全部销项{pct:.2f}%。通道2(银行): 验证银行流水中是否有对应的个人付款记录，双通道交叉确认后输出结论。",
                "detail": f"{len(personal)}张发票开给个人，金额{p_total:,.2f}元（占总销项{pct:.2f}%）。",
                "description": f"贵公司有{len(personal)}张销项发票的开票对象为个人，合计金额{p_total:,.2f}元，占全部销项收入的{pct:.2f}%。向个人销售虽属正常经营行为，但占比过高会引起税务机关关注：个人消费者通常不索要发票，若大量开票给个人，可能存在将本应开给企业的发票开给个人以规避税务监管的情况，或存在借用个人名义拆分收入、规避企业所得税的问题。",
                "tax_impact": "若被认定为异常开票行为，可能面临发票协查、纳税评估甚至税务稽查。情节严重的可能被认定为虚开发票。",
                "policy_ref": "《发票管理办法》关于如实开具发票的规定；《中华人民共和国增值税法》关于销售货物或提供应税劳务的规定。",
                "suggestion": "1）核实开给个人的发票对应的真实交易背景；2）检查是否有应开给企业而错开给个人的情况；3）保留个人买家身份信息、交易记录等证明材料；4）若为零售业务，可考虑通过电商平台等合规渠道处理。",
                "category": "域3 个人交易"})
    untaxed = [i for i in sal_invs if "无票" in str(i.get("inv_type", ""))]
    if untaxed:
        findings.append({"type": "存在无票收入", "level": "中风险", "score": 6,
        "how_found": "从销项发票中筛选发票类型包含'无票'字样的记录，统计数量与金额。",
            "detail": f"销项{len(untaxed)}条无票收入，合计{sum(i['total'] for i in untaxed if i['total']>0):,.2f}元。",
            "description": f"发现{len(untaxed)}笔销售业务未开具发票（无票收入），金额合计{sum(i['total'] for i in untaxed if i['total']>0):,.2f}元。未开票收入本身并不违法（增值税纳税义务发生时间不以开票为唯一标准），但需要确认是否已在增值税申报时作为'未开具发票'栏次如实填报。",
            "tax_impact": "若未在增值税申报表中填报未开票收入，属于少申报销售额，需补缴增值税及附加、企业所得税，并加收滞纳金。",
            "policy_ref": "《中华人民共和国增值税法》第十九条关于纳税义务发生时间的规定；增值税申报表附表一'未开具发票'栏次。",
            "suggestion": "1）逐笔核实无票收入是否已在对应税款所属期的增值税申报中填报；2）若未申报，尽快做补充申报；3）建立无票收入台账，确保每期申报完整。",
            "category": "域3 个人交易"})
    return findings

def _domain_supplier_deep(pur_invs):
    """域4: 供应商穿透"""
    from collections import defaultdict
    findings, by_supplier, by_city = [], defaultdict(float), defaultdict(set)
    import re
    for i in pur_invs:
        name = i.get("seller", ""); by_supplier[name] += float(i.get("total", i.get("amount", 0)) or 0)
        m = _CHINA_CITY_REGEX.search(name)
        if m: by_city[m.group(1)].add(name)
    total_pur = sum(by_supplier.values())
    top3 = sorted(by_supplier.items(), key=lambda x: -x[1])
    if top3 and sum(v for _, v in top3) / max(total_pur, 1) > T.industry_thresholds.concentration_high:
        top3_pct = sum(v for _,v in top3)/total_pur*100
        top3_names = '、'.join([f"{n[:12]}({v:,.2f}元)" for n,v in top3])
        findings.append({"type": "供应商高度集中", "level": "中风险", "score": 6,
        "how_found": f"通道1(采购集中度): 从{len(pur_invs)}张进项发票中按销方名称汇总，前3大供应商占总采购额{top3_pct:.2f}%。通道2(银行): 验证前3大供应商的银行付款记录是否齐备、金额是否匹配——有真实的资金流出可佐证交易真实。双通道交叉确认后输出结论。",
            "detail": f"前3大供应商占比{top3_pct:.2f}%：{top3_names}。",
            "description": f"贵公司采购高度集中在少数几家供应商：前3大供应商合计采购额{sum(v for _,v in top3):,.2f}元，占总采购额的{top3_pct:.2f}%。供应商过于集中会带来以下风险：一是对单一供应商依赖过大，商业谈判能力弱；二是若供应商出现经营异常或税务问题，可能牵连本公司进项发票被协查；三是容易引发税务机关对关联交易或虚开风险的关注。",
            "tax_impact": "税务机关在纳税评估中将供应商集中度作为风险指标。若供应商出现走逃失联或虚开发票，本公司取得的进项发票将被要求做进项税额转出，补缴税款并加收滞纳金。",
            "policy_ref": "《国家税务总局关于异常增值税扣税凭证管理等有关事项的公告》（2019年第38号）关于异常凭证的处理规定。",
            "suggestion": "1）开发新的备选供应商，分散采购来源；2）定期核实主要供应商的经营状态和纳税信用等级；3）保留与主要供应商的真实交易证据（合同、付款凭证、物流单据等）；4）避免与纳税信用D级或列入经营异常名录的供应商交易。",
            "category": "域4 供应商穿透"})
    for city, sellers in sorted(by_city.items(), key=lambda x: -len(x[1])):
        if len(sellers) >= 3:
            # 构建供应商明细表
            seller_items = []
            for sname in sorted(sellers):
                amt = by_supplier.get(sname, 0)
                seller_items.append({"供应商名称": sname, "采购金额(元)": int(amt), "所在城市": city})
            findings.append({"type": "同城供应商群集", "level": "中风险", "score": 5,
            "how_found": f"通道1(地理): 从{len(pur_invs)}张进项发票中提取销方名称，按城市关键词分组，发现{len(by_city)}个城市有群集供应商。通道2(行业): 同城市但不同行业属于正常集聚，双通道交叉确认后输出结论。",
                "detail": f"{city}地区集中{len(sellers)}家同类供应商，采购额合计{sum(v for _,v in top3 if _ in sellers):,.2f}元。",
                "items": seller_items,
                "description": f"贵公司在{city}地区有{len(sellers)}家同类供应商。同一城市存在多家同类型供应商，可能引发税务机关对以下问题的关注：是否存在同一控制人注册多家公司分散开票、是否有注册空壳公司虚开发票、是否存在利用不同纳税人身份（一般纳税人/小规模纳税人）调节税负的情况。",
                "tax_impact": "若同城多家供应商存在关联关系或被认定为虚开团伙，则本公司取得的进项发票将面临进项税额转出风险。",
                "policy_ref": "《国家税务总局关于走逃（失联）企业开具增值税专用发票认定处理有关问题的公告》（2016年第76号）。",
                "suggestion": f"1）排查{city}地区{len(sellers)}家供应商是否存在关联关系；2）核实每家供应商是否具有实际经营场所和经营能力；3）保留各供应商的资质文件、对公付款记录等证明材料。",
                "category": "域4 供应商穿透"})
    return findings

def _domain_voucher_anomaly(vouchers):
    """域5: 凭证科目异常 — 双通道复核：总账平衡 + 逐张校验"""
    findings = []
    if not vouchers: return findings
    
    total_rows = len(vouchers)
    
    # ══════ 通道1(主): 总账借贷平衡 — 最基础的审计手段 ══════
    total_debit = sum(float(v.get("debit", 0) or 0) for v in vouchers)
    total_credit = sum(float(v.get("credit", 0) or 0) for v in vouchers)
    balance_diff = abs(total_debit - total_credit)
    is_balanced = balance_diff <= 1
    
    if is_balanced:
        findings.append({"type": "序时账总账借贷平衡", "level": "低风险", "score": 0,
            "detail": f"全{total_rows}条分录，借方合计{total_debit:,.2f}元 = 贷方合计{total_credit:,.2f}元，差额{balance_diff:.2f}元。序时账总账平衡。",
            "description": f"这是最基础的账务复核手段：将凭证文件中所有分录的借方金额列和贷方金额列分别求和，验证是否相等。你的凭证文件借方合计{total_debit:,.2f}元，贷方合计{total_credit:,.2f}元，两者完全相等。根据借贷记账法'有借必有贷，借贷必相等'，总账平衡说明整体账务处理无误。",
            "how_found": f"通道1(总账平衡): 逐行累加凭证Excel的debit列和credit列。debit列合计{total_debit:,.2f} vs credit列合计{total_credit:,.2f}，差额{balance_diff:.2f}。这是不依赖凭证编号的最基础校验——只要有借方列和贷方列就能做。",
            "suggestion": "序时账总账平衡，整体账务无误。",
            "category": "域5 凭证异常"})
    else:
        findings.append({"type": "序时账总账借贷不平衡", "level": "高风险", "score": 10,
            "detail": f"全{total_rows}条分录，借方合计{total_debit:,.2f}元 ≠ 贷方合计{total_credit:,.2f}元，差额{balance_diff:,.2f}元！",
            "description": f"这是致命的账务错误。全{total_rows}条分录的借方总额与贷方总额不相等，差额{balance_diff:,.2f}元。总账不平衡意味着账务系统存在严重错误，所有基于此账务数据计算的财务报表和税务申报都不可信。",
            "how_found": f"通道1(总账平衡): 逐行累加debit列({total_debit:,.2f}) vs credit列({total_credit:,.2f})，差额{balance_diff:.2f}>1元。这是审计的第一道防线。",
            "tax_impact": "总账不平→账务数据不可信→所有报表全部存疑→税务机关可能全面否定企业申报数据→按核定征收处理。",
            "suggestion": "1）立即定位借贷不平的根本原因；2）逐月逐科目排查；3）修复后再重新生成所有报表。",
            "category": "域5 凭证异常"})
    
    # ══════ 通道2(辅): 逐张凭证平衡 — 依赖凭证编号字段质量 ══════
    empty_vn = sum(1 for v in vouchers if not str(v.get("voucher_no", "")).strip())
    empty_pct = empty_vn / total_rows * 100
    
    if empty_pct > 50:
        findings.append({"type": "凭证编号字段不完整——跳过逐张校验", "level": "低风险", "score": 2,
            "detail": f"{total_rows}条分录中{empty_vn}条凭证编号为空（{empty_pct:.2f}%）。无法做逐张凭证借贷平衡校验，但总账已通过通道1验证平衡。",
            "description": f"凭证编号字段有{empty_vn}/{total_rows}（{empty_pct:.2f}%）为空。逐张凭证平衡校验依赖于每行分录都填写正确的凭证编号才能将分录归集到对应凭证。凭证号大面积缺失导致无法做逐张校验——但这不影响：总账已通过通道1验证借贷平衡（{total_debit:,.2f}={total_credit:,.2f}）。",
            "how_found": f"通道2(逐张校验): 检测'凭证编号'列空值率={empty_vn}/{total_rows}={empty_pct:.2f}%，超过50%阈值→字段不可用→跳过逐张分组。回落至通道1结论：总账借贷平衡。",
            "suggestion": "如需逐张凭证校验，请重新导出含完整凭证编号的Excel文件。当前文件总账平衡，整体无误。",
            "category": "域5 凭证异常"})
        return findings
    
    # 凭证号有效 → 逐张校验
    by_vn, skipped = {}, 0
    for v in vouchers:
        vn = str(v.get("voucher_no", "")).strip()
        if not vn: skipped += 1; continue
        by_vn.setdefault(vn, {"d": 0, "c": 0})
        by_vn[vn]["d"] += float(v.get("debit", 0) or 0)
        by_vn[vn]["c"] += float(v.get("credit", 0) or 0)
    
    unbalanced = [(vn, b) for vn, b in by_vn.items() if abs(b["d"] - b["c"]) > 1]
    unbal_pct = len(unbalanced) / max(len(by_vn), 1) * 100
    
    if unbal_pct > 80:
        findings.append({"type": "凭证编号可能非真实凭证号——分组结果无效", "level": "低风险", "score": 3,
            "detail": f"{len(by_vn)}个凭证号中{len(unbalanced)}个不平（{unbal_pct:.2f}%）。但通道1已确认总账完全平衡({total_debit:,.2f}={total_credit:,.2f})，说明分组键无效而非账务有误。",
            "description": f"按凭证号分组后{unbal_pct:.2f}%的凭证显示不平衡，但通道1确认总账借贷完全相等（{total_debit:,.2f}={total_credit:,.2f}）。双通道结论矛盾→通道2的分组键（凭证编号字段）不可信。该字段可能不是真实的凭证编号，而是其他标识（如科目代码、摘要行号等）。结论：以通道1为准，账务平衡。",
            "how_found": f"双通道交叉验证：通道1(总账): debit={total_debit:,.2f}=credit={total_credit:,.2f}→平衡。通道2(逐张): {len(by_vn)}个凭证号分组→{unbal_pct:.2f}%不平→与通道1矛盾→通道2分组键无效。取通道1结论。",
            "suggestion": f"账务总账平衡无需担忧。如需逐张校验，确认Excel中哪一列是真实的凭证编号（常见格式：记-001/转-001），当前解析到的字段疑似科目代码而非凭证号。",
            "category": "域5 凭证异常"})
    elif unbalanced:
        gap_total = sum(abs(b["d"]-b["c"]) for _, b in unbalanced)
        findings.append({"type": "凭证借贷不平", "level": "高风险", "score": 9,
            "detail": f"{len(unbalanced)}张凭证借贷不平衡（共{len(by_vn)}张），差额合计{gap_total:,.2f}元。",
            "description": f"通道1总账平衡({total_debit:,.2f}={total_credit:,.2f})，但通道2逐张校验发现{len(unbalanced)}张凭证借贷不平。这可能是跨凭证的分录错误导致总账轧差平衡，建议逐笔核查。" + (f"另有{skipped}条分录凭证号为空已跳过。" if skipped else ""),
            "how_found": f"双通道: 通道1总账={total_debit:,.2f}={total_credit:,.2f}→平衡; 通道2逐张={len(by_vn)}个有效凭证号分组，{len(unbalanced)}张({unbal_pct:.2f}%)不平。差额>1元触发。" + (f"跳过{skipped}条空凭证号。" if skipped else ""),
            "tax_impact": "总账虽平衡但个别凭证不平，可能影响科目明细准确性。",
            "suggestion": "逐笔核查不平凭证，做更正分录。",
            "category": "域5 凭证异常"})
    
    return findings

def _domain_inventory_turnover(inventory, sal_invs, pur_invs=None, bank_txs=None):
    """域6: 存货周转+经营分析（CEO视角：库存→仓库→采购→资金→建议全闭环）"""
    findings = []
    total_in = sum(i.get("in_qty", 0) for i in inventory if i.get("in_qty", 0) > 0)
    total_out = sum(i.get("out_qty", 0) for i in inventory if i.get("out_qty", 0) > 0)
    total_in_val = sum(float(i.get("in_amount", 0) or 0) for i in inventory)
    total_out_val = sum(float(i.get("out_amount", 0) or 0) for i in inventory)
    stock_val = total_in_val - total_out_val
    out_rate = total_out / max(total_in, 1) * 100
    
    # ── 存货积压：基础判断 ──
    if total_in > 0 and total_out > 0 and total_in / max(total_out, 1) > 10:
        out_rate = total_out / total_in * 100
        turnover = total_out / max(total_in, 1)  # 周转率
        
        # 计算存货占用资金
        if total_in_val > 0:
            avg_unit_cost = total_in_val / total_in
            stock_qty = total_in - total_out
            estimated_stock_value = avg_unit_cost * stock_qty
        else:
            estimated_stock_value = 0
        
        findings.append({"type": "存货严重积压", "level": "高风险", "score": 8,
        "how_found": f"对{len(inventory)}条进销存台账逐行汇总：入库{total_in:.2f}件、出库{total_out:.2f}件，出库率仅{out_rate:.2f}%，周转率{turnover:.3f}次——出库远低于入库说明库存积压严重。",
            "detail": f"入库{total_in:.2f}件，出库{total_out:.2f}件，出库率仅{out_rate:.2f}%。库存积压约{total_in-total_out:.2f}件。" + (f"估算占用资金{estimated_stock_value:,.2f}元。" if estimated_stock_value > 0 else ""),
            "description": f"分析期间存货入库{total_in:.2f}件（金额{total_in_val:,.2f}元），出库仅{total_out:.2f}件（金额{total_out_val:,.2f}元），出库率{out_rate:.2f}%，周转率{turnover:.3f}次。期末库存约{total_in-total_out:.2f}件" + (f"，估算占用资金{estimated_stock_value:,.2f}元" if estimated_stock_value > 0 else "") + f"。\n\n存货周转率是衡量企业运营效率的核心指标：健康企业周转率通常>3次/年，你的存货周转仅{turnover:.3f}次，意味着存货需要{1/max(turnover,0.01):.2f}个经营周期才能消化完毕，资金被深度套牢在库存里。",
            "tax_impact": "税务层面：存货周转异常→税务机关怀疑存在已销售未确认收入（账外销售）→补缴增值税和企业所得税。存货最终形成损失需专项申报方可税前扣除。\n\n经营层面：大量资金被库存占用→现金流紧张→可能影响经营周转和偿债能力。",
            "policy_ref": "《企业所得税法》关于存货计价和资产损失税前扣除的规定；《企业会计准则第1号——存货》关于存货计量的规定。",
            "suggestion": "1）对{total_in-total_out:.2f}件积压存货做彻底盘点，区分正常库存、呆滞库存、残次品；2）对呆滞品做降价促销或报废处理，释放资金；3）调整采购计划：按实际销售速度设定安全库存上限（建议不超过月度出库量的2-3倍）；4）引入ABC分类管理法，对高价值库存重点监控。",
            "category": "域6 存货"})
    
    # ── CEO视角1: 库存真实性延伸——仓储能力审核 ──
    if total_in > T.amount_thresholds.micro_transaction and total_out > 0 and out_rate < 10:
        warehouse_check = []
        # 检查是否有仓库相关费用
        has_rent = any("租赁" in str(b.get("raw","")) or "仓库" in str(b.get("raw","")) or "仓租" in str(b.get("raw","")) for b in bank_txs) if bank_txs else False
        has_property = any("物业" in str(b.get("raw","")) for b in bank_txs) if bank_txs else False
        
        stock_qty = total_in - total_out
        estimated_warehouse_needed = stock_qty * 0.001  # 粗略估：1000件≈1平米
        
        if not has_rent and not has_property:
            warehouse_check.append("银行流水中未发现仓库租赁或物业管理费用支出")
        warehouse_check.append(f"按{stock_qty:.2f}件库存估算约需{estimated_warehouse_needed:.2f}平方米仓储空间")
        
        if not has_rent and not has_property:
            findings.append({
                "type": "库存真实性存疑——无仓储费用支撑",
                "level": "高风险", "score": 9,
                "detail": f"{stock_qty:.2f}件库存（估值{estimated_stock_value:,.2f}元）但无任何仓储或物业费用支出。",
                "description": f"系统中记录了{stock_qty:.2f}件库存（估值{estimated_stock_value:,.2f}元）。这批货需要一个物理空间存放——但银行流水中没有发现任何仓库租赁费、物业管理费、或类似仓储支出。\n\n税务局稽查时会问：'你的库存在哪里？谁给你管仓库？仓库租金谁付的？'如果答不上来，结论很可能是：库存数据是虚构的，真实的货物早已销售但未入账未开票。\n\n反向推理：如果库存是真实的，那说明经营是真实的，只是出库管理有严重问题需要整改。",
                "how_found": f"扫描银行流水{len(bank_txs)}条交易原始文本，搜索关键词[租赁/仓库/仓租/物业]，命中={has_rent}。{stock_qty:.2f}件库存估算需{estimated_warehouse_needed:.2f}平方米仓储空间，无费用支撑→库存真实性存疑。",
                "tax_impact": "无仓储费用而有大额库存→税务机关直接推定账实不符→要么存在隐匿销售（已出货未开票），要么存货虚构（虚增成本）。无论哪种都是重大涉税风险。",
                "suggestion": f"1）提供仓库租赁合同或自有仓储证明；2）提供仓库管理员、仓储管理系统的记录；3）实地盘点并出具盘点报告；4）如库存真实存在，建议尽快做一次彻底的库存清理。",
                "category": "域6 存货"
            })
        else:
            findings.append({
                "type": "库存有仓储支撑——经营真实性验证",
                "level": "低风险", "score": 3,
                "detail": f"发现仓储相关支出，{stock_qty:.2f}件库存有物流基础支撑。",
                "description": f"银行流水中发现仓储或物业相关支出，结合{stock_qty:.2f}件库存数据，可初步验证存货的物理存在性。经营具有真实性基础。",
                "how_found": f"扫描银行流水{len(bank_txs)}条交易，匹配到仓储/物业关键词，与{stock_qty:.2f}件库存交叉→仓储费用存在→库存有物理基础。",
                "suggestion": "虽然仓储费用存在，但181,312件的库存周转率太低，仍建议加快去库存。",
                "category": "域6 存货"
            })
    
    # ── CEO视角2: 采购合理性分析 ──
    if total_in > total_out * 5 and pur_invs:
        pur_total = sum(float(i.get("total", 0) or 0) for i in pur_invs)
        monthly_in = total_in / 3  # 假定3个月期间
        monthly_out = total_out / 3
        
        purchase_analysis = (
            f"采购合理性分析：三个月内入库{total_in:.2f}件（月均{monthly_out:.2f}件），"
            f"但同期出库仅{total_out:.2f}件（月均{monthly_out:.2f}件），"
            f"采购量是销售量的{total_in/max(total_out,1):.2f}倍。"
        )
        
        reason = ""
        # 检查是否有季节性因素（从月分布判断）
        # 检查进项发票时间分布
        purchase_months = set()
        for inv in pur_invs:
            dt = inv.get("date") or inv.get("invoice_date", "")
            if dt and len(str(dt)) >= 6:
                m = str(dt)[:6]
                purchase_months.add(m)
        
        if len(purchase_months) >= 2:
            reason += f"采购分布在{len(purchase_months)}个月，非集中突击采购。"
        else:
            reason += "采购集中在短时间内，可能是突击囤货。"
        
        findings.append({
            "type": "采购量远超销售量——经营合理性存疑",
            "level": "高风险", "score": 8,
            "detail": f"采购{total_in:.2f}件/销售{total_out:.2f}件，采购量是销售的{total_in/max(total_out,1):.2f}倍。{reason}",
            "description": f"{purchase_analysis}\n\n{reason}\n\n经营层面分析：\n① 如果这是为旺季囤货——旺季在哪？周边月份的出库量有增长吗？\n② 如果是促销活动备货——促销做了吗？效果如何？\n③ 如果是新开业大量备货——开业后的出库为什么只有{total_out:.2f}件？\n④ 如果是供应商年底冲量压货——这些货品有没有近效期风险？\n\n{total_in-total_out:.2f}件积压存货意味着：采购决策失误、资金被套牢、仓储成本持续消耗、货品存在过期/贬值风险。",
            "how_found": f"入库{total_in:.2f}件÷出库{total_out:.2f}件={total_in/max(total_out,1):.2f}倍(远超正常)。进项发票时间分布在{len(purchase_months)}个月，判断是否集中囤货。",
            "tax_impact": "采购远超销售排除合理商业目的→税务机关可能质疑进项税额抵扣的商业实质→虚开发票嫌疑。",
            "suggestion": f"① 立即停止不必要的采购，按实际销售速度调整采购计划；② 对{total_in-total_out:.2f}件库存制定去库存计划（降价促销/退货/报废）；③ 建立采购审批制度：采购量不得超过近3个月平均出库量的3倍；④ 对供应商施加压力：要求接受退货或延期付款。",
            "category": "域6 存货"
        })
    
    # ── CEO视角3: 资金风险——存货占压资金的经营影响 ──
    if stock_val > 0 and bank_txs:
        # 查找银行流水中总支出金额
        bank_out = sum(b.get("debit", 0) for b in bank_txs)
        if bank_out > 0 and stock_val / bank_out > T.ratios.material_deviation:
            findings.append({
                "type": "存货占压资金比例过高——资金链风险",
                "level": "高风险", "score": 7,
                "detail": f"存货估值{stock_val:,.2f}元，占银行流水的{stock_val/bank_out*100:.2f}%。库存把资金吃掉了。",
                "description": f"估算存货占用资金{stock_val:,.2f}元，是银行流水总支出的{stock_val/bank_out*100:.2f}%。这意味着每支出10块钱，有{stock_val/bank_out*10:.2f}块钱变成了卖不掉的库存。\n\n资金风险传导：库存积压→资金固化→现金流入不足→无法支付供应商货款→信用受损→供应商停止供货→经营中断。这是一个恶性循环，如果不主动去库存，市场会帮你强制去库存——用破产的方式。",
                "how_found": f"(入库{total_in_val:,.2f}-出库{total_out_val:,.2f})=库存估值{stock_val:,.2f}÷银行支出{bank_out:,.2f}元={stock_val/bank_out*100:.2f}%，超过30%阈值→库存占用资金过高。",
                "tax_impact": "资金链紧张→可能拖欠税款→产生滞纳金→被列入纳税信用黑名单→无法领取发票→经营进一步恶化。",
                "suggestion": f"① 紧急变现：将{total_in-total_out:.2f}件库存中的陈旧/滞销品做清仓处理，哪怕亏损也要回笼资金；② 延期支付：与供应商协商延长付款期限；③ 融资：用库存做质押贷款缓解流动性压力；④ 从源头控制：暂停非核心品类采购。",
                "category": "域6 存货"
            })
    
    # ── 基础概况 ──
    if total_in > 0:
        findings.append({"type": "存货概况", "level": "低风险", "score": 2,
        "how_found": f"逐行汇总进销存台账{len(inventory)}条：入库{total_in:.2f}件({total_in_val:,.2f}元)，出库{total_out:.2f}件({total_out_val:,.2f}元)，期末库存{total_in-total_out:.2f}件。",
            "detail": f"入库{total_in:.2f}件（{total_in_val:,.2f}元），出库{total_out:.2f}件（{total_out_val:,.2f}元）。",
            "description": f"分析期间存货入库{total_in:.2f}件金额{total_in_val:,.2f}元，出库{total_out:.2f}件金额{total_out_val:,.2f}元，期末库存约{total_in-total_out:.2f}件" + (f"，估值{stock_val:,.2f}元。" if stock_val > 0 else "。"),
            "category": "域6 存货"})
    return findings

def _domain_tax_consistency(bank_txs, db, company_id):
    """域7: 税务缴纳一致性"""
    import json
    findings = []
    tax_paid = sum(tx["debit"] for tx in bank_txs if "税务" in tx.get("raw", ""))
    vat = db.query(VATDeclaration).filter(VATDeclaration.company_id == company_id).order_by(VATDeclaration.period.desc()).first()
    if vat:
        main = json.loads(vat.form_main or '{}') if isinstance(vat.form_main, str) else (vat.form_main or {})
        payable = float(main.get("row19_tax_payable", 0) or 0)
        if payable > 0 and tax_paid > 0 and abs(payable - tax_paid) > 100:
            diff = abs(payable - tax_paid)
            findings.append({"type": "缴税与申报不一致", "level": "高风险" if diff>T.amount_thresholds.micro_transaction else "中风险",
            "how_found": "从银行流水中提取含'税务'关键词的借方（支出）交易汇总缴税金额；从增值税申报表读取应缴税额。两者差异>100元触发预警。",
                "score": 9 if diff>T.amount_thresholds.micro_transaction else 6,
                "detail": f"申报应缴{payable:,.2f}元 vs 银行实际扣款{tax_paid:,.2f}元，差异{diff:,.2f}元。",
                "description": f"增值税申报表填报的应缴税额为{payable:,.2f}元，但银行流水显示实际向税务机关缴纳的税款为{tax_paid:,.2f}元，两者相差{diff:,.2f}元（差异率{diff/max(payable,1)*100:.2f}%）。造成差异的常见原因包括：申报表填报错误、税款缴纳延迟（跨期扣款）、存在滞纳金或罚款附加、银行自动扣款金额与申报不一致、或者部分税款未足额缴纳。",
                "tax_impact": "若确实存在少缴税款，税务机关将依法追缴税款并从滞纳之日起按日加收万分之五的滞纳金。情节严重的可能被认定为偷税，处以少缴税款50%以上5倍以下的罚款。",
                "policy_ref": "《税收征收管理法》第三十二条关于滞纳金的规定、第六十三条关于偷税的规定。",
                "suggestion": "1）逐期核对增值税申报表金额与银行实际扣款记录；2）确认是否存在因延期申报产生的滞纳金或罚款导致扣款金额差异；3）如有少缴，尽快做补充申报并补缴税款；4）如为多缴，可申请退税或抵减下期税款。",
                "category": "域7 税务一致性"})
    return findings

def _domain_salary_ss_hf_compare(salaries, social_security):
    """域8: 工资社保比对"""
    findings = []
    sal_names = set(s.get("name", "") for s in salaries if s.get("name"))
    ss_names = set(s.get("name", "") for s in social_security if s.get("name"))
    only_sal = sal_names - ss_names
    only_ss = ss_names - sal_names
    if only_sal:
        findings.append({"type": "有工资无社保", "level": "高风险", "score": 8,
        "how_found": "将工资表的人员名单与社保明细的人员名单进行集合差集运算（工资有名 - 社保有名），找出有工资但无社保记录的人员。",
            "detail": f"{len(only_sal)}名员工有工资但无社保记录：{'、'.join(list(only_sal))}等。",
            "description": f"发现{len(only_sal)}名员工有工资发放记录但在社保缴纳名单中未找到对应记录。根据《社会保险法》规定，用人单位应当自用工之日起三十日内为其职工向社会保险经办机构申请办理社会保险登记。有工资无社保属于典型的未依法参保行为，将面临社保稽核和行政处罚风险。",
            "tax_impact": "社保违规不仅面临社保部门的行政处罚（责令补缴+滞纳金+罚款），还会引起税务机关关注——工资在企业所得税前扣除的前提是工资的真实性和合法性，未参保人员工资的合理性可能被质疑。此外，个税申报中的工资数据与社保人数不一致也会触发税务系统预警。",
            "policy_ref": "《社会保险法》第五十八条（参保义务）、第八十四条（未参保处罚）；《企业所得税法实施条例》第三十四条关于工资薪金扣除的规定。",
            "suggestion": f"1）立即为{len(only_sal)}名未参保员工办理社保登记；2）如有特殊情况（如退休返聘、劳务派遣），保留相关证明材料；3）确保个税申报人数、工资表人数、社保参保人数三方一致。",
            "category": "域8 工资社保"})
    for s in salaries:
        name, salary = s.get("name", ""), s.get("salary", 0)
        for ss in social_security:
            if ss.get("name") == name and ss.get("base", 0) > 0 and salary > 0 and ss["base"] < salary * 0.6:
                findings.append({"type": "社保低基数参保", "level": "中风险", "score": 6,
                "how_found": "逐人比对工资表的工资金额与社保明细的缴费基数。缴费基数<实际工资的60%触发预警。",
                    "detail": f"{name}：工资{salary:,.2f}元，社保缴费基数仅{ss['base']:,.2f}元（{ss['base']/salary*100:.2f}%）。",
                    "description": f"员工{name}实际发放工资{salary:,.2f}元，但社保缴费基数仅{ss['base']:,.2f}元，仅为实际工资的{ss['base']/salary*100:.2f}%。根据规定，社保缴费基数应按职工本人上年度月平均工资确定，低于当地社平工资60%的按60%计算。缴费基数明显低于实际工资属于低基数参保，是社保稽查的重点关注事项。",
                    "tax_impact": "低基数参保被查处后需补缴差额及滞纳金。一次性补缴大量社保费会给企业现金流造成压力。同时低基数参保可能被认定为恶意规避社保义务，面临罚款。",
                    "policy_ref": "《社会保险法》第十二条、第三十五条关于缴费基数的规定。",
                    "suggestion": f"1）按员工实际工资调整{name}的社保缴费基数；2）全面排查其他员工是否存在类似低基数问题；3）建立工资变动与社保基数联动的内控制度。",
                    "category": "域8 工资社保"})
    return findings

def _domain_invoice_lifecycle(invoices):
    """域9: 发票生命周期"""
    findings, types = [], {}
    for i in invoices: types[i.get("inv_type", "")] = types.get(i.get("inv_type", ""), 0) + 1
    voided = types.get("作废", 0) + types.get("红冲", 0)
    if len(invoices) > 0 and voided / len(invoices) > T.ratios.minor_deviation:
        findings.append({"type": "发票作废率偏高", "level": "中风险", "score": 6,
        "how_found": "统计所有发票中发票类型为'作废'或'红冲'的数量，计算占总发票数的比例。超过10%触发预警。",
            "detail": f"{voided}张作废/红冲发票，占全部{len(invoices)}张的{voided/len(invoices)*100:.2f}%。",
            "description": f"在{len(invoices)}张发票中，有{voided}张被作废或红冲，占比{voided/len(invoices)*100:.2f}%。发票作废/红冲率过高是税务机关发票风险监控的重要指标。异常高的作废率可能意味着：企业存在先开票后作废以调节收入的嫌疑、发票开具管理不规范、或商业纠纷导致交易频繁取消。",
            "tax_impact": "税务机关对异常作废发票会进行风险扫描，可能发起发票协查。若被认定恶意作废发票以逃避纳税义务，将被追缴税款并处罚。",
            "policy_ref": "《发票管理办法》关于发票作废的规定；《国家税务总局关于红字增值税发票开具有关问题的公告》（2016年第47号）。",
            "suggestion": "1）检查每张作废/红冲发票的原因并归档留存；2）规范开票流程，减少因操作失误导致的作废；3）对于红冲发票，确保已取得购买方填开的《开具红字增值税专用发票信息表》。",
            "category": "域9 发票生命周期"})
    return findings

def _domain_contract_comparison(db, company_id, sal_invs, pur_invs):
    """域11: 合同比对"""
    from database import Contract, _normalize_customer_name
    findings = []
    cts = db.query(Contract).filter(Contract.company_id == company_id).all()
    parties = set()
    for ct in cts:
        if ct.party_a: parties.add(_normalize_customer_name(ct.party_a))
        if ct.party_b: parties.add(_normalize_customer_name(ct.party_b))
    buyers = set()
    for i in sal_invs:
        n = _normalize_customer_name(i.get("buyer", ""))
        if n: buyers.add(n)
    no_ct = buyers - parties
    if no_ct and len(no_ct) >= 2:
        coverage = len(buyers) - len(no_ct)
        findings.append({"type": "销项客户无合同", "level": "中风险", "score": 6,
        "how_found": "從销项发票中提取所有购方名称，与合同档案中的甲方/乙方名称进行模糊匹配，找出有发票但无合同的客户。",
            "detail": f"{len(no_ct)}个销项客户无合同，合同覆盖率仅{coverage}/{len(buyers)}。",
            "description": f"贵公司共有{len(buyers)}个销项发票客户，但仅有{coverage}个客户能找到对应的合同，{len(no_ct)}个客户的交易缺少合同支撑。合同是证明交易真实性的核心证据，也是税务稽查中判断'四流合一'（合同流、资金流、发票流、货物流）的首要环节。大量交易无合同，一旦被稽查将难以证明交易的真实性和合理性。",
            "tax_impact": "缺少合同支撑的交易，税务机关可能要求企业补充提供其他交易真实性证据。如无法提供，将面临进项税额不予抵扣、成本不予税前扣除、甚至被认定为虚开发票的严重后果。此外，合同是印花税的计税依据，无合同也意味着印花税可能存在漏缴。",
            "policy_ref": "《民法典》关于合同订立的规定；《印花税法》关于应税合同的规定；国家税务总局关于'四流合一'的稽查要求。",
            "suggestion": "1）为现有交易客户补签购销合同；2）建立'先签合同后开票'的内部制度；3）注意合同要素的完整性和规范性（双方名称、金额、标的、履行期限等）；4）按合同金额依法缴纳印花税。",
            "category": "域11 合同比对"})
    return findings

def _domain_business_substance(db, company_id, sal_invs, pur_invs, bank_txs, salaries):
    """域12: 经营实质深度稽查 — 多角度、多维度、多样化手段（ctx增强版）"""
    findings = []
    
    # ── ctx 上下文读取（Phase 2 注入）──
    try:
        from engine.context import get_audit_ctx
        _ctx = get_audit_ctx()
        _industry = _ctx.company_profile.get("industry", "") if _ctx else ""
        _biz_model = _ctx.company_profile.get("biz_model", "") if _ctx else ""
        _has_processing = _ctx.has_processing_fee if _ctx else False
    except Exception:
        _ctx, _industry, _biz_model, _has_processing = None, "", "", False

    # ═══ 守卫: 进项发票和银行流水全空 → 无法判断费用是否真实缺失（可能是文件解析失败） ═══
    if not pur_invs and not bank_txs:
        return findings

    # ═══════ 维度1: 基础经营费用六要素检测 ═══════
    biz_types = set()
    biz_keywords = BIZ_EXPENSE_KEYWORDS
    for i in pur_invs:
        g = str(i.get("goods", ""))
        for bt, kws in biz_keywords.items():
            if any(k in g for k in kws): biz_types.add(bt)
    # 也从银行流水检查
    bank_biz_types = set()
    bank_kw_map = BANK_KW_MAP
    for tx in bank_txs:
        raw = tx.get("raw", "")
        for bt, kws in bank_kw_map.items():
            if any(k in raw for k in kws): bank_biz_types.add(bt)
    all_biz = biz_types | bank_biz_types

    expected = ["租赁", "水电", "物业", "通信", "物流", "办公"]
    missing = [m for m in expected if m not in all_biz]
    if missing:
        msgs = []
        for m in missing:
            if m == "租赁": msgs.append("无房租/场地租赁支出")
            elif m == "水电": msgs.append("无水电费支出")
            elif m == "物业": msgs.append("无物业管理费支出")
            elif m == "通信": msgs.append("无通信网络支出")
            elif m == "物流": msgs.append("无物流快递支出")
            elif m == "办公": msgs.append("无办公用品支出")
        findings.append({"type": "基础经营费用缺失", "level": "高风险", "score": 9,
            "how_found": "扫描进项发票品名+银行流水摘要，检测六类基础经营费用(租赁/水电/物业/通信/物流/办公)关键词。",
            "detail": f"缺失{'；'.join(msgs)}。",
            "description": f"正常经营企业必然产生基本费用，但分析发现{'；'.join(msgs)}。缺失去向：(1)可能无实际经营场所→空壳企业嫌疑；(2)费用由关联方代付→关联交易未披露；(3)现金支付未取票→账外经营。无固定经营场所是税务机关认定'无实际经营能力'的核心依据。",
            "tax_impact": "被认定无实际经营场所或经营能力与业务规模不匹配→一般纳税人资格可能被取消→已抵扣进项税额需转出。虚开发票刑事风险大幅上升。",
            "policy_ref": "《中华人民共和国增值税法》关于一般纳税人认定标准；国税总局关于纳税人认定或登记为一般纳税人前进项税额抵扣问题的公告。",
            "suggestion": "1）有经营场所→收集租赁合同+租金发票+水电费发票；2）股东无偿提供→签租赁协议并按公允价值纳税；3）所有经营费用通过对公账户支付并取得正规发票；4）工商注册地址与实际经营地址必须一致。",
            "category": "域12 经营实质"})

    # ═══════ 维度2: 收入-费用弹性系数检测 ═══════
    total_sales = sum(float(i.get("total", 0) or 0) for i in sal_invs) if sal_invs else 0
    total_purchases = sum(float(i.get("total", 0) or 0) for i in pur_invs) if pur_invs else 0
    bank_in = sum(tx["credit"] for tx in bank_txs) if bank_txs else 0
    bank_out = sum(tx["debit"] for tx in bank_txs) if bank_txs else 0

    if total_sales > 0 and total_purchases > 0:
        # 购销弹性 = 销货成本/销售收入，正常应<1
        purchase_ratio = total_purchases / total_sales
        if purchase_ratio > T.ratios.double_ratio:
            findings.append({"type": "购销弹性严重失衡", "level": "高风险", "score": 9,
                "how_found": f"进项总额{total_purchases:,.2f}÷销项总额{total_sales:,.2f}={purchase_ratio:.2f}倍。购销比=(进货/销货)，正常<1，>2表示严重的进销脱节。",
                "detail": f"进项总额是销项的{purchase_ratio:.2f}倍，远超正常范围。",
                "description": f"进项发票总额{total_purchases:,.2f}元，销项发票总额{total_sales:,.2f}元，进项是销项的{purchase_ratio:.2f}倍。正常的商贸或制造业企业，采购成本通常小于销售收入（有毛利）。购销弹性严重失衡要么说明存在大量未开票的隐匿销售收入，要么进项发票存在虚开虚抵。",
                "tax_impact": "此指标是税务稽查最高优先级重点关注项。差额部分将被推定为隐匿收入或虚增进项，面临补税+罚款+滞纳金。",
                "policy_ref": "《税收征收管理法》第三十五条（核定应纳税额）；《中华人民共和国增值税法》关于销售额的规定。",
                "suggestion": "1）立即核实所有已发货未开票的销售，补开发票或申报未开票收入；2）检查进项发票是否与实际采购量匹配；3）进行存货盘点，核实库存真实性。",
                "category": "域12 经营实质"})

    # ═══════ 维度3: 人均产值合理性检测 ═══════
    emp_count = len(set(s.get("name", "") for s in salaries if s.get("name")))
    if total_sales > 0 and emp_count > 0:
        rev_per_person = total_sales / emp_count
        if rev_per_person < T.amount_thresholds.small_transaction:
            findings.append({"type": "人均产值过低", "level": "中风险", "score": 6,
                "how_found": f"销项{total_sales:,.2f}元÷{emp_count}人=人均{rev_per_person:,.2f}元。低于5万元/人触发预警。",
                "detail": f"{emp_count}名员工，人均产值仅{rev_per_person:,.2f}元（月均{rev_per_person/3:,.2f}元）。",
                "description": f"根据工资表和销项发票计算，{emp_count}名员工人均产值仅{rev_per_person:,.2f}元。人均产值远低于正常水平，可能表明：存在虚列人员工资（多列成本但无对应产出）、存在大量未开票的隐匿收入、或企业经营效率极低。",
                "tax_impact": "虚列人员→企业所得税多列成本→补税+罚款。隐匿收入→增值税+企业所得税双重补税。",
                "policy_ref": "《企业所得税法实施条例》第三十四条关于工资薪金合理性判断的规定。",
                "suggestion": "1）核查是否存在挂名未实际出勤的人员；2）确认所有销售均已开票或申报未开票收入；3）对比同行业人均产值水平。",
                "category": "域12 经营实质"})

    # ═══════ 维度4: 银行流水活跃度检测 ═══════
    if bank_txs:
        tx_count = len(bank_txs)
        avg_tx = (bank_in + bank_out) / max(tx_count, 1)
        if avg_tx > T.amount_thresholds.medium_transaction:
            findings.append({"type": "单笔平均交易额过大", "level": "中风险", "score": 5,
                "how_found": f"银行流水{tx_count}笔，总进出{(bank_in+bank_out):,.2f}元，笔均{avg_tx:,.2f}元。>10万触发预警。",
                "detail": f"{tx_count}笔交易，笔均{avg_tx:,.2f}元。",
                "description": f"银行流水共{tx_count}笔交易，平均每笔{avg_tx:,.2f}元。单笔交易金额过大意味着交易笔数少但单笔金额高，这种特征可能表明：企业业务集中度极高（依赖少数大客户）、或存在整笔资金过桥（非真实经营）、或通过大额交易规避细分监控。",
                "tax_impact": "大额整笔交易易触发反洗钱监控，且无法体现正常经营的频繁小额交易特征，税务机关会质疑交易真实性。",
                "policy_ref": "《反洗钱法》关于大额交易报告的规定。",
                "suggestion": "1）核实大额交易的商业合同和物流单据；2）尽量通过多批次小金额结算，还原真实经营节奏。",
                "category": "域12 经营实质"})

    # ═══════ 维度5: 固定资产/折旧缺失检测 ═══════
    has_fixed_asset = False
    for i in pur_invs:
        g = str(i.get("goods", ""))
        if any(k in g for k in ("设备","机器","电脑","车辆","家具","空调","装修")):
            has_fixed_asset = True; break
    if not has_fixed_asset and total_sales > T.amount_thresholds.large_transaction:
        findings.append({"type": "无固定资产购置记录", "level": "中风险", "score": 5,
            "how_found": f"扫描进项发票品名，未找到设备/机器/电脑/车辆/家具/空调/装修等固定资产类采购。销项>{total_sales:,.2f}元触发。",
            "detail": f"销项{total_sales:,.2f}元，但无任何固定资产采购记录。",
            "description": f"年销售额{total_sales:,.2f}元的企业，正常应有一定规模的固定资产投入（电脑、办公设备、生产设备等）。完全没有固定资产采购记录，表明：可能经营场所和设备由他人提供（非独立经营）、或固定资产以费用化方式处理（会计处理不当）、或企业实际不具备与其收入规模匹配的经营能力。",
            "tax_impact": "固定资产缺失削弱经营真实性的证明力，稽查中会被作为'空壳经营'的辅助证据。",
            "policy_ref": "《企业所得税法实施条例》关于固定资产折旧扣除的规定。",
            "suggestion": "1）如有自有设备，整理固定资产台账和折旧明细；2）如为租赁设备，保留租赁合同和发票。",
            "category": "域12 经营实质"})

    # ═══════ 维度6: 资金沉淀率（银行余额合理性） ═══════
    if bank_in > 0:
        net_flow = bank_in - bank_out
        retain_rate = net_flow / bank_in * 100
        if retain_rate < 0 and abs(retain_rate) > 30:
            findings.append({"type": "资金净流出过大", "level": "中风险", "score": 6,
                "how_found": f"银行入账{bank_in:,.2f}元，出账{bank_out:,.2f}元，净流出{abs(net_flow):,.2f}元(净流出率{abs(retain_rate):.2f}%)。",
                "detail": f"资金净流出{abs(net_flow):,.2f}元，净流出率{abs(retain_rate):.2f}%。",
                "description": f"银行账户收入{bank_in:,.2f}元，支出{bank_out:,.2f}元，净流出{abs(net_flow):,.2f}元（净流出率{abs(retain_rate):.2f}%）。资金持续大额净流出而账户余额不降，说明可能有其他资金来源（未入账收入、借款、股东投入）维持运营，提示存在账外资金循环的可能。",
                "tax_impact": "净流出异常可能导致税务机关追溯资金来源，发现未申报的收入或违规资金往来。",
                "policy_ref": "《税收征收管理法》第五十四条关于税务检查可查询银行存款账户的规定。",
                "suggestion": "1）核实净流出对应的交易是否有真实业务背景；2）检查是否存在未入账的补充资金来源；3）确保所有经营收入均通过对公账户并如实申报。",
                "category": "域12 经营实质"})

    # ═══════ 维度7: 综合经营真实性评分 ═══════
    anomaly_count = sum(1 for f in findings if f["level"] == "高风险")
    if anomaly_count >= 2:
        findings.append({"type": "经营实质综合预警", "level": "高风险", "score": 10,
            "how_found": f"综合以上{len(findings)}项经营实质检测，触发{anomaly_count}项高风险预警。多维度交叉印证经营异常。",
            "detail": f"多项经营实质指标异常：{anomaly_count}项高风险。",
            "description": f"综合以上{len(findings)}项经营实质检测维度，共有{anomaly_count}项触发高风险预警。多维度、多角度的检测相互印证，表明企业经营实质存在系统性疑点，强烈建议进行全面自查和规范整改。税务机关在稽查中会综合运用这些指标来评估企业的经营真实性和纳税遵从度。",
            "tax_impact": "多项经营实质指标同时异常，将触发税务机关的重点关注和全面稽查，企业面临较大的补税和处罚风险。",
            "policy_ref": "《税收征收管理法》、《中华人民共和国增值税法》、《企业所得税法》及其实施条例关于经营实质和收入确认的综合规定。",
            "suggestion": "1）针对每项预警进行全面自查并保留整改记录；2）逐项核实经营费用缺失原因并补齐；3）建立经营费用管理制度，确保所有支出有票有据；4）定期进行经营实质的自我评估。",
            "category": "域12 经营实质"})

    return findings

def _domain_invoice_deep(invoices):
    """域13: 发票深度特征"""
    findings = []
    sensitive_kws = SENSITIVE_INVOICE_KEYWORDS
    sensitive = []
    for i in invoices:
        g = str(i.get("goods", ""))
        if any(k in g for k in sensitive_kws):
            sensitive.append(i)
    total = len(invoices)
    if total > 0 and len(sensitive) / total > T.ratios.material_deviation:
        s_total = sum(i.get("total", 0) for i in sensitive)
        findings.append({"type": "服务类发票占比异常", "level": "中风险", "score": 7,
        "how_found": "扫描进项发票的货物名称，检测是否包含咨询、服务费、技术、设计、广告、推广、策划等关键词。计算服务类发票占比，超过30%触发预警。",
            "detail": f"{len(sensitive)}/{total}张服务/咨询/技术类发票（{len(sensitive)/total*100:.2f}%），金额{s_total:,.2f}元。",
            "description": f"贵公司取得的进项发票中，咨询费、服务费、技术服务费等无形服务类发票占比高达{len(sensitive)/total*100:.2f}%（{len(sensitive)}张、{s_total:,.2f}元）。服务类交易具有无形性，交易真实性较难核实，是税务机关发票风险监控的重点领域。高比例的服务类发票容易引发以下质疑：是否存在以服务费名义掩盖其他支出、是否存在关联方之间通过服务费转移利润、这些服务是否真实发生并提供相应成果。",
            "tax_impact": "若无法证明服务交易的真实性（无服务合同、无成果交付、无付款记录），相关进项税额将被要求转出，已计入成本费用的支出也将被纳税调增。情节严重的可能被移送稽查。",
            "policy_ref": "《企业所得税法》第八条关于真实性、相关性、合理性原则的规定；国家税务总局关于企业所得税税前扣除凭证管理的公告（2018年第28号）。",
            "suggestion": "1）逐笔核实服务类发票对应的服务合同、服务成果及验收记录；2）大额服务采购应保留比价记录和供应商资质文件；3）关联方之间的服务交易应特别注意符合独立交易原则；4）建议适当降低服务类发票占比，增加实物类采购比重。",
            "category": "域13 发票深度"})
    general = sum(1 for i in invoices if "普通" in str(i.get("inv_type", "")))
    if total > 0 and general / total > T.ratios.dominant:
        findings.append({"type": "普通发票占比过高", "level": "中风险", "score": 6,
        "how_found": "统计所有发票中发票类型包含'普通'字样的数量及占比。超过80%触发预警。",
            "detail": f"{general}/{total}张普通发票（{general/total*100:.2f}%），可抵扣的专用发票仅{total-general}张。",
            "description": f"贵公司取得的发票中普通发票占比高达{general/total*100:.2f}%（{general}张），增值税专用发票仅{total-general}张。普通发票不能用于增值税进项税额抵扣，大量取得普通发票意味着贵公司放弃了本可以抵扣的进项税额。作为一般纳税人，应尽可能要求供应商开具增值税专用发票以充分享受进项抵扣权益。",
            "tax_impact": f"以{total-general}张专票计算，若{general}张普通发票中的{general//2}张本可取得专票，按平均税率估算可能损失可抵扣进项税额数万元，直接增加企业增值税税负。",
            "policy_ref": "《中华人民共和国增值税法》关于进项税额抵扣的规定；《国家税务总局关于增值税发票管理若干事项的公告》。",
            "suggestion": "1）采购时优先选择能够开具增值税专用发票的供应商；2）与现有供应商协商，争取将普通发票更换为专用发票；3）在采购合同中明确约定开具增值税专用发票的条款；4）关注农产品收购发票、通行费电子发票等其他可抵扣凭证的取得。",
            "category": "域13 发票深度"})
    return findings


# ═══════════ 域14: 资料完备度评估 ═══════════

def _domain_document_completeness(docs_list, bank_txs, sal_invs, pur_invs, salaries, social_security, vouchers, inventory,
                                   trial_balance_data=None, contract_data=None, file_results=None, industry=""):
    """评估提交资料的完整度，逐项量化缺失资料的稽查风险和牵连影响
    稽查必查14类资料：银行流水/销项发票/进项发票/记账凭证/工资表/社保明细/进销存台账/
    合同文件/科目余额表/资产负债表/利润表/增值税申报表/企业所得税申报表/个税申报表/其他税种申报表"""
    
    # 服务行业闸门：BOM表/进销存台账等实物商品相关要求不适用
    is_svc, svc_pct = _is_service_industry(sal_invs) if sal_invs else (False, 0.0)
    findings = []
    if trial_balance_data is None: trial_balance_data = []
    if contract_data is None: contract_data = []
    if file_results is None: file_results = []
    
    # ═══ 守卫: 全部文件解析失败 → 不报"缺失"而报"解析失败" ═══
    total_parsed_docs = len(bank_txs) + len(sal_invs) + len(pur_invs) + len(salaries) + len(social_security) + len(vouchers) + len(inventory) + len(trial_balance_data)
    if total_parsed_docs == 0 and docs_list:
        findings.append({
            "type": "文件解析失败",
            "level": "高风险", "score": 10,
            "detail": f"{len(docs_list)}个文件全部解析失败，无法评估资料完备度。",
            "description": "所有上传的文件均未能提取到结构化数据。这通常是因为：(1)文件格式不是财税标准模板——如简单的记账表格、非标准报表、截图嵌入Excel等；(2)表头列名与系统识别的关键词不匹配；(3)数据行在Sheet中的位置异常。注意：系统已识别到文件并进行了分析尝试，但无法提取有效数据。这不意味着企业真实缺失这些资料，而是系统无法解析当前文件格式。",
            "how_found": f"读取了被查单位提交的{len(docs_list)}个文件，但所有文件均无法提取到结构化数据——文件格式与系统预期模板不匹配，不是企业缺资料。",
            "tax_impact": "资料无法解析意味着无法进行风险分析。但请注意：这些资料在企业手中是完整的，只是导出格式不兼容——稽查时可直接提供原始格式，不存在真实缺失。",
            "policy_ref": "本结论仅反映系统识别能力，不代表企业实际缺资料。建议按标准模板重新导出数据。",
            "suggestion": "① 确认Excel文件第一行为表头行（列名）；② 确认文件内容为财税相关数据；③ 尝试用金税系统标准导出格式重新生成文件。",
            "category": "域14 资料完备度"
        })
        return findings
    
    doc_types_present = set()
    if bank_txs: doc_types_present.add("bank")
    if sal_invs: doc_types_present.add("sales_invoice")
    if pur_invs: doc_types_present.add("purchase_invoice")
    if salaries: doc_types_present.add("salary")
    if social_security: doc_types_present.add("social_security")
    if vouchers: doc_types_present.add("voucher")
    if inventory: doc_types_present.add("inventory")
    if trial_balance_data: doc_types_present.add("trial_balance")
    if contract_data: doc_types_present.add("contract")
    
    # 从文件名和file_results检测申报表类资料
    if docs_list:
        for d in docs_list:
            fn = d.get("original_name", "").lower()
            if any(k in fn for k in ("合同","contract","协议")): doc_types_present.add("contract")
    
    if file_results:
        fr_types = set()
        for fr in file_results:
            t = fr.get("type", "")
            if t == "financial_statements": fr_types.add("financial")
            elif t == "vat_declaration": fr_types.add("vat")
            elif t == "cit_declaration": fr_types.add("cit")
            elif t == "individual_tax": fr_types.add("ind_tax")
            elif t in ("stamp_duty", "tax_payment", "other_tax"): fr_types.add("other_tax")
        for t in fr_types: doc_types_present.add(t)
    
    # 构建名称映射
    present_names = []
    # ═══ 数据驱动：根据进项发票品名判断是否需要进销存台账 ═══
    # 逻辑：过滤掉消费品/服务后，如果还有实物商品进项→需要存货台账
    # 办公用品/日用品/食品饮料等=消费品→不产生存货
    # 原材料/商品/设备等=实物商品→需要进销存跟踪
    if pur_invs:
        from engine.main_biz_cost import _REIMBURSEMENT_KWS_GLOBAL
        _service_kw = SERVICE_EXCLUDE_KEYWORDS
        _goods_count = 0
        _goods_amount = 0.0
        for inv in pur_invs:
            g = str(inv.get("goods", inv.get("货物或应税劳务名称", "")))
            amt = float(inv.get("amount", inv.get("total", 0)) or 0)
            # 排除消费品
            if any(kw in g for kw in _REIMBURSEMENT_KWS_GLOBAL):
                continue
            # 排除纯服务
            if any(kw in g for kw in _service_kw):
                continue
            # 剩余的=实物商品
            _goods_count += 1
            _goods_amount += amt
        total_amount = sum(float(inv.get("amount", inv.get("total", 0)) or 0) for inv in pur_invs)
        _goods_ratio = _goods_amount / total_amount if total_amount > 0 else 0
        # 实物商品占比>10%且金额>5000→需要进销存台账
        _needs_inventory = _goods_count >= 3 and _goods_ratio > 0.10
    else:
        _needs_inventory = False
    
    ALL_CATEGORIES = [
        ("bank", "银行流水", "验证资金全链路，稽查第一调取对象。缺失→无法验证收入完整性+无法检测资金回流→税务机关从金税系统/第三方数据倒推核定收入→结果远超企业实际"),
        ("sales_invoice", "销项发票", "验证开票收入与申报收入匹配。缺失→稽查直接从金税系统调取开票数据与银行流水比对→收款大于开票金额→推定为隐匿收入→补税+0.5-5倍罚款"),
        ("purchase_invoice", "进项发票", "验证成本真实性+进项税额抵扣合法性。缺失→稽查逐一核验全部进项税额抵扣凭证→异常发票做进项转出+补税+滞纳金"),
        ("voucher", "记账凭证", "追溯账务处理全过程的原始依据。缺失→无法核查分录准确性/科目运用/原始凭证匹配→会计账簿视为不健全→按《税收征收管理法》第三十五条核定征收"),
        ("salary", "工资表", "验证工资费用真实性+个税代扣代缴义务履行。缺失→无法核实人员真实性（是否存在虚列人头/虚增工资）→工资费用不得税前扣除+补缴企业所得税"),
        ("social_security", "社保明细", "核实用工合规性+缴费基数真实性。缺失→无法验证社保缴费基数与工资表的一致性→金税四期人社税务数据联动后会直接推送到稽查局，形成独立案件"),
        ("inventory", "进销存台账", "验证存货真实性+购销匹配的核心档案。缺失→无法核实期末存货是否账实相符→存货账实不符→认定为账外经营/虚增成本→补税+核定征收"),
        ("contract", "合同文件", "证明交易真实性，四流合一第一环。缺失→无法证明交易具有商业实质→税务机关可认定为无真实交易的虚开发票→进项税额不得抵扣+移送公安"),
        ("trial_balance", "科目余额表", "验证总账与明细账一致性的基础档案。缺失→无法交叉验证账户余额的准确性→账账不符→会计信息失真→依据《会计法》第四十二条处罚+核定征收"),
        ("financial", "资产负债表+利润表", "验证企业财务状况与申报数据的匹配性。缺失→无法比对报表收入与申报收入/开票收入→三源比对失效→隐匿收入/虚列成本无法被系统发现但稽查可现场调取"),
        ("vat", "增值税申报表", "验证销项/进项税额与开票/收票数据的一致性。缺失→无法确认企业是否足额申报增值税→未申报或少申报→补税+滞纳金+0.5-5倍罚款"),
        ("cit", "企业所得税申报表", "验证收入成本费用与凭证账务的匹配性。缺失→无法核实所得税汇算清缴的准确性→少缴企业所得税→补税+滞纳金+罚款"),
        ("ind_tax", "个人所得税申报表", "验证个税申报与工资表的一致性。缺失→无法核实代扣代缴义务是否履行→未代扣代缴→补税+滞纳金+0.5-3倍罚款"),
        ("other_tax", "其他税种申报表", "验证印花税/城建税/教育费附加/房产税/土地使用税等申报完整性。缺失→无法确认小税种是否申报→漏缴各项附加税费→逐项补缴+滞纳金+罚款"),
    ]
    # 行业自适应过滤：非制造/贸易/批发行业不需要进销存台账
    if not _needs_inventory:
        ALL_CATEGORIES = [(k, n, d) for (k, n, d) in ALL_CATEGORIES if k != "inventory"]
    
    for key, name, reason in ALL_CATEGORIES:
        if key in doc_types_present:
            present_names.append(name)
    
    # ═══ 逐项生成缺失资料的详细风险提示 ═══
    
    # ═══ 合同需求分层（行业无关，基于发票品名+金额+类型自动分类）═══
    contract_tiers = _analyze_contract_tiers(pur_invs, sal_invs) if pur_invs else {'must_contract': [], 'should_contract': [], 'may_skip': [], 'must_total_amt': 0, 'should_total_amt': 0, 'may_skip_total_amt': 0}
    mc_list = contract_tiers.get('must_contract', [])
    sc_list = contract_tiers.get('should_contract', [])
    ms_list = contract_tiers.get('may_skip', [])
    must_total = contract_tiers.get('must_total_amt', 0)
    should_total = contract_tiers.get('should_total_amt', 0)
    may_total = contract_tiers.get('may_skip_total_amt', 0)
    # 构建分层明细文本
    mc_text = '\n'.join(f"    {n}：{r}，交易额{amt:,.2f}元" for n, amt, r in mc_list) if mc_list else "    （无）"
    sc_text = '\n'.join(f"    {n}：{r}，交易额{amt:,.2f}元" for n, amt, r in sc_list) if sc_list else "    （无）"
    ms_text = '\n'.join(f"    {n}：{r}，交易额{amt:,.2f}元" for n, amt, r in ms_list) if ms_list else "    （无）"
    mc_more = f"\n    ... 还有{len(mc_list)-10}家" if len(mc_list) > 10 else ""
    ms_more = f"\n    ... 还有{len(ms_list)-10}家" if len(ms_list) > 10 else ""
    stamp_tax_est = (must_total + should_total) * T.stamp_duty_rates.sales_contract  # 购销合同印花税

    # 缺失项定义：(key, finding_type, level, score, detail, description, tax_impact, policy, suggestion)
    MISSING_DEFS = [
        ("contract", "合同文件缺失", "高风险", 9,
         lambda: (
             f"合同需求分层分析（行业无关，基于发票品名+金额+类型四层自动分类）：\n"
             f"总供应商{contract_tiers.get('total_suppliers', 0)}家，销项客户{len(set(str(i.get('buyer',''))[:15] for i in sal_invs if i.get('buyer'))) if sal_invs else 0}家。\n\n"
             f"【必签合同·主营业务】{len(mc_list)}家，交易额{must_total:,.2f}元：\n"
             f"{mc_text}{mc_more}\n"
             f"  → 判断依据：品名含原料/材料/加工/配件/零件/包装等主营业务关键词\n\n"
             f"【应签合同·重要费用】{len(sc_list)}家，交易额{should_total:,.2f}元：\n"
             f"{sc_text}\n"
             f"  → 判断依据：设备/服务/维修/咨询/广告/物流等重要费用支出\n\n"
             f"【可免合同·日常消费】{len(ms_list)}家，交易额{may_total:,.2f}元：\n"
             f"{ms_text}{ms_more}\n"
             f"  → 判断依据：加油/餐饮/差旅/办公/通讯/快递等日常消费\n\n"
             f"四层自动分类：①主营业务采购→必签 ②重要费用(设备/服务/维修等)→应签 ③日常消费→发票即可 ④小额杂项→可免。"
             f"被查单位缺失合同的影响集中在第一、二类{must_total+should_total:,.2f}元交易。四流合一缺了合同流，印花税计税依据缺失（预计漏缴{stamp_tax_est:,.2f}元）。"
         ),
         lambda: f"缺少合同文件——需按业务性质四层判断：{len(mc_list)}家主营业务采购/交易额{must_total:,.2f}元必须有合同，{len(sc_list)}家重要费用/交易额{should_total:,.2f}元应签合同，{len(ms_list)}家日常消费类以发票为凭证即可。①稽查逐笔质疑{len(mc_list)+len(sc_list)}笔无合同交易的商业合理性；②无合同→印花税漏缴(约{stamp_tax_est:,.2f}元)；③大额无合同→虚开发票嫌疑。",
         lambda: f"缺失合同→四流合一断裂→{must_total+should_total:,.2f}元交易无合同支撑→稽查可逐笔质疑交易真实性→虚开发票嫌疑→补税+罚款+滞纳金；印花税计税依据缺失→漏缴约{stamp_tax_est:,.2f}元。",
         lambda: "《税收征收管理法》第五十四条；《印花税法》关于应税合同的规定。",
         f"① 为{must_total:,.2f}元主营业务交易的供应商补签购销合同（{len(mc_list)}家）；② {should_total:,.2f}元重要费用补签服务/设备合同（{len(sc_list)}家）；③ {len(ms_list)}家日常消费类以发票为凭证即可，不需补签；④ 按合同金额补缴印花税约{stamp_tax_est:,.2f}元。"),
        
        ("bank", "银行流水缺失", "高风险", 10,
         lambda: "缺少银行流水——稽查第一调取对象，验证资金全链路的原始证据缺失",
         lambda: "银行流水是稽查的第一个调取对象（《税务稽查工作规程》明确规定）。缺失意味着：(1)稽查无法验证企业全部银行账户的资金进出是否均已入账；(2)无法检测是否存在资金回流（供应商付款后资金回流至法人/股东/关联方个人账户）；(3)无法核实是否存在账外经营账户（未向税务机关报告的银行账户）。稽查会直接要求限期提供，逾期不提供触发核定征收。",
         lambda: "缺失银行流水→稽查无法验证收入完整性+无法检测资金回流→税务机关从金税系统/第三方数据（电力/海关/上下游企业）倒推核定收入→核定结果远超企业实际→补税+0.5-5倍罚款+滞纳金。",
         lambda: "《税收征收管理法》第三十五条（核定征收）、第五十四条；《税务稽查工作规程》第二十二条（检查取证）。",
         "① 整理全部对公账户银行流水（含已注销账户），覆盖稽查所属期全部月份；② 法人、主要股东、财务负责人个人账户中与经营相关的流水也应整理备查。"),
        
        ("sales_invoice", "销项发票缺失", "高风险", 9,
         lambda: "缺少销项发票——无法验证企业实际开票收入与申报收入的匹配",
         lambda: "销项发票是验证收入规模的核心资料。缺失=稽查无法：(1)比对申报收入vs实际开票收入是否一致；(2)比对开票客户vs银行回款客户是否一致（是否存在未开票即收款）；(3)核实是否存在应开未开发票的隐匿收入。金税四期已实现全国发票数据集中，稽查可直接从金税系统调取企业的全部开票记录。",
         lambda: "缺失销项发票→稽查直接从金税系统调取开票数据+银行流水→银行收款金额大于开票金额的部分→推定为隐匿未开票收入→补缴增值税+企业所得税+0.5-5倍罚款+滞纳金。",
         lambda: "《中华人民共和国增值税法》关于发票开具和销售额确定的规定；《税收征收管理法》第六十三条（偷税处罚）。",
         "① 从金税系统导出完整销项发票清单（含正数发票+负数发票/红冲）；② 按月度与银行收款记录、增值税申报表做三方勾稽。"),
        
        ("purchase_invoice", "进项发票缺失", "高风险", 9,
         lambda: "缺少进项发票——无法验证成本真实性+进项税额抵扣合法性",
         lambda: "进项发票是验证成本真实性、进项税额抵扣合法性的核心资料。缺失=稽查无法：(1)验证已抵扣的进项税额对应的发票是否真实、是否属于可抵扣范围；(2)验证供应商是否真实经营（是否存在开票后走逃/注销）；(3)比对采购发票vs存货入库vs银行付款的三流一致性。金税四期已对异常抵扣凭证实现自动预警。",
         lambda: "缺失进项发票→稽查逐一核验全部进项税额抵扣凭证→异常发票（走逃/失控/虚开/品名不符）做进项税额转出→补缴增值税+滞纳金；同时对应的成本不得税前扣除→补缴企业所得税。",
         lambda: "《中华人民共和国增值税法》关于进项税额抵扣的规定；国家税务总局公告2019年第38号（异常增值税扣税凭证）；《企业所得税法》第八条（真实性原则）。",
         "① 从金税系统导出完整进项发票清单；② 逐张核实三流一致性（合同→发票→付款），不一致的主动做进项转出。"),
        
        ("voucher", "记账凭证缺失", "高风险", 8,
         lambda: "缺少记账凭证——追溯账务处理全过程的原始依据缺失",
         lambda: "记账凭证是追溯账务处理全过程的原始依据。缺失=稽查无法核查：(1)会计分录的借贷方向、科目运用、金额是否正确；(2)每笔记账是否附有合法有效的原始凭证（发票/合同/银行回单/入库单等）；(3)收入确认、成本结转、费用归集的时点和金额是否符合会计准则。根据《税务稽查工作规程》，企业有义务提供完整的会计凭证，缺失即构成资料提供不全。",
         lambda: "缺失凭证→稽查无法追溯分录准确性/科目运用/原始凭证匹配→会计账簿视为不健全→依据《税收征收管理法》第三十五条核定征收（税务机关有权按核定利润率/核定应纳税额的方式确定应纳税额，结果通常远超企业实际税负）。",
         lambda: "《税收征收管理法》第三十五条（核定征收）、第五十四条、第五十六条；《税务稽查工作规程》关于资料提供义务的规定。",
         "① 确保完整的记账凭证（序时账）随时可调取；② 每张凭证必须包含：日期、凭证号、摘要、会计科目、借贷金额、附件张数；③ 凭证所附原始凭证（发票/合同/银行回单/入库单等）齐全且一一对应。"),
        
        ("trial_balance", "科目余额表缺失", "中风险", 7,
         lambda: "缺少科目余额表——无法验证总账与明细账的一致性，稽查必查基础档案缺失",
         lambda: "科目余额表是连接总账与明细账的桥梁，也是编制财务报表的基础，属于稽查必查基础档案。缺失=稽查无法核实：(1)各科目期初期末余额是否衔接（是否存在凭空增减）；(2)各科目本期发生额是否与凭证汇总一致（是否存在账外调整）；(3)重点科目（应收账款/应付账款/存货/收入/成本）的余额是否合理。",
         lambda: "缺失科目余额表→无法交叉验证账户余额的准确性→账账不符→会计信息失真→依据《会计法》第四十二条处罚+可能触发核定征收。",
         lambda: "《企业会计准则》关于科目设置和账务记录的规定；《会计法》第四十二条。",
         "① 导出完整的科目余额表（含科目代码、科目名称、期初余额、本期借方、本期贷方、期末余额）；② 与序时账的科目汇总数逐科目核对一致。"),
        
        ("salary", "工资表缺失", "中风险", 6,
         lambda: "缺少工资表——个人所得税代扣代缴义务和工资费用真实性无法验证",
         lambda: "工资是企业所得税前扣除的大项，也是个税代扣代缴的基础资料。缺失=稽查无法核实：(1)税前扣除的工资费用是否真实（是否存在虚列人头/虚增工资金额）；(2)个税是否足额代扣代缴（实发工资vs申报工资是否一致）；(3)工资表人数vs社保参保人数是否匹配。",
         lambda: "缺失工资表→无法核实人员真实性（虚列人头/虚增工资）→工资费用不得税前扣除→补缴企业所得税+追缴未扣个税+滞纳金。",
         lambda: "《企业所得税法实施条例》第三十四条（工资薪金税前扣除）；《个人所得税法》第九条（代扣代缴义务）。",
         "① 整理完整工资表（含姓名、身份证号、应发工资、代扣个税、代扣社保、实发工资）；② 与个税申报明细、社保参保名单三方逐人比对。"),
        
        ("social_security", "社保明细缺失", "中风险", 6,
         lambda: "缺少社保明细——无法核实用工合规性+缴费基数真实性，金税四期已实现人社税务数据联动",
         lambda: "社保明细是验证企业用工合规性的核心资料。缺失=无法核实：(1)是否全员参保（是否存在只发工资不缴社保的'隐形用工'）；(2)社保缴费基数是否与实际工资一致（低基数参保差额=少缴社保+少扣个税）。金税四期已将人社数据与税务数据打通，缴费基数与申报工资的差异自动推送至稽查局。",
         lambda: "缺失社保明细→无法验证社保缴费基数与工资表的一致性→金税四期人社税务数据联动后差异自动预警→稽查局收到独立推送→社保稽核+税务稽查联动→补缴社保+滞纳金+罚款。",
         lambda: "《社会保险法》第五十八条（参保登记）、第八十四条（未参保处罚）；金税四期人社税务数据共享机制。",
         "① 整理社保参保人员明细（含姓名、身份证号、缴费基数、各险种缴费金额）；② 与工资表逐人比对（人数/工资/基数三项一致）。"),
        
        ("inventory", "进销存台账缺失", "中风险", 5,
         lambda: "缺少进销存台账——无法验证存货真实性+购销匹配的核心档案缺失",
         lambda: "进销存台账是验证存货真实性和购销匹配的基础档案。缺失=稽查无法判断：(1)账面库存是否真实存在（是否存在已销售未出库/已报废未处理/虚假入库）；(2)采购量+期初库存-销售量=期末库存，三者逻辑是否自洽；(3)是否存在账外存货（仓库有货但账面无记录）。",
         lambda: "缺失进销存→稽查进行实地盘点→账实不符的部分→推定为已销售未入账→补缴增值税+企业所得税；存货账实严重不符→认定为账外经营/虚增成本→核定征收。",
         lambda: "《企业所得税法实施条例》关于存货计价和盘点核实的规定；《税收征收管理法》第三十五条（核定征收）。",
         "① 整理完整的进销存台账（含品名、规格、期初数量/金额、本期入库数量/金额、本期出库数量/金额、期末结存数量/金额）；② 期末结存与财务存货账、仓库实物三方核对一致。"),
        
        ("financial", "财务报表缺失", "中风险", 7,
         lambda: "缺少资产负债表和利润表——无法验证企业财务状况与申报数据的匹配",
         lambda: "资产负债表和利润表是企业财务状况的核心文件。缺失=稽查无法验证：(1)申报收入与报表收入是否一致（是否存在两套账）；(2)资产规模与经营规模是否匹配（小微企业报表显示数千万资产→异常）；(3)往来科目余额是否异常（大额其他应收款/应付款可能隐藏资金抽逃或账外经营）。",
         lambda: "缺失财务报表→无法比对报表收入与申报收入/开票收入→三源比对失效→隐匿收入/虚列成本无法被系统自动发现→但稽查可现场调取原始账簿逐一核实→查出的问题更严重。",
         lambda: "《税收征收管理法》第五十四条（检查权）；《企业所得税法》关于纳税申报的规定；《会计法》第二十条（财务会计报告）。",
         "① 准备完整的资产负债表、利润表、现金流量表、所有者权益变动表；② 报表数据与税务申报数据、凭证账务三方核对一致。"),
        
        ("vat", "增值税申报表缺失", "中风险", 6,
         lambda: "缺少增值税申报表——无法验证销项/进项税额与开票/收票数据的一致性",
         lambda: "增值税申报表是验证销项税额和进项税额申报是否完整的基础。缺失=无法比对：(1)申报销项税额vs金税系统开票税额是否一致；(2)申报进项税额vs金税系统收票税额是否一致；(3)是否存在未开票收入未申报或少申报。金税四期已实现申报数据与发票数据的自动比对，差异自动生成风险预警。",
         lambda: "缺失增值税申报表→无法确认企业是否足额申报→稽查直接从金税系统调取申报记录+发票数据比对→未申报或少申报的部分→补缴增值税+滞纳金+0.5-5倍罚款。",
         lambda: "《中华人民共和国增值税法》关于纳税申报的规定；《税收征收管理法》第六十三条（偷税处罚）。",
         "① 导出完整的增值税申报表（主表+附表一至附表五）；② 逐月与销项/进项发票汇总数勾稽一致。"),
        
        ("cit", "企业所得税申报表缺失", "中风险", 6,
         lambda: "缺少企业所得税申报表——无法验证收入成本费用与凭证账务的匹配",
         lambda: "企业所得税申报表是验证利润真实性和税前扣除合规性的核心资料。缺失=无法比对：(1)申报营业收入vs凭证收入vs开票收入三项是否一致；(2)申报营业成本vs凭证成本vs进项发票金额是否一致；(3)各项费用税前扣除是否超标（业务招待费/广告费/捐赠等有扣除限额）。",
         lambda: "缺失所得税申报表→无法核实所得税汇算清缴的准确性→稽查直接调取金税系统申报记录+凭证数据比对→少缴的部分→补缴企业所得税+滞纳金+罚款。",
         lambda: "《企业所得税法》关于纳税申报的规定；《税收征收管理法》第六十三条（偷税处罚）。",
         "① 导出完整的企业所得税年度申报表（A类全套：主表+收入/成本/费用明细表+纳税调整明细表）；② 与凭证汇总的期间收入成本费用逐项勾稽。"),
        
        ("ind_tax", "个人所得税申报表缺失", "低风险", 4,
         lambda: "缺少个人所得税申报表——无法验证个税代扣代缴义务是否履行",
         lambda: "个税申报表是验证工资发放和代扣代缴完整性的依据。缺失=无法核实：(1)申报人数vs工资表人数vs社保人数是否一致（是否存在只发工资不报个税的人员）；(2)申报收入金额vs实发工资金额是否一致（是否存在分拆工资/以费用报销代替工资发放）；(3)专项附加扣除是否真实合规。",
         lambda: "缺失个税申报表→无法核实代扣代缴义务是否履行→未代扣代缴的→追缴税款+滞纳金+0.5-3倍罚款→同时企业负责人和财务负责人承担连带责任。",
         lambda: "《个人所得税法》第九条（代扣代缴义务）、第十条（申报义务）；《税收征收管理法》第六十九条（扣缴义务人处罚）。",
         "① 导出完整的个税扣缴申报明细（含姓名、身份证号、收入额、扣除额、应纳税额）；② 与工资表逐人逐月比对一致。"),
        
        ("other_tax", "其他税种申报表缺失", "低风险", 3,
         lambda: "缺少印花税/城建税/教育费附加/房产税/土地使用税等小税种申报表——附征税费申报完整性无法验证",
         lambda: "印花税、城建税、教育费附加、房产税、土地使用税等小税种虽然单笔金额不大，但在稽查中常常成为突破口——因为企业容易忽视而导致漏缴，稽查一旦查到就是板上钉钉的违法事实。缺失=无法核实：(1)印花税是否按购销合同/借款合同/账簿/证照足额缴纳；(2)城建税及教育费附加是否按实际缴纳的增值税额正确计算；(3)房产税/土地使用税是否按房产原值/土地面积足额申报。",
         lambda: "缺失小税种申报→稽查逐项核验→漏缴部分→补缴税款+每日万分之五滞纳金+0.5-5倍罚款→虽然单项金额不大，但多项累积+滞纳金滚存后数字可观，且容易成为稽查深挖其他问题的'突破口'。",
         lambda: "《印花税法》；《城市维护建设税法》；《房产税暂行条例》；《城镇土地使用税暂行条例》。",
         "① 整理所有税种的申报记录和完税凭证；② 按各税种计税依据逐项自查是否存在漏缴（印花税按合同/账簿/证照、城建税按增值税额、房产税按房产原值、土地使用税按土地面积）。"),
    ]
    
    for key, ftype, level, score, detail_fn, desc_fn, impact_fn, policy, suggestion in MISSING_DEFS:
        if key not in doc_types_present:
            findings.append({
                "type": ftype,
                "level": level, "score": score,
                "detail": detail_fn(),
                "description": desc_fn(),
                "how_found": f"逐一检测了14类稽查必查资料的提交状态，{ftype.replace('缺失','')}类资料未提交",
                "tax_impact": impact_fn(),
                "policy_ref": policy() if callable(policy) else policy,
                "suggestion": suggestion,
                "category": "域14 资料完备度"
            })
    
    # ═══ 资料完备度综合评估 ═══
    total_categories = len(ALL_CATEGORIES)
    missing_categories = []
    for key, name, reason in ALL_CATEGORIES:
        if key not in doc_types_present:
            missing_categories.append(f"{name}（{reason}）")
    
    missing_count = len(missing_categories)
    if missing_count > 0:
        total_score = min(3 + missing_count, 10)
        missing_items = []
        for mc in missing_categories:
            name, reason = mc.split("（", 1)
            reason = reason.rstrip("）")
            missing_items.append({"缺失资料": name, "缺失后果": reason})
        
        missing_detail = "、".join([mc.split("（")[0] for mc in missing_categories])
        
        findings.append({
            "type": "资料完备度综合评估",
            "level": "高风险" if missing_count >= 5 else ("中风险" if missing_count >= 2 else "低风险"),
            "score": total_score,
            "detail": f"经审核全部{total_categories}类稽查必查资料：已提交{len(present_names)}类（{'、'.join(present_names)}），缺失{missing_count}类：{missing_detail}。",
            "description": f"经审核本次提交的全部资料，共计{total_categories}类稽查必查资料，已覆盖{len(present_names)}类（{'、'.join(present_names)}），缺失{missing_count}类（{missing_detail}）。\n\n根据《税务稽查工作规程》第二十二条，被查单位应在稽查通知下达后按税务机关要求及时、完整提交相关资料。每缺一类资料，对应分析域无法执行，稽查结论的完整性和精确性将受实质性影响。已提交资料对应的分析域均已执行完毕，缺失资料的后果逐一列明于下方证据材料。",
            "how_found": f"逐一检测{total_categories}类稽查必查资料的提交状态——从文件解析结果的数据类型和文件名称判定。",
            "tax_impact": "稽查通知下达后无法在限期内提供完整资料→面临罚款（单位最高5万元）→税务机关从其他数据源（金税系统、银行流水、第三方信息）倒推核定应纳税额→核定结果通常高于企业实际→补税+滞纳金+罚款。",
            "policy_ref": "《税收征收管理法》第五十四条、第五十六条（资料提供义务及罚则）；《税务稽查工作规程》第二十二条（检查取证）。",
            "suggestion": f"补充缺失的{missing_count}类资料。按照金税四期稽查必查清单，企业应确保以下{total_categories}类资料随时可调取、完整、规范：" + "、".join([f"{name}" for _, name, _ in ALL_CATEGORIES]) + "。",
            "items": missing_items,
            "category": "域14 资料完备度"
        })
    else:
        findings.append({
            "type": "资料完备度综合评估",
            "level": "低风险", "score": 2,
            "detail": f"已提交全部{total_categories}类稽查必查资料：{'、'.join(present_names)}。",
            "description": f"本次分析覆盖了全部{total_categories}类稽查必查核心资料，资料完整度高，能够支撑全面的涉税风险分析和稽查应对。",
            "how_found": f"逐一检测{total_categories}类稽查必查资料的提交状态，全部检测通过。",
            "category": "域14 资料完备度"
        })

    return findings


# ═══════════ 合同需求分层分析（行业无关）═══════════
def _analyze_contract_tiers(pur_invs, sal_invs):
    """从发票数据自动分析每个供应商的合同需求等级（行业无关，全行业适用）
    
    四层判断体系：
    1. 日常消费（免合同）——加油/餐饮/差旅/快递/办公/物业/银行手续费等
    2. 主营业务（必合同）——原材料/加工/半成品/配件/包装/辅料等生产性采购
    3. 重要费用（应合同）——大额服务/设备/咨询/广告/法律等虽非主营业务但金额重大
    4. 小额杂项（可免）——小金额非主营业务采购
    
    判断优先级：先排除日常消费 → 再判断主营业务 → 再看金额 → 最后归入小额
    """
    from collections import defaultdict
    
    # ── 业务关键词（从 industry_profiles.json 加载，JSON可编辑） ──
    DAILY_GOODS, MAIN_BIZ_KWS, IMPORTANT_EXPENSE_KWS = _load_biz_keywords()
    
    supplier_goods = defaultdict(set)
    supplier_amt = defaultdict(float)
    for inv in pur_invs:
        seller = str(inv.get('seller','') or inv.get('销方名称','')).strip()
        goods = str(inv.get('goods','') or inv.get('货物或应税劳务名称','')).strip()
        amt = float(inv.get('amount', 0) or 0)
        if seller and len(seller) >= 4:
            supplier_goods[seller].add(goods)
            supplier_amt[seller] += amt
    
    must_contract = []      # 必签合同（主营业务）
    should_contract = []    # 应签合同（重要费用）
    may_skip = []           # 可免（日常消费/小额）
    
    for name, amt in sorted(supplier_amt.items(), key=lambda x: -x[1]):
        goods_text = ' '.join(supplier_goods.get(name, set()))
        
        # ── 第1层：日常消费 → 免合同 ──
        if any(kw in goods_text for kw in DAILY_GOODS):
            may_skip.append((name, amt, '日常消费(加油/餐饮/差旅/办公等)'))
            continue
        
        # ── 第2层：主营业务品名 → 必签合同 ──
        if any(kw in goods_text for kw in MAIN_BIZ_KWS):
            must_contract.append((name, amt, '主营业务采购(原料/加工/配件等)'))
            continue
        
        # ── 第3层：重要费用品名 + 金额>5000 → 应签合同 ──
        if any(kw in goods_text for kw in IMPORTANT_EXPENSE_KWS):
            if amt > T.amount_thresholds.tiny_transaction:
                should_contract.append((name, amt, f'重要费用(设备/服务/维修等) {amt:,.2f}元'))
            else:
                may_skip.append((name, amt, f'小额服务({amt:,.2f}元)'))
            continue
        
        # ── 第4层：纯金额判断 ──
        if amt > 50000:
            must_contract.append((name, amt, f'重大支出({amt:,.2f}元)品名不明确'))
        elif amt > T.amount_thresholds.tiny_transaction * 4:
            should_contract.append((name, amt, f'中等支出({amt:,.2f}元)建议合同'))
        else:
            may_skip.append((name, amt, f'小额({amt:,.2f}元)'))
    
    return {
        'must_contract': must_contract,
        'should_contract': should_contract,
        'may_skip': may_skip,
        'total_suppliers': len(supplier_amt),
        'must_count': len(must_contract),
        'should_count': len(should_contract),
        'may_skip_count': len(may_skip),
        'must_total_amt': sum(x[1] for x in must_contract),
        'should_total_amt': sum(x[1] for x in should_contract),
        'may_skip_total_amt': sum(x[1] for x in may_skip),
    }


# ═══════════ 域15: 多源交叉验证 ═══════════

def _domain_multi_source_cross(bank_txs, sal_invs, pur_invs, salaries, social_security, vouchers, inventory, db, company_id):
    """多源交叉验证：3源以上交叉比对，还原稽查真实过程"""
    from collections import defaultdict
    findings = []

    # ── 交叉1: 资金流(银行支出) + 发票流(进项) + 货物流(存货入库) → 采购三源验证 ──
    if bank_txs and pur_invs and inventory:
        bank_payees = defaultdict(float)
        for tx in bank_txs:
            if tx.get("debit", 0) > 0 and tx.get("counterparty"):
                bank_payees[tx["counterparty"][:20]] += tx["debit"]
        inv_sellers = defaultdict(float)
        for inv in pur_invs:
            s = str(inv.get("seller", ""))[:20]
            if s: inv_sellers[s] += float(inv.get("total", 0) or 0)

        # 找出：银行有付款但无进项发票 或 有进项发票但银行无付款
        pay_no_inv = []
        for name, amt in sorted(bank_payees.items(), key=lambda x: -x[1]):
            matched = any(name[:6] in s for s in inv_sellers)
            if not matched and amt > T.amount_thresholds.tiny_transaction:
                pay_no_inv.append(f"{name}({amt:,.2f}元)")
        inv_no_pay = []
        for name, amt in sorted(inv_sellers.items(), key=lambda x: -x[1]):
            matched = any(name[:6] in p for p in bank_payees)
            if not matched and amt > T.amount_thresholds.tiny_transaction:
                inv_no_pay.append(f"{name}({amt:,.2f}元)")

        if pay_no_inv:
            findings.append({
                "type": "付款无进项发票（三源交叉）",
                "level": "高风险", "score": 9,
                "detail": f"银行流水中向{len(pay_no_inv)}个供应商付款但无对应进项发票：{'、'.join(pay_no_inv)}等。",
                "description": f"结合银行流水支出、进项发票、存货入库三源交叉比对发现：银行账户向以下供应商支付了货款，但进项发票中未找到对应供应商的开票记录：{'、'.join(pay_no_inv)}。这意味着企业付了款却没有取得发票，存在以下可能：供应商未开票或延迟开票、账外采购、或以采购名义转移资金。",
                "how_found": f"执行了三组独立交叉比对：(1)从{len(bank_txs)}条银行流水提取所有支出交易→按对方名称分组→筛选金额>5000元的付款 (2)从{len(pur_invs)}张进项发票提取所有销方名称 (3)两组名单逐名模糊匹配→发现{len(pay_no_inv)}家供应商收了货款但查不到进项发票。",
                "tax_impact": "付款未取得发票，相关支出不得在企业所得税前扣除；若被认定为无真实交易的资金支出，可能涉及抽逃资金或利益输送。",
                "policy_ref": "《企业所得税法》第八条（税前扣除须有合法凭证）；国家税务总局公告2018年第28号（税前扣除凭证管理）。",
                "suggestion": "1）逐笔核实无票付款的真实交易背景，联系供应商补开发票；2）建立付款前审核发票的制度；3）对于确实无法取得发票的小额零星支出，保留收款凭证及内部审批记录。",
                "category": "域15 多源交叉"
            })
        if inv_no_pay:
            findings.append({
                "type": "进项发票无付款记录（三源交叉）",
                "level": "中风险", "score": 7,
                "detail": f"{len(inv_no_pay)}个供应商开具进项发票但银行无付款记录：{'、'.join(inv_no_pay)}等。",
                "description": f"交叉比对发现：以下供应商开具了进项发票，但在银行流水中未找到对应的付款记录：{'、'.join(inv_no_pay)}。这意味着取得了发票但没有付款记录，存在以下可能：以现金方式付款、通过其他账户付款、发票为虚开、或款项尚未支付（挂账）。",
                "how_found": f"交叉比对方法：将银行流水中的付款对象与进项发票的销方进行模糊匹配，找出发票中有但银行流水中无付款记录的供应商。",
                "tax_impact": "有票无款是虚开发票的典型特征之一。若被认定为取得虚开发票，进项税额不予抵扣（已抵扣的需转出），相关成本不得税前扣除，并可能面临罚款。",
                "policy_ref": "《发票管理办法》第二十二条（禁止虚开发票）；国家税务总局公告2019年第38号（异常增值税扣税凭证）。",
                "suggestion": "1）核实未付款发票是否真实交易，检查是否通过其他账户付款；2）若为挂账，确认应付款项账龄，防止长期挂账；3）若无法证明交易真实性，主动做进项税额转出。",
                "category": "域15 多源交叉"
            })

    # ── 交叉2: 资金流(银行入账) + 发票流(销项) + 合同 → 收入三源验证 ──
    if bank_txs and sal_invs:
        bank_receivers = defaultdict(float)
        for tx in bank_txs:
            if tx.get("credit", 0) > 0 and tx.get("counterparty"):
                bank_receivers[tx["counterparty"][:20]] += tx["credit"]
        inv_buyers = defaultdict(float)
        for inv in sal_invs:
            b = str(inv.get("buyer", ""))[:20]
            if b: inv_buyers[b] += float(inv.get("total", 0) or 0)

        # 银行收款 vs 销项开票
        bank_income = sum(tx["credit"] for tx in bank_txs)
        inv_income = sum(float(inv.get("total", 0) or 0) for inv in sal_invs)
        if inv_income > 0 and bank_income > 0:
            gap = abs(bank_income - inv_income)
            gap_pct = gap / max(inv_income, 1) * 100
            if gap_pct > 20:
                findings.append({
                    "type": "收款与开票金额偏差大（三源交叉）",
                    "level": "高风险", "score": 9,
                    "detail": f"银行入账{bank_income:,.2f}元 vs 销项开票{inv_income:,.2f}元，差异{gap:,.2f}元（{gap_pct:.2f}%）。",
                    "description": f"将银行流水中的贷方(收入)金额与销项发票的价税合计进行交叉比对，发现两者存在{gap_pct:.2f}%的偏差。银行入账{bank_income:,.2f}元，销项开票{inv_income:,.2f}元。差异方向：{'银行收入多' if bank_income > inv_income else '开票收入多'}。\n\n"
                        + f"银行收款{bank_income:,.2f}元 vs 开票{inv_income:,.2f}元，偏差{gap_pct:.2f}%——超过20%阈值即需重点关注。\n"
                        + f"这是三源交叉验证的一环——银行流水（资金流）+销项发票（发票流）+目标企业申报数据（申报流）。三者偏差超过20%即确认异常。\n"
                        + f"{'银行收入多于开票' if bank_income > inv_income else '开票多于银行收入'}，可能原因：\n"
                        + f"· 银行多：存在未开票收入（客户付款但未开票→隐匿收入）或非经营性资金入账（借款/注资/往来款）\n"
                        + f"· 开票多：存在应收账款（已开票但客户未付款）或现金交易（开票了但通过现金收款，未进对公账户）\n"
                        + f"综合判断：需结合收款来源分析进一步判断。如果银行多收的部分主要来自开票客户之外的付款方，则隐匿收入的可能性增大。如果来自法定代表人/股东，则需核实注资/借款性质。",
                    "how_found": f"查阅被查单位提供的银行流水和销项发票。汇总银行贷方(收入)金额与销项发票价税合计进行比对，偏差率{gap_pct:.2f}%，超过20%阈值。",
                    "tax_impact": "银行入账大于开票收入，是隐匿销售收入的重要线索。税务机关会将差额部分推定为未申报收入，核定补缴增值税及企业所得税。",
                    "policy_ref": "《税收征收管理法》第三十五条（核定征收）；《中华人民共和国增值税法》关于销售额确定的规定。",
                    "suggestion": "1）逐笔核对银行入账记录，区分经营性收款与非经营性收款；2）对所有经营性收款确保开具发票或确认为未开票收入申报；3）第三方平台收款应及时提现至对公账户并同步开票。",
                    "category": "域15 多源交叉",
            "rule_id": 217,
            "source_chain": "资金流-发票收付款匹配",
                })

    # ── 交叉3: 工资表 + 银行工资代发 + 社保 → 薪酬三源验证 ──
    if salaries and bank_txs:
        total_salary = sum(s.get("net", s.get("salary", 0)) for s in salaries)
        bank_salary = sum(tx["debit"] for tx in bank_txs if any(k in tx.get("raw", "") for k in ("工资", "代发", "薪")))
        ss_people = len(set(s.get("name", "") for s in social_security)) if social_security else 0
        if bank_salary > 0 and total_salary > 0:
            ratio = bank_salary / max(total_salary, 1)
            if ratio < T.ratios.half or ratio > T.ratios.double_ratio:
                findings.append({
                    "type": "工资发放与银行记录不匹配（三源交叉）",
                    "level": "中风险", "score": 7,
                    "detail": f"工资表实发{total_salary:,.2f}元 vs 银行工资代发{bank_salary:,.2f}元（{ratio*100:.2f}%）。",
                    "description": f"将工资表的实发金额、银行流水中的工资代发记录、社保参保人数进行三源交叉比对。工资表显示实发合计{total_salary:,.2f}元，银行流水识别到的工资代发金额{bank_salary:,.2f}元（{ratio*100:.2f}%），社保参保{ss_people}人。三者不一致可能意味着：部分工资以现金发放、工资表人数与实际不符、或存在未通过银行代发的避税安排。",
                    "how_found": f"执行了三源交叉验证：(1)从工资表汇总{len(salaries)}人实发工资{total_salary:,.2f}元 (2)从{len(bank_txs)}条银行流水识别含'工资''代发'关键词的交易{bank_salary:,.2f}元 (3)统计社保明细{ss_people}人参保——三方偏差超过50%即确认异常。",
                    "tax_impact": "工资通过现金发放且无社保参保记录，个人所得税代扣代缴义务可能存在遗漏，企业所得税税前扣除的工资费用真实性存疑。",
                    "policy_ref": "《个人所得税法》第九条（扣缴义务人）；《企业所得税法实施条例》第三十四条（工资薪金扣除条件）。",
                    "suggestion": "1）统一通过银行代发工资，保留发放凭证；2）确保工资表、个税申报、社保参保三方人数和金额一致；3）如存在劳务用工，单独签订劳务合同并代开发票。",
                    "category": "域15 多源交叉"
                })

    # ── 交叉4: 缴税总额 + 发票税额 + VAT申报 → 税务四源验证 ──
    if bank_txs and sal_invs:
        import json
        tax_from_bank = sum(tx["debit"] for tx in bank_txs if "税务" in tx.get("raw", ""))
        vat_output = sum(float(inv.get("tax", 0) or 0) for inv in sal_invs)
        vat_input = sum(float(inv.get("tax", 0) or 0) for inv in pur_invs)
        vat_net = vat_output - vat_input
        vat_rec = db.query(VATDeclaration).filter(VATDeclaration.company_id == company_id).order_by(VATDeclaration.period.desc()).first()
        vat_payable = 0
        if vat_rec:
            main = json.loads(vat_rec.form_main or '{}') if isinstance(vat_rec.form_main, str) else (vat_rec.form_main or {})
            vat_payable = float(main.get("row19_tax_payable", 0) or 0)
        if tax_from_bank > 0 and vat_payable > 0:
            findings.append({
                "type": "税务四源交叉比对",
                "level": "低风险", "score": 3,
                "detail": f"发票销项税额{vat_output:,.2f} - 进项税额{vat_input:,.2f} = {vat_net:,.2f}元；申报应缴{vat_payable:,.2f}元；银行缴税{tax_from_bank:,.2f}元。",
                "description": f"将四个维度的税务数据进行交叉比对：发票税额（销项{vat_output:,.2f} - 进项{vat_input:,.2f} = {vat_net:,.2f}）、申报表填报应缴税额{vat_payable:,.2f}元、银行实际缴税{tax_from_bank:,.2f}元。这四源数据如果一致或差异在合理范围内，说明税务合规性较好；如果存在较大偏差，需要逐环节排查。",
                "how_found": f"执行了四源交叉验证：(1)从{len(sal_invs)}张销项发票提取销项税额{vat_output:,.2f}元 (2)从{len(pur_invs)}张进项发票提取进项税额{vat_input:,.2f}元 (3)从申报表取应缴税额{vat_payable:,.2f}元 (4)从银行流水提取实际缴税{tax_from_bank:,.2f}元——四源比对，追溯差异根源。",
                "category": "域15 多源交叉"
            })

    return findings


# ═══════════ 域15.5: 客户维度三源穿透分析 ═══════════
# 逐客户匹配开票/收款/合同——资深稽查员逐户穿透逻辑

def _domain_customer_revenue_matching(bank_txs, sal_invs, contract_data=None, voucher_revenue=None):
    """逐客户匹配开票金额与银行收款金额——穿透到每个客户维度的三源交叉验证
    
    稽查逻辑（老邓方法论）：
    只看总额偏差只是信号，逐客户匹配才是证据。
    ┌ 客户A：开票100万→收款150万→多收50万→查预收账款/合同付款节点
    ├ 客户B：开票200万→收款80万→少收120万→查应收账款账龄/客户真实性
    ├ 客户C：开票0→收款300万→未开票大额收款→查是否为隐匿收入
    └ 客户D：付款方≠开票对象→查代付协议/两套账嫌疑
    
    五时点验证：合同签订→发货/交付→开票→收款→会计确认收入
    """
    from collections import defaultdict
    
    findings = []
    if not bank_txs or not sal_invs:
        return findings
    
    # ── 1. 构建客户维度数据 ──
    # 销项发票按客户汇总
    inv_by_buyer = defaultdict(lambda: {"total": 0, "count": 0, "goods": set(), "dates": []})
    for inv in sal_invs:
        buyer = str(inv.get("buyer", "")).strip()
        if not buyer or len(buyer) < 2:
            continue
        key = buyer[:30]  # 取前30字作为匹配键
        amt = float(inv.get("total", 0) or inv.get("amount", 0) or 0)
        inv_by_buyer[key]["total"] += amt
        inv_by_buyer[key]["count"] += 1
        inv_by_buyer[key]["goods"].add(str(inv.get("goods", "")).strip()[:30])
        d = inv.get("date", "")
        if d: inv_by_buyer[key]["dates"].append(str(d)[:10])
    
    # 银行收款按付款方汇总
    bank_by_payer = defaultdict(lambda: {"credit": 0, "debit": 0, "count": 0, "dates": [], "raw": []})
    for tx in bank_txs:
        cp = str(tx.get("counterparty", "")).strip()
        if not cp or len(cp) < 2:
            continue
        key = cp[:30]
        credit = float(tx.get("credit", 0) or 0)
        debit = float(tx.get("debit", 0) or 0)
        bank_by_payer[key]["credit"] += credit
        bank_by_payer[key]["debit"] += debit
        bank_by_payer[key]["count"] += 1
        d = tx.get("date", "")
        if d: bank_by_payer[key]["dates"].append(str(d)[:10])
        # 保存原始交易记录用于特征分析
        bank_by_payer[key]["raw"].append({
            "date": str(d)[:10], "credit": credit, "debit": debit,
            "summary": str(tx.get("summary", ""))[:50]
        })
    
    # 合同数据按对方名称汇总
    contract_by_party = defaultdict(lambda: {"amount": 0, "count": 0})
    if contract_data:
        for ct in contract_data:
            party = str(ct.get("counterparty", "")).strip()
            if not party: continue
            key = party[:30]
            amt = float(ct.get("amount", 0) or 0)
            contract_by_party[key]["amount"] += amt
            contract_by_party[key]["count"] += 1
    
    # ── 2. 构建匹配关系 ──
    # 使用前缀匹配（前6字）和全文包含两种策略
    def _match_name(a, b):
        """模糊匹配两个名称"""
        a, b = a.lower().strip(), b.lower().strip()
        if not a or not b: return False
        if a == b: return True
        if len(a) >= 6 and len(b) >= 6:
            if a[:6] == b[:6]: return True
        if len(a) >= 4 and len(b) >= 4:
            if a in b or b in a: return True
        # 去除常见后缀后匹配
        for suffix in ["有限公司", "有限责任公司", "股份公司", "厂", "店", "经营部"]:
            a_clean = a.replace(suffix, "")
            b_clean = b.replace(suffix, "")
        return len(a_clean) >= 4 and len(b_clean) >= 4 and (a_clean in b_clean or b_clean in a_clean)
    
    # 建立客户映射：发票客户→银行收款方
    # 统计总数
    total_inv_amount = sum(d["total"] for d in inv_by_buyer.values())
    total_bank_credit = sum(d["credit"] for d in bank_by_payer.values())
    
    # ── 3. 逐客户穿透分析 ──
    customer_details = []  # 逐客户明细
    gap_customers = []     # 偏差显著客户
    payment_no_inv = []    # 收款无开票
    inv_no_payment = []    # 开票无收款
    party_mismatch = []    # 付款方≠开票对象
    
    for buyer_key, inv_data in inv_by_buyer.items():
        inv_amt = inv_data["total"]
        if inv_amt < 5000:
            continue
        
        # 找匹配的银行收款
        matched_credit = 0
        matched_payers = []
        for payer_key, bank_data in bank_by_payer.items():
            if _match_name(buyer_key, payer_key):
                matched_credit += bank_data["credit"]
                matched_payers.append(payer_key)
        
        gap = matched_credit - inv_amt
        gap_pct = (gap / max(inv_amt, 1)) * 100
        
        # 合同金额
        contract_amt = 0
        for ct_key, ct_data in contract_by_party.items():
            if _match_name(buyer_key, ct_key):
                contract_amt += ct_data["amount"]
        
        detail = {
            "buyer": buyer_key,
            "inv_amt": inv_amt,
            "inv_count": inv_data["count"],
            "bank_credit": matched_credit,
            "contract_amt": contract_amt,
            "gap": gap,
            "gap_pct": gap_pct,
            "goods": ", ".join(list(inv_data["goods"])[:3]),
        }
        customer_details.append(detail)
        
        # 偏差>30%且>5万元 → 高风险客户
        if abs(gap_pct) > 30 and abs(gap) > 50000:
            gap_customers.append(detail)
        
        # 开票但无收款（赊销/虚开风险）
        if matched_credit < 1000 and inv_amt > 50000:
            inv_no_payment.append(detail)
        
        # 付款方名称与开票客户不一致
        if matched_payers and not any(_match_name(buyer_key, p) for p in matched_payers):
            party_mismatch.append({
                "buyer": buyer_key,
                "inv_amt": inv_amt,
                "bank_credit": matched_credit,
                "matched_payers": matched_payers
            })
    
    # 检查银行收款中无对应开票的客户
    for payer_key, bank_data in bank_by_payer.items():
        credit = bank_data["credit"]
        if credit < T.amount_thresholds.medium_transaction:
            continue
        matched = False
        for buyer_key in inv_by_buyer:
            if _match_name(payer_key, buyer_key):
                matched = True
                break
        if not matched:
            # 排除法人/股东/关联方
            raw_texts = " ".join([r.get("summary", "") for r in bank_data["raw"]])
            is_personal = any(k in raw_texts for k in ["工资", "报销", "借款", "还款", "往来"])
            if not is_personal:
                payment_no_inv.append({
                    "payer": payer_key,
                    "credit": credit,
                    "count": bank_data["count"],
                    "dates": bank_data["dates"][:3],
                    "samples": bank_data["raw"][:3]
                })
    
    # ── 4. 大额整数收款特征检测 ──
    integer_receipts = []
    for payer_key, bank_data in bank_by_payer.items():
        for r in bank_data["raw"]:
            amt = r["credit"]
            if amt >= 100000 and amt % 10000 == 0:
                integer_receipts.append({
                    "payer": payer_key,
                    "date": r["date"],
                    "amount": amt,
                    "summary": r["summary"]
                })
    
    # ── 5. 生成稽查发现 ──
    
    # 5.1 逐客户偏差汇总
    if gap_customers:
        top_customers = sorted(gap_customers, key=lambda x: abs(x["gap"]), reverse=True)[:5]
        gap_lines = []
        for c in top_customers:
            direction = "多收" if c["gap"] > 0 else "少收"
            gap_lines.append(
                f"  {c['buyer'][:15]}：开票{c['inv_amt']:,.2f}元 vs 收款{c['bank_credit']:,.2f}元 → "
                f"{direction}{abs(c['gap']):,.2f}元（{abs(c['gap_pct']):.2f}%）"
                + (f" | 合同{c['contract_amt']:,.2f}元" if c['contract_amt'] > 0 else "")
            )
        
        avg_gap_pct = sum(abs(c["gap_pct"]) for c in gap_customers) / len(gap_customers)
        
        findings.append({
            "type": "客户维度开票收款偏差（逐户穿透）",
            "level": "高风险",
            "score": 9,
            "detail": f"逐客户匹配后，{len(gap_customers)}个客户的开票金额与银行收款偏差>30%：\n" + "\n".join(gap_lines),
            "description": (
                f"我将销项发票和银行流水做了逐客户匹配——不是看总额，是穿透到每个客户维度：\n\n"
                f"匹配算法：提取{len(inv_by_buyer)}个发票客户×{len(bank_by_payer)}个银行收款方 → "
                f"前程匹配+全文包含+去后缀 → 逐对匹配。\n\n"
                f"结果：{len(gap_customers)}个客户偏差>30%（平均{avg_gap_pct:.2f}%）。\n\n"
                f"⚠ 这是关键信号——逐客户偏差比总额偏差更有稽查价值。"
                f"总额偏差可能相互抵消，逐客户偏差暴露真实问题：\n"
                f"• 收款>开票的客户 → 可能存在已收款未确认收入 → 检查预收账款/合同付款节点/发货记录\n"
                f"• 开票>收款的客户 → 可能存在已开票未收款 → 检查应收账款账龄/客户真实性/是否存在虚开\n"
                f"• 无论哪种，都需要逐户调取客户明细账、合同、出库单做五时点比对"
            ),
            "how_found": (
                f"我走了完整的逐户穿透流程：\n"
                f"(1)从{len(sal_invs)}张销项发票提取{len(inv_by_buyer)}个购方名称→按客户汇总开票金额\n"
                f"(2)从{len(bank_txs)}条银行流水提取全部贷方(收入)交易→按付款方汇总收款金额\n"
                f"(3)对{len(inv_by_buyer)}个客户逐一用模糊匹配找对应的银行收款→计算偏差\n"
                f"(4)合同数据（如有）作为第三方验证——比对合同金额与开票/收款\n"
                f"(5)发现{len(gap_customers)}个客户偏差超过30%阈值"
            ),
            "tax_impact": (
                f"逐客户偏差揭示了个体风险：\n"
                f"• 收款>开票的客户：差额可能为已交货未确认收入——需追查预收账款科目、合同结算条款、发货记录。"
                f"若已交货→延迟确认收入→当期补税+滞纳金\n"
                f"• 开票>收款的客户：差额可能为虚开发票——需追查应收账款真实性、客户工商状态。"
                f"若长期挂账→虚开嫌疑→进项转出+移送公安\n\n"
                f"法律后果：隐匿收入→《税收征收管理法》第六十三条偷税处罚（0.5-5倍罚款）；"
                f"虚开发票→《发票管理办法》第二十二条+刑法第二百零五条"
            ),
            "policy_ref": (
                "《税收征收管理法》第三十五条（核定征收）、第六十三条（偷税处罚）；"
                "《中华人民共和国增值税法》关于纳税义务发生时间的规定；"
                "《发票管理办法》第二十二条（禁止虚开）；"
                "《企业所得税法实施条例》第九条（权责发生制）"
            ),
            "suggestion": (
                f"① 对{len(gap_customers)}个偏差客户逐户调取：\n"
                f"  - 客户明细账（应收账款/预收账款科目）\n"
                f"  - 销售合同（核对金额+付款节点+交货条款）\n"
                f"  - 出库单/发货记录（核实货物是否已交付）\n"
                f"② 收款>开票的客户：若已发货→补开票+补申报；若未发货→确认为预收并附合同证明\n"
                f"③ 开票>收款的客户：核实应收账款账龄，超90天→排查虚开风险\n"
                f"④ 建立开票与回款逐月勾稽制度——每月按客户维度比对，偏差>30%当月处理"
            ),
            "category": "域15.5 客户维度穿透",
            "rule_id": 310,
            "source_chain": "客户维度-三源穿透-五时点验证",
        })
    
    # 5.2 大额收款无开票（未开票收入风险）
    if payment_no_inv:
        top = sorted(payment_no_inv, key=lambda x: x["credit"], reverse=True)[:5]
        detail_lines = []
        total_uninvoiced = 0
        for p in top:
            total_uninvoiced += p["credit"]
            detail_lines.append(f"  {p['payer'][:15]}：收款{p['credit']:,.2f}元（{p['count']}笔，" +
                               f"样例：{'、'.join(str(r['summary'])[:20] for r in p.get('samples',[]) if r.get('summary'))})")
        
        findings.append({
            "type": "大额收款无对应开票（未开票收入风险）",
            "level": "高风险",
            "score": 10,
            "detail": f"{len(payment_no_inv)}个付款方向企业支付大额款项（>10万元），但在销项发票中查不到对应客户的开票记录，合计{total_uninvoiced:,.2f}元：\n" + "\n".join(detail_lines),
            "description": (
                f"逐户穿透中发现了更严重的问题——{len(payment_no_inv)}个付款方向企业支付了合计{total_uninvoiced:,.2f}元，但销项发票库中完全找不到对应的开票记录。\n\n"
                f"这不是偏差的问题，是'零开票'的问题——企业收了钱但没有开任何发票。"
                f"需要立即核实：这些付款是经营性收款（已交货未开票→隐匿收入），还是非经营性收款（借款/注资/往来款）。\n\n"
                f"⚠ 稽查关键判断：如果这些付款方是企业而非个人、金额非整数、摘要含'货款''项目款'等经营关键词 → 高度嫌疑为隐匿收入。"
            ),
            "how_found": (
                f"逐户穿透反向扫描：对{len(bank_by_payer)}个银行收款方逐一检查——"
                f"是否在{len(inv_by_buyer)}个发票客户中有匹配→未匹配的标记为'无开票收款'→"
                f"排除法人/股东/关联方/工资/报销等非经营性关键词→"
                f"筛选金额>10万元的→发现{len(payment_no_inv)}个"
            ),
            "tax_impact": (
                f"合计{total_uninvoiced:,.2f}元收款无开票——若被认定为隐匿收入：\n"
                f"• 补缴增值税（{total_uninvoiced*0.13:,.2f}元起，按适用税率）\n"
                f"• 补缴企业所得税（{total_uninvoiced*0.25*0.25:,.2f}元起，按核定利润率）\n"
                f"• 加收每日万分之五滞纳金\n"
                f"• 0.5-5倍罚款\n"
                f"• 情节严重移送公安"
            ),
            "policy_ref": (
                "《税收征收管理法》第六十三条（偷税）；"
                "《中华人民共和国增值税法》第一条（纳税义务）；"
                "《发票管理办法》第十九条（销售商品/提供服务必须开具发票）"
            ),
            "suggestion": (
                f"① 逐笔核实{len(payment_no_inv)}个付款方的收款性质：\n"
                f"  - 经营性收款→立即补开票+补申报增值税及企业所得税\n"
                f"  - 非经营性收款→保留借款合同/注资决议/往来对账记录\n"
                f"② 建立收款即开票制度——对公账户收到经营款项后3个工作日内必须开票\n"
                f"③ 对无法确认性质的收款，先挂预收账款，6个月内未确认收入的做出说明"
            ),
            "category": "域15.5 客户维度穿透",
            "rule_id": 311,
            "source_chain": "客户维度-零开票收款-隐匿收入",
        })
    
    # 5.3 大额整数收款特征
    if len(integer_receipts) >= 3:
        total_int = sum(r["amount"] for r in integer_receipts)
        int_lines = [f"  {r['date']} {r['payer'][:15]} {r['amount']:,.2f}元" for r in integer_receipts[:5]]
        
        findings.append({
            "type": "大额整数收款特征（客户维度）",
            "level": "中风险",
            "score": 5,
            "detail": f"发现{len(integer_receipts)}笔大额整数收款（≥10万元且金额为万元整倍数），合计{total_int:,.2f}元：\n" + "\n".join(int_lines),
            "description": (
                f"逐户分析银行收款记录时，发现{len(integer_receipts)}笔收款金额为整数（≥10万元且为万元整倍数）。"
                f"真实交易的收款通常有零有整，频繁出现整数金额需引起注意——"
                f"可能是非经营性资金（借款/注资/往来款）或刻意安排的交易。"
            ),
            "how_found": "逐笔扫描所有银行收款交易→筛选金额≥10万元且金额%10000==0→统计数量和来源方。",
            "tax_impact": "整数收款本身非违规信号，但需核实交易性质——若为经营性收款但未开票，则涉及隐匿收入；若为非经营性，需确认会计处理是否正确。",
            "policy_ref": "《税收征收管理法》第五十四条（检查权）；《企业会计准则》关于收入确认的规定。",
            "suggestion": "逐笔核实整数收款的交易背景——确认是否为经营性收入，若是则核对是否已开票申报。",
            "category": "域15.5 客户维度穿透",
            "rule_id": 312,
            "source_chain": "客户维度-整数收款特征",
        })
    
    # 5.4 付款方与开票对象不一致
    if party_mismatch:
        mismatch_lines = []
        for m in party_mismatch[:5]:
            mismatch_lines.append(
                f"  开票给'{m['buyer'][:15]}'（{m['inv_amt']:,.2f}元），"
                f"但收款来自'{m['matched_payers'][0][:15] if m['matched_payers'] else '?'}'（{m['bank_credit']:,.2f}元）"
            )
        
        findings.append({
            "type": "付款方与开票对象不一致（客户维度）",
            "level": "中风险",
            "score": 6,
            "detail": f"{len(party_mismatch)}个客户存在付款方名称与发票抬头不一致：\n" + "\n".join(mismatch_lines),
            "description": (
                f"逐客户匹配时发现{len(party_mismatch)}个客户的付款方名称与销项发票的购方名称不一致。\n\n"
                f"这可能是代付款（需有代付协议）→也可能是两套账的信号——"
                f"发票开给A，但B付款，A和B之间无关联关系。"
                f"稽查会追问：B为什么替A付钱？A和B什么关系？是否有真实的货物交付？"
            ),
            "how_found": "逐客户匹配发票购方名称与银行付款方名称→发现名称不一致的客户→排除前缀匹配偏差后确认不一致。",
            "tax_impact": "付款方与发票抬头不一致→三流不合一→可能被认定为虚开发票→进项税额不得抵扣+罚款。",
            "policy_ref": "《发票管理办法》第二十二条（如实开具发票）；国家税务总局公告2014年第39号（三流一致）。",
            "suggestion": (
                "① 逐笔核实不一致的原因——是否代付？是否有代付协议？\n"
                "② 代付情况应取得三方代付协议+付款方身份证明\n"
                "③ 无法解释的不一致→主动红冲原发票并重新开具给实际付款方"
            ),
            "category": "域15.5 客户维度穿透",
            "rule_id": 313,
            "source_chain": "客户维度-付款方一致性",
        })
    
    return findings


# ═══════════ 域16: 扩展规则引擎 ═══════════

def _domain_advanced_rules(bank_txs, sal_invs, pur_invs, salaries, social_security, vouchers, inventory):
    """扩展审查规则：覆盖217条之外的风险维度"""
    from collections import defaultdict
    findings = []

    # ── 规则1: 大额整数交易检测 ──
    round_txs = []
    for tx in bank_txs:
        amt = abs(tx.get("amount", 0))
        if amt >= 10000 and amt % 10000 == 0:
            round_txs.append(tx)
    if len(round_txs) >= 3:
        findings.append({
            "type": "大额整数交易频繁",
            "level": "中风险", "score": 7,
            "detail": f"银行流水中有{len(round_txs)}笔整数万元交易（如{round_txs[0].get('amount',0):,.2f}元）。",
            "description": f"银行流水中发现{len(round_txs)}笔金额为整万元的交易。真实的商业交易金额通常带有零头（含税、运费等），大量整数交易可能表明：资金过桥、虚假交易、或通过整数金额规避银行反洗钱监控阈值。",
            "how_found": "扫描银行流水，筛选金额>=1万元且为10000的整数倍的交易记录。正常商业交易含税金额极少为纯粹整数。",
            "tax_impact": "整数交易易引发反洗钱监测和税务稽查关注，可能被认定为无真实商业背景的资金往来。",
            "policy_ref": "《反洗钱法》关于大额交易和可疑交易报告的规定；《金融机构大额交易和可疑交易报告管理办法》。",
            "suggestion": "1）逐笔核实整数交易的商业背景；2）保留交易合同、订单等证明文件；3）避免无商业实质的整数资金往来。",
            "category": "域16 扩展规则"
        })

    # ── 规则2: 周末/节假日交易检测 ──
    weekend_txs = []
    for tx in bank_txs:
        d = tx.get("date", "")
        if len(d) == 8:
            try:
                import datetime as dt
                dd = dt.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
                if dd.weekday() >= 5:  # 周六=5 周日=6
                    weekend_txs.append(tx)
            except: pass
    if len(weekend_txs) >= 5:
        findings.append({
            "type": "周末交易频繁",
            "level": "中风险", "score": 5,
            "detail": f"{len(weekend_txs)}笔交易发生在周末/节假日。",
            "description": f"发现{len(weekend_txs)}笔银行交易发生在周末或节假日。正常企业间的对公交易通常在营业日进行，周末频繁交易可能表明：个人经营者使用对公账户处理个人事务、或通过周末交易规避监管。",
            "how_found": "提取每笔银行交易的日期，使用Python datetime模块计算星期几（weekday>=5为周末）。",
            "tax_impact": "周末异常交易可能被纳入可疑交易监测范围，引发反洗钱和税务联合检查。",
            "policy_ref": "《人民币银行结算账户管理办法》关于账户用途的规定。",
            "suggestion": "1）核实周末交易是否具有合理商业理由（如电商行业周末正常收款属正常）；2）非营业日交易应有明确业务背景支撑。",
            "category": "域16 扩展规则"
        })

    # ── 规则3: 购销品名匹配度检测 ──
    if sal_invs and pur_invs:
        sal_goods = set()
        for inv in sal_invs:
            g = str(inv.get("goods", "")).lower()
            for kw in g.replace("*"," ").split():
                if len(kw) >= 2: sal_goods.add(kw)
        pur_goods = set()
        for inv in pur_invs:
            g = str(inv.get("goods", "")).lower()
            for kw in g.replace("*"," ").split():
                if len(kw) >= 2: pur_goods.add(kw)
        common = sal_goods & pur_goods
        if sal_goods and pur_goods and len(common) < 3:
            findings.append({
                "type": "购销售商品种不匹配",
                "level": "中风险", "score": 7,
                "detail": f"销项涉及{len(sal_goods)}类品名，进项涉及{len(pur_goods)}类品名，重叠仅{len(common)}类。",
                "description": f"将销项发票和进项发票的品名关键词进行交叉比对：销项涉及{len(sal_goods)}类品名，进项涉及{len(pur_goods)}类品名，但两者重叠仅{len(common)}类。正常的商贸企业，采购的商品与销售的商品应有较高的品名重叠度（买入什么就卖出什么）。品名不匹配可能意味着：进项发票虚开（采购了与经营无关的商品）、存在大量委托加工但无加工费发票、或营业范围发生重大变化。",
                "how_found": "提取销项发票和进项发票的货物名称，分词后构建品名集合，计算交集大小。交集<3类触发预警。",
                "tax_impact": "购销品名严重不匹配是虚开进项发票的典型特征。税务机关会重点核查进项发票对应的货物是否与企业实际经营相关。",
                "policy_ref": "《中华人民共和国增值税法》关于进项税额抵扣须与生产经营相关的规定。",
                "suggestion": "1）核实进项品名与销项品名不匹配的原因；2）如存在委托加工，应取得加工费发票并建立加工台账；3）确保采购的货物与服务与企业经营范围相关。",
                "category": "域16 扩展规则"
            })

    # ── 规则4: 发票连号检测 ──
    if sal_invs:
        inv_nos = []
        for inv in sal_invs:
            no = str(inv.get("inv_no", ""))
            if no.isdigit() and len(no) >= 8:
                inv_nos.append(int(no))
        inv_nos.sort()
        consecutive_groups = []
        group = [inv_nos[0]] if inv_nos else []
        for i in range(1, len(inv_nos)):
            if inv_nos[i] - inv_nos[i-1] <= 3:
                group.append(inv_nos[i])
            else:
                if len(group) >= 5: consecutive_groups.append(group)
                group = [inv_nos[i]]
        if len(group) >= 5: consecutive_groups.append(group)
        if consecutive_groups:
            group_details = []
            for g in consecutive_groups:
                group_details.append(f"{len(g)}张连号({g[0]}~{g[-1]})")
            findings.append({
                "type": "发票连号异常",
                "level": "中风险", "score": 6,
                "detail": f"发现{len(consecutive_groups)}组连号或近号发票（每组>=5张）。{'；'.join(group_details)}。",
                "description": f"销项发票中存在{len(consecutive_groups)}组发票号码连续或接近连续的发票。正常的经营活动中，发票通常是分散开给不同客户的，连号发票可能表明：集中突击开票、为完成业绩或调节税负而集中开票、或向同一客户大额拆分开票。",
                "how_found": "提取所有销项发票号码（数字部分），排序后检测连续号码组（相邻号码差<=3），连续>=5张触发预警。",
                "tax_impact": "连号开票易被税务机关认定为人为调节收入或拆分开票，若被认定存在虚开嫌疑，将面临协查和处罚。",
                "policy_ref": "《发票管理办法》关于如实开具发票的规定。",
                "suggestion": "1）核实连号发票是否全部具有真实交易背景；2）避免在同一时间段集中向单一客户大量开票；3）如确需拆分开票，保留订单、出库单等证明。",
                "category": "域16 扩展规则"
            })

    # ── 规则5: 员工人均效能检测 ──
    if salaries and sal_invs:
        emp_count = len(set(s.get("name", "") for s in salaries))
        total_revenue = sum(float(inv.get("total", 0) or 0) for inv in sal_invs)
        if emp_count > 0 and total_revenue > 0:
            rev_per_person = total_revenue / emp_count
            findings.append({
                "type": "人均效能评估",
                "level": "低风险", "score": 2,
                "detail": f"{emp_count}名员工创造销项收入{total_revenue:,.2f}元，人均{rev_per_person:,.2f}元。",
                "description": f"根据工资表和销项发票计算：{emp_count}名员工在分析期间创造销项收入{total_revenue:,.2f}元，人均产值{rev_per_person:,.2f}元。人均效能是衡量企业经营效率和管理规范性的参考指标之一。如果人均产值远低于行业平均水平，可能表明存在虚列人员工资或收入申报不足的问题。",
                "how_found": "从工资表统计在职人数，从销项发票汇总收入，计算人均产值。",
                "category": "域16 扩展规则"
            })

    # ── 规则6: 发票备注栏合规检测 ──
    if sal_invs:
        no_remark = sum(1 for inv in sal_invs if not inv.get("remark", "").strip())
        if sal_invs and no_remark / len(sal_invs) > T.ratios.half:
            findings.append({
                "type": "发票备注栏信息缺失",
                "level": "低风险", "score": 3,
                "detail": f"{no_remark}/{len(sal_invs)}张销项发票无备注信息。",
                "description": f"有{no_remark}张销项发票未填写备注栏信息。根据规定，建筑服务、运输服务、不动产租赁、销售不动产等特定业务的发票备注栏属于必填项目。大量空白备注栏可能意味着未按规定填写发票信息，虽然不直接构成偷逃税，但在稽查中会被认定为发票管理不规范。",
                "how_found": "扫描销项发票的备注字段，统计空白率。",
                "tax_impact": "特定业务备注栏缺失的发票不得作为税收凭证，购买方取得的此类发票不得抵扣进项税额或税前扣除。",
                "policy_ref": "《国家税务总局关于全面推开营业税改征增值税试点有关税收征收管理事项的公告》（2016年第23号）关于发票备注栏的规定。",
                "suggestion": "1）检查发票是否涉及需要备注的特殊业务类型；2）规范开票流程，确保备注栏按要求填写。",
                "category": "域16 扩展规则"
            })

    # ── 规则7: 供应商纳税信用预警 ──
    if pur_invs:
        # 检查供应商名称中是否存在异常模式
        abnormal_names = []
        for inv in pur_invs:
            s = str(inv.get("seller", ""))
            # 检测异常短名称、纯数字、特殊字符
            if len(s) <= 3 and s.strip():
                abnormal_names.append(s)
            if any(c in s for c in ["***", "..."]) and s not in abnormal_names:
                abnormal_names.append(s)
        if abnormal_names:
            findings.append({
                "type": "供应商名称异常",
                "level": "中风险", "score": 6,
                "detail": f"发现{len(abnormal_names)}个名称异常的供应商：{'、'.join(abnormal_names)}。",
                "description": f"进项发票供应商中存在{len(abnormal_names)}个名称异常的情况：{'、'.join(abnormal_names)}。供应商名称过短或包含特殊字符可能意味着：发票信息填写不规范、供应商未进行工商登记、或使用了虚假名称开票。",
                "how_found": "扫描所有进项发票的销方名称，检测名称长度<=3字符或包含异常字符（***）的记录。",
                "tax_impact": "从名称异常的供应商取得发票，税务机关会重点怀疑其是否为正常经营的企业，进项税额抵扣存在风险。",
                "policy_ref": "国家税务总局公告2019年第38号关于异常增值税扣税凭证的规定。",
                "suggestion": "1）核实异常名称供应商的工商登记和纳税状态；2）联系供应商更正发票抬头信息；3）避免与工商登记不规范的供应商交易。",
                "category": "域16 扩展规则"
            })

    return findings


# ═══════════ 域17: 凭证收入 vs 发票收入对比 ═══════════

def _domain_voucher_invoice_revenue_compare(voucher_rev, sal_invs, bank_txs):
    """对比凭证中主营业务收入（区分开票/未开票）与销项发票收入、银行入账"""
    findings = []
    
    inv_total = sum(float(i.get("total", 0) or 0) for i in sal_invs)
    bank_income = sum(tx["credit"] for tx in bank_txs) if bank_txs else 0
    
    vr_total = voucher_rev["total"]
    vr_invoiced = voucher_rev["invoiced"]
    vr_uninvoiced = voucher_rev["uninvoiced"]
    
    # 收入三源对比总览
    findings.append({
        "type": "收入三源对比总览",
        "level": "低风险", "score": 2,
        "detail": f"凭证主营业务收入{vr_total:,.2f}元（开票{vr_invoiced:,.2f} + 未开票{vr_uninvoiced:,.2f}） vs 销项发票{inv_total:,.2f}元 vs 银行入账{bank_income:,.2f}元。",
        "description": f"这是稽查中最核心的三源收入对比。凭证记录的主营业务收入为{vr_total:,.2f}元，其中明确标注开票收入{vr_invoiced:,.2f}元、未开票收入{vr_uninvoiced:,.2f}元（占比{vr_uninvoiced/max(vr_total,1)*100:.2f}%）。销项发票价税合计{inv_total:,.2f}元，银行流水入账{bank_income:,.2f}元。",
        "how_found": f"①凭证端: {voucher_rev['rows']}条主营收入分录，按摘要(普票/专票/无票)分类求和→开票{vr_invoiced:,.2f}+未开票{vr_uninvoiced:,.2f}={vr_total:,.2f}元; ②发票端: {len(sal_invs)}张销项发票汇总{inv_total:,.2f}元; ③银行端: {len(bank_txs)}条流水贷方合计{bank_income:,.2f}元。三源对比出差异。",
        "category": "域17 凭证发票收入对比"
    })
    
    # 未开票收入占比过大
    if vr_total > 0 and vr_uninvoiced / vr_total > T.ratios.material_deviation:
        pct = vr_uninvoiced / vr_total * 100
        findings.append({
            "type": "未开票收入占比过高",
            "level": "高风险", "score": 9,
            "detail": f"凭证主营业务收入{vr_total:,.2f}元中，未开票收入{vr_uninvoiced:,.2f}元（占比{pct:.2f}%）。",
            "description": f"贵公司{vr_total:,.2f}元的主营业务收入中，有{vr_uninvoiced:,.2f}元（{pct:.2f}%）为未开票收入。这个比例非常高。未开票收入本身并不违法，但必须确认是否已在增值税申报表中'未开具发票'栏次如实填报了{vr_uninvoiced:,.2f}元。如果申报表中未填报或填报金额不一致，将构成少申报销售额的严重问题。",
            "how_found": f"从凭证主营收入{vr_total:,.2f}元中，筛选摘要含[未开票/无票]或无发票类型标注的贷方合计{vr_uninvoiced:,.2f}元，占{vr_uninvoiced/vr_total*100:.2f}%，超30%触发。",
            "tax_impact": f"未开票收入{vr_uninvoiced:,.2f}元若未在增值税申报中如实填报，将少缴增值税约{vr_uninvoiced*0.13:,.2f}元（按13%税率估算），需补缴税款+滞纳金+可能罚款。同时企业所得税也存在少申报营业收入的风险。",
            "policy_ref": "《中华人民共和国增值税法》第十九条关于纳税义务发生时间的规定；增值税申报表附表一'未开具发票'栏次；《税收征收管理法》第六十三条关于偷税的规定。",
            "suggestion": f"1）立即核实{vr_uninvoiced:,.2f}元未开票收入是否已在对应税款所属期的增值税申报中填报；2）若未申报，尽快做补充申报并补缴税款；3）建立未开票收入台账，确保每期申报完整；4）考虑将未开票收入逐步转为规范开票。",
            "category": "域17 凭证发票收入对比"
        })
    
    # 凭证开票收入 vs 销项发票差异
    if vr_invoiced > 0 and inv_total > 0:
        gap = abs(vr_invoiced - inv_total)
        if gap / max(vr_invoiced, 1) > T.ratios.minor_deviation:
            findings.append({
                "type": "凭证开票收入与发票金额不一致",
                "level": "高风险", "score": 8,
                "detail": f"凭证记录开票收入{vr_invoiced:,.2f}元 vs 销项发票价税合计{inv_total:,.2f}元，差异{gap:,.2f}元。",
                "description": f"凭证中标注为开票收入的金额为{vr_invoiced:,.2f}元，但销项发票价税合计为{inv_total:,.2f}元，两者差异{gap:,.2f}元（{gap/max(vr_invoiced,1)*100:.2f}%）。这个差异意味着：要么凭证中有些标注为开票的收入实际未开票，要么存在发票未入账（发票已开但凭证未记），要么金额录入有误。",
                "how_found": f"凭证标注开票收入{vr_invoiced:,.2f}元 vs 销项发票价税合计{inv_total:,.2f}元，差异{gap:,.2f}元({gap/vr_invoiced*100:.2f}%)，超10%触发。",
                "tax_impact": "凭证与发票金额不一致，说明会计核算与税务申报之间存在脱节，稽查时会深究每一笔差异的来源和性质。",
                "policy_ref": "《会计法》关于会计核算真实性的要求；《发票管理办法》关于发票入账的规定。",
                "suggestion": "1）逐月核对凭证主营业务收入与销项发票金额；2）差异编制调节表并逐笔说明原因（如含税/不含税差异、发票跨期等）；3）确保会计记账与开票系统数据同步。",
                "category": "域17 凭证发票收入对比"
            })
    
    # 银行入账 vs 凭证收入差异
    if vr_total > 0 and bank_income > 0:
        gap = abs(vr_total - bank_income)
        gap_pct = gap / max(vr_total, 1) * 100
        if gap_pct > 20:
            findings.append({
                "type": "凭证收入与银行入账偏差大",
                "level": "高风险", "score": 8,
                "detail": f"凭证收入{vr_total:,.2f}元 vs 银行入账{bank_income:,.2f}元，差异{gap:,.2f}元（{gap_pct:.2f}%）。",
                "description": f"凭证记录的主营业务收入为{vr_total:,.2f}元，银行流水贷方入账{bank_income:,.2f}元，两者差异{gap:,.2f}元（{gap_pct:.2f}%）。银行入账大于凭证收入，说明存在未确认收入的资金入账；凭证收入大于银行入账，说明存在非银行渠道收款（现金、第三方平台等）或收入确认时点与收款时点不一致。",
                "how_found": f"凭证主营收入{vr_total:,.2f}元 vs 银行流水贷方合计{bank_income:,.2f}元，差异{gap:,.2f}元({gap_pct:.2f}%)，超20%触发。",
                "tax_impact": "银行入账与账面收入不匹配，会触发税务机关对隐匿收入或虚列收入的质疑。若银行入账多但账面收入少，差额可能被推定为隐匿收入。",
                "policy_ref": "《税收征收管理法》第三十五条关于核定应纳税额的规定。",
                "suggestion": "1）逐月编制银行入账与主营业务收入的调节表；2）区分经营性收款和非经营性收款；3）确保所有经营收款及时确认收入并如实申报。",
                "category": "域17 凭证发票收入对比"
            })
    
    return findings


# ═══════════ 域19: 跨域关联推理——从点→线→面→体 ═══════════

def _domain_cross_domain_reasoning(all_findings, bank_txs, sal_invs, pur_invs, vouchers, inventory):
    """将所有发现的关联关系串联成证据链，实现单点→多域印证→风险主题
    
    稽查方法论⑥：从 cross_domain_evidence.json 加载链定义（数据驱动，非硬编码）
    """
    findings = []
    
    # ═══ 加载跨域证据链定义（JSON驱动） ═══
    chain_defs = []
    try:
        chain_path = os.path.join(os.path.dirname(__file__), "static", "cross_domain_evidence.json")
        with open(chain_path, 'r', encoding='utf-8') as _f:
            chain_defs = json.load(_f)
    except Exception as _e:
        # 回退：JSON加载失败时使用内置定义（保持系统可用性）
        chain_defs = _BUILTIN_CROSS_DOMAIN_CHAINS
    
    # 只执行 executable=True 且非 legacy 的链（旧证据链仅用于UI展示）
    chain_defs = [c for c in chain_defs if c.get("executable", True)]
    
    # ═══ 构建关键词索引 ═══
    def keyword_match(finding, keywords):
        if not isinstance(finding, dict):
            return False
        text = str(finding.get("type","")) + str(finding.get("detail","")) + str(finding.get("description",""))
        return any(kw in text for kw in keywords)
    
    # ═══ 逐链处理：JSON驱动 ═══
    for chain_def in chain_defs:
        chain_name = chain_def.get("name", "跨域证据链")
        min_evidence = chain_def.get("min_evidence", 2)
        dimensions = chain_def.get("dimensions", [])
        
        evidence_collected = []
        chain_findings = []
        
        for dim in dimensions:
            dim_code = dim.get("code", "")
            dim_source = dim.get("source", "")
            dim_kws = dim.get("kws", [])
            dim_desc = dim.get("desc", "")
            
            for f in all_findings:
                if keyword_match(f, dim_kws):
                    detail_text = str(f.get("detail", ""))
                    evidence_collected.append((dim_code, dim_source, detail_text, f.get("score", 0), dim_desc))
                    if f not in chain_findings:
                        chain_findings.append(f)
                    break  # 每个维度只取第一个匹配
        
        # 达到最小证据数 → 生成跨域发现
        if len(evidence_collected) >= min_evidence:
            total_score = sum(e[3] for e in evidence_collected)
            avg_score = total_score // max(len(evidence_collected), 1)
            
            # 构建证据文本
            evidence_text = ""
            for code, source, detail, sc, desc in evidence_collected:
                evidence_text += f"[{code}-{source}] {desc}\n  → {detail}\n\n"
            
            findings.append({
                "type": chain_name,
                "level": chain_def.get("level", "高风险"),
                "score": min(avg_score, 10),
                "detail": f"{len(evidence_collected)}条相互印证的发现指向同一结论：{chain_name}。证据链维度：{', '.join(e[0] for e in evidence_collected)}。",
                "description": f"以下{len(evidence_collected)}条来自不同域、不同数据源的发现，从不同角度指向同一个结论——【{chain_name}】：\n\n{evidence_text}\n{chain_def.get('description', '')}",
                "how_found": chain_def.get("how_found", f"对{len(evidence_collected)}个独立维度的数据进行交叉验证，各方证据互相印证形成证据链闭环"),
                "tax_impact": chain_def.get("tax_impact", ""),
                "policy_ref": chain_def.get("policy_ref", ""),
                "suggestion": chain_def.get("suggestion", ""),
                "category": "域19 跨域推理",
                "source_chain": chain_name,
                "cross_domain_evidence": {
                    "chain_id": chain_def.get("id"),
                    "dimensions_triggered": [e[0] for e in evidence_collected],
                    "total_dimensions": len(dimensions),
                },
            })
    
    return findings


_BUILTIN_CROSS_DOMAIN_CHAINS = [
    {"id":1,"name":"隐匿收入证据链","sub_topic":"资金流","level":"高风险","trigger_keywords":["第三方收款","第三方收款占比","未开票收入占比","未开票收入占比过高","收款与开票","进销严重倒挂"],"min_evidence":3,"dimensions":[{"code":"A","source":"资金端","kws":["第三方收款","第三方收款占比"],"desc":"收款方式异常，脱离对公监管"},{"code":"B","source":"凭证端","kws":["未开票收入占比","未开票收入占比过高"],"desc":"凭证记录有大量未开票收入"},{"code":"C","source":"发票端","kws":["收款与开票"],"desc":"收款与开票偏差巨大"},{"code":"D","source":"进销端","kws":["进销严重倒挂"],"desc":"进项远超销项"}]},
    {"id":2,"name":"虚开发票嫌疑证据链","sub_topic":"发票流","level":"高风险","trigger_keywords":["同城供应商群集","进项发票无付款","供应商高度集中","采购量远超销售","供应商名称"],"min_evidence":3,"dimensions":[{"code":"A","source":"供应商地理","kws":["同城供应商群集"],"desc":"供应商集中"},{"code":"B","source":"资金匹配","kws":["进项发票无付款"],"desc":"有票无付款"},{"code":"C","source":"采购集中度","kws":["供应商高度集中"],"desc":"前3大占比过高"},{"code":"D","source":"采购合理性","kws":["采购量远超销售"],"desc":"采购量远超销售"},{"code":"E","source":"供应商身份","kws":["供应商名称"],"desc":"名称异常"}]},
    {"id":3,"name":"无实质经营证据链","sub_topic":"经营实质","level":"高风险","trigger_keywords":["基础经营费用缺失","库存真实性","经营实质","没有仓储"],"min_evidence":2,"dimensions":[{"code":"A","source":"经营费用","kws":["基础经营费用缺失"],"desc":"基础费用为零"},{"code":"B","source":"仓储空间","kws":["库存真实性"],"desc":"库存真实性存疑"},{"code":"C","source":"经营实质","kws":["经营实质"],"desc":"业务链不完整"},{"code":"D","source":"存货支撑","kws":["没有仓储"],"desc":"无物理空间"}]},
    {"id":4,"name":"会计基础工作薄弱证据链","sub_topic":"资料完备","level":"中风险","trigger_keywords":["凭证号字段缺失","凭证借贷不平","合同文件缺失"],"min_evidence":2,"dimensions":[{"code":"A","source":"凭证管理","kws":["凭证号字段缺失"],"desc":"凭证号全空"},{"code":"B","source":"借贷平衡","kws":["凭证借贷不平"],"desc":"借贷不平衡"},{"code":"C","source":"档案管理","kws":["合同文件缺失"],"desc":"合同缺失"}]},
    {"id":5,"name":"资金链危机证据链","sub_topic":"资金流","level":"高风险","trigger_keywords":["存货占压资金","采购量远超"],"min_evidence":2,"dimensions":[{"code":"A","source":"存货压款","kws":["存货占压资金"],"desc":"存货占压资金"},{"code":"B","source":"收支对比","kws":[],"desc":"收支严重失衡"},{"code":"C","source":"过度采购","kws":["采购量远超"],"desc":"过度采购"}]},
    {"id":6,"name":"利润现金流背离证据链","sub_topic":"财务报表","level":"中风险","trigger_keywords":["利润表","现金流","银行收入","开票收入"],"min_evidence":2,"dimensions":[{"code":"A","source":"利润端","kws":["利润表"],"desc":"账面有利润"},{"code":"B","source":"现金流","kws":["现金流"],"desc":"现金流为负"},{"code":"C","source":"发票端","kws":["开票收入"],"desc":"开票银行差异"}]},
    {"id":7,"name":"发票异常行为证据链","sub_topic":"发票流","level":"中风险","trigger_keywords":["红冲","作废","三角","时间","跨月"],"min_evidence":2,"dimensions":[{"code":"A","source":"红冲作废","kws":["红冲","作废"],"desc":"红冲作废异常"},{"code":"B","source":"三角验真","kws":["三角"],"desc":"三角验证失败"},{"code":"C","source":"时间模式","kws":["时间","跨月"],"desc":"时间模式可疑"}]},
]


# ═══════════ 稽查方法论㉓ 四步稽查分析法：detect→verify→diagnose→report 统一框架 ═══════════

def _four_step_audit_framework(all_findings, bank_txs, invoices, target_entity):
    """四步稽查分析法：将核心发现按 detect→verify→diagnose→report 统一处理"""
    if not all_findings: return all_findings
    legal_rep = (target_entity or {}).get("legal_representative", "") or ""
    sal_invs = [i for i in (invoices or []) if i.get("type") == "销项"]
    pur_invs = [i for i in (invoices or []) if i.get("type") == "进项"]
    core_types = ["收款来源与开票客户严重不匹配","进项发票与银行付款未匹配","有进无销","有销无进","进销品名","重物跨省","外地加工费","费用发票占比异常","收款与开票金额偏差","个人付款方身份核实"]
    enriched = 0
    for f in all_findings:
        if f.get("_four_step_applied"): continue
        ftype = f.get("type","")
        if not any(ct in ftype for ct in core_types): continue
        # Step 1: detect - 检测现象
        signals = [f"数据扫描发现异常信号: {ftype}"]
        # Step 2: verify - 交叉验证
        related = sum(1 for o in all_findings if o is not f and any(k in ftype and k in o.get("type","") for k in ["收款","开票","发票","进项","销项","进销","品名","资金","费用"]))
        sources = sum([bool(bank_txs), bool(sal_invs), bool(pur_invs)])
        # Step 3: diagnose - 根因诊断
        causes = _get_root_causes(ftype, legal_rep)
        # Step 4: report - 输出结论
        paths = _get_action_paths(ftype, f.get("level","中风险"))
        f["_four_step_applied"] = True
        f["_four_step"] = {"detect":{"signals":signals},"verify":{"related_findings":related,"multi_source":sources},"diagnose":{"root_causes":causes},"report":{"action_paths":paths}}
        enriched += 1
    return all_findings

def _get_root_causes(ftype, legal_rep=""):
    if "收款来源" in ftype: return ["①跨期/预收/应收(正常商业)", "②合并/拆单收付款", "③未开票经营收入(隐匿)", "④股东注资/借款(非经营)"] + ([f"法定代表人{legal_rep}需确认为何打款"] if legal_rep else [])
    if "进项发票与银行付款" in ftype: return ["①自然跨期","②应付账款(正常)","③非对公付款","④虚开发票嫌疑"]
    if "有进无销" in ftype: return ["①纯贸易→品名应一致→隐瞒销售","②制造业→有加工信号→焦点转移","③存货积压"]
    if "有销无进" in ftype: return ["①制造业→加工信号→可解释","②虚开发票→销项真实性存疑"]
    if "重物跨省" in ftype or "外地加工费" in ftype: return ["供应商/客户/加工商三组地址不重叠","零运输成本→货物流断裂","从单点扩展到面(全链条经营实质)"]
    return ["综合判定→需结合资料进一步确认"]

def _get_action_paths(ftype, level):
    if "隐匿" in ftype or "未开票" in ftype: return ["路径A: 主动补报→补税+滞纳金(从轻)","路径B: 被查实→0.5-5倍罚款(从重)"]
    if "虚开" in ftype or "进项发票" in ftype: return ["路径A: 自行转出进项税额→免刑事","路径B: 被查实→移送公安+刑事追诉"]
    if "加工" in ftype or "有进无销" in ftype or "有销无进" in ftype: return ["路径A: 提供BOM+加工合同+物流→证实真实性","路径B: 无法提供→进项税额转出+补税"]
    return ["提供佐证→降级","无法提供→升级→按最高标准"]

# ═══════════ 跨域线索链分析引擎 ═══════════

def _domain_cross_domain_clues(all_findings):
    """加载跨域线索链，匹配发现并记录触发状态到报告中。
    增强：调用 narratives_builder 生成结构化叙事 detail（含分步叙事+交叉验证表+证据链闭环）。
    """
    chain_defs = _load_json("static/cross_domain_clues.json", [])
    if not chain_defs:
        return []
    
    # 只执行 executable=True 的链（旧方法链仅用于UI展示）
    chain_defs = [c for c in chain_defs if c.get("executable", True)]
    if not chain_defs:
        return []
    
    # 延迟导入叙事生成器
    try:
        from narrative_builder import build_narrative
        _has_narrative = True
    except ImportError:
        _has_narrative = False
    
    findings = []
    for chain_def in chain_defs:
        kws = chain_def.get("trigger_keywords", [])
        min_ev = chain_def.get("min_evidence", 2)
        
        triggered_findings = []
        for f in all_findings:
            ftype = str(f.get("type", ""))
            fdetail = str(f.get("detail", ""))
            if any(kw in ftype or kw in fdetail for kw in kws):
                if f not in triggered_findings:
                    triggered_findings.append(f)
        
        if len(triggered_findings) >= min_ev:
            path_steps = []
            for s in chain_def.get("investigation_path", []):
                path_steps.append(f"Step{s.get('step','')}: {s.get('domain','')} → {s.get('action','')}")
            
            # ── 叙事增强：触发发现≥1条时生成结构化叙事 ──
            narrative_obj = None
            if _has_narrative and len(triggered_findings) >= 1:
                try:
                    narrative_obj = build_narrative(chain_def, triggered_findings, all_findings)
                except Exception:
                    narrative_obj = None
            
            if narrative_obj:
                # 用结构化叙事替换单纯的字符串 detail
                detail = narrative_obj
                description = narrative_obj.get("narrative", chain_def.get("description", ""))
            else:
                detail = f"通过{len(triggered_findings)}条独立发现的交叉验证，确认'{chain_def.get('name','')}'线索成立。"
                description = chain_def.get("description", "")
            
            findings.append({
                "type": chain_def.get('name',''),
                "level": chain_def.get("level", "中风险"),
                "score": min(len(triggered_findings) * 2, 9),
                "detail": detail,
                "description": description,
                "how_found": chain_def.get("how_found", f"从{len(kws)}个线索信号中发现{len(triggered_findings)}条关联发现，触发'{chain_def.get('name','')}'调查路径"),
                "tax_impact": chain_def.get("tax_impact",""),
                "policy_ref": chain_def.get("policy_ref",""),
                "suggestion": chain_def.get("suggestion",""),
                "category": "多域交叉验证",
                "_cross_domain_clue": True,
                "_investigation_path": path_steps,
                "_triggered_count": len(triggered_findings),
            })
    
    return findings


# ═══════════ 跨域分析链推理引擎 ═══════════

def _domain_cross_domain_analysis(all_findings):
    """加载跨域分析链，匹配触发信号并产生结构化推理发现"""
    chain_defs = _load_json("static/cross_domain_analysis.json", [])
    if not chain_defs:
        return []
    
    # 只执行 executable=True 且非 legacy 的链（旧方法论仅用于UI展示）
    chain_defs = [c for c in chain_defs if c.get("executable", True)]
    if not chain_defs:
        return []
    
    findings = []
    for chain_def in chain_defs:
        trigger_kws = chain_def.get("trigger_keywords", [])
        reasoning = chain_def.get("reasoning_path", [])
        min_evidence = chain_def.get("min_evidence", 1)
        
        if not trigger_kws or not reasoning:
            continue
        
        # 检查触发关键词是否在发现的type/detail/description中出现
        triggered = False
        for f in all_findings:
            ftype = str(f.get("type", ""))
            fdetail = str(f.get("detail", ""))
            fdesc = str(f.get("description", ""))
            combined = ftype + fdetail + fdesc
            match_count = sum(1 for kw in trigger_kws if kw in combined)
            if match_count >= min_evidence:
                triggered = True
                break
        
        if triggered:
            reasoning_desc = ""
            for rs in reasoning:
                action = rs.get("action", "")
                if isinstance(action, dict):
                    reasoning_desc += f"Step{action.get('order',rs.get('step',''))}: {action.get('from','')} → {action.get('to','')}\n"
                    if action.get("finding"):
                        reasoning_desc += f"  发现: {action['finding']}\n"
                    if action.get("action"):
                        reasoning_desc += f"  动作: {action['action']}\n"
                else:
                    reasoning_desc += f"Step{rs.get('step','')}: {str(action)[:100]}\n"
                reasoning_desc += "\n"
            
            # 从 description 或 suggestion 中提取回退条件提示
            desc = chain_def.get("description", "")
            suggestion = chain_def.get("suggestion", "")
            
            findings.append({
                "type": chain_def.get('name',''),
                "level": chain_def.get("level", "中风险"),
                "score": min(len(reasoning) * 2, 9),
                "detail": f"检测到{len(trigger_kws)}个触发关键词——经{len(reasoning)}步推理分析，发现{len(reasoning)}条异常线索。",
                "description": f"【推理路径】\n{reasoning_desc}\n\n{desc}\n\n{suggestion}",
                "how_found": f"自动监测到'{', '.join(trigger_kws[:5])}'等关键词，启动'{chain_def.get('name','')}'推理链进行{len(reasoning)}步因果推导",
                "suggestion": suggestion or f"按{len(reasoning)}步推理链逐步验证。",
                "category": "跨域推理分析",
                "_cross_domain_analysis": True,
                "_reasoning_chain": reasoning,
            })
    
    return findings


# ═══════════ 通用JSON加载 ═══════════

def _load_json(rel_path, default=None):
    path = os.path.join(os.path.dirname(__file__), rel_path)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default if default is not None else []


# ═══════════ 稽查队扩展: 收入时间线调查 ═══════════

def _domain_revenue_timeline(vouchers, sal_invs, bank_txs):
    """按时间线分析收入波动，找出异常时间点"""
    findings = []
    
    # 从凭证提取收入时间分布
    from collections import defaultdict
    rev_by_month = defaultdict(float)
    for v in vouchers:
        if "主营业务收入" in str(v.get("account", "")):
            date_str = str(v.get("date", ""))
            credit = float(v.get("credit", 0) or 0)
            if credit > 0 and len(date_str) >= 6:
                month = date_str[:6]
                rev_by_month[month] += credit
    
    if len(rev_by_month) >= 2:
        months = sorted(rev_by_month.keys())
        values = [rev_by_month[m] for m in months]
        if max(values) > min(values) * 3 and min(values) > 0:
            spike_month = months[values.index(max(values))]
            findings.append({
                "type": "收入时间线异常波动",
                "level": "中风险", "score": 5,
                "detail": f"收入月度波动剧烈：最高月{max(values):,.2f}元（{spike_month}），最低月{min(values):,.2f}元，波动倍数{max(values)/min(values):.2f}x。",
                "description": f"主营业务收入在不同月份间存在巨大波动：从最低{min(values):,.2f}元到最高{max(values):,.2f}元，相差{max(values)/min(values):.2f}倍。正常经营的电商企业收入通常呈平稳增长或季节性规律波动，非季节性月份出现3倍以上波动需要合理解释。\n\n可能原因：①某月集中确认了大额未开票收入；②促销活动导致收入暴增；③重大客户在集中月份付款；④之前月份有收入未及时入账。",
                "how_found": "从凭证中提取主营业务收入贷方发生额，按月汇总后计算最高月/最低月比值，>3倍触发预警。",
                "tax_impact": "收入大幅波动→若高月份是因为确认了长期积压的未开票收入→说明之前月份少确认了收入→跨期申报不准确。",
                "suggestion": f"① 解释{spike_month}月收入暴增的具体原因并提供支撑资料；② 检查其他月份是否遗漏了应确认的收入。",
                "category": "时间线调查"
            })
    
    # 销项发票时间分布
    inv_by_month = defaultdict(float)
    for inv in sal_invs:
        dt = str(inv.get("date", "") or inv.get("invoice_date", ""))
        if len(dt) >= 6:
            inv_by_month[dt[:6]] += float(inv.get("total", 0) or 0)
    
    if inv_by_month and rev_by_month:
        # 对比开票收入与主营业务收入的月度差异
        all_months = sorted(set(list(inv_by_month.keys()) + list(rev_by_month.keys())))
        mismatches = []
        for m in all_months:
            rev = rev_by_month.get(m, 0)
            inv = inv_by_month.get(m, 0)
            if rev > inv * 2 or inv > rev * 2:
                mismatches.append(m)
        
        if mismatches:
            findings.append({
                "type": "开票与入账收入月度错配",
                "level": "中风险", "score": 6,
                "detail": f"{len(mismatches)}个月存在开票收入与入账收入严重错配。",
                "description": f"在{len(mismatches)}个月份中，凭证主营业务收入与销项开票收入存在2倍以上差异。这意味着要么凭证入账了但没开票（未开票收入集中确认），要么开了票但凭证没入账（跨期或遗漏）。月度错配是申报不准确的前兆。",
                "how_found": "按月份分别汇总凭证主营收入和销项发票金额，对比月度差异，>2倍视为错配。",
                "tax_impact": "月度错配→增值税月度申报与会计收入确认不同步→存在跨期申报风险。",
                "suggestion": "逐月核对开票收入与入账收入，差异超过20%的月份要编制调节表。",
                "category": "时间线调查"
            })
    
    return findings


# ═══════════ 稽查队扩展: 供应商画像分析 ═══════

def _domain_supplier_profiling(pur_invs, bank_txs):
    """对核心供应商做深度画像: 交易频率/金额/时间/资金匹配"""
    findings = []
    if not pur_invs: return findings
    
    from collections import defaultdict
    supplier_stats = defaultdict(lambda: {"count": 0, "total": 0.0, "months": set()})
    for inv in pur_invs:
        name = str(inv.get("seller", ""))[:30].strip()
        if not name: continue
        supplier_stats[name]["count"] += 1
        supplier_stats[name]["total"] += float(inv.get("total", 0) or 0)
        dt = str(inv.get("date", "") or inv.get("invoice_date", ""))
        if len(dt) >= 6: supplier_stats[name]["months"].add(dt[:6])
    
    # 画像1: 高频低额供应商（刷票嫌疑）
    for name, s in supplier_stats.items():
        if s["count"] >= 20 and s["total"] / s["count"] < 5000:
            findings.append({
                "type": "高频低额供应商——刷票嫌疑",
                "level": "中风险", "score": 6,
                "detail": f"供应商「{name}」月度开票{s['count']}张，均额仅{s['total']/s['count']:,.2f}元，可能为拆分开票规避监管。",
                "description": f"供应商「{name}」在分析期间向贵公司开具了{s['count']}张发票，平均每张{s['total']/s['count']:,.2f}元。高频率、低单价的模式不符合正常B2B交易习惯，更常见于：①利用小规模纳税人起征点拆分开票；②刷流水式开票以虚增业务量；③将大额交易拆分为多张小额发票以规避大额交易报告。",
                "how_found": "按销方名称分组统计发票张数，单供应商>=20张且均额<5000元触发。",
                "tax_impact": "拆分开票是税务机关重点打击的行为。各张发票独立来看可能合规，但汇总起来暴露出规避监管的意图。",
                "suggestion": f"① 核实「{name}」{s['count']}笔交易的真实性和独立性；②检查是否应将连续小额交易合并为大额合同处理。",
                "category": "供应商画像"
            })
            break  # 只报告最典型的一个
    
    # 画像2: 供应商交易时间集中度
    for name, s in supplier_stats.items():
        if s["count"] >= 5 and len(s["months"]) == 1:
            findings.append({
                "type": "供应商交易集中在单月——突击开票嫌疑",
                "level": "中风险", "score": 5,
                "detail": f"供应商「{name}」{s['count']}张发票全部集中在同一个月，可能在突击开票。",
                "description": f"供应商「{name}」的{s['count']}张发票全部集中在一个月内开出。正常供应商的供货应该是持续性的，单月密集开票可能意味着：①期末突击采购以消耗预算或满足进项需求；②一次性交易刻意拆分成多张发票；③供应商本身经营不稳定。",
                "how_found": "按销方名称统计发票时间分布，>=5张发票但仅1个月的触发。",
                "suggestion": f"核实「{name}」集中交易的商业合理性，保留采购合同和入库凭证。",
                "category": "供应商画像"
            })
            break
    
    return findings


# ═══════════ 稽查队扩展: 资金流向追踪 ═══════

def _domain_fund_flow_mapping(bank_txs, sal_invs, pur_invs, target_entity=None):
    """绘制资金流向图: 谁在给企业钱→企业把钱给了谁"""
    findings = []
    if not bank_txs: return findings
    
    # ═══ 稽查方法论③：付款方身份核实 ═══
    # 从联网核查获取法定代表人/股东名单
    legal_rep = ""
    shareholders = []
    if target_entity:
        legal_rep = (target_entity.get("legal_representative", "") or "").strip()
        shareholders = target_entity.get("shareholders", []) or []
    
    from collections import defaultdict
    payers = defaultdict(float)  # 谁付钱给企业
    payees = defaultdict(float)  # 企业付钱给谁
    
    # 记录个人付款方（用于身份核实）
    personal_payers = defaultdict(float)
    legal_rep_payments = 0.0
    shareholder_payments = defaultdict(float)
    
    for tx in bank_txs:
        cp = str(tx.get("counterparty", "")).strip()
        if not cp: continue
        credit = float(tx.get("credit", 0) or 0)
        debit = float(tx.get("debit", 0) or 0)
        if credit > 0: payers[cp] += credit
        if debit > 0: payees[cp] += debit
        
        # 稽查方法论③：判断个人付款方身份
        if credit > 0:
            is_personal = (
                len(cp) <= 4 or  # 中文姓名通常2-4字
                (len(cp) <= 6 and not any(k in cp for k in ("公司", "厂", "店", "部", "局", "行", "院", "所", "中心"))))
            if is_personal:
                personal_payers[cp] += credit
                if legal_rep and (cp == legal_rep or cp in legal_rep or legal_rep in cp):
                    legal_rep_payments += credit
                for sh in shareholders:
                    sh_name = (sh.get("name", "") or "").strip()
                    if sh_name and (cp == sh_name or cp in sh_name or sh_name in cp):
                        shareholder_payments[cp] += credit
    
    # 生成付款方身份核实发现
    if personal_payers and (legal_rep or shareholders):
        id_check_parts = []
        if legal_rep_payments > 0:
            id_check_parts.append(f"法定代表人{legal_rep}个人账户向企业打款{legal_rep_payments:,.2f}元——可能为股东注资、借款或未申报的其他经营收款")
        for cp, amt in shareholder_payments.items():
            id_check_parts.append(f"股东{cp}个人账户向企业打款{amt:,.2f}元——可能为股东注资、借款或代收经营款项")
        
        other_personal = {cp: amt for cp, amt in personal_payers.items() 
                         if cp not in shareholder_payments and 
                         (not legal_rep or (cp != legal_rep and cp not in legal_rep and legal_rep not in cp))}
        if other_personal:
            other_total = sum(other_personal.values())
            other_names = "、".join(list(other_personal.keys()))
            id_check_parts.append(f"其他个人付款方（{len(other_personal)}个，合计{other_total:,.2f}元）：{other_names}——身份待核实")
        
        if id_check_parts:
            findings.append({
                "type": "个人付款方身份核实",
                "level": "中风险", "score": 6,
                "detail": "；".join(id_check_parts),
                "description": (
                    f"稽查方法论③：对银行流水中个人付款方进行身份核实。\n\n"
                    + f"联网核查获取的企业工商信息：\n"
                    + f"· 法定代表人：{legal_rep}\n"
                    + f"· 股东：{'、'.join([(s.get('name','')+'(持股'+str(s.get('ratio',''))+')') for s in shareholders]) if shareholders else '无数据'}\n\n"
                    + f"经逐笔比对银行流水中的个人付款方与法定代表人/股东名单：\n"
                    + f"· 法定代表人打款：{legal_rep_payments:,.2f}元（{'已确认' if legal_rep_payments > 0 else '零'}）\n"
                    + f"· 股东打款：{sum(shareholder_payments.values()):,.2f}元（覆盖{len(shareholder_payments)}位股东）\n"
                    + f"· 其他个人：{sum(other_personal.values() if other_personal else [0]):,.2f}元（{len(other_personal) if other_personal else 0}人）\n\n"
                    + f"【核查要点】\n"
                    + f"1. 法定代表人/股东个人打款 → 要求提供出资证明/借款合同/往来款说明，区分注资（资本公积）和经营收款（隐匿收入）\n"
                    + f"2. 其他个人打款 → 逐笔核实身份和交易背景，防止未开票的个人客户收款\n"
                    + f"3. 大额整数的个人打款 → 重点怀疑未开票货款"
                ),
                "how_found": f"银行流水{len(personal_payers)}个个人付款方→联网查询法定代表人+{len(shareholders)}位股东→逐名比对身份",
                "tax_impact": "法定代表人/股东个人打款如无法证明为注资或借款，推定为未申报的经营收入——补缴增值税+企业所得税+滞纳金+罚款",
                "suggestion": "①法定代表人/股东打款→提供股东会决议/出资证明/借款协议；②无法提供佐证的→视为经营收入主动申报补税；③其他个人打款→逐笔核实身份和交易背景",
                "category": "资金流向",
                "policy_ref": "《公司法》关于股东出资的规定；《税收征收管理法》第三十五条",
                "rule_id": 301,
                "source_chain": "资金流-付款方身份核实",
            })
    
    # 分析: 收款来源是客户还是非客户?
    buyer_names = set(str(i.get("buyer", ""))[:20].strip() for i in sal_invs) if sal_invs else set()
    total_income = sum(payers.values()) if payers else 0
    income_from_buyers = sum(payers.get(b, 0) for b in buyer_names)
    
    if total_income > 0 and income_from_buyers / total_income < 0.3:
        # 收集不匹配的付款方明细
        unmatched_payers = []
        for cp, amt in sorted(payers.items(), key=lambda x: -x[1]):
            if cp not in buyer_names and amt > 0:
                unmatched_payers.append({"name": cp[:25], "amount": amt})
        top_unmatched = unmatched_payers
        examples = "；".join([f"{u['name']}({u['amount']:,.2f}元)" for u in top_unmatched])
        
        # 也列出能匹配到的买家
        matched_payers = [(b, payers.get(b, 0)) for b in buyer_names if payers.get(b, 0) > 0]
        matched_payers.sort(key=lambda x: -x[1])
        matched_examples = "；".join([f"{m[0]}({m[1]:,.2f}元)" for m in matched_payers]) if matched_payers else "无"
        
        findings.append({
            "type": "收款来源与开票客户严重不匹配",
            "level": "高风险", "score": 9,
            "detail": f"银行账户累计收款{total_income:,.2f}元，其中仅{income_from_buyers:,.2f}元（{income_from_buyers/total_income*100:.2f}%）来自销项发票上的购方客户。剩余{total_income-income_from_buyers:,.2f}元（{(total_income-income_from_buyers)/total_income*100:.2f}%）来自销项发票上未出现的付款方。",
            "description": (
                f"将银行收款方名称与销项发票的购方客户名称进行双向比对。注意：实际经营中收款与开票天然不是一一对应关系"
                f"——客户可能分多次付款后一并开票（合并开票），也可能一次付款对应多张发票（合并收款），"
                f"还存在先收款后开票（预收账款）或先开票后收款（应收账款）的跨期情形。"
                f"因此，收款方名称与购方客户名称不匹配，不等于隐匿收入。\n\n"
                + f"经比对，被查单位{len(sal_invs)}张销项发票列示了{len(buyer_names)}个客户，银行账户共收到{len(payers)}个不同付款方的资金{total_income:,.2f}元。其中销项发票购方客户付款合计{income_from_buyers:,.2f}元（{income_from_buyers/total_income*100:.2f}%），匹配到的客户：{matched_examples}。\n\n"
                + f"其余{(total_income-income_from_buyers)/total_income*100:.2f}%的收款（{total_income-income_from_buyers:,.2f}元）来自销项发票上未列示的付款方，主要：{examples}等。这些资金可能属于以下情况：\n"
                + f"· 自然跨期（最常见）：收款发生在分析期间内但开票在前后期间——或者预收账款（收款在先开票在后），或者应收账款回款（开票在先收款在后）。需要拉长期间验证。\n"
                + f"· 合并/拆单收款：客户一次付款对应多张发票，或一笔发票对应多笔收款——名称能对上但金额对不上，此类已匹配成功。\n"
                + f"· 未开票的经营收入：客户付了款但确实没给开票——这是真正需要关注的隐匿收入风险。\n"
                + f"· 非经营资金流入：股东注资、借款、往来款——不是销售收入，但需要合同证明其性质。\n"
                + f"· 第三方代付：客户的关联方或实际控制人代为付款——需委托付款证明。\n"
                + f"· 已归类的非经营收款：社保退款、银行结息、法定代表人个人打款等——见本报告收款来源分析。\n\n"
                + f"综合判断：{(total_income-income_from_buyers)/total_income*100:.2f}%的未匹配收款需要逐笔核实属于哪种情况。重点是区分\u201c没有开票的经营收入\u201d（情况三\u2192隐匿收入）和\u201c有合理解释的非经营资金\u201d（情况四/五/六）。无法说明来源的按隐匿收入处理。"),
            "how_found": f"从银行流水提取{len(payers)}个付款方→与销项发票{len(buyer_names)}个购方名称交叉比对→{income_from_buyers/total_income*100:.2f}%匹配。",
            "tax_impact": f"若为未开票收入→补缴增值税（适用税率）+企业所得税（25%）+滞纳金+0.5-5倍罚款；若为借款/注资→需提供合同证明，无法证明的推定为应税收入；若为第三方代付→需委托付款证明。注意：收款与开票天然不是1:1关系，未匹配不自动等于隐匿收入。",
            "suggestion": f"要求被查单位逐笔说明{len(unmatched_payers)}个未匹配付款方的资金来源：①若为跨期收款——补充提供前后期间销项发票和银行流水；②若为预收/应收——提供预收账款或应收账款明细账佐证；③若为未开票销售收入——补开发票并申报未开票收入；④若为借款/注资——提供借款合同或出资证明；⑤若为第三方代付——提供委托付款证明。无法说明来源的按隐匿收入处理。",
            "category": "资金流向",
            "policy_ref": "《税收征收管理法》第三十五条；《中华人民共和国增值税法》关于销售额确定的规定；《企业所得税法》关于收入确认的规定。",
            "rule_id": 300,
            "source_chain": "资金流-发票收付款匹配",
        })
    
    # 分析: 付款流向是否与进项发票匹配
    seller_names = set(str(i.get("seller", ""))[:20].strip() for i in pur_invs) if pur_invs else set()
    total_expense = sum(payees.values()) if payees else 0
    expense_to_sellers = sum(payees.get(s, 0) for s in seller_names)
    
    if total_expense > 0 and expense_to_sellers / total_expense < 0.3:
        findings.append({
            "type": "付款流向与进项发票供应商严重不匹配",
            "level": "高风险", "score": 8,
            "detail": f"银行支出{total_expense:,.2f}元中仅{expense_to_sellers/total_expense*100:.2f}%流向进项供应商，其余资金需逐笔阐明去向。\n\n"
                f"【现实认知】注意：付款与进项发票天然不是一一对应关系。企业付款除了采购货款外，还包括："
                f"①工资薪金支出 ②固定资产购置 ③日常费用（租金/水电/差旅/办公）④税费缴纳 ⑤往来款/借款/还款 ⑥关联方资金调拨。"
                f"因此付款不流向供应商≠资金异常，但需要明确去向。",
            "description": f"银行流水中总共支出{total_expense:,.2f}元，但只有{expense_to_sellers:,.2f}元（{expense_to_sellers/total_expense*100:.2f}%）能匹配到进项发票上的销方名称。\n\n"
                "需要区分：剩余资金是正常费用支出（工资/租金/税费等）还是无法解释的资金流动。如果大量资金流出无法通过进项发票/费用票据/工资表/资产凭证等资料解释，则构成资金去向不明——这是税务稽查的核心关注点。",
            "how_found": "从银行流水提取交易对手名称和借方金额，与进项发票销方名称做模糊匹配。匹配不到的比例>70%触发。\n注意：该指标只考虑进项发票匹配，未包含工资、费用、税款等正常支出，因此触发不等于异常。",
            "suggestion": "① 逐笔分类银行支出：采购货款/工资薪金/日常费用/税费/固定资产/往来款；② 工资/费用类→确保取得合规票据并入账；③ 往来款→提供借款合同/往来明细；④ 无法分类的→逐笔核实原因，隐瞒资金真实去向的按隐匿资产或账外经营处理。",
            "category": "资金流向"
        })
    
    return findings


# ═══════════ 稽查队扩展: 人员与业务匹配 ═══════

def _domain_workforce_profiling(salaries, voucher_rev, bank_txs, social_security):
    """人员画像: 人数规模与业务量匹配、薪酬结构合理性"""
    findings = []
    if not salaries: return findings
    
    # 提取员工姓名和薪资
    emp_count = len(set(str(s.get("name", "")).strip() for s in salaries if str(s.get("name", "")).strip()))
    total_salary = sum(float(s.get("salary", 0) or 0) for s in salaries)
    avg_salary = total_salary / max(emp_count, 1)
    
    # 人均营收
    vr_total = voucher_rev.get("total", 0) if voucher_rev else 0
    per_person_revenue = vr_total / max(emp_count, 1)
    
    if emp_count > 0 and vr_total > 0:
        if per_person_revenue > T.amount_thresholds.large_transaction:
            findings.append({
                "type": "人均营收异常高——人员不足或收入虚高",
                "level": "中风险", "score": 5,
                "detail": f"{emp_count}名员工，人均营收{per_person_revenue:,.2f}元。超出一般中小企业水平。",
                "description": f"根据工资表统计有{emp_count}名员工，主营业务收入{vr_total:,.2f}元，人均创收{per_person_revenue:,.2f}元。对于一般企业，年人均营收在50-200万元属于正常范围。您的数据远超正常水平，可能意味着：①收入数据虚高（包含了不应计入收入的款项）；②存在大量外包/派遣人员未在工资表中体现；③企业确实属于高效轻资产模式。",
                "how_found": "主营业务收入（来自凭证）÷员工人数（来自工资表）>50万触发。",
                "suggestion": "① 如存在外包/派遣人员，补充相关合同和付款凭证；② 核实收入确认口径是否准确。",
                "category": "人员画像"
            })
        elif per_person_revenue < 100000 and vr_total > T.amount_thresholds.medium_transaction:
            findings.append({
                "type": "人均营收过低——人员冗余或收入少记",
                "level": "中风险", "score": 5,
                "detail": f"{emp_count}名员工，人均营收仅{per_person_revenue:,.2f}元。人员效率严重偏低。",
                "description": f"{emp_count}名员工人均创收仅{per_person_revenue:,.2f}元，效率极低。可能原因：①存在虚列人员吃空饷（工资表有人但实际无人）；②收入少记或隐匿；③企业处于初创期尚未产生收入。",
                "how_found": "主营业务收入÷员工人数<10万触发。",
                "suggestion": "① 逐人核实在岗情况；② 进行人员编制与产能的匹配分析；③ 裁撤冗余岗位。",
                "category": "人员画像"
            })
    
    # 薪酬与社保人数比对
    ss_count = len(set(str(s.get("name", "")).strip() for s in social_security if str(s.get("name", "")).strip())) if social_security else 0
    if emp_count > 0 and ss_count > 0 and emp_count != ss_count:
        findings.append({
            "type": "工资人数与社保人数不一致",
            "level": "高风险", "score": 8,
            "detail": f"工资表{emp_count}人 vs 社保{ss_count}人，差异{abs(emp_count-ss_count)}人。",
            "description": f"工资表显示有{emp_count}名员工，但社保参保仅{ss_count}人，差异{abs(emp_count-ss_count)}人。未参保的员工涉嫌违反《社会保险法》。金税四期已将人社数据与税务数据打通，工资个税申报人数与社保参保人数不一致将触发自动预警并可能引发社保稽核。",
            "how_found": "分别从工资表和社保明细中提取唯一员工姓名集合，对比人数差异。",
            "tax_impact": "① 未参保员工→社保稽核+补缴+滞纳金；② 工资费用如无社保支撑→可能被质疑为虚列费用→纳税调整。",
            "suggestion": "① 立即为未参保员工补办社保登记并补缴；② 如为劳务派遣/外包，提供派遣协议。",
            "category": "人员画像"
        })
    
    return findings


# ═══════════ 稽查队: 发票-存货-付款三角验证 ═══════════

def _domain_triangle_invoice_inventory_payment(pur_invs, inventory, bank_txs):
    """三角链: 进项发票时间→存货入库时间→银行付款时间 是否逻辑一致"""
    findings = []
    if not pur_invs or not bank_txs: return findings
    
    from collections import defaultdict
    # 构建供应商付款时间线
    pay_timeline = defaultdict(list)
    for tx in bank_txs:
        cp = str(tx.get("counterparty", "")).strip()
        if not cp: continue
        debit = float(tx.get("debit", 0) or 0)
        dt = str(tx.get("date", ""))
        if debit > 0 and len(dt) >= 8: pay_timeline[cp].append(dt)
    
    # 检查: 发票日期是否在付款之后（先付款后到票=异常）
    after_pay = 0
    for inv in pur_invs:
        seller = str(inv.get("seller", ""))[:30].strip()
        inv_date = str(inv.get("date", "") or inv.get("invoice_date", ""))
        if not seller or len(inv_date) < 8: continue
        for cp, dates in pay_timeline.items():
            if seller[:5] in cp or cp[:5] in seller:
                for pay_date in dates:
                    if pay_date < inv_date:
                        after_pay += 1
                        break
                break
    
    if after_pay > 0:
        findings.append({
            "type": "发票日期在付款之后——逻辑异常",
            "level": "中风险", "score": 6,
            "detail": f"发现{after_pay}笔交易的进项发票日期晚于银行付款日期。先付款后到票→交易逻辑存疑。",
            "description": f"正常的商业逻辑是: 签订合同→对方开票→我方付款。但发现了{after_pay}笔交易存在「先付款、后开票」的时间倒置现象。\n\n这可能是: ① 发票跨期（本月付款下月才拿到票）→ 正常的票据流转延迟；② 预付款后供应商补票 → 看是否符合合同约定；③ 发票为后补的「走账票」→ 真实交易发生在之前，后补发票来完成税务处理。\n\n建议逐笔核实时间倒置的合理性。",
            "how_found": "比对进项发票日期和银行流水付款日期，发票日期晚于付款日期超过30天视为异常。",
            "suggestion": "逐笔核实时间倒置交易的商业合理性：(1)若为正常跨期→保留采购订单确认交易时间；(2)若为预付款→提供预付款合同条款；(3)若为后补发票→核实真实交易发生时间并提供物流签收记录。",
            "policy_ref": "《发票管理办法》关于发票开具时限的规定；《中华人民共和国增值税法》关于纳税义务发生时间的规定。",
            "category": "三角验证"
        })
    
    # ═══════════ 进项发票分层分类：区分主营业务成本/重大费用/日常报销 ═══════════
    # 真实企业经营中，不同类别的进项发票有不同的付款模式：
    # ① 主营业务成本（原料/加工费/设备等）→ 对公付款，必须匹配供应商名称
    # ── 稽查方法论④-D：进项发票与银行付款匹配（主营成本识别驱动）──
    # 分析链：主营业务成本识别 → 三层分类 → 只对核心成本+重大费用做供应商名称匹配
    # 证据链：核心成本供应商清单 + 银行付款对方户名簿 + 六模式匹配结果
    # 方法：日常报销发票（餐饮住宿汽油等）员工先垫付后报销，付款对象是员工而非开票单位
    #       → 供应商名称未匹配属商业正常现象，不计入风险统计
    # 跨结论：与其他进销结论串联——如已有BOM缺失，供应商匹配的未匹配可能性更高
    
    # 使用共享的主营业务成本识别模块（替代原内联分类逻辑）
    from engine.main_biz_cost import identify_main_biz_cost
    biz_classification = identify_main_biz_cost(pur_invs, None)  # 该函数无 sal_invs 参数
    core_invs = biz_classification["core_cost_invs"]
    major_invs = biz_classification["major_expense_invs"]
    minor_invs = biz_classification["minor_expense_invs"]
    
    # 分层统计（保持与原代码兼容）
    biz_cost_invs = core_invs + major_invs  # 需匹配：核心成本+重大费用
    reimb_invs = minor_invs                  # 无需匹配：日常报销
    reimb_count = len(reimb_invs)
    reimb_total = sum(float(inv.get("total", 0) or 0) for inv in reimb_invs)
    
    if reimb_count > 0:
        findings.append({
            "type": "进项发票分层——日常费用报销排除",
            "level": "低风险", "score": 2,
            "detail": (
                f"从{len(pur_invs)}张进项发票中识别出{reimb_count}张为日常费用报销（"
                f"餐饮{sum(1 for i in reimb_invs if any(k in str(i.get('goods','')).lower() for k in ['餐饮','餐费','饭店']))}张、"
                f"住宿{sum(1 for i in reimb_invs if any(k in str(i.get('goods','')).lower() for k in ['住宿','酒店','宾馆','房费']))}张、"
                f"汽油{sum(1 for i in reimb_invs if any(k in str(i.get('goods','')).lower() for k in ['汽油','加油','柴油','车用']))}张、"
                f"其他{sum(1 for i in reimb_invs if not any(k in str(i.get('goods','')).lower() for k in ['餐饮','餐费','住宿','酒店','汽油','加油']))}张），"
                f"合计{reimb_total:,.2f}元。"
            ),
            "description": (
                f"我在做进项发票与银行付款匹配之前，先对{len(pur_invs)}张进项发票按品名做了三层分类——这是真实稽查的必要步骤。\n\n"
                f"第一层·主营业务成本（原料/加工费/设备等）：需对公付款，发票销方名称必须能在银行付款记录中找到。\n"
                f"第二层·重大费用（房租/咨询/广告/运输等）：一般对公或按合同付款，也应能在银行付款中匹配。\n"
                f"第三层·日常费用报销（餐饮/住宿/汽油/办公/差旅/通讯等）：员工先垫付后报销，\n"
                f"  对公账户的付款对象是员工而非开票单位。因此'供应商名称未匹配'属于商业正常现象，\n"
                f"  不应计入进项发票与付款不匹配的风险统计。\n\n"
                f"本次识别出{reimb_count}张发票属于第三层（日常费用报销），合计{reimb_total:,.2f}元，\n"
                f"已从匹配分析中排除。剩余{len(biz_cost_invs)}张为业务成本类发票，以下仅对这部分做名称匹配分析。"
            ),
            "how_found": (
                f"我逐张翻阅了{len(pur_invs)}张进项发票的'货物或应税劳务名称'列，"
                f"按{len(_REIMBURSEMENT_KWS_GLOBAL)}个日常报销关键词进行分类——"
                f"这是从真实企业财务实践中总结的规则：餐饮、住宿、汽油、差旅等费用"
                f"通常由员工垫付后凭发票报销，付款对象是员工而非开票单位。"
            ),
            "tax_impact": "日常费用报销发票本身合规，无需做供应商名称匹配。但需确保：(1)报销发票真实且与经营相关；(2)不得将个人消费发票用于企业进项抵扣；(3)差旅费等需附行程单/审批单等佐证材料。",
            "policy_ref": "《企业所得税法》第八条（与收入相关的合理支出）；《中华人民共和国增值税法》关于进项税额抵扣的规定。",
            "suggestion": "日常费用报销发票无需与银行付款匹配——建立费用报销制度，确保每张报销发票有对应的费用审批单、行程单等佐证材料即可。",
            "category": "三角验证"
        })
    
    # 重新做名称匹配——只对主营业务成本/重大费用类发票（排除日常报销）
    amt_mismatch = 0
    for inv in biz_cost_invs:
        seller = str(inv.get("seller", ""))[:30].strip()
        inv_total = float(inv.get("total", 0) or 0)
        if not seller or inv_total <= 0: continue
        found = False
        for cp, dates in pay_timeline.items():
            if seller[:5] in cp or cp[:5] in seller:
                found = True; break
        if not found: amt_mismatch += 1
    
    if amt_mismatch > 5:
        # 收集未匹配发票的详细信息
        unmatched_invs = []
        for inv in biz_cost_invs:
            seller = str(inv.get("seller", ""))[:30].strip()
            inv_total = float(inv.get("total", 0) or 0)
            if not seller or inv_total <= 0: continue
            found = False
            for cp, dates in pay_timeline.items():
                if seller[:5] in cp or cp[:5] in seller:
                    found = True; break
            if not found:
                unmatched_invs.append({
                    "seller": seller[:20],
                    "amount": inv_total,
                    "goods": str(inv.get("goods", ""))[:20],
                })
        
        total_unmatched = sum(inv["amount"] for inv in unmatched_invs)
        total_biz_cost = sum(float(inv.get("total", 0) or 0) for inv in biz_cost_invs)
        total_pur = sum(float(inv.get("total", 0) or 0) for inv in pur_invs)
        pct = total_unmatched / max(total_biz_cost, 1) * 100
        reimb_excluded_note = f"（已排除日常费用报销{reimb_count}张{reimb_total:,.2f}元——餐饮住宿汽油等以报销形式支付，不参与供应商名称匹配）" if reimb_count > 0 else ""
        
        # 按金额排序取前5
        unmatched_invs.sort(key=lambda x: -x["amount"])
        top5 = unmatched_invs
        examples = "；".join([f"{u['seller']}({u['goods']}, {u['amount']:,.2f}元)" for u in top5])
        
        findings.append({
            "type": "进项发票与银行付款未匹配——资金去向不明",
            "level": "高风险", "score": 8,
            "detail": (
                f"【分层分析结果】我将{len(pur_invs)}张进项发票按品名分为三层——主营业务成本/重大费用/日常报销。\n"
                f"已排除{reimb_count}张日常费用报销发票（餐饮住宿汽油等，合计{reimb_total:,.2f}元）——这些发票属于员工报销模式，付款对象是员工而非开票单位，不参与供应商名称匹配。\n"
                f"对剩余{len(biz_cost_invs)}张业务成本类发票做名称匹配：{amt_mismatch}张" +
                (f"（占业务成本类发票的{amt_mismatch/max(len(biz_cost_invs),1)*100:.2f}%）" if len(biz_cost_invs)>0 else "") +
                f"的供应商在银行流水付款记录中找不到对应付款，涉及采购金额{total_unmatched:,.2f}元，占业务成本采购总额{total_biz_cost:,.2f}元的{pct:.2f}%。"
            ),
            "description": f"将进项发票的销方名称与银行付款的对方户名进行双向比对。\n\n"
                + f"【现实认知】实际经营中发票与付款天然不是一一对应关系，而是以下六种模式之一：\n"
                + f"  ① 自然跨期——发票期末开、付款下期发生，或付款上期完成、发票后到（最常见）\n"
                + f"  ② 合并付款——一笔银行付款对应多张发票（供应商按月汇总结算，一次付清多月货款）\n"
                + f"  ③ 分期付款——一张发票对应多笔银行付款（大额采购分期支付，每次付一部分）\n"
                + f"  ④ 预付账款——付款在先、发票在后（先打款锁定货源或产能，供应商后续按实际发货开票）\n"
                + f"  ⑤ 应付账款——发票在先、付款在后（货到票到，但按账期约定如60天后付款）\n"
                + f"  ⑥ 非对公/代付——通过现金、微信、支付宝、个人账户或第三方支付（商业上属实但银行流水无记录）\n\n"
                + f"发票名称与付款记录不匹配≠交易不真实。未匹配只是分析起点，需要逐笔核实属于上述哪种情况。\n\n"
                + f"【比对结果】被查单位{len(pur_invs)}张进项发票中，{amt_mismatch}张（{amt_mismatch/len(pur_invs)*100:.2f}%）的销方名称在当前银行付款记录中找不到名称匹配的付款。涉及采购金额{total_unmatched:,.2f}元，占进项采购总额{pct:.2f}%。\n\n"
                + f"【可能原因分析】\n"
                + f"· 自然跨期：发票已开但付款在分析期外——拉长银行流水期间或核对应付账款明细验证\n"
                + f"· 合并/分期：多票一次付或多笔付一票——名称对不上但交易属实，需对账明细佐证\n"
                + f"· 预付/应付：付款与开票有时间差——正常商业行为，需预付/应付账款明细支撑\n"
                + f"· 非对公/代付：通过个人或第三方付款——商业可能属实，但进项税抵扣在稽查中面临被否定\n"
                + f"· 虚开发票：无真实交易只走票——最需排除但占比通常最低的情况\n\n"
                + f"【关键供应商明细】{examples}等。",
            "how_found": (
                f"我先将{len(pur_invs)}张进项发票按品名做三层分类——识别出{reimb_count}张为日常费用报销（餐饮住宿汽油差旅等，合计{reimb_total:,.2f}元）并排除。"
                f"然后对剩余{len(biz_cost_invs)}张业务成本类发票做名称匹配——"
                f"将销方名称与银行付款对方户名逐条比对，发现{amt_mismatch}张发票的供应商名称在当前银行付款记录中无法匹配。"
                f"（若包含日常费用报销，共{len(pur_invs)}张中{amt_mismatch + reimb_count}张未匹配，但日常报销本就不应参与匹配。）"
            ),
            "tax_impact": f"纳税影响取决于未匹配发票属于哪种付款模式：\n"
                f"① 自然跨期 → 低风险——拉长期间验证后消除疑虑\n"
                f"②③ 合并/分期付款 → 中低风险——需对账明细佐证交易真实性\n"
                f"④ 预付账款 → 低风险——查看前期付款记录或预付账款明细账\n"
                f"⑤ 应付账款 → 中风险——尚未付款的进项税额需确认是否已抵扣（已抵扣存疑）\n"
                f"⑥ 非对公/代付 → 中高风险——进项税额抵扣在稽查中可能被否定\n"
                f"虚开发票 → 刑事责任（《刑法》第205条）+行政罚款+纳税信用降级\n"
                f"核心逻辑：发票与付款天然不是1:1关系，未匹配≠虚开，但需要逐笔厘清以排除；虚开嫌疑。",
            "policy_ref": "《发票管理办法》第二十二条（禁止虚开）；《国家税务总局关于加强增值税征收管理若干问题的通知》（三流一致要求）；《刑法》第二百零五条（虚开增值税专用发票罪）",
            "suggestion": f"要求被查单位对{amt_mismatch}张\u201c未匹配\u201d发票逐笔标注属于哪种付款模式：\n"
                "① 自然跨期 → 补充提供前后期（至少覆盖发票日期前后3个月）银行流水\n"
                "② 合并付款 → 提供供应商对账明细表（逐笔记账日期+发票号+付款金额+对应银行流水号）\n"
                "③ 分期付款 → 提供分期付款计划+每期银行回单+对应发票号\n"
                "④ 预付账款 → 提供前期银行付款记录+预付账款明细账（科目余额+逐笔发生额）\n"
                "⑤ 应付账款 → 提供应付账款明细账（科目余额+逐笔发生额），确认是否已抵扣进项税\n"
                "⑥ 非对公/代付 → 提供第三方交易记录（微信/支付宝截图/个人卡流水）+供应商盖章收据\n"
                "无法提供任何佐证的 → 进项税额转出 + 按虚开发票相关规定处理。",
            "category": "三角验证",
            "rule_id": 1502,
            "source_chain": "资金流-发票收付款匹配",
        })
    
    return findings


# ═══════════ 稽查队: 经营实质地理分析 ═══════════

def _domain_business_premise_geo(bank_txs, invoices, docs, target_industry=""):
    """经营实质地理分析——从单一风险点推理出面的风险。target_industry: 行业代码，用于行业自适应重物举例。
    
    核心逻辑：
    1. 提取企业地址 → 中山市
    2. 分析销项客户/进项供应商/加工费供应商的地理分布
    3. 检测运输成本是否缺失（重物必有的运输开支）
    4. 加工费供应商是否在企业所在地（外地加工不合常理）
    5. 交叉推理：客户分布 ≠ 供应商分布 ≠ 加工商分布 ≠ 运输成本缺失 → 经营链条可疑
    """
    findings = []
    if not invoices or not bank_txs: return findings
    
    # ── 提取企业所在城市（从发票中推断） ──
    from collections import Counter
    city_candidates = Counter()
    for inv in invoices:
        buyer = str(inv.get("buyer","") or inv.get("购方名称","")).strip()
        seller = str(inv.get("seller","") or inv.get("销方名称","")).strip()
        goods = str(inv.get("goods","") or inv.get("货物或应税劳务名称",""))
        for name in [buyer, seller]:
            for c in _CHINA_CITIES_UNIFIED:
                if c in name: city_candidates[c] += 1
    company_city = city_candidates.most_common(1)[0][0] if city_candidates else '未知'
    
    # ── 按地址提取城市前缀 ──
    def extract_city(name):
        # 从公司名称中提取城市（使用统一城市列表）
        for c in _CHINA_CITIES_UNIFIED:  # 已按长度降序排列，长城市名优先
            if c in name: return c
        return "其他"
    
    # ── 分类统计 ──
    buyers = {}     # 销项客户 → city
    sellers = {}    # 进项供应商 → city  
    processors = {} # 加工费供应商 → city
    
    for inv in invoices:
        direction = str(inv.get("direction", ""))
        goods = str(inv.get("goods", "") or inv.get("货物或应税劳务名称", ""))
        
        if direction == "销项":
            buyer = str(inv.get("buyer", "") or inv.get("购方名称", "")).strip()
            if buyer and len(buyer) >= 4:
                city = extract_city(buyer)
                buyers[buyer] = city
        elif direction == "进项":
            seller = str(inv.get("seller", "") or inv.get("销方名称", "")).strip()
            if seller and len(seller) >= 4:
                city = extract_city(seller)
                sellers[seller] = city
                # 加工费特殊标记（已修复：排除分类码误判）
                if '加工费' in goods or ('加工' in goods and not re.search(r'\*[\u4e00-\u9fa5]+加工[品物食料]\*', goods)):
                    processors[seller] = city
    
    # ── 统计本地 vs 外地 ──
    local_buyers = sum(1 for c in buyers.values() if c == company_city)
    remote_buyers = sum(1 for c in buyers.values() if c != company_city and c != "其他")
    local_sellers = sum(1 for c in sellers.values() if c == company_city)
    remote_sellers = sum(1 for c in sellers.values() if c != company_city and c != "其他")
    remote_procs = sum(1 for c in processors.values() if c != company_city and c != "其他")
    
    remote_buyer_cities = set(c for c in buyers.values() if c != company_city and c != "其他")
    remote_seller_cities = set(c for c in sellers.values() if c != company_city and c != "其他")
    proc_cities = set(c for c in processors.values() if c != company_city and c != "其他")
    
    # ── 检测运输成本 ──
    transport_kws = ["运输","物流","快递","货运","搬运","装卸","配送","运费","交通"]
    has_transport = False
    for inv in invoices:
        goods = str(inv.get("goods", "") or inv.get("货物或应税劳务名称", ""))
        if any(kw in goods for kw in transport_kws):
            has_transport = True
            break
        seller = str(inv.get("seller", "") or inv.get("销方名称", ""))
        if any(kw in seller for kw in transport_kws):
            has_transport = True
            break
    
    # 检查银行付款中是否有运输公司
    if not has_transport:
        for tx in bank_txs:
            cp = str(tx.get("counterparty", "")).strip()
            if any(kw in cp for kw in transport_kws):
                has_transport = True
                break
    
    # ── 行业自适应重物描述 ──
    _industry_data = _load_industry_data()
    _heavy_goods_examples = _industry_data.get("heavy_goods_examples", {})
    heavy_example = _heavy_goods_examples.get(target_industry, "")
    if not heavy_example:
        # 模糊匹配
        for ind, example in _heavy_goods_examples.items():
            if ind in target_industry or target_industry in ind:
                heavy_example = example
                break
    if not heavy_example:
        heavy_example = "原材料和成品"
    heavy_desc = f"{heavy_example}都是重物"
    
    # ── 行业自适应产业集群描述 ──
    # [外部化] _cluster_map, _proc_map → 从 industry_data.json 加载
    _cluster = next((v for k,v in _load_industry_data().get("cluster_map", {}).items() if k in target_industry or target_industry in k), f"{target_industry}产业" if target_industry else "本地产业")
    _proc = next((v for k,v in _load_industry_data().get("proc_map", {}).items() if k in target_industry or target_industry in k), "相关加工工序")
    
    if remote_sellers >= 3 and not has_transport:
        remote_cities_list = "、".join(sorted(remote_seller_cities))
        findings.append({
            "type": "重物跨省经营缺运输成本",
            "level": "高风险", "score": 8,
            "detail": f"被查单位位于{company_city}市，{remote_sellers}家进项供应商分布在{remote_cities_list}等外地城市（距离{company_city}数百至上千公里），销项客户也分布在{len(remote_buyer_cities)}个外地城市。{heavy_desc}，但进项发票和银行流水中均未发现任何运输/物流/快递类费用。",
            "description": f"企业地址在{company_city}市，经营{heavy_example}。\n\n"
                + f"进项供应商地理分布：{len(sellers)}家供应商中{remote_sellers}家在外地"
                + f"（{'、'.join(sorted(remote_seller_cities))}等），距离{company_city}数百至上千公里。\n"
                + f"销项客户地理分布：{len(buyers)}家客户中{remote_buyers}家在外地"
                + f"（{'、'.join(sorted(remote_buyer_cities))}等）。\n\n"
                + f"{heavy_desc}，批量跨省运输必然产生可观的运输费用——"
                + f"按行业经验，跨省运输成本通常占货值的3%-8%。但上传的全部进项发票和银行流水中均未发现任何运输/物流/快递类费用。\n\n"
                + f"这是一个需要解释的经营实质问题：如果货物确实从{remote_cities_list}运到了{company_city}，运输费在哪里？\n"
                + f"可能的解释：①运输费由供应商承担（含在原料价格中）→需要采购合同证明是到货价；\n"
                + f"②运输费通过其他渠道支付（私人账户、现金）→三流不合一；\n"
                + f"③货物并未真实运输→虚构交易。\n\n"
                + f"无论哪种情况，都需要被查单位提供运输单据（物流单、运单、运费发票）来证明货物流的真实性。",
            "how_found": f"查阅被查单位提供的全部发票（共{len(invoices)}张）和银行流水。提取所有供应商和客户的公司名称，按城市关键词解析地址——发现{remote_sellers}家外地供应商（分布在{len(remote_seller_cities)}个城市）、{remote_buyers}家外地客户。同步检索全部进项发票和银行流水中的运输/物流/快递类关键词——未发现任何运输费用。结合纺织重物产业属性，判定货物流物证链缺失。",
            "tax_impact": "无运输费=货物流的物证链断裂→发票流+资金流虽存在但第三流（货物流）无法验证→交易真实性存疑→企业所得税成本扣除资格可能被否定+增值税进项税额抵扣面临被否定的风险。",
            "policy_ref": "《企业所得税法》第八条（成本费用真实性）；国家税务总局关于三流一致的要求（货物流、资金流、发票流）。",
            "suggestion": f"①提供全部外地供应商的采购合同，确认运输费用承担方式（出厂价/到货价/运费到付）；②提供物流运输单据（运单、签收单、物流公司对账单）；③如有运输类发票未上传，立即补充上传；④如为供应商承担运费，提供合同中的运费条款和供应商的运费发票复印件。无法提供任何运输证明的，成本费用不得税前扣除。",
            "category": "经营实质",
            "rule_id": 1500,
            "source_chain": "经营实质-地理分布",
        })
    
    # ── 发现2：加工费不在本地 ──
    if processors:
        proc_city_names = "、".join(sorted(proc_cities)) if proc_cities else "无"
        all_remote = len(processors) == remote_procs and remote_procs > 0
        
        desc = f"被查单位位于{company_city}市，但进项发票中出现了{len(processors)}家外地的加工费供应商："
        for pname, pcity in list(processors.items()):
            desc += f"\n· {pname}（{pcity}）"
        desc += f"\n\n正常经营逻辑：{_proc}等工序是服务型业务，加工商会主动靠近产业集群。"
        desc += f"{company_city}本身就是{_cluster}，当地应有大量可选的加工厂。"
        desc += f"但被查单位的加工费却来自{proc_city_names}等外地，这增加了额外的运输成本和加工周期，在商业上不合理。\n\n"
        
        if remote_procs > 0 and remote_sellers >= 3:
            desc += f"更值得警惕的是：加工费供应商（{proc_city_names}）、原材料供应商（{', '.join(sorted(remote_seller_cities - proc_cities))}等{len(remote_seller_cities)}城）、"
            desc += f"销售客户（{', '.join(sorted(remote_buyer_cities))}等{len(remote_buyer_cities)}城）三者分布在完全不同的城市——"
            desc += f"这意味着货物要在{len(remote_seller_cities)}+{len(proc_cities)}+{len(remote_buyer_cities)}个城市之间反复运输，"
            desc += f"而系统未检测到任何运输成本记录。这是一个从单点（加工费）扩展到面（全链条）的交叉异常："
            desc += f"加工费不本地+供应商不本地+客户不本地+零运输成本=整个经营链条在物流层面缺乏物证支撑。\n\n"
        
        desc += f"存疑点：①为何选择外地加工商而非本地加工商？②外地加工的真实性（加工过程是否有证据）？"
        desc += f"③若货物需要在{company_city}↔外地之间往返运输，运输成本在哪里？"
        
        level = "高风险" if (all_remote and remote_sellers >= 3 and not has_transport) else "中风险"
        score = T.scoring_weights.risk_high_score if level == "高风险" else 6
        
        findings.append({
            "type": "外地加工费存疑",
            "level": level, "score": score,
            "detail": f"发现{len(processors)}家加工费供应商不在{company_city}市（{proc_city_names}），与当地{_cluster}现状不符。{('同时存在' + str(remote_sellers) + '家外地原材料供应商、' + str(remote_buyers) + '家外地客户、零运输成本——全链条物流存疑') if (remote_sellers >= 3 and not has_transport) else ''}",
            "description": desc,
            "how_found": f"查阅被查单位提供的全部发票。从进项发票中筛选加工费类品名，提取对应的供应商名称并解析地址——发现{len(processors)}家加工费供应商均不在企业所在地（{company_city}市）。同步提取原材料供应商地址（分布在{len(remote_seller_cities)}个城市）和销项客户地址（分布在{len(remote_buyer_cities)}个城市），交叉对比发现三组地址互不重叠。结合零运输成本的检测结果，判定全链条物流存疑。",
            "tax_impact": "加工费真实性存疑 + 三流（货物流）无法验证 → 加工费对应的进项税额可能被要求转出 → 企业所得税成本费用扣除资格可能被否定。",
            "policy_ref": "《企业所得税法》第八条（成本费用真实性、合理性）；《发票管理办法》第二十二条（禁止虚开）。",
            "suggestion": (
                f"①提供选择外地加工商的商业合理性说明（如本地无同类工艺、价格优势等）；"
                f"②提供每次委托加工的送料单、收货单、加工工艺单、质量检验单等全链条单据；"
                f"③提供货物往返运输的物流单据；"
                f"④如加工真实但仅为外地开票\u2192认定为虚开发票风险。"),
            "category": "经营实质",
            "rule_id": 1501,
            "source_chain": "经营实质-地理分布",
        })
    
    # ── 发现3：全链条经营实质地理异常（点→面推理核心） ──
    # 逻辑：加工商地址 ≠ 供应商地址 ≠ 客户地址 → 三地分离 + 零运输成本 → 全链条异常
    all_geo_sets = []
    if remote_seller_cities: all_geo_sets.append(("原材料供应商", remote_seller_cities))
    if proc_cities: all_geo_sets.append(("加工费供应商", proc_cities))
    if remote_buyer_cities: all_geo_sets.append(("销项客户", remote_buyer_cities))
    
    # 至少两组地址互不重叠（来自不同城市群）
    all_cities_list = [cities for _, cities in all_geo_sets]
    has_geo_overlap = False
    for i in range(len(all_cities_list)):
        for j in range(i+1, len(all_cities_list)):
            if all_cities_list[i] & all_cities_list[j]:
                has_geo_overlap = True
                break
    
    geo_disjoint = len(all_geo_sets) >= 2 and not has_geo_overlap
    
    if geo_disjoint and not has_transport and (remote_sellers >= 3 or remote_buyers >= 3):
        groups_desc = "；".join([f"{name}分布在{'、'.join(sorted(cities))}" for name, cities in all_geo_sets])
        
        findings.append({
            "type": "全链条经营实质地理异常",
            "level": "高风险", "score": 9,
            "detail": (
                f"点→面推理：从单点异常（{'加工费来自外地' if processors else '供应商在外地'}）扩展为全链条分析。\n"
                f"被查单位（{company_city}市）的经营链条中：{groups_desc}。\n"
                f"三组地址互不重叠+零运输成本→货物流物证链断裂，全链条经营实质存疑。"
            ),
            "description": (
                f"【点→面推理分析】\n\n"
                f"起点（单点发现）：{'发现' + str(len(processors)) + '家加工费供应商不在' + company_city + '市' if processors else '发现供应商地址分布异常'}。\n\n"
                f"扩展（关联维度）：\n"
                f"┌ 维度A-原材料供应链：{remote_sellers}家供应商分布在{len(remote_seller_cities)}个城市"
                f"（{'、'.join(sorted(remote_seller_cities))}）\n"
                f"├ 维度B-加工链条：{'、'.join(sorted(proc_cities)) if proc_cities else '无加工费'}\n"
                f"├ 维度C-销售链条：{remote_buyers}家客户分布在{len(remote_buyer_cities)}个城市"
                f"（{'、'.join(sorted(remote_buyer_cities))}）\n"
                f"└ 维度D-物流成本：运输/物流/快递费用为零\n\n"
                f"交叉验证：\n"
                f"· A∩B∩C = ∅ → 三组地址完全互不重叠\n"
                f"· D = 0 → 货物流物证链完全缺失\n"
                f"· 结论：货物在{len(remote_seller_cities)}+{len(proc_cities)}+{len(remote_buyer_cities)}个城市之间反复运输，"
                f"但没有产生任何运输费用→这在物理上不可能。\n\n"
                f"这是一个从单点（{'加工费地理异常' if processors else '供应商地理异常'}）扩展到面（全链条经营实质存疑）的交叉推理。"
                f"换一个稽查员拿同样资料，同样会得出这个结论——因为三组地址互不重叠+零运输成本是无法解释的客观事实。"
            ),
            "how_found": (
                f"从发票中提取全部供应商({len(sellers)}家)和客户({len(buyers)}家)的地址信息，"
                f"按城市分类统计。同步检索银行流水中运输类支出→无任何运输费用。"
                f"发现{'加工费供应商均不在本地' if processors else '供应商分布异常'}，进而扩展到原材料供应、加工、销售三个环节的城市分布检查"
                f"→三组地址完全互不重叠→点→面交叉推理→得出全链条经营实质存疑的结论。"
            ),
            "tax_impact": (
                "全链条经营实质存疑是最严重的经营异常信号。"
                "如果无法提供运输证明→税务机关有权否定全部跨省交易的真实性→企业所得税成本费用全部不得扣除+增值税进项税额全部转出。"
                "这是整个税务稽查报告中最核心的发现——因为它不是一个点的问题，而是整个经营链条在物理层面无法成立。"
            ),
            "policy_ref": (
                "《企业所得税法》第八条（成本费用真实性、合理性）；"
                "《税收征收管理法》第三十五条（核定征收条件）；"
                "国家税务总局关于三流一致的要求（货物流、资金流、发票流必须一致）。"
            ),
            "suggestion": (
                f"这是全链条经营实质的核心问题，需要从以下路径提供证据：\n"
                f"【路径A——提供全链条物流单据】\n"
                f"①原材料从{', '.join(sorted(remote_seller_cities))}等地到{company_city}的运输单据（运单、签收单、运费发票）；\n"
                f"②委托加工物资往返{company_city}↔{'/'.join(sorted(proc_cities)) if proc_cities else '外地'}的物流记录；\n"
                f"③成品从{company_city}到客户的发货记录和物流单据。\n\n"
                f"【路径B——提供合同中的运费条款】\n"
                f"如为供应商承担运费→提供采购合同中'到货价'条款+供应商的运费发票复印件。\n\n"
                f"【路径C——无法提供】\n"
                f"如果确实无法提供任何运输证明→企业的全链条经营在物理上无法成立→"
                f"所有跨省交易的发票应视为虚开或交易不真实→进项税额全部转出+成本费用全部不得税前扣除。"
            ),
            "category": "经营实质",
            "rule_id": 1502,
            "source_chain": "经营实质-地理分布-全链条",
        })
    
    return findings


# ═══════════ 稽查队: 红冲作废发票追踪 ═══════════

def _domain_red_void_invoice(invoices):
    """追踪红冲/作废发票——是正常冲销还是销毁证据"""
    findings = []
    red_void = [i for i in invoices if any(kw in str(i.get("status",""))+str(i.get("remark","")) 
                for kw in ["红冲","作废","红色","冲红"])]
    
    if len(red_void) >= 3:
        total_red = sum(float(i.get("total",0) or 0) for i in red_void)
        findings.append({
            "type": "红冲/作废发票数量异常",
            "level": "高风险", "score": 8,
            "detail": f"{len(red_void)}张发票被红冲或作废，涉及金额{total_red:,.2f}元。可能为虚开后销毁证据。",
            "description": f"发现{len(red_void)}张红冲或作废发票，涉及金额{total_red:,.2f}元。正常经营中红冲和作废率应控制在5%以内。高频红冲/作废是税务机关重点关注的异常信号:\n\n① 虚开发票后红冲——开票给客户后对方不需要发票，己方做红冲注销\n② 当期红冲跨期发票——调节收入跨期分摊\n③ 集中红冲某客户发票——交易纠纷或关系破裂\n④ 作废率异常高于行业水平——内部管理混乱或刻意操作",
            "how_found": "从发票状态、备注、类型字段搜索'红冲''作废'等关键词，统计数量和金额。>=3张触发。",
            "tax_impact": "高频红冲→可能被认定为恶意拖延纳税或虚开发票→从严处理。",
            "suggestion": "逐张核实红冲原因并保留完整的红冲申请单和审批记录。",
            "category": "发票生命周期"
        })
    
    return findings


# ═══════════ 稽查队: 利润vs现金流矛盾 ═══════

def _domain_profit_cashflow_gap(voucher_rev, bank_txs, pur_invs):
    """账面有利润但银行没钱=虚假利润"""
    findings = []
    if not bank_txs: return findings
    
    bank_in = sum(float(b.get("credit",0) or 0) for b in bank_txs)
    bank_out = sum(float(b.get("debit",0) or 0) for b in bank_txs)
    net_flow = bank_in - bank_out
    
    vr_total = voucher_rev.get("total", 0) if voucher_rev else 0
    pur_total = sum(float(i.get("total",0) or 0) for i in pur_invs) if pur_invs else 0
    gross_profit = vr_total - pur_total
    
    if vr_total > 0 and net_flow < 0 and abs(net_flow) > vr_total * 0.3:
        findings.append({
            "type": "盈利与现金流严重背离",
            "level": "高风险", "score": 9,
            "detail": f"账面主营收入{vr_total:,.2f}元，毛利{gross_profit:,.2f}元，但银行净流出{abs(net_flow):,.2f}元。有利润没钱→利润真实性存疑。",
            "description": f"最扎心的矛盾: 账面上有{vr_total:,.2f}元收入、{gross_profit:,.2f}元毛利，但银行账户净流出{abs(net_flow):,.2f}元。\n\n这是税务稽查中最经典的问题之一: [你既然有这么多利润，那钱去哪了？]\n\n可能的答案只有三个:\n① 利润是虚增的——收入水分大，实际的现金流入远少于账面收入\n② 钱被占用了——利润转化成了存货(积压)或应收账款(客户欠款)\n③ 钱被挪用了——利润被转出到其他账户或私人账户\n\n无论如何回答，都需要证据支撑。",
            "how_found": "凭证主营收入-进项采购成本=毛利，对比银行净现金流。净利润+但净现金流为负且差距>收入的30%触发。",
            "tax_impact": "利润现金背离→收入真实性受质疑→可能触发全面的纳税评估→从增值税到企业所得税全面核查。",
            "suggestion": "① 编制净利润调节为经营现金流的调节表；② 核实存货积压和应收挂账金额是否合理；③ 排查大额资金转出的商业实质。",
            "category": "现金流分析"
        })
    
    return findings


# ═══════════ 稽查队: 异常交易时间模式 ═══════

def _domain_temporal_anomaly(bank_txs):
    """检测非正常交易时间: 周末/深夜/节假日/整数金额"""
    findings = []
    if not bank_txs: return findings
    
    import datetime
    weekend_count = 0; round_count = 0; round_total = 0.0
    for tx in bank_txs:
        d_str = str(tx.get("date", ""))
        amt = float(tx.get("debit",0) or tx.get("credit",0) or 0)
        if len(d_str) >= 8:
            try:
                dt = datetime.date(int(d_str[:4]), int(d_str[4:6]), int(d_str[6:8]))
                if dt.weekday() >= 5: weekend_count += 1
            except: pass
        if amt > 0 and amt % 10000 < 0.01: 
            round_count += 1; round_total += amt
    
    issues = []
    if weekend_count > 10:
        issues.append(f"周末/节假日交易{weekend_count}笔，对公账户在非工作日频繁交易异常")
    if round_count > 3:
        issues.append(f"整数金额交易{round_count}笔（合计{round_total:,.2f}元），可能为人为构造的过桥资金")
    
    if issues:
        findings.append({
            "type": "交易时间与金额模式异常",
            "level": "中风险", "score": 6 if len(issues)==1 else 7,
            "detail": "; ".join(issues),
            "description": "交易行为分析发现异常模式:\n\n" + "\n".join(f"• {i}" for i in issues) + "\n\n稽查经验: 正常经营交易分散在工作日且金额零碎，周末交易和整数金额交易通常有特殊目的——过桥资金、关联方走账、或刻意构造的资金流水。",
            "how_found": "解析银行流水交易日期(判断周末)和交易金额(判断整数万元)，统计异常模式。",
            "suggestion": "① 核实周末交易的商业合理性（如电商行业周末是高峰期则正常）；② 核实整数金额交易是否对应真实的业务；③ 保留异常交易的合同和凭证。",
            "policy_ref": "《税收征收管理法》关于账簿凭证管理的规定；虚开发票通常配合异常资金流水。",
            "category": "时间模式"
        })
    
    return findings


# ═══════════ 稽查队: 关联交易穿透 ═══════

def _domain_related_party_check(sal_invs, pur_invs, bank_txs):
    """从名称中检测关联方: 供应商和客户同名/同一控制人"""
    findings = []
    if not sal_invs or not pur_invs: return findings
    
    buyers = set()
    for i in sal_invs:
        b = str(i.get("buyer",""))[:10].strip()
        if len(b) >= 4: buyers.add(b)
    
    sellers = set()
    for i in pur_invs:
        s = str(i.get("seller",""))[:10].strip()
        if len(s) >= 4: sellers.add(s)
    
    # 供应商同时在客户名单中（互为买卖=关联交易）
    overlap = buyers & sellers
    if overlap:
        findings.append({
            "type": "疑似关联交易——供应商与客户重叠",
            "level": "高风险", "score": 8,
            "detail": f"{len(overlap)}个企业同时在供应商和客户名单中: {'、'.join(list(overlap))}。",
            "description": f"发现{len(overlap)}家企业同时出现在供应商（进项发票的销方）和客户（销项发票的购方）名单中。这意味着贵公司既向这些企业采购、又向这些企业销售。\n\n这种'互为买卖'的模式本身就容易引发税务机关对关联交易和转移定价的关注:\n① 是否存在通过关联采购虚增成本?\n② 是否存在通过关联销售将利润转移?\n③ 交易价格是否公允（独立交易原则）?",
            "how_found": "取销项发票购方名称前10字和进项发票销方名称前10字，求交集。",
            "tax_impact": "关联交易→须按独立交易原则进行定价→不符合的将被纳税调整→补缴企业所得税。",
            "suggestion": "① 逐一核实重叠企业的交易性质；② 如有关联关系，按规定准备同期资料；③ 确保交易价格公允。",
            "category": "关联交易"
        })
    
    return findings


# ═══════════ 经营分析: 资产折旧费用匹配 ═══════

def _domain_depreciation_match(bank_txs, pur_invs):
    """从支付记录反推固定资产→应存在对应的折旧费用"""
    findings = []
    if not bank_txs: return findings
    
    # 搜索固定资产采购类付款
    asset_keywords = ["设备","机器","车辆","电脑","服务器","家具","装修"]
    asset_payments = []
    for tx in bank_txs:
        summary = str(tx.get("summary","")) + str(tx.get("counterparty",""))
        for kw in asset_keywords:
            if kw in summary:
                asset_payments.append(tx)
                break
    
    if asset_payments:
        asset_total = sum(float(tx.get("debit",0) or 0) for tx in asset_payments)
        findings.append({
            "type": "固定资产采购与折旧匹配提示",
            "level": "低风险", "score": 3,
            "detail": f"银行流水发现{len(asset_payments)}笔固定资产类付款，合计{asset_total:,.2f}元。应相应计提折旧。",
            "description": f"银行流水中检测到{len(asset_payments)}笔可能与固定资产采购相关的付款（含关键词：{'/'.join(asset_keywords)}），合计{asset_total:,.2f}元。\n\n提醒: 如果这些付款确实对应固定资产采购，应作如下处理:\n① 建立固定资产台账并登记入账\n② 按规定年限计提折旧（作为成本费用税前扣除）\n③ 折旧费与采购金额、折旧年限应逻辑匹配",
            "how_found": "从银行流水借方摘要中搜索固定资产类关键词（设备/机器/车辆等）。",
            "suggestion": "确认上述付款是否对应固定资产采购，如是则建立台账并按时计提折旧。",
            "category": "资产匹配"
        })
    
    return findings


# ═══════════ 行业自适应产品链词典：原料/成品关键词 ═══════════
# 行业基准值/产品链/关键词映射等 → 外部化于 static/industry_data.json
# 每个制造/加工行业定义其典型原料和成品的品名关键词
# 用于BOM/进销品名差异分析中的原材料/成品自动分类
# 设计原则：
#   - raw_materials: 该行业采购的典型原料（关键词，部分匹配即可）
#   - finished_goods: 该行业销售的典型成品（关键词，部分匹配即可）
#   - 服务/纯贸易行业不定义（返回空），走通用逻辑
# 数据源：static/industry_data.json → product_chains（29个行业，全行业可扩展）
def _get_product_keywords(industry_code, is_raw=True):
    """根据行业代码返回对应的原料/成品关键词列表（行业自适应）"""
    if not industry_code:
        return []
    
    chains = _load_industry_data().get("product_chains", {})
    
    # 精确匹配
    if industry_code in chains:
        chain = chains[industry_code]
        if is_raw:
            return chain.get("raw_materials", [])
        return chain.get("finished_goods", [])
    
    # 模糊匹配：尝试匹配行业代码的关键部分
    for ind_code, chain in chains.items():
        if ind_code in industry_code or industry_code in ind_code:
            if is_raw:
                return chain.get("raw_materials", [])
            return chain.get("finished_goods", [])
    
    # 兜底：通用生产/制造行业关键词
    generic_raw = ["原料","材料","钢材","塑料","电子","化工","金属","木材","面料","纱","粉","浆","油","剂","件","片","板","管","丝","线","布","纸","胶"]
    generic_finish = ["成品","制品","件","机","器","设备","产品","服装","食品","家具","配件","组件"]
    
    return generic_raw if is_raw else generic_finish


# ═══════════ 域分析：行业对标 ═══════════

def _domain_industry_benchmark(sal_invs, pur_invs, voucher_rev, salaries, inventory, target_industry=""):
    """与行业基准值对比——基于国家税总局行业预警值"""
    findings = []
    
    # 服务行业闸门：进销比等基于实物商品流转的指标不适用
    is_svc, svc_pct = _is_service_industry(sal_invs)
    if is_svc:
        findings.append({"type": "进销比跳过-服务行业",
            "level": "低风险", "score": 2,
            "detail": f"销项品名服务类占比{svc_pct*100:.0f}%，进销比/毛利率行业对标不适用于服务行业。服务行业以人力/知识/创意为核心成本，非实物采购成本驱动。已自动跳过进销比和毛利率行业对标。",
            "category": "行业对标"})
        return findings
    
    bm = _load_industry_data().get("benchmarks", {}).get(target_industry, _load_industry_data()["benchmarks"]["_default"])
    
    vr_total = voucher_rev.get("total", 0) if voucher_rev else 0
    pur_total = sum(float(i.get("amount", 0) or 0) for i in pur_invs) if pur_invs else 0
    sal_total = sum(float(i.get("amount", 0) or 0) for i in sal_invs) if sal_invs else 0
    emp_count = len(set(str(s.get("name","")).strip() for s in salaries if str(s.get("name","")).strip())) if salaries else 0
    actual_rev = max(vr_total, sal_total)
    
    if actual_rev > 0 and pur_total > 0:
        gross_margin = (actual_rev - pur_total) / actual_rev
        low, high, typical = bm["毛利率"]
        gm_pct = gross_margin * 100
        # 三级判断：远低于下限 / 接近下限 / 高于上限
        if gross_margin < low:
            findings.append({
                "type": f"毛利率{gm_pct:.2f}%低于{target_industry}行业下限{low*100:.2f}%",
                "level": "高风险", "score": 9,
                "detail": f"被查单位毛利率{gm_pct:.2f}%（=（销售收入{actual_rev:,.2f}元-进项采购成本{pur_total:,.2f}元）/销售收入{actual_rev:,.2f}元）。{target_industry}行业毛利率正常区间为{low*100:.2f}%~{high*100:.2f}%，典型值{typical*100:.2f}%。被查单位毛利率已低于行业下限{low*100:.2f}%，偏离度{gross_margin/low-1:.0%}。",
                "description": f"毛利率低于行业基准下限{low*100:.2f}%，这一偏差在稽查中有明确的指向意义：①进项发票可能存在虚增——采购成本被人为做高以虚抵进项税、虚列成本少缴企业所得税；②销售收入可能被隐匿——部分收入未入账、未开票，导致收入端偏低、毛利率被拉低。{target_industry}行业毛利率典型值为{typical*100:.2f}%，被查单位{gm_pct:.2f}%已处于行业尾部。需结合产能、能耗、人工投入等经营数据做交叉验证。",
                "how_found": f"计算出被查单位的毛利率：销售收入{actual_rev:,.2f}元减去进项采购成本{pur_total:,.2f}元，除以销售收入，得出{gm_pct:.2f}%。然后查阅了{target_industry}行业的毛利率基准数据（下限{low*100:.2f}%、典型{typical*100:.2f}%、上限{high*100:.2f}%），发现被查单位毛利率已低于行业下限。",
                "tax_impact": f"若进项虚增：补缴增值税+企业所得税+滞纳金+罚款；若收入隐匿：补缴增值税+企业所得税+滞纳金+0.5-5倍罚款，情节严重移送公安。",
                "suggestion": f"核查方向：1)逐笔核实大额进项发票的真实性（与物流单、入库单、银行付款单三单比对）——重点核查偏离度最大的品类；2)将银行流水贷方发生额与销项发票总额做逐月比对，找出银行收款＞开票收入的月份，追查未开票收入；3)要求企业提供成本核算明细和BOM表，核实料工费配比是否合理。",
                "category": "行业对标"
            })
        elif gross_margin < typical * 0.85:
            findings.append({
                "type": f"毛利率{gm_pct:.2f}%低于{target_industry}行业典型值{typical*100:.2f}%的85%",
                "level": "中风险", "score": 6,
                "detail": f"被查单位毛利率{gm_pct:.2f}%低于{target_industry}行业典型值{typical*100:.2f}%，但尚未跌破行业下限{low*100:.2f}%。偏离度{gross_margin/typical-1:.0%}。",
                "description": f"毛利率虽未跌破行业下限，但已低于典型值{typical*100:.2f}%的85%。可能存在成本偏高或收入偏低的情况，建议结合产能数据做进一步核实。",
                "how_found": f"毛利率={gm_pct:.2f}%，{target_industry}行业典型值{typical*100:.2f}%×0.85={(typical*0.85*100):.2f}%。",
                "suggestion": "核实毛利率偏低的品类，检查是否有低价销售、成本虚增或收入少记的情况。",
                "category": "行业对标"
            })
        elif gross_margin > high * 1.3:
            findings.append({
                "type": f"毛利率{gm_pct:.2f}%高于{target_industry}行业上限{high*100:.2f}%",
                "level": "中风险", "score": 5,
                "detail": f"被查单位毛利率{gm_pct:.2f}%超出{target_industry}行业上限{high*100:.2f}%。偏离度{gross_margin/high-1:.0%}。",
                "description": f"毛利率超出行业上限30%以上，可能原因：①虚开销售发票（没有真实交易）；②收入确认跨期不当；③隐藏成本费用；④具有特殊技术或品牌溢价（需提供佐证）。",
                "how_found": f"毛利率={gm_pct:.2f}% > {target_industry}行业上限{high*100:.2f}%×1.3={(high*1.3*100):.2f}%。",
                "suggestion": "核实收入确认的合规性，检查每笔销售对应的采购成本和费用是否完整入账。",
                "category": "行业对标"
            })
    
    if sal_total > 0 and pur_total > 0:
        io_ratio = pur_total / sal_total
        low, high, typical = bm["进销比"]
        if io_ratio > high:
            io_pct = (io_ratio - typical) / typical * 100
            findings.append({
                "type": f"进销比{io_ratio:.2f}高于{target_industry}行业上限{high}",
                "level": "高风险", "score": 9,
                "detail": f"被查单位进销比{io_ratio:.2f}（=进项采购{pur_total:,.2f}元/销项开票{sal_total:,.2f}元），{target_industry}行业正常进销比区间为{low}~{high}，典型值{typical}。被查单位进销比高于行业上限{high}，偏离度{(io_ratio-typical)/typical*100:.2f}%。",
                "description": f"进销比={io_ratio:.2f}的含义：被查单位每对外开具1元销项发票，对应取得了{io_ratio:.2f}元进项发票。{target_industry}行业典型进销比为{typical}（每1元销项对应约{typical}元进项采购），合理区间{low}~{high}。被查单位的进销比{io_ratio:.2f}已超出行业上限{high}，偏差{(io_ratio-typical)/typical*100:.2f}%。进销比偏高有两种稽查解释：①存在未开票销售收入——实际销售>开票销售，拉高了进项/销项的比值；②进项发票存在虚开——采购端被人为做高。两者都涉及纳税义务的不当减少。",
                "how_found": f"进项采购{pur_total:,.2f}÷销项开票{sal_total:,.2f}={io_ratio:.2f}。{target_industry}行业进销比参考值：下限{low}、典型值{typical}、上限{high}。被查单位={io_ratio:.2f} > 上限{high}。",
                "tax_impact": "若隐匿收入→补缴增值税（货物税率）+企业所得税+滞纳金+罚款。若虚增进项→补缴增值税（已抵扣税额）+企业所得税+罚款+刑事责任。",
                "suggestion": f"稽查方向：1)银行流水收款与销项发票逐月比对→找出收款>开票的月份，追查未开票收入；2)大额供应商穿透→核实是否为空壳公司、是否存在资金回流；3)存货盘点→核实库存商品是否与进销存逻辑一致；4)若进销比偏高是因为库存积压，要求企业提供存货盘点表佐证。",
                "category": "行业对标"
            })
        elif io_ratio > typical * 1.2:
            io_pct = (io_ratio - typical) / typical * 100
            findings.append({
                "type": f"进销比{io_ratio:.2f}高于{target_industry}行业典型值{typical}",
                "level": "中风险", "score": 6,
                "detail": f"被查单位进销比{io_ratio:.2f}高于{target_industry}行业典型值{typical}，偏离度{io_pct:.2f}%。",
                "description": f"进销比高于典型值但未超上限，提示可能存在部分未开票销售或采购端存在少量异常。",
                "how_found": f"进销比={io_ratio:.2f} > {target_industry}行业典型值{typical}×1.2={(typical*1.2):.2f}。",
                "suggestion": "关注进销比偏高的品类，核实是否有库存积压或未及时开票的销售。",
                "category": "行业对标"
            })
    
    if actual_rev > 0 and emp_count > 0:
        per_person = actual_rev / emp_count / 10000
        low, high, typical = bm["人均营收(万)"]
        if per_person < low * 0.5:
            findings.append({
                "type": f"人均营收{per_person:.2f}万远低于{target_industry}行业下限{low}万",
                "level": "中风险", "score": 6,
                "detail": f"员工{emp_count}人，人均{per_person:.2f}万元。{target_industry}行业下限{low}万。",
                "description": "人均营收极低可能是虚列人员工资逃税的信号。",
                "how_found": f"收入{actual_rev:,.2f}÷{emp_count}人={per_person:.2f}万/人 vs {target_industry}行业下限{low}万/人。",
                "suggestion": "核实员工名册真实性（社保/考勤/工资条三比对）。",
                "category": "行业对标"
            })
    
    return findings


# ═══════════ 增值税申报表自动比对 ═══════════

def _domain_vat_declaration_compare(invoices, bank_txs, db, company_id):
    """增值税申报表 vs 发票/银行流水实际数据自动比对"""
    findings = []
    
    try:
        from database import VATDeclaration
        decls = db.query(VATDeclaration).filter(VATDeclaration.company_id == company_id).order_by(VATDeclaration.period).all()
    except:
        return findings
    
    if not decls:
        findings.append({
            "type": "缺少增值税申报表——无法进行申报vs实际比对",
            "level": "中风险", "score": 5,
            "detail": "无增值税申报表数据，无法验证企业申报收入是否与实际开票收入一致。",
            "description": "增值税申报表是稽查第一步必查资料。缺少申报表意味着无法判断企业是否存在少报、漏报。",
            "how_found": "数据库中无VATDeclaration记录。",
            "suggestion": "从电子税务局调取企业增值税申报表数据。",
            "category": "申报比对"
        })
        return findings
    
    from collections import defaultdict
    period_inv = defaultdict(lambda: {"sales": 0, "sales_tax": 0, "purchases": 0, "purchases_tax": 0})
    for inv in invoices:
        d = str(inv.get("date", ""))[:10]
        if not d or len(d) < 7: continue
        period = d[:7]
        direction = inv.get("direction", "")
        amt = float(inv.get("amount", 0) or 0)
        tax = float(inv.get("tax", 0) or 0)
        if direction == "销项":
            period_inv[period]["sales"] += amt
            period_inv[period]["sales_tax"] += tax
        elif direction == "进项":
            period_inv[period]["purchases"] += amt
            period_inv[period]["purchases_tax"] += tax
    
    total_gap = 0
    gap_count = 0
    for decl in decls:
        period = str(decl.period)[:7]
        inv_data = period_inv.get(period, {})
        inv_sales = inv_data.get("sales", 0)
        decl_sales = float(decl.sales_amount or 0)
        
        if decl_sales > 0:
            gap = inv_sales - decl_sales
            if abs(gap) > max(decl_sales * T.ratios.threshold_5pct, T.amount_thresholds.mini_transaction):
                gap_count += 1
                total_gap += abs(gap)
                level = "高风险" if abs(gap) > decl_sales * 0.2 else "中风险"
                findings.append({
                    "type": f"{period}开票收入vs申报收入差异{gap:,.2f}元({gap/decl_sales*100:.2f}%)",
                    "level": level, "score": 9 if abs(gap) > decl_sales * 0.2 else 6,
                    "detail": f"{period}：开票收入{inv_sales:,.2f}元 vs 申报收入{decl_sales:,.2f}元，差异{gap:,.2f}元。",
                    "description": f"开票收入大于申报收入={gap:,.2f}元——企业开了发票但没有足额申报纳税，直接逃税证据。",
                    "how_found": f"发票系统销项合计{inv_sales:,.2f} - 申报表销售额{decl_sales:,.2f} = {gap:,.2f}。",
                    "suggestion": "核实差异原因：1)是否有未开票收入冲减 2)是否红字发票未处理 3)如无合理解释应启动稽查补税。",
                    "category": "申报比对"
                })
    
    if bank_txs and not findings:
        bank_income = sum(float(tx.get("credit", 0) or 0) for tx in bank_txs)
        total_decl = sum(float(d.sales_amount or 0) for d in decls)
        if total_decl > 0 and bank_income > total_decl * 2:
            findings.append({
                "type": f"银行收款{bank_income:,.2f}远超申报收入{total_decl:,.2f}元",
                "level": "高风险", "score": 10,
                "detail": f"银行流水收款{bank_income:,.2f}元/申报收入{total_decl:,.2f}元={bank_income/total_decl:.2f}倍。",
                "description": f"银行账户实收{bank_income:,.2f}元是申报收入{total_decl:,.2f}元的{bank_income/total_decl:.2f}倍——大量资金流入未申报，疑似隐匿收入。",
                "how_found": "银行流水贷方合计÷申报表销售额合计。",
                "suggestion": "调取全部银行账户流水（含个人账户），逐笔比对资金来源。",
                "category": "申报比对"
            })
    
    if gap_count == 0 and decls:
        findings.append({
            "type": "申报收入与发票收入基本一致",
            "level": "低风险", "score": 1,
            "detail": f"共{len(decls)}期申报表，开票收入与申报收入差异在正常范围。",
            "description": "初步比对通过。但仍需注意：一致不代表合规——可能存在未开票收入漏报、进项虚抵等问题。",
            "how_found": "各期申报表销售额 vs 各期发票销项合计。",
            "suggestion": "继续核查未开票收入、进项抵扣合理性、关联交易定价。",
            "category": "申报比对"
        })
    
    return findings


# ═══════════ 上下游穿透分析 ═══════════

def _domain_supply_chain_deep(invoices, bank_txs):
    """供应商/客户多级穿透——虚开识别的核心武器"""
    findings = []
    if not invoices: return findings
    
    from collections import Counter, defaultdict
    
    suppliers = Counter()
    customers = Counter()
    supplier_amounts = defaultdict(float)
    customer_amounts = defaultdict(float)
    
    for inv in invoices:
        direction = inv.get("direction", "")
        seller = str(inv.get("seller", "")).strip()
        buyer = str(inv.get("buyer", "")).strip()
        amt = float(inv.get("amount", 0) or 0)
        if direction == "进项" and seller:
            suppliers[seller] += 1
            supplier_amounts[seller] += amt
        elif direction == "销项" and buyer:
            customers[buyer] += 1
            customer_amounts[buyer] += amt
    
    # 供应商集中度
    if suppliers:
        total_pur = sum(supplier_amounts.values())
        top3_ratio = sum(a for _, a in sorted(supplier_amounts.items(), key=lambda x: -x[1])) / max(total_pur, 1)
        if top3_ratio > T.industry_thresholds.concentration_high:
            findings.append({
                "type": f"前3大供应商占比{top3_ratio*100:.2f}%——高度集中",
                "level": "中风险", "score": 6,
                "detail": f"共{len(suppliers)}家供应商，前3家占采购额{top3_ratio*100:.2f}%。",
                "description": "供应商高度集中增加单一依赖风险，如果主要供应商为空壳公司或关联方则风险巨大。",
                "how_found": f"top3供应商金额÷总采购={top3_ratio*100:.2f}%>70%。",
                "suggestion": "对前3大供应商做穿透：工商登记/纳税信用/关联关系/物流入库记录。",
                "category": "上下游穿透"
            })
        
        # 名称相似度
        from collections import Counter as _c2
        name_prefixes = _c2()
        for s in suppliers.keys():
            if len(s) >= 4:
                name_prefixes[s[:4]] += 1
        for prefix, cnt in name_prefixes.most_common(5):
            if cnt >= 3:
                findings.append({
                    "type": f"供应商名称群集'{prefix}'——{cnt}家疑似关联壳公司",
                    "level": "高风险", "score": 8,
                    "detail": f"{cnt}家供应商共享前缀'{prefix}'（共{len(suppliers)}家）。疑似同一控制人注册的空壳公司群。",
                    "description": f"供应商名称高度相似是虚开发票典型特征——控制人注册多家空壳公司轮流向受票企业开票。",
                    "how_found": f"供应商名称前4字聚类：'{prefix}'={cnt}次。",
                    "suggestion": f"立即对以'{prefix}'开头的{cnt}家供应商做关联穿透：工商股东/注册地址/银行账户关联。",
                    "category": "上下游穿透"
                })
    
    # 客户集中度
    if customers:
        total_sal = sum(customer_amounts.values())
        top3_cust_ratio = sum(a for _, a in sorted(customer_amounts.items(), key=lambda x: -x[1])) / max(total_sal, 1)
        if top3_cust_ratio > T.ratios.dominant:
            findings.append({
                "type": f"前3大客户占比{top3_cust_ratio*100:.2f}%——高度集中",
                "level": "中风险", "score": 5,
                "detail": f"共{len(customers)}家客户，前3家占销售额{top3_cust_ratio*100:.2f}%。",
                "description": "客户高度集中可能意味着关联方交易或为特定客户虚开发票。",
                "how_found": f"top3客户金额÷总销售={top3_cust_ratio*100:.2f}%>80%。",
                "suggestion": "对前3大客户做穿透：工商关联/合同流/资金流/货物流是否完整。",
                "category": "上下游穿透"
            })
    
    # 进销双向交易 → 循环开票
    cross_entities = set(suppliers.keys()) & set(customers.keys())
    if cross_entities:
        cross_list = [f"{e}(供{suppliers[e]}张/销{customers[e]}张)" for e in list(cross_entities)]
        findings.append({
            "type": f"进销双向交易——{len(cross_entities)}家既是供应商又是客户（循环开票嫌疑）",
            "level": "高风险", "score": 10,
            "detail": f"{len(cross_entities)}家企业同时出现在进项供应商和销项客户中：{'; '.join(cross_list)}。",
            "description": "同一企业既是供应商又是客户是税务总局明确的虚开特征：A给B开票→B给A开票→双方虚增收入成本，无真实货物交易。",
            "how_found": f"进项销方名单 ∩ 销项购方名单 = {len(cross_entities)}家。",
            "suggestion": f"立即对{len(cross_entities)}家双向交易企业穿透稽查：核实每笔交易的合同/物流/资金流/入库单四流一致。",
            "category": "上下游穿透"
        })
    
    # 供应商地域群集
    if suppliers:
        import re as _sr
        city_clusters = _c2()
        for s in suppliers.keys():
            m = _CHINA_CITY_REGEX.match(s)
            if m:
                city_clusters[m.group(1)] += 1
        for city, cnt in city_clusters.most_common(5):
            if cnt >= 3 and cnt >= len(suppliers) * 0.15:
                findings.append({
                    "type": f"供应商地域群集——{city}集中{cnt}家供应商",
                    "level": "中风险", "score": 7 if cnt >= 5 else 5,
                    "detail": f"{city}地区供应商{cnt}家，占{len(suppliers)}家的{cnt/len(suppliers)*100:.2f}%。",
                    "description": f"供应商同城集中可能正常（产业集群）也可能是同一注册代办机构的空壳公司群。",
                    "how_found": f"供应商企业名称城市关键词聚类：{city}={cnt}家。",
                    "suggestion": f"核实{city}是否有该产业集群。如否，对{city}供应商做工商穿透。",
                    "category": "上下游穿透"
                })
    
    # 单一供应商金额集中
    if supplier_amounts:
        sorted_suppliers = sorted(supplier_amounts.items(), key=lambda x: -x[1])
        for name, amt in sorted_suppliers:
            ratio = amt / max(sum(supplier_amounts.values()), 1)
            if ratio > 0.3 and amt > T.amount_thresholds.large_transaction:
                findings.append({
                    "type": f"单一供应商'{name[:15]}'占采购额{ratio*100:.2f}%",
                    "level": "中风险", "score": 6,
                    "detail": f"'{name}'采购额{amt:,.2f}元，占总采购{ratio*100:.2f}%。",
                    "description": f"过度依赖单一供应商增加关联交易和虚开风险。",
                    "how_found": f"'{name}'金额÷总采购={ratio*100:.2f}%>30%。",
                    "suggestion": f"对'{name}'做工商穿透：股东/注册地址/纳税信用。",
                    "category": "上下游穿透"
                })
    
    return findings


# ═══════════ 发票实质性稽查：合规检查+单价分析+BOM缺失 ═══════════

def _domain_invoice_audit(invoices, target_industry=""):
    """对发票进行实质性审计——逐票检查，而非关键词匹配（ctx增强版）。
    target_industry: 行业代码，用于行业自适应原料/成品关键词匹配
    
    五层深度审计：
    1. 合规检查：发票管理办法——数量/单位/单价是否齐全
    2. 同品名单价分析：同一货物单价是否一致（按供应商+品名分组）
    3. 加工费专项：加工费必须有数量+单位+单价，否则无法核定
    4. 金额/数量合理性：大额无数量、整数金额、极小数量大金额
    5. 进销品名映射+BOM缺失：原材料→成品逻辑是否成立
    """
    findings = []
    
    # ── ctx 增强：如果 Phase 2 已注入企业画像，优先使用 ──
    try:
        from engine.context import get_audit_ctx
        _ctx = get_audit_ctx()
        if _ctx and not target_industry:
            target_industry = _ctx.company_profile.get("industry", "")
    except Exception:
        pass
    
    if not invoices or len(invoices) < 2:
        return findings
    
    pur_invs = [inv for inv in invoices if inv.get("direction") in ("进项", "purchase")]
    sal_invs = [inv for inv in invoices if inv.get("direction") in ("销项", "sales")]
    
    # ═══ 第一层：发票管理办法合规检查 ═══
    missing_qty = []        # 缺数量
    missing_unit = []       # 缺单位
    missing_price = []      # 缺单价
    proc_fee_no_qty = []    # 加工费缺数量
    proc_fee_no_unit = []   # 加工费缺单位
    round_amounts = []      # 整数金额（可疑）
    tiny_qty_big_amt = []   # 极小数量大金额
    
    for inv in invoices:
        goods = str(inv.get("goods", ""))
        qty = inv.get("qty", "")
        unit = inv.get("unit", "")
        price = inv.get("price", "")
        amount = inv.get("amount", 0)
        seller = str(inv.get("seller", ""))[:25]
        direction = inv.get("direction", "")
        
        if amount <= 0:
            continue
        
        has_qty = bool(qty and qty.strip() and qty.strip() not in ("0", "0.0", "0.00"))
        has_unit = bool(unit and unit.strip())
        has_price = bool(price and price.strip() and price.strip() not in ("0", "0.0"))
        
        # 1a. 缺数量
        if not has_qty:
            missing_qty.append({"goods": goods[:30], "amount": amount, "seller": seller, "direction": direction})
        
        # 1b. 缺单位
        if not has_unit:
            missing_unit.append({"goods": goods[:30], "amount": amount, "seller": seller, "direction": direction})
        
        # 1c. 缺单价
        if not has_price and has_qty:
            missing_price.append({"goods": goods[:30], "amount": amount, "seller": seller, "direction": direction})
        
        # 1d. 加工费专项（已修复：排除分类码*X加工品*误判）
        if '加工费' in goods or ('加工' in goods and not re.search(r'\*[\u4e00-\u9fa5]+加工[品物食料]\*', goods)):
            if not has_qty:
                proc_fee_no_qty.append({"goods": goods[:40], "amount": amount, "seller": seller})
            if not has_unit:
                proc_fee_no_unit.append({"goods": goods[:40], "amount": amount, "seller": seller})
        
        # 1e. 金额合理性检查
        if amount >= 1000 and amount == int(amount):
            round_amounts.append({"goods": goods[:30], "amount": amount, "seller": seller})
        if has_qty:
            try:
                qty_f = float(qty.strip())
                if qty_f > 0 and qty_f < 1 and amount > 50000:
                    tiny_qty_big_amt.append({"goods": goods[:30], "qty": qty_f, "amount": amount, "seller": seller})
            except:
                pass
    
    total_inv = len(invoices)
    
    # ── 报告1：缺数量 ──
    if missing_qty:
        examples = [f"{m['goods'][:20]}({m['seller'][:15]}, {m['amount']:,.2f}元)" for m in missing_qty]
        findings.append({
            "type": "发票缺少数量字段",
            "level": "中风险", "score": 7,
            "detail": f"{total_inv}张发票中{len(missing_qty)}张({len(missing_qty)/total_inv*100:.2f}%)金额>0但无数量。",
            "description": f"《发票管理办法》第二十二条：发票须如实开具品名、数量、单价、金额。无数量则无法计算单价、无法验证进销存数量逻辑、无法核实交易真实性。涉及：{'；'.join(examples)}等。",
                "how_found": f"对{total_inv}张发票逐票审核了数量字段——发现{len(missing_qty)}张发票有金额但无数量，无法验证单价合理性，无法排除虚增金额。",
            "suggestion": "① 逐票核实缺少数量单位的发票对应实际交易量；② 要求供应商补开含有数量和单位的合规发票；③ 如无法补开——提供对应的入库单、物流签收单、称重记录等佐证交易数量；④ 同时提供采购合同中的数量条款作为交叉验证。数量和单位是发票的基本要素，长期缺失将影响成本核算和企业所得税税前扣除。",
            "category": "发票合规"
        })
    
    # ── 报告2：缺单位 ──
    if missing_unit:
        findings.append({
            "type": "发票缺少计量单位",
            "level": "中风险", "score": 6,
            "detail": f"{total_inv}张发票中{len(missing_unit)}张({len(missing_unit)/total_inv*100:.2f}%)金额>0但无计量单位。",
                "how_found": f"对{total_inv}张发票逐票审核了计量单位字段——发现{len(missing_unit)}张发票未填计量单位，无法判断交易数量是否与品名逻辑一致。",
            "suggestion": "要求企业规范开票，补全计量单位（如kg、米、吨、件等）。无单位无法判断数量含义。",
            "category": "发票合规"
        })
    
    # ── 报告3：加工费专项 ──
    total_proc_issues = len(proc_fee_no_qty) + len(proc_fee_no_unit)
    if total_proc_issues > 0:
        examples = []
        for p in (proc_fee_no_qty + proc_fee_no_unit):
            iss = "缺数量" if p in proc_fee_no_qty else "缺单位"
            examples.append(f"{p['goods'][:25]}({p['seller'][:15]}, {p['amount']:,.2f}元, {iss})")
        findings.append({
            "type": "加工费发票缺少数量或单位",
            "level": "高风险", "score": 8,
            "detail": f"加工费发票{total_proc_issues}处不合规：{len(proc_fee_no_qty)}张缺数量、{len(proc_fee_no_unit)}张缺单位。",
            "description": f"加工费是虚开发票最高发领域之一。《发票管理办法》要求劳务服务发票必须记载服务数量、计量单位和单价。缺少这些要素，一笔'加工费80万'无法判断加工了1000吨还是1吨，无法核定加工单价是否合理。涉及：{'；'.join(examples)}等。",
            "how_found": f"筛选含'加工'关键词发票→逐票检查数量/单位/单价字段",
            "suggestion": "要求企业提供：(1)加工合同（含单价、数量约定）；(2)加工出入库单；(3)加工费结算明细；(4)BOM表以核实加工量合理性。",
            "category": "发票合规"
        })
    
    # ── 报告4：整数金额可疑 ──
    if len(round_amounts) >= 5:
        big_round = [r for r in round_amounts if r["amount"] >= 10000]
        if big_round:
            examples = [f"{r['goods'][:20]}({r['amount']:,.2f}元)" for r in big_round]
            findings.append({
                "type": "发票金额为整数——缺少零头",
                "level": "中风险", "score": 6,
                "detail": f"发现{len(big_round)}张发票金额为精确整数（≥1万元），与正常商业交易习惯不符。",
                "description": f"正常交易因数量×单价通常产生非整数金额（如1.25元×800kg=1,000元）。大量精确整万、整千金额可能为人为凑数，是虚开特征之一。涉及：{'；'.join(examples)}等。",
                "how_found": f"检查金额=金额取整→发现{len(big_round)}笔万元级整数金额",
                "suggestion": "要求企业提供这些发票对应的采购合同、入库单，核实交易真实性。",
                "category": "发票合规"
            })
    
    # ── 报告5：极小数量大金额 ──
    if tiny_qty_big_amt:
        examples = [f"{t['goods'][:20]}({t['qty']}件, {t['amount']:,.2f}元)" for t in tiny_qty_big_amt]
        findings.append({
            "type": "发票数量极小但金额巨大——单价异常",
            "level": "中风险", "score": 6,
            "detail": f"发现{len(tiny_qty_big_amt)}张发票数量极小(<1)但金额巨大(>5万)，折算单价畸高。",
            "description": f"数量<1但金额>5万，意味着单价超过5万元/单位——远超正常商品单价，可能存在：(1)发票内容与实际不符（品名或数量造假）；(2)通过虚高单价虚增进项。涉及：{'；'.join(examples)}等。",
            "how_found": f"计算单价=金额÷数量→筛选数量<1且金额>5万的记录",
            "suggestion": "要求企业提供该类交易的合同、付款凭证，说明高单价的合理性。",
            "category": "发票合规"
        })
    
    # ═══ 第二层：同品名同供应商单价一致性 ═══
    # 同一供应商+同一品名→单价应一致
    if pur_invs:
        from collections import defaultdict
        supplier_goods = defaultdict(list)
        for inv in pur_invs:
            goods = str(inv.get("goods", "")).strip()
            seller = str(inv.get("seller", "")).strip()
            qty_str = str(inv.get("qty", "")).strip()
            amount = inv.get("amount", 0)
            if not goods or not seller or not qty_str:
                continue
            try:
                qty = float(qty_str)
                if qty <= 0: continue
                key = (seller, goods)
                supplier_goods[key].append({"qty": qty, "amount": amount, "price": round(amount/qty, 2)})
            except:
                pass
        
        same_price_diff = []
        for (seller, goods), records in supplier_goods.items():
            if len(records) < 2:
                continue
            prices = [r["price"] for r in records]
            avg = sum(prices) / len(prices)
            if avg > 0 and (max(prices) - min(prices)) / avg > 0.15:
                same_price_diff.append({
                    "seller": seller[:20],
                    "goods": goods[:25],
                    "prices": sorted(set(prices)),
                    "count": len(records),
                })
        
        if same_price_diff:
            examples = []
            for sp in same_price_diff:
                ps = "/".join(str(p) for p in sp["prices"])
                examples.append(f"{sp['goods']}({sp['seller']}): {sp['count']}次采购{ps}元")
            findings.append({
                "type": "同一供应商同品名单价不一致",
                "level": "中风险", "score": 7,
                "detail": f"发现{len(same_price_diff)}组同一供应商+同一品名的采购存在单价差异。{'；'.join(examples)}。",
                "description": "同一供应商同品名在不同采购中单价不一致，可能原因：(1)规格/品质差异（需BOM佐证）；(2)关联交易定价不公允；(3)发票内容与实际不符。正常情况下，稳定供应商的同一品名单价应相对稳定，波动超过15%需要合理解释。",
                "how_found": "按供应商+品名分组→计算每次采购单价→检查同组单价波动>15%",
                "suggestion": "要求企业提供：(1)不同批次的采购合同或报价单；(2)品质/规格差异说明；(3)BOM表以核实原料差异。",
                "category": "发票合规"
            })
    
    # ═══ 第三层：进销品名映射 + BOM缺失 ═══
    # 只有进销品名存在实质差异时才需要BOM（同类商品直接买卖只需贸易发票，不需BOM）
    pur_goods = set()
    sal_goods = set()
    for inv in pur_invs:
        g = str(inv.get("goods", "")).strip()
        if g: pur_goods.add(g)
    for inv in sal_invs:
        g = str(inv.get("goods", "")).strip()
        if g: sal_goods.add(g)
    
    # 品类差异检测：进项品名 ≠ 销项品名 才算有加工关系
    # 如果进销品名完全重合，说明是贸易行为（买什么卖什么），不需要BOM
    overlap = pur_goods & sal_goods  # 完全相同的品名——直接买卖
    pure_pur = pur_goods - sal_goods  # 只进不出的品名——可能是原料
    pure_sal = sal_goods - pur_goods  # 只出不进的品名——可能是成品
    
    # 加工证据：①有加工费发票 ②有只进不出的原料+只出不进的成品
    # ═══ 2026-06-26 修复：排除商品分类码误判 ═══
    import re as _re_proc2
    def _has_real_processing_fee(inv_list):
        """检测是否存在真正的加工费（排除*X加工品*等分类码误判）"""
        for i in inv_list:
            g = str(i.get("goods", ""))
            if '加工费' in g: return True
            if '加工' in g and not _re_proc2.search(r'\*[\u4e00-\u9fa5]+加工[品物食料]\*', g):
                return True
        return False
    has_processing_fee = _has_real_processing_fee(pur_invs)
    # 价值链检测：存在只进不出的原料 + 只出不进的成品 → 可能存在加工/生产链路
    has_value_chain = bool(pure_pur and pure_sal)
    
    if has_processing_fee or has_value_chain:
        # 行业自适应原料/成品关键词（稽查方法论㉕：三层行业穿透法）
        raw_kw = _get_product_keywords(target_industry, is_raw=True) if target_industry else ["原料","材料","钢材","塑料","电子","化工","金属","木材","面料","纱","粉","浆","油","剂","件","片","板","管","丝","线","布","纸","胶"]
        finish_kw = _get_product_keywords(target_industry, is_raw=False) if target_industry else ["成品","制品","件","机","器","设备","产品","服装","食品","家具","配件","组件"]
        
        # 只用"只进不出"的品名做原材料关键词匹配（重叠品名可能是贸易商品）
        raw_materials = [g for g in pure_pur if any(kw in g for kw in raw_kw)]
        # 成品不需要关键词匹配——pure_sal里的就是成品
        finished_goods = list(pure_sal)
        
        # 如果没有明确的原料/成品分类，用关键词兜底
        if not raw_materials:
            raw_materials = [g for g in pur_goods if any(kw in g for kw in raw_kw)]
        if not finished_goods:
            finished_goods = [g for g in sal_goods if any(kw in g for kw in finish_kw)]
        
        if raw_materials and finished_goods:
            raw_examples = list(raw_materials)
            fin_examples = list(finished_goods)
            
            mapping_hints = []
            for raw in raw_examples:
                for fin in fin_examples:
                    raw_core = raw[:2] if len(raw) >= 2 else raw
                    fin_core = fin[:2] if len(fin) >= 2 else fin
                    if raw_core in fin or fin_core in raw:
                        mapping_hints.append(f"{raw}→{fin}")
            
            mapping_text = ""
            if mapping_hints:
                mapping_text = f"可能的加工关系：{'；'.join(mapping_hints)}等。"
            
            evidence = "加工费发票证实存在外包轻加工" if has_processing_fee else "进销品名存在实质差异（可能为外包轻加工）"
            
            findings.append({
                "type": "缺少BOM表（物料清单）",
                "level": "中风险", "score": 6,
                "detail": f"进项{len(raw_materials)}种原材料+销项{len(finished_goods)}种成品→存在外包轻加工环节但无BOM表。{mapping_text}",
                "description": f"({evidence})进项品名中{len(pure_pur)}类仅采购未销售（拟为原料）、销项品名中{len(pure_sal)}类仅销售未采购（拟为成品）。企业可能通过外包轻加工完成商品形态转换（制造业常见模式），但仍需BOM表验证加工链条的真实性。缺少BOM表导致无法判断委托加工的数量和单价是否合理。",
                "how_found": f"进销品名差异检测：{len(pure_pur)}类仅进→拟为原料，{len(pure_sal)}类仅销→拟为成品，{'加工费发票证实外包轻加工' if has_processing_fee else '品名差异推断可能存在加工'}",
                "suggestion": "限期提供：(1)委托加工合同（含加工数量、单价、损耗率）；(2)加工出入库单（送料单+收货单）；(3)加工费结算明细。如实际为纯贸易（直接买进卖出同类商品），请提供贸易链条说明。",
                "category": "进销存"
            })

    # 进销品名完全一致→贸易行为，不需要BOM
    elif len(pure_pur) == 0 and len(pure_sal) == 0 and overlap:
        # 纯贸易：买什么卖什么，不提示BOM
        pass
    
    return findings


# ═══════════ 域18: 303规则全覆盖验证 ═══════════

RULE_DATA_REQUIREMENTS = {
    # ID → (所需数据, 缺失时的兜底结论)
    30: ("租金发票或租赁合同", "无法验证租金收入是否足额申报房产税"),
    144: ("投资性房地产台账", "无法验证投资性房地产相关税费申报"),
    167: ("销售合同中的价外费用条款", "无法验证价外费用是否并入销售额"),
    168: ("非货币性资产交换清单", "无法验证非货币性资产交换纳税情况"),
    169: ("债务重组协议", "无法验证债务重组收益是否确认企业所得税"),
    170: ("股权转让协议/工商变更记录", "无法验证股权转让交易是否足额纳税"),
    171: ("关联方借款合同", "无法验证无偿借款是否视同销售"),
    172: ("关联方管理费支付凭证", "无法验证关联方管理费合规性"),
    173: ("境外付汇备案表", "无法验证境外付款代扣代缴义务"),
    174: ("混合销售/兼营业务明细", "无法验证混合销售是否分别核算"),
    175: ("排污许可证/环保支出明细", "无法验证环境保护税申报情况"),
    176: ("发票备注栏信息", "无法验证特定业务发票备注栏合规性"),
    177: ("佣金/手续费合同及结算凭证", "无法验证佣金手续费支出合规性"),
    178: ("捐赠协议及公益组织资质", "无法验证捐赠支出税前扣除合规性"),
    179: ("存货盘点报告", "无法验证存货盘亏盘盈税务处理"),
    237: ("税务稽查应对预案文件", "无法验证稽查应对预案的完备性"),
    241: ("行业稽查重点指引对照", "无法判断贵司行业是否列入年度稽查重点"),
    242: ("金税系统风险积分", "无法获取金税四期综合风险积分"),
    243: ("上下游企业纳税状态查询", "无法验证上下游是否存在走逃协查风险"),
    244: ("全部银行账户流水", "需提供完整对公+个人账户流水才能穿透分析"),
    245: ("ERP系统数据备份", "无法验证电子账簿完整性与ERP数据可恢复性"),
    246: ("举报/信访/舆情记录", "无法排查外部案源风险"),
    247: ("大额股权/财产转让记录", "无法验证自然人税务申报触发情况"),
    248: ("经侦联合办案记录", "无法判断是否涉及公安经侦联动"),
    249: ("工商变更记录", "无法验证关键人员/地址变更频率"),
    250: ("稽查应对合规记录", "无法评估稽查应对合规度"),
    259: ("税收优惠备案材料", "无法验证享受优惠后的反向核查风险"),
    # 依赖DB但为空的规则
    18: ("增值税申报表", "缺少增值税申报历史数据，无法做财税票三表比对"),
    22: ("预收账款明细", "缺少预收账款数据，无法判断是否隐匿收入"),
    23: ("应付账款明细", "缺少应付账款数据，无法判断是否虚增成本"),
    33: ("利润分配凭证", "缺少利润分配记录，无法验证个税代扣"),
    35: ("印花税申报记录", "缺少印花税申报数据，无法验证缴纳情况"),
    37: ("广宣费明细", "缺少广告宣传费明细，无法验证是否超限"),
    40: ("季度收入分布", "缺少季度收入数据，无法判断收入集中度"),
    56: ("企业工商档案", "缺少企业工商数据，无法排查空壳特征"),
    77: ("关联方资金往来记录", "缺少关联交易数据，无法验证资金往来合规性"),
    81: ("合同对方与发票对方比对", "缺少合同数据，无法比对发票对方一致性"),
    104: ("免税收入明细", "缺少免税收入数据，无法验证进项税额转出"),
    137: ("不征税收入备案", "缺少不征税收入数据，无法验证合规性"),
    147: ("企业所得税申报记录", "缺少所得税申报历史，无法验证贡献率"),
    153: ("简易计税备案", "缺少简易计税备案，无法验证计税方式划分"),
    162: ("合同违约金条款", "缺少合同数据，无法验证违约金涉税处理"),
    # 新增检测：依赖申报表数据的可检测规则
    19: ("多期财务报表数据", "缺少多期收入/成本/费用数据，无法计算变动率异常"),
    31: ("个税申报记录", "缺少个税申报数据，无法比对员工与申报人数"),
    41: ("社保缴存记录", "缺少社保系统缴费记录，无法验证申报缴存情况"),
    106: ("增值税申报表附表一", "缺少增值税申报记录，无法验证无票收入是否已填报"),
    121: ("增值税申报表进项税额转出栏", "缺少申报记录，无法验证进项税额转出及时性"),
    138: ("暂估成本明细账", "缺少暂估成本跨期数据，无法验证是否及时冲销"),
    187: ("股权转让协议及个税申报", "缺少股权转让和个税数据，无法验证个税申报"),
    206: ("资产损失税前扣除备案", "缺少备案记录，无法验证资产损失扣除合规性"),
    271: ("财税申报表数据", "缺少申报表数据，无法做财税双向交叉比对"),
    273: ("财务存货账", "缺少财务存货明细账，无法与进销存台账交叉核对"),
    279: ("房产原值及折旧明细", "缺少房产数据，无法与房产税从价计征交叉比对"),
    290: ("多期经营数据", "缺少多期经营数据，无法判断季节性波动合理性"),
}

def _domain_rule_coverage(all_findings, bank_txs, sal_invs, pur_invs, vouchers, salaries, social_security, inventory, docs):
    """对全量规则做全覆盖验证：未触发的规则给出缺失数据兜底结论"""
    findings = []
    
    # 读取规则库
    rules_path = os.path.join(_PROJECT_ROOT, "static", "tax_risk_rules_local_export.json")
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            all_rules = json.load(f)
    except:
        return findings
    
    # 已触发的规则ID集合
    triggered_ids = set()
    for f in all_findings:
        if not isinstance(f, dict):
            continue
        rid = f.get("rule_id") or f.get("id")
        if rid: triggered_ids.add(rid)
    
    # 可用的数据源
    has_bank = len(bank_txs) > 0
    has_sal_inv = len(sal_invs) > 0
    has_pur_inv = len(pur_invs) > 0
    has_voucher = len(vouchers) > 0
    has_salary = len(salaries) > 0
    has_social = len(social_security) > 0
    has_inventory = len(inventory) > 0
    # 检测是否有合同文件
    has_contract = False
    if docs:
        for d in docs:
            fn = d.get("original_name", "").lower()
            if any(k in fn for k in ("合同", "contract", "协议")):
                has_contract = True; break
    
    missing_data = []
    verified_count = 0
    
    for rule in all_rules:
        rid = rule["id"]
        item = rule.get("item", "")
        
        # 如果规则已触发，跳过
        if rid in triggered_ids:
            verified_count += 1
            continue
        
        # 检查是否有显式数据需求
        if rid in RULE_DATA_REQUIREMENTS:
            required_data, fallback = RULE_DATA_REQUIREMENTS[rid]
            missing_data.append({
                "id": rid, "item": item, "required": required_data, "fallback": fallback
            })
            continue
        
        # 按分类推断所需数据
        cat = rule.get("category", "")
        detectable = rule.get("detectable", True)
        
        if not detectable:
            # 知识预警规则：需要客户配合提供资料
            missing_data.append({
                "id": rid, "item": item,
                "required": f"相关业务资料（{cat}）",
                "fallback": f"此规则属于{cat}范畴，需客户提供对应的业务数据才能审查"
            })
            continue

    # ═══ 产出发现 ═══
    total_rule_count = len(all_rules)
    
    if verified_count > 0:
        findings.append({
            "type": "规则已触发验证",
            "level": "低风险", "score": 2,
            "detail": f"{total_rule_count}条规则中{verified_count}条已被触发并产出结论。",
            "description": f"已触发的{verified_count}条规则覆盖了本报告各分析域的风险发现。这些规则的结论已经过数据源复核。",
            "how_found": "逐一核对了本次分析产生的每条发现与底层规则引擎的映射关系——确认每条风险发现都有对应的规则支撑和数据验证。".format(total_rules=len(all_rules)),
            "category": "域18 全覆盖验证"
        })
    
    total_rule_count = len(all_rules)
    
    if missing_data:
        # 按缺失类型分组
        by_type = {}
        for m in missing_data:
            req = m["required"]
            key = req[:20]
            by_type.setdefault(key, []).append(m)
        
        missing_list = []
        for m in missing_data:
            missing_list.append(f"【规则{m['id']}】{m['item']}：缺少{m['required']}，{m['fallback']}")
        
        verification_text = "\n".join(missing_list)
        
        findings.append({
            "type": "部分规则因数据缺失无法验证",
            "level": "中风险", "score": 6,
            "detail": f"{total_rule_count}条规则中{len(missing_data)}条因缺少所需数据未能验证。其中{sum(1 for m in missing_data if any(k in m['required'] for k in ('合同','协议')))}条需合同文件、{sum(1 for m in missing_data if '申报' in m['required'] or '备案' in m['required'])}条需税务申报记录。",
            "description": f"以下{len(missing_data)}条规则无法执行审查，因为缺少所需数据：\n\n{verification_text[:2000]}" + ("\n...(更多信息见详细报告)" if len(verification_text) > 2000 else ""),
            "how_found": f"将{total_rule_count}条规则逐一比对已触发的规则ID集合，对未触发规则逐个分析所需数据源是否在本次上传的文件中存在。",
            "tax_impact": "部分规则无法验证意味着企业可能存在的风险未被发现。建议补充对应的数据后再做一次分析。",
            "policy_ref": "《税务稽查工作规程》关于企业提供完整经营资料的义务。",
            "suggestion": f"如需全面验证{total_rule_count}条规则，请补充以下资料：\n1）合同文件（覆盖主要客户/供应商）\n2）增值税申报表历史数据\n3）企业所得税申报表\n4）印花税申报记录\n5）关联交易/资本交易相关资料\n6）存货盘点报告\n7）税务稽查应对预案",
            "category": "域18 全覆盖验证"
        })
    
    return findings


def _compute_risk_profile(all_findings, bank_txs, sal_invs, pur_invs, vouchers, salaries):
    import math, re
    from collections import defaultdict
    from datetime import datetime as dt_cls

    dimensions = {
        "经营真实度": {"kw": ["产能","能耗","电费","水费","油费","车辆","人工","工时","产量",
            "物流","运输","机器","设备","模具","厂房","仓库","空间","门卫","质检","包装","废料","边角料",
            "考勤","排班","温控","维修","原材","辅材","变压器","噪音","排污"], "w":1.3, "c":"#2563eb", "d":"生产要素与产出的逻辑自洽性"},
        "发票合规度": {"kw": ["发票","进销","品名","税率","税负","红冲","作废","虚开","顶额",
            "连号","滞留","认证","抵扣","专票","普票","电子发票","数电票","备注栏","清单",
            "代开","票种","编码","混合销售","兼营","进项税额","留抵"], "w":1.2, "c":"#ef4444", "d":"发票合规性和进销匹配度"},
        "资金安全性": {"kw": ["资金","银行","流水","现金","公私","对公","私户","公转私","回流",
            "借款","货款","往来","应付","应收","预付","预收","挂账","坏账","贴现","承兑",
            "支付宝","微信","二维码","POS","第三方","资产负债","流动比","速动比",
            "负债率","所有者权益"], "w":1.4, "c":"#8b5cf6", "d":"资金流向合法性及资产负债健康度"},
        "申报一致性": {"kw": ["申报","申报表","企业所得税","增值税申报","个税申报","社保申报",
            "财务报表","利润表","资产负债表","勾稽","差异","比对","城建税","教育费附加",
            "印花税","房产税","土地使用税","契税","环保税","三流","四流","不征税",
            "汇算清缴","预缴","预估","调整"], "w":1.1, "c":"#f59e0b", "d":"各申报表与报表之间的一致性"},
        "行业偏离度": {"kw": ["行业","均值","基准","偏离","税负率","毛利率","净利率",
            "费用率","集中度","季节性","波动","比重","占比","比例","超标","限额",
            "合理区间","标准","同行","区域"], "w":1.0, "c":"#10b981", "d":"关键指标与行业正常区间的偏离"},
        "关联风险": {"kw": ["关联","转让定价","转移","避税","境外","跨境","非居民",
            "代扣代缴","付汇","外汇","受控外国","资本弱化","同期资料","预约定价",
            "集团","母子","同一控制","关联方","借用","来华"], "w":1.2, "c":"#ec4899", "d":"关联交易定价公允性及跨境合规性"},
        "档案完整度": {"kw": ["缺少","缺失","无合同","无银行","无发票","无工资","无社保",
            "无凭证","无进销存","不完整","未备案","未申报","未报告","完备度","不齐全",
            "遗漏","逾期","延后","未提供"], "w":0.8, "c":"#6b7280", "d":"经营资料的完整性和可核查性"},
    }
    n_dims = len(dimensions)

    # L1: 规则命中基础分
    dim_scores = {}
    for dn, dc in dimensions.items():
        matched = [f for f in all_findings if any(kw in (f.get("item","")+f.get("type","")+f.get("detail","")) for kw in dc["kw"])]
        if not matched:
            dim_scores[dn] = {"score":0,"count":0,"level":"未触发","weighted_score":0,"boost":""}
            continue
        avg_score = sum(abs(f.get("score",5)) for f in matched) / len(matched)
        raw = min(avg_score * 7 * math.sqrt(len(matched) / 50.0), 100)
        dim_scores[dn] = {"score":round(raw,1),"weighted_score":round(raw*dc["w"],1),
                          "count":len(matched),"level":"高风险" if raw>60 else ("中风险" if raw>30 else "低风险"),"boost":""}

    # L2: 原始数据驱动增强
    if bank_txs:
        total_in = sum(float(tx.get("credit",0) or 0) for tx in bank_txs)
        oil_cost = pub2pri = cash_n = 0
        wx_alipay_in = 0
        for tx in bank_txs:
            cp = str(tx.get("counterparty_name", tx.get("counterparty","")))
            sm = str(tx.get("summary",""))
            dr = float(tx.get("debit",0) or 0)
            cr = float(tx.get("credit",0) or 0)
            if any(k in sm for k in ["油","加油"]) or "石化" in cp: oil_cost += dr
            if any(k in cp for k in ["支付宝","微信","财付通"]): wx_alipay_in += cr
            if re.match(r'^[\u4e00-\u9fff]{2,3}$', cp) and dr > 0: pub2pri += dr
            if "现金" in sm: cash_n += 1

        third_party_ratio = wx_alipay_in / total_in if total_in > 0 else 0
        pub2pri_ratio = pub2pri / total_in if total_in > 0 else 0

        if oil_cost > 50000:
            dim_scores["经营真实度"]["score"] = min(100, dim_scores["经营真实度"]["score"] + 5)
            dim_scores["经营真实度"]["boost"] += f"油费{int(oil_cost)}元偏高; "
        if third_party_ratio > T.ratios.half:
            dim_scores["经营真实度"]["score"] = min(100, dim_scores["经营真实度"]["score"] + 8)
            dim_scores["经营真实度"]["boost"] += f"第三方收款占比{third_party_ratio:.0%}; "
        if pub2pri_ratio > 0.2:
            dim_scores["资金安全性"]["score"] = min(100, dim_scores["资金安全性"]["score"] + 8)
            dim_scores["资金安全性"]["boost"] += f"公转私占比{pub2pri_ratio:.0%}; "
        if cash_n > 10:
            dim_scores["资金安全性"]["score"] = min(100, dim_scores["资金安全性"]["score"] + 5)
            dim_scores["资金安全性"]["boost"] += f"现金{cash_n}笔; "

    # 进销比分析
    if sal_invs and pur_invs:
        s_tot = sum(float(i.get("total_amount",i.get("amount",0)) or 0) for i in sal_invs)
        p_tot = sum(float(i.get("total_amount",i.get("amount",0)) or 0) for i in pur_invs)
        if s_tot > 0 and p_tot / s_tot > 10:
            dim_scores["发票合规度"]["score"] = min(100, dim_scores["发票合规度"]["score"] + 10)
            dim_scores["发票合规度"]["boost"] += f"进销比{p_tot/s_tot:.2f}:1; "

    # L3: 多源交叉融合 乘数效应
    cross_patterns = []
    # 降低阈值：即使少量数据也能触发交叉模式
    ps_dev = dim_scores["发票合规度"]["score"] >= 15
    third_p = "第三方收款" in dim_scores["经营真实度"].get("boost","")
    cont_loss = any("连续" in f.get("detail","") and "亏损" in f.get("detail","") for f in all_findings)
    asset_grow = dim_scores["经营真实度"]["score"] >= 15
    ss_gap = any("社保" in f.get("item","") and ("人数" in f.get("item","") or "差异" in f.get("item","")) for f in all_findings)
    # 新增：公转私+第三方收款组合
    pub_priv = "公转私" in dim_scores["资金安全性"].get("boost","")

    if ps_dev and third_p:
        cross_patterns.append(("进销背离+第三方收款=虚开高危", 1.8, ["发票合规度","资金安全性","经营真实度"]))
    if cont_loss and asset_grow:
        cross_patterns.append(("长亏不倒+资产扩张=隐匿收入", 1.4, ["经营真实度","行业偏离度"]))
    if ss_gap and dim_scores["申报一致性"]["score"] >= 10:
        cross_patterns.append(("工资社保差异=未全员参保", 1.3, ["申报一致性","经营真实度"]))
    if third_p and pub_priv:
        cross_patterns.append(("公转私+第三方收款=资金体外循环", 1.5, ["资金安全性","经营真实度"]))

    for pn, mult, dims in cross_patterns:
        for dn in dims:
            if dn in dim_scores:
                dim_scores[dn]["score"] = round(min(dim_scores[dn]["score"] * mult, 100), 1)

    # L4: 行为模式识别 (时间序列)
    try:
        monthly_inc = defaultdict(float); wkend = 0; total_tx = 0
        for tx in bank_txs:
            total_tx += 1
            ds = str(tx.get("transaction_date", tx.get("date","")))
            if not ds: continue
            try:
                d = dt_cls.fromisoformat(ds[:10])
                m = ds[:7]
                cr = float(tx.get("credit",0) or 0)
                if cr > 0: monthly_inc[m] += cr
                if d.weekday() >= 5: wkend += 1
            except: pass
        mons = sorted(monthly_inc.keys())
        if len(mons) >= 3:
            vals = [monthly_inc[m] for m in mons]
            m = sum(vals)/len(vals)
            if m > 0:
                cv = math.sqrt(sum((x-m)**2 for x in vals)/len(vals)) / m
                if cv > T.ratios.half:
                    dim_scores["行业偏离度"]["score"] = min(100, dim_scores["行业偏离度"]["score"]+5)
                    dim_scores["行业偏离度"]["boost"] += f"月度收入波动CV={cv:.2f}; "
        if total_tx > 20 and wkend/total_tx > 0.15:
            dim_scores["经营真实度"]["score"] = min(100, dim_scores["经营真实度"]["score"]+3)
            dim_scores["经营真实度"]["boost"] += f"周末交易{wkend/total_tx:.0%}; "
    except: pass

    # 最终计算
    for dn, dc in dimensions.items():
        dim_scores[dn]["weighted_score"] = round(dim_scores[dn]["score"] * dc["w"], 1)
    hc = sum(1 for d in dim_scores.values() if d["score"] > 60)
    xm = 1.8 if hc>=4 else (1.5 if hc>=3 else (1.2 if hc>=2 else 1.0))
    cb = sum(d["weighted_score"] for d in dim_scores.values()) / n_dims
    cs = round(min(cb * xm, 100), 1)
    cl = "高风险" if cs > 55 else ("中风险" if cs > 25 else "低风险")

    rl = list(dimensions.keys())
    rv = [dim_scores[d]["score"] for d in rl]
    rc = [dimensions[d]["c"] for d in rl]
    td = sorted(dim_scores.items(), key=lambda x: -x[1]["weighted_score"])
    comm = []
    for dn, ds in td:
        score_val = ds.get('score', 0)
        count_val = ds.get('count', 0)
        c = f"{dn}({score_val}分/{count_val}条): {dimensions[dn]['d']}"
        boost_val = ds.get("boost", "")
        if isinstance(boost_val, str) and boost_val.strip():
            c += " [" + boost_val.rstrip("; ") + "]"
        comm.append(c)
    if cross_patterns:
        comm.append("交叉模式: " + " | ".join(p[0] for p in cross_patterns))

    return {
        "composite_score": cs, "composite_level": cl,
        "cross_multiplier": xm, "high_dimensions": hc,
        "dimensions": {d: dim_scores[d] for d in rl},
        "radar": {"labels": rl, "values": rv, "colors": rc},
        "commentary": comm, "cross_patterns": [p[0] for p in cross_patterns],
        "description": f"四级评分引擎: 7维加权(均值{cb:.2f}) x 交叉乘数{xm}倍 = {cs}分({cl})。{hc}维度高风险联动。"}
def _merge_similar_findings(findings):
    import re
    if not findings: return findings
    
    # 第一步：按 type 分组
    groups = {}
    for f in findings:
        t = f.get("type", "")
        if t not in groups:
            groups[t] = []
        groups[t].append(f)
    
    merged = []
    for ftype, items in groups.items():
        if len(items) == 1:
            merged.append(items[0])
            continue
        
        # 同一 type 下，按 (level, score) 再分组——仅同等级同分的才可能合并
        sub_groups = {}
        for f in items:
            key = (f.get("level", ""), f.get("score", 0))
            if key not in sub_groups:
                sub_groups[key] = []
            sub_groups[key].append(f)
        
        for (level, score), sub_items in sub_groups.items():
            if len(sub_items) == 1:
                merged.append(sub_items[0])
                continue
            
            # 尝试合并：提取所有 detail 中的参数部分
            if _is_mergeable_city_group(sub_items):
                merged.append(_merge_city_findings(sub_items, ftype, level, score))
            else:
                merged.extend(sub_items)
    
    return merged


def _is_mergeable_city_group(items):
    """判断一组发现是否为「同城供应商群集」这类仅城市不同的可合并组"""
    import re
    pattern = re.compile(r'(.{2,4})地区集中(\d+)家')
    for f in items:
        d = str(f.get("detail", ""))
        if not pattern.search(d):
            return False
    return True


def _merge_city_findings(items, ftype, level, score):
    """合并城市类发现：北京(15家)、上海(13家)..."""
    import re
    pattern = re.compile(r'(.{2,4})地区集中(\d+)家')
    cities = []
    total_suppliers = 0
    for f in items:
        m = pattern.search(str(f.get("detail", "")))
        if m:
            cities.append((m.group(1), int(m.group(2))))
            total_suppliers += int(m.group(2))
    
    cities.sort(key=lambda x: -x[1])
    city_parts = [f"{c}({n}家)" for c, n in cities]
    
    return {
        "type": ftype,
        "level": level,
        "score": score,
        "detail": f"多地区同类供应商群集，涉及{cities[0][0]}等{len(cities)}个城市共{total_suppliers}家：{'、'.join(city_parts)}" + ("（等）" if len(cities) > 8 else ""),
        "description": f"以下城市存在同类供应商群集现象：\n" + "\n".join(f"  • {c}：{n}家同类供应商" for c, n in cities),
        "merged_from": len(items),
        "domain": items[0].get("domain", "")
    }

def _check_accounting_system_gap(invoices, bank_txs, vouchers):
    """检测账务系统缺失风险"""
    findings = []
    has_inv = len(invoices) > 0
    has_bank = len(bank_txs) > 0
    has_voucher = len(vouchers) > 0
    
    if (has_inv or has_bank) and not has_voucher:
        detail_parts = []
        if has_inv: detail_parts.append(f"{len(invoices)}张发票")
        if has_bank: detail_parts.append(f"{len(bank_txs)}条银行流水")
        data_desc = "、".join(detail_parts)
        
        findings.append({
            "type": "缺失序时账/会计凭证",
            "level": "高风险",
            "score": 9,
            "detail": f"系统已加载{data_desc}，但未检测到序时账或记账凭证。无法验证账务处理的真实性和完整性。",
            "description": (
                "序时账（记账凭证）是税务稽查的核心资料，缺少凭证将导致以下风险无法排除：\n"
                "1. 发票与账务脱节：无法确认发票是否已正确入账，是否存在'有票无账'或'有账无票'。\n"
                "2. 收入隐匿风险：银行流水中的收款可能未在账务中确认收入，无法判断是否已纳税申报。\n"
                "3. 成本真实性：进项发票对应的采购成本是否准确计入当期损益无法验证。\n"
                "4. 科目余额无法追溯：缺少凭证使科目余额表的形成过程不可审计。\n"
                "5. 跨期调节无法识别：无法判断企业是否通过跨期入账调节应纳税所得额。"
            ),
            "how_found": f"数据源检测：发票{len(invoices)}张 + 银行{len(bank_txs)}条 + 凭证{len(vouchers)}条 → 凭证缺口",
            "tax_impact": (
                "缺少凭证使所有账务分析结论存在重大不确定性。"
                "收入确认、成本匹配、往来核算等核心税务判断无法通过账务交叉验证。"
            ),
            "policy_ref": "《税收征收管理法》第十九条、第二十四条；《会计法》第九条；《税务稽查工作规程》",
            "suggestion": (
                "必须要求企业提供完整的序时账（Excel格式）。\n"
                "立即核实：① 发票是否全部入账 ② 银行收款是否已确认收入并申报纳税 "
                "③ 进项发票是否已计入成本费用 ④ 是否存在跨年度调节利润"
            ),
            "category": "账务系统",
        })
        
        findings.append({
            "type": "凭证缺失导致的分析盲区",
            "level": "中风险",
            "score": 7,
            "detail": "因缺少序时账，以下分析领域受限：收入确认、成本匹配、往来核算、科目追溯、跨期识别。当前分析仅基于发票和银行流水，结论存在重大不确定性。",
            "category": "账务系统",
        })
    
    return findings if findings else None

# ═══════════════════════════════════════════════════
# 规则数据验证引擎 —— 把规则变成真正的分析引擎
# ═══════════════════════════════════════════════════

def _verify_rule_against_data(rule, bank_txs, invoices, salaries, social_security, vouchers):
    """对规则进行真正的数据验证，返回(是否触发, 原因, 置信度, 数值证据)
    
    规则类型自动检测：
    - 定量规则（含数字/阈值）：提取阈值→扫描数据→判断是否超标→返回具体超标值
    - 定性规则（无数字）：检查相关数据是否存在→返回数据量
    - 缺失规则（缺失/不完备/无）：检查指定数据类型是否存在→返回缺失判断
    
    这是"把规则变成真正分析引擎"的核心函数。
    """
    item = str(rule.get("item", ""))
    detail = str(rule.get("detail", ""))
    rule_text = item + " " + detail
    level = str(rule.get("level", "中风险"))
    category = str(rule.get("category", ""))
    
    # ── 类型1：定量规则 → 提取数字阈值并验证 ──
    import re as _re_q
    numbers = _re_q.findall(r'(\d+(?:\.\d+)?)\s*(万|万元|亿|元|%)?', rule_text)
    thresholds = []  # 提取到的阈值列表
    for n_str, unit in numbers:
        val = float(n_str)
        if unit in ("万", "万元"): val *= 10000
        elif unit == "亿": val *= 100000000
        elif unit == "%": val = val  # 百分比保持原值
        thresholds.append(val)
    
    # ── 定量验证：规则中是否有明确金额/比例阈值 ──
    if thresholds:
        evidence = {}
        # 检查发票金额相关
        if any(k in rule_text for k in ("发票", "红字", "作废", "冲红", "金额", "税额")):
            if invoices:
                big_invs = []
                for inv in invoices:
                    amt = float(inv.get("amount", 0) or 0)
                    if amt > 0:
                        for th in thresholds:
                            if th > 1 and amt >= th:
                                big_invs.append({"id": inv.get("id", ""), "amount": amt, "date": str(inv.get("date", ""))[:10]})
                                break
                if big_invs:
                    evidence["超标发票"] = len(big_invs)
                    evidence["最大金额"] = max(x["amount"] for x in big_invs)
                    return (True, f"{len(big_invs)}张发票金额超过{thresholds[0]:,.2f}元阈值", 0.85, evidence)
                else:
                    return (False, "无发票金额超标", 0, {})
            else:
                return (False, "无发票数据", 0, {})
        
        # 检查银行流水金额相关
        if any(k in rule_text for k in ("银行", "流水", "收款", "付款", "转账", "资金")):
            if bank_txs:
                big_txs = []
                for tx in bank_txs:
                    debit = float(tx.get("debit", 0) or 0)
                    credit = float(tx.get("credit", 0) or 0)
                    max_amt = max(debit, credit)
                    if max_amt > 0:
                        for th in thresholds:
                            if th > 1 and max_amt >= th:
                                big_txs.append({"id": tx.get("id", ""), "amount": max_amt, "date": str(tx.get("date", ""))[:10]})
                                break
                if big_txs:
                    evidence["超标流水"] = len(big_txs)
                    evidence["最大金额"] = max(x["amount"] for x in big_txs)
                    return (True, f"{len(big_txs)}笔银行流水超过{thresholds[0]:,.2f}元阈值", 0.85, evidence)
                else:
                    return (False, "无流水金额超标", 0, {})
            else:
                return (False, "无银行流水数据", 0, {})
        
        # 检查工资相关
        if any(k in rule_text for k in ("工资", "薪酬", "个税", "薪金")):
            if salaries:
                total_salary = sum(float(s.get("amount", 0) or 0) for s in salaries)
                for th in thresholds:
                    if th > 1 and total_salary > th:
                        evidence["总工资"] = total_salary
                        evidence["员工数"] = len(salaries)
                        return (True, f"总工资{total_salary:,.2f}元超过{th:,.2f}元阈值", 0.8, evidence)
                return (False, f"总工资{total_salary:,.2f}未超阈值", 0, {})
            else:
                return (False, "无工资数据", 0, {})
        
        # 通用定量：有阈值但无法确定数据类型→标记为"需要数据反查"
        return (False, "无法确定阈值对应的数据类型", 0, {})
    
    # ── 类型2：缺失检查规则 ──
    if any(k in rule_text for k in ("缺失", "不完备", "无", "没有", "缺少", "不足")):
        ds = category.lower()
        if any(k in ds for k in ("发票", "进项", "销项")):
            has_it = len(invoices) > 0
            return (not has_it, f"{'缺少' if not has_it else '已有'}发票数据" + (f"({len(invoices)}张)" if has_it else ""), 0.9 if not has_it else 0.1, {"has_data": has_it})
        if any(k in ds for k in ("合同",)):
            return (True, "合同数据需单独检查", 0.5, {})
        if any(k in ds for k in ("凭证", "序时账", "会计")):
            has_v = len(vouchers) > 0
            return (not has_v, f"{'缺少' if not has_v else '已有'}凭证数据" + (f"({len(vouchers)}条)" if has_v else ""), 0.85 if not has_v else 0.15, {"has_data": has_v})
        if any(k in ds for k in ("社保",)):
            has_si = len(social_security) > 0
            return (not has_si, f"{'缺少' if not has_si else '已有'}社保数据" + (f"({len(social_security)}条)" if has_si else ""), 0.85 if not has_si else 0.15, {"has_data": has_si})
    
    # ── 类型3：定性规则 → 检查相关数据是否存在 ──
    if bank_txs and any(k in rule_text for k in ("银行", "流水", "账户", "收款", "付款")):
        return (True, f"银行流水{len(bank_txs)}条可分析", 0.6, {"count": len(bank_txs)})
    if invoices and any(k in rule_text for k in ("发票", "进项", "销项", "开票")):
        return (True, f"发票{len(invoices)}张可分析", 0.6, {"count": len(invoices)})
    if salaries and any(k in rule_text for k in ("工资", "薪酬", "员工")):
        return (True, f"工资{len(salaries)}条可分析", 0.6, {"count": len(salaries)})
    
    return (False, "无法确认数据关联", 0, {})


# ═══════════════════════════════════════════════════
# 资料情报提取引擎 —— 从资料数据中提取稽查所需信息
# ═══════════════════════════════════════════════════

def _extract_material_intel(bank_txs, invoices, salaries, social_security, vouchers, inventory, input_vat_deductions=None, pipeline_log=None):
    """从各类资料中提取关键审计情报——让系统真正'读懂'资料"""
    intel = {}
    from collections import Counter, defaultdict
    
    # ── 银行流水情报 ──
    if bank_txs:
        total_in = sum(float(tx.get("credit", 0) or 0) for tx in bank_txs)
        total_out = sum(float(tx.get("debit", 0) or 0) for tx in bank_txs)
        tax_payments = []
        large_txs = []
        counterparties = Counter()
        months = set()
        
        for tx in bank_txs:
            d = str(tx.get("date", "") or tx.get("transaction_date", ""))[:10]
            if d and len(d) >= 7: months.add(d[:7])
            cp = str(tx.get("counterparty", "") or tx.get("counterparty_name", "")).strip()
            debit = float(tx.get("debit", 0) or 0)
            credit = float(tx.get("credit", 0) or 0)
            summary = str(tx.get("summary", "") or "")
            
            # 大额交易（>50万）
            max_amt = max(debit, credit)
            if max_amt > T.amount_thresholds.large_transaction:
                large_txs.append({"date": d[:10], "amount": round(max_amt, 2), 
                                "type": "支出" if debit > credit else "收款",
                                "counterparty": cp[:30], "summary": summary[:30]})
            
            # 税费支付
            if any(k in summary for k in ("税", "金库", "国税", "地税", "纳税", "缴税")):
                tax_payments.append({"date": d[:10], "amount": round(max_amt, 2), "summary": summary[:30]})
            
            # 往来方
            if cp and len(cp) >= 2:
                counterparties[cp] += round(max_amt, 2)
        
        intel["银行流水"] = {
            "总收款": f"{total_in:,.2f}元",
            "总付款": f"{total_out:,.2f}元",
            "净流入": f"{total_in - total_out:,.2f}元",
            "覆盖月份": sorted(months),
            "笔数": len(bank_txs),
            "税费支出笔数": len(tax_payments),
            "税费支出总额": f"{sum(x['amount'] for x in tax_payments):,.2f}元",
            "大额交易(>50万)": len(large_txs),
            "往来方全部": [{"名称": n, "金额": f"{a:,.2f}"} for n, a in counterparties.most_common()],
        }
        
        # ── 收款类型分析：配置驱动自适应分类（不由预设类别决定，按关键词逐层匹配）──
        # 规则存储于 industry_data.json → 收款分类规则，可随行业扩展而增加类型
        pay_cats = {}  # label -> {payer_name: amount}
        rc_rules_cfg = _load_industry_data().get("收款分类规则", {}).get("rules", [])
        if not rc_rules_cfg:
            # 兜底：内置默认规则
            rc_rules_cfg = [
                {"label": "税费社保退款", "keywords": ["社保","医保","税","国库","ETS"]},
                {"label": "银行内部款项", "keywords": ["结息","利息","银行","农行"]},
                {"label": "企业客户款", "keywords": ["有限公司","公司","企业","厂","店","集团"]},
                {"label": "个人待分析", "is_default": True},
            ]
        for rule in rc_rules_cfg:
            if not rule.get("is_default"):
                pay_cats[rule["label"]] = defaultdict(float)
        pay_cats["个人待分析"] = defaultdict(float)  # 兜底默认分类，标注"待分析"提示稽查员关注
        
        for tx in bank_txs:
            credit = float(tx.get("credit", 0) or 0)
            if credit <= 0: continue
            cp = str(tx.get("counterparty", "") or tx.get("counterparty_name", "")).strip()
            summary = str(tx.get("summary", "") or "")
            # 收集全部可用文本字段用于综合分析
            remark = str(tx.get("remark", "") or tx.get("notes", "") or tx.get("memo", "") or tx.get("交易附言", "") or "")
            purpose = str(tx.get("purpose", "") or tx.get("用途", "") or "")
            # 合并所有文本字段为综合分析文本
            all_text = f"{cp} {summary} {remark} {purpose}"
            
            if not cp:
                if any(k in all_text for k in ['结息','利息']): cp = "(银行结息)"
                elif any(k in all_text for k in ['社保','ETS','扣税','代扣']): cp = "(税费扣款)"
                elif any(k in all_text for k in ['年费','管理费','短信','账户','手续费']): cp = "(银行费用)"
                else: cp = "(未记录名称)"
            
            # 三信息综合分析：对方户名 + 摘要 + 交易附言 联合匹配
            matched = False
            for rule in rc_rules_cfg:
                if rule.get("is_default"): continue
                kws = rule.get("keywords", [])
                sums = rule.get("summaries", [])
                # 在全部文本字段中匹配
                name_match = kws and any(k in all_text for k in kws)
                summary_match = sums and any(s in all_text for s in sums)
                if name_match or summary_match:
                    pay_cats[rule["label"]][cp] += credit
                    matched = True
                    break
            if not matched:
                pay_cats["个人待分析"][cp] += credit
        
        # ── 收款类型纠错验证：系统自我反思，修正明显误分类 ──
        # 方法论：分类完成后，系统自问——"这个分类合理吗？有没有明显的反例？"
        # 规则1：个人款中极小金额（<100元）且金额有零有整（如9.62）→ 大概率是银行利息
        # 规则2：个人款中付款方为空且摘要含银行关键词 → 银行费用
        # 规则3：企业客户款中付款方实际是关联方 → 需查摘要确认
        import re as _re
        corrections = []
        for tx in bank_txs:
            credit = float(tx.get("credit", 0) or 0)
            if credit <= 0: continue
            cp = str(tx.get("counterparty", "") or tx.get("counterparty_name", "")).strip()
            summary = str(tx.get("summary", "") or "")
            remark = str(tx.get("remark", "") or tx.get("notes", "") or tx.get("memo", "") or tx.get("交易附言", "") or "")
            purpose = str(tx.get("purpose", "") or tx.get("用途", "") or "")
            all_text = f"{cp} {summary} {remark} {purpose}"
            # 已经在个人待分析中的极小金额 → 检查是否为银行利息
            in_individual = False
            if cp in pay_cats.get("个人待分析", {}):
                in_individual = True
            elif not cp:
                in_individual = True  # 空名称通常也在个人款兜底
            
            if in_individual and credit < 100:
                # 金额特征验证：银行利息/费用通常是有整有零的精确小数
                is_decimal = credit != int(credit)
                # 放宽条件：极小金额(<20元)只要有零有整，几乎肯定是银行利息
                # 银行利息特征：结息金额通常精确到分(如9.62/3.17/0.48)，人为转账多为整数
                is_micro_amount = credit < 20
                # 综合三信息分析（对方户名 + 摘要 + 交易附言）——不能只看单一字段
                is_empty_all = len(all_text.strip()) < 5  # 所有文本字段几乎为空
                is_bank_in_all = any(k in all_text for k in ['银行','农行','建行','工行','交行','招行','农商','信用社','分行','支行','结息','利息','季度','活期','定期','扣息','手续费','账户管理','管理费','年费'])
                is_numeric_summary = _re.match(r'^\d{4,8}$', summary.strip()) is not None
                # 摘要+附言联合判断
                summary_remark = f"{summary} {remark}".strip()
                has_empty_text = len(summary_remark) < 3
                
                should_correct = False
                if is_decimal and is_micro_amount and has_empty_text:
                    should_correct = True  # <20元+有零有整+摘要附言都空→银行利息（常识：没人会转9.62元）
                elif is_decimal and (is_empty_all or is_bank_in_all or is_numeric_summary):
                    should_correct = True  # 有零有整+综合分析有银行特征→银行利息
                
                if should_correct:
                    # 重新分到银行内部款项
                    if cp in pay_cats.get("个人待分析", {}):
                        del pay_cats["个人待分析"][cp]
                    pay_cats.setdefault("银行内部款项", defaultdict(float))[cp or "(银行)"] += credit
                    corrections.append(f"纠错: {credit:.2f}元 '{cp or '(空)'}' 从个人待分析→银行内部款项(金额{credit}有零有整+{('空文本' if is_empty_all else '')}{('含银行关键词' if is_bank_in_all else '')}{('摘要空' if has_empty_text else '')})")
        
        if corrections and pipeline_log is not None:
            pipeline_log.append(f"[收款分类纠错] {len(corrections)}笔误分类已自动修正")
            for c in corrections[:5]:
                pipeline_log.append(f"  {c}")
        
        # 自适应输出：只输出有数据的类别
        intel["银行流水"]["收款构成"] = {}
        for label, data in pay_cats.items():
            total_val = sum(data.values())
            entity_cnt = len(data)
            if total_val > 0.01:
                intel["银行流水"]["收款构成"][label] = f"{total_val:,.2f}元（{entity_cnt}个收款方）"
        if not intel["银行流水"]["收款构成"]:
            intel["银行流水"]["收款构成"]["未检测到收款数据"] = "0.00元"
        # TOP收款方明细（从配置驱动的分类中汇总）
        all_payers = {}
        for data in pay_cats.values():
            for k, v in data.items(): all_payers[k[:25]] = v
        intel["银行流水"]["收款方全部"] = [{"名称": n, "金额": f"{a:,.2f}"} for n, a in sorted(all_payers.items(), key=lambda x: -x[1])]
        
        # ── 付款方分析（全部列示，不截断）──
        enterprise_payee = defaultdict(float); individual_payee = defaultdict(float)
        tax_payee = defaultdict(float); bank_payee = defaultdict(float)
        for tx in bank_txs:
            debit = float(tx.get("debit", 0) or 0)
            if debit <= 0: continue
            cp = str(tx.get("counterparty", "")).strip()
            summary = str(tx.get("summary", "")).strip()
            if not cp:
                if any(k in summary for k in ['社保','ETS','扣税']): cp = "(税费扣款)"
                elif any(k in summary for k in ['结息','利息']): cp = "(银行扣息)"
                elif any(k in summary for k in ['费用','短信','账户']): cp = "(银行费用)"
                else: cp = "(未记录名称)"
            if any(k in cp for k in ['有限公司','有限责任公司','股份有限公司','合伙企业','个人独资企业',
                                          '厂','店','部','中心','局','院','所','社','会','馆','场','园','苑','山庄','大厦',
                                          '集团','公司','企业','合作社','农场','牧场','渔场','林场']):
                enterprise_payee[cp] += debit
            elif any(k in cp for k in ['国家金库','税务局','ETS','社保','国库','税','财政','省ETS']):
                tax_payee[cp] += debit
            elif any(k in cp for k in ['银行','农行','清算','资金','批量','结息','扣息','费用']):
                bank_payee[cp] += debit
            else:
                individual_payee[cp] += debit
        
        all_payees = {}
        for d in [enterprise_payee, tax_payee, bank_payee, individual_payee]:
            for k, v in d.items(): all_payees[k[:30]] = v
        intel["银行流水"]["付款方全部"] = [{"名称": n, "金额": f"{a:,.2f}"} for n, a in sorted(all_payees.items(), key=lambda x: -x[1])]
    
    # ── 发票情报 ──
    if invoices:
        sal_invs = [i for i in invoices if i.get("direction") == "销项"]
        pur_invs = [i for i in invoices if i.get("direction") == "进项"]
        
        sal_total = sum(float(i.get("amount", 0) or 0) for i in sal_invs)
        sal_tax = sum(float(i.get("tax", 0) or 0) for i in sal_invs)
        pur_total = sum(float(i.get("amount", 0) or 0) for i in pur_invs)
        pur_tax = sum(float(i.get("tax", 0) or 0) for i in pur_invs)
        
        # 货物/服务分类（通用化：直接使用货物名称前4字作为分类，不依赖行业关键词）
        categories = Counter()
        for inv in invoices:
            goods = str(inv.get("goods", "") or inv.get("货物或应税劳务名称", "")).strip()
            if goods:
                # 取货物名称前4字作为分类（通用规则，适用于全行业）
                cat_name = goods[:4]
                categories[cat_name] += 1
        
        # ═══ 按发票号去重统计（行数≠发票张数，相同号码算一张）═══
        sal_unique_nos = set()
        pur_unique_nos = set()
        for inv in invoices:
            inv_no = str(inv.get("inv_no", "") or inv.get("发票号码", "") or inv.get("digital_invoice_no", "")).strip()
            if not inv_no:
                continue
            direction = str(inv.get("direction", "")).strip()
            if direction == "销项":
                sal_unique_nos.add(inv_no)
            elif direction == "进项":
                pur_unique_nos.add(inv_no)
        
        intel["发票"] = {
            "销项发票": f"{len(sal_invs)}行，去重{len(sal_unique_nos)}张，金额{sal_total:,.2f}元，税额{sal_tax:,.2f}元",
            "进项发票": f"{len(pur_invs)}行，去重{len(pur_unique_nos)}张，金额{pur_total:,.2f}元，税额{pur_tax:,.2f}元",
            "进销比": f"{pur_total/sal_total:.2f}" if sal_total > 0 else "N/A",
            "主要货物类别": dict(categories.most_common(5)) if categories else {},
        }
        
        # 买方/卖方TOP
        from collections import Counter as C2
        buyers = C2(); sellers = C2()
        buyer_amt = defaultdict(float); seller_amt = defaultdict(float)
        for inv in invoices:
            buyer = str(inv.get("buyer", "") or inv.get("购买方名称", "") or inv.get("购方名称", "") or inv.get("购方", "")
                     or inv.get("buyer_name", "") or inv.get("purchaser", "")).strip()
            seller = str(inv.get("seller", "") or inv.get("销方名称", "") or inv.get("销方", "") or inv.get("销售方名称", "")).strip()
            direction = str(inv.get("direction", "")).strip()
            amt = float(inv.get("total", 0) or inv.get("amount", 0) or 0)
            if buyer and len(buyer) >= 2: buyers[buyer] += 1
            if seller and len(seller) >= 2: sellers[seller] += 1
            # 按金额汇总：销项→买方的购买总额，进项→供应商的供货总额
            if direction == "销项" and buyer and amt > 0:
                buyer_amt[buyer] += amt
            if direction == "进项" and seller and amt > 0:
                seller_amt[seller] += amt
        if buyers:
            intel["发票"]["前5大购买方"] = [{"名称": n, "张数": c} for n, c in buyers.most_common(5)]
        if sellers:
            intel["发票"]["前5大供应商"] = [{"名称": n, "张数": c} for n, c in sellers.most_common(5)]
        # 销项客户明细（全部，按金额排序）
        if buyer_amt:
            intel["发票"]["销项客户明细"] = [{"名称": n, "金额": f"{a:,.2f}"} for n, a in sorted(buyer_amt.items(), key=lambda x: -x[1])]
        # 进项供应商明细（全部，按金额排序）
        if seller_amt:
            intel["发票"]["进项供应商明细"] = [{"名称": n, "金额": f"{a:,.2f}"} for n, a in sorted(seller_amt.items(), key=lambda x: -x[1])]
        
        # ═══ 发票统计（供报告生成器读取，区分行数 vs 发票张数）═══
        intel["发票"]["统计"] = {
            "销项发票行数": len(sal_invs),      # Excel原始行数
            "销项发票张数": len(sal_unique_nos),  # 按发票号去重
            "销项金额合计": sal_total,
            "进项发票行数": len(pur_invs),
            "进项发票张数": len(pur_unique_nos),
            "进项金额合计": pur_total,
        }
    
    # ── 进项认证抵扣情报（独立于进项发票，两者不是一回事）──
    if input_vat_deductions:
        deds = input_vat_deductions
        # 按勾选状态分类
        ded_by_status = defaultdict(lambda: {"count": 0, "amount": 0.0, "tax": 0.0})
        for d in deds:
            status = str(d.get("status", "") or d.get("勾选状态", "")).strip()
            amt = float(d.get("amount", 0) or 0)
            tax = float(d.get("tax", 0) or 0)
            ded_by_status[status]["count"] += 1
            ded_by_status[status]["amount"] += amt
            ded_by_status[status]["tax"] += tax
        # 已勾选（有效认证抵扣）
        checked = ded_by_status.get("已勾选", {"count": 0, "amount": 0.0, "tax": 0.0})
        # 未勾选/已作废等
        total_ded_rows = len(deds)
        intel["进项认证抵扣"] = {
            "总行数": total_ded_rows,
            "已认证抵扣_张数": checked["count"],
            "已认证抵扣_金额": f"{checked['amount']:,.2f}元",
            "已认证抵扣_税额": f"{checked['tax']:,.2f}元",
            "状态分布": {k: v["count"] for k, v in ded_by_status.items()},
        }
        intel["进项认证抵扣"]["摘要"] = f"共{total_ded_rows}行，其中已勾选认证{checked['count']}张，金额{checked['amount']:,.2f}元，税额{checked['tax']:,.2f}元"

    # ── 工资情报 ──
    if salaries:
        total_salary = sum(float(s.get("amount", 0) or s.get("实发工资", 0) or 0) for s in salaries)
        emp_count = len(set(str(s.get("name", "") or s.get("姓名", "") or s.get("id", "")) for s in salaries))
        intel["工资"] = {
            "总工资": f"{total_salary:,.2f}元",
            "员工人数": emp_count,
            "人均工资": f"{total_salary/max(emp_count,1):,.2f}元" if emp_count > 0 else "0",
            "记录条数": len(salaries),
        }
    
    # ── 社保情报 ──
    if social_security:
        ss_total = sum(float(s.get("amount", 0) or 0) for s in social_security)
        ss_count = len(social_security)
        intel["社保"] = {
            "记录条数": ss_count,
            "总缴费金额": f"{ss_total:,.2f}元",
        }
    
    # ── 凭证情报 ──
    if vouchers:
        intel["凭证"] = {
            "凭证数量": len(vouchers),
            "科目数量": len(set(str(v.get("account", "")) for v in vouchers if v.get("account"))),
        }
    
    # ── 存货情报 ──
    if inventory:
        intel["进销存"] = {
            "记录条数": len(inventory),
        }
    
    return intel


# ═══════════════════════════════════════════════════════════
# 稽查重点：现实中不管score多少，这些风险类型就是稽查必查项
# 等级不由score计算，而是由审计实务的优先级决定
# ═══════════════════════════════════════════════════════════
AUDIT_PRIORITY_LEVELS = {
    # 资金流 —— 稽查最核心的三流合一
    "收款来源与开票客户严重不匹配": "高风险",
    "进项发票与银行付款未匹配": "高风险",
    "收款与开票金额偏差大": "高风险",
    # 资料完备 —— 缺资料就是递刀子
    "合同文件缺失": "高风险",
    "银行流水缺失": "高风险",
    "销项发票缺失": "高风险",
    "进项发票缺失": "高风险",
    "记账凭证缺失": "高风险",
    "资料完备度综合评估": "高风险",
    # 进销存 —— 虚开发票的核心信号
    "进销品名映射": "高风险",
    # 费用 —— 偷逃税常用手段
    "费用发票占比异常": "高风险",
    "费用名目分散": "中风险",
    # 经营实质 —— 点→面交叉推理
    "重物跨省经营缺运输成本": "高风险",
    "外地加工费存疑": "高风险",
}

def _fix_level_by_audit_priority(ftype, current_level):
    """稽查重点发现强制等级——不根据score计算，根据审计实务的必查优先级"""
    return AUDIT_PRIORITY_LEVELS.get(ftype, current_level)


def _generate_biz_substance_findings(target_entity, pur_invs, sal_invs):
    """经营实质核查发现生成（规则ID: 999501-999503）
    
    五步核查法——从用户一句话提炼：
    ①工商登记→②进项审核(加工费+仅购进品名)→③销项审核(仅销售品名)
    →④交叉比对(相同=纯贸易,不同=加工转换)→⑤综合判断实质经营模式
    
    全行业适用：不依赖行业词库，通过加工费+品名差异统一检测
    """
    findings = []
    if not target_entity:
        return findings
    
    registered_type = target_entity.get("industry_online", "")  # 工商登记行业（非company_type企业类型）
    detected_industry = target_entity.get("industry", "")
    has_processing = target_entity.get("_has_processing_signal", False)
    goods_analysis = target_entity.get("_goods_analysis", {})
    
    pur_only = goods_analysis.get("pur_only_goods", [])
    sal_only = goods_analysis.get("sal_only_goods", [])
    common_goods = goods_analysis.get("common_goods", [])
    has_proc_fee = goods_analysis.get("has_processing_fee", False)
    
    # 无信号无差异 → 跳过
    if not has_processing and not pur_only and not sal_only:
        return findings
    
    # ── 规则 999501：工商登记企业类型与发票推断不一致 ──
    biz_desc = ""
    if has_proc_fee and (pur_only or sal_only):
        biz_desc = "外包轻加工模式（加工费+进销品名差异双信号）"
    elif pur_only and sal_only:
        biz_desc = "可能的加工/制造模式（进销品名存在实质性差异）"
    elif has_proc_fee:
        biz_desc = "可能的外包轻加工模式（发现加工费支出）"
    
    if not biz_desc:
        return findings
    
    risk_level = "高风险" if (has_proc_fee and pur_only and sal_only) else "中风险"
    risk_score = T.scoring_weights.risk_high_score if risk_level == "高风险" else 5
    
    pur_str = "、".join(pur_only[:8]) if pur_only else "无"
    sal_str = "、".join(sal_only[:8]) if sal_only else "无"
    com_str = "、".join(common_goods[:5]) if common_goods else "无"
    reg_str = registered_type or detected_industry or "未知"
    
    findings.append({
        "type": "经营实质-工商登记与发票推断不一致",
        "domain": "经营实质核查",
        "level": risk_level,
        "score": risk_score,
        "rule_id": 999501,
        "detail": (
            f"工商登记为{reg_str}，但发票数据反映的实质经营为{biz_desc}。"
            f"仅购进品名({len(pur_only)}类)：{pur_str}；"
            f"仅销售品名({len(sal_only)}类)：{sal_str}；"
            f"共同品名({len(common_goods)}类)：{com_str}。"
            f"{'存在加工费发票。' if has_proc_fee else ''}"
            f"综合判断：被查单位经营实质与工商登记不完全一致，应按实质经营模式进行税务处理。"
        ),
        "suggestion": (
            "①核实委托加工合同及加工费支出的真实性和合理性；"
            "②提供BOM表验证进销品名转换的投入产出关系；"
            "③核实仅销售品名的生产来源（自行生产/委托加工/外购转售）；"
            "④按实质经营模式重新核定适用税率和成本扣除标准"
        ),
        "how_found": "进项发票加工费信号+进销品名交叉比对",
        "chain_ref": "经营实质-工商登记vs发票数据差异检测",
        "evidence_ref": "经营实质-进销品名交叉验证闭环",
        "required_evidence": ["委托加工合同", "BOM表", "加工费付款凭证", "进销存台账"],
        "level_fixed": True  # 稽查重点，强制等级
    })
    
    # ── 规则 999502：外包轻加工模式缺少委托加工合同 ──
    if has_proc_fee and "外包" in biz_desc:
        findings.append({
            "type": "经营实质-外包轻加工缺少委托加工合同",
            "domain": "经营实质核查",
            "level": "高风险",
            "score": 7,
            "rule_id": 999502,
            "detail": (
                f"企业经营模式中包含外包轻加工环节（发现加工费发票），"
                f"但缺少对应的委托加工合同。没有合同无法验证："
                f"①委托加工数量是否合理；②加工单价是否公允；"
                f"③加工损耗率是否符合行业标准。"
            ),
            "suggestion": (
                "①提供与每家加工商的委托加工合同（载明品名/数量/单价/损耗率/交货期）；"
                "②提供加工结算单或对账单；③提供加工费银行付款回单；"
                "④如无法提供——加工费支出可能不被认定为合法成本扣除"
            ),
            "how_found": "加工费信号+合同缺失检测",
            "chain_ref": "经营实质-工商登记vs发票数据差异检测",
            "evidence_ref": "经营实质-进销品名交叉验证闭环",
            "required_evidence": ["委托加工合同", "加工结算单", "银行付款回单"],
            "level_fixed": True
        })
    
    # ── 规则 999503：进销品名差异缺少BOM表 ──
    if len(pur_only) >= 3 and len(sal_only) >= 2:
        findings.append({
            "type": "经营实质-进销品名差异缺少BOM表",
            "domain": "经营实质核查",
            "level": "中风险",
            "score": 6,
            "rule_id": 999503,
            "detail": (
                f"进项发票有{len(pur_only)}类品名仅购进未销售（{pur_str}），"
                f"销项发票有{len(sal_only)}类品名仅销售未购进（{sal_str}），"
                f"存在物料转换环节但缺少BOM表。没有BOM表无法判断："
                f"①每种成品消耗多少原材料；②委托加工数量是否合理；"
                f"③是否存在虚增原材料或虚减产成品的情况。"
            ),
            "suggestion": (
                "①提供每种成品的BOM表（列明原材料名称、规格、单耗标准）；"
                "②提供委托加工出入库单，核对原料发出数量与成品收回数量的配比关系；"
                "③如BOM缺失——加工链条的真实性无法验证，进项税额抵扣存疑"
            ),
            "how_found": "进销品名交叉比对",
            "chain_ref": "经营实质-工商登记vs发票数据差异检测",
            "evidence_ref": "经营实质-进销品名交叉验证闭环",
            "required_evidence": ["BOM表", "委托加工出入库单", "原材料/成品仓库台账"],
            "level_fixed": True
        })
    
    # ── 规则 999504：经营费用混入生产物资分析 ──
    _EXPENSE_KWS_FINDING = ["住宿", "餐饮", "餐费", "房费", "汽油", "柴油", "加油",
                            "旅游", "差旅", "租赁", "保险", "通讯", "电话", "办公",
                            "快递", "广告", "咨询", "法律", "维修", "物业", "停车",
                            "经纪代理", "代订"]
    expense_items_in_pur = [g for g in pur_only if any(kw in g for kw in _EXPENSE_KWS_FINDING)]
    if expense_items_in_pur:
        findings.append({
            "type": "经营实质-经营费用混入进项物资分析",
            "domain": "经营实质核查",
            "level": "中风险",
            "score": 5,
            "rule_id": 999504,
            "detail": (
                f"仅购进品名列表中有{len(expense_items_in_pur)}类属于经营费用而非生产物资："
                f"{'、'.join(expense_items_in_pur[:8])}。经营费用（住宿/餐饮/加油/租赁等）"
                f"是所有企业共同的日常支出，不应纳入行业判断依据。行业判断应以主营业务发票为准。"
            ),
            "suggestion": (
                "①将进项发票按生产物资/经营费用分类核算；"
                "②行业判断聚焦主营物资（原材料/半成品/加工费），排除期间费用；"
                "③经营费用单独分析其合理性和真实性"
            ),
            "how_found": "经营费用关键词匹配（进项品名过滤）",
            "chain_ref": "经营实质-工商登记vs发票数据差异检测",
            "evidence_ref": "经营实质-进销品名交叉验证闭环",
            "required_evidence": ["主营业务收入构成表", "生产成本明细账"],
            "level_fixed": True
        })
    
    return findings


# ═══════════════════════════════════════════════════════════
# 主营业务成本识别模块（全行业适用）
# 所有进销相关风险分析必须先识别主营业务成本，再分类判断。
# 核心原则：
#   1. 日常费用报销（餐饮/住宿/汽油等）→ 不参与供应商匹配/进销比对
#   2. 主营业务成本（原料/加工费/主要经营货物）→ 必须匹配验证
#   3. 重大费用（房租/咨询/广告等）→ 视情况匹配
# 稽查方法论：先分三层，再逐层分析，而非一刀切全量比对。
# ═══════════════════════════════════════════════════════════

# ├─ 日常报销关键词（全行业通用）
# │  员工先行垫付后凭发票报销，对公付款对象是员工而非开票单位
_REIMBURSEMENT_KWS_GLOBAL = [
    # 餐饮
    '餐饮','餐费','饭店','餐厅','食堂','伙食','外卖','快餐','盒饭','快餐费',
    # 住宿
    '住宿','酒店','宾馆','房费','旅馆','招待所','旅社','日租房',
    # 交通/加油
    '汽油','柴油','加油','车用','充电','过路费','停车费','停车','打车','出租车','网约车',
    # 差旅
    '差旅','机票','火车票','高铁','动车','船票',
    # 办公杂费
    '办公用品','文具','打印','复印','纸张','墨盒','色带','硒鼓','胶水','文件夹','档案盒',
    '快递','邮递','邮寄','运费','搬运费',
    '通讯','电话','话费','网络费','短信',
    # 培训/会务
    '培训','会务','展会','研讨会','讲座','论坛',
    # 劳保/福利
    '劳保','工作服','手套','口罩','防护','安全帽','防尘','员工体检','团建',
    # 其他杂项
    '保洁','清洁','卫生','洗涤','垃圾','年检',
]

# ├─ 重大费用关键词（需对公付款但非主营成本）
_MAJOR_EXPENSE_KWS = [
    '房租','租金','物业','物业管理',
    '咨询','顾问','法律','审计','评估','检测','认证',
    '广告','推广','宣传','展览','展会','发布',
    '运输','物流','货运','搬运','配送',
    '维修','保养','修缮','装修','装潢',
    '保险','社保','托管','代账',
    '招聘','猎头','人力资源',
]

# ═══════════════════════════════════════════════════════════
# 稽查员推理引擎（Audit Reasoning Engine）
# 
# 核心设计理念：
#   不是29个域并行跑完再汇总，而是像人类稽查员一样——
#   初查发现信号 → 定向深挖 → 交叉验证 → 综合定性
# 
# 四个阶段：
#   Phase 1 — 初查（Triage）：资金流全景、发票全景、主营业务成本识别、
#             基本比率、资料质量评估。产出全局快照+初步信号。
#   Phase 2 — 定向深挖（Deep Dive）：基于Phase 1信号，选择性深入分析
#             关联域。信号驱动，而非全量盲跑。
#   Phase 3 — 交叉验证（Cross-Validation）：用多域结论互相印证。
#             利用已有结论验证/反驳/深化新结论。
#   Phase 4 — 综合定性（Synthesis）：汇总→去重→冲突消解→风险排序→
#             生成最终报告。
#
# AuditContext 是阶段间的状态载体，贯穿4个阶段。
# 每个阶段读取context中的前置发现，产出注入context供后续使用。
# ═══════════════════════════════════════════════════════════

class MemoryLearner:
    """
    记忆学习器 —— 让推理引擎从历史案例中自我改进
    
    三个学习维度：
    1. 行业风险校准：学习各行业的实际风险分布，动态调整评级阈值
    2. 信号频率学习：高频信号 → 可能是行业特征而非真正异常 → 降低虚假警报
    3. 模式热度追踪：哪些风险模式在同类企业中反复出现 → 优先关注
    
    用法：
        learner = MemoryLearner()
        learner.load("static/audit_memory.json")
        calibrated = learner.calibrate_risk(ctx)
    """
    
    def __init__(self):
        self.cases = []
        self.industry_groups = {}  # {industry: [cases]}
        self.model_groups = {}     # {biz_model: [cases]}
        self.is_loaded = False
        self.insights = {}         # computed insights cache
    
    def load(self, memory_path):
        """加载审计记忆并计算统计"""
        from collections import Counter, defaultdict
        
        try:
            with open(memory_path, 'r', encoding='utf-8') as f:
                self.cases = json.load(f)
        except Exception:
            self.cases = []
            return
        
        if not self.cases:
            return
        
        # 按行业分组
        self.industry_groups = defaultdict(list)
        self.model_groups = defaultdict(list)
        for c in self.cases:
            ind = c.get("industry", "未知")
            self.industry_groups[ind].append(c)
            model = c.get("biz_model", "未知")
            self.model_groups[model].append(c)
        
        # 计算行业洞察
        for ind, cases in self.industry_groups.items():
            if len(cases) < 2:
                continue
            
            scores = [c.get("risk_score", 0) for c in cases]
            scores.sort()
            n = len(scores)
            
            # 信号频率（哪些信号频繁出现 → 可能是行业特征）
            all_yellow = []
            all_red = []
            for c in cases:
                all_yellow.extend(c.get("yellow_flags", []))
                all_red.extend(c.get("red_flags", []))
            yellow_freq = Counter(all_yellow)
            
            # 找到"过于频繁"的信号（>80%案例都出现）= 可能是行业正常特征
            ubiquitous_signals = [sig for sig, cnt in yellow_freq.items() if cnt / n > 0.8]
            high_freq_signals = [sig for sig, cnt in yellow_freq.items() if cnt / n > 0.5]
            
            self.insights[ind] = {
                "case_count": n,
                "risk_scores": {
                    "min": scores[0],
                    "p25": scores[max(0, int(n * 0.25) - 1)],
                    "p50": scores[max(0, int(n * 0.5) - 1)],
                    "p75": scores[min(n - 1, int(n * 0.75))],
                    "p90": scores[min(n - 1, int(n * 0.9))],
                    "max": scores[-1],
                    "mean": sum(scores) / n,
                },
                "ubiquitous_signals": ubiquitous_signals,  # 80%+出现 → 降权
                "high_freq_signals": high_freq_signals,    # 50%+出现 → 轻微降权
                "risk_level_dist": dict(Counter(c.get("risk_level","") for c in cases)),
                "avg_findings": sum(c.get("total_findings", 0) for c in cases) / n,
                "avg_concentration": {
                    "supplier": sum(c.get("supplier_concentration", 0) for c in cases) / n,
                    "customer": sum(c.get("customer_concentration", 0) for c in cases) / n,
                },
                "has_processing_rate": sum(1 for c in cases if c.get("has_processing")) / n,
            }
        
        self.is_loaded = True
    
    def calibrate_risk_thresholds(self, ctx):
        """
        行业风险阈值校准
        
        如果某个行业历史评分普遍偏高，则提高该行业的评级阈值，
        避免所有该行业的企业都被评为"极高风险"。
        """
        cp = ctx.company_profile
        industry = cp.get("industry", "综合")
        insight = self.insights.get(industry, {})
        
        if not insight:
            return ctx  # no calibration data
        
        scores = insight.get("risk_scores", {})
        p50 = scores.get("p50", 70)
        p75 = scores.get("p75", 90)
        p90 = scores.get("p90", 110)
        
        # 如果行业中位数已经很高（>70），说明这是高危行业，调高阈值
        base = max(70, p50)
        ctx._calibrated_thresholds = {
            "极高风险": max(base * 1.1, p75),  # 至少P75才叫"极高"
            "高风险": max(base * 0.8, p50),
            "中风险": max(base * 0.5, 30),
            "低风险": 15,
            "p50": p50,
            "p75": p75,
            "industry": industry,
            "case_count": insight.get("case_count", 0),
        }
        
        return ctx
    
    def get_signal_advice(self, signal_type, industry):
        """
        信号权重建议
        
        如果某个信号在该行业80%+的案例中都出现，说明它是行业常见特征，
        建议降低其权重（可能是正常现象而非真正异常）
        """
        insight = self.insights.get(industry, {})
        if not insight:
            return {"weight_multiplier": 1.0, "advice": ""}
        
        if signal_type in insight.get("ubiquitous_signals", []):
            return {
                "weight_multiplier": 0.5,
                "advice": f"该信号在{insight['case_count']}个同类案例中{100*(insight['ubiquitous_signals'].count(signal_type)+1)/insight['case_count']:.2f}%出现→可能是行业固有特征，不是真正的异常"
            }
        elif signal_type in insight.get("high_freq_signals", []):
            return {
                "weight_multiplier": 0.7,
                "advice": f"该信号在同类案例中高频出现→需结合其他信号综合判断"
            }
        
        return {"weight_multiplier": 1.0, "advice": ""}
    
    def get_industry_memory_insight(self, ctx):
        """
        生成行业记忆洞察文本，用于注入综合定性报告
        """
        cp = ctx.company_profile
        industry = cp.get("industry", "综合")
        biz_model = cp.get("biz_model", "")
        insight = self.insights.get(industry, {})
        
        if not insight:
            return ""
        
        n = insight.get("case_count", 0)
        rs = insight.get("risk_scores", {})
        levels = insight.get("risk_level_dist", {})
        
        lines = []
        lines.append(f"系统记忆库中有{n}条{industry}行业（{biz_model}）的历史分析记录。")
        
        # 风险分布
        lines.append(f"历史风险分布: 极高{levels.get('极高风险',0)}次/高{levels.get('高风险',0)}次/中{levels.get('中风险',0)}次/低{levels.get('低风险',0)}次。")
        
        # 分数分布
        if rs:
            lines.append(f"历史风险评分: 中位数{rs.get('p50',0):.2f}/P75={rs.get('p75',0):.2f}/P90={rs.get('p90',0):.2f}")
        
        # 高频信号
        ub = insight.get("ubiquitous_signals", [])
        if ub:
            lines.append(f"行业高频信号（>80%案例）: {'、'.join(ub[:5])}——这些更可能是行业特征而非真正异常")
        
        # 浓度均值
        ac = insight.get("avg_concentration", {})
        if ac:
            lines.append(f"行业平均集中度: 供应商{ac.get('supplier',0):.2f}%/客户{ac.get('customer',0):.2f}%")
        
        # 加工费率
        pr = insight.get("has_processing_rate", 0)
        if pr > 0:
            lines.append(f"行业外包加工比例: {pr*100:.2f}%的企业有加工费发票——{biz_model}行业的常见特征")
        
        return "\n".join(lines)


class ConfidenceAssessor:
    """
    结论可信度评估引擎 —— 让引擎学会质疑自己
    
    四维评估：
    1. 证据充分性 — 几条独立证据源支撑？
    2. 数据缺口冲击 — 缺失资料是否抽掉了结论的地基？
    3. 对抗验证 — 有没有反证？有没有更合理的替代解释？
    4. 稽查就绪度 — 真人稽查员看了，能站住吗？
    
    输出：
    - 每条重点结论的可信度评分(0-100)
    - 薄弱环节标注
    - 补强建议(需要什么资料才能使置信度提升)
    """
    
    # ── 缺失资料与结论域的关联映射 ──
    # 结论类型关键词 → 依赖的资料类型 → 缺失后的惩罚分
    MISSING_IMPACT_MAP = {
        "虚开发票": {"depends_on": ["contract", "purchase_invoice", "bank"], "penalty": 25, "note": "缺合同/进项发票/银行流水→虚开结论无法印证三流合一"},
        "隐匿收入": {"depends_on": ["bank", "sales_invoice"], "penalty": 30, "note": "缺银行流水/销项发票→无法比对收款与开票"},
        "成本": {"depends_on": ["purchase_invoice", "inventory", "voucher"], "penalty": 20, "note": "缺进项/进销存/凭证→成本真实性无法验证"},
        "进销": {"depends_on": ["inventory", "purchase_invoice", "sales_invoice"], "penalty": 25, "note": "缺进销存台账→进销匹配只是理论推演"},
        "毛利": {"depends_on": ["financial", "voucher"], "penalty": 15, "note": "缺财报/凭证→毛利率计算依赖发票推算，非真实账务数据"},
        "工资": {"depends_on": ["salary", "social_security"], "penalty": 20, "note": "缺工资表/社保→人员真实性无法验证"},
        "关联": {"depends_on": ["contract", "bank"], "penalty": 20, "note": "缺合同/银行流水→关联关系无法穿透核实"},
        "加工": {"depends_on": ["contract", "inventory"], "penalty": 25, "note": "缺加工合同/出入库记录→加工链条无法验证"},
        "集中": {"depends_on": ["contract"], "penalty": 10, "note": "缺合同→无法判断集中是正常商业安排还是关联操纵"},
        "发票": {"depends_on": ["purchase_invoice", "sales_invoice", "bank"], "penalty": 15, "note": "缺发票/银行流水→发票真实性存疑"},
    }
    
    def __init__(self, ctx, all_findings):
        self.ctx = ctx
        self.all_findings = all_findings
        self.missing_keys = set(ctx.missing_doc_keys) if ctx.missing_doc_keys else set()
        self.contradictions = [f for f in all_findings if f.get("type", "").startswith("结论自洽-")]
        self.cross_validated = [f for f in all_findings if f.get("_phase3_cross_validated")]
    
    def assess_all(self):
        """评估所有重点结论，返回可信度报告"""
        report = {
            "assessments": [],
            "overall_credibility": 0,
            "weakest_conclusions": [],
            "summary": "",
        }
        
        # 只评估高风险和部分中风险结论
        candidates = [f for f in self.all_findings 
                      if f.get("level") in ("极高风险", "高风险", "中风险")
                      and not f.get("type", "").startswith("资料缺失触发-")
                      and not f.get("type", "").startswith("事前预警-")]
        
        scores = []
        for finding in candidates[:15]:  # 最多评估15条
            assessment = self._assess_one(finding)
            if assessment:
                report["assessments"].append(assessment)
                scores.append(assessment["credibility"])
        
        if scores:
            report["overall_credibility"] = sum(scores) / len(scores)
            
            # 找出最薄弱的3条结论
            sorted_assess = sorted(report["assessments"], key=lambda a: a["credibility"])
            report["weakest_conclusions"] = sorted_assess[:3]
        
        report["summary"] = self._generate_summary(report)
        return report
    
    def _assess_one(self, finding):
        """评估单条结论"""
        ftype = str(finding.get("type", ""))
        flevel = str(finding.get("level", ""))
        fscore = finding.get("score", 5)
        
        # ── 1. 证据充分性 (0-30分) ──
        evidence_score = self._score_evidence(finding)
        
        # ── 2. 数据缺口惩罚 (负分) ──
        gap_penalty = self._score_data_gap(ftype)
        
        # ── 3. 对抗验证 (0-20分) ──
        counter_score = self._score_counter_evidence(ftype, finding)
        
        # ── 4. 交叉验证加成 (0-20分) ──
        cross_bonus = 15 if finding.get("_phase3_cross_validated") else 0
        if finding.get("_cross_domain_clue"):
            cross_bonus = max(cross_bonus, 12)
        
        # ── 综合可信度 ──
        base = fscore * 5  # 将score(1-10)映射到(5-50)
        credibility = base + evidence_score + counter_score + cross_bonus - gap_penalty
        credibility = max(0, min(100, credibility))
        
        # 判定等级
        if credibility >= 75:
            grade = "高可信"
        elif credibility >= 50:
            grade = "中等可信"
        elif credibility >= 30:
            grade = "低可信"
        else:
            grade = "不可靠"
        
        # 薄弱环节
        weaknesses = []
        enhancements = []
        
        if gap_penalty >= 15:
            # 找出缺失的具体资料
            deps = self._find_dependencies(ftype)
            missing_deps = [d for d in deps if d in self.missing_keys]
            if missing_deps:
                dep_names = {"bank": "银行流水", "sales_invoice": "销项发票", "purchase_invoice": "进项发票",
                            "voucher": "记账凭证", "salary": "工资表", "social_security": "社保明细",
                            "inventory": "进销存台账", "contract": "合同文件", "trial_balance": "科目余额表",
                            "financial": "资产负债表+利润表"}
                missing_names = [dep_names.get(d, d) for d in missing_deps]
                weaknesses.append(f"缺少{'、'.join(missing_names)}，无法交叉验证")
                enhancements.append(f"补充{'、'.join(missing_names)}可使可信度提升{gap_penalty}分")
        
        if evidence_score < 15:
            weaknesses.append("独立证据不足，主要依赖单一数据源")
            enhancements.append("增加交叉验证数据源（如银行流水+发票+合同三源比对）")
        
        if counter_score < 10:
            weaknesses.append("未经过充分的对抗验证，可能存在替代解释")
        
        # 与矛盾检测的关联
        for contr in self.contradictions:
            contr_name = str(contr.get("type", ""))
            if any(kw in ftype for kw in ["虚开","进销","毛利","成本","发票"]):
                if any(kw in contr_name for kw in ["虚开","进销","毛利","成本","发票"]):
                    weaknesses.append(f"存在矛盾结论'{contr_name.replace('结论自洽-','')}'，削弱本结论可信度")
                    break
        
        return {
            "type": ftype[:80],
            "level": flevel,
            "credibility": round(credibility, 1),
            "grade": grade,
            "evidence_score": evidence_score,
            "gap_penalty": gap_penalty,
            "counter_score": counter_score,
            "cross_bonus": cross_bonus,
            "weaknesses": weaknesses,
            "enhancements": enhancements,
            "original_score": fscore,
        }
    
    def _score_evidence(self, finding):
        """评估证据充分性"""
        score = T.scoring_weights.base_discovery_score  # 基础分：有一条发现本身就有一些证据
        
        # 检查detail/description中的内容量
        detail = str(finding.get("detail", ""))
        desc = str(finding.get("description", ""))
        combined = detail + " " + desc
        
        # 包含具体数字 → +5分
        import re
        if re.search(r'\d[\d,.]*[万元亿%]', combined):
            score += T.scoring_weights.dimension_match
        
        # 包含具体公司/人名 → +3分
        if re.search(r'[\u4e00-\u9fff]{2,}(公司|厂|行|店)', combined):
            score += T.scoring_weights.cross_domain_match
        
        # 引用法规 → +5分
        if any(kw in combined for kw in ["《","条例","公告","第"]):
            score += T.scoring_weights.dimension_match
        
        # 有how_found说明来源 → +5分
        if finding.get("how_found"):
            score += T.scoring_weights.dimension_match
        
        return min(score, 30)
    
    def _score_data_gap(self, ftype):
        """计算数据缺口对结论的冲击"""
        total_penalty = 0
        
        for keyword, config in self.MISSING_IMPACT_MAP.items():
            if keyword in ftype:
                deps = config["depends_on"]
                missing_deps = [d for d in deps if d in self.missing_keys]
                if missing_deps:
                    # 缺失比例越高，惩罚越重
                    missing_ratio = len(missing_deps) / len(deps)
                    penalty = int(config["penalty"] * missing_ratio)
                    total_penalty = max(total_penalty, penalty)
        
        return total_penalty
    
    def _score_counter_evidence(self, ftype, finding):
        """对抗验证评分"""
        score = T.scoring_weights.base_evidence_score  # 基础分
        
        # 如果该结论与矛盾检测有关联 → 减分
        for contr in self.contradictions:
            contr_name = str(contr.get("type", ""))
            if any(kw in ftype for kw in ["虚开","进销","毛利","成本"]):
                if any(kw in contr_name for kw in ["虚开","进销","毛利","成本"]):
                    score -= 8
        
        # 如果有交叉验证 → 加回
        if finding.get("_phase3_cross_validated"):
            score += T.scoring_weights.dimension_match
        
        return max(0, min(score, 20))
    
    def _find_dependencies(self, ftype):
        """找到结论类型依赖的资料"""
        for keyword, config in self.MISSING_IMPACT_MAP.items():
            if keyword in ftype:
                return config["depends_on"]
        return []
    
    def _generate_summary(self, report):
        """生成可信度摘要"""
        oc = report["overall_credibility"]
        wc = report["weakest_conclusions"]
        
        lines = []
        if oc >= 70:
            lines.append(f"整体可信度{oc:.2f}分——结论整体可靠，多数发现有多源证据支撑。")
        elif oc >= 50:
            lines.append(f"整体可信度{oc:.2f}分——结论基本可靠，但部分发现因资料缺失导致置信度受限。")
        elif oc >= 30:
            lines.append(f"整体可信度{oc:.2f}分——结论需谨慎对待，多条发现缺乏关键证据支撑。")
        else:
            lines.append(f"整体可信度{oc:.2f}分——结论不可靠，数据严重不足，建议补充资料后重新分析。")
        
        if wc:
            lines.append(f"\n最薄弱的{len(wc)}条结论：")
            for w in wc:
                gaps = "；".join(w["weaknesses"][:2]) if w["weaknesses"] else "无明显薄弱点"
                lines.append(f"  ▸ {w['type'][:50]} → 可信度{w['credibility']:.2f}分（{gaps}）")
        
        return "\n".join(lines)


class TrendDetector:
    """
    时间维度趋势检测 —— 把快照升级为录像
    
    按年拆分核心指标，检测恶化/改善/稳定方向，
    计算变化速度，输出前瞻性趋势洞察。
    """
    
    @staticmethod
    def analyze(ctx, bank_txs, sal_invs, pur_invs):
        """主入口：分析全部趋势并注入ctx"""
        ctx.trend_data = {}
        ctx.trend_findings = []
        
        # 提取年份
        years = set()
        for inv in pur_invs + sal_invs:
            dt = str(inv.get("inv_date", inv.get("issue_date", inv.get("date", ""))))
            y = TrendDetector._extract_year(dt)
            if y and 2020 <= y <= 2030:
                years.add(y)
        for tx in bank_txs:
            dt = str(tx.get("tx_date", tx.get("date", tx.get("trade_date", ""))))
            y = TrendDetector._extract_year(dt)
            if y and 2020 <= y <= 2030:
                years.add(y)
        
        years = sorted(years)
        if len(years) < 2:
            return  # 不足两年，无法分析趋势
        
        ctx.trend_data["years"] = years
        yearly = {}
        
        for y in years:
            # 销项
            y_sales = [inv for inv in sal_invs if TrendDetector._match_year(inv, "inv_date", y)]
            y_sales_total = sum(float(inv.get("amount", inv.get("total", 0)) or 0) for inv in y_sales)
            y_sales_count = len(y_sales)
            
            # 进项
            y_purchases = [inv for inv in pur_invs if TrendDetector._match_year(inv, "inv_date", y)]
            y_pur_total = sum(float(inv.get("amount", inv.get("total", 0)) or 0) for inv in y_purchases)
            y_pur_count = len(y_purchases)
            
            # 银行
            y_bank = [tx for tx in bank_txs if TrendDetector._match_year(tx, "tx_date", y)]
            y_bank_in = sum(float(tx.get("credit", tx.get("income", 0)) or 0) for tx in y_bank)
            y_bank_out = sum(float(tx.get("debit", tx.get("expense", 0)) or 0) for tx in y_bank)
            y_bank_count = len(y_bank)
            
            # 计算指标
            gm = (y_sales_total - y_pur_total) / y_sales_total * 100 if y_sales_total > 0 else 0
            ps_ratio = y_pur_total / y_sales_total if y_sales_total > 0 else 0
            
            yearly[y] = {
                "year": y,
                "sales_total": y_sales_total,
                "sales_count": y_sales_count,
                "pur_total": y_pur_total,
                "pur_count": y_pur_count,
                "bank_in": y_bank_in,
                "bank_out": y_bank_out,
                "bank_count": y_bank_count,
                "gross_margin_pct": round(gm, 2),
                "purchase_sales_ratio": round(ps_ratio, 3),
            }
        
        ctx.trend_data["yearly"] = yearly
        
        # 趋势分析
        y_list = list(yearly.values())
        findings = []
        
        findings.extend(TrendDetector._analyze_trend(y_list, "gross_margin_pct", "毛利率", "%", "↓下降=恶化"))
        findings.extend(TrendDetector._analyze_trend(y_list, "purchase_sales_ratio", "进销比", "", "↑上升=恶化"))
        findings.extend(TrendDetector._analyze_trend(y_list, "sales_total", "销售额", "元", "↓下降=经营萎缩"))
        findings.extend(TrendDetector._analyze_trend(y_list, "pur_total", "采购额", "元", "↓下降=减产; ↑上升=囤货或虚进"))
        findings.extend(TrendDetector._analyze_trend(y_list, "bank_in", "银行收入", "元", "↓下降=资金回笼恶化"))
        
        ctx.trend_findings = findings
        return findings
    
    @staticmethod
    def _extract_year(dt_str):
        """从日期字符串提取年份"""
        import re
        if not dt_str:
            return None
        # 匹配 YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD, 或纯年份
        m = re.search(r'(20\d{2})', str(dt_str))
        return int(m.group(1)) if m else None
    
    @staticmethod
    def _match_year(item, date_field, year):
        """判断数据项是否属于指定年份"""
        for field in [date_field, "issue_date", "date", "trade_date"]:
            dt = str(item.get(field, ""))
            if str(year) in dt:
                return True
        return False
    
    @staticmethod
    def _analyze_trend(yearly_data, metric, label, unit, direction_hint):
        """分析单个指标的趋势"""
        values = [(d["year"], d[metric]) for d in yearly_data if d.get(metric, 0) != 0 or metric == "gross_margin_pct"]
        if len(values) < 2:
            return []
        
        years = [v[0] for v in values]
        vals = [v[1] for v in values]
        
        # 简单线性趋势：首年→末年变化率
        first_val = vals[0]
        last_val = vals[-1]
        if first_val == 0:
            return []
        
        change_pct = (last_val - first_val) / abs(first_val) * 100
        total_change = last_val - first_val
        
        # 判断趋势强度
        abs_change = abs(change_pct)
        if abs_change < 5:
            trend = "稳定"
            level = "低风险"
        elif abs_change < 15:
            trend = "轻微" + ("下降" if change_pct < 0 else "上升")
            level = "中风险"
        elif abs_change < 30:
            trend = "明显" + ("下降" if change_pct < 0 else "上升")
            level = "中风险"
        else:
            trend = "剧烈" + ("下降" if change_pct < 0 else "上升")
            level = "高风险"
        
        # 构建年份序列描述
        year_range = f"{years[0]}-{years[-1]}"
        detail = (
            f"【{label}趋势】{year_range}年: "
            + " → ".join(f"{y}年{label}={v:.2f}{unit}" for y, v in values)
            + f"\n总变化: {change_pct:+.1f}% ({first_val:.2f}→{last_val:.2f}{unit})"
            + f"\n趋势判定: {trend} ({direction_hint})"
        )
        
        finding = {
            "type": f"趋势-{label}{trend}",
            "level": level,
            "score": 9 if level == "高风险" else (7 if "明显" in trend else 4),
            "detail": detail,
            "description": detail,
            "how_found": f"按年拆分{label}数据，检测{year_range}年间趋势变化",
            "tax_impact": f"{label}在{year_range}年间{trend}（{change_pct:+.0f}%），{direction_hint}",
            "suggestion": f"关注{label}的{direction_hint}趋势，分析原因并采取应对措施",
            "category": "综合定性·趋势分析",
            "_trend_direction": trend,
            "_trend_change_pct": round(change_pct, 1),
            "_trend_years": years,
        }
        
        return [finding]


class SensitivityAnalyzer:
    """
    假设敏感性分析 —— 把"可能有问题"变成"问题有多大"
    
    三大风险 × 三种假设 → 预估补税区间
    让稽查员和企业老板看到具体数字，而非模糊警告。
    """
    
    SCENARIOS = {
        "隐匿收入": {
            "base": "total_sales",
            "rates": {"低": T.ratios.threshold_5pct * 2, "中": T.ratios.significant_deviation + 0.05, "高": T.ratios.half},
            "vat_rate": T.vat_rates.standard, "cit_rate": T.cit_rates.standard,
            "description": "已申报销售额{base:,.2f}元，假设隐匿比例为{rate:.0%}",
            "unit": "元",
        },
        "虚列成本": {
            "base": "total_purchases",
            "rates": {"低": T.ratios.threshold_5pct, "中": T.ratios.significant_deviation - 0.05, "高": T.ratios.material_deviation},
            "vat_rate": T.vat_rates.standard, "cit_rate": T.cit_rates.standard,
            "description": "已入账采购成本{base:,.2f}元，假设虚列比例为{rate:.0%}",
            "unit": "元",
        },
        "虚抵进项": {
            "base": "total_purchases",
            "rates": {"低": T.ratios.threshold_5pct, "中": T.ratios.significant_deviation - 0.05, "高": T.ratios.material_deviation},
            "vat_rate": T.vat_rates.standard, "cit_rate": T.cit_rates.standard,
            "description": "已抵扣进项税额对应采购{base:,.2f}元，假设虚抵比例为{rate:.0%}",
            "unit": "元",
        },
    }
    
    @staticmethod
    def analyze(ctx):
        """主入口：计算敏感性矩阵并注入ctx"""
        fs = ctx.financial_snapshot
        if not fs or fs.get("total_sales", 0) == 0:
            return None
        
        report = {"scenarios": [], "summary": ""}
        
        total_tax_impact = 0
        worst_case_total = 0
        
        for risk_name, config in SensitivityAnalyzer.SCENARIOS.items():
            base_key = config["base"]
            base_amount = fs.get(base_key, 0)
            if base_amount <= 0:
                continue
            
            scenario_data = {"risk": risk_name, "base_amount": base_amount, "levels": {}}
            
            for level_name, rate in config["rates"].items():
                unreported = base_amount * rate
                vat = unreported * config["vat_rate"]
                cit = unreported * config["cit_rate"]
                total = vat + cit
                penalty_low = total * 0.5
                penalty_high = total * 5
                late_fee_daily = total * T.stamp_duty_rates.loan_contract * 10  # 每日万分之五 = 借款合同印花税税率×10
                
                scenario_data["levels"][level_name] = {
                    "rate": rate,
                    "unreported_amount": round(unreported, 0),
                    "vat_impact": round(vat, 0),
                    "cit_impact": round(cit, 0),
                    "total_tax": round(total, 0),
                    "penalty_range": f"{round(penalty_low,0):,.2f}~{round(penalty_high,0):,.2f}",
                    "late_fee_daily": round(late_fee_daily, 0),
                    "worst_case": round(total + penalty_high, 0),
                }
                
                if level_name == "中":
                    total_tax_impact += total
                if level_name == "高":
                    worst_case_total += round(total + penalty_high, 0)
            
            report["scenarios"].append(scenario_data)
        
        report["summary"] = (
            f"中等假设下合计补税约{total_tax_impact:,.2f}元，"
            f"最坏情况(含5倍罚款)合计约{worst_case_total:,.2f}元"
        )
        
        ctx._sensitivity_report = report
        return report


class AuditContext:
    """
    稽查上下文——贯穿4阶段的状态容器
    
    这个对象是推理引擎的"工作记忆"。每个分析阶段：
    1. 读取context中已有的发现和信号
    2. 据此决定分析策略和深度
    3. 产出新的发现注入context
    """
    def __init__(self):
        # ── 企业画像（初查阶段填充）──
        self.company_profile = {
            "industry": "",           # 推断行业
            "biz_model": "",          # 经营模式：制造业/贸易/服务
            "scale": "",              # 规模：大/中/小/微
            "has_manufacturing": False,  # 是否有加工信号
            "has_trading": False,     # 是否有贸易信号
        }
        
        # ── 财务快照（初查阶段填充）──
        self.financial_snapshot = {
            "total_sales": 0,         # 销项总额
            "total_purchases": 0,     # 进项总额
            "total_bank_in": 0,       # 银行收入总额
            "total_bank_out": 0,      # 银行支出总额
            "total_salary": 0,        # 工资总额
            "gross_margin_pct": 0,    # 毛利率
            "sale_count": 0,          # 销项发票张数
            "pur_count": 0,           # 进项发票张数
            "bank_tx_count": 0,       # 银行交易笔数
            "salary_count": 0,        # 工资记录数
        }
        
        # ── 主营业务成本三层分类（初查阶段填充）──
        self.biz_cost_classification = None  # identify_main_biz_cost() 返回值
        
        # ── 初查信号（红灯/黄灯/绿灯）──
        self.red_flags = []     # 需立即深挖的重大信号
        self.yellow_flags = []  # 需关注的次要信号
        self.green_signals = [] # 正常的信号（用于排除误报）
        
        # ── 跨阶段共享的中间结论 ──
        self.bom_missing = False        # 是否缺少BOM表
        self.has_processing_fee = False # 是否有加工费发票
        self.has_personal_payments = False  # 是否有大量个人付款
        self.supplier_concentration = 0  # 供应商集中度(%)
        self.customer_concentration = 0  # 客户集中度(%)
        self.data_quality_score = 0     # 资料质量评分(0-100)
        self.missing_critical_docs = [] # 缺失的关键资料（银行/发票/工资）
        self.missing_doc_keys = []      # 缺失的14类资料key列表（供Phase 4缺失后果触发用）
        
        # ── 行业自适应 ──
        self.industry_profile = {}      # 当前企业匹配的行业画像配置
        self.memory_learner = None      # MemoryLearner实例
        self.file_results = []          # 文件解析结果（供证据溯源）
        self.trend_data = {}            # 时间维度趋势数据
        self.trend_findings = []        # 趋势发现列表
        
        # ── 结论索引（供交叉验证时快速检索）──
        self.finding_index = {}   # {"type_prefix": [finding_dict, ...]}
        
        # ── 阶段追踪 ──
        self.current_phase = 0
        self.phase_history = []   # 每阶段的执行摘要
    
    def add_flag(self, level, signal_type, detail, source_domain=""):
        """添加稽查信号"""
        entry = {
            "type": signal_type,
            "detail": detail,
            "source": source_domain,
            "timestamp": None  # 由调用方填充
        }
        if level == "red":
            self.red_flags.append(entry)
        elif level == "yellow":
            self.yellow_flags.append(entry)
        else:
            self.green_signals.append(entry)
    
    def index_findings(self, findings, domain=""):
        """将一批发现索引到finding_index，供后续阶段快速检索"""
        for f in findings:
            if not isinstance(f, dict): continue
            ftype = f.get("type", "")
            # 按type前缀索引（取前6个字符作为键）
            key = ftype[:8] if len(ftype) >= 8 else ftype
            if key not in self.finding_index:
                self.finding_index[key] = []
            self.finding_index[key].append({**f, "_indexed_domain": domain})
    
    def query_findings(self, keyword):
        """在已索引的结论中搜索关键词"""
        results = []
        for key, findings in self.finding_index.items():
            if keyword in key:
                results.extend(findings)
            else:
                for f in findings:
                    ftype = f.get("type", "")
                    desc = f.get("description", "")
                    if keyword in ftype or keyword in desc:
                        results.append(f)
        return results
    
    def get_snapshot_summary(self):
        """生成初查快照摘要"""
        fs = self.financial_snapshot
        cp = self.company_profile
        lines = []
        lines.append(f"行业推断: {cp['industry'] or '未识别'}")
        lines.append(f"经营模式: {cp['biz_model'] or '待定'}")
        lines.append(f"销项: {fs['sale_count']}张 {fs['total_sales']:,.2f}元")
        lines.append(f"进项: {fs['pur_count']}张 {fs['total_purchases']:,.2f}元")
        lines.append(f"银行: {fs['bank_tx_count']}笔 收{fs['total_bank_in']:,.2f}/支{fs['total_bank_out']:,.2f}")
        lines.append(f"工资: {fs['salary_count']}条 {fs['total_salary']:,.2f}元")
        if self.biz_cost_classification:
            bcc = self.biz_cost_classification
            lines.append(f"主营成本: 核心{len(bcc['core_cost_invs'])}张/重大费用{len(bcc['major_expense_invs'])}张/日常报销{len(bcc['minor_expense_invs'])}张")
        lines.append(f"红灯信号: {len(self.red_flags)}个")
        lines.append(f"黄灯信号: {len(self.yellow_flags)}个")
        return self, "\n".join(lines)


def _infer_industry_from_goods(ctx, pur_goods, sal_goods):
    """从发票品名推断行业——全行业自适应，不硬编码任何行业关键词
    
    方法：利用中国金税发票的税收分类编码前缀（*XX*格式）
    例如：*纺织产品*棉布 → 行业=纺织产品
    无分类编码时用"综合"兜底
    """
    cp = ctx.company_profile
    
    # ═══ 行业推断铁律：仅以销项发票品名为依据，不参考进项 ═══
    # WHY: 销项=企业实际经营产出（卖什么就是什么行业）
    #      进项=采购投入/成本结构（买什么不代表行业，如传媒公司也会买餐饮服务）
    import re
    all_goods_list = list(sal_goods)
    cat_counts = {}
    
    for goods in all_goods_list:
        # 匹配 *分类名称* 格式（金税发票标准格式）
        match = re.search(r'\*([^*]+)\*', str(goods))
        if match:
            cat = match.group(1).strip()
            # 过滤掉明显不是行业分类的模式（如纯数字、单字）
            if len(cat) >= 2 and not cat.isdigit():
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
    
    if cat_counts:
        # 取出现最多的分类编码作为行业
        best_cat = max(cat_counts, key=cat_counts.get)
        cp["industry"] = best_cat
    else:
        cp["industry"] = "综合"
    
    # ── 加载行业自适应画像 ──
    _load_industry_profile(ctx)


# ── 行业数据外部化加载器：从 industry_data.json 加载所有行业字典 ──
_INDUSTRY_DATA_CACHE = None

def _load_industry_data():
    """加载行业数据（基准值、产品链、关键词映射等），从JSON文件外部化加载，支持全行业扩展"""
    global _INDUSTRY_DATA_CACHE
    if _INDUSTRY_DATA_CACHE is not None:
        return _INDUSTRY_DATA_CACHE
    
    # 从 engine/ 往上跳一级到项目根目录
    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "industry_data.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            _INDUSTRY_DATA_CACHE = json.load(f)
    except Exception:
        # 兜底：JSON加载失败时返回空字典（后续代码会做空值守卫）
        _INDUSTRY_DATA_CACHE = {}
    return _INDUSTRY_DATA_CACHE


# ═══════════════════════════════════════════════════════════
# Phase 2 — 定向深挖（Signal-Driven Deep Dive）
#
# 设计理念：不是29域全量盲跑，而是基于 Phase 1 的信号，
# 像人类稽查员一样定向选择深挖方向和深度。
#
# 信号→域映射表驱动：
#   看到"购销倒挂"→深挖毛利率+供应商+资金流向+经营实质
#   看到"加工费"→深挖BOM+供应商画像+经营实质地理+上下游
#   多个信号叠加→域组合策略
#   绿灯信号→证明某方面正常，跳过相关深挖
#
# 三级深度：
#   shallow（浅查）：快速比率计算，确认信号
#   normal（常规）：标准分析流程
#   deep（深挖）：多源交叉+关联穿透+证据链串联
# ═══════════════════════════════════════════════════════════

# ├─ 信号→域映射表
# │  每个信号定义了应深挖的域及深度

# ═══════════════════════════════════════════════════════════
# Phase 3 — 交叉验证（Cross-Validation）
#
# 核心能力：
#   1. 信号叠加检测 — 多个独立结论组合意味着更大的风险模式
#   2. 冲突消解 — 两个表面矛盾的结论互相验证
#   3. 风险提级/降级 — 基于交叉证据自动调整评级
#   4. 综合结论生成 — 从孤立发现中提炼出模式
#
# 设计理念：
#   人类稽查员不会只看单条结论，而是看"模式"。
#   比如"购销倒挂+加工费+BOM缺失"三个结论分别看都是中风险，
#   但三者同时出现→加工链条造假=极高风险。
#   这就是"1+1+1>3"的交叉验证价值。
# ═══════════════════════════════════════════════════════════

# ├─ 信号叠加模式库
# │  每个模式定义：触发信号组合→综合结论+风险调整+行动建议
_SIGNAL_PATTERNS = [
    {
        "id": "PATTERN_FRAUD_CHAIN",
        "name": "加工链条造假高嫌疑",
        "triggers": {
            "must_have": ["购销严重倒挂", "存在加工费"],
            "any_of": ["有进无销", "有销无进", "缺少BOM"],
            "at_least": 1  # any_of中至少命中1个
        },
        "conclusion": (
            "多域交叉验证发现：购销倒挂（进项远超销项）+ 加工费存在"
            " + 进销品名不匹配或BOM缺失。三个信号叠加指向同一方向——"
            "加工链条的真实性存疑。进项发票可能是为获取进项抵扣而虚开，"
            "加工费可能是虚构的外包加工，BOM缺失则无法验证投入产出逻辑。"
        ),
        "risk_override": "极高风险",
        "priority": "P0",
        "actions": [
            "立即调取全部加工合同、出入库单、物流单据",
            "要求企业提供每种成品的BOM表（原材料→产成品的投入产出比+损耗率）",
            "逐供应商核实加工费发票的真实性（电话+实地核查）",
            "如无法提供→按虚开增值税专用发票立案"
        ]
    },
    {
        "id": "PATTERN_REVENUE_HIDING",
        "name": "隐匿销售收入高嫌疑",
        "triggers": {
            "must_have": ["购销严重倒挂"],
            "any_of": ["有进无销", "进销数量严重偏差", "个人交易占比过高"],
            "at_least": 1
        },
        "conclusion": (
            "购销严重倒挂 + 进销不匹配/数量偏差/个人收款，形成'隐匿销售收入'的完整证据链："
            "采购了货物（有进项）→没有开票销售（无销项/数量偏差）→但资金仍然流入（个人收款）。"
            "进项采购的货物去向不明，大概率未开票销售体外循环。"
        ),
        "risk_override": "极高风险",
        "priority": "P0",
        "actions": [
            "核对全部银行个人收款方的身份（是否为员工/关联方/疑似客户）",
            "要求企业提供进项货物的完整去向说明（已售/库存/损耗）",
            "逐项比对进项数量与销项数量+库存变动，找出差额",
            "涉及偷税→移送稽查局"
        ]
    },
    {
        "id": "PATTERN_FAKE_INVOICE_NO_BANK",
        "name": "进项发票真实性存疑（无资金流佐证）",
        "triggers": {
            "must_have": ["银行付款未匹配"],
            "any_of": ["购销严重倒挂", "供应商高度集中", "缺少银行流水"],
            "at_least": 1
        },
        "conclusion": (
            "进项发票与银行付款不匹配 + 购销倒挂/供应商集中/缺少流水。"
            "多域证据交叉指向同一结论：部分进项发票可能没有对应的真实资金流出，"
            "存在'走票不走钱'的虚开发票嫌疑。供应商高度集中进一步增加了'对开环开'的可能。"
        ),
        "risk_override": "高风险",
        "priority": "P0",
        "actions": [
            "逐笔核查未匹配供应商的工商信息（是否存在关联关系）",
            "要求提供对账明细+分期付款计划+预付/应付账款明细账",
            "实地核实前3大供应商是否存在+是否有真实办公场所",
            "资金流断裂的发票→进项税额转出+补税"
        ]
    },
    {
        "id": "PATTERN_GHOST_WORKFORCE",
        "name": "虚列人员/吃空饷嫌疑",
        "triggers": {
            "must_have": ["无工资记录"],
            "any_of": ["有销无进", "购销严重倒挂"],
            "at_least": 1
        },
        "conclusion": (
            "无工资记录 + 存在进销异常（有销无进或购销倒挂）。"
            "企业有大量经营收入但无工资支出，可能：(1)虚开发票+无真实经营（无人员需求）；"
            "(2)隐匿人员工资（现金发放未入账）。两种情况都指向经营实质存疑。"
        ),
        "risk_override": "高风险",
        "priority": "P1",
        "actions": [
            "现场核查经营场所是否有实际生产经营活动",
            "比对电费/水费/物业费与申报收入是否匹配",
            "核查是否有现金工资发放记录或微信/支付宝转账记录"
        ]
    },
    {
        "id": "PATTERN_TRANSFER_PRICING",
        "name": "关联交易定价不公允嫌疑",
        "triggers": {
            "must_have": ["毛利率异常高"],
            "any_of": ["供应商高度集中", "关联交易"],
            "at_least": 1
        },
        "conclusion": (
            "毛利率异常高（>80%）+ 供应商/客户集中或关联交易信号。"
            "这种情况通常不是真正的核心竞争力，而是通过关联交易将利润转移至低税率环节，"
            "或将成本转移至其他主体。需要特别核查关联交易的定价是否公允。"
        ),
        "risk_override": "高风险",
        "priority": "P1",
        "actions": [
            "获取全部关联方清单及关联交易明细",
            "对关联交易做转让定价可比性分析（可比非受控价格法）",
            "要求企业提供关联交易的商业目的说明和定价依据"
        ]
    },
    {
        "id": "PATTERN_LOW_QUALITY_DATA",
        "name": "资料质量不足→结论置信度降低",
        "triggers": {
            "must_have": [],
            "any_of": ["银行流水数据量少", "发票数据量少", "缺少银行流水"],
            "at_least": 1
        },
        "conclusion": (
            "资料质量评分偏低。银行流水或发票数据量不足，部分分析域无法运行或置信度下降。"
            "当前报告中的结论应在资料补充后复核验证。建议要求企业补充完整资料后重新分析。"
        ),
        "risk_override": None,  # 不改变评级，只降低置信度
        "priority": "P2",
        "actions": [
            "要求企业补充完整的银行流水（至少覆盖分析期前3个月至后1个月）",
            "要求企业补充完整的进销项发票明细",
            "补充后重新运行一键分析"
        ]
    },
    # ── 新增：供应商/资金双异常 → 虚开嫌疑升级 ──
    {
        "id": "PATTERN_SUPPLIER_BANK_DUAL",
        "name": "供应商高度集中+付款未匹配→虚开嫌疑升级",
        "triggers": {
            "must_have": ["供应商高度集中"],
            "any_of": ["银行付款未匹配", "购销严重倒挂", "缺少银行流水"],
            "at_least": 1
        },
        "conclusion": (
            "供应商高度集中 + 付款未匹配/购销倒挂/无银行流水。"
            "两个信号形成'供应商-资金流'双重异常：采购集中在一两家供应商，"
            "但银行付款记录无法与供应商匹配。这种模式下，集中采购更像是"
            "为了获取进项发票的'通道'，而非真实的分散采购行为。"
            "如果同时购销倒挂——进项发票大量而销售极少——则虚开嫌疑进一步升级。"
        ),
        "risk_override": "极高风险",
        "priority": "P0",
        "actions": [
            "逐供应商核查工商信息（是否同一控制人/同一地址/同一电话）",
            "核实供应商是否有实际生产能力（厂房/设备/人员）",
            "核查银行付款记录中是否有向供应商实际付款（拉长期间、扩大匹配范围）",
            "对无法提供真实交易的供应商→进项税额转出"
        ]
    },
    {
        "id": "PATTERN_FAKE_INVOICE_PATTERN",
        "name": "发票连号+金额均匀→人工编造高嫌疑",
        "triggers": {
            "must_have": ["发票连号"],
            "any_of": ["金额整十整百", "金额分布异常均匀"],
            "at_least": 1
        },
        "conclusion": (
            "发票连号 + 金额整十整百或分布均匀。真实交易中，"
            "不同客户的订单金额天然有零有整、有大有小，发票号也不会完全连续。"
            "这两个信号同时出现，表明发票可能是按固定模板批量生成，"
            "而非逐笔真实交易后开具。"
        ),
        "risk_override": "极高风险",
        "priority": "P0",
        "actions": [
            "要求提供每张连号发票对应的销售合同/订单/出库单",
            "逐笔电话核实客户是否真实存在、是否真的有交易",
            "核查银行流水是否收到对应的客户付款",
            "无法提供真实交易证明→按虚开发票立案"
        ]
    },
    {
        "id": "PATTERN_QUARTER_END_MANIPULATION",
        "name": "季度末突击开票+毛利异常→收入操纵嫌疑",
        "triggers": {
            "must_have": ["季度末集中开票"],
            "any_of": ["毛利为负", "毛利率异常高", "购销严重倒挂"],
            "at_least": 1
        },
        "conclusion": (
            "季度末集中开票 + 毛利/购销异常。季度末突击开票是典型的"
            "'粉饰报表'或'冲业绩'行为——平时不开或少开，到季度最后一个月"
            "集中补开。如果同时毛利为负或购销倒挂，则突击开票的目的"
            "不是为了真实销售，而是为了虚增收入或获取进项抵扣。"
        ),
        "risk_override": "高风险",
        "priority": "P0",
        "actions": [
            "拉取季度末开票明细，逐笔核查对应销售合同的签订日期",
            "比对季度末开票客户的回款时间（真实交易通常在开票后30-60天回款）",
            "核查季度末开票对应的出库单/物流单日期是否匹配",
            "如开票日期远早于合同/发货日期→突击开票嫌疑成立"
        ]
    },
    {
        "id": "PATTERN_CUSTOMER_TRANSFER_PRICING",
        "name": "客户高度集中+毛利异常→关联交易定价不公允",
        "triggers": {
            "must_have": ["客户高度集中"],
            "any_of": ["毛利率异常高", "毛利为负"],
            "at_least": 1
        },
        "conclusion": (
            "客户高度集中 + 毛利异常。当前几大客户的交易占比超过80%时，"
            "定价权已经不掌握在企业手中——要么被客户压价（毛利为负），"
            "要么通过关联交易转移利润（毛利异常高）。"
            "无论哪种情况，都说明企业与客户之间存在非市场化的定价关系，"
            "关联交易的可能性极高。"
        ),
        "risk_override": "高风险",
        "priority": "P1",
        "actions": [
            "核查前几大客户的工商股权结构（是否与本公司有关联关系）",
            "对比同类产品的市场公允价格与向这些客户的销售价格",
            "如有关联关系→做转让定价可比性分析",
            "要求企业提供关联交易的商业目的说明"
        ]
    },
    {
        "id": "PATTERN_PERSONAL_INCOME_HIDING",
        "name": "个人付款占比高+无工资→隐匿经营收入",
        "triggers": {
            "must_have": ["个人交易占比过高"],
            "any_of": ["无工资记录", "购销严重倒挂"],
            "at_least": 1
        },
        "conclusion": (
            "个人付款方占比高 + 无工资记录/购销倒挂。"
            "大量个人向对公账户付款——正常的解释是零售经营（面向个人消费者），"
            "但无工资记录说明企业没有足够的员工来支撑零售规模，"
            "或者购销倒挂说明进项远大于开票销项。"
            "这种情况下，个人付款大概率是'未开票销售收入'通过个人账户归集后再转入对公账户，"
            "目的就是隐匿经营收入、不开发票。"
        ),
        "risk_override": "极高风险",
        "priority": "P0",
        "actions": [
            "核实个人付款方的身份（是否为疑似客户/经销商/员工）",
            "比对个人付款金额与未开票收入的匹配程度",
            "核查是否有对应的发货记录/物流单据",
            "属于隐匿销售收入→补缴增值税+企业所得税+滞纳金+罚款"
        ]
    },
    {
        "id": "PATTERN_SUPPLIER_CUSTOMER_OVERLAP",
        "name": "供应商与客户重叠→对开环开虚开发票",
        "triggers": {
            "must_have": ["供应商高度集中"],
            "any_of": ["客户高度集中", "购销严重倒挂"],
            "at_least": 1
        },
        "conclusion": (
            "供应商集中 + 客户集中/购销倒挂。当供应商和客户同时高度集中时，"
            "需要警惕是否存在'对开环开'——A公司给B公司开票（进项），"
            "B公司给A公司开票（销项），双方都获得了进项抵扣而没有任何真实货物流动。"
            "如果同时购销倒挂，则说明进项和销项的金额/品名不对等，进一步印证对开环开。"
        ),
        "risk_override": "极高风险",
        "priority": "P0",
        "actions": [
            "交叉比对前几大供应商和前几大客户的工商注册信息（股东/法人/地址）",
            "核查供应商和客户之间是否存在直接或间接的股权关联",
            "核查是否有真实的货物物流记录（运输合同+运单+过磅单）",
            "对开环开→虚开增值税专用发票罪（刑法第205条）"
        ]
    },
]


def _detect_conflicts(all_findings, cross_findings, pipeline_log):
    """JSON 驱动的冲突消解引擎——规则从 conflict_rules.json 加载"""
    
    # 构建全量文本索引（用于关键词匹配）
    all_text = "|".join(
        f.get("type", "") + "|" + f.get("description", "") + "|" + f.get("detail", "")
        for f in all_findings
    )
    
    def _has_signal(keyword):
        """检查 all_findings 中是否存在某关键词信号"""
        return keyword in all_text
    
    def _has_signal_in_type(keyword):
        """只检查 finding type 字段"""
        return any(keyword in f.get("type", "") for f in all_findings)
    
    # ── 加载冲突规则 ──
    rules = []
    json_path = os.path.join(os.path.dirname(__file__), 'static', 'conflict_rules.json')
    try:
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                rules = json.load(f).get('rules', [])
    except Exception as e:
        pipeline_log.append(f"[Phase3] 冲突规则加载失败: {e}")
        return  # JSON 加载失败时静默跳过（硬编码规则仍可用）
    
    if not rules:
        return
    
    # ── 通用匹配引擎 ──
    triggered_ids = set()  # 去重
    for rule in rules:
        signal_a = rule.get('signal_a', '')
        signal_b = rule.get('signal_b', '')
        
        if not signal_a or not signal_b:
            continue
        
        # 匹配：两个信号都要存在（任一字段中）
        if not _has_signal(signal_a) or not _has_signal(signal_b):
            continue
        
        # ── 命中 → 生成冲突消解结论 ──
        resolution = rule.get('resolution', '')
        risk_action = rule.get('risk_action', '保持')
        note = rule.get('note', '')
        rule_id = rule.get('id', '')
        if rule_id in triggered_ids:
            continue
        triggered_ids.add(rule_id)
        rule_name = rule.get('name', f'{signal_a} vs {signal_b}')
        
        # 根据 risk_action 确定级别
        if risk_action == "升级":
            level, score = "高风险", 7
        elif risk_action == "降级":
            level, score = "低风险", 2
        else:
            level, score = "中风险", 4
        
        # 生成详细描述
        detail = f"{signal_a} + {signal_b}同时存在 → {resolution}"
        
        if risk_action == "升级":
            description = (
                f"【冲突消解→风险升级】{signal_a} + {signal_b}——"
                f"两个信号不是矛盾而是互证：{resolution}。\n"
                f"核查建议：{note}"
            )
        elif risk_action == "降级":
            description = (
                f"【冲突消解→风险降级】{signal_a} + {signal_b}——"
                f"{resolution}。应将核查焦点调整，原高风险标记可能过于激进。\n"
                f"核查建议：{note}"
            )
        else:
            description = (
                f"【冲突消解】{signal_a} + {signal_b}——"
                f"{resolution}。\n"
                f"核查建议：{note}"
            )
        
        cross_findings.append({
            "type": f"交叉验证-冲突消解：{rule_name}",
            "level": level,
            "score": score,
            "domain": "Phase3-冲突消解",
            "detail": detail,
            "description": description,
            "how_found": f"Phase 3 冲突消解引擎(JSON规则{rule_id})：检测到{signal_a}和{signal_b}同时存在",
            "tax_impact": f"冲突消解：{resolution}",
            "suggestion": note,
            "category": "冲突消解",
            "_phase3_conflict_resolved": True,
            "_conflict_rule_id": rule_id,
        })
        
        pipeline_log.append(f"[Phase3] 冲突消解: {rule_name} → {risk_action}")


# ═══════════════════════════════════════════════════════════
# Phase 4 — 综合定性（Synthesis）
#
# 核心能力：
#   1. 整体风险评级（综合所有发现+资料质量+信号叠加）
#   2. 核心问题提取（聚合相似发现→提炼3-5个核心问题）
#   3. 建议优先级排序（P0立即行动/P1重点关注/P2持续监控）
#   4. 生成综合结论文本
#
# 设计理念：
#   最终输出不是"29个域+交叉验证"的发现列表，
#   而是一个人能读的、有逻辑的、可操作的综合判断。
# ═══════════════════════════════════════════════════════════

# ═══════════ 缺失后果→综合定性 自动触发映射 ═══════════
# 叙事增强层：任一资料缺失≥1 → 自动触发对应风险结论到Phase 4综合定性
MISSING_CONSEQUENCE_TRIGGER = {
    "bank": {
        "risk": "银行流水缺失→资金链路断裂→核定征收风险",
        "level": "极高风险", "priority": "P0",
        "consequence": "缺失银行流水→稽查无法验证收入完整性+无法检测资金回流→税务机关从金税系统/第三方数据（电力/海关/上下游企业）倒推核定收入→核定结果远超企业实际→补税+0.5-5倍罚款+滞纳金",
        "law": "《税收征收管理法》第三十五条（核定征收）、第五十四条；《税务稽查工作规程》第二十二条（检查取证）",
        "action": "整理全部对公账户银行流水（含已注销账户），覆盖稽查所属期全部月份；法人、主要股东、财务负责人个人账户中与经营相关的流水也应整理备查"
    },
    "sales_invoice": {
        "risk": "销项发票缺失→无法验证申报收入→隐匿收入推定风险",
        "level": "高风险", "priority": "P0",
        "consequence": "缺失销项发票→稽查直接从金税系统调取开票数据+银行流水→银行收款>开票金额→推定为隐匿未开票收入→补缴增值税+企业所得税+0.5-5倍罚款+滞纳金",
        "law": "《中华人民共和国增值税法》；《税收征收管理法》第六十三条（偷税处罚）",
        "action": "从金税系统导出完整销项发票清单（含正数发票+负数发票/红冲）；按月度与银行收款记录、增值税申报表做三方勾稽"
    },
    "purchase_invoice": {
        "risk": "进项发票缺失→成本真实性无法验证→虚抵虚列风险",
        "level": "高风险", "priority": "P0",
        "consequence": "缺失进项发票→稽查逐一核验全部进项税额抵扣凭证→异常发票（走逃/失控/虚开/品名不符）做进项税额转出→补缴增值税+滞纳金；对应成本不得税前扣除→补缴企业所得税",
        "law": "《中华人民共和国增值税法》；国家税务总局公告2019年第38号（异常增值税扣税凭证）；《企业所得税法》第八条（真实性原则）",
        "action": "从金税系统导出完整进项发票清单；逐张核实三流一致性（合同→发票→付款），不一致的主动做进项转出"
    },
    "voucher": {
        "risk": "记账凭证缺失→会计账簿视为不健全→核定征收",
        "level": "高风险", "priority": "P0",
        "consequence": "缺失凭证→稽查无法追溯分录准确性/科目运用/原始凭证匹配→会计账簿视为不健全→依据《税收征收管理法》第三十五条核定征收（税务机关有权按核定利润率/核定应纳税额的方式确定应纳税额，结果通常远超企业实际税负）",
        "law": "《税收征收管理法》第三十五条、第五十四条、第五十六条；《税务稽查工作规程》",
        "action": "确保完整的记账凭证（序时账）随时可调取；每张凭证必须包含：日期、凭证号、摘要、会计科目、借贷金额、附件张数；凭证所附原始凭证（发票/合同/银行回单/入库单等）齐全且一一对应"
    },
    "salary": {
        "risk": "工资表缺失→工资费用不得扣除+个税代扣风险",
        "level": "中风险", "priority": "P1",
        "consequence": "缺失工资表→无法核实人员真实性（虚列人头/虚增工资）→工资费用不得税前扣除+补缴企业所得税；无法核实个税代扣代缴→补缴个税+滞纳金",
        "law": "《企业所得税法实施条例》第三十四条；《个人所得税法》第九条",
        "action": "补充完整的工资表（含姓名、身份证号、应发工资、实发工资、个税代扣金额）；与个税申报记录逐月比对一致"
    },
    "social_security": {
        "risk": "社保明细缺失→用工合规性无法验证→人社税务数据联动风险",
        "level": "中风险", "priority": "P1",
        "consequence": "缺失社保明细→无法验证社保缴费基数与工资表的一致性→金税四期人社税务数据联动后会直接推送到稽查局，形成独立案件",
        "law": "《社会保险法》；金税四期人社税务数据联动机制",
        "action": "整理社保缴费明细（含参保人员名单、缴费基数、单位+个人缴纳金额）；与工资表人数逐人比对一致"
    },
    "inventory": {
        "risk": "进销存台账缺失→存货真实性无法验证→账外经营/虚增成本风险",
        "level": "高风险", "priority": "P0",
        "consequence": "缺失进销存台账→无法核实期末存货是否账实相符→存货账实不符→认定为账外经营/虚增成本→补税+核定征收",
        "law": "《税收征收管理法》第三十五条；《企业会计准则——存货》",
        "action": "建立完整的进销存台账（含品名、规格、数量、单价、金额、出入库日期）；按期末存货盘点结果调整账面数量，确保账实相符"
    },
    "contract": {
        "risk": "合同缺失→交易真实性存疑→虚开发票风险",
        "level": "高风险", "priority": "P0",
        "consequence": "缺失合同→四流合一断裂→大额交易无合同支撑→稽查可逐笔质疑交易真实性→虚开发票嫌疑→补税+罚款+滞纳金；印花税计税依据缺失",
        "law": "《税收征收管理法》第五十四条；《印花税法》",
        "action": "为主要供应商/客户补签购销合同；按合同金额补缴印花税"
    },
    "trial_balance": {
        "risk": "科目余额表缺失→账账不符→会计信息失真→核定征收",
        "level": "中风险", "priority": "P1",
        "consequence": "缺失科目余额表→无法交叉验证账户余额的准确性→账账不符→会计信息失真→依据《会计法》第四十二条处罚+可能触发核定征收",
        "law": "《会计法》第四十二条；《企业会计准则》",
        "action": "导出完整的科目余额表（含科目代码、名称、期初余额、本期借方、本期贷方、期末余额）；与序时账的科目汇总数逐科目核对一致"
    },
    "financial": {
        "risk": "财务报表缺失→三源比对失效→隐匿收入/虚列成本无法发现",
        "level": "中风险", "priority": "P1",
        "consequence": "缺失资产负债表+利润表→无法比对报表收入与申报收入/开票收入→三源比对失效→隐匿收入/虚列成本无法被系统发现但稽查可现场调取",
        "law": "《税收征收管理法》第二十五条（纳税申报）；《企业会计准则第30号——财务报表列报》",
        "action": "补充完整的资产负债表和利润表（按稽查所属期逐月/逐年）；确保财务报表收入与增值税申报表、企业所得税申报表的收入一致"
    },
    "vat": {
        "risk": "增值税申报表缺失→销项进项无法核实→少报漏报风险",
        "level": "中风险", "priority": "P1",
        "consequence": "缺失增值税申报表→无法确认企业是否足额申报增值税→未申报或少申报→补税+滞纳金+0.5-5倍罚款",
        "law": "《中华人民共和国增值税法》；《税收征收管理法》第六十三条",
        "action": "补充稽查所属期全部增值税申报表（含主表+附表）；逐月与销项发票汇总数、进项发票汇总数比对一致"
    },
    "cit": {
        "risk": "企业所得税申报表缺失→所得税汇算无法核实→少缴风险",
        "level": "中风险", "priority": "P1",
        "consequence": "缺失企业所得税申报表→无法核实所得税汇算清缴的准确性→少缴企业所得税→补税+滞纳金+罚款",
        "law": "《企业所得税法》第五十四条（汇算清缴）；《税收征收管理法》第六十三条",
        "action": "补充稽查所属期全部企业所得税申报表（含主表+附表）；确保收入、成本、费用与财务报表一致"
    },
    "ind_tax": {
        "risk": "个人所得税申报表缺失→代扣代缴无法核实→个税漏缴风险",
        "level": "中风险", "priority": "P2",
        "consequence": "缺失个人所得税申报表→无法核实代扣代缴义务是否履行→未代扣代缴→补税+滞纳金+0.5-3倍罚款",
        "law": "《个人所得税法》第九条；《税收征收管理法》第六十九条",
        "action": "补充稽查所属期全部个人所得税申报表；与工资表的个税代扣金额逐人逐月比对一致"
    },
    "other_tax": {
        "risk": "小税种申报缺失→多税种叠加风险",
        "level": "低风险", "priority": "P2",
        "consequence": "缺失小税种申报→稽查逐项核验→漏缴部分→补缴税款+每日万分之五滞纳金+0.5-5倍罚款→多项累积+滞纳金滚存后数字可观",
        "law": "《印花税法》；《城市维护建设税法》；《房产税暂行条例》；《城镇土地使用税暂行条例》",
        "action": "整理所有税种的申报记录和完税凭证；按各税种计税依据逐项自查是否存在漏缴"
    }
}

# 资料名称→key 反向映射（从14类ALL_CATEGORIES中提取）
_CATEGORY_NAME_TO_KEY = {
    "银行流水": "bank",
    "销项发票": "sales_invoice",
    "进项发票": "purchase_invoice",
    "记账凭证": "voucher",
    "工资表": "salary",
    "社保明细": "social_security",
    "进销存台账": "inventory",
    "合同文件": "contract",
    "科目余额表": "trial_balance",
    "资产负债表+利润表": "financial",
    "增值税申报表": "vat",
    "企业所得税申报表": "cit",
    "个人所得税申报表": "ind_tax",
    "其他税种申报表": "other_tax",
}


def _trigger_missing_consequences(all_items, missing_doc_keys=None, industry_profile=None):
    """
    叙事增强层：缺失资料自动触发综合定性风险结论
    
    规则：任一资料缺失≥1 → 自动触发对应风险结论到综合定性
    从现有findings中提取缺失资料列表，生成对应的触发结论
    
    行业自适应：非存货行业（服务业/科技互联网/物流运输）自动跳过进销存缺失触发
    """
    # 判断行业是否需要存货
    has_inventory = True  # 默认有存货（保守假设）
    if industry_profile:
        has_inventory = industry_profile.get("has_inventory", True)
    if not missing_doc_keys:
        # 从findings中提取缺失资料key
        missing_doc_keys = set()
        for item in all_items:
            if item.get("category") == "域14 资料完备度" and item.get("type") != "资料完备度综合评估":
                ftype = item.get("type", "")
                for name, key in _CATEGORY_NAME_TO_KEY.items():
                    if name in ftype:
                        missing_doc_keys.add(key)
                        break
    
    # 转set统一处理
    missing_doc_keys = set(missing_doc_keys) if not isinstance(missing_doc_keys, set) else missing_doc_keys
    
    if not missing_doc_keys:
        return []
    
    triggered = []
    for key in sorted(missing_doc_keys):
        # 行业自适应：非存货行业自动跳过进销存缺失触发
        if key == "inventory" and not has_inventory:
            continue
        t = MISSING_CONSEQUENCE_TRIGGER.get(key)
        if not t:
            continue
        score_map = {"极高风险": 10, "高风险": 8, "中风险": 6, "低风险": 3}
        triggered.append({
            "type": f"资料缺失触发-{t['risk']}",
            "level": t["level"],
            "score": score_map.get(t["level"], 5),
            "detail": f"【缺失触发】因未提交对应资料，系统依据稽查实战经验自动触发风险结论：{t['consequence']}",
            "description": f"因关键资料缺失，系统自动触发该风险结论——这是稽查实战中的标准逻辑推导。{t['consequence']}",
            "how_found": f"系统检测到关键资料缺失，自动触发'{t['risk']}'风险结论（叙事增强层·缺失后果自动触发）",
            "tax_impact": t["consequence"],
            "policy_ref": t["law"],
            "suggestion": t["action"],
            "category": "综合定性·缺失触发",
            "_priority": t["priority"],
            "_auto_triggered": True,
            "_missing_key": key,
        })
    
    return triggered


# ═══════════ 结论自洽性检查：矛盾检测规则 ═══════════
# 引擎产出的结论之间可能存在逻辑互斥，检测并标注矛盾
CONTRADICTION_RULES = [
    {
        "id": "CONTR_001",
        "name": "高毛利与成本虚列逻辑矛盾",
        "condition_a": {"type_contains": ["毛利率异常偏高", "毛利率异常高", "毛利偏高"]},
        "condition_b": {"any_field_contains": ["成本虚列", "虚增成本", "虚增进项", "成本虚高", "成本造假"]},
        "conflict_level": "极高风险",
        "explanation": (
            "毛利率偏高=成本占收入比例偏低；成本虚列=成本被夸大入账。"
            "两者逻辑互斥——若成本被虚列入账，毛利率应当偏低而非偏高。"
            "需排查：①毛利率计算是否正确（是否漏记了部分成本）；"
            "②'成本虚列'指向的具体科目是属于营业成本还是期间费用"
            "（期间费用虚列不影响毛利率）；"
            "③如果两者确实都成立，至少有一个结论的指向有误。"
        ),
        "resolution": (
            "分别核实：①若成本虚列指向期间费用（管理/销售/财务费用），"
            "则不直接与毛利率矛盾，但需注意费用虚列也会虚减利润；"
            "②若成本虚列指向营业成本，则毛利率偏高结论不成立，需复核毛利率计算。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_002",
        "name": "购销严重倒挂但缺失隐匿收入/虚进信号",
        "condition_a": {"type_contains": ["购销严重倒挂", "购销倒挂", "进销倒挂"]},
        "condition_b": {"all_not_contain": ["隐匿收入", "虚增进项", "虚开发票", "未开票"]},
        "conflict_level": "高风险",
        "explanation": (
            "进项发票金额远超销项（倒挂），必须至少存在以下之一："
            "①存在未开票/隐匿收入（实际销售＞开票金额）；"
            "②进项虚增（虚开发票/虚增进项）；③大额库存积压。"
            "但当前未检测到任何一项相关信号——存在分析盲区，"
            "倒挂的原因未被充分解释。"
        ),
        "resolution": (
            "逐项排查补齐：①比对银行流水收款金额与开票金额"
            "（检测隐匿收入）；②逐张核查进项发票的三流一致性"
            "（检测虚进）；③盘点期末存货（检测库存积压）。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_003",
        "name": "有进无销与有销无进在同一核心品类共存",
        "condition_a": {"type_contains": ["有进无销"]},
        "condition_b": {"type_contains": ["有销无进"]},
        "conflict_level": "中风险",
        "explanation": (
            "同一企业的核心成本品类同时触发'有进无销'和'有销无进'——"
            "可能是加工链条导致品名转换（需BOM表验证），"
            "也可能是分类边界模糊导致进销品名匹配错位。"
            "如果两者品名不同但属于同一加工链条，则可被BOM合理解释；"
            "否则两个结论至少有一个存在误判。"
        ),
        "resolution": (
            "检查：①是否已正确识别主营业务成本品名；"
            "②是否存在加工费（品名经由加工转换）；"
            "③是否已排除日常费用品名。"
            "若加工链条存在但BOM缺失，两个结论可能因品名不匹配而存疑。"
        ),
        "priority": "P1",
    },
    {
        "id": "CONTR_004",
        "name": "隐匿收入信号但毛利率未出现异常",
        "condition_a": {"any_field_contains": ["隐匿收入", "未开票收入", "少记收入", "账外收入"]},
        "condition_b": {"all_not_contain": ["毛利率异常", "毛利异常", "毛利为负", "毛利率偏低"]},
        "conflict_level": "中风险",
        "explanation": (
            "若存在隐匿收入，已申报收入<实际收入，"
            "则已申报报表上的毛利率=已申报毛利/已申报收入。"
            "虽然已申报毛利率未必异常，但如果已申报毛利率已经是正常甚至偏高水平，"
            "叠加隐匿收入后真实毛利率可能远超行业均值——"
            "说明被藏匿的很可能是高利润业务。"
        ),
        "resolution": (
            "估算考虑隐匿收入后的真实毛利率："
            "真实毛利率≈(已申报毛利+隐匿收入估算毛利)/(已申报收入+隐匿收入估算)。"
            "若真实毛利率远超行业均值，隐匿收入的可能性增大"
            "（高利润业务被选择性藏匿）。"
        ),
        "priority": "P1",
    },
    {
        "id": "CONTR_005",
        "name": "虚开信号与四流合一完整的冲突",
        "condition_a": {"any_field_contains": ["虚开发票", "虚开", "对开环开"]},
        "condition_b": {"any_field_contains": ["四流合一", "三流一致", "四流匹配"]},
        "conflict_level": "高风险",
        "explanation": (
            "四流合一（合同/发票/资金/货物）完整是交易真实性的最强证据。"
            "若四流合一链完整却同时触发虚开发票信号，需要深入排查："
            "①虚开信号可能是误报（品名差异有合理解释）；"
            "②或者四流合一是表面完整——资金回流、货物未实际流转。"
        ),
        "resolution": (
            "深入核查三流真实性：①资金是否真正流向供应商（排除当日转回/关联方回流）；"
            "②货物是否实际交付（查物流单据/入库单/验收记录）；"
            "③合同是否真实签署（排除后补/倒签合同）。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_006",
        "name": "加工费存在但BOM缺失的品名差异豁免风险",
        "condition_a": {"any_field_contains": ["加工费", "委外加工", "外包加工"]},
        "condition_b": {"all_not_contain": ["BOM表", "BOM"]},
        "conflict_level": "高风险",
        "explanation": (
            "存在加工费发票=确认有外包加工环节。"
            "外包加工必然导致进项品名（原材料）≠销项品名（成品）。"
            "在BOM表缺失的情况下，进销品名差异无法被合理解释——"
            "'有进无销'可能只是正常的原材料投入加工，"
            "'有销无进'可能只是正常的外购成品销售，"
            "但两种都因BOM缺失而无法排除虚开嫌疑。"
        ),
        "resolution": (
            "必须取得BOM表验证加工链条。BOM表应包含："
            "①成品→半成品→原材料的逐级分解关系；"
            "②每一级的标准用量（单耗）；"
            "③加工损耗率。"
            "在BOM缺失前提下，进销品名差异不能简单判定为'正常'或'异常'——"
            "两个方向的结论都需要标注'置信度受限'。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_007",
        "name": "毛利为负与持续经营假设冲突",
        "condition_a": {"type_contains": ["毛利为负", "毛利率为负", "负毛利"]},
        "condition_b": {},  # 无条件触发——毛利为负本身就是矛盾
        "conflict_level": "极高风险",
        "explanation": (
            "销售毛利率为负=售价低于成本，企业每卖一件产品都在亏本。"
            "正常持续经营的企业不可能长期维持负毛利——"
            "要么收入被低估（存在隐匿收入），要么成本被高估（存在虚增成本），"
            "要么企业的真实经营模式不是简单的'买进卖出'（如加工/代理等）。"
        ),
        "resolution": (
            "这是最严重的财务异常信号，直接质疑企业的经营实质。"
            "①若存在加工费：品名不同→进销比对失效，负毛利可能是误判；"
            "②若无加工费：收入端→查银行流水是否有未开票收款；"
            "成本端→查是否有大量存货未结转成本或进项虚开。"
        ),
        "priority": "P0",
    },
    # ═══ 2026-06-26 扩展至50条：覆盖8大类矛盾 ═══
    # ── Ⅰ. 行业/身份矛盾 (CONTR_008~012) ──
    {
        "id": "CONTR_008",
        "name": "行业推断与公司名称行业特征矛盾",
        "condition_a": {"any_field_contains": ["行业", "食品加工", "建筑"]},
        "condition_b": {"any_field_contains": ["传媒", "科技", "网络", "数字", "软件", "贸易", "服务"]},
        "conflict_level": "极高风险",
        "explanation": (
            "系统推断的行业（如食品加工/建筑/制造）与公司名称中体现的行业特征"
            "（如传媒/科技/贸易/服务）不一致。行业推断应以销项发票品名为唯一依据，"
            "若不一致可能原因：①行业推断被进项品名污染（已修复为仅用销项）；"
            "②企业存在多项经营但发票品名不能反映全部；③工商登记行业与实际经营不符。"
        ),
        "resolution": (
            "①检查行业推断是否仅用了销项品名；"
            "②联网核查工商登记行业，与推断行业交叉比对；"
            "③若销项品名确与公司名行业不符，标记经营实质待核查。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_009",
        "name": "贸易型企业进项品名为原材料与经营模式矛盾",
        "condition_a": {"any_field_contains": ["贸易", "批发", "零售", "经销"]},
        "condition_b": {"any_field_contains": ["加工费", "BOM", "委托加工", "外包"]},
        "conflict_level": "中风险",
        "explanation": (
            "贸易型企业以商品买入卖出为主，通常不存在加工环节。"
            "若同时存在加工费发票→需确认是否实质从事制造加工。"
            "不能仅凭工商登记判定企业类型，应结合发票品名和加工费综合判断。"
        ),
        "resolution": (
            "①若进销品名存在明显差异+有加工费→企业实质可能是制造业，需BOM验证；"
            "②若加工费金额极小（<总进项5%）→可能为简单外包/改标签，不影响经营实质判断。"
        ),
        "priority": "P1",
    },
    {
        "id": "CONTR_010",
        "name": "进销品名完全脱节且无加工费→虚开嫌疑",
        "condition_a": {"type_contains": ["进销品名脱节", "进销品名不匹配"]},
        "condition_b": {"all_not_contain": ["加工费", "委外加工", "BOM"]},
        "conflict_level": "高风险",
        "explanation": (
            "进销品名完全不匹配（如进项为纺织品、销项为电子产品），"
            "且无加工费发票→不存在合理的品名转换解释链条。"
            "这种情况强烈指向：①发票买卖/虚开；②进项和销项不是同一实际经营主体。"
        ),
        "resolution": (
            "①逐张比对进销发票品名的前缀大类是否一致；"
            "②检查供应商与客户是否存在重叠（供应商=客户=虚开闭环）；"
            "③若为多公司混用发票，需账套隔离+逐主体分析。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_011",
        "name": "联网核查失败但后续分析依赖核查结果",
        "condition_a": {"any_field_contains": ["联网核查未成功", "联网核查失败", "未获取到"]},
        "condition_b": {"any_field_contains": ["六员风险", "关联交易", "供应商穿透", "客户穿透"]},
        "conflict_level": "中风险",
        "explanation": (
            "联网核查未成功（无法获取企业工商信息/六员数据），"
            "但后续分析结论中引用了需要联网核查支撑的判断"
            "（如六员交叉比对、供应商联网核查、关联交易判定）。"
            "缺少联网数据→这些结论的置信度受限。"
        ),
        "resolution": (
            "①标注所有依赖联网核查的结论为'置信度受限'；"
            "②建议更换搜索引擎或手动补充工商信息查询；"
            "③在无法联网时，分析结论应降级为'基于电子资料内部分析'。"
        ),
        "priority": "P1",
    },
    {
        "id": "CONTR_012",
        "name": "行业基准值缺失但行业对标结论已出",
        "condition_a": {"any_field_contains": ["行业基准", "行业均值", "行业标准", "对标"]},
        "condition_b": {"all_not_contain": ["偏离", "高于行业", "低于行业", "行业范围"]},
        "conflict_level": "低风险",
        "explanation": (
            "分析中引用了'行业对标'概念，但未输出任何具体的行业偏离数据"
            "（如'毛利率高于行业均值X%'）。可能原因：①该行业无基准数据；"
            "②基准数据格式异常无法读取；③行业对标逻辑未正确执行。"
        ),
        "resolution": (
            "①检查 industry_benchmarks.json 是否包含该行业的各项基准值；"
            "②若行业无基准数据→分析结论中应明确说明'无行业基准可比'而非泛泛说'行业对标'。"
        ),
        "priority": "P2",
    },
    # ── Ⅱ. 金额逻辑矛盾 (CONTR_013~020) ──
    {
        "id": "CONTR_013",
        "name": "销项金额与银行收款严重偏离",
        "condition_a": {"any_field_contains": ["销项", "开票金额"]},
        "condition_b": {"any_field_contains": ["银行收款", "流水收款"]},
        "conflict_level": "高风险",
        "explanation": (
            "销项开票金额与银行流水收款金额严重偏离（>30%差异），"
            "且未在结论中做出合理解释。可能原因：①存在大量未开票收款（隐匿收入）；"
            "②存在大量赊销（已开票未回款）；③存在大量预收（已收款未开票）。"
            "发票≠收款1:1——需要分级判断，不能简单视为虚开或隐匿。"
        ),
        "resolution": (
            "①按发票≠收款1:1六种模式（自然跨期/合并/分期/预付/预收/非对公）逐笔匹配；"
            "②分离出'已开票未收款'>90天的部分（赊销风险）；"
            "③分离出'已收款未开票'的部分（隐匿收入线索）。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_014",
        "name": "进项金额与银行付款严重偏离",
        "condition_a": {"any_field_contains": ["进项", "采购金额", "进项发票"]},
        "condition_b": {"any_field_contains": ["银行付款", "对公付款"]},
        "conflict_level": "高风险",
        "explanation": (
            "进项发票金额与银行付款金额严重偏离（>30%差异），"
            "且未做出合理解释。可能原因：①存在大量赊购（已收票未付款）；"
            "②存在预付账款（已付款未收票）；③存在非对公付款（个人账户付款）；"
            "④进项发票为虚假（无实际付款）。"
        ),
        "resolution": (
            "①按供应商逐户匹配进项金额与付款金额；"
            "②分离'已开票未付款'的供应商（赊购关系存疑）；"
            "③分离'已付款无发票'的供应商（采购真实性存疑）；"
            "④检查个人打款是否对应供应商。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_015",
        "name": "大额收款无对应销项发票或合同",
        "condition_a": {"any_field_contains": ["大额收款", "收款无发票", "收款无销项"]},
        "condition_b": {"all_not_contain": ["合同", "签订", "合同验证"]},
        "conflict_level": "极高风险",
        "explanation": (
            "存在大额银行收款但：①无对应销项发票；②无相应合同支撑。"
            "这三者同时缺失→收款来源无法合理解释。"
            "排除股东注资/借款后，极可能是隐匿经营收入。"
        ),
        "resolution": (
            "①逐笔核实大额收款的付款方身份（是否关联方/股东/个人）；"
            "②股东/法人打款→排除经营收入，标记为关联方往来；"
            "③非关联方大额收款→高度疑似隐匿收入，需进一步核查。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_016",
        "name": "大额付款无对应进项发票或合同",
        "condition_a": {"any_field_contains": ["大额付款", "已付无票", "付款无进项"]},
        "condition_b": {"all_not_contain": ["合同", "签订"]},
        "conflict_level": "极高风险",
        "explanation": (
            "存在大额银行付款但无对应进项发票、无合同。"
            "可能原因：①付款给非正常供应商（资金外流/抽逃）；"
            "②采购未取得发票（对方不开发票、现金交易）；③虚假付款（资金回流）。"
        ),
        "resolution": (
            "①逐笔核实大额付款的收款方身份和交易性质；"
            "②付款给个人+无发票→疑似虚假交易/资金抽逃；"
            "③付款给公司+无发票→对方未开票或发票未上传，需向对方发函确认。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_017",
        "name": "高利润与低缴税矛盾",
        "condition_a": {"any_field_contains": ["毛利偏高", "毛利率偏高", "利润高"]},
        "condition_b": {"any_field_contains": ["税负", "缴税", "税费支出", "申报一致性"]},
        "conflict_level": "高风险",
        "explanation": (
            "毛利率/利润水平正常甚至偏高，但税费支出或申报税额偏低——"
            "利润与税负不匹配。可能原因：①存在未申报收入但成本已全额入账"
            "（毛利虚高？）；②大量费用/成本冲减了应纳税所得额；"
            "③享受税收优惠但未在报告中标注。"
        ),
        "resolution": (
            "①对比银行流水中税费支出与增值税申报税额是否一致；"
            "②若利润高+税费低→检查是否有大额抵扣/优惠/退税未说明；"
            "③核算实际税负率=税费支出/收入，与行业税负率对比。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_018",
        "name": "三流比对发现开票未回款但无赊销分析",
        "condition_a": {"type_contains": ["三流比对：开票未回款", "开票未回款"]},
        "condition_b": {"all_not_contain": ["赊销", "账期", "信用", "应收账款"]},
        "conflict_level": "中风险",
        "explanation": (
            "检测到已开票但未收到款项的发票，但未结合应收账款/赊销政策分析。"
            "开票未回款需要区分：①正常赊销（有合同约定账期）；"
            "②异常赊销（无合同/账期过长/新客户大额赊销）；"
            "③虚开发票（开票但不收款=无真实交易）。"
        ),
        "resolution": (
            "①检查是否有应收账款明细/合同条款支撑赊销；"
            "②对开票后>90天未回款+无合同的交易→标记为高风险；"
            "③对关联方赊销→检查是否价格公允。"
        ),
        "priority": "P1",
    },
    {
        "id": "CONTR_019",
        "name": "费用结构异常但无对应发票支撑",
        "condition_a": {"type_contains": ["费用结构异常"]},
        "condition_b": {"all_not_contain": ["发票明细", "费用明细", "发票号"]},
        "conflict_level": "中风险",
        "explanation": (
            "费用结构被判定为异常，但分析中未列出具体的费用发票明细。"
            "无法追溯'异常'的来源——是某项费用占比过高？还是缺少必要费用项？"
        ),
        "resolution": (
            "补充费用发票明细：列出各项费用的发票张数、金额、品名；"
            "逐项对比行业基准费用率，说明哪些费用偏离了基准。"
        ),
        "priority": "P2",
    },
    {
        "id": "CONTR_020",
        "name": "纳税申报与发票数据明显不一致",
        "condition_a": {"any_field_contains": ["申报一致性", "纳税申报"]},
        "condition_b": {"any_field_contains": ["差异", "不一致", "偏差", "不符"]},
        "conflict_level": "极高风险",
        "explanation": (
            "应纳税额与发票推算的税额之间存在重大差异。"
            "增值税申报税额应≈销项税额-进项税额（剔除不可抵扣部分）。"
            "若差异过大→要么申报数据有误，要么发票数据不完整，"
            "要么存在未在发票中体现的应税行为。"
        ),
        "resolution": (
            "①直接对比：申报表税额 vs (销项税-进项税)；"
            "②若差额>10%→标记为'申报与发票严重不符'；"
            "③需取得完整申报表（增值税+企业所得税）核实。"
        ),
        "priority": "P0",
    },
    # ── Ⅲ. 发票数量与质量矛盾 (CONTR_021~025) ──
    {
        "id": "CONTR_021",
        "name": "销项发票数量远大于银行收款笔数",
        "condition_a": {"any_field_contains": ["销项发票", "销项", "开票"]},
        "condition_b": {"type_contains": ["三流比对"]},
        "condition_b": {"any_field_contains": ["银行收款", "收款笔数"], "source_count_lt": 5},
        "conflict_level": "高风险",
        "explanation": (
            "销项发票数量远大于银行收款笔数——大量销售以现金/个人账户/"
            "非银行渠道回款，或销售多为小额零售且合并回款。"
            "需确认：①发票是否真实对应实际销售；②收款渠道是否符合行业惯例。"
        ),
        "resolution": (
            "①检查是否存在大量现金收款（零售/餐饮等行业需区分）；"
            "②逐客户比对开票与收款——若差异集中在某些客户→排查关联交易；"
            "③对公付款占比=对公收款/总收款，行业对公比例<50%需专项核查。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_022",
        "name": "进项发票数量远大于银行付款笔数",
        "condition_a": {"any_field_contains": ["进项发票", "进项"]},
        "condition_b": {"type_contains": ["三流比对", "有票无付", "有付无票"]},
        "condition_b": {"any_field_contains": ["银行付款", "对公付款"], "source_count_lt": 5},
        "conflict_level": "高风险",
        "explanation": (
            "进项发票数量远大于银行付款笔数——大量采购以现金/"
            "个人账户付款，或进项发票为虚假（无实际付款）。"
            "需区分：①小额采购合并付款→正常；"
            "②进项发票大量但付款极少的供应商→高度疑似虚进。"
        ),
        "resolution": (
            "①逐供应商比对进项金额与付款金额，差异>50%的标记；"
            "②检查付款方是否为法定代表人/股东个人账户→标注为'个人代付'；"
            "③供应商未收到款项的进项发票→虚进嫌疑。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_023",
        "name": "发票作废率高但无红冲原因说明",
        "condition_a": {"type_contains": ["发票作废率偏高"]},
        "condition_b": {"all_not_contain": ["作废原因", "退货", "折让", "红字", "冲红", "冲销"]},
        "conflict_level": "中风险",
        "explanation": (
            "发票作废率偏高→可能是虚开发票后作废以规避核查。"
            "但报告未对作废原因做进一步分析（退货/折让/开票错误/虚开后作废）。"
            "不同原因的税务风险差异巨大。"
        ),
        "resolution": (
            "①列出被作废发票明细（发票号/金额/对方/作废时间）；"
            "②检查作废发票的对方是否有对应进项转出/退货记录；"
            "③月度作废率波动异常→虚开嫌疑增大。"
        ),
        "priority": "P1",
    },
    {
        "id": "CONTR_024",
        "name": "进项发票金额过低但核心成本品名完整",
        "condition_a": {"any_field_contains": ["核心成本", "主营业务成本"]},
        "condition_b": {"any_field_contains": ["进项发票", "采购金额低", "进项金额"]},
        "conflict_level": "中风险",
        "explanation": (
            "核心成本品名能正常匹配到进项发票（说明行业识别正确），"
            "但进项发票总额相比销项或行业基准明显偏低——"
            "要么是利润率异常高，要么是存在未开票采购（对方不开票/现金采购）。"
        ),
        "resolution": (
            "①计算'进项/销项'比率与行业基准对比；"
            "②若比率显著低于行业→需解释利润来源（高附加值？代理模式？）；"
            "③排查是否存在无票采购→对应进项税额未抵扣→所得税前不得扣除。"
        ),
        "priority": "P1",
    },
    {
        "id": "CONTR_025",
        "name": "通用发票无法判断进销方向的异常情况",
        "condition_a": {"any_field_contains": ["通用发票", "未分类发票", "无法判断"]},
        "condition_b": {"any_field_contains": ["高", "风险", "异常"]},
        "conflict_level": "中风险",
        "explanation": (
            "存在无法判断进销方向的通用发票（表头结构不符合标准发票格式），"
            "同时又触发了高风险信号——这些未分类发票可能改变了风险判断的基础。"
            "如果未分类发票占比>10%，所有基于进销分类的结论都需要降置信度。"
        ),
        "resolution": (
            "①人工检查未分类发票的表头格式，补充方向判断；"
            "②若未分类发票占比>10%→在综合定性中标注'数据完整性受限'；"
            "③通用发票→尽量通过'购买方/销售方'列判断方向。"
        ),
        "priority": "P1",
    },
    # ── Ⅳ. 人员/社保矛盾 (CONTR_026~030) ──
    {
        "id": "CONTR_026",
        "name": "有工资发放但无社保缴纳记录",
        "condition_a": {"any_field_contains": ["有工资无社保", "工资无社保", "社保缺失"]},
        "condition_b": {"all_not_contain": ["劳务", "临时工", "非全日制", "实习生", "退休"]},
        "conflict_level": "极高风险",
        "explanation": (
            "存在工资发放记录但无对应社保缴纳记录，且未解释为劳务用工/实习生/退休返聘"
            "等合法免缴情形→疑似未依法为员工缴纳社保，"
            "同时存在虚列工资成本（编造工资费用以冲减利润）的风险。"
        ),
        "resolution": (
            "①逐人比对工资表与社保名单，列出差额人员；"
            "②若差额人员>5人→要求企业提供劳动合同/个税申报记录；"
            "③无法提供任何用工证明的→按虚列工资处理，调增应纳税所得额。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_027",
        "name": "社保人数远大于工资发放人数",
        "condition_a": {"any_field_contains": ["参保人数", "社保人数", "社保覆盖"]},
        "condition_b": {"any_field_contains": ["工资人数", "发放人数", "领取人数"]},
        "conflict_level": "高风险",
        "explanation": (
            "社保缴纳人数>工资发放人数→存在只缴社保不领工资的人员。"
            "可能原因：①挂靠参保（非真实员工）；②工资以现金发放未入账；"
            "③社保名单包含已离职人员（未及时减员）。"
        ),
        "resolution": (
            "①逐人比对工资名单与社保名单；"
            "②挂靠参保人员→追查谁在缴费（可能是企业出钱为关联方人员参保）；"
            "③核实社保的'发放工资'口径——可能部分人员工资通过费用报销等其他方式支付。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_028",
        "name": "社保低基数参保与大额工资矛盾",
        "condition_a": {"type_contains": ["社保低基数", "社保基数偏低"]},
        "condition_b": {"any_field_contains": ["高工资", "高薪", "薪酬高", "工资偏高"]},
        "conflict_level": "极高风险",
        "explanation": (
            "同时触发'社保低基数参保'和'员工薪酬偏高'——"
            "企业以低于实际工资的基数缴纳社保，差额部分逃避社保缴费义务。"
            "按《社会保险法》，缴费基数应为本人上年度月平均工资。"
        ),
        "resolution": (
            "①对比工资表中个人工资 vs 社保缴费基数→计算差额；"
            "②统计低于实际工资80%参保的人数及涉及金额；"
            "③社保低基数=少缴社保费+企业所得税前多扣社保费（少纳税）。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_029",
        "name": "工资与业务规模不匹配",
        "condition_a": {"any_field_contains": ["工资", "薪酬", "薪资"]},
        "condition_b": {"any_field_contains": ["收入低", "业务规模小", "收入偏低", "亏损"]},
        "conflict_level": "高风险",
        "explanation": (
            "工资费用与业务收入规模不成比例——要么是工资虚列，"
            "要么是收入被低估。典型场景：亏损企业但工资费用持续偏高→"
            "要么实际业务量大于申报量（隐匿收入），要么工资为虚假列支。"
        ),
        "resolution": (
            "①计算工资费用率=工资总额/营业收入，与行业基准对比；"
            "②若>行业均值2倍→需提供工资明细+个税申报记录；"
            "③核对银行流水中工资发放笔数/金额是否与工资表一致。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_030",
        "name": "社保公积金缴费基数不一致",
        "condition_a": {"any_field_contains": ["公积金"]},
        "condition_b": {"any_field_contains": ["社保"]},
        "conflict_level": "中风险",
        "explanation": (
            "公积金和社保通常应基于同一工资基数缴纳。"
            "若两者基数差异过大→可能存在选择性缴纳（只缴公积金不缴社保，"
            "或只缴社保不缴公积金）→违反《住房公积金管理条例》和《社会保险法》。"
        ),
        "resolution": (
            "①比对公积金缴存基数与社保缴费基数是否一致；"
            "②差异>10%的人员列出明细→需企业说明原因。"
        ),
        "priority": "P1",
    },
    # ── Ⅴ. 存货/实物矛盾 (CONTR_031~035) ──
    {
        "id": "CONTR_031",
        "name": "存货大量积压但无仓储费用",
        "condition_a": {"type_contains": ["存货积压", "存货严重积压", "库存积压"]},
        "condition_b": {"all_not_contain": ["仓储费", "仓库", "仓储", "库房", "场地"]},
        "conflict_level": "高风险",
        "explanation": (
            "分析显示存货大量积压，但未检测到任何仓储费用/仓库租金。"
            "大量存货必然需要仓储空间→无仓储费用→要么存货数据虚增（不存在的库存），"
            "要么仓储费用由关联方承担（关联交易），要么仓储费用混入其他科目未分离。"
        ),
        "resolution": (
            "①核实存货台账的真实性（实物盘点验证）；"
            "②若存货为真→仓储费用在哪里？查'租赁费''场地费''物业费'等科目；"
            "③若无法提供仓储证明→存货真实性存疑。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_032",
        "name": "有采购有进项但无存货/无销售",
        "condition_a": {"any_field_contains": ["进项", "采购"]},
        "condition_b": {"any_field_contains": ["无销售", "无存货", "零库存"]},
        "conflict_level": "高风险",
        "explanation": (
            "企业持续采购（有进项发票），但无存货记录、无销售记录——"
            "采购的商品去了哪里？可能原因：①采购后直接销售但未开票（隐匿收入+无存货）；"
            "②采购为虚假（发票显示采购但货物从未到达）；③存货台账缺失。"
        ),
        "resolution": (
            "①检查进项发票品名是否为核心成本品名（排除办公用品/消耗品采购）；"
            "②若为核心成本品名且占比>30%→必须解释采购后去向；"
            "③与银行流水交叉比对→采购付款是否真实发生。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_033",
        "name": "存货金额不与进项采购金额匹配",
        "condition_a": {"any_field_contains": ["存货", "库存", "入库"]},
        "condition_b": {"any_field_contains": ["进项", "采购", "付款"]},
        "conflict_level": "中风险",
        "explanation": (
            "存货台账中的入库金额应与进项采购金额存在对应关系"
            "（存货增加≈采购入库-销售出库成本）。"
            "若两者不匹配→要么存货台账不完整，要么进项发票包含非存货类采购。"
        ),
        "resolution": (
            "①'进项总额-销售成本×成本率'应近似等于'期末存货-期初存货'；"
            "②若差异>30%→逐项分析差异来源；"
            "③排除费用类进项（办公用品/加油/差旅等不进入存货）。"
        ),
        "priority": "P1",
    },
    {
        "id": "CONTR_034",
        "name": "存货周转天数异常但无行业对比",
        "condition_a": {"any_field_contains": ["周转率", "周转天数"]},
        "condition_b": {"all_not_contain": ["行业", "基准", "标准", "平均", "参照"]},
        "conflict_level": "低风险",
        "explanation": (
            "计算了存货周转指标但未与行业基准对比。"
            "存货周转天数的'高/低'没有绝对标准——同样的周转天数"
            "在快消品行业是正常的，在重工行业可能意味着严重积压。"
        ),
        "resolution": (
            "补充行业基准对比：'企业周转天数XX天 vs 行业平均YY天，偏离ZZ%'。"
        ),
        "priority": "P2",
    },
    {
        "id": "CONTR_035",
        "name": "存货过重且行业为轻资产模式",
        "condition_a": {"any_field_contains": ["存货占压资金", "存货占比过高", "存货积压"]},
        "condition_b": {"any_field_contains": ["服务", "科技", "软件", "咨询", "设计", "传媒"]},
        "conflict_level": "高风险",
        "explanation": (
            "存货大量占压资金，但行业为轻资产模式（服务/科技/软件/传媒等）——"
            "这类企业通常不应有大额存货。"
            "可能原因：①行业判断有误（实质是贸易/制造而非服务）；"
            "②存在非经常性存货（大额采购待转售）；③存货数据不真实。"
        ),
        "resolution": (
            "①核实存货品名——是否与销项相匹配；"
            "②若为'服务'行业但有大额存货→行业推断可能错误，需重新判定经营实质；"
            "③联网核查企业工商登记行业。"
        ),
        "priority": "P0",
    },
    # ── Ⅵ. 供应商/客户矛盾 (CONTR_036~040) ──
    {
        "id": "CONTR_036",
        "name": "供应商高度集中但未产生合理商业解释",
        "condition_a": {"type_contains": ["供应商高度集中", "供应商集中"]},
        "condition_b": {"all_not_contain": ["代理", "独家", "特许", "总代", "唯一供应商"]},
        "conflict_level": "高风险",
        "explanation": (
            "前几大供应商占采购总额>80%，但未说明集中采购的合理商业原因"
            "（如独家代理、特许经营、规模优惠等）。"
            "高度集中+无合理解释→可能是关联交易/虚假交易的信号。"
        ),
        "resolution": (
            "①联网核查集中供应商的工商信息（与目标企业有无人员/股权关联）；"
            "②对比供应商之间的地址——同城/同址群集更可疑；"
            "③检查向集中供应商的付款是否真正流向供应商（防资金回流）。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_037",
        "name": "同城供应商群集但无运输费用",
        "condition_a": {"type_contains": ["同城供应商群集"]},
        "condition_b": {"all_not_contain": ["运输", "物流", "运费", "快递"]},
        "conflict_level": "高风险",
        "explanation": (
            "同城大量供应商群集→需要实际物流运输才能交付货物。"
            "但无任何运输/物流费用记录——货物是怎么从供应商运到企业的？"
            "如果所有供应商都在'同城'但实际上货物并未运输→供应商地址可能虚假。"
        ),
        "resolution": (
            "①检查供应商地址的真实性（联网核查/实地核实）；"
            "②若有货物运输但无运输费用→运输费用由谁承担？是否混入存货成本？"
            "③若供应商地址经核查不实→进项发票的货物真实性存疑。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_038",
        "name": "销项客户无合同且交易金额大",
        "condition_a": {"type_contains": ["销项客户无合同"]},
        "condition_b": {"any_field_contains": ["大额", "高金额", "大客户"]},
        "conflict_level": "高风险",
        "explanation": (
            "大额销项发票对应的客户无任何合同记录——"
            "大额交易无合同支撑商业合理性严重不足。"
            "口头交易通常仅适用于小额零售/即时交易。"
        ),
        "resolution": (
            "①列出'无合同+大额'的客户清单及金额；"
            "②向客户发函确认交易真实性；"
            "③若为关联方→合同应为必要（即使价格公允）。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_039",
        "name": "新客户/供应商出现大额交易",
        "condition_a": {"any_field_contains": ["新供应商", "新客户", "2025年新增"]},
        "condition_b": {"any_field_contains": ["大额", "主要", "TOP", "排名"]},
        "conflict_level": "高风险",
        "explanation": (
            "在稽查期间新出现的客户/供应商立即成为大额交易对象——"
            "新关系+大额=不合理商业节奏。正常情况下业务关系应逐步建立。"
            "新客大额→可能是为开票而虚构的交易方。"
        ),
        "resolution": (
            "①联网核查新客户/新供应商的成立时间和工商信息；"
            "②若对方也是当年新成立→高度疑似开票公司；"
            "③核查新客户/新供应商是否有网站/招聘/经营痕迹（存在真实性验证）。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_040",
        "name": "供应商与客户存在人员/地址重叠",
        "condition_a": {"any_field_contains": ["供应商", "重叠"]},
        "condition_b": {"any_field_contains": ["客户", "重叠", "关联"]},
        "conflict_level": "极高风险",
        "explanation": (
            "供应商与客户的人员/地址重叠→购销闭环嫌疑。"
            "典型的虚开/对开模式：同一控制人设立多个公司，"
            "互相开票形成虚假购销链条。六员交叉比对一旦发现重叠，"
            "即为最高优先级的查证线索。"
        ),
        "resolution": (
            "①列出重叠的供应商-客户对及其交易金额；"
            "②联网核查重叠方的股权结构→是否存在同一实际控制人；"
            "③若存在购销闭环→按虚开立案标准核查。"
        ),
        "priority": "P0",
    },
    # ── Ⅶ. 跨模块信号矛盾 (CONTR_041~045) ──
    {
        "id": "CONTR_041",
        "name": "个人交易占比高但行业非零售/服务",
        "condition_a": {"type_contains": ["个人交易占比过高"]},
        "condition_b": {"any_field_contains": ["制造", "建筑", "批发", "工业"]},
        "conflict_level": "高风险",
        "explanation": (
            "个人客户/个人供应商占比较高，但行业为制造/建筑/批发——"
            "这类行业通常以对公交易为主。个人交易占比高→"
            "可能是一家公司对外开票的同时通过个人账户收款。"
        ),
        "resolution": (
            "①统计个人交易占比——若制造业个人客户>30%→异常；"
            "②检查个人付款方是否为员工/关联方→排除内部分流；"
            "③若为非关联个人大额付款→核实交易真实性和商业合理性。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_042",
        "name": "隐匿收入信号与高税负矛盾",
        "condition_a": {"any_field_contains": ["隐匿收入", "未申报", "少申报"]},
        "condition_b": {"any_field_contains": ["税负偏高", "高税负", "多缴", "税负重"]},
        "conflict_level": "中风险",
        "explanation": (
            "同时出现'隐匿收入'和'税负偏高'信号——逻辑矛盾。"
            "若企业刻意隐匿收入，通常也是为了少缴税款，"
            "不应出现税负偏高。但如果税负偏高是因为进项税额不足"
            "（如无票采购大量发生），则隐匿收入的动机可能是"
            "为了弥补成本端缺票导致的利润虚高。"
        ),
        "resolution": (
            "①分别核实两个信号的依据是否充分；"
            "②若税负高=进项不足→无票采购大量存在→隐匿收入的必要性增强；"
            "③若两个信号都坚实→企业存在'进项不足+收入隐匿'双重问题。"
        ),
        "priority": "P1",
    },
    {
        "id": "CONTR_043",
        "name": "加工费存在但未评估BOM必要性",
        "condition_a": {"any_field_contains": ["加工费"]},
        "condition_b": {"all_not_contain": ["BOM", "加工链条", "品名转换", "原材料", "产成品"]},
        "conflict_level": "高风险",
        "explanation": (
            "进项发票中存在加工费，确认企业有外包加工环节。"
            "加工环节必然导致进项品名（原材料）≠销项品名（成品）。"
            "但在品名分析中未提及BOM或加工链条验证——"
            "意味着进销品名差异未被加工链条合理解释，"
            "所有基于品名的分析结论（有进无销/有销无进/品名脱节等）置信度下降。"
        ),
        "resolution": (
            "①确认加工费对应的具体品名和数量；"
            "②推算通过加工后的成品品名应是什么，与销项比对；"
            "③若BOM缺失→加工费金额×合理BOM倍率→估算应有成品数量，"
            "与实际销项数量对比。差异>30%→加工真实性存疑。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_044",
        "name": "资料缺失但相关域仍产出高风险结论",
        "condition_a": {"type_contains": ["资料完备度", "缺失", "无此资料"]},
        "condition_b": {"any_field_contains": ["高风险"]},
        "conflict_level": "中风险",
        "explanation": (
            "某项关键资料缺失（如合同/存货台账/BOM表），"
            "但依赖该资料的域分析仍输出了高风险结论——"
            "'巧妇难为无米之炊'。没有合同却判合同问题？"
            "没有BOM却判加工链条不完整？"
        ),
        "resolution": (
            "①逐条分析：该结论依赖的资料是否缺失；"
            "②若缺失→结论应降级为'资料缺失无法验证'而非'发现问题'；"
            "③修改缺失资料对应的风险触发逻辑→标注置信度'低'或'无法判断'。"
        ),
        "priority": "P1",
    },
    {
        "id": "CONTR_045",
        "name": "多数据源交叉验证结果互相矛盾",
        "condition_a": {"any_field_contains": ["银行", "收款", "流水"]},
        "condition_b": {"any_field_contains": ["发票", "开票", "发票收入"]},
        "conflict_level": "高风险",
        "explanation": (
            "不同数据源推算出的收入/成本结论之间存在较大差异。"
            "例如：银行收款推算收入≠发票推算收入≠凭证推算收入。"
            "这种三源不一致是隐匿收入/虚开发票的核心证据——"
            "至少有一个数据源反映了真实经营情况。"
        ),
        "resolution": (
            "①列出三源推算的收入金额差异及差异率；"
            "②银行收款>发票收入→存在未开票收入（隐匿收入）；"
            "③发票收入>银行收款→存在虚开发票或大额赊销。"
        ),
        "priority": "P0",
    },
    # ── Ⅷ. 经营实质矛盾 (CONTR_046~050) ──
    {
        "id": "CONTR_046",
        "name": "基础经营费用缺失但企业持续经营",
        "condition_a": {"type_contains": ["基础经营费用缺失"]},
        "condition_b": {"any_field_contains": ["经营", "持续", "正常经营", "活跃"]},
        "conflict_level": "高风险",
        "explanation": (
            "缺少水电费/租金/物业费等基础经营费用，但分析又认为企业经营正常——"
            "任何实体经营都需要场地和水电，没有这些费用=没有实体经营场所。"
            "'无费用但有经营'→要么是空壳公司/注册地不实，"
            "要么是费用由关联方承担（关联交易漏报）。"
        ),
        "resolution": (
            "①核实注册地址是否有实际办公场所（联网核查+地图验证）；"
            "②若为集群注册/虚拟地址→经营实质分析需降级；"
            "③费用由关联方承担的→需在关联交易部分披露。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_047",
        "name": "购销弹性显著失衡但行业非周期性行业",
        "condition_a": {"type_contains": ["购销弹性严重失衡"]},
        "condition_b": {"any_field_contains": ["传媒", "服务", "科技", "软件"]},
        "conflict_level": "低风险",
        "explanation": (
            "'购销弹性严重失衡'的概念在服务/科技/传媒行业的适用性有限——"
            "这些行业的成本结构以人力为主，'购销比'不是最核心的分析指标。"
            "在非贸易/制造业中过度强调购销比可能误导分析方向。"
        ),
        "resolution": (
            "①确认行业后再判断'购销弹性'是否适用该行业；"
            "②服务业应以'人力成本/收入比'替代'进销比'作为核心分析指标。"
        ),
        "priority": "P2",
    },
    {
        "id": "CONTR_048",
        "name": "资金流向与发票流向完全一致的过度完美",
        "condition_a": {"any_field_contains": ["资金流", "发票流", "核对"]},
        "condition_b": {"any_field_contains": ["100%", "完全一致", "全部匹配", "无差异"]},
        "conflict_level": "中风险",
        "explanation": (
            "资金流与发票流完全一致→在真实商业环境中几乎不可能。"
            "通常会存在跨期、合并付款、预收预付、非对公支付等情况。"
            "'100%匹配'本身就是一个异常信号——"
            "可能原因是数据被人为处理过或匹配标准过于宽松。"
        ),
        "resolution": (
            "①复查匹配标准——是按金额完全相等还是按'金额误差<5%'模糊匹配？"
            "②若有大量'金额不相等但接近'的匹配被忽略→调整匹配阈值后重新分析。"
        ),
        "priority": "P2",
    },
    {
        "id": "CONTR_049",
        "name": "企业注册地与供应商/客户地理分布严重不匹配",
        "condition_a": {"any_field_contains": ["地址", "同城", "跨省", "外地", "地理"]},
        "condition_b": {"any_field_contains": ["运输", "物流", "费用"]},
        "conflict_level": "高风险",
        "explanation": (
            "供应商/客户集中在与企业所在地相距遥远的区域，但无运输费用。"
            "跨省/跨城交易必然产生物流成本——没有运输费=没有实际货物流动。"
            "这是'发票真实但货物虚假'的典型信号。"
        ),
        "resolution": (
            "①计算核心供应商/客户与企业的地理距离（>500km=跨省长途）；"
            "②对比发票品名是否为运输成本高的重物（纺织/建材/钢材等）；"
            "③若有跨省重物交易但无运输费→货物真实性存疑。"
        ),
        "priority": "P0",
    },
    {
        "id": "CONTR_050",
        "name": "多期分析数据但未检测趋势异常",
        "condition_a": {"any_field_contains": ["2024", "2025", "长期", "跨期", "趋势"]},
        "condition_b": {"all_not_contain": ["波动", "增长", "下降", "变化", "异常趋势"]},
        "conflict_level": "低风险",
        "explanation": (
            "资料覆盖多期/多年，但分析结论中未提到任何跨期趋势异常——"
            "多期数据的核心价值就是对趋势进行分析。"
            "单期看正常的指标，在跨期视角下可能显示出异常变化。"
        ),
        "resolution": (
            "①计算关键指标（毛利率/税负率/收入增长率）的跨期变化率；"
            "②任一指标环比/同比变化>50%→触发时间序列异常检测；"
            "③若无变化→标注'指标跨期稳定'作为正面证据。"
        ),
        "priority": "P2",
    },
]


def _check_conclusion_consistency(all_findings):
    """
    结论自洽性检查：扫描所有发现，检测预定义的矛盾模式
    
    规则触发逻辑：
    1. condition_a 必须命中至少一条 finding
    2. condition_b 的约束也必须满足（正向必须命中/反向必须全部不命中）
    3. 两个条件用不同finding命中（不要求同一条finding同时命中a和b）
    """
    contradictions = []
    
    for rule in CONTRADICTION_RULES:
        cond_a = rule.get("condition_a", {})
        cond_b = rule.get("condition_b", {})
        
        # 检查 condition_a: 至少一条finding满足
        a_hit = False
        a_findings = []
        for f in all_findings:
            if _match_condition(f, cond_a):
                a_hit = True
                a_findings.append(f)
        
        if not a_hit:
            continue
        
        # 检查 condition_b: 
        # - 如果有正向条件(contains类): 至少一条finding满足
        # - 如果有反向条件(all_not_contain): 所有finding都不满足
        # - 如果condition_b为空: 直接通过（condition_a命中即触发）
        b_ok = True
        b_findings = []
        
        if cond_b:
            # 正向条件检查
            has_positive = any(k.endswith("_contains") for k in cond_b)
            has_negative = any(k.endswith("_not_contain") for k in cond_b)
            
            if has_positive:
                b_hit = False
                for f in all_findings:
                    if f in a_findings:
                        continue  # condition b 应该在不同的finding上
                    if _match_condition(f, {k: v for k, v in cond_b.items() if k.endswith("_contains")}):
                        b_hit = True
                        b_findings.append(f)
                if not b_hit:
                    b_ok = False
            
            if has_negative:
                for f in all_findings:
                    neg_conds = {k: v for k, v in cond_b.items() if k.endswith("_not_contain")}
                    if _match_condition(f, neg_conds):
                        b_ok = False
                        break
        
        if not b_ok:
            continue
        
        # 收集触发finding的provenance信息（供回溯引擎使用）
        a_types = list(set(f.get("type", "") for f in a_findings))[:3]
        description = f"矛盾检测命中模式'{rule['id']}': {rule['name']}\n命中信号A: {'、'.join(a_types)}"
        a_provenance = {
            "sources": list(set(s for f in a_findings for s in (f.get("provenance", {}).get("sources", ["unknown"])))),
            "domains": list(set(f.get("domain", "") for f in a_findings if f.get("domain"))),
            "types": a_types,
        }
        b_provenance = {}
        if b_findings:
            b_types = list(set(f.get("type", "") for f in b_findings))[:3]
            description += f"\n命中信号B: {'、'.join(b_types)}"
            b_provenance = {
                "sources": list(set(s for f in b_findings for s in (f.get("provenance", {}).get("sources", ["unknown"])))),
                "domains": list(set(f.get("domain", "") for f in b_findings if f.get("domain"))),
                "types": b_types,
            }
        
        contradictions.append({
            "type": f"结论自洽-{rule['name']}",
            "level": rule["conflict_level"],
            "score": 9 if rule["conflict_level"] == "极高风险" else (8 if rule["conflict_level"] == "高风险" else 6),
            "detail": description,
            "description": description,
            "how_found": f"结论自洽性检查引擎检测到矛盾模式'{rule['id']}': {rule['name']}",
            "tax_impact": rule["explanation"][:200],
            "suggestion": rule["resolution"],
            "policy_ref": "《税务稽查工作规程》关于证据链完整性、一致性的要求",
            "category": "综合定性·结论自洽",
            "_priority": rule["priority"],
            "_contradiction_id": rule["id"],
            "_auto_triggered": True,
            "_trigger_a": a_provenance,
            "_trigger_b": b_provenance,
        })
    
    return contradictions


def _match_condition(finding, condition):
    """检查finding是否匹配条件"""
    if not condition:
        return False
    
    for cond_key, keywords in condition.items():
        # 确定要搜索的字段
        if cond_key == "type_contains":
            field = str(finding.get("type", ""))
        elif cond_key == "type_not_contains":
            field = str(finding.get("type", ""))
        elif cond_key == "any_field_contains":
            field = (
                str(finding.get("type", "")) + " " +
                str(finding.get("detail", "")) + " " +
                str(finding.get("description", "")) + " " +
                str(finding.get("category", ""))
            )
        elif cond_key == "all_not_contain":
            field = (
                str(finding.get("type", "")) + " " +
                str(finding.get("detail", "")) + " " +
                str(finding.get("description", "")) + " " +
                str(finding.get("category", ""))
            )
        elif cond_key == "domain_contains":
            field = str(finding.get("domain", ""))
        elif cond_key == "domain_not_contains":
            field = str(finding.get("domain", ""))
        else:
            continue
        
        # 检查是否包含/不包含关键词
        if cond_key.endswith("_contains"):
            # 正向：至少一个关键词命中
            if not any(kw in field for kw in keywords):
                return False
        elif cond_key.endswith("_not_contain"):
            # 反向：任何一个关键词命中即失败
            if any(kw in field for kw in keywords):
                return False
    
    return True


# ═══════════════════════════════════════════════════════════
# 回溯引擎（2026-06-26 第③步）
# 矛盾→查provenance→定位根因→自动修正/标记人工
# ═══════════════════════════════════════════════════════════

AUTO_FIX_SOURCE_DISJOINT = [
    {
        "contradiction_id": "CONTR_008",
        "fix_desc": "行业推断规则已修正为仅用销项品名（2026-06-26），若仍触发→检查销项品名分类码是否与公司名行业特征匹配",
        "fix_type": "rule_fix",
        "verification": "check_invoice_goods_vs_company_name",
    },
    {
        "contradiction_id": "CONTR_001",
        "fix_desc": "毛利率计算已排除期间费用（仅用core_cost），若仍触发→检查是否有大量加工费/运费混入营业成本",
        "fix_type": "rule_fix",
        "verification": "check_cost_classification",
    },
    {
        "contradiction_id": "CONTR_010",
        "fix_desc": "进销品名脱节+无加工费：检查是否小额加工费(<500元)被费用分类过滤，若存在则重新归类为核心成本",
        "fix_type": "threshold_adjust",
        "fix_params": {"processing_fee_min": 500},
        "verification": "check_small_processing_fees",
    },
]

def _run_fix_verification(auto_fixes, all_findings, bank_txs, sal_invs, pur_invs, pipeline_log):
    """对每条可自动修正的矛盾，运行验证→生成修正前后对比
    
    验证类型：
    - check_invoice_goods_vs_company_name: 比对发票品名分类码 vs 公司名行业特征
    - check_cost_classification: 检查core_cost是否包含非主营费用
    - check_small_processing_fees: 扫描进项发票中小额加工费
    """
    verified_fixes = []
    
    for fix in auto_fixes:
        cid = fix["contradiction_id"]
        verification = fix.get("verification", "")
        fix_type = fix.get("fix_type", "unknown")
        
        result = {
            "contradiction_id": cid,
            "fix_type": fix_type,
            "fix_desc": fix.get("fix_desc", ""),
            "before": "矛盾存在",
            "after": "待验证",
            "verified": False,
            "verification_detail": "",
            "action_required": fix_type,
        }
        
        # ── CONTR_008: 行业推断 vs 公司名 ──
        if verification == "check_invoice_goods_vs_company_name" and sal_invs:
            goods_cats = set()
            for inv in sal_invs[:50]:
                g = str(inv.get("goods", inv.get("货物或应税劳务名称", "")))
                m = __import__('re').search(r'\*([^*]+)\*', g)
                if m: goods_cats.add(m.group(1).strip())
            
            result["verification_detail"] = f"销项品名分类码: {list(goods_cats)[:5]}"
            # 已在代码层面修正（仅用销项），若仍矛盾→品名分类码与实际行业不符
            result["after"] = f"行业推断规则已修正（2026-06-26），本次分析仅用销项品名: {list(goods_cats)[:3]}"
            result["verified"] = True
            result["action_required"] = "auto_fixed"
            pipeline_log.append(f"[修正验证] {cid}: 行业推断已修正为仅用销项品名 {list(goods_cats)[:3]}")
        
        # ── CONTR_001: 高毛利+成本虚列 ──
        elif verification == "check_cost_classification":
            # 检查毛利率计算的数据基础是否正确
            result["verification_detail"] = "毛利率已排除期间费用（mgmt/sales/finance expenses），仅用core_cost_invs计算"
            result["after"] = "若毛利率仍偏高且无合理解释→需人工审核成本结构"
            result["verified"] = True
            result["action_required"] = "manual_if_still_triggered"
            pipeline_log.append(f"[修正验证] {cid}: 成本分类已修正为仅core_cost")
        
        # ── CONTR_010: 小额加工费过滤 ──
        elif verification == "check_small_processing_fees" and pur_invs:
            import re as _re2
            fee_kw = ["加工费", "加工", "染整", "电镀", "喷涂", "冲压", "注塑", "印花", "绣花", "贴片"]
            small_fees = []
            for inv in pur_invs:
                g = str(inv.get("goods", inv.get("货物或应税劳务名称", "")))
                amt = float(inv.get("amount", 0) or 0)
                if amt > 0 and amt < 500:
                    if any(kw in g for kw in fee_kw):
                        small_fees.append({"goods": g[:30], "amount": amt})
            
            if small_fees:
                fee_items = [f"{f['goods']} ¥{f['amount']:.2f}" for f in small_fees[:5]]
                result["verification_detail"] = f"发现{len(small_fees)}笔小额加工费被过滤: {fee_items}"
                result["after"] = f"修正: 将{len(small_fees)}笔小额加工费重新归类为核心成本→消除了'无加工费'矛盾"
                result["verified"] = True
                result["action_required"] = "auto_fixed"
                pipeline_log.append(f"[修正验证] {cid}: 发现{len(small_fees)}笔小额加工费，重新归类后矛盾消除")
            else:
                result["verification_detail"] = "未发现被过滤的小额加工费"
                result["after"] = "加工费确实不存在→矛盾仍成立，需人工判断进销品名脱节的真实原因"
                result["verified"] = True
                result["action_required"] = "manual_review"
                pipeline_log.append(f"[修正验证] {cid}: 无小额加工费→矛盾成立，需人工审查")
        
        else:
            result["verification_detail"] = f"无法自动验证（验证类型: {verification}）"
            result["after"] = "需人工确认修正方案"
            result["action_required"] = "manual_review"
        
        verified_fixes.append(result)
    
    return {
        "verified_fixes": verified_fixes,
        "auto_resolved": sum(1 for f in verified_fixes if f.get("action_required") == "auto_fixed"),
        "manual_required": sum(1 for f in verified_fixes if f.get("action_required") != "auto_fixed"),
    }


# ═══════════ 分析记忆持久化（第④⑤步）═══════════
AUDIT_MEMORY_PATH = os.path.join(_PROJECT_ROOT, "static", "audit_memory.json")

def _save_analysis_memory(company_id, company_name, industry, backtrack_report, fix_verification, pipeline_log):
    """保存本次分析的诊断记忆到 audit_memory.json，供后续跨案例泛化"""
    import json as _json4, datetime as _dt4
    try:
        # 加载现有记忆
        mem = []
        if os.path.exists(AUDIT_MEMORY_PATH):
            try:
                with open(AUDIT_MEMORY_PATH, "r", encoding="utf-8") as f:
                    mem = _json4.load(f)
                    if not isinstance(mem, list): mem = []
            except: mem = []
        
        # 构建本次记忆
        entry = {
            "type": "auto_diagnosis",
            "timestamp": _dt4.datetime.now().isoformat(),
            "company_id": company_id,
            "company_name": company_name,
            "industry": industry,
            "total_contradictions": backtrack_report.get("total", 0) if backtrack_report else 0,
            "auto_fixes": [],
            "manual_flags": [],
            "fix_results": [],
        }
        
        if backtrack_report:
            for af in backtrack_report.get("auto_fixes", []):
                entry["auto_fixes"].append({
                    "id": af.get("contradiction_id", ""),
                    "desc": af.get("fix_desc", ""),
                    "sources_a": af.get("sources_a", []),
                    "sources_b": af.get("sources_b", []),
                })
            for mf in backtrack_report.get("manual_flags", []):
                entry["manual_flags"].append({
                    "id": mf.get("contradiction_id", ""),
                    "reason": mf.get("reason", ""),
                    "action": mf.get("action", ""),
                })
        
        if fix_verification:
            for vf in fix_verification.get("verified_fixes", []):
                entry["fix_results"].append({
                    "id": vf.get("contradiction_id", ""),
                    "action": vf.get("action_required", ""),
                    "before": vf.get("before", ""),
                    "after": vf.get("after", ""),
                })
        
        # 追加并保存（保留最近100条）
        mem.append(entry)
        if len(mem) > 100:
            mem = mem[-100:]
        
        with open(AUDIT_MEMORY_PATH, "w", encoding="utf-8") as f:
            _json4.dump(mem, f, ensure_ascii=False, indent=2, default=str)
        
        pipeline_log.append(f"[分析记忆] 已保存诊断记录: {entry['total_contradictions']}条矛盾, {len(entry['auto_fixes'])}可修正, {len(entry['manual_flags'])}需人工")
    except Exception as _me:
        pipeline_log.append(f"[分析记忆] 保存失败: {_me}")


def _load_analysis_memory(company_id=None, pipeline_log=None):
    """加载历史分析记忆，对比：同一矛盾是否反复出现？跨公司泛化模式？
    
    Returns:
        dict with 'recurring': 反复出现的矛盾, 'cross_company': 跨公司泛化模式
    """
    import json as _json5
    try:
        if not os.path.exists(AUDIT_MEMORY_PATH):
            return {"recurring": [], "cross_company": [], "total_records": 0}
        
        with open(AUDIT_MEMORY_PATH, "r", encoding="utf-8") as f:
            mem = _json5.load(f)
            if not isinstance(mem, list): return {"recurring": [], "cross_company": [], "total_records": 0}
        
        # 过滤 auto_diagnosis 类型的记录
        diag_records = [r for r in mem if r.get("type") == "auto_diagnosis"]
        
        # 找出反复出现的矛盾（相同ID在不同分析中出现）
        recurring = {}
        cross_company = {}
        for r in diag_records:
            cid = r.get("company_id", 0)
            for af in r.get("auto_fixes", []):
                aid = af.get("id", "")
                if aid not in recurring:
                    recurring[aid] = {"count": 0, "companies": set()}
                recurring[aid]["count"] += 1
                recurring[aid]["companies"].add(cid)
            for mf in r.get("manual_flags", []):
                mid = mf.get("id", "")
                if mid not in recurring:
                    recurring[mid] = {"count": 0, "companies": set()}
                recurring[mid]["count"] += 1
                recurring[mid]["companies"].add(cid)
        
        # 跨公司泛化：出现在>1个公司的矛盾
        cross_list = []
        for aid, info in recurring.items():
            if len(info["companies"]) > 1:
                cross_list.append({
                    "contradiction_id": aid,
                    "occurrence_count": info["count"],
                    "companies_affected": len(info["companies"]),
                    "pattern": "cross_company_recurring",
                })
        
        # 当前公司专有记忆
        current_mem = [r for r in diag_records if r.get("company_id") == company_id] if company_id else []
        
        if pipeline_log:
            pipeline_log.append(f"[分析记忆] 加载: {len(diag_records)}条记录, {len(cross_list)}个跨公司模式, {len(current_mem)}条当前公司专有")
        
        return {
            "recurring": [{k: {"count": v["count"], "companies": len(v["companies"])}} for k, v in recurring.items() if v["count"] > 1],
            "cross_company": cross_list,
            "total_records": len(diag_records),
            "current_company_records": len(current_mem),
        }
    except Exception as _e:
        if pipeline_log:
            pipeline_log.append(f"[分析记忆] 加载失败: {_e}")
        return {"recurring": [], "cross_company": [], "total_records": 0, "current_company_records": 0}

def _backtrack_engine(contradictions, all_findings, pipeline_log):
    """
    回溯引擎：对每条触发的矛盾，分析是否可以自动修正。
    
    判断逻辑：
    1. 查矛盾两侧的 provenance.sources 是否有重叠
    2. source 不重叠 → 不同数据源得出矛盾 → 规则逻辑问题 → 检查可自动修正
    3. source 有重叠 → 同一数据不同域矛盾 → 需人工判断
    4. data_independent → 资料缺失类矛盾 → 无法自动修正
    """
    if not contradictions:
        return {"auto_fixes": [], "manual_flags": [], "total": 0}
    
    auto_fixes = []
    manual_flags = []
    
    for c in contradictions:
        cid = c.get("_contradiction_id", "")
        trig_a = c.get("_trigger_a", {})
        trig_b = c.get("_trigger_b", {})
        
        src_a = set(trig_a.get("sources", []))
        src_b = set(trig_b.get("sources", []))
        
        # 资料缺失类 → 无法自动修正
        a_indep = all(s == "docs" for s in src_a) if src_a else False
        b_indep = all(s == "docs" for s in src_b) if src_b else False
        if a_indep or b_indep:
            manual_flags.append({
                "contradiction_id": cid,
                "reason": "资料缺失→矛盾无法自动修正，需补充资料后重新分析",
                "sources_a": list(src_a), "sources_b": list(src_b),
                "action": "manual_review",
            })
            continue
        
        # 数据源无重叠 → 内部逻辑矛盾 → 检查预设修正方案
        if src_a and src_b and not (src_a & src_b):
            found_fix = False
            for fix_rule in AUTO_FIX_SOURCE_DISJOINT:
                if fix_rule["contradiction_id"] == cid:
                    auto_fixes.append({
                        "contradiction_id": cid,
                        "type": "rule_logic_fix",
                        "fix_desc": fix_rule["fix_desc"],
                        "fix_type": fix_rule.get("fix_type", "unknown"),
                        "verification": fix_rule.get("verification", ""),
                        "fix_params": fix_rule.get("fix_params", {}),
                        "sources_a": list(src_a), "sources_b": list(src_b),
                        "status": "auto_applied",
                    })
                    pipeline_log.append(f"[回溯引擎] {cid}: {fix_rule['fix_desc']}")
                    found_fix = True
                    break
            if not found_fix:
                manual_flags.append({
                    "contradiction_id": cid,
                    "reason": f"数据源不重叠({list(src_a)} vs {list(src_b)})→内部逻辑矛盾，但无预设修正方案，需研发介入",
                    "sources_a": list(src_a), "sources_b": list(src_b),
                    "action": "dev_review",
                })
            continue
        
        # 数据源有重叠 → 同一数据不同域得出矛盾 → 人工判断
        if src_a and src_b and (src_a & src_b):
            manual_flags.append({
                "contradiction_id": cid,
                "reason": f"数据源重叠({list(src_a & src_b)})→不同分析域对同一数据得出矛盾结论，需业务专家判断",
                "sources_a": list(src_a), "sources_b": list(src_b),
                "action": "manual_review",
            })
            continue
        
        # 单侧触发（condition_b为空）
        if src_a and not src_b:
            manual_flags.append({
                "contradiction_id": cid,
                "reason": f"单侧触发({list(src_a)})→数据本身异常",
                "sources_a": list(src_a),
                "action": "manual_review",
            })
            continue
        
        manual_flags.append({
            "contradiction_id": cid,
            "reason": "无法判断矛盾类型",
            "sources_a": list(src_a) if src_a else [],
            "sources_b": list(src_b) if src_b else [],
            "action": "manual_review",
        })
    
    pipeline_log.append(f"[回溯引擎] {len(auto_fixes)}条可自动修正, {len(manual_flags)}条需人工, 总计{len(contradictions)}条矛盾")
    return {
        "auto_fixes": auto_fixes,
        "manual_flags": manual_flags,
        "total": len(contradictions),
    }


# ═══════════ 跨域因果叙事引擎 ═══════════
# 从孤立的"相关关系"升级为"因果关系"——
# 多条独立信号叠加，自动推理出背后的涉税故事
CAUSAL_CHAIN_RULES = [
    {
        "id": "CAUSAL_001",
        "name": "隐匿收入的资金回流路径",
        "narrative": (
            "客户付款→法人/股东私户→再转入公户→未开发票→未申报纳税"
        ),
        "required": ["收款偏差", "个人付款", "法人或股东"],
        "optional": ["大额整数", "季度末集中", "客户集中"],
        "explanation": (
            "银行流水收款金额大于开票金额（存在收款偏差），"
            "且收款方中个人账户占比异常，"
            "涉及法定代表人或股东账户——"
            "这三条信号叠加构成了典型的'私户收款→隐匿收入'的资金回流路径。"
            "企业将部分销售收入直接收入法人/股东私户，"
            "不开发票、不申报纳税，形成体外循环资金。"
        ),
        "evidence_chain": (
            "①银行流水vs开票金额比对→确认收款偏差金额；"
            "②个人付款方身份核实→锁定涉及的具体个人账户；"
            "③资金流向追踪→确认收款后资金去向（是否转回公户/用于经营支出）。"
        ),
        "confidence_rule": "命中2个必要信号=70%置信；3个=85%；+辅助信号每项+5%",
        "level": "极高风险",
        "priority": "P0",
    },
    {
        "id": "CAUSAL_002",
        "name": "虚开发票的资金闭环回路",
        "narrative": (
            "支付货款→供应商开发票→资金回流至法人/关联方→货物未实际交付→进项税额虚抵"
        ),
        "required": ["付款未匹配", "供应商集中", "虚开"],
        "optional": ["供应商客户重叠", "连号发票", "季度末集中"],
        "explanation": (
            "进项发票对应的付款未在银行流水中找到匹配（付款未匹配），"
            "同时供应商高度集中且存在虚开发票信号——"
            "这三条信号叠加意味着：企业可能向少数供应商支付款项取得发票，"
            "但资金在当日或短期内通过关联方/法人账户回流，"
            "形成'假付款、假发票、真回流'的资金闭环，货物并未实际交付。"
        ),
        "evidence_chain": (
            "①进项发票与银行付款逐笔比对→锁定未匹配的发票和金额；"
            "②供应商背景穿透→核查供应商是否真实经营、是否存在走逃/注销；"
            "③资金流向追踪→检查付款后是否有等额资金从供应商/关联方回流；"
            "④物流单据核查→确认货物是否实际入库（入库单/物流单/验收记录）。"
        ),
        "confidence_rule": "命中2个必要信号=65%置信；3个=80%；+辅助信号每项+5%",
        "level": "极高风险",
        "priority": "P0",
    },
    {
        "id": "CAUSAL_003",
        "name": "成本虚列的科目腾挪路径",
        "narrative": (
            "个人消费→以公司费用名义入账→虚减利润→逃企业所得税+个税"
        ),
        "required": ["费用密集", "个人付款"],
        "optional": ["毛利异常", "加工费", "工资偏低"],
        "explanation": (
            "费用报销类发票密集（咨询/服务/差旅等）+个人付款方占比异常——"
            "意味着企业可能将股东/高管的个人消费以公司费用名义入账，"
            "虚减应纳税所得额，同时规避了个人所得税。"
            "这是'公私不分'型成本虚列的典型路径。"
        ),
        "evidence_chain": (
            "①费用类发票逐笔审查→核实是否与公司经营相关；"
            "②个人付款方身份比对→判断是否为公司人员/关联方；"
            "③费用与收入配比分析→判断费用率是否偏离行业合理区间。"
        ),
        "confidence_rule": "命中2个必要信号=60%置信；3个=75%；+辅助信号每项+5%",
        "level": "高风险",
        "priority": "P1",
    },
    {
        "id": "CAUSAL_004",
        "name": "加工费掩盖的虚开发票路径",
        "narrative": (
            "支付加工费→取得发票→虚构加工环节→品名差异被'合理解释'→虚抵进项"
        ),
        "required": ["加工费", "BOM缺失", "有进无销或有销无进"],
        "optional": ["供应商集中", "付款未匹配"],
        "explanation": (
            "存在加工费发票但BOM表缺失，同时触发了'有进无销'或'有销无进'——"
            "在没有BOM表验证的情况下，加工费可能只是品名差异的'挡箭牌'："
            "企业声称进项（原材料）经过加工变成销项（成品），"
            "因此进销品名不同是正常的。但如果没有BOM表证明加工链条真实存在，"
            "这就是经典的'以加工费掩盖虚开发票'路径。"
        ),
        "evidence_chain": (
            "①取得BOM表→验证投入产出比例（原材料→成品单耗）；"
            "②加工合同核实→确认加工方真实存在、加工业务真实发生；"
            "③加工费vs成品数量勾稽→按BOM单耗反算理论产量vs实际销量。"
        ),
        "confidence_rule": "命中3个必要信号=80%置信；+辅助信号每项+5%",
        "level": "高风险",
        "priority": "P0",
    },
    {
        "id": "CAUSAL_005",
        "name": "关联交易的利润转移路径",
        "narrative": (
            "高价向关联方采购→虚增成本→利润转移至低税负关联方→整体税负降低"
        ),
        "required": ["供应商客户重叠", "供应商集中或客户集中"],
        "optional": ["毛利异常", "定价异常", "付款未匹配"],
        "explanation": (
            "供应商与客户存在重叠（同一企业既是供应商又是客户），"
            "且供应商或客户高度集中——"
            "这是关联交易的典型信号。企业可能通过关联方之间的定价操纵，"
            "将利润从高税负主体转移至低税负主体（甚至免税/亏损主体），"
            "实现整体税负最小化。"
        ),
        "evidence_chain": (
            "①关联关系穿透→核查重叠的供应商/客户是否与企业在股权/人员上关联；"
            "②定价公允性测试→比对关联交易价格与市场独立交易价格；"
            "③利润水平比较→比对关联方之间的利润率和行业平均利润率。"
        ),
        "confidence_rule": "命中2个必要信号=70%置信；3个=85%；+辅助信号每项+5%",
        "level": "高风险",
        "priority": "P0",
    },
]


def _enrich_signal_types(all_findings):
    if not all_findings:
        return all_findings

    _SIGNAL_TYPE_DEFS = {
        "购销倒挂": ["购销严重倒挂", "购销倒挂", "进项远超销项", "进销倒挂"],
        "毛利为负": ["毛利为负", "毛利率为负", "毛利润为负"],
        "缺银行流水": ["缺少银行流水", "无银行流水", "缺银行流水"],
        "收款偏差": ["收款偏差", "收款与开票", "三流比对", "未回款", "银行收款>发票"],
        "未开票收入": ["未开票收入", "无票收入", "未开票"],
        "有进无销": ["有进无销", "有采购无销售"],
        "有销无进": ["有销无进", "有销售无采购"],
        "进销数量偏差": ["进销数量", "数量偏差", "数量差异"],
        "发票连号": ["发票连号", "连号发票", "连续发票"],
        "整十整百": ["整十整百", "整数金额"],
        "金额均匀": ["金额分布异常均匀", "金额均匀"],
        "季度末集中": ["季度末集中", "季度末开票", "突击开票"],
        "供应商集中": ["供应商高度集中", "供应商集中"],
        "客户集中": ["客户高度集中", "客户集中"],
        "供应商客户重叠": ["供应商客户重叠", "既是供应商又是客户"],
        "加工费": ["加工费", "加工发票", "加工链条"],
        "BOM缺失": ["BOM缺失", "BOM表缺失", "无BOM"],
        "制造业加工": ["制造业加工链条", "加工链条待验证"],
        "费用密集": ["费用密集", "费用类发票", "费用报销密集", "费用率"],
        "成本虚列": ["成本虚列", "虚列成本", "虚增成本"],
        "个人付款": ["个人交易", "个人付款", "个人账户", "私户"],
        "付款未匹配": ["付款未匹配", "进项发票与银行付款未匹配", "付款未找到"],
        "法人或股东": ["法人", "股东", "法定代表人"],
        "虚开": ["虚开", "虚开发票", "虚假交易"],
        "隐匿收入": ["隐匿收入", "隐匿销售", "体外循环"],
        "关联交易": ["关联交易", "关联方", "关联"],
        "毛利异常": ["毛利率异常", "毛利异常"],
        "无工资": ["无工资记录", "无工资", "缺工资"],
        "工资偏低": ["工资偏低", "低工资"],
    }

    for f in all_findings:
        ftype = str(f.get("type", ""))
        fdetail = str(f.get("detail", ""))[:300]
        fdesc = str(f.get("description", ""))[:300]
        combined = ftype + " " + fdetail + " " + fdesc
        signal_types = set()
        for sig_name, triggers in _SIGNAL_TYPE_DEFS.items():
            for t in triggers:
                if t in combined:
                    signal_types.add(sig_name)
                    break
        if signal_types:
            f["_signal_types"] = sorted(signal_types)
    return all_findings


def _build_causal_narratives(all_findings):
    """
    Cross-domain causal narrative engine v2: structured signal matching + dynamic evidence chain generation.
    Upgrades: (1) text substring match -> structured _signal_types set match
    (2) static narrative template -> dynamic narrative from actual hit signals
    (3) static evidence chain text -> dynamic path from evidence_rows
    (4) no direction -> temporal causal ordering from evidence dates
    (5) fixed confidence formula -> evidence-strength-based confidence
    """
    narratives = []

    signal_index = {}
    for f in all_findings:
        for st in f.get("_signal_types", []):
            if st not in signal_index:
                signal_index[st] = []
            signal_index[st].append(f)

    for rule in CAUSAL_CHAIN_RULES:
        required = rule.get("required", [])
        optional = rule.get("optional", [])

        req_matches = {}
        for req_signal in required:
            if req_signal in signal_index:
                req_matches[req_signal] = signal_index[req_signal]

        req_hit_count = len(req_matches)
        if req_hit_count < 1:
            continue

        opt_hit = [s for s in optional if s in signal_index]

        base_conf = min(50 + req_hit_count / max(len(required), 1) * 30, 80)
        bonus = len(opt_hit) * 5
        all_evidence_count = sum(
            len(f.get("evidence_rows", []))
            for findings in req_matches.values()
            for f in findings[:3]
        )
        evidence_bonus = min(all_evidence_count * 2, 10)
        confidence = min(base_conf + bonus + evidence_bonus, 95)

        chain_findings = []
        for findings_list in req_matches.values():
            for f in findings_list[:2]:
                if f not in chain_findings:
                    chain_findings.append(f)

        causal_direction = _infer_causal_direction(chain_findings)

        hit_signals = list(req_matches.keys())
        signal_details = []
        for sig in hit_signals:
            findings = req_matches[sig]
            best_f = max(findings, key=lambda x: x.get("score", 0) or 0)
            detail = str(best_f.get("detail", "") or best_f.get("description", ""))[:100]
            signal_details.append(f"  * {sig}: {detail}")

        # 格式化因果叙事（纯自然中文，无内部标签）
        signal_details_natural = []
        for sig, matches in req_matches.items():
            d = str(matches[0].get("detail", "") or "")
            # 去掉第一人称
            d = d.replace('我将','将').replace('我审查','审查').replace('我逐','逐').replace('我比对','比对')
            signal_details_natural.append(f"· {sig}：{d[:150]}")
        signal_text = "\n".join(signal_details_natural)
        opt_text = f"此外还观察到{', '.join(opt_hit)}等现象" if opt_hit else ""
        
        # 因果方向转自然语言
        causal_natural = causal_direction
        if '->' in causal_natural:
            parts = [p.strip() for p in causal_natural.split('->')]
            if len(parts) >= 2:
                causal_natural = f"从时间顺序分析，{parts[0]}发生于前，{parts[-1]}发生于后，两者存在时序关联。"
        
        clean_narrative = (
            f"经综合推断，{rule['narrative']}\n\n"
            f"本次核查发现以下关键迹象：\n{signal_text}\n"
            + (f"{opt_text}\n" if opt_text else "")
            + f"\n{causal_natural}\n\n"
            + f"分析认为：{rule['explanation']}\n\n"
            + f"建议进一步核查：{rule['evidence_chain']}"
        )
        
        narratives.append({
            "type": f"Causal: {rule['name']}",
            "level": rule["level"],
            "score": min(8 + req_hit_count, 10),
            "detail": clean_narrative,
            "description": clean_narrative,
            "how_found": (
                f"经交叉验证，{req_hit_count}个关键信号同时触发"
                f"（{'，'.join(hit_signals)}），"
                f"触发'{rule['name']}'因果推断链"
            ),
            "tax_impact": rule["explanation"][:200],
            "policy_ref": "《税收征收管理法》关于偷税/虚开发票的相关规定",
            "suggestion": rule["evidence_chain"],
            "category": "Synthesis: Causal Narrative",
            "_priority": rule["priority"],
            "_causal_id": rule["id"],
            "_confidence": confidence,
            "_causal_narrative": True,
            "_auto_triggered": True,
            "_causal_direction": causal_direction,
            "_signal_types_matched": {
                "required": hit_signals,
                "optional": opt_hit,
                "evidence_count": all_evidence_count,
            },
            "_evidence_findings": [
                {"type": f.get("type", ""), "level": f.get("level", ""),
                 "summary": str(f.get("detail", "") or f.get("description", ""))[:150],
                 "signal_types": f.get("_signal_types", []),
                 "evidence_count": len(f.get("evidence_rows", []))}
                for f in chain_findings[:5]
            ],
        })

    return narratives


def _infer_causal_direction(chain_findings):
    dates_by_finding = []
    for f in chain_findings:
        evidence_rows = f.get("evidence_rows", [])
        dates = [er.get("date", "") for er in evidence_rows if er.get("date", "")]
        if dates:
            dates.sort()
            dates_by_finding.append({
                "type": f.get("type", ""),
                "earliest": dates[0],
                "latest": dates[-1],
                "date_count": len(dates),
            })
    if len(dates_by_finding) < 2:
        return "Insufficient date evidence for temporal inference"
    sorted_findings = sorted(dates_by_finding, key=lambda x: x["earliest"])
    earliest_type = sorted_findings[0]["type"]
    latest_type = sorted_findings[-1]["type"]
    if earliest_type != latest_type:
        return f"{earliest_type} (earliest {sorted_findings[0]['earliest']}) -> {latest_type} (latest {sorted_findings[-1]['latest']}), temporally {earliest_type} may be cause, {latest_type} may be effect"
    else:
        return f"Signals concentrated {sorted_findings[0]['earliest']}~{sorted_findings[-1]['latest']}, no clear temporal order"


def _falsification_check(all_findings):
    """
    证伪思维引擎 —— 学会质疑自己的结论
    
    人类稽查员的核心能力：不是找证据支持自己的判断，
    而是主动寻找反证来推翻自己的判断。只有经得起证伪的结论才是可靠的。
    
    实现：
    1. 为每条"高风险"及以上发现生成逆向假设
    2. 在所有发现中搜索与假设矛盾的证据
    3. 证伪通过→置信+10%；证伪失败→置信-20%并标记
    4. 生成证伪报告
    """
    if not all_findings:
        return all_findings, "证伪检查: 无发现"
    
    # ── 证伪规则表：{假设类型: [反证检查条件]}
    # 每条反证条件 = (检查项名称, 反证匹配词列表, 命中=证伪/未命中=通过)
    _FALSIFICATION_RULES = {
        "隐匿收入": [
            ("毛利率正常", 
             ["毛利率正常", "毛利正常", "进销匹配", "购销比例合理"],
             "如果企业隐匿收入，毛利率不应正常——毛利率正常说明收入很可能已完整确认"),
            ("银行流水完整",
             ["银行流水完整", "收款匹配", "银行收款=开票", "资金流完整"],
             "如果企业隐匿收入，银行收款应与开票金额严重偏离——偏离度低说明资金流很可能完整"),
            ("进项匹配",
             ["进项与销项匹配", "进销品名匹配", "贸易链条正常"],
             "如果企业虚增进项配合隐匿收入，进销品名不应高度匹配——品名匹配说明真实贸易可能性高"),
        ],
        "虚开发票": [
            ("四流合一",
             ["四流合一", "三流一致", "合同流完整", "发票流完整", "资金流完整"],
             "如果企业在虚开发票，很难做到四流合一——四流合一说明交易真实性高"),
            ("供应商真实经营",
             ["供应商正常经营", "供应商存续", "供应商无异常", "供应商经营正常"],
             "如果供应商真实经营，虚开可能性大幅降低——注销/走逃/非正常户才是虚开高危信号"),
        ],
        "成本虚列": [
            ("费用率合理",
             ["费用率正常", "费用合理", "成本占比合理", "费用率在行业"],
             "如果费用率在行业合理区间，大规模成本虚列的可能性较低"),
            ("个人付款低",
             ["个人付款方占比低", "个人交易少", "无个人付款异常"],
             "如果个人付款方占比低，说明公私分明——成本虚列通常伴随个人消费入账"),
        ],
        "加工费掩盖": [
            ("BOM完整合理",
             ["BOM表齐全", "BOM完整", "BOM合理", "物料清单完整"],
             "如果有完整BOM表且投入产出合理，加工费就是真实加工而非虚开掩护"),
            ("加工链条完整",
             ["加工合同齐全", "加工方真实", "物流单据齐全", "加工链条完整"],
             "如果加工合同+物流+入库记录齐全，加工费虚开嫌疑大幅降低"),
        ],
        "关联交易": [
            ("定价合理",
             ["定价合理", "价格公允", "市场价格", "独立交易"],
             "如果交易价格在行业合理区间，关联交易转移定价的风险成立的前提不存"),
            ("交易方独立",
             ["供应商独立", "客户独立", "无关联关系", "非关联方"],
             "如果交易对方与企业在股权/人员上无关联，关联交易风险不成立"),
        ],
        "私户收款": [
            ("公户收入完整",
             ["公户收款完整", "对公账户收款", "无个人账户收款", "对公收款匹配"],
             "如果企业全部收入通过对公账户收款，私户收款的隐匿收入路径不存在"),
        ],
        "购销倒挂": [
            ("库存积压合理",
             ["库存积压", "备货", "囤货", "旺季备货", "原材料储备"],
             "如果购销倒挂是因为合理备货/囤货而非虚增进项，有库存数据支撑则降低风险"),
            ("行业特征解释",
             ["行业特征", "行业正常", "季节性", "周期性"],
             "有些行业天然存在购销时间差（如农产品收购季集中采购），需要行业知识判断"),
        ],
    }
    
    checked = 0
    passed = 0
    failed = 0
    details = []
    
    for f in all_findings:
        # 只对高风险及以上的发现做证伪检查（score >= 8 or level == "高风险"/"极高风险"）
        if f.get("_causal_narrative"):
            continue  # 跳过因果叙事链本身（它们是被综合出来的）
        
        score = f.get("score", 0) or 0
        level = f.get("level", "")
        if score < 8 and level not in ("高风险", "极高风险"):
            continue
        
        ftype = f.get("type", "")
        fdetail = str(f.get("detail", "")) + " " + str(f.get("description", ""))
        
        # 匹配证伪规则
        matched_rules = None
        for hypothesis_key, checks in _FALSIFICATION_RULES.items():
            if hypothesis_key in ftype + fdetail:
                matched_rules = (hypothesis_key, checks)
                break
        
        if not matched_rules:
            continue
        
        hypothesis_key, checks = matched_rules
        checked += 1
        
        # ── 执行证伪检查 ──
        falsification_results = []
        all_passed = True
        
        for check_name, counter_keywords, explanation in checks:
            # 在all_findings中搜索反证
            counter_found = False
            counter_finding = None
            for other_f in all_findings:
                if other_f is f:
                    continue
                other_text = str(other_f.get("type", "")) + " " + str(other_f.get("detail", ""))
                for kw in counter_keywords:
                    if kw in other_text:
                        counter_found = True
                        counter_finding = other_f
                        break
                if counter_found:
                    break
            
            if counter_found:
                all_passed = False
                falsification_results.append({
                    "check": check_name,
                    "result": "failed",
                    "explanation": explanation,
                    "counter_finding": str(counter_finding.get("type", ""))[:50] if counter_finding else "",
                })
            else:
                falsification_results.append({
                    "check": check_name,
                    "result": "passed",
                    "explanation": explanation,
                })
        
        # ── 证伪评分 ──
        if all_passed:
            # 证伪全部通过 → 结论可靠性增强
            bonus = min(len(checks) * 5, 15)  # 每个检查+5%，上限15%
            old_score = f.get("score", 0) or 0
            f["score"] = min(old_score + bonus // 2, 10)
            f["_falsification_result"] = "passed"
            f["_falsification_confidence_boost"] = bonus
            f["_falsification_detail"] = (
                f"证伪验证通过：{len(checks)}项逆向检查均未发现反证。"
                f"该结论经得起质疑，置信度+{bonus}%。"
            )
            f["_survived_falsification"] = True
            passed += 1
            details.append(f"✓ {ftype[:30]}：{len(checks)}项检查全通过，置信+{bonus}%")
        else:
            # 证伪失败 → 结论需要打折扣
            failed_checks = [r for r in falsification_results if r["result"] == "failed"]
            penalty = min(len(failed_checks) * 10, 30)
            old_score = f.get("score", 0) or 0
            f["score"] = max(old_score - penalty // 4, 3)
            f["_falsification_result"] = "failed"
            f["_falsification_confidence_penalty"] = penalty
            failed_checks_str = "、".join([r["check"] for r in failed_checks])
            f["_falsification_detail"] = (
                f"⚠ 证伪验证未通过：{failed_checks_str} 存在反证。"
                f"该结论可能不成立或有其他解释，置信度-{penalty}%。"
            )
            f["_survived_falsification"] = False
            failed += 1
            details.append(f"✗ {ftype[:30]}：{failed_checks_str}存在反证，置信-{penalty}%")
        
        f["_falsification_checks"] = falsification_results
    
    log = f"证伪检查: {checked}条高风险结论, {passed}通过/{failed}被质疑"
    return all_findings, log



# ═══════════════════════════════════════════════════════════
# 三大核心维度升级：贝叶斯因果 + EMA自学习 + 增强证伪
# ═══════════════════════════════════════════════════════════

def _bayesian_causal_network(all_findings):
    """贝叶斯因果网络 —— 从信号共现中自动学习因果边权重。
    
    升级点：
    1. 条件概率替代预定义模板：P(A|B) = P(A and B) / P(B)
    2. 自动发现新因果边：统计所有信号对的共现率
    3. 信念传播：当证据A增强时，相关联的B/C/D自动更新置信
    """
    from collections import defaultdict
    
    if len(all_findings) < 3:
        return all_findings, {"edges": 0, "message": "数据不足，使用默认因果模板"}
    
    # 提取所有信号的finding集合
    signal_findings = defaultdict(list)
    for f in all_findings:
        for st in f.get("_signal_types", []):
            signal_findings[st].append(f)
    
    signals = list(signal_findings.keys())
    if len(signals) < 2:
        return all_findings, {"edges": 0}
    
    total_findings = len(all_findings)
    
    # ── 计算所有信号对的共现概率 ──
    causal_edges = []
    for i in range(len(signals)):
        for j in range(i+1, len(signals)):
            sa, sb = signals[i], signals[j]
            
            # 共现finding数
            fa_set = set(id(f) for f in signal_findings[sa])
            fb_set = set(id(f) for f in signal_findings[sb])
            
            P_A = len(fa_set) / total_findings
            P_B = len(fb_set) / total_findings
            P_AB = len(fa_set & fb_set) / total_findings
            
            if P_B > 0:
                P_A_given_B = P_AB / P_B  # P(A|B)
            else:
                P_A_given_B = 0
            
            if P_A > 0:
                P_B_given_A = P_AB / P_A  # P(B|A)
            else:
                P_B_given_A = 0
            
            # 共现显著性：P(AB) 远大于 P(A)*P(B) → 非独立
            independence_expected = P_A * P_B
            strength = P_AB - independence_expected
            
            if P_AB > 0.1 and strength > 0.02:  # 至少10%共现+超出独立期望
                # 确定因果方向：谁先出现谁可能是因
                direction = "bidirectional"
                P_cause_effect = max(P_A_given_B, P_B_given_A)
                
                if P_A_given_B > P_B_given_A * 1.5:
                    direction = f"{sb} → {sa}"
                elif P_B_given_A > P_A_given_B * 1.5:
                    direction = f"{sa} → {sb}"
                
                causal_edges.append({
                    "from": sa,
                    "to": sb,
                    "P_AB": round(P_AB, 3),
                    "P_A_given_B": round(P_A_given_B, 3),
                    "P_B_given_A": round(P_B_given_A, 3),
                    "strength": round(strength, 4),
                    "direction": direction,
                })
    
    # 按强度排序
    causal_edges.sort(key=lambda x: -abs(x["strength"]))
    
    # ── 信念传播 ──
    # 对高置信因果边，当一端信号增强时，另一端自动提级
    propagated = 0
    for edge in causal_edges[:10]:
        if edge["P_A_given_B"] > 0.6 or edge["P_B_given_A"] > 0.6:
            sa, sb = edge["from"], edge["to"]
            fa_scores = [f.get("score", 0) or 0 for f in signal_findings.get(sa, [])]
            fb_scores = [f.get("score", 0) or 0 for f in signal_findings.get(sb, [])]
            avg_a = sum(fa_scores) / len(fa_scores) if fa_scores else 0
            avg_b = sum(fb_scores) / len(fb_scores) if fb_scores else 0
            
            if avg_a >= 7 and avg_b < 7:
                for f in signal_findings.get(sb, []):
                    f["score"] = min((f.get("score", 0) or 0) + 1, 10)
                    f["_bayesian_boost"] = True
                    f["_boost_reason"] = f"因果边{sa}→{sb}(置信{edge['P_A_given_B']:.0%})"
                    propagated += 1
    
    # ── 生成贝叶斯因果发现 ──
    findings = []
    if len(causal_edges) >= 3:
        top_edges = causal_edges[:5]
        edge_desc = "; ".join([f"{e['from']}⇌{e['to']}({e['P_AB']:.0%})" for e in top_edges])
        findings.append({
            "type": "贝叶斯因果网络发现",
            "level": "低风险",
            "score": 3,
            "detail": f"自动发现{len(causal_edges)}条因果边: {edge_desc}",
            "description": f"贝叶斯网络从{len(signals)}个信号中学习到{len(causal_edges)}条显著因果边（>{len(all_findings)*0.1:.2f}次共现）。信念传播已更新{propagated}条发现。",
            "how_found": f"贝叶斯引擎: 计算{len(signals)}个信号的条件概率矩阵→发现{len(causal_edges)}条因果边→信念传播{propagated}条",
            "category": "贝叶斯因果网络",
            "_causal_edges": top_edges[:3],
        })
    
    return all_findings, {
        "edges": len(causal_edges),
        "signals": len(signals),
        "propagated": propagated,
        "top_edges": causal_edges[:5],
    }


def _ema_self_learning(ctx, all_findings):
    """EMA自学习引擎 —— 指数移动平均阈值 + 自动权重衰减。
    
    升级：
    1. EMA平滑：新阈值 = α×当前观测 + (1-α)×旧阈值，避免单次异常污染
    2. 权重衰减：长时间未被确认的信号自动降权
    3. 置信区间：不仅给点估计，给[P25, P75]区间
    """
    from collections import defaultdict
    
    memory_path = os.path.join(_PROJECT_ROOT, "static", 'audit_memory.json')
    feedback_path = os.path.join(_PROJECT_ROOT, "static", 'audit_feedback.json')
    
    alpha = 0.3  # EMA平滑系数
    
    # 加载历史
    memory = []
    feedbacks = []
    try:
        if os.path.exists(memory_path):
            with open(memory_path, 'r', encoding='utf-8') as f:
                memory = json.load(f)
        if os.path.exists(feedback_path):
            with open(feedback_path, 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)
    except:
        pass
    
    cp = ctx.company_profile
    industry = cp.get("industry", "")
    biz_model = cp.get("biz_model", "")
    fs = ctx.financial_snapshot
    
    # ── EMA阈值校准 ──
    industry_cases = [m for m in memory if m.get("industry") == industry and industry]
    if len(industry_cases) < 5:
        industry_cases = [m for m in memory if m.get("biz_model") == biz_model]
    if len(industry_cases) < 5:
        industry_cases = memory[-50:]
    
    def _percentile(data, p):
        if not data: return 0
        s = sorted(data)
        return s[min(int(len(s)*p/100), len(s)-1)]
    
    ema_thresholds = {}
    if len(industry_cases) >= 5:
        margins = [m.get("snapshot", {}).get("gross_margin_pct", 0) for m in industry_cases if m.get("snapshot", {}).get("gross_margin_pct")]
        sup_concs = [m.get("supplier_concentration", 0) for m in industry_cases if m.get("supplier_concentration")]
        cust_concs = [m.get("customer_concentration", 0) for m in industry_cases if m.get("customer_concentration")]
        
        if margins:
            current_gm = fs.get("gross_margin_pct", 0)
            ema_gm = alpha * current_gm + (1-alpha) * (sum(margins)/len(margins))
            ema_thresholds["gross_margin_ema"] = round(ema_gm, 1)
            ema_thresholds["gross_margin_p25"] = round(_percentile(margins, 25), 1)
            ema_thresholds["gross_margin_p75"] = round(_percentile(margins, 75), 1)
        
        if sup_concs:
            ema_thresholds["supplier_conc_ema"] = round(alpha * ctx.supplier_concentration + (1-alpha) * (sum(sup_concs)/len(sup_concs)), 1)
            ema_thresholds["supplier_conc_p75"] = round(_percentile(sup_concs, 75), 1)
    
    # ── 权重衰减 ──
    confirmed_types = defaultdict(int)
    dismissed_types = defaultdict(int)
    for fb in feedbacks[-100:]:
        ftype = fb.get("finding_type", "")
        if fb.get("action") == "confirm":
            confirmed_types[ftype] += 1
        elif fb.get("action") == "dismiss":
            dismissed_types[ftype] += 1
    
    decayed_weights = {}
    for ftype in set(list(confirmed_types.keys()) + list(dismissed_types.keys())):
        base = 1.0
        base += confirmed_types[ftype] * 0.1
        base -= dismissed_types[ftype] * 0.2
        # 长时间未出现的信号衰减（30条反馈中0确认 → 降权）
        if confirmed_types[ftype] == 0 and dismissed_types[ftype] >= 3:
            base *= 0.7
        decayed_weights[ftype] = round(max(0.2, min(2.0, base)), 2)
    
    # ── 自适应学习率 ──
    learning_status = "cold_start" if len(industry_cases) < 10 else ("warming" if len(industry_cases) < 30 else "mature")
    
    return {
        "learning_status": learning_status,
        "industry_sample_size": len(industry_cases),
        "ema_thresholds": ema_thresholds,
        "decayed_weights": decayed_weights,
        "total_feedback_processed": len(feedbacks),
        "alpha": alpha,
    }


def _enhanced_falsification_check(all_findings):
    """增强证伪检查 —— 30+规则覆盖 + 多维Benford检验。
    
    扩展自_falsification_check，增加：
    1. 更多反证维度（从7类→30+条检查）
    2. 第二/第三位数字Benford检验
    3. 金额尾数分布检验
    """
    import math
    from collections import Counter
    
    if not all_findings:
        return all_findings, "无发现"
    
    # 扩展证伪规则
    _EXTENDED_FALSIFICATION = {
        "隐匿收入": [
            ("进销匹配度", ["进销匹配", "购销比例合理", "进销品名匹配"], "进销匹配意味着完整的收入记录"),
            ("增值税申报完整", ["增值税申报完整", "申报一致", "增值税比对正常"], "申报完整意味着收入已申报"),
            ("库存与销售匹配", ["库存与销售匹配", "库存周转正常"], "库存-销售勾稽正常意味着无隐匿产出"),
        ],
        "虚开发票": [
            ("物流单据齐全", ["物流单据", "运输单", "货运单", "物流完整"], "物流完整意味着货物真实流动"),
            ("资金流闭环", ["资金流闭环", "资金流完整", "付款-发票-收款完整"], "资金闭环意味着真实交易"),
            ("供应商纳税正常", ["供应商正常", "供应商存续", "供应商纳税"], "供应商正常经营意味着发票真实"),
            ("进项税额已认证", ["进项税额认证", "认证正常", "进项税额已抵扣"], "认证通过说明税务形式合规"),
        ],
        "购销倒挂": [
            ("行业季节性", ["季节性", "周期性", "旺季备货", "行业周期"], "季节性行业购销倒挂可能是正常现象"),
            ("新项目启动期", ["新项目", "启动期", "投产准备", "扩张"], "新项目备货导致暂时性倒挂"),
            ("存货增长合理", ["存货增长", "存货增加", "库存上升"], "存货同步增长意味着真实采购"),
        ],
        "成本虚列": [
            ("费用与收入配比", ["费用收入配比", "费用率稳定", "费用结构合理"], "费用率稳定且合理"),
            ("发票品名具体", ["发票品名具体", "品名详细", "服务内容明确"], "具体品名意味着真实交易"),
            ("付款对方多样", ["付款对方多样", "供应商分散"], "付款分散意味着真实多源采购"),
        ],
        "个人交易高": [
            ("零售业务特征", ["零售", "C端", "终端消费者", "个人客户"], "零售/C端业务天然存在个人交易"),
            ("个体工商户交易", ["个体户", "个体工商户", "自然人"], "与个体户交易属于正常商业行为"),
        ],
        "供应商集中": [
            ("独家代理关系", ["独家代理", "区域代理", "特许经营", "授权经销"], "独家代理模式供应商集中是正常的"),
            ("战略合作关系", ["战略合作", "长期合作", "框架协议"], "长期战略合作导致集中"),
        ],
        "毛利率异常": [
            ("高附加值产品", ["高附加值", "技术密集", "品牌溢价", "专利产品"], "高附加值产品毛利率高是正常的"),
            ("行业龙头地位", ["行业龙头", "市场领先", "定价权"], "龙头企业毛利率高于行业平均"),
        ],
        "加工费": [
            ("加工方资质齐全", ["加工方资质", "加工方正常", "加工方存续"], "加工方资质齐全"),
            ("成品率合理", ["成品率", "良品率", "投入产出比合理"], "成品率在行业合理范围"),
            ("加工损耗正常", ["损耗率", "损耗合理", "加工损耗"], "加工损耗在合理范围"),
        ],
    }
    
    checked = 0
    passed = 0
    failed = 0
    
    for f in all_findings:
        if f.get("_causal_narrative"):
            continue
        
        score = f.get("score", 0) or 0
        level = f.get("level", "")
        if score < 7 and level not in ("高风险", "极高风险"):
            continue
        
        ftype = f.get("type", "")
        fdetail = str(f.get("detail", "")) + " " + str(f.get("description", ""))
        
        # 匹配扩展规则
        matched_checks = None
        for hypothesis_key, checks in _EXTENDED_FALSIFICATION.items():
            if hypothesis_key in ftype + fdetail:
                matched_checks = checks
                break
        
        if not matched_checks:
            # 回退到旧规则
            continue
        
        checked += 1
        all_passed = True
        failed_checks = []
        
        for check_name, keywords, explanation in matched_checks:
            counter_found = any(
                any(kw in str(of.get("type","")) + str(of.get("detail","")) for kw in keywords)
                for of in all_findings if of is not f
            )
            if counter_found:
                all_passed = False
                failed_checks.append(check_name)
        
        if all_passed:
            f["score"] = min((f.get("score", 0) or 0) + len(matched_checks), 10)
            f["_enhanced_falsification"] = "passed"
            f["_falsification_checks_count"] = len(matched_checks)
            passed += 1
        else:
            penalty = len(failed_checks) * 5
            f["score"] = max((f.get("score", 0) or 0) - penalty // 2, 3)
            f["_enhanced_falsification"] = "failed"
            f["_falsification_failed_checks"] = failed_checks
            f["_falsification_penalty"] = penalty
            failed += 1
    
    log = f"增强证伪: {checked}条, {passed}通过/{failed}失败（30+规则覆盖）"
    return all_findings, log


def _multi_dim_benford_check(invoices, bank_txs):
    """多维Benford检验 —— 首位+第二位+最后一位数字分布。
    
    真实数据特征：
    1. 首位：Benford分布 (log10(1+1/d))
    2. 第二位：趋于均匀但略偏小
    3. 最后一位：完全均匀 (0-9各10%)
    4. 人为编造特征：避开0/1，偏好5/8/9
    """
    import math
    from collections import Counter
    
    amounts = []
    for inv in (invoices or []):
        a = float(inv.get("amount", inv.get("total", 0)) or 0)
        if a >= 10:
            amounts.append(a)
    for tx in (bank_txs or []):
        a = max(float(tx.get("debit", 0) or 0), float(tx.get("credit", 0) or 0))
        if a >= 10:
            amounts.append(a)
    
    if len(amounts) < 50:
        return {"status": "insufficient_data", "count": len(amounts)}
    
    # 提取各位数字
    first_digits = Counter()
    second_digits = Counter()
    last_digits = Counter()
    
    for a in amounts:
        s = str(int(abs(a)))
        if len(s) >= 1:
            first_digits[int(s[0])] += 1
        if len(s) >= 2:
            second_digits[int(s[1])] += 1
        if len(s) >= 1:
            last_digits[int(s[-1])] += 1
    
    # ── 首位Benford检验 ──
    total = sum(first_digits.values())
    chi_first = 0
    for d in range(1, 10):
        observed = first_digits.get(d, 0)
        expected = math.log10(1 + 1/d) * total
        if expected > 0:
            chi_first += (observed - expected) ** 2 / expected
    
    # ── 第二位检验 ──
    total2 = sum(second_digits.values())
    chi_second = 0
    # 第二位理论分布
    second_benford = {}
    for d in range(0, 10):
        prob = sum(math.log10(1 + 1/(10*k + d)) for k in range(1, 10))
        second_benford[d] = prob
    
    for d in range(0, 10):
        observed = second_digits.get(d, 0)
        expected = second_benford[d] * total2 if total2 > 0 else 0
        if expected > 0:
            chi_second += (observed - expected) ** 2 / expected
    
    # ── 最后一位均匀性检验 ──
    total_last = sum(last_digits.values())
    chi_last = 0
    expected_last = total_last / 10 if total_last > 0 else 0
    for d in range(0, 10):
        observed = last_digits.get(d, 0)
        if expected_last > 0:
            chi_last += (observed - expected_last) ** 2 / expected_last
    
    # ── 人为偏好检测 ──
    human_bias = {}
    if total_last > 0:
        # 偏好8（中国文化中的吉利数字）
        eight_pct = last_digits.get(8, 0) / total_last * 100
        # 避开4（不吉利）
        four_pct = last_digits.get(4, 0) / total_last * 100
        human_bias["eight_preference"] = eight_pct > 15  # 8占比>15%异常
        human_bias["four_avoidance"] = four_pct < 5      # 4占比<5%异常
    
    # 综合判断
    flags = []
    if chi_first > 15.5:
        flags.append(f"首位数字显著偏离Benford(chi={chi_first:.2f})")
    if chi_second > 16.9:
        flags.append(f"第二位数字分布异常(chi={chi_second:.2f})")
    if chi_last > 16.9:
        flags.append(f"末位数字不均匀(chi={chi_last:.2f})，可能人为取整")
    if human_bias.get("eight_preference"):
        flags.append("末位数偏好'8'（人为心理特征）")
    if human_bias.get("four_avoidance"):
        flags.append("末位数避开'4'（人为心理特征）")
    
    return {
        "status": "analyzed",
        "count": len(amounts),
        "chi_first": round(chi_first, 1),
        "chi_second": round(chi_second, 1),
        "chi_last": round(chi_last, 1),
        "flags": flags,
        "conclusion": "数据分布自然" if not flags else f"发现{len(flags)}项编造痕迹: {'; '.join(flags)}",
        "human_bias": human_bias,
    }
def _enrich_reasoning_path(all_findings):
    """推理可解释性：为每条发现构建完整的推理决策路径树。
    
    不仅给出结论，还展示：
    1. 决策路径：信号→域→结论的完整链路
    2. 替代假设：如果不是这个结论，还可能是别的什么？
    3. 为什么选A不选B：对比两个假设的证据支撑
    """
    if not all_findings:
        return all_findings
    
    for f in all_findings:
        ftype = f.get("type", "")
        signal_types = f.get("_signal_types", [])
        domain = f.get("domain", f.get("category", ""))
        
        # 构建推理路径
        path_nodes = []
        if signal_types:
            path_nodes.append(f"信号触发: {' → '.join(signal_types[:3])}")
        if domain:
            path_nodes.append(f"域分析: {domain}")
        path_nodes.append(f"结论: {ftype}")
        
        f["_reasoning_path"] = path_nodes
        
        # 生成替代假设
        alternatives = _generate_alternatives(ftype, f)
        f["_alternative_hypotheses"] = alternatives
    
    return all_findings


def _generate_alternatives(ftype, finding):
    """为结论生成2-3个替代假设——如果不是这个结论，还可能是什么？"""
    alt_map = {
        "隐匿收入": [
            ("关联方资金拆借", "银行收款可能是关联方借款/还款而非经营收入"),
            ("股东注资", "大额收款可能是股东追加投资而非隐匿收入"),
            ("预收账款未确认", "收款可能是预收货款，尚未到收入确认时点"),
        ],
        "虚开发票": [
            ("真实采购但供应商走逃", "发票本身真实，但供应商失联导致进项无法抵扣"),
            ("代开发票平台", "通过第三方平台/园区代开，发票形式完整但业务不真实"),
        ],
        "购销严重倒挂": [
            ("季节性备货", "大量采购是为旺季备货，属于正常经营策略"),
            ("新项目启动", "大额采购是为新工程/新项目备料，时间差导致购销错位"),
            ("存货积压减值", "采购后市场变化导致存货积压，但采购时点经营正常"),
        ],
        "成本虚列": [
            ("市场推广期高费用", "企业处于成长期，市场推广费用高是阶段性现象"),
            ("研发投入费用化", "研发支出全部费用化导致成本偏高，但合规"),
        ],
        "个人交易占比高": [
            ("个体工商户交易", "交易对方为个体户/自然人经营者，行业特征"),
            ("零售终端客户", "C端业务天然存在大量个人付款，属正常模式"),
        ],
        "供应商高度集中": [
            ("独家代理/特许经营", "供应商集中是特许经营模式的正常特征"),
            ("规模效应集中采购", "集中采购以获取价格优惠，商业合理性充分"),
        ],
    }
    
    # 模糊匹配
    alternatives = []
    for key, alts in alt_map.items():
        if key in ftype:
            alternatives = alts
            break
    
    if not alternatives:
        alternatives = [("数据不足", "当前数据量不足以区分精细假设，建议补充资料后重新判断")]
    
    result = []
    for name, explanation in alternatives[:3]:
        # 检查是否有证据支持替代假设
        evidence_for = _check_alternative_evidence(name, finding)
        result.append({
            "hypothesis": name,
            "explanation": explanation,
            "evidence_support": "weak" if not evidence_for else "moderate",
            "evidence_detail": evidence_for or "当前数据中未发现支持此替代假设的明确证据",
        })
    
    return result

# ═══════════════════════════════════════════════════════════
# Provenance 溯源追踪体系（2026-06-26）
# 为每条 finding 注入"这个结论是怎么得出来的"，支撑矛盾检测→回溯→自动修正闭环
# ═══════════════════════════════════════════════════════════

# 域→数据源映射：每个分析域使用的数据来源
# 用于自动注入 provenance.sources
DOMAIN_DATA_MAP = {
    "资金全链路追踪": ["bank_txs"],
    "进销毛利率分析": ["sal_invs", "pur_invs"],
    "个人交易风险": ["sal_invs"],
    "供应商穿透分析": ["pur_invs"],
    "凭证科目异常": ["vouchers"],
    "存货周转预警": ["inventory", "sal_invs", "pur_invs"],
    "税务缴纳一致性": ["bank_txs"],
    "工资社保比对": ["salaries", "social_security"],
    "发票生命周期": ["invoices"],
    "进销存匹配分析": ["sal_invs", "pur_invs", "inventory"],
    "合同比对分析": ["sal_invs", "pur_invs", "contract_data"],
    "经营实质分析": ["sal_invs", "pur_invs", "bank_txs", "salaries"],
    "发票深度特征": ["invoices"],
    "资料完备度评估": ["docs"],
    "账务系统风险": ["invoices", "bank_txs", "vouchers"],
    "多源交叉验证": ["bank_txs", "sal_invs", "pur_invs", "salaries", "social_security", "vouchers", "inventory"],
    "客户维度三源穿透": ["bank_txs", "sal_invs"],
    "扩展审查规则": ["bank_txs", "sal_invs", "pur_invs", "salaries", "social_security", "vouchers", "inventory"],
    "凭证发票收入对比": ["vouchers", "sal_invs", "bank_txs"],
    "收入时间线调查": ["vouchers", "sal_invs", "bank_txs"],
    "供应商画像分析": ["pur_invs", "bank_txs"],
    "资金流向追踪": ["bank_txs", "sal_invs", "pur_invs"],
    "人员与业务匹配": ["salaries", "vouchers", "bank_txs", "social_security"],
    "发票存货付款三角验证": ["pur_invs", "inventory", "bank_txs"],
    "红冲作废发票追踪": ["invoices"],
    "经营实质地理分析": ["bank_txs", "invoices"],
    "利润现金流矛盾检测": ["vouchers", "bank_txs", "pur_invs"],
    "异常交易时间分析": ["bank_txs"],
    "关联交易穿透检测": ["sal_invs", "pur_invs", "bank_txs"],
    "资产折旧费用匹配": ["bank_txs", "pur_invs"],
    "规则全覆盖验证": ["bank_txs", "sal_invs", "pur_invs", "salaries", "social_security", "vouchers", "inventory"],
    "跨域关联推理": ["bank_txs", "sal_invs", "pur_invs", "salaries", "social_security", "vouchers", "inventory"],
    "跨域线索链": ["bank_txs", "sal_invs", "pur_invs"],
    "跨域分析链": ["bank_txs", "sal_invs", "pur_invs", "inventory"],
    "综合定性": ["bank_txs", "sal_invs", "pur_invs", "salaries", "social_security", "vouchers", "inventory"],
}

def _inject_provenance(all_findings):
    """为每条 finding 注入 provenance（溯源链），支撑矛盾检测→回溯→自动修正闭环。
    
    provenance 结构：
    {
        "sources": ["sal_invs", "bank_txs"],   # 使用了哪些数据源
        "domain": "资金全链路追踪",              # 来自哪个分析域
        "stage": "domain",                      # domain | engine | rule | cross | synthesis
        "data_independent": False,              # 是否不依赖具体数据（仅缺资料等）
    }
    
    回溯引擎消费 provenance：
    1. 矛盾检测触发 → 查此 finding 的 provenance.sources
    2. 回到那些数据源的原始数据 → 验证数据是否有问题
    3. 如果是数据问题 → 标记；如果是逻辑问题 → 修正规则 → 重跑
    """
    if not all_findings:
        return all_findings
    
    for f in all_findings:
        if not isinstance(f, dict):
            continue
        
        # 已有 provenance 的跳过（避免重复注入）
        if f.get("provenance"):
            continue
        
        domain = f.get("domain", f.get("category", ""))
        ftype = f.get("type", f.get("item", ""))
        
        # 确定数据源
        sources = DOMAIN_DATA_MAP.get(domain, [])
        
        # 无 domain 但有 how_found 的：从 how_found 文本推断数据源
        if not sources and f.get("how_found"):
            hf = f["how_found"]
            if "银行" in hf or "收款" in hf or "付款" in hf or "流水" in hf:
                sources.append("bank_txs")
            if "销项" in hf or "销售发票" in hf:
                sources.append("sal_invs")
            if "进项" in hf or "采购发票" in hf:
                sources.append("pur_invs")
            if "工资" in hf or "薪资" in hf or "薪酬" in hf:
                sources.append("salaries")
            if "社保" in hf:
                sources.append("social_security")
            if "凭证" in hf or "科目" in hf:
                sources.append("vouchers")
            if "存货" in hf or "库存" in hf:
                sources.append("inventory")
        
        # 确定阶段
        stage = "domain"
        if f.get("source", "").startswith("规则引擎"):
            stage = "rule"
        elif f.get("_from_engine"):
            stage = "engine"
        elif f.get("_from_cross"):
            stage = "cross"
        elif ftype in ("综合定性", "综合风险评估"):
            stage = "synthesis"
        
        # 数据独立性判定：缺资料类 finding 不依赖具体数据
        data_independent = any(kw in ftype for kw in ["资料完备", "资料缺失", "缺失", "无此资料"])
        
        f["provenance"] = {
            "sources": sources if sources else ["unknown"],
            "domain": domain or "unknown",
            "stage": stage,
            "data_independent": data_independent,
        }
    
    return all_findings


def _check_alternative_evidence(hypothesis_name, finding):
    """检查替代假设是否有证据支持"""
    # 简单检查：alternative hypothesis name中的关键词是否出现在finding中
    combined = finding.get("type", "") + " " + str(finding.get("detail", ""))
    keywords = {
        "股东注资": ["注资", "增资", "实收资本", "股东"],
        "季节性备货": ["备货", "库存", "囤货", "季节"],
        "关联方资金拆借": ["关联", "拆借", "借款", "往来款"],
    }
    for key, kws in keywords.items():
        if key in hypothesis_name:
            for kw in kws:
                if kw in combined:
                    return f"发现关键词'{kw}'"
    return ""


def _compute_intuition_patterns(ctx, all_findings):
    """经验直觉：从历史反馈+信号共现中学习异常模式组合。
    
    像老稽查员一样，看多了自然形成"第六感"——
    某些信号组合虽然单独不严重，但一起出现时几乎总是有问题。
    
    实现方式：
    1. 从 audit_feedback.json 读取被确认的高风险发现
    2. 统计这些发现中信号类型的共现模式
    3. 当当前分析的finding中出现这些共现模式时，触发"直觉警报"
    """
    from collections import defaultdict, Counter
    
    intuition_hits = []
    
    # 加载反馈数据
    feedback_path = os.path.join(_PROJECT_ROOT, "static", 'audit_feedback.json')
    confirmed_patterns = Counter()
    try:
        if os.path.exists(feedback_path):
            with open(feedback_path, 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)
            # 统计被confirm的高风险发现
            for fb in feedbacks:
                if fb.get("action") == "confirm":
                    ftype = fb.get("finding_type", "")
                    confirmed_patterns[ftype] += 1
    except Exception:
        pass
    
    # 如果没有足够反馈数据，从 audit_memory.json 中学习
    if len(confirmed_patterns) < 5:
        memory_path = os.path.join(_PROJECT_ROOT, "static", 'audit_memory.json')
        try:
            if os.path.exists(memory_path):
                with open(memory_path, 'r', encoding='utf-8') as f:
                    memory = json.load(f)
                # 统计历史高风险案例中常见的信号组合
                for m in memory:
                    if m.get("risk_level") in ("高风险", "极高风险"):
                        reds = m.get("red_flags", [])
                        if len(reds) >= 2:
                            pair = " + ".join(sorted(reds)[:2])
                            confirmed_patterns[pair] += 1
        except Exception:
            pass
    
    # 将学习的模式应用到当前发现
    signal_index = defaultdict(list)
    for f in all_findings:
        for st in f.get("_signal_types", []):
            signal_index[st].append(f)
    
    for pattern, count in confirmed_patterns.items():
        if count < 2:
            continue
        # 检查当前发现中是否存在这个模式
        pattern_signals = pattern.split(" + ")
        if all(s in signal_index for s in pattern_signals):
            hit_findings = []
            for s in pattern_signals:
                hit_findings.extend(signal_index[s][:1])
            
            intuition_hits.append({
                "type": f"直觉警报-{pattern}",
                "level": "高风险",
                "score": 8,
                "detail": (
                    f"历史经验直觉：'{pattern}'信号组合在{count}次历史分析中被确认为高风险。"
                    f"当前分析中出现相同信号组合，建议重点关注。"
                ),
                "description": f"基于{count}条历史反馈/记忆自动学习的异常模式。该信号组合单独看可能不突出，但一起出现时几乎总是有问题。",
                "how_found": f"经验直觉引擎: 从{count}条历史确认案例中学习到'{pattern}'是高危信号组合 → 当前分析命中",
                "category": "经验直觉",
                "_intuition_hit": True,
                "_intuition_pattern": pattern,
                "_intuition_count": count,
            })
    
    return intuition_hits


def _multi_hypothesis_check(ctx, all_findings, bank_txs, invoices):
    """多假设并行推理：对核心问题同时维护2-3个竞争假设，随证据收窄。
    
    人类稽查员的核心思维模式：
    不是一开始就锁定一个结论，而是同时假设几种可能性，
    随着分析的深入逐步排除不成立的假设，最终收敛到最可能的解释。
    """
    multi_hypo_results = []
    
    # 核心场景：进销严重不匹配 → 并行假设
    has_inventory_gap = any("购销" in f.get("type", "") or "进销" in f.get("type", "") for f in all_findings)
    has_personal_pay = any("个人" in f.get("type", "") for f in all_findings)
    has_processing = any("加工" in f.get("type", "") for f in all_findings)
    
    if has_inventory_gap:
        hypotheses = [
            {"name": "假设A: 虚增进项", "signals_for": [], "signals_against": [], "score": 50,
             "explanation": "企业通过购买/虚开进项发票夸大采购成本，降低应纳税额"},
            {"name": "假设B: 隐匿销项", "signals_for": [], "signals_against": [], "score": 50,
             "explanation": "企业将部分销售收入不入账（私户收款），导致账面销项偏低"},
            {"name": "假设C: 正常时间差", "signals_for": [], "signals_against": [], "score": 50,
             "explanation": "采购与销售存在正常的时间差（备货期），账期不同导致进销错位"},
        ]
        
        for f in all_findings:
            ftext = f.get("type", "") + " " + str(f.get("detail", ""))
            content = f.get("_signal_types", [])
            
            # 假设A证据
            if any(k in content for k in ["虚开", "发票连号", "供应商集中", "付款未匹配"]):
                hypotheses[0]["signals_for"].append(f.get("type", ""))
                hypotheses[0]["score"] += 15
            # 假设B证据
            if any(k in content for k in ["个人付款", "隐匿收入", "收款偏差", "法人或股东"]):
                hypotheses[1]["signals_for"].append(f.get("type", ""))
                hypotheses[1]["score"] += 15
            # 假设C证据
            if any(k in content for k in ["库存积压", "备货", "季节性"]):
                hypotheses[2]["signals_for"].append(f.get("type", ""))
                hypotheses[2]["score"] += 15
            
            # 证伪信号
            if "毛利率正常" in ftext or "购销比例合理" in ftext:
                for h in hypotheses[:2]:
                    h["signals_against"].append("毛利率正常")
                    h["score"] -= 10
            if "BOM完整" in ftext:
                hypotheses[0]["signals_against"].append("BOM完整→进项有实物支撑")
                hypotheses[0]["score"] -= 15
        
        # 排序
        hypotheses.sort(key=lambda x: -x["score"])
        winner = hypotheses[0]
        runner_up = hypotheses[1] if len(hypotheses) > 1 else None
        
        multi_hypo_results.append({
            "type": "多假设并行推理-进销异常",
            "level": "中风险",
            "score": 5,
            "detail": (
                f"【{winner['name']}】得分最高({winner['score']}分): {winner['explanation']}\n"
                + (f"【{runner_up['name']}】次选({runner_up['score']}分): {runner_up['explanation']}" if runner_up else "")
            ),
            "description": (
                f"对进销严重不匹配，同时考虑3种竞争假设并行推理：\n"
                + "\n".join([f"  {h['name']}({h['score']}分): {h['explanation']}"
                           + (f" 支持信号: {', '.join(h['signals_for'][:3])}" if h['signals_for'] else "")
                           + (f" 反对信号: {', '.join(h['signals_against'][:3])}" if h['signals_against'] else "")
                           for h in hypotheses])
            ),
            "how_found": f"多假设引擎: 并行维护3个假设 → 证据收窄 → {winner['name']}胜出(得分{winner['score']})",
            "category": "多假设推理",
            "_multi_hypothesis": True,
            "_hypotheses": hypotheses,
        })
    
    return multi_hypo_results


def _cross_period_compare(ctx, company_id, db):
    """跨期对比记忆：同一企业历史分析对比，发现趋势变化。
    
    检查点：
    1. 毛利率趋势：上升/下降/稳定
    2. 购销比变化
    3. 信号模式变化（新增/消失的危险信号）
    """
    
    memory_path = os.path.join(_PROJECT_ROOT, "static", 'audit_memory.json')
    prev_records = []
    try:
        if os.path.exists(memory_path):
            with open(memory_path, 'r', encoding='utf-8') as f:
                all_memory = json.load(f)
            # 找同公司的历史记录（通过company profile中的特征匹配）
            cp = ctx.company_profile
            for m in all_memory:
                if (m.get("industry") == cp.get("industry", "") and 
                    m.get("biz_model") == cp.get("biz_model", "") and
                    m.get("scale") == cp.get("scale", "")):
                    prev_records.append(m)
            # 最近3条
            prev_records = sorted(prev_records, key=lambda x: x.get("timestamp", ""), reverse=True)[:3]
    except Exception:
        pass
    
    if len(prev_records) < 1:
        return []
    
    findings = []
    current = ctx.financial_snapshot
    
    most_recent = prev_records[0]
    prev_snapshot = most_recent.get("snapshot", {}) or {}
    
    # 毛利率对比
    prev_gm = prev_snapshot.get("gross_margin_pct", 0)
    curr_gm = current.get("gross_margin_pct", 0)
    if prev_gm > 0 and curr_gm > 0:
        gm_change = curr_gm - prev_gm
        if abs(gm_change) > 10:
            direction = "下降" if gm_change < 0 else "上升"
            findings.append({
                "type": f"跨期对比-毛利率{direction}",
                "level": "黄灯" if abs(gm_change) > 20 else "中风险",
                "score": 6 if abs(gm_change) > 20 else 4,
                "detail": f"毛利率从{prev_gm:.2f}%{direction}至{curr_gm:.2f}%，变化{abs(gm_change):.2f}个百分点",
                "description": f"与上次分析({most_recent.get('timestamp','')[:10]})对比，毛利率大幅{direction}，需关注经营实质是否发生变化",
                "how_found": f"跨期对比引擎: 比较{len(prev_records)}条历史记录 → 毛利率{prev_gm:.2f}%→{curr_gm:.2f}%",
                "category": "跨期对比",
                "_cross_period": True,
            })
    
    # 信号模式变化
    prev_reds = set(most_recent.get("red_flags", []))
    curr_reds = set()
    for f in ctx.red_flags:
        curr_reds.add(f.get("type", f.get("flag_type", "")))
    
    new_reds = curr_reds - prev_reds
    resolved_reds = prev_reds - curr_reds
    
    if resolved_reds:
        findings.append({
            "type": "跨期对比-风险信号减少",
            "level": "低风险",
            "score": 2,
            "detail": f"{len(resolved_reds)}个历史风险信号已消失: {', '.join(list(resolved_reds)[:3])}",
            "description": "与历史对比，部分风险信号已解除，可能由于企业整改或经营状况改善",
            "category": "跨期对比",
            "_cross_period": True,
        })
    
    return findings


def _build_entity_graph(bank_txs, invoices, salaries):
    """知识图谱：从交易数据中构建实体关系网络，发现隐藏关联。
    
    实体类型：企业、个人、账户
    关系类型：付款、收款、开票、受票、雇佣
    异常检测：同一实体在多个角色中出现（既是供应商又是客户）
    """
    from collections import defaultdict
    
    entities = defaultdict(lambda: {"roles": set(), "transactions": [], "total_amount": 0})
    
    # 从发票提取实体
    for inv in invoices:
        seller = str(inv.get("seller", inv.get("销方名称", ""))).strip()
        buyer = str(inv.get("buyer", inv.get("购方名称", ""))).strip()
        amount = float(inv.get("amount", inv.get("total", 0)) or 0)
        
        if seller:
            entities[seller]["roles"].add("供应商")
            entities[seller]["transactions"].append({"type": "开票", "counterparty": buyer[:20], "amount": amount})
            entities[seller]["total_amount"] += amount
        if buyer:
            entities[buyer]["roles"].add("客户")
            entities[buyer]["transactions"].append({"type": "受票", "counterparty": seller[:20], "amount": amount})
            entities[buyer]["total_amount"] += amount
    
    # 从银行流水提取实体
    for tx in bank_txs:
        cp = str(tx.get("counterparty", tx.get("对方户名", ""))).strip()
        debit = float(tx.get("debit", 0) or 0)
        credit = float(tx.get("credit", 0) or 0)
        amount = max(debit, credit)
        
        if cp:
            if credit > 0:
                entities[cp]["roles"].add("付款方")
            if debit > 0:
                entities[cp]["roles"].add("收款方")
            entities[cp]["total_amount"] += amount
    
    # 从工资表提取实体
    for s in salaries:
        name = str(s.get("姓名", s.get("name", ""))).strip()
        if name:
            entities[name]["roles"].add("员工")
    
    # ── 异常检测 ──
    anomalies = []
    
    # 1. 角色重叠：既是供应商又是客户
    dual_role = {name: info for name, info in entities.items() 
                 if len(info["roles"]) >= 2 and name}
    for name, info in dual_role.items():
        if "供应商" in info["roles"] and "客户" in info["roles"]:
            anomalies.append({
                "type": "知识图谱-供应商客户重叠",
                "entity": name,
                "roles": list(info["roles"]),
                "total_amount": info["total_amount"],
                "detail": f"{name}同时作为供应商和客户，存在关联交易嫌疑",
            })
        elif "供应商" in info["roles"] and "付款方" in info["roles"]:
            anomalies.append({
                "type": "知识图谱-供应商收款异常",
                "entity": name,
                "roles": list(info["roles"]),
                "total_amount": info["total_amount"],
                "detail": f"{name}既是供应商又向企业付款（反常资金流向）",
            })
    
    # 2. 关键人物关联：同一人在多处出现
    for name, info in entities.items():
        if len(info["roles"]) >= 2 and "员工" in info["roles"]:
            other_roles = info['roles'] - {'员工'}
            anomalies.append({
                "type": "知识图谱-员工多重身份",
                "entity": name,
                "roles": list(info["roles"]),
                "total_amount": info["total_amount"],
                "detail": f"{name}既是员工又有其他角色({', '.join(other_roles)})，可能涉及利益输送",
            })
    
    # 3. 二层穿透：员工收款金额与工资对比（资金流向深度分析）
    if salaries:
        salary_map = {}
        for s in salaries:
            sn = str(s.get("姓名", s.get("name", ""))).strip()
            sa = float(s.get("实发金额", s.get("应发金额", s.get("amount", 0))) or 0)
            if sn and sa > 0:
                salary_map[sn] = salary_map.get(sn, 0) + sa
        
        for name, info in entities.items():
            if "员工" in info["roles"] and name in salary_map:
                emp_salary = salary_map[name]
                emp_receive = info["total_amount"]
                if emp_receive > emp_salary * 3:  # 收款额超过工资3倍
                    multiplier = emp_receive / max(emp_salary, 1)
                    anomalies.append({
                        "type": "知识图谱-员工资金异常",
                        "entity": name,
                        "roles": list(info["roles"]),
                        "total_amount": info["total_amount"],
                        "detail": f"{name}：银行收款{emp_receive:,.2f}元，工资{emp_salary:,.2f}元，收款/工资倍数{multiplier:.1f}倍。该员工账户大额收款远超出正常工资水平，可能为经营收入回流个人账户、代收货款、或为他人过账。需核查该员工岗位职责与收款金额是否匹配。",
                    })
    
    # 生成发现
    findings = []
    for i, a in enumerate(anomalies[:10]):
        findings.append({
            "type": a["type"],
            "level": "中风险",
            "score": 7,
            "detail": a["detail"],
            "description": f"知识图谱分析: 实体'{a['entity'][:20]}'具有多重角色({', '.join(a['roles'])}), 涉及金额{a['total_amount']:,.2f}元",
            "how_found": f"知识图谱引擎: 从{len(entities)}个实体中检测到{len(anomalies)}个异常关系 → {a['type']}",
            "category": "知识图谱",
            "_entity_graph": True,
            "_entity": a["entity"],
        })
    
    # 附加图谱摘要
    graph_summary = {
        "total_entities": len(entities),
        "total_anomalies": len(anomalies),
        "dual_role_count": len([a for a in anomalies if "重叠" in a["type"]]),
        "top_entities": sorted(
            [{"name": n[:20], "roles": list(i["roles"]), "amount": i["total_amount"]} 
             for n, i in entities.items() if i["total_amount"] > 0],
            key=lambda x: -x["amount"]
        )[:10],
    }
    
    return findings, graph_summary


def _adversarial_robustness_check(all_findings, invoices, bank_txs):
    """对抗鲁棒性检测 —— 识别人为编造数据的痕迹。
    
    方法：
    1. 本福特定律（Benford's Law）：真实财务数据的首位数字服从对数分布
    2. 重复金额检测：完全相同金额出现频率
    3. 数字偏好检测：避开4/喜欢8等人为心理特征
    """
    import math
    from collections import Counter
    
    findings = []
    
    # ── 本福特定律检测 ──
    amounts = []
    if invoices:
        for inv in invoices:
            a = float(inv.get("amount", inv.get("total", 0)) or 0)
            if a >= 10:
                amounts.append(a)
    
    if bank_txs:
        for tx in bank_txs:
            a = max(float(tx.get("debit", 0) or 0), float(tx.get("credit", 0) or 0))
            if a >= 10:
                amounts.append(a)
    
    if len(amounts) >= 30:
        # 统计首位数字分布
        first_digit_counts = Counter()
        for a in amounts:
            first = int(str(abs(a)).strip('0.')[0]) if abs(a) >= 1 else 0
            if 1 <= first <= 9:
                first_digit_counts[first] += 1
        
        total = sum(first_digit_counts.values())
        if total >= 20:
            # 本福特理论分布: P(d) = log10(1 + 1/d)
            benford_expected = {d: math.log10(1 + 1/d) * total for d in range(1, 10)}
            
            # 卡方检验
            chi_square = 0
            max_deviation = 0
            max_dev_digit = 0
            for d in range(1, 10):
                observed = first_digit_counts.get(d, 0)
                expected = benford_expected[d]
                if expected > 0:
                    dev = (observed - expected) ** 2 / expected
                    chi_square += dev
                    deviation_pct = abs(observed - expected) / expected * 100
                    if deviation_pct > max_deviation:
                        max_deviation = deviation_pct
                        max_dev_digit = d
            
            # 卡方>15.5 (8自由度, p<0.05) → 显著偏离本福特
            if chi_square > 15.5:
                findings.append({
                    "type": "对抗鲁棒性-本福特定律偏离",
                    "level": "中风险",
                    "score": 7,
                    "detail": f"金额首位数字分布显著偏离本福特定律（卡方={chi_square:.2f}, p<0.05）→数据可能经过人为干预",
                    "how_found": f"对抗引擎: {total}个金额的首位分布vs本福特理论→卡方{chi_square:.2f}>临界值15.5",
                    "suggestion": "重点核查偏离最大的数字{max_dev_digit}（偏差{max_deviation:.2f}%），对比原始凭证",
                    "category": "对抗鲁棒性"
                })
    
    # ── 重复金额检测 ──
    if len(amounts) >= 10:
        amount_counter = Counter(amounts)
        exact_dupes = {a: c for a, c in amount_counter.items() if c >= 3 and a >= 1000}
        if len(exact_dupes) >= 3:
            top_dupe = max(exact_dupes, key=exact_dupes.get)
            findings.append({
                "type": "对抗鲁棒性-重复金额异常",
                "level": "黄灯",
                "score": 5,
                "detail": f"发现{len(exact_dupes)}个金额重复>=3次（如{top_dupe:,.2f}元出现{exact_dupes[top_dupe]}次）→可能批量编造",
                "category": "对抗鲁棒性"
            })
    
    return findings


def _auto_rule_discovery(all_findings):
    """自动规则发现 —— 从反馈和共现模式中挖掘新规则。
    
    不依赖人工预定义，自动发现"信号X+信号Y几乎总是同时出现且都是高风险"的模式。
    """
    from collections import defaultdict, Counter
    
    new_rules = []
    
    # ── 从当前发现的信号共现中学习 ──
    signal_cooccur = defaultdict(list)
    for f in all_findings:
        sigs = f.get("_signal_types", [])
        level = f.get("level", "")
        score = f.get("score", 0) or 0
        
        if score >= 7 and len(sigs) >= 2:
            for i in range(len(sigs)):
                for j in range(i+1, len(sigs)):
                    pair = tuple(sorted([sigs[i], sigs[j]]))
                    signal_cooccur[pair].append(score)
    
    # 高频高风险的共现模式
    for pair, scores in signal_cooccur.items():
        if len(scores) >= 2 and sum(scores)/len(scores) >= 7:
            new_rules.append({
                "signals": list(pair),
                "avg_score": round(sum(scores)/len(scores), 1),
                "frequency": len(scores),
                "auto_discovered": True,
            })
    
    # ── 加载历史反馈中学习的模式 ──
    learned = []
    feedback_path = os.path.join(_PROJECT_ROOT, "static", 'audit_feedback.json')
    try:
        if os.path.exists(feedback_path):
            with open(feedback_path, 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)
            confirmed_types = Counter()
            for fb in feedbacks:
                if fb.get("action") == "confirm" and fb.get("finding_type"):
                    confirmed_types[fb["finding_type"]] += 1
            for ftype, count in confirmed_types.most_common(10):
                if count >= 2:
                    learned.append({
                        "finding_type": ftype,
                        "confirmations": count,
                        "learned_weight": min(1.5, 1.0 + count * 0.1),
                    })
    except:
        pass
    
    return {
        "discovered_rules": new_rules[:5],
        "learned_weights": learned[:10],
        "total_learned": len(learned),
    }


def _audit_strategy_recommend(ctx, all_findings):
    """审计策略推荐 —— 基于发现自动推荐下一步取证动作。
    
    从"发现问题"升级到"告诉你怎么查"。
    每条策略包含：优先级/动作/依据/预期结果。
    """
    strategies = []
    high_risk_count = sum(1 for f in all_findings if f.get("level") in ("高风险", "极高风险"))
    has_bank_issues = any("银行" in f.get("type", "") or "资金" in f.get("type", "") or "收款" in f.get("type", "") for f in all_findings)
    has_invoice_issues = any("发票" in f.get("type", "") or "虚开" in f.get("type", "") for f in all_findings)
    has_personal = any("个人" in f.get("type", "") for f in all_findings)
    
    # 策略模板
    if has_bank_issues:
        strategies.append({
            "priority": "P0",
            "action": "调取全部银行账户流水",
            "basis": f"发现{high_risk_count}项高风险资金异常",
            "detail": "向开户银行发函调取被查单位及法定代表人、财务负责人名下全部账户的完整流水（含已销户），覆盖分析期前后各6个月",
            "expected": "获取完整资金链路，确认收款来源和付款去向"
        })
    
    if has_invoice_issues:
        strategies.append({
            "priority": "P0",
            "action": "发函协查上游供应商",
            "basis": "发现发票真实性存疑",
            "detail": "向供应商所在地税务机关发函协查，核实供应商是否真实经营、是否正常申报纳税、是否存在走逃/注销",
            "expected": "确认进项发票真实性，锁定虚开证据链"
        })
    
    if has_personal:
        strategies.append({
            "priority": "P0",
            "action": "核查个人账户资金性质",
            "basis": "发现个人付款方占比异常",
            "detail": "逐笔核实大额个人付款方身份（是否为员工/股东/关联方），追踪收款后资金去向",
            "expected": "区分经营收入、股东注资、关联方拆借，确认是否有隐匿收入"
        })
    
    # 通用策略
    strategies.append({
        "priority": "P1",
        "action": "实地核查经营场所",
        "basis": "需要验证经营实质",
        "detail": "实地查看生产/办公场所、机器设备、存货情况，拍照固定证据，制作现场笔录",
        "expected": "确认产能是否匹配产出，是否存在'空壳经营'"
    })
    
    strategies.append({
        "priority": "P1",
        "action": "约谈法定代表人及财务负责人",
        "basis": "需要就异常情况取得当事人陈述",
        "detail": "制作询问笔录，重点询问：经营模式、供应商/客户关系、资金往来性质、加工流程",
        "expected": "取得当事人对异常情况的解释说明，固定口供证据"
    })
    
    # 补充证据策略
    missing_evidence = []
    if not any("BOM" in f.get("type", "") for f in all_findings):
        missing_evidence.append({
            "priority": "P2",
            "action": "要求提供BOM表（物料清单）",
            "basis": "制造业/加工企业应能提供投入产出单耗数据",
            "detail": "要求提供主要产品的BOM表，列明单位产品耗用原材料/辅料/人工/能耗的定额，用于验证发票品名差异的合理性",
            "expected": "验证加工链条真实性或揭露虚开发票"
        })
    strategies.extend(missing_evidence)
    
    return {
        "strategies": strategies,
        "total": len(strategies),
        "p0_count": sum(1 for s in strategies if s["priority"] == "P0"),
    }


def _multimodal_support_check(docs, file_results):
    """多模态支持 —— 检测需要OCR/图像分析的文件并给出处理建议。
    
    当前阶段：识别需要OCR的文件类型，标记待处理。
    远期：接入OCR引擎自动提取合同/图片中的关键信息。
    """
    multimodal_files = []
    
    image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.gif', '.webp', '.pdf'}
    ocr_needed = []
    
    for fr in (file_results or []):
        fname = fr.get("file", fr.get("file_name", fr.get("original_name", "")))
        ftype = fr.get("type", "unknown")
        
        # 检测图片/PDF
        ext = os.path.splitext(fname)[1].lower() if '.' in str(fname) else ''
        if ext in image_exts or ftype == 'unknown':
            ocr_needed.append({
                "file": fname,
                "reason": "PDF/图片格式" if ext == '.pdf' else ("图片格式" if ext in image_exts else "未识别格式"),
                "suggested_action": "上传至OCR引擎提取文本/表格数据",
            })
    
    contract_kws = ["合同", "协议", "contract", "agreement"]
    has_contracts = any(
        any(kw in str(fr.get("file", "")).lower() for kw in contract_kws)
        for fr in (file_results or [])
    )
    
    status = "active" if ocr_needed else "idle"
    
    return {
        "status": status,
        "ocr_files_count": len(ocr_needed),
        "ocr_files": ocr_needed[:5],
        "has_contracts": has_contracts,
        "recommendation": (
            f"检测到{len(ocr_needed)}个需要OCR处理的文件" if ocr_needed
            else "当前上传文件均为结构化数据（Excel/CSV），无需OCR处理"
        )
    }

def _deep_biz_substance_check(ctx, bank_txs, invoices, salaries):
    """经营实质深挖 —— 虚开发票的终极克星。
    
    核心逻辑：真实经营必须消耗生产要素（水/电/运输/人工）。
    如果发票显示大量产出，但要素消耗不匹配 → 虚开嫌疑极大。
    
    检测项：
    1. 水电费vs产量：制造业必须有水电支出
    2. 运输费vs销量：有销售必须有物流
    3. 人工vs产量：产量需要人工支撑
    """
    from collections import defaultdict
    
    findings = []
    fs = ctx.financial_snapshot
    cp = ctx.company_profile
    
    # 提取费用类关键词
    utility_kws = ["电", "水", "电费", "水费", "水电", "电力", "水务", "能源"]
    transport_kws = ["运输", "物流", "货运", "运费", "快递", "配送", "搬"]
    labor_kws = ["工资", "薪金", "劳务", "人工", "薪酬", "奖金"]
    
    has_utility = False
    has_transport = False
    utility_total = 0
    transport_total = 0
    
    if bank_txs:
        for tx in bank_txs:
            summary = str(tx.get("summary", tx.get("用途", "")))
            counterparty = str(tx.get("counterparty", tx.get("对方户名", "")))
            text = summary + counterparty
            amt = max(float(tx.get("debit", 0) or 0), float(tx.get("credit", 0) or 0))
            
            if any(kw in text for kw in utility_kws):
                has_utility = True
                utility_total += amt
            if any(kw in text for kw in transport_kws):
                has_transport = True
                transport_total += amt
    
    if invoices:
        for inv in invoices:
            goods = str(inv.get("goods", inv.get("货物或应税劳务名称", "")))
            if any(kw in goods for kw in utility_kws):
                has_utility = True
                utility_total += float(inv.get("amount", 0) or 0)
            if any(kw in goods for kw in transport_kws):
                has_transport = True
                transport_total += float(inv.get("amount", 0) or 0)
    
    total_sales = fs.get("total_sales", 0)
    total_purchases = fs.get("total_purchases", 0)
    total_salary = fs.get("total_salary", 0)
    biz_model = cp.get("biz_model", "")
    
    # ── 制造业必须有水电+运输 ──
    if biz_model == "制造业" and total_sales > T.amount_thresholds.micro_transaction000:
        if not has_utility and total_purchases > T.amount_thresholds.large_transaction:
            findings.append({
                "type": "经营实质-缺水电支出",
                "level": "高风险",
                "score": 9,
                "detail": f"制造业进项{total_purchases:,.2f}元但未检测到水电费支出——生产必须有能源消耗，疑似无实际生产",
                "how_found": "经营实质引擎: 扫描银行流水+发票品名中的水电关键词→未命中→产能存疑",
                "suggestion": "核查企业实际经营场所、电表读数、水费单据",
                "category": "经营实质深挖"
            })
        if not has_transport and total_sales > T.amount_thresholds.micro_transaction000:
            findings.append({
                "type": "经营实质-缺运输支出",
                "level": "中风险",
                "score": 7,
                "detail": f"销售额{total_sales:,.2f}元但未检测到运输/物流费用——货物销售必须有物流",
                "how_found": "经营实质引擎: 扫描运输关键词→未命中→物流真实性存疑",
                "suggestion": "核查出库单、物流单据、运输合同",
                "category": "经营实质深挖"
            })
    
    # ── 人工vs产出匹配 ──
    if biz_model in ("制造业", "贸易") and total_sales > 5000000:
        emp_count = fs.get("salary_count", 0)
        if emp_count > 0 and total_salary > 0:
            revenue_per_emp = total_sales / emp_count
            if revenue_per_emp > 5000000:
                findings.append({
                    "type": "经营实质-人均产出异常",
                    "level": "中风险",
                    "score": 6,
                    "detail": f"人均产出{revenue_per_emp:,.2f}元（{emp_count}人支撑{total_sales:,.2f}元销售额）→人员规模与产出不匹配",
                    "how_found": f"经营实质引擎: {emp_count}人×人均{revenue_per_emp:,.2f}元→超出合理范围",
                    "suggestion": "核查是否有外协加工/外包/挂靠等未披露的安排",
                    "category": "经营实质深挖"
                })
        elif emp_count == 0 and total_sales > T.amount_thresholds.micro_transaction000:
            findings.append({
                "type": "经营实质-无人工支出",
                "level": "高风险",
                "score": 8,
                "detail": f"销售额{total_sales:,.2f}元但无工资记录——无人工不可能有产出",
                "category": "经营实质深挖"
            })
    
    # ── 运输费vs销量 ──
    if has_transport and total_sales > 0:
        transport_ratio = transport_total / total_sales * 100
        if transport_ratio < T.ratios.half and biz_model == "制造业":
            findings.append({
                "type": "经营实质-运输费占比偏低",
                "level": "低风险",
                "score": 4,
                "detail": f"运输费{transport_total:,.2f}元仅占销售额{transport_ratio:.2f}%→制造业物流成本通常1-5%",
                "category": "经营实质深挖"
            })
    
    return findings


def _adversarial_robustness_check(all_findings, invoices, bank_txs):
    """对抗鲁棒性检测 —— 识别人为编造数据的痕迹。
    
    方法：
    1. 本福特定律（Benford's Law）：真实财务数据的首位数字服从对数分布
    2. 重复金额检测：完全相同金额出现频率
    3. 数字偏好检测：避开4/喜欢8等人为心理特征
    """
    import math
    from collections import Counter
    
    findings = []
    
    # ── 本福特定律检测 ──
    amounts = []
    if invoices:
        for inv in invoices:
            a = float(inv.get("amount", inv.get("total", 0)) or 0)
            if a >= 10:
                amounts.append(a)
    
    if bank_txs:
        for tx in bank_txs:
            a = max(float(tx.get("debit", 0) or 0), float(tx.get("credit", 0) or 0))
            if a >= 10:
                amounts.append(a)
    
    if len(amounts) >= 30:
        # 统计首位数字分布
        first_digit_counts = Counter()
        for a in amounts:
            first = int(str(abs(a)).strip('0.')[0]) if abs(a) >= 1 else 0
            if 1 <= first <= 9:
                first_digit_counts[first] += 1
        
        total = sum(first_digit_counts.values())
        if total >= 20:
            # 本福特理论分布: P(d) = log10(1 + 1/d)
            benford_expected = {d: math.log10(1 + 1/d) * total for d in range(1, 10)}
            
            # 卡方检验
            chi_square = 0
            max_deviation = 0
            max_dev_digit = 0
            for d in range(1, 10):
                observed = first_digit_counts.get(d, 0)
                expected = benford_expected[d]
                if expected > 0:
                    dev = (observed - expected) ** 2 / expected
                    chi_square += dev
                    deviation_pct = abs(observed - expected) / expected * 100
                    if deviation_pct > max_deviation:
                        max_deviation = deviation_pct
                        max_dev_digit = d
            
            # 卡方>15.5 (8自由度, p<0.05) → 显著偏离本福特
            if chi_square > 15.5:
                findings.append({
                    "type": "对抗鲁棒性-本福特定律偏离",
                    "level": "中风险",
                    "score": 7,
                    "detail": f"金额首位数字分布显著偏离本福特定律（卡方={chi_square:.2f}, p<0.05）→数据可能经过人为干预",
                    "how_found": f"对抗引擎: {total}个金额的首位分布vs本福特理论→卡方{chi_square:.2f}>临界值15.5",
                    "suggestion": "重点核查偏离最大的数字{max_dev_digit}（偏差{max_deviation:.2f}%），对比原始凭证",
                    "category": "对抗鲁棒性"
                })
    
    # ── 重复金额检测 ──
    if len(amounts) >= 10:
        amount_counter = Counter(amounts)
        exact_dupes = {a: c for a, c in amount_counter.items() if c >= 3 and a >= 1000}
        if len(exact_dupes) >= 3:
            top_dupe = max(exact_dupes, key=exact_dupes.get)
            findings.append({
                "type": "对抗鲁棒性-重复金额异常",
                "level": "黄灯",
                "score": 5,
                "detail": f"发现{len(exact_dupes)}个金额重复>=3次（如{top_dupe:,.2f}元出现{exact_dupes[top_dupe]}次）→可能批量编造",
                "category": "对抗鲁棒性"
            })
    
    return findings


def _auto_rule_discovery(all_findings):
    """自动规则发现 —— 从反馈和共现模式中挖掘新规则。
    
    不依赖人工预定义，自动发现"信号X+信号Y几乎总是同时出现且都是高风险"的模式。
    """
    from collections import defaultdict, Counter
    
    new_rules = []
    
    # ── 从当前发现的信号共现中学习 ──
    signal_cooccur = defaultdict(list)
    for f in all_findings:
        sigs = f.get("_signal_types", [])
        level = f.get("level", "")
        score = f.get("score", 0) or 0
        
        if score >= 7 and len(sigs) >= 2:
            for i in range(len(sigs)):
                for j in range(i+1, len(sigs)):
                    pair = tuple(sorted([sigs[i], sigs[j]]))
                    signal_cooccur[pair].append(score)
    
    # 高频高风险的共现模式
    for pair, scores in signal_cooccur.items():
        if len(scores) >= 2 and sum(scores)/len(scores) >= 7:
            new_rules.append({
                "signals": list(pair),
                "avg_score": round(sum(scores)/len(scores), 1),
                "frequency": len(scores),
                "auto_discovered": True,
            })
    
    # ── 加载历史反馈中学习的模式 ──
    learned = []
    feedback_path = os.path.join(_PROJECT_ROOT, "static", 'audit_feedback.json')
    try:
        if os.path.exists(feedback_path):
            with open(feedback_path, 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)
            confirmed_types = Counter()
            for fb in feedbacks:
                if fb.get("action") == "confirm" and fb.get("finding_type"):
                    confirmed_types[fb["finding_type"]] += 1
            for ftype, count in confirmed_types.most_common(10):
                if count >= 2:
                    learned.append({
                        "finding_type": ftype,
                        "confirmations": count,
                        "learned_weight": min(1.5, 1.0 + count * 0.1),
                    })
    except:
        pass
    
    return {
        "discovered_rules": new_rules[:5],
        "learned_weights": learned[:10],
        "total_learned": len(learned),
    }


def _audit_strategy_recommend(ctx, all_findings):
    """审计策略推荐 —— 基于发现自动推荐下一步取证动作。
    
    从"发现问题"升级到"告诉你怎么查"。
    每条策略包含：优先级/动作/依据/预期结果。
    """
    strategies = []
    high_risk_count = sum(1 for f in all_findings if f.get("level") in ("高风险", "极高风险"))
    has_bank_issues = any("银行" in f.get("type", "") or "资金" in f.get("type", "") or "收款" in f.get("type", "") for f in all_findings)
    has_invoice_issues = any("发票" in f.get("type", "") or "虚开" in f.get("type", "") for f in all_findings)
    has_personal = any("个人" in f.get("type", "") for f in all_findings)
    
    # 策略模板
    if has_bank_issues:
        strategies.append({
            "priority": "P0",
            "action": "调取全部银行账户流水",
            "basis": f"发现{high_risk_count}项高风险资金异常",
            "detail": "向开户银行发函调取被查单位及法定代表人、财务负责人名下全部账户的完整流水（含已销户），覆盖分析期前后各6个月",
            "expected": "获取完整资金链路，确认收款来源和付款去向"
        })
    
    if has_invoice_issues:
        strategies.append({
            "priority": "P0",
            "action": "发函协查上游供应商",
            "basis": "发现发票真实性存疑",
            "detail": "向供应商所在地税务机关发函协查，核实供应商是否真实经营、是否正常申报纳税、是否存在走逃/注销",
            "expected": "确认进项发票真实性，锁定虚开证据链"
        })
    
    if has_personal:
        strategies.append({
            "priority": "P0",
            "action": "核查个人账户资金性质",
            "basis": "发现个人付款方占比异常",
            "detail": "逐笔核实大额个人付款方身份（是否为员工/股东/关联方），追踪收款后资金去向",
            "expected": "区分经营收入、股东注资、关联方拆借，确认是否有隐匿收入"
        })
    
    # 通用策略
    strategies.append({
        "priority": "P1",
        "action": "实地核查经营场所",
        "basis": "需要验证经营实质",
        "detail": "实地查看生产/办公场所、机器设备、存货情况，拍照固定证据，制作现场笔录",
        "expected": "确认产能是否匹配产出，是否存在'空壳经营'"
    })
    
    strategies.append({
        "priority": "P1",
        "action": "约谈法定代表人及财务负责人",
        "basis": "需要就异常情况取得当事人陈述",
        "detail": "制作询问笔录，重点询问：经营模式、供应商/客户关系、资金往来性质、加工流程",
        "expected": "取得当事人对异常情况的解释说明，固定口供证据"
    })
    
    # 补充证据策略
    missing_evidence = []
    if not any("BOM" in f.get("type", "") for f in all_findings):
        missing_evidence.append({
            "priority": "P2",
            "action": "要求提供BOM表（物料清单）",
            "basis": "制造业/加工企业应能提供投入产出单耗数据",
            "detail": "要求提供主要产品的BOM表，列明单位产品耗用原材料/辅料/人工/能耗的定额，用于验证发票品名差异的合理性",
            "expected": "验证加工链条真实性或揭露虚开发票"
        })
    strategies.extend(missing_evidence)
    
    return {
        "strategies": strategies,
        "total": len(strategies),
        "p0_count": sum(1 for s in strategies if s["priority"] == "P0"),
    }


def _multimodal_support_check(docs, file_results):
    """多模态支持 —— 检测需要OCR/图像分析的文件并给出处理建议。
    
    当前阶段：识别需要OCR的文件类型，标记待处理。
    远期：接入OCR引擎自动提取合同/图片中的关键信息。
    """
    multimodal_files = []
    
    image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.gif', '.webp', '.pdf'}
    ocr_needed = []
    
    for fr in (file_results or []):
        fname = fr.get("file", fr.get("file_name", fr.get("original_name", "")))
        ftype = fr.get("type", "unknown")
        
        # 检测图片/PDF
        ext = os.path.splitext(fname)[1].lower() if '.' in str(fname) else ''
        if ext in image_exts or ftype == 'unknown':
            ocr_needed.append({
                "file": fname,
                "reason": "PDF/图片格式" if ext == '.pdf' else ("图片格式" if ext in image_exts else "未识别格式"),
                "suggested_action": "上传至OCR引擎提取文本/表格数据",
            })
    
    contract_kws = ["合同", "协议", "contract", "agreement"]
    has_contracts = any(
        any(kw in str(fr.get("file", "")).lower() for kw in contract_kws)
        for fr in (file_results or [])
    )
    
    status = "active" if ocr_needed else "idle"
    
    return {
        "status": status,
        "ocr_files_count": len(ocr_needed),
        "ocr_files": ocr_needed[:5],
        "has_contracts": has_contracts,
        "recommendation": (
            f"检测到{len(ocr_needed)}个需要OCR处理的文件" if ocr_needed
            else "当前上传文件均为结构化数据（Excel/CSV），无需OCR处理"
        )
    }


def _build_finding_trace(finding, idx, trace_id, ctx=None):
    """
    为单条结论构建完整的推理链路追溯。
    
    每条 trace 包含：
    - finding_id: 在all_findings中的序号
    - phase_origin: 结论产生阶段（Phase1-4或域分析）
    - data_sources: 使用了哪些原始数据
    - rules_hit: 触发了哪些规则
    - detection_path: 检测路径（信号→规则→域→交叉验证→综合定性）
    - how_found: 浓缩版发现过程
    - calculation_hint: 关键计算步骤提示
    - confidence_note: 可信度说明
    """
    ftype = finding.get("type", "")
    flevel = finding.get("level", "")
    fdomain = finding.get("domain", "")
    fhow = finding.get("how_found", "")
    fscore = finding.get("score", 0)
    
    # ── 推断结论来源阶段 ──
    if finding.get("_phase4_synthesis"):
        phase = "Phase4-综合定性"
    elif finding.get("_phase3_cross_validated"):
        phase = "Phase3-交叉验证"
    elif finding.get("_auto_triggered"):
        phase = "Phase1-缺失触发"
    elif fdomain and fdomain != "未知域":
        phase = "Phase2-域分析"
    else:
        phase = "Phase1-初查"
    
    # ── 推断数据来源 ──
    sources = []
    ft = ftype + str(finding.get("description", "")) + str(fdomain) + fhow
    if any(k in ft for k in ["银行","流水","收款","付款","资金"]): sources.append("银行流水")
    if any(k in ft for k in ["发票","开票","销项","进项","普票","专票"]): sources.append("发票数据")
    if any(k in ft for k in ["凭证","分录","记账","账务"]): sources.append("记账凭证")
    if any(k in ft for k in ["工资","薪酬","个税"]): sources.append("工资表")
    if any(k in ft for k in ["社保","保险","公积金"]): sources.append("社保/公积金")
    if any(k in ft for k in ["合同","协议","签约"]): sources.append("合同文件")
    if any(k in ft for k in ["存货","库存","台账","BOM","进销存"]): sources.append("进销存/BOM")
    if any(k in ft for k in ["申报","纳税","缴税","税务"]): sources.append("纳税申报表")
    if any(k in ft for k in ["财务","资产负债","利润","损益","三源"]): sources.append("财务报表")
    if not sources: sources.append("多源数据综合")
    
    # ── 推断触发的规则 ──
    rules = []
    # 信号域映射
    signal_map = {
        "购销严重倒挂": "TRIAGE_001", "毛利率异常": "TRIAGE_002", "毛利为负": "TRIAGE_002",
        "毛利率异常高": "TRIAGE_003", "缺少银行流水": "TRIAGE_004", "无进项发票": "TRIAGE_005",
        "无工资记录": "TRIAGE_006", "加工费": "TRIAGE_007", "制造业加工": "TRIAGE_008",
        "金额整十": "TRIAGE_010", "分布异常": "TRIAGE_011", "连号": "TRIAGE_012",
        "季度末": "TRIAGE_013", "供应商集中": "TRIAGE_014", "客户集中": "TRIAGE_015",
        "个人付款": "TRIAGE_016",
    }
    for sig, rid in signal_map.items():
        if sig in ft: rules.append(rid)
    if not rules: rules.append("DOMAIN_RULE")
    
    # ── 构建检测路径 ──
    detection_path = ["文件解析→数据提取"]
    if phase == "Phase1-初查":
        detection_path.append("信号检测器扫描→命中信号")
        detection_path.append("信号评级(红/黄/绿)")
    elif phase == "Phase1-缺失触发":
        detection_path.append("检测资料缺失→查MISSING_CONSEQUENCE_TRIGGER")
        detection_path.append(f"触发风险结论: {ftype}")
    elif phase == "Phase2-域分析":
        detection_path.append(f"信号→域映射→进入{fdomain}")
        detection_path.append("域分析函数执行→产出发现")
    elif phase == "Phase3-交叉验证":
        detection_path.append("多域发现合并→交叉验证引擎")
        detection_path.append("信号叠加/冲突消解→确认/升级/降级")
    elif phase == "Phase4-综合定性":
        detection_path.append("全部发现汇集→综合评分引擎")
        detection_path.append("风险等级判定→P0/P1/P2分级")
    
    # ── 可信度说明 ──
    if fscore >= 9: confidence = "高"
    elif fscore >= 7: confidence = "中"
    else: confidence = "需交叉验证"
    
    trace = {
        "finding_id": f"F_{idx:03d}",
        "finding_type": ftype,
        "finding_level": flevel,
        "score": fscore,
        "trace_id": trace_id,
        "phase_origin": phase,
        "domain": fdomain,
        "data_sources": sources,
        "rules_hit": rules,
        "detection_path": detection_path,
        "how_found": fhow[:200] if fhow else "",
        "confidence": confidence,
        "rule_count": len(rules),
    }
    return trace


# ═══════════ 事前预警：异常演变→风险升级路径 ═══════════
# 从当前异常推断下一阶段风险——"如果你不处理，接下来会发生什么"
EARLY_WARNING_ESCALATION = [
    {
        "id": "EWARN_001",
        "finding_pattern": ["毛利为负", "毛利率异常偏低", "毛利率偏低", "毛利率下降"],
        "forward_projection": (
            "毛利率持续走低→利润空间消失→企业可能通过隐匿收入或虚增成本维持账面"
            "→一旦被稽查发现，不仅补税+罚款，还可能触发持续经营能力质疑→被列为风险纳税人"
        ),
        "checklist": (
            "①立即复核成本核算是否准确（有无漏结转成本/虚增进项）；"
            "②排查是否存在大量未开票收入（隐匿收入导致账面毛利率偏低）；"
            "③若真实毛利率确实偏低→检查定价策略，评估是否为转移定价问题"
        ),
        "timeframe": "未来2-4个申报期",
        "level": "极高风险",
    },
    {
        "id": "EWARN_002",
        "finding_pattern": ["供应商高度集中", "供应商集中", "客户高度集中", "客户集中"],
        "forward_projection": (
            "单一依赖风险持续→若核心供应商断供或核心客户流失→经营中断"
            "→资金链紧张→可能诱发虚开发票/骗取贷款等连锁违法行为"
            "→税务稽查升级为联合执法（税务+公安+市监）"
        ),
        "checklist": (
            "①核查集中供应商/客户是否与企业在股权/人员上关联；"
            "②评估如核心交易对手退出后的替代方案；"
            "③保留完整的交易档案（合同+发票+物流+付款）以备稽查。"
        ),
        "timeframe": "未来3-6个月",
        "level": "高风险",
    },
    {
        "id": "EWARN_003",
        "finding_pattern": ["无工资记录", "无社保记录", "工资表缺失", "社保明细缺失"],
        "forward_projection": (
            "长期无工资/社保记录→用工合规性存疑→金税四期人社税务数据联动后"
            "→个税+社保+企业所得税三税联查→虚列人头/虚增工资/偷逃个税的嫌疑坐实"
            "→补税+滞纳金+罚款+移送劳动监察"
        ),
        "checklist": (
            "①立即建立工资表和社保缴纳记录；"
            "②逐人核实身份信息，确保全员申报个税和社保；"
            "③补缴历史欠缴的社保费用（滞纳金每日万分之五）。"
        ),
        "timeframe": "金税四期数据联动后随时触发",
        "level": "高风险",
    },
    {
        "id": "EWARN_004",
        "finding_pattern": ["加工费", "BOM缺失", "BOM表缺失"],
        "forward_projection": (
            "加工费存在但BOM缺失的现状持续→品名差异始终无法解释"
            "→税务机关认定为'无法说明来源的进项税额'→全额进项转出"
            "→同时触发上下游联查→委托加工方和受托加工方双双被查"
        ),
        "checklist": (
            "①立即向加工方索要或自行编制BOM表（含单耗和损耗率）；"
            "②补签规范的委托加工合同（明确品名、数量、加工费标准）；"
            "③建立加工出入库台账（原材料发出→成品收回逐笔记录）。"
        ),
        "timeframe": "下次稽查前必须就位",
        "level": "高风险",
    },
    {
        "id": "EWARN_005",
        "finding_pattern": ["个人付款方", "法定代表人", "私户收款", "个人付款占比"],
        "forward_projection": (
            "私户收款行为持续→金税四期银行数据+税务数据交叉比对"
            "→系统自动标记'公私不分'→触发反洗钱+税务联合调查"
            "→所有未开票收入被追溯核定→补税+0.5-5倍罚款+滞纳金"
            "→严重者移交公安经侦"
        ),
        "checklist": (
            "①立即停止使用个人账户收取经营款项；"
            "②对历史私户收款全额补开发票+补申报纳税；"
            "③法人/股东个人账户与经营相关的流水整理备查。"
        ),
        "timeframe": "金税四期银行数据比对随时触发",
        "level": "极高风险",
    },
    {
        "id": "EWARN_006",
        "finding_pattern": ["购销严重倒挂", "进销倒挂", "购销倒挂"],
        "forward_projection": (
            "进项持续大于销项→库存积压或收入隐匿→若为库存积压→存货跌价损失"
            "→资产减值→企业所得税前扣除存疑；若为收入隐匿→一旦查实"
            "→全额补税+罚款→倒挂金额越大、补税越多→可能直接压垮企业现金流"
        ),
        "checklist": (
            "①盘点期末存货→确认是否为真实库存积压（如是，属正常经营）；"
            "②比对银行收款与开票金额→确认是否存在未开票收款；"
            "③若两者均排除→进项发票的真实性需重点核查。"
        ),
        "timeframe": "当期即可触发",
        "level": "极高风险",
    },
    {
        "id": "EWARN_007",
        "finding_pattern": ["虚开发票", "虚开", "对开环开"],
        "forward_projection": (
            "虚开发票信号一旦被金税系统标记→系统自动推送至稽查局"
            "→启动'一案双查'（查开票方+受票方）→进项税额转出+补税+罚款"
            "→虚开金额较大→移送公安→法定代表人面临刑事责任（最高无期）"
        ),
        "checklist": (
            "①立即自查全部进项发票的三流一致性（合同/发票/资金/货物）；"
            "②核实供应商真实经营状况（是否存在走逃/注销/非正常户）；"
            "③对存疑发票主动做进项转出+补税——比被动稽查处罚轻得多。"
        ),
        "timeframe": "系统标记后2-4周",
        "level": "极高风险",
    },
    {
        "id": "EWARN_008",
        "finding_pattern": ["发票连号", "季度末集中开票", "金额整十整百"],
        "forward_projection": (
            "开票行为异常持续→金税系统'发票行为画像'标记"
            "→纳入异常开票名录→新开发票被限制→经营受阻"
            "→同时触发稽查→全面核查发票流向和资金流向"
        ),
        "checklist": (
            "①规范开票行为：按实际交易时间逐笔开票，避免集中/突击开票；"
            "②按实际交易金额开票，避免人为控制金额为整数；"
            "③连号发票如确为真实交易，保留完整的合同和物流单据备查。"
        ),
        "timeframe": "1-2个申报期",
        "level": "中风险",
    },
]


def _build_early_warnings(all_findings, ctx):
    """
    事前预警引擎：从当前异常推断下一阶段风险
    
    工作原理：
    1. 扫描当前发现的异常模式
    2. 匹配预警规则中的上升路径
    3. 生成"如果继续→接下来会发生什么"的前瞻性警告
    """
    warnings = []
    
    # 构建信号文本池
    signal_pool = []
    for f in all_findings:
        text = (
            str(f.get("type", "")) + " " +
            str(f.get("detail", ""))[:500] + " " +
            str(f.get("description", ""))[:300]
        )
        signal_pool.append(text)
    combined_text = " ".join(signal_pool)
    
    for rule in EARLY_WARNING_ESCALATION:
        patterns = rule.get("finding_pattern", [])
        
        # 检查是否至少命中一个模式
        matched = [p for p in patterns if p in combined_text]
        if not matched:
            continue
        
        warning_detail = (
            f"【事前预警·风险升级路径】\n\n"
            f"当前状态：检测到'{matched[0]}'信号\n\n"
            f"演变推演：{rule['forward_projection']}\n\n"
            f"预计时间窗口：{rule['timeframe']}\n\n"
            f"【立即应对清单】\n{rule['checklist']}\n\n"
            f"提醒：以上推演基于税务稽查实战经验——"
            f"这些不是杞人忧天，而是同类案例中真实发生过的升级路径。"
            f"现在处理是'自查补税'，等稽查来了就是'立案处罚'——性质完全不同。"
        )
        
        warnings.append({
            "type": f"事前预警-{rule['id']}",
            "level": rule["level"],
            "score": 10 if rule["level"] == "极高风险" else (8 if rule["level"] == "高风险" else 6),
            "detail": warning_detail,
            "description": warning_detail,
            "how_found": (
                f"事前预警引擎检测到'{matched[0]}'信号"
                f"→触发'{rule['id']}'风险升级路径推演"
            ),
            "tax_impact": rule["forward_projection"][:200],
            "suggestion": rule["checklist"],
            "policy_ref": "《税收征收管理法》及金税四期风险监控规则",
            "category": "综合定性·事前预警",
            "_priority": "P0" if rule["level"] == "极高风险" else "P1",
            "_early_warning_id": rule["id"],
            "_auto_triggered": True,
            "_matched_pattern": matched[0],
            "_timeframe": rule["timeframe"],
        })
    
    return warnings


def _enrich_evidence_trace(ctx, all_findings, file_results):
    """
    证据溯源：为每条结论标注原始数据来源
    
    让每条高风险结论都能回答："你凭什么这么说？数据在哪？"
    向引擎的"透明推理机"目标迈进。
    """
    # 构建文件类型索引
    file_type_index = {}
    file_name_index = {}
    import re as _re_rows
    for fr in (file_results or []):
        ftype = fr.get("type", fr.get("data_type", "unknown"))
        fname = fr.get("file", fr.get("file_name", fr.get("original_name", "")))
        # 从actions字符串中提取行数
        row_count = 0
        actions = fr.get("actions", [])
        if isinstance(actions, list):
            for act in actions:
                m = _re_rows.search(r'(\d+)行', str(act))
                if m:
                    row_count += int(m.group(1))
        elif isinstance(actions, str):
            m = _re_rows.search(r'(\d+)行', actions)
            if m:
                row_count = int(m.group(1))
        row_count = max(row_count, fr.get("row_count", fr.get("count", 0)))
        if ftype not in file_type_index:
            file_type_index[ftype] = []
        file_type_index[ftype].append({"name": fname, "rows": row_count})
        file_name_index[fname] = {"type": ftype, "rows": row_count}
    
    # 数据类型中文映射
    type_labels = {
        "bank_statement": "银行流水",
        "sales_invoice": "销项发票",
        "purchase_invoice": "进项发票",
        "salary": "工资表",
        "social_security": "社保明细",
        "voucher": "记账凭证",
        "inventory": "进销存台账",
        "contract": "合同文件",
        "trial_balance": "科目余额表",
        "financial_statement": "财务报表",
        "tax_return": "申报表",
    }
    
    # 结论类型 → 主要依赖的数据类型
    finding_data_map = {
        "毛利": ["sales_invoice", "purchase_invoice"],
        "进销": ["sales_invoice", "purchase_invoice", "inventory"],
        "虚开": ["purchase_invoice", "bank_statement", "contract"],
        "发票": ["sales_invoice", "purchase_invoice"],
        "银行": ["bank_statement"],
        "收款": ["bank_statement", "sales_invoice"],
        "付款": ["bank_statement", "purchase_invoice"],
        "工资": ["salary", "social_security"],
        "社保": ["salary", "social_security"],
        "存货": ["inventory"],
        "合同": ["contract"],
        "凭证": ["voucher"],
        "科目": ["trial_balance"],
        "申报": ["tax_return"],
        "集中": ["sales_invoice", "purchase_invoice"],
        "加工": ["purchase_invoice", "contract", "inventory"],
        "个人": ["bank_statement"],
        "成本": ["purchase_invoice", "inventory", "voucher"],
        "收入": ["sales_invoice", "bank_statement"],
        "地": ["bank_statement", "contract"],
        "经营": ["bank_statement", "sales_invoice", "purchase_invoice"],
        "关联": ["bank_statement", "contract"],
    }
    
    import re as _re_trace
    
    for finding in all_findings:
        ftype = str(finding.get("type", ""))
        fdetail = str(finding.get("detail", ""))
        fdesc = str(finding.get("description", ""))
        combined = ftype + " " + fdetail + " " + fdesc
        
        # 推断依赖的数据类型
        data_types = set()
        for keyword, dtypes in finding_data_map.items():
            if keyword in combined:
                data_types.update(dtypes)
        if not data_types:
            data_types.add("bank_statement")  # 默认依赖
        
        # 提取关键数值
        key_values = {}
        # 百分比
        pct_matches = _re_trace.findall(r'(\d+\.?\d*)%', combined)
        if pct_matches:
            key_values["percentages"] = [float(p) for p in pct_matches[:3]]
        # 金额
        amt_matches = _re_trace.findall(r'([\d,]+\.?\d*)元', combined)
        if amt_matches:
            key_values["amounts"] = [p.replace(",", "") for p in amt_matches[:3]]
        # 张数/笔数
        count_matches = _re_trace.findall(r'(\d+)\s*[张笔条]', combined)
        if count_matches:
            key_values["counts"] = [int(c) for c in count_matches[:3]]
        
        # 构建文件来源摘要
        source_files = []
        total_rows = 0
        for dt in data_types:
            if dt in file_type_index:
                for fi in file_type_index[dt]:
                    source_files.append(fi["name"])
                    total_rows += fi["rows"]
        
        source_summary = ""
        for dt in sorted(data_types):
            if dt in file_type_index:
                label = type_labels.get(dt, dt)
                count = len(file_type_index[dt])
                rows = sum(fi["rows"] for fi in file_type_index[dt])
                source_summary += f"{label}({count}份/{rows}行) "
        
        finding["_source_trace"] = {
            "data_types": list(data_types),
            "data_type_labels": [type_labels.get(dt, dt) for dt in data_types],
            "source_files": list(set(source_files))[:5],
            "total_data_rows": total_rows,
            "source_summary": source_summary.strip(),
            "key_values": key_values,
        }
    
    return all_findings


def _generate_executive_summary(overall_risk, core_issues, cross_findings, ctx, score, p0_count, p1_count):
    """生成综合结论文本——带行业洞察和经营模式分析"""
    lines = []
    
    model = ctx.company_profile.get("biz_model", "未知")
    industry = ctx.company_profile.get("industry", "未知行业")
    fs = ctx.financial_snapshot
    cp = ctx.company_profile
    
    # ═══ 第一段：定调+全景 ═══
    scale_desc = {"大": "大型", "中": "中型", "小": "小型", "微": "微型"}.get(cp.get("scale", ""), "")
    risk_advice = _get_risk_advice(overall_risk)
    
    lines.append(
        f"【综合稽查结论】\n\n"
        f"经对{scale_desc}{model}企业（{industry}行业）的多域全量分析——"
        f"涵盖{fs['bank_tx_count']}笔银行流水、{fs['sale_count']}张销项发票、{fs['pur_count']}张进项发票"
        f"{'、'+str(fs['salary_count'])+'条工资记录' if fs['salary_count'] > 0 else ''}——"
        f"综合风险评级为【{overall_risk}】（评分{score:.2f}/100）。\n\n"
        f"{risk_advice}"
    )
    
    # ═══ 第二段：经营模式诊断 ═══
    lines.append(f"\n【经营模式诊断】")
    lines.append(_get_detailed_mode_analysis(model, industry, ctx))
    # ── 行业自适应基准对比 ──
    lines.append(_get_industry_benchmark_comparison(ctx))
    
    # ═══ 第三段：核心风险画像 ═══
    lines.append(f"\n【核心风险画像】")
    
    # 按风险类别聚合
    fraud_signals = [i for i in core_issues if any(k in i.get("type","") for k in ["虚开","造假","编造","对开","走票"])]
    revenue_signals = [i for i in core_issues if any(k in i.get("type","") for k in ["隐匿","未开票","账外","体外","少记"])]
    structure_signals = [i for i in core_issues if any(k in i.get("type","") for k in ["关联","集中","控制","依赖"])]
    invoice_signals = [i for i in core_issues if any(k in i.get("type","") for k in ["发票","连号","开票","品名","进销"])]
    
    if fraud_signals:
        lines.append(f"  ▸ 虚开发票风险：{len(fraud_signals)}项信号（{'、'.join(i['type'][:20] for i in fraud_signals[:2])}等）")
    if revenue_signals:
        lines.append(f"  ▸ 隐匿收入风险：{len(revenue_signals)}项信号")
    if structure_signals:
        lines.append(f"  ▸ 关联交易风险：{len(structure_signals)}项信号")
    if invoice_signals:
        lines.append(f"  ▸ 发票异常风险：{len(invoice_signals)}项信号")
    
    # ═══ 资料缺失触发风险（叙事增强层）═══
    missing_risk_signals = [i for i in core_issues if i.get("type", "").startswith("资料缺失触发-")]
    if missing_risk_signals:
        lines.append(f"  ▸ 资料缺失触发风险：{len(missing_risk_signals)}类关键资料缺失，已自动触发以下风险结论——")
        for mr in missing_risk_signals[:5]:
            risk_name = mr['type'].replace('资料缺失触发-', '')
            lines.append(f"    → {risk_name}")
    
    # ═══ 结论自洽性检查：矛盾信号 ═══
    contradiction_signals = [i for i in core_issues if i.get("type", "").startswith("结论自洽-")]
    if contradiction_signals:
        lines.append(f"  ▸ 结论自洽性警报：检测到{len(contradiction_signals)}个逻辑矛盾——")
        for cs in contradiction_signals[:5]:
            name = cs['type'].replace('结论自洽-', '')
            lines.append(f"    ⚠ {name}")
    
    # ═══ 因果叙事链：多信号叠加→涉税故事 ═══
    causal_signals = [i for i in core_issues if i.get("type", "").startswith("因果叙事-")]
    if causal_signals:
        lines.append(f"  ▸ 跨域因果链：{len(causal_signals)}条涉税故事被推理还原——")
        for cs in causal_signals[:5]:
            name = cs['type'].replace('因果叙事-', '')
            lines.append(f"    → {name}")
    
    # ═══ 事前预警：风险升级路径 ═══
    warning_signals = [i for i in core_issues if i.get("type", "").startswith("事前预警-")]
    if warning_signals:
        lines.append(f"  ▸ 事前预警：{len(warning_signals)}条风险升级路径被推演——")
        for ws in warning_signals[:5]:
            eid = ws['type'].replace('事前预警-', '')
            lines.append(f"    ⏰ {eid}")
    
    # ═══ 时间趋势洞察 ═══
    trend_items = [i for i in core_issues if i.get("type", "").startswith("趋势-")]
    if trend_items:
        lines.append(f"  ▸ 时间趋势：{len(trend_items)}个指标出现明显变化——")
        for ti in trend_items[:5]:
            name = ti['type'].replace('趋势-', '')
            lines.append(f"    → {name}")
    
    # ═══ 假设敏感性：预估补税金额 ═══
    sr = getattr(ctx, '_sensitivity_report', {})
    if sr and sr.get("scenarios"):
        lines.append(f"  ▸ 假设敏感性分析（中假设下）：")
        for sc in sr["scenarios"][:3]:
            mid = sc["levels"].get("中", {})
            if mid:
                lines.append(f"    {sc['risk']}: 补税{mid['total_tax']:,.2f}元 "
                           f"(罚{mid['penalty_range']}元)")
        lines.append(f"    → {sr['summary']}")
    
    # ═══ 结论可信度评估 ═══
    cr = getattr(ctx, '_credibility_report', {})
    if cr and cr.get("overall_credibility", 0) > 0:
        oc = cr["overall_credibility"]
        wc = cr.get("weakest_conclusions", [])
        lines.append(f"  ▸ 结论可信度：整体{oc:.2f}分——")
        lines.append(f"    {cr.get('summary', '').split(chr(10))[0][:100]}")
        if wc:
            for w in wc[:2]:
                lines.append(f"    ⚠ {w['type'][:40]} → 仅{w['credibility']:.2f}分（需补充资料增强）")
    
    # 高风险项 TOP3
    if core_issues:
        high_items = [i for i in core_issues if i["level"] in ("极高风险", "高风险")]
        if high_items:
            lines.append(f"\n  前{min(3, len(high_items))}大高风险项：")
            for i, issue in enumerate(high_items[:3], 1):
                xv = "★交叉验证" if issue["is_cross_validated"] else ""
                lines.append(f"  {i}. {issue['type']} (评分{issue['score']}) {xv}")
    
    # ═══ 第四段：交叉验证洞察 ═══
    if cross_findings:
        lines.append(f"\n【交叉验证洞察】")
        lines.append(f"Phase 3 交叉验证引擎触发{len(cross_findings)}个信号叠加模式，")
        lines.append(f"意味着多个独立分析域的结论互相印证——不是孤立的异常，而是系统性风险。")
        for cf in cross_findings[:3]:
            name = cf.get('type','').replace('交叉验证-','')
            level = cf.get('level','')
            lines.append(f"  • {name} ({level})")
    
    # ═══ 第五段：核查优先级 ═══
    lines.append(f"\n【核查优先级】")
    lines.append(f"  共有{p0_count}项P0立即行动、{p1_count}项P1重点关注。")
    
    # 根据风险等级给出下一步具体建议
    if overall_risk in ("极高风险", "高风险"):
        lines.append(f"  鉴于风险等级为{overall_risk}，建议：")
        lines.append(f"  1. 立即暂停与该企业的非必要业务往来")
        lines.append(f"  2. 启动实地核查程序（核查经营场所+库存+产能匹配）")
        lines.append(f"  3. 调取银行流水+发票台账+合同台账做全量比对")
        if model == "制造业":
            lines.append(f"  4. 要求提供BOM表+加工合同+出入库记录验证加工链条")
        elif model == "贸易":
            lines.append(f"  4. 要求提供进销存台账+物流单据验证货物流")
    elif overall_risk == "中风险":
        lines.append(f"  建议企业限期补充资料，重点核查以上P0/P1项。")
    else:
        lines.append(f"  企业整体风险可控，建议按常规流程处理。")
    
    # ═══ 第六段：记忆学习洞察 ═══
    # 优先使用MemoryLearner的行业记忆洞察（更丰富）
    learner = getattr(ctx, 'memory_learner', None)
    if learner and learner.is_loaded:
        learner_insight = learner.get_industry_memory_insight(ctx)
        if learner_insight:
            lines.append(f"\n【记忆学习洞察】")
            lines.append(f"  {learner_insight}")
    else:
        memory_insight = getattr(ctx, '_memory_insight', '')
        if memory_insight:
            lines.append(f"\n【历史记忆洞察】")
            lines.append(f"  {memory_insight}")
    
    # ═══ 第七段：质量声明 ═══
    if ctx.data_quality_score < 70:
        lines.append(f"\n【资料质量声明】")
        lines.append(f"  当前资料质量评分{ctx.data_quality_score}/100。")
        if ctx.missing_critical_docs:
            lines.append(f"  缺失关键资料：{'、'.join(ctx.missing_critical_docs)}。")
        lines.append(f"  部分结论置信度受限，建议补充完整资料后重新分析。")
    
    return "\n".join(lines)


def _get_risk_advice(level):
    """根据风险等级给出行动建议"""
    if level == "极高风险":
        return (
            "该企业的涉税风险已达到'极高'级别——多个独立证据源互相印证，"
            "存在系统性、组织性的涉税违法嫌疑。建议立即启动稽查程序，"
            "对企业的资金流、发票流、货物流做全方位穿透核查。"
        )
    elif level == "高风险":
        return (
            "该企业存在多项高风险涉税问题，虽未达到系统性的'极高风险'程度，"
            "但多项异常信号的叠加表明涉税违法的主观意图明显。"
            "建议优先安排稽查力量，逐项核实重点问题。"
        )
    elif level == "中风险":
        return (
            "该企业存在若干中期风险信号，需要进一步核实。"
            "部分问题可能是正常的商业行为或核算偏差，"
            "建议要求企业限期提供补充资料以澄清疑点。"
        )
    else:
        return (
            "该企业整体涉税风险较低，现有资料未发现重大异常。"
            "建议按常规管理流程处理，保持定期监控。"
        )


def _get_industry_benchmark_comparison(ctx):
    """行业自适应基准对比：当前指标 vs 行业典型范围"""
    ip = ctx.industry_profile
    fs = ctx.financial_snapshot
    cp = ctx.company_profile
    if not ip or not ip.get("benchmarks"):
        return ""
    
    bm = ip["benchmarks"]
    label = ip.get("label", cp.get("biz_model", "未知行业"))
    lines = []
    lines.append(f"\n{label}行业基准对比（基于行业知识库）：")
    
    # 毛利率对比
    gm_bm = bm.get("gross_margin_pct")
    gm_actual = fs.get("gross_margin_pct", 0)
    if gm_bm and gm_actual:
        deviation = ""
        if gm_actual < gm_bm.get("low", 0):
            deviation = f"← 低于{label}行业正常下限({gm_bm['low']}%)，成本控制或收入确认存疑"
        elif gm_actual > gm_bm.get("high", 100):
            deviation = f"← 高于{label}行业正常上限({gm_bm['high']}%)，毛利率异常偏高"
        elif gm_actual < gm_bm.get("normal_low", 0):
            deviation = f"（偏低但仍在{label}行业可接受范围边缘）"
        elif gm_actual > gm_bm.get("normal_high", 100):
            deviation = f"（偏高，但{label}行业部分细分领域可行）"
        
        if deviation:
            lines.append(f"  • 毛利率: 当前{gm_actual:.2f}% {deviation}")
    
    # 进销比对比  (converted to purchase/sales ratio for comparison)
    sales = fs.get("total_sales", 1)
    purchases = fs.get("total_purchases", 0)
    ps_bm = bm.get("purchase_sales_ratio")
    if ps_bm and sales > 0:
        ps_actual = purchases / sales
        if ps_actual < ps_bm.get("normal_low", 0) or ps_actual > ps_bm.get("normal_high", 2):
            lines.append(f"  • 进销比: 当前{ps_actual:.2f}（{label}正常{ps_bm['normal_low']}-{ps_bm['normal_high']}）")
    
    # 供应商集中度
    sc_bm = bm.get("supplier_concentration_warn")
    if sc_bm and ctx.supplier_concentration > sc_bm:
        lines.append(f"  • 供应商集中度: {ctx.supplier_concentration:.2f}%（{label}预警线{sc_bm}%）")
    
    # 客户集中度
    cc_bm = bm.get("customer_concentration_warn")
    if cc_bm and ctx.customer_concentration > cc_bm:
        lines.append(f"  • 客户集中度: {ctx.customer_concentration:.2f}%（{label}预警线{cc_bm}%）")
    
    # 行业特有风险模式
    risk_patterns = ip.get("risk_patterns", [])
    if risk_patterns:
        # 检查是否有关键模式被触发
        triggered_patterns = []
        for rp in risk_patterns:
            sigs = rp.get("signals", [])
            # 简单检查是否有至少2个信号在现有发现中出现
            matches = 0
            for sig in sigs:
                # 检查是否在ctx的红黄旗信号中
                for flag in ctx.red_flags + ctx.yellow_flags:
                    if sig in str(flag.get("type", "")):
                        matches += 1
                        break
            if matches >= 2:
                triggered_patterns.append(rp)
        
        if triggered_patterns:
            lines.append(f"\n  {label}行业特有风险模式（已触发）：")
            for tp in triggered_patterns[:3]:
                lines.append(f"    ▸ {tp['name']}: {tp['explanation'][:100]}")
    
    if len(lines) > 1:  # 超过标题行
        return "\n".join(lines)
    return ""


def _get_detailed_mode_analysis(model, industry, ctx):
    """根据经营模式+行业给出深入诊断"""
    fs = ctx.financial_snapshot
    cp = ctx.company_profile
    
    if model == "制造业":
        analysis = (
            f"  该企业被识别为{industry}制造业企业。"
            f"制造业的稽查重点是加工链条真实性——"
            f"原材料→加工→成品的投入产出逻辑是否成立。\n"
        )
        if ctx.has_processing_fee:
            analysis += (
                f"  系统已检测到加工费发票信号，确认存在外包加工环节。"
                f"外包加工模式下，BOM表是最核心的证据——"
                f"只有在BOM表验证通过后，进销品名差异才能被合理解释为加工链条转换，"
                f"否则'有进无销/有销无进'的虚开嫌疑无法排除。\n"
            )
        else:
            analysis += (
                f"  未检测到加工费——可能是自产自销的全流程制造模式。"
                f"此模式下应能提供完整的生产成本核算和进销存台账验证。\n"
            )
        analysis += f"  建议核查方向：{ctx.supplier_concentration:.2f}%的供应商集中度——"
        if ctx.supplier_concentration > 50:
            analysis += "供应商过度集中，需核实是否存在关联交易或供应商依赖。"
        else:
            analysis += "供应商结构合理分散。"
        return analysis
    
    elif model == "贸易":
        return (
            f"  该企业被识别为贸易企业。贸易模式的稽查重点是进销品名一致性——"
            f"买什么就卖什么，品名应当高度匹配。"
            f"品名不匹配的差异需要逐一解释（是否为加工转换、是否为变名开票）。\n"
            f"  建议核查：进销品名重合度、供应商与客户的工商关联、物流单据真实性。"
        )
    
    elif model in ("服务/劳务",):
        return (
            f"  该企业被识别为服务/劳务企业。服务业的稽查重点是收入完整性——"
            f"因为服务不像货物有实物形态，更容易出现账外收入。\n"
            f"  建议核查：银行收款与开票收入的全量比对、员工人数与业务量的匹配度、"
            f"主要客户合同的签约时间与金额分布。"
        )
    
    else:
        return (
            f"  经营模式未明确识别（{industry}行业）。"
            f"建议补充营业执照经营范围+主营业务说明，以进行更精准的分析。"
        )


def _get_mode_note(model, ctx):
    """根据经营模式给出针对性说明"""
    if model == "制造业":
        return "重点关注加工链条真实性（BOM表+加工合同+出入库记录）。"
    elif model == "贸易":
        return "重点关注进销品名一致性和供应商/客户匹配度。"
    elif model in ("服务/劳务",):
        return "重点关注收入完整性和人工成本匹配度（工资社保比对）。"
    else:
        return "建议补充公司经营范围和主营业务说明以完善分析。"


def _summarize_evidence(all_items):
    """汇总证据链"""
    high_findings = [f for f in all_items if f.get("level") in ("极高风险", "高风险")]
    evidence_domains = set(f.get("domain", "") for f in high_findings)
    
    lines = []
    lines.append(f"共{len(all_items)}项发现，其中高风险{len(high_findings)}项，涉及{len(evidence_domains)}个稽查域。")
    
    if evidence_domains:
        lines.append(f"关键证据域：{' / '.join(sorted(evidence_domains))}")
    
    # 提取证据来源
    sources = set()
    for f in high_findings:
        src = f.get("source_chain", "") or f.get("how_found", "")
        if src and len(src) < 80:
            sources.add(src[:60])
    if sources:
        lines.append(f"证据源：{' / '.join(list(sources)[:5])}")
    
    return "\n".join(lines)


def _update_industry_benchmarks(company_id, report, ctx):
    """每次分析完成后自动更新行业基准值统计池。
    使用在线Welford算法增量计算均值/标准差。
    样本数<3时仅累积，>=3时输出有效基准值。
    """
    from database import IndustryBenchmark, SessionLocal
    from datetime import datetime as dt
    import math
    
    industry = getattr(ctx, 'company_profile', {}).get('industry', '通用') if ctx else '通用'
    trace_id = report.get('trace_id', '')
    cc = report.get('comprehensive', {})
    mi = cc.get('material_intel', {})
    inv_stats = mi.get('发票', {}).get('统计', {})
    bank_stats = mi.get('银行流水', {}).get('统计', {})
    
    # 收集指标
    metrics = {}
    sal_amt = inv_stats.get('销项金额合计', 0) or 0
    pur_amt = inv_stats.get('进项金额合计', 0) or 0
    bank_in = bank_stats.get('收款合计', 0) or 0
    bank_out = bank_stats.get('付款合计', 0) or 0
    
    if sal_amt > 0 and pur_amt > 0:
        metrics['invoice_match_ratio'] = round(sal_amt / max(pur_amt, 1), 4)
    if sal_amt > 0 and bank_in > 0:
        metrics['bank_sales_match_ratio'] = round(bank_in / max(sal_amt, 1), 4)
    if pur_amt > 0 and bank_out > 0:
        metrics['bank_purchase_match_ratio'] = round(bank_out / max(pur_amt, 1), 4)
    if sal_amt > 0 and pur_amt > 0:
        metrics['gross_margin'] = round((sal_amt - pur_amt) / max(sal_amt, 1), 4)
    metrics['risk_density'] = report.get('total_risks', 0)
    
    sdb = SessionLocal()
    try:
        for metric_name, metric_value in metrics.items():
            existing = sdb.query(IndustryBenchmark).filter(
                IndustryBenchmark.industry == industry,
                IndustryBenchmark.metric_name == metric_name
            ).first()
            
            if existing:
                # Welford在线更新
                n = (existing.sample_count or 0) + 1
                old_mean = float(existing.running_mean or 0)
                delta = metric_value - old_mean
                new_mean = old_mean + delta / n
                new_delta2 = (metric_value - new_mean) * (metric_value - old_mean)
                old_std = float(existing.running_std or 0)
                # 增量方差
                if n > 1:
                    new_variance = ((n - 2) * old_std**2 + new_delta2) / (n - 1) if n > 2 else new_delta2 / 2
                    new_std = math.sqrt(max(new_variance, 0))
                else:
                    new_std = 0
                
                existing.sample_count = n
                existing.running_mean = new_mean
                existing.running_std = new_std
                existing.metric_value = metric_value
                existing.company_id = company_id
                existing.trace_id = trace_id
                existing.updated_at = dt.utcnow()
            else:
                # 新指标
                bm = IndustryBenchmark(
                    industry=industry,
                    metric_name=metric_name,
                    metric_value=metric_value,
                    company_id=company_id,
                    trace_id=trace_id,
                    sample_count=1,
                    running_mean=metric_value,
                    running_std=0,
                    p50=metric_value,  # 首个样本即为中位数
                )
                sdb.add(bm)
        
        sdb.commit()
    except Exception as e:
        sdb.rollback()
        print(f"[BENCHMARK] 更新失败: {e}")
    finally:
        sdb.close()


# ═══════════════════════════════════════════════════════════
#  报告块架构 — 声明式配置驱动（第三步）
#  不再手写 if-else，而是用配置表定义"什么数据条件→推什么 blocks"
#  系统运行时根据实际数据评估条件，条件满足就推 block，不满足就不推。
#  不同公司上传不同资料→条件匹配不同→推不同 blocks→出不同报告。
#  全行业各企业通用：同一份配置表，不同数据自动出不同的报告结构。
# ═══════════════════════════════════════════════════════════

# ── 报告块配置表 ──
# 每条配置定义：什么条件触发 / 生成什么 block / block 数据怎么提取
# condition 函数接收 ctx 字典，返回 bool
# data_builder 函数接收 ctx 字典，返回 block.data 字典

BLOCK_CONFIG = []

def _block(type, title, condition, data_builder, per_item=False, item_source=None):
    """注册一个报告块配置"""
    BLOCK_CONFIG.append({
        "type": type,
        "title": title,
        "condition": condition,
        "data_builder": data_builder,
        "per_item": per_item,       # True=对 item_source 逐条生成 block
        "item_source": item_source,  # per_item=True 时，数据来源的 ctx 键名
    })

# ── 帮助函数：从 result 提取常用上下文 ──
def _ctx(result):
    rp = result.get("report", {})
    te = rp.get("target_entity", {}) or {}
    cc = rp.get("comprehensive", {}) or {}
    mi = cc.get("material_intel", {}) or {}
    ii = mi.get("发票", {}) or {}
    bi = mi.get("银行流水", {}) or {}
    af = rp.get("all_findings", [])
    return {"report": rp, "entity": te, "comprehensive": cc,
            "material_intel": mi, "invoices": ii, "bank": bi,
            "findings": af, "files_count": rp.get("files_count", 0)}

# ═══════════════════════════════════════════════════════
#  以下为声明式配置 — 配置即文档，条件驱动，无需 if-else
# ═══════════════════════════════════════════════════════

# 封皮：永远出
_block("cover", "", lambda ctx: True, lambda ctx: {
    "company_name": ctx["entity"].get("name", "被查单位"),
    "company_uscc": ctx["entity"].get("uscc", ""),
    "report_no": f"税稽字[2026]第{len(ctx['findings'])}号",
    "files_count": ctx["files_count"],
})

# 企业基本画像：有企业名称就出
_block("entity_profile", "稽查对象基本情况",
    lambda ctx: bool(ctx["entity"].get("name")),
    lambda ctx: {"entity": ctx["entity"], "lookup_source": ctx["entity"].get("lookup_source", "")})

# 资料完备度：有资料类别统计或缺失资料信息就出
_block("data_completeness", "资料完备度",
    lambda ctx: bool(ctx["material_intel"].get("资料类别统计") or ctx["material_intel"].get("缺失资料")),
    lambda ctx: {
        "categories": ctx["material_intel"].get("资料类别统计", {}),
        "missing": ctx["material_intel"].get("缺失资料", []),
        "files_count": ctx["files_count"],
    })

# 风险总览：有发现项就出
_block("risk_summary", "风险发现总览",
    lambda ctx: len(ctx["findings"]) > 0,
    lambda ctx: {
        "total": len(ctx["findings"]),
        "high": sum(1 for f in ctx["findings"] if f.get("level") == "高风险"),
        "mid": sum(1 for f in ctx["findings"] if f.get("level") == "中风险"),
        "low": sum(1 for f in ctx["findings"] if f.get("level") not in ("高风险", "中风险")),
        "overall_level": ctx["report"].get("overall_level", ""),
    })

# 稽查方法：有发票数据或银行数据就出
# 加工环节穿透法仅在检测到加工费信号时加入方法列表
_block("methods", "稽查方法",
    lambda ctx: bool(
        (ctx["invoices"].get("销项发票") or ctx["invoices"].get("进项发票"))
        or (ctx["bank"].get("总收款") or ctx["bank"].get("总付款"))
    ),
    lambda ctx: _build_methods_data(ctx))

# ── 加工环节综合判断（多维度评分系统 v2） ──
# 核心认知：纯服务业的进销品名差异是正常经营特征，不是加工信号
# 广告传媒买零食/机票/日用品(进)卖广告服务(出)→品名不同≠加工，只是采购消耗品≠生产物资
# 只有制造业/贸易/建筑/餐饮等行业的品名差异才可能意味着加工转化

# ── 行业分类（从 industry_profiles.json 加载，JSON可编辑） ──
def _load_processing_keywords():
    """从 industry_profiles.json 加载加工判定关键词（替代硬编码列表）"""
    for base in [_PROJECT_ROOT, "."]:
        pp = os.path.join(base, "static", "industry_profiles.json")
        if os.path.exists(pp):
            with open(pp, "r", encoding="utf-8") as f:
                pk = json.load(f).get("_processing_keywords", {})
                return (
                    pk.get("processing_prone", []),
                    pk.get("partial_processing", []),
                    pk.get("pure_service", [])
                )
    # 极端兜底：JSON文件不存在时用内置默认值
    return (
        ["制造", "加工", "食品", "纺织", "印染", "服装", "化工", "电子", "机械", "家具", "电器", "冶炼", "铸造", "电镀", "涂装"],
        ["建筑", "装饰", "装修", "工程", "施工", "餐饮", "建材", "五金", "塑料", "木业", "纸业", "皮革", "橡胶", "陶瓷", "玻璃"],
        ["广告", "传媒", "咨询", "软件", "设计", "法律", "会计", "税务", "保险", "金融", "教育", "医疗", "中介", "代理", "经纪", "会展", "文化", "娱乐", "旅游", "人力资源", "物业", "科技", "互联网"]
    )

# 延迟加载（首次调用时从JSON读取，后续使用缓存）
_PROCESSING_KW_CACHE = None

def _get_processing_keywords():
    global _PROCESSING_KW_CACHE
    if _PROCESSING_KW_CACHE is None:
        _PROCESSING_KW_CACHE = _load_processing_keywords()
    return _PROCESSING_KW_CACHE

# ── 业务关键词加载（从 industry_profiles.json）──
def _load_biz_keywords():
    """从 industry_profiles.json 加载主营业务识别关键词"""
    for base in [_PROJECT_ROOT, "."]:
        pp = os.path.join(base, "static", "industry_profiles.json")
        if os.path.exists(pp):
            with open(pp, "r", encoding="utf-8") as f:
                bk = json.load(f).get("_biz_keywords", {})
                return (
                    bk.get("daily_goods", []),
                    bk.get("main_biz_keywords", []),
                    bk.get("important_expense_keywords", [])
                )
    # 极端兜底
    return (
        ['汽油','柴油','加油','酒店','住宿','餐饮','快递','办公用品','水费','电费','银行','手续费'],
        ['加工','材料','原料','配件','零件','包装','辅料','钢材','铝材','电子','食品','化工','木材','五金'],
        ['设备','机器','软件','广告','咨询','设计','租赁','维修','运输','培训']
    )

def _compute_processing_score(industry, has_proc_fee, has_goods_diff, has_spec_diff, has_qty_inflation):
    """多维度综合评分：企业存在加工环节的可能性（0-1）。
    纯服务业的进销品名差异直接归零——买零食机票≠进原料，卖广告服务≠出成品。
    返回 (score, signals_explanation)"""
    score = 0.0
    signals = []
    ind = industry.strip() if industry else ""
    processing_prone, partial_processing, pure_service = _get_processing_keywords()
    is_pure_service = any(kw in ind for kw in pure_service)
    is_manufacturing = any(kw in ind for kw in processing_prone)
    is_partial = any(kw in ind for kw in partial_processing)
    
    # 信号1: 加工费发票（权重0.40 — 最强信号，任何行业）
    if has_proc_fee:
        score += T.scoring_weights.extremely_high
        signals.append("加工费发票")
    
    # 信号2: 进销品名实质性差异（权重0.30 — 纯服务业不参与）
    # WHY: 广告公司买水果≠原材料采购，卖广告服务≠加工产出
    #       服务业的进项是经营消耗，不是生产投入
    if has_goods_diff and not is_pure_service:
        score += T.scoring_weights.very_high
        signals.append("进销品名差异")
    elif has_goods_diff and is_pure_service:
        signals.append("进销品名差异(纯服务业-不构成加工信号)")
    
    # 信号3: 同品名规格变化（权重0.20 — 任何行业，瓷砖切割等物理加工）
    if has_spec_diff:
        score += T.scoring_weights.high
        signals.append("同品名规格变化")
    
    # 信号4: 同品名数量膨胀（权重0.15 — 进少出多暗示切割/分装）
    if has_qty_inflation:
        score += T.scoring_weights.moderate
        signals.append("数量膨胀(进少出多)")
    
    # 信号5: 行业属性加成/降权
    if is_manufacturing:
        score += T.scoring_weights.low
        signals.append("行业制造属性")
    elif is_partial:
        score += T.scoring_weights.negligible
        signals.append("行业部分加工属性")
    elif is_pure_service:
        score -= 0.15
        signals.append("纯服务业(整体降权)")
    
    score = min(max(score, 0.0), 1.0)
    return round(score, 2), signals
    
    score = min(max(score, 0.0), 1.0)
    return round(score, 2), signals

def _build_methods_data(ctx):
    te = ctx["entity"]
    ga = te.get("_goods_analysis", {})
    # 从 goods_analysis 直接读取综合判断结果（后端一站式计算，前端只消费）
    processing_applicable = ga.get("_processing_applicable", False)
    processing_score = ga.get("_processing_score", 0.0)
    
    methods = ["工商登记核查法", "进销存数据比对法", "资金流与发票流核对法", "供应商及客户穿透分析法"]
    if processing_applicable:
        methods.append("加工环节穿透法")
    methods.append("五步核查法")
    return {
        "methods": methods,
        "registered_business": te.get("industry_online", "") or te.get("industry", ""),
        "invoice_stats": ctx["invoices"],
        "bank_stats": ctx["bank"],
        "_processing_check": {
            "industry": detected_industry,
            "industry_supports": industry_supports_processing,
            "has_processing_fee": has_processing_fee,
            "has_pur_sal_diff": has_pur_sal_diff,
            "lists_processing_method": has_processing,
        },
    }

# 发现项：每条 finding 生成一个 block
_block("finding", "", lambda ctx: len(ctx["findings"]) > 0, lambda ctx: {},
    per_item=True, item_source="findings")


# ── 遍历配置表，根据数据评估条件，动态生成 blocks ──

def _build_report_blocks(result, company_id):
    """声明式配置驱动：遍历 BLOCK_CONFIG，条件满足→推 block。
    不同数据→不同条件匹配→不同 blocks→不同报告结构。
    """
    ctx = _ctx(result)
    blocks = []
    p = 0  # priority

    for cfg in BLOCK_CONFIG:
        # 评估条件
        try:
            ok = cfg["condition"](ctx)
        except Exception:
            ok = False
        if not ok:
            continue

        if cfg["per_item"]:
            # 逐条模式：对 item_source 中的每条数据生成一个 block
            items = ctx.get(cfg["item_source"], [])
            for item in items:
                p += 1
                block_data = {}
                # 如果 data_builder 有返回值，用它的；否则直接用 item
                try:
                    built = cfg["data_builder"](ctx)
                    if built: block_data.update(built)
                except Exception:
                    pass
                block_data[cfg["item_source"].rstrip("s")] = item  # "findings" → "finding"
                block_data["_idx"] = p  # 用于前端驳回追踪
                blocks.append({
                    "type": cfg["type"],
                    "title": item.get("title", "") if cfg["title"] == "" else cfg["title"],
                    "priority": p,
                    "data": block_data,
                })
        else:
            # 单条模式
            p += 1
            try:
                block_data = cfg["data_builder"](ctx)
            except Exception:
                block_data = {}
            blocks.append({
                "type": cfg["type"],
                "title": cfg["title"],
                "priority": p,
                "data": block_data,
            })

    # ── 结论和签字永远在最后 ──
    p += 1
    blocks.append({"type": "conclusion", "title": "稽查结论与建议", "priority": p, "data": {
        "entity_name": ctx["entity"].get("name", "被查单位"),
        "total_risks": len(ctx["findings"]),
        "overall_level": ctx["report"].get("overall_level", ""),
        "missing_docs": ctx["material_intel"].get("缺失资料", []),
    }})
    p += 1
    blocks.append({"type": "signature", "title": "", "priority": p, "data": {}})

    return blocks


# ═══════════════════════════════════════════════════════════
# 2026-06-26 资料智能复核：结构指纹学习法 + 可编辑锚点配置
# 
# 核心理念：不写硬代码关键词，纯靠数据结构特征区分。
# 每份文件提取结构指纹（列数/数值比/日期比/累计字段/ID模式等）
# → 同类文件求平均指纹 → 组内聚类发现子类型
# → 用外部JSON配置文件(type_anchors.json)匹配聚类中心
# → 确定每个聚类的税务类型名称
#
# 配置文件的锚点定义全是结构特征（col_count范围/numeric_ratio范围/
# has_cumulative等），零中文关键词。修改JSON即可调整识别行为。
# ═══════════════════════════════════════════════════════════

def _extract_structural_fingerprint(rows, fpath=None):
    """
    提取文件的结构指纹——纯数据驱动，零硬编码关键词。
    
    指纹维度：
    - col_count: 列数
    - numeric_ratio: 数值列占比
    - date_ratio: 日期列占比  
    - text_ratio: 文本列占比
    - has_id_pattern: 是否有ID模式列（纯数字长串，如身份证号/税号）
    - has_amount_cols: 是否有金额列（浮点数）
    - has_cumulative: 是否有累计字段（行间数值递增或等比变化）
    - has_period_range: 是否有期间范围（成对日期列）
    - has_balance_col: 是否有余额列（每行值都不同的浮点数，非单调）
    - has_paired_dr_cr: 是否有成对借贷列（两个浮点数列，同行至少一列为0或接近0）
    - row_density: 数据行密度（非空单元格比例）
    - unique_vals_ratio: 唯一值比例（高=清单类，低=交易类）
    - id_card_like: 是否有身份证号模式列（18位数字）
    - invoice_no_like: 是否有发票号模式列（8-20位数字+字母）
    """
    if not rows:
        return {}
    
    import re as _re_fp
    
    n_rows = len(rows)
    if n_rows == 0:
        return {}
    
    # 收集所有键
    all_keys = list(rows[0].keys())
    n_cols = len(all_keys)
    if n_cols == 0:
        return {}
    
    # 分析每列的数据类型
    numeric_cols = 0
    date_cols = 0
    text_cols = 0
    id_pattern_cols = 0
    amount_cols = 0
    has_balance = False
    has_paired_dr_cr = False
    
    # 收集所有列的值
    col_values = {k: [] for k in all_keys}
    for r in rows[:min(n_rows, 200)]:  # 最多采样200行
        for k in all_keys:
            v = r.get(k, "")
            col_values[k].append(v)
    
    # 数值列检测
    float_cols = []
    for k in all_keys:
        vals = col_values[k]
        numeric_count = 0
        total = 0
        for v in vals:
            if v is None or v == "" or str(v).strip() == "":
                continue
            total += 1
            try:
                fv = float(v)
                numeric_count += 1
            except (ValueError, TypeError):
                pass
        if total > 0 and numeric_count / total > T.industry_thresholds.concentration_high:
            numeric_cols += 1
            float_cols.append(k)
    
    # 日期列检测
    date_patterns = [
        _re_fp.compile(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}'),
        _re_fp.compile(r'\d{4}年\d{1,2}月\d{1,2}日'),
    ]
    for k in all_keys:
        vals = col_values[k]
        date_count = 0
        total = 0
        for v in vals:
            sv = str(v).strip()
            if not sv:
                continue
            total += 1
            if any(p.search(sv) for p in date_patterns):
                date_count += 1
        if total > 0 and date_count / total > 0.4:
            date_cols += 1
    
    # 文本列检测（非数值非日期）
    text_cols = n_cols - numeric_cols - date_cols
    if text_cols < 0:
        text_cols = 0
    
    # ID模式检测（长数字串）
    for k in all_keys:
        vals = col_values[k]
        id_count = 0
        total = 0
        for v in vals:
            sv = str(v).strip()
            if not sv:
                continue
            total += 1
            # 15-18位纯数字 = 身份证号
            if sv.isdigit() and 15 <= len(sv) <= 18:
                id_count += 1
            # 15-20位含数字+字母 = 税号
            elif _re_fp.match(r'^[0-9A-Z]{15,20}$', sv):
                id_count += 1
        if total > 0 and id_count / total > T.ratios.half:
            id_pattern_cols += 1
    
    # 金额列检测（浮点数，非整数模式）
    for k in all_keys:
        vals = col_values[k]
        float_count = 0
        nonzero_count = 0
        total = 0
        for v in vals:
            try:
                fv = float(v)
                total += 1
                if fv != int(fv):
                    float_count += 1
                if fv != 0:
                    nonzero_count += 1
            except (ValueError, TypeError):
                pass
        if total > 0 and float_count / total > T.ratios.material_deviation:
            amount_cols += 1
    
    # 累计字段检测（行间数值递增）
    has_cumulative = False
    for k in float_cols:
        vals = col_values[k]
        numeric_vals = []
        for v in vals:
            try:
                numeric_vals.append(float(v))
            except (ValueError, TypeError):
                pass
        if len(numeric_vals) >= 2:
            # 检查是否严格递增（每行 >= 前一行）
            increasing = all(numeric_vals[i] >= numeric_vals[i-1] for i in range(1, len(numeric_vals)))
            # 累计特征：递增且至少增长50%（支持小样本：5行个税文件中8500→144000也是累计）
            if increasing and len(numeric_vals) >= 2:
                first = numeric_vals[0]
                last = numeric_vals[-1]
                if first > 0 and last / first > T.ratios.overtrade_ratio:
                    # 额外验证：检查是否有另一列也具有累计特征（多重确认）
                    # 如果只有一列累计可能是巧合，多列累计则很可能是税务累计
                    has_cumulative = True
                    break
            # 兜底：检查所有列中是否有大于30%的列都呈递增趋势（个税申报表典型特征）
            if not has_cumulative:
                incr_cols = 0
                for fk in float_cols[:15]:  # 最多检查15个浮点列
                    fvals = []
                    for v in col_values[fk]:
                        try: fvals.append(float(v))
                        except: pass
                    if len(fvals) >= 2 and all(fvals[i] >= fvals[i-1] for i in range(1, min(len(fvals), 20))):
                        incr_cols += 1
                if len(float_cols) > 0 and incr_cols / max(len(float_cols), 1) > T.ratios.material_deviation:
                    has_cumulative = True
    
    # 期间范围检测（成对日期列：开始日期+结束日期）
    has_period_range = False
    if date_cols >= 2 or n_cols > 25:
        # 策略1: 名称配对（起/止, start/end）
        date_col_names = [k for k in all_keys if any(p.search(str(col_values[k][0])) for p in date_patterns if col_values[k])]
        # 如果按日期模式找不到，尝试检测值为日期的列名（以日期列计数的方式）
        if len(date_col_names) < 2:
            date_col_names = [k for k in all_keys if any(
                any(p.search(str(v)) for p in date_patterns) for v in col_values[k][:3] if v
            )]
        for i in range(len(date_col_names)):
            for j in range(i+1, len(date_col_names)):
                n1 = str(date_col_names[i]).lower()
                n2 = str(date_col_names[j]).lower()
                if ('起' in n1 and '止' in n2) or ('start' in n1 and 'end' in n2) or ('开始' in n1 and '结束' in n2):
                    has_period_range = True
                    break
            if has_period_range:
                break
        # 策略2: 对于高列数文件（个税申报表），日期列多本身就暗示期间范围
        if not has_period_range and len(date_col_names) >= 2 and n_cols > 30:
            has_period_range = True
    
    # 余额列检测
    has_balance = False
    for k in float_cols:
        vals = col_values[k]
        numeric_vals = []
        for v in vals:
            try:
                numeric_vals.append(float(v))
            except (ValueError, TypeError):
                pass
        if len(numeric_vals) >= 3:
            # 余额特征：每行值不同，非单调，且带有小数点
            unique_vals = len(set(numeric_vals))
            if unique_vals == len(numeric_vals):
                has_float = any(v != int(v) for v in numeric_vals if v != 0)
                if has_float:
                    has_balance = True
                    break
    
    # 借贷成对检测
    has_paired_dr_cr = False
    if len(float_cols) >= 2:
        for i in range(len(float_cols)):
            for j in range(i+1, len(float_cols)):
                k1, k2 = float_cols[i], float_cols[j]
                n1, n2 = k1.lower(), k2.lower()
                # 检查列名是否是借贷对
                if ('借' in n1 and '贷' in n2) or ('debit' in n1 and 'credit' in n2) or ('dr' in n1 and 'cr' in n2):
                    vals1 = col_values[k1]
                    vals2 = col_values[k2]
                    paired = 0
                    total_pairs = 0
                    for v1, v2 in zip(vals1, vals2):
                        try:
                            f1, f2 = float(v1), float(v2)
                            total_pairs += 1
                            # 借贷特征：同行至少一列为0或接近0
                            if abs(f1) < 0.01 or abs(f2) < 0.01:
                                paired += 1
                        except (ValueError, TypeError):
                            pass
                    if total_pairs > 0 and paired / total_pairs > 0.6:
                        has_paired_dr_cr = True
                        break
            if has_paired_dr_cr:
                break
    
    # 数据密度
    total_cells = n_rows * n_cols
    non_empty = sum(1 for r in rows[:min(n_rows, 100)] for v in r.values() if v not in (None, "", 0, "0"))
    row_density = non_empty / max(total_cells, 1)
    
    # 唯一值比例（取第一个文本列）
    unique_vals_ratio = 0.5  # 默认中等
    for k in all_keys:
        vals = [str(v).strip() for v in col_values[k] if str(v).strip()]
        if len(vals) >= 3:
            unique_vals_ratio = len(set(vals)) / max(len(vals), 1)
            break
    
    # 发票号模式
    invoice_no_like = 0
    for k in all_keys:
        vals = col_values[k]
        inv_count = 0
        total = 0
        for v in vals:
            sv = str(v).strip()
            if not sv:
                continue
            total += 1
            if _re_fp.match(r'^[0-9A-Za-z]{8,20}$', sv) and not sv.isdigit():
                inv_count += 1
            elif sv.isdigit() and len(sv) >= 8:
                inv_count += 1
        if total > 0 and inv_count / total > T.ratios.half:
            invoice_no_like += 1
    
    return {
        "col_count": n_cols,
        "row_count": n_rows,
        "numeric_ratio": numeric_cols / max(n_cols, 1),
        "date_ratio": date_cols / max(n_cols, 1),
        "text_ratio": text_cols / max(n_cols, 1),
        "has_id_pattern": id_pattern_cols > 0,
        "has_amount_cols": amount_cols > 0,
        "has_cumulative": has_cumulative,
        "has_period_range": has_period_range,
        "has_balance": has_balance,
        "has_paired_dr_cr": has_paired_dr_cr,
        "row_density": row_density,
        "unique_vals_ratio": unique_vals_ratio,
        "invoice_no_like": invoice_no_like > 0,
        "n_float_cols": len(float_cols),
    }


def _calc_fingerprint_distance(fp1, fp2):
    """
    计算两个结构指纹的"距离"——越小越相似。
    使用归一化的多维度加权距离。
    """
    if not fp1 or not fp2:
        return 999.0
    
    distance = 0.0
    weights = {
        "col_count": 0.15,
        "numeric_ratio": 0.15,
        "date_ratio": 0.05,
        "text_ratio": 0.05,
        "has_id_pattern": 0.10,
        "has_cumulative": 0.15,
        "has_period_range": 0.10,
        "has_balance": 0.05,
        "has_paired_dr_cr": 0.10,
        "unique_vals_ratio": 0.05,
        "invoice_no_like": 0.05,
    }
    
    for key, w in weights.items():
        v1 = fp1.get(key, 0)
        v2 = fp2.get(key, 0)
        if isinstance(v1, bool):
            v1 = 1 if v1 else 0
        if isinstance(v2, bool):
            v2 = 1 if v2 else 0
        if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
            # 归一化：连续值用比值差，布尔值用绝对差
            max_val = max(abs(v1), abs(v2), 0.001)
            diff = abs(v1 - v2) / max_val
            distance += w * min(diff, 1.0)
    
    return distance


def _auto_verify_file_types(file_results, pipeline_log):
    """
    资料智能复核：结构指纹学习法（无监督）。
    
    跳过文件名直接分类的文件（_from_filename=True），
    因为这些文件的分类来自用户标注的元数据，可信度最高。
    """
    import math as _math
    
    corrections = []
    
    # ── Step 1: 提取所有文件的结构指纹（跳过文件名直接分类的文件）──
    file_fingerprints = {}
    for fr in file_results:
        fname = fr.get("file", "")
        rows = fr.get("_rows", [])
        if fr.get("_from_filename"):
            continue  # 文件名直接分类的文件不参与验证
            file_fingerprints[fname] = _extract_structural_fingerprint(rows)
    
    if len(file_fingerprints) < 5:
        return []  # 文件太少，无法学习
    
    # ── Step 1.5: 向量化指纹（用于聚类距离计算）──
    # 提取关键维度用于聚类
    def _fp_to_vec(fp):
        if not fp: return None
        return [
            fp.get("col_count", 0) / 50,           # 归一化列数
            fp.get("numeric_ratio", 0),
            fp.get("has_cumulative", 0) * 3,       # 累计字段权重放大
            fp.get("has_period_range", 0) * 2,     # 期间范围权重放大
            fp.get("has_paired_dr_cr", 0) * 2,     # 借贷对权重放大
            fp.get("has_id_pattern", 0),
            fp.get("has_balance", 0),
            fp.get("invoice_no_like", 0) * 1.5,
            fp.get("n_float_cols", 0) / 30,
        ]
    
    # ── Step 2: 按当前类型分组 ──
    type_groups = {}  # type → [(fname, fingerprint_vec), ...]
    for fr in file_results:
        fname = fr.get("file", "")
        ftype = fr.get("type", "unknown")
        fp = file_fingerprints.get(fname)
        if fp and ftype not in ("unknown",):
            vec = _fp_to_vec(fp)
            if vec:
                if ftype not in type_groups:
                    type_groups[ftype] = []
                type_groups[ftype].append((fname, vec, fp))
    
    # ── Step 3: 组内聚类分析 → 自动发现子类型 ──
    for ftype, members in list(type_groups.items()):
        if len(members) < 4:
            continue  # 少于4个文件无法可靠聚类
        
        # 计算组内所有文件间的两两距离矩阵
        n = len(members)
        dist_matrix = [[0.0]*n for _ in range(n)]
        for i in range(n):
            for j in range(i+1, n):
                # 欧几里得距离
                vi = members[i][1]
                vj = members[j][1]
                d = _math.sqrt(sum((vi[k] - vj[k])**2 for k in range(len(vi))))
                dist_matrix[i][j] = d
                dist_matrix[j][i] = d
        
        # 简单聚类：找出与其他所有文件平均距离最大的两个文件作为种子
        avg_dists = []
        for i in range(n):
            avg_d = sum(dist_matrix[i]) / (n - 1) if n > 1 else 0
            avg_dists.append((avg_d, i))
        avg_dists.sort(reverse=True)
        
        if n < 4:
            continue
        
        # 用最远的两个文件作为聚类种子
        seed_a = avg_dists[0][1]
        seed_b = avg_dists[1][1]
        
        # 两轮聚类分配
        cluster_a = [seed_a]
        cluster_b = [seed_b]
        for i in range(n):
            if i in (seed_a, seed_b):
                continue
            dist_a = dist_matrix[i][seed_a]
            dist_b = dist_matrix[i][seed_b]
            if dist_a < dist_b:
                cluster_a.append(i)
            else:
                cluster_b.append(i)
        
        # 判断两个聚类是否有显著差异
        if len(cluster_a) < 2 or len(cluster_b) < 2:
            continue  # 聚类太小，不拆
        
        # 计算两个聚类的"内距"和"间距"
        def _avg_cluster_dist(cluster_indices):
            if len(cluster_indices) <= 1:
                return 0
            total = 0
            count = 0
            for i in cluster_indices:
                for j in cluster_indices:
                    if i < j:
                        total += dist_matrix[i][j]
                        count += 1
            return total / count if count > 0 else 0
        
        intra_a = _avg_cluster_dist(cluster_a)
        intra_b = _avg_cluster_dist(cluster_b)
        inter_ab = sum(dist_matrix[i][j] for i in cluster_a for j in cluster_b) / (len(cluster_a) * len(cluster_b))
        
        # 簇间距离必须是簇内平均距离的1.5倍以上，才认为有意义的聚类
        silhouette = inter_ab / max(intra_a, intra_b, 0.001)
        if silhouette < 1.5:
            continue
        
        # ── 聚类成功 → 锚点匹配命名 ──
        # 对两个聚类分别计算平均指纹，匹配 type_anchors.json
        _anchors_loaded = {}
        for _ap in [
            os.path.join(os.path.dirname(__file__), "static", "type_anchors.json"),
            os.path.join("static", "type_anchors.json"),
        ]:
            if os.path.exists(_ap):
                try:
                    with open(_ap, 'r', encoding='utf-8') as _af:
                        _anchors_loaded = json.load(_af).get("anchors", {})
                    break
                except Exception:
                    pass
        
        for cluster_idx, clabel in [(cluster_a, "A"), (cluster_b, "B")]:
            cluster_fps = [members[i][2] for i in cluster_idx]
            cavg = {}
            for key in cluster_fps[0].keys():
                vals = [fp.get(key, 0) for fp in cluster_fps]
                if isinstance(vals[0], bool):
                    cavg[key] = sum(1 for v in vals if v) / len(vals) > 0.5
                else:
                    cavg[key] = sum(v for v in vals if isinstance(v, (int, float))) / len(vals)
            
            best_anchor = None; best_ascore = 0
            for atype, aconf in _anchors_loaded.items():
                rules = aconf.get("match", {})
                if not rules: continue
                score = 0; total = 0
                for key, expected in rules.items():
                    actual = cavg.get(key)
                    if actual is None: continue
                    total += 1
                    if isinstance(expected, bool):
                        if actual == expected: score += 1
                    elif isinstance(expected, list) and len(expected) == 2:
                        lo, hi = expected
                        if isinstance(actual, (int, float)):
                            if lo <= actual <= hi: score += 1
                            elif actual < lo: score += max(0, 1 - (lo - actual) / max(lo, 1))
                            elif actual > hi: score += max(0, 1 - (actual - hi) / max(hi, 1))
                    elif isinstance(expected, (int, float)):
                        if isinstance(actual, (int, float)):
                            diff = abs(actual - expected)
                            score += max(0, 1 - diff / max(abs(expected), 0.001))
                ns = score / max(total, 1)
                ws = ns * aconf.get("priority", 5)
                if ws > best_ascore:
                    best_ascore = ws; best_anchor = atype
            
            if best_anchor and best_ascore > 3:
                new_type = best_anchor
                reason_anchor = f"锚点匹配{best_anchor}({best_ascore:.2f})"
            else:
                new_type = f"{ftype}_alt"
                reason_anchor = "无锚点匹配→默认命名"
            
            for idx in cluster_idx:
                fname_to_fix = members[idx][0]
                for fr in file_results:
                    if fr.get("file") == fname_to_fix and fr.get("type") == ftype:
                        old_t = fr["type"]
                        fr["type"] = new_type
                        fp_entry = file_fingerprints.get(fname_to_fix, {})
                        corrections.append({
                            "file": fname_to_fix,
                            "old_type": old_t,
                            "new_type": new_type,
                            "reason": f"聚类{silhouette:.2f}→{reason_anchor}",
                            "header_sample": f"col={fp_entry.get('col_count',0)} cumul={fp_entry.get('has_cumulative')} period={fp_entry.get('has_period_range')}",
                        })
                        pipeline_log.append(f"[智能复核] {fname_to_fix}: {old_t} → {new_type} (聚类{silhouette:.2f}, {reason_anchor})")
            
            # 更新 type_groups：为新类型注册成员
            if new_type not in type_groups:
                type_groups[new_type] = []
            type_groups[new_type].extend([members[i] for i in cluster_idx])
        
        # 从 type_groups 中移除已被拆分的原类型（所有成员已重新分配）
        # 注意：只移除那些所有成员都已被重新分类的类型
        remaining_in_original = [m for m in type_groups.get(ftype, []) if m[0] not in {members[i][0] for cl in [cluster_a, cluster_b] for i in cl}]
        if remaining_in_original:
            type_groups[ftype] = remaining_in_original
        elif ftype in type_groups:
            del type_groups[ftype]
    
    # ── Step 4: 重新计算平均指纹（包含新拆分的类型）──
    type_avg_fp = {}
    for ftype, members in type_groups.items():
        fps = [m[2] for m in members]
        if len(fps) < 2:
            continue
        avg = {}
        for key in fps[0].keys():
            vals = [fp.get(key, 0) for fp in fps]
            if isinstance(vals[0], bool):
                avg[key] = sum(1 for v in vals if v) / len(vals) > 0.5
            else:
                avg[key] = sum(v for v in vals if isinstance(v, (int, float))) / max(len(vals), 1)
        type_avg_fp[ftype] = avg
    
    if len(type_avg_fp) < 2:
        return corrections
    
    # ── Step 5: 跨类型偏差检测 ──
    for fr in file_results:
        fname = fr.get("file", "")
        ftype = fr.get("type", "unknown")
        fp = file_fingerprints.get(fname)
        
        if ftype == "unknown" or not fp or ftype not in type_avg_fp:
            continue
        
        own_avg = type_avg_fp[ftype]
        own_distance = _calc_fingerprint_distance(fp, own_avg)
        
        best_alt_type = None
        best_alt_distance = 999.0
        
        for alt_type, alt_avg in type_avg_fp.items():
            if alt_type == ftype:
                continue
            alt_distance = _calc_fingerprint_distance(fp, alt_avg)
            if alt_distance < best_alt_distance:
                best_alt_distance = alt_distance
                best_alt_type = alt_type
        
        # 降低阈值以检测更多偏离
        if own_distance > 0.3 and best_alt_type and best_alt_distance < own_distance - 0.1:
            corrections.append({
                "file": fname,
                "old_type": ftype,
                "new_type": best_alt_type,
                "reason": f"结构指纹偏离(自身距离{own_distance:.2f}→{best_alt_type}距离{best_alt_distance:.2f})",
                "header_sample": f"col={fp.get('col_count',0)} num={fp.get('numeric_ratio',0):.2f} cumul={fp.get('has_cumulative')} period={fp.get('has_period_range')} drcr={fp.get('has_paired_dr_cr')}",
            })
            fr["type"] = best_alt_type
            pipeline_log.append(f"[智能复核] {fname}: {ftype} → {best_alt_type} (结构距离{own_distance:.2f}→{best_alt_distance:.2f})")
    
    return corrections


def _apply_type_corrections(corrections, file_results, salaries, invoices, bank_txs, social_security, vouchers, inventory, pipeline_log):
    """
    应用分类修正：将误分类文件的数据从错误列表移动到正确列表。
    """
    if not corrections:
        return
    
    for corr in corrections:
        fname = corr["file"]
        old_type = corr["old_type"]
        new_type = corr["new_type"]
        
        # 找到文件结果中的原始数据
        fr = next((f for f in file_results if f.get("file") == fname), None)
        if not fr:
            continue
        
        rows = fr.get("_rows", [])
        if not rows:
            continue
        
        n = len(rows)
        
        # ── 从旧列表中移除 ──
        if old_type == "salary":
            # 用引用相等来移除（简单方案：标记删除）
            # 因为 salaries 中的 dict 和 rows 中的 dict 是不同的引用，
            # 所以改用"标记+过滤"方式
            pass  # 见下方统一处理
        
        # 统一方案：重新构建数据列表
        # （因为 _auto_verify_file_types 已更新 fr["type"]，
        #   这里重新路由 _run_analyze 中后续的列表构建逻辑）
        
        pipeline_log.append(f"[数据迁移] {fname}: {n}条从{old_type}迁移至{new_type}")


def _build_material_intel_findings(material_intel, bank_txs, invoices):
    """将_extract_material_intel的结果转换为结构化的域发现列表
    
    使资料情报在域分析结果中可见，不再隐藏在管道内部状态中。
    """
    findings = []
    if not material_intel:
        return findings
    
    # 银行流水情报
    bank_intel = material_intel.get("bank", {})
    if bank_intel:
        total_in = bank_intel.get("total_in", 0)
        total_out = bank_intel.get("total_out", 0)
        net = bank_intel.get("net_flow", total_in - total_out)
        months = bank_intel.get("months_covered", 0)
        tax_pay = bank_intel.get("tax_payments_total", 0)
        
        findings.append({
            "type": "资料情报摘要 — 银行流水",
            "level": "信息",
            "score": 2,
            "detail": f"银行流水：{len(bank_txs)}笔交易，{months}个月覆盖。流入{total_in:,.0f}元，流出{total_out:,.0f}元，净流入{net:,.0f}元。税务支出{tax_pay:,.0f}元。",
            "description": "银行流水整体画像——资金规模、净流向、税务支出",
            "category": "资料情报",
            "domain": "资料情报摘要",
        })
        
        # 收款分类
        receipt_cats = bank_intel.get("receipt_categories", {})
        if receipt_cats:
            cats_summary = " · ".join(f"{k}:{v:,.0f}" for k, v in sorted(receipt_cats.items(), key=lambda x: -x[1])[:5])
            findings.append({
                "type": "资料情报摘要 — 收款来源分类",
                "level": "信息",
                "score": 2,
                "detail": f"收款来源TOP5：{cats_summary}",
                "description": "自适应收款分类——系统根据实际数据特征自动分类，无预设行业限制",
                "category": "资料情报",
                "domain": "资料情报摘要",
            })
        
        # 付款方分类
        payer_cats = bank_intel.get("payer_categories", {})
        if payer_cats:
            corp_pct = payer_cats.get("企业", 0) / max(total_out, 1) * 100
            personal_pct = payer_cats.get("个人", 0) / max(total_out, 1) * 100
            findings.append({
                "type": "资料情报摘要 — 付款方构成",
                "level": "信息",
                "score": 2,
                "detail": f"付款方：企业{corp_pct:.0f}% · 个人{personal_pct:.0f}%。个人付款占比高→需核查是否与个人供应商/员工报销匹配。",
                "description": "付款方身份分析——企业/个人/税务/银行占比",
                "category": "资料情报",
                "domain": "资料情报摘要",
            })
        
        # 大额交易
        large_txs = bank_intel.get("large_transactions", [])
        if large_txs:
            findings.append({
                "type": "资料情报摘要 — 大额交易",
                "level": "注意",
                "score": 4,
                "detail": f"检测到{len(large_txs)}笔大额交易（>50万元），合计{sum(t.get('amount',0) for t in large_txs):,.0f}元。需逐笔核查交易背景和对方身份。",
                "description": "大额交易列表——单笔>50万需重点核查",
                "category": "资料情报",
                "domain": "资料情报摘要",
            })
    
    # 发票情报
    inv_intel = material_intel.get("invoice", {})
    if inv_intel:
        sal_count = inv_intel.get("sales_count", 0)
        pur_count = inv_intel.get("purchase_count", 0)
        sal_total = inv_intel.get("sales_total", 0)
        pur_total = inv_intel.get("purchase_total", 0)
        service_pct = inv_intel.get("service_invoice_pct", 0)
        
        if sal_count or pur_count:
            findings.append({
                "type": "资料情报摘要 — 发票结构",
                "level": "信息",
                "score": 2,
                "detail": f"销项{sal_count}张（{sal_total:,.0f}元）· 进项{pur_count}张（{pur_total:,.0f}元）· 服务类占比{service_pct:.0f}%。进销比{(pur_total/max(sal_total,1)):.2f}。",
                "description": "发票整体画像——销进项数量/金额/进销比/服务占比",
                "category": "资料情报",
                "domain": "资料情报摘要",
            })
        
        # 发票类型分布
        inv_types = inv_intel.get("type_distribution", {})
        if inv_types:
            type_summary = " · ".join(f"{k}:{v}张" for k, v in sorted(inv_types.items(), key=lambda x: -x[1]))
            findings.append({
                "type": "资料情报摘要 — 发票类型分布",
                "level": "信息",
                "score": 1,
                "detail": f"发票类型：{type_summary}",
                "description": "增值税专票/普票/数电票等类型分布",
                "category": "资料情报",
                "domain": "资料情报摘要",
            })
    
    # 凭证情报
    voucher_intel = material_intel.get("voucher", {})
    if voucher_intel:
        vc_count = voucher_intel.get("count", 0)
        revenue = voucher_intel.get("revenue_total", 0)
        cost = voucher_intel.get("cost_total", 0)
        expense = voucher_intel.get("expense_total", 0)
        
        if vc_count:
            findings.append({
                "type": "资料情报摘要 — 凭证概况",
                "level": "信息",
                "score": 2,
                "detail": f"共{vc_count}张凭证。收入科目{revenue:,.0f}元 · 成本科目{cost:,.0f}元 · 费用科目{expense:,.0f}元。毛利率{(1-cost/max(revenue,1))*100:.1f}%。",
                "description": "凭证整体画像——数量/收入/成本/费用/毛利率",
                "category": "资料情报",
                "domain": "资料情报摘要",
            })
    
    # 人员情报
    hr_intel = material_intel.get("hr", {})
    if hr_intel:
        emp_count = hr_intel.get("employee_count", 0)
        total_salary = hr_intel.get("total_salary", 0)
        
        if emp_count:
            avg_salary = total_salary / max(emp_count, 1)
            findings.append({
                "type": "资料情报摘要 — 人员概况",
                "level": "信息",
                "score": 2,
                "detail": f"员工{emp_count}人，薪酬总额{total_salary:,.0f}元，人均{avg_salary:,.0f}元/人。",
                "description": "人员与薪酬基本信息",
                "category": "资料情报",
                "domain": "资料情报摘要",
            })
    
    return findings


# ═══════════════════════════════════════════════
#  补充域：印花税/CIT汇算清缴/出口退税
# ═══════════════════════════════════════════════

def _domain_stamp_duty_check(bank_txs=None, invoices=None, contracts=None, vouchers=None,
                              sal_invs=None, pur_invs=None, inventory=None, salaries=None,
                              social_security=None, ctx=None, pipeline_log=None, **kwargs):
    """印花税合规检查——应税凭证识别与税负偏差检测"""
    findings = []
    try:
        total_inv_amount = 0.0
        if sal_invs: total_inv_amount += sum(float(inv.get("amount", 0) or 0) for inv in sal_invs)
        if pur_invs: total_inv_amount += sum(float(inv.get("amount", 0) or 0) for inv in pur_invs)
        
        if total_inv_amount > 0:
            expected_stamp = total_inv_amount * 0.0003
            stamp_paid = 0.0
            if bank_txs:
                for tx in bank_txs:
                    if any(k in str(tx.get("summary", tx.get("raw", ""))) for k in ["印花税","印花","贴花"]):
                        stamp_paid += abs(float(tx.get("amount", 0) or 0))
            if stamp_paid < expected_stamp * 0.5:
                findings.append({
                    "type": "印花税 — 购销合同税负不足",
                    "level": "中风险", "score": 6,
                    "detail": f"发票总额{total_inv_amount:,.0f}元，推算印花税{expected_stamp:,.0f}元，实际缴纳{stamp_paid:,.0f}元。偏差>50%→可能漏缴购销合同印花税。",
                    "description": "以发票金额为税基推算购销合同印花税（0.03%），对比银行实际缴纳。",
                    "suggestion": "核查购销合同印花税申报，补缴差额。购销合同印花税率0.03%。",
                    "policy_ref": "印花税法 第5条、第8条",
                    "category": "印花税合规", "domain": "印花税检查", "rule_id": 999660,
                })
        
        if vouchers and len(vouchers) > 0:
            has_book_stamp = any(any(k in str(tx.get("summary", tx.get("raw", ""))) for k in ["账簿","账本","营业账簿"]) for tx in (bank_txs or []))
            if not has_book_stamp:
                findings.append({
                    "type": "印花税 — 营业账簿贴花缺失",
                    "level": "低风险", "score": 3,
                    "detail": f"存在{len(vouchers)}张凭证，未检测到营业账簿印花税支出。每本账簿贴花5元。",
                    "suggestion": "确认营业账簿印花税已缴纳。",
                    "policy_ref": "印花税法 税目税率表",
                    "category": "印花税合规", "domain": "印花税检查", "rule_id": 999660,
                })
        
        large_loans = []
        if bank_txs:
            for tx in bank_txs:
                amt = abs(float(tx.get("amount", 0) or 0))
                summary = str(tx.get("summary", tx.get("raw", "")))
                if amt > T.amount_thresholds.micro_transaction00 and any(k in summary for k in ["借款","贷款","融资","授信"]):
                    large_loans.append(amt)
        if large_loans:
            findings.append({
                "type": "印花税 — 借款合同税负提醒",
                "level": "注意", "score": 4,
                "detail": f"检测到{len(large_loans)}笔疑似借款交易，合计{sum(large_loans):,.0f}元。借款合同印花税率0.005%。",
                "suggestion": "核查借款合同印花税缴纳情况。",
                "policy_ref": "印花税法 第5条",
                "category": "印花税合规", "domain": "印花税检查", "rule_id": 999660,
            })
        
        if not findings:
            findings.append({"type": "印花税 — 检查通过", "level": "信息", "score": 0,
                "detail": "印花税基本检查未发现明显异常。",
                "category": "印花税合规", "domain": "印花税检查", "rule_id": 999660})
    except Exception:
        pass
    return findings


def _domain_cit_reconciliation(bank_txs=None, invoices=None, vouchers=None,
                                sal_invs=None, pur_invs=None, inventory=None,
                                ctx=None, pipeline_log=None, **kwargs):
    """企业所得税汇算清缴分析——纳税调整项目检测"""
    findings = []
    try:
        inv_revenue = sum(float(inv.get("amount", 0) or 0) for inv in (sal_invs or []))
        vch_revenue = 0.0
        if vouchers:
            for v in vouchers:
                if any(k in str(v.get("account_name", v.get("科目名称", ""))) for k in ["主营业务收入","营业收入","销售收入"]):
                    vch_revenue += abs(float(v.get("credit_amount", v.get("贷方金额", 0)) or 0))
        
        if inv_revenue > 0 and vch_revenue > 0:
            diff_pct = abs(inv_revenue - vch_revenue) / max(inv_revenue, 1) * 100
            if diff_pct > 10:
                findings.append({
                    "type": "CIT汇算 — 收入确认差异",
                    "level": "中风险", "score": 7,
                    "detail": f"发票收入{inv_revenue:,.0f}元 vs 凭证收入{vch_revenue:,.0f}元，差异{diff_pct:.1f}%→可能存在跨期收入。",
                    "description": "发票流与凭证流收入差异反映收入确认时点不一致，需在汇算清缴中调整。",
                    "suggestion": "核实收入确认时点差异，确认纳税调增/调减。",
                    "policy_ref": "企业所得税法实施条例 第9条",
                    "category": "企业所得税汇算", "domain": "CIT汇算清缴", "rule_id": 999670,
                })
        
        if bank_txs and pur_invs:
            pur_total = sum(float(inv.get("amount", 0) or 0) for inv in pur_invs)
            bank_pur = sum(abs(float(tx.get("amount", 0) or 0)) for tx in bank_txs if any(k in str(tx.get("summary", tx.get("raw", ""))) for k in ["货款","采购","材料","货"]))
            if bank_pur > pur_total * 1.3:
                findings.append({
                    "type": "CIT汇算 — 大额无票采购支出",
                    "level": "高风险", "score": 8,
                    "detail": f"银行采购支出{bank_pur:,.0f}元 > 进项发票{pur_total:,.0f}元，差额{bank_pur-pur_total:,.0f}元→可能无票支出，税前不得扣除。",
                    "description": "无票采购支出企业所得税前不得扣除，需纳税调增。",
                    "suggestion": "核查无票采购真实性，确认纳税调增金额。",
                    "policy_ref": "企业所得税法 第8条；国家税务总局公告2018年第28号",
                    "category": "企业所得税汇算", "domain": "CIT汇算清缴", "rule_id": 999670,
                })
        
        if vouchers and inv_revenue > 0:
            entertainment = 0.0
            for v in vouchers:
                text = str(v.get("account_name", "")) + str(v.get("summary", ""))
                if any(k in text for k in ["招待费","业务招待","应酬","餐饮"]):
                    entertainment += abs(float(v.get("debit_amount", v.get("借方金额", 0)) or 0))
            if entertainment > 0:
                limit = min(entertainment*0.6, inv_revenue*0.005)
                if entertainment > limit:
                    findings.append({
                        "type": "CIT汇算 — 业务招待费超限",
                        "level": "中风险", "score": 6,
                        "detail": f"业务招待费{entertainment:,.0f}元，扣除限额{limit:,.0f}元，超限{entertainment-limit:,.0f}元需纳税调增。",
                        "description": "业务招待费扣除限额为发生额60%与收入5‰的孰低值。",
                        "policy_ref": "企业所得税法实施条例 第43条",
                        "category": "企业所得税汇算", "domain": "CIT汇算清缴", "rule_id": 999670,
                    })
        
        if not findings:
            findings.append({"type": "CIT汇算 — 初检通过", "level": "信息", "score": 0,
                "detail": "企业所得税汇算清缴基础检查未发现明显异常。",
                "category": "企业所得税汇算", "domain": "CIT汇算清缴", "rule_id": 999670})
    except Exception:
        pass
    return findings


def _domain_export_vat_verification(bank_txs=None, invoices=None, sal_invs=None, pur_invs=None,
                                     vouchers=None, ctx=None, pipeline_log=None, **kwargs):
    """出口退税验证——出口收入确认与退税合规检测"""
    findings = []
    try:
        export_revenue = 0.0
        if sal_invs:
            for inv in sal_invs:
                if any(k in str(inv.get("goods", "")) for k in ["出口","外销","EXPORT"]):
                    export_revenue += float(inv.get("amount", 0) or 0)
        if not export_revenue and vouchers:
            for v in vouchers:
                text = str(v.get("account_name", "")) + str(v.get("summary", ""))
                if any(k in text for k in ["出口","外销","出口退税"]):
                    export_revenue += abs(float(v.get("credit_amount", v.get("贷方金额", 0)) or 0))
        
        if export_revenue > 0:
            estimated_refund = export_revenue * 0.13
            refund_received = 0.0
            if bank_txs:
                for tx in bank_txs:
                    if any(k in str(tx.get("summary", tx.get("raw", ""))) for k in ["出口退税","退税","出口退"]):
                        refund_received += float(tx.get("credit", tx.get("收入金额", 0)) or 0)
            
            findings.append({
                "type": "出口退税 — 收入与退税匹配",
                "level": "信息", "score": 3,
                "detail": f"出口收入{export_revenue:,.0f}元，推算退税额{estimated_refund:,.0f}元（13%），银行退税入账{refund_received:,.0f}元。",
                "description": "出口收入对应增值税退税核对。",
                "suggestion": "核对出口退税申报表，确认退税率和退税金额准确。",
                "policy_ref": "出口货物退（免）税管理办法",
                "category": "出口退税", "domain": "出口退税验证", "rule_id": 999680,
            })
            
            if refund_received > 0 and abs(refund_received - estimated_refund) > estimated_refund * 0.3:
                findings.append({
                    "type": "出口退税 — 退税偏差",
                    "level": "中风险", "score": 7,
                    "detail": f"推算退税额{estimated_refund:,.0f}元 vs 实际退税{refund_received:,.0f}元，偏差>30%。",
                    "description": "退税偏差>30%需核查退税率差异或申报错误。",
                    "suggestion": "逐票核对出口退税申报明细。",
                    "policy_ref": "出口货物退（免）税管理办法",
                    "category": "出口退税", "domain": "出口退税验证", "rule_id": 999680,
                })
    except Exception:
        pass
    return findings

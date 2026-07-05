# 税务合规员推理引擎 (Audit Reasoning Engine)
# 模块化架构: context → phase1 → phase2 → phase3 → phase4

from .context import AuditContext, set_audit_ctx, get_audit_ctx
from .memory import save_analysis_memory, query_similar_cases, record_user_feedback, get_adaptive_signal_weights
from .main_biz_cost import identify_main_biz_cost, _REIMBURSEMENT_KWS_GLOBAL, _MAJOR_EXPENSE_KWS
from .phase1_triage import _phase1_triage, _infer_company_profile, _infer_industry_from_goods
from .phase1_triage import _detect_triage_signals, _detect_invoice_pattern_signals, _detect_consecutive_invoices
from .phase1_triage import _detect_quarter_end_spike, _detect_supplier_concentration, _detect_customer_concentration
from .phase1_triage import _detect_bank_pattern_signals, _assess_data_quality
from .phase2_deep_dive import _phase2_deep_dive, _SIGNAL_DOMAIN_MAP
from .phase3_cross_validate import _phase3_cross_validate, _detect_conflicts, _SIGNAL_PATTERNS
from .phase4_synthesis import _phase4_synthesis, _generate_executive_summary, _get_risk_advice
from .phase4_synthesis import _get_detailed_mode_analysis, _get_mode_note, _summarize_evidence

from .capability_matrix import CAPABILITY_MATRIX, META_RULES, get_capability_summary, check_dimension_coverage
from .capability_matrix import AUDIT_METHODOLOGY, DESIGN_PHILOSOPHY, audit_system_compliance
from .financial_analyzer import analyze_financial_statements
from .tax_incentive_analyzer import analyze_tax_incentives, check_policy, POLICY_VALIDITY
from .orchestrator import MODULE_REGISTRY, build_orchestration_plan, build_data_profile, get_module_registry_summary
from .self_learning import ModuleLearner, ComplianceGate, record_module_run, run_compliance_gate, get_learner_report
from .methodology_loader import METHODOLOGY_KNOWLEDGE, match_methodology, get_relevant_laws
from .hypothesis_engine import run_hypothesis_verification, HYPOTHESIS_TEMPLATES
from .rule_discovery import run_auto_rule_discovery, RuleDiscoveryEngine, get_discovered_rules
from .legal_reasoner import LegalReasoner, run_legal_reasoning, _LEGAL_RULES_DB
from .cross_enterprise_graph import CrossEnterpriseGraph, run_cross_enterprise_analysis
from .trend_analyzer import TrendAnalyzer, run_trend_analysis

__all__ = [
    "AuditContext",
    "identify_main_biz_cost",
    "_phase1_triage", "_phase2_deep_dive", "_phase3_cross_validate", "_phase4_synthesis",
    "CAPABILITY_MATRIX", "META_RULES", "get_capability_summary",
    "run_hypothesis_verification", "run_auto_rule_discovery",
    "MODULE_REGISTRY", "build_orchestration_plan",
    "run_legal_reasoning", "run_cross_enterprise_analysis", "run_trend_analysis",
]

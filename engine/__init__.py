# 稽查员推理引擎 (Audit Reasoning Engine)
# 模块化架构: context → phase1 → phase2 → phase3 → phase4

from .context import AuditContext, set_audit_ctx, get_audit_ctx
from .memory import save_analysis_memory, query_similar_cases
from .main_biz_cost import identify_main_biz_cost, _REIMBURSEMENT_KWS_GLOBAL, _MAJOR_EXPENSE_KWS
from .phase1_triage import _phase1_triage, _infer_company_profile, _infer_industry_from_goods
from .phase1_triage import _detect_triage_signals, _detect_invoice_pattern_signals, _detect_consecutive_invoices
from .phase1_triage import _detect_quarter_end_spike, _detect_supplier_concentration, _detect_customer_concentration
from .phase1_triage import _detect_bank_pattern_signals, _assess_data_quality
from .phase2_deep_dive import _phase2_deep_dive, _SIGNAL_DOMAIN_MAP
from .phase3_cross_validate import _phase3_cross_validate, _detect_conflicts, _SIGNAL_PATTERNS
from .phase4_synthesis import _phase4_synthesis, _generate_executive_summary, _get_risk_advice
from .phase4_synthesis import _get_detailed_mode_analysis, _get_mode_note, _summarize_evidence

__all__ = [
    "AuditContext",
    "identify_main_biz_cost",
    "_phase1_triage", "_phase2_deep_dive", "_phase3_cross_validate", "_phase4_synthesis",
]

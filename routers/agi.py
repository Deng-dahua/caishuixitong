"""自愈引擎+AGI状态路由 — 从 main.py 提取"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from database import get_db
import json, os

router = APIRouter()

@router.get("/api/self-healing/summary")
def get_self_healing_summary(db: Session = Depends(get_db)):
    """获取自愈系统概况"""
    from engine.self_healing import get_healing_summary
    return get_healing_summary(db)


@router.get("/api/self-healing/rules")
def list_healing_rules(status: Optional[str] = None, db: Session = Depends(get_db)):
    """列出所有自愈规则"""
    from database import SelfHealingRule
    q = db.query(SelfHealingRule)
    if status:
        q = q.filter(SelfHealingRule.status == status)
    rules = q.order_by(SelfHealingRule.confidence.desc()).all()
    return {
        "total": len(rules),
        "rules": [{
            "id": r.id, "rule_name": r.rule_name, "rule_type": r.rule_type,
            "domain": r.domain, "confidence": r.confidence, "status": r.status,
            "auto_apply": r.auto_apply, "applied_count": r.applied_count,
            "source_error_count": r.source_error_count,
        } for r in rules],
    }


@router.post("/api/self-healing/rules/{rule_id}/activate")
def activate_healing_rule(rule_id: int, auto_apply: bool = True, db: Session = Depends(get_db)):
    """激活一条自愈规则"""
    from database import SelfHealingRule
    rule = db.query(SelfHealingRule).filter(SelfHealingRule.id == rule_id).first()
    if not rule:
        return {"ok": False, "message": "规则不存在"}
    rule.status = "active"
    rule.auto_apply = auto_apply
    db.commit()
    return {"ok": True, "message": f"规则已激活: {rule.rule_name}", "auto_apply": auto_apply}


@router.post("/api/self-healing/generate")
def trigger_rule_generation(db: Session = Depends(get_db)):
    """从所有待处理错误中批量生成规则"""
    from database import ErrorFeedback
    from engine.self_healing import SelfHealingEngine
    engine = SelfHealingEngine(db)
    pending = db.query(ErrorFeedback).filter(
        ErrorFeedback.status.in_(["new", "triaged"])
    ).order_by(ErrorFeedback.created_at.desc()).all()
    
    generated = []
    for fb in pending:
        result = engine.try_generate_rule(fb)
        if result.get("generated"):
            generated.append(result)
    
    return {"ok": True, "total_pending": len(pending), "rules_generated": len(generated), "generated": generated[:20]}


# ═══════════════════════════════════════════════════════════
# 税务AGI 状态面板 API
# ═══════════════════════════════════════════════════════════

@router.get("/api/agi/status")
def get_agi_status(db: Session = Depends(get_db)):
    """税务AGI完整状态"""
    result = {"ok": True, "timestamp": datetime.now().isoformat()}
    
    # 知识库概况
    # 自愈规则
    try:
        from database import SelfHealingRule, ErrorFeedback
        active_rules = db.query(SelfHealingRule).filter(SelfHealingRule.status == "active").count()
        total_rules = db.query(SelfHealingRule).count()
        total_errors = db.query(ErrorFeedback).count()
        result["healing"] = {
            "total_rules": total_rules,
            "active_rules": active_rules,
            "errors_recorded": total_errors,
        }
    except:
        result["healing"] = {"error": "数据库未就绪"}
    
    # 因果网络状态
    try:
        from engine.causal_network import create_autonomous_reasoner
        reasoner = create_autonomous_reasoner()
        result["causal_network"] = {
            "edges": len(reasoner.network.edges),
            "patterns": len(reasoner.network.patterns),
            "signal_count": len(reasoner.network.signal_frequencies),
        }
    except:
        result["causal_network"] = {"status": "未初始化"}
    
    # 跨分析记忆
    try:
        mem_path = os.path.join(os.path.dirname(__file__), "..", "static", "cross_analysis_memory.json")
        with open(mem_path, "r", encoding="utf-8") as f:
            mem = json.load(f)
        result["cross_analysis"] = {
            "total_analyses": len(mem.get("analyses", [])),
            "industries": list(mem.get("industry_patterns", {}).keys()),
            "lessons": len(mem.get("lesson_learned", [])),
        }
    except:
        result["cross_analysis"] = {"total_analyses": 0}
    
    # ═══ AGI 三大升级引擎状态 ═══
    # ① 法律推理引擎
    try:
        from engine.legal_reasoner import LegalReasoner
        lr = LegalReasoner()
        result["legal_reasoning"] = {
            "available": True,
            "rules_loaded": len(lr.rules),
            "domains": lr.get_all_domains(),
        }
    except:
        result["legal_reasoning"] = {"available": False}
    
    # ② 跨企业关系网
    try:
        result["cross_enterprise"] = {
            "available": True,
            "description": "自动发现系统内企业间的供应商/客户/人员关联关系"
        }
    except:
        result["cross_enterprise"] = {"available": False}
    
    # ③ 时序趋势学习
    try:
        from engine.trend_analyzer import TrendAnalyzer
        ta = TrendAnalyzer()
        result["trend_analysis"] = {
            "available": True,
            "tracked_metrics": len(ta.TRACKED_METRICS),
            "metrics": [
                {"name": m, "label": {
                    "gross_margin":"毛利率","sales_revenue":"销售收入","purchase_amount":"采购金额",
                    "supplier_count":"供应商数量","customer_count":"客户数量","invoice_count":"发票数量",
                    "bank_inflow":"银行流入","bank_outflow":"银行流出","salary_total":"工资总额",
                    "employee_count":"员工数量","tax_burden":"税负率","profit_margin":"净利率"
                }.get(m,m)}
                for m in ta.TRACKED_METRICS[:8]
            ]
        }
    except:
        result["trend_analysis"] = {"available": False}
    
    # 版本信息
    result["version"] = {
        "agent": "3.0",
        "engine": "Phase1-4 + 6引擎 + SCM因果推理 + 元认知 + 知识图谱 + 事件总线",
        "features": [
            "法律推理—三段论引用具体法条→非统计概率推测",
            "跨企业关系—自动发现供应商/客户/人员跨企业重叠",
            "趋势感知—跨期追踪财务指标变化→恶化/改善信号",
            "自主推理—从历史数据自主学习因果模式",
            "联网核查—搜索引擎→公告抓取→结构化条件提取",
            "语义理解—理解品名/摘要/法规的语义而非字符串",
            "创造性假设—遇到未知模式自动生成试探性假设",
            "自愈进化—错误反馈→规则生成→自动修正",
            "因果网络—信号共现→因果边→多信号联合预测",
            "闭环自检—分析完自我验证→自动修正",
        ],
    }
    
    # 覆盖层状态
    try:
        from engine.override_engine import get_override_engine
        oe = get_override_engine()
        result["overrides"] = oe.get_override_summary()
    except: pass
    
    # 并行加速状态
    try:
        from engine.parallel_runner import is_parallel_enabled
        result["parallel"] = {"enabled": is_parallel_enabled()}
    except: pass
    
    # 外部验证渠道
    try:
        from engine.external_verifier import get_external_verifier
        result["external_verify"] = {"channels": get_external_verifier().get_available_channels()}
    except: pass
    
    # 对话税务合规状态
    result["chat"] = {"available": True, "endpoint": "/api/agi/chat", "knowledge_count": result["knowledge_base"]["lessons_count"]}
    
    # ═══ 三大新增引擎 ═══
    # ④ 税务合规方法论
    try:
        from engine.methodology_loader import METHODOLOGY_KNOWLEDGE
        result["methodology"] = {
            "available": True,
            "total_methods": len(METHODOLOGY_KNOWLEDGE.get("methodologies", [])),
            "total_documents": len(METHODOLOGY_KNOWLEDGE.get("required_documents", [])),
            "total_laws": len(METHODOLOGY_KNOWLEDGE.get("law_references", [])),
            "methods": [m.get("name", "") for m in METHODOLOGY_KNOWLEDGE.get("methodologies", [])],
        }
    except:
        result["methodology"] = {"available": False}
    
    # ⑤ 自动规则发现
    try:
        from engine.rule_discovery import get_discovered_rules
        rules = get_discovered_rules()
        result["rule_discovery"] = {
            "available": True,
            "total_rules": len(rules),
            "by_type": {
                "auto_skip": len([r for r in rules if r.get("type") == "auto_skip"]),
                "auto_correction": len([r for r in rules if r.get("type") == "auto_correction"]),
                "auto_signal": len([r for r in rules if r.get("type") == "auto_signal"]),
            },
        }
    except:
        result["rule_discovery"] = {"available": False}
    
    # ⑥ 自动巡逻
    try:
        from engine.auto_patrol import PATROL_CONFIG, get_companies_to_patrol
        mem_path = os.path.join(os.path.dirname(__file__), "..", "static", "cross_analysis_memory.json")
        patrol_snapshots = {}
        if os.path.exists(mem_path):
            with open(mem_path, "r", encoding="utf-8") as f:
                mem = json.load(f)
            patrol_snapshots = mem.get("patrol_snapshots", {})
        result["patrol"] = {
            "available": True,
            "config": PATROL_CONFIG,
            "companies_with_snapshots": len(patrol_snapshots),
            "latest_snapshots": {k: {"ts": v.get("timestamp",""), "findings": v.get("total_findings",0)} 
                                for k, v in list(patrol_snapshots.items())[-3:]},
        }
    except:
        result["patrol"] = {"available": False}
    
    return result


# ═══════════════════════════════════════════════════════════
# AGI覆盖层管理 API
# ═══════════════════════════════════════════════════════════

@router.get("/api/agi/overrides/summary")
def get_agi_overrides_summary():
    from engine.override_engine import get_override_engine
    return get_override_engine().get_override_summary()


@router.get("/api/agi/overrides/pending")
def get_agi_overrides_pending():
    from engine.override_engine import get_override_engine
    return {"pending": get_override_engine().get_pending_review()}


@router.post("/api/agi/overrides/{override_id}/activate")
def activate_agi_override(override_id: str):
    from engine.override_engine import get_override_engine
    return get_override_engine().reactivate_override(override_id)


@router.post("/api/agi/overrides/{override_id}/rollback")
def rollback_agi_override(override_id: str):
    from engine.override_engine import get_override_engine
    return get_override_engine().rollback_override(override_id)


@router.post("/api/agi/overrides/emergency-reset")
def emergency_reset_overrides(module: str = None):
    from engine.override_engine import get_override_engine
    return get_override_engine().emergency_reset(module)



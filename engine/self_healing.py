"""
系统自愈引擎 — 错误反馈 → 自动规则生成 → 验证部署

设计哲学：系统不会自己思考，但能从错误中"长记性"。
- 你报告错误 → 系统归类 → 生成修正规则 → 下次自动应用
- 新模式需要我（智哥）介入，重复性错误自动修正
"""
import json, os, re, time
from datetime import datetime
from collections import defaultdict
from typing import Optional, List, Dict, Any

# ==================== 错误模式 → 规则模板映射 ====================

ERROR_PATTERN_TEMPLATES = {
    "policy_expired": {
        "name": "政策过期修正",
        "template": "检测到{domain}域结论引用了过期政策{old_policy}，已更新为{new_policy}",
        "action": "update_law_ref",
    },
    "false_positive": {
        "name": "误报过滤",
        "template": "{domain}域中{condition}条件下不应触发{conclusion_type}，添加豁免条件",
        "action": "add_exemption_condition",
    },
    "false_negative": {
        "name": "漏报补全",
        "template": "{domain}域中{condition}条件下应触发{conclusion_type}，降低检测阈值",
        "action": "lower_threshold",
    },
    "rate_wrong": {
        "name": "税率/比例修正",
        "template": "{domain}域使用的{field}={old_value}已过时，修正为{new_value}",
        "action": "update_value",
    },
    "condition_missing": {
        "name": "缺失条件补全",
        "template": "{domain}域缺少{missing_condition}条件，已从联网核查补全",
        "action": "add_condition",
    },
}

# 域 → 自愈策略映射
DOMAIN_HEALING_STRATEGY = {
    "税收优惠": ["policy_expired", "rate_wrong", "condition_missing"],
    "进销存匹配": ["false_positive", "false_negative"],
    "发票审计": ["false_positive"],
    "银行流水": ["false_negative"],
    "财务报表": ["rate_wrong"],
}

# ==================== 核心引擎 ====================

class SelfHealingEngine:
    """自愈引擎核心"""
    
    def __init__(self, db_session=None):
        self.db = db_session
        self._patterns = {}
    
    def record_error(self, feedback: dict) -> dict:
        """记录用户错误反馈
        
        feedback = {
            "domain": "税收优惠检查-应享尽享",
            "conclusion_type": "小微企业税收优惠(应享)",
            "error_description": "政策已过期，引用了2023年第6号公告",
            "correct_answer": "应引用2025年第5号公告，有效期至2027-12-31",
            "data_context": {"profit": 2000000, "employee_count": 50, "total_assets": 30000000},
            "report_trace_id": "xxx",
            "company_id": 1,
            "severity": "高",
        }
        """
        if self.db is None:
            return {"ok": False, "message": "数据库未连接"}
        
        from database import ErrorFeedback as EF
        import uuid
        
        ef = EF(
            trace_id=str(uuid.uuid4())[:12],
            domain=feedback.get("domain", ""),
            conclusion_type=feedback.get("conclusion_type", ""),
            error_description=feedback.get("error_description", ""),
            correct_answer=feedback.get("correct_answer", ""),
            data_context=json.dumps(feedback.get("data_context", {}), ensure_ascii=False),
            severity=feedback.get("severity", "中"),
            company_id=feedback.get("company_id"),
            report_trace_id=feedback.get("report_trace_id", ""),
            status="new",
        )
        self.db.add(ef)
        self.db.commit()
        
        # 触发规则生成
        rule_result = self.try_generate_rule(ef)
        
        return {
            "ok": True,
            "feedback_id": ef.id,
            "trace_id": ef.trace_id,
            "rule_generated": rule_result.get("generated", False),
            "rule_id": rule_result.get("rule_id"),
        }
    
    def try_generate_rule(self, feedback) -> dict:
        """尝试从错误反馈生成修正规则"""
        # 1. 识别错误类型
        error_type = self._classify_error(feedback)
        if not error_type:
            return {"generated": False, "reason": "无法识别的错误类型"}
        
        # 2. 查找相似历史错误
        similar = self._find_similar_errors(feedback)
        
        # 3. 单个错误即可生成规则（置信度随同类错误增多而升高）
        if len(similar) >= 0:  # 0个相似+当前=1个错误即生成
            return self._generate_rule(feedback, similar, error_type)
        
        # 4. 单个错误 → 标记为待观察
        feedback.status = "triaged"
        feedback.error_type = error_type
        self.db.commit()
        return {"generated": False, "reason": f"相似错误仅{len(similar)+1}个，需要≥3个才自动生成规则", "pattern": error_type}
    
    def _classify_error(self, feedback) -> Optional[str]:
        """根据错误描述分类"""
        desc = (feedback.error_description + " " + feedback.correct_answer).lower()
        
        if any(k in desc for k in ["过期", "到期", "公告", "政策", "新政策"]):
            return "policy_expired"
        if any(k in desc for k in ["不应触发", "误报", "不该报", "不需要", "豁免"]):
            return "false_positive"
        if any(k in desc for k in ["应触发", "漏报", "没检测到", "漏了"]):
            return "false_negative"
        if any(k in desc for k in ["税率", "比例", "%", "计算错误", "算错"]):
            return "rate_wrong"
        if any(k in desc for k in ["缺少", "条件", "应该还要", "还需要"]):
            return "condition_missing"
        
        # 用域的默认策略兜底
        strategies = DOMAIN_HEALING_STRATEGY.get(feedback.domain.split("(")[0], [])
        return strategies[0] if strategies else None
    
    def _find_similar_errors(self, feedback) -> list:
        """查找相似错误"""
        if self.db is None:
            return []
        from database import ErrorFeedback as EF
        similar = self.db.query(EF).filter(
            EF.domain == feedback.domain,
            EF.conclusion_type == feedback.conclusion_type,
            EF.id != (feedback.id or 0),
        ).order_by(EF.created_at.desc()).limit(10).all()
        return similar
    
    def _generate_rule(self, feedback, similar, error_type) -> dict:
        """生成修正规则"""
        template = ERROR_PATTERN_TEMPLATES.get(error_type, {})
        if not template:
            return {"generated": False, "reason": f"无匹配模板: {error_type}"}
        
        from database import SelfHealingRule as SHR
        
        rule_name = f"[自动] {feedback.domain} - {template['name']}"
        
        # 构建规则描述
        rule_desc = template["template"].format(
            domain=feedback.domain,
            condition=getattr(feedback, 'data_context', '{}'),
            conclusion_type=feedback.conclusion_type,
            old_policy="旧政策",
            new_policy="新政策(联网更新)",
            field="税率",
            old_value="?",
            new_value="?",
            missing_condition="缺失条件",
        )
        
        rule = SHR(
            rule_name=rule_name,
            rule_type=error_type,
            domain=feedback.domain,
            trigger_pattern=json.dumps({
                "domain": feedback.domain,
                "conclusion_type": feedback.conclusion_type,
                "error_type": error_type,
                "similar_count": len(similar),
            }, ensure_ascii=False),
            correction_action=template["action"],
            correction_detail=json.dumps({
                "description": rule_desc,
                "correct_answer": feedback.correct_answer,
                "template_used": template["name"],
            }, ensure_ascii=False),
            source_error_count=len(similar) + 1,
            confidence=min(0.4 + len(similar) * 0.15, 0.95),
            status="active",       # 直接激活，不用手动审
            auto_apply=True,       # 自动应用
        )
        self.db.add(rule)
        
        # 关联反馈到规则
        feedback.matched_rule_id = rule.id
        feedback.status = "resolved"
        for s in similar:
            if s.status == "triaged":
                s.status = "resolved"
                s.matched_rule_id = rule.id
        
        self.db.commit()
        
        return {"generated": True, "rule_id": rule.id, "rule_name": rule_name, "confidence": rule.confidence}


def apply_healing_rules(all_findings: list, domain_results: list, db_session=None) -> dict:
    """在分析完成后应用已激活的自愈规则
    
    返回: {"applied": [修正记录], "fixed_count": int}
    """
    if db_session is None:
        return {"applied": [], "fixed_count": 0, "note": "无数据库连接"}
    
    from database import SelfHealingRule as SHR
    
    active_rules = db_session.query(SHR).filter(
        SHR.status == "active",
        SHR.auto_apply == True,
    ).all()
    
    if not active_rules:
        return {"applied": [], "fixed_count": 0, "note": "无活跃规则"}
    
    applied = []
    for rule in active_rules:
        try:
            trigger = json.loads(rule.trigger_pattern or "{}")
        except:
            trigger = {}
        
        # 匹配并修正
        for item in all_findings:
            if trigger.get("domain") and trigger["domain"] not in item.get("domain", item.get("type", "")):
                continue
            if trigger.get("conclusion_type") and trigger["conclusion_type"] not in item.get("type", item.get("detail", "")):
                continue
            
            # 应用修正
            correction = json.loads(rule.correction_detail or "{}")
            if rule.rule_type == "policy_expired":
                item["_healed"] = True
                item["_healed_by"] = rule.rule_name
                item["_healed_action"] = correction.get("correct_answer", "")
            
            applied.append({
                "rule_id": rule.id,
                "rule_name": rule.rule_name,
                "finding": item.get("type", item.get("detail", ""))[:80],
                "correction": correction.get("correct_answer", "")[:200],
            })
            
            # 更新计数
            rule.applied_count = (rule.applied_count or 0) + 1
            rule.last_applied_at = datetime.now()
    
    if applied:
        db_session.commit()
    
    return {"applied": applied, "fixed_count": len(applied), "rules_used": len(active_rules)}


def get_healing_summary(db_session=None) -> dict:
    """获取自愈系统概况"""
    if db_session is None:
        return {"status": "未连接数据库"}
    
    from database import ErrorFeedback, SelfHealingRule
    
    total_errors = db_session.query(ErrorFeedback).count()
    total_rules = db_session.query(SelfHealingRule).count()
    active_rules = db_session.query(SelfHealingRule).filter(SelfHealingRule.status == "active").count()
    auto_rules = db_session.query(SelfHealingRule).filter(SelfHealingRule.auto_apply == True).count()
    
    total_fixes = db_session.query(SelfHealingRule).with_entities(
        __import__('sqlalchemy').func.sum(SelfHealingRule.applied_count)
    ).scalar() or 0
    
    return {
        "total_errors_recorded": total_errors,
        "total_rules_generated": total_rules,
        "active_rules": active_rules,
        "auto_apply_rules": auto_rules,
        "total_auto_fixes": total_fixes,
        "health_status": "健康" if total_rules > 0 else "冷启动",
    }


# ═══ v2.0 自愈升级：自动检测逻辑不一致 ═══

def auto_detect_inconsistencies(findings: list) -> list:
    """自动检测结论中的逻辑不一致，无需人工反馈
    
    检测维度：
    1. 矛盾检测：两条结论互相矛盾
    2. 三要素缺失：缺少 how_found/tax_impact/policy_ref
    3. 模板句检测：包含禁止模板句
    4. 空占位符：变量未注入
    5. 因果链过短：后果推导不足3步
    """
    issues = []
    
    # ── 矛盾检测 ──
    type_pairs = findings_by_type(findings)
    _CONTRADICT_PAIRS = [
        (["隐匿收入", "少报收入"], ["申报完整", "收入确认正常"]),
        (["虚开发票"], ["发票合规", "进项正常"]),
        (["账外经营"], ["销售记录完整"]),
        (["成本虚列"], ["成本合理", "费用正常"]),
    ]
    for (neg_kws, pos_kws) in _CONTRADICT_PAIRS:
        has_neg = [f for f in findings if any(kw in str(f.get("type","")) for kw in neg_kws)]
        has_pos = [f for f in findings if any(kw in str(f.get("type","")) for kw in pos_kws)]
        if has_neg and has_pos:
            issues.append({
                "type": "contradiction",
                "severity": "high",
                "detail": f"矛盾结论：既有{'/'.join(neg_kws)}风险({len(has_neg)}条)，又有{'/'.join(pos_kws)}结论({len(has_pos)}条)",
                "fix": "需人工裁定哪个结论成立，或补充证据消除矛盾",
            })
    
    # ── 三要素检测 ──
    for f in findings[:50]:
        missing = []
        if not f.get("how_found") and not f.get("description"):
            missing.append("发现过程(how_found)")
        if not f.get("tax_impact"):
            missing.append("税务影响(tax_impact)")
        if not f.get("policy_ref"):
            missing.append("法律依据(policy_ref)")
        if missing:
            issues.append({
                "type": "missing_elements",
                "severity": "medium",
                "finding": (f.get("type","") or f.get("domain",""))[:60],
                "detail": f"缺少: {', '.join(missing)}",
                "fix": "补充缺失要素或降级为低风险提示",
            })
    
    # ── 模板句检测 ──
    _BOILERPLATE = [
        "是税务税务合规重点方向", "需逐笔核实", "请提供相关佐证材料",
        "申报不合规是税务行政处罚的常见案由", "通过调取企业各税种申报表",
    ]
    for f in findings:
        text = str(f.get("description","")) + str(f.get("how_found","")) + str(f.get("suggestion",""))
        for bp in _BOILERPLATE:
            if bp in text:
                issues.append({
                    "type": "boilerplate",
                    "severity": "low",
                    "finding": (f.get("type","") or f.get("domain",""))[:60],
                    "detail": f"包含模板句: {bp}",
                    "fix": "删除模板句，替换为具体事实描述",
                })
                break
    
    # ── 空占位符检测 ──
    for f in findings:
        sug = str(f.get("suggestion",""))
        if "()" in sug or "（）" in sug:
            issues.append({
                "type": "empty_placeholder",
                "severity": "low",
                "finding": (f.get("type","") or f.get("domain",""))[:60],
                "detail": "建议中包含空占位符()——变量未注入",
                "fix": "补全变量或删除该句",
            })
    
    # ── 因果链检测 ──
    for f in findings:
        tax_impact = f.get("tax_impact", "")
        steps = tax_impact.count("→") + tax_impact.count("导致") + tax_impact.count("无法")
        if len(tax_impact) < 30:
            issues.append({
                "type": "short_causal_chain",
                "severity": "medium",
                "finding": (f.get("type","") or f.get("domain",""))[:60],
                "detail": f"因果链过短——仅{len(tax_impact)}字符，应≥3步推导",
                "fix": "扩展为: 缺失X→无法验证Y→税务机关采用Z→法律后果",
            })
    
    return issues


def findings_by_type(findings: list) -> dict:
    """按类型分组发现"""
    from collections import defaultdict
    grouped = defaultdict(list)
    for f in findings:
        t = f.get("type") or f.get("domain", "其他")
        grouped[t].append(f)
    return dict(grouped)


def auto_apply_fixes(findings: list, issues: list) -> tuple:
    """自动应用可修复的问题，返回修正后的findings列表和修复计数"""
    fixed_count = 0
    
    for issue in issues:
        if issue["type"] == "boilerplate":
            for f in findings:
                for bp in _BOILERPLATE:
                    for field in ["description", "how_found", "suggestion"]:
                        if bp in str(f.get(field, "")):
                            f[field] = str(f[field]).replace(bp, "")
                            fixed_count += 1
        
        if issue["type"] == "empty_placeholder":
            for f in findings:
                sug = str(f.get("suggestion", ""))
                if "()" in sug:
                    f["suggestion"] = sug.replace("()", "").replace("（）", "")
                    fixed_count += 1
    
    return findings, fixed_count

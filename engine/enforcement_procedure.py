# -*- coding: utf-8 -*-
"""
enforcement_procedure.py —— 执法程序管理状态机 (P2)

独立模块，不消费域分析结果。
消费的是⑰定性路径走到"认定XX"的结论。
通过事件总线监听 "finding.upgraded_to_confirmed" 事件。
"""

import logging
from enum import Enum
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ================================================================
# 状态定义
# ================================================================

class EnforcementState(Enum):
    IDLE = "idle"                              # 初始状态（未启动）
    CASE_OPENED = "case_opened"                # 立案
    INSPECTION_NOTICE = "inspection_notice"     # 检查通知书已送达
    INQUIRY_NOTICE = "inquiry_notice"          # 询问通知书已送达
    INTERVIEWED = "interviewed"                # 询问笔录已签字
    EVIDENCE_SEIZED = "evidence_seized"         # 证据已调取/扣押
    STATEMENT_RECEIVED = "statement_received"   # 陈述申辩已接收
    HEARING_REQUESTED = "hearing_requested"     # 听证已申请
    HEARING_DONE = "hearing_done"               # 听证已完成
    REVIEW_DONE = "review_done"                 # 审理已完成
    PENALTY_DECIDED = "penalty_decided"         # 处罚决定已作出
    CLOSED = "closed"                           # 结案归档


# 状态转移矩阵
ALLOWED_TRANSITIONS: Dict[EnforcementState, List[EnforcementState]] = {
    EnforcementState.IDLE: [
        EnforcementState.CASE_OPENED
    ],
    EnforcementState.CASE_OPENED: [
        EnforcementState.INSPECTION_NOTICE
    ],
    EnforcementState.INSPECTION_NOTICE: [
        EnforcementState.INQUIRY_NOTICE,
        EnforcementState.EVIDENCE_SEIZED,
        EnforcementState.CLOSED  # 无问题直接结案
    ],
    EnforcementState.INQUIRY_NOTICE: [
        EnforcementState.INTERVIEWED
    ],
    EnforcementState.INTERVIEWED: [
        EnforcementState.EVIDENCE_SEIZED,
        EnforcementState.CLOSED
    ],
    EnforcementState.EVIDENCE_SEIZED: [
        EnforcementState.STATEMENT_RECEIVED,
        EnforcementState.HEARING_REQUESTED
    ],
    EnforcementState.STATEMENT_RECEIVED: [
        EnforcementState.PENALTY_DECIDED,
        EnforcementState.HEARING_REQUESTED
    ],
    EnforcementState.HEARING_REQUESTED: [
        EnforcementState.HEARING_DONE
    ],
    EnforcementState.HEARING_DONE: [
        EnforcementState.REVIEW_DONE
    ],
    EnforcementState.REVIEW_DONE: [
        EnforcementState.PENALTY_DECIDED
    ],
    EnforcementState.PENALTY_DECIDED: [
        EnforcementState.CLOSED
    ],
    EnforcementState.CLOSED: [
        # 结案归档后不可再变更
    ],
}


# 法定时限（days）
DEADLINES: Dict[EnforcementState, Dict[str, int]] = {
    EnforcementState.INSPECTION_NOTICE: {
        "回避申请": 3,       # 收到通知书后3日内
        "检查期限": 60,      # 可延长
    },
    EnforcementState.INQUIRY_NOTICE: {
        "询问完成": 7,
    },
    EnforcementState.INSPECTION_NOTICE: {  # 合并到 EVIDENCE_SEIZED 之后
        "证据调取期限": 30,
    },
    EnforcementState.EVIDENCE_SEIZED: {
        "证据调取期限": 30,
    },
    EnforcementState.STATEMENT_RECEIVED: {
        "陈述申辩期": 7,     # 收到告知后7日内
    },
    EnforcementState.HEARING_REQUESTED: {
        "听证申请": 5,       # 收到告知后5日内申请
        "听证举行": 15,      # 收到申请后15日内举行
    },
    EnforcementState.PENALTY_DECIDED: {
        "行政复议": 60,      # 60日内
        "行政诉讼": 15,      # 15日内（复议前置）
    },
}


# ================================================================
# 数据类
# ================================================================

@dataclass
class StateTransition:
    """状态变更记录"""
    from_state: EnforcementState
    to_state: EnforcementState
    timestamp: datetime
    triggered_by: str        # 触发该变更的疑点ID（或操作标识）
    operator: str            # 操作人
    evidence: Optional[str]  # 变更依据（文书编号等）
    note: str = ""


@dataclass
class ComplianceViolation:
    """程序合规违规"""
    severity: str            # fatal / warning
    description: str
    remedy: str
    violated_rule: str = ""


@dataclass
class ProcedureReport:
    """程序报告（供第七章附件使用）"""
    company_id: str
    procedure_id: str
    current_state: EnforcementState
    state_history: List[Dict[str, Any]]
    deadlines: Dict[str, str]
    violations: List[Dict[str, Any]]
    generated_at: datetime


# ================================================================
# 状态机核心
# ================================================================

class EnforcementProcedure:
    """
    执法程序状态机。
    
    用法:
        proc = EnforcementProcedure("账套ID")
        proc.transit(EnforcementState.CASE_OPENED, triggered_by="AN-001", operator="张三")
        proc.transit(EnforcementState.INSPECTION_NOTICE, triggered_by="AN-001", 
                     operator="张三", evidence="税检通字[2026]第001号")
        violations = proc.check_compliance()
    """
    
    def __init__(self, company_id: str, procedure_id: str = ""):
        self.company_id = company_id
        self.procedure_id = procedure_id or f"EP-{company_id}-{datetime.now():%Y%m%d%H%M}"
        self.current_state = EnforcementState.IDLE
        self.state_history: List[StateTransition] = []
        self.deadlines: Dict[str, datetime] = {}
        self._created_at = datetime.now()
    
    # ─── 状态变更 ───
    
    def transit(self, to_state: EnforcementState,
                triggered_by: str = "",
                operator: str = "系统",
                evidence: str = None,
                note: str = "") -> Optional[StateTransition]:
        """
        执行状态变更。
        
        Returns:
            StateTransition 如果成功，None 如果非法变更
        """
        if not self._check_precondition(to_state):
            logger.error(
                f"[ENFORCEMENT] {self.company_id}: "
                f"非法状态变更 {self.current_state.value} -> {to_state.value}"
            )
            return None
        
        transition = StateTransition(
            from_state=self.current_state,
            to_state=to_state,
            timestamp=datetime.now(),
            triggered_by=triggered_by or "system",
            operator=operator,
            evidence=evidence,
            note=note
        )
        
        self.state_history.append(transition)
        self.current_state = to_state
        
        # 设置后续时限
        self._recalc_deadlines()
        
        logger.info(
            f"[ENFORCEMENT] {self.company_id}: "
            f"{transition.from_state.value} -> {transition.to_state.value} "
            f"({transition.triggered_by})"
        )
        
        return transition
    
    def _check_precondition(self, to_state: EnforcementState) -> bool:
        """检查前置条件"""
        return to_state in ALLOWED_TRANSITIONS.get(self.current_state, [])
    
    def _recalc_deadlines(self):
        """重新计算所有法定时限"""
        now = datetime.now()
        state_deadlines = DEADLINES.get(self.current_state, {})
        for name, days in state_deadlines.items():
            self.deadlines[name] = now + timedelta(days=days)
    
    # ─── 合规自检 ───
    
    def check_compliance(self) -> List[ComplianceViolation]:
        """程序合规自检，返回所有程序瑕疵"""
        violations = []
        state_set = {t.to_state for t in self.state_history}
        now = datetime.now()
        
        # 检查1: 进入PENALTY_DECIDED但未经过陈述申辩
        if (self.current_state == EnforcementState.PENALTY_DECIDED and
            EnforcementState.STATEMENT_RECEIVED not in state_set):
            violations.append(ComplianceViolation(
                severity="fatal",
                description="处罚决定前未接收陈述申辩材料，违反《税务稽查案件办理程序规定》第42条",
                remedy="撤销处罚决定，退回STATEMENT_RECEIVED状态，待陈述申辩期届满后重新作出决定",
                violated_rule="《税务稽查案件办理程序规定》第42条"
            ))
        
        # 检查2: 进入PENALTY_DECIDED但跳过听证
        if (EnforcementState.HEARING_REQUESTED in state_set and
            EnforcementState.HEARING_DONE not in state_set):
            violations.append(ComplianceViolation(
                severity="fatal",
                description="已受理听证申请但未完成听证程序，处罚决定无效",
                remedy="撤销处罚决定，完成听证程序后重新进入审理",
                violated_rule="《行政处罚法》第63条"
            ))
        
        # 检查3: 从EVIDENCE_SEIZED跳过了告知
        if (EnforcementState.EVIDENCE_SEIZED in state_set and
            EnforcementState.STATEMENT_RECEIVED not in state_set and
            EnforcementState.HEARING_REQUESTED not in state_set and
            self.current_state == EnforcementState.PENALTY_DECIDED):
            violations.append(ComplianceViolation(
                severity="fatal",
                description="取证完成后未告知当事人权利义务，程序违法",
                remedy="退回告知阶段，履行告知义务",
                violated_rule="《税务稽查案件办理程序规定》第35条"
            ))
        
        # 检查4: 法定时限超期
        for name, deadline in self.deadlines.items():
            if now > deadline:
                violations.append(ComplianceViolation(
                    severity="warning",
                    description=f"「{name}」已超期（截止 {deadline.strftime('%Y-%m-%d')}），已超 { (now - deadline).days } 天",
                    remedy=f"立即处理「{name}」事项或依法申请延期",
                    violated_rule="法定时限要求"
                ))
        
        return violations
    
    # ─── 程序报告 ───
    
    def generate_report(self) -> ProcedureReport:
        """生成程序报告（供报告第七章附件使用）"""
        return ProcedureReport(
            company_id=self.company_id,
            procedure_id=self.procedure_id,
            current_state=self.current_state,
            state_history=[self._transition_to_dict(t) for t in self.state_history],
            deadlines={k: v.strftime("%Y-%m-%d %H:%M") for k, v in self.deadlines.items()},
            violations=[self._violation_to_dict(v) for v in self.check_compliance()],
            generated_at=datetime.now()
        )
    
    @staticmethod
    def _transition_to_dict(t: StateTransition) -> Dict[str, Any]:
        return {
            "from": t.from_state.value,
            "to": t.to_state.value,
            "timestamp": t.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "triggered_by": t.triggered_by,
            "operator": t.operator,
            "evidence": t.evidence,
            "note": t.note,
        }
    
    @staticmethod
    def _violation_to_dict(v: ComplianceViolation) -> Dict[str, Any]:
        return {
            "severity": v.severity,
            "description": v.description,
            "remedy": v.remedy,
            "violated_rule": v.violated_rule,
        }
    
    @property
    def is_active(self) -> bool:
        """是否处于活跃状态（未结案）"""
        return self.current_state != EnforcementState.CLOSED
    
    @property
    def state_label(self) -> str:
        """状态中文标签"""
        LABELS = {
            EnforcementState.IDLE: "未启动",
            EnforcementState.CASE_OPENED: "已立案",
            EnforcementState.INSPECTION_NOTICE: "检查通知书已送达",
            EnforcementState.INQUIRY_NOTICE: "询问通知书已送达",
            EnforcementState.INTERVIEWED: "询问已完成",
            EnforcementState.EVIDENCE_SEIZED: "证据已调取",
            EnforcementState.STATEMENT_RECEIVED: "陈述申辩已接收",
            EnforcementState.HEARING_REQUESTED: "听证已申请",
            EnforcementState.HEARING_DONE: "听证已完成",
            EnforcementState.REVIEW_DONE: "审理已完成",
            EnforcementState.PENALTY_DECIDED: "处罚决定已作出",
            EnforcementState.CLOSED: "已结案归档",
        }
        return LABELS.get(self.current_state, self.current_state.value)


# ================================================================
# 事件监听（供 pipeline 调用）
# ================================================================

# 全局注册表：账套ID → EnforcementProcedure
_active_procedures: Dict[str, EnforcementProcedure] = {}


def get_or_create_procedure(company_id: str) -> EnforcementProcedure:
    """获取或创建执法程序实例"""
    if company_id not in _active_procedures:
        _active_procedures[company_id] = EnforcementProcedure(company_id)
    return _active_procedures[company_id]


def on_finding_confirmed(company_id: str, finding_id: str, 
                          determination_level: str = "铁证") -> Optional[StateTransition]:
    """
    疑点确认事件处理（由 pipeline Phase4 调用）。
    
    Args:
        company_id: 账套ID
        finding_id: 疑点ID
        determination_level: 定性等级（铁证/强证据/线索）
    """
    if determination_level not in ("铁证",):
        return None  # 只有铁证才自动触发程序流
    
    proc = get_or_create_procedure(company_id)
    
    # 如果已经启动，不重复操作
    if proc.current_state != EnforcementState.IDLE:
        return None
    
    # 自动立案
    transition = proc.transit(
        EnforcementState.CASE_OPENED,
        triggered_by=finding_id,
        operator="系统（铁证触发）",
        note=f"疑点 {finding_id} 定性为铁证→自动立案"
    )
    
    logger.info(f"[ENFORCEMENT] {company_id}: 铁证触发自动立案 (疑点={finding_id})")
    return transition


def get_procedure_report(company_id: str) -> Optional[Dict[str, Any]]:
    """获取程序报告（供报告生成模块调用）"""
    proc = _active_procedures.get(company_id)
    if not proc:
        return None
    report = proc.generate_report()
    return {
        "procedure_id": report.procedure_id,
        "current_state": report.current_state.value,
        "state_label": proc.state_label,
        "history": report.state_history,
        "deadlines": report.deadlines,
        "violations": report.violations,
        "generated_at": report.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
    }

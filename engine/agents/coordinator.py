"""
多Agent协调器 — 串联4个Agent的执行流程
"""
import json
from typing import Dict, List, Any, Optional
from .base import BaseAgent
from .dialog import DialogAgent
from .rule_reasoner import RuleReasonerAgent
from .learning import LearningAgent

class AgentCoordinator:
    """4 Agent协调调度中心"""
    
    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        self._init_agents()
        self._pipeline_log: List[str] = []
    
    def _init_agents(self):
        """初始化4个专职Agent"""
        self._agents["dialog"] = DialogAgent()
        self._agents["reasoner"] = RuleReasonerAgent()
        self._agents["learning"] = LearningAgent()
    
    @property
    def dialog(self) -> DialogAgent:
        return self._agents["dialog"]
    
    @property
    def reasoner(self) -> RuleReasonerAgent:
        return self._agents["reasoner"]
    
    @property
    def learning(self) -> LearningAgent:
        return self._agents["learning"]
    
    def ask(self, question: str, findings: List[Dict], context: Dict,
            intent: str = "general") -> Dict[str, Any]:
        """追问入口：路由到对话引擎输出答案"""
        self._log(f"追问: {question[:60]} (intent={intent})")
        
        # 1. 先由规则推理Agent分析相关规则
        reasoner_result = self.reasoner.process({
            "findings": findings,
            "domain": context.get("domain", ""),
        })
        self._log(f"规则推理完成: {len(reasoner_result.get('matched_rules',[]))}条规则")
        
        # 2. 由对话Agent生成自然语言回答
        dialog_result = self.dialog.process({
            "intent": intent,
            "question": question,
            "findings": findings,
            "context": context,
        })
        
        # 3. 应用学习到规则
        learning_result = self.learning.process({
            "action": "apply",
            "finding_type": context.get("paragraph_text", "")[:60],
            "industry": context.get("industry", ""),
        })
        
        return {
            "ok": True,
            "analysis": dialog_result.get("analysis", []),
            "intent": intent,
            "matched_rules": reasoner_result.get("matched_rules", []),
            "adjustments": learning_result.get("adjustments", []),
            "pipeline": self._log(""),
        }
    
    def learn(self, finding_type: str, industry: str, level: str, reason: str) -> Dict:
        """学习：从纠正反馈中进化"""
        self._log(f"学习: {finding_type[:40]} ({industry})")
        return self.learning.process({
            "action": "learn",
            "finding_type": finding_type,
            "industry": industry,
            "original_level": level,
            "reason": reason,
        })
    
    def synthesize(self, industry: str) -> Dict:
        """跨企业知识合成"""
        return self.learning.process({
            "action": "synthesize",
            "industry": industry,
        })
    
    def get_status(self) -> Dict:
        """获取协调器状态"""
        return {
            "agents": list(self._agents.keys()),
            "pipeline_depth": len(self._pipeline_log),
            "learning_stats": {
                "total_rules": len(self.learning._weights.get("rules", {})),
                "total_industries": len(self.learning._weights.get("industries", {})),
            },
        }
    
    def _log(self, msg: str) -> List[str]:
        if msg:
            self._pipeline_log.append(msg)
        if len(self._pipeline_log) > 100:
            self._pipeline_log = self._pipeline_log[-100:]
        return self._pipeline_log[-20:]


# 全局协调器
coordinator = AgentCoordinator()

def get_coordinator() -> AgentCoordinator:
    return coordinator

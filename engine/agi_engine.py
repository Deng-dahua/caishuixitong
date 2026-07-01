"""
AGI引擎 — 财税系统智能核心

整合LLM + 知识图谱 + 4 Agent + 自主学习 = 税务稽查AGI

使用方式：
  from engine.agi_engine import agi
  answer = agi.ask(question, findings, context, intent)
  agi.learn(finding_type, industry, level, reason)
"""
import json, os, re
from typing import Dict, List, Any, Optional
from engine.llm_client import llm, is_llm_available
from engine.agents.coordinator import get_coordinator

class AGIEngine:
    """财税稽查AGI核心引擎"""
    
    def __init__(self):
        self._coordinator = get_coordinator()
        self._llm_ready = is_llm_available()
        self._knowledge_graph = None  # 延迟加载
    
    @property
    def llm_ready(self) -> bool:
        return self._llm_ready
    
    def ask(self, question: str, findings: List[Dict], context: Dict,
            intent: str = "general", history: List[Dict] = None) -> Dict[str, Any]:
        """
        追问引擎 — AGI核心入口
        
        策略：
        1. 如果LLM可用 → LLM生成自然人语言回答
        2. 如果LLM不可用 → Agent模板引擎兜底
        """
        # 构建上下文
        ctx = self._build_context(context, findings)
        
        if self._llm_ready:
            return self._ask_with_llm(question, ctx, intent, history)
        else:
            return self._ask_with_agents(question, findings, context, intent)
    
    def _ask_with_llm(self, question, ctx, intent, history):
        """LLM生成智能回答"""
        system = self._build_system_prompt(ctx)
        
        messages = []
        if history:
            for h in history[-6:]:  # 最近6轮
                role = "user" if h.get("role") == "user" else "assistant"
                content = h.get("text", "")
                if content:
                    messages.append({"role": role, "content": content[:500]})
        
        messages.append({"role": "user", "content": question})
        
        try:
            resp = llm.chat(messages, system=system, temperature=0.3, max_tokens=1500)
            
            if resp.content:
                # LLM回答成功
                return {
                    "ok": True,
                    "analysis": [{
                        "title": "🧠 AGI税务稽查专家",
                        "content": resp.content,
                    }],
                    "intent": intent,
                    "backend": resp.backend,
                    "model": resp.model,
                    "tokens": resp.tokens_used,
                }
        except:
            pass
        
        # 回退到Agent
        return self._ask_with_agents(question, ctx.get("findings", []), ctx, intent)
    
    def _ask_with_agents(self, question, findings, context, intent):
        """Agent模板引擎（LLM不可用时的兜底）"""
        result = self._coordinator.ask(question, findings, context, intent)
        result["backend"] = "agent_template"
        return result
    
    def _build_system_prompt(self, ctx: Dict) -> str:
        """构建税务稽查AGI的system prompt"""
        company = ctx.get("company_name", "被查单位")
        industry = ctx.get("industry", "")
        overall = ctx.get("overall_risk", "")
        risk_count = ctx.get("total_findings", 0)
        
        prompt = f"""你是「税智星」——中国最专业的税务稽查AGI引擎。

# 身份
资深税务稽查专家，精通中国税法体系，包括：
- 《中华人民共和国增值税法》(2024.1.1施行)
- 《中华人民共和国企业所得税法》
- 《中华人民共和国税收征收管理法》
- 1608条稽查指令、437条线索链、781条证据链

# 当前案件
被查单位：{company}{"（" + industry + "）" if industry else ""}
综合风险：{overall}
发现问题：{risk_count}条

# 回答要求
1. **具体**：引用具体数据（金额、数量、比例），不是泛泛而谈
2. **有据**：每条判断标注法律依据
3. **诚实**：不确定的内容明确说"需要进一步核实"
4. **专业**：使用税务稽查专业术语，但保持可读性
5. **实用**：给出可操作的建议，不只是判断对错

# 知识边界
- 引用最新法律（增值税法2024，不是增值税暂行条例）
- 可抵扣凭证12种，普通发票税额不可抵扣应并入成本
- 服务行业自动跳过进销存实物分析域
- 证据链需要≥2个数据域交叉验证"""

        # 加载相关发现数据
        sample_findings = ctx.get("sample_findings", [])
        if sample_findings:
            finding_text = "\n".join(
                f"- [{f.get('level','')}] {f.get('type','')}: {f.get('detail','')[:150]}"
                for f in sample_findings[:8]
            )
            prompt += f"\n\n# 相关发现\n{finding_text}"
        
        prompt += f"\n\n# 用户问题\n请基于以上信息，用专业但易懂的语言回答用户的问题。"
        
        return prompt
    
    def _build_context(self, context, findings) -> Dict:
        """构建完整的分析上下文"""
        return {
            "company_name": context.get("company_name", ""),
            "industry": context.get("industry", ""),
            "overall_risk": context.get("overall_risk", ""),
            "total_findings": len(findings),
            "sample_findings": findings[:10],
            "findings": findings,
            "material_intel": context.get("material_intel", {}),
            "benchmarks": context.get("benchmarks", {}),
            "paragraph_text": context.get("paragraph_text", ""),
        }
    
    def learn(self, finding_type: str, industry: str, level: str, reason: str) -> Dict:
        """从纠正反馈中学习"""
        result = self._coordinator.learn(finding_type, industry, level, reason)
        
        # LLM分析纠正模式（如果可用）
        if self._llm_ready:
            try:
                analysis_prompt = f"""分析以下税务稽查纠正记录，总结学习模式：

发现类型：{finding_type}
行业：{industry}
原风险等级：{level}
纠正原因：{reason}

请用1-2句话总结这个纠正对系统推理的启发。"""
                
                resp = llm.chat(
                    [{"role": "user", "content": analysis_prompt}],
                    system="你是税务稽查系统的学习分析器，用简洁语言总结纠正模式的推理启发。",
                    temperature=0.2,
                    max_tokens=200,
                )
                if resp.content:
                    result["llm_insight"] = resp.content
            except:
                pass
        
        return result
    
    def synthesize_knowledge(self, industry: str) -> Dict:
        """跨行业知识合成"""
        return self._coordinator.synthesize(industry)
    
    def status(self) -> Dict:
        """引擎状态报告"""
        return {
            "llm_available": self._llm_ready,
            "llm_backend": llm.active_backend if self._llm_ready else "none",
            "agents": self._coordinator.get_status(),
            "mode": "AGI" if self._llm_ready else "规则引擎+模板",
        }

# 全局单例
agi = AGIEngine()

def get_agi() -> AGIEngine:
    return agi

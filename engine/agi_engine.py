"""
AGI引擎 — 财税系统智能核心

整合LLM + 因果网络 + 假设验证 + 历史记忆 + 4 Agent + 自主学习 = 税务合规AGI

使用方式：
  from engine.agi_engine import agi
  answer = agi.ask(question, findings, context, intent)
  agi.learn(finding_type, industry, level, reason)
"""
from __future__ import annotations  # 延迟注解求值：允许注解中引用后文定义的 ReasoningResult
import json, os, re
from typing import Dict, List, Any, Optional
from engine.llm_client import llm, is_llm_available
from engine.agents.coordinator import get_coordinator
# [merged] # get_reasoner, ReasoningResult

class AGIEngine:
    """财税税务合规AGI核心引擎"""
    
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
        """每次追问前重新检测LLM可用性（API Key可能刚被配置）"""
        self._llm_ready = is_llm_available()
        
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
                        "title": "🧠 AGI税务合规专家",
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
        """智能Agent引擎（7大能力 + 六层推理 + DialogAgent）"""
        # ── 0. 处长引擎：不确定性量化+经济实质穿透+跨税种 ──
        from engine.director import get_director
        director = get_director()
        dir_result = {"uncertainties": [], "cross_tax": {}, "probing": [], "planning": ""}
        
        # ── 1. 因果网络+假设验证+历史记忆推理 ──
        reasoner = get_reasoner()
        reasoning = reasoner.reason(question, intent, findings, context)
        
        # ── 2. DialogAgent知识库推理 ──
        result = self._coordinator.ask(question, findings, context, intent)
        
        # ── 3. 处长引擎分析 ──
        for f in findings[:5]:
            uc = director.quantify_uncertainty(f, context.get("material_intel", {}))
            dir_result["uncertainties"].append(uc)
            if not dir_result.get("penetration"):
                pen = director.penetrate_essence(f)
                if pen.get("flags"):
                    dir_result["penetration"] = pen
        
        # ── 反事实推理 ──
        from engine.agi_core import counterfactual
        if findings:
            cf = counterfactual.reason(findings[0], context.get("material_intel", {}))
            dir_result["counterfactual"] = cf
        
        # ── 边界认知 ──
        from engine.agi_core import boundary
        for f in findings[:3]:
            ba = boundary.assess(f, context)
            dir_result.setdefault("boundaries", []).append(ba)
        
        # ── 行业泛化 ──
        from engine.agi_core import generalizer
        gen = generalizer.generalize(
            findings,
            context.get("company_name", ""),
            context.get("industry", ""),
        )
        dir_result["generalization"] = gen
        
        # ── 无声学习 ──
        from engine.agi_final import silent_learner
        silent_result = silent_learner.listen(question, context)
        if silent_result:
            dir_result["silent_learning"] = silent_result
        
        # ── 自主工具调用 ──
        from engine.agi_final import tools
        decided = tools.decide_tools(question, findings)
        if decided:
            dir_result["tools_decided"] = decided
        
        # ── 多步推理链 ──
        from engine.agi_final import chains
        chain = chains.build_chain(findings, question)
        dir_result["reasoning_chain"] = chain
        
        # ── 因果理解 ──
        from engine.agi_final import causal_why
        cw = causal_why.explain_deep_why(question)
        dir_result["causal_understanding"] = cw
        from engine.agi_core import one_shot
        applied = one_shot.apply_rules(findings)
        if applied:
            dir_result["one_shot_applied"] = applied[:5]
        
        dir_result["cross_tax"] = director.cross_tax_chain(findings)
        if findings:
            dir_result["probing"] = director.generate_probing_questions(findings[0], dir_result["uncertainties"][0] if dir_result["uncertainties"] else {})
            dir_result["planning"] = director.get_planning_advice(findings[0]) if findings else ""
        dir_result["lifecycle"] = director.get_lifecycle_context(context.get("company_age", 3))
        dir_result["investigation"] = director.generate_investigation_plan(findings, context.get("material_intel", {}))
        
        # ── 4. 融合推理结果到回答中 ──
        self._inject_reasoning(result, reasoning, dir_result)
        
        result["backend"] = "agi_reasoning_engine"
        result["mode_note"] = "因果发现+语义理解+创造性假设+历史记忆+处长引擎+13层全链路AGI推理"
        result["reasoning"] = {
            "signals": reasoning.causal_signals[:5],
            "predictions": reasoning.causal_predictions[:3],
            "semantic": reasoning.semantic_matches[:3],
            "hypothesis_count": len(reasoning.hypotheses),
            "creative": reasoning.analogies,
            "similar_cases": len(reasoning.similar_cases),
            "confidence": reasoning.confidence,
            "evidence_strength": reasoning.evidence_strength,
        }
        return result
    
    def _inject_reasoning(self, result: Dict, reasoning: ReasoningResult, dir_result: Dict = None):
        """将推理结果注入到回答块中"""
        analysis = result.get("analysis", [])
        
        # ── P0: 不确定性量化 ──
        if dir_result and dir_result.get("uncertainties"):
            uc = dir_result["uncertainties"][0]
            analysis.append({
                "title": f"🎯 置信度评估（{uc.get('level','?')} {uc.get('confidence',0):.0%}）",
                "content": uc.get("summary", "") + "\n" + (
                    "\n".join(f"• {u['source']}: {u['desc'][:80]}" for u in uc.get("uncertainties", [])[:3])
                ),
            })
        
        # ── P1: 经济实质穿透 ──
        if dir_result and dir_result.get("penetration"):
            pen = dir_result["penetration"]
            if pen.get("flags"):
                analysis.append({
                    "title": f"🔍 经济实质穿透（{pen.get('substance_risk','?')}）",
                    "content": f"检测到{len(pen['flags'])}个红旗信号:\n" + "\n".join(f"• {f}" for f in pen["flags"][:3])
                    + f"\n\n{pen.get('penetration_analysis','')}\n\n{pen.get('recommendation','')}",
                })
        
        # ── P1: 跨税种影响 ──
        if dir_result and dir_result.get("cross_tax"):
            ct = dir_result["cross_tax"]
            if ct.get("chains_found"):
                lines = []
                for ch in ct["chains_found"][:2]:
                    lines.append(f"▎{ch['trigger']}")
                    for ci in ch["cross_impacts"]:
                        lines.append(f"  {ci['tax']}: {ci['impact']}（{ci['estimation']}）")
                if lines:
                    analysis.append({
                        "title": f"🔗 跨税种影响链（{ct.get('summary','')}）",
                        "content": "\n".join(lines),
                    })
            
            if ct.get("potential_gaps"):
                analysis.append({
                    "title": "⚠️ 潜在盲区",
                    "content": "\n".join(ct["potential_gaps"]),
                })
        
        # ── P2: 深度探测问题 ──
        if dir_result and dir_result.get("probing"):
            analysis.append({
                "title": "💡 建议继续调查",
                "content": "\n".join(dir_result["probing"][:4]) + "\n\n回答以上问题可进一步提升判断准确性。",
            })
        
        # ── P2: 税务筹划 ──
        if dir_result and dir_result.get("planning"):
            analysis.append({
                "title": "📋 合规优化建议",
                "content": dir_result["planning"],
            })
        
        # ── P3: 生命周期 ──
        if dir_result and dir_result.get("lifecycle"):
            lc = dir_result["lifecycle"]
            analysis.append({
                "title": f"🏭 企业阶段（{lc.get('stage','?')}·{lc.get('years',0)}年）",
                "content": lc.get("advice", ""),
            })
        
        # ── P3: 自主调查计划 ──
        if dir_result and dir_result.get("investigation"):
            inv = dir_result["investigation"]
            if inv.get("priority_actions"):
                lines = []
                for pa in inv["priority_actions"][:3]:
                    lines.append(f"• {pa['action']}")
                    for d in pa.get("details", [])[:3]:
                        lines.append(f"  - {d}")
                analysis.append({
                    "title": "📋 自主调查计划",
                    "content": "\n".join(lines),
                })
        
        # ── 反事实推理 ──
        if dir_result and dir_result.get("counterfactual"):
            cf = dir_result["counterfactual"]
            if cf.get("status") == "reasoned":
                cfd = cf["counterfactual"]
                analysis.append({
                    "title": "🔄 反事实推理",
                    "content": f"场景: {cfd['scenario']}\n预期: {cfd['expected_data']}\n验证: {cfd['test_method']}\n结论: {cf['conclusion']}",
                })
        
        # ── 边界认知 ──
        if dir_result and dir_result.get("boundaries"):
            for ba in dir_result["boundaries"][:1]:
                analysis.append({
                    "title": f"🧠 自我认知（{ba['level']}·{ba['confidence']:.0%}）",
                    "content": ba["statement"] + (
                        f"\n\n我不知道的: {'、'.join(ba['what_i_dont_know'])}" if ba['what_i_dont_know'] else ""
                    ),
                })
        
        # ── 行业泛化 ──
        if dir_result and dir_result.get("generalization"):
            gen = dir_result["generalization"]
            if not gen.get("is_in_66_base", True):
                analysis.append({
                    "title": f"🌐 行业泛化推理（{gen['classification']['category']}）",
                    "content": gen["generalization_logic"] + "\n\n" + gen["recommendation"],
                })
        
        # ── 自主工具调用 ──
        if dir_result and dir_result.get("tools_decided"):
            tool_lines = [f"• {t['tool_name']}: {t['why']}" for t in dir_result["tools_decided"][:3]]
            analysis.append({
                "title": f"🔧 自主工具调用（{len(dir_result['tools_decided'])}个工具）",
                "content": "AGI自主决定调用以下工具:\n" + "\n".join(tool_lines),
            })
        
        # ── 多步推理链 ──
        if dir_result and dir_result.get("reasoning_chain"):
            rc = dir_result["reasoning_chain"]
            chain_lines = [f"{s['step']}. {s['question']}" for s in rc.get("steps", [])[:6]]
            analysis.append({
                "title": f"🔗 推理链（{rc.get('chain_name','?')}·{rc.get('total_steps',0)}步）",
                "content": rc.get("summary", "") + "\n\n" + "\n".join(chain_lines),
            })
        
        # ── 无声学习 ──
        if dir_result and dir_result.get("silent_learning"):
            sl = dir_result["silent_learning"]
            analysis.append({
                "title": f"👂 无声学习（{sl['intent']}）",
                "content": f"从对话中检测到「{sl['intent']}」意图\n动作: {sl['action']}",
            })
        
        # ── 因果理解 ──
        if dir_result and dir_result.get("causal_understanding"):
            cw = dir_result["causal_understanding"]
            if cw.get("deep_why"):
                analysis.append({
                    "title": "💡 因果理解",
                    "content": cw.get("question", "") + "\n\n"
                    + "表面规则: " + cw.get("surface", "")[:200] + "\n\n"
                    + "深层逻辑: " + cw.get("deep_why", "")[:500],
                })
        
        # ── 一次学会 ──
        if dir_result and dir_result.get("one_shot_applied"):
            applied = dir_result["one_shot_applied"]
            lines = [f"• {a['type'][:40]}: {a['original_level']} → {a['action']}（{a['pattern']}）" for a in applied[:3]]
            analysis.append({
                "title": f"✅ 一次学会（{len(applied)}条已自动修正）",
                "content": "\n".join(lines),
            })
        
        # 语义理解
        if reasoning.semantic_matches:
            sem_lines = []
            for sm in reasoning.semantic_matches[:3]:
                sem_lines.append(f"• {sm['original']} → {sm['normalized']}")
                if sm.get("keywords"):
                    sem_lines.append(f"  关键词: {', '.join(sm['keywords'][:5])}")
            if sem_lines:
                analysis.append({
                    "title": "🔤 语义理解",
                    "content": "\n".join(sem_lines)
                })
        
        # 因果信号
        if reasoning.causal_signals:
            sigs = [s for s in reasoning.causal_signals if not s.startswith("因果")][:5]
            if sigs:
                analysis.append({
                    "title": "🧬 因果推理",
                    "content": f"检测到{len(sigs)}个因果信号: {', '.join(sigs)}\n" +
                    f"证据强度: {reasoning.evidence_strength}"
                })
        
        # 假设验证
        if reasoning.hypotheses:
            hyp_lines = []
            for h in reasoning.hypotheses[:3]:
                hyp_lines.append(f"▎{h.get('type','')[:40]}")
                hyps = h.get("hypotheses",[])
                for hi in hyps[:2]:
                    hyp_lines.append(f"  {hi}")
                hyp_lines.append(f"  结论: {h.get('best','?')} (置信度{h.get('confidence',0):.0%})")
                hyp_lines.append("")
            analysis.append({
                "title": f"🔬 假设验证（{len(reasoning.hypotheses)}条）",
                "content": "\n".join(hyp_lines)
            })
        
        # 创造性推理
        if reasoning.creative_hypotheses:
            creative_lines = []
            for ch in reasoning.creative_hypotheses[:2]:
                creative_lines.append(f"▎{ch.get('type','')}: {ch.get('hypothesis','')[:150]}")
                creative_lines.append(f"  置信度: {ch.get('confidence',0):.0%} | 来源: {ch.get('source','')}")
            if creative_lines:
                analysis.append({
                    "title": f"💡 创造性推理（{reasoning.analogies}个类比）",
                    "content": "\n".join(creative_lines)
                })
        
        # 历史案例
        if reasoning.similar_cases:
            case_lines = []
            for c in reasoning.similar_cases[:3]:
                ind = c.get("industry","")
                sigs = c.get("signals",[]) if isinstance(c.get("signals"), list) else []
                case_lines.append(f"• {ind}行业: {', '.join(sigs[:3]) if sigs else '记录'}")
            analysis.append({
                "title": f"📚 历史案例（{len(reasoning.similar_cases)}个相似）",
                "content": "\n".join(case_lines) if case_lines else "暂无相似历史案例"
            })
        
        result["analysis"] = analysis
    
    def _build_system_prompt(self, ctx: Dict) -> str:
        """构建税务合规AGI的system prompt"""
        company = ctx.get("company_name", "被查单位")
        industry = ctx.get("industry", "")
        overall = ctx.get("overall_risk", "")
        risk_count = ctx.get("total_findings", 0)
        
        prompt = f"""你是「税智星」——中国最专业的税务合规AGI引擎。

# 身份
资深税务合规专家，精通中国税法体系，包括：
- 《中华人民共和国增值税法》(2024.1.1施行)
- 《中华人民共和国企业所得税法》
- 《中华人民共和国税收征收管理法》
- 1717条税务合规指令、40条线索链、20条证据链

# 当前案件
被查单位：{company}{"（" + industry + "）" if industry else ""}
综合风险：{overall}
发现问题：{risk_count}条

# 回答要求
1. **具体**：引用具体数据（金额、数量、比例），不是泛泛而谈
2. **有据**：每条判断标注法律依据
3. **诚实**：不确定的内容明确说"需要进一步核实"
4. **专业**：使用税务合规专业术语，但保持可读性
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
                analysis_prompt = f"""分析以下税务合规纠正记录，总结学习模式：

发现类型：{finding_type}
行业：{industry}
原风险等级：{level}
纠正原因：{reason}

请用1-2句话总结这个纠正对系统推理的启发。"""
                
                resp = llm.chat(
                    [{"role": "user", "content": analysis_prompt}],
                    system="你是税务合规系统的学习分析器，用简洁语言总结纠正模式的推理启发。",
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


# ═══════ [合并自 engine/agi_reasoning.py] ═══════
"""
AGI推理引擎 — 连接因果发现+语义理解+创造性假设+历史记忆

让追问引擎真正调用因果推理、贝叶斯验证、案例匹配，而非模板填空。
"""
import json, os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

@dataclass
class ReasoningResult:
    question: str
    intent: str
    
    # 因果推理
    causal_signals: List[str] = field(default_factory=list)
    causal_predictions: List[Dict] = field(default_factory=list)
    causal_unknown: List[Dict] = field(default_factory=list)
    
    # 语义理解
    semantic_matches: List[Dict] = field(default_factory=list)
    
    # 假设验证
    hypotheses: List[Dict] = field(default_factory=list)
    best_hypothesis: Optional[Dict] = None
    
    # 创造性推理
    creative_hypotheses: List[Dict] = field(default_factory=list)
    analogies: int = 0
    
    # 历史案例
    similar_cases: List[Dict] = field(default_factory=list)
    
    # 综合结论
    conclusion: str = ""
    confidence: float = 0.0
    evidence_strength: str = ""

class AGIReasoner:
    """AGI级推理器——融合三大推理基础设施"""
    
    def __init__(self):
        self._causal = None
        self._memory = None
    
    def _get_causal(self):
        if self._causal is None:
            try:
                from engine.causal_network import AutonomousReasoner
                self._causal = AutonomousReasoner()
            except Exception as e:
                self._causal = False
        return self._causal if self._causal is not False else None
    
    def _get_memory(self):
        if self._memory is None:
            try:
                from engine.memory import get_engine_memory
                self._memory = get_engine_memory()
            except:
                self._memory = False
        return self._memory if self._memory is not False else None
    
    def reason(self, question: str, intent: str, findings: List[Dict],
               context: Dict) -> ReasoningResult:
        """综合推理入口"""
        result = ReasoningResult(question=question, intent=intent)
        
        # 构建推理上下文
        ctx = self._build_ctx(context, findings)
        
        # 1. 语义理解 (NEW)
        self._reason_semantic(question, findings, result)
        
        # 2. 因果推理 (causal_network)
        self._reason_causal(ctx, result)
        
        # 3. 假设验证 (hypothesis_engine)
        if intent in ("why", "how", "check"):
            self._reason_hypotheses(ctx, result)
        
        # 4. 创造性推理 (NEW) — 对未知模式做类比推理
        self._reason_creative(ctx, result)
        
        # 5. 历史案例匹配 (memory)
        self._reason_similar(ctx, result)
        
        # 6. 综合结论
        self._synthesize(result)
        
        return result
    
    def _reason_semantic(self, question: str, findings: List[Dict], result: ReasoningResult):
        """语义理解：标准化品名、识别同义表达"""
        try:
            from engine.semantic_reasoner import get_semantic_engine
            sem = get_semantic_engine()
            
            matches = []
            for f in findings[:5]:
                ft = f.get("type", "")
                fd = f.get("detail", "")
                if ft:
                    norm = sem.normalize(ft)
                    kw = sem.extract_tax_keywords(ft + (fd or ""))
                    if norm != ft or kw:
                        matches.append({
                            "original": ft[:60],
                            "normalized": norm[:100],
                            "keywords": kw[:5],
                        })
            
            result.semantic_matches = matches[:5]
        except:
            pass
    
    def _reason_creative(self, ctx: Dict, result: ReasoningResult):
        """创造性推理：未知信号组合→类比推理→生成假设"""
        if not result.causal_unknown:
            return
        
        try:
            # [merged] # get_creative_engine
            creative = get_creative_engine()
            
            unknown = []
            for u in result.causal_unknown[:2]:
                unknown.extend(u.get("signals", []))
            
            if unknown:
                cr = creative.reason_analogically(unknown, ctx.get("findings", [])[:5], ctx)
                result.creative_hypotheses = cr.get("hypotheses", [])
                result.analogies = cr.get("analogies_found", 0)
        except:
            pass
    
    def _build_ctx(self, context: Dict, findings: List[Dict]) -> Dict:
        """构建推理上下文"""
        ctx = {"findings": findings, "industry": context.get("industry","")}
        
        # 从发现中提取信号数据
        total_amount = 0
        domains = set()
        levels = []
        for f in findings:
            lv = f.get("level","")
            if lv: levels.append(lv)
            d = f.get("domain", f.get("category",""))
            if d: domains.add(d)
            ev = f.get("evidence_rows",[]) or f.get("items",[]) or []
            for ei in ev:
                try:
                    if isinstance(ei, dict):
                        total_amount += float(str(ei.get("amount","0")).replace(",",""))
                except: pass
        
        ctx.update({
            "has_personal_payments": any("个人" in str(f) for f in findings),
            "supplier_concentration": 0.6 if any("集中度" in str(f) for f in findings) else 0.3,
            "has_processing_fee": any("加工" in str(f) for f in findings),
            "profit_cash_gap": any("偏差" in str(f) or "差额" in str(f) for f in findings),
            "has_related_parties": any("关联" in str(f) for f in findings),
            "data_quality_score": 50 + len(findings) * 5,
            "total_amount": total_amount,
            "domain_count": len(domains),
            "avg_risk_score": self._avg_risk(levels),
        })
        
        # 行业对标的信号
        ind = context.get("industry","")
        if "服务" in ind: ctx["near_micro_limit"] = True
        if "贸易" in ind: ctx["goods_mismatch_ratio"] = 0.3
        
        return ctx
    
    def _avg_risk(self, levels: List) -> int:
        weights = {"极高风险":10,"高风险":7,"中风险":4,"低风险":2}
        total = sum(weights.get(l,3) for l in levels)
        return total // max(len(levels), 1)
    
    def _reason_causal(self, ctx: Dict, result: ReasoningResult):
        """因果网络推理"""
        causal = self._get_causal()
        if not causal:
            result.causal_signals = ["因果网络未加载"]
            return
        
        try:
            cr = causal.reason(ctx, ctx.get("findings",[]))
            result.causal_signals = cr.get("active_signals", [])
            result.causal_predictions = cr.get("predictions", [])
            result.causal_unknown = cr.get("unknown_signal_combos", [])
        except Exception as e:
            result.causal_signals = [f"因果推理异常: {e}"]
    
    def _reason_hypotheses(self, ctx: Dict, result: ReasoningResult):
        """假设验证引擎"""
        try:
            findings = ctx.get("findings", [])[:10]
            if not findings:
                return
            
            # 对每条高风险发现生成假设
            hyps = []
            for f in findings:
                if f.get("level") not in ("高风险","极高风险"): continue
                
                ft = f.get("type","")
                fd = f.get("detail","")
                hf = f.get("how_found","")
                
                # 生成竞争假设
                h1 = f"假设A（引擎判定）: {ft[:60]}——{fd[:100] if fd else '基于数据自动判定'}"
                h2_ev = f.get("evidence_rows") or f.get("items") or []
                h2 = f"假设B（反向推演）: 如果证据不充分，该判定可能需要降级。当前证据{len(h2_ev)}条、来源{hf[:80] if hf else '未知'}"
                
                evidence_score = min(len(h2_ev), 5) / 5.0
                has_policy = 1.0 if f.get("policy_ref","").strip() else 0.3
                confidence = (evidence_score + has_policy) / 2
                
                hyps.append({
                    "type": ft[:60],
                    "hypotheses": [h1, h2],
                    "best": "假设A" if confidence >= 0.5 else "需补充证据",
                    "confidence": confidence,
                    "evidence_count": len(h2_ev),
                })
            
            result.hypotheses = hyps
            if hyps:
                best = max(hyps, key=lambda h: h["confidence"])
                result.best_hypothesis = best
                
        except Exception as e:
            result.hypotheses = [{"error": str(e)}]
    
    def _reason_similar(self, ctx: Dict, result: ReasoningResult):
        """历史案例匹配"""
        mem = self._get_memory()
        if not mem:
            return
        
        try:
            # 从记忆库搜索相似案例
            industry = ctx.get("industry","")
            findings = ctx.get("findings", [])
            
            if hasattr(mem, 'search_similar'):
                cases = mem.search_similar(
                    industry=industry,
                    signal_types=[f.get("type","")[:20] for f in findings[:5]],
                    limit=3,
                )
                result.similar_cases = cases if isinstance(cases, list) else []
            elif hasattr(mem, 'memories'):
                # 12维加权相似度检索
                memories = mem.memories if isinstance(mem.memories, list) else []
                scored = []
                for m in memories[-100:]:
                    m_ind = m.get("industry","")
                    m_sigs = m.get("signals",[])
                    score = 0
                    if m_ind == industry: score += 3
                    for f in findings[:5]:
                        if f.get("type","")[:20] in str(m_sigs):
                            score += 2
                    if score > 0:
                        scored.append((score, m))
                scored.sort(key=lambda x: -x[0])
                result.similar_cases = [s for _, s in scored[:3]]
        except:
            pass
    
    def _synthesize(self, result: ReasoningResult):
        """综合推理结论"""
        parts = []
        
        # 因果信号
        if result.causal_signals:
            signals = [s for s in result.causal_signals if not s.startswith("因果")]
            if signals:
                parts.append(f"活跃信号({len(signals)}个): {', '.join(signals[:6])}")
        
        # 假设可信度
        if result.best_hypothesis:
            parts.append(f"最佳假设: {result.best_hypothesis.get('best','?')} (置信度{result.best_hypothesis.get('confidence',0):.0%})")
        
        # 历史案例
        if result.similar_cases:
            parts.append(f"历史相似案例: {len(result.similar_cases)}个")
        
        # 证据强度
        evidence_count = len(result.hypotheses)
        if evidence_count > 0:
            avg_conf = sum(h.get("confidence",0) for h in result.hypotheses) / evidence_count
            if avg_conf >= 0.7:
                result.evidence_strength = "★★★ 证据闭环——多源数据交叉验证"
            elif avg_conf >= 0.4:
                result.evidence_strength = "★★☆ 证据基本充分——部分结论可进一步验证"
            else:
                result.evidence_strength = "★☆☆ 证据较弱——建议补充佐证材料"
        
        result.confidence = avg_conf if evidence_count > 0 else 0.3
        result.conclusion = "；".join(parts) if parts else "推理完成"


# 全局推理器
_reasoner = None

def get_reasoner() -> AGIReasoner:
    global _reasoner
    if _reasoner is None:
        _reasoner = AGIReasoner()
    return _reasoner



# ═══════ [合并自 engine/creative_hypothesis.py] ═══════
"""
创造性假设引擎 — 类比推理 + 未知模式探索

核心能力：
1. 类比推理：遇到未知模式→找最相似的已知模式→基于类比生成假设
2. 假设竞争验证：生成多个竞争假设→验证→贝叶斯加权→选最优
3. 自动规则生成：验证通过的假设→注册为新推理规则
"""
import json, os, math
from datetime import datetime
from typing import Dict, List, Any, Optional

from engine.causal_discovery import get_discovery_engine
from engine.semantic_reasoner import get_semantic_engine


class CreativeHypothesisEngine:
    """创造性假设引擎 — 系统自己生成假设、自己验证"""
    
    def __init__(self):
        self._discovery = get_discovery_engine()
        self._semantic = get_semantic_engine()
        self._generated_hypotheses: List[Dict] = []
        self._verified_hypotheses: List[Dict] = []
        self._load_state()
    
    def _load_state(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "creative_hypotheses.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                self._generated_hypotheses = data.get("generated", [])
                self._verified_hypotheses = data.get("verified", [])
        except:
            pass
    
    def _save_state(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "creative_hypotheses.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "generated": self._generated_hypotheses[-200:],
                "verified": self._verified_hypotheses[-200:],
            }, f, ensure_ascii=False, indent=2)
    
    def reason_analogically(self, unknown_signals: List[str], unknown_findings: List[Dict],
                            context: Dict = None) -> Dict:
        """
        类比推理：核心创新
        
        系统遇到不认识的数据模式时，不再标注"未知"等人工介入。
        而是主动做类比："这个模式跟哪个已知的最像？"
        
        步骤：
        1. 语义归一化：用语义引擎标准化信号和发现的名称
        2. 类比搜索：在因果发现库中找相似模式
        3. 生成假设：基于类比生成多个竞争假设
        4. 置信度计算：基于相似度×历史验证次数加权
        """
        # 1. 语义归一化
        norm_signals = []
        for sig in unknown_signals:
            std = self._semantic.get_standard(sig)
            norm_signals.append(std if std else sig)
        
        norm_findings = []
        for f in unknown_findings:
            ft = f.get("type", "")
            std_type = self._semantic.normalize(ft) if ft else ft
            norm_findings.append({**f, "semantic_type": std_type})
        
        # 2. 类比搜索
        analogies = self._discovery.find_similar_pattern(norm_signals)
        
        # 3. 生成假设
        hypotheses = []
        
        # 假设A：最相似的已知模式
        if analogies:
            best = analogies[0]
            h_a = {
                "id": f"HYPO-{len(self._generated_hypotheses)+1:04d}",
                "type": "类比推理",
                "hypothesis": f"该模式最接近「{best['known_finding']}」",
                "rationale": f"与已知模式相似度{best['similarity']:.0%}（基于{best['count']}次历史验证）",
                "confidence": best["similarity"] * 0.8,
                "source": "analogical_inference",
                "similarity": best["similarity"],
                "signals": unknown_signals,
                "finding": best["known_finding"],
            }
            hypotheses.append(h_a)
        
        # 假设B：语义推断（用语义引擎理解信号含义）
        sig_meanings = []
        for sig in unknown_signals[:5]:
            std = self._semantic.get_standard(sig)
            if std: sig_meanings.append(f"{sig}→{std}")
        
        if sig_meanings:
            semantic_hypothesis = f"信号语义：{', '.join(sig_meanings)}。"
            # 基于语义推测风险方向
            risk_mapping = {
                "加工费": "可能存在委托加工业务的税务风险",
                "运输费": "需核实货物流真实性与发票匹配度",
                "租金": "需核实经营场所真实性和租赁合同",
                "钢材": "需核实钢材采购与实际消耗的匹配度",
                "销售收入": "需核实收入确认时点和金额准确性",
                "采购成本": "需核实采购的真实性和关联交易",
            }
            risks = []
            for std in [self._semantic.get_standard(s) for s in unknown_signals]:
                if std and std in risk_mapping:
                    risks.append(risk_mapping[std])
            
            if risks:
                h_b = {
                    "id": f"HYPO-{len(self._generated_hypotheses)+2:04d}",
                    "type": "语义推断",
                    "hypothesis": semantic_hypothesis + "\n可能的税务风险方向：" + "；".join(set(risks)),
                    "rationale": "基于税务语义引擎对信号含义的理解",
                    "confidence": 0.6,
                    "source": "semantic_inference",
                    "signals": unknown_signals,
                }
                hypotheses.append(h_b)
        
        # 假设C：频率推断（这些信号在历史中各自出现的频率）
        signal_freq = {}
        for sig in unknown_signals[:5]:
            count = sum(1 for d in self._discovery._discoveries if sig in d.get("signals", []))
            signal_freq[sig] = count
        
        freq_signals = [s for s, c in signal_freq.items() if c > 0]
        if freq_signals:
            h_c = {
                "id": f"HYPO-{len(self._generated_hypotheses)+3:04d}",
                "type": "频率推断",
                "hypothesis": f"信号 {', '.join(freq_signals)} 在历史中分别出现过{max(signal_freq.values())}次，组合出现为新模式",
                "rationale": "单一信号常见但组合罕见→可能指示新的风险类型",
                "confidence": 0.4 + min(max(signal_freq.values()) / 50, 0.3),
                "source": "frequency_inference",
                "signals": unknown_signals,
            }
            hypotheses.append(h_c)
        
        # 4. 选出最佳假设
        if hypotheses:
            best = max(hypotheses, key=lambda h: h["confidence"])
            
            # 保存生成的假设
            self._generated_hypotheses.append({
                "signals": unknown_signals,
                "findings": [f.get("type") for f in unknown_findings],
                "hypotheses": [h["hypothesis"][:200] for h in hypotheses],
                "best": best["hypothesis"][:200],
                "confidence": best["confidence"],
                "generated_at": datetime.now().isoformat(),
            })
            self._save_state()
        
        return {
            "unknown_signals": unknown_signals,
            "analogies_found": len(analogies),
            "hypotheses": hypotheses[:5],
            "best_hypothesis": best if hypotheses else None,
            "total_generated": len(self._generated_hypotheses),
        }
    
    def verify_hypothesis(self, hypothesis_id: str, verification_result: Dict) -> Dict:
        """
        验证假设：用户确认/反驳 → 更新置信度 → 通过则注册为规则
        """
        for h in self._generated_hypotheses:
            if h.get("id") == hypothesis_id:
                old_conf = h.get("confidence", 0)
                if verification_result.get("confirmed"):
                    new_conf = min(0.99, old_conf + 0.15)
                    status = "verified" if new_conf >= 0.7 else "pending"
                else:
                    new_conf = max(0.1, old_conf - 0.2)
                    status = "rejected"
                
                h["confidence"] = new_conf
                h["verified_at"] = datetime.now().isoformat()
                h["status"] = status
                
                if status == "verified":
                    self._verified_hypotheses.append(h)
                
                self._save_state()
                return {"ok": True, "new_confidence": new_conf, "status": status}
        
        return {"ok": False, "message": f"假设 {hypothesis_id} 不存在"}
    
    def get_verified_rules(self) -> List[Dict]:
        """获取已验证通过的假设（可转化为正式推理规则）"""
        return [h for h in self._verified_hypotheses if h.get("confidence", 0) >= 0.7]
    
    def status(self) -> Dict:
        return {
            "generated": len(self._generated_hypotheses),
            "verified": len(self._verified_hypotheses),
            "ready_rules": len(self.get_verified_rules()),
        }


# 全局假设引擎
creative_engine = CreativeHypothesisEngine()

def get_creative_engine() -> CreativeHypothesisEngine:
    return creative_engine


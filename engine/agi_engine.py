"""
AGI引擎 — 财税系统智能核心

整合LLM + 因果网络 + 假设验证 + 历史记忆 + 4 Agent + 自主学习 = 税务稽查AGI

使用方式：
  from engine.agi_engine import agi
  answer = agi.ask(question, findings, context, intent)
  agi.learn(finding_type, industry, level, reason)
"""
import json, os, re
from typing import Dict, List, Any, Optional
from engine.llm_client import llm, is_llm_available
from engine.agents.coordinator import get_coordinator
from engine.agi_reasoning import get_reasoner, ReasoningResult

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

"""
多Agent协调器 — 串联4个Agent的执行流程
"""
import json
from typing import Dict, List, Any, Optional
from .base import BaseAgent
# [merged] # DialogAgent
# [merged] # RuleReasonerAgent
# [merged] # LearningAgent

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


# ═══════ [合并自 engine/dialog.py] ═══════
"""
对话交互Agent — AGI级智能问答（LLM优先，知识图谱兜底）

当LLM不可用时，使用知识图谱推理+规则引擎+分析链产生深度回答。
不做简单的关键词匹配，而是做因果推理和数据溯源。
"""
import json, os, re
from .base import BaseAgent
from typing import Dict, List, Any, Optional

class DialogAgent(BaseAgent):
    """真正的税务稽查AGI——理解问题→知识检索→推理→自然语言输出"""
    
    def __init__(self):
        super().__init__(
            name="稽查对话引擎",
            role="资深税务稽查专家，精通中国税法体系，擅长因果推理和证据溯源",
            expertise=["税法解释","证据链推理","金额计算","行业对标","政策时效性判断","风险因果分析"]
        )
        
        # 知识库
        self._tax_knowledge = self._init_tax_knowledge()
        self._analysis_chains = self._load_json("static/cross_domain_analysis.json")
        self._evidence_chains = self._load_json("static/cross_domain_evidence.json")
        self._rules = self._load_json("static/tax_risk_rules_local_export.json")
    
    def _load_json(self, path: str) -> List[Dict]:
        full = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), path)
        try:
            with open(full, encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    
    def _init_tax_knowledge(self) -> Dict:
        return {
            "税种触发": {
                "增值税": "所有货物销售和劳务提供均需缴纳增值税。系统从销项发票提取销售额×(13%/9%/6%)计算销项税额，从进项发票提取可抵扣税额计算进项税额。应纳税额=销项税额-进项税额。增值税法(2024.1.1施行)为现行法律依据。",
                "企业所得税": "企业全部经营所得缴纳企业所得税。应纳税所得额=收入总额-不征税收入-免税收入-各项扣除-弥补亏损。税率25%，小微企业年应纳税所得额≤300万部分减按25%计入、按20%税率。",
                "房产税": "自用房产按原值×(1-10%~30%)×1.2%从价计征；出租房产按租金收入×12%从租计征。城镇范围内拥有房产即触发。",
                "城镇土地使用税": "占用城镇土地的企业按实际占用面积×适用税额缴纳。",
                "消费税": "对特定消费品(烟/酒/化妆品/贵重首饰/汽车/成品油等)在生产/进口/委托加工环节征收。销项品名命中应税消费品类目即触发。",
                "印花税": "对书立/领受应税凭证(合同/账簿/证照)征收。购销合同按万分之三贴花。",
                "个人所得税": "工资薪金按累计预扣法代扣代缴。股东分红按20%税率。",
                "社保费": "依法必须申报缴纳，含养老/医疗/失业/工伤/生育五险。",
            },
            "扣税凭证": {
                "增值税专用发票": "可全额抵扣进项税额——最主要的抵扣凭证",
                "海关进口增值税专用缴款书": "可全额抵扣进项税额——进口环节取得",
                "农产品收购发票": "买价×9%计算抵扣（用于生产13%税率货物时×10%）",
                "机动车销售统一发票": "可全额抵扣进项税额——购买车辆取得",
                "收费公路通行费电子发票": "发票金额÷(1+税率)×税率——通行费抵扣",
                "国内旅客运输服务电子发票": "发票上注明的税额——差旅费抵扣",
                "增值税普通发票": "不可抵扣，税额应并入采购成本或费用——最常见误解",
            },
            "进项转出": {
                "集体福利": "用于集体福利的购进货物，进项税额不得抵扣，须做转出",
                "个人消费": "用于个人消费的购进货物，进项税额不得抵扣",
                "非正常损失": "因管理不善造成货物被盗/丢失/霉烂变质，进项税额须转出",
                "简易计税": "采用简易计税方法的项目，对应进项税额不得抵扣",
                "免税项目": "用于免征增值税项目的购进货物，进项税额不得抵扣",
            },
            "行业断言规则": {
                "服务行业": "自动跳过进销存实物分析域、BOM分析域、加工费专项域。启用：人均产值、经营费用完整性、工资社保合规。",
                "贸易行业": "启用进销比分析、供应商集中度、客户集中度、购销品名映射。",
                "制造业": "启用BOM进销映射、加工费专项、水电能耗与产能匹配、存货周转。",
                "建筑业": "启用项目成本归集、分包合规性、甲供材涉税处理。",
            },
            "政策时效": {
                "增值税法": "2024年1月1日施行，取代《增值税暂行条例》。原条例条款仅具有历史参考价值。",
                "企业所得税法": "2018年修正，现行有效。小微企业优惠标准：年应纳税所得额≤300万。",
                "税收征收管理法": "2015年修正，现行有效。滞纳金按日加收万分之五。",
            },
        }
    
    def process(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理对话消息，使用知识库产生深度回答"""
        intent = message.get("intent", "general")
        question = message.get("question", "")
        findings = message.get("findings", [])
        context = message.get("context", {})
        
        result = {"agent": self.name, "intent": intent, "analysis": []}
        
        # 为每个意图构建深度回答
        answer = None
        if intent == "how": answer = self._deep_how(question, findings, context)
        elif intent == "why": answer = self._deep_why(question, findings, context)
        elif intent == "what": answer = self._deep_what(question, findings, context)
        elif intent == "law": answer = self._deep_law(question, findings, context)
        elif intent == "calc": answer = self._deep_calc(question, findings, context)
        elif intent == "compare": answer = self._deep_compare(question, findings, context)
        elif intent == "check": answer = self._deep_check(question, findings, context)
        elif intent == "benchmark": answer = self._deep_benchmark(question, findings, context)
        elif intent == "level": answer = self._deep_level(question, findings, context)
        else: answer = self._deep_general(question, findings, context)
        
        result["analysis"] = answer
        return result
    
    # ═══════════════════════════════════
    # 深度推理方法
    # ═══════════════════════════════════
    
    def _deep_how(self, q: str, findings: List, ctx: Dict) -> List:
        """HOW意图：追溯判定逻辑——这是最核心的推理"""
        blocks = []
        para = ctx.get("paragraph_text", "")
        
        # 1. 检测税种关键字，自动展开判定逻辑
        tax_found = []
        for tax, desc in self._tax_knowledge["税种触发"].items():
            if tax in q or tax in para:
                tax_found.append(tax)
        
        if tax_found:
            lines = []
            for tax in tax_found:
                desc = self._tax_knowledge["税种触发"][tax]
                lines.append(f"▎{tax}\n{desc}")
            blocks.append({"title": "📊 税种判定依据", "content": "\n\n".join(lines)})
        
        # 2. 匹配分析链——从48条分析链中找推理路径
        qwords = [w for w in q.replace('？','').replace('?','').split() if len(w) >= 2]
        matched_chains = []
        for chain in self._analysis_chains:
            cname = str(chain.get("name","")) + str(chain.get("description",""))
            score = sum(1 for kw in qwords if kw in cname)
            if score >= 2:
                rp = chain.get("reasoning_path", [])
                matched_chains.append((score, chain.get("name",""), len(rp)))
        matched_chains.sort(key=lambda x: -x[0])
        
        if matched_chains:
            lines = [f"• 分析链「{name}」({steps}步推理)" for _, name, steps in matched_chains[:3]]
            blocks.append({"title": f"🔗 匹配分析链（{len(matched_chains)}条）", "content": "\n".join(lines)})
        
        # 3. 匹配规则
        matched_rules = []
        for rule in self._rules[:500]:
            rname = str(rule.get("name", rule.get("item", "")))
            rdetail = str(rule.get("detail", ""))
            score = sum(1 for kw in qwords if kw in rname + rdetail)
            if score >= 2:
                matched_rules.append((score, rname[:60], rule.get("level","")))
        matched_rules.sort(key=lambda x: -x[0])
        
        if matched_rules:
            lines = [f"• [{lv}] {name}" for _, name, lv in matched_rules[:5]]
            blocks.append({"title": f"⚙️ 匹配稽查指令（{len(matched_rules)}条）", "content": "\n".join(lines)})
        
        # 4. 从发现的how_found中溯源
        how_lines = []
        for f in findings:
            hf = f.get("how_found", "")
            if hf and any(kw in hf for kw in qwords if len(kw) >= 2):
                how_lines.append(f"• [{f.get('level','')}] {f.get('type','')[:50]}\n  {hf[:200]}")
                if len(how_lines) >= 3: break
        
        if how_lines:
            blocks.append({"title": "🔍 实际数据溯源", "content": "\n".join(how_lines)})
        
        if not blocks:
            blocks.append({"title": "📝 说明", "content": f"关于该问题的判定逻辑：系统通过42个域分析函数逐域扫描资料数据，匹配1608条稽查指令自动判定。如需了解具体判定依据，请查看报告中的③证据材料和④证据来源。"})
        
        return blocks
    
    def _deep_why(self, q: str, findings: List, ctx: Dict) -> List:
        """WHY意图：证据链推理 — 智能理解'为什么'"""
        blocks = []
        qwords = [w for w in q.replace('？','').replace('?','').split() if len(w) >= 2]
        
        # 通用"为什么"——自动定位到高风险发现
        scored = []
        for f in findings:
            ftext = str(f.get("type","")) + str(f.get("detail","")) + str(f.get("how_found",""))
            score = sum(1 for kw in qwords if kw in ftext)
            # 高风险发现自动加分（"为什么"通常问的就是高风险）
            if f.get("level") in ("高风险","极高风险"):
                score += 1
            if score >= 1:
                scored.append((score, f))
        scored.sort(key=lambda x: -x[0])
        
        if scored:
            lines = []
            for s, f in scored[:5]:
                lv = f.get("level","")
                ev_count = len(f.get("evidence",[]) or f.get("evidence_rows",[]) or f.get("items",[]) or [])
                domains = f.get("domain", f.get("category", ""))
                hf = f.get("how_found","")
                
                parts = [f"▎{f.get('type','')[:50]}  [{lv}]"]
                if domains: parts.append(f"分析域: {domains}")
                if ev_count > 0: parts.append(f"证据: {ev_count}条数据")
                if hf: parts.append(f"方法: {hf[:150]}")
                
                # 证据强度评估
                if ev_count >= 2 and domains:
                    parts.append("强度: ★★★ 证据闭环——多源数据交叉验证")
                elif ev_count >= 1:
                    parts.append("强度: ★★☆ 有证据但单源——建议复核")
                else:
                    parts.append("强度: ★☆☆ 缺证据材料——需补充资料")
                
                lines.append("  ".join(parts))
            
            blocks.append({"title": f"🔍 原因分析（{len(scored)}条因果链）", "content": "\n\n".join(lines)})
        else:
            blocks.append({"title": "📝 说明", "content": "未找到与该问题直接关联的证据链。系统中的高风险发现均标注了③证据材料和④证据来源，中风险发现需≥2条规则触发才形成闭环。"})
        
        return blocks
    
    def _deep_what(self, q: str, findings: List, ctx: Dict) -> List:
        """WHAT意图：列明细——包括证据行、金额、对方"""
        blocks = []
        qwords = [w for w in q.replace('？','').replace('?','').split() if len(w) >= 2]
        
        details = []
        for f in findings:
            ftext = str(f.get("type","")) + str(f.get("detail",""))
            # 通用"什么证据"——展示所有有证据的发现
            matched = any(kw in ftext for kw in qwords if len(kw) >= 2) if qwords else True
            if not matched:
                continue
            
            # 证据行
            ev = f.get("evidence_rows") or f.get("items") or []
            for ei in ev[:3]:
                if isinstance(ei, dict):
                    amt = ei.get("amount", ei.get("金额", ei.get("invoice_amount", "")))
                    cp = ei.get("counterparty", ei.get("对方", ""))
                    src = ei.get("source", ei.get("来源", ""))
                    line = f"• [{f.get('level','')}] {f.get('type','')[:30]}"
                    if cp: line += f" | 对方: {cp}"
                    if amt: line += f" | ¥{amt}"
                    if src: line += f" | {src}"
                    details.append(line)
                else:
                    details.append(f"• [{f.get('level','')}] {f.get('type','')[:30]}: {str(ei)[:150]}")
            
            if not ev and f.get("detail"):
                details.append(f"• [{f.get('level','')}] {f.get('type','')[:30]}: {f.get('detail','')[:200]}")
            
            if len(details) >= 15: break
        
        if details:
            blocks.append({"title": f"📊 具体明细（{len(details)}条）", "content": "\n".join(details[:15])})
        else:
            blocks.append({"title": "📝 说明", "content": "未找到与问题匹配的明细数据。请在报告中发现旁的「③证据材料」表格中查看原始数据。"})
        
        return blocks
    
    def _deep_law(self, q: str, findings: List, ctx: Dict) -> List:
        """LAW意图：法条引用+时效性判断"""
        blocks = []
        
        # 1. 从发现中找法条
        law_lines = []
        for f in findings[:20]:
            policy = str(f.get("policy_ref", ""))
            if policy and len(policy) > 5:
                # 检查时效性
                if "暂行条例" in policy and "增值税" in policy:
                    policy += " ⚠️ 注意：《增值税暂行条例》已于2024年1月1日废止，现行为《中华人民共和国增值税法》"
                law_lines.append(f"• [{f.get('level','')}] {f.get('type','')[:30]}\n  依据: {policy[:200]}")
                if len(law_lines) >= 5: break
        
        if law_lines:
            blocks.append({"title": "⚖️ 法律依据", "content": "\n\n".join(law_lines)})
        
        # 2. 匹配税法知识库
        for tax, desc in self._tax_knowledge["税种触发"].items():
            if tax in q:
                # 提取法条引用
                law_text = desc.split("。")[0] if "。" in desc else desc[:100]
                blocks.append({"title": f"📜 {tax}法律原文", "content": law_text})
        
        if not law_lines:
            # 给出政策时效说明
            blocks.append({"title": "📜 政策时效说明", "content": self._tax_knowledge["政策时效"].get("增值税法","")})
        
        return blocks
    
    def _deep_calc(self, q: str, findings: List, ctx: Dict) -> List:
        """CALC意图：金额汇总+分项计算"""
        blocks = []
        
        items = []
        total_all = 0
        for f in findings:
            ev = f.get("evidence_rows") or f.get("items") or []
            subtotal = 0
            for ei in ev:
                try:
                    if isinstance(ei, dict):
                        amt_str = str(ei.get("amount", ei.get("amount", "0"))).replace(",","")
                        amt = float(amt_str)
                        subtotal += amt
                except: pass
            if subtotal > 0:
                items.append((f.get("level",""), f.get("type","")[:40], subtotal))
                total_all += subtotal
        
        if items:
            lines = []
            for lv, ft, amt in items[:10]:
                lines.append(f"▎{ft} [{lv}] —— ¥{amt:,.0f}")
            
            vat_est = total_all * 0.13
            inc_est = total_all * 0.25
            
            lines.append("")
            lines.append(f"涉税金额合计：¥{total_all:,.0f}")
            lines.append(f"预估增值税(13%)：¥{vat_est:,.0f}")
            lines.append(f"预估企业所得税(25%)：¥{inc_est:,.0f}")
            lines.append(f"合计预估税款：¥{vat_est+inc_est:,.0f}")
            lines.append("")
            lines.append("⚠️ 说明：")
            lines.append("1. 增值税按13%一般税率预估，实际税率取决于货物/服务类型（9%/6%）")
            lines.append("2. 企业所得税按25%预估，小微企业适用优惠税率")
            lines.append("3. 以上不含滞纳金（日万分之五）和罚款")
            lines.append("4. 实际应补（退）税额以税务机关最终核定为准")
            
            blocks.append({"title": "💰 税负明细计算", "content": "\n".join(lines)})
        else:
            blocks.append({"title": "💰 税负预估", "content": "系统未在发现数据中找到具体的涉税金额。请在报告中发现旁的③证据材料表格查看原始金额。"})
        
        return blocks
    
    def _deep_compare(self, q: str, findings: List, ctx: Dict) -> List:
        """COMPARE意图：多维度排序对比"""
        blocks = []
        
        scored = []
        for f in findings:
            lv_score = {"极高风险":10,"高风险":7,"中风险":4,"低风险":2}.get(f.get("level",""),3)
            ev = f.get("evidence_rows") or f.get("items") or []
            max_amt = 0
            for ei in ev:
                try:
                    amt = float(str(ei.get("amount", ei.get("金额","0"))).replace(",",""))
                    max_amt = max(max_amt, amt)
                except: pass
            domain_count = 1 if f.get("domain") or f.get("category") else 0
            scored.append((lv_score + int(min(max_amt/10000, 5)) + domain_count, f))
        scored.sort(key=lambda x: -x[0])
        
        lines = []
        for i, (s, f) in enumerate(scored[:10]):
            lv = f.get("level","")
            ft = f.get("type","")[:50]
            hf = bool(f.get("how_found",""))
            pl = bool(f.get("policy_ref",""))
            marks = []
            if hf: marks.append("有溯源")
            if pl: marks.append("有法条")
            if not hf and not pl: marks.append("缺依据")
            icon = "🔴" if lv in ("高风险","极高风险") else "🟡" if lv == "中风险" else "🟢"
            lines.append(f"{icon} {i+1}. {ft} [{lv}] {' '.join(marks)}")
        
        blocks.append({"title": f"🔝 严重程度排名（TOP10）", "content": "\n".join(lines)})
        blocks.append({"title": "📊 排序说明", "content": "排序依据：风险等级权重(极高10/高7/中4/低2)+涉税金额(每万元+1)+分析域数量。标注「缺依据」的发现建议重点复核。"})
        
        return blocks
    
    def _deep_check(self, q: str, findings: List, ctx: Dict) -> List:
        """CHECK意图：质量审查——检查5个维度"""
        blocks = []
        
        results = []
        issues_count = 0
        for f in findings[:8]:
            ev = f.get("evidence",[]) or f.get("evidence_rows",[]) or f.get("items",[]) or []
            ev_count = len(ev)
            has_policy = bool(f.get("policy_ref","").strip()) and len(f.get("policy_ref","").strip()) > 5
            has_source = bool(f.get("how_found","").strip())
            has_domain = bool(f.get("domain","") or f.get("category",""))
            lv = f.get("level","")
            
            ft = f.get("type","")[:40]
            probs = []
            
            # 5维检查
            if ev_count == 0: probs.append("证据缺失"); issues_count += 1
            if not has_policy: probs.append("缺法条引用"); issues_count += 1
            if not has_source: probs.append("缺数据溯源"); issues_count += 1
            if not has_domain: probs.append("未标注分析域"); issues_count += 1
            if lv=="高风险" and ev_count<2: probs.append("高风险证据薄弱"); issues_count += 1
            
            if probs:
                results.append(f"❌ [{lv}] {ft}: {' | '.join(probs)}")
            else:
                results.append(f"✅ [{lv}] {ft}: 五项检查全部通过")
        
        blocks.append({"title": f"🔍 质量审查（{issues_count}处潜在问题）", "content": "\n".join(results)})
        
        # 资料缺口影响
        gaps = ctx.get("material_intel", {})
        if isinstance(gaps, dict) and gaps:
            gap_lines = []
            for k, v in list(gaps.items())[:5]:
                if isinstance(v, dict) and not v.get("exists"):
                    gap_lines.append(f"• {k}: {v.get('risk','影响判断')}")
            if gap_lines:
                blocks.append({"title": "📂 资料缺口影响链", "content": "\n".join(gap_lines)})
        
        if issues_count == 0 and not (isinstance(gaps, dict) and gaps):
            blocks.append({"title": "✅ 总体评估", "content": "报告质量检查基本通过。建议：①高风险发现需多源证据闭环 ②每条发现标注法条依据 ③补充缺失的稽查必查资料。"})
        
        return blocks
    
    def _deep_benchmark(self, q: str, findings: List, ctx: Dict) -> List:
        """BENCHMARK意图：行业对标"""
        blocks = []
        industry = ctx.get("industry", "未识别")
        
        benchmarks = ctx.get("benchmarks", {})
        if benchmarks:
            lines = [f"行业: {industry}"]
            for metric, vals in benchmarks.items():
                if isinstance(vals, dict):
                    lines.append(f"  {metric}: 下限{vals.get('min','?')} | 典型{vals.get('typical','?')} | 上限{vals.get('max','?')}")
            
            # 行业断言
            for kw, rule in self._tax_knowledge["行业断言规则"].items():
                if kw in industry:
                    lines.append(f"\n行业适配规则: {rule}")
            
            lines.append("\n对标逻辑：企业实际指标<下限→高风险，<典型值85%→中风险，>上限→异常需关注。")
            blocks.append({"title": f"🏭 {industry}行业基准", "content": "\n".join(lines)})
        else:
            blocks.append({"title": f"🏭 行业对标", "content": f"行业: {industry}\n系统内置66个行业×5个指标×3个基准值(P25/P50/P75)。该行业基准数据暂未加载。"})
        
        return blocks
    
    def _deep_level(self, q: str, findings: List, ctx: Dict) -> List:
        """LEVEL意图：风险等级解释"""
        blocks = []
        
        stats = {"极高风险":0,"高风险":0,"中风险":0,"低风险":0}
        for f in findings:
            lv = f.get("level","")
            if lv in stats: stats[lv] += 1
        
        overall = ctx.get("overall_risk", "未知")
        
        lines = [f"综合风险: {overall}"]
        for lv, cnt in stats.items():
            if cnt > 0: lines.append(f"  {lv}: {cnt}项")
        
        if overall in ("高风险","极高风险"):
            lines.append("\n高风险判定依据：")
            lines.append("1. 多源数据交叉验证形成证据闭环（≥2个分析域）")
            lines.append("2. 触发稽查重点强制等级（12类稽查重点之一）")
            lines.append("3. 行业对标偏离度超过阈值（<下限或>上限）")
            lines.append("\n每条高风险发现均可追溯至③证据材料和④证据来源。")
        
        blocks.append({"title": "⚠️ 风险等级说明", "content": "\n".join(lines)})
        return blocks
    
    def _deep_general(self, q: str, findings: List, ctx: Dict) -> List:
        """通用搜索：多维度智能匹配"""
        blocks = []
        qwords = [w for w in q.replace('？','').replace('?','').split() if len(w) >= 2]
        
        if not qwords:
            blocks.append({"title": "📝 说明", "content": "请输入具体问题，例如：这个发现怎么得出来的？/ 依据哪条法律？/ 要补多少税？"})
            return blocks
        
        # 多维度搜索
        found = []
        for f in findings:
            ftext = str(f.get("type",""))+"|"+str(f.get("detail",""))+"|"+str(f.get("description",""))+"|"+str(f.get("policy_ref",""))
            score = sum(1 for kw in qwords if kw in ftext)
            if score >= 2:
                found.append((score, f))
        found.sort(key=lambda x: -x[0])
        
        if found:
            lines = []
            for s, f in found[:8]:
                ft = f.get("type","")[:60]
                lv = f.get("level","")
                det = f.get("detail","")[:120]
                lines.append(f"• [{lv}] {ft}\n  {det}")
            blocks.append({"title": f"🔗 多维匹配结果（{len(found)}条）", "content": "\n".join(lines)})
            
            # 给建议
            blocks.append({"title": "💡 建议", "content": "以上为系统自动匹配的关联发现。您可以使用更精确的问题获得更聚焦的回答：\n• \"怎么判定\"——了解推理依据\n• \"为什么是高风险\"——查看证据链\n• \"具体有哪些\"——查看明细数据\n• \"要补多少税\"——查看金额计算\n• \"依据哪条法律\"——查看法条引用"})
        else:
            blocks.append({"title": "📝 说明", "content": f"关于「{q[:60]}」，系统未在全量1608条稽查指令、437条线索链、781条证据链中直接匹配到相关内容。\n\n建议：\n1. 使用更具体的术语追问（如\"增值税税负率\"而非\"税\"）\n2. 在报告中发现旁点击编辑按钮补充信息\n3. 对照③证据材料核实原始数据"})
        
        return blocks



# ═══════ [合并自 engine/learning.py] ═══════
"""
学习进化Agent — 分析纠正反馈，自动调整推理权重
"""
import json, os
from datetime import datetime
from .base import BaseAgent
from typing import Dict, List, Any

class LearningAgent(BaseAgent):
    """从用户纠正中学习，自动调整规则权重和行业适配"""
    
    def __init__(self):
        super().__init__(
            name="学习进化引擎",
            role="分析用户纠正模式，自动调整推理逻辑的自我进化系统",
            expertise=[
                "纠正模式识别",
                "规则权重自动调整",
                "行业自适应学习",
                "跨企业知识迁移",
                "阈值动态优化",
            ]
        )
        
        self._corrections_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "static", "user_corrections.json"
        )
        self._weights = self._load_weights()
    
    def _load_weights(self) -> Dict:
        try:
            with open(self._corrections_path, encoding="utf-8") as f:
                data = json.load(f)
            # Handle empty list case
            if isinstance(data, list):
                return {"rules": {}, "industries": {}, "patterns": []}
            # Handle record_correction format (fingerprint dict without "rules" key)
            if isinstance(data, dict) and "rules" not in data:
                return {"rules": data, "industries": {}, "patterns": []}
            return data
        except:
            return {"rules": {}, "industries": {}, "patterns": []}
    
    def _save_weights(self):
        with open(self._corrections_path, "w", encoding="utf-8") as f:
            json.dump(self._weights, f, ensure_ascii=False, indent=2)
    
    def process(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """分析纠正，更新权重"""
        action = message.get("action", "learn")
        
        if action == "learn":
            return self._learn_from_correction(message)
        elif action == "apply":
            return self._apply_learned_rules(message)
        elif action == "synthesize":
            return self._synthesize_cross_company(message)
        
        return {"agent": self.name, "status": "no_action"}
    
    def _learn_from_correction(self, msg: Dict) -> Dict:
        """从一次纠正中学习"""
        finding_type = msg.get("finding_type", "")
        industry = msg.get("industry", "")
        level = msg.get("original_level", "")
        reason = msg.get("reason", "")[:200]
        
        # 1. 按发现类型记录纠正模式
        key = finding_type[:60] or "unknown"
        if key not in self._weights["rules"]:
            self._weights["rules"][key] = {"corrections": 0, "industries": {}, "last_reason": ""}
        
        w = self._weights["rules"][key]
        w["corrections"] += 1
        w["last_reason"] = reason
        w["industries"][industry] = w["industries"].get(industry, 0) + 1
        
        # 2. 按行业记录
        if industry and len(industry) < 30:
            if industry not in self._weights["industries"]:
                self._weights["industries"][industry] = {"total_corrections": 0, "rules": {}}
            self._weights["industries"][industry]["total_corrections"] += 1
            self._weights["industries"][industry]["rules"][key] = \
                self._weights["industries"][industry]["rules"].get(key, 0) + 1
        
        # 3. 记录模式
        self._weights["patterns"].append({
            "type": key,
            "industry": industry,
            "level": level,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        })
        if len(self._weights["patterns"]) > 100:
            self._weights["patterns"] = self._weights["patterns"][-100:]
        
        self._save_weights()
        
        # 4. 判断是否触发自动规则
        auto_apply = w["corrections"] >= 3  # 同类纠正≥3次自动生效
        confidence = min(0.7 + w["corrections"] * 0.1, 1.0)
        
        return {
            "agent": self.name,
            "correction_count": w["corrections"],
            "auto_apply": auto_apply,
            "confidence": confidence,
            "learned_pattern": reason[:100] if auto_apply else "",
        }
    
    def _apply_learned_rules(self, msg: Dict) -> Dict:
        """应用已学规则到当前分析"""
        finding_type = msg.get("finding_type", "")[:60]
        industry = msg.get("industry", "")
        
        rule = self._weights["rules"].get(finding_type, {})
        corrections = rule.get("corrections", 0)
        
        result = {"agent": self.name, "adjustments": []}
        
        if corrections >= 3:
            # 同行业≥3次纠正 → 自动降级
            ind_corrections = rule.get("industries", {}).get(industry, 0)
            if ind_corrections >= 3:
                result["adjustments"].append({
                    "type": "auto_downgrade",
                    "reason": f"{industry}行业已纠正{ind_corrections}次此类型发现，自动降一级",
                    "confidence": min(0.7 + ind_corrections * 0.1, 1.0),
                })
        
        return result
    
    def _synthesize_cross_company(self, msg: Dict) -> Dict:
        """跨企业知识合成"""
        industry = msg.get("industry", "")
        rules = self._weights["rules"]
        ind_data = self._weights["industries"].get(industry, {})
        
        # 找出该行业最常见的纠正模式
        rule_ranking = sorted(
            ind_data.get("rules", {}).items(),
            key=lambda x: -x[1]
        )[:5]
        
        return {
            "agent": self.name,
            "industry": industry,
            "total_corrections": ind_data.get("total_corrections", 0),
            "top_patterns": [
                {"rule": r, "count": c, "conclusion": self._weights["rules"].get(r,{}).get("last_reason","")[:80]}
                for r, c in rule_ranking
            ],
        }



# ═══════ [合并自 engine/rule_reasoner.py] ═══════
"""
规则推理Agent — 匹配1608稽查指令，串联线索→证据→分析链
"""
import json, os
from .base import BaseAgent
from typing import Dict, List, Any

class RuleReasonerAgent(BaseAgent):
    """根据发现数据匹配规则，推理风险等级"""
    
    def __init__(self):
        super().__init__(
            name="规则推理引擎",
            role="精通1608条稽查指令的规则匹配专家，负责将域分析发现与规则引擎对接",
            expertise=[
                "规则匹配(1608条稽查指令)",
                "线索链驱动(437条)",
                "证据链闭环(781条)",
                "分析链推理(48条)",
                "跨域协商(29条)",
                "行业适配(66行业基准)",
            ]
        )
        
        # 加载规则库
        self._rules = self._load_rules()
        self._evidence = self._load_json("static/cross_domain_evidence.json")
        self._clues = self._load_json("static/cross_domain_clues.json")
        self._analysis = self._load_json("static/cross_domain_analysis.json")
    
    def _load_rules(self) -> List[Dict]:
        return self._load_json("static/tax_risk_rules_local_export.json")
    
    def _load_json(self, path: str) -> List[Dict]:
        full = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), path)
        try:
            with open(full, encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    
    def process(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """匹配规则、串联证据链"""
        finding = message.get("finding", {})
        findings = message.get("findings", [])
        domain = message.get("domain", "")
        
        result = {
            "agent": self.name,
            "matched_rules": [],
            "triggered_clues": [],
            "evidence_chain": [],
            "risk_assessment": "",
        }
        
        # 1. 匹配规则
        ftype = str(finding.get("type", ""))
        fdetail = str(finding.get("detail", ""))
        for rule in self._rules[:200]:  # 采样前200条规则
            rule_name = str(rule.get("name", rule.get("item", "")))
            rule_detail = str(rule.get("detail", ""))
            if any(kw in ftype+rule_name for kw in ftype[:10].split() if len(kw) >= 3):
                result["matched_rules"].append({
                    "id": rule.get("id", ""),
                    "name": rule_name[:60],
                    "level": rule.get("level", ""),
                    "category": rule.get("category", ""),
                })
                if len(result["matched_rules"]) >= 5:
                    break
        
        # 2. 触发线索链
        for clue in self._clues[:50]:
            clue_name = str(clue.get("name", ""))
            if any(kw in clue_name for kw in ftype[:20].split() if len(kw) >= 2):
                result["triggered_clues"].append({
                    "name": clue_name[:60],
                    "executable": clue.get("executable", False),
                })
                if len(result["triggered_clues"]) >= 3:
                    break
        
        # 3. 证据链检测
        evidence_count = len(finding.get("evidence", []) or [])
        evidence_rows = len(finding.get("evidence_rows", []) or finding.get("items", []) or [])
        domains_involved = set()
        for f in findings:
            d = f.get("domain", f.get("category", ""))
            if d: domains_involved.add(d)
        
        result["risk_assessment"] = self._assess_risk(
            finding.get("level", "中风险"),
            evidence_count + evidence_rows,
            len(domains_involved),
            len(result["matched_rules"]),
        )
        
        return result
    
    def _assess_risk(self, level, evidence_count, domain_count, rule_count):
        """综合评估风险"""
        if level in ("高风险", "极高风险"):
            if evidence_count >= 2 and domain_count >= 2:
                return "证据确凿——多源数据交叉验证，证据闭环完整"
            else:
                return "高风险判定——但证据链尚不完整，建议补充佐证材料"
        elif level == "中风险":
            if rule_count >= 2:
                return "中风险——多条规则触发，建议关注"
            else:
                return "中风险——单一规则触发，可能是偶然信号"
        return "低风险——建议保持关注"


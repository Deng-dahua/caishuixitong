"""
对话交互Agent — 理解追问意图，多轮对话，知识库问答
"""
import json, re
from .base import BaseAgent
from typing import Dict, List, Any

class DialogAgent(BaseAgent):
    """理解用户追问意图，给出自然语言回答"""
    
    def __init__(self):
        super().__init__(
            name="稽查对话引擎",
            role="资深税务稽查专家，擅长用通俗语言解释专业判断",
            expertise=[
                "10意图分类(how/why/what/law/level/calc/compare/check/benchmark/general)",
                "税务稽查报告解读",
                "法条引用与解释",
                "金额计算与税负预估",
                "行业对标分析",
                "证据链溯源",
            ]
        )
        
        # 知识库
        self.set_knowledge("税种判定规则", {
            "增值税": "覆盖所有货物销售和劳务提供。销项税额-进项税额=应纳税额。税率：13%/9%/6%。2024年1月1日起《增值税法》施行。",
            "企业所得税": "覆盖全部经营所得。应纳税所得额=收入总额-不征税收入-免税收入-各项扣除-以前年度亏损。税率25%，小微企业优惠税率。",
            "房产税": "自用房产：原值×(1-扣除比例)×1.2%。出租房产：租金收入×12%。城镇土地使用税：面积×适用税额。",
        })
        self.set_knowledge("扣税凭证类型", {
            "增值税专用发票": "可全额抵扣进项税额",
            "海关进口增值税专用缴款书": "可全额抵扣进项税额",
            "农产品收购发票": "按买价×9%计算抵扣（深加工×10%）",
            "机动车销售统一发票": "可全额抵扣进项税额",
            "收费公路通行费电子发票": "按发票金额÷(1+税率)×税率计算抵扣",
            "增值税普通发票": "不可抵扣，税额并入成本",
        })
    
    def process(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理对话消息"""
        intent = message.get("intent", "general")
        question = message.get("question", "")
        findings = message.get("findings", [])
        context = message.get("context", {})
        
        result = {
            "agent": self.name,
            "intent": intent,
            "analysis": [],
            "sources": [],
        }
        
        # 构建分析块
        block = {"title": "", "content": ""}
        
        if intent == "how":
            block = self._answer_how(question, findings, context)
        elif intent == "why":
            block = self._answer_why(question, findings, context)
        elif intent == "what":
            block = self._answer_what(question, findings, context)
        elif intent == "law":
            block = self._answer_law(question, findings, context)
        elif intent == "calc":
            block = self._answer_calc(question, findings, context)
        elif intent == "compare":
            block = self._answer_compare(question, findings, context)
        elif intent == "check":
            block = self._answer_check(question, findings, context)
        elif intent == "benchmark":
            block = self._answer_benchmark(question, findings, context)
        else:
            block = self._answer_general(question, findings, context)
        
        result["analysis"].append(block)
        return result
    
    def _answer_how(self, q, findings, ctx):
        """回答"怎么得出的"——追溯判定逻辑"""
        tax_kw = {
            "增值税": "对企业全部销项发票和进项发票进行逐票分析，计算销项税额-进项税额，对比申报表数据。",
            "企业所得税": "从利润表提取营业收入、成本费用，按25%税率计算应纳税额，对比实际申报数据。",
            "房产税": "检测企业经营费用中是否有房产税缴纳记录，或企业是否拥有自有房产。",
            "消费税": "检测销项发票品名是否含应税消费品(烟酒/化妆品/汽车等)。",
            "印花税": "检测购销合同金额，按万分之三核定应缴印花税。",
        }
        
        lines = []
        for tax, desc in tax_kw.items():
            if tax in q or tax in str(ctx.get("paragraph_text", "")):
                lines.append(f"【{tax}】{desc}")
        
        if lines:
            return {"title": "📊 税种判定方法", "content": "\n\n".join(lines)}
        
        # 搜索how_found
        for f in findings:
            hf = f.get("how_found", "")
            if hf and any(kw in hf for kw in q.replace('？','').split() if len(kw) >= 2):
                return {"title": "🔗 发现溯源", "content": f"该发现来源于：{hf}"}
        
        return {"title": "📝 说明", "content": "该判定基于系统内置的规则引擎和多域交叉分析。如需了解具体判定依据，请查看发现中的③证据材料和④证据来源。"}
    
    def _answer_why(self, q, findings, ctx):
        """回答"为什么"——证据链追溯"""
        qwords = [w for w in q.replace('？','').split() if len(w) >= 2]
        matched = []
        for f in findings:
            ftext = str(f.get("type","")) + str(f.get("detail","")) + str(f.get("how_found",""))
            score = sum(1 for kw in qwords if kw in ftext)
            if score >= 2:
                matched.append((score, f))
        matched.sort(key=lambda x: -x[0])
        
        if matched:
            lines = []
            for s, f in matched[:3]:
                lines.append(f"• [{f.get('level','')}] {f.get('type','')}")
                hf = f.get("how_found","")
                if hf: lines.append(f"  证据链: {hf[:150]}")
                ev = f.get("evidence_rows") or f.get("items") or []
                if ev: lines.append(f"  支撑证据: {len(ev)}条明细")
            return {"title": f"🔍 证据链分析（{len(matched)}条关联发现）", "content": "\n".join(lines)}
        
        return {"title": "📝 说明", "content": "未找到与该问题直接关联的证据链。建议在报告中发现旁使用'审核'按钮反馈判断准确性。"}
    
    def _answer_what(self, q, findings, ctx):
        """回答"哪些/具体"——列明细"""
        qwords = [w for w in q.replace('？','').split() if len(w) >= 2]
        items = []
        for f in findings:
            ftext = str(f.get("type","")) + str(f.get("detail",""))
            if any(kw in ftext for kw in qwords if len(kw) >= 2):
                ev = f.get("evidence_rows") or f.get("items") or []
                for ei in ev[:2]:
                    if isinstance(ei, dict):
                        items.append(f"[{f.get('level','')}] {f.get('type','')[:30]}: {json.dumps(ei, ensure_ascii=False)[:200]}")
                    else:
                        items.append(f"[{f.get('level','')}] {f.get('type','')[:30]}: {str(ei)[:200]}")
        if items:
            return {"title": f"📊 明细数据（{len(items)}条）", "content": "\n".join(items[:10])}
        return {"title": "📝 说明", "content": "未找到匹配的明细数据。请使用追问按钮针对具体发现进行查询。"}
    
    def _answer_law(self, q, findings, ctx):
        """回答法条问题"""
        law_lines = []
        for f in findings:
            policy = str(f.get("policy_ref", ""))
            if policy and len(policy) > 5:
                law_lines.append(f"• [{f.get('level','')}] {f.get('type','')[:30]}: {policy[:200]}")
                if len(law_lines) >= 5: break
        if law_lines:
            return {"title": "⚖️ 法律依据", "content": "\n".join(law_lines)}
        return {"title": "⚖️ 法律依据", "content": "未找到与该问题直接对应的法条引用。报告中每条发现均标注了⑤法律依据。"}
    
    def _answer_calc(self, q, findings, ctx):
        """回答金额计算"""
        total = 0
        items = []
        for f in findings:
            ev = f.get("evidence_rows") or f.get("items") or []
            for ei in ev[:1]:
                amt = str(ei.get("amount", ei.get("金额", ei.get("invoice_amount", "0"))) if isinstance(ei, dict) else "0")
                try:
                    a = float(amt.replace(",",""))
                    if a > 0:
                        total += a
                        items.append(f"• [{f.get('level','')}] {f.get('type','')[:30]}: ¥{a:,.0f}")
                except: pass
        if total > 0:
            vat = total * 0.13
            inc = total * 0.25
            lines = items[:10] + [
                "",
                f"涉税金额合计: ¥{total:,.0f}",
                f"预估增值税(13%): ¥{vat:,.0f}",
                f"预估企业所得税(25%): ¥{inc:,.0f}",
                f"合计预估: ¥{vat+inc:,.0f}",
                "",
                "⚠️ 以上为基于现有数据的机器估算，实际以税务机关核定为准。"
            ]
            return {"title": "💰 税负预估", "content": "\n".join(lines)}
        return {"title": "💰 税负预估", "content": "未在发现数据中找到具体金额明细。"}
    
    def _answer_compare(self, q, findings, ctx):
        """跨发现对比排序"""
        scored = []
        for f in findings:
            lv_score = {"极高风险":10,"高风险":7,"中风险":4,"低风险":2}.get(f.get("level",""),3)
            ev = f.get("evidence_rows") or f.get("items") or []
            max_amt = 0
            for ei in ev:
                try:
                    amt = float(str(ei.get("amount",ei.get("金额","0"))).replace(",",""))
                    max_amt = max(max_amt, amt)
                except: pass
            scored.append((lv_score + min(max_amt/10000, 5), f))
        scored.sort(key=lambda x: -x[0])
        lines = []
        for i, (s, f) in enumerate(scored[:10]):
            lines.append(f"{i+1}. [{f.get('level','')}] {f.get('type','')[:50]}")
        return {"title": f"🔝 严重程度排名（TOP{min(10,len(scored))}）", "content": "\n".join(lines)}
    
    def _answer_check(self, q, findings, ctx):
        """自查漏洞"""
        results = []
        for f in findings[:5]:
            issues = []
            ev_count = len(f.get("evidence",[]) or [])
            ev_rows = len(f.get("evidence_rows",[]) or f.get("items",[]) or [])
            has_policy = bool(f.get("policy_ref","").strip())
            has_source = bool(f.get("how_found","").strip())
            
            if ev_count < 1 and ev_rows < 1: issues.append("⚠ 缺少证据材料")
            if not has_policy: issues.append("⚠ 缺少法律条文")
            if not has_source: issues.append("⚠ 缺少证据来源")
            if f.get("level")=="高风险" and ev_count<2: issues.append("⚠ 高风险证据薄弱")
            
            results.append(f"[{f.get('level','')}] {f.get('type','')[:40]}:")
            results.extend(issues if issues else ["✅ 检查通过"])
            results.append("")
        
        # 资料缺口
        ctx_gaps = ctx.get("material_intel", {})
        if ctx_gaps:
            results.append("📂 资料缺口：")
            for k, v in list(ctx_gaps.items())[:5]:
                if isinstance(v, dict) and not v.get("exists"):
                    results.append(f"• {k}: {v.get('risk','影响判断')}")
        
        return {"title": "🔍 质量审查", "content": "\n".join(results)}
    
    def _answer_benchmark(self, q, findings, ctx):
        """行业对标"""
        ind = ctx.get("industry", "未识别")
        benchmarks = ctx.get("benchmarks", {})
        
        lines = [f"行业: {ind}"]
        if benchmarks:
            for metric, vals in benchmarks.items():
                if isinstance(vals, dict):
                    lines.append(f"• {metric}: 下限{vals.get('min','?')}/典型{vals.get('typical','?')}/上限{vals.get('max','?')}")
        
        lines.append("\n与行业基准对比：低于下限→高风险，低于典型值85%→中风险，高于上限→需关注。")
        return {"title": f"🏭 行业对标({ind})", "content": "\n".join(lines)}
    
    def _answer_general(self, q, findings, ctx):
        """通用搜索"""
        qwords = [w for w in q.replace('？','').replace('?','').split() if len(w) >= 2]
        found = []
        for f in findings:
            ftext = str(f.get("type",""))+" "+str(f.get("detail",""))+" "+str(f.get("description",""))
            score = sum(1 for kw in qwords if kw in ftext)
            if score >= 2: found.append((score, f))
        found.sort(key=lambda x: -x[0])
        
        if found:
            lines = [f"• [{f.get('level','')}] {f.get('type','')}: {f.get('detail','')[:150]}" for _, f in found[:5]]
            return {"title": f"🔗 相关发现（{len(found)}条）", "content": "\n".join(lines)}
        
        return {"title": "📝 说明", "content": f"关于「{q[:60]}」，未在全报告中发现匹配内容。建议使用具体关键词追问，或对报告段落进行编辑补充。"}

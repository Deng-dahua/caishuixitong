"""
AGI增强能力 — LLM报告生成 + 天眼查API + 培训案例 + 集团协同

不再只是"增强报告"，而是让LLM直接写一篇完整的5000字稽查报告，人只需审阅。
"""
import json, os, httpx
from datetime import datetime
from typing import Dict, List, Any, Optional


# ═══════════ 1. LLM 完整稽查报告生成 ═══════════

class FullReportWriter:
    """用LLM生成完整的5000字稽查报告"""
    
    def generate_report(self, findings: List[Dict], company: Dict, 
                        use_llm: bool = True) -> Dict:
        """生成完整稽查报告"""
        
        # 统计数据
        high = [f for f in findings if f.get("level") in ("高风险", "极高风险")]
        mid = [f for f in findings if f.get("level") == "中风险"]
        low = [f for f in findings if f.get("level") == "低风险"]
        
        # 构建报告框架
        report = self._build_report_framework(findings, company)
        
        # 如果有LLM，生成完整的自然语言叙述
        if use_llm:
            try:
                narrative = self._generate_llm_narrative(findings, company)
                report["llm_narrative"] = narrative
            except:
                report["llm_narrative"] = "（LLM生成失败，使用结构化报告）"
        
        return report
    
    def _build_report_framework(self, findings: List[Dict], company: Dict) -> Dict:
        """构建9章完整报告框架"""
        high = [f for f in findings if f.get("level") in ("高风险", "极高风险")]
        mid = [f for f in findings if f.get("level") == "中风险"]
        
        return {
            "title": f"关于{company.get('name','被查单位')}的税务稽查报告",
            "sections": {
                "第一章 基本情况": {
                    "content": [
                        f"被查单位: {company.get('name','')}",
                        f"信用代码: {company.get('uscc','')}",
                        f"所属行业: {company.get('industry','')}",
                        f"稽查期间: {company.get('period','')}",
                        f"稽查方法: 42域全量分析 + AGI多维度推理",
                    ],
                },
                "第二章 资料审查": {
                    "content": self._summarize_materials(company.get("materials", {})),
                },
                "第三章 稽查发现": {
                    "high_risk": [{"type": f.get("type",""), "detail": f.get("detail",""), 
                                  "evidence": f.get("how_found",""), "law": f.get("policy_ref","")} 
                                 for f in high[:15]],
                    "mid_risk": [{"type": f.get("type",""), "detail": f.get("detail","")[:100]} 
                                for f in mid[:10]],
                },
                "第四章 证据分析": {
                    "evidence_summary": f"共{len(findings)}条发现，涉及{len(set(f.get('domain','') for f in findings if f.get('domain')))}个分析域",
                },
                "第五章 法律适用": {
                    "laws": list(set(f.get("policy_ref","") for f in findings if f.get("policy_ref","").strip()))[:10],
                },
                "第六章 风险定级": {
                    "overall": self._determine_overall_risk(findings),
                    "by_level": {"极高风险":0, "高风险":len(high), "中风险":len(mid), "低风险":len(findings)-len(high)-len(mid)},
                },
                "第七章 税款计算": {
                    "estimates": self._estimate_tax(findings),
                },
                "第八章 处理建议": {
                    "suggestions": list(set(f.get("suggestion","") for f in findings if f.get("suggestion","").strip()))[:5],
                },
                "第九章 稽查结论": {
                    "conclusion": self._write_conclusion(findings, company),
                },
            },
            "appendix": {
                "finding_list": [f"{i+1}. [{f.get('level','')}] {f.get('type','')}" for i, f in enumerate(findings[:30])],
            },
        }
    
    def _generate_llm_narrative(self, findings: List[Dict], company: Dict) -> str:
        """用LLM生成完整叙事"""
        from engine.llm_client import llm, is_llm_available
        if not is_llm_available():
            return "（LLM不可用）"
        
        high = [f for f in findings if f.get("level") in ("高风险", "极高风险")]
        
        prompt = f"""你是一位资深税务稽查专家，请用专业但易懂的语言撰写一份完整的稽查报告（5000字以上）。
        
被查单位: {company.get('name','')}
行业: {company.get('industry','')}
共发现{len(findings)}条风险，其中高风险{len(high)}条。

以下是所有发现:
{json.dumps([{'type':f.get('type',''),'level':f.get('level',''),'detail':f.get('detail',''),'how_found':f.get('how_found',''),'policy_ref':f.get('policy_ref','')[:100]} for f in findings[:15]], ensure_ascii=False, indent=2)}

请按以下结构撰写（每章必须详细展开，不少于800字）：
1. 稽查背景与总体评价
2. 重大风险发现（逐条详细叙述）
3. 证据分析（证据链的完整性和可靠性）
4. 法律依据（逐条援引法条原文）
5. 风险评级依据（为什么评定这个等级）
6. 税款预估（分税种计算）
7. 处理建议（分级建议，从紧急到常规）
8. 稽查结论

要求：数据具体、法条准确、建议可操作。如不确定处，标注"建议进一步核实"。"""

        try:
            resp = llm.chat([{"role": "user", "content": prompt}], 
                          system="你是资深税务稽查专家，撰写正式的稽查报告。用中文。",
                          temperature=0.4, max_tokens=4000)
            return resp.content if resp.content else ""
        except:
            return "（LLM调用失败）"
    
    def _summarize_materials(self, materials: Dict) -> List[str]:
        if not materials: return ["未检测到资料信息"]
        lines = [f"收到{k}: {v.get('count','?')}份" for k, v in list(materials.items())[:5] if isinstance(v, dict)]
        return lines or ["资料清单"]
    
    def _determine_overall_risk(self, findings: List[Dict]) -> str:
        highs = sum(1 for f in findings if f.get("level") in ("高风险", "极高风险"))
        if highs >= 3: return "极高风险"
        if highs >= 1: return "高风险"
        if len(findings) > 2: return "中风险"
        return "低风险"
    
    def _estimate_tax(self, findings: List[Dict]) -> Dict:
        total = 0
        for f in findings:
            for ei in (f.get("evidence_rows", []) or f.get("items", []) or []):
                try:
                    if isinstance(ei, dict):
                        total += float(str(ei.get("amount", "0")).replace(",", ""))
                except: pass
        return {
            "涉税金额合计": f"¥{total:,.0f}",
            "预估增值税(13%)": f"¥{total*0.13:,.0f}",
            "预估企业所得税(25%)": f"¥{total*0.25:,.0f}",
            "预估滞纳金(日万分之五·365天)": f"¥{total*0.0005*365:,.0f}",
        }
    
    def _write_conclusion(self, findings: List[Dict], company: Dict) -> str:
        highs = [f for f in findings if f.get("level") in ("高风险", "极高风险")]
        if highs:
            return f"经全面稽查，{company.get('name','被查单位')}存在{len(highs)}项高风险问题，涉及{', '.join(set(f.get('type','')[:20] for f in highs[:3]))}。建议对该企业进行重点监控并限期整改。"
        return f"经稽查分析，{company.get('name','被查单位')}整体税务合规状况良好。"


# ═══════════ 2. 天眼查API对接 ═══════════

class TianyanchaClient:
    """天眼查工商信息查询客户端"""
    
    def __init__(self):
        self._base = "https://api.tianyancha.com"
        self._key = os.environ.get("TIANYANCHA_API_KEY", "")
    
    def check_company(self, name: str) -> Dict:
        """查询企业工商信息"""
        if not self._key:
            return {"status": "no_key", "message": "未配置天眼查API Key。前往 https://open.tianyancha.com 申请。"}
        
        # 实际API调用（当前用模拟数据演示，配好Key即可真实调用）
        try:
            resp = httpx.get(
                f"{self._base}/search/v3",
                params={"keyword": name},
                headers={"Authorization": self._key},
                timeout=10.0,
            )
            if resp.status_code == 200:
                return {"status": "ok", "data": resp.json()}
        except:
            pass
        
        # 降级：返回占位信息提示用户
        return {
            "status": "demo",
            "message": f"天眼查API未配置或不可用。可通过以下方式查询「{name}」:\n"
                       "1. 前往 https://www.tianyancha.com 手动查询\n"
                       "2. 配置 TIANYANCHA_API_KEY 环境变量启用自动查询",
            "demo_data": {
                "company_name": name,
                "status": "存续",
                "registered_capital": "未知（需API Key）",
                "business_scope": "未知（需API Key）",
            },
        }
    
    def verify_supplier(self, supplier_name: str) -> Dict:
        """验证供应商资质"""
        result = self.check_company(supplier_name)
        result["verification_type"] = "供应商资质核查"
        result["checks"] = ["工商状态", "注册资本", "经营范围", "是否存在关联关系"]
        return result


# ═══════════ 3. AGI 培训案例生成 ═══════════

class TrainingCaseGenerator:
    """用AGI生成带详细解释的培训案例"""
    
    def __init__(self):
        self._cases: List[Dict] = []
    
    def generate_case(self, finding: Dict, company: Dict, use_llm: bool = True) -> Dict:
        """从一条真实发现生成培训案例"""
        
        case = {
            "title": f"案例: {finding.get('type','')}",
            "scenario": {
                "company": company.get("name", "某企业"),
                "industry": company.get("industry", "某行业"),
                "situation": f"系统在稽查中发现: {finding.get('detail','')}",
            },
            "analysis": {
                "what_happened": finding.get("detail", ""),
                "how_found": finding.get("how_found", "系统自动分析发现"),
                "evidence_chain": self._build_evidence_narrative(finding),
                "legal_basis": finding.get("policy_ref", "《税收征收管理法》相关规定"),
            },
            "lessons": {
                "for_auditor": self._auditor_lesson(finding),
                "for_enterprise": self._enterprise_lesson(finding),
                "key_takeaway": self._key_takeaway(finding),
            },
            "quiz": {
                "question": f"如果你在稽查中发现{finding.get('type','')[:30]}，你会怎么做？",
                "answer": self._build_answer(finding),
            },
        }
        
        # 用LLM增强案例的叙事质量
        if use_llm:
            try:
                from engine.llm_client import llm, is_llm_available
                if is_llm_available():
                    prompt = f"""请用通俗易懂的语言，为一个税务稽查新人解释以下案例:

发现: {finding.get('type','')}
详情: {finding.get('detail','')}
如何发现: {finding.get('how_found','')}
法律依据: {finding.get('policy_ref','')}

要求: 
1. 解释这个案例的稽查要点（新人能听懂的语言）
2. 说明稽查员应该怎么做
3. 给企业一个合规建议
4. 用1-2句话总结关键教训
用中文回答，不超过500字。"""
                    
                    resp = llm.chat([{"role": "user", "content": prompt}],
                                  temperature=0.5, max_tokens=500)
                    if resp.content:
                        case["llm_enhanced_narrative"] = resp.content
            except:
                pass
        
        self._cases.append(case)
        return case
    
    def _build_evidence_narrative(self, finding: Dict) -> str:
        ev = finding.get("evidence_rows", []) or finding.get("items", []) or []
        if not ev: return "系统通过多域交叉分析自动发现"
        return f"发现{len(ev)}条证据: " + "; ".join(
            f"{e.get('source','?')}: {e.get('amount','?')}" for e in ev[:3] if isinstance(e, dict)
        )
    
    def _auditor_lesson(self, finding: Dict) -> str:
        ftype = finding.get("type", "")
        if "虚开" in ftype: return "关注进项发票的三流一致性，不要只看票面金额，要穿透看资金流和货物流。"
        if "收入" in ftype: return "比对银行流水与开票记录是关键，很多隐匿收入藏在差异里。"
        if "成本" in ftype: return "大额成本必须有三单支撑（合同+发票+付款），缺一不可。"
        return "注意交叉验证——单一数据源永远不够。"
    
    def _enterprise_lesson(self, finding: Dict) -> str:
        ftype = finding.get("type", "")
        if "虚开" in ftype: return "确保所有进项发票对应真实交易，保留合同+付款+物流三套记录。"
        if "收入" in ftype: return "所有经营收入必须如实申报，不要存侥幸心理。"
        return "规范财务管理是避免税务风险的根本途径。"
    
    def _key_takeaway(self, finding: Dict) -> str:
        return f"核心教训: {finding.get('how_found','系统自动分析')[80:]} 说明——{self._auditor_lesson(finding)[:60]}"
    
    def _build_answer(self, finding: Dict) -> str:
        return f"第一步: 确认{finding.get('type','')[:20]}的具体数据来源。第二步: 对比多源证据。第三步: 查阅{finding.get('policy_ref','相关法规')[:50]}。第四步: 定量计算涉税金额。第五步: 形成正式稽查结论。"


# ═══════════ 4. 集团多账套协同分析 ═══════════

class GroupAnalyzer:
    """集团多企业协同稽查"""
    
    def analyze_group(self, companies: List[Dict], findings_by_company: Dict[int, List[Dict]]) -> Dict:
        """
        同时分析集团下多家公司
        
        companies: [{id, name, uscc, industry}, ...]
        findings_by_company: {company_id: [findings], ...}
        """
        results = {
            "group_overview": {
                "total_companies": len(companies),
                "total_findings": sum(len(v) for v in findings_by_company.values()),
                "high_risk_companies": 0,
                "group_risk_level": "低风险",
            },
            "per_company": [],
            "cross_company_patterns": [],
            "consolidated_risks": [],
        }
        
        # 逐公司分析
        high_count = 0
        for co in companies:
            cid = co["id"]
            cfindings = findings_by_company.get(cid, [])
            high = [f for f in cfindings if f.get("level") in ("高风险", "极高风险")]
            if high: high_count += 1
            
            results["per_company"].append({
                "id": cid,
                "name": co.get("name", ""),
                "findings": len(cfindings),
                "high_risk": len(high),
                "top_risks": [f.get("type", "")[:40] for f in high[:3]],
            })
        
        results["group_overview"]["high_risk_companies"] = high_count
        if high_count >= len(companies) * 0.5:
            results["group_overview"]["group_risk_level"] = "高风险"
        elif high_count > 0:
            results["group_overview"]["group_risk_level"] = "中风险"
        
        # 跨公司模式检测
        all_types = []
        for cid, cfindings in findings_by_company.items():
            for f in cfindings:
                all_types.append(f.get("type", ""))
        
        from collections import Counter
        type_counts = Counter(all_types)
        common = type_counts.most_common(5)
        
        for risk_type, count in common:
            if count >= 2:
                affected = []
                for co in companies:
                    cid = co["id"]
                    if any(risk_type in f.get("type", "") for f in findings_by_company.get(cid, [])):
                        affected.append(co.get("name", ""))
                
                results["cross_company_patterns"].append({
                    "risk_type": risk_type[:60],
                    "count": count,
                    "affected_companies": affected,
                    "risk": "系统性风险" if count >= 3 else "需关注",
                })
        
        # 合并报表稽查要点
        results["consolidated_risks"] = [
            "关联交易: 检查集团内交易的定价是否公允",
            "成本分摊: 集团内共同费用的分摊是否合理",
            "利润转移: 是否存在通过关联交易将利润转移至低税率实体",
            "资金池: 集团内部资金拆借的利息处理是否符合独立交易原则",
        ]
        
        results["summary"] = self._write_group_summary(results)
        
        return results
    
    def _write_group_summary(self, results: Dict) -> str:
        overview = results["group_overview"]
        patterns = results["cross_company_patterns"]
        
        summary = f"集团共{overview['total_companies']}家企业，发现{overview['total_findings']}条风险，"
        summary += f"{overview['high_risk_companies']}家存在高风险。"
        
        if patterns:
            common_str = "、".join(p["risk_type"][:30] for p in patterns[:3])
            summary += f"跨公司共同风险: {common_str}。"
        
        summary += f"集团整体风险: {overview['group_risk_level']}。"
        
        return summary


# 全局实例
report_writer = FullReportWriter()
tianyancha = TianyanchaClient()
training_gen = TrainingCaseGenerator()
group_analyzer = GroupAnalyzer()

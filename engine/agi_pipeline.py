"""
AGI知识管线连接器 —— 联通16+模块到AGI学习系统

每个模块的分析结果被采集为结构化"学习事件"，注入：
  - 知识库(knowledge_base) → 持久化知识积累
  - 因果网络(causal_network) → 因果边/模式发现
  - 自愈引擎(self_healing) → 错误修正规则
  - 分析记忆(memory) → 跨分析经验

全模块覆盖：
  ①-⑮ 标准16模块 + 推理引擎仪表盘 + 能力矩阵 + 智能大脑
"""
import json, time, os
from datetime import datetime
from collections import Counter, defaultdict
from typing import Dict, List, Any, Optional

# ==================== 学习事件类型 ====================

class LearningEvent:
    """一次可学习的分析事件"""
    def __init__(self, module: str, event_type: str, data: Dict):
        self.module = module
        self.event_type = event_type
        self.data = data
        self.timestamp = datetime.now().isoformat()
        self.trace_id = data.get("trace_id", "")

# ==================== 管线连接器 ====================

class AGIPipelineConnector:
    """联通16+模块到AGI知识系统的管线连接器"""
    
    def __init__(self):
        self.events: List[LearningEvent] = []
        self.stats = {"modules_connected": 0, "events_collected": 0, "rules_learned": 0}
        self.agent = None
        self.errors: List[str] = []  # 新模块错误日志
    
    def init_agent(self, db_session=None):
        """初始化存勤法税智能体——统一智能入口"""
        try:
            from engine.agent_core import create_agent
            self.agent = create_agent(db_session)
            self.stats["modules_connected"] += 1
            return self.agent
        except Exception as e:
            print(f"[AGI] 智能体初始化失败: {e}")
            return None
    
    def run_agent_cycle(self, bank_txs, invoices, salaries, vouchers, ctx, company_id, company_name, db):
        """运行智能体全周期：感知→分析→反思→学习→洞见"""
        if not self.agent:
            self.init_agent(db)
        if not self.agent:
            return {"error": "智能体未初始化"}
        
        try:
            self.agent.analyze(bank_txs, invoices, salaries, vouchers, ctx, company_id, company_name, db)
            agent_result = self.agent.finalize([], "", company_id, company_name, bank_txs, invoices, salaries, vouchers)
            # 将智能体产出注入管道事件
            self.events.append(LearningEvent("智能体", "insight_generated", {
                "summary": agent_result.get("insight_summary", ""),
                "reflection_checked": agent_result.get("reflection", {}).get("total_checked", 0),
            }))
            self.stats["events_collected"] += 1
            return agent_result
        except Exception as e:
            return {"error": str(e)}
    def ingest_engine_status(self, engine_status: Dict, ctx=None, trace_id: str = ""):
        """从推理引擎Phase1-4执行状态中学习
        
        采集：信号→深挖域映射、Phase执行决策、数据质量评估
        """
        events = []
        
        # Phase1 信号
        red_flags = engine_status.get("red_flags", [])
        yellow_flags = engine_status.get("yellow_flags", [])
        for flag in red_flags:
            events.append(LearningEvent("推理引擎", "red_flag_triggered", {
                "flag": str(flag)[:80], "trace_id": trace_id,
            }))
        for flag in yellow_flags:
            events.append(LearningEvent("推理引擎", "yellow_flag_triggered", {
                "flag": str(flag)[:80], "trace_id": trace_id,
            }))
        
        # Phase2 深挖决策
        phase2_domains = engine_status.get("phase2_domains_deep_dived", [])
        if phase2_domains:
            events.append(LearningEvent("推理引擎", "phase2_deep_dive", {
                "domains": phase2_domains[:10],
                "count": len(phase2_domains),
                "trace_id": trace_id,
            }))
        
        # Phase3 交叉验证
        phase3_patterns = engine_status.get("phase3_pattern_hits", [])
        phase3_conflicts = engine_status.get("phase3_conflicts", [])
        if phase3_conflicts:
            events.append(LearningEvent("推理引擎", "phase3_交叉验证冲突", {
                "conflict_count": len(phase3_conflicts),
                "trace_id": trace_id,
            }))
        
        # Phase4 综合定性
        synthesis = engine_status.get("phase4_synthesis", {})
        if synthesis:
            events.append(LearningEvent("推理引擎", "phase4_synthesis", {
                "risk_score": synthesis.get("risk_score", 0),
                "overall_risk": synthesis.get("overall_risk", ""),
                "p0_count": synthesis.get("p0_count", 0),
                "trace_id": trace_id,
            }))
        
        # 数据质量
        dq = engine_status.get("data_quality_score", 100)
        events.append(LearningEvent("推理引擎", "data_quality", {
            "score": dq, "trace_id": trace_id,
        }))
        
        self.events.extend(events)
        self.stats["events_collected"] += len(events)
        
        # 注入知识库：信号→域映射经验
        if red_flags and phase2_domains:
            try:
                kb = __import__('engine.knowledge_base', fromlist=['get_kb']).get_kb()
                kb.add_lesson(
                    f"{len(red_flags)}个红色信号触发了{len(phase2_domains)}个深挖域",
                    "推理引擎"
                )
            except: pass
        
        return len(events)
    
    # ─── 能力矩阵(B) ───
    def ingest_capability_matrix(self, capability_data: Dict = None, trace_id: str = ""):
        """从能力矩阵中学习维度覆盖情况"""
        if not capability_data:
            try:
                from engine.capability_matrix import get_capability_summary
                capability_data = get_capability_summary()
            except:
                capability_data = {}
        
        if not isinstance(capability_data, dict):
            capability_data = {}
        dims = capability_data.get("dimensions", capability_data.get("summary", {}))
        events = []
        
        if dims:
            # 统计覆盖维度
            covered = sum(1 for d in (dims if isinstance(dims, list) else dims.values()) 
                         if isinstance(d, dict) and d.get("covered", False))
            total = len(dims) if isinstance(dims, list) else len(dims)
            
            events.append(LearningEvent("能力矩阵", "dimension_coverage", {
                "covered": covered, "total": total,
                "coverage_ratio": round(covered/max(total,1), 2),
                "trace_id": trace_id,
            }))
        
        self.events.extend(events)
        self.stats["events_collected"] += len(events)
        
        if events:
            try:
                kb = __import__('engine.knowledge_base', fromlist=['get_kb']).get_kb()
                kb.add_lesson(
                    f"能力矩阵覆盖: {events[0].data.get('covered',0)}/{events[0].data.get('total',0)}维度",
                    "能力矩阵"
                )
            except: pass
        
        return len(events)
    
    # ─── 智能大脑/行为准则(C) ───
    def ingest_ai_rules(self, rule_executions: List[Dict] = None, trace_id: str = ""):
        """智能大脑(行为准则)执行追踪"""
        # 行为准则嵌在稽查方法论和自愈规则中，此处采集执行摘要
        if rule_executions:
            for rex in rule_executions:
                self.events.append(LearningEvent("智能大脑", "ai_rule_executed", {
                    "rule": rex.get("rule", rex.get("name", ""))[:80],
                    "result": rex.get("result", ""),
                    "trace_id": trace_id,
                }))
                self.stats["events_collected"] += 1
        
        return len(rule_executions or [])
    
    # ─── ① 稽查指令规则学习 ───
    def ingest_audit_rules(self, rules_used: int, rule_details: List[Dict], findings: List[Dict],
                           trace_id: str, company_id: int):
        """从稽查指令执行中学习
        
        记录：每条规则触发后实际产生了什么结论，成功率如何。
        """
        events = []
        for f in findings:
            rule_id = f.get("rule_id", f.get("_rule_id", ""))
            if rule_id:
                events.append(LearningEvent("①稽查指令", "rule_triggered", {
                    "rule_id": rule_id,
                    "finding_type": f.get("type", ""),
                    "level": f.get("level", ""),
                    "score": f.get("score", 0),
                    "was_filtered": f.get("_filtered", False),
                    "trace_id": trace_id,
                    "company_id": company_id,
                }))
        
        self.events.extend(events)
        self.stats["events_collected"] += len(events)
        
        # 注入知识库：更新规则使用频率
        self._update_rule_frequency(rule_details, findings)
        
        return len(events)
    
    def _update_rule_frequency(self, rule_details: List[Dict], findings: List[Dict]):
        """更新规则触发频率到知识库"""
        try:
            from engine.knowledge_base import get_kb
            kb = get_kb()
            
            # 统计每条规则的触发次数
            rule_hits = Counter()
            for f in findings:
                rid = f.get("rule_id", f.get("_rule_id", ""))
                if rid:
                    rule_hits[str(rid)] += 1
            
            # 更新行业画像中的常见高风险规则
            for rid, count in rule_hits.most_common(10):
                for rd in rule_details:
                    if str(rd.get("id", "")) == rid:
                        kb.add_lesson(f"规则{rid}({rd.get('name','')[:20]})触发{count}次", "稽查指令")
                        break
        except:
            pass
    
    # ─── ② 线索链 → 因果模式 ───
    def ingest_clue_chains(self, clue_chains: List[Dict], findings: List[Dict],
                           trace_id: str):
        """从线索链中学习线索→结论的因果模式"""
        events = []
        for chain in clue_chains or []:
            clue_id = chain.get("id", chain.get("clue_id", ""))
            linked_findings = [f for f in findings if clue_id in str(f.get("_clue_refs", ""))]
            
            if linked_findings:
                events.append(LearningEvent("②线索链", "clue_to_finding", {
                    "clue_id": clue_id,
                    "clue_name": chain.get("name", chain.get("sub_topic", "")),
                    "findings_triggered": [f.get("type", "") for f in linked_findings],
                    "trigger_count": len(linked_findings),
                    "trace_id": trace_id,
                }))
        
        self.events.extend(events)
        self.stats["events_collected"] += len(events)
        
        # 注入因果网络：线索→结论边
        self._inject_clue_causal_edges(clue_chains, findings)
        
        return len(events)
    
    def _inject_clue_causal_edges(self, clue_chains: List[Dict], findings: List[Dict]):
        """将线索→结论的关系注入因果网络"""
        try:
            from engine.knowledge_base import get_kb
            kb = get_kb()
            
            for chain in clue_chains or []:
                clue_name = chain.get("name", chain.get("sub_topic", ""))
                linked = [f for f in findings if 
                          chain.get("id","") in str(f.get("_clue_refs","")) or
                          any(k in f.get("type","") for k in chain.get("trigger_keywords",[]) if k)]
                
                for f in linked[:3]:
                    kb.add_causal_edge({
                        "signals": [f"线索:{clue_name[:20]}"],
                        "finding": f.get("type", ""),
                        "confidence": 0.6,
                        "source": "②线索链",
                    })
        except:
            pass
    
    # ─── ③ 证据链 → 置信度模型 ───
    def ingest_evidence_chains(self, evidence_chains: List[Dict], findings: List[Dict],
                               trace_id: str):
        """从证据链中学习证据组合→结论置信度"""
        events = []
        for ev in evidence_chains or []:
            ev_id = ev.get("id", ev.get("evidence_id", ""))
            dims = ev.get("dimensions", [])
            
            if dims:
                events.append(LearningEvent("③证据链", "evidence_combo", {
                    "evidence_id": ev_id,
                    "dimension_count": len(dims),
                    "dimensions": [d.get("code","") for d in dims],
                    "trace_id": trace_id,
                }))
        
        self.events.extend(events)
        
        # 注入知识库：高维证据组合(≥3维) → 高置信度标记
        for ev in evidence_chains or []:
            dims = ev.get("dimensions", [])
            if len(dims) >= 3:
                try:
                    kb = __import__('engine.knowledge_base', fromlist=['get_kb']).get_kb()
                    kb.add_lesson(f"证据链{ev.get('id','')}的{len(dims)}维证据组合可提高置信度", "③证据链")
                except: pass
        
        return len(events)
    
    # ─── ④ 分析链 → 路径学习 ───
    def ingest_analysis_chains(self, analysis_chains: List[Dict], trace_id: str):
        """从分析链中学习有效的分析路径"""
        for chain in analysis_chains or []:
            steps = chain.get("steps", chain.get("analysis_flow", []))
            if steps:
                self.events.append(LearningEvent("④分析链", "analysis_path", {
                    "chain_name": chain.get("name", chain.get("id", "")),
                    "step_count": len(steps),
                    "trace_id": trace_id,
                }))
                self.stats["events_collected"] += 1
        
        return len(analysis_chains or [])
    
    # ─── ⑤ 稽查方法论 → 方法映射 ───
    def ingest_methodologies(self, methodologies_applied: List[Dict], domain_results: List[Dict],
                             trace_id: str):
        """从稽查方法论应用中学习方法→域→结论的映射关系"""
        for method in methodologies_applied or []:
            m_name = method.get("name", method.get("id", ""))
            domains = method.get("domains", method.get("applicable_domains", []))
            
            self.events.append(LearningEvent("⑤稽查方法论", "method_applied", {
                "method_name": m_name,
                "domains_count": len(domains),
                "trace_id": trace_id,
            }))
            self.stats["events_collected"] += 1
            
            # 学习方法论的有效性：以后分析方法论命中域次数
            try:
                kb = __import__('engine.knowledge_base', fromlist=['get_kb']).get_kb()
                kb.add_lesson(f"方法论'{m_name[:30]}'在{len(domains)}个域中应用", "⑤稽查方法论")
            except: pass
        
        return len(methodologies_applied or [])
    
    # ─── ⑥ 代码 → 变更追踪 ───
    def ingest_code_changes(self, changes: List[str]):
        """追踪代码变更，用于影响分析和回滚决策"""
        for change in changes or []:
            self.events.append(LearningEvent("⑥代码", "code_change", {
                "description": change,
            }))
            self.stats["events_collected"] += 1
    
    # ─── ⑦ 文件解析 → 自适应修复 ───
    def ingest_file_parsing(self, file_results: List[Dict], trace_id: str):
        """从文件解析中学习解析失败→修复策略"""
        for fr in file_results or []:
            ftype = fr.get("type", "unknown")
            actions = fr.get("actions", [])
            failures = [a for a in actions if "失败" in a or "错误" in a or "unknown" in str(fr.get("type",""))]
            
            if failures or ftype == "unknown":
                self.events.append(LearningEvent("⑦文件解析", "parse_failure", {
                    "file": fr.get("file", "")[-30:],
                    "type": ftype,
                    "actions": actions,
                    "trace_id": trace_id,
                }))
                self.stats["events_collected"] += 1
            
            # 记录解析成功的方法
            if ftype != "unknown" and actions:
                try:
                    kb = __import__('engine.knowledge_base', fromlist=['get_kb']).get_kb()
                    kb.add_lesson(f"文件'{fr.get('file','')[-20:]}'解析为{ftype}({len(actions)}步)", "⑦文件解析")
                except: pass
        
        return sum(1 for fr in (file_results or []) if fr.get("type") == "unknown")
    
    # ─── ⑧ 域分析 → 已接入(因果网络) ───
    def ingest_domain_results(self, domain_results: List[Dict], trace_id: str, company_id: int):
        """从域分析结果中学习域→结论模式"""
        for dr in domain_results or []:
            domain = dr.get("domain", "")
            findings = dr.get("findings", [])
            
            for f in findings:
                self.events.append(LearningEvent("⑧域分析", "domain_finding", {
                    "domain": domain,
                    "finding_type": f.get("type", ""),
                    "level": f.get("level", ""),
                    "score": f.get("score", 0),
                    "trace_id": trace_id,
                    "company_id": company_id,
                }))
                self.stats["events_collected"] += 1
        
        # 注入因果网络：域×结论→因果边
        self._inject_domain_causal_edges(domain_results)
        
        return sum(len(dr.get("findings", [])) for dr in (domain_results or []))
    
    def _inject_domain_causal_edges(self, domain_results: List[Dict]):
        """域分析→因果边"""
        try:
            kb = __import__('engine.knowledge_base', fromlist=['get_kb']).get_kb()
            
            for dr in domain_results or []:
                domain = dr.get("domain", "")
                for f in dr.get("findings", []):
                    if f.get("level") == "高风险":
                        kb.add_causal_edge({
                            "signals": [f"域:{domain}"],
                            "finding": f.get("type", ""),
                            "confidence": 0.7,
                            "source": "⑧域分析",
                        })
        except: pass
    
    # ─── ⑨⑩⑪ 跨域线索/分析/证据链 ───
    def ingest_cross_domain(self, cross_clues: List[Dict], cross_analysis: List[Dict],
                            cross_evidence: List[Dict], trace_id: str):
        """跨域模式学习"""
        count = 0
        for item in (cross_clues or []) + (cross_analysis or []) + (cross_evidence or []):
            self.events.append(LearningEvent("⑨⑩⑪跨域", "cross_domain", {
                "item_type": item.get("type", ""),
                "domains": item.get("domains", item.get("_cross_domains", [])),
                "trace_id": trace_id,
            }))
            count += 1
        
        self.stats["events_collected"] += count
        
        # 跨域共现 → 知识库经验
        for item in (cross_clues or [])[:5]:
            try:
                kb = __import__('engine.knowledge_base', fromlist=['get_kb']).get_kb()
                domains = item.get("domains", item.get("_cross_domains", []))
                if len(domains) >= 2:
                    kb.add_lesson(f"跨域模式: {'+'.join(domains[:3])}同时触发→加强调查", "⑨跨域线索")
            except: pass
        
        return count
    
    # ─── ⑫ 方法论过滤器 → 过滤优化 ───
    def ingest_filter_results(self, filter_log: List[str], pre_filter_count: int,
                              post_filter_count: int, filtered_out: List[Dict], trace_id: str):
        """从过滤器结果中学习：哪些被过滤掉的可能仍有用
        
        关键学习：被过滤的不一定是噪音，可能是低信号但高价值的线索。
        """
        noise_ratio = (pre_filter_count - post_filter_count) / max(pre_filter_count, 1)
        
        self.events.append(LearningEvent("⑫方法论过滤", "filter_applied", {
            "pre_count": pre_filter_count,
            "post_count": post_filter_count,
            "noise_ratio": round(noise_ratio, 3),
            "filtered_count": pre_filter_count - post_filter_count,
            "trace_id": trace_id,
        }))
        self.stats["events_collected"] += 1
        
        # 学习：如果噪声率>90%，说明过滤器太激进
        if noise_ratio > 0.9:
            try:
                kb = __import__('engine.knowledge_base', fromlist=['get_kb']).get_kb()
                kb.add_lesson(f"过滤率{noise_ratio:.0%}偏高，可能过滤了有价值信号", "⑫方法论过滤")
            except: pass
        
        return 1
    
    # ─── ⑬⑭⑮ 质量体系 ───
    def ingest_quality_data(self, quality_report: Dict, pipeline_depth: int,
                            compliance_gate: Dict, trace_id: str):
        """从质量保障体系中学习"""
        events = []
        
        # 质量报告
        if quality_report:
            events.append(LearningEvent("⑮质量保障", "quality_check", {
                "issues_count": quality_report.get("issues_count", 0),
                "quality_score": quality_report.get("quality_score", 100),
                "trace_id": trace_id,
            }))
        
        # 流程深度
        if pipeline_depth:
            events.append(LearningEvent("⑭七步流程", "pipeline_depth", {
                "depth": pipeline_depth,
                "trace_id": trace_id,
            }))
        
        # 合规门禁
        if compliance_gate:
            events.append(LearningEvent("⑬全链路质量", "compliance_gate", {
                "passed": compliance_gate.get("passed", True),
                "checks": compliance_gate.get("checks", 0),
                "trace_id": trace_id,
            }))
        
        self.events.extend(events)
        self.stats["events_collected"] += len(events)
        
        # 质量反馈 → 经验
        if quality_report and quality_report.get("issues_count", 0) > 0:
            try:
                kb = __import__('engine.knowledge_base', fromlist=['get_kb']).get_kb()
                kb.add_lesson(f"质量检查发现{quality_report['issues_count']}个问题", "⑮质量保障")
            except: pass
        
        return len(events)
    
    # ─── 法律推理引擎(新增) ───
    def ingest_legal_reasoning(self, legal_results: Dict, trace_id: str = ""):
        """采集法律推理结果：条文引用、三段论推理链"""
        events = []
        for result in legal_results.get("results", []):
            events.append(LearningEvent("法律推理引擎", "legal_reasoning_applied", {
                "finding_type": result.get("finding_type", ""),
                "primary_article": result.get("primary_article", "")[:80],
                "primary_consequence": result.get("primary_consequence", "")[:120],
                "matched_rules_count": result.get("matched_rules_count", 0),
                "trace_id": trace_id,
            }))
        self.events.extend(events)
        return len(events)
    
    # ─── 跨企业关系网(新增) ───
    def ingest_cross_enterprise(self, graph_results: Dict, trace_id: str = ""):
        """采集跨企业关系图谱：关联关系、共享实体"""
        events = []
        for rel in graph_results.get("relationships", []):
            events.append(LearningEvent("跨企业关系网", "relationship_detected", {
                "type": rel.get("type", ""),
                "company_a": rel.get("company_a", "")[:50],
                "company_b": rel.get("company_b", "")[:50],
                "shared_count": len(rel.get("shared_entities", [])),
                "risk_level": rel.get("risk_level", ""),
                "trace_id": trace_id,
            }))
        self.events.extend(events)
        return len(events)
    
    # ─── 时序趋势学习(新增) ───
    def ingest_trend_analysis(self, trend_results: Dict, trace_id: str = ""):
        """采集趋势分析结果：指标变化轨迹、恶化信号"""
        events = []
        for trend in trend_results.get("trends", []):
            events.append(LearningEvent("时序趋势学习", "trend_detected", {
                "metric": trend.get("metric", ""),
                "trend": trend.get("trend", ""),
                "change_rate": trend.get("change_rate", 0),
                "risk_level": trend.get("risk_level", ""),
                "periods": trend.get("periods", 0),
                "signal": trend.get("signal", "")[:100],
                "trace_id": trace_id,
            }))
        self.events.extend(events)
        return len(events)
    

    # ─── 汇总 → 知识库持久化 ───
    
    def get_dashboard_data(self) -> Dict:
        """获取管道仪表盘数据——供前端展示16模块知识注入状态"""
        module_counts = Counter(e.module for e in self.events)
        modules_detail = []
        for module_name, count in module_counts.most_common():
            module_events = [e for e in self.events if e.module == module_name]
            modules_detail.append({"module": module_name, "events": count, "types": list(set(e.event_type for e in module_events))})
        kb_info = {}
        try:
            kb = __import__('engine.knowledge_base', fromlist=['get_kb']).get_kb()
            kb_info = {"analyses": len(getattr(kb,'analysis_history',[])), "lessons": len(getattr(kb,'lessons',[])), "edges": len(getattr(kb,'causal_edges',[]))}
        except: pass
        mem_info = {"analyses": 0}
        try:
            import os as _os, json as _json
            mp = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "static", "cross_analysis_memory.json")
            if _os.path.exists(mp):
                with open(mp, "r", encoding="utf-8") as f: mem = _json.load(f)
                mem_info["analyses"] = len(mem.get("analyses",[]))
        except: pass
        return {"stats": dict(self.stats), "total_events": len(self.events), "modules_active": len(module_counts), "module_breakdown": modules_detail, "knowledge_base": kb_info, "cross_memory": mem_info, "health": "active" if self.stats.get("events_collected",0)>0 else "idle"}
    
    def finalize_learning(self, analysis_trace_id: str, company_name: str = "", 
                          industry: str = "", ctx: Any = None) -> Dict:
        """将所有学习事件汇总并持久化到知识库和因果网络
        
        在每次分析完成后调用此方法，AGI从本次分析中汲取全部模块的经验。
        ctx: 可选，AuditContext 或 data_profile dict，用于提取信号值
        """
        # 写入分析历史
        try:
            kb = __import__('engine.knowledge_base', fromlist=['get_kb']).get_kb()
            kb.add_analysis_to_history({
                "trace_id": analysis_trace_id,
                "company_name": company_name,
                "industry": industry,
                "findings_count": self.stats["events_collected"],
                "high_risk_count": sum(1 for e in self.events if "高风险" in str(e.data.get("level", ""))),
            })
            kb.add_lesson(f"完成一次全模块分析，采集{self.stats['events_collected']}个学习事件", "综合")
        except: pass
        
        # ─── 提取 finding_types 和 data_profile ───
        finding_types = []
        data_profile = {}
        
        for event in self.events:
            # 提取 finding_type
            if event.module == "①稽查指令" and event.event_type == "rule_triggered":
                ft = event.data.get("finding_type", "")
                if ft and ft not in finding_types:
                    finding_types.append(ft)
            # 从域分析结果提取信号值
            if event.module == "⑧域分析" and event.event_type == "domain_result":
                dd = event.data.get("domain_data", {})
                if isinstance(dd, dict):
                    for k in ["bank_in_ratio","bank_out_ratio","supplier_concentration",
                               "goods_match_ratio","customer_concentration",
                               "has_processing_fee","personal_transfers_detected"]:
                        if k in dd and k not in data_profile:
                            data_profile[k] = dd[k]
        
        # 如果传入了 ctx，从中提取更多信号值
        if ctx:
            if isinstance(ctx, dict):
                for k in ["bank_in_ratio","bank_out_ratio","supplier_concentration",
                           "goods_match_ratio","customer_concentration",
                           "has_processing_fee","has_personal_payments",
                           "round_trip_detected","structured_transfers",
                           "supplier_same_city_ratio","pur_without_payment_ratio",
                           "phantom_suppliers","price_volatility","quantity_spike",
                           "sal_without_bank_ratio","revenue_smoothing",
                           "off_hours_invoice","profit_cash_gap","ar_ap_anomaly",
                           "data_quality_score","near_micro_limit",
                           "has_related_parties","has_six_personnel_overlap",
                           "supplier_is_customer"]:
                    if k in ctx and k not in data_profile:
                        data_profile[k] = ctx[k]
            else:
                # 尝试从对象提取
                for attr in ["red_flags","biz_cost_classification"]:
                    if hasattr(ctx, attr) and getattr(ctx, attr):
                        data_profile[f"has_{attr}"] = True
        
        # ─── 写入 cross_analysis_memory.json ───
        memory_path = ""
        try:
            import os
            memory_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "cross_analysis_memory.json")
            with open(memory_path, "r", encoding="utf-8") as f:
                memory = json.load(f)
        except:
            memory = {"analyses": [], "industry_patterns": {}, "lesson_learned": []}
        
        # 避免重复
        if not any(a.get("trace_id") == analysis_trace_id for a in memory["analyses"]):
            memory["analyses"].append({
                "trace_id": analysis_trace_id,
                "company_name": company_name,
                "industry": industry,
                "data_profile": data_profile,
                "learning_points": finding_types,
                "timestamp": datetime.now().isoformat(),
            })
            try:
                with open(memory_path, "w", encoding="utf-8") as f:
                    json.dump(memory, f, ensure_ascii=False, indent=2)
            except: pass
        
        # ─── 触发因果网络学习 ───
        causal_edges_found = 0
        patterns_found = 0
        try:
            from engine.causal_network import CausalNetwork
            network = CausalNetwork()
            if memory_path:
                network.load_data(memory_path)
            pairs = network.collect_signals()
            if pairs:
                network.build_cooccurrence_matrix(pairs)
                edges = network.discover_causal_edges()
                patterns = network.mine_multi_signal_patterns(pairs)
                
                # 保存到知识库
                kb = __import__('engine.knowledge_base', fromlist=['get_kb']).get_kb()
                for edge in edges:
                    edge_dict = {
                        "signals": edge.source_signals,
                        "finding": edge.target_finding,
                        "co_occurrence_count": edge.co_occurrence_count,
                        "total_source_occurrences": edge.total_source_occurrences,
                        "conditional_probability": edge.conditional_probability,
                        "lift": edge.lift,
                        "confidence": edge.confidence,
                        "first_seen": edge.first_seen,
                        "last_seen": edge.last_seen,
                        "companies": edge.companies,
                    }
                    kb.add_causal_edge(edge_dict)
                
                for pattern in patterns:
                    pattern_dict = {
                        "signals": pattern.signals,
                        "finding": pattern.target_finding,
                        "signal_count": pattern.signal_count,
                        "joint_probability": pattern.joint_probability,
                        "occurrence_count": pattern.occurrence_count,
                        "finding_occurrence": pattern.finding_occurrence,
                        "distinctiveness": pattern.distinctiveness,
                        "auto_rule_ready": pattern.auto_rule_ready,
                    }
                    kb.add_signal_pattern(pattern_dict)
                
                kb.save()
                causal_edges_found = len(edges)
                patterns_found = len(patterns)
        except Exception as e:
            print(f"[AGI Pipeline] 因果网络学习失败: {e}")
            import traceback
            traceback.print_exc()
        
        # ═══ v2.0 智能进化层 ═══
        # 1. 事件总线 — 模块间通信
        try:
            from engine.event_bus import bus, AGIEvents
            for edge in edges:
                bus.publish(AGIEvents.CAUSAL_EDGE_DISCOVERED, {
                    "signals": edge.source_signals,
                    "finding": edge.target_finding,
                    "confidence": edge.confidence,
                }, source="causal_network")
            for pattern in patterns:
                bus.publish(AGIEvents.CAUSAL_PATTERN_FORMED, {
                    "signals": pattern.signals,
                    "finding": pattern.target_finding,
                    "joint_probability": pattern.joint_probability,
                }, source="causal_network")
            bus.publish(AGIEvents.ANALYSIS_COMPLETED, {
                "company": company_name, "findings_count": len(finding_types),
                "causal_edges": len(edges), "patterns": len(patterns),
            }, source="agi_pipeline")
            bus.persist_log()
        except Exception as e:
            self.errors.append(f"[AGI 事件总线] {e}")
        
        # 2. SCM 因果推理
        scm_report = {}
        try:
            from engine.scm_reasoner import scm
            all_findings_dicts = [
                {"type": ft, "signals": [e.data.get("signal","") for e in self.events if e.event_type == "rule_triggered" and e.data.get("finding_type") == ft]}
                for ft in finding_types[:15]
            ]
            scm_report = scm.reasoning_report(all_findings_dicts)
        except Exception as e:
            self.errors.append(f"[AGI SCM推理] {e}")
        
        # 3. 元认知自检
        meta_report = {}
        try:
            from engine.metacognition import metacog
            meta_report = metacog.metacognitive_report(all_findings_dicts if 'all_findings_dicts' in dir() else [{"type": ft} for ft in finding_types])
        except Exception as e:
            self.errors.append(f"[AGI 元认知] {e}")
        
        # 4. 知识图谱导入
        try:
            from engine.knowledge_graph import kg
            kg.import_from_analysis(company_name, all_findings_dicts if 'all_findings_dicts' in dir() else [])
            kg.persist()
        except Exception as e:
            self.errors.append(f"[AGI 知识图谱] {e}")
        
        # 5. 知识库自生长
        auto_extract = {}
        try:
            from engine.knowledge_base import auto_extract_knowledge
            auto_extract = auto_extract_knowledge(
                all_findings_dicts if 'all_findings_dicts' in dir() else [],
                company_name, industry
            )
        except Exception as e:
            print(f"[AGI Pipeline] 知识提取失败: {e}")
        
        # 6. 自愈自动检测
        auto_heal_issues = []
        try:
            from engine.self_healing import auto_detect_inconsistencies
            auto_heal_issues = auto_detect_inconsistencies(all_findings_dicts if 'all_findings_dicts' in dir() else [])
        except Exception as e:
            print(f"[AGI Pipeline] 自愈检测失败: {e}")
        
        # 模块覆盖度报告
        module_coverage = Counter()
        for e in self.events:
            module_coverage[e.module] += 1
        
        return {
            "events_collected": self.stats["events_collected"],
            "modules_covered": len(module_coverage),
            "module_breakdown": dict(module_coverage.most_common()),
            "causal_edges": causal_edges_found,
            "patterns": patterns_found,
            # v2.0 新增
            "scm_reasoning": scm_report,
            "metacognition": meta_report,
            "auto_healing_issues": len(auto_heal_issues),
            "auto_healing_details": auto_heal_issues[:5],
            "knowledge_auto_extract": auto_extract,
            "cross_module_chains": len(bus.get_cross_module_chains()) if 'bus' in dir() else 0,
            "all_modules": [
                "①稽查指令","②线索链","③证据链","④分析链","⑤稽查方法论",
                "⑥代码","⑦文件解析","⑧域分析","⑨⑩⑪跨域","⑫方法论过滤",
                "⑬全链路质量","⑭七步流程","⑮质量保障",
                "推理引擎仪表盘","能力矩阵","智能大脑"
            ],
            "missing_modules": [
                m for m in [
                    "①稽查指令","②线索链","③证据链","④分析链","⑤稽查方法论",
                    "⑥代码","⑦文件解析","⑧域分析","⑨⑩⑪跨域","⑫方法论过滤",
                    "⑬全链路质量","⑭七步流程","⑮质量保障",
                    "推理引擎仪表盘","能力矩阵","智能大脑"
                ]
                if m not in module_coverage
            ],
            "knowledge_injected": True,
            "causal_edges_learned": causal_edges_found,
            "patterns_learned": patterns_found,
            "learning_points_saved": len(finding_types),
        }



# 便捷入口
def create_pipeline() -> AGIPipelineConnector:
    return AGIPipelineConnector()

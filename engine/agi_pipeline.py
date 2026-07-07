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
            # [merged] # create_agent
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
        # 行为准则嵌在税务合规方法论和自愈规则中，此处采集执行摘要
        if rule_executions:
            for rex in rule_executions:
                self.events.append(LearningEvent("智能大脑", "ai_rule_executed", {
                    "rule": rex.get("rule", rex.get("name", ""))[:80],
                    "result": rex.get("result", ""),
                    "trace_id": trace_id,
                }))
                self.stats["events_collected"] += 1
        
        return len(rule_executions or [])
    
    # ─── ① 税务合规指令规则学习 ───
    def ingest_audit_rules(self, rules_used: int, rule_details: List[Dict], findings: List[Dict],
                           trace_id: str, company_id: int):
        """从税务合规指令执行中学习
        
        记录：每条规则触发后实际产生了什么结论，成功率如何。
        """
        events = []
        for f in findings:
            rule_id = f.get("rule_id", f.get("_rule_id", ""))
            if rule_id:
                events.append(LearningEvent("①税务合规指令", "rule_triggered", {
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
                        kb.add_lesson(f"规则{rid}({rd.get('name','')[:20]})触发{count}次", "税务合规指令")
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
    
    # ─── ⑤ 税务合规方法论 → 方法映射 ───
    def ingest_methodologies(self, methodologies_applied: List[Dict], domain_results: List[Dict],
                             trace_id: str):
        """从税务合规方法论应用中学习方法→域→结论的映射关系"""
        for method in methodologies_applied or []:
            m_name = method.get("name", method.get("id", ""))
            domains = method.get("domains", method.get("applicable_domains", []))
            
            self.events.append(LearningEvent("⑤税务合规方法论", "method_applied", {
                "method_name": m_name,
                "domains_count": len(domains),
                "trace_id": trace_id,
            }))
            self.stats["events_collected"] += 1
            
            # 学习方法论的有效性：以后分析方法论命中域次数
            try:
                kb = __import__('engine.knowledge_base', fromlist=['get_kb']).get_kb()
                kb.add_lesson(f"方法论'{m_name[:30]}'在{len(domains)}个域中应用", "⑤税务合规方法论")
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
                "high_risk_count": sum(1 for e in self.events if hasattr(e, 'data') and isinstance(e.data, dict) and "高风险" in str(e.data.get("level", ""))),
            })
            kb.add_lesson(f"完成一次全模块分析，采集{self.stats['events_collected']}个学习事件", "综合")
        except: pass
        
        # ─── 提取 finding_types 和 data_profile ───
        finding_types = []
        ft_level = {}   # finding_type → 风险等级（供数据驱动行业画像沉淀高风险）
        data_profile = {}
        
        for event in self.events:
            # 提取 finding_type
            if event.module == "①税务合规指令" and event.event_type == "rule_triggered":
                ft = event.data.get("finding_type", "")
                if ft and ft not in finding_types:
                    finding_types.append(ft)
                if ft:
                    lv = event.data.get("level", "")
                    # 保留更高等级（"高"优先于空/低）
                    if lv and ("高" in str(lv) or not ft_level.get(ft)):
                        ft_level[ft] = lv
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
            if not isinstance(memory, dict):
                memory = {"analyses": [], "industry_patterns": {}, "lesson_learned": []}
        except:
            memory = {"analyses": [], "industry_patterns": {}, "lesson_learned": []}
        # 骨架兜底：防止旧文件/空文件结构缺失导致 KeyError/TypeError
        memory.setdefault("analyses", [])
        memory.setdefault("industry_patterns", {})
        memory.setdefault("lesson_learned", [])
        
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
        edges = []
        patterns = []
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
            # [merged] # bus, AGIEvents
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
                {"type": ft, "level": ft_level.get(ft, ""),
                 "signals": [e.data.get("signal","") for e in self.events if e.event_type == "rule_triggered" and e.data.get("finding_type") == ft]}
                for ft in finding_types
            ]
            scm_report = scm.reasoning_report(all_findings_dicts)
        except Exception as e:
            self.errors.append(f"[AGI SCM推理] {e}")
        
        # 3. 元认知自检
        meta_report = {}
        try:
            # [merged] # metacog
            meta_report = metacog.metacognitive_report(all_findings_dicts if 'all_findings_dicts' in dir() else [{"type": ft} for ft in finding_types])
        except Exception as e:
            self.errors.append(f"[AGI 元认知] {e}")
        
        # 4. 知识图谱导入
        try:
            # [merged] # kg
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
                "①税务合规指令","②线索链","③证据链","④分析链","⑤税务合规方法论",
                "⑥代码","⑦文件解析","⑧域分析","⑨⑩⑪跨域","⑫方法论过滤",
                "⑬全链路质量","⑭七步流程","⑮质量保障",
                "推理引擎仪表盘","能力矩阵","智能大脑"
            ],
            "missing_modules": [
                m for m in [
                    "①税务合规指令","②线索链","③证据链","④分析链","⑤税务合规方法论",
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


# ═══════ [合并自 engine/agent_core.py] ═══════
"""
财税智能体核心引擎 —— AgentCore

五层架构：感知→推理→学习→表达→记忆
设计哲学：不只是规则引擎，而是像一个真正的税务合规员一样思考。

能力边界：
  ✅ 假设驱动分析 — 基于数据模式主动生成调查假设
  ✅ 跨分析学习 — 从历史案例中归纳行业通用模式
  ✅ 自我反思 — 对每个结论进行反向假设验证
  ✅ 洞见总结 — 生成有因果推理的综合性报告
  ✅ 可追溯解释 — 每个结论可追溯到原始数据

核心创新：
  1. 主动假设生成：不只等规则触发，而是主动问"这个企业可能有什么问题？"
  2. 模式归纳：从多个企业的分析中归纳行业通用风险模式
  3. 自我质疑：每条结论生成反向假设并尝试证伪
  4. 记忆积累：每次分析成为经验，提升下次分析质量
"""
import json, os, time, re, uuid
from datetime import datetime
from collections import defaultdict, Counter
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict

# ==================== 数据类 ====================

@dataclass
class Hypothesis:
    """调查假设"""
    id: str
    description: str          # 假设描述：这家企业可能虚开进项发票
    trigger_signals: List[str] # 触发信号
    confidence: float          # 初始置信度 0-1
    evidence_for: List[Dict] = field(default_factory=list)
    evidence_against: List[Dict] = field(default_factory=list)
    verified: Optional[bool] = None
    final_confidence: float = 0.0
    causal_chain: List[str] = field(default_factory=list)

@dataclass
class AnalysisMemory:
    """分析记忆——每次分析的完整快照"""
    trace_id: str
    company_id: int
    company_name: str
    industry: str
    biz_model: str
    timestamp: str
    key_findings_count: int
    high_risk_count: int
    generated_hypotheses: int
    verified_hypotheses: int
    learning_points: List[str] = field(default_factory=list)
    data_profile: Dict = field(default_factory=dict)

@dataclass
class IndustryPattern:
    """行业通用风险模式"""
    industry: str
    pattern_name: str
    description: str
    trigger_conditions: List[str]
    occurrence_count: int
    confidence: float
    last_seen: str
    companies_affected: List[str] = field(default_factory=list)

# ==================== 1. 假设生成器 ====================

class HypothesisGenerator:
    """基于数据模式主动生成调查假设
    
    不像规则引擎那样被动等待触发，而是主动思考：
    - 看到进项发票中加工费占比高 → 生成"委托加工真实性"假设
    - 看到供应商高度集中在同城 → 生成"关联交易/虚开发票"假设
    - 看到银行收款远超开票 → 生成"隐匿收入"假设
    """
    
    HYPOTHESIS_TEMPLATES = [
        {
            "id": "H001", "name": "隐匿销售收入",
            "trigger": lambda ctx: ctx.get("bank_in_ratio", 0) > 1.3 and ctx.get("invoice_count", 0) > 5,
            "confidence": lambda ctx: min(0.95, (ctx.get("bank_in_ratio", 1) - 1) * 0.7),
            "description": lambda ctx: f"银行收款为开票收入的{ctx.get('bank_in_ratio',0):.1f}倍，可能存在未申报销售收入",
            "investigation_chain": [
                "逐户比对银行收款方与销项发票客户名称",
                "计算未匹配收款的金额和占比",
                "排查非经营性收款（注资、借款、往来款）",
                "无法说明来源的差额按隐匿收入处理"
            ]
        },
        {
            "id": "H002", "name": "虚开进项发票",
            "trigger": lambda ctx: ctx.get("supplier_concentration", 0) > 0.6 and ctx.get("pur_count", 0) > 10,
            "confidence": lambda ctx: min(0.9, ctx.get("supplier_concentration", 0) * 1.2),
            "description": lambda ctx: f"供应商高度集中({ctx.get('supplier_concentration',0):.0%}集中在少数供应商)，可能虚开进项",
            "investigation_chain": [
                "联网核查主要供应商的工商状态（天眼查/企查查）",
                "比对供应商注册地址是否住宅/虚拟地址",
                "核查银行付款记录——无付款的进项发票进项税额转出",
                "核查物流单据——无运输凭证的采购无法证实货物真实流转"
            ]
        },
        {
            "id": "H003", "name": "委托加工真实性存疑",
            "trigger": lambda ctx: ctx.get("has_processing_fee", False) and ctx.get("pur_count", 0) > 5,
            "confidence": lambda ctx: 0.7 if ctx.get("has_processing_fee") else 0.0,
            "description": "进项发票中含加工费，需核实委托加工的真实性",
            "investigation_chain": [
                "BOM验证：投入产出比率是否合理",
                "加工商地址核查：运输成本是否匹配",
                "加工合同：是否有书面委托加工协议",
                "资金流核查：加工费付款方是否为企业对公账户"
            ]
        },
        {
            "id": "H004", "name": "关联交易转移利润",
            "trigger": lambda ctx: ctx.get("has_related_parties", False) or ctx.get("has_six_personnel_overlap", False),
            "confidence": lambda ctx: 0.8 if ctx.get("has_related_parties") else 0.5,
            "description": "存在关联方或人员重叠，可能存在转移定价/利润转移",
            "investigation_chain": [
                "核查关联交易的定价是否公允（独立交易原则）",
                "比对关联方与非关联方的毛利率差异",
                "检查是否存在资金回流（付款后回流到控制人账户）",
                "评估是否存在不合理分摊费用/让渡利润"
            ]
        },
        {
            "id": "H005", "name": "虚列成本费用",
            "trigger": lambda ctx: ctx.get("pur_without_payment_ratio", 0) > 0.3 and ctx.get("pur_count", 0) > 10,
            "confidence": lambda ctx: min(0.85, ctx.get("pur_without_payment_ratio", 0) * 1.5),
            "description": lambda ctx: f"{ctx.get('pur_without_payment_ratio',0):.0%}的进项发票无对应银行付款，可能虚列成本",
            "investigation_chain": [
                "逐笔核实无付款进项发票的真实性",
                "核查是否存在现金交易——但大额交易必须银行转账",
                "取得供应商确认函或对账单",
                "无法证实真实的进项发票做进项税额转出"
            ]
        },
        {
            "id": "H006", "name": "进销品名不匹配",
            "trigger": lambda ctx: ctx.get("goods_mismatch_ratio", 0) > 0.3 and ctx.get("sal_count", 0) > 5,
            "confidence": lambda ctx: min(0.85, ctx.get("goods_mismatch_ratio", 0) * 2),
            "description": lambda ctx: f"进销品名匹配率仅{1-ctx.get('goods_mismatch_ratio',0):.0%}，可能存在虚开或隐匿收入",
            "investigation_chain": [
                "逐品名比对进销差异",
                "核查是否有委外加工（可解释品名差异）",
                "核查是否有视同销售未申报",
                "如无合理解释→进项税额转出+补缴销项税额"
            ]
        },
        {
            "id": "H007", "name": "会计账簿不健全→核定征收",
            "trigger": lambda ctx: ctx.get("data_quality_score", 100) < 40,
            "confidence": lambda ctx: 0.9 if ctx.get("data_quality_score", 100) < 40 else 0.3,
            "description": lambda ctx: f"资料完整度仅{ctx.get('data_quality_score',0)}分，会计账簿可能不健全",
            "investigation_chain": [
                "确认缺失资料是否无法补全",
                "评估是否触发《税收征收管理法》第35条核定征收条件",
                "测算核定征收对税负的影响",
                "建议补全资料以恢复正常征收方式"
            ]
        },
        {
            "id": "H008", "name": "小型微利企业资格不符",
            "trigger": lambda ctx: ctx.get("near_micro_limit", False),
            "confidence": lambda ctx: 0.6,
            "description": "企业接近但可能超出小微企业标准，需核实是否仍符合条件",
            "investigation_chain": [
                "核实应纳税所得额是否确≤300万",
                "核实从业人数季度平均值是否≤300人",
                "核实资产总额季度平均值是否≤5000万",
                "核实是否属于限制行业（如非金融、非房地产）"
            ]
        },
        {
            "id": "H009", "name": "发票群集性虚开",
            "trigger": lambda ctx: ctx.get("cluster_risk", False),
            "confidence": lambda ctx: 0.85 if ctx.get("cluster_risk") else 0.2,
            "description": "发票开具时间和金额呈现群集性特征，可能批量虚开",
            "investigation_chain": [
                "检查连续发票号码是否来自同一批次",
                "核查开票时间是否集中在非营业时间",
                "比对交易金额是否与经营范围匹配",
                "核查受票方是否为空壳公司"
            ]
        },
    ]
    
    def generate(self, context: Dict) -> List[Hypothesis]:
        """从数据上下文中生成假设"""
        hypotheses = []
        
        for template in self.HYPOTHESIS_TEMPLATES:
            try:
                if template["trigger"](context):
                    conf = template["confidence"](context)
                    if conf > 0.3:  # 过滤低置信度假设
                        desc = template["description"]
                        if callable(desc):
                            desc = desc(context)
                        
                        h = Hypothesis(
                            id=template["id"],
                            description=str(desc),
                            trigger_signals=[template["name"]],
                            confidence=round(conf, 2),
                            causal_chain=list(template["investigation_chain"]),
                        )
                        hypotheses.append(h)
            except Exception:
                pass
        
        # 按置信度排序
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        return hypotheses


# ==================== 2. 自我反思器 ====================

class SelfReflector:
    """对分析结论进行自我质疑——反向假设验证
    
    核心逻辑：对每条高风险及以上结论，生成相反假设并尝试证明。
    如果反向假设也能成立 → 原结论可信度降低 → 标记为需要更多证据
    阈值已调低，使反思器更积极地质疑结论。
    """
    
    @staticmethod
    def reflect(findings: List[Dict], context: Dict) -> List[Dict]:
        """对发现列表进行自我反思"""
        reflected = []
        total_checked = 0
        total_uncertain = 0
        total_refuted = 0
        
        for f in findings:
            level = f.get("level", "")
            score = f.get("score", 0)
            ftype = f.get("type", "")
            
            # 反思高风险 + 评分>=6的中风险
            if level == "高风险" or score >= 6:
                total_checked += 1
                reflection = SelfReflector._reflect_single(f, context)
                f["_self_reflection"] = reflection
                # 降低阈值：adj<-0.05→不确定, adj<-0.15→被推翻
                adj = reflection.get("confidence_adjustment", 0)
                if adj < -0.15:
                    reflection["verdict"] = "refuted"
                    total_refuted += 1
                    f["_reflection_verdict"] = "refuted"
                elif adj < -0.05 or abs(adj) > 0.1:
                    reflection["verdict"] = "uncertain"
                    total_uncertain += 1
                    f["_reflection_verdict"] = "uncertain"
            reflected.append(f)
        
        return reflected
    
    @staticmethod
    def _reflect_single(finding: Dict, context: Dict) -> Dict:
        """对单条结论进行自我反思（扩展版：覆盖更多发现类型）"""
        ftype = finding.get("type", "")
        detail = finding.get("detail", "")
        reflections = {
            "counter_hypothesis": "",
            "counter_evidence": [],
            "confirmation_evidence": [],
            "confidence_adjustment": 0,
            "verdict": "confirmed",
        }
        
        # 隐匿收入
        if any(kw in ftype for kw in ["隐匿收", "未申报", "少报", "账外"]):
            reflections["counter_hypothesis"] = "银行收款超额可能因非经营性收款（股东注资/借款/往来款），而非隐匿收入"
            if context.get("has_personal_payments"):
                reflections["counter_evidence"].append("存在个人转账，可能是非经营性收款")
                reflections["confidence_adjustment"] -= 0.15
            if context.get("bank_in_ratio", 0) < 1.2:
                reflections["counter_evidence"].append(f"银行收款超额幅度较小(bank_in_ratio={context.get('bank_in_ratio',0):.2f})")
                reflections["confidence_adjustment"] -= 0.1
            if context.get("data_quality_score", 0) < 30:
                reflections["counter_evidence"].append("资料完整度不足，结论依赖有限数据")
                reflections["confidence_adjustment"] -= 0.1
        
        # 虚开发票
        elif any(kw in ftype for kw in ["虚开", "虚假发票"]):
            reflections["counter_hypothesis"] = "进项发票集中可能因企业与特定供应商有长期稳定合作关系"
            conc = context.get("supplier_concentration", 0)
            if conc < 0.6:
                reflections["counter_evidence"].append(f"供应商集中度{conc:.2f}，未达到极端水平")
                reflections["confidence_adjustment"] -= 0.08
            if conc < 0.4:
                reflections["confidence_adjustment"] -= 0.05
        
        # 品名不匹配
        elif any(kw in ftype for kw in ["品名", "进销不匹配"]):
            reflections["counter_hypothesis"] = "品名差异可能因外发加工导致进料和成品名称不同"
            if context.get("has_processing_fee"):
                reflections["counter_evidence"].append("存在加工费发票，可解释品名差异")
                reflections["confidence_adjustment"] -= 0.2
            if context.get("has_manufacturing"):
                reflections["counter_evidence"].append("企业存在制造业特征，品名变化正常")
                reflections["confidence_adjustment"] -= 0.12
        
        # 账簿不健全
        elif any(kw in ftype for kw in ["账簿", "核定征收", "资料不完整", "资料缺失"]):
            reflections["counter_hypothesis"] = "资料不完整可能因部分资料未上传，而非实质缺失"
            dq = context.get("data_quality_score", 0)
            if dq > 30:
                reflections["counter_evidence"].append(f"仍有部分资料可用(dq_score={dq})，可能只是上传不完整")
                reflections["confidence_adjustment"] -= 0.12
            if dq > 50:
                reflections["confidence_adjustment"] -= 0.08
        
        # 关联交易
        elif any(kw in ftype for kw in ["关联交易", "关联方", "利益输送"]):
            reflections["counter_hypothesis"] = "关联方交易可能存在合理商业目的，未必是利益输送"
            if context.get("has_processing_fee"):
                reflections["counter_evidence"].append("存在委托加工关系，可能为正常业务往来")
                reflections["confidence_adjustment"] -= 0.1
        
        # 资金流不匹配
        elif any(kw in ftype for kw in ["资金流", "银行流水不匹配", "银行收款不匹配"]):
            reflections["counter_hypothesis"] = "资金流与发票流偏差可能因时间差或非对公支付造成"
            mismatch = context.get("bank_in_ratio", 1)
            if 0.8 < mismatch < 1.2:
                reflections["counter_evidence"].append("偏差在合理范围内(±20%)，可能是时间性差异")
                reflections["confidence_adjustment"] -= 0.15
        
        # 供应商集中度风险
        elif any(kw in ftype for kw in ["供应商集中", "集中度", "依赖"]):
            reflections["counter_hypothesis"] = "供应商集中可能因行业特征或特定原材料垄断"
            if context.get("industry") in ["纺织", "服装", "电子"]:
                reflections["counter_evidence"].append("该行业供应商集中属常见现象")
                reflections["confidence_adjustment"] -= 0.08
        
        return reflections


# ==================== 3. 跨分析学习器 ====================

class CrossAnalysisLearner:
    """从多企业分析中归纳行业通用模式
    
    核心：一家企业发现的规律，下次分析同行业企业时自动应用。
    """
    
    MEMORY_FILE = None
    
    @classmethod
    def _get_memory_path(cls):
        if cls.MEMORY_FILE is None:
            base = os.path.dirname(os.path.dirname(__file__))
            cls.MEMORY_FILE = os.path.join(base, "static", "cross_analysis_memory.json")
        return cls.MEMORY_FILE
    
    @classmethod
    def load_memory(cls) -> Dict:
        try:
            with open(cls._get_memory_path(), "r", encoding="utf-8") as f:
                mem = json.load(f)
            if not isinstance(mem, dict):
                mem = {"analyses": [], "industry_patterns": {}, "lesson_learned": []}
        except:
            mem = {"analyses": [], "industry_patterns": {}, "lesson_learned": []}
        mem.setdefault("analyses", [])
        mem.setdefault("industry_patterns", {})
        mem.setdefault("lesson_learned", [])
        return mem
    
    @classmethod
    def save_memory(cls, memory: Dict):
        os.makedirs(os.path.dirname(cls._get_memory_path()), exist_ok=True)
        with open(cls._get_memory_path(), "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def record_analysis(cls, memory: AnalysisMemory):
        """记录一次分析的完整快照"""
        store = cls.load_memory()
        store["analyses"].append(asdict(memory))
        
        # 归纳行业模式
        industry = memory.industry
        if industry and industry != "未知":
            if industry not in store["industry_patterns"]:
                store["industry_patterns"][industry] = {
                    "analyses_count": 0,
                    "common_high_risks": Counter(),
                    "avg_risk_score": 0,
                    "typical_data_profile": {},
                }
            
            ip = store["industry_patterns"][industry]
            ip["analyses_count"] += 1
            for lp in memory.learning_points:
                ip["common_high_risks"][lp] += 1
        
        cls.save_memory(store)
    
    @classmethod
    def get_industry_insights(cls, industry: str) -> Dict:
        """获取行业的累积分析洞察——对新分析的指导"""
        store = cls.load_memory()
        ip = store["industry_patterns"].get(industry, {})
        
        if not ip or ip.get("analyses_count", 0) < 2:
            return {"has_insights": False, "message": "该行业分析样本不足，暂无行业洞察"}
        
        common_risks = ip.get("common_high_risks", {})
        top_risks = common_risks.most_common(5) if hasattr(common_risks, 'most_common') else []
        
        return {
            "has_insights": True,
            "industry": industry,
            "analyses_count": ip["analyses_count"],
            "top_risk_patterns": top_risks,
            "guidance": cls._generate_industry_guidance(industry, top_risks),
        }
    
    @staticmethod
    def _generate_industry_guidance(industry: str, top_risks: List) -> str:
        if not top_risks:
            return "暂无"
        lines = [f"根据{industry}行业历史分析经验，建议重点关注："]
        for risk, count in top_risks[:3]:
            lines.append(f"  · {risk}（{count}次出现）")
        return "\n".join(lines)
    
    @classmethod
    def add_lesson(cls, lesson: str, category: str = "通用"):
        """添加一条经验教训"""
        store = cls.load_memory()
        store["lesson_learned"].append({
            "lesson": lesson,
            "category": category,
            "timestamp": datetime.now().isoformat(),
        })
        cls.save_memory(store)


# ==================== 4. 洞见总结引擎 ====================

class InsightSynthesizer:
    """生成有洞见的综合报告——不只是罗列发现
    
    能力：
    1. 风险因果链总结
    2. 核心问题提炼
    3. 对比行业基准
    4. 优先级排序
    5. 可执行建议
    """
    
    @staticmethod
    def synthesize(all_findings: List[Dict], context: Dict) -> str:
        """生成综合洞见报告"""
        sections = []
        
        # 1. 核心画像
        sections.append(InsightSynthesizer._profile_section(context))
        
        # 2. 风险全景
        sections.append(InsightSynthesizer._risk_overview(all_findings))
        
        # 3. 核心问题提炼
        sections.append(InsightSynthesizer._core_issues(all_findings, context))
        
        # 4. 行业对标
        sections.append(InsightSynthesizer._industry_compare(context))
        
        # 5. 优先级行动建议
        sections.append(InsightSynthesizer._action_plan(all_findings))
        
        return "\n\n".join(sections)
    
    @staticmethod
    def _profile_section(ctx: Dict) -> str:
        cp = ctx.get("company_profile", {})
        fs = ctx.get("financial_snapshot", {})
        
        lines = [
            "▌一、企业画像",
            f"行业：{cp.get('industry', '未知')} | 经营模式：{cp.get('biz_model', '未知')}",
            f"经营规模：销项{fs.get('sale_count',0)}张/{fs.get('total_sales',0):,.0f}元 | 进项{fs.get('pur_count',0)}张/{fs.get('total_purchases',0):,.0f}元",
            f"银行流水：收款{fs.get('total_bank_in',0):,.0f}元 | 付款{fs.get('total_bank_out',0):,.0f}元",
        ]
        if fs.get("gross_margin_pct", 0):
            lines.append(f"毛利率：{fs['gross_margin_pct']}%")
        return "\n".join(lines)
    
    @staticmethod
    def _risk_overview(findings: List[Dict]) -> str:
        high = sum(1 for f in findings if f.get("level") == "高风险")
        mid = sum(1 for f in findings if f.get("level") == "中风险")
        
        lines = ["▌二、风险全景"]
        lines.append(f"共{len(findings)}项发现 ：高风险{high}项 | 中风险{mid}项 | 低风险{len(findings)-high-mid}项")
        
        # Top 5 高风险
        top_high = [f for f in findings if f.get("level") == "高风险"][:5]
        for i, f in enumerate(top_high, 1):
            detail = str(f.get("detail", f.get("type", "")))[:80]
            lines.append(f"  {i}. [{f.get('level','')}] {detail}")
        
        return "\n".join(lines)
    
    @staticmethod
    def _core_issues(findings: List[Dict], ctx: Dict) -> str:
        lines = ["▌三、核心问题提炼"]
        
        # 从假设中提取已验证的核心问题
        hypotheses = [f for f in findings if f.get("_hypothesis_verified")]
        if not hypotheses:
            high_risks = [f for f in findings if f.get("level") == "高风险" and f.get("score", 0) >= 7]
            if high_risks:
                lines.append(f"经交叉验证，本企业的核心风险集中在：")
                for hr in high_risks[:3]:
                    lines.append(f"  · {hr.get('type', '')}")
            else:
                lines.append("未发现重大核心风险。企业整体税务合规状况良好。")
        else:
            for h in hypotheses[:3]:
                lines.append(f"  · {h.get('type','')}: {h.get('detail','')[:80]}")
        
        return "\n".join(lines)
    
    @staticmethod
    def _industry_compare(ctx: Dict) -> str:
        cp = ctx.get("company_profile", {})
        industry = cp.get("industry", "未知")
        
        lines = ["▌四、行业对标"]
        
        insights = CrossAnalysisLearner.get_industry_insights(industry)
        
        if insights.get("has_insights"):
            lines.append(insights["guidance"])
        else:
            lines.append(f"{industry}行业暂无足够历史分析样本用于对标比较。")
        
        return "\n".join(lines)
    
    @staticmethod
    def _action_plan(findings: List[Dict]) -> str:
        lines = ["▌五、优先行动建议"]
        
        priorities = {"P0": [], "P1": [], "P2": []}
        for f in findings:
            if f.get("level") == "高风险" and f.get("score", 0) >= 8:
                priorities["P0"].append(f)
            elif f.get("level") == "高风险":
                priorities["P1"].append(f)
            else:
                priorities["P2"].append(f)
        
        if priorities["P0"]:
            lines.append(f"\n【P0 — 立即行动】{len(priorities['P0'])}项")
            for f in priorities["P0"][:3]:
                action = f.get("action", f.get("suggestion", f.get("detail", "")))[:100]
                lines.append(f"  · {action}")
        
        if priorities["P1"]:
            lines.append(f"\n【P1 — 重点关注】{len(priorities['P1'])}项")
            for f in priorities["P1"][:2]:
                action = f.get("action", f.get("suggestion", f.get("detail", "")))[:80]
                lines.append(f"  · {action}")
        
        return "\n".join(lines)


# ==================== 5. 智能体核心 ====================

class TaxAuditAgent:
    """财税税务合规智能体核心
    
    统一调度五层引擎，模拟一个真正的税务合规员的思考过程。
    
    v1.1 进化：
    - 自主推理器(AutonomousReasoner)替代手工模板
    - 从历史分析数据中学习因果关系
    - 多信号条件概率网络驱动假设生成
    - 未知模式检测 → 智哥介入 → 规则注入
    
    工作流：
        analyze() 入口
          ↓
        1. 感知层 — 数据解析 + 特征提取 + 异常检测
          ↓
        2. 推理层 — 自主推理器(因果网络) + 假设生成
          ↓
        2.5 未知模式扫描
          ↓
        3. 学习层 — 历史经验 + 行业模式 + 自愈修正
          ↓
        4. 表达层 — 洞见总结 + 可追溯解释
          ↓
        5. 记忆层 + 因果网络训练 — 保存快照 + 更新因果边
    """
    
    def __init__(self, db_session=None):
        self.db = db_session
        self.reflector = SelfReflector()
        self.learner = CrossAnalysisLearner()
        self.synthesizer = InsightSynthesizer()
        
        # v1.1: 自主推理器替代手工模板
        self.reasoner = None
        try:
            from engine.causal_network import create_autonomous_reasoner
            self.reasoner = create_autonomous_reasoner()
        except Exception:
            self.reasoner = HypothesisGenerator()  # 回退
        
        # v1.2: 语义推理器 + 创造性假设引擎
        self.semantic_reasoner = None
        try:
            from engine.semantic_reasoner import SemanticReasoner
            self.semantic_reasoner = SemanticReasoner()
        except Exception:
            pass
        
        # 未知模式检测器
        self.unknown_detector = None
        try:
            from engine.unknown_pattern_detector import UnknownPatternDetector, route_to_zhige
            self.unknown_detector = UnknownPatternDetector()
        except Exception:
            pass
        
        # 分析状态
        self.context = {}
        self.hypotheses = []
        self.industry_insights = {}
        self.analysis_memory = None
        self.discovery_result = None  # 未知模式发现结果
    
    def perceive(self, bank_txs, invoices, salaries, vouchers, ctx) -> Dict:
        """感知层：数据解析 + 特征提取 + 异常检测"""
        if ctx is None:
            return {}
        
        cp = ctx.company_profile or {}
        fs = ctx.financial_snapshot or {}
        
        # 计算关键比率
        total_sales = fs.get("total_sales", 0)
        total_bank_in = fs.get("total_bank_in", 0)
        total_purchases = fs.get("total_purchases", 0)
        total_bank_out = fs.get("total_bank_out", 0)
        
        bank_in_ratio = total_bank_in / total_sales if total_sales > 0 else 1.0
        bank_out_ratio = total_bank_out / total_purchases if total_purchases > 0 else 1.0
        
        # 进销品名匹配率
        sal_goods = set()
        pur_goods = set()
        for inv in invoices or []:
            goods = str(inv.get("goods", "")).strip()
            if not goods:
                continue
            if inv.get("direction") in ("销项", "sales"):
                sal_goods.add(goods)
            else:
                pur_goods.add(goods)
        
        match_count = len(sal_goods & pur_goods)
        total_goods = len(sal_goods | pur_goods)
        goods_match_ratio = match_count / total_goods if total_goods > 0 else 1.0
        
        # 付款覆盖率
        pur_count = len([i for i in invoices or [] if i.get("direction") in ("进项", "purchase")])
        
        return {
            # 财务指标
            "bank_in_ratio": round(bank_in_ratio, 2),
            "bank_out_ratio": round(bank_out_ratio, 2),
            "goods_match_ratio": round(goods_match_ratio, 2),
            "goods_mismatch_ratio": round(1 - goods_match_ratio, 2),
            
            # 企业特征
            "industry": cp.get("industry", "未知"),
            "biz_model": cp.get("biz_model", "未知"),
            "company_profile": cp,
            "financial_snapshot": fs,
            
            # 信号
            "has_processing_fee": getattr(ctx, 'has_processing_fee', False),
            "has_personal_payments": getattr(ctx, 'has_personal_payments', False),
            "has_related_parties": getattr(ctx, 'has_related_parties', False),
            "has_six_personnel_overlap": getattr(ctx, 'has_six_personnel_overlap', False),
            "supplier_concentration": getattr(ctx, 'supplier_concentration', 0),
            "customer_concentration": getattr(ctx, 'customer_concentration', 0),
            "data_quality_score": getattr(ctx, 'data_quality_score', 100),
            "near_micro_limit": getattr(ctx, 'near_micro_limit', False),
            "cluster_risk": getattr(ctx, 'cluster_risk', False),
            "has_manufacturing": cp.get("has_manufacturing", False),
            
            # 原始数据摘要
            "sal_count": fs.get("sale_count", 0),
            "pur_count": fs.get("pur_count", 0),
            "invoice_count": fs.get("sale_count", 0) + fs.get("pur_count", 0),
            "pur_without_payment_ratio": 1 - bank_out_ratio if bank_out_ratio < 1 else 0,
        }
    
    def reason(self, context: Dict, existing_findings: List[Dict] = None) -> List:
        """推理层：自主推理器(因果网络)驱动假设生成"""
        if self.reasoner is None:
            return []
        
        # v1.1: 使用自主推理器而非模板
        if hasattr(self.reasoner, 'reason'):
            result = self.reasoner.reason(context, existing_findings or [])
            self.hypotheses = [
                Hypothesis(
                    id=f"AR_{i}",
                    description=p.get("finding", ""),
                    trigger_signals=[p.get("trigger", "")],
                    confidence=p.get("confidence", 0.5),
                    causal_chain=[
                        f"因果网络预测: {p.get('trigger','')}",
                        f"置信度: {p.get('confidence',0):.0%}",
                        f"证据: {p.get('evidence','')}"
                    ],
                    verified=None,
                )
                for i, p in enumerate(result.get("predictions", [])[:8])
            ]
            
            # v2.0: SCM因果推理增强
            try:
                from engine.scm_reasoner import scm
                for hp in self.hypotheses:
                    signals_for_scm = hp.trigger_signals if isinstance(hp.trigger_signals, list) else [hp.trigger_signals]
                    for sig in signals_for_scm:
                        intervention = scm.do_intervention(sig, "eliminate")
                        if intervention.get("total_affected", 0) > 0:
                            hp.causal_chain.append(f"SCM干预: 消除{sig}→影响{intervention['total_affected']}个下游变量")
            except Exception:
                pass
            
            return self.hypotheses
        
        # 回退到模板生成器
        if hasattr(self.reasoner, 'generate'):
            self.hypotheses = self.reasoner.generate(context)
            return self.hypotheses
        
        return []
    
    def learn(self, industry: str, all_findings: List[Dict]) -> Dict:
        """学习层：跨分析经验 + 行业模式"""
        self.industry_insights = self.learner.get_industry_insights(industry)
        
        # 提取本次学习要点
        learning_points = []
        for f in all_findings:
            if f.get("level") == "高风险":
                learning_points.append(f.get("type", ""))
        
        return self.industry_insights
    
    def reflect(self, all_findings: List[Dict], context: Dict) -> List[Dict]:
        """反思层：自我质疑 + 反向验证"""
        return self.reflector.reflect(all_findings, context)
    
    def express(self, all_findings: List[Dict], context: Dict) -> str:
        """表达层：洞见总结"""
        return self.synthesizer.synthesize(all_findings, context)
    
    def remember(self, company_id: int, company_name: str, industry: str, 
                 biz_model: str, all_findings: List[Dict], trace_id: str):
        """记忆层：保存分析快照"""
        self.analysis_memory = AnalysisMemory(
            trace_id=trace_id or str(uuid.uuid4())[:8],
            company_id=company_id,
            company_name=company_name,
            industry=industry or "未知",
            biz_model=biz_model or "未知",
            timestamp=datetime.now().isoformat(),
            key_findings_count=len(all_findings),
            high_risk_count=sum(1 for f in all_findings if f.get("level") == "高风险"),
            generated_hypotheses=len(self.hypotheses),
            verified_hypotheses=sum(1 for h in self.hypotheses if h.verified),
            learning_points=[h.description[:80] for h in self.hypotheses if h.verified],
            data_profile={
                "bank_in_ratio": self.context.get("bank_in_ratio", 0),
                "supplier_concentration": self.context.get("supplier_concentration", 0),
                "goods_match_ratio": self.context.get("goods_match_ratio", 0),
            }
        )
        self.learner.record_analysis(self.analysis_memory)
    
    def analyze(self, bank_txs, invoices, salaries, vouchers, ctx, 
                company_id=0, company_name="", db_session=None) -> Dict:
        """完整分析流程——智能体五步思考法"""
        
        # Step 1: 感知
        self.context = self.perceive(bank_txs, invoices, salaries, vouchers, ctx)
        
        # Step 2: 推理
        self.reason(self.context)
        
        # Step 2.5: 语义分析 + 创造性推理
        creative_result = None
        if self.semantic_reasoner and self.unknown_detector:
            try:
                # 语义品名分析
                from engine.semantic_reasoner import SemanticMatcher
                sem = SemanticMatcher()
                
                # 创造性推理：基于当前活跃信号和因果网络
                active_sigs = []
                try:
                    from engine.causal_network import PRIMARY_SIGNALS
                    for sig_id, sig_name, detector in PRIMARY_SIGNALS:
                        if detector(self.context):
                            active_sigs.append(sig_name)
                except: pass
                causal_edges = getattr(self.reasoner, 'network', None)
                if causal_edges:
                    creative_result = self.semantic_reasoner.creative_reason(
                        active_sigs,
                        getattr(causal_edges, 'edges', []),
                        getattr(causal_edges, 'patterns', []),
                    )
            except Exception:
                pass
        
        # Step 3: 学习（获取行业洞察）
        industry = self.context.get("industry", "未知")
        self.learn(industry, [])
        
        # 返回智能体状态
        return {
            "agent_version": "1.1",
            "context": {
                "industry": industry,
                "bank_in_ratio": self.context.get("bank_in_ratio", 0),
                "goods_match_ratio": self.context.get("goods_match_ratio", 0),
                "data_quality_score": self.context.get("data_quality_score", 100),
            },
            "hypotheses": [
                {
                    "id": h.id,
                    "description": h.description,
                    "confidence": h.confidence,
                    "investigation_chain": h.causal_chain[:3],
                }
                for h in self.hypotheses[:5]
            ],
            "industry_insights": self.industry_insights,
            "reflection_pending": True,
        }
    
    def finalize(self, all_findings: List[Dict], trace_id: str, 
                 company_id: int, company_name: str,
                 bank_txs=None, invoices=None, salaries=None, vouchers=None) -> Dict:
        """分析收尾：反思 + 未知模式扫描 + 总结 + 记忆"""
        
        # Step 3.5: 未知模式扫描（在反思之前——先看自己哪里不懂）
        discovery = None
        if self.unknown_detector:
            try:
                discovery = self.unknown_detector.scan(
                    bank_txs or [], invoices or [], salaries or [], vouchers or [],
                    self.context, all_findings, 
                    [{"id": h.id, "description": h.description, "type": h.id} for h in self.hypotheses],
                    company_id, company_name, trace_id
                )
                self.discovery_result = discovery
            except Exception as e:
                import traceback
                self.context["_detector_error"] = f"{e}: {traceback.format_exc()[-200:]}"
        
        # Step 4: 反思
        reflected_findings = self.reflect(all_findings, self.context)
        
        # Step 5: 总结
        insight_text = self.express(reflected_findings, self.context)
        
        # Step 6: 记忆
        self.remember(
            company_id, company_name,
            self.context.get("industry", "未知"),
            self.context.get("biz_model", "未知"),
            all_findings, trace_id
        )
        
        # Step 7: 训练因果网络（从本次分析中学习新的因果边）
        training_result = None
        if hasattr(self.reasoner, 'train_and_update') and self.reasoner is not None:
            try:
                training_result = self.reasoner.train_and_update()
            except Exception:
                pass
        
        result = {
            "agent_version": "1.1",
            "insight_summary": insight_text,
            "reflection": {
                "total_checked": len(all_findings),
                "confirmed": sum(1 for f in reflected_findings if f.get("_self_reflection", {}).get("verdict") == "confirmed"),
                "uncertain": sum(1 for f in reflected_findings if f.get("_self_reflection", {}).get("verdict") == "uncertain"),
                "refuted": sum(1 for f in reflected_findings if f.get("_self_reflection", {}).get("verdict") == "refuted"),
            },
            "memory": {
                "saved": self.analysis_memory is not None,
                "trace_id": trace_id,
                "industry_experience": self.industry_insights.get("analyses_count", 0),
            },
            "causal_network": training_result,  # 因果网络训练结果
            "reflected_findings": reflected_findings,
        }
        
        # 附加未知模式发现
        if discovery:
            try:
                from engine.unknown_pattern_detector import route_to_zhige as _r2z
            except ImportError:
                _r2z = lambda p: {"id": p.id, "routed": False}
            result["unknown_patterns"] = {
                "total_discovered": len(discovery.unknown_patterns),
                "evolution_potential": discovery.evolution_potential,
                "coverage": discovery.known_coverage,
                "patterns": [
                    {
                        "id": p.id, "name": p.name, "dimension": p.dimension,
                        "significance": p.statistical_significance,
                        "why_unknown": p.why_unknown, "best_guess": p.best_guess,
                        "status": p.status,
                    }
                    for p in discovery.unknown_patterns[:10]
                ],
                "routing_to_zhige": [
                    _r2z(p) for p in discovery.unknown_patterns[:3]
                ],
                "message": f"发现{len(discovery.unknown_patterns)}个未知模式，已路由到智哥进行分析" if discovery.unknown_patterns else "系统认知边界内未发现未知模式"
            }
        
        return result


# 便捷入口
def create_agent(db_session=None) -> TaxAuditAgent:
    return TaxAuditAgent(db_session)



# ═══════ [合并自 engine/event_bus.py] ═══════
"""
税务AGI 事件总线 —— 模块间实时通信中枢

设计原则：
  - 发布者不知道谁在订阅，订阅者不知道谁在发布
  - 同步/异步双模式
  - 事件持久化到知识库，供因果网络和元认知回溯
  - 模块间反馈闭环：因果网络→假设生成器→风险预测→巡逻

使用：
  from engine.event_bus import bus
  bus.subscribe("causal_edge_discovered", on_new_causal_edge)
  bus.publish("causal_edge_discovered", {"signals": [...], "finding": "..."})
"""
import json, os, time, threading
from datetime import datetime
from typing import Callable, Dict, List, Any
from collections import defaultdict


class EventBus:
    """全局事件总线 —— 税务AGI的神经系统"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._event_log: List[Dict] = []  # 持久化事件日志
        self._lock = threading.Lock()
        self._max_log = 500
        self._persist_path = None
    
    def subscribe(self, event_type: str, callback: Callable):
        """订阅事件类型。callback(event_data) 在事件发生时被调用"""
        with self._lock:
            self._subscribers[event_type].append(callback)
    
    def publish(self, event_type: str, data: Dict[str, Any], source: str = ""):
        """发布事件。通知所有订阅者，记录事件日志"""
        event = {
            "type": event_type,
            "data": data,
            "source": source,
            "timestamp": datetime.now().isoformat(),
            "id": f"evt_{len(self._event_log):06d}",
        }
        with self._lock:
            self._event_log.append(event)
            if len(self._event_log) > self._max_log:
                self._event_log = self._event_log[-self._max_log:]
        
        # 通知订阅者（在锁外执行，避免死锁）
        subs = list(self._subscribers.get(event_type, []))
        for cb in subs:
            try:
                cb(data)
            except Exception as e:
                pass  # 一个订阅者报错不影响其他
    
    def get_recent_events(self, event_type: str = None, limit: int = 50) -> List[Dict]:
        """获取最近的事件"""
        events = self._event_log
        if event_type:
            events = [e for e in events if e["type"] == event_type]
        return events[-limit:]
    
    def get_cross_module_chains(self) -> List[Dict]:
        """提取跨模块因果链：事件A（来自模块X）→ 事件B（来自模块Y）→ ..."""
        chains = []
        recent = self._event_log[-100:]
        # 按时间窗口(60秒)分组事件，在同一窗口内的不同模块事件形成链
        if len(recent) < 2:
            return chains
        window = 60
        i = 0
        while i < len(recent):
            chain = [recent[i]]
            base_ts = datetime.fromisoformat(recent[i]["timestamp"])
            j = i + 1
            while j < len(recent):
                ts_j = datetime.fromisoformat(recent[j]["timestamp"])
                if (ts_j - base_ts).total_seconds() <= window and recent[j]["source"] != chain[-1]["source"]:
                    chain.append(recent[j])
                else:
                    break
                j += 1
            if len(chain) >= 3:
                chains.append({
                    "events": [{"type": c["type"], "source": c["source"]} for c in chain],
                    "span": (datetime.fromisoformat(chain[-1]["timestamp"]) - base_ts).total_seconds(),
                })
            i = j if j > i + 1 else i + 1
        return chains
    
    def persist_log(self, filepath: str = None):
        """持久化事件日志"""
        if filepath:
            self._persist_path = filepath
        if not self._persist_path:
            self._persist_path = os.path.join(os.path.dirname(__file__), "..", "static", "event_log.json")
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump({
                    "updated_at": datetime.now().isoformat(),
                    "total_events": len(self._event_log),
                    "events": self._event_log[-200:],
                }, f, ensure_ascii=False, indent=2, default=str)
        except:
            pass
    
    def get_summary(self) -> Dict:
        """获取总线概况"""
        with self._lock:
            types = Counter(e["type"] for e in self._event_log)
            sources = Counter(e["source"] for e in self._event_log)
            return {
                "total_events": len(self._event_log),
                "active_subscribers": sum(len(v) for v in self._subscribers.values()),
                "event_types": list(self._subscribers.keys()),
                "top_event_types": types.most_common(10),
                "top_sources": sources.most_common(10),
                "cross_module_chains": len(self.get_cross_module_chains()),
            }


# ── 全局单例 ──
bus = EventBus()


# ── 预定义事件类型 ──
class AGIEvents:
    """税务AGI标准事件类型"""
    # 因果网络
    CAUSAL_EDGE_DISCOVERED = "causal_edge_discovered"
    CAUSAL_PATTERN_FORMED = "causal_pattern_formed"
    
    # 假设生成
    HYPOTHESIS_GENERATED = "hypothesis_generated"
    HYPOTHESIS_CONFIRMED = "hypothesis_confirmed"
    HYPOTHESIS_REFUTED = "hypothesis_refuted"
    
    # 自愈
    SELF_HEALING_RULE_CREATED = "self_healing_rule_created"
    ERROR_DETECTED = "error_detected"
    AUTO_CORRECTION_APPLIED = "auto_correction_applied"
    
    # 巡逻
    PATROL_TRIGGERED = "patrol_triggered"
    PATROL_SIGNIFICANT_CHANGE = "patrol_significant_change"
    
    # 知识库
    KNOWLEDGE_GROWN = "knowledge_grown"
    NEW_SIGNAL_PATTERN = "new_signal_pattern"
    
    # 元认知
    UNCERTAINTY_DETECTED = "uncertainty_detected"
    REASONING_GAP_FOUND = "reasoning_gap_found"
    
    # 分析
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETED = "analysis_completed"
    FINDING_GENERATED = "finding_generated"


# 自动持久化（每100条事件触发一次）
_persist_counter = [0]

def _auto_persist_wrapper(data):
    _persist_counter[0] += 1
    if _persist_counter[0] % 100 == 0:
        bus.persist_log()

bus.subscribe("*", _auto_persist_wrapper)


from collections import Counter



# ═══════ [合并自 engine/knowledge_graph.py] ═══════
"""
税务知识图谱 —— 实体-关系-属性的图结构推理

设计原则：
  - 节点：企业/供应商/客户/人员/发票/法条/风险类型
  - 边：供应/销售/雇佣/关联/引用/触发
  - 支持多跳推理：企业→供应商→关联人员→其他企业
  - 与因果网络互补：因果网络负责"什么导致什么"，知识图谱负责"谁和谁什么关系"

使用：
  from engine.knowledge_graph import kg
  kg.add_entity("enterprise", "广州纺织", {"industry": "纺织业"})
  kg.add_relation("广州纺织", "深圳染整", "委托加工")
  paths = kg.find_paths("广州纺织", "虚开发票风险")
"""
import json, os, heapq
from datetime import datetime
from typing import Dict, List, Set, Tuple, Any, Optional
from collections import defaultdict, deque


class KnowledgeGraph:
    """税务领域知识图谱"""
    
    def __init__(self):
        self._entities: Dict[str, Dict] = {}     # id → {type, props}
        self._relations: List[Dict] = []          # [{from, to, type, props}]
        self._adjacency: Dict[str, List[Tuple[str, str, Dict]]] = defaultdict(list)  # from → [(to, rel_type, props)]
        self._reverse_adj: Dict[str, List[Tuple[str, str, Dict]]] = defaultdict(list)  # to → [(from, rel_type, props)]
        self._index: Dict[str, List[str]] = defaultdict(list)  # keyword → [entity_ids]
    
    # ── 实体管理 ──
    def add_entity(self, etype: str, eid: str, props: Dict = None):
        """添加或更新实体"""
        if eid in self._entities:
            self._entities[eid].update(props or {})
        else:
            self._entities[eid] = {"type": etype, "props": props or {}, "created_at": datetime.now().isoformat()}
        # 建立关键词索引
        for val in [etype, eid] + list((props or {}).values()):
            if isinstance(val, str) and len(val) > 1:
                self._index[val.lower()].append(eid)
    
    def get_entity(self, eid: str) -> Optional[Dict]:
        return self._entities.get(eid)
    
    def find_entities(self, etype: str = None, keyword: str = None) -> List[str]:
        """查找实体"""
        if keyword:
            ids = set(self._index.get(keyword.lower(), []))
        else:
            ids = set(self._entities.keys())
        if etype:
            ids = {eid for eid in ids if self._entities[eid].get("type") == etype}
        return list(ids)
    
    # ── 关系管理 ──
    def add_relation(self, from_id: str, to_id: str, rel_type: str, props: Dict = None):
        """添加关系"""
        rel = {"from": from_id, "to": to_id, "type": rel_type, "props": props or {}, "timestamp": datetime.now().isoformat()}
        self._relations.append(rel)
        self._adjacency[from_id].append((to_id, rel_type, props or {}))
        self._reverse_adj[to_id].append((from_id, rel_type, props or {}))
    
    # ── 图推理 ──
    def get_neighbors(self, eid: str, rel_type: str = None, direction: str = "out") -> List[Tuple[str, str, Dict]]:
        """获取邻居节点"""
        if direction == "out":
            neighbors = self._adjacency.get(eid, [])
        else:
            neighbors = self._reverse_adj.get(eid, [])
        if rel_type:
            neighbors = [(n, t, p) for n, t, p in neighbors if t == rel_type]
        return neighbors
    
    def find_paths(self, from_id: str, to_id: str, max_depth: int = 3) -> List[List[Dict]]:
        """BFS查找两个实体之间的所有路径"""
        if from_id not in self._adjacency:
            return []
        paths = []
        queue = deque([(from_id, [])])
        visited_paths = set()
        
        while queue:
            current, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            for neighbor, rel_type, props in self._adjacency.get(current, []):
                step = {"from": current, "to": neighbor, "type": rel_type}
                new_path = path + [step]
                path_sig = "→".join(s["to"] for s in new_path)
                if path_sig in visited_paths:
                    continue
                visited_paths.add(path_sig)
                if neighbor == to_id:
                    paths.append(new_path)
                elif len(new_path) < max_depth:
                    queue.append((neighbor, new_path))
        return paths
    
    def find_connected_component(self, eid: str, max_depth: int = 3) -> Dict[str, List]:
        """查找实体的关联子图"""
        nodes = set()
        edges = []
        queue = deque([(eid, 0)])
        visited = set()
        
        while queue:
            current, depth = queue.popleft()
            if current in visited or depth > max_depth:
                continue
            visited.add(current)
            nodes.add(current)
            for neighbor, rel_type, props in self._adjacency.get(current, []):
                edges.append({"from": current, "to": neighbor, "type": rel_type})
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))
        
        return {"nodes": list(nodes), "edges": edges}
    
    def detect_cycles(self, eid: str, max_depth: int = 4) -> List[List[Dict]]:
        """检测闭环：企业→供应商→...→企业"""
        cycles = []
        
        def dfs(current, start, path, visited, depth):
            if depth > max_depth:
                return
            for neighbor, rel_type, props in self._adjacency.get(current, []):
                if neighbor == start and len(path) >= 1:
                    cycles.append(path + [{"from": current, "to": neighbor, "type": rel_type}])
                    continue
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                dfs(neighbor, start, path + [{"from": current, "to": neighbor, "type": rel_type}], visited, depth + 1)
                visited.discard(neighbor)
        
        dfs(eid, eid, [], {eid}, 0)
        return cycles
    
    # ── 多跳推理 ──
    def multi_hop_query(self, start_id: str, relation_path: List[str]) -> List[str]:
        """多跳查询：企业→供应→关联人员→控制→其他企业"""
        current = {start_id}
        for rel_type in relation_path:
            next_set = set()
            for eid in current:
                for neighbor, rtype, _ in self._adjacency.get(eid, []):
                    if rtype == rel_type:
                        next_set.add(neighbor)
            current = next_set
            if not current:
                break
        return list(current)
    
    # ── 统计与导入 ──
    def get_stats(self) -> Dict:
        return {
            "total_entities": len(self._entities),
            "total_relations": len(self._relations),
            "entity_types": Counter(e["type"] for e in self._entities.values()),
            "relation_types": Counter(r["type"] for r in self._relations),
            "densest_entities": sorted(self._adjacency.items(), key=lambda x: len(x[1]), reverse=True)[:5],
        }
    
    def import_from_analysis(self, company_name: str, findings: List[Dict], invoices: List[Dict] = None, bank_txs: List[Dict] = None):
        """从分析结果导入知识图谱"""
        # 企业节点
        self.add_entity("enterprise", company_name, {"source": "analysis"})
        
        # 供应商节点（从进项发票）
        if invoices:
            suppliers = set()
            for inv in invoices:
                supplier = inv.get("对方公司名称") or inv.get("seller_name") or inv.get("supplier", "")
                if supplier and supplier != company_name:
                    suppliers.add(supplier)
                    self.add_entity("supplier", supplier, {"source": "invoice"})
                    self.add_relation(company_name, supplier, "采购", {"source": "invoice"})
            
            # 客户节点（从销项发票）
            for inv in invoices:
                buyer = inv.get("对方公司名称") or inv.get("buyer_name") or inv.get("customer", "")
                if buyer and buyer != company_name:
                    self.add_entity("customer", buyer, {"source": "invoice"})
                    self.add_relation(buyer, company_name, "采购", {"source": "invoice"})
        
        # 风险节点
        for f in findings:
            risk_type = f.get("type") or f.get("domain", "")
            if risk_type:
                risk_id = f"risk:{risk_type}"
                self.add_entity("risk", risk_id, {"level": f.get("level", ""), "count": 1})
                self.add_relation(company_name, risk_id, "触发", {"finding_count": 1})
    
    def persist(self, filepath: str = None):
        """持久化到JSON"""
        if not filepath:
            filepath = os.path.join(os.path.dirname(__file__), "..", "static", "knowledge_graph.json")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({
                "entities": {k: {"type": v["type"], "props": v["props"]} for k, v in self._entities.items()},
                "relations": self._relations[-1000:],
                "updated_at": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2, default=str)
    
    def load(self, filepath: str = None):
        """从JSON加载"""
        if not filepath:
            filepath = os.path.join(os.path.dirname(__file__), "..", "static", "knowledge_graph.json")
        if not os.path.exists(filepath):
            return
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        for eid, edata in data.get("entities", {}).items():
            self.add_entity(edata["type"], eid, edata.get("props", {}))
        for rel in data.get("relations", []):
            self.add_relation(rel["from"], rel["to"], rel["type"], rel.get("props", {}))


# ── 全局单例 ──
kg = KnowledgeGraph()

from collections import Counter



# ═══════ [合并自 engine/metacognition.py] ═══════
"""
元认知引擎 —— 监控系统自身的推理过程

核心能力：
  1. 推理质量自评：每条结论的推理链是否完整？
  2. 不确定性检测：哪条结论系统自己都不确定？
  3. 信息缺口识别：还缺什么数据才能更确定？
  4. 决策建议：基于不确定性，建议获取什么信息

与反思器(agent_core.py SelfReflector)的关系：
  - 反思器：针对每条结论生成反向假设
  - 元认知：站在更高一层看"反思器做得对不对"
"""
import json, os
from datetime import datetime
from typing import List, Dict


class MetacognitionEngine:
    """元认知 —— 对自己的思考进行思考"""
    
    def __init__(self):
        self.reasoning_log: List[Dict] = []
        self.uncertainty_threshold = 0.3
        self.gap_patterns = self._init_gap_patterns()
    
    def _init_gap_patterns(self) -> List[Dict]:
        """信息缺口模式 —— 常见的不确定性来源"""
        return [
            {"pattern": "缺合同", "keywords": ["合同", "协议"], "missing": "购销合同/服务协议", "impact": 0.4},
            {"pattern": "缺物流", "keywords": ["运输", "物流", "快递"], "missing": "运输单据/物流记录", "impact": 0.35},
            {"pattern": "缺凭证", "keywords": ["凭证", "记账"], "missing": "记账凭证", "impact": 0.3},
            {"pattern": "缺银行流水", "keywords": ["银行", "收款", "付款"], "missing": "银行对账单", "impact": 0.5},
            {"pattern": "缺申报表", "keywords": ["申报", "增值税", "所得税"], "missing": "纳税申报表", "impact": 0.45},
            {"pattern": "单源证据", "keywords": ["仅", "只有", "单一"], "missing": "多源交叉验证", "impact": 0.35},
        ]
    
    def evaluate_reasoning_quality(self, finding: Dict) -> Dict:
        """评估单条结论的推理质量"""
        scores = {}
        issues = []
        
        # 1. 因果链完整性
        how_found = finding.get("how_found") or finding.get("description", "")
        if len(how_found) < 20:
            scores["causal_completeness"] = 0.2
            issues.append("发现过程描述过于简短，缺乏调查步骤")
        elif "经查" in how_found or "核查" in how_found or "比对" in how_found:
            scores["causal_completeness"] = 0.8
        else:
            scores["causal_completeness"] = 0.5
        
        # 2. 证据充分性
        evidence = finding.get("evidence") or finding.get("items", [])
        if isinstance(evidence, list) and len(evidence) >= 2:
            scores["evidence_sufficiency"] = 0.9
        elif isinstance(evidence, list) and len(evidence) == 1:
            scores["evidence_sufficiency"] = 0.5
            issues.append("仅单一证据源，建议增加交叉验证")
        else:
            scores["evidence_sufficiency"] = 0.3
            issues.append("缺少具体证据明细")
        
        # 3. 法律依据
        policy = finding.get("policy_ref", "")
        if "第" in str(policy) and "条" in str(policy):
            scores["legal_grounding"] = 0.9
        elif len(str(policy)) > 10:
            scores["legal_grounding"] = 0.6
        else:
            scores["legal_grounding"] = 0.2
            issues.append("缺少具体法律条款引用")
        
        # 4. 建议可操作性
        suggestion = finding.get("suggestion", "")
        if "①" in suggestion or "1." in suggestion:
            scores["actionability"] = 0.9
        elif len(suggestion) > 30:
            scores["actionability"] = 0.6
        else:
            scores["actionability"] = 0.3
            issues.append("行动建议过于笼统")
        
        # 综合质量分
        quality = sum(scores.values()) / max(len(scores), 1)
        
        return {
            "finding_type": finding.get("type", ""),
            "quality_score": round(quality, 3),
            "dimension_scores": scores,
            "issues": issues,
            "verdict": "优秀" if quality >= 0.8 else ("良好" if quality >= 0.6 else ("一般" if quality >= 0.4 else "需改进")),
        }
    
    def detect_uncertainty(self, findings: List[Dict]) -> List[Dict]:
        """检测哪些结论系统自己不确定"""
        uncertain = []
        for f in findings:
            q = self.evaluate_reasoning_quality(f)
            if q["quality_score"] < self.uncertainty_threshold + 0.3:
                uncertain.append({
                    "finding_type": q["finding_type"],
                    "quality_score": q["quality_score"],
                    "issues": q["issues"],
                    "suggestion": "建议获取更多信息以确认该结论",
                })
        return uncertain
    
    def identify_information_gaps(self, findings: List[Dict]) -> List[Dict]:
        """识别信息缺口 —— 为了更确定还需要什么数据"""
        gaps = []
        all_text = " ".join([
            str(f.get("how_found", "")) + str(f.get("description", "")) + str(f.get("detail", ""))
            for f in findings
        ]).lower()
        
        for pattern in self.gap_patterns:
            if any(kw in all_text for kw in pattern["keywords"]):
                gaps.append({
                    "gap_type": pattern["pattern"],
                    "missing_info": pattern["missing"],
                    "impact_on_confidence": pattern["impact"],
                    "suggestion": f"获取{pattern['missing']}可提升结论置信度约{int(pattern['impact']*100)}%",
                })
        
        return gaps
    
    def metacognitive_report(self, findings: List[Dict], agent_result: Dict = None) -> Dict:
        """生成元认知报告"""
        # 逐一评估
        quality_evaluations = [self.evaluate_reasoning_quality(f) for f in findings]
        
        # 统计
        avg_quality = sum(q["quality_score"] for q in quality_evaluations) / max(len(quality_evaluations), 1)
        good_count = sum(1 for q in quality_evaluations if q["verdict"] in ("优秀", "良好"))
        weak_count = sum(1 for q in quality_evaluations if q["verdict"] in ("一般", "需改进"))
        
        # 不确定性检测
        uncertain = self.detect_uncertainty(findings)
        
        # 信息缺口
        gaps = self.identify_information_gaps(findings)
        
        # 自我反思质量
        reflection_quality = "优秀" if avg_quality >= 0.7 else ("良好" if avg_quality >= 0.5 else "需改进")
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "overall_quality": round(avg_quality, 3),
            "quality_verdict": reflection_quality,
            "distribution": {"优秀+良好": good_count, "一般+需改进": weak_count},
            "uncertain_findings": uncertain[:5],
            "information_gaps": gaps,
            "action_items": [],
        }
        
        # 生成行动建议
        if avg_quality < 0.5:
            report["action_items"].append("整体推理质量偏低，建议补充更多原始资料后重新分析")
        if len(uncertain) > len(findings) * 0.3:
            report["action_items"].append(f"超过30%的结论存在不确定性({len(uncertain)}/{len(findings)})，建议人工复核")
        if len(gaps) >= 3:
            report["action_items"].append(f"发现{len(gaps)}个信息缺口，补充后可显著提升分析质量")
        
        # 记录推理日志，持久化用于跨运行比较
        self.reasoning_log.append({
            "timestamp": report["timestamp"],
            "avg_quality": avg_quality,
            "findings_count": len(findings),
            "issues": sum(len(q["issues"]) for q in quality_evaluations),
        })
        self._persist_log()
        
        # ═══ 自知增强：六维能力自评分 ═══
        report["agi_capability_scores"] = self._score_capabilities(findings, avg_quality)
        report["vs_baseline"] = self._compare_to_baseline(avg_quality, len(findings))
        report["anomalies"] = self._detect_anomalies(quality_evaluations)
        
        return report
    
    def _score_capabilities(self, findings, avg_quality):
        """六维能力自评分（自知层核心）"""
        has_correction_rules = os.path.exists(
            os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "user_corrections.json"))
        has_memory = len(self.reasoning_log) > 1
        total_findings = len(findings)
        high_risk = sum(1 for f in findings if f.get("level") in ("高风险","极高风险"))
        has_evidence = sum(1 for f in findings if f.get("items") or f.get("evidence"))
        has_law = sum(1 for f in findings if "第" in str(f.get("policy_ref","")) and "条" in str(f.get("policy_ref","")))
        
        return {
            "记忆": min(0.95, 0.6 + 0.15 * has_memory + 0.1 * min(total_findings/50, 1)),
            "学习": min(0.95, 0.5 + 0.3 * has_correction_rules + 0.15 * min(len(self.reasoning_log)/5, 1)),
            "思考": min(0.95, 0.5 + 0.2 * min(has_evidence/total_findings, 1) if total_findings else 0.5),
            "判断": min(0.95, 0.6 + 0.2 * min(has_law/total_findings, 1) + 0.1 * avg_quality),
            "决策": min(0.95, 0.5 + 0.25 * min(high_risk/5, 1) + 0.2 * avg_quality),
            "自知": min(0.95, 0.4 + 0.3 * has_memory + 0.15 * avg_quality),
        }
    
    def _compare_to_baseline(self, current_quality, current_count):
        """与历史基线比较（自知的核心：我知道自己进步了还是退步了）"""
        if len(self.reasoning_log) < 2:
            return {"status": "baseline", "message": "首轮分析，无历史基线可对比"}
        
        prev = [r for r in self.reasoning_log[:-1]]
        avg_prev_quality = sum(r["avg_quality"] for r in prev) / len(prev)
        avg_prev_count = sum(r["findings_count"] for r in prev) / len(prev)
        
        q_change = current_quality - avg_prev_quality
        c_change = current_count - avg_prev_count
        
        status = "improving" if q_change > 0.05 else ("declining" if q_change < -0.05 else "stable")
        return {
            "status": status,
            "current_quality": round(current_quality, 3),
            "baseline_quality": round(avg_prev_quality, 3),
            "quality_delta": round(q_change, 3),
            "finding_count_delta": int(c_change),
            "total_runs": len(self.reasoning_log),
            "message": f"推理质量{'提升' if status=='improving' else ('下降' if status=='declining' else '稳定')}（当前{current_quality:.2f} vs 基线{avg_prev_quality:.2f}）"
        }
    
    def _detect_anomalies(self, quality_evaluations):
        """检测异常：突然出现大量低质量结论"""
        anomalies = []
        very_low = [q for q in quality_evaluations if q["quality_score"] < 0.2]
        if len(very_low) > 3:
            anomalies.append(f"检测到{len(very_low)}条极低质量结论（<0.2），可能数据源存在问题")
        
        # 检查评分方差（过高方差=不稳定）
        scores = [q["quality_score"] for q in quality_evaluations]
        if len(scores) > 5:
            avg = sum(scores) / len(scores)
            variance = sum((s - avg) ** 2 for s in scores) / len(scores)
            if variance > 0.15:
                anomalies.append(f"结论质量方差过大（{variance:.3f}），引擎输出不够稳定")
        
        return anomalies
    
    def _persist_log(self):
        """持久化推理日志，跨运行保留"""
        try:
            log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "metacognition_log.json")
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(self.reasoning_log[-20:], f, ensure_ascii=False, indent=2)
        except:
            pass


# ── 全局单例 ──
metacog = MetacognitionEngine()


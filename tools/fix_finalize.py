import re

with open("agi_pipeline.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find the old finalize_learning method
old_start = '    # ─── 汇总 → 知识库持久化 ───\n    \n    def finalize_learning(self, analysis_trace_id: str, company_name: str = "", \n                          industry: str = "") -> Dict:'
old_end = '\n\n\n# 便捷入口'

idx_start = content.find(old_start)
if idx_start < 0:
    print("ERROR: 未找到 finalize_learning 开始位置")
    # Try to find with different whitespace
    idx = content.find("def finalize_learning")
    if idx >= 0:
        print(f"找到 finalize_learning at {idx}")
        print(repr(content[idx:idx+300]))
    exit(1)

idx_end = content.find(old_end, idx_start)
if idx_end < 0:
    print("ERROR: 未找到 finalize_learning 结束位置")
    exit(1)

print(f"找到 finalize_learning: {idx_start} ~ {idx_end}")

# New implementation
new_impl = '''
    # ─── 汇总 → 知识库持久化 ───
    
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
            if event.module == "①税务合规指令" and event.event_type == "rule_triggered":
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
        
        # 模块覆盖度报告
        module_coverage = Counter()
        for e in self.events:
            module_coverage[e.module] += 1
        
        return {
            "events_collected": self.stats["events_collected"],
            "modules_covered": len(module_coverage),
            "module_breakdown": dict(module_coverage.most_common()),
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
'''

# Replace
content_new = content[:idx_start] + new_impl + content[idx_end:]

with open("agi_pipeline.py", "w", encoding="utf-8") as f:
    f.write(content_new)

print("OK: finalize_learning() 已替换")
print(f"旧长度: {idx_end - idx_start}, 新长度: {len(new_impl)}")

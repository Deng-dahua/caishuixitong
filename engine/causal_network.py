"""
多信号条件概率网络 —— 自主调查决策引擎

核心理念：系统不是被动等程序员写规则，而是从历史分析数据中自己学。
"我看到这4个信号同时出现3次，每次都导致虚开进项的结论 → 下次自动生成假设"

架构：
  1. 信号收集器 — 从历史分析+反馈+记忆中提取信号对
  2. 共现矩阵 — N×N信号共现频率矩阵
  3. 因果边发现 — P(结果|信号组合) > 阈值 → 新边
  4. 多信号模式挖掘 — 2/3/4信号组合的联合预测力
  5. 自动规则生成 — 高置信度模式 → 可执行调查规则
"""
import json, os, time, math
from datetime import datetime
from collections import defaultdict, Counter
from itertools import combinations
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict

# ==================== 信号定义 ====================

# 系统可检测的信号全集
PRIMARY_SIGNALS = [
    # 银行流水信号
    ("bank_income_excess", "银行收款超额", lambda ctx: ctx.get("bank_in_ratio", 1) > 1.2),
    ("bank_outgo_deficit", "银行付款不足", lambda ctx: ctx.get("bank_out_ratio", 1) < 0.8),
    ("personal_transfers", "个人账户大量转账", lambda ctx: ctx.get("has_personal_payments", False)),
    ("round_number_tx", "大额整数交易", lambda ctx: ctx.get("round_trip_detected", False)),
    ("structured_transfers", "结构化资金转移", lambda ctx: ctx.get("structured_transfers", False)),
    
    # 进项发票信号
    ("supplier_concentration", "供应商高度集中", lambda ctx: ctx.get("supplier_concentration", 0) > 0.6),
    ("supplier_same_city", "供应商同城扎堆", lambda ctx: ctx.get("supplier_same_city_ratio", 0) > 0.5),
    ("processing_fee_exists", "存在加工费发票", lambda ctx: ctx.get("has_processing_fee", False)),
    ("pur_without_payment", "进项发票无付款", lambda ctx: ctx.get("pur_without_payment_ratio", 0) > 0.3),
    ("phantom_suppliers", "幽灵供应商", lambda ctx: ctx.get("phantom_suppliers", False)),
    ("price_volatility", "同品名价格波动大", lambda ctx: ctx.get("price_volatility", False)),
    ("quantity_spike", "数量异常突变", lambda ctx: ctx.get("quantity_spike", False)),
    
    # 销项发票信号
    ("customer_concentration", "客户高度集中", lambda ctx: ctx.get("customer_concentration", 0) > 0.6),
    ("sal_without_bank", "已开票无银行收款", lambda ctx: ctx.get("sal_without_bank_ratio", 0) > 0.2),
    ("goods_mismatch", "进销品名不匹配", lambda ctx: ctx.get("goods_mismatch_ratio", 0) > 0.3),
    ("revenue_smoothing", "收入人为平滑", lambda ctx: ctx.get("revenue_smoothing", False)),
    ("off_hours_invoice", "非营业时间开票", lambda ctx: ctx.get("off_hours_invoice", False)),
    
    # 财务报表信号
    ("profit_cash_gap", "利润现金流背离", lambda ctx: ctx.get("profit_cash_gap", False)),
    ("ar_ap_anomaly", "往来科目异常", lambda ctx: ctx.get("ar_ap_anomaly", False)),
    ("low_data_quality", "资料完整度低", lambda ctx: ctx.get("data_quality_score", 100) < 40),
    ("near_micro_limit", "接近小微门槛", lambda ctx: ctx.get("near_micro_limit", False)),
    
    # 关联关系信号
    ("related_parties", "存在关联方", lambda ctx: ctx.get("has_related_parties", False)),
    ("personnel_overlap", "六员跨企业重叠", lambda ctx: ctx.get("has_six_personnel_overlap", False)),
    ("supplier_is_customer", "供应商即客户", lambda ctx: ctx.get("supplier_is_customer", False)),
]

# 信号→结论名称映射（用于构建因果边）
FINDING_TYPES = [
    "隐匿销售收入",
    "虚开进项发票", 
    "委托加工真实性存疑",
    "关联交易转移利润",
    "虚列成本费用",
    "进销品名不匹配",
    "会计账簿不健全",
    "小型微利资格不符",
    "发票群集性虚开",
    "资金回流",
    "收入人为平滑",
    "供应商空壳风险",
]

# ==================== 数据类 ====================

@dataclass
class CausalEdge:
    """因果边：信号A → 结论B"""
    source_signals: List[str]  # 触发信号组合
    target_finding: str        # 导致的结论
    co_occurrence_count: int   # 共现次数
    total_source_occurrences: int  # 信号出现总次数
    conditional_probability: float  # P(结论|信号)
    lift: float                # 提升度 = P(结论|信号) / P(结论)
    confidence: float          # 综合置信度
    first_seen: str            # 首次发现时间
    last_seen: str             # 最近出现时间
    companies: List[str] = field(default_factory=list)

@dataclass
class MultiSignalPattern:
    """多信号组合模式"""
    signals: List[str]         # 信号组合
    signal_count: int          # 信号数量
    target_finding: str        # 预测的结论
    joint_probability: float   # 联合概率 P(结论|所有信号)
    occurrence_count: int      # 该组合出现次数
    finding_occurrence: int    # 该组合下结论出现次数
    distinctiveness: float     # 该组合相对于单信号的独特性
    auto_rule_ready: bool      # 是否可以自动生成规则

# ==================== 核心引擎 ====================

class CausalNetwork:
    """多信号条件概率因果网络"""
    
    def __init__(self, data_path=None):
        self.edges: List[CausalEdge] = []
        self.patterns: List[MultiSignalPattern] = []
        self.signal_frequencies: Dict[str, int] = Counter()
        self.finding_frequencies: Dict[str, int] = Counter()
        self.cooccurrence_matrix: Dict[Tuple, int] = Counter()
        
        if data_path:
            self.load_data(data_path)
    
    def load_data(self, data_path: str = None):
        """从跨分析记忆加载历史数据"""
        if data_path is None:
            base = os.path.dirname(os.path.dirname(__file__))
            data_path = os.path.join(base, "static", "cross_analysis_memory.json")
        
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                memory = json.load(f)
        except:
            memory = {"analyses": [], "industry_patterns": {}, "lesson_learned": []}
        
        self._memory = memory
        return self
    
    def collect_signals(self, context_history: List[Dict] = None) -> Dict[str, Set[str]]:
        """从历史分析中收集信号→结论对
        
        返回: {analysis_trace_id: {signals: [...], findings: [...]}}
        """
        signal_finding_pairs = {}
        
        # 从memory加载
        for analysis in self._memory.get("analyses", []):
            trace_id = analysis.get("trace_id", "")
            data_profile = analysis.get("data_profile", {})
            
            # 激活信号检测
            active_signals = []
            for sig_id, sig_name, detector in PRIMARY_SIGNALS:
                try:
                    if detector(data_profile):
                        active_signals.append(sig_name)
                except:
                    pass
            
            learnings = analysis.get("learning_points", [])
            
            if active_signals and learnings:
                signal_finding_pairs[trace_id] = {
                    "signals": active_signals,
                    "findings": learnings,
                    "industry": analysis.get("industry", ""),
                }
        
        # 如果有额外的context_history，合并
        if context_history:
            for ctx in context_history:
                trace_id = ctx.get("trace_id", str(time.time()))
                active_signals = []
                for sig_id, sig_name, detector in PRIMARY_SIGNALS:
                    try:
                        if detector(ctx):
                            active_signals.append(sig_name)
                    except:
                        pass
                findings = [f.get("type", "") for f in ctx.get("findings", [])]
                if active_signals and findings:
                    signal_finding_pairs[trace_id] = {
                        "signals": active_signals,
                        "findings": findings,
                    }
        
        return signal_finding_pairs
    
    def build_cooccurrence_matrix(self, signal_finding_pairs: Dict):
        """构建信号×结论 共现矩阵"""
        # 计数
        for trace_id, pair in signal_finding_pairs.items():
            signals = pair["signals"]
            findings = pair["findings"]
            
            for sig in signals:
                self.signal_frequencies[sig] += 1
                for finding in findings:
                    key = (sig, finding)
                    self.cooccurrence_matrix[key] += 1
            
            for finding in findings:
                self.finding_frequencies[finding] += 1
    
    def discover_causal_edges(self, min_occurrence=2, min_confidence=0.5) -> List[CausalEdge]:
        """发现因果边：P(结论|信号) > 阈值
        
        如果P(隐匿收入|银行收款超额)很高，并且提升度也高 → 因果边成立
        """
        total_analyses = len(self._memory.get("analyses", []))
        if total_analyses < 2:
            return []
        
        edges = []
        
        for (signal, finding), co_count in self.cooccurrence_matrix.items():
            sig_count = self.signal_frequencies.get(signal, 0)
            finding_count = self.finding_frequencies.get(finding, 0)
            
            if sig_count < min_occurrence or co_count < min_occurrence:
                continue
            
            # P(结论|信号)
            cond_prob = co_count / sig_count if sig_count > 0 else 0
            
            # P(结论) — 基线概率
            base_prob = finding_count / total_analyses if total_analyses > 0 else 0
            
            # 提升度 = P(结论|信号) / P(结论)
            lift = cond_prob / base_prob if base_prob > 0 else 0
            
            # 综合置信度 = cond_prob * log2(lift+1) / log2(2)
            confidence = cond_prob * (math.log2(lift + 1) / math.log2(2)) if lift > 0 else 0
            
            if cond_prob >= min_confidence and lift > 1.2:
                edge = CausalEdge(
                    source_signals=[signal],
                    target_finding=finding,
                    co_occurrence_count=co_count,
                    total_source_occurrences=sig_count,
                    conditional_probability=round(cond_prob, 3),
                    lift=round(lift, 2),
                    confidence=round(confidence, 3),
                    first_seen=datetime.now().isoformat(),
                    last_seen=datetime.now().isoformat(),
                )
                edges.append(edge)
        
        # 按置信度排序
        edges.sort(key=lambda e: e.confidence, reverse=True)
        self.edges = edges
        return edges
    
    def mine_multi_signal_patterns(self, signal_finding_pairs: Dict, 
                                    max_signal_combo: int = 4) -> List[MultiSignalPattern]:
        """挖掘多信号组合模式
        
        不只找单信号→结论的关系，还找信号组合的联合预测力。
        "银行收款超额"单独可能不确定，但"银行收款超额+供应商集中+无运输发票"三信号组合→几乎确定是虚开
        """
        patterns = []
        total = len(signal_finding_pairs)
        
        for combo_size in range(2, max_signal_combo + 1):
            for trace_id, pair in signal_finding_pairs.items():
                signals = pair["signals"]
                findings = pair["findings"]
                
                if len(signals) < combo_size:
                    continue
                
                for signal_combo in combinations(signals, combo_size):
                    signal_combo = tuple(sorted(signal_combo))
                    
                    # 统计该信号组合在所有分析中的出现
                    combo_occurrences = 0
                    combo_finding_occurrences = Counter()
                    
                    for tid2, pair2 in signal_finding_pairs.items():
                        sigs2 = pair2["signals"]
                        if all(s in sigs2 for s in signal_combo):
                            combo_occurrences += 1
                            for f in pair2["findings"]:
                                combo_finding_occurrences[f] += 1
                    
                    if combo_occurrences < 2:
                        continue
                    
                    # 对每个结论计算联合概率
                    for finding, count in combo_finding_occurrences.most_common(3):
                        joint_prob = count / combo_occurrences if combo_occurrences > 0 else 0
                        
                        # 独特性：多信号组合比单信号好多少？
                        single_best = max(
                            self.cooccurrence_matrix.get((s, finding), 0) / max(self.signal_frequencies.get(s, 1), 1)
                            for s in signal_combo
                        )
                        distinctiveness = joint_prob - single_best if single_best else 0
                        
                        if joint_prob > 0.6 and distinctiveness > 0.1:
                            pattern = MultiSignalPattern(
                                signals=list(signal_combo),
                                signal_count=combo_size,
                                target_finding=finding,
                                joint_probability=round(joint_prob, 3),
                                occurrence_count=combo_occurrences,
                                finding_occurrence=count,
                                distinctiveness=round(distinctiveness, 3),
                                auto_rule_ready=joint_prob > 0.75 and combo_occurrences >= 3,
                            )
                            patterns.append(pattern)
        
        # 去重 + 排序
        seen = set()
        unique_patterns = []
        for p in sorted(patterns, key=lambda x: (x.joint_probability, x.distinctiveness), reverse=True):
            key = (tuple(p.signals), p.target_finding)
            if key not in seen:
                seen.add(key)
                unique_patterns.append(p)
        
        self.patterns = unique_patterns[:50]
        return self.patterns
    
    def generate_auto_rules(self) -> List[Dict]:
        """从发现的多信号模式和高置信度因果边自动生成调查规则"""
        rules = []
        
        # 从多信号模式生成规则
        for pattern in self.patterns:
            if not pattern.auto_rule_ready:
                continue
            
            rule = {
                "source": "causal_network",
                "rule_name": f"[因果发现] {', '.join(pattern.signals[:3])} → {pattern.target_finding}",
                "trigger_signals": pattern.signals,
                "target_finding": pattern.target_finding,
                "confidence": pattern.joint_probability,
                "evidence_count": pattern.occurrence_count,
                "investigation_priority": "高风险" if pattern.joint_probability > 0.85 else "中风险",
                "investigation_steps": [
                    f"检测到{len(pattern.signals)}个共现信号",
                    f"历史{pattern.occurrence_count}次相同模式中有{pattern.finding_occurrence}次导致{pattern.target_finding}",
                    f"联合概率 {pattern.joint_probability:.0%} → 强烈建议深入调查",
                ],
            }
            rules.append(rule)
        
        # 从高置信度因果边生成规则
        for edge in self.edges:
            if edge.confidence >= 0.8 and edge.co_occurrence_count >= 3:
                rule = {
                    "source": "causal_edge",
                    "rule_name": f"[因果边] {edge.source_signals[0]} → {edge.target_finding}",
                    "trigger_signals": edge.source_signals,
                    "target_finding": edge.target_finding,
                    "confidence": edge.confidence,
                    "evidence_count": edge.co_occurrence_count,
                    "prob": edge.conditional_probability,
                    "lift": edge.lift,
                }
                rules.append(rule)
        
        return rules
    
    def run_full_discovery(self, context_history: List[Dict] = None) -> Dict:
        """运行完整的因果发现流程"""
        # Step 1: 收集信号
        pairs = self.collect_signals(context_history)
        
        # Step 2: 构建共现矩阵
        self.build_cooccurrence_matrix(pairs)
        
        # Step 3: 发现因果边
        edges = self.discover_causal_edges()
        
        # Step 4: 挖掘多信号模式
        patterns = self.mine_multi_signal_patterns(pairs)
        
        # Step 5: 自动生成规则
        rules = self.generate_auto_rules()
        
        return {
            "total_analyses_processed": len(pairs),
            "causal_edges_discovered": len(edges),
            "multi_signal_patterns": len(patterns),
            "auto_rules_generated": len(rules),
            "top_edges": [
                {
                    "signals": e.source_signals,
                    "finding": e.target_finding,
                    "prob": e.conditional_probability,
                    "lift": e.lift,
                    "count": e.co_occurrence_count,
                }
                for e in edges[:10]
            ],
            "top_patterns": [
                {
                    "signals": p.signals,
                    "finding": p.target_finding,
                    "joint_prob": p.joint_probability,
                    "signals_count": p.signal_count,
                    "auto_ready": p.auto_rule_ready,
                }
                for p in patterns[:10]
            ],
            "rules_generated": rules[:10],
        }
    
    def predict_hypotheses(self, active_signals: List[str], min_confidence: float = 0.5) -> List[Dict]:
        """给定当前活跃信号，预测可能的结论（自主调查决策）
        
        这是核心推理机制：系统看到当前数据中的信号 → 查因果网络 → 输出"你应该调查这些方向"
        """
        predictions = []
        
        # 1. 单信号预测（因果边）
        for signal in active_signals:
            for edge in self.edges:
                if signal in edge.source_signals and edge.confidence >= min_confidence:
                    predictions.append({
                        "type": "single_signal",
                        "trigger": signal,
                        "finding": edge.target_finding,
                        "confidence": edge.confidence,
                        "evidence": f"历史{edge.co_occurrence_count}/{edge.total_source_occurrences}次 = {edge.conditional_probability:.0%}",
                    })
        
        # 2. 多信号组合预测
        for pattern in self.patterns:
            if all(s in active_signals for s in pattern.signals):
                predictions.append({
                    "type": "multi_signal",
                    "trigger": " + ".join(pattern.signals[:3]),
                    "finding": pattern.target_finding,
                    "confidence": pattern.joint_probability,
                    "signal_count": pattern.signal_count,
                    "auto_rule": pattern.auto_rule_ready,
                })
        
        # 去重（多信号优先）→ 按置信度排序
        seen = set()
        unique = []
        for p in sorted(predictions, key=lambda x: (x["type"] != "multi_signal", -x["confidence"])):
            key = (p["finding"],)
            if key not in seen:
                seen.add(key)
                unique.append(p)
        
        return unique[:10]


# ==================== 集成到智能体 ====================

class AutonomousReasoner:
    """自主推理器 —— 替换手工模板，让系统自己学因果关系"""
    
    def __init__(self):
        self.network = CausalNetwork()
        self.network.load_data()
    
    def learn_from_history(self) -> Dict:
        """从所有历史分析中学习"""
        return self.network.run_full_discovery()
    
    def reason(self, context: Dict, existing_findings: List[Dict] = None) -> Dict:
        """基于当前数据和历史学习结果进行自主推理"""
        
        # 检测当前数据中的活跃信号
        active_signals = []
        for sig_id, sig_name, detector in PRIMARY_SIGNALS:
            try:
                if detector(context):
                    active_signals.append(sig_name)
            except:
                pass
        
        # 用因果网络预测
        predictions = self.network.predict_hypotheses(active_signals, min_confidence=0.4)
        
        # 发现当前数据中网络不认识的信号组合 → 标记为未知
        unknown_combos = []
        for size in range(2, min(5, len(active_signals) + 1)):
            for combo in combinations(active_signals, size):
                combo_key = tuple(sorted(combo))
                known = any(
                    set(combo) == set(p.signals) 
                    for p in self.network.patterns
                )
                if not known:
                    unknown_combos.append({
                        "signals": list(combo),
                        "size": size,
                        "status": "未见过的信号组合",
                        "investigation_needed": size >= 3,  # 3+信号组合未知→需要调查
                    })
        
        return {
            "active_signals": active_signals,
            "predictions": predictions,
            "unknown_signal_combos": unknown_combos[:5],
            "network_state": {
                "total_edges": len(self.network.edges),
                "total_patterns": len(self.network.patterns),
            },
        }
    
    def train_and_update(self, context_history: List[Dict] = None):
        """训练网络并更新——每次分析后调用"""
        result = self.network.run_full_discovery(context_history)
        
        # 自动注入规则到自愈引擎
        if result["auto_rules_generated"] > 0:
            self._inject_discovered_rules(result["rules_generated"])
        
        return result
    
    def _inject_discovered_rules(self, rules: List[Dict]):
        """将因果网络发现的规则注入到系统中"""
        try:
            base = os.path.dirname(os.path.dirname(__file__))
            rules_path = os.path.join(base, "static", "discovered_rules.json")
            
            existing = []
            try:
                with open(rules_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except:
                pass
            
            # 去重后追加
            existing_names = {r.get("rule_name", "") for r in existing}
            new_count = 0
            for rule in rules:
                if rule.get("rule_name") not in existing_names:
                    existing.append(rule)
                    new_count += 1
            
            if new_count > 0:
                os.makedirs(os.path.dirname(rules_path), exist_ok=True)
                with open(rules_path, "w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def get_signal_hash(self, context: Dict) -> str:
        """生成当前数据上下文的信号指纹"""
        active = []
        for sig_id, sig_name, detector in PRIMARY_SIGNALS:
            try:
                if detector(context):
                    active.append(sig_id)
            except:
                pass
        return "|".join(sorted(active))


# 便捷入口
def create_autonomous_reasoner() -> AutonomousReasoner:
    return AutonomousReasoner()

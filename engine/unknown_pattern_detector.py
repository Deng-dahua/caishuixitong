"""
未知模式检测器 —— 系统认知边界探测器

核心使命：当数据中出现现有知识体系无法解释的模式时，自动捕获并路由到智哥介入。

工作原理：
  1. 已知规则覆盖度检查 — 每个数据维度是否有对应的规则/假设覆盖
  2. 残差显著性评分 — 未被覆盖但统计显著的数据模式
  3. 模式聚类 — 将未知信号聚合为可分析的模式单元
  4. 智能路由 — 自动排队等待智哥分析→生成新规则→注入系统

这是系统从"规则引擎"进化到"自进化的智能体"的关键一步。
"""
import json, os, time, re
from datetime import datetime
from collections import defaultdict, Counter
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
import uuid

# ==================== 数据类 ====================

@dataclass
class UnknownPattern:
    """系统无法解释的数据模式"""
    id: str
    name: str                         # 模式名称（由系统自动生成）
    dimension: str                    # 所属分析维度
    data_snapshot: Dict               # 触发该模式的数据快照
    statistical_significance: float   # 统计显著性 0-1
    why_unknown: str                  # 为什么系统不理解（无匹配规则/超出阈值/新数据形态）
    best_guess: str                   # 系统的最佳猜测（基于最近邻模式）
    suggested_investigation: List[str] # 建议的调查方向
    similar_known_patterns: List[str] # 最相似的已知模式
    company_id: int = 0
    company_name: str = ""
    analysis_trace_id: str = ""
    created_at: str = ""
    status: str = "new"               # new / analyzing / resolved / dismissed
    resolution_rule_id: Optional[int] = None
    resolution_note: str = ""

@dataclass
class DiscoveryResult:
    """一次未知模式发现的结果"""
    unknown_patterns: List[UnknownPattern] = field(default_factory=list)
    known_coverage: Dict[str, float] = field(default_factory=dict)
    total_dimensions: int = 0
    covered_dimensions: int = 0
    uncovered_dimensions: int = 0
    evolution_potential: float = 0.0  # 系统进化潜力 0-1


# ==================== 已知规则覆盖度定义 ====================

# 系统已知的分析维度及其覆盖的规则范围
KNOWN_COVERAGE = {
    "银行流水": {
        "rules": ["隐匿收入", "异常交易时间", "大额整数交易", "非对公付款", "公私混用"],
        "hypotheses": ["H001_隐匿销售收入", "H005_虚列成本费用"],
        "coverage": 0.75,  # 已知规则覆盖率
    },
    "进项发票": {
        "rules": ["虚开进项", "品名匹配", "单价异常", "数量异常", "加工费专项", 
                 "供应商集中", "同城供应商", "无付款进项", "红冲作废"],
        "hypotheses": ["H002_虚开进项", "H003_委托加工真实性", "H009_发票群集性虚开"],
        "coverage": 0.70,
    },
    "销项发票": {
        "rules": ["品名匹配", "客户集中", "开票时间异常", "作废率异常", "红冲率异常",
                 "已开票无银行收款", "未开票收入", "进销数量偏差"],
        "hypotheses": ["H001_隐匿销售收入", "H006_进销品名不匹配"],
        "coverage": 0.72,
    },
    "财务报表": {
        "rules": ["利润现金流背离", "往来科目异常", "资产折旧匹配", "毛利率异常", 
                 "三项费用率异常", "税负率异常", "行业对标"],
        "hypotheses": ["H004_关联交易转移利润", "H008_小微资格不符"],
        "coverage": 0.65,
    },
    "工资社保": {
        "rules": ["工资水平异常", "社保基数不匹配", "个税申报不一致", "工资现金发放"],
        "hypotheses": [],
        "coverage": 0.55,
    },
    "税收优惠": {
        "rules": ["小微企业条件", "高新企业条件", "研发加计条件", "政策有效期"],
        "hypotheses": ["H008_小微资格不符"],
        "coverage": 0.60,
    },
    "合同物流": {
        "rules": ["合同缺失", "运输成本缺失", "重物跨省无运输", "加工费无合同"],
        "hypotheses": ["H003_委托加工真实性"],
        "coverage": 0.40,
    },
}

# 各维度可能的异常信号及其检测逻辑
ANOMALY_DETECTORS = {
    "银行流水": {
        "money_laundering_pattern": lambda b, i, s: _detect_structured_transfers(b),
        "salary_proxy_pattern": lambda b, i, s: _detect_same_amount_transfers(b),
        "round_trip_pattern": lambda b, i, s: _detect_round_trip(b),
    },
    "进项发票": {
        "phantom_supplier_pattern": lambda b, i, s: _detect_phantom_suppliers(i, "进项"),
        "price_escalation_pattern": lambda b, i, s: _detect_price_trend_anomalies(i, "进项"),
        "quantity_anomaly_pattern": lambda b, i, s: _detect_quantity_spikes(i),
    },
    "销项发票": {
        "phantom_customer_pattern": lambda b, i, s: _detect_phantom_suppliers(i, "销项"),
        "revenue_smoothing_pattern": lambda b, i, s: _detect_revenue_smoothing(i),
        "off_hours_invoicing": lambda b, i, s: _detect_off_hours(i),
    },
}

# ==================== 检测函数 ====================

def _detect_structured_transfers(bank_txs):
    """检测结构化资金转移模式（洗钱特征）"""
    if not bank_txs or len(bank_txs) < 5:
        return None
    # 检测相同金额的规律性付款
    amounts = []
    for tx in bank_txs:
        debit = float(tx.get("debit", 0) or 0)
        credit = float(tx.get("credit", 0) or 0)
        amt = debit + credit
        if amt > 0:
            amounts.append(round(amt, -2))  # 四舍五入到百元
    
    if not amounts:
        return None
    
    counter = Counter(amounts)
    most_common = counter.most_common(3)
    total = len(amounts)
    if most_common[0][1] > total * 0.2:
        return {
            "pattern": "结构化资金转移",
            "detail": f"相同金额({most_common[0][0]:,.0f})出现{most_common[0][1]}次/{total}次",
            "significance": min(0.9, most_common[0][1] / total * 3),
            "risk_hint": "可能为拆分大额交易规避监管"
        }
    return None

def _detect_same_amount_transfers(bank_txs):
    """检测固定金额批次转账（代发工资或隐匿分红特征）"""
    if not bank_txs or len(bank_txs) < 3:
        return None
    # 检测多人相同金额的收款
    credit_amounts = Counter()
    for tx in bank_txs:
        credit = float(tx.get("credit", 0) or 0)
        if credit > 1000:
            credit_amounts[round(credit, -2)] += 1
    
    for amt, count in credit_amounts.most_common(5):
        if count >= 3 and count / len(bank_txs) > 0.1:
            return {
                "pattern": "固定金额批次转账",
                "detail": f"相同收款金额({amt:,.0f})出现{count}次",
                "significance": 0.7,
                "risk_hint": "可能为代发工资/发放股东分红未代扣个税"
            }
    return None

def _detect_round_trip(bank_txs):
    """检测资金回流：付出后短期内从同一对方收回"""
    if not bank_txs or len(bank_txs) < 10:
        return None
    # 简化检测：相同交易对方的付-收对
    tx_by_cp = defaultdict(list)
    for tx in bank_txs:
        cp = str(tx.get("counterparty", "")).strip()
        if cp and len(cp) >= 4:
            tx_by_cp[cp].append(tx)
    
    for cp, txs in tx_by_cp.items():
        if len(txs) < 2:
            continue
        debits = [t for t in txs if float(t.get("debit", 0) or 0) > 0]
        credits = [t for t in txs if float(t.get("credit", 0) or 0) > 0]
        if debits and credits:
            return {
                "pattern": "资金回流",
                "detail": f"{cp}存在收付双向交易",
                "significance": 0.75,
                "risk_hint": "可能为虚假交易套取资金/虚开进项后资金回流"
            }
    return None

def _detect_phantom_suppliers(invoices, direction):
    """检测幽灵供应商/客户：名称异常短或含虚拟词汇"""
    if not invoices:
        return None
    kws = ["科技", "咨询", "服务", "贸易", "商贸", "实业", "发展"]
    suspicious = []
    for inv in invoices:
        if inv.get("direction", "") != direction:
            continue
        name = str(inv.get("seller", inv.get("buyer", inv.get("counterparty", "")))).strip()
        if not name or len(name) < 4:
            continue
        # 名称异常短但含常见壳公司关键词
        if len(name) <= 6 and any(k in name for k in kws):
            suspicious.append(name)
    
    if len(suspicious) >= 3:
        return {
            "pattern": "幽灵供应商/客户",
            "detail": f"疑似壳公司：{suspicious[:3]}",
            "significance": 0.8,
            "risk_hint": "这些企业名称短且含通用关键词，可能为空壳公司"
        }
    return None

def _detect_price_trend_anomalies(invoices, direction):
    """检测价格趋势异常：同品名价格波动过大"""
    if not invoices or len(invoices) < 5:
        return None
    
    goods_prices = defaultdict(list)
    for inv in invoices:
        if inv.get("direction", "") != direction:
            continue
        goods = str(inv.get("goods", "")).strip()
        amount = float(inv.get("amount", 0) or 0)
        quantity = float(inv.get("quantity", 0) or 1)
        if goods and amount > 0 and quantity > 0:
            goods_prices[goods].append(amount / quantity)
    
    for goods, prices in goods_prices.items():
        if len(prices) < 3:
            continue
        avg = sum(prices) / len(prices)
        if avg == 0:
            continue
        variations = [abs(p - avg) / avg for p in prices]
        max_var = max(variations)
        if max_var > 0.5:
            return {
                "pattern": "同品名价格波动大",
                "detail": f"品名'{goods}'价格偏离均值{max_var:.0%}",
                "significance": min(0.85, max_var),
                "risk_hint": "同品名价格大幅波动，可能混入非同类商品或人为操控价格"
            }
    return None

def _detect_quantity_spikes(invoices):
    """检测数量异常突变"""
    if not invoices or len(invoices) < 10:
        return None
    # 按日期排序检测数量突变
    dated = []
    for inv in invoices:
        date_str = str(inv.get("date", inv.get("开票日期", ""))).strip()[:10]
        qty = float(inv.get("quantity", 0) or 0)
        if date_str and qty > 0:
            dated.append((date_str, qty))
    
    if len(dated) < 5:
        return None
    
    dated.sort()
    quantities = [d[1] for d in dated]
    avg = sum(quantities) / len(quantities)
    if avg == 0:
        return None
    
    # 检测超过3倍标准差的突变
    std = (sum((q - avg)**2 for q in quantities) / len(quantities)) ** 0.5
    spikes = [i for i, q in enumerate(quantities) if abs(q - avg) > 3 * std and std > 0]
    if spikes:
        return {
            "pattern": "数量异常突变",
            "detail": f"发现{len(spikes)}个交易日数量异常偏离均值",
            "significance": 0.7,
            "risk_hint": "发票数量突然暴增或暴减，可能为集中开票/隐匿交易"
        }
    return None

def _detect_revenue_smoothing(invoices):
    """检测收入平滑：人为将收入均匀分布在各月"""
    if not invoices or len(invoices) < 6:
        return None
    
    monthly = defaultdict(float)
    for inv in invoices:
        if inv.get("direction") not in ("销项", "sales"):
            continue
        date_str = str(inv.get("date", "")).strip()[:7]
        amount = float(inv.get("amount", 0) or 0)
        if date_str and amount > 0:
            monthly[date_str] += amount
    
    if len(monthly) < 4:
        return None
    
    amounts = list(monthly.values())
    avg = sum(amounts) / len(amounts)
    if avg == 0:
        return None
    # 变异系数 < 0.1 表示收入过于均匀
    std = (sum((a - avg)**2 for a in amounts) / len(amounts)) ** 0.5
    cv = std / avg
    if cv < 0.1:
        return {
            "pattern": "收入平滑",
            "detail": f"月度收入变异系数仅{cv:.2f}，过于均匀",
            "significance": 0.65,
            "risk_hint": "月度收入几乎一致，可能人为调节收入确认时点"
        }
    return None

def _detect_off_hours(invoices):
    """检测非营业时间开票"""
    if not invoices or len(invoices) < 5:
        return None
    off_hours = 0
    for inv in invoices:
        time_str = str(inv.get("time", inv.get("开票时间", ""))).strip()
        if time_str and len(time_str) >= 4:
            try:
                hour = int(time_str.split(":")[0]) if ":" in time_str else int(time_str[-4:-2] or "0")
                if hour < 6 or hour > 20:
                    off_hours += 1
            except:
                pass
    
    if off_hours >= 3:
        return {
            "pattern": "非营业时间开票",
            "detail": f"{off_hours}张发票在凌晨或深夜开具",
            "significance": 0.75,
            "risk_hint": "非正常工作时间开票，可能是批量虚开发票的特征"
        }
    return None

# ==================== 核心检测引擎 ====================

class UnknownPatternDetector:
    """未知模式检测器 —— 系统的认知边界扫描器"""
    
    def __init__(self):
        self._known_coverage = KNOWN_COVERAGE
        self._anomaly_detectors = ANOMALY_DETECTORS
    
    def scan(self, bank_txs, invoices, salaries, vouchers, context: Dict, 
             existing_findings: List[Dict], agent_hypotheses: List[Dict],
             company_id: int = 0, company_name: str = "", trace_id: str = "") -> DiscoveryResult:
        """全维度扫描，发现系统无法解释的模式"""
        unknown_patterns = []
        coverage_map = {}
        
        # 构建已覆盖的信号集合（从existing_findings和agent_hypotheses中提取）
        covered_signals = set()
        for f in existing_findings:
            ftype = f.get("type", "")
            for dim, meta in self._known_coverage.items():
                for rule in meta["rules"]:
                    if rule in ftype or self._fuzzy_match(rule, ftype):
                        covered_signals.add(f"{dim}:{rule}")
                for hyp in meta.get("hypotheses", []):
                    if hyp.split("_", 1)[1] if "_" in hyp else hyp in ftype:
                        covered_signals.add(f"{dim}:{hyp}")
        
        for dim, meta in self._known_coverage.items():
            # 计算该维度的规则覆盖度
            total_rules = len(meta["rules"]) + len(meta.get("hypotheses", []))
            covered = sum(1 for sig in covered_signals if sig.startswith(f"{dim}:"))
            coverage = covered / total_rules if total_rules > 0 else 1.0
            coverage_map[dim] = coverage
            
            # 低覆盖维度 → 生成未知模式
            if coverage < 0.5:
                unknown_patterns.append(UnknownPattern(
                    id=str(uuid.uuid4())[:12],
                    name=f"维度覆盖不足: {dim}",
                    dimension=dim,
                    data_snapshot={"dimension": dim, "covered": covered, "total_rules": total_rules},
                    statistical_significance=0.7,
                    why_unknown=f"该维度仅{covered}/{total_rules}条规则被触发，存在{total_rules-covered}条规则空白",
                    best_guess=f"需扩展{dim}维度的规则覆盖",
                    suggested_investigation=[f"检查{dim}数据是否有已知规则外的新模式"],
                    similar_known_patterns=[],
                    company_id=company_id, company_name=company_name,
                    analysis_trace_id=trace_id, created_at=datetime.now().isoformat(),
                ))
        
        # 运行异常检测器，查找完全未知的信号
        for dim, detectors in self._anomaly_detectors.items():
            for det_name, det_func in detectors.items():
                result = det_func(bank_txs, invoices, salaries)
                if result and not self._is_pattern_covered(result["pattern"], covered_signals):
                    unknown_patterns.append(UnknownPattern(
                        id=str(uuid.uuid4())[:12],
                        name=result["pattern"],
                        dimension=dim,
                        data_snapshot=result,
                        statistical_significance=result.get("significance", 0.6),
                        why_unknown=f"异常检测发现'{result['pattern']}'，但无匹配的已知规则",
                        best_guess=result.get("risk_hint", "需人工分析"),
                        suggested_investigation=[result.get("risk_hint", "")],
                        similar_known_patterns=[],
                        company_id=company_id, company_name=company_name,
                        analysis_trace_id=trace_id, created_at=datetime.now().isoformat(),
                    ))
        
        # 计算进化潜力
        total_dims = len(self._known_coverage)
        covered_dims = sum(1 for v in coverage_map.values() if v >= 0.5)
        uncovered_dims = total_dims - covered_dims
        evolution_potential = uncovered_dims / total_dims if total_dims > 0 else 0
        
        return DiscoveryResult(
            unknown_patterns=unknown_patterns,
            known_coverage=coverage_map,
            total_dimensions=total_dims,
            covered_dimensions=covered_dims,
            uncovered_dimensions=uncovered_dims,
            evolution_potential=evolution_potential,
        )
    
    def _fuzzy_match(self, keyword: str, text: str) -> bool:
        """模糊匹配：关键词是否出现在文本中"""
        kw_parts = keyword
        text_short = text[:len(keyword)+5] if len(text) > len(keyword) else text
        return kw_parts in text_short or any(c in text_short for c in kw_parts if len(c) >= 2)
    
    def _is_pattern_covered(self, pattern_name: str, covered_signals: set) -> bool:
        """检查异常检测结果是否已被已知规则覆盖"""
        for sig in covered_signals:
            if pattern_name in sig or sig.split(":")[-1].split("_")[-1] in pattern_name:
                return True
        return False


# ==================== 智能路由 → 三体协作 ====================

def route_to_zhige(unknown_pattern: UnknownPattern) -> Dict:
    """将未知模式路由到智哥（我）进行人工分析
    
    返回标准化的分析请求，包含足够的上下文让我能做出判断。
    """
    return {
        "routing_type": "unknown_pattern_analysis",
        "priority": "high" if unknown_pattern.statistical_significance > 0.75 else "medium",
        "pattern_id": unknown_pattern.id,
        "pattern_name": unknown_pattern.name,
        "dimension": unknown_pattern.dimension,
        "why_unknown": unknown_pattern.why_unknown,
        "data_context": unknown_pattern.data_snapshot,
        "best_guess": unknown_pattern.best_guess,
        "investigation_hints": unknown_pattern.suggested_investigation,
        "action_required": "分析该未知模式 → 确定是否为有效风险信号 → 如是，写入新规则 → 系统自动学习",
        "company_id": unknown_pattern.company_id,
        "company_name": unknown_pattern.company_name,
        "trace_id": unknown_pattern.analysis_trace_id,
    }


def inject_new_rule(pattern_id: str, rule_definition: Dict, db_session=None) -> Dict:
    """智哥分析完成后，将新规则注入系统
    
    rule_definition = {
        "rule_name": "新规则名称",
        "rule_type": "风险检测/税收优惠/数据质量/...",
        "trigger_conditions": {"dimension": "银行流水", "min_amount": 100000, ...},
        "detection_logic": "检测逻辑描述",
        "risk_level": "高/中/低",
        "law_ref": "法律依据",
        "suggestion": "处理建议",
    }
    """
    if db_session is None:
        return {"ok": False, "message": "需要数据库连接"}
    
    from database import SelfHealingRule
    import sqlalchemy as sa
    
    # 创建自愈规则（复用self_healing的机制）
    rule = SelfHealingRule(
        rule_name=f"[智哥] {rule_definition.get('rule_name', '新规则')}",
        rule_type=rule_definition.get("rule_type", "unknown_pattern"),
        domain=rule_definition.get("trigger_conditions", {}).get("dimension", "通用"),
        trigger_pattern=json.dumps(rule_definition.get("trigger_conditions", {}), ensure_ascii=False),
        correction_action="new_rule",
        correction_detail=json.dumps({
            "detection_logic": rule_definition.get("detection_logic", ""),
            "risk_level": rule_definition.get("risk_level", "中"),
            "law_ref": rule_definition.get("law_ref", ""),
            "suggestion": rule_definition.get("suggestion", ""),
            "source_pattern_id": pattern_id,
        }, ensure_ascii=False),
        source_error_count=1,
        confidence=0.85,
        status="active",
        auto_apply=True,  # 直接激活！
    )
    db_session.add(rule)
    db_session.commit()
    
    return {
        "ok": True,
        "rule_id": rule.id,
        "rule_name": rule.rule_name,
        "auto_apply": True,
        "message": f"新规则已注入系统: {rule.rule_name}",
    }

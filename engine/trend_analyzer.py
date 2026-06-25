# ═══════════════════════════════════════════════════════════════
# 时序趋势学习引擎 (Temporal Trend Analyzer)
#
# 设计理念：
#   从"每次分析独立"进化为"趋势感知"——
#   跨期追踪企业的财务和经营指标，自动发现恶化/改善趋势。
#
#   示例输出：
#   "该企业毛利率连续3个月下降5%（从22%→17%）→ 经营恶化信号"
#   "供应商数量逐月增加但销项发票金额未同步增长 → 可能存在虚增进项"
# ═══════════════════════════════════════════════════════════════

import json
import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean, stdev


@dataclass
class MetricPoint:
    """单个时间点的指标快照"""
    timestamp: str
    value: float
    label: str = ""  # 如 "2024-01"
    metadata: Dict = field(default_factory=dict)


@dataclass
class TrendResult:
    """趋势分析结果"""
    metric: str  # 指标名称
    points: List[MetricPoint]  # 时间序列数据点
    trend: str  # rising / falling / stable / volatile
    change_rate: float  # 变化率（%）
    signal: str  # 趋势信号描述
    risk_level: str  # high / medium / low
    confidence: float  # 置信度 0-1


class TrendAnalyzer:
    """
    时序趋势分析器
    
    用法：
        analyzer = TrendAnalyzer(memory_path)
        trends = analyzer.analyze(company_id, current_metrics)
        # trends: [{metric, points, trend, signal, risk_level}]
    """
    
    # 需要追踪的核心指标
    TRACKED_METRICS = [
        "gross_margin",           # 毛利率
        "sales_revenue",          # 销售收入
        "purchase_amount",         # 采购金额
        "supplier_count",          # 供应商数量
        "customer_count",          # 客户数量
        "invoice_count",           # 发票数量
        "bank_inflow",             # 银行流入
        "bank_outflow",            # 银行流出
        "salary_total",            # 工资总额
        "employee_count",          # 员工数量
        "tax_burden",              # 税负率
        "profit_margin",           # 净利率
    ]
    
    # 恶化趋势的危险阈值
    DETERIORATION_THRESHOLDS = {
        "gross_margin": {"direction": "falling", "threshold": 5.0, "periods": 3},
        "sales_revenue": {"direction": "falling", "threshold": 10.0, "periods": 3},
        "tax_burden": {"direction": "falling", "threshold": 30.0, "periods": 2},
        "profit_margin": {"direction": "falling", "threshold": 5.0, "periods": 3},
    }
    
    def __init__(self, memory_path: str = None):
        if memory_path is None:
            memory_path = os.path.join(
                os.path.dirname(__file__), "..", "static", "cross_analysis_memory.json"
            )
        self.memory_path = memory_path
    
    def load_history(self, company_id: int) -> List[Dict]:
        """加载该企业的历史分析记录"""
        if not os.path.exists(self.memory_path):
            return []
        
        try:
            with open(self.memory_path, "r", encoding="utf-8") as f:
                memory = json.load(f)
        except Exception:
            return []
        
        analyses = memory.get("analyses", [])
        # 筛选该企业
        company_analyses = [
            a for a in analyses
            if str(a.get("company_id", "")) == str(company_id)
        ]
        
        # 按时间排序
        company_analyses.sort(
            key=lambda a: a.get("timestamp", a.get("created_at", "2000-01-01"))
        )
        
        return company_analyses
    
    def extract_metrics(self, analysis: Dict) -> Dict[str, float]:
        """从分析记录中提取可追踪的指标"""
        metrics = {}
        
        # 从不同层级提取
        financial = analysis.get("financial", {})
        snapshot = analysis.get("financial_snapshot", analysis.get("snapshot", {}))
        findings = analysis.get("findings", [])
        
        # 毛利率
        if "gross_margin" in financial:
            metrics["gross_margin"] = float(financial["gross_margin"])
        elif "gross_margin" in snapshot:
            metrics["gross_margin"] = float(snapshot["gross_margin"])
        
        # 销售收入
        if "sales_revenue" in financial:
            metrics["sales_revenue"] = float(financial["sales_revenue"])
        elif "total_sales" in financial:
            metrics["sales_revenue"] = float(financial["total_sales"])
        elif "revenue" in snapshot:
            metrics["sales_revenue"] = float(snapshot["revenue"])
        
        # 采购金额
        if "purchase_amount" in financial:
            metrics["purchase_amount"] = float(financial["purchase_amount"])
        
        # 供应商数量
        if "supplier_count" in analysis:
            metrics["supplier_count"] = int(analysis["supplier_count"])
        elif "supplier_count" in snapshot:
            metrics["supplier_count"] = int(snapshot["supplier_count"])
        
        # 客户数量
        if "customer_count" in analysis:
            metrics["customer_count"] = int(analysis["customer_count"])
        elif "customer_count" in snapshot:
            metrics["customer_count"] = int(snapshot["customer_count"])
        
        # 发票数量
        if "invoice_count" in analysis:
            metrics["invoice_count"] = int(analysis["invoice_count"])
        elif "invoice_count" in snapshot:
            metrics["invoice_count"] = int(snapshot["invoice_count"])
        
        # 银行流水
        if "bank_inflow" in snapshot:
            metrics["bank_inflow"] = float(snapshot["bank_inflow"])
        if "bank_outflow" in snapshot:
            metrics["bank_outflow"] = float(snapshot["bank_outflow"])
        
        # 工资
        if "salary_total" in snapshot:
            metrics["salary_total"] = float(snapshot["salary_total"])
        
        # 员工
        if "employee_count" in snapshot:
            metrics["employee_count"] = int(snapshot["employee_count"])
        
        # 风险评分可作为综合指标
        if "risk_score" in analysis:
            metrics["risk_score"] = float(analysis["risk_score"])
        
        return metrics
    
    def build_timeseries(self, company_id: int) -> Dict[str, List[MetricPoint]]:
        """构建时间序列"""
        history = self.load_history(company_id)
        
        timeseries: Dict[str, List[MetricPoint]] = {
            metric: [] for metric in self.TRACKED_METRICS
        }
        
        for analysis in history:
            ts = analysis.get("timestamp", analysis.get("created_at", ""))
            if not ts:
                continue
            
            metrics = self.extract_metrics(analysis)
            period = analysis.get("period", "")
            
            for metric_name in self.TRACKED_METRICS:
                if metric_name in metrics:
                    timeseries[metric_name].append(MetricPoint(
                        timestamp=ts,
                        value=metrics[metric_name],
                        label=period or ts[:10],
                        metadata={"analysis_id": analysis.get("trace_id", "")}
                    ))
        
        return timeseries
    
    def detect_trend(self, points: List[MetricPoint], min_points: int = 3) -> Optional[TrendResult]:
        """检测时间序列的趋势"""
        if len(points) < min_points:
            return None
        
        values = [p.value for p in points]
        
        if len(values) < 3:
            return None
        
        # 计算变化率
        last_values = values[-3:]  # 最近3期
        prev_values = values[:3] if len(values) >= 6 else values[:-3]  # 前3期
        
        if len(prev_values) < 1:
            return None
        
        avg_last = mean(last_values)
        avg_prev = mean(prev_values)
        
        if avg_prev == 0:
            change_rate = 100.0 if avg_last > 0 else 0.0
        else:
            change_rate = ((avg_last - avg_prev) / abs(avg_prev)) * 100
        
        # 判断趋势方向
        abs_change = abs(change_rate)
        
        if abs_change < 3:  # 变化 < 3% 视为稳定
            trend = "stable"
        elif change_rate > 0:
            trend = "rising"
        else:
            trend = "falling"
        
        # 计算波动性
        if len(values) >= 3:
            try:
                std = stdev(values)
                cv = std / (abs(mean(values)) + 0.01)  # 变异系数
                if cv > 0.5:
                    trend = "volatile"
            except Exception:
                pass
        
        return TrendResult(
            metric="",
            points=points[-5:],  # 最近5个点
            trend=trend,
            change_rate=round(change_rate, 1),
            signal="",
            risk_level="low",
            confidence=min(0.9, len(values) / 10.0 + 0.5)
        )
    
    def analyze(self, company_id: int, current_metrics: Dict = None) -> Dict:
        """
        综合分析：加载历史 + 当前数据 → 趋势信号
        
        Args:
            company_id: 企业ID
            current_metrics: 当前分析的指标（如 {"gross_margin": 17.5, ...}）
        
        Returns: {
            company_id, periods_analyzed,
            trends: [{metric, trend, change_rate, signal, risk_level}],
            alerts: [description],
            summary
        }
        """
        timeseries = self.build_timeseries(company_id)
        
        # 如果有当前指标，追加到时间序列
        if current_metrics:
            now = datetime.now().isoformat()
            for metric_name, value in current_metrics.items():
                if metric_name in self.TRACKED_METRICS:
                    timeseries[metric_name].append(MetricPoint(
                        timestamp=now,
                        value=float(value),
                        label="当前",
                        metadata={"source": "current_analysis"}
                    ))
        
        trends = []
        alerts = []
        
        for metric_name, points in timeseries.items():
            if len(points) < 3:
                continue
            
            trend = self.detect_trend(points)
            if trend is None:
                continue
            
            trend.metric = metric_name
            
            # 生成趋势信号
            if metric_name in self.DETERIORATION_THRESHOLDS:
                d = self.DETERIORATION_THRESHOLDS[metric_name]
                direction_match = trend.trend == d["direction"]
                change_enough = abs(trend.change_rate) >= d["threshold"]
                periods_enough = len(points) >= d["periods"]
                
                if direction_match and change_enough and periods_enough:
                    metric_labels = {
                        "gross_margin": "毛利率",
                        "sales_revenue": "销售收入",
                        "tax_burden": "税负率",
                        "profit_margin": "净利率",
                    }
                    label = metric_labels.get(metric_name, metric_name)
                    
                    direction_cn = {"falling": "下降", "rising": "上升"}.get(trend.trend, "变化")
                    
                    trend.signal = (
                        f"⚠️ {label}连续{len(points)}期{direction_cn}"
                        f"{abs(trend.change_rate):.1f}%"
                        f"（从{points[0].value:.1f}→{points[-1].value:.1f}）"
                        f"→ 经营{'恶化' if trend.trend == 'falling' else '异常'}信号"
                    )
                    trend.risk_level = "high"
                    alerts.append(trend.signal)
                else:
                    trend.signal = (
                        f"{metric_labels.get(metric_name, metric_name)}"
                        f"{trend.change_rate:+.1f}%（{len(points)}期）"
                    )
                    trend.risk_level = "low" if abs(trend.change_rate) < 10 else "medium"
            else:
                trend.signal = f"{metric_name} → {trend.trend} ({trend.change_rate:+.1f}%, {len(points)}期)"
                trend.risk_level = "low"
            
            trends.append({
                "metric": trend.metric,
                "metric_label": {
                    "gross_margin": "毛利率",
                    "sales_revenue": "销售收入",
                    "purchase_amount": "采购金额",
                    "supplier_count": "供应商数量",
                    "customer_count": "客户数量",
                    "invoice_count": "发票数量",
                    "bank_inflow": "银行流入",
                    "bank_outflow": "银行流出",
                    "salary_total": "工资总额",
                    "employee_count": "员工数量",
                    "tax_burden": "税负率",
                    "profit_margin": "净利率",
                    "risk_score": "风险评分",
                }.get(trend.metric, trend.metric),
                "periods": len(points),
                "values": [{"period": p.label, "value": round(p.value, 2)} for p in trend.points],
                "trend": trend.trend,
                "change_rate": trend.change_rate,
                "signal": trend.signal,
                "risk_level": trend.risk_level,
            })
        
        # 按风险排序
        risk_order = {"high": 0, "medium": 1, "low": 2}
        trends.sort(key=lambda t: risk_order.get(t["risk_level"], 2))
        
        return {
            "company_id": company_id,
            "periods_analyzed": max(
                (len(timeseries[m]) for m in self.TRACKED_METRICS),
                default=0
            ),
            "metrics_tracked": sum(1 for m in self.TRACKED_METRICS if len(timeseries[m]) >= 3),
            "trends": trends,
            "alerts": alerts,
            "summary": (
                f"累计追踪{len(trends)}项指标趋势，"
                f"发现{len(alerts)}条恶化/异常信号。" 
                if alerts else
                f"累计追踪{len(trends)}项指标趋势，未发现明显恶化信号。"
            )
        }


def run_trend_analysis(company_id: int, current_metrics: Dict = None, memory_path: str = None) -> Dict:
    """
    一键调用：时序趋势分析
    
    Args:
        company_id: 企业ID
        current_metrics: 当前指标快照
        memory_path: 历史记忆文件路径
    
    Returns: 趋势分析结果
    """
    analyzer = TrendAnalyzer(memory_path)
    return analyzer.analyze(company_id, current_metrics)

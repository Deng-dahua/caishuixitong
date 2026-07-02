"""
风险预测模型 — 基于因果网络的多维风险预测

不是等分析完才知道风险，而是在分析前就预测：
1. 企业画像 + 历史信号 → 预测可能的风险类型和概率
2. 资料完备度 → 预测分析置信度
3. 行业 + 规模 → 预测高发风险区域
"""
import json, os, math
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Any, Optional, Tuple

class RiskPredictor:
    """税务风险预测引擎"""
    
    def __init__(self):
        self._historical_risks: List[Dict] = []
        self._industry_patterns: Dict[str, Dict] = {}
        self._load_data()
    
    def _load_data(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "cross_analysis_memory.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                self._historical_risks = data.get("analyses", [])
                self._industry_patterns = data.get("industry_patterns", {})
        except:
            pass
    
    def predict(self, company_profile: Dict, material_completeness: float = 0.5) -> Dict:
        """
        预测企业可能的风险
        
        company_profile: {industry, scale, region, history_signals, ...}
        material_completeness: 0-1的资料完备度
        """
        industry = company_profile.get("industry", "")
        scale = company_profile.get("scale", "small")
        signals = company_profile.get("signals", [])
        
        predictions = []
        
        # 1. 行业基准风险
        ind_risks = self._industry_patterns.get(industry, {})
        if ind_risks:
            for risk_type, freq in sorted(ind_risks.items(), key=lambda x: -x[1])[:5]:
                confidence = min(0.9, freq / 20)
                predictions.append({
                    "type": risk_type,
                    "probability": confidence,
                    "source": "industry_baseline",
                    "reason": f"{industry}行业历史高发（{freq}次）",
                })
        
        # 2. 规模相关风险
        scale_risks = {
            "micro": ["收入确认不合规", "发票管理不规范"],
            "small": ["增值税申报偏差", "成本费用凭证缺失"],
            "medium": ["关联交易定价", "进项税额转出遗漏"],
            "large": ["跨境交易风险", "集团内部交易"],
        }
        for risk in scale_risks.get(scale, []):
            predictions.append({
                "type": risk,
                "probability": 0.5,
                "source": "scale_baseline",
                "reason": f"{scale}规模企业常见风险",
            })
        
        # 3. 资料完备度影响
        if material_completeness < 0.3:
            predictions.append({
                "type": "资料缺失导致分析不完整",
                "probability": 0.8,
                "source": "material_gap",
                "reason": f"资料完备度仅{material_completeness:.0%}，多项分析域无法执行",
            })
        
        # 4. 信号驱动的风险预测
        signal_risk_map = {
            "银行收款超额": ("隐匿销售收入", 0.7),
            "供应商高度集中": ("虚开进项发票", 0.6),
            "加工费": ("委托加工税务风险", 0.5),
            "运输费": ("货物流真实性风险", 0.4),
            "关联方": ("关联交易合规风险", 0.6),
        }
        for sig in signals:
            if sig in signal_risk_map:
                risk_name, prob = signal_risk_map[sig]
                predictions.append({
                    "type": risk_name,
                    "probability": prob,
                    "source": "signal_driven",
                    "reason": f"检测到信号「{sig}」",
                })
        
        # 去重 + 排序
        seen = set()
        unique = []
        for p in sorted(predictions, key=lambda x: -x["probability"]):
            if p["type"] not in seen:
                seen.add(p["type"])
                unique.append(p)
        
        # 综合风险评分
        total_score = sum(p["probability"] for p in unique)
        avg_score = total_score / max(len(unique), 1)
        
        return {
            "predicted_risks": unique[:10],
            "total_risk_score": round(avg_score, 2),
            "risk_level": "高风险" if avg_score > 0.6 else ("中风险" if avg_score > 0.3 else "低风险"),
            "material_completeness": material_completeness,
            "confidence_note": f"基于{len(self._historical_risks)}条历史分析数据" if self._historical_risks else "首次预测，基于行业基准",
            "predicted_at": datetime.now().isoformat(),
        }
    
    def compare_to_actual(self, predicted: Dict, actual_findings: List[Dict]) -> Dict:
        """对比预测与实际结果，计算预测准确度"""
        predicted_types = set(p["type"] for p in predicted.get("predicted_risks", []))
        actual_types = set(f.get("type", "") for f in actual_findings)
        
        hits = predicted_types & actual_types
        misses = predicted_types - actual_types
        surprises = actual_types - predicted_types
        
        precision = len(hits) / max(len(predicted_types), 1)
        recall = len(hits) / max(len(actual_types), 1)
        
        return {
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / max(precision + recall, 0.01),
            "hits": list(hits)[:10],
            "misses": list(misses)[:10],
            "surprises": list(surprises)[:10],
            "evaluation": (
                f"预测准确率{precision:.0%}，召回率{recall:.0%}"
                f"；{len(surprises)}个未预料到的新发现"
            ),
        }
    
    def get_industry_trends(self) -> Dict:
        """获取各行业风险趋势"""
        trends = {}
        for ind, risks in self._industry_patterns.items():
            top_risks = sorted(risks.items(), key=lambda x: -x[1])[:3]
            trend = "上升" if sum(r[1] for r in top_risks) > 5 else ("稳定" if sum(r[1] for r in top_risks) > 0 else "无数据")
            trends[ind] = {
                "top_risks": [r[0] for r in top_risks],
                "total_analyses": sum(risks.values()),
                "trend": trend,
            }
        return trends


# 全局预测引擎
predictor = RiskPredictor()

def get_predictor() -> RiskPredictor:
    return predictor

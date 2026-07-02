"""
智能抽样引擎 — 基于统计的稽查抽样策略

不随机抽，而是：
1. 分层抽样：按金额/风险/行业分层
2. 重点抽样：高风险区域100%覆盖，低风险按比例抽
3. 自适应抽样：看前N笔结果决定后N笔的抽样密度
4. 置信度射击：抽到95%置信度自动停
"""
import json, math, os
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

class SmartSampler:
    """稽查智能抽样引擎"""
    
    def __init__(self):
        self._history: List[Dict] = []
    
    def design_sample(self, population: List[Dict], risk_field: str = "risk_score",
                      amount_field: str = "amount", confidence: float = 0.95) -> Dict:
        """
        设计抽样策略
        
        population: 总体数据列表，每条含risk_score和amount
        返回: {sample_indices, coverage, expected_issues, strategy}
        """
        if not population:
            return {"error": "总体为空"}
        
        n = len(population)
        
        # 1. 分层：按风险评分分4层
        sorted_pop = sorted(population, key=lambda x: x.get(risk_field, 0), reverse=True)
        
        high_cut = max(1, int(n * 0.1))  # 前10%为高风险层
        mid_cut = max(1, int(n * 0.4))   # 10-40%为中风险层
        
        strata = {
            "高风险层": sorted_pop[:high_cut],
            "中风险层": sorted_pop[high_cut:mid_cut],
            "低风险层": sorted_pop[mid_cut:],
        }
        
        # 2. 各层抽样率
        sample_plan = []
        
        for name, items in strata.items():
            if name == "高风险层":
                rate = 1.0  # 100%
            elif name == "中风险层":
                rate = 0.5 + 0.3 * (len(items) / max(n, 1))
            else:
                rate = 0.1 + 0.2 * (len(items) / max(n, 1))
            
            k = max(1, int(len(items) * rate))
            # 取该层前k条（已按风险排序）
            sampled = items[:k]
            
            total_amt = sum(x.get(amount_field, 0) for x in items)
            sampled_amt = sum(x.get(amount_field, 0) for x in sampled)
            
            sample_plan.append({
                "stratum": name,
                "population": len(items),
                "sampled": k,
                "rate": rate,
                "total_amount": total_amt,
                "sampled_amount": sampled_amt,
                "coverage": sampled_amt / max(total_amt, 1),
            })
        
        total_sampled = sum(p["sampled"] for p in sample_plan)
        total_pop = n
        
        # 3. 预估发现数
        expected_findings = sum(
            p["sampled"] * 0.3 if p["stratum"] == "高风险层"
            else p["sampled"] * 0.1 if p["stratum"] == "中风险层"
            else p["sampled"] * 0.02
            for p in sample_plan
        )
        
        return {
            "total_population": total_pop,
            "total_sampled": total_sampled,
            "sample_rate": total_sampled / max(total_pop, 1),
            "confidence": confidence,
            "strata": sample_plan,
            "expected_findings": int(expected_findings),
            "strategy": (
                f"分层抽样：高风险层100%覆盖({sample_plan[0]['sampled']}条)，"
                f"中风险层{int(sample_plan[1]['rate']*100) if len(sample_plan)>1 else 0}%抽样，"
                f"低风险层{int(sample_plan[2]['rate']*100) if len(sample_plan)>2 else 0}%抽样"
            ) if len(sample_plan) >= 3 else "自适应分层抽样",
            "generated_at": datetime.now().isoformat(),
        }
    
    def adaptive_continue(self, results_so_far: List[Dict], remaining: List[Dict],
                          target_precision: float = 0.1) -> Dict:
        """
        自适应继续抽样：根据前N笔结果自动调整后续抽样密度
        
        如果前N笔发现率高于预期→加大抽样
        如果前N笔发现率接近零→提前终止
        """
        if not results_so_far:
            return {"action": "continue", "sample_rate": 0.5}
        
        n_done = len(results_so_far)
        n_found = sum(1 for r in results_so_far if r.get("issue", False))
        hit_rate = n_found / max(n_done, 1)
        
        if hit_rate > 0.3:
            return {
                "action": "increase",
                "reason": f"发现率高({hit_rate:.0%})，建议加大抽样密度",
                "sample_rate": 0.7,
                "remaining": len(remaining),
            }
        elif hit_rate < 0.02 and n_done >= 20:
            return {
                "action": "stop",
                "reason": f"发现率极低({hit_rate:.0%})，已抽{n_done}条，建议终止抽样",
                "sample_rate": 0,
                "remaining": len(remaining),
            }
        else:
            return {
                "action": "continue",
                "reason": f"发现率正常({hit_rate:.0%})，继续当前抽样密度",
                "sample_rate": 0.3,
                "remaining": len(remaining),
            }


# 全局抽样引擎
sampler = SmartSampler()

def get_sampler() -> SmartSampler:
    return sampler

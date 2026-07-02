"""
多期趋势分析 + 多企业集团分析

趋势分析：对比同一企业多期分析的指标变化
集团分析：关联企业间的风险传导网络
"""
import json, os, math
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any, Optional

class TrendAnalyzer:
    """多期趋势分析引擎"""
    
    def __init__(self):
        self._history: Dict[int, List[Dict]] = defaultdict(list)  # company_id → [analyses]
        self._load()
    
    def _load(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "cross_analysis_memory.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                for analysis in data.get("analyses", []):
                    cid = analysis.get("company_id", 0)
                    self._history[cid].append(analysis)
                # 只保留最近10期
                for cid in self._history:
                    self._history[cid] = sorted(
                        self._history[cid],
                        key=lambda x: x.get("analyzed_at", ""),
                    )[-10:]
        except:
            pass
    
    def record(self, company_id: int, analysis: Dict):
        """记录一次分析"""
        analysis["analyzed_at"] = datetime.now().isoformat()
        self._history[company_id].append(analysis)
        if len(self._history[company_id]) > 10:
            self._history[company_id] = self._history[company_id][-10:]
    
    def analyze_trends(self, company_id: int) -> Dict:
        """分析多期趋势"""
        analyses = self._history.get(company_id, [])
        if len(analyses) < 2:
            return {"status": "insufficient_data", "message": f"仅{len(analyses)}期分析数据，需>=2期才能做趋势分析"}
        
        # 按时间排序
        sorted_analyses = sorted(analyses, key=lambda x: x.get("analyzed_at", ""))
        first = sorted_analyses[0]
        last = sorted_analyses[-1]
        
        trends = []
        
        # 风险等级趋势
        risk_order = {"低风险": 1, "中风险": 2, "高风险": 3, "极高风险": 4}
        first_risk = risk_order.get(first.get("overall_level", "中风险"), 2)
        last_risk = risk_order.get(last.get("overall_level", "中风险"), 2)
        risk_change = last_risk - first_risk
        
        trends.append({
            "metric": "综合风险等级",
            "first": first.get("overall_level", "?"),
            "last": last.get("overall_level", "?"),
            "change": "上升" if risk_change > 0 else ("下降" if risk_change < 0 else "稳定"),
            "magnitude": abs(risk_change),
        })
        
        # 发现数量趋势
        first_count = first.get("total_risks", 0)
        last_count = last.get("total_risks", 0)
        count_change = last_count - first_count
        
        trends.append({
            "metric": "风险发现数量",
            "first": first_count,
            "last": last_count,
            "change": "增加" if count_change > 0 else ("减少" if count_change < 0 else "不变"),
            "magnitude": abs(count_change),
        })
        
        # 新增/消失的发现类型
        first_types = set(f.get("type", "") for f in first.get("findings", []))
        last_types = set(f.get("type", "") for f in last.get("findings", []))
        new_types = last_types - first_types
        removed_types = first_types - last_types
        
        if new_types:
            trends.append({
                "metric": "新增风险类型",
                "first": "",
                "last": ", ".join(list(new_types)[:3]),
                "change": "新增",
                "magnitude": len(new_types),
            })
        
        if removed_types:
            trends.append({
                "metric": "消失风险类型",
                "first": ", ".join(list(removed_types)[:3]),
                "last": "",
                "change": "消除",
                "magnitude": len(removed_types),
            })
        
        return {
            "company_id": company_id,
            "periods": len(analyses),
            "date_range": f"{first.get('analyzed_at','')[:10]} ~ {last.get('analyzed_at','')[:10]}",
            "trends": trends,
            "summary": self._summarize_trends(trends),
        }
    
    def _summarize_trends(self, trends: List[Dict]) -> str:
        improvements = [t for t in trends if t["change"] in ("下降", "减少", "消除")]
        deteriorations = [t for t in trends if t["change"] in ("上升", "增加", "新增")]
        
        if not deteriorations and improvements:
            return f"整体向好——{len(improvements)}项指标改善"
        elif deteriorations and not improvements:
            return f"⚠️ 整体恶化——{len(deteriorations)}项指标变差"
        elif not deteriorations and not improvements:
            return "整体稳定"
        else:
            return f"有升有降——{len(improvements)}项改善，{len(deteriorations)}项变差"


class GroupAnalyzer:
    """多企业集团分析引擎"""
    
    def __init__(self):
        self._relations: List[Dict] = []
        self._load()
    
    def _load(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "cross_enterprise_data.json")
        try:
            with open(path, encoding="utf-8") as f:
                self._relations = json.load(f)
        except:
            self._relations = []
    
    def add_relation(self, company_a: str, company_b: str, rel_type: str,
                     common_signals: List[str] = None):
        """添加企业间关系"""
        self._relations.append({
            "company_a": company_a,
            "company_b": company_b,
            "type": rel_type,  # 关联方/供应商/客户/共同人员/共同地址
            "common_signals": common_signals or [],
            "added_at": datetime.now().isoformat(),
        })
    
    def find_risk_cluster(self, company_name: str) -> Dict:
        """找到与目标企业相关的风险集群"""
        related = []
        for rel in self._relations:
            if rel["company_a"] == company_name:
                related.append({"company": rel["company_b"], "type": rel["type"]})
            elif rel["company_b"] == company_name:
                related.append({"company": rel["company_a"], "type": rel["type"]})
        
        # 二级关联（关联的关联）
        second_degree = set()
        for r in related:
            for rel2 in self._relations:
                if rel2["company_a"] == r["company"]:
                    second_degree.add(rel2["company_b"])
                elif rel2["company_b"] == r["company"]:
                    second_degree.add(rel2["company_a"])
        second_degree.discard(company_name)
        for r in related:
            second_degree.discard(r["company"])
        
        return {
            "target": company_name,
            "direct_relations": len(related),
            "related_companies": related[:10],
            "second_degree": len(second_degree),
            "risk_conduction": (
                "高风险传导" if len(related) >= 5
                else "中风险传导" if len(related) >= 2
                else "低风险传导"
            ),
            "recommendation": (
                "建议对该企业集团进行关联稽查" if len(related) >= 5
                else "建议关注关联企业的交叉风险" if len(related) >= 2
                else "关联关系简单，风险传导概率较低"
            ),
        }
    
    def detect_anomalies(self) -> List[Dict]:
        """检测集团异常模式"""
        anomalies = []
        
        # 检测循环关联（A→B→C→A）
        companies = set()
        graph = defaultdict(set)
        for rel in self._relations:
            graph[rel["company_a"]].add(rel["company_b"])
            companies.add(rel["company_a"])
            companies.add(rel["company_b"])
        
        # 简单循环检测
        for a in companies:
            for b in graph[a]:
                for c in graph[b]:
                    if a in graph[c]:
                        anomalies.append({
                            "type": "循环关联",
                            "companies": [a, b, c],
                            "risk": "可能存在资金循环或发票对开",
                        })
        
        return anomalies[:10]


# 全局实例
trend_analyzer = TrendAnalyzer()
group_analyzer = GroupAnalyzer()

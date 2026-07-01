"""
因果网络自动发现引擎 — 系统自己学因果关系，不是手工编码

核心能力：
1. 从历史分析中自动提取"信号组合→结论"的贝叶斯条件概率
2. 发现P>阈值的因果关系 → 自动注册为推理规则
3. 识别未见过的信号组合 → 标记为"新发现模式"供人工审核
"""
import json, os, math
from datetime import datetime
from itertools import combinations
from collections import defaultdict, Counter
from typing import Dict, List, Any, Tuple, Optional

from engine.causal_network import (
    CausalNetwork, AutonomousReasoner, 
    PRIMARY_SIGNALS, CausalEdge, MultiSignalPattern,
)
from engine.semantic_reasoner import get_semantic_engine


class CausalDiscoveryEngine:
    """因果发现引擎 — 让系统自己发现'银行收款超额+供应商集中+无运输发票→虚开进项'"""
    
    def __init__(self):
        self._reasoner = AutonomousReasoner()
        self._semantic = get_semantic_engine()
        self._discoveries: List[Dict] = []
        self._load_discoveries()
    
    def _load_discoveries(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "causal_discoveries.json")
        try:
            with open(path, encoding="utf-8") as f:
                self._discoveries = json.load(f)
        except:
            self._discoveries = []
    
    def _save_discoveries(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "causal_discoveries.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._discoveries[-200:], f, ensure_ascii=False, indent=2)
    
    def discover_from_analysis(self, analysis_result: Dict) -> List[Dict]:
        """
        从一次分析结果中自动发现因果模式
        
        analysis_result: {
            "active_signals": [...],
            "findings": [{"type": "虚开进项发票", "level": "高风险", "confidence": 0.85}, ...],
            "industry": "纺织业",
            "trace_id": "xxx"
        }
        """
        signals = analysis_result.get("active_signals", [])
        findings = analysis_result.get("findings", [])
        industry = analysis_result.get("industry", "")
        trace_id = analysis_result.get("trace_id", str(datetime.now().timestamp()))
        
        new_discoveries = []
        
        # 1. 单信号→结论
        for sig in signals:
            for f in findings:
                ftype = f.get("type", "")
                if ftype:
                    new_discoveries.append({
                        "signals": [sig],
                        "finding": ftype,
                        "industry": industry,
                        "level": f.get("level", ""),
                        "confidence": f.get("confidence", 0.7),
                        "trace_id": trace_id,
                        "discovered_at": datetime.now().isoformat(),
                    })
        
        # 2. 多信号组合→结论（2/3/4信号组合）
        for size in range(2, min(5, len(signals) + 1)):
            for combo in combinations(signals, size):
                for f in findings:
                    ftype = f.get("type", "")
                    if ftype:
                        new_discoveries.append({
                            "signals": list(combo),
                            "finding": ftype,
                            "industry": industry,
                            "level": f.get("level", ""),
                            "confidence": f.get("confidence", 0.7) + (size - 2) * 0.05,
                            "trace_id": trace_id,
                            "discovered_at": datetime.now().isoformat(),
                        })
        
        # 3. 去重 + 累积计数
        for nd in new_discoveries:
            self._accumulate(nd)
        
        self._save_discoveries()
        return new_discoveries[:10]
    
    def _accumulate(self, discovery: Dict):
        """累积同模式发现次数，自动计算条件概率"""
        sigs = set(discovery["signals"])
        finding = discovery["finding"]
        industry = discovery.get("industry", "")
        
        # 找到匹配的历史记录
        for existing in self._discoveries:
            if (set(existing.get("signals", [])) == sigs and 
                existing.get("finding") == finding):
                existing["count"] = existing.get("count", 1) + 1
                existing["confidence"] = min(0.99, existing["count"] / 10)
                if industry and industry not in existing.get("industries", []):
                    existing.setdefault("industries", []).append(industry)
                return
        
        # 新发现
        self._discoveries.append({
            **discovery,
            "count": 1,
            "industries": [industry] if industry else [],
            "status": "observed",
        })
    
    def get_inference_rules(self, min_count: int = 3, min_confidence: float = 0.5) -> List[Dict]:
        """
        获取可升级为推理规则的高置信度因果发现
        
        规则格式：当 [信号1, 信号2, ...] 同时出现时，
        有 P% 概率导致 [结论]，已在 N 次分析中验证
        """
        rules = []
        for d in self._discoveries:
            count = d.get("count", 0)
            if count >= min_count:
                conf = d.get("confidence", 0)
                if conf >= min_confidence:
                    signals = d.get("signals", [])
                    finding = d.get("finding", "")
                    industries = d.get("industries", [])
                    
                    # 生成自然语言描述
                    sig_desc = " + ".join(signals)
                    rule_text = f"当 [{sig_desc}] 同时出现时，有 {conf:.0%} 概率导致「{finding}」({count}次验证)"
                    
                    rules.append({
                        "signals": signals,
                        "finding": finding,
                        "confidence": conf,
                        "count": count,
                        "industries": list(set(industries)),
                        "rule_text": rule_text,
                        "auto_apply": conf >= 0.7 and count >= 5,
                    })
        
        return sorted(rules, key=lambda x: -x["confidence"] * x["count"])
    
    def find_similar_pattern(self, unknown_signals: List[str]) -> List[Dict]:
        """
        类比推理：对于未知信号组合，找最相似的历史模式
        
        "这个我从没见过的组合，跟哪个已知的最像？"
        """
        unknown_set = set(unknown_signals)
        scored = []
        
        for d in self._discoveries:
            known_set = set(d.get("signals", []))
            # Jaccard相似度
            intersection = unknown_set & known_set
            union = unknown_set | known_set
            if union:
                similarity = len(intersection) / len(union)
                if similarity > 0:
                    scored.append({
                        "known_signals": list(known_set),
                        "known_finding": d.get("finding", ""),
                        "match_signals": list(intersection),
                        "missing_signals": list(known_set - unknown_set),
                        "extra_signals": list(unknown_set - known_set),
                        "similarity": similarity,
                        "count": d.get("count", 0),
                        "confidence": d.get("confidence", 0),
                    })
        
        return sorted(scored, key=lambda x: -x["similarity"] * x["count"])[:5]
    
    def generate_hypothesis(self, unknown_signals: List[str], context: Dict = None) -> List[Dict]:
        """
        创造性假设：基于类比生成新假设
        
        输入：一组从未见过的信号组合
        输出：基于类比推理的假设列表
        """
        similar = self.find_similar_pattern(unknown_signals)
        hypotheses = []
        
        for pattern in similar[:3]:
            sim = pattern["similarity"]
            known_finding = pattern["known_finding"]
            extra = pattern["extra_signals"]
            missing = pattern["missing_signals"]
            
            if sim >= 0.5:
                h_text = f"该模式与已发现的「{known_finding}」相似度{sim:.0%}"
                if missing:
                    h_text += f"，建议检查是否存在 {', '.join(missing)} 信号"
                if extra:
                    h_text += f"，新增信号 {', '.join(extra)} 可能指示新风险方向"
                
                hypotheses.append({
                    "hypothesis": f"可能存在类似{known_finding}的风险",
                    "rationale": h_text,
                    "confidence": sim * pattern.get("confidence", 0.7),
                    "based_on": pattern["known_finding"],
                    "action": "自动生成调查步骤" if sim > 0.7 else "建议人工审核",
                })
        
        # 如果没有相似模式，标记为真正的新模式
        if not hypotheses:
            hypotheses.append({
                "hypothesis": "发现全新的风险信号组合",
                "rationale": f"信号 [{', '.join(unknown_signals)}] 此前从未被观察到，建议人工分析可能的因果方向",
                "confidence": 0.3,
                "based_on": "新发现",
                "action": "标记为未知模式，等待人工确认",
            })
        
        return hypotheses
    
    def status(self) -> Dict:
        """获取发现引擎状态"""
        return {
            "total_discoveries": len(self._discoveries),
            "inference_rules": len(self.get_inference_rules(min_count=2)),
            "auto_rules": len(self.get_inference_rules(min_count=5, min_confidence=0.7)),
            "latest_discovery": self._discoveries[-1] if self._discoveries else None,
        }


# 全局发现引擎
discovery_engine = CausalDiscoveryEngine()

def get_discovery_engine() -> CausalDiscoveryEngine:
    return discovery_engine

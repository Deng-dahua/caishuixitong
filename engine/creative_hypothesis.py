"""
创造性假设引擎 — 类比推理 + 未知模式探索

核心能力：
1. 类比推理：遇到未知模式→找最相似的已知模式→基于类比生成假设
2. 假设竞争验证：生成多个竞争假设→验证→贝叶斯加权→选最优
3. 自动规则生成：验证通过的假设→注册为新推理规则
"""
import json, os, math
from datetime import datetime
from typing import Dict, List, Any, Optional

from engine.causal_discovery import get_discovery_engine
from engine.semantic_reasoner import get_semantic_engine


class CreativeHypothesisEngine:
    """创造性假设引擎 — 系统自己生成假设、自己验证"""
    
    def __init__(self):
        self._discovery = get_discovery_engine()
        self._semantic = get_semantic_engine()
        self._generated_hypotheses: List[Dict] = []
        self._verified_hypotheses: List[Dict] = []
        self._load_state()
    
    def _load_state(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "creative_hypotheses.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                self._generated_hypotheses = data.get("generated", [])
                self._verified_hypotheses = data.get("verified", [])
        except:
            pass
    
    def _save_state(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "creative_hypotheses.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "generated": self._generated_hypotheses[-200:],
                "verified": self._verified_hypotheses[-200:],
            }, f, ensure_ascii=False, indent=2)
    
    def reason_analogically(self, unknown_signals: List[str], unknown_findings: List[Dict],
                            context: Dict = None) -> Dict:
        """
        类比推理：核心创新
        
        系统遇到不认识的数据模式时，不再标注"未知"等人工介入。
        而是主动做类比："这个模式跟哪个已知的最像？"
        
        步骤：
        1. 语义归一化：用语义引擎标准化信号和发现的名称
        2. 类比搜索：在因果发现库中找相似模式
        3. 生成假设：基于类比生成多个竞争假设
        4. 置信度计算：基于相似度×历史验证次数加权
        """
        # 1. 语义归一化
        norm_signals = []
        for sig in unknown_signals:
            std = self._semantic.get_standard(sig)
            norm_signals.append(std if std else sig)
        
        norm_findings = []
        for f in unknown_findings:
            ft = f.get("type", "")
            std_type = self._semantic.normalize(ft) if ft else ft
            norm_findings.append({**f, "semantic_type": std_type})
        
        # 2. 类比搜索
        analogies = self._discovery.find_similar_pattern(norm_signals)
        
        # 3. 生成假设
        hypotheses = []
        
        # 假设A：最相似的已知模式
        if analogies:
            best = analogies[0]
            h_a = {
                "id": f"HYPO-{len(self._generated_hypotheses)+1:04d}",
                "type": "类比推理",
                "hypothesis": f"该模式最接近「{best['known_finding']}」",
                "rationale": f"与已知模式相似度{best['similarity']:.0%}（基于{best['count']}次历史验证）",
                "confidence": best["similarity"] * 0.8,
                "source": "analogical_inference",
                "similarity": best["similarity"],
                "signals": unknown_signals,
                "finding": best["known_finding"],
            }
            hypotheses.append(h_a)
        
        # 假设B：语义推断（用语义引擎理解信号含义）
        sig_meanings = []
        for sig in unknown_signals[:5]:
            std = self._semantic.get_standard(sig)
            if std: sig_meanings.append(f"{sig}→{std}")
        
        if sig_meanings:
            semantic_hypothesis = f"信号语义：{', '.join(sig_meanings)}。"
            # 基于语义推测风险方向
            risk_mapping = {
                "加工费": "可能存在委托加工业务的税务风险",
                "运输费": "需核实货物流真实性与发票匹配度",
                "租金": "需核实经营场所真实性和租赁合同",
                "钢材": "需核实钢材采购与实际消耗的匹配度",
                "销售收入": "需核实收入确认时点和金额准确性",
                "采购成本": "需核实采购的真实性和关联交易",
            }
            risks = []
            for std in [self._semantic.get_standard(s) for s in unknown_signals]:
                if std and std in risk_mapping:
                    risks.append(risk_mapping[std])
            
            if risks:
                h_b = {
                    "id": f"HYPO-{len(self._generated_hypotheses)+2:04d}",
                    "type": "语义推断",
                    "hypothesis": semantic_hypothesis + "\n可能的税务风险方向：" + "；".join(set(risks)),
                    "rationale": "基于税务语义引擎对信号含义的理解",
                    "confidence": 0.6,
                    "source": "semantic_inference",
                    "signals": unknown_signals,
                }
                hypotheses.append(h_b)
        
        # 假设C：频率推断（这些信号在历史中各自出现的频率）
        signal_freq = {}
        for sig in unknown_signals[:5]:
            count = sum(1 for d in self._discovery._discoveries if sig in d.get("signals", []))
            signal_freq[sig] = count
        
        freq_signals = [s for s, c in signal_freq.items() if c > 0]
        if freq_signals:
            h_c = {
                "id": f"HYPO-{len(self._generated_hypotheses)+3:04d}",
                "type": "频率推断",
                "hypothesis": f"信号 {', '.join(freq_signals)} 在历史中分别出现过{max(signal_freq.values())}次，组合出现为新模式",
                "rationale": "单一信号常见但组合罕见→可能指示新的风险类型",
                "confidence": 0.4 + min(max(signal_freq.values()) / 50, 0.3),
                "source": "frequency_inference",
                "signals": unknown_signals,
            }
            hypotheses.append(h_c)
        
        # 4. 选出最佳假设
        if hypotheses:
            best = max(hypotheses, key=lambda h: h["confidence"])
            
            # 保存生成的假设
            self._generated_hypotheses.append({
                "signals": unknown_signals,
                "findings": [f.get("type") for f in unknown_findings],
                "hypotheses": [h["hypothesis"][:200] for h in hypotheses],
                "best": best["hypothesis"][:200],
                "confidence": best["confidence"],
                "generated_at": datetime.now().isoformat(),
            })
            self._save_state()
        
        return {
            "unknown_signals": unknown_signals,
            "analogies_found": len(analogies),
            "hypotheses": hypotheses[:5],
            "best_hypothesis": best if hypotheses else None,
            "total_generated": len(self._generated_hypotheses),
        }
    
    def verify_hypothesis(self, hypothesis_id: str, verification_result: Dict) -> Dict:
        """
        验证假设：用户确认/反驳 → 更新置信度 → 通过则注册为规则
        """
        for h in self._generated_hypotheses:
            if h.get("id") == hypothesis_id:
                old_conf = h.get("confidence", 0)
                if verification_result.get("confirmed"):
                    new_conf = min(0.99, old_conf + 0.15)
                    status = "verified" if new_conf >= 0.7 else "pending"
                else:
                    new_conf = max(0.1, old_conf - 0.2)
                    status = "rejected"
                
                h["confidence"] = new_conf
                h["verified_at"] = datetime.now().isoformat()
                h["status"] = status
                
                if status == "verified":
                    self._verified_hypotheses.append(h)
                
                self._save_state()
                return {"ok": True, "new_confidence": new_conf, "status": status}
        
        return {"ok": False, "message": f"假设 {hypothesis_id} 不存在"}
    
    def get_verified_rules(self) -> List[Dict]:
        """获取已验证通过的假设（可转化为正式推理规则）"""
        return [h for h in self._verified_hypotheses if h.get("confidence", 0) >= 0.7]
    
    def status(self) -> Dict:
        return {
            "generated": len(self._generated_hypotheses),
            "verified": len(self._verified_hypotheses),
            "ready_rules": len(self.get_verified_rules()),
        }


# 全局假设引擎
creative_engine = CreativeHypothesisEngine()

def get_creative_engine() -> CreativeHypothesisEngine:
    return creative_engine

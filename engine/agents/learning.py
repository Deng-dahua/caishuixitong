"""
学习进化Agent — 分析纠正反馈，自动调整推理权重
"""
import json, os
from datetime import datetime
from .base import BaseAgent
from typing import Dict, List, Any

class LearningAgent(BaseAgent):
    """从用户纠正中学习，自动调整规则权重和行业适配"""
    
    def __init__(self):
        super().__init__(
            name="学习进化引擎",
            role="分析用户纠正模式，自动调整推理逻辑的自我进化系统",
            expertise=[
                "纠正模式识别",
                "规则权重自动调整",
                "行业自适应学习",
                "跨企业知识迁移",
                "阈值动态优化",
            ]
        )
        
        self._corrections_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "static", "user_corrections.json"
        )
        self._weights = self._load_weights()
    
    def _load_weights(self) -> Dict:
        try:
            with open(self._corrections_path, encoding="utf-8") as f:
                data = json.load(f)
            # Handle empty list case
            if isinstance(data, list):
                return {"rules": {}, "industries": {}, "patterns": []}
            # Handle record_correction format (fingerprint dict without "rules" key)
            if isinstance(data, dict) and "rules" not in data:
                return {"rules": data, "industries": {}, "patterns": []}
            return data
        except:
            return {"rules": {}, "industries": {}, "patterns": []}
    
    def _save_weights(self):
        with open(self._corrections_path, "w", encoding="utf-8") as f:
            json.dump(self._weights, f, ensure_ascii=False, indent=2)
    
    def process(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """分析纠正，更新权重"""
        action = message.get("action", "learn")
        
        if action == "learn":
            return self._learn_from_correction(message)
        elif action == "apply":
            return self._apply_learned_rules(message)
        elif action == "synthesize":
            return self._synthesize_cross_company(message)
        
        return {"agent": self.name, "status": "no_action"}
    
    def _learn_from_correction(self, msg: Dict) -> Dict:
        """从一次纠正中学习"""
        finding_type = msg.get("finding_type", "")
        industry = msg.get("industry", "")
        level = msg.get("original_level", "")
        reason = msg.get("reason", "")[:200]
        
        # 1. 按发现类型记录纠正模式
        key = finding_type[:60] or "unknown"
        if key not in self._weights["rules"]:
            self._weights["rules"][key] = {"corrections": 0, "industries": {}, "last_reason": ""}
        
        w = self._weights["rules"][key]
        w["corrections"] += 1
        w["last_reason"] = reason
        w["industries"][industry] = w["industries"].get(industry, 0) + 1
        
        # 2. 按行业记录
        if industry and len(industry) < 30:
            if industry not in self._weights["industries"]:
                self._weights["industries"][industry] = {"total_corrections": 0, "rules": {}}
            self._weights["industries"][industry]["total_corrections"] += 1
            self._weights["industries"][industry]["rules"][key] = \
                self._weights["industries"][industry]["rules"].get(key, 0) + 1
        
        # 3. 记录模式
        self._weights["patterns"].append({
            "type": key,
            "industry": industry,
            "level": level,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        })
        if len(self._weights["patterns"]) > 100:
            self._weights["patterns"] = self._weights["patterns"][-100:]
        
        self._save_weights()
        
        # 4. 判断是否触发自动规则
        auto_apply = w["corrections"] >= 3  # 同类纠正≥3次自动生效
        confidence = min(0.7 + w["corrections"] * 0.1, 1.0)
        
        return {
            "agent": self.name,
            "correction_count": w["corrections"],
            "auto_apply": auto_apply,
            "confidence": confidence,
            "learned_pattern": reason[:100] if auto_apply else "",
        }
    
    def _apply_learned_rules(self, msg: Dict) -> Dict:
        """应用已学规则到当前分析"""
        finding_type = msg.get("finding_type", "")[:60]
        industry = msg.get("industry", "")
        
        rule = self._weights["rules"].get(finding_type, {})
        corrections = rule.get("corrections", 0)
        
        result = {"agent": self.name, "adjustments": []}
        
        if corrections >= 3:
            # 同行业≥3次纠正 → 自动降级
            ind_corrections = rule.get("industries", {}).get(industry, 0)
            if ind_corrections >= 3:
                result["adjustments"].append({
                    "type": "auto_downgrade",
                    "reason": f"{industry}行业已纠正{ind_corrections}次此类型发现，自动降一级",
                    "confidence": min(0.7 + ind_corrections * 0.1, 1.0),
                })
        
        return result
    
    def _synthesize_cross_company(self, msg: Dict) -> Dict:
        """跨企业知识合成"""
        industry = msg.get("industry", "")
        rules = self._weights["rules"]
        ind_data = self._weights["industries"].get(industry, {})
        
        # 找出该行业最常见的纠正模式
        rule_ranking = sorted(
            ind_data.get("rules", {}).items(),
            key=lambda x: -x[1]
        )[:5]
        
        return {
            "agent": self.name,
            "industry": industry,
            "total_corrections": ind_data.get("total_corrections", 0),
            "top_patterns": [
                {"rule": r, "count": c, "conclusion": self._weights["rules"].get(r,{}).get("last_reason","")[:80]}
                for r, c in rule_ranking
            ],
        }

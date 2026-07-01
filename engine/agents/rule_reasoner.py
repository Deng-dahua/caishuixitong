"""
规则推理Agent — 匹配1608稽查指令，串联线索→证据→分析链
"""
import json, os
from .base import BaseAgent
from typing import Dict, List, Any

class RuleReasonerAgent(BaseAgent):
    """根据发现数据匹配规则，推理风险等级"""
    
    def __init__(self):
        super().__init__(
            name="规则推理引擎",
            role="精通1608条稽查指令的规则匹配专家，负责将域分析发现与规则引擎对接",
            expertise=[
                "规则匹配(1608条稽查指令)",
                "线索链驱动(437条)",
                "证据链闭环(781条)",
                "分析链推理(48条)",
                "跨域协商(29条)",
                "行业适配(66行业基准)",
            ]
        )
        
        # 加载规则库
        self._rules = self._load_rules()
        self._evidence = self._load_json("static/cross_domain_evidence.json")
        self._clues = self._load_json("static/cross_domain_clues.json")
        self._analysis = self._load_json("static/cross_domain_analysis.json")
    
    def _load_rules(self) -> List[Dict]:
        return self._load_json("static/tax_risk_rules_local_export.json")
    
    def _load_json(self, path: str) -> List[Dict]:
        full = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), path)
        try:
            with open(full, encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    
    def process(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """匹配规则、串联证据链"""
        finding = message.get("finding", {})
        findings = message.get("findings", [])
        domain = message.get("domain", "")
        
        result = {
            "agent": self.name,
            "matched_rules": [],
            "triggered_clues": [],
            "evidence_chain": [],
            "risk_assessment": "",
        }
        
        # 1. 匹配规则
        ftype = str(finding.get("type", ""))
        fdetail = str(finding.get("detail", ""))
        for rule in self._rules[:200]:  # 采样前200条规则
            rule_name = str(rule.get("name", rule.get("item", "")))
            rule_detail = str(rule.get("detail", ""))
            if any(kw in ftype+rule_name for kw in ftype[:10].split() if len(kw) >= 3):
                result["matched_rules"].append({
                    "id": rule.get("id", ""),
                    "name": rule_name[:60],
                    "level": rule.get("level", ""),
                    "category": rule.get("category", ""),
                })
                if len(result["matched_rules"]) >= 5:
                    break
        
        # 2. 触发线索链
        for clue in self._clues[:50]:
            clue_name = str(clue.get("name", ""))
            if any(kw in clue_name for kw in ftype[:20].split() if len(kw) >= 2):
                result["triggered_clues"].append({
                    "name": clue_name[:60],
                    "executable": clue.get("executable", False),
                })
                if len(result["triggered_clues"]) >= 3:
                    break
        
        # 3. 证据链检测
        evidence_count = len(finding.get("evidence", []) or [])
        evidence_rows = len(finding.get("evidence_rows", []) or finding.get("items", []) or [])
        domains_involved = set()
        for f in findings:
            d = f.get("domain", f.get("category", ""))
            if d: domains_involved.add(d)
        
        result["risk_assessment"] = self._assess_risk(
            finding.get("level", "中风险"),
            evidence_count + evidence_rows,
            len(domains_involved),
            len(result["matched_rules"]),
        )
        
        return result
    
    def _assess_risk(self, level, evidence_count, domain_count, rule_count):
        """综合评估风险"""
        if level in ("高风险", "极高风险"):
            if evidence_count >= 2 and domain_count >= 2:
                return "证据确凿——多源数据交叉验证，证据闭环完整"
            else:
                return "高风险判定——但证据链尚不完整，建议补充佐证材料"
        elif level == "中风险":
            if rule_count >= 2:
                return "中风险——多条规则触发，建议关注"
            else:
                return "中风险——单一规则触发，可能是偶然信号"
        return "低风险——建议保持关注"

"""
元认知引擎 —— 监控系统自身的推理过程

核心能力：
  1. 推理质量自评：每条结论的推理链是否完整？
  2. 不确定性检测：哪条结论系统自己都不确定？
  3. 信息缺口识别：还缺什么数据才能更确定？
  4. 决策建议：基于不确定性，建议获取什么信息

与反思器(agent_core.py SelfReflector)的关系：
  - 反思器：针对每条结论生成反向假设
  - 元认知：站在更高一层看"反思器做得对不对"
"""
from typing import Dict, List, Any, Optional
from datetime import datetime


class MetacognitionEngine:
    """元认知 —— 对自己的思考进行思考"""
    
    def __init__(self):
        self.reasoning_log: List[Dict] = []
        self.uncertainty_threshold = 0.3
        self.gap_patterns = self._init_gap_patterns()
    
    def _init_gap_patterns(self) -> List[Dict]:
        """信息缺口模式 —— 常见的不确定性来源"""
        return [
            {"pattern": "缺合同", "keywords": ["合同", "协议"], "missing": "购销合同/服务协议", "impact": 0.4},
            {"pattern": "缺物流", "keywords": ["运输", "物流", "快递"], "missing": "运输单据/物流记录", "impact": 0.35},
            {"pattern": "缺凭证", "keywords": ["凭证", "记账"], "missing": "记账凭证", "impact": 0.3},
            {"pattern": "缺银行流水", "keywords": ["银行", "收款", "付款"], "missing": "银行对账单", "impact": 0.5},
            {"pattern": "缺申报表", "keywords": ["申报", "增值税", "所得税"], "missing": "纳税申报表", "impact": 0.45},
            {"pattern": "单源证据", "keywords": ["仅", "只有", "单一"], "missing": "多源交叉验证", "impact": 0.35},
        ]
    
    def evaluate_reasoning_quality(self, finding: Dict) -> Dict:
        """评估单条结论的推理质量"""
        scores = {}
        issues = []
        
        # 1. 因果链完整性
        how_found = finding.get("how_found") or finding.get("description", "")
        if len(how_found) < 20:
            scores["causal_completeness"] = 0.2
            issues.append("发现过程描述过于简短，缺乏调查步骤")
        elif "经查" in how_found or "核查" in how_found or "比对" in how_found:
            scores["causal_completeness"] = 0.8
        else:
            scores["causal_completeness"] = 0.5
        
        # 2. 证据充分性
        evidence = finding.get("evidence") or finding.get("items", [])
        if isinstance(evidence, list) and len(evidence) >= 2:
            scores["evidence_sufficiency"] = 0.9
        elif isinstance(evidence, list) and len(evidence) == 1:
            scores["evidence_sufficiency"] = 0.5
            issues.append("仅单一证据源，建议增加交叉验证")
        else:
            scores["evidence_sufficiency"] = 0.3
            issues.append("缺少具体证据明细")
        
        # 3. 法律依据
        policy = finding.get("policy_ref", "")
        if "第" in str(policy) and "条" in str(policy):
            scores["legal_grounding"] = 0.9
        elif len(str(policy)) > 10:
            scores["legal_grounding"] = 0.6
        else:
            scores["legal_grounding"] = 0.2
            issues.append("缺少具体法律条款引用")
        
        # 4. 建议可操作性
        suggestion = finding.get("suggestion", "")
        if "①" in suggestion or "1." in suggestion:
            scores["actionability"] = 0.9
        elif len(suggestion) > 30:
            scores["actionability"] = 0.6
        else:
            scores["actionability"] = 0.3
            issues.append("行动建议过于笼统")
        
        # 综合质量分
        quality = sum(scores.values()) / max(len(scores), 1)
        
        return {
            "finding_type": finding.get("type", ""),
            "quality_score": round(quality, 3),
            "dimension_scores": scores,
            "issues": issues,
            "verdict": "优秀" if quality >= 0.8 else ("良好" if quality >= 0.6 else ("一般" if quality >= 0.4 else "需改进")),
        }
    
    def detect_uncertainty(self, findings: List[Dict]) -> List[Dict]:
        """检测哪些结论系统自己不确定"""
        uncertain = []
        for f in findings:
            q = self.evaluate_reasoning_quality(f)
            if q["quality_score"] < self.uncertainty_threshold + 0.3:
                uncertain.append({
                    "finding_type": q["finding_type"],
                    "quality_score": q["quality_score"],
                    "issues": q["issues"],
                    "suggestion": "建议获取更多信息以确认该结论",
                })
        return uncertain
    
    def identify_information_gaps(self, findings: List[Dict]) -> List[Dict]:
        """识别信息缺口 —— 为了更确定还需要什么数据"""
        gaps = []
        all_text = " ".join([
            str(f.get("how_found", "")) + str(f.get("description", "")) + str(f.get("detail", ""))
            for f in findings
        ]).lower()
        
        for pattern in self.gap_patterns:
            if any(kw in all_text for kw in pattern["keywords"]):
                gaps.append({
                    "gap_type": pattern["pattern"],
                    "missing_info": pattern["missing"],
                    "impact_on_confidence": pattern["impact"],
                    "suggestion": f"获取{pattern['missing']}可提升结论置信度约{int(pattern['impact']*100)}%",
                })
        
        return gaps
    
    def metacognitive_report(self, findings: List[Dict], agent_result: Dict = None) -> Dict:
        """生成元认知报告"""
        # 逐一评估
        quality_evaluations = [self.evaluate_reasoning_quality(f) for f in findings]
        
        # 统计
        avg_quality = sum(q["quality_score"] for q in quality_evaluations) / max(len(quality_evaluations), 1)
        good_count = sum(1 for q in quality_evaluations if q["verdict"] in ("优秀", "良好"))
        weak_count = sum(1 for q in quality_evaluations if q["verdict"] in ("一般", "需改进"))
        
        # 不确定性检测
        uncertain = self.detect_uncertainty(findings)
        
        # 信息缺口
        gaps = self.identify_information_gaps(findings)
        
        # 自我反思质量
        reflection_quality = "优秀" if avg_quality >= 0.7 else ("良好" if avg_quality >= 0.5 else "需改进")
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "overall_quality": round(avg_quality, 3),
            "quality_verdict": reflection_quality,
            "distribution": {"优秀+良好": good_count, "一般+需改进": weak_count},
            "uncertain_findings": uncertain[:5],
            "information_gaps": gaps,
            "action_items": [],
        }
        
        # 生成行动建议
        if avg_quality < 0.5:
            report["action_items"].append("整体推理质量偏低，建议补充更多原始资料后重新分析")
        if len(uncertain) > len(findings) * 0.3:
            report["action_items"].append(f"超过30%的结论存在不确定性({len(uncertain)}/{len(findings)})，建议人工复核")
        if len(gaps) >= 3:
            report["action_items"].append(f"发现{len(gaps)}个信息缺口，补充后可显著提升分析质量")
        
        # 记录推理日志
        self.reasoning_log.append({
            "timestamp": report["timestamp"],
            "avg_quality": avg_quality,
            "findings_count": len(findings),
            "issues": sum(len(q["issues"]) for q in quality_evaluations),
        })
        
        return report


# ── 全局单例 ──
metacog = MetacognitionEngine()

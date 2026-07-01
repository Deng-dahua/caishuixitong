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
import json, os
from datetime import datetime
from typing import List, Dict


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
        
        # 记录推理日志，持久化用于跨运行比较
        self.reasoning_log.append({
            "timestamp": report["timestamp"],
            "avg_quality": avg_quality,
            "findings_count": len(findings),
            "issues": sum(len(q["issues"]) for q in quality_evaluations),
        })
        self._persist_log()
        
        # ═══ 自知增强：六维能力自评分 ═══
        report["agi_capability_scores"] = self._score_capabilities(findings, avg_quality)
        report["vs_baseline"] = self._compare_to_baseline(avg_quality, len(findings))
        report["anomalies"] = self._detect_anomalies(quality_evaluations)
        
        return report
    
    def _score_capabilities(self, findings, avg_quality):
        """六维能力自评分（自知层核心）"""
        has_correction_rules = os.path.exists(
            os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "user_corrections.json"))
        has_memory = len(self.reasoning_log) > 1
        total_findings = len(findings)
        high_risk = sum(1 for f in findings if f.get("level") in ("高风险","极高风险"))
        has_evidence = sum(1 for f in findings if f.get("items") or f.get("evidence"))
        has_law = sum(1 for f in findings if "第" in str(f.get("policy_ref","")) and "条" in str(f.get("policy_ref","")))
        
        return {
            "记忆": min(0.95, 0.6 + 0.15 * has_memory + 0.1 * min(total_findings/50, 1)),
            "学习": min(0.95, 0.5 + 0.3 * has_correction_rules + 0.15 * min(len(self.reasoning_log)/5, 1)),
            "思考": min(0.95, 0.5 + 0.2 * min(has_evidence/total_findings, 1) if total_findings else 0.5),
            "判断": min(0.95, 0.6 + 0.2 * min(has_law/total_findings, 1) + 0.1 * avg_quality),
            "决策": min(0.95, 0.5 + 0.25 * min(high_risk/5, 1) + 0.2 * avg_quality),
            "自知": min(0.95, 0.4 + 0.3 * has_memory + 0.15 * avg_quality),
        }
    
    def _compare_to_baseline(self, current_quality, current_count):
        """与历史基线比较（自知的核心：我知道自己进步了还是退步了）"""
        if len(self.reasoning_log) < 2:
            return {"status": "baseline", "message": "首轮分析，无历史基线可对比"}
        
        prev = [r for r in self.reasoning_log[:-1]]
        avg_prev_quality = sum(r["avg_quality"] for r in prev) / len(prev)
        avg_prev_count = sum(r["findings_count"] for r in prev) / len(prev)
        
        q_change = current_quality - avg_prev_quality
        c_change = current_count - avg_prev_count
        
        status = "improving" if q_change > 0.05 else ("declining" if q_change < -0.05 else "stable")
        return {
            "status": status,
            "current_quality": round(current_quality, 3),
            "baseline_quality": round(avg_prev_quality, 3),
            "quality_delta": round(q_change, 3),
            "finding_count_delta": int(c_change),
            "total_runs": len(self.reasoning_log),
            "message": f"推理质量{'提升' if status=='improving' else ('下降' if status=='declining' else '稳定')}（当前{current_quality:.2f} vs 基线{avg_prev_quality:.2f}）"
        }
    
    def _detect_anomalies(self, quality_evaluations):
        """检测异常：突然出现大量低质量结论"""
        anomalies = []
        very_low = [q for q in quality_evaluations if q["quality_score"] < 0.2]
        if len(very_low) > 3:
            anomalies.append(f"检测到{len(very_low)}条极低质量结论（<0.2），可能数据源存在问题")
        
        # 检查评分方差（过高方差=不稳定）
        scores = [q["quality_score"] for q in quality_evaluations]
        if len(scores) > 5:
            avg = sum(scores) / len(scores)
            variance = sum((s - avg) ** 2 for s in scores) / len(scores)
            if variance > 0.15:
                anomalies.append(f"结论质量方差过大（{variance:.3f}），引擎输出不够稳定")
        
        return anomalies
    
    def _persist_log(self):
        """持久化推理日志，跨运行保留"""
        try:
            log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "metacognition_log.json")
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(self.reasoning_log[-20:], f, ensure_ascii=False, indent=2)
        except:
            pass


# ── 全局单例 ──
metacog = MetacognitionEngine()

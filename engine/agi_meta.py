"""
AGI自审引擎 — 报告质量自审 + 规则自动调整闭环

AGI审查自己生成的报告，发现问题后自动调整规则，下次分析更准确。
这是AGI最核心的能力：自我反思 → 自我改进。
"""
import json, os, math, hashlib
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Any, Optional, Tuple


class ReportAuditor:
    """报告质量自审引擎 — AGI审查自己的输出"""
    
    # 自审维度
    AUDIT_DIMENSIONS = {
        "证据充分性": {
            "weight": 0.25,
            "checks": [
                "每条高风险发现是否≥2条证据",
                "每条发现是否标注了证据来源",
                "证据是否来自≥2个不同的数据域",
                "是否有仅凭单一数据源做出的重大判断",
            ],
        },
        "法条准确性": {
            "weight": 0.20,
            "checks": [
                "引用的法条是否为现行有效版本",
                "是否存在用旧法条代替新法条的情况",
                "法条引用是否精确到条/款",
                "是否引用了已废止的法规(如增值税暂行条例)",
            ],
        },
        "逻辑一致性": {
            "weight": 0.20,
            "checks": [
                "同一笔交易是否触发了所有应触发的税种",
                "风险等级与发现数量/性质是否匹配",
                "高风险发现是否有对应的高影响建议",
                "结论是否与证据方向一致(无矛盾)",
            ],
        },
        "覆盖面完整性": {
            "weight": 0.15,
            "checks": [
                "是否覆盖了所有可用的分析域",
                "是否有明显的分析盲区未标注",
                "缺失资料的影响是否在报告中体现",
                "是否考虑了企业生命周期阶段的特殊性",
            ],
        },
        "可操作性": {
            "weight": 0.10,
            "checks": [
                "处理建议是否具体可执行",
                "金额计算是否有明确的计算公式",
                "是否有明确的资料补充指引",
                "修改建议是否有量化指标",
            ],
        },
        "表达质量": {
            "weight": 0.10,
            "checks": [
                "是否存在模糊表述(如'可能''大概'而无量化)",
                "专业术语使用是否准确",
                "数值是否全部标注了单位",
                "是否有信息冗余或重复",
            ],
        },
    }
    
    def __init__(self):
        self._audits: List[Dict] = []
        self._load()
    
    def _load(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "report_audits.json")
        try:
            with open(path, encoding="utf-8") as f:
                self._audits = json.load(f)
        except:
            self._audits = []
    
    def _save(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "report_audits.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._audits[-50:], f, ensure_ascii=False, indent=2)
    
    def audit(self, findings: List[Dict], company: Dict, materials: Dict = None) -> Dict:
        """
        自审一份报告
        
        返回: 各维度评分 + 发现的问题 + 改进建议 + 逐条发现审核
        """
        dimension_scores = {}
        all_issues = []
        
        # ── 0. 逐条发现深度审核 ──
        per_finding_audits = []
        for i, f in enumerate(findings):
            pfa = self._audit_finding(f, i+1, company)
            per_finding_audits.append(pfa)
            all_issues.extend(pfa["issues"])
        
        for dim_name, dim_config in self.AUDIT_DIMENSIONS.items():
            issues = self._check_dimension(dim_name, dim_config["checks"], findings, company, materials)
            score = max(0, 1.0 - len(issues) * 0.15)
            dimension_scores[dim_name] = {
                "score": round(score, 2),
                "issues": issues,
                "status": "通过" if score >= 0.7 else ("需改进" if score >= 0.4 else "不合格"),
            }
            all_issues.extend(issues)
        
        # 加权总分
        weighted = sum(
            dimension_scores[d]["score"] * self.AUDIT_DIMENSIONS[d]["weight"]
            for d in self.AUDIT_DIMENSIONS
        )
        
        # 按严重程度分类问题
        critical = [i for i in all_issues if i["severity"] == "严重"]
        warning = [i for i in all_issues if i["severity"] == "警告"]
        info = [i for i in all_issues if i["severity"] == "提示"]
        
        audit_record = {
            "timestamp": datetime.now().isoformat(),
            "company": company.get("name", ""),
            "finding_count": len(findings),
            "overall_score": round(weighted, 2),
            "dimensions": dimension_scores,
            "critical_count": len(critical),
            "warning_count": len(warning),
            "grade": "A" if weighted >= 0.85 else ("B" if weighted >= 0.7 else ("C" if weighted >= 0.5 else "D")),
        }
        
        self._audits.append(audit_record)
        self._save()
        
        return {
            **audit_record,
            "per_finding_audits": per_finding_audits,
            "valid_findings": sum(1 for p in per_finding_audits if p["verdict"] == "成立"),
            "questionable_findings": sum(1 for p in per_finding_audits if p["verdict"] != "成立"),
            "critical_issues": critical[:5],
            "warnings": warning[:5],
            "suggestions": self._generate_suggestions(critical, warning),
            "auto_adjustments": self._generate_adjustments(critical, findings),
        }
    
    def _audit_finding(self, f: Dict, idx: int, company: Dict) -> Dict:
        """逐条深度审核：这个发现是否成立？文字是否准确？"""
        issues = []
        ftype = f.get("type", "未命名")
        flevel = f.get("level", "")
        fdetail = f.get("detail", f.get("description", ""))
        fhow = f.get("how_found", "")
        fpolicy = f.get("policy_ref", "")
        ev = f.get("evidence", []) or f.get("evidence_rows", []) or f.get("items", []) or []
        
        # ── 文字质量检查 ──
        # 1. 模糊表述
        vague_count = sum(1 for w in ["可能", "大概", "也许", "似乎", "好像", "或许", "大约"] if w in (fdetail or ""))
        if vague_count >= 2:
            issues.append({"type": "文字质量", "severity": "提示",
                          "detail": f"含{vague_count}处模糊表述，建议用定量数据替代", "fix": "用具体数字和百分比替代模糊词"})
        if vague_count >= 4:
            issues.append({"type": "文字质量", "severity": "警告",
                          "detail": f"表述过于模糊({vague_count}处)，严重影响判断可信度", "fix": "需要大幅改写，提供更精确的数据"})
        
        # 2. 术语准确性
        if "暂行条例" in (fpolicy or "") and "增值税" in (fpolicy or ""):
            issues.append({"type": "法条错误", "severity": "严重",
                          "detail": "引用了已废止的《增值税暂行条例》，应使用2024年1月1日施行的《增值税法》", 
                          "fix": "替换为《中华人民共和国增值税法》"})
        
        # 3. 数值规范性
        import re
        nums = re.findall(r'\d+\.?\d*', fdetail or "")
        if nums and not any(u in (fdetail or "") for u in ["万元", "元", "%", "倍", "张", "笔"]):
            issues.append({"type": "表达质量", "severity": "提示",
                          "detail": "数值未带单位，可能导致理解歧义", "fix": "为所有数值添加单位（万元/元/%等）"})
        
        # ── 逻辑有效性检查 ──
        # 4. 证据与结论的一致性
        if flevel in ("高风险", "极高风险") and len(ev) < 2:
            issues.append({"type": "逻辑有效性", "severity": "警告",
                          "detail": f"高风险发现仅有{len(ev)}条证据，结论与证据强度不匹配",
                          "fix": "降级至中风险，或补充≥2个独立数据源的证据"})
        
        # 5. 是否有how_found
        if not (fhow or "").strip():
            issues.append({"type": "逻辑有效性", "severity": "警告",
                          "detail": "缺少发现方法(how_found)，无法追溯判定依据", "fix": "补充判定方法和数据来源描述"})
        
        # 6. 证据描述是否具体
        has_specific_evidence = any(
            isinstance(ei, dict) and (ei.get("amount") or ei.get("counterparty") or ei.get("date"))
            for ei in ev[:3]
        ) if ev else False
        
        if ev and not has_specific_evidence and flevel in ("高风险", "极高风险"):
            issues.append({"type": "逻辑有效性", "severity": "提示",
                          "detail": "证据行缺少金额/对方/日期等关键信息", "fix": "补充证据行的具体数据字段"})
        
        # ── 结论判定 ──
        severe = [i for i in issues if i["severity"] == "严重"]
        warnings = [i for i in issues if i["severity"] == "警告"]
        
        if severe:
            verdict = "存疑——存在严重问题需要修正"
            verdict_color = "#dc2626"
        elif len(warnings) >= 2:
            verdict = "基本成立——有警告需要关注"
            verdict_color = "#d97706"
        elif warnings:
            verdict = "成立——有小问题"
            verdict_color = "#f59e0b"
        else:
            verdict = "成立"
            verdict_color = "#16a34a"
        
        return {
            "index": idx,
            "type": ftype[:60],
            "level": flevel,
            "verdict": verdict,
            "verdict_color": verdict_color,
            "issues": issues,
            "issue_count": len(issues),
            "severe_count": len(severe),
            "warning_count": len(warnings),
            "score": round(max(0, 1.0 - len(issues) * 0.15), 2),
        }
    
    def _check_dimension(self, dim_name: str, checks: List[str], findings: List[Dict],
                         company: Dict, materials: Dict = None) -> List[Dict]:
        """按维度逐项检查"""
        issues = []
        
        if dim_name == "证据充分性":
            for i, f in enumerate(findings):
                ev = f.get("evidence", []) or f.get("evidence_rows", []) or f.get("items", []) or []
                if f.get("level") in ("高风险", "极高风险") and len(ev) < 2:
                    issues.append({
                        "dimension": dim_name,
                        "finding_index": i,
                        "finding_type": f.get("type", "")[:40],
                        "issue": f"高风险发现#{i+1}仅{len(ev)}条证据",
                        "severity": "严重",
                        "fix": "需补充至少1个额外数据源的证据",
                    })
                if not f.get("how_found", "").strip():
                    issues.append({
                        "dimension": dim_name,
                        "finding_index": i,
                        "finding_type": f.get("type", "")[:40],
                        "issue": f"发现#{i+1}缺少证据来源(hw_found)",
                        "severity": "警告",
                        "fix": "补充how_found字段说明分析方法",
                    })
        
        elif dim_name == "法条准确性":
            for i, f in enumerate(findings):
                policy = f.get("policy_ref", "") or ""
                if "暂行条例" in policy and "增值税" in policy:
                    issues.append({
                        "dimension": dim_name,
                        "finding_index": i,
                        "finding_type": f.get("type", "")[:40],
                        "issue": f"发现#{i+1}引用了已废止的《增值税暂行条例》",
                        "severity": "严重",
                        "fix": "替换为《中华人民共和国增值税法》(2024.1.1施行)",
                    })
                if not policy.strip() and f.get("level") in ("高风险", "极高风险"):
                    issues.append({
                        "dimension": dim_name,
                        "finding_index": i,
                        "finding_type": f.get("type", "")[:40],
                        "issue": f"高风险发现#{i+1}缺少法律依据",
                        "severity": "警告",
                        "fix": "补充引用的法律条文",
                    })
        
        elif dim_name == "逻辑一致性":
            # 检查跨税种盲区
            all_types = set(f.get("type", "") for f in findings)
            if any("增值税" in t or "收入" in t or "收款" in t for t in all_types):
                if not any("城建税" in t or "附加" in t for t in all_types):
                    issues.append({
                        "dimension": dim_name,
                        "issue": "检测到增值税问题但未包含城建税及附加检查",
                        "severity": "警告",
                        "fix": "涉及增值税的问题应同时检查城建税(7%)+教育费附加(3%+2%)",
                    })
                if not any("所得税" in t for t in all_types):
                    issues.append({
                        "dimension": dim_name,
                        "issue": "检测到增值税问题但未包含企业所得税检查",
                        "severity": "提示",
                        "fix": "收入/发票问题通常同时影响企业所得税",
                    })
        
        elif dim_name == "覆盖面完整性":
            # 资料缺口检查
            if isinstance(materials, dict):
                missing = [k for k, v in materials.items() if isinstance(v, dict) and not v.get("exists", True)]
                if missing and not any("资料" in f.get("type","") for f in findings):
                    issues.append({
                        "dimension": dim_name,
                        "issue": f"缺失{len(missing)}类资料但报告中未见资料完备度分析",
                        "severity": "警告",
                        "fix": f"在报告中增加资料缺口影响分析: {', '.join(missing[:3])}",
                    })
        
        elif dim_name == "表达质量":
            vague_words = ["可能", "大概", "也许", "似乎"]
            for i, f in enumerate(findings[:3]):
                detail = f.get("detail", "") or ""
                vague_count = sum(1 for w in vague_words if w in detail)
                if vague_count >= 2:
                    issues.append({
                        "dimension": dim_name,
                        "finding_index": i,
                        "finding_type": f.get("type", "")[:40],
                        "issue": f"发现#{i+1}描述中含{vague_count}处模糊表述",
                        "severity": "提示",
                        "fix": "用具体数据和量化指标替代模糊表述",
                    })
        
        return issues
    
    def _generate_suggestions(self, critical: List, warning: List) -> List[str]:
        suggestions = []
        if critical:
            suggestions.append(f"🔴 有{len(critical)}个严重问题需要立即修正。")
        if warning:
            suggestions.append(f"🟡 有{len(warning)}个警告级别问题建议修正。")
        suggestions.append("建议修正后重新运行AGI自审，直至评分≥0.85(A级)。")
        return suggestions
    
    def _generate_adjustments(self, critical: List, findings: List[Dict]) -> List[Dict]:
        """根据自审发现的问题生成规则调整建议"""
        adjustments = []
        
        for issue in critical:
            adj = {
                "trigger": issue["issue"],
                "dimension": issue["dimension"],
                "action": self._map_issue_to_action(issue),
                "target": issue.get("finding_type", ""),
                "auto_apply": issue["severity"] == "严重",
            }
            adjustments.append(adj)
        
        return adjustments
    
    def _map_issue_to_action(self, issue: Dict) -> str:
        dim = issue["dimension"]
        if dim == "法条准确性":
            return "自动替换已废止的法条引用为现行有效版本"
        if dim == "证据充分性":
            return "降低证据不足的高风险发现权重，标注'证据薄弱'"
        if dim == "逻辑一致性":
            return "在生成报告时自动追加跨税种影响分析"
        return "标记该问题供人工复核"


class RuleAutoAdjuster:
    """规则自动调整器 — 基于自审结果自动修改推理规则"""
    
    def __init__(self):
        self._adjustments: List[Dict] = []
        self._load()
    
    def _load(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "rule_adjustments.json")
        try:
            with open(path, encoding="utf-8") as f:
                self._adjustments = json.load(f)
        except:
            self._adjustments = []
    
    def _save(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "rule_adjustments.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._adjustments[-100:], f, ensure_ascii=False, indent=2)
    
    def apply_adjustments(self, audit_result: Dict) -> Dict:
        """根据自审结果生成并应用规则调整"""
        adjustments = audit_result.get("auto_adjustments", [])
        applied = []
        
        for adj in adjustments:
            if adj.get("auto_apply"):
                rule_id = hashlib.md5(
                    f"{adj['trigger']}:{adj['action']}".encode()
                ).hexdigest()[:8]
                
                adjustment_record = {
                    "id": f"ADJ-{len(self._adjustments)+1:04d}",
                    "rule_id": rule_id,
                    "trigger": adj["trigger"],
                    "action": adj["action"],
                    "target": adj.get("target", ""),
                    "dimension": adj["dimension"],
                    "applied_at": datetime.now().isoformat(),
                    "applied_count": 0,
                    "status": "active",
                }
                
                # 检查是否已有同类调整
                existing = [a for a in self._adjustments if a.get("rule_id") == rule_id]
                if existing:
                    existing[0]["applied_count"] += 1
                else:
                    self._adjustments.append(adjustment_record)
                
                applied.append(adjustment_record)
        
        self._save()
        return {
            "total_adjustments": len(self._adjustments),
            "newly_applied": len(applied),
            "active_rules": len([a for a in self._adjustments if a.get("status") == "active"]),
            "adjustments": applied,
        }
    
    def get_active_rules(self) -> List[Dict]:
        """获取当前活跃的规则调整"""
        return [a for a in self._adjustments if a.get("status") == "active"]
    
    def summarize_impact(self) -> Dict:
        """总结规则调整的整体影响"""
        # 按维度统计
        by_dimension = defaultdict(int)
        for a in self._adjustments:
            by_dimension[a.get("dimension", "未知")] += 1
        
        return {
            "total_adjustments": len(self._adjustments),
            "by_dimension": dict(by_dimension),
            "most_improved": max(by_dimension, key=by_dimension.get) if by_dimension else "无",
            "latest": self._adjustments[-1] if self._adjustments else None,
            "evolution": f"系统至今已自动调整{len(self._adjustments)}次规则，主要改进集中在{max(by_dimension, key=by_dimension.get) if by_dimension else '无'}维度。",
        }


class AGIMetaLoop:
    """AGI元认知闭环 — 自审 → 调整 → 再分析 → 对比 → 进化"""
    
    def __init__(self):
        self._auditor = ReportAuditor()
        self._adjuster = RuleAutoAdjuster()
        self._history: List[Dict] = []
    
    def run(self, findings: List[Dict], company: Dict, materials: Dict = None) -> Dict:
        """
        执行完整的AGI自审+调整闭环
        
        1. 自审报告质量
        2. 生成规则调整
        3. 应用调整
        4. 记录对比基准
        """
        # 1. 自审
        audit = self._auditor.audit(findings, company, materials)
        
        # 2. 生成调整
        adj_result = self._adjuster.apply_adjustments(audit)
        
        # 3. 记录循环
        loop_record = {
            "timestamp": datetime.now().isoformat(),
            "company": company.get("name", ""),
            "audit_score": audit["overall_score"],
            "audit_grade": audit["grade"],
            "critical_issues": audit["critical_count"],
            "adjustments_applied": adj_result["newly_applied"],
            "effects": self._analyze_effects(audit, adj_result),
        }
        
        self._history.append(loop_record)
        if len(self._history) > 50:
            self._history = self._history[-50:]
        
        return {
            "ok": True,
            "audit": audit,
            "adjustments": adj_result,
            "meta_analysis": {
                "score": audit["overall_score"],
                "grade": audit["grade"],
                "improvement": self._estimate_improvement(),
                "next_action": (
                    "报告已自审完毕，建议修正严重问题后重新分析" if audit["critical_count"] > 0
                    else "报告质量达标，下次分析将应用新的调整规则"
                ),
            },
        }
    
    def _analyze_effects(self, audit: Dict, adj_result: Dict) -> str:
        if adj_result["newly_applied"] > 0:
            return f"本次自审发现{audit['critical_count']}个严重问题，已自动生成{adj_result['newly_applied']}条规则调整。"
        return "未发现需要自动调整的严重问题。"
    
    def _estimate_improvement(self) -> Dict:
        if len(self._history) < 2:
            return {"status": "首次自审，无历史对比"}
        
        prev = self._history[-2]
        curr = self._history[-1]
        
        score_change = curr["audit_score"] - prev["audit_score"]
        issue_change = curr["critical_issues"] - prev["critical_issues"]
        
        return {
            "score_trend": "上升" if score_change > 0 else ("下降" if score_change < 0 else "持平"),
            "score_delta": round(score_change, 2),
            "issue_trend": "减少" if issue_change < 0 else ("增加" if issue_change > 0 else "持平"),
            "evolution": "AGI在自我改进" if score_change > 0 or issue_change < 0 else "质量稳定" if score_change == 0 else "需关注",
        }
    
    def get_status(self) -> Dict:
        return {
            "total_loops": len(self._history),
            "average_score": round(sum(h["audit_score"] for h in self._history) / max(len(self._history), 1), 2),
            "active_adjustments": self._adjuster.summarize_impact(),
            "latest": self._history[-1] if self._history else None,
        }


# 全局元认知闭环
meta_loop = AGIMetaLoop()

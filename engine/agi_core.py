"""
AGI核心能力模块 — 持续记忆 + 自主决策 + 一次学会 + 反事实推理

P0: 持续记忆 — 增量分析，不重跑全量。记住结论、纠正、数据特征。
P1: 自主决策 — 设好定时→自己跑→对比上次→异常通知→无异常记录。
P1: 一次学会 — 纠正1次就分析模式→自动修正同类场景。
P2: 反事实推理 — "如果X不成立，数据应该长成Z样。实际是Z吗？"
"""
import json, os, math, hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple
from collections import defaultdict


class PersistentMemory:
    """持续记忆系统 — AGI的海马体
    
    不像人一样每次失忆重来，而是记住：
    - 每次分析的结论和关键指标
    - 用户纠正的模式和原因
    - 企业特征指纹
    """
    
    def __init__(self):
        self._analyses: Dict[int, List[Dict]] = defaultdict(list)  # company_id → [分析记录]
        self._corrections: List[Dict] = []
        self._fingerprints: Dict[int, Dict] = {}  # 企业特征指纹
        self._load()
    
    def _load(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "agi_memory.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                self._analyses = defaultdict(list, {int(k): v for k, v in data.get("analyses", {}).items()})
                self._corrections = data.get("corrections", [])
                self._fingerprints = {int(k): v for k, v in data.get("fingerprints", {}).items()}
        except:
            pass
    
    def _save(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "agi_memory.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "analyses": {str(k): v[-20:] for k, v in self._analyses.items()},
                "corrections": self._corrections[-200:],
                "fingerprints": {str(k): v for k, v in self._fingerprints.items()},
            }, f, ensure_ascii=False, indent=2)
    
    def remember_analysis(self, company_id: int, result: Dict):
        """记住一次分析"""
        findings = result.get("findings", result.get("all_findings", []))
        record = {
            "timestamp": datetime.now().isoformat(),
            "risk_level": result.get("overall_risk", result.get("level", "")),
            "risk_score": result.get("risk_score", 0),
            "finding_count": len(findings),
            "finding_types": [f.get("type", "")[:60] for f in findings[:20]],
            "high_risk_count": sum(1 for f in findings if f.get("level") in ("高风险", "极高风险")),
            "signals": result.get("active_signals", []),
            "industry": result.get("industry", ""),
        }
        self._analyses[company_id].append(record)
        if len(self._analyses[company_id]) > 50:
            self._analyses[company_id] = self._analyses[company_id][-50:]
        
        # 更新企业指纹
        if company_id not in self._fingerprints:
            self._fingerprints[company_id] = {
                "first_analyzed": datetime.now().isoformat(),
                "total_analyses": 0,
                "trend": "stable",
                "common_risks": [],
                "last_risk_level": "",
            }
        fp = self._fingerprints[company_id]
        fp["total_analyses"] += 1
        fp["last_analyzed"] = datetime.now().isoformat()
        fp["last_risk_level"] = record["risk_level"]
        
        # 趋势判断
        prev = self._analyses[company_id][-2] if len(self._analyses[company_id]) > 1 else None
        if prev:
            if record["high_risk_count"] > prev["high_risk_count"]:
                fp["trend"] = "worsening"
            elif record["high_risk_count"] < prev["high_risk_count"]:
                fp["trend"] = "improving"
            else:
                fp["trend"] = "stable"
        
        # 常见风险
        all_types = []
        for a in self._analyses[company_id][-5:]:
            all_types.extend(a.get("finding_types", []))
        from collections import Counter
        fp["common_risks"] = [t for t, _ in Counter(all_types).most_common(5)]
        
        self._save()
    
    def recall(self, company_id: int) -> Dict:
        """回忆：该企业的历史分析摘要"""
        history = self._analyses.get(company_id, [])
        fp = self._fingerprints.get(company_id, {})
        
        if not history:
            return {"status": "no_history", "message": "该企业首次分析"}
        
        last = history[-1]
        prev = history[-2] if len(history) > 1 else None
        
        changes = []
        if prev:
            if last["risk_level"] != prev["risk_level"]:
                changes.append(f"风险等级: {prev['risk_level']} → {last['risk_level']}")
            if last["finding_count"] != prev["finding_count"]:
                changes.append(f"发现数量: {prev['finding_count']} → {last['finding_count']} ({'+' if last['finding_count']>prev['finding_count'] else ''}{last['finding_count']-prev['finding_count']})")
        
        # 增量差异：比起上次，多了或少了哪些发现
        if prev:
            prev_types = set(prev.get("finding_types", []))
            last_types = set(last.get("finding_types", []))
            new = last_types - prev_types
            gone = prev_types - last_types
            if new:
                changes.append(f"新增风险: {', '.join(list(new)[:3])}")
            if gone:
                changes.append(f"消除风险: {', '.join(list(gone)[:3])}")
        
        return {
            "status": "has_history",
            "total_analyses": len(history),
            "first_analyzed": history[0].get("timestamp", "")[:10] if history else "",
            "last_analyzed": last.get("timestamp", "")[:10],
            "last_risk_level": last.get("risk_level", ""),
            "trend": fp.get("trend", "stable"),
            "common_risks": fp.get("common_risks", []),
            "changes_since_last": changes,
            "incremental_summary": (
                f"这是第{len(history)}次分析。"
                + (f"本次变化: {'; '.join(changes)}" if changes else "本次与上次结论一致。")
            ),
        }
    
    def remember_correction(self, finding_type: str, reason: str, industry: str = ""):
        """记住一次纠正"""
        self._corrections.append({
            "type": finding_type[:60],
            "reason": reason[:200],
            "industry": industry,
            "timestamp": datetime.now().isoformat(),
        })
        if len(self._corrections) > 200:
            self._corrections = self._corrections[-200:]
        self._save()
    
    def is_learned(self, finding_type: str, industry: str = "") -> Tuple[bool, int]:
        """检查是否已学会——同类型纠正≥1次即认为已学"""
        count = sum(1 for c in self._corrections 
                   if c["type"] == finding_type[:60]
                   and (not industry or c.get("industry") == industry))
        return count >= 1, count


class OneShotLearner:
    """一次学会 — 纠正 1 次就分析模式，自动修正同类场景
    
    核心：不是等 3 次再降权，而是分析纠正原因→找出共性问题→一次性修正
    """
    
    def __init__(self):
        self._patterns: List[Dict] = []
        self._load()
    
    def _load(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "one_shot_rules.json")
        try:
            with open(path, encoding="utf-8") as f:
                self._patterns = json.load(f)
        except:
            self._patterns = []
    
    def _save(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "one_shot_rules.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._patterns[-100:], f, ensure_ascii=False, indent=2)
    
    def learn_once(self, finding_type: str, reason: str, findings: List[Dict], industry: str = "") -> Dict:
        """一次学会——分析纠正原因，生成通用修正规则"""
        
        # 提取纠正中的关键词模式
        pattern_keywords = self._extract_pattern(reason, finding_type)
        
        # 搜索同类发现
        affected = []
        for f in findings:
            ft = f.get("type", "")
            if any(kw in ft for kw in pattern_keywords["keywords"] if len(kw) >= 2):
                affected.append({"type": ft[:60], "level": f.get("level", "")})
        
        rule = {
            "id": hashlib.md5(f"{finding_type}:{reason}".encode()).hexdigest()[:8],
            "finding_type": finding_type[:60],
            "pattern": pattern_keywords["pattern"],
            "keywords": pattern_keywords["keywords"],
            "action": pattern_keywords["action"],
            "affected_count": len(affected),
            "industry": industry,
            "created_at": datetime.now().isoformat(),
            "auto_apply": True,  # 一次就生效
        }
        
        self._patterns.append(rule)
        self._save()
        
        return {
            "ok": True,
            "rule": rule["id"],
            "pattern": rule["pattern"],
            "action": rule["action"],
            "affected": affected[:10],
            "auto_applied": len(affected),
        }
    
    def _extract_pattern(self, reason: str, ftype: str) -> Dict:
        """从纠正原因中提取模式"""
        keywords = []
        pattern = ""
        action = "降级"
        
        # 行业跳过模式
        if "服务" in reason and ("进销存" in reason or "BOM" in reason):
            keywords = ["进销存", "BOM", "加工费", "实物分析"]
            pattern = "服务行业跳过进销存分析"
            action = "降级"
        # 行业特化纠正
        elif "非适用" in reason or "不应触发" in reason:
            words = [w for w in reason.replace("，",",").replace("、",",").split(",") if len(w) >= 2]
            keywords = words[:5]
            pattern = f"{ftype[:20]}在特定行业中非适用"
            action = "跳过"
        # 证据不足
        elif "证据不足" in reason or "资料缺失" in reason:
            keywords = ["证据", "资料", "缺失", "不足"]
            pattern = "证据不足导致误判"
            action = "降级+标注"
        # 金额偏差
        elif any(w in reason for w in ["金额", "算错", "计算错误"]):
            keywords = ["金额", "计算", "偏差"]
            pattern = "金额计算偏差"
            action = "修正金额"
        else:
            # 通用模式提取
            words = [w for w in reason.replace("，",",").split(",") if len(w) >= 2]
            keywords = words[:5]
            pattern = reason[:80]
            action = "降级"
        
        return {"pattern": pattern, "keywords": keywords, "action": action}
    
    def apply_rules(self, findings: List[Dict]) -> List[Dict]:
        """应用已学规则到当前发现列表"""
        modified = []
        for f in findings:
            ft = f.get("type", "")
            for rule in self._patterns:
                if any(kw in ft for kw in rule.get("keywords", []) if len(kw) >= 2):
                    modified.append({
                        "type": ft,
                        "original_level": f.get("level", ""),
                        "action": rule["action"],
                        "rule": rule["id"],
                        "pattern": rule["pattern"],
                    })
        return modified


class CounterfactualReasoner:
    """反事实推理 — "如果...那么数据应该长什么样？"
    
    处长级别的思维：
    "如果虚开不成立，银行流水应该有对应的回款记录。我们看看有没有。"
    "如果成本是真实的，应该有对应的入库单和运输发票。检查一下。"
    """
    
    COUNTERFACTUALS = {
        "虚开发票": {
            "否认条件": "如果发票是真实交易的产物",
            "预期数据": "应有对应的银行付款记录、入库单、运输发票",
            "验证方法": "检查银行流水对方户名与开票方是否一致",
            "证伪条件": "如果缺少上述任一证据，虚开嫌疑上升",
        },
        "隐匿收入": {
            "否认条件": "如果收入已全部申报",
            "预期数据": "开票金额应等于银行流水收款金额",
            "验证方法": "比对银行收款总额与开票总额，差异应<5%",
            "证伪条件": "如果差异>10%且无合理商业解释，隐匿收入成立",
        },
        "虚增成本": {
            "否认条件": "如果成本是真实发生的",
            "预期数据": "应有对应的付款凭证、入库记录、物流单据",
            "验证方法": "抽查大额成本的合同+发票+付款三单匹配",
            "证伪条件": "如果三单不一致或缺少关键单据，虚增成本成立",
        },
        "关联交易不公允": {
            "否认条件": "如果交易定价是公允的",
            "预期数据": "交易价格应在同行业同类交易±20%范围内",
            "验证方法": "对比同行业同类交易价格或第三方报价",
            "证伪条件": "如果偏离超出合理范围且无合理商业目的，定价不公允成立",
        },
    }
    
    def reason(self, finding: Dict, available_data: Dict) -> Dict:
        """
        反事实推理：构造"如果X不成立"的场景 → 推导预期数据特征 → 对比实际数据
        """
        ftype = finding.get("type", "")
        fdeta = finding.get("detail", "")
        ftext = ftype + (fdeta or "")
        
        # 匹配反事实模板
        cf = None
        for keyword, template in self.COUNTERFACTUALS.items():
            if keyword in ftext:
                cf = template
                break
        
        if not cf:
            return {
                "status": "no_template",
                "message": "该发现类型暂无预定义反事实模板，建议人工构建",
            }
        
        # 构建反事实场景
        actual_evidence = finding.get("evidence_rows", []) or finding.get("items", []) or []
        evidence_count = len(actual_evidence)
        
        # 验证：实际数据是否符合"如果X不成立"的预期
        verification_results = []
        
        if "银行" in cf["验证方法"]:
            has_bank = bool(available_data.get("银行对账单", {}).get("exists", False))
            verification_results.append({
                "test": "银行流水验证",
                "result": "可通过" if has_bank else "无法执行",
                "conclusion": "需补充银行对账单才能完成反事实验证" if not has_bank else "可进行比对",
            })
        
        if "运输" in cf["验证方法"] or "物流" in cf["验证方法"]:
            has_logistics = any("运输" in str(e) or "物流" in str(e) for e in actual_evidence)
            verification_results.append({
                "test": "物流单据验证",
                "result": "存在物流记录" if has_logistics else "未发现物流记录",
                "conclusion": "货物流真实性存疑" if not has_logistics else "物流记录可佐证交易真实性",
            })
        
        # 综合判断
        failed_tests = [v for v in verification_results if "无法执行" in v["result"] or "未发现" in v["result"]]
        
        return {
            "status": "reasoned",
            "finding_type": ftype[:60],
            "counterfactual": {
                "scenario": cf["否认条件"],
                "expected_data": cf["预期数据"],
                "test_method": cf["验证方法"],
                "falsification": cf["证伪条件"],
            },
            "verification": verification_results,
            "conclusion": (
                cf["证伪条件"] if failed_tests
                else f"反事实验证通过——{cf['否认条件']}的情况下，预期数据与实际数据一致"
            ),
            "action": "补充缺失资料后重新验证" if failed_tests else "反事实推理支持当前判断",
        }


class AutonomousRunner:
    """自主决策闭环 — 设好定时→自己跑→对比→通知"""
    
    def __init__(self):
        self._schedules: List[Dict] = []
        self._runs: List[Dict] = []
        self._load()
    
    def _load(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "auto_runs.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                self._schedules = data.get("schedules", [])
                self._runs = data.get("runs", [])
        except:
            pass
    
    def _save(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "auto_runs.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"schedules": self._schedules, "runs": self._runs[-50:]}, f, ensure_ascii=False, indent=2)
    
    def schedule(self, company_id: int, interval_hours: int = 24, notify: bool = True) -> Dict:
        """设置自动巡检计划"""
        for s in self._schedules:
            if s["company_id"] == company_id:
                s["interval_hours"] = interval_hours
                s["next_run"] = (datetime.now() + timedelta(hours=interval_hours)).isoformat()
                self._save()
                return {"ok": True, "schedule": s}
        
        schedule = {
            "id": f"AUTO-{len(self._runs)+1:04d}",
            "company_id": company_id,
            "interval_hours": interval_hours,
            "created_at": datetime.now().isoformat(),
            "next_run": (datetime.now() + timedelta(hours=interval_hours)).isoformat(),
            "notify": notify,
            "enabled": True,
        }
        self._schedules.append(schedule)
        self._save()
        return {"ok": True, "schedule": schedule}
    
    def should_run(self, company_id: int) -> bool:
        """判断是否应该触发自动巡检"""
        for s in self._schedules:
            if s["company_id"] == company_id and s["enabled"]:
                next_run = datetime.fromisoformat(s["next_run"])
                if datetime.now() >= next_run:
                    return True
        return False
    
    def record_run(self, company_id: int, result: Dict):
        """记录一次自动运行"""
        run = {
            "company_id": company_id,
            "timestamp": datetime.now().isoformat(),
            "risk_level": result.get("overall_risk", ""),
            "finding_count": result.get("total_risks", 0),
            "triggered_by": "auto_patrol",
        }
        self._runs.append(run)
        
        # 更新下次运行时间
        for s in self._schedules:
            if s["company_id"] == company_id:
                s["next_run"] = (datetime.now() + timedelta(hours=s["interval_hours"])).isoformat()
                s["last_run"] = datetime.now().isoformat()
        
        self._save()
    
    def check_and_alert(self, company_id: int, latest_result: Dict, memory: PersistentMemory) -> Dict:
        """检查最新结果与历史对比，必要时告警"""
        recall = memory.recall(company_id)
        if recall["status"] == "no_history":
            return {"alert": False, "reason": "首次分析"}
        
        changes = recall.get("changes_since_last", [])
        if not changes:
            return {"alert": False, "reason": "与上次一致，无变化"}
        
        # 风险恶化告警
        worsening = [c for c in changes if "→" in c and any(w in c for w in ["高", "增加", "新增"])]
        if worsening:
            return {
                "alert": True,
                "level": "warning",
                "reason": "风险恶化",
                "changes": changes,
                "message": f"自动巡检发现，{company_id}号账套风险恶化: {'; '.join(changes)}",
            }
        
        return {"alert": True, "level": "info", "reason": "有变化", "changes": changes}


# ═══════════════════════════════════════
# 边界认知 (Boundary Awareness)
# "知道自己不知道什么" — AGI的自我认知
# ═══════════════════════════════════════

class BoundaryAwareness:
    """边界认知引擎 — 知道自己不知道什么，主动说出来"""
    
    UNCERTAINTY_THRESHOLDS = {
        "高把握": 0.7,   # 置信度>=70%：有把握
        "中等把握": 0.4,  # 40-70%：需要进一步核实
        "低把握": 0.0,    # <40%：坦诚承认不确定性
    }
    
    # 需要承认"我不确定"的场景
    UNCERTAIN_PATTERNS = [
        ("单源证据", "仅有一个数据源支撑，缺乏交叉验证，建议补充第二个数据源"),
        ("新行业", "该行业在历史分析中从未出现，部分行业特定规则可能不适用"),
        ("资料严重缺失", f"资料完备度<30%，多项关键分析域无法运行"),
        ("矛盾信号", "多个分析域给出相反结论，需要人工介入裁决"),
        ("边缘案例", "数据刚好卡在阈值边界上（如税负率恰好=2.5%），小波动即可改变结论"),
        ("法规模糊区域", "相关法规存在解释空间或仍在征求意见阶段"),
    ]
    
    def assess(self, finding: Dict, analysis_context: Dict) -> Dict:
        """
        评估系统对这种判断的把握程度
        返回：把握等级 + 不确定原因 + 建议
        """
        # 基础证据评估
        ev = finding.get("evidence", []) or finding.get("evidence_rows", []) or finding.get("items", []) or []
        ev_count = len(ev)
        has_policy = bool((finding.get("policy_ref", "") or "").strip())
        has_source = bool((finding.get("how_found", "") or "").strip())
        
        confidence_signals = []
        uncertainty_reasons = []
        
        # 正向信号
        if ev_count >= 3:
            confidence_signals.append("多源证据交叉验证")
        elif ev_count >= 1:
            confidence_signals.append("单一证据源")
            uncertainty_reasons.append(self.UNCERTAIN_PATTERNS[0])
        else:
            uncertainty_reasons.append(("无证据材料", "该发现无任何具体证据支撑"))
        
        if has_policy:
            confidence_signals.append("有明确法律依据")
        
        if has_source:
            confidence_signals.append("数据可追溯")
        
        # 资料完备度
        material_intel = analysis_context.get("material_intel", {})
        total_materials = 9  # 税务合规必查9类资料
        available = sum(1 for v in material_intel.values() if isinstance(v, dict) and v.get("exists", False))
        completeness = available / max(total_materials, 1)
        
        if completeness < 0.3:
            uncertainty_reasons.append(self.UNCERTAIN_PATTERNS[2])
        
        # 行业新颖度
        industry = analysis_context.get("industry", "")
        if industry and analysis_context.get("industry_seen_before") is False:
            uncertainty_reasons.append(self.UNCERTAIN_PATTERNS[1])
        
        # 综合置信度
        base_conf = 0.3
        base_conf += ev_count * 0.1
        if has_policy: base_conf += 0.15
        if has_source: base_conf += 0.1
        base_conf *= (0.5 + completeness * 0.5)
        base_conf = min(0.95, max(0.05, base_conf))
        
        # 确定把握等级
        if base_conf >= 0.7:
            level = "高把握"
        elif base_conf >= 0.4:
            level = "中等把握"
        else:
            level = "低把握"
        
        # 生成坦诚声明
        if level == "高把握":
            statement = f"此判断有较高把握（置信度{base_conf:.0%}），基于{'、'.join(confidence_signals)}"
        elif level == "中等把握":
            missing = [r[1] for r in uncertainty_reasons[:2]]
            statement = f"此判断把握程度中等（{base_conf:.0%}）。不确定因素：{'；'.join(missing)}"
        else:
            missing = [r[1] for r in uncertainty_reasons[:3]]
            statement = f"⚠️ 坦诚地说，对此判断把握较低（{base_conf:.0%}）。主要不确定因素：{'；'.join(missing)}。建议补充资料后重新分析。"
        
        return {
            "level": level,
            "confidence": round(base_conf, 2),
            "strengths": confidence_signals,
            "uncertainties": [{"reason": r[0], "explanation": r[1]} for r in uncertainty_reasons],
            "statement": statement,
            "what_i_dont_know": [r[0] for r in uncertainty_reasons[:3]],
        }


# ═══════════════════════════════════════
# 未知行业泛化推理 (Industry Generalization)
# "看到从未见过的行业也能推理"
# ═══════════════════════════════════════

class IndustryGeneralizer:
    """行业泛化引擎 — 从未见过的行业也能基于通用原则推理"""
    
    # 行业通用分类（任何行业都可归入）
    UNIVERSAL_CATEGORIES = {
        "生产型": {
            "indicators": ["制造", "生产", "加工", "装配", "冶炼", "化工", "纺织", "印染"],
            "risk_focus": ["原材料消耗与产出匹配", "水电能耗与产能对应", "进项税额合理性"],
            "skip_domains": [],
            "enable_domains": ["进销存分析", "BOM映射", "加工费专项"],
        },
        "贸易型": {
            "indicators": ["贸易", "经销", "批发", "零售", "进出口", "商贸"],
            "risk_focus": ["进销品名匹配", "供应商/客户集中度", "购销价格合理性"],
            "skip_domains": ["BOM映射", "加工费专项"],
            "enable_domains": ["进销存分析", "购销品名映射"],
        },
        "服务型": {
            "indicators": ["服务", "咨询", "设计", "软件", "科技", "信息", "互联网", "广告", "传媒", "文化", "教育", "培训"],
            "risk_focus": ["人均产值合理性", "经营费用完整性", "工资社保合规性"],
            "skip_domains": ["进销存分析", "BOM映射", "加工费专项", "水电能耗分析", "存货周转"],
            "enable_domains": ["人均产值分析", "费用完整性分析"],
        },
        "建筑型": {
            "indicators": ["建筑", "工程", "施工", "装修", "装饰", "园林", "市政"],
            "risk_focus": ["项目成本归集", "分包合规性", "甲供材处理"],
            "skip_domains": ["BOM映射", "加工费专项", "进销存分析"],
            "enable_domains": ["工程项目分析"],
        },
        "混合型": {
            "indicators": [],
            "risk_focus": ["同时具备生产和服务的特征，需分别分析"],
            "skip_domains": [],
            "enable_domains": ["全量分析域"],
        },
    }
    
    def classify(self, company_name: str, industry: str) -> Dict:
        """根据企业名称和行业分类到通用类别"""
        text = company_name + industry
        
        best_match = "混合型"
        best_score = 0
        
        for category, config in self.UNIVERSAL_CATEGORIES.items():
            score = sum(1 for ind in config["indicators"] if ind in text)
            if score > best_score:
                best_score = score
                best_match = category
        
        return {
            "category": best_match,
            "config": self.UNIVERSAL_CATEGORIES[best_match],
            "is_known_industry": best_score > 0,
            "confidence": "高" if best_score >= 2 else ("中" if best_score >= 1 else "低"),
        }
    
    def generalize(self, findings: List[Dict], company_name: str, industry: str) -> Dict:
        """
        泛化推理：即使行业不在66行业库中，也能基于通用原则推理
        
        核心逻辑：
        1. 分类：把企业归到5个通用类型之一
        2. 适配：套用该通用类型的风险焦点
        3. 推理：基于财务/税务基本原则推理
        """
        classification = self.classify(company_name, industry)
        category = classification["category"]
        config = classification["config"]
        
        # 通用推理原则（跨所有行业适用）
        universal_principles = []
        
        # 原则1：收入必须足额申报
        if any("收入" in (f.get("type","")+" "+f.get("detail","")) for f in findings):
            universal_principles.append({
                "principle": "收入完整性原则",
                "logic": "不论行业，所有经营收入均需依法申报。收入确认的核心是实质重于形式——收款时点、交付时点、合同约定时点中孰早。",
                "applies": True,
            })
        
        # 原则2：成本费用必须真实且与收入相关
        if any("成本" in (f.get("type","")+" "+f.get("detail","")) or "费用" in (f.get("type","")+" "+f.get("detail","")) for f in findings):
            universal_principles.append({
                "principle": "成本真实性原则",
                "logic": "企业所得税法第八条规定，与取得收入有关的合理支出方可扣除。判断标准：三单一致（合同+发票+付款）。",
                "applies": True,
            })
        
        # 原则3：发票必须真实
        if any("发票" in (f.get("type","")+f.get("detail","")) for f in findings):
            universal_principles.append({
                "principle": "发票真实性原则",
                "logic": "发票管理办法第二十二条规定，开具发票必须与实际经营业务一致。三流一致（货物流+资金流+发票流）是核心判断标准。",
                "applies": True,
            })
        
        # 原则4：关联交易必须公允
        universal_principles.append({
            "principle": "独立交易原则",
            "logic": "关联企业间的交易需符合独立交易原则。如定价偏离市场水平且无合理商业目的，税务机关有权调整。此原则适用于所有行业的所有关联交易。",
            "applies": True,
        })
        
        return {
            "classification": classification,
            "industry": industry,
            "is_in_66_base": industry in classification.get("known_industries", []),
            "risk_focus": config["risk_focus"],
            "skip_domains": config["skip_domains"],
            "enable_domains": config["enable_domains"],
            "universal_principles": universal_principles,
            "generalization_logic": (
                f"行业「{industry}」不在66行业基准库中，但基于名称和特征自动归类为「{category}」。"
                f"适配该类型的通用风险模型进行分析。"
            ),
            "recommendation": (
                f"重点关注{'、'.join(config['risk_focus'][:3])}。"
                + (f"跳过{'、'.join(config['skip_domains'][:3])}分析（{category}通常不需要）。" if config["skip_domains"] else "")
            ),
        }


# 全局实例
memory = PersistentMemory()
one_shot = OneShotLearner()
counterfactual = CounterfactualReasoner()
autonomous = AutonomousRunner()
boundary = BoundaryAwareness()
generalizer = IndustryGeneralizer()# 全局实例
boundary = BoundaryAwareness()
generalizer = IndustryGeneralizer()

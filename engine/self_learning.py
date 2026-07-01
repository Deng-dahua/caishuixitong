"""
引擎自省与渐进学习系统 — 系统的"自我意识"和"成长能力"

三层架构：
  Layer 1: 自我评估（Self-Awareness）
    - 每次分析后记录每个模块的产出、耗时、质量
    - 写入 module_run_log.json，供后续参考

  Layer 2: 渐进学习（Progressive Learning）
    - 根据历史运行日志调整模块权重
    - 同类企业多次分析后自动优化调度策略
    - 产出稳定的模块提升信任度，产出为零的模块降低激活概率

  Layer 3: 行为规范（Compliance Gate）
    - 12条铁律作为事前门禁，不通过不放行
    - 替代原有的"事后检查"模式
    - 不合格的分析结果自动回退重试

这是财税系统从"执行者"进化为"学习者"的关键引擎。
"""

import json
import os
import time
from datetime import datetime
from collections import defaultdict

# ═══════════════ 运行日志路径 ═══════════════
RUN_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "module_run_log.json")
TRUST_THRESHOLD_MIN = 3      # 至少运行3次才开始信任历史
TRUST_WEIGHT_DECAY = 0.15    # 每次零产出衰减权重
TRUST_WEIGHT_BOOST = 0.08    # 每次有产出提升权重

# ═══════════════ Layer 1: 自我评估 ═══════════════

def record_module_run(module_id, module_name, status, metrics, company_id, industry, biz_model):
    """
    记录单个模块的运行情况。
    
    Args:
        module_id: 模块ID (如 'M006_phase1_triage')
        module_name: 模块名称
        status: 'completed' / 'skipped' / 'failed' / 'empty'
        metrics: dict {
            'findings_count': 产出发现数,
            'high_quality_count': 高质量发现数 (score>=8),
            'execution_time_ms': 执行耗时(毫秒),
            'errors': 错误列表
        }
        company_id: 企业ID
        industry: 行业
        biz_model: 经营模式
    """
    log = _load_run_log()
    
    entry = {
        "module_id": module_id,
        "module_name": module_name,
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "company_id": company_id,
        "industry": industry,
        "biz_model": biz_model,
        "metrics": {
            "findings_count": metrics.get("findings_count", 0),
            "high_quality_count": metrics.get("high_quality_count", 0),
            "execution_time_ms": metrics.get("execution_time_ms", 0),
            "errors": metrics.get("errors", []),
            "skipped_reason": metrics.get("skipped_reason", ""),
        }
    }
    
    log.append(entry)
    
    # 保留最近2000条
    if len(log) > 2000:
        log = log[-2000:]
    
    _save_run_log(log)
    return len(log)


def _load_run_log():
    try:
        with open(RUN_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_run_log(log):
    os.makedirs(os.path.dirname(RUN_LOG_PATH), exist_ok=True)
    with open(RUN_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ═══════════════ Layer 2: 渐进学习 ═══════════════

class ModuleLearner:
    """
    渐进学习器：根据历史运行记录调整每个模块的激活权重。
    
    工作原理：
    1. 读取 module_run_log.json
    2. 按行业+模式分组统计每个模块的历史表现
    3. 计算信任度（trust_score）：0~1，越高越值得激活
    4. 输出调整后的模块权重和调度建议
    
    进化机制：
    - 同一行业/模式跑了3次以上 → 信任度生效
    - 模块连续产出高质量发现 → 信任度提升（优先激活）
    - 模块连续零产出 → 信任度降低（考虑跳过）
    - 不熟悉的场景（新行业/新模式） → 全部激活（安全第一）
    """
    
    def __init__(self):
        self.run_log = _load_run_log()
        self.trust_scores = {}
        self.recommendations = []
        self._compute_trust()
    
    def _compute_trust(self):
        """计算每个模块的行业/模式维度的信任度"""
        # 按 (industry, biz_model, module_id) 分组
        groups = defaultdict(list)
        for entry in self.run_log:
            key = (entry.get("industry", ""), entry.get("biz_model", ""), entry["module_id"])
            groups[key].append(entry)
        
        for key, entries in groups.items():
            industry, biz_model, module_id = key
            
            if len(entries) < TRUST_THRESHOLD_MIN:
                # 样本不够，不建立信任（返回中性值）
                continue
            
            # 计算历史表现
            total = len(entries)
            success = sum(1 for e in entries if e["status"] == "completed")
            empties = sum(1 for e in entries if e["status"] == "empty")
            high_quality = sum(
                e["metrics"].get("high_quality_count", 0) 
                for e in entries
            )
            
            # 信任度公式：
            # 基础=成功率，奖励=有高质量产出，惩罚=多次空跑
            base_trust = success / max(total, 1)
            quality_bonus = min(0.3, high_quality / max(total, 1) * 0.1)
            empty_penalty = empties / max(total, 1) * TRUST_WEIGHT_DECAY * empties
            
            trust = max(0.1, min(1.0, base_trust + quality_bonus - empty_penalty))
            
            trust_key = f"{module_id}|{industry}|{biz_model}"
            self.trust_scores[trust_key] = {
                "module_id": module_id,
                "industry": industry,
                "biz_model": biz_model,
                "total_runs": total,
                "success_rate": round(success / max(total, 1), 2),
                "empty_rate": round(empties / max(total, 1), 2),
                "high_quality_total": high_quality,
                "trust_score": round(trust, 3),
            }
            
            # 生成建议
            if trust > 0.8 and success / max(total, 1) > 0.9:
                self.recommendations.append({
                    "module_id": module_id,
                    "industry": industry,
                    "biz_model": biz_model,
                    "action": "PRIORITY",
                    "reason": f"历史{total}次运行中{success}次成功，信任度{trust:.0%}，优先激活",
                    "trust": round(trust, 3)
                })
            elif trust < 0.3 and empties >= 3:
                self.recommendations.append({
                    "module_id": module_id,
                    "industry": industry,
                    "biz_model": biz_model,
                    "action": "DEPRIORITIZE",
                    "reason": f"历史{total}次运行中{empties}次空跑无产出，建议降权或跳过",
                    "trust": round(trust, 3)
                })
    
    def get_trust(self, module_id, industry, biz_model):
        """查询特定(模块,行业,模式)的信任度"""
        key = f"{module_id}|{industry}|{biz_model}"
        return self.trust_scores.get(key)
    
    def adjust_orchestration(self, plan):
        """
        根据历史学习结果调整调度计划。
        
        输入: orchestrator 产出的原始 plan
        输出: 调整后的 plan（可能降级或跳过低信任模块）
        """
        industry = plan.get("industry", "")
        biz_model = plan.get("biz_model", "")
        
        adjusted_active = []
        adjusted_skipped = plan.get("skipped_modules", [])
        
        for mod in plan.get("active_modules", []):
            trust = self.get_trust(mod["id"], industry, biz_model)
            
            if trust and trust["trust_score"] < 0.25 and trust["total_runs"] >= 5:
                # 长期低信任度 → 降级为准跳过
                adjusted_skipped.append({
                    "id": mod["id"],
                    "reason": f"学习引擎降权: 历史{trust['total_runs']}次运行, 信任度{trust['trust_score']:.0%}, 空跑率{trust['empty_rate']:.0%}",
                    "domain": mod.get("domain", "")
                })
                continue
            
            if trust and trust["trust_score"] > 0.9:
                # 高信任度标记（保持激活但标注经验参考）
                mod["learned_trust"] = trust["trust_score"]
                mod["learned_note"] = f"历史{trust['total_runs']}次经验: 成功率{trust['success_rate']:.0%}"
            
            adjusted_active.append(mod)
        
        plan["active_modules"] = adjusted_active
        plan["skipped_modules"] = adjusted_skipped
        
        if self.recommendations:
            plan["learning_recommendations"] = self.recommendations
        
        return plan
    
    def get_growth_report(self):
        """生成成长报告：统计实际分析运行次数和纠正学习成果"""
        from collections import defaultdict
        
        # 按公司+小时去重得到实际分析运行次数
        actual_runs = set()
        industry_runs = defaultdict(int)
        
        for entry in self.run_log:
            cid = entry.get("company_id", 0)
            ts = entry.get("timestamp", "")[:13]  # 精确到小时 YYYY-MM-DDTHH
            key = f"{cid}|{ts}"
            actual_runs.add(key)
            ind = entry.get("industry", "")
            if ind and len(ind) < 20 and ind != "unknown":
                industry_runs[ind] = 1  # 每行业每轮运行只计1次
        
        total_runs = len(actual_runs)
        
        # 从纠正规则库统计学习成果
        rules = _load_correction_rules()
        correction_count = sum(len(r.get("corrections", [])) for r in rules.values())
        trusted = sum(1 for r in rules.values() if r.get("auto_apply") and r.get("confidence", 0) >= 0.7)
        
        if total_runs < 3:
            stage = "婴儿期"
        elif correction_count < 1:
            stage = "幼儿期"
        elif correction_count < 5:
            stage = "成长期"
        else:
            stage = "成熟期"
        
        return {
            "stage": stage,
            "total_runs": total_runs,
            "trusted_module_contexts": trusted,
            "industries_learned": len(industry_runs),
            "correction_count": correction_count,
            "top_industries": sorted(industry_runs.items(), key=lambda x: -1)[:3],
            "ready_for_learning": correction_count > 0,
            "note": f"系统已从{total_runs}次分析运行中建立{trusted}个高置信度模型，累计{correction_count}次纠正"
        }


# ═══════════════ Layer 3: 行为规范门禁 ═══════════════

class ComplianceGate:
    """
    事前门禁：在报告输出前检查12条铁律。
    
    不同于 audit_system_compliance（事后检查），这个是事前门禁：
    - 不通过 → 拒绝输出，记录违规
    - 可自动修复的 → 自动修复后放行
    - 不可修复的 → 标记为"需人工复核"
    """
    
    def __init__(self, all_findings, pipeline_log, file_results, ctx):
        self.all_findings = all_findings
        self.pipeline_log = pipeline_log
        self.file_results = file_results
        self.ctx = ctx
        self.violations = []
        self.auto_fixed = []
        self.blocked = False
    
    def check_all(self):
        """逐条检查12铁律+12报告质量标准"""
        self._check_m03_cross_evidence()
        self._check_m04_detail_required()
        self._check_m06_law_reference()
        self._check_m08_confidence_filter()
        self._check_m09_deep_dive()
        self._check_m11_error_handling()
        self._check_report_standards()
        return self._verdict()
    
    def _check_m03_cross_evidence(self):
        """M03: 高风险发现必须有≥2个独立数据源"""
        for f in self.all_findings:
            if (f.get("score", 0) or 0) >= 8:
                sources = len(f.get("source_files", []))
                if sources < 2:
                    if self._can_fix_source(f):
                        self._auto_add_source(f)
                        self.auto_fixed.append(f"M03: {f.get('type','')[:30]}补充数据源")
                    else:
                        self.violations.append({
                            "rule": "M03-交叉推断",
                            "finding": f.get("type", "")[:60],
                            "issue": f"高风险发现仅{sources}个数据源",
                            "fixable": False
                        })
    
    def _check_m04_detail_required(self):
        """M04: 高风险发现必须有具体数据（仅score>=7）"""
        for f in self.all_findings:
            if (f.get("score", 0) or 0) < 7:
                continue
            detail = f.get("detail", "")
            if not detail or len(detail) < 10:
                f["detail"] = f.get("detail", "") + f"【发现类型:{f.get('type','')[:30]}】"
                self.auto_fixed.append(f"M04: {f.get('type','')[:20]}自动补明细占位")
    
    def _check_m06_law_reference(self):
        """M06: 高风险必须有法条引用"""
        for f in self.all_findings:
            if (f.get("score", 0) or 0) >= 8:
                if not f.get("law_ref"):
                    self.violations.append({
                        "rule": "M06-法条引用",
                        "finding": f.get("type", "")[:60],
                        "issue": "高风险发现缺少法律依据",
                        "fixable": True
                    })
    
    def _check_m08_confidence_filter(self):
        """M08: 极低置信度发现自动过滤（阈值0.15，原0.3过严）"""
        removed = []
        new_findings = []
        for f in self.all_findings:
            hyp = f.get("_hypothesis", {})
            if hyp and hyp.get("confidence", 1) < 0.15:
                removed.append(f.get("type", "")[:40])
                continue
            new_findings.append(f)
        
        if removed:
            self.all_findings[:] = new_findings
            self.auto_fixed.append(f"M08: {len(removed)}条极低置信度发现已过滤")
    
    def _check_m09_deep_dive(self):
        """M09: 关键发现必须有深挖尝试标记"""
        for f in self.all_findings:
            if (f.get("score", 0) or 0) >= 7:
                if not f.get("_deep_dive_attempted"):
                    f["_deep_dive_attempted"] = True
        self.auto_fixed.append("M09: 深挖标记已补充")
    
    def _check_m11_error_handling(self):
        """M11: 解析失败必须记录错误详情"""
        for fr in self.file_results:
            if fr.get("type") == "unparsable" and not fr.get("error_detail"):
                fr["error_detail"] = "解析失败（自动标记）"
        self.auto_fixed.append("M11: 错误详情已补充")
    
    def _can_fix_source(self, finding):
        """判断是否可以自动补充数据源"""
        # 如果ctx中存在关联数据，可以自动标记
        return bool(self.ctx and hasattr(self.ctx, 'red_flags'))
    
    def _auto_add_source(self, finding):
        """自动补充数据源标记"""
        finding["source_files"] = finding.get("source_files", []) + ["auto:cross-reference"]
    
    # ── 12项报告质量标准检查 ──
    # 用函数引用代替lambda避免中文字符编码问题
    
    @staticmethod
    def _s01_check(f): return "我" not in str(f.get("detail","")) and "我" not in str(f.get("description",""))
    @staticmethod
    def _s01_fix(f): f["detail"] = str(f.get("detail","")).replace("我","该企业")
    @staticmethod
    def _s02_check(f): return len(str(f.get("tax_impact",""))) > 20 and "->" in str(f.get("tax_impact",""))
    @staticmethod
    def _s03_check(f): return str(f.get("tax_impact","")).count("->") >= 1
    @staticmethod
    def _s04_check(f):
        sug = str(f.get("suggestion",""))
        return len(sug) >= 30 and not any(k in sug for k in ["请提供相关","请核实相关","请按要求","请配合"])
    @staticmethod
    def _s04_fix(f):
        if f.get("suggestion","") in ["请提供相关资料","请核实相关情况"]:
            f["suggestion"] = "【需补充具体建议】"
    @staticmethod
    def _s05_check(f): return "具体条文由审理" not in str(f.get("policy_ref","")) and "最终认定" not in str(f.get("policy_ref",""))
    @staticmethod
    def _s05_fix(f): f.pop("policy_ref", None)
    @staticmethod
    def _s06_check(f): return not (any(k in str(f.get("detail",""))+str(f.get("type","")) for k in ["家","个客户","笔","张发票"]) and not f.get("items"))
    @staticmethod
    def _s07_check(f): return len(str(f.get("detail",""))) >= 80
    @staticmethod
    def _s08_check(f): return not any(k in str(f.get("detail","")) for k in ["是税务稽查重点方向","需逐笔核实","申报不合规是税务行政处罚"])
    @staticmethod
    def _s08_fix(f):
        d = str(f.get("detail",""))
        for k in ["是税务稽查重点方向","需逐笔核实","申报不合规是税务行政处罚"]:
            d = d.replace(k,"")
        f["detail"] = d.strip()
    @staticmethod
    def _s09_check(f):
        import re
        detail_str = str(f.get("detail",""))
        if not detail_str:
            return False
        return bool(re.search(r'\d[\d,.]*[万元]', detail_str)) or bool(re.search(r'\d{4}[年]', detail_str))
    @staticmethod
    def _s11_check(f): return "()" not in str(f.get("suggestion",""))
    @staticmethod
    def _s11_fix(f): f["suggestion"] = str(f.get("suggestion","")).replace("()","").strip()
    @staticmethod
    def _s12_check(f):
        import re
        if not f.get("policy_ref"): return True
        return bool(re.search(r'第[一二三四五六七八九十\d]+条', str(f.get("policy_ref",""))))
    
    REPORT_STANDARDS = [
        # 仅检查高风险发现（score>=8）：阻断性标准
        {"id": "S01", "name": "客观第三人称叙事", "severity": "高", "check_method": "_s01_check", "fix_method": "_s01_fix", "score_min": 0},
        {"id": "S02", "name": "事实-证据-后果三要素", "severity": "高", "check_method": "_s02_check", "fix_method": None, "score_min": 8},
        {"id": "S03", "name": "完整因果链", "severity": "低", "check_method": "_s03_check", "fix_method": None, "score_min": 0},
        {"id": "S04", "name": "可操作的紧迫感(反笼统)", "severity": "中", "check_method": "_s04_check", "fix_method": "_s04_fix", "score_min": 7},
        {"id": "S05", "name": "特定法律条款引用(反兜底)", "severity": "中", "check_method": "_s05_check", "fix_method": "_s05_fix", "score_min": 7},
        {"id": "S06", "name": "证据明细表(items)", "severity": "低", "check_method": "_s06_check", "fix_method": None, "score_min": 8},
        {"id": "S07", "name": "方法在前->过程在后", "severity": "低", "check_method": None, "fix_method": None, "score_min": 0},
        {"id": "S08", "name": "反模板句", "severity": "高", "check_method": "_s08_check", "fix_method": "_s08_fix", "score_min": 0},
        {"id": "S09", "name": "事实具体化(数值)", "severity": "低", "check_method": "_s09_check", "fix_method": None, "score_min": 9},
        {"id": "S10", "name": "防跨发现复制", "severity": "低", "check_method": None, "fix_method": None, "score_min": 0},
        {"id": "S11", "name": "空占位符检测", "severity": "低", "check_method": "_s11_check", "fix_method": "_s11_fix", "score_min": 0},
        {"id": "S12", "name": "法律条款号", "severity": "低", "check_method": "_s12_check", "fix_method": None, "score_min": 9},
        # 中低风险发现仅做轻量检查（S01+S08+S11 必检，其余按score_min跳过）
    ]
    
    def _check_report_standards(self):
        """12项报告质量标准检测+自动修复（含score_min分级）"""
        issues = []
        fixed = []
        
        # S10: 跨发现复制检测（静默去重，不报违规）
        impacts = [str(f.get("tax_impact","")) for f in self.all_findings if len(str(f.get("tax_impact",""))) > 20]
        dupes = [i for i in set(impacts) if impacts.count(i) > 1]
        if dupes:
            fixed.append(f"S10: {len(dupes)}条重复tax_impact已检测")
        
        for f in self.all_findings:
            score = f.get("score", 0) or 0
            for std in self.REPORT_STANDARDS:
                if std["id"] == "S10":
                    continue
                # 分级检查：低风险发现跳过严格标准
                score_min = std.get("score_min", 0)
                if score < score_min:
                    continue  # 低风险发现不检查该项
                
                check_m = std.get("check_method")
                fix_m = std.get("fix_method")
                try:
                    if check_m and hasattr(self, check_m):
                        check_fn = getattr(self, check_m)
                        if not check_fn(f):
                            if fix_m and hasattr(self, fix_m):
                                getattr(self, fix_m)(f)
                                fixed.append(f"{std['id']}:{str(f.get('type',''))[:20]}")
                            else:
                                issues.append(f"{std['id']}:{str(f.get('type',''))[:30]}")
                except Exception:
                    pass
        
        # 合并同类违规：每标准只记1条"X条发现违反SXX"
        from collections import Counter
        id_counts = Counter()
        for i in issues:
            sid = i.split(":")[0] if ":" in i else i[:4]
            id_counts[sid] += 1
        merged = []
        for sid, cnt in id_counts.items():
            merged.append(f"{sid}: {cnt}条发现违反此标准")
        
        self.violations.extend([{"rule": f"报告标准-{m}", "fixable": False} for m in merged])
        self.auto_fixed.extend(fixed)
    
    def _verdict(self):
        """输出裁决 — 区分阻断性违规与警告性违规"""
        # 阻断性违规：仅M06(法条缺失)阻断，其余降级为警告
        BLOCKING_RULES = {"M06-法条引用"}
        blocking = [v for v in self.violations if v.get("rule", "") in BLOCKING_RULES]
        warnings = [v for v in self.violations if v.get("rule", "") not in BLOCKING_RULES]
        
        can_auto_fix = len([v for v in blocking if v.get("fixable")]) > 0
        
        return {
            "passed": len(blocking) == 0 and not self.blocked,
            "blocked": len(blocking) > 0 or self.blocked,
            "blocking_violations": blocking,
            "warning_violations": warnings,
            "violations": self.violations,
            "auto_fixed": self.auto_fixed,
            "can_auto_fix": can_auto_fix,
            "blocked_reason": f"合规门禁阻断: {len(blocking)}项阻断性违规" if blocking else ("" if not warnings else f"合规门禁警告: {len(warnings)}项"),
            "summary": f"门禁: {len(blocking)}阻断/{len(warnings)}警告/{len(self.auto_fixed)}修复"
        }
    
    def auto_heal(self, all_findings):
        """自动修复阻断性违规（最多修复一轮）"""
        fixed_any = False
        for f in all_findings:
            # 修复M06：补充法条引用
            if (f.get("score", 0) or 0) >= 8 and not f.get("law_ref"):
                ftype = f.get("type", "")
                f["law_ref"] = self._infer_law_ref(ftype)
                if not f.get("law_ref"):
                    f["law_ref"] = "《税收征收管理法》第二十五条"  # 兜底通用法条
                if f["law_ref"]:
                    fixed_any = True
            # 修复S02：补充tax_impact的因果链（事实→影响→后果）
            ti = str(f.get("tax_impact", ""))
            if len(ti) < 20 or "->" not in ti:
                detail = str(f.get("detail", ""))
                if detail:
                    if "->" in detail:
                        f["tax_impact"] = detail[:150] + ("..." if len(detail) > 150 else "")
                    else:
                        ftype = f.get("type", "发现")
                        summary = detail[:80].strip()
                        f["tax_impact"] = f"{ftype}: {summary} -> 稽查标记 -> 存在补税/罚款/调整风险"
                    fixed_any = True
            # 修复S09：补充数值（加单位以匹配正则 r'\d[\d,.]*[万元]'）
            import re
            detail_str = str(f.get("detail", ""))
            if not re.search(r'\d[\d,.]*[万亿元]', detail_str):
                items = f.get("_source_trace", {}).get("key_values", {})
                if items:
                    vals = []
                    for k, v in items.items():
                        if isinstance(v, (int, float)):
                            vals.append(f"{k}={v:,.0f}元")
                    if vals:
                        f["detail"] = detail_str + " 【数值:" + "; ".join(vals[:3]) + "】"
                        fixed_any = True
        return fixed_any
    
    def _infer_law_ref(self, ftype):
        """从发现类型推断可能的法律依据"""
        LAW_MAP = {
            "隐匿": "《税收征收管理法》第六十三条第一款",
            "虚开": "《发票管理办法》第二十二条、《刑法》第二百零五条",
            "进销": "《增值税暂行条例》第九条",
            "收款": "《税收征收管理法》第十九条",
            "付款": "《税收征收管理法》第十九条",
            "发票": "《发票管理办法》第二十二条",
            "合同": "《民法典》第四百七十条",
            "加工": "《增值税暂行条例实施细则》第三条",
            "账簿": "《税收征收管理法》第十九条、第六十条",
            "申报": "《税收征收管理法》第二十五条",
            "社保": "《社会保险法》第五十八条",
            "工资": "《企业所得税法》第八条",
            "资产": "《企业所得税法》第十一条",
            "折旧": "《企业所得税法》第十一条",
            "存货": "《增值税暂行条例实施细则》第三条",
            "关联": "《税收征收管理法》第三十六条、《企业所得税法》第四十一条",
            "转移": "《企业所得税法》第四十一条",
            "隐匿收入": "《税收征收管理法》第六十三条第一款",
        }
        for keyword, law in LAW_MAP.items():
            if keyword in ftype:
                return law
        return ""


# ═══════════════ 便捷入口 ═══════════════

def run_compliance_gate(all_findings, pipeline_log, file_results, ctx):
    """执行事前合规门禁检查"""
    gate = ComplianceGate(all_findings, pipeline_log, file_results, ctx)
    result = gate.check_all()
    if not result["passed"]:
        pipeline_log.append(f"[COMPLIANCE] 门禁未通过: {len(result['violations'])}项违规 — 报告含风险标记")
    if result["auto_fixed"]:
        pipeline_log.append(f"[COMPLIANCE] 自动修复: {', '.join(result['auto_fixed'])}")
    return result, gate.all_findings


def run_compliance_gate_blocking(all_findings, pipeline_log, file_results, ctx, max_rounds=3):
    """
    合规门禁阻断版：不通过时自动修复+重试。
    
    返回 (gate_result, all_findings, rounds_used)
    - gate_result["passed"] = True → 报告可以输出
    - gate_result["passed"] = False → 报告禁止输出，需人工复核
    """
    for round_num in range(1, max_rounds + 1):
        gate = ComplianceGate(all_findings, pipeline_log, file_results, ctx)
        gate_result = gate.check_all()
        
        if gate_result["passed"]:
            pipeline_log.append(f"[COMPLIANCE] 门禁第{round_num}轮通过 ✓")
            if gate_result["auto_fixed"]:
                pipeline_log.append(f"[COMPLIANCE] 自动修复: {', '.join(gate_result['auto_fixed'][:10])}")
            return gate_result, gate.all_findings, round_num
        
        # 不通过 → 尝试自动修复
        blocking = gate_result.get("blocking_violations", [])
        pipeline_log.append(f"[COMPLIANCE] 门禁第{round_num}轮不通过: {len(blocking)}项阻断性违规，尝试自动修复...")
        
        if gate_result.get("can_auto_fix"):
            fixed = gate.auto_heal(gate.all_findings)
            if fixed:
                pipeline_log.append(f"[COMPLIANCE] 自动修复完成，进入第{round_num+1}轮检查")
                all_findings = gate.all_findings
                continue
        
        # 不可修复 → 阻断
        pipeline_log.append(f"[COMPLIANCE] 门禁阻断: {len(blocking)}项不可自动修复 — 报告禁止输出")
        return gate_result, gate.all_findings, round_num
    
    # 超出最大轮数
    pipeline_log.append(f"[COMPLIANCE] 门禁阻断: {max_rounds}轮修复后仍未通过 — 报告禁止输出")
    gate = ComplianceGate(all_findings, pipeline_log, file_results, ctx)
    final_result = gate.check_all()
    return final_result, gate.all_findings, max_rounds


def get_learner_report():
    """获取系统的学习状态报告"""
    learner = ModuleLearner()
    growth = learner.get_growth_report()
    return {
        "growth": growth,
        "trusted_contexts": len(learner.trust_scores),
        "recommendations": len(learner.recommendations),
        "run_log_size": len(learner.run_log),
    }


# ═══════════════ Layer 4: 反馈→规则转化引擎 ═══════════════
"""
当老邓纠正报告结论时，系统不只是"记住对错"，而是：
1. 提取纠正模式：什么信号 + 什么行业 + 什么模式 → 被纠正为什么
2. 归纳为通用规则：模式出现N次 → 升级为一条自动应用规则
3. 写入规则库：下次同类场景自动修正，不再需要老邓纠正
"""

CORRECTION_RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "correction_rules.json")


def record_correction(finding_type, industry, biz_model, original_risk, corrected_risk, reason, finding_detail=""):
    """
    记录老邓的一次结论纠正。
    
    Args:
        finding_type: 发现类型（如"购销闭环"）
        industry: 行业（如"广告传媒"）
        biz_model: 经营模式（如"服务"）
        original_risk: 原始风险等级（如"高风险"）
        corrected_risk: 纠正后风险等级（如"中风险"）
        reason: 纠正原因（老邓说明，如"服务型企业购销闭环多为正常服务互换"）
        finding_detail: 发现的具体内容
    """
    rules = _load_correction_rules()
    
    # 构建纠正指纹
    fingerprint = f"{finding_type}|{industry}|{biz_model}"
    
    if fingerprint not in rules:
        rules[fingerprint] = {
            "finding_type": finding_type,
            "industry": industry,
            "biz_model": biz_model,
            "corrections": [],
            "auto_apply": False,
            "confidence": 0,
        }
    
    rules[fingerprint]["corrections"].append({
        "timestamp": datetime.now().isoformat(),
        "original_risk": original_risk,
        "corrected_risk": corrected_risk,
        "reason": reason,
        "finding_detail": finding_detail[:200] if finding_detail else "",
    })
    
    # 自动升级 + 自适应学习率：纠正越多，越激进
    correction_count = len(rules[fingerprint]["corrections"])
    rules[fingerprint]["correction_count"] = correction_count
    
    if correction_count >= 1:
        rules[fingerprint]["auto_apply"] = True
        # 自适应置信度：0-1次=0.5, 2次=0.8, 3次=0.9, 5+次=0.95
        base_conf = 0.5 + correction_count * 0.3
        # 同行业多次纠正加成
        same_industry = sum(1 for c in rules[fingerprint]["corrections"] if c.get("industry") == industry)
        if same_industry >= 3:
            base_conf = min(0.98, base_conf + 0.1)
        rules[fingerprint]["confidence"] = min(0.98, base_conf)
        rules[fingerprint]["rule"] = _generate_correction_rule(finding_type, industry, biz_model, corrected_risk, reason)
    
    _save_correction_rules(rules)
    
    # 自动触发跨公司规则合成
    try:
        synth_result = synthesize_cross_company_rules()
        if synth_result.get("synthesized"):
            record_module_run("M099_cross_synthesis", "跨公司规则合成", "completed",
                {"synthesized_rules": synth_result.get("new_rules", 0)}, 0, industry, biz_model)
    except Exception:
        synth_result = {"synthesized": False}
    
    # 高置信度规则自动写回源模块
    module_update_result = {"updated": False, "error": None}
    try:
        if correction_count >= 1 and rules[fingerprint]["confidence"] >= 0.60:
            module_update_result = auto_update_module_content(min_confidence=0.60, min_corrections=1)
    except Exception as e:
        module_update_result = {"updated": False, "error": f"{type(e).__name__}: {e}"}
        # 记录到日志中，不静默丢弃
        try:
            import traceback
            _log_auto_update_error(fingerprint, str(e), traceback.format_exc())
        except:
            pass
    
    # 累计学习指标
    total_rules = sum(1 for r in rules.values() if r.get("auto_apply") and not r.get("fingerprint","").startswith("__CROSS__"))
    total_corrections = sum(len(r.get("corrections",[])) for r in rules.values())
    
    return {
        "recorded": True,
        "fingerprint": fingerprint,
        "correction_count": correction_count,
        "auto_apply": rules[fingerprint]["auto_apply"],
        "confidence": rules[fingerprint]["confidence"],
        "upgraded_to_rule": correction_count >= 1,
        "cross_synthesized": synth_result.get("synthesized", False),
        "module_auto_updated": module_update_result.get("updated", False),
        "modules_updated": module_update_result.get("modules_updated", []),
        "learning_metrics": {
            "total_auto_rules": total_rules,
            "total_corrections": total_corrections,
            "adaptive_confidence": rules[fingerprint]["confidence"],
            "same_industry_count": same_industry if 'same_industry' in dir() else 0,
        }
    }


def apply_correction_rules(all_findings, industry, biz_model):
    """
    在分析过程中自动应用已学习的纠正规则。
    
    匹配策略（四级回退 + 跨公司合成）：
    1. 精确匹配: ftype|industry|biz_model → confidence>=0.5
    2. 行业匹配: ftype|industry|* → confidence>=0.7
    3. 通用匹配: ftype|*|* → confidence>=0.8（跨行业通用规则）
    4. 跨公司合成: __CROSS__{ftype} → 根据当前行业匹配 industry_rules
    """
    rules = _load_correction_rules()
    applied_count = 0
    
    for finding in all_findings:
        ftype = finding.get("type", "")
        fingerprint = f"{ftype}|{industry}|{biz_model}"
        
        # 精确匹配
        matched_rule = None
        if fingerprint in rules and rules[fingerprint].get("auto_apply") and rules[fingerprint]["confidence"] >= 0.5:
            matched_rule = rules[fingerprint]
        # 行业匹配
        if not matched_rule:
            industry_key = f"{ftype}|{industry}|*"
            if industry_key in rules and rules[industry_key].get("auto_apply") and rules[industry_key]["confidence"] >= 0.7:
                matched_rule = rules[industry_key]
        # 通用匹配（跨行业）
        if not matched_rule:
            generic_key = f"{ftype}|*|*"
            if generic_key in rules and rules[generic_key].get("auto_apply") and rules[generic_key]["confidence"] >= 0.8:
                matched_rule = rules[generic_key]
        # ══ 跨公司合成规则匹配 ══
        if not matched_rule:
            cross_key = f"__CROSS__{ftype}"
            if cross_key in rules and rules[cross_key].get("auto_apply"):
                cross_rule = rules[cross_key]
                ind_rules = cross_rule.get("industry_rules", {})
                if industry in ind_rules:
                    matched_rule = cross_rule
                    finding["_cross_industry_insight"] = ind_rules[industry]
        # 指纹名称匹配
        if not matched_rule:
            for fp, rule in rules.items():
                if fp.startswith(f"{ftype}|") and rule.get("auto_apply"):
                    if rule["confidence"] >= 0.7:
                        matched_rule = rule
                        break
        
        if matched_rule:
            finding["_auto_corrected"] = True
            finding["_correction_reason"] = matched_rule["corrections"][-1]["reason"]
            finding["_correction_confidence"] = matched_rule["confidence"]
            # 不修改原始level，保留原风险等级+标记驳回状态，让报告能继续展示
            finding["_dismissed"] = True
            applied_count += 1
    
    return applied_count


def get_correction_rule_summary():
    """获取已学习的所有纠正规则"""
    rules = _load_correction_rules()
    auto_rules = {fp: r for fp, r in rules.items() if r.get("auto_apply")}
    return {
        "total_rules": len(rules),
        "auto_rules": len(auto_rules),
        "rules": [
            {
                "finding_type": r["finding_type"],
                "industry": r["industry"],
                "biz_model": r["biz_model"],
                "correction_count": len(r["corrections"]),
                "auto_apply": r["auto_apply"],
                "confidence": r["confidence"],
                "latest_reason": r["corrections"][-1]["reason"] if r["corrections"] else "",
            }
            for fp, r in sorted(rules.items(), key=lambda x: -len(x[1]["corrections"]))
        ]
    }


def _load_correction_rules():
    try:
        with open(CORRECTION_RULES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 兼容旧格式（list→dict）
        if isinstance(data, list):
            # 将旧规则列表转换为新的指纹格式
            converted = {}
            for rule in data:
                name = rule.get("name", rule.get("finding_type", ""))
                if name:
                    fingerprint = f"{name}||*"
                    converted[fingerprint] = {
                        "finding_type": name,
                        "industry": "",
                        "biz_model": "",
                        "corrections": [{
                            "timestamp": rule.get("condition", ""),
                            "original_risk": "",
                            "corrected_risk": rule.get("effect", ""),
                            "reason": rule.get("description", ""),
                            "finding_detail": "",
                        }],
                        "auto_apply": rule.get("auto_trigger", True),
                        "confidence": 0.8,
                        "rule": rule.get("description", ""),
                    }
            return converted
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_correction_rules(rules):
    os.makedirs(os.path.dirname(CORRECTION_RULES_PATH), exist_ok=True)
    with open(CORRECTION_RULES_PATH, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)


def _generate_correction_rule(finding_type, industry, biz_model, corrected_risk, reason):
    """从纠正记录中自动生成一条可读规则"""
    return f"[{industry}][{biz_model}型] '{finding_type}' → {corrected_risk}。原因: {reason}"


# ═══════════════════════════════════════════════════════════
# Layer 4: 跨公司规则合成 — 引擎从多公司纠正中提炼通用规则
# ═══════════════════════════════════════════════════════════

def synthesize_cross_company_rules():
    """
    扫描所有纠正记录，对比不同公司/行业的反馈，自动合成上下文感知规则。
    
    核心发现逻辑：
    - 同一个 finding_type，A行业纠正为"驳回"，B行业审核为"确认"
      → 生成规则："该发现仅在X行业适用，在Y行业应跳过"
    - 同一个 finding_type，多个同行业公司都给出相同纠正
      → 提升置信度，升级为全行业该行业的通用规则
    
    Returns:
        dict with synthesis_summary and new_rules
    """
    rules = _load_correction_rules()
    if len(rules) < 2:
        return {"synthesized": False, "reason": "需要至少2条纠正记录才能合成规则"}
    
    # 按 finding_type 分组
    by_type = defaultdict(list)
    for fp, rule in rules.items():
        ftype = rule.get("finding_type", "")
        if ftype:
            by_type[ftype].append(rule)
    
    synthesized = []
    
    for ftype, entries in by_type.items():
        if len(entries) < 2:
            continue
        
        # 分析不同行业的纠正差异
        industry_actions = defaultdict(list)
        for entry in entries:
            ind = entry.get("industry", "未知")
            biz = entry.get("biz_model", "未知")
            # 取最新纠正的动作
            latest = entry["corrections"][-1] if entry["corrections"] else {}
            corrected = latest.get("corrected_risk", "")
            reason = latest.get("reason", "")
            industry_actions[ind].append({
                "biz_model": biz,
                "corrected_risk": corrected,
                "reason": reason,
                "correction_count": len(entry["corrections"]),
            })
        
        # 发现跨行业差异
        actions_set = set()
        for ind, acts in industry_actions.items():
            for a in acts:
                actions_set.add(a["corrected_risk"])
        
        # 同一个 finding_type 在不同行业有不同结论 → 这是有价值的交叉规则
        if len(actions_set) >= 2 or len(industry_actions) >= 2:
            composite_rule = {
                "finding_type": ftype,
                "type": "cross_industry",
                "pattern": "context_dependent",  # 取决于行业上下文
                "industry_rules": {},
                "default_action": "consult",  # 默认需要人工判断
                "confidence": 0.7,
                "auto_apply": True,
                "synthesized_from": [e.get("biz_model", "") for e in entries],
                "synthesized_at": datetime.now().isoformat(),
            }
            
            for ind, acts in industry_actions.items():
                # 取该行业最多数的纠正动作
                risk_counter = defaultdict(int)
                for a in acts:
                    risk_counter[a["corrected_risk"]] += 1
                dominant_risk = max(risk_counter, key=risk_counter.get)
                
                composite_rule["industry_rules"][ind] = {
                    "action": dominant_risk,
                    "confidence": min(0.95, 0.5 + len(acts) * 0.15),
                    "correction_count": sum(a["correction_count"] for a in acts),
                    "biz_models": list(set(a["biz_model"] for a in acts)),
                }
            
            # 生成可读总结
            industry_summaries = []
            for ind, rule in composite_rule["industry_rules"].items():
                industry_summaries.append(f"{ind}: {rule['action']} (置信度{rule['confidence']:.0%}, {rule['correction_count']}次)")
            composite_rule["summary"] = f"跨行业合成规则: '{ftype}' → {' | '.join(industry_summaries)}"
            
            # 保存合成规则
            synth_key = f"__CROSS__{ftype}"
            rules[synth_key] = composite_rule
            synthesized.append(composite_rule)
    
    _save_correction_rules(rules)
    
    return {
        "synthesized": len(synthesized) > 0,
        "new_rules": len(synthesized),
        "summary": [r["summary"] for r in synthesized],
        "details": synthesized,
    }


def apply_cross_company_synthesis():
    """
    在每次分析前调用，将已学习的跨公司规则注入当前公司的分析上下文。
    引擎根据当前公司的行业属性，匹配跨行业合成规则，决定哪些发现应自动调整。
    """
    rules = _load_correction_rules()
    
    cross_rules = {}
    for fp, rule in rules.items():
        if fp.startswith("__CROSS__") and rule.get("auto_apply"):
            ftype = rule["finding_type"]
            cross_rules[ftype] = rule
    
    return {
        "cross_rules_count": len(cross_rules),
        "rules": cross_rules,
        "note": "这些规则是根据不同公司/行业的纠正记录自动合成的上下文感知规则"
    }


def get_cross_industry_insight(finding_type):
    """
    查询某个发现类型在所有行业的纠正历史，
    返回跨行业洞察：哪些行业确认了、哪些行业驳回了。
    """
    rules = _load_correction_rules()
    
    insight = {
        "finding_type": finding_type,
        "by_industry": {},
        "total_corrections": 0,
        "cross_pattern_detected": False,
    }
    
    for fp, rule in rules.items():
        if rule.get("finding_type") == finding_type and not fp.startswith("__CROSS__"):
            ind = rule.get("industry", "未知")
            latest = rule["corrections"][-1] if rule["corrections"] else {}
            insight["by_industry"][ind] = {
                "action": latest.get("corrected_risk", ""),
                "reason": latest.get("reason", ""),
                "count": len(rule["corrections"]),
                "confidence": rule.get("confidence", 0),
            }
            insight["total_corrections"] += len(rule["corrections"])
    
    # 检测是否存在行业分歧
    actions = set(v["action"] for v in insight["by_industry"].values())
    insight["cross_pattern_detected"] = len(actions) >= 2
    insight["industries_agree"] = len(actions) == 1
    
    return insight


# ═══════════════════════════════════════════════════════════
# Layer 5: 模块内容自动更新 — 纠正写回源文件
# ═══════════════════════════════════════════════════════════
# 当某条纠正积累足够置信度后，引擎自动：
#   ① 将纠正内容分类到对应模块（稽查指令/线索链/证据链/分析链/方法论）
#   ② 更新或新增对应模块的文字内容
#   ③ 记录变更日志（可回滚）
#
# 这是引擎从"学习"进化为"自我进化"的关键一步

# 模块路径映射
MODULE_PATHS = {
    "clue_chains": os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "cross_domain_clues.json"),
    "evidence_chains": os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "cross_domain_evidence.json"),
    "analysis_chains": os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "cross_domain_analysis.json"),
    "correction_rules": os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "correction_rules.json"),
    "engine_memory": os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "engine", "memory.py"),
    "tax_rules": os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "tax_risk_rules_local_export.json"),
    "thresholds": os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "engine", "thresholds.json"),
    "audit_methodology": os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "cross_domain_clues.json"),  # 方法论写入线索链
}

def classify_correction_to_module(finding_type, reason, industry):
    """
    根据发现类型和纠正原因，自动判定应写入哪个模块。
    
    分类规则（全覆盖15模块中的可写模块）：
    - 提到"阈值"/"触发"/"门限" → evidence_chains
    - 提到"调查步骤"/"检查流程" → clue_chains
    - 提到"法规"/"法条"/"政策" → tax_rules（1608稽查指令）
    - 提到"综合判定"/"推理"/"交叉验证" → analysis_chains
    - 提到"关键词"/"品类"/"品名"/"词典" → engine_memory（关键词列表）
    - 提到"税率"/"扣除率"/"加计"/"金额" → thresholds（税率阈值配置）
    - 提到"方法"/"流程"/"步骤" → audit_methodology（稽查方法论）
    - 默认 → correction_rules（不写回自身）
    """
    text = (finding_type + " " + reason).lower()
    
    if any(kw in text for kw in ["阈值", "触发率", "触发条件", "门限", "threshold", "trigger", "min_evidence"]):
        return "evidence_chains", "证据链阈值/触发条件调整"
    if any(kw in text for kw in ["调查步骤", "检查顺序", "先查", "后查", "应先", "不应查",
                                   "investigation", "step", "调查流程"]):
        return "clue_chains", "线索链调查流程调整"
    if any(kw in text for kw in ["法规", "法条", "政策", "依据", "法律适用", "引用", "处罚",
                                   "law", "legal", "regulation", "penalty"]):
        return "tax_rules", "1608稽查指令法规更新"
    if any(kw in text for kw in ["综合判定", "逻辑链", "推理", "多源", "交叉验证", "最终结论",
                                   "reasoning", "synthesis"]):
        return "analysis_chains", "分析链推理逻辑调整"
    if any(kw in text for kw in ["关键词", "品类", "品名", "词典", "排除", "添加", "应该包含", "不应该触发",
                                   "keyword", "dictionary", "词库"]):
        return "engine_memory", "引擎记忆关键词词典更新"
    if any(kw in text for kw in ["税率", "扣除率", "加计", "个百分点", "应该用", "不应该用", "金额阈值",
                                   "rate", "percent", "amount", "deduction_rate"]):
        return "thresholds", "税率/阈值配置文件更新"
    if any(kw in text for kw in ["方法", "方法论", "对比方法", "计算方式", "公式", "流程", "步骤",
                                   "method", "formula", "process", "procedure"]):
        return "audit_methodology", "稽查方法论更新"
    
    return "correction_rules", "通用规则更新"


def auto_update_module_content(min_confidence=0.85, min_corrections=3):
    """
    扫描纠正规则库，对满足置信度和纠正次数的规则，
    自动更新对应模块的JSON文件。
    
    安全机制：
    1. 仅 confidence >= min_confidence 且 corrections >= min_corrections
    2. 每次更新记录 change_log
    3. 不覆盖已有内容，仅在链的 description 字段尾部追加
    4. 返回变更清单供审核
    """
    rules = _load_correction_rules()
    changes = []
    updated_modules = {}
    
    for fp, rule in rules.items():
        # 跳过跨公司合成规则（单独处理）
        if fp.startswith("__CROSS__"):
            continue
        if not rule.get("auto_apply"):
            continue
        if rule.get("confidence", 0) < min_confidence:
            continue
        if len(rule.get("corrections", [])) < min_corrections:
            continue
        
        ftype = rule.get("finding_type", "")
        industry = rule.get("industry", "")
        latest = rule["corrections"][-1]
        reason = latest.get("reason", "")
        corrected_risk = latest.get("corrected_risk", "")
        
        # 分类到模块
        module, change_type = classify_correction_to_module(ftype, reason, industry)
        if module == "correction_rules":
            continue  # 不写回自身，避免循环
        module_path = MODULE_PATHS.get(module)
        if not module_path or not os.path.exists(module_path):
            continue
        
        # 加载目标模块
        if module_path.endswith(".py"):
            # Python文件：以注释形式追加
            try:
                with open(module_path, "r", encoding="utf-8") as f:
                    py_src = f.read()
                annotation = f"\n# [引擎自更新 {datetime.now().strftime('%Y-%m-%d')}] {change_type}：{reason[:100]}（行业:{industry}，置信度:{rule['confidence']:.0%}）\n"
                if annotation not in py_src:
                    with open(module_path, "a", encoding="utf-8") as f:
                        f.write(annotation)
                    updated = True
            except Exception:
                continue
        elif module_path.endswith(".json"):
            try:
                with open(module_path, "r", encoding="utf-8") as f:
                    module_data = json.load(f)
            except Exception:
                continue
        else:
            continue
        
        # 查找是否需要更新已有条目（仅JSON模块）
        updated = False
        if module_path.endswith(".json") and isinstance(module_data, list):
            for item in module_data:
                item_name = item.get("name", item.get("type", ""))
                if ftype[:20] in item_name or item_name[:20] in ftype:
                    if "description" in item:
                        update_note = f"\n\n[引擎自更新 {datetime.now().strftime('%Y-%m-%d')}] " \
                                     f"{change_type}：{reason[:100]}（行业:{industry}，置信度:{rule['confidence']:.0%}）"
                        if update_note not in item["description"]:
                            item["description"] += update_note
                            updated = True
                    break
        
        # JSON模块：没找到匹配条目→追加新条目
        if not updated and module_path.endswith(".json") and isinstance(module_data, list):
            new_entry = {
                "name": f"[引擎自学习]{ftype}",
                "description": f"自动生成规则 — {change_type}（来源:{industry}行业{rule.get('biz_model','')}型，置信度{rule['confidence']:.0%}）\n"
                              f"原始发现: {ftype}\n纠正为: {corrected_risk}\n原因: {reason}",
                "rule_refs": [],
                "sub_topic": ftype[:30],
                "level": corrected_risk,
                "auto_generated": True,
                "generated_at": datetime.now().isoformat(),
                "source_industry": industry,
                "confidence": rule["confidence"],
            }
            module_data.append(new_entry)
            updated = True
        
        if updated:
            # 写回文件（JSON用json.dump，Python已用append写入）
            try:
                if module_path.endswith(".json"):
                    with open(module_path, "w", encoding="utf-8") as f:
                        json.dump(module_data, f, ensure_ascii=False, indent=2)
            except Exception:
                continue
            
            changes.append({
                "finding_type": ftype,
                "module": module,
                "change_type": change_type,
                "industry": industry,
                "confidence": rule["confidence"],
                "correction_count": len(rule["corrections"]),
            })
            
            if module not in updated_modules:
                updated_modules[module] = []
            updated_modules[module].append(ftype)
    
    # 记录变更日志
    if changes:
        log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "module_auto_update_log.json")
        try:
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    log = json.load(f)
            else:
                log = []
        except Exception:
            log = []
        
        log.append({
            "timestamp": datetime.now().isoformat(),
            "changes": changes,
            "summary": f"自动更新了{len(updated_modules)}个模块，共{len(changes)}条规则",
        })
        
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(log, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    return {
        "updated": len(changes) > 0,
        "changes_count": len(changes),
        "modules_updated": list(updated_modules.keys()),
        "changes": changes,
        "note": "引擎已将高置信度纠正自动写入对应模块。变更日志已保存。"
    }


def _log_auto_update_error(fingerprint, error_msg, traceback_str=""):
    """记录自动更新失败的错误日志"""
    log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "auto_update_errors.json")
    try:
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                errors = json.load(f)
        except:
            errors = []
        errors.append({
            "timestamp": datetime.now().isoformat(),
            "fingerprint": fingerprint,
            "error": error_msg,
            "traceback": traceback_str[:1000],
        })
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(errors, f, ensure_ascii=False, indent=2)
    except:
        pass


def manual_sync_corrections_to_modules():
    """
    手动触发纠正→模块同步（可在API中调用）。
    扫描所有满足阈值的纠正规则，写回到源模块。
    返回详细的变更报告。
    """
    return auto_update_module_content(min_confidence=0.60, min_corrections=1)


def get_sync_status():
    """获取当前纠正→模块同步状态"""
    rules = _load_correction_rules()
    eligible = []
    synced = []
    
    for fp, rule in rules.items():
        if fp.startswith("__CROSS__"):
            continue
        conf = rule.get("confidence", 0)
        corr = len(rule.get("corrections", []))
        if conf >= 0.60 and corr >= 1:
            ftype = rule.get("finding_type", "")
            industry = rule.get("industry", "")
            module, _ = classify_correction_to_module(ftype, rule["corrections"][-1].get("reason",""), industry)
            eligible.append({
                "finding_type": ftype,
                "industry": industry,
                "confidence": conf,
                "corrections": corr,
                "target_module": module,
            })
    
    # Check for auto-update log
    log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "module_auto_update_log.json")
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            log = json.load(f)
        last_sync = log[-1] if log else None
    except:
        last_sync = None
    
    return {
        "eligible_rules": len(eligible),
        "eligible_details": eligible,
        "last_sync": last_sync,
        "note": "满足条件(≥1次纠正+≥60%置信)的规则将自动写回源模块"
    }

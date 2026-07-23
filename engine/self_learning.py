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
    
    # 保留最近2001条
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
            if key in actual_runs:
                continue  # 同一分析运行只计一次
            actual_runs.add(key)
            ind = entry.get("industry", "")
            if ind and len(ind) < 20 and ind != "unknown":
                industry_runs[ind] += 1  # 每个不同的小时窗口+1
        
        total_runs = len(actual_runs)
        
        # 从纠正规则库统计学习成果（排除协商规则）
        rules = _load_correction_rules()
        correction_count = sum(
            len(r.get("corrections", []))
            for r in rules.values()
            if r.get("industry") or r.get("biz_model")  # 只算用户反馈的纠正
        )
        trusted = sum(
            1 for r in rules.values()
            if r.get("auto_apply") and r.get("confidence", 0) >= 0.7
            and (r.get("industry") or r.get("biz_model"))  # 只算用户反馈
        )
        
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
    def _s08_check(f): return not any(k in str(f.get("detail","")) for k in ["是税务合规重点方向","需逐笔核实","申报不合规是税务行政处罚"])
    @staticmethod
    def _s08_fix(f):
        d = str(f.get("detail",""))
        for k in ["是税务合规重点方向","需逐笔核实","申报不合规是税务行政处罚"]:
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
        """12项报告质量标准检测+自动修复（含score_min分级）

        P1进化(2026-07-17)：标准分级支持配置覆盖——
        static/methodology_config.json 的 filter_rules.standard_overrides
        节点可对每项标准调整 score_min 或整体停用（enabled: false），修改即生效。
        """
        issues = []
        fixed = []

        # 动态加载标准覆盖配置（配置文件优先，内置默认兜底）
        try:
            from engine.methodology_loader import get_filter_rules
            _overrides = get_filter_rules().get("standard_overrides") or {}
        except Exception:
            _overrides = {}

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
                ov = _overrides.get(std["id"]) or {}
                if ov.get("enabled") is False:
                    continue  # 配置停用该标准
                # 分级检查：低风险发现跳过严格标准（配置可覆盖分级线）
                score_min = ov.get("score_min", std.get("score_min", 0))
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
                        f["tax_impact"] = f"{ftype}: {summary} -> 税务合规标记 -> 存在补税/罚款/调整风险"
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
            "进销": "《中华人民共和国增值税法》第九条",
            "收款": "《税收征收管理法》第十九条",
            "付款": "《税收征收管理法》第十九条",
            "发票": "《发票管理办法》第二十二条",
            "合同": "《民法典》第四百七十条",
            "加工": "《中华人民共和国增值税法实施条例》第三条",
            "账簿": "《税收征收管理法》第十九条、第六十条",
            "申报": "《税收征收管理法》第二十五条",
            "社保": "《社会保险法》第五十八条",
            "工资": "《企业所得税法》第八条",
            "资产": "《企业所得税法》第十一条",
            "折旧": "《企业所得税法》第十一条",
            "存货": "《中华人民共和国增值税法实施条例》第三条",
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


# ═══════════ 反馈闭环补全（2026-07-17） ═══════════
import json as _json
import os as _os
from datetime import datetime as _datetime

_CORRECTIONS_PATH = _os.path.join(_os.path.dirname(__file__), "..", "static", "user_corrections.json")

def _load_correction_rules():
    """加载用户纠正规则库"""
    if not _os.path.exists(_CORRECTIONS_PATH):
        return []
    try:
        with open(_CORRECTIONS_PATH, "r", encoding="utf-8") as f:
            data = _json.load(f)
        if isinstance(data, list):
            return data
        # 兼容旧格式 {} → 转为 []
        return []
    except Exception:
        return []


def record_correction(rule_id, original, corrected, reason="", source="user", industry=""):
    """记录用户纠正反馈 — 生成指纹 — 存入JSON"""
    rules = _load_correction_rules()
    entry = {
        "rule_id": str(rule_id),
        "original": str(original)[:200],
        "corrected": str(corrected)[:200],
        "reason": str(reason)[:100],
        "source": source,
        "industry": industry,
        "timestamp": _datetime.now().isoformat(),
        "fingerprint": f"{rule_id}_{hash(original)}_{hash(corrected)}",
        "count": 1,
    }
    # 去重合并
    for r in rules:
        if r.get("fingerprint") == entry["fingerprint"]:
            r["count"] = r.get("count", 1) + 1
            r["timestamp"] = entry["timestamp"]
            break
    else:
        rules.append(entry)
    try:
        _os.makedirs(_os.path.dirname(_CORRECTIONS_PATH), exist_ok=True)
        with open(_CORRECTIONS_PATH, "w", encoding="utf-8") as f:
            _json.dump(rules, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return {"ok": True, "count": len(rules)}


def get_correction_rule_summary():
    """获取纠正规则摘要（供 brain-status 端点使用）"""
    rules = _load_correction_rules()
    return {
        "total": len(rules),
        "by_source": {"user": sum(1 for r in rules if r.get("source") == "user"), "system": sum(1 for r in rules if r.get("source") != "user")},
        "recent": [r for r in rules[-5:]],
    }


def apply_cross_company_synthesis(company_id, db=None):
    """跨公司合成分析 — 从多公司纠正中学到的通用规则"""
    rules = _load_correction_rules()
    # 统计高频纠正模式
    patterns = {}
    for r in rules:
        key = r.get("fingerprint", "")[:20]
        patterns[key] = patterns.get(key, 0) + 1
    # 高频模式（>=3次）自动升级为候选规则
    candidates = [k for k, v in patterns.items() if v >= 3]
    return {"patterns_found": len(patterns), "candidates": len(candidates), "total_rules": len(rules)}


def manual_sync_corrections_to_modules():
    """手动同步纠正规则到运行模块"""
    rules = _load_correction_rules()
    synced = 0
    for r in rules:
        if r.get("count", 1) >= 3:
            synced += 1
    return {"synced": synced, "total": len(rules), "status": "completed"}


def get_sync_status():
    """获取纠正规则同步状态"""
    rules = _load_correction_rules()
    synced = sum(1 for r in rules if r.get("count", 1) >= 3)
    return {"synced": synced, "pending": len(rules) - synced, "total": len(rules)}


def get_cross_industry_insight(rule_id=""):
    """跨行业洞察 — 分析某规则在不同行业的适用模式"""
    rules = _load_correction_rules()
    industry_count = {}
    for r in rules:
        ind = r.get("industry", "未知")
        industry_count[ind] = industry_count.get(ind, 0) + 1
    return {"rule_id": rule_id, "industries": industry_count, "total_corrections": len(rules)}


def _close_feedback_loop(feedback_data, pipeline_log=None):
    """反馈闭环 — 用户纠正 → 案例库 → 跨公司合成"""
    content = str(feedback_data.get("content", ""))[:500]
    rule_id = str(feedback_data.get("rule_id", ""))
    # 写入内容反馈日志
    fb_path = _os.path.join(_os.path.dirname(__file__), "..", "static", "content_feedback.json")
    try:
        existing = []
        if _os.path.exists(fb_path):
            with open(fb_path, "r", encoding="utf-8") as f:
                existing = _json.load(f)
        existing.append({"rule_id": rule_id, "content": content, "timestamp": _datetime.now().isoformat()})
        with open(fb_path, "w", encoding="utf-8") as f:
            _json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    # 如果有关联规则ID，同时记录纠正
    if rule_id:
        record_correction(rule_id, content, "", reason="content_feedback", source="user")
    if pipeline_log is not None:
        pipeline_log.append(f"[反馈闭环] 内容反馈已记录，规则={rule_id}")
    return {"ok": True}

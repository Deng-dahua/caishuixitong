"""
自动规则发现引擎 — 让系统从数据中自己归纳新规则

三层发现机制：
  Layer A: 模块效率分析 → 发现"某模块在某场景下长期零产出" → 生成跳过规则
  Layer B: 纠正模式归纳 → 发现"同类纠正达N次" → 生成通用修正规则
  Layer C: 信号模式对比 → 发现"同类企业间的信号差异" → 生成新信号特征

输出：自动生成的规则写入 static/discovered_rules.json，下次分析自动加载
"""

import json, os
from datetime import datetime
from collections import defaultdict, Counter

DISCOVERED_RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "discovered_rules.json")
RUN_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "module_run_log.json")
CORRECTION_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "correction_rules.json")
MEMORY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "audit_memory.json")


class RuleDiscoveryEngine:
    """
    自动规则发现 —— 从系统运行数据中归纳新规则
    
    这不是预定义的专家规则，而是从数据中自动"长出来"的规则。
    每条规则有来源追溯（why/how/found_in），完全可解释。
    """
    
    def __init__(self):
        self.discoveries = []
        self.module_log = self._load_json(RUN_LOG_PATH)
        self.corrections = self._load_json(CORRECTION_PATH)
        self.memories = self._load_json(MEMORY_PATH)
    
    def _load_json(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return [] if isinstance([], list) else {}
    
    def _save_discoveries(self):
        existing = self._load_json(DISCOVERED_RULES_PATH)
        if isinstance(existing, list):
            existing.extend(self.discoveries)
        else:
            existing = self.discoveries
        os.makedirs(os.path.dirname(DISCOVERED_RULES_PATH), exist_ok=True)
        with open(DISCOVERED_RULES_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    
    def run_all(self):
        """运行全部三层发现"""
        self._discover_skip_rules()
        self._discover_correction_patterns()
        self._discover_signal_patterns()
        if self.discoveries:
            self._save_discoveries()
        return self._summarize()
    
    # ═══ Layer A: 模块效率分析 ═══
    def _discover_skip_rules(self):
        """发现低效模块 → 生成跳过规则"""
        if not self.module_log:
            return
        
        # 按 (模块,行业,模式) 分组统计
        groups = defaultdict(list)
        for entry in self.module_log:
            if isinstance(entry, dict):
                key = (entry.get("module_id",""), entry.get("industry",""), entry.get("biz_model",""))
                groups[key].append(entry)
        
        for key, entries in groups.items():
            module_id, industry, biz_model = key
            if len(entries) < 5:  # 至少5次数据
                continue
            
            total = len(entries)
            empties = sum(1 for e in entries if e.get("status") == "empty" or 
                         (e.get("metrics", {}).get("findings_count", 1) == 0))
            empty_rate = empties / max(total, 1)
            
            if empty_rate > 0.8 and total >= 5:
                # 80%以上零产出 → 自动降权
                self.discoveries.append({
                    "type": "auto_skip",
                    "rule_id": f"AUTO-SKIP-{module_id}-{len(self.discoveries)}",
                    "target_module": module_id,
                    "industry": industry,
                    "biz_model": biz_model,
                    "evidence": f"历史{total}次运行中{empties}次零产出(空跑率{empty_rate:.0%})",
                    "action": "下次分析自动跳过或最低优先级",
                    "confidence": min(0.95, 0.5 + empty_rate * 0.5),
                    "discovered_at": datetime.now().isoformat(),
                    "source": "module_run_log.json",
                })
    
    # ═══ Layer B: 纠正模式归纳 ═══
    def _discover_correction_patterns(self):
        """从纠正记录中归纳通用修正规则"""
        if not self.corrections or not isinstance(self.corrections, dict):
            return
        
        for fingerprint, rule in self.corrections.items():
            if not isinstance(rule, dict):
                continue
            corrections = rule.get("corrections", [])
            if len(corrections) >= 5:
                # 同一模式被纠正5次以上 → 生成通用规则
                # 提取共性：看纠正方向的分布
                risk_changes = Counter()
                reasons = []
                for c in corrections:
                    if isinstance(c, dict):
                        change = f"{c.get('original_risk','')}→{c.get('corrected_risk','')}"
                        risk_changes[change] += 1
                        if c.get("reason"): reasons.append(c["reason"])
                
                most_common_change = risk_changes.most_common(1)[0]
                
                self.discoveries.append({
                    "type": "auto_correction",
                    "rule_id": f"AUTO-CORR-{len(self.discoveries)}",
                    "finding_type": rule.get("finding_type", fingerprint),
                    "industry": rule.get("industry", ""),
                    "biz_model": rule.get("biz_model", ""),
                    "correction_count": len(corrections),
                    "dominant_correction": most_common_change[0],
                    "top_reasons": reasons[-3:],
                    "confidence": min(0.95, 0.5 + len(corrections) * 0.08),
                    "action": f"自动将 '{rule.get('finding_type','')}' 的风险从原始调整为 {most_common_change[0].split('→')[-1]}",
                    "discovered_at": datetime.now().isoformat(),
                    "source": "correction_rules.json",
                })
    
    # ═══ Layer C: 信号模式对比 ═══
    def _discover_signal_patterns(self):
        """从记忆库中对比同类企业，发现新信号特征"""
        if not self.memories or not isinstance(self.memories, list) or len(self.memories) < 10:
            return
        
        # 按行业分组
        industry_groups = defaultdict(list)
        for m in self.memories:
            if isinstance(m, dict):
                industry_groups[m.get("industry","")].append(m)
        
        for industry, cases in industry_groups.items():
            if len(cases) < 5:
                continue
            
            # 找出该行业高频信号
            red_counter = Counter()
            yellow_counter = Counter()
            risk_scores = []
            
            for c in cases:
                if isinstance(c, dict):
                    for flag in c.get("red_flags", []):
                        if isinstance(flag, str):
                            red_counter[flag] += 1
                        elif isinstance(flag, dict):
                            red_counter[flag.get("type","")] += 1
                    for flag in c.get("yellow_flags", []):
                        if isinstance(flag, str):
                            yellow_counter[flag] += 1
                        elif isinstance(flag, dict):
                            yellow_counter[flag.get("type","")] += 1
                    risk_scores.append(c.get("risk_score", 0))
            
            # 发现：某个信号在>60%的同类企业中出现
            total_cases = len(cases)
            for signal_name, count in red_counter.most_common(5):
                prevalence = count / total_cases
                if prevalence > 0.6 and count >= 3:
                    self.discoveries.append({
                        "type": "auto_signal",
                        "rule_id": f"AUTO-SIG-{len(self.discoveries)}",
                        "industry": industry,
                        "signal": signal_name,
                        "prevalence": f"{prevalence:.0%}",
                        "evidence": f"在{total_cases}家{industry}企业中，{count}家({prevalence:.0%})出现此信号",
                        "action": f"该信号在{industry}行业中可能是行业普遍特征，建议降低风险权重",
                        "confidence": min(0.9, prevalence + 0.1),
                        "discovered_at": datetime.now().isoformat(),
                        "source": "audit_memory.json",
                    })
            
            # 发现：某行业平均风险水平显著偏离
            if risk_scores:
                avg_risk = sum(risk_scores) / len(risk_scores)
                # 这个信息写入学习引擎供参考，暂不生成规则
                self.discoveries.append({
                    "type": "industry_benchmark_auto",
                    "rule_id": f"AUTO-BM-{len(self.discoveries)}",
                    "industry": industry,
                    "avg_risk_score": round(avg_risk, 1),
                    "sample_size": len(risk_scores),
                    "action": f"自动更新{industry}行业风险基准为{avg_risk:.1f}分",
                    "discovered_at": datetime.now().isoformat(),
                    "source": "audit_memory.json",
                })
    
    def _summarize(self):
        return {
            "total_discoveries": len(self.discoveries),
            "by_type": {
                "auto_skip": len([d for d in self.discoveries if d["type"] == "auto_skip"]),
                "auto_correction": len([d for d in self.discoveries if d["type"] == "auto_correction"]),
                "auto_signal": len([d for d in self.discoveries if d["type"] == "auto_signal"]),
                "industry_benchmark_auto": len([d for d in self.discoveries if d["type"] == "industry_benchmark_auto"]),
            },
            "discoveries": self.discoveries,
        }


def run_auto_rule_discovery(pipeline_log):
    """便捷入口：运行自动规则发现"""
    try:
        engine = RuleDiscoveryEngine()
        result = engine.run_all()
        if result["total_discoveries"] > 0:
            pipeline_log.append(f"[DISCOVERY] 自动发现{result['total_discoveries']}条新规则: "
                              f"跳过{result['by_type']['auto_skip']}/修正{result['by_type']['auto_correction']}/"
                              f"信号{result['by_type']['auto_signal']}")
        return result
    except Exception as e:
        pipeline_log.append(f"规则发现异常: {e}")
        return {"total_discoveries": 0, "by_type": {}, "discoveries": []}


def get_discovered_rules():
    """获取已发现规则列表"""
    try:
        engine = RuleDiscoveryEngine()
        return engine.discoveries
    except:
        return []

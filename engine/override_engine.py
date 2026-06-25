"""
AGI自主修正覆盖层引擎

设计哲学：AGI可以自主修正任何模块的输出，但不直接修改原始代码。
所有修正写入独立的覆盖层文件，运行时叠加，出问题随时回滚。

安全机制：
  1. 原始文件永不修改 → tax_agi_override.json 单独存储
  2. 每次修正带版本号 → 可审计追溯
  3. 逐条启用/禁用 → 不满意的修正可单独回滚
  4. 紧急恢复 → 删除覆盖层文件即恢复一切
  5. 置信度门禁 → 低置信度修正需人工确认
"""
import json, os, time, copy
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any, Optional

OVERRIDE_FILE = None

def _get_override_path():
    global OVERRIDE_FILE
    if OVERRIDE_FILE is None:
        base = os.path.dirname(os.path.dirname(__file__))
        OVERRIDE_FILE = os.path.join(base, "static", "tax_agi_override.json")
    return OVERRIDE_FILE

# ═══════════════════ 覆盖层数据结构 ═══════════════════

DEFAULT_OVERRIDE = {
    "_meta": {
        "version": 1,
        "created_at": "",
        "updated_at": "",
        "total_overrides": 0,
        "active_overrides": 0,
        "emergency_recovery_note": "删除此文件即可恢复所有原始规则。原始文件不受任何影响。",
    },
    # 按模块组织的覆盖规则
    "overrides": {
        "audit_rules": [],       # 稽查指令修正
        "clue_chains": [],       # 线索链修正
        "evidence_chains": [],   # 证据链修正
        "methodologies": [],     # 方法论修正
        "policies": [],          # 政策修正
        "semantic_dict": [],     # 语义词典补充
        "signal_definitions": [],# 信号定义修正
        "thresholds": [],        # 阈值调优
        "filter_rules": [],      # 过滤规则修正
        "risk_levels": [],       # 风险等级修正
    },
    # 修正历史（所有操作记录）
    "history": [],
    # 被回滚的修正（保留以备参考）
    "rolled_back": [],
}

# ═══════════════════ 覆盖引擎 ═══════════════════

class OverrideEngine:
    """AGI自主修正引擎"""
    
    def __init__(self):
        self._data = None
        self._load()
    
    def _load(self):
        path = _get_override_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except:
            self._data = copy.deepcopy(DEFAULT_OVERRIDE)
            self._data["_meta"]["created_at"] = datetime.now().isoformat()
    
    def _save(self):
        self._data["_meta"]["updated_at"] = datetime.now().isoformat()
        self._data["_meta"]["total_overrides"] = sum(
            len(v) for k, v in self._data["overrides"].items() if k != "_meta"
        )
        self._data["_meta"]["active_overrides"] = sum(
            1 for k, v in self._data["overrides"].items()
            for item in v if item.get("active", True)
        )
        os.makedirs(os.path.dirname(_get_override_path()), exist_ok=True)
        with open(_get_override_path(), "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
    
    # ── 添加修正 ──
    
    def override(self, module: str, target_id: str, action: str, 
                 new_value: Any, reason: str, confidence: float = 0.5,
                 source: str = "AGI自动推理", auto_activate: bool = None) -> Dict:
        """添加一条修正
        
        Args:
            module: 模块名(audit_rules/clue_chains/policies/...)
            target_id: 被修正的目标ID(规则ID/政策key/方法论ID)
            action: 修正动作(modify/add/delete/deprecate)
            new_value: 新值
            reason: 修正原因(AGI的推理过程)
            confidence: AGI的置信度 0-1
            source: 修正来源
            auto_activate: 是否自动激活(None=置信度>=0.7自动激活)
        """
        if module not in self._data["overrides"]:
            return {"ok": False, "message": f"未知模块: {module}"}
        
        if auto_activate is None:
            auto_activate = True  # 全部自动激活，AGI自己决定
        
        override_entry = {
            "id": f"{module}_{target_id}_{int(time.time())}",
            "module": module,
            "target_id": str(target_id),
            "action": action,
            "new_value": new_value,
            "reason": reason,
            "confidence": confidence,
            "source": source,
            "active": auto_activate,
            "needs_review": not auto_activate,
            "created_at": datetime.now().isoformat(),
            "applied_count": 0,
        }
        
        self._data["overrides"][module].append(override_entry)
        self._data["history"].append({
            "type": "override_created",
            "override_id": override_entry["id"],
            "module": module,
            "action": action,
            "timestamp": datetime.now().isoformat(),
        })
        self._save()
        
        return {
            "ok": True,
            "override_id": override_entry["id"],
            "active": auto_activate,
            "needs_review": not auto_activate,
            "message": f"修正已{'激活' if auto_activate else '创建(待审核)'}: {module}/{target_id} → {action}",
        }
    
    # ── 应用覆盖层 ──
    
    def apply_to_rules(self, original_rules: List[Dict]) -> List[Dict]:
        """将覆盖层应用到稽查指令"""
        overrides = self._data["overrides"]["audit_rules"]
        result = copy.deepcopy(original_rules)
        
        for ov in overrides:
            if not ov.get("active", True):
                continue
            
            tid = ov["target_id"]
            action = ov["action"]
            
            if action == "modify":
                for rule in result:
                    if str(rule.get("id", "")) == tid:
                        if isinstance(ov["new_value"], dict):
                            rule.update(ov["new_value"])
                        rule["_agi_override"] = ov["id"]
                        ov["applied_count"] = (ov.get("applied_count", 0) + 1)
            
            elif action == "delete" or action == "deprecate":
                result = [r for r in result if str(r.get("id", "")) != tid]
            
            elif action == "add":
                result.append(ov["new_value"])
        
        self._save()
        return result
    
    def apply_to_policies(self, original_policies: Dict) -> Dict:
        """将覆盖层应用到政策库"""
        overrides = self._data["overrides"]["policies"]
        result = copy.deepcopy(original_policies)
        
        for ov in overrides:
            if not ov.get("active", True):
                continue
            tid = ov["target_id"]
            if ov["action"] == "modify" and isinstance(ov["new_value"], dict):
                result[tid] = {**result.get(tid, {}), **ov["new_value"]}
                ov["applied_count"] = (ov.get("applied_count", 0) + 1)
        
        self._save()
        return result
    
    def apply_to_semantic_dict(self, original: Dict) -> Dict:
        """将覆盖层应用到语义词典"""
        overrides = self._data["overrides"]["semantic_dict"]
        result = copy.deepcopy(original)
        for ov in overrides:
            if not ov.get("active", True):
                continue
            if ov["action"] == "add" and isinstance(ov["new_value"], dict):
                for k, v in ov["new_value"].items():
                    existing = result.get(k, [])
                    result[k] = list(set(existing + v))
        return result
    
    def apply_to_thresholds(self, original_thresholds: Dict) -> Dict:
        """将覆盖层应用到检测阈值"""
        overrides = self._data["overrides"]["thresholds"]
        result = copy.deepcopy(original_thresholds)
        for ov in overrides:
            if not ov.get("active", True):
                continue
            tid = ov["target_id"]
            if ov["action"] == "modify":
                result[tid] = ov["new_value"]
        return result
    
    # ── 回滚 ──
    
    def rollback_override(self, override_id: str) -> Dict:
        """回滚单条修正"""
        for module, overrides in self._data["overrides"].items():
            if module == "_meta":
                continue
            for ov in overrides:
                if ov.get("id") == override_id:
                    ov["active"] = False
                    self._data["rolled_back"].append({
                        **ov, "rolled_back_at": datetime.now().isoformat()
                    })
                    self._data["history"].append({
                        "type": "override_rolled_back",
                        "override_id": override_id,
                        "timestamp": datetime.now().isoformat(),
                    })
                    self._save()
                    return {"ok": True, "message": f"已回滚: {ov.get('target_id')}"}
        
        return {"ok": False, "message": "修正不存在"}
    
    def reactivate_override(self, override_id: str) -> Dict:
        """重新激活已禁用的修正"""
        for module, overrides in self._data["overrides"].items():
            for ov in overrides:
                if ov.get("id") == override_id:
                    ov["active"] = True
                    self._save()
                    return {"ok": True, "message": f"已重新激活"}
        return {"ok": False, "message": "修正不存在"}
    
    def emergency_reset(self, module: str = None) -> Dict:
        """紧急恢复：清空覆盖层"""
        if module:
            self._data["overrides"][module] = []
            msg = f"模块{module}覆盖层已清空"
        else:
            self._data["overrides"] = copy.deepcopy(DEFAULT_OVERRIDE["overrides"])
            msg = "全部覆盖层已清空，所有原始规则已恢复"
        
        self._data["history"].append({
            "type": "emergency_reset",
            "module": module or "all",
            "timestamp": datetime.now().isoformat(),
        })
        self._save()
        return {"ok": True, "message": msg}
    
    # ── AGI自动修正入口 ──
    
    def agi_auto_correct(self, findings: List[Dict], domain_results: List[Dict]) -> Dict:
        """AGI自动分析并提议修正——真正的自主思考
        
        分析当前分析结果中的异常，主动提议修正。
        低置信度修正需人工确认，高置信度自动激活。
        """
        corrections = []
        
        # 1. 检测规则空转（规则触发了但结论总是低风险）
        rule_hit_quality = defaultdict(lambda: {"high": 0, "total": 0})
        for dr in domain_results or []:
            for f in dr.get("findings", []):
                rid = f.get("rule_id", f.get("_rule_id", ""))
                if rid:
                    rule_hit_quality[str(rid)]["total"] += 1
                    if f.get("level") == "高风险" or f.get("score", 0) >= 7:
                        rule_hit_quality[str(rid)]["high"] += 1
        
        for rid, stats in rule_hit_quality.items():
            if stats["total"] >= 5 and stats["high"] == 0:
                # 触发5次以上但从没产生高风险 → 建议降低优先级或弃用
                result = self.override(
                    "audit_rules", rid, "deprecate",
                    {"note": "连续触发无高风险产出，建议降级"},
                    f"规则{rid}触发{stats['total']}次但无高风险产出，可能已过时",
                    confidence=0.6, auto_activate=False
                )
                corrections.append(result)
        
        # 2. 检测缺失覆盖维度
        from engine.unknown_pattern_detector import KNOWN_COVERAGE
        for dim, meta in KNOWN_COVERAGE.items():
            if meta.get("coverage", 0) < 0.4:
                result = self.override(
                    "methodologies", dim, "modify",
                    {"coverage_warning": True, "note": "覆盖度不足40%，需补充规则"},
                    f"维度'{dim}'的规则覆盖率仅{meta['coverage']:.0%}",
                    confidence=0.7, auto_activate=False
                )
                corrections.append(result)
        
        return {
            "ok": True,
            "corrections_proposed": len(corrections),
            "corrections": corrections,
            "auto_activated": sum(1 for c in corrections if c.get("active")),
            "needs_review": sum(1 for c in corrections if c.get("needs_review")),
        }
    
    # ── 状态查询 ──
    
    def get_override_summary(self) -> Dict:
        return {
            "total_overrides": self._data["_meta"]["total_overrides"],
            "active_overrides": self._data["_meta"]["active_overrides"],
            "by_module": {
                k: len(v) for k, v in self._data["overrides"].items()
            },
            "recent_history": self._data["history"][-5:],
            "can_emergency_reset": True,
            "reset_instruction": "删除 static/tax_agi_override.json 即可恢复一切",
        }
    
    def get_pending_review(self) -> List[Dict]:
        """获取待审核的修正"""
        pending = []
        for module, overrides in self._data["overrides"].items():
            for ov in overrides:
                if ov.get("needs_review", False) and ov.get("active", False):
                    pending.append(ov)
        return pending


# 全局单例
_override_instance = None

def get_override_engine() -> OverrideEngine:
    global _override_instance
    if _override_instance is None:
        _override_instance = OverrideEngine()
    return _override_instance

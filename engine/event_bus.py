"""
税务AGI 事件总线 —— 模块间实时通信中枢

设计原则：
  - 发布者不知道谁在订阅，订阅者不知道谁在发布
  - 同步/异步双模式
  - 事件持久化到知识库，供因果网络和元认知回溯
  - 模块间反馈闭环：因果网络→假设生成器→风险预测→巡逻

使用：
  from engine.event_bus import bus
  bus.subscribe("causal_edge_discovered", on_new_causal_edge)
  bus.publish("causal_edge_discovered", {"signals": [...], "finding": "..."})
"""
import json, os, time, threading
from datetime import datetime
from typing import Callable, Dict, List, Any
from collections import defaultdict


class EventBus:
    """全局事件总线 —— 税务AGI的神经系统"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._event_log: List[Dict] = []  # 持久化事件日志
        self._lock = threading.Lock()
        self._max_log = 500
        self._persist_path = None
    
    def subscribe(self, event_type: str, callback: Callable):
        """订阅事件类型。callback(event_data) 在事件发生时被调用"""
        with self._lock:
            self._subscribers[event_type].append(callback)
    
    def publish(self, event_type: str, data: Dict[str, Any], source: str = ""):
        """发布事件。通知所有订阅者，记录事件日志"""
        event = {
            "type": event_type,
            "data": data,
            "source": source,
            "timestamp": datetime.now().isoformat(),
            "id": f"evt_{len(self._event_log):06d}",
        }
        with self._lock:
            self._event_log.append(event)
            if len(self._event_log) > self._max_log:
                self._event_log = self._event_log[-self._max_log:]
        
        # 通知订阅者（在锁外执行，避免死锁）
        subs = list(self._subscribers.get(event_type, []))
        for cb in subs:
            try:
                cb(data)
            except Exception as e:
                pass  # 一个订阅者报错不影响其他
    
    def get_recent_events(self, event_type: str = None, limit: int = 50) -> List[Dict]:
        """获取最近的事件"""
        events = self._event_log
        if event_type:
            events = [e for e in events if e["type"] == event_type]
        return events[-limit:]
    
    def get_cross_module_chains(self) -> List[Dict]:
        """提取跨模块因果链：事件A（来自模块X）→ 事件B（来自模块Y）→ ..."""
        chains = []
        recent = self._event_log[-100:]
        # 按时间窗口(60秒)分组事件，在同一窗口内的不同模块事件形成链
        if len(recent) < 2:
            return chains
        window = 60
        i = 0
        while i < len(recent):
            chain = [recent[i]]
            base_ts = datetime.fromisoformat(recent[i]["timestamp"])
            j = i + 1
            while j < len(recent):
                ts_j = datetime.fromisoformat(recent[j]["timestamp"])
                if (ts_j - base_ts).total_seconds() <= window and recent[j]["source"] != chain[-1]["source"]:
                    chain.append(recent[j])
                else:
                    break
                j += 1
            if len(chain) >= 3:
                chains.append({
                    "events": [{"type": c["type"], "source": c["source"]} for c in chain],
                    "span": (datetime.fromisoformat(chain[-1]["timestamp"]) - base_ts).total_seconds(),
                })
            i = j if j > i + 1 else i + 1
        return chains
    
    def persist_log(self, filepath: str = None):
        """持久化事件日志"""
        if filepath:
            self._persist_path = filepath
        if not self._persist_path:
            self._persist_path = os.path.join(os.path.dirname(__file__), "..", "static", "event_log.json")
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump({
                    "updated_at": datetime.now().isoformat(),
                    "total_events": len(self._event_log),
                    "events": self._event_log[-200:],
                }, f, ensure_ascii=False, indent=2, default=str)
        except:
            pass
    
    def get_summary(self) -> Dict:
        """获取总线概况"""
        with self._lock:
            types = Counter(e["type"] for e in self._event_log)
            sources = Counter(e["source"] for e in self._event_log)
            return {
                "total_events": len(self._event_log),
                "active_subscribers": sum(len(v) for v in self._subscribers.values()),
                "event_types": list(self._subscribers.keys()),
                "top_event_types": types.most_common(10),
                "top_sources": sources.most_common(10),
                "cross_module_chains": len(self.get_cross_module_chains()),
            }


# ── 全局单例 ──
bus = EventBus()


# ── 预定义事件类型 ──
class AGIEvents:
    """税务AGI标准事件类型"""
    # 因果网络
    CAUSAL_EDGE_DISCOVERED = "causal_edge_discovered"
    CAUSAL_PATTERN_FORMED = "causal_pattern_formed"
    
    # 假设生成
    HYPOTHESIS_GENERATED = "hypothesis_generated"
    HYPOTHESIS_CONFIRMED = "hypothesis_confirmed"
    HYPOTHESIS_REFUTED = "hypothesis_refuted"
    
    # 自愈
    SELF_HEALING_RULE_CREATED = "self_healing_rule_created"
    ERROR_DETECTED = "error_detected"
    AUTO_CORRECTION_APPLIED = "auto_correction_applied"
    
    # 巡逻
    PATROL_TRIGGERED = "patrol_triggered"
    PATROL_SIGNIFICANT_CHANGE = "patrol_significant_change"
    
    # 知识库
    KNOWLEDGE_GROWN = "knowledge_grown"
    NEW_SIGNAL_PATTERN = "new_signal_pattern"
    
    # 元认知
    UNCERTAINTY_DETECTED = "uncertainty_detected"
    REASONING_GAP_FOUND = "reasoning_gap_found"
    
    # 分析
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETED = "analysis_completed"
    FINDING_GENERATED = "finding_generated"


# 自动持久化（每100条事件触发一次）
_persist_counter = [0]

def _auto_persist_wrapper(data):
    _persist_counter[0] += 1
    if _persist_counter[0] % 100 == 0:
        bus.persist_log()

bus.subscribe("*", _auto_persist_wrapper)


from collections import Counter

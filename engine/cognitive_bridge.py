# ══════════════════════════════════════════════════════════════
# 认知桥接层 — 感知→记忆→思考的事件驱动通信
# 2026-07-16 新建：补齐智能引擎中枢五环路闭环通信
# ══════════════════════════════════════════════════════════════

import time
import json
import os

# ── 广播事件类型 ──
EVENT_PHASE_COMPLETE = "phase_complete"
EVENT_FINDING_GENERATED = "finding_generated"
EVENT_PATTERN_MATCHED = "pattern_matched"
EVENT_ANOMALY_DETECTED = "anomaly_detected"

# ── 事件日志 ──
_bridge_log = []

def broadcast(phase_name, data, pipeline_log=None):
    """感知层广播：Phase 完成时向事件总线广播"""
    event = {
        "event": EVENT_PHASE_COMPLETE,
        "phase": phase_name,
        "timestamp": time.time(),
        "data": data,
    }
    _bridge_log.append(event)
    msg = f"[认知桥接] 广播: {phase_name} 完成"
    if pipeline_log is not None:
        pipeline_log.append(msg)
    # 触发 P0 记忆匹配
    _memory_match(event, pipeline_log)
    return event


def _memory_match(event, pipeline_log=None):
    """记忆层：收到广播后匹配经验模式（P0/P1/P2 推送）"""
    phase = event.get("phase", "")
    data = event.get("data", {})
    matches = []

    if phase == "phase1_triage":
        matches = _push_industry_pattern(data, pipeline_log)
    elif phase == "phase2_deep_dive":
        matches = _push_signal_pattern(data, pipeline_log)
    elif phase == "phase3_cross_validate":
        matches = _push_cross_pattern(data, pipeline_log)
    elif phase == "phase4_synthesis":
        matches = _push_closing_pattern(data, pipeline_log)

    event["matches"] = matches
    return matches


def _push_industry_pattern(data, pipeline_log=None):
    """P0 推送 — 行业模式匹配"""
    industry = str(data.get("industry", ""))
    matches = []
    if industry:
        # 基于行业的 P1 推送
        matches.append({
            "priority": "P1",
            "action": f"行业经验匹配: {industry}",
            "suggestion": "加载行业TOP5高风险科目和基准偏离阈值",
        })
    if pipeline_log is not None:
        pipeline_log.append(f"[记忆层] P1 行业推送: {industry}")
    return matches


def _push_signal_pattern(data, pipeline_log=None):
    """P0/P2 推送 — 信号模式匹配"""
    matches = []
    findings = data.get("findings", [])
    high_count = sum(1 for f in findings if str(f.get("level", "")) in ("高风险", "极高风险"))
    if high_count >= 3:
        matches.append({
            "priority": "P0",
            "action": f"模式骨架匹配: 高风险信号密集({high_count}条)",
            "suggestion": "最高级别警报，建议立即启动深入核查",
        })
    else:
        matches.append({
            "priority": "P2",
            "action": "通用规则匹配",
            "suggestion": "指标偏离行业基准，作为补充输入",
        })
    if pipeline_log is not None:
        pipeline_log.append(f"[记忆层] 信号推送: {len(findings)}条发现 P0={high_count>=3}")
    return matches


def _push_cross_pattern(data, pipeline_log=None):
    """跨域模式推送"""
    matches = []
    conflicts = data.get("conflicts", 0)
    enhancements = data.get("enhancements", 0)
    if conflicts > 0:
        matches.append({"priority": "P1", "action": f"跨域矛盾消解: {conflicts}处", "suggestion": "检查协商结果是否自洽"})
    if enhancements > 0:
        matches.append({"priority": "P1", "action": f"多域增强: {enhancements}处联合增强", "suggestion": "合成发现的置信度需要额外验证"})
    if pipeline_log is not None:
        pipeline_log.append(f"[记忆层] 跨域推送: 矛盾{conflicts} 增强{enhancements}")
    return matches


def _push_closing_pattern(data, pipeline_log=None):
    """定案阶段推送"""
    matches = []
    total = data.get("total_findings", 0)
    high = data.get("high_risk", 0)
    if high > 0:
        matches.append({"priority": "P0", "action": f"定案推送: {high}/{total}条高风险", "suggestion": "建议启动红队证伪流程"})
    if pipeline_log is not None:
        pipeline_log.append(f"[记忆层] 定案推送: {high}条高风险/{total}条总计")
    return matches


# ── 拓扑模式骨架提取（学习层） ──
def extract_topology_pattern(all_findings, target_entity, pipeline_log=None):
    """从分析结果中提取违法模式骨架（三维拓扑）"""
    pattern = {
        "timestamp": time.time(),
        "entity": str(target_entity.get("name", "")) if target_entity else "",
        "fund_flow": [],   # 资金流向拓扑
        "relation": [],     # 关联关系拓扑
        "invoice_flow": [], # 发票流向拓扑
        "risk_score": 0,
    }
    high_findings = [f for f in all_findings if str(f.get("level", "")) in ("高风险", "极高风险")]
    pattern["risk_score"] = len(high_findings)
    for f in high_findings:
        ftype = str(f.get("type", ""))
        detail = str(f.get("detail", ""))
        if "资金" in ftype or "收款" in ftype or "银行" in ftype:
            pattern["fund_flow"].append({"type": ftype, "summary": detail[:100]})
        if "关联" in ftype or "同一" in ftype or "重叠" in ftype:
            pattern["relation"].append({"type": ftype, "summary": detail[:100]})
        if "发票" in ftype or "进" in ftype or "销" in ftype or "品名" in ftype:
            pattern["invoice_flow"].append({"type": ftype, "summary": detail[:100]})
    # 持久化模式骨架
    _save_pattern(pattern)
    if pipeline_log is not None:
        pipeline_log.append(f"[学习层] 模式骨架提取: 资金{len(pattern['fund_flow'])} 关联{len(pattern['relation'])} 发票{len(pattern['invoice_flow'])}")
    return pattern


def _save_pattern(pattern):
    """保存模式骨架到模式库"""
    try:
        patterns_dir = os.path.join(os.path.dirname(__file__), "..", "static", "patterns")
        os.makedirs(patterns_dir, exist_ok=True)
        ts = int(pattern["timestamp"])
        filename = f"pattern_{ts}.json"
        filepath = os.path.join(patterns_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(pattern, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── 中间评审（中断机制） ──
def mid_review(hypothesis_a, hypothesis_b, pipeline_log=None):
    """当记忆层P0推送与思考层当前假设方向相反时，触发中间评审"""
    result = {
        "conflict": True,
        "hypothesis_a": str(hypothesis_a)[:80],
        "hypothesis_b": str(hypothesis_b)[:80],
        "decision": "continue_current",  # continue_current / switch / escalate
        "reason": "",
    }
    # 简单裁决：P0 推送优先级高于当前假设
    result["decision"] = "switch"
    result["reason"] = "P0模式匹配优先级高于当前推理路径"
    if pipeline_log is not None:
        pipeline_log.append(f"[中间评审] P0冲突裁决: {result['decision']}")
    return result

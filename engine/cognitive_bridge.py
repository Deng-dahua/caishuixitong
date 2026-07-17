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
    # P0：已验证通用模式库（经验直觉——扛住红队攻击的模式骨架优先推送）
    try:
        from engine.evolution import get_verified_patterns
        verified = get_verified_patterns()
        if verified:
            matches.append({
                "priority": "P0",
                "action": f"已验证通用模式库: {len(verified)}个模式在库",
                "suggestion": "本次分析将与已验证模式骨架优先比对，命中即最高级别警报",
            })
            if pipeline_log is not None:
                pipeline_log.append(f"[记忆层] P0 直觉推送: {len(verified)}个已验证通用模式加载")
    except Exception:
        pass
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
    """P0/P2 推送 — 信号模式匹配

    兼容两种广播格式：findings 可以是发现列表，也可以是数量(int)。
    """
    matches = []
    findings = data.get("findings", [])
    if isinstance(findings, (int, float)):
        total_count = int(findings)
        high_count = int(data.get("high_findings", 0) or 0)
    else:
        total_count = len(findings)
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
        pipeline_log.append(f"[记忆层] 信号推送: {total_count}条发现 P0={high_count>=3}")
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
    """从分析结果中提取违法模式骨架（三维拓扑）并计算与历史模式的相似度"""
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
    # 计算与历史模式的拓扑相似度
    similarity = _compute_topology_similarity(pattern, pipeline_log)
    pattern["topology_match"] = similarity
    _save_pattern(pattern)
    if pipeline_log is not None:
        pipeline_log.append(
            f"[学习层] 模式骨架: 资金{len(pattern['fund_flow'])} 关联{len(pattern['relation'])} "
            f"发票{len(pattern['invoice_flow'])} 与历史最高相似度{similarity['best_score']:.1%}"
        )
    return pattern


# ── 拓扑相似度计算（图编辑距离） ──
def _compute_topology_similarity(current_pattern, pipeline_log=None):
    """计算当前模式与模式库中所有历史模式的拓扑相似度"""
    patterns = _load_pattern_library()
    if not patterns:
        return {"best_score": 0, "best_match": None, "matches": []}
    results = []
    for hist in patterns:
        score = _graph_edit_similarity(current_pattern, hist)
        if score > 0:
            results.append({"entity": hist.get("entity", ""), "score": score, "timestamp": hist.get("timestamp", 0)})
    results.sort(key=lambda x: x["score"], reverse=True)
    best = results[0] if results else {"entity": None, "score": 0}
    if results and best["score"] >= 0.8:
        if pipeline_log is not None:
            pipeline_log.append(f"[拓扑匹配·P0] 相似度≥80% 匹配到历史模式: {best['entity']}")
    return {"best_score": best["score"], "best_match": best.get("entity"), "matches": results[:3]}


def _graph_edit_similarity(p1, p2):
    """计算两个模式骨架的图编辑相似度"""
    if not p1 or not p2:
        return 0
    # 比较三维拓扑的Jaccard相似度
    scores = []
    for dim in ("fund_flow", "relation", "invoice_flow"):
        types1 = {item.get("type", "") for item in p1.get(dim, [])}
        types2 = {item.get("type", "") for item in p2.get(dim, [])}
        if types1 and types2:
            intersection = len(types1 & types2)
            union = len(types1 | types2)
            dim_score = intersection / union if union > 0 else 0
        elif not types1 and not types2:
            dim_score = 1.0
        else:
            dim_score = 0.5
        scores.append(dim_score)
    return sum(scores) / len(scores)


def _load_pattern_library():
    """加载历史模式库"""
    patterns_dir = os.path.join(os.path.dirname(__file__), "..", "static", "patterns")
    if not os.path.exists(patterns_dir):
        return []
    patterns = []
    for fname in os.listdir(patterns_dir):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(patterns_dir, fname), "r", encoding="utf-8") as f:
                    patterns.append(json.load(f))
            except Exception:
                pass
    return patterns


# ── 自愈反馈闭环：盲测崩塌点写入自愈规则库 ──
def self_heal_from_blind_test(blind_results, all_findings, pipeline_log=None):
    """盲测发现证据崩塌点后，自动写入自愈规则库"""
    collapsed = [f for f in all_findings if f.get("_blind_test", "").startswith("崩塌")]
    if not collapsed:
        return
    # 将崩塌的证据节点标记为不可靠
    heal_rules = []
    for f in collapsed:
        ftype = str(f.get("type", ""))
        heal_rules.append({
            "timestamp": time.time(),
            "trigger": f"盲测崩塌: {ftype}",
            "action": "增加交叉验证要求",
            "detail": "原来需要2个独立来源的提升到3个，原来需要3个的提升到4个",
        })
    # 写入自愈规则库
    try:
        heal_path = os.path.join(os.path.dirname(__file__), "..", "static", "self_heal_rules.json")
        existing = []
        if os.path.exists(heal_path):
            with open(heal_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        existing.extend(heal_rules)
        with open(heal_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    if pipeline_log is not None:
        pipeline_log.append(f"[自愈闭环] 盲测{len(collapsed)}个崩塌点已写入自愈规则库")


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

# ══════════════════════════════════════════════════════════════
# 进化引擎 — P2：经验直觉系统 + 秘笈自更新
# 2026-07-17 新建
#
# 经验直觉系统：
#   模式骨架匹配验证 → 置信度升降 → ≥3企业+≥2行业 → 对抗验证
#   → 升级"已验证通用模式"（下次分析P0推送）
#   连续误报 → 自动降级或暂停
#
# 秘笈自更新：
#   每次分析后对比方法论七层执行情况 → 未触发步骤计数标记"待验证"
#   → 新发现类型不在秘笈覆盖范围 → 写入补充建议节点等稽查员审核
# ══════════════════════════════════════════════════════════════

import json
import os
import time

_CONFIDENCE_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "pattern_confidence.json")

# 置信度参数（老稽查员的直觉养成规律）
_CONF_INIT = 0.5          # 新模式初始置信度
_CONF_STEP_UP = 0.1       # 验证通过 +0.1
_CONF_STEP_DOWN = 0.1     # 误报 -0.1
_CONF_DEMOTE = 0.2        # 低于此值降级暂停
_PROMOTE_ENTITIES = 3     # 升级需 ≥3 家企业验证
_PROMOTE_INDUSTRIES = 2   # 升级需 ≥2 个行业验证


def _load_confidence_lib():
    if os.path.exists(_CONFIDENCE_PATH):
        try:
            with open(_CONFIDENCE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_confidence_lib(lib):
    try:
        os.makedirs(os.path.dirname(_CONFIDENCE_PATH), exist_ok=True)
        with open(_CONFIDENCE_PATH, "w", encoding="utf-8") as f:
            json.dump(lib, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _pattern_signature(pattern):
    """模式骨架签名：三维拓扑的类型集合，跨企业跨行业可比"""
    parts = []
    for dim in ("fund_flow", "relation", "invoice_flow"):
        types = sorted({str(item.get("type", ""))[:30] for item in pattern.get(dim, []) if item.get("type")})
        parts.append(dim[:4] + ":" + "|".join(types[:5]))
    return ";".join(parts)


def evolve_pattern_confidence(topology_pattern, industry="", pipeline_log=None):
    """经验直觉系统核心：模式匹配后的置信度进化。

    - 当前分析的骨架签名入库（首次 0.5）
    - 匹配到历史模式（相似度≥80%）→ 双方置信度 +0.1（这就是"直觉"变准）
    - 记录验证企业和行业 → 满足 ≥3企业+≥2行业 → 对抗验证 → 升级通用模式
    - 置信度 ≤0.2 → 降级暂停（连续误报的直觉不能再信）
    """
    result = {"signature": "", "confidence": 0, "status": "", "promoted": False}
    if not topology_pattern or not any(
        topology_pattern.get(d) for d in ("fund_flow", "relation", "invoice_flow")
    ):
        return result

    lib = _load_confidence_lib()
    sig = _pattern_signature(topology_pattern)
    entity = str(topology_pattern.get("entity", ""))
    result["signature"] = sig

    entry = lib.get(sig) or {
        "confidence": _CONF_INIT,
        "status": "观察中",
        "entities": [],
        "industries": [],
        "created": time.time(),
        "verify_count": 0,
        "misfire_count": 0,
    }

    # 记录本次验证的企业和行业
    if entity and entity not in entry["entities"]:
        entry["entities"].append(entity)
    if industry and industry not in entry["industries"]:
        entry["industries"].append(industry)

    # 匹配到历史模式 → 验证通过 → 置信度上升
    match = topology_pattern.get("topology_match") or {}
    if match.get("best_score", 0) >= 0.8:
        entry["confidence"] = min(1.0, entry["confidence"] + _CONF_STEP_UP)
        entry["verify_count"] = entry.get("verify_count", 0) + 1
        if pipeline_log is not None:
            pipeline_log.append(
                f"[进化引擎] 直觉验证: 骨架匹配{match['best_score']:.0%} "
                f"置信度→{entry['confidence']:.1f} 验证{entry['verify_count']}次"
            )

    # 升级判定：≥3企业 + ≥2行业 → 对抗验证 → 已验证通用模式
    if (
        entry["status"] == "观察中"
        and len(entry["entities"]) >= _PROMOTE_ENTITIES
        and len(entry["industries"]) >= _PROMOTE_INDUSTRIES
    ):
        if _adversarial_verify(topology_pattern, pipeline_log):
            entry["status"] = "已验证通用模式"
            entry["confidence"] = max(entry["confidence"], 0.9)
            result["promoted"] = True
            if pipeline_log is not None:
                pipeline_log.append(
                    f"[进化引擎·升级] 模式骨架扛住红队攻击，升级为已验证通用模式"
                    f"（{len(entry['entities'])}企业/{len(entry['industries'])}行业）"
                )
        else:
            entry["misfire_count"] = entry.get("misfire_count", 0) + 1
            if pipeline_log is not None:
                pipeline_log.append("[进化引擎] 对抗验证未通过，模式保持观察中")

    # 降级判定：置信度过低 → 暂停
    if entry["confidence"] <= _CONF_DEMOTE and entry["status"] != "已暂停":
        entry["status"] = "已暂停"
        if pipeline_log is not None:
            pipeline_log.append(f"[进化引擎·降级] 模式置信度{entry['confidence']:.1f}过低，暂停推送")

    entry["updated"] = time.time()
    lib[sig] = entry
    _save_confidence_lib(lib)
    result["confidence"] = entry["confidence"]
    result["status"] = entry["status"]
    return result


def _adversarial_verify(pattern, pipeline_log=None):
    """对抗验证：红队模拟辩护方，从三个角度攻击模式骨架。

    资金流向→合法商业解释 / 关联关系→合理组织结构 / 发票流向→行业惯例。
    只有三个维度都有独立信号支撑（非单维度模式）才算扛住攻击。
    """
    dims_with_signal = sum(
        1 for d in ("fund_flow", "relation", "invoice_flow") if pattern.get(d)
    )
    # 攻击逻辑：单维度模式容易被"行业惯例/合理结构"解释掉，≥2维联合信号才立得住
    survived = dims_with_signal >= 2
    if pipeline_log is not None:
        pipeline_log.append(
            f"[对抗验证] {dims_with_signal}/3维度有信号 → {'扛住攻击' if survived else '被击破(单维可解释)'}"
        )
    return survived


def get_verified_patterns():
    """获取所有已验证通用模式（记忆层P0推送数据源）"""
    lib = _load_confidence_lib()
    return {sig: e for sig, e in lib.items() if e.get("status") == "已验证通用模式"}


# ══════════════ 秘笈自更新 ══════════════

_UNTRIGGERED_THRESHOLD = 10  # 连续N次分析未触发 → 标记待验证


def update_methodology_suggestions(pipeline_log, all_findings):
    """秘笈自更新：分析结果反向写入方法论配置。

    ① 七层执行完整性对比 → 未触发层累计计数 → 达阈值标记"待验证"
    ② 新发现类型不在秘笈方法论覆盖范围 → 写入 pending_suggestions 等稽查员审核
    审核通过前秘笈正文不变——引擎只提建议，定夺权在稽查员。
    """
    summary = {"untriggered": [], "new_suggestions": 0}
    try:
        from engine.methodology_loader import (
            load_methodology_config, save_methodology_config, validate_execution,
            METHODOLOGY_KNOWLEDGE,
        )
        config = load_methodology_config()

        # ① 七层执行完整性
        validation = validate_execution(pipeline_log or [])
        su = config.get("self_update") or {"untriggered_counts": {}, "pending_suggestions": []}
        counts = su.get("untriggered_counts") or {}
        for name in validation.get("missing", []):
            counts[name] = counts.get(name, 0) + 1
            if counts[name] >= _UNTRIGGERED_THRESHOLD:
                summary["untriggered"].append(name)
        for name in validation.get("executed", []):
            counts.pop(name, None)  # 触发过就清零
        su["untriggered_counts"] = counts

        # ② 新模式发现：高风险发现类型未被秘笈方法论覆盖 → 补充建议
        known_text = json.dumps(config.get("layers", []), ensure_ascii=False) + json.dumps(
            [m.get("name", "") + m.get("description", "") for m in METHODOLOGY_KNOWLEDGE.get("methodologies", [])],
            ensure_ascii=False,
        )
        existing_sugs = {s.get("type", "") for s in su.get("pending_suggestions", [])}
        high_findings = [f for f in (all_findings or []) if str(f.get("level", "")) in ("高风险", "极高风险")]
        for f in high_findings:
            ftype = str(f.get("type", ""))[:40]
            if not ftype or ftype in existing_sugs:
                continue
            # 类型关键词完全不在秘笈文本中 → 秘笈没覆盖的新手法
            key = ftype.replace("风险", "").replace("异常", "")[:12]
            if key and key not in known_text:
                su.setdefault("pending_suggestions", []).append({
                    "type": ftype,
                    "suggestion": f"发现秘笈未覆盖的风险类型「{ftype}」，建议评估是否补充为方法论检测项",
                    "status": "待稽查员审核",
                    "created": time.time(),
                })
                existing_sugs.add(ftype)
                summary["new_suggestions"] += 1

        # 建议上限：只保留最近51720条，防止无限增长
        su["pending_suggestions"] = (su.get("pending_suggestions") or [])[-50:]
        config["self_update"] = su
        save_methodology_config(config)

        if pipeline_log is not None:
            if summary["untriggered"]:
                pipeline_log.append(f"[秘笈自更新] {len(summary['untriggered'])}层连续未触发已标记待验证: {summary['untriggered']}")
            if summary["new_suggestions"]:
                pipeline_log.append(f"[秘笈自更新] {summary['new_suggestions']}条新模式补充建议已写入，等待稽查员审核")
    except Exception as e:
        if pipeline_log is not None:
            pipeline_log.append(f"[秘笈自更新] ERROR: {e}")
    return summary

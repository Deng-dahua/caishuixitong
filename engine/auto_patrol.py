"""
自动巡逻模块 —— 定期重新分析已分析过的企业，检测AGI学习效果

巡逻逻辑：
  1. 每次分析完成后，记录分析结果快照
  2. 当AGI知识库发生重大变化（因果边/模式增加），触发巡逻
  3. 对最近N家企业重新分析，对比前后结论
  4. 如果结论显著变化 → 说明AGI在学习；如果结论不变 → 说明AGI还没学到这个企业的关键模式
  5. 巡逻报告写入知识库，供闭环自检使用
"""
import json, os, time
from datetime import datetime
from collections import Counter
from typing import Dict, List, Any, Optional

# 巡逻配置
PATROL_CONFIG = {
    "max_companies_per_patrol": 5,    # 每次巡逻最多重新分析5家企业
    "significant_change_threshold": 2,  # 因果边或模式增加>=1720条时触发巡逻
    "finding_change_ratio_threshold": 0.3,  # 结论变化超过30%时标记为"显著变化"
    "patrol_interval_hours": 1,  # 最短巡逻间隔1小时
}


def should_trigger_patrol(kb_stats_before: Dict, kb_stats_after: Dict) -> bool:
    """判断是否需要触发巡逻
    
    触发条件：因果边或模式增加达到阈值
    """
    edges_before = kb_stats_before.get("causal_edges_count", 0)
    edges_after = kb_stats_after.get("causal_edges_count", 0)
    patterns_before = kb_stats_before.get("patterns_count", 0)
    patterns_after = kb_stats_after.get("patterns_count", 0)
    
    edges_added = edges_after - edges_before
    patterns_added = patterns_after - patterns_before
    
    return edges_added >= PATROL_CONFIG["significant_change_threshold"] or \
           patterns_added >= PATROL_CONFIG["significant_change_threshold"]


def compare_findings(old_findings: List[Dict], new_findings: List[Dict]) -> Dict:
    """对比两次分析的结论，返回变化报告"""
    old_types = Counter(f.get("type", "") for f in old_findings)
    new_types = Counter(f.get("type", "") for f in new_findings)
    
    added = set(new_types) - set(old_types)
    removed = set(old_types) - set(new_types)
    common = set(old_types) & set(new_types)
    
    changed = []
    for ft in common:
        old_count = old_types[ft]
        new_count = new_types[ft]
        if old_count != new_count:
            changed.append({
                "finding_type": ft,
                "old_count": old_count,
                "new_count": new_count,
                "change": new_count - old_count,
            })
    
    total_old = sum(old_types.values())
    total_new = sum(new_types.values())
    change_ratio = abs(total_new - total_old) / max(total_old, 1)
    
    return {
        "added_findings": list(added),
        "removed_findings": list(removed),
        "changed_counts": changed,
        "total_old": total_old,
        "total_new": total_new,
        "change_ratio": round(change_ratio, 3),
        "is_significant": change_ratio >= PATROL_CONFIG["finding_change_ratio_threshold"],
    }


def run_patrol(company_ids: List[int], db, knowledge_base_snapshot: Dict) -> Dict:
    """执行巡逻：对指定企业重新分析，对比前后结论
    
    巡逻逻辑：
    1. 从 cross_analysis_memory.json 加载该企业上次分析的结论快照
    2. 重新运行 _run_analyze 获取新结论
    3. 逐维度对比：
       - 风险等级变化（升降级）
       - 发现数量变化（新增/消失/增减）
       - 风险类型分布变化
    4. 生成巡逻对比报告
    """
    from main import _run_analyze
    from engine.knowledge_base import get_kb
    
    # 加载跨分析记忆（上次结论快照）
    cross_memory = _load_cross_memory()
    patrol_memories = cross_memory.get("patrol_snapshots", {})
    
    results = []
    for cid in company_ids[:PATROL_CONFIG["max_companies_per_patrol"]]:
        try:
            cid_str = str(cid)
            # 获取上次分析结论快照
            last_snapshot = patrol_memories.get(cid_str, None)
            old_findings = last_snapshot.get("findings", []) if last_snapshot else []
            old_risk_count = last_snapshot.get("risk_counts", {}) if last_snapshot else {}
            
            # 重新分析
            result = _run_analyze(cid, db)
            new_findings = result.get("findings", []) if isinstance(result, dict) else []
            
            # ── 对比分析 ──
            comparison = _deep_compare_findings(old_findings, new_findings, old_risk_count)
            
            # ── 保存本次快照 ──
            patrol_memories[cid_str] = {
                "timestamp": datetime.now().isoformat(),
                "findings": _extract_finding_sigs(new_findings),
                "risk_counts": _count_risk_levels(new_findings),
                "total_findings": len(new_findings),
            }
            
            results.append({
                "company_id": cid,
                "status": "completed",
                "old_findings_count": len(old_findings),
                "new_findings_count": len(new_findings),
                "comparison": comparison,
            })
        except Exception as e:
            results.append({
                "company_id": cid,
                "status": "error",
                "error": str(e),
            })
    
    # 持久化巡逻快照
    cross_memory["patrol_snapshots"] = patrol_memories
    _save_cross_memory(cross_memory)
    
    # 汇总巡逻报告
    completed = [r for r in results if r.get("status") == "completed"]
    return {
        "patrol_time": datetime.now().isoformat(),
        "companies_checked": len(results),
        "companies_with_changes": sum(1 for r in completed if r.get("comparison", {}).get("is_significant")),
        "knowledge_snapshot": knowledge_base_snapshot,
        "results": results,
    }


def _deep_compare_findings(old_findings: List[Dict], new_findings: List[Dict], old_risk: Dict) -> Dict:
    """深度对比两次分析的结论
    
    对比维度：
    1. 发现数量变化
    2. 风险等级迁移（升级/降级/新增/消失）
    3. 风险类型变化
    4. 高/中/低风险分布变化
    """
    if not old_findings and not new_findings:
        return {"is_significant": False, "summary": "无历史数据与新数据对比"}
    
    if not old_findings:
        return {
            "is_significant": False,
            "summary": f"首次巡逻，{len(new_findings)}条发现",
            "new_findings_count": len(new_findings),
        }
    
    # 提取新旧发现的类型签名
    old_sigs = {_finding_sig(f): f for f in old_findings}
    new_sigs = {_finding_sig(f): f for f in new_findings}
    
    old_keys = set(old_sigs.keys())
    new_keys = set(new_sigs.keys())
    
    added = new_keys - old_keys
    removed = old_keys - new_keys
    kept = old_keys & new_keys
    
    # 风险等级变化
    risk_changes = []
    for k in kept:
        old_level = old_sigs[k].get("level", "")
        new_level = new_sigs[k].get("level", "")
        if old_level != new_level:
            risk_changes.append({
                "finding": k[:80],
                "old_level": old_level,
                "new_level": new_level,
            })
    
    # 风险分布对比
    new_risk = _count_risk_levels(new_findings)
    
    change_ratio = (len(added) + len(removed)) / max(len(old_findings), 1)
    is_sig = change_ratio >= PATROL_CONFIG["finding_change_ratio_threshold"] or len(risk_changes) > 0
    
    parts = []
    if len(added) > 0:
        parts.append(f"新增{len(added)}条发现")
    if len(removed) > 0:
        parts.append(f"消失{len(removed)}条发现")
    if len(risk_changes) > 0:
        parts.append(f"{len(risk_changes)}条风险等级变化")
    if not parts:
        parts.append("结论无明显变化")
    
    return {
        "is_significant": is_sig,
        "summary": "；".join(parts),
        "added_count": len(added),
        "removed_count": len(removed),
        "risk_changes": risk_changes,
        "old_risk_distribution": old_risk,
        "new_risk_distribution": new_risk,
        "change_ratio": round(change_ratio, 3),
    }


def _finding_sig(finding: Dict) -> str:
    """生成发现的唯一签名（用于去重对比）"""
    domain = finding.get("domain", "") or finding.get("type", "")
    detail = finding.get("detail", "") or finding.get("description", "")
    return f"{domain}|{detail[:80]}"


def _extract_finding_sigs(findings: List[Dict]) -> List[Dict]:
    """提取发现的关键签名用于快照存储"""
    return [{"s": _finding_sig(f), "l": f.get("level", ""), "d": (f.get("domain", "") or f.get("type", ""))[:60]} for f in findings]


def _count_risk_levels(findings: List[Dict]) -> Dict:
    """统计各风险等级数量"""
    counts = {"高": 0, "中": 0, "低": 0}
    for f in findings:
        level = f.get("level", "")
        if "高" in str(level):
            counts["高"] += 1
        elif "中" in str(level):
            counts["中"] += 1
        elif "低" in str(level):
            counts["低"] += 1
    counts["总计"] = len(findings)
    return counts


def _load_cross_memory() -> Dict:
    """加载跨分析记忆"""
    path = os.path.join(os.path.dirname(__file__), "..", "static", "cross_analysis_memory.json")
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {"patrol_snapshots": {}, "industry_patterns": {}, "lessons": []}


def _save_cross_memory(data: Dict):
    """保存跨分析记忆"""
    path = os.path.join(os.path.dirname(__file__), "..", "static", "cross_analysis_memory.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


# ═══ v2.0 巡逻升级：因果影响分析 ═══

def causal_impact_patrol(new_causal_edges: List[Dict], company_ids: List[int], db) -> Dict:
    """
    因果影响分析：新发现的因果边会影响哪些企业的哪些结论？
    
    不再盲目重跑所有企业，而是计算每条新因果边的"影响半径"——
    只对信号匹配的企业定向重分析。
    """
    results = []
    patrol_memories = _load_cross_memory().get("patrol_snapshots", {})
    
    for edge in new_causal_edges[:10]:
        signals = edge.get("signals", [])
        finding = edge.get("finding", "")
        confidence = edge.get("confidence", 0)
        
        if confidence < 0.5:
            continue
        
        # 检查每家企业是否有匹配的信号
        impacted_companies = []
        for cid in company_ids:
            cid_str = str(cid)
            snapshot = patrol_memories.get(cid_str, {})
            prev_findings = snapshot.get("findings", [])
            
            # 匹配：该企业的历史结论是否包含该因果边的信号
            matched_findings = []
            for pf in prev_findings:
                pf_text = str(pf.get("s", "")) + str(pf.get("d", ""))
                if any(sig in pf_text for sig in signals):
                    matched_findings.append(pf)
            
            if matched_findings:
                impacted_companies.append({
                    "company_id": cid,
                    "matched_signals_count": len(matched_findings),
                    "findings_to_review": [
                        {"signature": mf["s"][:80], "domain": mf.get("d", "")}
                        for mf in matched_findings[:5]
                    ],
                })
        
        if impacted_companies:
            results.append({
                "causal_edge": {
                    "signals": signals,
                    "finding": finding,
                    "confidence": confidence,
                },
                "impacted_companies": len(impacted_companies),
                "companies": impacted_companies[:5],
            })
    
    return {
        "total_edges_evaluated": len(new_causal_edges),
        "edges_with_impact": len(results),
        "total_impacted": sum(r["impacted_companies"] for r in results),
        "details": results,
        "recommendation": f"建议对{sum(r['impacted_companies'] for r in results)}家受影响企业执行定向巡逻" if results else "新因果边暂未影响已有分析",
    }


def smart_patrol_recommendation(kb_stats: Dict, db) -> Dict:
    """
    智能巡逻推荐：不是"知识库变了就巡逻"，而是"新知识可能影响谁就巡谁"
    
    返回：{should_patrol: bool, target_companies: [...], reason: str}
    """
    new_edges = kb_stats.get("new_causal_edges", [])
    if not new_edges:
        return {"should_patrol": False, "reason": "无新因果边生成"}
    
    company_ids = get_companies_to_patrol(db)
    if not company_ids:
        return {"should_patrol": False, "reason": "无可巡逻企业"}
    
    impact = causal_impact_patrol(new_edges, company_ids, db)
    
    if impact["total_impacted"] > 0:
        return {
            "should_patrol": True,
            "target_companies": company_ids,
            "reason": f"新因果边影响{impact['total_impacted']}家企业",
            "impact_analysis": impact,
        }
    else:
        return {
            "should_patrol": False,
            "reason": "新因果边暂未影响已有企业的结论",
            "impact_analysis": impact,
        }


def get_companies_to_patrol(db, max_count: int = None) -> List[int]:
    """获取需要巡逻的企业列表（最近分析过的N家企业）"""
    max_count = max_count or PATROL_CONFIG["max_companies_per_patrol"]
    
    try:
        from engine.knowledge_base import get_kb
        kb = get_kb()
        history = kb._data.get("analysis_history", [])
        # 按时间倒序，取最近N家
        recent = sorted(history, key=lambda h: h.get("timestamp", ""), reverse=True)
        company_names = []
        company_ids = []
        for h in recent:
            name = h.get("company_name", "")
            if name and name not in company_names:
                company_names.append(name)
                # 从数据库查找company_id
                try:
                    from database import Company
                    c = db.query(Company).filter(Company.name == name).first()
                    if c:
                        company_ids.append(c.id)
                except: pass
            if len(company_ids) >= max_count:
                break
        return company_ids
    except:
        return []


# ═══════════════════ 巡逻API ═══════════════════

def register_patrol_api(app):
    """注册巡逻相关的API端点"""
    
    @app.get("/api/agi/patrol/status")
    def get_patrol_status():
        """获取巡逻状态"""
        try:
            from engine.knowledge_base import get_kb
            kb = get_kb()
            stats = kb.get_full_knowledge()
            return {
                "ok": True,
                "knowledge_base": stats,
                "config": PATROL_CONFIG,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    @app.post("/api/agi/patrol/trigger")
    def trigger_patrol(db: Session = Depends(get_db)):
        """手动触发巡逻"""
        try:
            company_ids = get_companies_to_patrol(db)
            if not company_ids:
                return {"ok": False, "message": "没有可巡逻的企业"}
            
            kb_before = get_kb().get_full_knowledge()
            result = run_patrol(company_ids, db, kb_before)
            
            return {"ok": True, "result": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

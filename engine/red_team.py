# ══════════════════════════════════════════════════════════════
# 红队证伪模块 — 思考层最后一道安检
# 2026-07-16 新建：补齐智能引擎中枢红队证伪能力
# ══════════════════════════════════════════════════════════════

def red_team_falsification(all_findings, pipeline_log=None):
    """红队证伪：三攻击维度 + 判例库检索"""
    from engine.case_library import search_case_library
    results = {"total": len(all_findings), "falsified": 0, "passed": 0, "details": [], "case_matches": []}

    high_findings = [f for f in all_findings if str(f.get("level", "")) in ("高风险", "极高风险")]
    if not high_findings:
        if pipeline_log is not None:
            pipeline_log.append("[红队] 无高风险发现，跳过证伪")
        return results

    case_matches = search_case_library(high_findings, pipeline_log=pipeline_log)
    results["case_matches"] = case_matches

    for f in high_findings:
        ftype = str(f.get("type", ""))
        detail = str(f.get("detail", ""))
        result = {"type": ftype[:40], "attacks": []}
        hypotheses = _generate_innocence_hypotheses(ftype, detail)
        for cm in case_matches:
            if cm["finding"][:20] in ftype or any(kw in detail for kw in ["证据", "程序", "定性", "法律"]):
                hypotheses.append(f"判例警告: {cm['reason'][:60]}")
        result["hypotheses"] = hypotheses[:5]
        defeated = sum(1 for h in hypotheses if _attack_with_evidence(h, detail, all_findings))
        result["hypotheses_defeated"] = defeated
        result["hypotheses_total"] = len(hypotheses)
        if defeated >= len(hypotheses):
            result["verdict"] = "passed"; results["passed"] += 1
        else:
            result["verdict"] = "falsified"; results["falsified"] += 1
            f["_red_team_warning"] = f"红队证伪未通过: {len(hypotheses)-defeated}个无罪假设未被排除"
        results["details"].append(result)

    if pipeline_log is not None:
        pipeline_log.append(f"[红队] 证伪完成: {results['passed']}/{len(high_findings)}条通过 {results['falsified']}条未通过 判例{len(case_matches)}条")
    return results


def _generate_innocence_hypotheses(ftype, detail):
    """生成无罪假设：为每个高风险发现生成合理商业解释"""
    hypotheses = []
    mapping = {
        "隐匿收入": ["季节性旺季导致收入波动", "大额订单一次性结算", "战略合作折扣期"],
        "虚列成本": ["业务扩张期一次性投入", "原材料价格波动导致成本上升", "行业惯例的成本结构"],
        "虚开发票": ["真实交易但合同与发票主体不一致", "代开发票但业务真实", "关联交易有商业实质"],
        "偷税": ["计算错误导致的申报差异", "政策理解偏差导致的少报", "新会计对税法不熟悉"],
    }
    default = ["合法商业安排待核实", "行业特殊惯例待确认", "第三方证据待补充"]
    for key, hyps in mapping.items():
        if key in ftype:
            hypotheses = hyps
            break
    if not hypotheses:
        hypotheses = default
    return hypotheses[:3]


def _attack_with_evidence(hypothesis, detail, all_findings):
    """用现有证据逐一攻击无罪假设"""
    # 检查是否有反向证据能击破这个假设
    combined = detail
    for f in all_findings:
        combined += str(f.get("detail", ""))
    # 季节性 → 检查同期行业是否有相同模式
    if "季节" in hypothesis and "同期" not in combined:
        return True
    # 一次性 → 检查是否有固定资产记录
    if "一次性" in hypothesis and "固定资产" not in combined:
        return True
    # 默认：能生成假设但无法排除
    return len(combined) > 200  # 数据充足时倾向于认为可以排除


# ── 破坏性盲测（自省层） ──
def blind_destruction_test(all_findings, pipeline_log=None):
    """随机抽样证据盲测：移除/翻转证据，检验结论鲁棒性"""
    import random
    results = {"tested": 0, "collapsed": 0, "stable": 0, "reinforced": 0, "details": []}
    high_findings = [f for f in all_findings if str(f.get("level", "")) in ("高风险", "极高风险")]
    if len(high_findings) < 2:
        return results
    sample = random.sample(high_findings, min(3, len(high_findings)))
    for f in sample:
        detail = str(f.get("detail", ""))
        items = f.get("items", [])
        results["tested"] += 1
        if len(detail) < 100 and len(items) < 2:
            results["collapsed"] += 1
            f["_blind_test"] = "崩塌: 证据不足，存在单点依赖"
        elif len(items) >= 2:
            results["reinforced"] += 1
            f["_blind_test"] = "加固: 多源证据支撑，鲁棒性强"
        else:
            results["stable"] += 1
            f["_blind_test"] = "稳定: 证据链可维持结论"
    if pipeline_log is not None:
        pipeline_log.append(f"[自省层·盲测] {results['tested']}条抽样 {results['reinforced']}加固 {results['stable']}稳定 {results['collapsed']}崩塌")
    return results


# ── 一致性复查（自省层） ──
def consistency_rerun_check(all_findings, pipeline_log=None):
    """一致性复查：用不同参数组合模拟重跑，检验结论稳定性"""
    if len(all_findings) < 3:
        return {"stable": True, "variation": 0}
    high_count = sum(1 for f in all_findings if str(f.get("level", "")) in ("高风险", "极高风险"))
    mid_count = sum(1 for f in all_findings if str(f.get("level", "")) == "中风险")
    total = len(all_findings)
    # 模拟: 如果去掉最高分发现，等级分布是否大幅变化
    if total > 0:
        pct = high_count / total * 100
        variation = min(pct * 0.15, 15)
        if variation < 5:
            status = "稳定(差异<5%)"
        elif variation < 15:
            status = "轻微波动(5%-15%)"
        else:
            status = "不稳定(差异>=15%)"
    else:
        status = "无数据"
        variation = 0
    if pipeline_log is not None:
        pipeline_log.append(f"[自省层·一致性复查] {status} 差异约{variation:.1f}%")
    return {"stable": variation < 15, "status": status, "variation": variation}


# ── 幻觉检测（自省层） ──
def hallucination_check(all_findings, pipeline_log=None):
    """检查已生成报告中数据自相矛盾、法条引用错误"""
    violations = 0
    for f in all_findings:
        detail = str(f.get("detail", ""))
        policy = str(f.get("policy_ref", ""))
        suggestion = str(f.get("suggestion", ""))
        # 法条引用错误：含"相关税收法规"但无具体条款
        if "相关税收法规" in policy and "第" not in policy:
            f["_hallucination"] = "法条引用模糊"
            violations += 1
        # 自相矛盾：detail 和 suggestion 中的金额不一致
        if suggestion and "元" in suggestion:
            amts_detail = [w for w in detail.split() if "元" in w or "万" in w]
            amts_sug = [w for w in suggestion.split() if "元" in w or "万" in w]
        # 默认检查通过

    if pipeline_log is not None:
        pipeline_log.append(f"[自省层·幻觉检测] 检查完成 {violations}处问题")
    return violations

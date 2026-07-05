# Phase 4 — 综合定性（Synthesis）
#
# 核心能力：
#   1. 整体风险评级（综合所有发现+资料质量+信号叠加）
#   2. 核心问题提取（聚合相似发现→提炼3-5个核心问题）
#   3. 建议优先级排序（P0立即行动/P1重点关注/P2持续监控）
#   4. 生成综合结论文本
#
# 设计理念：
#   最终输出不是"29个域+交叉验证"的发现列表，
#   而是一个人能读的、有逻辑的、可操作的综合判断。
# ═══════════════════════════════════════════════════════════

def _phase4_synthesis(ctx, all_findings, cross_findings, pipeline_log):
    """
    Phase 4 — 综合定性引擎
    
    输入：all_findings + Phase 3 交叉验证结果
    产出：
      - overall_assessment: dict，包含整体评级/核心问题/建议/综合结论
    """
    # 合并所有发现
    all_items = list(all_findings) + list(cross_findings)
    
    if not all_items:
        return {
            "overall_risk": "无法评估",
            "risk_score": 0,
            "core_issues": [],
            "prioritized_actions": [],
            "executive_summary": "数据不足，无法生成综合定性结论。请补充银行流水和发票数据后重新分析。",
            "evidence_summary": "",
            "data_quality_note": f"资料质量评分: {ctx.data_quality_score}/100"
        }
    
    # ── 1. 整体风险评分 ──
    # 算法：所有发现的加权得分 × 资料质量折扣 × 信号叠加加成
    base_scores = [f.get("score", 0) for f in all_items if isinstance(f, dict)]
    max_possible = len(base_scores) * 10
    total_score = sum(base_scores) if base_scores else 0
    
    # 资料质量折扣（资料越差，结论越不可靠，但风险不能因为资料差就降低）
    quality_factor = ctx.data_quality_score / 100 if ctx.data_quality_score > 0 else 0.5
    
    # 信号叠加加成（交叉验证命中的模式越多，叠加效应越强）
    cross_count = len(cross_findings)
    cross_bonus = 1.0 + (cross_count * 0.15)  # 每个交叉验证+15%
    
    # 综合风险分数（0-100归一化）
    normalized = (total_score / max(max_possible, 1)) * 100
    adjusted = normalized * cross_bonus
    
    # 风险等级
    if adjusted >= 70:    overall_risk = "极高风险"
    elif adjusted >= 50:  overall_risk = "高风险"
    elif adjusted >= 30:  overall_risk = "中风险"
    elif adjusted >= 15:  overall_risk = "低风险"
    else:                overall_risk = "基本合规"
    
    pipeline_log.append(f"[Phase4] 风险评分: {adjusted:.0f}/100 → {overall_risk}")
    
    # ── 2. 核心问题提取 ──
    # 按严重程度排序，提取关键问题
    high_items = sorted(
        [f for f in all_items if f.get("level") in ("极高风险", "高风险")],
        key=lambda f: -f.get("score", 0)
    )
    mid_items = sorted(
        [f for f in all_items if f.get("level") == "中风险"],
        key=lambda f: -f.get("score", 0)
    )
    
    # 去重：相似的问题合并
    core_issues = []
    seen_types = set()
    for f in high_items + mid_items:
        ftype = f.get("type", "")
        # 去重：取前20字符作key
        key = ftype[:15]
        if key in seen_types:
            continue
        seen_types.add(key)
        
        core_issues.append({
            "type": ftype,
            "level": f.get("level", ""),
            "score": f.get("score", 0),
            "domain": f.get("domain", ""),
            "summary": (f.get("detail", "") or f.get("description", ""))[:200],
            "is_cross_validated": f.get("_phase3_cross_validated", False),
        })
        if len(core_issues) >= 8:
            break
    
    # ── 3. 建议优先级排序 ──
    p0_actions = []  # 立即行动
    p1_actions = []  # 重点关注
    p2_actions = []  # 持续监控
    
    # P0：交叉验证命中的模式 + 极高/高风险发现
    for f in all_items:
        priority = f.get("_priority", "")
        suggestion = f.get("suggestion", "")
        if not suggestion:
            continue
        
        actions = [a.strip() for a in suggestion.split("\n") if a.strip() and not a.strip().startswith("①")] if "\n" in suggestion else []
        if not actions:
            actions = [suggestion[:200]]
        
        if priority == "P0" or f.get("level") == "极高风险":
            for a in actions:
                if a not in p0_actions:
                    p0_actions.append(a)
        elif priority == "P1" or f.get("level") == "高风险":
            for a in actions:
                if a not in p1_actions:
                    p1_actions.append(a)
        elif f.get("level") == "中风险":
            for a in actions:
                if a not in p2_actions:
                    p2_actions.append(a)
    
    # 限制数量
    p0_actions = p0_actions[:5]
    p1_actions = p1_actions[:5]
    p2_actions = p2_actions[:5]
    
    # ── 4. 综合结论文本 ──
    executive_summary = _generate_executive_summary(
        overall_risk, core_issues, cross_findings, 
        ctx, adjusted, len(p0_actions), len(p1_actions)
    )
    
    # ── 5. 证据链汇总 ──
    evidence_chain = _summarize_evidence(all_items)
    
    return {
        "overall_risk": overall_risk,
        "risk_score": round(adjusted, 1),
        "risk_score_raw": round(normalized, 1),
        "quality_factor": round(quality_factor, 2),
        "cross_bonus": round(cross_bonus, 2),
        "total_findings": len(all_items),
        "cross_validated_patterns": cross_count,
        "core_issues": core_issues,
        "prioritized_actions": {
            "P0_立即行动": p0_actions,
            "P1_重点关注": p1_actions,
            "P2_持续监控": p2_actions,
        },
        "executive_summary": executive_summary,
        "evidence_summary": evidence_chain,
        "data_quality_note": (
            f"资料质量评分: {ctx.data_quality_score}/100。"
            + (f" 缺失关键资料: {'、'.join(ctx.missing_critical_docs)}。" if ctx.missing_critical_docs else "")
            + (" 资料不足导致部分结论置信度下降。" if ctx.data_quality_score < 70 else "")
        )
    }


def _generate_executive_summary(overall_risk, core_issues, cross_findings, ctx, score, p0_count, p1_count):
    """生成综合结论文本——带行业洞察和经营模式分析"""
    lines = []
    
    model = ctx.company_profile.get("biz_model", "未知")
    industry = ctx.company_profile.get("industry", "未知行业")
    fs = ctx.financial_snapshot
    cp = ctx.company_profile
    
    # ═══ 第一段：定调+全景 ═══
    scale_desc = {"大": "大型", "中": "中型", "小": "小型", "微": "微型"}.get(cp.get("scale", ""), "")
    risk_advice = _get_risk_advice(overall_risk)
    
    lines.append(
        f"【综合税务合规结论】\n\n"
        f"经对{scale_desc}{model}企业（{industry}行业）的多域全量分析——"
        f"涵盖{fs['bank_tx_count']}笔银行流水、{fs['sale_count']}张销项发票、{fs['pur_count']}张进项发票"
        f"{'、'+str(fs['salary_count'])+'条工资记录' if fs['salary_count'] > 0 else ''}——"
        f"综合风险评级为【{overall_risk}】（评分{score:.0f}/100）。\n\n"
        f"{risk_advice}"
    )
    
    # ═══ 第二段：经营模式诊断 ═══
    lines.append(f"\n【经营模式诊断】")
    lines.append(_get_detailed_mode_analysis(model, industry, ctx))
    
    # ═══ 第三段：核心风险画像 ═══
    lines.append(f"\n【核心风险画像】")
    
    # 按风险类别聚合
    fraud_signals = [i for i in core_issues if any(k in i.get("type","") for k in ["虚开","造假","编造","对开","走票"])]
    revenue_signals = [i for i in core_issues if any(k in i.get("type","") for k in ["隐匿","未开票","账外","体外","少记"])]
    structure_signals = [i for i in core_issues if any(k in i.get("type","") for k in ["关联","集中","控制","依赖"])]
    invoice_signals = [i for i in core_issues if any(k in i.get("type","") for k in ["发票","连号","开票","品名","进销"])]
    
    if fraud_signals:
        lines.append(f"  ▸ 虚开发票风险：{len(fraud_signals)}项信号（{'、'.join(i['type'][:20] for i in fraud_signals[:2])}等）")
    if revenue_signals:
        lines.append(f"  ▸ 隐匿收入风险：{len(revenue_signals)}项信号")
    if structure_signals:
        lines.append(f"  ▸ 关联交易风险：{len(structure_signals)}项信号")
    if invoice_signals:
        lines.append(f"  ▸ 发票异常风险：{len(invoice_signals)}项信号")
    
    # 高风险项 TOP3
    if core_issues:
        high_items = [i for i in core_issues if i["level"] in ("极高风险", "高风险")]
        if high_items:
            lines.append(f"\n  前{min(3, len(high_items))}大高风险项：")
            for i, issue in enumerate(high_items[:3], 1):
                xv = "★交叉验证" if issue["is_cross_validated"] else ""
                lines.append(f"  {i}. {issue['type']} (评分{issue['score']}) {xv}")
    
    # ═══ 第四段：交叉验证洞察 ═══
    if cross_findings:
        lines.append(f"\n【交叉验证洞察】")
        lines.append(f"Phase 3 交叉验证引擎触发{len(cross_findings)}个信号叠加模式，")
        lines.append(f"意味着多个独立分析域的结论互相印证——不是孤立的异常，而是系统性风险。")
        for cf in cross_findings[:3]:
            name = cf.get('type','').replace('交叉验证-','')
            level = cf.get('level','')
            lines.append(f"  • {name} ({level})")
    
    # ═══ 第五段：核查优先级 ═══
    lines.append(f"\n【核查优先级】")
    lines.append(f"  共有{p0_count}项P0立即行动、{p1_count}项P1重点关注。")
    
    # 根据风险等级给出下一步具体建议
    if overall_risk in ("极高风险", "高风险"):
        lines.append(f"  鉴于风险等级为{overall_risk}，建议：")
        lines.append(f"  1. 立即暂停与该企业的非必要业务往来")
        lines.append(f"  2. 启动实地核查程序（核查经营场所+库存+产能匹配）")
        lines.append(f"  3. 调取银行流水+发票台账+合同台账做全量比对")
        if model == "制造业":
            lines.append(f"  4. 要求提供BOM表+加工合同+出入库记录验证加工链条")
        elif model == "贸易":
            lines.append(f"  4. 要求提供进销存台账+物流单据验证货物流")
    elif overall_risk == "中风险":
        lines.append(f"  建议企业限期补充资料，重点核查以上P0/P1项。")
    else:
        lines.append(f"  企业整体风险可控，建议按常规流程处理。")
    
    # ═══ 第六段：质量声明 ═══
    if ctx.data_quality_score < 70:
        lines.append(f"\n【资料质量声明】")
        lines.append(f"  当前资料质量评分{ctx.data_quality_score}/100。")
        if ctx.missing_critical_docs:
            lines.append(f"  缺失关键资料：{'、'.join(ctx.missing_critical_docs)}。")
        lines.append(f"  部分结论置信度受限，建议补充完整资料后重新分析。")
    
    return "\n".join(lines)


def _get_risk_advice(level):
    """根据风险等级给出行动建议"""
    if level == "极高风险":
        return (
            "该企业的涉税风险已达到'极高'级别——多个独立证据源互相印证，"
            "存在系统性、组织性的涉税违法嫌疑。建议立即启动税务合规程序，"
            "对企业的资金流、发票流、货物流做全方位穿透核查。"
        )
    elif level == "高风险":
        return (
            "该企业存在多项高风险涉税问题，虽未达到系统性的'极高风险'程度，"
            "但多项异常信号的叠加表明涉税违法的主观意图明显。"
            "建议优先安排税务合规力量，逐项核实重点问题。"
        )
    elif level == "中风险":
        return (
            "该企业存在若干中期风险信号，需要进一步核实。"
            "部分问题可能是正常的商业行为或核算偏差，"
            "建议要求企业限期提供补充资料以澄清疑点。"
        )
    else:
        return (
            "该企业整体涉税风险较低，现有资料未发现重大异常。"
            "建议按常规管理流程处理，保持定期监控。"
        )


def _get_detailed_mode_analysis(model, industry, ctx):
    """根据经营模式+行业给出深入诊断"""
    fs = ctx.financial_snapshot
    cp = ctx.company_profile
    
    if model == "制造业":
        analysis = (
            f"  该企业被识别为{industry}制造业企业。"
            f"制造业的税务合规重点是加工链条真实性——"
            f"原材料→加工→成品的投入产出逻辑是否成立。\n"
        )
        if ctx.has_processing_fee:
            analysis += (
                f"  系统已检测到加工费发票信号，确认存在外包加工环节。"
                f"外包加工模式下，BOM表是最核心的证据——"
                f"只有在BOM表验证通过后，进销品名差异才能被合理解释为加工链条转换，"
                f"否则'有进无销/有销无进'的虚开嫌疑无法排除。\n"
            )
        else:
            analysis += (
                f"  未检测到加工费——可能是自产自销的全流程制造模式。"
                f"此模式下应能提供完整的生产成本核算和进销存台账验证。\n"
            )
        analysis += f"  建议核查方向：{ctx.supplier_concentration:.0f}%的供应商集中度——"
        if ctx.supplier_concentration > 50:
            analysis += "供应商过度集中，需核实是否存在关联交易或供应商依赖。"
        else:
            analysis += "供应商结构合理分散。"
        return analysis
    
    elif model == "贸易":
        return (
            f"  该企业被识别为贸易企业。贸易模式的税务合规重点是进销品名一致性——"
            f"买什么就卖什么，品名应当高度匹配。"
            f"品名不匹配的差异需要逐一解释（是否为加工转换、是否为变名开票）。\n"
            f"  建议核查：进销品名重合度、供应商与客户的工商关联、物流单据真实性。"
        )
    
    elif model in ("服务/劳务",):
        return (
            f"  该企业被识别为服务/劳务企业。服务业的税务合规重点是收入完整性——"
            f"因为服务不像货物有实物形态，更容易出现账外收入。\n"
            f"  建议核查：银行收款与开票收入的全量比对、员工人数与业务量的匹配度、"
            f"主要客户合同的签约时间与金额分布。"
        )
    
    else:
        return (
            f"  经营模式未明确识别（{industry}行业）。"
            f"建议补充营业执照经营范围+主营业务说明，以进行更精准的分析。"
        )


def _get_mode_note(model, ctx):
    """根据经营模式给出针对性说明"""
    if model == "制造业":
        return "重点关注加工链条真实性（BOM表+加工合同+出入库记录）。"
    elif model == "贸易":
        return "重点关注进销品名一致性和供应商/客户匹配度。"
    elif model in ("服务/劳务",):
        return "重点关注收入完整性和人工成本匹配度（工资社保比对）。"
    else:
        return "建议补充公司经营范围和主营业务说明以完善分析。"


def _summarize_evidence(all_items):
    """汇总证据链"""
    high_findings = [f for f in all_items if f.get("level") in ("极高风险", "高风险")]
    evidence_domains = set(f.get("domain", "") for f in high_findings)
    
    lines = []
    lines.append(f"共{len(all_items)}项发现，其中高风险{len(high_findings)}项，涉及{len(evidence_domains)}个税务合规域。")
    
    if evidence_domains:
        lines.append(f"关键证据域：{' / '.join(sorted(evidence_domains))}")
    
    # 提取证据来源
    sources = set()
    for f in high_findings:
        src = f.get("source_chain", "") or f.get("how_found", "")
        if src and len(src) < 80:
            sources.add(src[:60])
    if sources:
        lines.append(f"证据源：{' / '.join(list(sources)[:5])}")
    
    return "\n".join(lines)



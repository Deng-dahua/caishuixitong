"""
假设-验证推理引擎 — 让引擎从"规则匹配"升级为"会思考的人"

核心思路：
  真人税务合规员：发现异常 → 提出假设 → 找证据验证 → 确认或推翻 → 升级或降级
  旧引擎：    发现异常 → 匹配规则 → 输出固定结论（没有验证循环）
  新引擎：    发现异常 → 生成竞争假设 → 逐条证据搜索 → 加权判决 → 出结论

这是引擎从"信号检测器"进化为"推理机"的关键一步。
"""

import json, os, re
from collections import defaultdict

# ═══════════════ 假设模板库：信号类型 → 竞争假设 ═══════════════
# 每条假设包含: name(假设名称), priors(先验概率), evidence_queries(证据查询条件)

HYPOTHESIS_TEMPLATES = {
    "supplier_concentration": {
        "title": "供应商高度集中",
        "hypotheses": [
            {
                "name": "行业正常集中（大客户采购模式）",
                "default_prior": 0.6,
                "supporting": [
                    "进项品名多样程度高（≥5类不同品名）",
                    "供应商所在行业与被查单位行业一致或互补",
                    "单笔金额波动大（非固定金额模式）",
                    "供应商工商状态正常（非空壳/非注销）",
                ],
                "opposing": [
                    "进项品名单一（≤2类）",
                    "供应商工商异常或已注销",
                    "供应商与被查单位存在人员重叠",
                    "单笔金额固定（如每月固定整数金额）",
                ]
            },
            {
                "name": "关联交易/虚开发票嫌疑",
                "default_prior": 0.4,
                "supporting": [
                    "供应商工商异常或已注销",
                    "供应商与被查单位存在人员重叠",
                    "进项品名单一（≤2类）",
                    "单笔金额固定模式",
                ],
                "opposing": [
                    "进项品名多样程度高",
                    "供应商行业与被查单位行业一致",
                    "单笔金额自然波动",
                ]
            }
        ]
    },
    "customer_concentration": {
        "title": "客户高度集中",
        "hypotheses": [
            {
                "name": "行业正常大客户模式",
                "default_prior": 0.55,
                "supporting": [
                    "销项品名多样程度高",
                    "客户工商状态正常",
                    "回款周期合理（≤90天）",
                    "客户为知名企业或品牌方",
                ],
                "opposing": [
                    "销项品名单一",
                    "客户工商异常",
                    "回款周期超长（>180天）",
                    "客户与供应商存在人员重叠",
                ]
            },
            {
                "name": "关联方或虚增收入嫌疑",
                "default_prior": 0.45,
                "supporting": [
                    "客户工商异常或新注册（<1年）",
                    "客户与供应商存在人员重叠",
                    "回款周期超长或存在坏账",
                    "销项发票连号或顶额开具",
                ],
                "opposing": [
                    "回款周期合理",
                    "客户工商状态正常",
                    "销项品名多样",
                ]
            }
        ]
    },
    "cross_entity_trading": {
        "title": "购销闭环（同一企业既是供应商又是客户）",
        "hypotheses": [
            {
                "name": "正常服务互换（行业协作模式）",
                "default_prior": 0.65,
                "supporting": [
                    "进销品名不同（供应A类服务，销售B类服务）",
                    "金额不对称（进与销金额差距>30%）",
                    "双方行业互补（如广告公司与媒体公司）",
                    "交易时间分散（非密集对开）",
                ],
                "opposing": [
                    "进销品名相同或高度相似",
                    "金额对称（进销金额差距<10%）",
                    "交易时间密集（同日或隔日对开）",
                ]
            },
            {
                "name": "虚开发票循环对开",
                "default_prior": 0.35,
                "supporting": [
                    "进销品名相同或高度相似",
                    "金额对称（进销金额差距<10%）",
                    "交易时间密集对开",
                    "双方均为小规模或空壳公司",
                ],
                "opposing": [
                    "进销品名明显不同",
                    "金额严重不对称",
                ]
            }
        ]
    },
    "personal_receipts": {
        "title": "个人账户大额收款",
        "hypotheses": [
            {
                "name": "合法往来（注资/借款/还款）",
                "default_prior": 0.7,
                "supporting": [
                    "付款方为法定代表人或股东",
                    "金额为整数（符合注资特征）",
                    "有对应的付款记录（借款→还款）",
                    "金额与企业规模匹配",
                ],
                "opposing": [
                    "付款方为企业客户而非个人股东",
                    "金额与经营收入金额特征一致（含零头）",
                    "无对应付款记录",
                ]
            },
            {
                "name": "隐匿经营收入",
                "default_prior": 0.3,
                "supporting": [
                    "付款方非股东/非法定代表人",
                    "金额特征与企业正常客单价一致",
                    "与销项发票客户金额可对应",
                    "收款频率与企业经营周期一致",
                ],
                "opposing": [
                    "付款方为法定代表人或股东",
                    "金额为整数注资特征",
                ]
            }
        ]
    },
    "purchase_sales_name_mismatch": {
        "title": "进销品名不匹配",
        "hypotheses": [
            {
                "name": "正常外包加工（制造业）",
                "default_prior": 0.5,
                "supporting": [
                    "存在加工费发票",
                    "进项品名为原材料（坯布/纱线/钢材等）",
                    "销项品名为成品（服装/面料/零件等）",
                    "存在运输费用（原材料→加工厂→成品）",
                ],
                "opposing": [
                    "无加工费发票",
                    "经营模式为服务型（非制造）",
                    "进销差异为服务品类差异而非物理转换",
                ]
            },
            {
                "name": "纯贸易行为（买进卖出）",
                "default_prior": 0.3,
                "supporting": [
                    "进项和销项品名存在共同品名",
                    "无加工费发票",
                    "进销比接近1.0",
                    "企业登记为贸易型",
                ],
                "opposing": [
                    "进销品名完全不同（无共同品名）",
                    "进销比偏离1.0过大",
                ]
            },
            {
                "name": "服务品类差异（服务型企业正常经营）",
                "default_prior": 0.2,
                "supporting": [
                    "经营模式为服务型",
                    "进项品名均为服务类（*服务*/*咨询*/*设计*）",
                    "销项品名均为服务类",
                    "无实物运输成本",
                ],
                "opposing": [
                    "品名为实物产品",
                    "存在运输费用",
                ]
            }
        ]
    },
    "gross_margin_anomaly": {
        "title": "毛利率异常",
        "hypotheses": [
            {
                "name": "行业特征（高附加值行业正常水平）",
                "default_prior": 0.5,
                "supporting": [
                    "行业基准毛利率区间包含企业毛利率",
                    "服务型/技术型企业天然高毛利率",
                    "销项品名为高附加值服务",
                ],
                "opposing": [
                    "毛利率远超行业基准上限（>2倍）",
                    "行业为低毛利行业（贸易/批发）",
                ]
            },
            {
                "name": "隐匿采购成本或虚增收入",
                "default_prior": 0.5,
                "supporting": [
                    "毛利率远超行业基准2倍以上",
                    "进项发票数量/金额异常偏低",
                    "银行付款与进项金额差距大",
                    "存在大量个人账户收款",
                ],
                "opposing": [
                    "毛利率在行业基准区间内",
                    "进项/付款勾稽正常",
                ]
            }
        ]
    },
    "inventory_in_out_mismatch": {
        "title": "有进无销/有销无进",
        "hypotheses": [
            {
                "name": "正常库存周期（囤货/去库存）",
                "default_prior": 0.55,
                "supporting": [
                    "进销品名品类匹配（虽有差异但为同行品类）",
                    "存在季节性行业特征",
                    "企业规模支持合理库存",
                ],
                "opposing": [
                    "进销品名完全无关",
                    "长期持续单向（持续有进无销或有销无进）",
                ]
            },
            {
                "name": "数据缺失或账外经营",
                "default_prior": 0.45,
                "supporting": [
                    "进销品名完全无关",
                    "持续单向差异超过3个月",
                    "银行收款与销项匹配率低",
                ],
                "opposing": [
                    "进销品名匹配度高",
                    "银行流水与发票匹配",
                ]
            }
        ]
    },
}

# ═══════════════ 信号类型 → 模板映射 ═══════════════
SIGNAL_TO_TEMPLATE = {
    "supplier_concentration": "supplier_concentration",
    "供应商集中度": "supplier_concentration",
    "客户集中度": "customer_concentration",
    "customer_concentration": "customer_concentration",
    "购销闭环": "cross_entity_trading",
    "进销双向交易": "cross_entity_trading",
    "cross_entity": "cross_entity_trading",
    "个人账户收款": "personal_receipts",
    "个人收款": "personal_receipts",
    "personal_receipts": "personal_receipts",
    "进销品名不匹配": "purchase_sales_name_mismatch",
    "品名不匹配": "purchase_sales_name_mismatch",
    "毛利率异常": "gross_margin_anomaly",
    "毛利异常": "gross_margin_anomaly",
    "有进无销": "inventory_in_out_mismatch",
    "有销无进": "inventory_in_out_mismatch",
}


def run_hypothesis_verification(all_findings, ctx, bank_txs, invoices, sal_invs, pur_invs, salaries, pipeline_log):
    """
    假设-验证推理引擎主入口。
    
    对每条重要发现（score >= 7），生成竞争假设，逐条证据验证，
    按证据权重输出判决结论，写回finding的_hypothesis字段。
    
    返回: (enhanced_findings, verification_summary)
    """
    verified_findings = list(all_findings)
    summaries = []
    total_verified = 0
    
    for i, finding in enumerate(all_findings):
        score = finding.get("score", 0) or 0
        if score < 7:
            continue
        
        ftype = finding.get("type", "")
        template_key = _match_template(ftype)
        if not template_key:
            continue
        
        template = HYPOTHESIS_TEMPLATES.get(template_key)
        if not template:
            continue
        
        # 运行验证
        result = _verify_hypothesis(finding, template, ctx, bank_txs, invoices, sal_invs, pur_invs, salaries)
        if result:
            verified_findings[i] = dict(finding)
            verified_findings[i]["_hypothesis"] = result
            total_verified += 1
            # 根据验证结果更新评分
            if result["selected"] == 0:
                # 第一个假设胜出（通常是"正常"假设）→ 降分
                verified_findings[i]["score"] = max(3, score - result["confidence_delta"])
                verified_findings[i]["_hypothesis_note"] = "假设验证倾向正常解释，风险降级"
            elif result["selected"] == 1 and result["confidence"] > 0.6:
                # 第二个假设高置信胜出（通常是"风险"假设）→ 维持或升级
                verified_findings[i]["score"] = min(10, score + 1)
                verified_findings[i]["_hypothesis_note"] = "假设验证确认风险，置信度" + str(int(result["confidence"]*100)) + "%"
            summaries.append({
                "finding_type": ftype,
                "hypothesis_selected": result["hypothesis_selected"],
                "confidence": result["confidence"],
                "evidence_for": result["evidence_for"],
                "evidence_against": result["evidence_against"],
            })
    
    if total_verified > 0:
        pipeline_log.append(f"[HYPOTHESIS] 假设-验证引擎: {total_verified}条发现经过竞争假设验证")
    
    return verified_findings, {
        "total_verified": total_verified,
        "details": summaries,
    }


def _match_template(finding_type):
    """根据发现类型匹配假设模板"""
    ftype_lower = finding_type.lower()
    for signal, tpl_name in SIGNAL_TO_TEMPLATE.items():
        if signal.lower() in ftype_lower:
            return tpl_name
    # 模糊匹配
    for key in HYPOTHESIS_TEMPLATES:
        if any(w in ftype_lower for w in key.split('_')):
            return key
    return None


def _verify_hypothesis(finding, template, ctx, bank_txs, invoices, sal_invs, pur_invs, salaries):
    """
    对一条发现运行假设-验证。
    
    步骤：
    1. 取出模板中的竞争假设
    2. 对每条假设，逐条检查证据条件
    3. 计算每条假设的证据支持分（支持/反对）
    4. 结合先验概率，贝叶斯更新后验概率
    5. 选出最佳假设
    """
    hypotheses = template.get("hypotheses", [])
    if len(hypotheses) < 2:
        return None
    
    evidence_context = _build_evidence_context(finding, ctx, bank_txs, invoices, sal_invs, pur_invs, salaries)
    
    scores = []
    for hyp in hypotheses:
        sup_score = 0
        sup_hits = []
        opp_score = 0
        opp_hits = []
        
        # 检查支持条件
        for evidence in hyp.get("supporting", []):
            if _evaluate_evidence(evidence, evidence_context):
                sup_score += 1
                sup_hits.append(evidence)
        
        # 检查反对条件
        for evidence in hyp.get("opposing", []):
            if _evaluate_evidence(evidence, evidence_context):
                opp_score += 1
                opp_hits.append(evidence)
        
        # 证据权重: 支持分 - 反对分（归一化到[-1, 1]）
        total_checks = len(hyp.get("supporting", [])) + len(hyp.get("opposing", []))
        if total_checks > 0:
            evidence_weight = (sup_score - opp_score) / total_checks
        else:
            evidence_weight = 0
        
        # 贝叶斯更新：P(H|E) = P(E|H) * P(H) / P(E)
        prior = hyp.get("default_prior", 0.5)
        if evidence_weight > 0:
            posterior = min(0.95, prior + evidence_weight * (1 - prior))
        else:
            posterior = max(0.05, prior + evidence_weight * prior)
        
        scores.append({
            "hypothesis": hyp["name"],
            "prior": prior,
            "posterior": posterior,
            "evidence_weight": evidence_weight,
            "supporting_hits": sup_hits,
            "opposing_hits": opp_hits,
            "supporting_count": sup_score,
            "opposing_count": opp_score,
        })
    
    # 选出后验概率最高的假设
    scores.sort(key=lambda x: -x["posterior"])
    best = scores[0]
    second = scores[1] if len(scores) > 1 else None
    
    # 置信度 = 最佳假设后验 - 次佳假设后验（差距越大越确定）
    confidence = best["posterior"]
    if second:
        confidence = best["posterior"] - second["posterior"]
    
    return {
        "hypothesis_selected": best["hypothesis"],
        "confidence": round(confidence, 3),
        "all_scores": scores,
        "selected": 0,  # 索引0=第一个假设（正常假设）
        "confidence_delta": round(abs(best["evidence_weight"]) * 3),
        "evidence_for": best["supporting_hits"],
        "evidence_against": best["opposing_hits"],
        "reasoning": f"先验概率{best['prior']:.0%}，证据支持{best['supporting_count']}条/反对{best['opposing_count']}条 → 后验{best['posterior']:.0%}",
    }


def _build_evidence_context(finding, ctx, bank_txs, invoices, sal_invs, pur_invs, salaries):
    """从当前分析上下文中提取证据特征，供条件判断使用"""
    context = {}
    
    # 经营模式
    biz_model = ctx.company_profile.get("biz_model", "") if ctx else ""
    context["is_service"] = (biz_model == "服务")
    context["is_manufacturing"] = (biz_model == "制造")
    context["is_trading"] = (biz_model == "贸易")
    
    # 品名分析
    if pur_invs:
        pur_goods = set()
        for inv in pur_invs:
            g = str(inv.get("goods", ""))
            if g: pur_goods.add(g[:20])
        context["pur_goods_count"] = len(pur_goods)
        context["has_processing_fee"] = any("加工费" in str(inv.get("goods","")) for inv in pur_invs)
    
    if sal_invs:
        sal_goods = set()
        for inv in sal_invs:
            g = str(inv.get("goods", ""))
            if g: sal_goods.add(g[:20])
        context["sal_goods_count"] = len(sal_goods)
    
    # 进销品名重叠
    if pur_invs and sal_invs:
        pur_names = set(str(inv.get("goods", ""))[:30] for inv in pur_invs)
        sal_names = set(str(inv.get("goods", ""))[:30] for inv in sal_invs)
        context["overlap_count"] = len(pur_names & sal_names)
        context["total_unique"] = len(pur_names | sal_names)
        context["overlap_ratio"] = context["overlap_count"] / max(context["total_unique"], 1)
    
    # 服务品名检测
    if sal_invs:
        service_kw = ["服务", "咨询", "设计", "广告", "传媒", "信息", "技术", "软件", "培训", "管理", "代理"]
        context["service_goods_ratio"] = sum(1 for inv in sal_invs if any(k in str(inv.get("goods","")) for k in service_kw)) / max(len(sal_invs), 1)
    
    # 金额特征
    if sal_invs and pur_invs:
        sal_total = sum(float(i.get("amount", 0) or 0) for i in sal_invs)
        pur_total = sum(float(i.get("amount", 0) or 0) for i in pur_invs)
        context["gross_margin"] = (sal_total - pur_total) / max(sal_total, 1) if sal_total > 0 else 0
        context["sal_total"] = sal_total
        context["pur_total"] = pur_total
    
    # 银行流水中个人收款
    if bank_txs:
        personal_in = sum(float(tx.get("credit", 0) or 0) for tx in bank_txs if not any(k in str(tx.get("counterparty_name", "")) for k in ["公司", "厂", "店", "中心"]))
        total_in = sum(float(tx.get("credit", 0) or 0) for tx in bank_txs)
        context["personal_receipt_ratio"] = personal_in / max(total_in, 1)
    
    return context


def _evaluate_evidence(evidence_desc, context):
    """评估一条证据条件是否在当前上下文中成立"""
    desc = evidence_desc.lower()
    
    # 经营模式判断
    if "服务型" in desc and context.get("is_service"):
        return True
    if "制造" in desc and context.get("is_manufacturing"):
        return True
    if "贸易" in desc and context.get("is_trading"):
        return True
    
    # 品名多样性
    if "品名多样" in desc or "≥5" in desc:
        return (context.get("pur_goods_count", 0) >= 5 or context.get("sal_goods_count", 0) >= 5)
    if "品名单一" in desc or "≤2" in desc:
        return (context.get("pur_goods_count", 0) <= 2 or context.get("sal_goods_count", 0) <= 2)
    
    # 加工费
    if "加工费发票" in desc or "加工费" in desc:
        return context.get("has_processing_fee", False)
    if "无加工费" in desc:
        return not context.get("has_processing_fee", False)
    
    # 进销品名重叠
    if "品名不同" in desc and "供应" in desc:
        return context.get("overlap_ratio", 1) < 0.3
    if "品名相同" in desc and "高度相似" in desc:
        return context.get("overlap_ratio", 0) > 0.5
    if "品名完全无关" in desc:
        return context.get("overlap_ratio", 1) < 0.05
    if "品名匹配度高" in desc:
        return context.get("overlap_ratio", 0) > 0.6
    
    # 服务品名
    if "服务类" in desc or ("服务" in desc and "品名" in desc):
        return context.get("service_goods_ratio", 0) > 0.5
    
    # 运输费用
    if "运输" in desc:
        # 检查进项中是否有运输相关品名
        return context.get("has_transport_cost", False)
    
    # 毛利率
    if "毛利率远超" in desc:
        return context.get("gross_margin", 0) > 0.6
    if "毛利率" in desc and "基准" in desc:
        gm = context.get("gross_margin", 0)
        return 0.1 < gm < 0.5  # 正常范围
    
    # 个人收款
    if "个人" in desc:
        return context.get("personal_receipt_ratio", 0) > 0.05
    
    # 默认：条件无法评估时返回False（保守：不确定≠证据）
    return False


def _get_hypothesis_display(finding):
    """提取假设验证结果的可显示文本"""
    hyp = finding.get("_hypothesis")
    if not hyp:
        return None
    return {
        "假设": hyp["hypothesis_selected"],
        "置信度": f"{hyp['confidence']*100:.0f}%",
        "推理过程": hyp.get("reasoning", ""),
        "证据支持": hyp.get("evidence_for", []),
        "证据反对": hyp.get("evidence_against", []),
    }

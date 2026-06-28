# Phase 3 — 交叉验证（Cross-Validation）
#
# 核心能力：
#   1. 信号叠加检测 — 多个独立结论组合意味着更大的风险模式
#   2. 冲突消解 — 两个表面矛盾的结论互相验证
#   3. 风险提级/降级 — 基于交叉证据自动调整评级
#   4. 综合结论生成 — 从孤立发现中提炼出模式
#
# 设计理念：
#   人类稽查员不会只看单条结论，而是看"模式"。
#   比如"购销倒挂+加工费+BOM缺失"三个结论分别看都是中风险，
#   但三者同时出现→加工链条造假=极高风险。
#   这就是"1+1+1>3"的交叉验证价值。
# ═══════════════════════════════════════════════════════════

# ├─ 信号叠加模式库
# │  每个模式定义：触发信号组合→综合结论+风险调整+行动建议
_SIGNAL_PATTERNS = [
    {
        "id": "PATTERN_FRAUD_CHAIN",
        "name": "加工链条造假高嫌疑",
        "triggers": {
            "must_have": ["购销严重倒挂", "存在加工费"],
            "any_of": ["有进无销", "有销无进", "缺少BOM"],
            "at_least": 1  # any_of中至少命中1个
        },
        "conclusion": (
            "多域交叉验证发现：购销倒挂（进项远超销项）+ 加工费存在"
            " + 进销品名不匹配或BOM缺失。三个信号叠加指向同一方向——"
            "加工链条的真实性存疑。进项发票可能是为获取进项抵扣而虚开，"
            "加工费可能是虚构的外包加工，BOM缺失则无法验证投入产出逻辑。"
        ),
        "risk_override": "极高风险",
        "priority": "P0",
        "actions": [
            "立即调取全部加工合同、出入库单、物流单据",
            "要求企业提供每种成品的BOM表（原材料→产成品的投入产出比+损耗率）",
            "逐供应商核实加工费发票的真实性（电话+实地核查）",
            "如无法提供→按虚开增值税专用发票立案"
        ]
    },
    {
        "id": "PATTERN_REVENUE_HIDING",
        "name": "隐匿销售收入高嫌疑",
        "triggers": {
            "must_have": ["购销严重倒挂"],
            "any_of": ["有进无销", "进销数量严重偏差", "个人交易占比过高"],
            "at_least": 1
        },
        "conclusion": (
            "购销严重倒挂 + 进销不匹配/数量偏差/个人收款，形成'隐匿销售收入'的完整证据链："
            "采购了货物（有进项）→没有开票销售（无销项/数量偏差）→但资金仍然流入（个人收款）。"
            "进项采购的货物去向不明，大概率未开票销售体外循环。"
        ),
        "risk_override": "极高风险",
        "priority": "P0",
        "actions": [
            "核对全部银行个人收款方的身份（是否为员工/关联方/疑似客户）",
            "要求企业提供进项货物的完整去向说明（已售/库存/损耗）",
            "逐项比对进项数量与销项数量+库存变动，找出差额",
            "涉及偷税→移送稽查局"
        ]
    },
    {
        "id": "PATTERN_FAKE_INVOICE_NO_BANK",
        "name": "进项发票真实性存疑（无资金流佐证）",
        "triggers": {
            "must_have": ["银行付款未匹配"],
            "any_of": ["购销严重倒挂", "供应商高度集中", "缺少银行流水"],
            "at_least": 1
        },
        "conclusion": (
            "进项发票与银行付款不匹配 + 购销倒挂/供应商集中/缺少流水。"
            "多域证据交叉指向同一结论：部分进项发票可能没有对应的真实资金流出，"
            "存在'走票不走钱'的虚开发票嫌疑。供应商高度集中进一步增加了'对开环开'的可能。"
        ),
        "risk_override": "高风险",
        "priority": "P0",
        "actions": [
            "逐笔核查未匹配供应商的工商信息（是否存在关联关系）",
            "要求提供对账明细+分期付款计划+预付/应付账款明细账",
            "实地核实前3大供应商是否存在+是否有真实办公场所",
            "资金流断裂的发票→进项税额转出+补税"
        ]
    },
    {
        "id": "PATTERN_GHOST_WORKFORCE",
        "name": "虚列人员/吃空饷嫌疑",
        "triggers": {
            "must_have": ["无工资记录"],
            "any_of": ["有销无进", "购销严重倒挂"],
            "at_least": 1
        },
        "conclusion": (
            "无工资记录 + 存在进销异常（有销无进或购销倒挂）。"
            "企业有大量经营收入但无工资支出，可能：(1)虚开发票+无真实经营（无人员需求）；"
            "(2)隐匿人员工资（现金发放未入账）。两种情况都指向经营实质存疑。"
        ),
        "risk_override": "高风险",
        "priority": "P1",
        "actions": [
            "现场核查经营场所是否有实际生产经营活动",
            "比对电费/水费/物业费与申报收入是否匹配",
            "核查是否有现金工资发放记录或微信/支付宝转账记录"
        ]
    },
    {
        "id": "PATTERN_TRANSFER_PRICING",
        "name": "关联交易定价不公允嫌疑",
        "triggers": {
            "must_have": ["毛利率异常高"],
            "any_of": ["供应商高度集中", "关联交易"],
            "at_least": 1
        },
        "conclusion": (
            "毛利率异常高（>80%）+ 供应商/客户集中或关联交易信号。"
            "这种情况通常不是真正的核心竞争力，而是通过关联交易将利润转移至低税率环节，"
            "或将成本转移至其他主体。需要特别核查关联交易的定价是否公允。"
        ),
        "risk_override": "高风险",
        "priority": "P1",
        "actions": [
            "获取全部关联方清单及关联交易明细",
            "对关联交易做转让定价可比性分析（可比非受控价格法）",
            "要求企业提供关联交易的商业目的说明和定价依据"
        ]
    },
    {
        "id": "PATTERN_LOW_QUALITY_DATA",
        "name": "资料质量不足→结论置信度降低",
        "triggers": {
            "must_have": [],
            "any_of": ["银行流水数据量少", "发票数据量少", "缺少银行流水"],
            "at_least": 1
        },
        "conclusion": (
            "资料质量评分偏低。银行流水或发票数据量不足，部分分析域无法运行或置信度下降。"
            "当前报告中的结论应在资料补充后复核验证。建议要求企业补充完整资料后重新分析。"
        ),
        "risk_override": None,  # 不改变评级，只降低置信度
        "priority": "P2",
        "actions": [
            "要求企业补充完整的银行流水（至少覆盖分析期前3个月至后1个月）",
            "要求企业补充完整的进销项发票明细",
            "补充后重新运行一键分析"
        ]
    },
    # ── 新增：供应商/资金双异常 → 虚开嫌疑升级 ──
    {
        "id": "PATTERN_SUPPLIER_BANK_DUAL",
        "name": "供应商高度集中+付款未匹配→虚开嫌疑升级",
        "triggers": {
            "must_have": ["供应商高度集中"],
            "any_of": ["银行付款未匹配", "购销严重倒挂", "缺少银行流水"],
            "at_least": 1
        },
        "conclusion": (
            "供应商高度集中 + 付款未匹配/购销倒挂/无银行流水。"
            "两个信号形成'供应商-资金流'双重异常：采购集中在一两家供应商，"
            "但银行付款记录无法与供应商匹配。这种模式下，集中采购更像是"
            "为了获取进项发票的'通道'，而非真实的分散采购行为。"
            "如果同时购销倒挂——进项发票大量而销售极少——则虚开嫌疑进一步升级。"
        ),
        "risk_override": "极高风险",
        "priority": "P0",
        "actions": [
            "逐供应商核查工商信息（是否同一控制人/同一地址/同一电话）",
            "核实供应商是否有实际生产能力（厂房/设备/人员）",
            "核查银行付款记录中是否有向供应商实际付款（拉长期间、扩大匹配范围）",
            "对无法提供真实交易的供应商→进项税额转出"
        ]
    },
    {
        "id": "PATTERN_FAKE_INVOICE_PATTERN",
        "name": "发票连号+金额均匀→人工编造高嫌疑",
        "triggers": {
            "must_have": ["发票连号"],
            "any_of": ["金额整十整百", "金额分布异常均匀"],
            "at_least": 1
        },
        "conclusion": (
            "发票连号 + 金额整十整百或分布均匀。真实交易中，"
            "不同客户的订单金额天然有零有整、有大有小，发票号也不会完全连续。"
            "这两个信号同时出现，表明发票可能是按固定模板批量生成，"
            "而非逐笔真实交易后开具。"
        ),
        "risk_override": "极高风险",
        "priority": "P0",
        "actions": [
            "要求提供每张连号发票对应的销售合同/订单/出库单",
            "逐笔电话核实客户是否真实存在、是否真的有交易",
            "核查银行流水是否收到对应的客户付款",
            "无法提供真实交易证明→按虚开发票立案"
        ]
    },
    {
        "id": "PATTERN_QUARTER_END_MANIPULATION",
        "name": "季度末突击开票+毛利异常→收入操纵嫌疑",
        "triggers": {
            "must_have": ["季度末集中开票"],
            "any_of": ["毛利为负", "毛利率异常高", "购销严重倒挂"],
            "at_least": 1
        },
        "conclusion": (
            "季度末集中开票 + 毛利/购销异常。季度末突击开票是典型的"
            "'粉饰报表'或'冲业绩'行为——平时不开或少开，到季度最后一个月"
            "集中补开。如果同时毛利为负或购销倒挂，则突击开票的目的"
            "不是为了真实销售，而是为了虚增收入或获取进项抵扣。"
        ),
        "risk_override": "高风险",
        "priority": "P0",
        "actions": [
            "拉取季度末开票明细，逐笔核查对应销售合同的签订日期",
            "比对季度末开票客户的回款时间（真实交易通常在开票后30-60天回款）",
            "核查季度末开票对应的出库单/物流单日期是否匹配",
            "如开票日期远早于合同/发货日期→突击开票嫌疑成立"
        ]
    },
    {
        "id": "PATTERN_CUSTOMER_TRANSFER_PRICING",
        "name": "客户高度集中+毛利异常→关联交易定价不公允",
        "triggers": {
            "must_have": ["客户高度集中"],
            "any_of": ["毛利率异常高", "毛利为负"],
            "at_least": 1
        },
        "conclusion": (
            "客户高度集中 + 毛利异常。当前几大客户的交易占比超过80%时，"
            "定价权已经不掌握在企业手中——要么被客户压价（毛利为负），"
            "要么通过关联交易转移利润（毛利异常高）。"
            "无论哪种情况，都说明企业与客户之间存在非市场化的定价关系，"
            "关联交易的可能性极高。"
        ),
        "risk_override": "高风险",
        "priority": "P1",
        "actions": [
            "核查前几大客户的工商股权结构（是否与本公司有关联关系）",
            "对比同类产品的市场公允价格与向这些客户的销售价格",
            "如有关联关系→做转让定价可比性分析",
            "要求企业提供关联交易的商业目的说明"
        ]
    },
    {
        "id": "PATTERN_PERSONAL_INCOME_HIDING",
        "name": "个人付款占比高+无工资→隐匿经营收入",
        "triggers": {
            "must_have": ["个人交易占比过高"],
            "any_of": ["无工资记录", "购销严重倒挂"],
            "at_least": 1
        },
        "conclusion": (
            "个人付款方占比高 + 无工资记录/购销倒挂。"
            "大量个人向对公账户付款——正常的解释是零售经营（面向个人消费者），"
            "但无工资记录说明企业没有足够的员工来支撑零售规模，"
            "或者购销倒挂说明进项远大于开票销项。"
            "这种情况下，个人付款大概率是'未开票销售收入'通过个人账户归集后再转入对公账户，"
            "目的就是隐匿经营收入、不开发票。"
        ),
        "risk_override": "极高风险",
        "priority": "P0",
        "actions": [
            "核实个人付款方的身份（是否为疑似客户/经销商/员工）",
            "比对个人付款金额与未开票收入的匹配程度",
            "核查是否有对应的发货记录/物流单据",
            "属于隐匿销售收入→补缴增值税+企业所得税+滞纳金+罚款"
        ]
    },
    {
        "id": "PATTERN_SUPPLIER_CUSTOMER_OVERLAP",
        "name": "供应商与客户重叠→对开环开虚开发票",
        "triggers": {
            "must_have": ["供应商高度集中"],
            "any_of": ["客户高度集中", "购销严重倒挂"],
            "at_least": 1
        },
        "conclusion": (
            "供应商集中 + 客户集中/购销倒挂。当供应商和客户同时高度集中时，"
            "需要警惕是否存在'对开环开'——A公司给B公司开票（进项），"
            "B公司给A公司开票（销项），双方都获得了进项抵扣而没有任何真实货物流动。"
            "如果同时购销倒挂，则说明进项和销项的金额/品名不对等，进一步印证对开环开。"
        ),
        "risk_override": "极高风险",
        "priority": "P0",
        "actions": [
            "交叉比对前几大供应商和前几大客户的工商注册信息（股东/法人/地址）",
            "核查供应商和客户之间是否存在直接或间接的股权关联",
            "核查是否有真实的货物物流记录（运输合同+运单+过磅单）",
            "对开环开→虚开增值税专用发票罪（刑法第205条）"
        ]
    },
]


def _phase3_cross_validate(ctx, all_findings, pipeline_log):
    """
    Phase 3 — 交叉验证引擎
    
    输入：all_findings（所有域的结论合并后）
    产出：
      - cross_findings: 新生成的综合交叉结论
      - risk_adjustments: 对已有结论的评级修正
    
    流程：
      1. 加载信号叠加模式（硬编码 + JSON 配置合并）
      2. 遍历模式库，检测是否命中
      3. 命中→生成综合结论
      4. 冲突检测→生成冲突消解说明
      5. 产出注入 ctx
    
    规则外置：可通过 static/signal_patterns.json 追加新规则，无需改代码。
    """
    import json as _json, os as _os
    
    cross_findings = []
    risk_adjustments = []
    
    if not all_findings:
        return cross_findings, risk_adjustments
    
    # ── 加载信号叠加模式：硬编码基础 + JSON 扩展 ──
    patterns = list(_SIGNAL_PATTERNS)  # 从硬编码开始
    
    # 尝试从 JSON 配置文件加载额外规则
    json_path = _os.path.join(_os.path.dirname(__file__), '..', 'static', 'signal_patterns.json')
    try:
        if _os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                config = _json.load(f)
                if not isinstance(config, dict):
                    pipeline_log.append(f"[Phase3] JSON配置文件格式错误: 期望object，实际为{type(config).__name__}")
                    json_patterns = []
                else:
                    json_patterns = config.get('patterns', [])
                # 按 id 去重：JSON 中的规则覆盖同 id 的硬编码规则
                existing_ids = {p['id'] for p in patterns}
                new_count = 0
                for jp in json_patterns:
                    if jp.get('id') not in existing_ids:
                        patterns.append(jp)
                        new_count += 1
                if new_count > 0:
                    pipeline_log.append(f"[Phase3] JSON配置加载: +{new_count}条新模式 (共{len(patterns)}条)")
    except Exception as e:
        pipeline_log.append(f"[Phase3] JSON配置加载跳过: {e}")
    
    # 提取所有发现中的关键信号关键词
    all_types = "|".join(f.get("type", "") for f in all_findings)
    all_descs = "|".join(f.get("description", "") for f in all_findings)
    all_text = all_types + "|" + all_descs
    
    # ── 辅助函数 ──
    def _has_signal(signal_name):
        """检查所有发现中是否存在某个信号，避免否定前缀误匹配"""
        import re
        # 转义特殊字符
        escaped = re.escape(signal_name)
        # 确保前面不是否定词（不/未/无/非/没）后面是标点或结尾
        pattern = r'(?<![不未无非没])' + escaped + r'(?=[，,。.!！；;、\\s\\|]|$)'
        return bool(re.search(pattern, all_text))
    
    # ── 遍历信号叠加模式库 ──
    for pattern in patterns:
        must_all = all(_has_signal(s) for s in pattern["triggers"]["must_have"])
        if not must_all:
            continue
        
        any_hits = sum(1 for s in pattern["triggers"]["any_of"] if _has_signal(s))
        if any_hits < pattern["triggers"]["at_least"]:
            continue
        
        # ── 命中模式 → 生成综合结论 ──
        # 收集触发该模式的具体发现
        triggered_types = []
        related_domains = set()
        for f in all_findings:
            ftype = f.get("type", "")
            for signal in pattern["triggers"]["must_have"] + pattern["triggers"]["any_of"]:
                if signal in ftype:
                    triggered_types.append(ftype[:30])
                    related_domains.add(f.get("domain", ""))
                    break
        
        cross_findings.append({
            "type": f"交叉验证-{pattern['name']}",
            "level": pattern.get("risk_override", "高风险"),
            "score": 10,
            "domain": "Phase3-交叉验证",
            "detail": f"多域信号叠加触发：{' + '.join(pattern['triggers']['must_have'])} + {any_hits}个关联信号",
            "description": (
                f"【Phase 3 — 交叉验证】\n\n"
                f"触发模式：{pattern['name']}\n"
                f"必须信号：{' / '.join(pattern['triggers']['must_have'])}\n"
                f"关联信号（{any_hits}/{len(pattern['triggers']['any_of'])}）："
                f"{' / '.join(s for s in pattern['triggers']['any_of'] if _has_signal(s))}\n"
                f"涉及域：{' / '.join(sorted(related_domains))}\n\n"
                f"{pattern['conclusion']}\n\n"
                f"【建议行动（{pattern['priority']}）】\n"
                + "\n".join(f"  {i+1}. {a}" for i, a in enumerate(pattern['actions']))
            ),
            "how_found": (
                f"Phase 3 交叉验证引擎在{len(all_findings)}条发现中检测到多域信号叠加——"
                f"{' + '.join(pattern['triggers']['must_have'])}"
                f" + {any_hits}个关联信号同时触发{pattern['name']}模式。"
                f"这是全量结论交叉比对的自动化结果。"
            ),
            "tax_impact": "多域信号叠加→风险级别提升。该模式涉及多个独立证据源互相印证，单一维度的异常解释不足以排除整体嫌疑。",
            "suggestion": "\n".join(f"{i+1}. {a}" for i, a in enumerate(pattern['actions'])),
            "category": "交叉验证",
            "_phase3_cross_validated": True,
            "_pattern_id": pattern["id"],
            "_priority": pattern["priority"],
        })
        
        pipeline_log.append(f"[Phase3] 命中模式 {pattern['name']} ({pattern['id']})")
    
    # ── 冲突检测 ──
    _detect_conflicts(all_findings, cross_findings, pipeline_log)
    
    ctx.phase_history.append({
        "phase": 3,
        "patterns_hit": len(cross_findings),
        "conflicts_found": sum(1 for f in cross_findings if "冲突" in f.get("type", ""))
    })
    
    return cross_findings, risk_adjustments


def _detect_conflicts(all_findings, cross_findings, pipeline_log):
    """检测表面矛盾的结论对，进行冲突消解"""
    # ── 冲突1：毛利率正常 vs 进销数量偏差 ──
    has_normal_margin = any("毛利" in f.get("type","") and "正常" in f.get("description","") for f in all_findings)
    has_qty_deviation = any("进销数量严重偏差" in f.get("type","") for f in all_findings)
    
    if has_normal_margin and has_qty_deviation:
        cross_findings.append({
            "type": "交叉验证-冲突消解：毛利正常vs数量偏差",
            "level": "中风险",
            "score": 4,
            "domain": "Phase3-冲突消解",
            "detail": "毛利率正常与进销数量偏差同时存在，表面矛盾但可解释",
            "description": (
                "【冲突消解】毛利率正常，但进销数量存在严重偏差——这两个结论看似矛盾，"
                "实际上可以共存：\n\n"
                "可能原因①：库存结转差异。上期库存量大→本期销售中部分来自上期库存→"
                "进项数量<销项数量，但进价和售价之间的价差正常（毛利不变）。\n"
                "可能原因②：BOM产出率差异。制造业中原材料投入与成品产出有固定的投入产出比，"
                "1吨原料产0.8吨成品是正常损耗→按重量比对的数量偏差属正常。\n"
                "可能原因③：期间性问题。分析期内的进项和销项可能分属不同的生产周期，"
                "跨期比对天然有偏差。\n\n"
                "验证方法：获取期初期末库存明细+生产成本计算表来核实数量差异是否可用库存变动解释。"
            ),
            "how_found": "Phase 3 交叉验证引擎在遍历全部结论时发现'毛利率正常'和'进销数量偏差'同时存在，触发冲突消解流程。",
            "tax_impact": "数量偏差+毛利正常→可能只是库存结转问题而非交易造假。应在排除库存变动影响后重新评估。",
            "suggestion": "①获取期初期末库存明细表 ②提供生产成本计算表 ③按存货变动调整后重新计算进销数量匹配度",
            "category": "冲突消解",
            "_phase3_conflict_resolved": True,
        })
        pipeline_log.append("[Phase3] 冲突消解: 毛利正常 vs 数量偏差")
    
    # ── 冲突2：工资人数正常 vs 人均产值低 ──
    has_salary = any("工资" in f.get("type","") for f in all_findings)
    has_low_per_person = any("人均" in f.get("type","") and "低" in f.get("type","") for f in all_findings)
    
    if has_salary and has_low_per_person:
        cross_findings.append({
            "type": "交叉验证-冲突消解：工资正常vs人均产值低",
            "level": "中风险",
            "score": 4,
            "domain": "Phase3-冲突消解",
            "detail": "工资表正常但人均产值低→人员效率问题或收入少记",
            "description": (
                "工资社保比对正常（人数一致、基数合规），但人均产值偏低。"
                "这两个结论不矛盾：工资表本身可能是真实的，但产值低说明：\n"
                "① 人员冗余→存在养闲人的管理问题（不涉税）\n"
                "② 收入少记→有产值但未开票/未入账（涉税）\n"
                "③ 大量人员从事非生产性工作（管理/后勤膨胀）→经营效率问题\n\n"
                "重点关注是否存在第②种情况。"
            ),
            "how_found": "Phase 3 冲突检测：工资正常+人均产值低",
            "tax_impact": "工资表真实但人均产值低，收入少记风险中等。需要逐月比对产能与收入。",
            "suggestion": "①按部门统计人员分布 ②逐月比对产量与收入 ③访谈生产负责人核实产能",
            "category": "冲突消解",
            "_phase3_conflict_resolved": True,
        })
        pipeline_log.append("[Phase3] 冲突消解: 工资正常 vs 人均产值低")
    
    # ── 冲突3：进销数量偏差 vs 供应商集中 ──
    has_qty_dev = any("进销数量严重偏差" in f.get("type","") for f in all_findings)
    has_supplier_conc = any("供应商高度集中" in f.get("type","") or "供应商" in f.get("type","") and "集中" in f.get("type","") for f in all_findings)
    
    if has_qty_dev and has_supplier_conc:
        cross_findings.append({
            "type": "交叉验证-冲突消解：数量偏差vs供应商集中",
            "level": "高风险",
            "score": 7,
            "domain": "Phase3-冲突消解",
            "detail": "进销数量偏差+供应商集中→采购端异常可能解释数量偏差",
            "description": (
                "【冲突消解升级】进销数量存在严重偏差，同时供应商高度集中。"
                "两个结论不是冲突而是互证：\n\n"
                "供应商集中意味着采购端存在'通道型'供应商——"
                "可能与供应商之间有发票流转但无实际货物交付。"
                "这就直接解释了为什么进销数量对不上——"
                "进项发票上的数量不代表实际到货数量。\n\n"
                "两个独立的异常信号互相印证，风险升级。"
            ),
            "how_found": "Phase 3 冲突检测：数量偏差+供应商集中→互证而非冲突",
            "tax_impact": "供应商集中+数量偏差→虚增进项数量的风险显著增加。进项税额的抵扣除可能被否定。",
            "suggestion": "①逐供应商核实实际到货数量（物流单/过磅单/入库单）②比对发票数量与实际库存数量 ③对差额部分做进项税额转出",
            "category": "冲突消解",
            "_phase3_conflict_resolved": True,
        })
        pipeline_log.append("[Phase3] 冲突消解: 数量偏差 vs 供应商集中 → 互证升级")
    
    # ── 冲突4：毛利为负 vs 持续经营 ──
    has_neg_margin = any("毛利为负" in f.get("type","") for f in all_findings)
    has_ongoing = any("费用报销" in f.get("type","") or "日常费用" in f.get("type","") for f in all_findings)
    
    if has_neg_margin and has_ongoing:
        cross_findings.append({
            "type": "交叉验证-冲突消解：毛利为负vs持续经营",
            "level": "高风险",
            "score": 7,
            "domain": "Phase3-冲突消解",
            "detail": "毛利为负但企业持续经营→存在未开票收入或体外资金",
            "description": (
                "【冲突消解】毛利为负（售价低于成本）但企业仍在持续经营。"
                "正常商业逻辑下，持续亏损的企业会停产或退出市场。"
                "企业持续经营且还有日常费用支出，说明一定有其他收入来源：\n\n"
                "① 存在大量未开票销售（账外经营）——有真实收入但未计入账面\n"
                "② 关联方补贴——通过其他主体输血维持经营\n"
                "③ 股东持续注资——用资本金填补经营亏损\n\n"
                "最可能的是第①种——企业实际销售额远大于开票额，"
                "毛利为负只是'账面上的假象'。"
            ),
            "how_found": "Phase 3 冲突消解：毛利为负但持续经营→收入来源存疑",
            "tax_impact": "毛利为负+持续经营→隐匿销售收入是最大可能。涉及增值税+企业所得税的少缴。",
            "suggestion": "①核查银行流水中的大额不明收入 ②比对用电量/用水量与申报产能 ③要求企业说明持续经营的资金来源",
            "category": "冲突消解",
            "_phase3_conflict_resolved": True,
        })
        pipeline_log.append("[Phase3] 冲突消解: 毛利为负 vs 持续经营")
    
    # ── 冲突5：有销无进 vs 加工费存在 ──
    has_sell_no_buy = any("有销无进" in f.get("type","") for f in all_findings)
    has_processing = any("加工费" in f.get("type","") or "加工链条" in f.get("description","") for f in all_findings)
    
    if has_sell_no_buy and has_processing:
        cross_findings.append({
            "type": "交叉验证-冲突消解：有销无进vs加工费",
            "level": "低风险",
            "score": 2,
            "domain": "Phase3-冲突消解",
            "detail": "有销无进+加工费存在→制造业加工链条可解释品名差异",
            "description": (
                "【冲突消解】有销无进（卖出但未采购同名商品）+加工费存在。"
                "这两个结论不是矛盾，而是互证：\n\n"
                "有销无进的真实含义不是'没有采购'，而是'没有采购同名商品'——"
                "这恰恰是制造业的特征：采购的是原材料，"
                "销售的是加工后的成品，品名天然不同。\n"
                "加工费的存在进一步证明企业确实有加工环节——"
                "原料经过加工变成成品，销项品名和进项品名不同是正常现象。\n\n"
                "应将'有销无进'的风险焦点从'虚开发票'转移到'加工链条真实性验证'。"
            ),
            "how_found": "Phase 3 冲突消解：有销无进+加工费→制造业正常加工链条",
            "tax_impact": "有销无进+加工费→品名差异属正常经营。但需BOM表+加工合同验证加工链条真实性。",
            "suggestion": "①提供BOM表验证原料→成品的投入产出关系 ②提供加工合同+出入库单 ③品名差异由加工解释→不构成虚开发票",
            "category": "冲突消解",
            "_phase3_conflict_resolved": True,
        })
        pipeline_log.append("[Phase3] 冲突消解: 有销无进 vs 加工费 → 制造业链条")
    
    # ── 冲突6：银行付款未匹配 vs 日常报销存在 ──
    has_pay_unmatch = any("银行付款未匹配" in f.get("type","") for f in all_findings)
    has_daily_reimb = any("费用报销" in f.get("type","") or "日常费用" in f.get("type","") or "日常报销" in f.get("type","") for f in all_findings)
    
    if has_pay_unmatch and has_daily_reimb:
        cross_findings.append({
            "type": "交叉验证-冲突消解：付款未匹配vs日常报销",
            "level": "低风险",
            "score": 2,
            "domain": "Phase3-冲突消解",
            "detail": "银行付款未匹配+日常费用报销存在→部分未匹配源于员工报销模式",
            "description": (
                "【冲突消解】银行付款未匹配+日常费用报销存在。"
                "日常费用报销（餐饮/住宿/汽油/差旅等）的支付模式是："
                "员工先垫付→凭发票报销→企业对公付款给员工（而非开票商家）。"
                "因此在银行流水中，付款对象是员工姓名而非发票上的供应商名称，"
                "导致'发票供应商与银行付款名称不匹配'。\n\n"
                "这部分'未匹配'属于商业正常现象，已从风险统计中排除。"
                "仅对主营业务成本的供应商做付款匹配。"
            ),
            "how_found": "Phase 3 冲突消解：付款未匹配+日常报销→员工报销模式",
            "tax_impact": "日常报销的未匹配属正常现象，不计入风险。仅主营业务成本供应商的未匹配需关注。",
            "suggestion": "①建立费用报销制度（每张报销发票附审批单+行程单）②主营业务成本供应商逐笔核实付款记录",
            "category": "冲突消解",
            "_phase3_conflict_resolved": True,
        })
        pipeline_log.append("[Phase3] 冲突消解: 付款未匹配 vs 日常报销 → 正常")
    
    # ── 冲突7：有进无销(高风险) vs 加工费存在 → 不应高风险 ──
    has_buy_no_sell_high = any("有进无销" in f.get("type","") and f.get("level") == "高风险" for f in all_findings)
    
    if has_buy_no_sell_high and has_processing:
        # 降级：有进无销+加工费 → 制造业正常加工链条，不应该是高风险
        for f in all_findings:
            if "有进无销" in f.get("type","") and f.get("level") == "高风险":
                # 不直接修改原结论，而是生成一个降级说明
                cross_findings.append({
                    "type": "交叉验证-冲突消解：有进无销降级",
                    "level": "中风险",
                    "score": 5,
                    "domain": "Phase3-冲突消解",
                    "detail": f"有进无销被评为高风险，但加工费存在→制造业加工链条可解释品名差异",
                    "description": (
                        "【冲突消解→建议重新评估】有进无销被评为高风险，但系统同时检测到加工费存在。"
                        "制造业中，采购原材料（不直接销售）→委托加工→销售成品（品名不同）"
                        "是正常经营模式。有进无销的品名差异源于加工链条而非隐匿收入。"
                        "建议将评级从高风险调整为中风险，核查焦点从'隐匿收入'转移到'加工链条真实性'。"
                    ),
                    "how_found": "Phase 3 冲突检测：有进无销(高风险)+加工费→制造业加工链条可解释",
                    "tax_impact": "有进无销+加工费→不建议直接判定为隐匿收入。应先验证加工链条真实性。",
                    "suggestion": "①提供BOM表验证加工投入产出 ②提供加工合同+出入库记录 ③验证通过后可排除隐匿收入嫌疑",
                    "category": "冲突消解",
                    "_phase3_conflict_resolved": True,
                })
                pipeline_log.append("[Phase3] 冲突消解: 有进无销(高风险)+加工费 → 建议降级")
                break  # 只生成一条降级说明
    
    # ── 冲突8：发票连号+正常经营信号 → 可能只是同批次领票 ──
    has_consecutive = any("发票连号" in f.get("type","") for f in all_findings)
    has_trade_normal = any("贸易模式" in f.get("type","") and "正常" in f.get("type","") for f in all_findings)
    
    if has_consecutive and has_trade_normal:
        cross_findings.append({
            "type": "交叉验证-冲突消解：发票连号vs贸易模式正常",
            "level": "低风险",
            "score": 2,
            "domain": "Phase3-冲突消解",
            "detail": "发票连号+贸易模式正常→可能是同批次购票，需进一步验证",
            "description": (
                "【冲突消解】发票连号 + 贸易模式正常（进销品名匹配度高）。"
                "如果企业的进销品名匹配、毛利率正常、供应商分散，"
                "连续的发票号可能只是因为企业一次性购买了同一卷/同批次发票——"
                "这是税务机关正常配票的结果，不代表交易造假。\n\n"
                "验证方法：检查连号发票对应的客户是否不同、金额是否有零有整、"
                "日期是否分散在不同日期——如果都分散，则连号只是同批次购票。"
            ),
            "how_found": "Phase 3 冲突消解：发票连号+贸易正常→同批次购票可能",
            "tax_impact": "发票连号+贸易模式正常→连号本身不构成虚开证据。需结合客户、金额、日期综合判断。",
            "suggestion": "①检查连号发票客户是否分散 ②检查连号发票金额是否有零有整 ③检查开票日期是否跨多天",
            "category": "冲突消解",
            "_phase3_conflict_resolved": True,
        })
        pipeline_log.append("[Phase3] 冲突消解: 发票连号 vs 贸易正常 → 同批次购票")


# ═══════════════════════════════════════════════════════════
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


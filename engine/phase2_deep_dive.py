# Phase 2 — 定向深挖（Signal-Driven Deep Dive）
#
# 设计理念：不是29域全量盲跑，而是基于 Phase 1 的信号，
# 像人类税务合规员一样定向选择深挖方向和深度。
#
# 信号→域映射表驱动：
#   看到"购销倒挂"→深挖毛利率+供应商+资金流向+经营实质
#   看到"加工费"→深挖BOM+供应商画像+经营实质地理+上下游
#   多个信号叠加→域组合策略
#   绿灯信号→证明某方面正常，跳过相关深挖
#
# 三级深度：
#   shallow（浅查）：快速比率计算，确认信号
#   normal（常规）：标准分析流程
#   deep（深挖）：多源交叉+关联穿透+证据链串联
# ═══════════════════════════════════════════════════════════
#
# 域函数通过 register 机制延迟绑定：main.py 加载后，engine/phase2_deep_dive.py
# 可调用 sys.modules 获取已加载的 main 模块中的域函数。

# ═══════════════════════════════════════════════════════════
# Lazy imports inside _phase2_deep_dive (avoids circular import at module load time)

# ├─ 信号→域映射表
# │  每个信号定义了应深挖的域及深度
_SIGNAL_DOMAIN_MAP = {
    # ── 红灯信号 ──
    "购销严重倒挂": {
        "domains": ["进销毛利率分析", "供应商穿透分析", "资金流向追踪", "经营实质分析"],
        "depth": "deep",
        "reason": "进>销1.5倍→需验证进项真实性+是否存在隐匿收入+供应商是否真实"
    },
    "毛利为负": {
        "domains": ["进销毛利率分析", "经营实质分析", "行业对标分析"],
        "depth": "deep",
        "reason": "毛利为负→可能是虚增进项或隐匿收入或不合理关联交易"
    },
    "缺少银行流水": {
        "domains": ["凭证发票收入对比", "经营实质分析", "增值税申报比对"],
        "depth": "deep",
        "reason": "无银行流水→需用凭证和发票替代验证资金流真实性"
    },
    # ── 黄灯信号 ──
    "存在加工费": {
        "domains": ["发票实质性审计", "经营实质分析", "供应商画像分析", "上下游穿透分析"],
        "depth": "deep",
        "reason": "加工费发票→需验证加工链条真实性(BOM+合同+物流)"
    },
    "制造业加工链条待验证": {
        "domains": ["发票实质性审计", "供应商画像分析", "经营实质地理分析", "关联交易穿透检测"],
        "depth": "deep",
        "reason": "制造业加工链条+无BOM→需全方位验证加工真实性"
    },
    "无进项发票": {
        "domains": ["经营实质分析", "发票实质性审计", "增值税申报比对"],
        "depth": "normal",
        "reason": "有销项无进项→可能是服务/劳务(正常)或虚开发票"
    },
    "无工资记录": {
        "domains": ["工资社保比对", "人员与业务匹配", "经营实质分析"],
        "depth": "normal",
        "reason": "有收入无工资→可能虚开发票或未全员申报个税"
    },
    "毛利率异常高": {
        "domains": ["进销毛利率分析", "行业对标分析", "经营实质分析"],
        "depth": "normal",
        "reason": "毛利率>80%→可能存在关联交易定价不公允或隐匿采购"
    },
    "银行流水数据量少": {
        "domains": ["凭证发票收入对比", "经营实质分析"],
        "depth": "shallow",
        "reason": "流水数据量少→用凭证和发票替代验证，降置信度"
    },
    "发票数据量少": {
        "domains": ["凭证发票收入对比", "增值税申报比对"],
        "depth": "shallow",
        "reason": "发票数据量少→用凭证替代验证"
    },
    "个人交易占比过高": {
        "domains": ["个人交易风险", "资金流向追踪", "关联交易穿透检测"],
        "depth": "deep",
        "reason": "大量个人付款→需核实资金性质+是否为隐匿经营收入"
    },
    "供应商高度集中": {
        "domains": ["供应商穿透分析", "供应商画像分析", "关联交易穿透检测"],
        "depth": "deep",
        "reason": "前3大供应商占比过高→可能存在关联交易或虚开发票"
    },
    # ── 新增：发票行为异常 ──
    "发票连号": {
        "domains": ["发票实质性审计", "经营实质分析"],
        "depth": "deep",
        "reason": "连续发票号→可能是集中开票或人为编造交易"
    },
    "金额整十整百比例高": {
        "domains": ["发票实质性审计"],
        "depth": "normal",
        "reason": "发票金额大量为整数→不符合真实交易的价格分布"
    },
    "金额分布异常均匀": {
        "domains": ["发票实质性审计", "经营实质分析"],
        "depth": "normal",
        "reason": "每张发票金额接近→人为编造而非真实波动"
    },
    "季度末集中开票": {
        "domains": ["发票实质性审计", "收入时间线调查", "经营实质分析"],
        "depth": "deep",
        "reason": "季度末突击开票→可能人为调节收入或虚开发票"
    },
    # ── 新增：银行异常 ──
    "个人交易占比过高": {
        "domains": ["个人交易风险", "资金流向追踪", "关联交易穿透检测"],
        "depth": "deep",
        "reason": "大量个人付款方→需核实资金性质+是否为隐匿经营收入"
    },
    # ── 新增：客户/供应商结构异常 ──
    "客户高度集中": {
        "domains": ["客户维度三源穿透", "关联交易穿透检测", "经营实质分析"],
        "depth": "deep",
        "reason": "前3大客户占比过高→可能存在关联交易或客户依赖"
    },
}


def _phase2_deep_dive(ctx, company_id, db, bank_txs, invoices, sal_invs, pur_invs,
                      salaries, social_security, vouchers, inventory, docs, file_results,
                      contract_data, voucher_revenue, total_parsed, pipeline_log):
    """
    Phase 2 — 信号驱动的定向深挖
    
    流程：
    1. 读取 ctx.red_flags + ctx.yellow_flags
    2. 查信号→域映射表，确定需深挖的域
    3. 去重：同一域不重复跑
    4. 对每个选中域按指定深度分析
    5. 产出注入 ctx（索引到 finding_index）
    
    返回：
        deep_dive_results: [{"domain": "XX", "findings": [...]}, ...]
    """
    # ── 延迟导入 main 中的域函数（避免循环依赖）──
    import sys as _sys, importlib as _il
    _m = _sys.modules.get("main") or _sys.modules.get("__main__")
    if not _m:
        try: _m = _il.import_module("main")
        except Exception: pass
    if _m:
        for _fname in ["_domain_profit_analysis","_domain_supplier_deep","_domain_fund_flow_mapping",
                        "_domain_business_substance","_domain_industry_benchmark","_domain_voucher_invoice_revenue_compare",
                        "_domain_vat_declaration_compare","_domain_invoice_audit","_domain_supplier_profiling",
                        "_domain_supply_chain_deep","_domain_business_premise_geo","_domain_related_party_check",
                        "_domain_salary_ss_hf_compare","_domain_workforce_profiling","_domain_personal_transactions",
                        "_domain_revenue_timeline","_domain_customer_revenue_matching"]:
            _fn = getattr(_m, _fname, None)
            if _fn is None:
                _fn = lambda *a, **kw: []
            globals()[_fname] = _fn  # 注入到当前模块的全局命名空间，lambda 闭包可访问
    else:
        # 绝对兜底：全部用空函数
        for _fname in ["_domain_profit_analysis","_domain_supplier_deep","_domain_fund_flow_mapping",
                        "_domain_business_substance","_domain_industry_benchmark","_domain_voucher_invoice_revenue_compare",
                        "_domain_vat_declaration_compare","_domain_invoice_audit","_domain_supplier_profiling",
                        "_domain_supply_chain_deep","_domain_business_premise_geo","_domain_related_party_check",
                        "_domain_salary_ss_hf_compare","_domain_workforce_profiling","_domain_personal_transactions",
                        "_domain_revenue_timeline","_domain_customer_revenue_matching"]:
            globals()[_fname] = lambda *a, **kw: []
    
    deep_dive_results = []
    domains_to_run = {}  # {domain_name: depth}
    
    # ── 步骤1：收集信号并映射域 ──
    all_signals = ctx.red_flags + ctx.yellow_flags
    
    for signal in all_signals:
        signal_type = signal.get("type", "")
        # 在映射表中查找最匹配的信号
        matched = None
        for map_signal, config in _SIGNAL_DOMAIN_MAP.items():
            if map_signal in signal_type or signal_type in map_signal:
                matched = config
                break
        if not matched:
            continue
        
        for domain in matched["domains"]:
            # 取最高深度（deep > normal > shallow）
            depth_order = {"deep": 3, "normal": 2, "shallow": 1}
            current_depth = domains_to_run.get(domain, "shallow")
            if depth_order.get(matched["depth"], 1) > depth_order.get(current_depth, 0):
                domains_to_run[domain] = matched["depth"]
    
    if not domains_to_run:
        pipeline_log.append("[Phase2] 无信号触发，跳过定向深挖")
        return deep_dive_results
    
    pipeline_log.append(f"[Phase2] 信号触发{len(domains_to_run)}个域深挖: {list(domains_to_run.keys())}")
    
    # ── 步骤2：执行选中域的分析 ──
    # 每个域有对应的分析函数，按深度执行
    # 域函数必须在 lazy import 之后定义，确保闭包捕获正确的函数引用
    
    # 域函数注册表 — 使用完整函数引用而非 lambda，避免闭包作用域问题
    domain_functions = {
        "进销毛利率分析": lambda: _domain_profit_analysis(sal_invs, pur_invs, inventory, voucher_revenue),
        "供应商穿透分析": lambda: _domain_supplier_deep(pur_invs),
        "资金流向追踪": lambda: _domain_fund_flow_mapping(bank_txs, sal_invs, pur_invs),
        "经营实质分析": lambda: _domain_business_substance(db, company_id, sal_invs, pur_invs, bank_txs, salaries),
        "行业对标分析": lambda: _domain_industry_benchmark(sal_invs, pur_invs, voucher_revenue, salaries, inventory, ctx.company_profile.get("industry", "")),
        "凭证发票收入对比": lambda: _domain_voucher_invoice_revenue_compare(voucher_revenue, sal_invs, bank_txs),
        "增值税申报比对": lambda: _domain_vat_declaration_compare(invoices, bank_txs, db, company_id),
        "发票实质性审计": lambda: _domain_invoice_audit(invoices, ctx.company_profile.get("industry", "")),
        "供应商画像分析": lambda: _domain_supplier_profiling(pur_invs, bank_txs),
        "上下游穿透分析": lambda: _domain_supply_chain_deep(invoices, bank_txs),
        "经营实质地理分析": lambda: _domain_business_premise_geo(bank_txs, invoices, docs, ctx.company_profile.get("industry", "")),
        "关联交易穿透检测": lambda: _domain_related_party_check(sal_invs, pur_invs, bank_txs),
        "工资社保比对": lambda: _domain_salary_ss_hf_compare(salaries, social_security),
        "人员与业务匹配": lambda: _domain_workforce_profiling(salaries, voucher_revenue, bank_txs, social_security),
        "个人交易风险": lambda: _domain_personal_transactions(sal_invs),
        "收入时间线调查": lambda: _domain_revenue_timeline(vouchers, sal_invs, bank_txs),
        "客户维度三源穿透": lambda: _domain_customer_revenue_matching(bank_txs, sal_invs, contract_data, voucher_revenue),
    }
    
    for domain, depth in domains_to_run.items():
        func = domain_functions.get(domain)
        if not func:
            pipeline_log.append(f"[Phase2] 域'{domain}'无对应分析函数，跳过")
            continue
        
        # ── ctx 全局注入：域函数可通过 get_audit_ctx() 获取上下文 ──
        from .context import set_audit_ctx
        set_audit_ctx(ctx)
        
        try:
            findings = func()
            # ── ctx 注入：将当前 ctx 的摘要附加到每条发现上 ──
            if findings and ctx:
                ctx_summary = {
                    "industry": ctx.company_profile.get("industry", ""),
                    "biz_model": ctx.company_profile.get("biz_model", ""),
                    "has_processing_fee": ctx.has_processing_fee,
                    "data_quality_score": ctx.data_quality_score,
                }
                for f in findings:
                    if isinstance(f, dict):
                        f["_ctx_industry"] = ctx_summary["industry"]
                        f["_ctx_biz_model"] = ctx_summary["biz_model"]
                        f["_ctx_has_processing"] = ctx_summary["has_processing_fee"]
            if findings:
                deep_dive_results.append({
                    "domain": domain,
                    "findings": findings,
                    "_phase2_depth": depth,
                    "_phase2_triggered": True
                })
                ctx.index_findings(findings, domain=domain)
                pipeline_log.append(f"[Phase2] {domain}({depth}): {len(findings)}项发现")
        except Exception as e:
            pipeline_log.append(f"[Phase2] {domain} 执行异常: {e}")
    
    ctx.phase_history.append({
        "phase": 2,
        "domains_run": list(domains_to_run.keys()),
        "findings_count": sum(len(dr["findings"]) for dr in deep_dive_results)
    })
    
    return deep_dive_results


# ═══════════════════════════════════════════════════════════
# Phase 3 — 交叉验证（Cross-Validation）
#
# 核心能力：
#   1. 信号叠加检测 — 多个独立结论组合意味着更大的风险模式
#   2. 冲突消解 — 两个表面矛盾的结论互相验证
#   3. 风险提级/降级 — 基于交叉证据自动调整评级
#   4. 综合结论生成 — 从孤立发现中提炼出模式
#
# 设计理念：
#   人类税务合规员不会只看单条结论，而是看"模式"。
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
            "涉及偷税→移送税务合规局"
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



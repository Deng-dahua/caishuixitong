def _phase1_triage(ctx, company_id, db, bank_txs, invoices, sal_invs, pur_invs, salaries, social_security, vouchers, inventory, docs, file_results, pipeline_log):
    """
    Phase 1 — 初查（Triage）
    
    目标：快速建立企业画像和财务全景，识别重大信号。
    不做深入分析，只做"有没有问题"的初步判断。
    
    产出入 AuditContext:
      - company_profile: 行业/经营模式/规模
      - financial_snapshot: 关键财务指标
      - biz_cost_classification: 主营业务成本三层分类
      - red_flags / yellow_flags: 初步信号
      - data_quality_score: 资料质量评分
    """
    from collections import defaultdict
    
    from .main_biz_cost import identify_main_biz_cost
    
    ctx.phase_history.append({"phase": 1, "start": True})
    
    # ── 1.1 财务快照 ──
    ctx.financial_snapshot["total_sales"] = sum(float(inv.get("amount", 0) or 0) for inv in sal_invs)
    ctx.financial_snapshot["total_purchases"] = sum(float(inv.get("amount", 0) or 0) for inv in pur_invs)
    ctx.financial_snapshot["total_bank_in"] = sum(float(tx.get("credit", 0) or 0) for tx in bank_txs)
    ctx.financial_snapshot["total_bank_out"] = sum(float(tx.get("debit", 0) or 0) for tx in bank_txs)
    ctx.financial_snapshot["total_salary"] = sum(float(s.get("实发金额", s.get("实发", s.get("amount", 0))) or 0) for s in salaries)
    ctx.financial_snapshot["sale_count"] = len(sal_invs)
    ctx.financial_snapshot["pur_count"] = len(pur_invs)
    ctx.financial_snapshot["bank_tx_count"] = len(bank_txs)
    ctx.financial_snapshot["salary_count"] = len(salaries)
    
    # 毛利率
    sales_total = ctx.financial_snapshot["total_sales"]
    pur_total = ctx.financial_snapshot["total_purchases"]
    if sales_total > 0:
        ctx.financial_snapshot["gross_margin_pct"] = (sales_total - pur_total) / sales_total * 100
    
    pipeline_log.append(f"[Phase1] 财务快照: 销{sales_total:,.0f}/进{pur_total:,.0f}/银行{ctx.financial_snapshot['bank_tx_count']}笔")
    
    # ── 1.2 主营业务成本识别（共享函数）──
    if pur_invs:
        ctx.biz_cost_classification = identify_main_biz_cost(pur_invs, sal_invs)
        pipeline_log.append(f"[Phase1] 主营成本识别: 核心{len(ctx.biz_cost_classification['core_cost_invs'])}张/重大费用{len(ctx.biz_cost_classification['major_expense_invs'])}张/日常报销{len(ctx.biz_cost_classification['minor_expense_invs'])}张")
    
    # ── 1.3 企业画像推断 ──
    _infer_company_profile(ctx, pur_invs, sal_invs, bank_txs, salaries)
    pipeline_log.append(f"[Phase1] 企业画像: 行业={ctx.company_profile['industry']} 模式={ctx.company_profile['biz_model']}")
    
    # ── 1.4 初查信号检测 ──
    _detect_triage_signals(ctx, pur_invs, sal_invs, bank_txs, invoices)
    
    # ── 1.5 资料质量评估 ──
    _assess_data_quality(ctx, docs, file_results, bank_txs, invoices, salaries)
    
    ctx.phase_history[-1]["end"] = True
    ctx.phase_history[-1]["summary"] = (
        f"Phase1完成: {len(ctx.red_flags)}红灯/{len(ctx.yellow_flags)}黄灯, "
        f"资料质量{ctx.data_quality_score}分, "
        f"行业{ctx.company_profile['biz_model']}"
    )
    
    return ctx


def _infer_company_profile(ctx, pur_invs, sal_invs, bank_txs, salaries):
    """从数据中推断企业行业和经营模式，并加载行业自适应配置"""
    import json, os
    cp = ctx.company_profile
    
    # ── 经营模式推断 ──
    pur_goods_set = set()
    sal_goods_set = set()
    for inv in pur_invs:
        g = str(inv.get("goods", inv.get("货物或应税劳务名称", ""))).strip()
        if g: pur_goods_set.add(g)
    for inv in sal_invs:
        g = str(inv.get("goods", inv.get("货物或应税劳务名称", ""))).strip()
        if g: sal_goods_set.add(g)
    
    # 加工信号（仅制造/贸易型企业适用，服务型企业跳过）
    has_processing = False
    biz_model_check = ctx.company_profile.get("biz_model", "") if hasattr(ctx, 'company_profile') and ctx.company_profile else ""
    if biz_model_check not in ("服务",):
        has_processing = any("加工" in g for g in pur_goods_set)
    ctx.has_processing_fee = has_processing
    
    # 品名重合度
    if pur_goods_set and sal_goods_set:
        overlap = len(pur_goods_set & sal_goods_set)
        total_unique = len(pur_goods_set | sal_goods_set)
        overlap_ratio = overlap / max(total_unique, 1)
    else:
        overlap_ratio = 0
    
    # ── 经营模式判断（插件注册模式）──
    _biz_model_rules = [
        ("制造业", 
         lambda: has_processing and overlap_ratio < 0.5,
         lambda: cp.update({"has_manufacturing": True})),
        ("贸易",
         lambda: overlap_ratio >= 0.5 and pur_goods_set and sal_goods_set,
         lambda: cp.update({"has_trading": True})),
        ("服务/劳务",
         lambda: not pur_invs and sal_invs,
         lambda: None),
    ]
    
    matched = False
    for model_name, condition, side_effect in _biz_model_rules:
        if condition():
            cp["biz_model"] = model_name
            if side_effect:
                side_effect()
            matched = True
            break
    if not matched:
        cp["biz_model"] = "未确定"
    
    # ── 规模推断 ──
    total_revenue = ctx.financial_snapshot["total_sales"]
    emp_count = ctx.financial_snapshot["salary_count"]
    if total_revenue > 50000000: cp["scale"] = "大"
    elif total_revenue > 10000000: cp["scale"] = "中"
    elif total_revenue > 1000000: cp["scale"] = "小"
    else: cp["scale"] = "微"
    
    # ── 行业推断（基于品名关键词，不做行业特化）──
    _infer_industry_from_goods(ctx, pur_goods_set, sal_goods_set)
    
    # ── 加载行业自适应配置（industry_profiles.json）──
    _load_industry_profile(ctx)


def _infer_industry_from_goods(ctx, pur_goods, sal_goods):
    """从发票品名推断行业——全行业自适应，不硬编码任何行业关键词
    
    ═══ 行业推断铁律 ═══
    仅以销项发票品名为依据，不参考进项发票品名。
    WHY: 销项=企业实际经营产出（卖什么就是什么行业）
         进项=采购投入/成本结构（买什么不代表行业，如传媒公司也会买餐饮服务）
    
    方法：利用中国金税发票的税收分类编码前缀（*XX*格式）
    例如：*广告服务*广告发布费 → 行业=广告服务
    无分类编码时用"综合"兜底
    """
    cp = ctx.company_profile
    
    # ═══ 仅从销项发票品名中提取行业分类编码 ═══
    import re
    cat_counts = {}
    
    for goods in sal_goods:
        # 匹配 *分类名称* 格式（金税发票标准格式）
        match = re.search(r'\*([^*]+)\*', str(goods))
        if match:
            cat = match.group(1).strip()
            # 过滤掉明显不是行业分类的模式（如纯数字、单字）
            if len(cat) >= 2 and not cat.isdigit():
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
    
    if cat_counts:
        # 取出现最多的分类编码作为行业
        best_cat = max(cat_counts, key=cat_counts.get)
        cp["industry"] = best_cat
    else:
        cp["industry"] = "综合"


def _load_industry_profile(ctx):
    """根据检测到的行业加载对应的行业画像配置（信号权重、基准阈值、重点域等）"""
    import json, os
    
    cp = ctx.company_profile
    industry = cp.get("industry", "综合")
    biz_model = cp.get("biz_model", "未确定")
    
    # 尝试多次路径找到 industry_profiles.json
    for base in [os.path.dirname(__file__), os.path.join(os.path.dirname(__file__), "..")]:
        profile_path = os.path.join(base, "static", "industry_profiles.json")
        if os.path.exists(profile_path):
            break
    else:
        profile_path = os.path.join(os.path.dirname(__file__) or ".", "static", "industry_profiles.json")
    
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            profiles = json.load(f)
    except Exception:
        ctx.industry_profile = {}
        return
    
    industries = profiles.get("industries", {})
    default = profiles.get("default_profile", {})
    
    # 匹配策略：精确匹配行业名 → subtypes → biz_model映射
    matched = None
    
    for key, prof in industries.items():
        if industry == key or industry in prof.get("subtypes", []):
            matched = prof
            break
    
    if not matched:
        model_to_key = {"制造业": "制造业", "贸易": "贸易批发", "服务/劳务": "服务业"}
        matched_key = model_to_key.get(biz_model)
        if matched_key:
            matched = industries.get(matched_key)
    
    ctx.industry_profile = matched or default


def _detect_triage_signals(ctx, pur_invs=None, sal_invs=None, bank_txs=None, invoices=None):
    """初查阶段信号检测——行业自适应 + 历史数据校准。
    
    阈值优先级：历史校准(同行业统计) > 行业配置(industry_profiles.json) > 兜底通用值
    """
    fs = ctx.financial_snapshot
    cp = ctx.company_profile
    ip = ctx.industry_profile or {}
    benchmarks = ip.get("benchmarks", {})
    
    # ── 历史校准阈值（从相似案例统计中动态学习）──
    calibrated = ctx._memory_data.get("calibrated_thresholds", {}) if hasattr(ctx, '_memory_data') and ctx._memory_data else {}
    
    # 阈值优先级：历史校准 > 行业配置 > 兜底
    gm_low = calibrated.get("gross_margin_low") or benchmarks.get("gross_margin_pct", {}).get("low", 0)
    gm_high = calibrated.get("gross_margin_high") or benchmarks.get("gross_margin_pct", {}).get("high", 40)
    pur_sale_low = benchmarks.get("purchase_sales_ratio", {}).get("normal_low", 0.85)
    supp_warn = calibrated.get("supplier_concentration_warn") or benchmarks.get("supplier_concentration_warn", 80)
    cust_warn = calibrated.get("customer_concentration_warn") or benchmarks.get("customer_concentration_warn", 80)
    
    # 记录校准来源
    if calibrated:
        calib_note = f"（历史校准：{calibrated.get('gross_margin_sample_size',0)}家同行业企业）"
    else:
        calib_note = ""
    
    # ═══════════════════════════════════════════
    # 红灯：基础数据严重异常（立即深挖）
    # ═══════════════════════════════════════════
    
    # 购销倒挂（进项远超销项）：可能虚增进项或隐匿收入
    # 行业阈值：如贸易<0.6即异常，制造业<0.7即异常
    if fs["total_sales"] > 0 and fs["total_purchases"] > 0:
        pur_sale_ratio = fs["total_purchases"] / fs["total_sales"]
        if pur_sale_ratio > (1.0 / pur_sale_low) if pur_sale_low > 0 else pur_sale_ratio > 1.5:
            ctx.add_flag("red", "购销严重倒挂", 
                         f"进项{fs['total_purchases']:,.0f}远超销项{fs['total_sales']:,.0f}(比{pur_sale_ratio:.1f})", "初查")
    
    # 毛利率异常：低于行业下限或高于行业上限
    gm = fs["gross_margin_pct"]
    if gm < gm_low and fs["total_sales"] > 0:
        ctx.add_flag("red", "毛利为负", f"毛利率{gm:.1f}%（行业下限{gm_low}%）→进价高于售价或隐匿收入", "初查")
    elif gm > gm_high and fs["total_sales"] > 1000000:
        ctx.add_flag("yellow", "毛利率异常高", f"毛利率{gm:.1f}%（行业上限{gm_high}%）→可能关联交易定价不公允", "初查")
    
    # 银行业务量异常
    if fs["bank_tx_count"] == 0 and fs["total_sales"] > 0:
        ctx.add_flag("red", "缺少银行流水", "有销售但无银行流水记录→资金流无法验证", "初查")
    
    # ═══════════════════════════════════════════
    # 黄灯：需关注但非紧急
    # ═══════════════════════════════════════════
    
    # 有销无进（服务/劳务除外）
    if fs["sale_count"] > 0 and fs["pur_count"] == 0 and cp["biz_model"] not in ("服务/劳务",):
        ctx.add_flag("yellow", "无进项发票", f"{fs['sale_count']}张销项但0张进项", "初查")
    
    # 工资为0但销项很大
    if fs["total_sales"] > 5000000 and fs["salary_count"] == 0:
        ctx.add_flag("yellow", "无工资记录", f"销项{fs['total_sales']:,.0f}但无工资→可能虚开或隐匿人员", "初查")
    
    # 加工信号
    if ctx.has_processing_fee:
        ctx.add_flag("yellow", "存在加工费", "进项中有加工费发票→可能为制造业", "初查")
        if ctx.biz_cost_classification:
            bcc = ctx.biz_cost_classification
            core_count = len(bcc["core_cost_invs"])
            if core_count > 0 and cp["biz_model"] == "制造业":
                ctx.add_flag("yellow", "制造业加工链条待验证",
                            f"核心成本{core_count}张+加工费→需BOM表验证", "初查")
    
    # ═══════════════════════════════════════════
    # 增强检测：发票行为模式
    # ═══════════════════════════════════════════
    if pur_invs:
        _detect_invoice_pattern_signals(ctx, pur_invs, "进项")
    if sal_invs:
        _detect_invoice_pattern_signals(ctx, sal_invs, "销项")
    
    # 进项发票连号检测（连续号码→虚假交易）
    if pur_invs and len(pur_invs) >= 3:
        _detect_consecutive_invoices(ctx, pur_invs, "进项")
    if sal_invs and len(sal_invs) >= 3:
        _detect_consecutive_invoices(ctx, sal_invs, "销项")
    
    # 季度末集中开票检测
    if sal_invs and len(sal_invs) >= 5:
        _detect_quarter_end_spike(ctx, sal_invs, "销项")
    if pur_invs and len(pur_invs) >= 5:
        _detect_quarter_end_spike(ctx, pur_invs, "进项")
    
    # 供应商集中度
    if pur_invs and len(pur_invs) >= 3:
        _detect_supplier_concentration(ctx, pur_invs)
    
    # 客户集中度
    if sal_invs and len(sal_invs) >= 3:
        _detect_customer_concentration(ctx, sal_invs)
    
    # 银行流水异常模式
    if bank_txs and len(bank_txs) >= 5:
        _detect_bank_pattern_signals(ctx, bank_txs)
    
    # 趋势/升频信号检测
    _detect_trend_signals(ctx, bank_txs, invoices)
    
    # ═══════════════════════════════════════════
    # 绿灯：正常信号
    # ═══════════════════════════════════════════
    if ctx.biz_cost_classification:
        bcc = ctx.biz_cost_classification
        minor_count = len(bcc["minor_expense_invs"])
        if minor_count > 0:
            ctx.add_flag("green", "存在日常费用报销",
                        f"{minor_count}张日常报销（餐饮住宿等）——正常经营信号", "初查")
        # 进销品名重合度高 → 贸易模式正常
        if cp["has_trading"]:
            ctx.add_flag("green", "贸易模式进销品名匹配", "进销品名重合度高→贸易链条正常", "初查")


def _detect_invoice_pattern_signals(ctx, invoices, direction):
    """发票行为模式检测：金额分布、整十整百比例"""
    if not invoices or len(invoices) < 5:
        return
    
    amounts = []
    for inv in invoices:
        a = float(inv.get("amount", inv.get("total", 0)) or 0)
        if a > 0:
            amounts.append(a)
    
    if len(amounts) < 5:
        return
    
    # 金额整十整百比例（人为编造发票的典型特征）
    round_count = sum(1 for a in amounts if a >= 1000 and (a % 1000 == 0 or a % 10000 == 0))
    round_pct = round_count / len(amounts) * 100
    if round_pct > 50 and len(amounts) >= 5:
        ctx.add_flag("yellow", f"{direction}金额整十整百比例高",
                    f"{round_count}/{len(amounts)}张（{round_pct:.0f}%）金额为整数→可能人为编造", "初查")
    
    # 单张发票金额过于均匀（标准差/均值 < 0.2 → 每张金额差不多）
    if len(amounts) >= 5:
        avg = sum(amounts) / len(amounts)
        variance = sum((a - avg) ** 2 for a in amounts) / len(amounts)
        std = variance ** 0.5
        if avg > 1000 and std / avg < 0.3:
            ctx.add_flag("yellow", f"{direction}金额分布异常均匀",
                        f"标准差/均值={std/avg:.2f}，每张金额接近→可能按计划编造而非真实交易", "初查")


def _detect_consecutive_invoices(ctx, invoices, direction):
    """进销项发票连号检测"""
    import re
    
    inv_nos = []
    for inv in invoices:
        no = str(inv.get("inv_no", inv.get("发票号码", ""))).strip()
        if no:
            # 提取数字部分
            nums = re.findall(r'\d+', no)
            if nums:
                inv_nos.append((no, int(nums[-1])))
    
    if len(inv_nos) < 3:
        return
    
    # 按数字排序，检测连续号码段
    inv_nos.sort(key=lambda x: x[1])
    consecutive_groups = []
    current_group = [inv_nos[0]]
    
    for i in range(1, len(inv_nos)):
        if inv_nos[i][1] - inv_nos[i-1][1] <= 1:
            current_group.append(inv_nos[i])
        else:
            if len(current_group) >= 3:
                consecutive_groups.append(current_group)
            current_group = [inv_nos[i]]
    
    if len(current_group) >= 3:
        consecutive_groups.append(current_group)
    
    if consecutive_groups:
        max_group = max(consecutive_groups, key=len)
        ctx.add_flag("yellow", f"{direction}发票连号",
                    f"发现{len(consecutive_groups)}组连号发票，最长连续{len(max_group)}张"
                    f"（{max_group[0][0]}~{max_group[-1][0]}）→可能集中开票或虚假交易", "初查")


def _detect_quarter_end_spike(ctx, invoices, direction):
    """季度末集中开票检测"""
    from collections import Counter
    
    month_counts = Counter()
    for inv in invoices:
        date_str = str(inv.get("date", inv.get("inv_date", inv.get("开票日期", "")))).strip()
        if date_str and len(date_str) >= 7:
            month = date_str[:7]  # YYYY-MM
            month_counts[month] += 1
    
    if len(month_counts) < 3:
        return
    
    # 季度末月份：3, 6, 9, 12
    quarter_end_months = set()
    for m in month_counts:
        if m.endswith('-03') or m.endswith('-06') or m.endswith('-09') or m.endswith('-12'):
            quarter_end_months.add(m)
    
    if not quarter_end_months:
        return
    
    qe_count = sum(month_counts[m] for m in quarter_end_months)
    total_count = sum(month_counts.values())
    qe_pct = qe_count / total_count * 100
    
    if qe_pct > 60 and total_count >= 10:
        ctx.add_flag("yellow", f"{direction}季度末集中开票",
                    f"季度末月份({','.join(sorted(quarter_end_months))})开票量占总量的{qe_pct:.0f}%"
                    f"→可能突击开票或人为调节收入", "初查")


def _detect_supplier_concentration(ctx, pur_invs):
    """供应商集中度检测（行业自适应阈值）"""
    from collections import defaultdict
    supplier_amounts = defaultdict(float)
    for inv in pur_invs:
        seller = str(inv.get("seller", inv.get("销方名称", ""))).strip()
        amount = float(inv.get("amount", inv.get("total", 0)) or 0)
        if seller and amount > 0:
            supplier_amounts[seller] += amount
    
    if len(supplier_amounts) < 2:
        return
    
    total = sum(supplier_amounts.values())
    top3 = sorted(supplier_amounts.values(), reverse=True)[:3]
    top3_pct = sum(top3) / total * 100
    
    ctx.supplier_concentration = top3_pct
    
    # 行业阈值：制造业60%，贸易50%
    ip = ctx.industry_profile or {}
    warn_threshold = ip.get("benchmarks", {}).get("supplier_concentration_warn", 80)
    
    if top3_pct > warn_threshold and len(supplier_amounts) >= 3:
        ctx.add_flag("yellow", "供应商高度集中",
                    f"前3大供应商占总采购额{top3_pct:.0f}%（行业预警{warn_threshold}%）→可能存在关联交易或供应商依赖风险", "初查")


def _detect_customer_concentration(ctx, sal_invs):
    """客户集中度检测（行业自适应阈值）"""
    from collections import defaultdict
    customer_amounts = defaultdict(float)
    for inv in sal_invs:
        buyer = str(inv.get("buyer", inv.get("购方名称", ""))).strip()
        amount = float(inv.get("amount", inv.get("total", 0)) or 0)
        if buyer and amount > 0:
            customer_amounts[buyer] += amount
    
    if len(customer_amounts) < 2:
        return
    
    total = sum(customer_amounts.values())
    top3 = sorted(customer_amounts.values(), reverse=True)[:3]
    top3_pct = sum(top3) / total * 100
    
    ctx.customer_concentration = top3_pct
    
    # 行业阈值：贸易50%，建筑70%
    ip = ctx.industry_profile or {}
    warn_threshold = ip.get("benchmarks", {}).get("customer_concentration_warn", 80)
    
    if top3_pct > warn_threshold and len(customer_amounts) >= 3:
        ctx.add_flag("yellow", "客户高度集中",
                    f"前3大客户占总销售额{top3_pct:.0f}%（行业预警{warn_threshold}%）→可能存在关联交易或客户依赖风险", "初查")


def _detect_bank_pattern_signals(ctx, bank_txs):
    """银行流水异常模式检测"""
    # 个人付款方比例
    personal_count = 0
    total_count = 0
    for tx in bank_txs:
        cp = str(tx.get("counterparty", tx.get("对方户名", ""))).strip()
        if not cp:
            continue
        total_count += 1
        # 判断个人：长度短、无"公司/有限/企业"等后缀
        if len(cp) <= 4 and not any(k in cp for k in ["公司", "有限", "企业", "厂", "行"]):
            personal_count += 1
    
    if total_count >= 10:
        personal_pct = personal_count / total_count * 100
        if personal_pct > 30:
            ctx.has_personal_payments = True
            ctx.add_flag("yellow", "个人交易占比过高",
                        f"{personal_count}/{total_count}笔（{personal_pct:.0f}%）付款方为个人"
                        f"→可能私户收款或未申报经营收入", "初查")


def _detect_trend_signals(ctx, bank_txs, invoices):
    """趋势/升频信号检测 —— 从时间序列中发现动态异常。
    
    检测维度：
    1. 月度金额波动：标准差/均值>0.5 → 收入/支出剧烈波动
    2. 月度交易频率趋势：逐月递增→经营异常扩张或人为编造
    3. 周末/非工作日交易占比：正常企业工作日为主
    4. 单日大额异常：单日金额超过日均3倍的天数
    """
    from collections import defaultdict
    from datetime import datetime
    
    # ── 1. 月度金额波动 ──
    if invoices and len(invoices) >= 10:
        month_amounts = defaultdict(float)
        month_counts = defaultdict(int)
        for inv in invoices:
            d = str(inv.get("date", inv.get("inv_date", ""))).strip()
            if len(d) >= 7:
                month = d[:7]
                month_amounts[month] += float(inv.get("amount", inv.get("total", 0)) or 0)
                month_counts[month] += 1
        
        if len(month_amounts) >= 3:
            amounts = list(month_amounts.values())
            avg_amt = sum(amounts) / len(amounts)
            if avg_amt > 0:
                variance = sum((a - avg_amt) ** 2 for a in amounts) / len(amounts)
                cv = (variance ** 0.5) / avg_amt
                if cv > 0.8:
                    ctx.add_flag("yellow", "月度开票金额剧烈波动",
                                f"月度变异系数{cv:.2f}（>0.8表明金额波动异常剧烈）", "初查")
            
            months_sorted = sorted(month_counts.keys())
            if len(months_sorted) >= 4:
                counts = [month_counts[m] for m in months_sorted]
                mid = len(counts) // 2
                first_half_avg = sum(counts[:mid]) / mid
                second_half_avg = sum(counts[mid:]) / (len(counts) - mid)
                if first_half_avg > 0 and second_half_avg / first_half_avg > 2.0:
                    ctx.add_flag("yellow", "开票频率逐月攀升",
                                f"月均开票从前半段{first_half_avg:.0f}张升至后半段{second_half_avg:.0f}张", "初查")
    
    # ── 2. 非工作日交易 ──
    if bank_txs and len(bank_txs) >= 10:
        weekend_count = 0
        total_dated = 0
        for tx in bank_txs:
            d = str(tx.get("date", ""))[:10]
            if len(d) >= 10:
                try:
                    dt = datetime.strptime(d, "%Y-%m-%d")
                    total_dated += 1
                    if dt.weekday() >= 5:
                        weekend_count += 1
                except:
                    pass
        if total_dated >= 10:
            weekend_pct = weekend_count / total_dated * 100
            if weekend_pct > 25:
                ctx.add_flag("yellow", "非工作日交易占比异常",
                            f"{weekend_count}/{total_dated}笔（{weekend_pct:.0f}%）交易发生在周末", "初查")
    
    # ── 3. 单日大额频率 ──
    if bank_txs and len(bank_txs) >= 20:
        daily_amounts = defaultdict(float)
        for tx in bank_txs:
            d = str(tx.get("date", ""))[:10]
            amt = max(float(tx.get("debit", 0) or 0), float(tx.get("credit", 0) or 0))
            if d and amt > 0:
                daily_amounts[d] += amt
        if daily_amounts:
            avg_daily = sum(daily_amounts.values()) / len(daily_amounts)
            spike_days = sum(1 for a in daily_amounts.values() if a > avg_daily * 3)
            if spike_days >= 3 and len(daily_amounts) >= 10:
                ctx.add_flag("yellow", "存在异常大额交易日",
                            f"{spike_days}天单日金额超日均{avg_daily:,.0f}元的3倍", "初查")


def _assess_data_quality(ctx, docs, file_results, bank_txs, invoices, salaries):
    """资料质量评估——影响后续分析的置信度"""
    score = 100
    
    # 基本资料检查
    has_bank = len(bank_txs) > 0
    has_invoices = len(invoices) > 0
    has_salary = len(salaries) > 0
    
    if not has_bank:
        score -= 30
        ctx.missing_critical_docs.append("银行流水")
    if not has_invoices:
        score -= 30
        ctx.missing_critical_docs.append("发票数据")
    if not has_salary:
        score -= 15
        ctx.missing_critical_docs.append("工资表")
    
    # 解析质量
    unknown_count = sum(1 for fr in file_results if fr["type"] == "unknown")
    if unknown_count > 0:
        score -= unknown_count * 5
    
    # 数据量级
    if has_bank and len(bank_txs) < 10:
        score -= 10
        ctx.add_flag("yellow", "银行流水数据量少", f"仅{len(bank_txs)}笔", "资料质量")
    
    if has_invoices and len(invoices) < 5:
        score -= 10
        ctx.add_flag("yellow", "发票数据量少", f"仅{len(invoices)}张", "资料质量")
    
    ctx.data_quality_score = max(0, min(100, score))


# ═══════════════════════════════════════════════════════════
# Phase 2 — 定向深挖（Signal-Driven Deep Dive）
#
# 设计理念：不是29域全量盲跑，而是基于 Phase 1 的信号，
# 像人类稽查员一样定向选择深挖方向和深度。
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

# ├─ 信号→域映射表
# │  每个信号定义了应深挖的域及深度



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
    _detect_triage_signals(ctx, pur_invs, sal_invs, bank_txs)
    
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
    """从数据中推断企业行业和经营模式"""
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
    
    # 加工信号
    has_processing = any("加工" in g for g in pur_goods_set)
    ctx.has_processing_fee = has_processing
    
    # 品名重合度
    if pur_goods_set and sal_goods_set:
        overlap = len(pur_goods_set & sal_goods_set)
        total_unique = len(pur_goods_set | sal_goods_set)
        overlap_ratio = overlap / max(total_unique, 1)
    else:
        overlap_ratio = 0
    
    # 模式判断
    if has_processing and overlap_ratio < 0.5:
        cp["biz_model"] = "制造业"
        cp["has_manufacturing"] = True
    elif overlap_ratio >= 0.5 and pur_goods_set and sal_goods_set:
        cp["biz_model"] = "贸易"
        cp["has_trading"] = True
    elif not pur_invs and sal_invs:
        cp["biz_model"] = "服务/劳务"
    else:
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


def _infer_industry_from_goods(ctx, pur_goods, sal_goods):
    """从发票品名推断行业——全行业自适应，不硬编码任何行业关键词
    
    方法：利用中国金税发票的税收分类编码前缀（*XX*格式）
    例如：*纺织产品*棉布 → 行业=纺织产品
    无分类编码时用"综合"兜底
    """
    cp = ctx.company_profile
    
    # 从所有品名中提取税收分类编码（*之间的文字）
    import re
    all_goods_list = list(pur_goods | sal_goods)
    cat_counts = {}
    
    for goods in all_goods_list:
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


def _detect_triage_signals(ctx, pur_invs=None, sal_invs=None, bank_txs=None):
    """初查阶段信号检测——像老稽查员翻一遍资料就能嗅出异常"""
    fs = ctx.financial_snapshot
    cp = ctx.company_profile
    
    # ═══════════════════════════════════════════
    # 红灯：基础数据严重异常（立即深挖）
    # ═══════════════════════════════════════════
    
    # 购销倒挂（进项>销项1.5倍）：可能虚增进项或隐匿收入
    if fs["total_purchases"] > fs["total_sales"] * 1.5 and fs["total_sales"] > 0:
        ctx.add_flag("red", "购销严重倒挂", 
                     f"进项{fs['total_purchases']:,.0f}远超销项{fs['total_sales']:,.0f}", "初查")
    
    # 毛利率异常（<0%或>80%）
    gm = fs["gross_margin_pct"]
    if gm < 0:
        ctx.add_flag("red", "毛利为负", f"毛利率{gm:.1f}%，进价高于售价或隐匿收入", "初查")
    elif gm > 80 and fs["total_sales"] > 1000000:
        ctx.add_flag("yellow", "毛利率异常高", f"毛利率{gm:.1f}%，可能关联交易定价不公允", "初查")
    
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
    """供应商集中度检测"""
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
    
    if top3_pct > 80 and len(supplier_amounts) >= 3:
        ctx.add_flag("yellow", "供应商高度集中",
                    f"前3大供应商占总采购额{top3_pct:.0f}%→可能存在关联交易或供应商依赖风险", "初查")


def _detect_customer_concentration(ctx, sal_invs):
    """客户集中度检测"""
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
    
    if top3_pct > 80 and len(customer_amounts) >= 3:
        ctx.add_flag("yellow", "客户高度集中",
                    f"前3大客户占总销售额{top3_pct:.0f}%→可能存在关联交易或客户依赖风险", "初查")


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



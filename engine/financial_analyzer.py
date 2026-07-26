"""
财务报表税务合规分析引擎

四层分析框架：
  Layer A: 表内勾稽 → 资产负债表自身平衡 + 利润表结构合理性
  Layer B: 跨表勾稽 → 资产负债表↔利润表↔现金流量表三表联动验证
  Layer C: 指标趋势 → 流动比/速动比/负债率/毛利率/净利率/周转率 时序异常检测
  Layer D: 税务合规 → 收入确认/成本结转/费用列支/资产处置/关联交易 税务视角专项分析
  Layer E: 往来款项税务合规 → 预收账款隐匿收入/预付账款套取资金/其他应收款股东占款/其他应付款异常
"""

import json, os, re
from datetime import datetime
from collections import defaultdict


# ═══════════════ 税务合规专项分析指标 ═══════════════
TAX_AUDIT_INDICATORS = {
    # ── 收入端税务合规 ──
    "revenue_declaration_ratio": {
        "name": "申报收入vs发票收入比",
        "formula": "申报收入 / 销项发票金额",
        "normal": (0.95, 1.05),  # 正常区间
        "risk_high": "<0.9",      # 申报收入远低于开票收入 → 可能隐匿开票外的收入
        "risk_medium": ">1.1",    # 申报收入高于开票 → 可能虚增收入
        "tax_impact": "少申报收入→少缴增值税/企业所得税",
    },
    "unbilled_revenue_ratio": {
        "name": "未开票收入占比",
        "formula": "(申报收入 - 销项发票金额) / 申报收入",
        "normal": (0, 0.15),
        "risk_high": ">0.3",
        "tax_impact": "未开票收入占比过高→需核实收入完整性/是否存在隐匿开票外收入",
    },
    
    # ── 成本端税务合规 ──
    "cost_income_ratio": {
        "name": "成本收入比",
        "formula": "主营业务成本 / 主营业务收入",
        "normal_by_industry": True,  # 行业自适应
        "risk_high": "偏离行业基准>20%",
        "tax_impact": "成本率异常→可能虚列成本/多转成本→少缴企业所得税",
    },
    "purchase_invoice_match": {
        "name": "进项发票vs成本匹配度",
        "formula": "进项发票金额 / 主营业务成本",
        "normal": (0.8, 1.0),
        "risk_high": "<0.6",  # 进项发票远低于成本 → 可能无票列支/白条入账
        "tax_impact": "无票成本→不得税前扣除→补缴企业所得税+滞纳金",
    },
    
    # ── 费用端税务合规 ──
    "expense_revenue_ratio": {
        "name": "期间费用率",
        "formula": "(销售费用+管理费用+财务费用) / 主营业务收入",
        "normal_by_industry": True,
        "risk_high": "偏离行业基准>50%",
        "tax_impact": "费用率异常→可能多列费用/混淆资本性支出与收益性支出",
    },
    "travel_entertainment_ratio": {
        "name": "业务招待费占比",
        "formula": "业务招待费 / 主营业务收入",
        "normal": (0, 0.005),  # 一般不超过0.5%
        "risk_high": ">0.008",
        "tax_impact": "超标部分不得税前扣除→纳税调增",
    },
    
    # ── 资产负债税务合规 ──
    "receivable_turnover": {
        "name": "应收账款周转率",
        "formula": "主营业务收入 / 平均应收账款",
        "normal": (4, 12),
        "risk_medium": "<3",  # 周转过慢
        "risk_high": ">20",   # 周转过快异常
        "tax_impact": "应收异常→可能虚增收入/虚构应收账款/关联交易非公允定价",
    },
    "inventory_turnover": {
        "name": "存货周转率",
        "formula": "主营业务成本 / 平均存货",
        "normal": (3, 12),
        "risk_medium": "<2",
        "risk_high": ">20",
        "tax_impact": "存货异常→可能多转成本(少计存货)/隐藏存货(账外资产)",
    },
    "asset_liability_ratio": {
        "name": "资产负债率",
        "formula": "总负债 / 总资产",
        "normal": (0.3, 0.7),
        "risk_medium": ">0.8",
        "risk_high": ">1.0",   # 资不抵债
        "tax_impact": "高负债→可能存在隐性负债/关联方借款利息扣除问题",
    },
    
    # ── 现金流税务合规 ──
    "operating_cashflow_quality": {
        "name": "经营现金流质量",
        "formula": "经营活动现金净流量 / 净利润",
        "normal": (0.8, 2.0),
        "risk_high": "<0.3",  # 有利润无现金
        "tax_impact": "利润与现金流严重背离→可能虚增收入/虚构利润→粉饰报表",
    },
    "cash_sales_match": {
        "name": "销售收现率",
        "formula": "销售商品收到的现金 / 主营业务收入",
        "normal": (0.9, 1.15),  # 含增值税
        "risk_medium": "<0.8",  # 赊销过多
        "risk_high": "<0.5",    # 严重不匹配
        "tax_impact": "收现率过低→应收账款质量存疑/可能虚开发票",
    },
    
    # ── 所有者权益税务合规 ──
    "owner_equity_change": {
        "name": "所有者权益异常变动",
        "formula": "本期所有者权益变动 / 期初所有者权益",
        "normal": (-0.3, 0.5),
        "risk_medium": ">1.0",   # 翻倍增长
        "risk_high": "<-0.5",    # 大幅减少
        "tax_impact": "权益异常变动→可能存在未入账的利润分配/资本公积转增未缴税",
    },
    
    # ── 跨年趋势税务合规 ──
    "revenue_growth_surge": {
        "name": "收入暴增检测",
        "formula": "本期收入 / 上期收入 - 1",
        "normal": (-0.2, 0.3),
        "risk_medium": ">0.5",
        "risk_high": ">1.0",
        "tax_impact": "收入暴增→需核实是否真实/是否存在一次性虚开冲业绩",
    },
    "cost_surge_detect": {
        "name": "成本暴增检测",
        "formula": "本期成本 / 上期成本 - 1",
        "normal": (-0.2, 0.3),
        "risk_medium": ">0.4 且收入增幅不到一半",
        "risk_high": ">0.8",
        "tax_impact": "成本暴增→可能突击列支/人为调节利润→少缴企业所得税",
    },
}


def analyze_financial_statements(balance_sheet, income_stmt, cash_flow, vouchers, sal_invs, pur_invs, ctx):
    """
    财务报表税务合规分析主入口
    
    Args:
        balance_sheet: 资产负债表数据 (dict with 资产/负债/权益余额)
        income_stmt: 利润表数据 (dict with 收入/成本/费用/利润)
        cash_flow: 现金流量表数据 (dict with 经营/投资/筹资现金流)
        vouchers: 记账凭证列表
        sal_invs: 销项发票列表
        pur_invs: 进项发票列表
        ctx: AuditContext
    
    Returns: findings list
    """
    findings = []
    biz_model = ctx.company_profile.get("biz_model", "") if ctx else ""
    
    if not balance_sheet and not income_stmt:
        return findings
    
    # ═══ Layer A+B+C+D 逐层分析 ═══
    findings.extend(_check_balance_sheet_balance(balance_sheet))
    findings.extend(_check_cross_statement(balance_sheet, income_stmt, cash_flow))
    findings.extend(_check_tax_indicators(balance_sheet, income_stmt, cash_flow, sal_invs, pur_invs, biz_model))
    findings.extend(_check_voucher_statement_gap(vouchers, income_stmt, sal_invs))
    findings.extend(analyze_balance_sheet_items(balance_sheet, income_stmt, vouchers, ctx))
    
    return findings


def _check_balance_sheet_balance(bs):
    """Layer A: 资产负债表自身平衡检查"""
    findings = []
    if not bs:
        return findings
    
    total_assets = bs.get("total_assets", 0) or 0
    total_liabilities = bs.get("total_liabilities", 0) or 0
    total_equity = bs.get("total_equity", 0) or 0
    
    if total_assets > 0 and abs(total_assets - total_liabilities - total_equity) > max(total_assets * 0.01, 1000):
        gap = total_assets - total_liabilities - total_equity
        findings.append({
            "type": "资产负债表不平衡",
            "level": "高风险",
            "score": 9,
            "detail": f"资产{total_assets:,.0f} ≠ 负债{total_liabilities:,.0f} + 权益{total_equity:,.0f}，差额{gap:,.0f}元",
            "tax_impact": "报表基础数据错误→所有财务指标分析不可信→无法作为税务合规依据",
            "law_ref": "征管法第21720条",
        })
    
    return findings


def _check_cross_statement(bs, income, cf):
    """Layer B: 跨表勾稽验证"""
    findings = []
    
    # 利润表净利润 vs 资产负债表未分配利润变动
    net_profit = income.get("net_profit", 0) or 0 if income else 0
    retained_change = bs.get("retained_earnings_change", bs.get("undistributed_profit_change", 0)) or 0 if bs else 0
    
    if net_profit > 0 and retained_change > 0:
        expected_change = net_profit * 0.8  # 假设提取20%盈余公积等
        if abs(retained_change - expected_change) > net_profit * 0.3:
            findings.append({
                "type": "利润表与资产负债表勾稽不符",
                "level": "中风险",
                "score": 7,
                "detail": f"净利润{net_profit:,.0f}元，未分配利润变动{retained_change:,.0f}元，差额过大",
                "tax_impact": "可能未正确结转利润→需核实利润分配账务处理→影响企业所得税汇算",
                "law_ref": "企业会计准则第30号-财务报表列报",
            })
    
    # 现金流量表经营现金流 vs 利润表收入+应收账款变动
    if cf:
        operating_cf = cf.get("operating_cash_inflow", 0) or 0
        revenue = income.get("revenue", income.get("total_revenue", 0)) or 0 if income else 0
        if operating_cf > 0 and revenue > 0:
            ratio = operating_cf / revenue
            if ratio < 0.5:
                findings.append({
                    "type": "经营收现与收入严重不匹配",
                    "level": "中风险",
                    "score": 7,
                    "detail": f"经营现金流入{operating_cf:,.0f}仅为收入{revenue:,.0f}的{ratio:.0%}",
                    "tax_impact": "大量赊销→应收账款质量存疑→可能虚开发票/虚构收入",
                    "law_ref": "征管法第31720条",
                })
    
    return findings


def _check_tax_indicators(bs, income, cf, sal_invs, pur_invs, biz_model):
    """Layer C+D: 税务合规指标分析"""
    findings = []
    
    if not income:
        return findings
    
    revenue = income.get("revenue", income.get("total_revenue", 0)) or 0
    cost = income.get("cost", income.get("total_cost", 0)) or 0
    net_profit = income.get("net_profit", 0) or 0
    
    if revenue <= 0:
        return findings
    
    # ── 成本收入比 ──
    if cost > 0:
        cost_ratio = cost / revenue
        if biz_model == "服务" and cost_ratio > 0.7:
            findings.append({
                "type": "成本率偏高(服务型企业)",
                "level": "中风险", "score": 6,
                "detail": f"成本率{cost_ratio:.0%}，服务型企业通常成本率<50%",
                "tax_impact": "可能虚列成本/混淆费用资本化→少缴企业所得税",
            })
        elif biz_model == "贸易" and (cost_ratio < 0.5 or cost_ratio > 0.95):
            findings.append({
                "type": "成本率异常(贸易型企业)",
                "level": "中风险", "score": 6,
                "detail": f"成本率{cost_ratio:.0%}，贸易企业通常50%-95%",
                "tax_impact": "异常成本率→需核实进销真实性",
            })
    
    # ── 期间费用率 ──
    selling = income.get("selling_expense", 0) or 0
    admin = income.get("admin_expense", 0) or 0
    finance = income.get("finance_expense", 0) or 0
    total_expense = selling + admin + finance
    
    if total_expense > 0:
        expense_ratio = total_expense / revenue
        if biz_model == "服务" and expense_ratio > 0.5:
            findings.append({
                "type": "期间费用率偏高",
                "level": "中风险", "score": 6,
                "detail": f"期间费用{total_expense:,.0f}占收入{expense_ratio:.0%}",
                "tax_impact": "可能多列费用→需逐项核实费用发票合规性",
            })
    
    # ── 业务招待费 ──
    entertainment = income.get("entertainment_expense", 0) or 0
    if entertainment > revenue * 0.005:
        excess = entertainment - revenue * 0.005
        findings.append({
            "type": "业务招待费超标",
            "level": "中风险", "score": 6,
            "detail": f"招待费{entertainment:,.0f}元，超标{excess:,.0f}元（限额为收入0.5%）",
            "tax_impact": f"超标{excess:,.0f}元不得税前扣除→应纳税调增→补缴企业所得税约{excess*0.25:,.0f}元",
            "law_ref": "企业所得税法实施条例第41720条",
        })
    
    # ── 发票vs报表对比 ──
    if sal_invs:
        sal_total = sum(float(i.get("amount", 0) or 0) for i in sal_invs)
        if sal_total > 0 and revenue > 0:
            ratio = sal_total / revenue
            if ratio < 0.85:
                findings.append({
                    "type": "开票收入低于报表收入",
                    "level": "中风险", "score": 7,
                    "detail": f"开票收入{sal_total:,.0f}仅为报表收入{revenue:,.0f}的{ratio:.0%}",
                    "tax_impact": "存在大量未开票收入→需核实是否全部申报纳税",
                })
            elif ratio > 1.15:
                findings.append({
                    "type": "开票收入高于报表收入",
                    "level": "中风险", "score": 7,
                    "detail": f"开票收入{sal_total:,.0f}超出报表收入{revenue:,.0f}的{ratio:.0%}",
                    "tax_impact": "开票多于申报→可能虚开发票/提前开票确认收入",
                })
    
    if pur_invs:
        pur_total = sum(float(i.get("amount", 0) or 0) for i in pur_invs)
        if pur_total > 0 and cost > 0:
            ratio = pur_total / cost
            if ratio < 0.6:
                findings.append({
                    "type": "进项发票远低于报表成本",
                    "level": "高风险", "score": 8,
                    "detail": f"进项发票{pur_total:,.0f}仅为报表成本{cost:,.0f}的{ratio:.0%}",
                    "tax_impact": "大量无票成本→不得税前扣除→可能虚构成本→补缴企业所得税",
                    "law_ref": "企业所得税法第1720条",
                })
    
    # ── 资产负债率 ──
    if bs:
        total_assets = bs.get("total_assets", 0) or 0
        total_liabilities = bs.get("total_liabilities", 0) or 0
        if total_assets > 0:
            al_ratio = total_liabilities / total_assets
            if al_ratio > 0.9:
                findings.append({
                    "type": "资产负债率过高",
                    "level": "中风险", "score": 6,
                    "detail": f"资产负债率{al_ratio:.0%}，接近资不抵债",
                    "tax_impact": "高负债企业→可能存在隐性债务/关联方借款→利息扣除需核实资本弱化",
                    "law_ref": "企业所得税法第41720条(资本弱化)",
                })
    
    # ── 收入暴增 ──
    prev_revenue = income.get("prev_revenue", 0) or 0
    if prev_revenue > 0:
        growth = (revenue - prev_revenue) / prev_revenue
        if growth > 1.0:
            findings.append({
                "type": "收入暴增异常",
                "level": "中风险", "score": 6,
                "detail": f"收入从{prev_revenue:,.0f}增至{revenue:,.0f}(增长{growth:.0%})",
                "tax_impact": "收入翻倍→需核实是否真实经营/是否存在虚开冲业绩→可能涉及虚开发票",
            })
    
    # ── 利润现金流背离 ──
    if cf and net_profit > 0:
        operating_ncf = cf.get("operating_net_cf", cf.get("operating_cash_net", 0)) or 0
        if operating_ncf < net_profit * 0.3:
            findings.append({
                "type": "有利润无现金流",
                "level": "高风险", "score": 8,
                "detail": f"净利润{net_profit:,.0f}元，经营净现金流仅{operating_ncf:,.0f}元({operating_ncf/net_profit:.0%})",
                "tax_impact": "利润与现金流严重背离→可能存在虚增收入/虚构利润→财务造假嫌疑",
                "law_ref": "征管法第61720条(偷税)",
            })
    
    return findings


def _check_voucher_statement_gap(vouchers, income_stmt, sal_invs):
    """凭证与报表差异分析"""
    findings = []
    if not vouchers:
        return findings
    
    # 凭证中的主营业务收入合计 vs 报表收入
    voucher_revenue = sum(
        float(v.get("credit", 0) or 0) 
        for v in vouchers 
        if "主营业务收入" in str(v.get("account_name", v.get("科目", "")))
    )
    
    if income_stmt and voucher_revenue > 0:
        report_revenue = income_stmt.get("revenue", income_stmt.get("total_revenue", 0)) or 0
        if report_revenue > 0:
            gap = abs(voucher_revenue - report_revenue) / report_revenue
            if gap > 0.05:
                findings.append({
                    "type": "凭证收入与报表收入不一致",
                    "level": "高风险", "score": 9,
                    "detail": f"凭证主营收入{voucher_revenue:,.0f} vs 报表收入{report_revenue:,.0f}(偏差{gap:.0%})",
                    "tax_impact": "账表不一致→可能存在账外账/两套账→严重税务风险",
                    "law_ref": "征管法第61720条",
                })
    
    return findings


# ═══════════════ Layer E: 往来款项深度税务合规 ═══════════════
def analyze_balance_sheet_items(bs, income, vouchers, ctx):
    """资产负债表关键科目税务合规：预收/预付/其他应收(个人)/存货/应收/长收长付"""
    findings = []
    if not bs:
        return findings
    
    revenue = income.get("revenue", income.get("total_revenue", 0)) or 0 if income else 0
    
    # -- 预收账款 --
    adv_recv = bs.get("advance_receipts", bs.get("预收账款", 0)) or 0
    if adv_recv > 0 and revenue > 0 and adv_recv / revenue > 0.3:
        findings.append({"type":"预收账款占比过高","level":"高风险","score":9,
            "detail":f"预收账款{adv_recv:,.0f}元，占收入{adv_recv/revenue:.0%}",
            "tax_impact":"可能货物已发出但未确认收入→延迟纳税/隐匿收入→少缴增值税和企业所得税",
            "law_ref":"中华人民共和国增值税法第11720条；征管法第61720条",
            "suggestion":f"逐笔核实预收账款对应的发货记录，已发货未开票的应确认收入补税约{adv_recv*0.13:,.0f}元(增值税)"})
    
    # -- 预付账款 --
    adv_pay = bs.get("advance_payments", bs.get("预付账款", 0)) or 0
    if adv_pay > 0 and revenue > 0 and adv_pay / revenue > 0.2:
        findings.append({"type":"预付账款占比过高","level":"中风险","score":7,
            "detail":f"预付账款{adv_pay:,.0f}元，占收入{adv_pay/revenue:.0%}",
            "tax_impact":"大额预付→可能虚构采购套取资金/关联方占用",
            "law_ref":"征管法第31720条",
            "suggestion":f"逐笔核实预付账款合同/付款凭证/到货记录"})
    
    # -- 其他应收款-个人(股东/法人) --
    other_recv = bs.get("other_receivables", bs.get("其他应收款", 0)) or 0
    personal_recv = bs.get("personal_receivables", bs.get("其他应收款-个人", 0)) or 0
    
    if other_recv > 0:
        total_assets = max(bs.get("total_assets", 1), 1)
        if other_recv / total_assets > 0.15:
            findings.append({"type":"其他应收款占比过高","level":"高风险","score":8,
                "detail":f"其他应收款{other_recv:,.0f}元，占总资产{other_recv/total_assets:.0%}",
                "tax_impact":"可能隐藏股东/法人占款→视同分红涉及个人所得税",
                "law_ref":"财税[2003]158号；个人所得税法",
                "suggestion":"逐户列示其他应收款明细，特别关注股东/法人/关联方借款"})
        
        if personal_recv > 0:
            findings.append({"type":"其他应收款-个人借款(股东/法人风险)","level":"高风险","score":10,
                "detail":f"其他应收款中含个人款项{personal_recv:,.0f}元",
                "tax_impact":f"如为股东/法人借款年末未归还→视同分红→补缴个税{personal_recv*0.2:,.0f}元",
                "law_ref":"财税[2003]158号",
                "suggestion":f"立即核实{personal_recv:,.0f}元：是否为股东/法人、年末是否归还、用途是否与经营相关"})
    
    # -- 其他应付款 --
    other_pay = bs.get("other_payables", bs.get("其他应付款", 0)) or 0
    if other_pay > 0 and revenue > 0 and other_pay / revenue > 0.25:
        findings.append({"type":"其他应付款占比过高","level":"中风险","score":6,
            "detail":f"其他应付款{other_pay:,.0f}元",
            "tax_impact":"可能隐藏已实现收入/关联方资金池",
            "law_ref":"征管法第31720条"})
    
    # -- 存货 --
    inv = bs.get("inventory", bs.get("存货", 0)) or 0
    if inv > 0 and revenue > 0 and inv / revenue > 0.5:
        findings.append({"type":"存货占比过高","level":"中风险","score":6,
            "detail":f"存货{inv:,.0f}元，占收入{inv/revenue:.0%}",
            "tax_impact":"存货积压→可能少转成本虚增利润/账外销售",
            "law_ref":"征管法第31720条"})
    
    # -- 应收账款 --
    ar = bs.get("accounts_receivable", bs.get("应收账款", 0)) or 0
    if ar > 0 and revenue > 0 and ar / revenue > 0.5:
        findings.append({"type":"应收账款占比过高","level":"中风险","score":6,
            "detail":f"应收账款{ar:,.0f}元，占收入{ar/revenue:.0%}",
            "tax_impact":"大量赊销→可能存在虚开发票/虚构收入",
            "law_ref":"征管法第31720条"})
    
    # -- 应付职工薪酬 --
    sal_pay = bs.get("salary_payable", bs.get("应付职工薪酬", 0)) or 0
    if sal_pay > 0 and revenue > 0 and sal_pay / revenue > 0.1:
        findings.append({"type":"应付职工薪酬余额偏高","level":"中风险","score":6,
            "detail":f"应付职工薪酬{sal_pay:,.0f}元",
            "tax_impact":"已计提未发放→汇算清缴前未发放不得税前扣除",
            "law_ref":"企业所得税法实施条例第31720条"})
    
    return findings

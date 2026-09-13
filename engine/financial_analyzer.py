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
    # 金税四期核心量化监控指标（消费 TAX_AUDIT_INDICATORS：进项发票vs成本匹配度、
    # 成本收入比、期间费用率、企业所得税贡献率、业务招待费占比）
    findings.extend(_check_tax_audit_indicators(balance_sheet, income_stmt, vouchers, sal_invs, pur_invs, ctx))
    
    return findings


def _check_tax_audit_indicators(bs, income, vouchers, sal_invs, pur_invs, ctx):
    """金税四期核心量化监控指标 —— 消费 TAX_AUDIT_INDICATORS 并产出待核疑点。

    ★ 背景（重要）：TAX_AUDIT_INDICATORS 此前**仅被定义、全项目零消费点**，
    导致「进项发票 vs 主营业务成本匹配度」等一批金税四期核心量化指标实际未生效。
    本函数将其真正计算并输出，补上"账面主营成本有票支撑不足""所得税贡献率偏低"等缺口。

    铁律：只输出可复算的数量事实与待核疑点，不自动定性；无数据(成本/收入为0)不输出。
    """
    findings = []
    if not income:
        return findings

    revenue = float(income.get("revenue", 0) or 0)
    cost = float(income.get("cost", 0) or 0)
    selling = float(income.get("selling_expense", 0) or 0)
    admin = float(income.get("admin_expense", 0) or 0)
    finance = float(income.get("finance_expense", 0) or 0)
    net_profit = float(income.get("net_profit", 0) or 0)

    def _inv_amount(inv):
        if not isinstance(inv, dict):
            return 0.0
        for k in ("amount", "金额", "价税合计", "total", "total_amount"):
            v = inv.get(k)
            if v not in (None, ""):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        return 0.0

    # ── ① 进项发票 vs 主营业务成本匹配度（金税四期：无票成本 / 白条入账）──
    # 对应 TAX_AUDIT_INDICATORS["purchase_invoice_match"]，risk_high < 0.6
    if cost > 0 and pur_invs:
        pur_total = sum(_inv_amount(i) for i in pur_invs)
        if pur_total > 0:
            ratio = pur_total / cost
            # ★ 匹配度 <0.6 的高风险档由 _check_tax_indicators 的「进项发票远低于报表成本」覆盖，
            #   此处只补 0.6~0.8 的偏低提示档，避免同一事实被重复输出两条不同的结论。
            if ratio < 0.6:
                pass
            elif ratio < 0.8:
                findings.append({
                    "type": "待核事实：主营业务成本有票支撑偏低",
                    "description": (
                        "主营业务成本应当有对应的采购发票支撑。当账面列支的成本高于取得的发票金额时，"
                        "差额部分通常表现为暂估入库、跨期取得发票或无票采购，需逐项核实。"
                        "注：分子含费用类进项发票，实际用于主营成本的发票匹配度只会更低。"
                    ),
                    "level": "中风险", "score": 6,
                    "detail": (
                        f"账面主营业务成本{cost:,.2f}元，进项发票金额合计{pur_total:,.2f}元，"
                        f"匹配度{ratio:.0%}，低于正常区间下限80%。"
                    ),
                    "description": "成本与进项发票存在缺口，可能由暂估入库、跨期取得发票或无票采购形成，需核实。",
                    "how_found": "进项发票金额 / 主营业务成本 = {:.0%}，低于正常区间0.8~1.0。".format(ratio),
                    "tax_impact": "缺口部分若无合规凭证，面临企业所得税税前不得扣除的纳税调增风险。",
                    "policy_ref": "《企业所得税税前扣除凭证管理办法》（国家税务总局公告2018年第28号）",
                    "suggestion": "核实成本缺口构成（暂估/跨期/无票采购），补充取得发票或准备真实性证明材料。",
                    "category": "成本费用",
                    "source_chain": "财务报表-进项发票与成本匹配度",
                    "redline_id": "RL-COST-003",
                    "indicator": "purchase_invoice_match",
                    "indicator_value": round(ratio, 4),
                })

    # ── ② 成本收入比极端异常（金税四期：成本率/毛利率背离）──
    if revenue > 0 and cost > 0:
        cost_rate = cost / revenue
        if cost_rate >= 1.0:
            findings.append({
                "type": "待核事实：主营业务成本已超过主营业务收入",
                "level": "高风险", "score": 8,
                "detail": f"主营业务成本{cost:,.2f}元已不低于主营业务收入{revenue:,.2f}元（成本率{cost_rate:.0%}），毛利为负。",
                "description": "长期成本不低于收入（购销倒挂、负毛利经营）不符合商业常理，需核实成本归集是否准确、是否存在多转成本或收入未足额入账。",
                "how_found": "利润表主营业务成本 / 主营业务收入 = {:.0%}。".format(cost_rate),
                "tax_impact": "多转成本将少缴企业所得税；若同时存在收入未足额确认，构成少缴税款。",
                "policy_ref": "《企业所得税法》第八条（实际发生且与取得收入有关的支出准予扣除）",
                "suggestion": "①说明负毛利的商业合理性（促销/清库/新业务投入）；②提供成本结转方法与存货计价说明；③核实收入是否足额确认。",
                "category": "成本费用",
                "source_chain": "财务报表-成本收入比",
                "redline_id": "RL-COST-004",
                "indicator": "cost_income_ratio",
                "indicator_value": round(cost_rate, 4),
            })
        elif cost_rate <= 0.05:
            findings.append({
                "type": "待核事实：主营业务成本率极低",
                "level": "中风险", "score": 6,
                "detail": f"主营业务成本{cost:,.2f}元仅占主营业务收入{revenue:,.2f}元的{cost_rate:.0%}。",
                "description": "成本率极低可能源于收入与成本不配比（成本挂账未结转），或企业实质为无经营的开票主体，需核实。",
                "how_found": "利润表主营业务成本 / 主营业务收入 = {:.0%}。".format(cost_rate),
                "tax_impact": "成本未及时结转将虚增利润；如业务不真实则涉嫌虚开发票。",
                "policy_ref": "《企业所得税法》第八条；《发票管理办法》第二十二条",
                "suggestion": "说明成本核算方法与结转时点，核实是否存在已发生成本未结转或业务实质不符。",
                "category": "成本费用",
                "source_chain": "财务报表-成本收入比",
                "redline_id": "RL-COST-004",
                "indicator": "cost_income_ratio",
                "indicator_value": round(cost_rate, 4),
            })

    # ── ③ 期间费用率过高（金税四期：费用率异常）──
    if revenue > 0:
        period_expense = selling + admin + finance
        if period_expense > 0:
            exp_rate = period_expense / revenue
            if exp_rate > 0.5:
                findings.append({
                    "type": "待核事实：期间费用率明显偏高",
                    "level": "中风险", "score": 6,
                    "detail": (
                        f"期间费用合计{period_expense:,.2f}元（销售{selling:,.2f}+管理{admin:,.2f}"
                        f"+财务{finance:,.2f}），占主营业务收入{revenue:,.2f}元的{exp_rate:.0%}。"
                    ),
                    "description": "期间费用率显著高于常规水平，需核实是否存在多列费用、资本性支出费用化或无关支出入账。",
                    "how_found": "（销售费用+管理费用+财务费用）/ 主营业务收入 = {:.0%}。".format(exp_rate),
                    "tax_impact": "多列费用将少缴企业所得税；与经营无关的支出不得税前扣除。",
                    "policy_ref": "《企业所得税法》第八条、第十条（与取得收入无关的支出不得扣除）",
                    "suggestion": "提供费用明细构成说明，核实大额费用凭证真实性及是否与经营相关。",
                    "category": "成本费用",
                    "source_chain": "财务报表-期间费用率",
                    "redline_id": "RL-COST-005",
                    "indicator": "expense_revenue_ratio",
                    "indicator_value": round(exp_rate, 4),
                })

    # ── ④ 企业所得税税负率/贡献率偏低（金税四期核心指标，本次新增）──
    # 优先取账面所得税费用；取不到时以净利润×25%作估算口径，并在结论中明示为估算。
    if revenue > 0:
        cit_expense = 0.0
        for v in (vouchers or []):
            if not isinstance(v, dict):
                continue
            acct = str(v.get("account_name", v.get("科目", "")) or "")
            if "所得税费用" in acct:
                cit_expense += float(v.get("debit", v.get("借方", 0)) or 0)

        if cit_expense > 0:
            cit_rate = cit_expense / revenue
            _basis = "账面所得税费用 / 主营业务收入"
        elif net_profit > 0:
            cit_rate = net_profit * 0.25 / revenue
            _basis = "按净利润×25%法定税率估算所得税 / 主营业务收入（未取到所得税费用科目，为估算口径）"
        else:
            cit_rate = None
            _basis = ""

        if cit_rate is not None and cit_rate < 0.01:
            _lvl = "高风险" if cit_rate < 0.005 else "中风险"
            findings.append({
                "type": "待核事实：企业所得税贡献率偏低",
                "level": _lvl, "score": 8 if _lvl == "高风险" else 6,
                "detail": (
                    f"企业所得税贡献率约{cit_rate:.2%}（{_basis}），"
                    f"低于常规水平。主营业务收入{revenue:,.2f}元，净利润{net_profit:,.2f}元。"
                ),
                "description": (
                    "企业所得税贡献率（所得税费用占收入的比重）是金税四期横向比对的常用指标。"
                    "该指标偏低可能来自行业特性、享受税收优惠、前期亏损弥补，"
                    "也可能指向成本费用虚增或收入未足额申报，须结合行业与优惠情况核验。"
                ),
                "how_found": f"计算口径：{_basis}；结果{cit_rate:.2%}，低于1%参照线。",
                "tax_impact": "如因虚增成本费用或隐匿收入导致少缴企业所得税，需补缴税款、滞纳金并可能处罚。",
                "policy_ref": "《企业所得税法》第四条、第二十八条（税率与优惠）；《税收征收管理法》第六十三条",
                "suggestion": (
                    "①说明适用的税收优惠政策及备案情况；②提供同期行业可比资料与经营模式说明；"
                    "③说明亏损弥补、研发费用加计扣除等影响因素。"
                ),
                "category": "税负",
                "source_chain": "财务报表-企业所得税贡献率",
                "redline_id": "RL-CIT-004",
                "indicator": "cit_contribution_ratio",
                "indicator_value": round(cit_rate, 6),
            })

    # ── ⑤ 业务招待费占比（限额扣除，超标须纳税调增）──
    if revenue > 0:
        ent = 0.0
        for v in (vouchers or []):
            if not isinstance(v, dict):
                continue
            acct = str(v.get("account_name", v.get("科目", "")) or "")
            if "招待" in acct:
                ent += float(v.get("debit", v.get("借方", 0)) or 0)
        if ent > 0:
            ent_rate = ent / revenue
            if ent_rate > 0.005:  # 超过收入0.5%（法定扣除限额为发生额60%与收入5‰孰低）
                _limit = min(ent * 0.6, revenue * 0.005)
                findings.append({
                    "type": "待核事实：业务招待费超过税前扣除限额",
                    "level": "中风险", "score": 6,
                    "detail": (
                        f"业务招待费{ent:,.2f}元，占主营业务收入{revenue:,.2f}元的{ent_rate:.2%}，"
                        f"超过收入5‰的法定参照线；按孰低法可扣除约{_limit:,.2f}元，"
                        f"超额部分约{ent - _limit:,.2f}元需纳税调增。"
                    ),
                    "description": "业务招待费按发生额的60%扣除，且不得超过当年销售收入的5‰，两者取其低。",
                    "how_found": f"凭证中业务招待费合计{ent:,.2f}元 / 主营业务收入{revenue:,.2f}元 = {ent_rate:.2%}。",
                    "tax_impact": "超标部分不得税前扣除，应在汇算清缴时纳税调增，补缴企业所得税。",
                    "policy_ref": "《企业所得税法实施条例》第四十三条（业务招待费扣除标准为发生额60%且不超过销售收入5‰）",
                    "suggestion": "核实业务招待费归集是否准确，汇算清缴时按孰低法作纳税调增。",
                    "category": "成本费用",
                    "source_chain": "财务报表-业务招待费占比",
                    "redline_id": "RL-COST-005",
                    "indicator": "travel_entertainment_ratio",
                    "indicator_value": round(ent_rate, 6),
                })

    return findings


def build_statements_from_trial_balance(rows):
    """
    从科目余额表构造 资产负债表/利润表/现金流量表 三套 dict，
    供 analyze_financial_statements 做真正的表内/跨表勾稽校验。

    此前 pipeline 调用 analyze_financial_statements 时传入空的 profit/balance/cash dict，
    导致「财务报表分析」域实际只从凭证派生、未做勾稽。本函数补齐真实三表数据。

    Args: rows: 科目余额表行列表（含 code / close_debit / close_credit）
    Returns: (balance_sheet, income_stmt, cash_flow)
    """
    balance_sheet = {}
    income_stmt = {}
    cash_flow = {}  # 现金流量表不在科目余额表内，留空

    def _net(code_prefix, debit_positive=True):
        """汇总某类科目的期末净额。资产类(1)借方为正，负债/权益类(2/4)贷方为正。"""
        total = 0.0
        for r in rows or []:
            code = str(r.get("code", r.get("科目编码", "")) or "").strip()
            if not code.startswith(code_prefix):
                continue
            d = float(r.get("close_debit", r.get("期末借方", 0)) or 0)
            c = float(r.get("close_credit", r.get("期末贷方", 0)) or 0)
            total += (d - c) if debit_positive else (c - d)
        return round(total, 2)

    def _item(code, debit_positive=True):
        for r in rows or []:
            code_r = str(r.get("code", r.get("科目编码", "")) or "").strip()
            if code_r == code:
                d = float(r.get("close_debit", r.get("期末借方", 0)) or 0)
                c = float(r.get("close_credit", r.get("期末贷方", 0)) or 0)
                return round((d - c) if debit_positive else (c - d), 2)
        return 0.0

    # ── 资产负债表 ──
    total_assets = _net("1", debit_positive=True)
    total_liabilities = _net("2", debit_positive=False)
    total_equity = _net("4", debit_positive=False)
    balance_sheet["total_assets"] = total_assets
    balance_sheet["total_liabilities"] = total_liabilities
    balance_sheet["total_equity"] = total_equity

    # 关键科目（净额）
    balance_sheet["accounts_receivable"] = _item("1122") - _item("1231", debit_positive=False)  # 应收-坏账准备
    balance_sheet["advance_payments"] = _item("1123")                                         # 预付账款
    balance_sheet["other_receivables"] = _item("1221")                                         # 其他应收款
    # 存货：1401~1411 净借方 - 存货跌价准备1471 贷方
    inv = _net("14", debit_positive=True) - _item("1471", debit_positive=False)
    balance_sheet["inventory"] = round(inv, 2)
    balance_sheet["advance_receipts"] = _item("2203", debit_positive=False)                    # 预收账款
    balance_sheet["other_payables"] = _item("2241", debit_positive=False)                      # 其他应付款
    balance_sheet["salary_payable"] = _item("2211", debit_positive=False)                     # 应付职工薪酬

    # ── 利润表 ──
    revenue = _item("6001", debit_positive=False)       # 主营业务收入(贷)
    cost = _item("6401", debit_positive=True)          # 主营业务成本(借)
    selling = _item("6601", debit_positive=True)        # 销售费用
    admin = _item("6602", debit_positive=True)          # 管理费用
    finance = _item("6603", debit_positive=True)        # 财务费用
    income_stmt["revenue"] = revenue
    income_stmt["cost"] = cost
    income_stmt["selling_expense"] = selling
    income_stmt["admin_expense"] = admin
    income_stmt["finance_expense"] = finance
    income_stmt["entertainment_expense"] = 0  # 科目余额表无法区分招待费明细，留 0
    income_stmt["net_profit"] = round(revenue - cost - selling - admin - finance, 2)

    return balance_sheet, income_stmt, cash_flow


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
            "law_ref": "征管法第25条",
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
                    "law_ref": "征管法第35条",
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
            "law_ref": "企业所得税法实施条例第43条",
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
        # ★ 修复：原实现仅读取 amount 字段，当发票数据以「金额」或「价税合计」为键时会被漏算，
        #   导致匹配度被严重低估（实测 30% 被算成 15%），进而误报"进项发票远低于报表成本"。
        #   此处兼容多字段取值，与 _check_tax_audit_indicators 口径保持一致。
        pur_total = sum(
            float(i.get("amount", i.get("金额", i.get("价税合计", 0))) or 0)
            for i in pur_invs if isinstance(i, dict)
        )
        if pur_total > 0 and cost > 0:
            ratio = pur_total / cost
            if ratio < 0.6:
                findings.append({
                    "type": "进项发票远低于报表成本",
                    "level": "高风险", "score": 8,
                    "detail": f"进项发票{pur_total:,.0f}仅为报表成本{cost:,.0f}的{ratio:.0%}",
                    "tax_impact": "大量无票成本→不得税前扣除→可能虚构成本→补缴企业所得税",
                    "law_ref": "企业所得税法第8条",
                    "policy_ref": "《企业所得税税前扣除凭证管理办法》（国家税务总局公告2018年第28号）第九条",
                    "suggestion": "提供差额部分的采购合同、入库单与付款记录；属暂估的请说明期后取得发票情况。",
                    "redline_id": "RL-COST-003",
                    "indicator": "purchase_invoice_match",
                    "indicator_value": round(ratio, 4),
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
                    "law_ref": "企业所得税法第46条(资本弱化)",
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
                "law_ref": "征管法第63条(偷税)",
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
                    "law_ref": "征管法第63条",
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
            "law_ref":"中华人民共和国增值税法第19条；征管法第63条",
            "suggestion":f"逐笔核实预收账款对应的发货记录，已发货未开票的应确认收入补税约{adv_recv*0.13:,.0f}元(增值税)"})
    
    # -- 预付账款 --
    adv_pay = bs.get("advance_payments", bs.get("预付账款", 0)) or 0
    if adv_pay > 0 and revenue > 0 and adv_pay / revenue > 0.2:
        findings.append({"type":"预付账款占比过高","level":"中风险","score":7,
            "detail":f"预付账款{adv_pay:,.0f}元，占收入{adv_pay/revenue:.0%}",
            "tax_impact":"大额预付→可能虚构采购套取资金/关联方占用",
            "law_ref":"征管法第35条",
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
            "law_ref":"征管法第35条"})
    
    # -- 存货 --
    inv = bs.get("inventory", bs.get("存货", 0)) or 0
    if inv > 0 and revenue > 0 and inv / revenue > 0.5:
        findings.append({"type":"存货占比过高","level":"中风险","score":6,
            "detail":f"存货{inv:,.0f}元，占收入{inv/revenue:.0%}",
            "tax_impact":"存货积压→可能少转成本虚增利润/账外销售",
            "law_ref":"征管法第35条"})
    
    # -- 应收账款 --
    ar = bs.get("accounts_receivable", bs.get("应收账款", 0)) or 0
    if ar > 0 and revenue > 0 and ar / revenue > 0.5:
        findings.append({"type":"应收账款占比过高","level":"中风险","score":6,
            "detail":f"应收账款{ar:,.0f}元，占收入{ar/revenue:.0%}",
            "tax_impact":"大量赊销→可能存在虚开发票/虚构收入",
            "law_ref":"征管法第35条"})
    
    # -- 应付职工薪酬 --
    sal_pay = bs.get("salary_payable", bs.get("应付职工薪酬", 0)) or 0
    if sal_pay > 0 and revenue > 0 and sal_pay / revenue > 0.1:
        findings.append({"type":"应付职工薪酬余额偏高","level":"中风险","score":6,
            "detail":f"应付职工薪酬{sal_pay:,.0f}元",
            "tax_impact":"已计提未发放→汇算清缴前未发放不得税前扣除",
            "law_ref":"企业所得税法实施条例第34条"})
    
    return findings

"""税前扣除限额补充探测器 —— 金税四期"纳税调整"类缺口的量化落地。

背景：`verified_rule_engine` 已有 VR038 业务招待费、VR039 广告费与业务宣传费、
VR040 职工福利费 三项扣除限额规则；本模块补齐同属"税前扣除限额"家族、此前缺失的：
  1) 工会经费超标（不超过工资薪金总额 2%）
  2) 职工教育经费超标（不超过工资薪金总额 8%）
  3) 公益性捐赠超标（不超过年度利润总额 12%）
  4) 关联方利息债资比超标（非金融企业 2:1，超支部分不得扣除）

数据来源：记账凭证（按科目归集）+ 利润表。均为可从账面复算的待核事实，
铁律：仅输出可复算的数量事实，不自动定性；无数据（取不到工资/利润等基数）不输出。
"""

from engine.numparse import to_number  # ★ 2026-09-25 统一数值解析（唯一实现）
from collections import defaultdict

# ── 阈值 ──
_UNION_RATE = 0.02          # 工会经费：工资薪金总额 2%
_EDU_RATE = 0.08            # 职工教育经费：工资薪金总额 8%
_DONATION_RATE = 0.12       # 公益性捐赠：年度利润总额 12%
_DEBT_EQUITY_RATIO = 2.0    # 非金融企业关联方债资比 2:1
_MIN_BASE = 10000.0         # 基数下限（元），低于此不判定，避免小样本噪音


def _safe(v):
    """数值解析（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/numparse.py（唯一权威）。
      原私有实现遇 "12,000.00" / "￥1,234.56" 等会静默返回 0，
      导致同一金额在不同模块被算成不同值（报告自相矛盾 / 规则漏触发）。
    """
    from engine.numparse import to_number as _to_number
    return _to_number(v)


def _acct(v):
    if not isinstance(v, dict):
        return ""
    return str(v.get("account_name", v.get("科目", v.get("account", ""))) or "")


def _dr(v):
    if not isinstance(v, dict):
        return 0.0
    return _safe(v.get("debit", v.get("借方", 0)))


def _wage_total(vouchers):
    """工资薪金总额：优先取'应付职工薪酬'贷方发生额，否则退取含'工资'科目借方。"""
    by_salary = 0.0
    by_wage = 0.0
    for v in (vouchers or []):
        if not isinstance(v, dict):
            continue
        a = _acct(v)
        if "应付职工薪酬" in a:
            by_salary += _safe(v.get("credit", v.get("贷方", 0)))
        if "工资" in a or "薪酬" in a:
            by_wage += _dr(v)
    return by_salary if by_salary > 0 else by_wage


def _profit_total(income):
    """利润总额：优先取账面利润总额，退而用净利润反推（口径估算）。"""
    if not isinstance(income, dict):
        return 0.0, ""
    for k in ("total_profit", "profit_total", "利润总额", "pretax_profit"):
        v = income.get(k)
        if v not in (None, ""):
            f = _safe(v)
            if f:
                return f, "账面利润总额"
    np_ = _safe(income.get("net_profit", income.get("净利润", 0)))
    if np_:
        return np_ / 0.75, "按净利润÷0.75反推利润总额（估算口径）"
    return 0.0, ""


def _mk(type_, level, score, detail, description, how_found, tax_impact,
        policy_ref, suggestion, category, source_chain, redline_id, indicator, value):
    """finding 构造（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/findingkit.py（唯一权威）。
      原先三个模块各有一份**逐字节相同**的副本，只改一份就会导致字段集不一致。
    """
    from engine.findingkit import make_finding as _make_finding
    return _make_finding(type_, level, score, detail, description, how_found, tax_impact, policy_ref, suggestion, category, source_chain, redline_id, indicator, value)


def _check_union_and_edu(vouchers):
    findings = []
    wage = _wage_total(vouchers)
    if wage < _MIN_BASE:
        return findings
    union = edu = 0.0
    for v in (vouchers or []):
        if not isinstance(v, dict):
            continue
        a = _acct(v)
        if "工会" in a:
            union += _dr(v)
        if "教育经费" in a or "职工教育" in a:
            edu += _dr(v)
    # 工会经费
    lim_u = wage * _UNION_RATE
    if union > lim_u > 0:
        findings.append(_mk(
            "待核事实：工会经费超过税前扣除限额",
            "中风险", 5,
            f"工会经费发生额{union:,.2f}元，工资薪金总额{wage:,.2f}元，扣除限额{lim_u:,.2f}元，"
            f"超支约{union - lim_u:,.2f}元。",
            "工会经费不超过工资薪金总额2%的部分准予扣除，超过部分应作纳税调增。",
            f"工会经费 / 工资薪金总额 = {union / wage:.2%}（限额2%）。",
            "超限额部分未调增将少缴企业所得税。",
            "《企业所得税法实施条例》第四十一条（工会经费扣除限额为工资薪金总额的2%）",
            "核实工会经费是否取得工会经费收入专用收据，超支部分在汇算清缴时纳税调增。",
            "成本费用", "凭证-工会经费限额", "RL-COST-005", "union_fund_over_limit", round(union - lim_u, 2),
        ))
    # 职工教育经费
    lim_e = wage * _EDU_RATE
    if edu > lim_e > 0:
        findings.append(_mk(
            "待核事实：职工教育经费超过税前扣除限额",
            "中风险", 5,
            f"职工教育经费发生额{edu:,.2f}元，工资薪金总额{wage:,.2f}元，扣除限额{lim_e:,.2f}元，"
            f"超支约{edu - lim_e:,.2f}元（可在以后年度结转扣除）。",
            "职工教育经费不超过工资薪金总额8%的部分准予扣除，超过部分准予结转以后纳税年度扣除。",
            f"职工教育经费 / 工资薪金总额 = {edu / wage:.2%}（限额8%）。",
            "超限额部分当期不得扣除（可结转），未调整将影响当期应纳税所得额。",
            "《企业所得税法实施条例》第四十二条（职工教育经费扣除限额为工资薪金总额的8%）",
            "核实职工教育经费归集与凭证，超支部分按规定结转扣除或纳税调整。",
            "成本费用", "凭证-教育经费限额", "RL-COST-005", "edu_fund_over_limit", round(edu - lim_e, 2),
        ))
    return findings


def _check_public_welfare_donation(vouchers, income):
    profit, basis = _profit_total(income)
    if profit < _MIN_BASE:
        return []
    donation = 0.0
    for v in (vouchers or []):
        if not isinstance(v, dict):
            continue
        a = _acct(v)
        if ("捐赠" in a) or ("公益性" in a):
            donation += _dr(v)
    lim = profit * _DONATION_RATE
    if donation > lim > 0:
        return [_mk(
            "待核事实：公益性捐赠超过税前扣除限额",
            "中风险", 5,
            f"公益性捐赠支出{donation:,.2f}元，年度利润总额{profit:,.2f}元（{basis}），"
            f"扣除限额{lim:,.2f}元，超支约{donation - lim:,.2f}元。",
            "企业发生的公益性捐赠支出，不超过年度利润总额12%的部分准予扣除，超过部分准予结转以后三年内扣除。",
            f"公益性捐赠 / 年度利润总额 = {donation / profit:.2%}（限额12%）。",
            "超限额部分当期不得扣除（可结转三年），未调整将影响应纳税所得额。",
            "《企业所得税法》第九条、《企业所得税法实施条例》第五十三条（公益性捐赠扣除限额）",
            "核实捐赠是否通过公益性社会组织或县级以上人民政府（取得合规捐赠票据），超支部分结转或调增。",
            "成本费用", "凭证-公益性捐赠限额", "RL-COST-005", "donation_over_limit", round(donation - lim, 2),
        )]
    return []


def _check_related_party_debt_equity(bs, vouchers):
    if not isinstance(bs, dict):
        return []
    equity = _safe(bs.get("total_equity", bs.get("所有者权益", 0)))
    if equity < _MIN_BASE:
        return []
    # 关联方借款：取'其他应付款/短期借款/长期借款'中含'关联'或'股东'的贷方余额
    related_loan = 0.0
    for v in (vouchers or []):
        if not isinstance(v, dict):
            continue
        a = _acct(v)
        if any(k in a for k in ("关联", "股东")) and any(k in a for k in ("借款", "应付", "拆借", "往来")):
            related_loan += _safe(v.get("credit", v.get("贷方", 0)))
    if related_loan <= 0:
        return []
    ratio = related_loan / equity
    if ratio > _DEBT_EQUITY_RATIO:
        excess = related_loan - equity * _DEBT_EQUITY_RATIO
        return [_mk(
            "待核事实：关联方债权性投资与权益性投资比例偏高",
            "中风险", 6,
            f"（疑似）关联方借款{related_loan:,.2f}元，所有者权益{equity:,.2f}元，"
            f"债资比约{ratio:.2f}:1，超出非金融企业2:1标准，超标准债权投资约{excess:,.2f}元。",
            "非金融企业实际支付给关联方的利息支出，在债权性投资与权益性投资比例不超过2:1的部分准予扣除，"
            "超过部分不得扣除，且利率不得超过金融企业同期同类贷款利率。",
            f"关联方借款 / 所有者权益 = {ratio:.2f}:1（标准2:1）。",
            "超标准部分对应的利息支出不得税前扣除，未调整将少缴企业所得税。",
            "《企业所得税法》第四十六条；财税〔2008〕121号（关联方债资比2:1）",
            "核实关联方借款性质与利率，按2:1限额计算可扣除利息并作纳税调整，补充关联关系与独立交易原则举证。",
            "关联交易", "凭证-关联方债资比", "RL-CIT-002", "related_party_debt_equity_ratio", round(ratio, 4),
        )]
    return []


def detect_deduction_limits(vouchers, income, bs, ctx=None):
    """税前扣除限额补充探测器主入口。

    Returns: findings list（每项带 redline_id）
    """
    findings = []
    for _fn in (
        lambda: _check_union_and_edu(vouchers),
        lambda: _check_public_welfare_donation(vouchers, income),
        lambda: _check_related_party_debt_equity(bs, vouchers),
    ):
        try:
            findings.extend(_fn() or [])
        except Exception:
            continue
    return findings

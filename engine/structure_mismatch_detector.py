"""结构错配探测器 —— 补齐金税四期"费用/成本结构 + 进项属性与主业匹配"类缺口。

背景：`verified_rule_engine` 已覆盖 VR031/035 印花税、VR042 房产税、VR070 固定资产处置、
VR032 进项转出等；`financial_analyzer` 已算期间费用率（费用/收入）。此前缺失的是：
  1) 期间费用与销售成本比例异常（费用/成本，区别于费用/收入）
  2) 农产品类进项税额与主营业务明显不符（主业与农产品无关却大量抵扣农产品）

均可从利润表 + 进项发票 + 企业行业画像复算，铁律：只输出可复算事实，不自动定性；无数据不输出。
"""

_AGRI_GOODS = ("农产品", "粮食", "棉花", "中药材", "木材", "原木", "生猪", "活畜",
               "蔬菜", "水果", "茶叶", "竹木", "苗木", "皮棉", "玉米", "大豆", "小麦", "稻谷")
_AGRI_INDUSTRY = ("农", "林", "牧", "渔", "食品", "纺织", "木材", "家具", "中药",
                  "医药制造", "农产品加工", "饲料", "酿造", "食用", "种植", "养殖")
# 期间费用 / 销售成本 的异常参照线
_EXP_COST_HIGH = 0.80   # 费用接近或超过成本，多数行业不合理
_EXP_COST_LOW = 0.02    # 费用极低（<2%），可能费用未如实归集
_AGRI_MIN_AMT = 100000.0  # 农产品进项关注金额


def _safe(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _goods(inv):
    if not isinstance(inv, dict):
        return ""
    return str(inv.get("goods", inv.get("货物或应税劳务名称", inv.get("商品名称", ""))) or "")


def _amt(inv):
    if not isinstance(inv, dict):
        return 0.0
    for k in ("amount", "金额", "价税合计", "total"):
        v = inv.get(k)
        if v not in (None, ""):
            a = abs(_safe(v))
            if a:
                return a
    return 0.0


def _industry(ctx):
    if ctx is None:
        return ""
    for src in (getattr(ctx, "company_profile", None), getattr(ctx, "industry_profile", None)):
        if isinstance(src, dict):
            for k in ("industry", "行业", "industry_name", "biz_model", "行业名称"):
                v = src.get(k)
                if v:
                    return str(v)
    return ""


def _mk(type_, level, score, detail, description, how_found, tax_impact,
        policy_ref, suggestion, category, source_chain, redline_id, indicator, value):
    return {
        "type": type_, "level": level, "score": score,
        "detail": detail, "description": description, "how_found": how_found,
        "tax_impact": tax_impact, "policy_ref": policy_ref, "suggestion": suggestion,
        "category": category, "source_chain": source_chain,
        "redline_id": redline_id, "indicator": indicator, "indicator_value": value,
    }


def _check_expense_cost_ratio(income):
    if not isinstance(income, dict):
        return []
    revenue = _safe(income.get("revenue", income.get("营业收入", 0)))
    cost = _safe(income.get("cost", income.get("营业成本", 0)))
    se = _safe(income.get("selling_expense", 0))
    ae = _safe(income.get("admin_expense", 0))
    fe = _safe(income.get("finance_expense", 0))
    period = se + ae + fe
    if cost <= 0 or period <= 0:
        return []
    ratio = period / cost
    if ratio >= _EXP_COST_HIGH or ratio <= _EXP_COST_LOW:
        lvl = "中风险" if ratio >= _EXP_COST_HIGH else "低风险"
        return [_mk(
            "待核事实：期间费用与销售成本比例异常",
            lvl, 6 if ratio >= _EXP_COST_HIGH else 4,
            f"期间费用合计{period:,.2f}元，主营业务成本{cost:,.2f}元，费用/成本比例约{ratio:.0%}"
            + ("（费用接近或超过成本，多数行业不合理）。" if ratio >= _EXP_COST_HIGH
               else "（费用占比极低，可能费用未如实归集）。"),
            "期间费用与销售成本的比例结构能反映费用归集是否合理。费用异常偏高可能指向多列费用、"
            "资本性支出费用化；异常偏低则可能费用未足额归集或成本核算口径不一致，均需核实。",
            f"（销售+管理+财务费用）/ 主营业务成本 = {ratio:.0%}。",
            "费用归集异常将影响企业所得税应纳税所得额的准确性。",
            "《企业所得税法》第八条、第十条（与取得收入有关的、合理的支出准予扣除）",
            "提供费用明细与成本核算说明，核实费用归集口径及与经营的相关性。",
            "成本费用", "结构-期间费用与成本比例", "RL-COST-005", "expense_cost_ratio", round(ratio, 4),
        )]
    return []


def _check_agri_input_mismatch(pur_invs, ctx):
    if not pur_invs:
        return []
    industry = _industry(ctx)
    agri_amt = 0.0
    agri_cnt = 0
    for i in pur_invs:
        g = _goods(i)
        if any(k in g for k in _AGRI_GOODS):
            agri_amt += _amt(i)
            agri_cnt += 1
    if agri_amt < _AGRI_MIN_AMT or agri_cnt < 1:
        return []
    # 行业与农产品明显无关时才提示（避免误伤食品/纺织/中药等本就涉农的行业）
    if industry and any(k in industry for k in _AGRI_INDUSTRY):
        return []
    return [_mk(
        "待核事实：农产品类进项税额与主营业务关联性存疑",
        "中风险", 6,
        f"取得农产品类进项发票{agri_cnt}张、金额合计{agri_amt:,.2f}元"
        + (f"，而企业行业为「{industry}」" if industry else "，未能取得企业行业信息")
        + "，与主营业务关联性存疑。",
        "农产品收购发票、农产品进项加计抵扣是虚开与虚抵的高发领域；若企业主业与农产品无关，"
        "却大量抵扣农产品进项，需核实收购的真实性、是否具备收购资质及与经营的关联性。",
        f"进项发票中农产品类金额{agri_amt:,.2f}元（行业：{industry or '未知'}）。",
        "与经营无关的农产品进项若不符合抵扣条件，面临进项税额转出与补税。",
        "《增值税暂行条例》第八条、第九条；农产品收购发票使用相关规定",
        "提供农产品收购合同、收购发票、付款凭证、入库与运输单据及使用去向说明，核实抵扣合规性。",
        "增值税", "进项-农产品与主业匹配", "RL-VAT-002", "agri_input_amount", round(agri_amt, 2),
    )]


def detect_structure_mismatch(pur_invs, income, ctx=None):
    findings = []
    for _fn in (
        lambda: _check_expense_cost_ratio(income),
        lambda: _check_agri_input_mismatch(pur_invs, ctx),
    ):
        try:
            findings.extend(_fn() or [])
        except Exception:
            continue
    return findings

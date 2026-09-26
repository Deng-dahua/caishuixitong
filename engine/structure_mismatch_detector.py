from engine.numparse import to_number  # ★ 2026-09-25 统一数值解析（唯一实现）
"""结构错配探测器 —— 补齐金税四期"费用/成本结构 + 进项属性与主业匹配"类缺口。

背景：`verified_rule_engine` 已覆盖 VR031/035 印花税、VR042 房产税、VR070 固定资产处置、
VR032 进项转出等；`financial_analyzer` 已算期间费用率（费用/收入）。此前缺失的是：
  1) 期间费用与销售成本比例异常（费用/成本，区别于费用/收入）
  2) 农产品类进项税额与主营业务明显不符（主业与农产品无关却大量抵扣农产品）

均可从利润表 + 进项发票 + 企业行业画像复算，铁律：只输出可复算事实，不自动定性；无数据不输出。
"""

_AGRI_GOODS = ("农产品", "粮食", "棉花", "中药材", "木材", "原木", "生猪", "活畜",
               "蔬菜", "水果", "茶叶", "竹木", "苗木", "皮棉", "玉米", "大豆", "小麦", "稻谷")
_AGRI_INDUSTRY = ("农", "林业", "园林", "绿化", "林场", "森林", "牧", "渔", "食品", "纺织",
                  "木材", "家具", "中药", "医药制造", "农产品加工", "饲料", "酿造", "食用",
                  "种植", "养殖")
# 期间费用 / 销售成本 的异常参照线
_EXP_COST_HIGH = 0.80   # 费用接近或超过成本，多数行业不合理
_EXP_COST_LOW = 0.02    # 费用极低（<2%），可能费用未如实归集
_AGRI_MIN_AMT = 100000.0  # 农产品进项关注金额

# ── 成本商品结构基线（补齐"成本结构与行业应有结构差异"缺口，2026-09-15）──
# 商品类别识别：关键词 → 类别（进项品名用于近似主营业务成本的投入结构）
_GOODS_CATS = (
    ("苗木绿化", ("苗木", "绿化", "花卉", "草皮", "草坪", "树苗", "乔木", "灌木", "园林", "苗")),
    ("砂石建材", ("沙", "砂", "碎石", "石材", "石头", "砖", "水泥", "石灰", "混凝土", "沥青",
                  "建材", "土方", "回填", "石")),
    ("金属材料", ("钢", "铁", "铝", "铜", "五金", "管材", "型材", "板材")),
    ("人工劳务", ("劳务", "人工", "工资", "派遣", "分包", "用工", "班组")),
    ("机械租赁", ("机械", "设备租赁", "租赁", "台班", "吊装", "挖掘")),
    ("农产农副", ("农产品", "粮食", "蔬菜", "水果", "中药材", "生猪", "活畜", "饲料", "化肥", "农药")),
)
# 行业 → 关键类别应占区间（经验参考区间、非官方口径；须结合合同/物流/入库核验；结构≠违规）
_STRUCT_BASELINE = {
    "园林": {"苗木绿化": (0.15, 0.55), "砂石建材": (0.10, 0.50)},
    "绿化": {"苗木绿化": (0.15, 0.55), "砂石建材": (0.10, 0.50)},
    "景观": {"苗木绿化": (0.15, 0.55), "砂石建材": (0.10, 0.50)},
    "建筑": {"砂石建材": (0.20, 0.60), "人工劳务": (0.05, 0.40)},
    "工程": {"砂石建材": (0.20, 0.60), "人工劳务": (0.05, 0.40)},
    "市政": {"砂石建材": (0.20, 0.60), "人工劳务": (0.05, 0.40)},
    "施工": {"砂石建材": (0.20, 0.60), "人工劳务": (0.05, 0.40)},
}
_STRUCT_MIN_TOTAL = 500000.0   # 进项合计门槛（低于此不据结构下判断）
_STRUCT_MARGIN = 0.10          # 结构偏离容差（±10 个百分点内不算偏离）


def _safe(v):
    """数值解析（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/numparse.py（唯一权威）。
      原私有实现遇 "12,000.00" / "￥1,234.56" 等会静默返回 0，
      导致同一金额在不同模块被算成不同值（报告自相矛盾 / 规则漏触发）。
    """
    from engine.numparse import to_number as _to_number
    return _to_number(v)


def _goods(inv) -> str:
    """字段读取/语义判定（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/fieldkit.py（唯一权威）。
      原多份私有实现互相不一致，导致同一张发票在不同检测器里结论不同。
    """
    from engine.fieldkit import goods_name as _fk
    return _fk(inv)


def _cat_of(goods):
    """进项品名 → 成本类别（用于近似主营业务成本的投入结构）。未命中归"其他"。"""
    g = str(goods or "")
    for cat, kws in _GOODS_CATS:
        if any(k in g for k in kws):
            return cat
    return "其他"


def _amt(inv):
    """数值解析（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/numparse.py（唯一权威）。
      原私有实现遇 "12,000.00" / "￥1,234.56" 等会静默返回 0，
      导致同一金额在不同模块被算成不同值（报告自相矛盾 / 规则漏触发）。
    """
    from engine.numparse import first_amount as _first_amount
    return _first_amount(inv, absolute=True)


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
    """finding 构造（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/findingkit.py（唯一权威）。
      原先三个模块各有一份**逐字节相同**的副本，只改一份就会导致字段集不一致。
    """
    from engine.findingkit import make_finding as _make_finding
    return _make_finding(type_, level, score, detail, description, how_found, tax_impact, policy_ref, suggestion, category, source_chain, redline_id, indicator, value)


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


def _check_cost_goods_structure(pur_invs, ctx):
    """主营业务成本的商品构成 vs 行业应有结构（2026-09-15 新增）。

    结构≠违规：仅在「行业命中基线 + 进项合计达门槛 + 某类别占比偏离超容差」三者同时满足时，
    输出待核线索（level="待核验"）。区间为经验参考、非官方口径。
    """
    if not pur_invs:
        return []
    industry = _industry(ctx)
    if not industry:
        return []
    baseline = None
    for kw, spec in _STRUCT_BASELINE.items():
        if kw in industry:
            baseline = spec
            break
    if not baseline:
        return []
    total = sum(_amt(i) for i in pur_invs)
    if total < _STRUCT_MIN_TOTAL:
        return []
    shares = {}
    for i in pur_invs:
        cat = _cat_of(_goods(i))
        shares[cat] = shares.get(cat, 0.0) + _amt(i)

    findings = []
    for cat, (lo, hi) in baseline.items():
        share = shares.get(cat, 0.0) / total
        if share > hi + _STRUCT_MARGIN:
            direction = "明显偏高"
        elif share < lo - _STRUCT_MARGIN:
            direction = "明显偏低"
        else:
            continue
        findings.append(_mk(
            "待核事实：主营业务成本结构与行业常规差异明显",
            "待核验", 5,
            f"取得发票按商品类别归集中，「{cat}」占比 {share:.0%}，{direction}于该行业参考区间 "
            f"({lo:.0%}~{hi:.0%})（区间为经验参考、非官方口径）。",
            "主营业务成本的投入结构应与企业所属行业的常规结构大致相符。结构明显偏离可能源于"
            "业务实质与登记行业不符、成本归集错配，或采购票据与真实业务不一致，须结合合同、"
            "运输与入库单据核验；结构本身不等同于违规。",
            f"进项按商品类别归集：{cat} 占 {share:.0%}（行业参考 {lo:.0%}~{hi:.0%}）。",
            "成本结构与行业不符本身不构成违规；若同时伴随票据/物流/入库缺失，相关成本的税前扣除"
            "与进项抵扣可能受影响。",
            "《企业所得税法》第八条（实际发生、与取得收入有关且合理的支出方可扣除）",
            "提供采购合同、运输单据、入库验收单及成本核算底稿，说明结构与行业差异的原因。",
            "成本费用", "结构-成本商品构成与行业差异", "RL-COST-005",
            "cost_goods_structure_share", round(share, 4),
        ))
    return findings


def detect_structure_mismatch(pur_invs, income, ctx=None):
    findings = []
    for _fn in (
        lambda: _check_expense_cost_ratio(income),
        lambda: _check_agri_input_mismatch(pur_invs, ctx),
        lambda: _check_cost_goods_structure(pur_invs, ctx),
    ):
        try:
            findings.extend(_fn() or [])
        except Exception:
            continue
    return findings

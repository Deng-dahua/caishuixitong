"""发票开票行为模式探测器 —— 金税四期"发票行为类"缺口的量化落地。

背景：系统已有虚开网络比对（false_invoice）、发票生命周期/深度特征/红冲作废追踪
（domain_analysis）等能力，但仍有一批**开票行为类**金税四期特征未被量化复核，
本模块补齐以下 7 类（均为可从进/销项发票直接复算的待核线索）：

  1) 月末集中开票 —— 开票金额异常集中在月末几天（调节收入/突击开票特征）
  2) 开票日期集中度异常 —— 极少数开票日承载绝大部分金额（突击/集中开票）
  3) 免税额度临界卡位 —— 小规模纳税人月/季开票额长期卡在免税额度或80%以上区间
  4) 个人抬头发票占比偏高 —— 进项费用票抬头为个人，与经营相关性存疑
  5) 进项税额控制额异常 —— 进项税额长期大于销项税额（大额留抵，涉嫌虚抵/囤票）
  6) 同一对方同金额多张发票 —— 疑似拆分开票 / 重复开具
  7) 跨年度红冲大额发票 —— 汇算清缴后大额红冲上年度发票，调节利润嫌疑

铁律：仅输出可复算的数量事实与待核线索，不自动定性；无数据 / 数据不足一律不输出。
"""

from engine.numparse import to_number  # ★ 2026-09-25 统一数值解析（唯一实现）
import re
from collections import defaultdict

# ── 阈值 ──
_MONTH_END_DAYS = 3          # 月末最后 N 天
_MONTH_END_SHARE = 0.50      # 月末开票金额占比阈值
_DATE_TOP1_SHARE = 0.30      # 单日集中度阈值
_DATE_TOP3_SHARE = 0.60      # 前三日集中度阈值
_MIN_INVOICES = 10           # 参与集中度判定的最小发票张数
_INDIV_BUYER_SHARE = 0.30    # 个人抬头占比阈值
_INPUT_TAX_RATIO = 1.50      # 进项税额 / 销项税额 阈值（大额留抵）
_MIN_MATCH_RATIO = 5.0       # 进项税额相对销项税额的极端倍数
_SAME_PAIR_COUNT = 3         # 同一对方同一金额最小张数
_SAME_PAIR_WINDOW = 45       # 同一对方同金额的时间窗（天）
_CROSS_YEAR_AMT = 500000.0   # 跨年度红冲关注金额（元）

_ENTERPRISE_KW = ("公司", "厂", "店", "中心", "部", "行", "社", "院", "所", "有限",
                  "企业", "集团", "合作社", "工作室", "事务所", "商行", "经营部")
_SMALL_SCALE_KW = ("小规模", "小规模纳税人")
_VAT_FREE_MONTH = 100000.0   # 小规模月免税额度（元）
_VAT_FREE_QUARTER = 300000.0  # 小规模季免税额度（元）


def _safe(v):
    """数值解析（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/numparse.py（唯一权威）。
      原私有实现遇 "12,000.00" / "￥1,234.56" 等会静默返回 0，
      导致同一金额在不同模块被算成不同值（报告自相矛盾 / 规则漏触发）。
    """
    from engine.numparse import to_number as _to_number
    return _to_number(v)


def _amt(inv):
    """数值解析（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/numparse.py（唯一权威）。
      原私有实现遇 "12,000.00" / "￥1,234.56" 等会静默返回 0，
      导致同一金额在不同模块被算成不同值（报告自相矛盾 / 规则漏触发）。
    """
    from engine.numparse import first_amount as _first_amount
    return _first_amount(inv, absolute=True)


def _tax(inv):
    if not isinstance(inv, dict):
        return 0.0
    return abs(_safe(inv.get("tax", inv.get("税额", 0))))


def _buyer(inv) -> str:
    """字段读取/语义判定（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/fieldkit.py（唯一权威）。
      原多份私有实现互相不一致，导致同一张发票在不同检测器里结论不同。
    """
    from engine.fieldkit import buyer_name as _fk
    return _fk(inv)


def _seller(inv) -> str:
    """字段读取/语义判定（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/fieldkit.py（唯一权威）。
      原多份私有实现互相不一致，导致同一张发票在不同检测器里结论不同。
    """
    from engine.fieldkit import seller_name as _fk
    return _fk(inv)


def _buyer_tax(inv):
    if not isinstance(inv, dict):
        return ""
    return str(inv.get("buyer_tax", inv.get("购方税号", inv.get("购买方纳税人识别号", ""))) or "").strip()


def _inv_type(inv) -> str:
    """字段读取/语义判定（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/fieldkit.py（唯一权威）。
      原多份私有实现互相不一致，导致同一张发票在不同检测器里结论不同。
    """
    from engine.fieldkit import invoice_type as _fk
    return _fk(inv)


def _is_void_or_red(inv) -> bool:
    """字段读取/语义判定（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/fieldkit.py（唯一权威）。
      原多份私有实现互相不一致，导致同一张发票在不同检测器里结论不同。
    """
    from engine.fieldkit import is_void_or_red as _fk
    return _fk(inv)


def _rate(inv):
    """征收率/税率（小数），失败返回 None。"""
    if not isinstance(inv, dict):
        return None
    v = inv.get("tax_rate", inv.get("税率", None))
    if v in (None, ""):
        return None
    s = str(v)
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    f = float(m.group(1))
    if f > 1:  # 13 → 0.13
        f = f / 100.0
    return f


def _parse_date(inv):
    """返回 (year, month, day) 或 None。兼容 2024-01-15 / 2024/1/15 / 2024年1月15日 / 20240115。"""
    if not isinstance(inv, dict):
        return None
    s = str(inv.get("date", inv.get("开票日期", inv.get("invoice_date", ""))) or "").strip()
    if not s:
        return None
    m = re.search(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})", s)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.search(r"^(\d{4})(\d{2})(\d{2})$", s.replace("-", "").replace("/", ""))
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.search(r"(\d{4})[-/年.](\d{1,2})", s)
    if m:
        return int(m.group(1)), int(m.group(2)), 15
    return None


def _days_in_month(y, m):
    if m == 12:
        return 31
    import calendar
    return calendar.monthrange(y, m)[1]


def _mk(type_, level, score, detail, description, how_found, tax_impact,
        policy_ref, suggestion, category, source_chain, redline_id, indicator, value):
    """finding 构造（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/findingkit.py（唯一权威）。
      原先三个模块各有一份**逐字节相同**的副本，只改一份就会导致字段集不一致。
    """
    from engine.findingkit import make_finding as _make_finding
    return _make_finding(type_, level, score, detail, description, how_found, tax_impact, policy_ref, suggestion, category, source_chain, redline_id, indicator, value)


# ── 1) 月末集中开票 ──
def _check_month_end(sal):
    dated = [(i, _parse_date(i)) for i in sal if not _is_void_or_red(i)]
    dated = [(i, d) for i, d in dated if d]
    if len(dated) < _MIN_INVOICES:
        return []
    total = sum(_amt(i) for i, _ in dated)
    if total <= 0:
        return []
    end_amt = 0.0
    end_cnt = 0
    for i, (y, m, d) in dated:
        if d >= _days_in_month(y, m) - _MONTH_END_DAYS + 1:
            end_amt += _amt(i)
            end_cnt += 1
    share = end_amt / total
    if share >= _MONTH_END_SHARE and end_cnt >= 5:
        _f = _mk(
            "待核事实：开票金额异常集中在月末",
            "中风险", 6,
            f"{len(dated)}张已开票中，有{end_cnt}张（金额{end_amt:,.2f}元）开具在月末最后{_MONTH_END_DAYS}天，"
            f"占可归属开票总额{total:,.2f}元的{share:.0%}。",
            "开票行为集中在月末，常见于按月度口径调节收入规模、突击完成开票任务或匹配申报节奏，"
            "需核实是否为真实业务节奏，还是人为集中开具调节当期收入。",
            f"月末{_MONTH_END_DAYS}天开票金额 / 可归属开票总额 = {share:.0%}（不低于50%）。",
            "人为集中开票可能造成收入期间错配，影响增值税与企业所得税的纳税义务所属期。",
            "《发票管理办法》关于按实际经营业务如实、及时开具发票的规定；《增值税暂行条例》第十九条",
            "核对月末集中开票对应的合同、发货与收款时点，说明开票节奏的业务合理性。",
            "发票行为", "发票-月末集中开票", "RL-PTY-005", "month_end_invoice_share", round(share, 4),
        )
        # ★ 2026-09-28：逐条判定 RL-PTY-005 第③条要件（开票日期时点异常）
        _f["constituent_hits"] = [{
            "index": 3,
            "evidence": f"{end_cnt} 张已开票（金额 {end_amt:,.2f} 元）集中在月末最后 {_MONTH_END_DAYS} 天，"
                        f"占可归属开票总额的 {share:.0%}——开票时点异常（是否与业务实际发生期矛盾须核对出库/收款单据）",
        }]
        return [_f]
    return []


# ── 2) 开票日期集中度异常 ──
def _check_date_concentration(sal):
    dated = [(i, _parse_date(i)) for i in sal if not _is_void_or_red(i)]
    dated = [(i, d) for i, d in dated if d]
    if len(dated) < _MIN_INVOICES:
        return []
    total = sum(_amt(i) for i, _ in dated)
    if total <= 0:
        return []
    by_day = defaultdict(float)
    for i, d in dated:
        by_day[d] += _amt(i)
    ordered = sorted(by_day.values(), reverse=True)
    top1 = ordered[0] / total if ordered else 0
    top3 = sum(ordered[:3]) / total if ordered else 0
    if top1 >= _DATE_TOP1_SHARE or top3 >= _DATE_TOP3_SHARE:
        _f = _mk(
            "待核事实：开票日期高度集中",
            "中风险", 6,
            f"{len(dated)}张已开票分布在{len(by_day)}个开票日，金额最大的1天占{top1:.0%}、"
            f"前3天占{top3:.0%}，开票日期高度集中。",
            "正常经营的发票通常分散开具；少数几天承载绝大部分开票金额，是突击开票、集中冲量"
            "或人为调节收入期间的特征，需核实对应业务的真实发生日期。",
            f"单日最大开票金额占比={top1:.0%}、前3日占比={top3:.0%}（阈值30%/60%）。",
            "集中开票可能造成收入确认期间与业务实际不符，影响纳税义务所属期与所得税归属。",
            "《发票管理办法》关于如实、及时开具发票的规定",
            "提供主要开票日的合同、出库单与收款记录，说明集中开票的业务实质。",
            "发票行为", "发票-开票日期集中度", "RL-PTY-005", "date_concentration_top1_share", round(top1, 4),
        )
        # ★ 2026-09-28：逐条判定 RL-PTY-005 第③条要件（开票日期时点异常）
        _f["constituent_hits"] = [{
            "index": 3,
            "evidence": f"{len(dated)} 张已开票分布在 {len(by_day)} 个开票日，金额最大的 1 天占 {top1:.0%}、"
                        f"前 3 天占 {top3:.0%}——开票时点与正常业务节奏不符（是否与业务单据日期矛盾须进一步核对）",
        }]
        return [_f]
    return []


# ── 3) 免税额度临界卡位 ──
def _check_tax_free_threshold(sal):
    real = [i for i in sal if not _is_void_or_red(i)]
    if not real:
        return []
    rates = [r for r in (_rate(i) for i in real) if r is not None]
    # 仅在小规模纳税人（征收率≤3% 或 明确标注"小规模"）时套用免税额度口径，否则跳过
    is_small = False
    for i in real:
        cm = str(i.get("collect_method", i.get("征收方式", "")) or "")
        if any(k in cm for k in _SMALL_SCALE_KW):
            is_small = True
            break
    if not is_small and rates:
        is_small = all(r <= 0.03 + 1e-9 for r in rates)
    if not is_small:
        return []

    by_month = defaultdict(float)
    by_quarter = defaultdict(float)
    for i in real:
        d = _parse_date(i)
        if not d:
            continue
        y, m, _ = d
        amt = _amt(i)
        by_month[f"{y}-{m:02d}"] += amt
        by_quarter[f"{y}-Q{(m - 1) // 3 + 1}"] += amt

    if not by_month:
        return []

    findings = []
    # 3a) 月度：落在 [80%·10万, 10万) 的月份数
    near_cnt = sum(1 for v in by_month.values() if _VAT_FREE_MONTH * 0.8 <= v < _VAT_FREE_MONTH)
    edge_cnt = sum(1 for v in by_month.values() if _VAT_FREE_MONTH * 0.95 <= v < _VAT_FREE_MONTH)
    if near_cnt >= 3 or edge_cnt >= 2:
        findings.append(_mk(
            "待核事实：月度开票额长期卡在免税额度附近",
            "中风险", 6,
            f"按小规模纳税人月免税额度{_VAT_FREE_MONTH:,.0f}元口径，共有{near_cnt}个月的开票额落在"
            f"80%~100%区间（其中{edge_cnt}个月达到95%以上）。",
            "开票额长期贴着免税额度但不突破，需核实是否存在人为拆分收入、跨期调节或"
            "隐匿超出部分收入以持续享受免税政策的情形。",
            f"近{len(by_month)}个月中，{near_cnt}个月开票额位于免税额度80%~100%区间。",
            "如存在人为拆分或隐匿收入以规避纳税义务，将少缴增值税及附加税费。",
            "《增值税暂行条例》及小规模纳税人免税政策相关规定",
            "提供各月收入台账与客户明细，核实开票额与真实销售额的一致性。",
            "发票行为", "发票-免税额度临界", "RL-VAT-004", "tax_free_near_ratio", round(near_cnt / max(len(by_month), 1), 4),
        ))
    # 3b) 季度：落在 [80%·30万, 30万)
    q_near = sum(1 for v in by_quarter.values() if _VAT_FREE_QUARTER * 0.8 <= v < _VAT_FREE_QUARTER)
    if q_near >= 2 and not findings:
        findings.append(_mk(
            "待核事实：季度开票额卡在30万免税临界点",
            "中风险", 6,
            f"按小规模纳税人季度免税额度{_VAT_FREE_QUARTER:,.0f}元口径，共有{q_near}个季度的开票额落在"
            f"80%~100%区间。",
            "季度开票额持续卡在免税临界点以内，需核实是否存在按季拆分开票以持续适用免税政策。",
            f"{len(by_quarter)}个季度中，{q_near}个季度开票额位于24万~30万区间。",
            "人为拆分季度收入以规避纳税义务，将少缴增值税及附加税费。",
            "《增值税暂行条例》及小规模纳税人免税政策相关规定",
            "提供季度收入台账与客户明细，核实开票节奏与真实销售的匹配性。",
            "发票行为", "发票-免税额度临界", "RL-VAT-004", "tax_free_quarter_near_ratio", round(q_near / max(len(by_quarter), 1), 4),
        ))
    return findings


# ── 4) 个人抬头发票占比 ──
def _check_individual_buyer(pur):
    real = [i for i in pur if not _is_void_or_red(i)]
    if len(real) < 5:
        return []
    total = sum(_amt(i) for i in real)
    if total <= 0:
        return []
    indiv_amt = 0.0
    indiv_cnt = 0
    for i in real:
        b = _buyer(i)
        if not b:
            continue
        has_ent = any(k in b for k in _ENTERPRISE_KW)
        if (not has_ent) and not _buyer_tax(i):
            indiv_amt += _amt(i)
            indiv_cnt += 1
    share = indiv_amt / total
    if share >= _INDIV_BUYER_SHARE and indiv_cnt >= 3:
        return [_mk(
            "待核事实：进项发票中存在大量个人抬头",
            "中风险", 6,
            f"进项发票共{len(real)}张，其中{indiv_cnt}张购方名称为个人（无企业特征且无税号），"
            f"金额{indiv_amt:,.2f}元，占进项总额{total:,.2f}元的{share:.0%}。",
            "个人抬头的发票通常不得作为企业税前扣除凭证；大量个人抬头发票计入成本，"
            "可能指向凭证不合规、业务与经营无关或借票入账，需逐笔核实业务实质。",
            f"个人抬头进项金额 / 进项总额 = {share:.0%}（不低于30%）。",
            "不合规凭证对应的成本费用不得税前扣除，面临企业所得税纳税调增。",
            "《企业所得税税前扣除凭证管理办法》（国家税务总局公告2018年第28号）",
            "逐笔核实个人抬头发票对应的业务真实性及与生产经营的关联性，补充合规凭证或作纳税调增。",
            "成本费用", "发票-个人抬头占比", "RL-COST-003", "individual_buyer_share", round(share, 4),
        )]
    return []


# ── 5) 进项税额控制额异常（大额留抵/虚抵）──
def _check_input_tax_control(sal, pur):
    real_sal = [i for i in sal if not _is_void_or_red(i)]
    real_pur = [i for i in pur if not _is_void_or_red(i)]
    pur_tax = sum(_tax(i) for i in real_pur)
    sal_tax = sum(_tax(i) for i in real_sal)
    if pur_tax <= 0:
        return []
    if sal_tax <= 0:
        # 有进项无销项（税额口径）→ 交 false_invoice/RL-VAT-002 处理，避免重复
        return []
    ratio = pur_tax / sal_tax
    if ratio >= _INPUT_TAX_RATIO:
        lvl = "高风险" if ratio >= _MIN_MATCH_RATIO else "中风险"
        _f = _mk(
            "待核事实：进项税额长期大于销项税额",
            lvl, 8 if lvl == "高风险" else 6,
            f"进项税额合计{pur_tax:,.2f}元，销项税额合计{sal_tax:,.2f}元，"
            f"进项税额为销项税额的{ratio:.2f}倍，形成大额留抵。",
            "进项税额持续大于销项税额形成大额留抵，除重资产投入、出口企业等合理情形外，"
            "也可能指向虚抵进项、囤票或隐匿销售（有进无销），需结合存货与销售核实。",
            f"进项税额 / 销项税额 = {ratio:.2f}（阈值1.5倍）。",
            "虚抵进项或隐匿销项将少缴增值税，并可能触发进项税额转出与滞纳金。",
            "《增值税暂行条例》第八条、第九条（进项税额抵扣与不得抵扣情形）",
            "核实大额留抵的成因（存货积压/在建工程/出口），提供存货与销售台账佐证进销匹配。",
            "增值税", "发票-进项税额控制额", "RL-VAT-002", "input_output_tax_ratio", round(ratio, 4),
        )
        # ★ 2026-09-28：逐条判定 RL-VAT-002 第②条要件（无对应销项实现的进项税额）
        _f["constituent_hits"] = [{
            "index": 2,
            "evidence": f"进项税额 {pur_tax:,.2f} 元持续大于销项税额 {sal_tax:,.2f} 元（{ratio:.2f} 倍），"
                        f"形成大额留抵——是否存在对应销项实现须结合存货与销售台账核实",
        }]
        return [_f]
    return []


# ── 6) 同一对方同金额多张发票（拆分开票/重复开具）──
def _check_same_pair_amount(sal):
    real = [i for i in sal if not _is_void_or_red(i)]
    groups = defaultdict(list)
    for i in real:
        b = _buyer(i)
        a = round(_amt(i), 2)
        if not b or a <= 0:
            continue
        groups[(b, a)].append(i)

    hits = []
    for (b, a), items in groups.items():
        if len(items) < _SAME_PAIR_COUNT:
            continue
        # 时间窗内判定：取最早日期起 _SAME_PAIR_WINDOW 天内的张数
        dated = sorted([(_parse_date(i), i) for i in items if _parse_date(i)],
                       key=lambda x: (x[0][0], x[0][1], x[0][2]))
        in_window = len(items)
        if dated:
            import datetime as _dt
            first = _dt.date(*dated[0][0])
            in_window = 0
            for d, _ in dated:
                cur = _dt.date(*d)
                if (cur - first).days <= _SAME_PAIR_WINDOW:
                    in_window += 1
        if in_window >= _SAME_PAIR_COUNT:
            hits.append((b, a, in_window))
    if not hits:
        return []
    hits.sort(key=lambda x: -x[2])
    parts = "、".join(f"{b}：{a:,.2f}元×{c}张" for b, a, c in hits[:3])
    maxc = hits[0][2]
    return [_mk(
        "待核事实：同一客户存在多张同额发票",
        "中风险", 6,
        f"共有{len(hits)}组'同一客户+同一金额'的发票（组内≥{_SAME_PAIR_COUNT}张），"
        f"例如：{parts}。",
        "向同一客户短期内开具多张金额完全一致的发票，常见于将同一笔业务拆分开票、"
        "重复开具或为匹配额度人为拆单，需核实是否为真实多笔交易。",
        f"按'购方+金额'聚合，{len(hits)}组在{_SAME_PAIR_WINDOW}天内出现≥{_SAME_PAIR_COUNT}张同额发票。",
        "拆分开票或重复开票可能造成收入虚增或发票管理违规，影响增值税与所得税计缴。",
        "《发票管理办法》关于如实开具发票、不得拆分或重复开具的规定",
        "提供这些同额发票对应的合同、订单与出库记录，核实是否为独立真实交易。",
        "发票行为", "发票-同额重复开票", "RL-PTY-005", "same_pair_amount_groups", len(hits),
    )]


# ── 7) 跨年度红冲大额发票 ──
def _check_cross_year_red(sal, pur):
    red = [i for i in (list(sal) + list(pur)) if _is_void_or_red(i)
           and ("红" in _inv_type(i) or "冲" in _inv_type(i))]
    if not red:
        return []
    hits = []
    for i in red:
        d = _parse_date(i)
        if not d or _amt(i) < _CROSS_YEAR_AMT:
            continue
        hits.append((d, _amt(i), _inv_type(i)))
    if not hits:
        return []
    total = sum(a for _, a, _ in hits)
    _f = _mk(
        "待核事实：存在大额红冲/红字发票",
        "中风险", 6,
        f"检测到{len(hits)}张金额较大的红冲/红字发票，合计红冲金额约{total:,.2f}元。",
        "大额红冲若无对应退货、折让或开票有误等合理依据，可能被用于跨期调节收入、"
        "冲减上年度利润或规避纳税义务；若发生在汇算清缴后跨年度红冲上年度发票，更需核实依据。",
        f"红冲/红字发票中，金额≥{_CROSS_YEAR_AMT:,.0f}元的共{len(hits)}张，合计{total:,.2f}元。",
        "无合理依据的大额跨期红冲可能造成收入期间错配、少缴增值税与企业所得税。",
        "《发票管理办法》及红字发票开具相关规定；《企业所得税法》关于收入确认期间的规定",
        "逐笔提供红冲原因（退货/折让/开票有误）、原发票信息及对应会计处理，核实红冲依据充分性。",
        "发票行为", "发票-大额红冲", "RL-VAT-007", "large_red_invoice_count", len(hits),
    )
    # ★ 2026-09-27（A 收敛）：本判定归属 RL-VAT-007 第 ⑤ 条要件（大额红冲）
    _f["constituent_hits"] = [{
        "index": 5,
        "evidence": f"大额红冲 {len(hits)} 张、合计 {total:,.2f} 元（单张 ≥ {_CROSS_YEAR_AMT:,.0f} 元）",
    }]
    return [_f]


def detect_invoice_patterns(sal_invs, pur_invs, ctx=None, tax_declarations=None):
    """发票开票行为类待核线索探测器主入口。

    Args:
        sal_invs: 销项发票列表（dict，含 date/inv_type/buyer/amount/tax 等键）
        pur_invs: 进项发票列表
        ctx: AuditContext（可选，仅作扩展预留）
        tax_declarations: 纳税申报表（可选，暂未消费，预留）
    Returns: findings list（每项带 redline_id）
    """
    sal = sal_invs or []
    pur = pur_invs or []
    if not sal and not pur:
        return []
    findings = []
    for _fn in (
        lambda: _check_month_end(sal),
        lambda: _check_date_concentration(sal),
        lambda: _check_tax_free_threshold(sal),
        lambda: _check_individual_buyer(pur),
        lambda: _check_input_tax_control(sal, pur),
        lambda: _check_same_pair_amount(sal),
        lambda: _check_cross_year_red(sal, pur),
    ):
        try:
            findings.extend(_fn() or [])
        except Exception:
            # 单项失败不影响其它项（与主分析解耦）
            continue
    return findings

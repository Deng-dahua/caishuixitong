from engine.numparse import to_number, amount_of  # ★ 2026-09-25 统一数值解析（唯一实现）
"""外部数据核验待办探测器 —— 把"单账套判不了、需外部数据"的风险项转化为可执行待核清单。

背景：金税四期的一批能力（开票 IP/MAC、企业注册/注销时间、实缴资本、参保人数、
法人户籍、实名办税、领票增量/走逃、海关报关与收汇、地下钱庄等）依赖税务端全国数据池
与跨部门共享；本系统是企业/稽查端、单账套，**拿不到这些外部数据**。

正确做法（遵循"无数据→置疑清单并列明需补资料"铁律）：当账内出现对应信号时，
不臆断结论，而是产出「需外部数据/资料核验」的待核项，明确列出需补什么。
本模块即承担这一职责——把"做不了"变成"明确告诉用户还需核验什么"。

铁律：仅在账内出现对应信号时输出；无信号不输出；绝不代替主管机关定性。
"""

# 各外部核验项的最贴近红线（措辞均为"需外部核验"，与实质红线发现区分，不重复定性）
_RID_SUPPLIER = "RL-PTY-002"   # 供应商高度集中且地域异常
_RID_FUND = "RL-FUND-001"      # 公转私/个人卡
_RID_CROSS = "RL-PTY-004"      # 订单-投料-完工-发货-收入闭环（含跨境物流）
_RID_EXPORT = "RL-SPT-008"     # 出口退税四单匹配
_RID_RELATED = "RL-CIT-001"    # 关联交易异常
_RID_INCENTIVE = "RL-SPT-011"  # 核定/优惠资格

# ★ 逐条判定：每个外部核验待办对应的「触发要件」序号（命中红线定义的第几条构成要件）。
#   外部核验项本身只确认"账内出现了需外部数据佐证的信号"，该信号即对应红线的某一构成要件；
#   指标值随证据一并回传，供报告"一、涉及的风险事项"标注（本企业：证据）。
_REMINDER_HIT_INDEX = {
    _RID_SUPPLIER: 2,    # RL-PTY-002 ② 前三大供应商占比较高/单一外省供应商占比较高
    _RID_FUND: 1,        # RL-FUND-001 ① 公司账户向股东/法定代表人/其亲属个人账户转账情形
    # ★ 2026-10-02（用户复核疑点5：宁缺勿错）—— **本项不认领任何要件**（index=None）。
    #   它真正算过的只有「既为供应商又为客户的主体 N 家」(=购销闭环雏形)，而
    #   RL-CIT-001 的①是「人员(六员)/地址/电话/账户重叠」、②是「购销占比超行业基准」、
    #   ④是「未准备同期资料」——这三条本项**一条都没核算**，认领①属虚认：
    #   报告会出现「认下第①条要件」却拿不出六员/地址/电话证据的假闭环。
    #   故如实留空：本项只报账内信号，是否落到哪条要件由要件核对表按真实数据源判。
    _RID_RELATED: None,
    _RID_CROSS: 1,       # RL-PTY-004  ① 订单-投料-完工-发货-收入数量闭环断裂
    _RID_EXPORT: 1,      # RL-SPT-008  ① 报关单/提单/收汇/生产四单未匹配
    _RID_INCENTIVE: 1,   # RL-SPT-011  ① 核定/优惠资格缺少支撑资料
}


# ★ 2026-10-02（用户复核疑点5）：**外部核验项该挂哪些原始行**的采样口径表（数据表驱动）。
#
#   事故：外部核验待办项原先没有自己的明细口径，由 pipeline 的「通用关键词兜底」按关键词
#   抓行拼表 —— 实测「需外部数据核验：关联交易的同期资料与关联申报（共8笔）」挂上去的是
#   「全年最大额银行流水 4 行 + 0 元高频交易对方 4 行」，表题与内容完全错位。
#   根因：**按词猜证据**。关键词「银行」来自该发现自身文案里"依赖工商/税务/海关/…/银行等"
#   这句说明，与"同期资料"毫无关系；「供应商」来自 detail。
#
#   修法：由本模块（最懂自身语义的一方）按 indicator 声明**采样分支 + 过滤条件**，
#   pipeline 只负责按分支取行（证据行格式仍由 pipeline 唯一生成，不在此另造一份）。
#   ⇒ 新增外部核验项时只需在 `_EXT_SAMPLE_BRANCH` 加一行，不必改 pipeline 采样逻辑。
#   分支语义（全部行业/企业通用）：
#     top_pur_invoices     —— 去向上"进"侧金额最大的若干张发票
#     entity_bank_txs      —— 对手方落在 `entities` 集合内的银行流水（个人往来户）
#     keyword_invoices     —— 品名命中关键字（本项业务特征词）的销项发票
#     entity_invoices      —— 对手方落在 `entities` 集合内的发票（本项真正锁定的主体）
_EXT_SAMPLE_BRANCH = {
    "ext_supplier_verify": {
        "branch": "top_pur_invoices", "limit": 5,
    },
    "ext_personal_payee_verify": {
        # 不是"金额最大的银行流水"，而是**对手方为个人账户**的那几笔
        "branch": "entity_bank_txs", "limit": 5,
    },
    "ext_export_docs_verify": {
        "branch": "keyword_invoices", "limit": 5,
        "keyword": "出口,离岸,境外,报关,FOB,CIF",
    },
    "ext_related_party_docs_verify": {
        "branch": "entity_invoices", "limit": 8,
    },
}


def _top_supplier_name(sellers):
    """金额最大的那家供应商的名称（取不到则空串——取不到就不声明实体过滤，不编造）。"""
    try:
        return max((sellers or {}).items(), key=lambda kv: kv[1])[0]
    except (TypeError, ValueError):
        return ""


def _personal_counterparties(bank):
    """银行流水中**对手方像个人账户**的户名清单（企业特征词一个都没命中即判个人户）。

    ★ 取不到就不返回，绝不的默认套"所有对手方"——与"缺失≠0"同一条铁律。
    """
    ent_kw = ("公司", "厂", "店", "中心", "部", "行", "社", "院", "所", "有限", "企业", "合作")
    names = []
    for t in (bank or []):
        cp = str((t or {}).get("counterparty", "") or "").strip()
        if cp and not any(k in cp for k in ent_kw) and cp not in names:
            names.append(cp)
    return names


def _safe(v):
    """数值解析（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/numparse.py（唯一权威）。
      原私有实现遇 "12,000.00" / "￥1,234.56" 等会静默返回 0，
      导致同一金额在不同模块被算成不同值（报告自相矛盾 / 规则漏触发）。
    """
    from engine.numparse import to_number as _to_number
    return _to_number(v)


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


def _reminder(name, detail, why, materials, redline_id, indicator, value, entities=None):
    _d = {
        "type": f"需外部数据核验：{name}",
        # 等级原为未登记值"提示"（会被静默丢弃）；权威词表的"待核验"才是本义
        "level": "待核验",
        "score": 3,
        "detail": detail,
        "description": why + " 本项依赖外部数据（工商/税务/海关/银行等），系统在单账套内无法单独判定，"
                             "仅列为待核事项。",
        "how_found": detail,
        "tax_impact": "如外部数据核实后确认存在违规，可能涉及补税、滞纳金及处罚；本项不作定性。",
        "policy_ref": "《税收征收管理法》及相关部门数据共享规定",
        "suggestion": "需补充核验的资料：" + materials,
        "category": "外部核验",
        "source_chain": "外部数据核验待办",
        "redline_id": redline_id,
        "indicator": indicator,
        "indicator_value": value,
    }
    # ★ 逐条判定：把"账内出现的触发信号"对应到红线第几条构成要件，作为（本企业：证据）回传
    _idx = _REMINDER_HIT_INDEX.get(redline_id)
    if _idx:
        _ev = detail
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            _ev = f"{detail}（指标值：{value}）"
        _d["constituent_hits"] = [{"index": _idx, "evidence": _ev}]
    # ★ 2026-10-02：声明本项的**证据行采样口径**（pipeline 据此取行，不走关键词兜底）。
    #   `entities` 是本项真正锁定的交易主体，供 "entity_invoices" 分支过滤用。
    _scope = dict(_EXT_SAMPLE_BRANCH.get(indicator) or {})
    if _scope.get("branch"):
        _scope["entities"] = [str(e).strip() for e in (entities or []) if str(e).strip()]
        _d["evidence_scope"] = _scope
    return _d


def build_external_check_reminders(sal_invs, pur_invs, bank_txs, bs, income, ctx=None):
    """产出"需外部数据核验"待核清单（仅在账内有对应信号时）。"""
    findings = []
    sal = sal_invs or []
    pur = pur_invs or []
    bank = bank_txs or []

    # ── 1) 供应商外部核验：供应商集中 / 名称缺失或雷同 ──
    # ★★ 2026-10-03（用户："疑点24 供应商集中度与地域分布缺乏商业合理性……
    #   你也必须充分证据证明到底是怎么缺乏商业合理性！！！！"）
    #   **根因：量纲错误（百分数 vs 小数）** —— `ctx.supplier_concentration` 是**百分数**
    #   （phase1_triage 写入 `top3_pct`，行业预警阈值也是 80），而这里曾用 `conc >= 0.6`
    #   （**小数**阈值）比较 ⇒ `33.45 >= 0.6` **恒真** ⇒ **任何企业都会命中"供应商高度集中"**。
    #   实测公司1：真实供应商 374 家、CR1 11.75%、CR3 33.68%，是**极其分散**，
    #   报告却写"供应商高度集中"——结论与事实完全相反。
    #   现统一走唯一权威 `engine/supplier_stats.supplier_concentration`（同一口径、同一量纲），
    #   并**只有判定为"集中"时才产出本项**；措辞直接来自统计（数值与文字一致）。
    from engine.supplier_stats import supplier_concentration as _sup_conc, DEFAULT_WARN_PCT as _WARN
    _home = None
    _ind = None
    try:
        if ctx is not None:
            _home = getattr(ctx, "home_province", None) or None
            # ★ 行业用于"成本类采购"筛选（供应商＝与主营业务成本相关的采购；
            #   期间费用类对手方不是"供应商"——见 supplier_stats 模块头注释）
            _ip = getattr(ctx, "industry_profile", None)
            if isinstance(_ip, dict):
                _ind = _ip.get("industry") or _ip.get("industries") or _ip.get("name")
            if not _ind:
                _cp = getattr(ctx, "company_profile", None)
                if isinstance(_cp, dict):
                    _ind = _cp.get("industry") or _cp.get("industry_resolved")
    except Exception:
        _home = _home or None
    _stat = _sup_conc(pur, home_province=_home, industry=_ind)
    if _stat["verdict"] == "集中":
        _warn = _WARN
        _ip_thr = None
        try:
            if ctx is not None and isinstance(getattr(ctx, "industry_profile", None), dict):
                _ip_thr = (ctx.industry_profile.get("benchmarks") or {}).get("supplier_concentration_warn")
        except Exception:
            _ip_thr = None
        if isinstance(_ip_thr, (int, float)) and _ip_thr > 0:
            _warn = float(_ip_thr)          # 行业自适应阈值（同为百分数）
        if _stat["cr3"] >= _warn:
            findings.append(_reminder(
                "供应商工商登记与开票环境",
                _stat["note"],
                "供应商集中时，需核实前几家是否为真实经营主体（成立时间、实缴资本、参保人数、"
                "注册地址、是否为走逃/非正常户、开票IP/MAC是否与本企业或关联企业雷同）。",
                "供应商营业执照/工商信息、参保人数、注册时间与实缴资本、开票环境信息。",
                _RID_SUPPLIER, "ext_supplier_verify", round(_stat["cr3"] / 100.0, 4),
                entities=_stat["top_names"][:1],
            ))

    # ── 2) 资金流实名核验：存在对私/公转私 ──
    has_personal = bool(getattr(ctx, "has_personal_payments", False)) if ctx else False
    if not has_personal:
        # 兜底：从银行流水对手方名称粗判（个人户名通常无企业特征），需金额达阈值
        ent_kw = ("公司", "厂", "店", "中心", "部", "行", "社", "院", "所", "有限", "企业", "合作")
        pers_amt = 0.0
        for t in bank:
            cp = str((t or {}).get("counterparty", "") or "")
            if cp and not any(k in cp for k in ent_kw):
                pers_amt += _safe((t or {}).get("debit", 0)) + _safe((t or {}).get("credit", 0))
        has_personal = pers_amt >= 100000
    if has_personal and bank:
        findings.append(_reminder(
            "对私资金往来对象实名与性质",
            "账面存在与个人账户的资金往来记录。",
            # 证据行只取**对手方确为个人户**的那几笔，不是"全年金额最大的银行流水"
            "对私大额/频繁往来需核实收款账户实名（是否为本企业股东、员工或其亲属）、"
            "款项性质（货款/借款/分红/工资）及是否存在资金回流闭环，避免账外经营与个税风险。",
            "对私收付款的账户实名信息、合同/借款/分红决议、回流路径核查说明。",
            _RID_FUND, "ext_personal_payee_verify", None,
            entities=_personal_counterparties(bank),
        ))

    # ── 3) 出口业务报关与收汇核验 ──
    goods_txt = " ".join(str((i or {}).get("goods", (i or {}).get("货物或应税劳务名称", "")) or "") for i in (sal + pur))
    if any(k in goods_txt for k in ("出口", "离岸", "境外", "报关", "FOB", "CIF")):
        findings.append(_reminder(
            "出口报关单与收汇匹配",
            "发票品名中出现出口/报关/境外相关字样。",
            "出口业务需核实报关单、提单、收汇与生产能力是否匹配（四单一致），"
            "防止买单配票、低值高报、虚假结汇。",
            "出口报关单、提单/运单、结汇水单、生产与产能证明。",
            _RID_EXPORT, "ext_export_docs_verify", None,
            # 证据行取品名含出口特征的发票（分支自带 keyword，实体留空）
        ))

    # ── 5) 关联交易/跨境同期资料核验 ──
    if pur or sal:
        common = {_seller(i) for i in pur} & {_buyer(i) for i in sal}
        common.discard("")
        if common:
            findings.append(_reminder(
                "关联交易的同期资料与关联申报",
                f"发现既为供应商又为客户的主体{len(common)}家，存在关联交易迹象。",
                "关联交易需按独立交易原则定价并准备同期资料（主体/本地/特殊事项文档）、"
                "按期完成关联申报；跨境关联交易还涉及受益所有人、特许权使用费等。",
                "关联关系认定资料、关联申报表、同期资料文档、定价可比性分析。",
                _RID_RELATED, "ext_related_party_docs_verify", len(common),
                # ★ 证据行只挂**这些既购又销主体**的实际购销发票，不再挂"最大额银行流水"
                entities=sorted(common),
            ))

    return findings


def detect_external_checks(sal_invs, pur_invs, bank_txs, bs=None, income=None, ctx=None):
    try:
        return build_external_check_reminders(sal_invs, pur_invs, bank_txs, bs, income, ctx) or []
    except Exception:
        return []

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


def _safe(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _buyer(inv):
    return str((inv or {}).get("buyer", (inv or {}).get("购方名称", "")) or "").strip()


def _seller(inv):
    return str((inv or {}).get("seller", (inv or {}).get("销方名称", "")) or "").strip()


def _reminder(name, detail, why, materials, redline_id, indicator, value):
    return {
        "type": f"需外部数据核验：{name}",
        "level": "提示",
        "score": 3,
        "detail": detail,
        "description": why + " 本项依赖外部数据（工商/税务/海关/公安/银行等），系统在单账套内无法单独判定，"
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


def build_external_check_reminders(sal_invs, pur_invs, bank_txs, bs, income, ctx=None):
    """产出"需外部数据核验"待核清单（仅在账内有对应信号时）。"""
    findings = []
    sal = sal_invs or []
    pur = pur_invs or []
    bank = bank_txs or []

    # ── 1) 供应商外部核验：供应商集中 / 名称缺失或雷同 ──
    sellers = {}
    for i in pur:
        s = _seller(i)
        if s:
            sellers[s] = sellers.get(s, 0.0) + abs(_safe((i or {}).get("amount", (i or {}).get("金额", 0))))
    pur_total = sum(sellers.values())
    if pur_total > 0 and sellers:
        top = max(sellers.values()) / pur_total
        conc = getattr(ctx, "supplier_concentration", None) if ctx else None
        if (len(sellers) >= 4 and top >= 0.6) or (isinstance(conc, (int, float)) and conc >= 0.6):
            findings.append(_reminder(
                "供应商工商登记与开票环境",
                f"对最大供应商的采购占进项总额约{top:.0%}，供应商高度集中。",
                "供应商高度集中时，需核实其是否为真实经营主体（成立时间、实缴资本、参保人数、"
                "注册地址、是否为走逃/非正常户、开票IP/MAC是否与本企业或关联企业雷同）。",
                "供应商营业执照/工商信息、参保人数、注册时间与实缴资本、开票环境信息。",
                _RID_SUPPLIER, "ext_supplier_verify", round(top, 4),
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
            "对私大额/频繁往来需核实收款账户实名（是否为本企业股东、员工或其亲属）、"
            "款项性质（货款/借款/分红/工资）及是否存在资金回流闭环，避免账外经营与个税风险。",
            "对私收付款的账户实名信息、合同/借款/分红决议、回流路径核查说明。",
            _RID_FUND, "ext_personal_payee_verify", None,
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
            ))

    return findings


def detect_external_checks(sal_invs, pur_invs, bank_txs, bs=None, income=None, ctx=None):
    try:
        return build_external_check_reminders(sal_invs, pur_invs, bank_txs, bs, income, ctx) or []
    except Exception:
        return []

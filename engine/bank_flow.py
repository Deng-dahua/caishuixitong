"""资金流（银行流水）比对引擎 —— 第四阶 P0 能力。

背景：数电票 + 申报自动预填 + 一窗式比对下，"已开票未申报"差异已被税局系统焊死，
财务不会、也不敢手动砍已开票收入。真正暴露税收违法的是**资金流**：
私户收款、未开票收入、与关联方的资金回流闭环。银行流水也是风险检查必收资料。

本模块作为独立 capability（与 external_verifier 同构），对照"申报收入/开票额"
量化银行流水的异常敞口，输出 comprehensive["bank_flow"]。

输入：
  bank_txs        : pipeline 已标准化的银行流水列表（credit/debit 为 float，
                    counterparty/date/summary/account 为 str）
  sal_invs        : 销项发票列表（含 amount 字段）
  pur_invs        : 进项发票列表（可选，暂未用）
  reported_income : 增值税申报表销售额合计（优先）；None 时回退开票额
  invoice_total   : 销项发票额合计（可选，自动从 sal_invs 计算）
  cross_enterprise: comprehensive["cross_enterprise"]（用于资金回流闭环）
  company_name    : 企业名称

输出：与 external_verifier 对齐的 dict（available/summary/body/metrics/signals/verdict...）。
"""
import time
from collections import defaultdict


# 公司户识别关键词（命中即视为对公/单位户，排除私户）
_CORP_KW = (
    "公司", "有限公司", "有限责任公司", "厂", "店", "商行", "部", "局", "行", "院",
    "所", "中心", "集团", "合伙", "事务所", "超市", "科技", "技术", "贸易", "实业",
    "供应链", "物流", "建材", "股份", "责任", "银行", "证券", "保险", "基金", "协会",
    "合作社", "学校", "医院", "政府", "村委会", "居委会", "委员会", "企业", "百货",
    "商城", "市场", "餐饮", "酒店", "宾馆", "俱乐部", "门诊", "诊所",
)

# 第三方支付平台关键词（支付宝/微信/财付通等）
_THIRD_PARTY_KW = ("支付宝", "微信", "财付通", "个人码", "二维码", "云闪付", "聚合支付")

# 明显非销售类流入关键词（借款/退税/利息/投资/工资等），仅用于说明敞口口径
_NONSALES_KW = (
    "税款", "税局", "税务", "国库", "利息", "贷款", "借款", "还款", "投资", "注资",
    "股东", "分红", "工资", "社保", "公积金", "报销", "退汇", "退回", "退款", "保证金",
    "押金", "代付", "代收", "往来款", "备用金", "提现", "取现", "结汇", "购汇", "兑换",
    "电费", "水费", "话费",
)


def _is_corporate(name):
    if not name:
        return False
    return any(k in name for k in _CORP_KW)


def _is_third_party(name, summary):
    hay = (name or "") + " " + (summary or "")
    return any(k in hay for k in _THIRD_PARTY_KW)


def _is_personal(name):
    """粗略判断是否为个人户（私户/个人码）。公司户与第三方平台已排除。"""
    if not name:
        return False
    if _is_corporate(name):
        return False
    if _is_third_party(name, ""):
        return False
    stripped = name.replace("·", "").replace(" ", "")
    if len(stripped) <= 4:
        return True
    if len(stripped) <= 6 and not any(k in name for k in ("公司", "厂", "店", "部", "局", "行", "院", "所", "中心")):
        return True
    return False


def _safe(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def _invoice_total(sal_invs):
    if not sal_invs:
        return 0.0
    tot = 0.0
    for i in sal_invs:
        tot += _safe(i.get("amount") or i.get("金额") or i.get("taxable_amount") or i.get("sales_amount"))
    return tot


def _sal_buyers(sal_invs):
    s = set()
    for i in sal_invs or []:
        b = str(i.get("buyer", i.get("购方", i.get("购买方", ""))) or "").strip()
        if b:
            s.add(b)
    return s


def run_bank_flow_compare(bank_txs, sal_invs=None, pur_invs=None,
                          reported_income=None, invoice_total=None,
                          cross_enterprise=None, company_name=""):
    """对照申报收入/开票额，量化银行流水的异常敞口。返回与 external_verifier 对齐的 dict。"""
    if not bank_txs:
        return {
            "available": False,
            "ok": True,
            "title": "银行流水（资金流）比对",
            "summary": "本轮未提供银行流水。",
            "body": "银行流水（资金流）是数电票时代暴露账外经营、私户收款、未开票收入的核心依据，"
                    "也是风险检查必收资料。未提供则无法做资金流比对，属系统能力边界内的待补强项。",
            "metrics": {},
            "signals": [],
            "verdict": "未提供银行流水",
            "recommendation": "上传企业基本户/一般户银行流水（含交易日期、对方户名、借贷金额、摘要），"
                              "系统将自动比对资金流与申报收入，量化未开票敞口与私户收款。",
            "note": "银行流水比对结论属「待证线索」，需逐笔核实交易背景，不作为定性依据。",
        }

    flow_receipt = 0.0
    flow_pay = 0.0
    corporate_receipt = 0.0
    personal_receipt = 0.0
    third_party_receipt = 0.0
    nonsales_receipt = 0.0
    personal_detail = defaultdict(float)
    third_detail = []
    payers = defaultdict(float)  # 收款方汇总（与开票客户匹配/资金回流）

    for tx in bank_txs:
        credit = _safe(tx.get("credit"))
        debit = _safe(tx.get("debit"))
        cp = str(tx.get("counterparty", "") or "").strip()
        summary = str(tx.get("summary", "") or "").strip()
        if credit > 0:
            flow_receipt += credit
            payers[cp] += credit
            if _is_third_party(cp, summary):
                third_party_receipt += credit
                if len(third_detail) < 12:
                    third_detail.append(f"{tx.get('date','')} {cp[:18]} {credit:,.2f}（{summary[:20]}）")
            elif _is_corporate(cp):
                corporate_receipt += credit
            elif _is_personal(cp):
                personal_receipt += credit
                personal_detail[cp[:18]] += credit
            # 非销售类流入单独累计，仅用于说明敞口口径
            if any(k in (cp + summary) for k in _NONSALES_KW):
                nonsales_receipt += credit
        if debit > 0:
            flow_pay += debit

    inv_total = _safe(invoice_total) if invoice_total is not None else _invoice_total(sal_invs)
    buyers = _sal_buyers(sal_invs)
    matched_receipt = sum(v for k, v in payers.items() if k in buyers)
    unmatched_corporate_receipt = max(corporate_receipt - matched_receipt, 0.0)

    # 申报侧：优先 reported_income（增值税申报表销售额），否则开票额代理
    reported_val = _safe(reported_income)
    has_decl = (reported_income is not None and reported_val > 0)
    declared = reported_val if has_decl else inv_total
    declared_source = "增值税申报表销售额" if has_decl else "销项发票额（数电票下≈申报销项，未含已申报未开票收入）"

    # 未开票/账外敞口：流水收款 − 申报侧
    gap = flow_receipt - declared
    gap_after_nonsales = flow_receipt - nonsales_receipt - declared

    # 资金回流闭环（结合跨企业图谱）
    circular_amount = 0.0
    circular_detail = []
    ce = cross_enterprise or {}
    rels = ce.get("relationships") or [] if isinstance(ce, dict) else []
    if rels:
        related_names = set()
        for rel in rels:
            for key in ("counterparty", "related_name", "name", "other_company"):
                nm = str(rel.get(key, "") or "").strip()
                if nm:
                    related_names.add(nm)
        for nm in related_names:
            recv = payers.get(nm, 0.0)
            paid = 0.0
            for tx in bank_txs:
                if str(tx.get("counterparty", "") or "").strip() == nm and _safe(tx.get("debit")) > 0:
                    paid += _safe(tx.get("debit"))
            if recv > 0 and paid > 0:
                loop = min(recv, paid)
                circular_amount += loop
                if len(circular_detail) < 8:
                    circular_detail.append(f"{nm}：企业收{recv:,.2f}/付{paid:,.2f}（闭环{min(recv, paid):,.2f}）")

    # ── 信号与结论 ──
    signals = []
    sev_high = False
    sev_mid = False

    if declared > 0 and gap > 0:
        ratio = flow_receipt / declared if declared else 0
        if ratio >= 1.3 and gap >= 100000:
            sev_high = True
            signals.append({
                "signal": f"银行流水收款{flow_receipt:,.2f}元，是{declared_source}（{declared:,.2f}元）的{ratio:.2f}倍，敞口{gap:,.2f}元",
                "hint": "流水收款显著大于申报收入，存在大额未开票/账外收款嫌疑；需逐笔核实每笔收款的交易背景与对应发票。",
            })
        elif gap >= 50000:
            sev_mid = True
            signals.append({
                "signal": f"银行流水收款{flow_receipt:,.2f}元，高于{declared_source}（{declared:,.2f}元）约{gap:,.2f}元",
                "hint": "收款与申报存在差额，核查是否为已发生纳税义务但未开票/未申报的收入。",
            })

    if personal_receipt > 0:
        if personal_receipt >= 100000:
            sev_high = True
        else:
            sev_mid = True
        top_personal = sorted(personal_detail.items(), key=lambda x: -x[1])[:8]
        names = "、".join(f"{n}({a:,.2f})" for n, a in top_personal)
        signals.append({
            "signal": f"私户/个人收款合计{personal_receipt:,.2f}元（{len(personal_detail)}个个人付款方）",
            "hint": f"个人户收款疑为未开票经营收入或股东/个人往来；重点核实：{names}。须逐笔确认是否应申报增值税与企业所得税。",
        })

    if third_party_receipt > 0:
        sev_mid = True
        signals.append({
            "signal": f"支付宝/微信等第三方平台收款{third_party_receipt:,.2f}元",
            "hint": "第三方收款需逐笔匹配订单与发票；电商/平台型行业占比高属正常，但须确认每笔均有合规开票，防止账外经营。",
        })

    if corporate_receipt > 0 and buyers and unmatched_corporate_receipt / max(corporate_receipt, 1) > 0.7:
        sev_mid = True
        signals.append({
            "signal": f"对公收款中约{unmatched_corporate_receipt:,.2f}元来自销项发票未记载的付款方",
            "hint": "大量对公收款方不在已开票客户名单中，可能存在未开票对公销售，需逐户核实交易与发票。",
        })

    if circular_amount > 0:
        sev_high = True
        signals.append({
            "signal": f"与关联方存在资金回流闭环约{circular_amount:,.2f}元",
            "hint": "企业与关联方互有收付款，疑似资金空转/虚开回款；结合跨企业图谱核实业务真实性。",
        })

    if sev_high:
        verdict = "存在资金流与申报严重背离，须深入核实"
    elif sev_mid:
        verdict = "存在资金流异常，需逐笔核实"
    elif gap > 0:
        verdict = "资金流略高于申报，建议关注"
    else:
        verdict = "资金流与申报基本匹配"

    metrics = {
        "flow_receipt": round(flow_receipt, 2),
        "flow_pay": round(flow_pay, 2),
        "corporate_receipt": round(corporate_receipt, 2),
        "personal_receipt": round(personal_receipt, 2),
        "third_party_receipt": round(third_party_receipt, 2),
        "nonsales_receipt": round(nonsales_receipt, 2),
        "invoice_total": round(inv_total, 2),
        "reported_income": round(reported_val, 2) if has_decl else None,
        "declared_side": declared_source,
        "declared_value": round(declared, 2),
        "uninvoiced_gap": round(gap, 2),
        "uninvoiced_gap_after_nonsales": round(gap_after_nonsales, 2),
        "unmatched_corporate_receipt": round(unmatched_corporate_receipt, 2),
        "circular_amount": round(circular_amount, 2),
    }

    lines = []
    lines.append(f"资金流收款合计：{flow_receipt:,.2f}元（付款合计{flow_pay:,.2f}元）")
    lines.append(f"申报侧（{declared_source}）：{declared:,.2f}元")
    lines.append(f"未开票/账外敞口（收款−申报侧）：{gap:,.2f}元"
                 + (f"（剔除明显非销售流入后约{gap_after_nonsales:,.2f}元）" if nonsales_receipt > 0 else ""))
    lines.append(f"对公收款：{corporate_receipt:,.2f}元｜私户/个人收款：{personal_receipt:,.2f}元"
                 + (f"｜第三方平台收款：{third_party_receipt:,.2f}元" if third_party_receipt else ""))
    if unmatched_corporate_receipt > 0:
        lines.append(f"对公收款中来自非开票客户的金额：{unmatched_corporate_receipt:,.2f}元")
    if circular_amount > 0:
        lines.append("资金回流闭环：")
        lines.extend(f"  - {d}" for d in circular_detail)
    if third_detail:
        lines.append("第三方平台收款样例：")
        lines.extend(f"  - {d}" for d in third_detail)
    if personal_detail:
        lines.append("私户收款主要个人户：")
        for n, a in sorted(personal_detail.items(), key=lambda x: -x[1])[:8]:
            lines.append(f"  - {n}：{a:,.2f}元")
    body = "\n".join(lines)

    recommendation = ("系统已量化上述敞口。下一步：①逐笔核实敞口对应交易是否开票申报；"
                      "②私户收款区分经营收入与股东往来；③第三方收款匹配订单与发票；"
                      "④资金回流结合关联企业业务真实性核查。全部需人工取证与定性。")

    return {
        "available": True,
        "ok": True,
        "title": "银行流水（资金流）比对",
        "company": company_name,
        "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": f"银行流水收款{flow_receipt:,.2f}元 vs {declared_source}{declared:,.2f}元，"
                   f"未开票/账外敞口约{gap:,.2f}元；私户收款{personal_receipt:,.2f}元。"
                   + (f"资金回流闭环约{circular_amount:,.2f}元。" if circular_amount > 0 else ""),
        "body": body,
        "metrics": metrics,
        "signals": signals,
        "verdict": verdict,
        "recommendation": recommendation,
        "note": "本比对基于银行流水与申报/开票数据，属「待证线索」：流水收款含借款、往来、投资、退税等非销售流入，"
                "敞口需逐笔核实交易背景后认定；定性权在风险检查员。",
    }

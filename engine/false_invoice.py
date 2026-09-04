"""虚开风险网络 比对引擎 —— 第四阶 P1 能力。

背景：数电票下"票表比对"只校验"已开票 vs 已申报"，对"票真业务假"的虚开反而自动通过。
虚开的典型特征（需结合多源才能暴露）：
  1) 进销项严重背离（有销无进/有进无销，购销不匹配）；
  2) 集中顶额开票（少数客户/发票占绝大比例，贴近发票限额）；
  3) 资金回流闭环（货款回流至开票方/关联方，货物流转不实）；
  4) 供应商=客户 自循环（对开/环开发票）；
  5) 跨企业图谱高风险关联（同一控制人、共享人员）。

本模块作为独立 capability（与 bank_flow / two_tax_income / input_voucher 同构），
叠加跨企业图谱与资金流，输出 comprehensive["false_invoice"]。

输入：
  sal_invs        : 销项发票列表（含 buyer/amount/tax/invoice_no）
  pur_invs        : 进项发票列表（含 seller/amount/tax/invoice_no）
  cross_enterprise: comprehensive["cross_enterprise"]（关系图谱，可选）
  bank_txs        : 银行流水列表（用于资金回流闭环，可选）
  company_name    : 企业名称
"""

import time
from collections import defaultdict

# 进销背离阈值（倍数）
_IN_OUT_DEVIATE = 5.0
# 集中顶额：单一客户/单张发票占比
_TOP1_SHARE = 0.50
_TOP3_SHARE = 0.80


def _safe(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def _buyer(inv):
    return str(inv.get("buyer", inv.get("购方名称", inv.get("购买方名称", ""))) or "").strip()


def _seller(inv):
    return str(inv.get("seller", inv.get("销方名称", inv.get("销售方名称", ""))) or "").strip()


def _amount(inv):
    return _safe(inv.get("amount"))


def _simple_fund_loop(bank_txs):
    """轻量资金回流：同名对手方既收又付 → 闭环=min(收,付)。返回 (amount, parties)。"""
    recv = defaultdict(float)
    paid = defaultdict(float)
    for tx in (bank_txs or []):
        cp = str(tx.get("counterparty", "") or "").strip()
        if not cp:
            continue
        c = _safe(tx.get("credit"))
        d = _safe(tx.get("debit"))
        if c > 0:
            recv[cp] += c
        if d > 0:
            paid[cp] += d
    amount = 0.0
    parties = []
    for cp, r in recv.items():
        p = paid.get(cp, 0.0)
        if r > 0 and p > 0:
            loop = min(r, p)
            amount += loop
            if len(parties) < 10:
                parties.append(f"{cp}：收{r:,.2f}/付{p:,.2f}（闭环{loop:,.2f}）")
    return amount, parties


def run_false_invoice_check(sal_invs, pur_invs, cross_enterprise=None,
                             bank_txs=None, company_name=""):
    """叠加跨企业图谱与资金流，识别虚开特征。返回对齐 dict。"""
    if not sal_invs and not pur_invs:
        return {
            "available": False,
            "ok": True,
            "title": "虚开风险网络比对",
            "summary": "本轮未提供进/销项发票数据。",
            "body": "虚开（票真业务假）是数电票下票表比对自动放行的盲区，需结合进销项背离、"
                    "集中顶额开票、资金回流闭环与跨企业图谱才能暴露。未提供发票则无法量化。",
            "metrics": {},
            "signals": [],
            "verdict": "未提供发票数据",
            "recommendation": "上传销项发票、进项发票（含购销方名称、金额、税额、发票号码），"
                              "并提供银行流水与关联企业清单以做资金回流与图谱勾稽。",
            "note": "虚开风险比对结论属「待证线索」：虚开定性需公安/税务查实资金、货物流与业务真实性，"
                    "系统仅给出待核特征组合。",
        }

    sal = sal_invs or []
    pur = pur_invs or []
    sal_total = sum(_amount(i) for i in sal)
    pur_total = sum(_amount(i) for i in pur)

    # ── 1) 进销背离 ──
    deviate_signal = None
    if sal_total > 0 and pur_total > 0:
        ratio = sal_total / pur_total
        if ratio >= _IN_OUT_DEVIATE:
            deviate_signal = ("进销项严重背离", f"销项{sal_total:,.2f}元 / 进项{pur_total:,.2f}元 = {ratio:.1f}倍",
                              "销项远大于进项，购销不匹配，疑似无货虚开/空壳开票（贸易、制造企业应警惕）；"
                              "结合存货、运费与资金流核实货物是否真实流转。")
        elif pur_total / sal_total >= _IN_OUT_DEVIATE:
            deviate_signal = ("进销项严重背离", f"进项{pur_total:,.2f}元 / 销项{sal_total:,.2f}元 = {pur_total/sal_total:.1f}倍",
                              "大量采购无对应销售，疑似过票/空转；结合库存与下游销售核实。")

    # ── 2) 集中顶额开票（销项，剔除平台服务商后按真实客户集中度）──
    # 平台运营商（天猫/阿里妈妈等）是服务费收款方，非货物销售客户；
    # 服务费发票不得计入"客户集中度"，否则会把平台商误标为"前3大客户"、虚增占比（同源矛盾信息误标）。
    from engine.verified_rule_engine import _is_platform_operator
    top1_name = "（无真实货物销售客户，销项均为平台服务费）"
    top1_amt = 0.0
    cust = defaultdict(float)
    for i in sal:
        b = _buyer(i)
        a = _amount(i)
        if not b or _is_platform_operator(b):
            continue  # 跳过平台运营商（服务费收款方，非货物销售客户）
        cust[b] += a
        if a > top1_amt:
            top1_amt = a
            top1_name = b
    sal_total_real = sum(cust.values())  # 真实客户销项合计（已剔除平台服务商）
    top1_share = (top1_amt / sal_total_real) if sal_total_real else 0.0
    sorted_cust = sorted(cust.items(), key=lambda x: -x[1])
    top3_amt = sum(a for _, a in sorted_cust[:3])
    top3_share = (top3_amt / sal_total_real) if sal_total_real else 0.0

    # ── 3) 顶额凑数（大量同额发票）──
    # 按发票号去重后再统计金额频次：一张发票的多行明细不应被重复计数，
    # 否则行项金额一致会被误判为"多张同额发票"假阳性。要求≥3张不同发票金额一致。
    _inv_amt = {}
    for i in sal:
        a = round(_amount(i), 2)
        if a <= 0:
            continue
        _inv = str(i.get("invoice_no") or i.get("inv_no") or "").strip()
        if _inv:
            _inv_amt.setdefault(_inv, a)  # 同发票号取首次金额
        else:
            _inv_amt[f"_row_{id(i)}"] = a  # 无发票号按行计
    amt_cnt = defaultdict(int)
    for a in _inv_amt.values():
        amt_cnt[a] += 1
    same_amount_groups = sorted([(a, c) for a, c in amt_cnt.items() if c >= 3],
                                 key=lambda x: -x[1])[:5]

    # ── 4) 供应商=客户 自循环 ──
    sal_buyers = set(_buyer(i) for i in sal)
    pur_sellers = set(_seller(i) for i in pur)
    circ_names = sal_buyers & pur_sellers
    circ_names.discard("")
    circular_supplier_signal = None
    if circ_names:
        circular_supplier_signal = ("供应商=客户自循环", f"既是客户又是供应商：{'、'.join(list(circ_names)[:4])}",
                                     "同一主体既采购又销售，疑似对开/环开发票；结合资金流核实是否闭环回流。")

    # ── 5) 资金回流闭环 ──
    loop_amt, loop_parties = _simple_fund_loop(bank_txs)

    # ── 6) 跨企业图谱高风险关联 ──
    ce = cross_enterprise or {}
    high_risk_rel = ce.get("high_risk_relationships", 0) or 0
    rel_total = ce.get("total_relationships", 0) or 0

    # ── 信号与结论 ──
    signals = []
    sev_high = False
    sev_mid = False

    if deviate_signal:
        sev_high = True
        signals.append({"signal": f"{deviate_signal[0]}：{deviate_signal[1]}", "hint": deviate_signal[2]})

    if top1_share >= _TOP1_SHARE or top3_share >= _TOP3_SHARE:
        sev_high = True if top3_share >= _TOP3_SHARE else sev_mid
        signals.append({
            "signal": f"集中顶额开票：最大客户占{top1_share*100:.1f}%，前3大客户占{top3_share*100:.1f}%",
            "hint": f"少数客户集中开票（最大：{top1_name}），贴近发票限额的集中开票是虚开高发特征；"
                    "核实客户真实性、是否受票方关联及资金是否回流。",
        })

    if same_amount_groups:
        sev_mid = True
        parts = "、".join(f"{a:,.0f}元×{c}张" for a, c in same_amount_groups[:3])
        signals.append({
            "signal": f"存在大量同额发票：{parts}",
            "hint": "多张发票金额完全一致，疑似凑数/顶额开票；结合发票号码连号与开票日期核查。",
        })

    if circular_supplier_signal:
        sev_high = True
        signals.append({"signal": circular_supplier_signal[0] + "：" + circular_supplier_signal[1],
                        "hint": circular_supplier_signal[2]})

    if loop_amt > 0:
        sev_high = True
        signals.append({
            "signal": f"资金回流闭环约{loop_amt:,.2f}元",
            "hint": "企业与对手方互有收付款，货款疑似回流；结合货物流转核实业务真实性。" +
                    ("样例：" + "；".join(loop_parties[:3]) if loop_parties else ""),
        })

    if high_risk_rel > 0:
        sev_high = True
        signals.append({
            "signal": f"跨企业图谱发现{high_risk_rel}条高风险关联关系（共{rel_total}条）",
            "hint": "同一控制人/共享人员/共享上下游的关联企业网络，是虚开团伙常见结构；"
                    "结合资金流与货物流核实关联交易商业目的。",
        })

    if sev_high:
        verdict = "存在多项虚开特征组合，须重点核查业务真实性"
    elif sev_mid:
        verdict = "存在虚开相关线索，需进一步核实"
    else:
        verdict = "未触发明显虚开特征（仅代表本轮数据范围）"

    metrics = {
        "sales_total": round(sal_total, 2),
        "purchase_total": round(pur_total, 2),
        "in_out_ratio": round(sal_total / pur_total, 3) if pur_total else None,
        "top1_customer_share": round(top1_share, 4),
        "top3_customer_share": round(top3_share, 4),
        "same_amount_groups": len(same_amount_groups),
        "circular_supplier_count": len(circ_names),
        "fund_loop_amount": round(loop_amt, 2),
        "high_risk_relationships": high_risk_rel,
    }

    lines = []
    lines.append(f"销项总额：{sal_total:,.2f}元（{len(sal)}张）｜进项总额：{pur_total:,.2f}元（{len(pur)}张）")
    if deviate_signal:
        lines.append(f"进销背离：{deviate_signal[1]}")
    lines.append(f"客户集中度：最大{top1_share*100:.1f}%、前3占{top3_share*100:.1f}%（最大客户：{top1_name}）")
    if same_amount_groups:
        lines.append("同额发票：" + "、".join(f"{a:,.0f}元×{c}张" for a, c in same_amount_groups[:3]))
    if circ_names:
        lines.append(f"供应商=客户自循环：{'、'.join(list(circ_names)[:4])}")
    if loop_amt > 0:
        lines.append(f"资金回流闭环：{loop_amt:,.2f}元")
        for p in loop_parties[:4]:
            lines.append(f"  - {p}")
    if rel_total:
        lines.append(f"跨企业关联：共{rel_total}条（高风险{high_risk_rel}条）")
    body = "\n".join(lines)

    recommendation = ("系统已组合上述虚开特征。下一步：①核实进销匹配与存货/运费；②核查集中客户与资金回流；"
                      "③比对发票连号/同额与开票日期；④穿透关联企业同一控制人。虚开定性须由主管机关查实，"
                      "系统仅提供待核线索。")

    return {
        "available": True,
        "ok": True,
        "title": "虚开风险网络比对",
        "company": company_name,
        "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": f"销项{sal_total:,.2f}元 / 进项{pur_total:,.2f}元；"
                   + (f"进销背离×{metrics['in_out_ratio']}；" if metrics["in_out_ratio"] else "")
                   + (f"前3客户占{top3_share*100:.1f}%；" if top3_share else "")
                   + (f"资金回流{loop_amt:,.2f}元；" if loop_amt > 0 else "")
                   + (f"高风险关联{high_risk_rel}条。" if high_risk_rel else ""),
        "body": body,
        "metrics": metrics,
        "signals": signals,
        "verdict": verdict,
        "recommendation": recommendation,
        "note": "本比对基于进销项、资金流与跨企业图谱的多源勾稽，属「待证线索」：虚开定性需查实"
                "资金流、货物流与业务真实性，系统不替代主管机关认定。",
    }

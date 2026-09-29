# -*- coding: utf-8 -*-
"""顶额开票探测器（RL-VAT-004）——单张发票金额长期贴近发票版本限额。

## 为什么补（检出能力缺口）

`RL-VAT-004「顶额开票」`此前属"盲区"：无检测器、无兜底，只能靠 match_hints
文字软匹配碰运气 —— 即"算了也看不出来"。本模块给它一条**从发票数据算出来**的路。

## 判据（**存在即触发、不设张数门槛**；幅度只作证据）

金税四期把"顶额开票"列为虚开/套开的经典特征：受票方为凑抵扣额度，要求按发票版本
上限（万元 / 十万元 / 百万元 / 千万元版）**顶额开具**，单张金额长期贴近上限。

  单张发票"金额" ≥ 某版本上限 × `_NEAR` 且 ≤ 上限 → 视为"贴近限额（顶额开具）"。

版本上限按增值税发票版本惯例取 **金额(不含税)** 常用档：
  万元版 9,999.99 / 十万元版 99,999.99 / 百万元版 999,999.99 / 千万元版 9,999,999.99。
`_NEAR` 取 0.995（贴近上限 0.5% 以内）——**保守**，避免把普通发票误算成顶额。

## 铁律

只输出**可复算的数量事实**（几张、多少钱、贴近哪档上限），**不自动定性**；
无销项发票数据不输出（无资料→不产违规）。
"""

from engine.numparse import to_number  # ★ 统一数值解析（唯一权威）
from engine.fieldkit import buyer_name  # ★ 购方名称读取（唯一权威；禁止各自实现）

# 常用发票版本"金额"上限（不含税，元）
_LIMITS = (9999.99, 99999.99, 999999.99, 9999999.99)
# 贴近系数：金额 ≥ 上限×0.995 且 ≤ 上限，视为顶额（保守）
_NEAR = 0.995


def _inv_amount(inv):
    return to_number(inv.get("total", inv.get("amount", inv.get("je", 0))))


def _inv_no(inv):
    return str(inv.get("invoice_no") or inv.get("inv_no") or inv.get("number") or "").strip()


def _limit_of(amount):
    """返回该金额贴近的版本上限；不贴近任何档返回 0。"""
    for lim in _LIMITS:
        if lim * _NEAR <= amount <= lim:
            return lim
    return 0.0


def detect_invoice_limit_top(sal_invs, ctx=None):
    """扫描销项发票，检出「顶额开票」（RL-VAT-004）。返回发现列表（0 或 1 条）。"""
    sal = [i for i in (sal_invs or []) if isinstance(i, dict)]
    if not sal:
        return []
    hits = []
    for inv in sal:
        a = _inv_amount(inv)
        if a <= 0:
            continue
        lim = _limit_of(a)
        if lim:
            hits.append((inv, a, lim))
    if not hits:
        return []

    n = len(hits)
    amt_total = sum(a for _, a, _ in hits)
    top_inv, top_amt, top_lim = max(hits, key=lambda x: x[1])
    # 受票方分布（要件②：同一或少数受票方开具顶额发票）
    by_buyer = {}
    for inv, _, _ in hits:
        b = buyer_name(inv)
        if b:
            by_buyer[b] = by_buyer.get(b, 0) + 1
    same_buyer = {b: c for b, c in by_buyer.items() if c >= 2}

    # ── 逐要件判定（要件表唯一口径：RL-VAT-004.constituents）──
    _hits = [{"index": 1, "evidence":
              f"检出 {n} 张单张金额贴近发票版本限额的销项发票"
              f"（最高单张 {top_amt:,.2f} 元，贴近 {top_lim:,.2f} 元档上限），合计 {amt_total:,.2f} 元。"}]
    if same_buyer:
        _detail = "；".join(f"{b}（{c} 张顶额）" for b, c in list(same_buyer.items())[:5])
        _hits.append({"index": 2, "evidence": f"其中向同一受票方开具顶额发票≥2 张：{_detail}。"})

    return [{
        "type": "顶额开票：开票金额长期贴近发票限额",
        "level": "中风险",
        "score": 6,
        "redline_id": "RL-VAT-004",
        "constituent_hits": _hits,
        "detail": (f"销项发票中检出 {n} 张单张金额贴近发票版本上限"
                   f"（万元/十万元/百万元/千万元版）的顶额发票，合计 {amt_total:,.2f} 元。"),
        "description": (
            f"销项发票中有 {n} 张单张金额已贴近发票版本上限"
            f"（最高单张 {top_amt:,.2f} 元，贴近 {top_lim:,.2f} 元档），合计 {amt_total:,.2f} 元。"
            "开票金额长期贴近版本上限（顶额开具）是虚开、套开的常见特征："
            "受票方为凑足抵扣额度，常要求按上限开票。须结合是否有对应的大额交付、"
            "物流与收款证据判断其真实性。"),
        "tax_impact": "若顶额发票对应的货物或服务并未真实发生，涉及虚开增值税专用发票，"
                      "相关进项不得抵扣、成本不得税前扣除，并可能被追究行政乃至刑事责任。",
        "suggestion": "1）逐张核对顶额发票对应的合同、出库/交付单、物流单据与收款记录；"
                      "2）核实受票方与本企业是否存在真实业务；3）如为分批交付合并开票，"
                      "保留批次台账以便说明。",
        "category": "域13 发票深度",
    }]

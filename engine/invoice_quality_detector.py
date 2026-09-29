# -*- coding: utf-8 -*-
"""发票数据质量探测器（RL-PTY-005）——票面勾稽与票号重复。

## 为什么补（检出能力缺口）

`RL-PTY-005「发票数据质量异常」`此前属"盲区"：无检测器、无兜底，只能靠 match_hints
软匹配碰运气。本模块给它一条**从发票数据硬算**的路。

## 只做两条**客观可复算**的要件（其余要件不硬凑）

- 要件①【票号重复】同一发票号码在本期出现 ≥2 次 → 重复入账 / 一票多开嫌疑。
  （**不做"断号"**：作废、红冲、多开票点、多税号分别开票都会造成合法断号，
   属红线自身豁免情形，硬判断号会大面积误报。）
- 要件②【勾稽错误】票面「金额 + 税额 ≠ 价税合计」（容差 0.05 元）→ 票面关系错误。

## 铁律

只输出**可复算的数量事实**（哪几张票、差多少），**不自动定性**；
字段缺失不参与判定（取不到就不说），无发票数据不输出。
"""

# ★ 字段读取全部走唯一权威 engine.fieldkit（禁止各检测器自写 _amount/_tax/_total/_no）
from engine.fieldkit import amount, tax, total, invoice_no

# 勾稽容差（元）：覆盖分位四舍五入
_TOL = 0.05


def _scan(invs):
    """返回 (重复票号 dict, 勾稽错误 list)。"""
    dup = {}
    bad_math = []
    if not isinstance(invs, list):
        return dup, bad_math
    seen = {}
    for inv in invs:
        if not isinstance(inv, dict):
            continue
        no = invoice_no(inv)
        if no:
            seen[no] = seen.get(no, 0) + 1
        a, t, tt = amount(inv), tax(inv), total(inv)
        # 三值齐备才判勾稽（缺一不参与判定）
        if a > 0 and tt > 0 and abs(a + t - tt) > _TOL:
            bad_math.append({"no": no, "amount": a, "tax": t, "total": tt,
                             "diff": round(a + t - tt, 2)})
    dup = {no: c for no, c in seen.items() if c >= 2}
    return dup, bad_math


def detect_invoice_quality(sal_invs, pur_invs=None):
    """扫描销项/进项发票，检出「发票数据质量异常」（RL-PTY-005）。返回 0/1 条发现。"""
    sal = [i for i in (sal_invs or []) if isinstance(i, dict)]
    pur = [i for i in (pur_invs or []) if isinstance(i, dict)]
    if not sal and not pur:
        return []

    dup_s, bad_s = _scan(sal)
    dup_p, bad_p = _scan(pur)
    dup = dict(dup_s)
    for no, c in dup_p.items():
        dup[no] = dup.get(no, 0) + c
    bad = bad_s + bad_p
    if not dup and not bad:
        return []

    hits = []
    if dup:
        _top = "、".join(f"{no}（{c} 次）" for no, c in list(dup.items())[:5])
        hits.append({"index": 1,
                     "evidence": f"检出 {len(dup)} 个重复发票号码，共 {sum(dup.values())} 张，"
                                 f"例：{_top}。"})
    if bad:
        _top2 = "、".join(f"{b['no'] or '（无号码）'}(差{b['diff']:,.2f}元)" for b in bad[:5])
        hits.append({"index": 2,
                     "evidence": f"检出 {len(bad)} 张票面「金额+税额≠价税合计」的发票，例：{_top2}。"})

    return [{
        "type": "发票数据质量异常：票面关系与连续性存疑",
        "level": "中风险",
        "score": 6,
        "redline_id": "RL-PTY-005",
        "constituent_hits": hits,
        "detail": (f"销项/进项发票中检出：重复票号 {len(dup)} 个、"
                   f"票面勾稽错误 {len(bad)} 张。"),
        "description": (
            "本轮发票数据存在两类票面质量问题："
            f"① 发票号码重复 {len(dup)} 个（同一号码出现 ≥2 次）；"
            f"② 票面「金额+税额≠价税合计」的勾稽错误 {len(bad)} 张。"
            "票号重复可能是一票多开、重复入账或替票；票面勾稽错误说明发票要素不自洽，"
            "须核对原始发票与开票系统数据。"),
        "tax_impact": "票面不自洽或重复的发票，其进项抵扣与成本列支的真实性存疑，"
                      "可能被要求进项转出、纳税调增。",
        "suggestion": "1）对重复票号逐一核对是否同一张票重复入账；"
                      "2）对勾稽错误发票核对外部原始票面，属录入错误的更正，属虚假发票的剔除；"
                      "3）建议以开票系统导出文件复核全量数据。",
        "category": "域13 发票深度",
    }]

# -*- coding: utf-8 -*-
"""潜在税额影响量化测算（2026-09-27，P1）。

用户诉求（P1）：资深稽查报告应给每项疑点算"值多少钱"——**潜在税额影响**，
并汇总"本轮潜在税额敞口"。

设计纪律（严格遵守项目铁律）：
  · **取不到就明说"未量化"**，绝不用默认值/文本里随便抓一个数当金额顶数
    （实测教训：把"账面成本总额 418 万"当成成本项敞口，纯属口径错误）。
  · 只认**关键词锚定**的金额（"涉及金额/差额/未匹配金额/少缴/虚增…"+ 数字 + 元），
    且必须 ≥ `_MIN_AMOUNT`（元），否则视为未取得。
  · 测算**必须标注口径与假设**（税率、是否含小微优惠等），并声明"仅供评估量级，
    不构成核定；实际以核实后依法核定为准"。
  · 税率来自 `_RATES` 单一表；新增税种只加一行。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from engine.numparse import to_number_checked

# 低于此金额不作为敞口（滤掉单价、计数、比率等噪音）
_MIN_AMOUNT = 1000.0

# 金额关键词锚（数字必须紧跟在这些词之后才认）
_AMOUNT_KW = (
    "涉及金额", "涉案金额", "未匹配金额", "未匹配", "差额", "差异额", "差异",
    "缺口", "少计收入", "少计销项", "少计", "少缴", "多抵", "虚增", "虚列",
    "隐匿收入", "未申报收入", "未开票收入", "价税合计", "调整金额", "涉及税额",
    "成本列支金额", "开票额",
)
_AMOUNT_PAT = re.compile(
    r"(?:" + "|".join(_AMOUNT_KW) + r")[^0-9¥￥]{0,12}?([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*元"
)

# 税率表（单一出处）：税种 → (默认税率, 口径说明)。
# ★ 2026-09-29（点评整改 P0-4）：默认税率只作**取不到语境时的兜底**。
#   实测事故：对销项全为服务费品名的企业按 13% 测增值税、按 25% 测企业所得税，
#   把敞口 66.77 万系统性虚高 2~3 倍。正确做法是先由 infer_rate_context() 从销项
#   品名/有效税率与净利润推断适用税率，再进入测算。
_RATES: Dict[str, tuple] = {
    "增值税": (0.13, "未取得销项税额明细，按 13% 法定上限口径测算；实际以票面适用税率（13%/9%/6%/3%）复核"),
    "企业所得税": (0.25, "按 25% 法定税率测算；小型微利企业另有优惠，实际以汇算清缴为准"),
    "个人所得税": (0.03, "按工资薪金/劳务报酬 3% 起点档测算；实际按超额累进税率计算"),
    "印花税": (0.0003, "按购销合同 0.03% 测算；实际按对应税目税率核对"),
}

# 增值税税率档（按销项有效税率落档）
_VAT_BRACKETS = (
    (0.028, 0.036, 0.03), (0.055, 0.066, 0.06),
    (0.085, 0.098, 0.09), (0.115, 0.145, 0.13),
)
# 小型微利企业临界值（应纳税所得额≤300万、从业人数≤300、资产总额≤5000万）
_SMALL_MICRO_PROFIT = 3_000_000.0
_SMALL_MICRO_STAFF = 300
_SMALL_MICRO_ASSETS = 50_000_000.0
# 个税基本减除费用（年度）
_PIT_BASIC_DEDUCTION = 60_000.0


def infer_rate_context(sal_invs=None, net_profit=None, employee_count=None,
                       total_assets=None) -> Dict[str, Any]:
    """推断本企业的适用税率语境（单一构造点，pipeline 调用一次存入 comprehensive）。

    返回 {"vat_rate": float|None, "vat_note": str,
          "cit_rate": float|None, "cit_note": str}。
    取不到的维度返回 None（由 estimate_tax 走兜底并如实注明），绝不猜。
    """
    ctx: Dict[str, Any] = {"vat_rate": None, "vat_note": "", "cit_rate": None, "cit_note": ""}
    # ── 增值税：按销项发票有效税率（税额/不含税金额）落档 ──
    try:
        from engine.numparse import amount_of as _amount_of
        amt_sum = 0.0
        tax_sum = 0.0
        for inv in (sal_invs or []):
            if not isinstance(inv, dict):
                continue
            a = _amount_of(inv)
            t = (to_number_checked(inv.get("tax_amount"))[0]
                 or to_number_checked(inv.get("税额"))[0]
                 or to_number_checked(inv.get("tax"))[0]
                 or 0.0)
            if a > 0:
                amt_sum += a
                tax_sum += t
        if amt_sum > 0:
            eff = tax_sum / amt_sum
            for lo, hi, rate in _VAT_BRACKETS:
                if lo <= eff <= hi:
                    ctx["vat_rate"] = rate
                    ctx["vat_note"] = (f"按销项发票有效税率 {rate*100:.0f}% 测算"
                                       f"（销项税额合计/不含税金额 = {eff*100:.1f}%，落 {rate*100:.0f}% 税率档）")
                    break
            if ctx["vat_rate"] is None:
                ctx["vat_note"] = f"销项有效税率 {eff*100:.1f}% 未落入常见税率档，按兜底口径测算"
    except Exception:
        pass
    # ── 企业所得税：小微判定（净利润>0 且 ≤300 万；人数/资产取得时一并校验）──
    try:
        np_val = to_number_checked(net_profit)[0] if net_profit is not None else None
        if np_val is not None and 0 < float(np_val) <= _SMALL_MICRO_PROFIT:
            staff_ok = employee_count is None or int(employee_count) <= _SMALL_MICRO_STAFF
            assets_ok = total_assets is None or float(total_assets) <= _SMALL_MICRO_ASSETS
            if staff_ok and assets_ok:
                ctx["cit_rate"] = 0.05
                miss = []
                if employee_count is None:
                    miss.append("从业人数未取得")
                if total_assets is None:
                    miss.append("资产总额未取得")
                ctx["cit_note"] = (
                    "按小型微利企业优惠口径 5% 测算（账面净利润≤300万"
                    + ("；" + "、".join(miss) + "，条件是否齐备以汇算清缴认定为准" if miss else "")
                    + "；若不符合优惠条件应按 25%）")
    except Exception:
        pass
    return ctx


def estimate_tax(amount: Optional[float], taxes: Optional[List[str]],
                 rate_ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """按税种测算潜在税额影响。amount 为不含税涉案金额；取不到→未量化。

    ★ 2026-09-29（点评整改 P0-4）：rate_ctx 由 infer_rate_context() 构造
    （pipeline 存于 comprehensive["tax_rate_context"]）；未提供时走 _RATES 兜底。
    个税：涉案金额低于 6 万元基本减除费用的，如实注明"无实际个税影响"，不计入合计。
    """
    if not amount or amount <= 0:
        return {
            "available": False, "basis": None, "items": [], "total": None,
            "note": "未量化：本项检查记录未给出可用于测算的明确金额，须补充资料后测算。",
        }
    rate_ctx = rate_ctx if isinstance(rate_ctx, dict) else {}
    taxes = [str(t) for t in (taxes or [])]
    items: List[Dict[str, Any]] = []
    vat_amount = 0.0
    for t in taxes:
        rate, note = _RATES.get(t, (None, ""))
        if rate is None:
            continue
        if t == "增值税":
            v_rate = rate_ctx.get("vat_rate")
            if v_rate:
                rate = float(v_rate)
                note = str(rate_ctx.get("vat_note") or note)
        elif t == "企业所得税":
            c_rate = rate_ctx.get("cit_rate")
            if c_rate:
                rate = float(c_rate)
                note = str(rate_ctx.get("cit_note") or note)
        if t == "个人所得税" and float(amount) < _PIT_BASIC_DEDUCTION:
            # 金额低于年度基本减除费用：若属工资薪金年度累计，无实际个税影响
            items.append({"tax": t, "rate": "0",
                          "amount": 0.0,
                          "note": f"涉案金额低于 {_PIT_BASIC_DEDUCTION:,.0f} 元基本减除费用，"
                                  "若属工资薪金年度累计则无实际个税影响；不计入敞口合计，"
                                  "实际以全员全额扣缴申报为准。"})
            continue
        amt = round(amount * rate, 2)
        if t == "增值税":
            vat_amount = amt
        items.append({"tax": t, "rate": "%.4f" % rate,
                      "amount": amt, "note": note})
    # 增值税附加（随增值税附征）
    if vat_amount:
        items.append({"tax": "城建税及教育费附加", "rate": "0.12",
                      "amount": round(vat_amount * 0.12, 2),
                      "note": "按增值税额的 12%（城建 7%+教育 3%+地方教育 2%）测算"})
    total = round(sum(i["amount"] for i in items), 2) if items else None
    return {
        "available": bool(items), "basis": round(float(amount), 2),
        "items": items, "total": total,
        "note": "以上为按适用税率与本期涉案金额的**粗略测算**，仅供评估影响量级；"
                "不构成核定，实际以核实后依法核定为准。各事项间金额可能重叠"
                "（同一笔资金可能同时进入多个疑点口径），敞口合计为最坏情形上界，"
                "不可逐项相加用于缴款。",
    }


def extract_amount(text: Any) -> Optional[Dict[str, Any]]:
    """从文本里**关键词锚定**地取一个代表金额；取不到返回 None（不猜）。"""
    if not isinstance(text, str) or not text:
        return None
    best = None
    for m in _AMOUNT_PAT.finditer(text):
        raw = m.group(1)
        val, ok = to_number_checked(raw)
        if not ok or val is None or abs(val) < _MIN_AMOUNT:
            continue
        if best is None or abs(val) > abs(best["amount"]):
            best = {"amount": abs(round(float(val), 2)), "raw": raw,
                    "context": m.group(0)[:40]}
    return best


def extract_amount_from_problem(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """在一项「具体问题」的检查记录（叙述段/明细表）中锚定金额。"""
    if not isinstance(p, dict):
        return None
    chunks: List[str] = []
    for np in (p.get("narrative_paragraphs") or []):
        if not isinstance(np, dict):
            continue
        chunks.append(str(np.get("text") or ""))
        chunks.append(" ".join(str(b) for b in (np.get("bullets") or [])))
        chunks.append(str(np.get("tail") or ""))
    for row in ((p.get("detail_table") or {}).get("rows") or []):
        if isinstance(row, dict):
            chunks.append(" ".join(str(v) for v in row.values()))
    return extract_amount("\n".join(chunks))


def build_tax_impact_summary(problems: List[Dict[str, Any]]) -> Dict[str, Any]:
    """汇总本轮的潜在税额敞口（分税种）+ 已量化/未量化覆盖度。"""
    by_tax: Dict[str, float] = {}
    quantified = 0
    for p in (problems or []):
        ti = (p or {}).get("tax_impact") or {}
        if not ti.get("available"):
            continue
        quantified += 1
        for it in ti.get("items") or []:
            _v = to_number_checked(it.get("amount"))[0] or 0.0
            by_tax[it["tax"]] = round(by_tax.get(it["tax"], 0.0) + float(_v), 2)
    total = round(sum(by_tax.values()), 2) if by_tax else None
    return {
        "quantified": quantified,
        "total_items": len(problems or []),
        "by_tax": [{"tax": k, "amount": v}
                   for k, v in sorted(by_tax.items(), key=lambda kv: -kv[1])],
        "total": total,
        "note": ("潜在税额敞口为按适用税率的粗略测算（税率语境见各项明细），仅供评估量级，"
                 "不构成核定；未量化的项表示检查记录中尚无明确金额，须补资料后测算。"
                 "各事项间金额可能重叠，敞口合计为最坏情形上界，不可逐项相加用于缴款。"),
    }

# -*- coding: utf-8 -*-
"""收入真实性（账外收入嫌疑）能力（2026-09-14 新增）。

把用户关心的"银行收款 > 申报收入 → 账外收入嫌疑"从单点规则升级为**三维度三角验证**：

* 维度1 发票↔申报收入匹配（开票是否漏报 / 未开票收入是否已申报）——复用 VR018 口径；
* 维度2 发票↔银行收款匹配（开了票但有无未收回款项、是否经个人账户归集）——复用 VR061 口径；
* 维度3 未收款项金额 + 账龄（账面应收挂账多久）——引擎 ``engine.ar_aging``。

三路并行后**综合裁定三态**（账外收入嫌疑↑ / 真赊账待核 / 资料缺失待核）。
起点信号（银行收款 > 申报收入）本身不是结论，任一维度给出合理解释即不肓目定罪。

铁律：发现≠确认；结论一律待证线索，不作为定性依据。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.ar_aging import run_ar_aging_check


def _number(value) -> float:
    try:
        return float(str(value).replace(",", "").replace("￥", "").replace("¥", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def _infer_base_date(data: Dict[str, Any]) -> Optional[str]:
    """从销项发票日期推断账龄基准日（取最晚一张发票日）。无则 None。"""
    import datetime as _dt
    best = None
    for inv in (data.get("sal_invs") or []):
        if not isinstance(inv, dict):
            continue
        raw = str(inv.get("date") or inv.get("invoice_date") or inv.get("开票日期") or "")
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) < 8:
            continue
        try:
            d = _dt.date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            continue
        if best is None or d > best:
            best = d
    return best.strftime("%Y-%m-%d") if best else None


def _dim1_invoice_vs_declaration(data: Dict[str, Any]):
    """维度1：开票收入 vs 申报销售额差额与方向。

    返回 {"declared": float, "invoiced": float, "gap": float,
          "declared_gt_invoiced": bool, "detail": str}
    """
    from collections import defaultdict
    decls = data.get("tax_declarations") or []
    sal = data.get("sal_invs") or []
    decl_by_month = defaultdict(float)
    for d in decls:
        if not isinstance(d, dict):
            continue
        s = _number(d.get("sales_amount"))
        if s <= 0:
            continue
        decl_by_month["all"] += s
    inv_total = sum(_number(r.get("amount")) for r in sal if isinstance(r, dict))
    declared = decl_by_month.get("all", 0.0)
    gap = declared - inv_total
    declared_gt_invoiced = declared > inv_total * 1.02
    if declared <= 0:
        detail = "未取得申报表，维度1无法核验。"
    elif declared_gt_invoiced:
        detail = (f"申报销售额 {declared:,.2f} 元 > 开票收入 {inv_total:,.2f} 元，"
                  f"差额 {gap:,.2f} 元属未开票收入已申报（合法），不构成账外嫌疑。")
    elif inv_total > declared * 1.02:
        detail = (f"开票收入 {inv_total:,.2f} 元 > 申报销售额 {declared:,.2f} 元，"
                  f"差额 {abs(gap):,.2f} 元，存在已开票未申报方向，须核验是否漏报。")
    else:
        detail = (f"申报销售额 {declared:,.2f} 元与开票收入 {inv_total:,.2f} 元基本吻合，"
                  f"未开票收入申报缺口不明显。")
    return {"declared": round(declared, 2), "invoiced": round(inv_total, 2),
            "gap": round(gap, 2), "declared_gt_invoiced": declared_gt_invoiced, "detail": detail}


def _dim2_invoice_vs_bank(data: Dict[str, Any]):
    """维度2：开票收入 vs 银行收款匹配（未收回款项 + 个人账户归集）。

    返回 {"total": float, "matched": float, "unmatched": float, "ratio": float,
          "person_in": float, "person_names": list, "bank_in_total": float, "detail": str}
    """
    sal = data.get("sal_invs") or []
    bank = data.get("bank_txs") or []
    if not sal or not bank:
        return {"total": 0.0, "matched": 0.0, "unmatched": 0.0, "ratio": 0.0,
                "person_in": 0.0, "person_names": [], "bank_in_total": 0.0,
                "detail": "缺销项发票或银行流水，维度2无法核验。"}
    from engine.fund_matching import (
        classify_revenue_receipt,
        is_individual_name,
        is_platform_counterparty,
    )
    rec = classify_revenue_receipt(sal, bank)
    totals = rec.get("totals") or {}
    total = totals.get("total") or 0.0
    matched = totals.get("matched") or 0.0
    unmatched = totals.get("unmatched") or 0.0
    ratio = rec.get("receipt_ratio") or 0.0

    person_in = 0.0
    person_names = set()
    bank_in_total = 0.0
    for tx in bank:
        credit = _number(tx.get("credit"))
        if credit > 0:
            bank_in_total += credit
            cp = str(tx.get("counterparty") or "").strip()
            if cp and is_individual_name(cp) and not is_platform_counterparty(cp):
                person_in += credit
                person_names.add(cp)

    if total <= 0:
        detail = "无开票收入，维度2不适用。"
    elif unmatched >= 50000 or (total > 0 and unmatched / total >= 0.10):
        detail = (f"开票收入中有 {unmatched:,.2f} 元（占 {unmatched / total * 100:.1f}%）"
                  f"未匹配到银行/第三方平台收款；")
        if person_in >= 50000 or (bank_in_total > 0 and person_in / bank_in_total >= 0.10):
            detail += (f"其中 {person_in:,.2f} 元来自个人账户（{len(person_names)} 个自然人），"
                       f"收入经个人账户归集，是账外收款的直接证据。")
        else:
            detail += "其余多为客户赊账未付，须按维度3核验账龄与期后回款。"
    else:
        detail = f"开票收入中 {ratio * 100:.0f}% 已匹配银行/平台收款，未收款比例较低。"
    return {"total": round(total, 2), "matched": round(matched, 2), "unmatched": round(unmatched, 2),
            "ratio": ratio, "person_in": round(person_in, 2), "person_names": sorted(person_names)[:10],
            "bank_in_total": round(bank_in_total, 2), "detail": detail}


def run_revenue_authenticity_check(data: Dict[str, Any], company_name: str = "",
                                   base_date: Optional[str] = None) -> Dict[str, Any]:
    """收入真实性（账外收入嫌疑）组合能力入口。

    输入 ``data`` 须含 sal_invs / bank_txs / tax_declarations / accounts_receivable（可选）
    / trial_balance（可选）。返回与能力范式同构的 dict。
    """
    title = "收入真实性（账外收入嫌疑）"
    if base_date is None:
        base_date = _infer_base_date(data)

    if not (data.get("sal_invs") or data.get("bank_txs") or data.get("tax_declarations")):
        return {
            "available": False,
            "ok": True,
            "title": title,
            "company": company_name,
            "summary": "未提供销项发票、银行流水或申报表，无法核验收入真实性。",
            "body": "收入真实性（账外收入嫌疑）三维度验证需要销项发票、银行收款流水与增值税申报表中的至少一项，"
                    "本轮均未提供，无法量化银行收款与申报收入的匹配关系。",
            "metrics": {},
            "signals": [],
            "verdict": "资料缺失待核",
            "recommendation": "上传销项发票、银行流水与增值税申报表后重新分析。",
            "note": "结论属待证线索，不作为定性依据。",
        }

    d1 = _dim1_invoice_vs_declaration(data)
    d2 = _dim2_invoice_vs_bank(data)
    ar = run_ar_aging_check(data, company_name=company_name, base_date=base_date)

    ar_m = ar.get("metrics", {}) or {}
    ar_unreceived = ar_m.get("ar_unreceived_total", 0.0) or 0.0
    ar_long = ar_m.get("ar_long_aging_count", 0) or 0

    bank_in = d2.get("bank_in_total", 0.0)
    declared = d1.get("declared", 0.0)
    invoiced = d1.get("invoiced", 0.0)
    unmatched = d2.get("unmatched", 0.0)
    person_in = d2.get("person_in", 0.0)

    # ── 起点信号：银行收款 > 申报收入 ──
    start_signal = bank_in > declared * 1.05 if declared > 0 else (bank_in > 0)
    has_person_in = person_in >= 50000 or (bank_in > 0 and person_in / bank_in >= 0.10)
    unmatched_high = unmatched >= 50000 or (d2.get("total", 0) > 0 and unmatched / d2["total"] >= 0.10)
    inv_approx_decl = invoiced <= declared * 1.02  # 开票≈申报（无未开票申报缺口）
    ar_unreceived_low = ar_unreceived < 50000

    # ── 综合裁定三态 ──
    if ar_long > 0:
        # 长期应收挂账无回款 → 收入真实性存疑，疑虚构收入或资金滞留账外（独立于起点信号）
        verdict = "账外收入嫌疑↑"
        verdict_detail = ("账面应收账款存在超 1 年的长期挂账（未收合计 "
                         f"{ar_unreceived:,.0f} 元），收入真实性存疑，"
                         "须逐笔核验交易背景与期后回款，警惕虚构收入或资金滞留账外。")
    elif not start_signal:
        verdict = "未见账外收入信号"
        verdict_detail = "银行收款未明显超过申报收入，且应收无长期无回款，起点信号不成立；三维明细见下，维持常规关注。"
    elif has_person_in:
        verdict = "账外收入嫌疑↑"
        verdict_detail = "银行收款明显超过申报收入，且部分收入经个人账户归集，是账外收款的直接证据，须逐一核验个人账户性质与去向。"
    elif (not d1["declared_gt_invoiced"]) and inv_approx_decl and (not unmatched_high) and ar_unreceived_low:
        verdict = "账外收入嫌疑↑"
        verdict_detail = ("银行收款超过申报收入，但开票≈申报、未收款与应收挂账均较低，"
                         "指向存在未开票收入未申报，构成账外收入嫌疑，须补开票与申报比对。")
    elif unmatched_high or ar_unreceived > 0:
        verdict = "真赊账待核"
        verdict_detail = "已开票未收回款项（应收挂账未达长期无回款），属正常赊销经营常态，待核非定罪。"
    else:
        verdict = "待核验"
        verdict_detail = "银行收款高于申报收入，但三维均未呈现强异常，暂列为待核实事项。"

    signals = []
    if start_signal:
        signals.append({"signal": "银行收款明显高于申报收入", "hint": "账外收入起点信号，须三维交叉验证"})
    if d1["declared_gt_invoiced"]:
        signals.append({"signal": "申报>开票（未开票收入已申报）", "hint": "合法，降低账外嫌疑"})
    elif invoiced > declared * 1.02:
        signals.append({"signal": "开票>申报（漏报方向）", "hint": "已开票未申报，须核验"})
    if has_person_in:
        signals.append({"signal": f"个人账户归集 {person_in:,.0f} 元", "hint": "账外收款直接证据"})
    if ar_long > 0:
        signals.append({"signal": f"{ar_long} 个客户应收挂账超 1 年", "hint": "长期无回款，疑虚构收入"})

    summary = (f"起点信号{'成立' if start_signal else '不成立'}；维度1：{d1['detail']} "
               f"维度2：{d2['detail']} 维度3（应收）：{ar.get('summary','')} "
               f"综合裁定：{verdict}。")

    body = (
        "【维度1 发票↔申报】" + d1["detail"] + "\n"
        "【维度2 发票↔银行】" + d2["detail"] + "\n"
        "【维度3 未收款项+账龄】" + (ar.get("body") or ar.get("summary") or "") + "\n"
        "【综合裁定】" + verdict_detail
    )

    metrics = {
        "start_signal": bool(start_signal),
        "bank_in_total": round(bank_in, 2),
        "declared_total": round(declared, 2),
        "invoiced_total": round(invoiced, 2),
        "unmatched_amount": round(unmatched, 2),
        "person_inflow_amount": round(person_in, 2),
        "ar_unreceived_total": round(ar_unreceived, 2),
        "ar_long_aging_count": ar_long,
        "ar_max_aging_days": ar_m.get("ar_max_aging_days", 0),
        "base_date": base_date or "",
    }

    return {
        "available": True,
        "ok": True,
        "title": title,
        "company": company_name,
        "summary": summary,
        "body": body,
        "metrics": metrics,
        "signals": signals,
        "verdict": verdict,
        "recommendation": "责令企业补提未开票收入明细、应收账款账龄表与银行回款流水，逐笔核验"
                          "未收回款项性质与回款去向；个人账户收款须说明资金来源与税务处理。",
        "note": "结论属待证线索，不作为定性依据；银行收款大于申报收入本身不构成确认，须三维交叉验证后出嫌疑结论。",
        # 三维明细透传，供报告分层渲染
        "dimensions": {
            "invoice_vs_declaration": d1,
            "invoice_vs_bank": d2,
            "ar_aging": ar,
        },
    }

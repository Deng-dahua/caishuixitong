"""出口退税四单交叉核验（2026-09-12）

把 RL-SPT-008「出口退税申报与收汇、物流、生产能力不匹配」从"缺数据只能置疑"
升级为**可用数据定量核验**的能力。

四单交叉口径（与现行出口退税管理一致）：
    出口发票（销售额） × 报关单（实际出口） × 收汇水单（资金回流） × 产能采购（业务支撑）

任一环断裂即构成待核线索：
1. 报关单金额 vs 出口发票金额 偏差超阈值 → 单证不一致
2. 收汇金额 vs 出口金额 缺口超阈值且长期未收汇 → 资金流断裂
3. 出口规模 vs 产能/采购/能耗支撑 明显不匹配 → 业务真实性存疑
4. 缺报关单或收汇数据 → 降级置疑清单，列明需补资料

★ 全部产出均为待核线索，绝不认定"骗取出口退税"。
"""

from __future__ import annotations

from typing import Any, Dict, List

# 偏差阈值（相对比例），超过即列疑点
_DECL_GAP_RATIO = 0.10      # 报关单与出口发票金额偏差
_RECEIPT_GAP_RATIO = 0.15   # 收汇缺口
_CAPACITY_MULTIPLE = 3.0    # 出口额相对采购/产能支撑的倍数异常线


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _sum(records: Any, keys: List[str]) -> float:
    total = 0.0
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        for k in keys:
            if rec.get(k) not in (None, ""):
                total += _num(rec.get(k))
                break
    return total


def _text(records: Any) -> str:
    parts = []
    for rec in records or []:
        parts.append(str(rec))
    return "\n".join(parts)


def _is_export(rec: Dict) -> bool:
    """判断是否为出口相关发票/报关单记录。"""
    s = str(rec)
    return any(k in s for k in ("出口", "报关", "EXW", "FOB", "CIF", "境外", "外币", "USD"))


def run_export_rebate_crosscheck(
    engine_data: Dict,
    pipeline_log: List[str] = None,
) -> List[Dict]:
    """执行出口退税四单交叉核验，返回待核发现列表。"""
    sal_invs = [r for r in (engine_data.get("sal_invs") or []) if isinstance(r, dict)]
    declarations = [r for r in (engine_data.get("tax_declarations") or []) if isinstance(r, dict)]
    bank_txs = [r for r in (engine_data.get("bank_txs") or []) if isinstance(r, dict)]
    vouchers = [r for r in (engine_data.get("vouchers") or []) if isinstance(r, dict)]
    customs = engine_data.get("declarations") or []   # 报关单（管线单独解析）

    all_text = _text(sal_invs) + _text(declarations) + _text(customs) + _text(vouchers)
    if not any(k in all_text for k in ("出口", "报关", "退税")):
        return []   # 无出口业务，直接返回（避免无谓置疑）

    findings: List[Dict] = []

    # ① 出口销售额
    export_sales = _sum([r for r in sal_invs if _is_export(r)],
                        ["金额", "价税合计", "total", "amount", "不含税金额"])
    if export_sales <= 0:
        export_sales = _sum([r for r in sal_invs if _is_export(r)], ["销售额", "金额"])

    # ② 报关单金额
    decl_amount = _sum([r for r in customs if isinstance(r, dict)],
                       ["total_usd", "amount", "金额", "成交金额", "declared_value"])
    if decl_amount <= 0:
        decl_amount = _sum([r for r in declarations if _is_export(r)],
                           ["金额", "销售额", "amount", "total"])

    # ③ 收汇金额（银行流水中的外汇/境外入账）
    receipts = _sum([r for r in bank_txs if _is_export(r) or "汇" in str(r)],
                    ["金额", "amount", "收入", "贷方"])

    # ④ 产能/采购支撑
    capacity = _sum([r for r in vouchers
                     if any(k in str(r) for k in ("原材料", "采购", "生产成本", "用电", "能耗"))],
                    ["金额", "借方金额", "借方"])

    # 缺报关单或收汇 → 置疑清单
    if decl_amount <= 0 or receipts <= 0:
        missing = []
        if decl_amount <= 0:
            missing.append("出口报关单（含品名、数量、金额、收发货人）")
        if receipts <= 0:
            missing.append("收汇水单与外汇入账流水")
        findings.append({
            "type": "出口业务缺报关单或收汇佐证（待核）",
            "detail": (
                "账簿或发票中存在出口业务线索，但缺少报关单或收汇水单，"
                "无法完成出口发票、报关单、收汇、产能四单交叉核验。"
                "请补充资料后复核是否存在单证不一致、未收汇或出口规模与产能不匹配的情形。"
            ),
            "level": "中风险", "score": 5, "tax_type": "出口退税", "domain": "特定税种",
            "policy_ref": "RL-SPT-008",
            "suggestion": "请补充下列资料后复核：" + "、".join(missing),
            "items": [{"name": m, "status": "待补充"} for m in missing],
            "evidence": [f"出口发票金额 {export_sales:,.2f}" if export_sales else "存在出口线索"],
            "needs_material": missing,
            "_gap_detector": "RL-SPT-008",
            "_detection_method": "四单交叉（出口发票×报关单×收汇×产能）；缺单证时降级置疑清单",
            "_unconfirmed": True,
        })
        return findings

    # ① 报关单 vs 出口发票
    if export_sales > 0:
        gap = abs(decl_amount - export_sales) / export_sales
        if gap > _DECL_GAP_RATIO:
            findings.append({
                "type": "报关单与出口发票金额不一致（待核）",
                "detail": (
                    f"报关单金额 {decl_amount:,.2f} 与出口发票金额 {export_sales:,.2f} "
                    f"偏差 {gap*100:.1f}%，超过 {_DECL_GAP_RATIO*100:.0f}% 阈值。"
                    "请核实是否存在单证品名、数量、金额或收发货人不一致的情形。"
                ),
                "level": "高风险", "score": 8, "tax_type": "出口退税", "domain": "特定税种",
                "policy_ref": "RL-SPT-008",
                "suggestion": "提供报关单、海运提单、装箱单与出口发票，逐票比对品名、数量、金额、收发货人。",
                "items": [{"name": "报关单", "status": "待补充"},
                          {"name": "海运提单与装箱单", "status": "待补充"}],
                "evidence": [f"报关单 {decl_amount:,.2f}", f"出口发票 {export_sales:,.2f}",
                             f"偏差 {gap*100:.1f}%"],
                "needs_material": ["报关单", "海运提单", "装箱单", "出口发票"],
                "_gap_detector": "RL-SPT-008",
                "_detection_method": "报关单金额与出口发票金额相对偏差比对（阈值10%）",
                "_unconfirmed": False,
            })

    # ② 收汇缺口
    if export_sales > 0:
        shortfall = (export_sales - receipts) / export_sales
        if shortfall > _RECEIPT_GAP_RATIO:
            findings.append({
                "type": "出口后收汇缺口较大（待核）",
                "detail": (
                    f"出口金额 {export_sales:,.2f} 中尚有 {export_sales-receipts:,.2f} "
                    f"（{shortfall*100:.1f}%）未见对应收汇。请核实是否已办理延期收汇备案，"
                    "或存在视同收汇的合法情形；长期未收汇且无合法情形的，不符合退（免）税条件。"
                ),
                "level": "高风险", "score": 7, "tax_type": "出口退税", "domain": "特定税种",
                "policy_ref": "RL-SPT-008",
                "suggestion": "提供收汇水单、延期收汇备案或视同收汇的证明材料。",
                "items": [{"name": "收汇水单", "status": "待补充"},
                          {"name": "延期收汇备案或视同收汇证明", "status": "待补充"}],
                "evidence": [f"出口 {export_sales:,.2f}", f"收汇 {receipts:,.2f}",
                             f"缺口 {shortfall*100:.1f}%"],
                "needs_material": ["收汇水单", "延期收汇备案", "视同收汇证明"],
                "_gap_detector": "RL-SPT-008",
                "_detection_method": "出口金额与收汇金额缺口比对（阈值15%）",
                "_unconfirmed": False,
            })

    # ③ 出口规模 vs 产能/采购支撑
    if capacity > 0 and export_sales > capacity * _CAPACITY_MULTIPLE:
        findings.append({
            "type": "出口规模与采购产能支撑明显不匹配（待核）",
            "detail": (
                f"出口金额 {export_sales:,.2f} 达到同期采购/产能投入 {capacity:,.2f} 的 "
                f"{export_sales/capacity:.1f} 倍。请核实是否有足够的原材料采购、生产产能与"
                "能耗支撑该出口规模，排除虚构出口的可能。"
            ),
            "level": "高风险", "score": 8, "tax_type": "出口退税", "domain": "特定税种",
            "policy_ref": "RL-SPT-008",
            "suggestion": "提供产能台账、用电量记录、原材料采购合同与进项发票、生产工时记录。",
            "items": [{"name": "产能台账与用电量记录", "status": "待补充"},
                      {"name": "原材料采购合同与进项发票", "status": "待补充"}],
            "evidence": [f"出口 {export_sales:,.2f}", f"采购产能投入 {capacity:,.2f}",
                         f"倍数 {export_sales/capacity:.1f}"],
            "needs_material": ["产能台账", "用电量记录", "采购合同与进项发票", "生产工时记录"],
            "_gap_detector": "RL-SPT-008",
            "_detection_method": "出口额与采购/能耗/产能投入的倍数比对（异常线3倍）",
            "_unconfirmed": True,
        })

    return findings

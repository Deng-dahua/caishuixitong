"""行业预警指标库与对标探测（2026-09-12）

对应金税四期最核心的能力之一：**行业指标预警**。
税务机关常用的横向比对口径即「本企业指标 vs 同行业预警区间」，偏离即列为风险纳税人。

本模块提供：
1. INDUSTRY_BENCHMARKS —— 分行业的增值税税负率/毛利率/期间费用率/进销比参考预警区间；
2. compute_indicators()  —— 用现有数据计算企业实际指标；
3. run_industry_benchmark_check() —— 实际值 vs 行业区间，产出待核疑点。

★ 边界声明（必须随结果一并告知，绝不定性）：
- 区间为**通用参考预警值**，来源于公开行业经验区间，非税务机关官方口径，
  各地税务机关的行业预警值以本地模型为准；
- 偏离区间只构成**待核线索**，不构成"少缴税款"的定性结论；
- 行业周期、经营模式、出口占比、政策优惠等都会造成合理偏离，须经正当理由核验。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# ── 行业参考预警区间（下限, 上限），单位：百分比 ──────────────────────────
# vat_burden     增值税税负率 = 应纳增值税 / 销售收入
# gross_margin   毛利率       = (收入 - 成本) / 收入
# expense_ratio  期间费用率   = (销售+管理+财务费用) / 收入（仅给上限）
# purchase_sales 进销比       = 进项金额 / 销项金额
INDUSTRY_BENCHMARKS: Dict[str, Dict[str, Tuple[float, float]]] = {
    "制造业":            {"vat_burden": (1.5, 3.5), "gross_margin": (10.0, 30.0), "expense_ratio": (0.0, 15.0), "purchase_sales": (0.40, 0.95)},
    "批发和零售业":      {"vat_burden": (0.5, 1.5), "gross_margin": (5.0, 20.0),  "expense_ratio": (0.0, 12.0), "purchase_sales": (0.60, 0.98)},
    "建筑业":            {"vat_burden": (2.0, 3.5), "gross_margin": (8.0, 20.0),  "expense_ratio": (0.0, 10.0), "purchase_sales": (0.50, 0.95)},
    "软件和信息技术服务业": {"vat_burden": (1.0, 3.0), "gross_margin": (25.0, 60.0), "expense_ratio": (0.0, 35.0), "purchase_sales": (0.10, 0.60)},
    "住宿和餐饮业":      {"vat_burden": (1.0, 3.0), "gross_margin": (40.0, 65.0), "expense_ratio": (0.0, 45.0), "purchase_sales": (0.20, 0.70)},
    "交通运输仓储和邮政业": {"vat_burden": (2.0, 3.5), "gross_margin": (12.0, 28.0), "expense_ratio": (0.0, 15.0), "purchase_sales": (0.30, 0.85)},
    "房地产业":          {"vat_burden": (2.5, 5.0), "gross_margin": (20.0, 40.0), "expense_ratio": (0.0, 15.0), "purchase_sales": (0.30, 0.90)},
    "租赁和商务服务业":  {"vat_burden": (1.5, 4.0), "gross_margin": (20.0, 50.0), "expense_ratio": (0.0, 30.0), "purchase_sales": (0.15, 0.70)},
    "农、林、牧、渔业":  {"vat_burden": (0.5, 2.0), "gross_margin": (10.0, 30.0), "expense_ratio": (0.0, 20.0), "purchase_sales": (0.30, 0.90)},
    "电力热力燃气及水生产供应业": {"vat_burden": (1.5, 3.0), "gross_margin": (10.0, 25.0), "expense_ratio": (0.0, 12.0), "purchase_sales": (0.40, 0.90)},
}

# 未匹配到具体行业时的通用宽松区间（避免无行业信息时误报）
_GENERIC = {"vat_burden": (0.3, 6.0), "gross_margin": (2.0, 70.0),
            "expense_ratio": (0.0, 50.0), "purchase_sales": (0.05, 1.20)}

_LABEL = {
    "vat_burden": "增值税税负率",
    "gross_margin": "毛利率",
    "expense_ratio": "期间费用率",
    "purchase_sales": "进销比",
}


def match_industry(name: str) -> str:
    """按企业名称/行业描述模糊匹配库内行业，匹配不到返回空串。"""
    text = str(name or "")
    for key in INDUSTRY_BENCHMARKS:
        # 用行业名中的关键片段做包含匹配
        frag = key.replace("、", "").replace("和", "")[:4]
        if frag and frag in text:
            return key
    for key in INDUSTRY_BENCHMARKS:
        if key in text:
            return key
    return ""


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _sum_field(records: Any, keys: List[str]) -> float:
    """按候选键名求和金额（容错不同来源字段命名）。"""
    total = 0.0
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        for k in keys:
            if rec.get(k) not in (None, ""):
                total += _num(rec.get(k))
                break
    return total


def compute_indicators(engine_data: Dict) -> Dict[str, float]:
    """计算企业实际指标（百分比）。返回 {指标: 值}，取不到数据的指标不返回。"""
    sal_invs = engine_data.get("sal_invs") or []
    pur_invs = engine_data.get("pur_invs") or []
    vouchers = engine_data.get("vouchers") or []

    sales = _sum_field(sal_invs, ["金额", "价税合计", "total", "amount", "不含税金额"])
    sales_tax = _sum_field(sal_invs, ["税额", "tax", "销项税额"])
    purchase = _sum_field(pur_invs, ["金额", "价税合计", "total", "amount", "不含税金额"])
    purchase_tax = _sum_field(pur_invs, ["税额", "tax", "进项税额"])

    # 成本费用：优先从凭证科目归集
    cost = 0.0
    expense = 0.0
    for rec in vouchers:
        if not isinstance(rec, dict):
            continue
        text = str(rec.get("科目", "")) + str(rec.get("摘要", ""))
        amt = _num(rec.get("金额") or rec.get("借方金额") or rec.get("借方"))
        if any(k in text for k in ("主营业务成本", "生产成本", "库存商品", "原材料")):
            cost += amt
        elif any(k in text for k in ("销售费用", "管理费用", "财务费用")):
            expense += amt

    out: Dict[str, float] = {}
    if sales > 0:
        vat_due = sales_tax - purchase_tax
        out["vat_burden"] = round(vat_due / sales * 100, 2)
        if cost > 0:
            out["gross_margin"] = round((sales - cost) / sales * 100, 2)
        if expense > 0:
            out["expense_ratio"] = round(expense / sales * 100, 2)
        if purchase > 0:
            out["purchase_sales"] = round(purchase / sales, 3)
    return out


def run_industry_benchmark_check(
    engine_data: Dict,
    industry: str = "",
    pipeline_log: List[str] = None,
) -> List[Dict]:
    """实际指标 vs 行业预警区间，产出待核疑点（绝不定性）。"""
    indicators = compute_indicators(engine_data)
    if not indicators:
        return []

    matched = match_industry(industry) if industry else ""
    bench = INDUSTRY_BENCHMARKS.get(matched, _GENERIC)
    if not matched and pipeline_log is not None:
        pipeline_log.append("[行业对标] 未匹配到具体行业，按通用宽松区间比对（降低误报）")

    findings: List[Dict] = []
    for key, actual in indicators.items():
        low, high = bench.get(key, (None, None))
        if low is None:
            continue
        # 进销比是比值不是百分比
        value = actual / 100 if key == "purchase_sales" and actual > 1.5 else actual
        if low <= value <= high:
            continue
        direction = "低于" if value < low else "高于"
        unit = "" if key == "purchase_sales" else "%"
        detail_value = round(value, 3) if key == "purchase_sales" else value
        bound = low if value < low else high
        bound_disp = round(bound, 3) if key == "purchase_sales" else bound

        findings.append({
            "type": f"{_LABEL[key]}偏离行业预警区间（待核）",
            "detail": (
                f"本企业{_LABEL[key]}为 {detail_value}{unit}，{direction}行业"
                f"参考预警区间（{bound_disp}{unit}）。"
                f"该偏离可能由经营模式、行业周期、出口占比、税收优惠等合理因素造成，"
                f"也可能指向收入隐匿、成本虚列或进项异常，须结合业务实质核实。"
            ),
            "level": "中风险",
            "score": 5,
            "tax_type": "增值税" if key == "vat_burden" else "企业所得税",
            "domain": "行业对标",
            "policy_ref": "",
            "suggestion": f"请说明{_LABEL[key]}偏离的原因，并提供同期行业可比资料、"
                          f"经营模式说明及适用税收优惠备案资料。",
            "items": [{"name": "行业可比资料与经营模式说明", "status": "待补充"},
                      {"name": "适用税收优惠备案资料", "status": "待补充"}],
            "evidence": [f"{_LABEL[key]}={detail_value}{unit}", f"行业区间 {low}~{high}"],
            "needs_material": ["行业可比资料与经营模式说明", "适用税收优惠备案资料"],
            "_industry": matched or "通用",
            "_indicator": key,
            "_actual": value,
            "_range": [low, high],
            "_detection_method": "计算企业实际指标 → 与同行业参考预警区间比对 → 偏离即列为待核线索",
            "_unconfirmed": True,
        })
    return findings

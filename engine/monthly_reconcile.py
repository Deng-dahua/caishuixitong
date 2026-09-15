# -*- coding: utf-8 -*-
"""跨文件逐月对等勾稽引擎（2026-09-15 新增）。

把多份上传文件里的**同一口径**，按「月 / 季 / 年」对齐成序列，逐期校验"对等相等"，
输出可复算的对等表与差异待核线索。补齐此前缺口：
  - 收入四方：增值税申报表销售额 ↔ 序时账主营业务收入(贷方) ↔ 开具发票金额(不含税) ↔ 利润表收入
  - 工资四方：工资表应发 ↔ 个税申报本月收入 ↔ 序时账计提工资(应付职工薪酬贷方)
  - 个税三方：工资表代扣个税 ↔ 个税申报个税 ↔ 序时账计提个税(应交个人所得税贷方)

铁律：只输出可复算事实与待核线索，绝不自动定性；不足两方数据或无法归月时不输出。
口径提示：申报表销售额与开具发票取**不含税**；序时账收入取贷方发生额（会计口径通常为不含税）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

_TOL_ABS = 1000.0      # 绝对容差（元）
_TOL_REL = 0.01        # 相对容差（1%）

_REV_ACCT_KWS = ("主营业务收入", "营业收入", "销售收入", "产品销售收入")
_WAGE_ACCT_KWS = ("应付职工薪酬", "应付工资", "工资")
_IIT_ACCT_KWS = ("个人所得税", "应交个人所得税", "代扣代缴个人所得税")


def _num(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("￥", "").replace("¥", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def _month_of(text) -> Optional[str]:
    """从任意日期/期间文本提取 YYYY-MM。容错：2026-01-15 / 20260115 / 2026/1/15 / 2026年1月 / 2026-01。"""
    import re
    s = str(text or "")
    m = re.search(r"(20\d{2})\s*[-年/.]\s*(\d{1,2})", s)
    if m:
        mm = int(m.group(2))
        if 1 <= mm <= 12:
            return f"{m.group(1)}-{mm:02d}"
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 6:
        y, mm = int(digits[:4]), int(digits[4:6])
        if 2000 <= y <= 2099 and 1 <= mm <= 12:
            return f"{y}-{mm:02d}"
    return None


def _agg_period(month: str, kind: str) -> str:
    y, m = month.split("-")
    if kind == "month":
        return month
    if kind == "quarter":
        return f"{y}-Q{(int(m) - 1) // 3 + 1}"
    return y


def _first(row: Dict, keys) -> Any:
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return v
    return None


# ── 各方序列构建（返回 {month: amount}）────────────────────────────────
def _voucher_series(vouchers: List[Dict], acct_kws) -> Dict[str, float]:
    """序时账按科目关键词取贷方发生额，按月份汇总。"""
    out: Dict[str, float] = {}
    for v in vouchers or []:
        if not isinstance(v, dict):
            continue
        acct = str(v.get("account") or v.get("科目") or v.get("科目名称") or "")
        if not acct or not any(k in acct for k in acct_kws):
            continue
        m = _month_of(v.get("date") or v.get("凭证日期") or v.get("发生日期"))
        if not m:
            continue
        out[m] = out.get(m, 0.0) + _num(v.get("credit", v.get("贷方")))
    return out


def _invoice_series(invs: List[Dict]) -> Dict[str, float]:
    """开具发票按不含税金额（amount）按月汇总。"""
    out: Dict[str, float] = {}
    for i in invs or []:
        if not isinstance(i, dict):
            continue
        m = _month_of(_first(i, ("date", "invoice_date", "开票日期")))
        if not m:
            continue
        amt = _num(_first(i, ("amount", "金额", "不含税金额")))
        if amt == 0:
            tot = _num(_first(i, ("total", "价税合计", "total_amount")))
            amt = tot / 1.13 if tot else 0.0
        out[m] = out.get(m, 0.0) + amt
    return out


def _vat_decl_series(decls: List[Dict]) -> Dict[str, float]:
    """增值税申报表销售额（不含税）按月汇总。"""
    out: Dict[str, float] = {}
    for d in decls or []:
        if not isinstance(d, dict):
            continue
        if str(d.get("_declaration_type") or "").lower() not in ("vat", ""):
            continue
        sales = _num(d.get("sales_amount"))
        if sales <= 0:
            continue
        m = _month_of(d.get("period") or d.get("税款所属期") or d.get("期间"))
        if not m:
            continue
        out[m] = out.get(m, 0.0) + sales
    return out


def _salary_series(salaries: List[Dict]):
    """工资表 → ({月: 应发}, {月: 代扣个税})。月份取 period_start/period_end/所属期。"""
    gross: Dict[str, float] = {}
    tax: Dict[str, float] = {}
    for s in salaries or []:
        if not isinstance(s, dict):
            continue
        m = _month_of(_first(s, ("month", "所属期", "period", "period_start", "period_end", "税款所属期")))
        if not m:
            continue
        g = _num(_first(s, ("gross", "应发合计", "应发工资", "应发", "salary", "本期收入")))
        t = _num(_first(s, ("tax", "代扣个税", "个税", "个人所得税")))
        gross[m] = gross.get(m, 0.0) + g
        tax[m] = tax.get(m, 0.0) + t
    return gross, tax


def _ind_tax_decl_series(decls: List[Dict]):
    """个税申报表（通用表）→ ({月: 本月收入}, {月: 个税})。键名容错。"""
    income: Dict[str, float] = {}
    tax: Dict[str, float] = {}
    for d in decls or []:
        if not isinstance(d, dict):
            continue
        if str(d.get("_declaration_type") or "").lower() not in ("individual_tax", "iit", "ind_tax", ""):
            continue
        m = _month_of(_first(d, ("税款所属期", "所属期", "period", "期间", "月份", "period_start", "period_end")))
        if not m:
            continue
        inc = _num(_first(d, ("本月收入", "本期收入", "收入额", "收入", "工资薪金", "应纳税所得额")))
        t = _num(_first(d, ("本月个税", "个税", "应纳税额", "已缴税额", "本期应补(退)税额", "应补退税额", "税额")))
        if inc:
            income[m] = income.get(m, 0.0) + inc
        if t:
            tax[m] = tax.get(m, 0.0) + t
    return income, tax


# ── 对等校验 ─────────────────────────────────────────────────────────
_LABELS = {
    "vat_decl": "增值税申报表销售额",
    "voucher_rev": "序时账主营业务收入",
    "sal_inv": "开具发票金额",
    "fin_rev": "利润表收入",
    "salary_gross": "工资表应发",
    "ind_tax_income": "个税申报本月收入",
    "voucher_wage": "序时账计提工资",
    "salary_tax": "工资表代扣个税",
    "ind_tax_tax": "个税申报个税",
    "voucher_iit": "序时账计提个税",
}


def _fmt(v: float) -> str:
    return f"{v:,.2f}"


def _match(a: float, b: float) -> bool:
    return abs(a - b) <= max(_TOL_ABS, _TOL_REL * max(abs(a), abs(b)))


def _reconcile(sources: Dict[str, Dict[str, float]], kind: str,
               title: str, category: str, redline_id: str,
               policy_ref: str, tax_impact: str):
    """把多方序列按 period(kind) 对齐，逐期输出对等结论。返回 findings。"""
    # 聚合到目标粒度并合并
    agg: Dict[str, Dict[str, float]] = {}
    for name, series in sources.items():
        if not series:
            continue
        for m, amt in series.items():
            p = _agg_period(m, kind)
            agg.setdefault(p, {})[name] = agg.setdefault(p, {}).get(name, 0.0) + amt

    findings = []
    equal_lines = []
    mismatch_lines = []
    for p in sorted(agg):
        vals = agg[p]
        names = [n for n in sources if n in vals]
        if len(names) < 2:
            continue
        amounts = [vals[n] for n in names]
        spread = max(amounts) - min(amounts)
        desc = "；".join(f"{_LABELS.get(n, n)}{_fmt(vals[n])}" for n in names)
        if spread <= max(_TOL_ABS, _TOL_REL * max(abs(x) for x in amounts)):
            equal_lines.append(f"{p}：" + "＝".join(_fmt(v) for v in amounts))
        else:
            mismatch_lines.append((p, desc, spread, spread / max(abs(x) for x in amounts)))

    if equal_lines:
        findings.append({
            "type": f"对等勾稽一致：{title}",
            "level": "信息", "score": 1,
            "detail": f"经逐{kind == 'month' and '月' or ('季' if kind == 'quarter' else '年')}对齐，"
                      f"以下期间多方口径一致：{'；'.join(equal_lines[:12])}。",
            "description": f"{title} 在所列期间内各来源金额对等一致，可作为收入/薪酬真实性的一致印证。",
            "how_found": "将各来源按月份归集后升/降期聚合到" + ("月" if kind == "month" else ("季" if kind == "quarter" else "年")) + "，逐期比较各来源合计。",
            "tax_impact": "多方一致可降低收入/薪酬不实的风险。",
            "policy_ref": policy_ref,
            "suggestion": "保持各系统数据同步与一致。",
            "category": category, "source_chain": f"逐{kind}勾稽-一致",
            "redline_id": redline_id, "indicator": f"reconcile_equal_{kind}", "indicator_value": len(equal_lines),
        })
    for p, desc, spread, rel in mismatch_lines:
        findings.append({
            "type": f"待核事实：{title}逐{kind == 'month' and '月' or ('季' if kind == 'quarter' else '年')}不匹配（{p}）",
            "level": "待核验", "score": 5,
            "detail": f"{p} 各来源金额不一致：{desc}；差异{_fmt(spread)}元（{rel * 100:.1f}%）。",
            "description": f"同一口径在多个来源之间应相互对等；出现差异可能是口径（含税/不含税）、期间归属、"
                          f"跨期确认、或数据未同步所致，也可能指向申报/记账不实，须逐笔核实并编制差异调节表。",
            "how_found": f"按月份归集各方后聚合到" + ("月" if kind == "month" else ("季" if kind == "quarter" else "年")) + f"，{p} 各方差额超容差。",
            "tax_impact": tax_impact,
            "policy_ref": policy_ref,
            "suggestion": "编制该期间差异调节表，逐笔说明差异原因（含税口径/跨期/未同步/漏记），必要时补充申报或更正账务。",
            "category": category, "source_chain": f"逐{kind}勾稽-差异",
            "redline_id": redline_id, "indicator": f"reconcile_gap_{kind}", "indicator_value": round(spread, 2),
        })
    return findings


def run_cross_period_reconcile(data: Dict[str, Any]) -> List[Dict]:
    """跨文件逐月/季/年对等勾稽入口。返回 findings 列表（可能为空）。"""
    vouchers = data.get("vouchers") or []
    sal_invs = data.get("sal_invs") or []
    decls = data.get("tax_declarations") or data.get("declaration") or []
    salaries = data.get("salaries") or []

    if not (vouchers or sal_invs or decls or salaries):
        return []

    findings: List[Dict] = []

    # ── 家族一：收入（申报表 / 序时账主营收入 / 开具发票）──
    rev_sources = {
        "voucher_rev": _voucher_series(vouchers, _REV_ACCT_KWS),
        "sal_inv": _invoice_series(sal_invs),
        "vat_decl": _vat_decl_series(decls),
    }
    for _kind in ("month", "quarter", "year"):
        findings.extend(_reconcile(
            rev_sources, _kind, "收入多源对等",
            "收入真实性", "RL-INC-001",
            "《税收征收管理法》第二十五条（如实申报）；《增值税暂行条例》关于销售额申报的规定",
            "收入申报与账载、开票不一致，可能少申报销售额，面临补税及滞纳金风险。",
        ))

    # ── 家族二：工资（工资表应发 / 个税申报本月收入 / 序时账计提工资）──
    sal_gross, sal_tax = _salary_series(salaries)
    iit_income, iit_tax = _ind_tax_decl_series(decls)
    wage_sources = {
        "salary_gross": sal_gross,
        "ind_tax_income": iit_income,
        "voucher_wage": _voucher_series(vouchers, _WAGE_ACCT_KWS),
    }
    if sum(1 for s in wage_sources.values() if s) >= 2:
        for _kind in ("month", "year"):
            findings.extend(_reconcile(
                wage_sources, _kind, "工资多源对等",
                "个人所得税", "RL-PAY-005",
                "《个人所得税法》第十一条（扣缴义务人按月预扣预缴）；《社会保险法》关于缴费基数的规定",
                "工资与个税申报不一致，可能少代扣代缴个税或少缴社保，面临补税与社保稽核风险。",
            ))

    # ── 家族三：个税（工资表代扣个税 / 个税申报个税 / 序时账计提个税）──
    iit_sources = {
        "salary_tax": sal_tax,
        "ind_tax_tax": iit_tax,
        "voucher_iit": _voucher_series(vouchers, _IIT_ACCT_KWS),
    }
    if sum(1 for s in iit_sources.values() if s) >= 2:
        for _kind in ("month", "year"):
            findings.extend(_reconcile(
                iit_sources, _kind, "个税三源对等",
                "个人所得税", "RL-PAY-005",
                "《个人所得税法》第十一条；《税收征收管理法》关于代扣代缴义务的规定",
                "代扣个税与申报、账载不一致，可能少扣少缴个税，面临补税与滞纳金风险。",
            ))
    return findings

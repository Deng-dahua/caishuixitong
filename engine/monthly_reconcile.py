# -*- coding: utf-8 -*-
"""跨文件逐月对等勾稽引擎（2026-09-15 新增）。

把多份上传文件里的**同一口径**，按「月 / 季 / 年」对齐成序列，逐期校验"对等相等"，
输出可复算的对等表与差异待核线索。补齐此前缺口：
  - 收入四方：增值税申报表销售额 ↔ 序时账主营业务收入(贷方) ↔ 开具发票金额(不含税) ↔ 利润表收入
  - 工资四方：工资表应发 ↔ 个税申报本月收入 ↔ 序时账计提工资(应付职工薪酬贷方)
  - 个税三方：工资表代扣个税 ↔ 个税申报个税 ↔ 序时账计提个税(应交个人所得税贷方)
  - 应收发生额：开具发票(不含税) ↔ 序时账应收账款(借方)  —— 开票是否全部挂账
  - 应付发生额：取得发票(不含税) ↔ 序时账应付账款(贷方)  —— 采购发票是否全部挂账
  - 收入税价配比：序时账主营业务收入(贷方) × 适用税率 ↔ 销项税额(贷方) —— 税率适用/含税误记
  - 采购税价配比：取得发票(不含税) × 适用税率 ↔ 序时账进项税额(借方) —— 进项税率/价税分离
  - 固定资产：固定资产清单(原值/累计折旧) ↔ 科目余额表(1601/1602) —— 清单与账面账实相符

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


def _bare_month(v) -> Optional[int]:
    """序时账"记账月份"常只有月序（如 1/2/…12），返回 1..12；否则 None。"""
    s = "".join(ch for ch in str(v or "") if ch.isdigit())
    if s and len(s) <= 2:
        n = int(s)
        if 1 <= n <= 12:
            return n
    return None


def _infer_year(data: Dict[str, Any]) -> Optional[str]:
    """从其他来源（开具发票/申报表/工资表）推断年份，供"只有月序"的序时账对齐。"""
    from collections import Counter
    c = Counter()

    def _scan(rows, keys):
        for r in rows or []:
            if isinstance(r, dict):
                for k in keys:
                    m = _month_of(r.get(k))
                    if m:
                        c[m[:4]] += 1

    _scan(data.get("sal_invs"), ("date", "invoice_date", "开票日期"))
    _scan(data.get("pur_invs"), ("date", "invoice_date", "开票日期"))
    _scan(data.get("input_vat_deductions"), ("date", "开票日期", "勾选时间", "所属期"))
    _scan(data.get("vouchers"), ("date", "凭证日期", "发生日期"))
    _scan(data.get("tax_declarations"), ("period", "税款所属期", "期间"))
    _scan(data.get("salaries"), ("period_start", "period_end", "所属期", "month"))
    return c.most_common(1)[0][0] if c else None


def _first(row: Dict, keys) -> Any:
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return v
    return None


# ── 各方序列构建（返回 {month: amount}）────────────────────────────────
def _voucher_series(vouchers: List[Dict], acct_kws, year: Optional[str] = None,
                    side: str = "credit") -> Dict[str, float]:
    """序时账按科目（编码或名称）关键词取某方向发生额，按月份汇总。

    序时账常见表头为"记账月份｜…｜科目编码｜科目名称｜借方金额｜贷方金额"：
    科目可能只给编码（如 600102），月份可能只有月序（如 1）→ 用 year 补全年月。
    side="credit" 取贷方（收入/计提/负债），side="debit" 取借方（费用/进项/资产）。
    """
    out: Dict[str, float] = {}
    for v in vouchers or []:
        if not isinstance(v, dict):
            continue
        acct = " ".join(str(v.get(k) or "") for k in ("account", "account_name", "科目", "科目名称"))
        if not acct.strip() or not any(k in acct for k in acct_kws):
            continue
        m = _month_of(v.get("date") or v.get("凭证日期") or v.get("发生日期"))
        if not m:
            bm = _bare_month(v.get("month_no") or v.get("记账月份") or v.get("月份"))
            if bm and year:
                m = f"{year}-{bm:02d}"
        if not m:
            continue
        amt = _num(v.get(side, v.get("贷方" if side == "credit" else "借方")))
        out[m] = out.get(m, 0.0) + amt
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
        g = _num(_first(s, ("salary", "本期收入", "acc_income", "累计收入",
                            "gross", "应发合计", "应发工资", "应发")))
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


# ── 字段要点（增值税/银行/社保等）────────────────────────────────────
def _vat_decl_field_series(decls: List[Dict], field: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for d in decls or []:
        if not isinstance(d, dict):
            continue
        if str(d.get("_declaration_type") or "").lower() not in ("vat", ""):
            continue
        v = _num(d.get(field))
        if v <= 0:
            continue
        m = _month_of(d.get("period") or d.get("税款所属期") or d.get("期间"))
        if not m:
            continue
        out[m] = out.get(m, 0.0) + v
    return out


def _invoice_tax_series(invs: List[Dict]) -> Dict[str, float]:
    """发票税额按月汇总（销项/进项通用，用 tax 字段）。"""
    out: Dict[str, float] = {}
    for i in invs or []:
        if not isinstance(i, dict):
            continue
        m = _month_of(_first(i, ("date", "invoice_date", "开票日期")))
        if not m:
            continue
        out[m] = out.get(m, 0.0) + _num(_first(i, ("tax", "税额")))
    return out


def _deduction_tax_series(rows: List[Dict]) -> Dict[str, float]:
    """抵扣认证（勾选平台）有效抵扣税额按月汇总。"""
    out: Dict[str, float] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        m = _month_of(_first(r, ("date", "开票日期", "勾选时间", "所属期")))
        if not m:
            continue
        out[m] = out.get(m, 0.0) + _num(_first(r, ("deductible_tax", "有效抵扣税额", "tax", "税额")))
    return out


def _bank_series(bank: List[Dict]):
    """银行流水 → ({月: 收入合计}, {月: 支出合计})。"""
    credit: Dict[str, float] = {}
    debit: Dict[str, float] = {}
    for t in bank or []:
        if not isinstance(t, dict):
            continue
        m = _month_of(_first(t, ("date", "交易日期", "记账日期", "发生日期")))
        if not m:
            continue
        c = _num(_first(t, ("credit", "贷方金额", "收入金额", "贷方")))
        d = _num(_first(t, ("debit", "借方金额", "支出金额", "借方")))
        if c:
            credit[m] = credit.get(m, 0.0) + c
        if d:
            debit[m] = debit.get(m, 0.0) + d
    return credit, debit


def _fund_series(rows: List[Dict]) -> Dict[str, float]:
    """住房公积金明细（通用表）→ {月: 缴存额合计}。"""
    out: Dict[str, float] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        m = _month_of(_first(r, ("counterparty", "缴存月份", "period", "月份", "所属期")))
        if not m:
            continue
        out[m] = out.get(m, 0.0) + _num(_first(r, ("amount_col", "单位缴存额", "单位缴存", "total", "amount")))
    return out


def _social_series(rows: List[Dict]) -> Dict[str, float]:
    """社保明细 → {月: 应缴合计}（过滤表头行）。"""
    out: Dict[str, float] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        nm = str(r.get("name") or "")
        if not nm or nm in ("姓名", "合计", "小计", "总计"):
            continue
        m = _month_of(_first(r, ("period_start", "period_end", "费款所属期起", "所属期")))
        if not m:
            continue
        amt = _num(_first(r, ("due_amount", "应缴费额", "应缴金额")))
        if amt <= 0:
            amt = _num(r.get("company_pay")) + _num(r.get("personal_pay"))
        out[m] = out.get(m, 0.0) + amt
    return out


def _fixed_asset_series(rows: List[Dict]):
    """固定资产清单（通用表，字段随企业格式变）→ (原值合计, 累计折旧合计)。

    按关键词匹配列，做到格式无关：原值优先取「原值/资产原值/入账价值/购置价值」，
    缺失时用「净值+累计折旧」回推；累计折旧取「累计折旧/折旧额」。
    """
    gross = 0.0
    accum = 0.0
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        g = _num(_first(r, ("原值", "资产原值", "入账价值", "购置价值", "资产价值", "原值金额")))
        if g <= 0:
            net = _num(_first(r, ("净值", "资产净值", "账面净值")))
            dep = _num(_first(r, ("累计折旧", "折旧额")))
            if net > 0 and dep > 0:
                g = net + dep
        accum += _num(_first(r, ("累计折旧", "折旧额", "累计折旧额")))
        gross += g
    return gross, accum


def _tb_balance(trial_balance: List[Dict], code_prefix: str):
    """科目余额表按一级科目前缀（如 "1601"）汇总期末借/贷余额。返回 (close_debit, close_credit)。"""
    d = c = 0.0
    for r in trial_balance or []:
        if not isinstance(r, dict):
            continue
        digits = "".join(ch for ch in str(r.get("code") or r.get("科目编码") or "") if ch.isdigit())
        if not digits.startswith(code_prefix):
            continue
        cd = _num(r.get("close_debit", r.get("期末借方")))
        cc = _num(r.get("close_credit", r.get("期末贷方")))
        if cd == 0 and cc == 0:
            bal = _num(r.get("close_balance", r.get("期末余额")))
            if str(r.get("direction") or r.get("余额方向") or "").startswith(("借", "dr", "D")):
                d += bal
            else:
                c += bal
        else:
            d += cd
            c += cc
    return d, c


_OUTPUT_VAT_KWS = ("销项税额",)
_INPUT_VAT_KWS = ("进项税额",)
_BANK_ACCT_KWS = ("银行存款", "1002")
_SOCIAL_KWS = ("社会保险费", "社保", "社会保险")
_FUND_KWS = ("住房公积金",)


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
    "vat_decl_sales_tax": "申报表销项税额",
    "sal_inv_tax": "开具发票税额",
    "voucher_output_vat": "序时账销项税额",
    "vat_decl_input_tax": "申报表进项税额",
    "pur_inv_tax": "进项发票税额",
    "deduction_tax": "抵扣认证税额",
    "voucher_input_vat": "序时账进项税额",
    "bank_credit": "银行收款",
    "voucher_bank_debit": "序时账银行存款借方",
    "bank_debit": "银行付款",
    "voucher_bank_credit": "序时账银行存款贷方",
    "social": "社保应缴合计",
    "voucher_social": "序时账社保",
    "fund": "公积金缴存合计",
    "voucher_fund": "序时账住房公积金",
    "sal_inv_ar": "开具发票金额(不含税)",
    "voucher_ar": "序时账应收账款(借方)",
    "pur_inv_ap": "取得发票金额(不含税)",
    "voucher_ap": "序时账应付账款(贷方)",
}

_AR_ACCT_KWS = ("应收账款", "1122")
_AP_ACCT_KWS = ("应付账款", "2202")

# 常见增值税征收率（不含税口径）及其含税等价率（税额÷含税金额 = c/(1+c)），
# 用于"税价配比"勾稽：收入/采购若按含税金额入账，隐含率会落在含税等价区间。
_CANON_RATES = (0.01, 0.03, 0.05, 0.06, 0.09, 0.13)
_CANON_RATES_INCL = tuple(round(c / (1 + c), 4) for c in _CANON_RATES)
_RATE_TOL = 0.015  # 1.5 个百分点


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


def _point_reconcile(val_a: float, val_b: float, label_a: str, label_b: str,
                     title: str, category: str, redline_id: str,
                     policy_ref: str, tax_impact: str) -> List[Dict]:
    """单点（时点）对等：两方总额比对，容差内出一致、超容差出待核。用于固定资产清单 vs 账面等。"""
    if val_a <= 0 or val_b <= 0:
        return []
    spread = abs(val_a - val_b)
    if spread <= max(_TOL_ABS, _TOL_REL * max(abs(val_a), abs(val_b))):
        return [{
            "type": f"对等勾稽一致：{title}",
            "level": "信息", "score": 1,
            "detail": f"{label_a}{_fmt(val_a)} 与 {label_b}{_fmt(val_b)} 一致（差异{_fmt(spread)}）。",
            "description": f"{title} 两来源金额对等一致。",
            "how_found": f"将 {label_a} 与 {label_b} 直接比对，差额≤容差。",
            "tax_impact": "两来源一致可降低资产/折旧不实的风险。",
            "policy_ref": policy_ref,
            "suggestion": "保持资产台账与账面同步。",
            "category": category, "source_chain": "时点勾稽-一致",
            "redline_id": redline_id, "indicator": "point_equal", "indicator_value": round(spread, 2),
        }]
    return [{
        "type": f"待核事实：{title}不一致",
        "level": "待核验", "score": 6,
        "detail": f"{label_a}{_fmt(val_a)} 与 {label_b}{_fmt(val_b)} 不一致，差异{_fmt(spread)}元（{spread / max(abs(val_a), abs(val_b)) * 100:.1f}%）。",
        "description": "固定资产清单与科目余额表应一致。不一致可能源于漏记资产、折旧计提差异、"
                       "资产类别归集错误或账外资产，须逐卡核对。",
        "how_found": f"将 {label_a} 与 {label_b} 直接比对，差额超容差。",
        "tax_impact": tax_impact,
        "policy_ref": policy_ref,
        "suggestion": "编制固定资产台账与科目余额表的差异调节表，逐卡说明差异原因。",
        "category": category, "source_chain": "时点勾稽-差异",
        "redline_id": redline_id, "indicator": "point_gap", "indicator_value": round(spread, 2),
    }]


def _rate_consistency(base: Dict[str, float], tax: Dict[str, float],
                       title: str, category: str, redline_id: str,
                       policy_ref: str, tax_impact: str) -> List[Dict]:
    """税价配比（派生对等）：逐月 税额 ÷ 计税基础 = 隐含征收率，与常见税率(含/不含税口径)比对。

    用于发现：收入/成本按含税金额入账、税率适用错误、小规模与一般纳税人混淆、进项票未按规则抵扣。
    仅对"两方同月均非零"的月份判定；偏差 ≤1.5pp 视为一致。返回 findings。
    """
    monthly: Dict[str, float] = {}
    for m in set(base) | set(tax):
        b = base.get(m, 0.0)
        t = tax.get(m, 0.0)
        if b > 0 and t > 0:
            monthly[m] = t / b
    if not monthly:
        return []
    ok, bad = [], []
    for m, r in sorted(monthly.items()):
        if any(abs(r - c) <= _RATE_TOL for c in _CANON_RATES) or \
           any(abs(r - c) <= _RATE_TOL for c in _CANON_RATES_INCL):
            ok.append((m, r))
        else:
            bad.append((m, r))
    findings: List[Dict] = []
    if ok and not bad:
        findings.append({
            "type": f"对等勾稽一致：{title}",
            "level": "信息", "score": 1,
            "detail": f"逐月按税额÷计税基础计算隐含征收率，均在常见税率区间："
                      + "；".join(f"{m}≈{r*100:.1f}%" for m, r in ok[:12]) + "。",
            "description": f"{title} 各月税价配比合理，无明显税率错配或收入含税误记。",
            "how_found": "逐月计算 销项(进项)税额 ÷ 主营业务收入(取得发票不含税)，与 1%/3%/5%/6%/9%/13% "
                         "及其含税等价率比对，偏差≤1.5pp 视为一致。",
            "tax_impact": "税价配比一致可降低税率适用错误与收入含税误记风险。",
            "policy_ref": policy_ref,
            "suggestion": "保持税率适用与价税分离准确。",
            "category": category, "source_chain": "税价配比-一致",
            "redline_id": redline_id, "indicator": "rate_consistent", "indicator_value": len(ok),
        })
    for m, r in bad:
        findings.append({
            "type": f"待核事实：{title}异常（{m}）",
            "level": "待核验", "score": 5,
            "detail": f"{m} 隐含征收率 {r*100:.1f}%，偏离常见税率区间。",
            "description": "税额与计税基础的配比应落在适用税率附近；明显偏离可能源于收入/成本按含税金额入账、"
                          "税率适用错误、小规模与一般纳税人混淆，或进项税票未按规则抵扣，须核实。",
            "how_found": f"逐月计算税额÷计税基础，{m} 结果 {r*100:.1f}% 与所有常见税率(含含税等价)偏差>1.5pp。",
            "tax_impact": tax_impact,
            "policy_ref": policy_ref,
            "suggestion": "核对该月凭证的价税分离与税率适用，必要时调整账务或补充申报。",
            "category": category, "source_chain": "税价配比-异常",
            "redline_id": redline_id, "indicator": "rate_anomaly", "indicator_value": round(r, 4),
        })
    return findings


def run_cross_period_reconcile(data: Dict[str, Any]) -> List[Dict]:
    """跨文件逐月/季/年对等勾稽入口。返回 findings 列表（可能为空）。"""
    vouchers = data.get("vouchers") or []
    sal_invs = data.get("sal_invs") or []
    decls = data.get("tax_declarations") or data.get("declaration") or []
    salaries = data.get("salaries") or []
    pur_invs = data.get("pur_invs") or []
    input_vat_deductions = data.get("input_vat_deductions") or []
    bank_txs = data.get("bank_txs") or []
    social = data.get("social_security") or []
    fund = data.get("housing_fund") or []
    fixed_assets = data.get("fixed_assets") or []
    trial_balance = data.get("trial_balance") or []

    if not (vouchers or sal_invs or decls or salaries or pur_invs or bank_txs
            or fixed_assets or trial_balance):
        return []

    findings: List[Dict] = []
    year = _infer_year(data)   # 序时账"记账月份"常只有月序，用其他来源的年份补齐

    # ── 家族一：收入（申报表 / 序时账主营收入 / 开具发票）──
    rev_sources = {
        "voucher_rev": _voucher_series(vouchers, _REV_ACCT_KWS, year),
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
        "voucher_wage": _voucher_series(vouchers, _WAGE_ACCT_KWS, year),
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
        "voucher_iit": _voucher_series(vouchers, _IIT_ACCT_KWS, year),
    }
    if sum(1 for s in iit_sources.values() if s) >= 2:
        for _kind in ("month", "year"):
            findings.extend(_reconcile(
                iit_sources, _kind, "个税三源对等",
                "个人所得税", "RL-PAY-005",
                "《个人所得税法》第十一条；《税收征收管理法》关于代扣代缴义务的规定",
                "代扣个税与申报、账载不一致，可能少扣少缴个税，面临补税与滞纳金风险。",
            ))

    # ── 家族四：增值税销项税额（申报表 ↔ 开具发票 ↔ 序时账 销项税额）──
    out_vat = {
        "sal_inv_tax": _invoice_tax_series(sal_invs),
        "vat_decl_sales_tax": _vat_decl_field_series(decls, "sales_tax"),
        "voucher_output_vat": _voucher_series(vouchers, _OUTPUT_VAT_KWS, year, side="credit"),
    }
    if sum(1 for s in out_vat.values() if s) >= 2:
        for _kind in ("month", "year"):
            findings.extend(_reconcile(
                out_vat, _kind, "增值税销项税额对等", "增值税", "RL-VAT-001",
                "《增值税暂行条例》关于销项税额申报的规定；增值税申报表附表一",
                "销项税额在申报表、开具发票与账载之间不一致，可能少计少缴增值税。",
            ))

    # ── 家族五：增值税进项税额（申报表 ↔ 进项发票 ↔ 抵扣认证 ↔ 序时账 进项税额）──
    in_vat = {
        "pur_inv_tax": _invoice_tax_series(pur_invs),
        "deduction_tax": _deduction_tax_series(input_vat_deductions),
        "vat_decl_input_tax": _vat_decl_field_series(decls, "input_tax"),
        "voucher_input_vat": _voucher_series(vouchers, _INPUT_VAT_KWS, year, side="debit"),
    }
    if sum(1 for s in in_vat.values() if s) >= 2:
        for _kind in ("month", "year"):
            findings.extend(_reconcile(
                in_vat, _kind, "增值税进项税额对等", "增值税", "RL-VAT-002",
                "《增值税暂行条例》第八条、第九条关于进项税额抵扣的规定",
                "进项税额在申报、发票、认证与账载之间不一致，可能多抵或少抵进项税额。",
            ))

    # ── 家族六：银行存款（银行流水 ↔ 序时账 银行存款 借/贷）──
    bank_credit, bank_debit = _bank_series(bank_txs)
    _vbank_debit = _voucher_series(vouchers, _BANK_ACCT_KWS, year, side="debit")
    _vbank_credit = _voucher_series(vouchers, _BANK_ACCT_KWS, year, side="credit")
    if bank_credit and _vbank_debit:
        findings.extend(_reconcile(
            {"bank_credit": bank_credit, "voucher_bank_debit": _vbank_debit},
            "month", "银行存款收入方对等", "资金流", "RL-INC-001",
            "《企业会计准则》关于货币资金核算的规定",
            "银行收款与账面银行存款借方不一致，可能存在未入账收款或跨期。",
        ))
    if bank_debit and _vbank_credit:
        findings.extend(_reconcile(
            {"bank_debit": bank_debit, "voucher_bank_credit": _vbank_credit},
            "month", "银行存款支出方对等", "资金流", "RL-COST-003",
            "《企业会计准则》关于货币资金核算的规定",
            "银行付款与账面银行存款贷方不一致，可能存在账外支付或跨期。",
        ))

    # ── 家族七：社保 / 公积金（明细 ↔ 序时账 费用侧）──
    if social:
        s_src = {"social": _social_series(social),
                 "voucher_social": _voucher_series(vouchers, _SOCIAL_KWS, year, side="debit")}
        if sum(1 for s in s_src.values() if s) >= 2:
            findings.extend(_reconcile(
                s_src, "month", "社保缴纳对等", "社保", "RL-PAY-005",
                "《社会保险法》关于缴费的规定",
                "社保应缴与账面社保费用不一致，可能存在补缴/漏缴或口径差异。",
            ))
    if fund:
        f_src = {"fund": _fund_series(fund),
                 "voucher_fund": _voucher_series(vouchers, _FUND_KWS, year, side="debit")}
        if sum(1 for s in f_src.values() if s) >= 2:
            findings.extend(_reconcile(
                f_src, "month", "公积金缴存对等", "住房公积金", "RL-PAY-005",
                "《住房公积金管理条例》关于缴存的规定",
                "公积金缴存与账面不一致，可能存在少缴或口径差异。",
            ))

    # ── 家族八：应收账款发生额（开具发票不含税 ↔ 序时账 应收账款 借方）──
    ar_sources = {
        "sal_inv_ar": _invoice_series(sal_invs),
        "voucher_ar": _voucher_series(vouchers, _AR_ACCT_KWS, year, side="debit"),
    }
    if sum(1 for s in ar_sources.values() if s) >= 2:
        for _kind in ("month", "year"):
            findings.extend(_reconcile(
                ar_sources, _kind, "应收账款发生额对等", "收入真实性", "RL-INC-001",
                "《企业会计准则》关于应收账款核算的规定；《增值税暂行条例》关于销售额申报的规定",
                "开票金额与账面应收账款借方不一致，可能开票未入账、挂错科目，或存在未开票收入/无票销售，"
                "进而影响收入确认与增值税申报完整性。",
            ))

    # ── 家族九：应付账款发生额（取得发票不含税 ↔ 序时账 应付账款 贷方）──
    ap_sources = {
        "pur_inv_ap": _invoice_series(pur_invs),
        "voucher_ap": _voucher_series(vouchers, _AP_ACCT_KWS, year, side="credit"),
    }
    if sum(1 for s in ap_sources.values() if s) >= 2:
        for _kind in ("month", "year"):
            findings.extend(_reconcile(
                ap_sources, _kind, "应付账款发生额对等", "成本费用", "RL-COST-003",
                "《企业会计准则》关于应付账款核算的规定；《增值税暂行条例》关于进项税额抵扣的规定",
                "取得发票与账面应付账款贷方不一致，可能发票未入账、暂估差异或取得虚开发票挂账，"
                "影响成本列支与进项税额抵扣的真实性。",
            ))

    # ── 家族十：收入税价配比（序时账 主营业务收入 ↔ 销项税额）──
    _rev_base = _voucher_series(vouchers, _REV_ACCT_KWS, year)
    _out_tax = _voucher_series(vouchers, _OUTPUT_VAT_KWS, year, side="credit")
    if _rev_base and _out_tax:
        findings.extend(_rate_consistency(
            _rev_base, _out_tax, "收入税价配比", "增值税", "RL-VAT-001",
            "《增值税暂行条例》关于销售额与销项税额的规定",
            "收入与销项税额配比异常，可能收入含税误记或税率适用错误，影响增值税申报准确性。",
        ))

    # ── 家族十一：采购税价配比（取得发票不含税 ↔ 序时账 进项税额）──
    _pur_base = _invoice_series(pur_invs)
    _in_tax = _voucher_series(vouchers, _INPUT_VAT_KWS, year, side="debit")
    if _pur_base and _in_tax:
        findings.extend(_rate_consistency(
            _pur_base, _in_tax, "采购税价配比", "增值税", "RL-VAT-002",
            "《增值税暂行条例》第八条关于进项税额抵扣的原则规定",
            "采购与进项税额配比异常，可能取得发票未分离价税、税率适用错误或违规抵扣。",
        ))

    # ── 家族十二：固定资产清单 ↔ 科目余额表（原值 / 累计折旧，时点勾稽）──
    if fixed_assets and trial_balance:
        fa_gross, fa_accum = _fixed_asset_series(fixed_assets)
        tb_fa_d, _ = _tb_balance(trial_balance, "1601")       # 固定资产(1601) 借方余额=原值
        _, tb_dep_c = _tb_balance(trial_balance, "1602")       # 累计折旧(1602) 贷方余额
        if fa_gross > 0 and tb_fa_d > 0:
            findings.extend(_point_reconcile(
                fa_gross, tb_fa_d, "固定资产清单原值合计", "科目余额表固定资产(1601)借方余额",
                "固定资产原值勾稽", "资产账实", "RL-COST-003",
                "《企业会计准则》关于固定资产核算的规定；《会计法》关于账实相符的规定",
                "固定资产账实不符将影响折旧、资产税务处理与企业所得税扣除基数。",
            ))
        if fa_accum > 0 and tb_dep_c > 0:
            findings.extend(_point_reconcile(
                fa_accum, tb_dep_c, "固定资产清单累计折旧合计", "科目余额表累计折旧(1602)贷方余额",
                "累计折旧勾稽", "资产账实", "RL-COST-003",
                "《企业会计准则》关于固定资产折旧的规定",
                "累计折旧账实不符将影响折旧费用与企业所得税扣除。",
            ))
    return findings


def run_ledger_reconcile(vouchers: List[Dict], trial_balance: List[Dict]) -> List[Dict]:
    """账账相符：序时账（按一级科目汇总本期借/贷发生额）↔ 科目余额表（本期发生额）。

    返回 findings（逐科目差异汇总为一条）。不足数据不输出。
    """
    if not vouchers or not trial_balance:
        return []
    led: Dict[str, List[float]] = {}
    for v in vouchers or []:
        if not isinstance(v, dict):
            continue
        digits = "".join(ch for ch in str(v.get("account") or v.get("科目编码") or "") if ch.isdigit())
        if len(digits) < 4:
            continue
        d = led.setdefault(digits[:4], [0.0, 0.0])
        d[0] += _num(v.get("debit", v.get("借方")))
        d[1] += _num(v.get("credit", v.get("贷方")))
    tb: Dict[str, Any] = {}
    for r in trial_balance or []:
        if not isinstance(r, dict):
            continue
        digits = "".join(ch for ch in str(r.get("code") or r.get("科目编码") or "") if ch.isdigit())
        if len(digits) < 4:
            continue
        tb[digits[:4]] = (_num(r.get("current_debit", r.get("本期借方"))),
                          _num(r.get("current_credit", r.get("本期贷方"))),
                          str(r.get("name") or r.get("科目名称") or ""))
    diffs = []
    for k in sorted(set(led) | set(tb)):
        ld, lc = led.get(k, (0.0, 0.0))
        td, tc, nm = tb.get(k, (0.0, 0.0, ""))
        tol = max(_TOL_ABS, _TOL_REL * max(abs(ld), abs(td), abs(lc), abs(tc), 1.0))
        if abs(ld - td) <= tol and abs(lc - tc) <= tol:
            continue
        diffs.append((k, nm, ld, td, lc, tc))
    if not diffs:
        return []
    lines = "；".join(
        f"{k}({nm or '?'}) 序时账借{ld:,.0f}/贷{lc:,.0f} vs 余额表借{td:,.0f}/贷{tc:,.0f}"
        for k, nm, ld, td, lc, tc in diffs[:8])
    return [{
        "type": "待核事实：序时账与科目余额表逐科目不一致（账账不符）",
        "level": "待核验", "score": 6,
        "detail": f"序时账按一级科目汇总的本期发生额与科目余额表「本期发生额」存在差异，涉及 {len(diffs)} 个科目：{lines}。",
        "description": "序时账（记账凭证）与科目余额表应逐科目勾稽一致。不一致可能源于汇总口径（含/不含下级科目、"
                       "含/不含结转）、期间归属或漏记，也可能指向账务处理错误，须逐科目核对。",
        "how_found": "序时账按一级科目编码汇总本期借/贷发生额，与科目余额表本期发生额逐科目比较，差额超容差者列示。",
        "tax_impact": "账账不符将影响各税种申报基数与账簿记录的准确性。",
        "policy_ref": "《会计法》关于会计核算真实完整的规定；《企业会计准则》关于账簿记录的规定",
        "suggestion": "逐科目编制序时账与科目余额表的差异调节表，查明口径差异或补记凭证。",
        "category": "账账相符", "source_chain": "账账-序时账vs科目余额表",
        "redline_id": "RL-COST-003", "indicator": "ledger_vs_trial_balance_gap",
        "indicator_value": len(diffs),
    }]

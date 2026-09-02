"""两税收入差异比对引擎 —— 第四阶 P0 能力。

背景：数电票 + 申报自动预填 + 一窗式比对下，"已开票未申报"差异已被税局系统焊死，
企业无法在增值税申报表层面隐匿已开票收入。但**增值税申报收入 vs 企业所得税申报收入**
之间仍可能存在重大背离，且这一背离税局不会自动拦截（两税分属不同申报表、自动预填互不校验）：

  - 增值税销售额（主表"按适用税率计税销售额"，已含未开票收入）应 ≥ 企业所得税营业收入。
  - 若增值税销售额 显著高于 企业所得税营业收入（>10%），强烈指向所得税少计收入 / 隐匿利润
    （把应税收入只报了增值税、却在所得税申报时砍掉）。这是风险检查第二阶必查的"两税差异"红线。
  - 若企业所得税营业收入 显著高于 增值税销售额，多为正常（含不征税收入、投资收益、以前年度
    收入、视同销售等），但必须提供两税收入调节表说明差异来源；若差异源自应税收入，则反过来
    疑增值税少计。

本模块作为独立 capability（与 bank_flow / external_verifier 同构），从 tax_declarations 中
稳健抽取两税收入口径并量化差异，输出 comprehensive["two_tax_income"]。

输入：
  tax_declarations : pipeline 已收集的全部纳税申报表（VAT 用 declaration 字典带 sales_amount；
                     CIT 用通用行带 _declaration_type="cit_declaration"）
  vat_sales        : 增值税申报销售额合计（可选，优先；None 时从 tax_declarations 抽取）
  cit_income       : 企业所得税申报营业收入合计（可选，优先；None 时从 tax_declarations 抽取）
  company_name     : 企业名称

输出：与 external_verifier / bank_flow 对齐的 dict（available/summary/body/metrics/signals/verdict...）。
"""

import time

# 企业所得税营业收入在通用申报表行里的标签关键词（按优先级）
_INCOME_LABELS = ("营业收入", "收入总额", "主营业务收入", "营业总收入")

# 差异判定阈值
_DIFF_WARN_RATIO = 1.10      # 两税收入偏离 >10% 触发信号
_DIFF_HIGH_RATIO = 1.30      # 偏离 >30% 且差额≥10万 → 高风险
_DIFF_HIGH_ABS = 100000.0


def _safe(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def _cit_income_from_row(row):
    """从 CIT 通用申报行（项目/金额 或 项目/本年金额/上年金额）抽取营业收入数值。"""
    if not isinstance(row, dict):
        return 0.0
    # 找出标签列（值为字符串且含收入标签）
    label_keys = [k for k, v in row.items()
                  if isinstance(v, str) and any(lb in v for lb in _INCOME_LABELS)]
    if not label_keys:
        return 0.0
    # 其余列里取最大数值（"本年金额"通常最大，且排除标签字符串列）
    best = 0.0
    for k, v in row.items():
        if k in label_keys:
            continue
        nv = _safe(v)
        if nv > best:
            best = nv
    return best


def _extract_from_tax_declarations(tax_declarations):
    """从 tax_declarations 抽取 (vat_sales, vat_periods, cit_income, cit_found)。"""
    vat_sales = 0.0
    vat_periods = 0
    cit_income = 0.0
    cit_found = False
    for d in (tax_declarations or []):
        if not isinstance(d, dict):
            continue
        dt = d.get("_declaration_type", "")
        if dt == "cit_declaration":
            v = _cit_income_from_row(d)
            if v > 0:
                cit_income += v
                cit_found = True
        elif dt == "vat_declaration":
            s = _safe(d.get("sales_amount"))
            if s > 0:
                vat_sales += s
                vat_periods += 1
        else:
            # VAT 申报表以 declaration 字典形式存入（带 sales_amount，无 _declaration_type）
            if "sales_amount" in d:
                s = _safe(d.get("sales_amount"))
                if s > 0:
                    vat_sales += s
                    vat_periods += 1
    return vat_sales, vat_periods, cit_income, cit_found


def run_two_tax_compare(tax_declarations=None, vat_sales=None, cit_income=None, company_name=""):
    """比对增值税申报销售额 vs 企业所得税申报营业收入，量化偏离。返回与 bank_flow 对齐的 dict。"""
    # 解析输入
    if vat_sales is None or cit_income is None:
        ev, evp, ei, eif = _extract_from_tax_declarations(tax_declarations)
        if vat_sales is None:
            vat_sales = ev
        if cit_income is None:
            cit_income = ei
    vat_sales = _safe(vat_sales)
    cit_income = _safe(cit_income)

    if vat_sales <= 0 and cit_income <= 0:
        return {
            "available": False,
            "ok": True,
            "title": "增值税收入 vs 企业所得税收入差异比对",
            "summary": "本轮未提供增值税申报表与企业所得税申报表。",
            "body": "增值税申报销售额与企业所得税申报营业收入的勾稽，是数电票时代暴露所得税少计收入、"
                    "隐匿利润的第二条主线证据（第一主线为银行资金流）。两税分属不同申报表、自动预填互不校验，"
                    "税局不会自动拦截其背离。未提供两税申报表则无法做此比对。",
            "metrics": {},
            "signals": [],
            "verdict": "未提供两税申报表",
            "recommendation": "上传增值税纳税申报表与企业所得税纳税申报表（年度汇算清缴/季度预缴均可），"
                              "系统将自动抽取两税收入口径并量化差异。",
            "note": "两税收入差异比对结论属「待证线索」，需结合收入确认政策与纳税调整底稿核实，不作为定性依据。",
        }

    # 仅取得一张申报表：降级比对，仍可提示
    only_vat = vat_sales > 0 and cit_income <= 0
    only_cit = cit_income > 0 and vat_sales <= 0

    signals = []
    sev_high = False
    sev_mid = False

    if vat_sales > 0 and cit_income > 0:
        diff = vat_sales - cit_income
        diff_pct = (diff / cit_income * 100.0) if cit_income else 0.0
        if vat_sales > cit_income:
            # 增值税销售额 > 所得税营业收入：所得税少计收入嫌疑（红线方向）
            if vat_sales / cit_income >= _DIFF_WARN_RATIO:
                gap = diff
                if vat_sales / cit_income >= _DIFF_HIGH_RATIO and gap >= _DIFF_HIGH_ABS:
                    sev_high = True
                else:
                    sev_mid = True
                signals.append({
                    "signal": f"增值税申报销售额{vat_sales:,.2f}元，高于企业所得税申报营业收入{cit_income:,.2f}元，"
                              f"差额{diff:,.2f}元（偏离{diff_pct:.1f}%）",
                    "hint": "增值税销售额（含未开票收入）原则上应≥所得税营业收入；反向背离超过10%疑所得税少计收入/"
                            "隐匿利润。需逐笔核实收入确认口径、未开票收入是否同步计入所得税、是否存在不应税但已报增值税的收入。",
                })
            else:
                signals.append({
                    "signal": f"增值税销售额{vat_sales:,.2f}元 与 企业所得税营业收入{cit_income:,.2f}元 基本一致（偏离{diff_pct:.1f}%）",
                    "hint": "两税收入口径基本一致，仍须结合未开票收入、视同销售等确认完整性。",
                })
        elif cit_income > vat_sales:
            # 所得税收入 > 增值税：多为正常，但需调节表
            rev_ratio = cit_income / vat_sales if vat_sales else 0.0
            if rev_ratio >= _DIFF_WARN_RATIO:
                sev_mid = True
                signals.append({
                    "signal": f"企业所得税申报营业收入{cit_income:,.2f}元，高于增值税申报销售额{vat_sales:,.2f}元，"
                              f"差额{-diff:,.2f}元（偏离{abs(diff_pct):.1f}%）",
                    "hint": "所得税收入高于增值税多为正常（含不征税收入、免税收入、投资收益、以前年度收入、视同销售等），"
                            "但必须提供两税收入调节表说明差异来源；若差异实质来自增值税应税收入，则反向疑增值税少计。",
                })
            else:
                signals.append({
                    "signal": f"企业所得税营业收入{cit_income:,.2f}元 与 增值税销售额{vat_sales:,.2f}元 基本一致（偏离{abs(diff_pct):.1f}%）",
                    "hint": "两税收入口径基本一致，仍须结合收入确认政策确认。",
                })
        else:
            signals.append({
                "signal": f"增值税销售额与企业所得税营业收入相等（{vat_sales:,.2f}元）",
                "hint": "两税收入口径一致，结合资金流与未开票收入确认完整性。",
            })
    elif only_vat:
        sev_mid = True
        signals.append({
            "signal": f"仅取得增值税申报表（销售额{vat_sales:,.2f}元），未取得企业所得税申报表",
            "hint": "无法做两税勾稽。所得税申报表是验证收入完整性的核心资料，请补充上传。",
        })
    elif only_cit:
        sev_mid = True
        signals.append({
            "signal": f"仅取得企业所得税申报表（营业收入{cit_income:,.2f}元），未取得增值税申报表",
            "hint": "无法做两税勾稽。增值税申报表是自动预填销项的基础，请补充上传。",
        })

    if sev_high:
        verdict = "增值税销售额显著高于所得税营业收入，疑所得税少计收入"
    elif sev_mid:
        verdict = "两税收入存在差异，需核实口径"
    else:
        verdict = "两税收入基本一致"

    metrics = {
        "vat_sales": round(vat_sales, 2),
        "cit_income": round(cit_income, 2),
        "diff": round(vat_sales - cit_income, 2),
        "diff_pct": round((vat_sales - cit_income) / cit_income * 100.0, 2) if cit_income else None,
        "vat_over_cit": round(vat_sales - cit_income, 2),
        "only_one_side": bool(only_vat or only_cit),
    }

    lines = []
    lines.append(f"增值税申报销售额合计：{vat_sales:,.2f}元" + ("（未取得）" if vat_sales <= 0 else ""))
    lines.append(f"企业所得税申报营业收入合计：{cit_income:,.2f}元" + ("（未取得）" if cit_income <= 0 else ""))
    if vat_sales > 0 and cit_income > 0:
        d = vat_sales - cit_income
        lines.append(f"两税收入差额（增值税−所得税）：{d:,.2f}元（偏离{(d / cit_income * 100.0) if cit_income else 0:.1f}%）")
        if d > 0:
            lines.append("判定：增值税销售额 > 所得税营业收入 → 所得税少计收入风险（红线方向）。")
        else:
            lines.append("判定：所得税营业收入 > 增值税销售额 → 多为正常，需提供两税收入调节表。")
    body = "\n".join(lines)

    if only_vat or only_cit:
        recommendation = ("系统已就取得的一张申报表给出提示。下一步：补充另一张申报表后重跑分析，"
                          "系统将自动完成两税收入勾稽并量化差异；差异>10%须附收入调节表。")
    else:
        recommendation = ("系统已量化两税收入差异。下一步：①差异>10%须编制两税收入调节表，"
                          "逐项列明增值税应税但所得税不征/免税/以前年度/视同销售等来源；"
                          "②增值税>所得税方向须逐笔核实是否将应税收入在所得税申报时砍掉；"
                          "③结合银行资金流（资金流比对所有收款）交叉验证未申报收入。全部需人工取证与定性。")

    return {
        "available": True,
        "ok": True,
        "title": "增值税收入 vs 企业所得税收入差异比对",
        "company": company_name,
        "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": f"增值税销售额{vat_sales:,.2f}元 vs 企业所得税营业收入{cit_income:,.2f}元，"
                   f"差额{vat_sales - cit_income:,.2f}元。",
        "body": body,
        "metrics": metrics,
        "signals": signals,
        "verdict": verdict,
        "recommendation": recommendation,
        "note": "本比对基于两张申报表抽取的收入口径，属「待证线索」：两税收入确认原则本就存在差异（如免税、"
                "不征税、以前年度、视同销售），差异需结合纳税调整底稿与收入确认政策核实后认定；定性权在风险检查员。",
    }

# -*- coding: utf-8 -*-
"""经过数据契约验证的原子筛查规则。

这里的规则只计算可复核的数据事实，不作违法定性。只有具备明确字段契约、
来源边界并通过回归测试的计算，才属于“可执行原子规则”。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime


VERIFIED_RULE_CATALOG = [
    {
        "id": "VR001",
        "name": "银行收款与销项开票金额月度差异",
        "layer": "通用基础规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["销售与收入确认", "收付款与资金结算", "开票、红冲与用途确认"],
        "required_sources": ["bank_txs", "sal_invs"],
        "status": "verified_executable_screening",
        "limitation": "收款不等于应税收入，开票也不等于申报收入；必须复核借款、资本往来、代收代付、预收款、退款和跨期。",
    },
    {
        "id": "VR002",
        "name": "会计收入与销项开票金额月度差异",
        "layer": "通用基础规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["会计核算与期末结转", "销售与收入确认", "开票、红冲与用途确认"],
        "required_sources": ["vouchers", "sal_invs"],
        "status": "verified_executable_screening",
        "limitation": "税会确认时点、含税口径、价外费用、不开票收入和非增值税收入须分别复核。",
    },
    {
        "id": "VR003",
        "name": "销项发票号码重复记录",
        "layer": "数据质量与发票规则",
        "industries": ["ALL"],
        "taxes": ["增值税"],
        "lifecycle": ["开票、红冲与用途确认"],
        "required_sources": ["sal_invs"],
        "status": "verified_executable_screening",
        "limitation": "优先排除重复上传、多行商品明细和解析拆分，不能仅凭重复记录推断重复开票。",
    },
    {
        "id": "VR004",
        "name": "进项发票号码重复记录",
        "layer": "数据质量与发票规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "开票、红冲与用途确认"],
        "required_sources": ["pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "优先排除重复上传、多行商品明细和解析拆分，抵扣状态仍须以合法取得的数据核验。",
    },
    {
        "id": "VR005",
        "name": "工资名册与社会保险人员范围差异",
        "layer": "人员税费协同规则",
        "industries": ["ALL"],
        "taxes": ["个人所得税", "社会保险费"],
        "lifecycle": ["用工、薪酬与扣缴"],
        "required_sources": ["salaries", "social_security"],
        "status": "verified_executable_screening",
        "limitation": "劳务派遣、退休返聘、兼职、入离职月份、异地参保和非雇员劳务必须单独排除。",
    },
    {
        "id": "VR006",
        "name": "库存期末数量为负",
        "layer": "存货数据质量规则",
        "industries": ["A", "B", "C", "F", "G", "H", "Q"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "生产、加工与服务交付", "存货、物流与资产", "销售与收入确认"],
        "required_sources": ["inventory"],
        "status": "verified_executable_screening",
        "limitation": "负库存可能来自单据时点、跨仓调拨、计量单位转换、在途和退货，首先属于账实及数据质量核验事项。",
    },
    {
        "id": "VR007",
        "name": "库存数量滚动关系不一致",
        "layer": "存货数据质量规则",
        "industries": ["A", "B", "C", "F", "G", "H", "Q"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "生产、加工与服务交付", "存货、物流与资产", "销售与收入确认"],
        "required_sources": ["inventory"],
        "status": "verified_executable_screening",
        "limitation": "仅在期初、入库、出库和期末字段齐全时计算；合理损耗、盘盈盘亏和单位换算须另行核验。",
    },
    {
        "id": "VR008",
        "name": "同一凭证借贷不平",
        "layer": "会计数据质量规则",
        "industries": ["ALL"],
        "taxes": ["企业所得税", "增值税"],
        "lifecycle": ["会计核算与期末结转"],
        "required_sources": ["vouchers"],
        "status": "verified_executable_screening",
        "limitation": "只评价上传凭证数据的完整性；缺行、解析失败和外币折算应先于涉税判断排除。",
    },
    {
        "id": "VR009",
        "name": "银行流水余额滚动关系不一致",
        "layer": "资金数据质量规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税", "个人所得税"],
        "lifecycle": ["收付款与资金结算", "资料接收"],
        "required_sources": ["bank_txs"],
        "status": "verified_executable_screening",
        "limitation": "仅在同一账户、日期和余额字段可识别时计算；银行借贷方向、日内排序、币种和重复导出须先核对。",
    },
    {
        "id": "VR010",
        "name": "销项发票金额税额价税合计关系不一致",
        "layer": "发票数据质量规则",
        "industries": ["ALL"],
        "taxes": ["增值税"],
        "lifecycle": ["开票、红冲与用途确认", "资料接收"],
        "required_sources": ["sal_invs"],
        "status": "verified_executable_screening",
        "limitation": "只校验上传字段的算术关系；差额可能来自四舍五入、价税字段映射、红字行和多行票面拆分。",
    },
    {
        "id": "VR011",
        "name": "进项发票金额税额价税合计关系不一致",
        "layer": "发票数据质量规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "开票、红冲与用途确认", "资料接收"],
        "required_sources": ["pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "只校验上传字段的算术关系；抵扣资格、交易真实性和税前扣除仍须单独核验。",
    },
    {
        "id": "VR012",
        "name": "同一交易对手同时出现在客户与供应商清单",
        "layer": "交易关系交叉规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "销售与收入确认"],
        "required_sources": ["sal_invs", "pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "双向交易在返修、材料互供、平台结算和集团协同中可能正常；必须按合同、货物流、定价和资金净额核验。",
    },
    {
        "id": "VR013",
        "name": "同一资金对手方存在大额双向收付",
        "layer": "资金关系交叉规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税", "个人所得税"],
        "lifecycle": ["收付款与资金结算", "资本投入与融资"],
        "required_sources": ["bank_txs"],
        "status": "verified_executable_screening",
        "limitation": "双向收付可能来自退款、借还款、保证金、代收代付和正常双向贸易；单一资金来源只形成调查线索。",
    },
]


def _number(value, default=0.0):
    try:
        return float(value) if value not in (None, "", "None") else default
    except (TypeError, ValueError):
        return default


def _month(value):
    text = str(value or "").strip().replace("/", "-").replace(".", "-")
    if not text:
        return ""
    digits = "".join(character for character in text if character.isdigit())
    return digits[:6] if len(digits) >= 6 else ""


def _invoice_amount(row, pretax=False):
    if pretax:
        amount = _number(row.get("amount"))
        if amount:
            return amount
        return max(_number(row.get("total")) - _number(row.get("tax")), 0.0)
    total = _number(row.get("total"))
    return total if total else _number(row.get("amount")) + _number(row.get("tax"))


def _finding(spec, detail, metrics, sources, status="clue_pending_investigation", priority="中"):
    return {
        "type": spec["name"],
        "rule_id": spec["id"],
        "category": spec["layer"],
        "level": "信息" if status == "data_quality_limitation" else "中风险",
        "score": 2 if status == "data_quality_limitation" else 5,
        "priority": priority,
        "detail": detail,
        "observed_metrics": metrics,
        "finding_status": status,
        "rule_maturity": spec["status"],
        "conclusion_scope": "screening_and_review_only",
        "required_human_review": True,
        "independent_sources": list(sources),
        "independent_source_count": len(set(sources)),
        "source_lineage_status": "observed_from_uploaded_data",
        "limitations": spec["limitation"],
        "methodology_controls": {
            "applicability_review_required": True,
            "supporting_and_opposing_evidence_required": True,
            "amount_and_legal_characterisation_separate": True,
            "decision_boundary": "该原子规则只形成可复算的数据事实或资料质量事项，不作税务处理、处罚或移送判断。",
        },
    }


def _monthly_amount(rows, value_fn, predicate=None):
    totals = defaultdict(float)
    for row in rows or []:
        if predicate and not predicate(row):
            continue
        month = _month(row.get("date") or row.get("invoice_date"))
        if month:
            totals[month] += value_fn(row)
    return totals


def _two_series_gap(left, right, ratio_threshold, amount_threshold):
    items = []
    for month in sorted(set(left) & set(right)):
        left_value, right_value = left[month], right[month]
        baseline = max(min(abs(left_value), abs(right_value)), 1.0)
        gap = left_value - right_value
        if abs(gap) >= amount_threshold and abs(gap) / baseline >= ratio_threshold:
            items.append({
                "month": month,
                "left": round(left_value, 2),
                "right": round(right_value, 2),
                "gap": round(gap, 2),
                "gap_ratio": round(abs(gap) / baseline, 4),
            })
    return items


def _scan_bank_invoice_gap(data, spec):
    bank = _monthly_amount(
        data.get("bank_txs", []),
        lambda row: _number(row.get("credit")),
        lambda row: _number(row.get("credit")) > 0,
    )
    invoices = _monthly_amount(data.get("sal_invs", []), _invoice_amount)
    gaps = _two_series_gap(bank, invoices, 0.25, 100000)
    if len(gaps) < 2:
        return []
    total_gap = sum(item["gap"] for item in gaps)
    return [_finding(
        spec,
        f"在{len(gaps)}个月中，银行贷方收款与销项发票价税合计的差异同时超过25%和10万元；累计方向性差额{total_gap:,.2f}元。该结果只说明两个数据口径需要逐月对账。",
        {"anomaly_months": gaps[:24], "directional_total_gap": round(total_gap, 2)},
        spec["required_sources"],
    )]


def _scan_voucher_invoice_gap(data, spec):
    def is_revenue(row):
        account = str(row.get("account_name") or row.get("account") or "")
        return "主营业务收入" in account or "其他业务收入" in account

    vouchers = _monthly_amount(
        data.get("vouchers", []),
        lambda row: _number(row.get("credit")),
        lambda row: is_revenue(row) and _number(row.get("credit")) > 0,
    )
    invoices = _monthly_amount(data.get("sal_invs", []), lambda row: _invoice_amount(row, pretax=True))
    gaps = _two_series_gap(vouchers, invoices, 0.15, 100000)
    if len(gaps) < 2:
        return []
    return [_finding(
        spec,
        f"在{len(gaps)}个月中，会计收入贷方发生额与销项发票不含税金额的差异同时超过15%和10万元，需要统一税会确认期间及金额口径。",
        {"anomaly_months": gaps[:24]},
        spec["required_sources"],
    )]


def _invoice_identity(row):
    code = str(row.get("inv_code") or row.get("invoice_code") or "").strip()
    number = str(
        row.get("inv_no") or row.get("invoice_no") or row.get("digital_invoice_no") or ""
    ).strip()
    return (code, number) if number else None


def _scan_duplicate_invoices(data, spec, source):
    groups = defaultdict(list)
    for index, row in enumerate(data.get(source, []) or []):
        identity = _invoice_identity(row)
        if identity:
            groups[identity].append(index + 1)
    duplicates = [
        {"invoice_code": key[0], "invoice_number": key[1], "rows": rows[:20]}
        for key, rows in groups.items() if len(rows) > 1
    ]
    if not duplicates:
        return []
    return [_finding(
        spec,
        f"上传资料中有{len(duplicates)}个发票号码出现多次。应先核对是否为重复上传、多行明细或解析拆分，再决定是否进入交易核验。",
        {"duplicate_invoice_count": len(duplicates), "examples": duplicates[:30]},
        [source],
        status="data_quality_limitation",
        priority="资料质量",
    )]


def _person_name(row):
    return str(row.get("name") or row.get("employee_name") or row.get("姓名") or "").strip()


def _scan_payroll_social(data, spec):
    salary_names = {_person_name(row) for row in data.get("salaries", []) or [] if _person_name(row)}
    social_names = {_person_name(row) for row in data.get("social_security", []) or [] if _person_name(row)}
    if len(salary_names) < 5 or len(social_names) < 5:
        return []
    only_salary = sorted(salary_names - social_names)
    only_social = sorted(social_names - salary_names)
    mismatch = len(only_salary) + len(only_social)
    denominator = max(len(salary_names | social_names), 1)
    if mismatch < 2 or mismatch / denominator < 0.2:
        return []
    return [_finding(
        spec,
        f"工资名册与社会保险人员清单共有{mismatch}人未能双向匹配，占合并人员范围的{mismatch / denominator:.1%}。该差异需要按人员身份和所属月份逐人解释。",
        {
            "salary_only_count": len(only_salary),
            "social_only_count": len(only_social),
            "salary_only_examples": only_salary[:30],
            "social_only_examples": only_social[:30],
        },
        spec["required_sources"],
    )]


def _inventory_value(row, names):
    for name in names:
        if row.get(name) not in (None, ""):
            return _number(row.get(name)), True
    return 0.0, False


def _scan_negative_inventory(data, spec):
    items = []
    for index, row in enumerate(data.get("inventory", []) or []):
        ending, present = _inventory_value(row, ("end_qty", "ending_qty", "close_qty"))
        if present and ending < -0.000001:
            items.append({
                "row": index + 1,
                "code": str(row.get("code") or ""),
                "name": str(row.get("name") or ""),
                "end_qty": ending,
            })
    if not items:
        return []
    return [_finding(
        spec,
        f"进销存资料中有{len(items)}项期末数量为负，应先核对单据时点、跨仓调拨、单位换算和解析完整性。",
        {"negative_items": items[:50], "negative_count": len(items)},
        spec["required_sources"],
        status="data_quality_limitation",
        priority="资料质量",
    )]


def _scan_inventory_rollforward(data, spec):
    mismatches, comparable = [], 0
    for index, row in enumerate(data.get("inventory", []) or []):
        opening, has_open = _inventory_value(row, ("open_qty", "begin_qty", "opening_qty"))
        incoming, has_in = _inventory_value(row, ("in_qty", "incoming_qty", "purchase_qty"))
        outgoing, has_out = _inventory_value(row, ("out_qty", "outgoing_qty", "sales_qty"))
        ending, has_end = _inventory_value(row, ("end_qty", "ending_qty", "close_qty"))
        if not all((has_open, has_in, has_out, has_end)):
            continue
        comparable += 1
        expected = opening + incoming - outgoing
        difference = ending - expected
        tolerance = max(0.01, abs(ending) * 0.01)
        if abs(difference) > tolerance:
            mismatches.append({
                "row": index + 1,
                "code": str(row.get("code") or ""),
                "name": str(row.get("name") or ""),
                "expected_end_qty": round(expected, 6),
                "reported_end_qty": round(ending, 6),
                "difference": round(difference, 6),
            })
    if comparable < 3 or not mismatches:
        return []
    return [_finding(
        spec,
        f"{comparable}项具有完整数量字段的存货中，{len(mismatches)}项不满足“期初＋入库－出库＝期末”的滚动关系。",
        {"comparable_count": comparable, "mismatch_count": len(mismatches), "examples": mismatches[:50]},
        spec["required_sources"],
        status="data_quality_limitation",
        priority="资料质量",
    )]


def _scan_voucher_balance(data, spec):
    groups = defaultdict(lambda: {"debit": 0.0, "credit": 0.0, "rows": []})
    for index, row in enumerate(data.get("vouchers", []) or []):
        number = str(row.get("voucher_no") or "").strip()
        if not number:
            continue
        key = (_month(row.get("date")), number)
        groups[key]["debit"] += _number(row.get("debit"))
        groups[key]["credit"] += _number(row.get("credit"))
        groups[key]["rows"].append(index + 1)
    mismatches = []
    for (month, number), values in groups.items():
        difference = values["debit"] - values["credit"]
        if abs(difference) > 1:
            mismatches.append({
                "month": month,
                "voucher_no": number,
                "debit": round(values["debit"], 2),
                "credit": round(values["credit"], 2),
                "difference": round(difference, 2),
                "rows": values["rows"][:30],
            })
    if not mismatches:
        return []
    return [_finding(
        spec,
        f"按月份和凭证号汇总后，有{len(mismatches)}张凭证借贷差额超过1元；应优先检查上传是否缺行或解析失败。",
        {"unbalanced_count": len(mismatches), "examples": mismatches[:50]},
        spec["required_sources"],
        status="data_quality_limitation",
        priority="资料质量",
    )]


def _scan_bank_balance_rollforward(data, spec):
    accounts = defaultdict(list)
    for index, row in enumerate(data.get("bank_txs", []) or []):
        if row.get("balance") in (None, ""):
            continue
        account = str(row.get("account") or row.get("account_no") or "未区分账户")
        accounts[account].append((str(row.get("date") or ""), index, row))
    mismatches, comparable = [], 0
    for account, rows in accounts.items():
        rows.sort(key=lambda item: (item[0], item[1]))
        for previous, current in zip(rows, rows[1:]):
            previous_balance = _number(previous[2].get("balance"))
            expected = previous_balance + _number(current[2].get("credit")) - _number(current[2].get("debit"))
            actual = _number(current[2].get("balance"))
            comparable += 1
            if abs(expected - actual) > 1:
                mismatches.append({
                    "account": account[-8:],
                    "date": current[0],
                    "expected_balance": round(expected, 2),
                    "reported_balance": round(actual, 2),
                    "difference": round(actual - expected, 2),
                })
    if comparable < 3 or not mismatches:
        return []
    return [_finding(
        spec,
        f"在{comparable}组可比较的相邻流水中，有{len(mismatches)}组余额未按“上笔余额＋收入－支出”滚动。",
        {"comparable_count": comparable, "mismatch_count": len(mismatches), "examples": mismatches[:50]},
        spec["required_sources"],
        status="data_quality_limitation",
        priority="资料质量",
    )]


def _scan_invoice_arithmetic(data, spec, source):
    mismatches, comparable = [], 0
    for index, row in enumerate(data.get(source, []) or []):
        if any(row.get(field) in (None, "") for field in ("amount", "tax", "total")):
            continue
        comparable += 1
        amount, tax, total = _number(row.get("amount")), _number(row.get("tax")), _number(row.get("total"))
        difference = total - amount - tax
        if abs(difference) > 1:
            identity = _invoice_identity(row)
            mismatches.append({
                "row": index + 1,
                "invoice_number": identity[1] if identity else "",
                "amount": amount,
                "tax": tax,
                "total": total,
                "difference": round(difference, 2),
            })
    if comparable < 3 or not mismatches:
        return []
    return [_finding(
        spec,
        f"{comparable}条字段齐全的发票记录中，有{len(mismatches)}条不满足“金额＋税额＝价税合计”（容差1元）。",
        {"comparable_count": comparable, "mismatch_count": len(mismatches), "examples": mismatches[:50]},
        spec["required_sources"],
        status="data_quality_limitation",
        priority="资料质量",
    )]


def _normalise_party(value):
    text = str(value or "").strip().replace("（", "(").replace("）", ")")
    for suffix in ("有限责任公司", "股份有限公司", "有限公司", "公司"):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
            break
    return "".join(character for character in text if character.isalnum()).lower()


def _scan_customer_supplier_overlap(data, spec):
    customers = defaultdict(set)
    suppliers = defaultdict(set)
    for row in data.get("sal_invs", []) or []:
        name = str(row.get("buyer") or "").strip()
        key = _normalise_party(name)
        if key:
            customers[key].add(name)
    for row in data.get("pur_invs", []) or []:
        name = str(row.get("seller") or "").strip()
        key = _normalise_party(name)
        if key:
            suppliers[key].add(name)
    overlaps = sorted(set(customers) & set(suppliers))
    if not overlaps:
        return []
    examples = [sorted(customers[key] | suppliers[key])[0] for key in overlaps[:50]]
    return [_finding(
        spec,
        f"进销项发票中有{len(overlaps)}个标准化交易对手名称同时出现在客户和供应商范围，应按业务合同和实际履约判断双向交易性质。",
        {"overlap_count": len(overlaps), "examples": examples},
        spec["required_sources"],
    )]


def _scan_bidirectional_bank(data, spec):
    parties = defaultdict(lambda: {"credit": 0.0, "debit": 0.0, "count": 0})
    for row in data.get("bank_txs", []) or []:
        party = str(row.get("counterparty") or "").strip()
        if not party:
            continue
        key = _normalise_party(party)
        parties[key]["credit"] += _number(row.get("credit"))
        parties[key]["debit"] += _number(row.get("debit"))
        parties[key]["count"] += 1
        parties[key]["name"] = party
    matches = []
    for values in parties.values():
        smaller, larger = min(values["credit"], values["debit"]), max(values["credit"], values["debit"])
        if smaller >= 100000 and larger and smaller / larger >= 0.2:
            matches.append({
                "counterparty": values["name"],
                "receipts": round(values["credit"], 2),
                "payments": round(values["debit"], 2),
                "transaction_count": values["count"],
            })
    if not matches:
        return []
    matches.sort(key=lambda item: -(item["receipts"] + item["payments"]))
    return [_finding(
        spec,
        f"有{len(matches)}个资金对手方同时存在累计不低于10万元的收款和付款，且较小方向达到较大方向的20%。",
        {"counterparty_count": len(matches), "examples": matches[:50]},
        spec["required_sources"],
        priority="调查优先级",
    )]


_SCANNERS = {
    "VR001": _scan_bank_invoice_gap,
    "VR002": _scan_voucher_invoice_gap,
    "VR003": lambda data, spec: _scan_duplicate_invoices(data, spec, "sal_invs"),
    "VR004": lambda data, spec: _scan_duplicate_invoices(data, spec, "pur_invs"),
    "VR005": _scan_payroll_social,
    "VR006": _scan_negative_inventory,
    "VR007": _scan_inventory_rollforward,
    "VR008": _scan_voucher_balance,
    "VR009": _scan_bank_balance_rollforward,
    "VR010": lambda data, spec: _scan_invoice_arithmetic(data, spec, "sal_invs"),
    "VR011": lambda data, spec: _scan_invoice_arithmetic(data, spec, "pur_invs"),
    "VR012": _scan_customer_supplier_overlap,
    "VR013": _scan_bidirectional_bank,
}


def run_verified_rules(engine_data):
    """运行全部已验证原子规则，返回发现和逐规则执行记录。"""
    findings, executions = [], []
    for spec in VERIFIED_RULE_CATALOG:
        missing = [source for source in spec["required_sources"] if not engine_data.get(source)]
        if missing:
            executions.append({
                "rule_id": spec["id"],
                "status": "not_run_missing_data",
                "missing_sources": missing,
            })
            continue
        try:
            results = _SCANNERS[spec["id"]](engine_data, spec)
            findings.extend(results)
            executions.append({
                "rule_id": spec["id"],
                "status": "triggered" if results else "completed_not_triggered",
                "finding_count": len(results),
            })
        except Exception as error:
            executions.append({
                "rule_id": spec["id"],
                "status": "execution_error",
                "message": str(error)[:240],
            })
    return {
        "version": "1.0.0",
        "executed_at": datetime.now().isoformat(),
        "catalog_count": len(VERIFIED_RULE_CATALOG),
        "findings": findings,
        "executions": executions,
    }

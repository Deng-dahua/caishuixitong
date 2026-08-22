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
    {
        "id": "VR014",
        "name": "生产用能源消耗与制造业生产规模不匹配",
        "layer": "生产经营实质规则",
        "industries": ["A", "B", "C", "D"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["生产、加工与服务交付", "采购与取得"],
        "required_sources": ["pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "生产可能外包、外购或使用房东代收的自备能源；能源发票缺失也可能是资料未上传或归集口径不同，不能据此认定无真实生产。",
    },
    {
        "id": "VR015",
        "name": "进项发票品名缺失",
        "layer": "数据质量与发票规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "资料接收"],
        "required_sources": ["pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "品名缺失可能来自字段映射、汇总导出或票面本身缺项，须回查原始票面后再判断业务性质。",
    },
    {
        "id": "VR016",
        "name": "供应商地域分布与跨省核验",
        "layer": "交易关系交叉规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得"],
        "required_sources": ["pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "跨省采购在原料产地集中、大宗采购或集团协同中可能正常；须按合同、物流和实际交付核验业务真实性。",
    },
    {
        "id": "VR017",
        "name": "购销双方集中度核验",
        "layer": "交易关系交叉规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "销售与收入确认"],
        "required_sources": ["sal_invs", "pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "集中度受行业和商业模式影响；定制生产、代工或单一核心客户模式下，少数客户或供应商占比较高可能正常。",
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


_PROVINCE_CITIES = {
    "广东": ["广州", "深圳", "东莞", "中山", "佛山", "珠海", "惠州", "江门", "汕头", "湛江", "肇庆", "茂名", "梅州", "揭阳", "潮州", "清远", "河源", "阳江", "韶关", "云浮"],
    "山东": ["济南", "青岛", "淄博", "潍坊", "临沂", "烟台", "日照", "德州", "威海", "菏泽", "泰安", "济宁", "聊城", "滨州", "东营", "枣庄"],
    "江苏": ["南京", "苏州", "无锡", "常州", "南通", "徐州", "扬州", "盐城", "泰州", "镇江", "淮安", "连云港", "宿迁", "吴江", "盛泽", "常熟", "张家港", "江阴", "宜兴"],
    "浙江": ["杭州", "宁波", "温州", "绍兴", "嘉兴", "湖州", "金华", "台州", "衢州", "丽水", "舟山"],
    "福建": ["福州", "厦门", "泉州", "漳州", "莆田", "三明", "南平", "龙岩", "宁德"],
    "上海": ["上海"], "北京": ["北京"], "天津": ["天津"], "重庆": ["重庆"],
    "河北": ["石家庄", "唐山", "秦皇岛", "邯郸", "邢台", "保定", "张家口", "承德", "沧州", "廊坊", "衡水"],
    "河南": ["郑州", "开封", "洛阳", "平顶山", "安阳", "新乡", "焦作", "许昌", "漯河", "南阳", "商丘", "信阳", "周口", "驻马店", "濮阳", "三门峡", "鹤壁", "济源", "鄢陵", "长葛", "禹州", "襄城"],
    "湖北": ["武汉", "黄石", "宜昌", "襄阳", "鄂州", "荆门", "孝感", "荆州", "黄冈", "咸宁", "十堰", "随州", "恩施", "宜城", "枣阳", "老河口", "仙桃", "潜江", "天门"],
    "湖南": ["长沙", "株洲", "湘潭", "衡阳", "邵阳", "岳阳", "常德", "益阳", "郴州", "永州", "怀化", "娄底"],
    "四川": ["成都", "自贡", "泸州", "德阳", "绵阳", "广元", "遂宁", "内江", "乐山", "南充", "眉山", "宜宾", "达州"],
    "安徽": ["合肥", "芜湖", "蚌埠", "淮南", "马鞍山", "铜陵", "安庆", "黄山", "滁州", "阜阳", "宿州", "六安", "宣城", "亳州", "池州"],
    "江西": ["南昌", "景德镇", "萍乡", "九江", "新余", "赣州", "吉安", "宜春", "抚州", "上饶"],
    "辽宁": ["沈阳", "大连", "鞍山", "抚顺", "本溪", "丹东", "锦州", "营口", "盘锦", "辽阳", "铁岭"],
    "陕西": ["西安", "铜川", "宝鸡", "咸阳", "渭南", "延安", "汉中", "榆林", "安康", "商洛"],
    "广西": ["南宁", "柳州", "桂林", "梧州", "北海", "钦州", "贵港", "玉林", "百色", "河池"],
    "云南": ["昆明", "曲靖", "玉溪", "保山", "昭通", "丽江", "普洱", "临沧", "大理", "红河"],
    "贵州": ["贵阳", "六盘水", "遵义", "安顺", "毕节", "铜仁", "黔南", "黔东南"],
    "山西": ["太原", "大同", "阳泉", "长治", "晋城", "晋中", "运城", "忻州", "临汾", "吕梁"],
    "黑龙江": ["哈尔滨", "齐齐哈尔", "大庆", "佳木斯", "牡丹江", "绥化"],
    "吉林": ["长春", "吉林", "四平", "通化", "白山", "松原", "延边"],
    "甘肃": ["兰州", "天水", "武威", "张掖", "平凉", "酒泉", "庆阳", "陇南"],
    "内蒙古": ["呼和浩特", "包头", "赤峰", "通辽", "鄂尔多斯", "呼伦贝尔"],
    "新疆": ["乌鲁木齐", "克拉玛依", "吐鲁番", "哈密", "昌吉", "巴音郭楞"],
    "海南": ["海口", "三亚", "儋州", "琼海"],
    "宁夏": ["银川", "石嘴山", "吴忠", "固原", "中卫"],
    "青海": ["西宁", "海东", "海西"],
    "西藏": ["拉萨", "日喀则", "昌都", "林芝"],
}


def _province_of(text):
    text = str(text or "")
    for province, cities in _PROVINCE_CITIES.items():
        if province in text or any(city in text for city in cities):
            return province
    return None


def _invoice_goods_text(row):
    return str(row.get("goods") or row.get("货物或应税劳务名称") or row.get("品名") or "").strip()


def _scan_production_energy(data, spec):
    pur = data.get("pur_invs", []) or []
    if not pur:
        return []
    energy_keywords = ["电费", "水费", "燃气", "天然气", "蒸汽", "热能", "供热", "供电", "供水", "电力"]
    vehicle_keywords = ["汽油", "柴油", "车用", "加油", "充电桩", "充电"]
    raw_material_keywords = ["纱", "布", "棉", "氨纶", "纤维", "坯布", "面料", "针织", "梭织", "染整",
                             "原料", "钢材", "钢板", "铝", "铜", "铁", "塑料", "化工", "粮食", "木材",
                             "石材", "水泥", "矿产", "原油", "煤炭", "纸浆", "浆粕", "化工原料", "颗粒"]
    raw_material_amount = 0.0
    energy_amount = 0.0
    energy_count = 0
    for row in pur:
        goods = _invoice_goods_text(row)
        if not goods:
            continue
        if any(key in goods for key in vehicle_keywords):
            continue
        amount = _number(row.get("amount"))
        if any(key in goods for key in raw_material_keywords):
            raw_material_amount += amount
        if any(key in goods for key in energy_keywords):
            energy_amount += amount
            energy_count += 1
    # 仅当存在明显原材料/生产物资采购时，才按制造业口径核验能源消耗，避免贸易企业误触发
    if raw_material_amount >= 1000000 and energy_amount < raw_material_amount * 0.001:
        return [_finding(
            spec,
            f"进项发票中原材料及生产物资采购{raw_material_amount:,.0f}元，但未识别到生产用能源（电/水/燃气/蒸汽）发票（能源发票{energy_count}张、{energy_amount:,.0f}元），能源消耗与生产规模不匹配，须核验生产场地、设备及实际生产实质。",
            {
                "raw_material_amount": round(raw_material_amount, 2),
                "production_energy_amount": round(energy_amount, 2),
                "production_energy_invoice_count": energy_count,
            },
            spec["required_sources"],
            priority="调查优先级",
        )]
    return []


def _scan_invoice_goods_missing(data, spec):
    pur = data.get("pur_invs", []) or []
    if not pur:
        return []
    missing = [row for row in pur if not _invoice_goods_text(row)]
    missing_amount = sum(_number(row.get("amount")) for row in missing)
    if missing and (len(missing) >= 30 or missing_amount >= 500000):
        return [_finding(
            spec,
            f"进项发票中有{len(missing)}张品名为空，合计金额{missing_amount:,.2f}元，无法识别购进业务性质，须回查原始票面并补充品名后再进入交易核验。",
            {"missing_count": len(missing), "missing_amount": round(missing_amount, 2), "total_count": len(pur)},
            spec["required_sources"],
        )]
    return []


def _scan_supplier_geo(data, spec):
    pur = data.get("pur_invs", []) or []
    if not pur:
        return []
    suppliers = defaultdict(lambda: {"amount": 0.0, "count": 0, "province": None})
    for row in pur:
        name = str(row.get("seller") or row.get("销方名称") or "").strip()
        if not name:
            continue
        entry = suppliers[name]
        entry["amount"] += _number(row.get("amount"))
        entry["count"] += 1
        if entry["province"] is None:
            entry["province"] = _province_of(name)
    if len(suppliers) < 3:
        return []
    provinces = defaultdict(lambda: {"amount": 0.0, "count": 0})
    for name, entry in suppliers.items():
        province = entry["province"] or "未知"
        provinces[province]["amount"] += entry["amount"]
        provinces[province]["count"] += 1
    cross_province = [p for p in provinces if p != "未知"]
    if len(cross_province) < 2:
        return []
    total_amount = sum(entry["amount"] for entry in suppliers.values())
    top_provinces = sorted(provinces.items(), key=lambda item: -item[1]["amount"])
    detail_parts = []
    for province, agg in top_provinces[:5]:
        ratio = (agg["amount"] / total_amount * 100) if total_amount else 0
        detail_parts.append(f"{province}{agg['count']}家{agg['amount']:,.0f}元({ratio:.0f}%)")
    return [_finding(
        spec,
        f"进项发票供应商分布在{len(cross_province)}个省份，前几大采购来源地：" + "、".join(detail_parts) + "。跨省分散采购须核验各供应商资质、合同、物流和实际交付，识别是否存在无实质交易的票据流转。",
        {
            "supplier_count": len(suppliers),
            "province_count": len(cross_province),
            "province_breakdown": {p: {"count": v["count"], "amount": round(v["amount"], 2)} for p, v in top_provinces[:8]},
        },
        spec["required_sources"],
        priority="调查优先级",
    )]


def _scan_concentration(data, spec):
    sal = data.get("sal_invs", []) or []
    pur = data.get("pur_invs", []) or []
    suppliers = defaultdict(float)
    customers = defaultdict(float)
    for row in pur:
        name = str(row.get("seller") or row.get("销方名称") or "").strip()
        if name:
            suppliers[name] += _number(row.get("amount"))
    for row in sal:
        name = str(row.get("buyer") or row.get("购方名称") or "").strip()
        if name:
            customers[name] += _number(row.get("amount"))
    supplier_total = sum(suppliers.values())
    customer_total = sum(customers.values())
    top3_supplier = sum(sorted(suppliers.values(), reverse=True)[:3])
    top3_customer = sum(sorted(customers.values(), reverse=True)[:3])
    supplier_ratio = (top3_supplier / supplier_total) if supplier_total else 0.0
    customer_ratio = (top3_customer / customer_total) if customer_total else 0.0
    signals = []
    if supplier_total > 0 and len(suppliers) >= 3 and supplier_ratio >= 0.8:
        top_supplier = max(suppliers, key=suppliers.get)
        signals.append(f"前3大供应商占采购额{supplier_ratio*100:.1f}%（最大供应商{top_supplier}）")
    if customer_total > 0 and len(customers) >= 3 and customer_ratio >= 0.8:
        top_customer = max(customers, key=customers.get)
        signals.append(f"前3大客户占销售额{customer_ratio*100:.1f}%（最大客户{top_customer}）")
    if not signals:
        return []
    return [_finding(
        spec,
        "；".join(signals) + "。购销集中度偏高，须核验交易真实性、定价独立性、是否存在关联关系或对单一渠道的异常依赖。",
        {
            "supplier_count": len(suppliers),
            "customer_count": len(customers),
            "supplier_top3_ratio": round(supplier_ratio, 4),
            "customer_top3_ratio": round(customer_ratio, 4),
        },
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
    "VR014": _scan_production_energy,
    "VR015": _scan_invoice_goods_missing,
    "VR016": _scan_supplier_geo,
    "VR017": _scan_concentration,
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

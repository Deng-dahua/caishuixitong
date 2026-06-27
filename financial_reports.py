"""
财务报表管理模块 - 从 main.py 自动拆分
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Form
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
import os, io, json, openpyxl, re as _re_module

from database import get_db

router = APIRouter(tags=["财务报表"])

def _prev_period(period: str) -> str:
    """计算上一个会计期间。'2025-03' → '2025-02'，'2025-01' → '2024-12'"""
    y, m = map(int, period.split("-"))
    m -= 1
    if m == 0:
        m = 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def _compute_period_balances(company_id: int, period_from, period_to, db) -> dict:
    """
    公用函数：计算指定期间范围内的科目借贷方发生额。
    单数据源：所有报表均通过此函数从序时账取数，避免重复查询。
    period_from: str 如 '2025-01' 或 None（无下限）
    period_to:   str 如 '2025-12' 或 None（无上限）
    返回: {account_code: {"debit": float, "credit": float}}
    """
    q = db.query(JournalEntry).filter(JournalEntry.company_id == company_id)
    if period_from is not None:
        q = q.filter(JournalEntry.period >= period_from)
    if period_to is not None:
        q = q.filter(JournalEntry.period <= period_to)
    result = {}
    for e in q.all():
        c = result.setdefault(e.account_code, {"debit": 0.0, "credit": 0.0})
        c["debit"] += float(e.debit_amount or 0)
        c["credit"] += float(e.credit_amount or 0)
    return result


def _build_trial_balance_tree(company_id, period_raw, cum_raw, db):
    """
    公用函数：基于 period_raw / cum_raw，构建科目余额表的树形汇总结果列表。
    与科目余额表前端返回格式一致。
    """
    accounts = db.query(Account).filter(
        Account.company_id == company_id,
        Account.is_active == True
    ).order_by(Account.code).all()
    acc_map = {a.code: a for a in accounts}

    children_map = {}
    for a in accounts:
        if a.parent_code:
            children_map.setdefault(a.parent_code, []).append(a.code)

    def aggregate(code, data_map):
        total = dict(data_map.get(code, {"debit": 0.0, "credit": 0.0}))
        for child in children_map.get(code, []):
            child_data = aggregate(child, data_map)
            total["debit"] += child_data["debit"]
            total["credit"] += child_data["credit"]
        return total

    period_agg = {a.code: aggregate(a.code, period_raw) for a in accounts}
    cum_agg = {a.code: aggregate(a.code, cum_raw) for a in accounts}

    display_codes = set()
    for a in accounts:
        pt = period_agg[a.code]
        ct = cum_agg[a.code]
        if pt["debit"] != 0 or pt["credit"] != 0 or ct["debit"] != 0 or ct["credit"] != 0:
            current = a.code
            while current:
                display_codes.add(current)
                parent = acc_map[current].parent_code if current in acc_map else None
                current = parent if parent else None

    result = []
    for acc in accounts:
        if acc.code not in display_codes:
            continue
        pt = period_agg[acc.code]
        ct = cum_agg[acc.code]
        pdr = round(pt["debit"], 2)
        pcr = round(pt["credit"], 2)
        cdr = round(ct["debit"], 2)
        ccr = round(ct["credit"], 2)
        direction = acc.balance_direction
        if direction == "借":
            net = round(cdr - ccr, 2)
            end_debit = net if net >= 0 else 0
            end_credit = round(-net, 2) if net < 0 else 0
        else:
            net = round(ccr - cdr, 2)
            end_credit = round(net, 2) if net >= 0 else 0
            end_debit = round(-net, 2) if net < 0 else 0
        result.append({
            "account_code": acc.code,
            "account_name": acc.name,
            "category": acc.category,
            "balance_direction": direction,
            "level": acc.level,
            "parent_code": acc.parent_code,
            "has_children": acc.code in children_map and len(children_map[acc.code]) > 0,
            "begin_debit": 0,
            "begin_credit": 0,
            "period_debit": pdr,
            "period_credit": pcr,
            "cumulative_debit": cdr,
            "cumulative_credit": ccr,
            "end_debit": end_debit,
            "end_credit": end_credit,
        })
    return result


# ==================== 科目余额表 ====================
@router.get("/api/trial-balance")
def trial_balance(
    company_id: int = Query(...),
    period: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """科目余额表：调用统一计算函数"""
    # 本期发生额
    period_raw = _compute_period_balances(company_id, period, period, db)
    # 累计发生额（年初 → 当前期间）
    cum_raw = {}
    if period:
        year = period.split("-")[0]
        cum_raw = _compute_period_balances(company_id, f"{year}-01", period, db)
    else:
        cum_raw = dict(period_raw)

    return _build_trial_balance_tree(company_id, period_raw, cum_raw, db)


# ==================== 总账 ====================
@router.get("/api/ledger/general")
def general_ledger(
    company_id: int = Query(...),
    period_from: str = Query(...),
    period_to: str = Query(...),
    db: Session = Depends(get_db)
):
    """总账：调用统一余额计算函数，树形汇总显示全级次"""
    prev = _prev_period(period_from)
    period_raw  = _compute_period_balances(company_id, period_from, period_to, db)
    cum_raw    = _compute_period_balances(company_id, None, period_to, db)
    open_raw   = _compute_period_balances(company_id, None, prev, db)

    accounts = db.query(Account).filter(
        Account.company_id == company_id,
        Account.is_active == True
    ).order_by(Account.code).all()
    acc_map = {a.code: a for a in accounts}

    # 构建层级名称链（纯名称，不带科目编码）
    def _get_name_chain(acct):
        parts = [acct.name]
        cur = acct
        while cur.parent_code and cur.parent_code in acc_map:
            cur = acc_map[cur.parent_code]
            parts.append(cur.name)
        parts.reverse()
        return " / ".join(parts)
    name_map = {a.code: _get_name_chain(a) for a in accounts}

    # 树形汇总：父级 = 自身 + 所有子级合计
    children_map = {}
    for a in accounts:
        if a.parent_code:
            children_map.setdefault(a.parent_code, []).append(a.code)

    def aggregate(code, data_map):
        total = dict(data_map.get(code, {"debit": 0.0, "credit": 0.0}))
        for child in children_map.get(code, []):
            child_data = aggregate(child, data_map)
            total["debit"] += child_data["debit"]
            total["credit"] += child_data["credit"]
        return total

    period_agg = {a.code: aggregate(a.code, period_raw) for a in accounts}
    cum_agg = {a.code: aggregate(a.code, cum_raw) for a in accounts}

    # 全级次过滤：聚合后有数据的科目 + 其所有父级链
    display_codes = set()
    for a in accounts:
        pt = period_agg[a.code]
        ct = cum_agg[a.code]
        if pt["debit"] != 0 or pt["credit"] != 0 or ct["debit"] != 0 or ct["credit"] != 0:
            current = a.code
            while current:
                display_codes.add(current)
                parent = acc_map[current].parent_code if current in acc_map else None
                current = parent if parent else None

    result = []
    for acc in accounts:
        if acc.code not in display_codes:
            continue
        p = period_agg[acc.code]
        c = cum_agg[acc.code]
        o = open_raw.get(acc.code, {"debit": 0.0, "credit": 0.0})
        direction = acc.balance_direction or "借"
        # 期初余额：从前期累计发生额推算
        if direction == "借":
            ob = round(o["debit"] - o["credit"], 2)
        else:
            ob = round(o["credit"] - o["debit"], 2)
        # 期末余额
        if direction == "借":
            balance = round(c["debit"] - c["credit"], 2)
        else:
            balance = round(c["credit"] - c["debit"], 2)
        # 期初方向：余额>0与科目方向一致，<0相反
        if ob >= 0:
            opening_direction = direction
        else:
            opening_direction = "贷" if direction == "借" else "借"
        result.append({
            "account_code": acc.code,
            "account_name": name_map.get(acc.code, acc.name),
            "level": acc.level,
            "opening_balance": round(ob, 2),
            "opening_direction": opening_direction,
            "total_debit": round(p["debit"], 2),
            "total_credit": round(p["credit"], 2),
            "end_balance": balance,
            "end_direction": direction,
        })
    return result


# ==================== 明细账 ====================
@router.get("/api/ledger/detail")
def detail_ledger(
    company_id: int = Query(...),
    account_code: str = Query(...),
    period_from: str = Query(...),
    period_to: str = Query(...),
    db: Session = Depends(get_db)
):
    """明细账：调用统一余额计算函数获取期初余额，交易明细仍从序时账取"""
    account = db.query(Account).filter(
        Account.company_id == company_id,
        Account.code == account_code
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="科目不存在")

    # 期初余额 = 截止上期期末的累计净额
    prev = _prev_period(period_from)
    opening_raw = _compute_period_balances(company_id, None, prev, db)
    ob = opening_raw.get(account_code, {"debit": 0.0, "credit": 0.0})
    if account.balance_direction == "借":
        opening_balance = round(ob["debit"] - ob["credit"], 2)
    else:
        opening_balance = round(ob["credit"] - ob["debit"], 2)

    # 本期交易明细（仍需逐笔，无法从余额表获取）
    entries = db.query(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.account_code == account_code,
        JournalEntry.period >= period_from,
        JournalEntry.period <= period_to
    ).order_by(JournalEntry.entry_date, JournalEntry.voucher_no, JournalEntry.id).all()

    rows = []
    balance = float(opening_balance)
    for e in entries:
        dr = float(e.debit_amount or 0)
        cr = float(e.credit_amount or 0)
        if account.balance_direction == "借":
            balance += dr - cr
        else:
            balance += cr - dr
        rows.append({
            "voucher_date": str(e.entry_date) if e.entry_date else "",
            "voucher_no": (e.voucher_word or '记') + '-' + str(e.voucher_no).zfill(4) if e.voucher_no else "",
            "summary": e.summary or "",
            "debit_amount": dr,
            "credit_amount": cr,
            "balance": round(balance, 2),
        })

    return {
        "account_code": account.code,
        "account_name": account.name,
        "balance_direction": account.balance_direction,
        "opening_balance": round(opening_balance, 2),
        "rows": rows,
    }


# ==================== 往来明细账（人员/客户/供应商） ====================

# 往来科目映射（每类仅用一个主科目）
_CONTACT_ACCOUNTS = {
    "employee": ["1221"],   # 其他应收款（人员）
    "customer": ["1122"],   # 应收账款（客户）
    "supplier": ["2202"],   # 应付账款（供应商）
}


def _sub_ledger_by_contact(company_id: int, account_codes: list, contact_name: str,
                           period_from: str, period_to: str, db: Session):
    """共用往来明细账计算函数

    返回：{ contact_name, opening_balance, rows: [{date, voucher_no, summary, account_code, account_name, debit, credit, balance}] }
    """
    entries_all = db.query(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.account_code.in_(account_codes),
        JournalEntry.contact_project == contact_name,
        JournalEntry.period <= period_to
    ).order_by(JournalEntry.entry_date, JournalEntry.voucher_no, JournalEntry.id).all()

    # 期初余额：period_from 之前的累计净额
    opening_balance = 0.0
    for e in entries_all:
        if e.period < period_from:
            opening_balance += float(e.debit_amount or 0) - float(e.credit_amount or 0)

    # 本期明细
    rows = []
    balance = opening_balance
    for e in entries_all:
        if e.period < period_from:
            continue
        dr = float(e.debit_amount or 0)
        cr = float(e.credit_amount or 0)
        balance += dr - cr
        rows.append({
            "voucher_date": str(e.entry_date) if e.entry_date else "",
            "voucher_no": (e.voucher_word or '记') + '-' + str(e.voucher_no).zfill(4) if e.voucher_no else "",
            "summary": e.summary or "",
            "account_code": e.account_code,
            "account_name": e.account_name or "",
            "debit_amount": dr,
            "credit_amount": cr,
            "balance": round(balance, 2),
        })

    return {
        "contact_name": contact_name,
        "opening_balance": round(opening_balance, 2),
        "rows": rows,
    }


def _contact_list(company_id: int, account_codes: list, db: Session):
    """提取往来项目列表（从序时账 contact_project 中汇总）"""
    results = db.query(
        JournalEntry.contact_project,
        func.sum(JournalEntry.debit_amount).label("total_debit"),
        func.sum(JournalEntry.credit_amount).label("total_credit"),
    ).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.account_code.in_(account_codes),
        JournalEntry.contact_project.isnot(None),
        JournalEntry.contact_project != "",
    ).group_by(JournalEntry.contact_project).all()

    contacts = []
    for r in results:
        name = r[0]
        td = round(r[1] or 0, 2)
        tc = round(r[2] or 0, 2)
        contacts.append({
            "name": name,
            "total_debit": td,
            "total_credit": tc,
            "net": round(td - tc, 2),
        })
    contacts.sort(key=lambda c: c["name"])
    return contacts


@router.get("/api/ledger/employee-contacts")
def employee_contacts(company_id: int = Query(...), db: Session = Depends(get_db)):
    return _contact_list(company_id, _CONTACT_ACCOUNTS["employee"], db)


@router.get("/api/ledger/customer-contacts")
def customer_contacts(company_id: int = Query(...), db: Session = Depends(get_db)):
    return _contact_list(company_id, _CONTACT_ACCOUNTS["customer"], db)


@router.get("/api/ledger/supplier-contacts")
def supplier_contacts(company_id: int = Query(...), db: Session = Depends(get_db)):
    return _contact_list(company_id, _CONTACT_ACCOUNTS["supplier"], db)


@router.get("/api/ledger/employee-detail")
def employee_detail(
    company_id: int = Query(...),
    contact_name: str = Query(...),
    period_from: str = Query(...),
    period_to: str = Query(...),
    db: Session = Depends(get_db)
):
    return _sub_ledger_by_contact(company_id, _CONTACT_ACCOUNTS["employee"], contact_name, period_from, period_to, db)


@router.get("/api/ledger/customer-detail")
def customer_detail(
    company_id: int = Query(...),
    contact_name: str = Query(...),
    period_from: str = Query(...),
    period_to: str = Query(...),
    db: Session = Depends(get_db)
):
    return _sub_ledger_by_contact(company_id, _CONTACT_ACCOUNTS["customer"], contact_name, period_from, period_to, db)


@router.get("/api/ledger/supplier-detail")
def supplier_detail(
    company_id: int = Query(...),
    contact_name: str = Query(...),
    period_from: str = Query(...),
    period_to: str = Query(...),
    db: Session = Depends(get_db)
):
    return _sub_ledger_by_contact(company_id, _CONTACT_ACCOUNTS["supplier"], contact_name, period_from, period_to, db)


# ==================== 利润表（企业会计准则一般企业—会企02号） ====================
def _pl_net(balances, code_prefix, is_credit_nature=True):
    """汇总指定前缀科目的净额：收入/收益类=贷-借，费用/损失类=借-贷"""
    total_dr = 0.0; total_cr = 0.0
    for code, bal in balances.items():
        if code.startswith(code_prefix):
            total_dr += bal["debit"]; total_cr += bal["credit"]
    return round(total_cr - total_dr, 2) if is_credit_nature else round(total_dr - total_cr, 2)

def _pl_row(label, current=0.0, prior=0.0, bold=False, highlight=False, indent=0):
    return {"label": label, "current": current, "prior": prior, "bold": bold, "highlight": highlight, "indent": indent}

def _build_pl(company_id, from_period, to_period, db):
    """构建单期利润表数据"""
    b = _compute_period_balances(company_id, from_period, to_period, db)
    # 一、营业收入
    rev = _pl_net(b, "6001") + _pl_net(b, "6051")
    cost = _pl_net(b, "6401", False) + _pl_net(b, "6402", False)
    tax_sur = _pl_net(b, "6403", False)
    sell_exp = _pl_net(b, "6601", False)
    admin_exp = _pl_net(b, "6602", False)
    rd_exp = _pl_net(b, "6604", False)
    fin_exp = _pl_net(b, "6603", False)
    inv_inc = _pl_net(b, "6111")
    credit_loss = _pl_net(b, "6701", False)
    asset_impair = _pl_net(b, "6702", False)
    asset_disp = _pl_net(b, "6712")  # 资产处置收益（贷余）
    other_inc = _pl_net(b, "6301")
    other_exp = _pl_net(b, "6711", False)
    income_tax = _pl_net(b, "6801", False)
    # 中间计算
    gross_p = round(rev - cost - tax_sur, 2)
    # 营业利润 = 毛利 - 期间费用 + 投资收益 + 资产处置收益 - 减值损失
    # 注：营业外收入(6301)/营业外支出(6711)不属于营业利润，在利润总额中加减
    op_p = round(gross_p - sell_exp - admin_exp - rd_exp - fin_exp + inv_inc + asset_disp - credit_loss - asset_impair, 2)
    total_p = round(op_p + other_inc - other_exp, 2)
    net_p = round(total_p - income_tax, 2)
    items = [
        _pl_row("一、营业收入", rev, bold=True),
        _pl_row("  减：营业成本", cost, indent=1),
        _pl_row("  减：税金及附加", tax_sur, indent=1),
        _pl_row("  减：销售费用", sell_exp, indent=1),
        _pl_row("  减：管理费用", admin_exp, indent=1),
        _pl_row("  减：研发费用", rd_exp, indent=1),
        _pl_row("  减：财务费用", fin_exp, indent=1),
        _pl_row("  加：其他收益", 0.0, indent=1),
        _pl_row("  加：投资收益", inv_inc, indent=1),
        _pl_row("  加：资产处置收益", asset_disp, indent=1),
        _pl_row("  减：信用减值损失", credit_loss, indent=1),
        _pl_row("  减：资产减值损失", asset_impair, indent=1),
        _pl_row("二、营业利润", op_p, bold=True, highlight=True),
        _pl_row("  加：营业外收入", other_inc, indent=1),
        _pl_row("  减：营业外支出", other_exp, indent=1),
        _pl_row("三、利润总额", total_p, bold=True, highlight=True),
        _pl_row("  减：所得税费用", income_tax, indent=1),
        _pl_row("四、净利润", net_p, bold=True, highlight=True),
        _pl_row("五、其他综合收益的税后净额", 0.0, bold=True),
        _pl_row("六、综合收益总额", net_p, bold=True, highlight=True),
        _pl_row("七、每股收益", 0.0, bold=True),
        _pl_row("  （一）基本每股收益", 0.0, indent=1),
        _pl_row("  （二）稀释每股收益", 0.0, indent=1),
    ]
    return items

def _prior_same_period(period_from: str, period_to: str):
    """计算上年同期：如 2026-01→2026-03 → 2025-01→2025-03"""
    yf, mf = map(int, period_from.split("-"))
    yt, mt = map(int, period_to.split("-"))
    return f"{yf-1}-{mf:02d}", f"{yt-1}-{mt:02d}"

@router.get("/api/reports/profit-loss")
def profit_loss_report(
    company_id: int = Query(...),
    period_from: str = Query(...),
    period_to: str = Query(...),
    db: Session = Depends(get_db)
):
    """利润表（会企02号）：本期金额 + 上期金额"""
    current_items = _build_pl(company_id, period_from, period_to, db)
    prior_from, prior_to = _prior_same_period(period_from, period_to)
    prior_items = _build_pl(company_id, prior_from, prior_to, db)
    prior_map = {it["label"]: it["current"] for it in prior_items}
    for it in current_items:
        it["prior"] = prior_map.get(it["label"], 0.0)
    return {"items": current_items, "period_from": period_from, "period_to": period_to}


# ==================== 资产负债表（企业会计准则一般企业—会企01号） ====================
def _bs_year_begin(period: str):
    """年初期间：2026-03 → 2025-12"""
    y = int(period.split("-")[0])
    return f"{y-1}-12"

def _opening_balance_dict(company_id: int, db: Session):
    """将会计科目的期初金额转为 _bs_net 可用的 balances 字典格式"""
    accounts = db.query(Account).filter(
        Account.company_id == company_id,
        Account.is_active == True
    ).all()
    result = {}
    for a in accounts:
        ob = a.opening_balance or 0
        if a.balance_direction == "借":
            if ob >= 0:
                result[a.code] = {"debit": ob, "credit": 0}
            else:
                result[a.code] = {"debit": 0, "credit": abs(ob)}
        else:
            if ob >= 0:
                result[a.code] = {"debit": 0, "credit": ob}
            else:
                result[a.code] = {"debit": abs(ob), "credit": 0}
    return result

def _bs_net(balances, code_prefix, is_debit_nature=True):
    """资产类=借-贷，负债/权益类=贷-借"""
    total_dr = 0.0; total_cr = 0.0
    for code, bal in balances.items():
        if code.startswith(code_prefix):
            total_dr += bal["debit"]; total_cr += bal["credit"]
    return round(total_dr - total_cr, 2) if is_debit_nature else round(total_cr - total_dr, 2)

def _bs_row(label, end=0.0, begin=0.0, bold=False, highlight=False, indent=0):
    return {"label": label, "end": end, "begin": begin, "bold": bold, "highlight": highlight, "indent": indent}

def _build_bs_side(balances, side):
    """构建资产负债表一侧（资产 或 负债+权益）"""
    r = _bs_row
    b = balances
    if side == "assets":
        # 流动资产
        cash = _bs_net(b, "1001") + _bs_net(b, "1002") + _bs_net(b, "1003")
        fin_asset = _bs_net(b, "1101")
        notes_recv = _bs_net(b, "1121")
        ar = _bs_net(b, "1122")
        ar_fin = _bs_net(b, "1124")
        prepay = _bs_net(b, "1123")
        other_recv = _bs_net(b, "1221")
        inventory = _bs_net(b, "1403") + _bs_net(b, "1405") + _bs_net(b, "1406") + _bs_net(b, "1408") + _bs_net(b, "1411")
        contract_asset = _bs_net(b, "1401")
        held_for_sale_a = _bs_net(b, "1501")
        noncurr_due_1y = _bs_net(b, "1502")
        other_current_a = _bs_net(b, "1503")
        total_current = round(cash + fin_asset + notes_recv + ar + ar_fin + prepay + other_recv + inventory + contract_asset + held_for_sale_a + noncurr_due_1y + other_current_a, 2)
        # 非流动资产
        debt_inv = _bs_net(b, "1504")
        other_debt_inv = _bs_net(b, "1505")
        lt_recv = _bs_net(b, "1511")
        lt_equity = _bs_net(b, "1512")
        other_equity = _bs_net(b, "1513")
        other_nc_fin = _bs_net(b, "1514")
        invest_prop = _bs_net(b, "1521")
        fixed_asset = _bs_net(b, "1601")
        accum_depr = _bs_net(b, "1602", False)
        cip = _bs_net(b, "1604")
        bio_asset = _bs_net(b, "1621")
        oil_gas = _bs_net(b, "1631")
        rou_asset = _bs_net(b, "1641")
        intangible = _bs_net(b, "1701")
        dev_exp = _bs_net(b, "1702")
        goodwill = _bs_net(b, "1711")
        lt_deferred = _bs_net(b, "1801")
        def_tax_asset = _bs_net(b, "1811")
        other_nc_a = _bs_net(b, "1901")
        total_nc = round(debt_inv + other_debt_inv + lt_recv + lt_equity + other_equity + other_nc_fin + invest_prop + (fixed_asset - accum_depr) + cip + bio_asset + oil_gas + rou_asset + intangible + dev_exp + goodwill + lt_deferred + def_tax_asset + other_nc_a, 2)
        total_assets = round(total_current + total_nc, 2)
        return [
            r("流动资产：", bold=True),
            r("  货币资金", cash, indent=1), r("  交易性金融资产", fin_asset, indent=1),
            r("  应收票据", notes_recv, indent=1), r("  应收账款", ar, indent=1),
            r("  应收款项融资", ar_fin, indent=1), r("  预付款项", prepay, indent=1),
            r("  其他应收款", other_recv, indent=1), r("  存货", inventory, indent=1),
            r("  合同资产", contract_asset, indent=1), r("  持有待售资产", held_for_sale_a, indent=1),
            r("  一年内到期的非流动资产", noncurr_due_1y, indent=1), r("  其他流动资产", other_current_a, indent=1),
            r("流动资产合计", total_current, bold=True, highlight=True),
            r("非流动资产：", bold=True),
            r("  债权投资", debt_inv, indent=1), r("  其他债权投资", other_debt_inv, indent=1),
            r("  长期应收款", lt_recv, indent=1), r("  长期股权投资", lt_equity, indent=1),
            r("  其他权益工具投资", other_equity, indent=1), r("  其他非流动金融资产", other_nc_fin, indent=1),
            r("  投资性房地产", invest_prop, indent=1),
            r("  固定资产", round(fixed_asset - accum_depr, 2) if fixed_asset else 0.0, indent=1),
            r("  在建工程", cip, indent=1), r("  生产性生物资产", bio_asset, indent=1),
            r("  使用权资产", rou_asset, indent=1), r("  无形资产", intangible, indent=1),
            r("  开发支出", dev_exp, indent=1), r("  商誉", goodwill, indent=1),
            r("  长期待摊费用", lt_deferred, indent=1), r("  递延所得税资产", def_tax_asset, indent=1),
            r("  其他非流动资产", other_nc_a, indent=1),
            r("", 0), r("", 0),
            r("非流动资产合计", total_nc, bold=True, highlight=True),
            r("资产总计", total_assets, bold=True, highlight=True),
        ]
    else:
        # 流动负债
        st_loan = _bs_net(b, "2001", False)
        fin_liab = _bs_net(b, "2101", False)
        notes_pay = _bs_net(b, "2201", False)
        ap = _bs_net(b, "2202", False)
        advance_rcv = _bs_net(b, "2203", False)
        contract_liab = _bs_net(b, "2204", False)
        payroll = _bs_net(b, "2211", False)
        taxes = _bs_net(b, "2210", False)
        other_pay = _bs_net(b, "2241", False)
        held_for_sale_l = _bs_net(b, "2242", False)
        nc_due_1y_l = _bs_net(b, "2243", False)
        other_current_l = _bs_net(b, "2244", False)
        total_current_l = round(st_loan + fin_liab + notes_pay + ap + advance_rcv + contract_liab + payroll + taxes + other_pay + held_for_sale_l + nc_due_1y_l + other_current_l, 2)
        # 非流动负债
        lt_loan = _bs_net(b, "2501", False)
        bonds_pay = _bs_net(b, "2502", False)
        lease_liab = _bs_net(b, "2601", False)
        lt_pay = _bs_net(b, "2701", False)
        estimated_liab = _bs_net(b, "2801", False)
        deferred_inc = _bs_net(b, "2901", False)
        def_tax_liab = _bs_net(b, "2902", False)
        other_nc_l = _bs_net(b, "2903", False)
        total_nc_l = round(lt_loan + bonds_pay + lease_liab + lt_pay + estimated_liab + deferred_inc + def_tax_liab + other_nc_l, 2)
        total_liab = round(total_current_l + total_nc_l, 2)
        # 所有者权益
        paid_in = _bs_net(b, "4001", False)
        other_equity_instr = _bs_net(b, "4002", False)
        capital_surplus = _bs_net(b, "4003", False)
        treasury_stock = _bs_net(b, "4004")
        oci = _bs_net(b, "4005", False)
        special_reserve = _bs_net(b, "4101", False)
        surplus = _bs_net(b, "4103", False)
        retained = round(_bs_net(b, "4104", False) + _bs_net(b, "4103", False), 2)
        total_equity = round(paid_in + other_equity_instr + capital_surplus - treasury_stock + oci + special_reserve + surplus + retained, 2)
        total_right = round(total_liab + total_equity, 2)
        return [
            r("流动负债：", bold=True),
            r("  短期借款", st_loan, indent=1), r("  交易性金融负债", fin_liab, indent=1),
            r("  应付票据", notes_pay, indent=1), r("  应付账款", ap, indent=1),
            r("  预收款项", advance_rcv, indent=1), r("  合同负债", contract_liab, indent=1),
            r("  应付职工薪酬", payroll, indent=1), r("  应交税费", taxes, indent=1),
            r("  其他应付款", other_pay, indent=1), r("  持有待售负债", held_for_sale_l, indent=1),
            r("  一年内到期的非流动负债", nc_due_1y_l, indent=1), r("  其他流动负债", other_current_l, indent=1),
            r("流动负债合计", total_current_l, bold=True, highlight=True),
            r("非流动负债：", bold=True),
            r("  长期借款", lt_loan, indent=1), r("  应付债券", bonds_pay, indent=1),
            r("  租赁负债", lease_liab, indent=1), r("  长期应付款", lt_pay, indent=1),
            r("  预计负债", estimated_liab, indent=1), r("  递延收益", deferred_inc, indent=1),
            r("  递延所得税负债", def_tax_liab, indent=1), r("  其他非流动负债", other_nc_l, indent=1),
            r("非流动负债合计", total_nc_l, bold=True, highlight=True),
            r("负债合计", total_liab, bold=True, highlight=True),
            r("所有者权益（或股东权益）：", bold=True),
            r("  实收资本（或股本）", paid_in, indent=1), r("  其他权益工具", other_equity_instr, indent=1),
            r("  资本公积", capital_surplus, indent=1), r("  减：库存股", treasury_stock, indent=1),
            r("  其他综合收益", oci, indent=1), r("  专项储备", special_reserve, indent=1),
            r("  盈余公积", surplus, indent=1), r("  未分配利润", retained, indent=1),
            r("所有者权益合计", total_equity, bold=True, highlight=True),
            r("负债和所有者权益总计", total_right, bold=True, highlight=True),
        ]

@router.get("/api/reports/balance-sheet")
def balance_sheet_report(
    company_id: int = Query(...),
    period: str = Query(...),
    db: Session = Depends(get_db)
):
    """资产负债表（会企01号）：期末余额 + 年初余额"""
    end_balances = _compute_period_balances(company_id, None, period, db)
    # 年初余额根据会计科目的期初金额确定
    begin_balances = _opening_balance_dict(company_id, db)
    assets = _build_bs_side(end_balances, "assets")
    liab_eq = _build_bs_side(end_balances, "liab_eq")
    # 年初余额单独计算
    assets_begin = _build_bs_side(begin_balances, "assets")
    liab_eq_begin = _build_bs_side(begin_balances, "liab_eq")
    begin_map_a = {r["label"]: r["end"] for r in assets_begin}
    begin_map_le = {r["label"]: r["end"] for r in liab_eq_begin}
    for r in assets:
        r["begin"] = begin_map_a.get(r["label"], 0.0)
    for r in liab_eq:
        r["begin"] = begin_map_le.get(r["label"], 0.0)
    return {"assets": assets, "liabilities_equity": liab_eq, "period": period}


# ==================== 现金流量表（企业会计准则一般企业—会企03号） ====================
def _prior_period_year(period: str):
    """上年同期：2026 → 2025"""
    y = int(period.split("-")[0])
    return str(y - 1)

def _cf_net_cash_by_accounts(company_id, period_from, period_to, cash_codes, db, inflow=True):
    """计算涉及现金科目的对方科目发生额（直接法）— 使用SQL聚合"""
    from sqlalchemy import func
    entries = db.query(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.period >= period_from,
        JournalEntry.period <= period_to,
        JournalEntry.voucher_no.in_(
            db.query(JournalEntry.voucher_no).filter(
                JournalEntry.company_id == company_id,
                JournalEntry.period >= period_from,
                JournalEntry.period <= period_to,
                JournalEntry.account_code.startswith(cash_codes[0])
            ).union(
                *[db.query(JournalEntry.voucher_no).filter(
                    JournalEntry.company_id == company_id,
                    JournalEntry.period >= period_from,
                    JournalEntry.period <= period_to,
                    JournalEntry.account_code.startswith(c)
                ) for c in cash_codes[1:]]
            )
        )
    ).all()
    # 按凭证号分组
    vouchers = {}
    for e in entries:
        vouchers.setdefault(e.voucher_no, []).append(e)
    total = 0.0
    for vno, lines in vouchers.items():
        for l in lines:
            if l.account_code and any(l.account_code.startswith(c) for c in cash_codes):
                if inflow:
                    total += float(l.credit_amount or 0)  # 现金流入：贷现金
                else:
                    total += float(l.debit_amount or 0)  # 现金流出：借现金
    return round(total, 2)


def _cf_op_classified(company_id, period_from, period_to, cash_codes, activity_codes, db, is_inflow=True):
    """按对方科目对经营现金流分类（SQL优化版）"""
    cash_cond = or_(*[JournalEntry.account_code.startswith(c) for c in cash_codes])
    activity_cond = or_(*[JournalEntry.account_code.startswith(a) for a in activity_codes])

    cash_vnos = db.query(JournalEntry.voucher_no).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.period >= period_from,
        JournalEntry.period <= period_to,
        cash_cond
    ).distinct().subquery()

    activity_vnos = db.query(JournalEntry.voucher_no).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.period >= period_from,
        JournalEntry.period <= period_to,
        activity_cond
    ).distinct().subquery()

    target_vnos = db.query(cash_vnos.c.voucher_no).join(
        activity_vnos, cash_vnos.c.voucher_no == activity_vnos.c.voucher_no
    ).subquery()

    if is_inflow:
        amt = func.coalesce(JournalEntry.credit_amount, 0)
    else:
        amt = func.coalesce(JournalEntry.debit_amount, 0)

    total = db.query(func.coalesce(func.sum(amt), 0)).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.period >= period_from,
        JournalEntry.period <= period_to,
        JournalEntry.voucher_no.in_(db.query(target_vnos.c.voucher_no)),
        cash_cond
    ).scalar()

    return round(float(total or 0), 2)


def _cf_activity(company_id, period_from, period_to, cash_codes, activity_codes, db, is_inflow=True):
    """按对方科目分类计算特定活动的现金流量（SQL优化版）
    activity_codes: 对方科目前缀列表（如投资活动的固定资产科目）
    is_inflow: True=流入, False=流出
    """
    cash_cond = or_(*[JournalEntry.account_code.startswith(c) for c in cash_codes])
    activity_cond = or_(*[JournalEntry.account_code.startswith(a) for a in activity_codes])

    # 子查询：同时涉及现金科目和活动科目的凭证号
    cash_vnos = db.query(JournalEntry.voucher_no).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.period >= period_from,
        JournalEntry.period <= period_to,
        cash_cond
    ).distinct().subquery()

    activity_vnos = db.query(JournalEntry.voucher_no).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.period >= period_from,
        JournalEntry.period <= period_to,
        activity_cond
    ).distinct().subquery()

    target_vnos = db.query(cash_vnos.c.voucher_no).join(
        activity_vnos, cash_vnos.c.voucher_no == activity_vnos.c.voucher_no
    ).subquery()

    if is_inflow:
        amt = func.coalesce(JournalEntry.credit_amount, 0)
    else:
        amt = func.coalesce(JournalEntry.debit_amount, 0)

    total = db.query(func.coalesce(func.sum(amt), 0)).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.period >= period_from,
        JournalEntry.period <= period_to,
        JournalEntry.voucher_no.in_(db.query(target_vnos.c.voucher_no)),
        cash_cond
    ).scalar()

    return round(float(total or 0), 2)


@router.get("/api/reports/cash-flow")
def cash_flow_report(
    company_id: int = Query(...),
    period_from: str = Query(...),
    period_to: str = Query(...),
    db: Session = Depends(get_db)
):
    """现金流量表（会企03号）：直接法"""
    cash_codes = ["1001", "1002", "1003"]  # 库存现金、银行存款、其他货币资金

    def cf_row(label, current=0.0, prior=0.0, bold=False, highlight=False, indent=0):
        return {"label": label, "current": current, "prior": prior, "bold": bold, "highlight": highlight, "indent": indent}

    # 期初/期末现金余额
    begin_period = period_from[:4] + "-01"
    balances_end = _compute_period_balances(company_id, None, period_to, db)
    balances_begin = _compute_period_balances(company_id, None, _prev_period(begin_period), db)
    cash_end = sum(_bs_net(balances_end, c) for c in cash_codes)
    cash_begin = sum(_bs_net(balances_begin, c) for c in cash_codes)

    # 经营活动 — 按对方科目精细分类（直接法）
    # 销售商品、提供劳务收到的现金：现金流入 + 凭证中涉及收入/应收科目
    revenue_codes = ["6001", "6051", "1122", "1123"]
    sales_cash = _cf_op_classified(company_id, period_from, period_to, cash_codes, revenue_codes, db, is_inflow=True)
    # 购买商品、接受劳务支付的现金：现金流出 + 凭证中涉及成本/存货/应付科目
    purchase_codes = ["1401", "1402", "1403", "1404", "1405", "1406", "1407", "1408", "6401", "6402", "6403", "2202"]
    purchase_cash = _cf_op_classified(company_id, period_from, period_to, cash_codes, purchase_codes, db, is_inflow=False)
    # 支付给职工以及为职工支付的现金：现金流出 + 凭证中涉及应付职工薪酬
    employee_codes = ["221101", "221102", "221103", "221104", "221105", "221106", "221107", "221108"]
    employee_cash = _cf_op_classified(company_id, period_from, period_to, cash_codes, employee_codes, db, is_inflow=False)
    # 支付的各项税费：现金流出 + 凭证中涉及应交税费
    tax_codes = ["221009", "221010", "221011", "221012", "221013", "221014", "221015"]
    tax_cash = _cf_op_classified(company_id, period_from, period_to, cash_codes, tax_codes, db, is_inflow=False)
    # 其他：总经营现金流中扣除以上各项
    total_inflow = _cf_net_cash_by_accounts(company_id, period_from, period_to, cash_codes, db, inflow=True)
    total_outflow = _cf_net_cash_by_accounts(company_id, period_from, period_to, cash_codes, db, inflow=False)

    # 投资/筹资活动
    invest_codes = ["1601", "1602", "1604", "1701", "1702", "1511", "1512"]
    invest_inflow = _cf_activity(company_id, period_from, period_to, cash_codes, invest_codes, db, is_inflow=True)
    invest_outflow = _cf_activity(company_id, period_from, period_to, cash_codes, invest_codes, db, is_inflow=False)

    finance_codes = ["4001", "4002", "2001", "2501", "2701"]
    finance_inflow = _cf_activity(company_id, period_from, period_to, cash_codes, finance_codes, db, is_inflow=True)
    finance_outflow = _cf_activity(company_id, period_from, period_to, cash_codes, finance_codes, db, is_inflow=False)

    # 经营项中扣除投资/筹资的现金部分，再从中扣出已分类的，剩余为"其他"
    op_inflow = round(total_inflow - invest_inflow - finance_inflow, 2)
    op_outflow = round(total_outflow - invest_outflow - finance_outflow, 2)
    other_op_inflow = round(op_inflow - sales_cash, 2)
    other_op_outflow = round(op_outflow - purchase_cash - employee_cash - tax_cash, 2)
    op_net = round(op_inflow - op_outflow, 2)
    invest_net = round(invest_inflow - invest_outflow, 2)
    finance_net = round(finance_inflow - finance_outflow, 2)
    total_net = round(op_net + invest_net + finance_net, 2)

    items = [
        cf_row("一、经营活动产生的现金流量：", bold=True),
        cf_row("  销售商品、提供劳务收到的现金", sales_cash, indent=1),
        cf_row("  收到的税费返还", 0.0, indent=1),
        cf_row("  收到其他与经营活动有关的现金", other_op_inflow, indent=1),
        cf_row("经营活动现金流入小计", op_inflow, bold=True, highlight=True),
        cf_row("  购买商品、接受劳务支付的现金", purchase_cash, indent=1),
        cf_row("  支付给职工以及为职工支付的现金", employee_cash, indent=1),
        cf_row("  支付的各项税费", tax_cash, indent=1),
        cf_row("  支付其他与经营活动有关的现金", other_op_outflow, indent=1),
        cf_row("经营活动现金流出小计", op_outflow, bold=True, highlight=True),
        cf_row("经营活动产生的现金流量净额", op_net, bold=True, highlight=True),
        cf_row("二、投资活动产生的现金流量：", bold=True),
        cf_row("  收回投资收到的现金", 0.0, indent=1),
        cf_row("  取得投资收益收到的现金", 0.0, indent=1),
        cf_row("  处置固定资产、无形资产收回的现金净额", invest_inflow, indent=1),
        cf_row("  处置子公司及其他营业单位收到的现金净额", 0.0, indent=1),
        cf_row("  收到其他与投资活动有关的现金", 0.0, indent=1),
        cf_row("投资活动现金流入小计", invest_inflow, bold=True, highlight=True),
        cf_row("  购建固定资产、无形资产支付的现金", invest_outflow, indent=1),
        cf_row("  投资支付的现金", 0.0, indent=1),
        cf_row("  取得子公司及其他营业单位支付的现金净额", 0.0, indent=1),
        cf_row("  支付其他与投资活动有关的现金", 0.0, indent=1),
        cf_row("投资活动现金流出小计", invest_outflow, bold=True, highlight=True),
        cf_row("投资活动产生的现金流量净额", invest_net, bold=True, highlight=True),
        cf_row("三、筹资活动产生的现金流量：", bold=True),
        cf_row("  吸收投资收到的现金", finance_inflow, indent=1),
        cf_row("  取得借款收到的现金", 0.0, indent=1),
        cf_row("  收到其他与筹资活动有关的现金", 0.0, indent=1),
        cf_row("筹资活动现金流入小计", finance_inflow, bold=True, highlight=True),
        cf_row("  偿还债务支付的现金", finance_outflow, indent=1),
        cf_row("  分配股利、利润或偿付利息支付的现金", 0.0, indent=1),
        cf_row("  支付其他与筹资活动有关的现金", 0.0, indent=1),
        cf_row("筹资活动现金流出小计", finance_outflow, bold=True, highlight=True),
        cf_row("筹资活动产生的现金流量净额", finance_net, bold=True, highlight=True),
        cf_row("四、汇率变动对现金的影响", 0.0),
        cf_row("五、现金及现金等价物净增加额", total_net, bold=True, highlight=True),
        cf_row("  加：期初现金及现金等价物余额", cash_begin, indent=1),
        cf_row("六、期末现金及现金等价物余额", cash_end, bold=True, highlight=True),
    ]
    return {"items": items, "period_from": period_from, "period_to": period_to, "cash_begin": cash_begin, "cash_end": cash_end}


# ==================== 所有者权益变动表（企业会计准则一般企业—会企04号） ====================
ZERO9 = [0.0]*9           # 9 列零值
def _eq9(*indices_vals):  # (idx, val, ...) → 9 列数组
    a = [0.0]*9
    for i in range(0, len(indices_vals), 2):
        a[indices_vals[i]] = round(indices_vals[i+1], 2)
    return a

@router.get("/api/reports/equity-changes")
def equity_changes_report(
    company_id: int = Query(...),
    period: str = Query(...),
    db: Session = Depends(get_db)
):
    """所有者权益变动表（会企04号标准格式）"""
    yb = _bs_year_begin(period)
    begin_b = _compute_period_balances(company_id, None, yb, db)
    end_b = _compute_period_balances(company_id, None, period, db)

    py = period.split("-")[0]
    pl_items = _build_pl(company_id, f"{py}-01", period, db)
    net_profit = next((it["current"] for it in pl_items if it["label"] == "四、净利润"), 0.0)

    def eq_val(balances, prefix):
        d = sum(v["debit"] for code, v in balances.items() if code.startswith(prefix))
        c = sum(v["credit"] for code, v in balances.items() if code.startswith(prefix))
        return round(c - d, 2)  # 权益类：贷-借

    prefixes = ["4001", "4002", "4003", "4004", "4005", "4101", "4103", "4104"]
    begin_each = [eq_val(begin_b, p) if p else 0.0 for p in prefixes]
    end_each = [eq_val(end_b, p) if p else 0.0 for p in prefixes]
    # 未分配利润期末：直接取自科目余额表（而非 年初+净利润 简化公式）
    # 避免因前期差错更正、利润分配等调整导致的偏差
    end_each[7] = eq_val(end_b, "4104")
    # 合计辅助
    def total9(arr): return round(sum(arr), 2)
    begin9 = begin_each + [total9(begin_each)]
    end9 = end_each + [total9(end_each)]
    chg9 = [round(end9[i] - begin9[i], 2) for i in range(9)]

    cols = ["实收资本", "其他权益工具", "资本公积", "库存股", "其他综合收益", "专项储备", "盈余公积", "未分配利润", "所有者权益合计"]

    # 净利润只影响 未分配利润(7) 和 合计(8)
    np9 = [0.0]*9; np9[7] = net_profit; np9[8] = net_profit

    items = [
        {"label": "一、上年年末余额", "vals": begin9, "bold": True, "indent": 0, "highlight": False},
        {"label": "  加：会计政策变更", "vals": ZERO9, "bold": False, "indent": 1, "highlight": False},
        {"label": "  前期差错更正", "vals": ZERO9, "bold": False, "indent": 1, "highlight": False},
        {"label": "  其他", "vals": ZERO9, "bold": False, "indent": 1, "highlight": False},
        {"label": "二、本年年初余额", "vals": begin9, "bold": True, "indent": 0, "highlight": False},
        {"label": "三、本年增减变动金额（减少以\"-\"号填列）", "vals": chg9, "bold": True, "indent": 0, "highlight": False},
        {"label": "  （一）综合收益总额", "vals": np9, "bold": False, "indent": 1, "highlight": True},
        {"label": "  （二）所有者投入和减少资本", "vals": ZERO9, "bold": False, "indent": 1, "highlight": False},
        {"label": "    1. 所有者投入的普通股", "vals": ZERO9, "bold": False, "indent": 2, "highlight": False},
        {"label": "    2. 其他权益工具持有者投入资本", "vals": ZERO9, "bold": False, "indent": 2, "highlight": False},
        {"label": "    3. 股份支付计入所有者权益的金额", "vals": ZERO9, "bold": False, "indent": 2, "highlight": False},
        {"label": "    4. 其他", "vals": ZERO9, "bold": False, "indent": 2, "highlight": False},
        {"label": "  （三）利润分配", "vals": ZERO9, "bold": False, "indent": 1, "highlight": False},
        {"label": "    1. 提取盈余公积", "vals": ZERO9, "bold": False, "indent": 2, "highlight": False},
        {"label": "    2. 对所有者（或股东）的分配", "vals": ZERO9, "bold": False, "indent": 2, "highlight": False},
        {"label": "    3. 其他", "vals": ZERO9, "bold": False, "indent": 2, "highlight": False},
        {"label": "  （四）所有者权益内部结转", "vals": ZERO9, "bold": False, "indent": 1, "highlight": False},
        {"label": "    1. 资本公积转增资本（或股本）", "vals": ZERO9, "bold": False, "indent": 2, "highlight": False},
        {"label": "    2. 盈余公积转增资本（或股本）", "vals": ZERO9, "bold": False, "indent": 2, "highlight": False},
        {"label": "    3. 盈余公积弥补亏损", "vals": ZERO9, "bold": False, "indent": 2, "highlight": False},
        {"label": "    4. 设定受益计划变动额结转留存收益", "vals": ZERO9, "bold": False, "indent": 2, "highlight": False},
        {"label": "    5. 其他综合收益结转留存收益", "vals": ZERO9, "bold": False, "indent": 2, "highlight": False},
        {"label": "    6. 其他", "vals": ZERO9, "bold": False, "indent": 2, "highlight": False},
        {"label": "  （五）专项储备", "vals": ZERO9, "bold": False, "indent": 1, "highlight": False},
        {"label": "    1. 本期提取", "vals": ZERO9, "bold": False, "indent": 2, "highlight": False},
        {"label": "    2. 本期使用", "vals": ZERO9, "bold": False, "indent": 2, "highlight": False},
        {"label": "  （六）其他", "vals": ZERO9, "bold": False, "indent": 1, "highlight": False},
        {"label": "四、本年年末余额", "vals": end9, "bold": True, "indent": 0, "highlight": True},
    ]
    return {"columns": cols, "items": items, "period": period}


@router.post("/api/sales-invoices/batch-to-journal")
def sales_invoice_batch_to_journal(
    body: dict = Body(default=None),
    company_id: int = Query(...),
    db=Depends(get_db)
):
    """一键生成勾选发票的记账凭证"""
    ids = body.get("ids", []) if body else []
    if not ids:
        return {"message": "未选择任何发票", "generated": 0, "skipped": 0, "errors": []}

    invoices = db.query(SalesInvoice).filter(
        SalesInvoice.company_id == company_id,
        SalesInvoice.id.in_(ids)
    ).order_by(SalesInvoice.invoice_date, SalesInvoice.id).all()

    generated = 0
    skipped = 0
    errors = []

    for inv in invoices:
        try:
            existing = db.query(JournalEntry).filter(
                JournalEntry.company_id == company_id,
                JournalEntry.source == "销项发票",
                JournalEntry.ref_id == inv.id
            ).first()
            if existing:
                skipped += 1
                continue

            from database import auto_generate_single_invoice
            auto_generate_single_invoice(db, inv)
            generated += 1
        except Exception as e:
            errors.append(f"发票{inv.id}({inv.invoice_no}): {str(e)}")

    db.commit()
    msg = f"批量生成完成：生成 {generated} 笔凭证"
    if skipped > 0:
        msg += f"，跳过 {skipped} 笔（已有凭证）"
    if errors:
        msg += f"，{len(errors)} 笔失败"
        print("Batch journal errors:", errors)
    return {"message": msg, "generated": generated, "skipped": skipped, "errors": errors}


@router.post("/api/sales-invoices/auto-voucher")
def sales_invoice_auto_voucher(company_id: int = Query(...), db=Depends(get_db)):
    """导入后自动为所有未生成凭证的销项发票生成序时账"""
    # 查询已有凭证的发票ID（通过 JournalEntry.source=销项发票 + ref_id 判断）
    existing_ids = set(r[0] for r in db.query(JournalEntry.ref_id).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.source == "销项发票",
        JournalEntry.ref_id.isnot(None)
    ).all())
    
    invoices = db.query(SalesInvoice).filter(
        SalesInvoice.company_id == company_id,
        ~SalesInvoice.id.in_(existing_ids) if existing_ids else True
    ).order_by(SalesInvoice.invoice_date, SalesInvoice.id).all()
    if not invoices:
        return {"message": "无待生成凭证的发票", "generated": 0}
    
    generated = 0
    errors = []
    for inv in invoices:
        try:
            from database import auto_generate_single_invoice
            auto_generate_single_invoice(db, inv)
            generated += 1
        except Exception as e:
            errors.append(f"发票{inv.id}({inv.invoice_no}): {str(e)}")
    
    db.commit()
    msg = f"自动生成 {generated} 笔凭证"
    if errors:
        msg += f"，{len(errors)} 笔失败"
    return {"message": msg, "generated": generated, "errors": errors}


@router.post("/api/input-vat-deductions/auto-voucher")
def input_vat_auto_voucher(company_id: int = Query(...), db=Depends(get_db)):
    """导入进项抵扣后自动生成序时账凭证"""
    # 查找所有未生成凭证的进项抵扣记录，按期分组
    unprocessed = db.query(InputVATDeduction).filter(
        InputVATDeduction.company_id == company_id,
        or_(InputVATDeduction.voucher_no == None, InputVATDeduction.voucher_no == "")
    ).all()
    if not unprocessed:
        return {"message": "无待生成凭证的进项抵扣", "generated": 0}
    
    periods = set()
    for d in unprocessed:
        p = d.deduction_period
        if not p and d.invoice_date:
            p = str(d.invoice_date)[:7]  # 从发票日期推导
        if p:
            periods.add(p)
    total = 0
    for period in periods:
        total += auto_generate_input_vat_for_period(db, company_id, period)
    
    db.commit()
    return {"message": f"自动生成 {total} 条进项抵扣凭证（共 {len(periods)} 个期间）", "generated": total}


@router.post("/api/sales-invoices/{invoice_id}/to-journal")
def sales_invoice_to_journal(invoice_id: int, company_id: int = Query(...), db=Depends(get_db)):
    """将单张销项发票生成记账凭证（分录）到序时账（允许重新生成，先删旧凭证）"""
    inv = db.query(SalesInvoice).filter(SalesInvoice.company_id == company_id, SalesInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "发票不存在")
    def get_full_name(code):
        """构建科目的全级次名称，如 221001001 → 应交税费/应交增值税/销项税额"""
        parts = []
        cur = code
        while cur:
            acc = db.query(Account).filter(
                Account.company_id == inv.company_id,
                Account.code == cur
            ).first()
            if not acc:
                break
            parts.insert(0, acc.name)
            cur = acc.parent_code
        return "/".join(parts) if parts else code

    def ensure_revenue_sub(goods_name):
        """确保主营业务收入下存在对应货物的子科目，返回 (code, full_name)"""
        if not goods_name:
            return ("6001", get_full_name("6001"))
        existing = db.query(Account).filter(
            Account.company_id == inv.company_id,
            Account.parent_code == "6001",
            Account.name == goods_name
        ).first()
        if existing:
            return (existing.code, get_full_name(existing.code))
        max_sub = db.query(Account.code).filter(
            Account.company_id == inv.company_id,
            Account.parent_code == "6001"
        ).order_by(Account.code.desc()).first()
        next_num = int(max_sub[0][4:7]) + 1 if (max_sub and max_sub[0] and len(max_sub[0]) >= 6) else 1
        # 科目编码规则：6001 下级为 600101/600102/...（6位，2位序号）
        new_code = f"6001{next_num:02d}"
        new_acc = Account(
            company_id=inv.company_id,
            code=new_code,
            name=goods_name,
            category="收入",
            balance_direction="贷",
            level=2,
            parent_code="6001",
        )
        db.add(new_acc)
        db.flush()
        return (new_code, get_full_name(new_code))

    period = inv.invoice_date.strftime("%Y-%m") if inv.invoice_date else datetime.now().strftime("%Y-%m")

    max_no = db.query(JournalEntry.voucher_no).filter(
        JournalEntry.company_id == inv.company_id,
        JournalEntry.period == period,
        JournalEntry.voucher_word == "记"
    ).order_by(JournalEntry.voucher_no.desc()).first()
    next_voucher_no = (max_no[0] + 1) if max_no and max_no[0] else 1

    date_str = inv.invoice_date.strftime("%Y-%m-%d") if inv.invoice_date else period + "-01"
    buyer = inv.buyer_name or "客户"
    goods = inv.goods_name or ""
    summary = f"销售{goods or '货物'}给{buyer}"

    # 先删旧凭证（允许重新生成）
    db.query(JournalEntry).filter(
        JournalEntry.company_id == inv.company_id,
        JournalEntry.source == "销项发票",
        JournalEntry.ref_id == inv.id
    ).delete(synchronize_session=False)
    db.flush()

    rev_code, rev_name = ensure_revenue_sub(goods)

    entries = [
        JournalEntry(
            company_id=inv.company_id,
            entry_date=datetime.strptime(date_str, "%Y-%m-%d").date(),
            period=period,
            voucher_word="记",
            voucher_no=next_voucher_no,
            summary=summary,
            account_code="1122",
            account_name=get_full_name("1122"),
            debit_amount=inv.total_amount,
            credit_amount=0,
            contact_project=buyer,
            spec_model=inv.spec or "",
            quantity=inv.quantity or 0,
            unit=inv.unit or "",
            unit_price=inv.unit_price or 0,
            source="销项发票", ref_id=inv.id,
        ),
        JournalEntry(
            company_id=inv.company_id,
            entry_date=datetime.strptime(date_str, "%Y-%m-%d").date(),
            period=period,
            voucher_word="记",
            voucher_no=next_voucher_no,
            summary=summary,
            account_code=rev_code,
            account_name=rev_name,
            debit_amount=0,
            credit_amount=inv.amount,
            contact_project="",
            spec_model=inv.spec or "",
            quantity=inv.quantity or 0,
            unit=inv.unit or "",
            unit_price=inv.unit_price or 0,
            source="销项发票", ref_id=inv.id,
        ),
        JournalEntry(
            company_id=inv.company_id,
            entry_date=datetime.strptime(date_str, "%Y-%m-%d").date(),
            period=period,
            voucher_word="记",
            voucher_no=next_voucher_no,
            summary=f"{summary}（增值税）",
            account_code="221001001",
            account_name=get_full_name("221001001"),
            debit_amount=0,
            credit_amount=inv.tax_amount,
            contact_project="",
            spec_model=inv.spec or "",
            quantity=inv.quantity or 0,
            unit=inv.unit or "",
            unit_price=inv.unit_price or 0,
            source="销项发票", ref_id=inv.id,
        ),
    ]
    for e in entries:
        db.add(e)
    db.commit()
    return {"message": f"已生成凭证，凭证号：记-{next_voucher_no}", "voucher_no": next_voucher_no, "period": period}



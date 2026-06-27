"""
银行流水管理模块 - 从 main.py 自动拆分
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Form
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
import os, io, json, openpyxl, re as _re_module

from database import get_db, BankRule, BankTransaction, BankConfig, Account, JournalEntry, InputVATDeduction, BookkeepingInvoice

router = APIRouter(tags=["银行流水"])


# ═══ Pydantic 模型 ═══

class BankRuleCreate(BaseModel):
    keyword: str
    account_code: str
    account_name: Optional[str] = None
    transaction_type: str = "全部"
    direction: str = "auto"
    priority: int = 0

class BankRuleUpdate(BaseModel):
    keyword: Optional[str] = None
    account_code: Optional[str] = None
    account_name: Optional[str] = None
    transaction_type: Optional[str] = None
    direction: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[int] = None

class BankAccountCreate(BaseModel):
    account_name: str
    account_no: str
    bank_name: str
    is_active: Optional[bool] = True

class BankAccountUpdate(BaseModel):
    account_name: Optional[str] = None
    account_no: Optional[str] = None
    bank_name: Optional[str] = None
    is_active: Optional[bool] = None

class BankConfigUpdate(BaseModel):
    key: str
    value: str


@router.get("/api/bank-rules")
def list_bank_rules(
    company_id: int = Query(...),
    transaction_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(BankRule).filter(BankRule.company_id == company_id, BankRule.is_active == 1)
    if transaction_type and transaction_type != "全部":
        q = q.filter(or_(BankRule.transaction_type == transaction_type, BankRule.transaction_type == "全部"))
    rules = q.order_by(BankRule.priority.desc(), BankRule.id.asc()).all()
    return [{
        "id": r.id, "keyword": r.keyword, "account_code": r.account_code,
        "account_name": r.account_name, "transaction_type": r.transaction_type,
        "direction": r.direction, "priority": r.priority, "is_active": r.is_active,
    } for r in rules]


@router.post("/api/bank-rules")
def create_bank_rule(data: BankRuleCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    # 确保科目存在
    acct = db.query(Account).filter(Account.company_id == company_id, Account.code == data.account_code).first()
    rule = BankRule(
        company_id=company_id,
        keyword=data.keyword,
        account_code=data.account_code,
        account_name=acct.name if acct else data.account_name,
        transaction_type=data.transaction_type,
        direction=data.direction,
        priority=data.priority,
        is_active=1,
    )
    db.add(rule)
    db.commit()
    return {"message": "规则已添加", "id": rule.id}


@router.put("/api/bank-rules/{rule_id}")
def update_bank_rule(rule_id: int, data: BankRuleUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    rule = db.query(BankRule).filter(BankRule.company_id == company_id, BankRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404, detail="规则不存在")
    for field in ["keyword", "account_code", "account_name", "transaction_type", "direction", "priority", "is_active"]:
        val = getattr(data, field, None)
        if val is not None:
            if field == "account_code":
                acct = db.query(Account).filter(Account.company_id == company_id, Account.code == val).first()
                if acct:
                    setattr(rule, "account_name", acct.name)
            setattr(rule, field, val)
    rule.updated_at = datetime.now()
    db.commit()
    return {"message": "规则已更新"}


@router.delete("/api/bank-rules/{rule_id}")
def delete_bank_rule(rule_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    rule = db.query(BankRule).filter(BankRule.company_id == company_id, BankRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404, detail="规则不存在")
    rule.is_active = 0
    rule.updated_at = datetime.now()
    db.commit()
    return {"message": "规则已删除"}


# ==================== 银行流水 ====================

class BankTransactionCreate(BaseModel):
    bank_config_id: Optional[int] = None
    transaction_date: date
    transaction_time: Optional[str] = None
    application_date: Optional[date] = None
    voucher_no: Optional[str] = None
    debit_amount: Optional[float] = 0.0
    credit_amount: Optional[float] = 0.0
    balance: Optional[float] = 0.0
    counterparty_name: Optional[str] = None
    counterparty_account: Optional[str] = None
    counterparty_bank: Optional[str] = None
    transaction_serial_no: Optional[str] = None
    voucher_seq: Optional[str] = None
    record_status: Optional[str] = None
    summary: Optional[str] = None
    transaction_remark: Optional[str] = None
    account_type: Optional[str] = None
    # 旧字段（向后兼容）
    amount: Optional[float] = 0.0
    transaction_type: Optional[str] = "支出"
    payment_method: Optional[str] = None
    reference_no: Optional[str] = None
    raw_data: Optional[str] = None
    remark: Optional[str] = None


class BankTransactionUpdate(BaseModel):
    bank_config_id: Optional[int] = None
    transaction_date: Optional[date] = None
    transaction_time: Optional[str] = None
    application_date: Optional[date] = None
    voucher_no: Optional[str] = None
    debit_amount: Optional[float] = None
    credit_amount: Optional[float] = None
    balance: Optional[float] = None
    counterparty_name: Optional[str] = None
    counterparty_account: Optional[str] = None
    counterparty_bank: Optional[str] = None
    transaction_serial_no: Optional[str] = None
    voucher_seq: Optional[str] = None
    record_status: Optional[str] = None
    summary: Optional[str] = None
    transaction_remark: Optional[str] = None
    account_type: Optional[str] = None
    # 旧字段（向后兼容）
    amount: Optional[float] = None
    transaction_type: Optional[str] = None
    payment_method: Optional[str] = None
    reference_no: Optional[str] = None
    raw_data: Optional[str] = None
    remark: Optional[str] = None


@router.get("/api/bank-transactions")
def list_bank_transactions(
    company_id: int = Query(...),
    bank_config_id: Optional[int] = None,
    transaction_type: Optional[str] = None,
    keyword: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    q = db.query(BankTransaction).filter(BankTransaction.company_id == company_id)
    if bank_config_id:
        q = q.filter(BankTransaction.bank_config_id == bank_config_id)
    if transaction_type:
        q = q.filter(BankTransaction.transaction_type == transaction_type)
    if date_from:
        q = q.filter(BankTransaction.transaction_date >= date_from)
    if date_to:
        q = q.filter(BankTransaction.transaction_date <= date_to)
    if keyword:
        q = q.filter(or_(
            BankTransaction.counterparty_name.contains(keyword),
            BankTransaction.summary.contains(keyword),
            BankTransaction.reference_no.contains(keyword)
        ))
    txs = q.order_by(BankTransaction.transaction_date.desc(), BankTransaction.id.desc()).offset(skip).limit(limit).all()

    # 动态查询凭证号：按 summary + 1002科目匹配（双分录中银行存款侧即代表该凭证）
    # 银行流水可能被多个模块匹配生成凭证（银行流水自动生成 / 社保缴纳 / 公积金缴纳），
    # summary 格式可能不同，需全部收集后匹配
    voucher_map = {}
    if txs:
        summaries = []
        # 收集所有可能的 summary 格式
        for tx in txs:
            cp = tx.counterparty_name or tx.summary or "银行流水"
            summaries.append(f"银行流水-#{tx.id}-{cp}")
            summaries.append(f"社保缴纳-#{tx.id}")
            summaries.append(f"公积金缴纳-#{tx.id}")
        summaries = list(set(summaries))
        bank_jes = db.query(JournalEntry).filter(
            JournalEntry.company_id == company_id,
            JournalEntry.account_code == "1002",
            JournalEntry.summary.in_(summaries)
        ).all() if summaries else []
        # 构建 summary → 凭证号 映射
        summary_to_voucher = {}
        for je in bank_jes:
            summary_to_voucher[je.summary] = f"{je.voucher_word}-{je.voucher_no}"
        for tx in txs:
            cp = tx.counterparty_name or tx.summary or "银行流水"
            target = f"银行流水-#{tx.id}-{cp}"
            voucher_no = summary_to_voucher.get(target, "")
            if not voucher_no:
                # 尝试社保缴纳/公积金缴纳 summary 格式
                for alt_fmt in [f"社保缴纳-#{tx.id}", f"公积金缴纳-#{tx.id}"]:
                    alt = summary_to_voucher.get(alt_fmt)
                    if alt:
                        voucher_no = alt
                        break
            voucher_map[tx.id] = voucher_no

    return [{
        "id": tx.id, "bank_config_id": tx.bank_config_id,
        "transaction_date": str(tx.transaction_date) if tx.transaction_date else "",
        "transaction_time": str(tx.transaction_time) if tx.transaction_time else "",
        "application_date": str(tx.application_date) if tx.application_date else "",
        "voucher_no": tx.voucher_no or "",
        "debit_amount": tx.debit_amount or 0,
        "credit_amount": tx.credit_amount or 0,
        "balance": tx.balance or 0,
        "counterparty_account": tx.counterparty_account or "",
        "counterparty_name": tx.counterparty_name or "",
        "counterparty_bank": tx.counterparty_bank or "",
        "transaction_serial_no": tx.transaction_serial_no or "",
        "voucher_seq": tx.voucher_seq or "",
        "record_status": tx.record_status or "",
        "summary": tx.summary or "",
        "transaction_remark": tx.transaction_remark or "",
        "account_type": tx.account_type or "",
        # 旧字段（向后兼容）
        "amount": tx.amount or 0,
        "transaction_type": tx.transaction_type,
        "payment_method": tx.payment_method or "",
        "reference_no": tx.reference_no or "",
        "raw_data": tx.raw_data or "{}",
        "remark": tx.remark or "",
        # 凭证号：优先读 DB 存储值（所有凭证生成路径都会回写此字段），动态匹配兜底
        "journal_voucher_no": tx.journal_voucher_no or voucher_map.get(tx.id, ""),
        "created_at": str(tx.created_at) if tx.created_at else ""
    } for tx in txs]


@router.post("/api/bank-transactions")
def create_bank_transaction(data: BankTransactionCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    tx = BankTransaction(company_id=company_id, **data.model_dump())
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return {"id": tx.id, "message": "银行流水创建成功"}


@router.get("/api/bank-transactions/stats")
def bank_transaction_stats(
    company_id: int = Query(...),
    bank_config_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db)
):
    base = db.query(BankTransaction).filter(BankTransaction.company_id == company_id)
    if bank_config_id:
        base = base.filter(BankTransaction.bank_config_id == bank_config_id)
    if date_from:
        base = base.filter(BankTransaction.transaction_date >= date_from)
    if date_to:
        base = base.filter(BankTransaction.transaction_date <= date_to)

    total_count = base.count()
    income_base = base.filter(BankTransaction.transaction_type == "收入")
    expense_base = base.filter(BankTransaction.transaction_type == "支出")

    total_income = income_base.with_entities(func.sum(BankTransaction.credit_amount)).scalar() or 0
    total_expense = expense_base.with_entities(func.sum(BankTransaction.debit_amount)).scalar() or 0
    # 新字段口径：借方=支出, 贷方=收入
    total_debit = base.with_entities(func.sum(BankTransaction.debit_amount)).scalar() or 0
    total_credit = base.with_entities(func.sum(BankTransaction.credit_amount)).scalar() or 0
    income_count = income_base.count()
    expense_count = expense_base.count()

    # 最新余额（取最后一条）
    last_tx = base.order_by(BankTransaction.transaction_date.desc(), BankTransaction.id.desc()).first()
    last_balance = last_tx.balance if last_tx else 0

    return {
        "total_count": total_count,
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "income_count": income_count,
        "expense_count": expense_count,
        "last_balance": round(last_balance, 2)
    }


class BatchDeleteRequest(BaseModel):
    ids: List[int]


@router.post("/api/bank-transactions/batch-delete")
def batch_delete_bank_transactions(req: BatchDeleteRequest, company_id: int = Query(...), db: Session = Depends(get_db)):
    deleted = db.query(BankTransaction).filter(
        BankTransaction.company_id == company_id,
        BankTransaction.id.in_(req.ids)
    ).delete(synchronize_session=False)
    db.commit()
    return {"message": f"成功删除 {deleted} 条流水记录", "count": deleted}


@router.get("/api/bank-transactions/{tx_id}")
def get_bank_transaction(tx_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    tx = db.query(BankTransaction).filter(BankTransaction.company_id == company_id, BankTransaction.id == tx_id).first()
    if not tx:
        raise HTTPException(404, detail="流水记录不存在")
    return {
        "id": tx.id, "bank_config_id": tx.bank_config_id,
        "transaction_date": str(tx.transaction_date) if tx.transaction_date else "",
        "amount": tx.amount or 0, "balance": tx.balance or 0,
        "counterparty_name": tx.counterparty_name or "",
        "counterparty_account": tx.counterparty_account or "",
        "counterparty_bank": tx.counterparty_bank or "",
        "summary": tx.summary or "",
        "transaction_type": tx.transaction_type,
        "payment_method": tx.payment_method or "",
        "voucher_no": tx.voucher_no or "",
        "reference_no": tx.reference_no or "",
        "raw_data": tx.raw_data or "{}",
        "remark": tx.remark or "",
        "created_at": str(tx.created_at) if tx.created_at else ""
    }


@router.put("/api/bank-transactions/{tx_id}")
def update_bank_transaction(tx_id: int, data: BankTransactionUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    tx = db.query(BankTransaction).filter(BankTransaction.company_id == company_id, BankTransaction.id == tx_id).first()
    if not tx:
        raise HTTPException(404, detail="流水记录不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(tx, k, v)
    db.commit()
    return {"message": "更新成功"}


@router.delete("/api/bank-transactions/{tx_id}")
def delete_bank_transaction(tx_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    tx = db.query(BankTransaction).filter(BankTransaction.company_id == company_id, BankTransaction.id == tx_id).first()
    if not tx:
        raise HTTPException(404, detail="流水记录不存在")
    db.delete(tx)
    db.commit()
    return {"message": "删除成功"}


@router.post("/api/bank-transactions/{tx_id}/to-journal")
def bank_transaction_to_journal(tx_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    """为单条银行流水生成双分录记账凭证（使用与批量生成相同的智能分类逻辑）"""
    tx = db.query(BankTransaction).filter(
        BankTransaction.id == tx_id,
        BankTransaction.company_id == company_id
    ).first()
    if not tx:
        raise HTTPException(404, "流水记录不存在")

    cp = tx.counterparty_name or tx.summary or "银行流水"
    summary_tag = f"银行流水-#{tx_id}-{cp}"

    # 去重：已生成凭证则跳过
    if tx.journal_voucher_no:
        raise HTTPException(400, f"该流水已生成凭证：{tx.journal_voucher_no}")

    period = tx.transaction_date.strftime("%Y-%m") if tx.transaction_date else datetime.now().strftime("%Y-%m")
    max_no = db.query(JournalEntry.voucher_no).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.period == period,
        JournalEntry.voucher_word == "记"
    ).order_by(JournalEntry.voucher_no.desc()).first()
    next_voucher_no = (max_no[0] + 1) if max_no and max_no[0] else 1
    date_str = tx.transaction_date.strftime("%Y-%m-%d") if tx.transaction_date else period + "-01"

    # 确保科目存在（复用 _generate_bank_journals 的依赖）
    _ensure_account(db, company_id, "1002", "银行存款", "资产", "借")
    _ensure_account(db, company_id, "1122", "应收账款", "资产", "借")
    _ensure_account(db, company_id, "1123", "预付账款", "资产", "借")
    _ensure_account(db, company_id, "2202", "应付账款", "负债", "贷")
    _ensure_account(db, company_id, "1221", "其他应收款", "资产", "借")
    _ensure_account(db, company_id, "2241", "其他应付款", "负债", "贷")
    _ensure_account(db, company_id, "4001", "实收资本", "权益", "贷")
    _ensure_account(db, company_id, "410401", "利润分配-应付股利", "权益", "贷")
    _ensure_account(db, company_id, "221101", "应付职工薪酬-工资", "负债", "贷")

    is_debit = tx.amount is not None and tx.amount < 0
    amount = abs(float(tx.amount) if tx.amount else 0)

    # 使用与批量生成相同的智能分类逻辑（跨实体匹配：股东/人员/客户/供应商）
    result = _classify_bank_tx(db, company_id, tx)
    if result is None:
        raise HTTPException(400, "无法自动分类该银行流水，请完善银行流水规则后再生成凭证")
    cp_code, cp_name, match_type, contact_name = result

    # contact_project：人员匹配时用员工规范姓名，其余用原始对方名称
    contact_proj = contact_name if contact_name else cp

    # 摘要修正
    if match_type == "customer_deposit":
        summary_tag = f"银行流水-#{tx_id}-{contact_proj}（保证金）"
    elif match_type == "prepaid_supplier":
        summary_tag = f"银行流水-#{tx_id}-{contact_proj}（预付供应商，待发票冲销）"

    # 工资匹配上月数据（老邓 2026-06-10）
    if match_type == "salary":
        salary_note = ""
        tx_date_val = tx.transaction_date
        if tx_date_val and hasattr(tx_date_val, 'year'):
            prev_month = tx_date_val.month - 1
            prev_year = tx_date_val.year
            if prev_month == 0:
                prev_month = 12
                prev_year -= 1
            prev_period = f"{prev_year}-{prev_month:02d}"
            salary_records = db.query(SalaryRecord).filter(
                SalaryRecord.company_id == company_id,
                SalaryRecord.period == prev_period
            ).all()
            if salary_records:
                total_net = sum(float(sr.net_salary or 0) for sr in salary_records)
                amt = float(amount)
                if abs(amt - total_net) < 0.02:
                    salary_note = "（已匹配上月工资表）"
                elif amt < total_net - 0.02:
                    salary_note = "（支付<计提，存有工资未发放）"
                else:
                    salary_note = "（支付>计提，可能存在工资未计提）"
            else:
                salary_note = "（无上月工资表数据）"
        summary_tag = f"{summary_tag}{salary_note}"

    if is_debit:
        # 付款：借 对方科目  贷 银行存款
        db.add(JournalEntry(
            company_id=company_id,
            entry_date=datetime.strptime(date_str, "%Y-%m-%d").date(),
            period=period, voucher_word="记", voucher_no=next_voucher_no,
            summary=summary_tag,
            account_code=cp_code, account_name=cp_name,
            debit_amount=amount, credit_amount=0,
            contact_project=contact_proj, source="银行流水", ref_id=tx_id
        ))
        db.add(JournalEntry(
            company_id=company_id,
            entry_date=datetime.strptime(date_str, "%Y-%m-%d").date(),
            period=period, voucher_word="记", voucher_no=next_voucher_no,
            summary=summary_tag,
            account_code="1002", account_name="银行存款",
            debit_amount=0, credit_amount=amount,
            contact_project=contact_proj, source="银行流水", ref_id=tx_id
        ))
    else:
        # 收款：借 银行存款  贷 对方科目
        db.add(JournalEntry(
            company_id=company_id,
            entry_date=datetime.strptime(date_str, "%Y-%m-%d").date(),
            period=period, voucher_word="记", voucher_no=next_voucher_no,
            summary=summary_tag,
            account_code="1002", account_name="银行存款",
            debit_amount=amount, credit_amount=0,
            contact_project=contact_proj, source="银行流水", ref_id=tx_id
        ))
        db.add(JournalEntry(
            company_id=company_id,
            entry_date=datetime.strptime(date_str, "%Y-%m-%d").date(),
            period=period, voucher_word="记", voucher_no=next_voucher_no,
            summary=summary_tag,
            account_code=cp_code, account_name=cp_name,
            debit_amount=0, credit_amount=amount,
            contact_project=contact_proj, source="银行流水", ref_id=tx_id
        ))

    # 老邓 2026-06-10：自动建档供应商/客户（即时创建，不依赖双源）
    entity_name = contact_name or (tx.counterparty_name or "").strip()
    if entity_name and len(entity_name) >= 2:
        _NON_ENTITY = ("手续费", "金库", "公积金", "待处理", "出售凭证", "业务收入", "国家金库", "税务", "国库")
        if not any(kw in entity_name for kw in _NON_ENTITY):
            if match_type in ("supplier", "supplier_invoice", "supplier_payment"):
                norm = _normalize_customer_name(entity_name)
                existing = db.query(Supplier).filter(
                    Supplier.company_id == company_id,
                    Supplier._fingerprint == norm
                ).first()
                if not existing:
                    max_code = db.query(Supplier.code).filter(
                        Supplier.company_id == company_id,
                        Supplier.code.like("GYS%")
                    ).order_by(Supplier.code.desc()).first()
                    next_num = 1
                    if max_code and max_code[0] and max_code[0].startswith("GYS"):
                        try:
                            next_num = int(max_code[0][3:]) + 1
                        except ValueError:
                            pass
                    code = f"GYS{next_num:03d}"
                    db.add(Supplier(
                        company_id=company_id, code=code,
                        name=entity_name, _fingerprint=norm, is_active=True,
                    ))
                    db.flush()
            elif match_type in ("customer", "customer_invoice", "customer_fallback", "customer_deposit", "customer_deposit_refund"):
                norm = _normalize_customer_name(entity_name)
                existing = db.query(Customer).filter(
                    Customer.company_id == company_id,
                    Customer._fingerprint == norm
                ).first()
                if not existing:
                    max_code = db.query(Customer.code).filter(
                        Customer.company_id == company_id,
                        Customer.code.like("KH%")
                    ).order_by(Customer.code.desc()).first()
                    next_num = 1
                    if max_code and max_code[0] and max_code[0].startswith("KH"):
                        try:
                            next_num = int(max_code[0][2:]) + 1
                        except ValueError:
                            pass
                    code = f"KH{next_num:03d}"
                    db.add(Customer(
                        company_id=company_id, code=code,
                        name=entity_name, _fingerprint=norm, is_active=True,
                    ))
                    db.flush()

    voucher_str = f"记-{next_voucher_no}"
    tx.journal_voucher_no = voucher_str
    db.commit()
    return {"message": f"已生成凭证：{voucher_str}（匹配类型：{match_type}，科目：{cp_name}）", "voucher_no": voucher_str, "period": period}



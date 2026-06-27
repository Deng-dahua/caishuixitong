"""
序时账管理模块 - 从 main.py 自动拆分
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

from database import get_db

router = APIRouter(tags=["序时账"])

class JournalEntryCreate(BaseModel):
    entry_date: date
    period: str
    voucher_word: str = "记"
    voucher_no: int
    attach_count: Optional[int] = 0
    summary: Optional[str] = None
    account_code: str
    account_name: Optional[str] = None
    debit_amount: Optional[float] = 0.0
    credit_amount: Optional[float] = 0.0
    prepared_by: Optional[str] = None
    reviewed_by: Optional[str] = None
    is_reviewed: Optional[bool] = False
    remark: Optional[str] = None
    contact_project: Optional[str] = None
    spec_model: Optional[str] = None
    quantity: Optional[float] = 0.0
    unit: Optional[str] = None
    unit_price: Optional[float] = 0.0


class JournalEntryUpdate(BaseModel):
    entry_date: Optional[date] = None
    period: Optional[str] = None
    voucher_word: Optional[str] = None
    voucher_no: Optional[int] = None
    attach_count: Optional[int] = None
    summary: Optional[str] = None
    account_code: Optional[str] = None
    account_name: Optional[str] = None
    debit_amount: Optional[float] = None
    credit_amount: Optional[float] = None
    prepared_by: Optional[str] = None
    reviewed_by: Optional[str] = None
    is_reviewed: Optional[bool] = None
    remark: Optional[str] = None
    contact_project: Optional[str] = None
    spec_model: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None


@router.get("/api/journal-entries")
def list_journal_entries(
    company_id: int = Query(...),
    period: Optional[str] = None,
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
    voucher_word: Optional[str] = None,
    keyword: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    is_reviewed: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    q = db.query(JournalEntry).filter(JournalEntry.company_id == company_id)
    if period:
        q = q.filter(JournalEntry.period == period)
    if period_from:
        q = q.filter(JournalEntry.period >= period_from)
    if period_to:
        q = q.filter(JournalEntry.period <= period_to)
    if voucher_word:
        q = q.filter(JournalEntry.voucher_word == voucher_word)
    if is_reviewed is not None:
        q = q.filter(JournalEntry.is_reviewed == is_reviewed)
    if date_from:
        q = q.filter(JournalEntry.entry_date >= date_from)
    if date_to:
        q = q.filter(JournalEntry.entry_date <= date_to)
    if keyword:
        q = q.filter(or_(
            JournalEntry.summary.contains(keyword),
            JournalEntry.account_name.contains(keyword),
            JournalEntry.account_code.contains(keyword),
        ))
    total = q.count()

    # 辅助：判断是否同凭证
    def _same_voucher(a, b):
        return a.period == b.period and a.voucher_word == b.voucher_word and a.voucher_no == b.voucher_no

    def _same_voucher_filter(v):
        return and_(
            JournalEntry.period == v.period,
            JournalEntry.voucher_word == v.voucher_word,
            JournalEntry.voucher_no == v.voucher_no,
        )

    entries = q.order_by(JournalEntry.voucher_no.asc(), JournalEntry.id.asc()).offset(skip).limit(limit).all()
    effective_consumed = limit  # 本页在 DB 中实际消耗了多少条记录

    if entries:
        # --- 处理开头：如果首页分录的凭证从前一页延续过来，补全该凭证全部前置分录 ---
        if skip > 0:
            first = entries[0]
            prior_count = q.filter(
                _same_voucher_filter(first),
                JournalEntry.id < first.id,
            ).count()
            if prior_count > 0:
                prior_entries = q.filter(
                    _same_voucher_filter(first),
                    JournalEntry.id < first.id,
                ).order_by(JournalEntry.id.asc()).all()
                entries = prior_entries + entries

        # --- 处理末尾：如果末尾凭证还有分录在下一页 ---
        last = entries[-1]
        in_batch = sum(1 for e in entries if _same_voucher(e, last))
        total_same_voucher = q.filter(_same_voucher_filter(last)).count()
        remaining = total_same_voucher - in_batch

        if remaining > 0:
            if total_same_voucher > limit:
                # 大凭证（分录数 > 单页上限）：取剩余分录补全到本页
                remaining_entries = q.filter(
                    _same_voucher_filter(last),
                    JournalEntry.id > last.id,
                ).order_by(JournalEntry.id.asc()).all()
                entries = entries + remaining_entries
                effective_consumed = limit + len(remaining_entries)
            else:
                # 小凭证：排除该凭证全部分录，推到下一页
                entries = [e for e in entries if not _same_voucher(e, last)]
                effective_consumed = limit - in_batch

    next_skip = skip + effective_consumed

    hierarchy = _build_account_hierarchy(db, company_id)
    return {
        "total": total,
        "next_skip": next_skip,
        "items": [{
            "id": e.id, "entry_date": str(e.entry_date), "period": e.period,
            "voucher_word": e.voucher_word, "voucher_no": e.voucher_no,
            "attach_count": e.attach_count or 0, "summary": e.summary or "",
            "account_code": e.account_code, "account_name": e.account_name or "",
            "account_full_name": hierarchy.get(e.account_code, e.account_name or ""),
            "debit_amount": e.debit_amount or 0, "credit_amount": e.credit_amount or 0,
            "prepared_by": e.prepared_by or "", "reviewed_by": e.reviewed_by or "",
            "is_reviewed": e.is_reviewed, "remark": e.remark or "",
            "contact_project": e.contact_project or "",
            "spec_model": e.spec_model or "",
            "quantity": e.quantity or 0, "unit": e.unit or "",
            "unit_price": e.unit_price or 0,
            "source": e.source or "手动录入",
            "created_at": str(e.created_at) if e.created_at else None,
        } for e in entries]
    }


@router.get("/api/journal-entries/stats")
def journal_entry_stats(
    company_id: int = Query(...),
    period: Optional[str] = None,
    db: Session = Depends(get_db)
):
    base = db.query(JournalEntry).filter(JournalEntry.company_id == company_id)
    if period:
        base = base.filter(JournalEntry.period == period)
    total_count = base.count()
    total_debit = base.with_entities(func.sum(JournalEntry.debit_amount)).scalar() or 0
    total_credit = base.with_entities(func.sum(JournalEntry.credit_amount)).scalar() or 0
    reviewed_count = base.filter(JournalEntry.is_reviewed == True).count()
    unreviewed_count = base.filter(JournalEntry.is_reviewed == False).count()
    period_count = base.with_entities(func.count(func.distinct(JournalEntry.period))).scalar() or 0
    return {
        "total_count": total_count,
        "total_debit": round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "reviewed_count": reviewed_count,
        "unreviewed_count": unreviewed_count,
        "period_count": period_count,
    }



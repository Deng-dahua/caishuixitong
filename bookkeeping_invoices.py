"""
记账发票管理模块 - 从 main.py 自动拆分
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Form
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
import os, io, json, openpyxl, re as _re_module

from database import get_db

router = APIRouter(tags=["记账发票"])

class BookkeepingInvoiceCreate(BaseModel):
    invoice_code: Optional[str] = None
    invoice_no: Optional[str] = None
    digital_invoice_no: Optional[str] = None
    seller_tax_no: Optional[str] = None
    seller_name: Optional[str] = None
    buyer_tax_no: Optional[str] = None
    buyer_name: Optional[str] = None
    invoice_date: Optional[date] = None
    tax_category_code: Optional[str] = None
    specific_business_type: Optional[str] = None
    goods_name: Optional[str] = None
    spec: Optional[str] = None
    unit: Optional[str] = None
    quantity: Optional[float] = 0
    unit_price: Optional[float] = 0
    amount: float = 0.0
    tax_rate: Optional[float] = 0.0
    tax_amount: Optional[float] = 0.0
    total_amount: Optional[float] = 0.0
    invoice_source: Optional[str] = None
    invoice_category: str = "增值税普通发票"
    status: str = "正常"
    is_positive: Optional[bool] = True
    invoice_risk_level: Optional[str] = None
    issuer: Optional[str] = None
    remark: Optional[str] = None


class BookkeepingInvoiceUpdate(BaseModel):
    invoice_code: Optional[str] = None
    digital_invoice_no: Optional[str] = None
    seller_tax_no: Optional[str] = None
    seller_name: Optional[str] = None
    buyer_tax_no: Optional[str] = None
    buyer_name: Optional[str] = None
    invoice_date: Optional[date] = None
    tax_category_code: Optional[str] = None
    specific_business_type: Optional[str] = None
    goods_name: Optional[str] = None
    spec: Optional[str] = None
    unit: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    tax_rate: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    invoice_source: Optional[str] = None
    invoice_category: Optional[str] = None
    status: Optional[str] = None
    is_positive: Optional[bool] = None
    invoice_risk_level: Optional[str] = None
    issuer: Optional[str] = None
    remark: Optional[str] = None


@router.get("/api/bookkeeping-invoices")
def list_bookkeeping_invoices(
    company_id: int = Query(...),
    invoice_category: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    is_posted: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    q = db.query(BookkeepingInvoice).filter(BookkeepingInvoice.company_id == company_id)
    if invoice_category:
        q = q.filter(BookkeepingInvoice.invoice_category == invoice_category)
    if status:
        q = q.filter(BookkeepingInvoice.status == status)
    if date_from:
        q = q.filter(BookkeepingInvoice.invoice_date >= date_from)
    if date_to:
        q = q.filter(BookkeepingInvoice.invoice_date <= date_to)
    if is_posted is True:
        q = q.filter(BookkeepingInvoice.voucher_no.isnot(None))
    elif is_posted is False:
        q = q.filter(BookkeepingInvoice.voucher_no.is_(None))
    if keyword:
        q = q.filter(or_(
            BookkeepingInvoice.invoice_no.contains(keyword),
            BookkeepingInvoice.invoice_code.contains(keyword),
            BookkeepingInvoice.digital_invoice_no.contains(keyword),
            BookkeepingInvoice.seller_name.contains(keyword),
            BookkeepingInvoice.goods_name.contains(keyword)
        ))
    invoices = q.order_by(BookkeepingInvoice.invoice_date.desc()).offset(skip).limit(limit).all()
    t = q.count()
    return {
        "total": t,
        "items": [{
            "id": inv.id,
            "invoice_code": inv.invoice_code or "",
            "invoice_no": inv.invoice_no,
            "digital_invoice_no": inv.digital_invoice_no or "",
            "seller_tax_no": inv.seller_tax_no or "",
            "seller_name": inv.seller_name or "",
            "buyer_tax_no": inv.buyer_tax_no or "",
            "buyer_name": inv.buyer_name or "",
            "invoice_date": str(inv.invoice_date) if inv.invoice_date else "",
            "tax_category_code": inv.tax_category_code or "",
            "specific_business_type": inv.specific_business_type or "",
            "goods_name": inv.goods_name or "",
            "spec": inv.spec or "",
            "unit": inv.unit or "",
            "quantity": inv.quantity or 0,
            "unit_price": inv.unit_price or 0,
            "amount": inv.amount or 0,
            "tax_rate": inv.tax_rate or 0,
            "tax_amount": inv.tax_amount or 0,
            "total_amount": inv.total_amount or 0,
            "invoice_source": inv.invoice_source or "",
            "invoice_category": inv.invoice_category or "增值税普通发票",
            "status": inv.status,
            "is_positive": inv.is_positive if inv.is_positive is not None else True,
            "invoice_risk_level": inv.invoice_risk_level or "",
            "issuer": inv.issuer or "",
            "remark": inv.remark or "",
            "voucher_no": inv.voucher_no or "",
            "created_at": str(inv.created_at) if inv.created_at else ""
        } for inv in invoices]
    }


@router.post("/api/bookkeeping-invoices")
def create_bookkeeping_invoice(data: BookkeepingInvoiceCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    inv = BookkeepingInvoice(company_id=company_id, **data.model_dump())
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return {"id": inv.id, "invoice_no": inv.invoice_no, "message": "记账发票创建成功"}


@router.get("/api/bookkeeping-invoices/stats")
def bookkeeping_invoice_stats(company_id: int = Query(...), tab: str = Query("all"), is_posted: Optional[bool] = None, db: Session = Depends(get_db)):
    base = db.query(BookkeepingInvoice).filter(BookkeepingInvoice.company_id == company_id)
    if is_posted is True:
        base = base.filter(BookkeepingInvoice.voucher_no.isnot(None))
    elif is_posted is False:
        base = base.filter(BookkeepingInvoice.voucher_no.is_(None))
    if tab == "zpt":
        base = base.filter(BookkeepingInvoice.invoice_category.contains("专用发票"))
    elif tab == "ppt":
        base = base.filter(BookkeepingInvoice.invoice_category.contains("普通发票"))
    total_count = base.count()
    total_amt = base.with_entities(func.sum(func.coalesce(BookkeepingInvoice.amount, 0))).scalar() or 0
    total_amount = base.with_entities(func.sum(func.coalesce(BookkeepingInvoice.total_amount, 0))).scalar() or 0
    total_raw_tax = base.with_entities(func.sum(func.coalesce(BookkeepingInvoice.tax_amount, 0))).scalar() or 0
    normal_count = base.filter(BookkeepingInvoice.status == "正常").count()
    void_count = base.filter(BookkeepingInvoice.status.like("%作废%")).count()
    red_count = base.filter(BookkeepingInvoice.status.like("%红冲%")).count()
    return {
        "total_count": total_count, "total_amt": round(total_amt, 2),
        "total_amount": round(total_amount, 2),
        "total_raw_tax": round(total_raw_tax, 2),
        "normal_count": normal_count, "void_count": void_count,
        "red_count": red_count
    }


@router.get("/api/bookkeeping-invoices/{invoice_id}")
def get_bookkeeping_invoice(invoice_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    inv = db.query(BookkeepingInvoice).filter(BookkeepingInvoice.company_id == company_id, BookkeepingInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, detail="发票不存在")
    return {
        "id": inv.id,
        "invoice_code": inv.invoice_code or "",
        "invoice_no": inv.invoice_no,
        "digital_invoice_no": inv.digital_invoice_no or "",
        "seller_tax_no": inv.seller_tax_no or "",
        "seller_name": inv.seller_name or "",
        "buyer_tax_no": inv.buyer_tax_no or "",
        "buyer_name": inv.buyer_name or "",
        "invoice_date": str(inv.invoice_date) if inv.invoice_date else "",
        "tax_category_code": inv.tax_category_code or "",
        "specific_business_type": inv.specific_business_type or "",
        "goods_name": inv.goods_name or "",
        "spec": inv.spec or "",
        "unit": inv.unit or "",
        "quantity": inv.quantity or 0,
        "unit_price": inv.unit_price or 0,
        "amount": inv.amount or 0,
        "tax_rate": inv.tax_rate or 0,
        "tax_amount": inv.tax_amount or 0,
        "total_amount": inv.total_amount or 0,
        "invoice_source": inv.invoice_source or "",
        "invoice_category": inv.invoice_category or "增值税普通发票",
        "status": inv.status,
        "is_positive": inv.is_positive if inv.is_positive is not None else True,
        "invoice_risk_level": inv.invoice_risk_level or "",
        "issuer": inv.issuer or "",
        "remark": inv.remark or "",
        "created_at": str(inv.created_at) if inv.created_at else "",
        "updated_at": str(inv.updated_at) if inv.updated_at else ""
    }


@router.put("/api/bookkeeping-invoices/{invoice_id}")
def update_bookkeeping_invoice(invoice_id: int, data: BookkeepingInvoiceUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    inv = db.query(BookkeepingInvoice).filter(BookkeepingInvoice.company_id == company_id, BookkeepingInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, detail="发票不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(inv, k, v)
    inv.updated_at = datetime.now()
    db.commit()
    return {"message": "更新成功"}


@router.delete("/api/bookkeeping-invoices/{invoice_id}")
def delete_bookkeeping_invoice(invoice_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    inv = db.query(BookkeepingInvoice).filter(BookkeepingInvoice.company_id == company_id, BookkeepingInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, detail="发票不存在")
    db.delete(inv)
    db.commit()
    return {"message": "删除成功"}


@router.post("/api/bookkeeping-invoices/auto-voucher")
def bookkeeping_invoices_auto_voucher(company_id: int = Query(...), db: Session = Depends(get_db)):
    """未记账发票一键生成凭证"""
    count = auto_generate_bookkeeping_journal(db, company_id)
    db.commit()
    return {"message": f"自动生成 {count} 张未记账发票凭证", "generated": count}


@router.post("/api/bookkeeping-invoices/batch-delete")
def batch_delete_bookkeeping_invoices(ids: list[int], company_id: int = Query(...), only_unposted: bool = Query(False), db: Session = Depends(get_db)):
    """批量删除记账发票。only_unposted=True时仅删除未记账的（voucher_no为空）"""
    q = db.query(BookkeepingInvoice).filter(
        BookkeepingInvoice.company_id == company_id,
        BookkeepingInvoice.id.in_(ids)
    )
    if only_unposted:
        q = q.filter(or_(BookkeepingInvoice.voucher_no == None, BookkeepingInvoice.voucher_no == ""))
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return {"message": f"成功删除 {deleted} 条记录", "deleted": deleted}


@router.post("/api/bookkeeping-invoices/batch-generate-voucher")
def batch_generate_bookkeeping_voucher(ids: list[int], company_id: int = Query(...), period: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """批量生成记账发票凭证。period指定记账期间（YYYY-MM），为空则按发票日期自动分组"""
    invoices = db.query(BookkeepingInvoice).filter(
        BookkeepingInvoice.company_id == company_id,
        BookkeepingInvoice.id.in_(ids)
    ).all()
    if not invoices:
        raise HTTPException(400, "未找到匹配的发票")
    
    # 确定记账期间
    if period:
        # 统一记入指定期间
        period_groups = {period: invoices}
    else:
        # 按发票日期分组
        period_groups = {}
        for inv in invoices:
            if not inv.invoice_date:
                continue
            p = str(inv.invoice_date)[:7]
            period_groups.setdefault(p, []).append(inv)
    
    if not period_groups:
        raise HTTPException(400, "所选发票均无开票日期")
    
    posted_count = 0
    for period, invs in period_groups.items():
        # 在期间内按发票三号分组，每组一个凭证号
        key_groups = {}
        for inv in invs:
            key = (inv.invoice_code or "") + "|" + (inv.invoice_no or "") + "|" + (inv.digital_invoice_no or "")
            key_groups.setdefault(key, []).append(inv)
        voucher_no = _next_voucher_no(db, company_id, period, "记")
        for key, group in key_groups.items():
            for inv in group:
                # 借方：费用科目（根据品名智能分类）
                debit_account, debit_account_name = _classify_purchase_debit(db, company_id, inv)
                amount = float(inv.amount or 0)
                tax_amount = float(inv.tax_amount or 0)
                
                # 费用分录（借方）
                db.add(JournalEntry(
                    company_id=company_id, entry_date=inv.invoice_date, period=period,
                    voucher_word="记", voucher_no=voucher_no,
                    account_code=debit_account,
                    debit_amount=amount, credit_amount=0,
                    summary=f"{inv.invoice_date} {inv.seller_name or '供应商'} {inv.goods_name or '发票'} 入账"
                ))
                # 进项税额（专票才有）
                if inv.invoice_category and "专用发票" in inv.invoice_category and tax_amount > 0:
                    db.add(JournalEntry(
                        company_id=company_id, entry_date=inv.invoice_date, period=period,
                        voucher_word="记", voucher_no=voucher_no,
                        account_code="221001002",
                        debit_amount=tax_amount, credit_amount=0,
                        summary=f"{inv.invoice_date} {inv.seller_name or '供应商'} 进项税额"
                    ))
                # 应付账款（贷方）
                db.add(JournalEntry(
                    company_id=company_id, entry_date=inv.invoice_date, period=period,
                    voucher_word="记", voucher_no=voucher_no,
                    account_code="2202",
                    debit_amount=0, credit_amount=amount + (tax_amount if (inv.invoice_category and "专用发票" in inv.invoice_category) else 0),
                    summary=f"{inv.invoice_date} {inv.seller_name or '供应商'} {inv.goods_name or '发票'}"
                ))
                # 标记已记账
                inv.voucher_no = f"记-{voucher_no}"
                posted_count += 1
            voucher_no += 1
    
    # 记账后同步锁定取得发票（通过三号匹配，标记 skip_accounting）
    for inv in invoices:
        if inv.invoice_no or inv.invoice_code or inv.digital_invoice_no:
            db.query(PurchaseInvoice).filter(
                PurchaseInvoice.company_id == company_id,
                PurchaseInvoice.invoice_code == inv.invoice_code,
                PurchaseInvoice.invoice_no == inv.invoice_no,
                PurchaseInvoice.digital_invoice_no == inv.digital_invoice_no,
            ).update({"skip_accounting": True}, synchronize_session=False)
    
    db.commit()
    return {"message": f"成功生成凭证，{posted_count} 条发票已记账", "posted": posted_count}



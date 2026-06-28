"""
付款管理模块 - 从 main.py 自动拆分
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

from database import get_db, JournalEntry, SalesInvoice, PurchaseInvoice, InputVATDeduction, Payment, BookkeepingInvoice

router = APIRouter(tags=["付款"])

class PaymentCreate(BaseModel):
    payment_type: str = "外部单位"
    scenario: Optional[str] = None
    payment_no: str
    payment_date: date
    employee_id: Optional[int] = None
    employee_name: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    contract_id: Optional[int] = None
    contract_no: Optional[str] = None
    amount: float
    payment_method: str = "银行转账"
    payee: Optional[str] = None
    payee_account: Optional[str] = None
    payee_bank: Optional[str] = None
    department: Optional[str] = None
    purpose: Optional[str] = None
    remark: Optional[str] = None


class PaymentUpdate(BaseModel):
    payment_type: Optional[str] = None
    scenario: Optional[str] = None
    employee_id: Optional[int] = None
    employee_name: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    contract_id: Optional[int] = None
    contract_no: Optional[str] = None
    amount: Optional[float] = None
    payment_method: Optional[str] = None
    payee: Optional[str] = None
    payee_account: Optional[str] = None
    payee_bank: Optional[str] = None
    status: Optional[str] = None
    approved_by: Optional[str] = None
    department: Optional[str] = None
    purpose: Optional[str] = None
    remark: Optional[str] = None


@router.get("/api/payments")
def list_payments(
    company_id: int = Query(...),
    payment_type: Optional[str] = None,
    status: Optional[str] = None,
    supplier_id: Optional[int] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(Payment).filter(Payment.company_id == company_id)
    if payment_type:
        q = q.filter(Payment.payment_type == payment_type)
    if status:
        q = q.filter(Payment.status == status)
    if supplier_id:
        q = q.filter(Payment.supplier_id == supplier_id)
    if keyword:
        q = q.filter(or_(
            Payment.payment_no.contains(keyword),
            Payment.supplier_name.contains(keyword),
            Payment.employee_name.contains(keyword),
            Payment.payee.contains(keyword),
            Payment.purpose.contains(keyword)
        ))
    payments = q.order_by(Payment.payment_date.desc()).all()
    return [{
        "id": p.id, "payment_type": p.payment_type, "scenario": p.scenario or "",
        "payment_no": p.payment_no,
        "payment_date": str(p.payment_date) if p.payment_date else "",
        "employee_id": p.employee_id, "employee_name": p.employee_name or "",
        "supplier_id": p.supplier_id, "supplier_name": p.supplier_name or "",
        "contract_id": p.contract_id, "contract_no": p.contract_no or "",
        "amount": p.amount, "payment_method": p.payment_method,
        "payee": p.payee or "", "payee_account": p.payee_account or "",
        "payee_bank": p.payee_bank or "", "status": p.status,
        "approved_by": p.approved_by or "",
        "approved_at": str(p.approved_at) if p.approved_at else "",
        "paid_at": str(p.paid_at) if p.paid_at else "",
        "department": p.department or "", "purpose": p.purpose or "",
        "remark": p.remark or "",
        "created_at": str(p.created_at) if p.created_at else ""
    } for p in payments]


@router.post("/api/payments")
def create_payment(data: PaymentCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    payment = Payment(company_id=company_id, **data.model_dump())
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {"id": payment.id, "payment_no": payment.payment_no, "message": "付款单创建成功"}


@router.get("/api/payments/stats")
def payment_stats(company_id: int = Query(...), db: Session = Depends(get_db)):
    """付款统计"""
    base = db.query(Payment).filter(Payment.company_id == company_id)
    total_count = base.count()
    total_amount = base.with_entities(func.sum(Payment.amount)).scalar() or 0
    
    # 按类型统计
    internal_base = base.filter(Payment.payment_type == "内部人员")
    internal_count = internal_base.count()
    internal_amount = internal_base.with_entities(func.sum(Payment.amount)).scalar() or 0
    
    external_base = base.filter(Payment.payment_type == "外部单位")
    external_count = external_base.count()
    external_amount = external_base.with_entities(func.sum(Payment.amount)).scalar() or 0
    
    pending_count = base.filter(Payment.status == "待审批").count()
    pending_amount = base.filter(Payment.status == "待审批").with_entities(func.sum(Payment.amount)).scalar() or 0
    approved_count = base.filter(Payment.status == "已审批").count()
    paid_count = base.filter(Payment.status == "已付款").count()
    paid_amount = base.filter(Payment.status == "已付款").with_entities(func.sum(Payment.amount)).scalar() or 0
    return {
        "total_count": total_count, "total_amount": total_amount,
        "internal_count": internal_count, "internal_amount": internal_amount,
        "external_count": external_count, "external_amount": external_amount,
        "pending_count": pending_count, "pending_amount": pending_amount,
        "approved_count": approved_count, "paid_count": paid_count,
        "paid_amount": paid_amount
    }


@router.put("/api/payments/{payment_id}")
def update_payment(payment_id: int, data: PaymentUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    p = db.query(Payment).filter(Payment.company_id == company_id, Payment.id == payment_id).first()
    if not p:
        raise HTTPException(404, detail="付款单不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    p.updated_at = datetime.now()
    # 如果状态改为"已付款"，记录付款时间
    if data.status == "已付款":
        p.paid_at = datetime.now()
    db.commit()
    return {"message": "更新成功"}


@router.delete("/api/payments/{payment_id}")
def delete_payment(payment_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    p = db.query(Payment).filter(Payment.company_id == company_id, Payment.id == payment_id).first()
    if not p:
        raise HTTPException(404, detail="付款单不存在")
    if p.status in ("已审批", "已付款"):
        raise HTTPException(400, detail=f"付款单状态为'{p.status}'，不能删除")
    db.delete(p)
    db.commit()
    return {"message": "删除成功"}


# ==================== 开具发票（销售发票）====================

class SalesInvoiceCreate(BaseModel):
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
    invoice_category: str = "增值税专用发票"
    status: str = "正常"
    is_positive: Optional[bool] = True
    invoice_risk_level: Optional[str] = None
    issuer: Optional[str] = None
    remark: Optional[str] = None


class SalesInvoiceUpdate(BaseModel):
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


@router.get("/api/sales-invoices")
def list_sales_invoices(
    company_id: int = Query(...),
    invoice_category: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    q = db.query(SalesInvoice).filter(SalesInvoice.company_id == company_id)
    if invoice_category:
        q = q.filter(SalesInvoice.invoice_category == invoice_category)
    if status:
        q = q.filter(SalesInvoice.status == status)
    if date_from:
        q = q.filter(SalesInvoice.invoice_date >= date_from)
    if date_to:
        q = q.filter(SalesInvoice.invoice_date <= date_to)
    if keyword:
        q = q.filter(or_(
            SalesInvoice.invoice_no.contains(keyword),
            SalesInvoice.invoice_code.contains(keyword),
            SalesInvoice.digital_invoice_no.contains(keyword),
            SalesInvoice.buyer_name.contains(keyword),
            SalesInvoice.goods_name.contains(keyword)
        ))
    invoices = q.order_by(SalesInvoice.invoice_date.desc()).offset(skip).limit(limit).all()
    # 构建凭证号映射（销项发票 → 序时账，通过摘要+借方金额+科目1122判重）
    voucher_map = {}
    for inv in invoices:
        buyer = inv.buyer_name or "客户"
        goods = inv.goods_name or ""
        summary = f"销售{goods or '货物'}给{buyer}"
        je = db.query(JournalEntry).filter(
            JournalEntry.company_id == company_id,
            JournalEntry.summary == summary,
            JournalEntry.debit_amount == inv.total_amount,
            JournalEntry.account_code == "1122"
        ).first()
        if je:
            voucher_map[inv.id] = f"{je.voucher_word}-{je.voucher_no}"
    return [{
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
        "invoice_category": inv.invoice_category or "增值税专用发票",
        "status": inv.status,
        "is_positive": inv.is_positive if inv.is_positive is not None else True,
        "invoice_risk_level": inv.invoice_risk_level or "",
        "issuer": inv.issuer or "",
        "remark": inv.remark or "",
        "journal_voucher_no": voucher_map.get(inv.id, ""),
        "created_at": str(inv.created_at) if inv.created_at else ""
    } for inv in invoices]


@router.post("/api/sales-invoices")
def create_sales_invoice(data: SalesInvoiceCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    # ── 按票号唯一去重 ──
    digital_no = (data.digital_invoice_no or "").strip()
    inv_code = (data.invoice_code or "").strip()
    inv_no = (data.invoice_no or "").strip()

    if digital_no:
        existing = db.query(SalesInvoice).filter(
            SalesInvoice.company_id == company_id,
            SalesInvoice.digital_invoice_no == digital_no
        ).first()
        if existing:
            raise HTTPException(400, detail=f"数电发票 {digital_no} 已存在，请勿重复录入")
    elif inv_no:
        q = db.query(SalesInvoice).filter(
            SalesInvoice.company_id == company_id,
            SalesInvoice.invoice_no == inv_no
        )
        if inv_code:
            q = q.filter(SalesInvoice.invoice_code == inv_code)
        existing = q.first()
        if existing:
            raise HTTPException(400, detail=f"发票 {inv_code}+{inv_no} 已存在，请勿重复录入")

    # 全行指纹去重
    fp_values = (
        str(company_id),
        str(data.invoice_no or ""),
        str(data.invoice_code or ""),
        str(data.digital_invoice_no or ""),
        str(data.seller_tax_no or ""),
        str(data.seller_name or ""),
        str(data.buyer_tax_no or ""),
        str(data.buyer_name or ""),
        str(data.invoice_date) if data.invoice_date else "",
        str(data.tax_category_code or ""),
        str(data.specific_business_type or ""),
        str(data.goods_name or ""),
        str(data.spec or ""),
        str(data.unit or ""),
        str(data.quantity),
        str(data.unit_price),
        str(data.amount),
        str(data.tax_rate),
        str(data.tax_amount),
        str(data.total_amount),
        str(data.invoice_source or ""),
        str(data.invoice_category or ""),
        str(data.status or ""),
        str(data.is_positive),
        str(data.invoice_risk_level or ""),
        str(data.issuer or ""),
        str(data.remark or ""),
    )
    fp_raw = "|".join(fp_values)
    fp = hashlib.sha256(fp_raw.encode("utf-8")).hexdigest()
    existing = db.query(SalesInvoice).filter(
        SalesInvoice.company_id == company_id,
        SalesInvoice._fingerprint == fp
    ).first()
    if existing:
        raise HTTPException(400, detail="该发票数据已存在（全行比对重复），请勿重复录入")
    inv = SalesInvoice(
        company_id=company_id,
        _fingerprint=fp,
        **data.model_dump()
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return {"id": inv.id, "invoice_no": inv.invoice_no, "message": "开具发票创建成功"}


@router.get("/api/sales-invoices/stats")
def sales_invoice_stats(company_id: int = Query(...), status: str = Query(None), db: Session = Depends(get_db)):
    base = db.query(SalesInvoice).filter(SalesInvoice.company_id == company_id)
    if status:
        base = base.filter(SalesInvoice.status.like(f"%{status}%"))
    total_count = base.count()
    total_amt = base.with_entities(func.sum(func.coalesce(SalesInvoice.amount, 0))).scalar() or 0
    total_amount = base.with_entities(func.sum(func.coalesce(SalesInvoice.total_amount, 0))).scalar() or 0
    total_tax = base.with_entities(func.sum(func.coalesce(SalesInvoice.tax_amount, 0))).scalar() or 0
    normal_count = base.filter(SalesInvoice.status == "正常").count() if not status else 0
    void_count = base.filter(SalesInvoice.status.like("%作废%")).count() if not status else 0
    red_count = base.filter(SalesInvoice.status.like("%红冲%")).count() if not status else 0
    return {
        "total_count": total_count, "total_amt": round(total_amt, 2),
        "total_amount": round(total_amount, 2),
        "total_tax": round(total_tax, 2),
        "normal_count": normal_count, "void_count": void_count,
        "red_count": red_count
    }


@router.get("/api/sales-invoices/{invoice_id}")
def get_sales_invoice(invoice_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    inv = db.query(SalesInvoice).filter(SalesInvoice.company_id == company_id, SalesInvoice.id == invoice_id).first()
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
        "invoice_category": inv.invoice_category or "增值税专用发票",
        "status": inv.status,
        "is_positive": inv.is_positive if inv.is_positive is not None else True,
        "invoice_risk_level": inv.invoice_risk_level or "",
        "issuer": inv.issuer or "",
        "remark": inv.remark or "",
        "created_at": str(inv.created_at) if inv.created_at else "",
        "updated_at": str(inv.updated_at) if inv.updated_at else ""
    }


@router.put("/api/sales-invoices/{invoice_id}")
def update_sales_invoice(invoice_id: int, data: SalesInvoiceUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    inv = db.query(SalesInvoice).filter(SalesInvoice.company_id == company_id, SalesInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, detail="发票不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(inv, k, v)
    inv.updated_at = datetime.now()
    # 重新计算全行指纹
    fp_values = (
        str(company_id),
        str(inv.invoice_no or ""),
        str(inv.invoice_code or ""),
        str(inv.digital_invoice_no or ""),
        str(inv.seller_tax_no or ""),
        str(inv.seller_name or ""),
        str(inv.buyer_tax_no or ""),
        str(inv.buyer_name or ""),
        str(inv.invoice_date) if inv.invoice_date else "",
        str(inv.tax_category_code or ""),
        str(inv.specific_business_type or ""),
        str(inv.goods_name or ""),
        str(inv.spec or ""),
        str(inv.unit or ""),
        str(inv.quantity or 0),
        str(inv.unit_price or 0),
        str(inv.amount or 0),
        str(inv.tax_rate or 0),
        str(inv.tax_amount or 0),
        str(inv.total_amount or 0),
        str(inv.invoice_source or ""),
        str(inv.invoice_category or ""),
        str(inv.status or ""),
        str(inv.is_positive if inv.is_positive is not None else True),
        str(inv.invoice_risk_level or ""),
        str(inv.issuer or ""),
        str(inv.remark or ""),
    )
    fp_raw = "|".join(fp_values)
    fp = hashlib.sha256(fp_raw.encode("utf-8")).hexdigest()
    inv._fingerprint = fp
    db.commit()
    db.refresh(inv)
    return {"message": "更新成功"}


@router.delete("/api/sales-invoices/{invoice_id}")
def delete_sales_invoice(invoice_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    inv = db.query(SalesInvoice).filter(SalesInvoice.company_id == company_id, SalesInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, detail="发票不存在")
    db.delete(inv)
    db.commit()
    return {"message": "删除成功"}


@router.post("/api/sales-invoices/batch-delete")
def batch_delete_sales_invoices(ids: list[int], company_id: int = Query(...), db: Session = Depends(get_db)):
    deleted = db.query(SalesInvoice).filter(
        SalesInvoice.company_id == company_id,
        SalesInvoice.id.in_(ids)
    ).delete(synchronize_session=False)
    db.commit()
    return {"message": f"成功删除 {deleted} 条记录", "deleted": deleted}


# ==================== 取得发票（采购发票）====================

class PurchaseInvoiceCreate(BaseModel):
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
    invoice_category: str = "增值税专用发票"
    status: str = "正常"
    is_positive: Optional[bool] = True
    invoice_risk_level: Optional[str] = None
    issuer: Optional[str] = None
    remark: Optional[str] = None


class PurchaseInvoiceUpdate(BaseModel):
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
@router.get("/api/purchase-invoices")
def list_purchase_invoices(
    company_id: int = Query(...),
    invoice_category: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    q = db.query(PurchaseInvoice).filter(PurchaseInvoice.company_id == company_id)
    if invoice_category:
        q = q.filter(PurchaseInvoice.invoice_category == invoice_category)
    if status:
        q = q.filter(PurchaseInvoice.status == status)
    if date_from:
        q = q.filter(PurchaseInvoice.invoice_date >= date_from)
    if date_to:
        q = q.filter(PurchaseInvoice.invoice_date <= date_to)
    if keyword:
        q = q.filter(or_(
            PurchaseInvoice.invoice_no.contains(keyword),
            PurchaseInvoice.invoice_code.contains(keyword),
            PurchaseInvoice.digital_invoice_no.contains(keyword),
            PurchaseInvoice.seller_name.contains(keyword),
            PurchaseInvoice.goods_name.contains(keyword)
        ))
    invoices = q.order_by(PurchaseInvoice.invoice_date.desc()).offset(skip).limit(limit).all()
    # 构建凭证号映射（取得发票 → 序时账，通过 ref_id 精确匹配）
    voucher_map = {}
    if invoices:
        inv_ids = [inv.id for inv in invoices]
        entries = db.query(JournalEntry).filter(
            JournalEntry.company_id == company_id,
            JournalEntry.source == "未记账发票",
            JournalEntry.ref_id.in_(inv_ids)
        ).all()
        for je in entries:
            if je.ref_id not in voucher_map:
                voucher_map[je.ref_id] = f"{je.voucher_word}-{je.voucher_no}"
    return [{
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
        "invoice_category": inv.invoice_category or "增值税专用发票",
        "status": inv.status,
        "is_positive": inv.is_positive if inv.is_positive is not None else True,
        "invoice_risk_level": inv.invoice_risk_level or "",
        "issuer": inv.issuer or "",
        "remark": inv.remark or "",
        "journal_voucher_no": voucher_map.get(inv.id, ""),
        "skip_accounting": bool(inv.skip_accounting) if inv.skip_accounting is not None else False,
        "created_at": str(inv.created_at) if inv.created_at else ""
    } for inv in invoices]


@router.post("/api/purchase-invoices")
def create_purchase_invoice(data: PurchaseInvoiceCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    # ── 取得发票全指纹去重 ──
    import hashlib
    fp_values = (
        str(company_id), str(data.invoice_no or ""), str(data.invoice_code or ""),
        str(data.digital_invoice_no or ""),
        str(data.seller_tax_no or ""), str(data.seller_name or ""),
        str(data.buyer_tax_no or ""), str(data.buyer_name or ""),
        str(data.invoice_date) if data.invoice_date else "",
        str(data.tax_category_code or ""), str(data.specific_business_type or ""),
        str(data.goods_name or ""), str(data.spec or ""),
        str(data.unit or ""), str(data.quantity or 0), str(data.unit_price or 0),
        str(data.amount or 0), str(data.tax_rate or 0), str(data.tax_amount or 0), str(data.total_amount or 0),
        str(data.invoice_source or ""),
        str(data.invoice_category or "增值税专用发票"),
        str(data.status or "正常"),
        str("是" if data.is_positive else "否"),
        str(data.invoice_risk_level or ""),
        str(data.issuer or ""),
        str(data.remark or ""),
    )
    fp_raw = "|".join(fp_values)
    pi_fp = hashlib.sha256(fp_raw.encode("utf-8")).hexdigest()
    existing = db.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice._fingerprint == pi_fp
    ).first()
    if existing:
        raise HTTPException(400, detail="全指纹重复，发票已存在，请勿重复录入")
    inv = PurchaseInvoice(company_id=company_id, _fingerprint=pi_fp, **data.model_dump())
    db.add(inv)
    db.flush()
    db.commit()
    db.refresh(inv)
    return {"id": inv.id, "invoice_no": inv.invoice_no, "message": "取得发票创建成功"}


@router.get("/api/purchase-invoices/stats")
def purchase_invoice_stats(company_id: int = Query(...), tab: str = Query("all"), db: Session = Depends(get_db)):
    base = db.query(PurchaseInvoice).filter(PurchaseInvoice.company_id == company_id)
    # 按票种筛选
    if tab == "zpt":
        base = base.filter(PurchaseInvoice.invoice_category.contains("专用发票"))
    elif tab == "ppt":
        base = base.filter(PurchaseInvoice.invoice_category.contains("普通发票"))
    elif tab == "tlp":
        base = base.filter(PurchaseInvoice.invoice_category.contains("铁路"))
    total_count = base.count()
    total_amt = base.with_entities(func.sum(func.coalesce(PurchaseInvoice.amount, 0))).scalar() or 0
    total_amount = base.with_entities(func.sum(func.coalesce(PurchaseInvoice.total_amount, 0))).scalar() or 0
    total_raw_tax = base.with_entities(func.sum(func.coalesce(PurchaseInvoice.tax_amount, 0))).scalar() or 0
    # 可抵扣税额：专票/铁路票 = 税额合计，普票 = 0
    if tab == "ppt":
        total_tax = 0.0
    else:
        deduct_q = db.query(PurchaseInvoice).filter(
            PurchaseInvoice.company_id == company_id,
            PurchaseInvoice.tax_amount != 0,  # 含红字发票（负税额应扣减）
        )
        if tab == "zpt":
            deduct_q = deduct_q.filter(PurchaseInvoice.invoice_category.contains("专用发票"))
        elif tab == "tlp":
            deduct_q = deduct_q.filter(PurchaseInvoice.invoice_category.contains("铁路"))
        else:  # all：专票 + 铁路票
            deduct_q = deduct_q.filter(
                or_(PurchaseInvoice.invoice_category.contains("专用发票"),
                     PurchaseInvoice.invoice_category.contains("铁路")))
        total_tax = round(deduct_q.with_entities(func.sum(func.coalesce(PurchaseInvoice.tax_amount, 0))).scalar() or 0, 2)
    normal_count = base.filter(PurchaseInvoice.status == "正常").count()
    void_count = base.filter(PurchaseInvoice.status.like("%作废%")).count()
    red_count = base.filter(PurchaseInvoice.status.like("%红冲%")).count()
    return {
        "total_count": total_count, "total_amt": round(total_amt, 2),
        "total_amount": round(total_amount, 2),
        "total_raw_tax": round(total_raw_tax, 2),
        "normal_count": normal_count, "void_count": void_count,
        "red_count": red_count,
    }


@router.get("/api/purchase-invoices/{invoice_id}")
def get_purchase_invoice(invoice_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    inv = db.query(PurchaseInvoice).filter(PurchaseInvoice.company_id == company_id, PurchaseInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, detail="发票不存在")
    # 查询凭证号
    voucher_no = ""
    je = db.query(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.source == "取得发票",
        JournalEntry.ref_id == inv.id
    ).first()
    if je:
        voucher_no = f"{je.voucher_word}-{je.voucher_no}"
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
        "invoice_category": inv.invoice_category or "增值税专用发票",
        "status": inv.status,
        "is_positive": inv.is_positive if inv.is_positive is not None else True,
        "invoice_risk_level": inv.invoice_risk_level or "",
        "issuer": inv.issuer or "",
        "remark": inv.remark or "",
        "journal_voucher_no": voucher_no,
        "skip_accounting": bool(inv.skip_accounting) if inv.skip_accounting is not None else False,
        "created_at": str(inv.created_at) if inv.created_at else "",
        "updated_at": str(inv.updated_at) if inv.updated_at else ""
    }


def _sync_pi_update_to_bi(db, company_id, pi):
    """编辑取得发票后同步到未记账凭证（按三号匹配更新）"""
    bis = db.query(BookkeepingInvoice).filter(
        BookkeepingInvoice.company_id == company_id,
        BookkeepingInvoice.invoice_code == pi.invoice_code,
        BookkeepingInvoice.invoice_no == pi.invoice_no,
        BookkeepingInvoice.digital_invoice_no == pi.digital_invoice_no,
    ).all()
    for bi in bis:
        bi.invoice_date = pi.invoice_date
        bi.seller_tax_no = pi.seller_tax_no
        bi.seller_name = pi.seller_name
        bi.buyer_tax_no = pi.buyer_tax_no
        bi.buyer_name = pi.buyer_name
        bi.tax_category_code = pi.tax_category_code
        bi.specific_business_type = pi.specific_business_type
        bi.goods_name = pi.goods_name
        bi.spec = pi.spec
        bi.unit = pi.unit
        bi.quantity = pi.quantity
        bi.unit_price = pi.unit_price
        bi.amount = pi.amount
        bi.tax_rate = pi.tax_rate
        bi.tax_amount = pi.tax_amount
        bi.total_amount = pi.total_amount
        bi.invoice_source = pi.invoice_source
        bi.invoice_category = pi.invoice_category
        bi.status = pi.status
        bi.is_positive = pi.is_positive
        bi.invoice_risk_level = pi.invoice_risk_level
        bi.issuer = pi.issuer
        bi.remark = pi.remark

def _sync_pi_delete_to_bi(db, company_id, pi):
    """删除取得发票后同步删除未记账凭证（按三号匹配，仅删未记账的）
    注意：三号可能为 None/空字符串，需用 IS NULL 处理，因为 SQL 中 NULL != NULL"""
    conditions = [BookkeepingInvoice.company_id == company_id]
    # 三号：按实际值匹配，NULL/空字符串用 IS NULL
    for bi_field, pi_val in [
        (BookkeepingInvoice.invoice_code, pi.invoice_code),
        (BookkeepingInvoice.invoice_no, pi.invoice_no),
        (BookkeepingInvoice.digital_invoice_no, pi.digital_invoice_no),
    ]:
        if pi_val and pi_val.strip():
            conditions.append(bi_field == pi_val)
        else:
            conditions.append(or_(bi_field.is_(None), bi_field == ""))
    # 仅删未记账的
    conditions.append(or_(BookkeepingInvoice.voucher_no.is_(None), BookkeepingInvoice.voucher_no == ""))
    db.query(BookkeepingInvoice).filter(and_(*conditions)).delete(synchronize_session=False)


@router.put("/api/purchase-invoices/{invoice_id}")
def update_purchase_invoice(invoice_id: int, data: PurchaseInvoiceUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    inv = db.query(PurchaseInvoice).filter(PurchaseInvoice.company_id == company_id, PurchaseInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, detail="发票不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(inv, k, v)
    inv.updated_at = datetime.now()
    db.flush()
    # 同步到未记账凭证（按三号匹配）
    _sync_pi_update_to_bi(db, company_id, inv)
    db.commit()
    return {"message": "更新成功"}


@router.delete("/api/purchase-invoices/{invoice_id}")
def delete_purchase_invoice(invoice_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    inv = db.query(PurchaseInvoice).filter(PurchaseInvoice.company_id == company_id, PurchaseInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, detail="发票不存在")
    # 同步删除到未记账凭证
    _sync_pi_delete_to_bi(db, company_id, inv)
    db.delete(inv)
    db.commit()
    return {"message": "删除成功"}


@router.post("/api/purchase-invoices/batch-delete")
def batch_delete_purchase_invoices(ids: list[int], company_id: int = Query(...), db: Session = Depends(get_db)):
    invoices = db.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.id.in_(ids)
    ).all()
    # 同步删除到未记账凭证
    for inv in invoices:
        _sync_pi_delete_to_bi(db, company_id, inv)
    db.flush()
    deleted = db.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.id.in_(ids)
    ).delete(synchronize_session=False)
    db.commit()
    return {"message": f"成功删除 {deleted} 条记录", "deleted": deleted}


@router.post("/api/purchase-invoices/transfer-to-bookkeeping")
def transfer_purchase_to_bookkeeping(ids: list[int], company_id: int = Query(...), db: Session = Depends(get_db)):
    """取得发票 → 转入记账发票（同时生成凭证入账）"""
    invoices = db.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.id.in_(ids)
    ).all()
    if not invoices:
        raise HTTPException(400, "未找到匹配的发票")
    period_groups = {}
    for inv in invoices:
        if not inv.invoice_date: continue
        p = str(inv.invoice_date)[:7]
        period_groups.setdefault(p, []).append(inv)
    if not period_groups:
        raise HTTPException(400, "所选发票均无开票日期")
    transferred = 0
    for period, invs in period_groups.items():
        vno = _next_voucher_no(db, company_id, period, "记")
        for inv in invs:
            bi = BookkeepingInvoice(
                company_id=company_id,
                invoice_code=inv.invoice_code, invoice_no=inv.invoice_no,
                digital_invoice_no=inv.digital_invoice_no,
                seller_tax_no=inv.seller_tax_no, seller_name=inv.seller_name,
                buyer_tax_no=inv.buyer_tax_no, buyer_name=inv.buyer_name,
                invoice_date=inv.invoice_date,
                tax_category_code=inv.tax_category_code,
                specific_business_type=inv.specific_business_type,
                goods_name=inv.goods_name, spec=inv.spec, unit=inv.unit,
                quantity=inv.quantity, unit_price=inv.unit_price,
                amount=inv.amount, tax_rate=inv.tax_rate, tax_amount=inv.tax_amount,
                total_amount=inv.total_amount,
                invoice_source=inv.invoice_source, invoice_category=inv.invoice_category,
                status=inv.status, is_positive=inv.is_positive,
                invoice_risk_level=inv.invoice_risk_level,
                issuer=inv.issuer, remark=inv.remark,
                voucher_no=f"记-{vno}"
            )
            db.add(bi); db.flush()
            debit_account, _ = _classify_purchase_debit(db, company_id, inv)
            amt = float(inv.amount or 0); tax = float(inv.tax_amount or 0)
            is_special = inv.invoice_category and "专用发票" in str(inv.invoice_category)
            db.add(JournalEntry(company_id=company_id, entry_date=inv.invoice_date, period=period, voucher_word="记", voucher_no=vno,
                account_code=debit_account, debit_amount=amt, credit_amount=0,
                summary=f"{inv.invoice_date} {inv.seller_name or ''} {inv.goods_name or '发票'} 入账"))
            if is_special and tax > 0:
                db.add(JournalEntry(company_id=company_id, entry_date=inv.invoice_date, period=period, voucher_word="记", voucher_no=vno,
                    account_code="221001002", debit_amount=tax, credit_amount=0,
                    summary=f"{inv.invoice_date} {inv.seller_name or ''} 进项税额"))
            db.add(JournalEntry(company_id=company_id, entry_date=inv.invoice_date, period=period, voucher_word="记", voucher_no=vno,
                account_code="2202", debit_amount=0, credit_amount=amt + (tax if is_special else 0),
                summary=f"{inv.invoice_date} {inv.seller_name or ''} {inv.goods_name or '发票'}"))
            transferred += 1
        vno += 1
    for inv in invoices: db.delete(inv)
    db.commit()
    return {"message": f"成功转入 {transferred} 条发票到记账发票并生成凭证", "transferred": transferred}


@router.post("/api/purchase-invoices/transfer-to-unbookkept")
def transfer_purchase_to_unbookkept(ids: list[int], company_id: int = Query(...), db: Session = Depends(get_db)):
    """取得发票 → 转入未记账发票（不生成凭证，voucher_no为空）"""
    invoices = db.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.id.in_(ids)
    ).all()
    if not invoices:
        raise HTTPException(400, "未找到匹配的发票")
    transferred = 0
    for inv in invoices:
        db.add(BookkeepingInvoice(
            company_id=company_id,
            invoice_code=inv.invoice_code, invoice_no=inv.invoice_no,
            digital_invoice_no=inv.digital_invoice_no,
            seller_tax_no=inv.seller_tax_no, seller_name=inv.seller_name,
            buyer_tax_no=inv.buyer_tax_no, buyer_name=inv.buyer_name,
            invoice_date=inv.invoice_date,
            tax_category_code=inv.tax_category_code,
            specific_business_type=inv.specific_business_type,
            goods_name=inv.goods_name, spec=inv.spec, unit=inv.unit,
            quantity=inv.quantity, unit_price=inv.unit_price,
            amount=inv.amount, tax_rate=inv.tax_rate, tax_amount=inv.tax_amount,
            total_amount=inv.total_amount,
            invoice_source=inv.invoice_source, invoice_category=inv.invoice_category,
            status=inv.status, is_positive=inv.is_positive,
            invoice_risk_level=inv.invoice_risk_level,
            issuer=inv.issuer, remark=inv.remark,
        ))
        db.delete(inv)
        transferred += 1
    db.commit()
    return {"message": f"成功转入 {transferred} 条发票到未记账发票", "transferred": transferred}


@router.post("/api/purchase-invoices/sync-to-unbookkept")
def sync_purchase_to_unbookkept(company_id: int = Query(...), db: Session = Depends(get_db)):
    """同步：取得发票 → 未记账发票（逐条创建BookkeepingInvoice，不去重）"""
    all_pi = db.query(PurchaseInvoice).filter(PurchaseInvoice.company_id == company_id).all()
    if not all_pi:
        return {"message": "无待同步发票", "synced": 0}
    
    synced = 0
    for inv in all_pi:
        db.add(BookkeepingInvoice(
            company_id=company_id,
            invoice_code=inv.invoice_code, invoice_no=inv.invoice_no,
            digital_invoice_no=inv.digital_invoice_no,
            seller_tax_no=inv.seller_tax_no, seller_name=inv.seller_name,
            buyer_tax_no=inv.buyer_tax_no, buyer_name=inv.buyer_name,
            invoice_date=inv.invoice_date,
            tax_category_code=inv.tax_category_code,
            specific_business_type=inv.specific_business_type,
            goods_name=inv.goods_name, spec=inv.spec, unit=inv.unit,
            quantity=inv.quantity, unit_price=inv.unit_price,
            amount=inv.amount, tax_rate=inv.tax_rate, tax_amount=inv.tax_amount,
            total_amount=inv.total_amount,
            invoice_source=inv.invoice_source, invoice_category=inv.invoice_category,
            status=inv.status, is_positive=inv.is_positive,
            invoice_risk_level=inv.invoice_risk_level,
            issuer=inv.issuer, remark=inv.remark,
        ))
        synced += 1
    
    db.commit()
    return {"message": f"成功同步 {synced} 条发票到未记账发票", "synced": synced}


@router.post("/api/purchase-invoices/generate-voucher-only")
def purchase_invoice_generate_voucher_only(body: dict, company_id: int = Query(...), db: Session = Depends(get_db)):
    """取得发票 → 仅生成序时账凭证（不入进项认证模块）"""
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(400, "请提供发票ID列表")
    invoices = db.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.id.in_(ids)
    ).all()
    if not invoices:
        raise HTTPException(400, "未找到匹配的发票")
    
    # 按期分组
    period_groups = {}
    for inv in invoices:
        if not inv.invoice_date: continue
        p = str(inv.invoice_date)[:7]
        period_groups.setdefault(p, []).append(inv)
    if not period_groups:
        raise HTTPException(400, "所选发票均无开票日期")
    
    count = 0
    for period, invs in period_groups.items():
        vno = _next_voucher_no(db, company_id, period, "记")
        for inv in invs:
            debit_account, _ = _classify_purchase_debit(db, company_id, inv)
            amt = float(inv.amount or 0); tax = float(inv.tax_amount or 0)
            is_special = inv.invoice_category and "专用发票" in str(inv.invoice_category)
            # 费用/成本（借方）
            db.add(JournalEntry(company_id=company_id, entry_date=inv.invoice_date, period=period, voucher_word="记", voucher_no=vno,
                account_code=debit_account, debit_amount=amt, credit_amount=0,
                summary=f"{inv.invoice_date} {inv.seller_name or ''} {inv.goods_name or '发票'}"))
            # 进项税额（专票）
            if is_special and tax > 0:
                db.add(JournalEntry(company_id=company_id, entry_date=inv.invoice_date, period=period, voucher_word="记", voucher_no=vno,
                    account_code="221001002", debit_amount=tax, credit_amount=0,
                    summary=f"{inv.invoice_date} {inv.seller_name or ''} 进项税额"))
            # 应付账款（贷方）
            db.add(JournalEntry(company_id=company_id, entry_date=inv.invoice_date, period=period, voucher_word="记", voucher_no=vno,
                account_code="2202", debit_amount=0, credit_amount=amt + (tax if is_special else 0),
                summary=f"{inv.invoice_date} {inv.seller_name or ''} {inv.goods_name or '发票'}"))
            count += 1
        vno += 1
    db.commit()
    return {"message": f"成功生成 {count} 张凭证（不入进项认证）", "count": count}


@router.post("/api/purchase-invoices/{invoice_id}/to-journal")
def purchase_invoice_to_journal(invoice_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    """将单张取得发票生成进项抵扣记录并生成凭证"""
    inv = db.query(PurchaseInvoice).filter(
        PurchaseInvoice.id == invoice_id,
        PurchaseInvoice.company_id == company_id
    ).first()
    if not inv:
        raise HTTPException(404, "发票不存在")

    period = inv.invoice_date.strftime("%Y-%m") if inv.invoice_date else datetime.now().strftime("%Y-%m")

    # 查找或创建进项抵扣记录
    ded = db.query(InputVATDeduction).filter(
        InputVATDeduction.company_id == company_id,
        InputVATDeduction.invoice_no == inv.invoice_no
    ).first()

    if not ded:
        ded = InputVATDeduction(
            company_id=company_id,
            purchase_invoice_id=inv.id,
            invoice_code=inv.invoice_code or "",
            invoice_no=inv.invoice_no or "",
            invoice_date=inv.invoice_date,
            seller_name=inv.seller_name or "",
            seller_tax_id=inv.seller_tax_no or "",
            amount=inv.amount or 0,
            tax_amount=inv.tax_amount or 0,
            deductible_tax_amount=inv.tax_amount or 0,
            total_amount=inv.total_amount or 0,
            invoice_category=inv.invoice_category or "增值税专用发票",
            goods_name=inv.goods_name or "",
            deduction_period=period,
            deduction_status="待抵扣",
        )
        db.add(ded)
    else:
        if not ded.deduction_period:
            ded.deduction_period = period
        if not ded.deduction_status:
            ded.deduction_status = "待抵扣"

    db.flush()

    # 供应商建档由 /api/process-all 统一处理，此处直接生成凭证（2026-06-10 铁律）

    # 生成采购入账凭证（借：库存商品 / 贷：应付账款）
    purchase_count = auto_generate_purchase_journal(db, company_id, invoice_id)

    # 按月汇总生成进项抵扣凭证
    vat_count = auto_generate_input_vat_for_period(db, company_id, period)
    db.commit()
    return {"message": f"已为 {period} 生成采购凭证 {purchase_count} 张、进项抵扣凭证 {vat_count} 条", "period": period}


@router.post("/api/purchase-invoices/batch-to-journal")
def purchase_invoice_batch_to_journal(
    body: dict = Body(default=None),
    company_id: int = Query(...),
    db=Depends(get_db)
):
    """一键将勾选的取得发票生成进项抵扣凭证（按月汇总）"""
    # body=None 表示前端传了 null，即为所有发票生成凭证
    if body is None:
        ids = None
    else:
        ids = body.get("ids")
    if ids is None:
        # 为所有未取得凭证的发票生成
        invoices = db.query(PurchaseInvoice).filter(
            PurchaseInvoice.company_id == company_id
        ).order_by(PurchaseInvoice.invoice_date, PurchaseInvoice.id).all()
    else:
        if not ids:
            return {"message": "未选择任何发票", "generated": 0, "skipped": 0, "errors": []}
        invoices = db.query(PurchaseInvoice).filter(
            PurchaseInvoice.company_id == company_id,
            PurchaseInvoice.id.in_(ids)
        ).order_by(PurchaseInvoice.invoice_date, PurchaseInvoice.id).all()

    generated = 0
    skipped = 0
    errors = []
    affected_periods = set()

    for inv in invoices:
        try:
            period = inv.invoice_date.strftime("%Y-%m") if inv.invoice_date else datetime.now().strftime("%Y-%m")

            # 供应商建档+采购凭证由 /api/process-all 统一处理（2026-06-10 铁律）

            # 查找或创建进项抵扣记录
            ded = db.query(InputVATDeduction).filter(
                InputVATDeduction.company_id == company_id,
                InputVATDeduction.invoice_no == inv.invoice_no
            ).first()

            if not ded:
                ded = InputVATDeduction(
                    company_id=company_id,
                    purchase_invoice_id=inv.id,
                    invoice_code=inv.invoice_code or "",
                    invoice_no=inv.invoice_no or "",
                    invoice_date=inv.invoice_date,
                    seller_name=inv.seller_name or "",
                    seller_tax_id=inv.seller_tax_no or "",
                    amount=inv.amount or 0,
                    tax_amount=inv.tax_amount or 0,
                    deductible_tax_amount=inv.tax_amount or 0,
                    total_amount=inv.total_amount or 0,
                    invoice_category=inv.invoice_category or "增值税专用发票",
                    goods_name=inv.goods_name or "",
                    deduction_period=period,
                    deduction_status="待抵扣",
                )
                db.add(ded)
                db.flush()
            else:
                if not ded.deduction_period:
                    ded.deduction_period = period
                if not ded.deduction_status:
                    ded.deduction_status = "待抵扣"
                db.flush()

            affected_periods.add(period)
            generated += 1
        except Exception as e:
            errors.append(f"发票{inv.id}({inv.invoice_no}): {str(e)}")
            db.rollback()

    # 按月汇总生成进项抵扣凭证
    voucher_count = 0
    for period in sorted(affected_periods):
        try:
            c = auto_generate_input_vat_for_period(db, company_id, period)
            voucher_count += c
        except Exception as e:
            errors.append(f"生成期间{period}凭证失败: {str(e)}")


    # 生成采购入账凭证（借：库存商品 / 贷：应付账款）
    # 只处理本次勾选的发票，避免全量重算
    if ids:
        _inv_ids = [inv.id for inv in invoices]
        purchase_count = auto_generate_purchase_journal(db, company_id, invoice_id=_inv_ids)
    else:
        purchase_count = auto_generate_purchase_journal(db, company_id)
    db.commit()
    msg = f"批量生成完成：{generated} 张发票 → 进项抵扣凭证 {voucher_count} 笔"
    if purchase_count:
        msg += f"，采购凭证 {purchase_count} 笔"
    if skipped > 0:
        msg += f"，跳过 {skipped} 张"
    if errors:
        msg += f"，{len(errors)} 项失败"
    return {"message": msg, "generated": generated, "skipped": skipped, "vouchers": voucher_count, "errors": errors}



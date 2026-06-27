"""
合同管理模块 - 从 main.py 自动拆分
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

from database import get_db

router = APIRouter(tags=["合同"])

class ContractCreate(BaseModel):
    contract_no: str
    name: str
    contract_type: str
    party_a: Optional[str] = None
    party_b: Optional[str] = None
    amount: float = 0.0
    signing_date: Optional[date] = None
    effective_date: Optional[date] = None
    expiry_date: Optional[date] = None
    status: str = "起草中"
    responsible_person: Optional[str] = None
    dept_code: Optional[str] = None
    content_summary: Optional[str] = None
    remark: Optional[str] = None


class ContractUpdate(BaseModel):
    name: Optional[str] = None
    contract_type: Optional[str] = None
    party_a: Optional[str] = None
    party_b: Optional[str] = None
    amount: Optional[float] = None
    signing_date: Optional[date] = None
    effective_date: Optional[date] = None
    expiry_date: Optional[date] = None
    status: Optional[str] = None
    responsible_person: Optional[str] = None
    content_summary: Optional[str] = None
    remark: Optional[str] = None


class ContractPaymentCreate(BaseModel):
    payment_no: int = 1
    payment_type: str
    amount: float
    due_date: Optional[date] = None
    remark: Optional[str] = None


@router.get("/api/contracts")
def list_contracts(
    company_id: int = Query(...),
    contract_type: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(Contract).filter(Contract.company_id == company_id)
    if contract_type:
        q = q.filter(Contract.contract_type == contract_type)
    if status:
        q = q.filter(Contract.status == status)
    if keyword:
        q = q.filter(or_(Contract.contract_no.contains(keyword), Contract.name.contains(keyword)))
    contracts = q.order_by(Contract.signing_date.desc()).all()
    return [{
        "id": c.id, "contract_no": c.contract_no, "name": c.name,
        "contract_type": c.contract_type, "party_a": c.party_a, "party_b": c.party_b,
        "amount": c.amount, "signing_date": str(c.signing_date) if c.signing_date else "",
        "effective_date": str(c.effective_date) if c.effective_date else "",
        "expiry_date": str(c.expiry_date) if c.expiry_date else "",
        "status": c.status, "responsible_person": c.responsible_person,
        "dept_code": c.dept_code, "content_summary": c.content_summary, "remark": c.remark
    } for c in contracts]


@router.post("/api/contracts")
def create_contract(data: ContractCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    contract = Contract(company_id=company_id, **data.model_dump())
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return {"id": contract.id, "contract_no": contract.contract_no, "message": "合同创建成功"}


@router.put("/api/contracts/{contract_id}")
def update_contract(contract_id: int, data: ContractUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    c = db.query(Contract).filter(Contract.company_id == company_id, Contract.id == contract_id).first()
    if not c:
        raise HTTPException(404, detail="合同不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    c.updated_at = datetime.now()
    db.commit()
    return {"message": "更新成功"}


@router.delete("/api/contracts/{contract_id}")
def delete_contract(contract_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    c = db.query(Contract).filter(Contract.company_id == company_id, Contract.id == contract_id).first()
    if not c:
        raise HTTPException(404, detail="合同不存在")
    if c.status in ("履行中", "已签署"):
        raise HTTPException(400, detail=f"合同状态为'{c.status}'，不能删除")
    db.delete(c)
    db.commit()
    return {"message": "删除成功"}


@router.get("/api/contracts/{contract_id}/payments")
def get_contract_payments(contract_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    payments = db.query(ContractPayment).filter(
        ContractPayment.company_id == company_id,
        ContractPayment.contract_id == contract_id
    ).order_by(ContractPayment.payment_no).all()
    return [{
        "id": p.id, "payment_no": p.payment_no, "payment_type": p.payment_type,
        "amount": p.amount, "due_date": str(p.due_date) if p.due_date else "",
        "paid_date": str(p.paid_date) if p.paid_date else "",
        "paid_amount": p.paid_amount, "status": p.status, "remark": p.remark
    } for p in payments]


@router.post("/api/contracts/{contract_id}/payments")
def add_contract_payment(contract_id: int, data: ContractPaymentCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    c = db.query(Contract).filter(Contract.company_id == company_id, Contract.id == contract_id).first()
    if not c:
        raise HTTPException(404, detail="合同不存在")
    payment = ContractPayment(
        company_id=company_id, contract_id=contract_id,
        payment_no=data.payment_no, payment_type=data.payment_type,
        amount=data.amount, due_date=data.due_date, remark=data.remark
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {"id": payment.id, "message": "付款计划添加成功"}

@router.delete("/api/contracts/{contract_id}/payments/{payment_id}")
def delete_contract_payment(contract_id: int, payment_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    """删除合同收付款计划"""
    p = db.query(ContractPayment).filter(
        ContractPayment.company_id == company_id,
        ContractPayment.id == payment_id,
        ContractPayment.contract_id == contract_id
    ).first()
    if not p:
        raise HTTPException(404, detail="付款计划不存在")
    db.delete(p)
    db.commit()
    return {"ok": True, "message": "付款计划已删除"}



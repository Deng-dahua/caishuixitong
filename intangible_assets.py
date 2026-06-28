"""
无形资产管理模块 - 从 main.py 自动拆分
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

from database import get_db, JournalEntry, IntangibleAsset, IntangibleAssetAmortization

router = APIRouter(tags=["无形资产"])

class IntangibleAssetCreate(BaseModel):
    code: str
    name: str
    category: str = "专利权"
    purchase_date: Optional[date] = None
    original_value: float = 0.0
    useful_life_months: int = 120
    residual_value: float = 0.0
    remark: Optional[str] = None


class IntangibleAssetUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    purchase_date: Optional[date] = None
    original_value: Optional[float] = None
    residual_value: Optional[float] = None
    useful_life_months: Optional[int] = None
    status: Optional[str] = None
    remark: Optional[str] = None


@router.get("/api/intangible-assets")
def list_intangible_assets(
    company_id: int = Query(...),
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(IntangibleAsset).filter(IntangibleAsset.company_id == company_id)
    if category:
        q = q.filter(IntangibleAsset.category == category)
    if keyword:
        q = q.filter(or_(IntangibleAsset.code.contains(keyword), IntangibleAsset.name.contains(keyword)))
    assets = q.order_by(IntangibleAsset.code).all()
    return [{
        "id": a.id, "code": a.code, "name": a.name, "category": a.category,
        "purchase_date": str(a.purchase_date) if a.purchase_date else "",
        "original_value": a.original_value, "residual_value": a.residual_value,
        "useful_life_months": a.useful_life_months,
        "accumulated_amortization": a.accumulated_amortization,
        "monthly_amortization": a.monthly_amortization,
        "status": a.status,
        "net_value": round(a.original_value - a.accumulated_amortization, 2),
        "remark": a.remark
    } for a in assets]


@router.get("/api/intangible-assets/{ia_id}")
def get_intangible_asset(ia_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    a = db.query(IntangibleAsset).filter(IntangibleAsset.company_id == company_id, IntangibleAsset.id == ia_id).first()
    if not a:
        raise HTTPException(404, detail="无形资产不存在")
    return {
        "id": a.id, "code": a.code, "name": a.name, "category": a.category,
        "purchase_date": str(a.purchase_date) if a.purchase_date else "",
        "original_value": a.original_value, "residual_value": a.residual_value,
        "useful_life_months": a.useful_life_months,
        "accumulated_amortization": a.accumulated_amortization,
        "monthly_amortization": a.monthly_amortization,
        "status": a.status,
        "net_value": round(a.original_value - a.accumulated_amortization, 2),
        "remark": a.remark
    }


@router.post("/api/intangible-assets")
def create_intangible_asset(data: IntangibleAssetCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    monthly = round((data.original_value - data.residual_value) / data.useful_life_months, 2) if data.useful_life_months > 0 else 0
    ia = IntangibleAsset(
        company_id=company_id, code=data.code, name=data.name,
        category=data.category, purchase_date=data.purchase_date,
        original_value=data.original_value, useful_life_months=data.useful_life_months,
        residual_value=data.residual_value, monthly_amortization=monthly,
        remark=data.remark
    )
    db.add(ia)
    db.commit()
    db.refresh(ia)
    return {"id": ia.id, "code": ia.code, "message": "无形资产新增成功"}


@router.put("/api/intangible-assets/{ia_id}")
def update_intangible_asset(ia_id: int, data: IntangibleAssetUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    ia = db.query(IntangibleAsset).filter(IntangibleAsset.company_id == company_id, IntangibleAsset.id == ia_id).first()
    if not ia:
        raise HTTPException(404, detail="资产不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(ia, k, v)
    if ia.useful_life_months and ia.useful_life_months > 0:
        orig = float(ia.original_value or 0)
        resid = float(ia.residual_value or 0)
        ia.monthly_amortization = round((orig - resid) / ia.useful_life_months, 2)
    ia.updated_at = datetime.now()
    db.commit()
    return {"message": "更新成功"}


@router.post("/api/intangible-assets/{ia_id}/amortize")
def amortize_asset(ia_id: int, period: str = Query(...), company_id: int = Query(...), db: Session = Depends(get_db)):
    """计提单月摊销"""
    ia = db.query(IntangibleAsset).filter(IntangibleAsset.company_id == company_id, IntangibleAsset.id == ia_id).first()
    if not ia:
        raise HTTPException(404, detail="资产不存在")
    if ia.status != "在用":
        raise HTTPException(400, detail=f"资产状态为'{ia.status}'，不能摊销")
    existing = db.query(IntangibleAssetAmortization).filter(
        IntangibleAssetAmortization.company_id == company_id,
        IntangibleAssetAmortization.asset_id == ia_id,
        IntangibleAssetAmortization.period == period
    ).first()
    if existing:
        raise HTTPException(400, detail=f"该资产在 {period} 期间已摊销")
    orig = float(ia.original_value or 0)
    resid = float(ia.residual_value or 0)
    accum = float(ia.accumulated_amortization or 0)
    monthly = float(ia.monthly_amortization or 0)
    if accum + monthly > orig - resid:
        amt = orig - resid - accum
    else:
        amt = monthly
    if amt <= 0:
        raise HTTPException(400, detail="该资产已摊销完毕")
    acc_before = accum
    ia.accumulated_amortization = acc_before + amt
    ia.updated_at = datetime.now()
    rec = IntangibleAssetAmortization(
        company_id=company_id, asset_id=ia_id, period=period,
        amortization_amount=amt, accumulated_before=acc_before,
        accumulated_after=round(orig - resid, 2),
        net_value=round(orig - resid, 2)
    )
    db.add(rec)
    db.commit()
    return {"message": f"摊销 ¥{amt:.2f}，累计摊销 ¥{ia.accumulated_amortization:.2f}"}


@router.delete("/api/intangible-assets/{ia_id}")
def delete_intangible_asset(ia_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    ia = db.query(IntangibleAsset).filter(IntangibleAsset.company_id == company_id, IntangibleAsset.id == ia_id).first()
    if not ia:
        raise HTTPException(404, detail="资产不存在")
    db.delete(ia)
    db.commit()
    return {"message": "删除成功"}


@router.get("/api/intangible-assets/{ia_id}/amortizations")
def get_asset_amortizations(ia_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    """查询某项无形资产的摊销明细"""
    recs = db.query(IntangibleAssetAmortization).filter(
        IntangibleAssetAmortization.company_id == company_id,
        IntangibleAssetAmortization.asset_id == ia_id
    ).order_by(IntangibleAssetAmortization.period).all()
    return [{
        "id": r.id, "period": r.period, "amortization_amount": r.amortization_amount,
        "accumulated_before": r.accumulated_before, "accumulated_after": r.accumulated_after,
        "net_value": r.net_value
    } for r in recs]


@router.post("/api/intangible-assets/amortize")
def batch_amortize(company_id: int = Query(...), period: Optional[str] = None,
                   db: Session = Depends(get_db)):
    """批量摊销 + 自动生成凭证"""
    if not period:
        period = datetime.now().strftime("%Y-%m")
    assets = db.query(IntangibleAsset).filter(
        IntangibleAsset.company_id == company_id, IntangibleAsset.status == "在用"
    ).all()
    if not assets:
        return {"amortized_count": 0, "message": "无在用资产"}
    
    amortized = []
    total_amount = 0.0
    for ia in assets:
        existing = db.query(IntangibleAssetAmortization).filter(
            IntangibleAssetAmortization.company_id == company_id,
            IntangibleAssetAmortization.asset_id == ia.id,
            IntangibleAssetAmortization.period == period
        ).first()
        if existing:
            continue
        monthly = float(ia.monthly_amortization or 0)
        if monthly <= 0:
            continue
        orig = float(ia.original_value or 0)
        resid = float(ia.residual_value or 0)
        accum = float(ia.accumulated_amortization or 0)
        max_amt = orig - resid - accum
        if max_amt <= 0:
            continue
        amt = min(monthly, max_amt)
        acc_before = float(ia.accumulated_amortization or 0)
        ia.accumulated_amortization = acc_before + amt
        ia.updated_at = datetime.now()
        rec = IntangibleAssetAmortization(
            company_id=company_id, asset_id=ia.id, period=period,
            amortization_amount=amt, accumulated_before=acc_before,
            accumulated_after=round(orig - resid, 2),
            net_value=round(orig - resid, 2)
        )
        db.add(rec)
        amortized.append((ia, amt))
        total_amount += amt
    
    if not amortized:
        db.commit()
        return {"amortized_count": 0, "total_amount": 0, "message": "所有资产已摊销或无需摊销"}
    
    # 生成摊销凭证
    _ensure_account(db, company_id, "1702", "累计摊销", "资产", "贷")
    _ensure_account(db, company_id, "660208", "摊销费", "损益", "借", parent_code="6602")
    _ensure_account(db, company_id, "6602", "管理费用", "损益", "借")
    
    next_vno = _next_voucher_no(db, company_id, period)
    summary = f"计提{period}无形资产摊销（{len(amortized)}项）"
    je_debit = JournalEntry(
        company_id=company_id, period=period, voucher_word="记", voucher_no=next_vno,
        entry_date=datetime.now().date(), summary=summary, account_code="660208", account_name="摊销费",
        debit_amount=round(total_amount, 2), credit_amount=0,
        source="摊销计提"
    )
    db.add(je_debit)
    je_credit = JournalEntry(
        company_id=company_id, period=period, voucher_word="记", voucher_no=next_vno,
        entry_date=datetime.now().date(), summary=summary, account_code="1702", account_name="累计摊销",
        debit_amount=0, credit_amount=round(total_amount, 2),
        source="摊销计提"
    )
    db.add(je_credit)
    
    db.commit()
    return {
        "amortized_count": len(amortized),
        "total_amount": round(total_amount, 2),
        "voucher_no": f"记-{next_vno}",
        "message": f"摊销{len(amortized)}项资产 ¥{total_amount:,.2f}"
    }


@router.get("/api/intangible-assets/stats")
def intangible_assets_stats(company_id: int = Query(...), db: Session = Depends(get_db)):
    assets = db.query(IntangibleAsset).filter(IntangibleAsset.company_id == company_id).all()
    active = [a for a in assets if a.status == "在用"]
    return {
        "total_count": len(assets),
        "active_count": len(active),
        "total_original": round(sum(a.original_value for a in assets), 2),
        "total_amortization": round(sum(a.accumulated_amortization for a in assets), 2),
        "total_net_value": round(sum(a.original_value - a.accumulated_amortization for a in assets), 2),
        "monthly_amortization": round(sum(a.monthly_amortization for a in active), 2),
    }


@router.post("/api/intangible-assets/batch-delete")
def batch_delete_intangible_assets(ids: List[int], company_id: int = Query(...), db: Session = Depends(get_db)):
    deleted = 0
    for ia_id in ids:
        ia = db.query(IntangibleAsset).filter(IntangibleAsset.company_id == company_id, IntangibleAsset.id == ia_id).first()
        if ia:
            db.delete(ia)
            deleted += 1
    db.commit()
    return {"deleted": deleted, "message": f"删除 {deleted} 项"}



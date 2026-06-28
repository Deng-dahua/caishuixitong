"""
固定资产管理模块 - 从 main.py 自动拆分
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

from database import get_db, JournalEntry, FixedAsset, FixedAssetDepreciation

router = APIRouter(tags=["固定资产"])

class FixedAssetCreate(BaseModel):
    code: str
    name: str
    category: str = "机器设备"
    spec: Optional[str] = None
    unit: Optional[str] = "台"
    dept_code: Optional[str] = None
    location: Optional[str] = None
    purchase_date: Optional[date] = None
    original_value: float = 0.0
    residual_value: float = 0.0
    useful_life_months: int = 60
    depreciation_method: str = "直线法"
    supplier: Optional[str] = None
    warranty_expiry: Optional[date] = None
    remark: Optional[str] = None


class FixedAssetUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    spec: Optional[str] = None
    unit: Optional[str] = None
    dept_code: Optional[str] = None
    location: Optional[str] = None
    purchase_date: Optional[date] = None
    original_value: Optional[float] = None
    residual_value: Optional[float] = None
    useful_life_months: Optional[int] = None
    depreciation_method: Optional[str] = None
    supplier: Optional[str] = None
    status: Optional[str] = None
    remark: Optional[str] = None


@router.get("/api/fixed-assets")
def list_fixed_assets(
    company_id: int = Query(...),
    category: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(FixedAsset).filter(FixedAsset.company_id == company_id)
    if category:
        q = q.filter(FixedAsset.category == category)
    if status:
        q = q.filter(FixedAsset.status == status)
    if keyword:
        q = q.filter(or_(FixedAsset.code.contains(keyword), FixedAsset.name.contains(keyword)))
    assets = q.order_by(FixedAsset.code).all()
    return [{
        "id": a.id, "code": a.code, "name": a.name, "category": a.category,
        "spec": a.spec, "unit": a.unit, "dept_code": a.dept_code,
        "location": a.location, "purchase_date": str(a.purchase_date) if a.purchase_date else "",
        "original_value": a.original_value, "residual_value": a.residual_value,
        "useful_life_months": a.useful_life_months,
        "accumulated_depreciation": a.accumulated_depreciation,
        "monthly_depreciation": a.monthly_depreciation,
        "depreciation_method": a.depreciation_method,
        "status": a.status, "supplier": a.supplier,
        "net_value": round(a.original_value - a.accumulated_depreciation, 2),
        "net_rate": round((a.original_value - a.accumulated_depreciation) / a.original_value * 100, 1) if a.original_value > 0 else 0,
        "remark": a.remark
    } for a in assets]


@router.get("/api/fixed-assets/{fa_id}")
def get_fixed_asset(fa_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    fa = db.query(FixedAsset).filter(FixedAsset.company_id == company_id, FixedAsset.id == fa_id).first()
    if not fa:
        raise HTTPException(404, detail="资产不存在")
    return {
        "id": fa.id, "code": fa.code, "name": fa.name, "category": fa.category,
        "spec": fa.spec, "unit": fa.unit, "dept_code": fa.dept_code,
        "location": fa.location, "purchase_date": str(fa.purchase_date) if fa.purchase_date else "",
        "original_value": fa.original_value, "residual_value": fa.residual_value,
        "useful_life_months": fa.useful_life_months,
        "accumulated_depreciation": fa.accumulated_depreciation,
        "monthly_depreciation": fa.monthly_depreciation,
        "depreciation_method": fa.depreciation_method,
        "status": fa.status, "supplier": fa.supplier,
        "net_value": round(fa.original_value - fa.accumulated_depreciation, 2),
        "net_rate": round((fa.original_value - fa.accumulated_depreciation) / fa.original_value * 100, 1) if fa.original_value > 0 else 0,
        "remark": fa.remark
    }


@router.post("/api/fixed-assets")
def create_fixed_asset(data: FixedAssetCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    # 计算月折旧额（直线法）
    monthly = 0.0
    if data.useful_life_months > 0:
        monthly = round((data.original_value - data.residual_value) / data.useful_life_months, 2)
    fa = FixedAsset(
        company_id=company_id, code=data.code, name=data.name,
        category=data.category, spec=data.spec, unit=data.unit,
        dept_code=data.dept_code, location=data.location,
        purchase_date=data.purchase_date, original_value=data.original_value,
        residual_value=data.residual_value, useful_life_months=data.useful_life_months,
        monthly_depreciation=monthly, depreciation_method=data.depreciation_method,
        supplier=data.supplier, warranty_expiry=data.warranty_expiry,
        remark=data.remark
    )
    db.add(fa)
    db.commit()
    db.refresh(fa)
    return {"id": fa.id, "code": fa.code, "message": "固定资产新增成功"}


@router.put("/api/fixed-assets/{fa_id}")
def update_fixed_asset(fa_id: int, data: FixedAssetUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    fa = db.query(FixedAsset).filter(FixedAsset.company_id == company_id, FixedAsset.id == fa_id).first()
    if not fa:
        raise HTTPException(404, detail="资产不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(fa, k, v)
    # 重新计算月折旧额
    if data.original_value is not None or data.residual_value is not None or data.useful_life_months is not None:
        if fa.useful_life_months and fa.useful_life_months > 0:
            orig = float(fa.original_value or 0)
            resid = float(fa.residual_value or 0)
            fa.monthly_depreciation = round((orig - resid) / fa.useful_life_months, 2)
    fa.updated_at = datetime.now()
    db.commit()
    return {"message": "更新成功"}


@router.post("/api/fixed-assets/{fa_id}/depreciate")
def depreciate_asset(fa_id: int, period: str = Query(...), company_id: int = Query(...), db: Session = Depends(get_db)):
    """计提单月折旧"""
    fa = db.query(FixedAsset).filter(FixedAsset.company_id == company_id, FixedAsset.id == fa_id).first()
    if not fa:
        raise HTTPException(404, detail="资产不存在")
    if fa.status != "在用":
        raise HTTPException(400, detail=f"资产状态为'{fa.status}'，不能计提折旧")
    # 检查是否已折旧
    existing = db.query(FixedAssetDepreciation).filter(
        FixedAssetDepreciation.company_id == company_id,
        FixedAssetDepreciation.asset_id == fa_id,
        FixedAssetDepreciation.period == period
    ).first()
    if existing:
        raise HTTPException(400, detail=f"该资产在 {period} 期间已计提折旧")
    # 累计折旧不能超过（原值-残值）
    orig = float(fa.original_value or 0)
    resid = float(fa.residual_value or 0)
    accum = float(fa.accumulated_depreciation or 0)
    monthly = float(fa.monthly_depreciation or 0)
    if accum + monthly > orig - resid:
        dep_amount = orig - resid - accum
    else:
        dep_amount = monthly
    if dep_amount <= 0:
        raise HTTPException(400, detail="该资产已提足折旧")
    acc_before = accum
    fa.accumulated_depreciation = acc_before + dep_amount
    fa.updated_at = datetime.now()
    rec = FixedAssetDepreciation(
        company_id=company_id, asset_id=fa_id, period=period,
        depreciation_amount=dep_amount, accumulated_before=acc_before,
        accumulated_after=round(orig - resid, 2),
        net_value=round(orig - resid, 2)
    )
    db.add(rec)
    db.commit()
    return {"message": f"计提折旧 ¥{dep_amount:.2f}，累计折旧 ¥{fa.accumulated_depreciation:.2f}"}


@router.get("/api/fixed-assets/{fa_id}/depreciations")
def get_asset_depreciations(fa_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    recs = db.query(FixedAssetDepreciation).filter(
        FixedAssetDepreciation.company_id == company_id,
        FixedAssetDepreciation.asset_id == fa_id
    ).order_by(FixedAssetDepreciation.period).all()
    return [{
        "id": r.id, "period": r.period, "depreciation_amount": r.depreciation_amount,
        "accumulated_before": r.accumulated_before, "accumulated_after": r.accumulated_after,
        "net_value": r.net_value
    } for r in recs]


@router.delete("/api/fixed-assets/{fa_id}")
def delete_fixed_asset(fa_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    fa = db.query(FixedAsset).filter(FixedAsset.company_id == company_id, FixedAsset.id == fa_id).first()
    if not fa:
        raise HTTPException(404, detail="资产不存在")
    if fa.status == "在用":
        raise HTTPException(400, detail="在用资产不能删除，请先变更为闲置或报废")
    db.delete(fa)
    db.commit()
    return {"message": "删除成功"}


@router.post("/api/fixed-assets/depreciate")
def batch_depreciate(company_id: int = Query(...), period: Optional[str] = None,
                     db: Session = Depends(get_db)):
    """批量计提折旧 + 自动生成凭证"""
    if not period:
        period = datetime.now().strftime("%Y-%m")
    assets = db.query(FixedAsset).filter(
        FixedAsset.company_id == company_id, FixedAsset.status == "在用"
    ).all()
    if not assets:
        return {"depreciated_count": 0, "message": "无在用资产"}
    
    depreciated = []
    total_amount = 0.0
    for fa in assets:
        existing = db.query(FixedAssetDepreciation).filter(
            FixedAssetDepreciation.company_id == company_id,
            FixedAssetDepreciation.asset_id == fa.id,
            FixedAssetDepreciation.period == period
        ).first()
        if existing:
            continue
        monthly = float(fa.monthly_depreciation or 0)
        if monthly <= 0:
            continue
        orig = float(fa.original_value or 0)
        resid = float(fa.residual_value or 0)
        accum = float(fa.accumulated_depreciation or 0)
        max_dep = orig - resid - accum
        if max_dep <= 0:
            continue
        dep_amount = min(monthly, max_dep)
        acc_before = float(fa.accumulated_depreciation or 0)
        fa.accumulated_depreciation = acc_before + dep_amount
        fa.updated_at = datetime.now()
        rec = FixedAssetDepreciation(
            company_id=company_id, asset_id=fa.id, period=period,
            depreciation_amount=dep_amount, accumulated_before=acc_before,
            accumulated_after=round(orig - resid, 2),
            net_value=round(orig - resid, 2)
        )
        db.add(rec)
        depreciated.append((fa, dep_amount))
        total_amount += dep_amount
    
    if not depreciated:
        db.commit()
        return {"depreciated_count": 0, "total_amount": 0, "message": "所有资产已计提或无需折旧"}
    
    # 生成折旧凭证
    _ensure_account(db, company_id, "1602", "累计折旧", "资产", "贷")
    _ensure_account(db, company_id, "660203", "折旧费", "损益", "借", parent_code="6602")
    _ensure_account(db, company_id, "6602", "管理费用", "损益", "借")
    
    next_vno = _next_voucher_no(db, company_id, period)
    summary = f"计提{period}固定资产折旧（{len(depreciated)}项）"
    # 借方：管理费用-折旧费
    je_debit = JournalEntry(
        company_id=company_id, period=period, voucher_word="记", voucher_no=next_vno,
        entry_date=datetime.now().date(), summary=summary, account_code="660203", account_name="折旧费",
        debit_amount=round(total_amount, 2), credit_amount=0,
        source="折旧计提"
    )
    db.add(je_debit)
    # 贷方：累计折旧
    je_credit = JournalEntry(
        company_id=company_id, period=period, voucher_word="记", voucher_no=next_vno,
        entry_date=datetime.now().date(), summary=summary, account_code="1602", account_name="累计折旧",
        debit_amount=0, credit_amount=round(total_amount, 2),
        source="折旧计提"
    )
    db.add(je_credit)
    
    db.commit()
    return {
        "depreciated_count": len(depreciated),
        "total_amount": round(total_amount, 2),
        "voucher_no": f"记-{next_vno}",
        "message": f"计提{len(depreciated)}项资产折旧 ¥{total_amount:,.2f}"
    }


@router.get("/api/fixed-assets/stats")
def fixed_assets_stats(company_id: int = Query(...), db: Session = Depends(get_db)):
    """固定资产统计概览"""
    assets = db.query(FixedAsset).filter(FixedAsset.company_id == company_id).all()
    active = [a for a in assets if a.status == "在用"]
    return {
        "total_count": len(assets),
        "active_count": len(active),
        "total_original": round(sum(a.original_value for a in assets), 2),
        "total_depreciation": round(sum(a.accumulated_depreciation for a in assets), 2),
        "total_net_value": round(sum(a.original_value - a.accumulated_depreciation for a in assets), 2),
        "monthly_depreciation": round(sum(a.monthly_depreciation for a in active), 2),
    }


@router.post("/api/fixed-assets/batch-delete")
def batch_delete_fixed_assets(ids: List[int], company_id: int = Query(...), db: Session = Depends(get_db)):
    deleted = 0
    for fa_id in ids:
        fa = db.query(FixedAsset).filter(FixedAsset.company_id == company_id, FixedAsset.id == fa_id).first()
        if fa and fa.status != "在用":
            db.delete(fa)
            deleted += 1
    db.commit()
    return {"deleted": deleted, "message": f"删除 {deleted} 项"}



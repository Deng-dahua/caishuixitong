"""
期间管理/看板管理模块 - 从 main.py 自动拆分
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

from database import get_db

router = APIRouter(tags=["期间管理/看板"])

@router.get("/api/periods")
def list_periods(company_id: int = Query(...), db: Session = Depends(get_db)):
    periods = db.query(Period).filter(Period.company_id == company_id).order_by(Period.period.desc()).all()
    return [{"period": p.period, "status": p.status} for p in periods]


@router.post("/api/periods/{period}/close")
def close_period(period: str, company_id: int = Query(...), db: Session = Depends(get_db)):
    p = db.query(Period).filter(Period.company_id == company_id, Period.period == period).first()
    if not p:
        raise HTTPException(404, detail="期间不存在")
    if p.status == "已结账":
        raise HTTPException(400, detail="该期间已结账")
    p.status = "已结账"
    p.closed_at = datetime.now()

    # 自动创建下期
    year, month = int(period[:4]), int(period[5:])
    if month == 12:
        next_period = f"{year + 1}-01"
    else:
        next_period = f"{year}-{str(month + 1).zfill(2)}"
    existing = db.query(Period).filter(Period.company_id == company_id, Period.period == next_period).first()
    if not existing:
        db.add(Period(company_id=company_id, period=next_period))

    db.commit()
    return {"message": f"{period} 结账成功，已自动创建 {next_period} 期间"}



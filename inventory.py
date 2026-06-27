"""
库存管理模块 - 从 main.py 自动拆分
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Form
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

from database import get_db

router = APIRouter(tags=["库存"])

class InventoryItemCreate(BaseModel):
    code: str
    name: str
    spec: Optional[str] = None
    unit: Optional[str] = "个"
    category: Optional[str] = "原材料"
    warehouse: Optional[str] = None
    safety_stock: float = 0.0
    cost_price: float = 0.0
    sale_price: float = 0.0
    account_code: Optional[str] = None
    remark: Optional[str] = None

class InventoryItemUpdate(BaseModel):
    name: Optional[str] = None
    spec: Optional[str] = None
    category: Optional[str] = None
    warehouse: Optional[str] = None
    safety_stock: Optional[float] = None
    cost_price: Optional[float] = None
    sale_price: Optional[float] = None
    is_active: Optional[bool] = None
    remark: Optional[str] = None

class InventoryTransactionCreate(BaseModel):
    transaction_date: date
    trans_type: str  # 入库/出库/调拨入/调拨出/盘盈/盘亏/其他
    item_code: str
    quantity: float
    unit_price: float = 0.0
    warehouse: Optional[str] = None
    warehouse_to: Optional[str] = None
    voucher_no: Optional[str] = None
    reference_no: Optional[str] = None
    operator: Optional[str] = "管理员"
    remark: Optional[str] = None


@router.get("/api/inventory-items")
def list_inventory_items(
    company_id: int = Query(...),
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(InventoryItem).filter(InventoryItem.company_id == company_id, InventoryItem.is_active == True)
    if category:
        q = q.filter(InventoryItem.category == category)
    if keyword:
        q = q.filter(or_(InventoryItem.code.contains(keyword), InventoryItem.name.contains(keyword)))
    items = q.order_by(InventoryItem.code).all()
    return [{
        "id": i.id, "code": i.code, "name": i.name, "spec": i.spec,
        "unit": i.unit, "category": i.category, "warehouse": i.warehouse,
        "safety_stock": i.safety_stock, "current_stock": i.current_stock,
        "cost_price": i.cost_price, "sale_price": i.sale_price,
        "stock_value": round(i.current_stock * i.cost_price, 2),
        "account_code": i.account_code, "remark": i.remark
    } for i in items]


@router.get("/api/inventory-items/{item_id}")
def get_inventory_item(item_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    i = db.query(InventoryItem).filter(InventoryItem.company_id == company_id, InventoryItem.id == item_id).first()
    if not i:
        raise HTTPException(404, detail="存货不存在")
    return {
        "id": i.id, "code": i.code, "name": i.name, "spec": i.spec,
        "unit": i.unit, "category": i.category, "warehouse": i.warehouse,
        "safety_stock": i.safety_stock, "current_stock": i.current_stock,
        "cost_price": i.cost_price, "sale_price": i.sale_price,
        "stock_value": round(i.current_stock * i.cost_price, 2),
        "account_code": i.account_code, "remark": i.remark
    }


@router.post("/api/inventory-items")
def create_inventory_item(data: InventoryItemCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    item = InventoryItem(company_id=company_id, **data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "code": item.code, "message": "新增成功"}


@router.put("/api/inventory-items/{item_id}")
def update_inventory_item(item_id: int, data: InventoryItemUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.company_id == company_id, InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(404, detail="商品不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    item.updated_at = datetime.now()
    db.commit()
    return {"message": "更新成功"}


@router.delete("/api/inventory-items/{item_id}")
def delete_inventory_item(item_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.company_id == company_id, InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(404, detail="存货不存在")
    item.is_active = False
    item.updated_at = datetime.now()
    db.commit()
    return {"message": "删除成功"}


@router.get("/api/inventory-transactions")
def list_inventory_transactions(
    company_id: int = Query(...),
    item_code: Optional[str] = None,
    trans_type: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    q = db.query(InventoryTransaction).filter(InventoryTransaction.company_id == company_id)
    if item_code:
        q = q.filter(InventoryTransaction.item_code == item_code)
    if trans_type:
        q = q.filter(InventoryTransaction.trans_type == trans_type)
    items = q.order_by(InventoryTransaction.transaction_date.desc(), InventoryTransaction.id.desc()).limit(limit).all()
    return [{
        "id": t.id, "item_code": t.item_code, "transaction_date": str(t.transaction_date),
        "trans_type": t.trans_type, "quantity": t.quantity, "unit_price": t.unit_price,
        "total_amount": t.total_amount, "warehouse": t.warehouse, "warehouse_to": t.warehouse_to,
        "voucher_no": t.voucher_no, "reference_no": t.reference_no,
        "operator": t.operator, "remark": t.remark, "created_at": str(t.created_at.date()) if t.created_at else ""
    } for t in items]


@router.post("/api/inventory-transactions")
def create_inventory_transaction(data: InventoryTransactionCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    # 校验商品存在
    item = db.query(InventoryItem).filter(InventoryItem.company_id == company_id, InventoryItem.code == data.item_code).first()
    if not item:
        raise HTTPException(400, detail=f"商品 {data.item_code} 不存在")
    qty = data.quantity
    total = round(abs(qty) * data.unit_price, 2)
    trans = InventoryTransaction(
        company_id=company_id, item_code=data.item_code,
        transaction_date=data.transaction_date, trans_type=data.trans_type,
        quantity=qty, unit_price=data.unit_price, total_amount=total,
        warehouse=data.warehouse, warehouse_to=data.warehouse_to,
        voucher_no=data.voucher_no, reference_no=data.reference_no,
        operator=data.operator, remark=data.remark
    )
    db.add(trans)
    # 更新库存
    if data.trans_type in ("入库", "调拨入", "盘盈", "其他"):
        item.current_stock += qty
    elif data.trans_type in ("出库", "调拨出", "盘亏"):
        item.current_stock -= qty
        if item.current_stock < 0:
            item.current_stock += qty
            raise HTTPException(400, detail=f"库存不足，当前库存: {item.current_stock}")
    item.updated_at = datetime.now()
    db.commit()
    db.refresh(trans)
    return {"id": trans.id, "message": f"{data.trans_type}成功，当前库存: {item.current_stock}"}


@router.post("/api/inventory-transactions/transfer")
def create_inventory_transfer(company_id: int = Query(...), db: Session = Depends(get_db),
    item_code: str = Form(...), transaction_date: str = Form(...),
    quantity: float = Form(...), warehouse_from: str = Form(...),
    warehouse_to: str = Form(...), unit_price: float = Form(0.0),
    reference_no: str = Form(""), operator: str = Form("管理员"),
    remark: str = Form("")):
    """仓库间调拨"""
    item = db.query(InventoryItem).filter(InventoryItem.company_id == company_id, InventoryItem.code == item_code).first()
    if not item:
        raise HTTPException(400, detail=f"商品 {item_code} 不存在")
    if quantity <= 0:
        raise HTTPException(400, detail="数量必须大于0")
    total = round(quantity * unit_price, 2)
    tx_date = datetime.strptime(transaction_date, "%Y-%m-%d").date() if transaction_date else datetime.now().date()
    
    # 调拨出
    out_tx = InventoryTransaction(
        company_id=company_id, item_code=item_code, transaction_date=tx_date,
        trans_type="调拨出", quantity=quantity, unit_price=unit_price, total_amount=total,
        warehouse=warehouse_from, warehouse_to=warehouse_to,
        reference_no=reference_no, operator=operator, remark=remark
    )
    db.add(out_tx)
    
    # 调拨入
    in_tx = InventoryTransaction(
        company_id=company_id, item_code=item_code, transaction_date=tx_date,
        trans_type="调拨入", quantity=quantity, unit_price=unit_price, total_amount=total,
        warehouse=warehouse_to, warehouse_to=warehouse_from,
        reference_no=reference_no, operator=operator, remark=remark
    )
    db.add(in_tx)
    
    db.commit()
    return {"message": f"调拨 {quantity} {item.unit}从{warehouse_from}到{warehouse_to}", "out_tx_id": out_tx.id, "in_tx_id": in_tx.id}


@router.post("/api/inventory-transactions/count")
def create_inventory_count(company_id: int = Query(...), db: Session = Depends(get_db),
    item_code: str = Form(...), transaction_date: str = Form(...),
    actual_quantity: float = Form(...), unit_price: float = Form(0.0),
    warehouse: str = Form(""), reference_no: str = Form(""),
    operator: str = Form("管理员"), remark: str = Form("")):
    """盘点（自动生成盘盈/盘亏）"""
    item = db.query(InventoryItem).filter(InventoryItem.company_id == company_id, InventoryItem.code == item_code).first()
    if not item:
        raise HTTPException(400, detail=f"商品 {item_code} 不存在")
    diff = actual_quantity - item.current_stock
    if abs(diff) < 0.001:
        return {"message": "库存账实相符，无需调整", "current": item.current_stock, "actual": actual_quantity}
    
    tx_date = datetime.strptime(transaction_date, "%Y-%m-%d").date() if transaction_date else datetime.now().date()
    trans_type = "盘盈" if diff > 0 else "盘亏"
    total = round(abs(diff) * unit_price, 2)
    
    trans = InventoryTransaction(
        company_id=company_id, item_code=item_code, transaction_date=tx_date,
        trans_type=trans_type, quantity=abs(diff), unit_price=unit_price, total_amount=total,
        warehouse=warehouse, reference_no=reference_no, operator=operator,
        remark=f"盘点调整：账存{item.current_stock} 实盘{actual_quantity} 差异{diff} {remark}"
    )
    db.add(trans)
    
    # 更新库存
    if diff > 0:
        item.current_stock += diff
    else:
        item.current_stock += diff  # diff is negative
    item.updated_at = datetime.now()
    db.commit()
    db.refresh(trans)
    return {
        "id": trans.id, "trans_type": trans_type,
        "difference": round(diff, 2), "total_amount": total,
        "message": f"{trans_type}已记录，差异: {diff:+.2f} {item.unit}，当前库存: {item.current_stock}"
    }


@router.get("/api/inventory-balances")
def list_inventory_balances(company_id: int = Query(...), period: str = Query(...),
    db: Session = Depends(get_db)):
    """库存余额表（按期核算）"""
    items = db.query(InventoryItem).filter(InventoryItem.company_id == company_id, InventoryItem.is_active == True).all()
    
    # 期初：取上月余额表或从0开始
    prev_period = _prev_period(period)
    prev_map = {}
    if prev_period:
        prev_balances = db.query(InventoryBalance).filter(
            InventoryBalance.company_id == company_id, InventoryBalance.period == prev_period
        ).all()
        prev_map = {b.item_code: b.end_quantity for b in prev_balances}
    
    # 本期收发汇总
    tx_start = datetime.strptime(period + "-01", "%Y-%m-%d").date()
    if len(period) == 7:
        y, m = int(period[:4]), int(period[5:7])
        if m == 12:
            tx_end = datetime(y + 1, 1, 1).date()
        else:
            tx_end = datetime(y, m + 1, 1).date()
    else:
        tx_end = datetime.now().date()
    
    txs = db.query(InventoryTransaction).filter(
        InventoryTransaction.company_id == company_id,
        InventoryTransaction.transaction_date >= tx_start,
        InventoryTransaction.transaction_date < tx_end
    ).all()
    
    # 按商品汇总
    from collections import defaultdict
    in_map = defaultdict(float)
    out_map = defaultdict(float)
    for t in txs:
        if t.trans_type in ("入库", "调拨入", "盘盈"):
            in_map[t.item_code] += t.quantity
        elif t.trans_type in ("出库", "调拨出", "盘亏"):
            out_map[t.item_code] += t.quantity
    
    results = []
    for item in items:
        begin = prev_map.get(item.code, 0.0)
        in_qty = round(in_map.get(item.code, 0), 2)
        out_qty = round(out_map.get(item.code, 0), 2)
        end_qty = round(begin + in_qty - out_qty, 2)
        end_amount = round(end_qty * item.cost_price, 2)
        results.append({
            "item_code": item.code, "item_name": item.name,
            "spec": item.spec, "unit": item.unit, "warehouse": item.warehouse,
            "begin_quantity": begin, "in_quantity": in_qty,
            "out_quantity": out_qty, "end_quantity": end_qty,
            "cost_price": item.cost_price, "end_amount": end_amount
        })
    
    return {"period": period, "items": results}


def _prev_period(period: str) -> Optional[str]:
    """计算上月期间"""
    if len(period) != 7:
        return None
    y, m = int(period[:4]), int(period[5:7])
    if m == 1:
        return f"{y-1}-12"
    return f"{y}-{m-1:02d}"


@router.post("/api/inventory-items/batch-delete")
def batch_delete_inventory_items(ids: List[int], company_id: int = Query(...), db: Session = Depends(get_db)):
    deleted = 0
    for item_id in ids:
        item = db.query(InventoryItem).filter(InventoryItem.company_id == company_id, InventoryItem.id == item_id).first()
        if item:
            item.is_active = False
            deleted += 1
    db.commit()
    return {"deleted": deleted, "message": f"停用 {deleted} 项"}



"""
进项抵扣管理模块 - 从 main.py 自动拆分
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Form
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
import os, io, json, openpyxl, re as _re_module

from database import get_db

router = APIRouter(tags=["进项抵扣"])

class InputVATDeductionCreate(BaseModel):
    purchase_invoice_id: Optional[int] = None
    check_status: Optional[str] = None
    invoice_source: Optional[str] = None
    domestic_sale_cert_no: Optional[str] = None
    digital_invoice_no: Optional[str] = None
    invoice_code: Optional[str] = None
    invoice_no: Optional[str] = None
    invoice_date: Optional[date] = None
    seller_tax_id: Optional[str] = None
    seller_name: Optional[str] = None
    amount: float = 0.0
    tax_amount: float = 0.0
    deductible_tax_amount: float = 0.0
    invoice_category: Optional[str] = None
    invoice_category_label: Optional[str] = None
    invoice_status: Optional[str] = "正常"
    check_time: Optional[datetime] = None
    risk_level: Optional[str] = "正常"
    # 保留字段
    goods_name: Optional[str] = None
    total_amount: float = 0.0
    tax_rate: Optional[float] = 0.0
    deducted_tax_amount: Optional[float] = 0.0
    deduction_period: Optional[str] = None
    deduction_status: str = "待抵扣"
    certification_date: Optional[date] = None
    deduction_date: Optional[date] = None
    deduction_method: str = "凭票抵扣"
    voucher_no: Optional[str] = None
    remark: Optional[str] = None


class InputVATDeductionUpdate(BaseModel):
    check_status: Optional[str] = None
    invoice_source: Optional[str] = None
    domestic_sale_cert_no: Optional[str] = None
    digital_invoice_no: Optional[str] = None
    invoice_code: Optional[str] = None
    invoice_no: Optional[str] = None
    invoice_date: Optional[date] = None
    seller_tax_id: Optional[str] = None
    seller_name: Optional[str] = None
    amount: Optional[float] = None
    tax_amount: Optional[float] = None
    deductible_tax_amount: Optional[float] = None
    invoice_category: Optional[str] = None
    invoice_category_label: Optional[str] = None
    invoice_status: Optional[str] = None
    check_time: Optional[datetime] = None
    risk_level: Optional[str] = None
    # 保留字段
    goods_name: Optional[str] = None
    total_amount: Optional[float] = None
    tax_rate: Optional[float] = None
    deducted_tax_amount: Optional[float] = None
    deduction_period: Optional[str] = None
    deduction_status: Optional[str] = None
    certification_date: Optional[date] = None
    deduction_date: Optional[date] = None
    deduction_method: Optional[str] = None
    voucher_no: Optional[str] = None
    remark: Optional[str] = None


@router.get("/api/input-vat-deductions")
def list_input_vat_deductions(
    company_id: int = Query(...),
    invoice_status: Optional[str] = None,
    check_status: Optional[str] = None,
    risk_level: Optional[str] = None,
    deduction_period: Optional[str] = None,
    keyword: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(InputVATDeduction).filter(InputVATDeduction.company_id == company_id)
    if invoice_status:
        q = q.filter(InputVATDeduction.invoice_status == invoice_status)
    if check_status:
        q = q.filter(InputVATDeduction.check_status == check_status)
    if risk_level:
        q = q.filter(InputVATDeduction.risk_level == risk_level)
    if deduction_period:
        q = q.filter(InputVATDeduction.deduction_period == deduction_period)
    if date_from:
        q = q.filter(InputVATDeduction.invoice_date >= date_from)
    if date_to:
        q = q.filter(InputVATDeduction.invoice_date <= date_to)
    if keyword:
        q = q.filter(or_(
            InputVATDeduction.invoice_no.contains(keyword),
            InputVATDeduction.digital_invoice_no.contains(keyword),
            InputVATDeduction.invoice_code.contains(keyword),
            InputVATDeduction.seller_name.contains(keyword),
            InputVATDeduction.seller_tax_id.contains(keyword),
        ))
    items = q.order_by(InputVATDeduction.invoice_date.desc(), InputVATDeduction.check_time.desc()).all()
    # 构建凭证号映射（进项抵扣 → 序时账，按期间匹配 source="进项抵扣" 的汇总凭证）
    # 期间取值与凭证生成逻辑一致：deduction_period 优先，fallback 到 invoice_date 年月
    def _effective_period(it):
        if it.deduction_period:
            return it.deduction_period
        if it.invoice_date:
            return it.invoice_date.strftime("%Y-%m")
        return None
    periods_set = list(set(_effective_period(it) for it in items if _effective_period(it)))
    period_vouchers = {}
    if periods_set:
        for je in db.query(JournalEntry).filter(
            JournalEntry.company_id == company_id,
            JournalEntry.source == "进项抵扣",
            JournalEntry.period.in_(periods_set),
            JournalEntry.account_code == "221001002"
        ).all():
            period_vouchers[je.period] = f"{je.voucher_word}-{je.voucher_no}"
    voucher_map = {}
    for it in items:
        ep = _effective_period(it)
        if ep and ep in period_vouchers:
            voucher_map[it.id] = period_vouchers[ep]
    return [{
        "id": it.id, "purchase_invoice_id": it.purchase_invoice_id,
        "check_status": it.check_status or "",
        "invoice_source": it.invoice_source or "",
        "domestic_sale_cert_no": it.domestic_sale_cert_no or "",
        "digital_invoice_no": it.digital_invoice_no or "",
        "invoice_code": it.invoice_code or "",
        "invoice_no": it.invoice_no or "",
        "invoice_date": str(it.invoice_date) if it.invoice_date else "",
        "seller_tax_id": it.seller_tax_id or "",
        "seller_name": it.seller_name or "",
        "amount": it.amount or 0,
        "tax_amount": it.tax_amount or 0,
        "deductible_tax_amount": it.deductible_tax_amount or 0,
        "invoice_category": it.invoice_category or "",
        "invoice_category_label": it.invoice_category_label or "",
        "invoice_status": it.invoice_status or "正常",
        "check_time": str(it.check_time) if it.check_time else "",
        "risk_level": it.risk_level or "正常",
        "goods_name": it.goods_name or "",
        "total_amount": it.total_amount or 0,
        "tax_rate": it.tax_rate or 0,
        "deducted_tax_amount": it.deducted_tax_amount or 0,
        "deduction_period": it.deduction_period or "",
        "deduction_status": it.deduction_status or "",
        "certification_date": str(it.certification_date) if it.certification_date else "",
        "deduction_date": str(it.deduction_date) if it.deduction_date else "",
        "deduction_method": it.deduction_method or "",
        "voucher_no": it.voucher_no or "", "remark": it.remark or "",
        "journal_voucher_no": voucher_map.get(it.id, ""),
        "import_batch_id": it.import_batch_id or "",
        "created_at": str(it.created_at) if it.created_at else ""
    } for it in items]


@router.post("/api/input-vat-deductions")
def create_input_vat_deduction(data: InputVATDeductionCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    item = InputVATDeduction(company_id=company_id, **data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    # 自动生成序时账凭证（按期间汇总）
    try:
        period = item.deduction_period
        if not period:
            period = item.invoice_date.strftime("%Y-%m") if item.invoice_date else datetime.now().strftime("%Y-%m")
        auto_generate_input_vat_for_period(db, company_id, period)
    except Exception as e:
        db.rollback()
    return {"id": item.id, "message": "进项抵扣记录创建成功"}


@router.get("/api/input-vat-deductions/stats")
def input_vat_deduction_stats(company_id: int = Query(...), db: Session = Depends(get_db)):
    base = db.query(InputVATDeduction).filter(InputVATDeduction.company_id == company_id)
    total_count = base.count()
    total_tax = base.with_entities(func.sum(InputVATDeduction.tax_amount)).scalar() or 0
    total_deductible = base.with_entities(func.sum(InputVATDeduction.deductible_tax_amount)).scalar() or 0
    total_amount = base.with_entities(func.sum(InputVATDeduction.amount)).scalar() or 0
    unchecked_count = base.filter(InputVATDeduction.check_status == "未勾选").count()
    checked_count = base.filter(InputVATDeduction.check_status == "已勾选").count()
    abnormal_count = base.filter(InputVATDeduction.risk_level.in_(["疑点", "异常", "失控"])).count()
    return {
        "total_count": total_count,
        "total_amount": round(total_amount, 2),
        "total_tax": round(total_tax, 2),
        "total_deductible": round(total_deductible, 2),
        "unchecked_count": unchecked_count,
        "checked_count": checked_count,
        "abnormal_count": abnormal_count
    }


@router.get("/api/input-vat-deductions/{item_id}")
def get_input_vat_deduction(item_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    it = db.query(InputVATDeduction).filter(InputVATDeduction.company_id == company_id, InputVATDeduction.id == item_id).first()
    if not it:
        raise HTTPException(404, detail="抵扣记录不存在")
    return {
        "id": it.id, "purchase_invoice_id": it.purchase_invoice_id,
        "check_status": it.check_status or "",
        "invoice_source": it.invoice_source or "",
        "domestic_sale_cert_no": it.domestic_sale_cert_no or "",
        "digital_invoice_no": it.digital_invoice_no or "",
        "invoice_code": it.invoice_code or "",
        "invoice_no": it.invoice_no or "",
        "invoice_date": str(it.invoice_date) if it.invoice_date else "",
        "seller_tax_id": it.seller_tax_id or "",
        "seller_name": it.seller_name or "",
        "amount": it.amount or 0,
        "tax_amount": it.tax_amount or 0,
        "deductible_tax_amount": it.deductible_tax_amount or 0,
        "invoice_category": it.invoice_category or "",
        "invoice_category_label": it.invoice_category_label or "",
        "invoice_status": it.invoice_status or "正常",
        "check_time": str(it.check_time) if it.check_time else "",
        "risk_level": it.risk_level or "正常",
        "goods_name": it.goods_name or "",
        "total_amount": it.total_amount or 0,
        "tax_rate": it.tax_rate or 0,
        "deducted_tax_amount": it.deducted_tax_amount or 0,
        "deduction_period": it.deduction_period or "",
        "deduction_status": it.deduction_status or "",
        "certification_date": str(it.certification_date) if it.certification_date else "",
        "deduction_date": str(it.deduction_date) if it.deduction_date else "",
        "deduction_method": it.deduction_method or "",
        "voucher_no": it.voucher_no or "", "remark": it.remark or "",
        "created_at": str(it.created_at) if it.created_at else "",
        "updated_at": str(it.updated_at) if it.updated_at else ""
    }


@router.put("/api/input-vat-deductions/{item_id}")
def update_input_vat_deduction(item_id: int, data: InputVATDeductionUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    it = db.query(InputVATDeduction).filter(InputVATDeduction.company_id == company_id, InputVATDeduction.id == item_id).first()
    if not it:
        raise HTTPException(404, detail="抵扣记录不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(it, k, v)
    it.updated_at = datetime.now()
    db.commit()
    # 自动更新序时账凭证（按期间汇总）
    try:
        period = it.deduction_period
        if not period:
            period = it.invoice_date.strftime("%Y-%m") if it.invoice_date else datetime.now().strftime("%Y-%m")
        auto_generate_input_vat_for_period(db, company_id, period)
    except Exception as e:
        db.rollback()
    return {"message": "更新成功"}


@router.delete("/api/input-vat-deductions/{item_id}")
def delete_input_vat_deduction(item_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    it = db.query(InputVATDeduction).filter(InputVATDeduction.company_id == company_id, InputVATDeduction.id == item_id).first()
    if not it:
        raise HTTPException(404, detail="抵扣记录不存在")
    db.delete(it)
    db.commit()
    return {"message": "删除成功"}


@router.post("/api/input-vat-deductions/batch-delete")
def batch_delete_input_vat_deductions(ids: list[int], company_id: int = Query(...), db: Session = Depends(get_db)):
    deleted = db.query(InputVATDeduction).filter(
        InputVATDeduction.company_id == company_id,
        InputVATDeduction.id.in_(ids)
    ).delete(synchronize_session=False)
    db.commit()
    return {"message": f"已删除 {deleted} 条记录", "deleted": deleted}


@router.post("/api/input-vat-deductions/batch-certify")
def batch_certify_input_vat_deductions(ids: list[int], company_id: int = Query(...), db: Session = Depends(get_db)):
    """批量认证：将选中记录标记为已勾选，设置勾选时间/认证日期"""
    now = datetime.now()
    today = date.today()
    
    items = db.query(InputVATDeduction).filter(
        InputVATDeduction.company_id == company_id,
        InputVATDeduction.id.in_(ids)
    ).all()
    
    if not items:
        raise HTTPException(400, detail="未找到可认证记录")
    
    certified = 0
    affected_periods = set()
    for it in items:
        changed = False
        if it.check_status != "已勾选":
            it.check_status = "已勾选"
            it.check_time = now
            changed = True
        if not it.certification_date:
            it.certification_date = today
            changed = True
        if it.deduction_status in (None, "", "待认证"):
            it.deduction_status = "待抵扣"
            changed = True
        if changed:
            it.updated_at = now
            certified += 1
            period = it.deduction_period
            if not period and it.invoice_date:
                period = it.invoice_date.strftime("%Y-%m")
            if period:
                affected_periods.add(period)
    
    db.commit()
    
    # 为受影响的期间重新生成进项抵扣凭证
    voucher_count = 0
    for period in affected_periods:
        try:
            voucher_count += auto_generate_input_vat_for_period(db, company_id, period)
        except Exception:
            pass
    db.commit()
    
    return {
        "message": f"已认证 {certified} 条记录" + (f"，生成 {voucher_count} 笔汇总凭证" if voucher_count else ""),
        "certified": certified,
        "voucher_count": voucher_count
    }


@router.post("/api/input-vat-deductions/batch-to-journal")
def input_vat_batch_to_journal(ids: Optional[List[int]] = Body(None), company_id: int = Query(...), db: Session = Depends(get_db)):
    """按指定进项抵扣记录的期间批量生成/重生成凭证；不传 ids 则处理全部"""
    q = db.query(InputVATDeduction).filter(InputVATDeduction.company_id == company_id)
    if ids:
        q = q.filter(InputVATDeduction.id.in_(ids))
    deductions = q.all()
    periods = set()
    for d in deductions:
        period = d.deduction_period or (d.invoice_date.strftime("%Y-%m") if d.invoice_date else None)
        if period:
            periods.add(period)
    total = 0
    vouchers = []
    for period in sorted(periods):
        try:
            c = auto_generate_input_vat_for_period(db, company_id, period)
            total += c
            if c:
                vouchers.append(period)
        except Exception:
            pass
    db.commit()
    return {
        "message": f"已为 {len(periods)} 个期间生成进项抵扣凭证，共 {total} 条",
        "periods": sorted(periods),
        "vouchers": vouchers,
        "total": total
    }


@router.post("/api/bank-transactions/batch-to-journal")
def bank_transactions_batch_to_journal(ids: Optional[List[int]] = Body(None), company_id: int = Query(...), db: Session = Depends(get_db)):
    """为指定银行流水批量生成记账凭证；不传 ids 则处理全部"""
    result = _generate_bank_journals(db, company_id, ids)
    db.commit()
    return {
        "message": f"已生成 {result['generated']} 条银行流水凭证，跳过 {result['skipped']} 条",
        "generated": result["generated"],
        "skipped": result["skipped"],
        "errors": result["errors"],
        "infos": result.get("infos", []),
    }


@router.post("/api/bank-transactions/auto-voucher")
def bank_transactions_auto_voucher(company_id: int = Query(...), db: Session = Depends(get_db)):
    """导入银行流水后自动全链路处理：
    0. 档案缺失补齐（序时账有往来科目但档案缺失 → 自动建档，零容忍gap）
    0.5 档案信息补全（从发票/银行流水提取税号/银行账号等，第一时间填补缺失字段）
    1. 双源供应商智能建档（发票∩银行流水 → 供应商档案）
    2. 常规银行流水凭证生成（_classify_bank_tx 11级分类）
    3. 社保缴纳匹配
    4. 国家金库税费组合缴纳匹配（含单税兜底）
    5. 公积金缴纳匹配
    """
    result = {"generated": 0, "suppliers_created": 0, "customers_fixed": 0, "suppliers_fixed": 0,
              "customers_enriched": 0, "suppliers_enriched": 0, "infos": []}

    # 第0步：档案缺失补齐（序时账有往来但档案缺失 → 自动建档）
    # 这是确定性规则：有明细账就必需有档案，零容忍gap
    try:
        gap_result = _close_archive_gap(db, company_id)
        result["customers_fixed"] = gap_result.get("customer_created", 0)
        result["suppliers_fixed"] = gap_result.get("supplier_created", 0)
    except Exception:
        pass

    # 第0.5步：档案信息补全（从发票/银行流水提取缺失字段）
    try:
        enrich_result = _enrich_archive_info(db, company_id)
        result["customers_enriched"] = enrich_result.get("customer_enriched", 0)
        result["suppliers_enriched"] = enrich_result.get("supplier_enriched", 0)
    except Exception:
        pass

    # 第1步：双源供应商智能建档（发票∩银行 → 正式供应商）
    try:
        supp_result = _do_auto_create_suppliers(db, company_id)
        result["suppliers_created"] = supp_result.get("created", 0)
        if supp_result.get("infos"):
            result["infos"].extend(supp_result["infos"])
    except Exception:
        pass

    # 第1步：常规银行流水凭证生成
    try:
        bk_result = _generate_bank_journals(db, company_id, None)
        result["generated"] += bk_result.get("generated", 0)
        if bk_result.get("infos"):
            result["infos"].extend(bk_result["infos"])
    except Exception:
        pass

    # 第2步：社保缴纳匹配
    try:
        ss_result = _match_ss_payment_journals(db, company_id)
        result["generated"] += ss_result.get("generated", 0)
    except Exception:
        pass

    # 第3步：国家金库税费组合缴纳匹配
    try:
        tax_result = _match_tax_payment_journals(db, company_id)
        result["generated"] += tax_result.get("generated", 0)
    except Exception:
        pass

    # 第4步：公积金缴纳匹配
    try:
        hf_result = _match_hf_payment_journals(db, company_id)
        result["generated"] += hf_result.get("generated", 0)
    except Exception:
        pass

    db.commit()
    return {
        "message": f"自动生成 {result['generated']} 条凭证，新建 {result['suppliers_created']} 个供应商",
        "generated": result["generated"],
        "suppliers_created": result["suppliers_created"],
        "detail": result
    }


@router.post("/api/bank-transactions/classify")
def classify_bank_transactions(ids: List[int] = Body(...), company_id: int = Query(...), db: Session = Depends(get_db)):
    """预览银行流水凭证分类结果（不生成凭证），返回每条流水的建议科目"""
    txs = db.query(BankTransaction).filter(
        BankTransaction.company_id == company_id,
        BankTransaction.id.in_(ids)
    ).all()
    results = []
    # 预建跨实体索引
    entity_index = _build_entity_index(db, company_id)
    for tx in txs:
        result = _classify_bank_tx(db, company_id, tx, entity_index)
        if result is None:
            results.append({
                "tx_id": tx.id,
                "summary": tx.summary or tx.counterparty_name or "银行流水",
                "amount": abs(float(tx.amount) if tx.amount else 0),
                "is_debit": tx.amount is not None and tx.amount < 0,
                "debit_account": "", "debit_name": "",
                "credit_account": "", "credit_name": "",
                "match_type": "unclassified",
            })
            continue
        other_code, other_name, match_type = result
        is_debit = tx.amount is not None and tx.amount < 0
        amount = abs(float(tx.amount) if tx.amount else 0)
        # 确定借贷方向
        if match_type == "internal_transfer":
            results.append({
                "tx_id": tx.id,
                "summary": tx.summary or tx.counterparty_name or "银行流水",
                "amount": amount,
                "is_debit": is_debit,
                "debit_account": "1002", "debit_name": "银行存款",
                "credit_account": "1002", "credit_name": "银行存款(内部转账)",
                "match_type": match_type,
            })
        elif is_debit:
            results.append({
                "tx_id": tx.id,
                "summary": tx.summary or tx.counterparty_name or "银行流水",
                "amount": amount,
                "is_debit": True,
                "debit_account": other_code, "debit_name": other_name,
                "credit_account": "1002", "credit_name": "银行存款",
                "match_type": match_type,
            })
        else:
            results.append({
                "tx_id": tx.id,
                "summary": tx.summary or tx.counterparty_name or "银行流水",
                "amount": amount,
                "is_debit": False,
                "debit_account": "1002", "debit_name": "银行存款",
                "credit_account": other_code, "credit_name": other_name,
                "match_type": match_type,
            })
    return {"results": results}


@router.post("/api/input-vat-deductions/{item_id}/to-journal")
def input_vat_deduction_to_journal(item_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    """为进项抵扣记录所在期间重新生成凭证"""
    it = db.query(InputVATDeduction).filter(
        InputVATDeduction.id == item_id,
        InputVATDeduction.company_id == company_id
    ).first()
    if not it:
        raise HTTPException(404, "抵扣记录不存在")

    period = it.deduction_period or (it.invoice_date.strftime("%Y-%m") if it.invoice_date else datetime.now().strftime("%Y-%m"))
    count = auto_generate_input_vat_for_period(db, company_id, period)
    db.commit()
    return {"message": f"已为 {period} 生成进项抵扣凭证 ({count} 条)", "period": period}



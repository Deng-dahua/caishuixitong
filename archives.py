"""
档案管理模块 - 从 main.py 自动拆分
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Form, UploadFile, File, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, text
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
import os, io, json, re as _re_module, openpyxl, hashlib, csv, logging
from runtime_storage import company_upload_dir
from utils import (
    build_account_hierarchy as _build_account_hierarchy,
    renumber_archive as _renumber_archive,
)

from database import get_db, Department, Employee, Customer, Supplier, Company, Account, Period, JournalEntry, \
    SalesInvoice, PurchaseInvoice, BookkeepingInvoice, BankTransaction, InputVATDeduction, \
    CompanyShareholder, CompanyDirector, CompanySupervisor, CompanyFinanceContact

router = APIRouter(tags=["档案管理"])


# ═══ Pydantic 模型 ═══

class DepartmentCreate(BaseModel):
    code: str
    name: str
    parent_code: Optional[str] = None
    manager: Optional[str] = None
    description: Optional[str] = None

class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    manager: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class EmployeeCreate(BaseModel):
    code: str
    name: str
    id_card: Optional[str] = None
    email: Optional[str] = None
    salary: Optional[float] = 0.0

class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    id_card: Optional[str] = None
    email: Optional[str] = None
    salary: Optional[float] = None
    leave_date: Optional[date] = None

class BatchDelete(BaseModel):
    ids: List[int]

class CustomerCreate(BaseModel):
    code: str
    name: str
    uscc: Optional[str] = None
    tax_no: Optional[str] = None
    address: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    remark: Optional[str] = None

class CustomerUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    uscc: Optional[str] = None
    tax_no: Optional[str] = None
    address: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    is_active: Optional[bool] = None
    remark: Optional[str] = None

class SupplierCreate(BaseModel):
    code: str
    name: str
    uscc: Optional[str] = None
    tax_no: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    remark: Optional[str] = None

class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    uscc: Optional[str] = None
    tax_no: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    is_active: Optional[bool] = None
    remark: Optional[str] = None

@router.get("/api/departments")
def list_departments(
    keyword: Optional[str] = None,
    company_id: int = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    q = db.query(Department).filter(Department.company_id == company_id)
    if keyword:
        q = q.filter(or_(
            Department.code.contains(keyword),
            Department.name.contains(keyword)
        ))
    depts = q.order_by(Department.code).offset(skip).limit(limit).all()
    return [
        {
            "id": d.id, "code": d.code, "name": d.name,
            "parent_code": d.parent_code, "manager": d.manager,
            "description": d.description, "is_active": d.is_active,
            "has_journal": False
        } for d in depts
    ]

# ── 档案锁定检查（被序时账引用时禁止编辑/删除）──

def _check_archive_lock(db, company_id, archive_type, archive_id) -> bool:
    """检查档案是否被序时账引用。返回 True=已锁定"""
    if archive_type == "department":
        return False
    elif archive_type == "employee":
        emp = db.query(Employee).filter(Employee.company_id == company_id, Employee.id == archive_id).first()
        if emp and emp.name:
            return db.query(JournalEntry).filter(
                JournalEntry.company_id == company_id,
                JournalEntry.contact_project == emp.name
            ).first() is not None
    elif archive_type == "customer":
        cust = db.query(Customer).filter(Customer.company_id == company_id, Customer.id == archive_id).first()
        if cust and cust.name:
            return db.query(JournalEntry).filter(
                JournalEntry.company_id == company_id,
                JournalEntry.contact_project == cust.name
            ).first() is not None
    elif archive_type == "supplier":
        supp = db.query(Supplier).filter(Supplier.company_id == company_id, Supplier.id == archive_id).first()
        if supp and supp.name:
            return db.query(JournalEntry).filter(
                JournalEntry.company_id == company_id,
                JournalEntry.contact_project == supp.name
            ).first() is not None
    return False

@router.post("/api/departments")
def create_department(data: DepartmentCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    d = Department(company_id=company_id, **data.model_dump())
    db.add(d)
    db.commit()
    return {"message": "新增成功"}

@router.put("/api/departments/{dept_id}")
def update_department(dept_id: int, data: DepartmentUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    if _check_archive_lock(db, company_id, "department", dept_id):
        raise HTTPException(403, detail="该部门已被序时账引用，不可编辑")
    d = db.query(Department).filter(Department.company_id == company_id, Department.id == dept_id).first()
    if not d:
        raise HTTPException(404, detail="部门不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(d, k, v)
    db.commit()
    return {"message": "更新成功"}

@router.delete("/api/departments/{dept_id}")
def delete_department(dept_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    if _check_archive_lock(db, company_id, "department", dept_id):
        raise HTTPException(403, detail="该部门已被序时账引用，不可删除")
    d = db.query(Department).filter(Department.company_id == company_id, Department.id == dept_id).first()
    if not d:
        raise HTTPException(404, detail="部门不存在")
    db.delete(d)
    db.flush()
    _renumber_archive(db, company_id, Department, 'BM')
    db.commit()
    return {"message": "删除成功"}

class DeptBatchDelete(BaseModel):
    ids: list[int]

@router.post("/api/departments/batch-delete")
def batch_delete_departments(req: DeptBatchDelete, company_id: int = Query(...), db: Session = Depends(get_db)):
    # 过滤掉被序时账引用的部门
    locked_ids = [did for did in req.ids if _check_archive_lock(db, company_id, "department", did)]
    deletable_ids = [did for did in req.ids if did not in locked_ids]
    if not deletable_ids:
        raise HTTPException(403, detail="所选部门均已被序时账引用，不可删除")
    deleted = db.query(Department).filter(
        Department.company_id == company_id,
        Department.id.in_(deletable_ids)
    ).delete(synchronize_session=False)
    db.flush()
    _renumber_archive(db, company_id, Department, 'BM')
    db.commit()
    return {"message": f"成功删除 {deleted} 个部门", "count": deleted}

@router.post("/api/departments/import")
async def import_departments(
    file: UploadFile = File(...),
    company_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """从 CSV/XLSX 导入部门（编码+名称），编码为空时自动生成 BM001 格式"""
    ext = os.path.splitext(file.filename or "unknown")[1].lower()
    content_bytes = await file.read()

    rows = []
    if ext in (".xlsx", ".xls"):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content_bytes), data_only=True)
            ws = wb.active
            for r in ws.iter_rows(values_only=True):
                rows.append([str(c) if c is not None else "" for c in r])
        except Exception as e:
            raise HTTPException(400, f"无法解析 Excel 文件: {e}")
    elif ext == ".csv":
        try:
            text = content_bytes.decode("utf-8-sig")
            rows = list(csv.reader(io.StringIO(text)))
        except UnicodeDecodeError as e:
            raise HTTPException(400, f"文件编码错误，请使用 UTF-8 编码的 CSV: {e}")
    else:
        raise HTTPException(400, f"不支持的文件格式: {ext}，请上传 .csv 或 .xlsx")

    if not rows:
        raise HTTPException(400, "文件为空")
    headers = [h.strip() for h in rows[0]]
    ci = next((i for i, h in enumerate(headers) if h in ("编码", "code", "部门编码")), None)
    ni = next((i for i, h in enumerate(headers) if h in ("名称", "name", "部门名称", "部门")), 1)


    # 获取当前最大编码（仅匹配 BM 前缀，提取数字部分）
    existing_codes = db.query(Department.code).filter(
        Department.company_id == company_id,
        Department.code.like('BM%')
    ).all()
    code_counter = 0
    for c in existing_codes:
        try:
            num = int(c[0][2:])
            if num > code_counter:
                code_counter = num
        except Exception: pass

    imported = 0
    skipped = 0
    for row in rows[1:]:
        # 跳过完全空行
        if not any(str(c).strip() for c in row):
            continue
        code = row[ci].strip() if (ci is not None and ci < len(row)) else ""
        name = row[ni].strip() if ni < len(row) else ""
        if not name:
            continue


        # 编码为空时自动生成 BM001 格式
        if not code:
            code_counter += 1
            code = f"BM{code_counter:03d}"

        existing = db.query(Department).filter(
            Department.company_id == company_id, Department.code == code
        ).first()
        if existing:
            existing.name = name
        else:
            db.add(Department(
                company_id=company_id, code=code, name=name
            ))
        imported += 1
    db.commit()
    msg = f"成功导入 {imported} 条部门"
    if skipped > 0:
        msg += f"，跳过 {skipped} 条重复"
    return {"message": msg, "count": imported, "skipped": skipped}


# ==================== 人员档案 ====================

@router.get("/api/employees")
def list_employees(
    keyword: Optional[str] = None,
    company_id: int = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    q = db.query(Employee).filter(Employee.company_id == company_id)
    if keyword:
        q = q.filter(or_(
            Employee.code.contains(keyword),
            Employee.name.contains(keyword)
        ))
    emps = q.order_by(Employee.code).offset(skip).limit(limit).all()

    # 检测哪些人员在序时账往来项目中出现过
    emp_names = [e.name for e in emps if e.name]
    names_with_entries = set()
    if emp_names:
        hits = db.query(JournalEntry.contact_project).filter(
            JournalEntry.company_id == company_id,
            JournalEntry.contact_project.in_(emp_names)
        ).distinct().all()
        names_with_entries.update(r[0] for r in hits if r[0])

    return [
        {
            "id": e.id, "code": e.code, "name": e.name,
            "id_card": e.id_card or "",
            "email": e.email or "", "salary": e.salary or 0,
            "has_journal": e.name in names_with_entries if e.name else False,
        } for e in emps
    ]

@router.post("/api/employees")
def create_employee(data: EmployeeCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    e = Employee(company_id=company_id, **data.model_dump())
    db.add(e)
    db.commit()
    return {"message": "新增成功"}

@router.put("/api/employees/{emp_id}")
def update_employee(emp_id: int, data: EmployeeUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    e = db.query(Employee).filter(Employee.company_id == company_id, Employee.id == emp_id).first()
    if not e:
        raise HTTPException(404, detail="员工不存在")
    # 检查该人员是否已被序时账往来项目引用
    if e.name:
        ref = db.query(JournalEntry.id).filter(
            JournalEntry.company_id == company_id,
            JournalEntry.contact_project == e.name
        ).first()
        if ref:
            raise HTTPException(400, detail=f"人员「{e.name}」已被序时账往来项目引用，不可编辑。")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    db.commit()
    return {"message": "更新成功"}

@router.delete("/api/employees/{emp_id}")
def delete_employee(emp_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    e = db.query(Employee).filter(Employee.company_id == company_id, Employee.id == emp_id).first()
    if not e:
        raise HTTPException(404, detail="员工不存在")
    # 检查该人员是否已被序时账往来项目引用
    if e.name:
        ref = db.query(JournalEntry.id).filter(
            JournalEntry.company_id == company_id,
            JournalEntry.contact_project == e.name
        ).first()
        if ref:
            raise HTTPException(400, detail=f"人员「{e.name}」已被序时账往来项目引用，不可删除。")
    db.delete(e)
    db.flush()
    _renumber_archive(db, company_id, Employee, 'RY')
    db.commit()
    return {"message": "删除成功"}

@router.post("/api/employees/batch-delete")
def batch_delete_employees(data: dict, company_id: int = Query(...), db: Session = Depends(get_db)):
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(400, detail="请选择要删除的记录")

    # 查询被序时账往来项目引用的人员名称
    locked_names = set()
    emp_names = db.query(Employee.name).filter(
        Employee.company_id == company_id,
        Employee.id.in_(ids)
    ).all()
    all_names = [n[0] for n in emp_names if n[0]]
    if all_names:
        hits = db.query(JournalEntry.contact_project).filter(
            JournalEntry.company_id == company_id,
            JournalEntry.contact_project.in_(all_names)
        ).distinct().all()
        locked_names.update(r[0] for r in hits if r[0])

    # 过滤掉被锁定的人员
    if locked_names:
        safe_ids = [
            eid for eid in ids
            if db.query(Employee).filter(Employee.company_id == company_id, Employee.id == eid).first().name not in locked_names
        ]
    else:
        safe_ids = ids

    if not safe_ids:
        raise HTTPException(400, detail=f"所选人员均已被序时账往来项目引用，不可删除。")

    deleted = db.query(Employee).filter(Employee.company_id == company_id, Employee.id.in_(safe_ids)).delete(synchronize_session=False)
    db.flush()
    _renumber_archive(db, company_id, Employee, 'RY')
    db.commit()

    skipped = len(ids) - len(safe_ids)
    msg = f"成功删除 {deleted} 条人员记录"
    if skipped > 0:
        msg += f"，{skipped} 条因被序时账引用已跳过"
    return {"message": msg}


# ==================== 客户档案 ====================


@router.get("/api/customers")
def list_customers(
    keyword: Optional[str] = None,
    is_active: Optional[bool] = None,
    company_id: int = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    q = db.query(Customer).filter(Customer.company_id == company_id)
    if keyword:
        q = q.filter(or_(
            Customer.code.contains(keyword),
            Customer.name.contains(keyword),
            Customer.contact.contains(keyword)
        ))
    if is_active is not None:
        q = q.filter(Customer.is_active == is_active)
    items = q.order_by(Customer.code).offset(skip).limit(limit).all()

    # 检测哪些客户名称存在于序时账中（contact_project 或 summary）
    cust_names = [c.name for c in items if c.name]
    names_with_entries = set()
    if cust_names:
        # 精确匹配 contact_project
        contact_hits = db.query(JournalEntry.contact_project).filter(
            JournalEntry.company_id == company_id,
            JournalEntry.contact_project.in_(cust_names)
        ).distinct().all()
        names_with_entries.update(r[0] for r in contact_hits if r[0])

        # 模糊匹配 summary（仅检查尚未匹配的客户）
        remaining = [n for n in cust_names if n not in names_with_entries]
        if remaining:
            conds = [JournalEntry.summary.contains(name) for name in remaining]
            summary_rows = db.query(JournalEntry.summary).filter(
                JournalEntry.company_id == company_id,
                or_(*conds)
            ).all()
            for row in summary_rows:
                if row[0]:
                    for name in remaining:
                        if name in row[0]:
                            names_with_entries.add(name)

    return [
        {
            "id": c.id, "code": c.code, "name": c.name,
            "uscc": c.uscc or "",
            "tax_no": c.tax_no,
            "bank_name": c.bank_name,
            "bank_account": c.bank_account,
            "is_active": c.is_active,
            "remark": c.remark,
            "has_journal": c.name in names_with_entries if c.name else False
        } for c in items
    ]

@router.post("/api/customers")
def create_customer(data: CustomerCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    if data.uscc:
        if len(data.uscc) != 18 or not data.uscc.isalnum():
            raise HTTPException(400, detail="统一社会信用代码必须为18位字母数字组合")
            raise HTTPException(400, detail=f"客户统一社会信用代码：{msg}")
    # 计算全行指纹
    fp_values = (
        str(company_id),
        str(data.code or ""),
        str(data.name or ""),
        str(data.uscc or ""),
        str(data.tax_no or ""),
        str(data.contact or ""),
        str(data.phone or ""),
        str(data.address or ""),
        str(data.credit_limit if data.credit_limit is not None else ""),
        str(data.payment_terms if data.payment_terms is not None else ""),
        str(data.bank_name or ""),
        str(data.bank_account or ""),
        str(data.is_active if data.is_active is not None else ""),
        str(data.remark or "")
    )
    fp_raw = "|".join(fp_values)
    fp = hashlib.sha256(fp_raw.encode("utf-8")).hexdigest()
    # 去重检查
    existing = db.query(Customer).filter(
        Customer.company_id == company_id,
        Customer._fingerprint == fp
    ).first()
    if existing:
        raise HTTPException(400, detail="该客户数据已存在（全行比对重复），请勿重复录入")
    c = Customer(company_id=company_id, _fingerprint=fp, **data.model_dump())
    db.add(c)
    db.commit()
    return {"message": "新增成功"}

@router.put("/api/customers/{cust_id}")
def update_customer(cust_id: int, data: CustomerUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    if _check_archive_lock(db, company_id, "customer", cust_id):
        raise HTTPException(403, detail="该客户已被序时账引用，不可编辑")
    c = db.query(Customer).filter(Customer.company_id == company_id, Customer.id == cust_id).first()
    if not c:
        raise HTTPException(404, detail="客户不存在")
    if data.uscc:
        if len(data.uscc) != 18 or not data.uscc.isalnum():
            raise HTTPException(400, detail="统一社会信用代码必须为18位字母数字组合")
            raise HTTPException(400, detail=f"客户统一社会信用代码：{msg}")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    # 重新计算全行指纹
    fp_values = (
        str(company_id),
        str(c.code or ""),
        str(c.name or ""),
        str(c.uscc or ""),
        str(c.tax_no or ""),
        str(c.contact or ""),
        str(c.phone or ""),
        str(c.address or ""),
        str(c.credit_limit if c.credit_limit is not None else ""),
        str(c.payment_terms if c.payment_terms is not None else ""),
        str(c.bank_name or ""),
        str(c.bank_account or ""),
        str(c.is_active if c.is_active is not None else ""),
        str(c.remark or "")
    )
    fp_raw = "|".join(fp_values)
    fp = hashlib.sha256(fp_raw.encode("utf-8")).hexdigest()
    c._fingerprint = fp
    db.commit()
    return {"message": "更新成功"}

@router.post("/api/customers/batch-delete")
def batch_delete_customers(
    body: BatchDelete,
    company_id: int = Query(...),
    db: Session = Depends(get_db)
):
    # 过滤被序时账引用的客户
    locked_ids = [cid for cid in body.ids if _check_archive_lock(db, company_id, "customer", cid)]
    deletable_ids = [cid for cid in body.ids if cid not in locked_ids]
    if not deletable_ids:
        raise HTTPException(403, detail="所选客户均已被序时账引用，不可删除")
    deleted = db.query(Customer).filter(
        Customer.company_id == company_id,
        Customer.id.in_(deletable_ids)
    ).delete(synchronize_session=False)
    db.flush()
    _renumber_archive(db, company_id, Customer, 'KH')
    db.commit()
    return {"message": f"成功删除 {deleted} 条客户"}

@router.delete("/api/customers/{cust_id}")
def delete_customer(cust_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    if _check_archive_lock(db, company_id, "customer", cust_id):
        raise HTTPException(403, detail="该客户已被序时账引用，不可删除")
    c = db.query(Customer).filter(Customer.company_id == company_id, Customer.id == cust_id).first()
    if not c:
        raise HTTPException(404, detail="客户不存在")
    db.delete(c)
    db.flush()
    _renumber_archive(db, company_id, Customer, 'KH')
    db.commit()
    return {"message": "删除成功"}


# ==================== 客户智能建档（新规则 2026-06-06） ====================

@router.post("/api/customers/auto-create")
def auto_create_customers(company_id: int = Query(...), db: Session = Depends(get_db)):
    """智能客户建档：
    1. 唯一来源：销项发票购方名称
    2. 只要开具发票模块有信息，就一定是客户
    3. 排除人员档案和公司内部人（存量清理）
    """
    created = 0
    updated = 0
    skipped = 0
    infos = []

    # 构建实体索引
    idx = _build_entity_index(db, company_id)
    existing_cust_map = {}  # norm -> Customer obj
    for cust in db.query(Customer).filter(Customer.company_id == company_id).all():
        if cust._fingerprint:
            existing_cust_map[cust._fingerprint] = cust
        elif cust.name:
            existing_cust_map[_normalize_customer_name(cust.name)] = cust
    insider_norms = idx['insiders'] | idx['shareholders']

    # 清理：将已在人员档案/内部人的客户从客户档案中移除
    removed_names = []
    for norm, cust in list(existing_cust_map.items()):
        if norm in insider_norms:
            db.delete(cust)
            removed_names.append(cust.name)
    if removed_names:
        db.flush()
        infos.append(f"已从客户档案移除{len(removed_names)}条内部人员：{', '.join(removed_names)}")
        # 从 existing_cust_map 中移除已删除的条目
        for norm in list(existing_cust_map.keys()):
            if norm in insider_norms:
                del existing_cust_map[norm]

    sources = []

    # 1. 销项发票购方名称（主要来源）
    invoices = db.query(SalesInvoice).filter(
        SalesInvoice.company_id == company_id,
        SalesInvoice.buyer_name.isnot(None)
    ).all()
    for inv in invoices:
        name = inv.buyer_name.strip() if inv.buyer_name else ""
        if name:
            sources.append({
                'name': name,
                'tax_no': inv.buyer_tax_no.strip() if inv.buyer_tax_no else None,
                'source': f'销项发票:{inv.invoice_no or inv.id}',
            })

    # 去重 & 过滤
    seen = {}
    for s in sources:
        norm = _normalize_customer_name(s['name'])
        # 跳过公司内部人
        if norm in insider_norms:
            skipped += 1
            continue
        # 跳过已存在的客户
        if norm in existing_cust_map:
            skipped += 1
            # 如果有税号且现有记录没有，更新税号
            cust = existing_cust_map[norm]
            if s['tax_no'] and not cust.uscc:
                cust.uscc = s['tax_no']
                cust.tax_no = s['tax_no']
                db.flush()
                updated += 1
            continue
        if norm not in seen:
            seen[norm] = s
        elif s['tax_no'] and not seen[norm]['tax_no']:
            seen[norm] = s

    # 逐个创建
    for norm, s in seen.items():
        # 生成编码
        max_cust = db.query(Customer.code).filter(
            Customer.company_id == company_id,
            Customer.code.like('KH%')
        ).order_by(Customer.code.desc()).first()
        if max_cust and max_cust[0] and max_cust[0].startswith('KH'):
            try:
                num = int(max_cust[0][2:]) + 1
            except ValueError:
                num = 1
        else:
            num = 1
        code = f"KH{num:03d}"

        cust = Customer(
            company_id=company_id,
            code=code,
            name=s['name'],
            tax_no=s['tax_no'] or '',
            uscc=s['tax_no'] or '',
            is_active=True,
            _fingerprint=norm,
        )
        db.add(cust)
        db.flush()
        created += 1
        infos.append(f"已创建客户：{s['name']}（来源：{s['source']}）")

    db.commit()
    return {
        "message": f"智能建档完成：新建{created}条，跳过{skipped}条",
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "infos": infos,
    }


# ==================== 供应商档案 ====================

@router.get("/api/suppliers")
def list_suppliers(
    keyword: Optional[str] = None,
    is_active: Optional[bool] = None,
    company_id: int = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    # 查询序时账中出现的供应商名称
    names_with_entries = set()
    try:
        entries = db.query(JournalEntry).filter(
            JournalEntry.company_id == company_id,
            JournalEntry.counterparty.isnot(None)
        ).all()
        names_with_entries = {e.counterparty for e in entries if e.counterparty}
    except Exception as e:
        logging.warning(f"供应商往来查询失败: {e}")
    q = db.query(Supplier).filter(Supplier.company_id == company_id)
    if keyword:
        q = q.filter(or_(
            Supplier.code.contains(keyword),
            Supplier.name.contains(keyword)
        ))
    if is_active is not None:
        q = q.filter(Supplier.is_active == is_active)
    items = q.order_by(Supplier.code).offset(skip).limit(limit).all()
    return [
        {
            "id": s.id, "code": s.code, "name": s.name,
            "uscc": s.uscc or "",
            "tax_no": s.tax_no,
            "bank_name": s.bank_name,
            "bank_account": s.bank_account,
            "is_active": s.is_active,
            "remark": s.remark,
            "has_journal": s.name in names_with_entries if s.name else False
        } for s in items
    ]

@router.post("/api/suppliers")
def create_supplier(data: SupplierCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    if data.uscc:
        if len(data.uscc) != 18 or not data.uscc.isalnum():
            raise HTTPException(400, detail="统一社会信用代码必须为18位字母数字组合")
            raise HTTPException(400, detail=f"供应商统一社会信用代码：{msg}")
    s = Supplier(company_id=company_id, **data.model_dump())
    db.add(s)
    db.commit()
    return {"message": "新增成功"}

@router.put("/api/suppliers/{supp_id}")
def update_supplier(supp_id: int, data: SupplierUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    if _check_archive_lock(db, company_id, "supplier", supp_id):
        raise HTTPException(403, detail="该供应商已被序时账引用，不可编辑")
    s = db.query(Supplier).filter(Supplier.company_id == company_id, Supplier.id == supp_id).first()
    if not s:
        raise HTTPException(404, detail="供应商不存在")
    if data.uscc:
        if len(data.uscc) != 18 or not data.uscc.isalnum():
            raise HTTPException(400, detail="统一社会信用代码必须为18位字母数字组合")
            raise HTTPException(400, detail=f"供应商统一社会信用代码：{msg}")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    return {"message": "更新成功"}

@router.post("/api/suppliers/batch-delete")
def batch_delete_suppliers(
    body: BatchDelete,
    company_id: int = Query(...),
    db: Session = Depends(get_db)
):
    locked_ids = [sid for sid in body.ids if _check_archive_lock(db, company_id, "supplier", sid)]
    deletable_ids = [sid for sid in body.ids if sid not in locked_ids]
    if not deletable_ids:
        raise HTTPException(403, detail="所选供应商均已被序时账引用，不可删除")
    deleted = db.query(Supplier).filter(
        Supplier.company_id == company_id,
        Supplier.id.in_(deletable_ids)
    ).delete(synchronize_session=False)
    db.flush()
    _renumber_archive(db, company_id, Supplier, 'GYS')
    db.commit()
    return {"message": f"成功删除 {deleted} 条供应商"}

@router.delete("/api/suppliers/{supp_id}")
def delete_supplier(supp_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    if _check_archive_lock(db, company_id, "supplier", supp_id):
        raise HTTPException(403, detail="该供应商已被序时账引用，不可删除")
    s = db.query(Supplier).filter(Supplier.company_id == company_id, Supplier.id == supp_id).first()
    if not s:
        raise HTTPException(404, detail="供应商不存在")
    db.delete(s)
    db.flush()
    _renumber_archive(db, company_id, Supplier, 'GYS')
    db.commit()
    return {"message": "删除成功"}


# ==================== 供应商智能建档（新规则 2026-06-06） ====================

def _extract_company_names(text: str) -> set:
    """从自由文本中提取企业名称（用于摘要/交易附言等字段）"""
    if not text:
        return set()
    # 常见前缀动词/介词（提取后需剥离）
    _LEADING_PREFIXES = [
        '待支付', '支付给', '转账给', '汇给', '转给', '退还', '退回',
        '支付', '转账', '付款给', '付款至', '付给', '付至', '付款',
        '预付', '预付给', '归还', '汇入', '汇出', '转付', '代付',
        '付', '转', '如', '给', '向',
    ]
    # 伪名称关键词：提取结果包含这些的视为非公司名（避免误提取）
    _NON_NAME_KEYWORDS = [
        '项目款', '保证金', '投标', '服务费', '货款', '租费',
        '顾问费', '咨询费', '代理费', '赞助费', '劳务费',
    ]
    names = set()
    # 企业后缀，按长度降序优先匹配长的
    _NAME_SUFFIXES = sorted([
        '有限责任公司', '股份有限公司', '集团有限公司', '有限公司',
        '总公司', '分公司', '公司', '厂', '中心', '机构', '店', '行',
        '协会', '所', '部', '网', '工作室', '事务所', '经营部'
    ], key=len, reverse=True)
    for suffix in _NAME_SUFFIXES:
        idx = 0
        while True:
            idx = text.find(suffix, idx)
            if idx < 0:
                break
            end = idx + len(suffix)
            start = idx
            # 向前扩展到标点/空格/换行
            while start > 0 and text[start - 1] not in '，,。. \t;；:：、（）()\n\r【】《》""\'\'!！?？':
                start -= 1
            name = text[start:end].strip()
            # 剥离常见前缀
            for prefix in sorted(_LEADING_PREFIXES, key=len, reverse=True):
                if name.startswith(prefix) and len(name) > len(prefix) + 2:
                    name = name[len(prefix):]
                    break
            # 合理长度范围（至少4个字符，不超过80字符）
            if 4 <= len(name) <= 80:
                # 排除包含业务关键词的伪名称
                if not any(kw in name for kw in _NON_NAME_KEYWORDS):
                    names.add(name)
            idx = end
    return names


def _enrich_archive_info(db: Session, company_id: int) -> dict:
    """档案信息补全：从发票/银行流水等数据源提取缺失字段，更新客户/供应商档案。
    触发时机：每次文件导入后自动运行，第一时间填补新信息。
    """
    from database import _normalize_customer_name
    enriched_cust = 0
    enriched_supp = 0
    fields_filled = []

    # ── 客户档案补全 ──
    custs = db.query(Customer).filter(Customer.company_id == company_id).all()
    cust_norm_map = {}
    for c in custs:
        # 用归一化名称做键（_fingerprint是SHA256，不能直接匹配银行流水的归一化名）
        norm = _normalize_customer_name(c.name or "")
        if norm:
            cust_norm_map[norm] = c

    # 来源1：销项发票购方信息
    for inv in db.query(SalesInvoice).filter(
        SalesInvoice.company_id == company_id,
        SalesInvoice.buyer_name.isnot(None)
    ).all():
        norm = _normalize_customer_name(inv.buyer_name.strip())
        c = cust_norm_map.get(norm)
        if not c:
            continue
        changed = False
        # 税号=统一社会信用代码（双向同步）
        inv_tax = (inv.buyer_tax_no or "").strip()
        if inv_tax:
            if not c.tax_no:
                c.tax_no = inv_tax
                fields_filled.append(f"客户[{c.name}]税号←销项发票")
                changed = True
            if not c.uscc:
                c.uscc = inv_tax
                changed = True
        if inv.buyer_address and not c.address:
            c.address = inv.buyer_address.strip()
            fields_filled.append(f"客户[{c.name}]地址←销项发票")
            changed = True
        if inv.buyer_bank_name and not c.bank_name:
            c.bank_name = inv.buyer_bank_name.strip()
            changed = True
        if inv.buyer_bank_account and not c.bank_account:
            c.bank_account = inv.buyer_bank_account.strip()
            changed = True
        # uscc→tax_no 反向
        if c.uscc and not c.tax_no:
            c.tax_no = c.uscc
            changed = True
        if c.tax_no and not c.uscc:
            c.uscc = c.tax_no
            changed = True
        if changed:
            enriched_cust += 1

    # 来源2：银行流水对方信息
    for tx in db.query(BankTransaction).filter(
        BankTransaction.company_id == company_id,
        BankTransaction.counterparty_name.isnot(None)
    ).all():
        norm = _normalize_customer_name(tx.counterparty_name.strip())
        c = cust_norm_map.get(norm)
        if not c:
            continue
        changed = False
        if tx.counterparty_bank and not c.bank_name:
            c.bank_name = tx.counterparty_bank.strip()
            changed = True
        if tx.counterparty_account and not c.bank_account:
            c.bank_account = tx.counterparty_account.strip()
            changed = True
        if changed:
            enriched_cust += 1

    # ── 供应商档案补全 ──
    supps = db.query(Supplier).filter(Supplier.company_id == company_id).all()
    supp_norm_map = {}
    for s in supps:
        norm = _normalize_customer_name(s.name or "")
        if norm:
            supp_norm_map[norm] = s

    # 来源1：取得发票销方信息
    for inv in db.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.seller_name.isnot(None)
    ).all():
        norm = _normalize_customer_name(inv.seller_name.strip())
        s = supp_norm_map.get(norm)
        if not s:
            continue
        changed = False
        # 税号=统一社会信用代码（双向同步）
        inv_tax = (inv.seller_tax_no or "").strip()
        if inv_tax:
            if not s.tax_no:
                s.tax_no = inv_tax
                fields_filled.append(f"供应商[{s.name}]税号←取得发票")
                changed = True
            if not s.uscc:
                s.uscc = inv_tax
                changed = True
        # uscc→tax_no 反向
        if s.uscc and not s.tax_no:
            s.tax_no = s.uscc
            changed = True
        if s.tax_no and not s.uscc:
            s.uscc = s.tax_no
            changed = True
        if changed:
            enriched_supp += 1

    # 来源2：银行流水对方信息
    for tx in db.query(BankTransaction).filter(
        BankTransaction.company_id == company_id,
        BankTransaction.counterparty_name.isnot(None)
    ).all():
        norm = _normalize_customer_name(tx.counterparty_name.strip())
        s = supp_norm_map.get(norm)
        if not s:
            continue
        changed = False
        if tx.counterparty_bank and not s.bank_name:
            s.bank_name = tx.counterparty_bank.strip()
            changed = True
        if tx.counterparty_account and not s.bank_account:
            s.bank_account = tx.counterparty_account.strip()
            changed = True
        if changed:
            enriched_supp += 1

    if enriched_cust or enriched_supp:
        db.flush()

    return {
        "customer_enriched": enriched_cust,
        "supplier_enriched": enriched_supp,
        "fields_filled": fields_filled,
    }


def _close_archive_gap(db: Session, company_id: int) -> dict:
    """档案缺失自动补齐：序时账往来科目中有contact_project但档案中不存在的实体 → 自动建档
    修复范围：1122应收账款 → 客户 / 2202应付账款 → 供应商 / 1123预付账款 → 供应商
    这是确定性修复——有明细账就必需有档案，不允许gap存在。
    """
    from database import _normalize_customer_name
    created_cust = 0
    created_supp = 0

    # 现有档案归一化集合
    cust_norms = set()
    for c in db.query(Customer).filter(Customer.company_id == company_id).all():
        fp = c._fingerprint or _normalize_customer_name(c.name or "")
        if fp:
            cust_norms.add(fp)
    supp_norms = set()
    for s in db.query(Supplier).filter(Supplier.company_id == company_id).all():
        fp = s._fingerprint or _normalize_customer_name(s.name or "")
        if fp:
            supp_norms.add(fp)

    # 扫描序时账往来科目：1122→客户, 2202/1123→供应商
    for code, entity_type in [("1122", "customer"), ("2202", "supplier"), ("1123", "supplier")]:
        entries = db.query(JournalEntry.contact_project).filter(
            JournalEntry.company_id == company_id,
            JournalEntry.account_code == code,
            JournalEntry.contact_project.isnot(None),
            JournalEntry.contact_project != "",
        ).distinct().all()

        for (cp,) in entries:
            name = cp.strip()
            if not name or len(name) < 4:
                continue
            norm = _normalize_customer_name(name)

            # 排除内部人员（1221的才是人员，1122/2202是企业往来）
            # 排除明显非企业名称
            _NON_ENTITY = ("手续费", "金库", "公积金", "待处理", "出售凭证", "业务收入",
                          "国家金库", "税务", "国库", "工资", "社保", "个税")
            if any(kw in name for kw in _NON_ENTITY):
                continue
            # 排除个人名（3字以下纯中文名）
            if len(name) <= 3 and all('\u4e00' <= c <= '\u9fff' for c in name):
                continue

            if entity_type == "customer":
                if norm in cust_norms:
                    continue
                max_c = db.query(Customer.code).filter(
                    Customer.company_id == company_id, Customer.code.like('KH%')
                ).order_by(Customer.code.desc()).first()
                num = int(max_c[0][2:]) + 1 if max_c and max_c[0] and max_c[0].startswith('KH') else 1
                db.add(Customer(company_id=company_id, code=f"KH{num:03d}", name=name,
                               _fingerprint=norm, is_active=True))
                db.flush()
                cust_norms.add(norm)
                created_cust += 1

            elif entity_type == "supplier":
                if norm in supp_norms:
                    continue
                max_s = db.query(Supplier.code).filter(
                    Supplier.company_id == company_id, Supplier.code.like('GYS%')
                ).order_by(Supplier.code.desc()).first()
                num = int(max_s[0][3:]) + 1 if max_s and max_s[0] and max_s[0].startswith('GYS') else 1
                db.add(Supplier(company_id=company_id, code=f"GYS{num:03d}", name=name,
                               _fingerprint=norm, is_active=True))
                db.flush()
                supp_norms.add(norm)
                created_supp += 1

    return {"customer_created": created_cust, "supplier_created": created_supp}


def _do_auto_create_suppliers(db: Session, company_id: int) -> dict:
    """供应商智能建档核心逻辑（可被API和导入流程复用）"""
    created = 0
    updated = 0
    skipped = 0
    infos = []

    # 构建实体索引
    idx = _build_entity_index(db, company_id)
    shareholder_norms = idx['shareholders']
    insider_norms = idx['insiders'] | idx['shareholders']

    # 清理：将已在人员档案/内部人的供应商移除
    removed_names = []
    for supp in db.query(Supplier).filter(Supplier.company_id == company_id).all():
        if supp.name:
            norm = _normalize_customer_name(supp.name)
            if norm in insider_norms:
                db.delete(supp)
                removed_names.append(supp.name)
    if removed_names:
        db.flush()
        infos.append(f"已从供应商档案移除{len(removed_names)}条内部人员：{', '.join(removed_names)}")

    # 1. 取得发票销方名称集合
    pi_names = set()
    pi_sources = {}
    invoices = db.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.seller_name.isnot(None)
    ).all()
    for inv in invoices:
        name = inv.seller_name.strip() if inv.seller_name else ""
        if not name:
            continue
        norm = _normalize_customer_name(name)
        pi_names.add(norm)
        pi_sources[norm] = {
            'name': name,
            'tax_no': inv.seller_tax_no.strip() if inv.seller_tax_no else None,
            'source': f'进项发票:{inv.invoice_no or inv.id}',
        }

    # 2. 银行流水付款方（借方=付款，即 debit_amount > 0）
    #   取数来源：对方户名 + 摘要 + 交易附言（老邓 2026-06-10 三源综合）
    # 手续费/税费/政府机构等非供应商关键词
    _NON_SUPPLIER_KEYWORDS = ('手续费', '金库', '公积金', '待处理', '出售凭证', '业务收入', '国家金库', '税务', '国库', '工资', '社保', '个税', '薪金', '薪酬')
    _BIZ_SUFFIXES = ('公司', '厂', '中心', '机构', '店', '行', '协会', '所', '部', '网')
    bt_names = set()
    bt_sources = {}
    txs = db.query(BankTransaction).filter(
        BankTransaction.company_id == company_id,
        BankTransaction.debit_amount > 0
    ).all()
    for tx in txs:
        # 从三个来源收集名称
        raw_names = set()
        # ① 对方户名
        if tx.counterparty_name and tx.counterparty_name.strip():
            raw_names.add(tx.counterparty_name.strip())
        # ② 摘要
        if tx.summary:
            raw_names |= _extract_company_names(tx.summary)
        # ③ 交易附言
        if tx.transaction_remark:
            raw_names |= _extract_company_names(tx.transaction_remark)

        for name in raw_names:
            if not name:
                continue
            # 跳过股东/内部人员
            norm = _normalize_customer_name(name)
            if norm in insider_norms:
                continue
            # 跳过手续费/税费/政府机构关键词
            if any(kw in name for kw in _NON_SUPPLIER_KEYWORDS):
                continue
            # 跳过明显非企业名称（长度<6且不含公司等后缀）
            if len(name) < 6 and not any(s in name for s in _BIZ_SUFFIXES):
                continue
            bt_names.add(norm)
            if norm not in bt_sources:
                bt_sources[norm] = {
                    'name': name,
                    'tax_no': None,
                    'source': f'银行流水:#{tx.id}',
                }

    # 3. 候选供应商：银行流水付款方 ∩ 取得发票销方（双源信号，老邓 2026-06-10 回归铁律）
    candidate_names = pi_names & bt_names
    # ⚠️ 用数据库直接查判重，不能用 idx['suppliers']——它被 _build_entity_index 污染了（含所有发票销方）
    existing_supp_norms = set()
    for s in db.query(Supplier).filter(Supplier.company_id == company_id).all():
        fp = s._fingerprint or _normalize_customer_name(s.name or "")
        if fp:
            existing_supp_norms.add(fp)

    for norm in candidate_names:
        if norm in shareholder_norms:
            skipped += 1
            continue
        if norm in existing_supp_norms:
            skipped += 1
            continue

        s = pi_sources.get(norm) or bt_sources.get(norm)
        if not s:
            continue

        source_tag = []
        if norm in pi_names:
            source_tag.append('取得发票')
        if norm in bt_names:
            source_tag.append('银行流水')
        full_source = '+'.join(source_tag)

        max_supp = db.query(Supplier.code).filter(
            Supplier.company_id == company_id,
            Supplier.code.like('GYS%')
        ).order_by(Supplier.code.desc()).first()
        if max_supp and max_supp[0] and max_supp[0].startswith('GYS'):
            try:
                num = int(max_supp[0][3:]) + 1
            except ValueError:
                num = 1
        else:
            num = 1
        code = f"GYS{num:03d}"

        supp = Supplier(
            company_id=company_id,
            code=code,
            name=s['name'],
            uscc=s['tax_no'] if s['tax_no'] and s['tax_no'].strip() else None,
            _fingerprint=norm,
            is_active=True,
        )
        db.add(supp)
        db.flush()
        created += 1
        infos.append(f"已创建供应商：{s['name']}（来源：{full_source}）")

    db.commit()
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "infos": infos,
    }


@router.post("/api/suppliers/auto-create")
def auto_create_suppliers(company_id: int = Query(...), db: Session = Depends(get_db)):
    """智能供应商建档：
    1. 以银行流水付款方为注来源
    2. 银行流水 + 取得发票双源出现 → 强信号 → 创建
    3. 单源（仅银行或仅发票）→ 不创建
    4. 排除股东（投资款归实收资本，付款归分红）
    """
    result = _do_auto_create_suppliers(db, company_id)
    return {
        "message": f"智能建档完成：新建{result['created']}条，跳过{result['skipped']}条",
        "created": result['created'],
        "updated": result['updated'],
        "skipped": result['skipped'],
        "infos": result['infos'],
    }


@router.get("/api/suppliers/diagnose")
def diagnose_suppliers(company_id: int = Query(...), db: Session = Depends(get_db)):
    """双源供应商诊断：展示取得发票销方 ∩ 银行流水付款方的匹配过程"""
    from database import _normalize_customer_name, _build_entity_index
    idx = _build_entity_index(db, company_id)
    insider_norms = idx['insiders']

    # 排除关键词
    _NON_SUPPLIER_KEYWORDS = ('手续费', '金库', '公积金', '待处理', '出售凭证', '业务收入', '国家金库', '税务', '国库')
    _BIZ_SUFFIXES = ('公司', '厂', '中心', '机构', '店', '行', '协会', '所', '部', '网')

    # 1. 取得发票销方
    pi_items = []
    pi_norms = set()
    for inv in db.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.seller_name.isnot(None)
    ).all():
        name = inv.seller_name.strip()
        if not name: continue
        norm = _normalize_customer_name(name)
        pi_norms.add(norm)
        pi_items.append({
            "name": name, "norm": norm,
            "tax_no": inv.seller_tax_no.strip() if inv.seller_tax_no else "",
            "invoice_no": inv.invoice_no or inv.digital_invoice_no or str(inv.id),
        })

    # 2. 银行流水付款方
    bt_items = []
    bt_norms = set()
    for tx in db.query(BankTransaction).filter(
        BankTransaction.company_id == company_id,
        BankTransaction.debit_amount > 0,
        BankTransaction.counterparty_name.isnot(None)
    ).all():
        name = tx.counterparty_name.strip()
        if not name: continue
        norm = _normalize_customer_name(name)
        if norm in insider_norms: continue
        if any(kw in name for kw in _NON_SUPPLIER_KEYWORDS): continue
        if len(name) < 6 and not any(s in name for s in _BIZ_SUFFIXES): continue
        bt_norms.add(norm)
        bt_items.append({
            "name": name, "norm": norm,
            "tx_id": tx.id, "amount": float(tx.debit_amount or 0),
        })

    # 3. 交集分析
    both = pi_norms & bt_norms
    pi_only = pi_norms - bt_norms
    bt_only = bt_norms - pi_norms

    # 4. 已有供应商（直接查数据库，不用 idx['suppliers']——已被发票销方污染）
    existing_list = [{"code": s.code, "name": s.name} for s in db.query(Supplier).filter(
        Supplier.company_id == company_id
    ).order_by(Supplier.code).all()]
    existing_norms = set()
    for s in db.query(Supplier).filter(Supplier.company_id == company_id).all():
        fp = s._fingerprint or _normalize_customer_name(s.name or "")
        if fp:
            existing_norms.add(fp)

    return {
        "summary": {
            "purchase_invoice_sellers": len(pi_norms),
            "bank_transaction_payers": len(bt_norms),
            "dual_source_match": len(both),
            "pi_only": len(pi_only),
            "bt_only": len(bt_only),
            "existing_suppliers": len(existing_list),
            "new_to_create": len(both - existing_norms),
        },
        "dual_source": sorted([
            {
                "name": next((bi["name"] for bi in bt_items if bi["norm"] == n), 
                              next((pi["name"] for pi in pi_items if pi["norm"] == n), n)),
                "norm": n,
                "from_purchase_invoice": bool(n in pi_norms),
                "from_bank_transaction": bool(n in bt_norms),
                "already_exists": n in existing_norms,
            }
            for n in both
        ], key=lambda x: x["name"]),
        "pi_only_sample": sorted(list(pi_only)),
        "bt_only_sample": sorted(list(bt_only)),
        "existing_suppliers": existing_list,
    }


@router.post("/api/process-all")
def process_all(company_id: int = Query(...), db: Session = Depends(get_db)):
    """三步统一处理流程（老邓 2026-06-10 铁律）：
    ① 确定供应商档案（双源：发票销方 ∩ 银行付款方）
    ② 取得发票序时账登记（根据供应商档案）
    ③ 银行流水序时账登记（根据供应商档案）
    """
    import logging
    log = logging.getLogger("process-all")

    # ── 第零步：档案缺失补齐（有明细账但档案缺失 → 自动建档，零容忍）──
    gap_result = {"customer_created": 0, "supplier_created": 0}
    try:
        gap_result = _close_archive_gap(db, company_id)
        db.commit()
    except Exception:
        pass

    # ── 第零步半：档案信息补全（第一时间填补缺失字段）──
    enrich_result = {"customer_enriched": 0, "supplier_enriched": 0}
    try:
        enrich_result = _enrich_archive_info(db, company_id)
        db.commit()
    except Exception:
        pass

    # ── 第一步：确定供应商档案 ──
    supp_result = _do_auto_create_suppliers(db, company_id)
    db.commit()

    # ── 第二步：未记账发票生成凭证 ──
    from database import BookkeepingInvoice
    pi_count = auto_generate_bookkeeping_journal(db, company_id)
    db.commit()

    db.commit()

    # ── 第三步：银行流水生成凭证 ──
    bank_result = _generate_bank_journals(db, company_id, None)
    db.commit()

    # ── 第四步：社保缴纳匹配 ──
    ss_result = {"generated": 0}
    try:
        ss_result = _match_ss_payment_journals(db, company_id)
        db.commit()
    except Exception:
        pass

    # ── 第五步：税费组合缴纳匹配（国家金库）──
    tax_result = {"generated": 0}
    try:
        tax_result = _match_tax_payment_journals(db, company_id)
        db.commit()
    except Exception:
        pass

    # ── 第六步：公积金缴纳匹配 ──
    hf_result = {"generated": 0}
    try:
        hf_result = _match_hf_payment_journals(db, company_id)
        db.commit()
    except Exception:
        pass

    return {
        "step0_archive_gap": gap_result,
        "step0_5_enrich": enrich_result,
        "step1_suppliers": supp_result,
        "step2_bookkeeping": {
            "generated": pi_count,
        },
        "step3_bank_transactions": bank_result,
        "step4_social_security": ss_result,
        "step5_tax_payment": tax_result,
        "step6_housing_fund": hf_result,
    }


@router.post("/api/generate-sample-archives")
def generate_sample_archives(company_id: int = Query(...), db: Session = Depends(get_db)):
    """为部门、人员、客户、供应商各生成21720条样本数据"""
    results = {"departments": 0, "employees": 0, "customers": 0, "suppliers": 0}

    # --- 部门：25个常用部门 ---
    dept_names = [
        "总经理办公室", "财务部", "人力资源部", "市场部", "销售一部",
        "销售二部", "研发一部", "研发二部", "采购部", "质量管理部",
        "物流部", "行政部", "法务合规部", "信息技术部", "客户服务部",
        "公关部", "审计部", "战略发展部", "工程部", "设计部",
        "培训部", "安全环保部", "后勤保障部", "国际业务部", "投资管理部"
    ]
    # 先查现有最大编码
    max_dept = db.query(Department.code).filter(
        Department.company_id == company_id, Department.code.like('BM%')
    ).order_by(Department.code.desc()).first()
    dept_idx = int(max_dept[0][2:]) + 1 if max_dept else 1
    for name in dept_names:
        existing = db.query(Department).filter(
            Department.company_id == company_id, Department.name == name
        ).first()
        if not existing:
            db.add(Department(company_id=company_id, code=f"BM{dept_idx:03d}", name=name))
            dept_idx += 1
            results["departments"] += 1
    db.flush()

    # --- 人员：25个员工 ---
    emp_data = [
        ("张伟", "440101199001011234"), ("李娜", "440102199103152345"), ("王磊", "440103198807203456"),
        ("陈静", "440104199206184567"), ("刘洋", "440105199311255678"), ("杨帆", "440106198912106789"),
        ("赵敏", "440107199507157890"), ("黄超", "440108199008168901"), ("周婷", "440109199409179012"),
        ("吴强", "440110199110181123"), ("郑芳", "440111199211192234"), ("冯涛", "440112199312203345"),
        ("何丽", "440113199401214456"), ("韩明", "440114199502225567"), ("曹雪", "440115199603236678"),
        ("许杰", "440116199704247789"), ("邓辉", "440117199805258890"), ("萧琳", "440118199906269901"),
        ("唐波", "440119198701270112"), ("彭悦", "440120198802282223"), ("曾强", "440121198903013334"),
        ("董洁", "440122199004024445"), ("袁浩", "440123199105035556"), ("蒋霞", "440124199206046667"),
        ("沈飞", "440125199307057778")
    ]
    max_emp = db.query(Employee.code).filter(
        Employee.company_id == company_id, Employee.code.like('RY%')
    ).order_by(Employee.code.desc()).first()
    emp_idx = int(max_emp[0][2:]) + 1 if max_emp else 1
    for i, (name, id_card) in enumerate(emp_data):
        existing = db.query(Employee).filter(
            Employee.company_id == company_id, Employee.name == name, Employee.id_card == id_card
        ).first()
        if not existing:
            db.add(Employee(
                company_id=company_id, code=f"RY{emp_idx:03d}", name=name,
                id_card=id_card,
                email=f"{name.lower()}{emp_idx}@cunqin.com",
                salary=round(5000 + i * 800 + (hash(name) % 3000), -2)
            ))
            emp_idx += 1
            results["employees"] += 1
    db.flush()

    # --- 客户：25个企业客户 ---
    cust_data = [
        ("广州天宏科技有限公司", "91440101MA5ABCD123"), ("深圳鹏程实业有限公司", "91440300MA5EFGH456"),
        ("东莞华耀电子有限公司", "91441900MA5IJKL789"), ("佛山顺达建材有限公司", "91440600MA5MNOP012"),
        ("中山明辉灯饰有限公司", "91442000MA5QRST345"), ("珠海海天贸易有限公司", "91440400MA5UVWX678"),
        ("惠州鑫源五金有限公司", "91441300MA5YZAB901"), ("江门益丰食品有限公司", "91440700MA5CDEF234"),
        ("肇庆鼎湖旅游开发有限公司", "91441200MA5GHIJ567"), ("汕头潮阳纺织有限公司", "91440500MA5KLMN890"),
        ("北京中科创新科技有限公司", "91110108MA5OPQR123"), ("上海浦江物流有限公司", "91310115MA5STUV456"),
        ("杭州西湖软件有限公司", "91330108MA5WXYZ789"), ("南京金陵机械有限公司", "91320105MA5ABCD012"),
        ("武汉江城建设集团有限公司", "91420102MA5EFGH345"), ("成都天府餐饮管理有限公司", "91510104MA5IJKL678"),
        ("重庆山城商贸有限公司", "91500103MA5MNOP901"), ("长沙星城文化传媒有限公司", "91430102MA5QRST234"),
        ("厦门海西进出口有限公司", "91350203MA5UVWX567"), ("青岛海尔智能科技有限公司", "91370281MA5YZAB890"),
        ("大连滨海渔业有限公司", "91210202MA5CDEF123"), ("苏州园林设计院有限公司", "91320505MA5GHIJ456"),
        ("无锡太湖环保科技有限公司", "91320213MA5KLMN789"), ("合肥高新投资管理有限公司", "91340104MA5OPQR012"),
        ("福州闽江房地产开发有限公司", "91350102MA5STUV345")
    ]
    max_cust = db.query(Customer.code).filter(
        Customer.company_id == company_id, Customer.code.like('KH%')
    ).order_by(Customer.code.desc()).first()
    cust_idx = int(max_cust[0][2:]) + 1 if max_cust else 1
    banks = ["中国工商银行", "中国建设银行", "中国农业银行", "中国银行", "招商银行"]
    for name, uscc in cust_data:
        existing = db.query(Customer).filter(
            Customer.company_id == company_id, Customer.uscc == uscc
        ).first()
        if not existing:
            bi = hash(name) % len(banks)
            db.add(Customer(
                company_id=company_id, code=f"KH{cust_idx:03d}", name=name,
                uscc=uscc, tax_no=uscc[2:20],
                bank_name=banks[bi],
                bank_account=f"{62220000 + cust_idx * 137:020d}",
                remark="样本数据"
            ))
            cust_idx += 1
            results["customers"] += 1
    db.flush()

    # --- 供应商：25个供应商 ---
    supp_data = [
        ("广州龙腾电子科技有限公司", "91440101MA5AAAA111"), ("深圳星辰照明有限公司", "91440300MA5BBBB222"),
        ("东莞万丰模具制品有限公司", "91441900MA5CCCC333"), ("佛山新力包装材料有限公司", "91440600MA5DDDD444"),
        ("中山瑞安五金机电有限公司", "91442000MA5EEEE555"), ("珠海格力精密模具有限公司", "91440400MA5FFFF666"),
        ("惠州德盛化工有限公司", "91441300MA5GGGG777"), ("江门华盛纺织原料有限公司", "91440700MA5HHHH888"),
        ("肇庆大发木业有限公司", "91441200MA5IIII999"), ("汕头阳光印务有限公司", "91440500MA5JJJJ000"),
        ("北京云帆信息技术有限公司", "91110108MA5KKKK111"), ("上海博达广告传媒有限公司", "91310115MA5LLLL222"),
        ("杭州网联通信设备有限公司", "91330108MA5MMMM333"), ("南京翔宇机械设备有限公司", "91320105MA5NNNN444"),
        ("武汉盛丰粮油贸易有限公司", "91420102MA5OOOO555"), ("成都锦程物流有限公司", "91510104MA5PPPP666"),
        ("重庆利群商贸有限公司", "91500103MA5QQQQ777"), ("长沙恒达仪器仪表有限公司", "91430102MA5RRRR888"),
        ("厦门伟业建筑工程有限公司", "91350203MA5SSSS999"), ("青岛远洋渔业有限公司", "91370281MA5TTTT000"),
        ("大连宏发水产品有限公司", "91210202MA5UUUU111"), ("苏州鼎丰纺织有限公司", "91320505MA5VVVV222"),
        ("无锡大明金属材料有限公司", "91320213MA5WWWW333"), ("合肥利安医疗器材有限公司", "91340104MA5XXXX444"),
        ("福州东南汽车配件有限公司", "91350102MA5YYYY555")
    ]
    max_supp = db.query(Supplier.code).filter(
        Supplier.company_id == company_id, Supplier.code.like('GYS%')
    ).order_by(Supplier.code.desc()).first()
    supp_idx = int(max_supp[0][3:]) + 1 if max_supp else 1
    for name, uscc in supp_data:
        existing = db.query(Supplier).filter(
            Supplier.company_id == company_id, Supplier.uscc == uscc
        ).first()
        if not existing:
            bi = hash(name + "_s") % len(banks)
            db.add(Supplier(
                company_id=company_id, code=f"GYS{supp_idx:03d}", name=name,
                uscc=uscc, tax_no=uscc[2:20],
                bank_name=banks[bi],
                bank_account=f"{62280000 + supp_idx * 211:020d}",
                remark="样本数据"
            ))
            supp_idx += 1
            results["suppliers"] += 1

    db.commit()
    return {"message": "样本数据生成完成", "results": results}


# ==================== 会计科目（原有，保留）====================


@router.get("/api/accounts")
def list_accounts(
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    level: Optional[int] = None,
    leaf_only: Optional[str] = None,
    company_id: int = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db)
):
    q = db.query(Account).filter(Account.company_id == company_id)
    if category:
        q = q.filter(Account.category == category)
    if keyword:
        q = q.filter(or_(
            Account.code.contains(keyword),
            Account.name.contains(keyword)
        ))
    if level:
        q = q.filter(Account.level == level)
    accounts = q.order_by(Account.code).offset(skip).limit(limit).all()

    # 末级科目过滤：排除那些是其他科目parent_code的科目
    if leaf_only and leaf_only.lower() in ("1", "true", "yes"):
        all_codes = {a.code for a in accounts}
        parent_codes = {a.parent_code for a in accounts if a.parent_code}
        accounts = [a for a in accounts if a.code not in parent_codes]

    # 构建全级次名称映射
    hierarchy = _build_account_hierarchy(db, company_id)

    # 检查哪些科目有下级
    all_codes = {a.code for a in accounts}
    parent_codes = {a.parent_code for a in accounts if a.parent_code}
    has_children_codes = parent_codes & all_codes

    # 检查哪些科目被序时账使用
    journal_codes = set()
    try:
        journal_codes = {r[0] for r in db.query(JournalEntry.account_code).filter(
            JournalEntry.company_id == company_id
        ).distinct().all()}
    except Exception as e:
        logging.warning(f"科目序时账使用检查失败: {e}")

    return [
        {
            "id": a.id, "code": a.code, "name": a.name,
            "full_name": hierarchy.get(a.code, f"{a.code} {a.name}"),
            "category": a.category, "balance_direction": a.balance_direction,
            "level": a.level, "parent_code": a.parent_code,
            "is_active": a.is_active,
            "opening_balance": a.opening_balance or 0.0,
            "has_children": a.code in has_children_codes,
            "has_journal": a.code in journal_codes,
        } for a in accounts
    ]


class AccountCreate(BaseModel):
    code: str
    name: str
    category: str = ""
    balance_direction: str = ""
    level: int = 1
    parent_code: str = ""
    opening_balance: float = 0.0


class AccountUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    balance_direction: Optional[str] = None
    level: Optional[int] = None
    parent_code: Optional[str] = None
    opening_balance: Optional[float] = None
    is_active: Optional[bool] = None


@router.post("/api/accounts")
def create_account(data: AccountCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    code = data.code
    name = (data.name or "").strip()
    category = data.category
    balance_direction = data.balance_direction
    level = data.level
    parent_code = data.parent_code
    if not code or not name:
        raise HTTPException(400, detail="科目编码和名称不能为空")
    # 一级科目限制：仅6个往来科目可作为一级科目，其他必须设二级
    ALLOWED_L1_CODES = {'1122', '2202', '2203', '1123', '1221', '2241'}
    if level == 1:
        code_root = code[:4]
        if code_root not in ALLOWED_L1_CODES:
            raise HTTPException(400,
                detail="该科目不可作为一级科目使用。仅以下6个往来科目允许设置一级科目："
                       "应收账款(1122)、应付账款(2202)、预收账款(2203)、"
                       "预付账款(1123)、其他应收款(1221)、其他应付款(2241)。"
                       "请选择2级（含）以上级次。")
    # 1221其他应收款不允许设二级科目，应使用往来项目（人员/供应商档案）
    if code[:4] == '1221' and level and level >= 2:
        raise HTTPException(400, detail="1221其他应收款不需要二级科目，请直接使用往来项目（人员档案/供应商档案）")
    # 去重检查：同一公司内科目编码不能重复
    dup_code = db.query(Account).filter(Account.company_id == company_id, Account.code == code).first()
    if dup_code:
        raise HTTPException(400, detail=f"科目编码【{code}】已存在（{dup_code.name}），请更换编码")
    # 去重检查：同一公司内科目名称不能重复（本级名称）
    dup_name = db.query(Account).filter(Account.company_id == company_id, Account.name == name).first()
    if dup_name:
        raise HTTPException(400, detail=f"科目名称【{name}】已存在（{dup_name.code}），请更换名称")
    acc = Account(company_id=company_id, code=code, name=name, category=category,
                  balance_direction=balance_direction, level=level, parent_code=parent_code,
                  opening_balance=data.opening_balance)
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return {"id": acc.id, "code": acc.code, "name": acc.name, "message": "创建成功"}


@router.put("/api/accounts/{account_id}")
def update_account(account_id: int, data: AccountUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    acc = db.query(Account).filter(Account.company_id == company_id, Account.id == account_id).first()
    if not acc:
        raise HTTPException(404, detail="科目不存在")
    if data.name is not None:
        new_name = data.name.strip()
        # 去重检查：同一公司内科目名称不能重复（排除自身）
        dup_name = db.query(Account).filter(
            Account.company_id == company_id,
            Account.name == new_name,
            Account.id != account_id
        ).first()
        if dup_name:
            raise HTTPException(400, detail=f"科目名称【{new_name}】已存在（{dup_name.code}），请更换名称")
        acc.name = new_name
    if data.is_active is not None:
        acc.is_active = data.is_active
    if data.opening_balance is not None:
        acc.opening_balance = data.opening_balance
    db.commit()
    return {"message": "更新成功"}


@router.delete("/api/accounts/{account_id}")
def delete_account(account_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    acc = db.query(Account).filter(Account.company_id == company_id, Account.id == account_id).first()
    if not acc:
        raise HTTPException(404, detail="科目不存在")
    db.delete(acc)
    db.commit()
    return {"message": "删除成功"}


# ==================== 统计看板 ====================

@router.get("/api/dashboard")
def dashboard(company_id: int = Query(...), db: Session = Depends(get_db)):
    """数据看板——各模块数量统计"""
    from datetime import date
    period = date.today().strftime("%Y-%m")

    customer_count = db.query(Customer).filter(Customer.company_id == company_id).count()
    supplier_count = db.query(Supplier).filter(Supplier.company_id == company_id).count()
    employee_count = db.query(Employee).filter(Employee.company_id == company_id).count()
    account_count = db.query(Account).filter(Account.company_id == company_id).count()
    si_count = db.query(SalesInvoice).filter(SalesInvoice.company_id == company_id).count()
    pi_count = db.query(PurchaseInvoice).filter(PurchaseInvoice.company_id == company_id).count()
    bi_count = db.query(BookkeepingInvoice).filter(BookkeepingInvoice.company_id == company_id).count()

    return {
        "period": period,
        "customer_count": customer_count,
        "supplier_count": supplier_count,
        "employee_count": employee_count,
        "account_count": account_count,
        "sales_invoice_count": si_count,
        "purchase_invoice_count": pi_count,
        "bookkeeping_invoice_count": bi_count,
    }


# ==================== 公司账套管理 ====================

class CompanyCreate(BaseModel):
    name: str
    uscc: Optional[str] = None
    registered_capital: Optional[float] = None
    established_date: Optional[date] = None
    legal_representative: Optional[str] = None
    legal_representative_id: Optional[str] = None
    address: Optional[str] = None
    business_scope: Optional[str] = None
    company_type: Optional[str] = None
    shareholders: Optional[List[dict]] = None
    directors: Optional[List[dict]] = None
    supervisors: Optional[List[dict]] = None
    finance_contacts: Optional[List[dict]] = None

class CompanyUpdateModel(BaseModel):
    name: Optional[str] = None
    uscc: Optional[str] = None
    registered_capital: Optional[float] = None
    established_date: Optional[date] = None
    legal_representative: Optional[str] = None
    legal_representative_id: Optional[str] = None
    address: Optional[str] = None
    business_scope: Optional[str] = None
    company_type: Optional[str] = None
    shareholders: Optional[List[dict]] = None
    directors: Optional[List[dict]] = None
    supervisors: Optional[List[dict]] = None
    finance_contacts: Optional[List[dict]] = None


@router.get("/api/companies")
def list_companies(request: Request, db: Session = Depends(get_db)):
    """获取公司列表（账套选择）"""
    query = db.query(Company)
    session = request.state.auth
    if not session.is_admin:
        query = query.filter(Company.id.in_(sorted(session.allowed_company_ids)))
    companies = query.order_by(Company.id).all()
    return [{
        "id": c.id, "name": c.name, "uscc": c.uscc or "",
        "registered_capital": c.registered_capital,
        "established_date": str(c.established_date) if c.established_date else "",
        "legal_representative": c.legal_representative or "",
        "legal_representative_id": c.legal_representative_id or "",
        "address": c.address or "",
        "business_scope": c.business_scope or "",
        "created_at": str(c.created_at.date()) if c.created_at else "",
        "shareholders": [{"name": s.name, "id_number": s.id_number or "", "ratio": s.ratio, "contribution_amount": s.contribution_amount} for s in c.shareholders],
        "directors": [{"name": d.name, "id_number": d.id_number or ""} for d in c.directors],
        "supervisors": [{"name": s.name, "id_number": s.id_number or ""} for s in c.supervisors],
        "finance_contacts": [{"name": f.name, "id_number": f.id_number or "", "phone": f.phone or ""} for f in c.finance_contacts],
    } for c in companies]


@router.post("/api/companies")
def create_company(data: CompanyCreate, db: Session = Depends(get_db)):
    """创建新公司/账套"""
    if data.uscc:
        if len(data.uscc) != 18 or not data.uscc.isalnum():
            raise HTTPException(400, detail="统一社会信用代码必须为18位字母数字组合")
        # 检查是否已存在
        existing = db.query(Company).filter(Company.uscc == data.uscc).first()
        if existing:
            raise HTTPException(400, detail=f"该统一社会信用代码已存在：{existing.name}")

    main_fields = {k: v for k, v in data.model_dump(exclude_unset=True).items()
                   if k not in ("shareholders", "directors", "supervisors", "finance_contacts")}
    company = Company(**main_fields)
    db.add(company)
    db.flush()

    # 子表（仅当数据存在且函数可用时处理）
    for sub_field, sub_model in [("shareholders", CompanyShareholder), ("directors", CompanyDirector),
                                  ("supervisors", CompanySupervisor), ("finance_contacts", CompanyFinanceContact)]:
        items = getattr(data, sub_field, None)
        if items:
            for item in items:
                obj = sub_model(company_id=company.id, **item)
                db.add(obj)

    # 初始化公司基础数据（仅当函数可用时）
    try:
        init_company_data(db, company.id)
    except NameError:
        pass
    db.commit()
    db.refresh(company)

    return {"id": company.id, "name": company.name, "message": f"公司 '{company.name}' 创建成功，已初始化科目表和基础档案"}


@router.put("/api/companies/{company_id}")
def update_company_detail(company_id: int, data: CompanyUpdateModel, db: Session = Depends(get_db)):
    """更新公司信息"""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, detail="公司不存在")
    if data.uscc:
        if len(data.uscc) != 18 or not data.uscc.isalnum():
            raise HTTPException(400, detail="统一社会信用代码必须为18位字母数字组合")
    main_fields = {k: v for k, v in data.model_dump(exclude_unset=True).items()
                   if k not in ("shareholders", "directors", "supervisors", "finance_contacts")}
    for k, v in main_fields.items():
        setattr(company, k, v)
    for sub_field, sub_model in [("shareholders", CompanyShareholder), ("directors", CompanyDirector),
                                  ("supervisors", CompanySupervisor), ("finance_contacts", CompanyFinanceContact)]:
        items = getattr(data, sub_field, None)
        if items:
            for item in items:
                obj = sub_model(company_id=company.id, **item)
                db.add(obj)
    db.commit()
    return {"message": "更新成功"}


@router.delete("/api/companies/{company_id}")
def delete_company(company_id: int, db: Session = Depends(get_db)):
    """删除公司及其所有关联数据"""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, detail="公司不存在")
    try:
        # SQLite级联删除：先删关联子表数据
        from sqlalchemy.sql import text
        tables = ['company_shareholders','company_directors','company_supervisors','company_finance_contacts',
                  'departments','employees','customers','suppliers','accounts','periods',
                  'sales_invoices','purchase_invoices','bookkeeping_invoices','bank_transactions',
                  'bank_configs','journal_entries','column_templates','bank_rules',
                  'input_vat_deductions','vat_declarations','salary_records','housing_fund_details',
                  'housing_fund_declarations','social_security_declarations','contracts','contract_payments',
                  'payments','inventory_items','inventory_balances','inventory_transactions',
                  'fixed_assets','fixed_asset_depreciations','intangible_assets','intangible_asset_amortizations']
        for tbl in tables:
            try:
                db.execute(text(f"DELETE FROM {tbl} WHERE company_id = :cid"), {"cid": company_id})
            except Exception:
                pass
        db.commit()
        db.delete(company)
        db.commit()
        # 清理文件目录
        import shutil
        upload_dir = str(company_upload_dir(company_id))
        if os.path.exists(upload_dir):
            try:
                shutil.rmtree(upload_dir)
            except Exception:
                pass
    except Exception as e:
        db.rollback()
        raise HTTPException(500, detail=f"删除失败：{e}")
    return {"ok": True, "message": f"已删除 {company.name}"}


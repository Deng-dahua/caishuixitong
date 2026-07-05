"""
文件解析模块 - 从 main.py 自动拆分
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Form, UploadFile, File, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, text
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
import os, io, json, re as _re_module, openpyxl, hashlib, csv, logging

from database import get_db

router = APIRouter(tags=["文件解析"])

class ColumnTemplateCreate(BaseModel):
    module: str
    template_name: str
    bank_config_id: Optional[int] = None
    column_mapping: Optional[str] = None
    is_default: bool = False


class ColumnTemplateUpdate(BaseModel):
    template_name: Optional[str] = None
    column_mapping: Optional[str] = None
    is_default: Optional[bool] = None


@router.get("/api/column-templates")
def list_column_templates(
    company_id: int = Query(...),
    module: Optional[str] = None,
    bank_config_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    q = db.query(ColumnTemplate).filter(ColumnTemplate.company_id == company_id)
    if module:
        q = q.filter(ColumnTemplate.module == module)
    if bank_config_id is not None:
        q = q.filter(ColumnTemplate.bank_config_id == bank_config_id)
    templates = q.order_by(ColumnTemplate.module, ColumnTemplate.template_name).all()
    return [{
        "id": t.id, "module": t.module, "template_name": t.template_name,
        "bank_config_id": t.bank_config_id,
        "column_mapping": t.column_mapping or "{}",
        "is_default": t.is_default,
        "created_at": str(t.created_at) if t.created_at else ""
    } for t in templates]


@router.post("/api/column-templates")
def create_column_template(data: ColumnTemplateCreate, company_id: int = Query(...), db: Session = Depends(get_db)):
    tpl = ColumnTemplate(company_id=company_id, **data.model_dump())
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return {"id": tpl.id, "message": "模板创建成功"}


@router.put("/api/column-templates/{tpl_id}")
def update_column_template(tpl_id: int, data: ColumnTemplateUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    tpl = db.query(ColumnTemplate).filter(ColumnTemplate.company_id == company_id, ColumnTemplate.id == tpl_id).first()
    if not tpl:
        raise HTTPException(404, detail="模板不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(tpl, k, v)
    tpl.updated_at = datetime.now()
    db.commit()
    return {"message": "更新成功"}


@router.delete("/api/column-templates/{tpl_id}")
def delete_column_template(tpl_id: int, company_id: int = Query(...), db: Session = Depends(get_db)):
    tpl = db.query(ColumnTemplate).filter(ColumnTemplate.company_id == company_id, ColumnTemplate.id == tpl_id).first()
    if not tpl:
        raise HTTPException(404, detail="模板不存在")
    db.delete(tpl)
    db.commit()
    return {"message": "删除成功"}


# ==================== 文件上传 - 表头分析 ====================

@router.post("/api/file/analyze-headers")
async def analyze_file_headers(
    file: UploadFile = File(...),
    module: str = Form("bank-transaction"),
    bank_config_id: Optional[int] = Form(None)
):
    """上传文件，返回表头列表供用户做列映射"""
    fname = file.filename or "unknown"
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"不支持的文件类型: {ext}，仅接受 xlsx/xls/csv/pdf/docx/图片")
    try:
        content_bytes = await file.read()
        if len(content_bytes) > MAX_UPLOAD_SIZE:
            raise HTTPException(400, f"文件过大（{len(content_bytes)/1024/1024:.2f}MB），上限10MB")

        headers = []
        preview_rows = []

        if ext in (".xlsx", ".xls"):
            wb = openpyxl.load_workbook(io.BytesIO(content_bytes), data_only=True)
            ws = wb.active
            # 第一行作为表头
            for col in range(1, ws.max_column + 1):
                cell = ws.cell(row=1, column=col)
                headers.append(str(cell.value).strip() if cell.value is not None else f"列{col}")
            # 预览前3行
            for row in range(2, min(ws.max_row + 1, 5)):
                vals = {}
                for col in range(1, ws.max_column + 1):
                    cell = ws.cell(row=row, column=col)
                    vals[headers[col - 1]] = str(cell.value) if cell.value is not None else ""
                preview_rows.append(vals)
            total_rows = ws.max_row - 1
        elif ext == ".csv":
            text = content_bytes.decode("utf-8-sig")
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            if rows:
                headers = [h.strip() for h in rows[0]]
                for row in rows[1:4]:
                    vals = {}
                    for i, h in enumerate(headers):
                        vals[h] = row[i] if i < len(row) else ""
                    preview_rows.append(vals)
                total_rows = len(rows) - 1
            else:
                headers, total_rows = [], 0
        elif ext == ".pdf" or ext == ".docx":
            raise HTTPException(400, f"{ext} 文件请在「资料风险分析」页面上传，系统将自动解析表格内容。")

        # 获取已知的列映射模板
        field_groups = {}
        field_order = None
        if module == "sales-invoice":
            # 严格按开具发票表头26列顺序，一一平铺
            field_order = [
                "invoice_code", "invoice_no", "digital_invoice_no",
                "seller_tax_no", "seller_name",
                "buyer_tax_no", "buyer_name",
                "invoice_date", "tax_category_code", "specific_business_type",
                "goods_name", "spec", "unit", "quantity", "unit_price",
                "amount", "tax_rate", "tax_amount", "total_amount",
                "invoice_source", "invoice_category", "status", "is_positive", "invoice_risk_level",
                "issuer", "remark"
            ]
        elif module == "purchase-invoice":
            # 取得发票26列
            field_order = [
                "invoice_code", "invoice_no", "digital_invoice_no",
                "seller_tax_no", "seller_name",
                "buyer_tax_no", "buyer_name",
                "invoice_date", "tax_category_code", "specific_business_type",
                "goods_name", "spec", "unit", "quantity", "unit_price",
                "amount", "tax_rate", "tax_amount", "total_amount",
                "invoice_source", "invoice_category", "status", "is_positive", "invoice_risk_level",
                "issuer", "remark"
            ]
        elif module == "bookkeeping-invoice":
            # 记账发票25列（无认证信息列）
            field_order = [
                "invoice_code", "invoice_no", "digital_invoice_no",
                "seller_tax_no", "seller_name",
                "buyer_tax_no", "buyer_name",
                "invoice_date", "tax_category_code", "specific_business_type",
                "goods_name", "spec", "unit", "quantity", "unit_price",
                "amount", "tax_rate", "tax_amount", "total_amount",
                "invoice_source", "invoice_category", "status", "is_positive", "invoice_risk_level",
                "issuer", "remark"
            ]
        elif module == "bank-transaction":
            field_order = [
                "transaction_date", "transaction_time", "application_date",
                "voucher_no", "debit_amount", "credit_amount", "balance",
                "counterparty_account", "counterparty_name", "counterparty_bank",
                "transaction_serial_no", "voucher_seq", "record_status",
                "summary", "transaction_remark", "account_type"
            ]
        elif module == "input-vat-deduction":
            field_order = [
                "check_status", "invoice_source", "domestic_sale_cert_no",
                "digital_invoice_no", "invoice_code", "invoice_no",
                "invoice_date", "seller_tax_id", "seller_name",
                "amount", "tax_amount", "deductible_tax_amount",
                "invoice_category", "invoice_category_label", "invoice_status",
                "check_time", "risk_level"
            ]
        elif module == "employee":
            field_order = [
                "name", "id_card"
            ]
        elif module == "customer":
            field_order = [
                "name", "uscc"
            ]
        elif module == "supplier":
            field_order = [
                "name", "uscc"
            ]
        elif module == "department":
            field_order = [
                "code", "name"
            ]

        return {
            "file_name": fname,
            "headers": headers,
            "preview_rows": preview_rows,
            "total_rows": total_rows,
            "module": module,
            "field_groups": field_groups,
            "field_order": field_order
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"error": f"文件分析失败：{str(e)}"}


@router.post("/api/file/import-with-mapping")
async def import_file_with_mapping(  # v2026-06-04-simplify: 进项发票改为单步导入
    file: UploadFile = File(...),
    module: str = Form("bank-transaction"),
    bank_config_id: Optional[int] = Form(None),
    column_mapping: str = Form(...),  # JSON: {标准字段: 文件列名}
    company_id: int = Form(...),
    force: str = Form("false"),
    db: Session = Depends(get_db)
):
    """根据列映射导入文件数据"""
    try:
        fname = file.filename or "unknown"
        ext = os.path.splitext(fname)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"不支持的文件类型: {ext}，仅接受 xlsx/xls/csv/pdf/txt")
        content_bytes = await file.read()
        if len(content_bytes) > MAX_UPLOAD_SIZE:
            raise HTTPException(400, f"文件过大（{len(content_bytes)/1024/1024:.2f}MB），上限10MB")
        mapping = json.loads(column_mapping)
        force_dup = (force == "true")

        # 读取数据行
        rows_data = []
        if ext in (".xlsx", ".xls"):
            wb = openpyxl.load_workbook(io.BytesIO(content_bytes), data_only=True)
            ws = wb.active
            headers_file = []
            for col in range(1, ws.max_column + 1):
                cell = ws.cell(row=1, column=col)
                headers_file.append(str(cell.value).strip() if cell.value is not None else f"列{col}")
            for row in range(2, ws.max_row + 1):
                row_dict = {}
                for col in range(1, ws.max_column + 1):
                    cell = ws.cell(row=row, column=col)
                    if cell.value is None:
                        row_dict[headers_file[col - 1]] = ""
                    elif isinstance(cell.value, datetime):
                        row_dict[headers_file[col - 1]] = cell.value.strftime("%Y-%m-%d %H:%M:%S")
                    elif isinstance(cell.value, (int, float)):
                        # 数字直接转字符串（openpyxl data_only=True 已自动把真正的日期转 datetime，
                        # 此处 int/float 就是纯数字如金额、数量，误当日期序列号会销毁金额数据）
                        row_dict[headers_file[col - 1]] = str(cell.value)
                    else:
                        row_dict[headers_file[col - 1]] = str(cell.value).strip()
                # 跳过完全空行
                if any(v.strip() for v in row_dict.values()):
                    rows_data.append(row_dict)
        elif ext == ".csv":
            text = content_bytes.decode("utf-8-sig")
            reader = csv.reader(io.StringIO(text))
            all_rows = list(reader)
            if all_rows:
                headers_file = [h.strip() for h in all_rows[0]]
                for row in all_rows[1:]:
                    row_dict = {}
                    for i, h in enumerate(headers_file):
                        row_dict[h] = row[i] if i < len(row) else ""
                    if any(v.strip() for v in row_dict.values()):
                        rows_data.append(row_dict)

        # 根据映射转换并导入
        import_batch_id = str(uuid.uuid4())
        imported = 0
        errors = []
        infos = []  # 非错误提示（如自动创建客户档案）

        new_customers = {}  # {(tax_no, name): True} — 自动添加客户档案
        new_invoices = []  # 收集新创建的发票，导入完成后自动生成凭证
        new_deductions = []  # 收集新创建的进项抵扣，导入完成后自动生成凭证
        new_bank_tx_ids = []  # 收集新创建的银行流水ID，导入完成后自动生成凭证
        for i, row in enumerate(rows_data):
            try:
                mapped = {}
                extra = {}
                for std_field, file_col in mapping.items():
                    if file_col and file_col in row:
                        mapped[std_field] = row[file_col].strip()

                # 收集额外列（未映射的）
                for col_name, val in row.items():
                    if col_name not in mapping.values():
                        extra[col_name] = val.strip()


                if module == "bank-transaction":
                    # 解析日期
                    tx_date = None
                    date_str = mapped.get("transaction_date", "")
                    if date_str:
                        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"]:
                            try:
                                tx_date = datetime.strptime(date_str, fmt).date()
                                break
                            except Exception: pass
                    if not tx_date:
                        errors.append(f"第{i+2}行: 无法解析日期")
                        continue

                    # 解析交易时间
                    tx_time = None
                    time_str = mapped.get("transaction_time", "")
                    if time_str:
                        for tf in ["%H:%M:%S", "%H:%M", "%H:%M:%S.%f"]:
                            try:
                                tx_time = datetime.strptime(time_str, tf).time()
                                break
                            except Exception: pass

                    # 解析申请日期
                    app_date = None
                    app_date_str = mapped.get("application_date", "")
                    if app_date_str:
                        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"]:
                            try:
                                app_date = datetime.strptime(app_date_str, fmt).date()
                                break
                            except Exception: pass

                    # 解析借方/贷方金额
                    def parse_amt(key):
                        v = mapped.get(key, "0").replace(",", "").replace("￥", "").replace("¥", "")
                        try: return float(v) if v else 0.0
                        except Exception: return 0.0
                    debit_amount = parse_amt("debit_amount")
                    credit_amount = parse_amt("credit_amount")

                    # 余额
                    bal_str = mapped.get("balance", "0").replace(",", "").replace("￥", "").replace("¥", "")
                    balance = 0.0
                    try: balance = float(bal_str) if bal_str else 0.0
                    except Exception: pass

                    # 全行指纹去重
                    bt_fp_values = (
                        str(company_id), str(bank_config_id if bank_config_id else ""),
                        str(tx_date) if tx_date else "", str(tx_time) if tx_time else "",
                        str(app_date) if app_date else "",
                        str(mapped.get("voucher_no", "")), str(debit_amount), str(credit_amount),
                        str(balance),
                        str(mapped.get("counterparty_account", "")),
                        str(mapped.get("counterparty_name", "")),
                        str(mapped.get("counterparty_bank", "")),
                        str(mapped.get("transaction_serial_no", "")),
                        str(mapped.get("voucher_seq", "")),
                        str(mapped.get("record_status", "")),
                        str(mapped.get("summary", "")),
                        str(mapped.get("transaction_remark", "")),
                        str(mapped.get("account_type", "")),
                    )
                    bt_fp_raw = "|".join(bt_fp_values)
                    bt_fp = hashlib.sha256(bt_fp_raw.encode("utf-8")).hexdigest()
                    existing_bt = db.query(BankTransaction).filter(
                        BankTransaction.company_id == company_id,
                        BankTransaction._fingerprint == bt_fp
                    ).first()
                    if existing_bt and not force_dup:
                        errors.append(f"第{i+2}行: 数据重复，已跳过")
                        continue

                    tx = BankTransaction(
                        company_id=company_id,
                        bank_config_id=bank_config_id,
                        transaction_date=tx_date,
                        transaction_time=tx_time,
                        application_date=app_date,
                        voucher_no=mapped.get("voucher_no", ""),
                        debit_amount=debit_amount,
                        credit_amount=credit_amount,
                        balance=balance,
                        counterparty_account=mapped.get("counterparty_account", ""),
                        counterparty_name=mapped.get("counterparty_name", ""),
                        counterparty_bank=mapped.get("counterparty_bank", ""),
                        transaction_serial_no=mapped.get("transaction_serial_no", ""),
                        voucher_seq=mapped.get("voucher_seq", ""),
                        record_status=mapped.get("record_status", ""),
                        summary=mapped.get("summary", ""),
                        transaction_remark=mapped.get("transaction_remark", ""),
                        account_type=mapped.get("account_type", ""),
                        # 旧字段兼容
                        amount=credit_amount - debit_amount,
                        transaction_type="收入" if credit_amount > 0 else "支出",
                        raw_data=json.dumps(extra, ensure_ascii=False) if extra else "{}",
                        remark=mapped.get("remark", ""),
                        _fingerprint=bt_fp,
                    )
                    db.add(tx)
                    db.flush()
                    new_bank_tx_ids.append(tx.id)

                elif module in ("sales-invoice", "purchase-invoice", "bookkeeping-invoice"):
                    inv_date = None
                    date_str = mapped.get("invoice_date", "")
                    if date_str:
                        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d",
                                    "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
                                    "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"]:
                            try:
                                inv_date = datetime.strptime(date_str, fmt).date()
                                break
                            except Exception: pass

                    # 空值保留为 None，不拦截
                    inv_no = mapped.get("invoice_no", "") or None

                    
                    # 安全转浮点数——兼容千分位/百分号/空值/文本
                    # nullable=True 时源文件为空则返回 None，保留空白不填 0
                    def safe_float(val, default=0.0, nullable=False):
                        if val is None or str(val).strip() == "":
                            return None if nullable else default
                        s = str(val).strip().replace(",", "").replace("%", "").replace("￥", "").replace("¥", "").replace("元", "").replace(" ", "")
                        try:
                            return float(s)
                        except (ValueError, TypeError):
                            return None if nullable else default

                    amt = safe_float(mapped.get("amount"))
                    tax_amt = safe_float(mapped.get("tax_amount"), nullable=True)
                    total = safe_float(mapped.get("total_amount"), nullable=True)
                    # 三个字段互推：任意两个有值就能算出第三个
                    if amt is not None and tax_amt is not None and total is None:
                        total = round(amt + tax_amt, 2)
                    elif amt is not None and total is not None and tax_amt is None:
                        tax_amt = round(total - amt, 2)
                    elif tax_amt is not None and total is not None and amt is None:
                        amt = round(total - tax_amt, 2)
                    if total is None:
                        total = 0.0
                    if tax_amt is None:
                        tax_amt = 0.0
                    if amt is None:
                        amt = 0.0
                    qty = safe_float(mapped.get("quantity"), 0, nullable=True)
                    uprice = safe_float(mapped.get("unit_price"), 0, nullable=True)
                    tr = safe_float(mapped.get("tax_rate"))

                    if module == "sales-invoice":
                        # 计算全行指纹（仅用于审计，去重以票号为准）
                        fp_values = (
                            str(company_id), str(inv_no or ""), str(mapped.get("invoice_code", "")),
                            str(mapped.get("digital_invoice_no", "")),
                            str(mapped.get("seller_tax_no", "")), str(mapped.get("seller_name", "")),
                            str(mapped.get("buyer_tax_no", "")), str(mapped.get("buyer_name", "")),
                            str(inv_date) if inv_date else "",
                            str(mapped.get("tax_category_code", "")), str(mapped.get("specific_business_type", "")),
                            str(mapped.get("goods_name", "")), str(mapped.get("spec", "")),
                            str(mapped.get("unit", "")), str(qty), str(uprice),
                            str(amt), str(tr), str(tax_amt), str(total),
                            str(mapped.get("invoice_source", "")),
                            str(mapped.get("invoice_category", "增值税专用发票")),
                            str(mapped.get("status", "正常")),
                            str(mapped.get("is_positive", "是")),
                            str(mapped.get("invoice_risk_level", "")),
                            str(mapped.get("issuer", "")),
                            str(mapped.get("remark", "")),
                        )
                        fp_raw = "|".join(fp_values)
                        fp = hashlib.sha256(fp_raw.encode("utf-8")).hexdigest()

                        # ── 按票号去重（数电发票号 > 发票代码+号码） ──
                        _si_digital = str(mapped.get("digital_invoice_no", "")).strip()
                        _si_code = str(mapped.get("invoice_code", "")).strip()
                        _si_no = str(inv_no or "").strip()
                        if _si_digital:
                            _dup = db.query(SalesInvoice).filter(
                                    SalesInvoice.company_id == company_id,
                                    SalesInvoice.digital_invoice_no == _si_digital
                                ).first()
                        elif _si_no:
                            _q = db.query(SalesInvoice).filter(
                                    SalesInvoice.company_id == company_id,
                                    SalesInvoice.invoice_no == _si_no
                                )
                            if _si_code:
                                _q = _q.filter(SalesInvoice.invoice_code == _si_code)
                            _dup = _q.first()
                        else:
                            _dup = None
                        if _dup and not force_dup:
                            errors.append(f"第{i+2}行: 发票票号重复，已跳过")
                            continue
                        inv = SalesInvoice(
                            company_id=company_id, invoice_no=inv_no,
                            invoice_code=mapped.get("invoice_code", ""),
                            digital_invoice_no=mapped.get("digital_invoice_no", ""),
                            seller_tax_no=mapped.get("seller_tax_no", ""),
                            seller_name=mapped.get("seller_name", ""),
                            buyer_tax_no=mapped.get("buyer_tax_no", ""),
                            buyer_name=mapped.get("buyer_name", ""),
                            invoice_date=inv_date,
                            tax_category_code=mapped.get("tax_category_code", ""),
                            specific_business_type=mapped.get("specific_business_type", ""),
                            goods_name=mapped.get("goods_name", ""),
                            spec=mapped.get("spec", ""),
                            unit=mapped.get("unit", ""),
                            quantity=qty, unit_price=uprice,
                            amount=amt, tax_rate=tr, tax_amount=tax_amt,
                            total_amount=total,
                            invoice_source=mapped.get("invoice_source", ""),
                            invoice_category=mapped.get("invoice_category", "增值税专用发票"),
                            status=mapped.get("status", "正常"),
                            is_positive=mapped.get("is_positive", "是") in ("是", "true", "True", "1", True),
                            invoice_risk_level=mapped.get("invoice_risk_level", ""),
                            issuer=mapped.get("issuer", ""),
                            remark=mapped.get("remark", ""),
                            raw_data=json.dumps(extra) if extra else None,
                            _fingerprint=fp,
                        )
                        db.add(inv)
                        db.flush()
                        new_invoices.append(inv)
                        # 收集购买方信息，导入后自动添加客户档案
                        buyer_nm = mapped.get("buyer_name", "").strip()
                        buyer_tn = mapped.get("buyer_tax_no", "").strip()
                        if buyer_nm:
                            new_customers[(buyer_tn, buyer_nm)] = True
                    else:  # purchase-invoice
                        # ── 取得发票全指纹去重 ──
                        pi_fp_values = (
                            str(company_id), str(inv_no or ""), str(mapped.get("invoice_code", "")),
                            str(mapped.get("digital_invoice_no", "")),
                            str(mapped.get("seller_tax_no", "")), str(mapped.get("seller_name", "")),
                            str(mapped.get("buyer_tax_no", "")), str(mapped.get("buyer_name", "")),
                            str(inv_date) if inv_date else "",
                            str(mapped.get("tax_category_code", "")), str(mapped.get("specific_business_type", "")),
                            str(mapped.get("goods_name", "")), str(mapped.get("spec", "")),
                            str(mapped.get("unit", "")), str(qty), str(uprice),
                            str(amt), str(tr), str(tax_amt), str(total),
                            str(mapped.get("invoice_source", "")),
                            str(mapped.get("invoice_category", "增值税专用发票")),
                            str(mapped.get("status", "正常")),
                            str(mapped.get("is_positive", "是")),
                            str(mapped.get("invoice_risk_level", "")),
                            str(mapped.get("issuer", "")),
                            str(mapped.get("remark", "")),
                        )
                        pi_fp_raw = "|".join(pi_fp_values)
                        pi_fp = hashlib.sha256(pi_fp_raw.encode("utf-8")).hexdigest()
                        existing_pi = db.query(PurchaseInvoice).filter(
                            PurchaseInvoice.company_id == company_id,
                            PurchaseInvoice._fingerprint == pi_fp
                        ).first()
                        if existing_pi and not force_dup:
                            errors.append(f"第{i+2}行: 全指纹重复，已跳过")
                            continue
                        inv = PurchaseInvoice(
                            company_id=company_id, invoice_no=inv_no,
                            invoice_code=mapped.get("invoice_code", ""),
                            digital_invoice_no=mapped.get("digital_invoice_no", ""),
                            seller_tax_no=mapped.get("seller_tax_no", ""),
                            seller_name=mapped.get("seller_name", ""),
                            buyer_tax_no=mapped.get("buyer_tax_no", ""),
                            buyer_name=mapped.get("buyer_name", ""),
                            invoice_date=inv_date,
                            tax_category_code=mapped.get("tax_category_code", ""),
                            specific_business_type=mapped.get("specific_business_type", ""),
                            goods_name=mapped.get("goods_name", ""),
                            spec=mapped.get("spec", ""),
                            unit=mapped.get("unit", ""),
                            quantity=qty, unit_price=uprice,
                            amount=amt, tax_rate=tr, tax_amount=tax_amt,
                            total_amount=total,
                            invoice_source=mapped.get("invoice_source", ""),
                            invoice_category=mapped.get("invoice_category", "增值税专用发票"),
                            status=mapped.get("status", "正常"),
                            is_positive=mapped.get("is_positive", "是") in ("是", "true", "True", "1", True),
                            invoice_risk_level=mapped.get("invoice_risk_level", ""),
                            issuer=mapped.get("issuer", ""),
                            remark=mapped.get("remark", ""),
                            raw_data=json.dumps(extra) if extra else None,
                            _fingerprint=pi_fp,
                        )
                        db.add(inv)
                        db.flush()
                        new_invoices.append(inv)

                elif module == "bookkeeping-invoice":
                    # 记账发票导入（无认证相关字段）
                    bi_fp_values = (
                        str(company_id), str(inv_no or ""), str(mapped.get("invoice_code", "")),
                        str(mapped.get("digital_invoice_no", "")),
                        str(mapped.get("seller_tax_no", "")), str(mapped.get("seller_name", "")),
                        str(mapped.get("buyer_tax_no", "")), str(mapped.get("buyer_name", "")),
                        str(inv_date) if inv_date else "",
                        str(mapped.get("tax_category_code", "")), str(mapped.get("specific_business_type", "")),
                        str(mapped.get("goods_name", "")), str(mapped.get("spec", "")),
                        str(mapped.get("unit", "")), str(qty), str(uprice),
                        str(amt), str(tr), str(tax_amt), str(total),
                        str(mapped.get("invoice_source", "")),
                        str(mapped.get("invoice_category", "增值税普通发票")),
                        str(mapped.get("status", "正常")),
                        str(mapped.get("is_positive", "是")),
                        str(mapped.get("invoice_risk_level", "")),
                        str(mapped.get("issuer", "")),
                        str(mapped.get("remark", "")),
                    )
                    bi_fp_raw = "|".join(bi_fp_values)
                    bi_fp = hashlib.sha256(bi_fp_raw.encode("utf-8")).hexdigest()
                    existing_bi = db.query(BookkeepingInvoice).filter(
                        BookkeepingInvoice.company_id == company_id,
                        BookkeepingInvoice._fingerprint == bi_fp
                    ).first()
                    if existing_bi and not force_dup:
                        errors.append(f"第{i+2}行: 数据重复，已跳过")
                        continue
                    inv = BookkeepingInvoice(
                        company_id=company_id, invoice_no=inv_no,
                        invoice_code=mapped.get("invoice_code", ""),
                        digital_invoice_no=mapped.get("digital_invoice_no", ""),
                        seller_tax_no=mapped.get("seller_tax_no", ""),
                        seller_name=mapped.get("seller_name", ""),
                        buyer_tax_no=mapped.get("buyer_tax_no", ""),
                        buyer_name=mapped.get("buyer_name", ""),
                        invoice_date=inv_date,
                        tax_category_code=mapped.get("tax_category_code", ""),
                        specific_business_type=mapped.get("specific_business_type", ""),
                        goods_name=mapped.get("goods_name", ""),
                        spec=mapped.get("spec", ""),
                        unit=mapped.get("unit", ""),
                        quantity=qty, unit_price=uprice,
                        amount=amt, tax_rate=tr, tax_amount=tax_amt,
                        total_amount=total,
                        invoice_source=mapped.get("invoice_source", ""),
                        invoice_category=mapped.get("invoice_category", "增值税普通发票"),
                        status=mapped.get("status", "正常"),
                        is_positive=mapped.get("is_positive", "是") in ("是", "true", "True", "1", True),
                        invoice_risk_level=mapped.get("invoice_risk_level", ""),
                        issuer=mapped.get("issuer", ""),
                        remark=mapped.get("remark", ""),
                        raw_data=json.dumps(extra) if extra else None,
                        _fingerprint=bi_fp,
                    )
                    db.add(inv)
                    db.flush()
                    new_invoices.append(inv)

                elif module == "input-vat-deduction":
                    # 进项抵扣导入：解析日期
                    inv_date = None
                    date_str = mapped.get("invoice_date", "")
                    if date_str:
                        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d",
                                    "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"]:
                            try:
                                inv_date = datetime.strptime(date_str, fmt).date()
                                break
                            except Exception: pass

                    check_time = None
                    ct_str = mapped.get("check_time", "")
                    if ct_str:
                        for fmt in ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                                    "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                            try:
                                check_time = datetime.strptime(ct_str, fmt)
                                break
                            except Exception: pass

                    amt = mapped.get("amount", "0").replace(",", "").replace("￥", "").replace("¥", "")
                    try: amt = float(amt) if amt else 0.0
                    except (ValueError, TypeError): amt = 0.0
                    tax_amt = mapped.get("tax_amount", "0").replace(",", "").replace("￥", "").replace("¥", "")
                    try: tax_amt = float(tax_amt) if tax_amt else 0.0
                    except (ValueError, TypeError): tax_amt = 0.0
                    deductible = mapped.get("deductible_tax_amount", "0").replace(",", "").replace("￥", "").replace("¥", "")
                    try: deductible = float(deductible) if deductible else 0.0
                    except (ValueError, TypeError): deductible = 0.0

                    # 全行指纹去重
                    ivd_fp_values = (
                        str(company_id),
                        str(mapped.get("check_status", "")),
                        str(mapped.get("invoice_source", "")),
                        str(mapped.get("domestic_sale_cert_no", "")),
                        str(mapped.get("digital_invoice_no", "")),
                        str(mapped.get("invoice_code", "")),
                        str(mapped.get("invoice_no", "")),
                        str(inv_date) if inv_date else "",
                        str(mapped.get("seller_tax_id", "")),
                        str(mapped.get("seller_name", "")),
                        str(amt), str(tax_amt), str(deductible),
                        str(mapped.get("invoice_category", "")),
                        str(mapped.get("invoice_category_label", "")),
                        str(mapped.get("invoice_status", "正常")),
                        str(check_time) if check_time else "",
                        str(mapped.get("risk_level", "正常")),
                    )
                    ivd_fp_raw = "|".join(ivd_fp_values)
                    ivd_fp = hashlib.sha256(ivd_fp_raw.encode("utf-8")).hexdigest()
                    existing_ivd = db.query(InputVATDeduction).filter(
                        InputVATDeduction.company_id == company_id,
                        InputVATDeduction._fingerprint == ivd_fp
                    ).first()
                    if existing_ivd and not force_dup:
                        errors.append(f"第{i+2}行: 数据重复，已跳过")
                        continue

                    inv = InputVATDeduction(
                        company_id=company_id,
                        check_status=mapped.get("check_status", ""),
                        invoice_source=mapped.get("invoice_source", ""),
                        domestic_sale_cert_no=mapped.get("domestic_sale_cert_no", ""),
                        digital_invoice_no=mapped.get("digital_invoice_no", ""),
                        invoice_code=mapped.get("invoice_code", ""),
                        invoice_no=mapped.get("invoice_no", ""),
                        invoice_date=inv_date,
                        seller_tax_id=mapped.get("seller_tax_id", ""),
                        seller_name=mapped.get("seller_name", ""),
                        amount=amt,
                        tax_amount=tax_amt,
                        deductible_tax_amount=deductible,
                        invoice_category=mapped.get("invoice_category", ""),
                        invoice_category_label=mapped.get("invoice_category_label", ""),
                        invoice_status=mapped.get("invoice_status", "正常"),
                        check_time=check_time,
                        risk_level=mapped.get("risk_level", "正常"),
                        remark=mapped.get("remark", ""),
                        raw_data=json.dumps(extra) if extra else None,
                        import_batch_id=import_batch_id,
                        _fingerprint=ivd_fp,
                    )
                    db.add(inv)
                    db.flush()
                    new_deductions.append(inv)

                elif module == "employee":
                    name = mapped.get("name", "").strip()
                    if not name:
                        errors.append(f"第{i+2}行: 姓名不能为空")
                        continue
                    # P1-4: 通用导入检查 id_card 去重
                    id_card = mapped.get("id_card", "").strip() or None
                    # 编码自动生成 RY001 格式：首次查DB取最大code，后续内存递增
                    if 'emp_code_counter' not in locals():
                        existing_codes = db.query(Employee.code).filter(
                            Employee.company_id == company_id,
                            Employee.code.like('RY%')
                        ).all()
                        emp_code_counter = 0
                        for c in existing_codes:
                            try:
                                num = int(c[0][2:])
                                if num > emp_code_counter:
                                    emp_code_counter = num
                            except Exception: pass
                    emp_code_counter += 1
                    code = f"RY{emp_code_counter:03d}"
                    emp = Employee(
                        company_id=company_id, code=code, name=name,
                        id_card=mapped.get("id_card", "") or None
                    )
                    db.add(emp)
                    db.flush()

                elif module == "customer":
                    name = mapped.get("name", "").strip()
                    if not name:
                        errors.append(f"第{i+2}行: 客户名称不能为空")
                        continue
                    # 编码自动生成 KH001 格式：首次查DB取最大code，后续内存递增
                    if 'cust_code_counter' not in locals():
                        existing_codes = db.query(Customer.code).filter(
                            Customer.company_id == company_id,
                            Customer.code.like('KH%')
                        ).all()
                        cust_code_counter = 0
                        for c in existing_codes:
                            try:
                                num = int(c[0][2:])
                                if num > cust_code_counter:
                                    cust_code_counter = num
                            except Exception: pass
                    cust_code_counter += 1
                    code = f"KH{cust_code_counter:03d}"
                    uscc = mapped.get("uscc", "").strip() or None
                    # 计算全行指纹
                    fp_values = (
                        str(company_id),
                        str(code),
                        str(name),
                        str(uscc or ""),
                        str(mapped.get("tax_no", "") or ""),
                        str(mapped.get("contact", "") or ""),
                        str(mapped.get("phone", "") or ""),
                        str(mapped.get("address", "") or ""),
                        str(mapped.get("credit_limit", "") or ""),
                        str(mapped.get("payment_terms", "") or ""),
                        str(mapped.get("bank_name", "") or ""),
                        str(mapped.get("bank_account", "") or ""),
                        str(True),  # is_active 默认为 True
                        str(mapped.get("remark", "") or "")
                    )
                    fp_raw = "|".join(fp_values)
                    fp = hashlib.sha256(fp_raw.encode("utf-8")).hexdigest()
                    # 去重检查
                    existing = db.query(Customer).filter(
                        Customer.company_id == company_id,
                        Customer._fingerprint == fp
                    ).first()
                    if existing and not force_dup:
                        errors.append(f"第{i+2}行: 数据重复，已跳过")
                        continue
                    cust = Customer(
                        company_id=company_id, code=code, name=name,
                        uscc=uscc,
                        tax_no=mapped.get("tax_no", "") or None,
                        contact=mapped.get("contact", "") or None,
                        phone=mapped.get("phone", "") or None,
                        address=mapped.get("address", "") or None,
                        credit_limit=float(mapped.get("credit_limit", 0) or 0),
                        payment_terms=int(mapped.get("payment_terms", 30) or 30),
                        bank_name=mapped.get("bank_name", "") or None,
                        bank_account=mapped.get("bank_account", "") or None,
                        is_active=True,
                        remark=mapped.get("remark", "") or None,
                        _fingerprint=fp
                    )
                    db.add(cust)
                    db.flush()

                elif module == "supplier":
                    name = mapped.get("name", "").strip()
                    if not name:
                        errors.append(f"第{i+2}行: 供应商名称不能为空")
                        continue
                                        # 编码自动生成 GYS001 格式：首次查DB取最大code，后续内存递增
                    if 'supp_code_counter' not in locals():
                        existing_codes = db.query(Supplier.code).filter(
                            Supplier.company_id == company_id,
                            Supplier.code.like('GYS%')
                        ).all()
                        supp_code_counter = 0
                        for c in existing_codes:
                            try:
                                num = int(c[0][3:])
                                if num > supp_code_counter:
                                    supp_code_counter = num
                            except Exception: pass
                    supp_code_counter += 1
                    code = f"GYS{supp_code_counter:03d}"
                    uscc = mapped.get("uscc", "") or None
                    supp = Supplier(
                        company_id=company_id, code=code, name=name,
                        uscc=uscc
                    )
                    db.add(supp)
                    db.flush()

                elif module == "department":
                    name = mapped.get("name", "").strip()
                    if not name:
                        errors.append(f"第{i+2}行: 部门名称不能为空")
                        continue
                                        # 编码：优先用导入的编码，为空则自动生成 BM001 格式
                    code = mapped.get("code", "").strip()
                    if not code:
                        if 'dept_code_counter' not in locals():
                            existing_codes = db.query(Department.code).filter(
                                Department.company_id == company_id,
                                Department.code.like('BM%')
                            ).all()
                            dept_code_counter = 0
                            for c in existing_codes:
                                try:
                                    num = int(c[0][2:])
                                    if num > dept_code_counter:
                                        dept_code_counter = num
                                except Exception: pass
                        dept_code_counter += 1
                        code = f"BM{dept_code_counter:03d}"
                    # 编码去重：同编码覆盖更新
                    existing = db.query(Department).filter(
                        Department.company_id == company_id, Department.code == code
                    ).first()
                    if existing:
                        existing.name = name
                    else:
                        db.add(Department(
                            company_id=company_id, code=code, name=name
                        ))
                    db.flush()

                imported += 1
            except Exception as e:
                errors.append(f"第{i+2}行: {str(e)}")

        # 自动添加客户档案（仅开具发票导入时）
        if module == "sales-invoice" and new_customers:
            customer_added = 0
            for (tax_no, name) in new_customers:
                # 先按税号匹配，再按名称匹配
                existing = None
                if tax_no:
                    existing = db.query(Customer).filter(
                        Customer.company_id == company_id,
                        Customer.tax_no == tax_no
                    ).first()
                if not existing:
                    existing = db.query(Customer).filter(
                        Customer.company_id == company_id,
                        Customer.name == name
                    ).first()
                if not existing:
                    # 自动生成编码（用局部变量递增，避免同事务内重复）
                    if 'next_cust_idx' not in locals():
                        existing_count = db.query(Customer).filter(
                            Customer.company_id == company_id
                        ).count()
                        next_cust_idx = existing_count + 1
                    code = f"KH{next_cust_idx:03d}"
                    next_cust_idx += 1
                    cust = Customer(
                        company_id=company_id,
                        code=code,
                        name=name,
                        uscc=tax_no or None,   # 购方识别号 → 统一社会信用代码
                        tax_no=tax_no or None
                    )
                    db.add(cust)
                    customer_added += 1
            if customer_added > 0:
                infos.append(f"自动新增 {customer_added} 个客户到客户档案")

        db.commit()
        return {
            "imported": imported,
            "total": len(rows_data),
            "skipped": len(rows_data) - imported,
            "errors": errors,
            "infos": infos,
            "message": "成功导入 " + str(imported) + "/" + str(len(rows_data)) + " 条记录"
        }
    except Exception as e:
        db.rollback()
        return {"error": f"导入失败：{str(e)}"}


# ═══════════════ 文件解析诊断端点 ═══════════════
@router.get("/api/file/debug")
async def get_file_parse_debug():
    """获取最近一次文件解析的完整诊断追踪。
    当文件导入识别失败时，前端可调用此端点获取详细的诊断信息和修复建议。
    返回：关键词匹配记录、结构分析候选、交叉验证裁决、失败诊断建议。
    """
    trace = _get_last_trace()
    if not trace or not trace.get("filename"):
        return {"ok": False, "message": "暂无文件解析记录，请先上传文件导入"}
    return {
        "ok": True,
        "filename": trace.get("filename", ""),
        "timestamp": trace.get("timestamp", ""),
        "sheets_scanned": trace.get("sheets_scanned", 0),
        "keyword_phase": {
            "matches": trace.get("keyword_phase", {}).get("matches", []),
            "best": trace.get("keyword_phase", {}).get("best")
        },
        "structure_phase": {
            "candidates": trace.get("structure_phase", {}).get("candidates", []),
            "best": trace.get("structure_phase", {}).get("best")
        },
        "cross_validation": trace.get("cross_validation", {}),
        "final_decision": trace.get("final_decision", {}),
        "diagnostics": trace.get("diagnostics", []),
        "suggestions": trace.get("suggestions", []),
    }


# ==================== 信息真实性校验（公用的校验工具） ====================

def validate_uscc(code: str) -> tuple:
    """校验统一社会信用代码 (GB 32100-2015)"""
    if not code or not code.strip():
        return True, ""
    code = code.strip().upper()
    if len(code) != 18:
        return False, "统一社会信用代码必须为18位"
    if not re.match(r'^[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}$', code):
        return False, "统一社会信用代码格式不正确（应为：2位登记管理机关+6位组织机构代码+9位主体标识码+1位校验码）"
    char_map = '0123456789ABCDEFGHJKLMNPQRTUWXY'
    weights = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]
    total = sum(char_map.index(code[i]) * weights[i] for i in range(17))
    check_idx = (31 - total % 31) % 31
    expected = char_map[check_idx]
    if code[17] != expected:
        return False, f"校验码不正确，应为 '{expected}'"
    return True, ""


def validate_id_card(card_no: str) -> tuple:
    """校验中国居民身份证号码 (GB 11643-1999)"""
    if not card_no or not card_no.strip():
        return True, ""
    card_no = card_no.strip().upper()
    if len(card_no) != 18:
        return False, "身份证号码必须为18位"
    if not re.match(r'^\d{17}[\dX]$', card_no):
        return False, "身份证号码前17位必须为数字，第18位为数字或X"
    try:
        birth_str = card_no[6:14]
        birth = date(int(birth_str[0:4]), int(birth_str[4:6]), int(birth_str[6:8]))
        if birth >= date.today():
            return False, "身份证号码中的出生日期不能晚于当前日期"
    except ValueError:
        return False, "身份证号码中的出生日期无效（应为YYYYMMDD格式）"
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_chars = '10X98765432'
    total = sum(int(card_no[i]) * weights[i] for i in range(17))
    expected = check_chars[total % 11]
    if card_no[17] != expected:
        return False, f"身份证校验码不正确，应为 '{expected}'"
    return True, ""


# ==================== Chat AI 助手模块 ====================
# chat_router 已移除（8888税务合规版）
# chat_router 已移除（8888税务合规版）


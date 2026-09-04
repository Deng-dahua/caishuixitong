"""
中小制造业账务处理系统 - 数据库模型（多公司账套版本）
"""
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Numeric, Date, Time, DateTime,
    Text, Boolean, ForeignKey, inspect, text as TextClause, Index,
    func, distinct, or_, and_, event
)
from sqlalchemy.orm import declarative_base, relationship, Session, sessionmaker
import json
from typing import Optional, List
from datetime import datetime, date
from runtime_storage import ACCOUNTING_DB

SQLALCHEMY_DATABASE_URL = "sqlite:///" + ACCOUNTING_DB.as_posix()

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def _configure_sqlite(connection, _record):
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI 依赖注入：生成数据库会话，请求完成后自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==================== 公司账套 ====================

class Company(Base):
    """公司主表 - 每一行代表一个独立的账套"""
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="公司全称")
    uscc = Column(String(50), comment="统一社会信用代码")
    registered_capital = Column(Numeric(18, 2), comment="注册资本")
    established_date = Column(Date, comment="成立日期")
    legal_representative = Column(String(50), comment="法定代表人")
    legal_representative_id = Column(String(30), comment="法定代表人身份证")
    address = Column(String(200), comment="注册地址")
    business_scope = Column(Text, comment="经营范围")
    company_type = Column(String(20), comment="公司类型")
    industry_code = Column(String(30), comment="行业代码(manufacturing/commerce/construction/real_estate/service/technology/catering/logistics/agriculture)")
    created_at = Column(DateTime, default=datetime.now)

    shareholders = relationship("CompanyShareholder", back_populates="company", cascade="all, delete-orphan")
    directors = relationship("CompanyDirector", back_populates="company", cascade="all, delete-orphan")
    supervisors = relationship("CompanySupervisor", back_populates="company", cascade="all, delete-orphan")
    finance_contacts = relationship("CompanyFinanceContact", back_populates="company", cascade="all, delete-orphan")
    vat_declarations = relationship("VATDeclaration", back_populates="company", cascade="all, delete-orphan")
    social_security_declarations = relationship("SocialSecurityDeclaration", back_populates="company", cascade="all, delete-orphan")
    housing_fund_details = relationship("HousingFundDetail", back_populates="company", cascade="all, delete-orphan")
    housing_fund_declarations = relationship("HousingFundDeclaration", back_populates="company", cascade="all, delete-orphan")
    departments = relationship("Department", back_populates="company", cascade="all, delete-orphan")
    employees = relationship("Employee", back_populates="company", cascade="all, delete-orphan")
    customers = relationship("Customer", back_populates="company", cascade="all, delete-orphan")
    suppliers = relationship("Supplier", back_populates="company", cascade="all, delete-orphan")
    accounts = relationship("Account", back_populates="company", cascade="all, delete-orphan")
    periods = relationship("Period", back_populates="company")
    fixed_assets = relationship("FixedAsset", back_populates="company", cascade="all, delete-orphan")
    intangible_assets = relationship("IntangibleAsset", back_populates="company", cascade="all, delete-orphan")
    inventory_items = relationship("InventoryItem", back_populates="company", cascade="all, delete-orphan")
    inventory_transactions = relationship("InventoryTransaction", back_populates="company")
    inventory_balances = relationship("InventoryBalance", back_populates="company")
    contracts = relationship("Contract", back_populates="company", cascade="all, delete-orphan")
    contract_payments = relationship("ContractPayment", back_populates="company")
    payments = relationship("Payment", back_populates="company")
    sales_invoices = relationship("SalesInvoice", back_populates="company")
    purchase_invoices = relationship("PurchaseInvoice", back_populates="company")
    bookkeeping_invoices = relationship("BookkeepingInvoice", back_populates="company")
    bank_transactions = relationship("BankTransaction", back_populates="company")
    input_vat_deductions = relationship("InputVATDeduction", back_populates="company")
    column_templates = relationship("ColumnTemplate", back_populates="company", cascade="all, delete-orphan")
    journal_entries = relationship("JournalEntry", back_populates="company")
    salary_records = relationship("SalaryRecord", back_populates="company", cascade="all, delete-orphan")
    cultural_construction_fee_declarations = relationship("CulturalConstructionFeeDeclaration", back_populates="company", cascade="all, delete-orphan")


class CompanyShareholder(Base):
    __tablename__ = "company_shareholders"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    name = Column(String(50), nullable=False, comment="股东姓名")
    id_number = Column(String(30), comment="身份证号")
    ratio = Column(Numeric(18, 2), comment="持股比例(%)")
    contribution_amount = Column(Numeric(18, 2), comment="认缴出资额")
    company = relationship("Company", back_populates="shareholders")


class CompanyDirector(Base):
    __tablename__ = "company_directors"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    name = Column(String(50), nullable=False, comment="董事姓名")
    id_number = Column(String(30), comment="身份证号")
    company = relationship("Company", back_populates="directors")


class CompanySupervisor(Base):
    __tablename__ = "company_supervisors"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    name = Column(String(50), nullable=False, comment="监事姓名")
    id_number = Column(String(30), comment="身份证号")
    company = relationship("Company", back_populates="supervisors")


class CompanyFinanceContact(Base):
    __tablename__ = "company_finance_contacts"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    name = Column(String(50), nullable=False, comment="财务负责人姓名")
    id_number = Column(String(30), comment="身份证号")
    phone = Column(String(20), comment="联系电话")
    company = relationship("Company", back_populates="finance_contacts")


# ==================== 部门档案 ====================

class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    code = Column(String(20), nullable=False, comment="部门编码")
    name = Column(String(50), nullable=False, comment="部门名称")
    parent_code = Column(String(20), nullable=True, comment="上级部门编码")
    manager = Column(String(50), comment="部门负责人")
    description = Column(String(200), comment="部门说明")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="departments")


# ==================== 人员档案 ====================

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    code = Column(String(20), nullable=False, comment="工号")
    name = Column(String(50), nullable=False, comment="姓名")
    id_card = Column(String(30), comment="身份证号")
    email = Column(String(100), comment="邮箱")
    salary = Column(Numeric(18, 2), default=0.0, comment="基本工资")
    leave_date = Column(Date, comment="离职日期")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="employees")


# ==================== 客户档案 ====================

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    code = Column(String(20), nullable=False, comment="客户编码")
    name = Column(String(100), nullable=False, comment="客户名称")
    tax_no = Column(String(50), comment="税号")
    contact = Column(String(50), comment="联系人")
    phone = Column(String(30), comment="联系电话")
    address = Column(String(200), comment="地址")
    credit_limit = Column(Numeric(18, 2), default=0.0, comment="信用额度")
    payment_terms = Column(Integer, default=30, comment="账期（天）")
    bank_name = Column(String(100), comment="开户银行")
    bank_account = Column(String(50), comment="银行账号")
    uscc = Column(String(50), comment="统一社会信用代码")
    is_active = Column(Boolean, default=True)
    remark = Column(String(200), comment="备注")
    _fingerprint = Column(String(64), comment="全行指纹（去重用）")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="customers")


# ==================== 供应商档案 ====================

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    code = Column(String(20), nullable=False, comment="供应商编码")
    name = Column(String(100), nullable=False, comment="供应商名称")
    tax_no = Column(String(50), comment="税号")
    bank_name = Column(String(100), comment="开户银行")
    bank_account = Column(String(50), comment="银行账号")
    uscc = Column(String(50), comment="统一社会信用代码")
    is_active = Column(Boolean, default=True)
    remark = Column(String(200), comment="备注")
    _fingerprint = Column(String(64), comment="全行指纹（去重用）")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="suppliers")


# ==================== 会计科目 ====================

class Account(Base):
    """会计科目 - 每个公司有独立的科目表"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    code = Column(String(20), nullable=False, comment="科目编码")
    name = Column(String(100), nullable=False, comment="科目名称")
    category = Column(String(20), nullable=False, comment="科目类别：资产/负债/权益/收入/费用/成本")
    balance_direction = Column(String(10), nullable=False, comment="余额方向：借/贷")
    level = Column(Integer, default=1, comment="科目级次")
    parent_code = Column(String(20), nullable=True, comment="上级科目编码")
    is_active = Column(Boolean, default=True)
    opening_balance = Column(Numeric(18, 2), default=0.0, comment="期初金额")
    created_at = Column(DateTime, default=datetime.now)
    company = relationship("Company", back_populates="accounts")


# ==================== 会计期间 ====================

class Period(Base):
    """会计期间 - 每个公司独立管理期间"""
    __tablename__ = "periods"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    period = Column(String(7), nullable=False, comment="YYYY-MM")
    status = Column(String(20), default="开放", comment="开放/已结账")
    closed_at = Column(DateTime, nullable=True)
    company = relationship("Company", back_populates="periods")


# ==================== 固定资产 ====================

class FixedAsset(Base):
    """固定资产卡片"""
    __tablename__ = "fixed_assets"
    __table_args__ = (
        Index('idx_fa_company_status', 'company_id', 'status'),
        Index('idx_fa_company_dept', 'company_id', 'dept_code'),
    )
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    code = Column(String(30), nullable=False, comment="资产编码")
    name = Column(String(100), nullable=False, comment="资产名称")
    category = Column(String(30), nullable=False, comment="资产类别：房屋建筑物/机器设备/运输工具/电子设备/办公设备/其他")
    spec = Column(String(100), comment="规格型号")
    unit = Column(String(10), comment="计量单位")
    dept_code = Column(String(20), comment="使用部门编码")
    location = Column(String(100), comment="存放地点")
    purchase_date = Column(Date, comment="购入日期")
    original_value = Column(Numeric(18, 2), default=0.0, comment="原值")
    residual_value = Column(Numeric(18, 2), default=0.0, comment="预计净残值")
    useful_life_months = Column(Integer, default=60, comment="使用年限（月）")
    accumulated_depreciation = Column(Numeric(18, 2), default=0.0, comment="累计折旧")
    monthly_depreciation = Column(Numeric(18, 2), default=0.0, comment="月折旧额")
    depreciation_method = Column(String(20), default="直线法", comment="折旧方法：直线法/双倍余额递减法/年数总和法")
    status = Column(String(20), default="在用", comment="状态：在用/闲置/报废/出售")
    supplier = Column(String(100), comment="供应商")
    warranty_expiry = Column(Date, comment="保修到期日")
    voucher_no = Column(String(30), comment="入账凭证号")
    disposal_voucher_no = Column(String(30), comment="处置凭证号")
    disposal_date = Column(Date, comment="处置日期")
    disposal_amount = Column(Numeric(18, 2), default=0.0, comment="处置收入")
    remark = Column(Text, comment="备注")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="fixed_assets")


class IntangibleAsset(Base):
    """无形资产卡片"""
    __tablename__ = "intangible_assets"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    code = Column(String(30), nullable=False, comment="资产编码")
    name = Column(String(100), nullable=False, comment="资产名称")
    category = Column(String(30), nullable=False, comment="类别：专利权/商标权/著作权/土地使用权/软件/特许权/其他")
    purchase_date = Column(Date, comment="取得日期")
    original_value = Column(Numeric(18, 2), default=0.0, comment="原值")
    useful_life_months = Column(Integer, default=120, comment="摊销期限（月）")
    accumulated_amortization = Column(Numeric(18, 2), default=0.0, comment="累计摊销")
    monthly_amortization = Column(Numeric(18, 2), default=0.0, comment="月摊销额")
    residual_value = Column(Numeric(18, 2), default=0.0, comment="预计残值")
    status = Column(String(20), default="在用", comment="状态：在用/处置")
    voucher_no = Column(String(30), comment="入账凭证号")
    disposal_voucher_no = Column(String(30), comment="处置凭证号")
    disposal_date = Column(Date, comment="处置日期")
    disposal_amount = Column(Numeric(18, 2), default=0.0, comment="处置收入")
    remark = Column(Text, comment="备注")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="intangible_assets")


class InventoryItem(Base):
    """库存商品/物料档案"""
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    code = Column(String(30), nullable=False, comment="商品编码")
    name = Column(String(100), nullable=False, comment="商品名称")
    spec = Column(String(100), comment="规格型号")
    unit = Column(String(10), comment="计量单位")
    category = Column(String(30), comment="分类：原材料/半成品/产成品/周转材料/低值易耗品")
    warehouse = Column(String(50), comment="仓库")
    safety_stock = Column(Numeric(18, 2), default=0.0, comment="安全库存量")
    current_stock = Column(Numeric(18, 2), default=0.0, comment="当前库存量")
    cost_price = Column(Numeric(18, 2), default=0.0, comment="参考成本价")
    sale_price = Column(Numeric(18, 2), default=0.0, comment="参考售价")
    account_code = Column(String(20), comment="关联会计科目编码")
    is_active = Column(Boolean, default=True)
    remark = Column(String(200), comment="备注")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="inventory_items")


class InventoryTransaction(Base):
    """库存流水"""
    __tablename__ = "inventory_transactions"
    __table_args__ = (
        Index('idx_it_company_item', 'company_id', 'item_code'),
        Index('idx_it_company_date', 'company_id', 'transaction_date'),
    )
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    item_code = Column(String(30), nullable=False, comment="商品编码")
    transaction_date = Column(Date, nullable=False, comment="业务日期")
    trans_type = Column(String(20), nullable=False, comment="类型：入库/出库/调拨入/调拨出/盘盈/盘亏/其他")
    quantity = Column(Numeric(18, 2), nullable=False, comment="数量（+入库/-出库）")
    unit_price = Column(Numeric(18, 2), default=0.0, comment="单价")
    total_amount = Column(Numeric(18, 2), default=0.0, comment="金额")
    warehouse = Column(String(50), comment="仓库")
    warehouse_to = Column(String(50), comment="调入仓库（调拨用）")
    voucher_no = Column(String(30), comment="关联凭证号")
    reference_no = Column(String(50), comment="单据号（入库单/出库单等）")
    operator = Column(String(50), comment="操作人")
    remark = Column(Text, comment="备注")
    created_at = Column(DateTime, default=datetime.now)
    company = relationship("Company", back_populates="inventory_transactions")


class InventoryBalance(Base):
    """库存余额快照（按期计算）"""
    __tablename__ = "inventory_balances"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    item_code = Column(String(30), nullable=False, comment="商品编码")
    period = Column(String(7), nullable=False, comment="期间 YYYY-MM")
    begin_quantity = Column(Numeric(18, 2), default=0.0, comment="期初数量")
    in_quantity = Column(Numeric(18, 2), default=0.0, comment="本期入库数量")
    out_quantity = Column(Numeric(18, 2), default=0.0, comment="本期出库数量")
    end_quantity = Column(Numeric(18, 2), default=0.0, comment="期末数量")
    total_amount = Column(Numeric(18, 2), default=0.0, comment="期末金额")
    created_at = Column(DateTime, default=datetime.now)
    company = relationship("Company", back_populates="inventory_balances")


# ==================== 合同管理 ====================

class Contract(Base):
    """合同台账"""
    __tablename__ = "contracts"
    __table_args__ = (
        Index('idx_contract_company_status', 'company_id', 'status'),
        Index('idx_contract_company_type', 'company_id', 'contract_type'),
    )
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    contract_no = Column(String(50), nullable=False, comment="合同编号")
    name = Column(String(200), nullable=False, comment="合同名称")
    contract_type = Column(String(20), nullable=False, comment="类型：采购/销售/服务/租赁/其他")
    party_a = Column(String(100), comment="甲方")
    party_b = Column(String(100), comment="乙方")
    amount = Column(Numeric(18, 2), default=0.0, comment="合同金额")
    signing_date = Column(Date, comment="签订日期")
    effective_date = Column(Date, comment="生效日期")
    expiry_date = Column(Date, comment="到期日期")
    status = Column(String(20), default="起草中", comment="状态：起草中/已签署/履行中/已完成/已终止")
    responsible_person = Column(String(50), comment="负责人")
    dept_code = Column(String(20), comment="部门编码")
    content_summary = Column(Text, comment="内容摘要")
    remark = Column(Text, comment="备注")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="contracts")


class ContractPayment(Base):
    """合同收付款计划"""
    __tablename__ = "contract_payments"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False)
    payment_no = Column(Integer, default=1, comment="期次")
    payment_type = Column(String(10), nullable=False, comment="收款/付款")
    amount = Column(Numeric(18, 2), nullable=False, comment="金额")
    due_date = Column(Date, comment="到期日期")
    paid_date = Column(Date, comment="实际收付日期")
    paid_amount = Column(Numeric(18, 2), default=0.0, comment="实收/实付金额")
    status = Column(String(20), default="未付", comment="状态：未付/部分已付/已付清")
    remark = Column(String(200), comment="备注")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="contract_payments")


# ==================== 付款管理 ====================

class Payment(Base):
    """付款记录"""
    __tablename__ = "payments"
    __table_args__ = (
        Index('idx_payment_company_status', 'company_id', 'status'),
        Index('idx_payment_company_supplier', 'company_id', 'supplier_id'),
    )
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    payment_type = Column(String(10), nullable=False, default="外部单位", comment="类型：内部人员/外部单位")
    scenario = Column(String(20), comment="情形：备用金/报销/借支（内部人员）或 预付款/应付款（外部单位）")
    payment_no = Column(String(50), nullable=False, comment="付款单号")
    payment_date = Column(Date, nullable=False, comment="付款日期")
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True, comment="内部人员ID")
    employee_name = Column(String(50), comment="内部人员姓名")
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True, comment="供应商ID（外部单位）")
    supplier_name = Column(String(100), comment="供应商名称")
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=True, comment="关联合同ID")
    contract_no = Column(String(50), comment="关联合同编号")
    amount = Column(Numeric(18, 2), nullable=False, comment="金额")
    payment_method = Column(String(20), nullable=False, default="银行转账", comment="付款方式：银行转账/现金/支票/其他")
    payee = Column(String(100), comment="收款方")
    payee_account = Column(String(50), comment="收款账号")
    payee_bank = Column(String(100), comment="收款银行")
    status = Column(String(20), default="待审批", comment="状态：待审批/已审批/已付款/已驳回")
    approved_by = Column(String(50), comment="审批人")
    approved_at = Column(DateTime, comment="审批时间")
    paid_at = Column(DateTime, comment="实际付款时间")
    department = Column(String(50), comment="所属部门")
    purpose = Column(String(200), comment="用途说明")
    remark = Column(Text, comment="备注")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="payments")


# ==================== 开具发票（销售发票）====================

class SalesInvoice(Base):
    """开具发票 - 企业开出的销售发票"""
    __tablename__ = "sales_invoices"
    __table_args__ = (
        Index('idx_si_company_date', 'company_id', 'invoice_date'),
        Index('idx_si_company_buyer', 'company_id', 'buyer_name'),
        Index('idx_si_company_status', 'company_id', 'status'),
    )
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    # 发票基本信息
    invoice_code = Column(String(30), comment="发票代码")
    invoice_no = Column(String(30), comment="发票号码")
    digital_invoice_no = Column(String(50), comment="数电发票号码")
    # 销方信息
    seller_tax_no = Column(String(50), comment="销方识别号")
    seller_name = Column(String(100), nullable=False, comment="销方名称")
    # 购方信息
    buyer_tax_no = Column(String(50), comment="购方识别号")
    buyer_name = Column(String(100), nullable=False, comment="购买方名称")
    # 发票日期与分类
    invoice_date = Column(Date, nullable=False, comment="开票日期")
    tax_category_code = Column(String(30), comment="税收分类编码")
    specific_business_type = Column(String(50), comment="特定业务类型")
    # 货物明细
    goods_name = Column(String(200), comment="货物或应税劳务名称")
    spec = Column(String(100), comment="规格型号")
    unit = Column(String(10), comment="单位")
    quantity = Column(Numeric(18, 2), default=0, comment="数量")
    unit_price = Column(Numeric(18, 2), default=0, comment="单价")
    # 金额信息
    amount = Column(Numeric(18, 2), nullable=False, default=0.0, comment="金额（不含税）")
    tax_rate = Column(Numeric(18, 2), nullable=False, default=0.0, comment="税率（%）")
    tax_amount = Column(Numeric(18, 2), nullable=False, default=0.0, comment="税额")
    total_amount = Column(Numeric(18, 2), nullable=False, default=0.0, comment="价税合计")
    # 发票属性
    invoice_source = Column(String(20), comment="发票来源")
    invoice_category = Column(String(20), nullable=False, default="增值税专用发票", comment="发票票种：增值税专用发票/增值税普通发票/电子普通发票/其他")
    status = Column(String(20), nullable=False, default="正常", comment="发票状态：正常/作废/红冲")
    is_positive = Column(Boolean, default=True, comment="是否正数发票")
    invoice_risk_level = Column(String(10), comment="发票风险等级")
    # 其他
    issuer = Column(String(30), comment="开票人")
    remark = Column(Text, comment="备注")
    raw_data = Column(Text, comment="导入时的额外列数据JSON")
    _fingerprint = Column(String(64), comment="全行指纹（去重用）")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="sales_invoices")

# ==================== 取得发票（采购发票）====================

class PurchaseInvoice(Base):
    """取得发票 - 企业收到的采购发票"""
    __tablename__ = "purchase_invoices"
    __table_args__ = (
        Index('idx_pi_company_date', 'company_id', 'invoice_date'),
        Index('idx_pi_company_seller', 'company_id', 'seller_name'),
    )
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    # 发票基本信息
    invoice_code = Column(String(30), comment="发票代码")
    invoice_no = Column(String(30), comment="发票号码")
    digital_invoice_no = Column(String(50), comment="数电发票号码")
    # 销方信息
    seller_tax_no = Column(String(50), comment="销方识别号")
    seller_name = Column(String(100), nullable=False, comment="销方名称")
    # 购方信息
    buyer_tax_no = Column(String(50), comment="购方识别号")
    buyer_name = Column(String(100), nullable=False, comment="购买方名称")
    # 发票日期与分类
    invoice_date = Column(Date, nullable=False, comment="开票日期")
    tax_category_code = Column(String(30), comment="税收分类编码")
    specific_business_type = Column(String(50), comment="特定业务类型")
    # 货物明细
    goods_name = Column(String(200), comment="货物或应税劳务名称")
    spec = Column(String(100), comment="规格型号")
    unit = Column(String(10), comment="单位")
    quantity = Column(Numeric(18, 2), default=0, comment="数量")
    unit_price = Column(Numeric(18, 2), default=0, comment="单价")
    # 金额信息
    amount = Column(Numeric(18, 2), nullable=False, default=0.0, comment="金额（不含税）")
    tax_rate = Column(Numeric(18, 2), nullable=False, default=0.0, comment="税率（%）")
    tax_amount = Column(Numeric(18, 2), nullable=False, default=0.0, comment="税额")
    total_amount = Column(Numeric(18, 2), nullable=False, default=0.0, comment="价税合计")
    # 发票属性
    invoice_source = Column(String(20), comment="发票来源")
    invoice_category = Column(String(20), nullable=False, default="增值税专用发票", comment="发票票种：增值税专用发票/增值税普通发票/电子普通发票/其他")
    status = Column(String(20), nullable=False, default="正常", comment="发票状态：正常/作废/红冲")
    is_positive = Column(Boolean, default=True, comment="是否正数发票")
    invoice_risk_level = Column(String(10), comment="发票风险等级")
    # 其他
    issuer = Column(String(30), comment="开票人")
    remark = Column(Text, comment="备注")
    raw_data = Column(Text, comment="导入时的额外列数据JSON")
    _fingerprint = Column(String(64), comment="全行指纹（去重用）")
    skip_accounting = Column(Boolean, default=False, comment="暂不记账：True=该发票暂不生成序时账凭证")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="purchase_invoices")


class BookkeepingInvoice(Base):
    """记账发票 - 企业收到的普通发票/收据等（不入进项抵扣体系）"""
    __tablename__ = "bookkeeping_invoices"
    __table_args__ = (
        Index('idx_bi_company_date', 'company_id', 'invoice_date'),
        Index('idx_bi_company_seller', 'company_id', 'seller_name'),
    )
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    # 发票基本信息
    invoice_code = Column(String(30), comment="发票代码")
    invoice_no = Column(String(30), comment="发票号码")
    digital_invoice_no = Column(String(50), comment="数电发票号码")
    # 销方信息
    seller_tax_no = Column(String(50), comment="销方识别号")
    seller_name = Column(String(100), nullable=False, comment="销方名称")
    # 购方信息
    buyer_tax_no = Column(String(50), comment="购方识别号")
    buyer_name = Column(String(100), nullable=False, comment="购买方名称")
    # 发票日期与分类
    invoice_date = Column(Date, nullable=False, comment="开票日期")
    tax_category_code = Column(String(30), comment="税收分类编码")
    specific_business_type = Column(String(50), comment="特定业务类型")
    # 货物明细
    goods_name = Column(String(200), comment="货物或应税劳务名称")
    spec = Column(String(100), comment="规格型号")
    unit = Column(String(10), comment="单位")
    quantity = Column(Numeric(18, 2), default=0, comment="数量")
    unit_price = Column(Numeric(18, 2), default=0, comment="单价")
    # 金额信息
    amount = Column(Numeric(18, 2), nullable=False, default=0.0, comment="金额（不含税）")
    tax_rate = Column(Numeric(18, 2), nullable=False, default=0.0, comment="税率（%）")
    tax_amount = Column(Numeric(18, 2), nullable=False, default=0.0, comment="税额")
    total_amount = Column(Numeric(18, 2), nullable=False, default=0.0, comment="价税合计")
    # 发票属性
    invoice_source = Column(String(20), comment="发票来源")
    invoice_category = Column(String(20), nullable=False, default="增值税普通发票", comment="发票票种")
    status = Column(String(20), nullable=False, default="正常", comment="发票状态：正常/作废/红冲")
    is_positive = Column(Boolean, default=True, comment="是否正数发票")
    invoice_risk_level = Column(String(10), comment="发票风险等级")
    # 其他
    issuer = Column(String(30), comment="开票人")
    remark = Column(Text, comment="备注")
    voucher_no = Column(String(30), comment="凭证号（为空表示未记账）")
    raw_data = Column(Text, comment="导入时的额外列数据JSON")
    _fingerprint = Column(String(64), comment="全行指纹（去重用）")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="bookkeeping_invoices")


# ==================== 银行配置（不同银行不同列映射）====================

class BankTransaction(Base):
    """银行流水 - 归一化核心字段 + raw_data JSON 存额外列"""
    __tablename__ = "bank_transactions"
    __table_args__ = (
        Index('idx_bt_company_date', 'company_id', 'transaction_date'),
        Index('idx_bt_company_type', 'company_id', 'transaction_type'),
    )
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    transaction_date = Column(Date, nullable=False, comment="交易日期")
    transaction_time = Column(Time, nullable=True, comment="交易时间")
    application_date = Column(Date, nullable=True, comment="申请日期")
    voucher_no = Column(String(30), comment="凭证号")
    debit_amount = Column(Numeric(18, 2), default=0.0, comment="借方金额")
    credit_amount = Column(Numeric(18, 2), default=0.0, comment="贷方金额")
    balance = Column(Numeric(18, 2), default=0.0, comment="余额")
    counterparty_account = Column(String(50), comment="对方账号")
    counterparty_name = Column(String(100), comment="对方户名")
    counterparty_bank = Column(String(100), comment="对方行名")
    transaction_serial_no = Column(String(50), comment="交易流水号")
    voucher_seq = Column(String(30), comment="传票序号")
    record_status = Column(String(20), comment="记录状态")
    summary = Column(String(300), comment="摘要/用途")
    transaction_remark = Column(Text, comment="交易附言")
    account_type = Column(String(30), comment="客户账户类型")
    # === 旧字段（保留向后兼容） ===
    amount = Column(Numeric(18, 2), default=0.0, comment="交易金额（旧：收入为正/支出为负）")
    transaction_type = Column(String(20), default="支出", comment="类型（旧）")
    payment_method = Column(String(30), comment="结算方式（旧）")
    reference_no = Column(String(50), comment="银行流水号（旧）")
    raw_data = Column(Text, comment="原始数据JSON（旧）")
    journal_voucher_no = Column(String(30), comment="关联序时账凭证号")
    remark = Column(Text, comment="备注（旧）")
    _fingerprint = Column(String(64), comment="全行指纹（去重用）")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="bank_transactions")


# ==================== 进项抵扣 ====================

class InputVATDeduction(Base):
    """进项抵扣管理 - 进项发票认证抵扣台账"""
    __tablename__ = "input_vat_deductions"
    __table_args__ = (
        Index('idx_ivd_company_check_time', 'company_id', 'check_time'),
        Index('idx_ivd_company_invoice', 'company_id', 'purchase_invoice_id'),
        Index('idx_ivd_status', 'company_id', 'invoice_status'),
    )
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    purchase_invoice_id = Column(Integer, ForeignKey("purchase_invoices.id"), nullable=True, comment="关联取得发票ID")
    # 核心发票信息
    check_status = Column(String(10), comment="勾选状态：已勾选/未勾选")
    invoice_source = Column(String(50), comment="发票来源，如：勾选平台/扫描认证/手工录入")
    domestic_sale_cert_no = Column(String(50), comment="转内销证明编号")
    digital_invoice_no = Column(String(50), comment="数电发票号码")
    invoice_code = Column(String(30), comment="发票代码")
    invoice_no = Column(String(30), comment="发票号码")
    invoice_date = Column(Date, comment="开票日期")
    seller_tax_id = Column(String(30), comment="销售方纳税人识别号")
    seller_name = Column(String(100), comment="销方名称")
    amount = Column(Numeric(18, 2), default=0.0, comment="金额（不含税）")
    tax_amount = Column(Numeric(18, 2), default=0.0, comment="税额")
    deductible_tax_amount = Column(Numeric(18, 2), default=0.0, comment="有效抵扣税额")
    # 票种信息
    invoice_category = Column(String(50), comment="票种，如：数电发票（增值税专用发票）")
    invoice_category_label = Column(String(30), comment="票种标签")
    invoice_status = Column(String(20), default="正常", comment="发票状态：正常/作废/红冲")
    # 勾选与风险
    check_time = Column(DateTime, comment="勾选时间")
    risk_level = Column(String(20), default="正常", comment="发票风险等级：正常/疑点/异常/失控")
    # 保留字段（历史兼容）
    goods_name = Column(String(200), comment="货物名称")
    total_amount = Column(Numeric(18, 2), default=0.0, comment="价税合计")
    tax_rate = Column(Numeric(18, 2), default=0.0, comment="税率（%）")
    deducted_tax_amount = Column(Numeric(18, 2), default=0.0, comment="已抵扣税额")
    deduction_period = Column(String(7), comment="抵扣所属期 YYYY-MM")
    deduction_status = Column(String(20), default="待抵扣", comment="抵扣状态：待认证/待抵扣/已抵扣/部分抵扣/不得抵扣")
    certification_date = Column(Date, comment="认证日期")
    deduction_date = Column(Date, comment="抵扣日期")
    deduction_method = Column(String(30), default="凭票抵扣", comment="抵扣方式：凭票抵扣/计算抵扣/核定抵扣")
    voucher_no = Column(String(30), comment="关联凭证号")
    remark = Column(Text, comment="备注")
    raw_data = Column(Text, comment="导入时的额外列数据JSON")
    import_batch_id = Column(String(36), comment="导入批次ID，同一次导入共享")
    _fingerprint = Column(String(64), comment="全行指纹（去重用）")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="input_vat_deductions")


# ==================== 列映射模板（动态表头）====================

class ColumnTemplate(Base):
    """列映射模板 - 保存各模块上传文件的列对应关系"""
    __tablename__ = "column_templates"
    __table_args__ = (
    )
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    module = Column(String(30), nullable=False, comment="模块：sales-invoice/purchase-invoice/bank-transaction")
    template_name = Column(String(100), nullable=False, comment="模板名称，如：工行流水模板")
    column_mapping = Column(Text, comment="列映射JSON：{标准字段: 文件列名}")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="column_templates")


class JournalEntry(Base):
    """序时账 - 按日期顺序记录所有会计分录"""
    __tablename__ = "journal_entries"
    __table_args__ = (
        Index('idx_je_company_date', 'company_id', 'entry_date'),
        Index('idx_je_company_period', 'company_id', 'period'),
        Index('idx_je_company_voucher', 'company_id', 'voucher_word', 'voucher_no'),
    )
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    entry_date = Column(Date, nullable=False, comment="日期")
    period = Column(String(7), nullable=False, comment="会计期间 YYYY-MM")
    voucher_word = Column(String(10), nullable=False, default="记", comment="凭证字：记/收/付/转")
    voucher_no = Column(Integer, nullable=False, comment="凭证号")
    attach_count = Column(Integer, default=0, comment="附单据数")
    summary = Column(Text, comment="摘要")
    account_code = Column(String(20), nullable=False, comment="科目编码")
    account_name = Column(String(100), comment="科目名称")
    debit_amount = Column(Numeric(18, 2), default=0.0, comment="借方金额")
    credit_amount = Column(Numeric(18, 2), default=0.0, comment="贷方金额")
    prepared_by = Column(String(50), comment="制单人")
    reviewed_by = Column(String(50), comment="复核人")
    is_reviewed = Column(Boolean, default=False, comment="是否复核")
    reviewed_at = Column(DateTime, comment="复核时间")
    remark = Column(Text, comment="备注")
    contact_project = Column(String(100), comment="往来项目")
    spec_model = Column(String(100), comment="规格型号")
    quantity = Column(Numeric(18, 2), default=0.0, comment="数量")
    unit = Column(String(20), comment="单位")
    unit_price = Column(Numeric(18, 2), default=0.0, comment="单价")
    source = Column(String(50), default="手动录入", comment="凭证来源：手动录入/销项发票/进项抵扣/银行流水")
    ref_id = Column(Integer, comment="关联业务ID（销项发票=SalesInvoice.id, 进项抵扣=InputVATDeduction.id）")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    company = relationship("Company", back_populates="journal_entries")


# ==================== 数据库迁移与初始化 ====================

def migrate_schema(db):
    """迁移旧数据库到多公司架构"""
    inspector = inspect(engine)

    # ── 1. 创建 companies 表（如果不存在） ──
    if "companies" not in inspector.get_table_names():
        Base.metadata.create_all(bind=engine, tables=[Company.__table__])

    # ── 1.5. 为 companies 补充新增字段（必须在查询 Company 之前） ──
    if "companies" in inspector.get_table_names():
        existing_cols = {c["name"] for c in inspector.get_columns("companies")}
        company_new_cols = {
            "registered_capital": "ALTER TABLE companies ADD COLUMN registered_capital FLOAT",
            "established_date": "ALTER TABLE companies ADD COLUMN established_date DATE",
            "legal_representative": "ALTER TABLE companies ADD COLUMN legal_representative VARCHAR(50)",
            "legal_representative_id": "ALTER TABLE companies ADD COLUMN legal_representative_id VARCHAR(30)",
            "address": "ALTER TABLE companies ADD COLUMN address VARCHAR(200)",
            "business_scope": "ALTER TABLE companies ADD COLUMN business_scope TEXT",
        }
        for col_name, sql in company_new_cols.items():
            if col_name not in existing_cols:
                try:
                    db.execute(TextClause(sql))
                    db.commit()
                    print(f"已为 companies 添加 {col_name} 列")
                except Exception as e:
                    db.rollback()
                    print(f"companies 添加 {col_name} 列失败: {e}")
        # 创建子表
        for sub_table in [CompanyShareholder.__table__, CompanyDirector.__table__,
                          CompanySupervisor.__table__, CompanyFinanceContact.__table__]:
            table_name = sub_table.name
            if table_name not in inspector.get_table_names():
                try:
                    sub_table.create(bind=engine)
                    db.commit()
                    print(f"已创建子表 {table_name}")
                except Exception as e:
                    db.rollback()
                    print(f"创建子表 {table_name} 失败: {e}")

    # ── 2. 给所有表增加 company_id 列 ──
    migrations = {
        "departments": "ALTER TABLE departments ADD COLUMN company_id INTEGER NOT NULL DEFAULT 1",
        "employees": "ALTER TABLE employees ADD COLUMN company_id INTEGER NOT NULL DEFAULT 1",
        "customers": "ALTER TABLE customers ADD COLUMN company_id INTEGER NOT NULL DEFAULT 1",
        "suppliers": "ALTER TABLE suppliers ADD COLUMN company_id INTEGER NOT NULL DEFAULT 1",
        "accounts": "ALTER TABLE accounts ADD COLUMN company_id INTEGER NOT NULL DEFAULT 1",
        "periods": "ALTER TABLE periods ADD COLUMN company_id INTEGER NOT NULL DEFAULT 1",
    }

    for table_name, sql in migrations.items():
        try:
            existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
            if "company_id" not in existing_cols:
                db.execute(TextClause(sql))
                db.commit()
                print(f"已为 {table_name} 添加 company_id 列")
        except Exception as e:
            db.rollback()
            print(f"迁移 {table_name} 跳过（可能已存在）: {e}")

    # ── 4. 补充 uscc 列 ──
    extra_cols = {
        "company_info": "ALTER TABLE company_info ADD COLUMN uscc VARCHAR(50)",
        "customers": "ALTER TABLE customers ADD COLUMN uscc VARCHAR(50)",
        "suppliers": "ALTER TABLE suppliers ADD COLUMN uscc VARCHAR(50)",
    }
    for table_name, sql in extra_cols.items():
        try:
            if table_name in inspector.get_table_names():
                existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
                if "uscc" not in existing_cols:
                    db.execute(TextClause(sql))
                    db.commit()
        except Exception:
            db.rollback()

    # ── 6. 付款管理：重命名 payment_type 值 + 添加 scenario 列 ──
    if "payments" in inspector.get_table_names():
        existing_cols = {c["name"] for c in inspector.get_columns("payments")}
        # 添加 scenario 列
        if "scenario" not in existing_cols:
            try:
                db.execute(TextClause("ALTER TABLE payments ADD COLUMN scenario VARCHAR(20)"))
                db.commit()
                print("已为 payments 添加 scenario 列")
            except Exception as e:
                db.rollback()
                print(f"payments 添加 scenario 列失败: {e}")
        # 重命名内部报销 → 内部人员
        try:
            db.execute(TextClause("UPDATE payments SET payment_type = '内部人员' WHERE payment_type = '内部报销'"))
            db.commit()
        except Exception as e:
            db.rollback()
        # 重命名外部支付 → 外部单位
        try:
            db.execute(TextClause("UPDATE payments SET payment_type = '外部单位' WHERE payment_type = '外部支付'"))
            db.commit()
        except Exception as e:
            db.rollback()

    # ── 7.1 客户档案 _fingerprint 字段扩展 ──
    if "customers" in inspector.get_table_names():
        existing_cols = {c["name"] for c in inspector.get_columns("customers")}
        new_cust_cols = {
            "_fingerprint": "ALTER TABLE customers ADD COLUMN _fingerprint VARCHAR(64)",
        }
        for col, sql in new_cust_cols.items():
            if col not in existing_cols:
                try:
                    db.execute(TextClause(sql))
                    db.commit()
                    print(f"已为 customers 添加字段: {col}")
                except Exception as e:
                    db.rollback()
                    print(f"customers 添加字段 {col} 失败（可能已存在）: {e}")

    # ── 7.2 销售发票字段扩展（数电发票、销方、风险等级等） ──
    if "sales_invoices" in inspector.get_table_names():
        existing_cols = {c["name"] for c in inspector.get_columns("sales_invoices")}
        new_si_cols = {
            "digital_invoice_no": "ALTER TABLE sales_invoices ADD COLUMN digital_invoice_no VARCHAR(50)",
            "seller_tax_no": "ALTER TABLE sales_invoices ADD COLUMN seller_tax_no VARCHAR(50)",
            "seller_name": "ALTER TABLE sales_invoices ADD COLUMN seller_name VARCHAR(100)",
            "tax_category_code": "ALTER TABLE sales_invoices ADD COLUMN tax_category_code VARCHAR(30)",
            "specific_business_type": "ALTER TABLE sales_invoices ADD COLUMN specific_business_type VARCHAR(50)",
            "invoice_source": "ALTER TABLE sales_invoices ADD COLUMN invoice_source VARCHAR(20)",
            "is_positive": "ALTER TABLE sales_invoices ADD COLUMN is_positive BOOLEAN DEFAULT 1",
            "invoice_risk_level": "ALTER TABLE sales_invoices ADD COLUMN invoice_risk_level VARCHAR(10)",
            "issuer": "ALTER TABLE sales_invoices ADD COLUMN issuer VARCHAR(30)",
            "invoice_category": "ALTER TABLE sales_invoices ADD COLUMN invoice_category VARCHAR(20)",
            "_fingerprint": "ALTER TABLE sales_invoices ADD COLUMN _fingerprint VARCHAR(64)",
        }
        for col, sql in new_si_cols.items():
            if col not in existing_cols:
                try:
                    db.execute(TextClause(sql))
                    db.commit()
                    print(f"已为 sales_invoices 添加字段: {col}")
                except Exception as e:
                    db.rollback()
                    print(f"sales_invoices 添加字段 {col} 失败（可能已存在）: {e}")
        # 将旧 invoice_type 数据迁移到 invoice_category
        if "invoice_type" in existing_cols and "invoice_category" in existing_cols or "invoice_category" not in existing_cols:
            pass
        if "invoice_type" in existing_cols:
            try:
                db.execute(TextClause("UPDATE sales_invoices SET invoice_category = invoice_type WHERE invoice_category IS NULL"))
                db.commit()
                print("已迁移 sales_invoices.invoice_type → invoice_category")
            except Exception as e:
                db.rollback()

    # ── 8. 取得发票字段扩展（数电发票、购方、风险等级等） ──
    if "purchase_invoices" in inspector.get_table_names():
        existing_cols = {c["name"] for c in inspector.get_columns("purchase_invoices")}
        new_pi_cols = {
            "digital_invoice_no": "ALTER TABLE purchase_invoices ADD COLUMN digital_invoice_no VARCHAR(50)",
            "buyer_tax_no": "ALTER TABLE purchase_invoices ADD COLUMN buyer_tax_no VARCHAR(50)",
            "buyer_name": "ALTER TABLE purchase_invoices ADD COLUMN buyer_name VARCHAR(100)",
            "tax_category_code": "ALTER TABLE purchase_invoices ADD COLUMN tax_category_code VARCHAR(30)",
            "specific_business_type": "ALTER TABLE purchase_invoices ADD COLUMN specific_business_type VARCHAR(50)",
            "invoice_source": "ALTER TABLE purchase_invoices ADD COLUMN invoice_source VARCHAR(20)",
            "is_positive": "ALTER TABLE purchase_invoices ADD COLUMN is_positive BOOLEAN DEFAULT 1",
            "invoice_risk_level": "ALTER TABLE purchase_invoices ADD COLUMN invoice_risk_level VARCHAR(10)",
            "issuer": "ALTER TABLE purchase_invoices ADD COLUMN issuer VARCHAR(30)",
            "invoice_category": "ALTER TABLE purchase_invoices ADD COLUMN invoice_category VARCHAR(20)",
            "_fingerprint": "ALTER TABLE purchase_invoices ADD COLUMN _fingerprint VARCHAR(64)",
        }
        for col, sql in new_pi_cols.items():
            if col not in existing_cols:
                try:
                    db.execute(TextClause(sql))
                    db.commit()
                    print(f"已为 purchase_invoices 添加字段: {col}")
                except Exception as e:
                    db.rollback()
                    print(f"purchase_invoices 添加字段 {col} 失败（可能已存在）: {e}")
        # 将旧 invoice_type 数据迁移到 invoice_category
        if "invoice_type" in existing_cols:
            try:
                db.execute(TextClause("UPDATE purchase_invoices SET invoice_category = invoice_type WHERE invoice_category IS NULL"))
                db.commit()
                print("已迁移 purchase_invoices.invoice_type → invoice_category")
            except Exception as e:
                db.rollback()

    # ── 8.05 记账发票表（复刻取得发票，独立建表） ──
    if "bookkeeping_invoices" not in inspector.get_table_names():
        try:
            db.execute(TextClause("""
                CREATE TABLE bookkeeping_invoices (
                    id INTEGER NOT NULL,
                    company_id INTEGER NOT NULL,
                    invoice_code VARCHAR(30),
                    invoice_no VARCHAR(30),
                    digital_invoice_no VARCHAR(50),
                    seller_tax_no VARCHAR(50),
                    seller_name VARCHAR(100),
                    buyer_tax_no VARCHAR(50),
                    buyer_name VARCHAR(100),
                    invoice_date DATE,
                    tax_category_code VARCHAR(30),
                    specific_business_type VARCHAR(50),
                    goods_name VARCHAR(200),
                    spec VARCHAR(100),
                    unit VARCHAR(10),
                    quantity NUMERIC(18,2) DEFAULT 0,
                    unit_price NUMERIC(18,2) DEFAULT 0,
                    amount NUMERIC(18,2) NOT NULL DEFAULT 0.0,
                    tax_rate NUMERIC(18,2) NOT NULL DEFAULT 0.0,
                    tax_amount NUMERIC(18,2) NOT NULL DEFAULT 0.0,
                    total_amount NUMERIC(18,2) NOT NULL DEFAULT 0.0,
                    invoice_source VARCHAR(20),
                    invoice_category VARCHAR(20) NOT NULL DEFAULT '增值税普通发票',
                    status VARCHAR(20) NOT NULL DEFAULT '正常',
                    is_positive BOOLEAN DEFAULT 1,
                    invoice_risk_level VARCHAR(10),
                    issuer VARCHAR(30),
                    remark TEXT,
                    raw_data TEXT,
                    _fingerprint VARCHAR(64),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    FOREIGN KEY (company_id) REFERENCES companies (id)
                )
            """))
            db.commit()
            print("已创建 bookkeeping_invoices 表")
        except Exception as e:
            db.rollback()
            print(f"创建 bookkeeping_invoices 表失败: {e}")

    # ── 8.06 取得发票：删除认证/抵扣字段（认证状态、认证日期、抵扣期间、抵扣率） ──
    if "purchase_invoices" in inspector.get_table_names():
        existing_cols = {c["name"] for c in inspector.get_columns("purchase_invoices")}
        for col in ["certification_status", "certification_date", "deduction_period", "deduction_rate"]:
            if col in existing_cols:
                try:
                    db.execute(TextClause(f"ALTER TABLE purchase_invoices DROP COLUMN {col}"))
                    db.commit()
                    print(f"已删除 purchase_invoices.{col}")
                except Exception as e:
                    db.rollback()
                    print(f"删除 purchase_invoices.{col} 失败（可能不支持 DROP COLUMN）: {e}")

    # ── 8.1 银行流水 _fingerprint 字段 ──
    if "bank_transactions" in inspector.get_table_names():
        existing_cols = {c["name"] for c in inspector.get_columns("bank_transactions")}
        bt_new_cols = {
            "_fingerprint": "ALTER TABLE bank_transactions ADD COLUMN _fingerprint VARCHAR(64)",
        }
        for col, sql in bt_new_cols.items():
            if col not in existing_cols:
                try:
                    db.execute(TextClause(sql))
                    db.commit()
                    print(f"已为 bank_transactions 添加字段: {col}")
                except Exception as e:
                    db.rollback()
                    print(f"bank_transactions 添加字段 {col} 失败（可能已存在）: {e}")

    # ── 8.2 进项抵扣 _fingerprint 字段 ──
    if "input_vat_deductions" in inspector.get_table_names():
        existing_cols = {c["name"] for c in inspector.get_columns("input_vat_deductions")}
        ivd_new_cols = {
            "_fingerprint": "ALTER TABLE input_vat_deductions ADD COLUMN _fingerprint VARCHAR(64)",
        }
        for col, sql in ivd_new_cols.items():
            if col not in existing_cols:
                try:
                    db.execute(TextClause(sql))
                    db.commit()
                    print(f"已为 input_vat_deductions 添加字段: {col}")
                except Exception as e:
                    db.rollback()
                    print(f"input_vat_deductions 添加字段 {col} 失败（可能已存在）: {e}")

    # ── 9. 发票号码和开票日期改为可空 ──
    for table_name in ("sales_invoices", "purchase_invoices"):
        if table_name in inspector.get_table_names():
            cols = {c["name"]: c for c in inspector.get_columns(table_name)}
            # 如果还需要修复，仅尝试 ALTER COLUMN（SQLite 不支持），
            # 实际情况是 create_all() 已按模型建表，无需重建
            # 清理可能残留的空备份表
            backup_table = f"{table_name}_bk"
            if backup_table in inspector.get_table_names():
                try:
                    db.execute(TextClause(f"DROP TABLE IF EXISTS {backup_table}"))
                    db.commit()
                    print(f"已清理残留备份表 {backup_table}")
                except Exception as e:
                    db.rollback()
                    print(f"清理 {backup_table} 跳过: {e}")


    # ── 11. JournalEntry 新增5个字段 ──
    if "journal_entries" in inspector.get_table_names():
        je_cols = {c["name"] for c in inspector.get_columns("journal_entries")}
        for col_name, col_def in [
            ("contact_project", "TEXT"),
            ("spec_model", "TEXT"),
            ("quantity", "REAL DEFAULT 0.0"),
            ("unit", "TEXT"),
            ("unit_price", "REAL DEFAULT 0.0"),
        ]:
            if col_name not in je_cols:
                try:
                    # safe: col_name/col_def 来自硬编码列表，无注入风险
                    db.execute(TextClause(f"ALTER TABLE journal_entries ADD COLUMN {col_name} {col_def}"))
                    db.commit()
                    print(f"  [OK] 已添加 journal_entries.{col_name}")
                except Exception as e:
                    db.rollback()
                    print(f"  [X] journal_entries.{col_name} 迁移失败: {e}")

    # ── 11.5. JournalEntry 新增 source 列 ──
    if "journal_entries" in inspector.get_table_names():
        je_cols = {c["name"] for c in inspector.get_columns("journal_entries")}
        if "source" not in je_cols:
            try:
                db.execute(TextClause("ALTER TABLE journal_entries ADD COLUMN source VARCHAR(50) DEFAULT '手动录入'"))
                db.commit()
                print("  [OK] 已添加 journal_entries.source")
            except Exception as e:
                db.rollback()
                print(f"  [X] journal_entries.source 迁移失败: {e}")
        if "ref_id" not in je_cols:
            try:
                db.execute(TextClause("ALTER TABLE journal_entries ADD COLUMN ref_id INTEGER"))
                db.commit()
                print("  [OK] 已添加 journal_entries.ref_id")
            except Exception as e:
                db.rollback()
                print(f"  [X] journal_entries.ref_id 迁移失败: {e}")

    # ── 12. 已有公司补充 销项税额 科目（221001001） ──
    if "accounts" in inspector.get_table_names():
        companies = db.query(Company).order_by(Company.id).all()
        for comp in companies:
            existing = db.query(Account).filter(
                Account.company_id == comp.id,
                Account.code == "221001001"
            ).first()
            if not existing:
                try:
                    db.add(Account(
                        company_id=comp.id,
                        code="221001001", name="销项税额",
                        category="负债", balance_direction="贷",
                        level=3, parent_code="221001"
                    ))
                    db.commit()
                    print(f"  [OK] 为 {comp.name} 添加科目 221001001 销项税额")
                except Exception as e:
                    db.rollback()
                    print(f"  [X] 221001001 销项税额 迁移失败: {e}")

    # ── 12.5. 已有公司补充 待认证进项税额 科目（221001003） ──
    if "accounts" in inspector.get_table_names():
        companies = db.query(Company).order_by(Company.id).all()
        for comp in companies:
            existing = db.query(Account).filter(
                Account.company_id == comp.id,
                Account.code == "221001003"
            ).first()
            if not existing:
                try:
                    db.add(Account(
                        company_id=comp.id,
                        code="221001003", name="待认证进项税额",
                        category="负债", balance_direction="贷",
                        level=3, parent_code="221001"
                    ))
                    db.commit()
                    print(f"  [OK] 为 {comp.name} 添加科目 221001003 待认证进项税额")
                except Exception as e:
                    db.rollback()
                    print(f"  [X] 221001003 待认证进项税额 迁移失败: {e}")


    # ── 12.7. 为档案表补充 updated_at 列 ──
    for tbl in ("departments", "employees", "customers", "suppliers", "bank_transactions"):
        if tbl in inspector.get_table_names():
            existing_cols = {c["name"] for c in inspector.get_columns(tbl)}
            if "updated_at" not in existing_cols:
                try:
                    db.execute(TextClause(f"ALTER TABLE {tbl} ADD COLUMN updated_at TIMESTAMP"))
                    db.commit()
                    print(f"  [OK] {tbl} 添加 updated_at 列")
                except Exception as e:
                    db.rollback()
                    print(f"  [X] {tbl} updated_at 迁移失败: {e}")



    # ── 15. 社保申报表──
    if "social_security_declarations" not in inspector.get_table_names():
        SocialSecurityDeclaration.__table__.create(bind=db.get_bind())
        db.commit()
        print("  [OK] 已创建 social_security_declarations 表")
    if "social_security_details" not in inspector.get_table_names():
        SocialSecurityDetail.__table__.create(bind=db.get_bind())
        db.commit()
        print("  [OK] 已创建 social_security_details 表")

    # ── 16. 公积金缴存表──
    if "housing_fund_declarations" not in inspector.get_table_names():
        HousingFundDeclaration.__table__.create(bind=db.get_bind())
        db.commit()
        print("  [OK] 已创建 housing_fund_declarations 表")

    # ── 18. 文化事业建设费申报表 ──
    if "cultural_construction_fee_declarations" not in inspector.get_table_names():
        CulturalConstructionFeeDeclaration.__table__.create(bind=db.get_bind())
        db.commit()
        print("  [OK] 已创建 cultural_construction_fee_declarations 表")

    # ── 18.1 CCF 新增 50% 减征字段（财税〔2025〕7号） ──
    if "cultural_construction_fee_declarations" in inspector.get_table_names():
        ccf_cols = [c["name"] for c in inspector.get_columns("cultural_construction_fee_declarations")]
        if "row10a_fee_reduction_current" not in ccf_cols:
            db.execute(TextClause(
                "ALTER TABLE cultural_construction_fee_declarations ADD COLUMN row10a_fee_reduction_current NUMERIC(18,2) DEFAULT 0.0"
            ))
            db.commit()
            print("  [OK] CCF 新增 row10a_fee_reduction_current 列")
        if "row10a_fee_reduction_ytd" not in ccf_cols:
            db.execute(TextClause(
                "ALTER TABLE cultural_construction_fee_declarations ADD COLUMN row10a_fee_reduction_ytd NUMERIC(18,2) DEFAULT 0.0"
            ))
            db.commit()
            print("  [OK] CCF 新增 row10a_fee_reduction_ytd 列")
        if "fee_reduction_rate" not in ccf_cols:
            db.execute(TextClause(
                "ALTER TABLE cultural_construction_fee_declarations ADD COLUMN fee_reduction_rate NUMERIC(18,4) DEFAULT 0.5"
            ))
            db.commit()
            print("  [OK] CCF 新增 fee_reduction_rate 列")

    # ── 19. 补充索引与唯一约束 ──
    idx_defs = [
        ("idx_accounts_company", "accounts", "company_id"),
        ("idx_customers_company", "customers", "company_id"),
        ("idx_suppliers_company", "suppliers", "company_id"),
        ("idx_employees_company", "employees", "company_id"),
        ("idx_departments_company", "departments", "company_id"),
        ("idx_ss_details_company", "social_security_details", "company_id"),
        ("idx_hf_details_company", "housing_fund_details", "company_id"),
        ("idx_salary_company", "salary_records", "company_id"),
        ("idx_je_source", "journal_entries", "source"),
        ("idx_je_ref_id", "journal_entries", "ref_id"),
        ("idx_ivd_period", "input_vat_deductions", "period"),
    ]
    for idx_name, tbl, col in idx_defs:
        try:
            if tbl in inspector.get_table_names():
                db.execute(TextClause(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl}({col})"))
                db.commit()
        except Exception:
            db.rollback()

    # Account(company_id, code) 唯一约束
    if "accounts" in inspector.get_table_names():
        try:
            db.execute(TextClause("CREATE UNIQUE INDEX IF NOT EXISTS uq_account_company_code ON accounts(company_id, code)"))
            db.commit()
        except Exception:
            db.rollback()

    # JournalEntry(source, ref_id) 索引（加速查询，非唯一约束：同一发票生成多行分录共享ref_id）
    if "journal_entries" in inspector.get_table_names():
        try:
            db.execute(TextClause(
                "CREATE INDEX IF NOT EXISTS idx_je_source_ref ON journal_entries(source, ref_id)"
            ))
            db.commit()
        except Exception:
            db.rollback()


    # ── 20. 发票表关键字段 NOT NULL 约束迁移 ──
    # SQLite 不支持 ALTER COLUMN，需要重建表
    _not_null_migrations = [
        ("sales_invoices", "invoice_date", "DATE", "2000-01-01"),
        ("sales_invoices", "seller_name", "VARCHAR(100)", "未知销方"),
        ("sales_invoices", "buyer_name", "VARCHAR(100)", "未知购方"),
        ("purchase_invoices", "invoice_date", "DATE", "2000-01-01"),
        ("purchase_invoices", "seller_name", "VARCHAR(100)", "未知销方"),
        ("purchase_invoices", "buyer_name", "VARCHAR(100)", "未知购方"),
        ("bookkeeping_invoices", "invoice_date", "DATE", "2000-01-01"),
        ("bookkeeping_invoices", "seller_name", "VARCHAR(100)", "未知销方"),
        ("bookkeeping_invoices", "buyer_name", "VARCHAR(100)", "未知购方"),
    ]
    for tbl, col, col_type, default_val in _not_null_migrations:
        if tbl not in inspector.get_table_names():
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(tbl)}
        if col not in existing_cols:
            continue
        col_info = {c["name"]: c for c in inspector.get_columns(tbl)}[col]
        if not col_info.get("nullable", True):
            continue  # 已经 NOT NULL
        # Step1: 将 NULL 值更新为默认值
        try:
            db.execute(TextClause(f"UPDATE {tbl} SET {col} = :v WHERE {col} IS NULL"), {"v": default_val})
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"  [X] {tbl}.{col} NULL值更新失败: {e}")
            continue
        # Step2: 重建表以添加 NOT NULL 约束（SQLite 必须）
        try:
            db.execute(TextClause(f"ALTER TABLE {tbl} RENAME TO _bk_{tbl}"))
            db.commit()
            if tbl == "sales_invoices":
                SalesInvoice.__table__.create(bind=engine, checkfirst=True)
            elif tbl == "purchase_invoices":
                PurchaseInvoice.__table__.create(bind=engine, checkfirst=True)
            elif tbl == "bookkeeping_invoices":
                BookkeepingInvoice.__table__.create(bind=engine, checkfirst=True)
            db.execute(TextClause(f"INSERT INTO {tbl} SELECT * FROM _bk_{tbl}"))
            db.commit()
            db.execute(TextClause(f"DROP TABLE _bk_{tbl}"))
            db.commit()
            print(f"  [OK] {tbl}.{col} NOT NULL 约束已添加")
        except Exception as e:
            db.rollback()
            try:
                db.execute(TextClause(f"DROP TABLE IF EXISTS {tbl}"))
                db.execute(TextClause(f"ALTER TABLE _bk_{tbl} RENAME TO {tbl}"))
                db.commit()
            except Exception:
                pass
            print(f"  [X] {tbl}.{col} NOT NULL 迁移失败（已回滚）: {e}")


def _normalize_customer_name(name: str) -> str:
    """标准化客户名称：去空格、全角括号转半角，提高匹配率"""
    if not name:
        return ""
    name = name.strip()
    name = name.replace("\uff08", "(").replace("\uff09", ")")
    name = name.replace("\u3000", " ").replace("\xa0", " ")
    name = " ".join(name.split())
    return name


class VATDeclaration(Base):
    """增值税及附加税费申报表头"""
    __tablename__ = "vat_declarations"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    period = Column(String(7), nullable=False)  # YYYY-MM 税款所属期
    # 纳税人信息
    taxpayer_name = Column(String(100))
    taxpayer_id = Column(String(50))
    industry = Column(String(50))
    register_type = Column(String(50))
    legal_representative = Column(String(50))
    address = Column(String(200))
    bank_account = Column(String(100))
    phone = Column(String(30))
    # 填表信息
    fill_date = Column(Date)
    # 小微企业"六税两费"减免
    micro_enterprise = Column(Boolean, default=False)
    six_tax_reduction = Column(Boolean, default=False)
    reduction_start = Column(String(10))
    reduction_end = Column(String(10))
    # 附加税费
    city_maintenance_tax = Column(Numeric(18, 2), default=0.0)
    education_surcharge = Column(Numeric(18, 2), default=0.0)
    local_education_surcharge = Column(Numeric(18, 2), default=0.0)
    # 状态
    status = Column(String(20), default="草稿")
    submitted_at = Column(DateTime)
    # 7张表的填报数据（JSON格式）
    form_main = Column(Text)
    form_sales = Column(Text)
    form_input = Column(Text)
    form_deduction = Column(Text)
    form_credit = Column(Text)
    form_surcharge = Column(Text)
    form_reduction = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    company = relationship("Company", back_populates="vat_declarations")


# ========== 社保申报模型 ==========

class SocialSecurityDeclaration(Base):
    """社保申报主表"""
    __tablename__ = "social_security_declarations"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    period = Column(String(7), nullable=False, index=True)  # YYYY-MM 费款所属期
    status = Column(String(20), default="草稿")  # 草稿/已确认
    note = Column(String(500))  # 备注
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    company = relationship("Company", back_populates="social_security_declarations")
    details = relationship("SocialSecurityDetail", back_populates="declaration", cascade="all, delete-orphan")


class SocialSecurityDetail(Base):
    """社保申报明细表"""
    __tablename__ = "social_security_details"

    id = Column(Integer, primary_key=True, index=True)
    declaration_id = Column(Integer, ForeignKey("social_security_declarations.id"), nullable=False, index=True)
    seq = Column(Integer, comment="序号")
    employee_name = Column(String(50), comment="姓名")
    id_number = Column(String(30), comment="证件号码")
    period_start = Column(String(7), comment="费款所属期起")
    period_end = Column(String(7), comment="费款所属期止")
    total_amount = Column(Numeric(18, 2), default=0.0, comment="应收金额")
    personal_amount = Column(Numeric(18, 2), default=0.0, comment="个人社保合计")
    company_amount = Column(Numeric(18, 2), default=0.0, comment="单位社保合计")
    salary_base = Column(Numeric(18, 2), default=0.0, comment="缴费工资")
    category = Column(String(20), default="在职人员", comment="人员类别：在职人员/退休人员/家属统筹人员")
    insurance_items = Column(Text, comment="JSON: 各项保险明细 [{name,rate,amount},...]")
    created_at = Column(DateTime, default=datetime.now)

    declaration = relationship("SocialSecurityDeclaration", back_populates="details")


# ========== 公积金缴存模型 ==========

class HousingFundDetail(Base):
    """公积金缴存明细（一人一行）"""
    __tablename__ = "housing_fund_details"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    period = Column(String(7), nullable=False, index=True)  # YYYY-MM
    employee_id = Column(String(20), comment="工号")
    employee_name = Column(String(50), nullable=False, comment="姓名")
    id_number = Column(String(18), comment="身份证号")
    deposit_base = Column(Numeric(18, 2), default=0.0, comment="缴存基数")
    company_ratio = Column(Numeric(18, 2), default=0.0, comment="单位缴存比例(%)")
    personal_ratio = Column(Numeric(18, 2), default=0.0, comment="个人缴存比例(%)")
    total_amount = Column(Numeric(18, 2), default=0.0, comment="缴存额（月缴存额合计）")
    company_amount = Column(Numeric(18, 2), default=0.0, comment="单位缴存额")
    personal_amount = Column(Numeric(18, 2), default=0.0, comment="个人缴存额")
    status = Column(String(20), default="正常", comment="正常/封存")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    company = relationship("Company", back_populates="housing_fund_details")


class HousingFundDeclaration(Base):
    """公积金申报主表"""
    __tablename__ = "housing_fund_declarations"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    period = Column(String(7), nullable=False, index=True)  # YYYY-MM
    status = Column(String(20), default="草稿")  # 草稿/已确认
    note = Column(String(500))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    company = relationship("Company", back_populates="housing_fund_declarations")


# 基础科目数据模板（中小制造业标准科目表）
ACCOUNTS_TEMPLATE = [
    ("1001", "库存现金", "资产", "借", 1),
    ("1002", "银行存款", "资产", "借", 1),
    ("1122", "应收账款", "资产", "借", 1),
    ("1123", "预付账款", "资产", "借", 1),
    ("1221", "其他应收款", "资产", "借", 1),
    ("1401", "原材料", "资产", "借", 1),
    ("1402", "在途物资", "资产", "借", 1),
    ("1403", "库存商品", "资产", "借", 1),
    ("1405", "委托加工物资", "资产", "借", 1),
    ("1411", "周转材料", "资产", "借", 1),
    ("1601", "固定资产", "资产", "借", 1),
    ("1602", "累计折旧", "资产", "贷", 1),
    ("1701", "无形资产", "资产", "借", 1),
    ("1801", "长期待摊费用", "资产", "借", 1),
    ("2001", "短期借款", "负债", "贷", 1),
    ("2202", "应付账款", "负债", "贷", 1),
    ("2203", "预收账款", "负债", "贷", 1),
    ("2221", "其他应付款", "负债", "贷", 1),
    ("2241", "其他应付款", "负债", "贷", 1),
    ("2501", "长期借款", "负债", "贷", 1),
    ("2210", "应交税费", "负债", "贷", 1),
    ("221001", "应交增值税", "负债", "贷", 2, "2210"),
    ("221001001", "销项税额", "负债", "贷", 3, "221001"),
    ("221001002", "进项税额", "负债", "借", 3, "221001"),
    ("221001003", "待认证进项税额", "负债", "贷", 3, "221001"),
    ("221001004", "已交税金", "负债", "借", 3, "221001"),
    ("221001005", "转出未交增值税", "负债", "借", 3, "221001"),
    ("221001006", "转出多交增值税", "负债", "贷", 3, "221001"),
    ("221001007", "减免税款", "负债", "借", 3, "221001"),
    ("221001008", "出口抵减内销产品应纳税额", "负债", "借", 3, "221001"),
    ("221001009", "出口退税", "负债", "贷", 3, "221001"),
    ("221001010", "进项税额转出", "负债", "贷", 3, "221001"),
    ("221001011", "销项税额抵减", "负债", "借", 3, "221001"),
    ("221009", "预交增值税", "负债", "借", 2, "2210"),
    ("221010", "待抵扣进项税额", "负债", "借", 2, "2210"),
    ("221011", "待转销项税额", "负债", "贷", 2, "2210"),
    ("221012", "增值税留抵税额", "负债", "借", 2, "2210"),
    ("221013", "简易计税", "负债", "贷", 2, "2210"),
    ("221014", "转让金融商品应交增值税", "负债", "贷", 2, "2210"),
    ("221015", "代扣代交增值税", "负债", "贷", 2, "2210"),
    ("221002", "应交企业所得税", "负债", "贷", 2, "2210"),
    ("221003", "应交个人所得税", "负债", "贷", 2, "2210"),
    ("221004", "未交增值税", "负债", "贷", 2, "2210"),
    ("221005", "应交城市维护建设税", "负债", "贷", 2, "2210"),
    ("221006", "应交教育费附加", "负债", "贷", 2, "2210"),
    ("221007", "应交地方教育附加", "负债", "贷", 2, "2210"),
    ("221008", "应交印花税", "负债", "贷", 2, "2210"),
    ("2211", "应付职工薪酬", "负债", "贷", 1),
    ("221101", "工资", "负债", "贷", 2, "2211"),
    ("221102", "社会保险费", "负债", "贷", 2, "2211"),
    ("221103", "住房公积金", "负债", "贷", 2, "2211"),
    ("222101", "代扣社会保险费", "负债", "贷", 2, "2221"),
    ("4001", "实收资本", "权益", "贷", 1),
    ("4002", "资本公积", "权益", "贷", 1),
    ("4101", "盈余公积", "权益", "贷", 1),
    ("4103", "本年利润", "权益", "贷", 1),
    ("4104", "利润分配", "权益", "贷", 1),
    ("5001", "生产成本", "成本", "借", 1),
    ("500101", "直接材料", "成本", "借", 2, "5001"),
    ("500102", "直接人工", "成本", "借", 2, "5001"),
    ("500103", "制造费用", "成本", "借", 2, "5001"),
    ("5101", "制造费用", "成本", "借", 1),
    ("6001", "主营业务收入", "收入", "贷", 1),
    ("6051", "其他业务收入", "收入", "贷", 1),
    ("6111", "投资收益", "收入", "贷", 1),
    ("6301", "营业外收入", "收入", "贷", 1),
    ("6401", "主营业务成本", "损益", "借", 1),
    ("6402", "其他业务成本", "损益", "借", 1),
    ("6403", "税金及附加", "损益", "借", 1),
    ("6601", "销售费用", "损益", "借", 1),
    ("6602", "管理费用", "损益", "借", 1),
    ("660201", "办公费", "损益", "借", 2, "6602"),
    ("660202", "差旅费", "损益", "借", 2, "6602"),
    ("660203", "折旧费", "损益", "借", 2, "6602"),
    ("660204", "工资", "损益", "借", 2, "6602"),
    # 660205已语义合并到660212(社会保险费)
    ("660212", "社会保险费", "损益", "借", 2, "6602"),
    ("660206", "交通费", "损益", "借", 2, "6602"),
    ("660207", "通讯费", "损益", "借", 2, "6602"),
    ("660208", "摊销费", "损益", "借", 2, "6602"),
    ("660209", "咨询费", "损益", "借", 2, "6602"),
    ("660210", "培训费", "损益", "借", 2, "6602"),
    ("660211", "维修费", "损益", "借", 2, "6602"),
    ("660213", "租赁费", "损益", "借", 2, "6602"),
    ("660214", "水电费", "损益", "借", 2, "6602"),
    ("660215", "业务招待费", "损益", "借", 2, "6602"),
    ("660216", "住房公积金", "损益", "借", 2, "6602"),
    ("6603", "财务费用", "损益", "借", 1),
    ("660301", "手续费", "损益", "借", 2, "6603"),
    ("6711", "营业外支出", "损益", "借", 1),
    ("6801", "所得税费用", "损益", "借", 1),
]

DEPARTMENTS_TEMPLATE = [
    ("BM001", "总经办"),
    ("BM002", "生产部"),
    ("BM003", "技术部"),
    ("BM004", "质检部"),
    ("BM005", "采购部"),
    ("BM006", "销售部"),
    ("BM007", "仓储部"),
    ("BM008", "财务部"),
    ("BM009", "行政部"),
    ("BM010", "人事部"),
]


class SalaryRecord(Base):
    """工资薪金所得预扣预缴明细 - 按税务模板"""
    __tablename__ = "salary_records"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    period = Column(String(20), nullable=False, index=True)  # 期间，如 2025-10

    # 人员信息
    employee_code = Column(String(50), index=True)          # 工号（关联人员档案 code）
    employee_name = Column(String(100), nullable=False)       # 姓名
    id_type = Column(String(50), default="居民身份证")       # 证件类型
    id_number = Column(String(50), index=True)                # 证件号码

    # 税款所属期
    tax_period_start = Column(String(20))  # 税款所属期起，如 2025-10-01
    tax_period_end = Column(String(20))    # 税款所属期止，如 2025-10-31
    income_type = Column(String(50), default="正常工资薪金")  # 所得项目

    # 本期扣除
    current_income = Column(Numeric(18, 2), default=0.0)       # 本期收入
    tax_free_income = Column(Numeric(18, 2), default=0.0)       # 免税收入
    basic_deduction = Column(Numeric(18, 2), default=5000.0)    # 基本减除费用

    # 专项扣除（本月）
    pension_insurance = Column(Numeric(18, 2), default=0.0)      # 基本养老保险
    medical_insurance = Column(Numeric(18, 2), default=0.0)     # 基本医疗保险
    unemployment_insurance = Column(Numeric(18, 2), default=0.0) # 失业保险
    housing_fund = Column(Numeric(18, 2), default=0.0)           # 住房公积金
    enterprise_annuity = Column(Numeric(18, 2), default=0.0)    # 企业年金
    commercial_health = Column(Numeric(18, 2), default=0.0)     # 商业健康保险
    tax_deferred_pension = Column(Numeric(18, 2), default=0.0)  # 税延养老保险
    other_special_deduction = Column(Numeric(18, 2), default=0.0) # 其他专项扣除

    # 专项附加扣除（本月）
    child_education = Column(Numeric(18, 2), default=0.0)        # 子女教育
    continuing_education = Column(Numeric(18, 2), default=0.0)   # 继续教育
    housing_loan_interest = Column(Numeric(18, 2), default=0.0)  # 住房贷款利息
    housing_rent = Column(Numeric(18, 2), default=0.0)            # 住房租金
    elderly_support = Column(Numeric(18, 2), default=0.0)        # 赡养老人
    infant_care = Column(Numeric(18, 2), default=0.0)            # 3岁以下婴幼儿照护
    major_medical = Column(Numeric(18, 2), default=0.0)           # 大病医疗
    other_additional_deduction = Column(Numeric(18, 2), default=0.0) # 其他附加扣除

    # 累计数据
    cumulative_income = Column(Numeric(18, 2), default=0.0)           # 累计收入额
    cumulative_tax_free = Column(Numeric(18, 2), default=0.0)         # 累计免税收入
    cumulative_deduction = Column(Numeric(18, 2), default=0.0)        # 累计减除费用
    cumulative_special = Column(Numeric(18, 2), default=0.0)          # 累计专项扣除
    cumulative_additional = Column(Numeric(18, 2), default=0.0)       # 累计专项附加扣除
    cumulative_other = Column(Numeric(18, 2), default=0.0)            # 累计其他扣除
    cumulative_tax_withheld = Column(Numeric(18, 2), default=0.0)    # 累计已预扣预缴税额

    # 本期其他扣除
    other_deduction = Column(Numeric(18, 2), default=0.0)             # 本期其他扣除

    # 税额计算
    taxable_income = Column(Numeric(18, 2), default=0.0)      # 应纳税所得额
    tax_rate = Column(Numeric(18, 2), default=0.0)            # 税率
    quick_deduction = Column(Numeric(18, 2), default=0.0)     # 速算扣除数
    tax_payable = Column(Numeric(18, 2), default=0.0)         # 累计应预扣预缴税额
    tax_already_withheld = Column(Numeric(18, 2), default=0.0) # 本期已预扣预缴税额
    tax_to_pay = Column(Numeric(18, 2), default=0.0)          # 本期应预扣预缴税额（实际应缴）
    tax_refund = Column(Numeric(18, 2), default=0.0)          # 应补(退)税额

    # 实发工资
    net_salary = Column(Numeric(18, 2), default=0.0)           # 实发工资

    # 原始行数据（JSON，保留导入时的完整列）
    raw_data = Column(Text)  # JSON string，存储Excel原始行

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('idx_salary_company_period', 'company_id', 'period'),
    )
    company = relationship("Company", back_populates="salary_records")


# ==================== 文化事业建设费申报 ====================

class CulturalConstructionFeeDeclaration(Base):
    """文化事业建设费申报表（主表）"""
    __tablename__ = "cultural_construction_fee_declarations"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, comment="所属公司")
    period = Column(String(7), nullable=False, comment="申报期间 YYYY-MM")
    status = Column(String(20), default="草稿", comment="状态：草稿/已确认/已申报")
    note = Column(Text, comment="备注")
    taxpayer_name = Column(String(200), comment="纳税人名称")
    taxpayer_id = Column(String(50), comment="纳税人识别号")
    fill_date = Column(Date, comment="填表日期")

    # 主表栏次（本月数 / 本年累计）—— 命名以 rowN_ 前缀对应 Pydantic 模型
    row1_taxable_income_current = Column(Numeric(18, 2), default=0.0, comment="栏次1 应征收入 本月数")
    row1_taxable_income_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次1 应征收入 本年累计")
    row2_tax_exempt_income_current = Column(Numeric(18, 2), default=0.0, comment="栏次2 免征收入 本月数")
    row2_tax_exempt_income_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次2 免征收入 本年累计")
    row3_deduction_beginning_current = Column(Numeric(18, 2), default=0.0, comment="栏次3 减除项目期初金额 本月数")
    row3_deduction_beginning_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次3 减除项目期初金额 本年累计")
    row4_deduction_current_period_current = Column(Numeric(18, 2), default=0.0, comment="栏次4 减除项目本期发生额 本月数")
    row4_deduction_current_period_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次4 减除项目本期发生额 本年累计")
    row5_taxable_income_deduction_current = Column(Numeric(18, 2), default=0.0, comment="栏次5 应征收入减除额 本月数")
    row5_taxable_income_deduction_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次5 应征收入减除额 本年累计")
    row6_tax_exempt_deduction_current = Column(Numeric(18, 2), default=0.0, comment="栏次6 免征收入减除额 本月数")
    row6_tax_exempt_deduction_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次6 免征收入减除额 本年累计")
    row7_deduction_ending_balance_current = Column(Numeric(18, 2), default=0.0, comment="栏次7 减除项目期末余额 本月数")
    row7_deduction_ending_balance_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次7 减除项目期末余额 本年累计")
    row8_taxable_sales_current = Column(Numeric(18, 2), default=0.0, comment="栏次8 计费销售额 本月数")
    row8_taxable_sales_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次8 计费销售额 本年累计")
    row9_fee_rate = Column(Numeric(18, 4), default=0.03, comment="栏次9 费率")
    row10_payable_fee_current = Column(Numeric(18, 2), default=0.0, comment="栏次10 应缴费额 本月数")
    row10_payable_fee_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次10 应缴费额 本年累计")
    row10a_fee_reduction_current = Column(Numeric(18, 2), default=0.0, comment="栏次10a 本期减免额（财税〔2025〕7号 50%减征）本月数")
    row10a_fee_reduction_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次10a 本期减免额 本年累计")
    fee_reduction_rate = Column(Numeric(18, 4), default=0.5, comment="减免比例（财税〔2025〕7号：归属中央收入50%减征）")
    row11_unpaid_beginning_current = Column(Numeric(18, 2), default=0.0, comment="栏次11 期初未缴费额 本月数")
    row11_unpaid_beginning_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次11 期初未缴费额 本年累计")
    row12_paid_current_period_current = Column(Numeric(18, 2), default=0.0, comment="栏次12 本期已缴费额 本月数")
    row12_paid_current_period_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次12 本期已缴费额 本年累计")
    row13_prepaid_current = Column(Numeric(18, 2), default=0.0, comment="栏次13 本期预缴费额 本月数")
    row13_prepaid_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次13 本期预缴费额 本年累计")
    row14_paid_last_period_current = Column(Numeric(18, 2), default=0.0, comment="栏次14 本期缴纳上期费额 本月数")
    row14_paid_last_period_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次14 本期缴纳上期费额 本年累计")
    row15_paid_arrears_current = Column(Numeric(18, 2), default=0.0, comment="栏次15 本期缴纳欠费额 本月数")
    row15_paid_arrears_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次15 本期缴纳欠费额 本年累计")
    row16_unpaid_ending_current = Column(Numeric(18, 2), default=0.0, comment="栏次16 期末未缴费额 本月数")
    row16_unpaid_ending_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次16 期末未缴费额 本年累计")
    row17_arrears_current = Column(Numeric(18, 2), default=0.0, comment="栏次17 欠缴费额 本月数")
    row17_arrears_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次17 欠缴费额 本年累计")
    row18_fill_refund_current = Column(Numeric(18, 2), default=0.0, comment="栏次18 本期应补(退)费额 本月数")
    row18_fill_refund_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次18 本期应补(退)费额 本年累计")
    row19_inspected_supplement_current = Column(Numeric(18, 2), default=0.0, comment="栏次19 本期检查已补缴费额 本月数")
    row19_inspected_supplement_ytd = Column(Numeric(18, 2), default=0.0, comment="栏次19 本期检查已补缴费额 本年累计")

    # JSON 表单数据（与 VAT 模块一致）
    form_main = Column(Text, comment="主表 JSON")
    form_deduction = Column(Text, comment="扣除项目表 JSON")

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('idx_ccf_company_period', 'company_id', 'period'),
    )
    company = relationship("Company", back_populates="cultural_construction_fee_declarations")


class ErrorFeedback(Base):
    """用户错误反馈记录——系统自学习的燃料"""
    __tablename__ = "error_feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(String(20), comment="反馈追踪ID")
    domain = Column(String(200), comment="所属分析域")
    conclusion_type = Column(String(200), comment="结论类型")
    error_description = Column(Text, comment="用户描述：哪里错了")
    correct_answer = Column(Text, comment="正确答案/修正方向")
    data_context = Column(Text, comment="JSON: 错误发生时的数据上下文")
    severity = Column(String(20), default="中", comment="严重程度: 高/中/低")
    error_type = Column(String(50), comment="自动分类: policy_expired/false_positive/...")
    status = Column(String(20), default="new", comment="new/triaged/resolved/archived")
    company_id = Column(Integer, comment="公司ID")
    report_trace_id = Column(String(50), comment="关联的报告追踪ID")
    matched_rule_id = Column(Integer, comment="匹配的自愈规则ID")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_ef_domain', 'domain'),
        Index('idx_ef_status', 'status'),
    )


class SelfHealingRule(Base):
    """自愈规则——从错误中自动生成的修正规则"""
    __tablename__ = "self_healing_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_name = Column(String(200), comment="规则名称")
    rule_type = Column(String(50), comment="规则类型: policy_expired/false_positive/false_negative/rate_wrong/condition_missing")
    domain = Column(String(200), comment="适用域")
    trigger_pattern = Column(Text, comment="JSON: 触发条件模式")
    correction_action = Column(String(50), comment="修正动作: update_law_ref/add_exemption_condition/lower_threshold/update_value/add_condition")
    correction_detail = Column(Text, comment="JSON: 修正详情")
    source_error_count = Column(Integer, default=1, comment="来源错误数量(≥3自动生成)")
    confidence = Column(Float, default=0.5, comment="置信度 0-1")
    status = Column(String(20), default="draft", comment="draft/active/disabled")
    auto_apply = Column(Boolean, default=False, comment="是否自动应用到分析")
    applied_count = Column(Integer, default=0, comment="已应用次数")
    last_applied_at = Column(DateTime, comment="上次应用时间")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_shr_type', 'rule_type'),
        Index('idx_shr_status', 'status'),
    )


# ═══════════════════════════════════════════════════════════
# 整改跟踪 —— 风险发现→整改完成全流程
# ═══════════════════════════════════════════════════════════

class RemediationRecord(Base):
    """整改跟踪记录——每条风险发现的整改进度"""
    __tablename__ = "remediation_records"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, nullable=False, comment="公司ID")
    finding_type = Column(String(200), comment="风险发现类型")
    finding_detail = Column(Text, comment="风险发现明细")
    risk_level = Column(String(10), comment="风险等级：高/中/低")
    status = Column(String(20), default="pending", comment="整改状态: pending/in_progress/completed/verified/closed")
    responsible_person = Column(String(50), comment="整改责任人")
    action_plan = Column(Text, comment="整改方案/措施")
    deadline = Column(Date, comment="整改截止日期")
    completed_at = Column(DateTime, comment="完成时间")
    verified_by = Column(String(50), comment="核验人")
    verification_note = Column(Text, comment="核验意见")
    evidence_files = Column(Text, comment="JSON: 整改证据文件列表")
    notes = Column(Text, comment="备注")
    trace_id = Column(String(50), comment="关联分析追踪ID")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_rr_company_status', 'company_id', 'status'),
        Index('idx_rr_trace', 'trace_id'),
    )


# ═══════════════════════════════════════════════════════════
# 行业对标统计池 —— 基准值从数据中自学习
# ═══════════════════════════════════════════════════════════

class IndustryBenchmark(Base):
    """行业基准值统计——每次分析完成后自动更新"""
    __tablename__ = "industry_benchmarks"

    id = Column(Integer, primary_key=True, index=True)
    industry = Column(String(50), nullable=False, comment="行业代码")
    metric_name = Column(String(50), nullable=False, comment="指标名称：invoice_match_ratio/tax_burden/gross_margin/in_out_ratio等")
    metric_value = Column(Numeric(18, 4), comment="本次分析值")
    company_id = Column(Integer, comment="公司ID")
    trace_id = Column(String(50), comment="分析追踪ID")
    sample_count = Column(Integer, default=1, comment="累计样本数")
    running_mean = Column(Numeric(18, 4), comment="累计均值")
    running_std = Column(Numeric(18, 4), comment="累计标准差")
    p25 = Column(Numeric(18, 4), comment="25分位数")
    p50 = Column(Numeric(18, 4), comment="中位数（benchmark）")
    p75 = Column(Numeric(18, 4), comment="75分位数")
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_ib_industry_metric', 'industry', 'metric_name'),
    )


def init_db():
    """初始化数据库：建表 → 迁移 → 初始化已有公司的种子数据

    新环境首次运行时，如果 companys 表为空，自动创建一家演示公司，
    并初始化其科目/部门/期间，保证系统可直接使用。
    """
    from datetime import date
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if "company_id" in table.c:
                index_name = f"ix_{table.name}_company_id"
                connection.execute(TextClause(
                    f'CREATE INDEX IF NOT EXISTS "{index_name}" '
                    f'ON "{table.name}" ("company_id")'
                ))
    db = SessionLocal()

    try:
        migrate_schema(db)

        # 新环境无公司时，不再自动创建演示公司
        # 用户可通过页面"创建新公司"自行创建
        companies = db.query(Company).order_by(Company.id).all()
        for company in companies:
            try:
                init_company_data(db, company.id)
            except Exception as e:
                print(f"[init_db] 警告：公司{company.id} 数据初始化失败: {e}")


        db.commit()
        print(f"数据库初始化完成（{len(companies)} 家公司）")

        # 初始化审计日志表
        try:
            db.execute(TextClause("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER,
                    user_name TEXT,
                    action TEXT NOT NULL,
                    target TEXT,
                    detail TEXT,
                    created_at TEXT
                )
            """))
            db.commit()
        except Exception:
            db.rollback()

        # 为已有公司自动识别行业
        for company in companies:
            if not company.industry_code and company.business_scope:
                try:
                    from audit_enhancements import detect_industry
                    company.industry_code = detect_industry(company.business_scope)
                    db.commit()
                except Exception:
                    pass

    except Exception as e:
        db.rollback()
        print(f"初始化错误: {e}")
        raise  # 重新抛出，让调用方知道初始化失败
    finally:
        db.close()

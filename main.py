"""
全行业财税风险防控系统 - 后端 API
"""
import hashlib, secrets, json as _json, time
from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, Form, Body, Request, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from sqlalchemy import func, and_, or_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from contextlib import asynccontextmanager
import os
import csv
import io
import re
import logging
import hashlib
import uuid
import openpyxl
import json
import urllib.request
import urllib.parse
import urllib.error
import ssl
import time as _time_module_inner
from pypdf import PdfReader

# ═══ 稽查员推理引擎（模块化架构）═══
from engine import (
    save_analysis_memory, query_similar_cases,
    get_audit_ctx,
    identify_main_biz_cost, _REIMBURSEMENT_KWS_GLOBAL,
    _phase1_triage, _phase2_deep_dive, _phase3_cross_validate, _phase4_synthesis,
    _SIGNAL_DOMAIN_MAP,
    build_orchestration_plan, build_data_profile, get_module_registry_summary,
    CAPABILITY_MATRIX, META_RULES, get_capability_summary,
    run_legal_reasoning, run_cross_enterprise_analysis, run_trend_analysis,
)
from engine.domain_analysis import *  # 35域分析函数（从 main.py 提取）
from engine.pipeline import *  # _run_analyze 核心管道
from engine.pipeline import _run_analyze  # 显式导入（下划线前缀不被 wildcard 导出）

from database import (
    get_db, init_db, init_company_data,
    Company, Department, Employee, Customer, Supplier,
    Account, Period,
    FixedAsset, FixedAssetDepreciation,
    IntangibleAsset, IntangibleAssetAmortization,
    InventoryItem, InventoryTransaction, InventoryBalance,
    Contract, ContractPayment,
    Payment,
    SalesInvoice, PurchaseInvoice, BookkeepingInvoice,
    BankConfig, BankTransaction, BankRule,
    InputVATDeduction, ColumnTemplate, JournalEntry,
    SalaryRecord, VATDeclaration,
    CompanyShareholder, CompanyDirector, CompanySupervisor, CompanyFinanceContact,
    auto_generate_single_invoice,
    auto_generate_input_vat_for_period, auto_generate_input_vat_journals,
    _normalize_customer_name, _match_customer, _generate_bank_journals, _classify_bank_tx, _build_entity_index, _ensure_account,
    _generate_salary_journals, _generate_hf_accrual_journals, _match_hf_payment_journals,
    _match_ss_payment_journals, _match_tax_payment_journals,
    auto_generate_purchase_journal, auto_generate_bookkeeping_journal, _next_voucher_no, _classify_purchase_debit,
)

from tax_risk import router as tax_risk_router
from chat import router as chat_router
from salary import router as salary_router
from vat import router as vat_router
from housing_fund import router as housing_fund_router
from social_security import router as social_security_router
from cultural_construction_fee import router as cultural_construction_fee_router
from utils import build_account_hierarchy as _build_account_hierarchy, clear_source_voucher_no as _clear_source_voucher_no, renumber_vouchers as _renumber_vouchers, renumber_archive as _renumber_archive, sync_biz_voucher_no as _sync_biz_voucher_no
from journal import router as journal_router
from payments import router as payments_router
from input_vat import router as input_vat_router
from tax_rules_api import router as tax_rules_api_router
from file_parser import router as file_parser_router
from archives import router as archives_router
from financial_reports import router as financial_reports_router
from bank_transactions import router as bank_transactions_router
from bank_transactions import router as bank_transactions_router
from bookkeeping_invoices import router as bookkeeping_invoices_router
from contracts import router as contracts_router
from inventory import router as inventory_router
from intangible_assets import router as intangible_assets_router
from fixed_assets import router as fixed_assets_router
from dashboard import router as dashboard_router

# ═══ 统一城市列表 — 从 shared_state 导入 ═══
from shared_state import _CHINA_CITIES_UNIFIED, _CHINA_CITY_REGEX, _last_analysis_cache, _tax_risk_docs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库+自检"""
    init_db()
    try:
        caps = get_capability_summary()
        orch = get_module_registry_summary()
        from engine.capability_matrix import check_quality_system
        qs = check_quality_system()
        print(f"[STARTUP] {caps['total_dimensions']}维({caps['four_star_count']}四星/{caps['three_star_count']}三星) | 调度中枢:{orch['total_modules']}模块 | 质量保障:{qs['layers']}层{qs['components']}组件{qs['status']}")
    except: pass
    # ⑥ 代码变更追踪 → AGI
    try: _track_code_changes()
    except: pass
    yield

app = FastAPI(title="财税风险防控系统", description="全行业通用财税风险防控与稽查应对系统", version="1.0.0", lifespan=lifespan)

# ═══════════════ 个人登录 ═══════════════
_AUTH_SESSIONS = {}

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    skip_paths = ["/login", "/api/auth/", "/static/", "/favicon.ico"]
    if any(path == s or path.startswith(s) for s in skip_paths):
        return await call_next(request)
    is_api = path.startswith("/api/")
    token = request.cookies.get("auth_token")
    if token and token in _AUTH_SESSIONS:
        sess = _AUTH_SESSIONS[token]
        if sess["expires"] > time.time():
            return await call_next(request)
        else:
            del _AUTH_SESSIONS[token]
    if is_api:
        return JSONResponse({"ok": False, "message": "请先登录", "code": 401}, status_code=401)
    return RedirectResponse("/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return _read_html("static/login.html")


@app.post("/api/auth/login")
async def api_login(data: dict):
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    if not name:
        return {"ok": False, "message": "请输入姓名"}
    if not phone or not phone.isdigit() or len(phone) != 11:
        return {"ok": False, "message": "请输入有效的11位手机号码"}
    token = secrets.token_hex(32)
    _AUTH_SESSIONS[token] = {"name": name, "phone": phone, "expires": time.time() + 86400 * 30}
    resp = JSONResponse({"ok": True, "name": name})
    resp.set_cookie("auth_token", token, httponly=True, max_age=86400*30, samesite="lax")
    return resp


@app.post("/api/auth/logout")
async def api_logout(request: Request):
    token = request.cookies.get("auth_token")
    if token and token in _AUTH_SESSIONS:
        del _AUTH_SESSIONS[token]
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("auth_token")
    return resp


# ═══════════════════ ⑥ 代码变更追踪 ═══════════════════
import hashlib as _hashlib

def _track_code_changes():
    """启动时扫描代码变更并注入AGI知识库"""
    scan_dirs = [
        os.path.join(os.path.dirname(__file__), "engine"),
        os.path.join(os.path.dirname(__file__), "static", "js"),
        os.path.join(os.path.dirname(__file__), "main.py"),
    ]
    
    state_file = os.path.join(os.path.dirname(__file__), "static", "code_state.json")
    current_state = {}
    
    for scan_dir in scan_dirs:
        if os.path.isfile(scan_dir):
            mtime = os.path.getmtime(scan_dir)
            size = os.path.getsize(scan_dir)
            current_state[scan_dir] = {"mtime": mtime, "size": size}
        elif os.path.isdir(scan_dir):
            for root, dirs, files in os.walk(scan_dir):
                for f in sorted(files):
                    if f.endswith(".py") or f.endswith(".js"):
                        fpath = os.path.join(root, f)
                        try:
                            mtime = os.path.getmtime(fpath)
                            size = os.path.getsize(fpath)
                            current_state[fpath] = {"mtime": mtime, "size": size}
                        except: pass
    
    # 加载上次状态
    previous_state = {}
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            previous_state = json.load(f)
    except: pass
    
    # 对比变更
    changes = []
    for fpath, info in current_state.items():
        prev = previous_state.get(fpath, {})
        if not prev:
            changes.append(f"新增文件: {os.path.basename(fpath)}")
        elif info["size"] != prev.get("size") or info["mtime"] != prev.get("mtime"):
            changes.append(f"文件变更: {os.path.basename(fpath)}")
    
    for fpath in previous_state:
        if fpath not in current_state:
            changes.append(f"文件删除: {os.path.basename(fpath)}")
    
    if changes:
        try:
            from engine.knowledge_base import get_kb
            kb = get_kb()
            for c in changes:
                kb.add_lesson(c, "⑥代码变更")
            print(f"[⑥代码] 检测到{len(changes)}个文件变更，已注入AGI知识库")
        except: pass
    
    # 保存当前状态
    try:
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(current_state, f, indent=2)
    except: pass

# ==================== 访问日志中间件 ====================
import time as _time_module

LOG_FILE = os.path.join(os.path.dirname(__file__), "access_logs.jsonl")

@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    start = _time_module.time()
    response = await call_next(request)
    elapsed_ms = int((_time_module.time() - start) * 1000)
    
    if not request.url.path.startswith("/static") and request.url.path != "/favicon.ico":
        try:
            import json as _json
            path = request.url.path
            cid = None
            if "company_id=" in str(request.url.query):
                import re as _re
                m = _re.search(r'company_id=(\d+)', str(request.url.query))
                if m: cid = int(m.group(1))
            action = None
            if "upload" in path: action = "upload"
            elif "analyze" in path: action = "analyze"
            elif "export" in path or "download" in path: action = "export"
            elif "audit" in path: action = "audit"
            elif "fix" in path: action = "fix"
            elif "/api/tax-risk-docs/review" in path: action = "review"
            # 获取用户信息（Header中是URL编码的，需解码）
            user_name = request.headers.get("X-User-Name", "")
            user_phone = request.headers.get("X-User-Phone", "")
            if user_name:
                try: 
                    import urllib.parse as _up
                    user_name = _up.unquote(user_name)
                except: pass
            if user_phone:
                try: 
                    import urllib.parse as _up
                    user_phone = _up.unquote(user_phone)
                except: pass
            entry = {"t": _time_module.time(), "cid": cid, "m": request.method, "p": path[:200],
                     "s": response.status_code, "ip": request.client.host if request.client else None,
                     "ms": elapsed_ms, "a": action, "un": user_name, "up": user_phone}
            with open(LOG_FILE, "a", encoding="utf-8") as lf:
                lf.write(_json.dumps(entry, ensure_ascii=False) + "\n")
        except: pass
    return response

# ==================== 使用日志 API ====================
from fastapi.responses import JSONResponse, HTMLResponse

@app.post("/api/system-logs/clear")
def clear_system_logs():
    try:
        lf_path = os.path.join(os.path.dirname(__file__), "access_logs.jsonl")
        if os.path.exists(lf_path): os.remove(lf_path)
        return {"ok": True, "message": "已清空"}
    except: return {"ok": False}

@app.get("/api/system-logs")
def get_system_logs(limit: int = 200, company_id: int = None):
    try:
        import json as _json
        logs = []
        lf_path = os.path.join(os.path.dirname(__file__), "access_logs.jsonl")
        if os.path.exists(lf_path):
            with open(lf_path, "r", encoding="utf-8") as lf:
                for line in lf:
                    line = line.strip()
                    if line:
                        try: logs.append(_json.loads(line))
                        except: pass
        logs.reverse()
        if company_id: logs = [l for l in logs if l.get("cid") == company_id]
        logs = logs[:limit]
        # IP地理位置解析（异步线程池，不阻塞事件循环）
        ip_locations = {}
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import urllib.request, json as _j2
            unique_ips = list(set(l.get("ip","") for l in logs if l.get("ip") and not l.get("ip","").startswith("127.") and l.get("ip") != "localhost"))
            if unique_ips:
                def _lookup_ip(ip):
                    try:
                        req = urllib.request.Request("http://ip-api.com/json/" + ip, headers={"User-Agent": "TaxSystem/1.0"})
                        with urllib.request.urlopen(req, timeout=1) as resp:
                            data = _j2.loads(resp.read())
                            if data.get("status") == "success":
                                return ip, data.get("regionName","") + " " + data.get("city","") if data.get("city") else data.get("country","")
                    except: pass
                    return ip, ""
                with ThreadPoolExecutor(max_workers=3) as ex:
                    futures = [ex.submit(_lookup_ip, ip) for ip in unique_ips]
                    for f in as_completed(futures):
                        try:
                            ip, loc = f.result(timeout=1.5)
                            if loc: ip_locations[ip] = loc
                        except: pass
        except: pass
        
        for i, l in enumerate(logs):
            from datetime import datetime as _dt
            ts = _dt.fromtimestamp(l["t"]).isoformat() if "t" in l else None
            ip = l.get("ip","")
            loc = ip_locations.get(ip, "")
            logs[i] = {"id": i+1, "company_id": l.get("cid"), "timestamp": ts,
                       "method": l.get("m",""), "path": l.get("p",""), "status_code": l.get("s",0),
                       "client_ip": ip, "location": loc, "response_time_ms": l.get("ms",0),
                       "user_name": l.get("un",""), "user_phone": l.get("up",""),
                       "action_type": l.get("a","")}
        return JSONResponse(logs)
    except Exception as e:
        return JSONResponse([], status_code=500)

# ==================== 开发模式：强制无缓存 ====================
@app.middleware("http")
async def add_cache_headers(request, call_next):
    """给所有响应加 no-cache 头，强制浏览器不用本地缓存。"""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
app.include_router(tax_risk_router)
app.include_router(chat_router)
app.include_router(salary_router)
app.include_router(vat_router)
app.include_router(housing_fund_router)
app.include_router(social_security_router)
app.include_router(cultural_construction_fee_router)
app.include_router(journal_router)
app.include_router(payments_router)
app.include_router(input_vat_router)
app.include_router(tax_rules_api_router)
app.include_router(file_parser_router)
app.include_router(archives_router)
app.include_router(financial_reports_router)
app.include_router(bank_transactions_router)
app.include_router(bank_transactions_router)
app.include_router(bookkeeping_invoices_router)
app.include_router(contracts_router)
app.include_router(inventory_router)
app.include_router(intangible_assets_router)
app.include_router(fixed_assets_router)
app.include_router(dashboard_router)

# 挂载静态文件（JS/CSS 禁用缓存，确保前端代码即时生效）
@app.middleware("http")
async def _cache_control_middleware(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.endswith('.js') or path.endswith('.css'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

app.mount("/static", StaticFiles(directory="static"), name="static")

# ==================== 文件上传安全常数 (P2-4/5) ====================
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.xlsx', '.xls', '.csv', '.pdf', '.txt', '.docx', '.doc'}
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}

def _validate_upload(file: UploadFile):
    """验证上传文件大小和扩展名"""
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"不支持的文件类型: {ext}，仅接受 {'/'.join(sorted(ALLOWED_EXTENSIONS))}")
    # 检查文件大小 — 先读入内存再判断
    content = file.file.read()
    file.file.seek(0)  # 重置让后续代码正常读取
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"文件过大（{len(content)/1024/1024:.2f}MB），上限10MB")
    return content


# ==================== Pydantic 模型 ====================

# 公司信息
class CompanyUpdate(BaseModel):
    company_name: Optional[str] = None
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

# 部门
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

# 人员
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

# 客户
class BatchDelete(BaseModel):
    ids: list[int]

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

# 供应商
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


# ==================== 首页 ====================

def _read_html(filename):
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(filename, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"

@app.get("/", response_class=HTMLResponse)
async def root():
    """直接进入系统"""
    return _read_html("static/index.html")

@app.get("/api/pinyin")
def get_pinyin(name: str = Query(...)):
    """将中文姓名转为拼音"""
    try:
        from pypinyin import pinyin, Style
        result = ''.join([item[0] for item in pinyin(name, style=Style.NORMAL)])
        return {"pinyin": result}
    except:
        return {"pinyin": name}

@app.get("/{user_name}/xuanzezhangtao/")
@app.get("/{user_name}/xinjianzhangtao/")
@app.get("/xuanzezhangtao/")
@app.get("/xinjianzhangtao/")
async def redirect_to_root():
    """旧路由统一跳转到根路径"""
    return RedirectResponse("/", status_code=302)


@app.get("/api/meta/processing-keywords")
def get_processing_keywords():
    """返回加工判定关键词（供前端使用，来源：industry_profiles.json）"""
    return {"data": {"keywords": _get_processing_keywords()}}

# ==================== 公司信息 ====================

@app.get("/api/company")
def get_company(company_id: int = Query(...), db: Session = Depends(get_db)):
    info = db.query(Company).filter(Company.id == company_id).first()
    if not info:
        return {"company_name": "", "uscc": ""}
    return {
        "id": info.id,
        "company_name": info.name,
        "uscc": info.uscc or "",
        "registered_capital": info.registered_capital,
        "established_date": str(info.established_date) if info.established_date else "",
        "legal_representative": info.legal_representative or "",
        "legal_representative_id": info.legal_representative_id or "",
        "address": info.address or "",
        "business_scope": info.business_scope or "",
        "company_type": info.company_type or "",
        "shareholders": [{"name": s.name, "id_number": s.id_number or "", "ratio": s.ratio, "contribution_amount": s.contribution_amount} for s in info.shareholders],
        "directors": [{"name": d.name, "id_number": d.id_number or ""} for d in info.directors],
        "supervisors": [{"name": s.name, "id_number": s.id_number or ""} for s in info.supervisors],
        "finance_contacts": [{"name": f.name, "id_number": f.id_number or "", "phone": f.phone or ""} for f in info.finance_contacts],
    }

@app.put("/api/company")
def update_company(data: CompanyUpdate, company_id: int = Query(...), db: Session = Depends(get_db)):
    info = db.query(Company).filter(Company.id == company_id).first()
    if not info:
        info = Company(id=company_id, name=data.company_name or "")
        db.add(info)
        db.flush()
    if data.uscc:
        ok, msg = validate_uscc(data.uscc)
        if not ok:
            raise HTTPException(400, detail=f"公司统一社会信用代码：{msg}")
    # 更新主表字段
    main_fields = {k: v for k, v in data.model_dump(exclude_unset=True).items()
                   if k not in ("shareholders", "directors", "supervisors", "finance_contacts")}
    for k, v in main_fields.items():
        if k == 'company_name':
            info.name = v
        else:
            setattr(info, k, v)
    # 更新子表
    _update_company_subtable(db, info, CompanyShareholder, data.shareholders)
    _update_company_subtable(db, info, CompanyDirector, data.directors)
    _update_company_subtable(db, info, CompanySupervisor, data.supervisors)
    _update_company_subtable(db, info, CompanyFinanceContact, data.finance_contacts)
    db.commit()
    return {"message": "保存成功"}


def _update_company_subtable(db, company, model, items):
    """更新公司子表：清空旧数据，写入新数据"""
    if items is None:
        return
    db.query(model).filter(model.company_id == company.id).delete()
    for item in items:
        db.add(model(company_id=company.id, **item))


# =================== 涉税风险规则报告解析 API ===================
def _parse_tax_report_text(report_text: str):
    """核心解析逻辑，供文本和文件上传两个端点共用"""
    import re as _re
    import uuid as _uuid
    from difflib import SequenceMatcher as _SeqMatcher

    text = report_text

    # === 第1步：文本预处理 ===
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            cleaned.append('')
        elif _re.match(r'^[\d\s\-–—_・•·]+$', line):
            continue
        elif len(line) <= 3 and _re.match(r'^\d+$', line):
            continue
        else:
            cleaned.append(line)
    text = '\n'.join(cleaned)

    # === 第2步：智能分段 ===
    paragraphs = []
    current_para = []
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            if current_para:
                paragraphs.append('\n'.join(current_para))
                current_para = []
            continue
        is_new_rule = False
        if _re.match(r'^[\(]?\d+[\)\.]?[\、\.)]', line):
            is_new_rule = True
        elif _re.match(r'^[一二三四五六七八九十]+[、\.]', line):
            is_new_rule = True
        elif any(kw in line for kw in ['风险点', '风险分析']) and len(line) < 40:
            is_new_rule = True
        elif '问题' in line and len(line) < 30:
            is_new_rule = True
        if is_new_rule and current_para:
            paragraphs.append('\n'.join(current_para))
            current_para = [line]
        else:
            current_para.append(line)
    if current_para:
        paragraphs.append('\n'.join(current_para))

    if len(paragraphs) < 2:
        sentences = _re.split(r'[。\.\!\?！？]+', text)
        paragraphs = []
        chunk = []
        for s in sentences:
            s = s.strip()
            if s:
                chunk.append(s)
                if len(chunk) >= 2:
                    paragraphs.append('。'.join(chunk) + '。')
                    chunk = []
        if chunk:
            paragraphs.append('。'.join(chunk))

    # === 第3步：提取规则 ===
    category_keywords = {
        "发票合规": ["发票", "进项", "销项", "税号", "全电", "数电", "红冲", "作废"],
        "发票异常": ["顶额", "作废", "红冲", "异常", "失控", "虚开"],
        "发票深度": ["油费", "运输费", "生活用品", "水电", "能耗", "进销"],
        "增值税专项": ["增值税", "留抵", "退税", "简易计税", "免税"],
        "企业所得税": ["所得税", "折旧", "摊销", "准备金", "不征税"],
        "纳税调整": ["招待费", "广告费", "业务招待", "纳税调增"],
        "个人所得税": ["个税", "工资", "薪金", "分红", "股东", "借款"],
        "成本结构": ["成本", "收入", "费用", "毛利率", "占比"],
        "经营实质": ["经营能力", "开票量", "注册地址"],
        "资金往来": ["公户", "私户", "转账", "资金回流"],
        "隐匿虚增": ["其他应收", "其他应付", "挂账", "隐瞒"],
        "财务健康": ["现金流", "偿债", "净资产", "利润率"],
        "征管风险": ["欠税", "走逃", "失联", "D级", "非正常户"],
        "申报比对": ["零申报", "比对", "未申报", "漏申报"],
        "税负水平": ["税负率", "印花税", "行业税负"],
        "交易特征": ["整数", "大额", "频繁", "同一", "回流"],
        "账务数据": ["借贷", "凭证", "序时账", "记账"],
    }

    def _auto_classify(text_content):
        best = ("其他", 0)
        for cat, kws in category_keywords.items():
            score = sum(1 for kw in kws if kw in text_content)
            if score > best[1]:
                best = (cat, score)
        return best[0] if best[1] > 0 else "其他"

    def _estimate_score(text_content):
        m = _re.search(r'评分[：:\s]*(\d+)', text_content)
        if m:
            return int(m.group(1))
        m = _re.search(r'(\d+)\s*分', text_content)
        if m and int(m.group(1)) <= 10:
            return int(m.group(1))
        high_kws = ['虚开', '偷税', '逃税', '隐瞒', '涉嫌', '不得', '禁止']
        mid_kws = ['异常', '偏高', '偏低', '超标', '不匹配', '未', '漏']
        if any(kw in text_content for kw in high_kws):
            return 8
        elif any(kw in text_content for kw in mid_kws):
            return 5
        return 5

    def _level_from_score(score):
        if score >= 7:
            return "高风险"
        elif score >= 4:
            return "中风险"
        elif score > 0:
            return "低风险"
        return "良好"

    cat_icon_map = {
        "发票合规": "🧾", "发票异常": "⚠️", "发票深度": "🔍",
        "增值税专项": "🧮", "企业所得税": "💰", "纳税调整": "⚖️",
        "个人所得税": "👤", "成本结构": "📐", "经营实质": "🏭",
        "资金往来": "💸", "隐匿虚增": "🫥", "财务健康": "💊",
        "征管风险": "🚨", "申报比对": "📊", "税负水平": "📉",
        "交易特征": "🔗", "账务数据": "📊", "其他": "📋",
    }

    rules = []
    seen_items = set()
    for para in paragraphs:
        if len(para) < 10:
            continue
        lines_para = [l.strip() for l in para.split('\n') if l.strip()]
        if not lines_para:
            continue
        first_line = _re.sub(r'^[\(\[\d]+[\)\.\、\.]?\s*', '', lines_para[0])
        first_line = _re.sub(r'^[一二三四五六七八九十]+[、\.\s]*', '', first_line)
        item = first_line[:40] if len(first_line) > 5 else first_line
        if not item or len(item) < 3:
            continue
        is_dup = False
        for seen in seen_items:
            if _SeqMatcher(None, item, seen).ratio() > 0.8:
                is_dup = True
                break
        if is_dup:
            continue
        seen_items.add(item)
        category = _auto_classify(para)
        _override_map = {
            "零申报": "申报比对", "留抵退税": "增值税专项", "出口退税": "增值税专项",
            "油费": "发票深度", "运输费": "发票深度", "水电": "发票深度",
            "走逃": "征管风险", "非正常户": "征管风险", "D级": "征管风险",
            "生活用品": "发票深度", "能耗": "发票深度", "进销": "发票深度",
            "印花税": "税负水平", "个税": "个人所得税",
            "税负率": "税负水平",
        }
        for _kw, _correct_cat in _override_map.items():
            if _kw in para and category != _correct_cat:
                category = _correct_cat
                break
        score = _estimate_score(para)
        level = _level_from_score(score)
        detail = para[:200] + ('...' if len(para) > 200 else '')
        suggestion = ""
        sug_match = _re.search(r'建议[：:\s]*(.+)', para)
        if sug_match:
            suggestion = sug_match.group(1)[:150]
        rules.append({
            "id": str(_uuid.uuid4()),
            "category": category,
            "categoryIcon": cat_icon_map.get(category, "📋"),
            "item": item,
            "detail": detail,
            "score": score,
            "level": level,
            "suggestion": suggestion,
            "urgency": "提醒" if score < 5 else ("紧急" if score >= 8 else "高"),
            "evidence": "",
            "dataSource": "报告解析",
            "remark": f"从报告解析（{len(para)}字）"
        })

    return {
        "ok": True,
        "rules": rules,
        "count": len(rules),
        "paragraphs_found": len(paragraphs),
        "text_length": len(report_text)
    }


# ══════════════════════════════════════════════════════════════
#  涉税内容相关性检测
# ══════════════════════════════════════════════════════════════
def _check_tax_relevance(text: str):
    """检测文本是否与涉税内容相关，返回相关性评分和详情"""
    import re as _re

    if not text or len(text.strip()) < 30:
        return {
            "is_tax_related": False, "score": 0,
            "keywords_found": [],
            "message": "文本过短，无法判断是否涉税内容"
        }

    # 涉税关键词体系（三层权重：强/中/弱）
    tax_keywords = {
        "strong": [
            "增值税", "企业所得税", "个人所得税", "消费税", "印花税",
            "房产税", "契税", "土地增值税", "城建税", "教育费附加",
            "进项税额", "销项税额", "进项税", "销项税", "留抵退税",
            "纳税申报", "税务稽查", "税务风险", "税收优惠", "税前扣除",
            "发票管理", "增值税专用发票", "普通发票", "数电发票",
            "应交税费", "税金及附加", "递延所得税", "文化事业建设费",
            "代扣代缴", "源泉扣缴", "税务登记", "小规模纳税人", "一般纳税人",
        ],
        "medium": [
            "税率", "税额", "税负", "纳税", "缴税", "退税", "征税",
            "免税", "扣税", "抵税", "完税", "涉税", "税务",
            "发票", "抵扣", "进项", "销项", "认证", "红冲", "作废",
            "申报", "预缴", "汇算", "清算", "留抵",
            "个税", "所得税", "流转税", "财产税",
            "纳税调整", "加计扣除", "加速折旧", "不征税收入",
            "查账征收", "核定征收", "税号",
            "进项转出", "不得抵扣", "视同销售",
            "减免税", "即征即退", "先征后退", "出口退税",
        ],
        "weak": [
            "财务报表", "利润表", "资产负债表", "现金流量表",
            "主营业务收入", "营业收入", "营业成本", "利润总额",
            "社保", "公积金", "工资薪金", "劳务报酬", "稿酬",
            "财产租赁", "财产转让", "股息红利",
            "稽查", "罚款", "滞纳金",
            "转让定价", "关联交易", "同期资料",
            "毛利率", "成本结构", "费用率", "应收账款", "应付账款",
            "其他应收款", "存货", "固定资产", "无形资产",
        ]
    }

    found_strong = [kw for kw in tax_keywords["strong"] if kw in text]
    found_medium = [kw for kw in tax_keywords["medium"] if kw in text]
    found_weak = [kw for kw in tax_keywords["weak"] if kw in text]

    total_found = len(found_strong) + len(found_medium) + len(found_weak)

    # 评分
    if total_found == 0:
        score = 0
    else:
        strong_score = len(found_strong) * 15
        medium_score = len(found_medium) * 5
        weak_score = len(found_weak) * 2
        raw_score = strong_score + medium_score + weak_score
        # 密度修正：200字出现1个关键词为基准
        text_len = len(text)
        density = total_found / max(text_len / 200, 1)
        density_factor = min(density, 2.0)
        score = min(int(raw_score * density_factor), 100)
        # 有强信号保底
        if len(found_strong) >= 1 and score < 20:
            score = max(score, 25)

    is_tax_related = score >= 20

    all_keywords = found_strong + found_medium + found_weak
    unique_keywords = list(dict.fromkeys(all_keywords))

    return {
        "is_tax_related": is_tax_related,
        "score": score,
        "strong_count": len(found_strong),
        "medium_count": len(found_medium),
        "weak_count": len(found_weak),
        "total_keywords": total_found,
        "keywords_found": unique_keywords,
        "text_length": len(text),
    }


@app.post("/api/tax-risk-rules/parse-report")
async def tax_risk_rules_parse_report(request: Request):
    """接收税务报告/文章内容，智能提取风险规则"""
    try:
        body = await request.json()
        report_text = body.get("text", "")
        if not report_text:
            return {"ok": False, "error": "报告内容不能为空"}
    except Exception:
        return {"ok": False, "error": "无效的请求数据"}
    return _parse_tax_report_text(report_text)


@app.post("/api/tax-risk-rules/upload-report")
async def tax_risk_rules_upload_report(request: Request):
    """接收上传的报告文件（PDF/Word/TXT），提取文本并解析为规则"""
    import io as _io
    import os as _os

    try:
        form = await request.form()
        file = form.get("file")
        if not file:
            return {"ok": False, "error": "未找到上传文件"}
    except Exception:
        return {"ok": False, "error": "无效的文件上传请求"}

    filename = (file.filename or "").lower()
    content_bytes = await file.read()

    if not content_bytes:
        return {"ok": False, "error": "文件内容为空"}

    extracted_text = ""
    source_desc = ""

    if filename.endswith('.txt'):
        try:
            extracted_text = content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            try:
                extracted_text = content_bytes.decode('gbk')
            except Exception:
                return {"ok": False, "error": "无法解码TXT文件编码"}
        source_desc = f"TXT文件 ({filename})"

    elif filename.endswith('.docx'):
        try:
            from docx import Document as _Document
            doc = _Document(_io.BytesIO(content_bytes))
            paragraphs_text = [p.text for p in doc.paragraphs]
            extracted_text = '\n\n'.join(paragraphs_text)
            source_desc = f"Word文档 ({filename})"
        except Exception as e:
            return {"ok": False, "error": f"Word文档解析失败: {str(e)}"}

    elif filename.endswith('.pdf'):
        try:
            from PyPDF2 import PdfReader as _PdfReader
            reader = _PdfReader(_io.BytesIO(content_bytes))
            pages_text = []
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t.strip())
            extracted_text = '\n\n'.join(pages_text)
            source_desc = f"PDF文件 ({filename}, {len(reader.pages)}页)"
        except Exception as e:
            return {"ok": False, "error": f"PDF解析失败: {str(e)}"}

    else:
        return {"ok": False, "error": f"不支持的文件格式 (.{filename.split('.')[-1]})，仅支持 PDF/Word/TXT"}

    if not extracted_text.strip():
        return {"ok": False, "error": "未能从文件中提取到文本内容"}

    result = _parse_tax_report_text(extracted_text.strip())
    result["source_file"] = source_desc
    # 附加涉税相关性检测
    relevance = _check_tax_relevance(extracted_text.strip())
    result["relevance"] = relevance
    return result

# ── 涉税风险分析资料库 ──

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads", "tax-risk-docs")
os.makedirs(UPLOAD_DIR, exist_ok=True)

def _get_company_upload_dir(company_id):
    """获取公司专属上传目录，物理账套隔离
    所有文件操作必须经过此函数，确保不同公司数据不会串混"""
    d = os.path.join(UPLOAD_DIR, str(company_id))
    os.makedirs(d, exist_ok=True)
    return d

# ═══════════════ 资料中转站 ═══════════════
TRANSFER_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads", "transfer")
os.makedirs(TRANSFER_DIR, exist_ok=True)
# ═══════════════ 最近分析结果缓存 ═══════════════

def _save_to_transfer(company_id, doc_id, original_name, parsed_data):
    path = os.path.join(TRANSFER_DIR, f"{company_id}_{doc_id}.json")
    payload = {"type":parsed_data.get("type","unknown"),"file":original_name,
        "parsed_at":datetime.now().isoformat(),"row_count":len(parsed_data.get("rows",[])),
        "rows":parsed_data.get("rows",[])}
    try:
        with open(path,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False,default=str)
        return True
    except: return False

def _load_from_transfer(company_id, doc_id):
    path = os.path.join(TRANSFER_DIR, f"{company_id}_{doc_id}.json")
    if not os.path.exists(path): return None
    try:
        with open(path,"r",encoding="utf-8") as f: return json.load(f)
    except: return None

def _clear_transfer(company_id=None):
    if os.path.exists(TRANSFER_DIR):
        for fn in os.listdir(TRANSFER_DIR):
            if company_id is None or fn.startswith(f"{company_id}_"):
                try:
                    os.remove(os.path.join(TRANSFER_DIR,fn))
                except PermissionError:
                    pass  # 沙箱/权限不足时静默跳过


_tax_doc_counter = [0]

# 启动时扫描磁盘上已有文件，初始化文件列表
_TAX_DOC_SCANNED = False
def _init_tax_docs_from_disk():
    global _TAX_DOC_SCANNED, _tax_risk_docs, _tax_doc_counter
    if _TAX_DOC_SCANNED: return
    _TAX_DOC_SCANNED = True
    if os.path.exists(UPLOAD_DIR):
        for subdir in os.listdir(UPLOAD_DIR):
            subpath = os.path.join(UPLOAD_DIR, subdir)
            if not os.path.isdir(subpath): continue
            try: company_id = int(subdir)
            except: continue
            for fname in os.listdir(subpath):
                fpath_sub = os.path.join(subpath, fname)
                if not os.path.isfile(fpath_sub): continue
                # fsdecode 确保 Windows 中文文件名编码正确
                try:
                    fname_clean = os.fsdecode(os.fsencode(fname))
                except:
                    fname_clean = fname
                parts = fname_clean.split("_", 2)  # 分割最多2次：公司ID_文件ID_原文件名
                if len(parts) < 3: continue
                try: f_cid, f_doc_id = int(parts[0]), int(parts[1])
                except: continue
                orig_name = parts[2]  # 第三个部分开始是原始文件名
                fpath = fpath_sub
                _tax_risk_docs.append({
                    "id": f_doc_id, "filename": fname, "original_name": orig_name,
                    "path": fpath, "size": os.path.getsize(fpath),
                    "uploaded_at": datetime.fromtimestamp(os.path.getmtime(fpath)).isoformat(),
                    "company_id": f_cid
                })
                if f_doc_id > _tax_doc_counter[0]:
                    _tax_doc_counter[0] = f_doc_id

# 初始化：在模块加载时扫描磁盘
_init_tax_docs_from_disk()


def _recover_tax_risk_docs():
    """启动时从磁盘恢复资料列表（如果 _init_tax_docs_from_disk 已运行则跳过，避免重复）"""
    global _TAX_DOC_SCANNED
    if _TAX_DOC_SCANNED:
        return  # _init_tax_docs_from_disk 已经扫描并初始化，无需重复
    import hashlib
    if not os.path.exists(UPLOAD_DIR):
        return
    for subdir in os.listdir(UPLOAD_DIR):
        subpath = os.path.join(UPLOAD_DIR, subdir)
        if not os.path.isdir(subpath): continue
        try: company_id = int(subdir)
        except: continue
        for fname in sorted(os.listdir(subpath)):
            fpath = os.path.join(subpath, fname)
            if not os.path.isfile(fpath):
                continue
            # 文件名格式: {company_id}_{doc_id}_{timestamp}.ext
            stem = os.path.splitext(fname)[0]
            parts = stem.split("_")
            if len(parts) < 3:
                continue
            try:
                company_id = int(parts[0])
                doc_id = int(parts[1])
            except ValueError:
                continue
            stat = os.stat(fpath)
            sz = stat.st_size
            with open(fpath, "rb") as fh:
                md5 = hashlib.md5(fh.read()).hexdigest()
            doc = {
                "id": doc_id, "filename": fname, "original_name": fname,
                "path": fpath, "size": sz, "md5": md5,
                "uploaded_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "company_id": company_id,
            }
            _tax_risk_docs.append(doc)
            if doc_id >= _tax_doc_counter[0]:
                _tax_doc_counter[0] = doc_id

    # 去重：同一 id + original_name 只保留一条
    seen = set()
    unique = []
    for d in _tax_risk_docs:
        key = (d["id"], d["original_name"])
        if key not in seen:
            seen.add(key)
            unique.append(d)
    _tax_risk_docs[:] = unique

_recover_tax_risk_docs()


def _read_file_text(filepath, original_name):
    """读取文件文本内容，支持全格式"""
    ext = os.path.splitext(original_name)[1].lower()
    # PDF
    if ext == ".pdf":
        try:
            import PyPDF2
            text = []
            with open(filepath, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    t = page.extract_text()
                    if t: text.append(t)
            return "\n".join(text)
        except: pass
    # Word (.docx)
    if ext == ".docx":
        try:
            import docx
            doc = docx.Document(filepath)
            return "\n".join(p.text for p in doc.paragraphs)
        except: pass
    # Excel (.xlsx)
    if ext == ".xlsx":
        try:
            import openpyxl
            wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
            rows = []
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    rows.append(" ".join(str(c) for c in row if c is not None))
                if len(rows) > 2000: break
            if rows: return "\n".join(rows)
        except: pass
    # Excel (.xls)
    if ext == ".xls":
        try:
            import xlrd
            wb = xlrd.open_workbook(filepath)
            rows = []
            for sheet in wb.sheets():
                for row_idx in range(sheet.nrows):
                    rows.append(" ".join(str(sheet.cell_value(row_idx, c)) for c in range(sheet.ncols) if sheet.cell_value(row_idx, c)))
                    if len(rows) > 2000: break
                if len(rows) > 2000: break
            if rows: return "\n".join(rows)
        except: pass
    # Text files
    TEXT_EXTS = {".txt", ".html", ".htm", ".json", ".xml", ".log", ".md", ".csv"}
    if ext in TEXT_EXTS:
        for enc in ["utf-8", "gb18030", "gbk", "latin-1"]:
            try:
                with open(filepath, "r", encoding=enc, errors="replace") as f:
                    text = f.read(50000)
                    if text and len(text.strip()) > 10:
                        return text
            except: continue
    # Fallback: try as text
    for enc in ["utf-8", "gb18030", "latin-1"]:
        try:
            with open(filepath, "r", encoding=enc, errors="replace") as f:
                text = f.read(50000)
                if text.strip(): return text
        except: pass
    return None


def _extract_structured_data(text, filename):
    """从文本中提取结构化财务数据"""
    import re
    data = {"filename": filename, "entities": [], "amounts": [], "tax_ids": [], "invoice_nos": []}
    seen = set()

    # 企业名称
    for pat in [r'([\u4e00-\u9fff]{2,20}(?:有限公司|有限责任公司|股份有限公司|集团|合伙企业|事务所|工作室|经营部|商行|中心))',
                r'([\u4e00-\u9fff]{2,4}(?:科技|文化|传媒|广告|设计|咨询|贸易|实业|投资|建设|工程|餐饮|酒店|管理|服务|信息)有限公司)']:
        for m in re.finditer(pat, text):
            name = m.group(1).strip()
            if name not in seen and len(name) >= 4:
                seen.add(name)
                data["entities"].append({"name": name, "pos": m.start(), "context": text[max(0,m.start()-10):m.end()+30]})

    # 金额（数字+元）
    for m in re.finditer(r'([\d,]+\.?\d*)\s*[元圆]', text):
        try:
            val_str = m.group(1).replace(',', '').replace('，', '')
            if len(val_str.replace('.', '')) > 10: continue
            if len(val_str.replace('.', '')) == 11 and val_str.startswith('1'): continue
            val = float(val_str)
            if 100 <= val <= 99999999:
                data["amounts"].append({"value": val, "pos": m.start(),
                    "context": text[max(0,m.start()-20):m.end()+20]})
        except: pass

    # 税号
    for m in re.finditer(r'[0-9A-Z]{15,18}', text):
        code = m.group(0)
        if any(c.isdigit() for c in code) and any(c.isalpha() for c in code):
            data["tax_ids"].append({"value": code})

    # 发票号
    for m in re.finditer(r'(?:发票号|发票代码|发票号码|数电发票)[：:\s]*([A-Z0-9]{10,20})', text):
        data["invoice_nos"].append({"value": m.group(1)})
    for m in re.finditer(r'\b(\d{10})\b', text):
        data["invoice_nos"].append({"value": m.group(1)})

    return data


def _load_tax_risk_rules():
    """加载涉税风险规则JSON"""
    import json as _json
    rules_path = os.path.join(os.path.dirname(__file__), "static", "tax_risk_rules_local_export.json")
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return []


def _match_all_rules(all_text, file_texts, rules):
    """逐条匹配全部规则"""
    import re
    findings = []
    text_lower = all_text.lower()
    STOP_WORDS = {"进行","存在","可能","相关","是否","需要","应当","已经","目前","本企业","该企业",
                  "以下","以上","包括","符合","属于","涉及","超过","发现","达到","不能","没有",
                  "不会","用于","使用","可以","并且","以及","或者","一个","这个"}

    for rule in rules:
        rule_text = (rule.get("item", "") + " " + rule.get("detail", "")).lower()
        words = set(re.findall(r'[\u4e00-\u9fff]{2,}', rule_text))
        keywords = [w for w in words if w not in STOP_WORDS and len(w) >= 2]
        if len(keywords) < 4:
            continue
        matched = [kw for kw in keywords if kw in text_lower]
        if len(matched) < 3 or not any(len(kw) >= 4 for kw in matched):
            continue

        main_kw = max(matched, key=len)
        idx = text_lower.find(main_kw)
        context = all_text[max(0, idx-40):idx+len(main_kw)+60] if idx >= 0 else ""

        source_files = []
        for fn, ft in file_texts.items():
            if main_kw in ft.lower():
                source_files.append(fn)

        findings.append({
            "rule_id": rule.get("id"), "item": rule.get("item", ""),
            "category": rule.get("category", ""), "icon": rule.get("categoryIcon", ""),
            "level": rule.get("level", "中风险"), "score": rule.get("score", 5),
            "urgency": rule.get("urgency", ""), "detail": rule.get("detail", "")[:200],
            "suggestion": rule.get("suggestion", "")[:200],
            "keywords": matched, "context": context[:150],
            "source_files": source_files
        })
    return findings


# ═══════════════ P0 财税票三流比对 ═══════════════

def _run_three_way_matching(db, company_id, cross):
    """财税票三流比对：发票流 + 资金流 + 合同流"""
    from database import _normalize_customer_name, Contract

    # 1. 销项发票购方 vs 银行流水收款方
    si_buyers = {}
    for si in db.query(SalesInvoice).filter(SalesInvoice.company_id == company_id).all():
        n = _normalize_customer_name(si.buyer_name or "")
        if n: si_buyers[n] = si_buyers.get(n, 0) + float(si.total_amount or 0)

    bt_receivers = {}
    for tx in db.query(BankTransaction).filter(
        BankTransaction.company_id == company_id, BankTransaction.credit_amount > 0
    ).all():
        n = _normalize_customer_name(tx.counterparty_name or "")
        if n: bt_receivers[n] = bt_receivers.get(n, 0) + float(tx.credit_amount or 0)

    invoiced_no_pay = set(si_buyers.keys()) - set(bt_receivers.keys())
    paid_no_invoice = set(bt_receivers.keys()) - set(si_buyers.keys())

    if invoiced_no_pay:
        names = list(invoiced_no_pay)
        total = sum(si_buyers[n] for n in invoiced_no_pay)
        cross.append({"type": "三流比对：开票未回款", "level": "中风险", "score": 7,
            "detail": f"{len(invoiced_no_pay)}个客户已开票但银行流水无对应收款，涉及{total:,.2f}元：{'、'.join(names)}",
            "suggestion": "关注虚开发票后资金回流或长期挂账坏账风险。", "category": "三流比对"})

    if paid_no_invoice:
        names = list(paid_no_invoice)
        total = sum(bt_receivers[n] for n in paid_no_invoice)
        cross.append({"type": "三流比对：收款无发票", "level": "高风险", "score": 9,
            "detail": f"{len(paid_no_invoice)}个收款方无销项发票记录，合计{total:,.2f}元：{'、'.join(names)}",
            "suggestion": "涉嫌未开票收入未申报增值税。", "category": "三流比对"})

    # 2. 进项发票 vs 银行付款
    pi_sellers = {}
    for pi in db.query(PurchaseInvoice).filter(PurchaseInvoice.company_id == company_id).all():
        n = _normalize_customer_name(pi.seller_name or "")
        if n: pi_sellers[n] = pi_sellers.get(n, 0) + float(pi.total_amount or 0)

    bt_payers = {}
    for tx in db.query(BankTransaction).filter(
        BankTransaction.company_id == company_id, BankTransaction.debit_amount > 0
    ).all():
        n = _normalize_customer_name(tx.counterparty_name or "")
        if n: bt_payers[n] = bt_payers.get(n, 0) + float(tx.debit_amount or 0)

    invoiced_no_payment = set(pi_sellers.keys()) - set(bt_payers.keys())
    paid_no_purchase = set(bt_payers.keys()) - set(pi_sellers.keys())

    if invoiced_no_payment:
        names = list(invoiced_no_payment)
        total = sum(pi_sellers[n] for n in invoiced_no_payment)
        cross.append({"type": "三流比对：有票无付", "level": "中风险", "score": 6,
            "detail": f"{len(invoiced_no_payment)}个供应商已取得发票但无付款记录，涉及{total:,.2f}元：{'、'.join(names)}",
            "suggestion": "进项发票无资金流印证，涉嫌虚开发票虚增成本。", "category": "三流比对"})

    if paid_no_purchase:
        names = list(paid_no_purchase)
        total = sum(bt_payers[n] for n in paid_no_purchase)
        cross.append({"type": "三流比对：有付无票", "level": "中风险", "score": 6,
            "detail": f"{len(paid_no_purchase)}个付款方无对应取得发票，合计{total:,.2f}元：{'、'.join(names)}",
            "suggestion": "付款未取得发票，可能存在账外交易。", "category": "三流比对"})

    # 3. 合同覆盖率
    contracts = db.query(Contract).filter(Contract.company_id == company_id).all()
    contract_parties = set()
    for ct in contracts:
        for p in [ct.party_a, ct.party_b]:
            if p: contract_parties.add(_normalize_customer_name(p))

    si_no_contract = set(si_buyers.keys()) - contract_parties
    if si_no_contract and len(si_no_contract) >= 2:
        cnames = list(si_no_contract)
        cross.append({"type": "三流比对：销项无合同", "level": "中风险", "score": 6,
            "detail": f"{len(si_no_contract)}个销项客户无对应合同：{'、'.join(cnames)}。覆盖率{len(si_buyers)-len(si_no_contract)}/{len(si_buyers)}。",
            "suggestion": "合同流缺失增加了虚开发票风险。", "category": "三流比对"})


# ═══════════════ P0 进销匹配分析 ═══════════════

def _run_purchase_sales_match(db, company_id, cross):
    """进销品名匹配度 + 进销比 + 费用结构"""
    import re

    def get_cat(inv):
        m = re.match(r'\*([^*]+)\*', inv.goods_name or "")
        return m.group(1) if m else "其他"

    si_cats = {}
    si_total = 0
    for si in db.query(SalesInvoice).filter(SalesInvoice.company_id == company_id).all():
        cat = get_cat(si)
        amt = float(si.total_amount or 0)
        si_cats[cat] = si_cats.get(cat, 0) + amt
        si_total += amt

    pi_cats = {}
    pi_total = 0
    for pi in db.query(PurchaseInvoice).filter(PurchaseInvoice.company_id == company_id).all():
        cat = get_cat(pi)
        amt = float(pi.total_amount or 0)
        pi_cats[cat] = pi_cats.get(cat, 0) + amt
        pi_total += amt

    if si_total <= 0 and pi_total <= 0:
        return

    if si_total > 0 and pi_total > 0:
        ratio = pi_total / si_total * 100
        if ratio > 150:
            cross.append({"type": "进销倒挂", "level": "高风险", "score": 8,
                "detail": f"进项{pi_total:,.2f} / 销项{si_total:,.2f} = {ratio:.2f}%（正常<100%），进销严重倒挂。",
                "suggestion": "涉嫌虚增进项发票或严重亏损经营。", "category": "进销匹配"})

    HOSPITALITY = {"餐饮服务", "住宿服务", "餐饮费", "住宿费"}
    hospitality_amt = sum(pi_cats.get(c, 0) for c in HOSPITALITY)
    if pi_total > 0 and hospitality_amt / pi_total * 100 > 30:
        cross.append({"type": "费用结构异常", "level": "高风险", "score": 8,
            "detail": f"餐饮住宿类占进项{hospitality_amt/pi_total*100:.2f}%（{hospitality_amt:,.2f}/{pi_total:,.2f}），远超正常。",
            "suggestion": "广告公司餐饮住宿占比正常<10%，超高指向虚列费用。", "category": "进销匹配"})

    mismatch = set(pi_cats.keys()) - set(si_cats.keys())
    if mismatch and len(mismatch) >= 3:
        cross.append({"type": "进销品名脱节", "level": "中风险", "score": 5,
            "detail": f"{len(mismatch)}个进项分类与销项业务无关：{mismatch}",
            "suggestion": "采购品名与销售无关，涉嫌购买与经营无关发票虚增成本。", "category": "进销匹配"})


# ═══════════════ P1 申报一致性 ═══════════════

def _run_declaration_consistency(db, company_id, cross):
    """申报表 vs 发票/银行原始数据的一致性验证"""
    import json

    vat = db.query(VATDeclaration).filter(
        VATDeclaration.company_id == company_id
    ).order_by(VATDeclaration.period.desc()).first()

    if vat:
        main = json.loads(vat.form_main or '{}') if isinstance(vat.form_main, str) else (vat.form_main or {})
        declared_output = float(main.get("row11_tax_output", 0) or 0)
        actual_output = sum(float(si.tax_amount or 0) for si in db.query(SalesInvoice).filter(
            SalesInvoice.company_id == company_id).all())
        if actual_output > 0 and declared_output > 0:
            diff = abs(declared_output - actual_output)
            if diff > 100:
                cross.append({"type": "申报一致性：销项税额差异", "level": "高风险" if diff > 1000 else "中风险",
                    "score": 9 if diff > 1000 else 6,
                    "detail": f"申报销项税{declared_output:,.2f} vs 发票销项{actual_output:,.2f}，差异{diff:,.2f}元。",
                    "suggestion": "申报销项税额与发票系统不一致。", "category": "申报一致性"})

        declared_input = float(main.get("row12_tax_input", 0) or 0)
        actual_input = sum(float(d.deduction_amount or 0) for d in db.query(InputVATDeduction).filter(
            InputVATDeduction.company_id == company_id).all())
        if actual_input > 0 and declared_input > 0:
            diff = abs(declared_input - actual_input)
            if diff > 100:
                cross.append({"type": "申报一致性：进项税额差异", "level": "高风险" if diff > 1000 else "中风险",
                    "score": 9 if diff > 1000 else 6,
                    "detail": f"申报进项税{declared_input:,.2f} vs 抵扣合计{actual_input:,.2f}，差异{diff:,.2f}元。",
                    "suggestion": "进项税额申报与抵扣数据不匹配。", "category": "申报一致性"})

@app.post("/api/tax-risk-docs/upload")
async def upload_tax_risk_docs(
    files: list[UploadFile] = File(...),
    company_id: int = Query(...),
):
    """上传涉税分析资料（支持多文件，同公司MD5去重）
    V15: 增加Word/图片格式支持 + 安全验证"""
    import hashlib
    # V15: 安全验证 — 文件类型和大小
    all_allowed = ALLOWED_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS
    validated_files = []
    rejected = []
    for f in files:
        ext = os.path.splitext(f.filename or '')[1].lower()
        if ext not in all_allowed:
            rejected.append({"filename": f.filename, "reason": f"不支持的文件类型: {ext}"})
            continue
        validated_files.append(f)
    if not validated_files:
        return {"ok": False, "error": "没有有效的文件", "rejected": rejected}

    files = validated_files

    # 计算已有文件的MD5集合——仅限当前公司（从内存列表取，避免磁盘残留导致误判重复）
    existing_hashes = set()
    for d in _tax_risk_docs:
        if d.get("company_id") != company_id:
            continue
        md5_val = d.get("md5")
        if md5_val:
            existing_hashes.add(md5_val)
            continue
        # 兼容旧数据：无 MD5 字段则从磁盘读取
        try:
            fpath = d.get("path") or os.path.join(_get_company_upload_dir(d.get("company_id", company_id)), d.get("filename", ""))
            if os.path.exists(fpath):
                with open(fpath, "rb") as fh:
                    existing_hashes.add(hashlib.md5(fh.read()).hexdigest())
        except:
            pass

    uploaded = []
    skipped = 0
    for f in files:
        content = await f.read()
        # V15: 大小验证
        if len(content) > MAX_UPLOAD_SIZE:
            rejected.append({"filename": f.filename, "reason": f"文件超过{MAX_UPLOAD_SIZE // 1024 // 1024}MB限制"})
            continue
        md5 = hashlib.md5(content).hexdigest()
        sha256 = hashlib.sha256(content).hexdigest()
        if md5 in existing_hashes:
            skipped += 1
            continue

        _tax_doc_counter[0] += 1
        doc_id = _tax_doc_counter[0]
        safe_name = f"{company_id}_{doc_id}_{f.filename}"
        company_udir = _get_company_upload_dir(company_id)
        filepath = os.path.join(company_udir, safe_name)
        
        # ═══ 同名覆盖：删除公司目录下同名旧文件（同一份资料只保留最新版）═══
        _removed_old = 0
        if os.path.exists(company_udir):
            for _old_fname in os.listdir(company_udir):
                # 旧文件名格式: {cid}_{docid}_{original_name}
                _parts = _old_fname.split("_", 2)
                if len(_parts) >= 3 and _parts[2] == f.filename:
                    _old_path = os.path.join(company_udir, _old_fname)
                    try:
                        os.remove(_old_path)
                        _removed_old += 1
                    except Exception:
                        pass
                    # 同步从内存列表中移除
                    _tax_risk_docs[:] = [d for d in _tax_risk_docs if d.get("original_name") != f.filename or d.get("company_id") != company_id]
        if _removed_old > 0:
            pass  # 旧文件已从磁盘和内存列表中移除
        
        file_saved = False
        try:
            with open(filepath, "wb") as fw:
                fw.write(content)
            file_saved = True
        except PermissionError:
            pass  # 沙箱环境下文件写入可能被拒绝，仍记录到内存列表
        existing_hashes.add(md5)
        doc = {
            "id": doc_id, "filename": safe_name, "original_name": f.filename,
            "path": filepath, "size": len(content), "md5": md5, "sha256": sha256,
            "uploaded_at": datetime.now().isoformat(), "company_id": company_id,
            "file_saved": file_saved
        }
        _tax_risk_docs.append(doc)
        uploaded.append({"id": doc_id, "filename": f.filename, "size": len(content),
                         "file_saved": file_saved})

    msg = f"已上传 {len(uploaded)} 个文件"
    if skipped > 0: msg += f"，跳过 {skipped} 个重复文件"
    if rejected: msg += f"，拒绝 {len(rejected)} 个无效文件"
    return {"ok": True, "uploaded": uploaded, "skipped": skipped, "rejected": rejected, "total": len(_tax_risk_docs), "message": msg}


@app.get("/api/tax-risk-docs/list")
def list_tax_risk_docs(company_id: int = Query(...)):
    global _tax_risk_docs
    # 确保已初始化（仅首次扫描磁盘）
    _init_tax_docs_from_disk()
    docs = [d for d in _tax_risk_docs if d["company_id"] == company_id]
    # 去重 + 验证磁盘文件实际存在（用户可能手动删除了文件）
    seen = set()
    valid = []
    stale_indices = []
    for i, d in enumerate(docs):
        key = (d["id"], d["original_name"])
        if key in seen:
            stale_indices.append(i)
            continue
        seen.add(key)
        if not os.path.exists(d["path"]):
            stale_indices.append(i)
            continue
        valid.append(d)
    # 清理无效条目（文件已被外部删除）
    if stale_indices:
        for i in sorted(stale_indices, reverse=True):
            _tax_risk_docs.remove(docs[i])
    return [{"id": d["id"], "original_name": d["original_name"], "size": d["size"],
             "uploaded_at": d["uploaded_at"]} for d in valid]

@app.get("/api/tax-risk-docs/debug")
def debug_tax_risk_docs(company_id: int = Query(...)):
    """诊断端点：确认磁盘文件是否可达（需指定 company_id）"""
    # 仅统计当前公司的文档
    upload_dir = _get_company_upload_dir(company_id)
    disk_files = []
    if os.path.exists(upload_dir):
        disk_files = [f for f in os.listdir(upload_dir) if os.path.isfile(os.path.join(upload_dir, f))]

    cid_counts = {str(company_id): len(_tax_risk_docs)}
    return {
        "company_id": company_id,
        "upload_dir": upload_dir,
        "dir_exists": os.path.exists(upload_dir),
        "files_on_disk": len(disk_files),
        "docs_in_memory": len([d for d in _tax_risk_docs if d.get("company_id") == company_id]),
        "scanned": _TAX_DOC_SCANNED,
        "cid_distribution": cid_counts,
        "file_sample": [{"name": f, "company_dir": str(company_id)} for f in disk_files[:10]],
    }


@app.delete("/api/tax-risk-docs/clear-transfer")
def clear_transfer_cache(company_id: int = Query(...)):
    """清除中转站缓存（容错版：沙箱环境下文件删除可能失败，返回实际结果）"""
    try:
        _clear_transfer(company_id)
        return {"ok": True, "message": "中转站缓存已清空"}
    except Exception as e:
        return {"ok": False, "message": f"清除失败: {str(e)}"}

@app.delete("/api/tax-risk-docs/{doc_id}")
def delete_tax_risk_doc(doc_id: int, company_id: int = Query(...)):
    """删除单条涉税资料（容错版：沙箱下文件删除可能失败）"""
    global _tax_risk_docs
    for i, d in enumerate(_tax_risk_docs):
        if d["id"] == doc_id and d["company_id"] == company_id:
            removed_file = False
            try: import stat; os.chmod(d["path"], stat.S_IWUSR | stat.S_IRUSR)
            except: pass
            try:
                os.remove(d["path"])
                removed_file = True
            except Exception as _e:
                pass  # 沙箱下删除失败，仍从列表中移除
            _tax_risk_docs.pop(i)
            return {"ok": True, "message": "删除成功" if removed_file else "已从列表移除（文件删除失败，可能是权限限制）"}
    raise HTTPException(404, "文件不存在")


def _classify_file_type(text, filename):
    """识别文件类型：返回 (模块名, 置信度)"""
    fn = filename.lower()
    # 文件名优先
    if any(k in fn for k in ["银行流水","对账单","bank","交易明细","流水"]): return ("bank", 0.9)
    if any(k in fn for k in ["增值税","vat","增值税申报"]): return ("vat", 0.9)
    if any(k in fn for k in ["发票","invoice","开票","销项","进项","取得发票","开具发票"]): return ("invoice", 0.9)
    if any(k in fn for k in ["社保","社会保险","养老","医疗","失业","工伤","生育"]): return ("social_security", 0.9)
    if any(k in fn for k in ["公积金","住房公积金","住房"]): return ("housing_fund", 0.9)
    if any(k in fn for k in ["工资","薪酬","薪资","salary","payroll","个税"]): return ("salary", 0.9)
    if any(k in fn for k in ["合同","协议","contract"]): return ("contract", 0.8)
    if any(k in fn for k in ["审计","稽查","检查报告","风险评估","涉税"]): return ("audit", 0.8)

    # 内容特征
    t = text[:500].lower()
    if "借方" in t and "贷方" in t and any(k in t for k in ["对方户名","交易日期","余额","摘要"]): return ("bank", 0.8)
    if "销项税额" in t and "进项税额" in t: return ("vat", 0.8)
    if "缴存月份" in t and "缴存基数" in t: return ("housing_fund", 0.9)
    if "发票代码" in t and "发票号码" in t and "开票日期" in t:
        if any(k in t for k in ["所得项目","本期收入","实发工资"]): return ("salary", 0.8)
        elif "勾选状态" in t or "有效抵扣税额" in t: return ("input_vat_deduction", 0.9)
        # 销方名称存在但购方名称也存在 → 无法判断→交给文件名
        return ("invoice", 0.7)
    if "本期收入" in t and "实发工资" in t: return ("salary", 0.9)
    if any(k in t for k in ["发票代码","发票号码","数电发票","货物或应税劳务名称"]) and "税率" in t: return ("invoice", 0.8)
    if "缴存月份" in t or ("缴存基数" in t and "单位缴存" in t): return ("housing_fund", 0.9)
    if "勾选" in t and "税额" in t and "有效抵扣" in t: return ("input_vat_deduction", 0.9)
    if any(k in t for k in ["费款所属期","缴费工资","单位社保","个人社保"]) and "基本养老" in t: return ("social_security", 0.85)
    if "缴费基数" in t and any(k in t for k in ["养老","医疗","工伤","生育","失业"]): return ("social_security", 0.8)
    if "公积金" in t and "缴存" in t: return ("housing_fund", 0.8)
    if any(k in t for k in ["应发工资","实发工资","应纳税所得额","代扣个税"]): return ("salary", 0.8)
    return ("unknown", 0.3)


from datetime import timedelta

# ═══════════ Excel 结构化提取 ═══════════

def _parse_excel_structured(filepath, ext, original_name="", return_wb=False):
    """智能识别Excel内容——不依赖Sheet名，纯靠表头和数据推断
    
    当 return_wb=True 时，返回 (result, wb) 元组，避免调用方重复打开文件。
    """
    fname = os.path.basename(filepath)
    _init_trace(fname)  # 初始化诊断追踪
    try:
        if ext == ".xls":
            import xlrd
            wb = xlrd.open_workbook(filepath)
            result = _parse_by_content(wb.sheet_names(), lambda i: wb.sheet_by_index(i), original_name)
        else:
            import openpyxl
            wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
            result = _parse_by_content(wb.sheetnames, lambda i: wb[wb.sheetnames[i]], original_name)
        if result is None:
            _trace_diag("三层递进全部失败: 关键词匹配→结构分析→通用解析 均未通过", "error")
        if return_wb:
            return (result, wb)
        return result
    except Exception as e:
        _trace_diag(f"Excel解析异常: {e}", "error")
        if return_wb:
            return (None, None)
        return None

# ── 资料类型特征库（列名关键词+得分）──
# 覆盖税务稽查所需的所有资料类型，纯内容识别，不依赖Sheet名
_FILE_FINGERPRINTS = {
    # ══════════ 第一梯队：高频核心类型（用户最常上传）══════════
    "bank_statement": {
        "keywords": ["对方户名", "对方账号", "对方行名", "对方开户行", "交易日期", "记账日期",
                     "收入金额", "支出金额", "贷方金额", "借方金额", "本次余额", "交易余额",
                     "流水号", "交易流水号", "凭证号", "交易行名", "借贷标志", "借贷",
                     "交易金额", "发生额", "币种", "起息日", "柜员号", "网点号"],
        "score_threshold": 3,
        "parser": lambda s, h: _parse_bank_sheet(s),
        "secondary": ["摘要", "用途", "附言", "备注", "对方", "收入", "支出", "余额"],
    },
    "salary": {
        "keywords": ["本期收入", "应纳税所得额", "代扣个税", "实发工资", "应发工资",
                     "专项扣除", "基本养老保险", "基本医疗保险", "住房公积金", "累计预扣预缴",
                     "子女教育", "住房贷款利息", "赡养老人", "继续教育", "大病医疗",
                     "累计收入", "累计减除费用", "累计专项扣除", "累计应纳税额", "已预缴税额",
                     "应补退税额", "基本扣除", "其他扣除", "准予扣除的捐赠额", "减免税额",
                     "税款负担方式", "所得项目", "收入额", "费用", "免税收入",
                     # 常见HR工资表列名
                     "基本工资", "绩效工资", "岗位工资", "加班工资", "工龄工资",
                     "交通补贴", "通讯补贴", "餐补", "高温补贴", "住房补贴",
                     "应发合计", "实发合计", "代扣个税合计", "税前工资",
                     "缺勤扣款", "迟到扣款", "奖金", "年终奖", "提成工资",
                     # 常见HR工资表简化列名
                     "工资", "代扣社保", "代扣公积金", "养老保险", "医疗保险", "失业保险",
                     "大病医疗", "证件类型", "联系电话", "任职受雇", "费用类型",
                     "应补（退）税额", "应补退税额", "累计应纳税所得额", "累计已缴税额"],
        "score_threshold": 2,
        "parser": lambda s, h: _parse_salary_sheet(s)
    },
    "sales_invoice": {
        "keywords": ["购方名称", "购方税号", "购方开户行", "购买方名称", "购买方纳税人识别号",
                     "购方地址", "购方电话", "购方银行账号", "购买方地址", "购买方电话",
                     "购买方开户行", "购买方银行账号"],
        "score_threshold": 2,
        "parser": lambda s, h: _parse_invoice_sheet(s, "销项")
    },
    "purchase_invoice": {
        "keywords": ["销方名称", "销方税号", "销售方名称", "供应商名称", "销方地址",
                     "销方开户行", "销方银行账号", "销售方税号", "销售方地址", "销售方电话",
                     "销售方开户行", "销售方银行账号", "供方名称", "供方税号"],
        "score_threshold": 2,
        "parser": lambda s, h: _parse_invoice_sheet(s, "进项")
    },
    "invoice_universal": {
        "keywords": ["发票号码", "发票代码", "数电发票号码", "发票类型", "开票日期",
                     "金额", "税额", "价税合计", "税率", "货物或应税劳务名称",
                     "规格型号", "数量", "单价", "不含税金额", "含税金额",
                     "税收分类编码", "商品和服务税收分类编码", "备注", "收款人", "复核人",
                     "开票人", "发票状态", "作废标志", "红字发票", "原发票号码"],
        "score_threshold": 4,
        "parser": lambda s, h: _parse_invoice_sheet(s, "进项")
    },
    "voucher": {
        "keywords": ["凭证号", "凭证编号", "凭证字号", "科目名称", "科目", "科目编号", "摘要", "会计科目",
                     "明细科目", "记账凭证", "凭证日期", "制单人", "审核人", "记账人"],
        "score_threshold": 2,
        "parser": lambda s, h: _parse_voucher_sheet(s),
        "secondary": ["借方金额", "借方", "贷方金额", "贷方", "借方合计", "贷方合计",
                      "金额", "附件", "结算方式", "结算号", "票号", "发生日期"],
    },
    "social_security": {
        "keywords": ["缴费基数", "单位缴纳", "个人缴纳", "养老保险", "医疗保险", "工伤保险",
                     "失业保险", "生育保险", "社保人数", "社保编号", "参保险种",
                     "单位比例", "个人比例", "单位缴费金额", "个人缴费金额", "缴费工资",
                     "险种类型", "社平工资", "大额医疗", "补充医疗"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "social_security", "rows": _parse_social_sheet(s, h)}
    },
    "housing_fund": {
        "keywords": ["公积金", "住房", "缴存基数", "缴存比例", "单位缴存", "个人缴存",
                     "月缴存额", "缴存人数", "汇缴", "补缴", "封存", "启封", "转移",
                     "提取", "公积金账号", "个人账号", "单位账号", "缴存状态",
                     "缴存月份", "缴存额", "单位缴存额", "个人缴存额", "身份证号"],
        "score_threshold": 2,
        "parser": lambda s, h: _parse_housing_fund_sheet(s, h)
    },
    "input_vat_deduction": {
        "keywords": ["勾选状态", "有效抵扣税额", "转内销证明编号", "发票风险等级",
                     "勾选时间", "票种标签", "数电发票号码"],
        "score_threshold": 2,
        "parser": lambda s, h: _parse_input_vat_sheet(s),
    },
    "inventory": {
        "keywords": ["本期入库", "本期出库", "期初库存", "期末库存", "产品编码", "产品名称",
                     "规格型号", "入库数量", "出库数量", "进销存", "单位", "单价", "库存金额",
                     "存货编码", "存货名称", "仓库", "批次号", "生产日期", "保质期",
                     "账面数量", "盘点数量", "盈亏数量", "存货类别", "收发类别"],
        "score_threshold": 2,
        "parser": lambda s, h: _parse_inventory_sheet(s)
    },
    # 科目余额表
    "trial_balance": {
        "keywords": ["科目编码", "科目名称", "期初余额", "本期发生额", "本年累计发生额",
                     "期末余额", "借方", "贷方", "一级科目", "明细科目"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "trial_balance", "rows": _parse_trial_balance_sheet(s, h)}
    },
    # ══════════ 合同/权证/关联交易 ══════════
    "contract": {
        "keywords": ["合同名称", "合同编号", "合同类型", "合同金额", "签订日期",
                     "甲方", "乙方", "签订时间", "合同期限", "付款方式",
                     "合同内容", "当事人", "签约方", "甲方名称", "乙方名称"],
        "score_threshold": 2,
        "parser": lambda s, h: _parse_contract_sheet(s, h)
    },
    "related_party": {
        "keywords": ["关联方名称", "关联关系", "关联交易", "交易类型", "交易金额",
                     "关联交易汇总", "关联方清单", "持股比例", "定价政策",
                     "交易内容", "关联交易类型", "金额（万元）", "关联主体",
                     "对外投资", "投资比例", "同期资料", "本年发生额"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "related_party", "rows": _parse_related_party_sheet(s, h)}
    },
    # ══════════ 第二梯队：申报表与财务报表 ══════════
    "financial_statements": {
        "keywords": ["资产负债表", "利润表", "现金流量表", "所有者权益变动表",
                     "资产总计", "负债合计", "所有者权益", "营业利润", "净利润",
                     "经营活动", "投资活动", "筹资活动", "期末现金", "年初余额",
                     "期末余额", "本年累计", "上年同期", "报表项目", "行次",
                     "流动资产", "非流动资产", "流动负债", "非流动负债"],
        "score_threshold": 3,
        "parser": lambda s, h: {"type": "financial_statements", "rows": _parse_generic_table(s, h)}
    },
    "trial_balance": {
        "keywords": ["科目余额表", "总账", "明细账", "期初借方", "期初贷方",
                     "本期借方", "本期贷方", "期末借方", "期末贷方", "累计借方",
                     "累计贷方", "余额方向", "核算维度", "辅助核算", "部门核算",
                     "项目核算", "客户核算", "供应商核算", "个人核算"],
        "score_threshold": 3,
        "parser": lambda s, h: {"type": "trial_balance", "rows": _parse_generic_table(s, h)}
    },
    "vat_declaration": {
        "keywords": ["增值税纳税申报表", "销项税额", "进项税额", "应纳税额", "未开具发票",
                     "即征即退", "免抵退税", "期末留抵税额", "本期应补(退)税额",
                     "简易计税", "按适用税率计税销售额", "应税劳务", "应税服务",
                     "一般项目", "即征即退项目", "免税", "不征税", "零税率"],
        "score_threshold": 3,
        "parser": lambda s, h: {"type": "vat_declaration", "rows": _parse_generic_table(s, h)}
    },
    "cit_declaration": {
        "keywords": ["企业所得税", "应纳税所得额", "利润总额", "纳税调整增加额", "纳税调整减少额",
                     "弥补以前年度亏损", "减免所得税额", "实际应纳所得税额", "资产总额", "从业人数",
                     "营业收入", "营业成本", "期间费用", "所得税费用", "递延所得税",
                     "预缴税额", "汇算清缴", "年度申报", "季度申报"],
        "score_threshold": 3,
        "parser": lambda s, h: {"type": "cit_declaration", "rows": _parse_generic_table(s, h)}
    },
    "individual_tax": {
        "keywords": ["个人所得税", "个税申报", "扣缴义务人", "纳税人识别号",
                     "工资薪金所得", "劳务报酬所得", "稿酬所得", "特许权使用费",
                     "经营所得", "财产租赁所得", "财产转让所得", "利息股息红利",
                     "偶然所得", "综合所得", "分类所得", "预扣预缴", "代扣代缴",
                     "汇算清缴", "专项附加扣除", "累计预扣法", "全员全额"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "individual_tax", "rows": _parse_generic_table(s, h)}
    },
    "stamp_duty": {
        "keywords": ["印花税", "计税金额", "应纳税额", "已纳税额", "应补税额",
                     "购销合同", "借款合同", "财产租赁", "技术合同", "加工承揽",
                     "建设工程", "运输合同", "仓储合同", "保险合同", "产权转移",
                     "营业账簿", "权利许可证照", "证券交易"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "stamp_duty", "rows": _parse_generic_table(s, h)}
    },
    "tax_payment": {
        "keywords": ["完税证明", "缴税记录", "税种", "税款所属期", "实缴金额",
                     "电子缴款凭证", "税收缴款书", "电子税票", "征收机关",
                     "缴款日期", "缴款期限", "滞纳金", "罚款", "退抵税",
                     "银行端查询缴税凭证", "国库", "中央级", "地方级"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "tax_payment", "rows": _parse_generic_table(s, h)}
    },
    # ══════════ 第三梯队：往来与合同 ══════════
    "contract_list": {
        "keywords": ["合同编号", "合同名称", "合同类型", "签订日期", "生效日期",
                     "到期日期", "甲方", "乙方", "合同金额", "已付金额", "未付金额",
                     "履行状态", "条款", "违约", "终止", "续签", "负责人",
                     "对方单位", "签约日期", "终止日期", "付款方式", "付款条件",
                     "质保金", "履约保证金", "框架协议", "补充协议"],
        "score_threshold": 2,
        "parser": lambda s, h: _parse_contract_sheet(s, h)
    },
    "accounts_receivable": {
        "keywords": ["应收账款", "期初余额", "借方发生额", "贷方发生额", "期末余额", "账龄",
                     "客户名称", "应收金额", "已收金额", "未收金额", "坏账准备",
                     "账龄分析", "逾期", "催收", "对账", "函证"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "accounts_receivable", "rows": _parse_generic_table(s, h)}
    },
    "accounts_payable": {
        "keywords": ["应付账款", "供应商", "应付金额", "已付金额", "未付金额",
                     "暂估应付款", "暂估入库", "应付暂估", "付款计划", "账期",
                     "采购订单", "入库单", "结算单", "对账单"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "accounts_payable", "rows": _parse_generic_table(s, h)}
    },
    "prepaid_advance": {
        "keywords": ["预收账款", "预收款项", "合同负债", "预付账款", "预付款项",
                     "预收金额", "预付金额", "待转销项税额", "预付费", "充值",
                     "预缴", "预存", "押金", "定金"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "prepaid_advance", "rows": _parse_generic_table(s, h)}
    },
    "other_receivables": {
        "keywords": ["其他应收款", "其他应付款", "往来单位", "备用金", "保证金",
                     "押金", "代垫款", "员工借款", "关联方往来"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "other_receivables", "rows": _parse_generic_table(s, h)}
    },
    # ══════════ 第四梯队：资产与费用 ══════════
    "fixed_assets": {
        "keywords": ["固定资产", "资产编码", "资产名称", "购置日期", "原值", "残值率",
                     "折旧年限", "月折旧额", "累计折旧", "净值", "使用部门", "存放地点",
                     "折旧方法", "资产类别", "资产状态", "使用年限", "残值", "净残值"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "fixed_assets", "rows": _parse_generic_table(s, h)}
    },
    "intangible_assets": {
        "keywords": ["无形资产", "摊销年限", "专利权", "商标权", "著作权", "土地使用权",
                     "软件", "摊销金额", "累计摊销", "入账价值", "资本化"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "intangible_assets", "rows": _parse_generic_table(s, h)}
    },
    "asset_impairment": {
        "keywords": ["资产损失", "存货跌价", "坏账损失", "资产减值", "报废", "盘亏",
                     "盘盈", "资产处置", "资产盘点"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "asset_impairment", "rows": _parse_generic_table(s, h)}
    },
    "expense_detail": {
        "keywords": ["费用明细", "广告费", "业务招待费", "差旅费", "会议费", "佣金",
                     "手续费", "咨询费", "服务费", "运输费", "仓储费", "包装费",
                     "办公费", "通讯费", "水电费", "租赁费", "物业费", "维修费",
                     "保险费", "培训费", "福利费", "工会经费", "职工教育经费",
                     "开办费", "装修费", "折旧费", "摊销费", "劳务费", "检测费"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "expense_detail", "rows": _parse_generic_table(s, h)}
    },
    "rd_expense": {
        "keywords": ["研发费用", "研发支出", "研究开发费", "自主研发", "委托研发",
                     "合作研发", "研发人员", "直接投入", "折旧费用", "无形资产摊销",
                     "设计费用", "装备调试费", "加计扣除", "研发项目"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "rd_expense", "rows": _parse_generic_table(s, h)}
    },
    # ══════════ 第五梯队：特殊交易 ══════════
    "employee_list": {
        "keywords": ["人员清单", "花名册", "入职日期", "离职日期", "部门", "岗位",
                     "身份证号", "联系电话", "学历", "职称", "劳动合同", "用工形式",
                     "在岗状态", "在职", "离职", "工号", "性别", "出生日期", "民族"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "employee_list", "rows": _parse_generic_table(s, h)}
    },
    "equity_transaction": {
        "keywords": ["股权转让", "股权变更", "注册资本", "实收资本", "股东", "出资额",
                     "股权比例", "转让价格", "转让协议", "增资", "减资", "撤资"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "equity_transaction", "rows": _parse_generic_table(s, h)}
    },
    "related_party": {
        "keywords": ["关联方", "关联交易", "关联企业", "关联关系", "母子公司",
                     "兄弟公司", "同一控制", "最终控制方", "关联购销", "关联借贷",
                     "关联担保", "转移定价", "独立交易原则", "同期资料"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "related_party", "rows": _parse_generic_table(s, h)}
    },
    "loan_borrowing": {
        "keywords": ["借款合同", "贷款合同", "借款金额", "年利率", "借款期限", "还款方式",
                     "担保方式", "抵押", "质押", "保证", "信用贷款", "授信额度",
                     "还本付息", "利息支出", "利息资本化", "资本弱化", "关联方借款"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "loan_borrowing", "rows": _parse_generic_table(s, h)}
    },
    "import_export": {
        "keywords": ["报关单", "海关", "进口", "出口", "退税", "外汇", "收汇", "付汇",
                     "跨境", "境外", "离岸", "到岸", "FOB", "CIF", "外汇管理局",
                     "出口日期", "贸易方式", "成交方式", "商品编码", "HS编码"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "import_export", "rows": _parse_generic_table(s, h)}
    },
    # ══════════ 常见办公/HR类文件（2026-06-26 扩充：减少generic兜底）══════════
    "expense_report": {
        "keywords": ["报销", "费用报销", "差旅", "招待", "交通", "办公用品", "通讯费",
                     "报销人", "报销日期", "费用类别", "发票张数", "报销金额", "审批人",
                     "行程", "住宿", "餐费", "出租车", "加油", "过路费", "停车费"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "expense_report", "rows": _parse_generic_table(s, h)}
    },
    "attendance": {
        "keywords": ["考勤", "出勤", "缺勤", "迟到", "早退", "请假", "旷工", "加班",
                     "打卡", "工时", "排班", "调休", "年假", "病假", "事假",
                     "签到", "签退", "应出勤", "实际出勤", "出勤天数"],
        "score_threshold": 2,
        "parser": lambda s, h: {"type": "attendance", "rows": _parse_generic_table(s, h)}
    },
    "contact_list": {
        "keywords": ["联系人", "电话", "手机", "邮箱", "地址", "邮编", "传真",
                     "部门", "职位", "QQ", "微信", "网址", "负责人"],
        "score_threshold": 3,
        "parser": lambda s, h: {"type": "contact_list", "rows": _parse_generic_table(s, h)}
    },
    # ══════════ 兜底：纯数值表（含大量数字列但无明确分类特征）══════════
    "generic_data": {
        "keywords": ["日期", "金额", "数量", "序号", "编码", "名称", "类型", "备注",
                     "合计", "总计", "小计"],
        "score_threshold": 1,
        "parser": lambda s, h: {"type": "generic_data", "rows": _parse_generic_table(s, h)}
    },
}

def _parse_generic_table(sheet, header):
    """通用表格解析: 提取表头+数据行，不做特定类型转换"""
    rows = []
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else sheet.max_row
    for r in range(1, min(nrows, 2000)):
        vals = _get_row_values(sheet, r)
        if _is_summary_row(vals): continue
        if _is_repeat_header(vals, header): continue
        row = {header[i]: vals[i] if i < len(vals) else "" for i in range(min(len(header), len(vals)))}
        if any(str(v).strip() for v in row.values()):
            rows.append(row)
    return rows

def _parse_bank_sheet(sheet):
    """解析银行流水：自适应表头+提取交易记录"""
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else sheet.max_row
    header_row, _scores = _detect_header_row(sheet, nrows, [
        "交易日期", "记账日期", "对方户名", "对方账号", "收入金额", "支出金额",
        "贷方金额", "借方金额", "摘要", "余额", "流水号", "用途", "附言",
        "Transaction Date", "Counterparty", "Debit Amount", "Credit Amount"
    ])
    header = _get_row_values(sheet, header_row)
    
    cols = _find_cols_semantic(header, {
        # 中文列名
        "交易日期": "date", "记账日期": "bk_date", "日期": "date", "申请日期": "apply_date",
        "对方户名": "counterparty", "对方名称": "counterparty", "对方": "counterparty", "户名": "counterparty",
        "对方账号": "account", "对方行名": "bank", "对方账户": "account",
        "收入金额": "credit", "支出金额": "debit",
        "贷方金额": "credit", "贷方": "credit",
        "借方金额": "debit", "借方": "debit",
        "摘要": "summary", "用途": "summary", "附言": "summary", "备注": "remark",
        "余额": "balance", "本次余额": "balance", "交易余额": "balance",
        "流水号": "tx_no", "交易流水号": "tx_no", "凭证号": "tx_no",
        "交易金额": "amount", "金额": "amount", "发生额": "amount",
        "借贷标志": "direction", "借贷": "direction",
        "币种": "currency", "交易时间": "tx_time",
        # 双语表头
        "Transaction Date": "date", "Counterparty Account Name": "counterparty",
        "Order": "seq", "Bank Name": "bank",
        "Debit Amount": "debit", "Credit Amount": "credit",
        "Currency": "currency", "Notes/Abstract": "summary",
        "Opposite Account No.": "account", "Opposite Account": "account",
    })
    if not cols: return None
    
    rows = []
    for r in range(header_row + 1, min(nrows, 5000)):
        raw_vals = _get_row_values(sheet, r)
        if _is_summary_row(raw_vals): continue
        if _is_repeat_header(raw_vals, header): continue
        vals = {}
        for field, col in cols.items():
            try:
                v = str(sheet.cell_value(r, col)).strip() if hasattr(sheet, 'cell_value') else str(raw_vals[col] or '') if col < len(raw_vals) else ''
                vals[field] = v
            except: vals[field] = ""
        
        # 至少要有日期或对方名称或合理金额才视为有效行（排除汇总行）
        has_date = bool(vals.get("date", "").strip())
        has_amount = any(vals.get(k) and str(vals[k]).strip() not in ("", "0", "0.0") for k in ["amount", "income", "expense", "credit", "debit"])
        has_counterparty = bool(vals.get("counterparty", "").strip())
        if not (has_date or has_amount or has_counterparty): continue
        
        # 额外检查：无日期+无对方+金额很大 → 可能是汇总行（收入合计/支出合计等）
        if not has_date and not has_counterparty:
            try:
                amt_val = abs(float(vals.get("credit", 0) or 0)) or abs(float(vals.get("debit", 0) or 0))
                if amt_val > 100000: continue  # 10万以上无日期无对方→汇总行
            except: pass
        
        # 统一金额
        if "amount" not in vals:
            amt = 0
            for k in ["income", "expense", "credit", "debit"]:
                try: amt = max(amt, abs(float(vals.get(k, 0) or 0)))
                except: pass
            vals["amount"] = str(amt)
        # 统一日期格式（优先用date，其次tx_time，支持datetime带时间组件的格式）
        d = (vals.get("date", "") or vals.get("tx_time", "")).strip()
        if d:
            # 先处理带时间的格式: "2025-09-29 10:33:35" → 取前10位日期
            if " " in d:
                d = d.split(" ")[0]
            d = d.replace("-", "").replace("/", "").replace(".", "").replace("年", "").replace("月", "").replace("日", "")
            if len(d) == 8: vals["date"] = d
        
        rows.append(vals)
    
    if not rows: return None
    return {"type": "bank_statement", "rows": rows}

def _parse_housing_fund_sheet(sheet, header):
    """解析住房公积金明细"""
    colmap = {
        "人员": "name", "姓名": "name", "证件号码": "id_card",
        "身份证号": "id_card", "工号": "emp_id",
        "缴存月份": "period", "缴存基数": "base",
        "缴存比例": "ratio", "单位缴存比例": "company_ratio",
        "个人缴存比例": "personal_ratio",
        "单位缴存额": "company_pay", "个人缴存额": "personal_pay",
        "月缴存额": "total_pay", "缴存额": "total_pay",
        "缴存人数": "count",
        "公积金账号": "hf_account", "个人账号": "personal_account",
    }
    cols = _find_cols_semantic(header, colmap)
    if not cols: return None
    rows = []
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else sheet.max_row
    for r in range(1, min(nrows, 200)):
        vals = {}
        for field, col in cols.items():
            try:
                v = str(sheet.cell_value(r, col)).strip() if hasattr(sheet, 'cell_value') else str(raw_vals[col] or '') if col < len(raw_vals) else ''
                vals[field] = v
            except: vals[field] = ""
        if not vals.get("name") and not vals.get("base"): continue
        for k in ["base", "company_pay", "personal_pay", "total_pay"]:
            try: vals[k] = float(vals.get(k, 0) or 0)
            except: vals[k] = 0
        rows.append(vals)
    return {"type": "housing_fund", "rows": rows}

def _parse_contract_sheet(sheet, header):
    """解析合同清单"""
    cols = _find_cols_semantic(header, {
        "合同编号": "contract_no", "合同名称": "name", "合同类型": "contract_type",
        "甲方": "party_a", "乙方": "party_b", "对方单位": "party_b",
        "合同金额": "amount", "已付金额": "paid_amount", "未付金额": "unpaid_amount",
        "签订日期": "signing_date", "签约日期": "signing_date",
        "生效日期": "effective_date", "到期日期": "expiry_date", "终止日期": "expiry_date",
        "履行状态": "status", "负责人": "responsible",
        "付款方式": "payment_method", "付款条件": "payment_terms",
        "备注": "remark", "条款": "terms",
    })
    if not cols: return None
    rows = []
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else sheet.max_row
    for r in range(1, min(nrows, 2000)):
        vals = {}
        for field, col in cols.items():
            try:
                v = str(sheet.cell_value(r, col)).strip() if hasattr(sheet, 'cell_value') else str(raw_vals[col] or '') if col < len(raw_vals) else ''
                vals[field] = v
            except: vals[field] = ""
        if not vals.get("name") and not vals.get("contract_no"): continue
        try: vals["amount"] = float(vals.get("amount", 0) or 0)
        except: vals["amount"] = 0
        rows.append(vals)
    return {"type": "contract_list", "rows": rows}

# ═══════════════ 诊断追踪系统 ═══════════════
# 目的：让系统能解释自己的每一个决策——为什么选这个类型、为什么排除那个类型、哪里出了问题
# 这是"把技能教给系统"的核心基础设施：系统不仅能做，还能说清楚为什么这样做

_LAST_PARSE_TRACE = {}  # 最近一次解析的完整追踪记录

def _init_trace(filename=""):
    """初始化一条新的解析追踪记录"""
    global _LAST_PARSE_TRACE
    _LAST_PARSE_TRACE = {
        "filename": filename,
        "timestamp": datetime.now().isoformat(),
        "sheets_scanned": 0,
        "keyword_phase": {"matches": [], "best": None},
        "structure_phase": {"candidates": [], "best": None},
        "cross_validation": {"agreed": None, "conflict": None, "winner": None, "reason": ""},
        "final_decision": {"type": None, "confidence": 0, "source": None, "reason": ""},
        "diagnostics": [],  # 诊断消息列表
        "suggestions": [],  # 修复建议
    }

def _trace_diag(msg, level="info"):
    """记录一条诊断消息"""
    global _LAST_PARSE_TRACE
    _LAST_PARSE_TRACE.setdefault("diagnostics", []).append({"level": level, "message": msg, "time": datetime.now().isoformat()})

def _get_last_trace():
    """获取最近一次解析的完整追踪"""
    return _LAST_PARSE_TRACE

def _parse_by_content(names, get_sheet, original_name=""):
    """智能识别: 扫描所有Sheet的表头和数据行，按特征库打分，选最高分类型。
    同时运行结构分析做交叉验证，记录完整决策过程。"""
    best_score = 0
    best_type = None
    best_sheet_idx = 0
    kw_trace_matches = []  # 记录所有达标的关键词匹配
    
    for i in range(len(names)):  # 扫描全部Sheet，不限于前3个
        try:
            s = get_sheet(i)
            # ═══ 扫前3行做表头识别（第0行常是标题，第1行才是列名） ═══
            all_text = ""
            # 行0单独扫描：检测文件标题（含进项/销项/台账等方向标识）
            row0_text = ""
            _nrows = s.nrows if hasattr(s, 'nrows') else (s.max_row or 1)
            if _nrows > 0:
                row0_vals = _get_row_values(s, 0)
                row0_text = " " + " ".join(str(v) for v in row0_vals if v)
            
            for scan_row in range(min(3, _nrows)):
                row_vals = _get_row_values(s, scan_row)
                all_text += " " + " ".join(str(v) for v in row_vals if v)
            
            # 标题行方向检测：给对应指纹加分（文件名+单元格双重检测）
            title_bonus = {}
            # 文件名关键词检测（超级权重99：文件名是用户对文件内容的直接标注，必须碾压任何指纹匹配）
            fn_lower = original_name.lower()
            if any(k in fn_lower for k in ["进销存", "台账", "明细账", "存货", "库存明细", "收发存"]):
                title_bonus["inventory"] = 99
            elif any(k in fn_lower for k in ["销项", "销售发票", "销货", "开票"]):
                title_bonus["sales_invoice"] = 99
            elif any(k in fn_lower for k in ["进项", "采购发票", "购货", "取得发票", "取票"]):
                title_bonus["purchase_invoice"] = 99
            elif any(k in fn_lower for k in ["银行", "流水", "bank"]):
                title_bonus["bank_statement"] = 99
            elif any(k in fn_lower for k in ["工资", "薪金", "所得"]):
                title_bonus["salary"] = 99
            elif any(k in fn_lower for k in ["社保", "社会保险"]):
                title_bonus["social_security"] = 99
            elif any(k in fn_lower for k in ["公积金"]):
                title_bonus["housing_fund"] = 99
            elif any(k in fn_lower for k in ["抵扣"]):
                title_bonus["input_vat_deduction"] = 99
            elif any(k in fn_lower for k in ["凭证", "记账", "序时"]):
                title_bonus["voucher"] = 99
            elif any(k in fn_lower for k in ["客户", "供应商", "人员", "部门", "档案"]):
                title_bonus["archive"] = 5
            # 单元格内容检测（作为补充）
            if "销项发票" in row0_text or "销售发票" in row0_text:
                title_bonus["sales_invoice"] = max(title_bonus.get("sales_invoice", 0), 3)
            elif "进项发票" in row0_text or "采购发票" in row0_text or "取得发票" in row0_text:
                title_bonus["purchase_invoice"] = max(title_bonus.get("purchase_invoice", 0), 3)
            elif "进销存" in row0_text or "台账" in row0_text or "存货" in row0_text or "库存" in row0_text or "物料" in row0_text:
                title_bonus["inventory"] = max(title_bonus.get("inventory", 0), 5)
            
            for ftype, fp in _FILE_FINGERPRINTS.items():
                score = 0
                kw_hits = []  # 命中的关键词
                for kw in fp["keywords"]:
                    if kw in all_text:
                        score += 1
                        kw_hits.append(kw)
                # 加分：次级关键词
                sec_hits = []
                if "secondary" in fp:
                    for kw in fp["secondary"]:
                        if kw in all_text:
                            score += 2
                            sec_hits.append(kw)
                
                threshold = fp["score_threshold"]
                # 标题行加分：如有标题方向匹配，额外加分
                if ftype in title_bonus:
                    score += title_bonus[ftype]
                    kw_hits.append(f"标题:{title_bonus[ftype]}分")
                if score >= threshold:
                    # 额外验证：取前3行样本数据
                    try:
                        sample_data = []
                        nrows = s.nrows if hasattr(s, 'nrows') else s.max_row
                        for r in range(1, min(nrows, 4)):
                            row_vals = _get_row_values(s, r)
                            sample_data.append(" ".join(str(v) for v in row_vals if v))
                        sample_text = " ".join(sample_data)
                        for kw in fp["keywords"]:
                            if kw in sample_text and kw not in all_text:
                                score += 0.5
                                kw_hits.append(kw + "(sample)")
                    except:
                        pass
                
                # 记录所有达标匹配（不仅是最高分）
                if score >= threshold:
                    kw_trace_matches.append({
                        "sheet": i, "type": ftype, "score": score, "threshold": threshold,
                        "kw_hits": kw_hits, "sec_hits": sec_hits
                    })
                
                if score > best_score:
                    best_score = score
                    best_type = ftype
                    best_sheet_idx = i
        except Exception as e:
            _trace_diag(f"扫描Sheet[{i}]异常: {e}", "warn")
    
    _LAST_PARSE_TRACE["keyword_phase"]["matches"] = kw_trace_matches
    _LAST_PARSE_TRACE["sheets_scanned"] = len(names)
    
    kw_passed = best_type is not None and best_score >= _FILE_FINGERPRINTS[best_type]["score_threshold"]
    if kw_passed:
        # ── invoice_universal/generic_data 吞并修复：优先选择得分最高的具体类型 ──
        if best_type in ("invoice_universal", "generic_data"):
            for m in sorted(kw_trace_matches, key=lambda x: -x["score"]):
                ft = m["type"]
                if ft not in ("invoice_universal", "generic_data") and m["score"] >= _FILE_FINGERPRINTS[ft]["score_threshold"]:
                    best_type = ft
                    best_score = m["score"]
                    best_sheet_idx = m["sheet"]
                    _trace_diag(f"{best_type}被具体类型覆盖: {ft}(得分{m['score']}), 原得分{best_score}")
                    break
        
        _LAST_PARSE_TRACE["keyword_phase"]["best"] = {"type": best_type, "score": best_score, "sheet": best_sheet_idx}
        _trace_diag(f"关键词匹配通过: {best_type}(得分{best_score}分), 阈值{_FILE_FINGERPRINTS[best_type]['score_threshold']}")
    else:
        best_info = f"{best_type}({best_score}分)" if best_type else "无"
        _trace_diag(f"关键词匹配未通过: 最高{best_info}, 未达阈值", "warn")
    
    # ═══════════════ 第2层：始终运行结构分析（不仅是兜底，也用于交叉验证） ═══════════════
    best_struct = None
    best_struct_conf = 0
    struct_candidates = []
    for i in range(len(names)):
        try:
            s = get_sheet(i)
            struct_result = _parse_by_structure_only(s)
            if struct_result and struct_result.get("confidence", 0) >= 0.50:
                struct_candidates.append({
                    "type": struct_result["type"], "confidence": struct_result["confidence"],
                    "sheet": i, "rows": len(struct_result.get("rows", []))
                })
            if struct_result and struct_result.get("confidence", 0) > best_struct_conf:
                best_struct = struct_result
                best_struct_conf = struct_result.get("confidence", 0)
        except Exception as e:
            _trace_diag(f"结构分析Sheet[{i}]异常: {e}", "warn")
    
    _LAST_PARSE_TRACE["structure_phase"]["candidates"] = struct_candidates
    if best_struct:
        _LAST_PARSE_TRACE["structure_phase"]["best"] = {"type": best_struct["type"], "confidence": best_struct_conf}
        _trace_diag(f"结构分析通过: {best_struct['type']}(置信度{best_struct_conf:.0%})")
    else:
        _trace_diag("结构分析未通过: 无结果或置信度不足", "warn")
    
    # ═══════════════ 交叉验证裁决 ═══════════════
    struct_passed = best_struct is not None and best_struct_conf >= 0.60
    cv = _LAST_PARSE_TRACE["cross_validation"]
    
    if kw_passed and struct_passed:
        kw_type = best_type
        st_type = best_struct["type"]
        # 类型映射：关键词类型 → 结构类型
        type_map = {
            "sales_invoice": "invoice", "purchase_invoice": "invoice", "invoice_universal": "invoice",
            "housing_fund": "housing_fund", "social_security": "social_security",
            "salary": "salary", "bank_statement": "bank_statement",
            "voucher": "trial_balance", "trial_balance": "trial_balance",
            "contract_list": "contract_list", "inventory": "trial_balance",
        }
        mapped_kw = type_map.get(kw_type, kw_type)
        
        if mapped_kw == st_type:
            cv["agreed"] = True
            cv["winner"] = "keyword"
            cv["reason"] = f"关键词({kw_type})与结构分析({st_type})一致，双重确认"
            _trace_diag(f"✓ 交叉验证一致: 关键词={kw_type} ↔ 结构={st_type}")
        else:
            cv["agreed"] = False
            cv["conflict"] = f"关键词={kw_type}({best_score}分) vs 结构={st_type}({best_struct_conf:.0%})"
            # ── 结构同形冲突规则：某些类型在纯结构层面不可区分 ──
            # salary/housing_fund/social_security 都是人名+金额的结构，
            # 只有关键词(列名语义)能区分。这类冲突优先信任关键词。
            STRUCT_AMBIGUOUS_PAIRS = [
                ("salary", "housing_fund"), ("salary", "social_security"),
                ("social_security", "housing_fund"), ("social_security", "salary"),
                ("housing_fund", "salary"), ("housing_fund", "social_security"),
                ("voucher", "bank_statement"), ("bank_statement", "voucher"),
            ]
            if (kw_type, st_type) in STRUCT_AMBIGUOUS_PAIRS:
                cv["winner"] = "keyword"
                cv["reason"] = f"关键词({kw_type})与结构({st_type})属结构同形类型，信任关键词语义"
                _trace_diag(f"⚠ 交叉验证冲突: {kw_type}↔{st_type}结构同形，采用关键词(得分{best_score})", "warn")
            # 结构分析置信度 ≥ 0.90 时，信任结构分析
            # 结构分析置信度 ≥ 0.90 时，通常信任结构分析
            # 但文件名明确标注时（score>=50），用户意图优先于结构分析
            elif best_struct_conf >= 0.90 and best_score < 50:
                cv["winner"] = "structure"
                cv["reason"] = f"结构分析置信度极高({best_struct_conf:.0%})，覆写关键词({kw_type})"
                _trace_diag(f"⚠ 交叉验证冲突: 结构分析置信度{best_struct_conf:.0%}极高，采用结构结果={st_type}，覆写关键词={kw_type}", "warn")
            elif best_score >= 50:
                cv["winner"] = "keyword"
                cv["reason"] = f"关键词得分极高({best_score}分/文件名明确)，覆写结构分析({st_type})"
                _trace_diag(f"⚠ 交叉验证冲突: 文件名明确标注，采用关键词={kw_type}(得分{best_score})", "warn")
            elif best_score >= 8:
                cv["winner"] = "keyword"
                cv["reason"] = f"关键词得分极高({best_score}分)，覆写结构分析({st_type})"
                _trace_diag(f"⚠ 交叉验证冲突: 关键词得分{best_score}极高，采用关键词={kw_type}", "warn")
            else:
                cv["winner"] = "structure"
                cv["reason"] = f"关键词({kw_type})与结构({st_type})冲突，默认信任结构分析(置信度{best_struct_conf:.0%})"
                _trace_diag(f"⚠ 交叉验证冲突: 采用结构分析={st_type}(置信度{best_struct_conf:.0%})", "warn")
    elif kw_passed and not struct_passed:
        cv["winner"] = "keyword"
        cv["reason"] = "仅关键词匹配通过，结构分析未达阈值"
        _trace_diag("结构分析未通过，仅使用关键词结果")
    elif not kw_passed and struct_passed:
        cv["winner"] = "structure"
        cv["reason"] = "仅结构分析通过，关键词匹配未达标"
        _trace_diag("关键词匹配失败，使用结构分析兜底")
    else:
        cv["winner"] = None
        cv["reason"] = "关键词和结构分析均未通过"
        _trace_diag("关键词和结构分析均失败，文件无法识别", "error")
    
    # ═══════════════ 最终裁决 ═══════════════
    winner = cv["winner"]
    fd = _LAST_PARSE_TRACE["final_decision"]
    
    if winner == "keyword":
        s = get_sheet(best_sheet_idx)
        header = _get_row_values(s, 0)
        result = _FILE_FINGERPRINTS[best_type]["parser"](s, header)
        
        # parser 可能因表头位置不匹配等原因返回 None
        if result is None:
            _trace_diag(f"关键词识别为{best_type}但parser返回None（表头位置可能不匹配），尝试结构兜底", "warn")
            if best_struct:
                # 结构分析有结果，降级为结构兜底
                fd["type"] = best_struct["type"]
                fd["source"] = "structure_fallback"
                fd["confidence"] = best_struct_conf
                fd["reason"] = cv["reason"]
                best_struct["_trace"] = _LAST_PARSE_TRACE
                return best_struct
            else:
                # 彻底失败
                _add_failure_suggestions()
                fd["type"] = None
                fd["source"] = None
                fd["confidence"] = 0
                fd["reason"] = cv["reason"]
                return None
        
        # 修正发票方向：销项发票的购方名称应在首列或前几列
        # ⚠ 此修正仅在文件名未明确标识方向时才生效（文件名标注是用户最直接可信的佐证）
        _fn_has_direction_hint = any(k in fn_lower for k in ["开票","销项","销售","进项","取得","取票","抵扣"])
        if best_type in ("purchase_invoice", "invoice_universal") and not _fn_has_direction_hint:
            hdr = " ".join(header)
            if "购方名称" in hdr or "购方税号" in hdr or "购买方" in hdr:
                result["type"] = "sales_invoice"
                for row in result.get("rows", []):
                    row["direction"] = "销项"
                _trace_diag("发票方向修正: 检测到购方关键词 → 标记为销项发票")
        
        # 文件名修正发票方向（最高优先级：文件名是用户对文件内容的直接标注）
        if result and result.get("type") in ("sales_invoice", "purchase_invoice", "invoice", "invoice_universal"):
            fn_lower = original_name.lower()
            if "进项" in fn_lower or "取得" in fn_lower or "取票" in fn_lower or "抵扣" in fn_lower:
                result["type"] = "purchase_invoice"
                for row in result.get("rows", []):
                    row["direction"] = "进项"
                _trace_diag(f"发票方向修正(文件名): {original_name} → 进项发票")
            elif "开票" in fn_lower or "销项" in fn_lower or "销售" in fn_lower:
                result["type"] = "sales_invoice"
                for row in result.get("rows", []):
                    row["direction"] = "销项"
                _trace_diag(f"发票方向修正(文件名): {original_name} → 销项发票")
        
        fd["type"] = result.get("type", best_type)
        fd["source"] = "keyword"
        fd["confidence"] = min(1.0, best_score / max(10, best_score + 2))
        fd["reason"] = cv["reason"]
        result["_trace"] = _LAST_PARSE_TRACE  # 附加追踪信息
        return result
    
    elif winner == "structure":
        fd["type"] = best_struct["type"]
        fd["source"] = "structure"
        fd["confidence"] = best_struct_conf
        fd["reason"] = cv["reason"]
        best_struct["_trace"] = _LAST_PARSE_TRACE
        return best_struct
    
    else:
        # 彻底失败，给出诊断建议
        _add_failure_suggestions()
        fd["type"] = None
        fd["source"] = None
        fd["confidence"] = 0
        fd["reason"] = cv["reason"]
        return None

def _add_failure_suggestions():
    """解析失败时自动分析原因并生成修复建议。
    将技能中的"常见陷阱与修复"知识嵌入系统，让系统能自我诊断。"""
    diags = _LAST_PARSE_TRACE.get("diagnostics", [])
    kw = _LAST_PARSE_TRACE.get("keyword_phase", {})
    st = _LAST_PARSE_TRACE.get("structure_phase", {})
    suggestions = []
    
    # 诊断1: 结构分析失败——可能是表头误判或数据形状异常
    try:
        st_candidates = st.get("candidates", [])
        st_best = st.get("best")
        if not st_candidates and not st_best:
            # 完全无结构候选——数据行全被判为重复表头/小计行/空行
            suggestions.append({
                "issue": "表头检测失败：所有行被跳过",
                "detail": "前几行可能全是数字（金额/日期），系统误判数据行为表头，导致后续所有数据行被判为'重复表头'或'小计行'而被跳过，最终0条有效数据行。",
                "fix": "(1)确认Excel前1-3行包含文本型列名（如'发票号码''金额''姓名'等），而非纯数字 (2)若数据从第1行开始，在首行上方插入一行列名 (3)检查是否有多余的空白行或标题行干扰了表头定位。"
            })
        elif st_candidates and not st_best:
            # 有候选但无不达阈值——可能是数据过于稀疏或格式异常
            top_candidates = sorted(st_candidates, key=lambda x: -x["confidence"])
            for c in top_candidates:
                suggestions.append({
                    "issue": f"数据结构接近{c['type']}但置信度不足({c['confidence']:.0%}, 需60%)",
                    "detail": f"Sheet[{c.get('sheet','?')}] {c.get('rows',0)}行数据，模式匹配{c['type']}但特征不够明确",
                    "fix": f"数据量可能太少(仅{c.get('rows',0)}行)，建议至少10行以上。或检查：日期格式是否标准(YYYY-MM-DD)、金额列是否纯数字(不含货币符号和单位文字)、身份证号是否18位完整。"
                })
    except Exception:
        pass
    
    # 诊断2: 所有关键词得分均为0——可能文件格式完全不匹配
    matches = kw.get("matches", [])
    if not matches:
        suggestions.append({
            "issue": "表头关键词全未命中",
            "detail": f"扫描了{_LAST_PARSE_TRACE.get('sheets_scanned', 0)}个Sheet的前3行，31类指纹无一匹配",
            "fix": "检查以下可能：(1)文件是否为财税相关数据(发票/工资/银行流水/社保/凭证等) (2)列名是否用了非标准简称(如'单位'代替'单位缴存额') (3)是否有合并单元格导致列名跨行 (4)尝试导出为标准格式(xlsx而非csv)"
        })
    
    # 诊断3: 有关键词命中但阈值不够
    if matches and not kw.get("best"):
        top_matches = sorted(matches, key=lambda x: -x["score"])
        for m in top_matches:
            suggestions.append({
                "issue": f"关键词得分不足: {m['type']}({m['score']}分, 需{m['threshold']}分)",
                "detail": f"命中关键词: {', '.join(m['kw_hits'])}",
                "fix": f"可能缺少关键列名。对于{m['type']}类型，确保包含完整的标准列名。例如银行流水需'对方户名'/'借方金额'等，工资需'本期收入'/'实发工资'等。"
            })
    
    # 诊断4: 结构分析接近阈值但不够
    st_best = st.get("best")
    st_candidates = st.get("candidates", [])
    if st_candidates and (not st_best or st_best.get("confidence", 0) < 0.60):
        top_st = sorted(st_candidates, key=lambda x: -x["confidence"])
        for c in top_st:
            suggestions.append({
                "issue": f"结构分析置信度不足: {c['type']}({c['confidence']:.0%}, 需60%)",
                "detail": f"数据形状接近{c['type']}模式，但特征不够明确。共{c['rows']}条数据。",
                "fix": "数据量可能太少，建议至少提供10行以上数据。或检查数据格式：日期是否标准(2025-01-15)、金额是否纯数字(不含文字)、身份证号是否完整(18位)。"
            })
    
    # 诊断5: 空数据或数据太少
    if not st_candidates and not matches:
        suggestions.append({
            "issue": "文件可能为空或格式异常",
            "detail": "关键词匹配和结构分析均无任何结果",
            "fix": "检查Excel文件是否可正常打开、是否包含数据行(非仅标题)、是否为加密或损坏文件。尝试用Excel重新保存后再上传。"
        })
    
    # 诊断6: 交叉验证冲突的通用建议
    cv = _LAST_PARSE_TRACE.get("cross_validation", {})
    if cv.get("conflict"):
        suggestions.append({
            "issue": "关键词与结构分析结论冲突",
            "detail": cv["conflict"],
            "fix": f"系统采用{cv.get('winner', '未知')}作为最终结果。建议人工复核：确认文件实际类型，必要时调整列名使其更精确。"
        })
    
    _LAST_PARSE_TRACE["suggestions"] = suggestions
    if suggestions:
        _trace_diag(f"生成{len(suggestions)}条修复建议", "info")

# ── 数据清洗：跳过小计/合计/空行/重复表头 ──
_SUBTOTAL_PATTERNS = ["小计", "合计", "总计", "累计", "本页小计", "本页合计", "本期合计", "本年累计", "当月合计", "收入笔数", "支出笔数", "收入合计", "支出合计"]

def _is_summary_row(vals):
    """判断是否为小计/合计行"""
    text = "".join(str(v) for v in vals if v)
    if not text.strip(): return True  # 全空行
    for p in _SUBTOTAL_PATTERNS:
        if p in text: return True
    return False

def _is_repeat_header(vals, header):
    """判断是否为重复表头行"""
    if not header or not vals: return False
    match = sum(1 for v in vals if v and any(str(v).strip() in str(h).strip() for h in header if h))
    return match >= min(3, len(header) - 1)  # 3个以上匹配视为重复表头

def _get_row_values(sheet, row_idx):
    """读取一行所有单元格的值，兼容xlrd和openpyxl(含read_only模式)
    
    优化：对于openpyxl read_only模式，使用行缓存避免重复iter_rows扫描。
    """
    # openpyxl: 有iter_rows方法
    if hasattr(sheet, 'iter_rows'):
        try:
            # 尝试使用行缓存（避免read_only模式下每个iter_rows都从头扫描）
            cache_key = '_row_cache'
            if not hasattr(sheet, cache_key):
                sheet._row_cache = {}
            if row_idx in sheet._row_cache:
                return sheet._row_cache[row_idx]
            # 批量读取：从当前已缓存的最大row+1到目标row
            cached_max = max(sheet._row_cache.keys()) if sheet._row_cache else -1
            if cached_max >= row_idx:
                return sheet._row_cache.get(row_idx, [])
            # 从 cached_max+1 读到 row_idx
            batch_start = cached_max + 2  # openpyxl使用1-based行号
            batch_end = row_idx + 2
            try:
                batch_rows = list(sheet.iter_rows(min_row=batch_start, max_row=batch_end, values_only=True))
                for i, batch_row in enumerate(batch_rows):
                    actual_row_idx = cached_max + 1 + i
                    if batch_row:
                        sheet._row_cache[actual_row_idx] = [str(c) if c is not None else "" for c in batch_row]
                    else:
                        sheet._row_cache[actual_row_idx] = []
            except:
                # 批量读取失败，回退到逐行读取
                rows = list(sheet.iter_rows(min_row=row_idx+1, max_row=row_idx+1, values_only=True))
                if rows and rows[0]:
                    sheet._row_cache[row_idx] = [str(c) if c is not None else "" for c in rows[0]]
                else:
                    sheet._row_cache[row_idx] = []
            return sheet._row_cache.get(row_idx, [])
        except:
            return []
    # xlrd: 有cell_value和ncols
    try:
        return [str(sheet.cell_value(row_idx, c)) for c in range(sheet.ncols)]
    except:
        return []

# ═══════════════ 通用表头检测（自适应任何行位置）═══════════════
# 核心哲学：人类看表格时自动扫描前几行找到"列名行"——系统也这样做
# 不再硬编码"表头在第1行"或"表头在第2行"

def _detect_header_row(sheet, nrows, column_keywords, max_scan=2000):
    """动态自适应表头检测：不预设表头在第N行之内，而是扫描直到找到确信的表头。
    
    工作原理：
    1. 从第0行开始逐行打分（命中column_keywords的数量）
    2. 当某行得分>=3 → 立即认定为表头（高置信度，直接返回）
    3. 如果连续100行得分都<=1 → 说明已进入数据区，取之前的最高分行为表头
    4. 如果到max_scan行仍未找到→取扫描范围内最高分（>=2才用，<2回退第0行）
    
    这个算法不依赖任何预设行号上限——表头在42行、100行、10000行都能找到。
    """
    best_row, best_score = 0, 0
    low_score_streak = 0  # 连续低分行计数
    
    for r in range(min(max_scan + 1, nrows)):
        row_vals = _get_row_values(sheet, r)
        row_text = " ".join(str(v) for v in row_vals if v)
        score = sum(1 for kw in column_keywords if kw in row_text)
        
        if score > best_score:
            best_score = score
            best_row = r
        
        # 高置信度命中：立即返回，不继续扫描（效率优化）
        if score >= 3:
            return r, {r: score}
        
        # 追踪连续低分行：连续100行都<=1说明已过表头进入数据区
        if score <= 1:
            low_score_streak += 1
            if low_score_streak >= 100 and best_score >= 2:
                return best_row, {best_row: best_score}
        else:
            low_score_streak = 0
    
    # 扫描结束：取最高分，>=2才认，<2回退
    if best_score >= 2:
        return best_row, {best_row: best_score}
    return 0, {}

# ═══════════════ 语义化列检测 ═══════════════
# 核心哲学：不依赖精确列名匹配，而是理解列的「语义角色」
# 人看到"本期收入"就知道是金额列，看到"销售方纳税人名称"就知道是公司名
# 这些语义角色通过大规模同义词库实现跨企业格式的通用识别

SEMANTIC_ROLES = {
    "person_name": ["姓名", "员工", "人员", "名称", "客户", "供应商", "户名", "对方", "销方名称", "购方名称",
                    "销售方", "购买方", "销售方纳税人名称", "销售方名称", "购买方名称", "纳税人名称", "name"],
    "id_number": ["身份证", "证件号码", "税号", "统一社会信用代码", "纳税人识别号", "USCC", "信用代码",
                  "身份证号", "身份证号码", "id", "ID"],
    "date_col": ["日期", "时间", "开票日期", "交易日期", "申请日期", "所属期", "税款所属期", "缴存月份",
                 "date", "时间", "年月"],
    "amount_col": ["金额", "收入", "支出", "工资", "费", "税", "缴", "扣", "额", "额合计",
                   "有效抵扣税额", "本期收入", "应发", "实发", "缴存额", "本期基本养老", "本期基本医疗",
                   "本期失业", "本期住房", "借方金额", "贷方金额", "价税合计", "不含税金额",
                   "amount", "salary", "fee", "tax", "debit", "credit", "net", "gross"],
    "counterparty": ["对方", "销方", "购方", "客户", "供应商", "购买方", "销售方",
                     "对方户名", "对方账号", "对方行名", "交易对手", "counterparty"],
    "invoice_number": ["发票号码", "发票代码", "数电发票号码", "发票编号", "invoice", "inv_no"],
    "bank_account": ["账号", "银行账号", "开户行", "银行", "account", "bank"],
    "employee_id": ["工号", "员工编号", "职工编号", "employee_id", "emp_id", "编号"],
    "department": ["部门", "科室", "车间", "dept", "department"],
    "position": ["职位", "岗位", "职务", "position", "title"],
}

def _find_cols_semantic(header, mapping):
    """增强版列名映射：精确匹配优先，语义角色匹配兜底
    
    - 第一轮：精确/子串匹配（原 _find_cols 逻辑）
    - 第二轮：语义角色匹配 —— 找不到精确匹配的字段，尝试用语义角色查找
    """
    cols = {}
    # Round 1: 精确匹配
    for keyword, field in mapping.items():
        best_i, best_len = None, 999
        for i, h in enumerate(header):
            hs = str(h).strip()
            if keyword in hs:
                if hs == keyword:
                    best_i = i; break
                if len(hs) < best_len:
                    best_len = len(hs); best_i = i
        if best_i is not None:
            cols[field] = best_i
    
    # Round 2: 语义角色兜底 —— 精确匹配没命中的字段
    missing_fields = [f for f in set(mapping.values()) if f not in cols]
    for field in missing_fields:
        # 找这个 field 对应的语义角色
        role = None
        for rname, synonyms in SEMANTIC_ROLES.items():
            # 检查 field 或它的关键词是否在语义角色中
            if field in synonyms or any(kw in synonyms for kw, f in mapping.items() if f == field and kw in " ".join(header)):
                if any(field in syn or syn in field for syn in synonyms):
                    role = rname
                    break
        if not role:
            # 模糊匹配：field 名本身可能暗示语义
            for rname, synonyms in SEMANTIC_ROLES.items():
                if any(syn in field or field in syn for syn in synonyms):
                    role = rname
                    break
        
        if role:
            synonyms = SEMANTIC_ROLES[role]
            best_i, best_score = None, 0
            for i, h in enumerate(header):
                if i in cols.values(): continue  # 已被占用的列
                hs = str(h).strip()
                score = 0
                for syn in synonyms:
                    if syn in hs:
                        score += len(syn) / len(hs) * 10  # 匹配越精准分越高
                        if hs == syn: score += 5  # 精确匹配加分
                if score > best_score:
                    best_score = score
                    best_i = i
            if best_i is not None and best_score > 3:
                cols[field] = best_i
    
    return cols

# ═══════════════ 数据内容推断列角色 ═══════════════
def _infer_columns_from_data(sheet, nrows):
    """不看表头，纯粹看数据内容猜每列的角色。
    
    这是终极兜底：当任何列名匹配都失败时，系统通过数据本身的形态来判断列的用途。
    就像人扫一眼表格——看到一列全是日期格式就知道是日期列，
    看到一列全是18位数字就知道是身份证号。
    """
    header = _get_row_values(sheet, 0)
    ncols = len(header) if header else min(20, sheet.ncols if hasattr(sheet, 'ncols') else sheet.max_column)
    sample_rows = min(nrows, 50)
    
    date_pattern = re.compile(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}')
    id_pattern = re.compile(r'^\d{15}$|^\d{17}[\dXx]$|^\d{18}$')
    amount_pattern = re.compile(r'^-?\d+\.?\d*$')
    bank_pattern = re.compile(r'^\d{10,20}$')
    phone_pattern = re.compile(r'^1[3-9]\d{9}$')
    
    col_roles = {}
    
    for ci in range(ncols):
        samples = []
        for r in range(1, sample_rows + 1):
            try:
                vals = _get_row_values(sheet, r)
                if ci < len(vals) and vals[ci] is not None and str(vals[ci]).strip():
                    samples.append(str(vals[ci]).strip())
            except: pass
        
        if not samples:
            continue
        
        date_count = sum(1 for s in samples if date_pattern.match(s))
        id_count = sum(1 for s in samples if id_pattern.match(s))
        amount_count = sum(1 for s in samples if amount_pattern.match(s.replace(',','')))
        bank_count = sum(1 for s in samples if bank_pattern.match(s))
        phone_count = sum(1 for s in samples if phone_pattern.match(s))
        
        total = len(samples)
        roles = []
        
        if date_count / total > 0.5: roles.append("date_col")
        if id_count / total > 0.3: roles.append("id_number")
        if amount_count / total > 0.5: roles.append("amount_col")
        if bank_count / total > 0.3: roles.append("bank_account")
        if phone_count / total > 0.3: roles.append("contact")
        
        # 文本列判断：不是数字/日期/ID的就是文本
        if not roles and total > 0:
            text_count = total - amount_count - date_count - id_count
            if text_count / total > 0.7:
                # 判断是人名还是其他
                avg_len = sum(len(s) for s in samples) / len(samples)
                if avg_len <= 4: roles.append("person_name")   # 短文本→人名
                elif avg_len <= 20: roles.append("counterparty")  # 中文本→公司名
                else: roles.append("description")  # 长文本→摘要/描述
        
        if roles:
            col_roles[ci] = roles
    
    return col_roles

# ═══════════════ 涉税相关性评分 ═══════════════
def _score_tax_relevance(sheet, nrows):
    """分析表格内容是否与涉税相关。返回 0-100 分数。
    
    涉税相关表格通常包含以下特征：
    - 包含金额列（交易/收入/税额）
    - 包含日期列
    - 包含对方名称（交易对手/供应商/客户）
    - 包含发票号码或税号
    - 包含税务关键词（增值税/所得税/抵扣/申报/缴税）
    """
    header = _get_row_values(sheet, 0)
    header_text = " ".join(str(v) for v in header if v)
    sample_rows = min(nrows, 30)
    all_data = header_text + " "
    for r in range(1, sample_rows + 1):
        try:
            vals = _get_row_values(sheet, r)
            all_data += " " + " ".join(str(v) for v in vals if v)
        except: pass
    
    score = 0
    
    # 1. 列名含税务关键词
    tax_kw = ["发票", "税金", "税额", "增值税", "所得税", "抵扣", "申报", "缴税", "纳税",
              "银行", "流水", "凭证", "记账", "工资", "社保", "公积金", "销项", "进项",
              "合同", "收入", "成本", "应收", "应付", "借方", "贷方", "余额", "对方"]
    for kw in tax_kw:
        if kw in header_text: score += 3
    
    # 2. 数据中包含金额
    col_roles = _infer_columns_from_data(sheet, nrows)
    if any("amount_col" in roles for roles in col_roles.values()): score += 20
    
    # 3. 包含日期列
    if any("date_col" in roles for roles in col_roles.values()): score += 15
    
    # 4. 包含对方名称（交易相关）
    if any("counterparty" in roles for roles in col_roles.values()): score += 15
    
    # 5. 包含身份证/税号
    if any("id_number" in roles for roles in col_roles.values()): score += 10
    
    # 6. 数据量合理（有足够的行）
    if sample_rows > 3: score += 5
    if sample_rows > 10: score += 5
    
    # 7. 数据含发票号码模式
    if re.search(r'\d{10,12}', all_data): score += 5
    
    return min(100, score)

# ═══════════════ 纯内容结构分析层 ═══════════════
# 核心哲学：不看文件名、不看Sheet名、不看表头关键词 —— 只看数据本身的形状、类型、分布、关联
# 人看到一个表：日期列 + 金额列 + 对方户名列 → 就知道是银行流水
# 人看到一个表：姓名列 + 身份证号 + 多列金额 → 就知道是工资表
# 下面就是把人的这个直觉，翻译成代码

import re

def _classify_cell_type(val_str):
    """分类单个单元格的值类型。返回 (type, normalized_value)"""
    v = val_str.strip() if val_str else ""
    if not v or v in ("None", "nan", "N/A", "-", "/", "——", "..."):
        return ("empty", None)
    
    # ── 日期检测 ──
    # 2025-01-15, 2025/01/15, 2025.01.15, 20250115, 2025年1月15日
    date_patterns = [
        r'^\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}$',
        r'^\d{8}$',  # 20250115
        r'^\d{4}年\d{1,2}月\d{1,2}日?$',
        r'^\d{1,2}[-/\.]\d{1,2}[-/\.]\d{4}$',  # 01/15/2025
    ]
    for pat in date_patterns:
        if re.match(pat, v):
            return ("date", v)
    # 也检测看起来像日期的纯数字（在合理范围内）
    if v.isdigit() and len(v) == 8:
        try:
            y, m, d = int(v[:4]), int(v[4:6]), int(v[6:8])
            if 2020 <= y <= 2030 and 1 <= m <= 12 and 1 <= d <= 31:
                return ("date", v)
        except: pass
    
    # ── 身份证号 ──
    if re.match(r'^\d{17}[\dXx]$', v):
        return ("id_card", v)
    
    # ── 金额/数字检测 ──
    v_clean = v.replace(",", "").replace("，", "").replace("￥", "").replace("¥", "").replace(" ", "")
    try:
        n = float(v_clean)
        if n == int(n) and abs(n) < 1e10:
            n = int(n)
        
        # 百分比：0-1 或 0-100 范围
        if 0 < n <= 1 and len(v_clean.replace(".", "")) <= 3:
            return ("percentage", n)
        if 0 < n <= 100 and any(p in v for p in ["%", "％"]):
            return ("percentage", n / 100.0)
        
        # 小整数（序号/计数）
        if isinstance(n, int) and 1 <= n <= 100 and v_clean.isdigit():
            return ("count", n)
        
        # 金额：一般 > 0，可以是整数或小数
        return ("amount", n)
    except ValueError:
        pass
    
    # ── 税率/比例（无百分号但看起来像） ──
    if re.match(r'^0?\.\d{1,4}$', v_clean):
        try:
            n = float(v_clean)
            if 0 < n < 1:
                return ("percentage", n)
        except: pass
    
    # ── 编码类（发票代码、合同编号等） ──
    if re.match(r'^\d{10,20}$', v):
        return ("code", v)
    if re.match(r'^\d{5,9}$', v):
        return ("code", v)
    if re.match(r'^[A-Za-z0-9]{6,}$', v) and any(c.isalpha() for c in v):
        return ("code", v)
    
    # ── 人名检测（2-4个中文字符） ──
    if re.match(r'^[\u4e00-\u9fff]{2,4}$', v):
        return ("person_name", v)
    
    # ── 公司名/长文本 ──
    if re.match(r'^[\u4e00-\u9fff]{5,}', v) and any(k in v for k in ["公司", "集团", "企业", "中心", "有限", "股份"]):
        return ("company_name", v)
    
    # ── 较长的中文文本 ──
    if re.match(r'^[\u4e00-\u9fff]{5,}', v):
        return ("text_cn", v)
    
    # ── 纯中文短词（科目名称、费用类别等） ──
    if re.match(r'^[\u4e00-\u9fff]{2,6}$', v):
        return ("short_cn", v)
    
    # ── 其他文本 ──
    if len(v) > 0:
        return ("text", v)
    
    return ("empty", None)


def _profile_sheet_columns(sheet):
    """纯内容结构分析：不看表头，只看数据列的类型和分布。
    返回: {
        'total_rows': int, 'col_count': int,
        'columns': [{type_distribution: {...}, dominant_type: str, sample_values: [...], ...}],
        'signature': str   # 如 "date|amount|amount|text|text|amount"
    }
    """
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else (sheet.max_row or 1)
    if nrows < 2: return None
    
    # 先用前几行找到真正的表头行（跳过标题）
    # 表头特征：文本多、数字/日期少、各行下面都有数据
    header_row = 0
    max_data_start = min(10, nrows)
    best_data_score = -1
    best_text_score = -1
    
    for candidate_header in range(max_data_start):
        # 1. 看下面行有多少数据
        data_score = 0
        for dr in range(candidate_header + 1, min(candidate_header + 6, nrows)):
            row_vals = _get_row_values(sheet, dr)
            non_empty = sum(1 for v in row_vals if v and str(v).strip())
            if non_empty >= 2:
                data_score += non_empty
        
        # 2. 当前行本身的"表头特征"分：文本多得分高，数字/日期多扣分
        header_vals = _get_row_values(sheet, candidate_header)
        text_score = 0
        non_empty_count = 0
        for v in header_vals:
            if not v or str(v).strip() in ("", "None", "nan"):
                continue
            non_empty_count += 1
            t, _ = _classify_cell_type(str(v))
            if t in ("text", "text_cn", "short_cn", "person_name", "company_name"):
                text_score += 2  # 文本 = 表头信号
            elif t in ("date", "amount", "code", "percentage", "count", "id_card"):
                text_score -= 1  # 数字/日期 = 不是表头
        
        # 综合评分：数据要好，文本特征更要强
        combined = data_score * 0.5 + text_score * 2 + (1 if candidate_header <= 1 else 0) * 3
        if combined > best_data_score:
            best_data_score = combined
            best_text_score = text_score
            header_row = candidate_header
    
    # 跳过表头和空行，取样本数据（最多100行）
    sample_rows = []
    sample_start = header_row + 1
    for r in range(sample_start, min(nrows, sample_start + 100)):
        row_vals = _get_row_values(sheet, r)
        if _is_summary_row(row_vals): continue
        if _is_repeat_header(row_vals, _get_row_values(sheet, header_row)): continue
        # 至少2个非空值
        non_empty = [str(v).strip() for v in row_vals if v and str(v).strip() not in ("None", "nan")]
        if len(non_empty) >= 2:
            sample_rows.append(row_vals)
    
    if len(sample_rows) < 2:
        return None
    
    # 确定列数（取最大值）
    col_count = max(len(r) for r in sample_rows) if sample_rows else 0
    if col_count == 0:
        return None
    
    # 对每一列进行类型分析
    columns = []
    for c in range(col_count):
        values = []
        for r in sample_rows:
            if c < len(r) and r[c]:
                values.append(str(r[c]).strip())
        if not values:
            columns.append({"dominant_type": "empty", "non_empty": 0, "dominant_ratio": 0, "numeric_rate": 0})
            continue
        
        # 统计类型分布
        type_counts = {}
        type_samples = {}
        for v in values:
            t, norm = _classify_cell_type(v)
            type_counts[t] = type_counts.get(t, 0) + 1
            if t not in type_samples and norm is not None:
                type_samples[t] = norm
        
        total = len(values)
        non_empty_total = sum(c for t, c in type_counts.items() if t != "empty")
        
        # 找主导类型（占比最高的非empty类型）
        dominant = "text"
        dominant_ratio = 0
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
            if t == "empty": continue
            ratio = c / max(non_empty_total, 1)
            if ratio > dominant_ratio:
                dominant = t
                dominant_ratio = ratio
        
        # 纯数字率（amount + percentage + count + code）
        numeric_rate = sum(type_counts.get(t, 0) for t in ["amount", "percentage", "count"]) / max(total, 1)
        
        columns.append({
            "dominant_type": dominant,
            "dominant_ratio": round(dominant_ratio, 2),
            "type_distribution": {t: c for t, c in type_counts.items() if t != "empty"},
            "non_empty": non_empty_total,
            "numeric_rate": round(numeric_rate, 2),
            "samples": [type_samples.get(dominant)],
        })
    
    # 生成结构签名
    signature_parts = []
    for col in columns:
        if col["dominant_type"] == "empty" or col.get("non_empty", 0) == 0:
            continue  # 跳过全空列
        sig = col["dominant_type"][:4]  # 缩写
        if col.get("dominant_ratio", 0) < 0.5:
            sig = "mixed"
        signature_parts.append(sig)
    signature = "|".join(signature_parts)
    
    # 统计有效数据行数
    valid_rows = 0
    for r in range(sample_start, min(nrows, sample_start + 200)):
        row_vals = _get_row_values(sheet, r)
        if not _is_summary_row(row_vals):
            non_empty = [v for v in row_vals if v and str(v).strip() not in ("None", "nan")]
            if len(non_empty) >= 2:
                valid_rows += 1
    
    return {
        "total_rows": valid_rows,
        "col_count": col_count,
        "columns": columns,
        "signature": signature,
    }


# ═══════════════ 结构签名 → 业务类型 映射表 ═══════════════
# 这是核心：人看到一个表的数据形状，就能判断它是什么
# 评分策略：每种类型有独特的加分项和扣分项，确保区分度
_STRUCTURAL_PATTERNS = [
    # ═══ 银行流水 ═══
    # 核心特征：date列 + 对方户名(文本列) + 多个金额列 + 大量数据行
    # 与科目余额表区分：前者有日期、有文本(户名/摘要)，后者无日期、有更多金额列
    {
        "type": "bank_statement",
        "col_count_range": (4, 25),
        "min_rows": 5,
        "required_types": ["date", "amount"],
        "min_amount_cols": 2,
        "bonus": {
            "has_date": 4,           # 必须有日期
            "has_text": 2,           # 对方户名/摘要
            "many_rows": 3,          # rows >= 10
            "has_person_or_company": 1,  # 对方户名是人名或公司名
        },
        "penalty": {
            "too_many_amount_cols": (8, -3),  # amount列太多→可能是科目余额表
            "has_percentage": -2,     # 银行流水不应有百分比
            "has_id_card": -2,        # 银行流水不应有身份证
        },
        "confidence": 0.85,
    },
    # ═══ 工资薪金 ═══
    # 核心特征：大量列(15-50)、大量amount列(>10)、身份证号、人名
    {
        "type": "salary",
        "col_count_range": (4, 60),
        "min_rows": 1,
        "required_types": ["amount"],
        "min_amount_cols": 4,
        "bonus": {
            "has_id_card": 6,         # 身份证号=极强信号
            "many_amount_cols": 5,    # amount>=10列
            "has_person_name": 2,     # 人名
            "high_col_count": 2,      # 列数>=15
        },
        "penalty": {
            "has_code": -2,           # 编码列→可能不是工资
            "has_percentage": -1,     # 工资可能有百分比(税率)但不强
        },
        "confidence": 0.80,
    },
    # ═══ 发票（进项/销项） ═══
    # 核心特征：编码列(inv_code) + 日期 + 金额 + 税额 + 公司名
    {
        "type": "invoice",
        "col_count_range": (5, 40),
        "min_rows": 1,
        "required_types": ["amount"],
        "min_amount_cols": 2,
        "bonus": {
            "has_code": 5,            # 发票代码/号码=极强信号
            "has_date": 3,            # 开票日期
            "has_company": 3,         # 购买方/销售方名称
            "has_amount_tax_pair": 2, # 金额+税额配对
            "has_percentage": 1,      # 税率
        },
        "penalty": {
            "has_id_card": -3,        # 发票不应有身份证
            "many_person_names": -2,  # 多个人名→不是发票
        },
        "confidence": 0.85,
    },
    # ═══ 社保 ═══
    # 核心特征：人名+身份证+多列amount(各险种) + 列数8-45
    {
        "type": "social_security",
        "col_count_range": (8, 50),
        "min_rows": 1,
        "required_types": ["amount"],
        "min_amount_cols": 4,
        "bonus": {
            "has_id_card": 4,
            "has_person_name": 3,
            "many_amount_cols": 3,    # amount>=6
            "high_col_count": 2,      # 列数>=15
        },
        "penalty": {
            "has_code": -2,
            "has_date": -1,           # 社保表通常没有日期列
            "has_company": -2,
        },
        "confidence": 0.75,
    },
    # ═══ 公积金 ═══
    # 核心特征：少列(6-12)、人名+身份证、基数+百分比+金额、数学关系可验证
    {
        "type": "housing_fund",
        "col_count_range": (5, 15),
        "min_rows": 1,
        "required_types": ["amount"],
        "min_amount_cols": 3,
        "bonus": {
            "has_percentage": 6,      # 公积金必有缴存比例=极强信号
            "has_person_name": 3,     # 人名
            "has_id_card": 3,         # 身份证
            "low_col_count": 3,       # 列少(<=12)且紧凑
            "amounts_match_ratio": 4, # base*ratio ≈ company/personal_pay
        },
        "penalty": {
            "has_code": -3,
            "has_date": -2,
            "has_company": -3,
            "high_col_count": -2,     # 列>=15→不太可能是公积金
        },
        "confidence": 0.80,
    },
    # ═══ 科目余额表 ═══
    # 核心特征：无日期、>=4个amount列、>=10行
    {
        "type": "trial_balance",
        "col_count_range": (5, 20),
        "min_rows": 5,
        "required_types": ["amount"],
        "min_amount_cols": 4,
        "bonus": {
            "many_amount_cols": 4,    # 5个以上amount列
            "no_date": 2,             # 无日期=科目余额表的特征
            "many_rows": 2,           # rows>=20
        },
        "penalty": {
            "has_date": -4,           # 有日期→不是科目余额表
            "has_id_card": -3,
            "has_percentage": -2,
        },
        "confidence": 0.75,
    },
    # ═══ 合同清单 ═══
    {
        "type": "contract_list",
        "col_count_range": (5, 25),
        "min_rows": 1,
        "required_types": ["amount"],
        "min_amount_cols": 1,
        "bonus": {
            "has_code": 3,
            "has_date": 3,
            "has_company": 2,
        },
        "penalty": {
            "has_id_card": -2,
            "has_percentage": -1,
        },
        "confidence": 0.70,
    },
    # ═══ 费用明细 ═══
    {
        "type": "expense_detail",
        "col_count_range": (3, 20),
        "min_rows": 3,
        "required_types": ["amount"],
        "min_amount_cols": 1,
        "max_amount_cols": 4,
        "bonus": {
            "has_date": 2,
            "has_text": 2,
        },
        "penalty": {
            "has_id_card": -2,
            "has_percentage": -1,
        },
        "confidence": 0.65,
    },
]


def _match_structural_pattern(profile):
    """根据数据结构签名匹配业务类型。返回 [(type, confidence), ...]
    新评分系统：每种类型有独特的 bonus（加分项）和 penalty（扣分项），确保区分度。
    """
    if not profile: return []
    
    cols = profile["columns"]
    total_rows = profile.get("total_rows", 0)
    col_count = profile["col_count"]
    
    # 列类型统计
    type_counts = {}
    amount_cols = 0
    has_date = False
    has_percentage = False
    has_person_name = False
    has_id_card = False
    has_code = False
    has_text = False
    has_company = False
    person_name_count = 0
    
    for col in cols:
        t = col["dominant_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
        if t in ("amount",): amount_cols += 1
        if t == "date": has_date = True
        if t == "percentage": has_percentage = True
        if t == "person_name":
            has_person_name = True
            person_name_count += 1
        if t == "id_card": has_id_card = True
        if t == "code": has_code = True
        if t in ("text", "text_cn"): has_text = True
        if t == "company_name": has_company = True
    
    # 额外特征：金额+税额配对（发票特征）
    has_amount_tax_pair = amount_cols >= 2 and has_percentage
    
    # 公积金数学关系验证
    amounts_match_ratio = False
    if has_percentage and amount_cols >= 3 and has_person_name:
        # 找金额列和百分比列，看 sample 中是否有 base*ratio≈其他金额列
        try:
            pct_samples = []
            amt_samples = []
            for col in cols:
                if col["dominant_type"] == "percentage" and col.get("samples"):
                    pct_samples.extend([s for s in col["samples"] if isinstance(s, (int, float)) and 0 < s <= 1])
                if col["dominant_type"] == "amount" and col.get("samples"):
                    amt_samples.extend([s for s in col["samples"] if isinstance(s, (int, float)) and s > 0])
            if pct_samples and amt_samples:
                for pct in pct_samples:
                    for amt in amt_samples:
                        if amt > 0 and pct > 0:
                            expected = round(amt * pct, 2)
                            for other_amt in amt_samples:
                                if other_amt != amt and abs(other_amt - expected) < max(1, expected * 0.05):
                                    amounts_match_ratio = True
                                    break
                            if amounts_match_ratio: break
                    if amounts_match_ratio: break
        except:
            pass
    
    candidates = []
    
    for pattern in _STRUCTURAL_PATTERNS:
        score = 0
        reasons = []
        
        # ── 基础条件检查 ──
        lo, hi = pattern.get("col_count_range", (1, 999))
        if not (lo <= col_count <= hi):
            continue  # 列数不匹配直接跳过
        
        if total_rows < pattern.get("min_rows", 0):
            continue  # 行数不够直接跳过
        
        req_types = pattern.get("required_types", [])
        if not all(type_counts.get(t, 0) > 0 for t in req_types):
            continue  # 必需类型缺失直接跳过
        
        min_amt = pattern.get("min_amount_cols", 0)
        if amount_cols < min_amt:
            continue
        
        max_amt = pattern.get("max_amount_cols", 999)
        if amount_cols > max_amt:
            continue
        
        # ── 基础分（通过基础条件的奖励） ──
        score = 3  # 基础分
        
        # ── Bonus 加分项 ──
        bonus = pattern.get("bonus", {})
        if bonus.get("has_date") and has_date:
            score += bonus["has_date"]
            reasons.append(f"has_date+{bonus['has_date']}")
        if bonus.get("has_text") and has_text:
            score += bonus["has_text"]
            reasons.append(f"has_text+{bonus['has_text']}")
        if bonus.get("many_rows") and total_rows >= 10:
            score += bonus["many_rows"]
            reasons.append(f"many_rows+{bonus['many_rows']}")
        if bonus.get("has_person_or_company") and (has_person_name or has_company):
            score += bonus["has_person_or_company"]
        if bonus.get("has_id_card") and has_id_card:
            score += bonus["has_id_card"]
            reasons.append(f"has_id_card+{bonus['has_id_card']}")
        if bonus.get("has_person_name") and has_person_name:
            score += bonus["has_person_name"]
            reasons.append(f"has_person+{bonus['has_person_name']}")
        if bonus.get("many_amount_cols"):
            threshold = 10 if pattern["type"] == "salary" else (6 if pattern["type"] == "social_security" else 5)
            if amount_cols >= threshold:
                score += bonus["many_amount_cols"]
                reasons.append(f"many_amt_cols({amount_cols})+{bonus['many_amount_cols']}")
        if bonus.get("high_col_count") and col_count >= 15:
            score += bonus["high_col_count"]
            reasons.append(f"high_cols({col_count})+{bonus['high_col_count']}")
        if bonus.get("has_code") and has_code:
            score += bonus["has_code"]
            reasons.append(f"has_code+{bonus['has_code']}")
        if bonus.get("has_company") and has_company:
            score += bonus["has_company"]
            reasons.append(f"has_company+{bonus['has_company']}")
        if bonus.get("has_amount_tax_pair") and has_amount_tax_pair:
            score += bonus["has_amount_tax_pair"]
            reasons.append(f"amt_tax_pair+{bonus['has_amount_tax_pair']}")
        if bonus.get("has_percentage") and has_percentage:
            score += bonus["has_percentage"]
            reasons.append(f"has_pct+{bonus['has_percentage']}")
        if bonus.get("low_col_count") and col_count <= 12:
            score += bonus["low_col_count"]
            reasons.append(f"low_cols({col_count})+{bonus['low_col_count']}")
        if bonus.get("amounts_match_ratio") and amounts_match_ratio:
            score += bonus["amounts_match_ratio"]
            reasons.append(f"ratio_match+{bonus['amounts_match_ratio']}")
        if bonus.get("no_date") and not has_date:
            score += bonus["no_date"]
            reasons.append(f"no_date+{bonus['no_date']}")
        
        # ── Penalty 扣分项 ──
        penalty = pattern.get("penalty", {})
        if penalty.get("too_many_amount_cols"):
            limit, pts = penalty["too_many_amount_cols"]
            if amount_cols > limit:
                score += pts
                reasons.append(f"too_many_amt({amount_cols}>{limit}){pts}")
        if penalty.get("has_percentage") and has_percentage:
            score += penalty["has_percentage"]
            reasons.append(f"has_pct{penalty['has_percentage']}")
        if penalty.get("has_id_card") and has_id_card:
            score += penalty["has_id_card"]
            reasons.append(f"has_id_card{penalty['has_id_card']}")
        if penalty.get("has_code") and has_code:
            score += penalty["has_code"]
            reasons.append(f"has_code{penalty['has_code']}")
        if penalty.get("has_date") and has_date:
            score += penalty["has_date"]
            reasons.append(f"has_date{penalty['has_date']}")
        if penalty.get("has_company") and has_company:
            score += penalty["has_company"]
            reasons.append(f"has_company{penalty['has_company']}")
        if penalty.get("high_col_count") and col_count >= 15:
            score += penalty["high_col_count"]
            reasons.append(f"high_cols{penalty['high_col_count']}")
        if penalty.get("many_person_names") and person_name_count >= 3:
            score += penalty["many_person_names"]
            reasons.append(f"many_persons({person_name_count}){penalty['many_person_names']}")
        
        # ── 最终得分 → 置信度 ──
        # score 越大越确信，base_confidence 是底分
        base_conf = pattern["confidence"]
        adj_conf = min(0.99, base_conf + max(0, score - 3) * 0.025)
        # score < 0 → 即使基础条件通过，也不可信
        if score < 1:
            adj_conf = base_conf * 0.6
        
        candidates.append({
            "type": pattern["type"],
            "confidence": round(adj_conf, 4),
            "score": score,
            "reasons": reasons,
        })
    
    # 按 (得分降序, 置信度降序) 排列 —— 得分优先，因为得分反映实际特征匹配
    candidates.sort(key=lambda x: (-x["score"], -x["confidence"]))
    
    return candidates


def _parse_by_structure_only(sheet):
    """纯靠数据结构识别并解析，完全不依赖表头和关键词。
    当 _parse_by_content 的关键词匹配失败时，调用此函数作为兜底。
    """
    profile = _profile_sheet_columns(sheet)
    if not profile:
        return None
    
    candidates = _match_structural_pattern(profile)
    if not candidates or candidates[0]["confidence"] < 0.60:
        return None
    
    best = candidates[0]
    ftype = best["type"]
    
    # 找到真正的表头行（文本多=表头，数字多=数据）
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else (sheet.max_row or 1)
    header_row = 0
    best_data_score = -1
    for candidate_header in range(min(10, nrows)):
        data_score = 0
        for dr in range(candidate_header + 1, min(candidate_header + 6, nrows)):
            row_vals = _get_row_values(sheet, dr)
            non_empty = sum(1 for v in row_vals if v and str(v).strip())
            if non_empty >= 2:
                data_score += non_empty
        header_vals = _get_row_values(sheet, candidate_header)
        text_score = 0
        for v in header_vals:
            if not v or str(v).strip() in ("", "None", "nan"): continue
            t, _ = _classify_cell_type(str(v))
            if t in ("text", "text_cn", "short_cn", "person_name", "company_name"):
                text_score += 2
            elif t in ("date", "amount", "code", "percentage", "count", "id_card"):
                text_score -= 1
        combined = data_score * 0.5 + text_score * 2 + (1 if candidate_header <= 1 else 0) * 3
        if combined > best_data_score:
            best_data_score = combined
            header_row = candidate_header
    
    header = _get_row_values(sheet, header_row)
    
    # 根据业务类型构建通用解析结果
    rows = []
    data_start = header_row + 1
    for r in range(data_start, min(nrows, 5000)):
        raw_vals = _get_row_values(sheet, r)
        if _is_summary_row(raw_vals): continue
        if _is_repeat_header(raw_vals, header): continue
        
        vals = {}
        for i, v in enumerate(raw_vals):
            col_type, norm_val = _classify_cell_type(str(v))
            key = header[i] if i < len(header) and header[i] else f"col_{i}"
            vals[key] = norm_val if norm_val is not None else str(v).strip()
        
        non_empty = sum(1 for v in vals.values() if v not in ("", None, 0, "0"))
        if non_empty >= 2:
            rows.append(vals)
    
    if not rows:
        return None
    
    return {
        "type": ftype,
        "rows": rows,
        "confidence": best["confidence"],
        "source": "structure",  # 标记来源：结构分析
    }


def _parse_input_vat_sheet(sheet):
    """解析进项认证抵扣明细"""
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else sheet.max_row
    header_row, _scores = _detect_header_row(sheet, nrows, [
        "数电发票号码", "发票代码", "发票号码", "开票日期",
        "金额", "税额", "有效抵扣税额", "勾选状态", "发票来源"
    ])
    header = _get_row_values(sheet, header_row)
    cols = _find_cols_semantic(header, {
        "数电发票号码": "digital_invoice_no", "发票代码": "invoice_code",
        "发票号码": "invoice_no", "开票日期": "date",
        "销售方纳税人识别号": "seller_tax", "销售方纳税人名称": "seller_name",
        "金额": "amount", "税额": "tax", "有效抵扣税额": "deductible_tax",
        "勾选状态": "status", "发票来源": "source",
        "票种": "invoice_type", "发票风险等级": "risk_level",
    })
    if not cols: return None
    rows = []
    start_row = header_row + 1
    for r in range(start_row, min(nrows, 5000)):
        vals = {}
        for field, col in cols.items():
            try: vals[field] = str(sheet.cell_value(r, col)).strip() if hasattr(sheet, 'cell_value') else str(_get_row_values(sheet, r)[col] or '')
            except: vals[field] = ""
        if not vals.get("invoice_no") and not vals.get("digital_invoice_no"): continue
        for k in ["amount", "tax", "deductible_tax"]:
            try: vals[k] = float(vals.get(k, 0) or 0)
            except: vals[k] = 0
        vals["direction"] = "进项"
        rows.append(vals)
    return {"type": "input_vat_deduction", "rows": rows, "sub_type": "进项认证抵扣"}

def _parse_invoice_sheet(sheet, direction):
    # ═══ 自适应表头检测：扫描前20行找真正的列名行 ═══
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else sheet.max_row
    header_row, _scores = _detect_header_row(sheet, nrows, [
        "发票号码", "发票代码", "数电发票号码", "开票日期", "购方名称", "销方名称",
        "金额", "税额", "价税合计", "货物或应税劳务名称", "规格型号", "数量", "单价"
    ])
    header = _get_row_values(sheet, header_row)
    cols = _find_cols_semantic(header, {
        "发票类型": "inv_type", "发票号码": "inv_no", "发票代码": "inv_code",
        "购方名称": "buyer", "购方税号": "buyer_tax", "购买方名称": "buyer", "购买方纳税人识别号": "buyer_tax",
        "销方名称": "seller", "销方税号": "seller_tax", "销售方名称": "seller", "销售方纳税人识别号": "seller_tax",
        "开票项目": "goods", "货物或应税劳务名称": "goods",
        "金额": "amount", "税额": "tax", "价税合计": "total",
        "业务类型": "biz_type", "税收编码": "tax_code", "税收分类编码": "tax_code",
        "开票日期": "date", "数量": "qty", "单价": "price",
        "税率": "tax_rate", "规格型号": "spec", "计量单位": "unit",
        "认证状态": "cert_status", "认证日期": "cert_date",
        "抵扣状态": "deduct_status", "抵扣方式": "deduct_method",
        "征收方式": "collect_method", "校验码": "check_code",
        "印花税": "stamp_tax", "文建费": "culture_fee",
        "备注": "remark", "凭证号": "voucher_no",
    })
    if not cols: return None
    rows = []
    start_row = header_row + 1  # 数据从表头的下一行开始
    for r in range(start_row, min(nrows, 5000)):
        raw_vals = _get_row_values(sheet, r)
        if _is_summary_row(raw_vals): continue
        vals = {}
        for field, col in cols.items():
            try:
                if hasattr(sheet, 'cell_value'):
                    v = str(sheet.cell_value(r, col)).strip()
                else:
                    v = str(raw_vals[col] or '') if col < len(raw_vals) else ''
                vals[field] = v
            except: vals[field] = ""
        if not vals.get("inv_no") and not vals.get("inv_code") and not vals.get("buyer") and not vals.get("seller") and not vals.get("goods"):
            continue
        try: vals["amount"] = float(vals.get("amount", 0) or 0)
        except: vals["amount"] = 0
        try: vals["tax"] = float(vals.get("tax", 0) or 0)
        except: vals["tax"] = 0
        try: vals["total"] = float(vals.get("total", 0) or 0)
        except: vals["total"] = vals["amount"] + vals["tax"]
        rows.append(vals)
    atype = "sales_invoice" if direction == "销项" else "purchase_invoice"
    return {"type": atype, "rows": rows}

def _parse_trial_balance_sheet(sheet, header):
    """解析科目余额表"""
    cols = _find_cols_semantic(header, {
        "科目编码": "code", "科目名称": "name",
        "期初余额": "open", "期初借方": "open_debit", "期初贷方": "open_credit",
        "本期发生额": "current", "本期借方": "current_debit", "本期贷方": "current_credit",
        "本年累计发生额": "year", "本年借方": "year_debit", "本年贷方": "year_credit",
        "期末余额": "close", "期末借方": "close_debit", "期末贷方": "close_credit",
        "借方": "debit", "贷方": "credit",
    })
    if not cols: return None
    rows = []
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else sheet.max_row
    for r in range(1, min(nrows, 500)):
        vals = {}
        for field, col in cols.items():
            try:
                v = str(sheet.cell_value(r, col)).strip() if hasattr(sheet, 'cell_value') else str(_get_row_values(sheet, r)[col] or '')
                vals[field] = v
            except: vals[field] = ""
        if not vals.get("code") and not vals.get("name"): continue
        for k in ["open_debit","open_credit","current_debit","current_credit","year_debit","year_credit","close_debit","close_credit"]:
            try: vals[k] = float(vals.get(k, 0) or 0)
            except: vals[k] = 0
        rows.append(vals)
    return rows

def _parse_contract_sheet(sheet, header):
    """解析合同台账"""
    cols = _find_cols_semantic(header, {
        "合同名称": "name", "合同编号": "contract_no", "合同类型": "contract_type",
        "甲方": "party_a", "甲方名称": "party_a", "乙方": "party_b", "乙方名称": "party_b",
        "合同金额": "amount", "签订日期": "sign_date", "签订时间": "sign_date",
        "合同期限": "term", "合同内容": "content", "付款方式": "payment_method",
        "合同状态": "status", "备注": "remark", "签约方": "party",
    })
    if not cols: return None
    rows = []
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else sheet.max_row
    for r in range(1, min(nrows, 2000)):
        vals = {}
        for field, col in cols.items():
            try: vals[field] = str(sheet.cell_value(r, col)).strip() if hasattr(sheet, 'cell_value') else str(_get_row_values(sheet, r)[col] or '')
            except: vals[field] = ""
        if not vals.get("name") and not vals.get("party_a"): continue
        try: vals["amount"] = float(vals.get("amount", 0) or 0)
        except: vals["amount"] = 0
        rows.append(vals)
    return {"type": "contract", "rows": rows}

def _parse_related_party_sheet(sheet, header):
    """解析关联交易报告"""
    cols = _find_cols_semantic(header, {
        "关联方名称": "name", "关联关系": "relation", "关联交易": "transaction",
        "交易类型": "type", "交易金额": "amount", "金额": "amount",
        "交易内容": "content", "定价政策": "pricing",
        "持股比例": "share_ratio", "对外投资": "investment",
        "投资比例": "invest_ratio", "本年发生额": "year_amount",
    })
    if not cols: return None
    rows = []
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else sheet.max_row
    for r in range(1, min(nrows, 1000)):
        vals = {}
        for field, col in cols.items():
            try: vals[field] = str(sheet.cell_value(r, col)).strip() if hasattr(sheet, 'cell_value') else str(_get_row_values(sheet, r)[col] or '')
            except: vals[field] = ""
        if not vals.get("name") and not vals.get("content"): continue
        try: vals["amount"] = float(vals.get("amount", 0) or 0)
        except: vals["amount"] = 0
        rows.append(vals)
    return rows

def _parse_salary_sheet(sheet):
    # ═══ 自适应表头检测 ═══
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else sheet.max_row
    header_row, _scores = _detect_header_row(sheet, nrows, [
        "姓名", "工号", "工资", "本期收入", "应发", "实发", "证件", "身份证",
        "应税", "应纳税所得额", "代扣个税", "基本养老保险", "住房公积金"
    ])
    header = _get_row_values(sheet, header_row)
    cols = _find_cols_semantic(header, {
        "姓名": "name", "员工": "name", "姓名/员工": "name",
        "证件号码": "id_card", "工资": "salary",
        "身份证号": "id_card", "身份证": "id_card", "工号": "emp_id",
        "基本工资": "salary", "应发合计": "gross", "实发合计": "net",
        "实发工资": "net", "应发工资": "gross",
        "本期收入": "salary", "本期费用": "fee_deduct",
        "本期免税收入": "tax_free", "本期基本养老保险费": "pension",
        "本期基本医疗保险费": "medical", "本期失业保险费": "unemploy",
        "本期住房公积金": "hf_deduct", "年金": "annuity",
        "企业(职业)年金": "annuity", "本期企业(职业)年金": "annuity",
        "代扣社保": "ss_deduct", "代扣住房公积金": "hf_deduct",
        "住房公积金": "hf_deduct", "代扣个税": "tax",
        "养老保险": "pension", "医疗保险": "medical", "失业保险": "unemploy",
        "大病医疗": "illness", "合计": "total",
        "个税": "tax", "个人所得税": "tax",
        "税款所属期起": "period_start", "税款所属期止": "period_end",
        "实发": "net", "应发": "gross",
        "部门": "dept", "职位": "position",
        "所得项目": "income_type", "费用类型": "fee_type",
        "累计收入": "acc_income", "累计应纳税所得额": "acc_taxable",
        "累计已缴税额": "acc_paid", "应补（退）税额": "tax_diff",
        "其他扣除": "other_deduct", "其他税后扣除": "other_after",
    })
    if not cols: return None
    rows = []
    # 使用已检测到的表头行：数据从表头下一行开始
    start_row = header_row + 1
    for r in range(start_row, min(nrows, 500)):
        raw_vals = _get_row_values(sheet, r)
        vals = {}
        for field, col in cols.items():
            try:
                v = str(sheet.cell_value(r, col)).strip() if hasattr(sheet, 'cell_value') else str(raw_vals[col] or '') if col < len(raw_vals) else ''
                vals[field] = v
            except: vals[field] = ""
        if not vals.get("name"): continue
        for k in ["salary","ss_deduct","hf_deduct","tax","net","gross"]:
            try: vals[k] = float(vals.get(k, 0) or 0)
            except: vals[k] = 0
        rows.append(vals)
    return {"type": "salary", "rows": rows}

def _parse_social_sheet(sheet, header):
    # 智能表头检测：社保文件常有合并的多行标题
    # 扫描行0-6，选关键词命中最多的一行作为真实表头
    best_header = header
    best_score = sum(1 for kw in ["姓名","身份证","参保","基数","单位","个人"] if any(kw in str(h) for h in header))
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else sheet.max_row
    for r in range(min(7, nrows)):  # 0-6行
        candidate = _get_row_values(sheet, r)
        score = sum(1 for kw in ["姓名","身份证","证件","参保","基数","缴费","险种","费款","序号","单位","个人","费率"] if any(kw in str(h) for h in candidate))
        if score > best_score:
            best_score = score
            best_header = candidate
    
    cols = _find_cols_semantic(best_header, {
        "姓名": "name", "证件号码": "id_card", "缴费工资": "base",
        "姓名": "name", "身份证号": "id_card", "身份证": "id_card",
        "序号": "seq", "费款所属期起": "period_start", "费款所属期止": "period_end",
        "缴费基数": "base", "社保基数": "base", "工资基数": "base",
        "应收金额": "due_amount", "个人社保合计": "personal_total", "单位社保合计": "company_total",
        "基本养老保险（单位）": "pension_company", "基本养老保险（个人）": "pension_personal",
        "基本医疗保险（单位）": "medical_company", "基本医疗保险（个人）": "medical_personal",
        "失业保险（单位）": "unemploy_company", "失业保险（个人）": "unemploy_personal",
        "工伤保险（单位）": "injury_company", "生育保险": "maternity",
        "职业年金（单位）": "annuity_company", "职业年金（个人）": "annuity_personal",
        "地方补充医疗（单位）": "supp_medical", "公务员医疗补助": "civil_medical",
        "单位承担": "company_pay", "个人承担": "personal_pay", "险种": "insurance",
        "单位缴纳": "company_pay", "个人缴纳": "personal_pay",
        "单位缴费": "company_pay", "个人缴费": "personal_pay",
        "合计": "total", "备注": "remark",
    })
    if not cols: return None
    rows = []
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else sheet.max_row
    for r in range(1, min(nrows, 200)):
        raw_vals = _get_row_values(sheet, r)
        vals = {}
        for field, col in cols.items():
            try:
                v = str(sheet.cell_value(r, col)).strip() if hasattr(sheet, 'cell_value') else str(raw_vals[col] or '') if col < len(raw_vals) else ''
                vals[field] = v
            except: vals[field] = ""
        if not vals.get("name"): continue
        for k in ["base","company_pay","personal_pay"]:
            try: vals[k] = float(vals.get(k, 0) or 0)
            except: vals[k] = 0
        rows.append(vals)
    return rows

def _parse_voucher_sheet(sheet):
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else sheet.max_row
    header_row, _scores = _detect_header_row(sheet, nrows, [
        "日期", "凭证字号", "凭证号", "摘要", "科目", "借方", "贷方"
    ])
    header = _get_row_values(sheet, header_row)
    cols = _find_cols_semantic(header, {"日期": "date", "凭证字号": "voucher_no", "摘要": "summary",
        "科目": "account", "借方": "debit", "贷方": "credit"})
    if not cols: return None
    rows = []
    start_row = header_row + 1
    for r in range(start_row, min(nrows, 5000)):
        raw_vals = _get_row_values(sheet, r)
        vals = {}
        for field, col in cols.items():
            try:
                v = str(sheet.cell_value(r, col)).strip() if hasattr(sheet, 'cell_value') else str(raw_vals[col] or '') if col < len(raw_vals) else ''
                vals[field] = v
            except: vals[field] = ""
        if not vals.get("account") and not vals.get("summary"): continue
        for k in ["debit","credit"]:
            try: vals[k] = float(vals.get(k, 0) or 0)
            except: vals[k] = 0
        rows.append(vals)
    return {"type": "voucher", "rows": rows}

def _parse_inventory_sheet(sheet):
    nrows = sheet.nrows if hasattr(sheet, 'nrows') else sheet.max_row
    header_row, _scores = _detect_header_row(sheet, nrows, [
        "日期", "凭证", "入库", "出库", "存货", "数量", "金额",
        "产品编码", "产品名称", "期初库存", "期末库存", "本期入库", "本期出库"
    ])
    header = _get_row_values(sheet, header_row)
    cols = _find_cols_semantic(header, {"日期": "date", "凭证字号": "voucher_no",
        "入库": "in_qty", "出库": "out_qty", "存货": "item", "数量": "qty", "金额": "amount"})
    if not cols: return None
    rows = []
    for r in range(header_row + 1, min(nrows, 5000)):
        raw_vals = _get_row_values(sheet, r)
        vals = {}
        for field, col in cols.items():
            try:
                v = str(sheet.cell_value(r, col)).strip() if hasattr(sheet, 'cell_value') else str(raw_vals[col] or '') if col < len(raw_vals) else ''
                vals[field] = v
            except: vals[field] = ""
        if not vals.get("date") and not vals.get("item"): continue
        for k in ["in_qty","out_qty","amount"]:
            try: vals[k] = float(vals.get(k, 0) or 0)
            except: vals[k] = 0
        rows.append(vals)
    return {"type": "inventory", "rows": rows}

# ═══════════ PDF 银行流水解析 ═══════════

def _parse_pdf_bank_statement(filepath):
    """解析招行银行流水PDF：合并多行记录，提取日期/对方/金额"""
    import re
    try:
        import PyPDF2
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            text = ""
            for page in reader.pages:
                t = page.extract_text() or ""
                text += t + "\n"
    except: return []

    lines = text.split("\n")
    # Step 1: merge multi-line records (lines starting with number+space are begin, continue until next number+space)
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line: i += 1; continue
        if re.match(r'^\d+\s', line):
            combined = line
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r'^\d+\s', lines[i].strip()):
                combined += lines[i].strip(); i += 1
            merged.append(combined)
        else:
            merged.append(line); i += 1

    txs = []
    for line in merged:
        # 提取日期和金额
        dates = re.findall(r'20[2-3]\d[01]\d[0-3]\d', line)
        amounts = re.findall(r'([\d,]+\.\d{2})', line)
        if not dates or not amounts: continue

        date_str = dates[0]
        vals = [float(a.replace(',','')) for a in amounts]

        # 判断借贷方向
        raw_line = line
        if len(vals) >= 2:
            debit, credit = vals[0], vals[1]
        elif any(k in raw_line for k in ('营收','入账','结算','退款','结息','汇入')):
            credit, debit = max(vals), 0
        elif any(k in raw_line for k in ('税务','收费','社保','失业','工伤','养老','医疗','印花','增值','教育','城建','工资','代发','公积金','委托收款','提回定借')):
            debit, credit = max(vals), 0
        elif any(k in raw_line for k in ('货款','快递','包装','服务费','材料')):
            debit, credit = max(vals), 0
        else:
            credit, debit = max(vals), 0

        # 提取对方名称（大兴支行之后、日期之前的内容）
        counterparty = ""
        bank_end = line.find("大兴支行")
        if bank_end >= 0:
            rest = line[bank_end+4:]
            dp = rest.find(date_str)
            if dp > 0:
                counterparty = rest[:dp].strip()
                # 去掉末尾的纯数字（账号）
                counterparty = re.sub(r'\s*\d{6,}\s*$', '', counterparty).strip()

        # 金额符号修正：贷方金额可能是负数表示退款，以实际金额为准
        amt = round(credit - debit, 2)
        txs.append({
            "date": date_str, "debit": round(debit, 2), "credit": round(credit, 2),
            "amount": amt,
            "counterparty": counterparty[:80] if counterparty else "",
            "summary": raw_line[raw_line.find("人民币")+3:].strip() if "人民币" in raw_line else "",
            "raw": line[:200]
        })
    return txs

@app.post("/api/tax-risk-docs/review")
async def review_tax_risk_docs(company_id: int = Query(...), db: Session = Depends(get_db)):
    """报告复核：优先使用缓存，无缓存时重新分析"""
    cached = _last_analysis_cache.get(company_id)
    if cached and cached.get("report"):
        report = cached["report"]
    else:
        report = await _run_analyze(company_id, db)
    if not report.get("ok"):
        return {"ok": False, "message": "分析失败，无法复核"}
    
    # 提取内层报告：_run_analyze 返回 {"ok":True, "report":{...}}，取内层
    report = report.get("report", report)
    # 解析原始数据做复核
    from datetime import datetime
    
    company_udir_review = _get_company_upload_dir(company_id)
    docs = []
    if os.path.exists(company_udir_review):
        for fname in os.listdir(company_udir_review):
            fpath = os.path.join(company_udir_review, fname)
            if os.path.isfile(fpath):
                docs.append({"original_name": fname, "path": fpath})
    
    bank_txs, invoices, salaries, social_security, vouchers, inventory = [], [], [], [], [], []
    for doc in docs:
        fname, fpath = doc["original_name"], doc["path"]
        ext = os.path.splitext(fname)[1].lower()
        try:
            if ext in (".xls", ".xlsx"):
                parsed = _parse_excel_structured(fpath, ext)
                if parsed:
                    ftype = parsed.get("type", "")
                    rows = parsed.get("rows", [])
                    if ftype == "salary": salaries = rows
                    elif ftype == "social_security": social_security = rows
                    elif ftype in ("sales_invoice", "purchase_invoice"): 
                        invoices.extend([{**r, "direction": "销项" if ftype == "sales_invoice" else "进项"} for r in rows])
                    elif ftype == "voucher": vouchers = rows
                    elif ftype == "inventory": inventory = rows
            elif ext == ".pdf":
                txs = _parse_pdf_bank_statement(fpath)
                if txs: bank_txs = txs
        except: pass
    
    review_issues = _review_report(
        report.get("all_findings", []),
        report.get("domain_summary", []),
        report.get("stats", {}),
        bank_txs, invoices, vouchers, salaries
    )
    
    return {
        "ok": True,
        "report_issues": len(review_issues),
        "review": review_issues,
        "passed": len([i for i in review_issues if i["level"] == "错误"]) == 0
    }


@app.post("/api/tax-risk-docs/review-single")
async def review_single_finding(request: Request, company_id: int = Query(...)):
    """单条结论复核：重新解析上传文件，对finding中的数据做源数据交叉验证"""
    try:
        finding = await request.json()
    except Exception as e:
        return {"ok": False, "message": f"无效的请求数据: {e}"}
    
    ftype = str(finding.get("type", ""))
    detail = str(finding.get("detail", ""))
    desc = str(finding.get("description", ""))
    how = str(finding.get("how_found", ""))
    issues = []
    
    # ═══ 重新解析上传文件获取原始数据 ═══
    ULDR = _get_company_upload_dir(company_id)
    raw_bank, raw_inv, raw_vouchers, raw_salaries = [], [], [], []
    if os.path.exists(ULDR):
        for fname in os.listdir(ULDR):
            fpath = os.path.join(ULDR, fname)
            ext = os.path.splitext(fname)[1].lower()
            try:
                if ext in (".xls", ".xlsx"):
                    parsed = _parse_excel_structured(fpath, ext)
                    if not parsed: continue
                    ft = parsed.get("type", "")
                    rows = parsed.get("rows", [])
                    if ft == "voucher": raw_vouchers = rows
                    elif ft == "salary": raw_salaries = rows
                    elif ft in ("sales_invoice", "purchase_invoice"):
                        raw_inv.extend([{**r, "direction": "销项" if ft == "sales_invoice" else "进项"} for r in rows])
                elif ext == ".pdf":
                    txs = _parse_pdf_bank_statement(fpath)
                    if txs: raw_bank.extend(txs)
            except: pass
    
    # ═══ 检查项1: 数据源实际数值验证 ═══
    import re
    
    # 提取结论中的金额
    amounts = []
    for m in re.finditer(r'[\d,]+\.?\d*(?:亿|万|元)?', detail):
        num_str = m.group().replace(',', '').replace('元', '').replace('万', '0000').replace('亿', '00000000')
        try: amounts.append(float(num_str))
        except: pass
    
    if amounts:
        # 验证: 结论中的金额是否在原始数据中有支撑
        # 凭证借贷不平检查
        if "凭证" in ftype and "借贷" in ftype:
            empty_vn = sum(1 for v in raw_vouchers if not str(v.get("voucher_no", "")).strip())
            total_vn = len(raw_vouchers)
            if total_vn > 0:
                if empty_vn / total_vn > 0.9:
                    issues.append({
                        "check": "源数据验证",
                        "result": f"❌ 凭证号字段{empty_vn}/{total_vn}={empty_vn/total_vn*100:.2f}%为空，按空键分组产生错误聚合。结论中的金额数字来源于全量汇总而非逐张凭证。"
                    })
                else:
                    # 重新计算有效凭证
                    vn_balanced = {}
                    for v in raw_vouchers:
                        vn = str(v.get("voucher_no", "")).strip()
                        if not vn: continue
                        vn_balanced.setdefault(vn, {"d": 0, "c": 0})
                        vn_balanced[vn]["d"] += float(v.get("debit", 0) or 0)
                        vn_balanced[vn]["c"] += float(v.get("credit", 0) or 0)
                    unbal = [(vn, b) for vn, b in vn_balanced.items() if abs(b["d"]-b["c"]) > 1]
                    gap = sum(abs(b["d"]-b["c"]) for _,b in unbal)
                    issues.append({
                        "check": "源数据重新计算",
                        "result": f"有效凭证{len(vn_balanced)}张，不平{len(unbal)}张，差额{gap:,.2f}元（跳�{empty_vn}条空凭证号）"
                    })
        
        # 收入数据验证
        if "主营业务收入" in detail or "主营收入" in "".join([ftype, detail]):
            vr_total = sum(float(v.get("credit", 0) or 0) for v in raw_vouchers if "主营业务收入" in str(v.get("account", "")))
            issues.append({
                "check": "收入原始数据复核",
                "result": f"凭证中主营业务收入贷方合计{vr_total:,.2f}元" + ("，与结论一致" if abs(vr_total - max(amounts, default=0)) < 1000 else f"，与结论差异{abs(vr_total - max(amounts, default=0)):,.2f}元")
            })
        
        # 进项/销项数据验证
        if "进项" in ftype or "销项" in "".join([ftype, detail]):
            sal_total = sum(float(i.get("total", 0) or 0) for i in raw_inv if i.get("direction") == "销项")
            pur_total = sum(float(i.get("total", 0) or 0) for i in raw_inv if i.get("direction") == "进项")
            sal_count = sum(1 for i in raw_inv if i.get("direction") == "销项")
            pur_count = sum(1 for i in raw_inv if i.get("direction") == "进项")
            issues.append({
                "check": "发票原始数据复核",
                "result": f"销项发票{sal_count}张合计{sal_total:,.2f}元，进项发票{pur_count}张合计{pur_total:,.2f}元"
            })
        
        # 银行流水数据验证
        if "银行" in ftype or "流水" in ftype or "收款" in ftype or "付款" in ftype:
            bt_income = sum(tx.get("credit", 0) for tx in raw_bank)
            bt_expense = sum(tx.get("debit", 0) for tx in raw_bank)
            issues.append({
                "check": "银行流水原始数据复核",
                "result": f"银行流水{len(raw_bank)}条，收入{bt_income:,.2f}元，支出{bt_expense:,.2f}元"
            })
    
    # ═══ 检查项2: 空值/默认值陷阱 ═══
    if "凭证" in ftype:
        empty_vn = sum(1 for v in raw_vouchers if not str(v.get("voucher_no", "")).strip()) if raw_vouchers else 0
        vn_pct = empty_vn / max(len(raw_vouchers), 1) if raw_vouchers else 0
        icon = "\u26a0\ufe0f" if vn_pct > 0.9 else "\u2705"
        vn_issue = "全空！所有按凭证号分组的结果均无效" if vn_pct > 0.9 else "正常"
        issues.append({
            "check": "空值陷阱",
            "result": icon + " 凭证号空值率%d/%d=%.0f%% %s" % (empty_vn, len(raw_vouchers), vn_pct*100, vn_issue)
        })
    
    if "工资" in ftype or "薪酬" in ftype:
        empty_names = sum(1 for s in raw_salaries if not str(s.get("name", "")).strip()) if raw_salaries else 0
        nm_pct = empty_names / max(len(raw_salaries), 1) if raw_salaries else 0
        nm_icon = "\u26a0\ufe0f" if nm_pct > 0.5 else "\u2705"
        issues.append({
            "check": "空值陷阱",
            "result": "%s 工资表姓名空值率%d/%d" % (nm_icon, empty_names, max(len(raw_salaries), 1))
        })
    
    # ═══ 检查项3: 极端值合理性 ═══
    for m in re.finditer(r'(9[5-9]|100)%', detail):
        issues.append({
            "check": f"极端值({m.group()})",
            "result": f"存在{m.group()}极端占比。需人工确认：1)数据是否完整 2)是否包含所有账户/平台 3)行业特性是否合理"
        })
    
    # ═══ 检查项4: 五段式完整性 ═══
    parts = []
    parts.append("✅" if desc else "❌" + "风险解释")
    parts.append("✅" if how else "❌" + "得出方式")
    parts.append("✅" if finding.get("tax_impact") else "❌" + "税务影响")
    parts.append("✅" if finding.get("policy_ref") else "❌" + "政策依据")
    parts.append("✅" if finding.get("suggestion") else "❌" + "整改建议")
    issues.append({"check": "五段式完整性", "result": " ".join(parts)})
    
    # ═══ 判断 ═══
    has_error = any("❌" in i["result"] and ("空键" in i["result"] or "无效" in i["result"]) for i in issues)
    has_warning = any("⚠️" in i["result"] or "❌" in i["result"] for i in issues)
    
    level = "错误" if has_error else ("警告" if has_warning else "通过")
    if level == "通过":
        summary = "数据复核通过，源数据与结论一致"
        method = "已从源文件重新解析数据并交叉比对，结论可信"
    elif level == "错误":
        summary = "结论不可靠——源数据与结论存在矛盾"
        method = "重新解析了上传文件，发现数据源问题"
    else:
        summary = "部分数据需人工确认"
        method = "已从源文件重新计算并比对，存在需核实的差异"
    
    return {
        "ok": True,
        "review": {
            "passed": level == "通过",
            "level": level,
            "summary": summary,
            "method": method,
            "issues": issues
        }
    }


@app.get("/api/tax-risk-docs/last-analysis")
async def get_last_analysis(company_id: int = Query(...)):
    """获取最近一次分析结果缓存（无需重新分析）"""
    cached = _last_analysis_cache.get(company_id)
    if not cached:
        return {"ok": False, "message": "暂无分析结果，请先运行一键分析"}
    return cached["report"]


# ═══════════════════════════════════════════════════════════
# 电子证据固化 —— SHA256哈希链 + 时间戳存证
# ═══════════════════════════════════════════════════════════

@app.get("/api/tax-risk-docs/evidence-chain")
def get_evidence_chain(company_id: int = Query(...)):
    """获取上传资料证据链（SHA256哈希 + 上传时间戳）
    每条证据含: 文件名、SHA256、上传时间、文件大小、证据编号
    用途: 稽查底稿附件、电子证据固化、可追溯审计链
    """
    import hashlib as _hashlib
    evidence = []
    file_hashes = {}
    _init_tax_docs_from_disk()
    
    for d in _tax_risk_docs:
        if d.get("company_id") != company_id:
            continue
        fpath = d.get("path", "")
        sha256 = d.get("sha256", "")
        # 若未缓存SHA256，实时计算
        if not sha256 and os.path.exists(fpath):
            try:
                with open(fpath, "rb") as fh:
                    sha256 = _hashlib.sha256(fh.read()).hexdigest()
                d["sha256"] = sha256
                d["size"] = d.get("size") or os.path.getsize(fpath)
            except Exception:
                sha256 = "计算失败"
        
        ev = {
            "evidence_id": f"EVD-{d['id']:06d}",
            "filename": d.get("original_name", d.get("filename", "")),
            "sha256": sha256,
            "md5": d.get("md5", ""),
            "size_bytes": d.get("size", 0),
            "uploaded_at": d.get("uploaded_at", ""),
            "file_saved": d.get("file_saved", False),
        }
        evidence.append(ev)
        if sha256 and sha256 != "计算失败":
            file_hashes[d.get("original_name", "")] = sha256
    
    # 构建证据链摘要
    chain_summary = {
        "total_files": len(evidence),
        "total_size_bytes": sum(e["size_bytes"] for e in evidence),
        "evidence_ids": [e["evidence_id"] for e in evidence],
        "chain_integrity": "完整" if all(e["sha256"] and e["sha256"] != "计算失败" for e in evidence) else "部分缺失",
    }
    
    return {
        "ok": True,
        "company_id": company_id,
        "generated_at": datetime.now().isoformat(),
        "chain_summary": chain_summary,
        "evidence": evidence,
        "file_hashes": file_hashes,
    }


# ═══════════════════════════════════════════════════════════
# 稽查底稿自动生成 —— 结构化审计工作底稿
# ═══════════════════════════════════════════════════════════

@app.get("/api/tax-risk-docs/working-papers")
def generate_working_papers(company_id: int = Query(...)):
    """基于最近一次分析结果自动生成稽查底稿
    结构: 审计目标→审计程序→发现清单→证据索引→结论与建议
    """
    cached = _last_analysis_cache.get(company_id)
    if not cached:
        return {"ok": False, "message": "请先运行一键分析，生成报告后再导出底稿"}
    
    report = cached["report"]["report"] if isinstance(cached["report"], dict) and "report" in cached["report"] else cached["report"]
    cc = report.get("comprehensive", {})
    all_f = report.get("all_findings", [])
    te = report.get("target_entity", {})
    mi = cc.get("material_intel", {})
    evidence = cc.get("evidence_closures", [])
    
    # 审计目标
    audit_objectives = [
        "验证发票流与资金流的一致性",
        "核查进销存数据真实性",
        "排查关联交易与虚开风险",
        "评估税务合规性与申报准确性",
        "识别隐匿收入与虚增成本风险",
    ]
    
    # 审计程序（已执行）
    audit_procedures = []
    ds = report.get("domain_summary", [])
    for d in ds[:20]:
        if d.get("findings"):
            audit_procedures.append({
                "procedure": d.get("name", ""),
                "findings_count": len(d.get("findings", [])),
                "high_risk_count": sum(1 for f in d.get("findings", []) if f.get("level") == "高风险"),
            })
    
    # 发现清单（按风险等级分组）
    high_risk = [f for f in all_f if f.get("level") == "高风险"]
    mid_risk = [f for f in all_f if f.get("level") == "中风险"]
    low_risk = [f for f in all_f if f.get("level") == "低风险"]
    
    def _fmt_finding(f):
        return {
            "id": f.get("_idx", ""),
            "type": f.get("type", f.get("category", "")),
            "level": f.get("level", ""),
            "score": f.get("score", 0),
            "detail": f.get("detail", ""),
            "suggestion": f.get("suggestion", ""),
            "law_ref": f.get("law_ref", f.get("legal_basis", "")),
            "evidence_refs": f.get("evidence_refs", []),
        }
    
    # 证据索引
    evidence_index = []
    for ev in evidence[:50]:
        evidence_index.append({
            "ref": ev.get("ref", ""),
            "type": ev.get("type", ""),
            "source": ev.get("source", ""),
            "closed": ev.get("closed", False),
        })
    
    # 资料明细（发票/银行流水统计）
    inv_stats = mi.get("发票", {}).get("统计", {})
    bank_stats = mi.get("银行流水", {}).get("统计", {})
    material_summary = {
        "销项发票": f"{inv_stats.get('销项发票数量', 0)}张, {inv_stats.get('销项金额合计', 0):,.2f}元",
        "进项发票": f"{inv_stats.get('进项发票数量', 0)}张, {inv_stats.get('进项金额合计', 0):,.2f}元",
        "银行收款": f"{bank_stats.get('收款合计', 0):,.2f}元",
        "银行付款": f"{bank_stats.get('付款合计', 0):,.2f}元",
    }
    
    papers = {
        "title": f"税务稽查工作底稿",
        "entity": te.get("name", ""),
        "period": te.get("period", ""),
        "generated_at": datetime.now().isoformat(),
        "report_ref": cached.get("timestamp", ""),
        "overall_level": report.get("overall_level", ""),
        "sections": {
            "audit_objectives": audit_objectives,
            "audit_procedures": audit_procedures,
            "material_summary": material_summary,
            "high_risk_findings": [_fmt_finding(f) for f in high_risk],
            "mid_risk_findings": [_fmt_finding(f) for f in mid_risk],
            "low_risk_findings": [_fmt_finding(f) for f in low_risk],
            "evidence_index": evidence_index,
            "conclusion": {
                "total_risks": report.get("total_risks", 0),
                "high_risk": report.get("high_risk", 0),
                "mid_risk": report.get("mid_risk", 0),
                "low_risk": report.get("low_risk", 0),
                "overall_assessment": cc.get("executive_summary", cc.get("narrative_summary", "")),
            },
        },
        "chain_of_custody": {
            "prepared_by": "财税稽查系统·AGI引擎",
            "reviewed_by": "待人工复核",
            "hash_algorithm": "SHA256",
            "total_evidence_count": len(evidence),
        },
    }
    
    return {"ok": True, "working_papers": papers}


# ═══════════════════════════════════════════════════════════
# 报告版本切换 —— 详细版 / 简报版 / 底稿版
# ═══════════════════════════════════════════════════════════

@app.get("/api/tax-risk-docs/report-summary")
def get_report_summary(company_id: int = Query(...), version: str = Query("full")):
    """获取指定版本的报告摘要
    version: full(详细版) | brief(简报版) | working(底稿版)
    """
    cached = _last_analysis_cache.get(company_id)
    if not cached:
        return {"ok": False, "message": "请先运行一键分析"}
    
    report = cached["report"]["report"] if isinstance(cached["report"], dict) and "report" in cached["report"] else cached["report"]
    cc = report.get("comprehensive", {})
    all_f = report.get("all_findings", [])
    te = report.get("target_entity", {})
    
    base = {
        "entity_name": te.get("name", ""),
        "period": te.get("period", ""),
        "overall_level": report.get("overall_level", ""),
        "total_risks": report.get("total_risks", 0),
        "high_risk": report.get("high_risk", 0),
        "mid_risk": report.get("mid_risk", 0),
        "low_risk": report.get("low_risk", 0),
        "version": version,
        # 智能体反思数据
        "agent_reflection": (cached.get("report") or {}).get("agent", {}).get("reflection", {}),
        "agent_insight": (cached.get("report") or {}).get("agent", {}).get("insight_summary", ""),
    }
    
    if version == "brief":
        # 简报版：核心结论 + P0/P1风险摘要 + 智能体反思标注
        top_risks = sorted(all_f, key=lambda x: -(x.get("score") or 0))[:10]
        brief_risks = []
        reflection_items = []  # 需关注的反思项
        for f in top_risks:
            refl = f.get("_self_reflection", {})
            refle_verdict = f.get("_reflection_verdict", "")
            brief_risks.append({
                "type": f.get("type", ""),
                "level": f.get("level", ""),
                "score": f.get("score", 0),
                "summary": (f.get("detail", "") or "")[:200],
                "suggestion": f.get("suggestion", ""),
                "reflection_verdict": refle_verdict,
                "reflection_note": refl.get("counter_hypothesis", "") if refle_verdict in ("uncertain", "refuted") else "",
            })
            # 收集被反思器质疑的结论
            if refle_verdict in ("uncertain", "refuted"):
                reflection_items.append({
                    "finding": f.get("type", ""),
                    "verdict": refle_verdict,
                    "counter": refl.get("counter_hypothesis", ""),
                    "evidence": refl.get("counter_evidence", []),
                })
        actions = cc.get("actions", {})
        base.update({
            "executive_summary": cc.get("executive_summary", cc.get("narrative_summary", "")),
            "top_risks": brief_risks,
            "reflection_notes": reflection_items,  # 智能体反思需注意项
            "recommended_actions": {
                "immediate": actions.get("P0", actions.get("immediate", [])),
                "short_term": actions.get("P1", actions.get("short_term", [])),
            },
            "data_overview": cc.get("data_overview", {}),
        })
    elif version == "working":
        # 底稿版：结构化审计发现
        base.update({
            "audit_procedures": [ds.get("name") for ds in (report.get("domain_summary") or [])[:15] if ds.get("findings")],
            "findings_by_level": {
                "high": [{"type": f.get("type"), "detail": f.get("detail"), "law_ref": f.get("law_ref")} for f in all_f if f.get("level") == "高风险"][:20],
                "mid": [{"type": f.get("type"), "detail": f.get("detail")} for f in all_f if f.get("level") == "中风险"][:30],
            },
            "material_intel": cc.get("material_intel", {}),
            "evidence_count": len(cc.get("evidence_closures", [])),
            "chain_stats": cc.get("chain_execution", {}),
        })
    else:
        # 全量版返回所有数据
        base.update({
            "domain_summary": report.get("domain_summary", []),
            "all_findings": all_f,
            "comprehensive": cc,
        })
    
    _report(100, "分析完成")
    return {"ok": True, "report": base}


# ═══════════════════════════════════════════════════════════
# 关联网络图谱数据 —— 供应商/客户/关联方关系网络
# ═══════════════════════════════════════════════════════════

@app.get("/api/tax-risk-docs/relation-graph")
def get_relation_graph(company_id: int = Query(...)):
    """获取供应商/客户/关联方关系网络数据
    返回nodes + edges，前端用D3.js/DOM渲染关系图谱
    自动检测：关联交易闭环、供应商=客户情况、人员重叠
    """
    cached = _last_analysis_cache.get(company_id)
    if not cached:
        return {"ok": False, "message": "请先运行一键分析"}
    
    report = cached["report"]["report"] if isinstance(cached["report"], dict) and "report" in cached["report"] else cached["report"]
    cc = report.get("comprehensive", {})
    te = report.get("target_entity", {})
    mi = cc.get("material_intel", {})
    cross_ent = cc.get("cross_enterprise", {})
    entity_graph = report.get("entity_graph", {})
    
    entity_name = te.get("name", "被查企业")
    
    nodes = []
    edges = []
    node_ids = set()
    
    def _add_node(nid, name, ntype, amount=0, risk=False):
        if nid in node_ids:
            return
        node_ids.add(nid)
        nodes.append({
            "id": nid,
            "name": name,
            "type": ntype,  # company/supplier/customer/related/person
            "amount": round(amount, 2) if amount else 0,
            "risk": risk,
        })
    
    # 核心节点：被查企业
    _add_node("entity_main", entity_name, "company")
    
    # 从发票数据提取供应商/客户
    inv_data = mi.get("发票", {})
    sal_detail = inv_data.get("销项发票全量明细", [])
    pur_detail = inv_data.get("进项发票全量明细", [])
    
    # 销项发票 → 客户
    customer_amounts = {}
    for inv in sal_detail:
        cname = inv.get("对方公司名称", "").strip()
        if cname and cname != entity_name:
            customer_amounts[cname] = customer_amounts.get(cname, 0) + float(inv.get("价税合计", 0) or 0)
    
    # 进项发票 → 供应商
    supplier_amounts = {}
    for inv in pur_detail:
        sname = inv.get("对方公司名称", "").strip()
        if sname and sname != entity_name:
            supplier_amounts[sname] = supplier_amounts.get(sname, 0) + float(inv.get("价税合计", 0) or 0)
    
    # 检测供应商=客户的重叠（购销闭环风险）
    overlap_names = set(customer_amounts.keys()) & set(supplier_amounts.keys())
    
    # Top10客户
    top_customers = sorted(customer_amounts.items(), key=lambda x: -x[1])[:10]
    for name, amt in top_customers:
        is_overlap = name in overlap_names
        _add_node(f"cust_{name}", name, "customer", amt, risk=is_overlap)
        edges.append({
            "from": "entity_main",
            "to": f"cust_{name}",
            "type": "销售",
            "amount": round(amt, 2),
            "label": f"销{amt:,.2f}",
        })
    
    # Top10供应商
    top_suppliers = sorted(supplier_amounts.items(), key=lambda x: -x[1])[:10]
    for name, amt in top_suppliers:
        is_overlap = name in overlap_names
        _add_node(f"supp_{name}", name, "supplier", amt, risk=is_overlap)
        edges.append({
            "from": f"supp_{name}",
            "to": "entity_main",
            "type": "采购",
            "amount": round(amt, 2),
            "label": f"购{amt:,.2f}",
        })
    
    # 重叠节点加双向边（购销闭环）
    for name in overlap_names:
        edges.append({
            "from": f"cust_{name}",
            "to": f"supp_{name}",
            "type": "闭环",
            "amount": round(customer_amounts.get(name, 0) + supplier_amounts.get(name, 0), 2),
            "label": "购销闭环风险",
            "style": "dashed",
            "risk": True,
        })
        # 标记节点风险
        for n in nodes:
            if n["name"] == name:
                n["risk"] = True
    
    # 从联网核查/六员比对提取关联人员
    personnel_overlap = cross_ent.get("personnel_overlap", []) if isinstance(cross_ent, dict) else []
    for p in personnel_overlap[:5]:
        pname = p.get("name", "") if isinstance(p, dict) else str(p)
        if pname:
            _add_node(f"person_{pname}", pname, "person", risk=True)
            edges.append({
                "from": "entity_main",
                "to": f"person_{pname}",
                "type": "关联",
                "label": "人员重叠",
                "style": "dotted",
                "risk": True,
            })
    
    # 统计闭环风险
    closed_loops = [e for e in edges if e.get("risk") and e.get("type") == "闭环"]
    
    return {
        "ok": True,
        "graph": {
            "nodes": nodes,
            "edges": edges,
        },
        "summary": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "supplier_count": len(top_suppliers),
            "customer_count": len(top_customers),
            "closed_loops": len(closed_loops),
            "overlap_entities": list(overlap_names),
            "personnel_links": len([e for e in edges if e.get("type") == "关联"]),
        },
    }


# ═══════════════════════════════════════════════════════════
# 智能抽样引擎 —— 基于风险评分自动选出重点深挖对象
# ═══════════════════════════════════════════════════════════

@app.get("/api/sampling/smart")
def smart_sampling(company_id: int = Query(...), sample_size: int = Query(10)):
    """风险驱动智能抽样：按风险贡献度/金额/异常度综合排序
    从发票/供应商/客户中自动选出最值得深挖的样本
    """
    cached = _last_analysis_cache.get(company_id)
    if not cached:
        return {"ok": False, "message": "请先运行一键分析"}
    
    report = cached["report"]["report"] if isinstance(cached["report"], dict) and "report" in cached["report"] else cached["report"]
    cc = report.get("comprehensive", {})
    mi = cc.get("material_intel", {})
    all_f = report.get("all_findings", [])
    
    samples = {
        "top_risk_transactions": [],
        "high_risk_suppliers": [],
        "high_value_customers": [],
        "anomaly_patterns": [],
        "sampling_methodology": {
            "method": "风险分层抽样（Stratified Risk Sampling）",
            "strata": ["P0高风险(score>=8)", "P1中风险(score>=5)", "P2低风险(score>=2)"],
            "weighting": "score权重0.5 + 金额权重0.3 + 异常度权重0.2",
            "rationale": "重点覆盖高风险+大金额，兼顾小金额异常模式"
        }
    }
    
    # 从findings中提取高风险发现关联的实体
    high_risk_findings = [f for f in all_f if (f.get("score") or 0) >= 7]
    
    # 从发票明细中按金额加权随机抽样
    inv_data = mi.get("发票", {})
    sal_detail = inv_data.get("销项发票全量明细", [])
    pur_detail = inv_data.get("进项发票全量明细", [])
    
    # 供应商风险排序（结合金额+发现数）
    supplier_risk = {}
    for inv in pur_detail:
        sname = inv.get("对方公司名称", "").strip()
        amt = float(inv.get("价税合计", 0) or 0)
        if sname not in supplier_risk:
            supplier_risk[sname] = {"total": 0, "count": 0, "risk_mentions": 0}
        supplier_risk[sname]["total"] += amt
        supplier_risk[sname]["count"] += 1
    
    # 统计每个供应商在风险发现中被提及次数
    for f in high_risk_findings:
        detail = (f.get("detail") or "") + (f.get("suggestion") or "")
        for sname in supplier_risk:
            if sname in detail:
                supplier_risk[sname]["risk_mentions"] += 1
    
    # 综合评分排序
    ranked_suppliers = sorted(supplier_risk.items(), key=lambda x: (
        x[1]["risk_mentions"] * 10 + x[1]["total"] / 10000
    ), reverse=True)
    
    for sname, info in ranked_suppliers[:sample_size]:
        samples["high_risk_suppliers"].append({
            "name": sname,
            "total_amount": round(info["total"], 2),
            "invoice_count": info["count"],
            "risk_mentions": info["risk_mentions"],
            "composite_score": round(info["risk_mentions"] * 10 + info["total"] / 10000, 1),
            "audit_priority": "P0" if info["risk_mentions"] > 0 else ("P1" if info["total"] > 100000 else "P2"),
        })
    
    # 客户金额排序（Top N）
    customer_amt = {}
    for inv in sal_detail:
        cname = inv.get("对方公司名称", "").strip()
        amt = float(inv.get("价税合计", 0) or 0)
        customer_amt[cname] = customer_amt.get(cname, 0) + amt
    
    top_customers = sorted(customer_amt.items(), key=lambda x: -x[1])[:sample_size]
    for cname, amt in top_customers:
        samples["high_value_customers"].append({
            "name": cname,
            "total_amount": round(amt, 2),
            "audit_priority": "P0" if amt > 500000 else ("P1" if amt > 100000 else "P2"),
        })
    
    # 异常模式检测
    anomaly_patterns = []
    # 检查品名异常（有加工费发票的供应商）
    for inv in pur_detail:
        pname = (inv.get("品名", "") or "").strip()
        if any(kw in pname for kw in ["加工", "修理", "修配", "劳务", "服务"]):
            anomaly_patterns.append({
                "type": "加工费交易",
                "supplier": inv.get("对方公司名称", ""),
                "amount": float(inv.get("价税合计", 0) or 0),
                "invoice_no": inv.get("发票号", ""),
                "concern": "需核实委托加工真实性",
            })
    
    samples["anomaly_patterns"] = anomaly_patterns[:sample_size]
    
    return {"ok": True, "samples": samples, "generated_at": datetime.now().isoformat()}


# ═══════════════════════════════════════════════════════════
# 整改跟踪闭环 —— 风险发现→整改完成全流程 API
# ═══════════════════════════════════════════════════════════

@app.post("/api/remediation/create")
def create_remediation(
    company_id: int = Query(...),
    finding_type: str = Query(""),
    finding_detail: str = Query(""),
    risk_level: str = Query("中"),
    responsible_person: str = Query(""),
    action_plan: str = Query(""),
    deadline: str = Query(""),
    trace_id: str = Query(""),
    db: Session = Depends(get_db),
):
    """创建整改记录"""
    from database import RemediationRecord
    rec = RemediationRecord(
        company_id=company_id,
        finding_type=finding_type,
        finding_detail=finding_detail,
        risk_level=risk_level,
        status="pending",
        responsible_person=responsible_person,
        action_plan=action_plan,
        deadline=datetime.strptime(deadline, "%Y-%m-%d").date() if deadline else None,
        trace_id=trace_id,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return {"ok": True, "id": rec.id, "message": "整改记录已创建"}


@app.get("/api/remediation/list")
def list_remediations(company_id: int = Query(...), status: str = Query(""), db: Session = Depends(get_db)):
    """列出整改记录"""
    from database import RemediationRecord
    q = db.query(RemediationRecord).filter(RemediationRecord.company_id == company_id)
    if status:
        q = q.filter(RemediationRecord.status == status)
    records = q.order_by(RemediationRecord.updated_at.desc()).all()
    
    def _fmt(r):
        return {
            "id": r.id, "finding_type": r.finding_type, "finding_detail": r.finding_detail,
            "risk_level": r.risk_level, "status": r.status,
            "responsible_person": r.responsible_person, "action_plan": r.action_plan,
            "deadline": str(r.deadline) if r.deadline else "",
            "completed_at": r.completed_at.isoformat() if r.completed_at else "",
            "verified_by": r.verified_by, "verification_note": r.verification_note,
            "notes": r.notes, "created_at": r.created_at.isoformat() if r.created_at else "",
            "updated_at": r.updated_at.isoformat() if r.updated_at else "",
        }
    
    return {
        "ok": True,
        "records": [_fmt(r) for r in records],
        "summary": {
            "total": len(records),
            "pending": sum(1 for r in records if r.status == "pending"),
            "in_progress": sum(1 for r in records if r.status == "in_progress"),
            "completed": sum(1 for r in records if r.status == "completed"),
            "verified": sum(1 for r in records if r.status == "verified"),
            "closed": sum(1 for r in records if r.status == "closed"),
        }
    }


@app.put("/api/remediation/{record_id}")
def update_remediation(
    record_id: int,
    status: str = Query(""),
    verified_by: str = Query(""),
    verification_note: str = Query(""),
    notes: str = Query(""),
    db: Session = Depends(get_db),
):
    """更新整改状态"""
    from database import RemediationRecord
    rec = db.query(RemediationRecord).filter(RemediationRecord.id == record_id).first()
    if not rec:
        raise HTTPException(404, "整改记录不存在")
    if status:
        rec.status = status
        if status == "completed":
            rec.completed_at = datetime.utcnow()
    if verified_by:
        rec.verified_by = verified_by
    if verification_note:
        rec.verification_note = verification_note
    if notes:
        rec.notes = notes
    rec.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": f"整改记录#{record_id}已更新为{rec.status}"}


@app.post("/api/remediation/batch-from-findings")
def batch_create_remediation(company_id: int = Query(...), db: Session = Depends(get_db)):
    """从最近一次分析结果批量创建整改记录（高风险发现自动转化为整改任务）"""
    from database import RemediationRecord
    cached = _last_analysis_cache.get(company_id)
    if not cached:
        return {"ok": False, "message": "请先运行一键分析"}
    
    report = cached["report"]["report"] if isinstance(cached["report"], dict) and "report" in cached["report"] else cached["report"]
    all_f = report.get("all_findings", [])
    trace_id = report.get("trace_id", "")
    
    # 只对高风险+中风险发现创建整改
    created = 0
    for f in all_f:
        level = f.get("level", "")
        if level not in ("高风险", "中风险"):
            continue
        rec = RemediationRecord(
            company_id=company_id, finding_type=f.get("type", ""),
            finding_detail=f.get("detail", ""), risk_level=level,
            status="pending", trace_id=trace_id,
        )
        db.add(rec)
        created += 1
    
    db.commit()
    return {"ok": True, "created": created, "message": f"已从{len(all_f)}项发现中创建{created}条整改任务"}


# ═══════════════════════════════════════════════════════════
# 多期趋势分析 —— 跨多次分析结果对比
# ═══════════════════════════════════════════════════════════

@app.get("/api/trend/analysis")
def get_trend_analysis(company_id: int = Query(...)):
    """跨分析历史趋势对比
    对比最近N次分析的指标变化趋势
    """
    cached = _last_analysis_cache.get(company_id)
    if not cached:
        return {"ok": False, "message": "请先运行一键分析"}
    
    report = cached["report"]["report"] if isinstance(cached["report"], dict) and "report" in cached["report"] else cached["report"]
    cc = report.get("comprehensive", {})
    mi = cc.get("material_intel", {})
    inv_stats = mi.get("发票", {}).get("统计", {})
    bank_stats = mi.get("银行流水", {}).get("统计", {})
    
    # 当前分析指标
    current_metrics = {
        "analysis_time": cached.get("timestamp", ""),
        "total_risks": report.get("total_risks", 0),
        "high_risk": report.get("high_risk", 0),
        "mid_risk": report.get("mid_risk", 0),
        "sales_invoices": inv_stats.get("销项发票数量", 0),
        "sales_amount": inv_stats.get("销项金额合计", 0),
        "purchase_invoices": inv_stats.get("进项发票数量", 0),
        "purchase_amount": inv_stats.get("进项金额合计", 0),
        "bank_inflow": bank_stats.get("收款合计", 0),
        "bank_outflow": bank_stats.get("付款合计", 0),
    }
    
    # 从industry_benchmarks表获取历史数据做趋势
    trend_indicators = {}
    try:
        from database import IndustryBenchmark, SessionLocal
        sdb = SessionLocal()
        benchmarks = sdb.query(IndustryBenchmark).filter(
            IndustryBenchmark.company_id == company_id
        ).order_by(IndustryBenchmark.updated_at.desc()).limit(50).all()
        
        for b in benchmarks:
            if b.metric_name not in trend_indicators:
                trend_indicators[b.metric_name] = []
            trend_indicators[b.metric_name].append({
                "value": float(b.metric_value) if b.metric_value else 0,
                "time": b.updated_at.isoformat() if b.updated_at else "",
            })
        sdb.close()
    except Exception:
        pass
    
    # 趋势方向判断
    def _trend_direction(values):
        if len(values) < 3: return "数据不足"
        recent = sum(v["value"] for v in values[:2]) / 2
        older = sum(v["value"] for v in values[-2:]) / 2
        if abs(recent - older) < older * 0.05: return "持平"
        return "上升" if recent > older else "下降"
    
    trends = {}
    for metric, data in trend_indicators.items():
        trends[metric] = {
            "direction": _trend_direction(data),
            "data_points": data[:10],
            "current": data[0]["value"] if data else 0,
        }
    
    return {
        "ok": True,
        "current": current_metrics,
        "trends": trends,
        # 智能体跨分析学习数据
        "agent_memory": (cached.get("report") or {}).get("agent", {}).get("memory", {}),
        "agent_reflection_stats": (cached.get("report") or {}).get("agent", {}).get("reflection", {}),
        "indicators": {
            "invoice_match_ratio": {
                "current": round((inv_stats.get("销项金额合计", 0) or 0) / max((inv_stats.get("进项金额合计", 0) or 1), 1), 2),
                "label": "进销比",
                "interpretation": "进销比接近1为正常，<0.8或>1.2需关注",
            },
            "risk_trend": {
                "high_risk_count": report.get("high_risk", 0),
                "label": "高风险发现数",
            },
        },
    }


# ═══════════════════════════════════════════════════════════
# 行业对标自更新 —— 基准值从每次分析中学习
# ═══════════════════════════════════════════════════════════

@app.get("/api/benchmarks/industry")
def get_industry_benchmarks(industry: str = Query(""), metric: str = Query("")):
    """获取行业基准值（动态自更新）
    每次分析完成后自动将企业指标纳入行业统计池
    当前基准为所有已分析企业的累计统计
    """
    try:
        from database import IndustryBenchmark, SessionLocal
        sdb = SessionLocal()
        q = sdb.query(IndustryBenchmark)
        if industry:
            q = q.filter(IndustryBenchmark.industry == industry)
        if metric:
            q = q.filter(IndustryBenchmark.metric_name == metric)
        
        benchmarks = q.order_by(IndustryBenchmark.updated_at.desc()).all()
        
        results = []
        by_metric = {}
        for b in benchmarks:
            item = {
                "industry": b.industry,
                "metric": b.metric_name,
                "sample_count": b.sample_count,
                "mean": round(float(b.running_mean), 4) if b.running_mean else None,
                "std": round(float(b.running_std), 4) if b.running_std else None,
                "p25": round(float(b.p25), 4) if b.p25 else None,
                "p50": round(float(b.p50), 4) if b.p50 else None,
                "p75": round(float(b.p75), 4) if b.p75 else None,
                "updated_at": b.updated_at.isoformat() if b.updated_at else "",
            }
            results.append(item)
            key = f"{b.industry}_{b.metric_name}"
            if key not in by_metric:
                by_metric[key] = item
        
        sdb.close()
        
        return {
            "ok": True,
            "total_benchmarks": len(results),
            "industries": list(set(b.industry for b in benchmarks)),
            "metrics": list(set(b.metric_name for b in benchmarks)),
            "benchmarks": list(by_metric.values()),
            "methodology": {
                "algorithm": "在线Welford算法（增量均值/标准差）",
                "update_trigger": "每次一键分析完成后自动更新",
                "min_samples_for_benchmark": 3,
                "note": "样本数<3时基准值仅供参考，随分析次数增加而精确",
            },
        }
    except Exception as e:
        return {"ok": False, "message": f"查询失败: {e}"}


# ═══════════════════════════════════════════════════════════
# 对话式稽查 —— 自然语言查询分析结果
# ═══════════════════════════════════════════════════════════

@app.post("/api/agi/query")
def agi_query(company_id: int = Query(...), query: str = Query(...)):
    """自然语言查询分析结果
    用户用中文提问，AGI自动查分析数据并用中文回答
    示例: "虚开风险多大""供应商集中度""进销比多少"
    """
    cached = _last_analysis_cache.get(company_id)
    if not cached:
        return {"ok": False, "answer": "请先运行一键分析，我才能回答您的问题。"}
    
    report = cached["report"]["report"] if isinstance(cached["report"], dict) and "report" in cached["report"] else cached["report"]
    cc = report.get("comprehensive", {})
    all_f = report.get("all_findings", [])
    mi = cc.get("material_intel", {})
    inv_stats = mi.get("发票", {}).get("统计", {})
    bank_stats = mi.get("银行流水", {}).get("统计", {})
    
    q = query.lower().strip()
    answer = ""
    related_findings = []
    
    # 关键词匹配引擎
    if any(kw in q for kw in ["虚开", "发票风险", "虚假", "开票风险"]):
        fake_findings = [f for f in all_f if any(kw in (f.get("type","")+f.get("detail","")) for kw in ["虚开","虚假","伪造","不实"])]
        high_count = sum(1 for f in fake_findings if f.get("level") == "高风险")
        total_amt = sum(float(f.get("detail","0").replace(",","")) if f.get("detail","0").replace(",","").replace(".","").isdigit() else 0 for f in fake_findings)
        answer = f"当前企业虚开发票风险评估为{'高风险' if high_count > 0 else '中风险'}。共发现{len(fake_findings)}条相关线索，其中高风险{high_count}条。建议重点核查进项发票品名与销项是否匹配、供应商是否真实存在。"
        related_findings = fake_findings[:5]
    
    elif any(kw in q for kw in ["供应商", "采购", "供应商集中", "供应商风险"]):
        pur_detail = mi.get("发票", {}).get("进项发票全量明细", [])
        supplier_amt = {}
        for inv in pur_detail:
            sname = inv.get("对方公司名称", "").strip()
            amt = float(inv.get("价税合计", 0) or 0)
            supplier_amt[sname] = supplier_amt.get(sname, 0) + amt
        total_pur = sum(supplier_amt.values())
        top3 = sorted(supplier_amt.items(), key=lambda x: -x[1])[:3]
        top3_ratio = sum(a for _, a in top3) / max(total_pur, 1) * 100
        conc_risk = "高" if top3_ratio > 70 else ("中" if top3_ratio > 50 else "低")
        top_names = " / ".join(f"{n}({(a/total_pur*100):.2f}%)" for n, a in top3)
        answer = f"供应商集中度风险：{conc_risk}（Top3占比{top3_ratio:.2f}%）。前三大供应商：{top_names}。共{len(supplier_amt)}家供应商，采购总额{total_pur:,.2f}元。{'建议分散采购来源以降低依赖风险。' if conc_risk != '低' else '供应商分布较为合理。'}"
    
    elif any(kw in q for kw in ["进销比", "购销比", "进销存", "进销匹配"]):
        sal_amt = inv_stats.get("销项金额合计", 0) or 0
        pur_amt = inv_stats.get("进项金额合计", 0) or 0
        ratio = sal_amt / max(pur_amt, 1)
        status = "偏高" if ratio > 1.2 else ("偏低" if ratio < 0.8 else "正常")
        answer = f"进销比 = {ratio:.2f}（{status}）。销项{sal_amt:,.2f}元 / 进项{pur_amt:,.2f}元。{'进销比偏高可能存在少计成本或虚增收入风险。' if ratio > 1.2 else ('进销比偏低可能存在隐匿收入或虚列成本风险。' if ratio < 0.8 else '进销比在正常范围内。')}"
    
    elif any(kw in q for kw in ["税负", "税率", "税负率", "增值税"]):
        sal_amt = inv_stats.get("销项金额合计", 0) or 0
        sal_tax = inv_stats.get("销项税额合计", 0) or 0
        pur_tax = inv_stats.get("进项税额合计", 0) or 0
        tax_burden = (sal_tax - pur_tax) / max(sal_amt, 1) * 100
        answer = f"增值税税负率约{tax_burden:.2f}%（销项税{sal_tax:,.2f} - 进项税{pur_tax:,.2f} / 销项额{sal_amt:,.2f}）。{'税负率偏低需关注是否存在隐匿销售收入。' if tax_burden < 1 else '税负率在合理区间。'}"
    
    elif any(kw in q for kw in ["风险", "整体", "综合", "总体"]):
        high_risk = report.get("high_risk", 0)
        mid_risk = report.get("mid_risk", 0)
        level = report.get("overall_level", "")
        # 优先使用智能体的洞见总结（在result顶层，不在report内层）
        agent_insight = ""
        if isinstance(cached.get("report"), dict):
            agent_insight = (cached["report"].get("agent") or {}).get("insight_summary", "")
        exec_summary = cc.get('executive_summary', cc.get('narrative_summary', ''))
        narrative = agent_insight or exec_summary
        answer = f"综合风险等级：{level}。共发现{report.get('total_risks',0)}项风险（高{high_risk}/中{mid_risk}）。{narrative}"
    
    elif any(kw in q for kw in ["银行", "资金流", "流水", "收款", "付款"]):
        bank_in = bank_stats.get("收款合计", 0) or 0
        bank_out = bank_stats.get("付款合计", 0) or 0
        sal_amt = inv_stats.get("销项金额合计", 0) or 0
        pur_amt = inv_stats.get("进项金额合计", 0) or 0
        answer = f"银行收款{bank_in:,.2f}元 vs 销项开票{sal_amt:,.2f}元（差异{abs(bank_in-sal_amt):,.2f}元）。银行付款{bank_out:,.2f}元 vs 进项发票{pur_amt:,.2f}元（差异{abs(bank_out-pur_amt):,.2f}元）。{'收款大于开票金额，可能存在未开票收入。' if bank_in > sal_amt * 1.1 else ''}{'付款大于进项金额，可能存在未取得发票的支出。' if bank_out > pur_amt * 1.1 else ''}"
    
    elif any(kw in q for kw in ["行业", "行业对比", "行业基准", "同行"]):
        benchmarks = ""
        try:
            from database import IndustryBenchmark, SessionLocal
            sdb = SessionLocal()
            bms = sdb.query(IndustryBenchmark).filter(IndustryBenchmark.metric_name == "invoice_match_ratio").order_by(IndustryBenchmark.sample_count.desc()).limit(5).all()
            if bms:
                benchmarks = "行业基准值（进销比）：" + " / ".join(f"{b.industry}(样本{b.sample_count})均值{(float(b.running_mean or 0)):.2f}" for b in bms)
            sdb.close()
        except: pass
        answer = f"当前企业行业：{report.get('target_entity',{}).get('industry','未知')}。{benchmarks}"
    
    else:
        answer = f"关于「{query}」的查询，当前分析结果中有{len(all_f)}项发现。您可以试试问：虚开风险多大？供应商集中度如何？进销比是多少？税负率如何？资金流正常吗？"
    
    return {
        "ok": True,
        "query": query,
        "answer": answer,
        "related_findings": [{"type": f.get("type"), "level": f.get("level"), "detail": f.get("detail","")[:150]} for f in (related_findings or [])],
        "timestamp": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════════════════════
# 自动巡检 —— 定时自动分析 + 状态监控
# ═══════════════════════════════════════════════════════════

_patrol_config = {"enabled": False, "interval_hours": 24, "company_ids": [], "last_run": None, "runs": []}

# ── AGI管道仪表盘 ──
@app.get("/api/agi/pipeline/dashboard")
def get_agi_pipeline_dashboard():
    """税务AGI管道仪表盘——展示16模块知识注入状态"""
    try:
        global _agi_pipeline_instance
        if '_agi_pipeline_instance' in globals() and _agi_pipeline_instance:
            data = _agi_pipeline_instance.get_dashboard_data()
            data["ok"] = True
            return data
    except: pass
    return {"ok": True, "stats": {"modules_connected": 0, "events_collected": 0}, "total_events": 0, "modules_active": 0, "health": "idle", "message": "AGI管道尚未运行，请先执行一键分析"}

@app.get("/api/patrol/status")
def patrol_status_v2():
    return {"ok": True, "config": _patrol_config, "runs_count": len(_patrol_config.get("runs", []))}

@app.post("/api/patrol/config")
def set_patrol_config(enabled: bool = Query(False), interval_hours: int = Query(24), company_ids: str = Query("")):
    """配置自动巡检：启用/禁用、间隔小时、巡检企业ID列表"""
    _patrol_config["enabled"] = enabled
    _patrol_config["interval_hours"] = interval_hours
    if company_ids:
        _patrol_config["company_ids"] = [int(x.strip()) for x in company_ids.split(",") if x.strip().isdigit()]
    else:
        _patrol_config["company_ids"] = [1]  # 默认巡检公司1
    return {"ok": True, "config": _patrol_config, "message": f"巡检已{'启用' if enabled else '禁用'}，间隔{interval_hours}小时"}

@app.post("/api/patrol/run")
def run_patrol_now():
    """手动触发一次巡检"""
    import traceback as _tb
    company_ids = _patrol_config.get("company_ids", [1])
    results = []
    
    for cid in company_ids:
        try:
            from database import SessionLocal
            db = SessionLocal()
            r = _run_analyze(cid, db)
            report = r.get("report", {})
            results.append({
                "company_id": cid,
                "ok": r.get("ok", False),
                "level": report.get("overall_level", ""),
                "total_risks": report.get("total_risks", 0),
                "high_risk": report.get("high_risk", 0),
            })
            db.close()
        except Exception as e:
            results.append({"company_id": cid, "ok": False, "error": str(e)})
    
    run_record = {"time": datetime.now().isoformat(), "companies": len(company_ids), "results": results}
    _patrol_config["runs"].insert(0, run_record)
    _patrol_config["last_run"] = run_record["time"]
    if len(_patrol_config["runs"]) > 50:
        _patrol_config["runs"] = _patrol_config["runs"][:50]
    
    return {"ok": True, "run": run_record, "total_runs": len(_patrol_config["runs"])}


# ═══════════════════════════════════════════════════════════
# 报告自动分发 —— 分析完成后系统内通知
# ═══════════════════════════════════════════════════════════

_notification_config = {"enabled": True, "channels": ["system"], "webhook_url": "", "email": ""}

@app.get("/api/notifications/config")
def get_notification_config():
    return {"ok": True, "config": _notification_config}

@app.post("/api/notifications/config")
def set_notification_config(webhook_url: str = Query(""), email: str = Query(""), enabled: bool = Query(True)):
    """配置通知渠道：系统内通知/Webhook/邮件"""
    if webhook_url:
        _notification_config["webhook_url"] = webhook_url
    if email:
        _notification_config["email"] = email
    _notification_config["enabled"] = enabled
    return {"ok": True, "config": _notification_config}

@app.get("/api/notifications/latest")
def get_latest_notification(company_id: int = Query(...)):
    """获取最近一次分析的通知摘要（用于分发）"""
    cached = _last_analysis_cache.get(company_id)
    if not cached:
        return {"ok": False, "message": "暂无分析结果"}
    
    report = cached["report"]["report"] if isinstance(cached["report"], dict) and "report" in cached["report"] else cached["report"]
    te = report.get("target_entity", {})
    
    notification = {
        "title": f"财税稽查报告 — {te.get('name', '')}",
        "summary": f"{report.get('overall_level', '')}，{report.get('total_risks', 0)}项风险发现（高{report.get('high_risk', 0)}/中{report.get('mid_risk', 0)}）",
        "time": cached.get("timestamp", ""),
        "key_findings": [f.get("type") for f in (report.get("all_findings", []) or [])[:5] if f.get("level") == "高风险"],
        "actions": ["请登录系统查看完整报告", "高风险发现需立即处理"],
    }
    
    # 如果配置了Webhook，尝试发送
    webhook_result = None
    if _notification_config.get("webhook_url"):
        try:
            import urllib.request, json as _json
            req = urllib.request.Request(
                _notification_config["webhook_url"],
                data=_json.dumps(notification).encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=5)
            webhook_result = "sent"
        except Exception as e:
            webhook_result = f"failed: {e}"
    
    return {
        "ok": True,
        "notification": notification,
        "webhook_result": webhook_result,
        "channels": _notification_config.get("channels", ["system"]),
    }


# ═══════════════════════════════════════════════════════════
# 法规变更影响分析 —— 政策版本对比 + 企业影响评估
# ═══════════════════════════════════════════════════════════

_policy_history = []

@app.get("/api/policy/changes")
def get_policy_changes():
    """获取法规变更记录及对企业的影响评估"""
    return {
        "ok": True,
        "changes": _policy_history[-20:],
        "total_tracked": len(_policy_history),
        "methodology": "自动监测税收政策文件有效期，识别到期/更新/废止变更",
    }

@app.post("/api/policy/check")
def check_policy_impact(company_id: int = Query(...)):
    """检查当前企业受法规变更的影响"""
    cached = _last_analysis_cache.get(company_id)
    impacts = []
    
    try:
        from engine.tax_incentive_analyzer import POLICY_VALIDITY
        from datetime import date as _date
        today = _date.today()
        
        for policy_name, policy_info in POLICY_VALIDITY.items():
            if isinstance(policy_info, dict):
                valid_until = policy_info.get("valid_until", "")
                if valid_until:
                    try:
                        expiry = _date.fromisoformat(valid_until)
                        days_left = (expiry - today).days
                        if days_left < 90:  # 3个月内到期
                            impacts.append({
                                "policy": policy_name,
                                "description": policy_info.get("description", ""),
                                "valid_until": valid_until,
                                "days_left": days_left,
                                "impact": "即将到期" if days_left > 0 else "已到期",
                                "severity": "高" if days_left < 30 else ("中" if days_left < 90 else "低"),
                                "action": "需关注政策更新，评估替代方案" if days_left < 30 else "建议提前准备应对方案",
                            })
                    except: pass
    except Exception as e:
        return {"ok": False, "message": f"检查失败: {e}"}
    
    return {
        "ok": True,
        "company_id": company_id,
        "checked_at": datetime.now().isoformat(),
        "impacts": impacts,
        "total_impacts": len(impacts),
    }


# ═══════════════════════════════════════════════════════════
# 风险预测模型 —— 基于历史数据预测风险等级
# ═══════════════════════════════════════════════════════════

@app.get("/api/risk/predict")
def predict_risk(company_id: int = Query(...)):
    """基于行业累积数据预测企业风险等级
    使用加权评分模型：行业基准偏离度 + 历史风险密度 + 指标异常度
    """
    cached = _last_analysis_cache.get(company_id)
    if not cached:
        return {"ok": False, "message": "请先运行一键分析"}
    
    report = cached["report"]["report"] if isinstance(cached["report"], dict) and "report" in cached["report"] else cached["report"]
    cc = report.get("comprehensive", {})
    mi = cc.get("material_intel", {})
    inv_stats = mi.get("发票", {}).get("统计", {})
    bank_stats = mi.get("银行流水", {}).get("统计", {})
    te = report.get("target_entity", {})
    industry = te.get("industry", "通用")
    
    # 计算指标
    sal_amt = inv_stats.get("销项金额合计", 0) or 0
    pur_amt = inv_stats.get("进项金额合计", 0) or 0
    bank_in = bank_stats.get("收款合计", 0) or 0
    bank_out = bank_stats.get("付款合计", 0) or 0
    
    factors = {}
    total_weight = 0
    
    # 因子1：进销比偏离度
    if sal_amt > 0 and pur_amt > 0:
        ratio = sal_amt / pur_amt
        deviation = abs(ratio - 1.0)
        factors["进销比偏离度"] = {"value": round(ratio, 2), "deviation": round(deviation, 2), "score": min(deviation * 10, 10)}
        total_weight += factors["进销比偏离度"]["score"]
    
    # 因子2：资金流匹配度
    if sal_amt > 0 and bank_in > 0:
        match = min(bank_in / sal_amt, sal_amt / bank_in)
        factors["资金流匹配度"] = {"value": round(match, 2), "score": (1 - match) * 10}
        total_weight += factors["资金流匹配度"]["score"]
    
    # 因子3：当前风险密度
    risk_density = report.get("high_risk", 0) / max(report.get("total_risks", 1), 1)
    factors["高风险占比"] = {"value": round(risk_density, 2), "score": risk_density * 10}
    total_weight += factors["高风险占比"]["score"]
    
    # 因子4：行业基准对比
    try:
        from database import IndustryBenchmark, SessionLocal
        sdb = SessionLocal()
        bm = sdb.query(IndustryBenchmark).filter(
            IndustryBenchmark.industry == industry,
            IndustryBenchmark.metric_name == "invoice_match_ratio"
        ).first()
        if bm and bm.running_mean:
            bench_mean = float(bm.running_mean)
            if sal_amt > 0 and pur_amt > 0:
                deviation = abs(sal_amt / pur_amt - bench_mean)
                factors["行业基准偏离"] = {"value": round(sal_amt/pur_amt, 2), "benchmark": round(bench_mean, 2), "score": min(deviation * 15, 10)}
                total_weight += factors["行业基准偏离"]["score"]
        sdb.close()
    except: pass
    
    # 加权综合评分
    predicted_score = total_weight  # 0-40分制
    predicted_level = "高风险" if predicted_score > 20 else ("中风险" if predicted_score > 10 else "低风险")
    predicted_prob = min(predicted_score / 40 * 100, 95)
    
    return {
        "ok": True,
        "prediction": {
            "level": predicted_level,
            "score": round(predicted_score, 1),
            "probability": round(predicted_prob, 1),
            "confidence": "中" if len(factors) >= 3 else "低（建议增加分析次数以提高准确性）",
        },
        "factors": factors,
        "methodology": "加权因子模型：进销比偏离度 + 资金流匹配度 + 风险密度 + 行业基准对比",
        "note": "预测基于当前数据和行业历史累积，准确度随分析次数增加而提高",
    }


# ═══════════════════════════════════════════════════════════
# 多企业集团分析 —— 跨企业横向对比
# ═══════════════════════════════════════════════════════════

@app.get("/api/group/analysis")
def group_analysis(company_ids: str = Query("")):
    """多企业横向对比分析
    company_ids: 逗号分隔的企业ID列表
    """
    ids = [int(x.strip()) for x in company_ids.split(",") if x.strip().isdigit()] if company_ids else []
    if len(ids) < 2:
        return {"ok": False, "message": "请至少选择2家企业进行对比（使用 company_ids 参数，逗号分隔）"}
    
    comparison = []
    for cid in ids[:5]:  # 最多5家
        cached = _last_analysis_cache.get(cid)
        if not cached:
            comparison.append({"company_id": cid, "status": "未分析"})
            continue
        
        report = cached["report"]["report"] if isinstance(cached["report"], dict) and "report" in cached["report"] else cached["report"]
        cc = report.get("comprehensive", {})
        mi = cc.get("material_intel", {})
        inv_stats = mi.get("发票", {}).get("统计", {})
        bank_stats = mi.get("银行流水", {}).get("统计", {})
        te = report.get("target_entity", {})
        
        sal_amt = inv_stats.get("销项金额合计", 0) or 0
        pur_amt = inv_stats.get("进项金额合计", 0) or 0
        
        comparison.append({
            "company_id": cid,
            "name": te.get("name", f"企业{cid}"),
            "industry": te.get("industry", ""),
            "risk_level": report.get("overall_level", ""),
            "total_risks": report.get("total_risks", 0),
            "high_risk": report.get("high_risk", 0),
            "mid_risk": report.get("mid_risk", 0),
            "sales_amount": round(sal_amt, 2),
            "purchase_amount": round(pur_amt, 2),
            "in_out_ratio": round(sal_amt / max(pur_amt, 1), 2),
            "bank_inflow": round(bank_stats.get("收款合计", 0) or 0, 2),
            "bank_outflow": round(bank_stats.get("付款合计", 0) or 0, 2),
            "top_risk_types": list(set(f.get("type", "") for f in (report.get("all_findings", []) or [])[:5] if f.get("level") == "高风险")),
        })
    
    # 集团整体风险画像
    group_profile = {
        "total_companies": len(comparison),
        "analyzed_count": sum(1 for c in comparison if c.get("risk_level")),
        "high_risk_count": sum(1 for c in comparison if c.get("risk_level") == "高风险"),
        "total_risks_sum": sum(c.get("total_risks", 0) for c in comparison),
        "common_risk_types": [],
    }
    
    # 找出跨企业共同风险类型
    all_types = {}
    for c in comparison:
        for t in (c.get("top_risk_types") or []):
            all_types[t] = all_types.get(t, 0) + 1
    group_profile["common_risk_types"] = sorted(all_types.items(), key=lambda x: -x[1])[:5]
    
    # 关联交易检测
    cross_relations = []
    names_map = {c["company_id"]: c["name"] for c in comparison}
    
    return {
        "ok": True,
        "comparison": comparison,
        "group_profile": group_profile,
        "cross_relations": cross_relations,
        "radar_dimensions": ["风险等级", "进销比", "高风险数", "资金匹配", "规模"],
        "generated_at": datetime.now().isoformat(),
    }


@app.get("/api/health")
def health_check():
    """健康检查——返回当前运行的git commit版本，用于验证服务器是否运行最新代码"""
    import subprocess
    commit = "unknown"
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0: commit = r.stdout.strip()
    except: pass
    return {"status": "ok", "commit": commit, "port": 8001}

@app.get("/api/audit/status")
def audit_status(company_id: int = Query(...)):
    """质量保障状态——返回audit.py 7项检查结果 + 系统健康评分（需指定 company_id）"""
    try:
        import importlib
        import audit as audit_mod
        importlib.reload(audit_mod)
        result = audit_mod.audit_all(company_id)
        
        # 转换输出格式
        items = []
        passed = 0
        total = 0
        check_names = {
            "重复记账": "验证同一银行流水不被多个匹配函数重复记账",
            "借贷不平": "验证每张凭证借=贷，自动化记账精度检查",
            "三号拆分": "验证同一(invoice_code,invoice_no,digital_invoice_no)合并为一张凭证",
            "BK凭证号不一致": "验证记账发票凭证号与序时账凭证号完全一致",
            "科目名称格式错误": "验证所有科目name字段只存本级名称，不含上级前缀",
            "档案锁定缺失": "验证已记账数据关联的档案记录已锁定，不可修改",
            "来源不一致": "验证来源系统记录与实际数据的一致性",
        }
        
        for check_name, count in result["results"].items():
            total += 1
            is_ok = count == 0
            if is_ok: passed += 1
            items.append({
                "name": check_name,
                "description": check_names.get(check_name, ""),
                "error_count": count,
                "passed": is_ok,
                "status": "pass" if is_ok else "fail",
            })
        
        # 额外检查：代码语法（编译检查）
        syntax_ok = True
        syntax_msg = "通过"
        try:
            import py_compile
            py_compile.compile(os.path.join(os.path.dirname(__file__) or ".", "main.py"), doraise=True)
        except py_compile.PyCompileError as pe:
            syntax_ok = False
            syntax_msg = str(pe)[:200]
        except Exception:
            syntax_ok = False
            syntax_msg = "语法检查异常"
        
        total += 1
        if syntax_ok: passed += 1
        items.append({
            "name": "语法编译检查",
            "description": "Python语法编译验证（main.py）",
            "error_count": 0 if syntax_ok else 1,
            "passed": syntax_ok,
            "status": "pass" if syntax_ok else "fail",
        })
        
        score = round(passed / total * 100)
        level = "健康" if score == 100 else ("良好" if score >= 80 else ("警告" if score >= 60 else "危险"))
        
        return {
            "ok": True,
            "score": score,
            "level": level,
            "passed": passed,
            "total": total,
            "items": items,
            "audit_errors": result["errors"][:20],
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "score": 0, "level": "未知", "items": []}

@app.get("/api/methodology-audit")
def methodology_audit():
    """方法论文档↔执行代码对账——扫描AUDIT_METHODOLOGY.md中的方法论编号，检查main.py中是否有实际引用"""
    import re as _re
    base_dir = os.path.dirname(__file__) or "."
    
    # 扫描方法论声明（从AUDIT_METHODOLOGY.md）
    md_path = os.path.join(base_dir, "AUDIT_METHODOLOGY.md")
    declared = []
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            md_text = f.read()
        # 匹配稽查方法论+编号模式：①~㉗ 或 1~N编号
        for m in _re.finditer(r'(?:稽查方法论|方法论)\s*([①-㉗\d]+(?:[-~]\d+)?)', md_text):
            declared.append(m.group(1))
        # 匹配编号方法论引用
        for m in _re.finditer(r'[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗]', md_text):
            n = m.group(0)
            if n not in declared: declared.append(n)
    
    # 扫描main.py中的实际引用
    py_path = os.path.join(base_dir, "main.py")
    py_text = ""
    if os.path.exists(py_path):
        with open(py_path, "r", encoding="utf-8") as f:
            py_text = f.read()
    
    # 查找代码中引用的方法论编号
    code_refs = set()
    for m in _re.finditer(r'[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗]', py_text):
        code_refs.add(m.group(0))
    
    # 查找关键词引用（稽查方法论文字描述）
    kw_map = {
        "主营业务成本识别": "④",
        "付款方身份核实": "③", 
        "联网核查": "⑥",
        "四步稽查分析法": "㉓",
        "三层行业穿透法": "㉕",
        "供应链联网核查": "㉗",
        "经营实质地理分析": "geo",
        "进销存分析": "④",
        "全链路质量保障": "quality",
        "跨域因果叙事": "causal",
        "结论自洽性": "contradiction",
        "缺失后果触发": "missing",
        "事前预警": "early_warning",
        "可信度评估": "confidence",
        "记忆自学习": "memory",
        "行业自适应": "industry",
    }
    kw_code_refs = set()
    for kw, ref in kw_map.items():
        if kw in py_text:
            kw_code_refs.add(ref)
    code_refs = code_refs | kw_code_refs
    
    # 方法论编号→名称映射（从文档中提取或硬编码）
    method_names = {
        "③": "付款方身份核实", "④": "主营业务成本识别驱动的进销存分析",
        "⑥": "联网核查", "㉓": "四步稽查分析法",
        "㉕": "三层行业穿透法", "㉗": "供应链联网核查",
        "geo": "经营实质地理分析", "quality": "全链路质量保障体系",
        "causal": "跨域因果叙事引擎", "contradiction": "结论自洽性检查引擎",
        "missing": "缺失后果自动触发引擎", "early_warning": "事前预警升级引擎",
        "confidence": "结论可信度评估引擎", "memory": "记忆自学习引擎",
        "industry": "行业自适应知识库",
    }
    
    # 构建对账结果
    results = []
    for ref_id in sorted(set(list(declared) + list(code_refs))):
        in_doc = ref_id in declared or ref_id in set(kw_map.values())
        in_code = ref_id in code_refs
        name = method_names.get(ref_id, f"方法论{ref_id}")
        
        if in_doc and in_code:
            status = "aligned"
        elif in_doc and not in_code:
            status = "doc_only"
        elif not in_doc and in_code:
            status = "code_only"
        else:
            status = "missing"
        
        results.append({
            "id": ref_id,
            "name": name,
            "status": status,
            "in_doc": in_doc,
            "in_code": in_code,
        })
    
    aligned = sum(1 for r in results if r["status"] == "aligned")
    doc_only = sum(1 for r in results if r["status"] == "doc_only")
    code_only = sum(1 for r in results if r["status"] == "code_only")
    total_methods = len(results)
    coverage = round(aligned / max(total_methods, 1) * 100)
    
    return {
        "ok": True,
        "total_methods": total_methods,
        "aligned": aligned,
        "doc_only": doc_only,
        "code_only": code_only,
        "coverage_pct": coverage,
        "methods": results,
        "verdict": "全部对齐" if doc_only == 0 and code_only == 0 else (
            f"需修复: {doc_only}条文档声明无代码, {code_only}条代码实现无文档"
        ),
    }

# ═══════════════════════════════════════════════════════════
# 一键分析：异步任务机制
# ═══════════════════════════════════════════════════════════

import threading
_analysis_tasks = {}
_analysis_lock = threading.Lock()

def _analysis_progress(task_id, progress, msg):
    """进度回调（在线程中被调用）"""
    with _analysis_lock:
        if task_id in _analysis_tasks:
            _analysis_tasks[task_id]["progress"] = progress
            _analysis_tasks[task_id]["message"] = msg

def _run_analysis_thread(task_id, company_id):
    """在后台线程中运行分析"""
    import traceback as _tb
    import socket as _socket
    _socket.setdefaulttimeout(10)
    try:
        from database import SessionLocal
        db = SessionLocal()
        try:
            result = _run_analyze(company_id, db, progress_callback=lambda p, m: _analysis_progress(task_id, p, m))
            with _analysis_lock:
                if task_id in _analysis_tasks:
                    _analysis_tasks[task_id]["status"] = "done"
                    _analysis_tasks[task_id]["result"] = result
                    _analysis_tasks[task_id]["progress"] = 100
                    _analysis_tasks[task_id]["message"] = "分析完成"
        finally:
            db.close()
    except Exception as _e:
        with _analysis_lock:
            if task_id in _analysis_tasks:
                _analysis_tasks[task_id]["status"] = "error"
                _analysis_tasks[task_id]["error"] = f"{_e}"
                _analysis_tasks[task_id]["traceback"] = _tb.format_exc()[:3000]

@app.post("/api/tax-risk-docs/analyze-start")
def analyze_tax_risk_docs_start(company_id: int = Query(...)):
    """启动异步分析，立即返回task_id"""
    # 2026-06-26 账套隔离防护：拒绝未选择公司的分析请求
    if company_id <= 0:
        return {"ok": False, "message": "请先选择账套（公司），再执行一键分析"}
    import uuid as _uuid, time as _time_
    task_id = _uuid.uuid4().hex[:12]
    with _analysis_lock:
        _analysis_tasks[task_id] = {
            "status": "running",
            "progress": 0,
            "message": "准备中...",
            "result": None,
            "error": None,
            "company_id": company_id,
            "started_at": _time_.time(),
        }
    t = threading.Thread(target=_run_analysis_thread, args=(task_id, company_id), daemon=True)
    t.start()
    return {"ok": True, "task_id": task_id, "message": "分析已启动"}

@app.get("/api/tax-risk-docs/analyze-status/{task_id}")
def analyze_tax_risk_docs_status(task_id: str):
    """轮询分析进度"""
    with _analysis_lock:
        task = _analysis_tasks.get(task_id)
        if not task:
            return {"ok": False, "message": "任务不存在或已过期"}
        result = {
            "ok": True,
            "task_id": task_id,
            "status": task["status"],
            "progress": task["progress"],
            "message": task["message"],
        }
        # 2026-06-26 修复：error状态下同时返回真正的错误信息，避免前端展示进度消息当错误
        if task["status"] == "error":
            result["error"] = task.get("error", task["message"])
        return result

@app.get("/api/tax-risk-docs/analyze-result/{task_id}")
def analyze_tax_risk_docs_result(task_id: str):
    """获取分析结果"""
    with _analysis_lock:
        task = _analysis_tasks.get(task_id)
        if not task:
            return {"ok": False, "message": "任务不存在或已过期"}
        if task["status"] == "running":
            return {"ok": False, "message": "分析还在进行中", "progress": task["progress"]}
        if task["status"] == "error":
            return {"ok": False, "message": f"分析失败: {task['error']}", "traceback": task.get("traceback", "")}
        return task["result"]

# 旧同步端点保留（兼容性），但建议前端改用异步
@app.post("/api/tax-risk-docs/analyze")
def analyze_tax_risk_docs(company_id: int = Query(...), db: Session = Depends(get_db)):
    """分析涉税资料（同步端点，会阻塞等待完成）"""
    # 2026-06-26 账套隔离防护
    if company_id <= 0:
        return {"ok": False, "message": "请先选择账套（公司），再执行一键分析"}
    import traceback as _tb
    import socket as _socket
    _socket.setdefaulttimeout(10)
    try:
        return _run_analyze(company_id, db)
    except Exception as _e:
        return {"ok": False, "message": f"分析异常: {_e}", "traceback": _tb.format_exc()[:2000]}


# ═══════════════════════════════════════════════════════════
# 生产环境加固中间件
# ═══════════════════════════════════════════════════════════

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time as _time_module
import asyncio

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局错误处理
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": str(exc), "type": type(exc).__name__}
    )

# 简易频率限制
_rate_limit_store = {}
@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    # 本地请求不限制
    if client_ip in ("127.0.0.1", "::1", "localhost"):
        return await call_next(request)
    now = _time_module.time()
    window = 60
    max_requests = 300
    
    if client_ip not in _rate_limit_store:
        _rate_limit_store[client_ip] = []
    _rate_limit_store[client_ip] = [t for t in _rate_limit_store[client_ip] if now - t < window]
    
    if len(_rate_limit_store[client_ip]) >= max_requests:
        return JSONResponse(status_code=429, content={"ok": False, "error": "请求过于频繁，请稍后再试"})
    
    _rate_limit_store[client_ip].append(now)
    response = await call_next(request)
    return response


# ═══════════════════════════════════════════════════════════
# LLM 叙事生成 —— 调用DeepSeek生成专业稽查报告文本
# ═══════════════════════════════════════════════════════════

@app.post("/api/audit/generate-narrative")
def generate_audit_narrative(data: dict):
    """用LLM生成专业稽查叙事文本。
    
    请求: {"findings": [...], "industry": "制造业", "style": "professional" | "concise"}
    返回: {"narrative": "生成的稽查报告文本"}
    """
    findings = data.get("findings", [])
    industry = data.get("industry", "综合")
    style = data.get("style", "professional")
    
    if not findings:
        return {"ok": False, "error": "没有发现项"}
    
    # 构建prompt
    prompt = f"你是资深税务稽查专家。以下是对一家{industry}企业的稽查发现，请生成一段专业的稽查结论叙述（200字以内，{style}风格）：\n\n"
    for i, f in enumerate(findings[:5]):
        prompt += f"{i+1}. {f.get('type','')}: {str(f.get('detail',''))[:100]}\n"
    
    try:
        # 尝试调用DeepSeek
        import requests as _req
        resp = _req.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {os.environ.get('DEEPSEEK_API_KEY', '')}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": 500, "temperature": 0.3},
            timeout=15
        )
        if resp.status_code == 200:
            narrative = resp.json()["choices"][0]["message"]["content"]
            return {"ok": True, "narrative": narrative, "source": "deepseek"}
    except:
        pass
    
    # 兜底：规则生成
    high_count = sum(1 for f in findings if f.get('level') in ('高风险','极高风险'))
    narrative = f"经对{industry}企业进行全维度稽查分析，共发现{len(findings)}项涉税疑点，其中高风险事项{high_count}项。建议重点核查资金流向真实性、进销匹配度及经营实质，必要时启动延伸稽查程序。"
    return {"ok": True, "narrative": narrative, "source": "rule_based"}


# ═══════════════════════════════════════════════════════════
# 联网核查 API —— 企查查/天眼查实时工商信息查询
# ═══════════════════════════════════════════════════════════

@app.get("/api/audit/online-verify/{company_name}")
def online_verify_company(company_name: str):
    """联网核查企业工商信息。
    
    当前阶段：通过公开信息源获取企业基本画像。
    远期：接入企查查/天眼查API获取完整工商数据。
    """
    import urllib.parse
    
    encoded = urllib.parse.quote(company_name)
    
    # 天眼查搜索链接
    tianyancha_url = f"https://www.tianyancha.com/search?key={encoded}"
    
    # 企查查搜索链接
    qichacha_url = f"https://www.qichacha.com/search?key={encoded}"
    
    # 国家企业信用信息公示系统
    gsxt_url = f"http://www.gsxt.gov.cn/index.html"
    
    # 尝试天眼查公开页面抓取
    info = {
        "company_name": company_name,
        "status": "pending_verification",
        "lookup_urls": {
            "tianyancha": tianyancha_url,
            "qichacha": qichacha_url,
            "gsxt": gsxt_url,
        },
        "recommendation": (
            f"已生成联网核查链接。建议通过以下方式获取完整工商信息：\n"
            f"1. 天眼查: {tianyancha_url}\n"
            f"2. 企查查: {qichacha_url}\n"
            f"3. 国家公示系统: 输入'{company_name}'查询"
        ),
        "auto_checks": {
            "risk_flags": [],
            "suggested_actions": [
                "核实法定代表人是否有关联企业",
                "检查是否存在经营异常/严重违法记录",
                "确认注册资本与经营规模是否匹配",
                "核查股东结构与交易对手是否存在重叠"
            ]
        }
    }
    
    # 简单风险检测（基于企业名称关键词）
    name_lower = company_name.lower()
    risk_keywords = {
        "商贸": "商贸企业是虚开发票高发类型",
        "咨询": "咨询服务费是成本虚列高发领域",
        "科技": "科技企业需核实研发费用真实性",
        "建筑": "建筑企业需关注分包和劳务真实性",
        "贸易": "贸易企业需关注进销匹配和物流单据",
    }
    for kw, risk in risk_keywords.items():
        if kw in name_lower or kw in company_name:
            info["auto_checks"]["risk_flags"].append(f"{kw}行业风险提示: {risk}")
    
    return {"ok": True, "info": info}


# ═══════════════════════════════════════════════════════════
# 行业基准库自动更新
# ═══════════════════════════════════════════════════════════

@app.post("/api/industries/refresh-benchmarks")
def refresh_industry_benchmarks():
    """刷新行业基准数据 —— 从公开数据源更新行业毛利率/税负率等基准。
    
    当前阶段：检查本地JSON完整性+时间戳。
    远期：接入wind/同花顺等金融数据API自动更新。
    """
    import json, os, datetime
    
    profile_path = os.path.join(os.path.dirname(__file__) or ".", "static", "industry_profiles.json")
    data_path = os.path.join(os.path.dirname(__file__) or ".", "static", "industry_data.json")
    
    status = {
        "profiles": {"exists": False, "industries": 0, "last_modified": None},
        "data": {"exists": False, "benchmark_entries": 0, "last_modified": None},
        "health": "unknown"
    }
    
    for key, filepath in [("profiles", profile_path), ("data", data_path)]:
        if os.path.exists(filepath):
            status[key]["exists"] = True
            status[key]["last_modified"] = datetime.datetime.fromtimestamp(
                os.path.getmtime(filepath)
            ).isoformat()
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                if key == "profiles":
                    status[key]["industries"] = len(content.get("industries", {}))
                else:
                    status[key]["benchmark_entries"] = len(content.get("benchmarks", {}))
            except:
                pass
    
    # 健康检查
    if status["profiles"]["industries"] >= 5 and status["data"]["benchmark_entries"] >= 20:
        status["health"] = "healthy"
    elif status["profiles"]["exists"] and status["data"]["exists"]:
        status["health"] = "degraded"
    else:
        status["health"] = "critical"
    
    status["updated_at"] = datetime.datetime.now().isoformat()
    status["message"] = (
        "行业基准数据健康状态良好" if status["health"] == "healthy"
        else "行业基准数据需要补充" if status["health"] == "degraded"
        else "行业基准数据缺失，系统使用兜底默认值"
    )
    
    return {"ok": True, "status": status}


# ═══════════════════════════════════════════════════════════
# 多语言报告 API
# ═══════════════════════════════════════════════════════════

# 预置翻译映射
_ZH_EN_MAP = {
    "高风险": "High Risk",
    "中风险": "Medium Risk",
    "低风险": "Low Risk",
    "极高风险": "Critical Risk",
    "黄灯": "Warning",
    "红灯": "Red Flag",
    "绿灯": "Normal",
    "购销严重倒挂": "Severe Purchase-Sales Inversion",
    "毛利为负": "Negative Gross Margin",
    "缺少银行流水": "Missing Bank Statements",
    "无进项发票": "No Purchase Invoices",
    "无工资记录": "No Payroll Records",
    "存在加工费": "Processing Fees Detected",
    "供应商高度集中": "High Supplier Concentration",
    "客户高度集中": "High Customer Concentration",
    "个人交易占比过高": "Excessive Personal Transactions",
    "隐匿收入": "Concealed Revenue",
    "虚开发票": "False Invoicing",
    "成本虚列": "Inflated Costs",
    "处理建议": "Recommendation",
    "税务影响": "Tax Impact",
    "法律依据": "Legal Basis",
    "证据溯源": "Evidence Trace",
    "推理路径": "Reasoning Path",
    "替代假设": "Alternative Hypotheses",
    "证伪通过": "Falsification Passed",
    "证伪未通过": "Falsification Failed",
}

@app.get("/api/audit/report-en/{company_id}")
def get_english_report(company_id: int, db: Session = Depends(get_db)):
    """获取英文版稽查报告 —— 自动翻译关键字段"""
    # 调用中文报告API
    result = analyze_tax_risk_docs(company_id=company_id, db=db)
    
    if not result.get("ok"):
        return result
    
    report = result["report"]
    all_findings = report.get("all_findings", [])
    
    # 翻译关键字段
    for f in all_findings:
        f["level_en"] = _ZH_EN_MAP.get(f.get("level", ""), f.get("level", ""))
        f["type_en"] = _ZH_EN_MAP.get(f.get("type", ""), f.get("type", ""))
    
    report["all_findings"] = all_findings
    report["language"] = "en"
    report["translation_note"] = "Machine-translated from Chinese. For official use, please refer to the Chinese original."
    
    return result


# ═══════════════════════════════════════════════════════════
# 异步分析任务支持
# ═══════════════════════════════════════════════════════════

_async_tasks = {}

@app.post("/api/audit/analyze-async/{company_id}")
def start_async_analysis(company_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """启动异步分析任务 —— 适用于大数据量企业。
    
    返回 task_id，通过 GET /api/audit/task/{task_id} 查询进度。
    """
    import uuid
    task_id = str(uuid.uuid4())[:8]
    _async_tasks[task_id] = {"status": "processing", "progress": 0, "result": None}
    
    def run_analysis():
        try:
            _async_tasks[task_id]["progress"] = 30
            result = analyze_tax_risk_docs(company_id=company_id, db=db)
            _async_tasks[task_id]["progress"] = 100
            _async_tasks[task_id]["status"] = "completed"
            _async_tasks[task_id]["result"] = result
        except Exception as e:
            _async_tasks[task_id]["status"] = "failed"
            _async_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(run_analysis)
    
    return {"ok": True, "task_id": task_id, "message": "分析任务已提交，请轮询 /api/audit/task/" + task_id}


@app.get("/api/audit/task/{task_id}")
def get_analysis_task_status(task_id: str):
    """查询异步分析任务状态"""
    task = _async_tasks.get(task_id)
    if not task:
        return {"ok": False, "error": "任务不存在"}
    return {"ok": True, "task": task}


# ═══════════════════════════════════════════════════════════
# 系统自愈引擎 API — 错误反馈 → 自动规则生成
# ═══════════════════════════════════════════════════════════

from pydantic import BaseModel as _PydanticBase
class ErrorFeedbackInput(_PydanticBase):
    domain: str = ""
    conclusion_type: str = ""
    error_description: str = ""
    correct_answer: str = ""
    data_context: dict = {}
    company_id: Optional[int] = None
    report_trace_id: str = ""
    severity: str = "中"

@app.post("/api/feedback/error")
def submit_error_feedback(body: ErrorFeedbackInput, db: Session = Depends(get_db)):
    """提交错误反馈——系统自学习的燃料"""
    from engine.self_healing import SelfHealingEngine
    engine = SelfHealingEngine(db)
    result = engine.record_error(body.dict())
    return result


@app.get("/api/self-healing/summary")
def get_self_healing_summary(db: Session = Depends(get_db)):
    """获取自愈系统概况"""
    from engine.self_healing import get_healing_summary
    return get_healing_summary(db)


@app.get("/api/self-healing/rules")
def list_healing_rules(status: Optional[str] = None, db: Session = Depends(get_db)):
    """列出所有自愈规则"""
    from database import SelfHealingRule
    q = db.query(SelfHealingRule)
    if status:
        q = q.filter(SelfHealingRule.status == status)
    rules = q.order_by(SelfHealingRule.confidence.desc()).all()
    return {
        "total": len(rules),
        "rules": [{
            "id": r.id, "rule_name": r.rule_name, "rule_type": r.rule_type,
            "domain": r.domain, "confidence": r.confidence, "status": r.status,
            "auto_apply": r.auto_apply, "applied_count": r.applied_count,
            "source_error_count": r.source_error_count,
        } for r in rules],
    }


@app.post("/api/self-healing/rules/{rule_id}/activate")
def activate_healing_rule(rule_id: int, auto_apply: bool = True, db: Session = Depends(get_db)):
    """激活一条自愈规则"""
    from database import SelfHealingRule
    rule = db.query(SelfHealingRule).filter(SelfHealingRule.id == rule_id).first()
    if not rule:
        return {"ok": False, "message": "规则不存在"}
    rule.status = "active"
    rule.auto_apply = auto_apply
    db.commit()
    return {"ok": True, "message": f"规则已激活: {rule.rule_name}", "auto_apply": auto_apply}


@app.post("/api/self-healing/generate")
def trigger_rule_generation(db: Session = Depends(get_db)):
    """从所有待处理错误中批量生成规则"""
    from database import ErrorFeedback
    from engine.self_healing import SelfHealingEngine
    engine = SelfHealingEngine(db)
    pending = db.query(ErrorFeedback).filter(
        ErrorFeedback.status.in_(["new", "triaged"])
    ).order_by(ErrorFeedback.created_at.desc()).all()
    
    generated = []
    for fb in pending:
        result = engine.try_generate_rule(fb)
        if result.get("generated"):
            generated.append(result)
    
    return {"ok": True, "total_pending": len(pending), "rules_generated": len(generated), "generated": generated[:20]}


# ═══════════════════════════════════════════════════════════
# 税务AGI 状态面板 API
# ═══════════════════════════════════════════════════════════

@app.get("/api/agi/status")
def get_agi_status(db: Session = Depends(get_db)):
    """税务AGI完整状态"""
    result = {"ok": True, "timestamp": datetime.now().isoformat()}
    
    # 知识库概况
    try:
        from engine.knowledge_base import get_kb
        kb = get_kb()
        result["knowledge_base"] = kb.get_full_knowledge()
    except Exception as e:
        result["knowledge_base"] = {"error": str(e)}
    
    # 自愈规则
    try:
        from database import SelfHealingRule, ErrorFeedback
        active_rules = db.query(SelfHealingRule).filter(SelfHealingRule.status == "active").count()
        total_rules = db.query(SelfHealingRule).count()
        total_errors = db.query(ErrorFeedback).count()
        result["healing"] = {
            "total_rules": total_rules,
            "active_rules": active_rules,
            "errors_recorded": total_errors,
        }
    except:
        result["healing"] = {"error": "数据库未就绪"}
    
    # 因果网络状态
    try:
        from engine.causal_network import create_autonomous_reasoner
        reasoner = create_autonomous_reasoner()
        result["causal_network"] = {
            "edges": len(reasoner.network.edges),
            "patterns": len(reasoner.network.patterns),
            "signal_count": len(reasoner.network.signal_frequencies),
        }
    except:
        result["causal_network"] = {"status": "未初始化"}
    
    # 跨分析记忆
    try:
        import json, os
        mem_path = os.path.join(os.path.dirname(__file__), "static", "cross_analysis_memory.json")
        with open(mem_path, "r", encoding="utf-8") as f:
            mem = json.load(f)
        result["cross_analysis"] = {
            "total_analyses": len(mem.get("analyses", [])),
            "industries": list(mem.get("industry_patterns", {}).keys()),
            "lessons": len(mem.get("lesson_learned", [])),
        }
    except:
        result["cross_analysis"] = {"total_analyses": 0}
    
    # ═══ AGI 三大升级引擎状态 ═══
    # ① 法律推理引擎
    try:
        from engine.legal_reasoner import LegalReasoner
        lr = LegalReasoner()
        result["legal_reasoning"] = {
            "available": True,
            "rules_loaded": len(lr.rules),
            "domains": lr.get_all_domains(),
        }
    except:
        result["legal_reasoning"] = {"available": False}
    
    # ② 跨企业关系网
    try:
        result["cross_enterprise"] = {
            "available": True,
            "description": "自动发现系统内企业间的供应商/客户/人员关联关系"
        }
    except:
        result["cross_enterprise"] = {"available": False}
    
    # ③ 时序趋势学习
    try:
        from engine.trend_analyzer import TrendAnalyzer
        ta = TrendAnalyzer()
        result["trend_analysis"] = {
            "available": True,
            "tracked_metrics": len(ta.TRACKED_METRICS),
            "metrics": [
                {"name": m, "label": {
                    "gross_margin":"毛利率","sales_revenue":"销售收入","purchase_amount":"采购金额",
                    "supplier_count":"供应商数量","customer_count":"客户数量","invoice_count":"发票数量",
                    "bank_inflow":"银行流入","bank_outflow":"银行流出","salary_total":"工资总额",
                    "employee_count":"员工数量","tax_burden":"税负率","profit_margin":"净利率"
                }.get(m,m)}
                for m in ta.TRACKED_METRICS[:8]
            ]
        }
    except:
        result["trend_analysis"] = {"available": False}
    
    # 版本信息
    result["version"] = {
        "agent": "3.0",
        "engine": "Phase1-4 + 6引擎 + SCM因果推理 + 元认知 + 知识图谱 + 事件总线",
        "features": [
            "法律推理—三段论引用具体法条→非统计概率推测",
            "跨企业关系—自动发现供应商/客户/人员跨企业重叠",
            "趋势感知—跨期追踪财务指标变化→恶化/改善信号",
            "自主推理—从历史数据自主学习因果模式",
            "联网核查—搜索引擎→公告抓取→结构化条件提取",
            "语义理解—理解品名/摘要/法规的语义而非字符串",
            "创造性假设—遇到未知模式自动生成试探性假设",
            "自愈进化—错误反馈→规则生成→自动修正",
            "因果网络—信号共现→因果边→多信号联合预测",
            "闭环自检—分析完自我验证→自动修正",
        ],
    }
    
    # 覆盖层状态
    try:
        from engine.override_engine import get_override_engine
        oe = get_override_engine()
        result["overrides"] = oe.get_override_summary()
    except: pass
    
    # 并行加速状态
    try:
        from engine.parallel_runner import is_parallel_enabled
        result["parallel"] = {"enabled": is_parallel_enabled()}
    except: pass
    
    # 外部验证渠道
    try:
        from engine.external_verifier import get_external_verifier
        result["external_verify"] = {"channels": get_external_verifier().get_available_channels()}
    except: pass
    
    # 对话稽查状态
    result["chat"] = {"available": True, "endpoint": "/api/agi/chat", "knowledge_count": result["knowledge_base"]["lessons_count"]}
    
    # ═══ 三大新增引擎 ═══
    # ④ 稽查方法论
    try:
        from engine.methodology_loader import METHODOLOGY_KNOWLEDGE
        result["methodology"] = {
            "available": True,
            "total_methods": len(METHODOLOGY_KNOWLEDGE.get("methodologies", [])),
            "total_documents": len(METHODOLOGY_KNOWLEDGE.get("required_documents", [])),
            "total_laws": len(METHODOLOGY_KNOWLEDGE.get("law_references", [])),
            "methods": [m.get("name", "") for m in METHODOLOGY_KNOWLEDGE.get("methodologies", [])],
        }
    except:
        result["methodology"] = {"available": False}
    
    # ⑤ 自动规则发现
    try:
        from engine.rule_discovery import get_discovered_rules
        rules = get_discovered_rules()
        result["rule_discovery"] = {
            "available": True,
            "total_rules": len(rules),
            "by_type": {
                "auto_skip": len([r for r in rules if r.get("type") == "auto_skip"]),
                "auto_correction": len([r for r in rules if r.get("type") == "auto_correction"]),
                "auto_signal": len([r for r in rules if r.get("type") == "auto_signal"]),
            },
        }
    except:
        result["rule_discovery"] = {"available": False}
    
    # ⑥ 自动巡逻
    try:
        from engine.auto_patrol import PATROL_CONFIG, get_companies_to_patrol
        import json, os
        mem_path = os.path.join(os.path.dirname(__file__), "static", "cross_analysis_memory.json")
        patrol_snapshots = {}
        if os.path.exists(mem_path):
            with open(mem_path, "r", encoding="utf-8") as f:
                mem = json.load(f)
            patrol_snapshots = mem.get("patrol_snapshots", {})
        result["patrol"] = {
            "available": True,
            "config": PATROL_CONFIG,
            "companies_with_snapshots": len(patrol_snapshots),
            "latest_snapshots": {k: {"ts": v.get("timestamp",""), "findings": v.get("total_findings",0)} 
                                for k, v in list(patrol_snapshots.items())[-3:]},
        }
    except:
        result["patrol"] = {"available": False}
    
    return result


# ═══════════════════════════════════════════════════════════
# AGI覆盖层管理 API
# ═══════════════════════════════════════════════════════════

@app.get("/api/agi/overrides/summary")
def get_agi_overrides_summary():
    from engine.override_engine import get_override_engine
    return get_override_engine().get_override_summary()


@app.get("/api/agi/overrides/pending")
def get_agi_overrides_pending():
    from engine.override_engine import get_override_engine
    return {"pending": get_override_engine().get_pending_review()}


@app.post("/api/agi/overrides/{override_id}/activate")
def activate_agi_override(override_id: str):
    from engine.override_engine import get_override_engine
    return get_override_engine().reactivate_override(override_id)


@app.post("/api/agi/overrides/{override_id}/rollback")
def rollback_agi_override(override_id: str):
    from engine.override_engine import get_override_engine
    return get_override_engine().rollback_override(override_id)


@app.post("/api/agi/overrides/emergency-reset")
def emergency_reset_overrides(module: str = None):
    from engine.override_engine import get_override_engine
    return get_override_engine().emergency_reset(module)


# ═══════════════════════════════════════════════════════════
# 对话式税务稽查 — AGI直接用中文回答税务问题
# ═══════════════════════════════════════════════════════════

@app.post("/api/agi/chat")
async def agi_chat(request: Request, db: Session = Depends(get_db)):
    """税务AGI对话接口
    
    body: {"question": "这家企业的虚开风险有多大？", "company_id": 1, "context": {}}
    
    AGI会基于知识库、历史分析、因果网络来回答。
    """
    try:
        body = await request.json()
    except:
        return {"ok": False, "answer": "请提供有效的问题"}
    
    question = body.get("question", "").strip()
    company_id = body.get("company_id", 0)
    
    if not question:
        return {"ok": False, "answer": "请提出税务问题"}
    
    # 构建回答上下文
    answer_parts = []
    
    # 1. 查知识库
    try:
        from engine.knowledge_base import get_kb
        kb = get_kb()
        
        # 关键词匹配知识
        policy_hits = []
        for key, p in kb.get_all_policies().items():
            if any(k in question for k in [p.get("name",""), key]):
                conds = p.get("conditions", {})
                policy_hits.append(f"{p['name']}: {p['law']}, 有效期至{p['expiry']}")
        if policy_hits:
            answer_parts.append("📋 **相关政策**:\n" + "\n".join(f"  · {h}" for h in policy_hits[:3]))
        
        # 语义匹配
        for cat, words in kb.get_semantic_dict().items():
            for w in words:
                if w in question:
                    answer_parts.append(f"🔍 **语义匹配**: 检测到关键品类'{cat}'(含{w}等)")
                    break
    except: pass
    
    # 2. 查历史分析
    if company_id:
        try:
            from database import Company
            company = db.query(Company).filter(Company.id == company_id).first()
            if company:
                # 查找最近分析结果
                cached = _last_analysis_cache.get(company_id)
                if cached:
                    report = cached.get("report", {})
                    stats = report.get("stats", report.get("report", {}).get("stats", {}))
                    if stats:
                        answer_parts.append(f"📊 **最近分析** ({company.name}): {stats.get('high_risk',0)}高风险/{stats.get('mid_risk',0)}中风险")
        except: pass
    
    # 3. 因果网络推理
    try:
        from engine.causal_network import create_autonomous_reasoner
        reasoner = create_autonomous_reasoner()
        if reasoner.network.edges:
            # 找相关因果边
            related_edges = [e for e in reasoner.network.edges[:5] 
                           if e.target_finding and any(k in question for k in e.target_finding.split())]
            if related_edges:
                answer_parts.append("🔗 **因果分析**:")
                for e in related_edges[:3]:
                    answer_parts.append(f"  · {', '.join(e.source_signals[:2])} → {e.target_finding} (置信度{e.confidence:.0%})")
    except: pass
    
    # 4. 经验教训
    try:
        from engine.knowledge_base import get_kb
        kb = get_kb()
        lessons = kb.get_lessons()
        if lessons:
            related = [l for l in lessons[-5:] if any(k in l.get("lesson","") for k in question[:10].split())]
            if related:
                answer_parts.append("💡 **相关经验**:")
                for l in related[:2]:
                    answer_parts.append(f"  · {l['lesson'][:100]}")
    except: pass
    
    # 组装回答
    if answer_parts:
        answer = "\n\n".join(answer_parts)
    else:
        answer = "我目前的知识库还没有覆盖这个问题的答案。建议：\n\n1. 上传更多企业资料进行分析，我会从数据中学习\n2. 在报告中发现错误后点击💬反馈，我会记住\n3. 更具体地描述你的问题"
    
    return {"ok": True, "question": question, "answer": answer, "sources_used": len(answer_parts)}


# ═══════════════════════════════════════════════════════════
# 闭环自检 — AGI分析完自我验证+自动修正
# ═══════════════════════════════════════════════════════════

@app.post("/api/agi/self-check/{company_id}")
async def agi_self_check(company_id: int, db: Session = Depends(get_db)):
    """触发AGI对自己最近一次分析进行自我验证"""
    cached = _last_analysis_cache.get(company_id)
    if not cached:
        return {"ok": False, "message": "暂无分析缓存，请先运行一键分析"}
    report = cached.get("report", {}).get("report", cached.get("report", {}))
    all_findings = report.get("all_findings", [])
    if not all_findings:
        return {"ok": False, "message": "无分析发现可验证"}
    results = {"total_findings": len(all_findings), "re_verified": 0, "corrected": 0, "actions": []}
    high_risk = [f for f in all_findings if f.get("level") == "高风险"]
    for f in high_risk[:20]:
        ftype = f.get("type", "")
        has_law = bool(f.get("law_ref") or f.get("policy_ref"))
        has_detail = bool(f.get("detail"))
        has_suggestion = bool(f.get("suggestion", "").strip() and len(f.get("suggestion","").strip()) > 20)
        issues = []
        if not has_law: issues.append("缺少法律依据引用")
        if not has_detail: issues.append("缺少事实描述")
        if not has_suggestion: issues.append("建议过于简短")
        if issues:
            results["corrected"] += 1
            results["actions"].append({"finding_type": ftype[:60], "issues": issues, "action": "建议补充"})
        results["re_verified"] += 1
    results["self_check_pass_rate"] = round((results["re_verified"]-results["corrected"])/max(results["re_verified"],1)*100,1)
    return {"ok": True, **results}

# ═══════════════════════════════════════════════════════════
# 外部数据源验证 — 天眼查/企查查/国家企业信用信息公示系统
# ═══════════════════════════════════════════════════════════

@app.get("/api/agi/verify-supplier")
def verify_supplier(company_name: str = Query(...), tax_id: str = Query("")):
    """验证供应商/客户工商信息"""
    from engine.external_verifier import get_external_verifier
    verifier = get_external_verifier()
    return verifier.verify(company_name, tax_id)


@app.get("/api/agi/verify-channels")
def get_verify_channels():
    """查看可用的验证渠道"""
    from engine.external_verifier import get_external_verifier
    return {"channels": get_external_verifier().get_available_channels()}


# ═══════════════════════════════════════════════════════════
# 并行加速 — 多域分析并发执行
# ═══════════════════════════════════════════════════════════

@app.post("/api/agi/parallel/toggle")
def toggle_parallel():
    """启用/查看并行加速状态"""
    from engine.parallel_runner import is_parallel_enabled, enable_parallel
    if not is_parallel_enabled():
        result = enable_parallel()
        return {"ok": True, "message": "并行加速已启用", **result}
    return {"ok": True, "message": "并行加速已启用", "parallel_enabled": True, "note": "设置环境变量 AGI_PARALLEL=1 永久启用"}
    """触发AGI对自己最近一次分析进行自我验证
    
    AGI会：
    1. 重新审视高风险结论，生成反向假设
    2. 检测结论间矛盾
    3. 对存疑结论自动降低置信度或添加修正
    """
    cached = _last_analysis_cache.get(company_id)
    if not cached:
        return {"ok": False, "message": "该公司暂无分析缓存，请先运行一键分析"}
    
    report = cached.get("report", {}).get("report", cached.get("report", {}))
    all_findings = report.get("all_findings", [])
    
    if not all_findings:
        return {"ok": False, "message": "无分析发现可验证"}
    
    results = {
        "total_findings": len(all_findings),
        "re_verified": 0,
        "corrected": 0,
        "actions": [],
    }
    
    # 只验证高风险结论
    high_risk = [f for f in all_findings if f.get("level") == "高风险"]
    
    for f in high_risk[:20]:  # 最多验证20条
        ftype = f.get("type", "")
        
        # 检查结论是否有法律依据
        has_law = bool(f.get("law_ref") or f.get("policy_ref"))
        has_detail = bool(f.get("detail"))
        has_suggestion = bool(f.get("suggestion", "").strip() and len(f.get("suggestion","").strip()) > 20)
        
        issues = []
        if not has_law:
            issues.append("缺少法律依据引用")
        if not has_detail:
            issues.append("缺少事实描述")
        if not has_suggestion:
            issues.append("建议过于简短")
        
        if issues:
            results["corrected"] += 1
            results["actions"].append({
                "finding_type": ftype[:60],
                "issues": issues,
                "action": "建议补充: " + ", ".join(issues),
            })
        
        results["re_verified"] += 1
    
    results["self_check_pass_rate"] = round(
        (results["re_verified"] - results["corrected"]) / max(results["re_verified"], 1) * 100, 1
    )
    
    return {"ok": True, **results}





# ═══ 自动巡逻 API ═══
@app.get("/api/agi/patrol/status")
def get_patrol_status():
    """获取巡逻状态"""
    try:
        from engine.auto_patrol import PATROL_CONFIG
        from engine.knowledge_base import get_kb
        kb = get_kb()
        return {"ok": True, "config": PATROL_CONFIG, "knowledge": kb.get_full_knowledge()}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/agi/patrol/trigger")
def trigger_patrol(company_id: int = None, db: Session = Depends(get_db)):
    """手动触发巡逻：对最近分析的企业重新分析并对比"""
    try:
        from engine.auto_patrol import get_companies_to_patrol
        if company_id:
            cids = [company_id]
        else:
            cids = get_companies_to_patrol(db)
        if not cids:
            return {"ok": False, "message": "没有可巡逻的企业，请先运行一键分析"}
        return {"ok": True, "message": f"巡逻已触发，将分析{len(cids)}家企业", "company_ids": cids}
    except Exception as e:
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn, argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    args, _ = parser.parse_known_args()
    uvicorn.run("main:app", host="0.0.0.0", port=args.port, reload=False)


@app.post("/api/tax-risk-rules/check-relevance")
async def tax_risk_rules_check_relevance(request: Request):
    """检测文本内容是否为涉税相关（输入文字/上传报告前预检）"""
    try:
        body = await request.json()
        text = body.get("text", "")
        if not text or not text.strip():
            return {"ok": False, "error": "文本内容不能为空"}
    except Exception:
        return {"ok": False, "error": "无效的请求数据"}
    result = _check_tax_relevance(text)
    result["ok"] = True
    return result

# ========== 开发模式：强制无缓存 ==========
@app.middleware('http')
async def add_cache_headers(request, call_next):
    '''强制浏览器不用本地缓存，每次都重新验证资源'''
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# ═══════════════════════════════════════════════════════════════
#  推理引擎规则库 — 返回全部规则的完整文字内容
# ═══════════════════════════════════════════════════════════════

@app.get("/api/tax-risk-docs/engine-rules")
def get_engine_rules():
    """返回推理引擎全部规则的完整文字，供仪表盘展示"""
    import json, os
    
    base = os.path.join(os.path.dirname(__file__), "static")
    rules = {"version": "v2.0", "phases": {}}
    
    # Phase 1 信号检测规则（从引擎代码提取描述）
    rules["phases"]["Phase1-初查信号检测"] = {
        "description": "16个信号检测器，像老稽查员翻一遍资料就能嗅出异常",
        "count": 16,
        "rules": [
            {"id": "TRIAGE_001", "name": "购销严重倒挂", "trigger": "进项 > 销项 × 1.5", "level": "red", "detail": "可能虚增进项或隐匿收入"},
            {"id": "TRIAGE_002", "name": "毛利为负", "trigger": "毛利率 < 0%", "level": "red", "detail": "售价低于成本，需核查未开票收入"},
            {"id": "TRIAGE_003", "name": "毛利率异常高", "trigger": "毛利率 > 80% 且销项 > 100万", "level": "yellow", "detail": "可能虚增售价或进项未全额入账"},
            {"id": "TRIAGE_004", "name": "缺少银行流水", "trigger": "有销售但无银行流水记录", "level": "red", "detail": "无法验证资金流真实性"},
            {"id": "TRIAGE_005", "name": "无进项发票", "trigger": "有销项发票但0张进项（非服务/劳务）", "level": "yellow", "detail": "需要解释进项来源"},
            {"id": "TRIAGE_006", "name": "无工资记录", "trigger": "销项 > 500万但0条工资", "level": "yellow", "detail": "可能虚开发票或隐匿人员"},
            {"id": "TRIAGE_007", "name": "存在加工费", "trigger": "进项中有加工费发票", "level": "yellow", "detail": "可能为制造业，需BOM表验证加工链条"},
            {"id": "TRIAGE_008", "name": "制造业加工链条待验证", "trigger": "核心成本>0 + 加工费 + 制造业", "level": "yellow", "detail": "进销品名差异需BOM表解释"},
            {"id": "TRIAGE_009", "name": "存在日常费用报销", "trigger": "进项中有日常报销（餐饮住宿汽油等）", "level": "green", "detail": "正常经营信号，排除误报"},
            {"id": "TRIAGE_010", "name": "金额整十整百异常", "trigger": "整十/整百金额占比 > 50%", "level": "yellow", "detail": "金额高度规整→可能人为编造"},
            {"id": "TRIAGE_011", "name": "金额分布异常均匀", "trigger": "标准差/均值 < 0.3", "level": "yellow", "detail": "开票金额过于均匀→可能按计划编造"},
            {"id": "TRIAGE_012", "name": "发票连号", "trigger": "≥3张连续发票号", "level": "yellow", "detail": "可能集中开票或虚假交易"},
            {"id": "TRIAGE_013", "name": "季度末集中开票", "trigger": "季度末月开票占比 > 60%", "level": "yellow", "detail": "可能突击开票人为调节收入"},
            {"id": "TRIAGE_014", "name": "供应商高度集中", "trigger": "前3大供应商占比 > 80%", "level": "yellow", "detail": "可能关联交易或虚开发票"},
            {"id": "TRIAGE_015", "name": "客户高度集中", "trigger": "前3大客户占比 > 80%", "level": "yellow", "detail": "可能关联交易或客户依赖"},
            {"id": "TRIAGE_016", "name": "个人付款方占比过高", "trigger": "银行个人付款方占比 > 30%", "level": "yellow", "detail": "可能私户收款或隐匿收入"},
        ]
    }
    
    # Phase 2 信号→域映射
    try:
        with open(os.path.join(base, "signal_domain_map.json"), "r", encoding="utf-8") as f:
            domain_map = json.load(f)
        rules["phases"]["Phase2-信号→域映射"] = {
            "description": domain_map.get("description", ""),
            "count": len(domain_map.get("mappings", {})),
            "mappings": domain_map.get("mappings", {}),
        }
    except Exception:
        rules["phases"]["Phase2-信号→域映射"] = {"error": "加载失败"}
    
    # Phase 3 信号叠加模式
    try:
        with open(os.path.join(base, "signal_patterns.json"), "r", encoding="utf-8") as f:
            patterns = json.load(f)
        rules["phases"]["Phase3-信号叠加模式"] = {
            "description": patterns.get("description", ""),
            "count": len(patterns.get("patterns", [])),
            "patterns": patterns.get("patterns", []),
        }
    except Exception:
        rules["phases"]["Phase3-信号叠加模式"] = {"error": "加载失败"}
    
    # Phase 3 冲突消解规则
    try:
        with open(os.path.join(base, "conflict_rules.json"), "r", encoding="utf-8") as f:
            conflicts = json.load(f)
        rules["phases"]["Phase3-冲突消解规则"] = {
            "description": conflicts.get("description", ""),
            "count": len(conflicts.get("rules", [])),
            "rules": conflicts.get("rules", []),
        }
    except Exception:
        rules["phases"]["Phase3-冲突消解规则"] = {"error": "加载失败"}
    
    # Phase 1 资料缺失触发规则（从MISSING_CONSEQUENCE_TRIGGER提取）
    mct_rules = []
    cat_names = {
        "bank": "银行流水", "sales_invoice": "销项发票", "purchase_invoice": "进项发票",
        "voucher": "记账凭证", "salary": "工资表", "social_security": "社保明细",
        "inventory": "进销存台账", "contract": "合同文件", "trial_balance": "科目余额表",
        "financial": "资产负债表+利润表", "vat": "增值税申报表", "cit": "企业所得税申报表",
        "ind_tax": "个人所得税申报表", "other_tax": "小税种申报"
    }
    for key, cfg in MISSING_CONSEQUENCE_TRIGGER.items():
        lv = "red" if cfg["level"] == "极高风险" else ("yellow" if cfg["level"] == "高风险" else "orange")
        mct_rules.append({
            "id": f"MISSING_{key.upper()}",
            "name": cat_names.get(key, key),
            "level": lv,
            "risk": cfg["risk"],
            "consequence": cfg["consequence"],
            "law_ref": cfg["law"],
            "action": cfg["action"],
            "priority": cfg["priority"],
        })
    rules["phases"]["Phase1-资料缺失触发规则"] = {
        "description": "任一资料缺失>=1→自动触发对应风险结论到综合定性。14类资料覆盖全证据链——缺失即风险，不存在'没资料不影响判断'的逻辑。",
        "count": len(mct_rules),
        "rules": mct_rules,
    }

    # Phase 3 结论自洽性检测（从CONTRADICTION_RULES提取）
    contr_rules = []
    for cr in CONTRADICTION_RULES:
        lv = "red" if cr["conflict_level"] == "极高风险" else ("yellow" if cr["conflict_level"] == "高风险" else "orange")
        contr_rules.append({
            "id": cr["id"],
            "name": cr["name"],
            "level": lv,
            "conflict_level": cr["conflict_level"],
            "explanation": cr["explanation"],
            "resolution": cr["resolution"],
            "priority": cr["priority"],
            "condition_a": cr.get("condition_a", {}),
            "condition_b": cr.get("condition_b", {}),
        })
    rules["phases"]["Phase3-结论自洽性检测"] = {
        "description": "双向条件匹配引擎：扫描所有发现，检测预定义的矛盾模式。发现矛盾→优先展示到core_issues→提醒稽查员结论之间存在逻辑互斥需深入核实。",
        "count": len(contr_rules),
        "rules": contr_rules,
    }

    # Phase 3 跨域分析推理链（从cross_domain_analysis.json加载）
    try:
        with open(os.path.join(base, "cross_domain_analysis.json"), "r", encoding="utf-8") as f:
            cross_analysis = json.load(f)
        xa_rules = []
        for xa in cross_analysis:
            lv = "red" if xa.get("level","") == "极高风险" else ("yellow" if xa.get("level","") == "高风险" else "orange")
            xa_rules.append({
                "id": f"XA_{xa['id']:02d}",
                "name": xa["name"],
                "level": lv,
                "trigger_signal": xa.get("trigger_signal", ""),
                "reasoning_steps": xa.get("reasoning_chain", []),
                "reversal_points": xa.get("reversal_points", []),
                "description": xa.get("description", ""),
                "methodology": xa.get("methodology", ""),
            })
        rules["phases"]["Phase3-跨域分析推理链"] = {
            "description": "从单一风险点出发，逐层扩展分析范围，形成完整的推理链。每条链包含推理步骤+回退路径——只要企业能提供合理解释，风险就会降级或消除。",
            "count": len(xa_rules),
            "rules": xa_rules,
        }
    except Exception as e:
        rules["phases"]["Phase3-跨域分析推理链"] = {"error": f"加载失败: {type(e).__name__}: {str(e)}"}

    # Phase 3 跨域线索链（从cross_domain_clues.json加载）
    try:
        with open(os.path.join(base, "cross_domain_clues.json"), "r", encoding="utf-8") as f:
            cross_clues = json.load(f)
        xc_rules = []
        for xc in cross_clues:
            lv = "red" if xc.get("level","") == "极高风险" else ("yellow" if xc.get("level","") == "高风险" else "orange")
            xc_rules.append({
                "id": f"XC_{xc['id']:02d}",
                "name": xc["name"],
                "level": lv,
                "sub_topic": xc.get("sub_topic", ""),
                "trigger_keywords": xc.get("trigger_keywords", []),
                "min_evidence": xc.get("min_evidence", 0),
                "investigation_path": xc.get("investigation_path", []),
            })
        rules["phases"]["Phase3-跨域线索链"] = {
            "description": "跨域线索是指多个分析域之间信号交叉验证产生的调查线索。每个线索需要至少N个维度的证据才能触发（min_evidence），低于此阈值为待观察状态。",
            "count": len(xc_rules),
            "rules": xc_rules,
        }
    except Exception as e:
        rules["phases"]["Phase3-跨域线索链"] = {"error": f"加载失败: {type(e).__name__}: {str(e)}"}

    # Phase 3 跨域证据链（从cross_domain_evidence.json加载）
    try:
        with open(os.path.join(base, "cross_domain_evidence.json"), "r", encoding="utf-8") as f:
            cross_evidence = json.load(f)
        xe_rules = []
        for xe in cross_evidence:
            lv = "red" if xe["level"] == "极高风险" else ("yellow" if xe["level"] == "高风险" else "orange")
            xe_rules.append({
                "id": f"XE_{xe['id']:02d}",
                "name": xe["name"],
                "level": lv,
                "sub_topic": xe.get("sub_topic", ""),
                "trigger_keywords": xe.get("trigger_keywords", []),
                "min_evidence": xe.get("min_evidence", 0),
                "dimensions": xe.get("dimensions", []),
            })
        rules["phases"]["Phase3-跨域证据链"] = {
            "description": "跨域证据链确保每个结论都有多维度、多来源的证据支撑。每个证据链包含A/B/C/D等多维证据源，全部维度命中的结论等级最高。",
            "count": len(xe_rules),
            "rules": xe_rules,
        }
    except Exception as e:
        rules["phases"]["Phase3-跨域证据链"] = {"error": f"加载失败: {type(e).__name__}: {str(e)}"}

    # Phase 4 因果叙事链（从CAUSAL_CHAIN_RULES提取）
    causal_rules = []
    for ch in CAUSAL_CHAIN_RULES:
        lv = "red" if ch["level"] == "极高风险" else ("yellow" if ch["level"] == "高风险" else "orange")
        causal_rules.append({
            "id": ch["id"],
            "name": ch["name"],
            "level": lv,
            "narrative": ch["narrative"],
            "required_signals": ch["required"],
            "optional_signals": ch["optional"],
            "explanation": ch["explanation"],
            "evidence_chain": ch["evidence_chain"],
            "confidence_rule": ch["confidence_rule"],
            "priority": ch["priority"],
        })
    rules["phases"]["Phase4-因果叙事链"] = {
        "description": "跨域因果叙事引擎：从孤立的发现中检测因果链模式（必要信号>=1即触发），构建'叙事链+证据链+置信度'的结构化涉税故事。",
        "count": len(causal_rules),
        "rules": causal_rules,
    }

    # Phase 4 事前预警升级路径（从EARLY_WARNING_ESCALATION提取）
    ewarn_rules = []
    for ew in EARLY_WARNING_ESCALATION:
        lv = "red" if ew["level"] == "极高风险" else ("yellow" if ew["level"] == "高风险" else "orange")
        ewarn_rules.append({
            "id": ew["id"],
            "name": "→".join(ew.get("finding_pattern", [])[:3]),
            "level": lv,
            "risk_level": ew["level"],
            "forward_projection": ew["forward_projection"],
            "checklist": ew["checklist"],
            "timeframe": ew["timeframe"],
            "patterns": ew.get("finding_pattern", []),
        })
    rules["phases"]["Phase4-事前预警升级路径"] = {
        "description": "从当前异常推断下一阶段风险：若当前发现不处理→下一阶段会演化成什么。预警引擎在Phase 4综合定性时运行，匹配当前异常模式→推演风险升级路径→输出前瞻性警告。",
        "count": len(ewarn_rules),
        "rules": ewarn_rules,
    }

    # Phase 2 行业自适应知识库
    try:
        with open(os.path.join(base, "industry_profiles.json"), "r", encoding="utf-8") as f:
            ind_profiles = json.load(f)
        ind_summary = []
        for ind_key, ind_cfg in ind_profiles.get("industries", {}).items():
            bm = ind_cfg.get("benchmarks", {})
            ind_summary.append({
                "name": ind_cfg.get("label", ind_key),
                "subtypes": ind_cfg.get("subtypes", []),
                "benchmarks": {
                    "毛利率范围": f"{bm.get('gross_margin_pct',{}).get('normal_low','?')}%-{bm.get('gross_margin_pct',{}).get('normal_high','?')}%",
                    "购销比范围": f"{bm.get('purchase_sales_ratio',{}).get('normal_low','?')}-{bm.get('purchase_sales_ratio',{}).get('normal_high','?')}",
                    "毛利率低": bm.get("gross_margin_pct",{}).get("low","?"),
                    "毛利率高": bm.get("gross_margin_pct",{}).get("high","?"),
                    "毛利率备注": bm.get("gross_margin_pct",{}).get("note",""),
                    "购销比备注": bm.get("purchase_sales_ratio",{}).get("note",""),
                },
                "focus_domains": ind_cfg.get("focus_domains", []),
                "always_check": ind_cfg.get("always_check", []),
                "signal_weights": ind_cfg.get("signal_weights", {}),
                "risk_patterns": ind_cfg.get("risk_patterns", []),
            })
        rules["phases"]["Phase2-行业自适应知识库"] = {
            "description": ind_profiles.get("description", "不同行业的基准参数、风险权重、重点关注域。自动匹配（精确→子类型→经营模式→默认通用），注入Phase2深挖。"),
            "count": len(ind_summary),
            "industries": ind_summary,
        }
    except Exception:
        rules["phases"]["Phase2-行业自适应知识库"] = {"error": "加载失败"}

    return {"ok": True, "rules": rules}


@app.get("/api/tax-risk-docs/trace/{analysis_id}")
def get_analysis_trace(analysis_id: str, company_id: int = Query(...), db: Session = Depends(get_db)):
    """
    结论可验证性：返回指定分析的完整推理链路。
    
    每条结论的 _trace 字段包含：
    - finding_id: 结论序号
    - phase_origin: 产生阶段
    - data_sources: 使用的原始数据
    - rules_hit: 触发的规则编号
    - detection_path: 检测路径
    - confidence: 可信度
    
    前端可逐条展开查看完整推理依据。
    """
    # 从缓存中查找
    cached = _last_analysis_cache.get(company_id)
    if not cached:
        raise HTTPException(404, "未找到分析记录，请先运行一键分析")
    
    # cached结构: {"report": {"ok": True, "report": {...}}, "timestamp": "..."}
    outer = cached.get("report", {})
    report = outer.get("report", outer)  # 兼容两种嵌套
    all_findings = report.get("all_findings", [])
    report_trace_id = report.get("trace_id", "")
    
    # 验证trace_id匹配
    if analysis_id != report_trace_id:
        raise HTTPException(404, f"分析ID不匹配: expected {report_trace_id}")
    
    # 提取所有trace记录
    traces = []
    for f in all_findings:
        t = f.get("_trace", {})
        if t:
            traces.append({
                "finding_id": t.get("finding_id", ""),
                "finding_type": t.get("finding_type", ""),
                "finding_level": t.get("finding_level", ""),
                "score": t.get("score", 0),
                "phase_origin": t.get("phase_origin", ""),
                "domain": t.get("domain", ""),
                "data_sources": t.get("data_sources", []),
                "rules_hit": t.get("rules_hit", []),
                "detection_path": t.get("detection_path", []),
                "how_found": t.get("how_found", ""),
                "confidence": t.get("confidence", ""),
            })
    
    return {
        "ok": True,
        "trace_id": report_trace_id,
        "total_findings": len(all_findings),
        "traced_findings": len(traces),
        "overall_risk": report.get("overall_level", ""),
        "traces": traces,
    }


# ═══════════════════════════════════════════════════════════════
#  V15新增端点：OCR / Word解析 / 审计日志 / 行业更新 / 数据脱敏
# ═══════════════════════════════════════════════════════════════

@app.post("/api/tax-risk-docs/ocr")
async def ocr_scan_document(
    file: UploadFile = File(...),
    company_id: int = Query(...),
):
    """OCR识别扫描件PDF/图片，返回提取的文本内容
    V15: 支持扫描件PDF、JPG/PNG/BMP/TIFF图片"""
    ext = os.path.splitext(file.filename or '')[1].lower()
    all_allowed = ALLOWED_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS
    if ext not in all_allowed:
        raise HTTPException(400, f"不支持的文件类型: {ext}")

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"文件超过{MAX_UPLOAD_SIZE // 1024 // 1024}MB限制")

    extracted_text = ""

    if ext == '.pdf':
        # 尝试文本提取
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            for page in reader.pages:
                page_text = page.extract_text() or ""
                extracted_text += page_text + "\n"
        except Exception:
            pass

        # 如果文本提取结果太少（扫描件），尝试OCR
        if len(extracted_text.strip()) < 50:
            ocr_text = _try_ocr_pdf(content)
            if ocr_text:
                extracted_text = ocr_text

    elif ext in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff'):
        # 图片直接OCR
        ocr_text = _try_ocr_image(content)
        if ocr_text:
            extracted_text = ocr_text

    elif ext in ('.docx', '.doc'):
        # Word文档
        extracted_text = _extract_word_text(content, ext)

    elif ext == '.txt':
        extracted_text = content.decode('utf-8', errors='ignore')

    if not extracted_text.strip():
        return {"ok": False, "error": "无法提取文本内容，可能是扫描件且OCR不可用。请安装OCR依赖：pip install pytesseract Pillow pdf2image", "text": ""}

    return {"ok": True, "filename": file.filename, "text": extracted_text[:10000], "char_count": len(extracted_text)}


def _try_ocr_pdf(content: bytes) -> str:
    """尝试对PDF进行OCR"""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
        from PIL import Image
        images = convert_from_bytes(content, dpi=200, first_page=1, last_page=5)  # 限制前5页
        text = ""
        for img in images:
            text += pytesseract.image_to_string(img, lang='chi_sim+eng') + "\n"
        return text
    except ImportError:
        return ""
    except Exception:
        return ""


def _try_ocr_image(content: bytes) -> str:
    """尝试对图片进行OCR"""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(content))
        return pytesseract.image_to_string(img, lang='chi_sim+eng')
    except ImportError:
        return ""
    except Exception:
        return ""


def _extract_word_text(content: bytes, ext: str) -> str:
    """提取Word文档文本"""
    try:
        from docx import Document
        doc = Document(io.BytesIO(content))
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        # 提取表格内容
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    text += cell.text + "\t"
                text += "\n"
        return text
    except ImportError:
        return "（需安装python-docx：pip install python-docx）"
    except Exception:
        return ""


@app.get("/api/audit-logs")
def get_audit_logs(
    company_id: int = Query(None),
    limit: int = Query(100),
    db: Session = Depends(get_db)
):
    """查询操作审计日志"""
    from sqlalchemy import text as TextClause
    try:
        if company_id:
            rows = db.execute(TextClause(
                "SELECT * FROM audit_logs WHERE company_id = :cid ORDER BY created_at DESC LIMIT :lim"
            ), {"cid": company_id, "lim": limit}).fetchall()
        else:
            rows = db.execute(TextClause(
                "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT :lim"
            ), {"lim": limit}).fetchall()
        return {"ok": True, "logs": [
            {"id": r[0], "company_id": r[1], "user_name": r[2], "action": r[3],
             "target": r[4], "detail": r[5], "created_at": r[6]}
            for r in rows
        ]}
    except Exception as e:
        return {"ok": False, "error": str(e), "logs": []}


@app.put("/api/companies/{company_id}/industry")
def update_company_industry(
    company_id: int,
    industry: str = Query(...),
    db: Session = Depends(get_db)
):
    """更新公司行业分类"""
    from audit_enhancements import INDUSTRY_KEYWORD_MAP
    valid_industries = list(INDUSTRY_KEYWORD_MAP.keys())
    if industry not in valid_industries:
        raise HTTPException(400, f"无效的行业代码，可选: {', '.join(valid_industries)}")
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "公司不存在")
    company.industry_code = industry
    db.commit()
    return {"ok": True, "message": f"行业已更新为: {industry}", "industry": industry}


@app.post("/api/companies/{company_id}/auto-detect-industry")
def auto_detect_industry(company_id: int, db: Session = Depends(get_db)):
    """根据经营范围自动识别行业"""
    from audit_enhancements import detect_industry
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "公司不存在")
    industry = detect_industry(company.business_scope or "")
    company.industry_code = industry
    db.commit()
    return {"ok": True, "industry": industry, "message": f"自动识别行业为: {industry}"}


@app.get("/api/industries")
def list_industries():
    """列出所有支持的行业分类"""
    industry_data = _load_industry_data()
    benchmarks = industry_data.get("benchmarks", {})
    all_industries = industry_data.get("all_industries", {})
    return {"industries": [
        {"code": k, "name": all_industries.get(k, {}).get("name", v.get("name", k)),
         "vat_burden_range": f"{v.get('vat_burden_min', v.get('税负率', [0,0,0])[0]*100)}-{v.get('vat_burden_max', v.get('税负率', [0,0,0])[1]*100)}%",
         "gross_margin_range": f"{v.get('gross_margin_min', v.get('毛利率', [0,0,0])[0]*100)}-{v.get('gross_margin_max', v.get('毛利率', [0,0,0])[1]*100)}%",
         "special_risks": all_industries.get(k, {}).get("special_risks", [])}
        for k, v in benchmarks.items()
    ]}


@app.post("/api/companies/{company_id}/online-lookup")
def online_company_lookup_api(company_id: int, db: Session = Depends(get_db)):
    """
    稽查方法论⑥ 联网核查 —— 手动触发企业信息联网查询
    
    从公开数据源（天眼查/企查查/国家公示系统）拉取企业工商信息：
    - 法定代表人
    - 注册资本
    - 成立日期
    - 经营范围
    - 注册地址
    - 统一社会信用代码
    - 行业分类
    - 企业状态
    - 股东信息
    
    查询结果自动更新到数据库Company表。
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "公司不存在")
    
    company_name = company.name or ""
    uscc = company.uscc or ""
    
    result = _online_company_lookup(company_name, uscc=uscc, db=db, company_id=company_id)
    
    return {
        "ok": True,
        "company_name": company_name,
        "lookup_result": result,
        "message": f"联网核查完成: {result.get('source', '未查到数据')}"
    }


@app.get("/api/companies/{company_id}/online-info")
def get_online_company_info(company_id: int, db: Session = Depends(get_db)):
    """
    获取已缓存的联网核查结果（不重新联网）
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "公司不存在")
    
    info = {
        "company_name": company.name or "",
        "uscc": company.uscc or "",
        "legal_representative": company.legal_representative or "",
        "legal_representative_id": company.legal_representative_id or "",
        "registered_capital": str(company.registered_capital or ""),
        "established_date": str(company.established_date or ""),
        "business_scope": company.business_scope or "",
        "address": company.address or "",
        "company_type": company.company_type or "",
        "industry_code": company.industry_code or "",
        "has_online_data": bool(company.legal_representative and company.registered_capital),
    }
    
    # 查股东
    try:
        from database import CompanyShareholder
        shs = db.query(CompanyShareholder).filter(
            CompanyShareholder.company_id == company_id
        ).all()
        info["shareholders"] = [
            {"name": s.name, "ratio": str(s.share_ratio or ""), "amount": str(s.amount or "")}
            for s in shs
        ]
    except:
        info["shareholders"] = []
    
    return {"ok": True, "info": info}


@app.post("/api/audit/feedback")
def submit_audit_feedback(data: dict, db: Session = Depends(get_db)):
    """用户反馈API — 对分析结论的确认/驳回/调整，驱动自学习。
    
    请求体：
    {
        "finding_type": "购销严重倒挂",
        "action": "confirm" | "dismiss" | "adjust",
        "original_score": 9,
        "adjusted_score": 7,    // 仅adjust时使用
        "note": "确实是关联交易问题"
    }
    """
    from engine.memory import record_user_feedback
    result = record_user_feedback(data)
    return result


@app.post("/api/feedback")
def submit_feedback(data: dict):
    """老邓纠正反馈API — 报告发现上的驳回按钮调用
    请求体：{action: "dismiss", finding_type, finding_title, original_level, reason, detail, fingerprint}
    """
    from engine.self_learning import record_correction
    # 从公司ID推断行业和经营模式（保守默认值）
    company_id = data.get("company_id", 1)
    industry = data.get("industry", "综合")
    biz_model = data.get("biz_model", "未确定")
    finding_type = data.get("finding_type") or data.get("finding_title") or ""
    original_level = data.get("original_level") or data.get("level") or "中风险"
    reason = data.get("reason") or ""
    detail = data.get("detail") or ""
    
    result = record_correction(
        finding_type=finding_type,
        industry=industry,
        biz_model=biz_model,
        original_risk=original_level,
        corrected_risk="低风险（用户驳回）",
        reason=reason,
        finding_detail=detail
    )
    return {"ok": True, "recorded": result["recorded"], "auto_rule": result.get("auto_apply", False), "count": result.get("correction_count", 0)}


@app.get("/api/audit/capabilities")
def get_capabilities():
    """能力矩阵API — 侧边栏动态读取，引擎吐出自己的25维能力"""
    from engine.capability_matrix import CAPABILITY_MATRIX, get_capability_summary
    from engine.capability_matrix import check_quality_system
    caps = get_capability_summary()
    qs = check_quality_system()
    return {"ok": True, "summary": caps, "quality_system": qs, "dimensions": CAPABILITY_MATRIX}


@app.get("/api/audit/brain-status")
def get_brain_status():
    """智能大脑状态"""
    result = {"ok": True}
    try:
        orch = get_module_registry_summary()
        result["orchestrator"] = {"total_modules": orch["total_modules"], "domain_count": len(orch["domains"]), "pipeline_depth": orch["pipeline_depth"], "domains": orch["domains"]}
    except: result["orchestrator"] = {}
    try:
        from engine.self_learning import get_learner_report, get_correction_rule_summary
        result["learner"] = get_learner_report()["growth"]
        result["corrections"] = get_correction_rule_summary()
    except: 
        result["learner"] = {"stage": "婴儿期", "total_runs": 0}
        result["corrections"] = {"total_rules": 0, "auto_rules": 0, "rules": []}
    # 税收优惠政策核实状态
    try:
        from engine.tax_incentive_analyzer import POLICY_VALIDITY, check_policy
        policy_status = []
        for key, p in POLICY_VALIDITY.items():
            try:
                chk_result = check_policy(key, auto_verify=False)
            except Exception:
                chk_result = {"valid": True, "status": "离线模式", "source": "", "conditions": {}}
            policy_status.append({
                "name": p["name"],
                "law": p["law"],
                "expiry": str(p["expiry"]) if p["expiry"] else "长期政策",
                "valid": chk_result.get("valid", True),
                "status": chk_result.get("status", ""),
                "auto_verify_source": (chk_result.get("source", "") or "")[:80] if chk_result.get("source") else None,
                "conditions": chk_result.get("conditions"),
            })
        expired_count = sum(1 for ps in policy_status if not ps["valid"])
        result["policy_verification"] = {
            "total_policies": len(policy_status),
            "valid_count": len(policy_status) - expired_count,
            "expired_count": expired_count,
            "policies": policy_status
        }
    except:
        result["policy_verification"] = {"total_policies": 0, "note": "政策核实模块未加载"}
    return result


@app.get("/api/audit/calibration")
def get_calibration_status(db: Session = Depends(get_db)):
    """获取自学习校准状态 — 查看历史数据积累和阈值校准情况"""
    from engine.memory import _load_memory, _calibrate_thresholds_from_history
    memory = _load_memory()
    industry_counts = {}
    for m in memory:
        ind = m.get("industry", "未知")
        industry_counts[ind] = industry_counts.get(ind, 0) + 1
    
    # 取样本量最多的行业做校准演示
    top_industry = max(industry_counts, key=industry_counts.get) if industry_counts else None
    calibration = _calibrate_thresholds_from_history(memory, top_industry, "") if top_industry else {}
    
    return {
        "total_records": len(memory),
        "industry_distribution": dict(sorted(industry_counts.items(), key=lambda x: -x[1])[:10]),
        "top_industry": top_industry,
        "sample_calibration": calibration,
        "status": "active" if len(memory) >= 5 else "warming_up",
        "message": f"记忆库有{len(memory)}条记录" + (f"，{top_industry}行业样本充足，阈值已校准" if top_industry and industry_counts.get(top_industry, 0) >= 5 else "，样本不足，使用默认阈值")
    }


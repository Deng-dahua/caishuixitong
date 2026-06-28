"""
稽查分析管道 — _run_analyze 核心引擎 + 辅助函数
从 main.py 提取，所有函数为纯分析逻辑
"""
from collections import defaultdict, Counter
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from typing import Optional, List, Dict, Any, Tuple
import json, os, re, math, uuid, hashlib, traceback, logging, io, time, ssl, urllib.request, urllib.parse

from database import (
    get_db, SessionLocal,
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

from engine.domain_analysis import *  # 35域分析函数
# 项目根目录（engine/ 子目录需要回退一层才能访问 static/ 和根级文件）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from shared_state import _CHINA_CITIES_UNIFIED, _CHINA_CITY_REGEX, _last_analysis_cache, _tax_risk_docs  # 共享全局状态

def _run_analyze(company_id, db, progress_callback=None):
    from database import VATDeclaration
    from collections import defaultdict
    # 懒加载 main.py 中的私有函数（避免循环导入）
    from main import (
        _get_company_upload_dir, _get_row_values, _infer_columns_from_data,
        _parse_excel_structured, _parse_pdf_bank_statement, _save_to_transfer,
        _score_tax_relevance,
    )
    from engine.main_biz_cost import identify_main_biz_cost
    from engine.phase1_triage import _phase1_triage
    from engine.phase2_deep_dive import _phase2_deep_dive
    from engine.phase3_cross_validate import _phase3_cross_validate
    from engine.phase4_synthesis import _phase4_synthesis
    from engine.orchestrator import build_data_profile, build_orchestration_plan
    from engine.memory import save_analysis_memory, query_similar_cases
    from engine.context import AuditContext
    
    def _report(progress, msg):
        """报告进度"""
        if progress_callback:
            try: progress_callback(progress, msg)
            except: pass

    # ── NEW ENGINE MARKER: 2026-06-23 Phase 1-4 Reasoning Engine ──
    _NEW_ENGINE_VERSION = True
    ctx = None  # AuditContext 将在 Phase 1 初始化，在此之前为 None
    
    # ── 结论可验证性：生成本次分析的 trace_id ──
    analysis_trace_id = str(uuid.uuid4())[:8]
    _analysis_traces = []  # 收集所有finding的推理链路
    
    # 直接从磁盘扫描文件列表——不依赖全局 _tax_risk_docs 状态
    # 使用公司专属子目录物理隔离，防止不同公司数据串混
    company_upload_dir = _get_company_upload_dir(company_id)
    docs = []
    if os.path.exists(company_upload_dir):
        for fname in os.listdir(company_upload_dir):
            if not os.path.isfile(os.path.join(company_upload_dir, fname)):
                continue
            parts = fname.split("_", 2)
            if len(parts) < 3: continue
            try: f_cid = int(parts[0]); f_doc_id = int(parts[1])
            except: continue
            orig_name = parts[2]
            fpath = os.path.join(company_upload_dir, fname)
            if os.path.isfile(fpath):
                docs.append({
                    "id": f_doc_id, "filename": fname, "original_name": orig_name,
                    "path": fpath, "company_id": f_cid
                })
    if not docs: return {"ok": False, "message": "暂无上传资料"}
    try: db.rollback()
    except Exception: pass

    bank_txs, invoices, salaries, social_security, vouchers, inventory = [], [], [], [], [], []
    input_vat_deductions = []  # 进项认证抵扣独立于进项发票（取票≠认证抵扣）
    contract_data, related_party_data, trial_balance_data = [], [], []
    pipeline_log, file_results = [], []
    
    # ── 🤖 财税智能体 + AGI管线统一初始化 ──
    agent = None  # 保留兼容，由agi_pipeline内部管理
    agent_status = None
    agi_pipeline = None
    agi_init_ok = False
    try:
        from engine.agi_pipeline import create_pipeline
        agi_pipeline = create_pipeline()
        _agi_pipeline_instance = agi_pipeline
        agent = agi_pipeline.init_agent(db)  # 统一入口：管道管理智能体
        agi_init_ok = True
        pipeline_log.append("[AGI] 智能体+34模块管线已统一连接")
    except Exception as _pe:
        pipeline_log.append(f"[AGI] 初始化失败→跳过反思/洞见/知识注入: {_pe}")
        agi_pipeline = None

    # ── NEW ENGINE VERSION CHECK ──
    pipeline_log.append("[ENGINE] 推理引擎v2.0 — Phase1-4 已加载 (2026-06-23)")

    _total_docs = len(docs)
    _report(0, f"开始解析 {_total_docs} 个文件...")
    _doc_idx = 0
    for doc in docs:
        _doc_idx += 1
        fname, fpath, ext = doc["original_name"], doc["path"], os.path.splitext(doc["original_name"])[1].lower()
        if _doc_idx % 5 == 0 or _doc_idx == _total_docs:
            _report(int(_doc_idx * 100 / _total_docs), f"解析文件 {_doc_idx}/{_total_docs}")
        fr = {"file": fname, "type": "unknown", "actions": []}
        parsed = None
        try:
            if ext in (".xls", ".xlsx"):
                parsed, _cached_wb = _parse_excel_structured(fpath, ext, fname, return_wb=True)
                
                # ═══ 兜底：数据内容推断 ═══
                # 当所有解析器失败（unknown或0行），复用已打开的workbook（避免重复打开慢）
                if (parsed is None or len(parsed.get("rows", [])) == 0) and _cached_wb is not None:
                    try:
                        if ext == ".xls":
                            _s = _cached_wb.sheet_by_index(0)
                            _nrows = _s.nrows
                        else:
                            _s = _cached_wb[_cached_wb.sheetnames[0]]
                            _nrows = _s.max_row
                        col_roles = _infer_columns_from_data(_s, _nrows)
                        if col_roles:
                            # 用推断的列角色尝试提取数据
                            rows = []
                            _header = _get_row_values(_s, 0)
                            for _r in range(1, min(_nrows, 200)):
                                _vals = {}
                                for _ci, _roles in col_roles.items():
                                    try:
                                        _v = _get_row_values(_s, _r)
                                        if _ci < len(_v):
                                            _vals[str(_roles[0])] = str(_v[_ci])
                                    except: pass
                                if any(v for v in _vals.values()):
                                    rows.append(_vals)
                            if rows:
                                # ═══ 智能文件类型推理：先想关系，再定类型 ═══
                                hdr_text = " ".join(str(v) for v in _header)
                                
                                # 第1步：获取公司身份（当前账套主体）
                                from database import Company as _CoModel
                                _co = db.query(_CoModel).filter(_CoModel.id == company_id).first()
                                _co_name = (_co.name or "") if _co else ""
                                _co_uscc = (_co.uscc or "") if _co else ""
                                
                                # 第2步：扫描数据，判断公司与文件的关系
                                # 收集所有行中出现的购买方和销售方信息
                                all_buyers = set(); all_sellers = set()
                                all_buyer_tax = set(); all_seller_tax = set()
                                for _r in rows:
                                    for _k, _v in _r.items():
                                        _vs = str(_v).strip() if _v else ""
                                        if not _vs: continue
                                        if any(x in _k for x in ['买方','购方','购买方']):
                                            if '税号' in _k or '识别号' in _k or '信用' in _k:
                                                all_buyer_tax.add(_vs)
                                            else:
                                                all_buyers.add(_vs)
                                        if any(x in _k for x in ['卖方','销方','销售方']):
                                            if '税号' in _k or '识别号' in _k or '信用' in _k:
                                                all_seller_tax.add(_vs)
                                            else:
                                                all_sellers.add(_vs)
                                
                                # 判断公司与数据的关系
                                buyer_matches = (_co_name and any(_co_name in b for b in all_buyers)) or (_co_uscc and _co_uscc in all_buyer_tax)
                                seller_matches = (_co_name and any(_co_name in s for s in all_sellers)) or (_co_uscc and _co_uscc in all_seller_tax)
                                
                                # 扫描文件是否有抵扣相关字段
                                has_deduction_info = any(k in hdr_text for k in [
                                    "有效抵扣税额","勾选状态","勾选时间","用途确认",
                                    "抵扣勾选","不抵扣","认证状态","进项税额","可抵扣"
                                ])
                                
                                # 扫描文件是否有工资相关字段
                                has_salary_info = any(k in hdr_text for k in [
                                    "工资","代扣社保","养老保险","本期收入","实发",
                                    "个税","应纳税","累计收入","费用类型","所得项目"
                                ])
                                has_housing_fund_info = any(k in hdr_text for k in [
                                    "缴存月份","缴存基数","单位缴存额","个人缴存额",
                                    "缴存比例","公积金"
                                ])
                                has_salary_tax_info = any(k in hdr_text for k in [
                                    "征收项目","征收品目","应纳税额","累计应扣缴税额",
                                    "已缴税额","应补退税额","个人所得税"
                                ])
                                
                                # 列角色辅助
                                has_amount = any("amount_col" in r for r in col_roles.values())
                                has_date = any("date_col" in r for r in col_roles.values())
                                has_name = any("person_name" in r or "counterparty" in r for r in col_roles.values())
                                
                                # 第3步：综合推理，确定文件类型
                                if has_salary_info:
                                    inferred_type = "salary"
                                elif has_salary_tax_info:
                                    inferred_type = "salary_tax"
                                elif has_housing_fund_info:
                                    inferred_type = "housing_fund"
                                elif buyer_matches and not seller_matches:
                                    # 公司是购买方 → 进项相关
                                    if has_deduction_info:
                                        inferred_type = "input_vat_deduction"  # 进项抵扣认证
                                    else:
                                        inferred_type = "purchase_invoice"  # 进项发票
                                elif seller_matches and not buyer_matches:
                                    # 公司是销售方 → 销项发票
                                    inferred_type = "sales_invoice"
                                elif buyer_matches and seller_matches:
                                    # 买卖双方都有公司信息 → 进项（保守）
                                    if has_deduction_info:
                                        inferred_type = "input_vat_deduction"
                                    else:
                                        inferred_type = "purchase_invoice"
                                elif not buyer_matches and not seller_matches:
                                    # 公司与文件中任何一方都不匹配 → 可能不是本公司的
                                    if all_buyers and all_sellers:
                                        inferred_type = "suspect"  # 存疑：不属于本公司
                                    elif all_sellers and not all_buyers:
                                        inferred_type = "purchase_invoice"  # 仅卖方信息，按进项处理
                                    elif all_buyers and not all_sellers:
                                        inferred_type = "sales_invoice"
                                    elif has_deduction_info and all_sellers:
                                        inferred_type = "input_vat_deduction"
                                    elif has_date and has_amount and has_name:
                                        inferred_type = "bank_statement"
                                    elif has_date and has_amount:
                                        inferred_type = "voucher"
                                    else:
                                        inferred_type = "generic_data"
                                else:
                                    if has_date and has_amount and has_name:
                                        inferred_type = "bank_statement"
                                    elif has_date and has_amount:
                                        inferred_type = "voucher"
                                    else:
                                        inferred_type = "generic_data"
                                
                                # 第4步：记录推理过程
                                reason_parts = []
                                if buyer_matches: reason_parts.append("购买方=本公司→进项相关")
                                if seller_matches: reason_parts.append("销售方=本公司→销项相关")
                                if has_deduction_info: reason_parts.append("含抵扣认证字段")
                                if has_salary_info: reason_parts.append("含工资相关字段")
                                if not buyer_matches and not seller_matches: reason_parts.append("双方均不匹配本公司")
                                
                                parsed = {"type": inferred_type, "rows": rows}
                                fr["type"] = inferred_type
                                fr["actions"].append(f"推理判定:{inferred_type}({';'.join(reason_parts)}) {len(rows)}条")
                                pipeline_log.append(f"{fname} -> 推理判定: {inferred_type} ({';'.join(reason_parts)})")
                                _save_to_transfer(company_id, doc["id"], fname, parsed)
                    except Exception as _ie:
                        fr["actions"].append(f"推断失败: {_ie}")
                
                if parsed and parsed.get("rows"): 
                    _save_to_transfer(company_id, doc["id"], fname, parsed)
                if parsed:
                    ftype = parsed.get("type", "unknown"); fr["type"] = ftype
                    fr["_rows"] = parsed.get("rows", [])  # 留存原始数据，用于智能复核
                    # ── 留存原始表头文本用于智能复核（从缓存的workbook读取）──
                    if _cached_wb is not None:
                        try:
                            if ext == ".xls":
                                _hdr_sheet = _cached_wb.sheet_by_index(0)
                            else:
                                _hdr_sheet = _cached_wb[_cached_wb.sheetnames[0]]
                            _hdr_row = _get_row_values(_hdr_sheet, 0)
                            fr["_header_row"] = " ".join(str(v) for v in _hdr_row if v)
                        except Exception:
                            fr["_header_row"] = ""
                    else:
                        fr["_header_row"] = ""
                    n = len(parsed.get("rows", []))
                    if ftype == "salary": salaries.extend(parsed["rows"]); fr["actions"].append(f"提取{n}条工资")
                    elif ftype == "social_security": social_security.extend(parsed["rows"]); fr["actions"].append(f"提取{n}条社保")
                    elif ftype == "sales_invoice": invoices.extend([{**r, "direction": "销项"} for r in parsed["rows"]]); fr["actions"].append(f"提取{n}条销项")
                    elif ftype == "purchase_invoice": invoices.extend([{**r, "direction": "进项"} for r in parsed["rows"]]); fr["actions"].append(f"提取{n}条进项")
                    elif ftype == "input_vat_deduction": input_vat_deductions.extend([{**r, "direction": "进项"} for r in parsed["rows"]]); fr["actions"].append(f"提取{n}条进项认证抵扣")
                    elif ftype == "invoice":  # 通用发票 → 按列内容判断进销方向
                        rows = parsed["rows"]
                        for r in rows:
                            seller_name = str(r.get("seller", "")).strip()
                            buyer_name = str(r.get("buyer", "")).strip()
                            seller_tax = str(r.get("seller_tax", "")).strip()
                            buyer_tax = str(r.get("buyer_tax", "")).strip()
                            # 根据当前账套公司信息判定发票方向
                            # 规则：购买方=当前公司 → 进项；销售方=当前公司 → 销项
                            # Company已从顶部导入，不需重复import
                            company = db.query(Company).filter(Company.id == company_id).first()
                            co_name = (company.name or "") if company else ""
                            co_uscc = (company.uscc or "") if company else ""
                            
                            buyer_match = (buyer_name and co_name and buyer_name in co_name) or (buyer_tax and co_uscc and buyer_tax == co_uscc)
                            seller_match = (seller_name and co_name and seller_name in co_name) or (seller_tax and co_uscc and seller_tax == co_uscc)
                            
                            if buyer_match and not seller_match:
                                r["direction"] = "进项"  # 公司是购买方，别人开给公司
                            elif seller_match and not buyer_match:
                                r["direction"] = "销项"  # 公司是销售方，公司开给别人
                            elif buyer_match and seller_match:
                                r["direction"] = "进项"  # 都匹配时优先进项（更保守）
                            elif not buyer_match and not seller_match and seller_name and buyer_name:
                                # 买卖双方都有信息但都不匹配当前公司 → 不属于本账套
                                r["direction"] = "存疑"
                                fr.setdefault("_mismatch_warnings", []).append(f"发票买卖双方均不匹配当前公司'{co_name}'，可能误传了其他公司的资料")
                            elif seller_name and seller_tax:
                                r["direction"] = "进项"  # 有销方信息但未匹配到公司（可能是公司简称/曾用名）
                            elif buyer_name and buyer_tax:
                                r["direction"] = "销项"  # 有购方信息但未匹配到公司
                            elif seller_name:
                                r["direction"] = "进项"
                            elif buyer_name:
                                r["direction"] = "销项"
                            else:
                                r["direction"] = "存疑"  # 无法判定
                            invoices.append(r)
                        fr["actions"].append(f"提取{n}条发票")
                    elif ftype == "voucher": vouchers.extend(parsed["rows"]); fr["actions"].append(f"提取{n}条凭证")
                    elif ftype == "inventory": inventory.extend(parsed["rows"]); fr["actions"].append(f"提取进销存")
                    elif ftype in ("bank", "bank_statement", "bank_transaction"): 
                        # 银行流水→标准化后加入bank_txs
                        success_count = 0
                        for r in parsed["rows"]:
                            try:
                                tx = dict(r)
                                # 标准化日期（兼容 date / tx_time / 交易日期 / 交易时间 / 记账日期 五种命名）
                                tx["date"] = str(tx.get("date") or tx.get("tx_time") or tx.get("交易日期") or tx.get("交易时间") or tx.get("记账日期") or "").strip()[:10]
                                # 标准化对方
                                tx["counterparty"] = str(tx.get("counterparty", tx.get("对方户名", tx.get("交易对方", tx.get("对方名称", ""))))).strip()
                                tx["summary"] = str(tx.get("summary", tx.get("摘要", tx.get("交易附言", tx.get("用途", ""))))).strip()
                                # 标准化金额（防御性转换——金额列可能是空/NULL/货币格式/文本）
                                def _safe_float(val):
                                    if val is None: return 0.0
                                    if isinstance(val, (int, float)): return float(val)
                                    s = str(val).strip().replace(",", "").replace("，", "").replace(" ", "").replace("¥", "").replace("￥", "").replace("元", "")
                                    if s == "" or s == "-" or s == "--": return 0.0
                                    try: return float(s)
                                    except: return 0.0
                                debit_val = _safe_float(tx.get("debit")) or _safe_float(tx.get("借方金额")) or _safe_float(tx.get("支出金额"))
                                credit_val = _safe_float(tx.get("credit")) or _safe_float(tx.get("贷方金额")) or _safe_float(tx.get("收入金额"))
                                amount_val = _safe_float(tx.get("amount")) or _safe_float(tx.get("交易金额")) or (debit_val + credit_val)
                                tx["debit"] = debit_val
                                tx["credit"] = credit_val
                                tx["amount"] = amount_val
                                tx["direction"] = "支出" if debit_val > 0 else ("收入" if credit_val > 0 else "未知")
                                # 跳过空行（日期和金额都为空的无效行）
                                if not tx["date"] or (debit_val == 0 and credit_val == 0):
                                    continue
                                # 跳过银行流水的"汇总"行和无效行
                                cp_name = str(tx.get("counterparty", "")).strip()
                                if not cp_name:
                                    st = str(tx.get("summary", "")).strip()
                                    # 有摘要的、无对手的中等交易可能是有实质内容的
                                    if credit_val < 50000 and credit_val != int(credit_val):
                                        pass  # 保留：有零头的小额交易（可能是摘要中有线索）
                                    elif credit_val < 1000:
                                        continue  # 忽略：极小金额无对手→银行费用
                                    elif "汇总" in st or "合计" in st:
                                        continue  # 忽略：明确的汇总行
                                    elif credit_val >= 50000:
                                        continue  # 忽略：大额无对手→汇总行/重复数据
                                    elif credit_val == int(credit_val) or (debit_val > 0 and debit_val == int(debit_val)):
                                        continue  # 忽略：整数金额无对手→非真实交易
                                bank_txs.append(tx)
                                success_count += 1
                            except Exception:
                                pass
                        fr["actions"].append(f"提取{success_count}条流水（共{n}行）")
                    elif ftype == "housing_fund": fr["actions"].append(f"提取{n}条公积金")
                    elif ftype == "contract": contract_data.extend(parsed["rows"]); fr["actions"].append(f"提取{n}份合同")
                    elif ftype == "related_party": related_party_data.extend(parsed["rows"]); fr["actions"].append(f"提取{n}条关联交易")
                    elif ftype == "trial_balance": trial_balance_data.extend(parsed["rows"]); fr["actions"].append(f"提取{n}条科目余额")
                    else: fr["actions"].append(f"识别为{ftype}({n}条)——已记录，用于交叉验证")
                    pipeline_log.append(f"{fname} -> {ftype}: {n}条")
            elif ext == ".pdf":
                txs = _parse_pdf_bank_statement(fpath)
                if txs: bank_txs.extend(txs); fr["type"] = "bank"; fr["actions"].append(f"提取{len(txs)}条流水")
        except Exception as e: fr["actions"].append(f"失败: {e}")
        file_results.append(fr)

    # ═══════════════════════════════════════════════════════
    # 2026-06-26 资料智能复核：自行验证文件分类准确性
    # 对每个已分类的文件，交叉验证其内容是否与声明类型匹配
    # 发现误分类→自动纠正类型→数据自动重新路由到正确列表
    # ═══════════════════════════════════════════════════════
    # ═══════════════════════════════════════════════════════════════
    #  资料分类决策方法论（系统化，写入代码逻辑）
    #
    #  Layer 0 — 文件名直接分类
    #    文件名是用户对内容的直接标注，可信度最高。
    #    例: "开票"→销项发票  "取票"→进项发票  "抵扣"→进项认证
    #    标记 _from_filename=True → 后续验证跳过此文件
    #
    #  Layer 1 — 指纹关键词匹配
    #    解析文件表头，匹配34类指纹关键词库，取最高分。
    #    适用于文件名无明确提示的文件。
    #
    #  Layer 2 — 结构指纹验证
    #    提取列数/数值比/累计字段/借贷对等抽象特征。
    #    同类文件求平均指纹，偏离者自动纠正。
    #    跳过 _from_filename=True 的文件。
    #
    #  Layer 3 — 自审计
    #    检查每个类型组内部是否结构一致。
    #    发现组内混入异类文件 → 标记并报告。
    #
    #  决策优先级: 文件名 > 结构指纹 > 关键词匹配
    # ═══════════════════════════════════════════════════════════════
    
    # ── 尝试加载外部配置（filename_type_map.json），失败则用内置映射 ──
    _FN_TYPE_MAP = []
    _fn_config_loaded = False
    for _fn_cfg_path in [
        os.path.join(_PROJECT_ROOT, "static", "filename_type_map.json"),
        "static/filename_type_map.json",
    ]:
        if os.path.exists(_fn_cfg_path):
            try:
                with open(_fn_cfg_path, 'r', encoding='utf-8') as _fn_f:
                    _fn_cfg = json.loads(_fn_f.read())
                for _m in _fn_cfg.get("mappings", []):
                    _FN_TYPE_MAP.append((_m["keywords"], _m["type"]))
                _fn_config_loaded = True
                pipeline_log.append(f"[配置] 已加载文件名映射表: {_fn_cfg_path}")
            except Exception as _fn_e:
                pipeline_log.append(f"[配置] 文件名映射表加载失败({_fn_e})，使用内置默认")
            if _fn_config_loaded:
                break
    
    if not _fn_config_loaded:
        _FN_TYPE_MAP = [
        (["银行", "流水", "bank_statement"], "bank_statement"),
        (["开票", "销项", "销售发票", "销货"], "sales_invoice"),
        (["取票", "进项", "采购发票", "购货", "取得发票"], "purchase_invoice"),
        (["抵扣", "勾选", "认证"], "input_vat_deduction"),
        (["工资", "薪金", "所得", "个税"], "salary"),
        (["社保", "社会保险"], "social_security"),
        (["公积金", "缴存"], "housing_fund"),
        (["申报", "扣缴", "个人所得税"], "salary_tax"),
        (["公积金", "住房"], "housing_fund"),
            (["凭证", "记账", "序时账"], "voucher"),
            (["进销存", "台账", "存货", "库存"], "inventory"),
            (["档案"], "archive"),
        ]
    for _fr in file_results:
        _fn = _fr.get("file", "").lower()
        _cur_type = _fr.get("type", "unknown")
        for _kws, _target_type in _FN_TYPE_MAP:
            if any(kw.lower() in _fn for kw in _kws):
                if _cur_type != _target_type:
                    pipeline_log.append(f"[文件名纠偏] {_fr['file']}: {_cur_type} → {_target_type} (文件名含{_kws[0]})")
                    _fr["type"] = _target_type
                    _fr["_from_filename"] = True  # 标记：避免被后续验证覆盖
                    _rows = _fr.get("_rows", [])
                    if _target_type == "bank_statement" and _cur_type in ("invoice", "invoice_universal", "sales_invoice", "purchase_invoice"):
                        for _r in _rows:
                            try:
                                _tx = dict(_r)
                                _tx["date"] = str(_tx.get("date") or _tx.get("tx_time") or _tx.get("交易日期") or _tx.get("交易时间") or _tx.get("记账日期") or _tx.get("会计期间") or "").strip()[:10]
                                _tx["counterparty"] = str(_tx.get("counterparty", _tx.get("对方名称", _tx.get("对方户名", "")))).strip()
                                _tx["summary"] = str(_tx.get("summary", _tx.get("摘要", ""))).strip()
                                _tx["debit"] = float(_tx.get("debit", 0) or 0)
                                _tx["credit"] = float(_tx.get("credit", 0) or 0)
                                bank_txs.append(_tx)
                            except: pass
                break
    
    _corrections = _auto_verify_file_types(file_results, pipeline_log)
    if _corrections:
        pipeline_log.append(f"[智能复核] 完成：共修正{len(_corrections)}个文件的分类")
    
    # ═══ Layer 3: 自审计 — 检查每个类型组内部结构一致性 ═══
    _type_groups_audit = {}
    for _fr in file_results:
        _t = _fr.get("type", "unknown")
        if _t not in _type_groups_audit:
            _type_groups_audit[_t] = []
        _type_groups_audit[_t].append(_fr)
    
    _audit_warnings = []
    for _t, _members in _type_groups_audit.items():
        if len(_members) < 3 or _t in ("unknown",):
            continue
        # 计算组内文件名的前缀多样性——如果同类型文件有不同的文件名前缀，说明可能混入了不同类型
        _fn_prefixes = {}
        for _m in _members:
            _fn = _m.get("file", "")
            # 提取文件名中的关键词（去掉数字和日期部分）
            import re as _re_audit
            _clean = _re_audit.sub(r'[\d\-_]+', '', _fn.lower())
            _fn_prefixes[_clean] = _fn_prefixes.get(_clean, 0) + 1
        # 如果组内有3种以上不同的文件名模式 → 可能存在混入
        if len(_fn_prefixes) >= 3:
            _audit_warnings.append(f"[自审计] {_t}组内文件名模式不统一({len(_fn_prefixes)}种): {list(_fn_prefixes.keys())[:5]}")
    
    if _audit_warnings:
        for _w in _audit_warnings:
            pipeline_log.append(_w)
    
    # ═══════════════════════════════════════════════════════════
    # 综合判断层：对比文件名暗示/列头推理/数据匹配三方证据，
    # 当证据冲突时做综合判定而非盲信单一来源。
    # ═══════════════════════════════════════════════════════════
    pipeline_log.append("[综合判断] 开始三方证据交叉验证")
    for _fr in file_results:
        _fn = _fr.get("file", "")
        _type = _fr.get("type", "unknown")
        _actions = _fr.get("actions", [])
        _hdr = _fr.get("_header_row", "")
        
        # 收集证据
        _evidences = []
        
        # 证据1: 文件名暗示的类型
        _fn_lower = _fn.lower()
        _fn_type = None
        for _kws, _tp in _FN_TYPE_MAP:
            if any(k.lower() in _fn_lower for k in _kws):
                _fn_type = _tp; break
        if _fn_type:
            _evidences.append(("文件名", _fn_type, "高" if _fn_type == _type else "中"))
        
        # 证据2: 数据推理的类型（从actions中提取）
        for _a in _actions:
            if _a.startswith("推理判定:"):
                _reason_type = _a.split(":")[1].split("(")[0]
                _evidences.append(("数据推理", _reason_type, "高"))
                break
        
        # 证据3: 公司身份匹配
        _has_co_match = any("本公司" in _a or "购买方=本" in _a or "销售方=本" in _a for _a in _actions)
        if _has_co_match:
            _evidences.append(("公司匹配", "身份确认", "高"))
        elif "不匹配本公司" in str(_actions):
            _evidences.append(("公司匹配", "不匹配", "高"))
        
        # 综合判定：收集所有证据类型
        _ev_types = set(e[1] for e in _evidences)
        _all_agree = len(_ev_types) <= 1  # 所有证据指向同一类型
        
        if not _all_agree and len(_evidences) >= 2:
            # 证据冲突 → 优先相信数据推理
            _data_type = next((e[1] for e in _evidences if e[0] == "数据推理"), None)
            if _data_type and _data_type != _type:
                _old_type = _type
                _fr["type"] = _data_type
                _fr["_comprehensive_override"] = True
                _fr.setdefault("actions", []).append(
                    f"[综合判断] 文件名暗示{_fn_type or '未知'}但数据推理为{_data_type}，以数据推理为准"
                )
                pipeline_log.append(f"[综合判断] {_fn}: {_old_type}→{_data_type} (数据推理优先，文件名暗示不符)")
            elif _type == "generic_data" and _fn_type:
                _fr["type"] = _fn_type
                _fr["_comprehensive_override"] = True
                _fr.setdefault("actions", []).append(
                    f"[综合判断] 数据未能判定，采纳文件名暗示为{_fn_type}"
                )
                pipeline_log.append(f"[综合判断] {_fn}: generic_data→{_fn_type} (数据不足，采纳文件名)")
        # ── 重新路由被修正文件的数据 ──
        # 策略：新增到正确列表 + 标记旧分类用于报告
        for _cor in _corrections:
            _fr = next((f for f in file_results if f.get("file") == _cor["file"]), None)
            if not _fr: continue
            _rows = _fr.get("_rows", [])
            _new_type = _cor["new_type"]
            _n = len(_rows)
            fr_actions = _fr.get("actions", [])
            # 追加修正后的正确类型数据到对应列表
            if _new_type == "salary":
                salaries.extend(_rows)
                fr_actions.append(f"[复核修正] 原误判→现确认为工资表({_n}条)")
            elif _new_type == "social_security":
                social_security.extend(_rows)
                fr_actions.append(f"[复核修正] 原误判→现确认为社保({_n}条)")
            elif _new_type in ("sales_invoice",):
                invoices.extend([{**r, "direction": "销项"} for r in _rows])
                fr_actions.append(f"[复核修正] 原误判→现确认为销项发票({_n}条)")
            elif _new_type in ("purchase_invoice", "input_vat_deduction"):
                invoices.extend([{**r, "direction": "进项"} for r in _rows])
                fr_actions.append(f"[复核修正] 原误判→现确认为进项发票({_n}条)")
            elif _new_type in ("invoice_universal", "invoice"):
                fr_actions.append(f"[复核修正] 原误判→现确认为通用发票({_n}条)")
            elif _new_type == "voucher":
                vouchers.extend(_rows)
                fr_actions.append(f"[复核修正] 原误判→现确认为记账凭证({_n}条)")
            elif _new_type == "individual_tax":
                # 个税申报表：数据是工薪数据，但格式是税务申报格式
                # 路由到 salaries 供分析使用，但标记为个税申报表类型
                salaries.extend(_rows)
                fr_actions.append(f"[复核修正] 原误判→现确认为个税扣缴申报表({_n}条)")
            elif _new_type == "bank_journal":
                # 银行日记账：有凭证号+银行流水号+对方名称
                # 标准化后加入 bank_txs
                _added = 0
                for _r in _rows:
                    try:
                        _tx = dict(_r)
                        _tx["date"] = str(_tx.get("date") or _tx.get("tx_time") or _tx.get("交易日期") or _tx.get("交易时间") or _tx.get("记账时间") or _tx.get("会计期间") or "").strip()[:10]
                        _tx["counterparty"] = str(_tx.get("counterparty", _tx.get("对方名称", _tx.get("对方户名", _tx.get("交易对方", ""))))).strip()
                        _tx["summary"] = str(_tx.get("summary", _tx.get("摘要", _tx.get("交易附言", _tx.get("用途", ""))))).strip()
                        _tx["voucher_no"] = str(_tx.get("凭证号", _tx.get("voucher_no", ""))).strip()
                        bank_txs.append(_tx)
                        _added += 1
                    except Exception:
                        pass
                fr_actions.append(f"[复核修正] 原误判→现确认为银行日记账({_added}条)")
            elif _new_type == "inventory":
                inventory.extend(_rows)
                fr_actions.append(f"[复核修正] 原误判→现确认为进销存({_n}条)")
            elif _new_type in ("bank", "bank_statement", "bank_transaction"):
                _added = 0
                for _r in _rows:
                    try:
                        _tx = dict(_r)
                        _tx["date"] = str(_tx.get("date") or _tx.get("tx_time") or _tx.get("交易日期") or _tx.get("交易时间") or _tx.get("记账日期") or "").strip()[:10]
                        _tx["counterparty"] = str(_tx.get("counterparty", _tx.get("对方户名", _tx.get("交易对方", _tx.get("对方名称", ""))))).strip()
                        _tx["summary"] = str(_tx.get("summary", _tx.get("摘要", _tx.get("交易附言", _tx.get("用途", ""))))).strip()
                        # 标准化金额（确保 credit/debit 字段存在，否则 _domain_bank_tracking 会 KeyError）
                        def _safe_float_v2(val):
                            if val is None: return 0.0
                            if isinstance(val, (int, float)): return float(val)
                            s = str(val).strip().replace(",", "").replace("，", "").replace(" ", "").replace("¥", "").replace("￥", "").replace("元", "")
                            if s == "" or s == "-" or s == "--": return 0.0
                            try: return float(s)
                            except: return 0.0
                        _tx["debit"] = _safe_float_v2(_tx.get("debit") or _tx.get("借方金额") or _tx.get("支出金额"))
                        _tx["credit"] = _safe_float_v2(_tx.get("credit") or _tx.get("贷方金额") or _tx.get("收入金额"))
                        _tx["amount"] = _safe_float_v2(_tx.get("amount") or _tx.get("交易金额")) or (_tx["debit"] + _tx["credit"])
                        _tx["direction"] = "支出" if _tx["debit"] > 0 else ("收入" if _tx["credit"] > 0 else "未知")
                        bank_txs.append(_tx)
                        _added += 1
                    except Exception:
                        pass
                fr_actions.append(f"[复核修正] 原误判→现确认为银行流水({_added}条)")
            else:
                fr_actions.append(f"[复核修正] 原误判→现确认为{_new_type}({_n}条，已记录待交叉验证)")

    sal_invs = [i for i in invoices if i["direction"] == "销项"]
    pur_invs = [i for i in invoices if i["direction"] == "进项"]
    suspect_invs = [i for i in invoices if i["direction"] == "存疑"]
    _report(95, f"文件解析完成 → 销项{len(sal_invs)}张 进项{len(pur_invs)}张" + (f" 存疑{len(suspect_invs)}张" if suspect_invs else ""))
    
    # 存疑发票不参与分析，但记录在案
    if suspect_invs:
        pipeline_log.append(f"[ISOLATION] {len(suspect_invs)}张发票买卖双方均不匹配当前公司，已排除出分析（防A账套混入B公司资料）")
    
    # ═══════════════════════════════════════
    # Phase 1: 确定分析对象 → 反推发票方向校正
    # ═══════════════════════════════════════
    from collections import Counter as _Counter
    
    # 统计所有发票中出现的名称（不依赖方向判断）
    _all_names = _Counter()
    for inv in invoices:
        b = str(inv.get("buyer", inv.get("购买方名称", ""))).strip()
        s = str(inv.get("seller", inv.get("销方名称", ""))).strip()
        if b and len(b) >= 6: _all_names[b] += 1
        if s and len(s) >= 6: _all_names[s] += 1
    
    # 同时统计交叉出现（同一名称既做买方又做卖方）
    _pur_buyers = _Counter()
    _sal_sellers = _Counter()
    _sal_buyers = _Counter()
    _pur_sellers = _Counter()
    for inv in invoices:
        b = str(inv.get("buyer", "")).strip()
        s = str(inv.get("seller", "")).strip()
        if b and len(b) >= 6:
            _pur_buyers[b] += 1; _sal_buyers[b] += 1  # 计数时不区分方向
        if s and len(s) >= 6:
            _pur_sellers[s] += 1; _sal_sellers[s] += 1
    
    _target_name = ""
    # 策略1：出现在所有位置总次数最多的名称
    if _all_names:
        best_name = _all_names.most_common(1)[0][0]
        # 验证：该名称至少出现在50%以上的发票中
        if _all_names[best_name] >= len(invoices) * 0.3:
            _target_name = best_name
            pipeline_log.append(f"Phase1-识别对象(频次): {_target_name} (出现{_all_names[best_name]}次/{len(invoices)}张)")
    
    # 策略2：交叉出现的名称
    if not _target_name:
        _cross_1 = set(_pur_buyers.keys()) & set(_sal_sellers.keys())
        _cross_2 = set(_sal_buyers.keys()) & set(_pur_sellers.keys())
        _cross = _cross_1 | _cross_2
        if _cross:
            _target_name = max(_cross, key=lambda n: _all_names.get(n, 0))
            pipeline_log.append(f"Phase1-识别对象(交叉): {_target_name}")
    
    if not _target_name and _all_names:
        _target_name = _all_names.most_common(1)[0][0]
    
    if _target_name:
        _corrected = 0
        for inv in invoices:
            buyer = str(inv.get("buyer", inv.get("购买方名称", ""))).strip()
            seller = str(inv.get("seller", inv.get("销方名称", ""))).strip()
            old_dir = inv.get("direction", "")
            if buyer == _target_name or _target_name in buyer:
                if old_dir != "进项":
                    inv["direction"] = "进项"; _corrected += 1
            elif seller == _target_name or _target_name in seller:
                if old_dir != "销项":
                    inv["direction"] = "销项"; _corrected += 1
        if _corrected:
            pipeline_log.append(f"Phase1-方向校正: {_corrected}张发票方向已修正")
        sal_invs = [i for i in invoices if i["direction"] == "销项"]
        pur_invs = [i for i in invoices if i["direction"] == "进项"]

    # ═════════════════════════════════════════════════════════==
    # 稽查方法论④：主营业务成本识别驱动的进销存分析
    # 核心原则：先识别主营业务成本（三层分类），再逐层分析，
    # 而非一刀切地全量比对。费用类发票不参与进销匹配。
    # 分析链：主营业务成本识别 → 核心成本进销匹配 → 制造业加工链条检测 → BOM交叉验证
    # 证据链：进销品名对照表 + 三层分类结果 + 加工费/BOM交叉信号
    # 注意：ctx 在此处尚未初始化（Phase 1 在后面运行），使用直接调用
    # ═════════════════════════════════════════════════════════==
    inv_match_findings = []
    if sal_invs and pur_invs:
        from collections import defaultdict
        
        # ═══ 服务行业品名过滤：精准到品名级别，而非公司级别 ═══
        # 逻辑：服务品名（广告/咨询/IT等）天然无实物货物流转，不参与进销存比对
        #       实物商品品名（纺织/金属/食品等）继续正常比对
        # 结果：一家公司既有服务又有货物 → 服务跳过，货物照查
        import re
        # 从 industry_data.json 加载服务行业编码（外部化配置，支持全行业扩展）
        try:
            _ind_path = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "industry_data.json")
            with open(_ind_path, 'r', encoding='utf-8') as _f:
                _ind_data = json.loads(_f.read())
            SERVICE_INDUSTRY_CODES = _ind_data.get("service_industries", {}).get("codes", [
                "广告服务","信息技术服务","研发和技术服务","文化创意服务",
                "物流辅助服务","鉴证咨询服务","广播影视服务","商务辅助服务",
                "金融服务","现代服务","生活服务","电信服务","建筑服务",
                "教育服务","医疗服务","旅游服务","娱乐服务","餐饮服务",
                "居民日常服务","其他现代服务","经纪代理服务","人力资源服务",
                "安全保护服务","会议展览服务","租赁服务","无形资产",
            ])
        except Exception:
            SERVICE_INDUSTRY_CODES = [
                "广告服务","信息技术服务","研发和技术服务","文化创意服务",
                "物流辅助服务","鉴证咨询服务","广播影视服务","商务辅助服务",
                "金融服务","现代服务","生活服务","电信服务","建筑服务",
                "教育服务","医疗服务","旅游服务","娱乐服务","餐饮服务",
                "居民日常服务","其他现代服务","经纪代理服务","人力资源服务",
                "安全保护服务","会议展览服务","租赁服务","无形资产",
            ]
        
        def _is_service_goods(goods_name):
            """判断品名是否为服务类（非实物）"""
            m = re.search(r'\*([^*]+)\*', str(goods_name))
            if not m: return False
            cat = m.group(1)
            return any(s in cat for s in SERVICE_INDUSTRY_CODES)
        
        # 扫描所有品名的服务/实物分类
        all_sale_cats = set()
        svc_sale_count = 0; phys_sale_count = 0
        for inv in sal_invs:
            g = str(inv.get("goods", inv.get("货物或应税劳务名称", "")))
            if _is_service_goods(g): svc_sale_count += 1
            else: phys_sale_count += 1
            m = re.search(r'\*([^*]+)\*', g)
            if m: all_sale_cats.add(m.group(1))
        
        if svc_sale_count + phys_sale_count > 0:
            svc_pct = svc_sale_count / (svc_sale_count + phys_sale_count) * 100
            pipeline_log.append(f"[进销存] 销项品名分类：服务类{svc_sale_count}条({svc_pct:.0f}%) 实物类{phys_sale_count}条 — 服务类品名跳过进销存比对，实物类正常检查")
        
        # ── 步骤0：主营业务成本识别（从Phase 1 AuditContext读取，避免重复计算）──
        if ctx and ctx.biz_cost_classification:
            biz_cost_classification = ctx.biz_cost_classification
        else:
            biz_cost_classification = identify_main_biz_cost(pur_invs, sal_invs)
        core_cost_invs = biz_cost_classification["core_cost_invs"]
        major_expense_invs = biz_cost_classification["major_expense_invs"]
        minor_expense_invs = biz_cost_classification["minor_expense_invs"]
        core_cost_goods = biz_cost_classification["pur_core_goods"]
        expense_goods = biz_cost_classification["pur_expense_goods"]
        
        n_core = len(core_cost_invs)
        n_major = len(major_expense_invs)
        n_minor = len(minor_expense_invs)
        
        # ── 按货物名称聚合（全量+核心成本两层）──
        sale_by_goods = defaultdict(lambda: {"qty": 0, "amount": 0, "count": 0})
        pur_by_goods = defaultdict(lambda: {"qty": 0, "amount": 0, "count": 0})
        pur_core_by_goods = defaultdict(lambda: {"qty": 0, "amount": 0, "count": 0})
        
        for inv in sal_invs:
            g = str(inv.get("goods", inv.get("货物或应税劳务名称", ""))).strip()
            if not g: g = "未命名商品"
            # 服务类品名跳过进销存数量比对
            if _is_service_goods(g): continue
            q = float(inv.get("qty", inv.get("数量", 0)) or 0)
            a = float(inv.get("amount", inv.get("金额", 0)) or 0)
            sale_by_goods[g]["qty"] += q
            sale_by_goods[g]["amount"] += a
            sale_by_goods[g]["count"] += 1
        for inv in pur_invs:
            g = str(inv.get("goods", inv.get("货物或应税劳务名称", ""))).strip()
            if not g: g = "未命名商品"
            q = float(inv.get("qty", inv.get("数量", 0)) or 0)
            a = float(inv.get("amount", inv.get("金额", 0)) or 0)
            pur_by_goods[g]["qty"] += q
            pur_by_goods[g]["amount"] += a
            pur_by_goods[g]["count"] += 1
        # ── 核心成本层独立聚合 ──
        for inv in core_cost_invs:
            g = str(inv.get("goods", inv.get("货物或应税劳务名称", ""))).strip()
            if not g: g = "未命名商品"
            q = float(inv.get("qty", inv.get("数量", 0)) or 0)
            a = float(inv.get("amount", inv.get("金额", 0)) or 0)
            pur_core_by_goods[g]["qty"] += q
            pur_core_by_goods[g]["amount"] += a
            pur_core_by_goods[g]["count"] += 1
        
        # 排除的费用品名集合（用于有进无销/有销无进的过滤）
        expense_goods_set = set(expense_goods)
        
        # ═══════════════════════════════════════════════════
        # 检查1：有进无销（33）
        # 稽查方法论④-A：只对主营业务成本的采购做有进无销判断
        # 费用类进项（餐饮住宿汽油等）天然不需要销售，不应标记为"有进无销"
        # 分析链：核心成本进项品名 → 销项品名交叉比对 → 制造业加工信号检测 → BOM验证
        # 证据链：核心成本进项清单 + 销项清单 + 加工费/BOM关联信号
        # ═══════════════════════════════════════════════════
        core_only_buy = [g for g in pur_core_by_goods if g not in sale_by_goods]
        # 统计被排除的费用类"仅采购"（不标记为风险，仅作说明）
        expense_only_buy = [g for g in pur_by_goods if g not in sale_by_goods and g in expense_goods_set]
        
        if core_only_buy:
            pur_core_total = sum(pur_core_by_goods[g]["amount"] for g in pur_core_by_goods)
            pur_amount_only = sum(pur_core_by_goods[g]["amount"] for g in core_only_buy)
            pct = pur_amount_only / max(pur_core_total, 1) * 100
        
            # 制造业诊断：核心成本中有加工费+有与销项品名不同的采购→可能是原材料加工为成品
            has_processing = any("加工费" in g or "加工" in g for g in pur_core_by_goods)
            expense_keywords_local = ["住宿","餐饮","餐费","加油","租赁","房租","物业","保险","通信","快递","办公","维修","服务费","咨询","广告","培训","差旅"]
            raw_like = [g for g in core_only_buy if not any(k in g for k in expense_keywords_local) and "加工" not in g]
            is_manufacturing = has_processing and len(raw_like) > 0
        
            # 排除说明
            excluded_note = ""
            if expense_only_buy:
                exp_amount = sum(pur_by_goods[g]["amount"] for g in expense_only_buy)
                excluded_note = f"（已排除{len(expense_only_buy)}类费用/报销类进项{exp_amount:,.2f}元——日常经营必有零星报销，不纳入主营业务进销比对）"
        
            if is_manufacturing:
                pur_raw_list = raw_like
                processing = [g for g in core_only_buy if "加工" in g]
                only_sell_goods = [g for g in sale_by_goods if g not in pur_core_by_goods]
            
                desc = f"【主营业务成本识别后分析】将核心成本{len(pur_core_by_goods)}种商品与销项{len(sale_by_goods)}种商品逐票交叉比对。{excluded_note}\n\n"
                desc += f"核心成本中发现{len(core_only_buy)}种商品仅采购无销售——"
                desc += f"采购了{'、'.join(pur_raw_list[:5])}等{len(core_only_buy)}种（金额{pur_amount_only:,.2f}元，占核心成本{pct:.2f}%），但销项发票中未发现同名产品的销售记录。\n\n"
            
                desc += f"进一步核查进项结构，发现：\n"
                desc += f"① 加工费发票{len(processing)}笔（{'、'.join(processing) if processing else '外包加工'}）\n"
                desc += f"② 非费用类原材料采购{len(raw_like)}种（{'、'.join(pur_raw_list[:5])}等）\n"
                desc += f"上述两个信号同时存在，表明企业采用'采购原材料→委托加工→销售成品'的经营模式。\n\n"
            
                desc += f"进项品名与销项品名不匹配的根本原因是制造业的正常加工链条——进项是原料（{'、'.join(pur_raw_list[:3])}等），"
                if only_sell_goods: desc += f"经过加工变成成品（{'、'.join(only_sell_goods[:3])}），"
                desc += f"品名天然不同。这跟面包店买面粉卖面包、家具厂买木材卖桌椅是同一个道理。\n"
                desc += f"因此，{len(core_only_buy)}种商品'有进无销'不是隐匿收入，而是制造业的正常加工链条。\n\n"
            
                desc += f"风险焦点从'有进无销=隐匿收入'转移到了'加工链条是否真实'："
                desc += f"① BOM表能否证明原材料投入→加工→成品产出的逻辑（投入产出比、损耗率）；"
                desc += f"② 加工费发票真实性（是否虚开）；"
                desc += f"③ 费用类进项（共{len(expense_only_buy)}类，如住宿、餐饮、汽油等）是否已通过报销制度管理，去向是否与经营规模匹配。"
            
                inv_match_findings.append({
                    "type": "有进无销风险",
                    "level": "中风险", "score": 5,
                    "detail": f"【主营业务成本识别后】核心成本中{len(core_only_buy)}类商品仅采购无销售记录，涉及金额{pur_amount_only:,.2f}元，占核心成本{pct:.2f}%{excluded_note}。",
                    "description": desc,
                    "how_found": f"先对{len(pur_invs)}张进项发票做主营业务成本识别（三层分类），排除{len(minor_expense_invs)}张日常报销+{len(major_expense_invs)}张重大费用后，对{len(core_cost_invs)}张核心成本发票逐品名与销项比对。发现{len(core_only_buy)}类进项商品从未出现在销项中。进一步检索进项中是否存在加工费——发现{has_processing}，同时存在{len(raw_like)}类非费用类原材料采购——判定为制造业加工链条而非隐匿收入。",
                    "tax_impact": "制造业加工链条导致进销品名不匹配属正常现象。但BOM表缺失则无法证明投入产出逻辑，加工费发票真实性无法验证，风险仍存在。",
                    "policy_ref": "《增值税暂行条例》第十条（进项税额转出情形）；企业所得税关于成本费用扣除真实性的规定。",
                    "suggestion": f"① 提供BOM表验证原材料→加工→成品的完整链条（投入产出比、损耗率）；② 提供加工合同、送料单、收货单；③ 费用类进项提供报销凭证和业务说明。以上三项齐全可排除隐匿收入嫌疑。",
                    "category": "进销存匹配",
                    "rule_id": 338,
                    "source_chain": "进销存-主营业务成本识别-进销品名匹配",
                    "_cross_refs": ["缺少BOM表"]  # 跨结论引用标记
                })
            else:
                inv_match_findings.append({
                    "type": "有进无销风险",
                    "level": "高风险", "score": 8,
                    "detail": f"【主营业务成本识别后】核心成本中{len(core_only_buy)}类商品仅采购无销售记录，涉及金额{pur_amount_only:,.2f}元，占核心成本{pct:.2f}%{excluded_note}。",
                    "description": f"先对{len(pur_invs)}张进项发票做主营业务成本识别，排除费用类后对{len(core_cost_invs)}张核心成本发票做进销比对。被查单位采购了{'、'.join(core_only_buy[:3])}等{len(core_only_buy)}种核心商品（金额{pur_amount_only:,.2f}元，占核心成本{pct:.2f}%），但销项发票中未发现对应产品的销售记录。\n\n"
                        + f"【人类稽查员行为判断】{'(常规经营必有零星费用报销，已排除' + str(len(expense_only_buy)) + '类费用发票）' if expense_only_buy else ''}对主营业务成本的'有进无销'，可能存在以下情况：①账外经营，隐匿销售收入（货物已售但未申报）；②未开票销售，未确认收入；③货物用于非应税项目、集体福利或个人消费但未作进项税额转出；④货物发生非正常损失、盘亏或去向不明。",
                    "how_found": f"对{len(pur_invs)}张进项发票做主营业务成本识别（三层分类），排除费用类后对{len(core_cost_invs)}张核心成本发票逐品名与销项比对。发现{len(core_only_buy)}类核心进项的品名从未出现在销项中。",
                    "tax_impact": "涉及隐匿销售收入→补缴增值税（货物适用税率）+企业所得税+滞纳金+0.5-5倍罚款；情节严重的移送公安。",
                    "policy_ref": "《税收征收管理法》第六十三条（偷税认定）；《增值税暂行条例》第十条（进项税额转出情形）；《刑法》第二百零一条（逃税罪）",
                    "suggestion": f"要求被查单位逐项说明{len(core_only_buy)}种核心商品的去向：1)提供对应销售合同、出库单、物流单据以证明已售；2)若用于生产，提供生产投料记录和产成品入库单以证明产出；3)若发生损失，提供损失清单及内部审批记录。无法说明去向的，按隐匿收入处理。",
                    "category": "进销存匹配",
                    "rule_id": 338,
                    "source_chain": "进销存-主营业务成本识别-进销品名匹配",
                })
        
        # ═══════════════════════════════════════════════════
        # 检查2：有销无进（34）
        # 稽查方法论④-B：只对主营业务成本对应的销售做有销无进判断
        # 如果已经判断缺少BOM表（制造业加工链条），则主营业务成本外
        # 的销售由加工产出，属于正常现象，不应标记为"有销无进"
        # ═══════════════════════════════════════════════════
        # 对销项品名做分类：哪些是核心成本相关，哪些是费用类
        sale_core_related = {}
        sale_non_core = {}
        for g in sale_by_goods:
            if g in core_cost_goods or any(kw in g for kw in ['加工','制品','成品','产品']):
                sale_core_related[g] = sale_by_goods[g]
            elif g in expense_goods_set:
                sale_non_core[g] = sale_by_goods[g]
            else:
                # 无法确定归属的 → 保守归入核心相关
                sale_core_related[g] = sale_by_goods[g]
        
        only_sell = [g for g in sale_core_related if g not in pur_core_by_goods]
        # 被排除的非核心销售（BOM缺失→可豁免）
        non_core_sell = [g for g in sale_non_core if g not in pur_core_by_goods]
        
        if only_sell:
            sell_amount_only = sum(sale_core_related[g]["amount"] for g in only_sell)
            sell_total_all = sum(sale_core_related[g]["amount"] for g in sale_core_related)
            pct = sell_amount_only / max(sell_total_all, 1) * 100
        
            # 制造业诊断：核心成本中有加工费+原材料→销售的是加工后的成品
            has_processing = any("加工费" in g or "加工" in g for g in pur_core_by_goods)
            expense_keywords_local = ["住宿","餐饮","餐费","加油","租赁","房租","物业","保险","通信","快递","办公","维修","服务费","咨询","广告","培训","差旅"]
            pur_raw = [g for g in pur_core_by_goods if not any(k in g for k in expense_keywords_local) and "加工" not in g]
            is_manufacturing = has_processing and len(pur_raw) > 0
        
            # BOM豁免说明
            bom_exempt_note = ""
            if non_core_sell:
                nc_amount = sum(sale_non_core[g]["amount"] for g in non_core_sell)
                bom_exempt_note = f"（已排除{len(non_core_sell)}类非核心销售{nc_amount:,.2f}元——若为制造业加工链条产出，BOM表缺失时不应将非核心销售标记为'有销无进'风险）"
        
            if is_manufacturing:
                pur_raw_list = pur_raw
                sell_list = only_sell
                raw_total = sum(pur_core_by_goods[g]["amount"] for g in pur_raw)
                proc_items = [g for g in pur_core_by_goods if "加工" in g]
                proc_total = sum(pur_core_by_goods[g]["amount"] for g in proc_items)
            
                desc = f"【主营业务成本识别后分析】将核心成本{len(pur_core_by_goods)}种商品与销项{len(sale_core_related)}种商品逐票交叉比对。{bom_exempt_note}\n\n"
                desc += f"发现{len(only_sell)}种商品仅销售无直接采购——"
                desc += f"销售了{'、'.join(sell_list[:3])}（金额{sell_amount_only:,.2f}元，占核心销项{pct:.2f}%），但核心进项中未发现同名商品的采购记录。\n\n"
            
                desc += f"进一步核查进项结构：\n"
                desc += f"① 加工费发票{len(proc_items)}笔（{'、'.join(proc_items[:3])}，合计{proc_total:,.2f}元）\n"
                desc += f"② 非费用类原材料{len(pur_raw)}种（{'、'.join(pur_raw_list[:3])}等，合计约{raw_total:,.2f}元）\n"
                desc += f"上述两个信号同时存在，表明原材料+加工费→成品，这是销项品名与进项品名不同的合理解释。\n\n"
            
                desc += f"销售的是加工后的成品（{'、'.join(sell_list[:2])}），采购的是原料（{'、'.join(pur_raw_list[:2])}），品名天然不同——买原料→委托加工→卖成品是制造业的标准流程。"
                desc += f"这与面包店买面粉卖面包、家具厂买木材卖桌椅是同一个道理。\n"
                desc += f"因此，{len(only_sell)}种商品'有销无进'不是虚开发票，而是制造业加工链条的正常结果。\n\n"
            
                desc += f"风险焦点从'有销无进=虚开'转移到了'加工链条是否真实'：\n"
                desc += f"① 进项原材料（{len(pur_raw)}种）能否通过加工真实产出销项成品（{len(only_sell)}种）？（需BOM表验证）\n"
                desc += f"② 加工费发票是真实外包加工还是仅为解释品名差异而虚开？（需加工合同和出入库记录）\n"
                desc += f"③ 如果纯贸易直接买成品，为什么找不到成品采购发票？（这才是真正的虚开风险）"
            
                inv_match_findings.append({
                    "type": "有销无进风险",
                    "level": "中风险", "score": 5,
                    "detail": f"【主营业务成本识别后】{len(only_sell)}类核心商品仅销售无直接采购记录，涉及金额{sell_amount_only:,.2f}元{bom_exempt_note}。",
                    "description": desc,
                    "how_found": f"先对{len(pur_invs)}张进项发票做主营业务成本识别（三层分类），对核心成本发票与销项逐品名交叉比对。发现{len(only_sell)}类销项商品从未出现在核心进项中。进一步检索进项中是否存在加工费（{has_processing}）和原材料采购（{len(pur_raw)}类），判定为制造业加工后产出成品——销项品名不匹配源于加工链条。",
                    "tax_impact": "制造业加工链条导致销项品名与进项品名不同属正常现象。但BOM表缺失则投入产出逻辑无法验证，加工费真实性无法判断。",
                    "policy_ref": "《发票管理办法》第二十二条（禁止虚开发票）；制造业加工链条导致的品名差异不自动构成虚开。",
                    "suggestion": f"① 提供BOM表验证加工链条（原料+加工费→能否产出成品）；② 提供委托加工合同、送料单、收货单；③ 如为纯贸易（直接买成品再卖），提供采购端对应的成品采购发票。资料齐全可排除虚开嫌疑。",
                    "category": "进销存匹配",
                    "rule_id": 337,
                    "source_chain": "进销存-主营业务成本识别-进销品名匹配",
                    "_cross_refs": ["缺少BOM表"]
                })
            else:
                inv_match_findings.append({
                    "type": "有销无进风险",
                    "level": "高风险", "score": 9,
                    "detail": f"【主营业务成本识别后】{len(only_sell)}类核心商品仅销售无采购记录，涉及金额{sell_amount_only:,.2f}元{bom_exempt_note}。",
                    "description": f"对进项做主营业务成本识别后，发现被查单位对外销售了{'、'.join(only_sell[:3])}等{len(only_sell)}种核心商品（金额{sell_amount_only:,.2f}元），但进项核心成本中未发现对应商品的采购记录。在没有采购的情况下对外销售，是虚开发票的典型特征。",
                    "how_found": f"先对{len(pur_invs)}张进项发票做主营业务成本识别（三层分类），对核心成本发票与销项逐品名交叉比对。发现{len(only_sell)}类销项商品的品名从未出现在核心进项中。",
                    "tax_impact": "虚开发票→刑事责任（刑法第205条，最高无期徒刑）+行政处罚（50万以下罚款）+税款追缴+滞纳金+纳税信用等级降为D级",
                    "policy_ref": "《发票管理办法》第二十二条（禁止虚开发票）；《刑法》第二百零五条（虚开增值税专用发票罪）；《重大税收违法失信主体信息公布管理办法》",
                    "suggestion": f"要求被查单位立即提供{len(only_sell)}种商品的采购来源证明材料。无法提供真实采购来源的，按虚开发票立案处理。",
                    "category": "进销存匹配",
                    "rule_id": 337,
                    "source_chain": "进销存-主营业务成本识别-进销品名匹配",
                })
        
        # ═══════════════════════════════════════════════════
        # 检查3：进销数量严重偏差（32）
        # 稽查方法论④-C：只对主营业务成本品名的进销数量做比对
        # 费用类品名（餐饮住宿汽油等）无数量概念参与无意义
        # ═══════════════════════════════════════════════════
        # 仅对核心成本品名（同时出现在进销中的）做数量比对
        core_goods_in_both = [g for g in sale_by_goods if g in pur_core_by_goods]
        matched = [(g, (sale_by_goods[g]["qty"] - pur_core_by_goods[g]["qty"])) 
                   for g in core_goods_in_both]
        big_diff = [(g, d) for g, d in matched if abs(d) > 100 and pur_core_by_goods[g]["qty"] > 0]
        if big_diff:
            big_diff.sort(key=lambda x: -abs(x[1]))
            top_diff = big_diff
            detail_parts = [f"{g}（销{sale_by_goods[g]['qty']:.2f}/进{pur_core_by_goods[g]['qty']:.2f}，差{d:.2f}）" for g,d in top_diff[:5]]
        
            # 排除说明：费用类不参与数量比对
            excluded_qty_note = f"本次仅对{len(core_goods_in_both)}种核心成本品名做进销数量比对，已排除{len(expense_goods_set & set(pur_by_goods.keys()))}类费用/报销品名（餐饮住宿汽油等无数量概念）。"
        
            inv_match_findings.append({
                "type": "进销数量严重偏差", "level": "中风险", "score": 6,
                "detail": f"【主营业务成本识别后】{len(big_diff)}类核心商品进销数量偏差超过100。典型：{'；'.join(detail_parts)}",
                "description": f"【主营业务成本识别后分析】{excluded_qty_note}\n\n"
                    + f"进销数量偏差分析：将{len(core_goods_in_both)}种核心成本品名的进销数量逐品名配对。"
                    + f"以'{top_diff[0][0]}'为例，销项开票数量{sale_by_goods[top_diff[0][0]]['qty']:.2f}但进项采购数量{pur_core_by_goods[top_diff[0][0]]['qty']:.2f}，差额{abs(top_diff[0][1]):.2f}。"
                    + f"如果销项数量>进项数量，可能存在：(1)未开票采购（原材料来源不明）；(2)上期库存结转未计入。"
                    + f"如果进项数量>销项数量，可能存在：(1)未开票销售（隐匿收入）；(2)存货积压未售出；(3)原材料损耗或用于非生产用途。",
                "how_found": f"先对{len(pur_invs)}张进项发票做主营业务成本识别，排除费用类后对{len(core_goods_in_both)}种核心品名做进销数量配对——逐品名对比进项采购数量和销项开票数量——发现{len(big_diff)}种核心商品的进销数量偏差超过100件，这不是正常库存波动能解释的。",
                "tax_impact": "进销数量严重偏差是账外经营和不实申报的典型特征。若销>进且无合理库存解释→可能存在未开票采购或虚开发票；若进>销且无合理库存解释→可能存在隐匿销售或存货异常损失。涉及增值税和企业所得税的少缴风险。",
                "suggestion": "要求企业提供：(1)每种偏差商品的期初期末库存数量；(2)偏差商品对应的采购合同和销售合同；(3)如为正常库存变动，提供进销存台账佐证。",
                "category": "进销存匹配",
            })
        
        # 总额概括
        sale_total = sum(float(inv.get("amount", 0) or 0) for inv in sal_invs)
        pur_total = sum(float(inv.get("amount", 0) or 0) for inv in pur_invs)
        pur_core_total = sum(float(inv.get("amount", inv.get("total", 0)) or 0) for inv in core_cost_invs)
        inv_match_findings.insert(0, {
            "type": "进销存虚拟匹配概览", "level": "低风险", "score": 2,
            "detail": f"基于{len(sal_invs)}张销项发票×{len(pur_invs)}张进项发票构建虚拟进销存。销项总额{sale_total:,.2f}元，进项总额{pur_total:,.2f}元（其中核心成本{pur_core_total:,.2f}元/{n_core}张，重大费用{n_major}张，日常报销{n_minor}张）。货物品类：销{len(sale_by_goods)}种/进{len(pur_by_goods)}种。",
            "category": "进销存匹配",
        })
    
    if inv_match_findings:
        pipeline_log.append(f"虚拟进销存分析: {len(inv_match_findings)}项发现")
    # ═══════════════════════════════════════════════════
    
    # ═══ 数据充分性守卫：全量解析失败时拒绝生成报告 ═══
    total_parsed = len(bank_txs) + len(invoices) + len(salaries) + len(social_security) + len(vouchers) + len(inventory)
    # 统计识别为unknown的文件数
    unknown_count = sum(1 for fr in file_results if fr["type"] == "unknown")
    zero_record_count = sum(1 for fr in file_results if fr["type"] != "unknown" and fr["type"] != "bank" and "提取0条" in str(fr.get("actions", [])))
    failure_count = sum(1 for fr in file_results if any("失败" in a for a in fr.get("actions", [])))
    
    # ═══ 涉税相关性评分：标记非涉税文件 ═══
    non_tax_files = 0
    for fr in file_results:
        if not fr.get("error") and fr["type"] not in ("unknown",):
            doc_obj = next((d for d in docs if d["original_name"] == fr["file"]), None)
            if doc_obj:
                try:
                    import xlrd as _xr, openpyxl as _ox
                    _ep = doc_obj["path"]
                    _ext = os.path.splitext(_ep)[1].lower()
                    if _ext == ".xls":
                        _wb = _xr.open_workbook(_ep); _s = _wb.sheet_by_index(0); _nr = _s.nrows
                    elif _ext == ".xlsx":
                        _wb = _ox.load_workbook(_ep, data_only=True); _s = _wb[_wb.sheetnames[0]]; _nr = _s.max_row
                    else: continue
                    _score = _score_tax_relevance(_s, _nr)
                    fr["tax_relevance"] = _score
                    if _score < 20:
                        fr["non_tax"] = True
                        non_tax_files += 1
                        fr["actions"].append(f"涉税相关度{_score}分-可能非财税资料")
                except: pass
    if non_tax_files > 0:
        pipeline_log.append(f"涉税相关性: {non_tax_files}个文件相关度低")
    
    if total_parsed == 0:
        fail_reasons = []
        if unknown_count > 0:
            unknown_files = [fr["file"] for fr in file_results if fr["type"] == "unknown"]
            fail_reasons.append(f"{unknown_count}个文件未能识别类型: {', '.join(unknown_files)}")
        if zero_record_count > 0:
            zero_files = [fr["file"] for fr in file_results if fr["type"] != "unknown" and "提取0条" in str(fr.get("actions", []))]
            fail_reasons.append(f"{zero_record_count}个文件识别成功但未提取到数据: {', '.join(zero_files)}")
        if failure_count > 0:
            fail_files = [fr["file"] for fr in file_results if any("失败" in a for a in fr.get("actions", []))]
            fail_reasons.append(f"{failure_count}个文件解析异常")
        
        return {"ok": False, "message": "所有文件解析失败，无法生成分析报告",
                "detail": "；".join(fail_reasons) if fail_reasons else "未提取到任何结构化数据",
                "files_count": len(docs), "pipeline_log": pipeline_log, "file_results": file_results,
                "suggestion": "请检查文件格式：1)确认Excel文件包含表头行 2)确认文件内容是财税相关数据(发票/工资/银行流水/凭证/社保等) 3)尝试用标准模板格式重新导出"}
    
    # _ 数据不足警告（少量数据，报告标注）
    low_data_warning = total_parsed < 10  # 少于10条记录视为数据不足
    
    # ── 凭证收入提取（区分开票/未开票）──
    voucher_revenue = {"invoiced": 0.0, "uninvoiced": 0.0, "total": 0.0, "rows": 0}
    for v in vouchers:
        acct = str(v.get("account", ""))
        if "主营业务收入" in acct:
            credit = float(v.get("credit", 0) or 0)
            summary = str(v.get("summary", ""))
            if credit <= 0: continue  # 结转行
            if "未开票" in summary or "无票" in summary:
                voucher_revenue["uninvoiced"] += credit
            elif "普票" in summary or "专票" in summary or "发票" in summary:
                voucher_revenue["invoiced"] += credit
            else:
                voucher_revenue["uninvoiced"] += credit
            voucher_revenue["total"] += credit
            voucher_revenue["rows"] += 1
    
    # ═══════════════════════════════════════════════════════════
    # Phase 1 — 初查：建立企业画像和全局快照
    # 推理引擎入口：创建AuditContext，跑初查阶段，
    # 产出企业画像+财务全景+主营业务成本识别+初查信号
    # 后续所有分析域都基于此context展开
    # ═══════════════════════════════════════════════════════════
    ctx = AuditContext()
    try:
        ctx = _phase1_triage(ctx, company_id, db, bank_txs, invoices, sal_invs, pur_invs, 
                             salaries, social_security, vouchers, inventory, docs, file_results, pipeline_log)
    except Exception as _p1e:
        pipeline_log.append(f"[Phase1] 初查异常: {_p1e}，使用默认企业画像继续")
        ctx.industry_profile = {"industry": "通用", "benchmarks": {}}
        ctx.red_flags = []
        ctx.yellow_flags = []
    
    # ═══ 调度中枢 ───
    comprehensive = {}
    orchestration_plan = {"pipeline_stages": [], "summary": "调度中枢未初始化"}
    try:
        data_profile = build_data_profile(bank_txs, invoices, salaries, social_security, vouchers, inventory, docs, file_results, ctx)
        orchestration_plan = build_orchestration_plan(data_profile)
        comprehensive["orchestration_plan"] = orchestration_plan
        pipeline_log.append(f"[ORCHESTRATOR] {orchestration_plan['summary']}")
    except Exception as _oe: pipeline_log.append(f"调度中枢异常: {_oe}")
    
    # ═══════════════════════════════════════════════════════════
    # 记忆检索：查询同行业/同模式的历史分析案例
    # ═══════════════════════════════════════════════════════════
    try:
        similar_cases = query_similar_cases(ctx)
        if similar_cases and similar_cases.get("similar_count", 0) > 0:
            pipeline_log.append(f"[MEMORY] 历史记忆: {similar_cases['similar_count']}条相似案例 (共{similar_cases['total_records']}条)")
        ctx._memory_insight = similar_cases.get("insight", "")
        ctx._memory_data = similar_cases
    except Exception:
        ctx._memory_insight = ""
        ctx._memory_data = {}
    
    # ═══════════════════════════════════════════════════════════
    # Phase 2 — 定向深挖：基于 Phase 1 信号选择性分析
    # 信号→域映射表驱动，只深挖触发了信号的域
    # ═══════════════════════════════════════════════════════════
    phase2_results = _phase2_deep_dive(ctx, company_id, db, bank_txs, invoices, sal_invs, pur_invs,
                                        salaries, social_security, vouchers, inventory, docs, file_results,
                                        contract_data, voucher_revenue, total_parsed, pipeline_log)
    # 记录 Phase 2 已覆盖的域名，避免后续 domain_results 重复
    phase2_domains_covered = set(dr["domain"] for dr in phase2_results)
    # 收集深度信息
    depth_levels = {}
    for dr in phase2_results:
        dom = dr.get("domain", "")
        if dom and dr.get("depth"):
            depth_levels[dom] = dr["depth"]
    
    domain_results = []
    
    # ═══ 预检测目标行业（供行业对标使用）═══
    _target_industry = ""
    if invoices:
        goods_list = []
        for inv in invoices:
            g = str(inv.get("goods", inv.get("货物或应税劳务名称", "")))
            if g: goods_list.append(g)
        if goods_list:
            goods_text = " ".join(goods_list)
            # 行业检测：匹配最精确的行业（双向匹配+优先长关键字）
            candidates = []
            industry_data = _load_industry_data()
            for kw in industry_data.get("benchmarks", {}):
                if kw == "_default": continue
                if kw in goods_text:
                    candidates.append((kw, len(kw)))
                else:
                    # 反向：检测商品关键词是否匹配行业名的子集
                    for word in set(goods_text.split()):
                        word = word.strip("*").strip()
                        if len(word) >= 2 and word in kw:
                            candidates.append((kw, len(word)))
                            break
            # 按匹配长度排序，取最长
            candidates.sort(key=lambda x: -x[1])
            if candidates:
                _target_industry = candidates[0][0]

    if bank_txs: domain_results.append({"domain": "资金全链路追踪", "findings": _domain_bank_tracking(bank_txs)})
    if sal_invs and pur_invs: domain_results.append({"domain": "进销毛利率分析", "findings": _domain_profit_analysis(sal_invs, pur_invs, inventory, voucher_revenue)})
    if sal_invs: domain_results.append({"domain": "个人交易风险", "findings": _domain_personal_transactions(sal_invs)})
    if pur_invs: domain_results.append({"domain": "供应商穿透分析", "findings": _domain_supplier_deep(pur_invs)})
    if vouchers: domain_results.append({"domain": "凭证科目异常", "findings": _domain_voucher_anomaly(vouchers)})
    if inventory: domain_results.append({"domain": "存货周转预警", "findings": _domain_inventory_turnover(inventory, sal_invs, pur_invs, bank_txs)})
    if bank_txs: domain_results.append({"domain": "税务缴纳一致性", "findings": _domain_tax_consistency(bank_txs, db, company_id)})
    if salaries or social_security: domain_results.append({"domain": "工资社保比对", "findings": _domain_salary_ss_hf_compare(salaries, social_security)})
    if invoices: domain_results.append({"domain": "发票生命周期", "findings": _domain_invoice_lifecycle(invoices)})
    if inv_match_findings: domain_results.append({"domain": "进销存匹配分析", "findings": inv_match_findings})
    # 无条件域加数据守卫：关键数据全空的域跳过，避免空数据触发误报
    _has_any_data = total_parsed > 0
    _has_inv_or_bank = len(invoices) > 0 or len(bank_txs) > 0
    _has_bank = len(bank_txs) > 0
    
    if _has_any_data: domain_results.append({"domain": "合同比对分析", "findings": _domain_contract_comparison(db, company_id, sal_invs, pur_invs)})
    else: domain_results.append({"domain": "合同比对分析", "findings": []})
    if _has_inv_or_bank: domain_results.append({"domain": "经营实质分析", "findings": _domain_business_substance(db, company_id, sal_invs, pur_invs, bank_txs, salaries)})
    else: domain_results.append({"domain": "经营实质分析", "findings": []})
    if invoices: domain_results.append({"domain": "发票深度特征", "findings": _domain_invoice_deep(invoices)})
    # 域14: 资料完备度（始终运行——空数据本身就是信号）
    doc_cplt_findings = _domain_document_completeness(docs, bank_txs, sal_invs, pur_invs, salaries, social_security, vouchers, inventory, trial_balance_data, contract_data, file_results, ctx.company_profile.get("industry", ""))
    # ── 记录缺失资料key到ctx，供Phase 4缺失后果自动触发使用 ──
    for f in doc_cplt_findings:
        if f.get("type") == "资料完备度综合评估" and f.get("items"):
            for item in f["items"]:
                missing_name = item.get("缺失资料", "")
                key = _CATEGORY_NAME_TO_KEY.get(missing_name, "")
                if key and key not in ctx.missing_doc_keys:
                    ctx.missing_doc_keys.append(key)
    domain_results.append({"domain": "资料完备度评估", "findings": doc_cplt_findings})
    # 域14.5: 账务系统缺失风险（有发票/流水但无凭证→无法验证账务真实性）
    _acct_risk = _check_accounting_system_gap(invoices, bank_txs, vouchers)
    if _acct_risk: domain_results.append({"domain": "账务系统风险", "findings": _acct_risk})
    # 域15: 多源交叉验证
    if _has_any_data: domain_results.append({"domain": "多源交叉验证", "findings": _domain_multi_source_cross(bank_txs, sal_invs, pur_invs, salaries, social_security, vouchers, inventory, db, company_id)})
    else: domain_results.append({"domain": "多源交叉验证", "findings": []})
    # 域15.5: 客户维度三源穿透分析（逐客户开票vs收款+合同验证+五时点确认）
    if sal_invs and bank_txs:
        domain_results.append({"domain": "客户维度三源穿透", "findings": _domain_customer_revenue_matching(bank_txs, sal_invs, contract_data, voucher_revenue)})
    else:
        domain_results.append({"domain": "客户维度三源穿透", "findings": []})
    # 域16: 扩展规则
    if _has_any_data: domain_results.append({"domain": "扩展审查规则", "findings": _domain_advanced_rules(bank_txs, sal_invs, pur_invs, salaries, social_security, vouchers, inventory)})
    else: domain_results.append({"domain": "扩展审查规则", "findings": []})
    # 域17: 凭证收入 vs 发票收入对比
    domain_results.append({"domain": "凭证发票收入对比", "findings": _domain_voucher_invoice_revenue_compare(voucher_revenue, sal_invs, bank_txs)})
    # 域18: 312规则全覆盖验证——对未触发的规则产出缺失数据结论 (需要在all_findings之后)
    # 域19: 跨域关联推理——单点发现→多域印证→证据链 (需要在all_findings之后)
    # 先跑不依赖all_findings的域
    if _has_any_data: domain_results.append({"domain": "收入时间线调查", "findings": _domain_revenue_timeline(vouchers, sal_invs, bank_txs)})
    else: domain_results.append({"domain": "收入时间线调查", "findings": []})
    if _has_inv_or_bank: domain_results.append({"domain": "供应商画像分析", "findings": _domain_supplier_profiling(pur_invs, bank_txs)})
    else: domain_results.append({"domain": "供应商画像分析", "findings": []})
    if _has_bank: domain_results.append({"domain": "资金流向追踪", "findings": _domain_fund_flow_mapping(bank_txs, sal_invs, pur_invs)})
    else: domain_results.append({"domain": "资金流向追踪", "findings": []})
    if _has_any_data: domain_results.append({"domain": "人员与业务匹配", "findings": _domain_workforce_profiling(salaries, voucher_revenue, bank_txs, social_security)})
    else: domain_results.append({"domain": "人员与业务匹配", "findings": []})
    if _has_inv_or_bank: domain_results.append({"domain": "发票存货付款三角验证", "findings": _domain_triangle_invoice_inventory_payment(pur_invs, inventory, bank_txs)})
    else: domain_results.append({"domain": "发票存货付款三角验证", "findings": []})
    if invoices: domain_results.append({"domain": "红冲作废发票追踪", "findings": _domain_red_void_invoice(invoices)})
    else: domain_results.append({"domain": "红冲作废发票追踪", "findings": []})
    # 经营实质地理分析
    if invoices and bank_txs: domain_results.append({"domain": "经营实质地理分析", "findings": _domain_business_premise_geo(bank_txs, invoices, docs, _target_industry)})
    else: domain_results.append({"domain": "经营实质地理分析", "findings": []})
    if _has_bank: domain_results.append({"domain": "利润现金流矛盾检测", "findings": _domain_profit_cashflow_gap(voucher_revenue, bank_txs, pur_invs)})
    else: domain_results.append({"domain": "利润现金流矛盾检测", "findings": []})
    if _has_bank: domain_results.append({"domain": "异常交易时间分析", "findings": _domain_temporal_anomaly(bank_txs)})
    else: domain_results.append({"domain": "异常交易时间分析", "findings": []})
    if _has_inv_or_bank: domain_results.append({"domain": "关联交易穿透检测", "findings": _domain_related_party_check(sal_invs, pur_invs, bank_txs)})
    else: domain_results.append({"domain": "关联交易穿透检测", "findings": []})
    if _has_inv_or_bank: domain_results.append({"domain": "资产折旧费用匹配", "findings": _domain_depreciation_match(bank_txs, pur_invs)})
    else: domain_results.append({"domain": "资产折旧费用匹配", "findings": []})
    if _has_any_data: domain_results.append({"domain": "行业对标分析", "findings": _domain_industry_benchmark(sal_invs, pur_invs, voucher_revenue, salaries, inventory, _target_industry)})
    else: domain_results.append({"domain": "行业对标分析", "findings": []})

    # ═══ 财务报表税务稽查分析（新增） ═══
    try:
        from engine.financial_analyzer import analyze_financial_statements
        tri_bal = next((d for d in (file_results or []) if d.get("type") == "trial_balance"), {})
        fin_findings = analyze_financial_statements({}, {}, {},
            vouchers or [], sal_invs or [], pur_invs or [], ctx)
        if fin_findings:
            domain_results.append({"domain": "财务报表分析", "findings": fin_findings})
            pipeline_log.append(f"财务报表分析: {len(fin_findings)}项发现")
    except Exception as _fe:
        pipeline_log.append(f"财务报表分析异常: {_fe}")

    # ═══ 税收优惠智能分析 ═══
    try:
        from engine.tax_incentive_analyzer import analyze_tax_incentives
        # 从已有数据中提取关键财务指标传给分析器
        _income_stmt = {}
        _balance_sheet = {}
        if trial_balance_data:
            # 从科目余额表提取资产总额
            _total_assets = 0
            for row in trial_balance_data:
                acct_code = str(row.get("code", row.get("科目编码", "")))[:4]
                if acct_code.startswith(("1",)):  # 1开头=资产类
                    _total_assets += float(row.get("close_debit", 0) or 0)
            if _total_assets > 0:
                _balance_sheet["total_assets"] = _total_assets
            # 从科目余额表提取收入/利润
            _total_revenue = 0
            _total_cost = 0
            for row in trial_balance_data:
                acct_code = str(row.get("code", row.get("科目编码", "")))[:4]
                if acct_code == "6001":  # 主营业务收入
                    _total_revenue += float(row.get("close_credit", 0) or 0)
                elif acct_code.startswith(("640", "6401", "6402", "5401")):  # 主营业务成本
                    _total_cost += float(row.get("close_debit", 0) or 0)
            if _total_revenue > 0:
                _income_stmt["revenue"] = _total_revenue
            if _total_cost > 0:
                _income_stmt["total_cost"] = _total_cost
                _income_stmt["net_profit"] = _total_revenue - _total_cost
        if not _income_stmt and vouchers:
            # 从凭证推算
            _rev = sum(float(v.get("credit", 0) or 0) for v in vouchers if "主营业务收入" in str(v.get("account_name", v.get("科目", ""))))
            _cost = sum(float(v.get("debit", 0) or 0) for v in vouchers if "主营业务成本" in str(v.get("account_name", v.get("科目", ""))))
            if _rev > 0: _income_stmt["revenue"] = _rev
            if _cost > 0: _income_stmt["total_cost"] = _cost
            if _rev > 0 and _cost > 0: _income_stmt["net_profit"] = _rev - _cost
        inc_findings, inc_opportunities = analyze_tax_incentives(
            ctx, sal_invs, pur_invs, bank_txs, salaries, _income_stmt, _balance_sheet, vouchers
        )
        if inc_findings:
            domain_results.append({"domain": "税收优惠检查-应享尽享", "findings": inc_findings})
        if inc_opportunities:
            domain_results.append({"domain": "税收优惠机会", "findings": inc_opportunities})
            pipeline_log.append(f"税收优惠分析: {len(inc_opportunities)}个机会")
    except Exception as _ie:
        pipeline_log.append(f"税收优惠分析异常: {_ie}")

    # ═══ 新增稽查域：增值税申报比对 ═══
    if _has_inv_or_bank:
        domain_results.append({"domain": "增值税申报比对", "findings": _domain_vat_declaration_compare(invoices, bank_txs, db, company_id)})
    else:
        domain_results.append({"domain": "增值税申报比对", "findings": []})
    
    # ═══ 新增稽查域：上下游穿透分析 ═══
    if invoices:
        domain_results.append({"domain": "上下游穿透分析", "findings": _domain_supply_chain_deep(invoices, bank_txs)})
    else:
        domain_results.append({"domain": "上下游穿透分析", "findings": []})
    
    # ═══ 新增稽查域：发票实质性审计（合规/单价/BOM）═══
    if invoices:
        domain_results.append({"domain": "发票实质性审计", "findings": _domain_invoice_audit(invoices, _target_industry)})
    else:
        domain_results.append({"domain": "发票实质性审计", "findings": []})

    # ═══════════════════════════════════════════════════════════
    # Phase 2 结果注入 + 去重
    # Phase 2 深挖的域优于盲跑的域（深挖有更好的上下文和针对性）
    # 移除被 Phase 2 覆盖的冗余域，再注入 Phase 2 结果
    # ═══════════════════════════════════════════════════════════
    if phase2_results:
        removed_count = 0
        filtered_results = []
        for dr in domain_results:
            if dr["domain"] not in phase2_domains_covered:
                filtered_results.append(dr)
            else:
                removed_count += 1
        domain_results = phase2_results + filtered_results  # Phase2结果排最前
        pipeline_log.append(f"[Phase2] 注入{len(phase2_results)}个深挖域, 去重移除{removed_count}个盲跑域")
    
    all_findings = []
    for dr in domain_results:
        for f in dr["findings"]:
            if isinstance(f, dict):
                all_findings.append({**f, "domain": dr["domain"]})
    # 过滤：确保 all_findings 中所有项都是 dict（防止错误字符串混入）
    all_findings = [f for f in all_findings if isinstance(f, dict)]
    
    # ── #5: 报告要求→域分析内建校验（12项标准在分析阶段即注入约束）──
    _quality_violations = 0
    for f in all_findings:
        desc = str(f.get("description", ""))
        detail = str(f.get("detail", ""))
        how = str(f.get("how_found", ""))
        policy = str(f.get("policy_ref", ""))
        level = str(f.get("level", ""))
        
        violations = []
        # 标准1: 第三人称检查
        for kw in ["你公司", "贵公司", "你们", "你企业"]:
            if kw in desc or kw in detail:
                violations.append("标准1: 非第三人称-" + kw)
                break
        # 标准2: 数量具体化
        if ("很多" in desc or "大量" in desc) and "笔" not in desc and "张" not in desc:
            violations.append("标准2: 数量模糊-使用了'很多/大量'未附具体数字")
        # 标准4: 结论可验证
        if len(how) < 10:
            violations.append("标准4: 发现过程不完整")
        # 标准7: 法规引用
        if len(policy) < 5 and level in ("高风险", "极高风险"):
            violations.append("标准7: 高风险发现缺少法规引用")
        # 标准9: 严重度
        if level not in ("高风险", "极高风险", "中风险", "低风险", "正常"):
            violations.append("标准9: 缺少风险等级")
        
        if violations:
            f["_quality_tags"] = violations
            _quality_violations += 1
    
    if _quality_violations > 0:
        pipeline_log.append(f"[质量标准] 内建校验发现{_quality_violations}条结论存在质量标签，将在最终报告中标注")

    # ═══════════════════════════════════════════════════════════
    # Phase 3 — 交叉验证：信号叠加检测 + 冲突消解 + 结论互证
    # Phase 4 — 综合定性：风险评级 + 核心问题 + 优先级排序 + 综合结论
    # ═══════════════════════════════════════════════════════════
    cross_findings, risk_adjustments = _phase3_cross_validate(ctx, all_findings, pipeline_log)
    
    # ── 保留原跨结论串联验证的轻量逻辑（Phase 3 的补充）──
    _bom_missing = any("缺少BOM" in f.get("type","") or "BOM" in f.get("type","") for f in all_findings)
    _has_expense_excluded = any("三层分类" in f.get("detail","") or "主营业务成本识别" in f.get("detail","") for f in all_findings)
    
    light_cross = 0
    for f in all_findings:
        ftype = f.get("type", "")
        desc = f.get("description", "")
        
        if "有销无进" in ftype and _bom_missing and "跨结论串联" not in desc:
            f["description"] = desc + (
                f"\n\n【跨结论串联验证】BOM缺失→非核心销售已豁免'有销无进'标记。核查焦点转移至加工链条。"
            )
            f["_cross_linked"] = True
            light_cross += 1
        
        if "有进无销" in ftype and _bom_missing and "跨结论串联" not in desc:
            f["description"] = desc + (
                f"\n\n【跨结论串联验证】BOM缺失→有进无销品名差异聚焦加工链条验证。"
            )
            f["_cross_linked"] = True
            light_cross += 1
        
        if "银行付款未匹配" in ftype and _has_expense_excluded and "跨结论串联" not in desc:
            f["description"] = desc + (
                f"\n\n【跨结论串联验证】日常费用报销已排除→未匹配统计仅含核心成本+重大费用。"
            )
            f["_cross_linked"] = True
            light_cross += 1
    
    if light_cross > 0:
        pipeline_log.append(f"轻量跨结论串联: {light_cross}项")
    
    # ── Phase 4：综合定性 ──
    synthesis = _phase4_synthesis(ctx, all_findings, cross_findings, pipeline_log)
    
    # ── 构建综合定性 finding（注入到 domain_results 和 all_findings）──
    synth_finding = None
    if synthesis:
        synth_finding = {
            "type": "综合定性结论",
            "level": synthesis["overall_risk"],
            "score": synthesis.get("risk_score", 0),
            "domain": "Phase4-综合定性",
            "detail": f"综合风险评分{synthesis['risk_score']}/100，共{synthesis['total_findings']}项发现，交叉验证{synthesis['cross_validated_patterns']}个模式",
            "description": synthesis["executive_summary"],
            "how_found": (
                f"Phase 4 综合定性引擎汇总全部{synthesis['total_findings']}项发现"
                f"（含Phase 3交叉验证{synthesis['cross_validated_patterns']}个模式），"
                f"经加权评分+资料质量折扣+信号叠加加成后综合评估。"
            ),
            "tax_impact": f"综合风险等级{synthesis['overall_risk']}。{synthesis['data_quality_note']}",
            "suggestion": "\n".join(
                [f"【P0 立即行动】{a}" for a in synthesis.get("prioritized_actions", {}).get("P0_立即行动", [])] +
                [f"【P1 重点关注】{a}" for a in synthesis.get("prioritized_actions", {}).get("P1_重点关注", [])] +
                [f"【P2 持续监控】{a}" for a in synthesis.get("prioritized_actions", {}).get("P2_持续监控", [])]
            ),
            "category": "综合定性",
            "_phase4_synthesis": True,
            "_synthesis_data": synthesis,
        }
        domain_results.insert(0, {"domain": "Phase4-综合定性", "findings": [synth_finding]})
        
        if cross_findings:
            domain_results.insert(1, {"domain": "Phase3-交叉验证", "findings": cross_findings})
        
        pipeline_log.append(f"[Phase4] 综合定性: {synthesis['overall_risk']} (评分{synthesis['risk_score']})")
    
    # ═══════ 290规则引擎: 将17文件数据完整导入空DB，跑全量规则后彻底清理 ═══════
    engine_results = []
    bk_ids, bt_ids, sr_ids = [], [], []
    if total_parsed > 0:  # 守卫: 无数据跳过，避免空DB触发误报规则
        try:
            from datetime import date as date_cls
            from decimal import Decimal as D
            from database import BookkeepingInvoice, BankTransaction, SalaryRecord as SR
            
            # ═══ 金额转换: 统一转Decimal，避免Decimal+float类型错误 ═══
            def _to_dec(v):
                try: return D(str(float(v or 0)))
                except: return D("0")
            
            # ═══ 临时导入: 全量导入 ═══
            # 发票
            for inv in invoices:
                try:
                    bk = BookkeepingInvoice(company_id=company_id,
                        digital_invoice_no=str(inv.get("inv_no", ""))[:50],
                        seller_name=str(inv.get("seller", ""))[:100],
                        buyer_name=str(inv.get("buyer", ""))[:100],
                        goods_name=str(inv.get("goods", ""))[:200],
                        total_amount=_to_dec(inv.get("total", inv.get("amount"))),
                        amount=_to_dec(inv.get("amount")),
                        tax_amount=_to_dec(inv.get("tax")),
                        invoice_date=datetime.now().date())
                    db.add(bk); db.flush(); bk_ids.append(bk.id)
                except: pass
            # 银行流水
            for tx in bank_txs:
                try:
                    d_str = tx.get("date", tx.get("transaction_date", ""))
                    if d_str and len(str(d_str)) >= 8:
                        ds = str(d_str)
                        bt = BankTransaction(company_id=company_id,
                            transaction_date=date_cls(int(ds[:4]), int(ds[4:6]), int(ds[6:8])),
                            counterparty_name=str(tx.get("counterparty", tx.get("counterparty_name", "")))[:100],
                            debit_amount=_to_dec(tx.get("debit")), credit_amount=_to_dec(tx.get("credit")),
                            amount=abs(_to_dec(tx.get("amount"))), summary=str(tx.get("summary", ""))[:200])
                        db.add(bt); db.flush(); bt_ids.append(bt.id)
                except: pass
            # 工资
            for s in salaries:
                try:
                    salary_val = _to_dec(s.get("salary", s.get("net", s.get("gross", 0))))
                    sr = SR(company_id=company_id,
                        employee_name=str(s.get("name", ""))[:50],
                        current_income=salary_val,
                        taxable_income=salary_val,
                        period=str(s.get("period", "2025-01"))[:20])
                    db.add(sr); db.flush(); sr_ids.append(sr.id)
                except: pass
            try:
                db.commit()
                pipeline_log.append(f"[临时]数据导入DB: {len(bk_ids)}发票+{len(bt_ids)}流水+{len(sr_ids)}工资")
            except Exception as _ce:
                pipeline_log.append(f"[临时]数据导入DB失败(DB只读/权限不足): {_ce}，跳过DB写入，继续内存分析")
                try: db.rollback()
                except: pass
                bk_ids, bt_ids, sr_ids = [], [], []  # 清空ID列表，避免后续清理报错

            # 读取实际规则数
            _real_rule_count = 1512
            try:
                _rp = os.path.join(_PROJECT_ROOT, "static", "tax_risk_rules_local_export.json")
                if os.path.exists(_rp):
                    with open(_rp, "r", encoding="utf-8") as _rf:
                        _real_rule_count = len(json.load(_rf))
            except: pass

            # 运行规则引擎
            try:
                from tax_risk import get_tax_risk_report
                from datetime import date as date_cls2
                _now = date_cls2.today()
                period_start = f"{_now.year - 2}-01-01"
                period_end = f"{_now.year}-12-31"
                engine_results = get_tax_risk_report(db=db, company_id=company_id,
                    period_from=period_start, period_to=period_end)
                # ═══ 行业过滤：排除不适用行业的制造专有规则 ═══
                _manu_only_rules = {"考勤记录与计件工资的产量反推", "计件工资"}
                ind = (ctx.company_profile or {}).get("industry", "")
                _is_manu = any(kw in str(ind) for kw in ["制造", "生产", "加工", "工业", "工厂", "车间"])
                if not _is_manu:
                    engine_results = [r for r in engine_results if r.get("item", "") not in _manu_only_rules]
                    pipeline_log.append(f"[行业过滤] 非制造业，已排除制造专有规则（{len(_manu_only_rules)}条）")
                pipeline_log.append(f"{_real_rule_count}条规则引擎: 发现{len(engine_results)}条风险")
            except Exception as re:
                pipeline_log.append(f"规则引擎异常: {re}")
        finally:
            # ── 审计基础检查：在临时数据清理前运行 ──
            try:
                from audit import audit_all
                audit_result = audit_all(company_id)
                # audit_all 返回 {"company_id", "results", "errors", "passed", "total_errors"}
                # 真正的检查项在 results 子 dict 里
                checks = audit_result.get("results", {})
                if not isinstance(checks, dict) or len(checks) == 0:
                    checks = {k: v for k, v in audit_result.items() if k not in ("company_id", "results", "errors", "passed", "total_errors")}
                audit_findings = []
                audit_errors = 0
                for check_name, count in checks.items():
                    if check_name == "errors":
                        continue
                    try:
                        c = int(count) if not isinstance(count, (list, dict)) else len(count)
                        if c > 0:
                            audit_errors += c
                            audit_findings.append({
                                "type": f"审计检查：{check_name}",
                                "level": "中风险", "score": 5,
                                "detail": f"{check_name}检查发现{c}项异常。",
                                "suggestion": f"请排查{check_name}相关问题。"
                            })
                    except (TypeError, ValueError):
                        pass
                if audit_errors > 0:
                    domain_results.append({"domain": "审计基础检查", "findings": audit_findings})
            except Exception as e:
                pipeline_log.append(f"审计检查异常: {e}")
            
            # ═══ 彻底清理: 上传资料仅用于资料风险分析报告，不污染其他模块 ═══
            try:
                if bk_ids: db.query(BookkeepingInvoice).filter(BookkeepingInvoice.id.in_(bk_ids)).delete(synchronize_session=False)
                if bt_ids: db.query(BankTransaction).filter(BankTransaction.id.in_(bt_ids)).delete(synchronize_session=False)
                if sr_ids: db.query(SR).filter(SR.id.in_(sr_ids)).delete(synchronize_session=False)
                db.commit()
                pipeline_log.append("已清理全部临时数据，DB恢复初始状态（与其他模块数据隔离）")
            except Exception as e:
                pipeline_log.append(f"清理临时数据异常: {e}")
                try: db.rollback()
                except: pass
    
    all_findings.extend(engine_results)
    # 再次过滤非 dict 项（引擎结果中可能有错误字符串）
    all_findings = [f for f in all_findings if isinstance(f, dict)]

    # ── 域18 & 域19: 依赖all_findings的域，必须在all_findings构建完成后运行 ──
    domain_results.append({"domain": "规则全覆盖验证", "findings": _domain_rule_coverage(all_findings, bank_txs, sal_invs, pur_invs, vouchers, salaries, social_security, inventory, docs)})
    domain_results.append({"domain": "跨域关联推理", "findings": _domain_cross_domain_reasoning(all_findings, bank_txs, sal_invs, pur_invs, vouchers, inventory)})
    # 跨域线索链：加载 cross_domain_clues.json 匹配发现
    if all_findings:
        domain_results.append({"domain": "跨域线索链", "findings": _domain_cross_domain_clues(all_findings)})
    # 跨域分析链：加载 cross_domain_analysis.json 推理分析
    if all_findings:
        domain_results.append({"domain": "跨域分析链", "findings": _domain_cross_domain_analysis(all_findings)})

    # ── 同类风险合并：将仅参数不同的同类发现合并为一条 ──
    for dr in domain_results:
        dr["findings"] = _merge_similar_findings(dr["findings"])
    
    # 重建 all_findings（合并后数量变了）
    all_findings = []
    for dr in domain_results:
        for f in dr["findings"]:
            all_findings.append({**f, "domain": dr["domain"]})
    all_findings.extend(engine_results)
    # 过滤掉非dict项（某些函数返回字符串混入）
    all_findings = [f for f in all_findings if isinstance(f, dict)]
    
    # ── 重建后注入 Phase 4 综合定性和 Phase 3 交叉验证 ──
    # （此处注入确保不被 _merge_similar_findings + domain_results 重建覆盖）
    if synthesis:
        all_findings.insert(0, synth_finding)
    if cross_findings:
        for cf in reversed(cross_findings):
            all_findings.insert(0, cf)
    
    # ── 证据溯源：为所有发现标注原始数据来源 ──
    try:
        all_findings = _enrich_evidence_trace(ctx, all_findings, file_results)
    except Exception:
        pass
    
    # ── 趋势发现：从ctx重新注入（Phase 4已生成但all_findings重建会丢失）──
    trend_findings_ext = getattr(ctx, 'trend_findings', [])
    if trend_findings_ext:
        all_findings.extend(trend_findings_ext)

    
    # ── 同类风险合并已移至 _apply_methodology_filter 的去重逻辑中 ──
    # (此处原有的 _normalize_type 合并过于激进，会误杀实质性发现)
    # merged_map 相关代码已禁用
    merged_count = 0

    # ═══════════════════════════════════════════════════
    # 链驱动分析引擎：线索链→逐步检查数据→触发规则→生成证据
    # ═══════════════════════════════════════════════════
    # ── 防御：过滤 all_findings 中非 dict 元素（避免 str 无 .get 崩溃）──
    all_findings = [f for f in all_findings if isinstance(f, dict)]
    
    chain_execution = []  # 每条链的执行结果
    chain_findings = []   # 链驱动生成的新发现
    try:
        chain_path = os.path.join(_PROJECT_ROOT, "static", "audit_chains.json")
        rules_path = os.path.join(_PROJECT_ROOT, "static", "tax_risk_rules_local_export.json")
        if os.path.exists(chain_path) and os.path.exists(rules_path):
            with open(chain_path, "r", encoding="utf-8") as cf:
                chains_data = json.load(cf)
            with open(rules_path, "r", encoding="utf-8") as rf:
                rules_data = json.load(rf)
            
            # 构建规则查找
            rule_map = {r["id"]: r for r in rules_data}
            # 构建现有发现的type→finding映射（用于复用已有分析结果）
            existing_finding_map = {}
            for f in all_findings:
                key = f.get("type", "").lower().replace(" ", "")
                existing_finding_map[key] = f
            
            # 收集所有可用的数据关键词（用于规则触发检测）
            data_keywords = set()
            for tx in bank_txs:
                cp = str(tx.get("counterparty", ""))
                summary = str(tx.get("summary", ""))
                if cp: data_keywords.add(cp[:20])
                if summary: data_keywords.update(summary[:30].replace(" ",""))
            for inv in invoices:
                goods = str(inv.get("goods", inv.get("货物或应税劳务名称", "")))
                seller = str(inv.get("seller", inv.get("销方名称", "")))
                if goods: data_keywords.update(goods[:20].replace(" ",""))
                if seller: data_keywords.add(seller[:20])
            for sal in salaries:
                name = str(sal.get("name", ""))
                if name: data_keywords.add(name)
            
            # 汇总数据特征
            has_bank = len(bank_txs) > 0
            has_invoice = len(invoices) > 0
            has_salary = len(salaries) > 0
            has_social = len(social_security) > 0
            has_voucher = len(vouchers) > 0
            total_items = len(bank_txs) + len(invoices) + len(salaries) + len(social_security)
            
            # 提取数据中的数值特征
            bank_total_in = sum(tx.get("credit", 0) for tx in bank_txs)
            bank_total_out = sum(tx.get("debit", 0) for tx in bank_txs)
            inv_total = sum(float(inv.get("amount", 0) or 0) for inv in invoices)
            sal_total = sum(float(sal.get("salary", sal.get("本期收入", 0)) or 0) for sal in salaries)
            # 第三方收款检测
            third_party_keywords = ["支付宝","微信","财付通","个人","张三","李四","王五"]
            third_party_count = sum(1 for tx in bank_txs if any(k in str(tx.get("counterparty","")) for k in third_party_keywords))
            
            # 获取目标企业行业（从DB读取实际行业，不使用关键词推测）
            _db_company = db.query(Company).filter(Company.id == company_id).first()
            target_industry = ""
            if _db_company:
                target_industry = (_db_company.industry_code or "") + " " + (_db_company.business_scope or "")
            # 行业关键词映射：发票推断行业 → audit_chains 中的行业链名称前缀
            # 注意：优先使用联网核查获取的真实行业(industry_online)，而非关键词推测
            def _chain_matches_industry(chain_name):
                """判断行业特化链是否匹配目标企业行业，全行业通用链不过滤"""
                if not chain_name or not chain_name.startswith("行业-"):
                    return True  # 非行业链，全部执行
                if not target_industry:
                    return False  # 不知道行业，跳过所有行业特化链
                # 提取行业名称
                chain_industry = chain_name.split("行业-", 1)[1] if "行业-" in chain_name else ""
                matched_industry = None
                for ind_kw, chain_prefix in _load_industry_data().get("chain_prefixes", {}).items():
                    if ind_kw in target_industry and chain_name.startswith(chain_prefix):
                        matched_industry = ind_kw
                        break
                if not matched_industry:
                    return False
                # 安全检查：关键词≥3字（排除2字短词的误匹配，如"体育"意外出现在经营范围中）
                if len(matched_industry) < 3:
                    # 2字关键词容易误匹配，要求完整词边界
                    import re as _re_ind
                    if not _re_ind.search(r'(?:^|\s|；|，|、)' + matched_industry + r'(?:$|\s|；|，|、)', target_industry):
                        return False
                return True
            
            # 逐一执行每条线索链
            chain_stats = []
            total_chains = len(chains_data.get("chains", []))
            triggered_count = 0
            skipped_chains = 0
            
            for chain in chains_data.get("chains", []):
                if not isinstance(chain, dict): continue
                if chain.get("chain_type") != "线索链": continue  # 只执行线索链
                
                # 行业特化链过滤：仅匹配时才执行
                chain_name = chain.get("name", "")
                if not _chain_matches_industry(chain_name):
                    skipped_chains += 1
                    continue
                
                steps_exec = []  # 每条步骤的执行结果
                triggered_steps = 0
                total_steps = len(chain.get("investigation_path", []))
                chain_triggered = False
                
                for step in chain.get("investigation_path", []):
                    if not isinstance(step, dict): continue
                    rid = step.get("rule_id")
                    rule = rule_map.get(rid) if rid else None
                    step_name = step.get("step", "")
                    rule_item = step.get("rule_item", "")
                    step_level = step.get("level", "")
                    
                    # 检查该规则是否可被当前数据触发
                    triggered = False
                    reason = "数据不足"
                    finding_ref = None
                    
                    if not rule:
                        reason = "规则未找到"
                    elif total_items == 0:
                        reason = "无数据"
                    else:
                        # ═══ 真正数据验证引擎 ═══
                        verified, v_reason, v_confidence, v_evidence = _verify_rule_against_data(
                            rule, bank_txs, invoices, salaries, social_security, vouchers)
                        
                        if v_confidence >= 0.8:
                            triggered = True
                            reason = f"数据验证: {v_reason}"
                        elif v_confidence >= 0.5:
                            rule_text = (rule.get("item", "") + " " + rule.get("detail", ""))
                            import re as _re_chain
                            rule_kws = set(_re_chain.findall(r'[\u4e00-\u9fff]{2,6}', rule_text))
                            data_hits = sum(1 for kw in rule_kws if kw in str(data_keywords))
                            if verified or data_hits >= 3:
                                triggered = True
                                reason = f"综合判断(置信{v_confidence}): {v_reason}"
                            else:
                                reason = f"验证不充分: {v_reason}"
                        else:
                            # 低置信度→回退关键词+已有发现检查
                            rule_text = rule.get("item", "").lower().replace(" ", "")
                            if rule_text in existing_finding_map:
                                triggered = True
                                reason = "已命中现有发现"
                                finding_ref = existing_finding_map[rule_text].get("type", "")
                            elif "缺失" in rule_item or "不完备" in rule_item or "无" in rule_item:
                                triggered = bool(total_items)
                                reason = "缺失检查触发" if total_items else "无数据"
                            else:
                                reason = f"验证未通过: {v_reason}"
                    
                    if triggered:
                        triggered_steps += 1
                        if not chain_triggered:
                            chain_triggered = True
                            triggered_count += 1
                    
                    steps_exec.append({
                        "step": step_name,
                        "rule_id": rid,
                        "rule_item": rule_item[:40],
                        "level": step_level,
                        "triggered": triggered,
                        "reason": reason,
                        "finding_ref": finding_ref,
                    })
                
                # 只在至少有1步触发时记录链执行结果
                if chain_triggered or len([s for s in steps_exec if s["triggered"]]) > 0:
                    chain_execution.append({
                        "chain_name": chain["name"],
                        "chain_type": chain.get("chain_type", ""),
                        "total_steps": total_steps,
                        "triggered_steps": triggered_steps,
                        "triggered_ratio": round(triggered_steps / max(total_steps, 1) * 100),
                        "steps": steps_exec,
                    })
            
            # 如果链触发了但现有发现中没对应的规则，生成新发现
            for ce in chain_execution:
                for s in ce["steps"]:
                    if s["triggered"] and not s.get("finding_ref") and s.get("rule_id"):
                        rule = rule_map.get(s["rule_id"])
                        if rule and s["rule_item"] not in [f.get("type", "") for f in all_findings]:
                            # ── 特殊处理：收款开票偏差 → 逐笔匹配 ──
                            if s["rule_id"] == 217:
                                from collections import defaultdict as _dd2
                                # 银行收款按收款方分组（贷方=收入）
                                bank_by_counterparty = _dd2(float)
                                for tx in bank_txs:
                                    cp = str(tx.get("counterparty", tx.get("counterparty_name", ""))).strip()
                                    credit = float(tx.get("credit", 0) or 0)
                                    if cp and credit > 0:
                                        bank_by_counterparty[cp] += credit
                                # 销项发票按购买方分组
                                inv_by_buyer = _dd2(float)
                                for inv in sal_invs:
                                    buyer = str(inv.get("buyer", inv.get("购买方名称", ""))).strip()
                                    amt = float(inv.get("amount", inv.get("total", 0)) or 0)
                                    if buyer and amt > 0:
                                        inv_by_buyer[buyer] += amt
                                
                                # 计算总体偏差
                                total_receipts = sum(bank_by_counterparty.values())
                                total_sales = sum(inv_by_buyer.values())
                                dev_pct = round(abs(total_receipts - total_sales) / max(total_sales, 1) * 100)
                                
                                # 逐客户/收款方对比
                                all_names = set(list(bank_by_counterparty.keys()) + list(inv_by_buyer.keys()))
                                match_details = []
                                for name in sorted(all_names, key=lambda n: bank_by_counterparty.get(n, 0) + inv_by_buyer.get(n, 0), reverse=True)[:15]:
                                    brev = bank_by_counterparty.get(name, 0)
                                    iamt = inv_by_buyer.get(name, 0)
                                    gap = brev - iamt
                                    if abs(gap) > 1000:  # 只显示有偏差的
                                        match_details.append({
                                            "往来方": name,
                                            "银行收款": f"{brev:,.2f}",
                                            "开票金额": f"{iamt:,.2f}",
                                            "偏差": f"{gap:+,.0f}",
                                            "判断": "收款＞开票→未开票收入存疑" if gap > 0 else "开票＞收款→应收账款/现金交易"
                                        })
                                
                                detail_text = (
                                    f"银行收款总额{total_receipts:,.2f}元 vs 销项开票{total_sales:,.2f}元，"
                                    f"偏差{dev_pct}%。"
                                    f"{'银行收款大于开票，需核查是否有未开票收入。' if total_receipts > total_sales else '开票大于银行收款，需核查应收账款回收情况。'}"
                                    f"{'逐户比对发现' + str(len(match_details)) + '户存在显著偏差。' if match_details else ''}"
                                )
                                
                                suggestion_text = (
                                    f"①已自动完成银行收款与销项开票的逐户比对（共{len(all_names)}户）；"
                                    f"②{'收款超出开票的' + str(sum(1 for m in match_details if m['偏差'].startswith('+')) if match_details else '0') + '户需提供未开票收入申报记录；' if match_details else ''}"
                                    f"③{'开票超出收款的' + str(sum(1 for m in match_details if m['偏差'].startswith('-')) if match_details else '0') + '户需提供应收账款明细和回款计划' if match_details else ''}"
                                )
                                
                                chain_findings.append({
                                    "type": s["rule_item"][:40],
                                    "level": rule.get("level", "中风险"),
                                    "score": rule.get("score", 5),
                                    "detail": detail_text[:300],
                                    "description": detail_text[:300],
                                    "how_found": f"逐户比对{len(all_names)}个往来方：银行贷方收入vs销项发票价税合计→发现{len(match_details)}户偏差",
                                    "tax_impact": rule.get("tax_impact", ""),
                                    "policy_ref": rule.get("policy_ref", ""),
                                    "suggestion": suggestion_text,
                                    "category": rule.get("category", ""),
                                    "chain_driven": True,
                                    "source_chain": "资金流-发票收付款匹配",
                                    "items": match_details,
                                })
                            else:
                                # 非R217的链驱动发现：清洗来源信息，去除内部调试标识
                                clean_chain_name = ce["chain_name"]
                                # 去除"行业-XX-"前缀，只保留实质罪名
                                for prefix_key in _load_industry_data().get("chain_prefixes", {}).values():
                                    if clean_chain_name.startswith(prefix_key + "-"):
                                        clean_chain_name = clean_chain_name[len(prefix_key) + 1:]
                                        break
                                clean_detail = rule.get("detail", "")[:200]
                                clean_suggestion = rule.get("suggestion", "")
                                # 如果suggestion是懒建议"逐笔核对"，替换为有意义的方向
                                if "逐笔核对" in (clean_suggestion or "") and "已自动完成" not in clean_suggestion:
                                    clean_suggestion = f"根据实际数据分析：规则「{rule.get('item','')}」触发。请补充{pipeline_log[-1] if pipeline_log else '相关'}佐证材料。"
                                chain_findings.append({
                                    "type": s["rule_item"][:40],
                                    "level": rule.get("level", "中风险"),
                                    "score": rule.get("score", 5),
                                    "detail": clean_detail,
                                    "description": clean_detail,
                                    "how_found": f"经对{len(bank_txs)}条流水、{len(invoices)}条发票、{len(salaries)}条工资、{len(social_security)}条社保的数据交叉分析，触发「{clean_chain_name}」线索。",
                                    "tax_impact": rule.get("tax_impact", ""),
                                    "policy_ref": rule.get("policy_ref", ""),
                                    "suggestion": clean_suggestion,
                                    "category": rule.get("category", ""),
                                    "chain_driven": True,
                                    "source_chain": clean_chain_name,
                                })
            
            # 合并链驱动发现到总发现列表
            if chain_findings:
                all_findings.extend(chain_findings)
            
            # ── 为链驱动发现补全规则匹配（用于证据链闭环检测）──
            # 修复：使用词级匹配(2+字中文词组)替代字符级匹配，避免误匹配
            import re as _re_cf
            for f in chain_findings:
                f_type = str(f.get("type", ""))
                f_cat = str(f.get("category", "")).lower()
                f_detail = str(f.get("detail", ""))[:100]
                matched_ids = []
                # 提取finding中的2+字中文关键词
                type_kws = set(_re_cf.findall(r'[\u4e00-\u9fff]{2,8}', f_type))
                detail_kws = set(_re_cf.findall(r'[\u4e00-\u9fff]{2,8}', f_detail))
                all_kws = type_kws | detail_kws
                for r in rules_data:
                    r_item = str(r.get("item", ""))
                    r_cat = str(r.get("category", "")).lower()
                    r_detail = str(r.get("detail", ""))[:100]
                    # 词级匹配：2+字关键词命中
                    hits = sum(1 for kw in all_kws if kw in r_item or kw in r_detail)
                    cat_match = f_cat and r_cat and (f_cat in r_cat or r_cat in f_cat)
                    # 修复：要求3+词命中或2词命中+分类一致
                    if hits >= 3 or (hits >= 2 and cat_match):
                        matched_ids.append(r["id"])
                f["matched_rule_ids"] = matched_ids
                f["matched_rule_count"] = len(matched_ids)
            
            chain_stats = [ce for ce in chain_execution if ce["triggered_steps"] > 0]
            chain_stats.sort(key=lambda x: -x["triggered_steps"])
            
            # ═══════════════════════════════════════════════════
            # 证据链闭环检测：收集所有触发规则 → ≥60% → 违法事实闭环
            # ═══════════════════════════════════════════════════
            evidence_closures = []
            # 收集所有触发的规则ID：来自已有发现 + 链驱动发现 + 链执行记录
            triggered_rule_ids_for_evidence = set()
            for f in all_findings:
                for rid in f.get("matched_rule_ids", []):
                    triggered_rule_ids_for_evidence.add(rid)
            # 也直接从链执行记录中收集
            for ce in chain_execution:
                for s in ce.get("steps", []):
                    if s.get("triggered") and s.get("rule_id"):
                        triggered_rule_ids_for_evidence.add(s["rule_id"])
            
            for chain in chains_data.get("chains", []):
                if chain.get("chain_type") != "证据链": continue
                
                total_steps = len(chain.get("investigation_path", []))
                if total_steps < 3: continue
                
                # 计算该证据链中触发的规则数
                triggered_in_chain = 0
                step_results = []
                for step in chain.get("investigation_path", []):
                    rid = step.get("rule_id")
                    hit = rid in triggered_rule_ids_for_evidence
                    if hit:
                        triggered_in_chain += 1
                    step_results.append({
                        "step": step.get("step", ""),
                        "rule_id": rid,
                        "rule_item": step.get("rule_item", "")[:30],
                        "level": step.get("level", ""),
                        "triggered": hit,
                    })
                
                ratio = triggered_in_chain / total_steps
                
                if ratio >= 0.5:  # ≥50%触发即记录
                    evidence_closures.append({
                        "chain_name": chain["name"],
                        "total_steps": total_steps,
                        "triggered_steps": triggered_in_chain,
                        "ratio": round(ratio * 100),
                        "closed": (ratio >= 0.6 and triggered_in_chain >= 3),  # 修复：≥60%且≥3条规则才闭环
                        "steps": step_results,
                    })
                    
                    # 闭环的链 → 生成违法事实发现 + 升级风险等级
                    # 修复：增加多源交叉验证——触发规则须来自≥2个数据域
                    if ratio >= 0.6 and triggered_in_chain >= 3:
                        # 检查触发的规则是否来自多数据源（多角度互证）
                        triggered_rules = [step_results[i] for i, s in enumerate(step_results) if s["triggered"]]
                        source_domains = set()
                        for tr in triggered_rules:
                            r_id = tr.get("rule_id")
                            if r_id and r_id in rule_map:
                                r_cat = str(rule_map[r_id].get("category", ""))
                                source_domains.add(r_cat[:6])
                        
                        # 修复：需≥2个数据域交叉验证才闭环，单域触发即使100%也不闭环
                        if len(source_domains) >= 2:
                            # 生成违法事实闭环发现
                            step_items = [s["rule_item"] for s in step_results if s["triggered"]]
                            policy_items = list(set(s.get("policy_ref","") for step in chain.get("investigation_path",[]) for s in [step] if s.get("rule_id") in triggered_rule_ids_for_evidence))
                            
                            all_findings.append({
                                "type": f"证据链闭环：{chain['name'][:30]}",
                                "level": "高风险",
                                "score": 9,
                                "detail": f"证据链[{chain['name']}]中{triggered_in_chain}/{total_steps}条规则触发({round(ratio*100)}%)，跨{len(source_domains)}域交叉验证，构成违法事实闭环。命中规则：{'、'.join(step_items)}",
                                "description": f"该证据链覆盖{total_steps}条关联规则，其中{triggered_in_chain}条被{len(source_domains)}个数据域验证命中，触发率{round(ratio*100)}%。根据《税务稽查工作规程》，多源交叉互证形成完整证据闭环，应启动正式稽查程序。",
                                "how_found": f"证据链闭环检测：{chain['name']} → {triggered_in_chain}/{total_steps}规则命中({len(source_domains)}域交叉) → 自动判定违法事实闭环",
                                "tax_impact": "补税+0.5-5倍罚款+滞纳金+移送公安",
                                "policy_ref": ";".join(policy_items) if policy_items else "《税收征收管理法》《税务稽查工作规程》",
                                "suggestion": f"该证据链已闭环，建议：(1)启动正式稽查立案程序 (2)调取完整账簿资料 (3)对{'、'.join(step_items)}进行重点核实",
                                "category": chain.get("sub_topic", "综合"),
                                "chain_closure": True,
                                "source_chain": chain["name"],
                                "cross_domains": len(source_domains),
                            })
                        else:
                            # 单域触发：写入证据链记录但不闭环，标注需多源验证
                            evidence_closures[-1]["closed"] = False
                            evidence_closures[-1]["note"] = f"仅{len(source_domains)}域触发，需多源交叉验证"
            
            # 按闭环优先排序
            evidence_closures.sort(key=lambda x: (-x["closed"], -x["ratio"]))
            
            if evidence_closures:
                closed_count = sum(1 for e in evidence_closures if e["closed"])
                pipeline_log.append(f"证据链闭环检测: {len(evidence_closures)}条≥50%, {closed_count}条≥60%闭环")
                for ec in evidence_closures:
                    if ec["closed"]:
                        pipeline_log.append(f"  闭环: {ec['chain_name'][:30]} {ec['triggered_steps']}/{ec['total_steps']}={ec['ratio']}%")
            
            comprehensive["evidence_closures"] = evidence_closures
            comprehensive["closed_chain_count"] = sum(1 for e in evidence_closures if e["closed"])
            # ═══════════════════════════════════════════════════
            
            if chain_execution:
                pipeline_log.append(f"链驱动引擎: {len(chain_execution)}条线索链执行({skipped_chains}条行业不匹配跳过), {triggered_count}条触发, {len(chain_findings)}条新发现")
            if evidence_closures:
                pipeline_log.append(f"证据链闭环: {sum(1 for e in evidence_closures if e['closed'])}条闭环({len(triggered_rule_ids_for_evidence)}条规则参与判定)")
            pipeline_log.append(f"全链路执行: 线索链{len(chain_execution)}条 → 证据链{len(evidence_closures)}条 → 规则{len(triggered_rule_ids_for_evidence)}条触发")
            comprehensive["chain_execution"] = chain_stats
            comprehensive["chain_triggered_count"] = triggered_count
            comprehensive["chain_total_count"] = len(chain_execution)

            # ── 合同/关联交易/科目余额 数据驱动分析域 ──
            if contract_data:
                ct = len(contract_data); ct_amt = sum(float(x.get("amount",0)or 0) for x in contract_data)
                cfs = []
                if ct < 3 and (len(invoices) > 0 or len(bank_txs) > 0):
                    cfs.append({"type":"合同覆盖率严重不足","level":"高风险","score":9,
                        "detail":f"仅{ct}份合同。发票{len(invoices)}张/流水{len(bank_txs)}条但合同极少→四流不一",
                        "description":"合同是四流合一的基石，合同缺失意味着无法验证交易的真实性。",
                        "category":"合同风险","contract_driven":True})
                if ct > 0:
                    cfs.append({"type":"合同金额汇总","level":"低风险","score":2,
                        "detail":f"合同{ct}份，总金额{ct_amt:,.2f}元","category":"合同风险"})
                all_findings.extend(cfs)
                pipeline_log.append(f"合同分析: {ct}份, {len(cfs)}项发现")
            if related_party_data:
                rp = len(related_party_data); rp_amt = sum(float(x.get("amount",0)or 0) for x in related_party_data)
                rfs = [{"type":"关联交易存在性","level":"中风险","score":6,
                    "detail":f"{rp}笔关联交易，总金额{rp_amt:,.2f}元。需核实独立交易原则。",
                    "category":"关联风险","rp_driven":True}]
                all_findings.extend(rfs)
                pipeline_log.append(f"关联交易分析: {rp}笔, {len(rfs)}项发现")
            if trial_balance_data:
                tb = len(trial_balance_data)
                td = sum(float(x.get("close_debit",0)or 0) for x in trial_balance_data)
                tc = sum(float(x.get("close_credit",0)or 0) for x in trial_balance_data)
                tfs = [{"type":"科目余额表概况","level":"低风险","score":2,
                    "detail":f"科目{tb}条，借方{td:,.2f}/贷方{tc:,.2f}","category":"资产负债往来"}]
                diff = abs(td-tc)
                if diff > 0.01:
                    tfs.append({"type":"科目余额表借贷不平衡","level":"高风险","score":10,
                        "detail":f"借方{td:,.2f}/贷方{tc:,.2f}，差额{diff:,.2f}元","category":"资产负债往来"})
                all_findings.extend(tfs)
                pipeline_log.append(f"科目余额分析: {tb}条, {len(tfs)}项发现")
    except Exception as che:
        pipeline_log.append(f"链驱动引擎异常: {che}")
    # ═══════════════════════════════════════════════════

    high = sum(1 for f in all_findings if f.get("level") in ("高风险",) or "高" in str(f.get("risk_level", "")))
    mid = sum(1 for f in all_findings if f.get("level") in ("中风险",) or "中" in str(f.get("risk_level", "")))
    total = len(all_findings)

    stats = {"分析文件数": len(docs), "银行流水": len(bank_txs), "销项发票": len(sal_invs),
             "进项发票": len(pur_invs), "工资记录": len(salaries), "社保记录": len(social_security), "凭证记录": len(vouchers),
             "凭证主营收入": f"{voucher_revenue['total']:,.2f}元", "其中未开票": f"{voucher_revenue['uninvoiced']:,.2f}元"}

    domain_summary = []
    for dr in domain_results:
        dh = sum(1 for f in dr["findings"] if f.get("level") == "高风险")
        dm = sum(1 for f in dr["findings"] if f.get("level") == "中风险")
        if dr["findings"]:
            domain_summary.append({"name": dr["domain"], "count": len(dr["findings"]), "high": dh, "mid": dm, "findings": dr["findings"]})

    # 将域分析外的新发现（链驱动/合同/关联交易/科目余额等）补入domain_summary
    extra_by_cat = {}
    existing_types = set()
    for dr in domain_summary:
        for f in dr["findings"]:
            existing_types.add(f.get("type", ""))
    for f in all_findings:
        if f.get("chain_closure") and f["type"] not in existing_types:
            cat = "证据链闭环"
            if cat not in extra_by_cat: extra_by_cat[cat] = []
            extra_by_cat[cat].append(f)
            existing_types.add(f["type"])
        elif f.get("contract_driven") and f["type"] not in existing_types:
            cat = "合同风险分析"
            if cat not in extra_by_cat: extra_by_cat[cat] = []
            extra_by_cat[cat].append(f)
            existing_types.add(f["type"])
        elif f.get("rp_driven") and f["type"] not in existing_types:
            cat = "关联交易分析"
            if cat not in extra_by_cat: extra_by_cat[cat] = []
            extra_by_cat[cat].append(f)
            existing_types.add(f["type"])
        elif f.get("tb_driven") and f["type"] not in existing_types:
            cat = "科目余额分析"
            if cat not in extra_by_cat: extra_by_cat[cat] = []
            extra_by_cat[cat].append(f)
            existing_types.add(f["type"])
        elif f.get("chain_driven") and f["type"] not in existing_types:
            cat = "线索链驱动分析"
            if cat not in extra_by_cat: extra_by_cat[cat] = []
            extra_by_cat[cat].append(f)
            existing_types.add(f["type"])
    for cat, findings in extra_by_cat.items():
        dh = sum(1 for f in findings if f.get("level") == "高风险")
        dm = sum(1 for f in findings if f.get("level") == "中风险")
        domain_summary.append({"name": cat, "count": len(findings), "high": dh, "mid": dm, "findings": findings})

    # ── 综合报告增强数据：月度资金流 + 往来方TOP20 + 分级整改建议 ──
    # 1. 月度资金流（银行流水按月汇总收入/支出/净额）
    if bank_txs:
        from collections import defaultdict
        monthly = defaultdict(lambda: {"income": 0, "expense": 0, "tax": 0})
        import re as _dre2
        for tx in bank_txs:
            d = str(tx.get("transaction_date") or tx.get("date", ""))
            if not d: continue
            # 智能解析月份: 支持 YYYY-MM-DD / YYYY/MM/DD / YYYYMMDD / YYYY年MM月DD日
            m_match = _dre2.match(r'(\d{4})[-/年]?(\d{1,2})', d)
            if not m_match:
                m_match = _dre2.match(r'(\d{4})(\d{2})\d{2}', d)
            if m_match:
                m = f"{m_match.group(1)}-{int(m_match.group(2)):02d}"
            else:
                continue
            if m and len(m) == 7:
                debit = float(tx.get("debit", 0) or 0)
                credit = float(tx.get("credit", 0) or 0)
                summ = str(tx.get("summary", ""))
                if debit > 0:
                    if any(k in summ for k in ("税", "国税", "地税", "金库", "纳税")):
                        monthly[m]["tax"] += debit
                    else:
                        monthly[m]["expense"] += debit
                if credit > 0:
                    monthly[m]["income"] += credit
        
        months = sorted(monthly.keys())
        comprehensive["cashflow"] = {
            "months": months,
            "income": [round(monthly[m]["income"], 2) for m in months],
            "expense": [round(monthly[m]["expense"], 2) for m in months],
            "tax": [round(monthly[m]["tax"], 2) for m in months],
            "net": [round(monthly[m]["income"] - monthly[m]["expense"] - monthly[m]["tax"], 2) for m in months],
        }
    
    # 2. 往来方TOP20（收入和支出分列）
    if bank_txs:
        from collections import defaultdict as dd2
        receivers = dd2(float)
        payers = dd2(float)
        for tx in bank_txs:
            name = str(tx.get("counterparty_name") or tx.get("counterparty", "")).strip()
            if not name or name == "无" or len(name) < 2: continue
            credit = float(tx.get("credit", 0) or 0)
            debit = float(tx.get("debit", 0) or 0)
            if credit > 0: receivers[name] += credit
            if debit > 0: payers[name] += debit
        
        top_recv = sorted(receivers.items(), key=lambda x: -x[1])
        top_pay = sorted(payers.items(), key=lambda x: -x[1])
        comprehensive["top_receivers"] = [{"name": n, "amount": round(a, 2)} for n, a in top_recv]
        comprehensive["top_payers"] = [{"name": n, "amount": round(a, 2)} for n, a in top_pay]
    
    # 3. 分级整改建议（从 all_findings 提取高风险→P0，中风险→P1，低风险→P2）
    urgent = []
    important = []
    normal = []
    seen_suggestions = set()
    for f in sorted(all_findings, key=lambda x: -(x.get("score") or 0)):
        suggestion = str(f.get("suggestion", "")).strip()
        if not suggestion or suggestion in seen_suggestions: continue
        seen_suggestions.add(suggestion)
        item = {
            "type": f.get("type", ""),
            "suggestion": suggestion[:200],
            "score": f.get("score", 0),
            "level": f.get("level", ""),
        }
        if f.get("level") == "高风险":
            urgent.append(item)
        elif f.get("level") == "中风险":
            important.append(item)
        else:
            normal.append(item)
    
    comprehensive["actions"] = {
        "p0_urgent": urgent,
        "p1_important": important,
        "p2_normal": normal,
    }
    
    # 4. 数据概览 —— 纯动态生成，仅根据实际识别到的文件类型展示
    data_present = []
    data_missing = []  # 不再使用，保留兼容
    type_label_map = {
        "bank": "银行流水", "bank_statement": "银行流水", "bank_transaction": "银行流水",
        "sales_invoice": "销项发票", "purchase_invoice": "进项发票", "invoice": "发票",
        "salary": "工资表", "social_security": "社保明细", "voucher": "记账凭证",
        "inventory": "进销存台账", "contract": "合同文件",
        "housing_fund": "公积金缴存", "financial_statements": "财务报表",
        "tax_return": "纳税申报表", "vat_declaration": "增值税申报表",
        "income_tax_return": "企业所得税申报表",
        "customs_declaration": "海关报关单",
        "trial_balance": "科目余额表", "input_vat_deduction": "进项抵扣",
        "archive": "档案文件", "unknown": "未识别文件",
    }
    
    # 根据实际识别到的文件类型统计
    from collections import Counter
    type_counts = Counter(fr.get("type", "unknown") for fr in file_results if not fr.get("error"))
    seen_labels = set()
    for ftype, count in type_counts.items():
        label = type_label_map.get(ftype, ftype)
        if label not in seen_labels and count > 0:
            data_present.append(f"{label}({count}份)")
            seen_labels.add(label)
    # ── 资料缺失信息（从ctx中读取Phase 1的分析结果）──
    missing_doc_names = []
    _all_cat_names = {"bank": "银行流水", "sales_invoice": "销项发票", "purchase_invoice": "进项发票",
                      "voucher": "记账凭证", "salary": "工资表", "social_security": "社保明细",
                      "inventory": "进销存台账", "contract": "合同文件", "trial_balance": "科目余额表",
                      "financial": "资产负债表+利润表", "vat": "增值税申报表", "cit": "企业所得税申报表",
                      "ind_tax": "个人所得税申报表", "other_tax": "其他税种申报表"}
    for key in ctx.missing_doc_keys:
        missing_doc_names.append(_all_cat_names.get(key, key))
    comprehensive["data_overview"] = {"present": data_present, "missing": missing_doc_names}
    
    # ── 缺失后果→综合定性自动触发（叙事增强层）──
    # 任一资料缺失≥1 → 自动触发对应风险结论，注入all_findings
    if ctx.missing_doc_keys:
        triggered = _trigger_missing_consequences(all_findings, ctx.missing_doc_keys, ctx.industry_profile)
        if triggered:
            all_findings.extend(triggered)
            pipeline_log.append(f"[叙事增强层] 缺失后果自动触发: {len(triggered)}条风险结论已注入all_findings")
    # 同时构建前端展示数据
    missing_trigger_list = []
    for key in ctx.missing_doc_keys:
        t = MISSING_CONSEQUENCE_TRIGGER.get(key)
        if t:
            missing_trigger_list.append({
                "missing_doc": _all_cat_names.get(key, key),
                "missing_key": key,
                "risk": t["risk"],
                "level": t["level"],
                "priority": t["priority"],
                "consequence": t["consequence"],
                "law_ref": t["law"],
                "action": t["action"],
            })
    comprehensive["missing_consequence_triggers"] = missing_trigger_list
    if missing_trigger_list:
        pipeline_log.append(f"[叙事增强层] 缺失后果前端数据: {len(missing_trigger_list)}项")
    
    # ── 数据资产计数（供前端报告头部展示）──
    _actual_rule_count = 1512  # 默认值，稍后从rules_data动态更新
    comprehensive["rule_count"] = _actual_rule_count
    # chain_count / evidence_count 从上方 chain_execution 块获取（如果已执行），否则为0
    comprehensive["chain_count"] = comprehensive.get("chain_total_count", 0)
    comprehensive["evidence_count"] = len(comprehensive.get("evidence_closures", []))
    
    # ── 资料情报提取：从数据中自动提取关键审计信息 ──
    try:
        material_intel = _extract_material_intel(bank_txs, invoices, salaries, social_security, vouchers, inventory, input_vat_deductions)
    except Exception as _mie:
        pipeline_log.append(f"资料情报提取异常: {_mie}")
        material_intel = {}
    comprehensive["material_intel"] = material_intel
    pipeline_log.append(f"资料情报提取: 已完成{len(material_intel)}个模块的关键信息提取")

    # ── 金税四期式多因子风险评分引擎 ──
    try:
        risk_profile = _compute_risk_profile(all_findings, bank_txs, sal_invs, pur_invs, vouchers, salaries)
    except Exception as _rpe:
        pipeline_log.append(f"风险评分引擎异常: {_rpe}")
        risk_profile = {"composite_level": "低风险", "composite_score": 0}
    comprehensive["risk_profile"] = risk_profile

    # ═══ 回路1: EMA自学习 → 风险评分动态调权 ═══
    try:
        ema_data = getattr(ctx, '_ema_learning', None) or {}
        if ema_data.get("learning_status") == "mature" and ema_data.get("decayed_weights"):
            dw = ema_data["decayed_weights"]
            # 对每个finding应用EMA学习到的衰减权重
            for f in all_findings:
                ftype = f.get("type", "")
                if ftype in dw:
                    old_score = f.get("score", 5) or 5
                    # 衰减：风险权重下降 → 置信度降低 → 分数调低
                    decay = dw[ftype]
                    new_score = max(2, old_score * (1.0 - (decay - 1.0) * 0.5))
                    f["score"] = round(new_score, 1)
                    f["_ema_adjusted"] = True
                    f["_ema_decay"] = round(decay, 3)
                    f["_ema_score_before"] = old_score
            # 读取EMA行业基准阈值，注入行业偏离度
            thresholds = ema_data.get("ema_thresholds", {})
            if thresholds:
                risk_profile["_ema_thresholds_injected"] = list(thresholds.keys())
                pipeline_log.append(f"[EMA] 行业基准阈值已注入风险评估: {len(thresholds)}项")
            pipeline_log.append(f"[EMA] 学习权重已反馈风险评估: {len(dw)}条衰减权重")
    except Exception: pass

    # 综合风险等级：优先使用评分引擎结果
    overall = risk_profile.get("composite_level", "低风险")
    # 如果评分引擎算低风险但实际有多个高分数高风险发现+跨域证据链，
    # 则等级应上调为"中风险"——评分引擎只看数量，不看质量
    high_score_count = sum(1 for f in all_findings if f.get("level") == "高风险" and f.get("score", 0) >= 8)
    has_cross_chain = any("证据链" in str(f.get("type", "")) for f in all_findings)
    if overall == "低风险" and (high_score_count >= 3 or has_cross_chain):
        overall = "中风险"
    if overall == "中风险" and high >= 10:
        overall = "高风险"
    # 证据链闭环 → 强制升级风险等级
    closed_count = comprehensive.get("closed_chain_count", 0)
    if closed_count >= 3:
        overall = "高风险"  # 3条以上证据链闭环 → 直接高风险
        pipeline_log.append(f"风险升级: {closed_count}条证据链闭环→等级强制提升为高风险")
    elif closed_count >= 1 and overall == "低风险":
        overall = "中风险"  # 至少1条闭环 → 至少中风险
        pipeline_log.append(f"风险升级: {closed_count}条证据链闭环→等级提升为中风险")
    if overall == "未触发":
        overall = "高风险" if high >= 3 else ("中风险" if high + mid >= 5 else "低风险")

    # ── 匹配稽查证据链（精确版：规则ID直连）──
    triggered_chains = []
    chains_data = {}
    rules_data = []
    try:
        import re as _re_find
        chain_path = os.path.join(_PROJECT_ROOT, "static", "audit_chains.json")
        rules_path = os.path.join(_PROJECT_ROOT, "static", "tax_risk_rules_local_export.json")
        if os.path.exists(chain_path):
            with open(chain_path, "r", encoding="utf-8") as cf:
                raw = json.load(cf)
                chains_data = raw if isinstance(raw, dict) else {}
        if os.path.exists(rules_path):
            with open(rules_path, "r", encoding="utf-8") as rf:
                raw_r = json.load(rf)
                rules_data = raw_r if isinstance(raw_r, list) else []
        
        rule_map = {r["id"]: r for r in rules_data}
        
        for f in all_findings:
            f_type = str(f.get("type", ""))
            f_cat = str(f.get("category", "")).lower()
            f_detail = str(f.get("detail", ""))[:100]
            matched_ids = []
            type_kws = set(_re_find.findall(r'[\u4e00-\u9fff]{2,8}', f_type))
            detail_kws = set(_re_find.findall(r'[\u4e00-\u9fff]{2,8}', f_detail))
            all_kws = type_kws | detail_kws
            for r in rules_data:
                r_item = str(r.get("item", ""))
                r_cat = str(r.get("category", "")).lower()
                r_detail = str(r.get("detail", ""))[:100]
                # 词级匹配：2+字关键词命中rule的item或detail
                hits = sum(1 for kw in all_kws if kw in r_item or kw in r_detail)
                cat_match = f_cat and r_cat and (f_cat in r_cat or r_cat in f_cat)
                # 修复：要求3+词命中或2词命中+分类一致，杜绝字符级误匹配
                if hits >= 3 or (hits >= 2 and cat_match):
                    matched_ids.append(r["id"])
            f["matched_rule_ids"] = matched_ids  # 最多5条规则
            f["matched_rule_count"] = len(matched_ids)
        
        # 构建 rule_id → 证据链 反向索引 + 链详情缓存
        chain_map = {}  # chain_name → full chain data
        rule_to_chains = {}
        for chain in chains_data.get("chains", []):
            if not isinstance(chain, dict): continue
            cn = chain["name"]
            chain_map[cn] = chain
            for step in chain.get("investigation_path", []):
                if not isinstance(step, dict): continue
                rid = step.get("rule_id")
                if rid:
                    if rid not in rule_to_chains:
                        rule_to_chains[rid] = []
                    if cn not in rule_to_chains[rid]:
                        rule_to_chains[rid].append(cn)
        
        # 为每条finding匹配证据链（含详细步骤）
        for f in all_findings:
            chain_names = set()
            chain_details = []
            for rid in f.get("matched_rule_ids", []):
                if rid in rule_to_chains:
                    for cn in rule_to_chains[rid]:
                        chain_names.add(cn)
            f["matched_chain_ids"] = list(chain_names)
            f["matched_chain_count"] = len(chain_names)
            # 附带前3条链的调查步骤（线索链+证据链共用）
            for cn in list(chain_names):
                c = chain_map.get(cn, {})
                steps_summary = []
                for s in c.get("investigation_path", []):
                    if not isinstance(s, dict): continue
                    steps_summary.append({"step": s.get("step",""), "rule_id": s.get("rule_id"), "level": s.get("level","")})
                chain_details.append({"name": cn, "steps": c.get("steps",0), "high_risk": c.get("high_risk_steps",0), "steps_detail": steps_summary})
            f["matched_chain_details"] = chain_details
        
        # 汇总触发的证据链（去重+排序）
        chain_hit_count = {}
        for f in all_findings:
            for cn in f.get("matched_chain_ids", []):
                chain_hit_count[cn] = chain_hit_count.get(cn, 0) + 1
        
        # 按命中次数排序，取top30
        sorted_chains = sorted(chain_hit_count.items(), key=lambda x: -x[1])
        for cn, hits in sorted_chains:
            # 找到链详情
            for chain in chains_data.get("chains", []):
                if not isinstance(chain, dict): continue
                if chain.get("name") == cn:
                    triggered_chains.append({
                        "name": cn, "hits": hits,
                        "steps": chain["steps"],
                        "high_risk": chain["high_risk_steps"],
                        "policies": chain.get("policies", []),
                        "tax_impacts": chain.get("tax_impacts", []),
                    })
                    break
        
        # ── 动态链触发：推荐下一步调查 ──
        triggered_rule_ids = set()
        for f in all_findings:
            mrids = f.get("matched_rule_ids", [])
            if isinstance(mrids, list):
                for rid in mrids:
                    triggered_rule_ids.add(rid)
        recommended_next = []
        for chain in chains_data.get("chains", []):
            if not isinstance(chain, dict): continue
            trig = []; notrig = []
            for step in chain.get("investigation_path", []):
                if not isinstance(step, dict): continue
                if step.get("rule_id") in triggered_rule_ids:
                    trig.append(step)
                else:
                    notrig.append(step)
            if trig and notrig and len(trig) >= 1:
                recommended_next.append({
                    "chain_name": chain["name"],
                    "chain_type": chain.get("chain_type", "证据链"),
                    "triggered": len(trig), "remaining": len(notrig),
                    "next_steps": [{"step": s["step"], "rule_id": s.get("rule_id"), "rule_item": s.get("rule_item","")[:40], "level": s.get("level","")} for s in notrig]
                })
        recommended_next.sort(key=lambda x: -(x["remaining"] + x["triggered"]))
        comprehensive["recommended_next"] = recommended_next
        
        # ── 链使用统计（持久化） ──
        chain_usage = {}
        for c in chains_data.get("chains", []):
            if not isinstance(c, dict):
                continue
            hits = sum(1 for s in c.get("investigation_path", []) if isinstance(s, dict) and s.get("rule_id") in triggered_rule_ids)
            if hits > 0:
                chain_usage[c["name"]] = {"hits": hits, "steps": c.get("steps", 0), "type": c.get("chain_type", "?")}
        try:
            for c in chains_data.get("chains", []):
                if not isinstance(c, dict):
                    continue
                uc = chain_usage.get(c["name"], {})
                if uc.get("hits", 0) > 0:
                    c["usage_count"] = c.get("usage_count", 0) + 1
                    c["last_triggered"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(chain_path, "w", encoding="utf-8") as cf2:
                json.dump(chains_data, cf2, ensure_ascii=False, indent=2)
        except: pass
        comprehensive["chain_usage"] = dict(sorted(chain_usage.items(), key=lambda x: -x[1]["hits"]))
        
        if triggered_chains:
            pipeline_log.append(f"证据链匹配: {len(triggered_chains)}条触发（规则ID直连）")
        if rules_data:
            pipeline_log.append(f"规则匹配: {len(rules_data)}条规则可追溯")
    except Exception as ce:
        pipeline_log.append(f"证据链匹配异常: {ce}")
    
    comprehensive["triggered_chains"] = triggered_chains

    # 动态读取实际规则数量
    _actual_rule_count = 1512
    try:
        if rules_data:
            _actual_rule_count = len(rules_data)
    except:
        pass
    comprehensive["rule_count"] = _actual_rule_count  # 用动态值覆盖可能存在的默认值

    # ═══ 确定分析对象 ═══
    target_entity = _detect_target_entity(bank_txs, invoices, salaries, db, company_id)
    
    # ═══ 经营实质信号检测（pur_invs/sal_invs 经 Phase1 方向校正后可用） ═══
    if pur_invs and sal_invs:
        def _get_goods(inv):
            return str(inv.get("goods", "") or inv.get("goods_name", "") or "")
        
        # 经营费用关键词——这些是日常运营支出，不是生产物资，不应混入原材料分析
        _EXPENSE_KWS = ["住宿", "餐饮", "餐费", "房费", "汽油", "柴油", "加油",
                        "旅游", "差旅", "租赁", "保险", "通讯", "电话", "办公",
                        "快递", "广告", "咨询", "法律", "维修", "物业", "停车",
                        "经纪代理", "代订"]
        def _is_expense(goods_name):
            return any(kw in goods_name for kw in _EXPENSE_KWS)
        
        # 加工费信号——从全部进项中检测（已修复：排除分类码*X加工品*误判）
        import re as _re_proc3
        has_processing_fee = False
        for i in pur_invs:
            g = _get_goods(i)
            if '加工费' in g:
                has_processing_fee = True; break
            if '加工' in g and not _re_proc3.search(r'\*[\u4e00-\u9fa5]+加工[品物食料]\*', g):
                has_processing_fee = True; break
        
        # 品名分析——仅分析生产物资，排除经营费用
        pur_production = set()
        sal_goods = set()
        for i in pur_invs:
            g = _get_goods(i).strip()
            if g and not _is_expense(g):
                pur_production.add(g)
        for i in sal_invs:
            g = _get_goods(i).strip()
            if g: sal_goods.add(g)
        common_goods = sorted(pur_production & sal_goods)
        pur_only = sorted(pur_production - sal_goods)
        sal_only = sorted(sal_goods - pur_production)
        # ── 综合加工信号检测：多维度评分 ──
        # 不是"有品名差异→触发"，而是收集多个独立信号综合判断
        # 信号1: 加工费发票（最强国税证据）
        # 信号2: 进销品名实质性差异
        # 信号3: 同品名规格变化（瓷板800×800→300×300，品名不变但加工了）
        # 信号4: 同品名数量膨胀（进1块大板→卖4块小板，可能切割加工）
        # 信号5: 行业属性加成（制造业→加权，纯服务业→降权）
        detected_ind = target_entity.get("industry", "")
        has_pur_sal_diff = bool(pur_only) and bool(sal_only)
        
        # ═══ 信号3: 同品名规格差异 ═══
        # 例：进"瓷砖800×800"→销"瓷砖300×300"，品名相同但实质在加工
        spec_diff_goods = []
        if common_goods:
            def _get_spec(inv):
                s = str(inv.get("spec", "") or inv.get("规格", "") or inv.get("specification", "") or "").strip()
                return s.replace(" ", "").replace("　", "").lower()  # 归一化空格
            for g in common_goods:
                pur_specs = set()
                sal_specs = set()
                for i in pur_invs:
                    if _get_goods(i).strip() == g:
                        s = _get_spec(i)
                        if s: pur_specs.add(s)
                for i in sal_invs:
                    if _get_goods(i).strip() == g:
                        s = _get_spec(i)
                        if s: sal_specs.add(s)
                if pur_specs and sal_specs and pur_specs != sal_specs:
                    spec_diff_goods.append({"goods": g, "pur_specs": sorted(pur_specs), "sal_specs": sorted(sal_specs)})
        
        # ═══ 信号4: 同品名数量膨胀 ═══
        # 进1块→卖4块，说明经过切割/分装，存在加工
        qty_inflation_goods = []
        if common_goods:
            def _get_qty(inv):
                try:
                    return float(inv.get("qty", 0) or inv.get("quantity", 0) or inv.get("数量", 0) or 0)
                except:
                    return 0.0
            for g in common_goods:
                pur_qty = sum(_get_qty(i) for i in pur_invs if _get_goods(i).strip() == g)
                sal_qty = sum(_get_qty(i) for i in sal_invs if _get_goods(i).strip() == g)
                if pur_qty > 0 and sal_qty > pur_qty * 1.15:
                    qty_inflation_goods.append({"goods": g, "pur_qty": round(pur_qty, 2), "sal_qty": round(sal_qty, 2), "ratio": round(sal_qty / pur_qty, 2)})
        
        # ═══ 综合评分 ═══
        processing_score, processing_signals = _compute_processing_score(
            detected_ind, has_processing_fee, has_pur_sal_diff,
            len(spec_diff_goods) > 0, len(qty_inflation_goods) > 0
        )
        # >=0.40 高置信度触发 | >=0.20 低置信度触发 | <0.20 不触发
        processing_applicable = processing_score >= 0.20
        
        target_entity["_has_processing_signal"] = processing_applicable
        target_entity["_goods_analysis"] = {
            "common_goods": common_goods, "pur_only_goods": pur_only,
            "sal_only_goods": sal_only, "has_processing_fee": has_processing_fee,
            "has_goods_mismatch": has_pur_sal_diff,
            "spec_diff_goods": spec_diff_goods,
            "qty_inflation_goods": qty_inflation_goods,
            "_processing_score": processing_score,
            "_processing_signals": processing_signals,
            "_processing_confidence": "high" if processing_score >= 0.40 else ("low" if processing_applicable else "none"),
            "_processing_applicable": processing_applicable,
        }
        pipeline_log.append(f"加工信号评分: {processing_score:.2f}, signals={processing_signals}, applicable={processing_applicable}")
    else:
        target_entity["_has_processing_signal"] = False
        target_entity["_goods_analysis"] = {}
    # ═══ 稽查方法论⑥ 联网核查 ═══
    if target_entity.get("name"):
        try:
            target_entity = _enrich_target_entity_from_online(target_entity, db, company_id)
            if target_entity.get("_online_lookup"):
                pipeline_log.append(f"联网核查: {target_entity['name']} — 来源: {target_entity.get('lookup_source', '未知')}")
                if target_entity.get("_company_status_warning"):
                    pipeline_log.append(f"  ⚠️ {target_entity['_company_status_warning']}")
        except Exception as _ol_err:
            pipeline_log.append(f"联网核查失败: {_ol_err}（继续流程）")
    
    # ═══ 行业修正：联网核查返回经营范围后，验证发票推断行业是否合理 ═══
    # 问题：只看销项发票品名推断行业→卖了纺织品就被判"纺织制造"
    #       但实际上可能是综合贸易商，经营范围涵盖多种品类
    # 修正：经营范围包含≥3个不同品类→判定为贸易/批发而非制造
    if target_entity.get("_online_lookup") and target_entity.get("industry"):
        biz_scope = target_entity.get("biz_scope", "") or target_entity.get("business_scope", "")
        if biz_scope:
            # 统计经营范围中的品类多样性
            _TRADE_CATEGORY_KW = ["销售", "零售", "批发", "贸易", "进出口", "日用百货",
                                  "五金", "化妆品", "食品", "服装", "鞋帽", "箱包", "家具",
                                  "电器", "电子", "办公", "体育", "玩具", "礼品", "饰品"]
            category_hits = sum(1 for kw in _TRADE_CATEGORY_KW if kw in biz_scope)
            # 经营范围含多种销售品类 + 发票推断为制造 → 实际应为贸易
            inferred_ind = target_entity.get("industry", "")
            _MANUFACTURING_ONLY = ["制造", "纺织", "服装", "化工", "电子制造", "机械制造"]
            is_mfg_inferred = any(kw in inferred_ind for kw in _MANUFACTURING_ONLY)
            if category_hits >= 3 and is_mfg_inferred:
                corrected = "综合贸易/批发"
                pipeline_log.append(f"行业修正: 发票推断={inferred_ind}, 经营范围含{category_hits}个贸易品类→修正为{corrected}")
                target_entity["industry"] = corrected
                target_entity["_industry_corrected"] = True
    try:
        analysis_memory = _load_analysis_memory(company_id, pipeline_log)
        comprehensive["analysis_memory"] = analysis_memory
        if analysis_memory.get("cross_company"):
            pipeline_log.append(f"[分析记忆] 发现{len(analysis_memory['cross_company'])}个跨公司泛化模式")
    except Exception as _amle:
        pipeline_log.append(f"[分析记忆] 加载异常: {_amle}")
    
    # ═══ 稽查方法论③ 付款方身份核实：联网获取法人/股东信息后，补充匹配 ═══
    if target_entity.get("_online_lookup") and bank_txs:
        try:
            payer_id_check = _domain_fund_flow_mapping(bank_txs, sal_invs, pur_invs, target_entity)
            for pf in payer_id_check:
                if "个人付款方身份核实" in pf.get("type", ""):
                    all_findings.append(pf)
                    pipeline_log.append(f"付款方身份核实: 个人付款方已与法定代表人/股东名单比对")
        except Exception as _pi_err:
            pipeline_log.append(f"付款方身份核实失败: {_pi_err}")
    
    # ═══ 稽查方法论㉗ 供应链联网核查：供应商/客户联网查询 + 六员交叉比对 ═══
    if target_entity.get("_online_lookup") and (sal_invs or pur_invs):
        try:
            from collections import defaultdict
            supply_chain_risk = _lookup_supply_chain(db, company_id, target_entity, sal_invs, pur_invs)
            sc_findings = supply_chain_risk.get("findings", [])
            if sc_findings:
                all_findings.extend(sc_findings)
                sc_results = len(supply_chain_risk.get("lookup_results", []))
                pipeline_log.append(f"供应链联网核查: {sc_results}家供应商/客户已查询, {len(sc_findings)}项风险发现")
                # 注入到target_entity供前端渲染
                target_entity["_supply_chain_risk"] = supply_chain_risk
        except Exception as _sc_err:
            pipeline_log.append(f"供应链联网核查失败: {_sc_err}")
    
    # ═══ 稽查方法论㉕补充：经营实质核查发现（工商登记vs发票推断） ═══
    biz_sub_findings = _generate_biz_substance_findings(target_entity, pur_invs, sal_invs)
    if biz_sub_findings:
        all_findings.extend(biz_sub_findings)
        pipeline_log.append(f"经营实质核查: {len(biz_sub_findings)}项发现（五步核查法：工商登记→进项审核→销项审核→交叉比对→综合判断）")
    
    # ═══ 稽查重点等级修正（必须在过滤器之前）：level_fixed标记保护关键发现不被误杀 ═══
    priority_fixed = 0
    for f in all_findings:
        ftype = f.get("type", "")
        for key, level in AUDIT_PRIORITY_LEVELS.items():
            if key in ftype:
                if f.get("level") != level:
                    f["level"] = level
                    priority_fixed += 1
                f["level_fixed"] = True
                break
    if priority_fixed:
        pipeline_log.append(f"稽查重点等级修正: {priority_fixed}条按审计实务优先级强制定级")

    # ═══ 服务行业后处理：剔除不适用服务行业的进销存/BOM/进销比发现 ═══
    # WHY: 服务行业(广告/IT/咨询等)天然无实物货物流转，进销存台账/BOM表/进销比等基于实物商品的指标不适用
    # 在 all_findings 合并后统一过滤，确保域分析/管道/跨域结论中的进销存误报全部清除
    try:
        import re, json as _json2
        _ind_path2 = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "industry_data.json")
        with open(_ind_path2, 'r', encoding='utf-8') as _f2:
            _svc_codes = _json2.loads(_f2.read()).get("service_industries", {}).get("codes", [])
    except Exception:
        _svc_codes = ["广告服务","信息技术服务","研发和技术服务","文化创意服务",
            "物流辅助服务","鉴证咨询服务","广播影视服务","商务辅助服务",
            "金融服务","现代服务","生活服务","电信服务","建筑服务",
            "教育服务","医疗服务","旅游服务","娱乐服务","餐饮服务",
            "居民日常服务","其他现代服务","经纪代理服务","人力资源服务",
            "安全保护服务","会议展览服务","租赁服务","无形资产"]
    _svc_sal = 0; _total_sal = 0
    for inv in sal_invs:
        g = str(inv.get("goods", inv.get("货物或应税劳务名称", "")))
        m = re.search(r'\*([^*]+)\*', g)
        if m:
            _total_sal += 1
            if any(s in m.group(1) for s in _svc_codes):
                _svc_sal += 1
    _is_svc_final = _total_sal > 0 and _svc_sal / _total_sal >= 0.5
    
    if _is_svc_final:
        # 需剔除的发现类型（关键词匹配）
        _svc_exclude_patterns = [
            "进销比","进销存","有进无销","有销无进","品名不匹配","品名差异",
            "BOM表","物料清单","进销品名","购销商品种不匹配","购销售商品种",
            "加工费掩盖","缺少BOM","商品种不匹配","加工链条","存货积压",
            "库存周转","进销异常","购销严重倒挂","原材料.*成品","原料.*加工",
        ]
        _filtered_out = 0
        _new_findings = []
        for f in all_findings:
            ftype = f.get("type", "")
            if any(re.search(pat, ftype) for pat in _svc_exclude_patterns):
                _filtered_out += 1
                continue
            # 也过滤detail中含有"BOM表"但type不匹配的
            fdetail = f.get("detail", "")
            if "BOM表" in fdetail and "进销" in fdetail:
                _filtered_out += 1
                continue
            _new_findings.append(f)
        all_findings = _new_findings
        if _filtered_out:
            pipeline_log.append(f"[服务行业过滤] 剔除{_filtered_out}条不适用服务行业的进销存/BOM相关发现（销项服务类占比{_svc_sal/_total_sal*100:.0f}%）")
    
    # ═══ 方法论过滤：剔除不具备数据支撑的噪声发现 ═══
    # target_industry 传入（来自_detect_target_entity()的加权投票结果），全行业适用
    _target_industry = target_entity.get("industry", "")
    all_findings, pipeline_log, filter_log = _apply_methodology_filter(
        all_findings, pipeline_log,
        bank_txs, invoices, salaries, social_security, vouchers, inventory, docs,
        target_industry=_target_industry)
    comprehensive["filter_log"] = filter_log  # 方法论过滤详情
    
    # ── 重建domain_summary（过滤后数据，确保count与all_findings一致）──
    for dr in domain_summary:
        filtered_findings = [f for f in dr.get("findings", []) 
                           if any(af.get("type") == f.get("type") and af.get("detail") == f.get("detail") 
                                  for af in all_findings)]
        dr["findings"] = filtered_findings
        dr["count"] = len(filtered_findings)
        dr["high"] = sum(1 for f in filtered_findings if f.get("level") == "高风险")
        dr["mid"] = sum(1 for f in filtered_findings if f.get("level") == "中风险")
    # 移除空域
    domain_summary[:] = [dr for dr in domain_summary if dr["count"] > 0]
    
    # ═══ 重算风险统计（过滤后）═══
    # 确保进销存匹配核心发现不丢失（有进无销/有销无进/进销数量偏差）
    for imf in inv_match_findings:
        if imf.get("score", 0) >= 5:  # 放宽到5（制造业诊断后score可低至5）
            exists = any(f.get("type") == imf.get("type") for f in all_findings)
            if not exists:
                # 稽查重点修正
                for key, level in AUDIT_PRIORITY_LEVELS.items():
                    if key in imf.get("type", ""):
                        imf["level"] = level
                        imf["level_fixed"] = True
                        break
                all_findings.append(imf)
    
    # ═══ 明细注入：为每条发现附加结构化明细数据 ═══
    all_findings = _enrich_finding_details(all_findings, bank_txs, invoices, salaries, docs)
    
    # ═══ 证据溯源：为每条发现附加原始数据行级引用（可点击溯源） ═══
    all_findings = _enrich_evidence_rows(all_findings, bank_txs, invoices, salaries, vouchers)
    
    # ═══ 信号类型标注：为每条发现打上结构化信号标签（驱动因果推理） ═══
    all_findings = _enrich_signal_types(all_findings)
    
    # ═══ 因果叙事链：信号叠加→因果推理（结构化匹配，>=1触发） ═══
    causal_narratives = _build_causal_narratives(all_findings)
    if causal_narratives:
        all_findings.extend(causal_narratives)
        pipeline_log.append(f"因果叙事链: {len(causal_narratives)}条因果推理链触发")
    
    # ═══ 证伪思维：对每条高风险结论生成反向假设并尝试证伪 ═══
    all_findings, falsification_log = _falsification_check(all_findings)
    pipeline_log.append(falsification_log)
    
    # ═══ 增强证伪：30+规则 + 多维Benford ═══
    all_findings, enhanced_fals_log = _enhanced_falsification_check(all_findings)
    pipeline_log.append(enhanced_fals_log)
    
    # ═══ 贝叶斯因果网络：条件概率 + 自动发现因果边 + 信念传播 ═══
    all_findings, bayesian_result = _bayesian_causal_network(all_findings)
    ctx._bayesian = bayesian_result
    if bayesian_result.get("edges", 0) > 0:
        pipeline_log.append(f"贝叶斯因果: {bayesian_result['edges']}条因果边/{bayesian_result.get('propagated',0)}条信念传播")
    
    # ═══ EMA自学习：指数移动平均阈值 + 权重衰减 ═══
    ema_result = _ema_self_learning(ctx, all_findings)
    ctx._ema_learning = ema_result
    pipeline_log.append(f"EMA自学习: {ema_result['learning_status']}({ema_result['industry_sample_size']}样本)")
    
    # ═══ 推断可解释性：决策路径+替代假设 ═══
    all_findings = _enrich_reasoning_path(all_findings)
    
    # ═══ Provenance 溯源链注入：每个 finding 记录"怎么来的" → 支撑矛盾检测回溯 ═══
    all_findings = _inject_provenance(all_findings)
    pipeline_log.append(f"[Provenance] 溯源链注入完成: {len(all_findings)}条finding")
    
    # ═══ 经验直觉：历史反馈学习+信号共现模式 ═══
    intuition_findings = _compute_intuition_patterns(ctx, all_findings)
    if intuition_findings:
        all_findings.extend(intuition_findings)
        pipeline_log.append(f"经验直觉: {len(intuition_findings)}条直觉警报")
    
    # ═══ 多假设并行推理 ═══
    multi_hypo_findings = _multi_hypothesis_check(ctx, all_findings, bank_txs, invoices)
    if multi_hypo_findings:
        all_findings.extend(multi_hypo_findings)
        pipeline_log.append(f"多假设推理: {len(multi_hypo_findings)}组竞争假设")
    
    # ═══ 跨期对比记忆 ═══
    cross_period_findings = _cross_period_compare(ctx, company_id, db)
    if cross_period_findings:
        all_findings.extend(cross_period_findings)
        pipeline_log.append(f"跨期对比: {len(cross_period_findings)}条趋势发现")
    
    # ═══ 知识图谱 ═══
    entity_findings, graph_summary = _build_entity_graph(bank_txs, invoices, salaries)
    if entity_findings:
        all_findings.extend(entity_findings)
        ctx._entity_graph = graph_summary
        pipeline_log.append(f"知识图谱: {graph_summary['total_entities']}个实体/{graph_summary['total_anomalies']}个异常关系")
    
    # ═══ 经营实质深挖：水电费/运输费/人工vs产能匹配 ═══
    biz_sub_findings = _deep_biz_substance_check(ctx, bank_txs, invoices, salaries)
    if biz_sub_findings:
        all_findings.extend(biz_sub_findings)
        pipeline_log.append(f"经营实质深挖: {len(biz_sub_findings)}项要素匹配异常")
    
    # ═══ 对抗鲁棒性：本福特定律+重复金额检测 ═══
    adv_findings = _adversarial_robustness_check(all_findings, invoices, bank_txs)
    if adv_findings:
        all_findings.extend(adv_findings)
        pipeline_log.append(f"对抗鲁棒性: {len(adv_findings)}项数据编造痕迹")
    
    # ═══ 多维Benford检验（首位+第二位+末位） ═══
    benford_result = _multi_dim_benford_check(invoices, bank_txs)
    ctx._benford = benford_result
    if benford_result.get("flags"):
        pipeline_log.append(f"Benford检验: {len(benford_result['flags'])}项异常")
    
    # ═══ 自动规则发现 ═══
    rule_discovery = _auto_rule_discovery(all_findings)
    ctx._discovered_rules = rule_discovery
    if rule_discovery.get("discovered_rules"):
        pipeline_log.append(f"自动规则发现: {len(rule_discovery['discovered_rules'])}条新信号组合模式")
    
    # ═══ 审计策略推荐 ═══
    audit_strategies = _audit_strategy_recommend(ctx, all_findings)
    ctx._audit_strategies = audit_strategies
    pipeline_log.append(f"审计策略: {audit_strategies['total']}条推荐策略({audit_strategies['p0_count']}条P0)")
    
    # ═══ 多模态支持检测 ═══
    multimodal_status = _multimodal_support_check(docs, file_results)
    ctx._multimodal = multimodal_status
    
    # ═══ 稽查方法论㉓ 四步稽查分析法：detect→verify→diagnose→report 统一框架 ═══
    try:
        all_findings = _four_step_audit_framework(all_findings, bank_txs, invoices, target_entity)
        pipeline_log.append(f"四步稽查分析法: detect→verify→diagnose→report 框架已应用于核心发现")
    except Exception as _fs_err:
        pipeline_log.append(f"四步稽查分析法执行异常: {_fs_err}")
    
    # ═══ 建议质量增强：确保每个风险点/面都有具体可操作的消除路径 ═══
    # 铁律：建议必须基于已分析出的数据，不得推给审计师做本该系统完成的分析工作
    enhanced = 0
    for f in all_findings:
        sug = (f.get("suggestion", "") or "").strip()

        ftype = f.get("type", "")
        
        # 检测敷衍建议：太短、或纯话术模板
        _BOILERPLATE_PREFIXES = ("立即整改", "按实际", "逐项核查", "逐项核实", "逐项检查",
                                 "逐笔核查", "逐笔核实", "逐笔核对", "逐笔检查")
        is_boilerplate = (len(sug) < 30 or any(sug.startswith(p) for p in _BOILERPLATE_PREFIXES))
        
        if is_boilerplate or sug == "":
            # ── 有明细数据的发现：直接报告分析结果 ──
            items = f.get("items") or []
            detail = f.get("detail", "")
            
            if "收款与开票" in ftype:
                if items and len(items) >= 3:
                    pass  # 已有逐票匹配明细，保留
                elif "银行入账" in detail and "销项开票" in detail:
                    # 数据已在 detail 中，补充具体行动路径
                    f["suggestion"] = (
                        "银行入账金额与销项开票金额的差额可能由以下原因造成，请逐项排除："
                        "① 非经营性收款（借款、注资、往来款）——核实银行流水备注/合同；"
                        "② 未开票收入——核对出库单/合同/收货确认单，确认后申报未开票收入；"
                        "③ 第三方代付——取得委托付款证明。"
                        "无法说明来源的差额部分，按隐匿收入处理。"
                    )
                    enhanced += 1
                else:
                    f["suggestion"] = (
                        "银行收款与销项开票存在偏差。可能原因：未开票收入/非经营性收款/第三方代付。"
                        "需结合收款来源分析逐项排除。无法说明来源的差额按隐匿收入处理。"
                    )
                    enhanced += 1
                    
            elif "供应商" in ftype and ("异地" in ftype or "集中" in ftype or "空壳" in ftype):
                # 供应商类发现——给出具体核实路径而非泛泛而谈
                f["suggestion"] = (
                    "对同城集中供应商执行以下核查步骤："
                    "① 逐户在天眼查/企查查核实工商状态（存续/注销/吊销）；"
                    "② 比对供应商注册地址是否为住宅/虚拟地址；"
                    "③ 核对银行付款记录——无付款的进项发票进项税额应予转出；"
                    "④ 核查物流单据——无运输凭证的跨省采购无法证实货物真实流转。"
                    "上述核查完成后，对无法证实真实性的进项发票主动做进项税额转出。"
                )
                enhanced += 1
                
            elif items and len(items) >= 2:
                # 有明细数据：直接给出结论
                sample_items = items[:3]
                item_desc = "；".join(
                    f"{it.get('payee','') or it.get('counterparty','') or it.get('name','')}"
                    f"({it.get('amount','') or it.get('count','')})"
                    for it in sample_items
                )
                f["suggestion"] = (
                    f"已识别{len(items)}条关联记录（如：{item_desc}）。"
                    f"请逐项核实业务真实性并提供对应合同/单据/凭证。"
                )
                enhanced += 1
                
            else:
                # 无明细数据的兜底——至少给出具体方向而非空话
                f["suggestion"] = (
                    f"请提供与「{ftype[:40]}」相关的合同、单据、凭证等业务佐证材料。"
                )
                enhanced += 1
    
    if enhanced:
        pipeline_log.append(f"建议质量增强: {enhanced}条发现补充了具体可操作的消除路径")
    
    # ═══ 稽查重点等级修正：现实中不根据score定级，根据审计实务优先级 ═══
    priority_fixed = 0
    for f in all_findings:
        ftype = f.get("type", "")
        for key, level in AUDIT_PRIORITY_LEVELS.items():
            if key in ftype:  # 模糊匹配——发现类型可能带长后缀
                if f.get("level") != level:
                    f["level"] = level
                    priority_fixed += 1
                f["level_fixed"] = True  # 稽查重点标记
                break
    if priority_fixed:
        pipeline_log.append(f"稽查重点等级修正: {priority_fixed}条发现按审计实务优先级调整等级")
    
    high = sum(1 for f in all_findings if f.get("level") in ("高风险",) or "高" in str(f.get("risk_level", "")))
    mid = sum(1 for f in all_findings if f.get("level") in ("中风险",) or "中" in str(f.get("risk_level", "")))
    total = len(all_findings)
    
    # ═══ 文本净化：剔除模板句/重复句/空描述（必须在质量标准之前）═══
    all_findings, sanitize_log = _sanitize_finding_boilerplate(all_findings)
    pipeline_log.append(sanitize_log)
    
    # ═══ 稽查报告质量标准执行（12项硬指标）═══
    all_findings, quality_report = _enforce_report_quality_standards(all_findings, pipeline_log)
    
    # ═══ 报告净化：剔除内部技术描述和敷衍文本，只保留审计师可读的专业发现 ═══
    _INTERNAL_PATTERNS = [
        "数据验证通过", "数据验证:",
        "链驱动分析", "线索链-行业-", "查证方式-",
        "证据来源：", "规则R", "命中",
    ]
    _BOILERPLATE_LEGAL = "《中华人民共和国税收征收管理法》及相关税收法规。具体条文由审理环节根据违法事实最终认定。"
    _BOILERPLATE_LEGAL_SHORT = "《中华人民共和国税收征收管理法》及相关税收法规。"
    
    for f in all_findings:
        # 1. 清理 how_found —— 内部技术描述
        hf = f.get("how_found", "")
        if hf and any(p in hf for p in _INTERNAL_PATTERNS):
            # 尝试提取有意义的查证路径，剔除纯技术噪声
            cleaned = hf
            for p in _INTERNAL_PATTERNS:
                cleaned = cleaned.replace(p, "")
            cleaned = cleaned.strip().lstrip("：:→|").strip()
            if cleaned and len(cleaned) > 10:
                f["how_found"] = cleaned
            else:
                del f["how_found"]
        
        # 2. 清理 detail / description 中的内部元数据
        for field in ("detail", "description"):
            val = f.get(field, "")
            if val and any(p in val for p in _INTERNAL_PATTERNS):
                cleaned = val
                for p in _INTERNAL_PATTERNS:
                    cleaned = cleaned.replace(p, "")
                # 去掉残留的竖线、箭头等符号
                import re as _re2
                cleaned = _re2.sub(r'\s*[|→]+\s*', '；', cleaned)
                cleaned = _re2.sub(r'；{2,}', '；', cleaned)
                f[field] = cleaned.strip().rstrip("；。").strip()
        
        # 3. 清理法律依据中的敷衍文本
        pf = f.get("policy_ref", "")
        if not isinstance(pf, str):
            pf = str(pf) if pf is not None else ""
        if pf == _BOILERPLATE_LEGAL or pf == _BOILERPLATE_LEGAL_SHORT:
            del f["policy_ref"]
        elif pf and _BOILERPLATE_LEGAL_SHORT in pf:
            # 混合了具体条文+敷衍文本的情况，只保留具体条文
            cleaned = pf.replace(_BOILERPLATE_LEGAL, "").replace(_BOILERPLATE_LEGAL_SHORT, "")
            cleaned = cleaned.strip().rstrip("；。;").strip()
            if cleaned:
                f["policy_ref"] = cleaned
            else:
                del f["policy_ref"]
    
    # ── 提取推理引擎完整状态（供独立展示模块使用）──
    engine_status = {}
    try:
        cp = ctx.company_profile
        fs = ctx.financial_snapshot
        bcc = ctx.biz_cost_classification or {}
        
        biz_cost_summary = {
            "core_cost_count": len(bcc.get("core_cost_invs", [])),
            "core_cost_amount": sum(float(inv.get("amount", 0) or 0) for inv in bcc.get("core_cost_invs", [])),
            "major_expense_count": len(bcc.get("major_expense_invs", [])),
            "minor_expense_count": len(bcc.get("minor_expense_invs", [])),
            "core_goods": list(bcc.get("pur_core_goods", []))[:20],
            "expense_goods": list(bcc.get("pur_expense_goods", []))[:20],
        }

        try:
            _domains = list(phase2_domains_covered) if 'phase2_domains_covered' in locals() else []
        except:
            _domains = []
        try:
            _depths = dict(depth_levels) if 'depth_levels' in locals() else {}
        except:
            _depths = {}

        try:
            _synth = synthesis
        except:
            _synth = {}

        engine_status = {
            "version": "v2.0",
            "phases": ["Phase1-初查", "Phase2-定向深挖", "Phase3-交叉验证", "Phase4-综合定性"],
            "company_profile": {
                "industry": cp.get("industry", "未知"),
                "biz_model": cp.get("biz_model", "未知"),
                "scale": cp.get("scale", "未知"),
                "has_manufacturing": cp.get("has_manufacturing", False),
                "has_trading": cp.get("has_trading", False),
            },
            "financial_snapshot": {
                "total_sales": fs.get("total_sales", 0),
                "total_purchases": fs.get("total_purchases", 0),
                "total_bank_in": fs.get("total_bank_in", 0),
                "total_bank_out": fs.get("total_bank_out", 0),
                "total_salary": fs.get("total_salary", 0),
                "gross_margin_pct": round(fs.get("gross_margin_pct", 0), 1),
                "sale_count": fs.get("sale_count", 0),
                "pur_count": fs.get("pur_count", 0),
                "bank_tx_count": fs.get("bank_tx_count", 0),
                "salary_count": fs.get("salary_count", 0),
            },
            "biz_cost_classification": biz_cost_summary,
            "red_flags": ctx.red_flags,
            "yellow_flags": ctx.yellow_flags,
            "green_signals": ctx.green_signals,
            "bom_missing": ctx.bom_missing,
            "has_processing_fee": ctx.has_processing_fee,
            "has_personal_payments": ctx.has_personal_payments,
            "supplier_concentration": ctx.supplier_concentration,
            "customer_concentration": ctx.customer_concentration,
            "data_quality_score": ctx.data_quality_score,
            "missing_critical_docs": ctx.missing_critical_docs,
            "missing_doc_keys": ctx.missing_doc_keys,
            "phase2_domains_deep_dived": _domains,
            "phase2_depth_levels": _depths,
            "phase3_pattern_hits": [
                {"name": cf.get("type", ""), "level": cf.get("level", ""), "score": cf.get("score", 0)}
                for cf in (cross_findings or [])
            ],
            "phase3_conflicts": [
                {"rule_id": cf.get("_conflict_rule_id", ""), "type": cf.get("type", ""), "level": cf.get("level", "")}
                for cf in (cross_findings or []) if cf.get("_conflict_rule_id")
            ],
            "phase4_synthesis": {
                "risk_score": _synth.get("risk_score", 0),
                "overall_risk": _synth.get("overall_risk", ""),
                "cross_validated_patterns": _synth.get("cross_validated_patterns", 0),
                "p0_count": len(_synth.get("prioritized_actions", {}).get("P0_立即行动", [])),
                "p1_count": len(_synth.get("prioritized_actions", {}).get("P1_重点关注", [])),
                "core_issues": _synth.get("core_issues", []),
            },
            "finding_index_keys": list(ctx.finding_index.keys())[:20] if ctx.finding_index else [],
            "memories_count": 0,
        }
    except Exception as e:
        import traceback
        engine_status = {"error": f"{e}: {traceback.format_exc()[-200:]}", "version": "v2.0-partial"}
    
    # ── 最终注入：Phase 4 综合定性 + Phase 3 交叉验证（在所有过滤之后）──
    # ═══ 服务行业二次过滤：确保Phase 3/4引擎新增的进销存发现也被清除 ═══
    if _is_svc_final:
        _svc_exclude_patterns2 = [
            "进销比","进销存","有进无销","有销无进","品名不匹配","品名差异",
            "BOM表","物料清单","进销品名","购销商品种不匹配","购销售商品种",
            "加工费掩盖","缺少BOM","商品种不匹配","加工链条","存货积压",
            "库存周转","进销异常","购销严重倒挂","原材料.*成品","原料.*加工",
        ]
        _filtered2 = 0
        _new_all = []
        for f in all_findings:
            ftype = f.get("type", "")
            if any(re.search(pat, ftype) for pat in _svc_exclude_patterns2):
                _filtered2 += 1
                continue
            fdetail = f.get("detail", "")
            if "BOM表" in fdetail and "进销" in fdetail:
                _filtered2 += 1
                continue
            _new_all.append(f)
        all_findings = _new_all
        if _filtered2:
            pipeline_log.append(f"[服务行业二次过滤] 追加剔除{_filtered2}条引擎阶段产生的进销存发现")
    
    final_findings = list(all_findings)
    if synth_finding is not None:
        final_findings.insert(0, synth_finding)
    if cross_findings:
        for cf in reversed(cross_findings):
            final_findings.insert(0, cf)
    
    # ── 结论可验证性：为每条 finding 生成推理链路 trace ──
    for idx, f in enumerate(final_findings):
        f["_trace"] = _build_finding_trace(f, idx, analysis_trace_id, ctx)
        _analysis_traces.append(f["_trace"])
    
    # ═══════════════════════════════════════════════════════════
    # AGI 三大升级引擎（2026-06-25）
    # ═══════════════════════════════════════════════════════════
    
    # ── ① 法律逻辑推理 ──
    try:
        from engine.legal_reasoner import run_legal_reasoning
        legal_results = run_legal_reasoning(final_findings, {"company_id": company_id})
        comprehensive["legal_reasoning"] = legal_results
        pipeline_log.append(f"[AGI-法律推理] {legal_results['matched_findings']}条发现匹配法律条文，引用{len(legal_results.get('articles',[]))}条")
    except Exception as e:
        pipeline_log.append(f"[AGI-法律推理] 执行异常: {e}")
    
    # ── ② 跨企业关系网 ──
    try:
        from engine.cross_enterprise_graph import run_cross_enterprise_analysis
        graph_results = run_cross_enterprise_analysis(db)
        comprehensive["cross_enterprise"] = graph_results
        pipeline_log.append(f"[AGI-跨企业] {graph_results.get('summary','')}")
    except Exception as e:
        pipeline_log.append(f"[AGI-跨企业] 执行异常: {e}")
    
    # ── ③ 时序趋势学习 ──
    try:
        from engine.trend_analyzer import run_trend_analysis
        # 提取当前指标快照
        current_metrics = {}
        if synthesis:
            current_metrics["risk_score"] = synthesis.get("risk_score", 0)
        if "material_intel" in comprehensive:
            mi = comprehensive["material_intel"]
            inv_stats = mi.get("发票", {}).get("统计", {})
            if inv_stats:
                current_metrics["invoice_count"] = inv_stats.get("销项发票数量", 0) + inv_stats.get("进项发票数量", 0)
            bank_stats = mi.get("银行流水", {}).get("统计", {})
            if bank_stats:
                current_metrics["bank_inflow"] = bank_stats.get("收款合计", 0)
                current_metrics["bank_outflow"] = bank_stats.get("付款合计", 0)
        
        trend_results = run_trend_analysis(company_id, current_metrics if current_metrics else None)
        comprehensive["trend_analysis"] = trend_results
        pipeline_log.append(f"[AGI-趋势] {trend_results.get('summary','')}")
    except Exception as e:
        pipeline_log.append(f"[AGI-趋势] 执行异常: {e}")
    
    result = {"ok": True, "report": {
        "overall_level": overall, "total_risks": total, "high_risk": high, "mid_risk": mid, "low_risk": total-high-mid,
        "files_count": len(docs), "rules_used": _actual_rule_count, "pipeline_log": pipeline_log, "file_results": file_results,
        "stats": stats, "domain_summary": domain_summary, "comprehensive": comprehensive,
        "target_entity": target_entity,
        "low_data_warning": low_data_warning,
        "quality_report": quality_report,
        "engine_status": engine_status,
        "all_findings": sorted(final_findings, key=lambda x: -(x.get("score") or 0)),
        "entity_graph": getattr(ctx, '_entity_graph', None) or {},
        "audit_strategies": getattr(ctx, '_audit_strategies', None) or {},
        "multimodal": getattr(ctx, '_multimodal', None) or {},
        "discovered_rules": getattr(ctx, '_discovered_rules', None) or {},
        "bayesian": getattr(ctx, '_bayesian', None) or {},
        "ema_learning": getattr(ctx, '_ema_learning', None) or {},
        "benford": getattr(ctx, '_benford', None) or {},
        "agi_initialized": agi_init_ok,
        "trace_id": analysis_trace_id,
        "trace_count": len(_analysis_traces),
        "blocked": False,
        "block_reason": "",
        "blocking_violations_count": 0,
        "gate_rounds": 0,
        "summary_text": (
            f"数据不足警告：仅提取{total_parsed}条记录，分析结果仅供参考。" if low_data_warning
            else f"29域+{_actual_rule_count}条稽查指令分析完成：{overall}，{total}项发现（高{high}/中{mid}）。提取{len(bank_txs)}条流水、{len(invoices)}张发票、{len(salaries)}条工资。凭证主营收入{voucher_revenue['total']:,.2f}元（未开票{voucher_revenue['uninvoiced']:,.2f}元）。")
    }}
    # 缓存最近分析结果（LRU: 最多保留30条，超出删除最旧）
    _MAX_CACHE = 30
    if len(_last_analysis_cache) >= _MAX_CACHE:
        oldest = min(_last_analysis_cache.keys(), key=lambda k: _last_analysis_cache[k].get("timestamp", ""))
        del _last_analysis_cache[oldest]
    _last_analysis_cache[company_id] = {"report": result, "timestamp": datetime.now().isoformat()}
    
    # ═══ 假设-验证推理 ───
    try:
        from engine.hypothesis_engine import run_hypothesis_verification
        all_findings, hypothesis_summary = run_hypothesis_verification(
            all_findings, ctx, bank_txs, invoices, sal_invs, pur_invs, salaries, pipeline_log
        )
        comprehensive["hypothesis_verification"] = hypothesis_summary
        # ── 同步result中的all_findings（因为假设验证修改了all_findings）──
        result["report"]["all_findings"] = sorted(all_findings, key=lambda x: -(x.get("score") or 0))
        result["report"]["total_risks"] = len(all_findings)
        result["report"]["high_risk"] = sum(1 for f in all_findings if f.get("level") == "高风险")
        result["report"]["mid_risk"] = sum(1 for f in all_findings if f.get("level") == "中风险")
        result["report"]["low_risk"] = sum(1 for f in all_findings if f.get("level") in ("低风险", "良好"))
    except Exception: pass
    
    # ═══ 纠正规则自动应用 ───
    try:
        from engine.self_learning import apply_correction_rules
        ind = ctx.company_profile.get("industry",""); bm = ctx.company_profile.get("biz_model","")
        corr_n = apply_correction_rules(all_findings, ind, bm)
        if corr_n > 0: pipeline_log.append(f"[CORRECTION] {corr_n}条纠正规则已应用")
    except Exception: pass
    
    # ═══ 结论自洽性检查：CONTRADICTION_RULES 矛盾检测 ═══
    try:
        contradictions = _check_conclusion_consistency(all_findings)
        if contradictions:
            all_findings.extend(contradictions)
            pipeline_log.append(f"[CROSS-CHECK] 矛盾检测: {len(contradictions)}条逻辑冲突发现")
        # ═══ 回溯引擎：矛盾→查provenance→定位根因→自动修正 ═══
        if contradictions:
            try:
                backtrack_report = _backtrack_engine(contradictions, all_findings, pipeline_log)
                comprehensive["backtrack_report"] = backtrack_report
                pipeline_log.append(f"[回溯引擎] 产出自查报告: {backtrack_report['total']}条矛盾分析")
                
                # ═══ 修正验证：对可自动修正的矛盾运行验证→对比新旧结果 ═══
                auto_fixes = backtrack_report.get("auto_fixes", [])
                if auto_fixes:
                    try:
                        fix_verification = _run_fix_verification(auto_fixes, all_findings, bank_txs, sal_invs, pur_invs, pipeline_log)
                        comprehensive["fix_verification"] = fix_verification
                        pipeline_log.append(f"[修正验证] {fix_verification['auto_resolved']}条已自动修正, {fix_verification['manual_required']}条仍需人工")
                        
                        # ═══ 第④步：保存分析记忆（矛盾+修正结果） ═══
                        industry = target_entity.get("industry", ctx.company_profile.get("industry", "未知"))
                        _save_analysis_memory(company_id, target_entity.get("name", ""), industry, backtrack_report, fix_verification, pipeline_log)
                    except Exception as _fve:
                        pipeline_log.append(f"[修正验证] 异常: {_fve}")
            except Exception as _bte:
                pipeline_log.append(f"[回溯引擎] 异常: {_bte}")
    except Exception as _cce:
        pipeline_log.append(f"[CROSS-CHECK] 矛盾检测异常: {_cce}")
    
    # ═══ 合规门禁（检测+标记模式，非阻断）───
    gate_passed = True
    gate_rounds = 1
    try:
        from engine.self_learning import run_compliance_gate
        gate_result, all_findings = run_compliance_gate(
            all_findings, pipeline_log, file_results, ctx
        )
        gate_passed = gate_result.get("passed", False)
        result["compliance_gate"] = gate_result
        result["report"]["gate_rounds"] = gate_rounds
        if not gate_passed:
            blocking_count = len(gate_result.get("blocking_violations", []))
            pipeline_log.append(f"[GATE-INFO] 合规门禁{gate_rounds}轮: {blocking_count}项违规已标记，报告仍可输出——底部标注质量警告")
            result["report"]["blocked"] = True
            result["report"]["block_reason"] = gate_result.get("blocked_reason", "")
            result["report"]["blocking_violations_count"] = blocking_count
        else:
            pipeline_log.append(f"[GATE-PASS] 合规门禁第{gate_rounds}轮通过 ✓")
    except Exception as e:
        pipeline_log.append(f"[COMPLIANCE] 门禁执行异常: {e}")
    
    # ── 保存分析记忆（引擎越用越聪明）──
    try:
        _synth = synthesis
        total_memories = save_analysis_memory(ctx, synthesis)
        pipeline_log.append(f"[MEMORY] 分析记忆已保存 (共{total_memories}条)")
    except Exception:
        pass
    
    # ── 行业基准自更新：将本次分析指标纳入行业统计池 ──
    try:
        _update_industry_benchmarks(company_id, result["report"], ctx)
        pipeline_log.append("[BENCHMARK] 行业基准值已更新")
    except Exception:
        pass
    
    # ── 自动规则发现：从运行数据中归纳新规则 ──
    try:
        from engine.rule_discovery import run_auto_rule_discovery
        discovery_result = run_auto_rule_discovery(pipeline_log)
        result["rule_discovery"] = discovery_result
        
        # ═══ 回路3: 规则发现 → 自动写入规则库 ═══
        discoveries = discovery_result.get("discoveries", [])
        auto_signals = [d for d in discoveries if d.get("type") == "auto_signal"]
        if auto_signals:
            rules_path = os.path.join(_PROJECT_ROOT, "static", "tax_risk_rules_local_export.json")
            try:
                if os.path.exists(rules_path):
                    with open(rules_path, "r", encoding="utf-8") as rf:
                        existing_rules = json.load(rf)
                else:
                    existing_rules = []
                max_id = max((r.get("id", 0) for r in existing_rules), default=1600)
                new_rules_added = 0
                for sig in auto_signals:
                    # 去重：已存在同类型signal才跳过
                    already_exists = any(
                        r.get("type") == "auto_signal" and r.get("industry") == sig.get("industry")
                        for r in existing_rules
                    )
                    if already_exists:
                        continue
                    max_id += 1
                    existing_rules.append({
                        "id": max_id,
                        "type": "auto_signal",
                        "rule_category": "自动发现",
                        "industry": sig.get("industry", ""),
                        "signal": sig.get("signal", ""),
                        "prevalence": sig.get("prevalence", ""),
                        "evidence": sig.get("evidence", ""),
                        "action": sig.get("action", ""),
                        "confidence": sig.get("confidence", 0),
                        "auto_discovered_at": datetime.now().isoformat(),
                        "severity": "中",
                        "enabled": True,
                    })
                    new_rules_added += 1
                if new_rules_added > 0:
                    with open(rules_path, "w", encoding="utf-8") as wf:
                        json.dump(existing_rules, wf, ensure_ascii=False, indent=2)
                    pipeline_log.append(f"[DISCOVERY] {new_rules_added}条自动发现的信号已写入规则库 (总数{len(existing_rules)})")
            except Exception: pass
    except Exception:
        pass
    
    # ═══ 模块运行日志 ───
    try:
        from engine.self_learning import record_module_run
        ind = ctx.company_profile.get("industry",""); bm = ctx.company_profile.get("biz_model","")
        for mod in orchestration_plan.get("active_modules", []):
            record_module_run(mod["id"], mod["name"], "completed",
                {"findings_count":len(all_findings),"high_quality_count":sum(1 for f in all_findings if (f.get("score",0)or 0)>=8)},
                company_id, ind, bm)
    except Exception: pass
    
    # ═══ 财税智能体：反思 + 洞见总结 + 经验积累 ═══
    try:
        target_name = target_entity.get("name","") if target_entity else ""
        if agi_pipeline is not None and agi_pipeline.agent is not None:
            agent_result = agi_pipeline.run_agent_cycle(
                bank_txs, invoices, salaries, vouchers, ctx, company_id, target_name, db
            )
            if not agent_result.get("error"):
                result["agent"] = {
                    "insight_summary": agent_result.get("insight_summary", ""),
                    "reflection": agent_result.get("reflection", {}),
                    "memory": agent_result.get("memory", {}),
                    "hypotheses": agent_result.get("hypotheses", []),
                }
                if agent_result.get("reflected_findings") and isinstance(agent_result["reflected_findings"], list) and len(agent_result["reflected_findings"]) > 0:
                    # v3.0: 合并而非覆盖 — 保留未被反思的原始发现
                    reflected = agent_result["reflected_findings"]
                    reflected_types = set()
                    for rf in reflected:
                        t = rf.get("_original_type") or rf.get("type", "")
                        if t: reflected_types.add(t)
                    # 合并：反思过的用反思版本，未反思的保留原版
                    merged = [f for f in all_findings if f.get("type", "") not in reflected_types]
                    merged.extend(reflected)
                    all_findings = merged
                    pipeline_log.append(f"[AGI] 反思合并完成: {len(reflected)}条更新, {len(merged)-len(reflected)}条保留")
                    result["report"]["all_findings"] = sorted(all_findings, key=lambda x: -(x.get("score") or 0))
                    result["report"]["total_risks"] = len(all_findings)
                    result["report"]["high_risk"] = sum(1 for f in all_findings if f.get("level") == "高风险")
                    result["report"]["mid_risk"] = sum(1 for f in all_findings if f.get("level") == "中风险")
                pipeline_log.append(f"[AGI] 智能体完成反思: {agent_result.get('reflection',{}).get('total_checked',0)}条结论")
                
                # ═══ 回路2: 反思证伪 → 自动降级结论 ═══
                downgraded_count = 0
                for f in all_findings:
                    reflection = f.get("_self_reflection", {})
                    verdict = reflection.get("verdict", "")
                    if verdict == "refuted":
                        old_level = f.get("level", "")
                        old_score = f.get("score", 5) or 5
                        # 高风险→中风险，中风险→低风险，分数减半
                        if old_level == "高风险":
                            f["level"] = "中风险"
                            f["score"] = max(2, old_score * 0.4)
                        elif old_level == "中风险":
                            f["level"] = "低风险"
                            f["score"] = max(1, old_score * 0.3)
                        f["_reflection_downgraded"] = True
                        f["_reflection_reason"] = reflection.get("reason", "")[:100]
                        downgraded_count += 1
                    elif verdict == "uncertain":
                        old_score = f.get("score", 5) or 5
                        f["score"] = max(3, old_score * 0.7)
                        f["_reflection_uncertain"] = True
                
                if downgraded_count > 0:
                    pipeline_log.append(f"[AGI] 反思证伪降级: {downgraded_count}条结论被证伪→自动降低风险等级")
                    # 重新统计
                    result["report"]["all_findings"] = sorted(all_findings, key=lambda x: -(x.get("score") or 0))
                    result["report"]["total_risks"] = len(all_findings)
                    result["report"]["high_risk"] = sum(1 for f in all_findings if f.get("level") == "高风险")
                    result["report"]["mid_risk"] = sum(1 for f in all_findings if f.get("level") == "中风险")
            else:
                pipeline_log.append(f"[AGI] 智能体异常: {agent_result['error']}")
    except Exception as _ag_err:
        pipeline_log.append(f"[AGI] 统一处理异常: {_ag_err}")
        result["agent"] = {"error": str(_ag_err)}
    
    # ═══ AGI管线：16模块知识注入 ═══
    if agi_pipeline is not None:
        try:
            # ⑦ 文件解析学习
            agi_pipeline.ingest_file_parsing(file_results, analysis_trace_id)
            
            # ⑧ 域分析学习
            agi_pipeline.ingest_domain_results(domain_results, analysis_trace_id, company_id)
            
            # ①② 稽查指令+线索链学习
            rule_details_list = []
            try:
                static_dir = os.path.join(_PROJECT_ROOT, "static")
                with open(os.path.join(static_dir, "tax_risk_rules_local_export.json"), "r", encoding="utf-8") as _rf:
                    rule_details_list = json.load(_rf)
            except: pass
            agi_pipeline.ingest_audit_rules(_actual_rule_count, rule_details_list, all_findings, analysis_trace_id, company_id)
            
            # ②③ 线索链+证据链学习（从comprehensive中提取触发记录）
            try:
                triggered = comprehensive.get("triggered_chains", [])
                agi_pipeline.ingest_clue_chains(triggered, all_findings, analysis_trace_id)
                agi_pipeline.ingest_evidence_chains(triggered, all_findings, analysis_trace_id)
            except: pass
            
            # ④ 分析链+因果叙事链学习
            try:
                agi_pipeline.ingest_analysis_chains(
                    triggered if 'triggered' in dir() else comprehensive.get("triggered_chains", []),
                    analysis_trace_id
                )
            except: pass
            
            # ⑤ 稽查方法论学习
            from engine.methodology_loader import METHODOLOGY_KNOWLEDGE
            methodologies = METHODOLOGY_KNOWLEDGE.get("methodologies", [])
            agi_pipeline.ingest_methodologies(methodologies, domain_results, analysis_trace_id)
            
            # ⑨⑩⑪ 跨域线索/分析/证据链学习
            try:
                agi_pipeline.ingest_cross_domain(
                    comprehensive.get("cross_clues", comprehensive.get("triggered_chains", [])),
                    comprehensive.get("cross_analysis", []),
                    comprehensive.get("cross_evidence", []),
                    analysis_trace_id
                )
            except: pass
            
            # ⑫ 方法论过滤学习
            pre_cnt = len(all_findings)
            agi_pipeline.ingest_filter_results(
                filter_log.get("reasons", []) if isinstance(filter_log, dict) else (filter_log or []),
                pre_cnt, len(all_findings),
                [], analysis_trace_id
            )
            
            # ⑬⑭⑮ 质量体系学习
            agi_pipeline.ingest_quality_data(
                quality_report or {},
                len(orchestration_plan.get("pipeline_stages", [])) if 'orchestration_plan' in dir() else 7,
                result.get("compliance_gate", {}),
                analysis_trace_id
            )
            
            # 推理引擎仪表盘(A) 学习
            agi_pipeline.ingest_engine_status(engine_status, ctx, analysis_trace_id)
            
            # 能力矩阵(B) 学习
            agi_pipeline.ingest_capability_matrix(None, analysis_trace_id)
            
            # 覆盖层(D): AGI自主修正
            try:
                from engine.override_engine import get_override_engine
                oe = get_override_engine()
                auto_result = oe.agi_auto_correct(all_findings, domain_results)
                if auto_result["corrections_proposed"] > 0:
                    pipeline_log.append(f"[AGI] 自主提议{auto_result['corrections_proposed']}条修正({auto_result['auto_activated']}条自动激活)")
                result["agi_overrides"] = auto_result
            except: pass
            
            # 汇总持久化
            try:
                agi_result = agi_pipeline.finalize_learning(
                    analysis_trace_id,
                    target_entity.get("name", "") if target_entity else "",
                    _target_industry or "",
                    ctx=ctx,
                )
                result["agi_pipeline"] = agi_result
                pipeline_log.append(f"[AGI] {agi_result.get('modules_covered',0)}/16模块已联通({agi_result.get('events_collected',0)}事件)")
                # 收集新模块错误
                if hasattr(agi_pipeline, 'errors') and agi_pipeline.errors:
                    for err in agi_pipeline.errors:
                        pipeline_log.append(f"[AGI] {err}")
            except Exception as _agi_finalize_err:
                pipeline_log.append(f"[AGI] 汇总持久化异常: {_agi_finalize_err}")
                result["agi_pipeline"] = {"error": str(_agi_finalize_err), "modules_covered": 0, "events_collected": 0}
        except Exception as _agi_err:
            pipeline_log.append(f"[AGI] 管线异常: {_agi_err}")
    
    # ═══ 回路4: 系统自愈引擎 — 应用从历史错误中学习的修正规则 ═══
    try:
        from engine.self_healing import apply_healing_rules, SelfHealingEngine
        healing_result = apply_healing_rules(all_findings, domain_results, db)
        if healing_result.get("fixed_count", 0) > 0:
            pipeline_log.append(f"[自愈] {healing_result['fixed_count']}条结论已自动修正 ({healing_result.get('rules_used',0)}条规则)")
            for applied in healing_result.get("applied", []):
                pipeline_log.append(f"[自愈] · {applied.get('rule_name','')[:50]} → {applied.get('finding','')[:40]}")
        elif healing_result.get("note") == "无活跃规则":
            # 尝试自动激活draft规则
            try:
                engine = SelfHealingEngine(db)
                draft_rules = db.query(engine._rule_model).filter(
                    engine._rule_model.status == "draft",
                    engine._rule_model.confidence >= 0.5,
                ).all() if hasattr(engine, '_rule_model') else []
                if draft_rules:
                    activated = 0
                    for rule in draft_rules:
                        rule.status = "active"
                        rule.auto_apply = True
                        activated += 1
                    if activated > 0:
                        db.commit()
                        pipeline_log.append(f"[自愈] 自动激活{activated}条draft规则(confidence>=0.5)")
            except Exception: pass
        result["self_healing"] = healing_result
    except Exception as _he:
        result["self_healing"] = {"error": str(_he)}
    
    # ═══ 报告块架构：将分析结果转化为结构化 blocks 数组 ═══
    # 每个 block 是独立的、自描述的。前端通用渲染器遍历 blocks 按 type 渲染。
    # 加段落→push block；调顺序→调 blocks 顺序；删段落→不 push。
    result["blocks"] = _build_report_blocks(result, company_id)
    
    # ═══ 报告文本增强：简短的detail自动扩充为规范结构 ═══
    _enrich_short_findings(all_findings, pipeline_log)
    
    # ═══ 发票明细数据注入（供报告附件使用）═══
    try:
        if sal_invs or pur_invs:
            invoice_tables = {"sales": [], "purchases": [], "core_cost": [], "major_expense": []}
            # 销项发票11列
            for inv in sal_invs[:200]:
                invoice_tables["sales"].append({
                    "counterparty": str(inv.get("buyer", inv.get("购买方",""))),
                    "goods": str(inv.get("goods", inv.get("货物或应税劳务名称",""))),
                    "spec": str(inv.get("spec", inv.get("规格",""))),
                    "unit": str(inv.get("unit", inv.get("单位",""))),
                    "qty": inv.get("qty", inv.get("数量", "")),
                    "amount": inv.get("amount", inv.get("金额", "")),
                    "tax": inv.get("tax", inv.get("税额", "")),
                    "total": inv.get("total", inv.get("价税合计", "")),
                    "date": str(inv.get("date", inv.get("开票日期",""))),
                    "inv_type": str(inv.get("inv_type", inv.get("发票类型",""))),
                    "inv_no": str(inv.get("inv_no", inv.get("发票号",""))),
                })
            # 进项发票11列
            for inv in pur_invs[:200]:
                row = {
                    "counterparty": str(inv.get("seller", inv.get("销售方",""))),
                    "goods": str(inv.get("goods", inv.get("货物或应税劳务名称",""))),
                    "spec": str(inv.get("spec", inv.get("规格",""))),
                    "unit": str(inv.get("unit", inv.get("单位",""))),
                    "qty": inv.get("qty", inv.get("数量", "")),
                    "amount": inv.get("amount", inv.get("金额", "")),
                    "tax": inv.get("tax", inv.get("税额", "")),
                    "total": inv.get("total", inv.get("价税合计", "")),
                    "date": str(inv.get("date", inv.get("开票日期",""))),
                    "inv_type": str(inv.get("inv_type", inv.get("发票类型",""))),
                    "inv_no": str(inv.get("inv_no", inv.get("发票号",""))),
                }
                invoice_tables["purchases"].append(row)
            # 主营业务成本发票
            if 'core_cost_invs' in dir() and core_cost_invs:
                for inv in core_cost_invs[:100]:
                    invoice_tables["core_cost"].append({
                        "counterparty": str(inv.get("seller", inv.get("销售方",""))),
                        "goods": str(inv.get("goods", inv.get("货物或应税劳务名称",""))),
                        "amount": inv.get("amount", inv.get("金额", "")),
                        "total": str(inv.get("total", inv.get("价税合计", ""))),
                        "date": str(inv.get("date", inv.get("开票日期",""))),
                    })
            # 重大费用发票
            if 'major_expense_invs' in dir() and major_expense_invs:
                for inv in major_expense_invs[:100]:
                    invoice_tables["major_expense"].append({
                        "counterparty": str(inv.get("seller", inv.get("销售方",""))),
                        "goods": str(inv.get("goods", inv.get("货物或应税劳务名称",""))),
                        "amount": inv.get("amount", inv.get("金额", "")),
                        "total": str(inv.get("total", inv.get("价税合计", ""))),
                        "date": str(inv.get("date", inv.get("开票日期",""))),
                    })
            result["report"]["invoice_tables"] = invoice_tables
            result["report"]["invoice_counts"] = {
                "sales": len(sal_invs), "purchases": len(pur_invs),
                "core_cost": len(core_cost_invs) if 'core_cost_invs' in dir() and core_cost_invs else 0,
                "major_expense": len(major_expense_invs) if 'major_expense_invs' in dir() and major_expense_invs else 0,
            }
    except Exception:
        pass
    
    return result

# ═══════════ 文本净化：剔除模板句/重复句/空描述 ═══════════
# 必须在质量标准执行之前运行，确保进入报告的是可读的专业文本

def _enrich_short_findings(all_findings, pipeline_log):
    """将简短的finding扩充为规范的报告结构：现象→证据→影响→法条→建议"""
    enriched = 0
    for f in all_findings:
        detail = str(f.get("detail", ""))
        if len(detail) < 60:
            # 拼合各字段为完整段落
            parts = []
            parts.append(detail)
            how = str(f.get("how_found", "")).strip()
            if how and len(how) > 10:
                parts.append("稽查方法：" + how)
            tax_impact = str(f.get("tax_impact", "")).strip()
            if tax_impact and len(tax_impact) > 10:
                parts.append("税务影响：" + tax_impact)
            policy = str(f.get("policy_ref", "")).strip()
            if policy and len(policy) > 5 and "法规依据" not in detail:
                parts.append("法规依据：" + policy)
            suggestion = str(f.get("suggestion", "")).strip()
            if suggestion and len(suggestion) > 10 and "驳回" not in suggestion and "立即整改" not in suggestion:
                parts.append("处理建议：" + suggestion)
            if len(parts) > 1:
                f["detail"] = "。".join(parts)
                enriched += 1
    if enriched:
        pipeline_log.append(f"报告增强: {enriched}条简短发现已扩充为规范结构")

_BOILERPLATE_PREFIXES = [
    "是税务稽查重点方向。",
    "是税务稽查重点方向",
    "稽查重点方向。",
    "需逐笔核实，",
    "请核实并提供相关佐证材料。",
]

_BOILERPLATE_SUFFIXES = [
    "——请核实并提供相关佐证材料。",
    "。——请核实并提供相关佐证材料。",
]

def _sanitize_finding_boilerplate(all_findings):
    """剔除每条发现中的模板句、重复句、空描述，确保报告文本专业可读。
    
    处理内容：
    1. 剔除"是税务稽查重点方向"等开篇模板
    2. 删除连续重复的句子
    3. 删除空描述（detail=title的复制品）
    4. 清除suggestion中的"请提供相关佐证材料"万能句
    """
    sanitized = []
    stats = {"cleaned_prefix": 0, "dedup": 0, "empty_desc": 0, "empty_suggestion": 0}
    
    for f in all_findings:
        ftype = str(f.get("type", ""))
        
        # ── 1. 清理detail中的模板前缀 ──
        detail = str(f.get("detail", ""))
        for prefix in _BOILERPLATE_PREFIXES:
            if detail.startswith(prefix):
                detail = detail[len(prefix):].strip()
                stats["cleaned_prefix"] += 1
                break
        # Also clean leading boilerplate if the detail starts with the type name itself
        if detail.startswith(ftype + "是"):
            idx = detail.find("。")
            if idx > 0:
                # Skip the redundant first sentence if it's just "X是税务稽查重点方向"
                first_sent = detail[:idx+1]
                if any(bp in first_sent for bp in _BOILERPLATE_PREFIXES[:3]):
                    detail = detail[idx+1:].strip()
                    stats["cleaned_prefix"] += 1
        
        # ── 2. 删除连续重复的句子（同一句话出现两次） ──
        sentences = [s.strip() for s in detail.replace("。", "。\n").split("\n") if s.strip()]
        deduped = []
        for s in sentences:
            if not deduped or s != deduped[-1]:
                deduped.append(s)
        if len(deduped) < len(sentences):
            stats["dedup"] += 1
        detail = "。".join(s for s in deduped if s)
        
        # ── 3. 检测空描述——detail仅等于标题或title的变体，无实质内容 ──
        desc = str(f.get("description", ""))
        if len(detail.replace(ftype, "").replace("是", "").replace("。", "").strip()) < 8:
            # detail is essentially empty - just the title repeated
            if desc and len(desc) > 20:
                detail = desc  # fallback to description
            else:
                stats["empty_desc"] += 1
        f["detail"] = detail
        
        # ── 4. 清理suggestion中的万能套话 ──
        suggestion = str(f.get("suggestion", ""))
        for suffix in _BOILERPLATE_SUFFIXES:
            suggestion = suggestion.replace(suffix, "")
        # 清除空占位符
        suggestion = suggestion.replace("（如：()；()；()）", "").replace("如：()；()；()", "")
        if not suggestion.strip() or suggestion.strip() in ("请核实并提供相关佐证材料", "请提供相关佐证材料", "请提供相关资料"):
            stats["empty_suggestion"] += 1
        f["suggestion"] = suggestion.strip()
        
        sanitized.append(f)
    
    log_msg = (f"文本净化完成: 剔除{stats['cleaned_prefix']}条模板前缀、去重{stats['dedup']}条、"
               f"修复空描述{stats['empty_desc']}条、清理套话建议{stats['empty_suggestion']}条")
    return sanitized, log_msg


# ═══════════ 稽查报告质量标准执行（12项硬指标）══════════
# 提炼自Finding①"资料完备度综合评估"的标杆质量 + 实战缺陷反思，全行业适用
# 标准1: 客观第三人称叙事 — 使用"经查""该企业""被查单位"等客观表述
# 标准2: 事实-证据-后果三要素 — 缺一不可
# 标准3: 完整因果链 A→B→C→D — 至少一步推导
# 标准4: 可操作的紧迫感 — suggestion具体到步骤
# 标准5: 特定法律条款引用 — 含具体条款号
# 标准6: 证据明细表(items) — 多项明细必须附items数组
# 标准7: 方法在前过程在后 — 先声明稽查方法再展示结果
# 标准8: 反模板句 — 禁止"是税务稽查重点方向""需逐笔核实"等口水话
# 标准9: 事实具体化 — 必须含具体数值（日期/金额/数量/百分比）
# 标准10: 防跨发现复制 — tax_impact不能与同批其他发现完全相同
# 标准11: 空占位符检测 — suggestion不能含"()""已识别N条关联记录（如：）"
# 标准12: 法律条款号 — policy_ref必须含"第X条"或"第X款"等具体条款号

BOILERPLATE_LEGAL_TEXT = "《中华人民共和国税收征收管理法》及相关税收法规。具体条文由审理环节根据违法事实最终认定。"
BOILERPLATE_LEGAL_SHORT = "《中华人民共和国税收征收管理法》及相关税收法规。"

def _enforce_report_quality_standards(all_findings, pipeline_log):
    """对全部发现执行12项质量标准检查，不达标标记问题但不阻塞（降级+标注）
    
    Returns: (enforced_findings, quality_report)
    """
    enforced = []
    quality_log = {"total": len(all_findings), "passed": 0, "warnings": [], "stats": {
        "标准1_叙事": 0, "标准2_三要素": 0, "标准3_因果链": 0,
        "标准4_建议": 0, "标准5_法律引用": 0, "标准6_items": 0, "标准7_方法": 0,
        "标准8_反模板": 0, "标准9_具体化": 0, "标准10_防复制": 0,
        "标准11_空占位": 0, "标准12_法条号": 0
    }}
    
    # 预收集所有tax_impact用于标准10防复制检查
    all_impacts = [str(f.get("tax_impact", "")) for f in all_findings]
    
    for f in all_findings:
        issues = []
        ftype = str(f.get("type", ""))
        how_found = str(f.get("how_found", ""))
        tax_impact = str(f.get("tax_impact", ""))
        policy_ref = str(f.get("policy_ref", ""))
        suggestion = str(f.get("suggestion", ""))
        description = str(f.get("description", ""))
        detail = str(f.get("detail", ""))
        has_items = bool(f.get("items")) and len(f.get("items", [])) > 0
        
        # 标准1: 客观第三人称叙事
        # how_found/description 应使用"经查""该企业""被查单位"等客观表述，不得使用第一人称"我"
        has_first_person = "我" in how_found or "我" in description
        has_third_person = any(k in how_found + description for k in ["经查", "该企业", "被查单位", "发现", "经核查"])
        if has_first_person and not has_third_person:
            issues.append("标准1_叙事: 应使用客观第三人称表述（经查/该企业），避免第一人称")
            quality_log["stats"]["标准1_叙事"] += 1
        elif has_first_person:
            issues.append("标准1_叙事: 含第一人称'我'，建议改为'经查'或'该企业'等客观表述")
            quality_log["stats"]["标准1_叙事"] += 1
        
        # 标准2: 事实-证据-后果三要素
        has_facts = len(tax_impact) > 20 and any(k in tax_impact for k in ["→", "导致", "可能", "将", "无法", "缺失"])
        has_evidence = len(how_found) > 20
        has_consequence = len(tax_impact) > 30 and ("→" in tax_impact or "。" in tax_impact)
        if not (has_facts and has_evidence and has_consequence):
            issues.append("标准2_三要素: 缺少事实/证据/后果之一")
            quality_log["stats"]["标准2_三要素"] += 1
        
        # 标准3: 完整因果链 A→B→C→D
        # tax_impact 中"→"的数量反映因果链深度，至少2个"→"
        arrow_count = tax_impact.count("→")
        if arrow_count < 1 and len(tax_impact) < 40:
            issues.append("标准3_因果链: 缺少因果关系推导")
            quality_log["stats"]["标准3_因果链"] += 1
        
        # 标准4: 可操作的紧迫感
        # suggestion 需具体，不能是"请提供相关资料"等套话
        boilerplate_suggestion = any(k in suggestion for k in ["请提供相关", "请配合", "请核实相关", "请按要求"])
        if boilerplate_suggestion or len(suggestion) < 30:
            issues.append("标准4_建议: 建议过于笼统或为套话")
            quality_log["stats"]["标准4_建议"] += 1
        
        # 标准5: 特定法律条款引用
        # 不能使用模板化的兜底法律文本
        if BOILERPLATE_LEGAL_TEXT in policy_ref or BOILERPLATE_LEGAL_SHORT in policy_ref:
            issues.append("标准5_法律引用: 使用了兜底模板文本")
            quality_log["stats"]["标准5_法律引用"] += 1
            # 清除模板文本，保留空或其他引用
            f["policy_ref"] = policy_ref.replace(BOILERPLATE_LEGAL_TEXT, "").replace(BOILERPLATE_LEGAL_SHORT, "").strip()
        
        # 标准6: 证据明细表
        # 如果detail中包含多个条目（如"缺失11类"）但没有items，标记
        detail = str(f.get("detail", ""))
        multi_item_keywords = ["缺失", "家", "个客户", "笔", "张发票", "项", "类"]
        should_have_items = any(k in ftype + detail for k in multi_item_keywords) and not has_items
        if should_have_items:
            issues.append("标准6_items: 涉及多项明细但缺少items数组")
            quality_log["stats"]["标准6_items"] += 1
        
        # 标准7: 方法在前，过程在后
        # detail/description 应先声明稽查方法再展示结果
        has_method_keywords = any(k in detail + how_found for k in ["稽查方法", "核查法", "比对法", "穿透法", "核对法", "比对"])
        has_process_detail = len(detail) > 80
        if has_process_detail and not has_method_keywords:
            issues.append("标准7_方法声明: 缺少稽查方法声明——应先讲方法再秀过程")
            quality_log["stats"]["标准7_方法"] += 1
        
        # 标准8: 反模板句 — 检测残留的"是税务稽查重点方向"等口水话
        boilerplate_phrases = [
            "是税务稽查重点方向", "需逐笔核实", "请核实并提供相关佐证材料",
            "通过调取企业各税种申报表及备案资料，核实企业是否按规定期限、规定内容完成各项税务申报和备案",
            "申报不合规是税务行政处罚的常见案由"
        ]
        full_text = ftype + detail + how_found + description + tax_impact + suggestion
        for bp in boilerplate_phrases:
            if bp in full_text:
                issues.append(f"标准8_反模板: 含模板句'{bp[:20]}...'")
                quality_log["stats"]["标准8_反模板"] += 1
                break
        
        # 标准9: 事实具体化 — 必须含具体数值
        import re
        has_numbers = bool(re.search(r'\d[\d,.]*万?元?', detail + description))
        has_date_context = bool(re.search(r'\d{4}年|\d{1,2}月|\d{1,2}日|共\d+[条张笔家个]', detail + description))
        if len(detail) > 30 and not has_numbers and not has_date_context:
            issues.append("标准9_具体化: 事实描述缺少具体数值（金额/日期/数量/百分比）")
            quality_log["stats"]["标准9_具体化"] += 1
        
        # 标准10: 防跨发现复制 — tax_impact不能与同批其他发现完全相同
        this_impact = str(f.get("tax_impact", ""))
        if len(this_impact) > 20:
            dupe_count = sum(1 for imp in all_impacts if imp == this_impact and len(imp) > 20)
            if dupe_count >= 2:
                issues.append(f"标准10_防复制: tax_impact与其他{dupe_count-1}条发现完全相同，疑似复制粘贴")
                quality_log["stats"]["标准10_防复制"] += 1
        
        # 标准11: 空占位符检测
        empty_patterns = ["()", "已识别N条关联记录（如：", "（如：()；()；()）", "如：()；()；()"]
        for ep in empty_patterns:
            if ep in suggestion:
                issues.append("标准11_空占位: 建议中含空占位符")
                quality_log["stats"]["标准11_空占位"] += 1
                break
        
        # 标准12: 法律条款号
        if policy_ref and len(policy_ref) > 5:
            has_clause_no = bool(re.search(r'第[一二三四五六七八九十\d]+条|第[一二三四五六七八九十\d]+款', policy_ref))
            if not has_clause_no:
                issues.append("标准12_法条号: 法律引用缺少具体条款号")
                quality_log["stats"]["标准12_法条号"] += 1
        
        # 记录质量结果
        if not issues:
            quality_log["passed"] += 1
        else:
            f["_quality_issues"] = issues
            quality_log["warnings"].append({"type": ftype[:40], "issues": issues})
        
        enforced.append(f)
    
    passed_pct = quality_log["passed"] / max(quality_log["total"], 1) * 100
    pipeline_log.append(
        f"稽查报告质量标准检查: {quality_log['passed']}/{quality_log['total']}项通过（{passed_pct:.2f}%）——"
        f"12项标准逐条检查完成"
    )
    
    return enforced, quality_log


# ═══════════ 明细注入：为每条发现附加结构化明细数据 ═══════════

def _enrich_finding_details(all_findings, bank_txs, invoices, salaries, docs):
    """为每条发现附加items明细列表，使报告有具体数据支撑而非空泛结论。
    
    每条items = [{列字段...}]，前端渲染为可折叠明细表。
    """
    if not all_findings:
        return all_findings
    
    # 预提取原始数据中的关键信息
    pur_invs = [i for i in invoices if i.get("direction") in ("进项", "purchase")]
    sal_invs = [i for i in invoices if i.get("direction") in ("销项", "sales")]
    
    for f in all_findings:
        ftype = f.get("type", "")
        items = []
        
        # ── 1. 有进无销风险：列出具体商品 ──
        if "有进无销" in ftype and pur_invs and sal_invs:
            sal_goods = set(str(i.get("goods", "")).strip() for i in sal_invs)
            pur_by_goods = {}
            for i in pur_invs:
                g = str(i.get("goods", "")).strip()
                if g and g not in sal_goods:
                    pur_by_goods[g] = pur_by_goods.get(g, {"amount": 0, "suppliers": set(), "count": 0})
                    pur_by_goods[g]["amount"] += float(i.get("amount", 0) or 0)
                    pur_by_goods[g]["suppliers"].add(str(i.get("seller", ""))[:20])
                    pur_by_goods[g]["count"] += 1
            sorted_goods = sorted(pur_by_goods.items(), key=lambda x: -x[1]["amount"])
            for g, v in sorted_goods:
                items.append({
                    "商品名称": g[:30], "采购次数": v["count"],
                    "采购金额": f"{v['amount']:,.2f}", "供应商": "、".join(list(v["suppliers"])) if v["suppliers"] else ""
                })
        
        # ── 2. 有销无进风险：列出具体商品 ──
        elif "有销无进" in ftype and sal_invs and pur_invs:
            pur_goods = set(str(i.get("goods", "")).strip() for i in pur_invs)
            sal_by_goods = {}
            for i in sal_invs:
                g = str(i.get("goods", "")).strip()
                if g and g not in pur_goods:
                    sal_by_goods[g] = sal_by_goods.get(g, {"amount": 0, "buyers": set(), "count": 0})
                    sal_by_goods[g]["amount"] += float(i.get("amount", 0) or 0)
                    sal_by_goods[g]["buyers"].add(str(i.get("buyer", ""))[:20])
                    sal_by_goods[g]["count"] += 1
            sorted_goods = sorted(sal_by_goods.items(), key=lambda x: -x[1]["amount"])
            for g, v in sorted_goods:
                items.append({
                    "商品名称": g[:30], "开票次数": v["count"],
                    "开票金额": f"{v['amount']:,.2f}", "客户": "、".join(list(v["buyers"])) if v["buyers"] else ""
                })
        
        # ── 3. 进项发票与银行付款未匹配 ──
        elif "进项发票与银行付款" in ftype and pur_invs and bank_txs:
            # 从银行流水中提取付款对方
            bank_payees = set()
            bank_payees_lower = set()
            for tx in bank_txs:
                debit = float(tx.get("debit", 0) or 0)
                if debit > 0:
                    cp = str(tx.get("counterparty", "")).strip()
                    if cp:
                        bank_payees.add(cp)
                        bank_payees_lower.add(cp.lower().replace(" ", ""))
            
            unmatched = []
            for i in pur_invs:
                seller = str(i.get("seller", "")).strip()
                if not seller:
                    continue
                # 排除特殊名称
                seller_lower = seller.lower().replace(" ", "")
                matched = any(
                    seller_lower in bp or bp in seller_lower
                    for bp in bank_payees_lower
                )
                if not matched:
                    # 2字特殊名排除
                    if len(seller.replace("市", "").replace("省", "")) <= 2:
                        continue
                    unmatched.append({
                        "供应商": seller[:30],
                        "金额": f"{float(i.get('amount', 0) or 0):,.2f}",
                        "货物": str(i.get("goods", ""))[:20],
                        "发票号": str(i.get("inv_no", ""))[:20] or "-"
                    })
            items = sorted(unmatched, key=lambda x: -float(x["金额"].replace(",", "")))
        
        # ── 4. 收款来源与开票客户不匹配 ──
        elif "收款来源" in ftype and "开票客户" in ftype and bank_txs and sal_invs:
            buyer_names = set()
            buyer_names_lower = set()
            for i in sal_invs:
                b = str(i.get("buyer", "")).strip()
                if b and len(b) > 2:
                    buyer_names.add(b)
                    buyer_names_lower.add(b.lower().replace(" ", ""))
            
            # 按收款对方统计
            payer_totals = {}
            for tx in bank_txs:
                credit = float(tx.get("credit", 0) or 0)
                if credit > 0:
                    cp = str(tx.get("counterparty", "")).strip()
                    if cp and len(cp) > 1:
                        payer_totals[cp] = payer_totals.get(cp, 0) + credit
            
            # 关联发票客户
            for i in sal_invs:
                b = str(i.get("buyer", "")).strip()
                if b and b in payer_totals:
                    payer_totals[b] = payer_totals[b] - float(i.get("amount", 0) or 0)
            
            sorted_payers = sorted(payer_totals.items(), key=lambda x: -x[1])
            for cp, amt in sorted_payers:
                if amt > 0:
                    # 判断是否来自开票客户
                    cp_lower = cp.lower().replace(" ", "")
                    is_customer = any(cp_lower in bl or bl in cp_lower for bl in buyer_names_lower)
                    items.append({
                        "付款方": cp[:25],
                        "收款金额": f"{amt:,.2f}",
                        "是否开票客户": "是" if is_customer else "否"
                    })
        
        # ── 5. 发票缺少数量/单位字段 ──
        elif ("发票缺少数量" in ftype or "发票缺少计量" in ftype or "加工费发票缺少" in ftype) and invoices:
            is_proc_fee = "加工费" in ftype
            for i in invoices:
                amt = float(i.get("amount", 0) or 0)
                qty = i.get("qty", "")
                unit = i.get("unit", "")
                goods = str(i.get("goods", ""))
                if amt <= 0:
                    continue
                # 加工费专项：只收录品名含"加工"的发票
                if is_proc_fee and "加工" not in goods:
                    continue
                if ("缺少数量" in ftype and (not qty or qty in ("", "0", "0.0"))):
                    items.append({
                        "供应商/客户": (str(i.get("seller", "")) or str(i.get("buyer", "")))[:25],
                        "货物": str(i.get("goods", ""))[:25], "金额": f"{amt:,.2f}",
                        "发票号": str(i.get("inv_no", ""))[:20] or "-",
                        "方向": i.get("direction", "")
                    })
                    if len(items) >= 20: break
                elif ("缺少计量" in ftype and (not unit or unit.strip() == "")):
                    items.append({
                        "供应商/客户": (str(i.get("seller", "")) or str(i.get("buyer", "")))[:25],
                        "货物": str(i.get("goods", ""))[:25], "金额": f"{amt:,.2f}",
                        "发票号": str(i.get("inv_no", ""))[:20] or "-",
                        "方向": i.get("direction", "")
                    })
                    if len(items) >= 20: break
        
        # ── 6. 加工费发票 ──
        elif "加工费" in ftype and invoices:
            for i in invoices:
                g = str(i.get("goods", ""))
                if "加工" in g:
                    amt = float(i.get("amount", 0) or 0)
                    if amt > 0:
                        qty = i.get("qty", "")
                        unit = i.get("unit", "")
                        issues = []
                        if not qty or qty in ("", "0"): issues.append("缺数量")
                        if not unit or unit.strip() == "": issues.append("缺单位")
                        if issues:
                            items.append({
                                "供应商": str(i.get("seller", ""))[:25],
                                "货物": g[:30], "金额": f"{amt:,.2f}",
                                "问题": "、".join(issues), "发票号": str(i.get("inv_no", ""))[:20] or "-"
                            })
                            if len(items) >= 20: break
        
        # ── 7. 进销数量严重偏差 ──
        elif "进销数量严重偏差" in ftype and pur_invs and sal_invs:
            pur_qty = {}
            for i in pur_invs:
                g = str(i.get("goods", "")).strip()
                qty_str = str(i.get("qty", "")).strip()
                if g and qty_str and qty_str != "0":
                    try:
                        pur_qty[g] = pur_qty.get(g, 0) + float(qty_str)
                    except: pass
            sal_qty = {}
            for i in sal_invs:
                g = str(i.get("goods", "")).strip()
                qty_str = str(i.get("qty", "")).strip()
                if g and qty_str and qty_str != "0":
                    try:
                        sal_qty[g] = sal_qty.get(g, 0) + float(qty_str)
                    except: pass
            for g in pur_qty:
                pi = pur_qty.get(g, 0)
                si = sal_qty.get(g, 0)
                if pi > 0 and abs(pi - si) > min(pi, si) * 0.5:
                    items.append({
                        "商品": g[:30], "进量": f"{pi:,.2f}",
                        "销量": f"{si:,.2f}", "偏差": f"{abs(pi-si):,.2f}"
                    })
                    if len(items) >= 20: break
        
        # ── 8. 发票连号异常 ──
        elif "发票连号" in ftype and sal_invs:
            # 简化去重
            seen_nos = set()
            for i in sal_invs:
                no = str(i.get("inv_no", "")).strip()
                d = str(i.get("date", ""))[:10]
                bn = str(i.get("buyer", ""))[:20]
                if no and no not in seen_nos and len(no) >= 6:
                    seen_nos.add(no)
                    try:
                        num = int("".join(c for c in no if c.isdigit())[-6:])
                        items.append({"号码": no, "日期": d, "客户": bn, "数字部分": num})
                    except: pass
            # 排序找连续
            items.sort(key=lambda x: x.get("数字部分", 0))
            groups = []
            cur = [items[0]] if items else []
            for j in range(1, len(items)):
                if items[j]["数字部分"] - items[j-1]["数字部分"] <= 3:
                    cur.append(items[j])
                else:
                    if len(cur) >= 3: groups.append(cur)
                    cur = [items[j]]
            if len(cur) >= 3: groups.append(cur)
            items = []
            for grp in groups:
                nos = [g["号码"] for g in grp]
                items.append({
                    "起始号": nos[0], "终止号": nos[-1],
                    "张数": str(len(grp)), "日期范围": f"{grp[0]['日期']}~{grp[-1]['日期']}"
                })
        
        # ── 9. 收款与开票金额偏差 ──
        elif "收款与开票金额偏差" in ftype and bank_txs and sal_invs:
            # Create items by rough period
            from collections import defaultdict
            period_bank = defaultdict(float)
            period_inv = defaultdict(float)
            for tx in bank_txs:
                credit = float(tx.get("credit", 0) or 0)
                if credit > 0:
                    d = str(tx.get("date", ""))[:7]
                    period_bank[d] += credit
            for i in sal_invs:
                d = str(i.get("date", ""))[:7]
                period_inv[d] += float(i.get("amount", 0) or 0)
            all_periods = sorted(set(list(period_bank.keys()) + list(period_inv.keys())))
            for p in all_periods:
                b = period_bank.get(p, 0)
                s = period_inv.get(p, 0)
                if b > 0 or s > 0:
                    diff = b - s
                    items.append({
                        "期间": p, "收款": f"{b:,.2f}",
                        "开票": f"{s:,.2f}", "差额": f"{diff:,.2f}"
                    })
            if items: items = items
        
        # ── 10. 经常损益(周末交易/高频低额等) ──
        elif "周末交易" in ftype or "非工作日" in ftype:
            for tx in bank_txs:
                d = str(tx.get("date", ""))[:10]
                debit = float(tx.get("debit", 0) or 0)
                credit = float(tx.get("credit", 0) or 0)
                amt = max(debit, credit)
                if amt > 0:
                    from datetime import datetime
                    try:
                        dt = datetime.strptime(d, "%Y-%m-%d")
                        if dt.weekday() >= 5:
                            items.append({
                                "日期": d, f"{'付款' if debit > 0 else '收款'}金额": f"{amt:,.2f}",
                                "对方": str(tx.get("counterparty", ""))[:20], "摘要": str(tx.get("summary", ""))[:30]
                            })
                            if len(items) >= 10:
                                break
                    except:
                        pass
        
        # 非工作日开票
        elif "非工作日开票" in ftype and sal_invs:
            for i in sal_invs:
                d = str(i.get("date", ""))[:10]
                if len(d) >= 10:
                    from datetime import datetime
                    try:
                        dt = datetime.strptime(d, "%Y-%m-%d")
                        if dt.weekday() >= 5:
                            items.append({
                                "日期": d, "发票号": str(i.get("inv_no", ""))[:20] or "-",
                                "客户": str(i.get("buyer", ""))[:20], "金额": f"{float(i.get('amount', 0) or 0):,.2f}",
                                "货物": str(i.get("goods", ""))[:20]
                            })
                            if len(items) >= 10: break
                    except: pass
        
        elif "高频低额" in ftype and pur_invs:
            # Count by seller
            seller_counts = {}
            for i in pur_invs:
                s = str(i.get("seller", ""))[:30].strip()
                if s:
                    seller_counts[s] = seller_counts.get(s, {"count": 0, "amount": 0})
                    seller_counts[s]["count"] += 1
                    seller_counts[s]["amount"] += float(i.get("amount", 0) or 0)
            for s, v in seller_counts.items():
                if v["count"] >= 10:
                    avg = v["amount"] / v["count"] if v["count"] > 0 else 0
                    items.append({
                        "供应商": s, "开票次数": str(v["count"]),
                        "均额": f"{avg:,.2f}", "总额": f"{v['amount']:,.2f}"
                    })
                    if len(items) >= 15: break
        
        elif "交易时间与金额模式" in ftype and bank_txs:
            for tx in bank_txs:
                amt = max(float(tx.get("debit", 0) or 0), float(tx.get("credit", 0) or 0))
                if amt >= 10000 and amt == int(amt):
                    items.append({
                        "日期": str(tx.get("date", ""))[:10],
                        "金额": f"{amt:,.2f}", "对方": str(tx.get("counterparty", ""))[:20],
                        "摘要": str(tx.get("summary", ""))[:30]
                    })
                    if len(items) >= 15: break
        
        # ── 注入items ──
        if items:
            f["items"] = items
    
    return all_findings


def _enrich_evidence_rows(all_findings, bank_txs, invoices, salaries, vouchers):
    """为每条发现附加原始数据行级引用（evidence_rows），实现白盒可验证结论。
    
    每条 evidence_row 包含：数据来源类型、引用ID（发票号/流水号/凭证号）、
    金额、对方名称、日期等可追溯字段。前端渲染为可点击证据链接。
    """
    if not all_findings:
        return all_findings
    
    # 数据分片
    pur_invs = [i for i in invoices if i.get("direction") in ("进项", "purchase")]
    sal_invs = [i for i in invoices if i.get("direction") in ("销项", "sales")]
    
    # 证据行构建辅助
    def _inv_row(inv, label="发票"):
        return {
            "source": label,
            "ref_id": str(inv.get("inv_no", inv.get("发票号码", "")))[:25] or "-",
            "ref_label": str(inv.get("goods", inv.get("货物或应税劳务名称", "")))[:30],
            "amount": float(inv.get("amount", inv.get("total", 0)) or 0),
            "counterparty": str(inv.get("seller", inv.get("buyer", inv.get("销方名称", inv.get("购方名称", "")))))[:25],
            "date": str(inv.get("date", inv.get("inv_date", inv.get("开票日期", ""))))[:10],
            "note": str(inv.get("direction", ""))
        }
    
    def _bank_row(tx, label="银行流水"):
        debit = float(tx.get("debit", 0) or 0)
        credit = float(tx.get("credit", 0) or 0)
        return {
            "source": label,
            "ref_id": str(tx.get("transaction_serial_no", tx.get("流水号", "")))[:25] or str(tx.get("date", ""))[:10],
            "ref_label": str(tx.get("summary", tx.get("用途", tx.get("摘要", ""))))[:30],
            "amount": max(debit, credit),
            "counterparty": str(tx.get("counterparty", tx.get("对方户名", "")))[:25],
            "date": str(tx.get("date", ""))[:10],
            "note": "收入" if credit > 0 else "支出" if debit > 0 else ""
        }
    
    def _voucher_row(v, label="凭证"):
        return {
            "source": label,
            "ref_id": str(v.get("voucher_no", v.get("凭证号", "")))[:25] or "-",
            "ref_label": str(v.get("summary", v.get("摘要", "")))[:30],
            "amount": float(v.get("credit", v.get("debit", 0)) or 0),
            "counterparty": str(v.get("account_name", v.get("科目", "")))[:25],
            "date": str(v.get("entry_date", v.get("period", v.get("日期", ""))))[:10],
            "note": ""
        }
    
    def _salary_row(s, label="工资"):
        return {
            "source": label,
            "ref_id": str(s.get("姓名", s.get("name", "")))[:15] or "-",
            "ref_label": str(s.get("部门", s.get("dept", "")))[:20],
            "amount": float(s.get("实发金额", s.get("实发", s.get("amount", 0))) or 0),
            "counterparty": "",
            "date": str(s.get("period", s.get("月份", s.get("date", ""))))[:10],
            "note": ""
        }
    
    for f in all_findings:
        ftype = f.get("type", "")
        combined = ftype + " " + str(f.get("detail", "")) + " " + str(f.get("description", ""))
        evidence_rows = []
        max_rows = 8  # 每种finding最多8条证据行
        
        # ── 按finding类型采样相关原始数据 ──
        # 进销相关 → 采样销项/进项发票
        if any(kw in combined for kw in ["购销", "进销", "毛利", "有进无销", "有销无进", "数量偏差"]):
            # 按金额从大到小取top发票
            sorted_sal = sorted(sal_invs, key=lambda x: float(x.get("amount", 0) or 0), reverse=True)[:3]
            sorted_pur = sorted(pur_invs, key=lambda x: float(x.get("amount", 0) or 0), reverse=True)[:3]
            for inv in sorted_sal:
                evidence_rows.append(_inv_row(inv, "销项发票"))
            for inv in sorted_pur:
                evidence_rows.append(_inv_row(inv, "进项发票"))
        
        # 银行/资金相关 → 采样银行流水
        if any(kw in combined for kw in ["银行", "收款", "付款", "资金", "流水", "个人交易"]):
            sorted_bank = sorted(bank_txs, key=lambda x: max(float(x.get("debit",0) or 0), float(x.get("credit",0) or 0)), reverse=True)[:5]
            for tx in sorted_bank:
                evidence_rows.append(_bank_row(tx, "银行流水"))
        
        # 凭证相关 → 采样凭证
        if any(kw in combined for kw in ["凭证", "分录", "记账", "科目", "收入三源"]):
            sorted_v = sorted(vouchers, key=lambda x: float(x.get("credit", x.get("debit", 0)) or 0), reverse=True)[:5]
            for v in sorted_v:
                evidence_rows.append(_voucher_row(v, "记账凭证"))
        
        # 发票行为 → 采样可疑发票
        if any(kw in combined for kw in ["发票连号", "整十整百", "季度末", "金额分布"]):
            # 对金额整十整百的采样
            round_invs = [i for i in invoices if float(i.get("amount", 0) or 0) >= 1000 and (float(i.get("amount", 0)) % 1000 == 0 or float(i.get("amount", 0)) % 10000 == 0)]
            for inv in round_invs[:5]:
                evidence_rows.append(_inv_row(inv, "可疑发票"))
        
        # 供应商/客户相关 → 采样高频对方
        if any(kw in combined for kw in ["供应商", "客户", "集中"]):
            from collections import Counter
            counterparty_counts = Counter()
            for inv in pur_invs + sal_invs:
                cp = str(inv.get("seller", inv.get("buyer", inv.get("销方名称", inv.get("购方名称", ""))))).strip()
                if cp: counterparty_counts[cp] += 1
            for cp, cnt in counterparty_counts.most_common(5):
                evidence_rows.append({
                    "source": "交易对方",
                    "ref_id": cp[:25],
                    "ref_label": f"交易{cnt}次",
                    "amount": 0,
                    "counterparty": cp[:25],
                    "date": "",
                    "note": f"高频交易对方"
                })
        
        # 工资相关 → 采样工资记录
        if any(kw in combined for kw in ["工资", "薪金", "人员"]):
            sorted_sal = sorted(salaries, key=lambda x: float(x.get("实发金额", x.get("实发", x.get("amount", 0))) or 0), reverse=True)[:5]
            for s in sorted_sal:
                evidence_rows.append(_salary_row(s, "工资表"))
        
        # 去重（按ref_id）并限制数量
        seen = set()
        unique_rows = []
        for row in evidence_rows:
            key = (row["source"], row["ref_id"])
            if key not in seen:
                seen.add(key)
                unique_rows.append(row)
                if len(unique_rows) >= max_rows:
                    break
        
        if unique_rows:
            f["evidence_rows"] = unique_rows
    
    return all_findings


# ═══════════ 报告复核函数 ═══════════

def _detect_target_entity(bank_txs, invoices, salaries, db, company_id):
    """从银行流水/发票/工资中自动识别被分析对象"""
    from collections import Counter
    
    entity = {"name": "", "biz_model": "", "industry": "", "period": "", "bank_account": "", "source": [],
              "legal_person": "", "legal_person_role": ""}
    
    # 1. 从银行流水表头提取（账户明细/户名）→ 补充公司名称线索
    # 银行流水表头常包含"户名:XXX公司"或"账户名称:XXX"等字段
    for tx in bank_txs:
        summary = str(tx.get("summary", ""))
        if "户名" in summary or "账户名称" in summary or "Account Name" in summary:
            # 提取"户名:XXX"中的公司名称
            import re as _re_un
            m = _re_un.search(r'(?:户名|账户名称|Account Name)\s*[:：]\s*([^\s]+)', summary)
            if m:
                # 作为备选名称，但不覆盖发票交叉识别结果
                if not entity.get("_bank_account_name"):
                    entity["_bank_account_name"] = m.group(1)
    
    # 2. 交叉推断：在进项票中是购买方、在销项票中是销售方 → 分析对象
    pur_buyers = Counter()
    sal_sellers = Counter()
    for inv in invoices:
        direction = inv.get("direction", "")
        buyer = str(inv.get("buyer", inv.get("购买方名称", ""))).strip()
        seller = str(inv.get("seller", inv.get("销方名称", ""))).strip()
        if direction == "进项" and buyer and len(buyer) >= 4:
            pur_buyers[buyer] += 1
        if direction == "销项" and seller and len(seller) >= 4:
            sal_sellers[seller] += 1
    
    # 取同时出现在进项购买方和销项销售方的名称
    cross_names = set(pur_buyers.keys()) & set(sal_sellers.keys())
    if cross_names:
        best = max(cross_names, key=lambda n: pur_buyers[n] + sal_sellers[n])
        entity["name"] = best
        entity["source"].append(f"进销交叉识别(进{pur_buyers[best]}次/销{sal_sellers[best]}次)")
    
    # 回退：只用进项购买方
    if not entity["name"] and pur_buyers:
        entity["name"] = pur_buyers.most_common(1)[0][0]
        entity["source"].append(f"进项发票购买方({pur_buyers[entity['name']]}次)")
    
    # 再回退：只用销项销售方
    if not entity["name"] and sal_sellers:
        entity["name"] = sal_sellers.most_common(1)[0][0]
        entity["source"].append(f"销项发票销售方({sal_sellers[entity['name']]}次)")
    
    # 4. 从银行流水对方户名反向推断（最后的兜底）
    if not entity["name"]:
        for tx in bank_txs:
            cp = str(tx.get("counterparty", ""))
            credit = float(tx.get("credit", 0) or 0)
            if credit > 100000:  # 大额收款
                entity["name"] = cp
                entity["source"].append("银行大额收款方")
                break
    
    # 5. 推断行业类型（仅以销项发票品名为依据，不参考进项）
    goods_list = []
    for inv in invoices:
        if inv.get("direction", "") != "销项": continue
        g = str(inv.get("goods", inv.get("货物或应税劳务名称", "")))
        if g: goods_list.append(g)
    
    if goods_list:
        goods_text = " ".join(goods_list)
        industry_map = _load_industry_data().get("industry_map", {})
        # 改进行业检测：加权投票制——统计各行业命中的关键词次数，取最高分
        # 避免单一通用词（如"设备"）覆盖多个专业词（如"软件""技术"）
        from collections import Counter as _ctr
        industry_votes = _ctr()
        for kw, industry in industry_map.items():
            if kw in goods_text:
                industry_votes[industry] += 1
        if industry_votes:
            entity["industry"] = industry_votes.most_common(1)[0][0]
            entity["_industry_votes"] = dict(industry_votes.most_common(3))
    
    # 6. 提取期间范围（智能解析多种日期格式，避免硬截取Bug）
    import re as _dre
    dates = []
    def _parse_ym(dstr):
        """从各种日期格式中提取(year, month)：2025-01-01 / 2025/01/01 / 20250101 / 2025年1月1日"""
        dstr = str(dstr).strip()
        # 尝试 ISO 格式 YYYY-MM-DD 或 YYYY/MM/DD
        m = _dre.match(r'(\d{4})[-/](\d{1,2})', dstr)
        if m: return (int(m.group(1)), int(m.group(2)))
        # 尝试无分隔符 YYYYMMDD
        m = _dre.match(r'(\d{4})(\d{2})\d{2}', dstr)
        if m: return (int(m.group(1)), int(m.group(2)))
        # 尝试中文格式 YYYY年MM月
        m = _dre.match(r'(\d{4})年(\d{1,2})月', dstr)
        if m: return (int(m.group(1)), int(m.group(2)))
        return None
    for inv in invoices:
        ym = _parse_ym(inv.get("date", inv.get("开票日期", "")))
        if ym: dates.append(ym)
    for tx in bank_txs:
        ym = _parse_ym(tx.get("date", ""))
        if ym: dates.append(ym)
    if dates:
        dates.sort()
        entity["period"] = f"{dates[0][0]}-{dates[0][1]:02d} 至 {dates[-1][0]}-{dates[-1][1]:02d}"
    
    # 7. 推断经营模式（注意：不是企业类型company_type，是经营模式biz_model）
    if entity["industry"] in _load_industry_data().get("production_industries", []):
        entity["biz_model"] = "制造业"
    elif entity["industry"] in _load_industry_data().get("service_industries", []):
        entity["biz_model"] = "服务业"
    else:
        # 从进销判断：有加工费/劳务票=生产型（已修复：排除分类码*X加工品*误判）
        import re as _re_biz
        for inv in invoices:
            goods = str(inv.get("goods", ""))
            real_processing = ('加工费' in goods or 
                ('加工' in goods and not _re_biz.search(r'\*[\u4e00-\u9fa5]+加工[品物食料]\*', goods)))
            if real_processing or "劳务" in goods or "制造" in goods or "生产" in goods:
                entity["biz_model"] = "制造业"
                break
        if not entity.get("biz_model"):
            entity["biz_model"] = "贸易业"
    
    return entity


# ═══════════ 稽查方法论⑥ 联网核查 —— 上线查企业工商信息 ═══════════

# 公开企业信息查询源
_COMPANY_LOOKUP_SOURCES = [
    # 搜狗搜索 — 知识图谱卡片自动聚合企查查/天眼查/启信宝数据（HTML文本提取，无需JS）
    {
        "name": "搜狗搜索",
        "url_template": "https://www.sogou.com/web?query={company_name}",
        "parser": "sogou_kg",
    },
    # 360搜索 — 备用源
    {
        "name": "360搜索",
        "url_template": "https://www.so.com/s?q={company_name}",
        "parser": "so360",
    },
]

def _http_get(url, timeout=8, headers=None):
    """带重试的 HTTP GET，返回 (status, body_text)。headers 可选，用于 API 认证。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if headers:
        hdrs.update(headers)
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                body = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.status, body.decode(charset, errors="replace")
        except Exception as e:
            if attempt == 0:
                _time_module_inner.sleep(1)
                continue
            return None, str(e)
    return None, "timeout"


def _extract_company_from_html(html_text, source_name):
    """
    从搜索引擎HTML中提取企业信息。
    
    策略（全行业通用，不依赖特定网页结构）：
    1. 先去除<script>/<style>，再将HTML转为纯文本
    2. 用正则从纯文本中提取"字段名：值"对
    3. 搜狗/360搜索的知识图谱卡片天然是结构化纯文本，无需JS解析
    """
    if not html_text or len(html_text) < 100:
        return None
    
    # 第一步：HTML → 纯文本
    clean = re.sub(r'<script[^>]*>.*?</script>', ' ', html_text, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r'<style[^>]*>.*?</style>', ' ', clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r'<[^>]+>', ' ', clean)       # 移除所有HTML标签
    clean = re.sub(r'&nbsp;', ' ', clean)
    clean = re.sub(r'&amp;', '&', clean)
    clean = re.sub(r'&lt;', '<', clean)
    clean = re.sub(r'&gt;', '>', clean)
    clean = re.sub(r'&#?\w+;', ' ', clean)       # HTML实体
    clean = re.sub(r'\s+', ' ', clean).strip()
    
    info = {
        "source": source_name,
        "company_name": "",
        "legal_representative": "",
        "registered_capital": "",
        "established_date": "",
        "business_scope": "",
        "address": "",
        "industry": "",
        "company_type": "",
        "uscc": "",
        "status": "",
        "shareholders": [],
        "directors": [],
        "supervisors": [],
        "finance_contacts": [],
        "raw_fields": {},
    }
    
    # 第二步：逐字段正则提取
    # —— 法定代表人（优先级最高，多个结果取第一个）
    for pat in [
        r'法定代表人[：:]\s*([^\s]{2,10})(?:\s|$)',
        r'法人代表[：:]\s*([^\s]{2,10})(?:\s|$)',
    ]:
        m = re.search(pat, clean)
        if m:
            info["legal_representative"] = m.group(1).strip()
            break
    
    # —— 注册资本
    for pat in [
        r'注册资本[：:]\s*([\d.]+)\s*万(?:元)?',
        r'注册资本[：:]\s*([\d.]+万?\s*元?)',
    ]:
        m = re.search(pat, clean)
        if m:
            info["registered_capital"] = m.group(1).strip()
            break
    
    # —— 成立日期（支持多种格式）
    for pat in [
        r'(\d{4}年\d{1,2}月\d{1,2}日)\s*成立',
        r'成立日期[：:]\s*(\d{4}[-年]\d{1,2}[-月]\d{1,2})',
        r'核准日期[：:]\s*(\d{4}[-年]\d{1,2}[-月]\d{1,2})',
    ]:
        m = re.search(pat, clean)
        if m:
            info["established_date"] = m.group(1).strip()
            break
    
    # —— 登记状态
    for pat in [
        r'登记状态[：:]\s*([^\s]{2,20}?)(?:\s|$)',
        r'经营状态[：:]\s*([^\s]{2,20}?)(?:\s|$)',
    ]:
        m = re.search(pat, clean)
        if m:
            s = m.group(1).strip()
            if s not in ('', ' ', '查看', '详情'):
                info["status"] = s
                break
    
    # —— 企业/注册地址
    for pat in [
        r'企业地址[：:]\s*(.{5,80}?)(?:\s{2,}|$)',
        r'注册地址[：:]\s*(.{5,80}?)(?:\s{2,}|$)',
        r'住所[：:]\s*(.{5,80}?)(?:\s{2,}|$)',
    ]:
        m = re.search(pat, clean)
        if m:
            addr = m.group(1).strip()
            if len(addr) >= 5:
                info["address"] = addr
                break
    
    # —— 经营范围
    for pat in [
        r'经营范围[：:]\s*(.{10,500}?)(?:\s{2,}|行业分类|工商信息)',
    ]:
        m = re.search(pat, clean)
        if m:
            scope = m.group(1).strip()
            if len(scope) >= 10:
                info["business_scope"] = scope[:500]
                break
    
    # —— 统一社会信用代码（18位数字+字母）
    m = re.search(r'统一社会信用代码[：:]\s*([A-Za-z0-9]{18})', clean)
    if m:
        info["uscc"] = m.group(1).strip()
    
    # —— 企业类型
    m = re.search(r'企业类型[：:]\s*([^\s]{4,30}?)(?:\s|$)', clean)
    if m:
        t = m.group(1).strip()
        if t not in ('', ' ', '查看'):
            info["company_type"] = t
    
    # —— 六员信息提取（稽查核心：法定代表人/董事/监事/财务负责人/股东/经理）
    # 搜狗知识图谱格式: "X位相关人员 更多 张三 执行董事,经理,财务负责人 李四 监事"
    # 策略：①提取"姓名 角色列表"对 ②按角色分类 ③保存到对应字段
    directors_map = {}      # {name: [roles]}
    supervisors_map = {}    # {name: [roles]}
    finance_map = {}        # {name: [roles]}
    all_personnel = set()   # 所有出现的人名（去重后作为股东候选）
    
    sh_block = re.search(r'(\d{1,2}位相关人员.*?)(?:工商信息|股东信息|变更记录|\Z)', clean)
    if sh_block:
        block = sh_block.group(1)
        # 模式: "姓名(2-4字) 角色列表(逗号分隔)"
        pairs = re.findall(r'([\u4e00-\u9fff]{2,4})\s+([\u4e00-\u9fff,、；;]+)(?=\s|$)', block)
        for name, roles_str in pairs:
            name = name.strip()
            # 过滤噪声词
            if name in ('更多', '工商信息', '股东信息', '变更记录', '财务信息', '查看', '详情'):
                continue
            # 拆分角色
            roles = [r.strip() for r in re.split(r'[,，、;；]', roles_str) if r.strip()]
            roles_lower = [r for r in roles if r and len(r) <= 8]  # 过滤超长噪声
            
            if not roles_lower:
                continue
            
            all_personnel.add(name)
            
            # 角色分类
            for role in roles_lower:
                if any(kw in role for kw in ('董事', '执行董事')):
                    if name not in directors_map:
                        directors_map[name] = []
                    directors_map[name].extend(roles_lower)
                if any(kw in role for kw in ('监事',)):
                    if name not in supervisors_map:
                        supervisors_map[name] = []
                    supervisors_map[name].extend(roles_lower)
                if any(kw in role for kw in ('财务负责人', '财务')):
                    if name not in finance_map:
                        finance_map[name] = []
                    finance_map[name].extend(roles_lower)
            # 如果角色包含"法定代表人"，记录为legal_representative候选
            if not info["legal_representative"] and any('法定代表人' in r for r in roles_lower):
                info["legal_representative"] = name
    
    # 从整个文本提取 "XXX - 法定代表人/高管/股东" 模式（天眼查摘要）
    for m in re.finditer(r'([\u4e00-\u9fff]{2,4})\s*[-—]\s*法定代表人[/]?高管[/]?股东', clean):
        name = m.group(1).strip()
        all_personnel.add(name)
    
    # 填充结果
    info["directors"] = [{"name": n, "roles": ",".join(set(r))} for n, r in directors_map.items()]
    info["supervisors"] = [{"name": n, "roles": ",".join(set(r))} for n, r in supervisors_map.items()]
    info["finance_contacts"] = [{"name": n, "roles": ",".join(set(r))} for n, r in finance_map.items()]
    # 股东 = 所有出现的人（包括未分类进董事/监事/财务的）
    for name in all_personnel:
        if name not in [s["name"] for s in info["shareholders"]]:
            info["shareholders"].append({"name": name})
    
    # 第三步：验证 — 至少要有法定代表人 or 注册资本才算有效提取
    if not info["legal_representative"] and not info["registered_capital"]:
        return None
    
    return info


# ═══════════════ 天眼查 / 企查查 API 集成 ═══════════════
# 配置优先级：环境变量 → 配置文件 → 搜索引擎兜底
# 天眼查开放平台: https://open.tianyancha.com
# 企查查开放平台: https://openapi.qcc.com

def _load_api_config():
    """加载天眼查/企查查 API 配置。完全防崩，出错返回空配置。"""
    config = {"tyc_appkey": "", "tyc_token": "", "qcc_appkey": "", "qcc_secret_key": ""}
    try:
        # 环境变量优先
        for k in config:
            env_val = os.environ.get(k.upper(), "")
            if env_val:
                config[k] = env_val
        # 配置文件兜底
        cfg_path = os.path.join(_PROJECT_ROOT, "api_config.json")
        if os.path.exists(cfg_path) and os.path.getsize(cfg_path) > 2:
            content = None
            # 尝试 UTF-8
            try:
                with open(cfg_path, "rb") as f:
                    raw = f.read()
                content = raw.decode("utf-8")
            except:
                # 尝试 GBK
                try:
                    content = raw.decode("gbk")
                except:
                    pass
            if content:
                cfg_json = json.loads(content)
                for k in config:
                    if not config[k] and cfg_json.get(k):
                        config[k] = cfg_json[k]
    except:
        pass
    return config

def _try_tyc_api(company_name):
    """天眼查工商信息查询。需要 TYC_APPKEY + TYC_TOKEN 环境变量或 api_config.json"""
    cfg = _load_api_config()
    if not cfg["tyc_appkey"] or not cfg["tyc_token"]:
        return None
    try:
        import time, hashlib
        ts = str(int(time.time()))
        sign_str = cfg["tyc_appkey"] + ts + cfg["tyc_token"]
        sign = hashlib.sha1(sign_str.encode()).hexdigest()
        headers = {
            "Authorization": f"Bearer {cfg['tyc_token']}",
            "appkey": cfg["tyc_appkey"],
            "timestamp": ts,
            "sign": sign,
        }
        url = f"https://open.api.tianyancha.com/services/open/company/baseinfo?keyword={urllib.parse.quote(company_name)}"
        status, body = _http_get(url, timeout=8, headers=headers)
        if status == 200 and body:
            data = json.loads(body)
            if data.get("error_code") == 0 and data.get("result"):
                r = data["result"]
                return {
                    "success": True,
                    "data": {
                        "source": "天眼查",
                        "company_name": r.get("name", company_name),
                        "legal_representative": r.get("legalPersonName", ""),
                        "registered_capital": str(r.get("regCapital", "")),
                        "established_date": r.get("estiblishTime", ""),
                        "business_scope": r.get("businessScope", ""),
                        "address": r.get("regLocation", ""),
                        "industry": r.get("industry", {}).get("category", "") if isinstance(r.get("industry"), dict) else "",
                        "company_type": r.get("companyOrgType", ""),
                        "uscc": r.get("creditCode", ""),
                        "status": r.get("regStatus", ""),
                        "shareholders": [{"name": s.get("name", ""), "ratio": str(s.get("percentTotal", ""))} for s in r.get("holders", [])],
                        "directors": [{"name": d.get("name", ""), "roles": d.get("type", "")} for d in r.get("staffList", []) if "董事" in (d.get("type", "") or "")],
                        "supervisors": [{"name": d.get("name", ""), "roles": d.get("type", "")} for d in r.get("staffList", []) if "监事" in (d.get("type", "") or "")],
                        "finance_contacts": [],
                    }
                }
    except:
        pass
    return None

def _try_qcc_api(company_name):
    """企查查工商信息查询。需要 QCC_APPKEY + QCC_SECRET_KEY 环境变量或 api_config.json"""
    cfg = _load_api_config()
    if not cfg["qcc_appkey"] or not cfg["qcc_secret_key"]:
        return None
    try:
        import time, hashlib
        ts = str(int(time.time()))
        sign_str = cfg["qcc_appkey"] + ts + cfg["qcc_secret_key"]
        sign = hashlib.sha256(sign_str.encode()).hexdigest()
        headers = {
            "AppKey": cfg["qcc_appkey"],
            "Timestamp": ts,
            "Sign": sign,
        }
        url = f"https://api.qcc.com/Company/GetCompanyDetail?key={urllib.parse.quote(company_name)}"
        status, body = _http_get(url, timeout=8, headers=headers)
        if status == 200 and body:
            data = json.loads(body)
            if data.get("Status") == "200" and data.get("Result"):
                r = data["Result"]
                return {
                    "success": True,
                    "data": {
                        "source": "企查查",
                        "company_name": r.get("CompanyName", company_name),
                        "legal_representative": r.get("OperName", ""),
                        "registered_capital": str(r.get("RegistCapi", "")),
                        "established_date": r.get("StartDate", ""),
                        "business_scope": r.get("Scope", ""),
                        "address": r.get("Address", ""),
                        "industry": r.get("Industry", {}).get("Industry", "") if isinstance(r.get("Industry"), dict) else "",
                        "company_type": r.get("CompanyType", ""),
                        "uscc": r.get("CreditCode", ""),
                        "status": r.get("Status", ""),
                        "shareholders": [],
                        "directors": [],
                        "supervisors": [],
                        "finance_contacts": [],
                    }
                }
    except:
        pass
    return None


def _online_company_lookup(company_name, uscc=None, db=None, company_id=None):
    """
    联网查询企业工商信息 —— 稽查方法论⑥核心实现
    
    策略：
    1. 如果数据库已有完整信息 → 直接返回（避免重复查询）
    2. 尝试多个公开数据源 → 提取结构化信息
    3. 优先天眼查/企查查，次选国家公示系统
    4. 返回结构化结果并更新数据库Company表
    
    Args:
        company_name: 企业全称
        uscc: 统一社会信用代码（可选，有则精确匹配）
        db: SQLAlchemy Session（用于查询和更新数据库）
        company_id: 公司ID
    
    Returns:
        dict: {company_name, legal_rep, registered_capital, industry, shareholders, ...}
    """
    if not company_name or len(company_name) < 4:
        return {"success": False, "reason": "企业名称过短或为空", "company_name": company_name}
    
    result = {
        "success": False,
        "company_name": company_name,
        "legal_representative": "",
        "legal_rep_id": "",
        "registered_capital": "",
        "established_date": "",
        "business_scope": "",
        "address": "",
        "industry": "",
        "company_type": "",
        "uscc": uscc or "",
        "status": "",
        "shareholders": [],
        "directors": [],
        "supervisors": [],
        "finance_contacts": [],
        "source": "",
        "lookup_time": datetime.now().isoformat(),
        "raw_data": None,
    }
    
    # 第一步：检查数据库是否已有完整信息（避免重复联网查询）
    # 验证DB中的公司名与查询名一致，防止A公司的数据错误关联到B公司
    if db and company_id:
        try:
            company = db.query(Company).filter(Company.id == company_id).first()
            if company and company.name == company_name:  # 名实相符才用缓存
                # 判断是否已经有足够的信息
                has_basic = bool(company.legal_representative and company.registered_capital)
                has_scope = bool(company.business_scope and len(company.business_scope or "") > 20)
                if has_basic and has_scope:
                    # 数据库已有基本信息 + 经营范围，直接返回
                    result["success"] = True
                    result["legal_representative"] = company.legal_representative or ""
                    result["registered_capital"] = str(company.registered_capital or "")
                    result["established_date"] = str(company.established_date or "")
                    result["business_scope"] = company.business_scope or ""
                    result["address"] = company.address or ""
                    result["company_type"] = company.company_type or ""
                    result["uscc"] = company.uscc or (uscc or "")
                    result["industry"] = company.industry_code or ""
                    result["source"] = "数据库缓存"
                    # 查股东
                    try:
                        from database import CompanyShareholder
                        shs = db.query(CompanyShareholder).filter(
                            CompanyShareholder.company_id == company_id
                        ).all()
                        result["shareholders"] = [
                            {"name": s.name, "ratio": str(s.share_ratio or ""), "amount": str(s.amount or "")}
                            for s in shs
                        ]
                    except:
                        pass
                    return result
        except Exception as e:
            pass  # 数据库查询失败，继续联网
    
    # 第二步：联网查询
    online_info = None
    
    # URL编码公司名称
    encoded_name = urllib.parse.quote(company_name)
    
    # ── 2a. 优先天眼查 API（精确、实时、覆盖全量企业）──
    try:
        tyc_result = _try_tyc_api(company_name)
    except Exception:
        tyc_result = None
    if tyc_result and tyc_result.get("success"):
        online_info = tyc_result["data"]
        online_info["source_url"] = f"天眼查API: {company_name}"
        result["source"] = "天眼查API"
    
    # ── 2b. 企查查 API ──
    if not online_info:
        try:
            qcc_result = _try_qcc_api(company_name)
        except Exception:
            qcc_result = None
        if qcc_result and qcc_result.get("success"):
            online_info = qcc_result["data"]
            online_info["source_url"] = f"企查查API: {company_name}"
            result["source"] = "企查查API"
    
    # ── 2c. 搜索引擎兜底 ──
    if not online_info:
        for src in _COMPANY_LOOKUP_SOURCES:
            try:
                url = src["url_template"].format(company_name=encoded_name)
                status, body = _http_get(url, timeout=10)
                if status and body and status == 200:
                    info = _extract_company_from_html(body, src["name"])
                    if info and (info.get("legal_representative") or info.get("registered_capital") or info.get("uscc")):
                        online_info = info
                        online_info["source_url"] = url
                        online_info["_raw_html"] = body
                        result["source"] = f"联网查询({src['name']})"
                        break
            except Exception:
                continue
    
    # 第三步：合并结果
    if online_info:
        result["success"] = True
        result["legal_representative"] = online_info.get("legal_representative", "")
        result["registered_capital"] = online_info.get("registered_capital", "")
        result["established_date"] = online_info.get("established_date", "")
        result["business_scope"] = online_info.get("business_scope", "")
        result["address"] = online_info.get("address", "")
        result["uscc"] = online_info.get("uscc", "") or (uscc or "")
        result["status"] = online_info.get("status", "")
        result["company_type"] = online_info.get("company_type", "")
        result["directors"] = online_info.get("directors", [])
        result["supervisors"] = online_info.get("supervisors", [])
        result["finance_contacts"] = online_info.get("finance_contacts", [])
        result["_raw_html"] = online_info.get("_raw_html", "")  # 历史任期核查用
        result["raw_data"] = online_info
        
        # 从经营范围推断行业
        if result["business_scope"]:
            from audit_enhancements import detect_industry as _detect_ind
            try:
                result["industry"] = _detect_ind(result["business_scope"])
            except:
                pass
    
    # 第四步：更新数据库（持久化）
    if result["success"] and db and company_id:
        try:
            company = db.query(Company).filter(Company.id == company_id).first()
            if company:
                updated = False
                if result["legal_representative"] and not company.legal_representative:
                    company.legal_representative = result["legal_representative"]
                    updated = True
                if result["registered_capital"] and not company.registered_capital:
                    # 尝试解析金额
                    cap_str = result["registered_capital"]
                    cap_num = re.sub(r'[^\d.]', '', cap_str)
                    if cap_num:
                        try:
                            company.registered_capital = float(cap_num)
                            updated = True
                        except:
                            pass
                if result["business_scope"] and (not company.business_scope or len(company.business_scope or "") < 10):
                    company.business_scope = result["business_scope"]
                    updated = True
                if result["address"] and not company.address:
                    company.address = result["address"]
                    updated = True
                if result["industry"] and not company.industry_code:
                    company.industry_code = result["industry"]
                    updated = True
                if result["established_date"] and not company.established_date:
                    try:
                        date_str = result["established_date"].replace("年", "-").replace("月", "-").replace("日", "")
                        from datetime import date as _date
                        company.established_date = _date.fromisoformat(date_str[:10])
                        updated = True
                    except:
                        pass
                if updated:
                    db.commit()
                    result["_db_updated"] = True
                
                # 保存六员信息到子表（稽查六员风险数据基础）
                # 董事
                if result["directors"]:
                    existing_dirs = {d.name for d in (company.directors or [])}
                    for d in result["directors"]:
                        if d["name"] not in existing_dirs:
                            try:
                                from database import CompanyDirector
                                db.add(CompanyDirector(company_id=company_id, name=d["name"]))
                            except:
                                pass
                # 监事
                if result["supervisors"]:
                    existing_sups = {s.name for s in (company.supervisors or [])}
                    for s in result["supervisors"]:
                        if s["name"] not in existing_sups:
                            try:
                                from database import CompanySupervisor
                                db.add(CompanySupervisor(company_id=company_id, name=s["name"]))
                            except:
                                pass
                # 财务负责人
                if result["finance_contacts"]:
                    existing_fcs = {f.name for f in (company.finance_contacts or [])}
                    for fc in result["finance_contacts"]:
                        if fc["name"] not in existing_fcs:
                            try:
                                from database import CompanyFinanceContact
                                db.add(CompanyFinanceContact(company_id=company_id, name=fc["name"]))
                            except:
                                pass
                if result["directors"] or result["supervisors"] or result["finance_contacts"]:
                    db.commit()
        except Exception as e:
            result["_db_error"] = str(e)
    
    return result


def _check_six_personnel_risk(db, company_id):
    """
    稽查六员风险检测 —— 跨企业人员交叉比对
    
    检测：
    1. 一人多角：同一人在本公司同时担任多个关键角色（内控缺陷）
    2. 跨企兼任：本公司的六员是否同时在其他企业任职（关联关系）
    
    Returns:
        dict: {
            "one_person_multi_role": [...],  # 一人多角色警告
            "cross_company_overlap": [...],   # 跨企业人员重叠
            "total_companies_checked": int
        }
    """
    from database import (Company as _C, CompanyDirector as _CD, CompanySupervisor as _CS,
                          CompanyFinanceContact as _FC, CompanyShareholder as _SH)
    
    company = db.query(_C).filter(_C.id == company_id).first()
    if not company:
        return {"one_person_multi_role": [], "cross_company_overlap": [], "total_companies_checked": 0}
    
    # 收集本企业所有六员
    my_personnel = {}  # {name: [role_list]}
    
    if company.legal_representative:
        my_personnel.setdefault(company.legal_representative, []).append("法定代表人")
    
    for sh in (company.shareholders or []):
        my_personnel.setdefault(sh.name, []).append("股东")
    
    for d in (company.directors or []):
        my_personnel.setdefault(d.name, []).append("董事")
    
    for s in (company.supervisors or []):
        my_personnel.setdefault(s.name, []).append("监事")
    
    for fc in (company.finance_contacts or []):
        my_personnel.setdefault(fc.name, []).append("财务负责人")
    
    # 检测1: 一人多角（≥3个不同角色 = 内控缺陷）
    multi_role = []
    for name, roles in my_personnel.items():
        unique_roles = list(set(roles))
        if len(unique_roles) >= 3:
            multi_role.append({"name": name, "roles": unique_roles, "count": len(unique_roles)})
    
    # 检测2: 跨企业人员交叉比对
    cross_company = []
    all_companies = db.query(_C).filter(_C.id != company_id).all()
    
    for other in all_companies:
        overlap = []
        for my_name, my_roles in my_personnel.items():
            # 检查此人是否在对方企业出现
            is_in_other = False
            other_roles = []
            
            if other.legal_representative == my_name:
                is_in_other = True
                other_roles.append("法定代表人")
            
            for sh in (other.shareholders or []):
                if sh.name == my_name:
                    is_in_other = True
                    other_roles.append("股东")
                    break
            
            for d in (other.directors or []):
                if d.name == my_name:
                    is_in_other = True
                    other_roles.append("董事")
                    break
            
            for s in (other.supervisors or []):
                if s.name == my_name:
                    is_in_other = True
                    other_roles.append("监事")
                    break
            
            for fc in (other.finance_contacts or []):
                if fc.name == my_name:
                    is_in_other = True
                    other_roles.append("财务负责人")
                    break
            
            if is_in_other:
                overlap.append({
                    "name": my_name,
                    "my_roles": list(set(my_roles)),
                    "other_company": other.name,
                    "other_roles": other_roles
                })
        
        if overlap:
            cross_company.append({
                "other_company": other.name,
                "other_company_id": other.id,
                "overlap_personnel": overlap
            })
    
    return {
        "one_person_multi_role": multi_role,
        "cross_company_overlap": cross_company,
        "total_companies_checked": len(all_companies),
        "my_personnel": {name: list(set(roles)) for name, roles in my_personnel.items()}
    }


def _lookup_supply_chain(db, company_id, target_entity, sal_invs, pur_invs):
    """
    供应链联网核查 —— 稽查方法论核心扩展
    
    步骤：
    1. 提取进项TOP供应商（按金额排序）和销项TOP客户
    2. 对每个供应商/客户执行联网核查
    3. 检测供应商/客户与本企业的六员重叠（关联交易信号）
    4. 检测供应商与客户是否同一企业（购销闭环=虚开嫌疑）
    
    Returns:
        dict: {lookup_results: [...], findings: [...], supply_personnel_map: {...}}
    """
    from collections import defaultdict
    
    results = {"lookup_results": [], "findings": [], "supply_personnel_map": {}}
    
    if not target_entity.get("name"):
        return results
    
    target_name = target_entity["name"]
    my_personnel = target_entity.get("_six_personnel_risk", {}).get("my_personnel", {})
    
    # 收集本企业六员姓名集合
    my_names = set(my_personnel.keys())
    if target_entity.get("legal_representative"):
        my_names.add(target_entity["legal_representative"])
    
    # ========== Step 1: 提取供应商/客户 ==========
    # 进项→供应商
    supplier_amounts = defaultdict(float)
    supplier_invs = defaultdict(list)
    for inv in (pur_invs or []):
        sname = str(inv.get("seller", inv.get("销方名称", inv.get("supplier", "")))).strip()
        if not sname or len(sname) < 4 or sname == target_name:
            continue
        amt = float(inv.get("amount", inv.get("金额", 0)) or 0)
        supplier_amounts[sname] += amt
        supplier_invs[sname].append(inv)
    
    # 销项→客户
    customer_amounts = defaultdict(float)
    customer_invs = defaultdict(list)
    for inv in (sal_invs or []):
        cname = str(inv.get("buyer", inv.get("购买方名称", inv.get("customer", "")))).strip()
        if not cname or len(cname) < 4 or cname == target_name:
            continue
        amt = float(inv.get("amount", inv.get("金额", 0)) or 0)
        customer_amounts[cname] += amt
        customer_invs[cname].append(inv)
    
    # TOP N（按金额排序，最多10家）
    top_suppliers = sorted(supplier_amounts.items(), key=lambda x: x[1], reverse=True)[:10]
    top_customers = sorted(customer_amounts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # ========== Step 2: 联网核查供应商/客户 ==========
    # 先查本企业的人员名单（从数据库获取）
    from database import Company as _C2
    company = db.query(_C2).filter(_C2.id == company_id).first()
    
    def _collect_personnel(comp):
        """收集企业的六员姓名集合+角色"""
        names = set()
        roles = {}
        if comp.legal_representative:
            names.add(comp.legal_representative)
            roles[comp.legal_representative] = "法定代表人"
        for sh in (comp.shareholders or []):
            names.add(sh.name)
            roles[sh.name] = "股东"
        for d in (comp.directors or []):
            names.add(d.name)
            roles[d.name] = "董事"
        for s in (comp.supervisors or []):
            names.add(s.name)
            roles[s.name] = "监事"
        for fc in (comp.finance_contacts or []):
            names.add(fc.name)
            roles[fc.name] = "财务负责人"
        return names, roles
    
    my_all_names, my_roles = _collect_personnel(company) if company else (my_names, {n: "未知" for n in my_names})
    my_roles_full = {}
    for n in my_all_names:
        my_roles_full[n] = my_roles.get(n, "相关人员")
    
    # 合并查找所有需要查询的企业名（去重，排除本企业）
    to_lookup = set()
    lookup_map = {}  # {company_name: type}  — 记录是供应商还是客户
    lookup_amt = {}
    
    for sname, samt in top_suppliers:
        if sname not in to_lookup and sname != target_name:
            to_lookup.add(sname)
            lookup_map[sname] = "供应商"
            lookup_amt[sname] = samt
    for cname, camt in top_customers:
        if cname not in to_lookup:
            to_lookup.add(cname)
            lookup_map[cname] = "客户"
            lookup_amt[cname] = camt
        elif lookup_map.get(cname) == "供应商":
            lookup_map[cname] = "供应商+客户"  # 同一个企业既是供应商又是客户→购销闭环
    
    lookup_count = 0
    for name_to_check in to_lookup:
        try:
            lk = _online_company_lookup(name_to_check, db=db)
            if lk.get("success"):
                results["lookup_results"].append({
                    "name": name_to_check,
                    "relation": lookup_map.get(name_to_check, ""),
                    "amount": lookup_amt.get(name_to_check, 0),
                    "legal_rep": lk.get("legal_representative", ""),
                    "status": lk.get("status", ""),
                    "address": lk.get("address", ""),
                    "_raw_html": lk.get("_raw_html", ""),
                })
                lookup_count += 1
                
                # 收集该企业的人员
                their_names = set()
                their_roles = {}
                if lk.get("legal_representative"):
                    their_names.add(lk["legal_representative"])
                    their_roles[lk["legal_representative"]] = "法定代表人"
                for s in (lk.get("shareholders") or []):
                    their_names.add(s.get("name", ""))
                    their_roles[s.get("name", "")] = "股东"
                for d in (lk.get("directors") or []):
                    their_names.add(d.get("name", ""))
                    their_roles[d.get("name", "")] = "董事"
                for s in (lk.get("supervisors") or []):
                    their_names.add(s.get("name", ""))
                    their_roles[s.get("name", "")] = "监事"
                for fc in (lk.get("finance_contacts") or []):
                    their_names.add(fc.get("name", ""))
                    their_roles[fc.get("name", "")] = "财务负责人"
                
                results["supply_personnel_map"][name_to_check] = {
                    "their_names": their_names,
                    "their_roles": their_roles
                }
        except:
            continue
    
    # ========== Step 3: 六员交叉比对 ==========
    # 检测：供应商/客户与本企业有无人员重叠
    for lr in results["lookup_results"]:
        sname = lr["name"]
        their_info = results["supply_personnel_map"].get(sname, {})
        their_names = their_info.get("their_names", set())
        their_roles_map = their_info.get("their_roles", {})
        
        overlap = my_all_names & their_names
        if overlap:
            relation = lr["relation"]
            # 生成风险发现
            overlap_details = []
            for name in overlap:
                my_r = my_roles_full.get(name, "相关人员")
                their_r = their_roles_map.get(name, "相关人员")
                overlap_details.append(f"{name}（我方{my_r} / {relation}{their_r}）")
            
            is_both = (relation == "供应商+客户")
            
            findings_entry = {
                "type": "供应商/客户六员重叠风险",
                "level": "高风险" if is_both else "中风险",
                "score": 9 if is_both else 7,
                "detail": f"{relation}{sname}与本企业存在人员重叠：{'、'.join(overlap_details)}。疑似关联方交易。",
                "description": (
                    f"通过联网核查，发现{relation}{sname}（交易金额{lr['amount']:,.2f}元）与本企业{target_name}存在人员重叠——"
                    f"{'、'.join(overlap_details)}。"
                    f"根据《企业所得税法》第四十一条及《特别纳税调整实施办法》，"
                    f"双方构成关联关系，交易属于关联交易。"
                    + (f"该企业同时作为供应商和客户，形成购销闭环，虚开发票嫌疑增大。" if is_both else "")
                ),
                "how_found": (
                    f"①从进销发票中提取{relation}名称（{'进项' if '供应商' in relation else '销项'}发票中金额TOP对象）；"
                    f"②通过搜索引擎知识图谱联网核查{relation}的六员信息；"
                    f"③将{relation}的六员名单与本企业{target_name}的六员名单逐名交叉比对——发现{len(overlap)}人重叠。"
                ),
                "tax_impact": (
                    "关联交易需按独立交易原则调整。若未按公允价值交易，需补缴企业所得税+滞纳金；"
                    "如涉及虚开发票（购销闭环+人员重叠+无真实货物交易），移送公安。"
                ),
                "policy_ref": (
                    "《企业所得税法》第四十一条（独立交易原则）；"
                    "《特别纳税调整实施办法（试行）》第九条（关联关系认定）；"
                    "《税收征收管理法》第三十六条（关联企业业务往来）；"
                    "《发票管理办法》第二十二条（虚开发票认定）"
                ),
                "suggestion": (
                    f"①提供与{sname}的全部交易合同、物流单据、资金流水，证明交易真实性；"
                    f"②提供关联交易定价依据（市场比价/成本加成），证明符合独立交易原则；"
                    f"③若{sname}同时为供应商和客户，需提供购销闭环的商业合理性说明；"
                    f"④编制关联交易申报表（年度企业所得税汇算清缴附件）。"
                ),
                "category": "关联交易",
                "rule_id": 1510,
                "source_chain": "供应链-六员重叠",
                "cross_domain": True,
                "cross_domains": ["人员信息", "发票数据", "资金流"],
                "supply_name": sname,
                "overlap_count": len(overlap),
            }
            results["findings"].append(findings_entry)
    
    # ========== Step 3.5: 历史任期核查（深度关联检测） ==========
    # 即使当前六员名册无重叠，也要在联网查询的原始文本中搜索本企业人员姓名
    # 发现历史关联（曾任董监高/股东/法定代表人）→ 说明存在历史关联关系
    historical_findings = []
    for lr in results["lookup_results"]:
        sname = lr["name"]
        raw_html = lr.get("_raw_html", "")
        if not raw_html or len(raw_html) < 100:
            continue
        
        # 在供应商/客户查询结果中搜索本企业六员姓名
        historical_overlap = []
        for name in my_all_names:
            if not name or len(name) < 2:
                continue
            # 排除已在当前名册中检测到的重叠（避免重复报）
            their_names = results["supply_personnel_map"].get(sname, {}).get("their_names", set())
            if name in their_names:
                continue
            # 在原始HTML文本中搜索该姓名
            if name in raw_html:
                my_r = my_roles_full.get(name, "相关人员")
                historical_overlap.append(f"{name}（我方{my_r}）")
        
        if historical_overlap:
            relation = lr["relation"]
            historical_findings.append({
                "type": "历史任期关联风险（深度核查）",
                "level": "中风险",
                "score": 6,
                "detail": (
                    f"联网核查发现，{relation}{sname}（交易金额{lr['amount']:,.2f}元）"
                    f"的工商信息页面中包含本企业{target_name}的人员姓名：{'、'.join(historical_overlap)}。"
                    f"虽然该人员当前不在{sname}的董监高/法定代表人正式名册中，"
                    f"但搜索引擎知识图谱中存在历史关联记录，"
                    f"表明其可能曾在该企业任职或存在其他历史业务联系。"
                ),
                "description": (
                    f"通过对{relation}{sname}的联网查询原始数据进行深度检索，"
                    f"在半结构化工商信息文本中发现了本企业人员的姓名痕迹。"
                    f"搜索引擎知识图谱通常包含变更记录、历史任职、新闻报道、司法文书等信息，"
                    f"即使当前六员名册已不包含该人员，其出现在搜索结果中也意味着可能的关联关系。"
                    f"需结合资金流水、交易合同、物流单据等交叉验证。"
                ),
                "how_found": (
                    f"①从进销发票提取{relation}名称→联网查询→获取原始工商信息文本；"
                    f"②在原始文本中逐名搜索本企业{target_name}的六员姓名；"
                    f"③排除当前名册重叠（已在Step3中处理），聚焦历史关联→发现{len(historical_overlap)}条痕迹。"
                ),
                "tax_impact": (
                    "若历史关联属实（曾任职/曾持股/亲属关系/业务代理），"
                    "当前交易可能构成关联交易，需按独立交易原则调整；"
                    "若历史关联配合异常资金流（无商业实质的回流），需进一步核查虚开发票风险。"
                ),
                "policy_ref": (
                    "《企业所得税法》第四十一条（独立交易原则）；"
                    "《特别纳税调整实施办法（试行）》第九条（关联关系认定——"
                    "包括曾任董监高/持股25%以上/亲属关系/业务控制等情形）；"
                    "国家税务总局公告2016年第42号（关联交易申报）"
                ),
                "suggestion": (
                    f"①核实{historical_overlap[0].split('（')[0] if historical_overlap else ''}与{sname}的历史关联性质（曾任职务/亲属/代理）；"
                    f"②比对与{sname}的交易定价是否与市场第三方价格相符；"
                    f"③核查与{sname}的资金往来是否存在回流或异常；"
                    f"④如确认关联交易，要求补充关联交易申报表。"
                ),
                "category": "关联交易",
                "rule_id": 1512,
                "source_chain": "供应链-历史任期深度核查",
                "cross_domain": True,
                "cross_domains": ["人员信息", "发票数据", "资金流", "搜索引擎数据"],
                "supply_name": sname,
                "overlap_count": len(historical_overlap),
            })
    
    if historical_findings:
        results["findings"].extend(historical_findings)
    
    # ========== Step 4: 供应商=客户 检测（购销闭环） ==========
    for lr in results["lookup_results"]:
        if lr["relation"] == "供应商+客户":
            # 已经在上面的重叠检测中处理了
            pass
    
    # 简单检测：从发票数据中找供应商=客户
    supplier_names = {s[0] for s in top_suppliers}
    customer_names = {c[0] for c in top_customers}
    both_set = supplier_names & customer_names
    for name in both_set:
        # 检查是否已经生成了finding
        already_found = any(f.get("supply_name") == name for f in results["findings"])
        if not already_found:
            results["findings"].append({
                "type": "购销闭环风险",
                "level": "高风险",
                "score": 9,
                "detail": f"企业{name}同时作为本企业的供应商（交易{supplier_amounts[name]:,.2f}元）和客户（交易{customer_amounts[name]:,.2f}元），形成购销闭环，存在虚开发票嫌疑。",
                "description": f"从发票数据发现，{name}既是本企业的供应商（进项金额{supplier_amounts[name]:,.2f}元）又是客户（销项金额{customer_amounts[name]:,.2f}元），构成'A→B→A'式的购销闭环。这种模式下，发票在关联方之间循环流转，极易被用于虚开增值税发票——无真实货物交易，仅为增大进销金额、虚增业绩或骗取出口退税。",
                "how_found": f"逐票比对进项发票的销售方名称和销项发票的购买方名称，交叉发现{name}既出现在进项侧又出现在销项侧。",
                "tax_impact": "如无真实货物交易，构成虚开增值税发票→补税+罚款+刑事责任。即使有真实交易，也需按关联交易申报。",
                "policy_ref": "《发票管理办法》第二十二条（虚开发票认定）；《刑法》第二百零五条（虚开增值税专用发票罪）",
                "suggestion": f"①提供与{name}的全部购销合同、物流单据、出入库记录；②说明双方互为供应商和客户的商业合理性；③核查资金流是否与发票流一一对应。",
                "category": "关联交易",
                "rule_id": 1511,
                "source_chain": "供应链-购销闭环",
                "cross_domain": True,
                "cross_domains": ["发票数据", "进销存"],
                "supply_name": name,
            })
    
    return results


def _enrich_target_entity_from_online(target_entity, db, company_id):
    """
    将联网查询结果注入 target_entity —— 在 _run_analyze 管道中调用
    
    增强项：
    - legal_representative → 用于判断个人打款性质
    - registered_capital → 用于判断经营规模
    - business_scope → 用于行业比对
    - shareholders → 用于关联交易判断
    - industry → 覆盖发票关键词推断结果（更准确）
    """
    if not target_entity.get("name"):
        return target_entity
    
    company_name = target_entity["name"]
    lookup = _online_company_lookup(company_name, db=db, company_id=company_id)
    
    if lookup.get("success"):
        target_entity["_online_lookup"] = True
        target_entity["legal_representative"] = lookup.get("legal_representative", "")
        target_entity["legal_person"] = target_entity["legal_representative"]
        target_entity["legal_person_role"] = lookup.get("legal_person_role", "") or (target_entity.get("legal_person_role", ""))
        target_entity["registered_capital"] = lookup.get("registered_capital", "")
        target_entity["established_date"] = lookup.get("established_date", "")
        target_entity["business_scope"] = lookup.get("business_scope", "")
        target_entity["address"] = lookup.get("address", "")
        target_entity["company_type"] = lookup.get("company_type", "")
        target_entity["uscc"] = lookup.get("uscc", "")
        target_entity["shareholders"] = lookup.get("shareholders", [])
        target_entity["directors"] = lookup.get("directors", [])
        target_entity["supervisors"] = lookup.get("supervisors", [])
        target_entity["finance_contacts"] = lookup.get("finance_contacts", [])
        target_entity["lookup_source"] = lookup.get("source", "")
    else:
        pipeline_log.append(f"联网核查未成功，六员信息从本地数据库获取")
    
    # 稽查六员风险检测——不依赖联网核查结果，从本地DB读取
    try:
        six_risk = _check_six_personnel_risk(db, company_id)
        target_entity["_six_personnel_risk"] = six_risk
        # 本地六员数据可用即启用供应链核查
        if not target_entity.get("_online_lookup"):
            target_entity["_online_lookup"] = True
            pipeline_log.append("六员比对已启用（基于本地数据库+发票交易对方）")
    except Exception as _sx_err:
        pipeline_log.append(f"六员比对跳过: {_sx_err}")
    
    # 联网查询未获取六员数据时，从DB已有数据回填
    if not target_entity.get("directors") or not target_entity.get("supervisors") or not target_entity.get("finance_contacts"):
        try:
                from database import Company as _C2
                _c = db.query(_C2).filter(_C2.id == company_id, _C2.name == company_name).first()
                if _c:
                    if not target_entity["directors"]:
                        target_entity["directors"] = [{"name": d.name, "id_number": d.id_number or ""} for d in (_c.directors or [])]
                    if not target_entity["supervisors"]:
                        target_entity["supervisors"] = [{"name": s.name, "id_number": s.id_number or ""} for s in (_c.supervisors or [])]
                    if not target_entity["finance_contacts"]:
                        target_entity["finance_contacts"] = [{"name": f.name, "id_number": f.id_number or "", "phone": f.phone or ""} for f in (_c.finance_contacts or [])]
            except:
                pass
        
        # 如果联网查到了行业分类，替换发票关键词推断的行业（联网数据更权威）
        if lookup.get("industry"):
            target_entity["industry_online"] = lookup["industry"]
            target_entity["industry_source"] = "联网查询"
            # 不直接覆盖 entity["industry"]，保留发票关键词推断的作为对比
            # 下游使用时可选择 industry_online 或 industry
        
        # 记录企业状态
        if lookup.get("status"):
            target_entity["company_status"] = lookup["status"]
            if lookup["status"] not in ("存续", "在业", "开业", "正常"):
                target_entity["_company_status_warning"] = f"企业状态异常: {lookup['status']}"
    
    return target_entity


# ═══════════ 稽查方法论过滤器 —— 剔除无数据支撑的噪声发现 ═══════════

def _apply_methodology_filter(all_findings, pipeline_log, bank_txs, invoices, salaries, social_security, vouchers, inventory, docs, target_industry=""):
    """过滤铁律：每条结论必须有上传资料中的实际数据支撑。target_industry: 由_caller传入，复用_detect_target_entity()的检测结果，避免重复造轮子。"""
    before = len(all_findings)
    
    has_bank = len(bank_txs) > 0
    has_invoice = len(invoices) > 0
    has_salary = len(salaries) > 0
    has_voucher = len(vouchers) > 0
    has_inventory = len(inventory) > 0
    
    has_declaration = any("vat" in str(doc.get("type","")).lower() or "declaration" in str(doc.get("type","")).lower() for doc in docs)
    has_contract = any("contract" in str(doc.get("type","")).lower() for doc in docs)
    
    # target_industry 由调用方传入（来自_detect_target_entity()的加权投票结果），全行业适用
    
    # ═══ 硬删除：绝对不可能基于当前资料的结论 ═══
    HARD_BAN = [
        "涉税中介","代账公司","空壳公司","壳公司",  # 需工商穿透
        "公安","经侦","刑事","移送司法","移送公安","联合办案",
        "走逃","失联","已被稽查","已被立案","已受查",
        "第三方机构","金税四期交叉比对","多部门数据交换",
        "伪造","变造","套打","克隆","防伪","票面","二维码",
        "拒绝提供资料","提供虚假资料","阻挠检查","逾期提供",
        "资金链断裂","银行抽贷","逾期欠款","员工欠薪",
        "税务稽查程序","稽查应对","合规度",
        # 证据链编号引用（非真实分析）
        "证据链[",
        "经营场所实质","开票经济","开票公司",
        # 医药相关（非医药行业）
        "医疗器械","两票制","推广费异常",
        # 需要外部信用/监管系统数据
        "失信记录","供应商信用","信用评级",
        # 需要个人账户数据
        "私户收款","个人银行账户","法定代表人/股东/财务人员个人",
        # 系统术语/功能描述
        "金税四期综合风险积分","税务四源偏差",
        # 需要专项调查
        "挂靠经营","转让定价","同期资料","主体文档","本地文档",
        # 需要跨境数据
        "跨境","出口退税","报关",
        # 需要个人账户/对私数据
        "公转私","对私转账",
        # 需要完整损益表/成本核算（无凭证时不可判断）
        "毛利率/净利率为负","毛利率偏离","成本无合法凭证",
        "已发货未开票","契税延期缴纳",
        # 方法论描述/信息摘要，非稽查发现
        "资金流水全量调取","资金流概览","进销概况",
        "进销存虚拟匹配概览","收入三源对比总览",
        # 需要凭证级明细的指标
        "指标","预警","配比异常",
        # 无具体交易支撑的推测
        "资金回流转账","陈述与证据矛盾",
        # Python模板变量未替换的僵尸发现
        "{bank_income", "{inv_income", "{gap_pct",
    ]
    if target_industry != "医药":
        HARD_BAN.extend(["医药"])
    
    COND_BAN = {
        "申报表": ("申报收入","申报表","未申报","少申报","漏申报","纳税申报"),
        "合同": ("四流不一","合同缺失","合同覆盖","合同流","三流不一"),
        "工资表": ("工资","薪酬","个税","个人所得税","人力成本","薪资"),
        "库存台账": ("存货","库存","盘点","账外物资"),
        "会计凭证": ("记账凭证","序时账","会计凭证","账务处理",
            "料工费配比","制造费用分摊","暂估成本","结转大额成本",
            "废品率","边角料","折旧年限","跨年度成本",
            "成本率季度","季度间波动","同比激增",
            "收入同比下滑成本同比","收入增长幅度远低于成本增长幅度",
            "办公费月度波动","差旅费月度集中","广告费业务宣传费",
            "补充养老保险","超标列支未调增",
            "年末集中结转","年末暂估","补缴以前年度",
            "指标","预警",  # 所有指标/预警类需完整财务数据
            "管理费用占收入比例","销售费用占","主营业务成本率",
            "原材料耗用占","业务招待费","办公用品采购与员工人数"),
    }
    
    filtered = []
    removed_count = 0
    removed_reasons = {}
    removed_items = []  # 详细删除日志
    gap_count = 0
    gap_limit = 5  # 资料缺失类最多保留5条
    
    for f in all_findings:
        f_type = str(f.get("type", ""))
        f_detail = str(f.get("detail", ""))
        f_desc = str(f.get("description", ""))
        full_text = f_type + " " + f_detail + " " + f_desc
        skip = False
        reason = ""
        
            
        # 规则0：稽查重点发现（level_fixed=True）不参与任何过滤，强制保留
        if f.get("level_fixed"):
            filtered.append(f)
            continue
        
        # 规则0.1：资料完备度评估类发现（资料完备度综合评估+各类缺失评估）
        # ——这类发现的描述必然提及缺失资料类别，会误中COND_BAN，因此全面豁免
        if "资料完备度" in f_type or "完备度" in f_type or any(k in f_type for k in ["缺失评估", "文件解析失败"]):
            filtered.append(f)
            continue
        
        # 规则0：证据链自动生成结论 → 删除（检查type和detail）
        if f_type.startswith("证据链闭环") or "证据链" in f_type or "证据链[" in f_detail:
            skip = True; reason = "自动生成证据链"
        
        # 规则1：硬删除
        if not skip:
            for kw in HARD_BAN:
                if kw in full_text:
                    skip = True; reason = f"禁止词:{kw}"; break
        
        # 规则2：有条件过滤
        if not skip:
            checks = [
                ("申报表", has_declaration),
                ("合同", has_contract),
                ("工资表", has_salary),
                ("库存台账", has_inventory),
                ("会计凭证", has_voucher),
            ]
            for name, has_it in checks:
                if has_it: continue
                for kw in COND_BAN[name]:
                    if kw in full_text:
                        skip = True; reason = f"无{name}"; break
                if skip: break
        
        # 规则3：正常/一致结论 → 排除
        if not skip:
            for kw in ["一致","正常","无明显差异","通过","良好","合规","无异常"]:
                if kw in f_type:
                    skip = True; reason = "正常结论"; break
        
        # 规则4：资料缺口类合并（发票/data audit发现不计入缺口上限）
        if not skip:
            for kw in ["缺少","缺失","无法验证","不完备","未被触发"]:
                if kw in f_type:
                    # 发票实质性审计发现(如"发票缺少数量字段")是真实发现，不计入资料缺口
                    if "发票" in f_type or "加工费" in f_type or "BOM" in f_type or "进销" in f_type:
                        gap_count += 0  # 不占缺口配额
                    elif gap_count >= gap_limit:
                        skip = True; reason = "资料缺口超限"
                    else:
                        gap_count += 1
                    break
        
        if skip:
            removed_count += 1
            removed_reasons[reason] = removed_reasons.get(reason, 0) + 1
            removed_items.append({
                "type": f_type[:60],
                "level": f.get("level", ""),
                "score": f.get("score", 0),
                "reason": reason,
                "category": f.get("category", "")[:40],
            })
            continue
        
        filtered.append(f)
    
    after1 = len(filtered)
    
    # ═══ 规则5：行业不匹配过滤 ═══
    # 所有可能的行业类型
    post_industry = []
    ind_removed = 0
    for f in filtered:
        ft = str(f.get("type", ""))
        fd = str(f.get("detail", ""))
        full = ft + fd
        skip = False
        for ind_name, keywords in _load_industry_data().get("all_industries", {}).items():
            if ind_name == target_industry or not target_industry:
                continue  # don't filter matching industry
            for kw in keywords:
                if kw in full:
                    skip = True
                    break
            if skip:
                break
        if skip:
            ind_removed += 1
            removed_items.append({
                "type": ft[:60],
                "level": f.get("level", ""),
                "score": f.get("score", 0),
                "reason": f"行业不匹配:{ind_name}",
                "category": f.get("category", "")[:40],
            })
            continue
        post_industry.append(f)
    
    # ═══ 规则6：去重 ═══
    seen = set()
    deduped = []
    dup_removed = 0
    for f in post_industry:
        # 以前60字type作为去重key
        key = str(f.get("type", ""))[:60]
        if key not in seen:
            seen.add(key)
            deduped.append(f)
        else:
            dup_removed += 1
            removed_items.append({
                "type": str(f.get("type", ""))[:60],
                "level": f.get("level", ""),
                "score": f.get("score", 0),
                "reason": "重复发现去重",
                "dup_of": key,
            })
    
    filtered = deduped
    after = len(filtered)
    total_removed = removed_count + ind_removed + dup_removed
    pipeline_log.append(f"方法论过滤: {before}→{after}条 (剔除{total_removed}条噪声)")
    for rsn, cnt in sorted(removed_reasons.items(), key=lambda x: -x[1]):
        pipeline_log.append(f"  剔除 [{rsn}]: {cnt}条")
    if ind_removed > 0:
        pipeline_log.append(f"  剔除 [行业不匹配]: {ind_removed}条")
    if dup_removed > 0:
        pipeline_log.append(f"  剔除 [重复发现]: {dup_removed}条")

    filter_log = {
        "before_count": before,
        "after_count": after,
        "total_removed": total_removed,
        "hard_ban_removed": removed_count,
        "industry_removed": ind_removed,
        "dup_removed": dup_removed,
        "reason_breakdown": dict(sorted(removed_reasons.items(), key=lambda x: -x[1])),
        "removed_items": removed_items,
        "noise_ratio": round(total_removed / max(before, 1) * 100),
    }
    return filtered, pipeline_log, filter_log

def _review_report(all_findings, domain_summary, stats, bank_txs, invoices, vouchers, salaries):
    """逐结论复核：1)数据源验证 2)计算复核 3)逻辑一致性 4)空值陷阱 5)极端值"""
    issues = []
    
    # ═══ 规则1: 数据源验证——结论引用的数字是否真实存在 ═══
    for f in all_findings:
        detail = str(f.get("detail", ""))
        ftype = str(f.get("type", ""))
        
        # 检查"凭证借贷不平"——凭证号是否有效
        if "借贷不平" in ftype:
            empty_vn = sum(1 for v in vouchers if not str(v.get("voucher_no", "")).strip()) if vouchers else 0
            total_vn = len(vouchers) if vouchers else 0
            if total_vn > 0 and empty_vn / total_vn > 0.9:
                issues.append({
                    "level": "错误", "item": f"凭证借贷不平结论无效",
                    "detail": f"凭证号字段{empty_vn}/{total_vn}为空，无法逐张校验借贷平衡。报告的'{ftype}'结论基于无效分组得出，数字不可信。",
                    "suggestion": "凭证文件需包含完整的凭证编号列才能做此分析。建议重新导出含凭证号的Excel。"
                })
        
        # 检查"253张凭证"等具体数字——与stats是否一致
        if "253张" in detail or "253 张" in detail:
            voucher_count = int(stats.get("凭证记录", 0))
            if voucher_count != 253:
                issues.append({
                    "level": "警告", "item": "凭证数量不一致",
                    "detail": f"报告中提到253张凭证，但实际解析到{voucher_count}条凭证记录。",
                    "suggestion": "检查文�是否解析完整，或报告生成时使用了错误的总数。"
                })

    # ═══ 规则0(最高优先): 多链路矛盾检测 ═══
    has_voucher_unbalanced = any("借贷不平" in str(f.get("type","")) for f in all_findings if "252张" in str(f.get("detail","")))
    if has_voucher_unbalanced and vouchers:
        total_d = sum(float(v.get("debit",0) or 0) for v in vouchers)
        total_c = sum(float(v.get("credit",0) or 0) for v in vouchers)
        if abs(total_d - total_c) <= 1:
            issues.append({
                "level": "错误", "item": "多链路矛盾: 凭证借贷不平 vs 总账平衡",
                "detail": f"通道1(总账): 借方{total_d:,.2f}=贷方{total_c:,.2f}→平衡。通道2(逐张): 报告称凭证不平→矛盾。凭证编号字段可能无效。",
                "suggestion": "采信通道1(总账)。检查凭证编号空值率，如大面积缺失则撤回通道2结论。"
            })
    for f in all_findings:
        import re
        for m in re.finditer(r'(9[5-9]|100)%', str(f.get("detail",""))):
            issues.append({
                "level": "警告", "item": f"极端占比{m.group()}缺多通道验证",
                "detail": f"'{f.get('type','')}'中{m.group()}极端值需第二通道交叉验证。",
                "suggestion": "增加独立数据源验证该比例的可信度。"
            })

    # ═══ 规则2: 计算复核——关键数字重新计算 ═══
    # 复核凭证主营收入
    vr_total = 0.0; vr_invoiced = 0.0; vr_uninvoiced = 0.0
    for v in vouchers:
        if "主营业务收入" in str(v.get("account", "")):
            credit = float(v.get("credit", 0) or 0)
            summary = str(v.get("summary", ""))
            if credit <= 0: continue
            vr_total += credit
            if "无票" in summary or "未开票" in summary:
                vr_uninvoiced += credit
            elif "普票" in summary or "专票" in summary or "发票" in summary:
                vr_invoiced += credit
            else:
                vr_uninvoiced += credit
    
    # 检查报告中的收入数字
    for f in all_findings:
        detail = str(f.get("detail", ""))
        if "主营业务收入" in detail and "3,014,766" in detail and vr_total > 0:
            report_amount = 3014766.19
            if abs(vr_total - report_amount) > 1000:
                issues.append({
                    "level": "警告", "item": "主营收入数据偏差",
                    "detail": f"报告显示{vr_total:,.2f}元，复核计算为{report_amount:,.2f}元，差异{abs(vr_total-report_amount):,.2f}元。",
                    "suggestion": "可能因凭证号为空导致重复计算。重新复核完整数据。"
                })
    
    # 复核进销比
    sal_total = sum(float(i.get("total", 0) or 0) for i in invoices if i.get("direction") == "销项")
    pur_total = sum(float(i.get("total", 0) or 0) for i in invoices if i.get("direction") == "进项")
    for f in all_findings:
        if "进销严重倒挂" in str(f.get("type", "")):
            for num_text in str(f.get("detail", "")).split():
                try:
                    num = float(num_text.replace(",", ""))
                    if num > 5000 and abs(num - (pur_total/max(sal_total, 1)*100)) > 100:
                        issues.append({
                            "level": "信息", "item": "进销比率复核",
                            "detail": f"报告比率与复核值差异。复核: {pur_total/max(sal_total,0.01)*100:.2f}%。",
                            "suggestion": "数值基本一致，可能是四舍五入差异。"
                        })
                except: pass

    # ═══ 规则3: 逻辑一致性——不同域结论是否自相矛盾 ═══
    has_uninvoiced = any("未开票" in str(f.get("type", "")) for f in all_findings)
    has_third_party = any("第三方收款" in str(f.get("type", "")) for f in all_findings)
    has_bank_income = any("收款与开票" in str(f.get("type", "")) for f in all_findings)
    
    if has_uninvoiced and has_third_party:
        # 这两项可能互相印证，合理
        pass
    
    # 检查是否有互相矛盾的百分比
    pcts = []
    for f in all_findings:
        detail = str(f.get("detail", ""))
        # 提取百分比
        import re
        for m in re.finditer(r'(\d{2,3})%', detail):
            pct = int(m.group(1))
            label = str(f.get("type", ""))
            pcts.append((label, pct))
    
    # 总额100%规则：同一总额下各分项占比和不能超过100%
    revenue_pcts = [(l, p) for l, p in pcts if "收入" in l or "收款" in l or "营收" in l]
    if revenue_pcts:
        total_pct = sum(p for _, p in revenue_pcts)
        if total_pct > 120:
            issues.append({
                "level": "警告", "item": "收入分项占比可能重叠",
                "detail": f"多个收入相关分项占比合计{total_pct}%，超过100%，可能同一金额被重复统计在不同维度。",
                "suggestion": "核实各分项的统计口径是否独立，确保没有重复计算。"
            })

    # ═══ 规则4: 空值/默认值陷阱 ═══
    # 检查工资数据是否有效
    salary_names = set()
    for s in salaries:
        name = str(s.get("name", "")).strip()
        if name: salary_names.add(name)
    if len(salaries) > 0 and len(salary_names) == 0:
        issues.append({
            "level": "错误", "item": "工资数据姓名字段全空",
            "detail": f"工资表有{len(salaries)}条记录，但员工姓名字段全空。所有基于员工姓名的分析结论无效。",
            "suggestion": "重新上传包含员工姓名的完整工资表。"
        })
    
    # 检查银行流水交易对手是否有效
    bt_counterparties = set()
    for tx in bank_txs:
        cp = str(tx.get("counterparty", "")).strip()
        if cp: bt_counterparties.add(cp)
    if bank_txs and len(bt_counterparties) / len(bank_txs) < 0.1:
        issues.append({
            "level": "警告", "item": "银行流水交易对手大面积缺失",
            "detail": f"{len(bank_txs)}条流水中仅{len(bt_counterparties)}条有交易对手名称。供应商/客户往来分析结论可能不完整。",
            "suggestion": "确保银行流水PDF包含完整的对方名称信息。"
        })

    # ═══ 规则5: 极端值合理性 ═══
    for f in all_findings:
        detail = str(f.get("detail", ""))
        ftype = str(f.get("type", ""))
        
        # 检查97% - 99% 区间的极端百分比
        for m in re.finditer(r'(9[5-9]|100)%', detail):
            issues.append({
                "level": "注意", "item": f"极端百分比: {m.group()}",
                "detail": f"'{ftype}'中存在{m.group()}的极端占比。虽然可能是真实的（如平台经济行业），但建议人工确认数据完整性。",
                "suggestion": "核实该维度是否存在数据缺失（如部分银行账户未提供流水、部分平台收款未包含等）。"
            })

    return issues



"""税险分析工具函数 — 从 tax_risk.py 提取"""
from datetime import date, timedelta, datetime
from typing import Optional, List, Tuple, Dict, Any
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func, case, extract, and_, or_
from database import JournalEntry, VATDeclaration
import json, os, calendar



# ============ 期间格式工具函数 ============
def _normalize_period(ym: str) -> str:
    """将各种格式的时期统一为 `YYYY-MM`（财税系统标准格式）。

    ★ 2026-09-25 根因修复：旧实现是 `ym[:7]`，**名为归一化、实则只截断**：

        '2025/1/15' → '2025/1/'   → `_period_to_date_range` 抛 ValueError（崩溃）
        '2025年1月'  → '2025年1月'  → 同上崩溃
        '2025.1.5'  → '2025.1.'   → 同上崩溃
        '2025-1'    → '2025-1'    → 长度<7 → 日期区间 ('','')，**整段期间静默无数据**

    凡用户或导入数据传入带分隔符/个位月份的期间（Excel 导出普遍如此），
    要么直接崩溃、要么静默分析空数据 —— 与行业无关，对所有企业都成立。
    现唯一权威为 `engine.findingkit.normalize_month`。
    """
    from engine.findingkit import normalize_month
    if not ym:
        return ''
    return normalize_month(ym)


def _period_to_date_range(ym: str) -> Tuple[str, str]:
    """
    将 YYYY-MM 转换为当月第一天和最后一天（财税严谨格式）
    如 2025-01 → ('2025-01-01', '2025-01-31')

    ★ 2026-09-25：入参一律先经唯一权威归一化，且**月份非法时返回 ('','')** 而非崩溃
      （旧实现直接 `int(ym[5:7])` / `calendar.monthrange(y, m)`，
       遇 '2025/1/' 或 13 月会抛 ValueError 把整条分析链打断）。
    """
    from engine.findingkit import normalize_month
    ym = normalize_month(ym)
    if not ym:
        return ('', '')
    y, m = int(ym[:4]), int(ym[5:7])
    if not (1 <= m <= 12):
        return ('', '')
    first_day = f'{y}-{m:02d}-01'
    last_day_num = calendar.monthrange(y, m)[1]
    last_day = f'{y}-{m:02d}-{last_day_num:02d}'
    return (first_day, last_day)

# ── 工具函数 ──

def _safe_float(val, default=0.0):
    """安全转数值 —— 唯一权威 engine.numparse.to_number。

    ★ 2026-09-25 根因修复：旧实现 `float(val)` **名为 safe、实则不安全** ——
    遇千分位 `"1,234.00"`、空串 `""`、非数字文本会直接抛 ValueError 打断分析链
    （而调用方都以为它"安全"，不会兜住异常）。现统一委托 numparse（含千分位/￥/全角/会计式负数）。
    """
    from engine.numparse import to_number
    return to_number(val, default)

def _risk_level(score: int) -> str:
    if score >= 7: return "高风险"
    elif score >= 4: return "中风险"
    elif score >= 1: return "低风险"
    return "良好"

def _risk_color(score: int) -> str:
    if score >= 7: return "#dc2626"
    elif score >= 4: return "#f59e0b"
    elif score >= 1: return "#3b82f6"
    return "#10b981"

def _get_period_range(db: Session, company_id: int):
    min_entry = db.query(func.min(JournalEntry.entry_date)).filter(
        JournalEntry.company_id == company_id).scalar()
    max_entry = db.query(func.max(JournalEntry.entry_date)).filter(
        JournalEntry.company_id == company_id).scalar()
    if min_entry and max_entry: return str(min_entry), str(max_entry)
    return None, None

def _vat_payable_sum(db: Session, company_id: int, ps: str = None, pe: str = None) -> float:
    """汇总增值税应纳税额（从 form_main JSON 中提取）"""
    q = db.query(VATDeclaration).filter(VATDeclaration.company_id == company_id)
    if ps: q = q.filter(VATDeclaration.period >= ps)
    if pe: q = q.filter(VATDeclaration.period <= pe)
    total = 0.0
    for v in q.all():
        if v.form_main:
            fm = v.form_main if isinstance(v.form_main, dict) else json.loads(v.form_main)
            total += _safe_float(fm.get("vat_payable"))
    return total

def _get_account_balance(db: Session, company_id: int, account_code: str, period: str = None) -> float:
    q = db.query(
        func.coalesce(func.sum(JournalEntry.debit_amount), 0),
        func.coalesce(func.sum(JournalEntry.credit_amount), 0)
    ).filter(JournalEntry.company_id == company_id, JournalEntry.account_code.like(account_code + '%'))
    if period: q = q.filter(JournalEntry.period <= period)
    debit, credit = q.first()
    return _safe_float(debit) - _safe_float(credit)

def _get_account_sum(db: Session, company_id: int, account_code: str, ps: str, pe: str, field: str = "debit") -> float:
    """期间内科目发生额合计"""
    col = JournalEntry.debit_amount if field == "debit" else JournalEntry.credit_amount
    return _safe_float(db.query(func.sum(col)).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.account_code.like(account_code + '%'),
        JournalEntry.period >= ps, JournalEntry.period <= pe
    ).scalar())

def _get_periods_between(ps: str, pe: str) -> list:
    """生成两个 `YYYY-MM` 之间的所有月份。

    ★ 2026-09-25：入参先经唯一权威归一化；任一端不可解析时返回 **[]**，
      不再靠 `int(ps[5:7])` 硬切（旧实现遇 `''` 抛 IndexError、遇非数字抛 ValueError，
      把整条分析链打断；现在退化为"无月份序列"，可被上层稳健处理）。
    """
    ps = _normalize_period(ps)
    pe = _normalize_period(pe)
    if not ps or not pe:
        return []
    result = []
    y1, m1 = int(ps[:4]), int(ps[5:7])
    y2, m2 = int(pe[:4]), int(pe[5:7])
    y, m = y1, m1
    if (y1, m1) > (y2, m2):
        return []
    while True:
        result.append(f"{y}-{m:02d}")
        if y == y2 and m == m2:
            break
        m += 1
        if m > 12:
            m = 1
            y += 1
    return result

def _monthly_account_balance(db: Session, company_id: int, account_code: str, ps: str, pe: str) -> dict:
    """按月汇总科目借方/贷方发生额"""
    ps = _normalize_period(ps)
    pe = _normalize_period(pe)
    rows = db.query(
        JournalEntry.period,
        func.coalesce(func.sum(JournalEntry.debit_amount), 0),
        func.coalesce(func.sum(JournalEntry.credit_amount), 0)
    ).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.account_code.like(account_code + '%'),
        JournalEntry.period >= ps, JournalEntry.period <= pe
    ).group_by(JournalEntry.period).order_by(JournalEntry.period).all()
    return {r[0]: {"debit": _safe_float(r[1]), "credit": _safe_float(r[2])} for r in rows}


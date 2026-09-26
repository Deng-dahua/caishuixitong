# -*- coding: utf-8 -*-
"""应付账款（A/P）索引与账龄（2026-09-14 新增）。

用途
----
供 VR060「成本列支的资金/负债双要件核验」判断第二要件——一笔**未付**的成本，
账面**是否已挂应付账款**、挂了多久。

口径（税务与会计一致）
--------------------
* 赊购是常态（账期 30/60/90/180 天，工程与大宗贸易可跨年），**"无付款"本身不是问题**；
* 真正的要求是：每一笔成本「**有付款**」或「**有负债**」二者至少其一；
* 二者皆无 → 成本凭空列支（虚列成本 / 票未入账 / 已用其他资金支付）→ 待核。

数据来源与诚实边界
----------------
1. **应付账款明细**（`accounts_payable`）：可按供应商归集余额与账龄 → 最有力；
2. **科目余额表**（`trial_balance`）：只能取"应付账款"科目的**汇总**余额 →
   无法按供应商归因。此时**不得**据此判定某供应商"已挂账"，
   只能提示"缺应付账款明细，无法逐户核验"（资料质量，不指向企业过错）。
"""

from __future__ import annotations
from engine.numparse import to_number  # ★ 2026-09-25 统一数值解析（唯一实现）

from typing import Any, Dict, List, Optional

try:  # 与资金匹配共用同一套名称归一化，避免两边口径不一致
    from engine.fund_matching import _core_of
except Exception:  # pragma: no cover
    import re as _re

    def _core_of(name: str) -> str:
        text = str(name or "").strip()
        return _re.sub(r"[（(].*?[)）]", "", text)[:12]


# ── 字段候选键（不同来源表头差异大，全部容错）──────────────────────────
SUPPLIER_KEYS = ("供应商", "供应商名称", "往来单位", "单位名称", "客户名称", "公司名称",
                 "名称", "supplier", "vendor", "counterparty", "name", "col_1", "col_0")
BALANCE_KEYS = ("应付金额", "未付金额", "应付余额", "应付账款", "期末余额", "挂账金额",
                "应付款", "未付", "余额", "balance", "amount", "col_3", "col_2", "col_4")
PAID_KEYS = ("已付金额", "已付款", "已付", "本期付款", "付款金额")
TERMS_KEYS = ("账期", "付款期限", "信用期", "结算账期", "付款条件")
AGING_KEYS = ("账龄", "账龄天数", "挂账天数")
DATE_KEYS = ("开票日期", "发票日期", "业务日期", "挂账日期", "日期", "date")

# 默认账期（天）：赊购常见上限，用于区分"正常赊购"与"长期挂账"
DEFAULT_TERMS_DAYS = 180
LONG_AGING_DAYS = 365          # 超过 1 年视为长期挂账

_AP_ACCOUNT_MARKS = ("应付账款", "2202", "应付暂估", "暂估应付")


def _first(row: Dict, keys) -> str:
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def _to_float(value) -> float:
    """数值解析（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/numparse.py（唯一权威）。
      原私有实现遇 "12,000.00" / "￥1,234.56" 等会静默返回 0，
      导致同一金额在不同模块被算成不同值（报告自相矛盾 / 规则漏触发）。
    """
    from engine.numparse import to_number as _to_number
    return _to_number(value)


def _parse_terms_days(text: str) -> Optional[int]:
    """从"账期 30 天 / 60日 / 月结90天 / Net 60"等文本里取账期天数。"""
    import re
    t = str(text or "")
    m = re.search(r"(\d+)\s*(天|日)", t)
    if m:
        return int(m.group(1))
    m = re.search(r"(?:账期|信用期|net)\D{0,4}(\d+)\s*(?:个月|月)", t, re.I)
    if m:
        return int(m.group(1)) * 30
    m = re.search(r"(\d+)\s*(?:个月|月)", t)
    if m:
        return int(m.group(1)) * 30
    return None


def build_ap_index(ap_rows: Optional[List[Dict]] = None,
                   trial_balance_rows: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """构建应付账款索引。

    返回::

        {
          "by_supplier": {核心名: {"balance": float, "terms_days": int|None,
                                   "aging_days": int|None, "rows": [...]}},
          "has_detail": bool,          # 是否提供了应付账款明细
          "aggregate_balance": float,  # 账面应付账款汇总余额（明细缺失时取自科目余额表）
          "from_trial_balance": bool,  # 该汇总是否来自科目余额表
        }
    """
    by_supplier: Dict[str, Dict[str, Any]] = {}
    for row in ap_rows or []:
        if not isinstance(row, dict):
            continue
        name = _first(row, SUPPLIER_KEYS)
        if not name or any(m in name for m in _AP_ACCOUNT_MARKS):
            continue          # 跳过"应付账款"合计行/科目行，只要供应商行
        balance = _to_float(_first(row, BALANCE_KEYS))
        paid = _to_float(_first(row, PAID_KEYS))
        aging = _to_float(_first(row, AGING_KEYS))
        terms = _parse_terms_days(_first(row, TERMS_KEYS))
        if balance <= 0 and paid > 0:
            continue          # 已付清、无余额 → 不构成"挂账"
        key = _core_of(name) or name
        item = by_supplier.setdefault(key, {"balance": 0.0, "terms_days": None,
                                            "aging_days": None, "rows": []})
        item["balance"] += balance
        if terms and not item["terms_days"]:
            item["terms_days"] = terms
        if aging > 0 and not item["aging_days"]:
            item["aging_days"] = int(aging)
        item["rows"].append({"name": name, "balance": balance})

    has_detail = bool(by_supplier)

    # 科目余额表兜底：仅取"应付账款"科目汇总余额，不做供应商归因
    aggregate, from_tb = 0.0, False
    if not has_detail:
        for row in trial_balance_rows or []:
            if not isinstance(row, dict):
                continue
            name = _first(row, ("科目名称", "科目", "account_name", "account", "col_1"))
            code = _first(row, ("科目编码", "科目代码", "code", "col_0"))
            if not any(m in name for m in _AP_ACCOUNT_MARKS) and not str(code).startswith("2202"):
                continue
            aggregate += _to_float(_first(row, ("期末余额", "期末贷方余额", "期末贷方", "贷方余额",
                                                "余额", "贷方", "close", "col_3", "col_4")))
        from_tb = aggregate > 0

    return {"by_supplier": by_supplier, "has_detail": has_detail,
            "aggregate_balance": round(aggregate, 2), "from_trial_balance": from_tb}


def lookup_ap(ap_index: Dict[str, Any], supplier: str) -> Optional[Dict[str, Any]]:
    """按供应商核心名查应付挂账（精确或互含匹配）。找不到返回 None。"""
    if not supplier:
        return None
    key = _core_of(supplier) or str(supplier).strip()
    by = (ap_index or {}).get("by_supplier") or {}
    if not by:
        return None
    if key in by:
        return by[key]
    for k, v in by.items():
        if k and (k in key or key in k):
            return v
    return None


def aging_days(invoice_date: str, base_date: str) -> Optional[int]:
    """账龄天数 = 基准日 − 发票日。日期格式容错：YYYY-MM-DD / YYYYMMDD / YYYY/M/D。"""
    def _d(text):
        s = "".join(ch for ch in str(text or "") if ch.isdigit())
        if len(s) < 8:
            return None
        import datetime as _dt
        try:
            return _dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except ValueError:
            return None
    d1, d2 = _d(invoice_date), _d(base_date)
    if not d1 or not d2:
        return None
    return (d2 - d1).days


def evaluate_ap(supplier: str, invoice_date: str, base_date: str,
                ap_index: Dict[str, Any]) -> Dict[str, Any]:
    """对单个供应商给出应付挂账判定，供 VR060 判定矩阵使用。

    返回：{"status": "有挂账"|"无挂账"|"无明细", "balance": float,
           "aging_days": int|None, "terms_days": int|None, "long_aging": bool}
    """
    info = lookup_ap(ap_index, supplier)
    age = aging_days(invoice_date, base_date)
    if info and info.get("balance", 0) > 0:
        terms = info.get("terms_days") or DEFAULT_TERMS_DAYS
        eff_age = info.get("aging_days") if info.get("aging_days") is not None else age
        return {"status": "有挂账", "balance": round(info["balance"], 2),
                "aging_days": eff_age, "terms_days": terms,
                "long_aging": bool(eff_age is not None and eff_age > LONG_AGING_DAYS)}
    if (ap_index or {}).get("has_detail"):
        return {"status": "无挂账", "balance": 0.0, "aging_days": age,
                "terms_days": DEFAULT_TERMS_DAYS, "long_aging": False}
    # 未提供应付账款明细 → 无法逐户核验（资料质量，不指向企业过错）
    return {"status": "无明细", "balance": 0.0, "aging_days": age,
            "terms_days": None, "long_aging": False}

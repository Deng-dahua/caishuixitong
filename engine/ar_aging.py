# -*- coding: utf-8 -*-
"""应收账款（A/R）索引与账龄（2026-09-14 新增，镜像 ap_aging.py）。

用途
----
供「收入真实性（账外收入嫌疑）」能力判断第三维度——一笔**已开票/已确认**的收入，
账面**是否真实存在未收回的应收**、挂了多久、是否长期挂账（指向虚构收入而非真赊账）。

口径（税务与会计一致）
--------------------
* 赊销是常态（账期 30/60/90/180 天，大额贸易可跨年），**"有应收挂账"本身不是问题**；
* 真正的红线是：**长期应收挂账 + 无银行回款印证** → 收入可能虚构或资金滞留账外；
* 反之，银行收款已覆盖开票（VR061 已印证）则应收维度无异常。

数据来源与诚实边界
----------------
1. **应收账款明细**（`accounts_receivable`）：可按客户归集未收金额与账龄 → 最有力；
2. **科目余额表**（`trial_balance`）：只能取"应收账款"科目的**汇总**余额 →
   无法按客户归因。此时仅提示"缺应收账款明细，无法逐户核验"（资料质量，不指向企业过错）。

注：本模块只做"应收挂账真实性待核"，不替代主管机关定性。结论一律待证线索。
"""

from __future__ import annotations
from engine.numparse import to_number  # ★ 2026-09-25 统一数值解析（唯一实现）

from typing import Any, Dict, List, Optional

try:  # 与资金匹配 / 应付账龄共用同一套名称归一化，避免两边口径不一致
    from engine.ap_aging import (
        aging_days,
        DEFAULT_TERMS_DAYS,
        LONG_AGING_DAYS,
        _core_of,
    )
except Exception:  # pragma: no cover
    import re as _re

    def _core_of(name: str) -> str:
        text = str(name or "").strip()
        return _re.sub(r"[（(].*?[)）]", "", text)[:12]

    def aging_days(invoice_date: str, base_date: str):
        return None

    DEFAULT_TERMS_DAYS = 180
    LONG_AGING_DAYS = 365


# ── 字段候选键（不同来源表头差异大，全部容错）──────────────────────────
CUSTOMER_KEYS = ("客户名称", "客户", "购货单位", "买方", "购方", "名称",
                 "customer", "buyer", "name", "col_1", "col_0")
RECEIVABLE_KEYS = ("应收金额", "应收账款", "期末余额", "余额", "应收",
                   "receivable", "amount", "col_3", "col_4")
RECEIVED_KEYS = ("已收金额", "已收款", "已收", "本期收款", "收款金额", "received")
UNRECEIVED_KEYS = ("未收金额", "未收", "未收回", "欠款", "未收余额",
                   "unreceived", "balance_due")
AGING_KEYS = ("账龄", "账龄天数", "挂账天数")
BAD_DEBT_KEYS = ("坏账准备", "坏账", "bad_debt")
DATE_KEYS = ("开票日期", "发票日期", "业务日期", "挂账日期", "日期", "date")

_AR_ACCOUNT_MARKS = ("应收账款", "1122", "应收暂估", "暂估应收")


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


def _parse_aging_days(text: str) -> Optional[int]:
    """从"账龄 120 天 / 6个月 / 1年"等文本里取账龄天数。"""
    import re
    t = str(text or "")
    m = re.search(r"(\d+)\s*(天|日)", t)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*(?:个月|月)", t)
    if m:
        return int(m.group(1)) * 30
    m = re.search(r"(\d+)\s*(?:年)", t)
    if m:
        return int(m.group(1)) * 365
    return None


def _rows_of(data) -> List[Dict]:
    """accounts_receivable 可能为 rows 列表，也可能为 {'rows': [...]} 包裹。"""
    if isinstance(data, dict):
        rows = data.get("rows") or []
        if isinstance(rows, list):
            return rows
    if isinstance(data, list):
        return data
    return []


def build_ar_index(ar_rows: Optional[List[Dict]] = None,
                   trial_balance_rows: Optional[List[Dict]] = None,
                   base_date: Optional[str] = None) -> Dict[str, Any]:
    """构建应收账款索引。

    返回::

        {
          "by_customer": {核心名: {"receivable": float, "received": float,
                                   "unreceived": float, "aging_days": int|None,
                                   "bad_debt": float, "rows": [...]}},
          "has_detail": bool,
          "aggregate_balance": float,
          "from_trial_balance": bool,
          "base_date": str|None,
        }
    """
    by_customer: Dict[str, Dict[str, Any]] = {}
    for row in ar_rows or []:
        if not isinstance(row, dict):
            continue
        name = _first(row, CUSTOMER_KEYS)
        if not name or any(m in name for m in _AR_ACCOUNT_MARKS):
            continue          # 跳过"应收账款"合计行/科目行，只要客户行
        receivable = _to_float(_first(row, RECEIVABLE_KEYS))
        received = _to_float(_first(row, RECEIVED_KEYS))
        given_unrec = _to_float(_first(row, UNRECEIVED_KEYS))
        unreceived = given_unrec if given_unrec > 0 else max(receivable - received, 0.0)
        if receivable <= 0 and unreceived <= 0:
            continue          # 无余额、无未收 → 不构成"挂账"
        aging_given = _parse_aging_days(_first(row, AGING_KEYS))
        inv_date = _first(row, DATE_KEYS)
        age = aging_given if aging_given and aging_given > 0 else aging_days(inv_date, base_date or "")
        bad_debt = _to_float(_first(row, BAD_DEBT_KEYS))
        key = _core_of(name) or name
        item = by_customer.setdefault(key, {"receivable": 0.0, "received": 0.0,
                                            "unreceived": 0.0, "aging_days": None,
                                            "bad_debt": 0.0, "rows": []})
        item["receivable"] += receivable
        item["received"] += received
        item["unreceived"] += unreceived
        if age is not None and (item["aging_days"] is None or age > item["aging_days"]):
            item["aging_days"] = age
        if bad_debt > 0:
            item["bad_debt"] += bad_debt
        item["rows"].append({"name": name, "unreceived": unreceived, "aging_days": age})

    has_detail = bool(by_customer)

    # 科目余额表兜底：仅取"应收账款"科目汇总余额，不做客户归因
    aggregate, from_tb = 0.0, False
    if not has_detail:
        for row in trial_balance_rows or []:
            if not isinstance(row, dict):
                continue
            nm = _first(row, ("科目名称", "科目", "account_name", "account", "col_1"))
            code = _first(row, ("科目编码", "科目代码", "code", "col_0"))
            if not any(m in nm for m in _AR_ACCOUNT_MARKS) and not str(code).startswith("1122"):
                continue
            aggregate += _to_float(_first(row, ("期末余额", "期末借方余额", "期末借方", "借方余额",
                                                "余额", "借方", "close", "col_3", "col_4")))
        from_tb = aggregate > 0

    return {"by_customer": by_customer, "has_detail": has_detail,
            "aggregate_balance": round(aggregate, 2), "from_trial_balance": from_tb,
            "base_date": base_date}


def lookup_ar(ar_index: Dict[str, Any], customer: str) -> Optional[Dict[str, Any]]:
    """按客户核心名查应收挂账（精确或互含匹配）。找不到返回 None。"""
    if not customer:
        return None
    key = _core_of(customer) or str(customer).strip()
    by = (ar_index or {}).get("by_customer") or {}
    if not by:
        return None
    if key in by:
        return by[key]
    for k, v in by.items():
        if k and (k in key or key in k):
            return v
    return None


def evaluate_ar(customer: str, invoice_date: str, base_date: str,
                ar_index: Dict[str, Any]) -> Dict[str, Any]:
    """对单个客户给出应收挂账判定。

    返回：{"status": "有应收挂账"|"无挂账"|"无明细", "unreceived": float,
           "aging_days": int|None, "long_aging": bool}
    """
    info = lookup_ar(ar_index, customer)
    age = aging_days(invoice_date, base_date)
    if info and info.get("unreceived", 0) > 0:
        eff_age = info.get("aging_days") if info.get("aging_days") is not None else age
        return {"status": "有应收挂账", "unreceived": round(info["unreceived"], 2),
                "aging_days": eff_age,
                "long_aging": bool(eff_age is not None and eff_age > LONG_AGING_DAYS)}
    if (ar_index or {}).get("has_detail"):
        return {"status": "无挂账", "unreceived": 0.0, "aging_days": age, "long_aging": False}
    # 未提供应收账款明细 → 无法逐户核验（资料质量，不指向企业过错）
    return {"status": "无明细", "unreceived": 0.0, "aging_days": age, "long_aging": False}


def run_ar_aging_check(data: Dict[str, Any], company_name: str = "",
                       base_date: Optional[str] = None) -> Dict[str, Any]:
    """应收账龄能力入口（维度3 引擎）。

    输入 ``data`` 须含 ``accounts_receivable``（rows 列表或 {'rows':[...]}）。
    返回与能力范式同构的 dict：available/ok/title/summary/body/metrics/signals/verdict/recommendation/note。
    """
    ar_raw = _rows_of(data.get("accounts_receivable"))
    tb_raw = _rows_of(data.get("trial_balance"))
    title = "应收账款账龄核验（收入真实性·维度3）"

    if not ar_raw and not tb_raw:
        return {
            "available": False,
            "ok": True,
            "title": title,
            "company": company_name,
            "summary": "未提供应收账款明细或科目余额表，无法核验未收款项账龄。",
            "body": "企业未上传应收账款明细表或科目余额表，无法判断已开票/已确认收入中"
                    "有多少尚未收回、挂账多久。该维度暂列为资料缺失，须补证后复核。",
            "metrics": {"ar_customers": 0, "ar_unreceived_total": 0.0,
                        "ar_long_aging_count": 0, "ar_max_aging_days": 0},
            "signals": [],
            "verdict": "资料缺失待核",
            "recommendation": "责令企业提供应收账款明细表（含客户、未收金额、账龄），或科目余额表中"
                              "应收账款科目余额，再逐户核验未收回款项与挂账时长。",
            "note": "结论属待证线索，不作为定性依据；未提供应收资料不指向企业过错。",
        }

    idx = build_ar_index(ar_raw, tb_raw, base_date=base_date)
    by = idx["by_customer"]

    if not by:  # 有汇总但无客户明细
        return {
            "available": True,
            "ok": True,
            "title": title,
            "company": company_name,
            "summary": "仅取得应收账款科目汇总余额，缺客户明细，无法逐户核验账龄。",
            "body": f"账面应收账款汇总余额为 {idx['aggregate_balance']:,.2f} 元，但缺少按客户拆分的明细，"
                    "无法判断未收回款项分布与挂账时长。该维度暂列为资料缺失，须补明细后复核。",
            "metrics": {"ar_customers": 0, "ar_unreceived_total": idx["aggregate_balance"],
                        "ar_long_aging_count": 0, "ar_max_aging_days": 0,
                        "ar_from_trial_balance": True},
            "signals": [],
            "verdict": "资料缺失待核",
            "recommendation": "责令企业提供应收账款明细表（含客户、未收金额、账龄），再逐户核验。",
            "note": "结论属待证线索，不作为定性依据；汇总余额来自科目余额表，无法按客户归因。",
        }

    total_unreceived = 0.0
    long_aging = 0
    max_age = 0
    customers_with_unrec = 0
    for core, item in by.items():
        unrec = item.get("unreceived", 0.0)
        if unrec > 0:
            customers_with_unrec += 1
            total_unreceived += unrec
        age = item.get("aging_days")
        if age is not None:
            max_age = max(max_age, age)
            if age > LONG_AGING_DAYS:
                long_aging += 1

    metrics = {
        "ar_customers": len(by),
        "ar_customers_with_unreceived": customers_with_unrec,
        "ar_unreceived_total": round(total_unreceived, 2),
        "ar_long_aging_count": long_aging,
        "ar_max_aging_days": max_age,
        "ar_base_date": base_date or "",
    }
    signals = []
    if long_aging > 0:
        signals.append({"signal": f"有 {long_aging} 个客户应收挂账超过 {LONG_AGING_DAYS} 天",
                        "hint": "长期应收挂账须核对期后回款与交易真实性，警惕虚构收入或资金滞留账外"})

    body = (f"应收账款涉及 {len(by)} 个客户，其中 {customers_with_unrec} 个存在未收回款项，"
            f"合计未收金额 {total_unreceived:,.2f} 元；最长账龄 {max_age} 天"
            f"（长期挂账客户 {long_aging} 个）。"
            f"未收款项须结合银行回款印证：若长期挂账且无任何回款记录，"
            f"收入真实性存疑，须逐笔核验交易背景与回款去向。")
    verdict = "待核验" if (long_aging > 0 or total_unreceived > 0) else "未见异常"
    recommendation = ("对长期应收挂账客户逐笔核验销售合同、发货单据、期后银行回款与函证，"
                      "确认收入真实性与资金去向。") if long_aging > 0 else "维持关注，期后回款到位即消除疑点。"

    return {
        "available": True,
        "ok": True,
        "title": title,
        "company": company_name,
        "summary": f"未收金额合计 {total_unreceived:,.2f} 元，最长账龄 {max_age} 天，"
                  f"长期挂账客户 {long_aging} 个。",
        "body": body,
        "metrics": metrics,
        "signals": signals,
        "verdict": verdict,
        "recommendation": recommendation,
        "note": "结论属待证线索，不作为定性依据；赊销挂账本身为经营常态，仅长期无回款方指向疑点。",
    }

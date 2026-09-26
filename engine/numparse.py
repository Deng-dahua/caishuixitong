"""统一数值解析（唯一权威）—— 全系统「金额 / 数量 / 比例」解析的唯一入口（2026-09-25）

═══════════════════════════════════════════════════════════════════════════════
为什么必须收敛（根因）
═══════════════════════════════════════════════════════════════════════════════
全项目曾有 **25 处**各自实现数值解析，其中 **20 处**在遇到带千分位/货币符号的
字符串（如 `"12,000.00"`、`"￥1,234.56"`）时会**静默返回 0**：

    domain_analysis._number   → 12,000.00 ✔（去千分位 + 正则兜底）
    verified_rule_engine._number → 0.0 ✘（float() 抛异常吃默认）
    bank_flow._safe           → 0.0 ✘（float(v or 0) 直接炸）

**后果**：同一张发票的「金额」，域分析算出 12000、规则引擎算出 0 —— 报告不同章节
的金额可能互相矛盾，甚至规则因"金额=0"而根本不触发（漏报）。
这与具体行业无关，对**所有企业**都成立。

═══════════════════════════════════════════════════════════════════════════════
三条铁律
═══════════════════════════════════════════════════════════════════════════════
N1 **解析不出就要显式区分**：无法识别时返回 `default`（默认 0.0），
   调用方若需区分"真的 0"与"解析失败"，用 `to_number_checked()` 拿 `(值, 是否成功)`。
N2 **解析规则必须唯一**：不得再有任何模块自带 `float(v or 0)` 之类的私有实现。
N3 **金额取值口径必须唯一**：`first_amount()` 是唯一实现，键优先级集中在此一处维护，
   新增字段名只需在此加一项，不必改各检测器。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

# 中文数量级（出现在金额文本中时必然表示倍数，如"1.2万"= 12000）
_MAGNITUDE = {"万": 10_000.0, "亿": 100_000_000.0, "千": 1_000.0, "百": 100.0}
# 需要剔除的字符：千分位分隔符、中英文货币符号、单位字、空白（含全角）
_STRIP_CHARS = ",，  \u00a0\t￥¥$€£元人民币"
# 视为"空值/无值"的字面量
_NULLS = {"", "none", "null", "nan", "-", "--", "—", "——", "/", "\\", "无", "***", "不适用", "n/a"}

# 金额字段的**唯一**优先级（新增字段名只在此处加，不必改各检测器）
AMOUNT_KEYS: Tuple[str, ...] = (
    "amount", "金额", "不含税金额", "tax_amount", "税额",
    "total", "价税合计", "含税金额", "total_amount", "金额合计",
    "debit", "借方金额", "credit", "贷方金额", "支出金额", "收入金额", "交易金额",
)


def to_number_checked(value: Any, default: float = 0.0) -> Tuple[float, bool]:
    """解析并返回 `(数值, 是否成功解析)`。N1：让调用方能区分"真 0"与"解析失败"。

    支持：int/float、`"12,000.00"`、`"￥1,234.56"`、`"1,234.56元"`、`"(1,234.00)"`(负数)、
    `"1.2万"`/`"3亿"`、`"6%"`（按数值 6 返回，需要比例请自行 /100）、全角数字与全角空格。
    """
    if value is None:
        return default, False
    if isinstance(value, bool):
        return float(value), True
    if isinstance(value, (int, float)):
        try:
            return float(value), True
        except (TypeError, ValueError):
            return default, False

    s = str(value)
    # 全角数字/符号 → 半角（源与目标必须等长：10 数字 + % . - ( )）
    s = s.translate(str.maketrans("０１２３４５６７８９％．－（）", "0123456789%.-()"))
    s = s.strip().strip("".join(_STRIP_CHARS))
    if s.lower() in _NULLS:
        return default, False

    # 会计式负数：(1,234.00) 或 （1,234.00）
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1].strip()

    for ch in _STRIP_CHARS:                      # 去千分位/货币/单位
        s = s.replace(ch, "")
    s = s.rstrip("%")                            # 百分号按数值处理（不做 /100，避免歧义）

    # 数量级（万/亿/千/百）—— 出现在末尾才是倍数
    mag = 1.0
    if s and s[-1] in _MAGNITUDE:
        mag = _MAGNITUDE[s[-1]]
        s = s[:-1].strip()

    try:
        num = float(s) * mag
    except (TypeError, ValueError):
        # 兜底：从文本中提取第一个数值（兼容 "金额:12000.00"）
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        if not m:
            return default, False
        try:
            num = float(m.group(0)) * mag
        except (TypeError, ValueError):
            return default, False
    return (-num if negative else num), True


def to_number(value: Any, default: float = 0.0) -> float:
    """把任意单元格值解析为 float —— **全系统唯一实现**。

    解析不出来时返回 default（默认 0.0），不抛异常、不返回 None。
    """
    return to_number_checked(value, default)[0]


def first_amount(row: Any, keys: Optional[Tuple[str, ...]] = None,
                 absolute: bool = True) -> float:
    """按**统一优先级**从一条记录里取"金额" —— 全系统唯一实现（N3）。

    行为：按 `AMOUNT_KEYS`（可覆盖）依次取第一个能解析出**非零**值的字段；
    全为零/取不到时返回 0.0。`absolute=True` 返回绝对值（金额比对通常只关心量级，
    方向另由 direction/借贷字段表达）。
    """
    if not isinstance(row, dict):
        return 0.0
    for k in (keys or AMOUNT_KEYS):
        v = row.get(k)
        if v in (None, ""):
            continue
        n = to_number(v)
        if n:
            return abs(n) if absolute else n
    return 0.0


def amount_of(row: Any, absolute: bool = False) -> float:
    """取金额（不过滤零值，取到即返回）—— 用于"该字段就是 0"也有意义的场景。"""
    if not isinstance(row, dict):
        return 0.0
    for k in AMOUNT_KEYS:
        if row.get(k) not in (None, ""):
            n = to_number(row.get(k))
            return abs(n) if absolute else n
    return 0.0


def sum_field(records: Any, keys: Optional[Tuple[str, ...]] = None) -> float:
    """对列表里每条记录按统一优先级取金额并求和（同一字段只计一次）。"""
    total = 0.0
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        for k in (keys or AMOUNT_KEYS):
            if rec.get(k) not in (None, ""):
                total += to_number(rec.get(k))
                break
    return total


def parse_ratio(value: Any) -> Optional[float]:
    """解析比例/百分比：`"6%"`→0.06、`"0.06"`→0.06、`6`→6.0 需调用方判断。

    ⚠ 仅用于明确是"率"的场景；一般金额请用 `to_number`。
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    pct = s.endswith("%") or "％" in s
    n, ok = to_number_checked(s)
    if not ok:
        return None
    return (n / 100.0) if pct else n

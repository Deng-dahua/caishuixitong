# -*- coding: utf-8 -*-
"""构成要件**阈值校验** —— 「本企业涉及第X条构成要件」这句话的唯一校验点。

## 为什么要有（外部点评 P1-5）

点评实测：某红线第②条要件写「未付款占比**超过 50%**」，而本企业实际 **32.5%**，
报告仍标「涉及要件②」；同类还有「差额占比」被拿去比「税负率区间」、
印花税被拿去比「应纳税所得额」（**量纲不同，根本无法相除**）。

根因：命中要件是"信号触发即命中"，**要件文本里的数值条件从未与证据里的实际值核对**。
于是要件清单（A：什么情形算涉嫌）与企业命中（B：本企业踩了哪条）之间没有算术闭环，
读者一算就发现"没到门槛也算命中"，整份报告的可信度受损。

## 做法（通用、与行业无关）

1. **从要件文本解析阈值条件**：`（占|率|比）…超过/不低于/大于/低于 N%`、
   `N 元以上/以下`、`N 天以上`、`N 倍以上` 等；
2. **从命中证据里解析同量纲的实际值**：只在**同一量纲**（%／元／天／倍）里取，
   取不到同量纲值 → **不判**（返回 unknown，不阻断、不误杀）；
3. 实际值**不满足**阈值 → 该要件**不得标记为命中**，改写为
   「未达该项阈值（实际 X，要件门槛 Y）」。

判据方向：**宁可漏标"未达阈值"（unknown 放行），不可把未达门槛的说成命中**（后者是硬伤）。
"""

from __future__ import annotations

import re
from typing import Any, Optional, Tuple

# 量纲标识（唯一权威；新增量纲只加一行）
_DIMS: Tuple[Tuple[str, str], ...] = (
    ("pct", "%"),
    ("yuan", "元"),
    ("day", "天"),
    ("times", "倍"),
)

# 要件文本里的阈值模式：量纲词 + 比较词 + 数字
_NUM = r"(\d+(?:\.\d+)?)"
_THRESHOLD_PATTERNS = (
    # 占比/比率/比例 … 超过/大于/高于/不低于/不足 N%
    ("pct", re.compile(
        r"(?:占比|比例|比率|率|比重)[^。；，,]{0,12}?"
        r"(超过|大于|高于|不低于|不少于|不足|低于|小于|不高于|不超过)\s*" + _NUM + r"\s*%")),
    # N% 以上/以下 形态（要件先给数再给量纲）
    ("pct", re.compile(
        r"(?:超过|大于|高于|不低于|不少于|不足|低于|小于|不高于|不超过)\s*" + _NUM + r"\s*%")),
    ("pct", re.compile(_NUM + r"\s*%\s*(?:以上|以下)")),
    # 金额：N 元 以上/以下/超过
    ("yuan", re.compile(
        r"(超过|大于|高于|不低于|不少于|不足|低于|小于|不高于|不超过)?\s*" + _NUM + r"\s*(?:万元|元)\s*(?:以上|以下)?")),
    # 天数
    ("day", re.compile(
        r"(超过|大于|高于|不低于|不少于|不足|低于|小于|不高于|不超过)\s*" + _NUM + r"\s*天")),
    # 倍数
    ("times", re.compile(
        r"(超过|大于|高于|不低于|不少于|不足|低于|小于|不高于|不超过)\s*" + _NUM + r"\s*倍")),
)

_GREATER = {"超过", "大于", "高于", "不低于", "不少于", "以上"}
_LESSER = {"不足", "低于", "小于", "不高于", "不超过", "以下"}

# 证据里取实际值：与阈值同量纲
_VALUE_PATTERNS = {
    "pct": re.compile(r"(\d+(?:\.\d+)?)\s*%"),
    "yuan": re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:万元|元)"),
    "day": re.compile(r"(\d+(?:\.\d+)?)\s*天"),
    "times": re.compile(r"(\d+(?:\.\d+)?)\s*倍"),
}


def parse_threshold(text: Any) -> Optional[Tuple[str, str, float]]:
    """从要件/描述文本解析阈值条件。返回 `(量纲, 比较符, 阈值)`；解析不到返回 None。

    比较符取 `">="` / "<=" 两态（"超过"→`>` 从严按 `>=` 处理会误杀，故用严格比较缓存原词）。
    """
    s = str(text or "")
    if not s:
        return None
    for dim, pat in _THRESHOLD_PATTERNS:
        for m in pat.finditer(s):
            groups = [g for g in m.groups() if g]
            num = None
            word = ""
            for g in groups:
                if re.fullmatch(r"\d+(?:\.\d+)?", g):
                    num = float(g)
                elif g in _GREATER or g in _LESSER:
                    word = g
            if num is None:
                continue
            # 未给比较词时（如 "5% 以上"）由包围词判定
            if not word:
                tail = s[m.end():m.end() + 4]
                head = s[max(0, m.start() - 4):m.start()]
                word = "以上" if "以上" in tail else ("以下" if "以下" in tail else
                                                      ("超过" if "超过" in head else ""))
            op = ">=" if word in _GREATER else ("<=" if word in _LESSER else ">=")
            if dim == "yuan":
                seg = s[m.start():m.end()]
                if "万元" in seg:
                    num *= 10000.0
            return dim, op, num
    return None


def extract_actual(text: Any, dim: str) -> Optional[float]:
    """从证据文本里取**同量纲**的实际值；取不到返回 None（不判，不阻断）。"""
    pat = _VALUE_PATTERNS.get(dim)
    if pat is None:
        return None
    s = str(text or "")
    if not s:
        return None
    vals = []
    for m in pat.finditer(s):
        raw = m.group(1).replace(",", "")
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if dim == "yuan" and "万元" in m.group(0):
            v *= 10000.0
        vals.append(v)
    if not vals:
        return None
    # 多个候选（如"占比 32.5%、毛利率 18%"）→ 取**唯一**值；不唯一则不判（避免误杀）
    return vals[0] if len(set(vals)) == 1 else None


def check_constituent_hit(constituent_text: Any, evidence_text: Any) -> Tuple[str, str]:
    """校验「该要件是否真的达到门槛」。

    返回 `(判定, 说明)`，判定 ∈ `{"met", "unmet", "unknown"}`：
      · unknown —— 要件无阈值，或证据取不到同量纲实际值 → **放行**（不阻断）；
      · unmet   —— 实际值不满足阈值 → 调用方**不得**把该要件标为命中；
      · met     —— 实际值满足阈值。
    """
    th = parse_threshold(constituent_text)
    if not th:
        return "unknown", ""
    dim, op, limit = th
    actual = extract_actual(evidence_text, dim)
    if actual is None:
        return "unknown", ""
    unit = dict(_DIMS).get(dim, "")
    ok = (actual >= limit) if op == ">=" else (actual <= limit)
    if ok:
        return "met", ""
    return "unmet", ("未达该项要件门槛（实际 %s%s，要件门槛 %s%s%s）"
                     % (_fmt(actual), unit, op, _fmt(limit), unit))


def _fmt(v: float) -> str:
    if abs(v - round(v)) < 1e-9:
        return "{:,.0f}".format(v)
    return "{:,.2f}".format(v)

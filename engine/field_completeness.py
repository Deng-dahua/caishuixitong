# -*- coding: utf-8 -*-
"""字段截断与完整性检测（Skill 3 唯一权威）。

## 为什么要它
用户复核（2026-10-07，疑点3）：报告出现「涉及月份 2025-01、…、2025-10」而**缺 11、12 月**，
读者据此会低估涉及期间（更危险的是：**看起来完整**的截断，读者无从察觉）。
同类风险面：人数/笔数/金额被硬切片（`[:N]`）后**没有省略号**，读者以为已列全。

## 判据（两条，均数据驱动）
1. **覆盖性**：当文本**自称**列举了"涉及月份/覆盖月份/各月/全年"等时，
   其月份集合必须覆盖检查期间的全部月份；缺一即 ERROR 级问题。
2. **截断可见性**：被截断的列举**必须带可见省略号**（`…`/`......`）或**如实标注范围**
   （如"共 12 个月，此处列示前 10 个月"）。既未列全、又无省略号/范围声明 ⇒ 判"疑似静默截断"。

## 口径
- **本模块只判"是否完整/截断是否可见"，不改写数值，也不补齐数据**（缺失就是缺失）。
- 检查期间取自报告的"检查期间"字段（`YYYY-MM 至 YYYY-MM`），**唯一权威**；
  取不到期间时**不猜**，返回"无法判定"，由调用方如实说明。
"""
from __future__ import annotations
import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple

VERSION = "1.0.0"

_MONTH_RE = re.compile(r"(20\d{2})[-/年\.]?(0[1-9]|1[0-2])")
_PERIOD_RE = re.compile(r"(20\d{2})[-/年\.]?(0[1-9]|1[0-2])\s*(?:至|~|-|—|到)\s*(20\d{2})[-/年\.]?(0[1-9]|1[0-2])")

#: "自称列举了期间月份"的触发词（**数据驱动**：新增同类只加一行）
COVERAGE_CLAIM_WORDS: tuple = ("涉及月份", "覆盖月份", "各月", "每月", "全年", "各月份",
                               "涉及期间", "逐月", "按月")

#: 可见的截断标记
TRUNCATION_MARKS: tuple = ("…", "...", "……", "等", "略", "余同")


def parse_period(period: Any) -> List[str]:
    """`2025-01 至 2025-12` → ['2025-01', …, '2025-12']；无法判定返回 []。"""
    s = str(period or "")
    m = _PERIOD_RE.search(s)
    if not m:
        return []
    y1, m1, y2, m2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    out: List[str] = []
    y, mo = y1, m1
    for _ in range(600):
        out.append("%04d-%02d" % (y, mo))
        if (y, mo) == (y2, m2):
            break
        mo += 1
        if mo > 12:
            y, mo = y + 1, 1
    return out


def months_in(text: Any) -> List[str]:
    """文本里出现的月份（去重、保持出现顺序）。"""
    seen, out = set(), []
    for m in _MONTH_RE.finditer(str(text or "")):
        k = "%s-%s" % (m.group(1), m.group(2))
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def claims_coverage(text: Any) -> bool:
    s = str(text or "")
    return any(w in s for w in COVERAGE_CLAIM_WORDS)


def has_truncation_mark(text: Any) -> bool:
    return any(t in str(text or "") for t in TRUNCATION_MARKS)


def check_text(text: Any, period: Any = "") -> List[Dict[str, Any]]:
    """检测单段文本的字段完整性问题（返回问题清单，空 = 合规）。"""
    s = str(text or "")
    issues: List[Dict[str, Any]] = []
    listed = months_in(s)
    if not listed:
        return issues
    full = parse_period(period)
    if full and claims_coverage(s):
        missing = [m for m in full if m not in listed]
        if missing:
            issues.append({
                "kind": "month_gap",
                "level": "ERROR",
                "detail": "本段自称列举期间月份，但缺 %s（检查期间 %s，共 %d 个月，实列 %d 个）。"
                          % ("、".join(missing), str(period), len(full), len(listed)),
                "missing": missing, "text": s[:160],
            })
    if full and len(listed) >= 3 and claims_coverage(s) and not has_truncation_mark(s):
        # 既未列全、又无可见截断标记 ⇒ 疑似静默截断
        if len(listed) < len(full):
            issues.append({
                "kind": "silent_truncation",
                "level": "ERROR",
                "detail": "本段列举 %d 个月（期间共 %d 个）却**无可见省略号、也无范围声明** —— "
                          "读者会误以为已列全。必须补「…」或写明「共 N 个月，此处列示 M 个」。"
                          % (len(listed), len(full)),
                "text": s[:160],
            })
    return issues


def scan(obj: Any, period: Any = "", *, _path: str = "") -> List[Dict[str, Any]]:
    """递归遍历报告结构里的**字符串**做检测（迭代去环，禁递归爆栈）。"""
    out: List[Dict[str, Any]] = []
    stack: List[Tuple[str, Any]] = [("", obj)]
    seen: set = set()
    while stack:
        path, cur = stack.pop()
        if isinstance(cur, (dict, list)):
            if id(cur) in seen:
                continue
            seen.add(id(cur))
            if isinstance(cur, dict):
                for k, v in cur.items():
                    stack.append(("%s.%s" % (path, k), v))
            else:
                for i, v in enumerate(cur):
                    stack.append(("%s[%d]" % (path, i), v))
            continue
        if isinstance(cur, str):
            for iss in check_text(cur, period):
                iss["path"] = path
                out.append(iss)
    return out


def coverage_line(period: Any) -> str:
    """字段完整性声明（报告可引用的标准句）。"""
    full = parse_period(period)
    if not full:
        return "检查期间未取到（无法判定月份覆盖性，须补充期间后复核）。"
    return "字段完整性：检查期间共 %d 个月（%s ~ %s），月份/人数/笔数/金额均须逐一列示或显式标注截断。" % (
        len(full), full[0], full[-1])


__all__ = ["VERSION", "COVERAGE_CLAIM_WORDS", "TRUNCATION_MARKS", "parse_period",
           "months_in", "claims_coverage", "has_truncation_mark", "check_text",
           "scan", "coverage_line"]

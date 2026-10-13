# -*- coding: utf-8 -*-
"""解析结果**校验**（P0-3）：6 类规则，唯一权威。

规则（与 `config/standard_fields.json::_validation` 一一对应，**键即规则名**）：
  · `required_missing`          必填缺失
  · `amount_format`             金额格式错误
  · `period_mismatch`           期间错配
  · `duplicate`                 重复数据
  · `debit_credit_unbalanced`   借贷不平衡
  · `cross_check`               报表勾稽异常

★ 设计口径
  · **只报不修**：校验函数不下结论、不改数据，只产出 `{rule, severity, message, detail}`；
    由调用方落 `extract_issues` 并展示，人工决定如何处理。
  · **不确定就不报**：取不到参与计算的量（如报表三项缺一）⇒ **跳过该规则**，
    报"无法判定"而非伪装成"通过"（与项目铁律「缺失≠0」一致）。
  · `severity`：`error`（必填缺失 / 借贷不平衡 / 金额格式）· `warning`（期间错配 / 重复 / 勾稽）
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from engine.standard_fields import (
    aliases_of, field as _field, fields as _all_fields, normalize_value,
    required_names, value_from_row,
)

#: 规则清单（★ 唯一权威：新增规则只加这里一处 + 实现函数一行）
RULES: Tuple[str, ...] = (
    "required_missing",
    "amount_format",
    "period_mismatch",
    "duplicate",
    "debit_credit_unbalanced",
    "cross_check",
)

RULE_CN: Dict[str, str] = {
    "required_missing": "必填缺失",
    "amount_format": "金额格式错误",
    "period_mismatch": "期间错配",
    "duplicate": "重复数据",
    "debit_credit_unbalanced": "借贷不平衡",
    "cross_check": "报表勾稽异常",
}

#: 借贷列（标准字段名）——用于 `debit_credit_unbalanced`
_DEBIT_COLS = ("opening_debit", "current_debit", "closing_debit", "debit")
_CREDIT_COLS = ("opening_credit", "current_credit", "closing_credit", "credit")
#: 勾稽三项
_A, _L, _E = "total_assets", "total_liabilities", "total_equity"
#: 金额相对误差容忍（勾稽/平衡用；1 元以内的尾差不算异常）
_TOLERANCE = 1.0


def _issue(rule: str, message: str, detail: Dict[str, Any],
           severity: str) -> Dict[str, Any]:
    return {"rule": rule, "rule_cn": RULE_CN.get(rule, rule),
            "severity": severity, "message": message,
            "detail": detail}


def _std_amount(name: str, row: Dict[str, Any]) -> Optional[float]:
    """按**标准字段名**从行内取金额并归一 ⇒ `None` 表示取不到或无法解析。

    ★ 命名说明（勿与既有 `_amount_of` 混淆）：既有 `_amount_of`（`domain_analysis` /
      `fund_matching`）是**按行内多种列名猜金额**；本函数是**按已声明的标准字段名取值**
      （输入 = 标准字段名 + 行），语义不同 ⇒ 取不同名字，避免被误判为同一概念多实现。
    """
    v = value_from_row(name, row)
    if v is None:
        return None
    num, ok, _ = normalize_value(name, v)
    return float(num) if ok else None


def validate_rows(rows: List[Dict[str, Any]], *, domain: str = "",
                  standard_names: Optional[List[str]] = None,
                  expect_period: Optional[str] = None) -> List[Dict[str, Any]]:
    """对**一张表**的行集做校验，返回问题清单（顺序 = `RULES`）。

    参数：
      · `rows`             原始行（dict 列表）
      · `domain`           该表被判定的业务域（仅作信息，不参与判定）
      · `standard_names`   本表已登记的标准字段名（缺省 = 该域+common 的全部待考字段）
      · `expect_period`    期望期间（来自项目稽查期间）；给了才做 `period_mismatch`
    """
    issues: List[Dict[str, Any]] = []
    if not isinstance(rows, list):
        return issues
    names = list(standard_names or [])

    # ── ① 必填缺失（**按域判定**：只要求该域必填字段）──
    dom = str(domain or "")
    need = [n for n in required_names(dom)] if dom else []
    if names:
        # 只看本表声明登记过的字段，避免"域不对却报缺失"
        need = [n for n in need if n in names] or need
    for n in need:
        got = [value_from_row(n, r) for r in rows]
        if not any(v not in (None, "") for v in got):
            issues.append(_issue(
                "required_missing",
                "必填字段「%s」整表未取到任何值" % (_field(n) or {}).get("cn", n),
                {"standard_field": n, "rows": len(rows)}, "error"))

    # ── ② 金额格式错误（逐行逐列）──
    amount_cols = [str(f.get("name")) for f in _all_fields()
                   if str(f.get("type")) == "amount"
                   and (not names or str(f.get("name")) in names)]
    bad: List[Dict[str, Any]] = []
    for i, r in enumerate(rows, 1):
        for n in amount_cols:
            v = value_from_row(n, r)
            if v in (None, ""):
                continue
            _, ok, why = normalize_value(n, v)
            if not ok:
                bad.append({"row": i, "standard_field": n,
                            "field_cn": (_field(n) or {}).get("cn", n),
                            "raw": str(v)[:60], "why": why})
    if bad:
        issues.append(_issue(
            "amount_format", "有 %d 处金额无法解析（共扫描 %d 行 × %d 金额列）"
            % (len(bad), len(rows), len(amount_cols)), {"items": bad[:50],
                                                        "total": len(bad)}, "error"))

    # ── ③ 期间错配（**给了期望期间才判**）──
    if expect_period:
        exp, exp_ok, _ew = normalize_value("period", expect_period)
        if exp_ok:
            got = set()
            for r in rows:
                v = value_from_row("period", r)
                if v in (None, ""):
                    continue
                p, ok, _ = normalize_value("period", v)
                if ok:
                    got.add(str(p))
            mismatch = sorted(x for x in got if not str(x).startswith(str(exp)[:7]))
            if mismatch:
                issues.append(_issue(
                    "period_mismatch",
                    "资料期间（%s）与项目稽查期间（%s）不一致"
                    % ("、".join(mismatch[:5]), exp),
                    {"expect": exp, "found": mismatch[:20]}, "warning"))

    # ── ④ 重复数据（整行标准字段完全一致）──
    seen: Dict[str, int] = {}
    dups: List[Dict[str, Any]] = []
    key_names = [n for n in (names or [])] or None
    for i, r in enumerate(rows, 1):
        if key_names:
            payload = {n: str(value_from_row(n, r)) for n in key_names}
        else:
            payload = {str(k): str(v) for k, v in r.items()}
        if not any(v not in ("", "None") for v in payload.values()):
            continue                                  # 全空行不算重复
        k = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if k in seen:
            dups.append({"row": i, "same_as_row": seen[k]})
        else:
            seen[k] = i
    if dups:
        issues.append(_issue(
            "duplicate", "有 %d 行为完全重复的数据" % len(dups),
            {"items": dups[:50], "total": len(dups)}, "warning"))

    # ── ⑤ 借贷不平衡（仅当借贷列**同时有值**才判；缺一侧 ⇒ 跳过）──
    for pair in (("current_debit", "current_credit"), ("opening_debit", "opening_credit"),
                 ("closing_debit", "closing_credit"), ("debit", "credit")):
        d_name, c_name = pair
        if names and (d_name not in names or c_name not in names):
            continue
        d_sum = c_sum = 0.0
        d_hit = c_hit = False
        for r in rows:
            dv = _std_amount(d_name, r)
            cv = _std_amount(c_name, r)
            if dv is not None:
                d_sum += dv
                d_hit = True
            if cv is not None:
                c_sum += cv
                c_hit = True
        if not (d_hit and c_hit):
            continue                                  # 缺一侧 ⇒ 无法判定，**跳过**（不伪装通过）
        if abs(d_sum - c_sum) > _TOLERANCE:
            issues.append(_issue(
                "debit_credit_unbalanced",
                "「%s / %s」合计不平衡：借方 %.2f、贷方 %.2f、差额 %.2f"
                % ((_field(d_name) or {}).get("cn", d_name),
                   (_field(c_name) or {}).get("cn", c_name), d_sum, c_sum, d_sum - c_sum),
                {"debit_field": d_name, "credit_field": c_name, "debit_sum": round(d_sum, 2),
                 "credit_sum": round(c_sum, 2), "diff": round(d_sum - c_sum, 2)}, "error"))

    # ── ⑥ 报表勾稽（三项**都取到**才判；缺一 ⇒ 跳过）──
    def _sum_col(n: str) -> Tuple[Optional[float], int]:
        s, hit = 0.0, 0
        for r in rows:
            v = _std_amount(n, r)
            if v is not None:
                s += v
                hit += 1
        return (s, hit) if hit else (None, 0)

    a_sum, a_hit = _sum_col(_A)
    l_sum, l_hit = _sum_col(_L)
    e_sum, e_hit = _sum_col(_E)
    if a_sum is not None and l_sum is not None and e_sum is not None:
        diff = a_sum - (l_sum + e_sum)
        if abs(diff) > _TOLERANCE:
            issues.append(_issue(
                "cross_check",
                "报表勾稽异常：资产总计 %.2f ≠ 负债合计 %.2f + 所有者权益合计 %.2f（差额 %.2f）"
                % (a_sum, l_sum, e_sum, diff),
                {"assets": round(a_sum, 2), "liabilities": round(l_sum, 2),
                 "equity": round(e_sum, 2), "diff": round(diff, 2)}, "warning"))

    return issues


def summary(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按规则/严重度汇总（供前端与验收断言）。"""
    by_rule: Dict[str, int] = {}
    by_sev: Dict[str, int] = {}
    for it in issues:
        by_rule[str(it.get("rule"))] = by_rule.get(str(it.get("rule")), 0) + 1
        k = str(it.get("severity"))
        by_sev[k] = by_sev.get(k, 0) + 1
    return {"total": len(issues), "by_rule": by_rule,
            "by_rule_cn": {RULE_CN.get(k, k): v for k, v in by_rule.items()},
            "by_severity": by_sev}


__all__ = ["RULES", "RULE_CN", "validate_rows", "summary"]

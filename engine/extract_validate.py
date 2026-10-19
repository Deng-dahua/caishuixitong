# -*- coding: utf-8 -*-
"""解析结果**校验**（P0-3）：规则清单唯一权威 = 下文 `RULES`（bank 域分派见设计口径）。

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
  · **按域分派**（2026-10-19）：同一列名在不同业务域语义不同——
    `debit`/`credit` 在账簿域是借贷（Σ必须相等），在流水域是支出/收入（Σ本就不等）⇒
    bank 域走 `bank_balance_check`（余额勾稽），其余域走 `debit_credit_unbalanced`；
    发票"同号一正一负"按数电红字冲销分诊；凭证内同科目同金额多行是合并记账。
  · `severity`：`error`（必填缺失 / 借贷不平衡 / 金额格式 / 余额勾稽异常）·
    `warning`（期间错配 / 重复 / 勾稽 / 余额连续性 / 红冲分诊等）
↓ 见下：`RULES` 已扩展（P1-3 由 6 条扩到 12 条）
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from engine.numparse import to_number_checked
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
    "bank_balance_check",
    "cross_check",
    # ── P1-3 新增 6 条（全部适用所有企业，**只报不修、不确定就不报**）──
    "amount_negative",
    "null_rate",
    "date_out_of_range",
    "account_code_format",
    "tax_rate_validity",
    "duplicate_invoice_no",
)

RULE_CN: Dict[str, str] = {
    "required_missing": "必填缺失",
    "amount_format": "金额格式错误",
    "period_mismatch": "期间错配",
    "duplicate": "重复数据",
    "debit_credit_unbalanced": "借贷不平衡",
    "bank_balance_check": "银行流水余额勾稽异常",
    "cross_check": "报表勾稽异常",
    "amount_negative": "金额异常负值",
    "null_rate": "关键列缺失率过高",
    "date_out_of_range": "日期超出合理范围",
    "account_code_format": "科目编码格式异常",
    "tax_rate_validity": "税率非标准档位",
    "duplicate_invoice_no": "发票号码重复",
}

#: **报表类**金额字段（只有这些列出现负值才算"异常"；借贷列的负值可能是红字冲销，不报）
_NEG_FIELDS: Tuple[str, ...] = (
    "total_assets", "total_liabilities", "total_equity", "revenue", "cost",
)

#: 关键列填充率下限（低于此值且 > 0 ⇒ "半空"，提示列名可能未被识别）
_FILL_FLOOR: float = 0.5

#: 增值税税率**法定档位**（含历史与征收率；单位 %）
STD_TAX_RATES: Tuple[float, ...] = (0.0, 1.0, 1.5, 3.0, 5.0, 6.0, 9.0, 10.0, 11.0, 13.0, 16.0, 17.0)

#: 日期合理区间（早于此或晚于"次年年底" ⇒ 疑为笔误）
_DATE_LO: str = "2000-01-01"


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


def rate_to_percent(value: Any) -> Optional[float]:
    """税率文本 → **百分比数值**（`"13%"` ⇒ 13.0；`"0.13"` ⇒ 13.0；`13` ⇒ 13.0）。

    无法解析 ⇒ `None`（**不猜**，由调用方按"无法解析为税率"如实报）。
    """
    s = str(value if value is not None else "").strip().replace("％", "%").replace(" ", "")
    if not s:
        return None
    pct = s.endswith("%")
    if pct:
        s = s[:-1]
    num, ok = to_number_checked(s, default=None)
    if not ok or num is None:
        return None
    try:
        f = float(num)
    except (TypeError, ValueError):
        return None
    if pct:
        return f
    if 0 < f <= 1:
        return f * 100.0
    return f


def _bank_balance_issues(rows: List[Dict[str, Any]],
                         names: List[str]) -> List[Dict[str, Any]]:
    """银行流水**余额勾稽**（替代误用于流水的「借贷平衡」判据）。

    为什么不是「借方合计=贷方合计」：流水的借=支出、贷=收入，两列合计**本来
    就不该相等**（差额=期间净流入）⇒ 那条判据只适用于账簿/凭证域。

    口径（只报不修 / **不确定就不报**）：
      · 逐行取标准字段 `balance` / `debit`（借=支出）/ `credit`（贷=收入）；
      · 有金额却取不到余额的行 ⇒ 余额链被它截断 ⇒ **整表跳过**（不猜）；
        无金额也无余额的行（空行/表尾杂质）⇒ 不参与，计数如实写入 detail；
      · **按日期分组**后做**顺序无关**的组间不变量：相邻两组 R1→R2，
        「R2 的某行余额 − R1 的某行余额 == R2 的净额（Σ贷−Σ借）」应当成立
        （余额是"交易后"口径，R2 首笔前的余额必是 R1 某行的余额）。
        同日多笔的先后不可知 ⇒ 组内不判、组间用**集合存在性**判 ⇒ 既不漏报、
        也不因排序歧义误报（实测：0720 两笔同秒、真实顺序与稳定排序相反，
        朴素逐行链式检查会**假报断裂**——这正是弃用链式的原因）；
      · 组间不变量不成立 ⇒ warning「余额连续性断裂」（对账单被抽行/改动的信号）；
      · 聚合：最早/最晚日期组都只有一行时，期初（余额−贷+借）＋Σ贷−Σ借＝期末，
        差额超容忍 ⇒ error「余额勾稽异常」——通常意味着流水缺行或余额列解析错位。
    """
    issues: List[Dict[str, Any]] = []
    if names and "balance" not in names:
        return issues
    recs: List[Dict[str, Any]] = []
    junk = 0
    for i, r in enumerate(rows, 1):
        bal = _std_amount("balance", r)
        dv = _std_amount("debit", r) if (not names or "debit" in names) else None
        cv = _std_amount("credit", r) if (not names or "credit" in names) else None
        if bal is None:
            if dv is None and cv is None:
                junk += 1                             # 无金额也无余额：杂质行，不参与
                continue
            return issues                             # 有金额却无余额：链被截断，不猜
        raw_d = value_from_row("tx_date", r) if (not names or "tx_date" in names) else None
        dkey = ""
        if raw_d not in (None, ""):
            pv, ok, _ = normalize_value("tx_date", raw_d)
            dkey = str(pv) if ok else str(raw_d)
        recs.append({"row": i, "bal": bal, "d": dv or 0.0, "c": cv or 0.0, "date": dkey})
    if not recs:
        return issues
    # 无日期的行无法定位到组 ⇒ 只能整表跳过（不猜它在链上的位置）
    if any(not x["date"] for x in recs):
        return issues
    recs.sort(key=lambda x: x["date"])

    # 按日期分组（升序；同日多笔在组内，顺序歧义被"集合存在性"吸收）
    groups: List[Dict[str, Any]] = []
    for x in recs:
        if groups and groups[-1]["date"] == x["date"]:
            groups[-1]["rows"].append(x)
        else:
            groups.append({"date": x["date"], "rows": [x]})
    for g in groups:
        g["net"] = sum(x["c"] - x["d"] for x in g["rows"])
        g["bals"] = [x["bal"] for x in g["rows"]]

    breaks: List[Dict[str, Any]] = []
    checked = 0
    for g1, g2 in zip(groups, groups[1:]):
        checked += 1
        ok = any(abs((y - x) - g2["net"]) <= _TOLERANCE
                 for x in g1["bals"] for y in g2["bals"])
        if not ok:
            breaks.append({"from_date": g1["date"], "to_date": g2["date"],
                           "net_g2": round(g2["net"], 2),
                           "bals_from": [round(b, 2) for b in g1["bals"]][:8],
                           "bals_to": [round(b, 2) for b in g2["bals"]][:8]})
    if breaks and checked:
        issues.append(_issue(
            "bank_balance_check",
            "余额连续性断裂 %d 处（判了 %d 个相邻日期组；组内多笔不判顺序）："
            "上一日期组的余额经「＋收入－支出」推不到下一日期组的任何余额 —— "
            "请核对流水是否被抽行/改动，或解析是否错位" % (len(breaks), checked),
            {"items": breaks[:50], "total": len(breaks), "checked_groups": checked,
             "junk_rows_skipped": junk}, "warning"))

    # 聚合勾稽：首尾组都只有一行时，期初/期末无歧义才判
    if len(groups) >= 2 and len(groups[0]["rows"]) == 1 and len(groups[-1]["rows"]) == 1:
        f, l = groups[0]["rows"][0], groups[-1]["rows"][0]
        opening = f["bal"] - f["c"] + f["d"]
        closing = l["bal"]
        c_sum = sum(x["c"] for x in recs)
        d_sum = sum(x["d"] for x in recs)
        expect = opening + c_sum - d_sum
        diff = closing - expect
        if abs(diff) > _TOLERANCE:
            issues.append(_issue(
                "bank_balance_check",
                "余额勾稽异常：期初 %.2f ＋ 收入合计 %.2f － 支出合计 %.2f = %.2f，"
                "但期末余额为 %.2f（差额 %.2f）——通常意味着流水缺行、或余额列解析错位"
                % (opening, c_sum, d_sum, expect, closing, diff),
                {"opening": round(opening, 2), "credit_sum": round(c_sum, 2),
                 "debit_sum": round(d_sum, 2), "expect_closing": round(expect, 2),
                 "closing": round(closing, 2), "diff": round(diff, 2),
                 "junk_rows_skipped": junk}, "error"))
    return issues


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
    #   ★ 2026-10-19（按域修正）：凭证/序时账里「同一凭证内」出现两行完全相同的
    #     分录是**合并记账的正常形态**（记-4 里两笔 9.00 元手续费就是两行）——
    #     实测 42 条"重复数据"抽样全部属于此类。⇒ `ledger` 域：同凭证号内的
    #     重复行**不报**；跨凭证的整行重复才报（那才是真克隆）。凭证号取不到 ⇒
    #     无法区分，维持原判（不猜）。
    seen: Dict[str, Tuple[int, str]] = {}
    dups: List[Dict[str, Any]] = []
    within_voucher = 0
    key_names = [n for n in (names or [])] or None
    for i, r in enumerate(rows, 1):
        if key_names:
            payload = {n: str(value_from_row(n, r)) for n in key_names}
        else:
            payload = {str(k): str(v) for k, v in r.items()}
        if not any(v not in ("", "None") for v in payload.values()):
            continue                                  # 全空行不算重复
        k = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        vno = str(value_from_row("voucher_no", r) or "").strip() if dom == "ledger" else ""
        if k in seen:
            if vno and seen[k][1] == vno:
                within_voucher += 1                   # 同凭证内：合并记账，正常
                continue
            dups.append({"row": i, "same_as_row": seen[k][0]})
        else:
            seen[k] = (i, vno)
    if dups:
        msg = "有 %d 行为完全重复的数据" % len(dups)
        if within_voucher:
            msg += "（另有 %d 行属同一凭证内的重复分录——合并记账，不计入）" % within_voucher
        issues.append(_issue(
            "duplicate", msg,
            {"items": dups[:50], "total": len(dups),
             "within_voucher_skipped": within_voucher}, "warning"))

    # ── ⑤ 借贷不平衡 / 银行流水余额勾稽（**按域分派**）──
    #   ★ 2026-10-19（用户质询「银行流水提示借贷不平衡，合理吗」——**不合理**）：
    #     流水的「借方发生额=支出、贷方发生额=收入」，两列合计**本来就不该相等**
    #     （差额 = 期间净流入/流出）。把账簿的借贷平衡判据套到流水上，等于把常态
    #     误报成 error（实测库里 37 条全部打在银行流水上，如「借方 254,549.80、
    #     贷方 312,120.00、差额 -57,570.20」——那只是这个月收大于付）。
    #     ⇒ 分派：`bank` 域 → 余额勾稽（`bank_balance_check`）；其余域（账簿/凭证）
    #       → 借贷平衡（原判据不变）。
    if dom == "bank":
        issues.extend(_bank_balance_issues(rows, names))
    else:
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
                continue                              # 缺一侧 ⇒ 无法判定，**跳过**（不伪装通过）
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

    # ══════════════════════════════════════════════════════════════════════
    # P1-3 新增 6 条（口径一致：**只报不修** / **不确定就不报** / 全部 warning 级）
    # ══════════════════════════════════════════════════════════════════════
    # ── ⑦ 金额异常负值（**报表类**字段；借贷列的负值可能是红字冲销 ⇒ 不报）──
    neg: List[Dict[str, Any]] = []
    for i, r in enumerate(rows, 1):
        for n in _NEG_FIELDS:
            if names and n not in names:
                continue
            v = _std_amount(n, r)
            if v is not None and v < 0:
                neg.append({"row": i, "standard_field": n,
                            "field_cn": (_field(n) or {}).get("cn", n),
                            "value": round(v, 2)})
    if neg:
        issues.append(_issue(
            "amount_negative",
            "有 %d 处报表类金额为负值（%s）—— 若属红字冲销请核实后忽略"
            % (len(neg), "、".join(sorted({str(x["field_cn"]) for x in neg}))),
            {"items": neg[:50], "total": len(neg)}, "warning"))

    # ── ⑧ 关键列填充率过低（**半空**：0 < 命中 < 下限；全空由 required_missing 报）──
    #   ★ `names` 为空时**必须遍历全部标准字段**：否则"不传 names"的调用方
    #     （如 `validate_rows(rows)`）会让本规则**永不触发**（实测踩过：
    #     样例 `[{"购方名称":"A"},{"购方名称":""},{"购方名称":""}]` 一条都不报）。
    fill_names = list(names) or [str(f.get("name")) for f in _all_fields()]
    lowfill: List[Dict[str, Any]] = []
    for n in fill_names:
        hit = sum(1 for r in rows if value_from_row(n, r) not in (None, ""))
        if rows and 0 < hit < len(rows) * _FILL_FLOOR:
            lowfill.append({"standard_field": n,
                            "field_cn": (_field(n) or {}).get("cn", n),
                            "hits": hit, "rows": len(rows),
                            "ratio": round(hit / len(rows), 4)})
    if lowfill:
        issues.append(_issue(
            "null_rate",
            "有 %d 个字段填充率低于 %d%%（列名可能未被识别，或该列本就稀疏）"
            % (len(lowfill), int(_FILL_FLOOR * 100)),
            {"items": lowfill[:50], "total": len(lowfill)}, "warning"))

    # ── ⑨ 日期超出合理范围（解析失败的不在此重复报）──
    date_cols = [str(f.get("name")) for f in _all_fields()
                 if str(f.get("type")) == "date"
                 and (not names or str(f.get("name")) in names)]
    bad_dates: List[Dict[str, Any]] = []
    hi = ""
    if date_cols:
        import datetime as _dt                            # noqa: PLC0415
        hi = "%d-12-31" % (_dt.date.today().year + 1)
        for i, r in enumerate(rows, 1):
            for n in date_cols:
                v = value_from_row(n, r)
                if v in (None, ""):
                    continue
                pv, ok, _why = normalize_value(n, v)
                if not ok:
                    continue
                s = str(pv)
                if s < _DATE_LO or s > hi:
                    bad_dates.append({"row": i, "standard_field": n, "value": s})
    if bad_dates:
        issues.append(_issue(
            "date_out_of_range",
            "有 %d 处日期超出合理区间（%s ~ 次年年底）" % (len(bad_dates), _DATE_LO),
            {"items": bad_dates[:50], "total": len(bad_dates),
             "range": [_DATE_LO, hi]}, "warning"))

    # ── ⑩ 科目编码格式异常（应为 4~12 位纯数字）──
    if not names or "account_code" in names:
        bad_code: List[Dict[str, Any]] = []
        for i, r in enumerate(rows, 1):
            v = value_from_row("account_code", r)
            if v in (None, ""):
                continue
            s = str(v).strip()
            if not s.isdigit() or not (4 <= len(s) <= 12):
                bad_code.append({"row": i, "value": s[:20]})
        if bad_code:
            issues.append(_issue(
                "account_code_format",
                "有 %d 处科目编码格式异常（应为 4~12 位纯数字）" % len(bad_code),
                {"items": bad_code[:50], "total": len(bad_code)}, "warning"))

    # ── ⑪ 税率非标准档位 ──
    if not names or "tax_rate" in names:
        bad_rate: List[Dict[str, Any]] = []
        for i, r in enumerate(rows, 1):
            v = value_from_row("tax_rate", r)
            if v in (None, ""):
                continue
            pct = rate_to_percent(v)
            if pct is None:
                bad_rate.append({"row": i, "value": str(v)[:20], "why": "无法解析为税率"})
            elif round(float(pct), 2) not in STD_TAX_RATES:
                bad_rate.append({"row": i, "value": str(v)[:20], "why": "不在法定档位"})
        if bad_rate:
            issues.append(_issue(
                "tax_rate_validity",
                "有 %d 处税率不在法定档位（%s）"
                % (len(bad_rate), "、".join("%g%%" % x for x in STD_TAX_RATES)),
                {"items": bad_rate[:50], "total": len(bad_rate)}, "warning"))

    # ── ⑫ 发票号码重复（**只看号码**；整行重复由 `duplicate` 报，两者不重叠）──
    #   ★ 2026-10-19（按税务常识修正）：数电发票平台导出时，**红字冲销与蓝票同号**——
    #     同一 20 位号码一行正数、一行负数（实测 117.22 / -34.25）是**正常形态**，
    #     不是"重复导入或错填"。⇒ 按金额方向分诊：
    #       一正一负 ⇒ 疑似红字冲销（如实说明，请核实对应关系，不吓人）；
    #       同向同额 ⇒ 真重复（维持原措辞）；
    #       同向不同额 ⇒ 同号多行且金额同向，须人工核对。
    if not names or "invoice_no" in names:
        seen_no: Dict[str, Tuple[int, float]] = {}
        dup_no: List[Dict[str, Any]] = []
        red_pairs: List[Dict[str, Any]] = []
        true_dups: List[Dict[str, Any]] = []
        mixed: List[Dict[str, Any]] = []

        def _amt(r: Dict[str, Any]) -> Optional[float]:
            for n in ("invoice_amount", "amount"):    # 发票域权威名 + 兜底
                a = _std_amount(n, r)
                if a is not None:
                    return a
            return None

        for i, r in enumerate(rows, 1):
            v = value_from_row("invoice_no", r)
            s = str(v).strip() if v not in (None, "") else ""
            if not s:
                continue
            amt = _amt(r)
            if s in seen_no:
                j, j_amt = seen_no[s]
                entry = {"row": i, "invoice_no": s, "same_as_row": j,
                         "amount_this": round(amt, 2) if amt is not None else None,
                         "amount_prev": round(j_amt, 2) if j_amt is not None else None}
                dup_no.append(entry)
                if amt is not None and j_amt is not None and (amt >= 0) != (j_amt >= 0):
                    entry["kind"] = "red_flush"
                    red_pairs.append(entry)
                elif amt is not None and j_amt is not None and abs(amt - j_amt) <= _TOLERANCE:
                    entry["kind"] = "true_dup"
                    true_dups.append(entry)
                else:
                    entry["kind"] = "check"
                    mixed.append(entry)
            else:
                seen_no[s] = (i, amt if amt is not None else 0.0)
        if dup_no:
            parts: List[str] = []
            if red_pairs:
                parts.append("%d 对「一正一负」——符合数电发票红字冲销形态"
                             "（平台把蓝票与红字一并导出，同号属正常），请核对冲销对应关系"
                             % len(red_pairs))
            if true_dups:
                parts.append("%d 对同号同额——可能是重复导入，须人工排查" % len(true_dups))
            if mixed:
                parts.append("%d 对同号同向不同额——请核对是否分次开票或拆行" % len(mixed))
            issues.append(_issue(
                "duplicate_invoice_no",
                "有 %d 行发票号码与前面的行重复：%s" % (len(dup_no), "；".join(parts)),
                {"items": dup_no[:50], "total": len(dup_no),
                 "red_flush": len(red_pairs), "true_dup": len(true_dups),
                 "check": len(mixed)}, "warning"))

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


__all__ = ["RULES", "RULE_CN", "STD_TAX_RATES", "rate_to_percent",
           "validate_rows", "summary"]

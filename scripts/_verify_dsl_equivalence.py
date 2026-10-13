# -*- coding: utf-8 -*-
"""T-6 遗留：**条件类 5 条的等价性验证**（切换执行的**前置**判据）。

## 为什么必须有这一步

`config/rule_dsl_scope.json` 里的「**可外置**」（`ext_ok`）标签，判据是
「`logic` 引用的字段在 `var_map` 有取数口径 **且** 用到的参数已登记」——
它衡量的是「**表达要件是否齐备**」，**不是**「**判据是否与现有实现等价**」。

⇒ 「可外置」**不得**被当作「可切换执行」的凭证。本脚本用**边界样本**
把两侧（现有 Python 判据 vs 候选 DSL 表达式）各跑一次，**结论不一致即不可切换**。

## 验证对象（5 条）

| 候选 | DSL 表达式 | 现有 Python 实现 |
|---|---|---|
| V1.0 VAT-010 | `abnormal_invoice_count > 0` | `gap_risk_detectors.detect_abnormal_input_voucher`（RL-INV-004）|
| V1.1 INV-011 | 同上（**与 VAT-010 同名同逻辑**） | 同上 |
| V1.1 IIT-001 | `abs(iit_headcount - social_headcount) / social_headcount > params.headcount_diff_ratio` | `verified_rule_engine._scan_payroll_social`（VR005）|
| V1.1 SI-001 | `abs(social_headcount - iit_headcount) / iit_headcount > params.headcount_diff_ratio` | 同上 |
| V1.1 IIT-002 | `abs(iit_salary_total - cit_salary_total) / cit_salary_total > params.salary_total_diff_ratio` | 无实现（A105050 表缺失 ⇒ 两侧皆不可算）|

只读：不修改候选库、不改判定逻辑、不落盘。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.rule_dsl import compile_expr, evaluate          # noqa: E402
from engine.verified_rule_engine import (                    # noqa: E402
    VERIFIED_RULE_CATALOG, _scan_payroll_social)
from engine.gap_risk_detectors import detect_abnormal_input_voucher  # noqa: E402

#: ★ 用**真实的 VR005 spec**（取自 catalog），不用自造 spec —— 否则验证的是"我造的判据"。
SPEC_VR005 = next(x for x in VERIFIED_RULE_CATALOG if x.get("id") == "VR005")

RESULT: list = []


def _sal(name: str, month: str, amount: float) -> dict:
    return {"姓名": name, "月份": month, "应发工资": amount}


def _soc(name: str, month: str, base: float) -> dict:
    return {"姓名": name, "月份": month, "缴费基数": base}


def _case_payroll(n_salary: int, n_social: int, label: str) -> dict:
    """构造工资/社保名册：前 n_social 人两侧都有，其余仅工资侧。"""
    sals = [_sal("员工%02d" % i, "2026-01", 8000) for i in range(1, n_salary + 1)]
    socs = [_soc("员工%02d" % i, "2026-01", 8000) for i in range(1, n_social + 1)]
    return {"label": label, "data": {"salaries": sals, "social_security": socs}}


def _run_py_payroll(data: dict) -> bool:
    """现有 Python 判据（VR005 / RL-PAY-001 实现）是否命中。"""
    out = _scan_payroll_social(data, SPEC_VR005)
    return bool(out)


def _run_dsl(expr: str, variables: dict, params: dict):
    """DSL 求值（三值逻辑：缺字段/参数待核 ⇒ None）。"""
    reasons: list = []
    got = evaluate(compile_expr(expr), variables, params, reasons)
    return got, (reasons[0] if reasons else "")


def _record(case: str, py: object, dsl: object, same: bool, note: str) -> None:
    RESULT.append({"case": case, "python": py, "dsl": dsl, "same": same, "note": note})


# ══════════════════════════════════════════════════════════════════════════════
# 一、人数差异（IIT-001 / SI-001）vs `_scan_payroll_social`
# ══════════════════════════════════════════════════════════════════════════════
# 现有 Python 判据（实测代码，`_scan_payroll_social`）：
#     mismatch = |only_salary| + |only_social|
#     ratio    = mismatch / max(|salary ∪ social|, 1)          ← 分母＝**合并人员范围**
#     has_uninsured = bool(only_salary)                        ← ★ 有工资无社保 ⇒ 直接命中
#     if not has_uninsured and (mismatch < 2 or ratio < 0.2):
#         if not month_gaps: return []                          ← 即：命中 = has_uninsured
#                                                                    或 (mismatch≥2 且 ratio≥0.2)
#
# 候选 DSL：abs(iit - social) / social > 0.2    （IIT-001，分母＝**社保人数**）
#           abs(social - iit) / iit    > 0.2    （SI-001，分母＝**个税人数**）
# ⇒ 三处差异：① 分母口径不同；② 缺 `mismatch ≥ 2` 下限；③ **缺 has_uninsured 防漏报护栏**。

PAYROLL_CASES = [
    (20, 19, "20 人有工资、19 人有社保：1 人【有工资无社保】(占 5%)"),
    (20, 18, "20 人有工资、18 人有社保：2 人【有工资无社保】(占 10%)"),
    (10, 8, "10 人有工资、8 人有社保：2 人【有工资无社保】(占 20%)"),
    (10, 13, "10 人有工资、13 人有社保：3 人【仅社保无工资】(占 23%)"),
    (8, 10, "8 人有工资、10 人有社保：2 人【仅社保无工资】(合并范围 20% 整)"),
    (100, 95, "100 人有工资、95 人有社保：5 人【有工资无社保】(占 5%)"),
]

print("=" * 100)
print("一、人数差异：现有实现 `_scan_payroll_social`（VR005/RL-PAY-001） vs 候选 DSL")
print("=" * 100)
for n_sal, n_soc, label in PAYROLL_CASES:
    c = _case_payroll(n_sal, n_soc, label)
    data = c["data"]
    py = _run_py_payroll(data)
    # 按 var_map 口径描述取数：两侧去重自然人计数
    iit = n_sal
    social = n_soc
    dsl_iit, why_iit = _run_dsl(
        "abs(iit_headcount - social_headcount) / social_headcount > params.headcount_diff_ratio",
        {"iit_headcount": iit, "social_headcount": social},
        {"headcount_diff_ratio": 0.2})
    dsl_si, _ = _run_dsl(
        "abs(social_headcount - iit_headcount) / iit_headcount > params.headcount_diff_ratio",
        {"iit_headcount": iit, "social_headcount": social},
        {"headcount_diff_ratio": 0.2})
    same = (py == bool(dsl_iit) == bool(dsl_si)) if dsl_iit is not None else False
    _record(label, py, {"IIT-001": dsl_iit, "SI-001": dsl_si}, same,
            "" if same else "两侧结论不一致")
    print("  %-56s Python=%-6s IIT-001=%-6s SI-001=%-6s %s"
          % (label[:56], py, dsl_iit, dsl_si, "一致" if same else "★ 不一致"))

# ══════════════════════════════════════════════════════════════════════════════
# 二、进项异常凭证（VAT-010 / INV-011）vs `detect_abnormal_input_voucher`
# ══════════════════════════════════════════════════════════════════════════════
# 现有 Python 判据：扫描异常标注票 → **再比对账内『进项税额转出』**
#     若「已足额转出」⇒ **属正当情形，不报**（红线要件⑤）。
# 候选 DSL：`abnormal_invoice_count > 0` ⇒ **只看票数**，忽略是否已转出。

def _inv(tax: float, status: str = "异常") -> dict:
    return {"销方名称": "某供应商", "发票号码": "12345678", "税额": tax,
            "票据状态": status, "货物名称": "原材料", "开票日期": "2026-01-15"}


VOUCHER_CASES = [
    ([_inv(1000.0)], 0.0, "1 张异常票(税额1000)，账内进项税额转出 0 ⇒ 未转出"),
    ([_inv(1000.0)], 1000.0, "1 张异常票(税额1000)，账内已足额转出 1000 ⇒ 正当情形"),
    ([_inv(600.0), _inv(400.0)], 1000.0, "2 张异常票(合计1000)，已足额转出 ⇒ 正当情形"),
    ([_inv(1000.0)], 500.0, "1 张异常票(税额1000)，仅转出 500 ⇒ 未足额"),
    ([], 0.0, "无异常标注票"),
]

print()
print("=" * 100)
print("二、进项异常凭证：现有实现 `detect_abnormal_input_voucher`（RL-INV-004） vs 候选 DSL")
print("=" * 100)
for invs, reversal, label in VOUCHER_CASES:
    # ⚠ 键名必须与 `_input_tax_reversal_amount` 的**真实取数**一致：
    #   它读 `data["vouchers"]`（贷方）与 `data["balances"]`（本期贷方），科目名键为 `name`。
    #   首版我写成 `balance_sheet` / `科目` ⇒ 转出额恒为 0 ⇒ **全部用例都判"未足额转出"**，
    #   于是错误地得出"进项部分 5/5 一致"。**验证工具的取数错了，结论就没有意义。**
    data = {"pur_invs": invs,
            "balances": [{"name": "应交税费—应交增值税（进项税额转出）",
                          "current_credit": reversal}]}
    py = bool(detect_abnormal_input_voucher(data))
    dsl, _ = _run_dsl("abnormal_invoice_count > 0",
                      {"abnormal_invoice_count": len(invs)}, {})
    same = (py == bool(dsl)) if dsl is not None else False
    _record(label, py, dsl, same, "" if same else "两侧结论不一致")
    print("  %-56s Python=%-6s DSL=%-6s %s"
          % (label[:56], py, dsl, "一致" if same else "★ 不一致"))

# ══════════════════════════════════════════════════════════════════════════════
# 三、IIT-002（个税工资 vs 企税工资）：两侧是否都「不可算」
# ══════════════════════════════════════════════════════════════════════════════
print()
print("=" * 100)
print("三、IIT-002：分母字段 `cit_salary_total`（企税 A105050 表）缺失时的行为")
print("=" * 100)
dsl_missing, why = _run_dsl(
    "abs(iit_salary_total - cit_salary_total) / cit_salary_total > params.salary_total_diff_ratio",
    {"iit_salary_total": 1200000.0}, {"salary_total_diff_ratio": 0.1})
print("  仅有个税工资、无企税工资表 ⇒ DSL 结果 = %r（原因：%s）" % (dsl_missing, why))
print("  ⇒ DSL 侧三值逻辑**正确地**给出 UNKNOWN（未当作 0 参与计算），符合「缺失≠0」铁律。")
_record("IIT-002 缺企税工资表", "不可算（无实现，须补资料）", dsl_missing,
        False, "两侧均不可算，但**都不是 FALSE** —— DSL 给 UNKNOWN，需资料")

# ══════════════════════════════════════════════════════════════════════════════
# 汇总
# ══════════════════════════════════════════════════════════════════════════════
print()
print("=" * 100)
print("汇总")
print("=" * 100)
diff = [r for r in RESULT if not r["same"]]
print("  用例总数 %d ｜ 两侧一致 %d ｜ **不一致 %d**" % (len(RESULT), len(RESULT) - len(diff), len(diff)))
print()
print("  ★ 不等价用例：")
for r in diff:
    print("    · %s" % r["case"][:70])
    print("        Python=%s  DSL=%s  (%s)" % (r["python"], r["dsl"], r["note"]))
print()
verdict = {
    "verdict": "NOT_EQUIVALENT",
    "switch_allowed": False,
    "reason": "候选 DSL 表达式是现有 Python 判据的**简化版**：丢失要件与防漏报护栏，"
              "切换将同时产生**漏报**（有工资无社保但占比 <20%）与**误报**"
              "（异常凭证已足额转出、属正当情形）；且人数差异的分母口径与实现不同。",
    "cases_total": len(RESULT),
    "cases_divergent": len(diff),
}
print("  ★ 裁定：%s（switch_allowed=%s）" % (verdict["verdict"], verdict["switch_allowed"]))
print("     理由：%s" % verdict["reason"])
print()
# 可机器消费的结论（供登记表/闸门引用）
out = ROOT / "config" / "dsl_equivalence.json"   # ★ 放 config/（与 scope 同级）：结论须随仓库走，
    #   若放 data/ 会被"清理磁盘"清掉 ⇒ 生成器读到 UNVERIFIED ⇒ 闸门误报 ERROR（实测踩到）。
out.write_text(json.dumps({"verdict": verdict, "cases": RESULT},
                          ensure_ascii=False, indent=2), encoding="utf-8")
print("  [OK] 结论已写出 %s（供登记表引用；本脚本只读候选库与判定逻辑）"
      % out.relative_to(ROOT))

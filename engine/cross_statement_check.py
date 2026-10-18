# -*- coding: utf-8 -*-
"""账表 ↔ 申报表跨表勾稽：**利润总额**（GAP-11）。

为什么单独建
----------
测评实证（META-SYSTEM-COMPLETENESS-AUDIT 3.4）：全库对 `利润总额` 的引用共 26 处，
**没有一处**做"财务报表利润总额 ↔ 企业所得税申报表利润总额"的比对。
最接近的 `rulelist_v1.scan_cit_003` 比的是**同一张申报表内部**的
「利润总额 vs 应纳税所得额」——那是表内自洽性检查，不是跨表勾稽。

口径（缺失≠0，三态明示）
--------------------
   1. 两侧都能取到 ⇒ 算差异率；超阈值（`DIFF_RATIO=5%` 且 `DIFF_MIN=1万元`）产出疑点；
   2. 只有一侧 ⇒ **不出结论**，返回 `status="one_sided"`（由覆盖度模块去要求补资料）；
   3. 都取不到 ⇒ `status="unavailable"`。

★ 为什么阈值同时要求比例和绝对额：小企业几万元的差额比例可能很大但无审计意义；
  大企业 4% 也可能是百万级错报。两个条件同时满足才报。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.numparse import to_number

#: 差异率阈值 与 最小绝对额（元）—— 两者**同时**满足才报
DIFF_RATIO = 0.05
DIFF_MIN = 10000.0


def _first_number(row: Dict, keys) -> Optional[float]:
    for k in keys:
        if k in row and row.get(k) not in (None, ""):
            v = to_number(row.get(k))
            if v or str(row.get(k)).strip() in ("0", "0.0", "0.00"):
                return float(v)
    return None


def _cit_profit_total(tax_declarations) -> Optional[float]:
    """企业所得税申报表的利润总额（多期求和；单期取该期）。"""
    total = 0.0
    got = False
    for r in (tax_declarations or []):
        if not isinstance(r, dict):
            continue
        t = str(r.get("_declaration_type") or "").lower()
        if t not in ("cit", "cit_declaration", "企业所得税", ""):
            # 明确是增值税等其他表的，跳过；空类型不排除（解析器可能未打标）
            if t not in ("",):
                continue
        v = _first_number(r, ("profit_total", "利润总额", "profit_amount"))
        if v is None:
            continue
        total += v
        got = True
    return round(total, 2) if got else None


def run_cross_statement_check(income_stmt: Optional[Dict] = None,
                              tax_declarations=None,
                              company_name: str = "") -> Dict[str, Any]:
    """执行"利润总额"跨表勾稽，返回结构化结果（`status` 三态 + 疑点）。"""
    is_ = income_stmt if isinstance(income_stmt, dict) else {}
    book_profit = _first_number(is_, ("profit_total", "利润总额", "net_profit"))
    decl_profit = _cit_profit_total(tax_declarations)

    out: Dict[str, Any] = {
        "available": False,
        "company": company_name,
        "book_profit_total": book_profit,
        "declared_profit_total": decl_profit,
        "book_basis": str(is_.get("profit_total_basis") or ""),
        "diff": None,
        "diff_ratio": None,
        "status": "unavailable",
        "findings": [],
    }

    if book_profit is None and decl_profit is None:
        out["summary"] = "既未取得可用的利润表数据，也未取得企业所得税申报表，本项勾稽无法执行。"
        return out
    if book_profit is None:
        out["status"] = "one_sided"
        out["summary"] = ("已取得企业所得税申报表利润总额 %s 元，但报表侧利润总额未取到"
                          "（缺利润表或科目余额表），本项勾稽无法执行。"
                          % format(decl_profit, ",.2f"))
        return out
    if decl_profit is None:
        out["status"] = "one_sided"
        out["summary"] = ("已取得报表侧利润总额 %s 元，但未取得企业所得税申报表"
                          "（或其利润总额未能提取），本项勾稽无法执行。"
                          % format(book_profit, ",.2f"))
        return out

    diff = round(decl_profit - book_profit, 2)
    ratio = round(diff / book_profit, 4) if book_profit else None
    out.update({"available": True, "status": "compared", "diff": diff, "diff_ratio": ratio})

    if abs(diff) >= DIFF_MIN and ratio is not None and abs(ratio) >= DIFF_RATIO:
        detail = ("利润表（或科目余额表反推）利润总额 %s 元，企业所得税申报表利润总额 %s 元，"
                  "相差 %s 元（%.1f%%）。两者本应一致：申报表 A100000 第13行「利润总额」"
                  "直接取自财务报表，差异说明报表与申报之间存在口径或抄报错误。"
                  % (format(book_profit, ",.2f"), format(decl_profit, ",.2f"),
                     format(abs(diff), ",.2f"), ratio * 100))
        if out["book_basis"]:
            detail += "（报表侧口径：%s）" % out["book_basis"]
        out["findings"].append({
            "type": "财务报表与所得税申报表利润总额不一致",
            "level": "中风险",
            "score": 6,
            "redline_id": "RL-CIT-008",
            "category": "表间勾稽",
            "detail": detail,
            "how_found": ("分别取报表侧利润总额（利润表/科目余额表反推）与企业所得税申报表"
                          "A100000 利润总额，比对差异率与绝对额（同时超 5% 且 1 万元才计入）"),
            "policy_ref": ("《中华人民共和国企业所得税法》第五十四条（报送年度纳税申报表）；"
                           "《中华人民共和国税收征收管理法》第六十三条"),
            "suggestion": ("核对申报表 A100000 第13行与财务报表利润总额是否一致；"
                           "若为口径差异（如报表侧未含营业外收支），应在底稿中说明并统一口径；"
                           "若确属申报错误，应更正申报。"),
            "observed_metrics": {
                "book_profit_total": book_profit,
                "declared_profit_total": decl_profit,
                "diff": diff,
                "diff_ratio": ratio,
                "book_basis": out["book_basis"],
            },
            "constituent_hits": [{
                "index": 1,
                "evidence": "报表侧 %s vs 申报侧 %s，差异 %s 元（%.1f%%）" % (
                    format(book_profit, ",.2f"), format(decl_profit, ",.2f"),
                    format(abs(diff), ",.2f"), ratio * 100),
            }],
        })
        out["summary"] = ("报表侧利润总额 %s 元 与 申报侧 %s 元 相差 %s 元（%.1f%%），超过阈值"
                          "（5%% 且 1 万元）。" % (
                              format(book_profit, ",.2f"), format(decl_profit, ",.2f"),
                              format(abs(diff), ",.2f"), ratio * 100))
    else:
        out["summary"] = ("报表侧利润总额 %s 元 与 申报侧 %s 元 相差 %s 元（%.1f%%），"
                          "未超阈值（5%% 且 1 万元）。" % (
                              format(book_profit, ",.2f"), format(decl_profit, ",.2f"),
                              format(abs(diff), ",.2f"), (ratio or 0) * 100))
    return out

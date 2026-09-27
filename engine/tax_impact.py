# -*- coding: utf-8 -*-
"""潜在税额影响量化测算（2026-09-27，P1）。

用户诉求（P1）：资深稽查报告应给每项疑点算"值多少钱"——**潜在税额影响**，
并汇总"本轮潜在税额敞口"。

设计纪律（严格遵守项目铁律）：
  · **取不到就明说"未量化"**，绝不用默认值/文本里随便抓一个数当金额顶数
    （实测教训：把"账面成本总额 418 万"当成成本项敞口，纯属口径错误）。
  · 只认**关键词锚定**的金额（"涉及金额/差额/未匹配金额/少缴/虚增…"+ 数字 + 元），
    且必须 ≥ `_MIN_AMOUNT`（元），否则视为未取得。
  · 测算**必须标注口径与假设**（税率、是否含小微优惠等），并声明"仅供评估量级，
    不构成核定；实际以核实后依法核定为准"。
  · 税率来自 `_RATES` 单一表；新增税种只加一行。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from engine.numparse import to_number_checked

# 低于此金额不作为敞口（滤掉单价、计数、比率等噪音）
_MIN_AMOUNT = 1000.0

# 金额关键词锚（数字必须紧跟在这些词之后才认）
_AMOUNT_KW = (
    "涉及金额", "涉案金额", "未匹配金额", "未匹配", "差额", "差异额", "差异",
    "缺口", "少计收入", "少计销项", "少计", "少缴", "多抵", "虚增", "虚列",
    "隐匿收入", "未申报收入", "未开票收入", "价税合计", "调整金额", "涉及税额",
    "成本列支金额", "开票额",
)
_AMOUNT_PAT = re.compile(
    r"(?:" + "|".join(_AMOUNT_KW) + r")[^0-9¥￥]{0,12}?([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*元"
)

# 税率表（单一出处）：税种 → (税率, 口径说明)
_RATES: Dict[str, tuple] = {
    "增值税": (0.13, "按 13% 货物/一般服务适用税率测算；实际应按票面适用税率（13%/9%/6%/3%）复核"),
    "企业所得税": (0.25, "按 25% 法定税率测算；小型微利企业另有优惠，实际以汇算清缴为准"),
    "个人所得税": (0.03, "按劳务/工资所得下限 3% 起测算；实际按超额累进税率计算"),
    "印花税": (0.0003, "按购销合同 0.03% 测算；实际按对应税目税率核对"),
}


def extract_amount(text: Any) -> Optional[Dict[str, Any]]:
    """从文本里**关键词锚定**地取一个代表金额；取不到返回 None（不猜）。"""
    if not isinstance(text, str) or not text:
        return None
    best = None
    for m in _AMOUNT_PAT.finditer(text):
        raw = m.group(1)
        val, ok = to_number_checked(raw)
        if not ok or val is None or abs(val) < _MIN_AMOUNT:
            continue
        if best is None or abs(val) > abs(best["amount"]):
            best = {"amount": abs(round(float(val), 2)), "raw": raw,
                    "context": m.group(0)[:40]}
    return best


def extract_amount_from_problem(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """在一项「具体问题」的检查记录（叙述段/明细表）中锚定金额。"""
    if not isinstance(p, dict):
        return None
    chunks: List[str] = []
    for np in (p.get("narrative_paragraphs") or []):
        if not isinstance(np, dict):
            continue
        chunks.append(str(np.get("text") or ""))
        chunks.append(" ".join(str(b) for b in (np.get("bullets") or [])))
        chunks.append(str(np.get("tail") or ""))
    for row in ((p.get("detail_table") or {}).get("rows") or []):
        if isinstance(row, dict):
            chunks.append(" ".join(str(v) for v in row.values()))
    return extract_amount("\n".join(chunks))


def estimate_tax(amount: Optional[float], taxes: Optional[List[str]]) -> Dict[str, Any]:
    """按税种测算潜在税额影响。amount 为不含税涉案金额；取不到→未量化。"""
    if not amount or amount <= 0:
        return {
            "available": False, "basis": None, "items": [], "total": None,
            "note": "未量化：本项检查记录未给出可用于测算的明确金额，须补充资料后测算。",
        }
    taxes = [str(t) for t in (taxes or [])]
    items: List[Dict[str, Any]] = []
    vat_amount = 0.0
    for t in taxes:
        rate_info = _RATES.get(t)
        if not rate_info:
            continue
        rate, note = rate_info
        amt = round(amount * rate, 2)
        if t == "增值税":
            vat_amount = amt
        items.append({"tax": t, "rate": "%.4f" % rate,
                      "amount": amt, "note": note})
    # 增值税附加（随增值税附征）
    if vat_amount:
        items.append({"tax": "城建税及教育费附加", "rate": "0.12",
                      "amount": round(vat_amount * 0.12, 2),
                      "note": "按增值税额的 12%（城建 7%+教育 3%+地方教育 2%）测算"})
    total = round(sum(i["amount"] for i in items), 2) if items else None
    return {
        "available": bool(items), "basis": round(float(amount), 2),
        "items": items, "total": total,
        "note": "以上为按公开税率与本期涉案金额的**粗略测算**，仅供评估影响量级；"
                "不构成核定，实际以核实后依法核定为准。",
    }


def build_tax_impact_summary(problems: List[Dict[str, Any]]) -> Dict[str, Any]:
    """汇总本轮的潜在税额敞口（分税种）+ 已量化/未量化覆盖度。"""
    by_tax: Dict[str, float] = {}
    quantified = 0
    for p in (problems or []):
        ti = (p or {}).get("tax_impact") or {}
        if not ti.get("available"):
            continue
        quantified += 1
        for it in ti.get("items") or []:
            _v = to_number_checked(it.get("amount"))[0] or 0.0
            by_tax[it["tax"]] = round(by_tax.get(it["tax"], 0.0) + float(_v), 2)
    total = round(sum(by_tax.values()), 2) if by_tax else None
    return {
        "quantified": quantified,
        "total_items": len(problems or []),
        "by_tax": [{"tax": k, "amount": v}
                   for k, v in sorted(by_tax.items(), key=lambda kv: -kv[1])],
        "total": total,
        "note": ("潜在税额敞口为按公开税率的粗略测算，仅供评估量级，不构成核定；"
                 "未量化的项表示检查记录中尚无明确金额，须补资料后测算。"),
    }

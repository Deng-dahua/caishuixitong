# -*- coding: utf-8 -*-
"""银行流水「收款性质」唯一权威（2026-10-03）

═══════════════════════════════════════════════════════════════════════════════
为什么必须建立这一层（根因）
═══════════════════════════════════════════════════════════════════════════════
**银行流水的"贷方发生额"不等于"收入"。** 同一笔贷方可能是：

  · 经营性收款：客户付来的货款/服务款（可能已开票，也可能尚未开票）；
  · 非经营性收款：股东注资、关联方往来、银行借款、押金保证金、税费返还、
    银行结息、政府补助、保险赔付、资产处置款……

把**全部贷方**当作"收入"去和销项开票额比对，差额会被读成「隐匿未开票收入」——
差额越大越像，方向恰好相反。实测（公司1 真账套）：

    全部贷方                8,371,659.92 元
    销项开票                7,035,008.58 元  →  照旧口径"差额 1,336,651.34 元"
    剔除非经营性后
      经营性收款 ≈ 6,815,365.39 元
                          →  开票比经营收款**还多 219,643.19 元**（结论完全反转）

其中被当成"收入"的 1,289,200.00 元是**关联方资金往来**、65,000.00 元是**押金/保证金**、
27.04 元是**银行结息**。报告据此写出的"存在未确认收入的资金入账 / 涉嫌隐匿未开票收入"
是**假线索**；而对"每一笔收款是什么性质都还没定"的流水直接下结论，是同样的病。

═══════════════════════════════════════════════════════════════════════════════
设计原则
═══════════════════════════════════════════════════════════════════════════════
B1 **单一数据源**：分类规则＝`static/industry_data.json → 收款分类规则`，逐条带 `nature`
   字段（经营性／非经营性／待判定）。**判定代码里不出现任何类目名**，新增类目只改数据表。
B2 **判不出必须"待判定"**：不匹配任何规则的收款归入默认类目，其 nature 一律
   **待判定**——不得为了凑出收入口径而默认算作经营性（那等于替企业认下收入）。
B3 **不可用要能自证**：规则表缺失/未标 nature 时 `available=False`，调用方**回退旧口径
   并在报告中说明**（宁可说"性质分类不可用"，不可静默按经营性算）。
B4 **留痕**：自我纠错（极小金额有零有整的收款实为银行结息）逐笔留痕，供报告说明。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from engine.numparse import to_number

# 三种性质（判定语义，不是类目名）
OPERATING = "经营性"
NON_OPERATING = "非经营性"
UNDETERMINED = "待判定"

#: 默认类目（无规则命中时）——nature 由数据表给出，此处只做兜底标签
_FALLBACK_RULES: Tuple[Dict[str, Any], ...] = (
    {"label": "税费社保退款", "keywords": ["社保", "医保", "税", "国库", "ETS", "电子税务局"]},
    {"label": "银行内部款项", "keywords": ["结息", "利息", "银行", "农行"], "is_bank_internal": True},
    {"label": "企业客户款", "keywords": ["有限公司", "公司", "企业", "厂", "店", "集团"]},
    {"label": "个人待分析", "is_default": True},
)

_ETS_RE = re.compile(r"(?<![A-Za-z])ETS(?![A-Za-z])")


def _receipt_cfg() -> Dict[str, Any]:
    """读取收款分类配置（唯一来源：industry_data.json）。"""
    try:
        from engine.industry_resolver import load_industry_data as _ld

        data = _ld() or {}
        cfg = data.get("收款分类规则") or {}
        if isinstance(cfg, dict):
            return cfg
    except Exception:
        pass
    return {}


def receipt_rules() -> List[Dict[str, Any]]:
    """收款分类规则表（配置驱动；配置缺失时用内置兜底表）。"""
    rules = list((_receipt_cfg().get("rules") or []))
    if not rules:
        rules = [dict(r) for r in _FALLBACK_RULES]
    return rules


def rules_available() -> bool:
    """分类规则是否**带性质标注**可用。

    判据：存在至少一条规则带 `nature` 字段。只有类目、没有性质标注 ⇒ 不可用
    （此时按经营性算收入＝凭空替企业认收入，故一律回退旧口径并由调用方说明）。
    """
    return any(str(r.get("nature") or "").strip() for r in receipt_rules())


def rule_nature(rule: Dict[str, Any]) -> str:
    """规则的性质；缺失 ⇒ 待判定（B2 不臆测）。"""
    n = str((rule or {}).get("nature") or "").strip()
    return n if n in (OPERATING, NON_OPERATING, UNDETERMINED) else UNDETERMINED


def default_rule(rules: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for r in rules:
        if r.get("is_default"):
            return r
    return None


def bank_internal_label(rules: Sequence[Dict[str, Any]]) -> str:
    """「银行内部款项」类目名（由数据表 `is_bank_internal` 标记指定，代码不含该字面量）。"""
    for r in rules:
        if r.get("is_bank_internal"):
            return str(r.get("label") or "")
    return ""


def _tx_text(tx: Any) -> str:
    """一条流水的全部可用文本（对手方 + 摘要 + 附言/备注 + 用途）联合。

    ★ 2026-10-03：字段清单与拼接口径已收敛到 `engine.fieldkit.bank_tx_text`
    （此前本模块与 payment_channel 各写一份、字段还不一样），此处只做薄转发。
    """
    from engine.fieldkit import bank_tx_text
    return bank_tx_text(tx)


def counterparty_of(tx: Any) -> str:
    """对手方（做完 ETS→电子税务局 的源端中文化，唯一实现）。"""
    cp = str(tx.get("counterparty") or tx.get("counterparty_name") or "").strip()
    if not cp:
        return ""
    return _ETS_RE.sub("电子税务局", cp)


def classify_credit(tx: Any, rules: Optional[Sequence[Dict[str, Any]]] = None) -> Tuple[str, str]:
    """单笔收款 → (类目 label, 性质 nature)。规则表按顺序匹配，**第一匹配生效**。"""
    rules = list(rules) if rules is not None else receipt_rules()
    text = _tx_text(tx)
    for rule in rules:
        if rule.get("is_default"):
            continue
        kws = rule.get("keywords") or []
        sums = rule.get("summaries") or []
        if (kws and any(k in text for k in kws)) or (sums and any(s in text for s in sums)):
            return str(rule.get("label") or ""), rule_nature(rule)
    dft = default_rule(rules)
    if dft is not None:
        return str(dft.get("label") or ""), rule_nature(dft)
    return "", UNDETERMINED


def _is_bank_like_text(text: str) -> bool:
    """是否带银行侧特征词（纠错用；词表由数据表 `correction.bank_keywords` 提供）。"""
    kws = (_receipt_cfg().get("correction") or {}).get("bank_keywords") or []
    return bool(kws) and any(k in text for k in kws)


def classify_receipts(bank_txs: Sequence[Any]) -> Dict[str, Any]:
    """把一批银行流水的**贷方**按收款性质分类汇总（唯一实现）。

    返回：
      rows/total/operating/non_operating/undetermined —— 金额与笔数
      by_label / by_nature                            —— 分组汇总
      *_rows                                          —— 逐笔明细（报告证据行可直接用）
      corrections                                     —— 自我纠错留痕
      available                                       —— 性质分类是否可用（B3）
    """
    rules = receipt_rules()
    available = rules_available()
    cfg_corr = (_receipt_cfg().get("correction") or {})
    max_amount = to_number(cfg_corr.get("max_amount", 100)) or 100.0
    micro_amount = to_number(cfg_corr.get("micro_amount", 20)) or 20.0
    internal_label = bank_internal_label(rules)

    by_label: Dict[str, Dict[str, Any]] = {}
    by_nature: Dict[str, Dict[str, Any]] = {}
    rows_by_nature: Dict[str, List[Dict[str, Any]]] = {
        OPERATING: [], NON_OPERATING: [], UNDETERMINED: []
    }
    corrections: List[str] = []
    total = 0.0
    n_rows = 0

    for tx in list(bank_txs or []):
        credit = to_number(tx.get("credit", 0))
        if credit <= 0:
            continue
        n_rows += 1
        total += credit
        label, nature = classify_credit(tx, rules)
        text = _tx_text(tx)
        # ── B4 自我纠错：极小金额 + 有零有整 + 文本无实质内容 ⇒ 实为银行结息 ──
        if nature == UNDETERMINED and internal_label and credit < max_amount:
            _decimal = abs(credit - int(credit)) > 1e-9
            _blank = len(str(text).strip()) < 5
            if _decimal and (
                (credit < micro_amount and len(str(text).strip()) < 3)
                or _blank
                or _is_bank_like_text(text)
                or re.match(r"^\d{4,8}$", str(tx.get("summary") or "").strip()) is not None
            ):
                corrections.append(
                    "纠错：%.2f 元「%s」由%s改判为%s（金额有零有整且文本无实质内容，符合银行结息特征）"
                    % (credit, counterparty_of(tx) or "(空)", label or UNDETERMINED, internal_label)
                )
                label = internal_label
                # 纠错目标的性质在规则表里就声明着（银行结息＝非经营性）
                for r in rules:
                    if str(r.get("label") or "") == internal_label:
                        nature = rule_nature(r)
                        break

        rec = {
            "date": str(tx.get("date") or "")[:10],
            "counterparty": counterparty_of(tx),
            "amount": round(credit, 2),
            "label": label,
            "nature": nature,
        }
        rows_by_nature.setdefault(nature, []).append(rec)

        b = by_label.setdefault(label, {"amount": 0.0, "count": 0, "nature": nature})
        b["amount"] += credit
        b["count"] += 1
        n = by_nature.setdefault(nature, {"amount": 0.0, "count": 0})
        n["amount"] += credit
        n["count"] += 1

    def _amt(nature: str) -> float:
        return round(by_nature.get(nature, {}).get("amount", 0.0), 2)

    return {
        "rows": n_rows,
        "total": round(total, 2),
        "operating": _amt(OPERATING),
        "non_operating": _amt(NON_OPERATING),
        "undetermined": _amt(UNDETERMINED),
        "by_label": by_label,
        "by_nature": by_nature,
        "operating_rows": rows_by_nature.get(OPERATING, []),
        "non_operating_rows": rows_by_nature.get(NON_OPERATING, []),
        "undetermined_rows": rows_by_nature.get(UNDETERMINED, []),
        "corrections": corrections,
        "available": available,
    }


def operating_credit_total(bank_txs: Sequence[Any]) -> float:
    """**收入口径**的经营性收款合计（凡"银行入账 vs 开票收入"比对一律用它）。

    性质分类不可用时（B3）返回全部贷方合计——调用方**必须**用
    `income_scope_note()` 把这一事实写进报告，不许静默。
    """
    res = classify_receipts(bank_txs)
    if not res["available"]:
        return res["total"]
    return res["operating"]


def income_scope_note(res: Dict[str, Any]) -> str:
    """报告用「收入口径说明」——把"剔除了什么、还有什么没定性"如实写出来。"""
    if not res or not res.get("rows"):
        return ""
    if not res.get("available"):
        return (
            "本项银行侧口径为全部流水贷方发生额%s元：收款性质分类规则本轮不可用，"
            "系统未对「哪些贷方属于经营收款」作出判断，该口径可能包含借款、往来款、"
            "保证金等非经营款项，仅作规模参考。" % format(res.get("total", 0), ",.2f")
        ).replace("**", "")
    parts = [
        "银行侧按**收款性质**取值：经营性收款 %s 元（%d 笔），"
        "已剔除非经营性收款 %s 元（%d 笔）"
        % (
            format(res.get("operating", 0), ",.2f"),
            int((res.get("by_nature", {}).get(OPERATING) or {}).get("count", 0)),
            format(res.get("non_operating", 0), ",.2f"),
            int((res.get("by_nature", {}).get(NON_OPERATING) or {}).get("count", 0)),
        )
    ]
    detail = []
    for label, v in sorted(
        (res.get("by_label") or {}).items(), key=lambda kv: -kv[1].get("amount", 0)
    ):
        if v.get("nature") == NON_OPERATING:
            detail.append("%s%s元" % (label, format(v.get("amount", 0), ",.2f")))
    if detail:
        parts.append("（已剔除的构成：" + "、".join(detail[:6]) + "）")
    if res.get("undetermined", 0) > 0:
        parts.append(
            "另有 %s 元（%d 笔）**收款性质待判定**，未计入经营性收款，"
            "须企业逐笔说明款项性质"
            % (
                format(res.get("undetermined", 0), ",.2f"),
                int((res.get("by_nature", {}).get(UNDETERMINED) or {}).get("count", 0)),
            )
        )
    return "".join(parts).replace("**", "")


def income_scope_note_with_undetermined_rows(res, limit: int = 5) -> str:
    """在口径说明后附「待判定收款」逐笔点名（便于企业据此举证）。"""
    note = income_scope_note(res)
    rows = (res or {}).get("undetermined_rows") or []
    if not rows:
        return note
    rows = sorted(rows, key=lambda r: -r.get("amount", 0))[:limit]
    lines = [
        "%s %s %s元" % (r.get("date") or "—", r.get("counterparty") or "(未记录名称)",
                        format(r.get("amount", 0), ",.2f"))
        for r in rows
    ]
    return note + "；待判定收款金额较大的有：" + "；".join(lines)


def income_scope_brief(res: Dict[str, Any]) -> str:
    """口径说明的**简短版**（用于会直接进报告的 `detail` 字段，避免过长被截断）。

    为什么单列一版：报告正文的事实句取自发现的 `detail`，而 `description` 并不呈现给读者
    —— 口径只说在 description 里等于**读者看不到**（实测："非经营性/待判定"在报告里 0 次）。
    """
    if not res or not res.get("rows"):
        return ""
    if not res.get("available"):
        return "银行侧为全部贷方发生额（收款性质分类不可用，含借款/往来等非经营款项）"
    parts = ["银行侧按收款性质取值：经营性收款 %s 元" % format(res.get("operating", 0), ",.2f")]
    if res.get("non_operating", 0) > 0:
        labels = [
            "%s%s元" % (lab, format(v.get("amount", 0), ",.2f"))
            for lab, v in sorted((res.get("by_label") or {}).items(), key=lambda kv: -kv[1].get("amount", 0))
            if v.get("nature") == NON_OPERATING
        ]
        parts.append(
            "；已剔除非经营性收款 %s 元（%s）"
            % (format(res.get("non_operating", 0), ",.2f"), "、".join(labels[:4]) if labels else "借款/往来/保证金等")
        )
    if res.get("undetermined", 0) > 0:
        parts.append(
            "；另有 %s 元收款性质待判定，未计入收入口径，须企业逐笔说明"
            % format(res.get("undetermined", 0), ",.2f")
        )
    return "".join(parts).replace("**", "")


__all__ = [
    "OPERATING",
    "NON_OPERATING",
    "UNDETERMINED",
    "receipt_rules",
    "rules_available",
    "rule_nature",
    "bank_internal_label",
    "counterparty_of",
    "classify_credit",
    "classify_receipts",
    "operating_credit_total",
    "income_scope_note",
    "income_scope_brief",
    "income_scope_note_with_undetermined_rows",
]

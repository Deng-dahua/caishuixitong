# -*- coding: utf-8 -*-
"""域间联动 —— **把互相印证的发现连起来**（外部点评 P1-13）。

## 问题

各业务域各算各的，报告把结论平铺成 N 条互不引用的清单。外部点评举证两例：

1. 「企业所得税贡献率 0.01%（账面费用约 664 元 vs 小微应提约 2 万）」与
   「小微优惠（应享）」**互不引用** —— 前者说税负偏低、后者说该享受优惠，
   读者看到两条对立结论却不知它们其实是同一件事的两面；
2. 「私户收款」与「公户超额代发 81.5 万」**未做时序/主体配对** ——
   两条线索合起来才能判断"是不是同一笔钱走两次"。

## 做法（通用规则，与行业无关）

给每条发现找**联动对象**并标注关系类型，报告据此提示"须合并/配对核实"。
判据全部是**结构化的两两关系**（不猜、不做业务定性）：

| 关系 | 触发条件 | 提示 |
|---|---|---|
| `opposite_flow` | 同一对手方，一收一付（分属两条发现） | 同主体反向资金，须配对核实是否代收代付/资金回流 |
| `same_tax_opposed` | 同一税种，两条发现的结论方向相反（含"优惠/减免"与"偏低/不足"） | 同一税种两项须合并判断，避免互相矛盾 |
| `same_metric_diff_source` | 同一指标名出现在不同资料口径的发现里 | 同一指标不同口径，须对照核实 |

只在**同类主体/同类指标**上连线；连不上就不连（宁缺勿滥）。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# 方向词（唯一权威；新增同类词只加一行）
_IN_WORDS = ("收款", "收入", "收到", "流入", "销项", "回款", "进账")
_OUT_WORDS = ("付款", "支出", "付出", "流出", "进项", "支付", "转账", "代发")
_BENEFIT_WORDS = ("优惠", "减免", "应享", "小微", "抵扣", "加计")
_LOW_WORDS = ("偏低", "不足", "异常低", "低于", "未足额", "贡献率低")

# 指标名候选（用于 same_metric_diff_source）
_METRIC_HINTS = ("毛利率", "税负率", "贡献率", "未付款占比", "红冲占比", "费用率",
                 "存货周转", "人均", "社保人数", "工资人数")

_MAX_LINKS = 6


def _norm_money(v: Any) -> Optional[float]:
    from engine.numparse import to_number_checked
    val, ok = to_number_checked(v)
    return float(val) if ok else None


def _text_of(f: Dict[str, Any]) -> str:
    parts = []
    for k in ("type", "detail", "description", "how_found"):
        parts.append(str(f.get(k) or ""))
    for h in (f.get("constituent_hits") or []):
        if isinstance(h, dict):
            parts.append(str(h.get("evidence") or ""))
    return " ".join(parts)


def _counterparties(f: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set()
    for r in (f.get("evidence_rows") or []):
        if isinstance(r, dict):
            cp = str(r.get("counterparty") or "").strip()
            if len(cp) >= 2:
                out.add(cp)
    m = (f.get("observed_metrics") or {})
    for k in ("counterparty", "对手方", "对方单位"):
        v = m.get(k) if isinstance(m, dict) else None
        if isinstance(v, str) and v.strip():
            out.add(v.strip())
    return out


def _flow_dir(text: str) -> int:
    """+1 偏收、-1 偏付、0 不可判。"""
    ins = sum(1 for w in _IN_WORDS if w in text)
    outs = sum(1 for w in _OUT_WORDS if w in text)
    if ins and not outs:
        return 1
    if outs and not ins:
        return -1
    return 0


def _metrics_in(text: str) -> Set[str]:
    return {m for m in _METRIC_HINTS if m in text}


def link_findings(findings: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, str]]]:
    """给每条发现找联动对象。返回 `{发现下标: [{id, type, relation, hint}]}`。

    ★ 2026-09-29：**只在"企业风险事项"之间连线** —— 复用台账准入判据
      （`ledger_governance.is_enterprise_risk_item`）把"综合定性结论""交叉验证-冲突消解"
      这类方法论/汇总条目排除在联动对象之外。实测：不过滤时 29/90 行有联动，其中
      大量是"与综合定性结论同指标不同口径"这种噪声，反而掩盖真正的域间联动。
    """
    fs = [f for f in (findings or []) if isinstance(f, dict)]
    n = len(fs)
    if n < 2:
        return {}
    try:
        from engine.ledger_governance import is_enterprise_risk_item as _admissible
    except Exception:
        def _admissible(_f):
            return True, ""
    _ok = [_admissible(f)[0] for f in fs]
    texts = [_text_of(f) for f in fs]
    dirs = [_flow_dir(t) for t in texts]
    cps = [_counterparties(f) for f in fs]
    metrics = [_metrics_in(t) for t in texts]
    taxes = [set(str(t) for t in (f.get("taxes") or []) if t) for f in fs]
    # 税种也可能只写在类型名里
    for i, f in enumerate(fs):
        t = str(f.get("type") or "")
        for w in ("增值税", "企业所得税", "个人所得税", "印花税", "城建税", "社保"):
            if w in t:
                taxes[i].add(w)

    links: Dict[int, List[Dict[str, str]]] = {}
    for i in range(n):
        got: List[Dict[str, str]] = []
        seen_rel: Set[Tuple[str, int]] = set()
        for j in range(n):
            if i == j or not _ok[j]:
                continue
            rel = ""
            hint = ""
            # ① 同一对手方、方向相反 → 同主体反向资金
            if cps[i] and cps[j]:
                shared = cps[i] & cps[j]
                if shared and dirs[i] and dirs[j] and dirs[i] != dirs[j]:
                    rel = "同主体反向资金"
                    hint = ("与「%s」涉及同一对手方（%s）且资金方向相反，"
                            "须配对核实是否代收代付、垫付或资金回流。" %
                            (str(fs[j].get("type"))[:24], "、".join(sorted(shared)[:2])))
            # ② 同一税种、结论方向相反（优惠 vs 偏低）
            if not rel and taxes[i] & taxes[j]:
                ti, tj = texts[i], texts[j]
                if ((any(w in ti for w in _BENEFIT_WORDS) and any(w in tj for w in _LOW_WORDS))
                        or (any(w in tj for w in _BENEFIT_WORDS) and any(w in ti for w in _LOW_WORDS))):
                    rel = "同税种结论相向"
                    hint = ("与「%s」同属%s，一项涉优惠享受、一项涉税负异常，"
                            "须合并判断（同一事实不应得出互斥结论）。" %
                            (str(fs[j].get("type"))[:24], "、".join(sorted(taxes[i] & taxes[j]))))
            # ③ 同一指标、不同资料口径
            if not rel and metrics[i] & metrics[j]:
                rel = "同指标不同口径"
                hint = ("与「%s」同涉指标%s，须对照两处口径（申报/开票/资金流/账面）后再下判断。" %
                        (str(fs[j].get("type"))[:24], "、".join(sorted(metrics[i] & metrics[j]))))
            if rel and (rel, j) not in seen_rel:
                seen_rel.add((rel, j))
                got.append({"index": j, "id": str(fs[j].get("finding_id") or ""),
                            "type": str(fs[j].get("type") or "")[:40],
                            "relation": rel, "hint": hint})
        if got:
            links[i] = got[:_MAX_LINKS]
    return links


def linkage_text(links: List[Dict[str, str]]) -> str:
    """把联动关系渲染为台账可读文本（简洁、去重：同类关系只写一次 + 对象清单）。"""
    if not links:
        return ""
    from collections import OrderedDict
    by_rel: "OrderedDict[str, List[str]]" = OrderedDict()
    hint_by_rel: Dict[str, str] = {}
    for l in links:
        rel = str(l.get("relation") or "")
        by_rel.setdefault(rel, [])
        t = str(l.get("type") or "")[:26]
        if t and t not in by_rel[rel]:
            by_rel[rel].append(t)
        hint_by_rel.setdefault(rel, str(l.get("hint") or ""))
    parts = []
    for rel, types in by_rel.items():
        parts.append("%s（%s）" % (rel, "、".join(types[:3]) + ("等" if len(types) > 3 else "")))
    return "；".join(parts)

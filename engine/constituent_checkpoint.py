# -*- coding: utf-8 -*-
"""构成要件级**独立核对**（per-constituent checkpoint）—— 要件是否"单独核对过"的唯一判据。

## 为什么要有（外部点评 P0-5 深层）

点评验收标准原文：

> 每要件独立 checkpoint（独立数据源 + 独立结论）；无独立证据显示"未单独核对"
> 且不计入"涉及第X条要件"。

此前只做到"机制收敛"：兜底命中只落首个序号 + 头句声明"未括注=未单独核对"。
但**判据本身**仍是"发现级信号命中即算涉及"，并没有逐要件回答三个问题：

1. 这一条要件的**独立数据源**是什么？（来自红线定义，不是猜的）
2. 该数据源本轮**取得了没有**？（`evidence_chain.elements[].status`）
3. 据此，这一条**单独核对的结论**是什么？

于是出现「要件②写"未付款占比超过50%"，实际 32.5% 却标涉及」这类硬伤
（阈值校验已由 `constituent_threshold` 兜住），以及"要件列了却看不出核过没有"。

## 数据来源（**全部来自红线自身定义**，不做逐条硬编码）

| 字段 | 用途 |
|---|---|
| `suspicion["constituents"]` | 抽象要件清单（要件原文、顺序） |
| `suspicion["evidence_chain"]["elements"]` | 每条要件的**独立数据源**（`role`/`name`/`status`） |
| `suspicion["clue_chain"]["nodes"]` | 环节级数据源与是否产出数据（回退用） |
| `argumentation["constituent_hits"]` | 信号命中（含证据） |

对应关系：**按序对齐**（同一份红线定义里，第 k 条要件 ↔ 第 k 个证据元素/第 k 个环节）。
两端条数不等时，缺的一端记"未定义独立数据源"（如实说明，不臆造）。

## 结论三态（写进报告，供读者核验）

- `checked_hit`   已单独核对 → 本企业符合该要件情形，**计入「涉及」**；
- `checked_miss`  已单独核对 → 未发现符合该要件的情形（**不计入**，但证明"查过"）；
- `not_checked`   未单独核对（独立数据源本轮未取得 / 无该要件的数据产出）→ **不计入「涉及」**。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# 数据源状态 → 是否"已取得"（唯一权威；新增状态词只加一行）
_PROVIDED_STATUS = ("已有", "已提交", "已提供", "已取得")
_MISSING_STATUS = ("缺失", "未提供", "待企业提交", "待提交", "待核", "未取得")

_CONCLUSION_ZH = {
    "checked_hit": "已单独核对：符合该要件情形",
    "checked_miss": "已单独核对：未发现符合该要件的情形",
    "threshold_unmet": "已单独核对：有信号但未达该要件的数值门槛",
    "not_checked": "未单独核对（独立数据源本轮未取得）",
    # ★ 2026-10-03（用户："服务类采购本无物流"）：**本业态不适用** ——
    #   该要件的独立数据源全部属"本业态不适用"资料（如服务型企业的货物流凭证）。
    #   与"缺资料"是**两件不同的事**：不适用资料不构成缺失，也不能因为它无法核对
    #   就把企业钉在"资料不足 ⇒ 无法排除"上（尤其出罪要件，否则企业永远无法自证清白）。
    "not_applicable": "本业态不适用（该要件依赖的资料与本业态经营形态不符）",
}


def _norm(s: Any) -> str:
    return str(s or "").strip()


# ── 语义重叠（用于把「要件」与「独立数据源」对上）────────────────────────────────
# ⚠ 为什么不用**位序对齐**：实测「红字冲销」红线里 `constituents` 的第 1 条是"红冲占比"，
#   而 `evidence_chain` 的第 1 项是"退货单、折让协议、拒收证明" —— 两者是**不同轴**
#   （要件 vs 证据项），按位对齐会把数据源**错配**给要件，那本身就是新的可信度缺陷。
#   ⇒ 改为按**文字重叠**匹配；匹配不上就如实写"未定义"，绝不臆造。
_GRAM_STOP = ("下列", "情形", "属于", "不属于", "或", "和", "与", "及", "的", "了",
              "存在", "无法", "是否", "以及", "其中", "需要", "需", "等", "并")


def _grams(text: str, n: int = 2) -> set:
    s = "".join(ch for ch in str(text or "") if "\u4e00" <= ch <= "\u9fff")
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))} - set(_GRAM_STOP)


def _overlap_ratio(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / float(min(len(a), len(b)))


def _match_source(constituent: str, candidates: List[tuple]) -> tuple:
    """在候选数据源里找与该要件文字最匹配的一项。

    返回 `(名称, 状态, 匹配度)`；匹配度低于阈值 → 名称为空（视为"未定义独立数据源"）。
    `candidates` = [(名称, 状态), ...]
    """
    cg = _grams(constituent)
    if not cg:
        return "", "", 0.0
    best, best_r, best_status = "", 0.0, ""
    second_r = 0.0
    for name, status in candidates:
        r = _overlap_ratio(cg, _grams(name))
        if r > best_r:
            second_r = best_r
            best, best_r, best_status = name, r, status
        elif r > second_r:
            second_r = r
    # 要求：达到阈值 且 明显优于次优（避免"两条都沾边"时乱配）
    if best_r < _MIN_MATCH or best_r < second_r * 1.15:
        return "", "", best_r
    return best, best_status, best_r


# 匹配阈值（唯一权威；调参只改这里）
_MIN_MATCH = 0.30


def build_constituent_checkpoints(suspicion: Dict[str, Any],
                                  not_required: Any = None) -> List[Dict[str, Any]]:
    """逐要件生成独立核对记录（不依赖任何单条红线的特例代码）。"""
    s = suspicion if isinstance(suspicion, dict) else {}
    cons = [_norm(c) for c in (s.get("constituents") or []) if _norm(c)]
    if not cons:
        return []
    arg = s.get("argumentation") or {}
    hits = {}
    for h in (arg.get("constituent_hits") or []):
        if isinstance(h, dict):
            try:
                hits[int(h.get("index"))] = _norm(h.get("evidence"))
            except (TypeError, ValueError):
                continue
    # 在 `_DEFAULT_HIT_INDEX` 兜底路径下，证据是"发现级"的（一段证据填首个序号）→
    # 它**不足以**支撑"逐要件独立核对"，故只作信号、不作独立结论。
    _elements = [e for e in ((s.get("evidence_chain") or {}).get("elements") or [])
                 if isinstance(e, dict)]
    _nodes = [n for n in ((s.get("clue_chain") or {}).get("nodes") or [])
              if isinstance(n, dict)]

    out: List[Dict[str, Any]] = []
    # 候选数据源（名称, 状态）：证据链元素 + 线索链环节。**按语义匹配**，不按位序。
    _cands: List[tuple] = []
    for e in _elements:
        nm = "、".join(x for x in (_norm(e.get("name")), _norm(e.get("purpose"))) if x)
        if nm:
            _cands.append((nm, _norm(e.get("status")) or "未知"))
    for n in _nodes:
        nm = "、".join(x for x in (_norm(n.get("source")), _norm(n.get("output"))) if x)
        if nm:
            _cands.append((nm, "已有" if n.get("has_data") else "未取得"))

    # ★ 2026-09-29（#448）：优先采用**红线显式声明的要件数据源** `constituent_sources`
    #   （与 constituents 按序对齐）。声明了就用单一权威 `evidence_chain._match_material`
    #   判定该材料本轮是否已取得；未声明才退回文字模糊匹配（原行为，兼容存量）。
    #   目的：把"未定义独立数据源"(占 not_checked 七成) 逐要件补成可自证的独立数据源。
    _avail: List[str] = []
    _ec = s.get("evidence_chain") or {}
    if isinstance(_ec, dict):
        _avail = [str(a) for a in (_ec.get("available_materials") or []) if a]
    _declared = s.get("constituent_sources") or []
    try:
        from engine.evidence_chain import _match_material as _material_match  # 单一权威
    except Exception:  # pragma: no cover
        _material_match = None

    for i, c in enumerate(cons, 1):
        _decl = ""
        if i - 1 < len(_declared):
            _e = _declared[i - 1]
            _decl = _norm(_e if isinstance(_e, str) else (_e.get("name") if isinstance(_e, dict) else ""))
        # ★ 2026-10-03：**先按业态剔除"不适用资料"**
        #   服务型企业的"物流单据/入库验收单"等货物流资料不适用（且业务上也不存在），
        #   不能因为"没提供"就判该要件"独立数据源未取得" —— 那会让要件（尤其出罪要件）
        #   永远无法核对，企业永远无法自证清白。
        _na_set = {str(x) for x in (not_required or ())}
        _decl_parts = [p.strip() for p in re.split(r"[、，,；;/／\s]+", _decl) if p.strip()] if _decl else []
        _decl_na = [p for p in _decl_parts if any(p == x or p in x or x in p for x in _na_set)]
        _decl_eff = "、".join(p for p in _decl_parts if p not in _decl_na)
        if _decl_parts and not _decl_eff:
            # 声明的数据源**全部**不适用 ⇒ 本要件对本业态不适用（不是"缺资料"）
            out.append({
                "index": i,
                "要件": c,
                "独立数据源": _decl,
                "数据源状态": "本业态不适用",
                "核对结论": _CONCLUSION_ZH["not_applicable"],
                "_conclusion": "not_applicable",
                "参与认定": False,
                "依据": ("本要件的独立数据源（%s）均为本业态不适用资料 —— "
                         "本企业业态天然无该形态资料，故不构成资料缺失，"
                         "本要件也不计入「未单独核对」。" % "、".join(_decl_na)),
                "证据": "",
            })
            continue
        if _decl_eff and _material_match is not None:
            # ① 明文声明的独立数据源（已剔除不适用项）：判定该材料是否已取得
            src_name = _decl_eff
            try:
                _m = _material_match(_decl_eff, "", _avail) or {}
                src_status = _norm(_m.get("status")) or "未知"
            except Exception:
                src_status = "未知"
            if _decl_na:
                src_name = _decl_eff
        elif _decl and _material_match is not None:
            # 声明项被全部剔除的情形已在上面 return；此处保留原分支（无剔除时走原逻辑）
            src_name = _decl
            try:
                _m = _material_match(_decl, "", _avail) or {}
                src_status = _norm(_m.get("status")) or "未知"
            except Exception:
                src_status = "未知"
        else:
            # ① 回退：与要件文字最匹配的那一项（匹配不上 → 未定义，如实说明）
            src_name, src_status, _r = _match_source(c, _cands)
            if not src_name:
                src_name, src_status = "（红线定义未标注该要件的独立数据源）", "未定义"

        _provided = any(w in src_status for w in _PROVIDED_STATUS)
        _hit_ev = hits.get(i, "")

        if not _provided:
            conclusion = "not_checked"
            basis = ("独立数据源「%s」本轮为「%s」，该要件未单独核对，"
                     "不计入「涉及第%d条要件」。" % (src_name, src_status or "未知", i))
            if _hit_ev:
                basis += "（其余环节有信号，但不足以支撑本要件的独立结论。）"
        elif _hit_ev:
            # ★ 2026-09-29（P1-5 并入）：有信号也要过**数值门槛**校验，
            #   未达门槛不得计入「涉及」（点评原例：要件写"超过50%"、实际 32.5%）。
            _verdict, _note = "unknown", ""
            try:
                from engine.constituent_threshold import check_constituent_hit as _cth
                _verdict, _note = _cth(c, _hit_ev)
            except Exception:
                pass
            if _verdict == "unmet":
                conclusion = "threshold_unmet"
                basis = ("独立数据源「%s」已取得；%s，故不计入「涉及第%d条要件」。"
                         % (src_name, _note, i))
            else:
                conclusion = "checked_hit"
                basis = "独立数据源「%s」已取得，且该要件有对应核对证据。" % src_name
        else:
            conclusion = "checked_miss"
            basis = ("独立数据源「%s」已取得，但未发现符合本要件情形。" % src_name)

        out.append({
            "index": i,
            "要件": c,
            "独立数据源": src_name,
            "数据源状态": src_status or "未知",
            "核对结论": _CONCLUSION_ZH[conclusion],
            "_conclusion": conclusion,
            "参与认定": conclusion == "checked_hit",
            "依据": basis,
            "证据": _hit_ev,
        })
    return out


def redline_verdict_rule(redline_id: Any) -> Dict[str, Any]:
    """红线的**要件组合逻辑**（可选声明；未声明返回空 dict ⇒ 保持既有行为）。

    字段（数据驱动，写在 engine/tax_redlines.py 的红线定义里）：
      indicator_constituents —— **指标类要件**：只说明"看到的现象"，单独成立**不构成违规**
                                （例：RL-VAT-006 第①条"全部收入均已开票"——全部开票本身是正当情形）；
      violation_any_of       —— **违规成立所需**的要件（任一成立即可）。

    ★ 2026-10-03（用户复核疑点11）根因：旧实现只要第①条（指标）成立就判"已触碰税务违规红线"，
      而②③④（未开票收入的**来源特征**）全部未发现 ⇒ 结论完全颠倒：
      一家客户全部要票、没有个人/现金/平台收款的企业，被指控"隐匿未开票收入"。
    """
    rid = str(redline_id or "").strip()
    if not rid:
        return {}
    try:
        from engine.tax_redlines import REDLINES
    except Exception:
        return {}
    for rl in REDLINES:
        if str(rl.get("id") or "") == rid:
            if rl.get("violation_any_of"):
                # ★ 不得返回 set —— 序列化后会以 `set()` repr 形式混进报告（闸门 check_no_set_in_report 实测抓出）。
                return {
                    "indicator": sorted(int(x) for x in (rl.get("indicator_constituents") or [])),
                    "any_of": sorted(int(x) for x in (rl.get("violation_any_of") or [])),
                }
            return {}
    return {}


def participating_indices(checkpoints: List[Dict[str, Any]],
                          redline_id: Any = None) -> List[int]:
    """可计入「涉及第X条要件」的序号（只有 `checked_hit`，且须通过**要件组合逻辑**）。

    给了 `redline_id` 且该红线声明了 `violation_any_of` 时：
      · 命中集合与 `any_of` 有交集 → 照旧（构成违规，全部命中要件计入）；
      · 只有 `indicator_constituents`（指标现象）成立 → **返回空集**
        （报告随之写"未认定到构成要件"，不再出现"仅指标现象就判触红"的颠倒结论）。
    """
    hits = sorted(int(cp["index"]) for cp in (checkpoints or []) if cp.get("参与认定"))
    rule = redline_verdict_rule(redline_id)
    if not rule or not hits:
        return hits
    if set(hits) & set(rule["any_of"]):
        return hits
    return []


def checkpoint_table(checkpoints: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """把核对记录转成报告可渲染的明细表（要件 / 独立数据源 / 数据源状态 / 核对结论）。"""
    rows = []
    for cp in (checkpoints or []):
        rows.append({
            "要件序号": "第%d条" % int(cp["index"]),
            "构成要件": str(cp.get("要件") or ""),
            "独立数据源": str(cp.get("独立数据源") or ""),
            "数据源状态": str(cp.get("数据源状态") or ""),
            "核对结论": str(cp.get("核对结论") or ""),
        })
    if not rows:
        return None
    return {"title": "构成要件独立核对表（每要件独立数据源与独立结论）",
            "columns": ["要件序号", "构成要件", "独立数据源", "数据源状态", "核对结论"],
            "rows": rows}


def summarize(checkpoints: List[Dict[str, Any]]) -> str:
    """一句话汇总：几条已单独核对（命中/未发现/未达门槛）、几条未单独核对。"""
    cps = checkpoints or []
    if not cps:
        return ""
    hit = sum(1 for c in cps if c.get("_conclusion") == "checked_hit")
    miss = sum(1 for c in cps if c.get("_conclusion") == "checked_miss")
    unmet = sum(1 for c in cps if c.get("_conclusion") == "threshold_unmet")
    nc = sum(1 for c in cps if c.get("_conclusion") == "not_checked")
    na = sum(1 for c in cps if c.get("_conclusion") == "not_applicable")
    _base = ("本项共 %d 条构成要件：已单独核对 %d 条（符合情形 %d 条、未发现符合 %d 条、"
             "有信号但未达数值门槛 %d 条）；未单独核对 %d 条（独立数据源本轮未取得，"
             "均不计入「涉及」）。" % (len(cps), hit + miss + unmet, hit, miss, unmet, nc))
    if na:
        _base += ("其中 %d 条**本业态不适用**（其独立数据源与本业态经营形态不符，"
                  "不构成资料缺失、不计入「涉及」）。" % na).replace("**", "")
    return _base

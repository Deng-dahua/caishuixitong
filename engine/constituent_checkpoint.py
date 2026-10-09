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
from typing import Any, Dict, List, Optional, Tuple

# 数据源状态 → 是否"已取得"（唯一权威；新增状态词只加一行）
_PROVIDED_STATUS = ("已有", "已提交", "已提供", "已取得")

#: 前提条（现象/存在性要件）判定 —— 唯一权威 `engine.trigger_conditions`（词表驱动）
from engine.trigger_conditions import is_premise_constituent as _is_premise  # noqa: E402
from engine.trigger_conditions import is_precondition as _is_precondition  # noqa: E402
_MISSING_STATUS = ("缺失", "未提供", "待企业提交", "待提交", "待核", "未取得")

_CONCLUSION_ZH = {
    "checked_hit": "已单独核对：符合该要件情形",
    "checked_miss": "已单独核对：未发现符合该要件的情形",
    "threshold_unmet": "已单独核对：有信号但未达该要件的数值门槛",
    "not_checked": "未单独核对（独立数据源本轮未取得）",
    # ★★ 2026-10-04（疑点10-21 合并批次 ⑲）：**禁止虚假排除**——
    #   「资料已取得」≠「核过且未发现符合」。旧实现只要独立数据源状态为"已取得"、
    #   而该要件又拿不到对应的核对证据，就直接写「未发现符合本要件情形」，
    #   那是一句**没有任何核对动作支撑**的结论（虚假排除），读者会误以为系统查过了。
    #   同理，`check_constituent_hit` 返回 `unknown`（要件无阈值 / 证据取不到同量纲值）
    #   时也不得判"符合"，否则等于用默认值替企业认了一条要件。
    #   两者统一落入 `not_concluded`：如实说明"资料已取得但未形成核对结论"，不计入「涉及」。
    "not_concluded": "未形成核对结论（资料已取得但缺本要件的对应核对证据，不作『未发现符合』认定）",
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


def _available_of(s: Dict[str, Any]) -> List[str]:
    # 2026-10-04（合并批次第三行）：本轮已提供资料清单的**唯一取法**。
    #   此前优先路径与回退路径各写一遍取法，改一处漏一处；抽成本函数后单一权威。
    _ec = s.get("evidence_chain") or {}
    if not isinstance(_ec, dict):
        return []
    return [str(a) for a in (_ec.get("available_materials") or []) if a]


def build_constituent_checkpoints(suspicion: Dict[str, Any],
                                  not_required: Any = None,
                                  detail_text: Any = None) -> List[Dict[str, Any]]:
    """逐要件生成独立核对记录（不依赖任何单条红线的特例代码）。

    `detail_text`：**本项明细表证据文本**（运行期由调用方传入，或由
    `data_source_status.detail_text_from_suspicion(s)` 与明细表**同源**取到）——
    用于"明细表里出现的数据源不得判未取得"这条硬规则（Skill 7 职责 3）。
    """
    # 数据源状态唯一权威（Skill 7）
    #   ⚠ 常量与 `_grp_reason` **必须在分支之前就位**：本项目"变量只在分支内赋值"
    #     已造成多次 `UnboundLocalError`/静默回归；下面的分支链并非必然走到导入那一支。
    from engine import data_source_status as _ds
    _DS_HAVE, _DS_MISSING, _DS_NA = _ds.STATUS_HAVE, _ds.STATUS_MISSING, _ds.STATUS_NA
    _grp_reason = ""
    s = suspicion if isinstance(suspicion, dict) else {}
    cons = [_norm(c) for c in (s.get("constituents") or []) if _norm(c)]
    if not cons:
        return []
    arg = s.get("argumentation") or {}
    # ★ 2026-10-07（触发条件与认定要件分离）：前提条按**结构化字段** `is_precondition` 判定
    #   （config/risk_conditions.json，唯一权威）；文本词表仅作配置缺失时的兜底。
    #   实测：疑点3/4/12 的第1条要件文本里没有"现象/前提条"字样，仅靠词表会漏判。
    _risk_code = str(s.get("redline_id") or s.get("risk_code") or "")
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
    # 2026-10-04（合并批次第三行 / 疑点2 D13）：**回退路径不得用环节 has_data 当资料有无**。
    #   has_data 的语义是「本环节有没有对题读数」，不是「这份资料有没有提供」。
    #   混用 ⇒ 资料已提供却判未取得 ⇒ 要件未单独核对＝有数据却放弃核对；
    #   且对题读数越严、误判越多。有清单 ⇒ 走资料齐备性唯一权威；无清单 ⇒ 保留原口径。
    for n in _nodes:
        nm = "、".join(x for x in (_norm(n.get("source")), _norm(n.get("output"))) if x)
        if not nm:
            continue
        _st_node = ""
        _avail_node = _available_of(s)
        if _avail_node:
            try:
                from engine.clue_chain import materials_available as _ma_node
                _ok_node, _miss_node = _ma_node(_norm(n.get("source")), _avail_node)
                if _ok_node:
                    _st_node = "已有"
                elif _miss_node:
                    _st_node = "未取得"
            except Exception:  # noqa: BLE001
                _st_node = ""
        _cands.append((nm, _st_node or ("已有" if n.get("has_data") else "未取得")))

    # ★ 2026-09-29（#448）：优先采用**红线显式声明的要件数据源** `constituent_sources`
    #   （与 constituents 按序对齐）。声明了就用单一权威 `evidence_chain._match_material`
    #   判定该材料本轮是否已取得；未声明才退回文字模糊匹配（原行为，兼容存量）。
    #   目的：把"未定义独立数据源"(占 not_checked 七成) 逐要件补成可自证的独立数据源。
    _avail: List[str] = _available_of(s)
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
        # ★★ 2026-10-06：**改薄转发到唯一权威** `industry_resolver.classify_not_required_segments`。
        #   旧实现有三处偏差（同一概念的第 3 份实现，判法与前两份都不同）：
        #     ① 切段表 **不含「与/及/和」** ⇒ "采购合同与入库验收单" 切不开，是**一整段**；
        #     ② 判定用**双向包含**（`x in p`）⇒ 整段命中"入库验收单" ⇒ `_decl_eff` 为空
        #        ⇒ **整条要件被误判「本业态不适用」**（而这要件里"采购合同"明明适用）；
        #     ③ 与 `evidence_chain` / `enterprise_report` 各一套，同份要件三种判法。
        #   现统一：段级 + **单向**包含（段包含不适用名才剔），与前两处**同一实现**。
        _decl_na: List[str] = []
        _decl_eff = ""
        if _decl:
            try:
                from engine.industry_resolver import (
                    classify_not_required_segments as _cls_na)
                _keep_segs, _decl_na, _had = _cls_na(_decl, not_required)
                _decl_eff = "、".join(_keep_segs)
            except Exception:  # noqa: BLE001
                # 取不到权威 ⇒ 如实按"未剔除"处理（宁可多列，不得无据少列）
                _decl_eff, _decl_na = _decl, []
        if _decl and not _decl_eff:
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
            # ★★ 2026-10-07（Skill 7「数据源状态一致性」）—— **根因修复，改薄转发到唯一权威**。
            #   旧实现把整串「独立数据源」当成**一份材料**去匹配（`_material_match(整串)`）⇒
            #   只要有一个源不在"已提供类别"里，整组就落「未取得」，**已取得的源被一起否定**；
            #   报告于是出现"正文正在用销项发票金额 / 明细表逐笔列着确认单编号，
            #   核对表却说独立数据源本轮未取得"的同页矛盾（实测 65 条要件行中 26 条命中）。
            #   现改为 `data_source_status.resolve_group()`：**逐源判定 + 合成 + 逐源点名说明**，
            #   并叠加两条硬证据规则（明细表里出现 / 由已取得资料提供 ⇒ 已有）。
            from engine.data_source_status import resolve_group as _rg
            _ds_detail = detail_text if detail_text is not None \
                else _ds.detail_text_from_suspicion(s)
            _grp = _rg(_decl_eff, available=_avail, detail=_ds_detail, not_required=not_required)
            src_name = _grp.get("group") or _decl_eff
            src_status = _grp.get("status") or "未知"
            _provided = bool(_grp.get("provided"))
            _grp_reason = str(_grp.get("reason") or "")
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

        # ★★ 2026-10-07（Skill 1「触发条件与认定要件分离」）—— 本项为**根因修复**：
        #   前提条（现象/存在性要件，原文声明"存在即成立"）的**证据就是触发信号本身**：
        #   本疑点之所以被列示，正因为检出了该现象 ⇒ 必须判「**符合情形**」。
        #   事故：报告一边写「未涉及任何一条构成要件」，一边写「红字发票13张」，
        #   而第1条要件原文就是「存在红字发票或作废发票（红冲行为）——本项为现象/前提条，
        #   存在即成立」—— 已检出 13 张，第1条显然已满足。
        #   旧实现只找"针对该要件的核对证据"，找不到就落 `not_concluded`（未形成核对结论），
        #   把"已满足的前提条"写成了"没查"。
        #   判据（词表驱动、不针对任何一条具体红线）：`trigger_conditions.is_premise_constituent`。
        _zh_override: Optional[str] = None
        _is_pre = _is_precondition(_risk_code, i, c) if _risk_code else _is_premise(c)
        if _is_pre:
            conclusion = "checked_hit"
            # ★ 用户要求（Skill 1 验收）：触发条件已满足的**必须写「符合情形」**，
            #   不得用含糊的等价措辞。故前提条显式覆盖展示结论（枚举表不动，避免影响其它要件）。
            _zh_override = "符合情形（本项为现象/前提条，存在即成立）"
            # ★★ 2026-10-09（用户复核审计 ERROR：疑点 seq=16「已有又要补」）—— **根因修复**。
            #   旧实现（2026-10-07 Skill 7）在此处**无条件**把 `src_status` 改写成「已有」，
            #   理由是"前提条的证据就是触发信号 ⇒ 现象已检出 ⇒ 状态必为已有"。
            #   ⚠ 该推理混了两个概念：**「现象由触发信号检出」≠「本要件声明的独立数据源已取得」**。
            #   实测后果（全量产物 12 条前提条中 6 条）：
            #     ① 同一疑点的「数据源状态表」（按唯一权威 `data_source_status.resolve_group`
            #        逐源判定）写着「缺失/须核对」，核对表这一行却写「已有」⇒ **同页自相矛盾**；
            #     ② 该无据的「已有」又让审计闸门 `check_next_actions_not_ghost_requirements`
            #        把「补充提供「股权转让协议、工商股权变更登记」」误判成
            #        "该资料已判已有却又要补"（seq=16 实测）。
            #   现口径（**单一权威**）：状态列一律取 `resolve_group` 的合成结论，**不得凭空改写**。
            #   「符合情形」只描述"现象已检出"，与"声明数据源是否取得"解耦；
            #   声明源未取得时在**依据**里如实点名（不静默、不掩盖），
            #   使读者看到的是"现象已检出 + 该要件声明资料待补"两件**各自为真**的事。
            if src_status not in (_DS_HAVE, _DS_NA):
                basis = ("本项为现象/前提条（存在即成立，不设数值比例/张数门槛）：本疑点因检出"
                         "该现象而列示，故判「符合该情形」。⚠ 须同时说明：本要件**声明的独立"
                         "数据源「%s」本轮%s**——上述「符合情形」依据的是**触发信号本身**，"
                         "并不代表该数据源已取得；该数据源须补充后复核。"
                         % (src_name, _grp_reason or (src_status or "未取得")))
            else:
                basis = ("本项为现象/前提条（存在即成立，不设数值比例/张数门槛）："
                         "本疑点因检出该现象而列示，故判「符合该情形」——占比、张数等仅作证据，"
                         "不作阈值判定。数据源状态按「现象已从本轮已取得资料中检出」登记为「已有」。")
        elif not _provided:
            conclusion = "not_checked"
            # ★★ 2026-10-07（Skill 7 职责 2）：**文案必须逐源点名**。
            #   旧文案一律写「独立数据源本轮未取得」——即使组内若干源本轮已取得、
            #   甚至正被本项正文使用 ⇒ 同页自相矛盾（用户点名的那类缺陷）。
            #   现按合成状态分三种说法，只有"全无"才允许说"本轮均未取得"。
            if src_status == _DS_MISSING:
                _zh_override = "未单独核对（独立数据源本轮均未取得）"
            else:
                _zh_override = "未单独核对（%s）" % (_grp_reason or "独立数据源未全部取得")
            basis = ("独立数据源「%s」：%s，该要件未单独核对，"
                     "不计入「涉及第%d条要件」。" % (src_name, _grp_reason or (src_status or "未知"), i))
            if _hit_ev:
                basis += "（其余环节有信号，但不足以支撑本要件的独立结论。）"
        elif _hit_ev:
            # ★★ 2026-10-03（用户复核疑点3）：**先做"证据措辞体检"** ——
            #   证据自称"未定量/需评估/待核实" ⇒ 不得判"符合"（该要件要求的数值没算）；
            #   证据自称"不构成/未见/未发现" ⇒ 判"未发现符合"（方向相反）。
            #   两类都不计入「涉及」，且都**保留原证据文本**供读者复核。
            _ev_verdict, _ev_note = assess_hit_evidence(_hit_ev)
            if _ev_verdict == "miss":
                conclusion = "checked_miss"
                basis = ("独立数据源「%s」已取得；%s，故判「未发现符合该要件情形」，"
                         "不计入「涉及第%d条要件」。" % (src_name, _ev_note, i))
            elif _ev_verdict == "unmet":
                conclusion = "threshold_unmet"
                basis = ("独立数据源「%s」已取得；%s，不计入「涉及第%d条要件」。"
                         % (src_name, _ev_note, i))
            else:
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
                elif _verdict == "unknown":
                    # ★⑲：`check_constituent_hit` 判不出（要件无阈值 / 证据取不到同量纲值）
                    #   ⇒ **不判符合**，也不得反推"未发现符合"（两样都缺数据支撑）。
                    conclusion = "not_concluded"
                    basis = ("独立数据源「%s」已取得，但本要件无可比对的同量纲数值，也未形成"
                             "针对该要件的核对证据（%s），故不作「符合」也不作「未发现符合」的认定，"
                             "不计入「涉及第%d条要件」。" % (src_name, _note or "要件未声明数值门槛", i))
                else:
                    conclusion = "checked_hit"
                    basis = "独立数据源「%s」已取得，且该要件有对应核对证据。" % src_name
        else:
            # ★⑲：资料已取得 = 有得查；**没有针对该要件的核对证据 = 没查过**，
            #   不得写成"未发现符合"。如实标「未形成核对结论」。
            conclusion = "not_concluded"
            basis = ("独立数据源「%s」本轮已取得，但未形成针对本要件的核对证据（该要件"
                     "既未检出符合情形的信号、也未见其不成立的记录），故**不认定**"
                     "「未发现符合本要件情形」；须补充该要件的核对证据后重新判断。" % src_name)

        out.append({
            "index": i,
            "要件": c,
            "独立数据源": src_name,
            "数据源状态": src_status or "未知",
            "核对结论": _zh_override or _CONCLUSION_ZH[conclusion],
            "_conclusion": conclusion,
            "_premise": _is_pre,
            # ★ 2026-10-07（Skill 7 同源）：把**逐源状态**一并带出 ⇒ 报告级「数据源状态表」
            #   直接聚合这里的结果，**不再另算一遍**（两处各算一遍必然出现"核对表一种状态、
            #   状态表另一种状态"的两张皮，而两者都"看起来对"）。
            "_data_sources": _grp.get("items") if _decl_eff else [],
            "参与认定": conclusion == "checked_hit",
            "依据": basis,
            "证据": _hit_ev,
        })
    return out


# ★★ 2026-10-03（用户复核疑点3「银行收款大于申报收入」）——
#   **核对证据本身"未定量"或"自我否定"时，不得判「符合该要件情形」**。
#   事故：要件② 的核对证据原文是
#     「累计方向性差额 1,170,164.14 元（**占申报收入比例需要逐月评估**）」
#   —— 证据自己写着"需要评估"（即**该要件要求的比值没有算**），却被判
#     「已单独核对：符合该要件情形」，进而计入「涉及第②条」。
#   同一疑点的结论段还写着「以行业基准税负率区间[1.5%~5.0%]为参照……**未见偏离**」
#   —— **判据（超过上沿）与证据（未见偏离）方向相反**。
#
#   判据（数据驱动、词表统一、可扩）：
#     ① 未定量类 ⇒ 判 `threshold_unmet`（"有信号但未达数值门槛"，如实说"该比值未算"）；
#     ② 反向/否定类 ⇒ 判 `checked_miss`（"已核对：未发现符合该要件的情形"）；
#     两类**都不计入「涉及」**，且都保留原证据文本供读者复核。
#   判据（数据驱动、**正则**、可扩）：
#     ① 未定量类 ⇒ 判 `threshold_unmet`（"有信号但未达数值门槛"，如实说"该比值未算"）；
#     ② 反向/否定类 ⇒ 判 `checked_miss`（"已核对：未发现符合该要件的情形"）；
#     两类**都不计入「涉及」**，且都保留原证据文本供读者复核。
#
# ★★★ 2026-10-03 关键坑（实测抓出，务必记住）：**词表必须覆盖"引擎侧原始措辞"**。
#   第一版用逐字串（"需要逐月评估"），实测**完全不生效**——因为引擎侧原文是
#     「累计方向性差额 1,170,164.14 元（占申报收入比例**须逐月评估**）」（**"须"**），
#   而报告输出侧 `plain_language` 会把它改写成"**需要**逐月评估" ⇒
#   逐字锚点在**判定侧**失效，报告的"符合"照旧。
#   ⇒ 改为**正则**：`(需|需要|须|尚须|仍须|待|有待) [逐月|逐笔|逐项|逐条]? (评估|核实|确认|核对|测算)`
#     一次覆盖"须/需/需要/尚须/待"等所有前缀，**不再依赖输出侧改写后的写法**。
#   （同类教训：`argumentation.neutralize_assertion` 也曾因"补证→补充资料"改写而静默失效。）
_HIT_EV_UNQ_RE = re.compile(
    r"(?:需|需要|须|须要|尚须|仍须|有待|待)"
    r"(?:逐月|逐笔|逐项|逐条|人工)?"
    r"(?:评估|核实|确认|核对|测算)"
)
_HIT_EV_DENY_RE = re.compile(
    r"(?:不构成|未构成|未见|未发现|无法认定|不能认定|尚不能|不足认定|无证据支持)"
)


def assess_hit_evidence(ev: Any) -> Tuple[str, str]:
    """对"信号命中证据"做**措辞体检**：返回 (verdict, note)。

    verdict ∈ {"", "unmet", "miss"}：
      · ""      —— 证据可用（保持原行为，判 checked_hit）；
      · "unmet" —— 证据自述"未定量/需评估/尚需核实" ⇒ 该要件**要求的数值没有算出来**，
                   不得判"符合"；如实标「有信号但未达数值门槛」；
      · "miss"  —— 证据自述"不构成/未见/未发现…" ⇒ 证据方向与"符合"相反，
                   判「已核对：未发现符合该要件的情形」。

    判据用正则（`_HIT_EV_UNQ_RE` / `_HIT_EV_DENY_RE`），**同时覆盖引擎侧与输出侧写法**
    （"须评估" / "需要评估"）；新增同类只加一处。
    """
    _t = str(ev or "").strip()
    if not _t:
        return "", ""
    _m = _HIT_EV_DENY_RE.search(_t)
    if _m:
        return "miss", ("核对证据含反向措辞「%s」——证据方向与「符合该要件」相反" % _m.group(0))
    _m = _HIT_EV_UNQ_RE.search(_t)
    if _m:
        return "unmet", ("核对证据含未定量措辞「%s」——该要件要求的数值尚未算出，"
                         "不得判「符合」" % _m.group(0))
    return "", ""


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
        （报告随之写"未认定到构成要件"，不再出现"仅指标现象就判触碰红线"的颠倒结论）。
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
    # ★ 2026-10-04（⑲）：`not_concluded` 单列 —— 它既不是"查过且未发现"，也不是"没查"，
    #   而是"查不了也没法定"，如实单列，不计进"已单独核对"的分子。
    ncn = sum(1 for c in cps if c.get("_conclusion") == "not_concluded")
    _base = ("本项共 %d 条构成要件：已单独核对 %d 条（符合情形 %d 条、未发现符合 %d 条、"
             "有信号但未达数值门槛 %d 条）；未形成核对结论 %d 条（资料已取得但缺对应核对证据，"
             "不作「未发现符合」认定）；未单独核对 %d 条（独立数据源**未全部取得**，"
             "均不计入「涉及」）。" % (len(cps), hit + miss + unmet, hit, miss, unmet, ncn, nc))
    # ★ 2026-10-07（Skill 7）：口径由"独立数据源本轮未取得"改为"**未全部取得**"——
    #   逐源判定后，多数要件是"部分已取得、部分未取得"，旧措辞会把已取得的部分一并否定。
    _base = _base.replace("**", "")
    if na:
        _base += ("其中 %d 条本业态不适用（其独立数据源与本业态经营形态不符，"
                  "不构成资料缺失、不计入「涉及」）。" % na).replace("**", "")
    return _base

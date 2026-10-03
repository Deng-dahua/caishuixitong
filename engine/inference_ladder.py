# -*- coding: utf-8 -*-
"""点→面推演层（推断与联想）——一键分析**每次都跑**的"多想一层"（2026-10-03）

═══════════════════════════════════════════════════════════════════════════════
为什么要有这一层（用户原话）
═══════════════════════════════════════════════════════════════════════════════
「财税稽查系统为什么有那么多问题，就是因为它傻逼，没有深度的去思考问题，
更没有拓展性的去联想思考问题。这种对每一项问题从点到面的推断思考与分析，
是应该接入一键分析按钮，并让它每次生成报告时都要触发的功能。」

「是不是有开票未收款的应收账款，是不是有收款未开票的预收账款？而且你他妈傻逼，
如果你是老板，你会傻逼到未开票收入用公司公账来收款吗？」

两句指向同一件事：**系统只把"读数"当"结论"，从不问这个读数在真实经营里还能由
什么原因造成、以及这个载体在逻辑上能不能成立。**

本层的职责（对每个疑点、每次分析都执行）：
  ① **正常解释**：这个读数在正常经营下可能由哪些原因造成（必须能对上会计科目）；
  ② **违规手法**：违规情形具体是什么样；
  ③ **判别检验**：哪份资料能把两类解释分开，本企业是否已提供；
  ④ **渠道/载体限制**：该推断在逻辑上能否成立（如"公账收款不可能用于隐匿收入"）；
  ⑤ **未解释差额**：两类都解释不了的部分，须企业举证。

数据源：`static/inference_ladders.json`（新增场景只加一条数据，代码不含业务词表）。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

_LADDERS: Optional[Dict[str, Any]] = None


def _path() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "static", "inference_ladders.json")


def load_ladders() -> Dict[str, Any]:
    """推演库（单例缓存）。读不到时返回空库——调用方必须能容忍并**不产出**推演段。"""
    global _LADDERS
    if _LADDERS is None:
        try:
            with open(_path(), "r", encoding="utf-8") as fh:
                _LADDERS = json.load(fh)
        except Exception:
            _LADDERS = {}
    return _LADDERS


# ── 收入差集：销项开票 ↔ 公账经营性收款 ──────────────────────────────────────
def revenue_gap_reasoning(inv_excl: float, bank_operating: float,
                          ar_movement: Optional[float] = None,
                          advance_movement: Optional[float] = None,
                          private_receipts: float = 0.0,
                          tolerance: float = 1000.0) -> Dict[str, Any]:
    """把"开票 vs 公账收款"的差额翻译成**会计实质**，并给出渠道逻辑限制。

    返回 dict：
      direction     —— "开票大于收款" / "收款大于开票" / "基本吻合"
      gap           —— 差额（元，取绝对值）
      explanations  —— 正常/违规解释清单（来自推演库，逐条带科目与佐证）
      explained_by  —— 已能用账内科目解释的部分（应收/预收变动）
      unexplained   —— 未解释差额
      channel_note  —— 渠道逻辑限制（公账 ≠ 隐匿渠道）
      checks        —— 判别性检验清单
      text          —— 可直接进报告的段落
    """
    ladders = load_ladders().get("收入差集") or {}
    channel = (load_ladders().get("渠道逻辑") or {}).get("公账收款") or {}
    inv = float(inv_excl or 0.0)
    bank = float(bank_operating or 0.0)
    gap = inv - bank
    if abs(gap) <= max(tolerance, 1.0):
        return {
            "direction": "基本吻合", "gap": 0.0, "explanations": [],
            "explained_by": 0.0, "unexplained": 0.0, "channel_note": "", "checks": [],
            "text": ("销项开票（不含税）%s 元与公账经营性收款 %s 元基本吻合，"
                     "不存在需要解释的收入差集。" % (_fmt(inv), _fmt(bank))),
        }

    key = "开票大于收款" if gap > 0 else "收款大于开票"
    explanations = [dict(x) for x in (ladders.get(key) or [])]

    # 账内已有科目能解释多少：开票>收款 看应收账款净增，收款>开票 看预收账款净增
    explained = 0.0
    if key == "开票大于收款" and ar_movement:
        explained = min(abs(gap), abs(float(ar_movement)))
    elif key == "收款大于开票" and advance_movement:
        explained = min(abs(gap), abs(float(advance_movement)))
    unexplained = max(0.0, abs(gap) - explained)

    parts = [
        "销项开票（不含税口径）%s 元与公账经营性收款 %s 元相差 %s 元（%s）。"
        % (_fmt(inv), _fmt(bank), _fmt(abs(gap)), key)
    ]
    if explained > 0:
        parts.append("其中 %s 元可由账内科目变动直接解释。" % _fmt(explained))
    if unexplained > 0:
        parts.append("尚余 %s 元未解释，须企业举证。" % _fmt(unexplained))
    if channel.get("推论"):
        parts.append(channel["推论"])
    if private_receipts > 0:
        parts.append("本轮检出经营相关的个人/非公账收款 %s 元，该方向才是隐匿收入的主线索，"
                     "已单列核查。" % _fmt(private_receipts))
    return {
        "direction": key,
        "gap": round(abs(gap), 2),
        "explanations": explanations,
        "explained_by": round(explained, 2),
        "unexplained": round(unexplained, 2),
        "channel_note": channel.get("推论") or "",
        "checks": [c for e in explanations for c in (e.get("佐证") or [])][:8],
        "text": "".join(parts),
    }


def _fmt(v: Any) -> str:
    try:
        return format(float(v), ",.2f")
    except Exception:
        return str(v)


# ── 通用推演：任意疑点都套的"多想一层" ───────────────────────────────────────
def ladder_for_suspicion(suspicion: Dict[str, Any],
                         lateral: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """为一个疑点生成「推断与联想」段（引擎侧算好，报告侧只渲染）。

    `lateral`：引擎在发现上附带的具体推演（如收入差集），优先使用。
    """
    rid = str((suspicion or {}).get("redline_id") or "").strip()
    title = str((suspicion or {}).get("redline_name") or (suspicion or {}).get("title") or "").strip()
    lib = load_ladders()
    pack = ((lib.get("红线推演") or {}).get(rid)) or {}
    frame = ((lib.get("通用推演") or {}).get("框架")) or []

    bullets: List[str] = []
    if lateral:
        _exps = lateral.get("explanations") or []
        # ★ 2026-10-03：**正常解释与违规手法必须分开** —— 曾把"未开票收入未入账（隐匿收入）"
        #   也列进"账内可能的正常情形"，读者会以为系统认为隐匿收入是正常情形。
        pack = {
            "正常解释": [str(e.get("解释")) for e in _exps
                     if e.get("解释") and e.get("性质") != "违规嫌疑"],
            "违规手法": [str(e.get("解释")) for e in _exps if e.get("性质") == "违规嫌疑"],
            "判别检验": list(dict.fromkeys(lateral.get("checks") or []))[:8],
            "渠道限制": lateral.get("channel_note") or "",
        }
    if pack.get("正常解释"):
        bullets.append("账内可能的正常情形：" + "；".join(pack["正常解释"][:5]))
    if pack.get("违规手法"):
        bullets.append("若为违规，通常的手法：" + "；".join(pack["违规手法"][:4]))
    if pack.get("判别检验"):
        bullets.append("能把上面两类区分开的资料：" + "；".join(pack["判别检验"][:6]))
    if pack.get("渠道限制"):
        bullets.append("逻辑限制：" + str(pack["渠道限制"]))
    if lateral and lateral.get("text"):
        bullets.insert(0, lateral["text"])
    if not bullets:
        # 没有专属推演包时，退到通用框架（保证"每次都触发"这件事本身不发生静默）
        bullets = ["本项按通用推演框架逐条展开：" + "；".join(frame[:5])]
    return {
        "heading": "六、从本项到全局：可能的解释与如何区分",
        "text": ("本项不是只有一个结论。就上述读数而言，先把「正常经营下可能是什么」与"
                 "「若为违规会是什么样」摊开，再落到「哪份资料能把两者分开」——"
                 "不能区分的部分，才需要企业举证。"),
        "bullets": bullets,
        "source": ("推演库（红线专属）" if rid in (lib.get("红线推演") or {}) else "通用推演框架"),
    }


def open_item_movement(vouchers) -> Dict[str, float]:
    """从序时账取「应收账款净增」「预收账款/合同负债净增」（用于解释收入差集）。

    唯一权威取科目名（`fieldkit.account_name`，**不是** account 编码字段）。
    """
    from engine.fieldkit import account_name as _acct_name
    from engine.numparse import to_number as _num

    ar = adv = 0.0
    for v in (vouchers or []):
        if not isinstance(v, dict):
            continue
        name = _acct_name(v)
        d = _num(v.get("debit", 0))
        c = _num(v.get("credit", 0))
        if "应收账款" in name or "应收票据" in name:
            ar += d - c
        elif "预收账款" in name or "合同负债" in name:
            adv += c - d
    return {"ar_movement": round(ar, 2), "advance_movement": round(adv, 2)}


__all__ = ["load_ladders", "revenue_gap_reasoning", "ladder_for_suspicion",
           "open_item_movement"]

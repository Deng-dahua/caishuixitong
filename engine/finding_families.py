# -*- coding: utf-8 -*-
"""**风险事项同族合并**的唯一权威（2026-10-06）。

## 为什么必须有它（用户评语：事项数量虚高、同一事实被拆成多个疑点）
用户在评语里逐条点名了重复关系（原文摘录）：
  · **薪酬三源**：疑点2 工资表人数与社保参保人数不符 / 疑点8 公积金未开户或基数不实 /
    疑点26 个税申报工资与账面工资、社保基数三者不一致 / 疑点32 公私混同发薪 /
    疑点33 社保低基数参保 —— 「都在讲同一批人、同一批工资、同一批社保基数」；
  · **个人账户/公转私/资金回流**：疑点16 / 17 / 20 / 31 / 34 ——
    「同一批个人账户收付、初永伟 1,071,343.80、李昭阳 1,004,478.76、私户收款 1,082,000 在多处重复」；
  · **银行收款/未开票/其他应付款**：疑点3 / 10 / 12 / 34；
  · **关联交易/对手方重叠**：疑点19 / 27；
  · **进项与申报差异**：疑点25 / 29（同一差异 4,501.34、32,630.49）；
  · **印花税四项同构**：疑点6 / 21 / 22 / 23 ——「同一逻辑，只换了税目和金额」；
  · 并指出「疑点27—34 基本是前面疑点的重复或汇总」⇒ **虚增事项数**。

## 设计（数据驱动；新增一族只加一行，不改逻辑分支）
  ① `FAMILIES`：族 → 关键词组（按**标题/红线名**命中即归族）；
  ② 同族内选**一个主事项**：等级最高 → 潜在税额最大 → 原顺序靠前；其余降为**子项**；
  ③ 子项**不再单独计入风险事项数**，但其信息**不丢**：
     主事项下挂 `family_members`（标题 / 等级 / 红线号 / 各自差异点 / 潜在税额），
     并在主事项的「涉及的风险事项」段如实写明"本族另含 N 个子项，差异点如下"；
  ④ **不合并跨族**；**不改变任何判定、等级、金额**；单族仅 1 项时**零改动**（幂等）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

#: 风险族 → 归族关键词（按**标题 + 红线名**匹配；命中任一即归该族）
#  ⚠ 顺序即优先级：先命中者胜（避免"公私混同发薪"同时命中薪酬族与资金族时摇摆）。
FAMILIES: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("薪酬与用工三源", "薪酬三源", (
        "工资表人数", "社保参保人数", "社会保险", "社保低基数", "低基数参保",
        "公积金", "住房公积金", "个税申报工资", "账面工资", "社保基数",
        "公私混同发薪", "私户支付薪酬", "用工", "参保",
    )),
    ("资金流与公私混同", "资金与公私混同", (
        "资金回流", "公私混同", "公转私", "个人账户", "私户", "资金对手方",
        "大额双向收付", "多税种联动", "资金流", "回流",
    )),
    ("印花税税目申报", "印花税", (
        "印花税", "借款合同", "租赁合同", "保险合同", "计税依据不足",
    )),
    ("进项与申报差异", "票账差异", (
        "表间勾稽", "进项税额", "进项发票税额", "认证税额", "申报进项税额",
        "票账差异", "四方比对",
    )),
    ("关联交易与对手方重叠", "关联与对手方", (
        "关联交易", "关联方", "同一交易对手", "客户与供应商", "购销闭环",
        "六员", "个体户供应商", "个人/个体户", "供应商客户",
    )),
    ("收入与银行收款", "收入与银行收款", (
        "银行收款", "申报收入", "未开票收入", "账外收入", "其他应付款",
        "收入三源", "销项与银行",
    )),
)

#: 等级排序（用于选主事项）——★ 2026-10-06 转发**唯一权威** `engine.risk_levels`：
#  本模块原先自建 `_LV_RANK`，与 `pipeline::_sev` / `enterprise_report` 的两张表**互相矛盾**
#  （对「信息 vs 低风险」给出相反答案），同一事项在不同章节会被判成不同等级。
from engine.risk_levels import severity as _risk_severity


def _blob(p: Dict[str, Any]) -> str:
    """取归族判据文本：**只看主题字段**（标题 / 红线名 / 税种 / 发现类型），
    不扫正文 —— 正文里偶然提到"个人账户支付"不代表本项主题是资金类。"""
    return " ".join(str(p.get(k) or "") for k in
                    ("title", "redline_id", "redline_name", "finding_type", "taxes", "category"))


def classify_family(p: Dict[str, Any]) -> Optional[str]:
    """判定某风险事项所属的风险族；不属任何族 ⇒ None（保持独立）。"""
    b = _blob(p)
    for fam, _label, kws in FAMILIES:
        if any(k in b for k in kws):
            return fam
    return None


def _family_amount(p: Dict[str, Any]) -> float:
    """取本项潜在税额合计（**用于选主事项**，非业务金额解析）。

    ⚠ 命名必须避开 `_amount_of` —— 那是别处的既有实现；本项目「数值解析唯一权威
       `engine/numparse`」，任何取值都必须**转发**它，不得自写解析（闸门会报
       "数值解析多头维护"）。这里取的是已解析好的 `tax_impact.total`，仍走
       `to_number_checked` 以保证口径一致与异常可追溯。
    """
    try:
        from engine.numparse import to_number_checked as _tnc
        v = (p.get("tax_impact") or {}).get("total")
        return float(_tnc(v)[0] or 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def merge_families(problems: List[Dict[str, Any]]) -> Dict[str, Any]:
    """同族合并：原地把**子项**从 `problems` 移除，并挂到主事项的 `family_members`。

    :return: {"merged_families": n, "removed_items": n, "detail": [...]}
    """
    stat = {"merged_families": 0, "removed_items": 0, "detail": []}
    if not isinstance(problems, list) or len(problems) < 2:
        return stat

    groups: Dict[str, List[int]] = {}
    for i, p in enumerate(problems):
        if not isinstance(p, dict):
            continue
        fam = classify_family(p)
        if fam:
            groups.setdefault(fam, []).append(i)

    drop: set = set()
    for fam, idxs in groups.items():
        if len(idxs) < 2:
            continue          # 单族仅一项 ⇒ 零改动（幂等）
        # 选主事项：等级高 → 税额大 → 原顺序靠前（等级标度走权威 `risk_levels.severity`）
        idxs_sorted = sorted(
            idxs,
            key=lambda i: (-_risk_severity(problems[i].get("risk_level")),
                           -_family_amount(problems[i]), i),
        )
        lead_i = idxs_sorted[0]
        lead = problems[lead_i]
        members = []
        for i in idxs_sorted[1:]:
            sub = problems[i]
            members.append({
                "title": str(sub.get("title") or "")[:60],
                "risk_level": sub.get("risk_level") or "",
                "redline_id": sub.get("redline_id") or "",
                "tax_impact_total": _family_amount(sub) or None,
                "diff_point": str(sub.get("verdict") or sub.get("summary") or "")[:80],
            })
            drop.add(i)
        if members:
            lead["family"] = {"name": fam, "label": next(
                (lb for f, lb, _k in FAMILIES if f == fam), fam)}
            lead["family_members"] = members
            # ★★ 2026-10-06：登记**同族别名**（族主标题 + 被并入成员标题）。
            #   为什么必须：`report_layout.QUESTION_THEME_TO_PROBLEM`（询问主题归属表，
            #   唯一权威）按**原疑点标题关键词**登记；同族合并后族主标题变了
            #   ⇒ 归属关键词匹配不上 ⇒ 询问主题**全部退回残余章**，与风险事项重复呈现
            #   （实测 5 条：资金·私户收款性质／资金·关联闭环／进项·双向往来主体／
            #     虚开·同额凑数／虚开·双向往来主体）。
            #   有了别名，归属表**一行都不用改**，也不必为"合并后标题长什么样"写特例。
            _aliases = {str(lead.get("title") or "")}
            for _m in members:
                _aliases.add(str(_m.get("title") or ""))
            lead["_family_aliases"] = sorted(x for x in _aliases if x)
            # 子项更原始的标题也可作别名（红线名/发现类型常与归属表关键词一致）
            _extra_alias = set()
            for _i in idxs_sorted[1:]:
                _sub = problems[_i]
                for _k in ("redline_name", "finding_type", "title"):
                    _v = str(_sub.get(_k) or "").strip()
                    if _v:
                        _extra_alias.add(_v)
            if _extra_alias:
                lead["_family_aliases"] = sorted(
                    set(lead["_family_aliases"]) | _extra_alias)
            # ★ **不静默丢**：把子项如实写进主事项的「一、涉及的风险事项」段，
            #   写明"本族另含 N 个子项"及各自差异点（企业仍能看到全部内容）。
            try:
                _names = "；".join("%s（%s）" % (m["title"], m["risk_level"] or "未定级")
                                   for m in members[:6])
                _extra = ("本项与以下 %d 个子项属同一风险族「%s」，子项不再单独计数，"
                          "差异点：%s。" % (len(members), fam, _names))
                _paras = lead.get("narrative_paragraphs") or []
                _hit = False
                for _pr in _paras:
                    if str((_pr or {}).get("heading") or "").strip() == "一、涉及的风险事项":
                        _pr["text"] = str(_pr.get("text") or "") + _extra
                        _hit = True
                        break
                if not _hit:
                    _paras.insert(0, {"heading": "一、涉及的风险事项", "text": _extra})
                    lead["narrative_paragraphs"] = _paras
            except Exception:  # noqa: BLE001
                pass
            stat["merged_families"] += 1
            stat["removed_items"] += len(members)
            stat["detail"].append({"family": fam, "lead": str(lead.get("title"))[:40],
                                   "members": [m["title"] for m in members]})

    if drop:
        for i in sorted(drop, reverse=True):
            problems.pop(i)
    return stat

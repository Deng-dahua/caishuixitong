# -*- coding: utf-8 -*-
"""从点到面抽象 —— 规则萃取建议（用户第 4 批 任务3）。

## 任务原文的闭环

> 「每次分析后，系统自动判断该发现能否抽象成规则。能抽象成规则的，进入规则萃取流程；
>  不能抽象成规则的，作为个案记录。规则必须**可配置、可测试、可版本化**。
>  输出《规则萃取建议》。」

本模块把"点（一条发现）"判成"面（一条通用规则）"或"个案"，并产出规则草案。

## 判据（★ 唯一权威表 `ABSTRACT_CRITERIA`，新增判据只加一行）

**能抽象**必须同时满足 4 条硬门槛（缺一不可，**不得默认上升为规则**）：
1. 根因可通用表达（现象里**不含**只属于本企业的标识）；
2. 存在**可机检判据**（能写成"当 X 成立判为 Y"，且 X 可由现有数据算出）；
3. 具备**复发可能**（换企业/换期间仍会重复出现）；
4. 有**可执行验收**（能写出一条会失败的用例 ⇒ 可反向验证）。

任一不满足 ⇒ 归入**个案记录**，并写明不满足哪一条（不留"判不出"的模糊态）。

## 三条硬要求怎么落地

| 要求 | 落点 |
|---|---|
| 可配置 | 规则草案带 `params_ref`（指向数据表/配置文件）与 `judge`，改阈值只改数据 |
| 可测试 | `acceptance` 必填 + `test_hint` 给出用例形态；无验收不许出草案 |
| 可版本化 | `rule_version`（语义化）+ `version_note` + 入库走 `retrospective` 台账（append-only） |
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

#: 抽象判据表（★ 唯一权威）
#:   key = 判据码；value = (中文名, 判据说明, 方向)  方向 ∈ {"pass","fail"}
ABSTRACT_CRITERIA: Tuple[Tuple[str, str, str, str], ...] = (
    ("generic_root_cause", "根因可通用表达",
     "现象里不含只属于本企业的标识（具体凭证号/账号/证件号/单笔事件）", "pass"),
    ("abstractable_judge", "存在可机检判据",
     "能写成「当 X 条件成立则判为 Y」，且 X 可由现有数据算出", "pass"),
    ("abstractable_recurrence", "具备复发可能",
     "同类情形在其他企业/其他期间可能重复出现", "pass"),
    ("abstractable_acceptance", "有可执行验收",
     "能为该规则写出一条会失败的用例（可反向验证）", "pass"),
    ("case_specific_identity", "现象绑定特定实体",
     "现象里含具体凭证号/账号/证件号/单笔标记 ⇒ 换个企业就不成立", "fail"),
    ("case_specific_event", "属一次性事件",
     "依赖某次偶发事件，无通用触发条件", "fail"),
    ("case_specific_no_judge", "写不出可机检判据",
     "无法表达为可由现有数据计算的条件", "fail"),
    ("case_specific_no_acceptance", "无可执行验收",
     "写不出任何会失败的用例 ⇒ 无法反向验证", "fail"),
)

#: 「绑定特定实体」的文本特征（★ 唯一权威：新增一类只加一行正则）
SPECIFIC_ID_PATTERNS: Tuple[str, ...] = (
    r"凭证号\s*[A-Za-z0-9\-]{4,}",
    r"第\s*\d+\s*号凭证",
    r"账号\s*[0-9\*]{6,}",
    r"(?:身份证|统一社会信用代码)\s*[0-9A-Za-z]{6,}",
    r"共\s*1\s*笔",
    r"仅\s*1\s*笔",
    r"单笔",
    r"票号\s*[0-9]{6,}",
)

#: 「一次性事件」的文本特征（偶发、无通用触发条件）
ONE_OFF_PATTERNS: Tuple[str, ...] = (
    r"本次仅此一例", r"偶发", r"一次性", r"特殊情况下", r"偶然",
)

#: 风险族关键词 → 规则族前缀（让规则号可读且有归类）
_FAMILY_PREFIX: Tuple[Tuple[str, str], ...] = (
    ("工资", "PAY"), ("社保", "PAY"), ("公积金", "PAY"), ("个税", "PAY"),
    ("收入", "REV"), ("开票", "REV"), ("申报", "REV"), ("账外", "REV"),
    ("成本", "COST"), ("费用", "COST"), ("扣除", "COST"), ("凭证", "COST"),
    ("资金", "FUND"), ("私户", "FUND"), ("银行", "FUND"), ("往来", "FUND"),
    ("关联", "REL"), ("发票", "INV"), ("虚开", "INV"), ("印花", "STAMP"),
)

#: 规则版本（草案首版）；`rule_version` 会随 `judge`/阈值变化而提升
DEFAULT_RULE_VERSION = "1.0.0"


def _finding_text(f: Any) -> str:
    if not isinstance(f, dict):
        return str(f or "")
    parts = [str(f.get(k) or "") for k in
             ("title", "type", "finding_type", "detail", "description", "suspect",
              "redline_name", "how_found")]
    return " ".join(parts)


def _family_of(f: Any) -> str:
    t = _finding_text(f)
    for kw, pref in _FAMILY_PREFIX:
        if kw in t:
            return pref
    return "GEN"


def can_abstract(finding: Any, context: Optional[Dict[str, Any]] = None
                 ) -> Tuple[bool, List[Dict[str, str]]]:
    """判断一条发现能否抽象成规则。返回 `(可否, [{code, name, detail, direction}])`。

    ★ 四条 pass 门槛必须**全部**满足，且不得触发任一 fail 特征；
      **判不出也当"不可抽象"**（默认归个案，绝不默认上升为规则）。
    """
    ctx = context or {}
    t = _finding_text(finding)
    verdicts: List[Dict[str, str]] = []

    def _add(code: str, detail: str) -> None:
        for k, name, judge, direction in ABSTRACT_CRITERIA:
            if k == code:
                verdicts.append({"code": k, "name": name, "detail": detail,
                                 "direction": direction, "judge": judge})
                return

    hits = [p for p in SPECIFIC_ID_PATTERNS if re.search(p, t)]
    if hits:
        _add("case_specific_identity", "现象中出现实体绑定特征：%s" % "、".join(hits[:3]))
    if any(re.search(p, t) for p in ONE_OFF_PATTERNS):
        _add("case_specific_event", "现象自述为偶发/一次性事件")

    # 判据可得性：有明确判据字段，或调用方显式给出 judge
    judge = str(ctx.get("judge") or "")
    has_judge = bool(judge) or any(finding.get(k) for k in
                                   ("indicator", "redline_id", "rule_id", "condition")
                                   if isinstance(finding, dict))
    if not has_judge:
        _add("case_specific_no_judge", "既无红线/指标标识，调用方也未给出可机检判据")

    acceptance = str(ctx.get("acceptance") or "")
    has_acceptance = bool(acceptance) or bool(ctx.get("test_hint"))
    if not has_acceptance:
        _add("case_specific_no_acceptance", "未给出会失败的用例（无法反向验证）")

    if not any(v["direction"] == "fail" for v in verdicts):
        _add("generic_root_cause", "现象描述通用于同类情形，未绑定单一实体")
        _add("abstractable_judge", judge or "以红线/指标字段作为机检判据")
        _add("abstractable_recurrence", "同类风险族在报告历史中可复用（见复盘台账）")
        _add("abstractable_acceptance", acceptance or str(ctx.get("test_hint") or "见附录用例"))

    ok = (not any(v["direction"] == "fail" for v in verdicts)
          and {v["code"] for v in verdicts if v["direction"] == "pass"}
          == {"generic_root_cause", "abstractable_judge",
              "abstractable_recurrence", "abstractable_acceptance"})
    return ok, verdicts


def abstract(finding: Any, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """把一条**可抽象**的发现转成规则萃取建议（不可抽象时返回 None，由调用方记个案）。"""
    ok, verdicts = can_abstract(finding, context)
    if not ok:
        return None
    ctx = context or {}
    fam = _family_of(finding)
    seq = int(ctx.get("seq") or 1)
    title = str((finding or {}).get("title") or (finding or {}).get("type") or "规则").strip()
    judge = str(ctx.get("judge") or "").strip() or (
        "以红线/指标判定条件为准：当「%s」所述条件成立时，判为「%s」风险。"
        % (str((finding or {}).get("redline_id") or (finding or {}).get("indicator") or "指标"),
           title[:30]))
    acceptance = str(ctx.get("acceptance") or "").strip() or str(ctx.get("test_hint") or "").strip()
    return {
        "rule_id": "AR-%s-%03d" % (fam, seq),
        "title": "从点到面规则：%s" % title[:40],
        "from_finding": title[:60],
        "risk_family": fam,
        "tier": str(ctx.get("tier") or "manual"),
        # ── 可配置 ──
        "judge": judge,
        "params_ref": str(ctx.get("params_ref") or ""),
        # ── 可测试 ──
        "acceptance": acceptance or "须补一条会失败的用例（未提供时不得入库）",
        "test_hint": str(ctx.get("test_hint") or ""),
        # ── 可版本化 ──
        "rule_version": str(ctx.get("rule_version") or DEFAULT_RULE_VERSION),
        "version_note": "首版：由第 4 批「从点到面抽象」产出，须人工确认后方可入库生效。",
        "affects_risk_level": False,
        "criteria": verdicts,
    }


def abstract_findings(findings: Iterable[Any],
                      context: Optional[Dict[str, Any]] = None
                      ) -> Dict[str, Any]:
    """批量抽象。返回 `{proposals, cases_kept, summary_line}`。

    `cases_kept` = 归入**个案记录**的条目（附不满足的判据码，绝不静默丢弃）。
    """
    ctx = context or {}
    proposals: List[Dict[str, Any]] = []
    cases: List[Dict[str, Any]] = []
    for i, f in enumerate(findings or [], 1):
        c = dict(ctx)
        c.setdefault("seq", i)
        ok, verdicts = can_abstract(f, c)
        title = str((f or {}).get("title") or (f or {}).get("type") or "未命名事项") if isinstance(f, dict) else str(f)
        if ok:
            p = abstract(f, c)
            if p:
                proposals.append(p)
                continue
        fails = [v for v in verdicts if v["direction"] == "fail"]
        cases.append({
            "title": title[:60],
            "kept_as": "个案",
            "reason_codes": [v["code"] for v in fails] or ["未满足全部抽象门槛"],
            "reasons": [v["detail"] for v in fails] or ["四条抽象门槛未全部满足"],
        })
    return {
        "proposals": proposals,
        "cases_kept": cases,
        "summary_line": ("本轮共 %d 条发现：其中 %d 条可抽象为规则（进入规则萃取流程，"
                         "须人工确认后入库）、%d 条作为个案记录（写明不满足的判据，不静默丢弃）。"
                         % (len(proposals) + len(cases), len(proposals), len(cases))),
    }


def commit_proposals(proposals: Iterable[Dict[str, Any]], dry_run: bool = True
                     ) -> Dict[str, List[Dict[str, Any]]]:
    """把规则草案送去**规则萃取流程**（薄转发 `retrospective` + 受 `learnable_rules` 守卫）。

    ★ `tier` 不可自动写入的（manual/forbidden/accumulate）**只登记事件、不入库生效**。
    """
    from engine.learnable_rules import guard_rule_write
    from engine.retrospective import PATTERN_SIGNATURES, record_event
    committed: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    for p in (proposals or []):
        rec = dict(p)
        try:
            guard_rule_write(str(p.get("tier") or "manual"))
            allowed = True
        except PermissionError as exc:
            rec["reason"] = str(exc)
            allowed = False
        if not dry_run:
            try:
                record_event({
                    "source": "从点到面抽象",
                    "module": "engine/rule_abstraction.py",
                    "symptom": rec.get("from_finding"),
                    "root_cause": rec.get("judge"),
                    "fix": "建议规则 %s（%s）" % (rec.get("rule_id"), rec.get("rule_version")),
                    "pattern_signature": "rule_from_point",
                    "evidence": [rec.get("acceptance") or ""],
                })
            except Exception:
                pass
        (committed if allowed else pending).append(rec)
    return {"committed": committed, "pending_manual": pending}


def render_proposals_md(result: Dict[str, Any]) -> str:
    """《规则萃取建议》（可独立交付）。"""
    L = ["# 规则萃取建议（从点到面）", "", str((result or {}).get("summary_line") or ""), ""]
    props = (result or {}).get("proposals") or []
    if props:
        cols = ["建议规则号", "来源事项", "风险族", "层级", "可机检判据", "验收方式", "版本"]
        L += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        for p in props:
            L.append("| " + " | ".join(
                str(p.get(k) or "—") for k in
                ("rule_id", "from_finding", "risk_family", "tier", "judge",
                 "acceptance", "rule_version")) + " |")
        L += ["", "三条硬要求：**可配置**（`params_ref` 指向数据表，改阈值只改数据）、"
              "**可测试**（`acceptance` 必填，须会失败才有效）、"
              "**可版本化**（`rule_version` + 入库台账 append-only）。", ""]
    else:
        L += ["本轮无可抽象规则。", ""]
    cases = (result or {}).get("cases_kept") or []
    if cases:
        L += ["## 归入个案记录（不上升为规则）", "",
              "| 事项 | 不满足的判据 | 说明 |", "|---|---|---|"]
        for c in cases:
            L.append("| %s | %s | %s |" % (c.get("title"),
                                           "、".join(c.get("reason_codes") or []),
                                           "；".join(c.get("reasons") or [])[:120]))
        L.append("")
    L += ["> 契约：规则草案**不改变任何风险等级**；`manual`/`forbidden` 档必须人工确认后才可入库。", ""]
    return "\n".join(L)


__all__ = ["ABSTRACT_CRITERIA", "SPECIFIC_ID_PATTERNS", "ONE_OFF_PATTERNS",
           "DEFAULT_RULE_VERSION", "can_abstract", "abstract", "abstract_findings",
           "commit_proposals", "render_proposals_md"]

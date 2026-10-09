# -*- coding: utf-8 -*-
"""知识库自学习模块（唯一权威实现）——把「每次报告暴露的问题」自动提炼为可复用知识。

指令依据（阶段9 第10项）：「每次报告问题自动提炼规则，更新知识库。」
闭环（指令阶段11 第15项）：
    报告生成 → 自动诊断 → **规则提炼** → **知识库更新** → 回归测试 → 发布新版本

设计原则（防止"自学习"变成"自污染"）：
  1. **只提炼、不直接改判据**：候选规则写入 `config/knowledge_candidates.json`，
     须人工确认后才由人合入 `dedup_rules.json` / `root_causes.json` 等权威表。
     （理由：自动改判据会导致判据漂移且不可追溯——项目已有"两处实现必然漂移"的教训）
  2. **每条候选必须带证据**：来源报告/命中位置/命中次数/建议落点，可复核。
  3. **幂等**：同一候选规则重复学习只累加 `times_seen`，不重复登记。
  4. **问题样本入库**：把本次报告作为问题样本写入 `config/experience_cases.json`。

对外接口：
  learn_from_diagnosis(problems, rates, *, sample_id) -> 候选规则
  record_case(case)               -> 问题样本入库
  update_knowledge(problems, rates, sample_id, case=None) -> 一次做完两件事
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CAND = os.path.join(_ROOT, "config", "knowledge_candidates.json")
_CASES = os.path.join(_ROOT, "config", "experience_cases.json")

#: 问题类别 → 建议落点（唯一权威表；新增类别只加一行）
CATEGORY_TO_TARGET = {
    "重复冗余": "config/dedup_rules.json",
    "数据与计数一致性": "engine/reconciliation.py",
    "数据与法规校验": "config/tax_limits.json",
    "定性口径": "config/conclusion_grades.json",
    "证据链闭合": "config/conclusion_grades.json",
    "等级与证据强度": "engine/risk_levels.py",
    "法规引用": "config/legal_versions.json",
    "术语一致性": "engine/risk_levels.py",
    "结构与导航": "config/report_structure.json",
    "归档与模板整洁": "config/archive_spec.json",
    "行业适配": "config/industry_params.json",
    "多版本输出": "engine/output_variants.py",
    "自检缺失": "engine/quality_gates.py",
}


def _load(p: str, default: Any) -> Any:
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001 —— 读不出用默认（首次运行时文件不存在）
        return default


def _save(p: str, obj: Any) -> None:
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


def learn_from_diagnosis(problems: List[Dict[str, Any]], rates: Optional[Dict[str, Any]] = None,
                         *, sample_id: str = "") -> Dict[str, Any]:
    """从诊断结果提炼**候选**规则（不直接改判据）。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    store = _load(_CAND, {"schema": 1, "note": "自学习候选规则（须人工确认后才合入权威表）", "candidates": []})
    cands: List[Dict[str, Any]] = store.setdefault("candidates", [])
    index = {c.get("key"): c for c in cands}

    added, bumped = 0, 0
    for p in problems or []:
        pid = str(p.get("id") or "")
        name = str(p.get("name") or "")
        cnt = int(p.get("count") or 0)
        # 只提炼"确实检出且需要长期防范"的问题（未检出/PASS 的不进候选）
        if cnt <= 0 and str(p.get("status") or "") not in ("检出", "FAIL", "未检出（即缺）"):
            continue
        key = f"{pid}:{name}"
        target = CATEGORY_TO_TARGET.get(str(p.get("category") or ""), "（待定，须人工归类）")
        if key in index:
            index[key]["times_seen"] = int(index[key].get("times_seen") or 1) + 1
            index[key]["last_sample"] = sample_id
            bumped += 1
            continue
        cands.append({
            "key": key, "problem_id": pid, "category": p.get("category"),
            "name": name, "evidence": str(p.get("sample") or p.get("detail") or "")[:160],
            "hits": cnt, "suggested_target": target,
            "suggested_rule": f"为『{name}』补一条机器判据（命中即阻断输出）",
            "times_seen": 1, "first_sample": sample_id, "last_sample": sample_id,
            "status": "待人工确认", "created_at": now,
        })
        added += 1

    store["updated"] = now
    store["last_run"] = {"sample_id": sample_id, "added": added, "bumped": bumped}
    _save(_CAND, store)
    return {"added": added, "bumped": bumped, "total": len(cands),
            "path": _CAND, "note": "候选规则须人工确认后合入权威表（不自动改判据）"}


def record_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """把本次报告作为问题样本入库（幂等：同 case_id 不重复登记）。"""
    store = _load(_CASES, {"schema": 1, "cases": []})
    cases: List[Dict[str, Any]] = store.setdefault("cases", [])
    cid = str(case.get("case_id") or "")
    for c in cases:
        if str(c.get("case_id")) == cid:
            return {"added": False, "reason": f"{cid} 已入库", "total": len(cases)}
    case.setdefault("added_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
    cases.append(case)
    _save(_CASES, store)
    return {"added": True, "total": len(cases), "case_id": cid}


def update_knowledge(problems: List[Dict[str, Any]], rates: Optional[Dict[str, Any]] = None,
                     *, sample_id: str = "", case: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """闭环入口：一次完成「规则提炼 + 问题样本入库」。"""
    lr = learn_from_diagnosis(problems, rates, sample_id=sample_id)
    cr = record_case(case) if case else {"added": False, "reason": "未提供 case"}
    return {"learn": lr, "case": cr,
            "summary": (f"候选规则 +{lr['added']}（累计 {lr['total']}）；"
                        f"样本入库={'是' if cr.get('added') else '否'}")
            }


# ══════════════════════════════════════════════════════════════════════════
# 从**本次报告**提炼问题与样本（唯一权威）
#   ★ 2026-10-08（条款 A10 核验发现）：产出链接线调用 `update_knowledge(problems, …)`
#     时 ① **没传 `case`** ⇒ `record_case` 从不执行、样本库永远为空（实测 experience_cases
#     仅 1 条手工样例）；② `problems` 读的是离线 `baseline/阶段1/问题诊断.json`
#     （**上一次离线诊断**的静态结果）⇒ 提炼源与"本次报告"**无关**。
#   现改为从本次报告的真实问题信号归一（不再依赖离线文件）。
# ══════════════════════════════════════════════════════════════════════════
def problems_from_report(report_data: Any) -> List[Dict[str, Any]]:
    """把本次报告的**问题信号**归一为自学习 `problems`（唯一权威取数）。

    信号来源（都取"确实未通过/确有命中"的项，`status` 一律含『检出/FAIL/不通过』，
    以便 `learn_from_diagnosis` 正确纳入）：
      · `_dedup_rate_after` / `_duplicate_rate`  → 重复冗余
      · `_wording_audit` 命中                     → 定性口径
      · `_reconciliation` 阻塞/差异               → 数据与计数一致性
      · `_pipeline_selfcheck` 不通过项            → 自检缺失
      · `_quality_gates` ERROR                    → 自检缺失
      · `_legal_versions` 阻断（版本未核）        → 法规引用
      · `_material_gap` 缺失资料                  → 证据链闭合
    """
    if not isinstance(report_data, dict):
        return []
    out: List[Dict[str, Any]] = []

    def add(pid: str, category: str, name: str, detail: str, count: int = 1) -> None:
        out.append({"id": pid, "category": category, "name": name,
                    "status": "检出", "count": int(count or 1), "detail": str(detail)[:200]})

    dr = report_data.get("_duplicate_rate") or {}
    if isinstance(dr, dict) and dr.get("阻断"):
        _o = dr.get("整体") or {}
        add("R-DUP", "重复冗余", "报告重复率超阈",
            "整体 %.2f%%（阈值 %.0f%%）；章节超阈 %s；事实超额 %s"
            % ((_o.get("重复率") or 0) * 100, (_o.get("阈值") or 0.1) * 100,
               (dr.get("章节统计") or {}).get("超阈章节"),
               (dr.get("事实重复") or {}).get("超额出现次数合计")), 1)

    wa = report_data.get("_wording_audit")
    if isinstance(wa, list) and wa:
        for h in wa[:8]:
            if isinstance(h, dict):
                add("R-WORD-%s" % h.get("rule", "?"), "定性口径",
                    str(h.get("name") or "措辞破句"), str(h.get("sample") or h.get("detail") or ""), 1)

    rc = report_data.get("_reconciliation") or {}
    if isinstance(rc, dict) and (rc.get("blocking") or rc.get("差异") or rc.get("diffs")):
        add("R-RECON", "数据与计数一致性", "数据勾稽存在阻塞项",
            str(rc.get("summary") or "")[:180], 1)

    sc = report_data.get("_pipeline_selfcheck")
    if isinstance(sc, list):
        fails = [c for c in sc if isinstance(c, dict) and c.get("结果") == "不通过"]
        for c in fails[:10]:
            add("R-SELF-%s" % c.get("no", "?"), "自检缺失",
                str(c.get("项") or "产出链自检不通过"), str(c.get("明细") or ""), 1)

    qg = report_data.get("_quality_gate") or report_data.get("_quality_gates") or {}
    if isinstance(qg, dict):
        _gates = qg.get("gates") or []
        _any_fail = False
        for g in _gates:
            if not isinstance(g, dict):
                continue
            st = str(g.get("status") or g.get("result") or "").upper()
            if st in ("FAIL", "不通过") or g.get("passed") is False:
                _any_fail = True
                for it in (g.get("issues") or [])[:4]:
                    if isinstance(it, dict) and str(it.get("level", "")) == "ERROR":
                        add("R-QG-%s" % g.get("id", "?"), "自检缺失",
                            str(it.get("message") or g.get("name") or "质量门禁 ERROR"), "")
        if qg.get("gate_passed") is False and not _any_fail:
            add("R-QG", "自检缺失", "质量门禁未通过",
                "决策边界：%s" % str(qg.get("decision_boundary"))[:120], 1)

    lv = report_data.get("_legal_versions") or {}
    if isinstance(lv, dict) and lv.get("blocking"):
        add("R-LAW", "法规引用", "法规版本未核到现行有效",
            str(lv.get("summary") or ""), 1)

    mg = report_data.get("_material_gap") or {}
    if isinstance(mg, dict):
        _m = mg.get("missing") or mg.get("missing_materials") or []
        if _m:
            add("R-MAT", "证据链闭合", "必查资料缺失（检查受限）",
                "缺失 %d 项：%s" % (len(_m), "、".join(str(x) for x in _m[:8])), len(_m))
    return out


def case_from_report(report_data: Any, company_id: Any = "") -> Dict[str, Any]:
    """把**本次报告**归一为问题样本（`config/experience_cases.json` 的 case 结构）。"""
    if not isinstance(report_data, dict):
        report_data = {}
    er = report_data.get("enterprise_readable_report")
    er = er if isinstance(er, dict) else {}
    cp = er.get("confirmed_problems") or report_data.get("confirmed_problems") or []
    te = report_data.get("target_entity") or {}
    ind = (te.get("industry") if isinstance(te, dict) else "") or ""
    _cr = report_data.get("compliance_round") or {}
    _round = _cr.get("round_no")
    problems = []
    for it in (cp or [])[:60]:
        if isinstance(it, dict):
            problems.append({
                "seq": it.get("seq"), "title": it.get("title"),
                "risk_level": it.get("risk_level"),
                "conclusion_grade": it.get("conclusion_grade"),
                "redline_id": it.get("redline_id"),
            })
    _cp_txt = (report_data.get("_pipeline_selfcheck") or [])
    fixes = [str(c.get("项")) for c in _cp_txt
             if isinstance(c, dict) and c.get("结果") == "不通过"][:20]
    _dup = (report_data.get("_duplicate_rate") or {}).get("整体") or {}
    return {
        "case_id": "AUTO-%s-R%s" % (company_id, _round if _round is not None else "?"),
        "name": "一键分析自动留档：%s" % (er.get("summary", {}) or {}).get("headline", "")[:40]
        if isinstance(er.get("summary"), dict) else "一键分析自动留档",
        "industry": ind,
        "business_category": (te.get("business_category") if isinstance(te, dict) else "") or "",
        "problems": problems,
        "fixes": fixes,
        "metrics": {"整体重复率": _dup.get("重复率"), "风险事项数": len(problems),
                    "轮次": _round},
        "source": "one_click_analysis",
    }

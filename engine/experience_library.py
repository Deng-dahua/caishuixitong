# -*- coding: utf-8 -*-
"""同类案例经验库 —— 统一出口（用户第 4 批 任务2）。

## 与既有模块的关系（**不新建第二份实现**）

- `engine/case_library.py` 是**法律判例库**（法院撤销/维持判决，双通道法律来源的通道二）——
  与"同类企业的同类风险怎么处理、要补什么资料"**不是同一个概念**，故不合并、不改名（避免概念混淆）。
- `engine/memory.query_similar_cases` 是**真实历史分析记录**的加权检索（同行业/同模式/规模相近）——
  本模块**薄转发**它，作为"同类企业"的第一来源。
- `static/cross_analysis_memory.json` 提供**同行业的真实分析次数**（可用作"样本量"声明）。

本模块新增的是"**处理结果 / 补资料经验**"这一列的**人工登记台账**：
`config/experience_cases.json`（策展，起步为空）+ `data/experience_cases.jsonl`（运行时追加）。
**起步为空是要如实呈现的事实**：没有真实闭环案例时，本模块必须说"无同类案例可参考"，
**不得用别的行业案例充数、更不得编造处理结果**。

## ★ 铁律

- 每条例的 `affects_risk_level` **恒为 False**：案例只作参考，**不改变风险等级**（闸门 + 行为测试锁死）。
- 匹配必须有**同行业或同风险**命中才返回；否则如实空。
- 取不到就给"未登记"，不猜。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
_CURATED = _ROOT / "config" / "experience_cases.json"
_LEDGER = _ROOT / "data" / "experience_cases.jsonl"
_MEMORY = _ROOT / "static" / "cross_analysis_memory.json"

#: 案例必备字段（★ 唯一权威：新增字段只加这里一处）
CASE_FIELDS: Tuple[str, ...] = (
    "case_id", "industry", "risk_types", "biz_model", "outcome", "material_experience",
)

#: 匹配权重（数据驱动：同行业 > 同风险 > 同模式）
MATCH_WEIGHTS: Dict[str, int] = {"industry": 3, "risk_type": 2, "biz_model": 2}


def load_curated() -> List[Dict[str, Any]]:
    try:
        d = json.loads(_CURATED.read_text(encoding="utf-8"))
    except Exception:
        return []
    cases = d.get("cases") if isinstance(d, dict) else d
    return [c for c in (cases or []) if isinstance(c, dict)]


def load_ledger() -> List[Dict[str, Any]]:
    if not _LEDGER.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in _LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if isinstance(o, dict):
            out.append(o)
    return out


def load_cases() -> List[Dict[str, Any]]:
    """全部案例（策展 + 运行时台账），逐条补 `affects_risk_level=False` 契约字段。"""
    out: List[Dict[str, Any]] = []
    for c in load_curated() + load_ledger():
        d = dict(c)
        d["affects_risk_level"] = False
        d["reference_only"] = True
        for f in CASE_FIELDS:
            d.setdefault(f, "" if f != "risk_types" else [])
        out.append(d)
    return out


def industry_sample_size(industry: str) -> int:
    """同行业的**真实历史分析次数**（来自跨企业记忆）；取不到返回 0（不猜）。"""
    try:
        mem = json.loads(_MEMORY.read_text(encoding="utf-8"))
    except Exception:
        return 0
    pats = mem.get("industry_patterns") or {}
    key = str(industry or "").strip()
    if not key:
        return 0
    for k, v in pats.items():
        if k and (k in key or key in k):
            try:
                return int((v or {}).get("analyses_count") or 0)
            except Exception:
                return 0
    return 0


def _norm(xs: Any) -> List[str]:
    if isinstance(xs, str):
        xs = [xs]
    return [str(x).strip() for x in (xs or []) if str(x).strip()]


def match_cases(industry: str = "", risk_types: Optional[Iterable[str]] = None,
                biz_model: str = "", limit: int = 5) -> List[Dict[str, Any]]:
    """按（同行业 / 同风险 / 同经营模式）打分配对；**无任何命中则返回空**。"""
    ind = str(industry or "").strip()
    risks = set(_norm(risk_types))
    biz = str(biz_model or "").strip()
    scored: List[Tuple[int, Dict[str, Any]]] = []
    for c in load_cases():
        s = 0
        hits: List[str] = []
        ci = str(c.get("industry") or "").strip()
        if ind and ci and (ind in ci or ci in ind):
            s += MATCH_WEIGHTS["industry"]
            hits.append("同行业")
        same_r = risks & set(_norm(c.get("risk_types")))
        if same_r:
            s += MATCH_WEIGHTS["risk_type"] * len(same_r)
            hits.append("同风险：" + "、".join(sorted(same_r)[:3]))
        cb = str(c.get("biz_model") or "").strip()
        if biz and cb and (biz in cb or cb in biz):
            s += MATCH_WEIGHTS["biz_model"]
            hits.append("同经营模式")
        if s <= 0:
            continue
        d = dict(c)
        d["match_score"] = s
        d["match_hits"] = hits
        scored.append((s, d))
    scored.sort(key=lambda t: (-t[0], str(t[1].get("case_id"))))
    return [d for _s, d in scored[:max(1, int(limit))]]


def case_reference_text(cases: List[Dict[str, Any]], industry: str = "",
                        risk_types: Optional[Iterable[str]] = None) -> str:
    """《同类案例参考》的说明句；**无命中时如实说"没有"**（不编造、不跨行业凑数）。"""
    n = industry_sample_size(industry)
    base = ("同行业历史分析样本：%d 次。" % n) if n else ""
    if not cases:
        return ("本轮**未匹配到可参考的同类案例**"
                + ("（%s）" % base if base else "")
                + "本系统的案例经验库需要由**已闭环的真实案例**人工沉淀"
                  "（处理结果与补资料经验），当前尚无登记记录，故不提供跨行业案例充数。"
                  "案例仅作参考，不影响任何风险等级的判定。")
    lines = ["本轮匹配到 %d 例可参考的同类案例（%s），仅作检查参考：" % (len(cases), base)
             if base else "本轮匹配到 %d 例可参考的同类案例，仅作检查参考：" % len(cases)]
    for c in cases[:5]:
        lines.append("「%s」行业为%s，涉%s，处理结果为%s，补资料经验为%s。"
                     % (c.get("case_id"), c.get("industry") or "未登记",
                        "、".join(_norm(c.get("risk_types"))) or "未登记",
                        c.get("outcome") or "未登记",
                        c.get("material_experience") or "未登记"))
    lines.append("以上案例不改变本企业任何风险事项的等级与结论。")
    return "".join(lines)


def render_cases_md(cases: List[Dict[str, Any]], industry: str = "",
                    risk_types: Optional[Iterable[str]] = None) -> str:
    """《同类案例参考》（可独立交付）。"""
    L = ["# 同类案例参考", "", case_reference_text(cases, industry, risk_types), ""]
    if not cases:
        return "\n".join(L)
    cols = ["案例号", "行业", "同类风险", "经营模式", "处理结果", "补资料经验", "匹配依据"]
    L += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for c in cases:
        L.append("| " + " | ".join([
            str(c.get("case_id") or "—"), str(c.get("industry") or "—"),
            "、".join(_norm(c.get("risk_types"))) or "—",
            str(c.get("biz_model") or "—"), str(c.get("outcome") or "—"),
            str(c.get("material_experience") or "—"),
            "、".join(c.get("match_hits") or []) or "—"]) + " |")
    L += ["", "> 契约：案例**只作参考**，不参与风险等级评定"
          "（`affects_risk_level=False`，由闸门与测试锁死）。", ""]
    return "\n".join(L)


def add_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """登记一条**已闭环**的真实案例（append-only 台账；缺必填字段即报错，不静默收下）。"""
    if not isinstance(case, dict):
        raise TypeError("case 必须是 dict")
    miss = [f for f in CASE_FIELDS if f not in case or case.get(f) in (None, "", [])]
    if miss:
        raise ValueError("案例缺必填字段：%s（案例经验必须可复核，不接受残缺条目）" % miss)
    rec = dict(case)
    rec["affects_risk_level"] = False
    rec.setdefault("case_id", "EXP-%04d" % (len(load_ledger()) + 1))
    _LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(_LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


__all__ = ["CASE_FIELDS", "MATCH_WEIGHTS", "load_curated", "load_ledger", "load_cases",
           "industry_sample_size", "match_cases", "case_reference_text",
           "render_cases_md", "add_case"]

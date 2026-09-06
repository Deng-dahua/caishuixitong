# -*- coding: utf-8 -*-
"""
红线判定引擎 —— 风险检查方法论的编排核心
==================================================

方法论主线（2026-09-06 确立，替代原「按行业套场景」的做法）
----------------------------------------------------------
    原始资料
      ↓ 原子观察（已有能力）
    税务红线判定 ← 行业无关：符合构成要件即触红，红线不因行业而变
      ↓
    ┌─────────────┬──────────────┬───────────────┐
   线索链        证据链          论证链
   （怎么发现的）（要什么证据）  （主张/反证/裁决）
    └─────────────┴──────────────┴───────────────┘
      ↓
    税务疑点（按红线归并输出，不再按「待核事实：XXX核验」罗列）

为什么按红线归而不是按发现罗列
--------------------------------------------------
同一条红线可能被多条发现命中（如「供应商地域分散」与「供应商集中度」
同属 RL-PTY-002）。按发现罗列会让报告变成碎片清单；按红线归并后，
一个疑点 = 一条红线 + 多条支撑线索 + 一条证据链 + 一次论证裁决。
"""

from typing import Any, Dict, List, Optional, Tuple

from engine.tax_redlines import match_redlines, get_redline, stats as redline_stats
from engine.clue_chain import build_clue_chain
from engine.evidence_chain import build_evidence_chain
from engine.argumentation import (
    build_argumentation, _VERDICT_CONFIRMED, _VERDICT_HIT_PENDING,
    _VERDICT_EXCLUDED, _VERDICT_WEAK,
)

# 裁决优先级：成立可定性 > 成立待补证 > 线索不足 > 排除
_VERDICT_RANK = {
    _VERDICT_CONFIRMED: 4, _VERDICT_HIT_PENDING: 3,
    _VERDICT_WEAK: 2, _VERDICT_EXCLUDED: 1,
}

ENGINE_VERSION = "1.0.0"


def _available_materials(engine_data: Optional[Dict],
                         material_readiness: Optional[Dict],
                         finding: Dict) -> List[str]:
    """汇总本轮已提供的资料类别"""
    mats: List[str] = []
    if isinstance(material_readiness, dict):
        for m in (material_readiness.get("provided") or []):
            if m and m not in mats:
                mats.append(str(m))
    if not mats and isinstance(engine_data, dict):
        for f in (engine_data.get("file_results") or []):
            if isinstance(f, dict):
                t = str(f.get("type") or f.get("doc_type") or "")
                if t and t not in mats:
                    mats.append(t)
    # 注意：不得把发现自身声明的独立来源当作「已提供资料」。
    # 独立来源是数据域名称（如「发票申报」「商品库存」），不是资料类别，
    # 混入后会把缺失的证据误判为已有，导致证据链闭合度虚高、错误定性。
    return mats


def _map_finding(finding: Dict) -> Optional[Dict]:
    """为单条发现匹配红线"""
    text = " ".join(str(finding.get(k) or "") for k in
                    ("type", "domain", "detail", "description", "target_fact"))
    cands = match_redlines(text, domain=finding.get("domain"), limit=3)
    return cands[0] if cands else None


def run_redline_detection(findings: List[Dict],
                          engine_data: Optional[Dict] = None,
                          material_readiness: Optional[Dict] = None,
                          pipeline_log: Optional[List] = None) -> Dict:
    """
    红线判定主入口。

    返回：
        {
          "version",
          "suspicions": [ {redline_id, redline_name, suspect, taxes, domain,
                            level, confidence, verdict, closure,
                            clue_chain, evidence_chain, argumentation,
                            supporting_findings:[...], finding_count} ],
          "confirmed": [...], "unconfirmed": [...], "excluded": [...],
          "unmapped": [...],
          "summary": {...}
        }
    """
    findings = [f for f in (findings or []) if isinstance(f, dict)]
    grouped: Dict[str, Dict] = {}
    unmapped: List[Dict] = []

    for f in findings:
        rl = _map_finding(f)
        if not rl:
            unmapped.append({
                "type": f.get("type", ""),
                "domain": f.get("domain", ""),
                "level": f.get("level", ""),
            })
            continue
        rid = rl["id"]
        mats = _available_materials(engine_data, material_readiness, f)
        clue = build_clue_chain(f, rl, engine_data)
        ev = build_evidence_chain(f, rl, mats, engine_data)
        arg = build_argumentation(f, rl, clue, ev, engine_data)
        entry = grouped.get(rid)
        if not entry:
            entry = {
                "redline_id": rid,
                "redline_name": rl.get("name", ""),
                "suspect": rl.get("suspect", ""),
                "taxes": list(rl.get("taxes") or []),
                "domain": rl.get("domain", ""),
                "legal_basis": list(rl.get("legal_basis") or []),
                "constituents": list(rl.get("constituents") or []),
                "clue_chain": clue,
                "evidence_chain": ev,
                "argumentation": arg,
                "supporting_findings": [],
                "level": f.get("level", ""),
                "confidence": arg.get("confidence", 0.0),
                "closure": ev.get("closure", 0.0),
                "verdict": arg.get("verdict", ""),
                "conclusion_grade": arg.get("conclusion_grade", "待核"),
                "redline_hit": bool(arg.get("redline_hit")),
                "remedy": ev.get("remedy", ""),
                "missing_materials": list(ev.get("missing_materials") or []),
            }
            grouped[rid] = entry
        else:
            entry["supporting_findings"].append({
                "type": f.get("type", ""),
                "domain": f.get("domain", ""),
                "terminal_signal": clue.get("terminal_signal", ""),
                "clue_nodes": clue.get("nodes", []),
                "numbers": clue.get("numbers", []),
                "samples": clue.get("samples", []),
            })
            # 归并时取更强的信号：闭合度更高者为主证据链，置信度取最高
            if ev.get("closure", 0) > entry["closure"]:
                entry["evidence_chain"] = ev
                entry["clue_chain"] = clue
                entry["closure"] = ev.get("closure", 0.0)
            # 同一条红线被多条发现命中时，取裁决层级最强的一次作为疑点结论
            if _VERDICT_RANK.get(arg.get("verdict"), 0) > _VERDICT_RANK.get(entry.get("verdict"), 0):
                entry["verdict"] = arg.get("verdict", "")
                entry["conclusion_grade"] = arg.get("conclusion_grade", "待核")
                entry["argumentation"] = arg
            entry["redline_hit"] = bool(entry.get("redline_hit") or arg.get("redline_hit"))
            if arg.get("confidence", 0) > entry["confidence"]:
                entry["confidence"] = arg.get("confidence", 0.0)
            for m in (ev.get("missing_materials") or []):
                if m not in entry["missing_materials"]:
                    entry["missing_materials"].append(m)

    # 主 findings 也要进 supporting（第一条）
    suspicions = sorted(
        grouped.values(),
        key=lambda x: (-float(x.get("confidence") or 0), -float(x.get("closure") or 0), x["redline_id"]),
    )
    for s in suspicions:
        s["finding_count"] = len(s.get("supporting_findings", [])) + 1

    confirmed = [s for s in suspicions if s.get("verdict") == _VERDICT_CONFIRMED]
    excluded = [s for s in suspicions if s.get("verdict") == _VERDICT_EXCLUDED]
    unconfirmed = [s for s in suspicions
                   if s.get("verdict") in (_VERDICT_HIT_PENDING, _VERDICT_WEAK)]

    summary = {
        "version": ENGINE_VERSION,
        "knowlege_version": redline_stats().get("version"),
        "redline_total": redline_stats().get("total"),
        "finding_total": len(findings),
        "suspicion_total": len(suspicions),
        "confirmed": len(confirmed),
        "excluded": len(excluded),
        "unconfirmed": len(unconfirmed),
        "unmapped": len(unmapped),
    }
    if pipeline_log is not None:
        pipeline_log.append(
            f"[红线判定] {len(findings)}项发现 → 归并命中{len(suspicions)}条税务红线"
            f"（可定性{len(confirmed)}/待补证{len(unconfirmed)}/排除{len(excluded)}"
            f"/未归类{len(unmapped)}），按红线组织线索链·证据链·论证链"
        )
    return {
        "version": ENGINE_VERSION,
        "suspicions": suspicions,
        "confirmed": confirmed,
        "unconfirmed": unconfirmed,
        "excluded": excluded,
        "unmapped": unmapped,
        "summary": summary,
    }


def suspicion_title(s: Dict) -> str:
    """疑点标题：红线名称（禁止再用「待核事实：XXX核验」）"""
    return f"{s.get('redline_id','')} {s.get('redline_name','')}".strip()

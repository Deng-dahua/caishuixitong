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

from engine.tax_redlines import (
    match_redlines, match_redline_grounded, get_redline, stats as redline_stats,
)
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


def _map_finding(finding: Dict, available_materials: Optional[List[str]] = None
                 ) -> Tuple[Optional[Dict], Dict]:
    """为单条发现匹配红线 → `(红线或 None, 配对说明)`。

    ★ 2026-09-25 根因修复：旧版是
        `cands = match_redlines(text, domain=..., limit=3); return cands[0] if cands else None`
      —— **只要得分为正就取第一名**。后果：一条"增值税申报进项税额与进项发票税额月度差异"
      因为文本含"增值税"、而「固定资产取得、投用与折旧不匹配」红线的 taxes 里也有"增值税"
      （得 1 分）→ 被采纳 → 报告随即用**固定资产折旧的构成要件**论证一个增值税差异，
      并写出"这些事实是从固定资产明细账、试生产记录、折旧计算表…核对出来的"。
      实测 13 条发现里 7 条配错红线。

    现分两条路径：
      ① 发现**显式声明** `redline_id`（扫描器前置认领）→ 直接采用，`mode="declared"`；
      ② 否则走 `match_redline_grounded()` —— 要求信号足够具体**且**该红线所需资料本轮有提供；
         不满足则返回 `(None, mode="unmatched")`，由调用方列为"未归入已知风险情形"，
         **绝不改挂次优红线**（宁可不归类，也不可套错构成要件）。
    """
    rid = finding.get("redline_id")
    if rid:
        rl = get_redline(rid)
        if rl:
            mats = [m for m in (rl.get("required_materials") or [])
                    if m in (available_materials or [])]
            return rl, {
                "mode": "declared",
                "score": None,
                "reasons": ["declared_by_scanner"],
                "materials": mats,
                "note": "发现自身声明了所属红线（扫描器前置认领）",
            }
    title = str(finding.get("type") or "")
    text = " ".join(str(finding.get(k) or "") for k in
                    ("type", "domain", "detail", "description", "target_fact"))
    return match_redline_grounded(title, text, available_materials,
                                  domain=finding.get("domain"))


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

    # 本轮实际已提供的资料类别对所有发现都一样 → 只算一次
    _mats_all = _available_materials(engine_data, material_readiness, {})

    for f in findings:
        rl, minfo = _map_finding(f, _mats_all)
        if not rl:
            # 未能与任何红线可靠配对：如实列为"未归入已知风险情形"，
            # **不**改挂次优红线（否则报告会用不相干的构成要件去论证本发现）
            unmapped.append({
                "type": f.get("type", ""),
                "domain": f.get("domain", ""),
                "level": f.get("level", ""),
                "detail": f.get("detail", ""),
                "match_note": minfo.get("note", ""),
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
                # ★ 2026-09-25：「待核」（有相关类别但须人工确认）必须与「缺失」分开上报，
                #   否则报告要么漏掉该确认动作，要么把企业其实已交的资料说成"缺"。
                "verify_materials": list(ev.get("verify_materials") or []),
                # ★ 2026-09-25：配对方式与依据必须随结论一起留给报告/审计核对，
                #   使"为什么这条发现被归到这条红线"可被复核。
                "match_mode": minfo.get("mode", ""),
                "match_score": minfo.get("score"),
                "match_reasons": list(minfo.get("reasons") or []),
                "match_materials": list(minfo.get("materials") or []),
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
            for m in (ev.get("verify_materials") or []):
                if m not in entry.get("verify_materials", []):
                    entry.setdefault("verify_materials", []).append(m)

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

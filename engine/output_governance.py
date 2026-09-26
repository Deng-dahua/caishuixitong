# -*- coding: utf-8 -*-
"""正式输出治理（取代原 scenario_execution 的场景驱动执行核心）。

设计原则（与红线驱动方法论一致）：
- 行业无关：不再按行业套场景契约生成"待核事实"，行业场景方法论已由
  engine/tax_redlines.py（红线驱动·线索链·证据链·论证链）替代。
- 原子计算仍是事实来源：直接调用 verified_rule_engine.run_verified_rules，
  其经过验证的原子规则在已上传数据上产生"被观察事实"。
- 正式输出封印保留：只有带 _scenario_governed 标记的发现才能进入正式报告，
  与既有注入/封印逻辑兼容（委外加工、供应链联网、客观域发现均带该标记）。
- 任何输出都不得替代行政认定：禁止自动定性、自动核定税额或移送。
"""

from __future__ import annotations

import copy
from collections import defaultdict
from datetime import datetime
from typing import Any

from engine.verified_rule_engine import VERIFIED_RULE_CATALOG, run_verified_rules


GOVERNANCE_STATUS = "output_governed"
EXECUTION_VERSION = "1.0.0"

# ══════════════════ 证据地位（evidence_tier）══════════════════
# ★ 2026-09-25 用户决策：「都要提升，一定是把所分析到的风险都要呈现在报告中！」
#   原设计把非"客观域"的 45 个分析域结论**整体隔离**，实测 86 项"算了但看不到"。
#   现改为全部纳入正式输出，但**必须可区分证据地位**，不得让读者以为
#   域分析结论与已验原子规则具有同等证据地位。
EVIDENCE_TIER_VERIFIED_RULE = "已验原子规则（可信观察）"
EVIDENCE_TIER_DOMAIN = "域分析结论（基于上传资料计算）"
EVIDENCE_TIER_NOTE = (
    "证据地位用于区分结论的取得方式，不改变其待人工复核的性质："
    "「已验原子规则」为在册已验证规则、数据谱系来自上传资料；"
    "「域分析结论」为分析域基于上传资料计算得出，尚未固化为已验证规则。"
    "两者均仅为待核事实，禁止自动定性。"
)


def _rule_index() -> dict:
    return {item["id"]: item for item in VERIFIED_RULE_CATALOG}


def _trusted_observation(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    rule_id = str(item.get("rule_id", ""))
    return (
        rule_id in _rule_index()
        and item.get("source_lineage_status") == "observed_from_uploaded_data"
        and item.get("rule_maturity") == "verified_executable_screening"
    )


def promote_domain_findings(execution: dict, domain_results, existing_fact_ids=None) -> dict:
    """把**分析域产出的风险级发现全部并入正式输出**（2026-09-25 用户决策）。

    背景：原设计只把 7 个"客观域"并入 `_scenario_execution`，其余 40+ 个域的结论
    被整体隔离（实测 86 项"算了但看不到"）—— 使用者因此长期觉得"很多风险查不出来"。
    用户决策：「都要提升，一定是把所分析到的风险都要呈现在报告中」。

    本函数是这件事的**唯一实现**（pipeline 只调用它，不在内联处另写一套）：
      · 跳过 `level` 为「信息」/空 的项（非风险，不进风险清单）；
      · 跳过已在 `execution["findings"]` 中的项（避免与客观域并入重复）；
      · 补 `scene_fact_id` / `_scenario_governed` / `evidence_tier` / `domain` / `conclusion_grade`；
      · 域结论未固化为已验证规则 → `conclusion_grade="待核"`（不得自称"已核定"）。

    返回 `{"promoted": n, "by_domain": {域: n}}`。
    """
    if not isinstance(execution, dict):
        return {"promoted": 0, "by_domain": {}}
    ids = existing_fact_ids if existing_fact_ids is not None else set()
    if not isinstance(ids, set):
        ids = set(ids)
    findings = execution.setdefault("findings", [])
    already = {id(f) for f in findings if isinstance(f, dict)}
    promoted, by_domain = 0, {}
    for dr in (domain_results or []):
        if not isinstance(dr, dict):
            continue
        dn = str(dr.get("domain") or "")
        for f in (dr.get("findings") or []):
            if not isinstance(f, dict) or id(f) in already:
                continue
            if f.get("level") in ("信息", None, ""):
                continue
            seq = 1
            fact_id = f"DOMAIN-{dn}-{seq}"
            while fact_id in ids:
                seq += 1
                fact_id = f"DOMAIN-{dn}-{seq}"
            ids.add(fact_id)
            f["scene_fact_id"] = fact_id
            f["fact_id"] = fact_id
            f["_scenario_governed"] = True
            f["_domain_analysis_finding"] = True
            f.setdefault("evidence_tier", EVIDENCE_TIER_DOMAIN)
            f.setdefault("scenario_scope", "domain_analysis_gate")
            f.setdefault("category", "域分析待核事实")
            f.setdefault("domain", dn)
            f.setdefault("conclusion_grade", "待核")
            f.setdefault("final_answer", "")
            findings.append(f)
            already.add(id(f))
            promoted += 1
            by_domain[dn] = by_domain.get(dn, 0) + 1
    if promoted:
        try:
            execution["domain_summary"] = _domain_summary(findings)
        except Exception:
            pass
    return {"promoted": promoted, "by_domain": by_domain}


def stamp_evidence_tiers(findings, default_tier: str = EVIDENCE_TIER_DOMAIN) -> int:
    """给已进入正式输出但**未标注证据地位**的发现补标注（幂等）。

    证据地位是"结论怎么来的"的标注，任何进入报告的发现都必须有，
    否则报告无法区分"已验原子规则"与"域分析结论"（用户要求全部呈现，
    但不允许混淆两者的可信度）。
    """
    n = 0
    for f in (findings or []):
        if not isinstance(f, dict):
            continue
        if not f.get("evidence_tier"):
            f["evidence_tier"] = default_tier
            n += 1
    return n


def _domain_summary(findings: list) -> list:
    grouped = defaultdict(list)
    for finding in findings:
        grouped[finding.get("domain", "待核事实")].append(finding)
    return [
        {
            "domain": domain,
            "count": len(items),
            "high": 0,
            "mid": 0,
            "status": "待人工复核",
            "findings": items,
        }
        for domain, items in sorted(grouped.items())
    ]


def run_output_governance(industry=None, file_results=None, engine_data=None) -> dict:
    engine_data = engine_data or {}
    atomic = run_verified_rules(engine_data)
    raw_observations = atomic.get("findings", [])
    observations = [copy.deepcopy(item) for item in raw_observations if _trusted_observation(item)]
    rejected = len(raw_observations) - len(observations)
    findings = []
    for item in observations:
        item = copy.deepcopy(item)
        item["_scenario_governed"] = True
        item.setdefault("scenario_scope", "common_fact_gate")
        # ★ 2026-09-25：标注**证据地位**。用户决策"分析到的风险必须全部呈现在报告中"，
        #   域分析结论也将并入正式输出；两者必须可区分，不能混淆可信度。
        item.setdefault("evidence_tier", EVIDENCE_TIER_VERIFIED_RULE)
        findings.append(item)
    return {
        "version": EXECUTION_VERSION,
        "governance_version": None,
        "executed_at": datetime.now().isoformat(),
        "governance_status": GOVERNANCE_STATUS,
        "industry_input": str(industry or ""),
        "industry_code": "",
        "industry_resolved": False,
        "status": "待人工复核",
        "decision_boundary": (
            "原子计算只形成观察事实；行业无关红线判定在 redline_detection 阶段完成。"
            "未经证据、政策时效、金额底稿和有权人员审签，不得形成正式结论。"
        ),
        "atomic_rule_version": atomic.get("version"),
        "atomic_rule_count": atomic.get("catalog_count", 0),
        "atomic_executions": copy.deepcopy(atomic.get("executions", [])),
        "trusted_observation_count": len(observations),
        "rejected_observation_count": rejected,
        "available_source_families": [],
        "observed_file_types": [],
        "source_quality_issues": [],
        "industry_scene_count": 0,
        "industry_scenes_assessed": 0,
        "industry_scenes_with_observations": 0,
        "industry_scene_findings": 0,
        "common_fact_findings": len(findings),
        "unmapped_industry_observations": [],
        "scenes": [],
        "review_plan": {},
        "findings": findings,
        "domain_summary": _domain_summary(findings),
        "report_release_allowed": False,
    }


def seal_governed_findings(execution: dict) -> list:
    if not isinstance(execution, dict) or execution.get("governance_status") != GOVERNANCE_STATUS:
        raise ValueError("缺少有效的输出治理结果")
    findings = execution.get("findings", [])
    if not isinstance(findings, list):
        raise ValueError("输出治理结果缺少规范待核事实")
    sealed = []
    identities = set()
    for item in findings:
        if not isinstance(item, dict) or item.get("_scenario_governed") is not True:
            continue
        identity = str(item.get("scene_fact_id") or item.get("fact_id") or item.get("type") or "").strip()
        if not identity or identity in identities:
            continue
        identities.add(identity)
        canonical = copy.deepcopy(item)
        if canonical.get("conclusion_grade") == "已核定":
            canonical["required_human_review"] = True
            canonical["automatic_determination_allowed"] = False
            canonical["report_release_allowed"] = True
            canonical["release_status"] = "已核定_限于所报资料勾稽_待人工确认"
        else:
            canonical["required_human_review"] = True
            canonical["automatic_determination_allowed"] = False
            canonical["report_release_allowed"] = False
            canonical["release_status"] = "草稿_待人工复核"
        sealed.append(canonical)
    # ★ 2026-09-25：**封印是报告发现的唯一产出点**（pipeline 与 main 各调用一次，
    #   且本函数内部 deepcopy 会丢弃上游对旧对象的任何修改）——因此"每条发现都必须有出口"
    #   （怎么解除 + 需补什么自证 + 终局方向）必须在这里落实，否则上游补了也会被这次
    #   重新封印覆盖掉（实测：管道里补齐 92 条，报告里 0 条生效）。
    try:
        from engine.audit_doctrine import apply_three_piece_to_all
        apply_three_piece_to_all(sealed)
    except Exception:
        pass
    return sealed

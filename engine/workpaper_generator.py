# -*- coding: utf-8 -*-
"""TaxRiskScan.Workpaper.Generator —— 工作底稿生成 Skill（编排层）。

WB-TRISK-2026-001 §5 的实现。本模块**不做判断**，只做两件事：
  1. 把 §5.4 的 15 步处理流程**声明化**（`STEPS`），每步指向唯一权威实现；
  2. 编排执行并产出**归档束**（工作底稿号 / 七类索引 / 门禁结论 / 清单）。

设计铁律
--------
* **不新造判据**：判据在 `config/quality_gates.json`，实现在 `engine/quality_gates.py`。
* **不新造编号**：编号在 `engine/numbering.py`。
* **未通过门禁 ⇒ 不得输出正式版**：`formal_output_allowed=False` 时，归档束标记为草稿/辅助结果。
* 取不到数据一律如实登记 `skipped`，**不填默认值**。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from engine import numbering as nb
from engine import quality_gates as qg
from engine.fact_store import FactStore, get_store

__all__ = [
    "SKILL_ID", "SKILL_VERSION", "STEPS", "run_workpaper", "build_archive_bundle",
    "render_manifest", "VERSION",
]

VERSION = "1.0.0"
SKILL_ID = "taxriskscan.workpaper.generator"
SKILL_VERSION = "1.0.0"

#: §5.4 处理流程（15 步）。每步 = (序号, 名称, 唯一权威实现, 产出键)
STEPS: List[Tuple[int, str, str, str]] = [
    (1, "资料接入", "engine.material_recognition / main._execute_tax_risk_analysis", "materials"),
    (2, "数据清洗", "engine.numparse / engine.fieldkit", "facts"),
    (3, "企业画像", "engine.enterprise_profile / engine.industry_resolver", "profile"),
    (4, "规则匹配", "engine.rule_gate / engine.tax_redlines", "matched_rules"),
    (5, "多源交叉比对", "engine.data_source_status / engine.two_tax_income", "cross_checks"),
    (6, "风险识别", "engine.redline_engine / engine.verified_rule_engine", "findings"),
    (7, "证据匹配", "engine.evidence_chain.build_evidence_chain", "evidence_chain"),
    (8, "闭合度计算", "engine.evidence_chain（closure）/ engine.constituent_checkpoint", "closure"),
    (9, "逻辑一致性校验", "engine.quality_gates.gate_logic_consistency", "logical_conflicts"),
    (10, "风险定级", "engine.risk_levels / engine.conclusion_grade.veto_triggers", "risk_levels"),
    (11, "结论分级", "engine.conclusion_grade（L1~L4）", "conclusion_grades"),
    (12, "底稿生成", "engine.enterprise_report.build_enterprise_readable_report", "workpaper"),
    (13, "归档规范质检", "engine.quality_gates.gate_archive_spec", "archive_gate"),
    (14, "模板整洁质检", "engine.quality_gates.gate_template_hygiene", "hygiene_gate"),
    (15, "质量门禁", "engine.quality_gates.attach_to_report（未通过不得输出正式版）", "gate_result"),
]

#: §5.3 输出清单（8 项）
OUTPUTS: List[str] = [
    "结构化工作底稿", "风险清单", "证据链闭合度报告", "逻辑一致性报告",
    "归档索引包", "整改台账", "老板摘要", "税务顾问版摘要",
]


def run_workpaper(
    report_data: Dict[str, Any],
    *,
    company_code: Any = "",
    period: Any = "",
    render_text: str = "",
    facts: Optional[FactStore] = None,
    version: int = 1,
) -> Dict[str, Any]:
    """按 §5.4 逐步骤执行并返回 Skill 运行结果（不改写业务结论）。"""
    if not isinstance(report_data, dict):
        return {"ok": False, "error": "report_data 不是 dict"}

    company_code = company_code or report_data.get("company_code") or ""
    period = period or report_data.get("inspection_period") or report_data.get("period") or ""
    svc = nb.NumberingService(company_code, period)
    store = facts or get_store(report_data)

    steps: List[Dict[str, Any]] = []
    for idx, name, impl, out_key in STEPS:
        skipped: List[str] = []
        if idx in (9, 13, 14, 15) and not report_data.get("enterprise_readable_report"):
            skipped.append("报告主体未生成，本步骤未执行")
        if idx == 15 and store is None:
            skipped.append("事实库未挂载（事实级冲突未纳入）")
        steps.append({"step": idx, "name": name, "impl": impl, "output_key": out_key,
                      "ran": not skipped, "skipped": skipped})

    gate_result = qg.run_all_gates(report_data, company_code=company_code, period=period,
                                   render_text=render_text, facts=store)
    report_data["_quality_gates_v2"] = gate_result
    report_data["formal_workpaper_allowed"] = bool(gate_result.get("formal_output_allowed"))
    if not report_data["formal_workpaper_allowed"]:
        report_data["automatic_determination_allowed"] = False

    bundle = build_archive_bundle(report_data, company_code=company_code, period=period,
                                 version=version, gate_result=gate_result)

    return {
        "ok": True,
        "skill_id": SKILL_ID,
        "skill_version": SKILL_VERSION,
        "company_code": svc.company_code,
        "period": svc.period,
        "workpaper_no": bundle["workpaper_no"],
        "steps": steps,
        "outputs": OUTPUTS,
        "gate_result": gate_result,
        "formal_output_allowed": report_data["formal_workpaper_allowed"],
        "archive_bundle": bundle,
    }


# ---------------------------------------------------------------- 归档束
_INDEX_RULE = {
    "risk": "risk", "evidence": "evidence", "gap": "gap",
    "law": "law", "attachment": "attachment", "rectify": "rectify",
}


def build_archive_bundle(
    report_data: Dict[str, Any],
    *,
    company_code: Any = "",
    period: Any = "",
    version: int = 1,
    gate_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """产出归档束：底稿号 + 七类索引 + 清单。**取不到就如实登记 missing。**"""
    svc = nb.NumberingService(company_code, period)
    items = qg.iter_items(report_data)
    store = get_store(report_data)
    missing: List[str] = []

    # 风险索引
    risk_rows: List[Dict[str, Any]] = []
    for i, it in enumerate(items, 1):
        risk_rows.append({
            "risk_no": it.get("risk_no") or svc.make("risk", i),
            "title": it.get("title"),
            "risk_level": it.get("risk_level"),
            "conclusion_grade": it.get("conclusion_grade"),
            "closure": it.get("closure"),
        })

    # 金额索引（事实库为唯一来源）
    amount_rows = store.amount_index_rows() if isinstance(store, FactStore) else []
    if not amount_rows:
        missing.append("amount: 事实库未挂载或未登记任何金额（金额索引为空）")

    indexes: Dict[str, Any] = {
        "risk": risk_rows,
        "evidence": [], "gap": [], "law": [],
        "amount": amount_rows,
        "attachment": [], "rectify": [],
    }

    # 证据索引（★ 2026-10-09 P1-5：用真实证据链元素填，取不到的字段留空不臆造）
    for it in items:
        chain = it.get("evidence_chain") if isinstance(it, dict) and isinstance(it.get("evidence_chain"), dict) else {}
        for e in (chain.get("elements") or []):
            if not isinstance(e, dict):
                continue
            indexes["evidence"].append({
                "evidence_no": e.get("evidence_no") or "",
                "risk_no": e.get("risk_no") or it.get("risk_no") or "",
                "role": e.get("role") or "",
                "name": e.get("name") or "",
                "status": e.get("status") or "",
                "source_file": e.get("source_file") or "",
                "sha256": e.get("sha256") or "",
            })
    # 附件索引（来源 = 报告已登记的「本轮收到的资料」；页码/哈希**未采集就留空**，不臆造）
    _mats = report_data.get("enterprise_readable_report", {}).get("materials") \
        if isinstance(report_data.get("enterprise_readable_report"), dict) else None
    for _m in (_mats or []):
        if not isinstance(_m, dict):
            continue
        _names = _m.get("file_names") or []
        indexes["attachment"].append({
            "attachment_no": svc.make("attachment", len(indexes["attachment"]) + 1),
            "name": _m.get("display_name") or _m.get("document_type") or "",
            "pages": "",
            "source_file": "；".join(str(x) for x in _names) if isinstance(_names, list) else str(_names or ""),
            "sha256": "",
        })
    # 整改台账索引（一项风险事项一行；动作取该项建议，取不到留空）
    for it in items:
        if not isinstance(it, dict):
            continue
        indexes["rectify"].append({
            "rectify_no": svc.make("rectify", len(indexes["rectify"]) + 1),
            "risk_no": it.get("risk_no") or "",
            "action": it.get("suggestion") or "",
            "owner": it.get("owner") or "",
            "due": it.get("due") or "",
            "deliverable": "；".join(str(x) for x in (it.get("verify_materials") or [])) if isinstance(it.get("verify_materials"), list) else "",
            "status": it.get("rectify_status") or "待整改",
        })

    # ★ 2026-10-09：缺口登记（`gap`）必须在**空判定之前**填充 —— 否则 gap 恒被误判"索引为空"，
    #   与事实矛盾（实测：gap 已填 15 行仍报"未登记"）。
    for i, it in enumerate(items, 1):
        for m in (it.get("missing_material_names") or []):
            indexes["gap"].append({
                "gap_no": svc.make("gap", len(indexes["gap"]) + 1),
                "material_name": m,
                "impact": it.get("title"),
                "remedy": it.get("remedy") or "",
                "alternative": "",
            })

    for k in ("evidence", "gap", "law", "attachment", "rectify"):
        if not indexes[k]:
            missing.append(f"{k}: 未登记（索引为空）")

    gate_result = gate_result or report_data.get("_quality_gates_v2") or {}
    formal = bool(gate_result.get("formal_output_allowed"))
    return {
        "workpaper_no": svc.workpaper_no(version),
        "company_code": svc.company_code,
        "period": svc.period,
        "edition": "正式版" if formal else "草稿（门禁未通过，不得归档为正式底稿）",
        "indexes": indexes,
        "indexes_missing": missing,
        "gate_summary": (gate_result or {}).get("summary"),
        "formal_output_allowed": formal,
        "members": [m.get("id") for m in ((_archive_spec().get("export_package") or {}).get("members") or [])],
    }


_SPEC_CACHE: Optional[Dict[str, Any]] = None


def _archive_spec() -> Dict[str, Any]:
    global _SPEC_CACHE
    if _SPEC_CACHE is None:
        _SPEC_CACHE = qg._load_archive_spec()  # 复用归档规范的唯一读取点
    return _SPEC_CACHE or {}


def render_manifest(bundle: Dict[str, Any]) -> str:
    """把归档束渲染为 `manifest.json` 文本。"""
    import json as _json
    return _json.dumps({
        "workpaper_no": bundle.get("workpaper_no"),
        "edition": bundle.get("edition"),
        "company_code": bundle.get("company_code"),
        "period": bundle.get("period"),
        "formal_output_allowed": bundle.get("formal_output_allowed"),
        "gate_summary": bundle.get("gate_summary"),
        "members": bundle.get("members"),
        "index_counts": {k: len(v) for k, v in (bundle.get("indexes") or {}).items()},
        "indexes_missing": bundle.get("indexes_missing"),
    }, ensure_ascii=False, indent=1)

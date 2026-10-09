# -*- coding: utf-8 -*-
"""资料缺失与风险分离模块（唯一权威实现）。

指令依据（阶段9 第7项 + 总原则第8条 + 禁止事项第5条）：
  「缺失资料自动归入『检查受限记录』，**不计入风险事项数**。」
  「禁止把资料缺失计入风险事项数。」

关键口径（这是原报告的硬伤之一：把缺失资料混进风险计数）：
  · `count_risks()` 只数**风险事项**（findings / confirmed_problems），资料缺失**永不计数**；
  · `separate()` 把缺口单独归入 `受限记录`，并逐条给出「待补资料 / 影响范围 / 替代程序」；
  · 业态剔除：服务型行业天然无实物货物流转 ⇒ 相关单据**不算缺失**
    （薄转发 `industry_resolver.not_required_materials`，不另造剔除表）。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


def _iter_items(report_data: Any) -> Iterable[dict]:
    """风险事项取数——**报告层优先**（薄转发 `engine.report_metrics.report_surface_items`）。

    ★ 2026-10-08 修复（真实缺陷）：原先直接取 `all_findings`，
    而那是**引擎层发现**（本样本 153 条），报告层确认事项只有 **16 项**
    （在 `enterprise_readable_report.confirmed_problems`）。
    取错口径会把 153 当风险事项数 ⇒ 与报告正文的 16 项自相矛盾。

    ★ 2026-10-09：改为**薄转发**唯一权威 —— 本模块原先自带一份"报告层优先"的解析，
      与 `report_metrics` / `report_pipeline.report_items` / `dedup_report_data` 内联实现
      **共四处**各写一套；同一概念四处维护必然漂移。口径只保留在 `report_metrics`。
    """
    from engine.report_metrics import report_surface_items   # noqa: PLC0415
    return list(report_surface_items(report_data))


def count_risks(report_data: Any) -> int:
    """风险事项数——**只数风险事项，资料缺失不计入**。"""
    return len(list(_iter_items(report_data)))


def gap_items(report_data: Any) -> List[Dict[str, Any]]:
    """从各事项的需补资料/缺口字段收集缺口（去重）。"""
    seen: Dict[str, Dict[str, Any]] = {}
    for it in _iter_items(report_data):
        src: List[str] = []
        for k in ("missing_materials", "missing_material_names", "需补资料", "gaps", "material_gaps"):
            v = it.get(k)
            if isinstance(v, list):
                src.extend(str(x) for x in v if x)
            elif isinstance(v, str) and v:
                src.append(v)
        for name in src:
            nm = name.strip()
            if not nm:
                continue
            rec = seen.setdefault(nm, {"资料名": nm, "影响的风险事项": [], "次数": 0})
            rec["次数"] += 1
            no = it.get("no") or it.get("id") or it.get("title")
            if no and no not in rec["影响的风险事项"]:
                rec["影响的风险事项"].append(str(no)[:24])
    return sorted(seen.values(), key=lambda x: -x["次数"])


def separate(report_data: Any, *, industry: str = "") -> Dict[str, Any]:
    """把资料缺失与风险事项**彻底分开**。

    返回 {风险事项数, 受限记录, 不适用资料（业态剔除）, summary}。
    """
    gaps = gap_items(report_data)
    not_required: Set[str] = set()
    note = ""
    if industry:
        try:
            from engine.industry_resolver import not_required_materials  # 薄转发
            not_required, note = not_required_materials(industry)
        except Exception as exc:  # noqa: BLE001 —— 留痕，不静默
            note = f"业态剔除不可用：{exc}"

    records: List[Dict[str, Any]] = []
    for g in gaps:
        nm = g["资料名"]
        # 业态剔除：服务型行业不适用实物货物流转单据 ⇒ 不算缺失
        if nm in not_required:
            continue
        records.append({
            "资料名": nm,
            "状态": "缺失/待补",
            "影响的风险事项": g["影响的风险事项"],
            "影响范围": "相关事项无法形成核对结论（不因此增加风险事项数）",
            "替代程序": "见 config/alternative_evidence.json",
        })

    excluded = sorted(nm for g in gaps for nm in [g["资料名"]] if nm in not_required)
    return {
        "风险事项数": count_risks(report_data),
        "受限记录": records,
        "受限记录数": len(records),
        "不适用资料（业态剔除）": excluded,
        "summary": (f"风险事项 {count_risks(report_data)} 项；检查受限记录 {len(records)} 条"
                    f"（**不计入风险事项数**）；业态剔除 {len(excluded)} 类"),
        "principle": "资料缺失归『检查受限记录』，永不计入风险事项数；业态不适用者不计缺失",
        "业态剔除说明": note,
    }

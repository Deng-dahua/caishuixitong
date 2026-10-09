# -*- coding: utf-8 -*-
"""风险-证据矩阵（唯一权威实现）——把「风险等级」与「证据强度」分离计算并分列展示。

指令依据（阶段9 第5项）：
  「风险-证据矩阵：自动计算风险等级，单独展示证据强度。」
指令阶段7：
  「风险等级 = 潜在影响 × 证据强度 × 紧迫性」「高风险但证据弱的，写『高风险（潜在影响高，证据强度弱，待核）』。」

设计要点：
  · 两个维度**独立计算、独立呈现**，不得互相顶替（原报告的病根：同一套值既表达等级又表达证据）；
  · 关键证据缺失 ⇒ 走 `conclusion_grade` 的一票否决（**薄转发**，不另造判据）；
  · 取不到证据强度 ⇒ 标『未登记』，不默认判『强』。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

#: 证据强度分档（阈值唯一权威在本表；新增档位只加一行）
STRENGTH_BANDS = (
    ("强", 0.80),   # 闭合度 ≥ 0.80
    ("中", 0.50),   # ≥ 0.50
    ("弱", 0.00),   # 其余
)
STRENGTH_UNKNOWN = "未登记"


def strength_of(closure: Optional[float]) -> str:
    """按闭合度给出证据强度分档；取不到 ⇒ 未登记（不默认判强）。"""
    if closure is None:
        return STRENGTH_UNKNOWN
    try:
        v = float(closure)
    except Exception:  # noqa: BLE001
        return STRENGTH_UNKNOWN
    for name, lo in STRENGTH_BANDS:
        if v >= lo:
            return name
    return STRENGTH_UNKNOWN


def urgency_of(missing_count: int) -> str:
    """紧迫性：待核要件数越多越紧迫（阈值唯一权威在本表）。"""
    if missing_count <= 0:
        return "低"
    if missing_count <= 2:
        return "中"
    return "高"


def build_row(item: Dict[str, Any], *, closure: Optional[float] = None) -> Dict[str, Any]:
    """构造矩阵的一行。item 至少含 no/title；closure 缺省读 item['闭合度']。"""
    cl = closure if closure is not None else item.get("闭合度")
    st = strength_of(cl)
    need = int(item.get("须核对要件") or 0)
    lvl = item.get("风险等级") or "待核验"
    # 指令要求的话术：高风险但证据弱 ⇒ 显式标注
    note = ""
    if lvl in ("高风险", "极高风险") and st in ("弱", STRENGTH_UNKNOWN):
        note = f"（潜在影响高，证据强度{st}，待核）"
    return {
        "no": item.get("no"), "事项": item.get("title"),
        "风险等级": lvl, "证据强度": st, "闭合度": cl,
        "紧迫性": urgency_of(need), "定性状态": item.get("定性状态") or _grade_cn(item.get("结论等级")),
        "话术": f"{lvl}{note}" if note else lvl,
        "否决触发": item.get("否决触发") or [],
    }


def _grade_cn(grade: Optional[str]) -> str:
    return {"L1": "风险信号", "L2": "待核事项", "L3": "已认定事实"}.get(str(grade or ""), "待核事项")


def build_matrix(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """风险-证据矩阵入口。"""
    rows = [build_row(it) for it in items or []]
    dist: Dict[str, int] = {}
    for r in rows:
        dist[r["证据强度"]] = dist.get(r["证据强度"], 0) + 1
    weak_high = [r for r in rows if r["风险等级"] in ("高风险", "极高风险")
                 and r["证据强度"] in ("弱", STRENGTH_UNKNOWN)]
    return {
        "rows": rows,
        "证据强度分布": dist,
        "风险高但证据弱": [r["no"] for r in weak_high],
        "summary": (f"矩阵 {len(rows)} 项；证据强度分布 {dist}；"
                    f"风险高但证据弱 {len(weak_high)} 项（须标『待核』）"),
        "principle": "风险等级与证据强度独立计算、分列呈现；证据缺失走 conclusion_grade 一票否决",
    }


def veto_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """对每项执行关键证据一票否决（薄转发到 conclusion_grade，不另造判据）。"""
    try:
        from engine.conclusion_grade import veto_applies  # type: ignore
    except Exception:  # noqa: BLE001 —— 取不到即如实返回空并标注
        return [{"note": "conclusion_grade.veto_applies 不可用，未执行否决"}]
    out: List[Dict[str, Any]] = []
    for it in items or []:
        try:
            hit = veto_applies(it)
            if hit:
                out.append({"no": it.get("no"), "triggers": hit})
        except Exception as exc:  # noqa: BLE001 —— 留痕，不静默
            out.append({"no": it.get("no"), "error": str(exc)})
    return out

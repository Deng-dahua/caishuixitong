# -*- coding: utf-8 -*-
"""叙事生成差异化（用户第 4 批 任务1：按税种、风险族、资料缺口、金额大小、整改优先级组织报告）。

## ⚠ 接入状态：**已研发未接入**（2026-10-16 阶段1 D-03 标注）

本模块**当前不在任何生产链路中**。实测（2026-10-16）：

| 项 | 实测值 |
|---|---|
| 生产代码引用 | **0 处**（`main.py` / `engine/enterprise_report.py` / `engine/pipeline.py` 均未 import） |
| 测试引用 | 1 处（`tests/test_batch4_skills.py`） |
| 计划接入点 | 报告事项**呈现次序**（报告链） |

**为什么不直接删**：它承载"同一批风险事项按不同维度组织呈现"的能力设计，
与 `engine/narrative_fresh.py`（措辞层）**不重叠**（见下"定位"），
删除会丢失该维度的设计意图（违反"不删除已有功能"红线）。

**为什么不算缺陷**：未接入 ≠ 有缺陷。它不参与判定、不影响任何输出，
故在《阶段2缺陷准入清单》中登记为**观察项**，不进入本轮修复范围。

**若要接入**：需经用户裁定（属"新增功能"范畴，超出"不无边界扩范围"红线），
且必须补行为断言（`engine.snapshot_invariance.verify_invariance` 四类指纹恒等）。

## 定位

已有 `engine/narrative_fresh.py` 负责**措辞**层面的新鲜感（LLM 重写 / 变体模板 / 编制标识）。
本模块负责**组织**层面：同样的 16 项事项，按不同维度给出不同的呈现顺序与组织说明。

两者**不重叠**：一个改"怎么说"，一个改"先说哪个"。

## 铁律

- **只改顺序与组织说明，绝不改任何事实、金额、等级、法律适用** ——
  由 `engine.snapshot_invariance.verify_invariance` 做行为断言（改前后四类指纹必须恒等）。
- **排序依据必须可解释**：每个维度都给出确定的排序键（不是随机、不是时间）。
  随机打乱恰是「假重新分析」的特征（见 `engine/reanalysis_guard.detect_unfounded_reorder`）。
- **默认不重排**：`by=None` ⇒ 原样返回（保证默认档与改造前一致）。
- **编号不重排**：`seq` 是对外稳定编号 + 报告内「办理顺序」会按编号交叉引用，
  重排编号会打断引用 ⇒ 排序只改**呈现次序**，不改编号。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

#: 组织维度（★ 唯一权威：新增维度只加这里一处 + `_SORT_KEYS` 一行）
ORGANIZE_BY: Tuple[str, ...] = ("tax", "risk_family", "material_gap", "amount",
                                "priority", "level")

ORGANIZE_CN: Dict[str, str] = {
    "tax": "按税种",
    "risk_family": "按风险族",
    "material_gap": "按资料缺口",
    "amount": "按金额大小",
    "priority": "按整改优先级",
    "level": "按风险等级",
}


def _report_problems(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """取报告里的事项（本模块私有；与 `snapshot_invariance._problems` 不重名以免被判同名分歧）。"""
    if not isinstance(report, dict):
        return []
    v = report.get("confirmed_problems")
    return v if isinstance(v, list) else []


def _first_tax(p: Dict[str, Any]) -> str:
    t = p.get("taxes") or []
    if isinstance(t, str):
        t = [t]
    return str(sorted(str(x) for x in t)[0]) if t else "（未标注税种）"


def _family(p: Dict[str, Any]) -> str:
    try:
        from engine.finding_families import classify_family
        r = classify_family(p)
        if isinstance(r, dict):
            return str(r.get("family") or r.get("name") or "其他")
        return str(r or "其他")
    except Exception:
        return "其他"


def _gap_count(p: Dict[str, Any]) -> int:
    miss = p.get("missing_materials") or p.get("missing_material_names") or []
    if isinstance(miss, str):
        miss = [miss]
    return -len([m for m in miss if str(m).strip()])


def _sort_amount(p: Dict[str, Any]) -> float:
    ti = p.get("tax_impact") if isinstance(p.get("tax_impact"), dict) else {}
    for v in (ti.get("total"), ti.get("basis")):
        try:
            if v is not None:
                return -float(v)
        except Exception:
            continue
    return 0.0


def _level_rank(p: Dict[str, Any]) -> int:
    try:
        from engine.risk_levels import present_order
        return int(present_order(p.get("risk_level") or p.get("level")))
    except Exception:
        return 99


def _priority(p: Dict[str, Any]) -> Tuple[int, int, float]:
    """整改优先级 = 等级序 → 缺口数 → 金额（都是"越前越紧急"的确定键）。"""
    return (_level_rank(p), _gap_count(p), _sort_amount(p))


def _view_weight(p: Dict[str, Any], orchestration: Optional[Dict[str, Any]]) -> int:
    """视角权重：本次视角顺序靠前、权重高的 → 其关联风险族的事项排前。"""
    orch = orchestration or {}
    fams = list(orch.get("risk_families") or [])
    fam = _family(p)
    try:
        from engine.risk_families import family_of
        fid = family_of(p) or ""
    except Exception:
        fid = ""
    if fid and fid in fams:
        return fams.index(fid)
    return len(fams) + (0 if fam else 1)


def _SORT_KEYS(by: str, orchestration: Optional[Dict[str, Any]]):
    if by == "tax":
        return lambda p: (_first_tax(p), _level_rank(p))
    if by == "risk_family":
        return lambda p: (_family(p), _level_rank(p))
    if by == "material_gap":
        return lambda p: (_gap_count(p), _level_rank(p))
    if by == "amount":
        return lambda p: (_sort_amount(p), _level_rank(p))
    if by == "level":
        return lambda p: (_level_rank(p), _sort_amount(p))
    # priority（默认）
    return lambda p: (_view_weight(p, orchestration),) + _priority(p)


def order_problems(report: Dict[str, Any], by: Optional[str] = None,
                   orchestration: Optional[Dict[str, Any]] = None
                   ) -> Tuple[List[Dict[str, Any]], str]:
    """按 `by` 给出事项的呈现顺序（`by=None` ⇒ 原顺序 + 「维持原顺序」说明）。"""
    probs = list(_report_problems(report))
    if not probs:
        return [], "本次无可呈现的风险事项。"
    if not by:
        return probs, "本次按引擎产出的默认顺序呈现（未声明组织维度）。"
    if by not in ORGANIZE_BY:
        raise ValueError("未知组织维度：%s（合法值 %s）" % (by, list(ORGANIZE_BY)))
    key = _SORT_KEYS(by, orchestration)
    # ★ 稳定排序 + 原序兜底：排序键相同者保持原相对次序（可复现，不受字典顺序影响）
    ordered = sorted(probs, key=lambda p: (key(p), probs.index(p)))
    note = "本次按「%s」组织呈现，共 %d 项。" % (ORGANIZE_CN.get(by, by), len(ordered))
    return ordered, note


def organize(report: Dict[str, Any], by: Optional[str] = None,
             orchestration: Optional[Dict[str, Any]] = None,
             renumber: bool = False) -> Tuple[Dict[str, Any], str]:
    """重排报告的呈现顺序。**只动 `confirmed_problems` 的顺序与组织说明**。

    `renumber=True` 时会按新顺序重编 `seq`（默认 **False**：编号是对外稳定标识，
    报告内「办理顺序」按编号交叉引用，重编会打断引用）。
    """
    if not isinstance(report, dict):
        return report, ""
    ordered, note = order_problems(report, by=by, orchestration=orchestration)
    if not ordered:
        return report, note
    new = dict(report)
    if renumber:
        fixed = []
        for i, p in enumerate(ordered, 1):
            q = dict(p)
            q.setdefault("orig_seq", p.get("seq"))
            q["seq"] = i
            fixed.append(q)
        ordered = fixed
    new["confirmed_problems"] = ordered
    new["narrative_order"] = {"by": by or "", "by_cn": ORGANIZE_CN.get(by or "", "默认顺序"),
                              "n": len(ordered), "note": note}
    return new, note


def variant_note(by: Optional[str], orchestration: Optional[Dict[str, Any]] = None) -> str:
    """给报告头/附件用的组织说明（自然句）。"""
    if not by:
        return "本次报告按引擎默认顺序呈现。"
    orch = orchestration or {}
    extra = ""
    if orch.get("views"):
        extra = "视角顺序为%s。" % "、".join(orch.get("view_names") or orch["views"])
    return "本次报告按「%s」组织呈现。%s" % (ORGANIZE_CN.get(by, by), extra)


__all__ = ["ORGANIZE_BY", "ORGANIZE_CN", "order_problems", "organize", "variant_note"]

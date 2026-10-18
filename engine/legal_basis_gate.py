# -*- coding: utf-8 -*-
"""无法规依据的风险**必须降级为线索**（GAP-19，2026-10-18）。

问题
----
实测风险详情页有近四成（19 条中 7 条）`legal_provisions_n = 0` —— 法规依据栏是空的，
但这些风险仍与"有明确法条支撑"的风险**同列同等级**呈现。读者无法分辨
"这条有法条支撑"与"这条只是系统觉得可疑"。

口径（唯一实现，读取层派生，**不改落盘的结构性等级**）
------------------------------------------------------
`annotate(finding, provisions_n)`：
  · `provisions_n > 0` ⇒ `legal_basis_status="grounded"`，不动等级；
  · `provisions_n == 0` ⇒ `legal_basis_status="none"`：
      - `conclusion_grade` 封顶为 **L2（待核线索）**（原值存入 `conclusion_grade_before`）；
      - `risk_level` 用权威 `risk_levels.cap_level` 封顶到「待核验」；
      - 加 `legal_basis_note`：「暂无法规依据，本条为线索性判断，不作定性依据」。
  · `provisions_n is None`（**取不到**）⇒ `legal_basis_status="unavailable"`，
    **不降级**（"读不到"≠"没有依据"，缺失如实）。

★ 只在**渲染/读取层**派生，源数据一字不改 —— 与「结构性等级字段永不改写」一致。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

#: 无依据时**必须降下来**的等级（这些档位都属"已认定有风险"，无法规依据不得使用）
ASSERTED_LEVELS: tuple = ("极高风险", "高风险", "中风险")

#: 无依据时的封顶等级（证据状态档；`risk_levels` 里它不进可比风险档）
CAP_TO = "待核验"

#: 无依据时的结论等级（`config/conclusion_grades.json::L2`）
GRADE_CLUE = "L2"

NOTE_NONE = "暂无法规依据：本条为线索性判断，不得作为定性依据，须补充法规依据或证据后再行研判。"
NOTE_UNAVAILABLE = "法规依据读取失败（不等于没有依据）：本条等级未作降级，须人工核对。"


def annotate(finding: Dict[str, Any], provisions_n: Optional[int]) -> Dict[str, Any]:
    """就地标注并在无依据时降级；返回同一个 dict。

    `provisions_n`：
      · `None` ⇒ 取不到（未降级，标 `unavailable`）
      · `0`    ⇒ 确认为 0 条依据（降级为线索）
      · `>0`   ⇒ 有依据
    """
    if not isinstance(finding, dict):
        return finding
    if provisions_n is None:
        finding["legal_basis_status"] = "unavailable"
        finding["legal_basis_note"] = NOTE_UNAVAILABLE
        return finding
    n = int(provisions_n)
    finding["legal_provisions_n"] = n
    if n > 0:
        finding["legal_basis_status"] = "grounded"
        return finding

    finding["legal_basis_status"] = "none"
    finding["legal_basis_note"] = NOTE_NONE
    # ── 降级：结论等级封顶为「待核线索」 ──
    old_grade = str(finding.get("conclusion_grade") or "").strip()
    if old_grade and old_grade != GRADE_CLUE:
        finding.setdefault("conclusion_grade_before", old_grade)
    if old_grade != GRADE_CLUE:
        finding["conclusion_grade"] = GRADE_CLUE
    # ── 降级：风险等级降为「待核验」 ──
    # ★ 为什么不用 `risk_levels.cap_level(old, "待核验")`：`cap_level` 的设计是
    #   「**证据状态不参与高低压制**」，所以 `cap_level("高风险","待核验")` 会**原样返回**
    #   「高风险」（实测确认）。那不是缺陷 —— 它管的是"等级不得超过其建入口那条发现"。
    #   本处是**另一条语义**：「没有法规依据 ⇒ 不得维持'已认定有风险'的档位」，
    #   必须显式降级。判据用权威词表 `ASSERTED_LEVELS`，非该三档（低风险/信息）不动
    #   （它们本来就不构成"认定"，且降到「待核验」反而会**抬高**）。
    old_level = str(finding.get("risk_level") or "").strip()
    if old_level in ASSERTED_LEVELS or not old_level:
        new_level = CAP_TO
    else:
        new_level = old_level
    if new_level != old_level:
        finding.setdefault("risk_level_before_clue", old_level)
        finding["risk_level"] = new_level
        finding["risk_level_capped_by_legal_basis"] = True
    return finding


def is_clue(finding: Dict[str, Any]) -> bool:
    """该条是否已被判为「线索」（无依据）。"""
    return str((finding or {}).get("legal_basis_status") or "") == "none"


def split_by_basis(items) -> Dict[str, Any]:
    """把一组发现按「有依据 / 无依据线索」分开（报告与列表**同一把尺**）。"""
    grounded, clues = [], []
    for f in (items or []):
        (clues if is_clue(f) else grounded).append(f)
    return {"grounded": grounded, "clues": clues,
            "grounded_n": len(grounded), "clue_n": len(clues),
            "note": ("无依据项已降级为线索，**不得**与有依据项并列作为定性结论。"
                     if clues else "本轮全部发现均有法规依据。")}


__all__ = ["annotate", "is_clue", "split_by_basis", "CAP_TO", "GRADE_CLUE",
           "NOTE_NONE", "NOTE_UNAVAILABLE"]

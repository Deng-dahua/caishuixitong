# -*- coding: utf-8 -*-
"""**风险等级**的唯一权威（等级词表 / 高低标度 / 呈现顺序 / 上限压制）（2026-10-06）。

## 为什么必须有它（用户评语 #1「事项数量和风险等级前后矛盾」）
报告不同章节曾各判一次等级，读者看到"同一事项在第 4 章是高风险、在第 7 章成了中风险"。
根因不是某处笔误，而是**等级标度多头维护**——实测同仓并存 6 张表，且彼此矛盾：

| 位置 | 信息 vs 低风险 谁更轻 |
|---|---|
| `enterprise_report::_rank`（上限压制） | 信息 **轻于** 低风险 |
| `pipeline::_sev`（合并取代表） | 信息 **重于** 低风险 |
| `enterprise_report::_rank`（主线研判，已死） | 并列 |
| `finding_families::_LV_RANK` | 只列低风险（无信息） |
| `enterprise_report::_LEVEL_RANK`（已死） | 信息 **重于** 低风险 |
| `audit_consistency`（等级不超发现） | 信息 **轻于** 低风险 |

同一句话在不同章节由不同表算出来，结论当然不一致。**收敛为一处**：

```
from engine.risk_levels import (LEGAL_LEVELS, PRESENT_ORDER, RISK_GRADES,
                               EVIDENCE_STATES, severity, present_order,
                               normalize, cap_level, is_legal)
severity("高风险")            # → 4（越高越重；未知/空 → -1）
present_order("待核验")        # → 4（越小越靠前；未知 → 99）
normalize("优惠机会")          # → "信息"（词表外归信息档，如实保留事项）
cap_level("高风险", "信息")    # → "信息"（等级不得超过其建入口那条发现）
cap_level("待核验", "信息")    # → "待核验"（证据状态不参与高低压制）
```

## 两条口径（写进数据，不写进分支）
1. **「待核验」是证据状态，不是风险高低** —— 它不进 `SEVERITY` 的可比风险档
   （见 `RISK_GRADES`），因此**不受上限压制**（`cap_level` 原样返回），
   但**参与合并取代表**（`severity` 给 2：尚未排除的疑点不应被轻项顶替）。
2. **「信息」是最轻档** —— 词表外的词（如"优惠机会"）一律归一为「信息」，
   它**不得重于**已确认的「低风险」（否则"没判出等级"的事项会顶掉真风险）。
   实测旧 `pipeline::_sev` 把它排在「低风险」之上，属本条缺陷。

新增/调整一个等级 ⇒ 只改本文件的表，不改任何逻辑分支。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

#: 合法等级词表（= 报告可出现的全体等级）。顺序为**由重到轻**的呈现语序。
LEGAL_LEVELS: Tuple[str, ...] = (
    "极高风险", "高风险", "中风险", "低风险", "待核验", "信息",
)

#: 可比高低的**风险档**（不含「待核验」——它是证据状态）。
RISK_GRADES: Tuple[str, ...] = ("极高风险", "高风险", "中风险", "低风险", "信息")

#: **证据状态**（不参与高低比较，也不受上限压制）。
EVIDENCE_STATES: Tuple[str, ...] = ("待核验",)

#: ★★ **正向（非风险）等级词表** —— 这类发现讲的是"企业享有/符合什么"，不是涉税风险。
#  唯一权威（2026-10-10 从 `redline_engine._NON_RISK_LEVELS` 上提到本模块）：
#  两处**必须同判**，否则同一概念两处口径：
#    · `redline_engine._map_finding()` —— 不得配成风险红线（否则报告出现
#      "疑点是未申报缴纳，证据却是依法免征"的自相矛盾，本项目已有此事故）；
#    · `text_guardrails.review_finding()` —— 不得被证据成熟度归一压成「待核验」
#      （否则同一行 `match_note` 说"不作为风险事项"、`level` 却说"待核验/全面复核"）。
#  新增同类**只需在此加一个词**（数据驱动，不改任何逻辑分支）。
NON_RISK_LEVELS: Tuple[str, ...] = ("优惠机会", "政策红利", "税收优惠")

#: 等级 → 轻重标度（**越大越重**）。含「待核验」以便"合并取代表"时不被轻项顶替。
SEVERITY: Dict[str, int] = {
    "极高风险": 5, "高风险": 4, "中风险": 3, "待核验": 2, "低风险": 1, "信息": 0,
}

#: 等级 → **呈现顺序**（越小越靠前）：风险由重到轻，「待核验/信息」是证据状态放最末。
#  注意：这是**顺序**不是轻重标度，与 `SEVERITY` 不同表（两者用途不同，故意分开）。
PRESENT_ORDER: Dict[str, int] = {
    "极高风险": 0, "高风险": 1, "中风险": 2, "低风险": 3, "待核验": 4, "信息": 4,
}

#: 等级 → **对外展示标签**（用户在报告里看到的写法）。
#  ★★ 2026-10-06（用户口径：报告正文不得出现"待核实/待核验"这类不确定措辞）：
#    展示时把证据状态写成「已列明」（有具体事实、只是未做风险分级）。
#  ⚠ 本表**只用于展示**：**结构化字段**（如 `risk_level`、`counts.by_level` 的**键**）
#    必须保留权威等级名 —— 项目铁律「结构性枚举字段不得被当展示文本替换」。
#    实测事故：`counts.by_level` 曾把键 `待核验` 改写成 `已列明`，导致
#    计数自检「等级「已列明」报告 2 项、实际 0 项」（键与实际值对不上，且丢失区分）。
DISPLAY_LABELS: Dict[str, str] = {
    "待核验": "已列明",
    "信息": "提示性事项",
}


def display_label(level: Any) -> str:
    """等级在**报告正文**里的展示写法（唯一权威）；未登记的原样返回。"""
    v = str(level or "").strip()
    return DISPLAY_LABELS.get(v, v)

#: 未知/空等级的标度（低于「信息」，保证它不会顶掉任何已知等级）。
_UNKNOWN_SEVERITY = -1
#: 未知等级的呈现顺序（沉到最末）。
_UNKNOWN_PRESENT = 99


def is_legal(level: Any) -> bool:
    """是否属于合法等级词表。"""
    return str(level or "").strip() in LEGAL_LEVELS


def normalize(level: Any) -> str:
    """规范到合法词表；**词表外一律归「信息」**（如实保留事项，不丢弃）。空值 → ""。

    实测病根：税收优惠分析器产出 `level="优惠机会"`（机会流词汇）被归入风险疑点章节，
    报告出现「风险等级=优惠机会」——它不是风险等级，读者无从理解。
    """
    v = str(level or "").strip()
    if v in LEGAL_LEVELS:
        return v
    return "信息" if v else ""


def severity(level: Any) -> int:
    """轻重标度（越大越重）。**未知/空 → -1**（不得顶掉已知等级）。"""
    return SEVERITY.get(str(level or "").strip(), _UNKNOWN_SEVERITY)


def is_non_risk_finding(finding: Any) -> bool:
    """**正向（非风险）发现**的唯一判据（2026-10-10）。

    两个条件，都用系统**既有**字段判定，**不针对具体税种/政策写特例**：
      ① `level ∈ NON_RISK_LEVELS`（机会流词汇）；
      ② 带正向字段 `tax_benefit`（"能省多少"）。

    调用方注意：判据本身只回答"这是不是正向机会"，**不改变**任何字段；
    需要"合法等级"时另调 `normalize()`（`优惠机会 → 信息`，最轻档）。
    """
    if not isinstance(finding, dict):
        return False
    if finding.get("tax_benefit"):
        return True
    return str(finding.get("level") or "").strip() in NON_RISK_LEVELS


def present_order(level: Any) -> int:
    """呈现顺序（越小越靠前）。未知 → 99。"""
    return PRESENT_ORDER.get(str(level or "").strip(), _UNKNOWN_PRESENT)


def cap_level(level: Any, ceiling: Any) -> Tuple[str, str]:
    """把 `level` 压到不超过 `ceiling`（`level = min(level, ceiling)`）。

    返回 `(最终等级, 被压前的等级)`；未被压时第二项为空串。

    判据（数据驱动，2026-10-03 用户复核疑点3）：**疑点等级不得超过其"建入口那条发现"的等级**。
    实测 3 例：发现级「中风险」被红线等级表升为「高风险」（RL-INC-001/002）、
    「低风险」被升为「中风险」（RL-VAT-006）——发现层自己写着"该结果只说明两个数据口径
    需要逐月对账"，疑点层却成了"高风险账外收入"。

    ★ 「待核验」等**证据状态**不参与压制（原样返回）：
      降级线索一律「待核验」，若允许它被"信息"压掉，等于把"证据不足待核"降级成"提示信息"。
    """
    _lv = str(level or "").strip()
    _cap = str(ceiling or "").strip()
    if _lv not in RISK_GRADES or _cap not in RISK_GRADES:
        return _lv, ""
    if severity(_cap) < severity(_lv):
        return _cap, _lv
    return _lv, ""


def worst(levels: Iterable[Any]) -> str:
    """取一组等级中**最重**的一个（空集合 → ""）。"""
    _best, _best_s = "", _UNKNOWN_SEVERITY - 1
    for _l in levels or []:
        _v = str(_l or "").strip()
        _s = severity(_v)
        if _s > _best_s:
            _best, _best_s = _v, _s
    return _best


def mildest(levels: Iterable[Any]) -> str:
    """取一组等级中**最轻**的一个（空集合 → ""）。"""
    _cands = [str(_l or "").strip() for _l in (levels or []) if str(_l or "").strip()]
    if not _cands:
        return ""
    return min(_cands, key=severity)


def sort_key(level: Any) -> Tuple[int, int]:
    """排序键：先按呈现顺序，再按轻重标度（同级时重者在前）。"""
    _v = str(level or "").strip()
    return (present_order(_v), -severity(_v))


def counts(levels: Iterable[Any]) -> List[Tuple[str, int]]:
    """按**合法等级的呈现顺序**统计各档项数（只返回非零档，顺序稳定）。"""
    _acc: Dict[str, int] = {}
    for _l in levels or []:
        _v = normalize(_l)
        if _v:
            _acc[_v] = _acc.get(_v, 0) + 1
    return [(_lv, _acc[_lv]) for _lv in LEGAL_LEVELS if _acc.get(_lv)]

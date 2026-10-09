"""报告级派生量**单一权威**（P0-1）。

## 为什么必须有这个模块（2026-10-08 真实产物取证）

报告首屏与摘要里的每一个计数，都是**读者会直接看到、并会据此判断报告可信度**的数字。
本项目曾用**两套集合各算一遍**：

  · 引擎层：`report_data["all_findings"]`（154 项，含未进入正文的检出明细）
      → `total_risks = 154`、`overall_level = "已核定2项/待核152项"`
  · 报告层：`enterprise_readable_report.confirmed_problems`（16 项，正文实际列出并编号的）

结果：一份报告首屏说「154 项」，正文只列 16 项，四门禁 B6 一次抓出 **11 处**声明-实际不符。
根因不是"漏改一处"，而是**同一事实有两个出处**。本模块把它收敛为**一个**。

## 唯一口径

**报告级声明一律以「报告正文条目集合」为口径** —— 读者能看见、且被编号的那个集合。
引擎层检出明细另有其用途，但**不得**冒充报告级计数（需要时可单独声明"检出明细 N 项"）。

## 唯一算术

所有等级/结论计数都在本模块实现一次；`pipeline.py` / `main.py` 的中间阶段
（此时正文尚未生成）调用同一批 helper 并**显式声明 scope**，不再各写一遍 for 循环。

## 取不到数据时不静默

`apply_report_metrics()` 在正文条目集合**缺失或为空**时**不写入**（返回 `{}`），
并把原因留在 `_report_metrics["skipped_reason"]`；绝不用 0 或旧值静默顶替。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from engine import risk_levels

#: 报告正文条目集合的路径（读者可见 + 被编号的集合）—— **唯一口径**。
SURFACE_PATH: Tuple[str, ...] = ("enterprise_readable_report", "confirmed_problems")
SURFACE_LABEL = "enterprise_readable_report.confirmed_problems"

#: 兜底路径：正文集合缺失时的降级来源（只为兼容，命中即声明 scope 不同）。
_FALLBACK_KEYS: Tuple[str, ...] = ("confirmed_problems", "findings", "all_findings")

#: 风险等级档（用于计数分档；「待核验/信息」是证据状态，不计入高/中/低）。
_RISK_BUCKETS: Tuple[Tuple[str, str], ...] = (
    ("high_risk", "高风险"), ("mid_risk", "中风险"), ("low_risk", "低风险"),
)

#: ⚠ 这是**字段值**（`conclusion_grade` 的枚举，=`verdict_mapping` 的键），
#:   **不是报告对外用词** —— 对外结论用语只有四个术语（见 `conclusion_count_labels`）。
#:   判定「是否已给最终答案」用它；**写进报告**必须用 `conclusion_count_phrase()`。
VERIFIED_WORD = "已核定"


# ── 结论成熟度摘要：**唯一产出点 + 唯一回读判据**（2026-10-09，P1-4 收尾）─────
#   事故：这句话在**四处各写一套**（`pipeline` 的 `overall_level`、本模块
#   `conclusion_summary`／`scope_note`），且用的是**裁决词**「已核定/待核」而非
#   **报告结论用语**（L3「已认定事实」/L2「待核事项」）⇒ 两个后果：
#     ① 报告首行出现用户明令禁止的裸词「待核」（D7 实测报出 1 处真缺陷）；
#     ② 与《四段式摘要》里的「已认定事实/待核事项」**同一概念两种措辞**（术语漂移）。
#   另有一个隐藏消费点：门禁 B9 用**硬写正则** `(已核定|待核)\s*(\d+)\s*项` 回读
#   —— 产出侧一改词，门禁就**静默失配**（既不报错也不校验）。故产出与回读**必须同源**。
def conclusion_count_labels() -> Tuple[str, str]:
    """(已给最终答案的标签, 待核事项的标签) —— 唯一权威 `conclusion_grade.term_authority`。"""
    try:
        from engine.conclusion_grade import term_of
        a, b = str(term_of("L3") or "").strip(), str(term_of("L2") or "").strip()
    except Exception:  # noqa: BLE001
        a = b = ""
    return (a or "已认定事实", b or "待核事项")


def conclusion_count_phrase(verified: Any, pending: Any) -> str:
    """「已认定事实 N 项／待核事项 M 项」—— **唯一产出点**（改口径只改本函数）。"""
    a, b = conclusion_count_labels()
    return "%s %d 项／%s %d 项" % (a, int(verified or 0), b, int(pending or 0))


def parse_conclusion_counts(text: Any) -> Dict[str, int]:
    """从摘要句**回读**计数（供门禁 B9）—— 与 `conclusion_count_phrase` **同源**。

    返回键：`verified` / `pending`（取不到的键不出现，由调用方如实表述"取不到"）。
    """
    a, b = conclusion_count_labels()
    out: Dict[str, int] = {}
    for lab, key in ((a, "verified"), (b, "pending")):
        m = re.search(re.escape(lab) + r"\s*(\d+)\s*项", str(text or ""))
        if m:
            out[key] = int(m.group(1))
    return out


# ---------------------------------------------------------------- 取数（唯一）
def _surface_value(report_data: Any) -> Optional[list]:
    """沿 `SURFACE_PATH` 逐层下降；任一层缺失返回 None（**不得**对同一层判两个键）。"""
    cur: Any = report_data
    for k in SURFACE_PATH:
        if not (isinstance(cur, dict) and k in cur):
            return None
        cur = cur[k]
    return cur if isinstance(cur, list) and cur else None


def report_surface_source(report_data: Any) -> str:
    """返回实际命中的取数来源标识（便于在报告里自证口径）。"""
    if isinstance(report_data, dict):
        if _surface_value(report_data) is not None:
            return SURFACE_LABEL
        for key in _FALLBACK_KEYS:
            v = report_data.get(key)
            if isinstance(v, list) and v:
                return key
    return ""


def report_surface_container(report_data: Any) -> Dict[str, Any]:
    """承载报告正文条目的**容器字典**（**唯一权威**）。

    为什么必须单独给出"容器"：报告层不只有条目列表，还有**伴随字段**必须与条目
    **写在同一层**才会被前端读到 —— `static/js/tax-doc-analysis.js:5678` 是
    `var report = r.enterprise_readable_report || {}; report.report_statement`。
    ⇒ 把 `report_statement` / `common_clauses` 写到顶层 `report_data` 等于**没写**
      （前端取的是 `r.enterprise_readable_report.report_statement`）。

    ★ 2026-10-09 实测事故：`common_clauses.hoist_common_clauses` 直接读
      `report_data["confirmed_problems"]`（顶层，实测不存在）⇒ 上提恒为 0 句、
      `report_statement` 写到了顶层 ⇒ **去重引擎接上了却什么都没做**，
      而闸门又读不到 ⇒ 双盲。
    """
    if not isinstance(report_data, dict):
        return {}
    cur: Any = report_data
    for k in SURFACE_PATH[:-1]:
        if isinstance(cur, dict) and isinstance(cur.get(k), dict):
            cur = cur[k]
        else:
            return report_data          # 无嵌套时容器即本体（兼容旧payload）
    return cur if isinstance(cur, dict) else report_data


def report_surface_items(report_data: Any) -> List[Dict[str, Any]]:
    """报告正文条目集合（推荐口径）—— **唯一权威取数入口**。

    `quality_gates.iter_items()` 与本函数必须同源：门禁判的是"读者看到的东西"，
    若门禁与产出各取一套集合，必然出现"判据 PASS 而报告照旧"的假绿。
    """
    if not isinstance(report_data, dict):
        return []
    v = _surface_value(report_data)
    if v is not None:
        return [x for x in v if isinstance(x, dict)]
    for key in _FALLBACK_KEYS:
        fv = report_data.get(key)
        if isinstance(fv, list) and fv:
            return [x for x in fv if isinstance(x, dict)]
    return []


# ---------------------------------------------------------------- 计数（唯一算术）
def normalize_item_level(item: Any) -> str:
    """把条目的风险等级归一到合法档（与 `quality_gates` 的 B 判据同口径）。"""
    from engine import conclusion_grade as cg
    raw = item.get("risk_level") if isinstance(item, dict) else item
    lv, _ = cg.normalize_level(raw)
    return lv


def count_levels(items: List[Dict[str, Any]]) -> Dict[str, int]:
    """按风险等级分档计数（唯一实现）。返回含 by_level 全表 + 三个桶 + 未分级数。"""
    by_level: Dict[str, int] = {}
    for it in items:
        lv = normalize_item_level(it)
        by_level[lv] = by_level.get(lv, 0) + 1
    out: Dict[str, Any] = {name: by_level.get(zh, 0) for name, zh in _RISK_BUCKETS}
    out["by_level"] = by_level
    out["unleveled"] = sum(
        v for k, v in by_level.items()
        if k not in ("高风险", "中风险", "低风险", "极高风险")
    )
    out["extreme_risk"] = by_level.get("极高风险", 0)
    return out


def is_verified_conclusion(item: Any) -> bool:
    """该项是否已给出最终答案（结论等级＝已核定）。"""
    return isinstance(item, dict) and str(item.get("conclusion_grade") or "") == VERIFIED_WORD


def count_conclusions(items: List[Dict[str, Any]]) -> Tuple[int, int]:
    """返回 (已核定数, 待核数)；两者之和**恒等于** len(items)。"""
    v = sum(1 for it in items if is_verified_conclusion(it))
    return v, len(items) - v


def risk_level_label(levels: Dict[str, int]) -> str:
    """报告整体风险等级标签（唯一实现）：取**已分级**条目中最重的一档。

    为什么必须与 `overall_level` 分开：`overall_level` 曾是"结论成熟度摘要"
    （已核定X项/待核Y项），却被前端当**风险等级标签**渲染 —— 两种语义挤一个字段。
    """
    present = []
    for name, _zh in _RISK_BUCKETS:
        if levels.get(name):
            present.append({"high_risk": "高风险", "mid_risk": "中风险", "low_risk": "低风险"}[name])
    if levels.get("extreme_risk"):
        present.append("极高风险")
    if not present:
        return "未分级"
    return risk_levels.worst(present)


# ---------------------------------------------------------------- 计算 / 写回
def compute_report_metrics(report_data: Any) -> Dict[str, Any]:
    """计算报告级派生量（**唯一计算入口**，不写回）。"""
    items = report_surface_items(report_data)
    if not items:
        return {
            "ok": False,
            "scope": "",
            "total_risks": 0,
            "skipped_reason": "取不到报告正文条目集合（正文尚未生成或为空）——不写入，不用 0 顶替",
        }
    levels = count_levels(items)
    verified, pending = count_conclusions(items)
    return {
        "ok": True,
        "scope": report_surface_source(report_data),
        "total_risks": len(items),
        "high_risk": levels["high_risk"],
        "mid_risk": levels["mid_risk"],
        "low_risk": levels["low_risk"],
        "unleveled": levels["unleveled"],
        "extreme_risk": levels["extreme_risk"],
        "by_level": levels["by_level"],
        "verified_count": verified,
        "pending_count": pending,
        "conclusion_summary": conclusion_count_phrase(verified, pending),
        "risk_level_label": risk_level_label(levels),
    }


def apply_report_metrics(report_data: Any, *, force: bool = False) -> Dict[str, Any]:
    """把报告级派生量定稿写回 `report_data`（**唯一写入入口**，幂等）。

    取不到正文集合 ⇒ 不写回（`force=True` 时允许写 0，仅供显式空报告场景）。
    """
    m = compute_report_metrics(report_data)
    if not m.get("ok") and not force:
        if isinstance(report_data, dict):
            report_data["_report_metrics"] = m          # 留痕：为什么这次没定稿
        return m
    if not isinstance(report_data, dict):
        return m
    report_data["total_risks"] = m["total_risks"]
    report_data["high_risk"] = m["high_risk"]
    report_data["mid_risk"] = m["mid_risk"]
    report_data["low_risk"] = m["low_risk"]
    report_data["verified_count"] = m["verified_count"]
    report_data["pending_count"] = m["pending_count"]
    # 兼容字段：`overall_level` 语义＝**结论成熟度摘要**（不是风险等级）。
    report_data["overall_level"] = m["conclusion_summary"]
    # ★ 新增：真正的风险等级标签（前端此前误把 overall_level 当等级用）。
    report_data["risk_level_label"] = m["risk_level_label"]
    report_data["_report_metrics"] = m
    return m


def scope_note(report_data: Any) -> str:
    """一句话说明"报告级计数覆盖什么"（供报告自证口径）。取不到则如实说取不到。"""
    m = compute_report_metrics(report_data)
    if not m.get("ok"):
        return "报告级计数口径：未能确定（正文条目集合缺失）——本轮不给出合计。"
    _a, _b = conclusion_count_labels()
    return ("报告级计数口径：以报告正文列出并编号的风险事项为准，共 %d 项"
            "（高 %d／中 %d／低 %d；未分级 %d）；其中%s %d 项、%s %d 项。"
            % (m["total_risks"], m["high_risk"], m["mid_risk"], m["low_risk"],
               m["unleveled"], _a, m["verified_count"], _b, m["pending_count"]))


# ---------------------------------------------------------------- 多口径集合解析
#: 「逐项解除与自证台账」的取数范围（与报告正文**不同**的一个更大集合，
#:  必须由台账**自己声明**，否则门禁只能拿它跟报告正文比 —— 必然假红）。
LEDGER_SCOPE = "all_findings"

_SCOPE_ALIASES = {
    "report_surface": SURFACE_LABEL,
    "confirmed_problems": SURFACE_LABEL,
    "all_findings": "all_findings",
    "findings": "findings",
}


def scope_items(report_data: Any, scope: str) -> List[Dict[str, Any]]:
    """按**已声明**的 scope 取集合（唯一解析入口）。未知 scope ⇒ 空列表（不猜）。"""
    if not isinstance(report_data, dict):
        return []
    key = _SCOPE_ALIASES.get(str(scope or "").strip(), "")
    if not key:
        return []
    if key == SURFACE_LABEL:
        return report_surface_items(report_data)
    v = report_data.get(key)
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def ledger_counts(items: List[Dict[str, Any]]) -> Dict[str, int]:
    """「逐项解除与自证台账」的**可复算**计数（唯一实现）。

    `engine/enterprise_report._build_resolution_ledger` 与本函数必须同源 ——
    台账写数、门禁验数若各写一遍算法，就是又一处多头维护。
    （`total` 不在此列：它是台账治理**聚合后**的行数，须由台账自行声明并单独校验行数与
      `rows` 长度一致，不能拿聚合前的集合长度去比。）
    """
    from engine.audit_doctrine import (
        TERMINAL_IRONCLAD, TERMINAL_PENDING, TERMINAL_SELF_PROOF,
        normalize_terminal_state,
    )
    c = {"ironclad": 0, "self_provable": 0, "pending": 0,
         "with_resolve": 0, "with_self_proof": 0}
    for f in items:
        st = normalize_terminal_state(f.get("terminal_state"))
        if st == TERMINAL_IRONCLAD:
            c["ironclad"] += 1
        elif st == TERMINAL_SELF_PROOF:
            c["self_provable"] += 1
        elif st == TERMINAL_PENDING:
            c["pending"] += 1
        if f.get("resolve_steps"):
            c["with_resolve"] += 1
        if f.get("self_proof_materials"):
            c["with_self_proof"] += 1
    return c


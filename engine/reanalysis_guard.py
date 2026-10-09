# -*- coding: utf-8 -*-
"""假重新分析检测（用户第 4 批 任务1：四类「假重新分析」）。

## 用户列的四种表现

1. **报告日期变但内容完全一致**；
2. **无依据随机打乱顺序**；
3. **同样事实结论随意变化**；
4. **事项数量异常减少或增加**。

## ★ 第 1 条必须先分清两种"一模一样"，否则会把正确行为判成缺陷

- 「**确定性一致**」：引擎真的重跑了（会话轨迹有执行证据），同一快照 ⇒ 结果必然一致。
  这是**正确**的（税务复算确定性不可破坏）。用户最初的疑问「为什么报告和之前一模一样」
  的真实答案就在这里：**不是没重分析，而是同快照下本就该一样**；缺的是"看得出重算过"的证据。
  ⇒ 本检测器对此报 `INFO`，并要求报告头给出**本次会话信息**（重算证据）。
- 「**缓存式一致**」：没有重跑，直接把上次结果返回（会话轨迹为空/标记 cached）。
  ⇒ 这才是**真缺陷**，报 `ERROR`。

## 判据全部可机检、可反向验证

| 检测器 | 触发条件 |
|---|---|
| `detect_date_only_change` | 快照版本相同 且 内容签名相同 且 会话/时间不同 且 **无执行证据** ⇒ ERROR；有执行证据 ⇒ INFO |
| `detect_unfounded_reorder` | 事项顺序变了，而两次会话的**编排声明**（视角顺序/组织维度）完全相同 ⇒ ERROR |
| `detect_unfounded_conclusion_change` | 快照相同，但事实/计算/法律指纹变了（⇒ 更严重）或**等级变了而事实没变** ⇒ ERROR |
| `detect_abnormal_count_change` | 事项数变化超阈值；**快照未变** ⇒ ERROR；快照变了 ⇒ INFO（有新资料） |

## 铁律

- 检测器**只报不改**（不改顺序、不改等级）——修复必须由人决定。
- 每条 issue 必须带 `code`（数据驱动表 `FAKE_PATTERNS`）、`level`、`detail`（含"看到了什么"）。
- **无上次会话 ⇒ 全部检测器跳过**并如实说明（不得对第一次分析报"假分析"）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

#: 假重新分析模式表（★ 唯一权威：新增一类只加一行）
#:   key   = 检测码
#:   value = (中文名, 怎么判出来的, 默认级别)
FAKE_PATTERNS: Dict[str, Tuple[str, str, str]] = {
    "date_only_change": (
        "只换日期、内容不变",
        "数据快照版本相同 + 内容签名相同 + 会话不同，且本次**没有执行证据**（轨迹为空/标记缓存）",
        "ERROR",
    ),
    "deterministic_identical": (
        "同快照内容一致（确定性重算，非缺陷）",
        "数据快照版本相同 + 内容签名相同，但本次**有执行证据**",
        "INFO",
    ),
    "unfounded_reorder": (
        "无依据随机打乱顺序",
        "事项呈现顺序变化，而两次会话的编排声明（视角顺序/组织维度）完全一致",
        "ERROR",
    ),
    "unfounded_conclusion_change": (
        "同样事实结论随意变化",
        "快照相同，却出现事实/计算/法律指纹变化，或事实未变而风险等级变化",
        "ERROR",
    ),
    "abnormal_count_change": (
        "事项数量异常增减",
        "事项数变化幅度超过阈值，且数据快照未发生变化（无新资料可解释）",
        "ERROR",
    ),
}

#: 事项数变化超过该比例，且快照未变 ⇒ 视为异常（可用 `count_tolerance` 覆盖）
ABNORMAL_COUNT_RATIO = 0.25

#: "本次有执行证据"的判据字段（会话轨迹里出现任一步骤即算重算过）
_EXEC_EVIDENCE_KEYS = ("trace", "execution_evidence", "pipeline_log")


# ★ 事项取数**唯一权威**（薄转发；不在本模块重复定义私有实现，避免同名分歧）
from engine.snapshot_invariance import problems_of as _problems


def _order(obj: Any) -> List[str]:
    from engine.snapshot_invariance import problem_key
    return [problem_key(p) for p in _problems(obj)]


def _snap(session: Optional[Dict[str, Any]]) -> str:
    return str(((session or {}).get("snapshot") or {}).get("version") or "")


def _has_exec_evidence(session: Optional[Dict[str, Any]]) -> bool:
    """本次是否**确实重算过**（而不是把上次结果原样返回）。"""
    s = session or {}
    for k in _EXEC_EVIDENCE_KEYS:
        v = s.get(k)
        if isinstance(v, (list, dict, str)) and len(v) > 0:
            return True
    if s.get("cached") is True:
        return False
    return False


def _basis_of(session: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """本次会话的**编排声明**（顺序变化必须有依据，依据就是它）。"""
    orch = (session or {}).get("orchestration") or {}
    return {
        "views": list(orch.get("views") or []),
        "narrative_by": str(((session or {}).get("narrative_order") or {}).get("by")
                            or (session or {}).get("narrative_by") or ""),
    }


def _issue(code: str, detail: str, level: Optional[str] = None) -> Dict[str, str]:
    name, judge, lv = FAKE_PATTERNS.get(code, (code, "", "WARN"))
    return {"code": code, "name": name, "level": level or lv,
            "judge": judge, "detail": detail}


# ── 四个检测器 ────────────────────────────────────────────────────────────────

def detect_date_only_change(prev: Any, curr: Any,
                            prev_session: Optional[Dict[str, Any]] = None,
                            curr_session: Optional[Dict[str, Any]] = None,
                            prev_signature: Optional[str] = None,
                            curr_signature: Optional[str] = None
                            ) -> List[Dict[str, str]]:
    """`prev_signature`/`curr_signature` 可显式传入：上一会话只存了**摘要**时，
    内容签名从会话里直接取（摘要不含全量叙述，无法重算签名）。"""
    from engine.snapshot_invariance import content_signature
    if not isinstance(prev, dict) or not isinstance(curr, dict):
        return []
    if _snap(prev_session) and _snap(curr_session) and _snap(prev_session) != _snap(curr_session):
        return []                       # 快照变了 ⇒ 内容变化是应有之义
    ps = prev_signature
    if not ps:
        ps = ((prev_session or {}).get("report_digest") or {}).get("content_signature") \
            or (prev_session or {}).get("content_signature")
    cs = curr_signature or content_signature(curr)
    if not ps:
        ps = content_signature(prev)
    if ps != cs:
        return []
    if _has_exec_evidence(curr_session):
        return [_issue("deterministic_identical",
                       "本次与上次内容一致，但会话轨迹显示引擎确实重算过（同快照的确定性结果），"
                       "不属「假重新分析」；报告头已标注本次会话信息以便区分。")]
    return [_issue("date_only_change",
                   "数据快照版本未变（%s）、报告内容签名完全一致，而本次会话**没有重算痕迹**"
                   "（轨迹为空或标记缓存）⇒ 疑似把上次结果换了个日期返回。"
                   % (_snap(curr_session) or "未提供快照版本"))]


def detect_unfounded_reorder(prev: Any, curr: Any,
                             prev_session: Optional[Dict[str, Any]] = None,
                             curr_session: Optional[Dict[str, Any]] = None
                             ) -> List[Dict[str, str]]:
    op, oc = _order(prev), _order(curr)
    if not op or not oc or set(op) != set(oc):
        return []                       # 事项集合本身变了 ⇒ 由数量检测器处理
    if op == oc:
        return []
    bp, bc = _basis_of(prev_session), _basis_of(curr_session)
    if bp != bc:
        return []                       # 编排声明变了 ⇒ 顺序变化有依据
    moved = [k for k, v in zip(oc, op) if k != v][:3]
    return [_issue("unfounded_reorder",
                   "两次会话的编排声明（视角顺序/组织维度）完全相同，事项顺序却发生变化"
                   "（如 %s）⇒ 顺序改变缺少依据。" % "；".join(str(x)[:24] for x in moved))]


def detect_unfounded_conclusion_change(prev: Any, curr: Any,
                                       prev_session: Optional[Dict[str, Any]] = None,
                                       curr_session: Optional[Dict[str, Any]] = None
                                       ) -> List[Dict[str, str]]:
    from engine.snapshot_invariance import diff_rows
    if not isinstance(prev, dict) or not isinstance(curr, dict):
        return []
    if _snap(prev_session) and _snap(curr_session) and _snap(prev_session) != _snap(curr_session):
        return []                       # 快照变了 ⇒ 事实/计算变化有解释
    out: List[Dict[str, str]] = []
    for kind, cn in (("facts", "底层事实"), ("calc", "计算结果"), ("legal", "法律适用")):
        d = diff_rows(prev, curr, kind)
        if d:
            out.append(_issue("unfounded_conclusion_change",
                              "数据快照未变，但%s发生变化（%d 处，例：%s）"
                              % (cn, len(d), d[0][:120])))
    ld = diff_rows(prev, curr, "level")
    if ld:
        from engine.snapshot_invariance import diff_rows as _dr
        fact_same = not any(_dr(prev, curr, k) for k in ("facts", "calc", "legal"))
        out.append(_issue("unfounded_conclusion_change",
                          "数据快照未变，风险等级发生变化（%d 处，例：%s）%s"
                          % (len(ld), ld[0][:120],
                             "；事实未变而等级变了，属「结论随意变化」" if fact_same else "")))
    return out


def detect_abnormal_count_change(prev: Any, curr: Any,
                                 prev_session: Optional[Dict[str, Any]] = None,
                                 curr_session: Optional[Dict[str, Any]] = None,
                                 tolerance: float = ABNORMAL_COUNT_RATIO
                                 ) -> List[Dict[str, str]]:
    np_, nc = len(_problems(prev)), len(_problems(curr))
    if not np_:
        return []
    ratio = abs(nc - np_) / float(np_)
    if ratio <= tolerance:
        return []
    snap_changed = bool(_snap(prev_session) and _snap(curr_session)
                        and _snap(prev_session) != _snap(curr_session))
    detail = ("风险事项数由 %d 项变为 %d 项（变化 %.1f%%，阈值 %.0f%%）"
              % (np_, nc, ratio * 100, tolerance * 100))
    if snap_changed:
        return [_issue("abnormal_count_change",
                       detail + "；数据快照已变化（有新资料），数量变化**有解释**，仅作提示。",
                       level="INFO")]
    if not _has_exec_evidence(curr_session):
        return [_issue("abnormal_count_change",
                       detail + "；数据快照未变且本次无重算痕迹 ⇒ 疑似可疑增减。")]
    return [_issue("abnormal_count_change",
                   detail + "；数据快照未变而数量变化超过阈值，须人工确认"
                            "（同族合并/去重规则变化也会造成，但必须留下依据）。")]


def audit_reanalysis(prev: Any, curr: Any,
                     prev_session: Optional[Dict[str, Any]] = None,
                     curr_session: Optional[Dict[str, Any]] = None,
                     tolerance: float = ABNORMAL_COUNT_RATIO,
                     prev_signature: Optional[str] = None,
                     curr_signature: Optional[str] = None) -> Dict[str, Any]:
    """跑全部检测器。返回 `{ok, issues, checked, note}`。

    `ok=False` 仅当存在 `level=ERROR` 的 issue（INFO 表示"已核实、属正常"）。
    """
    if not isinstance(prev, dict) or not _problems(prev):
        return {"ok": True, "issues": [], "checked": list(FAKE_PATTERNS),
                "note": "尚无上一次分析可比对，本轮不做假重新分析检测（如实说明，不臆断）。"}
    issues: List[Dict[str, str]] = []
    issues += detect_date_only_change(prev, curr, prev_session, curr_session,
                                      prev_signature, curr_signature)
    issues += detect_unfounded_reorder(prev, curr, prev_session, curr_session)
    issues += detect_unfounded_conclusion_change(prev, curr, prev_session, curr_session)
    issues += detect_abnormal_count_change(prev, curr, prev_session, curr_session, tolerance)
    errs = [i for i in issues if i.get("level") == "ERROR"]
    return {
        "ok": not errs,
        "issues": issues,
        "checked": list(FAKE_PATTERNS),
        "note": ("检出 %d 项须人工确认（ERROR）、%d 项已核实为正常（INFO）。"
                 % (len(errs), len(issues) - len(errs))) if issues
                else "四项检测均通过：日期、顺序、结论、数量均未见异常。",
    }


__all__ = ["FAKE_PATTERNS", "ABNORMAL_COUNT_RATIO",
           "detect_date_only_change", "detect_unfounded_reorder",
           "detect_unfounded_conclusion_change", "detect_abnormal_count_change",
           "audit_reanalysis"]

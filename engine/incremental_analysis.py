# -*- coding: utf-8 -*-
"""增量分析 —— 《与上次分析对比表》（用户第 4 批 任务1 验收标准 2）。

## 口径

对比**上一次会话**与**本次会话**：

| 类别 | 判据 |
|---|---|
| 已消除 | 上次在、本次不在（**且不是同族合并吃掉**——同族合并对同一快照是稳定行为，不会造成假消除） |
| 已降级 | 两次都在，风险等级**降低**（比较用 `engine.risk_levels.severity`，唯一权威） |
| 已升级 | 两次都在，风险等级**升高** |
| 新增 | 本次在、上次不在 |
| 仍待核实 | 两次都在且等级为「待核验」（证据状态，不是"低风险"） |
| 金额变化 | 两次都在但锚定金额或敞口变了（**必须单独列**，不能混进"仍待核实"） |

## 铁律

- **匹配键唯一**：`snapshot_invariance.problem_key`（跨会话稳定；刻意不用 `trace_id`）。
- **无上次分析 ⇒ 如实标"首次分析"**，不虚构对比结论、不把"全部新增"当作"新增风险"。
- **同名同等级不得因措辞变化被判成"变了"**：等级比较只看等级序数，不看文案。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ★ 事项取数**唯一权威**（薄转发；不在本模块重复定义私有实现，避免同名分歧）
from engine.snapshot_invariance import problems_of as _problems

_ROOT = Path(__file__).resolve().parent.parent

#: 对比分类（★ 唯一权威：新增一类只加这里一处 + `render_comparison_md` 一行）
DIFF_CATEGORIES: Tuple[str, ...] = (
    "eliminated", "downgraded", "upgraded", "added", "still_pending",
    "amount_changed", "unchanged",
)

_CATEGORY_CN: Dict[str, str] = {
    "eliminated": "已消除",
    "downgraded": "已降级",
    "upgraded": "已升级",
    "added": "新增",
    "still_pending": "仍待核实",
    "amount_changed": "金额变化",
    "unchanged": "无变化",
}


# ★ `_problems` 不再在本模块重复定义：一律薄转发到唯一权威
#   `engine.snapshot_invariance._problems`（同名重复定义会被闸门判为"跨模块真实分歧"）。


def _key(p: Dict[str, Any]) -> str:
    from engine.snapshot_invariance import problem_key
    return problem_key(p)


def _level(p: Dict[str, Any]) -> str:
    return str(p.get("risk_level") or p.get("level") or "").strip()


def _rank(level: str) -> int:
    """等级序数（**唯一权威** `engine.risk_levels.severity`；未知档返回最低，不抬高）。"""
    try:
        from engine.risk_levels import severity
        return int(severity(level))
    except Exception:
        return -1


def _amount_pair(p: Dict[str, Any]) -> Tuple[Any, Any]:
    ti = p.get("tax_impact") if isinstance(p.get("tax_impact"), dict) else {}
    return ti.get("basis"), ti.get("total")


def diff_reports(prev: Optional[Dict[str, Any]], curr: Dict[str, Any],
                 prev_session: Optional[Dict[str, Any]] = None,
                 curr_session: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """对比两次分析的风险事项。返回 `{first_run, categories, table, summary_line}`。"""
    cur_probs = _problems(curr)
    if not prev or not _problems(prev):
        return {
            "first_run": True,
            "categories": {k: [] for k in DIFF_CATEGORIES},
            "table": {"columns": ["事项", "风险等级"], "rows": [
                [p.get("title"), _level(p)] for p in cur_probs]},
            "counts": {k: 0 for k in DIFF_CATEGORIES},
            "summary_line": ("本次为**首次可比分析**（尚无上一次会话），因此不生成"
                             "「新增/消除」结论；下表仅列本次事项，供建立基线。"),
            "prev_session_id": None,
            "curr_session_id": (curr_session or {}).get("session_id"),
        }
    before = {_key(p): p for p in _problems(prev)}
    after = {_key(p): p for p in cur_probs}
    cats: Dict[str, List[Dict[str, Any]]] = {k: [] for k in DIFF_CATEGORIES}
    for k in sorted(set(before) | set(after)):
        b, a = before.get(k), after.get(k)
        if b is not None and a is None:
            cats["eliminated"].append({"key": k, "title": b.get("title"),
                                       "prev_level": _level(b), "curr_level": None})
            continue
        if a is not None and b is None:
            cats["added"].append({"key": k, "title": a.get("title"),
                                  "prev_level": None, "curr_level": _level(a)})
            continue
        lb, la = _level(b), _level(a)
        rb, ra = _rank(lb), _rank(la)
        item = {"key": k, "title": a.get("title") or b.get("title"),
                "prev_level": lb, "curr_level": la,
                "prev_amount": _amount_pair(b)[1], "curr_amount": _amount_pair(a)[1],
                "changed": ""}
        bb, ba = _amount_pair(b)[0], _amount_pair(a)[0]
        if bb != ba or _amount_pair(b)[1] != _amount_pair(a)[1]:
            item["changed"] = "金额"
            cats["amount_changed"].append(dict(item))
        if ra > rb:
            item["changed"] = (item["changed"] + "、等级").strip("、")
            cats["upgraded"].append(dict(item))
        elif ra < rb:
            item["changed"] = (item["changed"] + "、等级").strip("、")
            cats["downgraded"].append(dict(item))
        elif la == "待核验":
            cats["still_pending"].append(dict(item))
        elif not item["changed"]:
            cats["unchanged"].append(dict(item))
        else:
            # 金额变了但等级没变：已计入 amount_changed，不再重复计入 unchanged
            pass
    counts = {k: len(v) for k, v in cats.items()}
    parts = ["%s %d 项" % (_CATEGORY_CN[k], counts[k])
             for k in ("eliminated", "downgraded", "upgraded", "added", "still_pending")
             if counts[k]]
    summary = ("与上次分析（%s）相比：" % ((prev_session or {}).get("session_id") or "上一会话")
               + ("、".join(parts) if parts else "各项无变化")
               + ("；另有 %d 项金额发生变化。" % counts["amount_changed"]
                  if counts["amount_changed"] else "。"))
    return {"first_run": False, "categories": cats, "counts": counts,
            "summary_line": summary,
            "prev_session_id": (prev_session or {}).get("session_id"),
            "curr_session_id": (curr_session or {}).get("session_id")}


def comparison_table(diff: Dict[str, Any]) -> Dict[str, Any]:
    """《与上次分析对比表》的结构化形态（列名即口径声明）。"""
    cols = ["对比结论", "事项", "上次风险等级", "本次风险等级", "上次敞口(元)", "本次敞口(元)"]
    rows: List[List[Any]] = []
    cats = diff.get("categories") or {}
    for k in ("eliminated", "downgraded", "upgraded", "added", "still_pending",
              "amount_changed"):
        for it in (cats.get(k) or []):
            rows.append([_CATEGORY_CN[k], it.get("title"), it.get("prev_level") or "—",
                         it.get("curr_level") or "—", it.get("prev_amount"),
                         it.get("curr_amount")])
    return {"columns": cols, "rows": rows,
            "scope_note": ("共登记 %d 项对比结论；其中「仍待核实」指两次分析均为证据不足状态，"
                           "不等于低风险；「金额变化」单列，不并入等级变化。"
                           % len(rows))}


def render_comparison_md(diff: Dict[str, Any], curr_session: Optional[Dict[str, Any]] = None,
                         prev_session: Optional[Dict[str, Any]] = None) -> str:
    """渲染《与上次分析对比表》为 Markdown（可独立交付）。"""
    L = ["# 与上次分析对比表", ""]
    if diff.get("first_run"):
        L += ["> **首次可比分析**：尚无上一次会话，不生成「新增/消除」结论。", ""]
    else:
        L += ["对比基准会话：%s；本次会话：%s。"
              % (diff.get("prev_session_id") or "—", diff.get("curr_session_id") or "—"), ""]
    L += [diff.get("summary_line") or "", ""]
    t = comparison_table(diff)
    if not t["rows"]:
        L += ["无可对比事项。", ""]
        return "\n".join(L)
    L += ["| " + " | ".join(t["columns"]) + " |",
          "|" + "---|" * len(t["columns"])]
    for r in t["rows"]:
        L.append("| " + " | ".join("—" if x in (None, "") else str(x) for x in r) + " |")
    L += ["", t["scope_note"], ""]
    return "\n".join(L)


def run_incremental(company_id: Any, curr_report: Dict[str, Any],
                    curr_session: Dict[str, Any],
                    prev_report: Optional[Dict[str, Any]] = None,
                    prev_session: Optional[Dict[str, Any]] = None,
                    out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """完整跑一次增量分析并落盘《与上次分析对比表》。"""
    from engine.analysis_session import previous_session as _prev_sess
    ps = prev_session if prev_session is not None else _prev_sess(company_id, curr_session)
    diff = diff_reports(prev_report, curr_report, ps, curr_session)
    md = render_comparison_md(diff, curr_session, ps)
    d = Path(out_dir) if out_dir else (
        _ROOT / "data" / "analysis_sessions" / str(company_id or "0"))
    d.mkdir(parents=True, exist_ok=True)
    p = d / "与上次分析对比表.md"
    p.write_text(md, encoding="utf-8")
    diff["path"] = str(p)
    diff["markdown"] = md
    return diff


__all__ = ["DIFF_CATEGORIES", "diff_reports", "comparison_table",
           "render_comparison_md", "run_incremental"]

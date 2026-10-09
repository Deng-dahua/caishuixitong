# -*- coding: utf-8 -*-
"""分析会话（Analysis Session）—— 用户第 4 批 任务1 的承载体。

## 为什么要有"会话"

改造前的"一键分析"只留一个报告缓存，**没有"这次分析是谁、用什么配置、基于哪份快照"
的可追溯记录**。后果：① 用户看到的报告换了措辞却查不出"到底重算了什么"；
② 「假重新分析」（只换日期、内容一模一样）无法被机器识别；③ 无法做增量对比。

本模块把每次分析提升为一个**有身份、有配置、有快照、有轨迹的会话**：

| 会话要素（任务原文） | 本模块落点 |
|---|---|
| 会话 ID | `session_id`（内容派生：快照指纹 + 配置 + Skill 版本 ⇒ **同样输入得同样 ID**） |
| 分析时间 | `analyzed_at` |
| 启用的 Skill 清单及版本 | `skills: [{id, name, version}]`，**版本取自 `engine.skill_registry`（唯一权威）** |
| 分析参数（行业/税种/检查重点/阈值/重要性水平） | `params` |
| 数据快照版本 | `snapshot: {version, files}` |
| 分析轨迹 | `trace: [{step, detail, ms}]` |

## 铁律

- **会话 ID 由内容派生，不含随机数/当前时间**：同一快照 + 同一配置 ⇒ 同一 ID
  （这样"换个日期重跑"无法伪装成"新会话"）。
- **Skill 版本只有一处权威**（`config/skill_specs.json`）：本模块**不另写一份版本号**。
- **视角轮换是确定性的**（接上次顺序做轮转），**不是随机打乱** ——
  随机打乱正是「假重新分析」的特征（见 `engine/reanalysis_guard`）。
- **人工干预必须留痕**：等级/重要性水平/报告排序/补资料优先级/澄清问题的调整，
  逐条记 `interventions`（谁、何时、改前、改后、理由、依据）。
- 阈值与重要性水平本轮**进会话、进报告头（可追溯与可比）**；
  **尚未回灌到各检测器的判定参数** —— 这一点在交付文档里如实写明，不谎称已生效。
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
_CATALOG = _ROOT / "config" / "analysis_catalog.json"
_SESSION_ROOT = _ROOT / "data" / "analysis_sessions"

#: 会话结构版本（结构一变就 +1，便于旧会话可读性判断）
SESSION_SCHEMA_VERSION = 1

#: 人工干预类型（★ 唯一权威：新增一类只加这里一处）
INTERVENTION_KINDS: Tuple[str, ...] = (
    "risk_level",        # 风险等级调整
    "materiality",       # 重要性水平调整
    "report_order",      # 报告排序调整
    "material_priority", # 补资料优先级调整
    "clarification",     # 澄清问题调整
)

_INTERVENTION_CN: Dict[str, str] = {
    "risk_level": "风险等级",
    "materiality": "重要性水平",
    "report_order": "报告排序",
    "material_priority": "补资料优先级",
    "clarification": "澄清问题",
}

_CACHE: Optional[Dict[str, Any]] = None


def _cst_now() -> str:
    """★ 2026-10-08 收敛：北京时间戳统一到 runtime_storage.now_cst()（唯一权威）。"""
    from runtime_storage import now_cst
    return now_cst()


# ── 目录（唯一权威：config/analysis_catalog.json）───────────────────────────────

def load_catalog() -> Dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.loads(_CATALOG.read_text(encoding="utf-8"))
        except Exception:
            _CACHE = {"schema": 0, "views": [], "profiles": [], "default_thresholds": {}}
    if not isinstance(_CACHE, dict):
        _CACHE = {"schema": 0, "views": [], "profiles": [], "default_thresholds": {}}
    return _CACHE


def views() -> List[Dict[str, Any]]:
    return [v for v in (load_catalog().get("views") or []) if isinstance(v, dict)]


def view_of(view_id: str) -> Optional[Dict[str, Any]]:
    for v in views():
        if v.get("view_id") == view_id:
            return v
    return None


def view_ids() -> List[str]:
    return [str(v.get("view_id")) for v in views()]


def profiles() -> List[Dict[str, Any]]:
    return [p for p in (load_catalog().get("profiles") or []) if isinstance(p, dict)]


def profile_of(profile_id: str) -> Optional[Dict[str, Any]]:
    for p in profiles():
        if p.get("profile_id") == profile_id:
            return p
    return None


def materiality_levels() -> List[Dict[str, Any]]:
    return [m for m in (load_catalog().get("materiality_levels") or []) if isinstance(m, dict)]


def materiality_of(level_id: str) -> Dict[str, Any]:
    for m in materiality_levels():
        if m.get("level_id") == level_id:
            return m
    return {}


def default_thresholds() -> Dict[str, Any]:
    return dict(load_catalog().get("default_thresholds") or {})


def resolve_views(profile_id: Optional[str] = None) -> List[str]:
    """把 profile 视角声明解析成**具体视角 id 列表**；`__ALL__` ⇒ 全部视角。"""
    pid = str(profile_id or load_catalog().get("default_profile") or "default")
    prof = profile_of(pid) or profile_of("default") or {}
    want = list(prof.get("views") or [])
    if "__ALL__" in want or not want:
        return view_ids()
    return [v for v in want if v in view_ids()]


def _dep_closure(module_ids: Iterable[str]) -> List[str]:
    """按 `MODULE_REGISTRY.depends_on` 求依赖闭包（**唯一权威**：编排注册表）。"""
    try:
        from engine.orchestrator import MODULE_REGISTRY as MR
    except Exception:
        return sorted(set(module_ids))
    out, stack = set(), list(module_ids)
    while stack:
        m = stack.pop()
        if m in out:
            continue
        out.add(m)
        for dep in ((MR.get(m) or {}).get("depends_on") or []):
            if dep not in out:
                stack.append(dep)
    return sorted(out)


def _skills_with_versions(skill_ids: Iterable[str]) -> List[Dict[str, str]]:
    """Skill 清单（含版本）——**版本只有一处权威**：`engine.skill_registry`。"""
    try:
        from engine.skill_registry import spec_of
    except Exception:
        spec_of = None
    out: List[Dict[str, str]] = []
    for sid in sorted(set(str(s) for s in skill_ids if s)):
        spec = spec_of(sid) if spec_of else None
        out.append({
            "id": sid,
            "name": str((spec or {}).get("name") or sid),
            # 取不到版本 ⇒ 如实写"未登记"，**不伪造版本号**
            "version": str((spec or {}).get("version") or "未登记"),
        })
    return out


def resolve_orchestration(profile_id: Optional[str] = None,
                          industry: Optional[str] = None,
                          view_ids_override: Optional[Iterable[str]] = None,
                          materiality: Optional[str] = None,
                          thresholds: Optional[Dict[str, Any]] = None
                          ) -> Dict[str, Any]:
    """解析出**本次会话的分析编排**（启用的模块/Skill/视角/阈值/重要性水平）。"""
    pid = str(profile_id or load_catalog().get("default_profile") or "default")
    prof = profile_of(pid) or {}
    vids = list(view_ids_override) if view_ids_override else resolve_views(pid)
    vids = [v for v in vids if v in view_ids()]
    mods: List[str] = []
    sks: List[str] = []
    fams: List[str] = []
    mats: List[str] = []
    th = dict(default_thresholds())
    th.update({k: v for k, v in (prof.get("thresholds") or {}).items() if k})
    for vid in vids:
        v = view_of(vid) or {}
        mods += list(v.get("modules") or [])
        sks += list(v.get("skills") or [])
        fams += list(v.get("risk_families") or [])
        mats += list(v.get("materials") or [])
        th.update({k: val for k, val in (v.get("thresholds") or {}).items() if k})
    if thresholds:
        th.update({k: v for k, v in thresholds.items() if v is not None})
    mid = str(materiality or prof.get("materiality") or "standard")
    return {
        "profile_id": pid,
        "profile_name": str(prof.get("profile_name") or pid),
        "views": vids,
        "view_names": [str((view_of(v) or {}).get("view_name") or v) for v in vids],
        "modules": _dep_closure(mods),
        "skills": _skills_with_versions(sks),
        "risk_families": sorted(set(fams)),
        "materials": sorted(set(mats)),
        "thresholds": th,
        "materiality": mid,
        "materiality_level": materiality_of(mid),
        "industry": str(industry or ""),
        "is_default": (pid == str(load_catalog().get("default_profile") or "default")
                       and set(vids) == set(view_ids())),
    }


def rotate_views(last_view_ids: Optional[Iterable[str]] = None,
                 available: Optional[Iterable[str]] = None,
                 times: int = 1) -> List[str]:
    """**确定性**视角轮换：从"上次起始视角的下一项"开始轮转（不是随机打乱）。

    ★ 为什么要确定性：随机打乱是「假重新分析」的特征之一（无依据改变呈现顺序）。
      轮换必须能一句话解释："接着上次的视角往下轮"。
    """
    avail = list(available) if available else view_ids()
    avail = [v for v in avail if v in view_ids()] or view_ids()
    if not avail:
        return []
    last = [v for v in (last_view_ids or []) if v in avail]
    start = 0
    if last:
        try:
            start = (avail.index(last[0]) + max(1, int(times))) % len(avail)
        except ValueError:
            start = 0
    return avail[start:] + avail[:start]


def sections_weight(order: Optional[Iterable[str]] = None) -> Dict[str, int]:
    """视角 → 叙事权重（供 `engine.narrative_variants` 组织章节顺序）。"""
    order = list(order or view_ids())
    out: Dict[str, int] = {}
    for i, vid in enumerate(order):
        w = int((view_of(vid) or {}).get("narrative_weight") or 5)
        out[vid] = w * 100 - i      # 权重优先，同权重按本次顺序
    return out


# ── 编排落地：过滤执行计划（默认档为**恒等函数**，不改既有行为）─────────────────

def filter_orchestration_plan(plan: Dict[str, Any],
                              orchestration: Optional[Dict[str, Any]]
                              ) -> Tuple[Dict[str, Any], List[str]]:
    """按会话启用的模块过滤编排计划；返回 (新计划, 被跳过的模块 id 列表)。

    ★ **默认档（`is_default=True`）直接原样返回** —— 保证"改造前后行为一致"，
      这是本能力能安全上线的唯一前提（有行为测试锁死）。
    """
    if not isinstance(plan, dict) or not isinstance(orchestration, dict):
        return plan, []
    if orchestration.get("is_default"):
        return plan, []
    enabled = set(orchestration.get("modules") or [])
    if not enabled:
        return plan, []
    kept, skipped = [], []
    for m in (plan.get("active_modules") or []):
        mid = m.get("id") if isinstance(m, dict) else str(m)
        (kept if mid in enabled else skipped).append(m)
    if not skipped:
        return plan, []
    new_plan = dict(plan)
    new_plan["active_modules"] = kept
    new_plan["execution_order"] = [x for x in (plan.get("execution_order") or [])
                                   if (x.get("id") if isinstance(x, dict) else x) in enabled]
    new_plan["skipped_modules"] = list(plan.get("skipped_modules") or []) + [
        {"id": (m.get("id") if isinstance(m, dict) else str(m)),
         "reason": "本次分析编排未启用该模块（视角：%s）"
                   % "、".join(orchestration.get("view_names") or [])}
        for m in skipped]
    new_plan["total_active"] = len(kept)
    new_plan["total_skipped"] = len(skipped)
    new_plan["summary"] = "%s｜本次编排启用 %d 个模块（视角：%s）" % (
        str(plan.get("summary") or ""), len(kept),
        "、".join(orchestration.get("view_names") or []))
    return new_plan, [str(m.get("id") if isinstance(m, dict) else m) for m in skipped]


# ── 会话构造 ──────────────────────────────────────────────────────────────────

def _short(s: str, n: int = 8) -> str:
    return str(s or "")[:n]


def build_session(company_id: Any,
                  orchestration: Optional[Dict[str, Any]] = None,
                  snapshot: Optional[Dict[str, Any]] = None,
                  trace: Optional[Iterable[Dict[str, Any]]] = None,
                  params: Optional[Dict[str, Any]] = None,
                  fingerprint: Optional[Dict[str, str]] = None,
                  analyzed_at: Optional[str] = None,
                  session_seq: int = 1) -> Dict[str, Any]:
    """构造一个**分析会话**（任务1 的六个要素齐备）。

    ★ `session_id` **完全由内容派生**：`AS-<企业>-<配置与快照哈希前8位>`，**不含日期**。
      为什么刻意不放日期：一旦日期进 ID，"同快照换一天重跑"就会生成一个新编号，
      恰好把「只换日期」伪装成"新会话"——那正是用户第 4 批要检出的问题。
      时间只记在 `analyzed_at`；**同快照 + 同配置 ⇒ 同 `session_id`**。
    ★ `run_id` = `session_id + "-r%04d"`（**运行号**，每次执行 +1）：
      - 会话**身份**（session_id）用于判断"是不是同一份快照/同一套配置"；
      - **运行**（run_id）用于"这次 vs 上次"的增量对比与假分析检测；
      - 两者分开，才不会出现"同快照重跑把上次会话覆盖掉、永远无法对比"的死角。
    """
    from engine.snapshot_invariance import snapshot_version as _sv

    orch = orchestration or resolve_orchestration()
    snap = dict(snapshot or {})
    files = snap.get("files") or []
    if not snap.get("version"):
        snap["version"] = _sv(files)
    snap.setdefault("files_count", len(files))
    pid = str(orch.get("profile_id") or "default")
    _seed = json.dumps({
        "profile": pid, "views": orch.get("views"), "snapshot": snap.get("version"),
        "skills": [(s.get("id"), s.get("version")) for s in (orch.get("skills") or [])],
        "thresholds": orch.get("thresholds"), "materiality": orch.get("materiality"),
        "params": params or {},
    }, ensure_ascii=False, sort_keys=True)
    import hashlib as _hl
    h = _hl.sha1(_seed.encode("utf-8")).hexdigest()[:8]
    sid = "AS-%s-%s" % (str(company_id or "0"), h)
    seq = int(session_seq)

    return {
        "schema": SESSION_SCHEMA_VERSION,
        "session_id": sid,
        "run_id": "%s-r%04d" % (sid, seq),
        "session_seq": seq,
        "company_id": str(company_id or ""),
        "analyzed_at": analyzed_at or _cst_now(),
        "skills": list(orch.get("skills") or []),
        "orchestration": orch,
        "params": {
            "industry": str((params or {}).get("industry") or orch.get("industry") or ""),
            "taxes": list((params or {}).get("taxes") or []),
            "focus": list((params or {}).get("focus") or orch.get("view_names") or []),
            "thresholds": dict(orch.get("thresholds") or {}),
            "materiality": orch.get("materiality"),
            "materiality_level": orch.get("materiality_level") or {},
        },
        "snapshot": snap,
        "trace": [dict(t) for t in (trace or []) if isinstance(t, dict)],
        "fingerprint": dict(fingerprint or {}),
        "interventions": [],
        "session_hash": h,
    }


def record_intervention(session: Dict[str, Any], kind: str, before: Any, after: Any,
                        reason: str, operator: str = "人工",
                        basis: str = "", at: Optional[str] = None) -> Dict[str, Any]:
    """登记一条**人工干预**（类型必须在 `INTERVENTION_KINDS` 内；否则报错，不静默丢）。"""
    if not isinstance(session, dict):
        raise TypeError("session 必须是 dict")
    if kind not in INTERVENTION_KINDS:
        raise ValueError("未知干预类型：%s（合法值 %s）" % (kind, list(INTERVENTION_KINDS)))
    rec = {
        "kind": kind, "kind_cn": _INTERVENTION_CN.get(kind, kind),
        "before": before, "after": after, "reason": str(reason or ""),
        "operator": str(operator or "人工"), "basis": str(basis or ""),
        "at": at or _cst_now(),
    }
    session.setdefault("interventions", []).append(rec)
    return rec


def interventions_summary(session: Dict[str, Any]) -> List[str]:
    """干预留痕的自然句（**不用"字段：值"**，符合报告文风铁律）。"""
    out: List[str] = []
    for r in (session or {}).get("interventions") or []:
        out.append("本次由%s将%s由「%s」调整为「%s」，理由：%s%s。" % (
            r.get("operator"), r.get("kind_cn"), r.get("before"), r.get("after"),
            r.get("reason") or "未填写",
            "（依据：" + str(r.get("basis")) + "）" if r.get("basis") else ""))
    return out


def session_header_text(session: Dict[str, Any]) -> str:
    """报告开头要标明的**本次分析会话信息**（自然句，不用"字段：值"）。"""
    s = session or {}
    orch = s.get("orchestration") or {}
    p = s.get("params") or {}
    snap = s.get("snapshot") or {}
    ml = (p.get("materiality_level") or {})
    parts = [
        "本次分析于 %s 执行，会话编号 %s（第 %s 次分析）。"
        % (str(s.get("analyzed_at") or "")[:19].replace("T", " "),
           s.get("session_id") or "未生成", s.get("session_seq") or 1),
        "采用「%s」编排，覆盖%s共 %d 个检查视角，启用 %d 项检查能力。"
        % (orch.get("profile_name") or "常规全面检查",
           "、".join(p.get("focus") or orch.get("view_names") or []) or "全部",
           len(orch.get("views") or []), len(s.get("skills") or [])),
    ]
    if p.get("industry"):
        parts.append("行业口径按「%s」适用。" % p["industry"])
    if ml:
        parts.append("重要性水平取「%s」档（金额下限 %s 元）。"
                     % (ml.get("level_name") or p.get("materiality"),
                        "{:,}".format(int(ml.get("amount_floor") or 0))))
    parts.append("分析所依据的数据快照版本为 %s，共 %d 份资料；该版本只反映资料清单与体量，"
                 "不随上传时间变化。" % (snap.get("version") or "未生成", snap.get("files_count") or 0))
    iv = interventions_summary(s)
    if iv:
        parts.append("本次分析含 %d 项人工干预，逐项留痕见附件。" % len(iv))
    return "".join(parts)


# ── 落盘与读取（append-only 台账）──────────────────────────────────────────────

def session_dir(company_id: Any) -> Path:
    return _SESSION_ROOT / str(company_id or "0")


def persist_session(session: Dict[str, Any], out_dir: Optional[Path] = None) -> str:
    """把会话落盘为 `<公司>/<run_id>.json`（**每次运行一份**，同一次运行幂等覆盖自己）。

    ★ 用 `run_id` 而不是 `session_id` 命名：同一快照重跑时 `session_id` 相同，
      若按 session_id 命名就会**把上次会话覆盖掉** ⇒ 永远无法做增量对比/假分析检测。
    """
    d = Path(out_dir) if out_dir else session_dir((session or {}).get("company_id"))
    d.mkdir(parents=True, exist_ok=True)
    name = str((session or {}).get("run_id")
               or (session or {}).get("session_id") or "unknown")
    p = d / ("%s.json" % name)
    p.write_text(json.dumps(session, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(p)


def load_sessions(company_id: Any) -> List[Dict[str, Any]]:
    d = session_dir(company_id)
    if not d.exists():
        return []
    out: List[Dict[str, Any]] = []
    for f in sorted(d.glob("AS-*.json")):
        try:
            o = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(o, dict):
            out.append(o)
    out.sort(key=lambda s: (str(s.get("analyzed_at") or ""), int(s.get("session_seq") or 0)))
    for i, s in enumerate(out, 1):
        s["session_seq"] = i
    return out


def previous_session(company_id: Any, current: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """取**上一次运行**的会话（同企业、`run_id` 不同、时间不晚于当前）。"""
    cur_run = str((current or {}).get("run_id") or "")
    cur_id = str((current or {}).get("session_id") or "")
    cur_at = str((current or {}).get("analyzed_at") or "")
    cands = [s for s in load_sessions(company_id)
             if str(s.get("run_id") or "") != cur_run
             and not (not cur_run and str(s.get("session_id") or "") == cur_id)]
    prev = [s for s in cands if str(s.get("analyzed_at") or "") <= cur_at] or cands
    return (prev[-1] if prev else (cands[0] if cands else None))


def next_seq(company_id: Any) -> int:
    return len(load_sessions(company_id)) + 1


# ── 分析收尾：一次分析产出全部会话交付物 ──────────────────────────────────────

def _trace_from_execution(execution: Optional[Dict[str, Any]],
                          pipeline_log: Optional[Iterable[Any]] = None
                          ) -> List[Dict[str, Any]]:
    """把执行阶段转成**分析轨迹**（真实执行证据：用于区分"重算了"与"返回了缓存"）。"""
    out: List[Dict[str, Any]] = []
    stages = (execution or {}).get("stages") if isinstance(execution, dict) else None
    if isinstance(stages, dict):
        for k, v in stages.items():
            d = v if isinstance(v, dict) else {"status": str(v)}
            out.append({"step": str(k), "status": str(d.get("status") or ""),
                        "detail": str(d.get("message") or d.get("detail") or "")[:160]})
    for line in list(pipeline_log or [])[:40]:
        out.append({"step": "pipeline", "detail": str(line)[:160]})
    return out


def _files_of(report_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """数据快照的文件清单（名 + 大小 + 条数；**不含上传时间**）。"""
    out: List[Dict[str, Any]] = []
    for f in ((report_data or {}).get("file_results") or []):
        if not isinstance(f, dict):
            continue
        rows = f.get("rows")
        if isinstance(rows, list):
            rows = len(rows)
        out.append({"name": str(f.get("filename") or f.get("name") or ""),
                    "size": f.get("size") or f.get("file_size"),
                    "rows": rows})
    return out


def _acceptance_for(title: str, judge: str) -> str:
    """给规则草案一个**真会失败**的验收方式（可测试硬要求）。"""
    return ("构造满足判据的数据（%s），断言报告产出「%s」；再构造不满足的数据，"
            "断言不产出该项 ⇒ 该用例必须真的会失败才有效。"
            % (judge[:60] or "见判据", str(title)[:30]))


def finish_session(company_id: Any,
                   report_data: Dict[str, Any],
                   report: Dict[str, Any],
                   execution: Optional[Dict[str, Any]] = None,
                   params: Optional[Dict[str, Any]] = None,
                   out_dir: Optional[Path] = None
                   ) -> Dict[str, Any]:
    """一次分析的收尾：**构建会话 → 落盘 → 增量对比 → 假分析自检 → 画像/案例/规则建议**。

    返回 `{session, header, incremental, audit, dossier, cases, abstraction, docs, dir}`。
    ★ 全程 **except 留痕、绝不静默**：任一步失败都在返回值里写明 `degraded`。
    """
    from engine.snapshot_invariance import report_digest
    params = dict(params or {})
    degraded: List[str] = []
    industry = str(params.get("industry")
                   or ((report_data or {}).get("target_entity") or {}).get("industry") or "")
    orch = resolve_orchestration(params.get("profile"), industry=industry,
                                 view_ids_override=params.get("views"),
                                 materiality=params.get("materiality"),
                                 thresholds=params.get("thresholds"))
    snap = {"files": _files_of(report_data)}
    session = build_session(company_id, orch, snap,
                            trace=_trace_from_execution(execution,
                                                        (report_data or {}).get("pipeline_log")),
                            params={**params, "industry": industry},
                            analyzed_at=params.get("analyzed_at"),
                            session_seq=next_seq(company_id))
    digest = report_digest(report)
    session["report_digest"] = digest
    session["fingerprint"] = digest.get("fingerprints") or {}

    # 上一会话必须在**落盘本次之前**取（否则会取到自己）
    prev_session = params.get("prev_session") or previous_session(company_id, session)
    prev_digest = (prev_session or {}).get("report_digest") or {}

    # ★ 会话目录**先定**：增量对比表必须与其余文档落在同一个会话目录里
    #   （否则 out_dir=None 时对比表会落到公司根目录、跨会话互相覆盖）。
    d = Path(out_dir) if out_dir else (_SESSION_ROOT / str(company_id or "0"))
    # ★ 文档目录按 **run_id**（而非 session_id）命名：同快照重跑时 session_id 相同，
    #   若按 session_id 命名，第二次运行会把第一次的 5 份文档**覆盖掉**，
    #   增量对比与假分析检测的证据链就断了（本轮实测踩过 session JSON 的同一个坑）。
    sdir = d / str(session["run_id"])

    # ① 增量分析
    incremental: Dict[str, Any] = {}
    try:
        from engine.incremental_analysis import run_incremental
        incremental = run_incremental(company_id, report, session,
                                      prev_report=prev_digest or None,
                                      prev_session=prev_session, out_dir=sdir)
    except Exception as exc:                     # noqa: BLE001
        degraded.append("增量分析失败：%s" % exc)
    session["incremental"] = {k: v for k, v in incremental.items() if k != "markdown"}

    # ② 假重新分析自检
    audit: Dict[str, Any] = {}
    try:
        from engine.reanalysis_guard import audit_reanalysis
        audit = audit_reanalysis(prev_digest or None, report, prev_session, session,
                                 prev_signature=(prev_digest or {}).get("content_signature"),
                                 curr_signature=digest.get("content_signature"))
    except Exception as exc:                     # noqa: BLE001
        degraded.append("假重新分析检测失败：%s" % exc)
    session["reanalysis_audit"] = audit

    # ③ 企业画像
    dossier: Dict[str, Any] = {}
    dossier_md = ""
    try:
        from engine.entity_dossier import build_dossier, render_dossier_md
        dossier = build_dossier(report_data)
        dossier_md = render_dossier_md(dossier)
    except Exception as exc:                     # noqa: BLE001
        degraded.append("企业画像生成失败：%s" % exc)

    # ④ 同类案例参考（只作参考）
    cases: List[Dict[str, Any]] = []
    cases_md = ""
    try:
        from engine.experience_library import match_cases, render_cases_md
        risks = sorted({str(t) for p in (report.get("confirmed_problems") or [])
                        for t in (p.get("taxes") or [])})
        cases = match_cases(industry, risks, str(dossier.get("business_model") or ""))
        cases_md = render_cases_md(cases, industry, risks)
    except Exception as exc:                     # noqa: BLE001
        degraded.append("同类案例检索失败：%s" % exc)

    # ⑤ 从点到面抽象 → 规则萃取建议
    abstraction: Dict[str, Any] = {}
    proposals_md = ""
    try:
        from engine.rule_abstraction import abstract_findings, render_proposals_md
        findings_in: List[Dict[str, Any]] = []
        for p in (report.get("confirmed_problems") or []):
            judge = ""
            if p.get("redline_id") or p.get("indicator"):
                judge = "当红线/指标「%s」所述条件成立时，判为「%s」" % (
                    p.get("redline_id") or p.get("indicator"), str(p.get("title"))[:24])
            findings_in.append({**p, "_ctx": {}})
        # 逐条带 ctx（判据 + 验收），保证「可测试」硬要求落地
        results = {"proposals": [], "cases_kept": []}
        for i, p in enumerate(report.get("confirmed_problems") or [], 1):
            judge = ("当红线/指标「%s」所述条件成立时，判为「%s」"
                     % (p.get("redline_id") or p.get("indicator"), str(p.get("title"))[:24])
                     ) if (p.get("redline_id") or p.get("indicator")) else ""
            r = abstract_findings([p], {
                "seq": i, "judge": judge,
                "acceptance": _acceptance_for(str(p.get("title") or ""), judge) if judge else "",
                "test_hint": "tests/test_batch4_skills.py（新增用例）",
                "tier": "manual",
            })
            results["proposals"] += r["proposals"]
            results["cases_kept"] += r["cases_kept"]
        results["summary_line"] = (
            "本轮共 %d 条发现：其中 %d 条可抽象为规则（进入规则萃取流程，须人工确认后入库）、"
            "%d 条作为个案记录（写明不满足的判据，不静默丢弃）。"
            % (len(results["proposals"]) + len(results["cases_kept"]),
               len(results["proposals"]), len(results["cases_kept"])))
        abstraction = results
        proposals_md = render_proposals_md(results)
    except Exception as exc:                     # noqa: BLE001
        degraded.append("从点到面抽象失败：%s" % exc)
    session["rule_abstraction"] = {
        "proposal_count": len(abstraction.get("proposals") or []),
        "case_count": len(abstraction.get("cases_kept") or []),
        "summary_line": abstraction.get("summary_line") or "",
    }
    session["degraded"] = degraded

    # ⑥ 落盘：会话 JSON + 5 份文档
    docs: Dict[str, str] = {}
    try:
        sdir.mkdir(parents=True, exist_ok=True)
        _write(sdir / "本次分析会话说明.md", _session_md(session, incremental, audit))
        _write(sdir / "与上次分析对比表.md",
               incremental.get("markdown")
               or "# 与上次分析对比表\n\n（未生成：本轮增量分析未产出）\n")
        _write(sdir / "企业画像.md", dossier_md or "# 企业画像\n\n（未生成）\n")
        _write(sdir / "同类案例参考.md", cases_md or "# 同类案例参考\n\n（未生成）\n")
        _write(sdir / "规则萃取建议.md", proposals_md or "# 规则萃取建议\n\n（未生成）\n")
        docs = {p.name: str(p) for p in sorted(sdir.glob("*.md"))}
        session["doc_dir"] = str(sdir)
    except Exception as exc:                     # noqa: BLE001
        degraded.append("会话文档落盘失败：%s" % exc)
    try:
        session["session_file"] = persist_session(session, out_dir=d)
    except Exception as exc:                     # noqa: BLE001
        degraded.append("会话落盘失败：%s" % exc)

    header = session_header_text(session)
    if not audit.get("ok", True) and audit.get("issues"):
        header += "本次自检发现 %d 项须人工确认（%s）。" % (
            len([i for i in audit["issues"] if i.get("level") == "ERROR"]),
            "；".join(i["name"] for i in audit["issues"] if i.get("level") == "ERROR"))
    return {"session": session, "header": header, "incremental": incremental,
            "audit": audit, "dossier": dossier, "cases": cases,
            "abstraction": abstraction, "docs": docs, "dir": str(sdir)}


def _write(p: Path, text: str) -> None:
    p.write_text(text, encoding="utf-8")


def _session_md(session: Dict[str, Any], incremental: Dict[str, Any],
                audit: Dict[str, Any]) -> str:
    """《本次分析会话说明》。"""
    L = ["# 本次分析会话说明", "", session_header_text(session), ""]
    L += ["## 一、本次启用的检查能力与版本", "",
          "| 能力 | 版本 |", "|---|---|"]
    for s in (session.get("skills") or []):
        L.append("| %s | %s |" % (s.get("name") or s.get("id"), s.get("version")))
    L += ["", "## 二、分析参数", "",
          "| 参数 | 取值 |", "|---|---|"]
    p = session.get("params") or {}
    for k, cn in (("industry", "行业"), ("materiality", "重要性水平"),
                  ("taxes", "税种"), ("focus", "检查重点")):
        v = p.get(k)
        L.append("| %s | %s |" % (cn, "、".join(v) if isinstance(v, list) else (v or "—")))
    for k, v in (p.get("thresholds") or {}).items():
        L.append("| 阈值 %s | %s |" % (k, v))
    L += ["", "## 三、数据快照", "",
          "快照版本 %s（共 %d 份资料）。该版本只反映资料清单与体量，不随上传时间变化。"
          % ((session.get("snapshot") or {}).get("version") or "未生成",
             (session.get("snapshot") or {}).get("files_count") or 0), "",
          "## 四、分析轨迹", ""]
    tr = session.get("trace") or []
    if tr:
        L += ["| # | 步骤 | 状态 | 说明 |", "|---|---|---|---|"]
        for i, t in enumerate(tr, 1):
            L.append("| %d | %s | %s | %s |" % (i, t.get("step"), t.get("status") or "—",
                                                str(t.get("detail") or "—")[:120]))
    else:
        L.append("本次未采集到执行轨迹（如为缓存返回，将被「假重新分析检测」标记）。")
    L += ["", "## 五、与上次对比", "", incremental.get("summary_line") or "无对比结果。", "",
          "## 六、假重新分析自检", "", audit.get("note") or "未执行。", ""]
    for i in (audit.get("issues") or []):
        L.append("- 【%s】%s：%s" % (i.get("level"), i.get("name"), i.get("detail")))
    L += ["", "## 七、人工干预留痕", ""]
    iv = interventions_summary(session)
    L += iv if iv else ["本次无人工干预记录。"]
    if session.get("degraded"):
        L += ["", "## 八、降级说明（未静默丢弃）", ""] + ["- " + x for x in session["degraded"]]
    L.append("")
    return "\n".join(L)


__all__ = [
    "SESSION_SCHEMA_VERSION", "INTERVENTION_KINDS",
    "load_catalog", "views", "view_of", "view_ids", "profiles", "profile_of",
    "materiality_levels", "materiality_of", "default_thresholds", "resolve_views",
    "resolve_orchestration", "rotate_views", "sections_weight",
    "filter_orchestration_plan", "build_session", "record_intervention",
    "interventions_summary", "session_header_text", "persist_session",
    "load_sessions", "previous_session", "next_seq", "session_dir", "finish_session",
]

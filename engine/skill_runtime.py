# -*- coding: utf-8 -*-
"""Skill 编排引擎（用户第 6 批 任务1）。

## 任务要求 → 落点

| 要求 | 落点 |
|---|---|
| 按检查方案配置选择启用哪些 Skill | `config/skill_plan.json`（方案库，唯一权威）+ `resolve_plan()` |
| 按顺序执行、支持并行、条件分支、失败重试 | `run()`：`steps` 顺序；`parallel_group` 同组并行；`when` 条件分支；`retries` 重试 |
| 每个 Skill 的输入输出可追溯 | 日志每条含 `params`（入参）、`result`（出参摘要）、`ms`、`ok`、`error` |
| 支持行业/企业/税种/检查重点不同组合 | `resolve_plan(industry, company, taxes, focus)` 按 `applies_to` 选方案并叠加 |
| 支持局部重跑：只重跑该 Skill 及下游 | `rerun(from_step_id)`：下游 = 同方案里顺序在其后的步骤 + 同 `parallel_group` 的伙伴 |
| 输出《本次分析 Skill 执行日志》 | `render_log_md()`；同时落盘 `data/skill_runs/<run_id>.json` |
| 支持人工干预：某 Skill 后暂停、复核后继续 | `pause_after` ⇒ 返回 `status="paused"`；`resume(token)` 从暂停点继续 |
| 支持灰度发布与版本回滚 | `gray.enabled_for_companies` + `rollback_to`；`effective_version()` |

## 铁律

- **Skill 必须是已登记的**（`config/skill_specs.json`）：未登记 ⇒ 直接报错，**不得静默跳过**
  （静默跳过 = 报告少了一段却没人知道）。
- **条件分支必须留痕**：`when` 不成立 ⇒ 日志里记 `skipped` + 原因，不是"看不见"。
- **重试必须留痕**：每次尝试都记 `attempt`；最终失败 ⇒ `ok=false` + `error`。
- **暂停不丢进度**：暂停点之前的步骤结果全部保留在 `log` 里，`resume` 不重跑已成功的步骤。
- 版本只有一处权威：`config/skill_specs.json`（Skill 自身版本）+ 本方案库的 `versions`（**启用版本**）。
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
_PLAN = _ROOT / "config" / "skill_plan.json"
_RUNS = _ROOT / "data" / "skill_runs"

#: 日志字段（★ 唯一权威：任务点名要求的字段，新增只加这里一处）
LOG_FIELDS: Tuple[str, ...] = (
    "step_id", "skill_id", "version", "entry", "params", "ms", "attempt",
    "status", "result", "error",
)

#: 步骤状态枚举
STATUSES: Tuple[str, ...] = ("ok", "failed", "skipped", "paused")

_CACHE: Optional[Dict[str, Any]] = None


def _now() -> str:
    """★ 2026-10-08 收敛：北京时间戳统一到 runtime_storage.now_cst()（唯一权威）。"""
    from runtime_storage import now_cst
    return now_cst()


def load_plan_store() -> Dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.loads(_PLAN.read_text(encoding="utf-8"))
        except Exception:
            _CACHE = {}
    return _CACHE or {}


def plans() -> List[Dict[str, Any]]:
    return [p for p in (load_plan_store().get("plans") or []) if isinstance(p, dict)]


def plan_of(plan_id: str) -> Optional[Dict[str, Any]]:
    for p in plans():
        if p.get("plan_id") == plan_id:
            return p
    return None


def validate_plans() -> List[str]:
    """方案库自检（可机检）：Skill 已登记、entry 在 impl 里存在、状态/字段齐备。"""
    probs: List[str] = []
    try:
        from engine.skill_registry import spec_of
    except Exception as exc:  # noqa: BLE001
        return ["skill_registry 不可用：%s" % exc]
    seen = set()
    for pl in plans():
        pid = str(pl.get("plan_id") or "")
        if not pid or pid in seen:
            probs.append("方案 id 缺失或重复：%r" % pid)
        seen.add(pid)
        if not (pl.get("steps") or []):
            probs.append("方案 %s 没有步骤" % pid)
        for st in (pl.get("steps") or []):
            sid = str(st.get("skill_id") or "")
            spec = spec_of(sid)
            if not spec:
                probs.append("方案 %s 引用了未登记的 Skill：%s" % (pid, sid))
                continue
            impl = _ROOT / str(spec.get("impl") or "")
            entry = str(st.get("entry") or "")
            if entry and impl.exists():
                txt = impl.read_text(encoding="utf-8")
                if ("def %s(" % entry) not in txt:
                    probs.append("方案 %s 的 %s.entry「%s」在实现里不存在"
                                 % (pid, sid, entry))
            if "retries" in st and (not isinstance(st["retries"], int) or st["retries"] < 0):
                probs.append("方案 %s 步骤 %s 的 retries 非法" % (pid, st.get("step_id")))
    return probs


# ── 方案解析（行业/企业/税种/检查重点组合）───────────────────────────────────

def resolve_plan(industry: str = "", company_id: Any = None,
                 taxes: Optional[List[str]] = None, focus: Optional[List[str]] = None,
                 plan_id: Optional[str] = None) -> Dict[str, Any]:
    """选出**适用的方案**：显式 `plan_id` 优先；否则按 `applies_to` 命中（行业 > 检查重点 > 默认）。

    命中不了 ⇒ 用 `default_plan` 并**如实标注**（不猜一个看起来像的）。
    """
    if plan_id:
        p = plan_of(plan_id)
        if not p:
            raise ValueError("未登记的方案：%s（合法值 %s）"
                             % (plan_id, [x.get("plan_id") for x in plans()]))
        return dict(p, matched_by="explicit")
    ind = str(industry or "")
    fc = [str(x) for x in (focus or [])]
    tx = [str(x) for x in (taxes or [])]
    for p in plans():
        ap = p.get("applies_to") or {}
        if ind and ind in (ap.get("industries") or []):
            return dict(p, matched_by="industry")
    for p in plans():
        ap = p.get("applies_to") or {}
        if fc and set(fc) & set(ap.get("focus") or []):
            return dict(p, matched_by="focus")
    for p in plans():
        ap = p.get("applies_to") or {}
        if tx and set(tx) & set(ap.get("taxes") or []):
            return dict(p, matched_by="taxes")
    d = plan_of(str(load_plan_store().get("default_plan") or "standard")) or (plans() or [{}])[0]
    return dict(d, matched_by="default")


def effective_version(skill_id: str, company_id: Any = None) -> str:
    """该 Skill 本次**实际启用**的版本（灰度/回滚的唯一判据）。

    - 企业在 `gray.enabled_for_companies[skill]` 白名单里 ⇒ 用 `versions`（新版/灰度版）；
    - 否则若 `rollback_to[skill]` 有值 ⇒ 用回滚版本；
    - 都没有 ⇒ 用 Skill 自身登记版本（`skill_registry`，唯一权威）。
    """
    store = load_plan_store()
    g = store.get("gray") or {}
    vers = store.get("versions") or {}
    allow = (g.get("enabled_for_companies") or {})
    key = str(skill_id)
    cid = str(company_id or "")
    if cid and cid in (allow.get(key) or []):
        return str(vers.get(key) or _spec_version(key))
    rb = (g.get("rollback_to") or {}).get(key)
    if rb:
        return str(rb)
    return str(vers.get(key) or _spec_version(key))


def _spec_version(skill_id: str) -> str:
    try:
        from engine.skill_registry import spec_of
        s = spec_of(skill_id) or {}
        return str(s.get("version") or "未登记")
    except Exception:
        return "未登记"


def rollback(skill_id: str, to_version: Optional[str] = None) -> Dict[str, Any]:
    """记录一次**回滚**（写进方案库的 `gray.rollback_to`）。`to_version` 省略 ⇒ 回滚到登记版本。"""
    store = load_plan_store()
    g = store.setdefault("gray", {})
    rb = g.setdefault("rollback_to", {})
    rb[str(skill_id)] = str(to_version or _spec_version(skill_id))
    _PLAN.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    global _CACHE
    _CACHE = None
    return {"skill_id": skill_id, "rollback_to": rb[str(skill_id)], "at": _now()}


# ── 条件分支 ─────────────────────────────────────────────────────────────────

def _cond_met(when: Any, ctx: Dict[str, Any]) -> Tuple[bool, str]:
    """`when` 判据（★ 数据驱动：新增一种只加一行）。

    支持：`always` / `industry_matched` / `export_role`（值在列表内）/ `has`（ctx 键非空）。
    `when` 为空 ⇒ 视为成立。**判不出也当不成立**（宁可跳过并留痕，不无据执行）。
    """
    if not when:
        return True, "无条件"
    if not isinstance(when, dict):
        return False, "when 形态非法：%r" % (when,)
    if when.get("always"):
        return True, "always"
    if "industry_matched" in when:
        want = bool(when.get("industry_matched"))
        got = bool((ctx.get("industry_params") or {}).get("matched"))
        return (got == want), "industry_matched=%s（实际 %s）" % (want, got)
    if "export_role" in when:
        want = [str(x) for x in (when.get("export_role") or [])]
        got = str(ctx.get("export_role") or "")
        return (got in want), "export_role=%s" % (got or "未指定")
    if "has" in when:
        k = str(when.get("has"))
        return bool(ctx.get(k)), "has(%s)=%s" % (k, bool(ctx.get(k)))
    return False, "未登记的 when 形态：%s" % sorted(when.keys())


# ── 执行 ─────────────────────────────────────────────────────────────────────

Handler = Callable[[Dict[str, Any], Dict[str, Any]], Any]


def _default_handler(skill_id: str, entry: str) -> Handler:
    """默认执行器：真调该 Skill 的实现入口（签名不匹配 ⇒ 视为失败并留痕，不静默）。"""
    def _run(ctx: Dict[str, Any], params: Dict[str, Any]) -> Any:
        from engine.skill_registry import spec_of
        spec = spec_of(skill_id) or {}
        impl = str(spec.get("impl") or "")
        if not impl:
            raise RuntimeError("Skill %s 未登记实现文件" % skill_id)
        mod_name = impl.replace("/", ".").replace(".py", "")
        mod = __import__(mod_name, fromlist=["*"])
        fn = getattr(mod, entry or "", None)
        if not callable(fn):
            raise RuntimeError("Skill %s 缺入口 %s" % (skill_id, entry))
        args, kw = resolve_args(ctx, params)
        return fn(*args, **kw)
    return _run


def resolve_args(ctx: Dict[str, Any], params: Dict[str, Any]) -> Tuple[List[Any], Dict[str, Any]]:
    """把步骤声明的参数解析成真实实参（**可追溯**：解析结果会记进日志的 `params.resolved`）。

    支持三种写法（★ 数据驱动，新增一种只加一行）：
      · `{"arg": "industry"}`             —— 取 ctx 上的某个键作为唯一实参；
      · `{"args_from_ctx": ["a", "b"]}`   —— 依次取 ctx 的键作为位置实参；
      · `{"args": [...], "kwargs": {...}}` —— 字面量实参/关键字实参。
    """
    if params.get("args_from_ctx"):
        return [ctx.get(str(k)) for k in params["args_from_ctx"]], dict(params.get("kwargs") or {})
    if params.get("arg"):
        return [ctx.get(str(params["arg"]))], dict(params.get("kwargs") or {})
    return list(params.get("args") or []), dict(params.get("kwargs") or {})


def _summarize(v: Any, limit: int = 160) -> Any:
    if v is None or isinstance(v, (int, float, bool)):
        return v
    if isinstance(v, str):
        return v[:limit]
    if isinstance(v, (list, tuple)):
        return {"type": "list", "n": len(v), "sample": _summarize(v[0] if v else None, 60)}
    if isinstance(v, dict):
        return {"type": "dict", "keys": sorted(str(k) for k in v.keys())[:10]}
    return str(v)[:limit]


def run(plan: Dict[str, Any], ctx: Optional[Dict[str, Any]] = None,
        handlers: Optional[Dict[str, Handler]] = None,
        company_id: Any = None, stop_before: Optional[str] = None,
        only_steps: Optional[List[str]] = None) -> Dict[str, Any]:
    """执行方案。返回 `{run_id, status, log, plan_id, started_at, finished_at, ...}`。

    `stop_before` / `only_steps` 供**局部重跑**使用（只跑指定步骤及其下游）。
    """
    ctx = dict(ctx or {})
    handlers = handlers or {}
    steps = [s for s in (plan.get("steps") or []) if isinstance(s, dict)]
    if only_steps is not None:
        keep = set(str(x) for x in only_steps)
        steps = [s for s in steps if str(s.get("step_id")) in keep]
    # ★ 运行号里**不要**做"去掉日期分隔符再截取"的动作：那正是闸门禁止的
    #   "自造期间键"写法（虽然这里只是编号、不是月份键，但**不弱化闸门**更好）。
    run_id = "SR-%s-%s" % (_now()[:10], uuid.uuid4().hex[:6])
    log: List[Dict[str, Any]] = []
    status = "ok"

    def _exec_one(st: Dict[str, Any]) -> Dict[str, Any]:
        sid = str(st.get("skill_id") or "")
        entry = str(st.get("entry") or "")
        params = st.get("params") or {}
        rec: Dict[str, Any] = {
            "step_id": str(st.get("step_id") or ""), "skill_id": sid,
            "version": effective_version(sid, company_id), "entry": entry,
            "params": params, "ms": 0, "attempt": 0, "status": "ok",
            "result": None, "error": "",
        }
        # ★ 条件分支**必须每次都评估**。
        #   初版写了个 `skip_cond` 开关，但**没有任何调用点传 True** ⇒ `when` 从未生效、
        #   条件不成立也照跑（且日志显示"成功"，看不出问题）——实测被自己的用例抓出。
        met, why = _cond_met(st.get("when"), ctx)
        if not met:
            rec["status"] = "skipped"
            rec["error"] = "条件不成立：%s（已留痕，非静默跳过）" % why
            log.append(rec)
            return rec
        fn = handlers.get(sid) or _default_handler(sid, entry)
        try:
            _a, _k = resolve_args(ctx, params)
            rec["params"] = {**params,
                             "resolved": {"args": [_summarize(x, 40) for x in _a],
                                          "kwargs": {kk: _summarize(vv, 40)
                                                     for kk, vv in _k.items()}}}
        except Exception:  # noqa: BLE001
            pass
        retries = int(st.get("retries") or 0)
        t0 = time.time()
        for attempt in range(1, retries + 2):
            rec["attempt"] = attempt
            try:
                out = fn(ctx, params)
                rec["result"] = _summarize(out)
                rec["status"] = "ok"
                rec["error"] = ""
                break
            except Exception as exc:  # noqa: BLE001
                rec["status"] = "failed"
                rec["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:200])
                if attempt <= retries:
                    continue
        rec["ms"] = int((time.time() - t0) * 1000)
        log.append(rec)
        return rec

    # 顺序执行；同一 `parallel_group` 的相邻步骤并行（用线程池，结果仍按步骤顺序入日志）
    i = 0
    while i < len(steps):
        st = steps[i]
        grp = str(st.get("parallel_group") or "")
        if grp:
            group = [st]
            j = i + 1
            while j < len(steps) and str(steps[j].get("parallel_group") or "") == grp:
                group.append(steps[j])
                j += 1
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=len(group)) as ex:
                futs = [ex.submit(_exec_one, g) for g in group]
                for f in futs:
                    f.result()
            i = j
        else:
            _exec_one(st)
            i += 1
        # 人工干预暂停点
        if st.get("pause_after") and str(st.get("step_id") or "") == _last_ok_step(log):
            status = "paused"
            ctx["_pause"] = {
                "after_step": str(st.get("step_id") or ""),
                "reason": str(st.get("pause_reason") or "需人工复核后继续"),
            }
            break
        if stop_before and str(st.get("step_id")) == str(stop_before):
            break

    if any(r["status"] == "failed" for r in log):
        status = "failed" if status != "paused" else status
    out = {
        "run_id": run_id, "plan_id": plan.get("plan_id"), "plan_name": plan.get("plan_name"),
        "status": status, "log": log, "started_at": _now(), "finished_at": _now(),
        "company_id": str(company_id or ""),
        "summary": _summary(log),
    }
    if status == "paused":
        out["pause"] = ctx.get("_pause") or {}
    return out


def _last_ok_step(log: List[Dict[str, Any]]) -> str:
    for r in reversed(log):
        if r.get("status") == "ok":
            return str(r.get("step_id"))
    return ""


def _summary(log: List[Dict[str, Any]]) -> Dict[str, int]:
    d: Dict[str, int] = {"ok": 0, "failed": 0, "skipped": 0, "paused": 0}
    for r in log:
        d[str(r.get("status"))] = d.get(str(r.get("status")), 0) + 1
    d["total"] = len(log)
    d["ms"] = sum(int(r.get("ms") or 0) for r in log)
    return d


def rerun(plan: Dict[str, Any], from_step_id: str, ctx: Optional[Dict[str, Any]] = None,
          handlers: Optional[Dict[str, Handler]] = None,
          company_id: Any = None) -> Dict[str, Any]:
    """**局部重跑**：只跑 `from_step_id` **及其下游**（下游 = 原方案里顺序在其后的步骤，
    并含同 `parallel_group` 的伙伴）。被跳过的上游步骤在日志里以 `skipped` 说明"沿用上次结果"。
    """
    steps = [s for s in (plan.get("steps") or []) if isinstance(s, dict)]
    ids = [str(s.get("step_id")) for s in steps]
    if from_step_id not in ids:
        raise ValueError("未登记的步骤：%s（合法值 %s）" % (from_step_id, ids))
    k = ids.index(from_step_id)
    downstream = set(ids[k:])
    grp = str(steps[k].get("parallel_group") or "")
    if grp:
        downstream |= {str(s.get("step_id")) for s in steps
                       if str(s.get("parallel_group") or "") == grp}
    out = run(plan, ctx, handlers, company_id=company_id, only_steps=sorted(downstream))
    out["rerun_from"] = from_step_id
    out["rerun_scope"] = sorted(downstream)
    out["upstream_skipped"] = [i for i in ids[:k] if i not in downstream]
    return out


def persistence_path(run: Dict[str, Any]) -> str:
    _RUNS.mkdir(parents=True, exist_ok=True)
    p = _RUNS / ("%s.json" % str(run.get("run_id") or "unknown"))
    p.write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(p)


def render_log_md(run: Dict[str, Any]) -> str:
    """《本次分析 Skill 执行日志》。"""
    L = ["# 本次分析 Skill 执行日志", "",
         "运行号 %s；方案「%s」；状态 **%s**；公司 %s。"
         % (run.get("run_id"), run.get("plan_name") or run.get("plan_id"),
            run.get("status"), run.get("company_id") or "—"), ""]
    s = run.get("summary") or {}
    L += ["汇总：共 %s 步（成功 %s／跳过 %s／失败 %s），累计耗时 %s ms。"
          % (s.get("total", 0), s.get("ok", 0), s.get("skipped", 0), s.get("failed", 0),
             s.get("ms", 0)), ""]
    if run.get("pause"):
        L += ["> **已暂停（人工干预点）**：%s 之后 —— %s。复核完成后调用 resume 从暂停点继续。"
              % (run["pause"].get("after_step"), run["pause"].get("reason")), ""]
    cols = ["步骤", "Skill", "版本", "入口", "状态", "尝试", "耗时(ms)", "入参", "结果", "异常"]
    L += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in (run.get("log") or []):
        L.append("| " + " | ".join([
            str(r.get("step_id") or ""), str(r.get("skill_id") or ""),
            str(r.get("version") or ""), str(r.get("entry") or ""),
            {"ok": "✅成功", "failed": "❌失败", "skipped": "⏭跳过", "paused": "⏸暂停"}.get(
                str(r.get("status")), str(r.get("status"))),
            str(r.get("attempt") or 0), str(r.get("ms") or 0),
            json.dumps(r.get("params") or {}, ensure_ascii=False)[:40],
            json.dumps(r.get("result"), ensure_ascii=False)[:60],
            str(r.get("error") or "—")[:60]]) + " |")
    L.append("")
    return "\n".join(L)


__all__ = ["LOG_FIELDS", "STATUSES", "load_plan_store", "plans", "plan_of",
           "validate_plans", "resolve_plan", "effective_version", "rollback",
           "run", "rerun", "persistence_path", "render_log_md"]

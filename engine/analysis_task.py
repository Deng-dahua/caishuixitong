"""P0-4 一键稽查分析任务 —— **任务层**（8 步 / 5 状态 / 可取消 / 可重试 / 可追溯）。

★ 层级边界（本模块**只做任务层**，绝不重写引擎）::

    任务层（本模块）      8 步、5 状态、取消/重试/超时、项目↔作业链接
    业务层                `main._launch_analysis_task` → `main._run_analysis_thread`
    引擎层（唯一收敛点）    `main._execute_tax_risk_analysis` → `engine.pipeline._run_analyze`
    作业流水（落盘权威）    `engine/analysis_jobs.py`（本模块只读写它，**不另立注册表**）
    运行态（实时进度）      `main._analysis_tasks`（本模块只读；取消时**只置旗标**）
    资料层                `engine/document_service`（P0-2）/ `engine/project_service`（P0-1）

★ 为什么不另立一套进度与状态：
    引擎已在上报 `current_step`(1–7) / `progress` / `current_module`（`engine/pipeline.py`
    的 `_report`/`_module`）。本模块**不重算、不猜测**，只按**声明式映射**把引擎事实翻译成
    任务层事实；映射表 `ENGINE_STEP_TO_TASK` 是**唯一处**，闸门断言其单调（见 tests）。

★ 取消的语义（**如实声明，不夸大**）：
    引擎无法被硬中断 —— `engine/pipeline.py` 的 `_report`/`_module` 对
    `progress_callback` 的异常是 `try/except: pass`，回调里抛异常会被吞掉。
    因此取消 = ①置旗标（`cancel_requested`）②引擎收尾时**丢弃结果**（`main._run_analysis_thread`
    的写回处已加守卫）③作业终态记 `cancelled`。**取消后本次结果永不被采用**；
    引擎线程会自然收尾（不吃新作业的并发额度：旗标期间内存态仍是 `running`，并发闸门照旧拦住）。
    该边界写入交付报告的「未完成/风险」，不粉饰。
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ══════════════════════════════════════════════════════════════════════════
# ① 8 步模型（★ 唯一权威：新增/改名只改这里一处）
# ══════════════════════════════════════════════════════════════════════════
#: `(key, 中文名, 说明)`。步号 = 元组下标 + 1（**1 基**，与前端展示一致）。
TASK_STEPS: Tuple[Tuple[str, str, str], ...] = (
    ("readiness", "校验资料完整性", "检查项目下资料是否齐备；无资料不发车"),
    ("parse", "解析未解析文件", "对尚未解析的资料执行解析（已解析的不重跑）"),
    ("normalize", "数据标准化", "把解析结果映射到标准字段（35 个）"),
    ("quality", "数据质量检查", "必填/金额/期间/重复/借贷/勾稽六类校验"),
    ("rules", "规则扫描", "红线与已验证规则逐条匹配"),
    ("score", "风险评分", "按等级与证据强度评分"),
    ("findings", "生成风险发现", "生成风险事项、证据链与反证"),
    ("report", "生成报告草稿", "编制报告草稿与工作底稿"),
)

STEP_CN: Dict[str, str] = {k: name for k, name, _d in TASK_STEPS}


def step_count() -> int:
    return len(TASK_STEPS)


def step_of_no(no: Any) -> Dict[str, Any]:
    """步号(1 基) → 步定义；越界钳到 `[1, len]`（**不返回 None**，避免前端空窗）。"""
    n = _as_int(no, default=1)
    n = max(1, min(n, len(TASK_STEPS)))
    key, name, desc = TASK_STEPS[n - 1]
    return {"no": n, "key": key, "name": name, "desc": desc}


#: 引擎步骤号 → 任务步号（★ 唯一映射处）。
#: 左侧 = `engine/pipeline.py` `_report(..., step=N)` 的 N（该文件的**上报顺序**实测为
#: 1,2,3,4,6,5,7 —— 按文件行号 614/1543/2215/2767/2813/4569/5888）。
#: 右侧 = 任务 8 步（`TASK_STEPS` 下标 + 1）。
#: ★ 映射后任务步号严格递增（2,3,4,5,6,7,8）⇒ 前端可单调推进；
#:   闸门 `tests/test_analysis_task_api.py::TaskStepMapTests` 断言该单调性 ——
#:   引擎上线顺序一旦变化，映射必须同步改，**不允许静默错位**。
ENGINE_STEP_TO_TASK: Dict[int, int] = {
    0: 1,   # 引擎未开始 ⇒ 任务仍在第 1 步（校验资料完整性）
    1: 2,   # 引擎①资料扫描/解析        ⇒ 任务②解析未解析文件
    2: 3,   # 引擎②目标实体识别         ⇒ 任务③数据标准化
    3: 4,   # 引擎③域分析（含数据校验） ⇒ 任务④数据质量检查
    4: 5,   # 引擎④规则引擎+链驱动      ⇒ 任务⑤规则扫描
    6: 6,   # 引擎⑥行业对标/Phase4综合  ⇒ 任务⑥风险评分
    5: 7,   # 引擎⑤方法论噪声过滤       ⇒ 任务⑦生成风险发现
    7: 8,   # 引擎⑦正式报告输出         ⇒ 任务⑧生成报告草稿
}

#: 引擎**上报顺序**（与 `ENGINE_STEP_TO_TASK` 的键一一对应，供单调性断言用）。
#: ★ 这是对 `engine/pipeline.py` 的**事实记录**，不是本模块发明的顺序。
ENGINE_REPORT_ORDER: Tuple[int, ...] = (1, 2, 3, 4, 6, 5, 7)

# ══════════════════════════════════════════════════════════════════════════
# ② 5 状态模型（★ 唯一权威）
# ══════════════════════════════════════════════════════════════════════════
PENDING = "PENDING"
RUNNING = "RUNNING"
SUCCESS = "SUCCESS"
FAILED = "FAILED"
CANCELLED = "CANCELLED"

#: 任务状态（★ 唯一权威：新增一态只加这里一处）
TASK_STATUSES: Tuple[str, ...] = (PENDING, RUNNING, SUCCESS, FAILED, CANCELLED)

STATUS_CN: Dict[str, str] = {
    PENDING: "排队中",
    RUNNING: "执行中",
    SUCCESS: "已完成",
    FAILED: "执行失败",
    CANCELLED: "已取消",
}

#: 终局状态（不再变化）
TASK_TERMINAL: Tuple[str, ...] = (SUCCESS, FAILED, CANCELLED)

#: 可重试的终局（**只有这两种**：完成的不该重试，取消/失败才需要）
RETRYABLE: Tuple[str, ...] = (FAILED, CANCELLED)

#: 运行态（`main._analysis_tasks[task_id]["status"]`，权威在 main）→ 任务状态。
#: ★ 唯一映射处。`deleted` 是"报告已删除"（`purge_company_analysis_artifacts` 置的），
#:   语义是"本次结果已作废" ⇒ 归入 `CANCELLED`（**不归 FAILED**：它不是执行出错）。
RUNTIME_TO_TASK: Dict[str, str] = {
    "running": RUNNING,
    "done": SUCCESS,
    "error": FAILED,
    "blocked": FAILED,      # 主体一致性拦截 = 主动拒绝出报告，对用户即"没出报告"
    "cancelled": CANCELLED,
    "deleted": CANCELLED,
}

#: 默认超时（秒）。超过即按"超时取消"处理（见 `TIMEOUT_NOTE`）。
DEFAULT_TIMEOUT_SECONDS = 3600

#: ⚠ 超时**按取消处理**（而非失败）的口径说明 —— 面向界面与报告，双方一致。
TIMEOUT_NOTE = ("执行超时：已请求中止，本次结果不予采用（可重试）。"
                "引擎无法被硬中断，其线程会自然收尾。")


class AnalysisTaskError(Exception):
    """任务层错误（`status` 为 HTTP 语义状态码，由 API 层转 `HTTPException`）。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = int(status)


def _as_task_error(exc: Exception, default_status: int = 400) -> AnalysisTaskError:
    """把下游 Service 的业务异常统一转成任务层异常（**边界唯一转换处**）。

    ★ 为什么必须转：API 层只捕 `AnalysisTaskError`；下游 `ProjectError`（P0-1）/
      `DocumentError`（P0-2）若原样穿透就变成 **500** —— 与"跨租户返回 404"的口径
      直接冲突。实测已踩过这一类（P0-2 的 `ProjectError` 穿透 ⇒ 跨租户 500）。
    """
    st = getattr(exc, "status", None)
    msg = str(getattr(exc, "message", None) or exc)
    return AnalysisTaskError(msg, int(st) if st else default_status)


def _get_project(project_id: Any, session: Any, *, engine=None) -> Dict[str, Any]:
    """取项目（可见性由 P0-1 权威判定）＋ 统一错误转换。"""
    from engine import project_service as PSVC            # noqa: PLC0415
    try:
        return PSVC.get_project(project_id, session, engine=engine,
                                with_members=False, with_logs=False)
    except PSVC.ProjectError as exc:
        raise _as_task_error(exc) from exc


# ══════════════════════════════════════════════════════════════════════════
# ③ 项目 ↔ 作业 链接（append-only；**只存"别处没有"的那条事实**）
# ══════════════════════════════════════════════════════════════════════════
#: 为什么单独存：作业流水（`analysis_jobs`）是**业务侧**产物，它按 `company_id` 组织；
#: "这次分析属于哪个稽查项目""是哪次失败作业的重试"是**任务层**的独有事实，
#: 放进业务流水会污染其口径，另开一张 SQLite 表则为一个字段建表。
#: 故：append-only 小文件 + 唯一权威在本模块（**新增一类链接 = 加一行数据，不改逻辑**）。
_LINK_LOCK = threading.RLock()


def links_path() -> Path:
    """链接文件路径（延迟取 `DATA_DIR`：它在 `runtime_storage` import 时固化）。"""
    from runtime_storage import DATA_DIR                 # noqa: PLC0415
    return Path(DATA_DIR) / "analysis_task_links.jsonl"


def register_link(job_id: str, project_id: Any, *, retry_of: str = "",
                  created_by: Any = None) -> Dict[str, Any]:
    """登记一条"作业 ← 项目"链接。返回写入的行（失败抛 `AnalysisTaskError`）。"""
    row = {"job_id": str(job_id or ""), "project_id": _as_int(project_id, default=0),
           "retry_of": str(retry_of or ""),
           "created_by": ("" if created_by is None else str(created_by))}
    if not row["job_id"]:
        raise AnalysisTaskError("作业 id 不能为空", 500)
    p = links_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with _LINK_LOCK:
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:                             # noqa: BLE001
        raise AnalysisTaskError("登记项目↔作业链接失败：%s" % exc, 500) from exc
    return row


def _read_links() -> List[Dict[str, Any]]:
    """顺序读出全部链接（坏行**计数留痕到 stderr**，不静默丢弃也不静默当空）。"""
    p = links_path()
    if not p.exists():
        return []
    out: List[Dict[str, Any]] = []
    bad = 0
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as exc:                             # noqa: BLE001
        _warn("读取项目↔作业链接失败：%s" % exc)
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:                                # noqa: BLE001
            bad += 1
            continue
        if isinstance(o, dict):
            out.append(o)
        else:
            bad += 1
    if bad:
        _warn("项目↔作业链接有 %d 行无法解析（已跳过）" % bad)
    return out


def link_of(job_id: Any) -> Optional[Dict[str, Any]]:
    """取某作业的链接（同 id 多条时**最后一条胜出**，与 append-only 语义一致）。"""
    want = str(job_id or "")
    hit: Optional[Dict[str, Any]] = None
    for r in _read_links():
        if str(r.get("job_id") or "") == want:
            hit = r
    return hit


def jobs_of_project(project_id: Any) -> List[Dict[str, Any]]:
    """某项目下的全部链接（按**首次**登记顺序；同 id **先折叠再过滤**，最后一次胜出）。

    ★ 顺序不可颠倒：必须先按 job_id 折叠、再按 project_id 过滤。
      反过来的话，一个作业若换过项目（数据修正场景），会**同时**出现在两个项目的历史里
      （实测：单元测试抓到 —— `jobs_of_project(旧项目)` 仍能查到它）。
    """
    want = _as_int(project_id, default=-1)
    order: List[str] = []
    best: Dict[str, Dict[str, Any]] = {}
    for r in _read_links():
        jid = str(r.get("job_id") or "")
        if not jid:
            continue
        if jid not in best:
            order.append(jid)
        best[jid] = r
    return [best[j] for j in order
            if _as_int(best[j].get("project_id"), default=-2) == want]


# ══════════════════════════════════════════════════════════════════════════
# ④ 资料完整性（任务第 1 步；**引擎之前**的发车闸门）
# ══════════════════════════════════════════════════════════════════════════
def preflight(project_id: Any, session: Any, *, engine=None) -> Dict[str, Any]:
    """校验资料完整性。返回 `{ok, total, unparsed, parsed, by_category_cn, message}`。

    ★ 判据只有一条且**不猜**：项目下**一份资料都没有** ⇒ `ok=False`（不发车）。
      为什么不做"必查资料齐备度"判定作为**阻断**条件：那属于**报告层**的判断
      （`enterprise_report` 的 material_readiness，含业态剔除口径），在这里重算等于
      另立一套口径；故本步只报**事实计数**，齐备度结论仍由报告层给出。
    """
    from engine import document_service as DSVC           # noqa: PLC0415
    try:
        page = DSVC.list_documents(project_id, session, engine=engine,
                                   page=1, page_size=1)
        total = int(page.get("total") or 0)
        unparsed = 0
        if total:
            unparsed = int(DSVC.list_documents(
                project_id, session, engine=engine,
                parse_status="pending", page=1, page_size=1).get("total") or 0)
    except DSVC.DocumentError as exc:
        raise _as_task_error(exc) from exc
    out = {
        "ok": total > 0,
        "total": total,
        "unparsed": unparsed,
        "parsed": max(0, total - unparsed),
        "by_category_cn": dict(page.get("category_counts_cn") or {}),
    }
    out["message"] = ("项目下共 %d 份资料（待解析 %d 份）" % (total, unparsed)
                      if total else "项目下没有任何资料，无法发起稽查分析")
    return out


# ══════════════════════════════════════════════════════════════════════════
# ⑤ 发起 / 查询 / 取消 / 重试
# ══════════════════════════════════════════════════════════════════════════
def launch(project_id: Any, session: Any, *, force: bool = False,
           retry_of: str = "", engine=None, request: Any = None) -> Dict[str, Any]:
    """发起一次稽查分析任务（**项目 → 账套 → 既有唯一后台主流程**）。

    收敛路径：本函数 → `main._launch_analysis_task` → `main._run_analysis_thread`
    → `main._execute_tax_risk_analysis` → `engine.pipeline._run_analyze`（架构红线，不绕）。
    """
    proj = _get_project(project_id, session, engine=engine)
    pid = int(proj["id"])
    company_id = _as_int(proj.get("company_id"), default=0)
    if company_id <= 0:
        # ★ 2026-10-15 账套退役：不再拒绝 ⇒ 自动绑定内部账套（用户不感知）
        from engine.project_service import ensure_company_for_project as _ensure   # noqa: PLC0415
        company_id = _ensure(session, proj, engine=engine, request=request)
    _guard_project_status(proj)
    pf = preflight(pid, session, engine=engine)
    if not pf["ok"]:
        raise AnalysisTaskError(pf["message"], 400)

    import main as _main                                  # noqa: PLC0415
    res = _main._launch_analysis_task(                     # noqa: SLF001
        company_id, getattr(session, "user_id", None),
        trigger="project", force=bool(force),
    )
    if not res or not res.get("ok"):
        raise AnalysisTaskError(str((res or {}).get("message") or "启动分析失败"), 409)
    job_id = str(res.get("task_id") or "")
    reused = bool(res.get("reused"))
    # 并发复用时**不写链接**：它不是一次新作业，链接已存在（避免同 id 两条链接）。
    if job_id and not reused:
        register_link(job_id, pid, retry_of=retry_of,
                      created_by=getattr(session, "user_id", None))
    return {
        "ok": True,
        "job_id": job_id,
        "reused": reused,
        "message": str(res.get("message") or "分析已启动"),
        "project_id": pid,
        "project_name": str(proj.get("name") or ""),
        "company_id": company_id,
        "preflight": pf,
        "status": PENDING,
        "status_cn": STATUS_CN[PENDING],
    }


def get(job_id: Any, session: Any, *, engine=None, request: Any = None,
        commit_timeout: bool = True) -> Dict[str, Any]:
    """取任务详情（**融合**：落盘作业流水 + 内存运行态 + 任务层链接）。

    ★ 两侧各有其权威：落盘流水（重启后仍可查）与内存运行态（毫秒级进度）。
      本函数只做**融合与翻译**，不产生第三种事实。

    ★ `commit_timeout=True`（默认）时，**超时/孤儿**判定会落一次终态（幂等且有据）：
      · 仍在跑且超时 ⇒ 置取消旗标（终态由引擎线程 finally 登记，唯一写者）；
      · 无运行态且超时（服务重启后的孤儿作业）⇒ 本函数登记 `error`
        （"服务重启中断"）—— 否则它会**永远停在"执行中"**（假象）。
      列表接口一律传 `commit_timeout=False`（读操作不得有副作用）。
    """
    from engine.analysis_jobs import get_job as _job_of, status_cn as _job_status_cn
    jid = str(job_id or "")
    if not jid:
        raise AnalysisTaskError("作业 id 不能为空", 400)
    link = link_of(jid)
    persisted = _job_of(jid)
    runtime = _runtime(jid)
    if not persisted and not runtime:
        raise AnalysisTaskError("作业不存在", 404)
    _authorize(session, link, company_id=((persisted or {}).get("company_id")
                                          or runtime.get("company_id")))
    started_at = str((persisted or {}).get("started_at")
                     or _epoch_to_iso(runtime.get("started_at")))
    finished_at = str((persisted or {}).get("finished_at") or "")
    progress = _as_int(runtime.get("progress"), default=0)
    cur_step = _as_int(runtime.get("current_step"), default=0)
    module = str(runtime.get("current_module") or "")

    cancel_requested = bool(runtime.get("cancel_requested"))
    timeout_s = _timeout_seconds()
    elapsed = _elapsed_seconds(runtime.get("started_at"), started_at, finished_at)
    timed_out = False
    terminal_now = _is_terminal(persisted, runtime)
    if (not terminal_now) and elapsed is not None and elapsed > timeout_s:
        timed_out = True
        if commit_timeout:
            if runtime:
                _request_cancel(jid)      # 超时 ⇒ 请求中止（结果不予采用）
            else:
                _heal_orphan(jid, persisted, timeout_s)
                persisted = _job_of(jid)
                terminal_now = True
        cancel_requested = cancel_requested or bool(_runtime(jid).get("cancel_requested"))

    status = _task_status(persisted=persisted, runtime=runtime,
                          cancel_requested=cancel_requested, timed_out=timed_out)
    reached = ENGINE_STEP_TO_TASK.get(cur_step, 1)
    out = {
        "job_id": jid,
        "project_id": _as_int((link or {}).get("project_id"), default=0),
        "company_id": _as_int((persisted or {}).get("company_id")
                              or runtime.get("company_id"), default=0),
        "status": status,
        "status_cn": STATUS_CN.get(status, status),
        "engine_status": str((persisted or {}).get("status") or runtime.get("status") or ""),
        "engine_status_cn": _job_status_cn((persisted or {}).get("status")
                                           or runtime.get("status")),
        "progress": 100 if status == SUCCESS else max(0, min(progress, 100)),
        "current_step": reached,
        "current_step_name": step_of_no(reached)["name"],
        "current_module": module,
        "steps": _build_steps(reached, status),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": (persisted or {}).get("duration_ms"),
        "elapsed_seconds": elapsed,
        "timeout_seconds": timeout_s,
        "timed_out": timed_out,
        "cancel_requested": cancel_requested,
        # 取消已生效但**引擎线程尚未收尾** ⇒ 如实标注（不假装已经停了）
        "cancel_pending": bool(cancel_requested and not terminal_now),
        "trigger": str((persisted or {}).get("trigger") or ""),
        "trigger_cn": str((persisted or {}).get("trigger_cn") or ""),
        "retry_of": str((link or {}).get("retry_of") or ""),
        "findings_count": (persisted or {}).get("findings_count"),
        "overall_level": str((persisted or {}).get("overall_level") or ""),
        "report_doc_no": str((persisted or {}).get("report_doc_no") or ""),
        "error": _task_error(persisted=persisted, runtime=runtime,
                             status=status, timed_out=timed_out),
        "message": _task_message(status=status, runtime=runtime, timed_out=timed_out,
                                 persisted=persisted),
        "can_cancel": status == RUNNING,
        "can_retry": status in RETRYABLE,
        "retryable_statuses": list(RETRYABLE),
    }
    return out


def list_for_project(project_id: Any, session: Any, *, limit: Any = 50,
                     engine=None) -> Dict[str, Any]:
    """某项目的任务历史（**倒序**，最新在前）。"""
    proj = _get_project(project_id, session, engine=engine)
    pid = int(proj["id"])
    links = jobs_of_project(pid)
    try:
        top = max(1, min(int(limit), 200))
    except Exception:                                    # noqa: BLE001
        top = 50
    items: List[Dict[str, Any]] = []
    # 只读列表：不做超时提交（避免 GET 产生副作用），超时仅**如实标注**
    for lk in links:
        try:
            items.append(get(lk.get("job_id"), session, engine=engine,
                             commit_timeout=False))
        except AnalysisTaskError as exc:
            if exc.status == 404:
                continue            # 流水被删（账套purge）⇒ 跳过，不算历史
            raise
    items.sort(key=lambda x: (str(x.get("started_at") or ""),
                              str(x.get("job_id") or "")), reverse=True)
    return {"project_id": pid, "project_name": str(proj.get("name") or ""),
            "total": len(items), "jobs": items[:top]}


def cancel(job_id: Any, session: Any, *, engine=None) -> Dict[str, Any]:
    """取消任务。返回取消后的详情（**幂等**：已终局 ⇒ 只回详情并说明）。

    ★ 两条路径，都必须有唯一写者：
      ① 内存中仍在跑 ⇒ 置旗标（终态由引擎线程的 finally 登记，**唯一写者**）；
      ② 内存中已无（服务重启后的孤儿作业）⇒ 由本函数登记终态
         （线程已不存在，不可能双写）——这同时根治"重启后作业永远停在执行中"。
    """
    from engine.analysis_jobs import get_job as _job_of
    jid = str(job_id or "")
    if not jid:
        raise AnalysisTaskError("作业 id 不能为空", 400)
    link = link_of(jid)
    persisted = _job_of(jid)
    runtime = _runtime(jid)
    if not persisted and not runtime:
        raise AnalysisTaskError("作业不存在", 404)
    _authorize(session, link, company_id=((persisted or {}).get("company_id")
                                          or runtime.get("company_id")))
    if runtime and not _is_terminal(persisted, runtime):
        # ① 仍在跑 ⇒ 置旗标（终态由引擎线程 finally 登记，**唯一写者**）
        if not runtime.get("cancel_requested"):
            with _main_lock():
                live = _runtime_maybe(jid)
                if isinstance(live, dict):
                    live["cancel_requested"] = True
                    live["cancel_requested_by"] = str(getattr(session, "user_id", ""))
            _audit("job.cancel", jid, persisted, runtime,
                   "用户取消分析任务（结果不予采用）")
        out = get(jid, session, engine=engine)
        out["cancel_accepted"] = True
        return out
    # ② 已终局 ⇒ **幂等但如实**：不覆盖既成事实（否则 API 的"已取消"对不上流水的 "done"）
    if _is_terminal(persisted, runtime):
        out = get(jid, session, engine=engine)
        out["cancel_accepted"] = False
        out["reason"] = "作业已结束（%s），取消未生效" % out["status_cn"]
        return out
    # ③ 无内存运行态且无终态（服务重启后的孤儿作业）⇒ 由本函数登记 cancelled
    from engine.analysis_jobs import job_finished as _jf
    _jf(jid, "cancelled", company_id=(persisted or {}).get("company_id"),
        error_message="服务重启后取消（作业已无运行态）")
    _audit("job.cancel", jid, persisted, runtime,
           "取消服务重启后残留的运行中作业")
    out = get(jid, session, engine=engine)
    out["cancel_accepted"] = True
    return out


def delete_job(job_id: Any, session: Any, *, engine=None) -> Dict[str, Any]:
    """★ 2026-10-15 删除一条分析任务的**记录**（历史列表清理）。

    边界（如实）：
      · **运行中任务不可删**（须先取消；后端拦截 + 前端禁选双保险）；
      · 只删任务流水与项目链接（analysis_jobs.jsonl / analysis_task_links.jsonl，
        经既有权威原语），**不动**分析结果/报告/资料（各有专属删除出口）；
      · 审计 job.delete。"""
    from engine.analysis_jobs import (                                 # noqa: PLC0415
        delete_job_records as _del_rows, get_job as _job_of)
    jid = str(job_id or "")
    if not jid:
        raise AnalysisTaskError("作业 id 不能为空", 400)
    link = link_of(jid)
    persisted = _job_of(jid)
    runtime = _runtime(jid)
    if not persisted and not runtime:
        raise AnalysisTaskError("作业不存在", 404)
    _authorize(session, link, company_id=((persisted or {}).get("company_id")))
    if runtime and not _is_terminal(persisted, runtime):
        raise AnalysisTaskError("任务仍在运行中，请先取消再删除", 409)
    removed_rows = _del_rows(jid)
    removed_links = _delete_link_rows(jid)
    _audit("job.delete", jid, persisted, runtime,
           "删除分析任务记录（流水 %d 行、链接 %d 条；结果与报告不受影响）"
           % (removed_rows, removed_links), request=None)
    return {"ok": True, "job_id": jid,
            "removed_rows": removed_rows, "removed_links": removed_links}


def _delete_link_rows(job_id: str) -> int:
    """从 analysis_task_links.jsonl 删除某作业的链接行（同权威原语口径）。"""
    import json as _json                        # noqa: PLC0415
    p = links_path()
    with _LINK_LOCK:
        if not p.exists():
            return 0
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(_json.loads(line))
            except Exception:                    # noqa: BLE001 — 坏行原样保留（不静默丢）
                rows.append({"__raw__": line})
        keep = [r for r in rows if str(r.get("job_id") or "") != str(job_id or "")]
        removed = len(rows) - len(keep)
        if removed:
            clean = [r for r in keep if not r.get("__raw__")]
            raws = [r["__raw__"] for r in keep if r.get("__raw__")]
            nl = chr(10)
            data = "".join((_json.dumps(r, ensure_ascii=False) + nl) for r in clean) \
                 + "".join((r + nl) for r in raws)
            p.write_text(data, encoding="utf-8")
        return removed


def retry(job_id: Any, session: Any, *, engine=None, request: Any = None) -> Dict[str, Any]:
    """重试一次**失败或已取消**的作业（新建一次作业，不回改原作业）。"""
    current = get(job_id, session, engine=engine)
    if current["status"] not in RETRYABLE:
        raise AnalysisTaskError(
            "仅「执行失败」或「已取消」的作业可重试（当前：%s）" % current["status_cn"], 400)
    pid = _as_int(current.get("project_id"), default=0)
    if pid <= 0:
        raise AnalysisTaskError("该作业未关联稽查项目，无法按项目重试", 400)
    out = launch(pid, session, force=True, retry_of=str(job_id),
                 engine=engine, request=request)
    _audit("job.retry", str(out.get("job_id")), {"company_id": out.get("company_id")},
           {}, "重试作业 %s（原状态：%s）" % (job_id, current["status_cn"]),
           request=request)
    out["retry_of"] = str(job_id)
    return out


def metadata() -> Dict[str, Any]:
    """任务层字典（供前端，**不在前端硬编码中文名/步名**）。"""
    from engine.analysis_jobs import JOB_TRIGGERS, trigger_cn, TERMINAL_STATUSES
    return {
        "steps": [dict(step_of_no(i + 1)) for i in range(len(TASK_STEPS))],
        "statuses": [{"value": s, "label": STATUS_CN[s]} for s in TASK_STATUSES],
        "terminal_statuses": list(TASK_TERMINAL),
        "retryable_statuses": list(RETRYABLE),
        "runtime_to_task": dict(RUNTIME_TO_TASK),
        "engine_step_to_task": dict(ENGINE_STEP_TO_TASK),
        "triggers": [{"value": t, "label": trigger_cn(t)} for t in JOB_TRIGGERS],
        "job_terminal_statuses": list(TERMINAL_STATUSES),
        "timeout_seconds": _timeout_seconds(),
        "timeout_note": TIMEOUT_NOTE,
        "cancel_semantics": (
            "软取消：置取消旗标 ⇒ 引擎收尾时丢弃结果 ⇒ 作业终态记「已取消」。"
            "引擎无法被硬中断，其线程会自然收尾；取消期间不释放并发额度。"),
        "layers": {
            "task": "engine/analysis_task.py（本模块）",
            "engine": "main._execute_tax_risk_analysis → engine.pipeline._run_analyze（唯一收敛点）",
            "ledger": "engine/analysis_jobs.py（作业流水唯一权威）",
        },
    }


# ══════════════════════════════════════════════════════════════════════════
# 内部工具
# ══════════════════════════════════════════════════════════════════════════
def _as_int(v: Any, *, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:                                    # noqa: BLE001
        return default


def _warn(msg: str) -> None:
    """留痕（绝不静默）。"""
    try:
        import sys as _sys
        print("[analysis-task] %s" % msg, file=_sys.stderr, flush=True)
    except Exception:                                    # noqa: BLE001
        pass


def _timeout_seconds() -> int:
    """超时秒数（可用 `ANALYSIS_JOB_TIMEOUT_SECONDS` 覆盖；非法值回默认，**不静默当 0**）。"""
    raw = os.environ.get("ANALYSIS_JOB_TIMEOUT_SECONDS")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_TIMEOUT_SECONDS
    try:
        n = int(str(raw).strip())
    except Exception:                                    # noqa: BLE001
        _warn("ANALYSIS_JOB_TIMEOUT_SECONDS 非法（%r），按默认 %d 秒"
              % (raw, DEFAULT_TIMEOUT_SECONDS))
        return DEFAULT_TIMEOUT_SECONDS
    return n if n > 0 else DEFAULT_TIMEOUT_SECONDS


def _guard_project_status(proj: Dict[str, Any]) -> None:
    """项目状态闸门：**已归档**的项目不得发起分析（状态机语义，单一判据）。"""
    st = str(proj.get("status") or "")
    if st == "archived":
        raise AnalysisTaskError("项目已归档，无法发起稽查分析；请先迁移到其他状态", 400)
    if st == "reported":
        raise AnalysisTaskError("项目已出报告，如需重算请先迁移到「分析中」", 400)


def _main_module():
    import main as _main                                 # noqa: PLC0415
    return _main


def _runtime(job_id: str) -> Dict[str, Any]:
    """读内存运行态（**只读快照**）。"""
    m = _main_module()
    lock = getattr(m, "_analysis_lock", None)
    tasks = getattr(m, "_analysis_tasks", None)
    if lock is None or tasks is None:
        return {}
    with lock:
        t = tasks.get(str(job_id))
        return dict(t) if isinstance(t, dict) else {}


def _runtime_maybe(job_id: str) -> Optional[Dict[str, Any]]:
    """拿到内存运行态的**可变引用**（未持有或非 dict ⇒ `None`）。

    ★ 调用方必须已持有 `main._analysis_lock`（`threading.Lock` 不可重入）。
    """
    m = _main_module()
    tasks = getattr(m, "_analysis_tasks", None)
    if tasks is None:
        return None
    t = tasks.get(str(job_id))
    return t if isinstance(t, dict) else None


class _MainLock:
    def __init__(self) -> None:
        self._lock = None

    def __enter__(self):
        self._lock = getattr(_main_module(), "_analysis_lock", None)
        return self._lock.__enter__() if self._lock is not None else None

    def __exit__(self, *a):
        return self._lock.__exit__(*a) if self._lock is not None else False


def _main_lock() -> _MainLock:
    return _MainLock()


def _request_cancel(job_id: str) -> None:
    """请求取消（置旗标）。**幂等、不加审计**（审计只在用户显式取消时写）。"""
    m = _main_module()
    lock = getattr(m, "_analysis_lock", None)
    tasks = getattr(m, "_analysis_tasks", None)
    if lock is None or tasks is None:
        return
    with lock:
        t = tasks.get(job_id)
        if isinstance(t, dict) and not t.get("cancel_requested"):
            t["cancel_requested"] = True
            t["cancel_requested_by"] = "timeout"
            _warn("作业 %s 超过超时阈值，已请求中止（结果不予采用）" % job_id)


def _epoch_to_iso(epoch: Any) -> str:
    """epoch 秒 → 本地 ISO 字符串（取不到 ⇒ 空串，**不猜**）。"""
    try:
        from datetime import datetime
        return datetime.fromtimestamp(float(epoch)).isoformat(timespec="seconds")
    except Exception:                                    # noqa: BLE001
        return ""


def _elapsed_seconds(epoch: Any, started_iso: str, finished_iso: str) -> Optional[int]:
    """已耗时（秒）。优先内存 epoch（毫秒级）；否则用 ISO 差值；都取不到 ⇒ `None`。"""
    try:
        if epoch is not None:
            import time as _t
            return max(0, int(_t.time() - float(epoch)))
    except Exception:                                    # noqa: BLE001
        pass
    try:
        from datetime import datetime
        if started_iso:
            a = datetime.fromisoformat(str(started_iso))
            b = (datetime.fromisoformat(str(finished_iso)) if finished_iso
                 else datetime.now())
            return max(0, int((b - a).total_seconds()))
    except Exception:                                    # noqa: BLE001
        pass
    return None


def _is_terminal(persisted: Optional[Dict[str, Any]],
                 runtime: Dict[str, Any]) -> bool:
    """作业是否已终局（内存非 `running` 且非空 ⇒ 终局；否则看落盘终态行）。"""
    rt = str((runtime or {}).get("status") or "")
    if rt and rt != "running":
        return True
    return bool(persisted and persisted.get("is_terminal"))


def _heal_orphan(job_id: str, persisted: Optional[Dict[str, Any]],
                 timeout_s: int) -> None:
    """登记**孤儿作业**终态（服务重启后内存无运行态、落盘却无终态）。

    ★ 为什么记 `error` 而不是 `cancelled`：它**不是用户取消**，而是被重启打断 ——
      事实就是"没跑完"，如实记失败并写明原因。幂等（`job_finished` 已幂等）。
    """
    from engine.analysis_jobs import job_finished as _jf
    _jf(job_id, "error", company_id=(persisted or {}).get("company_id"),
        error_message="服务重启导致作业中断（超过 %d 秒仍无终态且无运行态）" % timeout_s)


def _task_status(*, persisted: Optional[Dict[str, Any]], runtime: Dict[str, Any],
                 cancel_requested: bool, timed_out: bool) -> str:
    """任务状态判定（**唯一判据处**）。

    取值优先级（顺序不可颠倒）：
      ① **已终局** ⇒ 用终局事实（★ 取消**不得**覆盖终局：对已完成的作业点取消，
         若被覆盖成 `CANCELLED`，就对不上作业流水里那条 `done` —— 两种事实一个名字）；
      ② 取消/超时 ⇒ `CANCELLED`；
      ③ 运行态 `running` ⇒ `PENDING`（尚未进入第 1 步）或 `RUNNING`；
      ④ 落盘说在跑而内存无记录（重启后）⇒ 如实 `RUNNING`（由超时看门狗兜底）。
    """
    if _is_terminal(persisted, runtime):
        st = str(runtime.get("status") or (persisted or {}).get("status") or "")
        mapped = RUNTIME_TO_TASK.get(st)
        if mapped is None:
            _warn("未知终局状态 %r（按 FAILED 处理）" % st)
            return FAILED
        return mapped
    if cancel_requested or timed_out:
        return CANCELLED
    rt = str((runtime or {}).get("status") or "")
    if rt == "running":
        if _as_int(runtime.get("progress"), default=0) == 0 \
                and _as_int(runtime.get("current_step"), default=0) == 0:
            return PENDING
        return RUNNING
    if rt:
        _warn("未知运行态 %r（按 RUNNING 处理）" % rt)
    return RUNNING


def _task_error(*, persisted: Optional[Dict[str, Any]], runtime: Dict[str, Any],
                status: str, timed_out: bool) -> str:
    if timed_out:
        return TIMEOUT_NOTE
    if status == CANCELLED:
        if (runtime or {}).get("cancel_requested_by") == "timeout":
            return TIMEOUT_NOTE
        return ""
    if status == FAILED:
        return str(runtime.get("error") or (persisted or {}).get("error_message") or "")
    return ""


def _task_message(*, status: str, runtime: Dict[str, Any],
                  timed_out: bool, persisted: Optional[Dict[str, Any]]) -> str:
    if timed_out:
        return "执行超时，已请求中止"
    if status == CANCELLED:
        return "已取消（本次结果不予采用）"
    msg = str((runtime or {}).get("message") or "")
    if msg:
        return msg
    return str((persisted or {}).get("status_cn") or STATUS_CN.get(status, status))


def _build_steps(reached: int, status: str) -> List[Dict[str, Any]]:
    """构造 8 步清单。`reached` = 已到达的任务步号。"""
    out: List[Dict[str, Any]] = []
    for i in range(1, len(TASK_STEPS) + 1):
        base = dict(step_of_no(i))
        if i < reached:
            base["status"] = "done"
        elif i == reached:
            if status == SUCCESS:
                base["status"] = "done"
            elif status == FAILED:
                base["status"] = "failed"
            elif status == CANCELLED:
                base["status"] = "cancelled"
            else:
                base["status"] = "active"
        else:
            base["status"] = "pending"
        out.append(base)
    return out


def _authorize(session: Any, link: Optional[Dict[str, Any]],
               company_id: Any = None) -> None:
    """可见性校验：作业所属项目对当前会话可见 ⇒ 放行；否则 **404**（不泄露存在性）。

    ★ 无链接时退回**账套可见性**判定（历史作业或非项目入口发起的老作业），
      绝不因此拒绝 —— 否则老作业全变 404（同一概念的两种来源必须都认）。
    """
    if link:
        _get_project(link.get("project_id"), session)
        return
    cid = _as_int(company_id, default=0)
    if cid > 0 and session is not None \
            and hasattr(session, "can_access_company") \
            and not session.can_access_company(cid):
        raise AnalysisTaskError("作业不存在或无权访问", 404)
    if not _can_see_any(session):
        raise AnalysisTaskError("作业不存在或无权访问", 404)


def _can_see_any(session: Any) -> bool:
    """会话是否至少可见一个账套（admin 恒真）。"""
    if session is None:
        return False
    if getattr(session, "is_admin", False):
        return True
    return bool(getattr(session, "allowed_company_ids", None))


def _audit(action: str, target: str, persisted: Any, runtime: Any,
           detail: str, request: Any = None) -> None:
    """写业务留痕（**不吞异常**：`record()` 自身不抛、不静默）。"""
    from engine.audit_trail import record as _record     # noqa: PLC0415
    cid = None
    for src in (persisted, runtime):
        if isinstance(src, dict) and src.get("company_id") is not None:
            cid = src.get("company_id")
            break
    _record(action, target=str(target), company_id=cid, detail=detail, request=request)


__all__ = [
    "TASK_STEPS", "STEP_CN", "step_count", "step_of_no",
    "ENGINE_STEP_TO_TASK", "ENGINE_REPORT_ORDER",
    "PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED",
    "TASK_STATUSES", "STATUS_CN", "TASK_TERMINAL", "RETRYABLE", "RUNTIME_TO_TASK",
    "DEFAULT_TIMEOUT_SECONDS", "TIMEOUT_NOTE", "AnalysisTaskError",
    "links_path", "register_link", "link_of", "jobs_of_project",
    "preflight", "launch", "get", "list_for_project", "cancel", "retry", "delete_job", "metadata",
]

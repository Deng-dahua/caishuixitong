# -*- coding: utf-8 -*-
"""分析作业流水（Analysis Job Ledger）—— 每一次「一键分析」的**作业实体**。

## 为什么要有「作业」

改造前，一次「一键分析」只留下两样东西：内存里的 `_analysis_tasks[task_id]`
（进程重启即丢、无回读）与事后那份**报告缓存**。于是下面这些问题**全部无处可查**：

| 问题 | 改造前 | 本模块落点 |
|---|---|---|
| 这次分析是谁发起的？ | 只有内存 `user_id`，重启即丢 | `started_by` |
| 什么时候开始、算了多久？ | 只有内存 `time.time()` | `started_at` / `finished_at` / `duration_ms` |
| 是强制重算，还是复用了上次？ | 只有内存标记 | `trigger` / `force` / `reused_from` |
| 失败在哪一步？ | 只有 `current_module` 快照 | `error_step` / `error_message` |
| 这份报告是哪一次分析产出的？ | **没有任何回指** | `job_id`（报告台账 `analysis_id` 指回本行） |
| 重启服务后还查得到吗？ | 查不到（404） | 落盘、可回读 |

## 铁律

- **作业身份只有一处权威：本模块**。任何"这次分析是谁/多久/什么触发"的问题，
  都只能从这里取，不得在别处另写一份。
- **事件式追加（append-only）**：`started` 与 `finished` 各追加一行，**不覆盖**。
  一次分析**恰好一行 `started`**、**恰好一行 `finished`**：终态登记**幂等**，
  重复登记被忽略并留痕 —— 因为作业的终点是唯一的（`_run_analysis_thread` 的
  `finally` 是唯一终态点），若允许覆盖，"同一作业两个终点"就会成为常态，
  掩盖真正的双写缺陷。异常路径**也必须**补终态，否则作业永远停在"执行中"，
  重启后按 `task_id` 查状态会给出错误的"仍在跑"。
- **每一行都自带 `company_id`**（含 `finished` 行）：删除按行过滤才彻底 ——
  否则只能删掉 `started` 行、在磁盘上留下终态残行（本模块首次验收实测到：
  删了 2 行、剩 4 行），直接违反"删了就是真删了"。
- **时长唯一从流水推导**（`finished_at - started_at`），**不信任内存里的计时**。
  时间戳一律 `runtime_storage.now_cst()`（北京时间唯一权威）。
- **落盘路径唯一权威 `runtime_storage.DATA_DIR`**（受 `APP_DATA_DIR` 覆盖）。
  ⚠ 不得写成 `_ROOT / "data"` —— 隔离实例（测试用 `APP_DATA_DIR=<临时目录>`
  起独立进程）会因此越界写真实项目（`tests/test_company_api.py` 有实测事故记录）。
- **写失败绝不静默**：任何一次追加失败都要留痕到 stderr（`[analysis-jobs] ...`）；
  失败**不得**让分析主流程失败（台账是旁路证据，不是主链），但必须能被看见。
- **读侧与存储解耦**：所有存取出入三个私有原语
  （`_append_row` / `_read_rows` / `_rewrite_rows`）。将来迁 SQLite 只换这三个，
  上层（`main.py` / 报告台账 / 前端接口）**一行不动**。
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

#: 作业流水结构版本（结构一变就 +1，便于旧流水可读性判断）
JOB_SCHEMA_VERSION = 1

#: 作业终态（★ 唯一权威：新增一态只加这里一处）
TERMINAL_STATUSES: Tuple[str, ...] = ("done", "error", "blocked")

#: 非终态（作业正在进行；读侧据此判断"是否仍在跑"）
RUNNING_STATUS = "running"

#: 触发方式（★ 唯一权威：新增一类只加这里一处）
JOB_TRIGGERS: Tuple[str, ...] = (
    "manual",       # 用户点「一键分析」
    "force",        # 用户点「重新计算」（force=1，跳过增量复用）
    "resume",       # 失败断点续跑（analyze-resume）
    "incremental",  # 资料与规则均未变化 ⇒ 增量复用（未真正重算）
    "auto_upload",  # 上传资料后自动重跑（前端与 manual 共用同一接口，需显式传参才能区分）
)

_TRIGGER_CN: Dict[str, str] = {
    "manual": "手动发起",
    "force": "强制重算",
    "resume": "失败断点续跑",
    "incremental": "增量复用",
    "auto_upload": "上传后自动重跑",
}

_STATUS_CN: Dict[str, str] = {
    "running": "执行中",
    "done": "已完成",
    "error": "执行失败",
    "blocked": "已拦截（未出报告）",
}

#: 作业行事件类型（★ 唯一权威）
JOB_EVENTS: Tuple[str, ...] = ("started", "finished")

#: 模块级写锁（进程内串行化 append/rewrite；RLock 以容纳自检里的重入）
_LOCK = threading.RLock()

#: 最近一次写入错误（供诊断/闸门读取；正常为 None）
_LAST_ERROR: Optional[str] = None

#: 仅供闸门/测试：置为 True 时写失败直接抛异常（用于反向验证"写失败不静默"）
RAISE_ON_WRITE_ERROR = False


# ── 路径（唯一权威：runtime_storage.DATA_DIR）─────────────────────────────────

def jobs_path() -> Path:
    """作业流水文件路径。

    ★ 延迟导入 `runtime_storage`：`DATA_DIR` 在**该模块 import 时**由
      `APP_DATA_DIR` 环境变量固化，故必须在使用时取，不能在本模块顶层固化。
    """
    from runtime_storage import DATA_DIR
    return Path(DATA_DIR) / "analysis_jobs.jsonl"


# ── 私有存储原语（★ 迁 SQLite 时只换这三个函数）────────────────────────────────

def _append_row(row: Dict[str, Any]) -> None:
    """追加一行（append-only）。"""
    p = jobs_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_rows() -> List[Dict[str, Any]]:
    """顺序读出全部行；坏行**计数留痕**（不静默丢弃）。"""
    global _LAST_ERROR
    p = jobs_path()
    if not p.exists():
        return []
    rows: List[Dict[str, Any]] = []
    bad = 0
    try:
        with _LOCK:
            text = p.read_text(encoding="utf-8")
    except Exception as exc:                     # noqa: BLE001
        _LAST_ERROR = "读取作业流水失败：%s" % exc
        _log(_LAST_ERROR)
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:                        # noqa: BLE001
            bad += 1
            continue
        if isinstance(o, dict):
            rows.append(o)
        else:
            bad += 1
    if bad:
        _LAST_ERROR = "作业流水有 %d 行无法解析（已跳过，未静默当作空）" % bad
        _log(_LAST_ERROR)
    return rows


def _rewrite_rows(rows: Iterable[Dict[str, Any]]) -> None:
    """整表重写（仅用于**删除**类维护操作）。

    ★ 原子替换走唯一实现 `runtime_storage.atomic_write_text`
      （fsync + `os.replace` + 失败清理临时文件）。
      **本模块不得出现任何删除调用** —— 闸门 `check_delete_exits` 曾抓到本函数
      "顺手 `os.unlink(tmp)`" 并报 ERROR（实测，2026-10-09）。"谁能删临时文件"
      必须落在已声明的出口里，各写一份就是多一个删除出口。
    """
    from runtime_storage import atomic_write_text
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    with _LOCK:
        atomic_write_text(jobs_path(), text)


# ── 留痕（绝不静默）──────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    try:
        import sys as _sys
        print("[analysis-jobs] %s" % msg, file=_sys.stderr, flush=True)
    except Exception:                            # noqa: BLE001
        pass


def _guard(fn, what: str):
    """执行一次写入；失败留痕（并可选抛出，供闸门反向验证）。"""
    global _LAST_ERROR
    try:
        out = fn()
        _LAST_ERROR = None
        return out
    except Exception as exc:                     # noqa: BLE001
        _LAST_ERROR = "%s失败：%s" % (what, exc)
        _log(_LAST_ERROR)
        if RAISE_ON_WRITE_ERROR:
            raise
        return None


def last_error() -> Optional[str]:
    """最近一次写入/读取错误（正常为 None）。"""
    return _LAST_ERROR


# ── 时间（唯一权威 runtime_storage.now_cst）────────────────────────────────────

def _now() -> str:
    from runtime_storage import now_cst
    return now_cst()


def _parse_iso(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s))
    except Exception:                            # noqa: BLE001
        return None


def _duration_ms(started_at: Any, finished_at: Any) -> Optional[int]:
    """时长**唯一从流水推导**；任一时间戳不可解析 ⇒ None（不猜）。"""
    a, b = _parse_iso(started_at), _parse_iso(finished_at)
    if a is None or b is None:
        return None
    return int((b - a).total_seconds() * 1000)


def _cid(company_id: Any) -> str:
    return str(company_id if company_id is not None else "")


# ── 写侧：作业生命周期 ────────────────────────────────────────────────────────

def job_started(company_id: Any, job_id: str, started_by: Any = None,
                trigger: str = "manual", force: bool = False,
                started_at: Optional[str] = None,
                data_fingerprint: str = "",
                rules_fingerprint: str = "") -> Optional[Dict[str, Any]]:
    """登记一次分析的**开始**。返回写入的行（失败返回 None，并已留痕）。

    `job_id` 即 `_analysis_tasks` 的 `task_id`（12 位 hex）—— 两者**同一个**，
    不另造 ID，避免"作业身份"与"任务身份"两套编号对不上。
    """
    trig = str(trigger or "manual")
    if trig not in JOB_TRIGGERS:                 # ★ 不静默丢弃：未知触发记原值 + 留痕
        _log("未知触发方式 %r（合法值 %s），按原值记录" % (trig, list(JOB_TRIGGERS)))
    row = {
        "schema": JOB_SCHEMA_VERSION,
        "event": "started",
        "job_id": str(job_id),
        "company_id": _cid(company_id),
        "started_by": ("" if started_by is None else str(started_by)),
        "started_at": started_at or _now(),
        "trigger": trig,
        "trigger_cn": _TRIGGER_CN.get(trig, trig),
        "force": bool(force),
        "data_fingerprint": str(data_fingerprint or ""),
        "rules_fingerprint": str(rules_fingerprint or ""),
    }
    return _guard(lambda: (_append_row(row), row)[1], "登记作业开始")


def job_finished(job_id: str, status: str, company_id: Any = None,
                 finished_at: Optional[str] = None,
                 error_step: str = "", error_message: str = "",
                 findings_count: Optional[int] = None,
                 overall_level: str = "",
                 report_doc_no: str = "",
                 reused_from: str = "",
                 block_detail: str = "") -> Optional[Dict[str, Any]]:
    """登记一次分析的**终态**（done / error / blocked）。返回写入的行。

    ★ 终态必须**恰好登记一次**（异常路径也要走到这里），否则作业永远停在
      "执行中"，重启后按 `task_id` 查状态就会给出错误的"仍在跑"。
    ★ **幂等**：该作业已有终态 ⇒ **忽略重复登记**并留痕（不静默）。为什么不是覆盖：
      作业的终点是唯一的（`_run_analysis_thread` 的 finally 是唯一终态点）；
      允许覆盖会让"同一作业两个终点"成为常态，掩盖真正的双写缺陷。
    ★ **每一行都自带 `company_id`**（含 finished 行）：删除按行过滤才彻底 ——
      否则 `remove_company_jobs` 只能删掉 started 行、在磁盘上留下终态残行
      （本模块首次验收实测到：删了 2 行、剩 4 行）。
    """
    st = str(status or "")
    if st not in TERMINAL_STATUSES:
        _log("非终态 %r 被当作终态登记（合法值 %s）" % (st, list(TERMINAL_STATUSES)))
    prev = _last_terminal(str(job_id))
    if prev is not None:
        _log("作业 %s 已有终态 %s，忽略重复登记 %s" % (job_id, prev.get("status"), st))
        return None
    row = {
        "schema": JOB_SCHEMA_VERSION,
        "event": "finished",
        "job_id": str(job_id),
        "company_id": _cid(company_id) if company_id is not None else _cid(
            (_started_of(str(job_id)) or {}).get("company_id")),
        "status": st,
        "status_cn": _STATUS_CN.get(st, st),
        "finished_at": finished_at or _now(),
        "error_step": str(error_step or ""),
        "error_message": str(error_message or "")[:2000],
        "findings_count": (None if findings_count is None else int(findings_count)),
        "overall_level": str(overall_level or ""),
        "report_doc_no": str(report_doc_no or ""),
        "reused_from": str(reused_from or ""),
        "block_detail": str(block_detail or "")[:500],
    }
    return _guard(lambda: (_append_row(row), row)[1], "登记作业终态")


# ── 读侧：折叠（最后一次 finished 胜出）────────────────────────────────────────

def _started_of(job_id: str) -> Optional[Dict[str, Any]]:
    """取某作业**最早**的 `started` 行（无则 None）。"""
    best: Optional[Dict[str, Any]] = None
    for r in _read_rows():
        if str(r.get("job_id") or "") != str(job_id) or str(r.get("event") or "") != "started":
            continue
        if best is None or str(r.get("started_at") or "") < str(best.get("started_at") or ""):
            best = r
    return best


def _last_terminal(job_id: str) -> Optional[Dict[str, Any]]:
    """取某作业**最后**的 `finished` 行（无则 None）。"""
    last: Optional[Dict[str, Any]] = None
    for r in _read_rows():
        if str(r.get("job_id") or "") == str(job_id) and str(r.get("event") or "") == "finished":
            last = r
    return last


def _collapse(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把事件流折叠成**作业视图**：一个 `job_id` 一行。

    - 起始信息（`company_id`/`started_by`/`started_at`/`trigger`/`force`）取**最早**
      的 `started`（同一次分析追加了多条 started 时，最早的才是真正起点）；
    - 终态信息取**最后**的 `finished`（"最后一次胜出"，与追加语义一致）；
    - `duration_ms` **由流水时间戳推导**，不取内存计时。
    """
    order: List[str] = []
    started: Dict[str, Dict[str, Any]] = {}
    finished: Dict[str, Dict[str, Any]] = {}
    counts: Dict[str, int] = {}
    for r in rows:
        jid = str(r.get("job_id") or "")
        if not jid:
            continue
        ev = str(r.get("event") or "")
        if jid not in order:
            order.append(jid)
            counts[jid] = 0
        counts[jid] += 1
        if ev == "started":
            prev = started.get(jid)
            if prev is None or str(r.get("started_at") or "") < str(prev.get("started_at") or ""):
                started[jid] = r
        elif ev == "finished":
            finished[jid] = r                        # 后者覆盖前者 ⇒ 最后一次胜出
    out: List[Dict[str, Any]] = []
    for jid in order:
        s = started.get(jid) or {}
        f = finished.get(jid) or {}
        started_at = s.get("started_at") or ""
        finished_at = f.get("finished_at") or ""
        out.append({
            "job_id": jid,
            "company_id": _cid(s.get("company_id") or f.get("company_id")),
            "started_by": str(s.get("started_by") or ""),
            "started_at": str(started_at),
            "finished_at": str(finished_at),
            "duration_ms": _duration_ms(started_at, finished_at),
            "trigger": str(s.get("trigger") or ""),
            "trigger_cn": str(s.get("trigger_cn") or _TRIGGER_CN.get(str(s.get("trigger") or ""), "")),
            "force": bool(s.get("force")),
            "status": (str(f.get("status") or "") if f else RUNNING_STATUS),
            "status_cn": (str(f.get("status_cn") or "") if f
                          else _STATUS_CN.get(RUNNING_STATUS, RUNNING_STATUS)),
            "is_terminal": bool(f),
            "error_step": str(f.get("error_step") or ""),
            "error_message": str(f.get("error_message") or ""),
            "findings_count": f.get("findings_count"),
            "overall_level": str(f.get("overall_level") or ""),
            "report_doc_no": str(f.get("report_doc_no") or ""),
            "reused_from": str(f.get("reused_from") or ""),
            "block_detail": str(f.get("block_detail") or ""),
            "data_fingerprint": str(s.get("data_fingerprint") or ""),
            "rules_fingerprint": str(s.get("rules_fingerprint") or ""),
            "row_count": counts.get(jid, 0),
        })
    return out


def list_jobs(company_id: Any = None, limit: Optional[int] = None,
              status: Optional[str] = None) -> List[Dict[str, Any]]:
    """列出作业（按 `started_at` **倒序**，最新在前）。"""
    jobs = _collapse(_read_rows())
    if company_id is not None:
        want = _cid(company_id)
        jobs = [j for j in jobs if j.get("company_id") == want]
    if status:
        jobs = [j for j in jobs if j.get("status") == str(status)]
    jobs.sort(key=lambda j: (str(j.get("started_at") or ""), str(j.get("job_id") or "")),
              reverse=True)
    if limit is not None:
        jobs = jobs[: max(0, int(limit))]
    return jobs


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """取单个作业（重启后依然可查 —— 这正是本模块存在的理由）。"""
    want = str(job_id or "")
    for j in _collapse(_read_rows()):
        if j.get("job_id") == want:
            return j
    return None


def last_job(company_id: Any) -> Optional[Dict[str, Any]]:
    """取某企业**最近一次**作业。"""
    jobs = list_jobs(company_id=company_id, limit=1)
    return jobs[0] if jobs else None


def is_terminal(job_id: str) -> bool:
    j = get_job(job_id)
    return bool(j and j.get("is_terminal"))


# ── 维护（删除类，唯一权威在调用方：main.purge_company_analysis_artifacts）──────

def remove_company_jobs(company_id: Any) -> int:
    """删除某企业的**全部**作业行，返回删除的行数。

    ★ 只由 `main.purge_company_analysis_artifacts` 调用（删除账套的第 ⑩ 项）。
      "删了就是真删了"：这里用整表重写，删除后**读不到任何残留**。
    """
    want = _cid(company_id)
    rows = _read_rows()
    kept = [r for r in rows if _cid(r.get("company_id")) != want]
    removed = len(rows) - len(kept)
    if removed:
        _guard(lambda: _rewrite_rows(kept), "删除企业作业流水")
    return removed


def all_job_ids() -> List[str]:
    """全部作业 id（正序）。"""
    return [str(j.get("job_id")) for j in _collapse(_read_rows())]


# ── 自检（供闸门/验收脚本；返回问题清单，空列表 = 通过）──────────────────────────

def selfcheck(company_id: Any = None) -> List[str]:
    """流水**结构自检**：事件/状态/触发合法、每个 job 有起点、终态唯一、时长可推导。

    返回中文问题清单；**空列表 = 通过**。任何一条都必须能在真实流水上跑出问题，
    否则说明判据是假的（见验收脚本的反向验证）。
    """
    problems: List[str] = []
    rows = _read_rows()
    if company_id is not None:
        want = _cid(company_id)
        rows = [r for r in rows if _cid(r.get("company_id")) == want]
    started_at: Dict[str, str] = {}
    finished_cnt: Dict[str, int] = {}
    for i, r in enumerate(rows, 1):
        ev = str(r.get("event") or "")
        jid = str(r.get("job_id") or "")
        if ev not in JOB_EVENTS:
            problems.append("第 %d 行：未知事件 %r" % (i, ev))
        if not jid:
            problems.append("第 %d 行：缺少 job_id" % i)
            continue
        if not _cid(r.get("company_id")):
            problems.append("作业 %s 第 %d 行：缺少 company_id" % (jid, i))
        if ev == "started":
            if not str(r.get("started_at") or ""):
                problems.append("作业 %s：started 行缺少 started_at" % jid)
            if not str(r.get("started_by") or ""):
                problems.append("作业 %s：started 行缺少发起人 started_by" % jid)
            trig = str(r.get("trigger") or "")
            if trig not in JOB_TRIGGERS:
                problems.append("作业 %s：未知触发方式 %r" % (jid, trig))
            started_at.setdefault(jid, str(r.get("started_at") or ""))
        elif ev == "finished":
            finished_cnt[jid] = finished_cnt.get(jid, 0) + 1
            st = str(r.get("status") or "")
            if st not in TERMINAL_STATUSES:
                problems.append("作业 %s：非终态 %r 被记为 finished" % (jid, st))
            if not str(r.get("finished_at") or ""):
                problems.append("作业 %s：finished 行缺少 finished_at" % jid)
    for jid, cnt in finished_cnt.items():
        if cnt > 1:
            problems.append("作业 %s：出现 %d 条 finished（终态应恰好一次）" % (jid, cnt))
    for jid in finished_cnt:
        if jid not in started_at:
            problems.append("作业 %s：有终态但**没有起点**" % jid)
    for j in _collapse(rows):
        if j.get("is_terminal") and j.get("duration_ms") is None:
            problems.append("作业 %s：终态但时长无法从流水推导" % j.get("job_id"))
    return problems


__all__ = [
    "JOB_SCHEMA_VERSION", "TERMINAL_STATUSES", "RUNNING_STATUS", "JOB_TRIGGERS", "JOB_EVENTS",
    "jobs_path", "job_started", "job_finished",
    "list_jobs", "get_job", "last_job", "is_terminal", "remove_company_jobs",
    "all_job_ids", "selfcheck", "last_error", "RAISE_ON_WRITE_ERROR",
]

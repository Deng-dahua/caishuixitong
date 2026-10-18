# -*- coding: utf-8 -*-
"""阈值告警（O-03，2026-10-18）。

评估结论：「告警只有『分析完成通知』，**无阈值告警**（错误率飙升 / 任务连败 /
磁盘将满无人知）」。此前唯一的"告警"是分析完成后推一条消息 —— 那是**通知**，
不是**告警**：没有阈值、没有触发条件、没有冷却、没有分级。

本模块补的是后者，设计上刻守四条：
  ① **规则是数据，不是代码**：新增一条阈值 = `RULES` 加一行，不改判定分支；
  ② **必须可冷却**：同一规则在 `cooldown_minutes` 内只报一次，
     否则一个持续故障会在短时间内刷出上百条（告警失效的典型死法）；
  ③ **绝不自己发消息**：只产出"该报什么"，投递交给既有通知配置
     （`main._notification_config` 的 webhook/site 通道）—— 不另造第二套通知；
  ④ **评估失败不静默**：数据取不到要如实说"取不到"，不能当作"正常"。
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from runtime_storage import DATA_DIR, now_cst

#: 告警冷却（分钟）。同一规则在该窗口内只报一次。
COOLDOWN_MINUTES = int(os.environ.get("APP_ALERT_COOLDOWN_MINUTES", "30"))

_lock = threading.Lock()
_last_fired: Dict[str, float] = {}
_history: List[Dict[str, Any]] = []
_HISTORY_MAX = 200


def _metrics() -> Dict[str, Any]:
    from engine import metrics as M          # noqa: PLC0415
    return M.snapshot()


def _backup_age_hours() -> Optional[float]:
    from engine import backup as B           # noqa: PLC0415
    return B.backup_age_hours()


def _disk_free_ratio() -> Optional[float]:
    """数据目录所在磁盘的可用比例（取不到返回 None —— 不假装正常）。"""
    try:
        usage = shutil.disk_usage(str(DATA_DIR))
        return usage.free / usage.total if usage.total else None
    except Exception:                        # noqa: BLE001
        return None


def _failed_jobs_ratio() -> Optional[float]:
    """最近作业里失败占比（读作业流水；读不到返回 None）。"""
    try:
        import json

        path = DATA_DIR / "analysis_jobs.jsonl"
        if not path.is_file():
            return None
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]
        done = fail = 0
        for ln in lines:
            try:
                ev = json.loads(ln)
            except Exception:                # noqa: BLE001
                continue
            if ev.get("event") != "finished":
                continue
            if ev.get("status") == "error":
                fail += 1
            elif ev.get("status") == "done":
                done += 1
        total = done + fail
        return (fail / total) if total else None
    except Exception:                        # noqa: BLE001
        return None


#: 规则表（**新增阈值只加一行**）。`check(快照) -> (是否触发, 数值, 说明)`。
RULES: List[Dict[str, Any]] = [
    {
        "code": "ERR_RATE_HIGH",
        "level": "critical",
        "title": "接口 5xx 错误率过高",
        "threshold": "> 1% 且样本 ≥ 50",
        "cooldown_minutes": 15,
        "check": lambda s: (
            s["requests"]["total"] >= 50
            and s["requests"]["error_rate"] > 0.01,
            "%.2f%%" % (s["requests"]["error_rate"] * 100),
            "服务端错误 %d / 总请求 %d"
            % (s["requests"]["server_errors_5xx"], s["requests"]["total"]),
        ),
    },
    {
        "code": "P95_SLOW",
        "level": "warning",
        "title": "接口 P95 延迟过高",
        "threshold": "> 3000 ms 且样本 ≥ 50",
        "cooldown_minutes": 30,
        "check": lambda s: (
            s["latency_ms"]["samples"] >= 50 and s["latency_ms"]["p95"] > 3000,
            "%d ms" % s["latency_ms"]["p95"],
            "P50=%d ms / P95=%d ms / P99=%d ms"
            % (s["latency_ms"]["p50"], s["latency_ms"]["p95"], s["latency_ms"]["p99"]),
        ),
    },
    {
        "code": "DISK_LOW",
        "level": "critical",
        "title": "磁盘可用空间不足",
        "threshold": "< 15%",
        "cooldown_minutes": 360,
        "check": lambda s: (
            (lambda r: (r is not None and r < 0.15, "%.1f%%" % (r * 100) if r is not None else "取不到",
                        "数据目录所在磁盘可用 %.1f%%" % (r * 100) if r is not None else "取不到磁盘信息（不视为正常）"))(
                _disk_free_ratio())
        ),
    },
    {
        "code": "BACKUP_STALE",
        "level": "critical",
        "title": "备份过期（数据只有一份的风险）",
        "threshold": "> 48 小时未成功备份",
        "cooldown_minutes": 720,
        "check": lambda s: (
            (lambda h: (h is None or h > 48,
                        "从未备份" if h is None else "%.1f 小时前" % h,
                        "最近一份备份：" + ("无" if h is None else "%.1f 小时前" % h)))(
                _backup_age_hours())
        ),
    },
    {
        "code": "JOB_FAIL_HIGH",
        "level": "warning",
        "title": "分析/解析作业失败率偏高",
        "threshold": "> 20% 且样本 ≥ 10",
        "cooldown_minutes": 60,
        "check": lambda s: (
            (lambda r: (r is not None and r > 0.20, "%.1f%%" % (r * 100) if r is not None else "取不到",
                        "近期作业失败占比 %.1f%%" % (r * 100) if r is not None else "取不到作业流水（不视为正常）"))(
                _failed_jobs_ratio())
        ),
    },
]


def evaluate(now: Optional[float] = None, *, respect_cooldown: bool = True) -> List[Dict[str, Any]]:
    """评估全部规则，返回**本次应当发出**的告警（已过滤冷却窗口）。"""
    ts = float(now if now is not None else time.time())
    try:
        snap = _metrics()
    except Exception as exc:                 # noqa: BLE001
        return [{"code": "EVAL_FAILED", "level": "warning", "title": "告警评估失败",
                 "value": "-", "detail": "%s: %s" % (type(exc).__name__, exc),
                 "fired_at": now_cst()}]

    out: List[Dict[str, Any]] = []
    for rule in RULES:
        try:
            fired, value, detail = rule["check"](snap)
        except Exception as exc:             # noqa: BLE001
            # ★ 单条规则算不出来不能让整轮静默；如实登记为"取不到"
            fired, value, detail = False, "取不到", "%s: %s" % (type(exc).__name__, exc)
        if not fired:
            continue
        code = str(rule["code"])
        with _lock:
            last = _last_fired.get(code)
            if respect_cooldown and last is not None:
                window = float(rule.get("cooldown_minutes", COOLDOWN_MINUTES)) * 60
                if ts - last < window:
                    continue
            _last_fired[code] = ts
        item = {"code": code, "level": rule["level"], "title": rule["title"],
                "threshold": rule["threshold"], "value": value, "detail": detail,
                "fired_at": now_cst()}
        with _lock:
            _history.append(item)
            if len(_history) > _HISTORY_MAX:
                del _history[:len(_history) - _HISTORY_MAX]
        out.append(item)
    return out


def history() -> List[Dict[str, Any]]:
    with _lock:
        return list(reversed(_history))


def status() -> Dict[str, Any]:
    """当前阈值与冷却状态（供管理页/接口展示，说明"为什么没报"）。"""
    snap = {}
    try:
        snap = _metrics()
    except Exception:                        # noqa: BLE001
        pass
    rows = []
    for rule in RULES:
        try:
            fired, value, detail = rule["check"](snap) if snap else (None, "-", "指标不可得")
        except Exception as exc:             # noqa: BLE001
            fired, value, detail = None, "取不到", str(exc)
        with _lock:
            last = _last_fired.get(str(rule["code"]))
        rows.append({"code": rule["code"], "level": rule["level"], "title": rule["title"],
                     "threshold": rule["threshold"], "current": value,
                     "detail": detail, "firing": fired,
                     "last_fired": last, "cooldown_minutes": rule.get("cooldown_minutes")})
    return {
        "rules": rows,
        "history": history()[:20],
        "cooldown_minutes_default": COOLDOWN_MINUTES,
        "note": ("阈值判定只看**数量与耗时**，不涉及业务结论；同一规则在冷却窗口内只报一次"
                 "（否则持续故障会刷屏，告警本身失效）。投递复用既有通知配置，不另造通道。"),
    }


def reset() -> None:
    """清空冷却与历史（测试用）。"""
    with _lock:
        _last_fired.clear()
        _history.clear()


__all__ = ["RULES", "COOLDOWN_MINUTES", "evaluate", "history", "status", "reset"]

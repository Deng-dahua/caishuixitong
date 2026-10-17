# -*- coding: utf-8 -*-
"""进程内指标采集（O-02，2026-10-17）。

评估结论：「**零指标** —— 无 CPU/内存/QPS/延迟/错误率采集，无法回答
『能扛多少并发、哪里慢』」。阶段 8 的性能结论只能靠外部压测脚本临时得出，
线上出了慢请求也没有数据可查。

本模块只做**最小可用**的一套（不引入 Prometheus 依赖）：
  · `record_request(path, method, status, seconds)` —— 由中间件逐请求调用；
  · `snapshot()` —— 汇总 QPS/延迟分位/错误率/慢请求 Top N；
  · `prometheus_text()` —— `/metrics` 的文本格式（便于将来接采集器）。

★ 三条纪律
  ① **绝不阻塞、绝不抛错**：所有采集都在 try 里，出错只计数，不能让业务请求失败；
  ② 内存有上限：路径维度做归一化 + Top N 截断，避免高基数撑爆内存；
  ③ 只统计**数量与耗时**，不记录 URL 查询参数、不记录请求体（避免泄露敏感信息）。
"""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Tuple

#: 延迟环形缓冲（最近 N 个请求的耗时，秒）—— 用于算 P50/P95/P99
_RING = 8000
#: 每个路径保留的耗时样本上限
_PER_PATH_RING = 400
#: 报告里最多列多少个路径
_TOP = 25

_lock = threading.Lock()
_started_at = time.time()
_total = 0
_errors = 0                 # 5xx
_client_errors = 0          # 4xx
_by_status: Dict[int, int] = defaultdict(int)
_by_method: Dict[str, int] = defaultdict(int)
_by_path: Dict[str, Dict[str, Any]] = {}
_all_durations: Deque[float] = deque(maxlen=_RING)
_slowest: List[Tuple[float, str, str, int]] = []

#: 路径归一化：把数字/UUID 段替换成占位符，防高基数
_NUM = re.compile(r"/\d+(?=/|$)")
_UUID = re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def normalize_path(path: str) -> str:
    """归一化路径：**先剥掉查询串/锚点**，再把数字与 UUID 段替换成占位符。

    ★ 必须剥查询串（2026-10-17 实测踩到）：中间件传的是 `request.url.path`（本无查询串），
      但只要有调用方传了完整 URL，搜索词/身份证号就会进指标 ⇒ 既泄隐私又造成高基数。
      这条由 `tests/test_consent_and_metrics.py::test_metrics_never_records_query_string` 守护。
    """
    p = str(path or "")
    for sep in ("?", "#"):
        idx = p.find(sep)
        if idx >= 0:
            p = p[:idx]
    p = _UUID.sub("/{uuid}", p)
    p = _NUM.sub("/{n}", p)
    return p[:120]


def record_request(path: str, method: str, status: int, seconds: float) -> None:
    """记录一次请求。**任何异常都必须吞掉**（采集不能影响业务）。"""
    global _total, _errors, _client_errors
    try:
        key = normalize_path(path)
        with _lock:
            _total += 1
            if status >= 500:
                _errors += 1
            elif status >= 400:
                _client_errors += 1
            _by_status[int(status)] += 1
            _by_method[(method or "GET").upper()] += 1
            _all_durations.append(float(seconds))
            slot = _by_path.get(key)
            if slot is None:
                slot = _by_path[key] = {"count": 0, "errors": 0, "total_ms": 0.0,
                                        "max_ms": 0.0, "durations": deque(maxlen=_PER_PATH_RING)}
            slot["count"] += 1
            slot["total_ms"] += seconds * 1000.0
            slot["max_ms"] = max(slot["max_ms"], seconds * 1000.0)
            slot["durations"].append(float(seconds))
            if status >= 500:
                slot["errors"] += 1
            _slowest.append((float(seconds), method or "GET", key, int(status)))
            if len(_slowest) > 200:
                _slowest.sort(reverse=True)
                del _slowest[100:]
    except Exception:                                  # noqa: BLE001
        return


def _pct(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    idx = min(len(vals) - 1, max(0, int(round(q * (len(vals) - 1)))))
    return round(vals[idx] * 1000.0, 2)


def snapshot() -> Dict[str, Any]:
    """汇总当前指标（调用即返回副本，不做长时间持锁）。"""
    with _lock:
        total = _total
        errors = _errors
        client_errors = _client_errors
        by_status = dict(_by_status)
        by_method = dict(_by_method)
        durations = list(_all_durations)
        paths = {k: {"count": v["count"], "errors": v["errors"],
                     "avg_ms": round(v["total_ms"] / v["count"], 2) if v["count"] else 0.0,
                     "max_ms": round(v["max_ms"], 2),
                     "durations": list(v["durations"])}
                 for k, v in _by_path.items()}
        slow = sorted(_slowest, reverse=True)[:10]
    uptime = max(0.0, time.time() - _started_at)
    ranked = sorted(paths.items(), key=lambda kv: -kv[1]["count"])[:_TOP]
    return {
        "uptime_seconds": round(uptime, 1),
        "requests": {"total": total, "server_errors_5xx": errors,
                     "client_errors_4xx": client_errors,
                     "error_rate": round(errors / total, 4) if total else 0.0,
                     "qps": round(total / uptime, 2) if uptime > 0 else 0.0},
        "by_status": {str(k): v for k, v in sorted(by_status.items())},
        "by_method": by_method,
        "latency_ms": {
            "p50": _pct(durations, 0.50),
            "p95": _pct(durations, 0.95),
            "p99": _pct(durations, 0.99),
            "samples": len(durations),
        },
        "top_paths": [
            {"path": p, "count": v["count"], "avg_ms": v["avg_ms"], "max_ms": v["max_ms"],
             "errors": v["errors"],
             "p95_ms": _pct(v["durations"], 0.95)}
            for p, v in ranked
        ],
        "slowest": [{"seconds": round(s, 4), "method": m, "path": p, "status": st}
                    for s, m, p, st in slow],
        "note": ("只统计请求数量与耗时，**不记录查询参数与请求体**；"
                 "路径已归一化（数字段→{n}），避免高基数。"),
    }


def prometheus_text() -> str:
    """Prometheus 文本格式（便于将来接采集器；字段保持稳定）。"""
    s = snapshot()
    lines = [
        "# HELP app_requests_total 累计请求数",
        "# TYPE app_requests_total counter",
        "app_requests_total %d" % s["requests"]["total"],
        "# HELP app_errors_5xx_total 服务端错误数",
        "# TYPE app_errors_5xx_total counter",
        "app_errors_5xx_total %d" % s["requests"]["server_errors_5xx"],
        "# HELP app_uptime_seconds 进程运行时长",
        "# TYPE app_uptime_seconds gauge",
        "app_uptime_seconds %.1f" % s["uptime_seconds"],
        "# HELP app_latency_p50_ms 请求耗时 P50（毫秒）",
        "# TYPE app_latency_p50_ms gauge",
        "app_latency_p50_ms %.2f" % s["latency_ms"]["p50"],
        "# HELP app_latency_p95_ms 请求耗时 P95（毫秒）",
        "# TYPE app_latency_p95_ms gauge",
        "app_latency_p95_ms %.2f" % s["latency_ms"]["p95"],
    ]
    for item in s["top_paths"]:
        safe = item["path"].replace('"', "'")
        lines.append('app_path_requests_total{path="%s"} %d' % (safe, item["count"]))
        lines.append('app_path_latency_p95_ms{path="%s"} %.2f' % (safe, item["p95_ms"]))
    return "\n".join(lines) + "\n"


def reset() -> None:
    """清空计数（测试用）。"""
    global _total, _errors, _client_errors, _started_at
    with _lock:
        _total = 0
        _errors = 0
        _client_errors = 0
        _by_status.clear()
        _by_method.clear()
        _by_path.clear()
        _all_durations.clear()
        _slowest.clear()
        _started_at = time.time()


__all__ = ["record_request", "snapshot", "prometheus_text", "normalize_path", "reset"]

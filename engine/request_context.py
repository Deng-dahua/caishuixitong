# -*- coding: utf-8 -*-
"""请求关联 ID（O-04，2026-10-18）。

评估结论：「trace_id 集中在 main.py（11 处），多数 API 域 0 处 ⇒ 跨模块请求无法串联」。
那些 `trace_id` 其实是**业务字段**（报告/证据链的编号），不是"这一次 HTTP 请求"的关联 id。
两者不是一回事：业务 trace_id 跟着数据走，请求 id 跟着调用走。

本模块补的是后者，做三件事：
  ① 每个请求分配（或沿用调用方带来的）`X-Request-ID`，放到 `contextvars`；
  ② **日志自动带上它**（`TraceFilter`）⇒ 一次请求跨多个模块的日志可以 grep 到一起；
  ③ 响应头回传 ⇒ 用户报"刚才那个操作失败了"时，能凭这个 id 精确定位。

★ 为什么用 contextvars 而不是 threading.local：
  FastAPI/uvicorn 是 async，同一线程会并发处理多个请求，thread-local 会串味。

用法
----
    from engine.request_context import current_trace_id, set_trace_id
    _log.info("...")     # 日志里自动出现 [rid=ab12cd34]，无需手工拼
"""
from __future__ import annotations

import contextvars
import logging
import secrets
from typing import Optional

#: 当前请求的关联 id（async 安全）
_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
#: 响应头名（与业界惯例一致，便于反代/网关沿用）
HEADER = "X-Request-ID"


def new_trace_id() -> str:
    return secrets.token_hex(4)


def set_trace_id(value: Optional[str]) -> str:
    """设置当前请求 id（空则生成一个）。返回最终使用的值。"""
    tid = (value or "").strip()[:64] or new_trace_id()
    _trace_id.set(tid)
    return tid


def current_trace_id() -> str:
    return _trace_id.get() or ""


class TraceFilter(logging.Filter):
    """把当前请求 id 注入日志记录（`%(trace_id)s` 供格式串使用）。

    ★ 没有请求上下文时填 `-`，**不是空串** —— 否则日志格式里会出现 `[rid=]` 这种半截样子。
    """

    def filter(self, record: logging.LogRecord) -> bool:   # noqa: A003
        if not getattr(record, "trace_id", ""):
            record.trace_id = current_trace_id() or "-"
        return True


def install_log_filter(fmt_with_trace: str) -> None:
    """把 TraceFilter 与带 `%(trace_id)s` 的格式装到根 logger 的所有 handler。"""
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, TraceFilter) for f in handler.filters):
            handler.addFilter(TraceFilter())
        handler.setFormatter(logging.Formatter(fmt_with_trace))


__all__ = ["HEADER", "new_trace_id", "set_trace_id", "current_trace_id",
           "TraceFilter", "install_log_filter"]

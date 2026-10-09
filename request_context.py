"""Request-local identity used by model configuration lookups."""
from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional


_CURRENT_USER_ID: ContextVar[Optional[int]] = ContextVar(
    "caishuixitong_current_user_id",
    default=None,
)

#: 当前**分析作业** id（= `_analysis_tasks` 的 task_id），供 engine 层
#: （报告合规台账 `report_compliance.record_version`）把"这份报告是哪一次分析
#: 产出的"写进台账，实现**报告 ↔ 作业**单向回指。
#: ★ 与用户身份同机制、同生命周期：分析线程入口 `set`、`finally` 里 `reset`。
_CURRENT_JOB_ID: ContextVar[Optional[str]] = ContextVar(
    "caishuixitong_current_job_id",
    default=None,
)


def set_current_user_id(user_id: int) -> Token:
    return _CURRENT_USER_ID.set(int(user_id))


def reset_current_user_id(token: Token) -> None:
    _CURRENT_USER_ID.reset(token)


def get_current_user_id() -> Optional[int]:
    return _CURRENT_USER_ID.get()


def set_current_job_id(job_id: str) -> Token:
    return _CURRENT_JOB_ID.set(str(job_id))


def reset_current_job_id(token: Token) -> None:
    _CURRENT_JOB_ID.reset(token)


def get_current_job_id() -> Optional[str]:
    return _CURRENT_JOB_ID.get()

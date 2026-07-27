"""Request-local identity used by model configuration lookups."""
from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional


_CURRENT_USER_ID: ContextVar[Optional[int]] = ContextVar(
    "caishuixitong_current_user_id",
    default=None,
)


def set_current_user_id(user_id: int) -> Token:
    return _CURRENT_USER_ID.set(int(user_id))


def reset_current_user_id(token: Token) -> None:
    _CURRENT_USER_ID.reset(token)


def get_current_user_id() -> Optional[int]:
    return _CURRENT_USER_ID.get()

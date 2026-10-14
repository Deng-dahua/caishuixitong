# -*- coding: utf-8 -*-
"""S12-TODO-002：SQLite 忙/锁/只读类**瞬时**故障必须转 **503**（不是 500）。

背景（P0 验收遗留 ⑤）：50 并发写时 SQLite 抛
`attempt to write a readonly database` / `database is locked`，一路冒泡到全局处理器
⇒ 用户看到 500「服务器内部错误」（不可区分、不可重试）。修法：唯一判别 + 503 映射。

本测试同时锁住两件事：
  ① 判别函数只认「忙/锁/只读」类文本（不得把普通错误也当忙）；
  ② 全局处理器确实按判别结果分流（503 vs 500）。
"""
import asyncio
import sqlite3

import pytest

from database import is_db_busy_error


@pytest.mark.parametrize("msg", [
    "database is locked",
    "attempt to write a readonly database",
    "database table is locked",
    "sqlite_busy",
    "SQLITE_BUSY: database is locked",
])
def test_busy_error_recognized(msg):
    assert is_db_busy_error(sqlite3.OperationalError(msg)) is True


@pytest.mark.parametrize("msg", [
    "boom",
    "no such table: companies",
    "UNIQUE constraint failed",
    "",
])
def test_non_busy_error_not_recognized(msg):
    assert is_db_busy_error(sqlite3.OperationalError(msg)) is False


def test_global_handler_maps_busy_to_503_others_to_500():
    import main
    r_busy = asyncio.run(main.global_exception_handler(
        None, sqlite3.OperationalError("database is locked")))
    assert r_busy.status_code == 503
    body = r_busy.body.decode("utf-8")
    assert "服务繁忙" in body, body
    r_other = asyncio.run(main.global_exception_handler(None, ValueError("boom")))
    assert r_other.status_code == 500

# -*- coding: utf-8 -*-
"""S12-TODO-002 / R-3：数据库故障的**语义分流**（不是把所有 DB 错误都当"忙"）。

背景（P0 验收遗留 ⑤）：50 并发写时 SQLite 抛
`database is locked` / `attempt to write a readonly database`，一路冒泡到全局处理器
⇒ 用户看到 500「服务器内部错误」（不可区分、不可重试）。

★★ 2026-10-14（R-3）**语义收窄**——原实现把「只读」也算"忙"并统一回 503「请重试」，
   实测教训：隔离副本环境下 `/audit-logs` 首访 503 提示"请重试"，但根因是**数据文件不可写**
   （权限/挂载/占用）——**重试永远不会成功**，提示把人引向错误方向。故拆为：

     | 判别 | 典型文本 | 可重试 | 状态码 | 提示 |
     |---|---|---|---|---|
     | `is_db_busy_error`     | `database is locked` / `sqlite_busy` | 是 | **503** | 请重试 |
     | `is_db_readonly_error` | `attempt to write a readonly database` | **否** | **500** | 检查写权限/占用 |

本测试锁住三件事：
  ① 两个判别函数互不重叠（"只读"不得被认作"忙"）；
  ② 全局处理器按判别结果**分流状态码与文案**；
  ③ 普通错误既不算忙也不算只读。
"""
import asyncio
import sqlite3

import pytest

from database import is_db_busy_error, is_db_readonly_error


@pytest.mark.parametrize("msg", [
    "database is locked",
    "database table is locked",
    "sqlite_busy",
    "SQLITE_BUSY: database is locked",
])
def test_busy_error_recognized(msg):
    assert is_db_busy_error(sqlite3.OperationalError(msg)) is True


@pytest.mark.parametrize("msg", [
    "attempt to write a readonly database",
    "read-only database",
])
def test_readonly_is_readonly_not_busy(msg):
    """★ 只读必须归 `is_db_readonly_error`，**不得**再被"忙"认领。"""
    exc = sqlite3.OperationalError(msg)
    assert is_db_readonly_error(exc) is True
    assert is_db_busy_error(exc) is False


@pytest.mark.parametrize("msg", [
    "boom",
    "no such table: companies",
    "UNIQUE constraint failed",
    "",
])
def test_non_busy_non_readonly_not_recognized(msg):
    exc = sqlite3.OperationalError(msg)
    assert is_db_busy_error(exc) is False
    assert is_db_readonly_error(exc) is False


def test_global_handler_maps_busy_to_503_and_readonly_to_500():
    import main
    r_busy = asyncio.run(main.global_exception_handler(
        None, sqlite3.OperationalError("database is locked")))
    assert r_busy.status_code == 503
    assert "服务繁忙" in r_busy.body.decode("utf-8")

    r_ro = asyncio.run(main.global_exception_handler(
        None, sqlite3.OperationalError("attempt to write a readonly database")))
    assert r_ro.status_code == 500, "只读不得再回 503（重试无效）"
    ro_body = r_ro.body.decode("utf-8")
    assert "不可写" in ro_body and "重试无效" in ro_body

    r_other = asyncio.run(main.global_exception_handler(None, ValueError("boom")))
    assert r_other.status_code == 500

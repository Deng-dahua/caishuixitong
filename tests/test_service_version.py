# -*- coding: utf-8 -*-
"""R-1 / R-2 / R-3（2026-10-14）：
  ① 服务版本可见化（进程载入的代码 vs 磁盘当前代码）；
  ② 页面级 HTML 错误兜底（页面路径给 HTML，`/api/**` 保持 JSON）；
  ③ 数据库「忙/锁」（可重试 ⇒ 503）与「只读」（多半不可重试 ⇒ 500）语义拆分。

★ 为什么需要（本文件锁住的三次实测事故）
  · 前端静态文件每次请求从磁盘读 ⇒ 永远最新；Python 代码是进程启动时的快照。
    错配后的现象是「菜单是新的、点进去 `{"detail":"Not Found"}`」或「侧边栏少项」——
    看起来像 bug，实则只是**没重启服务**（此前要靠人肉比对进程启动时间 vs git 提交时间）。
  · 页面路径出错把 JSON 摊给用户（截图即此），应有 HTML + 处置动作。
  · `attempt to write a readonly database` 曾被归入 503「请重试」，但根因（权限/挂载只读）
    **重试无效** ⇒ 误导。
"""
import asyncio
import sqlite3

import pytest

from database import is_db_busy_error, is_db_readonly_error
from engine import runtime_version as RV
from error_pages_api import error_route, page_404_handler, render_page_error, wants_json


class _E(Exception):
    def __init__(self, detail="Not Found"):
        super().__init__(detail)
        self.detail = detail


class _Req:
    def __init__(self, path):
        self.url = type("U", (), {"path": path})()
        self.method = "GET"


# ── R-1 版本可见化 ────────────────────────────────────────────────────────
def test_boot_snapshot_shape():
    boot = RV.boot_snapshot()
    assert set(boot) >= {"stamp", "count", "booted_at", "pid", "newest_file"}
    assert boot["count"] > 0, "被监控的 Python 源文件不应为 0（否则判据失效）"
    assert boot["booted_at"], "启动时间不得为空（缺失 ≠ 0）"


def test_snapshot_covers_python_sources_only():
    """只盯 Python 源码：前端/CSS 更新**不需要**重启，算进去会制造误报。"""
    rels = [str(p.relative_to(RV.ROOT)).replace("\\", "/") for p in RV.monitor_files()]
    assert any(r == "main.py" for r in rels)
    assert any(r.startswith("engine/") for r in rels)
    assert not any(r.startswith("static/") for r in rels), "static/ 不得计入"
    assert not any(r.endswith(".html") or r.endswith(".css") for r in rels)


def test_staleness_false_when_boot_equals_disk(monkeypatch):
    snap = {"files": {"main.py": "aaa", "engine/x.py": "bbb"}, "stamp": "s1",
            "count": 2, "newest_mtime": 0.0, "newest_file": "main.py"}
    monkeypatch.setattr(RV, "_BOOT", snap)
    monkeypatch.setattr(RV, "snapshot", lambda: dict(snap))
    RV._DISK_CACHE["val"] = None
    info = RV.staleness(refresh=True)
    assert info["stale"] is False
    assert info["changed_count"] == 0
    assert RV.stale_hint(info) == ""


def test_staleness_detects_modified_added_deleted(monkeypatch):
    boot = {"files": {"main.py": "aaa", "engine/x.py": "bbb"}, "stamp": "s1",
            "count": 2, "newest_mtime": 0.0, "newest_file": "main.py"}
    disk = {"files": {"main.py": "ZZZ", "engine/new.py": "ccc"}, "stamp": "s2",
            "count": 2, "newest_mtime": 0.0, "newest_file": "engine/new.py"}
    monkeypatch.setattr(RV, "_BOOT", boot)
    monkeypatch.setattr(RV, "snapshot", lambda: dict(disk))
    RV._DISK_CACHE["val"] = None
    info = RV.staleness(refresh=True)
    assert info["stale"] is True
    changes = {x["file"]: x["change"] for x in info["changed_files"]}
    assert changes["main.py"] == "已修改"
    assert changes["engine/new.py"] == "新增"
    assert changes["engine/x.py"] == "已删除"
    hint = RV.stale_hint(info)
    assert "重启" in hint and "start8001.bat" in hint
    assert RV.boot_snapshot()["booted_at"] in hint, "提示须带启动时间（否则无法自证）"


def test_health_payload_shape():
    pay = RV.health_payload()
    assert set(pay) == {"code", "stale"}
    assert set(pay["stale"]) >= {"stale", "changed_count", "changed_files",
                                 "disk_stamp", "monitored_files"}
    assert isinstance(pay["stale"]["stale"], bool)


def test_healthz_exposes_version():
    import main
    pay = asyncio.run(main.healthz())
    assert pay["ok"] is True
    assert "booted_at" in pay["code"] and "stale" in pay["stale"]


# ── R-3 忙/锁 vs 只读 ────────────────────────────────────────────────────
@pytest.mark.parametrize("msg", ["database is locked", "database table is locked",
                                 "sqlite_busy", "SQLITE_BUSY: database is locked"])
def test_busy_recognized(msg):
    assert is_db_busy_error(sqlite3.OperationalError(msg)) is True


@pytest.mark.parametrize("msg", ["attempt to write a readonly database",
                                 "read-only database"])
def test_readonly_is_not_busy(msg):
    """★ 语义收窄：只读**不再**算"忙"（与"可重试"语义冲突）。"""
    exc = sqlite3.OperationalError(msg)
    assert is_db_readonly_error(exc) is True
    assert is_db_busy_error(exc) is False


@pytest.mark.parametrize("msg", ["readonly database", "attempt to write a readonly database"])
def test_readonly_recognized(msg):
    assert is_db_readonly_error(sqlite3.OperationalError(msg)) is True


@pytest.mark.parametrize("exc", [ValueError("boom"), sqlite3.OperationalError("no such table: x")])
def test_other_errors_are_neither(exc):
    assert is_db_busy_error(exc) is False
    assert is_db_readonly_error(exc) is False


def test_error_route_maps_status_and_message():
    ro = error_route(_Req("/api/v1/x"), sqlite3.OperationalError("attempt to write a readonly database"))
    assert ro[0] == 500 and "重试无效" in ro[1] and ro[2] is None
    busy = error_route(_Req("/api/v1/x"), sqlite3.OperationalError("database is locked"))
    assert busy[0] == 503 and "重试" in busy[1] and busy[2] is None
    other = error_route(_Req("/api/v1/x"), ValueError("boom"))
    assert other[0] == 500 and other[2] is None


# ── R-2 页面级 HTML 兜底 ─────────────────────────────────────────────────
@pytest.mark.parametrize("path,expect", [("/api/x", True), ("/static/a.js", True),
                                         ("/docs", True), ("/risks", False), ("/", False)])
def test_wants_json_boundary(path, expect):
    assert wants_json(path) is expect


def test_api_404_stays_json():
    r = page_404_handler(_Req("/api/v1/nope"), _E())
    assert r.status_code == 404
    assert b'"detail"' in r.body and b"<!DOCTYPE" not in r.body


def test_page_404_is_html_with_restart_judgement():
    r = page_404_handler(_Req("/not-a-page"), _E())
    body = r.body.decode("utf-8")
    assert r.status_code == 404 and "<!DOCTYPE html>" in body
    assert "旧代码" in body and "start8001.bat" in body and "/healthz" in body


def test_page_error_html_contains_boot_time_and_stale_block():
    _, _, html = error_route(_Req("/risks"), sqlite3.OperationalError("database is locked"))
    assert html is not None and html.status_code == 503
    body = html.body.decode("utf-8")
    assert RV.boot_snapshot()["booted_at"] in body
    assert "start8001.bat" in body


def test_render_page_error_is_escaped():
    html = render_page_error(404, "页面不存在", '<script>alert(1)</script>', "/x")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_404_handler_registered_on_app():
    import main
    keys = [str(k) for k in getattr(main.app, "exception_handlers", {}).keys()]
    assert any("404" in k for k in keys), "404 兜底未注册到 app"
    assert any("Exception" in k or "500" in k for k in keys)

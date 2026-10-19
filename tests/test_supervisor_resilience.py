# -*- coding: utf-8 -*-
"""服务守护器（`scripts/serve_supervisor.py`）健壮性守护（2026-10-19）。

## 为什么单独守它（实测事故，用户报「服务器进不去」）

时间线（`data/logs/supervisor.log` + `server8001.combined.log` 实测）：

  · `13:59:42` 守护器启动 → 打开子进程日志 `server8001.combined.log` 时抛
    `PermissionError: [Errno 13] Permission denied`
    （上一轮重启遗留的子进程尚未释放句柄，Windows 拒绝重复打开）；
  · 异常从 `_spawn()` 冒泡出 `while` 循环（**当时循环里没有兜底**）
    ⇒ 守护进程**整个退出**，连一句"将在 Xs 后重启"都没写；
  · 结果：**服务无人拉起，守护也死了** —— 用户看到的就是"进不去"。

两条必须锁住的判据：

  ① **日志打不开不得让服务不可用**：`_open_server_log()` 必须有重试 + 备用日志 + DEVNULL 兜底；
  ② **单次启动失败不得让守护器退出**：主循环必须吞下 `_spawn()` 的异常并按退避重试。

本文件用**行为级**验证（临时把日志路径指到一个"必然打不开"的地方），
而不是只 grep 源码 —— 「判据扫全文」的假绿在本仓已多次出现。
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SUP_PY = ROOT / "scripts" / "serve_supervisor.py"


def _load_sup(monkey_log_dir: Path | None = None):
    """把守护器模块载入内存（可把 LOG_DIR 指向临时目录，避免污染真实日志）。"""
    spec = importlib.util.spec_from_file_location("_sup_under_test", SUP_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if monkey_log_dir is not None:
        mod.LOG_DIR = monkey_log_dir
        mod.LOG = monkey_log_dir / "supervisor.log"
        mod.SERVER_LOG = monkey_log_dir / "server8001.combined.log"
    return mod


# ══════════════════════════════════════════════════════════════════════════
# ① 日志打不开 ⇒ 仍必须拿到一个可用的写入目标（绝不因日志而不可用）
# ══════════════════════════════════════════════════════════════════════════
def test_log_open_succeeds_normally(tmp_path: Path) -> None:
    mod = _load_sup(tmp_path)
    fh, path = mod._open_server_log()
    try:
        assert fh is not subprocess.DEVNULL, "正常情况必须写主日志（不能默认丢弃）"
        assert Path(path) == mod.SERVER_LOG, "正常情况必须用主日志（保持路径单一权威）"
        fh.write("probe\n")
    finally:
        fh.close()


def test_log_open_falls_back_when_locked(tmp_path: Path, monkeypatch) -> None:
    """**核心判据**：主日志打不开时必须（重试后）降级到备用日志，而不是抛异常。"""
    mod = _load_sup(tmp_path)
    real_open = Path.open
    tried = {"n": 0}

    def fake_open(self, *a, **kw):
        # 只让**主日志**打不开；备用日志仍可正常打开（模拟"该文件被别的进程占用"）
        if self.name == mod.SERVER_LOG.name:
            tried["n"] += 1
            raise PermissionError(13, "Permission denied", str(self))
        return real_open(self, *a, **kw)

    monkeypatch.setattr(Path, "open", fake_open)
    fh, path = mod._open_server_log()
    try:
        assert fh is not subprocess.DEVNULL, "备用日志可用时必须写备用，不是直接丢弃"
        assert path is not None and Path(path).name.startswith("server8001."), (
            "必须落到带时间戳的备用日志（用户才能找到当晚的日志）")
        assert Path(path).name != mod.SERVER_LOG.name
        fh.write("fallback\n")
    finally:
        fh.close()
    assert tried["n"] >= 2, (
        "必须先**重试**再降级（Windows 句柄释放常只需几百毫秒；不重试就换文件会"
        "把日志拆得七零八落）—— 实测重试次数 %d" % tried["n"])


def test_log_open_never_raises(tmp_path: Path, monkeypatch, capsys) -> None:
    """极端情况（**连 supervisor.log 都写不了**）也必须返回 DEVNULL，绝不抛异常。

    ★ 判据演进（测试先抓到真缺陷）：
      首版只断言"必须写进 supervisor.log"。跑起来才发现 —— 当**所有**日志文件都不可写时
      （这正是本用例模拟的极端场景），`_log()` 自己也会抛 `PermissionError`，
      异常再次冒出去。⇒ 这一条其实暴露了**第二处同源缺陷**：`_log()` 没有兜底。
      修好后，留痕只能退化为 stdout（文件写入在物理上不可能）。
      故本用例的判据是：**① 不抛异常；② 返回 DEVNULL；③ 至少尝试从 stdout 发声。**
    """
    mod = _load_sup(tmp_path)

    def always_fail(self, *a, **kw):
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "open", always_fail)
    fh, path = mod._open_server_log()          # 不抛 ⇒ 这一行本身就是断言
    assert fh is subprocess.DEVNULL
    assert path is None
    # 文件全不可写 ⇒ 只能从 stdout 说明；用户/运维据此仍可判断发生了什么
    captured = capsys.readouterr()
    assert "备用日志也不可写" in (captured.out + captured.err), (
        "连 stdout 都没有任何说明 ⇒ 故障完全静默（该场景下唯一可用的留痕手段就是 stdout）")


# ══════════════════════════════════════════════════════════════════════════
# ② 单次启动失败 ⇒ 守护器必须继续重试，不得退出
# ══════════════════════════════════════════════════════════════════════════
def test_spawn_failure_does_not_kill_supervisor(tmp_path: Path, monkeypatch) -> None:
    """**核心判据**：`_spawn()` 抛异常时，守护器要按退避重试，而不是崩掉。

    做法：跑真实 `main()`（`--once` 关闭无限重启不可用，所以用"限定尝试次数"的方式）——
    把 `_spawn` 换成"永远抛 PermissionError"，把 `port_listening` 换成 False，
    `time.sleep` 换成空操作，`BACKOFF` 缩到极短；守护器应当在**有限时间内**
    记下多次失败并**仍然存活**（我们不真的等它跑满 60s，用线程 + 超时判断）。
    """
    import threading

    mod = _load_sup(tmp_path)
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        if calls["n"] >= 4:              # 第 4 次成功"拉起"，随后用 KeyboardInterrupt 收场
            raise KeyboardInterrupt
        raise PermissionError(13, "Permission denied", "server8001.combined.log")

    monkeypatch.setattr(mod, "_spawn", boom)
    monkeypatch.setattr(mod, "port_listening", lambda *a, **kw: False)
    monkeypatch.setattr(mod, "BACKOFF", (0.01, 0.01, 0.01, 0.01, 0.01, 0.01))
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)
    monkeypatch.setattr(sys, "argv", ["serve_supervisor.py"])

    rc = {"v": None}

    def run():
        rc["v"] = mod.main()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=15)
    assert not t.is_alive(), (
        "守护器在 `_spawn()` 连续失败时没有继续重试/未能按预期退出 ⇒ 可能已崩溃")
    assert calls["n"] >= 4, "未按退避重试（只试了 %d 次）" % calls["n"]
    assert rc["v"] == 0, "KeyboardInterrupt 路径应正常收场（返回 0），实际 %r" % rc["v"]
    log_text = (tmp_path / "supervisor.log").read_text(encoding="utf-8")
    assert "子进程启动失败" in log_text, "启动失败必须留痕（不能静默重试）"
    assert log_text.count("子进程启动失败") >= 3, (
        "退避重试日志条数不足（实际 %d 条）" % log_text.count("子进程启动失败"))


def test_spawn_actually_uses_the_safe_opener() -> None:
    """**接线判据**：`_spawn()` 必须真的走 `_open_server_log()`。

    ★ 为什么需要这一条（由反向验证抓出）：首版测试只是**直接调用** `_open_server_log()`
      验证它健壮，却没有断言 `_spawn()` 用了它。于是把 `_spawn()` 里的
      `out, _path = _open_server_log()` 改回裸 `SERVER_LOG.open(...)`
      —— **测试照样全绿**。健壮的函数 + 没接线 = 等于没修。
      ⇒ 判据必须覆盖"接线"，不能只覆盖"函数存在且正确"。
    """
    src = SUP_PY.read_text(encoding="utf-8")
    seg = src[src.index("def _spawn"):]
    seg = seg[:seg.index("\ndef ", 10)] if "\ndef " in seg[10:] else seg
    assert "_open_server_log()" in seg, (
        "`_spawn()` 未使用 `_open_server_log()` ⇒ 日志打不开时仍会抛异常把守护器搞死")
    assert 'SERVER_LOG.open("a"' not in seg, (
        "`_spawn()` 内仍在直接打开主日志（绕过了兜底）")


def test_main_loop_survives_spawn_exception() -> None:
    """**接线判据**：主循环里必须有 `try: _spawn() except` 的兜底。

    说明：`test_spawn_failure_does_not_kill_supervisor` 是行为级的，
    但它依赖"能在后台线程里跑真实 `main()`"这一较重前提；本判据给出**轻量且稳定**
    的结构性检查，两者互补（结构判据防"接线被删"，行为判据防"接线写错"）。
    """
    src = SUP_PY.read_text(encoding="utf-8")
    seg = src[src.index("def main("):]
    assert "try:\n                proc = _spawn()" in seg, (
        "主循环没有把 `_spawn()` 包在 try 里 ⇒ 一次启动失败就整个守护器退出（原事故）")
    assert "except Exception as exc:" in seg, "缺异常分支"
    assert "子进程启动失败" in seg, "启动失败必须留痕"
    assert "continue" in seg, "失败后必须 continue 重试，不得落出循环"


def test_backoff_is_bounded() -> None:
    """退避必须有上限（避免无限拉长或疯狂重启）。"""
    mod = _load_sup()
    assert mod.BACKOFF == tuple(sorted(mod.BACKOFF)), "退避序列必须单调不减"
    assert max(mod.BACKOFF) <= 120, "退避上限过大（服务长时间不可用）"
    assert min(mod.BACKOFF) >= 0.5, "退避过小（崩溃风暴时会刷爆日志）"


def test_single_instance_guard_intact() -> None:
    """单实例守卫不得被本轮改动破坏（两个 uvicorn 指向同一 DB ⇒ readonly）。"""
    src = SUP_PY.read_text(encoding="utf-8")
    assert "不启第二个实例" in src, "单实例守卫口径注释缺失"
    assert src.count("port_listening()") >= 2, (
        "端口探测点少于 2 处（启动前 + 重启前各需一次）—— 实测 %d 处"
        % src.count("port_listening()"))


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
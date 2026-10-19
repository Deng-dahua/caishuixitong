# -*- coding: utf-8 -*-
"""8001 服务守护器（D-03：崩溃自动重启）。

背景（阶段 9 评估结论 D-03）
--------------------------
服务崩溃后必须人工双击 `start8001.bat` 才能恢复。本轮评估期间出现多次
「8001 未监听」，每次都要人介入 —— 对财税系统来说这是**可用性缺口**。

本守护器做三件事，且只做这三件：
  1. **单实例守卫**：启动前先探端口；端口已被监听就**不启第二个**
     （★ 项目铁律：两个 uvicorn 指向同一个 security.db 必然 readonly）；
  2. **崩溃即重启**：子进程退出后按 **1→2→5→10→30s 退避**重启，
     连续快速失败达 5 次则拉长到 60s（避免疯狂重启刷日志）；
  3. **全程留痕**：每次启停写 `data/logs/supervisor.log`，可事后核对
     「服务究竟中断过几次、每次多久」。

用法
----
    python scripts/serve_supervisor.py             # 前台守护（Ctrl+C 退出）
    python scripts/serve_supervisor.py --once      # 只启一次，不重启（调试用）

★ 不改变任何业务逻辑，不碰数据库，不写数据目录以外的文件。
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime_storage import LOG_DIR, now_cst  # noqa: E402

HOST = "127.0.0.1"
PORT = int(os.environ.get("APP_PORT", "8001"))
LOG = LOG_DIR / "supervisor.log"
SERVER_LOG = LOG_DIR / "server8001.combined.log"

#: 退避序列（秒）。连续快速失败时逐步拉长，避免崩溃-重启风暴。
BACKOFF = (1, 2, 5, 10, 30, 60)
#: 子进程存活超过这个秒数，就认为「这次启动是成功的」，重置退避。
HEALTHY_AFTER = 60
#: 打开子进程日志的**重试**参数（Windows 上句柄释放通常只需几百毫秒）。
#: 见 `_open_server_log()` 的说明：这里重试是为了"瞬间占用不放大成守护器崩溃"。
LOG_OPEN_RETRIES = 5
LOG_OPEN_DELAY = 0.4
#: 兼容模块级私有名（便于测试直接引用，避免下划线名在两处各自硬编码）
_LOG_OPEN_RETRIES = LOG_OPEN_RETRIES
_LOG_OPEN_DELAY = LOG_OPEN_DELAY


def _log(msg: str) -> None:
    """写守护器日志。**写不进去也不得抛异常**（2026-10-19 修）。

    ★ 与 `_open_server_log()` 同源的事故：守护器的第一职责是"把服务维持住"，
      日志只是辅助。若 `_log()` 会抛，那么"日志目录不可写"这种环境问题
      就会再次把守护器打死 —— 且恰好发生在**最需要它留下痕迹**的时候。
      （实测由 `tests/test_supervisor_resilience.py::test_log_open_never_raises` 抓出：
        `_open_server_log` 的兜底分支里调 `_log` 报"备用日志也不可写"，
        而 `_log` 自己写不进去 ⇒ 异常又冒出去了。）
    处置：`OSError` 一律吞掉，只退化为"打到 stdout"；`print` 再失败也吞掉。
    """
    line = "[%s] %s" % (now_cst(), msg)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        # 日志文件不可写（被占用/无权限/磁盘满）⇒ 放弃文件，走 stdout
        pass
    try:
        print(line, flush=True)
    except Exception:                                # noqa: BLE001  # 连 stdout 都没有就算了
        pass


def port_listening(host: str = HOST, port: int = PORT, timeout: float = 0.6) -> bool:
    """端口是否已被监听（**只探测，不连接业务逻辑**）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _open_server_log():
    """打开子进程日志文件；**绝不因为打不开日志就把守护器搞死**。

    ## 为什么需要这层（2026-10-19 实测事故）

    实测：`13:59:42` 守护器启动时，`SERVER_LOG.open("a")` 抛
    `PermissionError: [Errno 13] Permission denied`（上一轮重启遗留的子进程
    尚未释放日志句柄，Windows 对打开中的文件会拒绝再打开）。
    后果不是"这次没启起来"，而是 —— `_spawn()` 抛异常 → 外层 `while` **没有兜底**
    → 守护进程**整个退出**，连一句"将在 Xs 后重启"都没写。
    ⇒ **守护机制形同虚设**：服务挂了、守护也死了，用户看到的就是"服务器进不去"。

    三级兜底（逐级降级，但**始终返回可用的写入流**）：
      ① 原名打开，最多试 `_LOG_OPEN_RETRIES` 次、每次间隔 `_LOG_OPEN_DELAY` 秒
         —— 句柄释放通常只需几百毫秒，重试即可成功，**日志路径保持单一权威**；
      ② 仍失败 ⇒ 打开**带时间戳的备用日志**，并把这件事写进 supervisor.log
         （绝不静默：用户必须能看出"今晚的服务器日志在另一个文件里"）；
      ③ 备用也打不开（极端：磁盘满/目录不可写）⇒ 退回 `subprocess.DEVNULL`。
         日志可以丢，**服务不能因为日志而不可用**。

    返回 `(fileobj_or_DEVNULL, 实际使用的路径或 None)`。
    """
    last_exc: Exception | None = None
    for attempt in range(1, _LOG_OPEN_RETRIES + 1):
        try:
            return SERVER_LOG.open("a", encoding="utf-8"), SERVER_LOG
        except OSError as exc:                       # PermissionError 是其子类
            last_exc = exc
            if attempt < _LOG_OPEN_RETRIES:
                time.sleep(_LOG_OPEN_DELAY)
    alt = LOG_DIR / ("server8001.%s.log" % datetime.now().strftime("%Y%m%d-%H%M%S"))
    try:
        fh = alt.open("a", encoding="utf-8")
        _log("★ 主日志不可写（%s）⇒ 本次改用备用日志 %s" % (last_exc, alt.name))
        return fh, alt
    except OSError as exc2:
        _log("★★ 备用日志也不可写（%s）⇒ 子进程输出丢弃，但**服务继续启动**" % exc2)
        return subprocess.DEVNULL, None


def _spawn():
    """拉起 uvicorn 子进程（与 start8001.bat 完全同参）。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("APP_COOKIE_SECURE", "0")   # 本地 http 必需，否则 cookie 不回传
    env.setdefault("PYTHONIOENCODING", "utf-8")
    out, _path = _open_server_log()
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app",
         "--host", HOST, "--port", str(PORT)],
        cwd=str(ROOT), env=env, stdout=out, stderr=subprocess.STDOUT,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="8001 服务守护器（崩溃自动重启）")
    ap.add_argument("--once", action="store_true", help="只启动一次，退出后不重启")
    args = ap.parse_args()

    if port_listening():
        _log("端口 %d 已在监听 ⇒ **不启第二个实例**（避免同一 security.db 双进程）" % PORT)
        return 0

    _log("守护启动：%s:%d → %s" % (HOST, PORT, SERVER_LOG))
    failures = 0
    stop = False
    proc = None
    try:
        while not stop:
            started = time.time()
            try:
                proc = _spawn()
            except Exception as exc:                 # noqa: BLE001
                # ★ 2026-10-19：**单次启动失败绝不能让守护器退出**。
                #   实测事故：`_spawn()` 抛 PermissionError（日志被瞬时占用）
                #   ⇒ 守护进程整个死掉，服务再没人拉起 —— 用户看到"服务器进不去"。
                #   守护器的职责就是"无论如何把服务维持住"，因此这里必须自己吞下异常、
                #   记明细、按退避重试，而不是把异常抛到 `while` 之外。
                failures += 1
                delay = BACKOFF[min(failures - 1, len(BACKOFF) - 1)]
                _log("子进程启动失败（第 %d 次）：%s: %s ⇒ %ds 后重试"
                     % (failures, type(exc).__name__, exc, delay))
                if args.once:
                    return 1
                if port_listening():             # 别人已经起来了 ⇒ 正常交接
                    _log("端口 %d 已被监听 ⇒ 停止重试，交回对方" % PORT)
                    return 0
                time.sleep(delay)
                continue
            _log("子进程已拉起 PID=%d" % proc.pid)
            code = proc.wait()
            lived = time.time() - started
            _log("子进程退出 code=%s 存活 %.1fs" % (code, lived))
            if args.once:
                return code
            if lived >= HEALTHY_AFTER:
                failures = 0                       # 这次是稳定运行后退出 ⇒ 退避归零
            failures += 1
            delay = BACKOFF[min(failures - 1, len(BACKOFF) - 1)]
            if port_listening():
                _log("端口仍被他人占用 ⇒ 停止重启，交回人工处理")
                return 0
            _log("将在 %ds 后重启（连续失败 %d 次）" % (delay, failures))
            time.sleep(delay)
    except KeyboardInterrupt:
        _log("收到 Ctrl+C ⇒ 停止守护")
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:      # pragma: no cover
                proc.kill()
        stop = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

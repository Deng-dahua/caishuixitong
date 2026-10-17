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


def _log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = "[%s] %s" % (now_cst(), msg)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def port_listening(host: str = HOST, port: int = PORT, timeout: float = 0.6) -> bool:
    """端口是否已被监听（**只探测，不连接业务逻辑**）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _spawn() -> subprocess.Popen:
    """拉起 uvicorn 子进程（与 start8001.bat 完全同参）。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("APP_COOKIE_SECURE", "0")   # 本地 http 必需，否则 cookie 不回传
    env.setdefault("PYTHONIOENCODING", "utf-8")
    out = SERVER_LOG.open("a", encoding="utf-8")
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
            proc = _spawn()
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

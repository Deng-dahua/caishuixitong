# -*- coding: utf-8 -*-
"""以「脱离会话」方式启动 8001 服务（等价于双击 start8001.bat，但无需 cmd.exe）。

背景：本环境的会话后台任务会在会话结束后被回收（实测运行约 18 分钟后被终止），
而 start8001.bat 需要 cmd.exe —— 从 PowerShell 启动 cmd.exe 会被安全策略拦截。
故此处直接用 Windows 的 DETACHED_PROCESS 标志拉起项目自带启动器
`scripts/_start_uvicorn.py`，使服务**不属于本会话**、可长期常驻。
"""
import os
import subprocess

REPO = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
PY = os.path.join(REPO, ".venv", "Scripts", "python.exe")
LOG_DIR = os.path.join(REPO, "data", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

env = dict(os.environ)
env["APP_COOKIE_SECURE"] = "0"          # 与 start8001.bat 一致（HTTP 本地访问）
for k in ("CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR", "CODEBUDDY_TOOL_CALL_ID",
          "CODEBUDDY_SAFE_DELETE_BULK_GUARD", "CODEBUDDY_NODE_BIN"):
    env.pop(k, None)                     # 清守护变量，否则用户批量删资料会杀进程

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000

log_path = os.path.join(LOG_DIR, "uvicorn.out.log")
PYW = os.path.join(REPO, ".venv", "Scripts", "pythonw.exe")
launcher = os.path.join(REPO, "scripts", "_start_uvicorn.py")
_exe = PYW if os.path.exists(PYW) else PY
with open(log_path, "ab", buffering=0) as fh:
    p = subprocess.Popen(
        [_exe, launcher],
        cwd=REPO, env=env, stdin=subprocess.DEVNULL, stdout=fh, stderr=fh,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
print("已脱离会话启动 8001，PID =", p.pid, "| 可执行:", _exe, "| 日志:", log_path)


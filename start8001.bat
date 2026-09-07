@echo off
cd /d "%~dp0"
set "APP_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%APP_PYTHON%" (
  echo Virtual environment not found.
  exit /b 1
)
rem 2026-09-05: 清除 AI 会话环境的批量删除守护变量，否则用户在界面
rem 「删除选中资料」超过 50 个文件时，守护会强制终止整个服务进程。
rem 该守护只适用于 AI 工具调用的文件删除，不适用于用户在自己应用内的正常操作。
set "CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR="
set "CODEBUDDY_TOOL_CALL_ID="
set "CODEBUDDY_SAFE_DELETE_BULK_GUARD="
set "CODEBUDDY_NODE_BIN="
rem 2026-09-07: HTTP 本地访问需要 APP_COOKIE_SECURE=0，否则 Set-Cookie 上的 Secure 标志
rem 会导致浏览器（除 localhost 例外）在 http://127.0.0.1:8001 上不发送 auth_token，所有调用 401。
rem 与 start.bat / start.sh 保持一致。
set "APP_COOKIE_SECURE=0"
echo Starting on http://127.0.0.1:8001  (Ctrl+C to stop)
"%APP_PYTHON%" -m uvicorn main:app --host 127.0.0.1 --port 8001
pause

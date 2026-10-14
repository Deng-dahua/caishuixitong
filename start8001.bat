@echo off
rem ============================================================
rem  caishuixitong one-click launcher   ->  http://127.0.0.1:8001
rem  Keep this window OPEN while using the app.
rem  Closing the window (or Ctrl+C) stops the server.
rem  Log: data\logs\server8001.combined.log
rem ============================================================
rem  IMPORTANT (2026-10-14 incident): this file MUST stay
rem    (1) CRLF line endings, and (2) ASCII-only.
rem  With LF-only endings, cmd.exe decoded the UTF-8 comments as
rem  GBK; odd-length byte runs swallowed the trailing LF, lines got
rem  merged, `set` broke, %APP_PYTHON% became empty and python was
rem  NEVER launched  ->  "double-click does nothing, browser cannot
rem  connect".  .gitattributes enforces eol=crlf for *.bat.
rem ============================================================
cd /d "%~dp0"

set "APP_PYTHON=%~dp0.venv\Scripts\python.exe"
set "PORT=8001"
set "LOGDIR=%~dp0data\logs"
set "LOG=%LOGDIR%\server8001.combined.log"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

rem -- If the port is already listening, the service is already up.
rem    Just open the browser and exit (do NOT start a 2nd instance).
set "LISTEN_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do set "LISTEN_PID=%%P"
if defined LISTEN_PID (
  echo [INFO] Service already running on port %PORT% ^(PID %LISTEN_PID%^).
  echo [INFO] Opening browser: http://127.0.0.1:%PORT%
  start "" "http://127.0.0.1:%PORT%"
  timeout /t 3 /nobreak >nul
  exit /b 0
)

if not exist "%APP_PYTHON%" (
  echo [ERROR] Virtual environment not found.
  echo         Expected: "%APP_PYTHON%"
  echo         Make sure the .venv folder sits next to this file.
  echo.
  pause
  exit /b 1
)

rem 2026-09-05: clear AI-session bulk-delete guard vars, otherwise deleting
rem more than 50 files from the UI can force-kill the whole server process.
rem That guard applies only to AI tool calls, not to in-app user actions.
set "CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR="
set "CODEBUDDY_TOOL_CALL_ID="
set "CODEBUDDY_SAFE_DELETE_BULK_GUARD="
set "CODEBUDDY_NODE_BIN="

rem 2026-09-07: local HTTP needs APP_COOKIE_SECURE=0, otherwise the Secure
rem flag on Set-Cookie stops browsers from sending auth_token over
rem http://127.0.0.1:8001 and every call returns 401.
set "APP_COOKIE_SECURE=0"

echo ============================================================
echo   caishuixitong  -^>  http://127.0.0.1:8001
echo   Use 127.0.0.1, NOT localhost: localhost resolves to IPv6 ::1
echo   while this server binds IPv4 only.
echo   Press Ctrl+C to stop.
echo   While the server runs this window stays quiet - that is normal.
echo   Log: data\logs\server8001.combined.log
echo ============================================================
echo.

echo [launcher] start  python="%APP_PYTHON%" >> "%LOG%"

rem -- Run uvicorn. Server output is appended to the log file.
rem    cmd redirection is used on purpose: it is reliable, keeps the log in
rem    UTF-8, and leaves %ERRORLEVEL% meaningful (a pipe would swallow it).
rem -- Open the browser a few seconds later, once uvicorn is listening.
rem    (Separate detached cmd so the delay does not block the server.)
start "" /min cmd /c "ping -n 7 127.0.0.1 >nul & start http://127.0.0.1:%PORT%"
"%APP_PYTHON%" -m uvicorn main:app --host 127.0.0.1 --port %PORT% >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

echo [launcher] exit  code=%RC% >> "%LOG%"

echo.
echo [SERVER STOPPED]  exit code = %RC%
echo   ---- last lines of data\logs\server8001.combined.log ----
powershell -NoProfile -Command "if (Test-Path '%LOG%') { Get-Content '%LOG%' -Tail 20 }" 2>nul
echo.
pause

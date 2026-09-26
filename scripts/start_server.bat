@echo off
REM One-click launcher for caishuixitong server
REM Double-click to start; keep the window open (closing it stops the server).
cd /d "C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong"
set APP_COOKIE_SECURE=0
set CODEBUDDY_SAFE_DELETE_BULK_1=
set CODEBUDDY_SAFE_DELETE_BULK_2=
set CODEBUDDY_NODE_BIN=
echo Starting server on http://127.0.0.1:8001 ...
".venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8001
pause

@echo off
cd /d "C:\Users\26726\WorkBuddy\2026-06-22-10-40-26\caishuixitong"
REM Kill existing
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8001" ^| findstr "LISTENING"') do taskkill /F /PID %%a 2>nul
timeout /t 2 /nobreak >nul
REM Clear cache
rmdir /s /q __pycache__ 2>nul
del /q static\uploads\transfer\2_*.json 2>nul
REM Start
C:\Users\26726\.workbuddy\binaries\python\envs\zhangwu\Scripts\python.exe -B -m uvicorn main:app --host 0.0.0.0 --port 8001

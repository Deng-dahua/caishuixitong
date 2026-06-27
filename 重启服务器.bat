@echo off
echo ============================================
echo   Caishui System - Force Restart
echo ============================================

echo [1/3] Killing ALL Python processes...
taskkill /F /IM python.exe /T >nul 2>&1
timeout /t 3 /nobreak >nul

echo [2/3] Clean cache...
rmdir /s /q __pycache__ 2>nul
for /d /r . %%d in (__pycache__) do @rmdir /s /q "%%d" 2>nul
del /s *.pyc 2>nul

echo [3/3] Start server on port 8001...
set PYTHONDONTWRITEBYTECODE=1
C:\Users\26726\.workbuddy\binaries\python\envs\zhangwu\Scripts\python.exe -B -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

pause

@echo off
chcp 65001 >nul
echo ============================================
echo   财税系统 - 强制重启
echo ============================================

echo [1/3] 清理旧进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8001" ^| findstr "LISTENING"') do (
    echo   杀掉 PID %%a
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo [2/3] 清除缓存...
if exist __pycache__ rmdir /s /q __pycache__
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d" 2>nul
del /s *.pyc 2>nul

echo [3/3] 启动服务器...
set PYTHONDONTWRITEBYTECODE=1
C:\Users\26726\.workbuddy\binaries\python\envs\zhangwu\Scripts\python.exe -B -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

pause

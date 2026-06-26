@echo off
cd /d "%~dp0"
set PYTHON=C:\Users\26726\.workbuddy\binaries\python\envs\zhangwu\Scripts\python.exe
set PYTHONDONTWRITEBYTECODE=1

echo 财税系统后台启动中...
echo 启动后窗口自动最小化，不要关闭
echo.

:: 清理旧进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8001" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

:: 启动服务器
start /min "财税系统" "%PYTHON%" -B -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

timeout /t 5 /nobreak >nul
echo 服务器已启动: http://localhost:8001
timeout /t 2 /nobreak >nul

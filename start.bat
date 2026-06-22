@echo off
REM === 财税系统启动脚本 ===
REM 功能：杀僵尸进程→清缓存→启动→验证版本

set PORT=8001
set VENV_PYTHON=C:\Users\26726\.workbuddy\binaries\python\envs\zhangwu\Scripts\python.exe

echo [1/4] 清除占用端口 %PORT% 的所有进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    echo   杀掉 PID %%a
    taskkill /F /PID %%a 2>nul
)
timeout /t 2 /nobreak >nul

echo [2/4] 清除 Python 字节码缓存...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
del /s /q *.pyc 2>nul

echo [3/4] 启动服务器...
set PYTHONDONTWRITEBYTECODE=1
%VENV_PYTHON% -B -m uvicorn main:app --host 0.0.0.0 --port %PORT% --reload

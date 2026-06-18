@echo off
REM === 财税系统停止脚本 ===
set PORT=8001

echo 清除端口 %PORT% 的所有进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    echo   杀掉 PID %%a
    taskkill /F /PID %%a 2>nul
)

echo 清除 Python 进程...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM python3.13.exe 2>nul

echo 已停止

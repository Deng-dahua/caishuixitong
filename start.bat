@echo off
cd /d "%~dp0"
set PYTHON=C:\Users\26726\.workbuddy\binaries\python\envs\zhangwu\Scripts\python.exe
set PYTHONDONTWRITEBYTECODE=1

echo Starting server on port 8001...
echo Working dir: %CD%
echo.

%PYTHON% -B -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

echo.
echo Server stopped.
pause

@echo off
set PORT=8001
set VENV=C:\Users\26726\.workbuddy\binaries\python\envs\zhangwu\Scripts\python.exe

echo Killing zombie processes on port %PORT%...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do taskkill /F /PID %%a 2>nul
timeout /t 2 /nobreak >nul

echo Clearing bytecode cache...
for /d /r . %%d in (__pycache__) do if exist "%%d" rd /s /q "%%d" 2>nul
del /s /q *.pyc 2>nul

echo.
echo Running system consistency audit...
"%VENV%" audit_consistency.py
echo.

echo Starting server on http://localhost:%PORT%
set PYTHONDONTWRITEBYTECODE=1
"%VENV%" -B -m uvicorn main:app --host 0.0.0.0 --port %PORT%
pause

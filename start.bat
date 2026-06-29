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
echo Running system consistency sync...
echo   1/2 audit_consistency.py --sync (fix code + engine memory docstring)
"%VENV%" audit_consistency.py --sync
echo   2/2 audit_consistency.py (verify all pass)
"%VENV%" audit_consistency.py
echo.

echo Starting server on http://localhost:%PORT%
set PYTHONDONTWRITEBYTECODE=1
"%VENV%" -B -m uvicorn main:app --host 0.0.0.0 --port %PORT%
pause

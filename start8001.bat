@echo off
cd /d "%~dp0"
set "APP_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%APP_PYTHON%" (
  echo Virtual environment not found.
  exit /b 1
)
echo Starting on http://127.0.0.1:8001  (Ctrl+C to stop)
"%APP_PYTHON%" -m uvicorn main:app --host 127.0.0.1 --port 8001
pause

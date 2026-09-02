@echo off
cd /d "%~dp0"
set "APP_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%APP_PYTHON%" (
  echo Virtual environment not found.
  exit /b 1
)
"%APP_PYTHON%" -m uvicorn main:app --host 127.0.0.1 --port 8001

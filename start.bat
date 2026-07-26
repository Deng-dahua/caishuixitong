@echo off
setlocal
cd /d "%~dp0"

set "APP_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%APP_PYTHON%" (
  echo Virtual environment not found.
  echo Run: py -3.12 -m venv .venv
  echo Then: .venv\Scripts\python.exe -m pip install -r requirements.lock
  exit /b 1
)

set "APP_COOKIE_SECURE=0"
set "APP_ALLOWED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000"
if not defined APP_DATA_DIR set "APP_DATA_DIR=%~dp0data"

echo Starting on loopback only: http://127.0.0.1:8000
"%APP_PYTHON%" -m uvicorn main:app --host 127.0.0.1 --port 8000
endlocal

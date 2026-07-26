#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "Virtual environment not found."
  echo "Run: python3.12 -m venv .venv"
  echo "Then: .venv/bin/python -m pip install -r requirements.lock"
  exit 1
fi

export APP_COOKIE_SECURE="${APP_COOKIE_SECURE:-0}"
export APP_ALLOWED_ORIGINS="${APP_ALLOWED_ORIGINS:-http://127.0.0.1:8000,http://localhost:8000}"
export APP_DATA_DIR="${APP_DATA_DIR:-$(pwd)/data}"

echo "Starting on loopback only: http://127.0.0.1:8000"
exec .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000

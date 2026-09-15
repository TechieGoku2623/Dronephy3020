#!/usr/bin/env bash
set -euo pipefail

echo "1) Running backend tests..."
python3 -m pytest -q

echo "2) Starting backend API on port 8000..."
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "3) Preparing and starting frontend on port 3000..."
if [ ! -d node_modules ]; then
  npm install
fi
npm run dev &
FRONTEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" "$FRONTEND_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait "$BACKEND_PID" "$FRONTEND_PID"

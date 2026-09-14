#!/usr/bin/env bash
set -euo pipefail

WORKERS="${GRIDOS_API_WORKERS:-2}"
TIMEOUT="${GRIDOS_API_TIMEOUT_SECONDS:-60}"

exec gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  --workers "$WORKERS" \
  --bind 0.0.0.0:8000 \
  --timeout "$TIMEOUT"

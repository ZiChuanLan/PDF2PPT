#!/bin/sh
set -eu

export APP_SERVICE_ROLE="${APP_SERVICE_ROLE:-api}"

python -m app.services.paddle_prewarm

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT_EFFECTIVE="${PORT:-${API_PORT:-8000}}"

exec uvicorn app.main:app --host "${API_HOST}" --port "${API_PORT_EFFECTIVE}"

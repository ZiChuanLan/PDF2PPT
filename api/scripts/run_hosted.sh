#!/bin/sh
set -eu

if [ -z "${REDIS_URL:-}" ]; then
  export REDIS_URL="memory://"
fi

EMBEDDED_WORKER_CONCURRENCY="${EMBEDDED_WORKER_CONCURRENCY:-0}"
API_PID=""
WORKER_PID=""

cleanup() {
  if [ -n "${API_PID}" ]; then
    kill "${API_PID}" >/dev/null 2>&1 || true
    wait "${API_PID}" >/dev/null 2>&1 || true
  fi
  if [ -n "${WORKER_PID}" ]; then
    kill "${WORKER_PID}" >/dev/null 2>&1 || true
    wait "${WORKER_PID}" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

if printf '%s' "${REDIS_URL}" | grep -q '^memory://'; then
  echo "[hosted] REDIS_URL=memory://, jobs will run inline in the API process" >&2
else
  if [ "${EMBEDDED_WORKER_CONCURRENCY}" -gt 0 ]; then
    echo "[hosted] Starting embedded worker supervisor (workers=${EMBEDDED_WORKER_CONCURRENCY})" >&2
    (
      export WORKER_CONCURRENCY="${EMBEDDED_WORKER_CONCURRENCY}"
      export APP_SERVICE_ROLE=worker
      exec sh /app/scripts/run_worker.sh
    ) &
    WORKER_PID=$!
  else
    echo "[hosted] WARNING: REDIS_URL is set but EMBEDDED_WORKER_CONCURRENCY=0; queued jobs will not be processed" >&2
  fi
fi

(
  export APP_SERVICE_ROLE=api
  exec sh /app/scripts/run_api.sh
) &
API_PID=$!

wait "${API_PID}"

#!/bin/sh
set -eu

if printf '%s' "${REDIS_URL:-}" | grep -q '^memory://'; then
  echo "[worker] REDIS_URL=memory:// does not support a standalone worker" >&2
  exit 1
fi

export APP_SERVICE_ROLE="${APP_SERVICE_ROLE:-worker}"

python -m app.services.paddle_prewarm

workers="${WORKER_CONCURRENCY:-1}"
i=1
while [ "${i}" -le "${workers}" ]; do
  APP_SERVICE_ROLE=worker python -m app.worker &
  i=$((i + 1))
done

wait

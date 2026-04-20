#!/bin/sh
set -eu

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

profile="${CCDASH_RUNTIME_PROFILE:-}"

case "$profile" in
  local)
    exec python -m uvicorn backend.runtime.bootstrap_local:app --host 0.0.0.0 --port "${CCDASH_BACKEND_PORT:-8000}"
    ;;
  api)
    exec python -m uvicorn backend.runtime.bootstrap_api:app --host 0.0.0.0 --port "${CCDASH_BACKEND_PORT:-8000}"
    ;;
  worker)
    exec python -m backend.worker
    ;;
  *)
    echo "Unsupported CCDASH_RUNTIME_PROFILE: '${profile}'" >&2
    echo "Expected one of: local, api, worker" >&2
    exit 1
    ;;
esac

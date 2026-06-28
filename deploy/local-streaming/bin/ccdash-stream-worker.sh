#!/usr/bin/env bash
# CCDash local streaming worker wrapper.
#
# Sourced env keeps DB credentials out of the LaunchAgent plist. This script
# is what com.ccdash.stream-worker.plist actually exec's. It loads the env
# file, cd's into the repo checkout, then exec's the worker entrypoint.
set -euo pipefail

ENV_FILE="${CCDASH_STREAM_ENV:-$HOME/.ccdash/stream.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ccdash-stream-worker: env file not found: $ENV_FILE" >&2
  echo "Copy deploy/local-streaming/stream.env.example to ~/.ccdash/stream.env and fill it in." >&2
  exit 78  # EX_CONFIG
fi
# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

REPO="${CCDASH_REPO:-}"
if [[ -z "$REPO" || ! -d "$REPO" ]]; then
  echo "ccdash-stream-worker: CCDASH_REPO is unset or not a directory: '${REPO:-<empty>}'" >&2
  echo "Set CCDASH_REPO in $ENV_FILE to your CCDash checkout." >&2
  exit 78
fi
cd "$REPO"

PY="$REPO/backend/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ccdash-stream-worker: venv python not found at $PY" >&2
  echo "Run 'npm run setup' in the repo to create backend/.venv." >&2
  exit 69  # EX_UNAVAILABLE
fi

exec "$PY" -m backend.worker

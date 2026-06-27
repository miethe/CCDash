#!/usr/bin/env bash
# CCDash project auto-registration wrapper.
#
# Enumerates ~/.claude/projects/<dir> leaf dirs and registers each as its own
# CCDash project against the node API, so the worker-watch fan-out picks them
# up. Idempotent and stdlib-only (the underlying script handles dedupe).
#
# Curated filter (edit here to change what gets registered):
#   --no-worktrees       skip git worktree leaf dirs (folding is deferred)
#   --min-sessions 5     ignore noise dirs with < 5 sessions
#   --exclude=...        drop known non-project dirs (note: --exclude=VALUE
#                        form is REQUIRED because the dir names begin with '-',
#                        which argparse would otherwise read as a flag).
set -euo pipefail

ENV_FILE="${CCDASH_STREAM_ENV:-$HOME/.ccdash/stream.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ccdash-register: env file not found: $ENV_FILE" >&2
  exit 78  # EX_CONFIG
fi
# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

REPO="${CCDASH_REPO:-}"
if [[ -z "$REPO" || ! -d "$REPO" ]]; then
  echo "ccdash-register: CCDASH_REPO is unset or not a directory: '${REPO:-<empty>}'" >&2
  exit 78
fi
cd "$REPO"

PY="$REPO/backend/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ccdash-register: venv python not found at $PY (run 'npm run setup')" >&2
  exit 69  # EX_UNAVAILABLE
fi

API_BASE="${CCDASH_API:-http://10.42.10.76:8090}"

exec "$PY" scripts/register_claude_projects.py \
  --api "$API_BASE" \
  --apply \
  --no-worktrees \
  --min-sessions 5 \
  --exclude=--claude-jobs \
  --exclude=-private-tmp \
  --exclude=intenttree-

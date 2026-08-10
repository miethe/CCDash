#!/usr/bin/env bash
# Run the reviewer-gate validation-scope resolver for this branch and emit its JSON.
#
# The hook itself is NOT deployed into this repo's .claude/skills/dev-execution/hooks/
# (it exists only in the agentic_meta_dev upstream), so this wrapper invokes the upstream
# copy directly rather than hand-fabricating a measurement blob — the gate consumes the
# output mechanically and an invented number there would defeat the gate.
#
# Usage:  bash .claude/worknotes/di-4e-routing-success-rate/run_validation_scope.sh [base_ref]
set -euo pipefail

HOOK="/Users/miethe/dev/homelab/development/agentic_meta_dev/.claude/skills/dev-execution/hooks/validation-scope.sh"
BASE_REF="${1:-02140cc9dd496741659130d51c9f88a7ff839142}"

if [[ ! -f "$HOOK" ]]; then
  echo '{"scope_status": "hook_unavailable"}'
  exit 0
fi

export VALIDATION_SCOPE_REPO
VALIDATION_SCOPE_REPO="$(git rev-parse --show-toplevel)"
export VALIDATION_SCOPE_BASE_REF="$BASE_REF"
export VALIDATION_SCOPE_JSON=1

# The base tree MUST be materialized outside the repo being scanned. The hook defaults
# VALIDATION_SCOPE_WORKDIR to `.claude/worktrees`, which in this repo is INSIDE the scanned
# tree — so the resolver picked up its own materialized copy's test files
# (".claude/worktrees/validation-scope-<sha>/backend/tests/...") and reported them as in-scope.
# Those paths are not runnable targets for the head tree, so the measurement was junk.
export VALIDATION_SCOPE_WORKDIR="${VALIDATION_SCOPE_WORKDIR:-/tmp/ccdash-validation-scope}"
mkdir -p "$VALIDATION_SCOPE_WORKDIR"

exec bash "$HOOK"

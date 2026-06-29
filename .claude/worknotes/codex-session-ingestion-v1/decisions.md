# Codex Session Ingestion v1 — execution decisions

Captured at execute-plan start (2026-06-28). Branch: `feat/codex-session-ingestion-v1` (base `419c355`).

## Design decisions (operator call)

| ID | Decision | Choice | Impact vs plan |
|----|----------|--------|----------------|
| D1 | cwd → project attribution | **D1-a**: add canonical `projects.repo_path`, resolve by exact-then-longest-prefix match | As recommended. Dual DDL (SQLite + PG) + COLUMN_PARITY_DRIFT_ALLOWLIST. |
| D2 | unmatched cwd | **D2-b**: ingest into an Unattributed bucket, log one-line summary | **Deviates** from plan's skip+count. Requires an FE "Unattributed" view/filter. |

> **D2-b realization (Phase 2 finding):** `sessions` has `PRIMARY KEY (project_id, id)` and child
> tables FK on `(project_id, id)`, so `project_id` **cannot be NULL**. The Unattributed bucket is
> therefore realized as the sentinel `project_id = ""` (empty string), NOT SQL NULL. The captured
> `cwd` is stored on `sessions.cwd` so the UI can show which repo was unattributed. **Phase 3 FE must
> treat `project_id === ""` as the "Unattributed" bucket.**
| D3 | first-run backfill | **D3-b**: last-N-days then live-watch forward | **Deviates** from plan's backfill-all. Needs a backfill-days config knob (`CCDASH_CODEX_BACKFILL_DAYS`). |

## Added requirement (operator, mid-execution)

- **Clear session origin indicator** is a hard requirement, not cosmetic. Every session surface
  must make the originating agent unmistakable: Codex / Claude / remote / Unattributed.
  - Session **cards**: origin chip (reuse existing chip styling).
  - Session **inspector header**: origin indicator.
  - Source **filter** must include Codex and Unattributed values.
  Folded into Phase 3 scope.

## Invariants to honor (from CLAUDE.md + memory)

- New DB column → dual DDL (SQLite + Postgres) in same change set + parity allowlist check.
- New write paths in `db/repositories/` → `retry_on_locked` + direct-count assertion test.
- Independent SQLite connections → `PRAGMA busy_timeout = 30000`.
- Every new optional backend field → explicit FE fallback (missing = contract state).
- Codex ingestion fully gated (`CCDASH_CODEX_INGEST_ENABLED`); flag off → Claude behavior unchanged (AC6).
- Tests: run **named** test modules only (unscoped `pytest backend/tests` hangs at import; test_runtime_bootstrap/test_sse_wire_boundary hang).
- AC4 node runtime smoke (http://10.42.10.76:3010) needs a **node redeploy** — out of band from the squash-merge; flag to operator.

## Phase sequence (strictly sequential — no wave_plan)

1. P1 — repo_path column + `resolve_project_for_cwd` + tests
2. P2 — codex watch root + sync attribution (D2-b) + cwd capture + idempotency + tests
3. P3 — backend `_derive_session_source` codex/unattributed + title derivation + FE origin indicator + filter
4. P4 — worker fan-out wiring + D3-b backfill knob + verification

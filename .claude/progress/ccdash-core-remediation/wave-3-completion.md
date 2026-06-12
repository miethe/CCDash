# Wave 3 Completion — CCDash Core Remediation

**Wave**: 3 of 6 — Phases **P2, P5, P8**
**Date**: 2026-06-11
**Executed by**: Opus orchestration + ICA `--bare` bash delegation (opus[1m]/sonnet[1m])
**Base**: `epic/ccdash-core-remediation` @ `039a6f8` → isolated worktree `worktree-core-remediation-w3` → squash-merge back to epic.

## Execution model

The Agent tool overflows on this repo's CLAUDE.md (documented constraint), so all implementation
ran via ICA bash delegation per the `/dev:execute-plan` fallback path. Collision analysis of the
*detailed* phase docs (not just `wave_plan` frontmatter) found P5 to be the collision hub
(`models.py` with P2; `sync_engine.py` + `config.py` with P8). Resolved by serializing:

**P5 (alone) → {P2 ∥ P8}** — P2 and P8 are mutually file-disjoint and were run in parallel on the
committed P5 base. No parallel-edit hazard; verified disjoint at merge (only `config.py` touched by
P8 alone among the second pair).

## Phases

| Phase | Title | Commit | Tasks | Tests | Result |
|:-----:|-------|--------|:-----:|:-----:|--------|
| P5 | Detection (log-derivable) | `2c421e6` | T5-001..T5-011 | 42 new + 29 regression | ✅ |
| P2 | REST /api/v1 detail+transcript | `02f2155` | T2-001..T2-004 | 34 new | ✅ |
| P8 | Cross-project freshness hardening | `a24111b` | T8-001..T8-005 | 8 new + 13 regression | ✅ |

Scaffold commit: `240f397`. Finalize commit: (this commit).

## Highlights

- **P5**: new `workflow_sidecar.py` parser + localized ±60s sidecar→session 1M-context join (gated
  `CCDASH_SIDECAR_CONTEXT_JOIN_ENABLED`); 5 detection columns with dual SQLite+PG DDL +
  `COLUMN_PARITY_DRIFT_ALLOWLIST` in the same change; log-derived linkage that survives a null sidecar;
  FE surfacing in SessionInspector + Dashboard with explicit fallbacks. **Caught + fixed a real bug**:
  SQLite session-upsert placeholder off-by-one (62→63) that would have broken all SQLite session writes.
- **P2**: `/api/v1/sessions/{id}/detail` + `/transcript` read endpoints over the Phase 1 service;
  `project_id` required (400, no active-project fallback); redaction inherited (AWS key absent from body,
  asserted); `{items,cursor,limit,nextCursor}` envelope contract-pinned. READ-only; reuses the existing
  `_EXPECTED_API_VERSION` (forward-compatible with the unmerged streaming ingest route).
- **P8**: periodic all-projects reconcile job enumerating the DB-authoritative registry (ADR-006),
  dispatching through the Phase 7 coalescing guard; watcher liveness self-heal; `CCDASH_SYNC_ALL_PROJECTS`
  default flipped True→False (plan AC 8.4) with reconcile decoupled so cross-project freshness is not
  regressed; non-active writeback stays OFF (permanent regression fixture).

## Guard compliance (all clean)

- No `source_ref`/`source_type` column; session upsert key unchanged (ADR-009 boundary owned by streaming branch).
- P5 sidecar join additive/localized; no source/cursor re-architecture.
- All P8 reconcile dispatches route through the Phase 7 `_sync_in_flight` guard (verified in code).
- DB-authoritative registry enumeration only (ADR-006); `retry_on_locked` path reused (no new write path).
- Cross-phase: only `config.py` shared (P5 + P8 additive blocks, no clobber).

## Reviewer gate

Consolidated read-only + bash-enabled validator (opus[1m]) over P2/P5/P8 against the committed diff:
**VERDICT: APPROVED.** All ACs (R2.1/R2.2, AC-5.1..5.5, AC 8.1..8.5) MET; zero guard violations;
**97 named tests passed**.

## Findings (non-blocking)

- **F-W3-001**: AC 8.2 prose overclaims cross-trigger coalescing (guard keys on `(project_id, trigger)`);
  correctness-safe; recommend prose tightening at Phase 12. See `.claude/findings/ccdash-core-remediation-findings.md`.
- **F-W3-002**: 3 benign unawaited-coroutine RuntimeWarnings in `test_sync_all_projects.py` setup.

## Deferred to post-merge

- **P5 runtime smoke**: `runtime_smoke: skipped` (isolated worktree, no dev server). FE changes are
  additive optional-field renders with explicit fallbacks, tsc-clean. Browser smoke to be performed on
  the epic branch where the dev env is provisioned (CLAUDE.md UI-phase gate).

## Next

Wave 4 = **[P3, P9, P10]** (MCP/CLI session group + Postgres convergence gate + external API).
P9 requires the **Bash-enabled PG seam review** (hard gate; edit-less prohibited).

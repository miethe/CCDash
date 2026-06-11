# Phase 0 — Cross-project session correctness — Completion Note

**Wave**: 1 (of 6) — `/dev:execute-plan ... W1 only`
**Branch**: `epic/ccdash-core-remediation` (forked from `development`; worked in worktree `.claude/worktrees/ccr-epic`)
**Status**: ✅ Complete — all exit criteria met, reviewer gate APPROVED.
**Date**: 2026-06-11

## Summary

Phase 0 makes ID-based session reads project-safe in **both** backends — the hard prerequisite
for all cross-project reads in Phases 2/3. `project_id` is now an optional, strictly-equality
WHERE-clause predicate on `get_by_id` / `get_many_by_ids`; `None`/`''` preserves the existing
active-project hot path unchanged. `get_session_family_v1` derives `project_id` from the anchor
row (not the active-project singleton). ~11 call sites audited and threaded; a permanent ADR-007
collision-test fixture pins zero-leak behavior.

## Tasks (8/8 complete)

| Task | Result |
|------|--------|
| T0-001 SQLite `project_id` enforcement | `get_by_id`/`get_many_by_ids` param-bound predicate; None/'' → unscoped |
| T0-002 Postgres `project_id` enforcement | Mirror of T0-001 (`$N` params, `ANY($2::text[])`); parity confirmed |
| T0-003 Call-site audit + threading | 10 threaded, 7 intentionally active-bound, 0 silent drops (`phase-0-call-site-audit.md`) |
| T0-004 Family anchor-derived project_id | `get_session_family_v1` anchor-scoped; anchor-not-found→404 no fallback |
| T0-005 ADR-007 collision tests (SQLite) | 13 direct-count tests, all pass |
| T0-006 Postgres parity tests | 6 tests, skip-with-reason (Postgres unreachable in env — NOT silent pass) |
| T0-007 Family-scope test | 4 handler-level tests, all pass |
| T0-008 Regression + PG seam review | Bash-enabled senior-code-reviewer: **VERDICT APPROVED** |

## Files changed (committed on epic)

Repos: `backend/db/repositories/sessions.py`, `backend/db/repositories/postgres/sessions.py`,
`backend/db/repositories/base.py` (Protocol). Router/family: `backend/routers/_client_v1_sessions.py`,
`backend/routers/api.py`. Call sites: `backend/application/services/session_intelligence.py`,
`.../agent_queries/{feature_evidence_summary,feature_forensics,planning}.py`,
`backend/application/services/documents.py`, `backend/services/integrations/skillmeat_memory_drafts.py`.
New: `backend/tests/test_session_repository_project_scope.py`,
`.claude/worknotes/ccdash-core-remediation/phase-0-call-site-audit.md`.

## Verification (independently re-run by Opus, not just delegate-reported)

- New collision/family suite: **17 passed, 6 skipped** (Postgres skips, explicit reason).
- Regression suites: `test_sessions_parser.py` 36 ✓, `test_request_context.py` 40 ✓.
- **No-regression proof**: the 4 FK-fixture failures in `test_sessions_repository_filters.py` /
  `test_session_intelligence_repository.py` reproduce **identically** on clean baseline `25b53e1`
  (verified via `git stash -u`) → pre-existing, not Phase 0. Logged as finding F-001.
- Composite PK `(project_id, id)` confirmed present in `sqlite_migrations.py:228` and
  `postgres_migrations.py:204` (resolves the reviewer's one static uncertainty).
- Provenance check: baseline `25b53e1` `get_by_id(session_id)` had no `project_id` param →
  changes were genuinely authored this wave (delegate's "pre-existed" narration was confabulation;
  code verified real and correct).

## AC → task → test coverage map

| AC | Covered by | Evidence |
|----|-----------|----------|
| P0.1 — project_id enforced both backends | T0-001, T0-002 | 13 SQLite tests; 6 PG tests (skip-with-reason) |
| P0.2 — zero cross-project leak (ADR-007 direct-count) | T0-005, T0-006 | `test_fixture_seeded_two_colliding_rows`, `..._returns_only_project_a_row`, `..._drops_a_only` |
| P0.3 — family derivation anchor-scoped end-to-end | T0-004, T0-007 | `..._non_active_project_returns_only_that_tree`, `..._raises_404_no_fallback`, `..._derives_project_from_anchor_row` |
| P0.4 — all call sites threaded; active path unchanged | T0-003, T0-008 | audit table (10/7/0); `..._default_arg_matches_legacy_behaviour` |
| NULL/'' tolerance | T0-001, T0-002 | `..._none_project_id_unscoped_no_crash`, `..._empty_string_project_id_unscoped` |

(Logged independently because `ac-coverage-report.py` can't parse the spec's nested-list
`verified_by` — finding F-003. Substantive coverage is complete and verified above.)

## Gates

- ✅ Phase-completion evidence gate: PASSED (0 violations).
- ✅ T0-008 Bash-enabled senior-code-reviewer (PG seam): APPROVED, no required fixes.
- ✅ Opus independent verification (tests, regression-baseline diff, diff review, PK check).
- Runtime smoke gate: N/A — pure data-layer phase, no `*.tsx` (R-P4 not triggered).
- Note: the heavyweight `task-completion-validator` agent gate is deferred to the end-of-feature
  reviewer pass (out of scope for this `W1 only` run); its mechanical AC↔task check is satisfied
  above and the code-correctness judgment is covered by the senior-code-reviewer APPROVED gate.

## Delegation notes (for retro)

- Implementer + reviewer ran via **ICA bash delegation** (`claude-sonnet-4-6[1m]`, `--bare`):
  the Agent tool overflowed ("Prompt is too long") on `data-layer-expert` due to heavy auto-loaded
  project context; per the run directive, fell back to bash delegation, which succeeded.
- First reviewer attempt hit the 40-turn cap (open-ended exploration); relaunch with **inline diffs**
  + 60-turn cap completed cleanly. Lesson: hand read-only reviewers the diffs inline to bound turns.

## Downstream

Phases 2 and 3 (cross-project `/api/v1` detail/transcript + MCP/CLI session tools) are now
unblocked. The T0-005/006 collision fixture is a **permanent** regression guard.

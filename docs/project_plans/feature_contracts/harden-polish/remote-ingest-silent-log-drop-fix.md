---
title: "Feature Contract: Remote Session Ingest Silently Drops payload.logs"
schema_version: 2
doc_type: feature_contract
it_schema: 1
description: "RemoteSessionIngestService.process() never persists payload.logs; make the remote ingest path honour declared transcript data instead of silently discarding it."
status: draft
created: 2026-08-05
updated: 2026-08-05
feature_slug: remote-ingest-silent-log-drop-fix
category: "harden-polish"
estimated_points: 5
tier: 1
owner: null
priority: high
risk_level: low
changelog_required: true
node_type: work_package
acceptance_criteria: []
definition_of_done: "A remote push carrying payload.logs cannot silently lose data; a 200 response with a non-empty logs array MUST result in the logs being retrievable afterward. A regression test enforces this."
execution_mode: unassigned
agent_title: "Fix silent transcript drop in RemoteSessionIngestService"
agent_summary: "Make the remote NDJSON ingest path call upsert_logs like the file-based path already does, and document the two divergent call sites."
agent_context: "Two independent classes both ingest AgentSession-shaped payloads and both declare a `logs` field, but only one of them writes it to session_logs. See references/notes below for the exact divergence."
open_questions: []
decisions:
  - decision: "Honour payload.logs on the remote path by calling upsert_logs, rather than rejecting the field with a 4xx."
    rationale: "The file-based SessionIngestService already treats logs as a normal, expected field; rejecting it on the remote path would create an unnecessary asymmetry between the two ingest transports for data the daemon legitimately sends on every push."
    status: accepted
scores: {}
related_documents: []
spike_ref: null
prd_ref: null
plan_ref: null
commit_refs: []
pr_refs: []
files_affected:
  - backend/application/services/ingest/session_ingest.py
  - backend/ingestion/session_ingest_service.py
  - backend/tests/test_ingest_endpoint.py
---

# Feature Contract: Remote Session Ingest Silently Drops `payload.logs`

## 1. Goal

A remote NDJSON push whose `payload.logs` field is non-empty must result in those logs being persisted and retrievable — not accepted with `200` and silently discarded.

---

## 2. User / Actor

- **Primary user**: The `ccdash-cli daemon` process pushing session events from a workstation to a remote CCDash server via `POST /api/v1/ingest/sessions`.
- **Secondary users**: Any operator or dashboard viewer who expects a remotely-ingested session's transcript to be visible via `GET /api/v1/sessions/{id}/transcript` or `/detail`.

---

## 3. Job To Be Done

When **the daemon pushes a session event whose payload includes a populated `logs` array**, the ingest server wants to **persist those logs the same way the file-based ingest path does**, so that **the session's transcript is retrievable afterward instead of silently vanishing behind a `200 accepted` response**.

---

## 4. Scope

### In Scope

- `RemoteSessionIngestService.process()` (`backend/application/services/ingest/session_ingest.py:130`, class starts at `:49`) — extract `logs` from `event.payload` and call `self._session_repo.upsert_logs(...)` when non-empty, mirroring the file-based path's behavior (`backend/ingestion/session_ingest_service.py:174`).
- A regression test that pushes an NDJSON event carrying `payload.logs` through the real `POST /api/v1/ingest/sessions` endpoint (or directly against `RemoteSessionIngestService.process()` with a real/fake `SqliteSessionRepository`) and asserts the logs are persisted and retrievable — a `200` with the logs silently absent must fail this test.
- A short docstring/comment note at **both** call sites (`session_ingest.py` remote service and `session_ingest_service.py` file-based service) cross-referencing each other so a future reader sees both paths and their contract for `logs` without re-discovering the divergence via grep.

### Out of Scope

- Replicating the file-based path's full canonical-message derivation (`project_session_messages`, `session_message_repo.replace_session_messages`, usage-attribution/telemetry/intelligence-facts replay). The remote path's contract for this fix is: **logs are not silently dropped** — writing them to `session_logs` via `upsert_logs` (the same table the file-based path also writes for its "legacy" branch, and the same table `SessionTranscriptService.list_session_logs` reads from) satisfies that. Building out canonical per-message derivation for the remote transport is separate, larger work and is not required by this contract's acceptance criteria.
- Any change to the daemon (`ccdash-cli daemon`) send-side behavior.
- Any change to batch limits, dedup/LRU behavior, or cursor advancement semantics.
- Retroactive backfill of logs for events already ingested (and silently dropped) before this fix ships.

---

## 5. UX / Behavior Requirements

- When `event.payload` contains a non-empty `logs` list, `process()` MUST call `self._session_repo.upsert_logs(session_id, logs, project_id)` after the existing `upsert(...)` call, before `cursor_repo.advance(...)`.
- When `event.payload` contains no `logs` key, or `logs` is an empty list, behavior is unchanged (no-op) — do not introduce a spurious `DELETE`-then-empty-insert cycle for events that never had logs; only call `upsert_logs` when there's something to write. Deduplication and cursor-advance behavior are otherwise unchanged.
- If the `upsert_logs` call raises, it must be treated the same way the existing `upsert(...)` failure is treated (caught by the existing `try/except`, wrapped in `IngestProcessingError(code="upsert_failed")`, cursor `record_error` called) — do not add a second, differently-shaped failure path.
- `session_id` for the `upsert_logs` call must come from `event.payload.get("id")` (the same field the `AgentSession` model treats as the primary session id, per `backend/models.py`) — validate it's non-empty before calling `upsert_logs`; if absent, this is already a payload the existing `upsert(...)` call would have trouble with, so no new guard class is needed beyond a defensive empty-string check.

---

## 6. Data Requirements

- **Entities affected**: `session_logs` table (via `SqliteSessionRepository.upsert_logs`, `backend/db/repositories/sessions.py:1041`). No schema change — `upsert_logs` already exists and is exercised by the file-based path and by direct repo tests.
- **New fields**: None.
- **State changes**: A remote-ingested session that carries `logs` will now have rows in `session_logs` scoped to `(project_id, session_id)`, where previously it had none.
- **Storage implications**: None beyond normal row writes; `upsert_logs` already handles its own scoped `DELETE` + re-insert and dedup-by-`source_log_id`.

---

## 7. API / Integration Requirements

**No new or modified endpoints.** `POST /api/v1/ingest/sessions` (`backend/routers/ingest.py`) is unchanged; this is a body-effect fix inside the service it calls.

**Internal service dependencies:**
- `SqliteSessionRepository.upsert_logs(session_id, logs, project_id)` — already exists, no signature change needed.
- `SessionTranscriptService.list_session_logs` (`backend/application/services/sessions.py:93`) — the consumer that proves the fix worked; it reads from `session_logs`, the same table `upsert_logs` writes to.

---

## 8. Architecture Constraints

**Must follow existing patterns in:**
- The existing `try/except IngestProcessingError` shape in `RemoteSessionIngestService.process()` — extend it, don't parallel it.
- The file-based service's precedent at `backend/ingestion/session_ingest_service.py:171-177` for what "handle logs" means at the repository-call level (calling `upsert_logs`) — but do NOT copy its `write_legacy_logs`/canonical-message branching; that branching exists because the file-based path also maintains `session_message_repo`, which is explicitly out of scope here (§4).

**Must not change** (protected areas):
- `IngestSessionEvent` / batch response shapes (`backend/models.py`, `IngestBatchResponse`, `RejectedEvent`).
- Dedup LRU semantics, cursor advancement ordering, `MAX_EVENTS_PER_BATCH` / `MAX_BATCH_BYTES` limits.
- The file-based `SessionIngestService.process()` batch-write behavior — this contract only adds a documentation note there (§4), no functional change.

**New dependencies:**
- Allowed? **No**. *No new dependencies expected.*

---

## 9. Acceptance Criteria

- [ ] AC1: A remote push (`POST /api/v1/ingest/sessions`) whose event `payload.logs` is a non-empty list results in those logs being persisted such that `SessionTranscriptService.list_session_logs(session_id, project_id, ...)` (or an equivalent direct repository read of `session_logs`) returns them after the push — not silently discarded behind a `200 accepted` response.
- [ ] AC2: A new regression test exists (in `backend/tests/test_ingest_endpoint.py` or a sibling test module) that pushes an event carrying `payload.logs`, then asserts the logs are retrievable. The test MUST fail against the pre-fix code (i.e., it actually exercises the previously-silent drop, not just a happy-path count).
- [ ] AC3: An event with no `logs` key, or an empty `logs` list, is unaffected — no new empty-log rows, no new errors, dedup/cursor behavior identical to before this fix.
- [ ] AC4: Both `RemoteSessionIngestService.process()` and `SessionIngestService.process()` (file-based) carry a short comment/docstring note cross-referencing the other path's `logs` handling, so the divergence documented in this contract does not silently reappear for the next reader.
- [ ] AC5: A failure inside the new `upsert_logs` call is caught by the existing error path and surfaces as `IngestProcessingError(code="upsert_failed")`, covered by cursor `record_error` — verified by a test that forces `upsert_logs` to raise.

---

## 10. Validation Requirements

- [ ] **Typecheck**: N/A (Python, no mypy/pyright gate configured for this module beyond IDE diagnostics — trust runtime import + pytest per project convention).
- [ ] **Lint**: no new lint violations introduced.
- [ ] **Tests**: new regression test(s) per AC2 and AC5 added; run `backend/.venv/bin/python -m pytest backend/tests/test_ingest_endpoint.py -v` and confirm pass.
- [ ] **Relevant tests pass**: full `test_ingest_endpoint.py` file (all 7 existing contract cases) still passes — no regression to dedup/cursor/auth/batch-limit behavior.
- [ ] **Build**: N/A (backend-only, no frontend build affected).
- [ ] **Docs updated**: CHANGELOG `[Unreleased]` entry (bug fix, user-visible data-loss correction) — `changelog_required: true` above.
- [ ] **No unrelated changes** introduced.

---

## 11. Risk Areas

- **Silent behavior drift for empty-logs events**: Must guard the `upsert_logs` call behind a "logs is non-empty" (or "logs key present") check so we don't introduce a spurious delete-then-reinsert-nothing cycle on every remote event that never carried logs in the first place (most events, historically, given the bug). Low risk if guarded; verify via AC3.
- **`session_id` extraction**: `event.payload` is `dict[str, Any]` (not a validated `AgentSession` model) on the remote path — must defensively pull `payload.get("id", "")` and skip the `upsert_logs` call (but not fail the whole event) if it's empty, since the existing `upsert(...)` call already has to cope with whatever shape the caller sent. Low risk, single defensive check.
- **Test realism**: The regression test must actually prove the pre-fix bug existed (AC2) — a test that only checks `accepted == 1` without checking log retrievability would pass both before and after the fix and wouldn't be a real regression guard. Reviewer should confirm the test reads back logs, not just batch counters.

---

## 12. Implementation Notes

**Suggested approach:**
1. Read `backend/application/services/ingest/session_ingest.py` in full (small file, ~182 lines) to confirm exact insertion point (right after the existing `upsert(...)` call inside the `try` block at line ~130-135, before `cursor_repo.advance`).
2. Add: extract `logs = event.payload.get("logs")`; if `logs` is a non-empty list, call `await self._session_repo.upsert_logs(session_id, logs, project_id)` where `session_id = str(event.payload.get("id") or "").strip()`. Skip the call (log a debug line) if `session_id` is empty.
3. Add a short docstring/comment at the top of `RemoteSessionIngestService` (near the existing class docstring) noting the file-based sibling path and its `logs` handling, and add a matching one-line comment near `backend/ingestion/session_ingest_service.py:164-178` pointing back.
4. Add the regression test(s) to `backend/tests/test_ingest_endpoint.py`, following the existing `_minimal_payload` / `TestClient` setup pattern already in that file — add a `logs` key to a payload dict and assert retrievability post-push (via a direct `SqliteSessionRepository`/`SessionTranscriptService` read against the test's SQLite DB, matching how other cases in that file already assert DB state).
5. Add the failure-path test (AC5) using a mock/monkeypatch of `upsert_logs` to raise, asserting the event lands in `rejected[]` with `code="upsert_failed"`.

**Similar existing code:**
- Reference: `backend/ingestion/session_ingest_service.py:171-177` — the file-based path's `write_legacy_logs` branch is the precedent for "logs go to `upsert_logs`"; do not copy the canonical-message branching, only the `upsert_logs` call itself.
- Reference: `backend/tests/test_ingest_endpoint.py` — existing 7-case contract test file; follow its `_minimal_payload`/TestClient/tempfile-SQLite setup exactly.

**Known gotchas:**
- `event.payload` is an untyped `dict[str, Any]` (`IngestSessionEvent.payload: dict[str, Any]`, `backend/application/models/ingest.py:27`) — no pydantic validation guarantees `logs` is well-formed; guard with `isinstance(logs, list)` before passing to `upsert_logs`, matching the defensive `isinstance(..., list)` pattern already used throughout `session_ingest_service.py` (e.g. line 165-166 for the file-based path's own `logs` extraction).
- `upsert_logs(session_id, logs, project_id="")` (`backend/db/repositories/sessions.py:1041`) does NOT accept a `workspace_id` kwarg — do not pass one.

---

## 13. Completion Report Required

The executing agent must produce a Completion Report including:

- **Files changed**: List of all modified/new files with brief reason
- **Tests run**: What tests were added/updated and results
- **Validation results**: Table of all validation commands and their results (pass/fail/not applicable)
- **Deviations from contract**: Any material changes to the contract during implementation and why
- **Risks / Limitations**: Any remaining risks or known limitations
- **Follow-up recommendations**: Suggested next steps or follow-on work

See `.claude/skills/dev-execution/validation/completion-criteria.md` for the full Completion Report template.

---

## Metadata & References

**Tier**: 1 (5 points)

**Execution Mode**: Autonomous Feature Sprint (Mode C) — single sprint to completion, no phase orchestration

**Reviewer**: `task-completion-validator` (mandatory)

**Related Documents**:
- `backend/models.py:369` — `AgentSession.logs` field declaration
- `backend/application/models/ingest.py:27` — `IngestSessionEvent.payload: dict[str, Any]`
- `docs/guides/remote-ingest-operator-guide.md` — remote ingest transport operator guidance

---

## Notes for Agents

This contract is your specification. Implement to satisfy the acceptance criteria and pass validation. If you find:

- **Scope ambiguity**: Ask one focused question or make a conservative assumption and note it in the Completion Report.
- **Impossible constraints**: Flag in the Completion Report before attempting workarounds.
- **Better implementation path**: Document the deviation in the Completion Report with justification.

Stay within scope. Avoid cleanup, refactors, or feature expansion beyond this contract (in particular, do NOT pull the file-based path's canonical-message/telemetry/intelligence-facts derivation into the remote path — that's explicitly out of scope, §4). The reviewer will check for scope drift.

```json autopilot-graph
{
  "tier": 1,
  "effort_points": 5,
  "wave_count": 1,
  "phase_count": 1,
  "file_count": 3,
  "mode_d": false,
  "mode_d_reasons": [],
  "needs_spike": false,
  "spike_reasons": [],
  "single_pass_feasible": true,
  "plan_artifact_path": "docs/project_plans/feature_contracts/harden-polish/remote-ingest-silent-log-drop-fix.md",
  "execution_target": "execute-contract",
  "slug": "remote-ingest-silent-log-drop-fix",
  "category": "harden-polish",
  "review_intensity": "standard",
  "files_affected": [
    "backend/application/services/ingest/session_ingest.py",
    "backend/ingestion/session_ingest_service.py",
    "backend/tests/test_ingest_endpoint.py"
  ],
  "execution_graph": {
    "waves": [
      {
        "id": "wave-1",
        "phases": [
          {
            "id": "phase-1",
            "title": "Fix silent logs drop in RemoteSessionIngestService + regression test",
            "mode": "C",
            "review_intensity": "standard",
            "tasks": [
              {
                "id": "TASK-1.1",
                "prompt": "Mode C: Autonomous Feature Sprint.\n\nContract: docs/project_plans/feature_contracts/harden-polish/remote-ingest-silent-log-drop-fix.md\n\nImplement the full contract above. Summary: RemoteSessionIngestService.process() (backend/application/services/ingest/session_ingest.py, class at line 49, upsert call at line ~130) accepts payload.logs (declared on AgentSession at backend/models.py:369, and present on IngestSessionEvent.payload: dict[str, Any] at backend/application/models/ingest.py:27) but never persists it — a 200-accepted push silently loses the transcript. The sibling file-based path (backend/ingestion/session_ingest_service.py:174, SessionIngestService.process) DOES call self.session_repo.upsert_logs(...) for the same conceptual field; the two paths have diverged.\n\nFix: in RemoteSessionIngestService.process(), after the existing self._session_repo.upsert(...) call and before cursor_repo.advance(...), extract logs = event.payload.get('logs'); if isinstance(logs, list) and logs is non-empty, extract session_id = str(event.payload.get('id') or '').strip(), and if session_id is non-empty call await self._session_repo.upsert_logs(session_id, logs, project_id). Reuse the existing try/except so a failure here also raises IngestProcessingError(code='upsert_failed') and triggers cursor_repo.record_error, matching the existing upsert(...) failure path. Do NOT introduce a second differently-shaped error path. Do NOT call upsert_logs when logs is absent/empty (avoid a spurious delete-then-reinsert-nothing cycle on the common no-logs case).\n\nAdd a short cross-referencing comment/docstring at both RemoteSessionIngestService (session_ingest.py) and SessionIngestService.process (session_ingest_service.py, near line 164-178) noting the sibling path's logs handling, so this divergence is discoverable by a future reader without re-grepping both classes.\n\nAdd regression tests to backend/tests/test_ingest_endpoint.py following its existing _minimal_payload/TestClient/tempfile-SQLite pattern: (1) a push with a non-empty payload.logs list, asserting the logs are retrievable afterward via a direct read against session_logs (or via SessionTranscriptService.list_session_logs) -- this test MUST fail against the pre-fix code, not just assert accepted==1; (2) a push with no logs / empty logs, asserting no error and no spurious rows (AC3); (3) a forced upsert_logs failure (monkeypatch/mock) asserting the event lands in rejected[] with code='upsert_failed' (AC5).\n\nOut of scope: do NOT replicate the file-based path's canonical-message derivation (project_session_messages, session_message_repo, usage-attribution/telemetry/intelligence-facts replay) into the remote path -- calling upsert_logs alone satisfies the contract. Do NOT change IngestSessionEvent/IngestBatchResponse shapes, dedup/LRU semantics, cursor-advance ordering, or batch limits. Do NOT change ccdash-cli daemon send-side code.\n\nRun backend/.venv/bin/python -m pytest backend/tests/test_ingest_endpoint.py -v and confirm all cases (existing 7 + new) pass. Add a CHANGELOG [Unreleased] entry (bug fix category) per changelog_required: true.\n\nProduce a Completion Report per .claude/skills/dev-execution/validation/completion-criteria.md.\n\nDo NOT git add/commit/push/stash.",
                "assigned_to": "python-backend-engineer",
                "effort": 5,
                "files_affected": [
                  "backend/application/services/ingest/session_ingest.py",
                  "backend/ingestion/session_ingest_service.py",
                  "backend/tests/test_ingest_endpoint.py",
                  "CHANGELOG.md"
                ]
              }
            ]
          }
        ]
      }
    ]
  },
  "escalation_recommendation": "If scope expands to also cover canonical-message derivation for the remote path (out-of-scope §4), promote to Tier 2 and author a PRD + milestone Implementation Plan for a 'remote ingest transcript-parity' feature instead of stretching this contract."
}
```

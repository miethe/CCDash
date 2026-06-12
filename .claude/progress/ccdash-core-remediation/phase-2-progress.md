---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-core-remediation"
feature_slug: "ccdash-core-remediation"
phase: 2
status: completed
created: 2026-06-11
updated: 2026-06-11
completed: 2026-06-11
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
commit_refs: ["02f2155"]
pr_refs: []
owners: ["python-backend-engineer"]
contributors: []
overall_progress: 100
tasks:
  - id: "T2-001"
    name: "v1 response models + contracts"
    status: "completed"
    assigned_to: ["python-backend-engineer"]
    dependencies: []
  - id: "T2-002"
    name: "Detail + transcript v1 handlers"
    status: "completed"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T2-001"]
  - id: "T2-003"
    name: "Cross-project param + family-aware detail"
    status: "completed"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T2-002"]
  - id: "T2-004"
    name: "Contract test (envelope pin) + redaction-at-API assertion"
    status: "completed"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T2-002","T2-003"]
parallelization:
  batch_1: ["T2-001"]
  batch_2: ["T2-002","T2-003"]
  batch_3: ["T2-004"]
---

# Phase 2 — REST /api/v1 detail + transcript endpoints Progress

Executed via ICA bash delegation. Disjoint from P8 (runs in parallel after P5 commits).
Builds on Phase 1 `session_detail` service (Wave 2, completed).

## Guards
- READ routes only on `/api/v1`; reuse existing `_EXPECTED_API_VERSION` constant (streaming branch owns the write/ingest route + version convention).
- Missing `project_id` → 400 (never active-project fallback). Unknown session → 404.
- Redaction inherited from Phase 1 service; assert secret absent from HTTP body at API layer.
- `models.py` edited AFTER P5 (sequential) — extend the transcript-bearing detail model; do not clobber P5 detection fields.

## Implementation Evidence

### T2-001: v1 response models + contracts
- Added TranscriptPageV1, SessionDetailV1, SessionTranscriptPageV1 to
  packages/ccdash_contracts/src/ccdash_contracts/models.py (camelCase field
  names matching SessionDetailBundle.as_dict() / TranscriptPage.as_dict()).
- All three models exported from ccdash_contracts.__init__ __all__.
- {items, cursor, limit, nextCursor} cursor envelope confirmed in TranscriptPageV1
  and SessionTranscriptPageV1.
- Full bundle fields (session, transcript, subagents, tokens, artifacts,
  links, redactedFieldCount) confirmed in SessionDetailV1.

### T2-002: Detail + transcript v1 handlers
- get_session_full_detail_v1 added to backend/routers/_client_v1_sessions.py;
  delegates to session_detail.get_session_detail, accepts include list, cursor,
  limit; returns ClientV1Envelope[SessionDetailV1].
- get_session_transcript_page_v1 added; restricts include={transcript};
  returns ClientV1Envelope[SessionTranscriptPageV1].
- GET /api/v1/sessions/{session_id}/detail registered in client_v1.py.
- GET /api/v1/sessions/{session_id}/transcript registered in client_v1.py.
- Both paths confirmed in OpenAPI schema (test verified).

### T2-003: Cross-project param + family-aware detail
- Both handlers require project_id query param; raise HTTP 400 with actionable
  message if missing. No active-project fallback path exists in either handler.
- project_id is passed directly to get_session_detail; unknown session under
  that project_id returns None => HTTP 404.
- Phase 0 project-scoped session lookup invariant inherited from service.

### T2-004: Contract test + redaction assertion
- backend/tests/test_client_v1_session_detail.py created (34 tests).
- Test run result: 34 passed in 2.67s (no failures, no errors).
- Redaction test: AWS key AKIAIOSFODNN7EXAMPLE injected into mocked transcript
  is absent from both /detail and /transcript HTTP response bodies.
- Envelope shape pinned via TypeAdapter(ClientV1Envelope[SessionDetailV1]) and
  TypeAdapter(ClientV1Envelope[SessionTranscriptPageV1]) contract validation.
- Guard note: existing test_client_v1_contract.py uses broken project_manager
  patch path (runtime_ports.project_manager vs runtime_ports.db_project_manager).
  New test uses the correct path. Pre-existing issue, not introduced by Phase 2.

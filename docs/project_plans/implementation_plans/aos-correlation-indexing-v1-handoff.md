---
schema_version: 1
status: completed
updated: 2026-07-06
source_plan: /Users/miethe/dev/homelab/development/agentic_meta_dev/.claude/plans/aos-universal-correlation-ids-v1.md
contract: /Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/aos-correlation.md
---

# AOS Correlation Indexing v1 - CCDash Handoff

## Goal

Let CCDash ingest and search AOS IDs from final-turn footers, local sidecar events, and linked
Operator/IntentTree records.

## Required Work

- Add ingestion for `AOS-ID: urn:aos:turn:<uuid>` in session transcripts.
- Add sidecar-event ingestion for `$AOS_ID_HOME/events.jsonl` pointers without storing prompt or
  response bodies.
- Add derived indexes/search for turn, session, run, feature, artifact, app, service, and trace UUIDs.
- Add a session-detail affordance to show/copy the leaf AOS turn ID and navigate to parent
  run/feature/artifact where known.
- Preserve existing transcript intelligence and CCDash session ID behavior.

## Acceptance

- Search by a turn UUID resolves to its session and any linked run/artifact aliases.
- Missing sidecars, stale transcript paths, malformed JSONL, and unknown UUIDs show unresolved
  status rather than crashing ingestion or UI.
- UI copy action exposes only the leaf `AOS-ID` footer unless a user opens details.

## Validation

Add backend ingestion tests, a fixture with duplicate/malformed sidecar lines, and a focused UI/API
test for copyable AOS-ID display.

## Completion Evidence

Implemented 2026-07-06:

- Added read-time AOS correlation derivation for transcript footers and optional
  `$AOS_ID_HOME/events.jsonl` sidecar events.
- Extracts `AOS-ID: urn:aos:turn:<uuid>` plus turn/session/run/feature/artifact/app/service/trace
  aliases without copying prompt or response body fields from sidecars.
- Surfaces optional `aosCorrelation` on session list/detail payloads and session-detail query bundles.
- Adds AOS-aware session intelligence search for bare UUID and AOS URN queries before lexical fallback.
- Adds a Session Inspector affordance that copies only the leaf `AOS-ID` footer and shows parent
  run/feature/artifact aliases separately.

Validation run:

- `backend/.venv/bin/python -m pytest -q backend/tests/test_aos_correlation.py backend/tests/test_session_detail_service.py::TestGetSessionDetail::test_session_payload_includes_aos_correlation_from_transcript_urns backend/tests/test_session_intelligence_service.py::SessionIntelligenceServiceTests::test_bare_uuid_search_resolves_aos_urn_transcript_rows backend/tests/test_sessions_api_router.py::SessionApiRouterTests::test_get_session_includes_aos_correlation_for_legacy_detail_payload`
- `PATH=/opt/homebrew/bin:$PATH ./node_modules/.bin/vitest run lib/__tests__/aosCorrelation.test.ts components/__tests__/transcriptIntelligence.test.tsx`
- `backend/.venv/bin/python -m py_compile backend/services/aos_correlation.py backend/application/services/session_intelligence.py backend/application/services/agent_queries/session_detail.py backend/routers/api.py backend/models.py`
- `git diff --check`

Known repo-wide gate caveat:

- `PATH=/opt/homebrew/bin:$PATH npm run typecheck -- --pretty false` still fails on existing
  baseline errors outside this AOS slice, including `components/Dashboard.tsx`,
  `contexts/DataContext.tsx`, design-copy files under `docs/project_plans/designs/ccdash-planning/`,
  and `lib/sessionTranscriptLive.ts`.

# Live Update Platform Developer Reference

Last updated: 2026-05-02

This reference documents the shared SSE/live-update platform delivered for execution, sessions, features, tests, and ops surfaces.
Session transcripts now have an append-first topic as well, gated separately from coarse session invalidation.

## Core files

- Backend topic and contract helpers:
  - `backend/application/live_updates/contracts.py`
  - `backend/application/live_updates/topics.py`
  - `backend/application/live_updates/domain_events.py`
- Backend transport/runtime wiring:
  - `backend/adapters/live_updates/in_memory_broker.py`
  - `backend/adapters/live_updates/sse_stream.py`
  - `backend/routers/live.py`
  - `backend/runtime/container.py`
- Frontend client and helpers:
  - `services/live/client.ts`
  - `services/live/connectionManager.ts`
  - `services/live/topics.ts`
  - `services/live/useLiveInvalidation.ts`

## Topic families

- `execution.run.{run_id}`
- `session.{session_id}`
- `session.{session_id}.transcript`
- `feature.{feature_id}`
- `project.{project_id}.features`
- `project.{project_id}.tests`
- `project.{project_id}.ops`

Execution remains the append-oriented path. Session transcript updates use append-first delivery when safe, while coarse `session.{session_id}` invalidation remains the recovery path for unsafe mutations, cursor gaps, and reconnect recovery. Feature, test, and ops surfaces continue to use invalidation plus targeted REST recovery for V1.

## Session Transcript Contract

- Backend publisher helper:
  - `backend/application/live_updates/domain_events.py`
- Frontend topic helper:
  - `services/live/topics.ts`
- Frontend merge contract:
  - `types.ts`

Transcript append payloads are intentionally small and append-oriented:

- `sessionId`
- `entryId`
- `sequenceNo`
- `kind`
- `createdAt`
- `payload`

The nested `payload` mirrors the `SessionLog` fields Session Inspector already consumes, including `id`, `timestamp`, `speaker`, `type`, `content`, `agentName`, `linkedSessionId`, `relatedToolCallId`, `metadata`, and `toolCall`.

## Publisher entry points

- Execution snapshots/events:
  - `backend/db/repositories/execution.py`
  - `backend/db/repositories/postgres/execution.py`
- Session invalidation:
  - `backend/db/sync_engine.py`
- Feature invalidation:
  - `backend/routers/features.py`
  - `backend/db/sync_engine.py`
- Test invalidation:
  - `backend/routers/test_visualizer.py`
- Ops invalidation:
  - `backend/db/sync_engine.py`

## Frontend subscription conventions

- Prefer one topic per visible surface and let `sharedLiveConnectionManager` multiplex them into one browser-tab stream.
- Use `services/live/useLiveInvalidation.ts` for invalidation-only surfaces.
- Keep REST reads as bootstrap/recovery paths.
- Treat polling as fallback only. The intended fallback states are disabled rollout, closed connection, or backoff after stream errors.
- Use `pauseWhenHidden` for view-scoped surfaces so hidden tabs do not keep long-lived live subscriptions open unnecessarily.

## Rollout gates

- Backend:
  - `CCDASH_LIVE_TEST_UPDATES_ENABLED`
  - existing project-scoped testing flags still apply via `env && project`
- Frontend:
  - `VITE_CCDASH_LIVE_EXECUTION_ENABLED`
  - `VITE_CCDASH_LIVE_SESSIONS_ENABLED`
  - `VITE_CCDASH_LIVE_SESSION_TRANSCRIPT_APPEND_ENABLED`
  - `VITE_CCDASH_LIVE_FEATURES_ENABLED`
  - `VITE_CCDASH_LIVE_TESTS_ENABLED`
  - `VITE_CCDASH_LIVE_OPS_ENABLED`

Execution and sessions default on. Transcript append defaults off behind its own gate so operators can keep coarse session live updates enabled while independently rolling back append-first transcript delivery. Feature, test, and ops surfaces default off for staged rollout.

## Session Inspector Behavior

- Append in place when the transcript append event is for the active session, carries a known `entryId`, and advances the stream with a valid monotonic `sequenceNo`.
- Refetch `GET /api/sessions/{id}` when the stream emits `snapshot_required`, when append identity or ordering is ambiguous, when the active session receives an unsafe invalidation, or when the frontend rollout flag is disabled.
- Keep polling as the last-resort fallback only when live transport is degraded or closed. This is the browser recovery path for fanout outages: `components/SessionInspector.tsx` forces `getSessionById(..., { force: true })` while the live connection status is `backoff` or `closed`, so persisted transcript rows are recovered through REST even if no live append reaches the tab.

## OBS-004 Recovery Validation

OBS-004 depends on persistence being independent from live fanout and on the browser retaining a REST recovery path.

- Sync persistence: `backend/tests/test_sync_engine_transcript_canonicalization.py` patches `_publish_session_transcript_appends` to return `False` and still verifies transcript rows are written to `session_messages` in enterprise mode and to both `session_messages` and `session_logs` in local mode.
- SSE recovery signal: `backend/tests/test_live_router.py` covers transcript topic replay and `snapshot_required` when the browser cursor falls out of the broker replay buffer.
- Browser cursor recovery: `services/__tests__/liveConnectionManager.test.ts` verifies transcript-topic cursors are replayed after reconnect and cleared after `snapshot_required`, which forces the subscriber's REST snapshot handler.
- Browser REST fallback: `components/SessionInspector.tsx` uses `refreshSelectedSessionDetail` for `snapshot_required`, unsafe invalidations, ambiguous append payloads, and active-session polling while the live connection is in `backoff` or `closed`.

## Observability

- `GET /api/cache/status` now includes `liveUpdates` broker metrics.
- Current metrics include subscriber count, active topic subscriptions, buffered topics, published events, dropped events, buffer evictions, replay gaps, and subscription open/close counts.
- Ops panel renders the broker snapshot when present.

## Known V1 residual risk

Session transcript append streaming is now the normal path for safe active-session growth, but invalidation plus targeted `GET /api/sessions/{id}` recovery remains the safety net for rewrites, gaps, and recovery after reconnect or tab suspension.

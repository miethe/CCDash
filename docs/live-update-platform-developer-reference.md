# Live Update Platform Developer Reference

Last updated: 2026-03-23

This reference documents the shared SSE/live-update platform delivered for execution, sessions, features, tests, and ops surfaces.
Session transcripts now have an append-first topic as well, gated separately from coarse session invalidation.

## Core files

- Backend topic and contract helpers:
  - `/Users/miethe/dev/homelab/development/CCDash/backend/application/live_updates/contracts.py`
  - `/Users/miethe/dev/homelab/development/CCDash/backend/application/live_updates/topics.py`
  - `/Users/miethe/dev/homelab/development/CCDash/backend/application/live_updates/domain_events.py`
- Backend transport/runtime wiring:
  - `/Users/miethe/dev/homelab/development/CCDash/backend/adapters/live_updates/in_memory_broker.py`
  - `/Users/miethe/dev/homelab/development/CCDash/backend/adapters/live_updates/sse_stream.py`
  - `/Users/miethe/dev/homelab/development/CCDash/backend/routers/live.py`
  - `/Users/miethe/dev/homelab/development/CCDash/backend/runtime/container.py`
- Frontend client and helpers:
  - `/Users/miethe/dev/homelab/development/CCDash/services/live/client.ts`
  - `/Users/miethe/dev/homelab/development/CCDash/services/live/connectionManager.ts`
  - `/Users/miethe/dev/homelab/development/CCDash/services/live/topics.ts`
  - `/Users/miethe/dev/homelab/development/CCDash/services/live/useLiveInvalidation.ts`

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
  - `/Users/miethe/dev/homelab/development/CCDash/backend/db/repositories/execution.py`
  - `/Users/miethe/dev/homelab/development/CCDash/backend/db/repositories/postgres/execution.py`
- Session invalidation:
  - `/Users/miethe/dev/homelab/development/CCDash/backend/db/sync_engine.py`
- Feature invalidation:
  - `/Users/miethe/dev/homelab/development/CCDash/backend/routers/features.py`
  - `/Users/miethe/dev/homelab/development/CCDash/backend/db/sync_engine.py`
- Test invalidation:
  - `/Users/miethe/dev/homelab/development/CCDash/backend/routers/test_visualizer.py`
- Ops invalidation:
  - `/Users/miethe/dev/homelab/development/CCDash/backend/db/sync_engine.py`

## Frontend subscription conventions

- Prefer one topic per visible surface and let `sharedLiveConnectionManager` multiplex them into one browser-tab stream.
- Use `/Users/miethe/dev/homelab/development/CCDash/services/live/useLiveInvalidation.ts` for invalidation-only surfaces.
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
- Keep polling as the last-resort fallback only when live transport is degraded or closed.

## Observability

- `GET /api/cache/status` now includes `liveUpdates` broker metrics.
- Current metrics include subscriber count, active topic subscriptions, buffered topics, published events, dropped events, buffer evictions, replay gaps, and subscription open/close counts.
- Ops panel renders the broker snapshot when present.

## Known V1 residual risk

Session transcript append streaming is now the normal path for safe active-session growth, but invalidation plus targeted `GET /api/sessions/{id}` recovery remains the safety net for rewrites, gaps, and recovery after reconnect or tab suspension.

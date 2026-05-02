---
type: request-log
doc_id: REQ-20260502-ccdash
title: Live Ingest Senior Review Follow-ups (FU-2, FU-4)
project_id: ccdash
item_count: 2
tags: [api, live-fanout, reliability, session-inspector, test-coverage, web]
items_index:
  - id: REQ-20260502-ccdash-01
    type: enhancement
    title: PostgresLiveNotificationListener: reconnect with exponential backoff
  - id: REQ-20260502-ccdash-02
    type: enhancement
    title: End-to-end SSE wire-boundary smoke test for SessionInspector
created_at: 2026-05-02T19:16:58.897Z
updated_at: 2026-05-02T19:16:58.897Z
archived: false
---

## REQ-20260502-ccdash-01 - PostgresLiveNotificationListener: reconnect with exponential backoff

**Type:** enhancement | **Domain:** api | **Priority:** high | **Status:** triage
**Subdomain:** live-fanout
**Tags:** api, live-fanout, reliability

#### Notes

**Note 1: General** (Created: 2026-05-02 19:16)

Problem: If the listener fails to start (Postgres unreachable) or its connection is later evicted (Postgres restart), there is no retry — cross-process live fanout silently degrades until the API process is restarted. status_snapshot exposes running=False but recovery is manual.

**Note 2: General** (Created: 2026-05-02 19:16)

Goal: Add a supervisor that retries listener.start() with exponential backoff (e.g., 2s -> 4s -> 8s -> 30s cap) on initial failure and on detected disconnect. Integrate with container.py lifecycle. Emit retry-state metric/log so dashboards can alert on prolonged degradation.

**Note 3: General** (Created: 2026-05-02 19:16)

Source: senior-code-reviewer follow-up FU-2 from enterprise-live-session-ingest-v1 review (commit 323903b). Estimate: 3-4 pts. Touches backend/adapters/live_updates/postgres_listener.py and backend/runtime/container.py. Open design questions: supervisor task placement, retry policy bounds, observability on retry state.


---

## REQ-20260502-ccdash-02 - End-to-end SSE wire-boundary smoke test for SessionInspector

**Type:** enhancement | **Domain:** web | **Priority:** medium | **Status:** triage
**Subdomain:** session-inspector
**Tags:** web, session-inspector, test-coverage

#### Notes

**Note 1: General** (Created: 2026-05-02 19:16)

Problem: Current Phase 5 smoke (SessionInspectorLiveSmoke.test.tsx) mocks the SSE transport via FakeEventSource and asserts on synthetic emissions. The real path (backend publishes -> SSE stream -> EventSource -> LiveConnectionManager -> SessionInspector) is untested in CI. No reconnect scenario is covered.

**Note 2: General** (Created: 2026-05-02 19:16)

Goal: Add an integration smoke that exercises the wire boundary. Options: (a) MSW SSE stub driving real EventSource in jsdom, (b) backend-driven test with httpx async client + spawned API. Cover at minimum: live append delivery, invalidation handling, and reconnect-after-disconnect re-subscription.

**Note 3: General** (Created: 2026-05-02 19:16)

Source: senior-code-reviewer follow-up FU-4 from enterprise-live-session-ingest-v1 review (commit 323903b). Estimate: 2 pts. New test infra likely needed; consider whether MSW already exists in the repo before introducing new tooling. Replaces the static-string source-grep block in the existing smoke.


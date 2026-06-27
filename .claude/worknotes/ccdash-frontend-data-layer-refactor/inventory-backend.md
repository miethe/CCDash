# Backend HTTP Surface Inventory — Fat-Read Bundle Design

> Read-only inventory feeding the CCDash frontend data-layer refactor PRD + implementation plan.
> Source: codebase-explorer pass (2026-05-28). Written by orchestrator (agent write blocked by bg-isolation guard).

## 1. Surface scale

~50 GET read endpoints across 10 routers, plus a newer `/api/v1/` envelope layer (`backend/routers/client_v1.py`). `/api/v1/` responses wrap in `ClientV1Envelope` with a `meta` field.

## 2. Fat-read bundle precedents (the template to follow)

Three composed/bundled payloads already exist and are the canonical "fat read" shape to replicate:

1. **`GET /api/agent/planning/summary`** → `ProjectPlanningSummaryDTO` — composes `statusCounts`, `ctxPerPhase`, `tokenTelemetry`, per-feature summaries in one response. Helpers `_build_status_counts/_ctx_per_phase/_token_telemetry` at `backend/application/services/agent_queries/planning.py:787–857`.
2. **`GET /api/agent/planning/session-board`** → `PlanningAgentSessionBoardDTO` — Kanban groups × session cards × tallies. `backend/application/services/agent_queries/planning_sessions.py:296`.
3. **`GET /api/v1/features/{id}/modal`** → `FeatureModalOverviewDTO` — card + rollup in one call. `backend/routers/client_v1.py:265`, DTOs at `dtos.py:163`. The `/modal/{section}` pattern for lazy tab loading is already the correct architecture for FeatureModal.

ARC `read_run_bundle` is the conceptual target shape: one request composing everything a view needs above-the-fold.

## 3. Per-view waterfall → bundle candidates

| Screen | Current fan-out | Proposed bundle |
|--------|-----------------|-----------------|
| **Dashboard** | `GET /api/sessions` + `GET /api/tasks` + live-count polls | `GET /api/v1/dashboard` (sessions+tasks); keep live-count polls separate (10s TTL) |
| **ProjectBoard** | `GET /api/features?limit=5000` + `GET /api/tasks?limit=5000` (largest over-fetch) | `GET /api/v1/features?view=cards` already exists; `FeatureCardDTO` carries task counts — collapse onto it |
| **Planning page** | 3 calls: summary, graph, session-board | `GET /api/agent/planning/view` composing all, with `include=graph,session_board` |
| **Analytics** | 3–5 sequential calls | `GET /api/analytics/overview-bundle` for above-fold; tabs stay lazy |
| **FeatureModal (v2)** | already correct | migration effort = retiring legacy `GET /api/features/{id}` fallback |
| **SessionInspector** | list + detail 2-hop | detail endpoint already exists; optimize via TQ prefetch on hover, not new bundle |

## 4. Server-side query cache (distinct from client TQ cache)

`@memoized_query` decorator wraps agent_queries service methods via a `TTLCache(maxsize=512, ttl=600s)` singleton at `backend/application/services/agent_queries/cache.py:50`. **Bundle endpoints compose already-cached sub-results at ~zero extra DB cost.** This server cache is ADDITIVE to the new client-side TanStack cache — they are independent layers.

Four TTL knobs:
- `CCDASH_QUERY_CACHE_TTL_SECONDS` (600s)
- query-cache refresh warmer (300s)
- live-count cache (10s)
- system-metrics cache (30s)

## 5. Field-narrowing / sparse fieldsets

No `?fields=` sparse fieldsets exist today. Existing narrowing primitives:
- `view=` (cards vs summary on `/api/v1/features`)
- `include=` (optional section extras)
- `include_tasks: bool` on legacy `/api/features/{id}`

**Recommendation**: new bundle endpoints expose an `include=` param for optional heavy sub-payloads (graph, session_board) — narrow by default, opt-in heavy.

## 6. Pagination contract

Two schemes coexist:
- **offset** — `PaginatedResponse` at `backend/models.py:13` — used almost everywhere
- **cursor** — `nextCursor` integer on log lines at `backend/routers/api.py:819`

No unified `SESSIONS_PER_PAGE` server constant; limit defaults vary (50 sessions, hard-coded 5000 for tasks/features in client calls — the over-fetch hotspot). `/api/v1/` routes wrap responses in `ClientV1Envelope.meta`.

## 7. Implications for the plan

- Bundle endpoints are cheap to add: they compose cached agent_queries reads. Backend work is mostly DTO composition + router wiring, not new query logic.
- The 5000-limit task/feature client calls are the single biggest backend over-fetch — fixing requires narrow card DTO + offset pagination on the client.
- `include=` opt-in heavy payloads keep the default bundle small.
- Server cache + client TQ cache are complementary; document the two-layer model in the architecture guide.
- Transport-neutral pattern: any new composed reads should land in `backend/application/services/agent_queries/` first, then wire into `routers/` (and CLI/MCP if applicable).

---
it_schema: 1
schema_version: 2
doc_type: implementation_plan
feature_slug: are-we-winning-dashboard
title: "Are-We-Winning Dashboard v1 — implementation plan"
status: not_started
planning_maturity: draft
created: 2026-08-14
updated: 2026-08-15
tier: 2
priority: high
points: "8-13"
risk_level: medium
context_class: C2
prd_ref: docs/project_plans/PRDs/features/are-we-winning-dashboard-v1.md
plan_ref: null
category: features
changelog_required: true
itt_node_id: node_01M009H6DGAKD5VCC8QCM0KP0K
intenttree_workspace: ws_01KV8VMWX9EJ6VDQKEBMYQZRXG
intenttree_tree: tree_01KVTH95F7P7CXK3QH9ZMECM5T
related_documents:
  - docs/project_plans/PRDs/features/are-we-winning-dashboard-v1.md
  - .claude/worknotes/are-we-winning-dashboard/measured-data-availability.md
  - backend/application/services/agent_queries/intent_node_cost.py
  - backend/application/services/agent_queries/system_metrics.py
acceptance_criteria:
  - "Weekly created/completed/reopened trendlines and the self-caught ratio render from CCDash's own cache with zero live IntentTree calls and zero model calls on the render path."
  - "Every rendered count (per week per trendline; each ratio bucket) drills through to its exact underlying IntentTree node rows."
  - "The self-caught ratio is a closed 3-bucket vocabulary (self-caught / other-caught / unknown); unknown is expected to dominate and is never silently folded into a percentage."
open_questions:
  - "OQ-1 (from PRD, unresolved here by design): per-actor IntentTree token provisioning is the durable fix for the self-caught discriminator; out of scope for this plan."
decisions:
  - decision: "OQ-2 — bucket weekly trendlines by ISO calendar week (Mon-Sun), not a rolling 7-day window."
    rationale: "Fixed week boundaries give a stable cache key so weekly rollups can be precomputed once per week and reused on every render, satisfying the zero-render-compute posture (FR-6). A rolling 7-day window has no stable boundary and would force recomputation on every request."
    status: accepted
  - decision: "OQ-3 — ingest and derive on a dedicated scheduled job, not the existing worker/watcher filesystem-sync cadence."
    rationale: "Worker/watcher cadence is triggered by local JSONL filesystem changes; IntentTree's event log is an unrelated HTTP source with its own staleness tolerance. A dedicated interval-based job (registered the same way as other worker background jobs) can be tuned independently and stays fail-soft per FR-9 without coupling to filesystem-sync semantics it has nothing to do with."
    status: accepted
  - decision: "OQ-4 — drill-through opens via the existing planning modal-first navigation pattern (lib/planning-routes.ts), with the modal opened only from a user click handler, never written on chart render/effect."
    rationale: "Reuses an established pattern instead of inventing a new one. The explicit constraint that the write happens only in a click handler is required because recharts 3.x trap #3 (a chart writing to searchParams on render loops the page) previously broke FeatureDetailShell and SessionInspector — drill-through is exactly the feature most likely to repeat that mistake."
    status: accepted
routing_constraints:
  - "Reopened-derivation correctness (M2) MUST stay claude-primary — a wrong terminal-status transition boundary is silently plausible and would misreport regression, not just render wrong."
  - "Self-caught bucketing logic (M2) MUST stay claude-primary — misrouting a node into self-caught/other-caught instead of unknown when the proxy signal is absent is silently plausible and violates the never-silently-divide requirement."
  - "Cursor-paginated ingestion plumbing (M1) and weekly created/completed rollup aggregation (M2, direct event counts) are offload-eligible — mechanical, verifiable by row count."
  - "Frontend chart wiring that extends TrendChart/InteractiveChartCard (M3) is offload-eligible; the runtime browser smoke verification itself is not — it must be performed and its evidence recorded, never skipped in favor of a unit-test pass."
wave_plan:
  waves: [["M1"], ["M2"], ["M3"]]
  phases:
    - id: M1
      title: "IntentTree lifecycle events are durable in CCDash"
      depends_on: []
      exit_criteria:
        - "node.created and node.completed events are cursor-paginated into a dual-DDL CCDash cache; ingestion fails soft on IntentTree API unavailability."
      gate_lens: [validator]
    - id: M2
      title: "Weekly rollups, reopened derivation, and the self-caught ratio are correct"
      depends_on: ["M1"]
      exit_criteria:
        - "A transport-neutral query service returns weekly created/completed/reopened counts and the 3-bucket self-caught ratio, each with a drill-through row lookup, entirely from cache."
      gate_lens: [validator]
    - id: M3
      title: "Dashboard view is reviewable in the product"
      depends_on: ["M2"]
      exit_criteria:
        - "The extended Analytics dashboard renders the trendlines and ratio widget with working drill-through; runtime browser smoke passes."
      gate_lens: [validator]
pr_refs:
  - '#71'
---

# Implementation Plan — Are-We-Winning Dashboard v1

CCDash today holds zero IntentTree lifecycle-event data. When this plan is done, CCDash ingests
that event log into its own cache, derives a reopened trendline and an honestly-bucketed
self-caught ratio from it, and renders both — plus the direct created/completed rollups — in an
extended Analytics dashboard view with drill-through on every count, entirely off cached data.

## Scope boundary

**In:** IntentTree event ingestion (`node.created`, `node.completed`), weekly created/completed
rollups, bounded reopened derivation, 3-bucket self-caught ratio, drill-through query + REST, FE
trendline + ratio widget extending the existing Analytics module.

**Out (stated, not silently dropped):** recurrence-rate-per-defect-class and gate-claims-vs-
enforcement audit status (PRD §7, separate data models, follow-on PRDs); any backfill of
historical self-caught attribution (permanently impossible per the worknote — the shared
service token collapsed every actor to `system`); per-actor IntentTree token provisioning (the
upstream fix, IntentTree-side, not this repo).

## Rubric — what "good" looks like

The render path never calls IntentTree or a model, ever, under any code path a reviewer can find —
not just the common one. Every number a user can see has a real drill-through, not a decorative
click target. The self-caught ratio's `unknown` bucket is visually prominent, not a muted footnote
— it dominating is the correct rendering of the measured reality (worknote: 17/200 and 7/200
sampled nodes carry any discriminator at all), and hiding that would misrepresent the feature.
Reopened derivation only ever walks the ever-completed node set (745 today), never the full tree.
Any new column ships with SQLite + Postgres DDL in the same commit; a plan that ships one backend
only is not done.

## Named risks

- **Local SQLite is an empty stub for IntentTree data.** A green local-SQLite run proves nothing
  about operability — verify ingestion, dual DDL, and the query service against Postgres (`npm run
  docker:hosted:smoke:seeded-pg`) before considering M1/M2 done.
- **Postgres-only `@memoized_query` cache-write hazard.** `PostgresCacheBackend.aset` previously
  stringified pydantic return values via an unguarded `json.dumps(default=str)`, 500-ing on
  Postgres only (fixed main `579aaf2`) — local SQLite cannot reproduce this. Any new
  `@memoized_query` surface in M2 must be exercised against Postgres, not just SQLite.
- **recharts 3.x trap 1 — pie/ratio widget blank ~500ms** unless `isAnimationActive={false}`.
- **recharts 3.x trap 2 — never key `ResponsiveContainer`**; it causes an infinite render loop
  that blanks the whole page.
- **recharts 3.x trap 3 — a chart writing to `searchParams` on render loops** (broke
  `FeatureDetailShell` and `SessionInspector` previously). Drill-through is the feature most likely
  to repeat this; OQ-4's decision above exists specifically to prevent it.
- **Self-caught proxy signal has thin, uneven coverage** (17/200, 7/200 sampled). Do not let this
  read as a bug to "fix" by inflating a bucket — it is the measured reality; ship the honest
  `unknown`-dominant ratio per the rubric.

## References

- `.claude/worknotes/are-we-winning-dashboard/measured-data-availability.md` — mandatory ground
  truth: event counts, `GET /api/v1/events` pagination cap (200/page), `GET
  /api/v1/nodes/{node_id}/history`, recharts traps, frontend reuse surface.
- `backend/application/services/agent_queries/intent_node_cost.py` +
  `backend/db/repositories/entity_graph.py` `INTENT_NODE_LINK_*` — closest existing pattern (reads
  CCDash's own `entity_links`, not IntentTree's event log — this ingestion is net-new).
- `backend/application/services/agent_queries/system_metrics.py` — sibling transport-neutral,
  cache-backed cross-project metrics service; same shape to follow for M2's query service.
- `backend/parsers/ica_spend.py` (`decide_attribution`) — the closed-vocabulary,
  never-silently-divide pattern the self-caught ratio must mirror.
- `backend/db/migration_governance.py` (`COLUMN_PARITY_DRIFT_ALLOWLIST`,
  `validate_migration_governance_contract`) — the dual-DDL parity mechanism this plan's new
  table/columns must pass.
- `components/Analytics/TrendChart.tsx`, `components/Analytics/primitives/InteractiveChartCard.tsx`
  — extend these; do not build a parallel chart stack. `lib/planning-routes.ts` — reuse for
  drill-through per OQ-4's decision.

## Milestones

### M1 — IntentTree lifecycle events are durable in CCDash

A new dual-DDL (SQLite + Postgres) cache holds `node.created` and `node.completed` events, kept
current by a cursor-paginated (never single-call — the API caps at 200 rows/page), fail-soft
scheduled ingestion job. IntentTree downtime never blocks ingestion from resuming later, and never
touches the render path.

**AC:** ingestion persists all `node.created`/`node.completed` rows without relying on a single
uncapped call; a simulated IntentTree-unreachable run leaves the cache untouched and does not
crash; the new table/columns pass `validate_migration_governance_contract` with zero undocumented
`COLUMN_PARITY_DRIFT_ALLOWLIST` drift; parity is verified against a live Postgres backend, not
SQLite alone.

### M2 — Weekly rollups, reopened derivation, and the self-caught ratio are correct

A transport-neutral service in `backend/application/services/agent_queries/` computes: weekly
created/completed counts (direct rollup, ISO-week bucketed per the OQ-2 decision), a reopened
trendline derived by walking per-node status history bounded to the ever-completed node set only,
and a self-caught ratio in the closed `self-caught`/`other-caught`/`unknown` vocabulary. A
drill-through query returns the exact underlying node rows for any count. All of this is exposed
via REST and computed with zero live IntentTree calls and zero model calls at request time.

**AC:** unit tests cover the ISO-week bucket boundary, the reopened-derivation scope boundary
(asserts the query only ever touches the ever-completed set, not all nodes), and the ratio's
`unknown`-bucket behavior when the proxy signal is absent; drill-through returns real node rows for
at least one entry per bucket/trendline; the query service is exercised against Postgres to rule
out the `@memoized_query` cache-write hazard; a code-path trace/test shows no external HTTP or
model call fires when the REST endpoint is hit with a warm cache.

### M3 — Dashboard view is reviewable in the product

The Analytics dashboard is extended (not parallel-built) with the three trendlines and the ratio
widget, `unknown` rendered as a first-class visible element, and drill-through wired via the
modal-first pattern per the OQ-4 decision. A feature flag gates the new ingestion job and REST
surface.

**AC:** the view renders real cached data with a working drill-through on every count; a runtime
browser smoke check (per CLAUDE.md's runtime-smoke gate — a clean unit-test pass alone is
explicitly insufficient) confirms no `ResponsiveContainer` key-loop, no blank-pie flash, and no
`searchParams`-write-on-render loop; CHANGELOG `[Unreleased]` entry added.

## AC -> command -> evidence

| AC | Command | Evidence of pass |
|---|---|---|
| M1 dual DDL / parity | `backend/.venv/bin/python -m pytest backend/tests/test_migration_governance.py -v` | Passes; new table/columns present in both SQLite and Postgres DDL blocks with zero undocumented drift. |
| M1 operable on Postgres (not SQLite-green only) | `npm run docker:hosted:smoke:seeded-pg` | Smoke script exits 0 against the seeded Postgres stack, not local SQLite. |
| M1 pagination + fail-soft | `backend/.venv/bin/python -m pytest backend/tests/ -k "intenttree" -v` | New ingestion tests pass: pagination beyond the 200-row cap is exercised; a simulated-unreachable case leaves cache state unchanged. |
| M2 bucketing / derivation / ratio correctness | `backend/.venv/bin/python -m pytest backend/tests/ -k "are_we_winning or self_caught or reopened" -v` | Passes: ISO-week boundary, ever-completed-only derivation scope, `unknown`-bucket behavior all asserted. |
| M2 zero render-path calls | Code review of the query-service call graph + a request-path test with network calls mocked to raise | No external HTTP/model client invocation reachable from the REST handler on a warm cache. |
| M3 render + drill-through | `npm run dev` then manual click-through of every trendline point and ratio bucket | Every count opens its underlying node-row list; no console error. |
| M3 runtime smoke (mandatory, not substitutable by tests) | Manual browser smoke per CLAUDE.md runtime-smoke gate | No `ResponsiveContainer` key-loop, no pie blank flash, no `searchParams` render-loop; recorded with `runtime_smoke: passed` (or `skipped` + reason) before milestone close. |

## Execution ledger

Deviations and conservative choices are logged with rationale to
`.claude/worknotes/are-we-winning-dashboard/implementation-notes.md` and reviewed at each milestone
boundary — rather than halting on them.

**Blockers still stop** (a failing test on current work, an unsatisfiable declared artifact,
exhausted recovery). Beyond those, mid-milestone halts are only for: destructive action, real scope
change, or input only the operator has.

**Mode-D boundaries are unchanged and non-negotiable**: auth · payments/billing · schema migrations
· data deletion · secret rotation · infrastructure. This plan's schema migrations (M1's new
cache table) are additive-only and non-destructive, but the schema-migration Mode-D boundary still
applies — halt for explicit approval before applying it to a shared Postgres instance.

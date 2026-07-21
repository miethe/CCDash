---
schema_version: 2
doc_type: design_spec
title: "RF Run Telemetry: IntentTree intent_id/task_node_id Resolution"
status: draft
maturity: idea
created: 2026-07-21
updated: 2026-07-21
feature_slug: research-foundry-run-telemetry
feature_version: v1
prd_ref: docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md
plan_ref: docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md
spike_ref: docs/project_plans/exploration/research-foundry-run-telemetry/spikes/risk-spike.md
adr_refs: []
related_documents:
- docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1/phase-2-run-entity-correlation.md
- docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1/phase-3-analytics-tab.md
- ../../../../research-foundry/docs/project_plans/design-specs/research_foundry_search_router_spec.md
priority: low
risk_level: low
category: integration-design
tags:
- research-foundry
- intenttree
- correlation
- deferred
- cross-system
- opaque-id
problem_statement: >
  `research_runs` rows carry RF's `intent_id`/`task_node_id` as opaque display-only strings
  (OQ-5, D2). An operator viewing the run-level drill table or KPI strip sees these ids as
  inert text with no way to jump to the IntentTree node they name. Resolving them into
  human-readable labels or clickable links requires a live call to a system CCDash's backend
  does not currently have a client for: the IntentTree API.
open_questions:
- "OQ-D7-1: Does resolution happen at ingest time (denormalize a resolved label onto the
  research_runs row when the event is persisted) or at query time (run_intelligence.py calls
  IntentTree per request/batch)? Ingest-time avoids per-request latency and degrades cleanly
  if IntentTree is unreachable at ingest; query-time stays current if a node is renamed after
  ingest but adds a live external dependency to every run-detail read."
- "OQ-D7-2: What IntentTree API surface would this call? Per the agentic_meta_dev IntentTree
  integration rule, the canonical endpoint is the node's `itt` API at the AOS node instance
  (10.42.10.76:8032 under the standing `aos-target set node` default), not a local CLI
  round-trip. CCDash's backend has no HTTP client, auth, or retry/circuit-breaker wiring for
  that endpoint today, and the node is not treated as a CCDash service dependency anywhere in
  `backend/config.py`."
- "OQ-D7-3: Is `task_node_id` always a child of `intent_id` in IntentTree's tree model, and if
  so, should CCDash resolve only the leaf node or the full ancestor path (breadcrumb)? Not
  established — no IntentTree schema reference has been reviewed as part of this PRD."
- "OQ-D7-4: What is the resilience contract when IntentTree is unreachable? The existing
  ingest_sources[] freshness pattern (idle/connected/backed_up/disconnected) is a plausible
  precedent, but IntentTree resolution is a read-side enrichment, not an ingest source — a
  new degrade-to-opaque-string fallback path would need to be designed explicitly so a
  resolution failure never blocks or empties the run-detail response."
explored_alternatives:
- "Option A (Deferred — CURRENT, v1 shipped): Store intent_id/task_node_id as opaque
  display-only string attributes on research_runs (D2). Render them as plain text, never as
  clickable links, in the run-level drill table and KPI strip (Phase 3 AC). Zero external
  dependency; zero new failure mode; operator gets the raw id for manual cross-reference
  against IntentTree's own UI/CLI (itt show <id>) if needed."
- "Option B (Ingest-time resolution): When an rf_events row is persisted, best-effort call the
  IntentTree node API to resolve intent_id/task_node_id into a human-readable label
  (node title, tree name, status) and denormalize it onto the research_runs row alongside the
  raw id. Fail-open: a failed or unreachable call leaves the resolved-label column null and the
  raw opaque string still renders. Requires: an IntentTree HTTP client + auth in CCDash's
  backend, a new nullable column pair (e.g. intent_label, task_node_label) on research_runs
  (dual DDL), and a decision on retry/backoff since ingest is where CCDash's fail-open contract
  is strictest today (FR-1 resilience clause)."
- "Option C (Query-time resolution with cache): run_intelligence.py resolves intent_id/
  task_node_id against IntentTree on read, with a short-TTL in-memory or DB-backed cache to
  avoid a live external call on every run-detail request. Keeps labels current if IntentTree
  nodes are renamed after ingest, at the cost of a live dependency on every read path and a
  new caching layer to design and test. Higher implementation cost than Option B for a
  correctness benefit (freshness) that has not been validated as operator-valuable."
- "Option D (EntityLinkButton-style deep link only, no label resolution): Skip resolving a
  human-readable label entirely; instead render a clickable link that opens IntentTree's own
  UI/CLI output for that node id (e.g. a URI scheme or a copy-to-clipboard `itt show <id>`
  affordance), reusing the existing EntityLinkButton visual pattern from the run-level drill
  table without a backend resolution call at all. Cheapest option that still improves on plain
  text, but does not surface the node's title/status inline — the operator still has to leave
  CCDash to see what the id names."
---

# RF Run Telemetry: IntentTree intent_id/task_node_id Resolution

**Deferred item**: DF-007 from `docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1/phase-4-hardening-docs.md` (T4-007), tracing to PRD §12 "IntentTree `intent_id`/`task_node_id` resolution" and OQ-5.

**Maturity**: idea — the problem and the v1 fallback behavior are well understood, but the
resolution mechanism (ingest-time vs. query-time), the IntentTree API surface it would call, and
the resilience contract for that call are all unresolved. Do not promote to `shaping` until the
unblock condition below is met and OQ-D7-1/OQ-D7-2 have working answers.

---

## 1. Context

Research Foundry (RF) search runs carry two correlation-shaped ids that are meaningful inside
IntentTree's task-graph model but are opaque to CCDash:

- `intent_id` — the IntentTree intent node a search run was launched under.
- `task_node_id` — the specific IntentTree task node, if the run was dispatched as part of a
  bound task (per the `aos-operator`/`op` binding model — see `ITT_NODE_ID` in the
  agentic_meta_dev IntentTree integration rule).

Per D2 (PRD §7 "Decisions"), CCDash's run↔session correlation is keyed exclusively by a genuine
UUID `run_id` via `entity_graph.py` entity-link rows — RF's `intent_id`/`task_node_id` are
explicitly **not** join keys and are stored only as display-only string attributes on the
`research_runs` row (FR-9). This was a deliberate scope boundary for v1: RF's ids are non-UUID
semantic slugs (risk spike, confidence 0.75) that would corrupt the AOS URN graph if force-fit
into `aos_correlation.py`'s UUID/URN join logic.

The consequence, confirmed for Phase 3 (`phase-3-analytics-tab.md` AC "resilience" clause):
`intent_id`/`task_node_id` render as opaque display strings only, never as clickable links, in
the run-level drill table and KPI strip.

---

## 2. Problem

An operator looking at the Provider Economics tab's run-level drill table sees a raw string like
`intent-8f2a91` or a UUID-shaped `task_node_id` with no context — no node title, no tree name, no
status, no way to navigate to the corresponding IntentTree node without leaving CCDash and
querying IntentTree separately (`itt show <id>` or the IntentTree UI). This is a legibility gap,
not a data-integrity one: the raw id is stored correctly and displayed correctly per its v1
contract (opaque string). The gap is that the id names something CCDash cannot yet describe.

This is functionally identical in shape to the `EntityLinkButton` pattern CCDash already uses for
`linked_session_id` (clickable link to `SessionInspector` when a session correlation exists) —
the difference is that `linked_session_id` resolves against CCDash's own database, while
`intent_id`/`task_node_id` would require an out-of-process call to a different system's API.

---

## 3. Why It Is Deferred

### 3.1 No IntentTree Client Exists in CCDash's Backend

`backend/config.py` has no IntentTree host/port/auth configuration; there is no HTTP client
module for the IntentTree API anywhere in `backend/`. IntentTree is reached today only via the
`itt` CLI or the `intenttree` skill, both operator-tier tools, not a CCDash service dependency.

### 3.2 Cross-System Dependency Risk

Per the agentic_meta_dev IntentTree integration rule, IntentTree's canonical endpoint is the AOS
node instance (`10.42.10.76:8032` under the standing `aos-target set node` default) — a shared
LAN service outside CCDash's own deploy lifecycle. Wiring a live dependency on it into a query
path that CCDash's own resilience contracts treat as "must never null-coalesce or 0-mask an
absent value" (AC-4, FR-14) requires a resilience design CCDash does not yet have for
externally-owned, non-CCDash-authored APIs. (`/api/v1/ingest/*` and the RF telemetry event itself
are both push-based and fail-open on the *sender's* side; IntentTree resolution would be the
first *pull*-based, CCDash-initiated call to an external non-RF system.)

### 3.3 Contained Scope Boundary (D2)

D2 was locked specifically to keep this PRD's correlation surface (`entity_graph.py`,
`aos_correlation.py`) untouched. Any IntentTree resolution design must preserve that boundary —
resolution is a **read-side label enrichment**, not a new join key or a new entity-link kind.

### 3.4 Unvalidated Operator Value

No operator report or usage signal currently indicates that raw `intent_id`/`task_node_id`
strings are causing confusion or lost context in practice (contrast with the F-W6-001 precedent,
which was surfaced by an audit, not by design). This is a legibility improvement on a Should/nice
level, not a Must — consistent with its `idea`-maturity, deferred status.

---

## 4. Unblock Condition

Per PRD §12, the named unblock condition is:

> **IntentTree API access is wired for CCDash's backend** (today `intent_id` is stored and
> displayed as an opaque string only).

Concretely, this means all of the following exist before this spec can be promoted to `shaping`:

1. CCDash's backend has an HTTP client module for the IntentTree node API (host/port/auth
   configured via `backend/config.py`, following the same `CCDASH_*` env-var convention as every
   other external dependency — e.g. `CCDASH_INTENTTREE_API_URL`, `CCDASH_INTENTTREE_API_TOKEN`).
2. A resilience contract for that client is designed and tested: timeout, retry/backoff (or
   explicit no-retry), and a **degrade-to-opaque-string** fallback so an unreachable IntentTree
   node never blocks, nulls, or errors a `research_runs` read.
3. A decision is made and recorded (OQ-D7-1) on ingest-time denormalization vs. query-time
   resolution vs. deep-link-only (Options B/C/D in this spec's `explored_alternatives`).

---

## 5. Prerequisites Before Implementation

1. **IntentTree API contract review** (OQ-D7-2, OQ-D7-3): confirm the exact endpoint shape for
   resolving a node id to a label/status/ancestor path, and whether `task_node_id` requires a
   distinct call from `intent_id` or shares one endpoint.
2. **Resilience design** (OQ-D7-4): define the fallback contract explicitly — this is the first
   CCDash read path with a pull-based dependency on a non-RF external system, so no existing
   precedent (ingest_sources freshness states) transfers without adaptation.
3. **Dual-DDL column addition, if Option B is chosen**: any denormalized label column on
   `research_runs` follows the standard dual SQLite+Postgres DDL + `retry_on_locked` +
   direct-count test + column-parity allowlist rule (ADR-007), same as every other write path in
   this feature.
4. **D2 boundary re-confirmation**: whichever option is chosen, resolution must not introduce
   `intent_id`/`task_node_id` as an `entity_graph.py` join key — it remains a label enrichment on
   top of the existing display-only attribute, never a correlation mechanism.

---

## 6. Related Specs

- **Parent PRD's correlation dedup precedent (D5)**: `docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md`
- **Phase 2 run entity + correlation plan** (defines the `intent_id`/`task_node_id` display-only DTO fields this spec would extend): `docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1/phase-2-run-entity-correlation.md`
- **Phase 3 analytics tab plan** (defines the current opaque-string rendering contract this spec would change): `docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1/phase-3-analytics-tab.md`
- **IntentTree SDLC integration rule** (agentic_meta_dev, canonical endpoint + binding model reference): `agentic_meta_dev/.claude/rules/intenttree-integration.md`

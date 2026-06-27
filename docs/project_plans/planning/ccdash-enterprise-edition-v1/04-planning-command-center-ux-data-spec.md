---
schema_version: 2
doc_type: design_spec
maturity: shaping
title: "Planning Command Center — UX & Data Spec (Multi-Project Control Plane)"
status: draft
created: 2026-05-30
updated: 2026-05-30
feature_slug: ccdash-enterprise-edition-v1
audience: [ai-agents, developers]
related_documents:
  - docs/project_plans/planning/ccdash-enterprise-edition-v1/README.md
---

# Planning Command Center — UX & Data Spec (Multi-Project Control Plane)

> Target experience for the centralized, multi-project planning command center, plus the
> data/API plan to serve it fast at `skillmeat` scale. This spec **builds on what already
> exists** — modal-first navigation, the 7-tab feature shell, the V1 command-center
> list/card/board, the agent session board + forensics detail, and the multi-project command
> center (currently flagged off). It does not propose a rewrite.
>
> Phasing follows the steering brief exactly: **Phase 5 — Command Center as Multi-Project
> Control Plane** is the home of this spec, and it **depends on Phase 2 (cache/query
> correctness) and Phase 3 (DB-backed registry + multi-project worker) data contracts**
> (synthesis-brief.md §7). ARC/MeatyWiki are net-new, capability-gated, and land in Phase 5+.
> This is a planning/analysis document — no application code is modified here.

---

## 1. Vision & Principles

The command center is the **default landing surface** for an operator running many projects
through AI agents. Today, `/planning` is single-project, dumps every section into one vertical
stack, and fires **5 concurrent cold-load requests** on entry (view, command-center,
session-board, sessions, features) — planning-frontend.md §2. The V1 `PlanningCommandCenter`
bypasses TanStack Query entirely (raw `useEffect`, `PlanningCommandCenter.tsx:133–161`), so
every navigation re-fetches cold. The session board has **no pagination** and **no
virtualization** (planning-frontend.md CRIT-01, HIGH-03). At enterprise scale (10+ projects ×
1000+ sessions) this is unusable.

### Principles

1. **High-signal by default, progressive disclosure.** The default view shows four attention
   lenses — **active-now / changed-recently / needs-attention / next-work** — not an
   everything-dump. This is the steering decision (synthesis-brief.md §5). Detail is fetched on
   drill-down, not pre-loaded.
2. **Multi-project is the default, gated by a runtime flag.** `MULTI_PROJECT_COMMAND_CENTER_ENABLED`
   is a **build-time** Vite constant today (`constants.ts:418–421`, planning-frontend.md MED-03)
   — changing it requires a rebuild. Phase 5 replaces this with a **runtime capability flag**
   served by the existing `getLaunchCapabilities()` path (PlanningHomePage.tsx:946).
3. **Summary cheap, detail lazy.** The default page never loads transcripts, full graphs, full
   phase task lists, or per-item git probes. Those are detail-payload concerns (data-contracts.md §7).
4. **Two doors to a feature: modal (in-context) and route (focus/share).** Keep modal-first
   drill-down (already wired via `planningRouteFeatureModalHref`, `services/planningRoutes.ts:41`)
   AND add a deep-linkable `/planning/feature/:id` route (§4).
5. **Resilience-by-default.** Every new optional backend field (e.g. `tokenUsageByModel`, live PR
   status, ARC/MeatyWiki) requires an explicit FE fallback. A missing field is a **contract
   state**, not a bug (root `CLAUDE.md`).
6. **No synthesized fictions.** Today's sparkline (`PlanningHomePage.tsx:135–142`) and
   "tokens saved %" (`line 127`) are fabricated client-side (planning-frontend.md LOW-02). Phase 5
   either backs these with real data or removes them.

---

## 2. Information Architecture

### 2.1 Default view — multi-project portfolio

The default `/planning` view is the **portfolio**, not a single project. It is rendered by a
runtime-flagged `MultiProjectCommandCenter` (`components/Planning/CommandCenter/MultiProjectCommandCenter.tsx`)
once the gate is runtime-resolved (§9). Backend already supports this:
`GET /api/agent/planning/multi-project/command-center` (`agent.py:835`, cached as
`mpcc_command_center`) and `GET /api/agent/planning/multi-project/session-board` (`agent.py:913`,
cached as `mpss_session_board`) — data-contracts.md row "Multi-project command center aggregate"
= DONE.

```
┌─ Portfolio Top Bar ──────────────────────────────────────────────┐
│  Cmd-K search │ project filter chips │ live-agent pill │ New Spec │
├──────────────────────────────────────────────────────────────────┤
│  PORTFOLIO RAIL  │  ATTENTION COLUMNS (cross-project, default)    │
│  per-project     │  ┌─ Active Now ─┬─ Changed ─┬─ Needs ─┬─ Next ┐│
│  lanes:          │  │ live sessions│ recently  │ Attn    │ Work  ││
│   skillmeat  ▓▓  │  │ + in-progress│ updated   │ blocked │ ranked││
│   ccdash     ▓   │  │ features     │ features  │ stale   │ backlog││
│   meatywiki  ·   │  │              │           │ mismatch│       ││
│  (color/group/   │  └──────────────┴───────────┴─────────┴───────┘│
│   sort from      │                                                 │
│   ProjectDisplay │  [ List | Cards | Board ] view toggle           │
│   Config)        │                                                 │
└──────────────────┴─────────────────────────────────────────────────┘
```

### 2.2 Per-project lanes

The **portfolio rail** uses `ProjectDisplayConfig` (color, group, sortOrder, labelOverride;
data-contracts.md §1.1, `resolve_display_metadata()`) — already DONE. Each lane shows a compact
roll-up: active session count (from `mpss_session_board`), in-progress feature count, and a
needs-attention badge. Clicking a lane **filters** the attention columns to that project (does
not navigate away).

### 2.3 Attention columns (the four lenses)

These reuse the existing attention-derivation pattern in `PlanningSummaryPanel` (stale / blocked /
mismatched from `summary.staleFeatureIds`, `blockedFeatureIds`, `reversalFeatureIds`;
planning-frontend.md §1.6) but extended cross-project and augmented:

| Column | Source today | New work for Phase 5 |
|---|---|---|
| **Active Now** | `mpss_session_board` live sessions + active features | None (data exists; just surface cross-project) |
| **Changed Recently** | `Feature.updatedAt` (indexed: `features` `status+updated`, data-contracts.md §9) | New: ranked-by-recency cross-project query (§7.1) |
| **Needs Attention** | `blockedFeatureIds`/`staleFeatureIds`/`reversalFeatureIds` per project | Aggregate across projects in the rollup endpoint (§7.1) |
| **Next Work** | `status_counts.shaping + .planned` counts only (PARTIAL, data-contracts.md row) | New ranked **available-next-work** endpoint (§7.2) |

> **Quick drill-down**: every row/card in every column opens the feature via modal-first
> navigation (§4), with hover-prefetch that — unlike today — **populates the TQ cache**
> (planning-frontend.md HIGH-02 fix).

### 2.4 Runtime flag, not build-time

`MULTI_PROJECT_COMMAND_CENTER_ENABLED` moves from `import.meta.env` (`constants.ts:418–421`) to a
**capability field** returned by the launch-capabilities surface (PlanningHomePage.tsx:946). When
the capability is off, the page falls back to the single-project V1 command center for the active
project (preserving today's behavior). This is the steering decision (synthesis-brief.md §5, §6.7).

---

## 3. Active Project / Plan / Feature Model — what a "work item" is

A command-center **work item** is the unit of attention. It is a **feature joined to its plan,
phase, status, and links**. The data already exists across these contracts (data-contracts.md
§1.2–1.6):

```
WorkItem
  identity:   Feature.id, name, slug, summary, category, tags, owners, priority
  status:     PlanningEffectiveStatus { rawStatus, effectiveStatus, mismatchState }
              + statusBucket ∈ {shaping|planned|active|blocked|review|completed|deferred|stale_or_mismatched}
  plan:       FeaturePrimaryDocuments { prd, implementationPlan, phasePlans[], progressDocs[] }
  phase:      current/next/total from feature_phases (FeaturePhase: phase, title, status, progress, batches[])
  links:      linkedDocs[], linkedFeatures[], linkedSessions (forensics), prRefs[], commitRefs[]
  signals:    qualitySignals { blockerCount, atRiskTaskCount }, dependencyState
  execution:  command (string, targetArtifactPath, alternatives[]), worktree, gitState, launchBatch
  artifacts:  SkillMeat artifacts[] (DONE — surface in detail, §10.1)
```

- **statusBucket** precedence is already computed by `_build_status_counts` (`planning.py:788`):
  `blocked > review > active > planned > shaping > completed > deferred > stale_or_mismatched`
  (data-contracts.md §3.1). The command center buckets items the same way via `bucketCommandCenterItem`.
- **Phase status** lives in `feature_phases` (`sqlite_migrations.py:452`) + `data_json` BLOB
  (data-contracts.md §1.3). The "next phase" is derived (`PlanningCommandCenterPhaseDTO.next_phase`).
- **Plan ↔ feature linkage** is the `featureSlugCanonical` join on `documents` (data-contracts.md §1.6,
  indexed `feature_slug_canonical`).

The **active project** remains request-scoped via `X-CCDash-Project-Id` (synthesis-brief.md §3),
but in the multi-project default, a work item is always tagged with its `project_id` so cards can
be rendered cross-project and drill-down can rebind project scope.

---

## 4. Drill-Down Model — modal-first AND deep-linkable route

**RECOMMENDATION: keep modal-first in-context drill-down AND add a deep-linkable detail route
`/planning/feature/:id`.** This is the steering decision (synthesis-brief.md §5 UX decision).

### 4.1 Why both

- **Modal-first is already correct and shipped.** `planningRouteFeatureModalHref`
  (`services/planningRoutes.ts:41`) generates `/planning?feature=<id>&modal=feature&tab=<tab>`; the
  page resolves modal state from `useSearchParams` and renders `ProjectBoardFeatureModal` as an
  overlay (planning-frontend.md §3 = DONE). This preserves the operator's portfolio context —
  closing the modal returns to the exact scroll position and filter state. Keep it as the **default**
  for in-context inspection from a column/card/board.
- **A deep-linkable route is needed for focus and share.** A modal cannot be bookmarked, shared in
  Slack, or opened in a focused full-page mode. `planningFeatureDetailHref(featureId)` already exists
  in `services/planningRoutes.ts:93` but is not backed by a route. Phase 5 wires it to a real
  `/planning/feature/:id` page.

### 4.2 When modal vs page

| Use modal | Use `/planning/feature/:id` page |
|---|---|
| Click from an attention column / card / board on `/planning` | Direct navigation / bookmark / shared link |
| Quick triage, then return to portfolio | Focused deep-work on one feature |
| Hover-prefetch already warmed the cache | Cold entry (no portfolio context to preserve) |
| Keyboard `Esc` should return to list | Browser back returns to referrer |

### 4.3 Performance justification (shared data layer)

Both doors **share the same TQ-cached, tab-scoped data layer**, so there is no double-fetch:

- The modal and the route both render `FeatureDetailShell` (`components/FeatureModal/FeatureDetailShell.tsx`,
  7-tab shell, planning-frontend.md §1.7).
- **Fix the prefetch gap first** (planning-frontend.md HIGH-02): `prefetchFeaturePlanningContext`
  (`services/planning.ts:848`) currently bypasses TQ — it calls `getFeaturePlanningContext` directly
  and discards the result, so the modal still issues a fresh request on open. Phase 5 routes hover
  prefetch through `queryClient.prefetchQuery` keyed identically to `usePlanningFeatureContextQuery`,
  so the modal/route opens warm.
- The route `/planning/feature/:id` does **not** require `PlanningRouteLayout`'s pre-queries
  (`useSessionsQuery` + `useFeaturesQuery`, planning-frontend.md HIGH-03 / §2) — those fire today on
  every `/planning/*` route including nested ones, adding multi-megabyte payloads. The detail route
  must be excluded from those layout-level pre-queries.

---

## 5. Feature Detail Experience

`FeatureDetailShell` already has a 7-tab shell. Phase 5 extends it to the full tab set below with
**lazy per-tab loading** (tab content fetched only when the tab is activated, not hidden via the
`hidden` attribute as today — planning-frontend.md §4) and **virtualized lists** on any tab that can
exceed ~50 rows.

| Tab | Fetches from | Lazy / virtualized | Notes |
|---|---|---|---|
| **Overview** | `GET /api/agent/planning/features/{id}` (`agent.py:543`, cached `planning_feature_context`) | eager (default tab) | identity, status, phase summary, KPI strip |
| **Plan** | same context payload → `FeaturePrimaryDocuments` + `PhasePlanTable` (`phaseFiles`) | lazy | prd/impl-plan/phase-plan links + phase table |
| **Tasks** | `feature_phases[*].tasks` (from context) | lazy + **virtualized** | task list can be large; window it |
| **Sessions (live + historical)** | `GET /api/agent/features/{id}/forensics` → `FeatureForensicsDTO.linked_sessions` (data-contracts.md row "Linked sessions per feature") | lazy + **virtualized + cursor-paginated** | live = `status="active"`; historical = cursor page (§6) |
| **Artifacts** | SkillMeat: `GET /api/agent/artifact-intelligence/rankings` + recommendations (data-contracts.md §4.1, DONE) | lazy | surface existing artifact intelligence (§10.1) |
| **Research** | ARC/MeatyWiki — **MISSING** (data-contracts.md §5) | lazy, **capability-gated** | net-new, Phase 5+; empty-state until wired |
| **Council** | ARC reviews — **MISSING** (data-contracts.md §5) | lazy, **capability-gated** | net-new, Phase 5+; empty-state until wired |
| **Logs** | `GET /api/agent/features/{id}/forensics` session refs → on-demand transcript per session | lazy + **virtualized** | NEVER bulk-load transcripts; per-session on click (§6) |
| **Decisions** | open-question resolutions — today in-memory `_OQ_OVERLAY` (`planning.py:109`); DB-backed in Phase 3 | lazy | `PlanningOpenQuestionItem` list (data-contracts.md row "Open questions") |
| **Blockers** | context `qualitySignals.blockerCount` + per-phase `BlockerDTO` (data-contracts.md row "Blocked features") | lazy | DONE data; render as list |
| **Next** | `GET /api/agent/planning/next-run-preview/{id}` (planning-frontend.md §1.7) | lazy | prompt skeleton, launch readiness; copy/preview-only |

> **Per-tab fetch discipline:** Overview is the only tab fetched on open (it shares the context
> payload). Plan/Tasks/Blockers/Decisions/Next reuse the **same** `planning_feature_context`
> payload (no extra round-trip). Sessions/Logs/Artifacts/Research/Council each fetch on first
> activation. This avoids the current pattern where opening a feature implies loading everything.

---

## 6. Data Loading Strategy

### 6.1 Summary payload (default page) vs detail payload (drill-down)

This is the steering decision (synthesis-brief.md §6.5): **summary = cached, column-projected,
denormalized; detail = lazy**. The split already exists conceptually (data-contracts.md §7) but is
not enforced — every planning service does `features.list_all → SELECT * ... LIMIT 5000` including
the `data_json` BLOB (backend-api.md §6.1, §6.9).

**Summary payload** (portfolio default; one cached request per project, aggregated):
- `status_counts` (8 buckets), `feature_summaries` (FeatureSummaryItem: id, name, raw/effective
  status, mismatch, phase_count, node_count), `node_counts_by_type`,
  `blocked/stale/reversal_feature_ids`, per-project active-session count, `ctx_per_phase`,
  **`tokenTelemetry.total`** (once `tokenUsageByModel` is fixed, §7 / data-contracts.md §3.3).
- Backed by a **column-projected** `list_summary(project_id)` (backend-api.md Fix 6) selecting only
  `id, name, status, category, updated_at` (+ minimal phase summary), NOT `data_json`.

**Detail payload** (per feature, on drill-down): full planning graph, full phase+task detail, open
questions, spike items, token-by-model-family, linked artifact refs, execution context, session
cards, next-run preview (data-contracts.md §7 detail list).

### 6.2 What must NEVER be in the default payload

- **Session transcripts / logs.** The session-list N+1 already proves the cost: `GET /api/sessions`
  fetches up to 5000 log rows **per session per page** (backend-api.md §2.1, ranked #1 CRITICAL).
  Transcripts are Logs-tab, per-session, on-click only.
- **Full session board.** `GET /api/agent/planning/session-board` fetches all sessions with a
  hard-coded `limit=500` and no cursor (backend-api.md §6.10, planning-frontend.md CRIT-01). The
  default portfolio uses the **counts** from `mpss_session_board`, not the full card payload.
- **Per-item git probes.** `_build_item` spawns a `git status` subprocess **per feature** in the V1
  command center (backend-api.md §1.5, §6.4) — up to 50 synchronous subprocess spawns per request.
  MPCC already defers these via `_NullGitProbe` (backend-api.md §4.1); the default view must do the
  same and only probe page-visible items.
- **Full planning graph.** `build_planning_graph` runs per feature on cache miss (data-contracts.md
  §6.5). Graph is detail-only and should be precomputed (§7.5).
- **`Feature.data_json` BLOB.** Column-project it out of summary reads (backend-api.md §6.9).

### 6.3 Lazy / virtualized

| Surface | Lazy-mount | Virtualize |
|---|---|---|
| Session board (any) | viewport-deferred (today always-mounted, planning-frontend.md HIGH-01) | yes — V1 board has none (HIGH-03) |
| V1 command center board/list | viewport-deferred | yes — `CommandCenterBoardView` has none (MED-01) |
| Attention columns | eager (above fold) | yes if > ~50 rows (today `ROW_LIMIT=8` truncation, MED — add click-through) |
| Feature detail Tasks/Sessions/Logs tabs | lazy on tab activation | yes |

MPCC already virtualizes (`MultiProjectCommandCenter` threshold 250, `MultiProjectSessionBoard`
threshold 250 cards/col — planning-frontend.md §1.3–1.4). The **250 threshold is too high** for a
10 GB backend; Phase 5 lowers it (e.g. 60–80) so windowing engages before the DOM bloats.

### 6.4 Per-project filtering & cursor pagination

- **Per-project filtering** at the API: the portfolio rollup accepts a `project_ids[]` filter so a
  lane click scopes the aggregate without re-fanning over all projects.
- **Cursor pagination** replaces the hard-coded `limit=500` session-board scan (backend-api.md §6.10)
  and the V1 command center's hard-coded `pageSize=50` with no page > 1 (planning-frontend.md MED-02).
  Cursor over `(updated_at, id)` using the existing `idx_sessions_project_status_updated` index
  (synthesis-brief.md §6.3). The Sessions/Logs tabs and the session board both consume cursors.

---

## 7. API Requirements — NEW / CHANGED endpoints

> Add cross-domain reads in `backend/application/services/agent_queries/` first, then wire REST
> (`routers/agent.py`), CLI, and MCP per the transport-neutral pattern (root `CLAUDE.md`). Shapes
> below are sketches; `…` denotes existing fields carried through.

### 7.1 Cross-project rollup (NEW) — portfolio default payload

`GET /api/agent/planning/portfolio/rollup?project_ids=skillmeat,ccdash`

```jsonc
{
  "projects": [
    { "projectId": "skillmeat", "display": { "color": "#…", "group": "…", "sortOrder": 1 },
      "statusCounts": { "active": 12, "blocked": 3, "planned": 8, "review": 2, … },
      "activeSessions": 4, "changedRecently": 6, "needsAttention": 5,
      "tokenTotal": 184320000 }                     // requires §7 tokenUsageByModel fix
  ],
  "attention": {                                    // cross-project, pre-bucketed
    "activeNow":   [ { "featureId": "...", "projectId": "...", "effectiveStatus": "active", … } ],
    "changedRecently": [ … ],                       // ranked by Feature.updatedAt desc
    "needsAttention":  [ … ],                       // blocked|stale|mismatch ids resolved to items
    "nextWork": [ … ]                               // see 7.2
  },
  "generatedAt": "2026-05-30T…"
}
```

Build on the existing `mpcc_command_center` fan-out (`multi_project_planning_command_center.py:355`,
backend-api.md §4.1) with `asyncio.Semaphore(CCDASH_SYSTEM_METRICS_CONCURRENCY=10)`. Cached as a new
`@memoized_query("planning_portfolio_rollup")` (root `CLAUDE.md` cache tiers). Must use the
column-projected `list_summary` (§6.1), NOT `list_all SELECT *`.

### 7.2 Ranked available-next-work backlog (NEW)

`GET /api/agent/planning/next-work?project_ids=…&limit=50&cursor=…`

Today only `status_counts.shaping + .planned` **counts** exist — there is no ranked list endpoint
(data-contracts.md row "Available-next-work backlog" = PARTIAL; synthesis-brief.md §4).

```jsonc
{
  "items": [
    { "featureId": "...", "projectId": "...", "rank": 1,
      "readiness": "ready",                          // from commandCenterLaunchReadiness (DONE)
      "nextPhase": { "phase": "3", "title": "..." }, // PlanningCommandCenterPhaseDTO.next_phase
      "blockers": [], "storyPoints": 3,
      "command": { "string": "...", "targetArtifactPath": "..." } },
    …
  ],
  "nextCursor": "…"
}
```

Ranking signals (all already computed): `commandCenterLaunchReadiness` (ready/blocked/needs-context,
planning-frontend.md §6), `FeatureDependencyState` (unblocked first), `priority`, `Feature.updatedAt`
recency. No new heuristic invented — it reuses existing readiness + dependency resolution.

### 7.3 Cross-project token/cost aggregate (NEW)

`GET /api/agent/system/token-rollup?project_ids=…&period=daily`

No cross-project token/cost aggregate exists (data-contracts.md §8, backend-api.md §4.3 covers only
session counts via `system_metrics.py`). Add to `system_metrics.py` (the documented extension point
for cross-project live metrics, root `CLAUDE.md`).

```jsonc
{ "totals": { "tokensIn": …, "tokensOut": …, "costUsd": … },
  "byProject": [ { "projectId": "skillmeat", "tokensIn": …, "costUsd": … } ],
  "byModelFamily": [ { "family": "opus", "tokens": … }, { "family": "sonnet", … } ] }
```

Aggregates from `session_usage_events` / `sessions` denormalized token columns (data-contracts.md §9)
with a `GROUP BY project_id, model_family` — not per-feature Python loops.

### 7.4 Live PR status (CHANGED)

`GET /api/agent/planning/features/{id}/pr-status`

Today `Feature.prRefs` stores only the first ref string; **no live GitHub status**
(data-contracts.md row "Pull request linkage" = PARTIAL, §8; `models.py:2283`). Add a thin,
**cached** GitHub status fetch (state, checks, mergeable) keyed off `prRefs`, with a short TTL and a
fail-soft fallback to the stored ref (resilience-by-default). Capability-gated so air-gapped
enterprise deploys disable it.

### 7.5 Precomputed planning graph (CHANGED)

`GET /api/agent/planning/graph` exists (`agent.py:436`) but `build_planning_graph` runs **per
feature, per request** on cache miss (data-contracts.md §6.5, backend-api.md §1.3). Phase 2/3 work
**precomputes the graph in DB via the worker** (synthesis-brief.md §6.5); Phase 5 reads the
precomputed snapshot for the detail Graph view instead of building it in-request.

### 7.6 `tokenUsageByModel` on Feature (REQUIRED FIX)

**Telemetry is broken today.** `PlanningTokenTelemetry.source` is **always `"unavailable"`** because
`getattr(feature, "tokenUsageByModel", None)` (`planning.py:833`) returns `None` — the field does not
exist on the `Feature` model (`models.py:2052–2097`; data-contracts.md §3.3, §6.2). This breaks the
header KPI and §7.1/§7.3 token rollups.

**Fix:** add `tokenUsageByModel: Optional[TokenUsageByModel]` to `Feature` and populate it during
`feature_from_row()`, OR aggregate at summary time via a batch SQL query over `session_usage_events`
joined by feature. The working path already exists per-feature via `FeatureEvidenceSummaryService`
(`planning.py:1417`) but is not fed back to the summary level — wire that aggregation into the summary
build (data-contracts.md §3.3).

### 7.7 Integration surfaces (NEW, capability-gated — §10)

- `GET /api/integrations/meatywiki/research?feature_id=…` — research notes (MISSING today).
- `GET /api/agent/features/{id}/council` — ARC council review status (MISSING today).
- SkillMeat artifacts are **already** served (`/api/agent/artifact-intelligence/rankings`,
  `/api/integrations/skillmeat/*` — data-contracts.md §4.1); no new endpoint, just surface in detail.

---

## 8. Data Availability Matrix

Every command-center need, grounded in data-contracts.md §2 + planning-frontend.md §6. `Exists?` ∈
{exists, partial, missing}.

| Command-center need | Exists? | Source / endpoint / table | Action needed |
|---|---|---|---|
| Active plans per project (in-progress features) | exists | `GET /api/agent/planning/summary` → `status_counts.active` (`agent.py:406`) | Switch summary read to column-projected `list_summary` (backend-api.md Fix 6) |
| Current phase / phase status per feature | exists | `GET /api/agent/planning/features/{id}` → `phases`; `feature_phases` table | Lazy-load on detail; reuse shared context payload |
| Feature status (raw + effective + mismatch) | exists | `PlanningEffectiveStatus` (rawStatus/effectiveStatus/mismatchState) | None |
| Completed features | exists | `status_counts.completed`; `features.completed_at` index | Add time-ordered "recently completed" view (planning-frontend.md §6 PARTIAL) |
| Next available work (next phase per feature) | partial | `PlanningCommandCenterPhaseDTO.next_phase`; counts only | **NEW** ranked backlog endpoint (§7.2) |
| Blocked features / phases | exists | `blocked_feature_ids` in summary; `BlockerDTO` per item | Aggregate cross-project in rollup (§7.1) |
| Linked sessions per feature | partial | `GET /api/agent/features/{id}/forensics` → `linked_sessions` | Cursor-paginate + virtualize Sessions tab (§5, §6.4) |
| Linked features / dependency state | exists | `FeatureDependencyState`, `FeatureFamilySummary`, `ExecutionGateState` | Feed dependency order into next-work ranking (§7.2) |
| Linked artifacts per feature | exists | `artifacts[]` in command-center item; `PhasePlanTable.phaseFiles` | Surface SkillMeat ranking/recs in Artifacts tab (§10.1) |
| Available-next-work backlog (ranked) | partial | `status_counts.shaping + .planned` counts; no list endpoint | **NEW** `GET /api/agent/planning/next-work` (§7.2) |
| Live session status | exists | `GET /api/agent/live/active-count` (10s TTL); `mpss_session_board` | Wire SSE invalidation to board (planning-frontend.md §11 PARTIAL) |
| Active sessions board (per project) | exists | `GET /api/agent/planning/session-board` → board DTO | **Add cursor pagination** (hard-coded `limit=500`, backend-api.md §6.10) + virtualize (HIGH-03) |
| Multi-project command-center aggregate | exists | `GET /api/agent/planning/multi-project/command-center` (`mpcc_command_center`) | Runtime-flag the FE gate; lower virtualization threshold (§6.3) |
| Cross-project token/cost aggregate | partial | `system_metrics.py` session counts only; `analytics.py` per-project | **NEW** `GET /api/agent/system/token-rollup` (§7.3) |
| Token telemetry per feature (by model family) | partial | `PlanningTokenTelemetry` — always `source="unavailable"` | **FIX** add `tokenUsageByModel` to `Feature` (§7.6, data-contracts.md §3.3) |
| Live PR status | partial | `Feature.prRefs` first ref only; no GitHub status (`models.py:2283`) | **NEW** cached PR status endpoint (§7.4), fail-soft |
| Precomputed planning graph | partial | `GET /api/agent/planning/graph` builds per-feature per-request | **CHANGE** precompute in DB via worker (§7.5, synthesis-brief.md §6.5) |
| Open-question resolutions / decisions | partial | `PlanningOpenQuestionItem`; `_OQ_OVERLAY` in-memory (`planning.py:109`) | Move overlay to DB (Phase 3, synthesis-brief.md §3); then read in Decisions tab |
| SkillMeat artifact snapshots/rankings/recs | exists | `artifact_snapshot_cache`, `artifact_ranking` tables; `/api/agent/artifact-intelligence/rankings` | Surface in Artifacts tab (§10.1) — data already wired |
| MeatyWiki research integration | missing | only a project name in `projects.json:654`; no client/model/endpoint | **NEW** capability-gated integration (§10.2, Phase 5+) |
| ARC / agentic-research council | missing | zero implementation (data-contracts.md §5) | **NEW** capability-gated integration (§10.2, Phase 5+) |
| Project display metadata (color/group/sort) | exists | `ProjectDisplayConfig`; `resolve_display_metadata()` | Use for portfolio lanes (§2.2) |
| Worktree context per feature | exists | `planning_worktree_contexts` table; worktree DTO | Defer git probe to page-visible items (backend-api.md Fix 9) |

---

## 9. Frontend Component Skeleton Plan

> Reference: `components/Planning/CommandCenter/*` (confirmed files: `PlanningCommandCenter.tsx`,
> `MultiProjectCommandCenter.tsx`, `MultiProjectSessionBoard.tsx`, `CommandCenterListView.tsx`,
> `CommandCenterCardView.tsx`, `CommandCenterBoardView.tsx`, `CommandCenterFeatureCard.tsx`,
> `CommandCenterFeatureRow.tsx`, `MultiProjectFilterRail.tsx`, `MultiProjectDetailRail.tsx`,
> `MultiProjectWorkItemCard.tsx`, `QuickCommandBar.tsx`).

### 9.1 Reuse as-is

- `MultiProjectSessionBoard.tsx` — already TQ-backed + virtualized (`useVirtualizer`, threshold-gated)
  (planning-frontend.md §1.4). Lower threshold per §6.3.
- `CommandCenterFeatureCard.tsx` / `CommandCenterFeatureRow.tsx` — the per-item card/row renderers.
- `QuickCommandBar.tsx` — launch readiness + command bar.
- `ProjectDisplayConfig` consumers (color/group/sort) for portfolio lanes.

### 9.2 Modify

| Component | Change |
|---|---|
| `MultiProjectCommandCenter.tsx` | Drive from runtime capability flag (not build-time `MULTI_PROJECT_COMMAND_CENTER_ENABLED`, planning-frontend.md MED-03); replace hardcoded `projectListReady: true` (HIGH-04) with a real `useProjectListReady()` gate; lower virtualize threshold (§6.3); consume new portfolio rollup (§7.1) |
| `PlanningCommandCenter.tsx` (V1) | Migrate from raw `useEffect`+local state to TanStack Query (CRIT-02); add cursor pagination UI (MED-02) |
| `CommandCenterBoardView.tsx` | Add virtualization to the 5 kanban columns (MED-01) |
| `PlanningAgentSessionBoard.tsx` (V1) | Add `useVirtualizer` to `BoardColumn` (HIGH-03); stabilize highlight Sets to stop O(N) hover re-render cascade (MED-01); gate `StaleIndicator` interval on stale state (MED-05) |
| `PlanningHomePage.tsx` | Viewport-defer the session board + command center (today always-mounted, HIGH-01); route hover-prefetch through `queryClient.prefetchQuery` (HIGH-02) |
| `PlanningRouteLayout.tsx` | Exclude `/planning/feature/:id` from `useSessionsQuery`+`useFeaturesQuery` pre-queries (planning-frontend.md §2); self-host fonts (MED-04, synthesis-brief.md §6) |
| `FeatureDetailShell.tsx` | Lazy per-tab fetch (today `hidden`-attr only); add Artifacts/Research/Council/Logs/Decisions/Blockers/Next tabs (§5) |
| `PlanningTopBar.tsx` | Implement Cmd-K search (today a stub toast, planning-frontend.md §8.4) and New Spec (stub, §8.5) |

### 9.3 Build new

- `PortfolioRail` — per-project lanes with rollup badges (§2.2).
- `AttentionColumns` — the four-lens cross-project columns (§2.3), generalizing
  `PlanningSummaryPanel`'s attention derivation cross-project.
- `NextWorkColumn` — consumes `GET /api/agent/planning/next-work` (§7.2).
- `FeatureDetailRoute` — `/planning/feature/:id` page wrapper around `FeatureDetailShell`,
  registered to `planningFeatureDetailHref` (`services/planningRoutes.ts:93`).
- `useProjectListReady()` — readiness gate for multi-project queries (replaces hardcoded `true`).
- `useRuntimeCapabilities()` extension — resolve the multi-project flag at runtime (§2.4).

### 9.4 Virtualization + viewport-deferred mounting requirements

- **Viewport-deferred mounting** (IntersectionObserver or accordion) for the session board and
  command center on `/planning` — both currently always mount and fire requests on entry
  (planning-frontend.md HIGH-01, §7). Mount the query only when the section scrolls into view.
- **Virtualization mandatory** on: V1 session board columns, V1 command-center board/list, attention
  columns > ~50 rows, and the detail Tasks/Sessions/Logs tabs. MPCC's existing 250-card threshold
  drops to ~60–80 (§6.3).
- **Stable identities**: rebuild highlight Sets only when the active session changes between distinct
  ids, not on every hover (MED-01).

---

## 10. Integration Surfaces

### 10.1 SkillMeat artifact intelligence (PRESENT — surface it)

SkillMeat is **fully wired** (data-contracts.md §4.1; synthesis-brief.md §4): snapshot
(`artifact_snapshot_cache`), identity map (`artifact_identity_map`), per-artifact ranking
(`artifact_ranking` + `artifact_ranking_service.py`), recommendations
(`artifact_recommendation_service.py`), stack observations, memory drafts, effectiveness rollups,
and outbound SAM telemetry. Endpoints exist: `GET /api/agent/artifact-intelligence/rankings`,
`/api/integrations/skillmeat/snapshot`, `/api/integrations/skillmeat/workflow-effectiveness`.

**Phase 5 action is pure FE surfacing — no new backend.** The feature-detail **Artifacts tab** (§5)
renders the ranked artifacts + recommendations (with rationale codes) and effectiveness for the
feature's linked workflows. The command-center item already carries `artifacts[]`
(planning-frontend.md §6 = DONE) — extend cards with an "effectiveness" affordance pulling from the
ranking rows.

### 10.2 ARC council + MeatyWiki research (NET-NEW, capability-gated, Phase 5)

Both are **entirely missing** (data-contracts.md §5; synthesis-brief.md §4): MeatyWiki appears only
as a project name in `projects.json:654`; there is zero implementation of ARC — no `research_note`,
`council_review`, or `wiki_article` entity, client, model, schema, or endpoint.

**Phase 5 scope = scaffold behind capability flags** (synthesis-brief.md §6.7, §8 open decision —
"scaffold-now-vs-defer"):

- **Capability flags** (runtime, served via capabilities surface): `arc_council_enabled`,
  `meatywiki_research_enabled`. Default **off**. When off, the Research/Council tabs render a clean
  empty-state ("integration not configured") — a missing integration is a **contract state**, not a
  bug (resilience-by-default).
- **MeatyWiki research**: a new authenticated client + `research_note` entity + `GET
  /api/integrations/meatywiki/research?feature_id=…` (§7.7), surfaced in the **Research tab**.
- **ARC council**: a `council_review` entity (status attached to a feature/plan) +
  `GET /api/agent/features/{id}/council` (§7.7), surfaced in the **Council tab**.
- These follow the transport-neutral pattern: query service in
  `backend/application/services/agent_queries/` first, then REST/CLI/MCP (root `CLAUDE.md`).

---

## 11. Sequencing & Dependencies

Per synthesis-brief.md §7, this spec is **Phase 5**, and depends on:

- **Phase 2** (cache/query correctness) — the summary/detail split (§6.1), column-projected
  `list_summary`, parallelized bundle sub-calls, project-scoped + cached fingerprint. Without these,
  the portfolio rollup (§7.1) inherits the 10 GB-DB slowness.
- **Phase 3** (DB-backed registry + multi-project worker) — `projects` table, `_OQ_OVERLAY` → DB
  (Decisions tab, §5), precomputed planning graph via worker (§7.5). The multi-project default
  (§2.1) needs the DB-backed registry to work across replicas (synthesis-brief.md §3, §6.1).
- **Phase 4** (frontend perf finish) — TQ completion, virtualization, viewport-deferred mounting,
  font self-host. Several §9 modifications (V1 TQ migration, virtualization, prefetch fix) are
  shared with Phase 4; coordinate ownership so they are not done twice.

`tokenUsageByModel` (§7.6) is a small fix that unblocks the header KPI and the token rollups (§7.1,
§7.3) — schedule it early in Phase 5 regardless of the larger backlog/integration work.

---

## 12. Acceptance Criteria (FE-facing, resilience-included)

1. Default `/planning` renders the **multi-project portfolio** with four attention lenses and ≤ 2
   cold-load requests above the fold (rollup + capabilities); session board + command center are
   **viewport-deferred** (no request until scrolled into view).
2. The multi-project gate is **runtime-resolved**; toggling it requires no rebuild. When off, the
   single-project V1 command center renders for the active project.
3. Feature drill-down opens via **modal by default** and via **`/planning/feature/:id`** for direct
   navigation; both share the TQ-cached context payload; hover-prefetch populates the cache (no
   double-fetch on open).
4. The Sessions/Logs tabs **never** bulk-load transcripts; transcripts load per-session on click;
   lists are cursor-paginated and virtualized.
5. `tokenTelemetry.source` is `"backend"` (not `"unavailable"`) once `tokenUsageByModel` is wired;
   the header token KPI shows real data or a defined fallback if the field is absent.
6. Research/Council/Artifacts tabs render real data when their capability is enabled and a clean
   empty-state when not — a missing integration is a contract state, not an error.
7. The next-work column is backed by `GET /api/agent/planning/next-work` with ranked items derived
   from existing readiness + dependency state — no synthesized sparkline or fabricated "tokens
   saved %".

---
type: worknotes
doc_type: worknotes
prd: feature-surface-data-loading-redesign-v1
phase: 0
task: P0-003
created: 2026-04-23
---

# FeatureRollupDTO Draft

## 1. Summary

`FeatureRollupDTO` is the **card-level aggregate contract** returned by `POST /api/v1/features/rollups`. Its single job is to let the board (and the modal metric tiles) render every numeric badge, counter, progress chip, and hover-tooltip summary **without loading a single `FeatureSessionLink` object on the frontend**.

The field inventory (P0-001) identified 18 distinct metric groups that today require the full `/api/features/{id}/linked-sessions` array. Of those, **15 are reducible to bounded SQL aggregates** against `sessions` (via `feature_id`) plus the `links` table for doc/task counts; **3 are not cheaply reducible** and are moved to detail-only (modal Sessions tab / History tab loading a paged `/sessions` endpoint). See §6.

All fields are aggregates; no raw linked-session objects or session-log references appear in the DTO. The response is keyed by `featureId` and is **additive-only** over time — adding a new metric never removes one.

Total field count: **22 scalar/list fields** + 2 meta fields (`precision`, `freshness`) = **24 fields**.

- `exact`: 8
- `eventually_consistent`: 12
- `partial`: 4

## 2. Request / Response Shape

### Request: `POST /api/v1/features/rollups`

```jsonc
{
  "projectId": "skillmeat",          // required; scopes session aggregation via sessions.project_id
  "featureIds": ["FEAT-123", ...],   // required; 1..100 entries, deduped server-side
  "include": {
    "modelFamilies": true,           // default true — cheap GROUP BY
    "providers": true,               // default true
    "workflowTypes": true,           // default true
    "linkedDocCount": true,          // default true — links table
    "testCount": true                // default false — requires health join
  },
  "asOf": "2026-04-23T12:00:00Z"     // optional; default = now. Used as the `freshness.requestedAt`
}
```

Bounds and validation:

- `featureIds` max length **100**. Over-budget returns `422` with an explicit `limit_exceeded` error. Rationale: the board's default page window is 50; doubling gives headroom for virtualized prefetch without letting a client request the whole catalog in one call.
- `featureIds` is deduped; duplicates are silently collapsed.
- Unknown `include` keys are ignored (forward-compat); known keys default-true for the card-critical set.
- `projectId` is required so the backend can scope `sessions.project_id` filters and avoid cross-project fan-out.

### Response

```jsonc
{
  "rollups": {                       // map keyed by featureId (NOT an array)
    "FEAT-123": { ...FeatureRollupDTO },
    "FEAT-124": { ...FeatureRollupDTO }
  },
  "missing": ["FEAT-999"],           // featureIds requested but not found in project
  "errors": {                        // featureIds that partially failed (non-fatal)
    "FEAT-456": { "code": "session_aggregate_unavailable", "message": "..." }
  },
  "generatedAt": "2026-04-23T12:00:02Z",
  "cacheVersion": "rollup:skillmeat:v1:rev-2026-04-23T12:00:00Z"
}
```

Missing/error semantics:

- `missing[]`: feature ID does not exist in this project. FE renders an "unknown feature" pill; never blocks other cards.
- `errors{}`: feature exists but one or more underlying queries (e.g. test health) failed. The rollup for that feature is still present in `rollups{}` with `precision: "partial"` and `nulls` on the impacted fields. FE shows a warning badge on the affected card tile.
- Rationale for **map, not array**: FE keys React Query cache entries per-feature; a map lets the FE merge partial refreshes without index drift, and `missing[]` / `errors{}` give explicit non-fatal channels without polluting the main data.

## 3. Field Catalog

| Field | Type | Semantics | Source (repository query / aggregate) | Precision class | Freshness source | Notes |
|---|---|---|---|---|---|---|
| `featureId` | `string` | Echoes the request ID. | — | `exact` | request | Always present when key exists in `rollups{}`. |
| `sessionCount` | `int` | Total linked sessions (primary + subthread). | `SELECT COUNT(*) FROM sessions WHERE feature_id = ? AND project_id = ?` | `eventually_consistent` | `sync_freshness` (sync_engine last run) | Linkage is sync-driven; see `FeatureForensicsDTO.sessions_note`. |
| `primarySessionCount` | `int` | Sessions whose `parent_session_id IS NULL` AND `is_primary_link = true` (main-thread roots). | `COUNT(*) ... WHERE parent_session_id IS NULL AND is_primary_link = 1` | `eventually_consistent` | sync_freshness | Replaces `countThreadNodes(primarySessionRoots)`. |
| `subthreadCount` | `int` | Sessions with non-null `parent_session_id`. | `COUNT(*) ... WHERE parent_session_id IS NOT NULL` | `eventually_consistent` | sync_freshness | |
| `unresolvedSubthreadCount` | `int` | Subthreads whose `parent_session_id` is NOT in the feature's session set. | Self-join `sessions s1 LEFT JOIN sessions s2 ON s2.session_id = s1.parent_session_id AND s2.feature_id = s1.feature_id WHERE s1.parent_session_id IS NOT NULL AND s2.session_id IS NULL` | `partial` | sync_freshness | Semantically fuzzy; only reliable when the full feature set is sync-stable. Null when sync is mid-run. |
| `totalCost` | `float` | `SUM(total_cost)` across linked sessions (raw recorded). | `SUM(total_cost)` | `eventually_consistent` | sync_freshness | |
| `displayCost` | `float` | `SUM(COALESCE(display_cost_usd, recalculated_cost_usd, reported_cost_usd, total_cost))` — mirrors FE `resolveDisplayCost`. | Same SUM with COALESCE | `eventually_consistent` | sync_freshness | If `display_cost_usd` not materialized in SQL, compute in repository CTE. |
| `observedTokens` | `int` | `SUM(observed_tokens)` (workload tokens excluding cache). | `SUM(observed_tokens)` | `eventually_consistent` | sync_freshness | Naming mirrors `FeatureSessionLink.observedTokens`. |
| `modelIOTokens` | `int` | `SUM(input_tokens + output_tokens)`. | `SUM(input_tokens) + SUM(output_tokens)` | `eventually_consistent` | sync_freshness | |
| `cacheInputTokens` | `int` | `SUM(tool_result_cache_creation_input_tokens + tool_result_cache_read_input_tokens)`. | Same | `eventually_consistent` | sync_freshness | Card computes `cacheShare = cacheInputTokens / observedTokens` FE-side. |
| `latestSessionAt` | `ISO8601 \| null` | `MAX(started_at)` over linked sessions. | `MAX(started_at)` | `eventually_consistent` | sync_freshness | Used for the board default sort ("recent"). |
| `latestActivityAt` | `ISO8601 \| null` | `MAX` of `updated_at` across sessions AND `feature.updated_at` AND linked doc `updated_at`. | Repository-level `GREATEST` across joined tables | `eventually_consistent` | sync_freshness | Broader than `latestSessionAt`; powers "activity" heuristics. |
| `modelFamilies` | `{family: string, sessionCount: int}[]` | Distinct normalized model families used by linked sessions, with per-family count. Sorted by count desc. Capped at top 5. | `GROUP BY model_family` | `eventually_consistent` | sync_freshness | Replaces card hover-tooltip "models" chip. |
| `providers` | `{provider: string, sessionCount: int}[]` | Distinct provider labels (anthropic / openai / gemini / ...). Capped at top 5. | `GROUP BY provider` | `eventually_consistent` | sync_freshness | |
| `workflowTypes` | `{workflow: string, sessionCount: int}[]` | Distinct `workflow_type` values. Capped at top 5. Powers the card's `byType[]` breakdown. | `GROUP BY workflow_type` | `eventually_consistent` | sync_freshness | Replaces P0-001 §4 open question #3. |
| `linkedDocCount` | `int` | Count of linked documents via `links` table. | `COUNT(*) FROM links WHERE src_kind='feature' AND src_id=? AND dst_kind='document'` | `exact` | `links.updated_at` | Replaces `feature.linkedDocs.length` in the card rollup path; `linkedDocs[]` array itself stays in the **feature list row** DTO (see §5) for the hover type-breakdown badge. |
| `linkedDocCountsByType` | `{docType: string, count: int}[]` | Per-doc-type counts (prd, spec, plan, ctx, report). Top 8. | `GROUP BY documents.doc_type` | `exact` | `links.updated_at` | Replaces FE-side `buildLinkedDocTypeCounts`. |
| `linkedTaskCount` | `int` | Count of tasks referenced by any linked session's `related_tasks[]`. | `COUNT(DISTINCT task_id)` over `links` | `eventually_consistent` | sync_freshness | |
| `linkedCommitCount` | `int` | Distinct commit hashes across `commit_correlations` for this feature's sessions. | `COUNT(DISTINCT commit_hash)` via sessions→commit_correlations join | `eventually_consistent` | sync_freshness | Replaces History tab "Linked commits count" tile; detail list stays in `/activity`. |
| `linkedPrCount` | `int` | Distinct PR identifiers across sessions. | `COUNT(DISTINCT pr_id)` | `eventually_consistent` | sync_freshness | |
| `testCount` | `int \| null` | Total tests tracked for this feature. | `getFeatureHealth()` / `feature_test_health` table | `exact` | `feature_test_health.updated_at` | Null when `include.testCount=false` OR health data not yet collected. |
| `failingTestCount` | `int \| null` | Currently-failing tests. | Same source | `exact` | `feature_test_health.updated_at` | Null under same conditions as `testCount`. |
| `precision` | `"exact" \| "eventually_consistent" \| "partial"` | **Overall** precision class of this rollup (worst field wins). | Derived | meta | — | Allows the FE to show a single "staleness" indicator per card. |
| `freshness` | `{ sessionSyncAt: ISO8601 \| null, linksUpdatedAt: ISO8601 \| null, testHealthAt: ISO8601 \| null, cacheVersion: string }` | Per-source timestamps plus the global cache revision. | Derived | meta | — | FE uses this to decide whether to show a "refresh" nudge; see §4. |

**Dropped from P0-001 hotspots** (not in rollup, see §6 for rationale):

- Per-feature full session forest (`primarySessionRoots`, thread tree) — detail only
- `byType[]` as *session-by-session* grouping — replaced with `workflowTypes` counts
- `sessionHasLinkedSubthreads` cross-check — replaced with `unresolvedSubthreadCount` aggregate
- Per-commit aggregates (token in/out, fileCount, additions, deletions, costUsd) — detail only (`/activity`)
- Per-session linked-task annotations (cross-join of sessions × phase tasks) — detail only
- History event timeline (session start/end events mixed with doc timeline) — detail only

## 4. Precision and Freshness Taxonomy

### Precision classes

| Class | Definition | Example fields | FE contract |
|---|---|---|---|
| `exact` | Value is derivable from a single authoritative table at query time with no staleness beyond transactional commit. | `featureId`, `linkedDocCount`, `testCount` | Render without staleness indicator. |
| `eventually_consistent` | Value derives from data populated by the background sync engine (parsers → DB). Freshness lags filesystem state by up to `sync_freshness` seconds. | `sessionCount`, `totalCost`, `observedTokens`, `modelFamilies`, `latestSessionAt` | Render normally; show a subtle freshness dot if `sync_freshness` older than N minutes. Matches the existing `FeatureForensicsDTO.sessions_note` convention. |
| `partial` | Value depends on cross-record reconciliation that can be wrong mid-sync (e.g. subthread parent resolution when parents haven't landed yet), OR a requested source was unavailable. | `unresolvedSubthreadCount`, fields set null due to `errors{}` entries | Render with a warning badge; tooltip explains which source is partial. |

**Rule:** The top-level `precision` field takes the **worst** class across all populated fields in that rollup. This gives the card a single correctness signal without demanding the FE reason about each metric.

### Freshness semantics

Three independent freshness clocks, all surfaced in `freshness`:

1. `sessionSyncAt` — timestamp of the last completed sync engine run that touched this feature's sessions. This dominates `eventually_consistent` fields.
2. `linksUpdatedAt` — `MAX(links.updated_at)` for this feature. Governs `linkedDocCount*`, `linkedTaskCount`.
3. `testHealthAt` — `MAX(feature_test_health.updated_at)`. Governs `testCount`, `failingTestCount`.

Plus one global meta:

4. `cacheVersion` (top-level) — a monotonic token the backend rollup cache emits. Combines project-scoped sync revision and rollup cache bucket. The FE uses it as a React Query cache key component; on `cacheVersion` change, the FE invalidates affected card queries.

**Interaction with the existing backend cache** (`CCDASH_QUERY_CACHE_TTL_SECONDS`, `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS`):

- Rollup queries **opt into** the existing agent-query cache, keyed by `(projectId, sortedFeatureIds, includeFlags)`.
- Cache key includes the project's latest `sync_freshness` so a fresh sync invalidates rollups atomically — we do **not** need a separate rollup-specific invalidation channel.
- `--no-cache` (CLI) / `CCDash-Cache-Control: no-store` (HTTP) bypasses cache for parity tests.

## 5. Feature List DTO vs Rollup DTO — Separation of Concerns

The phase plan defines a parallel **Feature List DTO** (P0-001 companion, returned by `GET /api/v1/features`). The two DTOs must stay non-overlapping on the **cost-of-compute** axis:

| Dimension | Feature List DTO (`/features`) | Feature Rollup DTO (`/features/rollups`) |
|---|---|---|
| Source | `features` + `feature_phases` + `links` (no session aggregation) | `sessions` aggregation + health + links counts |
| Per-row cost | O(1) per row (pure row read + pre-materialized counts) | O(n) per feature (GROUP BY across sessions), bounded by SQL |
| Invariant | Needed for layout, filter, sort | Needed for numeric metric tiles & hover badges |
| Payload bound | Page size (default 50) | Batch size (max 100 IDs) |

**Field allocation decisions** (resolves P0-001 open questions 6 & 7):

| Metric | Belongs in | Rationale |
|---|---|---|
| `id`, `name`, `status`, `effectiveStatus`, `category`, `tags`, `priority`, `riskLevel` | List | Layout / filter / sort-critical; must be in the row. |
| `totalTasks`, `completedTasks`, `deferredTasks`, `phaseCount` | List | Already materialized on `features` table; no aggregation cost. |
| `plannedAt`, `startedAt`, `completedAt`, `updatedAt`, `dates.*` | List | Primary-date derivation needs per-row. |
| `documentCoverage` summary (`present[]`, `missing[]` *as scalars* `presentCount` / `missingCount`) | List | Keep scalar counts in list; drop the full string arrays. If FE needs the labels it can open the Docs tab. **Decision for OQ-7**: replace `documentCoverage.present[]/.missing[]` arrays with `presentCount`/`missingCount` scalars + one list of missing coverage type names (capped at 5). |
| `linkedDocs[]` (full array) | **Neither** | **Decision for OQ-6**: remove from the list DTO. Card's hover type-breakdown uses `linkedDocCountsByType` from the rollup. If the full list is needed (modal Docs tab), it loads via `GET /features/{id}` (Overview shell). |
| `linkedDocCount`, `linkedDocCountsByType` | Rollup | Cheap `links` aggregate; keeps the list row payload small. |
| `qualitySignals` (blocker count, at-risk count, test impact) | List | Pre-materialized on the feature row. |
| `familyPosition`, `relatedFeatureCount` | List | Already on the feature row. |
| `primaryDocuments` | List, **summary only** (id + title + docType) | Full docs in modal fetch. |
| Session counts, token/cost, latest activity, modelFamilies, workflowTypes, commit/PR counts | **Rollup** | Require session GROUP BY. |
| `testCount`, `failingTestCount` | **Rollup** (opt-in via `include.testCount`) | Separate data source; should not block list-row rendering. |
| `planningStatus`, `mismatchState` | List | Already on the feature row. |

**Overlap concerns:** `linkedDocCount` could live in both. Recommendation: **keep it in the Rollup only**. The list row already carries `linkedDocCountsByType` would be redundant; the list DTO gives size for layout purposes via `primaryDocuments.length`. A card that has rendered its row but not yet received its rollup can display a neutral "—" for the docs badge for ~200ms without visual regression.

## 6. Metrics Deemed Detail-Only (Not in Any List/Rollup)

These P0-001 metrics cannot be reasonably aggregated in bounded SQL per-card and are explicitly **not** in `FeatureRollupDTO`. They remain available through detail-only endpoints (`/features/{id}/sessions`, `/features/{id}/activity`) loaded on modal tab open.

| Metric | Reason it's detail-only | Target endpoint |
|---|---|---|
| Session forest / thread tree (`primarySessionRoots`, `countThreadNodes`) | Graph structure requires per-session joins; cannot be collapsed to scalars without losing fidelity. | `GET /features/{id}/sessions` |
| Per-session `linked tasks` annotation (cross-join sessions × phase tasks by `task.sessionId`) | N×M relationship; materializing per-rollup is O(phases × sessions). | `GET /features/{id}/sessions?include=tasks` |
| Per-commit aggregates (tokenInput, tokenOutput, fileCount, additions, deletions, costUsd, eventCount, toolCallCount, commandCount, artifactCount) | Pivot over `commit_correlations`; card only needs the count. | `GET /features/{id}/activity?group=commits` |
| Per-PR aggregates | Same as above for PR grouping. | `GET /features/{id}/activity?group=prs` |
| History timeline events (feature + doc timeline + session start/end events merged) | Ordering + merging of heterogeneous event sources; not a scalar. | `GET /features/{id}/activity` |
| Session card-level fields (model, duration, confidence, agentsUsed, skillsUsed, commands, toolSummary, linkStrategy, reasons) | Per-session detail; belongs on session card render path. | `GET /features/{id}/sessions` |
| Core session groups (plan/execution/other classification per session) | Classification heuristic per-session; expose as a `group` filter on the paged sessions endpoint. | `GET /features/{id}/sessions?group=plan` |
| Phase-linked session/commit id lists (Modal Phases tab) | Inverse index (phase → session_ids); requires a specific shape for the Phases tab. | Load from `GET /features/{id}/sessions` + compute in Phases tab component, OR add a tiny `GET /features/{id}/phase-session-index` in P0-004 (modal section contracts). |
| Test status tab data (`FeatureTestHealth`) | Already a separate endpoint; unchanged. | `getFeatureHealth(projectId, {featureId})` |

## 7. Open Questions / Decisions Needed

1. **`unresolvedSubthreadCount` necessity.** This field is `partial` by construction and is the only metric that currently requires cross-row reconciliation at aggregate time. Proposal: include it gated by `include.subthreadResolution` (default false), and drop the card badge that relies on it — it was a debug affordance, not a product metric. Needs sign-off from whoever owns the session indicator UX (P0-001 OQ-2).

2. **`displayCost` computation location.** Today's FE helper `resolveDisplayCost` falls back through four fields (`displayCostUsd` → `recalculatedCostUsd` → `reportedCostUsd` → `totalCost`). We can either: (a) precompute `display_cost_usd` during sync so the aggregate is a plain `SUM`; or (b) compute `SUM(COALESCE(...))` in the rollup query at read time. Option (a) is cheaper per-read but adds a sync-engine obligation. **Recommend (a)** — sync already recomputes cost fields — but surface the decision to backend-architect before Phase 1.

3. **Request size bound (100) and batch ergonomics.** The default board page is 50 cards. A bound of 100 gives headroom but constrains any future "load all 500 features" product request. Alternatives: (a) keep 100 and require the FE to page rollups alongside list paging; (b) raise to 250 and accept a larger worst-case GROUP BY. **Recommend (a)** and lock 100 as a hard invariant so repository index planning in Phase 1 is bounded.

## Cross-References

- P0-001 field inventory: `.claude/worknotes/feature-surface-data-loading-redesign-v1/phase-0/field-inventory.md`
- Phase plan: `docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1/phase-0-inventory-contracts.md` (§ Feature Rollup DTO, § Feature List DTO)
- Parent implementation plan: `docs/project_plans/implementation_plans/refactors/feature-surface-data-loading-redesign-v1.md` (§ Target Data Contracts)
- Existing forensics DTO (reference for envelope semantics): `backend/application/services/agent_queries/models.py` (`FeatureForensicsDTO`, `AgentQueryEnvelope`)
- Session aggregation source columns: `backend/db/repositories/sessions.py` (total_cost, observed_tokens, input_tokens, output_tokens, cache_*_input_tokens, started_at, ended_at, model_family, workflow_type, parent_session_id, is_primary_link, feature_id)

# P3 Seam Contract Mapping (T3-000)

**Purpose**: Per Plan Generator Rule R-P3, verify the `GET /api/agent/research-runs` (+
`/{run_id}` detail) response DTO — Phase 2 T2-003 (`run_intelligence.py`) / T2-004
(`backend/routers/agent.py:1241-1327`) — before any Phase 3 panel work begins (T3-002+).

**Result: no `types.ts` `ResearchRun`/`ResearchRunMetrics` interfaces exist yet.** T3-001 (which
authors them) is downstream of this task and has not run. There is therefore nothing to *diff*
against today — the actual seam risk this task closes is **drift-by-guessing**: T3-001 must not
invent field names/shapes independently of the backend DTO. This note is the locked source-of-truth
field list T3-001 must adopt verbatim (plus the one structural delta called out below). T3-002
should treat this file, not the phase-3 plan prose, as the authoritative contract.

## 1. Wire-format finding (blocking for T3-001's design)

`ResearchRunSummaryDTO`, `ResearchRunDetailDTO`, `ResearchRunListResponseDTO`, and
`ResearchRunDetailResponseDTO` (`backend/application/services/agent_queries/run_intelligence.py`)
declare **no** `model_config` / `alias_generator`. Contrast with `AnalyticsKPIsDTO`
(`backend/application/services/agent_queries/models.py:1024-1038`), which explicitly opts into
`alias_generator=to_camel`. Absent that, FastAPI serializes Pydantic v2 models by field name — so
the `/api/agent/research-runs` wire payload is **pure snake_case**, byte-identical to the Python
attribute names below. Verified by reading the DTO source directly (no camelCase alias anywhere in
`run_intelligence.py`); not re-verified via a live HTTP call in this pass (no seeded RF data on this
worktree) — the Pydantic-model-config method is authoritative and requires no seeded data.

This matches the codebase's existing established pattern for exactly this situation: see
`services/queries/planning.ts:253-274` (`WirePlanningViewBundle` snake_case → `PlanningViewBundleDTO`
camelCase, adapted client-side, backend never pre-adapts) and the `sessionId`/`projectId` camelCase
convention throughout `types.ts`. **T3-001 should follow the identical pattern**: an internal
`WireResearchRun`/`WireResearchRunDetail` interface (snake_case, 1:1 with the DTOs below) consumed
only inside the query-hook module, adapted to camelCase `ResearchRun`/`ResearchRunDetail` before
those types leave `services/queries/` — do not export raw snake_case shapes as the public
`types.ts` contract.

## 2. Structural delta the FE must adopt: no `ResearchRunMetrics` DTO exists

The phase-3 plan names two FE interfaces, `ResearchRun` and `ResearchRunMetrics`, implying a
nested metrics sub-object. **The backend has no such split.** All metric fields (`event_count`
through `drift_score`, plus governance/reuse flags) are flat, top-level fields on
`ResearchRunSummaryDTO` — there is exactly one DTO shape per grain (summary vs. detail), not a
run/metrics pair.

**Delta**: T3-001 has two compliant options — (a) drop the `ResearchRunMetrics` split and make
`ResearchRun` a single flat interface mirroring the DTO ("metrics" are just fields on the run), or
(b) keep `ResearchRunMetrics` as a **client-side derived/grouped view** (a subset-of-fields type
used for panel props) rather than a distinct wire shape — never expect the backend to send a nested
`metrics: {...}` object. Recommend (a) for T3-001 (simplest, zero adapter risk) with `ResearchRunMetrics`
reserved as an optional narrower type alias if a panel wants a metrics-only prop shape.

## 3. Field-by-field mapping — `ResearchRunSummaryDTO` (list item, `items[]`)

Source: `run_intelligence.py:194-264`. All `Optional`/nullable fields serialize as JSON `null`
(never a fabricated `0`/`""`/`[]`) per AC-2-Field — confirmed via `_safe_*_or_none` helpers
(`run_intelligence.py:130-189`) and the `_run_row_to_summary` mapper (`run_intelligence.py:305-354`).

| Wire field (snake_case) | Python type | Nullable | TS type FE must use (camelCase) |
|---|---|---|---|
| `run_id` | `str` | no | `runId: string` |
| `rf_run_id` | `str \| None` | yes | `rfRunId: string \| null` |
| `project_id` | `str` | no | `projectId: string` |
| `workspace_id` | `str` (default `"default-local"`) | no | `workspaceId: string` |
| `intent_id` | `str \| None` | yes | `intentId: string \| null` |
| `task_node_id` | `str \| None` | yes | `taskNodeId: string \| null` |
| `rf_project` | `str \| None` | yes | `rfProject: string \| null` |
| `event_count` | `int` (default `0`) | no | `eventCount: number` |
| `first_event_at` | `str \| None` (ISO) | yes | `firstEventAt: string \| null` |
| `last_event_at` | `str \| None` (ISO) | yes | `lastEventAt: string \| null` |
| `queries_executed` | `int \| None` | yes | `queriesExecuted: number \| null` |
| `urls_extracted` | `int \| None` | yes | `urlsExtracted: number \| null` |
| `useful_source_count` | `int \| None` | yes | `usefulSourceCount: number \| null` |
| `tokens_estimated` | `int \| None` | yes | `tokensEstimated: number \| null` |
| `claims_total` | `int \| None` | yes | `claimsTotal: number \| null` |
| `claims_supported` | `int \| None` | yes | `claimsSupported: number \| null` |
| `claims_mixed` | `int \| None` | yes | `claimsMixed: number \| null` |
| `claims_contradicted` | `int \| None` | yes | `claimsContradicted: number \| null` |
| `unsupported_claims` | `int \| None` | yes | `unsupportedClaims: number \| null` |
| `estimated_cost_usd` | `float \| None` | yes | `estimatedCostUsd: number \| null` |
| `latency_ms` | `float \| None` | yes | `latencyMs: number \| null` |
| `citation_coverage` | `float \| None` | yes | `citationCoverage: number \| null` |
| `duplicate_rate` | `float \| None` | yes | `duplicateRate: number \| null` |
| `extraction_failure_rate` | `float \| None` | yes | `extractionFailureRate: number \| null` |
| `quality_score` | `str \| None` | yes | `qualityScore: string \| null` |
| `drift_score` | `float \| None` | yes | `driftScore: number \| null` |
| `mode` | `str \| None` (always `None` today — no rollup column yet, see module docstring) | yes | `mode: string \| null` |
| `selected_providers` | `list[str] \| None` (always `None` today, same gap) | yes | `selectedProviders: string[] \| null` |
| `governance_sensitivity` | `str \| None` | yes | `governanceSensitivity: string \| null` |
| `governance_policy_passed` | `bool \| None` | yes | `governancePolicyPassed: boolean \| null` |
| `human_review_required` | `bool \| None` | yes | `humanReviewRequired: boolean \| null` |
| `human_review_status` | `str \| None` | yes | `humanReviewStatus: string \| null` |
| `human_review_reviewer` | `str \| None` | yes | `humanReviewReviewer: string \| null` |
| `reuse_meatywiki_writeback_candidate` | `bool \| None` | yes | `reuseMeatywikiWritebackCandidate: boolean \| null` |
| `reuse_skillbom_candidate` | `bool \| None` | yes | `reuseSkillbomCandidate: boolean \| null` |
| `reuse_reusable_source_pack_candidate` | `bool \| None` | yes | `reuseReusableSourcePackCandidate: boolean \| null` |
| `linked_session_id` | `str \| None` (first of `linked_session_ids`, `None` if empty) | yes | `linkedSessionId: string \| null` |
| `linked_session_ids` | `list[str]` (default `[]`, never `null`) | no (empty array is the resilience state) | `linkedSessionIds: string[]` |
| `created_at` | `str \| None` (ISO) | yes | `createdAt: string \| null` |
| `updated_at` | `str \| None` (ISO) | yes | `updatedAt: string \| null` |

**AC-4-Fields cross-check** (phase-3 plan line 116 enumerates 9 fields as the FE's minimum
resilience coverage): `estimated_cost_usd`, `citation_coverage`, `latency_ms`, `mode`,
`selected_providers`, `linked_session_id`, `rf_run_id`, `intent_id`, `task_node_id` — **all 9 are
present verbatim in the table above with matching optionality**. Zero mismatch between the AC
prose and the actual DTO for this specific enumerated set.

## 4. `ResearchRunDetailDTO` — additive fields only (superset of summary)

Source: `run_intelligence.py:266-277`. Inherits every field above unchanged, plus:

| Wire field (snake_case) | Python type | Nullable | TS type FE must use (camelCase) |
|---|---|---|---|
| `agent_postures` | `list[str] \| None` | yes | `agentPostures: string[] \| null` |
| `skillbom_ids` | `list[str] \| None` | yes | `skillbomIds: string[] \| null` |
| `tools` | `list[str] \| None` | yes | `tools: string[] \| null` |
| `input_artifacts` | `list[str] \| None` | yes | `inputArtifacts: string[] \| null` |
| `output_artifacts` | `list[str] \| None` | yes | `outputArtifacts: string[] \| null` |

These 5 fields are list-only (omitted from `ResearchRunSummaryDTO` to keep pages lightweight, per
the DTO docstring) — FE must not expect them on `items[]` rows in the list response; they only
appear on `GET /api/agent/research-runs/{run_id}`'s `run` object.

## 5. Response envelopes

### `ResearchRunListResponseDTO` (`GET /api/agent/research-runs`) — extends `AgentQueryEnvelope`

`AgentQueryEnvelope` (`models.py:29-41`) also has **no** `alias_generator` — envelope fields are
snake_case on the wire too.

| Wire field | Python type | TS type |
|---|---|---|
| `status` | `"ok" \| "partial" \| "error"` | `status: 'ok' \| 'partial' \| 'error'` |
| `data_freshness` | `datetime` (ISO string on wire) | `dataFreshness: string` |
| `generated_at` | `datetime` (ISO string on wire) | `generatedAt: string` |
| `source_refs` | `list[str]` (default `[]`) | `sourceRefs: string[]` |
| `project_id` | `str` | `projectId: string` |
| `items` | `list[ResearchRunSummaryDTO]` (default `[]`) | `items: ResearchRun[]` |
| `cursor` | `str` (default `""`) | `cursor: string` |
| `limit` | `int` (default `50`) | `limit: number` |
| `next_cursor` | `str \| None` | `nextCursor: string \| null` |

### `ResearchRunDetailResponseDTO` (`GET /api/agent/research-runs/{run_id}`) — extends `AgentQueryEnvelope`

| Wire field | Python type | TS type |
|---|---|---|
| `status` / `data_freshness` / `generated_at` / `source_refs` | (same as above) | (same as above) |
| `project_id` | `str` | `projectId: string` |
| `run_id` | `str` | `runId: string` |
| `found` | `bool` (default `false`) | `found: boolean` |
| `run` | `ResearchRunDetailDTO \| None` | `run: ResearchRunDetail \| null` |

`found: false, run: null` is the documented normal "no such run" shape (never a 404/exception from
this DTO's perspective — the router does raise 404 only when `status === "error"`, i.e. project
scope unresolved; a genuinely-missing `run_id` is `status: "ok"`, `found: false`). FE resilience
logic must branch on `found`, not on HTTP status, for the "run not found" empty state.

## 6. Query params / pagination (for T3-002's hook signature)

`GET /api/agent/research-runs` accepts `project_id` (optional override), `cursor` (opaque
base64 string, omit for page 1), `limit` (1–200, default 50), `bypass_cache` (bool). `next_cursor`
is `null` on the last page — standard "fetch until null" pagination, same shape as
`session_detail.py`'s transcript cursor.

## 7. Net verdict

- **No mismatch found** between the backend DTO and any FE type, because no FE type exists yet
  (T3-001 not started) — this task closes the *drift-prevention* half of R-P3, not a *fix-a-bug*
  half.
- **One structural delta T3-001 must adopt**: build `ResearchRun` as a single flat interface (no
  nested `metrics` object matches the wire shape); treat `ResearchRunMetrics` as an optional
  client-side derived/subset type only, per §2.
- **One convention T3-001 must follow**: snake_case wire → camelCase public type, adapted in the
  query-hook module, per the `WirePlanningViewBundle` precedent in `services/queries/planning.ts`
  — do not export the raw DTO shape as `types.ts`'s `ResearchRun`.
- T3-002 (query hooks) may proceed using §3–§6 above as the locked contract.

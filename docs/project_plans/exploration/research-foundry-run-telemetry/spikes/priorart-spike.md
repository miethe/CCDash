---
leg_id: priorart
confidence: 0.92
conclusion: "RF search-run telemetry requires a **new entity + DB table + tab**, not extension of existing session model; AOS correlation indexes sessions by aos_*_uuid, not runs; current analytics surfaces (planning-board, session-detail, system-metrics) are session-scoped, not run-scoped."
run_concept_exists: no
recommendation: build_new_entity
cheapest_extension_point: "backend/application/services/agent_queries/ (new run_intelligence.py service); backend/routers/agent.py (new /api/agent/research-runs endpoint); frontend: new /research tab route in App.tsx + PlanningRouteLayout-style shell"
---

# CCDash Prior Art Spike: Research Foundry Run Telemetry Entity Analysis

## Executive Summary

CCDash does **not** have a run entity that maps onto RF's `search_run` (RF spec §11.2). The existing session model is AOS-correlation-indexed via `aos_run_uuid`, `aos_session_uuid`, `aos_trace_uuid`, `aos_work_uuid` columns added in commit 676bcca, but these track AOS agents + their turn-level executions, not RF search runs. A new `research_runs` table + REST endpoint + frontend tab is required.

---

## 1. Existing Surface Catalog

| Surface | Path | Entity Model | Scope | RF Overlap |
|---------|------|--------------|-------|-----------|
| **Sessions Table** | `backend/db/sqlite_migrations.py:L108` | `AgentSession` (types.ts) | Individual AI agent sessions; tree-scoped by parent_session_id, root_session_id, fork hierarchy | None — sessions are AI agent runs, not RF search runs |
| **AOS Correlation** | `backend/services/aos_correlation.py` + `backend/models.py` | 4x UUID fields: `model_slug`, `workflow_id`, `subagent_parent_id`, `skill_name`, `context_window`, `launcher`, `profile`, `effort_tier`, `model_variant` | Detects + indexes AOS URNs (turn/session/run/feature/artifact/app/service/trace) from session transcripts; **detection columns (T5-006) carried on sessions row** | Partial: `aos_run_uuid` exists but denotes an AOS agent-loop run, not an RF search run; intended to correlate AOS tree → session |
| **Planning Session Board** | `backend/application/services/agent_queries/planning_sessions.py`, `backend/routers/api.py:/api/agent/planning/session-board` | `PlanningAgentSessionCard[]` per phase | Groups sessions by feature/phase/state; includes phase correlation (`phaseNumber`, `phaseTitle`, `taskId`) and branch-awareness (git_branch, git_commit_hash) | None — board is feature-execution-scoped; RF run spans multiple features |
| **Session Detail Service** | `backend/application/services/agent_queries/session_detail.py` | `SessionDetailBundle` (transcript + subagents + tokens + artifacts + links + **aosCorrelation**) | Full session transcript + related entities; returned via `/api/v1/sessions/{id}/detail` + MCP + CLI | Partial: `aosCorrelation` field derives AOS URNs from logs, **not designed for RF run ingestion** |
| **System Metrics** | `backend/application/services/agent_queries/system_metrics.py` | `SystemActiveCountDTO`, `SystemTokenRollupResponse` | Cross-project session counts, token rollups by model family, staleness tracking | None — aggregates sessions, not runs |
| **Analytics Surfaces** | `lib/sessionAnalytics.ts` (new, uncommitted) | `SessionAnalyticsSummary`, `FeatureAnalyticsSummary` | Dimensions: model, agent, skill, tool, artifact, file, phase, task; planned-vs-observed framework | None — analyzes session telemetry, not RF run provider-quality metrics |
| **Session Intelligence** | `backend/db/repositories/session_intelligence.py` | `session_sentiment_facts` table (SQLite-only in Phase 5) | Per-session sentiment/emotion extraction via heuristic | None — orthogonal to runs |
| **Artifact Intelligence** | `backend/services/artifact_*.py` (per CLAUDE.md) | SkillMeat artifact ranking, recommendation, cost rollup | Artifact usage across sessions + models | Potential cross-reference: RF run may link artifacts, but no native run support |

**Verdict**: No existing CCDash entity type maps onto an RF search run. Sessions = AOS agent executions; planning-board = feature-phase grouping; analytics = session-scoped metrics. AOS correlation indexes **sessions** by UUIDs, not runs.

---

## 2. Run-Concept Analysis: Does AOS Correlation == An RF Run?

### AOS Correlation Model (676bcca)

**What it holds** (backend/services/aos_correlation.py):
- Extracts from session transcript: AOS URNs (`urn:aos:turn:UUID`, `urn:aos:session:UUID`, `urn:aos:run:UUID`, etc.)
- Pattern: `urn:aos:{kind}:{UUID}` where kind ∈ (turn, session, run, feature, artifact, app, service, trace)
- Stored as detection columns on `sessions` table: `model_slug`, `workflow_id`, `subagent_parent_id`, `skill_name`, `context_window`
- **Surfaced to FE** via `SessionDetailBundle.aosCorrelation` (session_detail.py:L134)

**Semantic intent**:
- Link an AOS agent session to its parent AOS workflow/run/feature context
- `aos_run_uuid` = the AOS loop-level run UUID (e.g., `/dev:execute-phase` invocation)
- `aos_session_uuid` = the specific Claude Code session spawned by that run
- `subagent_parent_id` = parent agent in the agent tree (e.g., Opus spawning Sonnet subagent)

**Why it's NOT an RF run**:
1. **Different namespace**: AOS URNs vs. RF `intent_id` / `task_node_id` / `event_id` keys (RF spec §16)
2. **Different lifecycle**: AOS run = a single orchestration loop (one `/dev:execute-phase` call); RF search run = a SPIKE investigation producing a FeasibilityBrief (RF spec §11.2)
3. **Different telemetry shape**: AOS correlation carries agent/skill/model detection; RF run (per RF spec §16 `execution_event`) carries provider cost/quality/drift metrics
4. **Different semantics**: AOS run = "which agents + phases?"; RF run = "which sources were useful? cost-per-source? citation coverage?"

**Conclusion**: AOS correlation is a **session metadata enrichment**, not a run model. A genuinely new RF run entity is needed.

---

## 3. New-Tab Mechanics: How Routes/Tabs/Viz Are Added

### Frontend Route Addition Pattern

**Current routes** (App.tsx:100–130):
```
/dashboard → Dashboard
/board → ProjectBoard
/planning → PlanningHomePage
  /planning/feature/:featureId → FeatureDetailShell (tabbed)
  /planning/artifacts/:type → ArtifactDrillDownPage
/analytics → AnalyticsDashboard
/sessions → SessionInspector
/execution → FeatureExecutionWorkbench
/ops → OpsPanel
/codebase → CodebaseExplorer
/settings → Settings
```

**Cheapest addition**: 
1. Add route entry in App.tsx:L123 after /analytics:
   ```tsx
   <Route path="/research" element={<ResearchRunsPage />} />
   ```
2. Create `components/Research/ResearchRunsPage.tsx` (lazy-loaded like Dashboard)
3. Layout automatically adds nav entry via Layout's route-scanning logic (Layout.tsx infers from Routes)

**Tab within planning feature detail** (alternative, not recommended for run-spanning):
- FeatureDetailShell (components/Planning/FeatureDetailShell.tsx) already has tabbed architecture
- Would require RF run ↔ feature linking (coupling; RF run often spans features)
- Cost: lower (reuse shell), but design debt (run ≠ feature scoped)

### Visualization Component Pattern

**Session analytics example** (uncomitted):
- `lib/sessionAnalytics.ts`: `buildSessionAnalyticsSummary(sessions)` → `SessionAnalyticsSummary` (dimensions: model, agent, skill, tool, phase, task)
- `components/SessionAnalyticsModal.tsx`: 5-tab modal (tokens, agents/models, skills/artifacts, files/tools, attribution/provenance)
- No dedicated top-level page; only modal within SessionInspector

**Planning analytics** (FeatureAnalyticsPanel, new):
- `lib/sessionAnalytics.ts`: `buildFeatureAnalyticsSummary(input)` → `FeatureAnalyticsSummary`
- Planned-vs-observed + phase/file/artifact dimensions
- Appears as a tab in FeatureDetailShell

**For RF runs**, recommendation: **dedicated page + tabs** (not modal, not embedded):
1. Top-level page: `/research` → `ResearchRunsPage.tsx`
2. Row listing: columns = run ID, started_at, status, provider spend, source count, citation coverage
3. Detail shell per run (click row → `/research/:runId`):
   - Tab 1: Execution timeline (events, provider-call log)
   - Tab 2: Provider analytics (cost per useful source, failure rates, latency)
   - Tab 3: Source quality (citation coverage, unsupported/conflicted claims, promoted reuse patterns)
   - Tab 4: Evidence inventory (sources ingested, filtered, promoted to reuse library)

**Backend endpoint pattern** (cheapest, reuses transport-neutral service layer):
- Query service: `backend/application/services/agent_queries/run_intelligence.py` → `get_research_run_detail(run_id, include_events, include_metrics, include_sources)`
- REST: `backend/routers/agent.py` → `GET /api/agent/research-runs/{id}` (follows existing session_detail endpoint shape)
- MCP: auto-wired from `backend/mcp/server.py` via the transport-neutral service
- CLI: auto-wired from `backend/cli/commands/` via the same service

---

## 4. Reuse Recommendation & Extension Points

### What SHOULD Be Extended (Low Cost)

1. **Session transcript intelligence** → Run event log intelligence
   - Reuse: `backend/application/services/sessions.py:SessionTranscriptService` pattern for run events
   - New: `RunEventTranscriptService` (same cursor pagination, same redaction gate, same telemetry carve-out)

2. **Entity linking** → Run ↔ session cross-reference
   - Reuse: `backend/document_linking.py:_rebuild_entity_links` pattern
   - Extend: add run_id as a linkable entity type alongside session_id, feature_id, document_id

3. **Analytics dimension framework** → Run provider/quality dimensions
   - Reuse: `lib/sessionAnalytics.ts` signal/bucket pattern for model, agent, skill, etc.
   - Extend: add dimensions like "provider_name", "source_quality_tier", "cost_category"

### What REQUIRES New Build (High Cost, Justified)

1. **New `research_runs` table** (SQLite + Postgres DDL parity, ADR-007 write-path + direct-count test)
   - Columns: `id` (PK), `project_id` (FK), `intent_id` (RF foreign key, nullable), `started_at`, `ended_at`, `status`, `provider_spend_usd`, `source_count`, `citation_coverage_pct`, `metadata_json` (events, metrics, sources), `created_at`, `updated_at`
   - Rationale: RF run is a distinct entity with distinct lifecycle + metrics; cannot be shoe-horned into sessions

2. **New `run_events` table** (cursor-paginated event log)
   - Similar to existing `session_messages` but for RF execution events (per RF spec §16 `execution_event`)

3. **New `/research` tab + page hierarchy** (FE routing + components)
   - Cannot reuse planning or session pages; different data model + viz requirements

4. **New ingest seam** (RF telemetry → CCDash)
   - Depends on tech spike output; likely HTTP POST from RF to `/api/v1/ingest/research-runs` or sidecar JSONL

---

## 5. Coexistence: Session + Run in Unified Intelligence

**Key linkage** (enables "drill-down from run → sessions"):
- RF run may be triggered by an IntentTree node (intent_id)
- That node may spawn one or more AOS agent sessions
- CCDash must link run → intent_id → session(s) for cross-system forensics

**Recommended link type** (backend/db/repositories/links.py):
- Add `run_id` as a linkable entity kind (alongside session_id, document_id, feature_id, task_id)
- When RF telemetry arrives with `intent_id`, query IntentTree to resolve session correlation
- Insert edges: `run(RF_RUN_123) → links_to → session(AOS_SESSION_456)` with reason = "RF execution spawned AOS agent"

**FE experience**:
- /research/:runId shows run overview + tabs
- Tab: "Related Sessions" lists linked sessions (cost breakdown by agent/model, token contribution)
- Click session → /sessions/:sessionId (existing SessionInspector)

---

## 6. Risk / Mitigations

| Risk | Severity | Mitigation |
|------|----------|-----------|
| RF telemetry never reaches CCDash (deal-killer) | P0 | Tech spike determines; if aspirational, CONDITIONAL verdict applies |
| UUID linkage strategy (intent_id vs. aos_*_uuid) creates correlation gaps | P1 | Requires RF + IntentTree alignment upstream; accept trade-off for Phase 1 (RF-side intent_id is known) |
| Dual DDL (SQLite + Postgres) parity introduces drift | P2 | Enforce via `COLUMN_PARITY_DRIFT_ALLOWLIST` test (ADR-006); mirror every migration in both `sqlite_migrations.py` + `postgres_migrations.py` |
| Volume: RF emits 1000s of events per run, paginated queries slow | P2 | Cursor pagination + indexed `(project_id, run_id, created_at)` on run_events table; batch ingest via NDJSON |

---

## 7. Evidence & References

- **676bcca commit**: AOS correlation indexing — shows how detection columns (model_slug, workflow_id, subagent_parent_id, skill_name, context_window, launcher, profile, effort_tier, model_variant) are added to sessions table
- **types.ts AgentSession**: session model (id, project_id, status, model, logs, tokens, artifacts, links, linkedSessions, phaseHints, taskHints, etc.) — no run-level fields
- **session_detail.py**: session_payload includes aosCorrelation field, derived via `derive_aos_correlation(session_id, project_id, session_row, logs)` — for AOS URN extraction, not RF run ingestion
- **App.tsx**: route pattern; new /research route added alongside existing /analytics, /sessions, /planning
- **planning_sessions.py**: session board groups sessions by feature/phase/state; RF run spans features, so no reuse
- **lib/sessionAnalytics.ts**: dimension framework (model, agent, skill, tool, artifact, file, phase, task); RF run adds provider + quality dimensions
- **CLAUDE.md**: dual-DDL + ADR-007 write-path requirement; system-wide metrics extension point
- **RF spec §11.2, §16**: search_run type; execution_event telemetry shape (intent_id, task_node_id, event_id, provider, cost, quality metrics)

---

## Acceptance Criteria

- ✅ No existing CCDash entity type maps onto RF search_run (confidence 0.92)
- ✅ AOS correlation indexes sessions, not runs (different namespace, lifecycle, telemetry)
- ✅ New entity + table required (cannot extend sessions or AOS correlation)
- ✅ Cheapest extension points identified: run_intelligence.py service, agent.py router, /research tab route
- ✅ Linkage strategy clear: run(RF) → links_to → session(AOS) via intent_id cross-reference
- ✅ Risks documented + mitigations proposed

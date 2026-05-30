# CCDash Data Contracts Investigation
## Enterprise Edition v1 — Data Availability Matrix & Entity Model

**Investigator**: Claude Sonnet 4.6 (senior architect subagent)
**Date**: 2026-05-30
**Scope**: Full entity model inventory, command-center data needs, integration surface audit

---

## 1. Core Entity Model

### 1.1 Project (`backend/models.py:1679`)

```
Project
  id: str                      # slug, e.g. "skillmeat"
  name: str
  path: str                    # filesystem root
  description: str
  repoUrl: str
  agentPlatforms: list[str]    # ["Claude Code"]
  planDocsPath: str            # relative docs path
  sessionsPath: str            # abs path to JSONL files
  progressPath: str            # relative progress path
  pathConfig: ProjectPathConfig  # structured multi-source path refs (filesystem | project_root | github_repo)
  testConfig: ProjectTestConfig  # test platform config (pytest, jest, playwright, etc.)
  skillMeat: SkillMeatProjectConfig  # integration config
  display: Optional[ProjectDisplayConfig]  # color, group, sortOrder, labelOverride
```

Projects registered in `projects.json` (814 lines, ~20 projects). No DB table — **projects live entirely in a JSON file**, never synced to DB. This is a critical gap for enterprise/container mode where the filesystem may not be writable.

### 1.2 Feature (`backend/models.py:2052`)

```
Feature
  id: str                      # slug e.g. "ccdash-planning-reskin-v2"
  name: str
  status: str                  # backlog | in-progress | review | done | deferred
  totalTasks / completedTasks / deferredTasks: int
  category / tags / description / summary / priority / riskLevel / complexity
  track / timelineEstimate / targetRelease / milestone
  owners / contributors / requestLogIds / commitRefs / prRefs
  executionReadiness / testImpact / featureFamily
  updatedAt / plannedAt / startedAt / completedAt
  linkedDocs: list[LinkedDocument]
  linkedFeatures: list[LinkedFeatureRef]
  primaryDocuments: FeaturePrimaryDocuments  # prd | implementationPlan | phasePlans | progressDocs | supportingDocs
  documentCoverage: FeatureDocumentCoverage
  qualitySignals: FeatureQualitySignals      # blockerCount, atRiskTaskCount, integritySignalRefs
  dependencyState: Optional[FeatureDependencyState]  # unblocked | blocked | blocked_unknown
  familySummary / familyPosition / executionGate / nextRecommendedFamilyItem
  phases: list[FeaturePhase]
  relatedFeatures: list[str]
  planningStatus: Optional[PlanningEffectiveStatus]  # rawStatus + effectiveStatus + mismatchState
  dates: EntityDates
  timeline: list[TimelineEvent]
```

DB table `features` (`sqlite_migrations.py:431`): `id, project_id, title, status, category, priority, data_json, created_at, updated_at, completed_at, started_at, planned_at`. The full Feature payload is serialized into `data_json` BLOB — **no columnar denormalization for tags, owners, prRefs, phases, etc.**

**CRITICAL**: `tokenUsageByModel` is NOT a field on the `Feature` model (models.py has no such field). It is accessed defensively via `getattr(feature, "tokenUsageByModel", None)` in `planning.py:833` — this **always returns None** unless dynamically patched. The `PlanningTokenTelemetry` payload will therefore always have `source="unavailable"` at the planning summary level unless token telemetry is injected differently.

### 1.3 FeaturePhase (`backend/models.py:1918`)

```
FeaturePhase
  id: Optional[str]
  phase: str                    # "1", "2", "all"
  title: str
  status: str                   # backlog | in-progress | review | done | deferred
  progress: int                 # 0-100
  totalTasks / completedTasks / deferredTasks: int
  tasks: list[ProjectTask]
  planningStatus: Optional[PlanningEffectiveStatus]
  phaseBatches: list[PlanningPhaseBatch]
```

DB table `feature_phases` (`sqlite_migrations.py:452`): `id, feature_id, phase_number, title, status, progress, data_json, created_at, updated_at`. Same BLOB-first pattern. Indexed by `feature_id` only (`idx_phases_feature`).

### 1.4 ProjectTask (`backend/models.py:1254`)

```
ProjectTask
  id / title / description
  status: str                   # backlog | in-progress | review | done | deferred
  owner / lastAgent / cost / priority
  projectType / projectLevel
  tags / updatedAt / relatedFiles / sourceFile / sessionId / commitHash
  featureId: Optional[str]
  phaseId: Optional[str]
```

DB table `tasks` (`sqlite_migrations.py:402`): `id, project_id, feature_id, phase_id, title, description, status, owner, priority, tags_json, data_json, source_file, created_at, updated_at`. Indexed by `(feature_id, phase_id)` and `(project_id, status)`.

### 1.5 AgentSession (`backend/models.py:154`, `types.ts:393`)

The richest entity. Key fields for command center:

```
AgentSession
  id / title / taskId / status ("active" | "completed")
  model / modelDisplayName / modelProvider / modelFamily / modelVersion
  modelsUsed / platformType / platformVersion / platformVersions
  agentsUsed / skillsUsed / toolSummary
  sessionType / parentSessionId / rootSessionId / agentId
  threadKind / conversationFamilyId / contextInheritance
  forkParentSessionId / forkDepth / forkCount
  durationSeconds / tokensIn / tokensOut / totalCost
  cacheCreationInputTokens / cacheReadInputTokens / cacheShare / outputShare
  currentContextTokens / contextWindowSize / contextUtilizationPct
  reportedCostUsd / recalculatedCostUsd / displayCostUsd / costProvenance
  startedAt / endedAt / createdAt / updatedAt
  qualityRating / frictionRating
  gitCommitHash / gitCommitHashes / gitAuthor / gitBranch
  updatedFiles: list[SessionFileUpdate]
  linkedArtifacts: list[SessionArtifact]
  toolsUsed: list[ToolUsage]
  impactHistory: list[ImpactPoint]
  logs: list[SessionLog]                # loaded on demand
  sessionMetadata: Optional[SessionMetadata]
  subagentType / displayAgentType
  linkedFeatureIds / phaseHints / taskHints  # P15-001 classification
  sessionForensics / forks / sessionRelationships
  usageEvents / usageAttributions / usageAttributionSummary
  intelligenceSummary: Optional[SessionIntelligenceSessionRollup]  # sentiment/churn/scopeDrift
  dates: EntityDates / timeline: list[TimelineEvent]
```

DB table `sessions` (`sqlite_migrations.py:88`): ~60 columns, most token/cost fields denormalized. `logs` not stored inline in sessions table — stored in `session_logs` and `session_messages` tables.

### 1.6 PlanDocument (`backend/models.py:1193`, `types.ts:978`)

```
PlanDocument
  id / title / filePath / canonicalPath / status / docType / category / docSubtype
  rootKind: "project_plans" | "progress" | "document"
  hasFrontmatter / frontmatterType
  featureSlugHint / featureSlugCanonical / prdRef / phaseToken / phaseNumber
  overallProgress / completionEstimate / priority / riskLevel / complexity
  track / timelineEstimate / targetRelease / milestone / decisionStatus
  executionReadiness / testImpact / primaryDocRole / featureSlug / featureFamily
  blockedBy / sequenceOrder / featureVersion / planRef / implementationPlanRef
  totalTasks / completedTasks / inProgressTasks / blockedTasks
  pathSegments / featureCandidates
  frontmatter: DocumentFrontmatter  # linkedFeatures, linkedSessions, lineage, commitRefs, etc.
  metadata: DocumentMetadata
  linkCounts: DocumentLinkCounts    # features/tasks/sessions/documents
  dates: EntityDates / timeline: list[TimelineEvent]
  content: Optional[str]            # markdown body, loaded on demand
```

DB table `documents` (`sqlite_migrations.py:344`): ~40 columns, heavily denormalized for search. Indexed by `project_id`, `doc_type`, `canonical_path`, `feature_slug_canonical`, `status_normalized`.

---

## 2. Planning Command Center Data Needs — Availability Matrix

| **Needed Data** | **Exists?** | **Source / Endpoint** | **Notes** |
|---|---|---|---|
| Active plans per project (features in-progress) | DONE | `GET /api/agent/planning/summary` → `ProjectPlanningSummaryDTO.status_counts.active` | Requires full feature+doc scan per call |
| Current phase / phase status per feature | DONE | `GET /api/agent/planning/context/{feature_id}` → `FeaturePlanningContextDTO.phases` | Phase data lives in `feature_phases` table + `data_json` |
| Feature status (raw + effective w/ mismatch) | DONE | Planning service: `PlanningEffectiveStatus.rawStatus/.effectiveStatus/.mismatchState` | Fully computed |
| Completed features | DONE | `status_counts.completed` in summary DTO | Derived from all features |
| Next recommended work (next phase per feature) | PARTIAL | `PlanningCommandCenterPhaseDTO.next_phase`, `PlanningNextRunPreviewDTO` | next_phase derived from phase list; no cross-project "next work" backlog view |
| Blocked features / phases | DONE | `blocked_feature_ids` in summary; `BlockerDTO` per item in command center | Quality signal blockers + phase-level blockers |
| Linked sessions per feature | PARTIAL | `FeatureForensicsDTO.linked_sessions` via `GET /api/agent/features/{id}/forensics` | Linkage is eventually-consistent (background sync); not available in planning summary |
| Live active session count per project | DONE | `GET /api/agent/live/active-count` → `LiveActiveCountDTO.count` | 10-second TTL, window-based |
| Active sessions board (per project) | DONE | `GET /api/agent/planning/session-board` → `PlanningAgentSessionBoardDTO` | Kanban grouping by state/feature/phase/agent/model |
| Multi-project command center aggregate | DONE | `GET /api/agent/multi-project/command-center` → `MultiProjectCommandCenterResponse` | Fan-out w/ NullGitProbe + page-first enrichment (MPCC-202/203/206) |
| SkillMeat artifact snapshots | DONE | `artifact_snapshot_cache` table; `GET /api/integrations/skillmeat/snapshot` | Via `SkillMeatArtifactSnapshot` contract |
| SkillMeat artifact rankings | DONE | `artifact_ranking` table; `GET /api/agent/artifact-intelligence/rankings` | `ArtifactRankingRow` with effectiveness scores |
| SkillMeat artifact recommendations | DONE | `ArtifactRecommendationService` generating from ranking rows | `ArtifactRecommendation` with rationale codes |
| SkillMeat workflow observations (stack) | DONE | `session_stack_observations` + `session_stack_components` tables | `SessionStackObservation` model |
| SkillMeat memory drafts | DONE | `session_memory_drafts` table; `GET /api/integrations/skillmeat/memory-drafts` | Draft→approved→published lifecycle |
| SkillMeat workflow effectiveness rollups | DONE | `effectiveness_rollups` table; `GET /api/integrations/skillmeat/workflow-effectiveness` | `WorkflowEffectivenessRollup` |
| SkillMeat outbound telemetry (SAM) | DONE | `outbound_telemetry_queue`; `services/integrations/telemetry_exporter.py` | `ExecutionOutcomePayload` + `ArtifactOutcomePayload` to SAM endpoint |
| Token telemetry per feature (by model family) | PARTIAL | `PlanningTokenTelemetry` in summary DTO, but always `source="unavailable"` | `tokenUsageByModel` NOT on Feature model; accessed via `getattr()` defensive — always None; `FeatureEvidenceSummary.token_usage_by_model` via forensics path DOES work |
| Planning graph (nodes/edges) | DONE | `GET /api/agent/planning/graph` → `ProjectPlanningGraphDTO` | Built from features + linked docs in-memory |
| Phase batch readiness | DONE | `PlanningPhaseBatch.readinessState` in `FeaturePlanningContextDTO.phases[*].batches` | Computed in `feature_execution.py` |
| Worktree context per feature | DONE | `planning_worktree_contexts` table; `PlanningCommandCenterWorktreeDTO` | git state lazily probed per page-visible item |
| Pull request linkage | PARTIAL | `Feature.prRefs` → `PlanningCommandCenterPullRequestDTO` | Only extracts first ref; no live PR status from GitHub API |
| Feature family sequencing / dependency state | DONE | `FeatureDependencyState`, `FeatureFamilySummary`, `ExecutionGateState` | Full dependency chain resolution |
| Available-next-work backlog (shaping/planned) | PARTIAL | `status_counts.shaping + .planned` counts; no dedicated "next work" list endpoint | Planned-status items surfaced in command center but no ranked backlog endpoint |
| Open questions per feature | DONE | `PlanningOpenQuestionItem` list in `FeaturePlanningContextDTO` | In-memory overlay; not DB-persisted |
| Spike items per feature | DONE | `PlanningSpikeItem` list in `FeaturePlanningContextDTO` | Derived from doc subtypes |
| ARC / agentic-research council reviews | MISSING | Not found in any backend service, model, router, or DB table | Zero implementation |
| MeatyWiki research integration | MISSING | Only "MeatyWiki" appears as a registered project name in `projects.json:654`, no API client or data model | Zero integration |
| Cross-project token/cost summary | PARTIAL | `system_metrics.py` active counts; `analytics.py` endpoint for per-project cost/token; no cross-project aggregate | No `/api/agent/system/token-rollup` equivalent |
| Project display metadata (color/group/sort) | DONE | `ProjectDisplayConfig` in `Project` model; `resolve_display_metadata()` for fallbacks | Deterministic hash-based fallbacks |

---

## 3. Planning Summary Payload Fields — statusCounts, ctxPerPhase, tokenTelemetry

### 3.1 `statusCounts` — `PlanningStatusCounts` (`planning/models.py:317`)

**Status**: DONE (shipped in P13-001)

Buckets: `shaping | planned | active | blocked | review | completed | deferred | stale_or_mismatched`

Source: `_build_status_counts(projected)` in `planning.py:788`. Iterates all projected features, applies precedence: `blocked > review > active > planned > shaping > completed > deferred > stale_or_mismatched`. Returned in `ProjectPlanningSummaryDTO.status_counts`.

### 3.2 `ctxPerPhase` — `PlanningCtxPerPhase` (`models.py:330`)

**Status**: DONE (shipped in P13-001)

Fields: `context_count / phase_count / ratio (float|None) / source ("backend"|"unavailable")`

Source: `_build_ctx_per_phase()` in `planning.py:806`. Counts context-type planning nodes divided by total phase count. `ratio=None` when `phase_count=0`.

### 3.3 `tokenTelemetry` — `PlanningTokenTelemetry` (`models.py:346`)

**Status**: BROKEN/PARTIAL — always `source="unavailable"`

The implementation (`planning.py:826-862`) calls `getattr(feature, "tokenUsageByModel", None)` on each projected Feature. The `Feature` model (`models.py:2052-2097`) does **not** define `tokenUsageByModel` as a field. The `getattr` guard therefore always returns `None`, `family_totals` stays empty, and the payload returns `PlanningTokenTelemetry(total_tokens=None, by_model_family=[], source="unavailable")`.

The correct data path is through `FeatureEvidenceSummaryService.get_summary()` → `token_usage_by_model` (a `TokenUsageByModel` with opus/sonnet/haiku/other/total), which aggregates from joined session rows. This path IS used in `get_feature_planning_context()` (`planning.py:1416-1428`) for the per-feature detail view but NOT fed back to the summary-level telemetry.

**Fix needed**: Either add `tokenUsageByModel: Optional[TokenUsageByModel]` to `Feature` model and populate it during feature reconstruction in `feature_from_row()`, or aggregate token telemetry at summary time by calling `FeatureEvidenceSummaryService` per feature (expensive) or building a batch aggregate SQL query.

---

## 4. SkillMeat / SAM Integration Surfaces

### 4.1 What Flows Today

| Integration Point | Status | Implementation File |
|---|---|---|
| SkillMeat artifact snapshot fetch (pull) | DONE | `services/integrations/skillmeat_client.py` |
| Snapshot cache storage | DONE | `artifact_snapshot_cache` table |
| Artifact identity mapping (CCDash name → SM uuid) | DONE | `artifact_identity_map` table |
| Artifact ranking table (per-workflow/period) | DONE | `artifact_ranking` table; `artifact_ranking_service.py` |
| Artifact recommendation generation | DONE | `artifact_recommendation_service.py` |
| Session stack observations + components | DONE | Tables + `stack_observations.py` |
| Outbound: `ExecutionOutcomePayload` → SAM | DONE | `telemetry_exporter.py` + `sam_telemetry_client.py` |
| Outbound: `ArtifactOutcomePayload` → SAM | DONE | `artifact_rollup_export_job.py` |
| SkillMeat memory drafts (session → module) | DONE | `skillmeat_memory_drafts.py` |
| SkillMeat definition sync (artifacts/workflows) | DONE | `external_definitions` table + `skillmeat_sync.py` |
| SkillMeat workflow effectiveness rollups | DONE | `effectiveness_rollups` table + `workflow_effectiveness.py` |
| Workflow registry (observed CLI/commands → SM workflows) | DONE | `workflow_registry.py` |
| SkillMeat trust/AAA validation | DONE | `skillmeat_trust.py` |

### 4.2 What Is Missing From SkillMeat

- **No reverse webhook / push subscription**: SkillMeat pushes data to CCDash only via pull (scheduled sync). There is no inbound event handler for SM pushing snapshot updates.
- **No cross-project artifact usage rollup via SAM API**: The `ArtifactUsageRollup` schema is defined but no endpoint calls back to SAM to fetch per-artifact aggregate data; CCDash computes its own from local session data only.
- **No `ArtifactVersionOutcomePayload` currently emitted**: The `content_hash` requirement means version-level outcomes need explicit hash tracking which is not wired in the export job.

---

## 5. ARC (Agentic Research Council) Integration

**Status**: ENTIRELY MISSING

Zero references to "ARC", "agentic-research", "research council" in the backend Python, TypeScript, or config files (excluding `.venv` and third-party lexers). The `MeatyWiki` name appears only as a registered project entry in `projects.json:654` — it is not an API integration target, not a data source, and has no client, model, schema, or endpoint in CCDash.

There is no concept of:
- Research notes, investigation reports, or wiki articles as a data source
- Council review status attached to features or planning artifacts
- Any authenticated client for an ARC/MeatyWiki API
- Any `research_note`, `council_review`, or `wiki_article` entity in the type system

---

## 6. Key Denormalization Gaps

### 6.1 Feature Data in BLOB

`features.data_json` (`sqlite_migrations.py:431`) stores the full Feature payload as JSON. Fields like `tags`, `owners`, `phases`, `linkedDocs`, `dependencyState`, `linkedFeatures`, `prRefs`, `commitRefs` are NOT in individual columns. This means:

- Any query filtering on tags, owners, or phase status requires full table scan + JSON parsing in application layer
- The SQL indexes only cover `project_id`, `status`, `category`, `completed_at`, `started_at`, `planned_at` (added in migrations)
- Feature family ordering and dependency chain resolution happen entirely in Python (CPU-intensive, not DB-accelerated)

### 6.2 `tokenUsageByModel` on Feature — Missing Field

As documented in §3.3, the `Feature` model lacks `tokenUsageByModel`. This means `PlanningTokenTelemetry.source` will always be `"unavailable"` in project-level planning summaries. The token intelligence for the command center header KPIs is broken.

### 6.3 Projects in JSON — No DB Table

`projects.json` is the sole source of truth for projects. In a containerized deployment where the filesystem may not be writable or may be ephemeral:
- Registered projects would not survive container restarts unless `projects.json` is volume-mounted
- No multi-tenant isolation: all projects share one `projects.json`
- No API for registering projects without filesystem access

### 6.4 Open Questions Not Persisted

`PlanningOpenQuestionItem` answers are held in `_OQ_OVERLAY` — a process-memory dict in `planning.py:109`. Resolutions are **not written to any DB table** (`pending_sync=True` flag exists but no sync path). Container restarts or multi-instance deployments lose all OQ resolutions.

### 6.5 Planning Graph Computed In-Memory

`build_planning_graph()` is called per feature, per request (after `@memoized_query` TTL). For large projects (e.g. skillmeat with 100+ features), this means building hundreds of planning graphs on cache miss. No precomputed graph snapshot in DB.

---

## 7. Summary Payload vs Detail Payload Split

### Summary Payload (for list/aggregate views)

Appropriate fields (already in `ProjectPlanningSummaryDTO` / `PlanningCommandCenterPageDTO`):
- `status_counts` (shaping/planned/active/blocked/review/completed/deferred/stale_or_mismatched)
- `feature_summaries` (FeatureSummaryItem: id, name, raw_status, effective_status, is_mismatch, phase_count, node_count)
- `ctx_per_phase` ratio
- `node_counts_by_type` (prd/design_spec/impl_plan/progress/context/tracker/report)
- `blocked_feature_ids / stale_feature_ids / reversal_feature_ids`
- Per item: `PlanningCommandCenterItemDTO` with feature identity, status, tier, story_points, phase summary, blockers, command

### Detail Payload (for single feature views)

Appropriate for on-demand fetch:
- Full planning graph (nodes + edges + phase_batches)
- Full phase list with task detail
- Open questions + spike items
- Token telemetry by model family
- Linked artifact refs (prds, plans, specs, ctxs, reports)
- Execution context (recommendations, stack, family position, gate state)
- Session board (linked sessions as cards)
- Next-run preview with prompt skeleton

**Gap**: Token telemetry (even the summary-level `total_tokens`) should be in the summary payload but is broken (`source="unavailable"`). This needs to be fixed before enterprise-grade KPI dashboards work.

---

## 8. Multi-Project / Enterprise Readiness Gaps

| Gap | Severity | Evidence |
|---|---|---|
| `projects.json` not DB-backed | Critical | `backend/project_manager.py`; no SQL table for projects |
| `tokenUsageByModel` not on Feature → telemetry always unavailable | Critical | `planning.py:833`; `models.py:2052-2097` |
| Open question overlays in-memory only | High | `planning.py:109` — `_OQ_OVERLAY` dict, not persisted |
| Feature `data_json` BLOB — no columnar phase/tag/owner indexing | High | `sqlite_migrations.py:431` |
| Planning graph recomputed in-memory per cache TTL | High | `planning.py:1267` — `build_planning_graph()` per feature |
| ARC/MeatyWiki integration: zero implementation | High | No files found |
| No cross-project token/cost aggregate endpoint | Medium | `system_metrics.py` only does session counts; no token rollup |
| PR status not live (only stored refs) | Medium | `models.py:2283` — only `prRefs` string list, no GitHub client per item |
| No available-next-work backlog endpoint | Medium | Status bucket counts exist but no ranked "next to execute" query |
| Outbound SAM: `ArtifactVersionOutcomePayload` not emitted | Low | `models.py:356-363` — defined but not wired in export job |

---

## 9. DB Schema Summary (relevant tables)

| Table | Purpose | Key Indexes |
|---|---|---|
| `sessions` | Agent sessions (60+ columns, mostly denormalized) | `(project_id, started_at)`, `(project_id, status, updated_at)`, `conversation_family_id`, `updated_at` |
| `session_logs` | Per-session JSONL log entries | `(session_id, log_index)`, `source_log_id` |
| `session_messages` | Parsed message blocks | `(conversation_family_id)` |
| `session_file_updates` | File touch events | `session_id`, `file_path` |
| `session_usage_events` | Token attribution events | `(project_id, session_id)`, `entity dims` |
| `session_usage_attributions` | Attribution rows per event | `entity_type/id`, `method` |
| `session_relationships` | Parent/child session links | `(project_id, parent_session_id)`, `(project_id, child_session_id)` |
| `session_stack_observations` | SkillMeat stack per session | `(project_id, session_id)`, `(project_id, feature_id)` |
| `session_memory_drafts` | SM memory draft pipeline | `(project_id, status)`, `(project_id, session_id)` |
| `features` | Feature records (data_json BLOB) | `project_id`, `status+updated`, `category`, `completed/started/planned_at` |
| `feature_phases` | Phase records (data_json BLOB) | `feature_id` |
| `tasks` | Task records | `(feature_id, phase_id)`, `(project_id, status)` |
| `documents` | Plan docs + progress files | `project_id`, `doc_type`, `canonical_path`, `feature_slug_canonical`, `status_normalized` |
| `document_refs` | Cross-reference index | `(project_id, ref_kind, ref_value_norm)` |
| `entity_links` | Generic entity cross-links | `(source_type, source_id)`, `(target_type, target_id)` |
| `artifact_snapshot_cache` | SkillMeat snapshot data | `(project_id, fetched_at)`, `(project_id, collection_id)` |
| `artifact_identity_map` | CCDash name → SM uuid mapping | `(project_id, ccdash_name)`, `(project_id, skillmeat_uuid)` |
| `artifact_ranking` | Per-artifact usage/effectiveness metrics | `(project_id, period)`, `(artifact_uuid, period)`, `(workflow_id, period)` |
| `effectiveness_rollups` | SM workflow effectiveness | `(project_id, scope_type, scope_id, period)` UNIQUE |
| `planning_worktree_contexts` | Worktree context per feature/phase | `(project_id, feature_id)`, `(project_id, status)` |
| `execution_runs` + `execution_run_events` | CLI execution tracking | `(project_id, feature_id)`, `(project_id, status)` |
| `test_runs` / `test_definitions` / `test_results` | Test platform integration | `(project_id, timestamp)`, `(project_id, agent_session_id)` |
| `outbound_telemetry_queue` | SAM telemetry export queue | `status`, `created_at` |
| `commit_correlations` | Git commit → session/feature correlation | `(project_id, commit_hash)`, `session_id`, `feature_id` |
| `session_sentiment_facts` / `session_code_churn_facts` / `session_scope_drift_facts` | Intelligence heuristics | Per-session, per-project |

---

## 10. Frontend Type System Summary

`types.ts` (~4000 lines) covers:

- **Auth types** (lines 1-70): `AuthProviderMetadataResponse`, `AuthSessionResponse`, `AuthSessionMembership` — full JWT/OAuth surface
- **Core entities** (lines 73-490): `AgentSession`, `SessionLog`, `SessionFileUpdate`, `SessionArtifact`, `ToolUsage`, `ProjectTask`
- **Intelligence** (lines 490-1000): Full `SessionUsageEvent/Attribution/Aggregate/Drilldown`, `SessionIntelligence*` (sentiment/churn/scope_drift)
- **Documents** (lines 978-1135): `PlanDocument` (matches backend model)
- **Analytics** (lines 1145-1490): `AnalyticsOverview`, `AnalyticsBreakdownItem`, `AnalyticsArtifactsResponse` (massive multi-dimensional artifact analytics DTO)
- **SkillMeat/SAM** (lines 253-600, 1490-1640): Artifact snapshot, ranking, recommendation, usage rollup, effectiveness types — **fully mirrored from backend models**
- **Planning** (lines 1840-2200+): `PlanningNode/Edge/Graph`, `FeaturePhase`, `Feature`, `FeatureExecutionContext`, `PlanningCommandCenter*` DTOs — complete
- **Multi-project** (lines ~3391+): `MultiProjectCommandCenterResponse`, `ProjectSummary`, `AggregateWorkItem`, `AggregatePagination` — matches backend models.py exactly

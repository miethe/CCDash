---
schema_version: 2
doc_type: report
report_category: feasibility
title: "Branch-Aware Planning Intelligence (R-01: BranchWatcherRegistry) — Feasibility
  Brief"
status: finalized
created: 2026-06-04
updated: '2026-06-04'
feature_slug: branch-aware-planning-intelligence
verdict: conditional
verdict_confidence: 0.88
exploration_charter_ref: 
  docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md
proposed_adr_ref: 
  docs/project_plans/adrs/adr-008-branch-watcher-registry-planning-service-seam.md
recommended_next_action: "/plan:plan-feature --tier=2 --charter=docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md
  — with four preconditions: (1) ADR-007 retrofit for SqliteDocumentRepository.upsert
  scoped as mandatory Phase 0 task; (2) BranchWatcherRegistry lifecycle notification
  mechanism (planning service write path → register/unregister) explicitly designed
  in PRD data contracts section, with proposed ADR-008 cited; (3) startup sync serialization
  path specified in Phase 1 task breakdown; (4) Phase 1 AC for Codex null-branch disclosure
  included per charter disclosure constraints."
related_documents:
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/watcher-arch-findings.md
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/data-model-findings.md
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/risk-findings.md
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/tech-findings.md
- docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/ux-value-findings.md
spike_legs:
- id: watcher-arch
  confidence: 0.88
  status: complete
- id: data-model
  confidence: 0.88
  status: complete
- id: ux-value
  confidence: 0.82
  status: complete
---

# Branch-Aware Planning Intelligence (R-01: BranchWatcherRegistry) — Feasibility Brief

---

## 1. Synopsis

Branch-Aware Planning Intelligence (R-01) covers the design of multi-branch/worktree filesystem watching for CCDash's planning surfaces. The parent exploration charter (status: conditional) established that Phase 1 display-from-existing-data is a go, but Phase 2 multi-branch doc scanning was gated on this dedicated spike to answer six research questions: the correct operator-registered vs auto-discovery design for worktree binding under ADR-006, the shape of a BranchWatcherRegistry abstraction over the existing `FileWatcher`/`FileWatcherRegistry` infrastructure, the write-amplification and performance envelope of watching N worktrees simultaneously, the DB schema changes needed for branch-scoped document coexistence, the cache key strategy for branch-aware planning queries, and the branch-to-feature session linkage model. This brief synthesizes findings from three parallel research legs (watcher-arch, data-model, and ux-value) and delivers a concrete conditional-go recommendation for Phase 2 implementation.

The gitBranch coverage audit (recorded in the charter notes, 2026-06-04) passed at 99.1% on feature-linked sessions, removing the coverage gate on story S3 (branch/commit click-dialog). S3 is ungated into Phase 1 scope. The UX leg additionally identified three concrete gaps with direct Phase 2 AC implications: the missing active-session chip on `CommandCenterFeatureCard`, the absent sessions tab on `CommandCenterDetailPanel`, and ongoing consolidation debt between the planning side pane and the board modal.

---

## 2. Investigation Summary

| Leg | Agent | Confidence | Findings | Conclusion |
|-----|-------|-----------|----------|------------|
| watcher-arch | codebase-explorer | 0.88 | [watcher-arch-findings.md](./watcher-arch-findings.md) | Operator-registered worktree paths via `planning_worktree_contexts` is the only ADR-006-compliant binding source; a parallel `BranchWatcherRegistry` keyed by `(project_id, worktree_path)` mirroring `FileWatcherRegistry` is architecturally feasible, scoped to docs/progress dirs only, with manageable write amplification at N≤5. |
| data-model | codebase-explorer | 0.88 | [data-model-findings.md](./data-model-findings.md) | Adding `branch TEXT DEFAULT ''` to `documents` (O(1) SQLite) plus a composite index on `sessions(git_branch, project_id)` is the minimal-cost correct design; `@memoized_query` with `branch_filter` as a `param_extractor` dimension provides backward-compatible branch-aware cache isolation with project-scoped eviction via `aclear_project_cache`; ADR-007 retrofit on `SqliteDocumentRepository.upsert` is a prerequisite gate. |
| ux-value | ux-researcher | 0.82 | [ux-value-findings.md](../ux-value-findings.md) | Active-session chip missing from `CommandCenterFeatureCard` (highest-priority gap; pattern exists in `MultiProjectWorkItemCard`); `CommandCenterDetailPanel` has no sessions tab or per-phase session links; `ProjectBoard` modal already carries branch/session/commit data and is the correct long-term consolidation target via `planningRouteFeatureModalHref`. |

All three legs returned complete, non-partial findings. Aggregate confidence: **0.87** (weighted mean across all three leg confidence scores).

---

## 3. Cost Estimate

**Rough estimate**: 20–27 story points (Tier 2)

**Comparable past feature**: Planning session board (`ccdash-planning-reskin-v2`) — approximately 15–20 pts, delivered across 3 phases; that feature introduced `PlanningAgentSessionBoard`, new backend planning query surfaces, and incremental DB migrations. Phase 2 branch-watcher work is narrower (no new UI components from scratch) but introduces new infrastructure (BranchWatcherRegistry) and ADR-007 retrofit debt. The UX leg adds non-trivial frontend work that was absent from the prior estimate.

**Major cost drivers**:

- `BranchWatcherRegistry` class, container registration, startup lifecycle serialization, and snapshot API extension: ~5 pts
- ADR-007 retrofit on `SqliteDocumentRepository.upsert` + direct-count assertion tests + Postgres parity migration: ~3 pts
- DB migration (v34): `documents.branch` column, `sessions(git_branch, project_id)` index, Postgres parity: ~2 pts
- `_correlate_branch` step 5a in `session_correlation.py`, exclusion set, prefix normalization, `PlanningAgentSessionCardDTO.git_branch` field: ~3 pts
- `@memoized_query` `branch_filter` param_extractor dimension on four planning endpoints: ~2 pts
- Integration tests (ADR-007 direct-count, lock-injection, correlation pipeline, watcher lifecycle): ~3 pts
- **UX: Active-session chips on `CommandCenterFeatureCard`** — backend `activeSessions` enrichment on command-center item query + frontend chip row (mirrors `MultiProjectWorkItemCard` pattern): ~2–3 pts
- **UX: Per-phase session links in `CommandCenterDetailPanel`** — backend phase→sessions inverse query + frontend "phase sessions" section with transcript links (mirrors `PlanningAgentSessionDetailPanel`): ~3–4 pts
- **UX: Branch/commit click-dialog on feature cards** — replace static branch row with clickable popover showing linked branches, commit SHAs, per-branch sessions (ungated by 99.1% coverage audit): ~2 pts

**Hidden plumbing budget** (~15%): operator documentation, CLAUDE.md pointer updates, `--reload-exclude` guidance for dev mode, proposed ADR-008 authoring.

---

## 4. Value Statement

**Primary beneficiaries**: Operators running multi-worktree development workflows where agent sessions span more than one checked-out branch simultaneously (e.g., parallel feature branches, hotfix worktrees alongside active feature work).

**Evidence of demand**:
- Charter hypothesis: operators currently lose visibility into work happening on non-checked-out branches; planning items cannot be traced to the sessions or commits that produced them (operator-reported pain, verified structurally by the tech leg as addressable from existing `sessions.git_branch` data).
- The `planning_worktree_contexts` table was specifically introduced prior to this spike, signaling operator intent to use CCDash with multiple concurrent worktrees.
- `sessions.git_branch` is already a persisted DB column populated from JSONL (tech-leg confirmed); the correlation signal is latent — it only needs a query pipeline step and index to be surfaced.
- UX leg finding (confidence 0.95): `CommandCenterFeatureCard` has no active-session chip — operators cannot see "N agents running now on this feature" without navigating to the separate session board. This is the highest-value missing affordance, with a direct implementation template in `MultiProjectWorkItemCard` lines 97–123.
- UX leg finding (confidence 0.95): `PhasePlanTable` (in `CommandCenterDetailPanel`) shows phase/status/agent/model but no session links per phase; the per-session transcript link pattern already exists in `CardActionRow` and `PlanningAgentSessionDetailPanel`.

**gitBranch coverage audit (post-verdict)**: The charter notes record a 99.1% coverage rate on feature-linked sessions (audit completed 2026-06-04). This removes the tech-leg coverage gate on S3 (branch/commit click-dialog) and elevates S3 from conditional to Phase 1 scope. The original synthesis verdict_confidence was calculated before this audit; the updated aggregate is unchanged at 0.88 for the watcher/data-model legs; the ux-value leg at 0.82 lowers the three-leg aggregate slightly to 0.87, but the S3 ungate is a positive signal that offsets this.

**Counterfactual**: If Phase 2 is not built, operators with active multi-worktree workflows see planning board sessions that are not filtered or correlated by branch, doc syncs cover only the main checkout path (missing work-in-progress docs on feature branches), and branch-to-feature session linkage remains absent from planning cards, requiring manual cross-referencing outside CCDash. The active-session chip gap means operators cannot immediately see live agent activity on the planning command center — they must navigate to a separate board.

---

## 5. Risks & Blast Radius

| Risk | Category | Severity | Mitigation |
|------|----------|---------|------------|
| ADR-007 retrofit debt: `SqliteDocumentRepository.upsert` uses bare `self.db.commit()` without `retry_on_locked`, violating ADR-007 §2; Phase 2 branch write path inherits this violation if not fixed first | technical | H | Retrofit is a prerequisite gate — must ship in the same PR as the `branch` column write path; treat as Phase 2 entry criterion |
| Codex null-branch structural limitation: `backend/parsers/platforms/codex/parser.py` line 1244 hardcodes `gitBranch=None`; any branch-filter dimension or branch-signal correlation is silently broken for Codex sessions; charter explicitly names this as a disclosure constraint that must carry into Phase 1 PRD as ACs | technical | H | Phase 1 UI must treat `gitBranch=None` as a first-class state, not a missing-data case; active-session chips, branch/commit dialog, and session board filters must all handle null branch with graceful empty-state; do not gate any planning logic on branch presence per risk leg R-02; document as known Codex limitation in operator guidance |
| Document identity collision: two worktrees syncing the same file path overwrite each other at upsert because PK is `id` (slug/hash), not `(project_id, file_path, branch)`; last-writer-wins is Phase 2 known limitation | technical | M | Accept as Phase 2 known limitation; document explicitly for operators; Phase 3 scope includes PK change for full per-worktree isolation |
| Write amplification at N=10+ branch watchers triggers N full entity_links rebuilds (`INCREMENTAL_LINK_REBUILD_ENABLED=false` default); ~6s serialized rebuild work at N=3 during heavy agent activity | technical | M | Enforce serialized startup sync; document N≤5 as supported operational range; enable `CCDASH_STARTUP_SYNC_LIGHT_MODE` for large worktree deployments |
| uvicorn --reload drops all watcher registrations (main + N branch) on every code change in dev mode; missed-event windows compound with N active worktrees | operational | M | Accept as dev-mode limitation (existing accepted risk); provide operator guidance for `--reload-exclude` configuration; production worker-watch profile is unaffected |
| Branch correlation false-positive rate: subjective <5% FP estimate is unvalidated; real rate may be higher for projects with short or generic branch naming conventions | technical | M | Enforce 8-char minimum length + concrete exclusion set at shipping; add telemetry hook for FP rate measurement post-ship; make exclusion set configurable via env var |
| Codex/cwd indexability gap: `workingDirectories`/cwd is stored in `session_forensics_json` blob (not a direct DB column) per risk leg findings (confidence 0.95); any Phase 2 work inferring branch from cwd requires a migration to surface cwd as a direct column or a runtime JSON extraction; non-indexable without migration | technical | M | Scope cwd-based branch inference to Phase 3 or later; Phase 2 must not depend on cwd indexing; document as known limitation in PRD; if cwd inference is added to Phase 2, a `_ensure_column` migration to extract cwd into a direct column is a prerequisite |
| Postgres parity gap: branch column addition and v34 migration must be mirrored in postgres_migrations.py with ON CONFLICT DO UPDATE SET branch = EXCLUDED.branch; no dedicated Postgres ADR-007 test currently planned | technical | M | Treat Postgres parity as co-equal migration deliverable; add dedicated Postgres direct-count assertion test per ADR-007 |
| Auto-discovery via git worktree list as UI registration aid must be strictly gated from becoming a runtime binding path; any refactor risk would constitute an ADR-006 violation | organizational | M | Enforce code-review gate: `git worktree list` invocations must not appear outside the UI registration helper; add a linting comment at the call site |
| Planning service → BranchWatcherRegistry cross-layer dependency: the planning service write path calling `BranchWatcherRegistry.register()` on INSERT introduces a new cross-owner seam between the planning service layer and watcher infrastructure; see proposed ADR-008 | organizational | M | Document in proposed ADR-008; enforce via code review that register/unregister are called only from the planning control plane write path; no other service layer may call BranchWatcherRegistry directly |
| `PlanningAgentSessionCardDTO` serialization contract: adding git_branch field must be validated against all existing API consumers to avoid breaking existing contracts | technical | L | Add field as Optional with None default; validate against `backend/routers/agent.py` response serialization and frontend `types.ts` before merging |
| Incremental link rebuild entity_ids gap: `_sync_documents`/`_sync_sessions` return counts not entity_ids, causing full rebuilds even when `INCREMENTAL_LINK_REBUILD_ENABLED=true`; branch watchers inherit this limitation | technical | L | Track as known limitation; if incremental rebuild is on near-term roadmap, entity_ids surfacing is a prerequisite — flag as Phase 3 dependency |
| BranchWatcherRegistry snapshot API breaks existing dict[project_id, dict] contract in `_watcher_registry_snapshot()` if composite keys are used | technical | L | Use parallel snapshot key (`branch_watchers`) rather than composite keys; document extension point in runtime.py |

---

## 6. Architectural Implications

The R-01 spike surfaces several architectural patterns that must be carried forward regardless of the exact implementation schedule.

**Proposed ADR-008 — BranchWatcherRegistry/Planning-Service seam**: Section 6 of this brief introduces a new cross-layer dependency: the planning service write path calling `BranchWatcherRegistry.register()` on `planning_worktree_contexts` INSERT. This is a cross-owner seam between the planning service layer and the watcher infrastructure layer. It does not resolve to an extension of ADR-006 (registry is DB-authoritative) or ADR-007 (write failure surfacing) — it introduces a new bounded coupling contract between two previously independent layers. Per project ADR threshold, this seam requires documentation. The proposed ADR (status: proposed, to be accepted at PRD approval) should define: the call site (planning control plane write path only), the interface contract (register on INSERT status=running, unregister on UPDATE to terminal status), and the prohibition on any other service layer calling BranchWatcherRegistry directly.

**BranchWatcherRegistry as a first-class runtime singleton**: The registry must be registered in `backend/runtime/container.py` alongside `FileWatcherRegistry`, with its lifecycle tied to `RuntimeJobAdapter.start()/stop()`. It is keyed by `(project_id, worktree_path)` and reuses `FileWatcher` instances internally — no modification to `FileWatcher.start()` is required. The planning control plane's write path for `planning_worktree_contexts` must call `BranchWatcherRegistry.register()` on INSERT (status=running) and `unregister()` on UPDATE to terminal status. This introduces the cross-layer dependency documented in proposed ADR-008.

**Shared sync_engine entry point**: `sync_engine.sync_changed_files()` remains the single sync entry point for both primary and branch watcher events. No new sync codepath should be introduced. All syncs use the parent `project_id`, ensuring ADR-006 compliance. The branch label in `BranchWatcherEntry` is for logging and snapshot metadata only.

**Transport-neutral agent query extension**: `_correlate_branch` is a new step 5a in `session_correlation.py`, following the established extension point pattern. `git_branch` is added to `PlanningAgentSessionCardDTO` in `agent_queries/models.py`. The branch exclusion set (`_BRANCH_EXCLUSION_SET`), prefix normalization (`_BRANCH_PREFIXES`, `_normalize_branch_for_correlation`), and 8-character minimum-length threshold are module-level constants collocated with `_correlate_command_tokens`.

**Cache isolation via param_extractor (project-scoped by design)**: Adding `branch_filter` as a `param_extractor` dimension on the four `@memoized_query`-wrapped planning endpoints is backward-compatible (when `branch_filter=None`, the key is identical to today's). The cache key structure is `{endpoint_name}:{project_id}:{param_hash}:{fingerprint}` — `project_id` is embedded as a structural key segment. `aclear_project_cache(project_id)` evicts by project_id prefix match, making all cache eviction project-scoped by design. There is no global cache eviction on per-project sync. The `_FINGERPRINT_TABLES` set does not require changes because `sessions.updated_at` already covers new sessions from any branch and `planning_worktree_contexts.updated_at` covers new worktree registrations.

**UX layer — active-session enrichment**: `PlanningCommandCenterItem` requires a new `activeSessions` field (type `AggregateWorkItemSession[]`, nullable) to support the chip row on `CommandCenterFeatureCard`. The `MultiProjectWorkItemCard` session indicator strip (lines 97–123) is the direct implementation template. The backend command-center item query must be enriched to return running sessions per feature. This is a new query join, not a new endpoint.

**UX layer — phase sessions section**: `CommandCenterDetailPanel` requires a "phase sessions" section below the existing phase plan table. The inverse query (feature phase → sessions) is not currently exposed; it requires a new query join on `(feature_id, phase_number)` returning `PlanningAgentSessionCardDTO` rows. The transcript link and session card patterns are already established in `CardActionRow` and `PlanningAgentSessionDetailPanel`.

**UX layer — consolidation path**: `CommandCenterDetailPanel` should gain a "Open full detail" button navigating to `planningRouteFeatureModalHref`. This makes the richer `ProjectBoard` feature modal (with sessions tab, history tab, branch/commit data) reachable from the planning command center without a full side-pane replacement. Full consolidation (replacing `CommandCenterDetailPanel` with the modal as primary) is deferred; `MultiProjectDetailRail` already records this debt ("Future: full modal replacement once existing modal hooks are project-scoped").

**Phase 2 is display-first, read-path only**: No PK changes, no new write tables, no join tables. The branch column on `documents` adds a query-filtering dimension; last-writer-wins at upsert is an accepted limitation. Phase 3 is the scope boundary for full per-worktree document isolation (composite PK) and richer linkage models.

**Session watch scope exclusion**: Sessions directories must be explicitly excluded from `BranchWatcherEntry.watch_paths`. Watch scope is strictly `(worktree_path/docs_subdir, worktree_path/progress_subdir)`. This constraint must be documented and enforced at the `register()` call site.

---

## 7. Verdict

**Verdict**: conditional
**Confidence**: 0.88 (R-01 watcher/data-model legs); 0.87 three-leg aggregate including ux-value

**Rationale**: All three R-01 research legs return complete, non-partial findings. Phase 2 multi-branch doc scanning is architecturally feasible without violating ADR-006 or ADR-007: the operator-registered model using `planning_worktree_contexts` as the sole runtime binding source, a parallel `BranchWatcherRegistry` reusing `FileWatcher` instances, and the minimal DB additions (branch column on `documents`, composite index on `sessions(git_branch, project_id)`) form a coherent, low-risk Phase 2 design. The UX leg confirms three high-value affordances with direct implementation templates (active-session chips, per-phase session links, branch/commit dialog). The gitBranch coverage audit (99.1% on feature-linked sessions) removes the coverage gate on S3 and elevates it to Phase 1 scope.

The verdict is conditional because: (1) the ADR-007 retrofit on `SqliteDocumentRepository.upsert` is a high-severity prerequisite gate that must be resolved before the branch write path ships — it is pre-existing technical debt that Phase 2 would inherit; (2) write amplification at N=10+ is extrapolated at 0.60 confidence and requires profiling before Phase 3 multi-worktree scale-out; (3) the event mechanism driving `planning_worktree_contexts` lifecycle notifications to `BranchWatcherRegistry` (event bus vs. polling vs. direct call) is an unresolved open question that must be answered in the Phase 2 implementation plan before task decomposition; and (4) the Codex null-branch structural limitation must carry into Phase 1 PRD as explicit ACs per the charter disclosure constraints.

**Recommended next action**: `/plan:plan-feature --tier=2 --charter=docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md` — author Phase 2 PRD with: (a) ADR-007 retrofit as Phase 0 entry criterion; (b) BranchWatcherRegistry lifecycle notification mechanism explicitly designed in PRD data contracts section with proposed ADR-008 cited; (c) startup sync serialization path specified in Phase 1 task breakdown; (d) Codex null-branch disclosure ACs in Phase 1; (e) UX stories (active-session chips ~2–3 pts, per-phase session links ~3–4 pts, branch/commit dialog ~2 pts) in scope.

**Preconditions before PRD approval**:
1. ADR-007 retrofit design for `SqliteDocumentRepository.upsert` is scoped in the PRD as a mandatory Phase 0 task (not deferred to Phase 3).
2. The `BranchWatcherRegistry` lifecycle notification mechanism (`planning_worktree_contexts` INSERT/UPDATE → register/unregister path) is explicitly designed in the PRD data contracts section, with proposed ADR-008 cited.
3. The BranchWatcherRegistry startup sync serialization path (wired into `_run_all_projects_sync_job` or a separate coroutine) is specified in the Phase 1 task breakdown.
4. Phase 1 ACs include Codex null-branch graceful-empty-state handling per charter disclosure constraints.

---

## 8. Open Questions Carried Forward

These questions are unresolved at the end of the R-01 spike and must be addressed in the Phase 2 PRD. Questions 6 and 8 from the prior synthesis have been resolved by spike artifacts and are removed from the carried-forward list; their answers are recorded below.

**Resolved — not carried forward:**

- **[Resolved] branch_filter=None default behavior**: The risk leg (R-02) explicitly states "do not gate any planning logic on branch presence" and "Phase 1 UI must show branch as optional field with graceful empty-state." The only safe default is `branch_filter=None` returns sessions across ALL branches (current behavior), preserving backward compatibility and handling the Codex null-branch population transparently. This is not an ambiguous PRD question.

- **[Resolved] aclear_project_cache eviction scope**: The cache key structure (`{endpoint_name}:{project_id}:{param_hash}:{fingerprint}`) embeds `project_id` as a structural segment. `aclear_project_cache(project_id)` evicts by project_id prefix match. Eviction is project-scoped by design. There is no global cache eviction; cross-project contention from per-project sync is not a concern.

**Carried forward:**

1. What event mechanism drives `planning_worktree_contexts` INSERT/UPDATE notifications to `BranchWatcherRegistry`? Is there an existing event bus, or does the registry need to be called directly from the planning control plane write path (service-layer coupling)? This determines the proposed ADR-008 interface contract.
2. Should `BranchWatcherRegistry` live in `backend/db/file_watcher.py` alongside `FileWatcherRegistry`, or in a new `backend/db/branch_watcher.py`? Each option has different import-graph and test-isolation implications.
3. What is the startup sync serialization path — wired into `_run_all_projects_sync_job` or a separate startup coroutine triggered after project sync completes?
4. When a `worktree_path` does not exist on disk at startup (worktree deleted without a status update), should the registry log a warning and skip, or update the `planning_worktree_contexts` row to a terminal status?
5. What are the actual measured timings for `sync_changed_files` under N=3–5 simultaneous watcher events? The 0.70-confidence write-amplification estimate requires profiling to validate before Phase 3 N=10+ scale-out.
6. Should exact feature-ID branch slug matches (`feat/my-feature-slug` matching feature ID `my-feature-slug`) be auto-promoted to `confidence='high'`? If so, what constitutes an exact match (case-insensitive, hyphen/underscore normalized)?
7. What operator guidance is needed for `--reload-exclude` configuration in dev mode to partially mitigate the uvicorn reload hazard for branch watchers?

---

## 9. Citations

- Exploration charter: `docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md`
- Watcher architecture leg findings: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/watcher-arch-findings.md`
- Data model leg findings: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/data-model-findings.md`
- UX value leg findings: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/ux-value-findings.md`
- Prior risk register (R-01 through R-08): `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/risk-findings.md`
- Prior integration-point inventory: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/tech-findings.md`
- ADR-006 (DB-authoritative project registry): `docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md`
- ADR-007 (DB write failure surfacing standard): `docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md`
- Proposed ADR-008 (BranchWatcherRegistry/planning-service seam): `docs/project_plans/adrs/adr-008-branch-watcher-registry-planning-service-seam.md`
- Feature surface architecture (cache tiers, polling): `docs/guides/feature-surface-architecture.md`

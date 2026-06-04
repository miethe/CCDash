# Decisions Block — Branch-Aware Planning Intelligence v1 (Phase 1: display-from-existing-data)

> Opus-authored scaffold for `implementation-planner` expansion. Feature scope is the PRD's Phase 1
> ONLY (~12–13 pts). PRD: `docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md`.
> Evidence base: `docs/project_plans/exploration/branch-aware-planning-intelligence/` (brief + 3 spike findings + r01 spike).

## 1. Phase Boundaries

| Phase | Name | Scope | Success criteria | Exit gate |
|-------|------|-------|------------------|-----------|
| 1 | Backend query/DTO exposure | Add `git_branch` to `PlanningAgentSessionCardDTO`; `commitRefs`/`prRefs` onto `FeatureSummaryItem` (from `document_refs`); `activeSessions` onto `PlanningCommandCenterItemDTO`; inverse phase→sessions query in `backend/application/services/agent_queries/planning_sessions.py` (+ `links.py` repo read). NO migrations, NO new write paths (display-only). | All new fields populated in service-layer unit tests against seeded fixtures; transport-neutral pattern respected (agent_queries first) | Unit tests pass; task-completion-validator |
| 2 | Transport + FE contract | Wire fields through `backend/routers/agent.py`; update `types.ts`; extend `services/queries/` planning hooks; add `refetchInterval` to both planning board hooks (S5/S6); cache freshness decision (see Risk R1) | API returns new fields; TS types compile; hooks poll at chosen interval | Contract test + typecheck; validator |
| 3 | Frontend surfaces | S-ACT active-session chips on `CommandCenterFeatureCard` (template: `MultiProjectWorkItemCard:97–123`) w/ transcript links; S1 `git_branch` chip on session cards; S3 commit/PR click-dialog w/ provenance identifiers; S4 per-phase session links in `CommandCenterDetailPanel`; "Open full detail" bridge button to board modal | Each story matches its PRD AC incl. all null/empty/resilience states (Codex-null vs missing-null; worktree empty states) | Component tests; runtime smoke per R-P4 |
| 4 | Verification | AC coverage matrix; seam verification task (see §4); runtime browser smoke over every target_surface; ADR-007 non-applicability confirmation (no new write paths) | `ac-coverage-report.py` clean; smoke evidence recorded | task-completion-validator + karen (end of feature) |
| 5 | Docs finalization | CHANGELOG `[Unreleased]` entry (changelog_required: true); SSE topology disclosure in feature guide worknote; CLAUDE.md pointer if needed | Docs merged | validator |

## 2. Agent Routing

| Phase | Primary | Secondary | Parallel? |
|-------|---------|-----------|-----------|
| 1 | python-backend-engineer | data-layer-expert (query review only) | Tasks within phase parallelizable per DTO |
| 2 | python-backend-engineer | ui-engineer-enhanced (types.ts/hooks) | BE router + FE contract in one batch after P1 |
| 3 | ui-engineer-enhanced | frontend-developer | YES — S-ACT, S1, S3, S4 are independent components; bridge button with S4 |
| 4 | task-completion-validator | karen (feature end) | Sequential |
| 5 | documentation-writer (haiku) | — | Single batch |

## 3. Risk Hotspots

| ID | Risk | Severity | Mitigation |
|----|------|----------|------------|
| R1 | **Server cache vs live updates**: planning endpoints sit behind `@memoized_query` (~600s TTL). `refetchInterval` polling re-reads stale server cache, defeating the "live" promise. | HIGH | Decision: override TTL to ≤30s for the two planning-board endpoints (simplest; no new write path; avoids event-driven eviction work which is Phase 2's cache-key question). Plan MUST carry a seam task asserting end-to-end freshness ≤45s (sync→API→UI) in in-process SQLite topology. |
| R2 | Codex structural null branch (788 sessions, parser hardcodes NULL) | HIGH | Two distinct display ACs already in PRD (AC-NULLBRANCH-1/2); FE must branch on `platform_type`, never infer. |
| R3 | DTO contract breakage for existing consumers of `PlanningAgentSessionCardDTO` | MED | All new fields additive + optional; resilience ACs (R-P2) already in PRD; contract test asserting old consumers unaffected. |
| R4 | "Active session" definition ambiguity for S-ACT chips | MED | Reuse the session-board state classification from `planning_sessions.py` (state grouping already shipped); do NOT invent a new liveness heuristic. |
| R5 | Transcript link targets | LOW | Use existing HashRouter SessionInspector routes; no new route work. |
| R6 | cwd/workingDirectories temptation | LOW | PRD AC-CWD-EXCLUSION prohibits; code-review gate. |

## 4. Seam Integrity (R-P3)

Phases 2–3 have FE+BE owners with overlapping `files_affected` (`types.ts`, `services/queries/`).
- `integration_owner: ui-engineer-enhanced`
- Mandatory seam task (Phase 4): verify each new backend field propagates producer→`routers/agent.py`→`types.ts`→query hook→each target_surface component, including the absent-field fallback path. References every PRD `target_surfaces` entry.

## 5. Estimation Anchors (H5)

- **Anchor**: Planning session board feature (`planning_sessions.py` + `PlanningAgentSessionBoard`) — same shape: agent_queries service + REST wiring + board UI. That feature landed at a comparable scale; this one is smaller per-story but 5 stories wide.
- Bottom-up: P1=4, P2=2, P3=5, P4=1.5, P5=0.5 ⇒ **~13 pts** (within PRD's ~12-pt envelope + H6 plumbing margin). Delta to anchor <30% — no justification needed.

## 6. Dependency Map

P1 → P2 → P3 → P4 → P5 (strict layer order; Phase 3 stories fan out in parallel after P2).
Critical path: P1 DTO exposure → P2 hooks → S4 per-phase links (deepest UI story) → P4 seam task.

## 7. Model Routing

| Phase | Model | Effort |
|-------|-------|--------|
| 1–3 | sonnet | adaptive |
| 4 | sonnet (validator) | adaptive |
| 5 | haiku | adaptive |

## 8. Open Questions for implementation-planner (OQ-*)

- OQ-1: Exact TTL override mechanism for the two planning-board endpoints (per-endpoint `@memoized_query` ttl param vs config flag). Pick whichever the decorator already supports; do not build new infra.
- OQ-2: Whether the inverse phase→sessions query needs pagination guard (cap at N most-recent per phase; recommend cap=20).
- OQ-3: Bridge-button placement in `CommandCenterDetailPanel` header vs footer — defer to existing planning-tokens layout conventions.

## 9. Plan Skeleton Pointer

- Template: `.claude/skills/planning/templates/implementation-plan-template.md`
- Output: `docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v1.md`
- Frontmatter: `prd_ref: docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md`, `changelog_required: true`, `feature_slug: branch-aware-planning-intelligence`, tier 2.
- Constraints to propagate: PRD mandatory ACs (null states, worktree empty state, SSE topology disclosure, cwd exclusion, resilience fallbacks); R-P1..R-P4 plan generator rules; runtime smoke task mandatory (UI phases).

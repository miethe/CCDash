---
type: context
schema_version: 2
doc_type: context
prd: branch-aware-planning-intelligence
feature_slug: branch-aware-planning-intelligence
prd_ref: docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v2.md
title: "Branch-Aware Planning Intelligence v2 — Development Context"
status: in_progress
created: '2026-06-11'
updated: '2026-06-11'
commit_refs: []
pr_refs: []
critical_notes_count: 4
implementation_decisions_count: 4
active_gotchas_count: 0
agent_contributors: []
agents: []
phase_status:
  - { phase: 0, status: not_started, reason: null }
  - { phase: 1, status: not_started, reason: null }
  - { phase: 2, status: not_started, reason: null }
  - { phase: 3, status: not_started, reason: null }
  - { phase: 4, status: not_started, reason: null }
  - { phase: 5, status: not_started, reason: null }
  - { phase: 6, status: not_started, reason: null }
blockers: []
decisions:
  - id: DECISION-1
    question: "Where should BranchWatcherRegistry live and how should it integrate with planning services?"
    decision: "Option A — new file backend/db/branch_watcher.py; direct-call model (no event bus); planning write path calls register()/unregister() directly"
    rationale: "OQ-1 + OQ-2 resolution per decisions-block §7; direct-call model avoids event-bus complexity for N<=5 use case; isolated new file avoids contaminating FileWatcher"
    tradeoffs: "Tight coupling between planning write path and registry; mitigated by ADR-008 call-site constraint and linting comment gate"
    location: "backend/db/branch_watcher.py (new), backend/application/services/agent_queries/planning_command_center.py (call site)"
    phase: 0
  - id: DECISION-2
    question: "How should the startup watcher hydration sequence be ordered relative to the sync job?"
    decision: "Startup coroutine runs AFTER _run_all_projects_sync_job completes (OQ-3 resolution)"
    rationale: "Prevents race condition between per-project sync and watcher registration; sync must complete before watchers are active"
    tradeoffs: "Slightly delayed watcher availability on startup; acceptable given the correctness guarantee"
    location: "backend/runtime/container.py (startup lifecycle), backend/adapters/jobs/runtime_job_adapter.py"
    phase: 2
  - id: DECISION-3
    question: "What happens when a worktree_path is missing at startup hydration?"
    decision: "Log WARNING + skip the row; no unilateral terminal-status mutation (OQ-4 resolution)"
    rationale: "ADR-006 forbids unilateral state mutations outside the owning write path; logging is sufficient for operator awareness"
    tradeoffs: "Orphaned planning_worktree_contexts rows may persist; mitigated by operator guidance in T6-002"
    location: "backend/db/branch_watcher.py (register method)"
    phase: 2
  - id: DECISION-4
    question: "What confidence level should _correlate_branch() assign to branch-signal matches?"
    decision: "uniform confidence='medium'; no confidence='high' assigned (reserved for entity_links); exact-match -> high deferred to OQ-6 post-v2 tuning"
    rationale: "Prevents false-positive promotion to high confidence before FP telemetry data is available; medium is conservative and safe"
    tradeoffs: "Lower precision than possible; OQ-6 tracks promotion path once FP rate measured"
    location: "backend/application/services/agent_queries/session_correlation.py (_correlate_branch)"
    phase: 3
gotchas: []
modified_files: []
notes: >
  Delegation: This repo uses ICA --bare delegation due to CLAUDE.md overflow.
  All implementation tasks must be delegated to subagents (never implemented directly by Opus).
  File paths are passed to subagents, not file contents. See CLAUDE.md §Opus Delegation Principle.
---

# Branch-Aware Planning Intelligence v2 — Development Context

**Status**: In Progress (P0–P6 pending)
**Created**: 2026-06-11
**Last Updated**: 2026-06-11

> **Purpose**: Shared worknotes for all agents working on Branch-Aware Planning Intelligence v2.
> Add observations, decisions, gotchas, and handoff notes here.
> The YAML frontmatter is machine-queryable; the body is for human-readable context.

---

## Feature Summary

Branch-Aware Planning Intelligence v2 closes the multi-worktree infrastructure gap left by
Phase 1 (display-only). It delivers: ADR-007 compliance on `SqliteDocumentRepository.upsert`
and ADR-008 acceptance formalizing the `BranchWatcherRegistry`↔planning-service seam (P0);
DB migration v34 adding `documents.branch` column + two indexes and `branch_filter` cache
isolation on four `@memoized_query` planning endpoints (P1); a new `BranchWatcherRegistry`
class in `backend/db/branch_watcher.py` with container registration, startup hydration
serialized after the sync job, and per-worktree `docs/progress` watching that excludes
sessions dirs (P2); the `_correlate_branch` step 5a medium-confidence session↔feature
correlation in `session_correlation.py` with exclusion set, min-length guard, and Codex
null-branch disclosure (P3); the `PlanningTopBar` DEF-003 branch chip with resilience fallback
(P4); and integration tests, N=3–5 write-amplification profiling, runtime smoke, operator
docs, and plan finalization (P5–P6). Total: **26 pts** across 7 phases (~3 weeks).

---

## Phase Overview (P0–P6)

| Phase | Title | Est. | Wave | Notes |
|-------|-------|-----:|------|-------|
| P0 | Prerequisites & Seam Decision | 4 pts | Wave 1 | karen milestone; ADR-007 + ADR-008 |
| P1 | Data Layer | 4 pts | Wave 2 | Migration v34 + cache param_extractor |
| P2 | BranchWatcherRegistry Infrastructure | 6 pts | Wave 3 (parallel) | Heaviest; karen milestone |
| P3 | S2 Branch-Signal Correlation | 4 pts | Wave 3 (parallel) | H3 floor ≥3 pts honored |
| P4 | Frontend Surface (DEF-003) | 3 pts | Wave 3 (parallel) | Thin; R-P4 smoke deferred to P5 |
| P5 | Verification & Profiling | 3 pts | Wave 4 | N=3–5 write-amplification; karen milestone |
| P6 | Docs & Finalization | 2 pts | Wave 5 | karen feature-end sign-off |

**Critical path**: P0 → P1 → P2 → P5 → P6 (~19 pts). P3 and P4 run concurrently with P2.

---

## Key Architectural Decisions

### 1. BranchWatcherRegistry — Option A (new file, direct-call)

**Decision**: `BranchWatcherRegistry` lives in new file `backend/db/branch_watcher.py`
(not in `file_watcher.py`). Registry model uses direct-call seam — the planning control
plane write path calls `register()`/`unregister()` directly when inserting/updating
`planning_worktree_contexts` rows. No event bus.

**Rationale**: OQ-1 + OQ-2 resolution per decisions-block §7. Simpler for N≤5 use case.
ADR-008 enforces the call-site constraint with a linting comment gate.

### 2. ADR-008 Direct-Call Seam

`BranchWatcherRegistry.register()` is invoked ONLY from the planning control plane write
path on `planning_worktree_contexts` INSERT with `status='running'`. `unregister()` only on
UPDATE to terminal status. A linting comment marks the sole call site:
`# BranchWatcherRegistry call site — ADR-008 §3`.

### 3. DB Migration v34

- `ALTER TABLE documents ADD COLUMN branch TEXT DEFAULT ''` (via `_ensure_column`, idempotent)
- `CREATE INDEX IF NOT EXISTS idx_docs_project_branch ON documents(project_id, branch)`
- `CREATE INDEX IF NOT EXISTS idx_sessions_git_branch_project ON sessions(git_branch, project_id)`
- Mirrored in `postgres_migrations.py` with `IF NOT EXISTS` guards.

### 4. Cache Isolation: `branch_filter` param_extractor Dimension

`branch_filter: str | None = None` added to the `param_extractor` on four planning endpoints.
When `branch_filter=None`, the cache key is **byte-identical** to the Phase 1 key — no cache
regression. `aclear_project_cache(project_id)` evicts all branch-filtered slots.

---

## R-01 Preconditions (OQ Resolutions)

These four open questions from the R-01 brief were resolved in the decisions block §7 and
must be verified at the P0 exit gate:

1. **OQ-1 — Registry model**: Direct-call model selected (no event bus). Planning write path
   calls `register()`/`unregister()` directly. Accepted by ADR-008.

2. **OQ-2 — File location**: `BranchWatcherRegistry` lives in new file
   `backend/db/branch_watcher.py` — NOT in `file_watcher.py`.

3. **OQ-3 — Startup lifecycle**: Startup hydration coroutine runs **after**
   `_run_all_projects_sync_job` completes (prevents registration race).

4. **OQ-4 — Missing path behavior**: Missing `worktree_path` at startup → log `WARNING` +
   skip. No unilateral terminal-status mutation (ADR-006 spirit). Tested in T2-004 and T5-001.

---

## Key Document Links

| Document | Path |
|----------|------|
| PRD v2 | `docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v2.md` |
| Implementation Plan v2 | `docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v2.md` |
| Decisions Block v2 | `.claude/worknotes/branch-aware-planning-intelligence/decisions-block-v2.md` |
| Human Brief | `docs/project_plans/human-briefs/branch-aware-planning-intelligence.md` |
| Charter | `docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md` |
| R-01 Brief | `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/r01-branch-watcher-brief.md` |
| ADR-007 | `docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md` |
| ADR-008 (proposed) | `docs/project_plans/adrs/adr-008-branch-watcher-registry-planning-service-seam.md` |
| Design Spec | `docs/project_plans/design-specs/branch-aware-phase2-multi-branch-watcher.md` |
| Phase 1 Guide | `.claude/worknotes/branch-aware-planning-intelligence/feature-guide.md` |

---

## Delegation Note

> **This repo uses ICA `--bare` delegation due to CLAUDE.md overflow.**
>
> All implementation tasks MUST be delegated to specialized subagents. Opus never writes
> code directly. Subagents receive file paths, not file contents. See CLAUDE.md
> §Opus Delegation Principle and §Agent Delegation for model selection rules.
>
> Default subagent model: **Sonnet 4.6** (except P6 doc tasks which use Haiku 4.5).
> Escalate to Opus only for cross-system architectural reasoning.

---

## Agent Notes

> _Add observations, gotchas, handoff notes, and integration findings below as implementation proceeds._

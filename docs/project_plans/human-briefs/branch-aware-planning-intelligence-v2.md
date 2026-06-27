---
schema_name: ccdash_document
schema_version: 2
doc_type: human_brief
root_kind: project_plans
title: "Branch-Aware Planning Intelligence — Human Brief"
status: draft
created: '2026-06-11'
updated: '2026-06-11'
category: human-briefs
feature_slug: branch-aware-planning-intelligence
feature_family: branch-aware-planning-intelligence
feature_version: v2
audience: [humans]
prd_ref: docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v2.md
intent_ref: null
epic_ref: null
owner: null
contributors: []
priority: high
confidence: 0.87
related_documents:
  - docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md
  - docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v1.md
  - docs/project_plans/design-specs/branch-aware-phase2-multi-branch-watcher.md
  - docs/project_plans/design-specs/command-center-detail-panel-consolidation.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/r01-branch-watcher-brief.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/watcher-arch-findings.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/data-model-findings.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/risk-findings.md
  - docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/ux-value-findings.md
tags: [human-brief, branch-watcher, multi-branch, session-correlation, phase-2]
---

# Branch-Aware Planning Intelligence — Human Brief

> Living document for human orchestrators. Agents: do not load unless explicitly instructed.
> Status: draft | Updated: 2026-06-11 | Covers v1 (completed) and v2 (planning)

---

## 1. Context Pointers

One-line pointers only. Do not restate content.

- **PRD v2**: `docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v2.md`
- **Plan v2**: `docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v2.md`
- **PRD v1 (completed)**: `docs/project_plans/PRDs/enhancements/branch-aware-planning-intelligence-v1.md`
- **Plan v1 (completed)**: `docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v1.md`
- **Design Spec (primary)**: `docs/project_plans/design-specs/branch-aware-phase2-multi-branch-watcher.md`
- **R-01 Feasibility Brief**: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/r01-branch-watcher-brief.md`
- **Charter**: `docs/project_plans/exploration/branch-aware-planning-intelligence/branch-aware-planning-intelligence-charter.md`
- **Decisions Block (architectural authority)**: `.claude/worknotes/branch-aware-planning-intelligence/decisions-block-v2.md`
- **Deferred — CommandCenter consolidation**: `docs/project_plans/design-specs/command-center-detail-panel-consolidation.md`

---

## 2. Estimation Sanity Check

_Migrated from v2 decisions block §4 and plan. Human-authored; not agent-relevant._

**Bottom-up total**: 26 pts / ~3 engineer-weeks
**Top-down anchor (H5)**: `ccdash-planning-reskin-v2` session board (~15–20 pts, 3 phases) introduced
new planning query surfaces + incremental DB migrations. Phase 2 is narrower on UI but wider on
infrastructure (BranchWatcherRegistry) + ADR-007 retrofit debt + correlation logic — justifying the
+6–11 pt delta. Within H5's ±30% tolerance given infra/retrofit additions.

### H3: Algorithmic Service Flag
`_correlate_branch` in `session_correlation.py` is an algorithmic correlation service → ≥3 pts
floor. P3 = 4 pts (floor honored). If correlation gains additional normalization strategies in
implementation, estimate could hit 5 pts; flag but do not pre-inflate.

### H5: External Anchor
`ccdash-planning-reskin-v2` ~15–20 pts. v2 adds:
- BranchWatcherRegistry new infra: +6 pts (no prior art in codebase)
- ADR-007 retrofit debt (mandatory P0): +4 pts (bounded, established pattern)
- S2 correlation (H3 floor): +4 pts
- Cache param_extractor: +2 pts (precedent in existing `@memoized_query` pattern)
- Frontend chip (DEF-003): +3 pts (thin; reads existing data)
- Integration profiling (OQ-5): +3 pts (empirical; repeatable harness)
- Docs (H6 plumbing): +2 pts
Total: 26 pts. Within R-01's 20–27 range.

### H6: Hidden-Plumbing Budget
P6 = 2 pts (~8% of total). Covers: CHANGELOG entry, operator guidance (N≤5 range, OQ-7
`--reload-exclude`, SSE topology), feature guide, deferred-item spec refresh + OQ-6 tuning note,
plan/charter finalization. Standard hidden-plumbing budget.

### 26-pt Phase Breakdown (from decisions block §4)

| Phase | Points | Basis |
|-------|-------:|-------|
| P0: Prerequisites & Seam Decision | 4 | ADR-007 retrofit ~3 (bounded pattern) + ADR-008 authoring ~1 (judgment) |
| P1: Data Layer | 4 | Migration v34 ~2 (O(1) SQLite, 2 indexes, Postgres parity) + cache `param_extractor` on 4 endpoints ~2 |
| P2: BranchWatcherRegistry Infra | 6 | Registry class + container + snapshot + register/unregister + startup serialization + OQ-4 — mostly-new infra |
| P3: S2 Branch-Signal Correlation | 4 | Correlation step + exclusion/normalization + high test density (H3 ≥3 pts floor) |
| P4: Frontend Surface (DEF-003) | 3 | DEF-003 chip ~1 + reconciliation/resilience ~2 |
| P5: Verification & Profiling | 3 | Integration tests ~1.5 + profiling harness + report ~1.5 |
| P6: Docs & Finalization | 2 | H6 hidden-plumbing: CHANGELOG, operator guidance, feature guide, charter/spec updates |
| **Total** | **26** | Within R-01 20–27 range |

### Reconciliation
Bottom-up (26 pts) agrees with top-down anchor delta (~+6–11 pts over 15–20 pt anchor). The
principal uncertainty is P2 (6 pts, `extended` effort) — startup serialization correctness is the
hardest surface. If P2 hits unexpected lifecycle edge cases, allow +1 pt buffer before escalating.

---

## 3. Wave & Orchestration Notes

**Critical path**: P0 → P1 → P2 → P5 → P6 = 19 pts. Every day saved on P2 saves a day overall.

**Parallel opportunities**: After P1 exits, three slices run concurrently:
- P2 (backend infra, 6 pts, extended effort — longest)
- P3 (S2 correlation, 4 pts, self-contained)
- P4 (frontend chip, 3 pts, reads existing data — shortest)

P4 can theoretically ship before P2 or P3 complete. P5 blocks on all three.

**Merge order**: P0 and P1 must be merged (and ADR-008 accepted) before P2 branch is cut.
P3 and P4 can merge independently after P1. P5 and P6 are strictly sequential after P2+P3+P4.

**Cross-feature coupling**: None in flight. `planning_worktree_contexts` table pre-exists.
Phase 1 ACs (AC-NULLBRANCH-1/2, AC-SSE-TOPOLOGY) are confirmed shipped — do not re-verify.

---

## 4. Open Questions Ledger

OQ-1..OQ-7 from decisions block §7. Carry forward until ADR-008 acceptance closes OQ-1/2/3/4.

| ID | Source | Question | Status | Resolved By |
|----|--------|----------|--------|-------------|
| OQ-1 | R-01 §8 | What event mechanism drives `planning_worktree_contexts` INSERT/UPDATE notifications to `BranchWatcherRegistry`? Direct call vs event bus? | **Resolved** — direct-call model per decisions block §7: planning write path calls `register`/`unregister` directly; coupling restricted + formalized in ADR-008 call-site allow-list | ADR-008 (T0-005) |
| OQ-2 | R-01 §8 | Should `BranchWatcherRegistry` live in `file_watcher.py` or a new `branch_watcher.py`? | **Resolved** — new `backend/db/branch_watcher.py` for test isolation + import-graph clarity per decisions block §7 | ADR-008 (T0-005) |
| OQ-3 | R-01 §8 | Startup sync serialization — wired into `_run_all_projects_sync_job` or separate coroutine? | **Resolved** — separate startup coroutine that runs **after** `_run_all_projects_sync_job` completes per decisions block §7 | ADR-008 (T0-005), implemented T2-004 |
| OQ-4 | R-01 §8 | Missing `worktree_path` at startup: log+skip or terminal-status update? | **Resolved** — log `WARNING` and skip; no unilateral planning-state mutation (ADR-006 spirit) per decisions block §7 | ADR-008 (T0-005), implemented T2-004 |
| OQ-5 | R-01 §8 | Actual timings for `sync_changed_files` under N=3–5 simultaneous watcher events? | **Deferred to P5** — profiling harness T5-002 produces empirical data; not a P0–P4 blocker | T5-002 profiling report |
| OQ-6 | design spec | Should exact feature-ID branch slug matches auto-promote to `confidence=high`? | **Deferred** — Phase 2 ships uniform `medium` confidence; post-ship tuning note appended in T6-004 | Post-v2 tuning (T6-004 note) |
| OQ-7 | R-01 §5 | What `--reload-exclude` configuration mitigates uvicorn reload hazard for branch watchers in dev mode? | **Deferred to P6** — operator docs task T6-002 resolves and documents | T6-002 |

---

## 5. Deferred Items Rationale

_Plan owns the triage table. Rationale here._

- **CommandCenterDetailPanel consolidation** (DEF-002): Full replacement with the board modal
  requires the `MultiProjectDetailRail` consolidation debt to be resolved. Phase 1's "Open full
  detail" bridge button is the interim affordance. Promote when design spec reaches `approved`
  maturity and cross-feature coupling is resolved. No Phase 2 engineering required.

- **OQ-6: exact-match high-confidence promotion**: `feat/<slug>` exact match → `confidence=high`
  is architecturally straightforward but the FP rate at exact-match threshold is unvalidated.
  Phase 2 ships `medium` for all branch-signal correlations. Post-ship: measure FP rate with
  telemetry hook; refine exclusion set; promote if FP rate < 2%.

- **Composite PK on `documents`** (Phase 3 scope): Full per-worktree isolation requires
  `(project_id, file_path, branch)` composite PK. Last-writer-wins is accepted Phase 2 limitation.
  Blocked on Phase 3 PRD.

- **cwd/workingDirectories inference**: Stored in `session_forensics_json` blob; not a direct DB
  column. Any Phase 2+ use requires `_ensure_column` migration first (charter disclosure constraint a).

---

## 6. Risk Narrative

_From decisions block §3. Orchestrator-facing rationale._

- **ADR-007 non-compliance on `SqliteDocumentRepository.upsert`** (H): This is pre-existing
  technical debt that Phase 2 would inherit and entrench. The P0 gate is non-negotiable —
  retrofit must ship in the same PR as the `documents.branch` write path. Watch for the
  test runner catching any missed bare `self.db.commit()` calls.

- **ADR-008 not accepted before P2 starts** (H): The planning service → `BranchWatcherRegistry`
  cross-layer coupling is load-bearing architecture. If ADR-008 is not accepted before P2 is
  cut, the registry implementation has no bounded contract to implement against. Hard gate at P0.

- **Startup-sync race** (M→H): Registering watchers mid-sync can double-process or miss events.
  OQ-3 resolution (separate coroutine after `_run_all_projects_sync_job`) is the mitigation.
  Watch T2-004 closely — this is the correctness surface in the heaviest phase.

- **Codex null-branch silent degradation** (H): `parsers/platforms/codex/parser.py:1244`
  hardcodes `git_branch=NULL`. If `_correlate_branch` doesn't early-exit, correlation silently
  produces empty evidence without disclosure. T3-004 tests this explicitly. Do not let this
  slip past P3.

- **Write amplification at N≥10** (M): Only 0.60 confidence in the current estimate; unmeasured.
  Enforcing N≤5 operational range and running T5-002 profiling is the mitigation. Do not allow
  Phase 3 to begin N=10+ scale-out without the profiling report as gate input.

- **Branch correlation false positives** (M): The <5% FP rate estimate is subjective and
  unvalidated. The exclusion set + 8-char minimum guard in T3-001 are the primary defenses.
  Post-ship: add telemetry hook to measure actual FP rate before any exclusion-set tuning.

- **uvicorn `--reload` drops watchers** (M): Dev-mode hazard — every code change in dev mode
  drops all watcher registrations. Accepted limitation (same as primary `FileWatcher`).
  T6-002 documents `--reload-exclude` guidance. Production unaffected.

---

## 7. What to Watch For

_Gotchas and trap-doors during execution._

- **ADR-008 authoring quality**: T0-005 uses `extended` effort for a reason. If the ADR
  draft is shallow (missing OQ-1/2/3/4 resolutions, no call-site constraint, no lifecycle
  binding), it will not pass the P0 exit gate. `backend-architect` review is required.

- **P2 `asyncio.Lock` correctness**: The registry uses `asyncio.Lock` on all mutating ops.
  Watch for deadlock if a coroutine awaits inside the lock. T2-001 and T2-002 need careful
  review of lock scope.

- **P3 feature_index shape**: `_correlate_branch` receives a `feature_index: dict`. Verify
  this index shape is consistent with how `_correlate_command_tokens` uses it — do not
  assume without reading `correlate_session()` call site.

- **P4 reconciliation trap**: T4-001 must confirm what actually shipped in Phase 1 v1.
  The v1 plan `files_affected` list includes `PlanningTopBar.tsx` — DEF-003 chip may be
  partially implemented. Do not re-author shipped UI.

- **Profiling harness realism** (T5-002): The harness uses `asyncio.gather` to simulate
  simultaneous events. Confirm the harness actually exercises the `sync_changed_files`
  lock contention path, not just parallel no-op coroutines.

---

## 8. Expected Success Behaviors

_Human-verifiable post-ship outcomes. From PRD §12 ACs._

- [ ] **Multi-worktree doc sync**: Operator edits a PRD on a registered worktree path on
      a non-active-checkout branch. The document appears in CCDash planning queries within
      ≤5s of the file save (under N≤3 concurrent watcher events).

- [ ] **Branch-signal correlation coverage**: A session with `git_branch='feat/my-feature'`
      (≥8 normalized chars, not in exclusion set) shows `medium` confidence branch-signal
      evidence linking it to the `my-feature` feature item on the planning session board.

- [ ] **Codex session null-branch non-regression**: Codex sessions (`git_branch=NULL`) appear
      in planning board queries with `branch_filter=None`. No correlation evidence assigned.
      No error in UI. Consistent with Phase 1 behavior.

- [ ] **Branch chip on PlanningTopBar**: For a feature with an active registered worktree,
      `PlanningTopBar` shows a secondary metadata chip with the branch name (e.g., `feat/my-feature`).
      For a feature with no registered worktree, chip is absent — no error, no blank page.

- [ ] **Cache backward-compat**: Existing Phase 1 callers of the four `@memoized_query`
      planning endpoints see no change in behavior or response time. `branch_filter=None`
      (default) cache key is byte-identical to Phase 1 key.

- [ ] **ADR-007 compliance**: Running the `test_documents_adr007.py` suite produces zero
      failures. Lock-injection test passes. Direct-count assertion passes on SQLite + Postgres.

- [ ] **N≤5 profiling envelope**: Profiling report in
      `.claude/worknotes/branch-aware-planning-intelligence/wamp-profiling-report-v2.md`
      shows N=3–5 `sync_changed_files` p95 latency within acceptable bounds
      (no >50ms degradation vs. N=1 baseline). If flagged, Phase 3 is blocked.

- [ ] **Operator guidance present**: `docs/guides/` (or equivalent) contains N≤5 operational
      range note, uvicorn `--reload-exclude` guidance, and SSE in-process-only constraint note.

---

## 9. Running Log

_Append-only. Short notes during execution._

- **2026-06-04**: Phase 1 planning completed. R-01 BranchWatcherRegistry feasibility brief
  finalized (verdict: conditional, confidence 0.88). R-01 preconditions recorded. Design spec
  authored (`branch-aware-phase2-multi-branch-watcher.md`, maturity: shaping). Phase 1 (v1)
  ~13 pts, display-from-existing-data; all Phase 1 ACs confirmed.

- **2026-06-11**: Decisions block v2 authored by Opus. 7-phase plan (P0–P6, 26 pts) expanded
  from decisions block. Human brief updated for v2. Phase 1 ACs (AC-NULLBRANCH-1/2,
  AC-SSE-TOPOLOGY) confirmed shipped — not re-verified in Phase 2.

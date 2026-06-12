# Opus Decisions Block — Branch-Aware Planning Intelligence v2 (Phase 2)

> Architectural judgment scaffold authored by Opus. `implementation-planner` expands this into the
> full plan at `docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v2.md`.
> Source of truth for design detail: `docs/project_plans/design-specs/branch-aware-phase2-multi-branch-watcher.md`
> and the R-01 feasibility brief. Do NOT restate that detail — reference it.

- **feature_slug**: branch-aware-planning-intelligence
- **feature_version**: v2
- **tier**: 2 (estimate 26 pts; SPIKE prerequisite satisfied by R-01 + tech/risk/ux legs — Tier 3 SPIKE gate cleared, so Tier 2 artifact set applies)
- **risk_level**: medium
- **execution model**: phase-by-phase orchestration
- **reviewer gates**: `task-completion-validator` per phase; `karen` at the P0/P2 milestone and at feature end (size-driven hardening — 26 pts warrants a mid-feature karen pass)
- **delegation transport**: ICA `--bare` bash (this repo's CLAUDE.md overflows the standard Agent tool); see worknotes.

---

## 1. Phase Boundaries

Strict layer order. Each phase exits only when its gate is green and the per-phase validator passes.

| Phase | Name | Scope (what changes) | Exit gate |
|-------|------|----------------------|-----------|
| **P0** | Prerequisites & Seam Decision | ADR-007 retrofit of `SqliteDocumentRepository.upsert` (+ direct-count + lock-injection tests + Postgres parity); draft & **accept** proposed ADR-008 (BranchWatcherRegistry↔planning-service seam) resolving OQ-1/OQ-2/OQ-3 | ADR-008 status `accepted`; retrofit merged, ADR-007 tests green on both backends; OQ-1/2/3 resolved in ADR text. **karen milestone.** |
| **P1** | Data Layer | Migration v34: `documents.branch TEXT DEFAULT ''`, `idx_docs_project_branch`, `idx_sessions_git_branch_project`; `branch_filter` `param_extractor` on the 4 `@memoized_query` planning endpoints; Postgres parity | Migration applies clean on SQLite + Postgres; `branch_filter=None` cache key byte-identical to current (backward-compat test); branch-isolation cache test passes |
| **P2** | BranchWatcherRegistry Infra | New `BranchWatcherRegistry` (Option A, keyed `(project_id, worktree_path)`, `asyncio.Lock`); container registration; `branch_watchers` snapshot key; register/unregister from planning write path; startup load of active `planning_worktree_contexts` rows; startup-sync serialization; `stop_all` on shutdown; OQ-4 missing-path handling | Register/unregister verified; startup serialization race-free; existing `_watcher_registry_snapshot()` contract intact; shutdown clean. **karen milestone.** |
| **P3** | S2 Branch-Signal Correlation | `_correlate_branch` step 5a in `session_correlation.py`: exclusion set, prefix normalization, ≥8-char guard, **medium** confidence, Codex null-branch early-exit | Correlation unit tests (positive slug match, exclusion-set reject, short-branch reject, Codex `git_branch=None` → `[]`); no regression in existing correlation steps |
| **P4** | Frontend Surface | DEF-003 `PlanningTopBar` active-branch chip (reads existing `worktree.branch`; no backend change) + any verified-unshipped UX gap; resilience for empty/missing `branch` | Runtime smoke on planning surfaces (chip renders w/ and w/o branch); resilience AC met |
| **P5** | Verification & Profiling | Multi-watcher integration tests (N=2–3); **write-amplification profiling at N=3–5** (OQ-5) to validate the performance envelope before any future N=10 scale-out | Integration green; profiling report recorded; N≤5 envelope confirmed or flagged. **karen milestone.** |
| **P6** | Docs & Finalization | Operator guidance (N≤5 range, `--reload-exclude` OQ-7, worktree registration UX); CHANGELOG `[Unreleased]` (changelog_required); feature-guide; promote design spec `maturity: promoted`; update charter Notes | Docs complete; CHANGELOG entry present; charter/design-spec updated. **karen feature-end.** |

Scope guard: P4 is intentionally thin. Per design spec §1, the Phase-1 coverage audit pulled the chip/dialog/sessions-tab UX into v1. v2 frontend = DEF-003 chip + only genuinely-unshipped gaps. Do not re-author shipped Phase-1 UI.

---

## 2. Agent Routing

| Phase | Primary | Secondary / Reviewer | Notes |
|-------|---------|----------------------|-------|
| P0 (retrofit) | `data-layer-expert` | `task-completion-validator` | ADR-007 pattern is established (`retry_on_locked`); mechanical + test-heavy |
| P0 (ADR-008) | `backend-architect` (via `pm:create-adr`) | Opus sign-off on OQ-1 decision | Cross-layer seam — needs architectural judgment, not just drafting |
| P1 | `data-layer-expert` | `task-completion-validator` | Migration + cache `param_extractor`; both-backend parity |
| P2 | `backend-architect` | `python-backend-engineer`, `task-completion-validator` | Lifecycle + startup serialization is the hardest correctness surface |
| P3 | `python-backend-engineer` | `task-completion-validator` | Self-contained correlation logic; high test density |
| P4 | `ui-engineer-enhanced` | `task-completion-validator` | Small; reconcile against Phase-1 shipped state first |
| P5 | `python-backend-engineer` (profiling harness) | `karen` | Profiling is empirical; needs a repeatable harness |
| P6 | `documentation-writer` | `changelog-generator` | haiku-class doc work |

**Parallelization**: P3 and P4 can run concurrently after P1 (P3 needs the sessions index from P1; P4 needs nothing from P2/P3). P0→P1→P2 is strictly serial. P5 needs P2 + P3 complete.

---

## 3. Risk Hotspots

| Risk | Severity | Rationale | Mitigation (must appear as plan tasks/ACs) |
|------|----------|-----------|---------------------------------------------|
| ADR-007 violation on `upsert` compounds when branch write path lands | **H** | Adding a write path to a non-compliant repo entrenches the debt | Retrofit is P0 entry criterion, not deferred; lock-injection test proves retry |
| Cross-layer seam (planning service → registry) without an accepted ADR | **H** | Hard import coupling decided ad-hoc becomes load-bearing | ADR-008 **accepted** before P2 starts; call-site restricted to planning write path + code-review gate |
| Startup-sync ↔ watcher-registration race | **M→H** | Registering watchers mid-sync can double-process or miss events | OQ-3: register only after `_run_all_projects_sync_job` completes; serialize explicitly |
| Codex null-branch silently degrades correlation/UI | **H** | `parser.py:1244` hardcodes NULL; silent hide = dishonest UI | `_correlate_branch` early-exits on None; explicit disclosure AC (not hidden) |
| Write amplification at N≥10 watchers | **M** | Only 0.60 confidence; unmeasured | Enforce N≤5 operational range; P5 profiling gate before any scale-out |
| Document identity collision (last-writer-wins across worktrees) | **M** | Same path on two branches shares `documents.id` | Accepted v2 limitation; `branch` disambiguates queries only; composite-PK isolation is Phase 3 |
| Branch-correlation false positives | **M** | <5% subjective, unvalidated | Exclusion set + ≥8-char guard; make exclusion set configurable; telemetry hook post-ship |
| uvicorn `--reload` drops watcher registrations | **M** | Dev-mode hazard, compounded by N watchers | Accept as dev limitation; operator `--reload-exclude` guidance (OQ-7) in P6 |
| Snapshot API contract break | **L** | Composite keys would break `dict[project_id, dict]` consumers | Parallel `branch_watchers` key, not composite keys |

---

## 4. Estimation Anchors

| Phase | Points | Basis |
|-------|--------|-------|
| P0 | 4 | ADR-007 retrofit ~3 (bounded, established pattern) + ADR-008 authoring ~1 (judgment, not volume) |
| P1 | 4 | Migration v34 ~2 (O(1) SQLite, 2 indexes, Postgres parity) + cache `param_extractor` on 4 endpoints ~2 |
| P2 | 6 | Registry class + container + snapshot + register/unregister + startup serialization + OQ-4 — the heaviest, mostly-new infra |
| P3 | 4 | Correlation step + exclusion/normalization + high test density (H3 algorithmic-service flag: "correlation" → ≥3 pts floor) |
| P4 | 3 | DEF-003 chip ~1 + reconciliation/resilience ~2 |
| P5 | 3 | Integration tests ~1.5 + profiling harness + report ~1.5 |
| P6 | 2 | H6 hidden-plumbing/docs budget (CHANGELOG, operator guidance, feature-guide, charter/spec updates) |
| **Total** | **26** | Within R-01's 20–27 range |

**H5 anchor**: `ccdash-planning-reskin-v2` planning session board (~15–20 pts, 3 phases) introduced new planning query surfaces + incremental DB migrations. v2 is comparable but trades net-new UI for net-new infrastructure (BranchWatcherRegistry) + ADR-007 retrofit debt + correlation logic — justifying the +6–11 pt delta over that anchor (within H5's 30% tolerance given the infra/retrofit additions).
**H3 flag**: `_correlate_branch` is a correlation service → ≥3 pts floor honored (P3 = 4).
**H6 plumbing**: P6 = 2 pts (~8% of total) for DTO/migration/OpenAPI/CHANGELOG/operator-doc tail.

---

## 5. Dependency Map

```
P0 (ADR-007 retrofit + ADR-008 accept)
  └─> P1 (migration v34 + cache branch_filter)
        ├─> P2 (BranchWatcherRegistry infra)   ──┐
        ├─> P3 (S2 branch correlation)          ──┤   (P3 needs sessions index from P1, not P2)
        └─> P4 (PlanningTopBar chip)            ──┤   (FE needs nothing from P2/P3)
                                                  └─> P5 (integration + N=3–5 profiling)  [needs P2 + P3]
                                                        └─> P6 (docs + finalization)
```

- **Critical path**: P0 → P1 → P2 → P5 → P6 (≈ 19 pts on the longest chain).
- **Parallelizable after P1**: {P2, P3, P4} — three independent slices; P4 can ship earliest (lowest risk).
- **Hard serial**: P0 → P1 → P2 (each consumes the prior's schema/seam contract).

---

## 6. Model Routing (per phase per agent)

Claude models: effort `adaptive` default, `extended` where flagged. ICA `--bare` transport; Opus/Sonnet use `[1m]` ids.

| Phase | Agent | Model | Effort | Why |
|-------|-------|-------|--------|-----|
| P0 retrofit | data-layer-expert | sonnet | adaptive | Established `retry_on_locked` pattern |
| P0 ADR-008 | backend-architect | sonnet | **extended** | Cross-layer seam reasoning; OQ-1 decision |
| P1 | data-layer-expert | sonnet | adaptive | Migration + cache, both-backend parity |
| P2 | backend-architect | sonnet | **extended** | Lifecycle + startup serialization correctness |
| P3 | python-backend-engineer | sonnet | adaptive | Self-contained correlation |
| P4 | ui-engineer-enhanced | sonnet | adaptive | Small FE chip |
| P5 | python-backend-engineer | sonnet | adaptive | Profiling harness + integration |
| P6 | documentation-writer | haiku | adaptive | Doc/CHANGELOG/operator-guidance |
| All reviews | task-completion-validator / karen | sonnet / opus | adaptive | Per-phase + milestone gates |

---

## 7. Open Questions for Expansion (implementation-planner)

Carry these into the plan with Opus's recommended resolutions; flag any the planner must escalate.

- **OQ-1 (event mechanism)** — *Opus recommendation*: no event bus exists; use a **direct call** from the planning control-plane write path to `BranchWatcherRegistry.register/unregister`, with the coupling formalized + restricted in ADR-008 (call-site allow-list + code-review gate). Record in ADR-008; do not invent a new bus for v2.
- **OQ-2 (module placement)** — *Opus recommendation*: new `backend/db/branch_watcher.py` (test isolation + import-graph clarity) rather than overloading `file_watcher.py`.
- **OQ-3 (startup serialization)** — *Opus recommendation*: trigger registry hydration in a startup coroutine that runs **after** `_run_all_projects_sync_job` completes; do not interleave with per-project sync.
- **OQ-4 (missing worktree path at startup)** — *Opus recommendation*: log a warning and **skip**; only transition the `planning_worktree_contexts` row to a terminal status when deletion is confirmed by the planning layer (registry must not mutate planning state unilaterally — ADR-006 spirit).
- **OQ-5 (write amplification N=3–5)** — empirical; P5 profiling task owns this. Not a P0–P4 blocker.
- **OQ-6 (exact-match → high confidence)** — **defer** to a post-v2 tuning note; v2 ships medium confidence only.
- **OQ-7 (`--reload-exclude` guidance)** — P6 operator-docs task.

---

## 8. Plan Skeleton Pointer

- **Template**: `.claude/skills/planning/templates/implementation-plan-template.md`
- **Output**: `docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v2.md`
- **Frontmatter must set**: `doc_type: implementation_plan`, `feature_slug: branch-aware-planning-intelligence`, `feature_version: v2`, `prd_ref:` (the v2 PRD), `spike_ref:` (R-01 brief), `charter_ref:` (charter), `adr_refs:` [006, 007, proposed-008], `deferred_items_spec_refs:` [command-center-detail-panel-consolidation], `findings_doc_ref: null`, `changelog_required: true`, `plan_structure: unified`, `progress_init: auto`, `priority: high`, `risk_level: medium`, `created: '2026-06-11'`.
- **wave_plan**: 7 phases (P0–P6); set phase-level `model`/`effort` defaults per §6; per-task overrides allowed.
- **AC schema**: use the structured-AC format (target_surfaces / propagation_contract / resilience / verified_by) for the cross-layer + resilience ACs (R-P1..R-P4 plan-generator rules). The `documents.branch` field triggers R-P2 (FE-handles-missing AC). P2/P4 are multi-owner-touching → declare `integration_owner` + a seam task (R-P3). P4 is `*.tsx`-touching → runtime-smoke task (R-P4).
- **DOC-006 deferred-items task**: author/refresh the command-center-detail-panel-consolidation design spec note + OQ-6 tuning note in P6.

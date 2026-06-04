---
schema_version: 2
doc_type: exploration_charter
title: "Branch-Aware Planning Intelligence — Exploration Charter"
status: concluded
created: 2026-06-04
feature_slug: branch-aware-planning-intelligence
timebox_days: 3
hypothesis: "We believe branch-aware, live-updating planning intelligence (branch/commit
  provenance and session linkage on planning board items) is worth building because
  operators currently lose visibility into work happening on non-checked-out branches
  and worktrees, and planning items cannot be traced to the sessions or commits that
  produced them."
deal_killer: "If session logs and planning artifacts contain no reliable branch/commit
  identifiers (e.g., gitBranch in session JSONL, commit_refs/pr_refs in frontmatter)
  from which branch↔item↔session linkage can be derived without invasive per-branch
  git checkout scanning, abandon."
investigation_legs:
- id: tech
  question: What does CCDash actually do today for branch tracking, 
    planning-board live updates, branch/commit field population, and 
    session↔item linkage — and what are the integration points and rough cost to
    deliver the proposed capabilities?
  assigned_to: research-technical-spike
- id: risk
  question: What are the top risks and blast radius of multi-branch/worktree 
    scanning, new linkage schema, and live board updates across the sync engine,
    file watcher, DB, and query cache? Confirm or refute the deal-killer.
  assigned_to: backend-architect
- id: ux-value
  question: 'Do operators experience real pain from missing branch/session visibility,
    and what is the best UX shape: branch/commit dialogs on cards, per-phase session
    links in the details pane, active-session chips, and board-modal vs planning side-pane
    consolidation?'
  assigned_to: ux-researcher
verdict_criteria:
  go:
  - tech and risk legs report confidence >= 0.7
  - 'Deal-killer condition not triggered: branch/commit provenance is derivable from
    existing session/artifact data'
  - A bounded phased path exists (display-from-existing-data first, deeper 
    scanning later)
  no_go:
  - Deal-killer condition triggered
  - tech leg reports infeasibility with confidence >= 0.8
  conditional:
  - Open question(s) remain resolvable by a specific named subsequent 
    investigation (e.g., dedicated spike on watcher multi-branch scanning or 
    live-update transport)
verdict: conditional
verdict_rationale: 'Phase 1 (display-from-existing-data, ~6-9 pts) meets all go gates:
  tech and risk legs at 0.85 confidence, deal-killer not triggered (gitBranch is a
  persisted DB column; commitRefs/prRefs live in document_refs; no git scanning needed).
  Conditional because: (1) S3 branch/commit dialog is gated on a gitBranch coverage
  audit (coverage confidence 0.50; Codex sessions hardcode NULL); (2) Phase 2 multi-branch
  doc scanning partially triggers the deal-killer (working-tree-bound docs) and is
  gated on a dedicated BranchWatcherRegistry watcher spike (R-01); (3) four disclosure
  constraints (cwd in JSON blob, operator-gated worktree contexts, in-process-only
  SSE under SQLite, Codex structural null-branch) must carry into the Phase 1 PRD
  as ACs. Approved by operator 2026-06-04 with directive to run the coverage audit
  immediately.'
output_artifacts:
- path: docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/r01-branch-watcher/r01-branch-watcher-brief.md
  doc_type: report
  report_category: feasibility
  spike_slug: r01-branch-watcher
  confidence: 0.88
  status: finalized
  verdict: conditional
updated: '2026-06-04'
---

# Branch-Aware Planning Intelligence — Exploration Charter

## Hypothesis Context

The operator reports (unverified) that: (1) CCDash only tracks the currently checked-out branch per project; (2) planning command-center board items do not update live and should reflect progress from any branch; (3) `branch`/`commit` fields on planning items are never populated; (4) there is no way to link sessions to planning items (per-phase links in the details pane, active-session chips on cards, transcript links); (5) the board page already shows many of these details but not cross-project, raising a consolidation question (reuse the board modal from the planning page vs. keep the side pane). All five claims must be verified against runtime truth before tiering.

---

## Investigation Legs

### Leg: tech — Current-State Verification & Feasibility

**Question**: see frontmatter.
**Assigned to**: `research-technical-spike`
**Expected output**: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/tech-findings.md`

- Does `backend/parsers/sessions.py` capture `gitBranch`/cwd per session? Do progress/PRD frontmatter `commit_refs`/`pr_refs` reach the DB and API?
- Is `backend/db/sync_engine.py` + `file_watcher.py` scoped to one checkout path per project? How are worktrees handled?
- Planning board data contract: do branch/commit/session fields exist in `types.ts`, `backend/models.py`, planning query services (`planning.py`, `planning_sessions.py`)?
- What linkage already exists in `backend/document_linking.py` and `db/repositories/links.py` (session↔feature↔task↔doc)?
- Live updates: polling cadence in `AppRuntimeContext`/TanStack Query for planning surfaces; what "live" gap actually exists?
- Board page (`ProjectBoard`) vs planning page modal/side-pane components: what exists, what's shared?
- Rough story-point range with H5 anchor (e.g., planning session board, document linking).

### Leg: risk — Blast Radius & Deal-Killer Assessment

**Question**: see frontmatter.
**Assigned to**: `backend-architect`
**Expected output**: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/risk-findings.md`

- Multi-branch/worktree scan cost; watcher binding complexity; sync-engine perf and DB write amplification (ADR-007 constraints).
- Schema/migration impact for branch/commit/session linkage; query-cache and polling load for live updates.
- Confirm/refute deal-killer; surface any additional deal-killers.

### Leg: ux-value — Operator Value & UX Shape

**Question**: see frontmatter.
**Assigned to**: `ux-researcher`
**Expected output**: `docs/project_plans/exploration/branch-aware-planning-intelligence/spikes/ux-value-findings.md`

- Counterfactual: how does the operator answer "what's happening on branch X?" today?
- Card affordances: branch/commit click-dialog with link-provenance identifiers; active-session chips; per-phase session links in details pane; transcript links.
- Consolidation trade-offs: board-page modal reused on planning page vs. existing side pane; cross-project board mode implications.

---

## Verdict Criteria Narrative

**Go** if: tech + risk legs ≥0.7 confidence, branch/commit/session provenance is derivable from existing parsed data (session JSONL fields, frontmatter `commit_refs`), and a phased path exists that ships display-of-existing-data before any multi-branch scanning.
**No-go** if: the deal-killer holds — no reliable identifiers exist and linkage would require per-branch checkout scanning or invasive git plumbing.
**Conditional** if: core display/linkage is feasible but live-update transport or multi-branch watcher design needs its own named spike before commitment.

---

## Out of Scope

- Any implementation work (this is pre-commitment exploration)
- Remote/GitHub API integration (PR status, remote branch enumeration)
- Non-git VCS support
- Rewriting the sync engine or watcher architecture

---

## Citations / Prior Art

- `.claude/worknotes/ccdash-planning-reskin-v2-interaction-performance-addendum/feature-guide.md` (planning modal-first navigation)
- `docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md`, `adr-007-db-write-failure-surfacing-standard.md`
- `docs/guides/feature-surface-architecture.md` (cache tiers, polling)

---

## Notes

<!-- Append timestamped entries as legs complete. Format: YYYY-MM-DD: [note]. -->
- 2026-06-04: Verdict recorded (conditional, 0.85) with operator sign-off. gitBranch coverage audit PASSED (99.1% on feature-linked sessions) — S3 ungated into Phase 1. R-01 watcher spike delegated via spike workflow; results land under spikes/r01-branch-watcher/.
- 2026-06-04: R-01 spike concluded (conditional, 0.87) with operator sign-off. Phase 2 feasible (20-27 pts) gated on: ADR-007 retrofit of SqliteDocumentRepository.upsert (Phase 0 task), drafting proposed ADR-008 (BranchWatcherRegistry<->planning-service seam), write-amplification profiling before N=10+. Phase 1 PRD+plan authored and approved; plan at docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v1.md.

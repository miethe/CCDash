---
type: context
schema_version: 2
doc_type: context
prd: "ccdash-planning-reskin-v2"
feature_slug: "ccdash-planning-reskin-v2"
title: "CCDash Planning Reskin v2 - Development Context"
status: "active"
created: 2026-04-20
updated: 2026-04-20
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md
commit_refs: []
pr_refs: []

critical_notes_count: 0
implementation_decisions_count: 0
active_gotchas_count: 0
agent_contributors: []
agents: []

phase_status:
  - { phase: 1, status: "not_started" }
  - { phase: 2, status: "not_started" }
  - { phase: 3, status: "not_started" }
  - { phase: 4, status: "not_started" }
  - { phase: 5, status: "not_started" }
  - { phase: 6, status: "not_started" }
  - { phase: 7, status: "not_started" }
  - { phase: 8, status: "not_started" }
  - { phase: 9, status: "not_started" }
  - { phase: 10, status: "not_started" }

blockers: []
decisions: []
integrations: []
gotchas: []
modified_files: []
---

# CCDash Planning Reskin v2 — Development Context

**Status**: Active Development
**Created**: 2026-04-20
**Last Updated**: 2026-04-20

> **Purpose**: Shared worknotes file for all agents working on this PRD. Add brief observations, decisions, gotchas, and implementation notes that future agents should know.

---

## Quick Reference

**Agent Notes**: 0 notes from 0 agents
**Critical Items**: 0 items requiring attention
**Last Contribution**: — (not yet started)

---

## Feature Overview

CCDash Planning Control Plane v1 (completed) delivered a functional planning surface. This wave authorizes a pixel-faithful **reskin + enhancements** to match the Claude Design handoff ("Planning Deck"). The v2 reskin introduces:

1. **Design tokenization** — OKLCH token system in `planning-tokens.css` and Tailwind config; base UI primitive components in `components/Planning/primitives/`.
2. **Shell + home reskin** — new typography (Geist/JetBrains Mono/Fraunces), hero header with corpus stats, 6-tile metrics strip, 8-artifact composition chip row.
3. **Enhanced surfaces** — triage inbox (filterable tabs: All/Blocked/Mismatches/Stale/Ready-to-promote), live agent roster (two-up layout), planning graph totals lane (effort + tokens + model-identity bar).
4. **Feature detail drawer enhancements** — lineage strip, SPIKEs section with exec buttons, OQ inline resolution editor, model legend, dependency DAG SVG, per-batch/task exec buttons, exec toast.
5. **Backend extension** — `PATCH /api/planning/features/:id/open-questions/:oq_id` endpoint for OQ write-back.
6. **A11y + perf + testing** — WCAG 2.1 AA, keyboard nav, ARIA roles, performance budgets, Vitest coverage.
7. **Documentation** — CHANGELOG, README, design specs for DEFER-01..10.

**Key outcome**: `/planning` route reaches visual parity with design handoff (≥90% per surface). All 11 planning surfaces implemented and tested.

---

## Key Surfaces (11 Total)

| # | Surface | Phase | Component |
|---|---------|-------|-----------|
| 1 | App rail (active Planning state) | Phase 1 | Existing app rail — reskin |
| 2 | Top bar (breadcrumb, live-agent pill, search, CTA) | Phase 1 | New top bar component |
| 3 | Planning Deck hero header (serif h1, corpus stats, spark) | Phase 2 | PlanningHomePage reskin |
| 4 | Metrics strip (6 tiles: total/active/blocked/stale/mismatches/completed) | Phase 2 | MetricTile primitive |
| 5 | Artifact composition chips (8 types: SPEC/SPIKE/PRD/PLAN/PHASE/CTX/TRK/REP) | Phase 2 | ArtifactChip primitive |
| 6 | Triage inbox (filterable tabs, severity bars, action buttons) | Phase 3 | TriagePanel (new) |
| 7 | Live agent roster (state dots, two-up layout) | Phase 3 | AgentRoster (new) |
| 8 | Planning graph (lane headers, DocChips, PhaseStackInline, TotalsCell, SVG edges, legend) | Phase 4 | PlanningGraphPanel reskin |
| 9 | Feature detail drawer (header, lineage, SPIKEs, OQ editor, batches, DAG) | Phases 5-6 | PlanningNodeDetail reskin |
| 10 | Dependency DAG SVG view | Phase 6 | DependencyDAG (new) |
| 11 | Exec toast | Phase 6 | ExecToast primitive |

---

## Deferred Items

| ID | Category | Description |
|----|----------|-------------|
| DEFER-01 | infra | SSE streaming for live agent roster updates — roster polls until streaming infra stable |
| DEFER-02 | feature | Actual SPIKE/phase/batch/task execution dispatch — exec buttons toast-only for v2 |
| DEFER-03 | backend | OQ frontmatter write-through to filesystem — OQ endpoint returns 200 with in-memory state only |
| DEFER-04 | ops | Bundled font assets for offline deployment — CDN default for v2 |
| DEFER-05 | data | Session-linked actual token counts (vs client-side estimated) — requires session→task linkage work |
| DEFER-06 | feature | "New spec" creation flow UI — top bar CTA stub shows toast for v2 |
| DEFER-07 | engineering | @miethe/ui extraction of v2 Planning primitives — evaluate after 2-week stability window post-ship |
| DEFER-08 | feature | Collab/comment threads on planning artifacts — requires auth/tenancy work |
| DEFER-09 | design | Light-mode variant of planning token system — no light-mode design exists |
| DEFER-10 | perf | Planning graph virtualization for >200 features — current scale does not require it |

Design specs for all 10 deferred items will be authored in Phase 10 (DOC-004) at `docs/project_plans/design-specs/`.

---

## Open Questions (with Adopted Resolutions)

| ID | Question | Resolution |
|----|----------|------------|
| OQ-01 | Does PlanningQueryService already return `spikes[]` and `openQuestions[]`? | Audit in Phase 0 (T0-004); add if missing — in scope |
| OQ-02 | Is client-side token estimation acceptable for v2 telemetry tiles? | Yes — client-side estimation acceptable; actual session-linked tokens deferred (DEFER-05) |
| OQ-03 | Is Google Fonts CDN acceptable for local-first deployment? | Default to CDN for v2; bundled fonts deferred (DEFER-04) |
| OQ-04 | Should "New spec" CTA open a creation flow or show a stub toast? | Stub with toast for v2; full creation flow deferred (DEFER-06) |

---

## Cross-References

| Document | Path |
|----------|------|
| PRD | `docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md` |
| Implementation Plan | `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md` |
| Design Bundle README | `docs/project_plans/designs/ccdash-planning/README.md` |
| Planning Deck (primary visual truth) | `docs/project_plans/designs/ccdash-planning/project/Planning Deck.html` |
| Control Plane v1 Plan (completed baseline) | `docs/project_plans/implementation_plans/enhancements/ccdash-planning-control-plane-v1.md` |
| Primitives source (handoff) | `docs/project_plans/designs/ccdash-planning/project/app/primitives.jsx` |
| Graph source (handoff) | `docs/project_plans/designs/ccdash-planning/project/app/graph.jsx` |
| Feature detail source (handoff) | `docs/project_plans/designs/ccdash-planning/project/app/feature_detail.jsx` |
| Triage source (handoff) | `docs/project_plans/designs/ccdash-planning/project/app/triage.jsx` |

---

## Implementation Decisions

> Key architectural and technical decisions made during development — populate as agents make decisions.

---

## Gotchas & Observations

> Things that tripped us up or patterns discovered during implementation — populate as agents encounter issues.

---

## Integration Notes

> How components interact and connect — populate as agents implement integrations.

### Frontend OQ Editor → Backend PATCH Endpoint

**From**: `PlanningNodeDetail.tsx` (OQ inline resolution editor, T6-002)
**To**: `PATCH /api/planning/features/:id/open-questions/:oq_id` (T7-002)
**Method**: `services/planning.ts` — typed API client call
**Notes**: T6-002 can be developed against a mocked endpoint; actual integration tested in T9-003. OQ state is in-memory only (DEFER-03 — no filesystem write-through).

---

## Performance Notes

> Performance considerations discovered during implementation — populate as agents work.

---

## Agent Handoff Notes

> Quick context for agents picking up work — populate as phases hand off.

---

## References

- Phase progress files: `.claude/progress/ccdash-planning-reskin-v2/phase-{0..10}-progress.md`
- Implementation plan: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md`
- PRD: `docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md`
- Design handoff: `docs/project_plans/designs/ccdash-planning/project/Planning Deck.html`

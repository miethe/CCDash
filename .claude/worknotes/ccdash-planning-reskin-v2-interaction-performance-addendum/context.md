---
type: context
schema_version: 2
doc_type: context
prd: "ccdash-planning-reskin-v2-interaction-performance-addendum"
title: "CCDash Planning Reskin v2 Interaction and Performance Addendum - Development Context"
status: "active"
created: 2026-04-21
updated: 2026-04-21

critical_notes_count: 2
implementation_decisions_count: 0
active_gotchas_count: 2
agent_contributors: []

agents: []
---

# CCDash Planning Reskin v2 Interaction and Performance Addendum - Development Context

**Status**: Active Development
**Created**: 2026-04-21
**Last Updated**: 2026-04-21

> Shared worknotes for all agents working on this addendum. Add brief observations, decisions, gotchas, and implementation notes that future agents should know.

---

## Scope Summary

This addendum delivers the interaction and performance layer on top of the in-flight planning reskin (phases 1-10 of `ccdash-planning-reskin-v2`). The reskin established visual direction; this addendum tightens the planning page into a true control-plane surface.

**Four problem areas addressed:**

1. **Modal-first navigation** — Feature/artifact clicks must resolve inside `/planning` first. No primary click should bounce the operator to `/board`, `/sessions`, or `/artifacts`.
2. **Active-first cached loading** — Summary renders first; graph/detail loads lazily. Browser cache with stale-while-revalidate semantics. Backend cache fingerprint must cover all planning input tables (including documents).
3. **Metric wiring** — Placeholder tiles must become real data (`statusCounts`, `ctxPerPhase`, `tokenTelemetry`) or explicit unavailable states. Status buckets must be mutually exclusive and clickable.
4. **In-context interactions** — Tracker/intake rows open `PlanningQuickViewPanel`. Roster rows open an agent detail modal. No row click should navigate away.

**New surfaces introduced:**

| Surface | Phase | Component |
|---------|-------|-----------|
| Route-local feature modal | 11 | Extracted/wrapped from `ProjectBoard` |
| `PlanningQuickViewPanel` | 14 | New right-side quick-view panel |
| Agent detail modal | 15 | New modal from `PlanningAgentRosterPanel` rows |
| Metric tile filters | 13 | Extended `PlanningMetricsStrip` |
| Density controls | 13 | Extended `PlanningRouteLayout` CSS variables |

---

## Document References

| Document | Path |
|----------|------|
| Parent PRD | `docs/project_plans/PRDs/enhancements/ccdash-planning-reskin-v2.md` |
| Parent plan | `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md` |
| Addendum plan | `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md` |
| Progress files | `.claude/progress/ccdash-planning-reskin-v2-interaction-performance-addendum/phase-{11..17}-progress.md` |
| Findings (lazy-create) | `.claude/findings/ccdash-planning-reskin-v2-interaction-performance-addendum-findings.md` |

---

## Critical Notes

### Sequencing Risk: Parent Phases 8-10 Must Merge First

Phase 11 (modal orchestration) touches `PlanningHomePage.tsx` and `PlanningRouteLayout.tsx`. These are the same files targeted by parent plan phases 8-10, which were open at addendum planning time. **Do not start Phase 11 until parent phases 8-10 are merged.** Divergent edits on these files will produce difficult merge conflicts.

Check parent plan phase status with:
```bash
python .claude/skills/artifact-tracking/scripts/manage-plan-status.py \
  --read docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2.md
```

### Cache Fingerprint Gap (Current Known Issue)

The existing backend planning cache fingerprint covers sessions and features only. Document-only changes (no feature/session modification) do not currently trigger cache invalidation. P12-003 must fix this by adding documents, feature_phases, entity_links, and planning writeback tables to all planning query fingerprints. This is a known staleness risk in production until P12-003 lands.

---

## Gotchas and Active Observations

### PlanningMetricsStrip Overlapping Counts

Current `PlanningMetricsStrip` exposes `total`, `active`, `blocked`, `stale`, `mismatches`, and `completed` as peer metrics. These are not mutually exclusive — `blocked` features are also counted in `active`. The Phase 13 rework must introduce two visually distinct zones: (1) mutually exclusive status buckets, (2) health signal overlays. Do not attempt to make health signals sum to total.

### Density Variables Have Limited Reach Today

`PlanningRouteLayout` sets CSS variables for density but many planning row components hard-code their padding, gaps, and heights. Phase 13 (P13-004) must audit all planning row components and replace hard-coded values with token references. Start from a grep of `px-` and `py-` in `components/Planning/` to find candidates.

---

## Integration Notes

### Phase 11 → Phases 14 and 15

Both Phase 14 (`PlanningQuickViewPanel`) and Phase 15 (roster detail modal) depend on Phase 11's route-local modal state infrastructure. The same route-state mechanism that opens the feature modal (P11-003) should be reusable for opening the quick-view panel and agent detail modal — avoid creating three separate state systems.

### Phase 12 Backend Split → Phase 13 Frontend Tiles

The summary/facets split (P12-001) defines the payload shape that Phase 13's metric tiles consume. The `statusCounts`, `ctxPerPhase`, and `tokenTelemetry` fields added in P13-001 must be agreed between backend and frontend engineers before P13-002 begins. Coordinate early on the `source` field enum values (`"backend"` vs `"unavailable"`) to avoid UI-side branching surprises.

---

## References

- Progress files: `.claude/progress/ccdash-planning-reskin-v2-interaction-performance-addendum/`
- Addendum plan: `docs/project_plans/implementation_plans/enhancements/ccdash-planning-reskin-v2-interaction-performance-addendum-v1.md`
- Parent reskin progress: `.claude/progress/ccdash-planning-reskin-v2/`
- Findings (lazy-create on first finding): `.claude/findings/ccdash-planning-reskin-v2-interaction-performance-addendum-findings.md`

---

## Status Updates

<!-- Agents: append timestamped notes here as work progresses -->

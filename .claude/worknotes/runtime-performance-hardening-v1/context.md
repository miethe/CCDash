---
type: context
schema_version: 2
doc_type: context
prd: "runtime-performance-hardening-v1"
feature_slug: "runtime-performance-hardening"
title: "CCDash Runtime Performance Hardening v1 - Development Context"
status: active
created: 2026-04-20
updated: 2026-04-20
prd_ref: "docs/project_plans/PRDs/infrastructure/runtime-performance-hardening-v1.md"
plan_ref: "docs/project_plans/implementation_plans/infrastructure/runtime-performance-hardening-v1.md"
commit_refs: []
pr_refs: []
critical_notes_count: 0
implementation_decisions_count: 0
active_gotchas_count: 0
agent_contributors: []
agents: []
phase_status:
  - phase: 1
    status: not_started
  - phase: 2
    status: not_started
  - phase: 3
    status: not_started
  - phase: 4
    status: not_started
  - phase: 5
    status: not_started
  - phase: 6
    status: not_started
blockers: []
decisions: []
gotchas: []
modified_files: []
---

# CCDash Runtime Performance Hardening v1 - Development Context

**Status**: Active Development
**Created**: 2026-04-20
**Last Updated**: 2026-04-20

> **Purpose**: Shared worknotes for all agents working on runtime-performance-hardening-v1. Add observations, decisions, gotchas, and handoff notes as implementation progresses.

---

## Quick Reference

**PRD**: `docs/project_plans/PRDs/infrastructure/runtime-performance-hardening-v1.md`
**Implementation Plan**: `docs/project_plans/implementation_plans/infrastructure/runtime-performance-hardening-v1.md`
**Design Spec**: `docs/project_plans/design-specs/runtime-performance-hardening-v1.md`
**Feature Slug**: `runtime-performance-hardening`
**Agent Notes**: 0 notes from 0 agents
**Critical Items**: 0 items requiring attention

---

## PRD Overview

This feature addresses three operator-visible performance and reliability problems:

1. **Frontend tab memory growth** (2GB+ observed) — transcript/log arrays grow unboundedly during sustained operation
2. **Redundant startup link rebuilds** — two full rebuilds per boot with old defaults
3. **Cached query cold windows + N+1 workflow fetches** — 60s TTL creates cold windows against a 300s warmer; per-workflow detail loop produces N queries per diagnostics call

**Success metrics:**
- Tab memory flat within ±50MB over 60-min idle with worker running
- ≤1 full rebuild per boot
- ≥95% cache hit rate in steady-state
- Single-batch workflow detail query per diagnostics call

---

## Key References

| Document | Path |
|----------|------|
| PRD | `docs/project_plans/PRDs/infrastructure/runtime-performance-hardening-v1.md` |
| Implementation Plan | `docs/project_plans/implementation_plans/infrastructure/runtime-performance-hardening-v1.md` |
| Design Spec | `docs/project_plans/design-specs/runtime-performance-hardening-v1.md` |
| Meta-Plan | `docs/project_plans/meta_plans/performance-and-reliability-v1.md` |
| DB Caching Layer Plan | `docs/project_plans/implementation_plans/db-caching-layer-v1.md` |
| Query Cache Tuning Guide | `docs/guides/query-cache-tuning-guide.md` |
| Operator Setup Guide | `docs/guides/operator-setup-user-guide.md` |

**Progress files:**
- Phase 1: `.claude/progress/runtime-performance-hardening-v1/phase-1-progress.md`
- Phase 2: `.claude/progress/runtime-performance-hardening-v1/phase-2-progress.md`
- Phase 3: `.claude/progress/runtime-performance-hardening-v1/phase-3-progress.md`
- Phase 4: `.claude/progress/runtime-performance-hardening-v1/phase-4-progress.md`
- Phase 5: `.claude/progress/runtime-performance-hardening-v1/phase-5-progress.md`
- Phase 6: `.claude/progress/runtime-performance-hardening-v1/phase-6-progress.md`

---

## Deferred Items (OQ-1, OQ-3)

| Item | Category | Trigger | Target Spec Path |
|------|----------|---------|-----------------|
| OQ-1 | research | Operator feedback after v1 soak | `docs/project_plans/design-specs/transcript-fetch-on-demand-v1.md` |
| OQ-3 | enhancement | Cache hit rate < 90% post-release | `docs/project_plans/design-specs/agent-query-cache-lru-v1.md` |

OQ-2 (EntityLinksRepository.rebuild_for_entities audit) is a contingent implementation task, not a post-delivery deferred item — handled by BE-201/BE-203 in Phase 2.

---

## Implementation Decisions

_(Empty — fill in as decisions are made during implementation)_

---

## Gotchas & Observations

_(Empty — fill in as implementation progresses)_

---

## Integration Notes

_(Empty — fill in as cross-component integration points are discovered)_

---

## Agent Handoff Notes

_(Empty — fill in as phases complete)_

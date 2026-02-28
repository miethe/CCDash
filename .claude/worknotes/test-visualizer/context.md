---
type: context
prd: "test-visualizer"
title: "Test Visualizer - Development Context"
status: "active"
created: "2026-02-28"
updated: "2026-02-28"

critical_notes_count: 0
implementation_decisions_count: 0
active_gotchas_count: 0
agent_contributors: []

agents: []
---

# Test Visualizer - Development Context

**Status**: Active Development
**Created**: 2026-02-28
**Last Updated**: 2026-02-28

> **Purpose**: Shared worknotes for all AI agents working on the Test Visualizer feature. Add observations, decisions, gotchas, and implementation notes here as work progresses.

---

## Quick Reference

**Agent Notes**: 0 notes from 0 agents
**Critical Items**: 0 items requiring attention
**Last Contribution**: None

---

## Feature Overview

The Test Visualizer adds test result tracking, domain health rollups, and integrity signal detection to CCDash. It is a full-stack feature spanning 8 phases:

| Phase | Title | Owner | Status |
|-------|-------|-------|--------|
| 1 | Data Layer | data-layer-expert, python-backend-engineer | planning |
| 2 | Ingestion Pipeline | python-backend-engineer, backend-architect | planning |
| 3 | API Layer | python-backend-engineer, backend-architect | planning |
| 4 | UI/UX Design | ui-designer, gemini-orchestrator, ux-researcher, ui-engineer | planning |
| 5 | Core UI Components | ui-engineer-enhanced, frontend-developer | planning |
| 6 | Page & Tab Integration | ui-engineer-enhanced, frontend-developer | planning |
| 7 | Domain Mapping & Integrity | python-backend-engineer, backend-architect | planning |
| 8 | Testing & Polish | python-backend-engineer, frontend-developer | planning |

**Phase 4 runs in parallel with Phases 1-3.** All other phases are sequential.

---

## Key Architecture Points

- **SCHEMA_VERSION**: Increments from 12 to 13 in Phase 1.
- **Feature flag**: `CCDASH_TEST_VISUALIZER_ENABLED` gates all tables, endpoints, and UI.
- **Secondary flags**: `CCDASH_INTEGRITY_SIGNALS_ENABLED`, `CCDASH_SEMANTIC_MAPPING_ENABLED`.
- **Ingest surface**: `POST /api/tests/ingest` — primary write path. File watcher is optional convenience.
- **test_id stability**: SHA-256 hash of `"{path}::{name}::{framework}"` — must be consistent across runs.
- **Idempotency**: Same `run_id` second ingest returns `status: 'skipped'`. Partial re-ingest fills missing `(run_id, test_id)` pairs only.
- **Router prefix**: `/api/tests` — all endpoints share this prefix.
- **Frontend entry points**: 4 locations — Testing Page (/tests), Execution Page tab, Session Page tab, Feature Modal tab.
- **Shared component**: `TestStatusView` is the core composite used in all 4 entry points.

---

## Implementation Decisions

_No decisions recorded yet._

---

## Gotchas & Observations

_No observations recorded yet._

---

## Integration Notes

_No integration notes recorded yet._

---

## Performance Notes

_No performance notes recorded yet._

---

## Agent Handoff Notes

_No handoffs recorded yet._

---

## References

**Related Files**:
- PRD: `/docs/project_plans/PRDs/features/test-visualizer-v1.md`
- Implementation Plan: `/docs/project_plans/implementation_plans/features/test-visualizer-v1.md`
- Design Spec: `/docs/project_plans/designs/test-visualizer.md`
- Phase 1 Progress: `.claude/progress/test-visualizer/phase-1-progress.md`
- Phase 2 Progress: `.claude/progress/test-visualizer/phase-2-progress.md`
- Phase 3 Progress: `.claude/progress/test-visualizer/phase-3-progress.md`
- Phase 4 Progress: `.claude/progress/test-visualizer/phase-4-progress.md`
- Phase 5 Progress: `.claude/progress/test-visualizer/phase-5-progress.md`
- Phase 6 Progress: `.claude/progress/test-visualizer/phase-6-progress.md`
- Phase 7 Progress: `.claude/progress/test-visualizer/phase-7-progress.md`
- Phase 8 Progress: `.claude/progress/test-visualizer/phase-8-progress.md`

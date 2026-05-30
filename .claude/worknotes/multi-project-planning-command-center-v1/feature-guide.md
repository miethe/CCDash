---
doc_type: feature_guide
feature_slug: multi-project-planning-command-center-v1
prd_ref: docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/multi-project-planning-command-center-v1.md
spike_ref: docs/project_plans/spikes/multi-project-planning-command-center-v1.md
adr_refs: []
created: 2026-05-30
---

# Multi-Project Planning Command Center V1 — Feature Guide

## Summary

Delivered a unified portfolio planning view across multiple CCDash projects. Operators can now toggle between single-project and multi-project (portfolio) modes within the Planning Command Center, see active sessions consolidated from all registered projects on a unified Kanban board with flexible grouping (by state, project, feature, phase, agent, or model), toggle projects on/off in a filter rail with stale-data indicators, customize project colors and display metadata via `ProjectDisplayConfig` in `projects.json`, and open cross-project session details without switching the active project.

## Feature Flags

| Environment Variable | Type | Default | Scope |
|----------------------|------|---------|-------|
| `CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED` | Boolean (env) | False | Backend (`backend/config.py:89`) — gates API endpoints and service layer. |
| `VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED` | Boolean (env) | false | Frontend (`constants.ts`) — gates Portfolio/Current Project toggle and multi-project UI. Consumed at Vite build time. |

Both flags must be enabled for the feature to function.

## API Endpoints

Both endpoints are feature-flagged and return `404` if either flag is disabled:

- **`GET /api/agent/planning/multi-project/command-center`** — Aggregated command-center data across projects (counts, filters, state summary).
- **`GET /api/agent/planning/multi-project/session-board`** — Consolidated active-session board with sessions from all projects, filterable and groupable by state/project/feature/phase/agent/model, paginated.

Both endpoints support partial-failure responses with per-project warning messages (status: 'partial') and per-project staleness signals.

## Validation Status

| Component | Coverage | Status |
|-----------|----------|--------|
| **Backend (pytest)** | 106 multi-project named suites + 57 planning regression suites | 163 tests pass |
| **Frontend (Vitest)** | 102 tests across 9 Planning suites | 102 tests pass |
| **TypeScript (tsc)** | Full codebase type check | 0 errors |
| **Build** | Production bundle | Succeeds |

### Test Suites Included

**Backend:**
- `test_multi_project_command_center.py` — Core aggregation, filtering, grouping, pagination.
- `test_multi_project_session_board.py` — Board rendering, state column logic.
- `test_multi_project_staleness.py` — Staleness detection and per-project error resilience.
- `test_multi_project_display_config.py` — ProjectDisplayConfig fallback colors and custom metadata.
- Plus 57 regression tests ensuring Planning v1 single-project experience remains intact.

**Frontend:**
- `components/__tests__/MultiProjectCommandCenter.test.tsx` — Mode toggle, project filter rail, grouping.
- `components/__tests__/MultiProjectSessionBoard.test.tsx` — Card rendering, project badges, state columns.
- `components/__tests__/ProjectFilterRail.test.tsx` — Project filtering, staleness indicators, label overrides.
- Plus 9 Planning-suite smoke tests covering single + multi-project workflows.

## Rollback & Fallback

**Disabling either flag fully reverts to single-project v1 experience WITHOUT a code revert:**

1. Disable backend flag: `CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=false` (or unset; default is False).
2. Disable frontend flag: `VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=false` (or unset; default is false) and rebuild.

The UI immediately shows no Portfolio toggle; the API returns 404. No database migration or schema change required; all data is ephemeral (aggregated in memory per request).

## Operator Guidance

See **`docs/guides/multi-project-command-center-guide.md`** for:
- Enabling both flags
- Configuring project colors and groups via `ProjectDisplayConfig`
- Understanding stale-data semantics and freshness indicators
- Using the active-session board and grouping options
- Opening cross-project details without switching the active project
- Performance tuning for >250 sessions or >10 projects
- Troubleshooting common issues

## Rollout Strategy

See **`docs/guides/multi-project-command-center-rollout.md`** for:
- Staged rollout approach (alpha → beta → general availability)
- Default-off safety for the release branch
- Per-flag disable strategy and feature-safe fallback
- Fallback procedures if issues are encountered during staged rollout

## Related Documentation

- **PRD:** `docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md`
- **Implementation Plan:** `docs/project_plans/implementation_plans/enhancements/multi-project-planning-command-center-v1.md`
- **SPIKE (Design & Validation):** `docs/project_plans/spikes/multi-project-planning-command-center-v1.md`
- **Operator Guide:** `docs/guides/multi-project-command-center-guide.md`
- **Rollout Guide:** `docs/guides/multi-project-command-center-rollout.md`

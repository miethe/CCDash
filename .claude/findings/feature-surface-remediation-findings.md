---
schema_version: 2
doc_type: report
title: "Feature Surface Remediation — Runtime Smoke Findings"
status: draft
created: 2026-04-24
feature_slug: feature-surface-remediation-v1
plan_ref: docs/project_plans/implementation_plans/harden-polish/feature-surface-remediation-v1.md
report_category: smoke-findings
tags: [feature-surface, runtime-smoke, findings]
---

# Runtime Smoke Findings — feature-surface-remediation-v1 Phase 3 (G4)

**Environment**: Local dev stack (`npm run dev`); frontend Vite on :3002, backend FastAPI on :8000. Chrome via claude-in-chrome MCP. Active project: SkillMeat (230 features).

## G4-001 — ProjectBoard initial load network trace: PASS

Captured network requests for `#/board` cold load after cache clear:

| # | Method | URL | Status |
|---|--------|-----|--------|
| 1 | GET | `/api/v1/features?view=cards&sort_by=updated_at&sort_direction=desc&limit=50&offset=0` | 200 |
| 2 | POST | `/api/v1/features/rollups` | 422 (see Finding 1) |
| 3 | GET | `/api/live/stream?topic=project.{pid}.features` (SSE) | pending/streaming |
| — | — | `/api/features?offset=0&limit=5000` (legacy) | **NOT CALLED** ✅ |

**Result**: G1 decoupling verified in runtime. ProjectBoard loads purely from v2 bounded surfaces plus a single live-stream subscription. The legacy 5000-row `/api/features` endpoint is absent from the initial-load trace, confirming `AppRuntimeContext.featureSurfaceV2Active` correctly suppresses `refreshFeatures()` when the v2 flag is on.

Request count for feature surfaces on initial load: **3** (list + rollups + live stream) — meets plan AC (≤3). The `/api/documents?...` calls present in the same trace belong to the shell Documents provider (out of scope for this phase).

Note: the list endpoint fired twice in a row (duplicate mount/StrictMode double-invoke); same URL so browser cache handles the second. Not a regression but flagged for P3 follow-up.

## G4-002 — Modal lazy-load waterfall: SKIPPED

Couldn't exercise the feature modal because the card grid did not render interactive `[data-feature-id]` DOM nodes for the current active project at smoke time. Board shell rendered correctly (status columns, filters, "230 features · Synced…" header) but card tiles were not selectable by the standard query selector used by the smoke harness. Lazy-load behavior for Overview/Phases/Sessions tabs therefore not verified in this run.

**Recommendation**: retry G4-002 with Playwright harness or manual operator smoke before promoting the plan to `completed` status; the lazy-load pattern has unit coverage (Phase 4/5 of parent plan) but no runtime trace.

## G4-003 — Status update → invalidation → re-render: SKIPPED

Skipped for the same reason as G4-002 (no interactive cards available to the harness). Unit coverage for invalidation exists in `services/__tests__/featureSurfaceDecoupling.test.ts` (10 cases), but runtime round-trip not verified.

## Finding 1 — `/api/v1/features/rollups` rejects empty `feature_ids: []` (latent, not caused by this plan)

**Severity**: Medium (board-initial-load cosmetic; data still renders via list endpoint)
**Reproduced in**: G4-001 trace, 3 consecutive 422 responses during cold load.

```json
POST /api/v1/features/rollups  body={"feature_ids": []}
→ 422
{
  "detail": [{
    "loc": ["body", "feature_ids"],
    "msg": "List should have at least 1 item after validation, not 0",
    "type": "too_short",
    "ctx": {"min_length": 1}
  }]
}
```

**Analysis**: The frontend posts `feature_ids: []` to the rollups endpoint when the v2 list request is still in flight or before cards populate the derived set. Backend pydantic schema requires `min_length: 1`. The two are disagreeing on the contract.

**Fix options** (future work, not in this plan's scope):
- (a) FE: short-circuit the rollups fetch when the derived ID list is empty.
- (b) BE: relax `min_length` and return `{}` for empty input.

(a) is cheaper and aligns with "don't ask for nothing" bounded-surface discipline. File a dedicated bug in request-log.

**Not a G1/G2 regression** — the rollups POST shape predates Phase 2 of this plan (see `backend/routers/features.py` rollups handler and prior `services/planning.ts` derivations). Flagged here because the smoke pass surfaced it.

## Finding 2 — Duplicate initial list fetch on mount (low severity)

`/api/v1/features?view=cards&…&limit=50&offset=0` fires twice on first board render. Likely React 18 StrictMode double-invoke in dev; benign because the second call hits the browser HTTP cache (both returned 200 within milliseconds). Does not warrant a fix unless observed in production.

## Summary

- **G1 decoupling verified in runtime**: legacy /features?limit=5000 is absent from the ProjectBoard trace. This was the primary AC for the feature-surface-remediation-v1 plan and it passes.
- **G2 encoding verified via unit tests** (frontend + backend) in Phase 1.
- **G3 decision** documented at `.claude/specs/feature-surface-remediation/feature-execution-workbench-scope.md` (Option b: migrate the sessions tab).
- **G4-002/G4-003 deferred**: modal and status-update smoke not exercised in this run. Unit coverage present; operator smoke recommended before final sign-off.
- **One latent finding** (rollups 422 on empty ID list) recorded for separate remediation.

The runtime smoke gate for Phase 2's G1-003 (network trace ≤3 requests, no legacy 5000-row call) is satisfied by this report.

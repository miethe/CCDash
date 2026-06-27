---
name: project_ee_phase5_wave4
description: EE P5 Wave 4 — CommandPalette (P5-009) + NewSpecModal (P5-010) + createSpec helper
metadata:
  type: project
---

Wave 4 (P5-009/P5-010) implemented for the planning shell top bar.

**Files created:**
- `services/specs.ts` — `createSpec(req)` POST /api/agent/planning/specs. Throws `CreateSpecError` on non-ok responses. Fail-soft: returns `{ id, path, status }`.
- `components/Planning/CommandPalette.tsx` — ⌘K palette. Features: `listFeatureCards` (GET /api/v1/features?view=cards&q=), docs: `apiRequestJson('/api/documents?q=...')`. Debounced 220ms. Groups: Features / Documents. Keyboard nav (↑/↓/Enter/Esc). Navigates features via `planningFeatureDetailHref`, docs via `/docs?doc=<id>`.
- `components/Planning/NewSpecModal.tsx` — Form: title (required) + docType select (default 'design-spec'). Calls `createSpec`. On success: toast + close. On error: inline error, modal stays open.

**Files modified:**
- `components/Planning/PlanningTopBar.tsx` — wires `paletteOpen`/`newSpecOpen` state; `handleSearch` opens palette (replaces pushToast stub); `handleNewSpec` opens modal (replaces pushToast stub). `activeProject.id` passed to NewSpecModal.

**Key patterns:**
- `listFeatureCards` from `services/featureSurface.ts` accepts `{ q, pageSize }` — use this for feature search.
- `PlanDocument` has `docType` (not `type`) and `filePath` (not `file_path`).
- `useData()` exposes `activeProject` which has the project id.
- Build gate: `npm run build` clean (✓ 9s). Typecheck: 0 new errors in our files.

**Why:** Pre-existing `planningHomePage` vitest failures (QueryClient not set) are unrelated — confirmed pre-existing per project_ee_phase5_fds memory.

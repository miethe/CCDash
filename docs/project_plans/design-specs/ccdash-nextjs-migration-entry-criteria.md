---
schema_version: 2
doc_type: design_spec
title: "CCDash Next.js / SSR Migration — Entry Criteria"
status: draft
maturity: shaping
created: '2026-05-29'
updated: '2026-05-29'
feature_slug: ccdash-frontend-data-layer-refactor
category: refactors
prd_ref: docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
tags:
  - design-spec
  - nextjs
  - ssr
  - migration
  - entry-criteria
  - epic-d
related_documents:
  - docs/project_plans/implementation_plans/refactors/ccdash-nextjs-migration-v1.md
  - .claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-priorart.md
problem_statement: >
  CCDash is a HashRouter SPA with module-scope browser-global accesses that are
  incompatible with server-side rendering. This document defines the mandatory
  entry criteria that must all be true before Epic D (Next.js / SSR migration)
  execution is permitted to begin.
open_questions: []
explored_alternatives: []
---

# CCDash Next.js / SSR Migration — Entry Criteria

**Document Role**: Gating artifact for Epic D of the CCDash Frontend Data Layer
Refactor. This design spec defines the conditions that must ALL be satisfied before
any implementation work on the Next.js / SSR migration begins. Epic D has no
standalone PRD yet; a dedicated sub-plan (`ccdash-nextjs-migration-v1.md`) must
be authored and approved as part of these entry criteria.

**Authored**: P7 / DOC-006 of `ccdash-frontend-data-layer-refactor-v1`

---

## 1. AC-D1 Entry Criteria (verbatim from PRD §11 Epic D)

The following criteria are reproduced verbatim from PRD §11, Epic D, AC-D1
(`docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md`):

> **AC-D1: Entry criteria defined and documented**
> Entry criteria that must ALL be true before Epic D execution begins:
> 1. Epics A, B, and C are shipped and runtime-smoke-clean for a minimum of 14
>    calendar days.
> 2. `window.location.hash` module-scope reads in `AppRuntimeContext.tsx:43` are
>    refactored to use a safe browser-check guard (`typeof window !== 'undefined'`).
> 3. HashRouter is replaced with `BrowserRouter` (or removed) across all ~30
>    affected files — verified by source grep asserting no `HashRouter` import.
> 4. A dedicated sub-plan (`ccdash-nextjs-migration-v1.md`) is authored and
>    approved.
> 5. Feature flag `CCDASH_NEXTJS_ENABLED` is defined in backend health and tested
>    via canary deploy.

> *verified_by: This AC is a documentation gate, not a runtime test. The
> implementation plan for Epic D references this AC as its entry check.*

---

## 2. SSR Blockers — Analysis and Verified File:Line Citations

Three categories of SSR-hostile code were identified in the inventory
(`inventory-priorart.md §4`). Each is documented below with verified file:line
citations as of 2026-05-29.

### Blocker 1: HashRouter across the application

**Inventory claim**: `HashRouter` from `react-router-dom` across ~30 files
(`App.tsx:2,65,105`) is SSR-hostile because `HashRouter` relies on
`window.location.hash` internally and cannot be rendered in a Node.js server
context.

**Verified citations (as of 2026-05-29)**:

| File | Line(s) | Content |
|------|---------|---------|
| `App.tsx` | 2 | `import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';` |
| `App.tsx` | 92 | `<HashRouter>` (opening tag) |
| `App.tsx` | 132 | `</HashRouter>` (closing tag) |
| `components/Workflows/WorkflowRegistryPage.tsx` | 338 | Comment reference only — no import or usage |

**Citation drift noted**: The inventory cited `App.tsx:2,65,105`. Verified actual
lines are `App.tsx:2,92,132`. Line 65 is a comment about lazy devtools; line 105
is a route `<Route>` entry — neither is a `HashRouter` reference. The line numbers
have drifted from the inventory snapshot.

**File count drift noted**: The inventory stated "~30 files." In the current
worktree only `App.tsx` contains an active `HashRouter` import and usage.
`WorkflowRegistryPage.tsx:338` contains only a prose comment. The ~30-file
estimate likely reflects an earlier branch or pre-migration state. The actual
remediation scope is `App.tsx` (the single file containing `<HashRouter>`). Source
grep to verify: `grep -rn "HashRouter" --include="*.tsx" --include="*.ts"`.

**Remediation required**: Replace `HashRouter` in `App.tsx` with `BrowserRouter`
(or adopt Next.js App Router). All route path strings using hash-based navigation
(`/#/...`) must be converted to path-based navigation (`/...`). Verify no
`HashRouter` imports remain via source grep before Epic D proceeds.

---

### Blocker 2: Module-scope `window.location.hash` read in AppRuntimeContext.tsx

**Inventory claim**: `contexts/AppRuntimeContext.tsx:43` reads
`window.location.hash` at module scope, which causes a `ReferenceError` in SSR
(Node.js) where `window` is not defined.

**Verified citations (as of 2026-05-29)**:

Grep result for `window.location` in `contexts/AppRuntimeContext.tsx`: **no
matches found**.

**Citation drift noted**: The current `AppRuntimeContext.tsx` (97 lines) does not
contain any `window.location.hash` reference. The file appears to have been
substantially refactored during Phase 4 (T4-001/002/006 per the file header
comment) and no longer exhibits the module-scope `window` access. The current
file uses `sessionStorage` (inside try/catch) and `isMemoryGuardEnabled()` — both
are safe patterns.

**Status of this blocker**: The specific `window.location.hash` read at line 43
has already been resolved in this worktree. However, the PRD AC-D1 criterion 2
text is preserved verbatim as the entry criterion, since the broader requirement
(ensure no module-scope browser-global reads remain in any context file) must be
verified across the full codebase before SSR migration. A comprehensive audit of
all context files is required at Epic D entry.

**Remediation required**: Verify via source grep that no context or service file
reads `window`, `document`, or `location` at module scope (outside of
`typeof window !== 'undefined'` guards). Current known-safe patterns:
- `ModelColorsContext.tsx:44,59` — guards with `typeof window === 'undefined'`
- `ThemeContext.tsx:21-47` — guards with `typeof window === 'undefined'`
- `AuthSessionContext.tsx:192-193` — uses `window.location.assign` inside a
  callback, guarded by `typeof window !== 'undefined'` check on line 192 (SSR-safe)

---

### Blocker 3: `window.location.assign` in AuthSessionContext.tsx

**Inventory assessment**: `AuthSessionContext.tsx:192-193` uses
`window.location.assign`. This is explicitly noted as **SSR-safe** in the
inventory.

**Verified citation (as of 2026-05-29)**:

| File | Line | Content |
|------|------|---------|
| `contexts/AuthSessionContext.tsx` | 192 | `if (options.redirect !== false && typeof window !== 'undefined') {` |
| `contexts/AuthSessionContext.tsx` | 193 | `window.location.assign(response.authorizationUrl);` |

**Citation accuracy**: Lines 192-193 are correct. The `window.location.assign`
call is inside a callback (not module scope) and is guarded by
`typeof window !== 'undefined'`. This pattern is SSR-safe and does not need to be
changed before Epic D begins.

---

## 3. Preconditions for Epic D Execution

The following preconditions must all be confirmed before the `ccdash-nextjs-migration-v1.md`
implementation plan is activated for execution:

### Precondition 1: Epics A, B, and C smoke-clean for 14 calendar days

Epics A, B, and C of `ccdash-frontend-data-layer-refactor-v1` must all be:
- Shipped to the target environment
- Passing runtime smoke tests across all target surfaces (Dashboard, SessionInspector,
  PlanCatalog, ProjectBoard, Planning, FeatureModal, Analytics)
- Free of P0/P1 incidents for a minimum of **14 consecutive calendar days**

This window is required to establish confidence that the TQ migration is stable
before adding the additional complexity of Next.js / SSR rendering.

**Gate**: Record the smoke-clean start date. Epic D cannot begin until 14 days
have elapsed from that date.

### Precondition 2: `ccdash-nextjs-migration-v1.md` sub-plan authored and approved

The stub implementation plan at
`docs/project_plans/implementation_plans/refactors/ccdash-nextjs-migration-v1.md`
must be promoted from stub to a full implementation plan with:
- A dedicated PRD authored for Epic D scope
- Full task tables covering HashRouter→BrowserRouter conversion, Next.js project
  setup, Vite proxy → `next.config.ts` rewrites, SSR compatibility audit, and
  incremental route migration
- `status` promoted from `draft` to `approved`
- An assigned owner and contributor list

### Precondition 3: `CCDASH_NEXTJS_ENABLED` feature flag defined

The feature flag `CCDASH_NEXTJS_ENABLED` must be:
- Defined as a backend environment variable
- Exposed via `/api/health` response (following the `CCDASH_FEATURE_SURFACE_V2_ENABLED`
  runtime pattern — see `services/featureSurfaceFlag.ts:36` for the convention)
- Tested in a canary deploy to confirm the flag gates SSR rendering without
  breaking the baseline Vite SPA path

This flag enables progressive rollout: the SSR path can be enabled per-environment
without a full redeploy, and rolled back by toggling the backend env var.

---

## 4. Verification Checklist

Before Epic D execution begins, the responsible owner must confirm all items below:

- [ ] Epics A, B, C shipped — date: ___________
- [ ] 14-day smoke-clean window elapsed — end date: ___________
- [ ] Source grep confirms no `HashRouter` import in any `.tsx`/`.ts` file
- [ ] Source grep confirms no module-scope `window.*` reads outside
  `typeof window !== 'undefined'` guards in context or service files
- [ ] `ccdash-nextjs-migration-v1.md` status is `approved` (not `draft`)
- [ ] `CCDASH_NEXTJS_ENABLED` flag defined in backend env + exposed via `/api/health`
- [ ] Canary deploy with `CCDASH_NEXTJS_ENABLED=true` passes smoke tests
- [ ] Epic D PRD authored and referenced in `ccdash-nextjs-migration-v1.md`

---

## 5. References

- **Parent PRD** (AC-D1 source): `docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md` §11 Epic D
- **Parent implementation plan**: `docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md`
- **Phase plan (DOC-006 task)**: `docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1/phase-5-7-backend-virtualization-validation.md` (T7-006)
- **Prior art inventory (SSR analysis)**: `.claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-priorart.md §4`
- **Next.js migration stub**: `docs/project_plans/implementation_plans/refactors/ccdash-nextjs-migration-v1.md`
- **Feature surface flag convention**: `services/featureSurfaceFlag.ts:36`
- **AuthSessionContext (SSR-safe window usage)**: `contexts/AuthSessionContext.tsx:192-193`

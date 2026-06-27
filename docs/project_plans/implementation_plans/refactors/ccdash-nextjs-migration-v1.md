---
schema_version: 2
doc_type: implementation_plan
title: "Implementation Plan: CCDash Next.js / SSR Migration v1 (STUB)"
status: draft
created: '2026-05-29'
updated: '2026-05-29'
feature_slug: ccdash-frontend-data-layer-refactor
category: refactors
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
scope: >
  Migrate CCDash from a Vite + HashRouter SPA to Next.js App Router with
  server-side rendering. Scope includes HashRouter-to-BrowserRouter conversion,
  module-scope browser-global remediation, Vite proxy replacement with
  next.config.ts rewrites, incremental route migration, and SSR compatibility
  validation. Execution is blocked until all entry criteria in
  ccdash-nextjs-migration-entry-criteria.md are met.
architecture_summary: null
effort_estimate: null
plan_structure: unified
progress_init: auto
tags:
  - implementation
  - stub
  - nextjs
  - ssr
  - migration
  - epic-d
  - blocked
priority: low
risk_level: high
owner: null
contributors: []
milestone: null
commit_refs: []
pr_refs: []
related_documents:
  - docs/project_plans/design-specs/ccdash-nextjs-migration-entry-criteria.md
  - docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md
  - docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md
  - .claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-priorart.md
---

# Implementation Plan: CCDash Next.js / SSR Migration v1 (STUB)

> **BLOCKED — DO NOT EXECUTE**
>
> This plan is a stub. Execution is blocked until all entry criteria defined in
> `docs/project_plans/design-specs/ccdash-nextjs-migration-entry-criteria.md`
> are satisfied. No implementation tasks are defined here; those require a
> dedicated PRD for Epic D that has not yet been authored.

---

## Scope

This plan covers the migration of CCDash from its current Vite-bundled,
HashRouter-based SPA to a Next.js App Router application with server-side
rendering capability. The migration is the execution phase of Epic D from the
CCDash Frontend Data Layer Refactor PRD. The work includes: replacing the single
`HashRouter` instance in `App.tsx` (lines 2, 92, 132) with Next.js file-based
routing; auditing and remediating any remaining module-scope browser-global reads
across context and service files; replacing the `vite.config.ts` `/api` proxy
(lines 54-59) with `next.config.ts` rewrites targeting the same backend origin;
migrating all `React.lazy`/`lazyNamed` route imports to `next/dynamic`; and
validating SSR rendering of each route surface under the `CCDASH_NEXTJS_ENABLED`
feature flag. Implementation detail, task tables, and effort estimates will be
authored in a future PRD for Epic D after the entry criteria gate opens.

---

## SSR Blockers

The following blockers were identified during the `ccdash-frontend-data-layer-refactor-v1`
inventory phase (`inventory-priorart.md §4`) and must be resolved before this plan
can proceed to implementation. See
`docs/project_plans/design-specs/ccdash-nextjs-migration-entry-criteria.md §2`
for full analysis and verified citations.

### Blocker 1: HashRouter usage in App.tsx

`HashRouter` from `react-router-dom` is imported and used in `App.tsx` (import at
line 2, `<HashRouter>` at line 92, `</HashRouter>` at line 132). `HashRouter`
depends on `window.location.hash` internally and cannot function in a Node.js SSR
context. All routing must be converted to Next.js App Router file-based routing or
`BrowserRouter` before SSR is possible.

The inventory originally cited ~30 affected files. As of 2026-05-29, grep
confirms `HashRouter` is actively used only in `App.tsx`. The single file with
an active import is the primary remediation target. A prose comment in
`components/Workflows/WorkflowRegistryPage.tsx:338` references `HashRouter` but
contains no import or usage.

### Blocker 2: Module-scope window.location.hash read (AppRuntimeContext.tsx)

The inventory documented a module-scope `window.location.hash` read at
`contexts/AppRuntimeContext.tsx:43`. As of 2026-05-29, this read is no longer
present in the current worktree — the file was refactored during Phase 4 of the
parent plan. The PRD AC-D1 criterion 2 is preserved as a mandatory audit gate:
before Epic D begins, a comprehensive grep must confirm no context or service file
reads `window`, `document`, or `location` at module scope outside of
`typeof window !== 'undefined'` guards.

### Non-blocker: window.location.assign in AuthSessionContext.tsx

`contexts/AuthSessionContext.tsx:193` uses `window.location.assign` inside a
callback, guarded by `typeof window !== 'undefined'` on line 192. This pattern is
SSR-safe and does not require remediation.

---

## Entry Criteria Gate

**Execution of this plan is blocked until all of the following are true:**

1. Epics A, B, and C of `ccdash-frontend-data-layer-refactor-v1` are shipped and
   runtime-smoke-clean for a minimum of 14 consecutive calendar days.

2. `window.location.hash` module-scope reads in any context or service file are
   confirmed absent by source grep (the specific `AppRuntimeContext.tsx:43`
   instance was already removed; a full audit is still required at Epic D entry).

3. `HashRouter` is replaced with `BrowserRouter` (or removed in favor of Next.js
   App Router) across all affected files — verified by source grep asserting no
   `HashRouter` import remains.

4. This stub plan is promoted to a full implementation plan: a dedicated Epic D
   PRD is authored and approved, and this file's `status` is changed from `draft`
   to `approved` with complete task tables and effort estimates.

5. Feature flag `CCDASH_NEXTJS_ENABLED` is defined in backend health and tested
   via canary deploy.

See `docs/project_plans/design-specs/ccdash-nextjs-migration-entry-criteria.md`
for the complete entry criteria specification, verification checklist, and
precondition details.

---

## References

- **Entry criteria spec**: `docs/project_plans/design-specs/ccdash-nextjs-migration-entry-criteria.md`
- **Parent PRD (AC-D1)**: `docs/project_plans/PRDs/refactors/ccdash-frontend-data-layer-refactor-v1.md §11`
- **Parent implementation plan**: `docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1.md`
- **Phase plan (DOC-006)**: `docs/project_plans/implementation_plans/refactors/ccdash-frontend-data-layer-refactor-v1/phase-5-7-backend-virtualization-validation.md` (T7-006, T7-007)
- **SSR blocker inventory**: `.claude/worknotes/ccdash-frontend-data-layer-refactor/inventory-priorart.md §4`

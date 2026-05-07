---
created: 2026-05-07
purpose: Phase 4 — ModalTabId ownership manifest for planning/forensics/execution boundary extraction
scope: components/ProjectBoard.tsx, services/useFeatureModalData.ts, services/featureSurface.ts
status: ready-for-p4-001
---

# Phase 4 Tab/Domain Ownership Manifest

Maps all 7 `ModalTabId` values to their post-extraction domain owner. Authoritative input for P4-001 through P4-007 parallel UI work.

`ModalTabId` is defined at `services/useFeatureModalData.ts:53–60`. The type alias `FeatureModalTab = PlanningFeatureModalTab` exported from `components/ProjectBoard.tsx:236` is an alias over `PLANNING_FEATURE_MODAL_TABS` defined in `services/planningRoutes.ts:5–13`. Both enumerate the same 7 values.

---

## Tab Ownership Summary Table

| Tab ID | Owner domain | Current source file(s) | Target file(s) | Data route | Cache bus events | Tests to update |
|--------|-------------|------------------------|----------------|------------|-----------------|-----------------|
| `overview` | `shared-shell` (card + rollup) + `planning` (execution gate, family position, delivery metadata) | `components/ProjectBoard.tsx` L3112–3374 (inline in modal) | `components/FeatureModal/OverviewTab.tsx` (new); shell props from `shared-shell`; planning sub-sections from `components/Planning/` | `GET /api/v1/features/{id}/modal` → `getFeatureModalOverview` → `FeatureModalOverviewDTO` (card + rollup). Planning sub-fields (execution gate, family position) continue from `useData()` legacy path during P4. | `featureCacheBus` `kind: status | phase | rename | generic` — triggers `featureSurfaceCache` invalidation which marks `overview` stale via `modalSections.overview.invalidate()` | `components/__tests__/FeatureModalConsumerWiring.test.tsx`, `components/__tests__/ProjectBoard.featureModal.test.tsx`, `services/__tests__/useFeatureModalData.test.ts` |
| `phases` | `planning` | `components/ProjectBoard.tsx` L3375–3633 (inline in modal) | `components/FeatureModal/PhasesTab.tsx` (new, planning-owned) | `GET /api/v1/features/{id}/modal/phases` → `getFeatureModalSection('phases')` → `FeatureModalSectionDTO`. Wire key: `phases`. | `kind: phase` → `featureSurfaceCache` invalidates; `modalSections.phases` transitions to `stale` via live refresh policy (`applyLiveRefreshPolicy('phases', ...)` at ProjectBoard L1754). Live topic: `feature.{id}`. | `components/__tests__/FeatureModalConsumerWiring.test.tsx`, `components/__tests__/FeatureModalLazyTabs.test.tsx`, `components/__tests__/FeatureModalLiveRefresh.test.tsx`, `services/__tests__/useFeatureModalData.test.ts` |
| `docs` | `planning` | `components/ProjectBoard.tsx` L3634–3775 (inline in modal) | `components/FeatureModal/DocsTab.tsx` (new, planning-owned) | `GET /api/v1/features/{id}/modal/documents` → `getFeatureModalSection('docs')` → `FeatureModalSectionDTO`. Wire key: `documents`. | `kind: generic` → cache invalidates; live topic `feature.{id}` drives `applyLiveRefreshPolicy('docs', ...)` at ProjectBoard L1755. Document mutations arrive as `feature.{id}` events per the live invalidation topology. | `components/__tests__/FeatureModalConsumerWiring.test.tsx`, `components/__tests__/FeatureModalLazyTabs.test.tsx`, `components/__tests__/FeatureModalLiveRefresh.test.tsx` |
| `relations` | `planning` | `components/ProjectBoard.tsx` L3776–3902 (inline in modal) | `components/FeatureModal/RelationsTab.tsx` (new, planning-owned) | `GET /api/v1/features/{id}/modal/relations` → `getFeatureModalSection('relations')` → `FeatureModalSectionDTO`. Wire key: `relations`. | `kind: generic` → cache invalidates; live topic `feature.{id}` drives `applyLiveRefreshPolicy('relations', ...)` at ProjectBoard L1756. | `components/__tests__/FeatureModalConsumerWiring.test.tsx`, `components/__tests__/FeatureModalLazyTabs.test.tsx`, `components/__tests__/FeatureModalLiveRefresh.test.tsx` |
| `sessions` | `forensics` | `components/ProjectBoard.tsx` L3903–4097 (inline in modal) | `components/FeatureModal/SessionsTab.tsx` (new, forensics-owned) | `GET /api/v1/features/{id}/sessions/page` → `getFeatureLinkedSessionPage` → `LinkedFeatureSessionPageDTO`. Pagination accumulator at `SessionPaginationState` in `useFeatureModalData`. Wire key: `sessions` (not a `FeatureModalSectionKey`; uses the paginated sessions endpoint directly). | `kind: generic` or `kind: status` → cache invalidates sessions section. Live topics: `session.{id}` (per visible session) and `feature.{id}`. Pagination state reset on invalidation. | `components/__tests__/FeatureModalSessionsPagination.test.tsx`, `components/__tests__/FeatureModalConsumerWiring.test.tsx`, `components/__tests__/FeatureModalLazyTabs.test.tsx`, `services/__tests__/useFeatureModalDataSessionsPagination.test.ts` |
| `test-status` | `execution` | `components/ProjectBoard.tsx` L4098–4115 (inline in modal); `FeatureModalTestStatus` sub-component (unknown extract target) | `components/FeatureModal/TestStatusTab.tsx` (new, execution-owned); links to `FeatureExecutionWorkbench` at `/execution?feature=...&tab=test-status` | `GET /api/v1/features/{id}/modal/test_status` → `getFeatureModalSection('test-status')` → `FeatureModalSectionDTO`. Wire key: `test_status`. Legacy: `featureTestHealth` state set by `refreshFeatureTestHealth()` in ProjectBoard; the typed section supplements but does not yet replace it. | `kind: generic` → cache invalidates; live topic `project.{id}.tests` drives `applyLiveRefreshPolicy('test-status', ...)` at ProjectBoard L1758 (calls `refreshFeatureTestHealth()`). | `components/__tests__/FeatureModalConsumerWiring.test.tsx`, `components/__tests__/FeatureModalLiveRefresh.test.tsx`, `components/__tests__/ProjectBoardFilters.test.tsx` (test-status gate) |
| `history` | `forensics` | `components/ProjectBoard.tsx` L4116–4297 (inline in modal) | `components/FeatureModal/HistoryTab.tsx` (new, forensics-owned) | `GET /api/v1/features/{id}/modal/activity` → `getFeatureModalSection('history')` → `FeatureModalSectionDTO`. Wire key: `activity`. `gitHistoryData` (commits, PRs, branches) is derived client-side from the `FeatureModalSectionDTO` items. | `kind: generic` → cache invalidates; live topic `feature.{id}` drives `applyLiveRefreshPolicy('history', ...)` at ProjectBoard L1757. | `components/__tests__/FeatureModalConsumerWiring.test.tsx`, `components/__tests__/FeatureModalLazyTabs.test.tsx`, `components/__tests__/FeatureModalLiveRefresh.test.tsx` |

---

## Decisions

### 1. `overview` — shared-shell vs planning vs forensics?

**Decision: split ownership — shared-shell for the DTO container + metric tiles; planning for the editorial sub-sections.**

Rationale:

- The `overview` tab is loaded via `getFeatureModalOverview` which returns `FeatureModalOverviewDTO` — a composite of `FeatureCardDTO` (summary metrics: task counts, status, coverage) and `FeatureRollupDTO` (session totals, token aggregates, model families). Neither is domain-specific; both are shared summaries consumed by the board, dashboard, and modal alike.
- However, the tab body currently renders three distinct sub-sections that are unambiguously planning-owned: **Delivery Metadata** (priority, risk, complexity, track, target release, milestone, readiness — `ProjectBoard.tsx` L3146–3162), **Quality Signals** (blockers, at-risk counts, integrity refs — L3163–3180), and **Family Position + Blocker Evidence** (L3200–3268). These fields come from the legacy `fullFeature` / `activeFeature` state, not from `FeatureModalOverviewDTO`.
- The **Execution Gate** card (L3184–3198) and the **Begin Work CTA** (L3059–3067) are execution-owned (see Decision 3).
- The four metric tiles at L3114–3142 (Total Tasks, Completed, Phases, Documents) are shared-shell summaries derivable from `FeatureCardDTO`.

**Extraction target**: `OverviewTab.tsx` composes:
- `OverviewMetricStrip` (shared-shell) — the four `FeatureMetricTile` cards from `FeatureCardDTO`
- `PlanningDeliverySection` (planning) — Delivery Metadata + Quality Signals sub-sections
- `PlanningFamilySection` (planning) — Family Position + Blocker Evidence sub-sections
- `ExecutionGateCard` (execution) — Execution Gate card only; Begin Work CTA is in the modal header (shared-shell)

The `FeatureModalOverviewDTO` (card + rollup) is the `overview` section's primary data payload and is owned by `shared-shell`. Planning sub-sections continue to read from `fullFeature` during P4 (legacy path) and are migrated in P5.

---

### 2. `test-status` — execution vs shared?

**Decision: execution-owned.**

Rationale:

- The `test-status` tab renders `FeatureModalTestStatus` (L4106–4113), whose only navigation action is `navigate(/execution?feature=...&tab=test-status)` — it links directly into `FeatureExecutionWorkbench`. There is no planning-domain content in this tab.
- The `featureTestHealth` state (used as a gate to show/hide the tab at L4098 and L2619) is populated by `refreshFeatureTestHealth()`, which reads test health data. Test health is an execution signal, not a planning artifact.
- The live refresh topic for `test-status` is `project.{id}.tests` — a purpose-built test metrics topic separate from the planning `feature.{id}` topic — confirming the execution domain boundary.
- The tab is conditionally hidden when `featureTestHealth.totalTests <= 0` (L1634–1635) and omitted from the tab bar when no test health is present. This guard is an execution-domain concern.

**Extraction target**: `components/FeatureModal/TestStatusTab.tsx` (execution-owned). The `FeatureModalTestStatus` component and `refreshFeatureTestHealth` helper migrate with it.

---

### 3. Execution gate / Begin Work CTA — must be execution-owned, currently in ProjectBoard

**Decision: CTA button stays in shared-shell modal header; `ExecutionGateCard` extracted to execution domain.**

Rationale:

- The **Begin Work** button (L3059–3067) lives in the modal header chrome alongside the Expand and Close buttons. This chrome is shared-shell and must remain a single coherent unit — splitting the header across domains would require prop-drilling the gate state up, which costs more than keeping the CTA in the header and marking it execution-intent.
- The CTA calls `handleBeginWork` (L1827, L1831) which calls `trackExecutionEvent` and navigates to `/execution`. The CTA's presence/readiness can be gated by an `executionGateState` prop passed down from the `ExecutionGateCard` to the modal header. This is a thin interface (one boolean + one string label) that is acceptable shared-shell surface.
- The **Execution Gate card** inside the `overview` tab body (L3184–3198) — which shows the gate state badge, reason, waiting-on-family-predecessor, and next item — is execution-domain content and should extract to `components/FeatureModal/ExecutionGateCard.tsx` (execution-owned). It is composed into `OverviewTab.tsx` by import, not by prop-drilling JSX.

**Concrete boundary**: the modal header and tab nav remain `shared-shell`. The `ExecutionGateCard` JSX sub-component is `execution`-owned and imported into `OverviewTab.tsx` by the shared-shell composition layer.

---

### 4. `history` — forensics (session history) vs shared?

**Decision: forensics-owned.**

Rationale:

- The `history` tab renders git commits, pull requests, and branches linked to the feature — all of which are derived from session/VCS forensics signals, not from planning documents or execution state.
- The wire section key is `activity` (per `TAB_TO_SECTION_KEY` at `useFeatureModalData.ts:62–68`), and the backend handler (`_client_v1_features.py`) resolves this via the session-activity and git-link subsystems — not the planning phase/doc/relations subsystem.
- While the tab is displayed inside the planning-oriented feature modal, its data dependency is on git history correlation to sessions, which is an artifact of the forensics pipeline (commit→session linking, branch tracking). No planning-domain mutations affect this tab.
- The `gitHistoryCommitFilter` filter state (L1409) is a forensics-navigation feature, not a planning filter. It does not appear in any planning state context.

**Extraction target**: `components/FeatureModal/HistoryTab.tsx` (forensics-owned). The `gitHistoryData` derivation logic and `gitHistoryCommitFilter` state migrate with it.

---

## Shared Type Changes Needed Before Parallel UI Work

The following additions must land in `services/useFeatureModalData.ts` (or a co-located types file) before P4-001 through P4-007 can proceed in parallel, to avoid merge conflicts on the type surface:

1. **`ModalTabDomain` enum/union** — `'shared-shell' | 'planning' | 'forensics' | 'execution'` — allows type-safe domain tagging on tab components and guards. Currently absent; each domain PR would otherwise add it redundantly.

2. **`TabOwnershipRecord`** — `Record<ModalTabId, ModalTabDomain>` constant — a single source of truth for which domain owns which tab. Consumed by the tab-bar renderer and any future tab-level permission/feature-flag checks. Currently this mapping is implicit in the `activeTab === ...` branches in ProjectBoard.

3. **`OverviewTabProps` interface** — the overview tab takes a composite of `FeatureModalOverviewDTO` (shared-shell) plus optional planning and execution sub-section props. This interface must be defined once before three different domain PRs touch the overview rendering. Candidate location: `components/FeatureModal/types.ts` (new shared types file for the FeatureModal subtree).

4. **`ExecutionGateCardProps` interface** — the execution gate card needs a stable prop interface (`state`, `reason`, `isReady`, `waitingOnFamilyPredecessor`, `nextItemLabel`) so the shared-shell `OverviewTab.tsx` can import and compose it without coupling to the full `fullFeature` legacy shape.

No type additions are required in the root `types.ts` — all new types are scoped to the feature modal subtree.

---

## Write-Scope Conflicts

The following files must NOT be edited concurrently across domain extraction tasks. Each row identifies the conflict and the required serialization order.

| File | Conflict reason | Required order |
|------|----------------|----------------|
| `services/useFeatureModalData.ts` | `ModalTabId` type, `ALL_TABS` array, `TAB_TO_SECTION_KEY` map, and the `ModalSectionStore` shape are shared by all 7 domain PRs. Any domain that adds a tab-level type (e.g., `ModalTabDomain`) touches this file. | Add shared types (Decision §Shared types above) in a single pre-PR commit before domain PRs open. After that, domain PRs must not modify this file — they only import from it. |
| `components/ProjectBoard.tsx` | Contains all 7 tab render blocks inline. Every domain extraction deletes a block from this file and replaces it with a component import. Parallel edits will produce merge conflicts in the `activeTab === ...` conditional chain. | Extract tabs sequentially or assign non-overlapping line ranges per PR. Preferred: a single "extraction coordinator" PR deletes all 7 inline blocks and replaces with stub imports; domain PRs then implement the stub components in new files only. |
| `services/planningRoutes.ts` | `PLANNING_FEATURE_MODAL_TABS` constant is the canonical tab list. If any domain PR adds or reorders a tab ID, this file changes. | No tab additions are planned for P4; if added, serialize through a single PR before domain work. |
| `components/FeatureModal/TabStateView.tsx` | Shared rendering primitive used by all 7 tabs. Any a11y or status-semantic change here affects every domain. | Do not modify `TabStateView.tsx` during P4 domain extraction. Changes require a separate cross-domain PR with full test coverage. |
| `services/featureSurface.ts` | DTO types (`FeatureModalOverviewDTO`, `FeatureModalSectionDTO`, `LinkedFeatureSessionPageDTO`) are imported by all domain tab components. Wire-type changes ripple to all 7 tabs. | Freeze wire types during P4 extraction. P5 may introduce new section fields; add them as optional fields to avoid breaking extraction PRs in flight. |

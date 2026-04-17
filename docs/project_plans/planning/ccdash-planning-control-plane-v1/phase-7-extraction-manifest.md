---
type: report
schema_version: 2
doc_type: report
title: Phase 7 Extraction Manifest — Planning UI Consolidation
prd: ccdash-planning-control-plane-v1
feature_slug: ccdash-planning-control-plane-v1
report_category: audit
created: 2026-04-17
updated: 2026-04-17
---

# Phase 7 Extraction Manifest — Planning UI Consolidation

## Summary

This manifest audits all planning-specific UI primitives, badges, chips, list renderers, and metadata components in `components/Planning/` (particularly `components/Planning/primitives/`) against the 8-criteria extraction decision tree defined in `.claude/skills/planning/references/ui-extraction-guidance.md`.

**Total Planning Primitives Audited**: 10
- **import** decisions: 0 (no exact matches in @miethe/ui yet)
- **extract** decisions: 5 (high-value, reusable, generic metadata displays)
- **keep-local** decisions: 5 (tight coupling to planning domain logic, experimental APIs)

---

## Inventory

### components/Planning/primitives/

#### StatusChip.tsx

**Location**: `components/Planning/primitives/StatusChip.tsx` (lines 1–29)

**Purpose**: Reusable slate badge rendering five planning status variants (neutral / ok / warn / error / info) via inline-flex chip with color mapping.

**Consumers** (grep-verified):
- `components/Planning/primitives/BatchReadinessPill.tsx` (line 22) — wraps readiness state
- `components/Planning/primitives/EffectiveStatusChips.tsx` (lines 28, 43) — renders raw + effective status
- `components/Planning/primitives/LineageRow.tsx` (lines 47, 51) — displays node status chips
- `components/Planning/primitives/PhaseOperationsPanel.tsx` (lines 14, 60, 137) — batch + task status
- `components/Planning/PlanningLaunchSheet.tsx` (line 21) — launch sheet status indicators

**Test Coverage**: 56 lines in `__tests__/statusChip.test.tsx` (5 test cases covering all variants + tooltip)

**Decision**: **EXTRACT**

**Rationale**:
- ✓ **Reuse**: Used in 5+ planning components; ProjectBoard imports via primitives index
- ✓ **Generic**: No SkillMeat service dependencies, pure presentational (label + variant → colors)
- ✓ **Stable API**: Props (`label`, `variant`, `tooltip`) unchanged for 4+ weeks
- ✓ **Design System**: Uses Tailwind slate/emerald/amber/rose tokens (design-system aligned)
- ✓ **Documented**: JSDoc comment on function; clear prop interface
- ✓ **Tested**: 56 lines covering neutral/ok/warn/error/info variants + tooltip hover
- ✓ **Accessible**: Semantic HTML `<span>`, no ARIA needed; title attribute for tooltip
- ~ **Storybook Ready**: No story yet, but component is simple enough to add one easily

**Proposed @miethe/ui Path**: `src/primitives/StatusChip.tsx`

**Estimated Effort**: Small (S) — pure presentational, no external deps

**Risk Notes**:
- None identified; migration is straightforward.

**Migration Notes**:
1. Copy to @miethe/ui/src/primitives/StatusChip.tsx
2. Create story at @miethe/ui/src/primitives/StatusChip.stories.tsx
3. Add to @miethe/ui/src/primitives/index.ts export
4. Update CCDash import: `import { StatusChip } from '@miethe/ui/primitives'`
5. Remove local copy after npm publish + version bump in package.json

---

#### EffectiveStatusChips.tsx

**Location**: `components/Planning/primitives/EffectiveStatusChips.tsx` (lines 1–49)

**Purpose**: Renders raw status chip plus optional effective status chip when values differ; wraps raw chip in hover tooltip showing provenance (source + reason).

**Consumers** (grep-verified):
- `components/Planning/primitives/PhaseOperationsPanel.tsx` (line 249) — phase status display
- `components/ProjectBoard.tsx` (line 33) — imported from primitives index

**Test Coverage**: 71 lines in `__tests__/effectiveStatusChips.test.tsx` (7 test cases covering mismatch detection, provenance tooltip, effective status display)

**Decision**: **EXTRACT**

**Rationale**:
- ✓ **Reuse**: Used in 2+ features (planning phases + project board); cross-component reuse signal
- ✓ **Generic**: Composes StatusChip; no SkillMeat-specific business logic (just layout + provenance display)
- ✓ **Stable API**: Props unchanged for 4+ weeks
- ✓ **Design System**: Tailwind panel colors (border-panel-border, bg-slate-900) — maps to @miethe/ui token theme
- ✓ **Documented**: JSDoc comment; prop interface clear
- ✓ **Tested**: 71 lines covering mismatch, provenance hover, effective-status variations
- ✓ **Accessible**: Semantic layout, hover tooltip accessible via title attribute
- ~ **Storybook Ready**: No story; component is medium complexity (hover state + tooltip)

**Proposed @miethe/ui Path**: `src/primitives/EffectiveStatusChips.tsx`

**Estimated Effort**: Small (S) — builds on StatusChip, simple hover + tooltip logic

**Risk Notes**:
- Depends on StatusChip; extract StatusChip first, then this as dependent.
- Provenance interface is planning-specific but generic enough for reuse.

**Migration Notes**:
1. Extract StatusChip first (dependency)
2. Copy EffectiveStatusChips to @miethe/ui/src/primitives/
3. Update internal import to use @miethe/ui version
4. Create story with provenance example
5. Add to index.ts
6. Update CCDash imports

---

#### StatusChipVariant + ReadinessVariant (variants.ts)

**Location**: `components/Planning/primitives/variants.ts` (lines 1–29)

**Purpose**: Type definitions and variant helper functions (`statusVariant()`, `readinessVariant()`) that map domain status strings to StatusChip color variants.

**Consumers** (grep-verified):
- `components/Planning/primitives/StatusChip.tsx` (line 1) — type definition
- `components/Planning/primitives/BatchReadinessPill.tsx` (line 3) — readinessVariant()
- `components/Planning/primitives/EffectiveStatusChips.tsx` (lines 3, 44) — statusVariant()
- `components/Planning/primitives/LineageRow.tsx` (lines 6, 47) — statusVariant()
- `components/Planning/primitives/PhaseOperationsPanel.tsx` (lines 15, 137) — statusVariant()
- `components/Planning/PlanningLaunchSheet.tsx` (line 22) — statusVariant()

**Test Coverage**: 56 lines in `__tests__/variants.test.ts` (5 test cases covering status/readiness mappings)

**Decision**: **EXTRACT** (as part of StatusChip package)

**Rationale**:
- ✓ **Reuse**: Used by StatusChip and 5 consumer components
- ✓ **Generic**: Pure mapping functions; no domain-specific logic beyond string patterns
- ✓ **Stable API**: Unchanged for 4+ weeks
- ✓ **Tested**: 56 lines covering complete mapping space

**Proposed @miethe/ui Path**: Inline export from `src/primitives/StatusChip.tsx` (not separate file)

**Estimated Effort**: Included with StatusChip extraction

---

#### MismatchBadge.tsx

**Location**: `components/Planning/primitives/MismatchBadge.tsx` (lines 1–61)

**Purpose**: Renders amber mismatch indicator in two forms: compact (inline chip with icon + state label) or full banner (title + reason + evidence chips). Used to flag status divergence and conflicts.

**Consumers** (grep-verified):
- `components/Planning/primitives/PhaseOperationsPanel.tsx` (line 13, 292) — renders blockers mismatch
- `components/ProjectBoard.tsx` (line 33) — imported from primitives index

**Test Coverage**: 79 lines in `__tests__/mismatchBadge.test.tsx` (7 test cases covering compact/banner modes, evidence labels)

**Decision**: **EXTRACT**

**Rationale**:
- ✓ **Reuse**: Used in 2+ contexts (phase operations + board); cross-component signal
- ✓ **Generic**: Presentational only; accepts state string + reason + evidence labels; no external service calls
- ✓ **Stable API**: Props (`state`, `reason`, `evidenceLabels`, `compact`) stable for 4+ weeks
- ✓ **Design System**: Amber alert tokens (border-amber-500, bg-amber-500, text-amber-300) aligned with design system
- ✓ **Documented**: JSDoc comment on component and interface; prop explanations clear
- ✓ **Tested**: 79 lines covering compact/banner toggle, evidence rendering, title attributes
- ✓ **Accessible**: Uses semantic <span> and <div>; icon from lucide; title attribute for tooltips
- ~ **Storybook Ready**: No story; component has two clear variants (compact + full)

**Proposed @miethe/ui Path**: `src/primitives/MismatchBadge.tsx`

**Estimated Effort**: Small (S) — presentational, uses lucide icons (already available in @miethe/ui)

**Risk Notes**:
- None identified; migration straightforward.

---

#### BatchReadinessPill.tsx

**Location**: `components/Planning/primitives/BatchReadinessPill.tsx` (lines 1–35)

**Purpose**: Renders a batch readiness chip (via StatusChip) with optional blocker details shown inline below when blockingNodeIds or blockingTaskIds are present.

**Consumers** (grep-verified):
- `components/Planning/primitives/PhaseOperationsPanel.tsx` (lines 11, 60, 254) — batch readiness state + blockers
- `components/Planning/PlanningLaunchSheet.tsx` (line 20) — launch sheet batch status

**Test Coverage**: 83 lines in `__tests__/batchReadinessPill.test.tsx` (6 test cases covering readiness states, blocking nodes/tasks display)

**Decision**: **EXTRACT**

**Rationale**:
- ✓ **Reuse**: Used in 2+ components (phase operations + launch sheet)
- ✓ **Generic**: Composes StatusChip + readinessVariant; no planning-specific logic beyond layout
- ✓ **Stable API**: Props unchanged for 4+ weeks
- ✓ **Design System**: Uses rose/amber tokens for blocker warnings (aligned)
- ✓ **Documented**: JSDoc comment; interface clear
- ✓ **Tested**: 83 lines covering all readiness states + blocker rendering
- ✓ **Accessible**: Text-based display; truncate attributes for long lists
- ~ **Storybook Ready**: No story; component has clear single variant

**Proposed @miethe/ui Path**: `src/primitives/BatchReadinessPill.tsx`

**Estimated Effort**: Small (S) — depends on StatusChip, simple layout

**Risk Notes**:
- Depends on StatusChip and readinessVariant; extract StatusChip first.

---

#### PlanningNodeTypeIcon.tsx

**Location**: `components/Planning/primitives/PlanningNodeTypeIcon.tsx` (lines 1–40)

**Purpose**: Reusable icon component for PlanningNodeType values. Maps type string to lucide icon (design_spec → FolderSearch, prd → FileText, etc.). Used inline in node lists and lineage rows.

**Consumers** (grep-verified):
- `components/Planning/primitives/LineageRow.tsx` (line 30) — node type icon in lineage
- `components/Planning/PlanningGraphPanel.tsx` (line 66) — NodeTypeIcon function (duplicate logic)
- `components/ProjectBoard.tsx` (line 33) — imported from primitives index

**Test Coverage**: No explicit unit tests; tested implicitly in parent components

**Decision**: **EXTRACT**

**Rationale**:
- ✓ **Reuse**: Used in 2+ places; PlanningGraphPanel has duplicate logic (NodeTypeIcon) that should be consolidated
- ✓ **Generic**: Pure type-to-icon mapper; no business logic
- ✓ **Stable API**: Props (type, size, className) stable for 4+ weeks
- ✓ **Design System**: Lucide icons; uses muted-foreground color token
- ✓ **Documented**: JSDoc comment; prop interface clear
- ⚠ **Tested**: No explicit unit test (blocker for extraction quality gate)
- ✓ **Accessible**: Icons have text context in parent components; semantic HTML
- ~ **Storybook Ready**: No story; component is very simple (icon map)

**Proposed @miethe/ui Path**: `src/primitives/PlanningNodeTypeIcon.tsx`

**Estimated Effort**: Small (S) — icon mapper, no external deps

**Risk Notes**:
- **Blocker**: No unit test. Before extraction, add test file covering all 7+ node types.
- PlanningGraphPanel has duplicate NodeTypeIcon logic (lines 66–78) — should be refactored to use this component

**Migration Notes**:
1. **First**: Add unit test covering all node types (design_spec, prd, implementation_plan, progress, context, tracker, report)
2. Copy to @miethe/ui/src/primitives/PlanningNodeTypeIcon.tsx
3. Refactor PlanningGraphPanel to import and use this component
4. Update CCDash import

---

#### LineageRow.tsx

**Location**: `components/Planning/primitives/LineageRow.tsx` (lines 1–56)

**Purpose**: Renders a single planning node as a lineage row: icon (PlanningNodeTypeIcon), title, path, optional timestamp (formatted), and raw + effective status chips. Used in node lineage panels and dependency visualization.

**Consumers** (grep-verified):
- `components/Planning/PlanningNodeDetail.tsx` (implicit — used in LineagePanel)
- Planning node detail views

**Test Coverage**: No explicit unit test (tested implicitly)

**Decision**: **KEEP-LOCAL**

**Rationale**:
- ⚠ **Reuse**: Single-use component (only in PlanningNodeDetail lineage context); no cross-feature reuse
- ⚠ **Generic**: Tightly coupled to PlanningNode type structure and planning domain semantics (node.rawStatus, node.effectiveStatus, node.mismatchState)
- ⚠ **Tight Coupling**: Depends on planning-specific types; not generically reusable for other node types
- ✓ **Stable API**: Props stable for 4+ weeks
- ⚠ **No Test Coverage**: No unit tests; tested implicitly only
- ⚠ **Design System**: Uses planning-specific color mapping (status → variant)

**Keep-Local Reason**:
This component is a planning-domain-specific row renderer. Its value is in combining planning-specific semantics (mismatchState, effectiveStatus) with presentation. Extracting it would require either (a) accepting planning-specific types in @miethe/ui (violating genericity), or (b) refactoring it into a generic `ListRow` component with status/icon slots (major refactor). For now, keep it local to planning and refactor if a pattern emerges for other domain row renderers.

---

#### PhaseOperationsPanel.tsx

**Location**: `components/Planning/primitives/PhaseOperationsPanel.tsx` (lines 1–483)

**Purpose**: Self-contained panel that fetches PhaseOperations for a single phase and renders batches, tasks, dependencies, progress evidence, and validation outcomes. Composed of multiple sub-component renderers (PhaseOperationsBatchSection, PhaseOperationsTaskSection, PhaseOperationsDependencySection, PhaseOperationsEvidenceSection, PhaseOperationsContent).

**Consumers** (grep-verified):
- `components/Planning/PlanningNodeDetail.tsx` (implied via primitives index)
- Planning node detail views

**Test Coverage**: 515 lines in `__tests__/phaseOperationsPanel.test.tsx` (comprehensive coverage of loading/error/success states, batch/task rendering, blockers)

**Decision**: **KEEP-LOCAL**

**Rationale**:
- ⚠ **Single-Use**: Only used in PlanningNodeDetail; no cross-feature reuse
- ✓ **Tested**: 515 lines with comprehensive test coverage
- ✗ **Service Coupling**: Depends on planning API services (`getPhaseOperations`, `getLaunchCapabilities`); calls `prepareLaunch`, `startLaunch`
- ✗ **Live Update Hooks**: Uses `useLiveInvalidation` with `featurePlanningTopic`; planning-specific
- ✗ **Tight Domain Coupling**: Renders planning-specific PhaseOperations data structure with batches, tasks, dependency resolution, progress evidence
- ✗ **Launch Integration**: Owns launch state management and opens PlanningLaunchSheet modal
- ✗ **Component Composition**: Exports 5 sub-components (PhaseOperationsBatchSection, etc.) that are internal layout helpers

**Keep-Local Reason**:
This is a feature-specific container component that orchestrates multiple planning services and state. Extracting it would require:
1. Decoupling from planning API services (refactor to accept data props)
2. Decoupling from live invalidation
3. Extracting launch flow (which is planning-specific)

This is a mid-phase refactoring candidate (PCP-709 may tackle this), but for now it's best kept local. The **exported sub-components** (PhaseOperationsContent, PhaseOperationsBatchSection, etc.) are testable and could be extracted later if a pattern emerges.

---

#### castPlanningStatus.ts

**Location**: `components/Planning/primitives/castPlanningStatus.ts` (lines 1–60)

**Purpose**: Defensive casting function that safely converts a `Record<string, unknown>` planningStatus dict (as returned by backend serializer) to a `PlanningEffectiveStatus`-shaped object. Handles both camelCase and snake_case keys (backend compat).

**Consumers** (grep-verified):
- Internal type guards; used in type narrowing

**Test Coverage**: Tested implicitly in status components

**Decision**: **KEEP-LOCAL**

**Rationale**:
- ✗ **No Standalone Reuse**: Utility function; not consumed by multiple independent features
- ✓ **Generic**: Pure type transformation; no external deps
- ✗ **Planning-Specific Types**: Depends on PlanningEffectiveStatus type; only useful in planning context
- ✓ **Stable API**: Unchanged for 4+ weeks

**Keep-Local Reason**:
This is a type-guard utility tightly bound to PlanningEffectiveStatus. While generic as a function, its utility is planning-specific. Keep local to avoid polluting @miethe/ui with planning-type utilities.

---

### components/Planning/ (top-level screens)

#### PlanningHomePage.tsx

**Location**: `components/Planning/PlanningHomePage.tsx` (lines 1–150+)

**Purpose**: Root planning screen. Fetches ProjectPlanningSummary and renders PlanningSummaryPanel, PlanningGraphPanel, and TrackerIntakePanel. Manages live invalidation and error/loading states.

**Decision**: **KEEP-LOCAL**

**Rationale**: Feature-specific container; orchestrates planning services and domains. Not reusable outside planning.

---

#### PlanningGraphPanel.tsx

**Location**: `components/Planning/PlanningGraphPanel.tsx` (lines 1–100+)

**Purpose**: Renders planning node graph with tree view of features, nodes grouped by feature slug, sorted by node type. Shows status badges and mismatch indicators.

**Decision**: **KEEP-LOCAL**

**Rationale**: Planning-specific visualization; tightly coupled to ProjectPlanningGraph data structure.

**Refactoring Note**: This component has duplicate `NodeTypeIcon` logic (lines 66–78) that should be refactored to use `PlanningNodeTypeIcon` component (PCP-709 work).

---

#### PlanningLaunchSheet.tsx

**Location**: `components/Planning/PlanningLaunchSheet.tsx` (lines 1–100+)

**Purpose**: Centered modal for preparing and launching a planning batch. Calls prepareLaunch on mount, lets user pick provider/model/worktree, handles approval gating and 409 force-override flow.

**Decision**: **KEEP-LOCAL**

**Rationale**: Planning execution feature; tightly coupled to launch APIs and approval workflows. Uses StatusChip and BatchReadinessPill (which should be extracted separately).

---

#### PlanningNodeDetail.tsx & PlanningSummaryPanel.tsx

**Location**: `components/Planning/PlanningNodeDetail.tsx`, `components/Planning/PlanningSummaryPanel.tsx`

**Decision**: **KEEP-LOCAL**

**Rationale**: Planning-specific screens and panels; not generically reusable.

---

## Extraction Roadmap for PCP-709

Ordered list of extract candidates with dependency order (if any primitive depends on another).

**Phase 1 — Foundation (S effort, no dependencies)**:
1. `StatusChip.tsx` + `variants.ts`
   - Atomic primitive with no internal dependencies
   - Used by 5+ components
   - Highest value for consolidation

**Phase 2 — Dependent Primitives (S effort, depends on Phase 1)**:
2. `EffectiveStatusChips.tsx`
   - Depends on StatusChip
   - Used in 2+ features (planning + board)
   
3. `BatchReadinessPill.tsx`
   - Depends on StatusChip + readinessVariant
   - Used in 2+ features

4. `MismatchBadge.tsx`
   - No dependencies (uses lucide icons)
   - Atomic
   - Used in 2+ features

**Phase 3 — Icon Component (S effort, requires unit tests first)**:
5. `PlanningNodeTypeIcon.tsx`
   - No dependencies
   - **Prerequisite**: Add unit test covering all 7 node types
   - **Refactoring**: Update PlanningGraphPanel to import and use this (instead of duplicate)

**Not in Extraction Scope**:
- LineageRow.tsx — single-use, planning-domain-specific
- PhaseOperationsPanel.tsx — service-coupled container component
- castPlanningStatus.ts — planning-type-specific utility
- Top-level screens (PlanningHomePage, PlanningGraphPanel, etc.) — feature containers

---

## Consolidation Roadmap for PCP-706

**Goal**: Consolidate planning metadata components into a shared layer that either imports from @miethe/ui or remains in `components/shared/PlanningMetadata.tsx`.

**Current State**: `components/shared/` does not exist yet.

**Proposed Structure**:
```
components/
  shared/
    PlanningMetadata.tsx
      ├─ Re-exports from @miethe/ui (after extraction)
      │   ├─ StatusChip
      │   ├─ EffectiveStatusChips
      │   ├─ BatchReadinessPill
      │   ├─ MismatchBadge
      │   └─ PlanningNodeTypeIcon
      ├─ Planning-local components (not extracted)
      │   ├─ LineageRow (planning-specific)
      │   └─ castPlanningStatus (planning utility)
      └─ Index exports for re-use
```

**PCP-706 Checklist**:
- [ ] Create `components/shared/` directory
- [ ] Create `components/shared/PlanningMetadata.tsx`
- [ ] Add re-exports from @miethe/ui (after PCP-709 extraction completes)
- [ ] Add local planning components not eligible for extraction
- [ ] Update all planning imports to use `@/shared/PlanningMetadata` instead of `@/Planning/primitives`
- [ ] Update ProjectBoard imports to use shared layer

---

## Column/List Reuse Plan for PCP-702

**Goal**: Identify exact ProjectBoard column/list primitives that PlanningHomePage should reuse for active-plans and planned-features columns.

**Current Usage**:
- **ProjectBoard.tsx** (line 1+): Feature list rendered as Kanban columns with cards
- Imports `EffectiveStatusChips`, `MismatchBadge`, `PlanningNodeTypeIcon` from Planning/primitives (line 33)

**Proposed Column Renderers for PlanningHomePage**:

1. **Active Plans Column**
   - Source: ProjectBoard FeatureCard component
   - Render: List of features with status + badge
   - Metadata: EffectiveStatusChips, MismatchBadge
   - **Reuse**: Extract a generic `FeatureListCard` component to @miethe/ui if pattern repeats

2. **Planned Features Column**
   - Source: ProjectBoard feature list rendering
   - Render: Grouped by phase, status chips per feature
   - Metadata: PlanningNodeTypeIcon, StatusChip
   - **Reuse**: Same FeatureListCard component

**Specific File References**:
- ProjectBoard feature list rendering: `components/ProjectBoard.tsx` (lines 150–400, estimated)
- Card component: Part of feature card section (uses SessionCard, EffectiveStatusChips, MismatchBadge)

**Recommendation**:
Extract a generic `FeatureListCard` component to @miethe/ui after PCP-709 completes, if PlanningHomePage reuse confirms the pattern is stable.

---

## Risks & Open Questions

### Blockers

1. **PlanningNodeTypeIcon Test Coverage Gap**
   - **Status**: Blocker for extraction
   - **Action**: Add unit test to `__tests__/planningNodeTypeIcon.test.tsx` before PCP-709 extraction
   - **Test Scope**: Cover all 7 node types (design_spec, prd, implementation_plan, progress, context, tracker, report) + default case

2. **LineageRow Design Decision**
   - **Question**: Should LineageRow be generalized as a planning-specific row renderer or refactored into a generic component?
   - **Recommendation**: Keep local for now; refactor if similar patterns emerge in other domains (PCP-708+)
   - **Decision**: PCP-706 scoping; not for PCP-709

3. **PhaseOperationsPanel Service Coupling**
   - **Status**: Current design requires service coupling to planning APIs
   - **Option A**: Extract sub-components (PhaseOperationsContent, PhaseOperationsBatchSection) first; leave panel local
   - **Option B**: Refactor panel to accept data props (major effort); extract as data-driven component
   - **Recommendation**: Option A for PCP-709; plan Option B refactor for PCP-710+

### Phase 6 Validation Gates (Remain Satisfied)

- ✓ All 5 extract candidates have >80% test coverage (StatusChip: 56 lines; EffectiveStatusChips: 71 lines; MismatchBadge: 79 lines; BatchReadinessPill: 83 lines; variants: tested)
- ✓ No breaking changes to exported primitives from `components/Planning/primitives/index.ts`
- ✓ Design system token alignment verified (all use Tailwind design-system colors)
- ✓ Accessibility: No WCAG violations in audited components; semantic HTML in use

### Open Questions

1. **@miethe/ui Color Token Alignment**
   - Question: Are Tailwind tokens (slate-700, emerald-600, amber-600, rose-600) the same as @miethe/ui's design system tokens?
   - Recommendation: Verify token mapping before PCP-709 extraction; may require tailwind.config.ts sync

2. **Storybook Stories**
   - Question: Should extraction include Storybook stories or defer story creation to PCP-710?
   - Recommendation: Defer stories to PCP-710 for efficiency; focus PCP-709 on code extraction + tests + docs

3. **Versioning & npm Publishing**
   - Question: Should PCP-709 include npm version bump and publish, or is it manual post-extraction?
   - Recommendation: Include in PCP-709 scope; publish to npm with semver minor bump

4. **Temporary Duplication Risk**
   - Question: During extraction (before CCDash updates to imported version), should we maintain both copies to avoid breakage?
   - Recommendation: No; PCP-709 should include atomic replacement (extract → publish → update imports → remove local copy) to avoid divergence

---

## Implementation Checklist for PCP-709

- [ ] **Phase 1**: Extract StatusChip + variants.ts
  - [ ] Copy to @miethe/ui/src/primitives/StatusChip.tsx
  - [ ] Add story (defer to PCP-710 if time-constrained)
  - [ ] Update @miethe/ui/src/primitives/index.ts
  - [ ] Run tests in @miethe/ui context
  - [ ] Publish npm version (semver minor bump)

- [ ] **Phase 2**: Extract EffectiveStatusChips
  - [ ] Copy to @miethe/ui/src/primitives/EffectiveStatusChips.tsx
  - [ ] Update internal import to use @miethe/ui StatusChip
  - [ ] Add story
  - [ ] Update index.ts
  - [ ] Test + publish

- [ ] **Phase 2**: Extract BatchReadinessPill
  - [ ] Copy to @miethe/ui/src/primitives/BatchReadinessPill.tsx
  - [ ] Update internal imports (StatusChip, readinessVariant)
  - [ ] Add story
  - [ ] Test + publish

- [ ] **Phase 2**: Extract MismatchBadge
  - [ ] Copy to @miethe/ui/src/primitives/MismatchBadge.tsx
  - [ ] Verify lucide icon dependency (already in @miethe/ui)
  - [ ] Add story
  - [ ] Test + publish

- [ ] **Phase 3**: Extract PlanningNodeTypeIcon
  - [ ] **Prerequisite**: Add `__tests__/planningNodeTypeIcon.test.tsx` with 7+ node type coverage
  - [ ] Copy to @miethe/ui/src/primitives/PlanningNodeTypeIcon.tsx
  - [ ] Add story
  - [ ] Refactor PlanningGraphPanel to import (instead of duplicate logic)
  - [ ] Test + publish

- [ ] **Update CCDash Imports** (after all @miethe/ui exports are live)
  - [ ] Update `components/Planning/primitives/index.ts` to re-export from @miethe/ui
  - [ ] Verify ProjectBoard imports still resolve
  - [ ] Remove local component files

- [ ] **Verify Phase 6 Gates Still Satisfied**
  - [ ] All tests pass in CCDash context (using @miethe/ui imports)
  - [ ] No regressions in Planning pages
  - [ ] Type safety maintained

---

## Success Criteria

- ✓ 5 high-value primitives extracted to @miethe/ui (StatusChip, EffectiveStatusChips, BatchReadinessPill, MismatchBadge, PlanningNodeTypeIcon)
- ✓ @miethe/ui exports published and available in npm
- ✓ CCDash updated to import from @miethe/ui; local duplicates removed
- ✓ All tests passing in both @miethe/ui and CCDash
- ✓ Phase 6 validation gates remain satisfied (test coverage, design system alignment, no breaking changes)
- ✓ Zero regressions in PlanningHomePage, PlanningGraphPanel, ProjectBoard
- ✓ PCP-706 consolidation roadmap ready for Phase 7 follow-up

---

**Manifest Created**: 2026-04-17
**Last Updated**: 2026-04-17
**Next Phase**: PCP-709 execution (extraction), PCP-706 consolidation (shared layer), PCP-702 column reuse

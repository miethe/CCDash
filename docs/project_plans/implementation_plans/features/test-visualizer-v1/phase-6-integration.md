---
title: "Phase 6: Page & Tab Integration - Test Visualizer"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-02-28
updated: 2026-02-28
feature_slug: "test-visualizer"
feature_version: "v1"
phase: 6
phase_title: "Page & Tab Integration"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/test-visualizer-v1.md
effort_estimate: "16 story points"
duration: "1 week"
assigned_subagents: [ui-engineer-enhanced, frontend-developer]
entry_criteria:
  - Phase 5 complete: all core UI components exist and are functional
  - Phase 3 complete: all API endpoints functional
  - Design specs from Phase 4 finalized
exit_criteria:
  - Testing Page (/tests route) renders domain hierarchy and drilldown
  - Feature Modal has "Test Status" tab (visible only when tests mapped)
  - Execution Page has "Test Status" tab with live/historical toggle
  - Session Page has "Test Status" tab with modified-tests section
  - Layout.tsx sidebar nav includes "Testing" NavItem
  - SidebarFilters portal renders test filters on Testing Page
  - All 4 entry points share TestStatusView components
  - Live polling works on active sessions
tags: [implementation, frontend, test-visualizer, routing, integration, tabs]
---

# Phase 6: Page & Tab Integration

**Parent Plan**: [Test Visualizer Implementation Plan](../test-visualizer-v1.md)
**Effort**: 16 story points | **Duration**: 1 week
**Assigned Subagents**: ui-engineer-enhanced, frontend-developer

---

## Overview

This phase wires the core components from Phase 5 into the four entry points defined in the PRD. The work is primarily integration: creating the Testing Page, adding three new tabs to existing pages, updating routing, and handling the sidebar portal. No new components are built in this phase — only composition of Phase 5 components.

Key constraint: existing tab patterns must be followed exactly to avoid regressions. The existing `WorkbenchTab`, `FeatureModalTab`, and session inspector tab types must be extended, not replaced.

---

## Testing Page (`/tests`)

### File: `components/TestVisualizer/TestingPage.tsx`

New standalone page component registered at route `/tests`.

**Component structure:**

```typescript
export const TestingPage: React.FC = () => {
  const { activeProject } = useData();
  const [selectedDomainId, setSelectedDomainId] = useState<string | null>(null);
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(null);
  const [selectedTestId, setSelectedTestId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<TestStatus[]>([]);
  const [searchQuery, setSearchQuery] = useState('');

  // Breadcrumb: "Testing > Domain A > Auth > Login Feature"
  const breadcrumb = useMemo(() => buildBreadcrumb(selectedDomainId, selectedFeatureId), [...]);

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Test Visualizer</h1>
          <p className="text-slate-400 text-sm">{breadcrumb}</p>
        </div>
        <GlobalHealthSummary projectId={activeProject.id} />
      </div>

      {/* Main split layout */}
      <div className="flex gap-4 flex-1 min-h-0">
        {/* Left: Domain Tree */}
        <aside className="w-72 shrink-0 bg-slate-900 border border-slate-800 rounded-xl p-4 overflow-y-auto">
          <DomainTreeView
            projectId={activeProject.id}
            selectedDomainId={selectedDomainId}
            onSelect={setSelectedDomainId}
          />
        </aside>

        {/* Right: Detail Panel */}
        <div className="flex-1 min-w-0 flex flex-col gap-4">
          <TestStatusView
            projectId={activeProject.id}
            filter={{
              domainId: selectedDomainId ?? undefined,
              featureId: selectedFeatureId ?? undefined,
            }}
            mode="full"
            onNavigateToTestingPage={undefined}
          />
        </div>
      </div>

      {/* Sidebar Portal: Filters */}
      <SidebarFiltersPortal>
        <TestFilters
          statusFilter={statusFilter}
          onStatusChange={setStatusFilter}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
        />
      </SidebarFiltersPortal>
    </div>
  );
};
```

### Global Health Summary (page header)

```typescript
// Small component showing overall stats in the page header
const GlobalHealthSummary: React.FC<{ projectId: string }> = ({ projectId }) => {
  const { domains } = useTestStatus(projectId);
  const totals = useMemo(() => aggregateDomainTotals(domains), [domains]);

  return (
    <div className="flex items-center gap-4 text-sm">
      <HealthGauge passRate={totals.passRate} size="sm" />
      <div className="text-slate-400">
        <span className="text-emerald-400 font-medium">{totals.passed}</span> passing
        {' • '}
        <span className="text-rose-400 font-medium">{totals.failed}</span> failing
        {' • '}
        <span className="text-slate-300">{totals.total}</span> total
      </div>
      <button onClick={refresh} className="...">
        <RefreshCw size={14} />
      </button>
    </div>
  );
};
```

### Sidebar Filters Portal

The existing `#sidebar-portal` div in `Layout.tsx` accepts injected content via React Portal:

```typescript
// Pattern already exists for other pages; replicate it
const TestFilters: React.FC<TestFiltersProps> = ({ statusFilter, onStatusChange, ... }) => {
  const portalEl = document.getElementById('sidebar-portal');
  if (!portalEl) return null;

  return createPortal(
    <div className="space-y-4">
      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Test Filters</h3>
      {/* Status checkboxes */}
      {/* Run date filter */}
      {/* Branch filter */}
    </div>,
    portalEl
  );
};
```

---

## App.tsx Route Addition

```typescript
// Add import:
import { TestingPage } from './components/TestVisualizer/TestingPage';

// Add route in Routes:
<Route path="/tests" element={<TestingPage />} />
```

---

## Layout.tsx Nav Item

Add "Testing" nav item using `TestTube2` icon from Lucide:

```typescript
// Import:
import { TestTube2 } from 'lucide-react';

// In nav:
<NavItem
  to="/tests"
  icon={TestTube2}
  label="Testing"
  active={location.pathname === '/tests'}
  isCollapsed={isCollapsed}
/>
```

Position: after "Execution" (Command icon), before "Documents" (FileText icon).

---

## Execution Page "Test Status" Tab

### File: `components/FeatureExecutionWorkbench.tsx`

**Step 1: Extend `WorkbenchTab` union type**

```typescript
// Before:
type WorkbenchTab = 'overview' | 'phases' | 'documents' | 'sessions' | 'artifacts' | 'history' | 'analytics';

// After:
type WorkbenchTab = 'overview' | 'phases' | 'documents' | 'sessions' | 'artifacts' | 'history' | 'analytics' | 'test-status';
```

**Step 2: Add to `TAB_ITEMS` array**

```typescript
// Add after 'analytics' entry:
{ id: 'test-status', label: 'Test Status', icon: TestTube2 },
```

**Step 3: Add conditional render in tab content**

```typescript
{activeTab === 'test-status' && selectedFeature && (
  <TestStatusView
    projectId={activeProject.id}
    filter={{ featureId: selectedFeature.id }}
    mode="tab"
    isLive={isSessionActive}
    onNavigateToTestingPage={() => navigate(`/tests?featureId=${selectedFeature.id}`)}
  />
)}
```

**Live indicator logic:**

```typescript
// Derive isSessionActive from the feature's linked sessions
const isSessionActive = useMemo(
  () => executionContext?.sessions?.some(s => s.status === 'running') ?? false,
  [executionContext]
);
```

---

## Session Page "Test Status" Tab

### File: `components/SessionInspector.tsx`

Find existing tab union type in `SessionInspector`. The exact name requires checking the file, but the pattern is:

**Step 1: Extend session tab union type** (add `'test-status'`)

**Step 2: Add to session TAB_ITEMS array**

```typescript
{ id: 'test-status', label: 'Test Status', icon: TestTube2 },
```

**Step 3: Add conditional render**

```typescript
{activeTab === 'test-status' && selectedSession && (
  <SessionTestStatusView
    projectId={activeProject.id}
    sessionId={selectedSession.id}
    sessionStatus={selectedSession.status}
    sessionFileUpdates={selectedSession.fileUpdates}
  />
)}
```

**`SessionTestStatusView` component:**

This is a thin wrapper around `TestStatusView` that adds the "Modified tests during this session" section:

```typescript
const SessionTestStatusView: React.FC<SessionTestStatusViewProps> = ({
  projectId, sessionId, sessionStatus, sessionFileUpdates,
}) => {
  // Derive test files modified during session from sessionFileUpdates
  const modifiedTestFiles = useMemo(
    () => sessionFileUpdates?.filter(f => isTestFile(f.filePath)) ?? [],
    [sessionFileUpdates]
  );

  const isLive = sessionStatus === 'running';

  return (
    <div className="flex flex-col gap-4">
      {/* Modified tests section - unique to session view */}
      {modifiedTestFiles.length > 0 && (
        <ModifiedTestsSection files={modifiedTestFiles} sessionId={sessionId} />
      )}

      {/* Standard test status view filtered to session */}
      <TestStatusView
        projectId={projectId}
        filter={{ sessionId }}
        mode="tab"
        isLive={isLive}
        onNavigateToTestingPage={() => {/* navigate to /tests?sessionId= */}}
      />
    </div>
  );
};
```

**`isTestFile()` helper:**

```typescript
const TEST_FILE_PATTERNS = [
  /test_.*\.py$/,
  /.*_test\.py$/,
  /.*\.test\.(ts|tsx|js|jsx)$/,
  /.*\.spec\.(ts|tsx|js|jsx)$/,
  /tests?\//,
];

function isTestFile(path: string): boolean {
  return TEST_FILE_PATTERNS.some(pattern => pattern.test(path));
}
```

---

## Feature Modal "Test Status" Tab

### File: `components/ProjectBoard.tsx`

The Feature Modal uses `FeatureModalTab` union type. Find existing modal tab implementation and:

**Step 1: Extend `FeatureModalTab` union** (add `'test-status'`)

**Step 2: Add to modal TAB_ITEMS array** (only if feature has test health data)

```typescript
// Conditionally include tab:
const modalTabs = useMemo(() => {
  const base: FeatureModalTab[] = ['overview', 'phases', 'docs', 'sessions', 'history'];
  if (featureTestHealth?.totalTests > 0) {
    base.push('test-status');
  }
  return base;
}, [featureTestHealth]);
```

**Step 3: Fetch test health for modal feature**

```typescript
// In FeatureModal component:
const [featureTestHealth, setFeatureTestHealth] = useState<FeatureTestHealth | null>(null);

useEffect(() => {
  if (!feature) return;
  getFeatureHealth(projectId, { featureId: feature.id })
    .then(result => setFeatureTestHealth(result.items[0] ?? null))
    .catch(() => setFeatureTestHealth(null));
}, [feature?.id, projectId]);
```

**Step 4: Tab content**

```typescript
{activeModalTab === 'test-status' && featureTestHealth && (
  <FeatureModalTestStatus
    projectId={projectId}
    featureId={feature.id}
    health={featureTestHealth}
    onNavigateToExecution={() => {
      onClose();
      navigate(`/execution?featureId=${feature.id}&tab=test-status`);
    }}
  />
)}
```

**`FeatureModalTestStatus` component:** Compact view (~4 data points + link to Execution Page):

```typescript
const FeatureModalTestStatus: React.FC<{...}> = ({ projectId, featureId, health, onNavigateToExecution }) => (
  <div className="space-y-4">
    <div className="flex items-center gap-4">
      <HealthGauge passRate={health.passRate} integrityScore={health.integrityScore} size="md" />
      <HealthSummaryBar passed={health.passed} failed={health.failed} skipped={health.skipped} total={health.totalTests} />
    </div>
    {health.openSignals > 0 && (
      <p className="text-amber-400 text-sm">
        {health.openSignals} integrity alert{health.openSignals > 1 ? 's' : ''}
      </p>
    )}
    <button onClick={onNavigateToExecution} className="text-indigo-400 text-sm hover:underline flex items-center gap-1">
      View full test status <ExternalLink size={12} />
    </button>
  </div>
);
```

---

## Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------------|---------------------|--------------|
| INT-1 | App.tsx + Layout.tsx | Add `/tests` route to App.tsx. Add "Testing" NavItem to Layout.tsx (after Execution, before Documents). Use TestTube2 icon. | Route renders TestingPage. NavItem is active when path is /tests. Collapsed sidebar shows tooltip. | 1 | frontend-developer | Phase 5 complete |
| INT-2 | TestingPage implementation | Implement `components/TestVisualizer/TestingPage.tsx`. Split layout: DomainTreeView left sidebar, TestStatusView right panel. Global health header. Breadcrumb navigation. URL-synced selection state. | Page renders. Domain tree click updates detail panel. URL search params sync selection (featureId, domainId). | 4 | ui-engineer-enhanced | INT-1 |
| INT-3 | Sidebar filters portal | Implement `TestFilters` component rendering into `#sidebar-portal`. Status checkboxes, search input, run date filter. Apply filter to TestStatusView. | Filters render in sidebar portal. Status filter changes update result table. Search debounced 300ms. | 2 | frontend-developer | INT-2 |
| INT-4 | Execution Page tab | Extend `WorkbenchTab` type, add to `TAB_ITEMS`, add conditional render. Live/historical state. Derive `isSessionActive`. Show LIVE badge when active session. | Tab appears in Execution Workbench. Live badge shows when session running. Results update on 30s poll when live. | 3 | ui-engineer-enhanced | Phase 5 |
| INT-5 | Session Page tab | Extend session tab type, add to tab items, add conditional render. Implement `SessionTestStatusView` with modified-tests section. `isTestFile()` helper. | Tab appears in SessionInspector. Modified test files section shows only test files from session_file_updates. | 3 | ui-engineer-enhanced | Phase 5 |
| INT-6 | Feature Modal tab | Extend `FeatureModalTab` type. Conditional tab inclusion based on test health data. Implement `FeatureModalTestStatus` compact view. Fetch test health on modal open. | Tab appears in feature modal only when feature has test data. Health gauge and summary bar render. Link to Execution Page tab works. | 2 | frontend-developer | Phase 5 |
| INT-7 | URL state management | Add URL search param syncing for TestingPage: `?domainId=`, `?featureId=`, `?runId=`. Deep links work from correlate response `links` object. | Navigate to `/#/tests?featureId=my-feature` opens page with feature pre-selected. Back button restores previous selection. | 1 | frontend-developer | INT-2 |

---

## Quality Gates

- [ ] All 4 entry points render without errors
- [ ] `/tests` route resolves and TestingPage renders
- [ ] Domain tree click selects domain and updates detail panel
- [ ] TestingPage URL params (`?featureId=`, `?domainId=`) pre-select on load
- [ ] Execution Page "Test Status" tab appears only when feature has test runs
- [ ] Session Page "Test Status" tab shows modified test files correctly
- [ ] Feature Modal "Test Status" tab is hidden when feature has no test data
- [ ] Live badge appears and polling starts when session.status === 'running'
- [ ] Sidebar filter portal renders filters when on /tests route, disappears on other routes
- [ ] No existing functionality broken (all existing tabs still work)
- [ ] TestTube2 icon appears in sidebar nav between Execution and Documents

---

## Key Files Created / Modified

| File | Action | Notes |
|------|--------|-------|
| `App.tsx` | Modified | Add `/tests` route |
| `components/Layout.tsx` | Modified | Add TestTube2 NavItem |
| `components/TestVisualizer/TestingPage.tsx` | Created | Full Testing Page |
| `components/FeatureExecutionWorkbench.tsx` | Modified | Add 'test-status' to WorkbenchTab, TAB_ITEMS, and render |
| `components/SessionInspector.tsx` | Modified | Add 'test-status' tab |
| `components/ProjectBoard.tsx` | Modified | Add 'test-status' to FeatureModalTab, conditional inclusion |
| `components/TestVisualizer/SessionTestStatusView.tsx` | Created | Session-scoped wrapper with modified-tests section |
| `components/TestVisualizer/FeatureModalTestStatus.tsx` | Created | Compact modal tab view |
| `components/TestVisualizer/TestFilters.tsx` | Created | Sidebar portal filter panel |

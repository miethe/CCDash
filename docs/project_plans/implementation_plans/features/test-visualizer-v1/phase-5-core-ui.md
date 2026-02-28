---
title: "Phase 5: Core UI Components - Test Visualizer"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-02-28
updated: 2026-02-28
feature_slug: "test-visualizer"
feature_version: "v1"
phase: 5
phase_title: "Core UI Components"
prd_ref: /docs/project_plans/PRDs/features/test-visualizer-v1.md
plan_ref: /docs/project_plans/implementation_plans/features/test-visualizer-v1.md
effort_estimate: "18 story points"
duration: "1.5 weeks"
assigned_subagents: [ui-engineer-enhanced, frontend-developer]
entry_criteria:
  - Phase 3 complete: all API endpoints functional
  - Phase 4 complete: design specs for all components
  - Design system spec reviewed
exit_criteria:
  - All TypeScript interfaces added to types.ts
  - Frontend service (services/testVisualizer.ts) implemented for all 9 endpoints
  - All 8 core components implemented and individually functional
  - Custom hooks: useTestStatus, useTestRuns, useLiveTestUpdates
  - Components tested manually against live API
  - Feature flag check in service (returns null/empty when disabled)
tags: [implementation, frontend, test-visualizer, react, typescript, components]
---

# Phase 5: Core UI Components

**Parent Plan**: [Test Visualizer Implementation Plan](../test-visualizer-v1.md)
**Effort**: 18 story points | **Duration**: 1.5 weeks
**Assigned Subagents**: ui-engineer-enhanced, frontend-developer

---

## Overview

This phase builds all shared frontend infrastructure for the Test Visualizer: TypeScript types, the API service layer, eight reusable React components, and three custom hooks. All work lives in the `components/TestVisualizer/` directory and `services/testVisualizer.ts`. The components are designed to be composable — the same components used in the dedicated Testing Page (Phase 6) are reused in the Feature Modal, Execution Page, and Session Page tabs.

All components follow CCDash conventions:
- Functional components with TypeScript props
- Tailwind CSS only (no inline styles)
- Slate dark theme with indigo accents
- Lucide React for icons
- `useCallback` / `useMemo` for performance where data-heavy

---

## TypeScript Types

Add to `types.ts`:

```typescript
// ── Test Visualizer Types ──────────────────────────────────────────

export type TestStatus =
  | 'passed'
  | 'failed'
  | 'skipped'
  | 'error'
  | 'xfailed'
  | 'xpassed'
  | 'unknown'
  | 'running';

export interface TestRun {
  runId: string;
  projectId: string;
  timestamp: string;
  gitSha: string;
  branch: string;
  agentSessionId: string;
  envFingerprint: string;
  trigger: 'local' | 'ci';
  status: 'running' | 'complete' | 'failed';
  totalTests: number;
  passedTests: number;
  failedTests: number;
  skippedTests: number;
  durationMs: number;
  metadata: Record<string, unknown>;
  createdAt: string;
}

export interface TestDefinition {
  testId: string;
  projectId: string;
  path: string;
  name: string;
  framework: string;
  tags: string[];
  owner: string;
  createdAt: string;
  updatedAt: string;
}

export interface TestResult {
  runId: string;
  testId: string;
  status: TestStatus;
  durationMs: number;
  errorFingerprint: string;
  errorMessage: string;
  artifactRefs: string[];
  stdoutRef: string;
  stderrRef: string;
  createdAt: string;
}

export interface TestDomain {
  domainId: string;
  projectId: string;
  name: string;
  parentId: string | null;
  description: string;
  tier: 'core' | 'extras' | 'nonfunc';
  sortOrder: number;
}

export interface TestFeatureMapping {
  mappingId: number;
  projectId: string;
  testId: string;
  featureId: string;
  domainId: string | null;
  providerSource: string;
  confidence: number;
  isPrimary: boolean;
  createdAt: string;
}

export interface TestIntegritySignal {
  signalId: string;
  projectId: string;
  gitSha: string;
  filePath: string;
  testId: string | null;
  signalType:
    | 'assertion_removed'
    | 'skip_introduced'
    | 'xfail_added'
    | 'broad_exception'
    | 'edited_before_green';
  severity: 'low' | 'medium' | 'high';
  details: Record<string, unknown>;
  linkedRunIds: string[];
  agentSessionId: string;
  createdAt: string;
}

export interface DomainHealthRollup {
  domainId: string;
  domainName: string;
  tier: 'core' | 'extras' | 'nonfunc';
  totalTests: number;
  passed: number;
  failed: number;
  skipped: number;
  passRate: number;
  integrityScore: number;
  lastRunAt: string | null;
  children: DomainHealthRollup[];
}

export interface FeatureTestHealth {
  featureId: string;
  featureName: string;
  domainId: string | null;
  totalTests: number;
  passed: number;
  failed: number;
  skipped: number;
  passRate: number;
  integrityScore: number;
  lastRunAt: string | null;
  openSignals: number;
}

export interface TestTimelinePoint {
  date: string;
  passRate: number;
  passed: number;
  failed: number;
  skipped: number;
  runIds: string[];
  signals: TestIntegritySignal[];
}

export interface FeatureTestTimeline {
  featureId: string;
  featureName: string;
  timeline: TestTimelinePoint[];
  firstGreen: string | null;
  lastRed: string | null;
  lastKnownGood: string | null;
}
```

---

## Frontend Service

`services/testVisualizer.ts` — all API calls, returning typed data:

```typescript
// services/testVisualizer.ts

const BASE = '/api/tests';

export interface TestRunsFilter {
  projectId: string;
  agentSessionId?: string;
  featureId?: string;
  gitSha?: string;
  since?: string;
  cursor?: string;
  limit?: number;
}

export async function getDomainHealth(
  projectId: string,
  since?: string
): Promise<DomainHealthRollup[]>

export async function getFeatureHealth(
  projectId: string,
  options?: { domainId?: string; since?: string; cursor?: string; limit?: number }
): Promise<{ items: FeatureTestHealth[]; nextCursor: string | null; total: number }>

export async function getTestRun(runId: string, projectId: string): Promise<{
  run: TestRun;
  results: TestResult[];
  definitions: Record<string, TestDefinition>;
  integritySignals: TestIntegritySignal[];
}>

export async function listTestRuns(
  filter: TestRunsFilter
): Promise<{ items: TestRun[]; nextCursor: string | null; total: number }>

export async function getTestHistory(
  testId: string,
  projectId: string,
  options?: { limit?: number; since?: string; cursor?: string }
): Promise<{ items: TestResult[]; nextCursor: string | null; total: number }>

export async function getFeatureTimeline(
  featureId: string,
  projectId: string,
  options?: { since?: string; until?: string; includeSignals?: boolean }
): Promise<FeatureTestTimeline>

export async function getIntegrityAlerts(
  projectId: string,
  options?: {
    since?: string;
    signalType?: string;
    severity?: string;
    agentSessionId?: string;
    cursor?: string;
    limit?: number;
  }
): Promise<{ items: TestIntegritySignal[]; nextCursor: string | null; total: number }>

export async function correlateRun(
  runId: string,
  projectId: string
): Promise<{
  run: TestRun;
  agentSession: AgentSession | null;
  features: FeatureTestHealth[];
  integritySignals: TestIntegritySignal[];
  links: Record<string, string>;
}>
```

Service functions:
- Throw `Error` on non-2xx HTTP responses (with `message` from response body)
- Return `null` / empty arrays gracefully when feature flag is disabled (503 response)
- Use `camelCase` conversion for all API responses (snake_case -> camelCase)

---

## Custom Hooks

### `useTestStatus(projectId, options?)`

Fetches domain health rollup. Refreshes on `CCDASH_LIVE_TEST_UPDATES_ENABLED` interval (60s).

```typescript
interface UseTestStatusOptions {
  since?: string;
  pollingInterval?: number; // ms, default 60000
  enabled?: boolean;
}

interface UseTestStatusResult {
  domains: DomainHealthRollup[];
  isLoading: boolean;
  error: Error | null;
  lastFetchedAt: Date | null;
  refresh: () => void;
}

export function useTestStatus(
  projectId: string,
  options?: UseTestStatusOptions
): UseTestStatusResult
```

### `useTestRuns(projectId, filter)`

Paginated runs list with `loadMore` support.

```typescript
interface UseTestRunsResult {
  runs: TestRun[];
  isLoading: boolean;
  hasMore: boolean;
  loadMore: () => void;
  error: Error | null;
}

export function useTestRuns(
  projectId: string,
  filter?: Omit<TestRunsFilter, 'projectId'>
): UseTestRunsResult
```

### `useLiveTestUpdates(projectId, runId?, featureId?, sessionId?)`

Manages polling for live updates during active sessions. Returns latest run data.

```typescript
interface UseLiveTestUpdatesOptions {
  pollingInterval?: number; // ms, default 30000
  enabled?: boolean; // enable only when session is active
}

interface UseLiveTestUpdatesResult {
  latestRun: TestRun | null;
  isLive: boolean;
  lastUpdated: Date | null;
  error: Error | null;
}

export function useLiveTestUpdates(
  projectId: string,
  filter?: { runId?: string; featureId?: string; sessionId?: string },
  options?: UseLiveTestUpdatesOptions
): UseLiveTestUpdatesResult
```

---

## Component Implementations

### `components/TestVisualizer/TestStatusBadge.tsx`

```typescript
interface TestStatusBadgeProps {
  status: TestStatus;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

// Status -> { icon: LucideIcon, colorClass: string, label: string }
const STATUS_CONFIG: Record<TestStatus, StatusConfig> = {
  passed: { icon: CheckCircle2, colorClass: 'text-emerald-500', label: 'Passing' },
  failed: { icon: XCircle, colorClass: 'text-rose-500', label: 'Failing' },
  skipped: { icon: MinusCircle, colorClass: 'text-amber-500', label: 'Skipped' },
  error: { icon: AlertCircle, colorClass: 'text-rose-600', label: 'Error' },
  xfailed: { icon: AlertTriangle, colorClass: 'text-amber-400', label: 'XFail' },
  xpassed: { icon: AlertTriangle, colorClass: 'text-rose-400', label: 'XPass' },
  unknown: { icon: HelpCircle, colorClass: 'text-slate-500', label: 'Unknown' },
  running: { icon: Loader2, colorClass: 'text-indigo-400', label: 'Running', spin: true },
};
```

### `components/TestVisualizer/HealthGauge.tsx`

Circular SVG progress ring. Derived from pass_rate * integrity_score.

```typescript
interface HealthGaugeProps {
  passRate: number;      // 0-1
  integrityScore?: number; // 0-1, default 1
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
}
```

### `components/TestVisualizer/HealthSummaryBar.tsx`

Stacked horizontal bar: emerald/rose/amber segments.

### `components/TestVisualizer/TestStatusBadge.tsx`

Icon + color + optional label. All 8 status types.

### `components/TestVisualizer/TestRunCard.tsx`

Compact card: run_id chip + timestamp + pass/fail/skip counts + optional session link.

### `components/TestVisualizer/TestResultTable.tsx`

Sortable table with: test name, status badge, duration, error preview. Expandable rows for full error. Filtering by status.

### `components/TestVisualizer/DomainTreeView.tsx`

Recursive tree. Collapsible nodes. Health badge per node. Keyboard navigable.

### `components/TestVisualizer/IntegrityAlertCard.tsx`

Card with severity left-border. Signal type badge, git_sha chip, file_path, timestamp. Expandable details.

### `components/TestVisualizer/TestTimeline.tsx`

Line chart for pass_rate over time. Signal markers. Annotations for first_green, last_red. Uses existing chart library pattern from AnalyticsDashboard.

### `components/TestVisualizer/TestStatusView.tsx`

Composite view assembling multiple sub-components. Accepts `filter` prop: `{ featureId?, sessionId?, domainId?, runId? }`. This is the shared view used in all tabs and the Testing Page.

```typescript
interface TestStatusViewProps {
  projectId: string;
  filter?: {
    featureId?: string;
    sessionId?: string;
    domainId?: string;
    runId?: string;
  };
  mode: 'full' | 'compact' | 'tab';
  isLive?: boolean; // true when linked session is active
  onNavigateToTestingPage?: () => void;
}
```

---

## Task Breakdown

| Task ID | Task Name | Description | Acceptance Criteria | Estimate (pts) | Assigned Subagent(s) | Dependencies |
|---------|-----------|-------------|---------------------|----------------|---------------------|--------------|
| UI-1 | TypeScript types | Add all test-related interfaces to `types.ts`: TestStatus, TestRun, TestDefinition, TestResult, TestDomain, TestFeatureMapping, TestIntegritySignal, DomainHealthRollup, FeatureTestHealth, TestTimelinePoint, FeatureTestTimeline. | All types compile without errors. No `any` types used. Consistent with backend DTOs. | 2 | ui-engineer-enhanced | Phase 3 DTOs |
| UI-2 | Frontend service | Implement all 8 API functions in `services/testVisualizer.ts`. Handle snake_case -> camelCase conversion. Return typed data. Graceful 503 handling (return null/empty). | All 8 functions implemented. Type-safe return values. Unit tests for camelCase conversion. Error thrown on 4xx/5xx (except 503). | 3 | frontend-developer | UI-1, Phase 3 APIs |
| UI-3 | Custom hooks | Implement `useTestStatus`, `useTestRuns`, `useLiveTestUpdates`. Handle loading/error states. Cleanup on unmount. | Hooks correctly manage loading states. Polling cleans up on unmount. `useLiveTestUpdates` only polls when `enabled=true`. | 2 | ui-engineer-enhanced | UI-2 |
| UI-4 | TestStatusBadge + HealthSummaryBar | Implement smallest, most-reused components. All 8 status types. Accessibility (aria-label). 3 sizes for badge. | Renders all status types correctly. WCAG AA contrast ratios met. Storybook-style manual review done. | 2 | ui-engineer-enhanced | UI-1 |
| UI-5 | HealthGauge | Implement circular SVG progress ring. Color scale based on health score. Animated value transitions (300ms). | Renders 0%, 50%, 89%, 100% correctly. Color changes at thresholds. Smooth animation on value change. | 2 | ui-engineer-enhanced | UI-4 |
| UI-6 | TestRunCard + IntegrityAlertCard | Implement run summary card and integrity alert card. TestRunCard: session link, git_sha chip. IntegrityAlertCard: severity left-border, expandable details. | Both cards render with all props. Expandable state works. Links are valid HashRouter paths. | 2 | frontend-developer | UI-4 |
| UI-7 | TestResultTable | Implement sortable/filterable results table. Expandable rows. Loading skeleton. Empty state. | Sorts by status, duration, name. Filter by status works. Expandable error shows full error_message. Loading skeleton shows 5 rows. | 3 | ui-engineer-enhanced | UI-4 |
| UI-8 | DomainTreeView | Implement recursive tree. Collapsible nodes. Health badge per node. Keyboard nav (arrows + Enter). | Tree renders 3+ levels. Expand/collapse works. Keyboard nav works. Selected node highlighted with indigo border. | 2 | ui-engineer-enhanced | UI-4 |

---

## Quality Gates

- [ ] All TypeScript types compile without errors (`npx tsc --noEmit`)
- [ ] No `any` types in types.ts additions or component props
- [ ] All 8 API service functions return correctly typed data
- [ ] Service gracefully returns empty/null on 503 (feature disabled)
- [ ] All 8 components render without errors in isolation
- [ ] TestStatusBadge renders all 8 status types correctly
- [ ] DomainTreeView keyboard navigation works: arrow keys + Enter
- [ ] TestResultTable loading skeleton shows during fetch
- [ ] HealthGauge animates smoothly on value change
- [ ] `useLiveTestUpdates` cleans up polling interval on unmount (no memory leaks)
- [ ] All status colors meet WCAG AA contrast ratio on `bg-slate-900`

---

## Key Files Created / Modified

| File | Action | Notes |
|------|--------|-------|
| `types.ts` | Modified | ~100 lines of new test-related interfaces |
| `services/testVisualizer.ts` | Created | All 8 API functions, camelCase conversion |
| `components/TestVisualizer/TestStatusBadge.tsx` | Created | Status icon + color + label |
| `components/TestVisualizer/HealthGauge.tsx` | Created | Circular SVG progress ring |
| `components/TestVisualizer/HealthSummaryBar.tsx` | Created | Stacked horizontal bar |
| `components/TestVisualizer/TestRunCard.tsx` | Created | Run summary card |
| `components/TestVisualizer/TestResultTable.tsx` | Created | Results table with expandable rows |
| `components/TestVisualizer/DomainTreeView.tsx` | Created | Recursive collapsible tree |
| `components/TestVisualizer/IntegrityAlertCard.tsx` | Created | Alert card with severity styling |
| `components/TestVisualizer/TestTimeline.tsx` | Created | Line chart with signal markers |
| `components/TestVisualizer/TestStatusView.tsx` | Created | Composite shared view |
| `components/TestVisualizer/index.ts` | Created | Barrel export for all components |

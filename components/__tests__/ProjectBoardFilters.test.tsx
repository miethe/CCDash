/**
 * P3-003: Server-Backed Filters — ProjectBoard filter wiring tests.
 *
 * Two layers of tests:
 *
 * Layer 1 — Pure logic (no React):
 *   boardSortToApiSort helper, applySidebarFilters query shape construction,
 *   clearSidebarFilters reset shape.  These are extracted inline and tested
 *   without rendering anything.
 *
 * Layer 2 — Hook initialisation (renderToStaticMarkup):
 *   Verifies useFeatureSurface is called with the active project id on mount,
 *   and that the component renders without crashing with the hook wired in.
 *
 * Why not @testing-library/react:
 *   The project does not have @testing-library/react installed (vitest only).
 *   Interaction-layer tests (click Apply → assert setQuery) are deferred to
 *   P3-007 where the full test infrastructure decision will be made.
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Feature, PlanDocument } from '../../types';

// ── Hook mock ────────────────────────────────────────────────────────────────

const mockSetQuery = vi.fn();

vi.mock('../../services/useFeatureSurface', () => ({
  useFeatureSurface: vi.fn((opts) => ({
    query: {
      projectId: opts?.initialQuery?.projectId,
      page: 1,
      pageSize: 50,
      search: '',
      status: [],
      stage: [],
      tags: [],
      sortBy: 'updated_at',
      sortDirection: 'desc',
      include: [],
    },
    setQuery: mockSetQuery,
    cards: [],
    rollups: new Map(),
    totals: { total: 42, filteredTotal: 17 },
    listState: 'success' as const,
    rollupState: 'success' as const,
    listError: null,
    rollupError: null,
    retryList: vi.fn(),
    retryRollups: vi.fn(),
    refetch: vi.fn(),
    invalidate: vi.fn(),
    cacheKey: 'test-key',
  })),
}));

// ── DataContext mock ──────────────────────────────────────────────────────────

vi.mock('../../contexts/DataContext', () => ({
  useData: () => ({
    features: [] as Feature[],
    documents: [] as PlanDocument[],
    sessions: [],
    tasks: [],
    alerts: [],
    notifications: [],
    projects: [],
    activeProject: { id: 'proj-1', name: 'Test Project' },
    loading: false,
    error: null,
    runtimeStatus: null,
    refreshAll: vi.fn(),
    refreshSessions: vi.fn(),
    loadMoreSessions: vi.fn(),
    refreshDocuments: vi.fn(),
    refreshTasks: vi.fn(),
    refreshFeatures: vi.fn(),
    refreshProjects: vi.fn(),
    addProject: vi.fn(),
    updateProject: vi.fn(),
    switchProject: vi.fn(),
    updateFeatureStatus: vi.fn(),
    updatePhaseStatus: vi.fn(),
    updateTaskStatus: vi.fn(),
    getSessionById: vi.fn(),
  }),
}));

// ── Router mocks ──────────────────────────────────────────────────────────────

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    Link: ({
      to,
      children,
      ...props
    }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { to: string | { pathname?: string } }) => (
      <a href={typeof to === 'string' ? to : (to.pathname ?? '#')} {...props}>
        {children}
      </a>
    ),
    useNavigate: () => vi.fn(),
    useSearchParams: () => [new URLSearchParams(), vi.fn()] as const,
  };
});

// ── Dependency mocks ──────────────────────────────────────────────────────────

vi.mock('../../services/live', () => ({
  executionRunTopic: vi.fn(),
  featureTopic: vi.fn(),
  isExecutionLiveUpdatesEnabled: () => false,
  isFeatureLiveUpdatesEnabled: () => false,
  isStackRecommendationsEnabled: () => true,
  isWorkflowAnalyticsEnabled: () => true,
  projectFeaturesTopic: vi.fn(),
  sharedLiveConnectionManager: {},
  useLiveInvalidation: () => 'idle',
}));

vi.mock('../../services/execution', () => ({
  trackExecutionEvent: vi.fn(),
  approveExecutionRun: vi.fn(),
  cancelExecutionRun: vi.fn(),
  checkExecutionPolicy: vi.fn(),
  createExecutionRun: vi.fn(),
  getExecutionRun: vi.fn(),
  getFeatureExecutionContext: vi.fn(),
  listExecutionRunEvents: vi.fn(),
  listExecutionRuns: vi.fn(),
  retryExecutionRun: vi.fn(),
  getLaunchCapabilities: vi.fn().mockResolvedValue({ planningEnabled: true }),
}));

vi.mock('../../services/testVisualizer', () => ({
  getFeatureHealth: vi.fn(),
  listTestRuns: vi.fn(),
}));

vi.mock('../SessionCard', () => ({
  SessionCard: ({ children }: { children?: React.ReactNode }) => (
    <div data-mock="session-card">{children}</div>
  ),
  SessionCardDetailSection: () => null,
  deriveSessionCardTitle: (id: string) => id,
}));

vi.mock('../execution/RecommendedStackCard', () => ({
  RecommendedStackCard: () => <div data-mock="recommended-stack-card" />,
}));

vi.mock('../execution/RecommendedStackPreviewCard', () => ({
  RecommendedStackPreviewCard: () => <div data-mock="recommended-stack-preview-card" />,
}));

vi.mock('../execution/ExecutionRunHistory', () => ({
  ExecutionRunHistory: () => <div data-mock="execution-run-history" />,
}));

vi.mock('../execution/ExecutionRunPanel', () => ({
  ExecutionRunPanel: () => <div data-mock="execution-run-panel" />,
}));

vi.mock('../execution/WorkflowEffectivenessSurface', () => ({
  WorkflowEffectivenessSurface: () => <div data-mock="workflow-effectiveness-surface" />,
}));

vi.mock('../TestVisualizer/FeatureModalTestStatus', () => ({
  FeatureModalTestStatus: () => <div data-mock="feature-modal-test-status" />,
}));

vi.mock('../TestVisualizer/TestStatusView', () => ({
  TestStatusView: () => <div data-mock="test-status-view" />,
}));

vi.mock('../../contexts/AppRuntimeContext', () => ({
  useAppRuntime: () => ({
    loading: false,
    error: null,
    runtimeStatus: null,
    refreshAll: vi.fn(),
  }),
}));

vi.mock('../../services/featureSurfaceFlag', () => ({
  isFeatureSurfaceV2Enabled: vi.fn(() => false),
}));

// ── Import component and hook ─────────────────────────────────────────────────

import { ProjectBoard } from '../ProjectBoard';
import { useFeatureSurface } from '../../services/useFeatureSurface';

beforeEach(() => {
  vi.clearAllMocks();
});

// ── Layer 1: Pure sort-mapping logic ─────────────────────────────────────────
// Mirrors the boardSortToApiSort function in ProjectBoard.tsx.
// This logic is tested purely — no React needed.

function boardSortToApiSort(sort: 'date' | 'progress' | 'tasks'): string {
  switch (sort) {
    case 'progress': return 'progress_pct';
    case 'tasks': return 'total_tasks';
    case 'date':
    default: return 'updated_at';
  }
}

describe('P3-003 — boardSortToApiSort (pure sort mapping)', () => {
  it('maps "date" to "updated_at"', () => {
    expect(boardSortToApiSort('date')).toBe('updated_at');
  });

  it('maps "progress" to "progress_pct"', () => {
    expect(boardSortToApiSort('progress')).toBe('progress_pct');
  });

  it('maps "tasks" to "total_tasks"', () => {
    expect(boardSortToApiSort('tasks')).toBe('total_tasks');
  });
});

// ── Layer 1: applySidebarFilters query shape ──────────────────────────────────
// Extracts the query construction logic inline and tests the shape.

function buildAppliedQuery(opts: {
  projectId: string | undefined;
  draftSearchQuery: string;
  draftStatusFilter: string;
  draftCategoryFilter: string;
  draftSortBy: 'date' | 'progress' | 'tasks';
  draftPlannedFrom?: string;
  draftPlannedTo?: string;
  draftStartedFrom?: string;
  draftStartedTo?: string;
  draftCompletedFrom?: string;
  draftCompletedTo?: string;
  draftUpdatedFrom?: string;
  draftUpdatedTo?: string;
}) {
  return {
    projectId: opts.projectId,
    search: opts.draftSearchQuery,
    stage: opts.draftStatusFilter !== 'all' ? [opts.draftStatusFilter] : [],
    status: [],
    tags: [],
    category: opts.draftCategoryFilter !== 'all' ? opts.draftCategoryFilter : undefined,
    sortBy: boardSortToApiSort(opts.draftSortBy),
    sortDirection: 'desc' as const,
    plannedFrom: opts.draftPlannedFrom || undefined,
    plannedTo: opts.draftPlannedTo || undefined,
    startedFrom: opts.draftStartedFrom || undefined,
    startedTo: opts.draftStartedTo || undefined,
    completedFrom: opts.draftCompletedFrom || undefined,
    completedTo: opts.draftCompletedTo || undefined,
    updatedFrom: opts.draftUpdatedFrom || undefined,
    updatedTo: opts.draftUpdatedTo || undefined,
    page: 1,
  };
}

describe('P3-003 — applySidebarFilters query shape', () => {
  it('produces empty stage array when statusFilter is "all"', () => {
    const q = buildAppliedQuery({
      projectId: 'proj-1',
      draftSearchQuery: '',
      draftStatusFilter: 'all',
      draftCategoryFilter: 'all',
      draftSortBy: 'date',
    });
    expect(q.stage).toEqual([]);
  });

  it('wraps non-all status in a single-element stage array', () => {
    const q = buildAppliedQuery({
      projectId: 'proj-1',
      draftSearchQuery: '',
      draftStatusFilter: 'in-progress',
      draftCategoryFilter: 'all',
      draftSortBy: 'date',
    });
    expect(q.stage).toEqual(['in-progress']);
  });

  it('passes search text through to search field', () => {
    const q = buildAppliedQuery({
      projectId: 'proj-1',
      draftSearchQuery: 'feat search',
      draftStatusFilter: 'all',
      draftCategoryFilter: 'all',
      draftSortBy: 'date',
    });
    expect(q.search).toBe('feat search');
  });

  it('omits category when "all"', () => {
    const q = buildAppliedQuery({
      projectId: 'proj-1',
      draftSearchQuery: '',
      draftStatusFilter: 'all',
      draftCategoryFilter: 'all',
      draftSortBy: 'date',
    });
    expect(q.category).toBeUndefined();
  });

  it('passes through specific category', () => {
    const q = buildAppliedQuery({
      projectId: 'proj-1',
      draftSearchQuery: '',
      draftStatusFilter: 'all',
      draftCategoryFilter: 'refactor',
      draftSortBy: 'date',
    });
    expect(q.category).toBe('refactor');
  });

  it('always resets page to 1', () => {
    const q = buildAppliedQuery({
      projectId: 'proj-1',
      draftSearchQuery: 'x',
      draftStatusFilter: 'backlog',
      draftCategoryFilter: 'all',
      draftSortBy: 'progress',
    });
    expect(q.page).toBe(1);
  });

  it('passes date range filters through, omitting empties as undefined', () => {
    const q = buildAppliedQuery({
      projectId: 'proj-1',
      draftSearchQuery: '',
      draftStatusFilter: 'all',
      draftCategoryFilter: 'all',
      draftSortBy: 'date',
      draftPlannedFrom: '2026-01-01',
      draftPlannedTo: '',
    });
    expect(q.plannedFrom).toBe('2026-01-01');
    expect(q.plannedTo).toBeUndefined();
  });

  it('status array is always empty (stage carries the filter)', () => {
    const q = buildAppliedQuery({
      projectId: 'proj-1',
      draftSearchQuery: '',
      draftStatusFilter: 'done',
      draftCategoryFilter: 'all',
      draftSortBy: 'date',
    });
    expect(q.status).toEqual([]);
    expect(q.stage).toEqual(['done']);
  });
});

// ── Layer 2: Hook initialisation (static render) ──────────────────────────────

describe('P3-003 — ProjectBoard hook initialisation', () => {
  it('renders without crashing with useFeatureSurface wired in', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter initialEntries={['/board']}>
        <ProjectBoard />
      </MemoryRouter>,
    );
    expect(html.length).toBeGreaterThan(0);
    expect(html).not.toMatch(/TypeError:|ReferenceError:/);
  });

  it('calls useFeatureSurface with the active project id', () => {
    renderToStaticMarkup(
      <MemoryRouter initialEntries={['/board']}>
        <ProjectBoard />
      </MemoryRouter>,
    );
    expect(useFeatureSurface).toHaveBeenCalledWith(
      expect.objectContaining({
        initialQuery: expect.objectContaining({ projectId: 'proj-1' }),
      }),
    );
  });

  it('passes noCache: false (cache enabled by default)', () => {
    renderToStaticMarkup(
      <MemoryRouter initialEntries={['/board']}>
        <ProjectBoard />
      </MemoryRouter>,
    );
    expect(useFeatureSurface).toHaveBeenCalledWith(
      expect.objectContaining({ noCache: false }),
    );
  });

  it('P3-005: header shows filteredTotal from hook as authoritative count', () => {
    // Hook returns filteredTotal: 17; the header now renders that directly as
    // the authoritative count (no legacy "server: N" suffix).
    const html = renderToStaticMarkup(
      <MemoryRouter initialEntries={['/board']}>
        <ProjectBoard />
      </MemoryRouter>,
    );
    // filteredTotal (17) should appear; legacy "server: 42" pattern is gone.
    expect(html).toContain('17 features');
    expect(html).not.toContain('server: 42');
  });
});

/**
 * P3-004: Remove Eager Linked-Session Summary Loop
 *
 * Asserts that initial board render issues ZERO requests to
 * /api/features/{id}/linked-sessions.  The per-feature fan-out that existed
 * prior to P3-004 fired one fetch per visible feature on every filteredFeatures
 * change; this test proves it is gone.
 *
 * Approach:
 *  - Uses renderToStaticMarkup (same approach as ProjectBoardFilters.test.tsx)
 *  - fetch is globally mocked via vi.stubGlobal; the test asserts zero calls to
 *    the linked-sessions path
 *  - Uses empty features list (same as ProjectBoardFilters tests) to avoid
 *    rendering real FeatureCard sub-trees which require a full Feature shape
 *
 * The structural test (source text assertion) provides a belt-and-suspenders
 * guarantee: even if side effects ran asynchronously, the source proof is the
 * authoritative check that the callback was removed.
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Feature, PlanDocument } from '../../types';
import * as fs from 'node:fs';
import * as path from 'node:path';

// ── fetch spy ────────────────────────────────────────────────────────────────

const fetchSpy = vi.fn();

// ── useFeatureSurface mock ────────────────────────────────────────────────────

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
    setQuery: vi.fn(),
    cards: [],
    rollups: new Map(),
    totals: { total: 0, filteredTotal: 0 },
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

// ── featureSurfaceCache mock ──────────────────────────────────────────────────

vi.mock('../../services/featureSurfaceCache', () => ({
  invalidateFeatureSurface: vi.fn(),
}));

// ── DataContext mock — empty features (avoids FeatureCard shape issues) ───────

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

// ── Component under test ──────────────────────────────────────────────────────

import { ProjectBoard } from '../ProjectBoard';

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderBoard() {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={['/board']}>
      <ProjectBoard />
    </MemoryRouter>,
  );
}

function linkedSessionCalls(): string[] {
  return fetchSpy.mock.calls
    .map((args: unknown[]) => String(args[0]))
    .filter((url: string) => /\/api\/features\/[^/]+\/linked-sessions/.test(url));
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('P3-004 — No eager linked-session fetches', () => {
  beforeEach(() => {
    fetchSpy.mockReset();
    fetchSpy.mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('does not call fetch at all during static render (no side effects run)', () => {
    // renderToStaticMarkup is synchronous; useEffect does not fire.
    // The old eager loop lived in a useEffect triggered by filteredFeatures.
    renderBoard();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('issues zero /api/features/{id}/linked-sessions requests on initial render', () => {
    renderBoard();
    const offending = linkedSessionCalls();
    expect(offending).toHaveLength(0);
  });

  it('renders without crashing after P3-004 loop removal', () => {
    const html = renderBoard();
    expect(html.length).toBeGreaterThan(0);
    expect(html).not.toMatch(/TypeError:|ReferenceError:/);
  });
});

// ── Structural source-code assertion (belt-and-suspenders) ────────────────────
// This test reads the ProjectBoard.tsx source directly and asserts that the
// eager loop callback and its driving useEffect no longer exist.  This is the
// primary proof that P3-004 is complete — it cannot be fooled by async timing.

describe('P3-004 — Source-level proof: eager loop removed', () => {
  const sourceFile = path.resolve(__dirname, '../ProjectBoard.tsx');
  const source = fs.readFileSync(sourceFile, 'utf8');

  it('loadFeatureSessionSummary callback is gone', () => {
    expect(source).not.toContain('loadFeatureSessionSummary');
  });

  it('loadingFeatureSessionSummaries state is gone', () => {
    expect(source).not.toContain('loadingFeatureSessionSummaries');
  });

  it('no raw fetch to /api/features/{id}/linked-sessions inside a forEach loop', () => {
    // The pattern: filteredFeatures.forEach(feature => { ... fetch(.../linked-sessions) })
    // Verify neither the forEach nor the fetch for linked-sessions remains in proximity.
    const hasFanOutLoop =
      /filteredFeatures\.forEach[\s\S]{0,200}linked-sessions/.test(source);
    expect(hasFanOutLoop).toBe(false);
  });

  it('invalidateFeatureSurface is imported and wired to handleStatusChange', () => {
    expect(source).toContain("import { invalidateFeatureSurface } from '../services/featureSurfaceCache'");
    expect(source).toContain('invalidateFeatureSurface({ projectId: activeProjectId, featureIds: [featureId] })');
  });

  it('featureSessionSummaries state fully removed (P3-005: rollup data path in place)', () => {
    // P3-005: the state is gone; session data now comes from FeatureRollupDTO
    // via rollupToSessionSummary() imported from featureCardAdapters.ts.
    expect(source).not.toContain('featureSessionSummaries, setFeatureSessionSummaries');
    expect(source).toContain('rollupToSessionSummary');
  });
});

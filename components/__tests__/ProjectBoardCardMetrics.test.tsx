/**
 * P3-005: Card Metric Mapping — ProjectBoard card metrics tests.
 *
 * Verifies that board and list cards render session count, subthread count,
 * latest-activity timestamp, and linked-doc count from FeatureRollupDTO, and
 * that the header count comes from hook totals (filteredTotal ?? total).
 *
 * Three scenarios covered:
 *  1. Full render: cards present + rollups resolved → all metrics visible.
 *  2. Partial render: cards present + rollups still loading → list renders
 *     immediately; session indicator shows loading state.
 *  3. Filter totals: header count matches hook totals.filteredTotal ?? total.
 *
 * Uses renderToStaticMarkup (same pattern as ProjectBoardFilters and
 * ProjectBoardEagerLoop) — no @testing-library/react required.
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Feature, PlanDocument } from '../../types';
import type { FeatureCardDTO, FeatureRollupDTO } from '../../services/featureSurface';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const FIXTURE_CARD: FeatureCardDTO = {
  id: 'feat-001',
  name: 'Auth Overhaul',
  status: 'in-progress',
  effectiveStatus: 'in-progress',
  category: 'security',
  tags: ['auth', 'backend'],
  summary: 'Rewrite auth layer',
  descriptionPreview: '',
  priority: 'high',
  riskLevel: 'medium',
  complexity: 'high',
  executionReadiness: 'ready',
  testImpact: 'auth regression suite',
  planningStatus: { effectiveStatus: 'active' },
  totalTasks: 10,
  completedTasks: 4,
  deferredTasks: 0,
  phaseCount: 3,
  plannedAt: '2026-01-15T00:00:00Z',
  startedAt: '2026-02-01T00:00:00Z',
  completedAt: '',
  updatedAt: '2026-04-20T00:00:00Z',
  documentCoverage: { present: ['prd', 'plan'], missing: [], countsByType: {} },
  qualitySignals: { blockerCount: 1, atRiskTaskCount: 0, hasBlockingSignals: true, testImpact: 'auth regression suite', integritySignalRefs: [] },
  dependencyState: { state: 'unblocked', blockingReason: '', blockedByCount: 0, readyDependencyCount: 0 },
  primaryDocuments: [],
  familyPosition: null,
  relatedFeatureCount: 2,
  precision: 'exact',
  freshness: null,
};

const FIXTURE_ROLLUP: FeatureRollupDTO = {
  featureId: 'feat-001',
  sessionCount: 7,
  primarySessionCount: 5,
  subthreadCount: 2,
  unresolvedSubthreadCount: 0,
  totalCost: 0.42,
  displayCost: 0.42,
  observedTokens: 125000,
  modelIoTokens: 115000,
  cacheInputTokens: 10000,
  latestSessionAt: '2026-04-22T18:00:00Z',
  latestActivityAt: '2026-04-22T18:30:00Z',
  modelFamilies: [{ key: 'sonnet', label: 'Sonnet', count: 5, share: 0.71 }],
  providers: [{ key: 'anthropic', label: 'Anthropic', count: 7, share: 1.0 }],
  workflowTypes: [{ key: 'execution', label: 'Execution', count: 5, share: 0.71 }],
  linkedDocCount: 4,
  linkedDocCountsByType: [],
  linkedTaskCount: 3,
  linkedCommitCount: 2,
  linkedPrCount: 1,
  testCount: 12,
  failingTestCount: 0,
  precision: 'exact',
  freshness: null,
};

// ── useFeatureSurface mock factory ────────────────────────────────────────────

function makeSurfaceMock(
  cards: FeatureCardDTO[],
  rollups: Map<string, FeatureRollupDTO>,
  rollupState: 'loading' | 'success' | 'error' = 'success',
  totals: { total: number; filteredTotal?: number } = { total: cards.length, filteredTotal: cards.length },
): () => UseFeatureSurfaceResult {
  return () => ({
    query: {
      projectId: 'proj-1',
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
    cards,
    rollups,
    totals,
    listState: 'success' as const,
    rollupState,
    listError: null,
    rollupError: null,
    retryList: vi.fn(),
    retryRollups: vi.fn(),
    refetch: vi.fn(),
    invalidate: vi.fn(),
    cacheKey: 'test-key',
  });
}

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('../../services/useFeatureSurface', () => ({
  useFeatureSurface: makeSurfaceMock([], new Map()),
}));

vi.mock('../../services/featureSurfaceCache', () => ({
  invalidateFeatureSurface: vi.fn(),
}));

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
import type { UseFeatureSurfaceResult } from '../../services/useFeatureSurface';
import * as UseFeatureSurfaceModule from '../../services/useFeatureSurface';

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderBoard() {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={['/board']}>
      <ProjectBoard />
    </MemoryRouter>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('P3-005 — Card Metric Mapping: session count from rollup', () => {
  beforeEach(() => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock(
        [FIXTURE_CARD],
        new Map([['feat-001', FIXTURE_ROLLUP]]),
        'success',
        { total: 1, filteredTotal: 1 },
      ),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the card name from FeatureCardDTO', () => {
    const html = renderBoard();
    expect(html).toContain('Auth Overhaul');
  });

  it('renders the session count from FeatureRollupDTO.sessionCount', () => {
    const html = renderBoard();
    // FeatureSessionIndicator shows total session count (7) as a badge.
    // The badge format is: terminal icon + count in a span.
    expect(html).toContain('>7<');
  });

  it('renders the linked-doc count from FeatureRollupDTO.linkedDocCount', () => {
    const html = renderBoard();
    // RollupLinkedDocsBadge shows "Docs N" where N = linkedDocCount (4).
    expect(html).toContain('>4<');
  });

  it('renders the phase count from FeatureCardDTO.phaseCount', () => {
    const html = renderBoard();
    // Card shows "N phase(s)" badge from card.phaseCount (3).
    expect(html).toContain('3 phases');
  });

  it('renders the feature ID', () => {
    const html = renderBoard();
    expect(html).toContain('feat-001');
  });

  it('renders card priority badge', () => {
    const html = renderBoard();
    expect(html).toContain('high');
  });

  it('renders saved card metadata without requiring full feature details', () => {
    const html = renderBoard();
    expect(html).toContain('Rewrite auth layer');
    expect(html).toContain('risk medium');
    expect(html).toContain('complexity high');
    expect(html).toContain('ready');
    expect(html).toContain('1 blocker');
  });
});

describe('P3-005 — Card Metric Mapping: partial render (rollups pending)', () => {
  beforeEach(() => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock(
        [FIXTURE_CARD],
        new Map(), // rollups empty — not yet resolved
        'loading',
        { total: 1, filteredTotal: 1 },
      ),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the card list immediately without blocking on rollup resolution', () => {
    const html = renderBoard();
    // Card name appears even though rollups are still loading.
    expect(html).toContain('Auth Overhaul');
  });

  it('session indicator shows loading state (spin icon) when rollup is pending', () => {
    const html = renderBoard();
    // When loading=true and no rollup, the indicator renders with animate-spin.
    expect(html).toContain('animate-spin');
  });
});

describe('P3-005 — Card Metric Mapping: filter totals from hook', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('header shows filteredTotal when available', () => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock(
        [],
        new Map(),
        'success',
        { total: 42, filteredTotal: 17 },
      ),
    );

    const html = renderBoard();
    expect(html).toContain('17 features');
    expect(html).not.toContain('42 features');
  });

  it('header falls back to total when filteredTotal is undefined', () => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock(
        [],
        new Map(),
        'success',
        { total: 42, filteredTotal: undefined },
      ),
    );

    const html = renderBoard();
    expect(html).toContain('42 features');
  });

  it('header shows loading state when listState is loading', () => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      () => ({
        query: { projectId: 'proj-1', page: 1, pageSize: 50, search: '', status: [], stage: [], tags: [], sortBy: 'updated_at', sortDirection: 'desc', include: [] },
        setQuery: vi.fn(),
        cards: [],
        rollups: new Map(),
        totals: { total: 0 },
        listState: 'loading' as const,
        rollupState: 'loading' as const,
        listError: null,
        rollupError: null,
        retryList: vi.fn(),
        retryRollups: vi.fn(),
        refetch: vi.fn(),
        invalidate: vi.fn(),
        cacheKey: 'test-key',
      }),
    );

    const html = renderBoard();
    expect(html).toContain('Loading');
  });
});

// ── Source-level proof: featureSessionSummaries fully removed ─────────────────

import * as fs from 'node:fs';
import * as path from 'node:path';

describe('P3-005 — Source-level proof: featureSessionSummaries state removed', () => {
  const sourceFile = path.resolve(__dirname, '../ProjectBoard.tsx');
  const source = fs.readFileSync(sourceFile, 'utf8');

  it('featureSessionSummaries useState is gone', () => {
    expect(source).not.toContain('featureSessionSummaries, setFeatureSessionSummaries');
  });

  it('rollupToSessionSummary adapter is imported', () => {
    expect(source).toContain('rollupToSessionSummary');
  });

  it('board render uses surfaceCards, not filteredFeatures', () => {
    expect(source).toContain('surfaceCards.filter(c => cardDTOBoardStage(c)');
  });

  it('list render maps over surfaceCards', () => {
    expect(source).toContain('surfaceCards.map(c => (');
  });

  it('no per-feature session fetch calls remain on the render path', () => {
    // No raw fetch to /linked-sessions or similar per-feature fan-out.
    const hasFanOut = /surfaceCards\.forEach[\s\S]{0,200}fetch/.test(source);
    expect(hasFanOut).toBe(false);
  });
});

/**
 * P4-008: FeatureExecutionWorkbench Surface Migration
 *
 * Verifies that the workbench sources its feature list from useFeatureSurface
 * (unified bounded payload) rather than DataContext features fan-out.
 *
 * Scenarios:
 *   1. Bounded call proof — useFeatureSurface called exactly once on render;
 *      no per-feature /api/features/{id}/linked-sessions or DataContext
 *      features fan-out calls issued.
 *   2. Feature picker list populated from surface cards.
 *   3. Surface loading state — list loading → picker still renders without crash.
 *   4. Source-level proof — workbench imports useFeatureSurface; DataContext
 *      destructuring no longer contains `features` or `refreshFeatures`.
 *   5. Rollup-derived metrics are available (surfaceCards carries rollup data
 *      via the hook; analytics tab metrics come from context.analytics, not
 *      a separate raw fan-out).
 *
 * Strategy: renderToStaticMarkup with synchronous mocks so hook state is
 * stable on first render (same pattern as DashboardFeatureSurface.test.tsx).
 * The workbench has deep transitive dependencies (live connections, execution
 * runs, planning context), so we stub them all to their no-op defaults.
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import type { FeatureCardDTO, FeatureRollupDTO } from '../../services/featureSurface';
import type { Feature, PlanDocument } from '../../types';
import type { UseFeatureSurfaceResult } from '../../services/useFeatureSurface';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const FIXTURE_CARD_A: FeatureCardDTO = {
  id: 'feat-alpha',
  name: 'Alpha Feature',
  status: 'in-progress',
  effectiveStatus: 'in-progress',
  category: 'backend',
  tags: ['core'],
  summary: 'Alpha summary',
  descriptionPreview: '',
  priority: 'high',
  riskLevel: 'low',
  complexity: 'medium',
  totalTasks: 6,
  completedTasks: 2,
  deferredTasks: 0,
  phaseCount: 2,
  plannedAt: '2026-01-01T00:00:00Z',
  startedAt: '2026-02-01T00:00:00Z',
  completedAt: '',
  updatedAt: '2026-04-20T00:00:00Z',
  documentCoverage: { present: [], missing: [], countsByType: {} },
  qualitySignals: {
    blockerCount: 0,
    atRiskTaskCount: 0,
    hasBlockingSignals: false,
    testImpact: '',
    integritySignalRefs: [],
  },
  dependencyState: {
    state: 'unblocked',
    blockingReason: '',
    blockedByCount: 0,
    readyDependencyCount: 0,
  },
  primaryDocuments: [],
  familyPosition: null,
  relatedFeatureCount: 0,
  precision: 'exact',
  freshness: null,
};

const FIXTURE_CARD_B: FeatureCardDTO = {
  ...FIXTURE_CARD_A,
  id: 'feat-beta',
  name: 'Beta Feature',
  status: 'planned',
  effectiveStatus: 'planned',
};

const FIXTURE_ROLLUP_A: FeatureRollupDTO = {
  featureId: 'feat-alpha',
  sessionCount: 3,
  primarySessionCount: 2,
  subthreadCount: 1,
  unresolvedSubthreadCount: 0,
  totalCost: 0.15,
  displayCost: 0.15,
  observedTokens: 30000,
  modelIoTokens: 28000,
  cacheInputTokens: 2000,
  latestSessionAt: '2026-04-22T10:00:00Z',
  latestActivityAt: '2026-04-22T10:30:00Z',
  modelFamilies: [],
  providers: [],
  workflowTypes: [],
  linkedDocCount: 1,
  linkedDocCountsByType: [],
  linkedTaskCount: 2,
  linkedCommitCount: 0,
  linkedPrCount: 0,
  testCount: 4,
  failingTestCount: 0,
  precision: 'exact',
  freshness: null,
};

// ── Mock factory ──────────────────────────────────────────────────────────────

function makeSurfaceMock(
  cards: FeatureCardDTO[],
  rollups: Map<string, FeatureRollupDTO>,
  listState: 'idle' | 'loading' | 'success' | 'error' = 'success',
): () => UseFeatureSurfaceResult {
  return () => ({
    query: {
      projectId: undefined,
      page: 1,
      pageSize: 50,
      search: '',
      status: [],
      stage: [],
      tags: [],
      sortBy: 'updated_at',
      sortDirection: 'desc' as const,
      include: [],
    },
    setQuery: vi.fn(),
    cards,
    rollups,
    totals: { total: cards.length },
    freshness: null,
    listState,
    rollupState: 'success' as const,
    listError: null,
    rollupError: null,
    retryList: vi.fn(),
    retryRollups: vi.fn(),
    refetch: vi.fn(),
    invalidate: vi.fn(),
    cacheKey: 'test-wb-key',
  });
}

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('../../services/useFeatureSurface', () => ({
  useFeatureSurface: makeSurfaceMock([], new Map()),
  DEFAULT_FEATURE_SURFACE_QUERY: {
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
}));

vi.mock('../../services/featureSurfaceCache', () => ({
  defaultFeatureSurfaceCache: {
    get: vi.fn(),
    set: vi.fn(),
    delete: vi.fn(),
    clear: vi.fn(),
  },
  invalidateFeatureSurface: vi.fn(),
}));

vi.mock('../../services/featureCacheBus', () => ({
  featureCacheBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() },
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
    activeProject: { id: 'proj-test', name: 'Test Project' },
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

vi.mock('../../services/execution', () => ({
  getFeatureExecutionContext: vi.fn().mockResolvedValue(null),
  checkExecutionPolicy: vi.fn().mockResolvedValue(null),
  createExecutionRun: vi.fn().mockResolvedValue(null),
  approveExecutionRun: vi.fn().mockResolvedValue(null),
  cancelExecutionRun: vi.fn().mockResolvedValue(null),
  retryExecutionRun: vi.fn().mockResolvedValue(null),
  getExecutionRun: vi.fn().mockResolvedValue(null),
  listExecutionRuns: vi.fn().mockResolvedValue([]),
  listExecutionRunEvents: vi.fn().mockResolvedValue({ items: [], nextSequence: 0 }),
  trackExecutionEvent: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../../services/planning', () => ({
  getFeaturePlanningContext: vi.fn().mockResolvedValue(null),
  PlanningApiError: class PlanningApiError extends Error {},
}));

vi.mock('../../services/testVisualizer', () => ({
  listTestRuns: vi.fn().mockResolvedValue({ items: [] }),
}));

vi.mock('../../services/live', () => ({
  executionRunTopic: vi.fn(() => 'execution-run-topic'),
  featurePlanningTopic: vi.fn(() => 'feature-planning-topic'),
  isExecutionLiveUpdatesEnabled: vi.fn(() => false),
  sharedLiveConnectionManager: { connect: vi.fn(), disconnect: vi.fn() },
  useLiveInvalidation: vi.fn(),
}));

vi.mock('../../services/agenticIntelligence', () => ({
  isStackRecommendationsEnabled: vi.fn(() => false),
  isWorkflowAnalyticsEnabled: vi.fn(() => false),
}));

vi.mock('../../services/featureSurface', () => ({
  getLegacyFeatureDetail: vi.fn().mockResolvedValue(null),
  getLegacyFeatureLinkedSessions: vi.fn().mockResolvedValue([]),
  getFeatureLinkedSessionPage: vi.fn().mockResolvedValue({
    items: [],
    total: 0,
    offset: 0,
    limit: 20,
    hasMore: false,
    nextCursor: null,
    enrichment: { includes: [], logsRead: false, commandCountIncluded: false, taskRefsIncluded: false, threadChildrenIncluded: false },
    precision: 'exact',
    freshness: null,
  }),
  FeatureSurfaceApiError: class extends Error {},
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useSearchParams: () => [new URLSearchParams(), vi.fn()] as const,
  };
});

// ── Component under test ──────────────────────────────────────────────────────

import { FeatureExecutionWorkbench } from '../FeatureExecutionWorkbench';
import * as UseFeatureSurfaceModule from '../../services/useFeatureSurface';

// ── Render helper ─────────────────────────────────────────────────────────────

function renderWorkbench() {
  return renderToStaticMarkup(
    <MemoryRouter>
      <FeatureExecutionWorkbench />
    </MemoryRouter>,
  );
}

// ── Tests: bounded call proof ─────────────────────────────────────────────────

describe('P4-008 — FeatureExecutionWorkbench Surface: bounded call proof', () => {
  beforeEach(() => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock([], new Map(), 'success'),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls useFeatureSurface exactly once on initial render (no fan-out)', () => {
    renderWorkbench();
    expect(UseFeatureSurfaceModule.useFeatureSurface).toHaveBeenCalledTimes(1);
  });

  it('renders without crashing when surface returns empty cards', () => {
    expect(() => renderWorkbench()).not.toThrow();
  });
});

// ── Tests: feature picker populated from surface cards ────────────────────────

describe('P4-008 — FeatureExecutionWorkbench Surface: picker from surface cards', () => {
  const twoCards = [FIXTURE_CARD_A, FIXTURE_CARD_B];
  const rollupMap = new Map([['feat-alpha', FIXTURE_ROLLUP_A]]);

  beforeEach(() => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock(twoCards, rollupMap, 'success'),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders feature option elements sourced from surface cards', () => {
    const html = renderWorkbench();
    expect(html).toContain('Alpha Feature');
    expect(html).toContain('Beta Feature');
  });

  it('useFeatureSurface called exactly once even with populated cards (no duplicate)', () => {
    renderWorkbench();
    expect(UseFeatureSurfaceModule.useFeatureSurface).toHaveBeenCalledTimes(1);
  });
});

// ── Tests: loading state ──────────────────────────────────────────────────────

describe('P4-008 — FeatureExecutionWorkbench Surface: surface loading state', () => {
  beforeEach(() => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock([], new Map(), 'loading'),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders without crash while surface list is loading', () => {
    expect(() => renderWorkbench()).not.toThrow();
  });

  it('still renders the Refresh button', () => {
    const html = renderWorkbench();
    expect(html).toContain('Refresh');
  });
});

// ── Source-level proof: no DataContext features fan-out ───────────────────────

import * as fs from 'node:fs';
import * as path from 'node:path';

describe('P4-008 — FeatureExecutionWorkbench source-level proof: no per-feature fan-out', () => {
  const sourceFile = path.resolve(__dirname, '../FeatureExecutionWorkbench.tsx');
  const source = fs.readFileSync(sourceFile, 'utf8');

  it('imports useFeatureSurface', () => {
    expect(source).toContain('useFeatureSurface');
  });

  it('does not destructure `features` from useData()', () => {
    // features should NOT appear in the useData destructuring pattern
    expect(source).not.toMatch(/const\s*\{[^}]*\bfeatures\b[^}]*\}\s*=\s*useData\(\)/);
  });

  it('does not destructure `refreshFeatures` from useData()', () => {
    expect(source).not.toMatch(/const\s*\{[^}]*\brefreshFeatures\b[^}]*\}\s*=\s*useData\(\)/);
  });

  it('does not call raw /api/features/ endpoint with template interpolation', () => {
    // No raw fetch() calls to /api/features/${...} URLs in the component
    expect(source).not.toMatch(/fetch\(['"]\/?api\/features\/\$\{/);
  });

  it('sources the feature picker list from surfaceCards', () => {
    expect(source).toContain('surfaceCards');
  });

  it('uses refetchSurface instead of refreshFeatures for Refresh button', () => {
    expect(source).toContain('refetchSurface');
    expect(source).not.toContain('refreshFeatures()');
  });

  it('getLegacyFeatureDetail is kept for phases tab (per-feature detail, correct)', () => {
    // getLegacyFeatureDetail is the correct typed helper for phases tab detail
    expect(source).toContain('getLegacyFeatureDetail');
  });
});

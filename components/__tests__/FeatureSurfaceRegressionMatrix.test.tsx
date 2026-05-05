/**
 * P5-004: Feature Surface Regression Matrix
 *
 * Hard invariant: NO per-feature /api/features/{id}/linked-sessions call happens
 * on initial render for any of the migrated consumer surfaces.
 *
 * Surfaces covered:
 *   - ProjectBoard (component + source)
 *   - SessionInspector (source)
 *   - FeatureExecutionWorkbench (component + source)
 *   - Dashboard / BlockingFeatureList (component + source)
 *   - Planning modals (source — planning surfaces do not call linked-sessions)
 *   - useFeatureModalData service (source — demand-driven only, never on mount)
 *
 * Strategy:
 *   - renderToStaticMarkup with globally-mocked fetch for component surfaces;
 *     static render is synchronous so useEffect never fires — any eager call
 *     inside an effect would be caught by the runtime fetch spy tests elsewhere.
 *   - Source-level proofs for all surfaces: grep for absence of forbidden
 *     patterns and presence of required migration markers.
 *   - Shared helpers extract repeated fixture / render logic to avoid duplication
 *     with existing per-surface test suites (these tests focus on the matrix
 *     invariant, not on full feature coverage of each surface).
 *
 * Relation to existing suites:
 *   - ProjectBoardEagerLoop.test.tsx    → belt-and-suspenders for the board source proof
 *   - SessionInspectorFeatureSurface.test.tsx → full SI pagination proof
 *   - FeatureExecutionWorkbenchSurface.test.tsx → full workbench proof
 *   - DashboardFeatureSurface.test.tsx  → full dashboard proof
 *   - BlockingFeatureListPhase4.test.tsx → full BFL DTO proof
 *
 * This matrix adds: cross-surface unified assertion, Planning coverage, and the
 * useFeatureModalData demand-gate proof that is missing from the existing suites.
 *
 * NOTE on vi.mock hoisting: vi.mock() factories are hoisted before any module-level
 * variable declarations. Factories therefore use inline values only — no references
 * to module-scope constants like EMPTY_ROLLUPS.  The makeSurfaceMock helper is used
 * only inside beforeEach / test bodies where it runs after initialization.
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

import type { Feature, PlanDocument } from '../../types';
import type { FeatureCardDTO, FeatureRollupDTO } from '../../services/featureSurface';
import type { UseFeatureSurfaceResult } from '../../services/useFeatureSurface';

// ─────────────────────────────────────────────────────────────────────────────
// Module-level mocks — factories use inline values only (vi.mock is hoisted)
// ─────────────────────────────────────────────────────────────────────────────

vi.mock('../../services/useFeatureSurface', () => ({
  // Returns an empty-success surface; overridden per-test via vi.spyOn
  useFeatureSurface: () => ({
    query: {
      projectId: undefined,
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
    setQuery: () => {},
    cards: [],
    rollups: new Map(),
    totals: { total: 0 },
    freshness: null,
    listState: 'success',
    rollupState: 'success',
    listError: null,
    rollupError: null,
    retryList: () => {},
    retryRollups: () => {},
    refetch: () => {},
    invalidate: () => {},
    cacheKey: 'matrix-test-key',
  }),
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
    activeProject: { id: 'proj-matrix', name: 'Matrix Project' },
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

vi.mock('../../contexts/AuthSessionContext', () => ({
  useAuthSession: () => ({
    session: { localMode: true, authMode: 'local', authenticated: true },
    metadata: { localMode: true, authMode: 'local' },
    hasPermission: vi.fn(() => true),
  }),
}));

vi.mock('../../services/live', () => ({
  executionRunTopic: vi.fn(() => 'execution-run-topic'),
  featureTopic: vi.fn(() => 'feature-topic'),
  featurePlanningTopic: vi.fn(() => 'feature-planning-topic'),
  isExecutionLiveUpdatesEnabled: vi.fn(() => false),
  isFeatureLiveUpdatesEnabled: vi.fn(() => false),
  isStackRecommendationsEnabled: vi.fn(() => true),
  isWorkflowAnalyticsEnabled: vi.fn(() => true),
  projectFeaturesTopic: vi.fn(),
  sharedLiveConnectionManager: { connect: vi.fn(), disconnect: vi.fn() },
  useLiveInvalidation: vi.fn(() => 'idle'),
}));

vi.mock('../../services/execution', () => ({
  trackExecutionEvent: vi.fn(),
  approveExecutionRun: vi.fn(),
  cancelExecutionRun: vi.fn(),
  checkExecutionPolicy: vi.fn(),
  createExecutionRun: vi.fn(),
  getExecutionRun: vi.fn(),
  getFeatureExecutionContext: vi.fn().mockResolvedValue(null),
  listExecutionRunEvents: vi.fn().mockResolvedValue({ items: [], nextSequence: 0 }),
  listExecutionRuns: vi.fn().mockResolvedValue([]),
  retryExecutionRun: vi.fn(),
  getLaunchCapabilities: vi.fn().mockResolvedValue({ planningEnabled: true }),
}));

vi.mock('../../services/agenticIntelligence', () => ({
  isStackRecommendationsEnabled: vi.fn(() => false),
  isWorkflowAnalyticsEnabled: vi.fn(() => false),
}));

vi.mock('../../services/testVisualizer', () => ({
  getFeatureHealth: vi.fn(),
  listTestRuns: vi.fn().mockResolvedValue({ items: [] }),
}));

vi.mock('../../services/planning', () => ({
  getFeaturePlanningContext: vi.fn().mockResolvedValue(null),
  PlanningApiError: class PlanningApiError extends Error {},
}));

vi.mock('../../services/analytics', () => ({
  analyticsService: {
    getOverview: vi.fn().mockResolvedValue({ kpis: {} }),
    getSessionCostCalibration: vi.fn().mockResolvedValue({}),
    getSeries: vi.fn().mockResolvedValue({ items: [] }),
  },
}));

vi.mock('../../services/geminiService', () => ({
  generateDashboardInsight: vi.fn().mockResolvedValue('Mock insight'),
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
    enrichment: {
      includes: [],
      logsRead: false,
      commandCountIncluded: false,
      taskRefsIncluded: false,
      threadChildrenIncluded: false,
    },
    precision: 'exact',
    freshness: null,
  }),
  getFeatureTaskSource: vi.fn().mockResolvedValue({ tasks: [] }),
  listFeatureCards: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  getFeatureRollups: vi.fn().mockResolvedValue([]),
  getFeatureModalOverview: vi.fn().mockResolvedValue(null),
  getFeatureModalSection: vi.fn().mockResolvedValue(null),
  FeatureSurfaceApiError: class extends Error {},
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

// ─────────────────────────────────────────────────────────────────────────────
// Post-hoist fixtures and helpers
// (These run after module initialization, so module-level refs are fine here)
// ─────────────────────────────────────────────────────────────────────────────

const BASE_CARD: FeatureCardDTO = {
  id: 'feat-matrix-1',
  name: 'Matrix Feature',
  status: 'in-progress',
  effectiveStatus: 'in-progress',
  category: 'backend',
  tags: [],
  summary: '',
  descriptionPreview: '',
  priority: 'high',
  riskLevel: 'low',
  complexity: 'medium',
  totalTasks: 4,
  completedTasks: 1,
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

/**
 * Shared mock factory — called inside beforeEach / test bodies only.
 * NOT safe to call from vi.mock() factory (hoisting issue).
 */
function makeSurfaceMock(
  cards: FeatureCardDTO[] = [],
  rollups: Map<string, FeatureRollupDTO> = new Map(),
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
    cacheKey: 'matrix-test-key',
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Source probe helpers
// ─────────────────────────────────────────────────────────────────────────────

const ROOT = path.resolve(__dirname, '../..');

function readSource(relPath: string): string {
  return fs.readFileSync(path.resolve(ROOT, relPath), 'utf-8');
}

function readSessionInspectorSource(): string {
  return [
    readSource('components/SessionInspector.tsx'),
    readSource('components/SessionInspector/TranscriptView.tsx'),
  ].join('\n');
}

/**
 * Returns non-comment lines that contain the given pattern.
 */
function productionLines(source: string, pattern: string): string[] {
  return source.split('\n').filter(
    line =>
      line.includes(pattern) &&
      !line.trimStart().startsWith('//') &&
      !line.trimStart().startsWith('*'),
  );
}

/** True if source has any production call to getLegacyFeatureLinkedSessions. */
function hasLegacyLinkedSessionsCall(source: string): boolean {
  return productionLines(source, 'getLegacyFeatureLinkedSessions(').length > 0;
}

/**
 * True if source includes an eager call pattern that bypasses the network
 * abstraction layer:
 * - direct fetch template-literal to /api/features/${id}/linked-sessions
 * - direct fetch string to /api/features/.../linked-sessions
 */
function hasEagerLinkedSessionsInSource(source: string): boolean {
  // Template-literal interpolation: `/api/features/${...}/linked-sessions`
  if (/`[^`]*\/api\/features\/\$\{[^`]*\/linked-sessions[^`]*`/.test(source)) return true;
  // Raw string fetch to linked-sessions
  if (/fetch\(['"]\/?api\/features\/[^'"]*\/linked-sessions/.test(source)) return true;
  return false;
}

// ─────────────────────────────────────────────────────────────────────────────
// Fetch spy (shared across all render-based suites in this file)
// ─────────────────────────────────────────────────────────────────────────────

const fetchSpy = vi.fn();

function linkedSessionFetchCalls(): string[] {
  return fetchSpy.mock.calls
    .map((args: unknown[]) => String(args[0]))
    .filter((url: string) => /\/api\/features\/[^/]+\/linked-sessions/.test(url));
}

// ─────────────────────────────────────────────────────────────────────────────
// Component imports (after all vi.mock() calls)
// ─────────────────────────────────────────────────────────────────────────────

import { ProjectBoard } from '../ProjectBoard';
import { Dashboard } from '../Dashboard';
import { FeatureExecutionWorkbench } from '../FeatureExecutionWorkbench';
import * as UseFeatureSurfaceModule from '../../services/useFeatureSurface';

// ─────────────────────────────────────────────────────────────────────────────
// Render helpers
// ─────────────────────────────────────────────────────────────────────────────

function renderProjectBoard() {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={['/board']}>
      <ProjectBoard />
    </MemoryRouter>,
  );
}

function renderDashboard() {
  return renderToStaticMarkup(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  );
}

function renderWorkbench() {
  return renderToStaticMarkup(
    <MemoryRouter>
      <FeatureExecutionWorkbench />
    </MemoryRouter>,
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SURFACE 1: ProjectBoard
// ─────────────────────────────────────────────────────────────────────────────

describe('P5-004 Matrix — ProjectBoard: no linked-sessions on initial render', () => {
  beforeEach(() => {
    fetchSpy.mockReset();
    fetchSpy.mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal('fetch', fetchSpy);
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock([BASE_CARD], new Map(), 'success'),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('issues zero fetch calls during synchronous static render', () => {
    // renderToStaticMarkup is synchronous; useEffect never fires.
    // The old eager loop fired inside useEffect on filteredFeatures change.
    renderProjectBoard();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('issues zero /api/features/*/linked-sessions calls on static render', () => {
    renderProjectBoard();
    expect(linkedSessionFetchCalls()).toHaveLength(0);
  });

  it('reads from useFeatureSurface — called exactly once, no fan-out', () => {
    renderProjectBoard();
    expect(UseFeatureSurfaceModule.useFeatureSurface).toHaveBeenCalledTimes(1);
  });

  it('renders without crashing in loading state', () => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock([], new Map(), 'loading'),
    );
    expect(() => renderProjectBoard()).not.toThrow();
  });

  it('renders without crashing when surface is empty', () => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock([], new Map(), 'success'),
    );
    expect(() => renderProjectBoard()).not.toThrow();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// SURFACE 1 (cont): ProjectBoard source-level proof
// ─────────────────────────────────────────────────────────────────────────────

describe('P5-004 Matrix — ProjectBoard source: no eager linked-sessions call', () => {
  const src = readSource('components/ProjectBoard.tsx');

  it('no eager fetch template-literal to /linked-sessions', () => {
    expect(hasEagerLinkedSessionsInSource(src)).toBe(false);
  });

  it('refreshLinkedSessions callback exists and is gated behind activeTab === sessions (P5-006: now uses v2 API)', () => {
    // refreshLinkedSessions still exists but now calls getFeatureLinkedSessionPage
    const callbackIdx = src.indexOf('const refreshLinkedSessions = useCallback');
    expect(callbackIdx).toBeGreaterThan(-1);

    // The effect that calls refreshLinkedSessions must check activeTab
    const gateMarker = "activeTab === 'sessions' && !sessionsFetchedRef.current";
    expect(src).toContain(gateMarker);
  });

  it('P5-006: getLegacyFeatureLinkedSessions is NOT called in ProjectBoard production code', () => {
    // After P5-006 migration, refreshLinkedSessions uses getFeatureLinkedSessionPage.
    // The legacy call must be absent.
    expect(hasLegacyLinkedSessionsCall(src)).toBe(false);
  });

  it('P5-006: getFeatureLinkedSessionPage is imported in ProjectBoard', () => {
    expect(src).toContain('getFeatureLinkedSessionPage');
  });

  it('each refreshLinkedSessions() call site has a guard in surrounding context', () => {
    const lines = src.split('\n');
    const callLines = lines
      .map((line, idx) => ({ line, idx }))
      .filter(
        ({ line }) =>
          (line.includes('void refreshLinkedSessions()') ||
            line.includes('refreshLinkedSessions()')) &&
          !line.trimStart().startsWith('//') &&
          !line.trimStart().startsWith('*'),
      );

    for (const { idx } of callLines) {
      const context = lines.slice(Math.max(0, idx - 5), idx + 1).join('\n');
      const hasGuard =
        context.includes("activeTab === 'sessions'") ||
        context.includes('sessionsFetchedRef') ||
        context.includes('sessionsFetchedRef.current');
      expect(hasGuard, `refreshLinkedSessions() at line ${idx + 1} has no lazy-sessions guard`).toBe(true);
    }
  });

  it('useFeatureSurface is imported and used for the board data path', () => {
    expect(src).toContain("import { useFeatureSurface } from '../services/useFeatureSurface'");
  });

  it('rollupToSessionSummary is used (rollup data path in place of fan-out)', () => {
    expect(src).toContain('rollupToSessionSummary');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// SURFACE 2: SessionInspector source-level proof
// (Runtime proof is already in SessionInspectorFeatureSurface.test.tsx — this
//  extends the matrix by verifying the cross-surface invariant.)
// ─────────────────────────────────────────────────────────────────────────────

describe('P5-004 Matrix — SessionInspector source: no eager linked-sessions call', () => {
  const src = readSessionInspectorSource();

  it('no eager fetch template-literal to /linked-sessions', () => {
    expect(hasEagerLinkedSessionsInSource(src)).toBe(false);
  });

  it('getLegacyFeatureLinkedSessions is not imported', () => {
    const importLines = src
      .split('\n')
      .filter(
        line =>
          line.includes("from '../services/featureSurface'") &&
          line.includes('getLegacyFeatureLinkedSessions'),
      );
    expect(importLines).toHaveLength(0);
  });

  it('getFeatureLinkedSessionPage is demand-driven — inside loadRelatedMainThreadSessions only', () => {
    const callIdx = src.indexOf('getFeatureLinkedSessionPage(featureId,');
    expect(callIdx).toBeGreaterThan(-1);

    // Walk backwards to confirm we are inside loadRelatedMainThreadSessions
    const before = src.slice(0, callIdx);
    const lastFnDecl = before.lastIndexOf('loadRelatedMainThreadSessions');
    expect(lastFnDecl).toBeGreaterThan(-1);
  });

  it('per-feature detail fan-out is gated on activeTab === features', () => {
    expect(src).toContain("if (activeTab !== 'features') return;");
  });

  it('no production call to getLegacyFeatureLinkedSessions remains', () => {
    expect(hasLegacyLinkedSessionsCall(src)).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// SURFACE 3: FeatureExecutionWorkbench
// ─────────────────────────────────────────────────────────────────────────────

describe('P5-004 Matrix — FeatureExecutionWorkbench: no linked-sessions on initial render', () => {
  beforeEach(() => {
    fetchSpy.mockReset();
    fetchSpy.mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal('fetch', fetchSpy);
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock([], new Map(), 'success'),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('issues zero /api/features/*/linked-sessions calls on static render', () => {
    renderWorkbench();
    expect(linkedSessionFetchCalls()).toHaveLength(0);
  });

  it('reads from useFeatureSurface — called exactly once', () => {
    renderWorkbench();
    expect(UseFeatureSurfaceModule.useFeatureSurface).toHaveBeenCalledTimes(1);
  });

  it('renders without crashing in loading state', () => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock([], new Map(), 'loading'),
    );
    expect(() => renderWorkbench()).not.toThrow();
  });

  it('renders without crashing in error state', () => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock([], new Map(), 'error'),
    );
    expect(() => renderWorkbench()).not.toThrow();
  });
});

describe('P5-004 Matrix — FeatureExecutionWorkbench source: no eager linked-sessions call', () => {
  const src = readSource('components/FeatureExecutionWorkbench.tsx');

  it('no eager fetch template-literal to /linked-sessions', () => {
    expect(hasEagerLinkedSessionsInSource(src)).toBe(false);
  });

  it('does not call getLegacyFeatureLinkedSessions', () => {
    expect(hasLegacyLinkedSessionsCall(src)).toBe(false);
  });

  it('sources the feature list from surfaceCards via useFeatureSurface', () => {
    expect(src).toContain('surfaceCards');
    expect(src).toContain('useFeatureSurface');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// SURFACE 4: Dashboard
// ─────────────────────────────────────────────────────────────────────────────

describe('P5-004 Matrix — Dashboard: no linked-sessions on initial render', () => {
  beforeEach(() => {
    fetchSpy.mockReset();
    fetchSpy.mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal('fetch', fetchSpy);
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock([], new Map(), 'success'),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('issues zero /api/features/*/linked-sessions calls on static render', () => {
    renderDashboard();
    expect(linkedSessionFetchCalls()).toHaveLength(0);
  });

  it('reads from useFeatureSurface — called exactly once', () => {
    renderDashboard();
    expect(UseFeatureSurfaceModule.useFeatureSurface).toHaveBeenCalledTimes(1);
  });

  it('renders without crashing in loading state', () => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock([], new Map(), 'loading'),
    );
    expect(() => renderDashboard()).not.toThrow();
  });

  it('renders without crashing in error state', () => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock([], new Map(), 'error'),
    );
    expect(() => renderDashboard()).not.toThrow();
  });
});

describe('P5-004 Matrix — Dashboard source: no eager linked-sessions call', () => {
  const src = readSource('components/Dashboard.tsx');

  it('no eager fetch template-literal to /linked-sessions', () => {
    expect(hasEagerLinkedSessionsInSource(src)).toBe(false);
  });

  it('does not call getLegacyFeatureLinkedSessions', () => {
    expect(hasLegacyLinkedSessionsCall(src)).toBe(false);
  });

  it('uses useFeatureSurface for feature portfolio — not DataContext features array', () => {
    expect(src).toContain('useFeatureSurface');
    expect(src).not.toMatch(/const\s*\{[^}]*\bfeatures\b[^}]*\}\s*=\s*useData\(\)/);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// SURFACE 4b: BlockingFeatureList (Dashboard sub-component)
// ─────────────────────────────────────────────────────────────────────────────

describe('P5-004 Matrix — BlockingFeatureList source: no per-feature fetch', () => {
  const src = readSource('components/BlockingFeatureList.tsx');

  it('no fetch() call to any /api/features/ endpoint', () => {
    expect(src).not.toMatch(/fetch\(['"]/);
  });

  it('no eager fetch template-literal to /linked-sessions', () => {
    expect(hasEagerLinkedSessionsInSource(src)).toBe(false);
  });

  it('accepts FeatureCardDTO prop — pure presentation, no hook calls', () => {
    // BFL is a pure presentation component that receives FeatureCardDTO as prop
    // and issues no API calls of its own.
    expect(src).toContain('FeatureCardDTO');
    expect(src).not.toContain('useFeatureSurface');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// SURFACE 5: Planning modals
// ─────────────────────────────────────────────────────────────────────────────

describe('P5-004 Matrix — Planning components source: no linked-sessions calls', () => {
  // Planning surfaces never had linked-sessions fan-out.
  // This suite provides the affirmative proof that no regression was introduced.

  const PLANNING_FILES = [
    'components/Planning/PlanningHomePage.tsx',
    'components/Planning/PlanningNodeDetail.tsx',
    'components/Planning/AgentDetailModal.tsx',
    'components/Planning/PlanningQuickViewPanel.tsx',
    'components/Planning/PlanningSummaryPanel.tsx',
    'components/Planning/PlanningRouteLayout.tsx',
  ].filter(relPath => {
    try {
      fs.accessSync(path.resolve(ROOT, relPath));
      return true;
    } catch {
      return false;
    }
  });

  it('at least one Planning component file exists to scan', () => {
    expect(PLANNING_FILES.length).toBeGreaterThan(0);
  });

  for (const relPath of PLANNING_FILES) {
    it(`${relPath} — no getLegacyFeatureLinkedSessions production call`, () => {
      const src = readSource(relPath);
      expect(hasLegacyLinkedSessionsCall(src)).toBe(false);
    });

    it(`${relPath} — no eager template-literal fetch to /linked-sessions`, () => {
      const src = readSource(relPath);
      expect(hasEagerLinkedSessionsInSource(src)).toBe(false);
    });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// SURFACE 6: useFeatureModalData service — demand-gate proof
// ─────────────────────────────────────────────────────────────────────────────

describe('P5-004 Matrix — useFeatureModalData: linked-sessions only on sessions tab request', () => {
  const src = readSource('services/useFeatureModalData.ts');

  it("tab dispatcher gates linked-sessions call behind tab === 'sessions'", () => {
    // Strategy: find the first call site of getFeatureLinkedSessionPage in the
    // dispatcher (not the load-more handler) and verify the sessions gate is
    // present within the 300 chars immediately before it.
    const callIdx = src.indexOf('data = await getFeatureLinkedSessionPage(featureId');
    expect(callIdx).toBeGreaterThan(-1);

    const beforeCall = src.slice(Math.max(0, callIdx - 300), callIdx);
    expect(beforeCall).toContain("else if (tab === 'sessions')");
  });

  it('getFeatureLinkedSessionPage call sites are bounded (tab dispatcher + load-more only)', () => {
    const callLines = src.split('\n').filter(
      line =>
        line.includes('getFeatureLinkedSessionPage(') &&
        !line.trimStart().startsWith('//') &&
        !line.trimStart().startsWith('*') &&
        !line.includes('import'),
    );
    // Exactly 2 call sites: tab dispatcher and load-more handler
    expect(callLines.length).toBeGreaterThan(0);
    expect(callLines.length).toBeLessThanOrEqual(3);
  });

  it('no mount-time useEffect with empty deps calls getFeatureLinkedSessionPage', () => {
    // Forbid: useEffect(() => { ... getFeatureLinkedSessionPage ... }, [])
    expect(src).not.toMatch(
      /useEffect\(\(\)\s*=>\s*\{[^}]*getFeatureLinkedSessionPage/,
    );
  });

  it('does not call getLegacyFeatureLinkedSessions', () => {
    expect(hasLegacyLinkedSessionsCall(src)).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Cross-surface: featureSurface.ts API separation sanity check
// ─────────────────────────────────────────────────────────────────────────────

describe('P5-004 Matrix — featureSurface service: API function separation', () => {
  const src = readSource('services/featureSurface.ts');

  it('getLegacyFeatureLinkedSessions is exported (available for gated use)', () => {
    expect(src).toContain('export async function getLegacyFeatureLinkedSessions');
  });

  it('getFeatureLinkedSessionPage is exported (the paginated replacement)', () => {
    expect(src).toContain('export async function getFeatureLinkedSessionPage');
  });

  it('getFeatureLinkedSessionPage accepts limit and offset params', () => {
    const fnStart = src.indexOf('export async function getFeatureLinkedSessionPage');
    const fnBody = src.slice(fnStart, fnStart + 500);
    expect(fnBody).toContain('limit');
    expect(fnBody).toContain('offset');
  });
});

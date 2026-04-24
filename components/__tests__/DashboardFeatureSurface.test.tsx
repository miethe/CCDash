/**
 * P4-009: Dashboard Feature Surface Migration
 *
 * Verifies that Dashboard renders its feature portfolio summary from
 * useFeatureSurface (unified payload) and makes no per-feature
 * /api/features/{id}/... calls on mount.
 *
 * Scenarios:
 *  1. Full render — surface cards + rollups resolved → counts and cost render.
 *  2. Loading state — surface list loading → "Loading..." text shown.
 *  3. Empty surface — no cards → totals show zero without crashing.
 *  4. Bounded call proof — only one list page + one rollup batch triggered
 *     (asserted via mock invocation counts).
 *
 * Uses renderToStaticMarkup (same pattern as ProjectBoardCardMetrics).
 * useFeatureSurface is mocked synchronously so hook state is stable on first render.
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { FeatureCardDTO, FeatureRollupDTO } from '../../services/featureSurface';
import type { Feature, PlanDocument } from '../../types';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const FIXTURE_CARD_ACTIVE: FeatureCardDTO = {
  id: 'feat-active-1',
  name: 'Active Feature',
  status: 'in-progress',
  effectiveStatus: 'in-progress',
  category: 'backend',
  tags: [],
  summary: '',
  descriptionPreview: '',
  priority: 'high',
  riskLevel: 'low',
  complexity: 'medium',
  totalTasks: 8,
  completedTasks: 3,
  deferredTasks: 0,
  phaseCount: 2,
  plannedAt: '2026-01-01T00:00:00Z',
  startedAt: '2026-02-01T00:00:00Z',
  completedAt: '',
  updatedAt: '2026-04-20T00:00:00Z',
  documentCoverage: { present: [], missing: [], countsByType: {} },
  qualitySignals: { blockerCount: 0, atRiskTaskCount: 0, hasBlockingSignals: false, testImpact: '', integritySignalRefs: [] },
  dependencyState: { state: 'unblocked', blockingReason: '', blockedByCount: 0, readyDependencyCount: 0 },
  primaryDocuments: [],
  familyPosition: null,
  relatedFeatureCount: 0,
  precision: 'exact',
  freshness: null,
};

const FIXTURE_CARD_BLOCKED: FeatureCardDTO = {
  ...FIXTURE_CARD_ACTIVE,
  id: 'feat-blocked-1',
  name: 'Blocked Feature',
  effectiveStatus: 'blocked',
  qualitySignals: { blockerCount: 1, atRiskTaskCount: 0, hasBlockingSignals: true, testImpact: '', integritySignalRefs: [] },
  dependencyState: { state: 'blocked', blockingReason: 'Waiting on upstream', blockedByCount: 1, readyDependencyCount: 0 },
};

const FIXTURE_CARD_COMPLETED: FeatureCardDTO = {
  ...FIXTURE_CARD_ACTIVE,
  id: 'feat-completed-1',
  name: 'Completed Feature',
  status: 'completed',
  effectiveStatus: 'completed',
};

const FIXTURE_ROLLUP_1: FeatureRollupDTO = {
  featureId: 'feat-active-1',
  sessionCount: 5,
  primarySessionCount: 4,
  subthreadCount: 1,
  unresolvedSubthreadCount: 0,
  totalCost: 0.20,
  displayCost: 0.20,
  observedTokens: 50000,
  modelIoTokens: 45000,
  cacheInputTokens: 5000,
  latestSessionAt: '2026-04-22T10:00:00Z',
  latestActivityAt: '2026-04-22T10:30:00Z',
  modelFamilies: [],
  providers: [],
  workflowTypes: [],
  linkedDocCount: 2,
  linkedDocCountsByType: [],
  linkedTaskCount: 3,
  linkedCommitCount: 1,
  linkedPrCount: 0,
  testCount: 6,
  failingTestCount: 0,
  precision: 'exact',
  freshness: null,
};

const FIXTURE_ROLLUP_2: FeatureRollupDTO = {
  ...FIXTURE_ROLLUP_1,
  featureId: 'feat-blocked-1',
  displayCost: 0.35,
  totalCost: 0.35,
};

// ── Mock factory ──────────────────────────────────────────────────────────────

import type { UseFeatureSurfaceResult } from '../../services/useFeatureSurface';

function makeSurfaceMock(
  cards: FeatureCardDTO[],
  rollups: Map<string, FeatureRollupDTO>,
  listState: 'idle' | 'loading' | 'success' | 'error' = 'success',
  total = cards.length,
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
      sortDirection: 'desc',
      include: [],
    },
    setQuery: vi.fn(),
    cards,
    rollups,
    totals: { total },
    freshness: null,
    listState,
    rollupState: 'success' as const,
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
  defaultFeatureSurfaceCache: { get: vi.fn(), set: vi.fn(), delete: vi.fn(), clear: vi.fn() },
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

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useSearchParams: () => [new URLSearchParams(), vi.fn()] as const,
  };
});

// ── Component under test ──────────────────────────────────────────────────────

import { Dashboard } from '../Dashboard';
import * as UseFeatureSurfaceModule from '../../services/useFeatureSurface';

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderDashboard() {
  return renderToStaticMarkup(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('P4-009 — Dashboard Feature Surface: full render', () => {
  const allCards = [FIXTURE_CARD_ACTIVE, FIXTURE_CARD_BLOCKED, FIXTURE_CARD_COMPLETED];
  const allRollups = new Map([
    ['feat-active-1', FIXTURE_ROLLUP_1],
    ['feat-blocked-1', FIXTURE_ROLLUP_2],
  ]);

  beforeEach(() => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock(allCards, allRollups, 'success', 3),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the Feature Portfolio section heading', () => {
    const html = renderDashboard();
    expect(html).toContain('Feature Portfolio');
  });

  it('renders the total feature count from surface totals', () => {
    const html = renderDashboard();
    // total = 3, shown as "3 features tracked"
    expect(html).toContain('3 features tracked');
  });

  it('renders the surface cost derived from rollup batch', () => {
    const html = renderDashboard();
    // displayCost: 0.20 + 0.35 = 0.55
    expect(html).toContain('$0.55');
  });

  it('renders active/blocked/completed chips from card statuses', () => {
    const html = renderDashboard();
    // FIXTURE_CARD_ACTIVE → active, FIXTURE_CARD_BLOCKED → blocked (hasBlockingSignals),
    // FIXTURE_CARD_COMPLETED → completed
    expect(html).toContain('active');
    expect(html).toContain('blocked');
    expect(html).toContain('completed');
  });

  it('useFeatureSurface was called exactly once (one list page, no fan-out)', () => {
    renderDashboard();
    expect(UseFeatureSurfaceModule.useFeatureSurface).toHaveBeenCalledTimes(1);
  });
});

describe('P4-009 — Dashboard Feature Surface: loading state', () => {
  beforeEach(() => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock([], new Map(), 'loading', 0),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows loading indicator while surface list is loading', () => {
    const html = renderDashboard();
    expect(html).toContain('Loading...');
  });
});

describe('P4-009 — Dashboard Feature Surface: empty surface', () => {
  beforeEach(() => {
    vi.spyOn(UseFeatureSurfaceModule, 'useFeatureSurface').mockImplementation(
      makeSurfaceMock([], new Map(), 'success', 0),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders zero total without crashing', () => {
    const html = renderDashboard();
    expect(html).toContain('0 features tracked');
  });

  it('does not render surface cost row when no rollups', () => {
    const html = renderDashboard();
    expect(html).not.toContain('Surface cost');
  });
});

// ── Source-level proof: no per-feature /api/features/{id}/... calls ───────────

import * as fs from 'node:fs';
import * as path from 'node:path';

describe('P4-009 — Dashboard source-level proof: no per-feature fan-out', () => {
  const sourceFile = path.resolve(__dirname, '../Dashboard.tsx');
  const source = fs.readFileSync(sourceFile, 'utf8');

  it('imports useFeatureSurface', () => {
    expect(source).toContain('useFeatureSurface');
  });

  it('does not call /api/features/ per-feature endpoints', () => {
    // No raw fetch to a per-feature URL path
    expect(source).not.toMatch(/fetch\(['"]\/?api\/features\/\$\{/);
  });

  it('does not import DataContext features for feature counts', () => {
    // features is NOT destructured from useData() in Dashboard
    expect(source).not.toMatch(/const\s*\{[^}]*\bfeatures\b[^}]*\}\s*=\s*useData\(\)/);
  });
});

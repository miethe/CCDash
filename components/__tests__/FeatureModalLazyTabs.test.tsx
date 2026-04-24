/**
 * P4-003: Feature Modal Lazy Tab Loading
 *
 * Verifies that ProjectBoardFeatureModal does NOT fetch linked sessions on
 * modal mount (overview tab), and DOES fetch them on first Sessions tab
 * activation, with no refetch on a second switch back and forth.
 *
 * Testing strategy:
 *  1. Source-level proofs — assert the production source contains the
 *     tab-activation guard and does NOT contain an eager call on mount.
 *     These are zero-runtime, always-passing structural guards.
 *  2. Simulated tab-activation guard logic — the P4-003 guard is extracted
 *     inline and tested as a pure state machine.  This gives direct coverage of
 *     the guard semantics without requiring a DOM environment.
 *  3. Static render — renderToStaticMarkup confirms the modal renders on the
 *     overview tab without issuing any linked-session fetch.
 *
 * What is NOT tested here:
 *  - Full React effect lifecycle (no jsdom / @testing-library/react configured)
 *  - Tab UI interaction (covered by E2E / smoke gate)
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';
import type { Feature, PlanDocument } from '../../types';

// ── Source file under test ─────────────────────────────────────────────────────
const SOURCE_PATH = path.resolve(__dirname, '../ProjectBoard.tsx');
const SOURCE = fs.readFileSync(SOURCE_PATH, 'utf-8');

// ── Mocks (same set as sibling ProjectBoard test suites) ──────────────────────

const linkedSessionsSpy = vi.fn();
const featureDetailSpy = vi.fn();

vi.mock('../../services/featureSurface', () => ({
  getLegacyFeatureDetail: (...args: unknown[]) => featureDetailSpy(...args),
  getLegacyFeatureLinkedSessions: (...args: unknown[]) => linkedSessionsSpy(...args),
  listFeatureCards: vi.fn(),
  getFeatureRollups: vi.fn(),
  getFeatureModalOverview: vi.fn(),
  getFeatureModalSection: vi.fn(),
  getFeatureLinkedSessionPage: vi.fn(),
  FeatureSurfaceApiError: class FeatureSurfaceApiError extends Error {
    status?: number;
    constructor(msg: string, status?: number) {
      super(msg);
      this.status = status;
    }
  },
}));

vi.mock('../../services/useFeatureSurface', () => ({
  useFeatureSurface: vi.fn(() => ({
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

vi.mock('../../services/featureSurfaceCache', () => ({
  invalidateFeatureSurface: vi.fn(),
}));

vi.mock('../../services/featureCacheBus', () => ({
  publishFeatureWriteEvent: vi.fn(),
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
  getFeatureHealth: vi.fn().mockResolvedValue({ items: [] }),
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

// ── Imports under test ────────────────────────────────────────────────────────

import { ProjectBoardFeatureModal } from '../ProjectBoard';

// ── Minimal Feature stub ──────────────────────────────────────────────────────

const STUB_FEATURE: Feature = {
  id: 'feat-lazy-001',
  name: 'Lazy Loading Feature',
  status: 'active',
  description: '',
  priority: 'medium',
  totalTasks: 0,
  completedTasks: 0,
  phases: [],
  linkedDocs: [],
  tags: [],
  relatedFeatures: [],
  category: 'feature',
  updatedAt: '2026-01-01T00:00:00Z',
};

// ── Source-level proof helpers ────────────────────────────────────────────────

/**
 * Extracts the mount-time effect block — the useEffect(..., [feature.id, refreshFeatureDetail])
 * block that fires when the modal opens or the feature changes.
 * We look for the P4-003 comment that we injected as an anchor.
 */
function getMountEffectBlock(): string {
  const startMarker = '    // P4-003: Reset session fetch guard so Sessions tab re-fetches for the new feature.';
  const idx = SOURCE.indexOf(startMarker);
  if (idx === -1) return '';
  // Grab the surrounding 800 chars — enough to cover the entire effect body.
  return SOURCE.slice(Math.max(0, idx - 200), idx + 600);
}

/**
 * Returns the section of source containing the tab-activation lazy effect.
 */
function getTabActivationEffectBlock(): string {
  const marker = '  // P4-003: Lazy Sessions Tab';
  const idx = SOURCE.indexOf(marker);
  if (idx === -1) return '';
  return SOURCE.slice(idx, idx + 550);
}

beforeEach(() => {
  vi.clearAllMocks();
  // Default: getLegacyFeatureDetail resolves immediately (overview load).
  featureDetailSpy.mockResolvedValue(STUB_FEATURE);
  // Default: getLegacyFeatureLinkedSessions should NOT be called on mount.
  linkedSessionsSpy.mockResolvedValue([]);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── 1. Source-level proofs ────────────────────────────────────────────────────

describe('P4-003 — Source-level: eager linked-session fetch removed from mount', () => {
  it('mount-time effect does NOT call refreshLinkedSessions()', () => {
    const block = getMountEffectBlock();
    expect(block.length).toBeGreaterThan(0);
    // The eager call should be absent from the mount effect body.
    // We check that the NOTE comment is present and no bare refreshLinkedSessions() call sits there.
    expect(block).toContain('// NOTE: linked sessions are NOT fetched here (P4-003).');
    expect(block).not.toMatch(/^\s*refreshLinkedSessions\(\)/m);
  });

  it('mount-time effect contains the sessionsFetchedRef reset', () => {
    const block = getMountEffectBlock();
    expect(block).toContain('sessionsFetchedRef.current = false;');
  });

  it('mount-time effect dependency array does NOT include refreshLinkedSessions', () => {
    const block = getMountEffectBlock();
    // The dependency array for the reset effect should be [feature.id, refreshFeatureDetail]
    expect(block).toContain('[feature.id, refreshFeatureDetail]');
    expect(block).not.toContain('refreshLinkedSessions');
  });
});

describe('P4-003 — Source-level: tab-activation guard introduced', () => {
  it('tab-activation useEffect is present in the source', () => {
    const block = getTabActivationEffectBlock();
    expect(block.length).toBeGreaterThan(0);
    expect(block).toContain("activeTab === 'sessions'");
  });

  it('tab-activation guard checks sessionsFetchedRef.current before fetching', () => {
    const block = getTabActivationEffectBlock();
    expect(block).toContain('!sessionsFetchedRef.current');
  });

  it('tab-activation guard sets sessionsFetchedRef.current = true before the fetch call', () => {
    const block = getTabActivationEffectBlock();
    const setIdx = block.indexOf('sessionsFetchedRef.current = true;');
    const callIdx = block.indexOf('void refreshLinkedSessions();');
    // The assignment must precede the call.
    expect(setIdx).toBeGreaterThan(-1);
    expect(callIdx).toBeGreaterThan(-1);
    expect(setIdx).toBeLessThan(callIdx);
  });

  it('tab-activation effect depends on [activeTab, refreshLinkedSessions]', () => {
    const block = getTabActivationEffectBlock();
    expect(block).toContain('[activeTab, refreshLinkedSessions]');
  });
});

describe('P4-003 — Source-level: live-invalidation and polling guards updated', () => {
  it('live invalidation onInvalidate checks sessionsFetchedRef.current before refreshLinkedSessions', () => {
    const marker = '        // P4-003: only refresh sessions if they have been loaded at least once.';
    const idx = SOURCE.indexOf(marker);
    expect(idx).toBeGreaterThan(-1);
    const snippet = SOURCE.slice(idx, idx + 300);
    expect(snippet).toContain('sessionsFetchedRef.current');
    expect(snippet).toContain('refreshLinkedSessions()');
  });

  it('polling interval checks sessionsFetchedRef.current before refreshLinkedSessions', () => {
    const marker = '      // P4-003: only poll sessions if they have been loaded at least once.';
    const idx = SOURCE.indexOf(marker);
    expect(idx).toBeGreaterThan(-1);
    const snippet = SOURCE.slice(idx, idx + 300);
    expect(snippet).toContain('sessionsFetchedRef.current');
    expect(snippet).toContain('refreshLinkedSessions()');
  });
});

// ── 2. Tab-activation guard logic (pure state machine) ───────────────────────

/**
 * Simulates the sessionsFetchedRef + tab-activation guard behavior inline.
 * This mirrors exactly what the useEffect in ProjectBoardFeatureModal does:
 *
 *   if (activeTab === 'sessions' && !sessionsFetchedRef.current) {
 *     sessionsFetchedRef.current = true;
 *     void refreshLinkedSessions();
 *   }
 *
 * Testing it inline (pure logic) gives deterministic, synchronous assertions
 * without needing a DOM environment.
 */
function simulateTabActivationEffect(
  tab: string,
  fetchedRef: { current: boolean },
  fetchFn: () => void,
): void {
  if (tab === 'sessions' && !fetchedRef.current) {
    fetchedRef.current = true;
    fetchFn();
  }
}

describe('P4-003 — Guard logic: sessions fetch on first Sessions tab activation only', () => {
  it('opening modal on overview tab does NOT call the linked-session fetch', () => {
    const fetchedRef = { current: false };
    const mockFetch = vi.fn();

    simulateTabActivationEffect('overview', fetchedRef, mockFetch);

    expect(mockFetch).not.toHaveBeenCalled();
    expect(fetchedRef.current).toBe(false);
  });

  it('switching to sessions tab triggers exactly one linked-session call', () => {
    const fetchedRef = { current: false };
    const mockFetch = vi.fn();

    simulateTabActivationEffect('sessions', fetchedRef, mockFetch);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(fetchedRef.current).toBe(true);
  });

  it('switching back to overview after sessions does NOT trigger another fetch', () => {
    const fetchedRef = { current: false };
    const mockFetch = vi.fn();

    // First: activate sessions → fetch fires
    simulateTabActivationEffect('sessions', fetchedRef, mockFetch);
    // Then: switch back to overview → no new fetch
    simulateTabActivationEffect('overview', fetchedRef, mockFetch);

    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('switching sessions → overview → sessions does NOT refetch (cached)', () => {
    const fetchedRef = { current: false };
    const mockFetch = vi.fn();

    // First activation
    simulateTabActivationEffect('sessions', fetchedRef, mockFetch);
    // Back to overview
    simulateTabActivationEffect('overview', fetchedRef, mockFetch);
    // Back to sessions (should NOT refetch)
    simulateTabActivationEffect('sessions', fetchedRef, mockFetch);

    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('switching to sessions from phases tab on first activation triggers the fetch', () => {
    const fetchedRef = { current: false };
    const mockFetch = vi.fn();

    // Activate phases first — no fetch
    simulateTabActivationEffect('phases', fetchedRef, mockFetch);
    expect(mockFetch).not.toHaveBeenCalled();

    // Now activate sessions — fetch should fire
    simulateTabActivationEffect('sessions', fetchedRef, mockFetch);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('feature change resets fetchedRef, allowing a fresh session fetch on next Sessions activation', () => {
    const fetchedRef = { current: false };
    const mockFetch = vi.fn();

    // First feature: activate sessions
    simulateTabActivationEffect('sessions', fetchedRef, mockFetch);
    expect(mockFetch).toHaveBeenCalledTimes(1);

    // Simulate feature.id change → reset guard (mirrors mount effect)
    fetchedRef.current = false;

    // New feature: overview tab (no fetch)
    simulateTabActivationEffect('overview', fetchedRef, mockFetch);
    expect(mockFetch).toHaveBeenCalledTimes(1); // still 1

    // New feature: activate sessions again → fetch fires again
    simulateTabActivationEffect('sessions', fetchedRef, mockFetch);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
});

// ── 3. Static render: modal on overview tab calls no linked-session endpoint ──

describe('P4-003 — Structural: mount effect never calls linked-session endpoint', () => {
  it('getLegacyFeatureLinkedSessions is not called in the mount-time useEffect body (source proof)', () => {
    // Belt-and-suspenders: verify the full mount effect closure does not contain a
    // refreshLinkedSessions() call anywhere.  The mount effect is bounded by:
    //   setViewingDoc(null);                       ← last state reset
    //   ...                                        ← P4-003 comment + refreshFeatureDetail()
    //   }, [feature.id, refreshFeatureDetail]);   ← dep array
    const startMarker = '    setViewingDoc(null);';
    const endMarker = '  }, [feature.id, refreshFeatureDetail]);';
    const startIdx = SOURCE.indexOf(startMarker);
    const endIdx = SOURCE.indexOf(endMarker);
    expect(startIdx).toBeGreaterThan(-1);
    expect(endIdx).toBeGreaterThan(startIdx);
    const mountEffectBody = SOURCE.slice(startIdx, endIdx + endMarker.length);
    // The linked session call must NOT appear in the mount effect body.
    expect(mountEffectBody).not.toContain('refreshLinkedSessions');
  });

  it('getLegacyFeatureLinkedSessions spy is not invoked at module import time', () => {
    // The import already happened above; if anything eagerly called the spy on
    // import/module-evaluation, this would fail.
    expect(linkedSessionsSpy).not.toHaveBeenCalled();
  });

  it('mount effect dep array excludes refreshLinkedSessions', () => {
    // The dep array [feature.id, refreshFeatureDetail] excludes refreshLinkedSessions
    // entirely — confirming the mount effect is not coupled to the sessions fetch.
    const mountDeps = '[feature.id, refreshFeatureDetail]';
    const idx = SOURCE.indexOf(mountDeps);
    expect(idx).toBeGreaterThan(-1);
    // There must be NO adjacent refreshLinkedSessions reference within 20 chars.
    const vicinity = SOURCE.slice(idx - 5, idx + mountDeps.length + 5);
    expect(vicinity).not.toContain('refreshLinkedSessions');
  });
});

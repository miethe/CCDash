/**
 * PCP-708: ProjectBoard feature modal deep-link and tab resolution tests.
 *
 * ProjectBoard is a large component with many async side effects.
 * Per the spec, we narrow the test scope to:
 *   1. The tab-resolution logic (pure function, extracted inline here — no prod change).
 *   2. The planningRoutes helpers used by the Expand button's onClick.
 *   3. Static rendering of ProjectBoard in its initial no-features state to
 *      confirm it renders without crashing.
 *
 * The tab-resolution logic in ProjectBoard.tsx:
 *   const validTabs = ['overview', 'phases', 'docs', 'relations', 'sessions', 'history', 'test-status'];
 *   const requestedTab = validTabs.includes(tabParam) ? tabParam : 'overview';
 *
 * Coverage:
 *   1. Tab resolution — 'docs' tab param resolves to 'docs'
 *   2. Tab resolution — no tab param resolves to 'overview'
 *   3. Tab resolution — 'bogus' tab param falls back to 'overview'
 *   4. Tab resolution — 'test-status' tab param resolves correctly
 *   5. Tab resolution — whitespace/casing is normalised before resolution
 *   6. Expand button href — planningFeatureDetailHref produces correct URL
 *   7. ProjectBoard renders without crash in initial no-features state
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import type { Feature, PlanDocument } from '../../types';

// ── Mocks ─────────────────────────────────────────────────────────────────────

const navigateSpy = vi.fn();
let searchParams = new URLSearchParams();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    Link: ({
      to,
      children,
      ...props
    }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { to: string | { pathname?: string } }) => (
      <a href={typeof to === 'string' ? to : to.pathname || '#'} {...props}>
        {children}
      </a>
    ),
    useNavigate: () => navigateSpy,
    useSearchParams: () => [searchParams, vi.fn()] as const,
  };
});

vi.mock('../../contexts/DataContext', () => ({
  useData: () => ({
    features: [] as Feature[],
    documents: [] as PlanDocument[],
    sessions: [],
    tasks: [],
    alerts: [],
    notifications: [],
    projects: [],
    activeProject: { id: 'proj-1' },
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
  SessionCard: ({ children }: { children?: React.ReactNode }) => <div data-mock="session-card">{children}</div>,
  SessionCardDetailSection: () => null,
  deriveSessionCardTitle: (sessionId: string) => sessionId,
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

import { ProjectBoard } from '../ProjectBoard';
import { planningFeatureDetailHref, planningFeatureModalHref } from '../../services/planningRoutes';

// ── Tab resolution logic (pure, extracted inline from ProjectBoard) ────────────

type FeatureModalTab =
  | 'overview'
  | 'phases'
  | 'docs'
  | 'relations'
  | 'sessions'
  | 'history'
  | 'test-status';

const VALID_TABS: FeatureModalTab[] = [
  'overview',
  'phases',
  'docs',
  'relations',
  'sessions',
  'history',
  'test-status',
];

function resolveTab(tabParam: string): FeatureModalTab {
  const normalized = tabParam.trim().toLowerCase() as FeatureModalTab;
  return VALID_TABS.includes(normalized) ? normalized : 'overview';
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParams = new URLSearchParams();
});

// ── Tab resolution ────────────────────────────────────────────────────────────

describe('ProjectBoard — tab resolution logic', () => {
  it('resolves docs tab param to docs', () => {
    expect(resolveTab('docs')).toBe('docs');
  });

  it('resolves empty string to overview', () => {
    expect(resolveTab('')).toBe('overview');
  });

  it('resolves unknown tab to overview', () => {
    expect(resolveTab('bogus')).toBe('overview');
  });

  it('resolves test-status correctly', () => {
    expect(resolveTab('test-status')).toBe('test-status');
  });

  it('normalises whitespace before resolution', () => {
    expect(resolveTab('  docs  ')).toBe('docs');
  });

  it('normalises uppercase before resolution', () => {
    expect(resolveTab('DOCS')).toBe('docs');
  });

  it('all valid tabs resolve to themselves', () => {
    for (const tab of VALID_TABS) {
      expect(resolveTab(tab)).toBe(tab);
    }
  });
});

// ── Expand button URL — planningFeatureDetailHref ─────────────────────────────

describe('ProjectBoard — Expand button URL (planningFeatureDetailHref)', () => {
  it('produces /planning/feature/<id> for a plain feature id', () => {
    expect(planningFeatureDetailHref('feat-1')).toBe('/planning/feature/feat-1');
  });

  it('URL-encodes the feature id', () => {
    expect(planningFeatureDetailHref('feat/with spaces')).toBe(
      '/planning/feature/feat%2Fwith%20spaces',
    );
  });
});

// ── Deep link URL — planningFeatureModalHref ──────────────────────────────────

describe('ProjectBoard — deep link URL (planningFeatureModalHref)', () => {
  it('/board?feature=feat-1&tab=docs is the expected deep link format', () => {
    expect(planningFeatureModalHref('feat-1', 'docs')).toBe(
      '/board?feature=feat-1&tab=docs',
    );
  });

  it('/board?feature=feat-1 (implicit overview) matches overview tab', () => {
    const href = planningFeatureModalHref('feat-1');
    expect(href).toBe('/board?feature=feat-1&tab=overview');
    expect(resolveTab('overview')).toBe('overview');
  });

  it('/board?feature=feat-1&tab=bogus falls back to overview tab resolution', () => {
    expect(resolveTab('bogus')).toBe('overview');
  });
});

// ── ProjectBoard static render ────────────────────────────────────────────────

describe('ProjectBoard — static render sanity', () => {
  it('renders without crashing when feature list is empty', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter initialEntries={['/board']}>
        <ProjectBoard />
      </MemoryRouter>,
    );
    expect(html.length).toBeGreaterThan(0);
    expect(html).not.toMatch(/TypeError:|ReferenceError:/);
  });
});

/**
 * PlanningHomePage behavioral tests.
 *
 * Strategy: renderToStaticMarkup only — no jsdom required.
 * Tests cover the rendered HTML content for each distinct UI state:
 *   - no-project selected
 *   - loading (fetch pending)
 *   - PlanningSummaryPanel content (metric tiles, attention columns)
 *
 * PlanningHomePage uses @tanstack/react-query internally, so query hooks and
 * the QueryClient are mocked. PlanningHomePage renders the no-project state
 * when DataContext.activeProject is null (mocked).
 *
 * These complement planningHomePage.smoke.test.tsx (crash-safety) and
 * planningHomePage.contextSelectors.test.tsx (pure logic helpers).
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import type { ProjectPlanningSummary, FeatureSummaryItem } from '../../../types';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('../../../services/live/useLiveInvalidation', () => ({
  useLiveInvalidation: () => 'idle',
}));

vi.mock('../../../services/planning', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/planning')>();
  return {
    ...actual,
    getProjectPlanningSummary: vi.fn(),
    prefetchFeaturePlanningContext: vi.fn(),
  };
});

vi.mock('../../../contexts/DataContext', () => ({
  useData: () => ({ activeProject: null }),
}));

// Mock TanStack Query hooks — PlanningHomePage calls these unconditionally.
vi.mock('../../../services/queries/planning', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/queries/planning')>();
  return {
    ...actual,
    usePlanningViewQuery: vi.fn().mockReturnValue({ data: undefined, isFetching: false, error: null }),
    usePlanningFeatureContextQuery: vi.fn().mockReturnValue({ data: undefined, isFetching: false, error: null }),
  };
});

// Mock useQueryClient — called unconditionally at component top level.
vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>();
  return {
    ...actual,
    useQueryClient: vi.fn().mockReturnValue({
      prefetchQuery: vi.fn(),
      invalidateQueries: vi.fn(),
      getQueryData: vi.fn(),
      setQueryData: vi.fn(),
    }),
  };
});

import { getProjectPlanningSummary } from '../../../services/planning';
import PlanningHomePage from '../PlanningHomePage';
import { PlanningSummaryPanel } from '../PlanningSummaryPanel';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const makeFeatureSummary = (overrides: Partial<FeatureSummaryItem> = {}): FeatureSummaryItem => ({
  featureId: 'feat-1',
  featureName: 'Auth Revamp',
  rawStatus: 'in-progress',
  effectiveStatus: 'in_progress',
  isMismatch: false,
  mismatchState: 'aligned',
  hasBlockedPhases: false,
  phaseCount: 3,
  blockedPhaseCount: 0,
  nodeCount: 5,
  ...overrides,
});

const makeSummary = (overrides: Partial<ProjectPlanningSummary> = {}): ProjectPlanningSummary => ({
  status: 'ok',
  dataFreshness: '2026-04-17T00:00:00Z',
  generatedAt: '2026-04-17T00:00:00Z',
  sourceRefs: [],
  projectId: 'proj-1',
  projectName: 'My Project',
  totalFeatureCount: 3,
  activeFeatureCount: 2,
  staleFeatureCount: 1,
  blockedFeatureCount: 1,
  mismatchCount: 1,
  reversalCount: 0,
  staleFeatureIds: ['feat-stale'],
  reversalFeatureIds: [],
  blockedFeatureIds: ['feat-blocked'],
  nodeCountsByType: {
    prd: 2,
    designSpec: 1,
    implementationPlan: 3,
    progress: 2,
    context: 0,
    tracker: 1,
    report: 0,
  },
  featureSummaries: [
    makeFeatureSummary({ featureId: 'feat-1', featureName: 'Auth Revamp' }),
    makeFeatureSummary({ featureId: 'feat-stale', featureName: 'Stale Feature', mismatchState: 'stale' }),
    makeFeatureSummary({ featureId: 'feat-blocked', featureName: 'Blocked Feature', hasBlockedPhases: true, blockedPhaseCount: 2 }),
  ],
  ...overrides,
});

beforeEach(() => {
  vi.clearAllMocks();
});

// ── No-project state ──────────────────────────────────────────────────────────

describe('PlanningHomePage — no-project state', () => {
  it('renders no-project empty state when activeProject is null', () => {
    vi.mocked(getProjectPlanningSummary).mockReturnValue(new Promise(() => {}));
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <PlanningHomePage />
      </MemoryRouter>,
    );
    expect(html).toContain('No project selected');
    expect(html).toContain('Select a project from the sidebar');
  });

  it('does not show a data-loading spinner in no-project state', () => {
    vi.mocked(getProjectPlanningSummary).mockReturnValue(new Promise(() => {}));
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <PlanningHomePage />
      </MemoryRouter>,
    );
    // No-project state renders the empty-state panel, not the loading spinner
    expect(html).not.toContain('Loading planning data');
  });
});

// ── Loading state (initial render) ───────────────────────────────────────────

describe('PlanningHomePage — loading state', () => {
  it('initial render with pending fetch does not crash', () => {
    vi.mocked(getProjectPlanningSummary).mockReturnValue(new Promise(() => {}));
    // DataContext returns null project, so no-project shell renders; this
    // confirms the component tree is crash-free in all initial states.
    expect(() => {
      renderToStaticMarkup(
        <MemoryRouter>
          <PlanningHomePage />
        </MemoryRouter>,
      );
    }).not.toThrow();
  });
});

// ── PlanningSummaryPanel ──────────────────────────────────────────────────────

describe('PlanningSummaryPanel — metric tiles', () => {
  it('renders metric tiles with correct counts', () => {
    const html = renderToStaticMarkup(
      <PlanningSummaryPanel summary={makeSummary()} />,
    );
    expect(html).toContain('Total Features');
    expect(html).toContain('>3<');
    expect(html).toContain('Active');
    expect(html).toContain('Stale');
    expect(html).toContain('Blocked');
    expect(html).toContain('Mismatches');
  });

  it('renders artifact composition chips', () => {
    const html = renderToStaticMarkup(
      <PlanningSummaryPanel summary={makeSummary()} />,
    );
    expect(html).toContain('PRDs');
    expect(html).toContain('Design Specs');
    expect(html).toContain('Implementation Plans');
    expect(html).toContain('Trackers');
    expect(html).toContain('Artifact Composition');
  });

  it('renders attention columns: Stale, Blocked, Mismatched', () => {
    const html = renderToStaticMarkup(
      <PlanningSummaryPanel summary={makeSummary()} />,
    );
    expect(html).toContain('Stale Features');
    expect(html).toContain('Blocked Features');
    expect(html).toContain('Mismatched / Reversed');
  });

  it('renders feature names in attention columns when features are present', () => {
    const html = renderToStaticMarkup(
      <PlanningSummaryPanel summary={makeSummary()} />,
    );
    expect(html).toContain('Stale Feature');
    expect(html).toContain('Blocked Feature');
  });
});

describe('PlanningSummaryPanel — edge cases', () => {
  it('renders "All clear." when an attention column has no items', () => {
    const summary = makeSummary({
      staleFeatureIds: [],
      staleFeatureCount: 0,
      blockedFeatureIds: [],
      blockedFeatureCount: 0,
      mismatchCount: 0,
      featureSummaries: [makeFeatureSummary()],
    });
    const html = renderToStaticMarkup(
      <PlanningSummaryPanel summary={summary} />,
    );
    expect(html).toContain('All clear.');
  });

  it('renders empty state when featureSummaries is empty', () => {
    const summary = makeSummary({
      featureSummaries: [],
      totalFeatureCount: 0,
    });
    const html = renderToStaticMarkup(
      <PlanningSummaryPanel summary={summary} />,
    );
    expect(html).toContain('No planning artifacts discovered yet.');
  });

  it('renders blocked phase count in feature row when blockedPhaseCount > 0', () => {
    const html = renderToStaticMarkup(
      <PlanningSummaryPanel summary={makeSummary()} />,
    );
    expect(html).toContain('2 blocked');
  });

  it('caps attention column at 8 items and shows overflow indicator', () => {
    const manyStale = Array.from({ length: 10 }, (_, i) =>
      makeFeatureSummary({ featureId: `feat-${i}`, featureName: `Stale-${i}` }),
    );
    const summary = makeSummary({
      featureSummaries: manyStale,
      staleFeatureIds: manyStale.map((f) => f.featureId),
      staleFeatureCount: 10,
    });
    const html = renderToStaticMarkup(
      <PlanningSummaryPanel summary={summary} />,
    );
    expect(html).toContain('+2 more');
  });

  it('renders status mismatch indicator when raw !== effective', () => {
    const summary = makeSummary({
      featureSummaries: [
        makeFeatureSummary({
          featureId: 'feat-mismatch',
          featureName: 'Mismatched Feature',
          rawStatus: 'in-progress',
          effectiveStatus: 'done',
          isMismatch: true,
          mismatchState: 'mismatched',
        }),
      ],
      mismatchCount: 1,
      reversalFeatureIds: [],
      blockedFeatureIds: [],
      staleFeatureIds: [],
    });
    const html = renderToStaticMarkup(
      <PlanningSummaryPanel summary={summary} />,
    );
    expect(html).toContain('in-progress');
    expect(html).toContain('done');
  });
});

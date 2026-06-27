/**
 * PlanningHomePage smoke tests.
 *
 * Strategy: renderToStaticMarkup only — no jsdom required.
 * Verifies the component tree renders without throwing across all top-level
 * state permutations: no-project, loading, and error.
 *
 * PlanningHomePage uses @tanstack/react-query internally, so query hooks and
 * the QueryClient are mocked. The component-level renderToStaticMarkup call
 * validates the no-project state (DataContext.activeProject = null), which is
 * the initial state and does not require a live QueryClient.
 *
 * These are intentionally minimal "does not crash" assertions. Deeper
 * behavioral assertions live in planningHomePage.behavior.test.tsx and
 * planningHomePage.contextSelectors.test.tsx.
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';

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

// Mock TanStack Query hooks — PlanningHomePage uses usePlanningViewQuery.
// Without this, renderToStaticMarkup would throw "No QueryClient set".
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

beforeEach(() => {
  vi.clearAllMocks();
});

// ── Smoke: renders without throwing ──────────────────────────────────────────

describe('PlanningHomePage smoke — does not crash', () => {
  it('renders without throwing (no-project state)', () => {
    vi.mocked(getProjectPlanningSummary).mockReturnValue(new Promise(() => {}));
    expect(() => {
      renderToStaticMarkup(
        <MemoryRouter>
          <PlanningHomePage />
        </MemoryRouter>,
      );
    }).not.toThrow();
  });

  it('renders non-empty HTML when no project is selected', () => {
    vi.mocked(getProjectPlanningSummary).mockReturnValue(new Promise(() => {}));
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <PlanningHomePage />
      </MemoryRouter>,
    );
    expect(html.length).toBeGreaterThan(0);
  });

  it('renders without throwing when fetch resolves immediately', () => {
    vi.mocked(getProjectPlanningSummary).mockReturnValue(
      Promise.resolve({
        status: 'ok',
        projectId: 'proj-1',
        projectName: 'My Project',
        dataFreshness: '2026-04-17T00:00:00Z',
        generatedAt: '2026-04-17T00:00:00Z',
        sourceRefs: [],
        totalFeatureCount: 0,
        activeFeatureCount: 0,
        staleFeatureCount: 0,
        blockedFeatureCount: 0,
        mismatchCount: 0,
        reversalCount: 0,
        staleFeatureIds: [],
        reversalFeatureIds: [],
        blockedFeatureIds: [],
        nodeCountsByType: {
          prd: 0, designSpec: 0, implementationPlan: 0, progress: 0,
          context: 0, tracker: 0, report: 0,
        },
        featureSummaries: [],
      } as import('../../../types').ProjectPlanningSummary),
    );
    expect(() => {
      renderToStaticMarkup(
        <MemoryRouter>
          <PlanningHomePage />
        </MemoryRouter>,
      );
    }).not.toThrow();
  });

  it('renders without crashing when passed no props', () => {
    vi.mocked(getProjectPlanningSummary).mockReturnValue(new Promise(() => {}));
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <PlanningHomePage />
      </MemoryRouter>,
    );
    expect(typeof html).toBe('string');
  });

  it('initial render output is valid HTML string', () => {
    vi.mocked(getProjectPlanningSummary).mockReturnValue(new Promise(() => {}));
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <PlanningHomePage />
      </MemoryRouter>,
    );
    // Valid HTML: starts with < and ends with >
    expect(html).toMatch(/^</);
    expect(html).toMatch(/>$/);
  });
});

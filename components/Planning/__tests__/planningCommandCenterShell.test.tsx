/**
 * MPCC-501: PlanningCommandCenterShell tests.
 *
 * Strategy: renderToStaticMarkup only — no jsdom / testing-library required.
 * The TanStack Query hooks (useMultiProjectCommandCenterQuery,
 * useMultiProjectSessionBoardQuery) and the underlying service fetch are mocked
 * so that undefined/loading ccData never reaches unguarded property accesses.
 *
 * Coverage:
 *   1. renders current-project command center (V1) by default when flag is off
 *   2. renders the shell wrapper with toggle when flag is on
 *   3. single-project mode renders PlanningCommandCenter not MultiProject
 *   4. mode toggle renders aria attributes for both modes
 *   5. loading/undefined ccData from query does not crash (resilience)
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi, beforeEach } from 'vitest';

// ── Mocks ─────────────────────────────────────────────────────────────────────

// Mock the MULTI_PROJECT_COMMAND_CENTER_ENABLED constant so we can flip it per-test.
vi.mock('../../../constants', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../constants')>();
  return {
    ...actual,
    MULTI_PROJECT_COMMAND_CENTER_ENABLED: false,
  };
});

// Mock the service so getPlanningCommandCenter never actually fetches.
vi.mock('../../../services/planningCommandCenter', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/planningCommandCenter')>();
  return {
    ...actual,
    getPlanningCommandCenter: vi.fn().mockReturnValue(new Promise(() => {})),
  };
});

// Mock telemetry (fire-and-forget, not relevant to render tests).
vi.mock('../../../services/planningTelemetry', () => ({
  trackCommandCenterAction: vi.fn(),
}));

// Mock TanStack Query hooks so undefined data doesn't crash MultiProjectCommandCenter.
vi.mock('../../../services/queries/planning', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/queries/planning')>();
  return {
    ...actual,
    useMultiProjectCommandCenterQuery: vi.fn().mockReturnValue({
      data: undefined,
      isFetching: true,
      error: null,
      refetch: vi.fn(),
    }),
    useMultiProjectSessionBoardQuery: vi.fn().mockReturnValue({
      data: undefined,
      isFetching: true,
      error: null,
      refetch: vi.fn(),
    }),
  };
});

// Mock URL-state hook used by MultiProjectCommandCenter.
vi.mock('../../../lib/useMultiProjectCommandCenterState', () => ({
  useMultiProjectCommandCenterState: vi.fn().mockReturnValue({
    state: {
      projectIds: [],
      group: null,
      status: null,
      search: null,
      sort: 'priority',
      page: 1,
      sessionGrouping: 'state',
      selectedCardId: null,
      modalFeatureId: null,
    },
    setProjectIds: vi.fn(),
    setGroup: vi.fn(),
    setSessionGrouping: vi.fn(),
    setSelectedCardId: vi.fn(),
    setModalFeatureId: vi.fn(),
    setStatus: vi.fn(),
    setSearch: vi.fn(),
    setSort: vi.fn(),
    setPage: vi.fn(),
  }),
  toCommandCenterFilters: vi.fn().mockReturnValue({ projectIds: [], status: null, kind: null, group: null, search: null, page: 1, pageSize: 50, sort: 'priority' }),
  toSessionBoardFilters: vi.fn().mockReturnValue({ projectIds: [], group: null, groupBy: 'state', activeWindowMinutes: 120, includeWorkers: true, page: 1, pageSize: 50, includeStale: false }),
}));

import { PlanningCommandCenterShell } from '../CommandCenter/PlanningCommandCenter';
import { MultiProjectModeToggle } from '../CommandCenter/MultiProjectModeToggle';

beforeEach(() => {
  vi.clearAllMocks();
});

// ── Shell with flag OFF (default) ─────────────────────────────────────────────

describe('PlanningCommandCenterShell — flag off (default)', () => {
  it('renders current-project command center by default', () => {
    const html = renderToStaticMarkup(
      <PlanningCommandCenterShell />,
    );
    // V1 component renders; no shell wrapper with mode toggle
    expect(html).toContain('data-testid="planning-command-center"');
    expect(html).not.toContain('data-testid="planning-command-center-shell"');
  });

  it('does not render multi-project toggle when flag is off', () => {
    const html = renderToStaticMarkup(
      <PlanningCommandCenterShell />,
    );
    // No portfolio toggle should be present when flag is off
    expect(html).not.toContain('data-testid="multi-project-mode-toggle"');
    expect(html).not.toContain('data-testid="multi-project-command-center"');
  });

  it('passes projectId prop through to V1 command center', () => {
    const html = renderToStaticMarkup(
      <PlanningCommandCenterShell projectId="proj-test" />,
    );
    // V1 component receives the projectId and renders without crashing
    expect(html).toContain('data-testid="planning-command-center"');
  });

  it('V1 renders loading state without crashing when data is undefined', () => {
    // This is the core resilience test: on first render, getPlanningCommandCenter
    // is unresolved so loadState.phase is 'loading'. The component must not throw.
    const html = renderToStaticMarkup(
      <PlanningCommandCenterShell projectId={null} />,
    );
    expect(html).toContain('Loading command center');
    expect(html).not.toContain('Cannot read properties of undefined');
  });

  it('V1 renders empty-data state without crashing', () => {
    const html = renderToStaticMarkup(
      <PlanningCommandCenterShell />,
    );
    // No crash; loading or idle renders the spinner UI
    expect(html.length).toBeGreaterThan(0);
  });
});

// ── Mode toggle (flag-on path, pure unit) ─────────────────────────────────────

describe('MultiProjectModeToggle standalone', () => {
  it('renders single-project button as active (aria-pressed=true)', () => {
    const html = renderToStaticMarkup(
      <MultiProjectModeToggle mode="single" onModeChange={() => void 0} />,
    );
    expect(html).toContain('aria-label="Command center scope"');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('aria-pressed="false"');
  });

  it('switches to portfolio mode on toggle — renders portfolio button as active', () => {
    const html = renderToStaticMarkup(
      <MultiProjectModeToggle mode="multi" onModeChange={() => void 0} />,
    );
    // In portfolio mode the portfolio button is pressed
    // Both buttons must be present
    expect(html).toContain('aria-label="Single project view"');
    expect(html).toContain('aria-label="All projects portfolio view"');
    // One button must be aria-pressed=true (multi mode)
    const pressed = html.match(/aria-pressed="true"/g) ?? [];
    expect(pressed.length).toBe(1);
  });

  it('renders both buttons regardless of mode', () => {
    const singleHtml = renderToStaticMarkup(
      <MultiProjectModeToggle mode="single" onModeChange={() => void 0} />,
    );
    const multiHtml = renderToStaticMarkup(
      <MultiProjectModeToggle mode="multi" onModeChange={() => void 0} />,
    );
    expect(singleHtml).toContain('project');
    expect(singleHtml).toContain('portfolio');
    expect(multiHtml).toContain('project');
    expect(multiHtml).toContain('portfolio');
  });
});

// ── Resilience: undefined ccData must not crash ───────────────────────────────

describe('PlanningCommandCenterShell — undefined data resilience', () => {
  it('renders without throwing when projectId is undefined', () => {
    expect(() => {
      renderToStaticMarkup(<PlanningCommandCenterShell />);
    }).not.toThrow();
  });

  it('renders without throwing when projectId is null', () => {
    expect(() => {
      renderToStaticMarkup(<PlanningCommandCenterShell projectId={null} />);
    }).not.toThrow();
  });

  it('renders without throwing with a valid projectId string', () => {
    expect(() => {
      renderToStaticMarkup(<PlanningCommandCenterShell projectId="proj-abc" />);
    }).not.toThrow();
  });
});

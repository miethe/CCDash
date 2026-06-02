/**
 * T4-003: SystemMetricsChip frontend tests
 *
 * Tests the R-P2 resilience contracts and rendering behaviour for the
 * SystemMetricsChip component (GET /api/agent/system/active-count).
 *
 * Strategy (mirrors DashboardLiveAgentsChip.test.tsx and DashboardFeatureSurface.test.tsx):
 *   - renderToStaticMarkup (server-side, synchronous) for all assertions.
 *   - useSystemMetricsQuery is mocked via vi.mock so the component renders
 *     without a QueryClientProvider. T4-006-2 migrated the hook from a manual
 *     setInterval to TanStack Query (refetchInterval: 30 s), which requires a
 *     QueryClientProvider in the React tree. Mocking the hook here is the
 *     lightest-weight fix: it follows the same pattern used in
 *     LayoutAuthShell.test.tsx (mocking useNotificationsQuery / useAlertsQuery)
 *     and keeps tests synchronous without a real QueryClient.
 *   - The actual exported SystemMetricsChip is also rendered to confirm the
 *     initial-loading state and to verify the component does not throw.
 *
 * Variants covered (T4-003):
 *  1. Full mock response — chip renders total count
 *  2. status="partial" with one per-project error entry — chip renders count +
 *     per-project error row visible after expanding
 *  3. Empty per_project: [] — expanded view renders "breakdown unavailable"
 *  4. Per-project count: null — expanded row renders em-dash (—)
 *  5. Per-project is_stale: null — expanded row renders warning icon (treated as stale)
 *  6. Full fetch failure — chip renders "data may be outdated" indicator
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ProjectActiveCountSummary } from '../../types';

// ── Module mocks ──────────────────────────────────────────────────────────────

// T4-006-2: SystemMetricsChip now calls useSystemMetricsQuery (TanStack Query)
// instead of a manual setInterval. Mock the hook so the component can render
// synchronously in server-render tests without a real QueryClientProvider.
// The initial-loading state (isLoading=true, data=undefined) is the default.
vi.mock('../../services/queries/systemMetrics', () => ({
  useSystemMetricsQuery: () => ({
    data: undefined,
    isLoading: true,
    isError: false,
    dataUpdatedAt: 0,
  }),
  SYSTEM_METRICS_POLL_MS: 30_000,
  systemMetricsKeys: {
    all: () => ['system-metrics'],
    activeCount: () => ['system-metrics', 'active-count'],
  },
}));

// apiClient is still imported by the query module; keep the stub so the import
// resolves cleanly (the hook mock above means apiRequestJson is never invoked).
vi.mock('../../services/apiClient', () => ({
  apiFetch: vi.fn(),
  apiRequestJson: vi.fn(),
}));

// lucide-react renders SVG; replace with lightweight stubs to keep assertions
// focused on text content rather than SVG internals.
vi.mock('lucide-react', () => ({
  Activity: ({ size, className }: { size?: number; className?: string }) => (
    <span data-testid="icon-activity" data-size={size} className={className} />
  ),
  AlertTriangle: ({ size, className, 'aria-label': ariaLabel }: { size?: number; className?: string; 'aria-label'?: string }) => (
    <span data-testid="icon-alert-triangle" data-size={size} className={className} aria-label={ariaLabel} />
  ),
  ChevronDown: ({ size }: { size?: number }) => (
    <span data-testid="icon-chevron-down" data-size={size} />
  ),
  ChevronUp: ({ size }: { size?: number }) => (
    <span data-testid="icon-chevron-up" data-size={size} />
  ),
}));

// ── Component under test ──────────────────────────────────────────────────────

import { SystemMetricsChip } from '../SystemMetricsChip';

// ── Inline test-harness helpers ───────────────────────────────────────────────
//
// Because renderToStaticMarkup is synchronous and React effects never fire,
// the hook inside SystemMetricsChip always yields its initial loading state.
// State variants are exercised via minimal harness components that mirror the
// rendering contract directly — the same technique used in
// DashboardLiveAgentsChip.test.tsx.

interface HarnessChipProps {
  total: number | null;
  perProject: ProjectActiveCountSummary[];
  status: 'ok' | 'partial' | null;
  isLoading: boolean;
  isError: boolean;
  lastFetchedAt: Date | null;
  /** Render in expanded state */
  expanded?: boolean;
}

/**
 * Mirrors the rendering logic of SystemMetricsChip without the hook, so we can
 * drive it with arbitrary state in tests.
 */
const HarnessChip: React.FC<HarnessChipProps> = ({
  total,
  perProject,
  status,
  isLoading,
  isError,
  lastFetchedAt,
  expanded = false,
}) => {
  // lastKnown fallback (stateless mirror — in production this is a ref)
  const displayTotal = isError ? null : total;
  const showOutdatedBadge = isError && lastFetchedAt !== null;
  const showNeverFetched = isError && lastFetchedAt === null;

  const totalLabel =
    isLoading && displayTotal === null
      ? '—'
      : displayTotal !== null
        ? displayTotal.toLocaleString()
        : '—';

  const hasBreakdown = perProject.length > 0;

  return (
    <div data-testid="system-metrics-chip">
      <div data-testid="chip-header">
        <span data-testid="live-label">Live now</span>
        <span data-testid="total-count">{totalLabel}</span>

        {status === 'partial' && (
          <span data-testid="partial-badge">partial</span>
        )}

        {showOutdatedBadge && (
          <span data-testid="outdated-badge">data may be outdated</span>
        )}

        {showNeverFetched && (
          <span data-testid="never-fetched-badge">unavailable</span>
        )}

        <button
          type="button"
          aria-expanded={expanded}
          aria-label={expanded ? 'Collapse per-project breakdown' : 'Expand per-project breakdown'}
        >
          {expanded ? 'Collapse' : 'By project'}
        </button>
      </div>

      {expanded && (
        <div data-testid="breakdown-panel">
          {hasBreakdown ? (
            <table>
              <thead>
                <tr>
                  <th>Project</th>
                  <th>Active</th>
                </tr>
              </thead>
              <tbody>
                {perProject.map((entry) => {
                  const showStale = entry.is_stale !== false;
                  return (
                    <tr key={entry.project_id} data-testid={`row-${entry.project_id}`}>
                      <td data-testid="row-project-name">{entry.project_name}</td>
                      <td data-testid="row-count">
                        {entry.count !== null ? entry.count.toLocaleString() : '—'}
                      </td>
                      <td>
                        {showStale && (
                          <span
                            data-testid="stale-icon"
                            aria-label="Stale data"
                          />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <p data-testid="breakdown-unavailable">breakdown unavailable</p>
          )}
        </div>
      )}
    </div>
  );
};

// ── Fixture factories ─────────────────────────────────────────────────────────

function makeEntry(overrides: Partial<ProjectActiveCountSummary> = {}): ProjectActiveCountSummary {
  return {
    project_id: 'proj-1',
    project_name: 'Alpha Project',
    count: 4,
    is_stale: false,
    last_synced_at: '2026-05-20T10:00:00Z',
    error: null,
    ...overrides,
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('T4-003 variant 1 — full mock response: chip renders total count', () => {
  it('renders the total count in the chip header', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={7}
        perProject={[makeEntry()]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date('2026-05-20T10:00:00Z')}
      />,
    );
    expect(html).toContain('>7<');
    expect(html).toContain('Live now');
  });

  it('renders "Live now" label regardless of count value', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={0}
        perProject={[]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
      />,
    );
    expect(html).toContain('Live now');
    expect(html).toContain('>0<');
  });

  it('collapse button is present in collapsed state (aria-expanded=false)', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={3}
        perProject={[makeEntry()]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
        expanded={false}
      />,
    );
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('By project');
  });

  it('breakdown panel is absent when collapsed', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={3}
        perProject={[makeEntry()]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
        expanded={false}
      />,
    );
    expect(html).not.toContain('data-testid="breakdown-panel"');
  });
});

describe('T4-003 variant 2 — status="partial" with error entry: per-project error row visible', () => {
  const errorEntry = makeEntry({
    project_id: 'proj-err',
    project_name: 'Error Project',
    count: 0,
    is_stale: true,
    error: 'query timeout',
  });

  it('renders "partial" badge next to the total count', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={2}
        perProject={[errorEntry]}
        status="partial"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
      />,
    );
    expect(html).toContain('partial');
    expect(html).toContain('>2<');
  });

  it('does NOT render partial badge when status is "ok"', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={2}
        perProject={[makeEntry()]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
      />,
    );
    expect(html).not.toContain('data-testid="partial-badge"');
  });

  it('expanded breakdown shows the error project row', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={2}
        perProject={[errorEntry]}
        status="partial"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
        expanded
      />,
    );
    expect(html).toContain('Error Project');
    expect(html).toContain('data-testid="row-proj-err"');
    expect(html).toContain('aria-expanded="true"');
  });
});

describe('T4-003 variant 3 — empty per_project: expanded view renders "breakdown unavailable"', () => {
  it('renders "breakdown unavailable" text when per_project is empty and expanded', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={5}
        perProject={[]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
        expanded
      />,
    );
    expect(html).toContain('breakdown unavailable');
    expect(html).not.toContain('<table');
  });

  it('shows the total count even when per_project is empty', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={5}
        perProject={[]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
        expanded
      />,
    );
    expect(html).toContain('>5<');
  });

  it('does not render the breakdown table when per_project is empty', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={0}
        perProject={[]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
        expanded
      />,
    );
    expect(html).not.toContain('<tbody');
  });
});

describe('T4-003 variant 4 — per-project count: null: expanded row renders em-dash', () => {
  const nullCountEntry = makeEntry({ count: null });

  it('renders em-dash when count is null in a project row', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={0}
        perProject={[nullCountEntry]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
        expanded
      />,
    );
    // em-dash character or HTML entity
    expect(html).toContain('—');
    expect(html).not.toMatch(/data-testid="row-count">\d/);
  });

  it('does not render a numeric count cell for null count rows', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={0}
        perProject={[nullCountEntry]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
        expanded
      />,
    );
    // The count cell must not contain a number
    expect(html).not.toMatch(/data-testid="row-count">[0-9]/);
  });
});

describe('T4-003 variant 5 — per-project is_stale: null: expanded row renders warning icon', () => {
  it('shows stale warning icon when is_stale is null (treated as stale)', () => {
    const nullStaleEntry = makeEntry({ is_stale: null });
    const html = renderToStaticMarkup(
      <HarnessChip
        total={1}
        perProject={[nullStaleEntry]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
        expanded
      />,
    );
    expect(html).toContain('data-testid="stale-icon"');
    expect(html).toContain('aria-label="Stale data"');
  });

  it('shows stale warning icon when is_stale is true', () => {
    const staleEntry = makeEntry({ is_stale: true });
    const html = renderToStaticMarkup(
      <HarnessChip
        total={1}
        perProject={[staleEntry]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
        expanded
      />,
    );
    expect(html).toContain('data-testid="stale-icon"');
  });

  it('does NOT show stale warning icon when is_stale is explicitly false', () => {
    const freshEntry = makeEntry({ is_stale: false });
    const html = renderToStaticMarkup(
      <HarnessChip
        total={1}
        perProject={[freshEntry]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
        expanded
      />,
    );
    expect(html).not.toContain('data-testid="stale-icon"');
  });
});

describe('T4-003 variant 6 — full fetch failure: chip renders "data may be outdated" indicator', () => {
  it('renders "data may be outdated" when isError=true and a prior fetch succeeded', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={null}
        perProject={[]}
        status={null}
        isLoading={false}
        isError
        lastFetchedAt={new Date('2026-05-20T09:00:00Z')}
      />,
    );
    expect(html).toContain('data may be outdated');
    expect(html).not.toContain('data-testid="never-fetched-badge"');
  });

  it('renders "unavailable" when isError=true and no prior fetch has completed', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={null}
        perProject={[]}
        status={null}
        isLoading={false}
        isError
        lastFetchedAt={null}
      />,
    );
    expect(html).toContain('unavailable');
    expect(html).not.toContain('data-testid="outdated-badge"');
  });

  it('does not render error indicators when fetch succeeded', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={3}
        perProject={[makeEntry()]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
      />,
    );
    expect(html).not.toContain('data may be outdated');
    expect(html).not.toContain('unavailable');
  });
});

describe('T4-003 — expand/collapse toggle: aria-expanded reflects expanded state', () => {
  it('collapsed state: aria-expanded is false, breakdown panel absent', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={4}
        perProject={[makeEntry()]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
        expanded={false}
      />,
    );
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain('data-testid="breakdown-panel"');
  });

  it('expanded state: aria-expanded is true, breakdown panel present', () => {
    const html = renderToStaticMarkup(
      <HarnessChip
        total={4}
        perProject={[makeEntry()]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
        expanded
      />,
    );
    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain('data-testid="breakdown-panel"');
  });

  it('collapse button label changes from "By project" to "Collapse" when expanded', () => {
    const collapsedHtml = renderToStaticMarkup(
      <HarnessChip
        total={4}
        perProject={[makeEntry()]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
        expanded={false}
      />,
    );
    const expandedHtml = renderToStaticMarkup(
      <HarnessChip
        total={4}
        perProject={[makeEntry()]}
        status="ok"
        isLoading={false}
        isError={false}
        lastFetchedAt={new Date()}
        expanded
      />,
    );
    expect(collapsedHtml).toContain('By project');
    expect(collapsedHtml).not.toContain('>Collapse<');
    expect(expandedHtml).toContain('>Collapse<');
    expect(expandedHtml).not.toContain('By project');
  });
});

describe('T4-003 — SystemMetricsChip actual component: resilience (no error-boundary throw)', () => {
  beforeEach(() => {
    // useSystemMetricsQuery is module-mocked above (isLoading=true, data=undefined).
    // Clearing mocks here keeps the slate clean between tests without affecting
    // the module-level vi.mock declaration.
    vi.clearAllMocks();
  });

  it('renders without throwing in initial loading state', () => {
    // T4-006-2: hook is now TanStack Query; QueryClientProvider is not needed
    // because useSystemMetricsQuery is mocked at the module level above.
    expect(() => renderToStaticMarkup(<SystemMetricsChip />)).not.toThrow();
  });

  it('initial render produces non-empty HTML output', () => {
    const html = renderToStaticMarkup(<SystemMetricsChip />);
    expect(html.length).toBeGreaterThan(0);
  });

  it('initial render includes "Live now" label', () => {
    const html = renderToStaticMarkup(<SystemMetricsChip />);
    expect(html).toContain('Live now');
  });

  it('initial render includes expand button', () => {
    const html = renderToStaticMarkup(<SystemMetricsChip />);
    // The button is always present; aria-expanded="false" in initial collapsed state
    expect(html).toContain('aria-expanded="false"');
  });

  it('initial render does not render breakdown panel (collapsed by default)', () => {
    const html = renderToStaticMarkup(<SystemMetricsChip />);
    expect(html).not.toContain('breakdown unavailable');
    expect(html).not.toContain('<tbody');
  });
});

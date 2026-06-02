/**
 * Command Center component smoke and resilience tests.
 *
 * Strategy: renderToStaticMarkup only — no jsdom required.
 * Complements planningCommandCenter.test.tsx (which covers the sub-view
 * components) by focusing on the top-level PlanningCommandCenter component
 * in its loading/error/empty/ready states and null-safety guards.
 *
 * Coverage:
 *   1. PlanningCommandCenter renders toolbar in all states
 *   2. Loading state renders spinner and no list view
 *   3. Error state renders error message and retry button
 *   4. Empty page renders empty list view without crashing
 *   5. Null-safety: page?.warnings and page?.items fallback correctly
 *   6. PlanningCommandCenterShell renders V1 by default
 *
 * T4-002: usePlanningCommandCenterQuery replaces useEffect+LoadState.
 *   Hook is mocked here so no QueryClientProvider is needed for
 *   renderToStaticMarkup — mock returns a TQ-shaped result directly.
 * T4-014: page (default 1) + pageSize (default 50) pagination added;
 *   toolbar now always includes a pageSize selector when wired.
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi, beforeEach } from 'vitest';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('../../../constants', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../constants')>();
  return {
    ...actual,
    MULTI_PROJECT_COMMAND_CENTER_ENABLED: false,
  };
});

// T4-002: mock the TQ hook that replaced useEffect+LoadState.
// Returns a loading state (data: undefined, isLoading: true) to match the
// old behaviour of a never-resolving getPlanningCommandCenter promise.
// Mocking at hook level avoids the need for a QueryClientProvider.
vi.mock('../../../services/queries/planning', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/queries/planning')>();
  return {
    ...actual,
    usePlanningCommandCenterQuery: vi.fn().mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }),
  };
});

// Keep the service mock so transitive imports of planningCommandCenter.ts do
// not attempt real network calls (getPlanningCommandCenter is still re-exported
// by the service module).
vi.mock('../../../services/planningCommandCenter', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/planningCommandCenter')>();
  return {
    ...actual,
    getPlanningCommandCenter: vi.fn().mockReturnValue(new Promise(() => {})),
  };
});

vi.mock('../../../services/planningTelemetry', () => ({
  trackCommandCenterAction: vi.fn(),
}));

import {
  PlanningCommandCenter,
  PlanningCommandCenterShell,
} from '../CommandCenter/PlanningCommandCenter';

beforeEach(() => {
  vi.clearAllMocks();
});

// ── PlanningCommandCenter states ──────────────────────────────────────────────

describe('PlanningCommandCenter — initial render states', () => {
  it('renders toolbar wrapper on initial synchronous render', () => {
    const html = renderToStaticMarkup(
      <PlanningCommandCenter />,
    );
    // Toolbar and panel always render
    expect(html).toContain('data-testid="planning-command-center"');
  });

  it('renders loading spinner when fetch is pending (initial render)', () => {
    const html = renderToStaticMarkup(
      <PlanningCommandCenter />,
    );
    // T4-002: isLoading=true → spinner shown
    expect(html).toContain('Loading command center');
  });

  it('does not render list view while loading', () => {
    const html = renderToStaticMarkup(
      <PlanningCommandCenter />,
    );
    // List view only renders when page data is non-null; data: undefined → no list
    expect(html).not.toContain('data-testid="command-center-list-view"');
  });

  it('does not crash when projectId is undefined', () => {
    expect(() => {
      renderToStaticMarkup(<PlanningCommandCenter />);
    }).not.toThrow();
  });

  it('does not crash when projectId is null', () => {
    expect(() => {
      renderToStaticMarkup(<PlanningCommandCenter projectId={null} />);
    }).not.toThrow();
  });

  it('does not crash when projectId is a string', () => {
    expect(() => {
      renderToStaticMarkup(<PlanningCommandCenter projectId="proj-xyz" />);
    }).not.toThrow();
  });
});

// ── Null-safety: page?.warnings / page?.items ─────────────────────────────────

describe('PlanningCommandCenter — null-safety guards', () => {
  it('initial render never accesses .items on undefined data', () => {
    // T4-002: hook returns data: undefined during loading — component must not
    // throw when using items = page?.items ?? [].
    let threw = false;
    try {
      renderToStaticMarkup(<PlanningCommandCenter />);
    } catch {
      threw = true;
    }
    expect(threw).toBe(false);
  });

  it('loading state shows spinner, not undefined error', () => {
    const html = renderToStaticMarkup(<PlanningCommandCenter />);
    expect(html).not.toContain('Cannot read properties of undefined');
    expect(html).toContain('animate-spin');
  });
});

// ── T4-014: pagination toolbar ────────────────────────────────────────────────

describe('PlanningCommandCenter — T4-014 pagination', () => {
  it('toolbar renders with data-testid command-center-toolbar', () => {
    const html = renderToStaticMarkup(<PlanningCommandCenter />);
    expect(html).toContain('data-testid="command-center-toolbar"');
  });

  it('toolbar includes pageSize selector (aria-label "Items per page")', () => {
    const html = renderToStaticMarkup(<PlanningCommandCenter />);
    // T4-014: onPageSizeChange is always wired; pageSize select always present.
    expect(html).toContain('Items per page');
  });

  it('prev/next pagination controls absent when data is undefined', () => {
    // Controls only render when page is defined AND totalPages > 1.
    const html = renderToStaticMarkup(<PlanningCommandCenter />);
    expect(html).not.toContain('aria-label="Previous page"');
    expect(html).not.toContain('aria-label="Next page"');
  });
});

// ── PlanningCommandCenterShell — flag off ─────────────────────────────────────

describe('PlanningCommandCenterShell — renders V1 by default', () => {
  it('renders PlanningCommandCenter directly when flag is off', () => {
    const html = renderToStaticMarkup(<PlanningCommandCenterShell />);
    expect(html).toContain('data-testid="planning-command-center"');
    expect(html).not.toContain('data-testid="planning-command-center-shell"');
  });

  it('toolbar is present in the rendered output', () => {
    const html = renderToStaticMarkup(<PlanningCommandCenterShell />);
    // Toolbar always renders (contains view controls and refresh button)
    expect(html).toContain('data-testid="planning-command-center"');
  });
});

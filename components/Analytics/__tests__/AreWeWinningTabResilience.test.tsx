/**
 * are-we-winning-dashboard-v1 (M3): resilience tests for AreWeWinningTab.
 *
 * Follows the AnalyticsDashboardResearchResilience.test.tsx precedent —
 * renderToStaticMarkup (no jsdom / @testing-library/react needed, matching
 * this repo's vitest config: no jsdom environment is configured), the
 * `useAreWeWinningSummaryQuery` hook mocked per-test via `vi.spyOn`.
 *
 * Coverage:
 *  - A null summary (disabled flag or any other fetch failure) renders the
 *    explicit "not available" panel, never a crash or a broken chart.
 *  - `reopened: null` renders "Not captured yet", never an empty/zero chart.
 *  - `selfCaughtRatio: null` renders "Not captured yet", never a fabricated
 *    ratio.
 *  - `selfCaughtRatio` with `unknown` at 100% of the population renders the
 *    `unknown` bucket as a visible, first-class legend row with its real
 *    count and percentage — never hidden, muted away, or silently folded.
 *  - A populated `reopened` trendline renders its real point count, not the
 *    "not captured" fallback.
 */

import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, afterEach } from 'vitest';
import type { AreWeWinningSummary } from '../../../types';

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('../../../services/queries/areWeWinning', () => ({
  useAreWeWinningSummaryQuery: vi.fn(() => ({ data: null, isLoading: false })),
  useAreWeWinningDrillThroughQuery: vi.fn(() => ({ data: null, isLoading: false })),
}));

import { AreWeWinningTab } from '../AreWeWinningTab';
import * as AreWeWinningQueries from '../../../services/queries/areWeWinning';

// ── Fixtures ──────────────────────────────────────────────────────────────────

function summaryWith(overrides: Partial<AreWeWinningSummary> = {}): AreWeWinningSummary {
  return {
    created: { eventType: 'node.created', points: [{ isoYear: 2026, isoWeek: 33, weekStartDate: '2026-08-10', count: 12 }] },
    completed: { eventType: 'node.completed', points: [{ isoYear: 2026, isoWeek: 33, weekStartDate: '2026-08-10', count: 4 }] },
    reopened: null,
    selfCaughtRatio: null,
    generatedAt: '2026-08-14T00:00:00Z',
    ...overrides,
  };
}

function mockSummary(data: AreWeWinningSummary | null, isLoading = false) {
  vi.spyOn(AreWeWinningQueries, 'useAreWeWinningSummaryQuery').mockImplementation(
    () => ({ data, isLoading } as any),
  );
}

function renderTab(): string {
  // AreWeWinningTab renders InteractiveChartCard (via SelfCaughtRatioWidget)
  // when selfCaughtRatio is populated, and InteractiveChartCard calls
  // useSearchParams() unconditionally — a Router context is required even
  // though this tab never itself reads/writes search params.
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={['/analytics?tab=are_we_winning']}>
      <AreWeWinningTab />
    </MemoryRouter>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('AreWeWinningTab — surface-absent resilience', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the "not available" panel (never crashes) when summary is null', () => {
    mockSummary(null);
    const html = renderTab();
    expect(html).toContain('not available');
    expect(html).not.toContain('Nodes Created');
  });

  it('renders a loading state distinct from the absent-data state', () => {
    mockSummary(null, true);
    const html = renderTab();
    expect(html).toContain('Loading are-we-winning dashboard');
    expect(html).not.toContain('not available');
  });
});

describe('AreWeWinningTab — reopened resilience (M2 part-B not yet implemented)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders "Not captured yet" for reopened=null, never an empty/zero chart', () => {
    mockSummary(summaryWith({ reopened: null }));
    const html = renderTab();
    expect(html).toContain('Nodes Reopened');
    expect(html).toContain('Not captured yet');
    expect(html).toContain('reopened-not-captured');
  });

  it('renders the real reopened trendline (not the fallback) when populated', () => {
    mockSummary(
      summaryWith({
        reopened: {
          eventType: 'node.reopened',
          points: [{ isoYear: 2026, isoWeek: 20, weekStartDate: '2026-05-11', count: 2 }],
        },
      }),
    );
    const html = renderTab();
    expect(html).not.toContain('reopened-not-captured');
  });
});

describe('AreWeWinningTab — self-caught ratio resilience', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders "Not captured yet" for selfCaughtRatio=null, never a fabricated ratio', () => {
    mockSummary(summaryWith({ selfCaughtRatio: null }));
    const html = renderTab();
    expect(html).toContain('Self-Caught Ratio');
    expect(html).toContain('Not captured yet');
    expect(html).toContain('self-caught-ratio-not-captured');
  });

  it('renders the unknown bucket as a visible first-class legend row when it is 100% of the population', () => {
    mockSummary(
      summaryWith({
        selfCaughtRatio: {
          buckets: [
            { bucket: 'self_caught', count: 0 },
            { bucket: 'other_caught', count: 0 },
            { bucket: 'unknown', count: 200 },
          ],
          total: 200,
        },
      }),
    );
    const html = renderTab();

    expect(html).toContain('self-caught-ratio-bucket-unknown');
    expect(html).toContain('Unknown');
    expect(html).toContain('200');
    expect(html).toContain('100.0%');
    // The dominant-unknown legend row must render, not be omitted or zeroed.
    expect(html).not.toContain('self-caught-ratio-not-captured');
  });

  it('renders real per-bucket counts for a mixed ratio, including self_caught/other_caught rows', () => {
    mockSummary(
      summaryWith({
        selfCaughtRatio: {
          buckets: [
            { bucket: 'self_caught', count: 5 },
            { bucket: 'other_caught', count: 2 },
            { bucket: 'unknown', count: 193 },
          ],
          total: 200,
        },
      }),
    );
    const html = renderTab();

    expect(html).toContain('self-caught-ratio-bucket-self_caught');
    expect(html).toContain('self-caught-ratio-bucket-other_caught');
    expect(html).toContain('self-caught-ratio-bucket-unknown');
  });
});

describe('AreWeWinningTab — trendline empty-state resilience', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders explicit empty-state copy (not a blank chart) when created/completed have zero points', () => {
    mockSummary(
      summaryWith({
        created: { eventType: 'node.created', points: [] },
        completed: { eventType: 'node.completed', points: [] },
      }),
    );
    const html = renderTab();
    expect(html).toContain('No created-node events captured yet.');
    expect(html).toContain('No completed-node events captured yet.');
  });
});

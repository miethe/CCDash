/**
 * T3-005 (research-foundry-run-telemetry-v1, Phase 3): Resilience fallbacks
 * for optional/absent fields on the "Research" (Provider Economics) analytics
 * tab.
 *
 * Verifies AC-4 / AC-4-Fields:
 *  - Zero research_runs renders the explicit "No research runs recorded yet"
 *    empty state (never a broken/empty-looking panel set).
 *  - Every optional field enumerated in AC-4-Fields (`estimated_cost_usd`,
 *    `citation_coverage`, `latency_ms`, `mode`, `selected_providers`,
 *    `linked_session_id`, `rf_run_id`, `intent_id`, `task_node_id`) renders an
 *    explicit "—" per-cell when null — never `$0.00`/`NaN`/`0%`.
 *  - `linked_session_id` absence renders "no linked session" text (not a
 *    broken EntityLinkButton); `intent_id`/`task_node_id` render as opaque
 *    text only, never as clickable links (DF-007).
 *
 * Uses renderToStaticMarkup (no jsdom / @testing-library/react needed) — same
 * pattern as components/__tests__/ProjectBoardCardMetrics.test.tsx. Confirmed
 * via spike that recharts' ResponsiveContainer renders (as an empty
 * zero-dimension container, no throw) under vitest's default node
 * environment, so the two chart panels in this tab are safe to leave
 * unmocked.
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ResearchRun } from '../../../types';

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('../../../contexts/DataContext', () => ({
  useData: () => ({
    activeProject: { id: 'proj-1', name: 'Test Project' },
  }),
}));

vi.mock('../../../contexts/ModelColorsContext', () => ({
  useModelColors: () => ({
    getColorForModel: vi.fn(() => '#000000'),
    getBadgeStyleForModel: vi.fn(() => ({})),
  }),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useSearchParams: () => [new URLSearchParams('tab=research'), vi.fn()] as const,
  };
});

// Every other analytics tab's hooks — stubbed so the component mounts without
// hitting the network; the "research" tab (this file's focus) never reads
// these, but they are unconditionally called at the top of the component.
vi.mock('../../../services/queries/analytics', () => ({
  useAnalyticsFullOverviewQuery: () => ({ data: null, isLoading: false }),
  useAnalyticsNotificationsQuery: () => ({ data: [] }),
  useAnalyticsArtifactsQuery: () => ({ data: null, isLoading: false }),
  useAnalyticsCorrelationQuery: () => ({ data: [], isLoading: false }),
  useAnalyticsCostCalibrationQuery: () => ({ data: null }),
  useAnalyticsUsageAttributionQuery: () => ({ data: null }),
  useAnalyticsUsageCalibrationQuery: () => ({ data: null }),
  useAnalyticsUsageDrilldownQuery: () => ({ data: null }),
}));

// useResearchRuns is overridden per-test via vi.spyOn (same pattern as
// useFeatureSurface in ProjectBoardCardMetrics.test.tsx).
vi.mock('../../../services/queries/researchRuns', () => ({
  useResearchRuns: vi.fn(() => ({ data: undefined, isLoading: false })),
}));

// ── Component under test ──────────────────────────────────────────────────────

import { AnalyticsDashboard } from '../AnalyticsDashboard';
import * as ResearchRunsModule from '../../../services/queries/researchRuns';

// ── Fixtures ──────────────────────────────────────────────────────────────────

/** Every AC-4-Fields optional field populated, plus every other optional field. */
const POPULATED_RUN: ResearchRun = {
  runId: 'run-full-1',
  rfRunId: 'rf-run-full-1',
  projectId: 'proj-1',
  workspaceId: 'default-local',
  intentId: 'intent-42',
  taskNodeId: 'task-node-7',
  rfProject: 'rf-project-alpha',
  eventCount: 12,
  firstEventAt: '2026-07-01T00:00:00Z',
  lastEventAt: '2026-07-02T00:00:00Z',
  queriesExecuted: 5,
  urlsExtracted: 20,
  usefulSourceCount: 8,
  tokensEstimated: 15000,
  claimsTotal: 10,
  claimsSupported: 7,
  claimsMixed: 2,
  claimsContradicted: 1,
  unsupportedClaims: 0,
  estimatedCostUsd: 1.2345,
  latencyMs: 4500,
  citationCoverage: 0.82,
  duplicateRate: 0.05,
  extractionFailureRate: 0.01,
  qualityScore: 'high',
  driftScore: 0.1,
  mode: 'deep',
  selectedProviders: ['tavily', 'brave'],
  governanceSensitivity: 'internal',
  governancePolicyPassed: true,
  humanReviewRequired: false,
  humanReviewStatus: null,
  humanReviewReviewer: null,
  reuseMeatywikiWritebackCandidate: true,
  reuseSkillbomCandidate: false,
  reuseReusableSourcePackCandidate: false,
  linkedSessionId: 'sess-abc123',
  linkedSessionIds: ['sess-abc123'],
  createdAt: '2026-07-01T00:00:00Z',
  updatedAt: '2026-07-02T00:00:00Z',
};

/** Every AC-4-Fields optional field (and every other optional field) absent. */
const NULL_RUN: ResearchRun = {
  runId: 'run-null-1',
  rfRunId: null,
  projectId: 'proj-1',
  workspaceId: 'default-local',
  intentId: null,
  taskNodeId: null,
  rfProject: null,
  eventCount: 0,
  firstEventAt: null,
  lastEventAt: null,
  queriesExecuted: null,
  urlsExtracted: null,
  usefulSourceCount: null,
  tokensEstimated: null,
  claimsTotal: null,
  claimsSupported: null,
  claimsMixed: null,
  claimsContradicted: null,
  unsupportedClaims: null,
  estimatedCostUsd: null,
  latencyMs: null,
  citationCoverage: null,
  duplicateRate: null,
  extractionFailureRate: null,
  qualityScore: null,
  driftScore: null,
  mode: null,
  selectedProviders: null,
  governanceSensitivity: null,
  governancePolicyPassed: null,
  humanReviewRequired: null,
  humanReviewStatus: null,
  humanReviewReviewer: null,
  reuseMeatywikiWritebackCandidate: null,
  reuseSkillbomCandidate: null,
  reuseReusableSourcePackCandidate: null,
  linkedSessionId: null,
  linkedSessionIds: [],
  createdAt: null,
  updatedAt: null,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function mockResearchRuns(items: ResearchRun[], isLoading = false) {
  vi.spyOn(ResearchRunsModule, 'useResearchRuns').mockImplementation(() => ({
    data: {
      status: 'ok',
      dataFreshness: '2026-07-21T00:00:00Z',
      generatedAt: '2026-07-21T00:00:00Z',
      sourceRefs: [],
      projectId: 'proj-1',
      items,
      cursor: '',
      limit: 50,
      nextCursor: null,
    },
    isLoading,
  }) as any);
}

function renderResearchTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderToStaticMarkup(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/analytics?tab=research']}>
        <AnalyticsDashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Slices the row containing the given runId's "Run" cell (which carries
 * `title={runId}`) through to the row's closing tag, so per-row assertions
 * don't accidentally match the other fixture row. */
function rowSlice(html: string, runId: string): string {
  const marker = `title="${runId}"`;
  const start = html.indexOf(marker);
  expect(start).toBeGreaterThan(-1);
  const end = html.indexOf('</tr>', start);
  expect(end).toBeGreaterThan(start);
  return html.slice(start, end);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('T3-005 — Research tab: zero-events empty state', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders "No research runs recorded yet" when research_runs is empty', () => {
    mockResearchRuns([]);
    const html = renderResearchTab();
    expect(html).toContain('No research runs recorded yet');
  });

  it('does not render any of the 4 panel headings when empty', () => {
    mockResearchRuns([]);
    const html = renderResearchTab();
    expect(html).not.toContain('Cost &amp; Quality by Mode');
    expect(html).not.toContain('Daily Research Spend');
    expect(html).not.toContain('Daily Research Volume');
    expect(html).not.toContain('<table');
  });
});

describe('T3-005 — Research tab: per-run field resilience (AC-4-Fields)', () => {
  let html: string;

  beforeEach(() => {
    mockResearchRuns([POPULATED_RUN, NULL_RUN]);
    html = renderResearchTab();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders every populated optional field with its real value in the drill table', () => {
    const row = rowSlice(html, POPULATED_RUN.runId);
    expect(row).toContain('rf-run-full-1'); // rf_run_id
    expect(row).toContain('deep'); // mode
    expect(row).toContain('tavily, brave'); // selected_providers
    expect(row).toContain('$1.2345'); // estimated_cost_usd
    expect(row).toContain('82.0%'); // citation_coverage
    expect(row).toContain('sess-abc123'); // linked_session_id (as EntityLinkButton label)
    expect(row).toContain('intent-42'); // intent_id
    expect(row).toContain('task-node-7'); // task_node_id
  });

  it('renders an explicit em-dash for every absent AC-4-Fields optional field, never a fallback substitute', () => {
    const row = rowSlice(html, NULL_RUN.runId);
    // rf_run_id must NOT fall back to the internal runId when absent.
    expect(row).not.toContain(NULL_RUN.runId + '</td>');
    // Count of "—" occurrences in this row should cover: rf_run_id, mode,
    // selected_providers, estimated_cost_usd, citation_coverage, latency_ms,
    // intent_id, task_node_id (8 fields) — "no linked session" text covers
    // linked_session_id separately (see next test).
    const dashCount = (row.match(/—/g) || []).length;
    expect(dashCount).toBeGreaterThanOrEqual(8);
  });

  it('never renders $0.00, 0%, or NaN for an absent numeric/percent field', () => {
    const row = rowSlice(html, NULL_RUN.runId);
    expect(row).not.toContain('$0.00');
    expect(row).not.toContain('0%');
    expect(row).not.toContain('NaN');
  });

  it('renders "no linked session" text (not a broken EntityLinkButton) when linked_session_id is absent', () => {
    const row = rowSlice(html, NULL_RUN.runId);
    expect(row).toContain('no linked session');
    expect(row).not.toContain('<button');
  });

  it('renders intent_id and task_node_id as opaque text, never as clickable links (DF-007)', () => {
    const populatedRow = rowSlice(html, POPULATED_RUN.runId);
    // Neither field is wrapped in an <a> or <button> anywhere in the row.
    const intentIdx = populatedRow.indexOf('intent-42');
    const taskNodeIdx = populatedRow.indexOf('task-node-7');
    expect(intentIdx).toBeGreaterThan(-1);
    expect(taskNodeIdx).toBeGreaterThan(-1);
    expect(populatedRow.slice(Math.max(0, intentIdx - 60), intentIdx)).not.toContain('<a ');
    expect(populatedRow.slice(Math.max(0, intentIdx - 60), intentIdx)).not.toContain('<button');
    expect(populatedRow.slice(Math.max(0, taskNodeIdx - 60), taskNodeIdx)).not.toContain('<a ');
    expect(populatedRow.slice(Math.max(0, taskNodeIdx - 60), taskNodeIdx)).not.toContain('<button');
  });
});

describe('T3-005 — Research tab: KPI-strip resilience when no run has a given metric', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders "—" (never $0.00/NaN/0%) for Estimated Spend, Citation Coverage, and Avg Latency when every run lacks that metric', () => {
    mockResearchRuns([NULL_RUN]);
    const html = renderResearchTab();

    expect(html).toContain('Estimated Spend');
    expect(html).toContain('no cost data yet');
    expect(html).toContain('Citation Coverage');
    expect(html).toContain('no coverage data yet');
    expect(html).toContain('Avg Latency');
    expect(html).toContain('no latency data yet');

    expect(html).not.toContain('$0.00');
    expect(html).not.toContain('NaN');
    // A fabricated "0.0%"/"0%" cell (as opposed to unrelated CSS like
    // ResponsiveContainer's "width:100%") would only ever appear here as a
    // coerced-to-zero citation-coverage value; must not appear as rendered
    // cell/badge content anywhere in the KPI strip.
    expect(html).not.toMatch(/>0(\.0)?%</);
  });

  it('renders real KPI values when the run has all metrics populated', () => {
    mockResearchRuns([POPULATED_RUN]);
    const html = renderResearchTab();

    expect(html).toContain('$1.2345'); // Estimated Spend (single run, avg == its own cost)
    expect(html).toContain('82.0%'); // Citation Coverage
    expect(html).toContain('1 linked to sessions'); // sanity: linked count present
  });
});

describe('T3-005 — Research tab: mode-quality table resilience', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('buckets a null mode as "Unspecified" and renders "—" for its avg cost/coverage when unmeasured', () => {
    mockResearchRuns([NULL_RUN]);
    const html = renderResearchTab();
    expect(html).toContain('Unspecified');
    expect(html).not.toContain('$0.00');
    expect(html).not.toMatch(/>0(\.0)?%</);
  });
});

/**
 * PCP-708: PlanningSummaryPanel interactive-behaviour tests.
 *
 * Strategy: renderToStaticMarkup (no jsdom) consistent with the rest of the
 * Planning test suite. Interaction assertions are structural: we assert on
 * rendered HTML to verify that chips with count > 0 are <button> elements
 * with the correct aria-label, and chips with count === 0 or Trackers are
 * rendered as <span> (not clickable).
 *
 * Coverage:
 *   1. ArtifactChip count > 0 — rendered as <button> with aria-label
 *   2. ArtifactChip count === 0 — rendered as <span>, no button
 *   3. Clicking a button chip calls onDrillDown (verified structurally: button present)
 *   4. Each drillDown-capable chip has the correct aria-label
 *   5. Trackers chip — rendered as <span> regardless of count (documented deviation)
 *   6. onSelectFeature rows are buttons
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import type { FeatureSummaryItem, ProjectPlanningSummary } from '../../../types';
import { PlanningSummaryPanel } from '../PlanningSummaryPanel';

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeFeatureSummary(overrides: Partial<FeatureSummaryItem> = {}): FeatureSummaryItem {
  return {
    featureId: 'feat-1',
    featureName: 'Auth Revamp',
    rawStatus: 'in-progress',
    effectiveStatus: 'in_progress',
    isMismatch: false,
    mismatchState: 'aligned',
    hasBlockedPhases: false,
    phaseCount: 2,
    blockedPhaseCount: 0,
    nodeCount: 3,
    ...overrides,
  };
}

function makeSummary(overrides: Partial<ProjectPlanningSummary> = {}): ProjectPlanningSummary {
  return {
    status: 'ok',
    dataFreshness: '2026-04-17T00:00:00Z',
    generatedAt: '2026-04-17T00:00:00Z',
    sourceRefs: [],
    projectId: 'proj-1',
    projectName: 'My Project',
    totalFeatureCount: 1,
    activeFeatureCount: 1,
    staleFeatureCount: 0,
    blockedFeatureCount: 0,
    mismatchCount: 0,
    reversalCount: 0,
    staleFeatureIds: [],
    reversalFeatureIds: [],
    blockedFeatureIds: [],
    nodeCountsByType: {
      prd: 2,
      designSpec: 1,
      implementationPlan: 3,
      progress: 2,
      context: 0,
      tracker: 1,
      report: 0,
    },
    featureSummaries: [makeFeatureSummary()],
    ...overrides,
  };
}

function wrap(node: React.ReactElement): string {
  return renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ── Chip clickability (structural) ────────────────────────────────────────────

describe('PlanningSummaryPanel — ArtifactChip as button when count > 0', () => {
  it('renders PRDs chip as a button with correct aria-label when count > 0', () => {
    const html = wrap(
      <PlanningSummaryPanel
        summary={makeSummary({ nodeCountsByType: { prd: 3, designSpec: 0, implementationPlan: 0, progress: 0, context: 0, tracker: 0, report: 0 } })}
        onDrillDown={vi.fn()}
      />,
    );
    expect(html).toContain('aria-label="View 3 PRDs"');
    expect(html).toContain('<button');
  });

  it('renders Design Specs chip as a button when count > 0', () => {
    const html = wrap(
      <PlanningSummaryPanel
        summary={makeSummary({ nodeCountsByType: { prd: 0, designSpec: 2, implementationPlan: 0, progress: 0, context: 0, tracker: 0, report: 0 } })}
        onDrillDown={vi.fn()}
      />,
    );
    expect(html).toContain('aria-label="View 2 Design Specs"');
  });

  it('renders Implementation Plans chip as a button when count > 0', () => {
    const html = wrap(
      <PlanningSummaryPanel
        summary={makeSummary({ nodeCountsByType: { prd: 0, designSpec: 0, implementationPlan: 4, progress: 0, context: 0, tracker: 0, report: 0 } })}
        onDrillDown={vi.fn()}
      />,
    );
    expect(html).toContain('aria-label="View 4 Implementation Plans"');
  });

  it('does NOT render a Progress chip regardless of count (evidence-only artifact)', () => {
    const html = wrap(
      <PlanningSummaryPanel
        summary={makeSummary({ nodeCountsByType: { prd: 0, designSpec: 0, implementationPlan: 0, progress: 5, context: 0, tracker: 0, report: 0 } })}
        onDrillDown={vi.fn()}
      />,
    );
    expect(html).not.toContain('Progress');
    expect(html).not.toContain('aria-label="View 5 Progress"');
  });

  it('renders Context chip as a button when count > 0', () => {
    const html = wrap(
      <PlanningSummaryPanel
        summary={makeSummary({ nodeCountsByType: { prd: 0, designSpec: 0, implementationPlan: 0, progress: 0, context: 5, tracker: 0, report: 0 } })}
        onDrillDown={vi.fn()}
      />,
    );
    expect(html).toContain('aria-label="View 5 Context"');
  });

  it('renders Reports chip as a button when count > 0', () => {
    const html = wrap(
      <PlanningSummaryPanel
        summary={makeSummary({ nodeCountsByType: { prd: 0, designSpec: 0, implementationPlan: 0, progress: 0, context: 0, tracker: 0, report: 7 } })}
        onDrillDown={vi.fn()}
      />,
    );
    expect(html).toContain('aria-label="View 7 Reports"');
  });
});

describe('PlanningSummaryPanel — ArtifactChip as span when count === 0', () => {
  it('does not render PRDs as a button when count is 0', () => {
    const html = wrap(
      <PlanningSummaryPanel
        summary={makeSummary({ nodeCountsByType: { prd: 0, designSpec: 0, implementationPlan: 0, progress: 0, context: 0, tracker: 0, report: 0 } })}
        onDrillDown={vi.fn()}
      />,
    );
    // No "View 0 PRDs" button
    expect(html).not.toContain('aria-label="View 0 PRDs"');
    // PRDs label still present
    expect(html).toContain('PRDs');
  });
});

describe('PlanningSummaryPanel — Trackers chip deviation', () => {
  it('Trackers is never a button even when count > 0', () => {
    const html = wrap(
      <PlanningSummaryPanel
        summary={makeSummary({ nodeCountsByType: { prd: 0, designSpec: 0, implementationPlan: 0, progress: 0, context: 0, tracker: 5, report: 0 } })}
        onDrillDown={vi.fn()}
      />,
    );
    // No "View N Trackers" aria-label — Trackers has no drillDownType
    expect(html).not.toContain('aria-label="View 5 Trackers"');
    // The text is present
    expect(html).toContain('Trackers');
  });
});

describe('PlanningSummaryPanel — onSelectFeature rows are buttons', () => {
  it('feature rows are rendered as buttons', () => {
    const summary = makeSummary({
      staleFeatureIds: ['feat-1'],
      staleFeatureCount: 1,
    });
    const html = wrap(
      <PlanningSummaryPanel
        summary={summary}
        onSelectFeature={vi.fn()}
        onDrillDown={vi.fn()}
      />,
    );
    // FeatureRow renders as a button element
    expect(html).toContain('aria-label="View planning context for Auth Revamp"');
  });
});

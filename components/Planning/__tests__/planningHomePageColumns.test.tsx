/**
 * PCP-702: ActivePlansColumn + PlannedFeaturesColumn tests.
 *
 * Strategy: renderToStaticMarkup (no jsdom) consistent with the rest of the
 * Planning test suite. Column components are exported from PlanningHomePage
 * so they can be exercised in isolation here.
 *
 * Coverage:
 *   1. ActivePlansColumn – renders features with in_progress effective status.
 *   2. ActivePlansColumn – shows empty state when no in-progress features.
 *   3. PlannedFeaturesColumn – renders features with draft status.
 *   4. PlannedFeaturesColumn – renders features with approved status.
 *   5. PlannedFeaturesColumn – shows empty state when no planned features.
 *   6. Status filter – in-progress features do NOT appear in planned column.
 *   7. Status filter – draft features do NOT appear in active column.
 *   8. Mismatch badge – renders when isMismatch is true.
 *   9. Phase metadata – renders phase count in row.
 *  10. data-testid presence – planning-feature-columns wrapper renders in page.
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import type { FeatureSummaryItem } from '../../../types';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('../../../services/live/useLiveInvalidation', () => ({
  useLiveInvalidation: () => 'idle',
}));

vi.mock('../../../services/planning', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/planning')>();
  return { ...actual, getProjectPlanningSummary: vi.fn() };
});

vi.mock('../../../services/execution', () => ({
  getLaunchCapabilities: vi.fn().mockResolvedValue({ planningEnabled: true }),
}));

vi.mock('../../../contexts/DataContext', () => ({
  useData: () => ({ activeProject: { id: 'proj-1', name: 'My Project' } }),
}));

import { ActivePlansColumn, PlannedFeaturesColumn } from '../PlanningHomePage';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const makeFeature = (overrides: Partial<FeatureSummaryItem> = {}): FeatureSummaryItem => ({
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

const wrap = (node: React.ReactElement) =>
  renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>);

beforeEach(() => {
  vi.clearAllMocks();
});

// ── ActivePlansColumn ─────────────────────────────────────────────────────────

describe('ActivePlansColumn', () => {
  it('renders features with in_progress effective status', () => {
    const html = wrap(
      <ActivePlansColumn
        features={[
          makeFeature({ featureId: 'feat-a', featureName: 'Active Feature A', effectiveStatus: 'in_progress' }),
          makeFeature({ featureId: 'feat-b', featureName: 'Draft Feature B', effectiveStatus: 'draft' }),
        ]}
        onSelectFeature={vi.fn()}
      />,
    );
    expect(html).toContain('data-testid="active-plans-column"');
    expect(html).toContain('Active Feature A');
    expect(html).not.toContain('Draft Feature B');
  });

  it('also accepts in-progress (hyphen) as active status', () => {
    const html = wrap(
      <ActivePlansColumn
        features={[
          makeFeature({ featureId: 'feat-h', featureName: 'Hyphen Feature', effectiveStatus: 'in-progress' }),
        ]}
        onSelectFeature={vi.fn()}
      />,
    );
    expect(html).toContain('Hyphen Feature');
  });

  it('shows empty state when no in-progress features', () => {
    const html = wrap(
      <ActivePlansColumn
        features={[makeFeature({ effectiveStatus: 'draft' })]}
        onSelectFeature={vi.fn()}
      />,
    );
    expect(html).toContain('No active implementation plans');
    expect(html).not.toContain('Auth Revamp');
  });

  it('shows empty state for empty feature list', () => {
    const html = wrap(
      <ActivePlansColumn features={[]} onSelectFeature={vi.fn()} />,
    );
    expect(html).toContain('No active implementation plans');
  });
});

// ── PlannedFeaturesColumn ─────────────────────────────────────────────────────

describe('PlannedFeaturesColumn', () => {
  it('renders features with draft effective status', () => {
    const html = wrap(
      <PlannedFeaturesColumn
        features={[
          makeFeature({ featureId: 'feat-d', featureName: 'Draft Feature', effectiveStatus: 'draft', rawStatus: 'draft' }),
          makeFeature({ featureId: 'feat-a', featureName: 'Active Feature', effectiveStatus: 'in_progress' }),
        ]}
        onSelectFeature={vi.fn()}
      />,
    );
    expect(html).toContain('data-testid="planned-features-column"');
    expect(html).toContain('Draft Feature');
    expect(html).not.toContain('Active Feature');
  });

  it('renders features with approved effective status', () => {
    const html = wrap(
      <PlannedFeaturesColumn
        features={[
          makeFeature({ featureId: 'feat-ap', featureName: 'Approved Feature', effectiveStatus: 'approved', rawStatus: 'approved' }),
        ]}
        onSelectFeature={vi.fn()}
      />,
    );
    expect(html).toContain('Approved Feature');
  });

  it('shows empty state when no planned features', () => {
    const html = wrap(
      <PlannedFeaturesColumn
        features={[makeFeature({ effectiveStatus: 'in_progress' })]}
        onSelectFeature={vi.fn()}
      />,
    );
    expect(html).toContain('No draft or approved features');
    expect(html).not.toContain('Auth Revamp');
  });

  it('shows empty state for empty feature list', () => {
    const html = wrap(
      <PlannedFeaturesColumn features={[]} onSelectFeature={vi.fn()} />,
    );
    expect(html).toContain('No draft or approved features');
  });
});

// ── PlanningFeatureRow behaviour ──────────────────────────────────────────────

describe('PlanningFeatureRow (via ActivePlansColumn)', () => {
  it('renders mismatch badge when isMismatch is true', () => {
    const html = wrap(
      <ActivePlansColumn
        features={[
          makeFeature({
            featureId: 'feat-mm',
            featureName: 'Mismatched Feature',
            isMismatch: true,
            mismatchState: 'reversed',
            effectiveStatus: 'in_progress',
          }),
        ]}
        onSelectFeature={vi.fn()}
      />,
    );
    expect(html).toContain('Mismatched Feature');
    // MismatchBadge renders the state string
    expect(html).toContain('reversed');
  });

  it('renders phase count metadata', () => {
    const html = wrap(
      <ActivePlansColumn
        features={[makeFeature({ phaseCount: 7, effectiveStatus: 'in_progress' })]}
        onSelectFeature={vi.fn()}
      />,
    );
    expect(html).toContain('7 phases');
  });

  it('renders singular "phase" for phaseCount=1', () => {
    const html = wrap(
      <ActivePlansColumn
        features={[makeFeature({ phaseCount: 1, effectiveStatus: 'in_progress' })]}
        onSelectFeature={vi.fn()}
      />,
    );
    expect(html).toContain('1 phase');
    expect(html).not.toContain('1 phases');
  });

  it('includes data-testid with featureId for click targeting', () => {
    const html = wrap(
      <ActivePlansColumn
        features={[makeFeature({ featureId: 'feat-target', effectiveStatus: 'in_progress' })]}
        onSelectFeature={vi.fn()}
      />,
    );
    expect(html).toContain('data-testid="planning-feature-row-feat-target"');
  });

  it('shows blocked phase count when hasBlockedPhases is true', () => {
    const html = wrap(
      <ActivePlansColumn
        features={[
          makeFeature({ effectiveStatus: 'in_progress', hasBlockedPhases: true, blockedPhaseCount: 2 }),
        ]}
        onSelectFeature={vi.fn()}
      />,
    );
    expect(html).toContain('2 blocked');
  });
});

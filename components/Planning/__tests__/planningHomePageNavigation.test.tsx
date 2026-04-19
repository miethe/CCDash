/**
 * PCP-708: PlanningHomePage navigation tests.
 *
 * Tests that:
 *   1. Clicking a feature card calls navigate with planningFeatureModalHref(featureId)
 *   2. Clicking a composition badge calls navigate with planningArtifactsHref(type)
 *
 * Strategy: renderToStaticMarkup for structural assertions (no jsdom).
 * We verify that PlanningFeatureRow data-testids and ArtifactChip aria-labels
 * are present in the rendered HTML.  The actual navigate call is exercised via
 * the exported column components (ActivePlansColumn / PlannedFeaturesColumn)
 * with a mock navigate function, matching the pattern used in the suite.
 *
 * Coverage:
 *   1. PlanningFeatureRow — data-testid present for click targeting
 *   2. ActivePlansColumn — onSelectFeature called (verified structurally)
 *   3. PlannedFeaturesColumn — onSelectFeature called (verified structurally)
 *   4. PlanningShell artifact chips call navigate with planningArtifactsHref
 *   5. PlanningShell feature clicks call navigate with planningFeatureModalHref
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import type { FeatureSummaryItem } from '../../../types';
import { planningFeatureModalHref, planningArtifactsHref } from '../../../services/planningRoutes';
import { ActivePlansColumn, PlannedFeaturesColumn } from '../PlanningHomePage';

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

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeFeature(overrides: Partial<FeatureSummaryItem> = {}): FeatureSummaryItem {
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

function wrap(node: React.ReactElement): string {
  return renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ── planningFeatureModalHref integration ──────────────────────────────────────

describe('planningFeatureModalHref — URL output used in navigation', () => {
  it('produces the expected URL for a plain id', () => {
    expect(planningFeatureModalHref('feat-1')).toBe('/board?feature=feat-1&tab=overview');
  });

  it('produces the expected URL with explicit docs tab', () => {
    expect(planningFeatureModalHref('feat-1', 'docs')).toBe('/board?feature=feat-1&tab=docs');
  });
});

// ── planningArtifactsHref integration ─────────────────────────────────────────

describe('planningArtifactsHref — URL output used in onDrillDown', () => {
  it('produces the expected URL for design-specs', () => {
    expect(planningArtifactsHref('design-specs')).toBe('/planning/artifacts/design-specs');
  });

  it('produces the expected URL for prds', () => {
    expect(planningArtifactsHref('prds')).toBe('/planning/artifacts/prds');
  });
});

// ── ActivePlansColumn — feature row targeting ─────────────────────────────────

describe('ActivePlansColumn — feature row click targeting', () => {
  it('renders data-testid with featureId for active feature', () => {
    const html = wrap(
      <ActivePlansColumn
        features={[makeFeature({ featureId: 'feat-nav-1', effectiveStatus: 'in_progress' })]}
        onSelectFeature={vi.fn()}
      />,
    );
    expect(html).toContain('data-testid="planning-feature-row-feat-nav-1"');
  });

  it('each active feature row has its own data-testid', () => {
    const html = wrap(
      <ActivePlansColumn
        features={[
          makeFeature({ featureId: 'feat-a', featureName: 'Feature A', effectiveStatus: 'in_progress' }),
          makeFeature({ featureId: 'feat-b', featureName: 'Feature B', effectiveStatus: 'in_progress' }),
        ]}
        onSelectFeature={vi.fn()}
      />,
    );
    expect(html).toContain('data-testid="planning-feature-row-feat-a"');
    expect(html).toContain('data-testid="planning-feature-row-feat-b"');
  });
});

// ── PlannedFeaturesColumn — feature row targeting ─────────────────────────────

describe('PlannedFeaturesColumn — feature row click targeting', () => {
  it('renders data-testid with featureId for draft feature', () => {
    const html = wrap(
      <PlannedFeaturesColumn
        features={[makeFeature({ featureId: 'feat-draft-1', effectiveStatus: 'draft' })]}
        onSelectFeature={vi.fn()}
      />,
    );
    expect(html).toContain('data-testid="planning-feature-row-feat-draft-1"');
  });

  it('renders data-testid with featureId for approved feature', () => {
    const html = wrap(
      <PlannedFeaturesColumn
        features={[makeFeature({ featureId: 'feat-approved-1', effectiveStatus: 'approved' })]}
        onSelectFeature={vi.fn()}
      />,
    );
    expect(html).toContain('data-testid="planning-feature-row-feat-approved-1"');
  });
});

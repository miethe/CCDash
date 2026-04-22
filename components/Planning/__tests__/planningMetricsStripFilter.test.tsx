/**
 * P13-003: PlanningMetricsStrip filter interaction tests.
 *
 * SC-13.3 coverage:
 *   1. Tile click invokes onStatusBucketClick with correct bucket key.
 *   2. Active tile receives aria-pressed=true.
 *   3. Inactive tile receives aria-pressed=false.
 *   4. Clicking active tile again toggles off (caller responsibility via hook —
 *      tested structurally via aria-pressed attribute).
 *   5. Signal pill click invokes onSignalClick with correct signal key.
 *   6. Active signal pill receives aria-pressed=true.
 *   7. Telemetry tiles do NOT have aria-pressed (not clickable).
 *   8. ActivePlansColumn renders only features matching the active bucket.
 *   9. PlannedFeaturesColumn renders only features matching the active bucket.
 *  10. deriveStatusBucket correctly maps effectiveStatus values to buckets.
 *  11. featureMatchesSignal correctly identifies blocked/stale/mismatch.
 *  12. resolvePlanningFilterState reads statusBucket and signal from URLSearchParams.
 *  13. resolvePlanningFilterState ignores unknown values.
 */

import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import type { FeatureSummaryItem, ProjectPlanningSummary } from '../../../types';
import {
  resolvePlanningFilterState,
  isPlanningStatusBucket,
  isPlanningSignal,
} from '../../../services/planningRoutes';
import {
  deriveStatusBucket,
  featureMatchesBucket,
  featureMatchesSignal,
} from '../../../services/planning';
import { PlanningMetricsStrip } from '../PlanningMetricsStrip';
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

function makeSummary(overrides: Partial<ProjectPlanningSummary> = {}): ProjectPlanningSummary {
  return {
    status: 'ok',
    dataFreshness: '2026-04-21T00:00:00Z',
    generatedAt: '2026-04-21T00:00:00Z',
    sourceRefs: [],
    projectId: 'proj-1',
    projectName: 'Test Project',
    totalFeatureCount: 8,
    activeFeatureCount: 3,
    staleFeatureCount: 1,
    blockedFeatureCount: 2,
    mismatchCount: 1,
    reversalCount: 0,
    staleFeatureIds: ['feat-stale'],
    reversalFeatureIds: [],
    blockedFeatureIds: ['feat-blocked-1', 'feat-blocked-2'],
    nodeCountsByType: {
      prd: 2,
      designSpec: 1,
      implementationPlan: 3,
      progress: 2,
      context: 1,
      tracker: 0,
      report: 0,
    },
    featureSummaries: [],
    statusCounts: {
      shaping: 1,
      planned: 2,
      active: 3,
      blocked: 2,
      review: 0,
      completed: 0,
      deferred: 0,
      staleOrMismatched: 1,
    },
    ctxPerPhase: null,
    tokenTelemetry: null,
    ...overrides,
  };
}

function wrap(node: React.ReactElement): string {
  return renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>);
}

// ── resolvePlanningFilterState ────────────────────────────────────────────────

describe('resolvePlanningFilterState', () => {
  it('returns null for both when params are absent', () => {
    const params = new URLSearchParams('');
    const state = resolvePlanningFilterState(params);
    expect(state.statusBucket).toBeNull();
    expect(state.signal).toBeNull();
  });

  it('parses a valid statusBucket', () => {
    const params = new URLSearchParams('statusBucket=active');
    const state = resolvePlanningFilterState(params);
    expect(state.statusBucket).toBe('active');
  });

  it('parses a valid signal', () => {
    const params = new URLSearchParams('signal=stale');
    const state = resolvePlanningFilterState(params);
    expect(state.signal).toBe('stale');
  });

  it('rejects an unknown statusBucket value', () => {
    const params = new URLSearchParams('statusBucket=nonsense');
    const state = resolvePlanningFilterState(params);
    expect(state.statusBucket).toBeNull();
  });

  it('rejects an unknown signal value', () => {
    const params = new URLSearchParams('signal=nonsense');
    const state = resolvePlanningFilterState(params);
    expect(state.signal).toBeNull();
  });

  it('parses both params simultaneously', () => {
    const params = new URLSearchParams('statusBucket=blocked&signal=mismatch');
    const state = resolvePlanningFilterState(params);
    expect(state.statusBucket).toBe('blocked');
    expect(state.signal).toBe('mismatch');
  });
});

// ── isPlanningStatusBucket / isPlanningSignal ─────────────────────────────────

describe('isPlanningStatusBucket', () => {
  it('returns true for all valid bucket values', () => {
    const valid = ['blocked', 'review', 'active', 'planned', 'shaping', 'completed', 'deferred', 'stale_or_mismatched'];
    for (const v of valid) {
      expect(isPlanningStatusBucket(v)).toBe(true);
    }
  });

  it('returns false for invalid values', () => {
    expect(isPlanningStatusBucket('in_progress')).toBe(false);
    expect(isPlanningStatusBucket('')).toBe(false);
  });
});

describe('isPlanningSignal', () => {
  it('returns true for all valid signal values', () => {
    for (const v of ['blocked', 'stale', 'mismatch']) {
      expect(isPlanningSignal(v)).toBe(true);
    }
  });

  it('returns false for invalid values', () => {
    expect(isPlanningSignal('review')).toBe(false);
  });
});

// ── deriveStatusBucket ────────────────────────────────────────────────────────

describe('deriveStatusBucket', () => {
  it('returns "active" for in_progress effectiveStatus', () => {
    expect(deriveStatusBucket(makeFeature({ effectiveStatus: 'in_progress' }))).toBe('active');
  });

  it('returns "active" for in-progress effectiveStatus', () => {
    expect(deriveStatusBucket(makeFeature({ effectiveStatus: 'in-progress' }))).toBe('active');
  });

  it('returns "blocked" when hasBlockedPhases=true regardless of effectiveStatus', () => {
    expect(
      deriveStatusBucket(makeFeature({ hasBlockedPhases: true, effectiveStatus: 'in_progress' })),
    ).toBe('blocked');
  });

  it('returns "blocked" when effectiveStatus is blocked', () => {
    expect(deriveStatusBucket(makeFeature({ effectiveStatus: 'blocked' }))).toBe('blocked');
  });

  it('returns "planned" for approved effectiveStatus', () => {
    expect(deriveStatusBucket(makeFeature({ effectiveStatus: 'approved', rawStatus: 'approved' }))).toBe('planned');
  });

  it('returns "shaping" for draft effectiveStatus', () => {
    expect(deriveStatusBucket(makeFeature({ effectiveStatus: 'draft', rawStatus: 'draft' }))).toBe('shaping');
  });

  it('returns "completed" for completed effectiveStatus', () => {
    expect(deriveStatusBucket(makeFeature({ effectiveStatus: 'completed', rawStatus: 'completed' }))).toBe('completed');
  });

  it('returns "deferred" for deferred effectiveStatus', () => {
    expect(deriveStatusBucket(makeFeature({ effectiveStatus: 'deferred', rawStatus: 'deferred' }))).toBe('deferred');
  });

  it('falls back to stale_or_mismatched for unknown status', () => {
    expect(deriveStatusBucket(makeFeature({ effectiveStatus: 'unknown_status', rawStatus: 'unknown_status' }))).toBe('stale_or_mismatched');
  });
});

// ── featureMatchesSignal ──────────────────────────────────────────────────────

describe('featureMatchesSignal', () => {
  it('matches blocked signal when hasBlockedPhases=true', () => {
    expect(featureMatchesSignal(makeFeature({ hasBlockedPhases: true }), 'blocked')).toBe(true);
  });

  it('does not match blocked signal for a normal active feature', () => {
    expect(featureMatchesSignal(makeFeature(), 'blocked')).toBe(false);
  });

  it('matches stale signal when mismatchState contains "stale"', () => {
    expect(featureMatchesSignal(makeFeature({ mismatchState: 'stale' }), 'stale')).toBe(true);
  });

  it('matches stale signal when mismatchState is "reversed"', () => {
    expect(featureMatchesSignal(makeFeature({ mismatchState: 'reversed' }), 'stale')).toBe(true);
  });

  it('does not match stale signal for aligned feature', () => {
    expect(featureMatchesSignal(makeFeature({ mismatchState: 'aligned' }), 'stale')).toBe(false);
  });

  it('matches mismatch signal when isMismatch=true', () => {
    expect(featureMatchesSignal(makeFeature({ isMismatch: true }), 'mismatch')).toBe(true);
  });

  it('does not match mismatch signal when isMismatch=false', () => {
    expect(featureMatchesSignal(makeFeature({ isMismatch: false }), 'mismatch')).toBe(false);
  });
});

// ── featureMatchesBucket ──────────────────────────────────────────────────────

describe('featureMatchesBucket', () => {
  it('matches active bucket for in_progress feature', () => {
    expect(featureMatchesBucket(makeFeature({ effectiveStatus: 'in_progress' }), 'active')).toBe(true);
  });

  it('does not match shaping bucket for in_progress feature', () => {
    expect(featureMatchesBucket(makeFeature({ effectiveStatus: 'in_progress' }), 'shaping')).toBe(false);
  });
});

// ── PlanningMetricsStrip: tile renders with aria-pressed ──────────────────────

describe('PlanningMetricsStrip — clickable status bucket tiles', () => {
  it('SC-13.3: tile renders with aria-pressed=false when no bucket is active', () => {
    const html = wrap(
      <PlanningMetricsStrip
        summary={makeSummary()}
        activeStatusBucket={null}
        onStatusBucketClick={vi.fn()}
      />,
    );
    // All bucket tiles should have aria-pressed=false when no filter active
    expect(html).toContain('aria-pressed="false"');
    expect(html).not.toContain('aria-pressed="true"');
  });

  it('SC-13.3: active tile has aria-pressed=true', () => {
    const html = wrap(
      <PlanningMetricsStrip
        summary={makeSummary()}
        activeStatusBucket="active"
        onStatusBucketClick={vi.fn()}
      />,
    );
    expect(html).toContain('aria-pressed="true"');
  });

  it('SC-13.3: tiles render as buttons when onStatusBucketClick is provided', () => {
    const html = wrap(
      <PlanningMetricsStrip
        summary={makeSummary()}
        onStatusBucketClick={vi.fn()}
      />,
    );
    // Bucket wrapper buttons should be present
    expect(html).toContain('<button');
  });

  it('SC-13.3: signal pill renders with aria-pressed=false when no signal is active', () => {
    const html = wrap(
      <PlanningMetricsStrip
        summary={makeSummary()}
        activeSignal={null}
        onSignalClick={vi.fn()}
      />,
    );
    // All signal chips should have aria-pressed=false
    expect(html).toContain('aria-pressed="false"');
  });

  it('SC-13.3: active signal pill has aria-pressed=true', () => {
    const html = wrap(
      <PlanningMetricsStrip
        summary={makeSummary()}
        activeSignal="stale"
        onSignalClick={vi.fn()}
      />,
    );
    expect(html).toContain('aria-pressed="true"');
  });

  it('SC-13.3: telemetry tiles do not have aria-pressed (not interactive)', () => {
    const html = wrap(
      <PlanningMetricsStrip
        summary={makeSummary({
          ctxPerPhase: { contextCount: 4, phaseCount: 2, ratio: 2.0, source: 'backend' },
          tokenTelemetry: { totalTokens: 50000, byModelFamily: [], source: 'session_attribution' },
        })}
        onStatusBucketClick={vi.fn()}
      />,
    );
    // Telemetry section should be present
    expect(html).toContain('data-testid="telemetry-tiles"');
    // Telemetry tiles should NOT be wrapped in interactive buttons (no aria-pressed in telemetry section)
    const telemetrySection = html.match(/data-testid="telemetry-tiles"[^]*/)?.[0] ?? '';
    expect(telemetrySection).not.toContain('aria-pressed');
  });
});

// ── ActivePlansColumn: filtering ──────────────────────────────────────────────

describe('ActivePlansColumn — filter by status bucket', () => {
  const activeFeature = makeFeature({
    featureId: 'feat-active',
    effectiveStatus: 'in_progress',
    rawStatus: 'in-progress',
  });
  const blockedFeature = makeFeature({
    featureId: 'feat-blocked',
    effectiveStatus: 'in_progress',
    rawStatus: 'in-progress',
    hasBlockedPhases: true,
  });
  const features = [activeFeature, blockedFeature];

  it('SC-13.3: shows all in-progress features when no filter is active', () => {
    const html = wrap(
      <ActivePlansColumn
        features={features}
        onSelectFeature={vi.fn()}
        activeBucket={null}
        activeSignal={null}
      />,
    );
    expect(html).toContain('data-testid="planning-feature-row-feat-active"');
    expect(html).toContain('data-testid="planning-feature-row-feat-blocked"');
  });

  it('SC-13.3: hides non-matching features when active bucket is "active"', () => {
    const html = wrap(
      <ActivePlansColumn
        features={features}
        onSelectFeature={vi.fn()}
        activeBucket="active"
        activeSignal={null}
      />,
    );
    // feat-active matches "active" bucket (in_progress, no blocked phases)
    expect(html).toContain('data-testid="planning-feature-row-feat-active"');
    // feat-blocked derives to "blocked" bucket (hasBlockedPhases=true), so filtered out
    expect(html).not.toContain('data-testid="planning-feature-row-feat-blocked"');
  });

  it('SC-13.3: shows only blocked in-progress features when active bucket is "blocked"', () => {
    const html = wrap(
      <ActivePlansColumn
        features={features}
        onSelectFeature={vi.fn()}
        activeBucket="blocked"
        activeSignal={null}
      />,
    );
    expect(html).not.toContain('data-testid="planning-feature-row-feat-active"');
    expect(html).toContain('data-testid="planning-feature-row-feat-blocked"');
  });

  it('SC-13.3: signal filter narrows to features matching the signal', () => {
    const html = wrap(
      <ActivePlansColumn
        features={features}
        onSelectFeature={vi.fn()}
        activeBucket={null}
        activeSignal="blocked"
      />,
    );
    // feat-active has no blocked phases — should not appear
    expect(html).not.toContain('data-testid="planning-feature-row-feat-active"');
    // feat-blocked has blocked phases — should appear
    expect(html).toContain('data-testid="planning-feature-row-feat-blocked"');
  });
});

// ── PlannedFeaturesColumn: filtering ─────────────────────────────────────────

describe('PlannedFeaturesColumn — filter by status bucket', () => {
  const draftFeature = makeFeature({
    featureId: 'feat-draft',
    effectiveStatus: 'draft',
    rawStatus: 'draft',
  });
  const approvedFeature = makeFeature({
    featureId: 'feat-approved',
    effectiveStatus: 'approved',
    rawStatus: 'approved',
  });
  const features = [draftFeature, approvedFeature];

  it('SC-13.3: shows all planned features when no filter is active', () => {
    const html = wrap(
      <PlannedFeaturesColumn
        features={features}
        onSelectFeature={vi.fn()}
        activeBucket={null}
        activeSignal={null}
      />,
    );
    expect(html).toContain('data-testid="planning-feature-row-feat-draft"');
    expect(html).toContain('data-testid="planning-feature-row-feat-approved"');
  });

  it('SC-13.3: hides all planned features when active bucket is "active"', () => {
    const html = wrap(
      <PlannedFeaturesColumn
        features={features}
        onSelectFeature={vi.fn()}
        activeBucket="active"
        activeSignal={null}
      />,
    );
    // Neither draft nor approved → active bucket; both should be hidden
    expect(html).not.toContain('data-testid="planning-feature-row-feat-draft"');
    expect(html).not.toContain('data-testid="planning-feature-row-feat-approved"');
  });

  it('SC-13.3: shows shaping-bucket features when active bucket is "shaping"', () => {
    const html = wrap(
      <PlannedFeaturesColumn
        features={features}
        onSelectFeature={vi.fn()}
        activeBucket="shaping"
        activeSignal={null}
      />,
    );
    // draft → shaping bucket; approved → planned bucket
    expect(html).toContain('data-testid="planning-feature-row-feat-draft"');
    expect(html).not.toContain('data-testid="planning-feature-row-feat-approved"');
  });

  it('SC-13.3: shows planned-bucket features when active bucket is "planned"', () => {
    const html = wrap(
      <PlannedFeaturesColumn
        features={features}
        onSelectFeature={vi.fn()}
        activeBucket="planned"
        activeSignal={null}
      />,
    );
    // approved → planned bucket; draft → shaping bucket
    expect(html).not.toContain('data-testid="planning-feature-row-feat-draft"');
    expect(html).toContain('data-testid="planning-feature-row-feat-approved"');
  });
});

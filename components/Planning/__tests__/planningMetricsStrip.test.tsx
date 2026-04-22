/**
 * P13-002: PlanningMetricsStrip tests.
 *
 * Verifies:
 *   1. Status buckets render from statusCounts (mutually exclusive).
 *   2. Health signals row is visually distinct and labeled "Signals".
 *   3. Signals are NOT double-counted as status buckets.
 *   4. ctxPerPhase tile renders backend data when available.
 *   5. ctxPerPhase tile renders "unavailable" when source === 'unavailable'.
 *   6. ctxPerPhase tile renders "unavailable" when ctxPerPhase is null.
 *   7. tokenTelemetry tile renders data when available.
 *   8. tokenTelemetry tile renders "unavailable" when source === 'unavailable'.
 *   9. tokenTelemetry tile renders "unavailable" when tokenTelemetry is null.
 *  10. No fabricated values — tiles source from summary fields only.
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { ProjectPlanningSummary, FeatureSummaryItem } from '../../../types';
import { PlanningMetricsStrip } from '../PlanningMetricsStrip';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const makeFeatureSummary = (overrides: Partial<FeatureSummaryItem> = {}): FeatureSummaryItem => ({
  featureId: 'feat-1',
  featureName: 'Auth Revamp',
  rawStatus: 'in-progress',
  effectiveStatus: 'in_progress',
  isMismatch: false,
  mismatchState: 'aligned',
  hasBlockedPhases: false,
  phaseCount: 2,
  blockedPhaseCount: 0,
  nodeCount: 4,
  ...overrides,
});

const makeSummary = (overrides: Partial<ProjectPlanningSummary> = {}): ProjectPlanningSummary => ({
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
  featureSummaries: [makeFeatureSummary()],
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
  ctxPerPhase: {
    contextCount: 6,
    phaseCount: 3,
    ratio: 2.0,
    source: 'backend',
  },
  tokenTelemetry: {
    totalTokens: 48000,
    byModelFamily: [{ modelFamily: 'claude-sonnet', totalTokens: 48000 }],
    source: 'session_attribution',
  },
  ...overrides,
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('PlanningMetricsStrip', () => {
  // ── Status buckets ──────────────────────────────────────────────────────────

  it('SC-13.2: renders status buckets section with data-testid', () => {
    const html = renderToStaticMarkup(<PlanningMetricsStrip summary={makeSummary()} />);
    expect(html).toContain('data-testid="status-buckets"');
  });

  it('SC-13.2: renders all eight status bucket labels', () => {
    const html = renderToStaticMarkup(<PlanningMetricsStrip summary={makeSummary()} />);
    expect(html).toContain('Shaping');
    expect(html).toContain('Planned');
    expect(html).toContain('Active');
    expect(html).toContain('Review');
    expect(html).toContain('Completed');
    expect(html).toContain('Deferred');
    expect(html).toContain('Stale');
    expect(html).toContain('Blocked');
  });

  it('SC-13.1: bucket values come from statusCounts, not derived heuristics', () => {
    const sc = {
      shaping: 1,
      planned: 2,
      active: 3,
      blocked: 2,
      review: 1,
      completed: 4,
      deferred: 0,
      staleOrMismatched: 1,
    };
    const html = renderToStaticMarkup(
      <PlanningMetricsStrip summary={makeSummary({ statusCounts: sc })} />,
    );
    // Completed must be 4 (from statusCounts), not derived from featureSummaries
    const bucketSection = html.match(/data-testid="status-buckets"[^]*/)?.[0] ?? '';
    expect(bucketSection).toContain('>4<');
  });

  // ── Health signals ──────────────────────────────────────────────────────────

  it('SC-13.2: renders a health signals section with "Signals" label', () => {
    const html = renderToStaticMarkup(<PlanningMetricsStrip summary={makeSummary()} />);
    expect(html).toContain('data-testid="health-signals"');
    expect(html).toContain('Signals');
  });

  it('SC-13.2: signals show blocked, stale, mismatched counts', () => {
    const html = renderToStaticMarkup(
      <PlanningMetricsStrip
        summary={makeSummary({
          blockedFeatureCount: 2,
          staleFeatureCount: 1,
          mismatchCount: 3,
        })}
      />,
    );
    expect(html).toContain('Blocked');
    expect(html).toContain('Stale');
    expect(html).toContain('Mismatched');
    expect(html).toContain('>2<');
    expect(html).toContain('>1<');
    expect(html).toContain('>3<');
  });

  it('SC-13.2: health signals are in a separate container from status buckets', () => {
    const html = renderToStaticMarkup(<PlanningMetricsStrip summary={makeSummary()} />);
    const bucketsIdx = html.indexOf('data-testid="status-buckets"');
    const signalsIdx = html.indexOf('data-testid="health-signals"');
    // Both sections exist and are separate (signals comes after buckets)
    expect(bucketsIdx).toBeGreaterThan(-1);
    expect(signalsIdx).toBeGreaterThan(bucketsIdx);
  });

  // ── Ctx per phase ───────────────────────────────────────────────────────────

  it('SC-13.1: renders ctx-per-phase tile with real data when source is backend', () => {
    const html = renderToStaticMarkup(
      <PlanningMetricsStrip
        summary={makeSummary({
          ctxPerPhase: { contextCount: 6, phaseCount: 3, ratio: 2.0, source: 'backend' },
        })}
      />,
    );
    expect(html).toContain('data-testid="ctx-per-phase"');
    expect(html).toContain('Ctx / Phase');
    // ratio formatted as "2.0"
    expect(html).toContain('2.0');
    // sub-label contains raw counts
    expect(html).toContain('6 ctx');
    expect(html).toContain('3 phases');
  });

  it('SC-13.1: renders ctx-per-phase as unavailable when source is unavailable', () => {
    const html = renderToStaticMarkup(
      <PlanningMetricsStrip
        summary={makeSummary({
          ctxPerPhase: { contextCount: 0, phaseCount: 0, ratio: null, source: 'unavailable' },
        })}
      />,
    );
    expect(html).toContain('data-testid="ctx-per-phase-unavailable"');
    expect(html).toContain('unavailable');
    // Should not show fabricated numbers
    expect(html).not.toContain('>2.0<');
  });

  it('SC-13.1: renders ctx-per-phase as unavailable when ctxPerPhase is null', () => {
    const html = renderToStaticMarkup(
      <PlanningMetricsStrip summary={makeSummary({ ctxPerPhase: null })} />,
    );
    expect(html).toContain('data-testid="ctx-per-phase-unavailable"');
    expect(html).toContain('unavailable');
  });

  // ── Token telemetry ─────────────────────────────────────────────────────────

  it('SC-13.1: renders token telemetry tile with formatted total when available', () => {
    const html = renderToStaticMarkup(
      <PlanningMetricsStrip
        summary={makeSummary({
          tokenTelemetry: {
            totalTokens: 48000,
            byModelFamily: [{ modelFamily: 'claude-sonnet', totalTokens: 48000 }],
            source: 'session_attribution',
          },
        })}
      />,
    );
    expect(html).toContain('data-testid="token-telemetry"');
    expect(html).toContain('Total Tokens');
    expect(html).toContain('48K');
    expect(html).toContain('claude-sonnet');
  });

  it('SC-13.1: formats large token counts as M suffix', () => {
    const html = renderToStaticMarkup(
      <PlanningMetricsStrip
        summary={makeSummary({
          tokenTelemetry: {
            totalTokens: 2_500_000,
            byModelFamily: [],
            source: 'session_attribution',
          },
        })}
      />,
    );
    expect(html).toContain('2.5M');
  });

  it('SC-13.1: renders token telemetry as unavailable when source is unavailable', () => {
    const html = renderToStaticMarkup(
      <PlanningMetricsStrip
        summary={makeSummary({
          tokenTelemetry: {
            totalTokens: null,
            byModelFamily: [],
            source: 'unavailable',
          },
        })}
      />,
    );
    expect(html).toContain('data-testid="token-telemetry-unavailable"');
    expect(html).toContain('unavailable');
  });

  it('SC-13.1: renders token telemetry as unavailable when tokenTelemetry is null', () => {
    const html = renderToStaticMarkup(
      <PlanningMetricsStrip summary={makeSummary({ tokenTelemetry: null })} />,
    );
    expect(html).toContain('data-testid="token-telemetry-unavailable"');
    expect(html).toContain('unavailable');
  });

  // ── Telemetry section ───────────────────────────────────────────────────────

  it('SC-13.1: telemetry tiles render in their own section', () => {
    const html = renderToStaticMarkup(<PlanningMetricsStrip summary={makeSummary()} />);
    expect(html).toContain('data-testid="telemetry-tiles"');
  });
});

/**
 * Tests for the Are-We-Winning dashboard's pure chart-data helpers
 * (are-we-winning-dashboard-v1, M3).
 *
 * These are the rubric-critical assertions for the "unknown must render as
 * a first-class, visually prominent bucket" requirement — checked at the
 * pure-function layer so they don't depend on rendering recharts internals.
 */

import { describe, expect, it } from 'vitest';
import {
  formatRatioBucketPercent,
  ratioToChartData,
  trendlineToChartPoints,
  weeklyPointToChartPoint,
  SELF_CAUGHT_RATIO_BUCKET_ORDER,
} from '../areWeWinning';
import type { AreWeWinningTrendline, SelfCaughtRatio } from '../../types';

describe('weeklyPointToChartPoint / trendlineToChartPoints', () => {
  it('maps a weekly point to a chart point carrying drill-through bucket coordinates', () => {
    const point = weeklyPointToChartPoint('node.created', {
      isoYear: 2026,
      isoWeek: 33,
      weekStartDate: '2026-08-10',
      count: 7,
    });

    expect(point.date).toBe('2026-08-10');
    expect(point.value).toBe(7);
    expect(point.meta).toEqual({ eventType: 'node.created', isoYear: 2026, isoWeek: 33 });
    expect(point.fullDate).toContain('2026-08-10');
  });

  it('returns an empty array for a null/undefined trendline (absent, not fabricated)', () => {
    expect(trendlineToChartPoints(null)).toEqual([]);
    expect(trendlineToChartPoints(undefined)).toEqual([]);
  });

  it('maps every point in a populated trendline', () => {
    const trendline: AreWeWinningTrendline = {
      eventType: 'node.completed',
      points: [
        { isoYear: 2026, isoWeek: 1, weekStartDate: '2026-01-05', count: 3 },
        { isoYear: 2026, isoWeek: 2, weekStartDate: '2026-01-12', count: 5 },
      ],
    };

    const points = trendlineToChartPoints(trendline);

    expect(points).toHaveLength(2);
    expect(points[1].value).toBe(5);
    expect(points[1].meta.isoWeek).toBe(2);
  });
});

describe('ratioToChartData', () => {
  it('returns an empty array for a null/undefined ratio (absent, not a fabricated 0/100 split)', () => {
    expect(ratioToChartData(null)).toEqual([]);
    expect(ratioToChartData(undefined)).toEqual([]);
  });

  it('renders every closed-vocabulary bucket even when the backend omits one entirely', () => {
    const ratio: SelfCaughtRatio = {
      buckets: [{ bucket: 'unknown', count: 200 }],
      total: 200,
    };

    const data = ratioToChartData(ratio);

    // All 3 buckets are present — self_caught/other_caught fill in as
    // explicit zero, never silently disappearing from the legend/chart.
    expect(data.map((d) => d.bucket).sort()).toEqual([...SELF_CAUGHT_RATIO_BUCKET_ORDER].sort());
    expect(data.find((d) => d.bucket === 'self_caught')!.value).toBe(0);
    expect(data.find((d) => d.bucket === 'other_caught')!.value).toBe(0);
  });

  it('renders the unknown bucket as a first-class entry even when it is 100% of the population', () => {
    const ratio: SelfCaughtRatio = {
      buckets: [
        { bucket: 'self_caught', count: 0 },
        { bucket: 'other_caught', count: 0 },
        { bucket: 'unknown', count: 200 },
      ],
      total: 200,
    };

    const data = ratioToChartData(ratio);
    const unknownEntry = data.find((d) => d.bucket === 'unknown');

    expect(unknownEntry).toBeDefined();
    expect(unknownEntry!.value).toBe(200);
    expect(unknownEntry!.label).toBe('Unknown');
    // A dominant-unknown ratio must never be dropped or zeroed out — it is
    // the correct rendering of measured reality (worknote: 17/200, 7/200).
    expect(unknownEntry!.value).toBe(ratio.total);
  });

  it('maps real per-bucket counts through unchanged', () => {
    const ratio: SelfCaughtRatio = {
      buckets: [
        { bucket: 'self_caught', count: 5 },
        { bucket: 'other_caught', count: 2 },
        { bucket: 'unknown', count: 193 },
      ],
      total: 200,
    };

    const data = ratioToChartData(ratio);

    expect(data.find((d) => d.bucket === 'self_caught')!.value).toBe(5);
    expect(data.find((d) => d.bucket === 'other_caught')!.value).toBe(2);
    expect(data.find((d) => d.bucket === 'unknown')!.value).toBe(193);
  });
});

describe('formatRatioBucketPercent', () => {
  it('renders an explicit em-dash for a zero-total population, never a fabricated 0%/NaN%', () => {
    expect(formatRatioBucketPercent(0, 0)).toBe('—');
  });

  it('computes a real percentage for a non-zero total', () => {
    expect(formatRatioBucketPercent(193, 200)).toBe('96.5%');
  });

  it('renders 100.0% when a single bucket is the entire population', () => {
    expect(formatRatioBucketPercent(200, 200)).toBe('100.0%');
  });
});

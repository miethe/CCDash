/**
 * Pure helpers for the Are-We-Winning dashboard (are-we-winning-dashboard-v1,
 * M3). Kept dependency-free from React/recharts so the "unknown must render
 * as a first-class, visually prominent bucket" rubric item can be asserted
 * with plain unit tests, not a full component render.
 */

import type {
  AreWeWinningTrendline,
  AreWeWinningWeeklyPoint,
  SelfCaughtRatio,
  SelfCaughtRatioBucketId,
} from '../types';
import type { InteractiveChartDatum } from '../components/Analytics/primitives/InteractiveChartCard';

// ── Trendline → chart point mapping ─────────────────────────────────────────

export interface AreWeWinningChartPoint {
  /** Display label for the X axis (the ISO week's Monday date). */
  date: string;
  /** Tooltip label — human-readable ISO week + date. */
  fullDate: string;
  value: number;
  /** Bucket coordinates for drill-through — set only from a click handler. */
  meta: { eventType: string; isoYear: number; isoWeek: number };
}

export function weeklyPointToChartPoint(
  eventType: string,
  point: AreWeWinningWeeklyPoint,
): AreWeWinningChartPoint {
  return {
    date: point.weekStartDate,
    fullDate: `ISO week ${point.isoWeek}, ${point.isoYear} (starts ${point.weekStartDate})`,
    value: point.count,
    meta: { eventType, isoYear: point.isoYear, isoWeek: point.isoWeek },
  };
}

export function trendlineToChartPoints(
  trendline: AreWeWinningTrendline | null | undefined,
): AreWeWinningChartPoint[] {
  if (!trendline) return [];
  return trendline.points.map((point) => weeklyPointToChartPoint(trendline.eventType, point));
}

// ── Self-caught ratio → chart data ──────────────────────────────────────────

/** Fixed render order — `unknown` last so its slice/legend row reads as the
 * "residual reality" bucket rather than being buried alphabetically first. */
export const SELF_CAUGHT_RATIO_BUCKET_ORDER: SelfCaughtRatioBucketId[] = [
  'self_caught',
  'other_caught',
  'unknown',
];

export const SELF_CAUGHT_RATIO_BUCKET_LABELS: Record<SelfCaughtRatioBucketId, string> = {
  self_caught: 'Self-caught',
  other_caught: 'Other-caught',
  unknown: 'Unknown',
};

/** Tone key into lib/chartTheme.ts's CHART_SERIES_COLORS. `unknown` is
 * deliberately the loudest tone (danger) — its dominance is measured reality
 * (17/200, 7/200 sampled nodes carry any discriminator at all), not a bug to
 * visually downplay. */
export const SELF_CAUGHT_RATIO_BUCKET_TONE: Record<SelfCaughtRatioBucketId, 'success' | 'info' | 'danger'> = {
  self_caught: 'success',
  other_caught: 'info',
  unknown: 'danger',
};

/**
 * Every bucket in `SELF_CAUGHT_RATIO_BUCKET_ORDER` renders even if the
 * backend omitted it (count 0) — the ratio's shape is closed-vocabulary, so
 * a missing bucket in the response is filled in as an explicit zero rather
 * than silently disappearing from the legend/chart.
 */
export function ratioToChartData(
  ratio: SelfCaughtRatio | null | undefined,
): Array<InteractiveChartDatum & { bucket: SelfCaughtRatioBucketId; countValue: number }> {
  if (!ratio) return [];
  const byBucket = new Map(ratio.buckets.map((b) => [b.bucket, b.count] as const));
  return SELF_CAUGHT_RATIO_BUCKET_ORDER.map((bucket) => {
    const count = byBucket.get(bucket) ?? 0;
    return {
      key: bucket,
      label: SELF_CAUGHT_RATIO_BUCKET_LABELS[bucket],
      value: count,
      bucket,
      countValue: count,
    };
  });
}

export function formatRatioBucketPercent(count: number, total: number): string {
  if (total <= 0) return '—';
  return `${((count / total) * 100).toFixed(1)}%`;
}

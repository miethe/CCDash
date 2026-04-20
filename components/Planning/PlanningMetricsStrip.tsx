import type { ProjectPlanningSummary } from '../../types';
import { MetricTile } from './primitives';

// ── Derived counts ─────────────────────────────────────────────────────────────

function deriveMetrics(summary: ProjectPlanningSummary) {
  const completedCount = summary.featureSummaries.filter(
    (f) => f.effectiveStatus === 'completed',
  ).length;

  return {
    total: summary.totalFeatureCount,
    active: summary.activeFeatureCount,
    blocked: summary.blockedFeatureCount,
    stale: summary.staleFeatureCount,
    mismatches: summary.mismatchCount,
    completed: completedCount,
  };
}

// ── Component ──────────────────────────────────────────────────────────────────

/**
 * PlanningMetricsStrip — six-tile feature-health summary.
 *
 * Renders beneath the HeroHeader in PlanningShell (T2-002).
 * Grid: 6 cols on desktop, wraps on narrow viewports (2 cols on sm, 3 on md).
 * Accent colors from Phase 0 design tokens (planning-tokens.css).
 */
export function PlanningMetricsStrip({
  summary,
}: {
  summary: ProjectPlanningSummary;
}) {
  const { total, active, blocked, stale, mismatches, completed } = deriveMetrics(summary);

  return (
    <div
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6"
      data-testid="planning-metrics-strip"
      aria-label="Feature health summary"
    >
      <MetricTile
        label="Features"
        value={total}
        sub="total"
        accent="var(--ink-0)"
      />
      <MetricTile
        label="Active"
        value={active}
        sub="in-progress"
        accent="var(--brand)"
      />
      <MetricTile
        label="Blocked"
        value={blocked}
        sub="need attention"
        accent="var(--err)"
      />
      <MetricTile
        label="Stale"
        value={stale}
        sub="no recent activity"
        accent="var(--warn)"
      />
      <MetricTile
        label="Mismatches"
        value={mismatches}
        sub="status drift"
        accent="var(--mag)"
      />
      <MetricTile
        label="Completed"
        value={completed}
        sub="shipped"
        accent="var(--ok)"
      />
    </div>
  );
}

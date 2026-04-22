import type { ProjectPlanningSummary } from '../../types';
import type { PlanningStatusBucket, PlanningSignal } from '../../services/planningRoutes';
import { MetricTile } from './primitives';

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatTokens(total: number | null): string {
  if (total === null) return '—';
  if (total >= 1_000_000) return `${(total / 1_000_000).toFixed(1)}M`;
  if (total >= 1_000) return `${(total / 1_000).toFixed(0)}K`;
  return String(total);
}

function formatRatio(ratio: number | null): string {
  if (ratio === null) return '—';
  return ratio.toFixed(1);
}

function fallbackStatusCounts(summary: ProjectPlanningSummary) {
  return {
    shaping: 0,
    planned: 0,
    active: summary.activeFeatureCount,
    blocked: summary.blockedFeatureCount,
    review: 0,
    completed: summary.featureSummaries.filter((feature) =>
      ['completed', 'done'].includes((feature.effectiveStatus ?? '').toLowerCase()),
    ).length,
    deferred: summary.featureSummaries.filter((feature) =>
      ['deferred', 'superseded'].includes((feature.effectiveStatus ?? '').toLowerCase()),
    ).length,
    staleOrMismatched: Math.max(summary.staleFeatureCount, summary.mismatchCount),
  };
}

// ── Sub-components ─────────────────────────────────────────────────────────────

interface SignalChipProps {
  label: string;
  count: number;
  accent: string;
  active?: boolean;
  onClick?: () => void;
}

function SignalChip({ label, count, accent, active = false, onClick }: SignalChipProps) {
  const isClickable = onClick !== undefined;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!isClickable}
      aria-pressed={isClickable ? active : undefined}
      aria-label={`${label}: ${count}${isClickable ? (active ? ' — click to clear filter' : ' — click to filter') : ''}`}
      className="planning-chip planning-tnum inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium transition-all"
      style={{
        background: active
          ? `color-mix(in oklab, ${accent} 22%, var(--bg-2))`
          : `color-mix(in oklab, ${accent} 12%, var(--bg-2))`,
        border: `1px solid ${active ? accent : `color-mix(in oklab, ${accent} 28%, var(--line-1))`}`,
        color: `color-mix(in oklab, ${accent} 85%, var(--ink-0))`,
        cursor: isClickable ? 'pointer' : 'default',
        boxShadow: active ? `0 0 0 2px color-mix(in oklab, ${accent} 25%, transparent)` : undefined,
        outline: 'none',
      }}
    >
      <span
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ background: accent }}
        aria-hidden="true"
      />
      <span className="planning-caps text-[9.5px] tracking-[0.08em] opacity-70">{label}</span>
      <span className="font-bold" style={{ color: accent }}>{count}</span>
    </button>
  );
}

// ── Component ──────────────────────────────────────────────────────────────────

export interface PlanningMetricsStripProps {
  summary: ProjectPlanningSummary;
  /** Current active status bucket filter (from URL). */
  activeStatusBucket?: PlanningStatusBucket | null;
  /** Current active health signal filter (from URL). */
  activeSignal?: PlanningSignal | null;
  /** Called when a status bucket tile is clicked (toggle). */
  onStatusBucketClick?: (bucket: PlanningStatusBucket) => void;
  /** Called when a health signal pill is clicked (toggle). */
  onSignalClick?: (signal: PlanningSignal) => void;
}

/**
 * PlanningMetricsStrip — two-section feature-health summary (P13-002/P13-003).
 *
 * Section 1 – Status Buckets: mutually exclusive counts from `statusCounts`.
 *   All buckets sum to totalFeatureCount. Clicking a tile sets route filter
 *   `?statusBucket=<bucket>`. Clicking again clears it.
 * Section 2 – Health Signals: overlay chips for blocked / stale / mismatched.
 *   These are NOT additive to the status total; they are cross-cutting signals.
 *   Clicking a pill sets route filter `?signal=<signal>`. Clicking again clears.
 * Section 3 – Telemetry tiles: ctx-per-phase and token totals.
 *   Both show explicit "unavailable" when the backend cannot supply data.
 *   Telemetry tiles are NOT clickable.
 *
 * Renders beneath the HeroHeader in PlanningShell.
 */
export function PlanningMetricsStrip({
  summary,
  activeStatusBucket = null,
  activeSignal = null,
  onStatusBucketClick,
  onSignalClick,
}: PlanningMetricsStripProps) {
  const sc = summary.statusCounts ?? fallbackStatusCounts(summary);
  const ctx = summary.ctxPerPhase;
  const tok = summary.tokenTelemetry;

  const ctxUnavailable = !ctx || ctx.source === 'unavailable';
  const tokUnavailable = !tok || tok.source === 'unavailable';

  // Helper: wrap a MetricTile as a clickable button if handler is supplied
  function BucketTile({
    bucket,
    label,
    value,
    sub,
    accent,
    testId,
  }: {
    bucket: PlanningStatusBucket;
    label: string;
    value: number;
    sub: string;
    accent: string;
    testId?: string;
  }) {
    const isActive = activeStatusBucket === bucket;
    if (!onStatusBucketClick) {
      return (
        <MetricTile
          label={label}
          value={value}
          sub={sub}
          accent={accent}
          data-testid={testId}
        />
      );
    }
    return (
      <button
        type="button"
        data-testid={testId ?? `bucket-tile-${bucket}`}
        aria-pressed={isActive}
        aria-label={`${label}: ${value}${isActive ? ' — click to clear filter' : ' — click to filter'}`}
        onClick={() => onStatusBucketClick(bucket)}
        className="w-full text-left"
        style={{ outline: 'none', background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
      >
        <MetricTile
          label={label}
          value={value}
          sub={sub}
          accent={accent}
          style={{
            outline: isActive ? `2px solid ${accent}` : undefined,
            outlineOffset: isActive ? '2px' : undefined,
            background: isActive
              ? `color-mix(in oklab, ${accent} 10%, var(--bg-2))`
              : undefined,
            transition: 'outline 120ms ease, background 120ms ease',
          }}
        />
      </button>
    );
  }

  return (
    <div
      data-testid="planning-metrics-strip"
      aria-label="Feature health summary"
      className="flex flex-col gap-3"
    >
      {/* ── Section 1: Status Buckets ─────────────────────────────────────── */}
      <div aria-label="Status buckets" className="flex flex-col gap-1.5">
        <div className="planning-caps text-[9.5px] tracking-[0.08em] text-[color:var(--ink-3)]">
          Status Distribution
        </div>
        <div
          data-testid="status-buckets"
          className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8"
        >
          <BucketTile
            bucket="shaping"
            label="Shaping"
            value={sc.shaping}
            sub="ideation"
            accent="var(--info)"
          />
          <BucketTile
            bucket="planned"
            label="Planned"
            value={sc.planned}
            sub="ready"
            accent="var(--spec)"
          />
          <BucketTile
            bucket="active"
            label="Active"
            value={sc.active}
            sub="in-progress"
            accent="var(--brand)"
          />
          <BucketTile
            bucket="review"
            label="Review"
            value={sc.review}
            sub="in review"
            accent="var(--prd)"
          />
          <BucketTile
            bucket="completed"
            label="Completed"
            value={sc.completed}
            sub="shipped"
            accent="var(--ok)"
          />
          <BucketTile
            bucket="deferred"
            label="Deferred"
            value={sc.deferred}
            sub="paused"
            accent="var(--ink-3)"
          />
          <BucketTile
            bucket="stale_or_mismatched"
            label="Stale / Drift"
            value={sc.staleOrMismatched}
            sub="needs triage"
            accent="var(--warn)"
          />
          <BucketTile
            bucket="blocked"
            label="Blocked"
            value={sc.blocked}
            sub="hard stop"
            accent="var(--err)"
          />
        </div>
      </div>

      {/* ── Section 2: Health Signals ─────────────────────────────────────── */}
      <div
        data-testid="health-signals"
        className="flex flex-wrap items-center gap-2 rounded-lg border border-[color:var(--line-1)] bg-[color:var(--bg-2)] px-3 py-2"
        aria-label="Health signals"
      >
        <span className="planning-caps text-[9.5px] tracking-[0.08em] text-[color:var(--ink-3)]">
          Signals
        </span>
        <div className="mx-1 h-3.5 w-px bg-[color:var(--line-1)]" aria-hidden="true" />
        <SignalChip
          label="Blocked"
          count={summary.blockedFeatureCount}
          accent="var(--err)"
          active={activeSignal === 'blocked'}
          onClick={onSignalClick ? () => onSignalClick('blocked') : undefined}
        />
        <SignalChip
          label="Stale"
          count={summary.staleFeatureCount}
          accent="var(--warn)"
          active={activeSignal === 'stale'}
          onClick={onSignalClick ? () => onSignalClick('stale') : undefined}
        />
        <SignalChip
          label="Mismatched"
          count={summary.mismatchCount}
          accent="var(--mag)"
          active={activeSignal === 'mismatch'}
          onClick={onSignalClick ? () => onSignalClick('mismatch') : undefined}
        />
        <span className="ml-auto planning-caps text-[9px] text-[color:var(--ink-3)] italic">
          overlapping — not additive
        </span>
      </div>

      {/* ── Section 3: Telemetry tiles ────────────────────────────────────── */}
      <div
        data-testid="telemetry-tiles"
        className="grid grid-cols-2 gap-2"
        aria-label="Telemetry metrics"
      >
        {/* Ctx / phase */}
        {ctxUnavailable ? (
          <MetricTile
            label="Ctx / Phase"
            value={
              <span className="text-[color:var(--ink-3)]" aria-label="unavailable">
                —
              </span>
            }
            sub="unavailable"
            accent="var(--ink-3)"
            data-testid="ctx-per-phase-unavailable"
          />
        ) : (
          <MetricTile
            label="Ctx / Phase"
            value={formatRatio(ctx!.ratio)}
            sub={`${ctx!.contextCount} ctx · ${ctx!.phaseCount} phases`}
            accent="var(--ctx)"
            data-testid="ctx-per-phase"
          />
        )}

        {/* Token telemetry */}
        {tokUnavailable ? (
          <MetricTile
            label="Total Tokens"
            value={
              <span className="text-[color:var(--ink-3)]" aria-label="unavailable">
                —
              </span>
            }
            sub="unavailable"
            accent="var(--ink-3)"
            data-testid="token-telemetry-unavailable"
          />
        ) : (
          <MetricTile
            label="Total Tokens"
            value={formatTokens(tok!.totalTokens)}
            sub={tok!.byModelFamily.length > 0 ? tok!.byModelFamily.map((e) => e.modelFamily).join(', ') : 'all models'}
            accent="var(--plan)"
            data-testid="token-telemetry"
          />
        )}
      </div>
    </div>
  );
}

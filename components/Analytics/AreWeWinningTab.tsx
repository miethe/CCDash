/**
 * Are-We-Winning dashboard tab content (are-we-winning-dashboard-v1, M3).
 *
 * Extends the existing Analytics chart stack — TrendChart.tsx (weekly
 * created/completed/reopened trendlines) and InteractiveChartCard.tsx (the
 * self-caught ratio pie) — rather than building a parallel one.
 *
 * Drill-through (OQ-4, ratified plan decision): opening the drill-through
 * modal is a `useState` write made ONLY inside an `onClick` handler
 * (`openTrendPointDrillThrough` below, wired to TrendChart's `onPointClick`).
 * It is never written from render or from a `useEffect`, and it never
 * touches `useSearchParams` — the two
 * previously-broken sibling surfaces (FeatureDetailShell, SessionInspector)
 * were both `searchParams`-write-on-render bugs; this surface avoids the
 * class of bug entirely by keeping the selection in local component state.
 *
 * Resilience-by-default: `reopened` and `selfCaughtRatio` are `null` until
 * the M2-part-B backend task lands (a separate, concurrent execution lane —
 * see the plan's routing_constraints). Both render an explicit "not
 * captured yet" panel, never a fabricated zero/empty chart. A disabled
 * feature flag or any other summary-fetch failure resolves to `summary ===
 * null` and renders the top-level "not available" panel — never a crash.
 */
import React, { useCallback, useState } from 'react';

import { TrendChart } from './TrendChart';
import { InteractiveChartCard, type InteractiveChartDatum } from './primitives/InteractiveChartCard';
import { Surface, AlertSurface } from '../ui/surface';
import { Button } from '../ui/button';
import { getChartSeriesColor } from '../../lib/chartTheme';
import {
  ratioToChartData,
  trendlineToChartPoints,
  formatRatioBucketPercent,
  SELF_CAUGHT_RATIO_BUCKET_LABELS,
  SELF_CAUGHT_RATIO_BUCKET_TONE,
} from '../../lib/areWeWinning';
import type { AreWeWinningChartPoint } from '../../lib/areWeWinning';
import {
  useAreWeWinningSummaryQuery,
  useAreWeWinningDrillThroughQuery,
} from '../../services/queries/areWeWinning';

const formatWeeklyCount = (value: number): string => Number(value || 0).toLocaleString();

// ── Drill-through modal ─────────────────────────────────────────────────────

interface DrillThroughTarget {
  eventType: string;
  isoYear: number;
  isoWeek: number;
  /** Display label — the trendline/bucket name the user clicked. */
  label: string;
}

const DrillThroughModal: React.FC<{
  target: DrillThroughTarget;
  onClose: () => void;
}> = ({ target, onClose }) => {
  const [cursor, setCursor] = useState<string | null>(null);
  const { data, isLoading } = useAreWeWinningDrillThroughQuery({
    eventType: target.eventType,
    isoYear: target.isoYear,
    isoWeek: target.isoWeek,
    cursor,
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Drill-through: ${target.label}`}
      onClick={onClose}
    >
      <div
        className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-panel-border bg-panel p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold text-panel-foreground">{target.label}</h3>
            <p className="text-xs text-muted-foreground">
              ISO week {target.isoWeek}, {target.isoYear}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>

        {isLoading && !data ? (
          <p className="text-sm text-muted-foreground">Loading node rows...</p>
        ) : !data || data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No underlying node rows found for this bucket.</p>
        ) : (
          <>
            <p className="mb-3 text-xs text-muted-foreground">{data.total} row(s) total</p>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-panel-border text-muted-foreground">
                  <th className="py-2 pr-3 text-left">Title</th>
                  <th className="py-2 pr-3 text-left">Node ID</th>
                  <th className="py-2 text-left">Occurred At</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row, idx) => (
                  <tr key={`${row.nodeId ?? 'row'}-${idx}`} className="border-b border-panel-border/80">
                    <td className="py-2 pr-3">{row.title ?? '—'}</td>
                    <td className="py-2 pr-3 font-mono text-xs text-muted-foreground">{row.nodeId ?? '—'}</td>
                    <td className="py-2 font-mono text-xs">{row.occurredAt}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.nextCursor ? (
              <div className="mt-3 flex justify-center">
                <Button variant="outline" size="sm" onClick={() => setCursor(data.nextCursor)}>
                  Load more
                </Button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
};

// ── Self-caught ratio widget ────────────────────────────────────────────────

const SelfCaughtRatioWidget: React.FC<{
  ratio: ReturnType<typeof ratioToChartData>;
  total: number;
}> = ({ ratio, total }) => {
  const chartData: InteractiveChartDatum[] = ratio.map((entry) => ({
    key: entry.key,
    label: entry.label,
    value: entry.value,
    colorHint: getChartSeriesColor(SELF_CAUGHT_RATIO_BUCKET_TONE[entry.bucket]),
  }));

  return (
    <Surface tone="panel" padding="lg">
      <h3 className="mb-1 text-lg font-semibold text-panel-foreground">Self-Caught Ratio</h3>
      <p className="mb-4 text-xs text-muted-foreground">
        Whether a regression was caught by the same actor who introduced it. `Unknown` is expected
        to dominate today — most nodes carry no attribution discriminator — and is never folded
        into the other buckets.
      </p>

      <InteractiveChartCard
        title="Self-Caught Ratio"
        paramPrefix="selfCaughtRatio"
        resolveData={() => chartData}
        chartTypes={[{ id: 'pie', label: 'Pie' }]}
        defaultChartTypeId="pie"
        heightClassName="h-56"
        emptyMessage="No self-caught ratio data captured yet."
        valueFormatter={formatWeeklyCount}
        seriesLabel="Nodes"
        className="border-none p-0"
      />

      <ul className="mt-4 space-y-2" data-testid="self-caught-ratio-legend">
        {ratio.map((entry) => (
          <li
            key={entry.key}
            className="flex w-full items-center justify-between gap-3 rounded-lg border border-panel-border px-3 py-2 text-sm"
            data-testid={`self-caught-ratio-bucket-${entry.bucket}`}
            data-bucket={entry.bucket}
          >
            <span className="flex items-center gap-2">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: getChartSeriesColor(SELF_CAUGHT_RATIO_BUCKET_TONE[entry.bucket]) }}
              />
              <span className={entry.bucket === 'unknown' ? 'font-semibold text-panel-foreground' : 'text-panel-foreground'}>
                {SELF_CAUGHT_RATIO_BUCKET_LABELS[entry.bucket]}
              </span>
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              {formatWeeklyCount(entry.countValue)} ({formatRatioBucketPercent(entry.countValue, total)})
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-muted-foreground">
        Per-bucket drill-through is not yet wired up in this UI. The backend
        already exposes a per-bucket drill-through endpoint
        (<code>get_self_caught_drill_through</code>); this tab does not call
        it yet. Tracked separately (node_01M01R99RTVZFGJT1708VT057M).
      </p>
    </Surface>
  );
};

// ── Tab root ─────────────────────────────────────────────────────────────────

export const AreWeWinningTab: React.FC = () => {
  const { data: summary, isLoading } = useAreWeWinningSummaryQuery();
  const [drillTarget, setDrillTarget] = useState<DrillThroughTarget | null>(null);

  // Only ever invoked from a click handler passed down as a prop (TrendChart's
  // onPointClick, or a ratio-bucket <button onClick>) — never from render/effect.
  const openTrendPointDrillThrough = useCallback(
    (label: string) => (point: AreWeWinningChartPoint) => {
      setDrillTarget({
        eventType: point.meta.eventType,
        isoYear: point.meta.isoYear,
        isoWeek: point.meta.isoWeek,
        label: `${label} — week of ${point.date}`,
      });
    },
    [],
  );

  const closeDrillThrough = useCallback(() => setDrillTarget(null), []);

  if (isLoading) {
    return (
      <Surface tone="overlay" padding="lg" className="flex h-64 items-center justify-center text-muted-foreground">
        Loading are-we-winning dashboard...
      </Surface>
    );
  }

  if (!summary) {
    return (
      <AlertSurface intent="neutral">
        The are-we-winning dashboard is not available. It may be disabled
        (<code>CCDASH_ARE_WE_WINNING_ENABLED</code>) or its backing data is
        not yet captured for this deployment. This is an expected contract
        state, not an error.
      </AlertSurface>
    );
  }

  const createdPoints = trendlineToChartPoints(summary.created);
  const completedPoints = trendlineToChartPoints(summary.completed);
  const reopenedPoints = summary.reopened ? trendlineToChartPoints(summary.reopened) : null;
  const ratioChartData = summary.selfCaughtRatio ? ratioToChartData(summary.selfCaughtRatio) : null;

  return (
    <div className="space-y-6" data-testid="are-we-winning-tab">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TrendChart
          title="Nodes Created"
          color={getChartSeriesColor('info')}
          valueFormatter={formatWeeklyCount}
          points={createdPoints}
          onPointClick={openTrendPointDrillThrough('Nodes Created')}
          emptyMessage="No created-node events captured yet."
        />
        <TrendChart
          title="Nodes Completed"
          color={getChartSeriesColor('success')}
          valueFormatter={formatWeeklyCount}
          points={completedPoints}
          onPointClick={openTrendPointDrillThrough('Nodes Completed')}
          emptyMessage="No completed-node events captured yet."
        />
      </div>

      {/* `reopened` is explicitly Optional on the backend contract (M2 part
          B, not yet implemented) — absent renders "not captured yet", never
          a fabricated empty/zero trendline. */}
      {reopenedPoints !== null ? (
        <TrendChart
          title="Nodes Reopened"
          color={getChartSeriesColor('warning')}
          valueFormatter={formatWeeklyCount}
          points={reopenedPoints}
          onPointClick={openTrendPointDrillThrough('Nodes Reopened')}
          emptyMessage="No reopened-node events captured yet."
        />
      ) : (
        <Surface tone="overlay" padding="lg" data-testid="reopened-not-captured">
          <h3 className="mb-2 text-lg font-semibold text-panel-foreground">Nodes Reopened</h3>
          <p className="text-sm text-muted-foreground">
            Not captured yet — reopened-derivation is a separate, in-progress backend task.
          </p>
        </Surface>
      )}

      {/* `selfCaughtRatio` is explicitly Optional on the backend contract
          (M2 part B) — absent renders "not captured yet", never a
          fabricated ratio. */}
      {ratioChartData !== null ? (
        <SelfCaughtRatioWidget
          ratio={ratioChartData}
          total={summary.selfCaughtRatio!.total}
        />
      ) : (
        <Surface tone="overlay" padding="lg" data-testid="self-caught-ratio-not-captured">
          <h3 className="mb-2 text-lg font-semibold text-panel-foreground">Self-Caught Ratio</h3>
          <p className="text-sm text-muted-foreground">
            Not captured yet — self-caught bucketing is a separate, in-progress backend task.
          </p>
        </Surface>
      )}

      {drillTarget ? <DrillThroughModal target={drillTarget} onClose={closeDrillThrough} /> : null}
    </div>
  );
};

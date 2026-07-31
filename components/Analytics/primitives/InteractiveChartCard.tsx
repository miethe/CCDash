/**
 * InteractiveChartCard — reusable, generic chart card that lets a caller
 * independently switch dimension / metric / chart-type without owning any
 * data-fetching (T-004, analytics-provider-views quick feature).
 *
 * This establishes the interactive-chart pattern the app will later adopt
 * broadly (see PRD deferred item #1, "app-wide interactive chart system").
 * The API is intentionally generic — nothing here is provider-specific.
 *
 * - Every axis (dimension/metric/chartType) is optional; pass only what a
 *   given view needs. When an axis is omitted, no switcher renders for it
 *   and `resolveData` receives `undefined` for that argument.
 * - Selection is OPT-IN URL-persisted (`persistToUrl`, default false) under `paramPrefix`,
 *   mirroring the `activeTab` pattern in
 *   `components/Analytics/AnalyticsDashboard.tsx` (L119-207): params are
 *   omitted at their default value so a default view never pollutes the URL.
 * - Chart rendering strictly follows `lib/chartTheme.ts` (grid/axis/tooltip
 *   spreads, `radius={[4,4,0,0]}` bars, `ResponsiveContainer` inside a
 *   fixed-height div) — see the `models_tools` tab's `modelTokenChart`
 *   BarChart (AnalyticsDashboard.tsx L1032-1057) as the idiom this
 *   generalizes.
 * - An all-zero (or empty) series renders an explicit empty state, never a
 *   blank chart — Codex/OpenAI sessions legitimately report 0 tokens
 *   end-to-end, and that must read as "no data", not a rendering bug.
 *
 * recharts 3.x animation caveat (found via browser smoke, 2026-07-31): `<Pie>`'s
 * entrance animation renders ZERO `<path class="recharts-sector">` elements for
 * ~500-600ms after every mount — unlike `<Bar>`, whose rectangles exist in the
 * DOM from the first frame and merely interpolate height/width. Confirmed via a
 * real-Chromium (puppeteer) harness: `sectorCount` was 0 at t+400ms and only
 * appeared at t+~550ms; setting `isAnimationActive={false}` on `<Pie>` makes
 * sectors appear synchronously with the click. `isAnimationActive={false}` is
 * also set on `<Bar>` defensively — this card's whole purpose is rapid
 * dimension/metric/chart-type switching, and any animation left running risks
 * being interrupted mid-flight by the next switch (or by an unrelated parent
 * re-render, e.g. live polling in a real page) and getting stuck in a
 * transitional, visually-broken state instead of settling. Switching between
 * chart types is instant everywhere now, matching the `bar` reference path.
 * The remount `key={chartTypeId}` lives on the WRAPPER DIV, never on
 * `ResponsiveContainer`. Keying ResponsiveContainer itself remounts its
 * ResizeObserver mid-commit and drives recharts' internal layout store into an
 * infinite setState loop that blanks the page (reproduced in-browser on the
 * horizontalBar path, 2026-07-31). Keying the wrapper still guarantees a clean
 * unmount/remount across a chart-type swap without touching the observer.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { CHART_SERIES_COLORS, chartTheme, getChartSeriesColor } from '../../../lib/chartTheme';
import { cn } from '../../../lib/utils';
import { SegmentedControl, type SegmentedControlOption } from './SegmentedControl';

export type ChartTypeId = 'bar' | 'horizontalBar' | 'pie';

export interface ChartAxisOption {
  id: string;
  label: string;
  icon?: SegmentedControlOption['icon'];
  disabled?: boolean;
}

export interface ChartTypeOption {
  id: ChartTypeId;
  label: string;
  icon?: SegmentedControlOption['icon'];
  disabled?: boolean;
}

export interface InteractiveChartDatum {
  key: string;
  label: string;
  value: number;
  /** Explicit color override (e.g. `useModelColors().getColorForModel(...)`); falls back to a cycled chart-theme tone when absent. */
  colorHint?: string;
}

export interface InteractiveChartCardProps {
  title: string;
  /** URL search-param namespace for this card's selection state, e.g. "providerUsage". */
  paramPrefix: string;
  dimensions?: ChartAxisOption[];
  defaultDimensionId?: string;
  metrics?: ChartAxisOption[];
  defaultMetricId?: string;
  chartTypes?: ChartTypeOption[];
  defaultChartTypeId?: ChartTypeId;
  /** Card never fetches — caller supplies data for the current (dimension, metric) selection. */
  resolveData: (dimensionId: string | undefined, metricId: string | undefined) => InteractiveChartDatum[];
  /** Tailwind height class for the chart viewport. Defaults to `h-72`. */
  heightClassName?: string;
  emptyMessage?: string;
  valueFormatter?: (value: number) => string;
  /** Series name shown in the tooltip. Defaults to "Value". */
  seriesLabel?: string;
  subtitle?: string;
  className?: string;
  /**
   * Persist dimension/metric/chart-type selection to the URL via
   * `useSearchParams`.
   *
   * OPT-IN, and deliberately defaults to `false`. Only enable it on a route
   * you have verified in a browser.
   *
   * Writing search params from this card re-renders any ancestor that derives
   * its own state from `searchParams` on every render without buffering it in
   * local state. Two such routes exist today — `FeatureDetailShell.tsx`
   * (`activeTab` recomputed from `searchParams.get('tab')` each render) and
   * `SessionInspector.tsx` — and on both, that extra render cascade drives
   * recharts' internal layout-store effect into an unrecoverable setState loop
   * ("Maximum update depth exceeded" whose stack originates *inside* recharts,
   * at `commitHookEffectListMount`), blanking the entire page. Both were
   * reproduced and re-verified by toggling this flag.
   *
   * `AnalyticsDashboard.tsx` is safe because it mirrors its tab into `useState`
   * and only re-syncs from the URL through a guarded effect, so it opts in.
   *
   * When `false`, selection still initializes from the URL once (a shared link
   * still opens on the right view) but never reads or writes it again — state
   * lives purely in local `useState` for the rest of the card's lifetime.
   */
  persistToUrl?: boolean;
}

const CYCLE_TONES: Array<keyof typeof CHART_SERIES_COLORS> = [
  'primary',
  'secondary',
  'tertiary',
  'quaternary',
  'quinary',
  'success',
  'warning',
  'danger',
  'info',
];

const defaultValueFormatter = (value: number): string => Number(value || 0).toLocaleString();

function firstId(options: ChartAxisOption[] | undefined): string | undefined {
  return options && options.length > 0 ? options[0].id : undefined;
}

export const InteractiveChartCard: React.FC<InteractiveChartCardProps> = ({
  title,
  paramPrefix,
  dimensions,
  defaultDimensionId,
  metrics,
  defaultMetricId,
  chartTypes,
  defaultChartTypeId,
  resolveData,
  heightClassName = 'h-72',
  emptyMessage = 'No data available for this view.',
  valueFormatter = defaultValueFormatter,
  seriesLabel = 'Value',
  subtitle,
  className,
  persistToUrl = false,
}) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const searchParamsString = searchParams.toString();

  const dimKey = `${paramPrefix}Dim`;
  const metricKey = `${paramPrefix}Metric`;
  const chartKey = `${paramPrefix}Chart`;

  const resolvedDefaultDimensionId = defaultDimensionId ?? firstId(dimensions);
  const resolvedDefaultMetricId = defaultMetricId ?? firstId(metrics);
  const effectiveDefaultChartTypeId: ChartTypeId =
    defaultChartTypeId ?? (chartTypes && chartTypes.length > 0 ? chartTypes[0].id : 'bar');

  const [dimensionId, setDimensionId] = useState<string | undefined>(() => {
    if (!dimensions || dimensions.length === 0) return undefined;
    const fromUrl = searchParams.get(dimKey);
    return fromUrl && dimensions.some((d) => d.id === fromUrl) ? fromUrl : resolvedDefaultDimensionId;
  });
  const [metricId, setMetricId] = useState<string | undefined>(() => {
    if (!metrics || metrics.length === 0) return undefined;
    const fromUrl = searchParams.get(metricKey);
    return fromUrl && metrics.some((m) => m.id === fromUrl) ? fromUrl : resolvedDefaultMetricId;
  });
  const [chartTypeId, setChartTypeId] = useState<ChartTypeId>(() => {
    if (!chartTypes || chartTypes.length === 0) return effectiveDefaultChartTypeId;
    const fromUrl = searchParams.get(chartKey) as ChartTypeId | null;
    return fromUrl && chartTypes.some((c) => c.id === fromUrl) ? fromUrl : effectiveDefaultChartTypeId;
  });

  // Sync FROM the URL (external nav, e.g. back/forward or a shared link).
  // Skipped entirely when `persistToUrl` is false — see the prop doc for why.
  useEffect(() => {
    if (!persistToUrl) return;
    if (dimensions && dimensions.length > 0) {
      const fromUrl = searchParams.get(dimKey);
      if (fromUrl && dimensions.some((d) => d.id === fromUrl) && fromUrl !== dimensionId) {
        setDimensionId(fromUrl);
      }
    }
    if (metrics && metrics.length > 0) {
      const fromUrl = searchParams.get(metricKey);
      if (fromUrl && metrics.some((m) => m.id === fromUrl) && fromUrl !== metricId) {
        setMetricId(fromUrl);
      }
    }
    if (chartTypes && chartTypes.length > 0) {
      const fromUrl = searchParams.get(chartKey) as ChartTypeId | null;
      if (fromUrl && chartTypes.some((c) => c.id === fromUrl) && fromUrl !== chartTypeId) {
        setChartTypeId(fromUrl);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persistToUrl, searchParams, dimKey, metricKey, chartKey]);

  // Sync TO the URL — omit params that sit at their default value. Skipped
  // entirely when `persistToUrl` is false — see the prop doc for why.
  useEffect(() => {
    if (!persistToUrl) return;
    const next = new URLSearchParams(searchParamsString);
    let changed = false;
    const apply = (key: string, current: string | undefined, def: string | undefined) => {
      if (!current || current === def) {
        if (next.has(key)) {
          next.delete(key);
          changed = true;
        }
        return;
      }
      if (next.get(key) !== current) {
        next.set(key, current);
        changed = true;
      }
    };
    apply(dimKey, dimensionId, resolvedDefaultDimensionId);
    apply(metricKey, metricId, resolvedDefaultMetricId);
    apply(chartKey, chartTypeId, effectiveDefaultChartTypeId);
    if (changed) {
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persistToUrl, dimensionId, metricId, chartTypeId, searchParamsString]);

  const series = useMemo(
    () => resolveData(dimensionId, metricId),
    [resolveData, dimensionId, metricId],
  );
  const hasData = series.length > 0 && series.some((entry) => Number(entry.value) > 0);

  const colorFor = (entry: InteractiveChartDatum, index: number): string =>
    entry.colorHint ?? getChartSeriesColor(CYCLE_TONES[index % CYCLE_TONES.length]);

  const tooltipFormatter = (value: number) => [valueFormatter(value), seriesLabel] as [string, string];

  return (
    <div className={cn('bg-panel border border-panel-border rounded-xl p-5', className)}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-panel-foreground font-semibold">{title}</h3>
          {subtitle ? <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p> : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {dimensions && dimensions.length > 0 && dimensionId !== undefined ? (
            <SegmentedControl
              options={dimensions}
              value={dimensionId}
              onChange={setDimensionId}
              size="sm"
              ariaLabel={`${title} — dimension`}
            />
          ) : null}
          {metrics && metrics.length > 0 && metricId !== undefined ? (
            <SegmentedControl
              options={metrics}
              value={metricId}
              onChange={setMetricId}
              size="sm"
              ariaLabel={`${title} — metric`}
            />
          ) : null}
          {chartTypes && chartTypes.length > 0 ? (
            <SegmentedControl
              options={chartTypes}
              value={chartTypeId}
              onChange={(id) => setChartTypeId(id as ChartTypeId)}
              size="sm"
              ariaLabel={`${title} — chart type`}
            />
          ) : null}
        </div>
      </div>

      {!hasData ? (
        <div
          className={cn(
            'interactive-chart-empty-state flex items-center justify-center text-sm text-muted-foreground border border-dashed border-panel-border rounded-lg',
            heightClassName,
          )}
        >
          {emptyMessage}
        </div>
      ) : (
        // NOTE: the remount key lives on the wrapper, NOT on ResponsiveContainer.
        // Keying ResponsiveContainer itself remounts its ResizeObserver mid-commit,
        // which drives recharts' internal layout store into an infinite setState loop
        // (blank page + "Maximum update depth exceeded" originating inside recharts).
        <div key={chartTypeId} className={cn('w-full', heightClassName)}>
          <ResponsiveContainer width="100%" height="100%">
            {chartTypeId === 'pie' ? (
              <PieChart>
                <Tooltip
                  contentStyle={chartTheme.tooltip.contentStyle}
                  itemStyle={chartTheme.tooltip.itemStyle}
                  labelStyle={chartTheme.tooltip.labelStyle}
                  cursor={chartTheme.tooltip.cursor}
                  formatter={tooltipFormatter}
                />
                <Pie data={series} dataKey="value" nameKey="label" cx="50%" cy="50%" outerRadius={100} isAnimationActive={false} label>
                  {series.map((entry, index) => (
                    <Cell key={entry.key} fill={colorFor(entry, index)} />
                  ))}
                </Pie>
              </PieChart>
            ) : (
              <BarChart data={series} layout={chartTypeId === 'horizontalBar' ? 'vertical' : 'horizontal'}>
                <CartesianGrid {...chartTheme.grid} vertical={chartTypeId === 'horizontalBar'} horizontal={chartTypeId !== 'horizontalBar'} />
                {chartTypeId === 'horizontalBar' ? (
                  <>
                    <XAxis type="number" {...chartTheme.axis} tick={{ ...chartTheme.axis.tick, fontSize: 11 }} tickFormatter={valueFormatter} />
                    <YAxis type="category" dataKey="label" {...chartTheme.axis} tick={{ ...chartTheme.axis.tick, fontSize: 11 }} width={110} />
                  </>
                ) : (
                  <>
                    <XAxis dataKey="label" {...chartTheme.axis} tick={{ ...chartTheme.axis.tick, fontSize: 11 }} />
                    <YAxis {...chartTheme.axis} tick={{ ...chartTheme.axis.tick, fontSize: 11 }} tickFormatter={valueFormatter} />
                  </>
                )}
                <Tooltip
                  contentStyle={chartTheme.tooltip.contentStyle}
                  itemStyle={chartTheme.tooltip.itemStyle}
                  labelStyle={chartTheme.tooltip.labelStyle}
                  cursor={chartTheme.tooltip.cursor}
                  formatter={tooltipFormatter}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                  {series.map((entry, index) => (
                    <Cell key={entry.key} fill={colorFor(entry, index)} />
                  ))}
                </Bar>
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
};

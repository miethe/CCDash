import React, { useState, useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { useData } from '../contexts/DataContext';
import { useDashboardBundleQuery, useDashboardChartQuery, useLiveAgentsCountQuery } from '../services/queries/dashboard';
import { useAnalyticsOverviewQuery } from '../services/queries/analytics';
import { TrendingUp, AlertTriangle, Zap, DollarSign, Cpu, LayoutGrid, ShieldAlert, CheckCircle2, Clock, Activity } from 'lucide-react';
import { generateDashboardInsight } from '../services/geminiService';
import { chartTheme, getChartGradientStops, getChartSeriesColor } from '../lib/chartTheme';
import { formatPercent, formatTokenCount, resolveTokenMetrics } from '../lib/tokenMetrics';
import { Button } from './ui/button';
import { Surface, AlertSurface } from './ui/surface';
import { cn } from '../lib/utils';
import { useFeatureSurface } from '../services/useFeatureSurface';
import { SystemMetricsChip } from './SystemMetricsChip';
import { IngestHealthBadge } from './IngestHealthBadge';

const STAT_TONE_STYLES: Record<string, string> = {
  primary: 'border-primary-border bg-primary/10 text-primary-foreground',
  info: 'border-info-border bg-info/10 text-info-foreground',
  success: 'border-success-border bg-success/10 text-success-foreground',
  warning: 'border-warning-border bg-warning/10 text-warning-foreground',
  danger: 'border-danger-border bg-danger/10 text-danger-foreground',
};

const StatCard = ({ label, value, sub, icon: Icon, tone }: any) => (
  <Surface tone="panel" padding="lg" className="h-full">
    <div className="flex justify-between items-start mb-4">
      <div>
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
        <h3 className="mt-1 text-2xl font-bold text-panel-foreground">{value}</h3>
      </div>
      <div className={cn('rounded-lg border p-2', STAT_TONE_STYLES[tone])}>
        <Icon size={20} />
      </div>
    </div>
    <p className="text-xs text-muted-foreground">{sub}</p>
  </Surface>
);

// ── Live agents count chip ────────────────────────────────────────────────────

interface LiveAgentsChipProps {
  /** Integer count, or null when data is unavailable. */
  count: number | null;
}

/**
 * Displays the number of currently active agent sessions.
 *
 * Resilience contract (R-P2): renders "--" when count is null, an error occurred,
 * or the API field is absent. Never shows "0" for unavailable data — 0 means
 * genuinely no active sessions.
 */
const LiveAgentsChip: React.FC<LiveAgentsChipProps> = ({ count }) => {
  const isAvailable = count !== null;
  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-lg border px-3 py-2 text-sm',
        isAvailable && count > 0
          ? 'border-success-border bg-success/10 text-success-foreground'
          : 'border-primary-border bg-primary/10 text-primary-foreground',
      )}
      title="Active agent sessions in the last 10 minutes"
    >
      <Activity size={14} className="shrink-0" />
      <span className="font-semibold tabular-nums">
        {isAvailable ? count.toLocaleString() : '--'}
      </span>
      <span className="text-xs">live agents</span>
    </div>
  );
};
// useLiveAgentsCount (setInterval) replaced by useLiveAgentsCountQuery (TQ refetchInterval).
// T4-006-1: no manual setInterval remains in this file.

// ── Feature surface summary chip ──────────────────────────────────────────────

const FeatureSummaryChip = ({
  icon: Icon,
  label,
  count,
  tone,
}: {
  icon: React.ElementType;
  label: string;
  count: number;
  tone: string;
}) => (
  <div className={cn('flex items-center gap-2 rounded-lg border px-3 py-2 text-sm', STAT_TONE_STYLES[tone])}>
    <Icon size={14} className="shrink-0" />
    <span className="font-semibold tabular-nums">{count.toLocaleString()}</span>
    <span className="text-xs">{label}</span>
  </div>
);

export const Dashboard: React.FC = () => {
  const { activeProject, tasks, runtimeStatus } = useData();

  // T5-005 / T5-006: Replace separate useSessionsQuery + useTasksQuery with
  // a single fat-read bundle.  Cold Dashboard load now issues ONE GET /api/v1/dashboard.
  // AC-R-P2 resilience: sessions ?? [] and taskCounts ?? {} are applied in the hook.
  const {
    sessions: bundleSessions,
    taskCounts,
  } = useDashboardBundleQuery({ projectId: activeProject?.id });

  // T5-007: KPI cards migrated to TanStack Query — decouples slow overview
  // endpoint from the chart series calls; provides loading/error affordances.
  const {
    data: overviewData,
    isLoading: overviewLoading,
    isError: overviewError,
  } = useAnalyticsOverviewQuery({ projectId: activeProject?.id });

  // Adapt SessionCardDTO (snake_case) to the shape used by analyticsData below.
  const sessions = bundleSessions.map(s => ({
    startedAt: s.started_at ?? undefined,
    totalCost: s.total_cost ?? 0,
    qualityRating: undefined as number | undefined,
  }));

  // T4-011 / T4-006-1: Live agents count via TQ refetchInterval (replaces setInterval).
  // Returns null before first fetch or on error — R-P2 resilience contract.
  const liveAgentsCount = useLiveAgentsCountQuery();

  // Feature surface — one bounded page fetch + one rollup batch.
  // pageSize:1 is sufficient to get totals; rollup fields give cost+session
  // aggregates across all features.  No per-feature /api/features/{id}/...
  // calls are made; the bounded cache guards against duplicate requests.
  const {
    cards: surfaceCards,
    rollups: surfaceRollups,
    totals: surfaceTotals,
    listState: surfaceListState,
  } = useFeatureSurface({
    initialQuery: { pageSize: 50, sortBy: 'updated_at', sortDirection: 'desc' },
    rollupFields: ['session_counts', 'token_cost_totals', 'latest_activity'],
  });

  // Derive per-status counts from the surface card list (client-side, no extra
  // fetch).  Falls back to zeros while list is loading.
  const featureCounts = useMemo(() => {
    const counts = { active: 0, blocked: 0, completed: 0, total: surfaceTotals.total };
    for (const card of surfaceCards) {
      const s = card.effectiveStatus ?? card.status;
      if (s === 'completed' || s === 'done') counts.completed += 1;
      else if (card.qualitySignals?.hasBlockingSignals || card.dependencyState?.state === 'blocked' || card.dependencyState?.state === 'blocked_unknown') counts.blocked += 1;
      else counts.active += 1;
    }
    return counts;
  }, [surfaceCards, surfaceTotals.total]);

  // Total cost across all loaded feature rollups (no per-feature call).
  const surfaceTotalCost = useMemo(() => {
    let cost = 0;
    for (const rollup of surfaceRollups.values()) {
      cost += rollup.displayCost ?? rollup.totalCost ?? 0;
    }
    return cost;
  }, [surfaceRollups]);

  // Phase 5 (T5-008): detection coverage summary derived from the session bundle.
  // Resilience: fields the bundle omits simply don't count — a session with no
  // context_window / skill_name is "not detected", never an error or "null" text.
  const detectionCoverage = useMemo(() => {
    let contextDetected = 0;
    const skills = new Set<string>();
    for (const s of bundleSessions) {
      if ((s.context_window ?? '').toString().trim()) contextDetected += 1;
      const skill = (s.skill_name ?? '').toString().trim();
      if (skill) skills.add(skill);
    }
    return { contextDetected, skillCount: skills.size };
  }, [bundleSessions]);

  const [insight, setInsight] = useState<string | null>(null);
  const [loadingInsight, setLoadingInsight] = useState(false);

  // T4-011: Chart series + calibration via TQ (replaces useEffect + local state).
  // isLoading is available but not rendered (chart shows empty gracefully while loading).
  const { chartData, costCalibration } = useDashboardChartQuery({ projectId: activeProject?.id });

  // Derive analytics from real session data
  const analyticsData = useMemo(() => {
    return sessions.map(s => ({
      date: s.startedAt?.split('T')[0] || 'Unknown',
      cost: s.totalCost,
      featuresShipped: tasks.filter(t => t.status === 'done' || t.status === 'deferred').length,
      avgQuality: s.qualityRating || 4,
    }));
  }, [sessions, tasks]);

  const handleGenerateInsight = async () => {
    setLoadingInsight(true);
    const insightMetrics = (chartData.length > 0 ? chartData : analyticsData).map((point: { date: string; cost: number }) => ({
      name: point.date,
      value: Number(point.cost || 0),
      unit: '$',
    }));
    const result = await generateDashboardInsight(insightMetrics, tasks);
    setInsight(result);
    setLoadingInsight(false);
  };

  const workloadMetrics = useMemo(
    () => resolveTokenMetrics({
      modelIOTokens: overviewData?.kpis?.modelIOTokens,
      cacheInputTokens: overviewData?.kpis?.cacheInputTokens,
      observedTokens: overviewData?.kpis?.observedTokens,
      toolReportedTokens: overviewData?.kpis?.toolReportedTokens,
    }),
    [overviewData],
  );

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold text-panel-foreground">Analytics Overview</h2>
          <p className="mt-2 text-muted-foreground">Performance metrics across all active agents and sessions.</p>
        </div>
        <Button
          onClick={handleGenerateInsight}
          disabled={loadingInsight}
          size="sm"
        >
          {loadingInsight ? (
            <span className="animate-pulse">Analyzing...</span>
          ) : (
            <>
              <Cpu size={16} />
              AI Insight
            </>
          )}
        </Button>
      </div>

      {insight && (
        <AlertSurface intent="info" className="flex items-start gap-3">
          <div className="mt-1"><Zap size={16} className="text-info" /></div>
          <div>{insight}</div>
        </AlertSurface>
      )}

      {/* Feature Surface Summary — sourced from useFeatureSurface (unified payload, no per-feature calls) */}
      <Surface tone="panel" padding="lg">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <div>
            <p className="text-sm font-medium text-muted-foreground">Feature Portfolio</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {surfaceListState === 'loading'
                ? 'Loading...'
                : `${surfaceTotals.total.toLocaleString()} features tracked`}
            </p>
          </div>
          {surfaceRollups.size > 0 && (
            <span className="text-xs text-muted-foreground">
              Surface cost: <span className="font-semibold text-panel-foreground">${surfaceTotalCost.toFixed(2)}</span>
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <FeatureSummaryChip icon={LayoutGrid} label="total" count={surfaceTotals.total} tone="info" />
          <FeatureSummaryChip icon={Clock} label="active" count={featureCounts.active} tone="primary" />
          <FeatureSummaryChip icon={ShieldAlert} label="blocked" count={featureCounts.blocked} tone="danger" />
          <FeatureSummaryChip icon={CheckCircle2} label="completed" count={featureCounts.completed} tone="success" />
          {/* live-agents-count-v1: live active-agents chip; polls /api/agent/live/active-count every 10 s */}
          <LiveAgentsChip count={liveAgentsCount} />
        </div>
      </Surface>

      {/* System-wide live agent count — polls /api/agent/system/active-count every 30 s.
          Placed between Feature Portfolio and KPI cards per OQ-EXP-1. */}
      <SystemMetricsChip />

      {/* Phase 6: ingest/daemon health rollup — sourced from the existing 30 s health
          poll (AppRuntimeContext → useHealthQuery). No new fetch. Absent on pre-v36
          backends → renders neutral "Local only" state, never an error. */}
      <IngestHealthBadge ingestSources={runtimeStatus?.ingestSources} />

      {/* KPI Cards — TQ-managed (T5-007). Shows loading placeholders while fetching,
          error affordance on failure, never renders literal 0 for unavailable data. */}
      {overviewError && !overviewData && (
        <AlertSurface intent="danger" className="text-sm">
          Analytics KPIs could not be loaded. The chart and calibration data below may still be available.
        </AlertSurface>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">
        <StatCard
          label="Observed Workload (30d)"
          value={!overviewData ? '—' : formatTokenCount(workloadMetrics.workloadTokens)}
          sub={!overviewData ? 'Loading...' : `${formatTokenCount(workloadMetrics.cacheInputTokens)} cache input (${formatPercent(workloadMetrics.cacheShare)})`}
          icon={Cpu}
          tone="info"
        />
        <StatCard
          label="Total Spend (30d)"
          value={!overviewData ? '—' : `$${Number(overviewData?.kpis?.sessionCost || 0).toFixed(2)}`}
          sub={!overviewData ? 'Loading...' : `${costCalibration?.comparableSessionCount || 0} comparable sessions • ${formatTokenCount(workloadMetrics.modelIOTokens)} model IO`}
          icon={DollarSign}
          tone="success"
        />
        <StatCard
          label="Avg. Session Quality"
          value={!overviewData ? '—' : `${Number(overviewData?.kpis?.taskCompletionPct || 0).toFixed(1)}%`}
          sub="Task completion across done/deferred/completed"
          icon={TrendingUp}
          tone="primary"
        />
        <StatCard
          label="Tool Success Rate"
          value={!overviewData ? '—' : `${Number(overviewData?.kpis?.toolSuccessRate || 0).toFixed(1)}%`}
          sub={!overviewData ? 'Loading...' : `${Number(overviewData?.kpis?.toolCallCount || 0).toLocaleString()} tool calls tracked`}
          icon={AlertTriangle}
          tone="danger"
        />
        <StatCard
          label="Features Shipped"
          value={!overviewData ? '—' : `${Number(overviewData?.kpis?.taskVelocity || 0).toLocaleString()}`}
          sub={!overviewData ? 'Loading...' : `${Number(overviewData?.kpis?.sessionCount || 0).toLocaleString()} sessions • ${taskCounts['done'] ?? 0} done tasks`}
          icon={Zap}
          tone="warning"
        />
      </div>

      <AlertSurface intent="neutral" className="text-xs text-muted-foreground">
        Display spend prefers reported cost, then recalculated cost, then estimated fallback. Current-context snapshots were captured for {Number(overviewData?.kpis?.contextSessionCount || 0).toLocaleString()} recent sessions at an average {Number(overviewData?.kpis?.avgContextUtilizationPct || 0).toFixed(1)}% utilization.
      </AlertSurface>

      <AlertSurface intent="neutral" className="text-xs text-muted-foreground">
        Calibration coverage: {Number(costCalibration?.comparableSessionCount || 0).toLocaleString()} comparable sessions, average mismatch {(Number(costCalibration?.avgMismatchPct || 0) * 100).toFixed(1)}%, average cost confidence {(Number(costCalibration?.avgCostConfidence || 0) * 100).toFixed(0)}%.
      </AlertSurface>

      {/* Phase 5 detection coverage — only rendered when something was detected.
          Missing context_window / skill_name → this note is simply omitted (the
          explicit missing-field fallback for the Dashboard surface, R-P2). */}
      {(detectionCoverage.contextDetected > 0 || detectionCoverage.skillCount > 0) && (
        <AlertSurface intent="neutral" className="text-xs text-muted-foreground">
          Detection coverage:{' '}
          {detectionCoverage.contextDetected > 0
            ? `${detectionCoverage.contextDetected.toLocaleString()} session(s) with a detected context window`
            : 'no context-window sidecar matches'}
          {detectionCoverage.skillCount > 0
            ? ` • ${detectionCoverage.skillCount.toLocaleString()} distinct skill(s) attributed`
            : ''}
          .
        </AlertSurface>
      )}

      {/* Main Chart Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Surface tone="panel" padding="lg" className="lg:col-span-2">
          <h3 className="mb-6 text-lg font-semibold text-panel-foreground">Cost vs. Velocity</h3>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData.length > 0 ? chartData : analyticsData}>
                <defs>
                  <linearGradient id="colorCost" x1="0" y1="0" x2="0" y2="1">
                    {getChartGradientStops(getChartSeriesColor('primary')).map((stop) => (
                      <stop
                        key={`cost-${stop.offset}`}
                        offset={stop.offset}
                        stopColor={stop.stopColor}
                        stopOpacity={stop.stopOpacity}
                      />
                    ))}
                  </linearGradient>
                  <linearGradient id="colorQuality" x1="0" y1="0" x2="0" y2="1">
                    {getChartGradientStops(getChartSeriesColor('success')).map((stop) => (
                      <stop
                        key={`quality-${stop.offset}`}
                        offset={stop.offset}
                        stopColor={stop.stopColor}
                        stopOpacity={stop.stopOpacity}
                      />
                    ))}
                  </linearGradient>
                </defs>
                <CartesianGrid {...chartTheme.grid} vertical={false} />
                <XAxis
                  dataKey="date"
                  tickFormatter={(val) => val.slice(5)}
                  {...chartTheme.axis}
                />
                <YAxis
                  {...chartTheme.axis}
                  tickFormatter={(val) => `$${val}`}
                />
                <Tooltip
                  contentStyle={chartTheme.tooltip.contentStyle}
                  itemStyle={chartTheme.tooltip.itemStyle}
                  labelStyle={chartTheme.tooltip.labelStyle}
                  cursor={chartTheme.tooltip.cursor}
                />
                <Area type="monotone" dataKey="cost" stroke={getChartSeriesColor('primary')} fillOpacity={1} fill="url(#colorCost)" strokeWidth={2} name="Daily Cost" />
                <Area type="monotone" dataKey="velocity" stroke={getChartSeriesColor('success')} fillOpacity={1} fill="url(#colorQuality)" strokeWidth={2} name="Task Velocity" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Surface>

        <Surface tone="panel" padding="lg">
          <h3 className="mb-6 text-lg font-semibold text-panel-foreground">Top Agent Models</h3>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={(overviewData?.top_models ?? []).slice(0, 6)} layout="vertical">
                <CartesianGrid {...chartTheme.grid} horizontal vertical={false} />
                <XAxis type="number" hide />
                <YAxis dataKey="name" type="category" width={80} {...chartTheme.axis} />
                <Tooltip
                  cursor={{ fill: 'transparent' }}
                  contentStyle={chartTheme.tooltip.contentStyle}
                  itemStyle={chartTheme.tooltip.itemStyle}
                  labelStyle={chartTheme.tooltip.labelStyle}
                />
                <Bar dataKey="usage" fill={getChartSeriesColor('info')} radius={[0, 4, 4, 0]} barSize={20} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Surface>
      </div>
    </div>
  );
};

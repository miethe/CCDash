import React, { useState, useEffect, useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { useData } from '../contexts/DataContext';
import { TrendingUp, AlertTriangle, Zap, DollarSign, Cpu } from 'lucide-react';
import { generateDashboardInsight } from '../services/geminiService';
import { analyticsService } from '../services/analytics';
import { chartTheme, getChartGradientStops, getChartSeriesColor } from '../lib/chartTheme';
import { type AnalyticsOverview, type SessionCostCalibrationSummary } from '../types';
import { formatPercent, formatTokenCount, resolveTokenMetrics } from '../lib/tokenMetrics';
import { Button } from './ui/button';
import { Surface, AlertSurface } from './ui/surface';
import { cn } from '../lib/utils';

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

export const Dashboard: React.FC = () => {
  const { sessions, tasks, loading } = useData();
  const [insight, setInsight] = useState<string | null>(null);
  const [loadingInsight, setLoadingInsight] = useState(false);
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [costCalibration, setCostCalibration] = useState<SessionCostCalibrationSummary | null>(null);
  const [chartData, setChartData] = useState<Array<{ date: string; cost: number; velocity: number }>>([]);
  const [modelData, setModelData] = useState<Array<{ name: string; usage: number }>>([]);

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
    const insightMetrics = (chartData.length > 0 ? chartData : analyticsData).map(point => ({
      name: point.date,
      value: Number(point.cost || 0),
      unit: '$',
    }));
    const result = await generateDashboardInsight(insightMetrics, tasks);
    setInsight(result);
    setLoadingInsight(false);
  };

  useEffect(() => {
    let mounted = true;
    const loadAnalytics = async () => {
      try {
        const [ov, calibration, costSeries, velocitySeries] = await Promise.all([
          analyticsService.getOverview(),
          analyticsService.getSessionCostCalibration(),
          analyticsService.getSeries({ metric: 'session_cost', period: 'daily', limit: 120 }),
          analyticsService.getSeries({ metric: 'task_velocity', period: 'daily', limit: 120 }),
        ]);
        if (!mounted) return;
        setOverview(ov);
        setCostCalibration(calibration);
        setModelData((ov.topModels || []).slice(0, 6));

        const byDate = new Map<string, { date: string; cost: number; velocity: number }>();
        for (const point of costSeries.items || []) {
          const date = String(point.captured_at || '').slice(0, 10);
          if (!date) continue;
          const current = byDate.get(date) || { date, cost: 0, velocity: 0 };
          current.cost = Number(point.value || 0);
          byDate.set(date, current);
        }
        for (const point of velocitySeries.items || []) {
          const date = String(point.captured_at || '').slice(0, 10);
          if (!date) continue;
          const current = byDate.get(date) || { date, cost: 0, velocity: 0 };
          current.velocity = Number(point.value || 0);
          byDate.set(date, current);
        }
        setChartData(Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date)));
      } catch (err) {
        console.error('Failed to load analytics overview:', err);
      }
    };
    loadAnalytics();
    return () => {
      mounted = false;
    };
  }, [sessions.length, tasks.length]);

  const workloadMetrics = useMemo(
    () => resolveTokenMetrics({
      modelIOTokens: overview?.kpis?.modelIOTokens,
      cacheInputTokens: overview?.kpis?.cacheInputTokens,
      observedTokens: overview?.kpis?.observedTokens,
      toolReportedTokens: overview?.kpis?.toolReportedTokens,
    }),
    [overview],
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

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">
        <StatCard
          label="Observed Workload (30d)"
          value={formatTokenCount(workloadMetrics.workloadTokens)}
          sub={`${formatTokenCount(workloadMetrics.cacheInputTokens)} cache input (${formatPercent(workloadMetrics.cacheShare)})`}
          icon={Cpu}
          tone="info"
        />
        <StatCard
          label="Total Spend (30d)"
          value={`$${Number(overview?.kpis?.sessionCost || 0).toFixed(2)}`}
          sub={`${costCalibration?.comparableSessionCount || 0} comparable sessions • ${formatTokenCount(workloadMetrics.modelIOTokens)} model IO`}
          icon={DollarSign}
          tone="success"
        />
        <StatCard
          label="Avg. Session Quality"
          value={`${Number(overview?.kpis?.taskCompletionPct || 0).toFixed(1)}%`}
          sub="Task completion across done/deferred/completed"
          icon={TrendingUp}
          tone="primary"
        />
        <StatCard
          label="Tool Success Rate"
          value={`${Number(overview?.kpis?.toolSuccessRate || 0).toFixed(1)}%`}
          sub={`${Number(overview?.kpis?.toolCallCount || 0).toLocaleString()} tool calls tracked`}
          icon={AlertTriangle}
          tone="danger"
        />
        <StatCard
          label="Features Shipped"
          value={`${Number(overview?.kpis?.taskVelocity || 0).toLocaleString()}`}
          sub={`${Number(overview?.kpis?.sessionCount || 0).toLocaleString()} sessions in scope`}
          icon={Zap}
          tone="warning"
        />
      </div>

      <AlertSurface intent="neutral" className="text-xs text-muted-foreground">
        Display spend prefers reported cost, then recalculated cost, then estimated fallback. Current-context snapshots were captured for {Number(overview?.kpis?.contextSessionCount || 0).toLocaleString()} recent sessions at an average {Number(overview?.kpis?.avgContextUtilizationPct || 0).toFixed(1)}% utilization.
      </AlertSurface>

      <AlertSurface intent="neutral" className="text-xs text-muted-foreground">
        Calibration coverage: {Number(costCalibration?.comparableSessionCount || 0).toLocaleString()} comparable sessions, average mismatch {(Number(costCalibration?.avgMismatchPct || 0) * 100).toFixed(1)}%, average cost confidence {(Number(costCalibration?.avgCostConfidence || 0) * 100).toFixed(0)}%.
      </AlertSurface>

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
              <BarChart data={modelData} layout="vertical">
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

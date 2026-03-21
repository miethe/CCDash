import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { TrendChart } from './TrendChart';
import { analyticsService } from '../../services/analytics';
import { useModelColors } from '../../contexts/ModelColorsContext';
import { useData } from '../../contexts/DataContext';
import { isUsageAttributionEnabled, isWorkflowAnalyticsEnabled } from '../../services/agenticIntelligence';
import {
    AnalyticsArtifactsResponse,
    AnalyticsCorrelationItem,
    AnalyticsOverview,
    Notification,
    SessionCostCalibrationSummary,
    SessionUsageAggregateResponse,
    SessionUsageCalibrationSummary,
    SessionUsageDrilldownResponse,
} from '../../types';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
    BarChart3,
    Bell,
    Download,
    Layers3,
    Network,
    RefreshCcw,
    Sparkles,
    Shapes,
    Wrench,
} from 'lucide-react';
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
import { WorkflowEffectivenessSurface } from '../execution/WorkflowEffectivenessSurface';
import { Badge, ModelBadge } from '../ui/badge';
import { Button } from '../ui/button';
import { AlertSurface, Surface } from '../ui/surface';
import { formatPercent, formatTokenCount, resolveTokenMetrics } from '../../lib/tokenMetrics';
import { costProvenanceLabel } from '../../lib/sessionSemantics';
import { chartTheme, getChartSeriesColor } from '../../lib/chartTheme';
import { cn } from '../../lib/utils';

type AnalyticsTab = 'overview' | 'attribution' | 'artifacts' | 'models_tools' | 'features' | 'correlation' | 'workflow_intelligence';

const TAB_LABELS: Array<{ id: AnalyticsTab; label: string; icon: any }> = [
    { id: 'overview', label: 'Overview', icon: BarChart3 },
    { id: 'attribution', label: 'Attribution', icon: Sparkles },
    { id: 'workflow_intelligence', label: 'Workflow Intel', icon: Sparkles },
    { id: 'artifacts', label: 'Artifacts', icon: Shapes },
    { id: 'models_tools', label: 'Models + Tools', icon: Network },
    { id: 'features', label: 'Features', icon: Layers3 },
    { id: 'correlation', label: 'Correlation', icon: Wrench },
];

const TAB_IDS = new Set<AnalyticsTab>(TAB_LABELS.map(tab => tab.id));

const isAnalyticsTab = (value: string | null): value is AnalyticsTab => (
    Boolean(value) && TAB_IDS.has(value as AnalyticsTab)
);

const PIE_TONES = ['primary', 'info', 'success', 'warning', 'danger', 'secondary', 'tertiary', 'quaternary'] as const;

const formatNumber = (value: number): string => Number(value || 0).toLocaleString();
const formatCurrency = (value: number): string => `$${Number(value || 0).toFixed(4)}`;
const formatDurationSeconds = (seconds: number): string => {
    const total = Math.max(0, Number(seconds || 0));
    if (total >= 3600) return `${(total / 3600).toFixed(1)}h`;
    if (total >= 60) return `${(total / 60).toFixed(1)}m`;
    return `${Math.round(total)}s`;
};

const MetricCard: React.FC<{ label: string; value: string; subtitle: string }> = ({ label, value, subtitle }) => (
    <Surface tone="panel" padding="md" className="h-full">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="mt-2 text-2xl font-semibold text-panel-foreground">{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>
    </Surface>
);

const EntityLinkButton: React.FC<{ label: string; onClick: () => void; mono?: boolean }> = ({ label, onClick, mono }) => (
    <button
        onClick={onClick}
        className={cn(
            'inline-flex items-center rounded px-1.5 py-0.5 text-primary hover:text-primary/90 hover:bg-primary/10 transition-colors',
            mono ? 'font-mono text-xs' : 'text-sm',
        )}
        title={`Open ${label}`}
    >
        {label}
    </button>
);

export const AnalyticsDashboard: React.FC = () => {
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const { getColorForModel, getBadgeStyleForModel } = useModelColors();
    const { activeProject } = useData();
    const [activeTab, setActiveTab] = useState<AnalyticsTab>(() => {
        const tabParam = searchParams.get('tab');
        return isAnalyticsTab(tabParam) ? tabParam : 'overview';
    });
    const [modelGrouping, setModelGrouping] = useState<'model' | 'family'>('model');
    const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
    const [notifications, setNotifications] = useState<Notification[]>([]);
    const [artifacts, setArtifacts] = useState<AnalyticsArtifactsResponse | null>(null);
    const [correlation, setCorrelation] = useState<AnalyticsCorrelationItem[]>([]);
    const [costCalibration, setCostCalibration] = useState<SessionCostCalibrationSummary | null>(null);
    const [usageAttribution, setUsageAttribution] = useState<SessionUsageAggregateResponse | null>(null);
    const [usageCalibration, setUsageCalibration] = useState<SessionUsageCalibrationSummary | null>(null);
    const [usageDrilldown, setUsageDrilldown] = useState<SessionUsageDrilldownResponse | null>(null);
    const [selectedUsageEntity, setSelectedUsageEntity] = useState<{ entityType: string; entityId: string } | null>(null);
    const [correlationLinkedOnly, setCorrelationLinkedOnly] = useState(false);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const workflowAnalyticsAvailable = isWorkflowAnalyticsEnabled(activeProject);
    const usageAttributionAvailable = isUsageAttributionEnabled(activeProject);

    const openSession = useCallback((sessionId: string) => {
        if (!sessionId) return;
        navigate(`/sessions?session=${encodeURIComponent(sessionId)}`);
    }, [navigate]);
    const openFeature = useCallback((featureId: string) => {
        if (!featureId) return;
        navigate(`/board?feature=${encodeURIComponent(featureId)}`);
    }, [navigate]);

    const loadAll = async () => {
        setLoading(true);
        setError(null);
        try {
            const usagePayloadPromise = usageAttributionAvailable
                ? analyticsService.getUsageAttribution({ limit: 24 }).then(data => ({ data, error: null as string | null }))
                    .catch(fetchError => ({ data: null, error: fetchError instanceof Error ? fetchError.message : 'Failed to load usage attribution analytics.' }))
                : Promise.resolve({ data: null, error: null as string | null });
            const calibrationPayloadPromise = usageAttributionAvailable
                ? analyticsService.getUsageAttributionCalibration().then(data => ({ data, error: null as string | null }))
                    .catch(fetchError => ({ data: null, error: fetchError instanceof Error ? fetchError.message : 'Failed to load usage attribution calibration.' }))
                : Promise.resolve({ data: null, error: null as string | null });

            const [overviewData, notificationData, artifactData, correlationData, costCalibrationData, usagePayload, calibrationPayload] = await Promise.all([
                analyticsService.getOverview(),
                analyticsService.getNotifications(),
                analyticsService.getArtifacts({ limit: 200 }),
                analyticsService.getCorrelation(),
                analyticsService.getSessionCostCalibration(),
                usagePayloadPromise,
                calibrationPayloadPromise,
            ]);
            setOverview(overviewData);
            setNotifications(notificationData);
            setArtifacts(artifactData);
            setCorrelation(correlationData.items || []);
            setCostCalibration(costCalibrationData);
            setUsageAttribution(usagePayload.data);
            setUsageCalibration(calibrationPayload.data);
            const firstRow = (usagePayload.data?.rows || [])[0];
            setSelectedUsageEntity(firstRow?.entityType && firstRow?.entityId
                ? { entityType: firstRow.entityType, entityId: firstRow.entityId }
                : null);
            if (usagePayload.error || calibrationPayload.error) {
                console.warn('Usage attribution analytics unavailable', usagePayload.error || calibrationPayload.error);
            }
        } catch (e) {
            console.error('Failed to load analytics dashboard payloads', e);
            setError('Failed to load analytics data.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        void loadAll();
    }, []);

    useEffect(() => {
        const tabParam = searchParams.get('tab');
        if (isAnalyticsTab(tabParam)) {
            setActiveTab(prev => (prev === tabParam ? prev : tabParam));
        }
    }, [searchParams]);

    useEffect(() => {
        const nextParams = new URLSearchParams(searchParams);
        if (activeTab === 'overview') {
            nextParams.delete('tab');
        } else {
            nextParams.set('tab', activeTab);
        }
        if (nextParams.toString() !== searchParams.toString()) {
            setSearchParams(nextParams, { replace: true });
        }
    }, [activeTab, searchParams, setSearchParams]);

    useEffect(() => {
        if (!selectedUsageEntity?.entityType || !selectedUsageEntity?.entityId) {
            setUsageDrilldown(null);
            return;
        }
        let cancelled = false;
        void analyticsService.getUsageAttributionDrilldown({
            entityType: selectedUsageEntity.entityType,
            entityId: selectedUsageEntity.entityId,
            limit: 30,
        }).then(payload => {
            if (!cancelled) setUsageDrilldown(payload);
        }).catch(fetchError => {
            console.error('Failed to load attribution drilldown', fetchError);
            if (!cancelled) setUsageDrilldown(null);
        });
        return () => {
            cancelled = true;
        };
    }, [selectedUsageEntity]);

    const handleExport = () => {
        window.open(analyticsService.getPrometheusExportUrl(), '_blank');
    };

    const artifactTypeChart = useMemo(
        () => (artifacts?.byType || []).slice(0, 8).map(item => ({ name: item.artifactType, count: item.count })),
        [artifacts]
    );
    const artifactSourceChart = useMemo(
        () => (artifacts?.bySource || []).slice(0, 8).map(item => ({ name: item.source, count: item.count })),
        [artifacts]
    );
    const modelTokenChart = useMemo(
        () => {
            if (modelGrouping === 'family') {
                return (artifacts?.tokenUsage?.byModelFamily || [])
                    .slice(0, 10)
                    .map(item => ({ name: item.modelFamily, tokens: item.totalTokens, cost: item.totalCost }));
            }
            return (artifacts?.tokenUsage?.byModel || [])
                .slice(0, 10)
                .map(item => ({ name: item.model, tokens: item.totalTokens, cost: item.totalCost }));
        },
        [artifacts, modelGrouping]
    );
    const featureChart = useMemo(
        () => (artifacts?.byFeature || []).slice(0, 10).map(item => ({ name: item.featureName || item.featureId, count: item.artifactCount })),
        [artifacts]
    );
    const filteredCorrelation = useMemo(
        () => (
            correlationLinkedOnly
                ? correlation.filter(row => Boolean((row.featureId || '').trim()))
                : correlation
        ),
        [correlation, correlationLinkedOnly]
    );
    const correlationSummary = useMemo(() => {
        const uniqueSessions = new Set<string>();
        const sessionsWithLinks = new Set<string>();
        let linkedRows = 0;
        let highConfidenceRows = 0;
        let confidenceTotal = 0;
        let confidenceCount = 0;
        let subagentRows = 0;
        let totalTokens = 0;

        correlation.forEach(row => {
            if (row.sessionId) uniqueSessions.add(row.sessionId);
            if (row.isSubagent) subagentRows += 1;
            totalTokens += Number(row.totalTokens || 0);
            if (!(row.featureId || '').trim()) return;
            linkedRows += 1;
            sessionsWithLinks.add(row.sessionId);
            const confidence = Number(row.confidence || 0);
            confidenceTotal += confidence;
            confidenceCount += 1;
            if (confidence >= 0.75) highConfidenceRows += 1;
        });

        return {
            totalRows: correlation.length,
            uniqueSessions: uniqueSessions.size,
            linkedRows,
            linkedSessionPct: uniqueSessions.size > 0 ? (sessionsWithLinks.size / uniqueSessions.size) * 100 : 0,
            avgConfidence: confidenceCount > 0 ? confidenceTotal / confidenceCount : 0,
            highConfidenceRows,
            subagentRows,
            totalTokens,
        };
    }, [correlation]);
    const overviewWorkload = useMemo(
        () => resolveTokenMetrics({
            modelIOTokens: overview?.kpis?.modelIOTokens,
            cacheInputTokens: overview?.kpis?.cacheInputTokens,
            observedTokens: overview?.kpis?.observedTokens,
            toolReportedTokens: overview?.kpis?.toolReportedTokens,
        }),
        [overview]
    );
    const attributionMethodMix = useMemo(
        () => (usageCalibration?.methodMix || []).slice(0, 6),
        [usageCalibration]
    );
    const attributionRows = useMemo(
        () => (usageAttribution?.rows || []).slice(0, 12),
        [usageAttribution]
    );

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
            <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                    <h2 className="text-3xl font-bold text-panel-foreground">Analytics & Trends</h2>
                    <p className="mt-2 text-muted-foreground">Expanded analytics across artifacts, models, tools, sessions, and features.</p>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                            void loadAll();
                        }}
                    >
                        <RefreshCcw size={15} />
                        Refresh
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={handleExport}
                    >
                        <Download size={16} />
                        Export Prometheus
                    </Button>
                </div>
            </div>

            <div className="flex items-center gap-2 overflow-x-auto pb-1">
                {TAB_LABELS.map(tab => {
                    const Icon = tab.icon;
                    const active = activeTab === tab.id;
                    return (
                        <Button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            variant={active ? 'panel' : 'chip'}
                            size="sm"
                            className="whitespace-nowrap"
                        >
                            <Icon size={15} />
                            {tab.label}
                        </Button>
                    );
                })}
            </div>

            {loading && <div className="text-muted-foreground">Loading analytics data...</div>}
            {!loading && error && <AlertSurface intent="danger">{error}</AlertSurface>}

            {!loading && !error && activeTab === 'overview' && (
                <div className="space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                        <MetricCard
                            label="Observed Workload"
                            value={formatTokenCount(overviewWorkload.workloadTokens)}
                            subtitle={`${formatTokenCount(overviewWorkload.cacheInputTokens)} cache input`}
                        />
                        <MetricCard
                            label="Model IO"
                            value={formatTokenCount(overviewWorkload.modelIOTokens)}
                            subtitle={`${formatTokenCount(overviewWorkload.tokenOutput)} output tokens`}
                        />
                        <MetricCard
                            label="Display Spend"
                            value={formatCurrency(Number(overview?.kpis?.sessionCost || 0))}
                            subtitle={`${formatNumber(costCalibration?.comparableSessionCount || 0)} comparable sessions`}
                        />
                        <MetricCard
                            label="Sessions"
                            value={formatNumber(Number(overview?.kpis?.sessionCount || 0))}
                            subtitle={`${Number(overview?.kpis?.sessionDurationAvg || 0).toFixed(1)}s avg duration`}
                        />
                        <MetricCard
                            label="Task Velocity"
                            value={formatNumber(Number(overview?.kpis?.taskVelocity || 0))}
                            subtitle={`${Number(overview?.kpis?.taskCompletionPct || 0).toFixed(1)}% completion`}
                        />
                        <MetricCard
                            label="Tool Reliability"
                            value={`${Number(overview?.kpis?.toolSuccessRate || 0).toFixed(1)}%`}
                            subtitle={`${formatNumber(Number(overview?.kpis?.toolCallCount || 0))} calls tracked`}
                        />
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <TrendChart metric="session_cost" title="Session Cost" color={getChartSeriesColor('danger')} valueFormatter={(v) => `$${v.toFixed(2)}`} />
                        <TrendChart metric="session_tokens" title="Observed Workload" color={getChartSeriesColor('info')} valueFormatter={(v) => v.toLocaleString()} />
                        <TrendChart metric="session_count" title="Sessions" color={getChartSeriesColor('success')} />
                        <TrendChart
                            metric="task_completion_pct"
                            title="Task Completion %"
                            color={getChartSeriesColor('warning')}
                            valueFormatter={(v) => `${v.toFixed(1)}%`}
                        />
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-[1.2fr_0.8fr] gap-6">
                        <Surface tone="panel" padding="lg">
                            <h3 className="text-lg font-semibold text-panel-foreground">Cache Efficiency</h3>
                            <p className="mt-1 text-sm text-muted-foreground">
                                Observed workload defaults to message-derived tokens. Tool-reported totals remain fallback-only and are not additive.
                            </p>
                            <div className="mt-5 grid grid-cols-1 sm:grid-cols-3 gap-3">
                                <Surface tone="overlay" padding="md">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Cache Share</div>
                                    <div className="mt-2 text-2xl font-semibold text-info-foreground">{formatPercent(overviewWorkload.cacheShare)}</div>
                                    <div className="mt-1 text-xs text-muted-foreground">of observed workload</div>
                                </Surface>
                                <Surface tone="overlay" padding="md">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Cache Input</div>
                                    <div className="mt-2 text-2xl font-semibold text-success-foreground">{formatTokenCount(overviewWorkload.cacheInputTokens)}</div>
                                    <div className="mt-1 text-xs text-muted-foreground">cache creation + cache read</div>
                                </Surface>
                                <Surface tone="overlay" padding="md">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Tool Fallback</div>
                                    <div className="mt-2 text-2xl font-semibold text-warning-foreground">{formatTokenCount(overviewWorkload.toolReportedTokens)}</div>
                                    <div className="mt-1 text-xs text-muted-foreground">visible for diagnostics only</div>
                                </Surface>
                            </div>
                        </Surface>

                        <Surface tone="panel" padding="lg">
                            <h3 className="text-lg font-semibold text-panel-foreground">Token Semantics</h3>
                            <div className="mt-4 space-y-3 text-sm text-foreground">
                                <Surface tone="overlay" padding="md">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Observed Workload</div>
                                    <div className="mt-1">Model IO plus cache input when available.</div>
                                </Surface>
                                <Surface tone="overlay" padding="md">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Current Context</div>
                                    <div className="mt-1">A point-in-time occupancy snapshot, never merged into observed workload totals.</div>
                                </Surface>
                                <Surface tone="overlay" padding="md">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Model IO</div>
                                    <div className="mt-1">Legacy `tokensIn` + `tokensOut`, preserved for cost and compatibility.</div>
                                </Surface>
                                <Surface tone="overlay" padding="md">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Display Spend</div>
                                    <div className="mt-1">Reported cost wins when available, then recalculated pricing, then estimated fallback.</div>
                                </Surface>
                                <Surface tone="overlay" padding="md">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Relay Policy</div>
                                    <div className="mt-1">Relay-wrapped `data.message.message.*` records stay excluded until attribution is implemented.</div>
                                </Surface>
                            </div>
                        </Surface>
                    </div>

                    {costCalibration && (
                        <Surface tone="panel" padding="lg">
                            <h3 className="text-lg font-semibold text-panel-foreground">Cost Calibration</h3>
                            <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                                <Surface tone="overlay" padding="md">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Comparable Coverage</div>
                                    <div className="mt-2 text-2xl font-semibold text-success-foreground">{formatPercent(costCalibration.comparableCoveragePct)}</div>
                                    <div className="mt-1 text-xs text-muted-foreground">{formatNumber(costCalibration.comparableSessionCount)} sessions</div>
                                </Surface>
                                <Surface tone="overlay" padding="md">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Avg Mismatch</div>
                                    <div className="mt-2 text-2xl font-semibold text-warning-foreground">{formatPercent(costCalibration.avgMismatchPct)}</div>
                                    <div className="mt-1 text-xs text-muted-foreground">max {formatPercent(costCalibration.maxMismatchPct)}</div>
                                </Surface>
                                <Surface tone="overlay" padding="md">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Avg Confidence</div>
                                    <div className="mt-2 text-2xl font-semibold text-primary-foreground">{formatPercent(costCalibration.avgCostConfidence)}</div>
                                    <div className="mt-1 text-xs text-muted-foreground">all sessions</div>
                                </Surface>
                                <Surface tone="overlay" padding="md">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Display Spend</div>
                                    <div className="mt-2 text-2xl font-semibold text-panel-foreground">{formatCurrency(costCalibration.totalDisplayCostUsd)}</div>
                                    <div className="mt-1 text-xs text-muted-foreground">reported &gt; recalculated &gt; estimated</div>
                                </Surface>
                            </div>
                        </Surface>
                    )}

                    <Surface tone="panel" padding="lg">
                        <div className="flex items-center gap-2 mb-4">
                            <Bell size={18} className="text-primary" />
                            <h3 className="text-lg font-semibold text-panel-foreground">Recent Alerts</h3>
                        </div>
                        <div className="space-y-3">
                            {notifications.length === 0 ? (
                                <p className="text-muted-foreground">No recent alerts.</p>
                            ) : (
                                notifications.map(n => (
                                    <Surface key={n.id} tone="overlay" padding="sm" className="flex items-center justify-between gap-3">
                                        <span className="text-sm text-foreground">{n.message}</span>
                                        <span className="text-xs text-muted-foreground">{new Date(n.timestamp).toLocaleString()}</span>
                                    </Surface>
                                ))
                            )}
                        </div>
                    </Surface>
                </div>
            )}

            {!loading && !error && activeTab === 'attribution' && (
                usageAttributionAvailable && usageAttribution && usageCalibration ? (
                <div className="space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                        <MetricCard
                            label="Primary Coverage"
                            value={formatPercent(Number(usageCalibration?.primaryCoverage || 0))}
                            subtitle={`${formatNumber(Number(usageCalibration?.primaryAttributedEventCount || 0))} primary-attributed events`}
                        />
                        <MetricCard
                            label="Exclusive Model IO"
                            value={formatTokenCount(Number(usageCalibration?.exclusiveModelIOTokens || 0))}
                            subtitle={`${formatTokenCount(Number(usageCalibration?.sessionModelIOTokens || 0))} session model IO`}
                        />
                        <MetricCard
                            label="Model IO Gap"
                            value={formatTokenCount(Math.abs(Number(usageCalibration?.modelIOGap || 0)))}
                            subtitle={Number(usageCalibration?.modelIOGap || 0) === 0 ? 'fully reconciled' : 'needs tuning'}
                        />
                        <MetricCard
                            label="Avg Confidence"
                            value={Number(usageCalibration?.averageConfidence || 0).toFixed(2)}
                            subtitle={`${formatNumber(Number(usageCalibration?.ambiguousEventCount || 0))} ambiguous events`}
                        />
                    </div>

                    <div className="grid grid-cols-1 xl:grid-cols-[1.2fr_0.8fr] gap-6">
                        <div className="bg-panel border border-panel-border rounded-xl p-5">
                            <div className="flex items-center justify-between gap-3 mb-4">
                                <div>
                                    <h3 className="text-panel-foreground font-semibold">Top Attribution Targets</h3>
                                    <p className="mt-1 text-sm text-muted-foreground">Exclusive totals reconcile workload. Supporting totals show participation across overlaps.</p>
                                </div>
                                <div className="text-xs text-muted-foreground">
                                    {formatNumber(Number(usageAttribution?.summary?.entityCount || 0))} entities
                                </div>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="text-muted-foreground border-b border-panel-border">
                                            <th className="text-left py-2 pr-3">Entity</th>
                                            <th className="text-right py-2 pr-3">Exclusive</th>
                                            <th className="text-right py-2 pr-3">Supporting</th>
                                            <th className="text-right py-2 pr-3">Cache Share</th>
                                            <th className="text-right py-2 pr-3">Cost</th>
                                            <th className="text-right py-2">Confidence</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {attributionRows.map((row, idx) => {
                                            const isSelected = selectedUsageEntity?.entityType === row.entityType && selectedUsageEntity?.entityId === row.entityId;
                                            const cacheShare = Number(row.exclusiveTokens || 0) > 0
                                                ? Number(row.exclusiveCacheInputTokens || 0) / Number(row.exclusiveTokens || 1)
                                                : 0;
                                            return (
                                                <tr
                                                    key={`${row.entityType}-${row.entityId}-${idx}`}
                                                    className={`border-b border-panel-border/80 text-foreground ${isSelected ? 'bg-primary/5' : ''}`}
                                                >
                                                    <td className="py-2 pr-3">
                                                        <button
                                                            onClick={() => setSelectedUsageEntity({ entityType: row.entityType, entityId: row.entityId })}
                                                            className="text-left"
                                                        >
                                                            <div className="text-panel-foreground">{row.entityLabel || row.entityId}</div>
                                                            <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{row.entityType}</div>
                                                        </button>
                                                    </td>
                                                    <td className="py-2 pr-3 text-right font-mono">{formatNumber(Number(row.exclusiveTokens || 0))}</td>
                                                    <td className="py-2 pr-3 text-right font-mono">{formatNumber(Number(row.supportingTokens || 0))}</td>
                                                    <td className="py-2 pr-3 text-right font-mono">{formatPercent(cacheShare)}</td>
                                                    <td className="py-2 pr-3 text-right font-mono">{formatCurrency(Number(row.exclusiveCostUsdModelIO || 0))}</td>
                                                    <td className="py-2 text-right font-mono">{Number(row.averageConfidence || 0).toFixed(2)}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        <div className="bg-panel border border-panel-border rounded-xl p-5">
                            <h3 className="text-panel-foreground font-semibold">Calibration Summary</h3>
                            <div className="mt-4 space-y-3 text-sm">
                                {(usageCalibration?.confidenceBands || []).map((band, idx) => (
                                    <div key={`${String(band.band)}-${idx}`} className="rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-3 flex items-center justify-between gap-3">
                                        <span className="text-foreground capitalize">{String(band.band || 'unknown')} confidence</span>
                                        <span className="font-mono text-panel-foreground">{formatNumber(Number(band.count || 0))}</span>
                                    </div>
                                ))}
                                <div className="rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-3 flex items-center justify-between gap-3">
                                    <span className="text-foreground">Unattributed events</span>
                                    <span className="font-mono text-panel-foreground">{formatNumber(Number(usageCalibration?.unattributedEventCount || 0))}</span>
                                </div>
                                <div className="rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-3 flex items-center justify-between gap-3">
                                    <span className="text-foreground">Cache reconciliation gap</span>
                                    <span className="font-mono text-panel-foreground">{formatTokenCount(Math.abs(Number(usageCalibration?.cacheGap || 0)))}</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 xl:grid-cols-[0.9fr_1.1fr] gap-6">
                        <div className="bg-panel border border-panel-border rounded-xl p-5">
                            <h3 className="text-panel-foreground font-semibold mb-4">Method Mix</h3>
                            <div className="space-y-3">
                                {attributionMethodMix.map((row, idx) => (
                                    <div key={`${String(row.method)}-${idx}`} className="rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-3">
                                        <div className="flex items-center justify-between gap-3">
                                            <span className="text-panel-foreground text-sm">{String(row.method || 'unknown')}</span>
                                            <span className="font-mono text-panel-foreground">{formatNumber(Number(row.tokens || 0))}</span>
                                        </div>
                                        <div className="mt-1 text-xs text-muted-foreground">
                                            {formatNumber(Number(row.eventCount || 0))} events, avg confidence {Number(row.averageConfidence || 0).toFixed(2)}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="bg-panel border border-panel-border rounded-xl p-5">
                            <div className="flex items-center justify-between gap-3 mb-4">
                                <div>
                                    <h3 className="text-panel-foreground font-semibold">Entity Drill-down</h3>
                                    <p className="mt-1 text-sm text-muted-foreground">
                                        {selectedUsageEntity ? `${selectedUsageEntity.entityType}: ${selectedUsageEntity.entityId}` : 'Select an entity to inspect contributing events.'}
                                    </p>
                                </div>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="text-muted-foreground border-b border-panel-border">
                                            <th className="text-left py-2 pr-3">Captured</th>
                                            <th className="text-left py-2 pr-3">Session</th>
                                            <th className="text-left py-2 pr-3">Method</th>
                                            <th className="text-right py-2 pr-3">Tokens</th>
                                            <th className="text-right py-2 pr-3">Role</th>
                                            <th className="text-right py-2">Confidence</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {(usageDrilldown?.items || []).map((row, idx) => (
                                            <tr key={`${row.eventId}-${idx}`} className="border-b border-panel-border/80 text-foreground">
                                                <td className="py-2 pr-3 text-xs text-muted-foreground">{new Date(row.capturedAt).toLocaleString()}</td>
                                                <td className="py-2 pr-3">
                                                    <EntityLinkButton label={row.sessionId} onClick={() => openSession(row.sessionId)} mono />
                                                </td>
                                                <td className="py-2 pr-3 text-xs">{row.method}</td>
                                                <td className="py-2 pr-3 text-right font-mono">{formatNumber(Number(row.deltaTokens || 0))}</td>
                                                <td className="py-2 pr-3 text-right text-xs uppercase tracking-wide">{row.attributionRole}</td>
                                                <td className="py-2 text-right font-mono">{Number(row.confidence || 0).toFixed(2)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
                ) : (
                    <div className="rounded-xl border border-warning-border/30 bg-warning/10 px-4 py-3 text-sm text-warning-foreground">
                        <p className="font-semibold">{usageAttributionAvailable ? 'Usage Attribution Unavailable' : 'Usage Attribution Disabled'}</p>
                        <p className="mt-1 text-warning-foreground/80">
                            {usageAttributionAvailable
                                ? 'The attribution endpoints are currently unavailable. Check the global rollout gate or backend status.'
                                : 'Enable Usage Attribution in Project Settings to show attribution rollups, calibration, and drill-down views.'}
                        </p>
                    </div>
                )
            )}

            {!loading && !error && activeTab === 'workflow_intelligence' && (
                workflowAnalyticsAvailable ? (
                    <div className="space-y-4">
                        <WorkflowEffectivenessSurface
                            title="Workflow Effectiveness"
                            description="Rank workflow, agent, skill, context, and stack patterns with real delivery outcomes and failure signals."
                            onOpenSession={(sessionId) => openSession(sessionId)}
                        />
                        <div className="flex justify-end">
                            <button
                                onClick={() => navigate('/workflows')}
                                className="inline-flex items-center gap-2 rounded-lg border border-hover px-3 py-2 text-xs font-semibold text-panel-foreground transition-colors hover:border-hover"
                            >
                                <Sparkles size={13} />
                                Open Workflow Registry
                            </button>
                        </div>
                    </div>
                ) : (
                    <div className="rounded-xl border border-warning-border/30 bg-warning/10 px-4 py-3 text-sm text-warning-foreground">
                        <p className="font-semibold">Workflow Intelligence Disabled</p>
                        <p className="mt-1 text-warning-foreground/80">
                            Project settings have disabled workflow effectiveness analytics for this surface.
                        </p>
                    </div>
                )
            )}

            {!loading && !error && activeTab === 'artifacts' && (
                <div className="space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        <MetricCard
                            label="Artifacts"
                            value={formatNumber(artifacts?.totals?.artifactCount || 0)}
                            subtitle={`${formatNumber(artifacts?.totals?.artifactTypes || 0)} unique types`}
                        />
                        <MetricCard
                            label="Sessions"
                            value={formatNumber(artifacts?.totals?.sessions || 0)}
                            subtitle={`${formatNumber(artifacts?.totals?.features || 0)} mapped features`}
                        />
                        <MetricCard
                            label="Agents / Skills"
                            value={`${formatNumber(artifacts?.totals?.kindTotals?.agents || 0)} / ${formatNumber(artifacts?.totals?.kindTotals?.skills || 0)}`}
                            subtitle="Artifact events classified as agent or skill"
                        />
                        <MetricCard
                            label="Commands"
                            value={formatNumber(artifacts?.totals?.kindTotals?.commands || 0)}
                            subtitle="Command-linked artifact events"
                        />
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <MetricCard
                            label="Model Families"
                            value={formatNumber(artifacts?.totals?.modelFamilies || 0)}
                            subtitle="Canonical family buckets (Opus, Sonnet, etc.)"
                        />
                        <MetricCard
                            label="Models"
                            value={formatNumber(artifacts?.totals?.models || 0)}
                            subtitle="Canonicalized model identifiers"
                        />
                        <MetricCard
                            label="Tools"
                            value={formatNumber(artifacts?.totals?.tools || 0)}
                            subtitle="Source tools linked to artifact generation"
                        />
                    </div>

                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                        <div className="bg-panel border border-panel-border rounded-xl p-5">
                            <h3 className="text-panel-foreground font-semibold mb-4">Artifacts by Type</h3>
                            <div className="h-72 w-full">
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={artifactTypeChart}>
                                        <CartesianGrid {...chartTheme.grid} vertical={false} />
                                        <XAxis dataKey="name" {...chartTheme.axis} tick={{ ...chartTheme.axis.tick, fontSize: 11 }} />
                                        <YAxis {...chartTheme.axis} tick={{ ...chartTheme.axis.tick, fontSize: 11 }} />
                                        <Tooltip
                                            contentStyle={chartTheme.tooltip.contentStyle}
                                            itemStyle={chartTheme.tooltip.itemStyle}
                                            labelStyle={chartTheme.tooltip.labelStyle}
                                            cursor={chartTheme.tooltip.cursor}
                                            formatter={(value: number) => [formatNumber(value), 'Artifacts']}
                                        />
                                        <Bar dataKey="count" fill={getChartSeriesColor('primary')} radius={[4, 4, 0, 0]} />
                                    </BarChart>
                                </ResponsiveContainer>
                            </div>
                        </div>

                        <div className="bg-panel border border-panel-border rounded-xl p-5">
                            <h3 className="text-panel-foreground font-semibold mb-4">Artifact Sources</h3>
                            <div className="h-72 w-full">
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Tooltip
                                            contentStyle={chartTheme.tooltip.contentStyle}
                                            itemStyle={chartTheme.tooltip.itemStyle}
                                            labelStyle={chartTheme.tooltip.labelStyle}
                                            cursor={chartTheme.tooltip.cursor}
                                        />
                                        <Pie data={artifactSourceChart} dataKey="count" nameKey="name" outerRadius={110} label>
                                            {artifactSourceChart.map((entry, index) => (
                                                <Cell key={`${entry.name}-${index}`} fill={getChartSeriesColor(PIE_TONES[index % PIE_TONES.length])} />
                                            ))}
                                        </Pie>
                                    </PieChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </div>

                    <div className="bg-panel border border-panel-border rounded-xl p-5">
                        <h3 className="text-panel-foreground font-semibold mb-4">Model ↔ Artifact Relationships</h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-muted-foreground border-b border-panel-border">
                                        <th className="text-left py-2 pr-3">Model</th>
                                        <th className="text-left py-2 pr-3">Artifact Type</th>
                                        <th className="text-right py-2 pr-3">Count</th>
                                        <th className="text-right py-2 pr-3">Sessions</th>
                                        <th className="text-right py-2 pr-3">IO Tokens</th>
                                        <th className="text-right py-2">Cost</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(artifacts?.modelArtifact || []).slice(0, 24).map((row, idx) => (
                                        <tr key={`${row.model}-${row.artifactType}-${idx}`} className="border-b border-panel-border/80 text-foreground">
                                            <td className="py-2 pr-3"><ModelBadge raw={row.model} family={row.modelFamily} /></td>
                                            <td className="py-2 pr-3">{row.artifactType}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.count)}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.sessions)}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.totalTokens)}</td>
                                            <td className="py-2 text-right font-mono">{formatCurrency(row.totalCost)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <div className="bg-panel border border-panel-border rounded-xl p-5">
                        <h3 className="text-panel-foreground font-semibold mb-4">Per-Session Artifact Detail</h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-muted-foreground border-b border-panel-border">
                                        <th className="text-left py-2 pr-3">Session</th>
                                        <th className="text-left py-2 pr-3">Model</th>
                                        <th className="text-right py-2 pr-3">Artifacts</th>
                                        <th className="text-right py-2 pr-3">IO Tokens</th>
                                        <th className="text-right py-2 pr-3">Cost</th>
                                        <th className="text-left py-2">Feature(s)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(artifacts?.bySession || []).slice(0, 20).map((row) => (
                                        <tr key={row.sessionId} className="border-b border-panel-border/80 text-foreground">
                                            <td className="py-2 pr-3">
                                                <EntityLinkButton label={row.sessionId} onClick={() => openSession(row.sessionId)} mono />
                                            </td>
                                            <td className="py-2 pr-3">
                                                <div><ModelBadge raw={row.model} family={row.modelFamily} /></div>
                                                {row.modelFamily && <div className="text-[11px] text-muted-foreground">{row.modelFamily}</div>}
                                            </td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.artifactCount)}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.totalTokens)}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatCurrency(row.totalCost)}</td>
                                            <td className="py-2 text-xs">
                                                {row.featureIds.length === 0 ? (
                                                    <span className="text-muted-foreground">Unlinked</span>
                                                ) : (
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {row.featureIds.map((featureId, idx) => (
                                                            <EntityLinkButton
                                                                key={`${row.sessionId}-${featureId}-${idx}`}
                                                                label={row.featureNames[idx] || featureId}
                                                                onClick={() => openFeature(featureId)}
                                                            />
                                                        ))}
                                                    </div>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            )}

            {!loading && !error && activeTab === 'models_tools' && (
                <div className="space-y-6">
                    <div className="bg-panel border border-panel-border rounded-xl p-5">
                        <div className="flex items-center justify-between mb-4 gap-3">
                            <h3 className="text-panel-foreground font-semibold">
                                Token Usage by {modelGrouping === 'model' ? 'Canonical Model' : 'Model Family'}
                            </h3>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={() => setModelGrouping('model')}
                                    className={`px-2.5 py-1.5 rounded-md text-xs border ${modelGrouping === 'model'
                                        ? 'bg-primary/10 border-primary-border/40 text-primary-foreground'
                                        : 'bg-surface-muted border-hover text-foreground'}`}
                                >
                                    Model
                                </button>
                                <button
                                    onClick={() => setModelGrouping('family')}
                                    className={`px-2.5 py-1.5 rounded-md text-xs border ${modelGrouping === 'family'
                                        ? 'bg-primary/10 border-primary-border/40 text-primary-foreground'
                                        : 'bg-surface-muted border-hover text-foreground'}`}
                                >
                                    Family
                                </button>
                            </div>
                        </div>
                        <div className="h-80 w-full">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={modelTokenChart}>
                                    <CartesianGrid {...chartTheme.grid} vertical={false} />
                                    <XAxis dataKey="name" {...chartTheme.axis} tick={{ ...chartTheme.axis.tick, fontSize: 11 }} />
                                    <YAxis {...chartTheme.axis} tick={{ ...chartTheme.axis.tick, fontSize: 11 }} />
                                    <Tooltip
                                        contentStyle={chartTheme.tooltip.contentStyle}
                                        itemStyle={chartTheme.tooltip.itemStyle}
                                        labelStyle={chartTheme.tooltip.labelStyle}
                                        cursor={chartTheme.tooltip.cursor}
                                        formatter={(value: number, name: string) => [name === 'cost' ? formatCurrency(value) : formatNumber(value), name]}
                                    />
                                    <Bar dataKey="tokens" radius={[4, 4, 0, 0]}>
                                        {modelTokenChart.map((entry, idx) => (
                                            <Cell
                                                key={`model-token-${entry.name}-${idx}`}
                                                fill={modelGrouping === 'family'
                                                    ? getColorForModel({ family: entry.name })
                                                    : getColorForModel({ model: entry.name })}
                                            />
                                        ))}
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    <div className="bg-panel border border-panel-border rounded-xl p-5">
                        <h3 className="text-panel-foreground font-semibold mb-4">Model Family Summary</h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-muted-foreground border-b border-panel-border">
                                        <th className="text-left py-2 pr-3">Family</th>
                                        <th className="text-right py-2 pr-3">Artifacts</th>
                                        <th className="text-right py-2 pr-3">Sessions</th>
                                        <th className="text-right py-2 pr-3">IO Tokens</th>
                                        <th className="text-right py-2">Cost</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(artifacts?.modelFamilies || []).slice(0, 12).map((row, idx) => (
                                        <tr key={`${row.modelFamily}-${idx}`} className="border-b border-panel-border/80 text-foreground">
                                            <td className="py-2 pr-3">
                                                <Badge
                                                    className="text-xs"
                                                    style={getBadgeStyleForModel({ family: row.modelFamily })}
                                                >
                                                    {row.modelFamily}
                                                </Badge>
                                            </td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.artifactCount)}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.sessions)}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.totalTokens)}</td>
                                            <td className="py-2 text-right font-mono">{formatCurrency(row.totalCost)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <div className="bg-panel border border-panel-border rounded-xl p-5">
                        <h3 className="text-panel-foreground font-semibold mb-4">Model + Artifact + Tool Relationships</h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-muted-foreground border-b border-panel-border">
                                        <th className="text-left py-2 pr-3">Model</th>
                                        <th className="text-left py-2 pr-3">Family</th>
                                        <th className="text-left py-2 pr-3">Artifact Type</th>
                                        <th className="text-left py-2 pr-3">Tool</th>
                                        <th className="text-right py-2 pr-3">Count</th>
                                        <th className="text-right py-2 pr-3">IO Tokens</th>
                                        <th className="text-right py-2">Cost</th>
                                    </tr>
                                </thead>
                                <tbody>
                                        {(artifacts?.modelArtifactTool || []).slice(0, 30).map((row, idx) => (
                                            <tr key={`${row.model}-${row.artifactType}-${row.toolName}-${idx}`} className="border-b border-panel-border/80 text-foreground">
                                                <td className="py-2 pr-3"><ModelBadge raw={row.model} family={row.modelFamily} /></td>
                                                <td className="py-2 pr-3 text-xs">
                                                    {row.modelFamily
                                                    ? <Badge style={getBadgeStyleForModel({ family: row.modelFamily })}>{row.modelFamily}</Badge>
                                                    : '-'}
                                                </td>
                                            <td className="py-2 pr-3">{row.artifactType}</td>
                                            <td className="py-2 pr-3 font-mono text-xs">{row.toolName}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.count)}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.totalTokens)}</td>
                                            <td className="py-2 text-right font-mono">{formatCurrency(row.totalCost)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                        <div className="bg-panel border border-panel-border rounded-xl p-5">
                            <h3 className="text-panel-foreground font-semibold mb-4">Commands ↔ Models</h3>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="text-muted-foreground border-b border-panel-border">
                                            <th className="text-left py-2 pr-3">Command</th>
                                            <th className="text-left py-2 pr-3">Model</th>
                                            <th className="text-left py-2 pr-3">Family</th>
                                            <th className="text-right py-2 pr-3">Events</th>
                                            <th className="text-right py-2">Sessions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {(artifacts?.commandModel || []).slice(0, 24).map((row, idx) => (
                                            <tr key={`${row.command}-${row.model}-${idx}`} className="border-b border-panel-border/80 text-foreground">
                                                <td className="py-2 pr-3 font-mono text-xs">{row.command}</td>
                                                <td className="py-2 pr-3"><ModelBadge raw={row.model} family={row.modelFamily} /></td>
                                                <td className="py-2 pr-3 text-xs">
                                                    {row.modelFamily
                                                        ? <Badge style={getBadgeStyleForModel({ family: row.modelFamily })}>{row.modelFamily}</Badge>
                                                        : '-'}
                                                </td>
                                                <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.count)}</td>
                                                <td className="py-2 text-right font-mono">{formatNumber(row.sessions)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        <div className="bg-panel border border-panel-border rounded-xl p-5">
                            <h3 className="text-panel-foreground font-semibold mb-4">Agents ↔ Models</h3>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="text-muted-foreground border-b border-panel-border">
                                            <th className="text-left py-2 pr-3">Agent</th>
                                            <th className="text-left py-2 pr-3">Model</th>
                                            <th className="text-left py-2 pr-3">Family</th>
                                            <th className="text-right py-2 pr-3">Events</th>
                                            <th className="text-right py-2">Sessions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {(artifacts?.agentModel || []).slice(0, 24).map((row, idx) => (
                                            <tr key={`${row.agent}-${row.model}-${idx}`} className="border-b border-panel-border/80 text-foreground">
                                                <td className="py-2 pr-3">{row.agent}</td>
                                                <td className="py-2 pr-3"><ModelBadge raw={row.model} family={row.modelFamily} /></td>
                                                <td className="py-2 pr-3 text-xs">
                                                    {row.modelFamily
                                                        ? <Badge style={getBadgeStyleForModel({ family: row.modelFamily })}>{row.modelFamily}</Badge>
                                                        : '-'}
                                                </td>
                                                <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.count)}</td>
                                                <td className="py-2 text-right font-mono">{formatNumber(row.sessions)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>

                    <div className="bg-panel border border-panel-border rounded-xl p-5">
                        <h3 className="text-panel-foreground font-semibold mb-4">Artifact Type ↔ Tool Relationships</h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-muted-foreground border-b border-panel-border">
                                        <th className="text-left py-2 pr-3">Artifact Type</th>
                                        <th className="text-left py-2 pr-3">Tool</th>
                                        <th className="text-right py-2 pr-3">Count</th>
                                        <th className="text-right py-2">Sessions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(artifacts?.artifactTool || []).slice(0, 24).map((row, idx) => (
                                        <tr key={`${row.artifactType}-${row.toolName}-${idx}`} className="border-b border-panel-border/80 text-foreground">
                                            <td className="py-2 pr-3">{row.artifactType}</td>
                                            <td className="py-2 pr-3 font-mono text-xs">{row.toolName}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.count)}</td>
                                            <td className="py-2 text-right font-mono">{formatNumber(row.sessions)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            )}

            {!loading && !error && activeTab === 'features' && (
                <div className="space-y-6">
                    <div className="bg-panel border border-panel-border rounded-xl p-5">
                        <h3 className="text-panel-foreground font-semibold mb-4">Artifacts by Feature</h3>
                        <div className="h-80 w-full">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={featureChart}>
                                    <CartesianGrid {...chartTheme.grid} vertical={false} />
                                    <XAxis dataKey="name" {...chartTheme.axis} tick={{ ...chartTheme.axis.tick, fontSize: 11 }} />
                                    <YAxis {...chartTheme.axis} tick={{ ...chartTheme.axis.tick, fontSize: 11 }} />
                                    <Tooltip
                                        contentStyle={chartTheme.tooltip.contentStyle}
                                        itemStyle={chartTheme.tooltip.itemStyle}
                                        labelStyle={chartTheme.tooltip.labelStyle}
                                        cursor={chartTheme.tooltip.cursor}
                                        formatter={(value: number) => [formatNumber(value), 'Artifacts']}
                                    />
                                    <Bar dataKey="count" fill={getChartSeriesColor('success')} radius={[4, 4, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    <div className="bg-panel border border-panel-border rounded-xl p-5">
                        <h3 className="text-panel-foreground font-semibold mb-4">Feature Detail</h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-muted-foreground border-b border-panel-border">
                                        <th className="text-left py-2 pr-3">Feature</th>
                                        <th className="text-right py-2 pr-3">Artifacts</th>
                                        <th className="text-right py-2 pr-3">Sessions</th>
                                        <th className="text-right py-2 pr-3">IO Tokens</th>
                                        <th className="text-right py-2">Cost</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(artifacts?.byFeature || []).slice(0, 24).map((row) => (
                                        <tr key={row.featureId} className="border-b border-panel-border/80 text-foreground">
                                            <td className="py-2 pr-3">
                                                <EntityLinkButton label={row.featureName || row.featureId} onClick={() => openFeature(row.featureId)} />
                                                <div className="text-xs text-muted-foreground font-mono">{row.featureId}</div>
                                            </td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.artifactCount)}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.sessions)}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.totalTokens)}</td>
                                            <td className="py-2 text-right font-mono">{formatCurrency(row.totalCost)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            )}

            {!loading && !error && activeTab === 'correlation' && (
                <div className="space-y-6">
                    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                        <MetricCard label="Rows" value={formatNumber(correlationSummary.totalRows)} subtitle="session-feature links" />
                        <MetricCard label="Sessions" value={formatNumber(correlationSummary.uniqueSessions)} subtitle={`${correlationSummary.linkedSessionPct.toFixed(1)}% linked`} />
                        <MetricCard label="Linked Rows" value={formatNumber(correlationSummary.linkedRows)} subtitle="feature-attached rows" />
                        <MetricCard label="High Confidence" value={formatNumber(correlationSummary.highConfidenceRows)} subtitle="confidence >= 0.75" />
                        <MetricCard label="Avg Confidence" value={correlationSummary.avgConfidence.toFixed(2)} subtitle="linked rows only" />
                        <MetricCard label="Observed Workload" value={formatNumber(correlationSummary.totalTokens)} subtitle={`${formatNumber(correlationSummary.subagentRows)} sub-thread rows`} />
                    </div>
                    {costCalibration && (
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            <MetricCard label="Comparable Sessions" value={formatNumber(costCalibration.comparableSessionCount)} subtitle={`${formatPercent(costCalibration.comparableCoveragePct)} coverage`} />
                            <MetricCard label="Avg Cost Mismatch" value={formatPercent(costCalibration.avgMismatchPct)} subtitle={`max ${formatPercent(costCalibration.maxMismatchPct)}`} />
                            <MetricCard label="Avg Cost Confidence" value={formatPercent(costCalibration.avgCostConfidence)} subtitle="display-cost rows" />
                        </div>
                    )}
                    <div className="bg-panel border border-panel-border rounded-xl p-5">
                        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                            <h3 className="text-panel-foreground font-semibold">Session ↔ Feature Correlation</h3>
                            <div className="flex bg-surface-overlay rounded-lg p-0.5 border border-panel-border">
                                <button
                                    onClick={() => setCorrelationLinkedOnly(false)}
                                    className={`px-3 py-1.5 text-[11px] font-semibold rounded ${!correlationLinkedOnly ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-panel-foreground'}`}
                                >
                                    All Rows
                                </button>
                                <button
                                    onClick={() => setCorrelationLinkedOnly(true)}
                                    className={`px-3 py-1.5 text-[11px] font-semibold rounded ${correlationLinkedOnly ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-panel-foreground'}`}
                                >
                                    Linked Only
                                </button>
                            </div>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-muted-foreground border-b border-panel-border">
                                        <th className="text-left py-2 pr-3">Session</th>
                                        <th className="text-left py-2 pr-3">Thread</th>
                                        <th className="text-left py-2 pr-3">Feature</th>
                                        <th className="text-right py-2 pr-3">Confidence</th>
                                        <th className="text-right py-2 pr-3">Linked Features</th>
                                        <th className="text-right py-2 pr-3">Observed Tokens</th>
                                        <th className="text-right py-2 pr-3">Current Context</th>
                                        <th className="text-right py-2 pr-3">Cost</th>
                                        <th className="text-left py-2 pr-3">Cost Source</th>
                                        <th className="text-right py-2 pr-3">Duration</th>
                                        <th className="text-left py-2 pr-3">Model</th>
                                        <th className="text-left py-2 pr-3">Family</th>
                                        <th className="text-left py-2">Link Strategy</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredCorrelation.slice(0, 80).map((row, idx) => (
                                        <tr key={`${row.sessionId}-${row.featureId}-${idx}`} className="border-b border-panel-border/80 text-foreground">
                                            <td className="py-2 pr-3">
                                                <EntityLinkButton label={row.sessionId} onClick={() => openSession(row.sessionId)} mono />
                                            </td>
                                            <td className="py-2 pr-3">
                                                <span className={`inline-flex rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${
                                                    row.isSubagent
                                                        ? 'bg-warning/10 text-warning-foreground border border-warning-border/25'
                                                        : 'bg-success/10 text-success-foreground border border-success-border/25'
                                                }`}>
                                                    {row.isSubagent ? 'sub-thread' : 'main'}
                                                </span>
                                            </td>
                                            <td className="py-2 pr-3">
                                                {row.featureId ? (
                                                    <EntityLinkButton
                                                        label={row.featureName || row.featureId}
                                                        onClick={() => openFeature(row.featureId)}
                                                    />
                                                ) : (
                                                    <span className="text-muted-foreground">Unlinked</span>
                                                )}
                                            </td>
                                            <td className="py-2 pr-3 text-right font-mono">{Number(row.confidence || 0).toFixed(2)}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(Number(row.linkedFeatureCount || 0))}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(Number(row.totalTokens || 0))}</td>
                                            <td className="py-2 pr-3 text-right font-mono">
                                                {row.currentContextTokens && row.contextWindowSize
                                                    ? `${formatNumber(Number(row.currentContextTokens || 0))} (${Number(row.contextUtilizationPct || 0).toFixed(1)}%)`
                                                    : '-'}
                                            </td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatCurrency(Number(row.totalCost || 0))}</td>
                                            <td className="py-2 pr-3 text-xs text-muted-foreground">
                                                {costProvenanceLabel(row.costProvenance)}
                                                {Number(row.costMismatchPct || 0) > 0 ? ` · ${(Number(row.costMismatchPct || 0) * 100).toFixed(1)}%` : ''}
                                            </td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatDurationSeconds(Number(row.durationSeconds || 0))}</td>
                                            <td className="py-2 pr-3">{row.model ? <ModelBadge raw={row.model} family={row.modelFamily} /> : <span className="text-muted-foreground">-</span>}</td>
                                            <td className="py-2 pr-3 text-xs">
                                                {row.modelFamily
                                                    ? <Badge style={getBadgeStyleForModel({ family: row.modelFamily })}>{row.modelFamily}</Badge>
                                                    : '-'}
                                            </td>
                                            <td className="py-2 text-xs text-muted-foreground">{row.linkStrategy || '-'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

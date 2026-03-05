import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { TrendChart } from './TrendChart';
import { analyticsService } from '../../services/analytics';
import { useModelColors } from '../../contexts/ModelColorsContext';
import {
    AnalyticsArtifactsResponse,
    AnalyticsCorrelationItem,
    AnalyticsMetric,
    Notification,
} from '../../types';
import { useNavigate } from 'react-router-dom';
import {
    BarChart3,
    Bell,
    Download,
    Layers3,
    Network,
    RefreshCcw,
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

type AnalyticsTab = 'overview' | 'artifacts' | 'models_tools' | 'features' | 'correlation';

const TAB_LABELS: Array<{ id: AnalyticsTab; label: string; icon: any }> = [
    { id: 'overview', label: 'Overview', icon: BarChart3 },
    { id: 'artifacts', label: 'Artifacts', icon: Shapes },
    { id: 'models_tools', label: 'Models + Tools', icon: Network },
    { id: 'features', label: 'Features', icon: Layers3 },
    { id: 'correlation', label: 'Correlation', icon: Wrench },
];

const PIE_COLORS = ['#6366f1', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#14b8a6', '#f97316'];

const formatNumber = (value: number): string => Number(value || 0).toLocaleString();
const formatCurrency = (value: number): string => `$${Number(value || 0).toFixed(4)}`;
const formatDurationSeconds = (seconds: number): string => {
    const total = Math.max(0, Number(seconds || 0));
    if (total >= 3600) return `${(total / 3600).toFixed(1)}h`;
    if (total >= 60) return `${(total / 60).toFixed(1)}m`;
    return `${Math.round(total)}s`;
};

const ModelBadge: React.FC<{ model: string; family?: string }> = ({ model, family }) => {
    const { getBadgeStyleForModel } = useModelColors();
    return (
        <span
            className="inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[11px]"
            style={getBadgeStyleForModel({ model, family })}
            title={model || 'unknown'}
        >
            {model || 'unknown'}
        </span>
    );
};

const MetricCard: React.FC<{ label: string; value: string; subtitle: string }> = ({ label, value, subtitle }) => (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <p className="text-slate-500 text-xs uppercase tracking-wide">{label}</p>
        <p className="text-2xl font-semibold text-slate-100 mt-2">{value}</p>
        <p className="text-xs text-slate-500 mt-1">{subtitle}</p>
    </div>
);

const EntityLinkButton: React.FC<{ label: string; onClick: () => void; mono?: boolean }> = ({ label, onClick, mono }) => (
    <button
        onClick={onClick}
        className={`inline-flex items-center rounded px-1.5 py-0.5 text-indigo-300 hover:text-indigo-200 hover:bg-indigo-600/10 transition-colors ${mono ? 'font-mono text-xs' : 'text-sm'}`}
        title={`Open ${label}`}
    >
        {label}
    </button>
);

export const AnalyticsDashboard: React.FC = () => {
    const navigate = useNavigate();
    const { getColorForModel, getBadgeStyleForModel } = useModelColors();
    const [activeTab, setActiveTab] = useState<AnalyticsTab>('overview');
    const [modelGrouping, setModelGrouping] = useState<'model' | 'family'>('model');
    const [metrics, setMetrics] = useState<AnalyticsMetric[]>([]);
    const [notifications, setNotifications] = useState<Notification[]>([]);
    const [artifacts, setArtifacts] = useState<AnalyticsArtifactsResponse | null>(null);
    const [correlation, setCorrelation] = useState<AnalyticsCorrelationItem[]>([]);
    const [correlationLinkedOnly, setCorrelationLinkedOnly] = useState(false);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

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
            const [metricData, notificationData, artifactData, correlationData] = await Promise.all([
                analyticsService.getMetrics(),
                analyticsService.getNotifications(),
                analyticsService.getArtifacts({ limit: 200 }),
                analyticsService.getCorrelation(),
            ]);
            setMetrics(metricData);
            setNotifications(notificationData);
            setArtifacts(artifactData);
            setCorrelation(correlationData.items || []);
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

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
            <div className="flex flex-wrap justify-between items-end gap-3">
                <div>
                    <h2 className="text-3xl font-bold text-slate-100">Analytics & Trends</h2>
                    <p className="text-slate-400 mt-2">Expanded analytics across artifacts, models, tools, sessions, and features.</p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => {
                            void loadAll();
                        }}
                        className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-2 rounded-lg text-sm font-medium transition-colors border border-slate-700"
                    >
                        <RefreshCcw size={15} />
                        Refresh
                    </button>
                    <button
                        onClick={handleExport}
                        className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 px-4 py-2 rounded-lg text-sm font-medium transition-colors border border-slate-700"
                    >
                        <Download size={16} />
                        Export Prometheus
                    </button>
                </div>
            </div>

            <div className="flex items-center gap-2 overflow-x-auto pb-1">
                {TAB_LABELS.map(tab => {
                    const Icon = tab.icon;
                    const active = activeTab === tab.id;
                    return (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`flex items-center gap-2 whitespace-nowrap px-3 py-2 rounded-lg text-sm border transition-colors ${
                                active
                                    ? 'bg-indigo-600/20 border-indigo-500/40 text-indigo-200'
                                    : 'bg-slate-900 border-slate-800 text-slate-300 hover:text-slate-100 hover:border-slate-700'
                            }`}
                        >
                            <Icon size={15} />
                            {tab.label}
                        </button>
                    );
                })}
            </div>

            {loading && <div className="text-slate-400">Loading analytics data...</div>}
            {!loading && error && <div className="text-rose-300 bg-rose-900/20 border border-rose-800 rounded-lg px-4 py-3">{error}</div>}

            {!loading && !error && activeTab === 'overview' && (
                <div className="space-y-6">
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                        {metrics.map((m) => (
                            <div key={m.name} className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                                <p className="text-slate-500 text-xs font-medium uppercase">{m.name}</p>
                                <div className="mt-2 flex items-baseline gap-1">
                                    <span className="text-2xl font-bold text-slate-100">{m.value}</span>
                                    <span className="text-sm text-slate-500">{m.unit}</span>
                                </div>
                            </div>
                        ))}
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <TrendChart metric="session_cost" title="Session Cost" color="#ef4444" valueFormatter={(v) => `$${v.toFixed(2)}`} />
                        <TrendChart metric="session_tokens" title="Tokens Used" color="#3b82f6" valueFormatter={(v) => v.toLocaleString()} />
                        <TrendChart metric="session_count" title="Sessions" color="#10b981" />
                        <TrendChart
                            metric="task_completion_pct"
                            title="Task Completion %"
                            color="#f59e0b"
                            valueFormatter={(v) => `${v.toFixed(1)}%`}
                        />
                    </div>

                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                        <div className="flex items-center gap-2 mb-4">
                            <Bell size={18} className="text-indigo-400" />
                            <h3 className="text-lg font-semibold text-slate-200">Recent Alerts</h3>
                        </div>
                        <div className="space-y-3">
                            {notifications.length === 0 ? (
                                <p className="text-slate-500">No recent alerts.</p>
                            ) : (
                                notifications.map(n => (
                                    <div key={n.id} className="p-3 bg-slate-800/50 rounded-lg border border-slate-700/50 flex justify-between items-center">
                                        <span className="text-slate-300 text-sm">{n.message}</span>
                                        <span className="text-slate-500 text-xs">{new Date(n.timestamp).toLocaleString()}</span>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>
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
                        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                            <h3 className="text-slate-200 font-semibold mb-4">Artifacts by Type</h3>
                            <div className="h-72 w-full">
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={artifactTypeChart}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                                        <XAxis dataKey="name" stroke="#64748b" tick={{ fill: '#64748b', fontSize: 11 }} />
                                        <YAxis stroke="#64748b" tick={{ fill: '#64748b', fontSize: 11 }} />
                                        <Tooltip
                                            contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
                                            formatter={(value: number) => [formatNumber(value), 'Artifacts']}
                                        />
                                        <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
                                    </BarChart>
                                </ResponsiveContainer>
                            </div>
                        </div>

                        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                            <h3 className="text-slate-200 font-semibold mb-4">Artifact Sources</h3>
                            <div className="h-72 w-full">
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                                        <Pie data={artifactSourceChart} dataKey="count" nameKey="name" outerRadius={110} label>
                                            {artifactSourceChart.map((entry, index) => (
                                                <Cell key={`${entry.name}-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                                            ))}
                                        </Pie>
                                    </PieChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </div>

                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                        <h3 className="text-slate-200 font-semibold mb-4">Model ↔ Artifact Relationships</h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-slate-400 border-b border-slate-800">
                                        <th className="text-left py-2 pr-3">Model</th>
                                        <th className="text-left py-2 pr-3">Artifact Type</th>
                                        <th className="text-right py-2 pr-3">Count</th>
                                        <th className="text-right py-2 pr-3">Sessions</th>
                                        <th className="text-right py-2 pr-3">Tokens</th>
                                        <th className="text-right py-2">Cost</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(artifacts?.modelArtifact || []).slice(0, 24).map((row, idx) => (
                                        <tr key={`${row.model}-${row.artifactType}-${idx}`} className="border-b border-slate-900/80 text-slate-300">
                                            <td className="py-2 pr-3"><ModelBadge model={row.model} family={row.modelFamily} /></td>
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

                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                        <h3 className="text-slate-200 font-semibold mb-4">Per-Session Artifact Detail</h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-slate-400 border-b border-slate-800">
                                        <th className="text-left py-2 pr-3">Session</th>
                                        <th className="text-left py-2 pr-3">Model</th>
                                        <th className="text-right py-2 pr-3">Artifacts</th>
                                        <th className="text-right py-2 pr-3">Tokens</th>
                                        <th className="text-right py-2 pr-3">Cost</th>
                                        <th className="text-left py-2">Feature(s)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(artifacts?.bySession || []).slice(0, 20).map((row) => (
                                        <tr key={row.sessionId} className="border-b border-slate-900/80 text-slate-300">
                                            <td className="py-2 pr-3">
                                                <EntityLinkButton label={row.sessionId} onClick={() => openSession(row.sessionId)} mono />
                                            </td>
                                            <td className="py-2 pr-3">
                                                <div><ModelBadge model={row.model} family={row.modelFamily} /></div>
                                                {row.modelFamily && <div className="text-[11px] text-slate-500">{row.modelFamily}</div>}
                                            </td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.artifactCount)}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(row.totalTokens)}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatCurrency(row.totalCost)}</td>
                                            <td className="py-2 text-xs">
                                                {row.featureIds.length === 0 ? (
                                                    <span className="text-slate-500">Unlinked</span>
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
                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                        <div className="flex items-center justify-between mb-4 gap-3">
                            <h3 className="text-slate-200 font-semibold">
                                Token Usage by {modelGrouping === 'model' ? 'Canonical Model' : 'Model Family'}
                            </h3>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={() => setModelGrouping('model')}
                                    className={`px-2.5 py-1.5 rounded-md text-xs border ${modelGrouping === 'model'
                                        ? 'bg-indigo-600/20 border-indigo-500/40 text-indigo-200'
                                        : 'bg-slate-800 border-slate-700 text-slate-300'}`}
                                >
                                    Model
                                </button>
                                <button
                                    onClick={() => setModelGrouping('family')}
                                    className={`px-2.5 py-1.5 rounded-md text-xs border ${modelGrouping === 'family'
                                        ? 'bg-indigo-600/20 border-indigo-500/40 text-indigo-200'
                                        : 'bg-slate-800 border-slate-700 text-slate-300'}`}
                                >
                                    Family
                                </button>
                            </div>
                        </div>
                        <div className="h-80 w-full">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={modelTokenChart}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                                    <XAxis dataKey="name" stroke="#64748b" tick={{ fill: '#64748b', fontSize: 11 }} />
                                    <YAxis stroke="#64748b" tick={{ fill: '#64748b', fontSize: 11 }} />
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
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

                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                        <h3 className="text-slate-200 font-semibold mb-4">Model Family Summary</h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-slate-400 border-b border-slate-800">
                                        <th className="text-left py-2 pr-3">Family</th>
                                        <th className="text-right py-2 pr-3">Artifacts</th>
                                        <th className="text-right py-2 pr-3">Sessions</th>
                                        <th className="text-right py-2 pr-3">Tokens</th>
                                        <th className="text-right py-2">Cost</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(artifacts?.modelFamilies || []).slice(0, 12).map((row, idx) => (
                                        <tr key={`${row.modelFamily}-${idx}`} className="border-b border-slate-900/80 text-slate-300">
                                            <td className="py-2 pr-3">
                                                <span
                                                    className="inline-flex items-center rounded border px-1.5 py-0.5 text-xs"
                                                    style={getBadgeStyleForModel({ family: row.modelFamily })}
                                                >
                                                    {row.modelFamily}
                                                </span>
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

                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                        <h3 className="text-slate-200 font-semibold mb-4">Model + Artifact + Tool Relationships</h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-slate-400 border-b border-slate-800">
                                        <th className="text-left py-2 pr-3">Model</th>
                                        <th className="text-left py-2 pr-3">Family</th>
                                        <th className="text-left py-2 pr-3">Artifact Type</th>
                                        <th className="text-left py-2 pr-3">Tool</th>
                                        <th className="text-right py-2 pr-3">Count</th>
                                        <th className="text-right py-2 pr-3">Tokens</th>
                                        <th className="text-right py-2">Cost</th>
                                    </tr>
                                </thead>
                                <tbody>
                                        {(artifacts?.modelArtifactTool || []).slice(0, 30).map((row, idx) => (
                                            <tr key={`${row.model}-${row.artifactType}-${row.toolName}-${idx}`} className="border-b border-slate-900/80 text-slate-300">
                                            <td className="py-2 pr-3"><ModelBadge model={row.model} family={row.modelFamily} /></td>
                                            <td className="py-2 pr-3 text-xs">
                                                {row.modelFamily
                                                    ? <span className="inline-flex rounded border px-1.5 py-0.5" style={getBadgeStyleForModel({ family: row.modelFamily })}>{row.modelFamily}</span>
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
                        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                            <h3 className="text-slate-200 font-semibold mb-4">Commands ↔ Models</h3>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="text-slate-400 border-b border-slate-800">
                                            <th className="text-left py-2 pr-3">Command</th>
                                            <th className="text-left py-2 pr-3">Model</th>
                                            <th className="text-left py-2 pr-3">Family</th>
                                            <th className="text-right py-2 pr-3">Events</th>
                                            <th className="text-right py-2">Sessions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {(artifacts?.commandModel || []).slice(0, 24).map((row, idx) => (
                                            <tr key={`${row.command}-${row.model}-${idx}`} className="border-b border-slate-900/80 text-slate-300">
                                                <td className="py-2 pr-3 font-mono text-xs">{row.command}</td>
                                                <td className="py-2 pr-3"><ModelBadge model={row.model} family={row.modelFamily} /></td>
                                                <td className="py-2 pr-3 text-xs">
                                                    {row.modelFamily
                                                        ? <span className="inline-flex rounded border px-1.5 py-0.5" style={getBadgeStyleForModel({ family: row.modelFamily })}>{row.modelFamily}</span>
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

                        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                            <h3 className="text-slate-200 font-semibold mb-4">Agents ↔ Models</h3>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="text-slate-400 border-b border-slate-800">
                                            <th className="text-left py-2 pr-3">Agent</th>
                                            <th className="text-left py-2 pr-3">Model</th>
                                            <th className="text-left py-2 pr-3">Family</th>
                                            <th className="text-right py-2 pr-3">Events</th>
                                            <th className="text-right py-2">Sessions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {(artifacts?.agentModel || []).slice(0, 24).map((row, idx) => (
                                            <tr key={`${row.agent}-${row.model}-${idx}`} className="border-b border-slate-900/80 text-slate-300">
                                                <td className="py-2 pr-3">{row.agent}</td>
                                                <td className="py-2 pr-3"><ModelBadge model={row.model} family={row.modelFamily} /></td>
                                                <td className="py-2 pr-3 text-xs">
                                                    {row.modelFamily
                                                        ? <span className="inline-flex rounded border px-1.5 py-0.5" style={getBadgeStyleForModel({ family: row.modelFamily })}>{row.modelFamily}</span>
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

                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                        <h3 className="text-slate-200 font-semibold mb-4">Artifact Type ↔ Tool Relationships</h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-slate-400 border-b border-slate-800">
                                        <th className="text-left py-2 pr-3">Artifact Type</th>
                                        <th className="text-left py-2 pr-3">Tool</th>
                                        <th className="text-right py-2 pr-3">Count</th>
                                        <th className="text-right py-2">Sessions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(artifacts?.artifactTool || []).slice(0, 24).map((row, idx) => (
                                        <tr key={`${row.artifactType}-${row.toolName}-${idx}`} className="border-b border-slate-900/80 text-slate-300">
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
                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                        <h3 className="text-slate-200 font-semibold mb-4">Artifacts by Feature</h3>
                        <div className="h-80 w-full">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={featureChart}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                                    <XAxis dataKey="name" stroke="#64748b" tick={{ fill: '#64748b', fontSize: 11 }} />
                                    <YAxis stroke="#64748b" tick={{ fill: '#64748b', fontSize: 11 }} />
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
                                        formatter={(value: number) => [formatNumber(value), 'Artifacts']}
                                    />
                                    <Bar dataKey="count" fill="#10b981" radius={[4, 4, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                        <h3 className="text-slate-200 font-semibold mb-4">Feature Detail</h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-slate-400 border-b border-slate-800">
                                        <th className="text-left py-2 pr-3">Feature</th>
                                        <th className="text-right py-2 pr-3">Artifacts</th>
                                        <th className="text-right py-2 pr-3">Sessions</th>
                                        <th className="text-right py-2 pr-3">Tokens</th>
                                        <th className="text-right py-2">Cost</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(artifacts?.byFeature || []).slice(0, 24).map((row) => (
                                        <tr key={row.featureId} className="border-b border-slate-900/80 text-slate-300">
                                            <td className="py-2 pr-3">
                                                <EntityLinkButton label={row.featureName || row.featureId} onClick={() => openFeature(row.featureId)} />
                                                <div className="text-xs text-slate-500 font-mono">{row.featureId}</div>
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
                        <MetricCard label="Session Tokens" value={formatNumber(correlationSummary.totalTokens)} subtitle={`${formatNumber(correlationSummary.subagentRows)} sub-thread rows`} />
                    </div>
                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                            <h3 className="text-slate-200 font-semibold">Session ↔ Feature Correlation</h3>
                            <div className="flex bg-slate-950 rounded-lg p-0.5 border border-slate-800">
                                <button
                                    onClick={() => setCorrelationLinkedOnly(false)}
                                    className={`px-3 py-1.5 text-[11px] font-semibold rounded ${!correlationLinkedOnly ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
                                >
                                    All Rows
                                </button>
                                <button
                                    onClick={() => setCorrelationLinkedOnly(true)}
                                    className={`px-3 py-1.5 text-[11px] font-semibold rounded ${correlationLinkedOnly ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
                                >
                                    Linked Only
                                </button>
                            </div>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-slate-400 border-b border-slate-800">
                                        <th className="text-left py-2 pr-3">Session</th>
                                        <th className="text-left py-2 pr-3">Thread</th>
                                        <th className="text-left py-2 pr-3">Feature</th>
                                        <th className="text-right py-2 pr-3">Confidence</th>
                                        <th className="text-right py-2 pr-3">Linked Features</th>
                                        <th className="text-right py-2 pr-3">Tokens</th>
                                        <th className="text-right py-2 pr-3">Cost</th>
                                        <th className="text-right py-2 pr-3">Duration</th>
                                        <th className="text-left py-2 pr-3">Model</th>
                                        <th className="text-left py-2 pr-3">Family</th>
                                        <th className="text-left py-2">Link Strategy</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredCorrelation.slice(0, 80).map((row, idx) => (
                                        <tr key={`${row.sessionId}-${row.featureId}-${idx}`} className="border-b border-slate-900/80 text-slate-300">
                                            <td className="py-2 pr-3">
                                                <EntityLinkButton label={row.sessionId} onClick={() => openSession(row.sessionId)} mono />
                                            </td>
                                            <td className="py-2 pr-3">
                                                <span className={`inline-flex rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${
                                                    row.isSubagent
                                                        ? 'bg-amber-500/10 text-amber-300 border border-amber-500/25'
                                                        : 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/25'
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
                                                    <span className="text-slate-500">Unlinked</span>
                                                )}
                                            </td>
                                            <td className="py-2 pr-3 text-right font-mono">{Number(row.confidence || 0).toFixed(2)}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(Number(row.linkedFeatureCount || 0))}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatNumber(Number(row.totalTokens || 0))}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatCurrency(Number(row.totalCost || 0))}</td>
                                            <td className="py-2 pr-3 text-right font-mono">{formatDurationSeconds(Number(row.durationSeconds || 0))}</td>
                                            <td className="py-2 pr-3">{row.model ? <ModelBadge model={row.model} family={row.modelFamily} /> : <span className="text-slate-500">-</span>}</td>
                                            <td className="py-2 pr-3 text-xs">
                                                {row.modelFamily
                                                    ? <span className="inline-flex rounded border px-1.5 py-0.5" style={getBadgeStyleForModel({ family: row.modelFamily })}>{row.modelFamily}</span>
                                                    : '-'}
                                            </td>
                                            <td className="py-2 text-xs text-slate-400">{row.linkStrategy || '-'}</td>
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

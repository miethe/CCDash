import React, { useEffect, useState } from 'react';
import { TrendChart } from './TrendChart';
import { analyticsService } from '../../services/analytics';
import { AnalyticsMetric, Notification } from '../../types';
import { Download, Bell } from 'lucide-react';

export const AnalyticsDashboard: React.FC = () => {
    const [metrics, setMetrics] = useState<AnalyticsMetric[]>([]);
    const [notifications, setNotifications] = useState<Notification[]>([]);

    useEffect(() => {
        const loadOverview = async () => {
            try {
                const [m, n] = await Promise.all([
                    analyticsService.getMetrics(),
                    analyticsService.getNotifications()
                ]);
                setMetrics(m);
                setNotifications(n);
            } catch (e) {
                console.error("Failed to load analytics overview", e);
            }
        };
        loadOverview();
    }, []);

    const handleExport = () => {
        window.open(analyticsService.getPrometheusExportUrl(), '_blank');
    };

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
            <div className="flex justify-between items-end">
                <div>
                    <h2 className="text-3xl font-bold text-slate-100">Analytics & Trends</h2>
                    <p className="text-slate-400 mt-2">Historical data and long-term trends.</p>
                </div>
                <button
                    onClick={handleExport}
                    className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 px-4 py-2 rounded-lg text-sm font-medium transition-colors border border-slate-700"
                >
                    <Download size={16} />
                    Export Prometheus
                </button>
            </div>

            {/* Metrics Grid */}
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

            {/* Charts Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <TrendChart
                    metric="session_cost"
                    title="Session Cost"
                    color="#ef4444"
                    valueFormatter={(v) => `$${v.toFixed(2)}`}
                />
                <TrendChart
                    metric="session_tokens"
                    title="Tokens Used"
                    color="#3b82f6"
                    valueFormatter={(v) => v.toLocaleString()}
                />
                <TrendChart
                    metric="session_count"
                    title="Sessions"
                    color="#10b981"
                />
                <TrendChart
                    metric="task_completion_pct"
                    title="Task Completion %"
                    color="#f59e0b"
                    valueFormatter={(v) => `${v.toFixed(1)}%`}
                />
            </div>

            {/* Notifications / Alerts Preview */}
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
    );
};

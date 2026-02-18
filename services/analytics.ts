import { AnalyticsMetric, AnalyticsTrendPoint, AlertConfig, Notification } from '../types';

const API_BASE = 'http://localhost:8000/api/analytics';

export const analyticsService = {
    async getMetrics(): Promise<AnalyticsMetric[]> {
        const res = await fetch(`${API_BASE}/metrics`);
        if (!res.ok) throw new Error('Failed to fetch metrics');
        return res.json();
    },

    async getTrends(
        metric: string,
        period: string = 'daily',
        start?: string,
        end?: string
    ): Promise<AnalyticsTrendPoint[]> {
        const params = new URLSearchParams({ metric, period });
        if (start) params.append('start', start);
        if (end) params.append('end', end);

        const res = await fetch(`${API_BASE}/trends?${params.toString()}`);
        if (!res.ok) throw new Error('Failed to fetch trends');
        return res.json();
    },

    async getAlerts(): Promise<AlertConfig[]> {
        const res = await fetch(`${API_BASE}/alerts`);
        if (!res.ok) throw new Error('Failed to fetch alerts');
        return res.json();
    },

    async getNotifications(): Promise<Notification[]> {
        const res = await fetch(`${API_BASE}/notifications`);
        if (!res.ok) throw new Error('Failed to fetch notifications');
        return res.json();
    },

    getPrometheusExportUrl(): string {
        return `${API_BASE}/export/prometheus`;
    }
};

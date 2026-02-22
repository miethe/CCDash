import {
    AnalyticsMetric,
    AnalyticsTrendPoint,
    AlertConfig,
    Notification,
    AnalyticsOverview,
    AnalyticsBreakdownItem,
    AnalyticsCorrelationItem,
} from '../types';

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

    async getOverview(start?: string, end?: string): Promise<AnalyticsOverview> {
        const params = new URLSearchParams();
        if (start) params.append('start', start);
        if (end) params.append('end', end);
        const qs = params.toString();
        const res = await fetch(`${API_BASE}/overview${qs ? `?${qs}` : ''}`);
        if (!res.ok) throw new Error('Failed to fetch analytics overview');
        return res.json();
    },

    async getSeries(params: {
        metric: string;
        period?: 'point' | 'hourly' | 'daily' | 'weekly';
        start?: string;
        end?: string;
        groupBy?: string;
        sessionId?: string;
        offset?: number;
        limit?: number;
    }): Promise<{ items: AnalyticsTrendPoint[]; total: number; offset: number; limit: number }> {
        const search = new URLSearchParams({
            metric: params.metric,
            period: params.period || 'daily',
            offset: String(params.offset || 0),
            limit: String(params.limit || 500),
        });
        if (params.start) search.append('start', params.start);
        if (params.end) search.append('end', params.end);
        if (params.groupBy) search.append('group_by', params.groupBy);
        if (params.sessionId) search.append('session_id', params.sessionId);
        const res = await fetch(`${API_BASE}/series?${search.toString()}`);
        if (!res.ok) throw new Error('Failed to fetch analytics series');
        return res.json();
    },

    async getBreakdown(
        dimension: 'model' | 'model_family' | 'session_type' | 'tool' | 'agent' | 'skill' | 'feature' = 'model',
        start?: string,
        end?: string,
    ): Promise<{ items: AnalyticsBreakdownItem[]; total: number; offset: number; limit: number }> {
        const search = new URLSearchParams({ dimension });
        if (start) search.append('start', start);
        if (end) search.append('end', end);
        const res = await fetch(`${API_BASE}/breakdown?${search.toString()}`);
        if (!res.ok) throw new Error('Failed to fetch analytics breakdown');
        return res.json();
    },

    async getCorrelation(): Promise<{ items: AnalyticsCorrelationItem[]; total: number; offset: number; limit: number }> {
        const res = await fetch(`${API_BASE}/correlation`);
        if (!res.ok) throw new Error('Failed to fetch analytics correlation');
        return res.json();
    },

    async getAlerts(): Promise<AlertConfig[]> {
        const res = await fetch(`${API_BASE}/alerts`);
        if (!res.ok) throw new Error('Failed to fetch alerts');
        return res.json();
    },

    async createAlert(payload: Omit<AlertConfig, 'id'> & { id?: string }): Promise<AlertConfig> {
        const res = await fetch(`${API_BASE}/alerts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error('Failed to create alert');
        return res.json();
    },

    async updateAlert(alertId: string, payload: Partial<AlertConfig>): Promise<AlertConfig> {
        const res = await fetch(`${API_BASE}/alerts/${alertId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error('Failed to update alert');
        return res.json();
    },

    async deleteAlert(alertId: string): Promise<void> {
        const res = await fetch(`${API_BASE}/alerts/${alertId}`, {
            method: 'DELETE',
        });
        if (!res.ok) throw new Error('Failed to delete alert');
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

import {
    AnalyticsMetric,
    AnalyticsTrendPoint,
    AlertConfig,
    Notification,
    SessionIntelligenceDetailResponse,
    SessionIntelligenceDrilldownResponse,
    SessionIntelligenceListResponse,
    SessionIntelligenceConcern,
    SessionCostCalibrationSummary,
    AnalyticsOverview,
    AnalyticsBreakdownItem,
    AnalyticsCorrelationItem,
    AnalyticsArtifactsResponse,
    EffectivenessScopeType,
    FailurePatternResponse,
    SessionSemanticSearchResponse,
    SessionUsageAggregateResponse,
    SessionUsageCalibrationSummary,
    SessionUsageDrilldownResponse,
    WorkflowEffectivenessResponse,
} from '../types';
import { apiFetch } from './apiClient';
import { apiRequestJson } from './apiClient';

const API_BASE = '/api/analytics';

export class AnalyticsApiError extends Error {
    status: number;
    hint: string;
    code: string;

    constructor(message: string, status: number, hint = '', code = '') {
        super(message);
        this.name = 'AnalyticsApiError';
        this.status = status;
        this.hint = hint;
        this.code = code;
    }
}

const buildAnalyticsApiError = async (res: Response, fallbackMessage: string): Promise<AnalyticsApiError> => {
    let message = fallbackMessage;
    let hint = '';
    let code = '';
    const contentType = res.headers.get('content-type') || '';

    if (contentType.includes('application/json')) {
        const payload = await res.json().catch(() => null) as { detail?: unknown } | null;
        const detail = payload?.detail;
        if (typeof detail === 'string') {
            message = detail;
        } else if (detail && typeof detail === 'object') {
            const detailRecord = detail as Record<string, unknown>;
            if (typeof detailRecord.message === 'string' && detailRecord.message.trim()) {
                message = detailRecord.message;
            }
            if (typeof detailRecord.hint === 'string' && detailRecord.hint.trim()) {
                hint = detailRecord.hint;
            }
            if (typeof detailRecord.error === 'string' && detailRecord.error.trim()) {
                code = detailRecord.error;
            }
        }
    }

    if (res.status === 404 && !hint) {
        hint = 'Restart the backend so it loads the latest analytics routes.';
    }

    return new AnalyticsApiError(message, res.status, hint, code);
};

export const analyticsService = {
    async getMetrics(): Promise<AnalyticsMetric[]> {
        const res = await apiFetch(`${API_BASE}/metrics`);
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

        const res = await apiFetch(`${API_BASE}/trends?${params.toString()}`);
        if (!res.ok) throw new Error('Failed to fetch trends');
        return res.json();
    },

    async getOverview(start?: string, end?: string): Promise<AnalyticsOverview> {
        const params = new URLSearchParams();
        if (start) params.append('start', start);
        if (end) params.append('end', end);
        const qs = params.toString();
        const res = await apiFetch(`${API_BASE}/overview${qs ? `?${qs}` : ''}`);
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
        const res = await apiFetch(`${API_BASE}/series?${search.toString()}`);
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
        const res = await apiFetch(`${API_BASE}/breakdown?${search.toString()}`);
        if (!res.ok) throw new Error('Failed to fetch analytics breakdown');
        return res.json();
    },

    async getCorrelation(): Promise<{ items: AnalyticsCorrelationItem[]; total: number; offset: number; limit: number }> {
        const res = await apiFetch(`${API_BASE}/correlation`);
        if (!res.ok) throw new Error('Failed to fetch analytics correlation');
        return res.json();
    },

    async getArtifacts(params?: {
        start?: string;
        end?: string;
        artifactType?: string;
        model?: string;
        modelFamily?: string;
        tool?: string;
        featureId?: string;
        limit?: number;
    }): Promise<AnalyticsArtifactsResponse> {
        const search = new URLSearchParams();
        if (params?.start) search.append('start', params.start);
        if (params?.end) search.append('end', params.end);
        if (params?.artifactType) search.append('artifact_type', params.artifactType);
        if (params?.model) search.append('model', params.model);
        if (params?.modelFamily) search.append('model_family', params.modelFamily);
        if (params?.tool) search.append('tool', params.tool);
        if (params?.featureId) search.append('feature_id', params.featureId);
        if (params?.limit) search.append('limit', String(params.limit));
        const qs = search.toString();
        const res = await apiFetch(`${API_BASE}/artifacts${qs ? `?${qs}` : ''}`);
        if (!res.ok) throw new Error('Failed to fetch artifact analytics');
        return res.json();
    },

    async getUsageAttribution(params?: {
        start?: string;
        end?: string;
        entityType?: string;
        entityId?: string;
        offset?: number;
        limit?: number;
    }): Promise<SessionUsageAggregateResponse> {
        const search = new URLSearchParams();
        if (params?.start) search.append('start', params.start);
        if (params?.end) search.append('end', params.end);
        if (params?.entityType) search.append('entity_type', params.entityType);
        if (params?.entityId) search.append('entity_id', params.entityId);
        if (typeof params?.offset === 'number') search.append('offset', String(params.offset));
        if (typeof params?.limit === 'number') search.append('limit', String(params.limit));
        const qs = search.toString();
        const res = await apiFetch(`${API_BASE}/usage-attribution${qs ? `?${qs}` : ''}`);
        if (!res.ok) throw new Error('Failed to fetch usage attribution analytics');
        return res.json();
    },

    async getUsageAttributionDrilldown(params: {
        entityType: string;
        entityId: string;
        start?: string;
        end?: string;
        offset?: number;
        limit?: number;
    }): Promise<SessionUsageDrilldownResponse> {
        const search = new URLSearchParams({
            entity_type: params.entityType,
            entity_id: params.entityId,
        });
        if (params.start) search.append('start', params.start);
        if (params.end) search.append('end', params.end);
        if (typeof params.offset === 'number') search.append('offset', String(params.offset));
        if (typeof params.limit === 'number') search.append('limit', String(params.limit));
        const res = await apiFetch(`${API_BASE}/usage-attribution/drilldown?${search.toString()}`);
        if (!res.ok) throw new Error('Failed to fetch usage attribution drilldown');
        return res.json();
    },

    async getUsageAttributionCalibration(start?: string, end?: string): Promise<SessionUsageCalibrationSummary> {
        const search = new URLSearchParams();
        if (start) search.append('start', start);
        if (end) search.append('end', end);
        const qs = search.toString();
        const res = await apiFetch(`${API_BASE}/usage-attribution/calibration${qs ? `?${qs}` : ''}`);
        if (!res.ok) throw new Error('Failed to fetch usage attribution calibration');
        return res.json();
    },

    async getSessionCostCalibration(start?: string, end?: string): Promise<SessionCostCalibrationSummary> {
        const search = new URLSearchParams();
        if (start) search.append('start', start);
        if (end) search.append('end', end);
        const qs = search.toString();
        const res = await apiFetch(`${API_BASE}/session-cost-calibration${qs ? `?${qs}` : ''}`);
        if (!res.ok) throw new Error('Failed to fetch session cost calibration');
        return res.json();
    },

    async getWorkflowEffectiveness(params?: {
        period?: 'all' | 'daily' | 'weekly';
        scopeType?: EffectivenessScopeType;
        scopeId?: string;
        featureId?: string;
        start?: string;
        end?: string;
        recompute?: boolean;
        offset?: number;
        limit?: number;
    }): Promise<WorkflowEffectivenessResponse> {
        const search = new URLSearchParams();
        if (params?.period) search.append('period', params.period);
        if (params?.scopeType) search.append('scopeType', params.scopeType);
        if (params?.scopeId) search.append('scopeId', params.scopeId);
        if (params?.featureId) search.append('featureId', params.featureId);
        if (params?.start) search.append('start', params.start);
        if (params?.end) search.append('end', params.end);
        if (typeof params?.recompute === 'boolean') search.append('recompute', String(params.recompute));
        if (typeof params?.offset === 'number') search.append('offset', String(params.offset));
        if (typeof params?.limit === 'number') search.append('limit', String(params.limit));
        const qs = search.toString();
        const res = await apiFetch(`${API_BASE}/workflow-effectiveness${qs ? `?${qs}` : ''}`);
        if (!res.ok) throw await buildAnalyticsApiError(res, 'Failed to fetch workflow effectiveness');
        return res.json();
    },

    async getFailurePatterns(params?: {
        scopeType?: EffectivenessScopeType;
        scopeId?: string;
        featureId?: string;
        start?: string;
        end?: string;
        offset?: number;
        limit?: number;
    }): Promise<FailurePatternResponse> {
        const search = new URLSearchParams();
        if (params?.scopeType) search.append('scopeType', params.scopeType);
        if (params?.scopeId) search.append('scopeId', params.scopeId);
        if (params?.featureId) search.append('featureId', params.featureId);
        if (params?.start) search.append('start', params.start);
        if (params?.end) search.append('end', params.end);
        if (typeof params?.offset === 'number') search.append('offset', String(params.offset));
        if (typeof params?.limit === 'number') search.append('limit', String(params.limit));
        const qs = search.toString();
        const res = await apiFetch(`${API_BASE}/failure-patterns${qs ? `?${qs}` : ''}`);
        if (!res.ok) throw await buildAnalyticsApiError(res, 'Failed to fetch failure patterns');
        return res.json();
    },

    async searchSessionIntelligence(params: {
        query: string;
        featureId?: string;
        rootSessionId?: string;
        sessionId?: string;
        offset?: number;
        limit?: number;
    }): Promise<SessionSemanticSearchResponse> {
        const search = new URLSearchParams({
            query: params.query,
            offset: String(params.offset || 0),
            limit: String(params.limit || 25),
        });
        if (params.featureId) search.append('feature_id', params.featureId);
        if (params.rootSessionId) search.append('root_session_id', params.rootSessionId);
        if (params.sessionId) search.append('session_id', params.sessionId);
        const res = await apiFetch(`${API_BASE}/session-intelligence/search?${search.toString()}`);
        if (!res.ok) throw await buildAnalyticsApiError(res, 'Failed to fetch transcript intelligence search');
        return res.json();
    },

    async getSessionIntelligence(params?: {
        featureId?: string;
        rootSessionId?: string;
        sessionId?: string;
        offset?: number;
        limit?: number;
    }): Promise<SessionIntelligenceListResponse> {
        const search = new URLSearchParams({
            offset: String(params?.offset || 0),
            limit: String(params?.limit || 50),
        });
        if (params?.featureId) search.append('feature_id', params.featureId);
        if (params?.rootSessionId) search.append('root_session_id', params.rootSessionId);
        if (params?.sessionId) search.append('session_id', params.sessionId);
        const res = await apiFetch(`${API_BASE}/session-intelligence?${search.toString()}`);
        if (!res.ok) throw await buildAnalyticsApiError(res, 'Failed to fetch session intelligence rollups');
        return res.json();
    },

    async getSessionIntelligenceDetail(sessionId: string): Promise<SessionIntelligenceDetailResponse> {
        const search = new URLSearchParams({ session_id: sessionId });
        const res = await apiFetch(`${API_BASE}/session-intelligence/detail?${search.toString()}`);
        if (!res.ok) throw await buildAnalyticsApiError(res, 'Failed to fetch session intelligence detail');
        return res.json();
    },

    async getSessionIntelligenceDrilldown(params: {
        concern: SessionIntelligenceConcern;
        featureId?: string;
        rootSessionId?: string;
        sessionId?: string;
        offset?: number;
        limit?: number;
    }): Promise<SessionIntelligenceDrilldownResponse> {
        const search = new URLSearchParams({
            concern: params.concern,
            offset: String(params.offset || 0),
            limit: String(params.limit || 50),
        });
        if (params.featureId) search.append('feature_id', params.featureId);
        if (params.rootSessionId) search.append('root_session_id', params.rootSessionId);
        if (params.sessionId) search.append('session_id', params.sessionId);
        const res = await apiFetch(`${API_BASE}/session-intelligence/drilldown?${search.toString()}`);
        if (!res.ok) throw await buildAnalyticsApiError(res, 'Failed to fetch session intelligence drilldown');
        return res.json();
    },

    async getAlerts(): Promise<AlertConfig[]> {
        const res = await apiFetch(`${API_BASE}/alerts`);
        if (!res.ok) throw new Error('Failed to fetch alerts');
        return res.json();
    },

    async createAlert(payload: Omit<AlertConfig, 'id'> & { id?: string }): Promise<AlertConfig> {
        return apiRequestJson<AlertConfig>(`${API_BASE}/alerts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
    },

    async updateAlert(alertId: string, payload: Partial<AlertConfig>): Promise<AlertConfig> {
        return apiRequestJson<AlertConfig>(`${API_BASE}/alerts/${alertId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
    },

    async deleteAlert(alertId: string): Promise<void> {
        await apiRequestJson<void>(`${API_BASE}/alerts/${alertId}`, {
            method: 'DELETE',
        });
    },

    async getNotifications(): Promise<Notification[]> {
        const res = await apiFetch(`${API_BASE}/notifications`);
        if (!res.ok) throw new Error('Failed to fetch notifications');
        return res.json();
    },

    getPrometheusExportUrl(): string {
        return `${API_BASE}/export/prometheus`;
    }
};

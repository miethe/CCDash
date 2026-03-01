import {
  CorrelatedTestRun,
  DomainHealthRollup,
  FeatureTestHealth,
  FeatureTestTimeline,
  TestMetricSummary,
  TestPlatformId,
  TestSourceStatus,
  TestSyncResponse,
  TestIntegritySignal,
  TestRun,
  TestVisualizerConfig,
  TestRunDetail,
  TestResult,
} from '../types';

const API_BASE = '/api/tests';

export interface TestRunsFilter {
  projectId: string;
  agentSessionId?: string;
  featureId?: string;
  gitSha?: string;
  since?: string;
  cursor?: string;
  limit?: number;
}

export interface CursorPage<T> {
  items: T[];
  nextCursor: string | null;
  total: number;
}

interface RequestOptions {
  emptyOn503?: unknown;
}

type JsonRecord = Record<string, unknown>;

export class TestVisualizerApiError extends Error {
  status: number;
  code: string;
  hint: string;

  constructor(message: string, status: number, code = '', hint = '') {
    super(message);
    this.name = 'TestVisualizerApiError';
    this.status = status;
    this.code = code;
    this.hint = hint;
  }

  get isFeatureDisabled(): boolean {
    return this.status === 503 && this.code === 'feature_disabled';
  }
}

const toCamelKey = (key: string): string => key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());

const toCamelValue = <T>(value: unknown): T => {
  if (Array.isArray(value)) {
    return value.map(item => toCamelValue(item)) as T;
  }
  if (value && typeof value === 'object') {
    const output: JsonRecord = {};
    Object.entries(value as JsonRecord).forEach(([key, item]) => {
      output[toCamelKey(key)] = toCamelValue(item);
    });
    return output as T;
  }
  return value as T;
};

const resolveErrorMessage = (payload: unknown, fallback: string): string => {
  const asRecord = payload as JsonRecord | null;
  const detail = (asRecord?.detail || null) as JsonRecord | string | null;

  if (typeof asRecord?.message === 'string' && asRecord.message.trim()) {
    return asRecord.message;
  }
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  if (detail && typeof detail === 'object' && typeof detail.message === 'string' && detail.message.trim()) {
    return detail.message;
  }
  return fallback;
};

async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  let payload: unknown = null;

  try {
    payload = await res.json();
  } catch {
    payload = null;
  }

  if (!res.ok) {
    const asRecord = payload as JsonRecord | null;
    const detail = (asRecord?.detail || null) as JsonRecord | string | null;
    const detailRecord = detail && typeof detail === 'object' ? detail as JsonRecord : null;
    const code = typeof detailRecord?.error === 'string' ? detailRecord.error : '';
    const hint = typeof detailRecord?.hint === 'string' ? detailRecord.hint : '';
    if (res.status === 503 && options.emptyOn503 !== undefined && code !== 'feature_disabled') {
      return options.emptyOn503 as T;
    }
    throw new TestVisualizerApiError(
      resolveErrorMessage(payload, `Request failed (${res.status})`),
      res.status,
      code,
      hint,
    );
  }

  return toCamelValue<T>(payload);
}

const buildQuery = (params: Record<string, string | number | boolean | null | undefined>): string => {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return;
    }
    query.append(key, String(value));
  });
  const serialized = query.toString();
  return serialized ? `?${serialized}` : '';
};

export async function getDomainHealth(projectId: string, since?: string): Promise<DomainHealthRollup[]> {
  const query = buildQuery({ project_id: projectId, since });
  return requestJson<DomainHealthRollup[]>(`/health/domains${query}`);
}

export async function getFeatureHealth(
  projectId: string,
  options?: { featureId?: string; domainId?: string; since?: string; cursor?: string; limit?: number }
): Promise<CursorPage<FeatureTestHealth>> {
  const query = buildQuery({
    project_id: projectId,
    feature_id: options?.featureId,
    domain_id: options?.domainId,
    since: options?.since,
    cursor: options?.cursor,
    limit: options?.limit,
  });
  return requestJson<CursorPage<FeatureTestHealth>>(`/health/features${query}`);
}

export async function getTestRun(runId: string, projectId: string): Promise<TestRunDetail | null> {
  const query = buildQuery({ project_id: projectId });
  return requestJson<TestRunDetail | null>(`/runs/${encodeURIComponent(runId)}${query}`);
}

export async function listTestRuns(filter: TestRunsFilter): Promise<CursorPage<TestRun>> {
  const query = buildQuery({
    project_id: filter.projectId,
    agent_session_id: filter.agentSessionId,
    feature_id: filter.featureId,
    git_sha: filter.gitSha,
    since: filter.since,
    cursor: filter.cursor,
    limit: filter.limit,
  });
  return requestJson<CursorPage<TestRun>>(`/runs${query}`);
}

export async function getTestHistory(
  testId: string,
  projectId: string,
  options?: { limit?: number; since?: string; cursor?: string }
): Promise<CursorPage<TestResult>> {
  const query = buildQuery({
    project_id: projectId,
    limit: options?.limit,
    since: options?.since,
    cursor: options?.cursor,
  });
  return requestJson<CursorPage<TestResult>>(`/${encodeURIComponent(testId)}/history${query}`);
}

export async function getFeatureTimeline(
  featureId: string,
  projectId: string,
  options?: { since?: string; until?: string; includeSignals?: boolean }
): Promise<FeatureTestTimeline | null> {
  const query = buildQuery({
    project_id: projectId,
    since: options?.since,
    until: options?.until,
    include_signals: options?.includeSignals,
  });
  return requestJson<FeatureTestTimeline | null>(`/features/${encodeURIComponent(featureId)}/timeline${query}`);
}

export async function getIntegrityAlerts(
  projectId: string,
  options?: {
    since?: string;
    signalType?: string;
    severity?: string;
    agentSessionId?: string;
    cursor?: string;
    limit?: number;
  }
): Promise<CursorPage<TestIntegritySignal>> {
  const query = buildQuery({
    project_id: projectId,
    since: options?.since,
    signal_type: options?.signalType,
    severity: options?.severity,
    agent_session_id: options?.agentSessionId,
    cursor: options?.cursor,
    limit: options?.limit,
  });
  return requestJson<CursorPage<TestIntegritySignal>>(`/integrity/alerts${query}`);
}

export async function correlateRun(runId: string, projectId: string): Promise<CorrelatedTestRun | null> {
  const query = buildQuery({ run_id: runId, project_id: projectId });
  return requestJson<CorrelatedTestRun | null>(`/correlate${query}`);
}

export async function getTestVisualizerConfig(projectId: string): Promise<TestVisualizerConfig> {
  const query = buildQuery({ project_id: projectId });
  return requestJson<TestVisualizerConfig>(`/config${query}`);
}

export async function getTestSourcesStatus(projectId: string): Promise<TestSourceStatus[]> {
  const query = buildQuery({ project_id: projectId });
  return requestJson<TestSourceStatus[]>(`/sources/status${query}`);
}

export async function syncTestSources(
  projectId: string,
  options?: { platforms?: TestPlatformId[]; force?: boolean }
): Promise<TestSyncResponse> {
  const res = await fetch(`${API_BASE}/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      project_id: projectId,
      platforms: options?.platforms || [],
      force: Boolean(options?.force),
    }),
  });

  let payload: unknown = null;
  try {
    payload = await res.json();
  } catch {
    payload = null;
  }

  if (!res.ok) {
    const asRecord = payload as JsonRecord | null;
    const detail = (asRecord?.detail || null) as JsonRecord | string | null;
    const detailRecord = detail && typeof detail === 'object' ? detail as JsonRecord : null;
    throw new TestVisualizerApiError(
      resolveErrorMessage(payload, `Request failed (${res.status})`),
      res.status,
      typeof detailRecord?.error === 'string' ? detailRecord.error : '',
      typeof detailRecord?.hint === 'string' ? detailRecord.hint : '',
    );
  }
  return toCamelValue<TestSyncResponse>(payload);
}

export async function getTestMetricsSummary(projectId: string): Promise<TestMetricSummary> {
  const query = buildQuery({ project_id: projectId });
  return requestJson<TestMetricSummary>(`/metrics/summary${query}`, {
    emptyOn503: {
      projectId,
      totalMetrics: 0,
      byPlatform: {},
      byMetricType: {},
      latestCollectedAt: '',
    },
  });
}

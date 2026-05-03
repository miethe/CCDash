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
  TestDefinition,
  TestResult,
} from '../types';
import { apiFetch } from './apiClient';

const API_BASE = '/api/tests';

export interface TestRunsFilter {
  projectId: string;
  agentSessionId?: string;
  featureId?: string;
  domainId?: string;
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

export interface RunResultPage {
  items: TestResult[];
  total: number;
  limit: number;
  nextCursor: string | null;
  definitions: Record<string, TestDefinition>;
}

interface RequestOptions {
  emptyOn503?: unknown;
}

type JsonRecord = Record<string, unknown>;
type CacheScope = 'domainHealth' | 'featureHealth' | 'testRuns' | 'runResults';
type CacheOutcome = 'hit' | 'stale' | 'miss' | 'inflight' | 'revalidateSuccess' | 'revalidateError' | 'missError';

interface CacheEntry<T> {
  value?: T;
  fetchedAt: number;
  staleAt: number;
  expiresAt: number;
  inFlight?: Promise<T>;
}

interface CachePolicy {
  scope: CacheScope;
  freshMs: number;
  staleMs: number;
  lruLimit?: number;
}

interface ProjectCacheStore {
  domainHealth: Map<string, CacheEntry<DomainHealthRollup[]>>;
  featureHealth: Map<string, CacheEntry<CursorPage<FeatureTestHealth>>>;
  testRuns: Map<string, CacheEntry<CursorPage<TestRun>>>;
  runResults: Map<string, CacheEntry<RunResultPage>>;
}

type CacheStats = Record<CacheScope, Record<CacheOutcome, number>>;

export interface TestVisualizerCacheStatsSnapshot {
  stats: CacheStats;
  projectsCached: number;
}

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
  const res = await apiFetch(`${API_BASE}${path}`);
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

const DEFAULT_FRESH_MS = 30_000;
const DEFAULT_STALE_MS = 120_000;
const RUN_RESULTS_FRESH_MS = 45_000;
const RUN_RESULTS_STALE_MS = 240_000;
const RUN_RESULTS_LRU_LIMIT = 60;
const PROJECT_CACHE = new Map<string, ProjectCacheStore>();
const CACHE_SCOPES: CacheScope[] = ['domainHealth', 'featureHealth', 'testRuns', 'runResults'];
const CACHE_OUTCOMES: CacheOutcome[] = ['hit', 'stale', 'miss', 'inflight', 'revalidateSuccess', 'revalidateError', 'missError'];
const IS_DEV = typeof window !== 'undefined'
  && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

const DOMAIN_HEALTH_CACHE_POLICY: CachePolicy = {
  scope: 'domainHealth',
  freshMs: DEFAULT_FRESH_MS,
  staleMs: DEFAULT_STALE_MS,
};

const FEATURE_HEALTH_CACHE_POLICY: CachePolicy = {
  scope: 'featureHealth',
  freshMs: DEFAULT_FRESH_MS,
  staleMs: DEFAULT_STALE_MS,
};

const TEST_RUNS_CACHE_POLICY: CachePolicy = {
  scope: 'testRuns',
  freshMs: DEFAULT_FRESH_MS,
  staleMs: DEFAULT_STALE_MS,
};

const RUN_RESULTS_CACHE_POLICY: CachePolicy = {
  scope: 'runResults',
  freshMs: RUN_RESULTS_FRESH_MS,
  staleMs: RUN_RESULTS_STALE_MS,
  lruLimit: RUN_RESULTS_LRU_LIMIT,
};

const CACHE_STATS: CacheStats = CACHE_SCOPES.reduce(
  (acc, scope) => {
    acc[scope] = CACHE_OUTCOMES.reduce((outcomeAcc, outcome) => {
      outcomeAcc[outcome] = 0;
      return outcomeAcc;
    }, {} as Record<CacheOutcome, number>);
    return acc;
  },
  {} as CacheStats,
);

const createProjectCacheStore = (): ProjectCacheStore => ({
  domainHealth: new Map<string, CacheEntry<DomainHealthRollup[]>>(),
  featureHealth: new Map<string, CacheEntry<CursorPage<FeatureTestHealth>>>(),
  testRuns: new Map<string, CacheEntry<CursorPage<TestRun>>>(),
  runResults: new Map<string, CacheEntry<RunResultPage>>(),
});

const getProjectCacheStore = (projectId: string): ProjectCacheStore => {
  const existing = PROJECT_CACHE.get(projectId);
  if (existing) {
    return existing;
  }
  const created = createProjectCacheStore();
  PROJECT_CACHE.set(projectId, created);
  return created;
};

const noteCacheEvent = (scope: CacheScope, outcome: CacheOutcome, projectId: string): void => {
  CACHE_STATS[scope][outcome] += 1;
  if (!IS_DEV) {
    return;
  }
  if (outcome === 'hit' || outcome === 'stale' || outcome === 'miss') {
    console.debug('[test-visualizer-cache]', `${scope}:${outcome}`, { projectId });
  }
};

const touchCacheKey = <T>(
  bucket: Map<string, CacheEntry<T>>,
  key: string,
  lruLimit: number | undefined,
): void => {
  const entry = bucket.get(key);
  if (!entry) {
    return;
  }
  bucket.delete(key);
  bucket.set(key, entry);
  if (lruLimit === undefined) {
    return;
  }
  while (bucket.size > lruLimit) {
    const oldestKey = bucket.keys().next().value as string | undefined;
    if (!oldestKey) {
      break;
    }
    bucket.delete(oldestKey);
  }
};

async function readThroughProjectCache<T>(
  projectId: string,
  key: string,
  bucket: Map<string, CacheEntry<T>>,
  policy: CachePolicy,
  loader: () => Promise<T>,
): Promise<T> {
  const now = Date.now();
  const existing = bucket.get(key);

  const startFetch = (mode: 'miss' | 'revalidate', previous?: CacheEntry<T>): Promise<T> => {
    const current = bucket.get(key);
    if (current?.inFlight) {
      noteCacheEvent(policy.scope, 'inflight', projectId);
      return current.inFlight;
    }

    const pending = loader()
      .then(value => {
        const fetchedAt = Date.now();
        bucket.set(key, {
          value,
          fetchedAt,
          staleAt: fetchedAt + policy.freshMs,
          expiresAt: fetchedAt + policy.freshMs + policy.staleMs,
        });
        touchCacheKey(bucket, key, policy.lruLimit);
        noteCacheEvent(policy.scope, mode === 'miss' ? 'miss' : 'revalidateSuccess', projectId);
        return value;
      })
      .catch(error => {
        if (mode === 'revalidate' && previous?.value !== undefined) {
          noteCacheEvent(policy.scope, 'revalidateError', projectId);
          return previous.value;
        }
        noteCacheEvent(policy.scope, 'missError', projectId);
        throw error;
      })
      .finally(() => {
        const latest = bucket.get(key);
        if (!latest || latest.inFlight !== pending) {
          return;
        }
        if (latest.value === undefined) {
          bucket.delete(key);
          return;
        }
        latest.inFlight = undefined;
        bucket.set(key, latest);
        touchCacheKey(bucket, key, policy.lruLimit);
      });

    bucket.set(key, {
      value: previous?.value,
      fetchedAt: previous?.fetchedAt ?? 0,
      staleAt: previous?.staleAt ?? 0,
      expiresAt: previous?.expiresAt ?? 0,
      inFlight: pending,
    });
    touchCacheKey(bucket, key, policy.lruLimit);
    return pending;
  };

  if (existing?.value !== undefined) {
    if (existing.staleAt > now) {
      touchCacheKey(bucket, key, policy.lruLimit);
      noteCacheEvent(policy.scope, 'hit', projectId);
      return existing.value;
    }
    if (existing.expiresAt > now) {
      touchCacheKey(bucket, key, policy.lruLimit);
      noteCacheEvent(policy.scope, 'stale', projectId);
      void startFetch('revalidate', existing);
      return existing.value;
    }
  }

  if (existing?.inFlight) {
    touchCacheKey(bucket, key, policy.lruLimit);
    noteCacheEvent(policy.scope, 'inflight', projectId);
    return existing.inFlight;
  }

  return startFetch('miss', existing);
}

export function invalidateTestVisualizerProjectCache(projectId?: string, reason = 'manual'): void {
  if (projectId && projectId.trim()) {
    PROJECT_CACHE.delete(projectId);
    if (IS_DEV) {
      console.debug('[test-visualizer-cache]', 'invalidate:project', { projectId, reason });
    }
    return;
  }
  PROJECT_CACHE.clear();
  if (IS_DEV) {
    console.debug('[test-visualizer-cache]', 'invalidate:all', { reason });
  }
}

export function getTestVisualizerCacheStats(): TestVisualizerCacheStatsSnapshot {
  const stats = CACHE_SCOPES.reduce(
    (scopeAcc, scope) => {
      scopeAcc[scope] = CACHE_OUTCOMES.reduce((outcomeAcc, outcome) => {
        outcomeAcc[outcome] = CACHE_STATS[scope][outcome];
        return outcomeAcc;
      }, {} as Record<CacheOutcome, number>);
      return scopeAcc;
    },
    {} as CacheStats,
  );
  return {
    stats,
    projectsCached: PROJECT_CACHE.size,
  };
}

export async function getDomainHealth(projectId: string, since?: string): Promise<DomainHealthRollup[]> {
  const query = buildQuery({ project_id: projectId, since });
  const path = `/health/domains${query}`;
  const projectCache = getProjectCacheStore(projectId);
  return readThroughProjectCache(
    projectId,
    path,
    projectCache.domainHealth,
    DOMAIN_HEALTH_CACHE_POLICY,
    () => requestJson<DomainHealthRollup[]>(path),
  );
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
  const path = `/health/features${query}`;
  const projectCache = getProjectCacheStore(projectId);
  return readThroughProjectCache(
    projectId,
    path,
    projectCache.featureHealth,
    FEATURE_HEALTH_CACHE_POLICY,
    () => requestJson<CursorPage<FeatureTestHealth>>(path),
  );
}

export async function getTestRun(
  runId: string,
  projectId: string,
  options?: { includeResults?: boolean }
): Promise<TestRunDetail | null> {
  const query = buildQuery({ project_id: projectId, include_results: options?.includeResults });
  return requestJson<TestRunDetail | null>(`/runs/${encodeURIComponent(runId)}${query}`);
}

export async function listRunResults(options: {
  runId: string;
  projectId: string;
  domainId?: string;
  statuses?: string[];
  query?: string;
  sortBy?: 'status' | 'duration' | 'name' | 'test_id';
  sortOrder?: 'asc' | 'desc';
  cursor?: string;
  limit?: number;
}): Promise<RunResultPage> {
  const query = buildQuery({
    project_id: options.projectId,
    domain_id: options.domainId,
    statuses: (options.statuses || []).join(','),
    query: options.query,
    sort_by: options.sortBy,
    sort_order: options.sortOrder,
    cursor: options.cursor,
    limit: options.limit,
  });
  const path = `/runs/${encodeURIComponent(options.runId)}/results${query}`;
  const projectCache = getProjectCacheStore(options.projectId);
  return readThroughProjectCache(
    options.projectId,
    path,
    projectCache.runResults,
    RUN_RESULTS_CACHE_POLICY,
    () => requestJson<RunResultPage>(path),
  );
}

export async function listTestRuns(filter: TestRunsFilter): Promise<CursorPage<TestRun>> {
  const query = buildQuery({
    project_id: filter.projectId,
    agent_session_id: filter.agentSessionId,
    feature_id: filter.featureId,
    domain_id: filter.domainId,
    git_sha: filter.gitSha,
    since: filter.since,
    cursor: filter.cursor,
    limit: filter.limit,
  });
  const path = `/runs${query}`;
  const projectCache = getProjectCacheStore(filter.projectId);
  return readThroughProjectCache(
    filter.projectId,
    path,
    projectCache.testRuns,
    TEST_RUNS_CACHE_POLICY,
    () => requestJson<CursorPage<TestRun>>(path),
  );
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
  const res = await apiFetch(`${API_BASE}/sync`, {
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
  const response = toCamelValue<TestSyncResponse>(payload);
  invalidateTestVisualizerProjectCache(projectId, 'sync_test_sources');
  return response;
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

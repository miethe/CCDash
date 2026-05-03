import type {
  AgentSession,
  AlertConfig,
  Feature,
  AuthErrorClassification,
  AuthLoginStartResponse,
  AuthLogoutResponse,
  AuthProviderMetadataResponse,
  AuthSessionResponse,
  Notification,
  PlanDocument,
  Project,
  ProjectTask,
  TaskStatus,
  TelemetryExportSettingsUpdateRequest,
  TelemetryExportStatus,
  TelemetryPushNowResponse,
} from '../types';
import type { PaginatedResponse, SessionFilters } from '../contexts/dataContextShared';
import { buildApiUrl } from './runtimeBase';

export interface RuntimeHealthResponse {
  status: string;
  db: string;
  watcher: string;
  profile?: string;
  schemaVersion?: string;
  probeReadyState?: string;
  probeReadyStatus?: string;
  probeDegraded?: boolean;
  degradedReasonCodes?: string[];
  degradedReasons?: RuntimeProbeReasonResponse[];
  probeContract?: RuntimeProbeContractResponse;
  startupSync?: string;
  analyticsSnapshots?: string;
  telemetryExports?: string;
  jobsEnabled?: boolean;
  storageMode?: string;
  storageProfile?: string;
  storageBackend?: string;
  recommendedStorageProfile?: string;
  supportedStorageProfiles?: string[];
  filesystemSourceOfTruth?: boolean;
  sharedPostgresEnabled?: boolean;
  storageIsolationMode?: string;
  supportedStorageIsolationModes?: string[];
  storageCanonicalStore?: string;
  storageSchema?: string;
  canonicalSessionStore?: string;
  /** Feature-surface v2 data path rollout toggle. Defaults to true when absent. */
  featureSurfaceV2Enabled?: boolean;
}

export interface RuntimeProbeReasonResponse {
  code?: string;
  category?: string;
  severity?: string;
  message?: string;
  detail?: string;
  source?: string;
}

export interface RuntimeProbeActivityResponse {
  name?: string;
  state?: string;
  status?: string;
  detail?: string;
  code?: string;
  severity?: string;
}

export interface RuntimeProbeSectionResponse {
  state?: string;
  status?: string;
  summary?: string;
  detail?: string;
  reasons?: RuntimeProbeReasonResponse[];
  activities?: RuntimeProbeActivityResponse[];
}

export interface RuntimeProbeContractResponse {
  schemaVersion?: string;
  live?: RuntimeProbeSectionResponse;
  ready?: RuntimeProbeSectionResponse;
  detail?: RuntimeProbeSectionResponse;
  probeReadyState?: string;
  probeReadyStatus?: string;
  probeDegraded?: boolean;
  degradedReasons?: RuntimeProbeReasonResponse[];
  degradedReasonCodes?: string[];
}

export interface ApiClient {
  getAuthMetadata(): Promise<AuthProviderMetadataResponse>;
  getAuthSession(): Promise<AuthSessionResponse>;
  login(options?: AuthLoginOptions): Promise<AuthLoginStartResponse>;
  logout(): Promise<AuthLogoutResponse>;
  getHealth(): Promise<RuntimeHealthResponse>;
  getSessions(filters: SessionFilters, options?: { offset?: number; limit?: number }): Promise<PaginatedResponse<AgentSession>>;
  getSession(sessionId: string): Promise<AgentSession>;
  getDocuments(offset: number, limit: number): Promise<PaginatedResponse<PlanDocument> | PlanDocument[]>;
  getTasks(): Promise<PaginatedResponse<ProjectTask> | ProjectTask[]>;
  getAlerts(): Promise<AlertConfig[]>;
  getNotifications(): Promise<Notification[]>;
  getFeatures(): Promise<PaginatedResponse<Feature> | Feature[]>;
  getProjects(): Promise<Project[]>;
  getActiveProject(): Promise<Project>;
  addProject(project: Project): Promise<void>;
  updateProject(projectId: string, project: Project): Promise<void>;
  switchProject(projectId: string): Promise<void>;
  updateFeatureStatus(featureId: string, status: string): Promise<Feature>;
  updatePhaseStatus(featureId: string, phaseId: string, status: string): Promise<Feature>;
  updateTaskStatus(featureId: string, phaseId: string, taskId: string, status: TaskStatus): Promise<Feature>;
  getTelemetryExportStatus(): Promise<TelemetryExportStatus>;
  updateTelemetryExportSettings(update: TelemetryExportSettingsUpdateRequest): Promise<TelemetryExportStatus>;
  triggerTelemetryPushNow(): Promise<TelemetryPushNowResponse>;
}

export interface AuthLoginOptions {
  redirectTo?: string;
  redirect?: boolean;
}

export class ApiError extends Error {
  readonly status: number;
  readonly url: string;
  readonly detail: unknown;
  readonly authClassification: AuthErrorClassification;

  constructor({ status, statusText, url, detail }: { status: number; statusText: string; url: string; detail: unknown }) {
    super(`API error: ${status} ${statusText} for ${url}`);
    this.name = 'ApiError';
    this.status = status;
    this.url = url;
    this.detail = detail;
    this.authClassification = classifyAuthErrorStatus(status);
  }
}

export function classifyAuthErrorStatus(status: number): AuthErrorClassification {
  if (status === 401) return 'unauthenticated';
  if (status === 403) return 'unauthorized';
  return null;
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export async function readApiErrorDetail(res: Response): Promise<unknown> {
  const text = await res.text().catch(() => '');
  if (!text) {
    return res.statusText;
  }
  try {
    const parsed = JSON.parse(text) as unknown;
    if (parsed && typeof parsed === 'object' && 'detail' in parsed) {
      return (parsed as { detail: unknown }).detail;
    }
    return parsed;
  } catch {
    return text;
  }
}

const normalizeApiPath = (path: string): string => {
  if (path === '/api') return '';
  if (path.startsWith('/api/')) return path.slice('/api'.length);
  return path;
};

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const url = buildApiUrl(normalizeApiPath(path));
  const requestInit: RequestInit = {
    ...init,
    credentials: init?.credentials ?? 'same-origin',
  };
  return fetch(url, requestInit);
}

export async function createApiErrorFromResponse(res: Response, url: string): Promise<ApiError> {
  return new ApiError({
    status: res.status,
    statusText: res.statusText,
    url,
    detail: await readApiErrorDetail(res),
  });
}

export async function apiRequestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = buildApiUrl(normalizeApiPath(path));
  const res = await apiFetch(path, init);
  if (!res.ok) {
    throw await createApiErrorFromResponse(res, url);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  const text = await res.text();
  if (!text) {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

const requestJson = apiRequestJson;

function appendSessionFilters(params: URLSearchParams, filters: SessionFilters): void {
  const scalarKeys: Array<keyof SessionFilters> = [
    'status',
    'thread_kind',
    'conversation_family_id',
    'model',
    'model_provider',
    'model_family',
    'model_version',
    'platform_type',
    'platform_version',
    'root_session_id',
    'start_date',
    'end_date',
    'created_start',
    'created_end',
    'completed_start',
    'completed_end',
    'updated_start',
    'updated_end',
  ];

  scalarKeys.forEach((key) => {
    const value = filters[key];
    if (typeof value === 'string' && value) {
      params.append(key, value);
    }
  });

  if (filters.include_subagents) params.append('include_subagents', 'true');
  if (typeof filters.min_duration === 'number') params.append('min_duration', filters.min_duration.toString());
  if (typeof filters.max_duration === 'number') params.append('max_duration', filters.max_duration.toString());
}

export function createApiClient(): ApiClient {
  return {
    async getAuthMetadata() {
      return requestJson<AuthProviderMetadataResponse>('/auth/metadata');
    },

    async getAuthSession() {
      return requestJson<AuthSessionResponse>('/auth/session');
    },

    async login(options = {}) {
      const params = new URLSearchParams({
        redirect: String(options.redirect ?? false),
      });
      if (options.redirectTo) {
        params.set('redirectTo', options.redirectTo);
      }
      return requestJson<AuthLoginStartResponse>(`/auth/login/start?${params.toString()}`);
    },

    async logout() {
      return requestJson<AuthLogoutResponse>('/auth/logout', {
        method: 'POST',
      });
    },

    async getHealth() {
      return requestJson<RuntimeHealthResponse>('/health');
    },

    async getSessions(filters, options = {}) {
      const params = new URLSearchParams({
        offset: String(options.offset ?? 0),
        limit: String(options.limit ?? 50),
        sort_by: 'started_at',
        sort_order: 'desc',
      });
      appendSessionFilters(params, filters);
      return requestJson<PaginatedResponse<AgentSession>>(`/sessions?${params.toString()}`);
    },

    async getSession(sessionId) {
      return requestJson<AgentSession>(`/sessions/${sessionId}`);
    },

    async getDocuments(offset, limit) {
      return requestJson<PaginatedResponse<PlanDocument> | PlanDocument[]>(`/documents?offset=${offset}&limit=${limit}&include_progress=true`);
    },

    async getTasks() {
      return requestJson<PaginatedResponse<ProjectTask> | ProjectTask[]>('/tasks?offset=0&limit=5000');
    },

    async getAlerts() {
      return requestJson<AlertConfig[]>('/analytics/alerts');
    },

    async getNotifications() {
      return requestJson<Notification[]>('/analytics/notifications');
    },

    async getFeatures() {
      return requestJson<PaginatedResponse<Feature> | Feature[]>('/features?offset=0&limit=5000');
    },

    async getProjects() {
      return requestJson<Project[]>('/projects');
    },

    async getActiveProject() {
      return requestJson<Project>('/projects/active');
    },

    async addProject(project) {
      await requestJson<Project>('/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(project),
      });
    },

    async updateProject(projectId, project) {
      await requestJson<Project>(`/projects/${projectId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(project),
      });
    },

    async switchProject(projectId) {
      await requestJson<Project>(`/projects/active/${projectId}`, {
        method: 'POST',
      });
    },

    // Encode featureId to handle RFC 3986 § 2.2 reserved characters (e.g. #, ?, &, +, space) in path segments.
    async updateFeatureStatus(featureId, status) {
      return requestJson<Feature>(`/features/${encodeURIComponent(featureId)}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
    },

    // Encode featureId and phaseId to handle RFC 3986 § 2.2 reserved characters in path segments.
    async updatePhaseStatus(featureId, phaseId, status) {
      return requestJson<Feature>(`/features/${encodeURIComponent(featureId)}/phases/${encodeURIComponent(phaseId)}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
    },

    // Encode featureId, phaseId, and taskId to handle RFC 3986 § 2.2 reserved characters in path segments.
    async updateTaskStatus(featureId, phaseId, taskId, status) {
      return requestJson<Feature>(`/features/${encodeURIComponent(featureId)}/phases/${encodeURIComponent(phaseId)}/tasks/${encodeURIComponent(taskId)}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
    },

    async getTelemetryExportStatus() {
      return requestJson<TelemetryExportStatus>('/telemetry/export/status');
    },

    async updateTelemetryExportSettings(update) {
      return requestJson<TelemetryExportStatus>('/telemetry/export/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(update),
      });
    },

    async triggerTelemetryPushNow() {
      return requestJson<TelemetryPushNowResponse>('/telemetry/export/push-now', {
        method: 'POST',
      });
    },
  };
}

import {
  WorkflowRegistryCorrelationState,
  WorkflowRegistryDetailResponse,
  WorkflowRegistryListResponse,
} from '../types';
import { apiFetch } from './apiClient';

const API_BASE = '/api/analytics';

export class WorkflowRegistryApiError extends Error {
  status: number;
  hint: string;
  code: string;

  constructor(message: string, status: number, hint = '', code = '') {
    super(message);
    this.name = 'WorkflowRegistryApiError';
    this.status = status;
    this.hint = hint;
    this.code = code;
  }
}

const buildWorkflowRegistryApiError = async (
  res: Response,
  fallbackMessage: string,
): Promise<WorkflowRegistryApiError> => {
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
      const record = detail as Record<string, unknown>;
      if (typeof record.message === 'string' && record.message.trim()) {
        message = record.message;
      }
      if (typeof record.hint === 'string' && record.hint.trim()) {
        hint = record.hint;
      }
      if (typeof record.error === 'string' && record.error.trim()) {
        code = record.error;
      }
    }
  }

  if (res.status === 404 && !hint) {
    hint = 'Refresh the workflow catalog or restart the backend if the route was added recently.';
  } else if (res.status === 503 && !hint) {
    hint = 'Workflow analytics may be disabled for the active project.';
  }

  return new WorkflowRegistryApiError(message, res.status, hint, code);
};

export const encodeWorkflowRegistryRouteParam = (registryId: string): string =>
  Array.from(new TextEncoder().encode(registryId))
    .map(byte => byte.toString(16).padStart(2, '0'))
    .join('');

export const decodeWorkflowRegistryRouteParam = (token: string): string => {
  if (!token || token.length % 2 !== 0 || /[^a-f0-9]/i.test(token)) {
    return token;
  }

  try {
    const bytes = new Uint8Array(
      token.match(/.{1,2}/g)?.map(part => Number.parseInt(part, 16)) || [],
    );
    return new TextDecoder().decode(bytes);
  } catch {
    return token;
  }
};

export const buildWorkflowRegistryPath = (registryId?: string): string =>
  registryId ? `/workflows/${encodeWorkflowRegistryRouteParam(registryId)}` : '/workflows';

export const workflowRegistryService = {
  async list(params?: {
    search?: string;
    correlationState?: WorkflowRegistryCorrelationState | 'all';
    offset?: number;
    limit?: number;
  }): Promise<WorkflowRegistryListResponse> {
    const search = new URLSearchParams();
    if (params?.search) search.append('search', params.search);
    if (params?.correlationState && params.correlationState !== 'all') {
      search.append('correlationState', params.correlationState);
    }
    if (typeof params?.offset === 'number') search.append('offset', String(params.offset));
    if (typeof params?.limit === 'number') search.append('limit', String(params.limit));
    const suffix = search.toString() ? `?${search.toString()}` : '';

    const res = await apiFetch(`${API_BASE}/workflow-registry${suffix}`);
    if (!res.ok) {
      throw await buildWorkflowRegistryApiError(res, 'Failed to fetch workflow registry');
    }
    return res.json() as Promise<WorkflowRegistryListResponse>;
  },

  async getDetail(registryId: string): Promise<WorkflowRegistryDetailResponse> {
    const search = new URLSearchParams({ registryId });
    const res = await apiFetch(`${API_BASE}/workflow-registry/detail?${search.toString()}`);
    if (!res.ok) {
      throw await buildWorkflowRegistryApiError(res, 'Failed to fetch workflow detail');
    }
    return res.json() as Promise<WorkflowRegistryDetailResponse>;
  },
};

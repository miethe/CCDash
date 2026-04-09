import {
  SkillMeatConfigValidationResponse,
  SkillMeatDefinitionSyncResponse,
  SkillMeatObservationBackfillResponse,
  SkillMeatRefreshResponse,
  SkillMeatProjectConfig,
  SessionMemoryDraft,
  SessionMemoryDraftGenerateResponse,
  SessionMemoryDraftListResponse,
  SessionMemoryDraftStatus,
} from '../types';

const API_BASE = '/api/integrations/skillmeat';
const MEMORY_DRAFTS_BASE = `${API_BASE}/memory-drafts`;

type SessionMemoryDraftGenerateRequest = {
  sessionId: string;
  limit: number;
  actor: string;
};

type SessionMemoryDraftReviewRequest = {
  decision: 'approved' | 'rejected';
  actor: string;
  notes: string;
};

type SessionMemoryDraftPublishRequest = {
  actor: string;
  notes: string;
};

async function requestSkillMeatJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    throw new Error(`Request failed (${res.status}) for ${path}`);
  }
  return res.json() as Promise<T>;
}

export async function validateSkillMeatConfig(
  config: Pick<SkillMeatProjectConfig, 'baseUrl' | 'projectId' | 'aaaEnabled' | 'apiKey' | 'requestTimeoutSeconds'>,
): Promise<SkillMeatConfigValidationResponse> {
  const res = await fetch(`${API_BASE}/validate-config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    throw new Error(`Failed to validate SkillMeat configuration (${res.status})`);
  }
  return res.json();
}

export async function syncSkillMeatDefinitions(projectId: string): Promise<SkillMeatDefinitionSyncResponse> {
  const res = await fetch(`${API_BASE}/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ projectId }),
  });
  if (!res.ok) {
    throw new Error(`Failed to sync SkillMeat definitions (${res.status})`);
  }
  return res.json();
}

export async function refreshSkillMeatCache(projectId: string): Promise<SkillMeatRefreshResponse> {
  const res = await fetch(`${API_BASE}/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ projectId }),
  });
  if (!res.ok) {
    throw new Error(`Failed to refresh SkillMeat cache (${res.status})`);
  }
  return res.json();
}

export async function backfillSkillMeatObservations(
  projectId: string,
  options?: { limit?: number; forceRecompute?: boolean },
): Promise<SkillMeatObservationBackfillResponse> {
  const res = await fetch(`${API_BASE}/observations/backfill`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      projectId,
      limit: options?.limit ?? 200,
      forceRecompute: options?.forceRecompute ?? true,
    }),
  });
  if (!res.ok) {
    throw new Error(`Failed to refresh SkillMeat observations (${res.status})`);
  }
  return res.json();
}

export async function listSessionMemoryDrafts(
  projectId: string,
  options?: {
    offset?: number;
    limit?: number;
    sessionId?: string;
    status?: SessionMemoryDraftStatus | 'all';
  },
): Promise<SessionMemoryDraftListResponse> {
  const params = new URLSearchParams({
    projectId,
    offset: String(options?.offset ?? 0),
    limit: String(options?.limit ?? 25),
  });
  if (options?.sessionId?.trim()) params.set('sessionId', options.sessionId.trim());
  if (options?.status && options.status !== 'all') params.set('status', options.status);
  return requestSkillMeatJson<SessionMemoryDraftListResponse>(`${MEMORY_DRAFTS_BASE}?${params.toString()}`);
}

export async function generateSessionMemoryDrafts(
  projectId: string,
  request: SessionMemoryDraftGenerateRequest,
): Promise<SessionMemoryDraftGenerateResponse> {
  return requestSkillMeatJson<SessionMemoryDraftGenerateResponse>(
    `${MEMORY_DRAFTS_BASE}/generate?projectId=${encodeURIComponent(projectId)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    },
  );
}

export async function reviewSessionMemoryDraft(
  projectId: string,
  draftId: number,
  request: SessionMemoryDraftReviewRequest,
): Promise<SessionMemoryDraft> {
  return requestSkillMeatJson<SessionMemoryDraft>(
    `${MEMORY_DRAFTS_BASE}/${draftId}/review?projectId=${encodeURIComponent(projectId)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    },
  );
}

export async function publishSessionMemoryDraft(
  projectId: string,
  draftId: number,
  request: SessionMemoryDraftPublishRequest,
): Promise<SessionMemoryDraft> {
  return requestSkillMeatJson<SessionMemoryDraft>(
    `${MEMORY_DRAFTS_BASE}/${draftId}/publish?projectId=${encodeURIComponent(projectId)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    },
  );
}

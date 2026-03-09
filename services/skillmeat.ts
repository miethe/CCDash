import {
  SkillMeatConfigValidationResponse,
  SkillMeatDefinitionSyncResponse,
  SkillMeatObservationBackfillResponse,
  SkillMeatRefreshResponse,
  SkillMeatProjectConfig,
} from '../types';

const API_BASE = '/api/integrations/skillmeat';

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

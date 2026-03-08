import { SkillMeatConfigValidationResponse, SkillMeatProjectConfig } from '../types';

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

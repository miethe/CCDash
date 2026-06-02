// P5-010: Create-spec helper.
// POST /api/agent/planning/specs → { id, path, status }
// Fails LOUD: throws CreateSpecError on any non-OK response (caller handles the error).

import { apiFetch } from './apiClient';

export interface CreateSpecRequest {
  title: string;
  docType: string;
  projectId: string;
}

export interface CreateSpecResponse {
  id: string;
  path: string;
  status: string;
}

export class CreateSpecError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'CreateSpecError';
    this.status = status;
  }
}

export async function createSpec(req: CreateSpecRequest): Promise<CreateSpecResponse> {
  const res = await apiFetch('/api/agent/planning/specs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      // Backend SpecCreateRequest uses camelCase field names (no alias) — must match
      // or docType/projectId are silently dropped to defaults.
      title: req.title,
      docType: req.docType,
      projectId: req.projectId,
    }),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new CreateSpecError(
      detail || `Spec creation failed (HTTP ${res.status})`,
      res.status,
    );
  }

  const json = await res.json().catch(() => null);
  if (!json) {
    throw new CreateSpecError('Empty response from spec creation endpoint', res.status);
  }
  return {
    id: json.id ?? '',
    path: json.path ?? '',
    status: json.status ?? 'draft',
  };
}

import type {
  PricingCatalogEntry,
  PricingCatalogSyncResponse,
  PricingCatalogUpsertRequest,
} from '../types';

const API_BASE = '/api/pricing';

const buildQuery = (params: Record<string, string | undefined>): string => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value && value.trim()) search.append(key, value);
  });
  const qs = search.toString();
  return qs ? `?${qs}` : '';
};

const fetchJson = async <T>(input: string, init?: RequestInit): Promise<T> => {
  const res = await fetch(input, init);
  if (!res.ok) {
    throw new Error(`Pricing API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
};

export const pricingService = {
  async getPricingCatalog(platformType?: string): Promise<PricingCatalogEntry[]> {
    return fetchJson<PricingCatalogEntry[]>(`${API_BASE}/catalog${buildQuery({ platformType })}`);
  },

  async upsertPricingCatalogEntry(payload: PricingCatalogUpsertRequest): Promise<PricingCatalogEntry> {
    return fetchJson<PricingCatalogEntry>(`${API_BASE}/catalog`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
  },

  async syncPricingCatalog(platformType = 'Claude Code'): Promise<PricingCatalogSyncResponse> {
    return fetchJson<PricingCatalogSyncResponse>(`${API_BASE}/catalog/sync${buildQuery({ platformType })}`, {
      method: 'POST',
    });
  },

  async resetPricingCatalogEntry(platformType: string, modelId = ''): Promise<{ status: string; entry: PricingCatalogEntry | null }> {
    return fetchJson<{ status: string; entry: PricingCatalogEntry | null }>(
      `${API_BASE}/catalog/reset${buildQuery({ platformType, modelId })}`,
      {
        method: 'POST',
      },
    );
  },
};

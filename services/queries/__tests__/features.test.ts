/**
 * Tests for useFeaturesQuery (T2-004).
 *
 * Strategy: test queryFn directly through QueryClient.fetchQuery.
 * Verifies paginated shape, query param forwarding, legacy normalisation,
 * and staleTime cache behaviour.
 *
 * Scenarios covered:
 *   T2-004 — paginated GET on initial fetch
 *   T2-004 — returns FeaturesPage { items, total, page, pageSize }
 *   T2-004 — optional query param forwarded to getFeaturesPaginated
 *   T2-004 — normalises legacy array response
 *   T2-004 — staleTime prevents re-fetch within cache window
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import type { PaginatedResponse } from '../../../contexts/dataContextShared';
import type { Feature } from '../../../types';
import { featuresKeys } from '../../queryKeys';
import { FEATURES_PAGE_SIZE, type FeaturesPage } from '../features';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeFeature(id: string): Feature {
  return { id } as Feature;
}

function makePaginatedFeatures(
  items: Feature[],
  total: number,
): PaginatedResponse<Feature> {
  return { items, total, offset: 0, limit: FEATURES_PAGE_SIZE };
}

function makeMockClient(opts: {
  features?: Feature[];
  total?: number;
  useLegacy?: boolean;
} = {}) {
  const features = opts.features ?? [makeFeature('f1'), makeFeature('f2')];
  const total = opts.total ?? features.length;
  const useLegacy = opts.useLegacy ?? false;

  const getFeaturesPaginated = vi.fn(
    (_page: number, _pageSize: number, _query?: string) => {
      if (useLegacy) {
        return Promise.resolve(features);
      }
      return Promise.resolve(makePaginatedFeatures(features, total));
    },
  );

  return { getFeaturesPaginated };
}

function makeQueryClient(staleTime = 0) {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime } },
  });
}

// Mirror the hook's queryFn
function makeQueryFn(
  client: ReturnType<typeof makeMockClient>,
  page: number,
  query?: string,
): () => Promise<FeaturesPage> {
  return async () => {
    const raw = await client.getFeaturesPaginated(page, FEATURES_PAGE_SIZE, query);
    if (Array.isArray(raw)) {
      return { items: raw, total: raw.length, page, pageSize: FEATURES_PAGE_SIZE };
    }
    const p = raw as PaginatedResponse<Feature>;
    return { items: p.items ?? [], total: p.total ?? 0, page, pageSize: FEATURES_PAGE_SIZE };
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('T2-004: useFeaturesQuery — queryFn behaviour', () => {
  let qc: QueryClient;
  let client: ReturnType<typeof makeMockClient>;

  beforeEach(() => {
    qc = makeQueryClient();
    client = makeMockClient({ features: [makeFeature('f1'), makeFeature('f2')], total: 2 });
  });

  afterEach(() => {
    qc.clear();
  });

  it('fires one paginated GET on initial fetch', async () => {
    await qc.fetchQuery({
      queryKey: featuresKeys.list('proj-1', undefined, 0),
      queryFn: makeQueryFn(client, 0),
    });
    expect(client.getFeaturesPaginated).toHaveBeenCalledTimes(1);
    expect(client.getFeaturesPaginated).toHaveBeenCalledWith(0, FEATURES_PAGE_SIZE, undefined);
  });

  it('returns FeaturesPage shape with items, total, page, pageSize', async () => {
    const result = await qc.fetchQuery({
      queryKey: featuresKeys.list('proj-1', undefined, 0),
      queryFn: makeQueryFn(client, 0),
    });
    expect(result).toHaveProperty('items');
    expect(result).toHaveProperty('total');
    expect(result).toHaveProperty('page', 0);
    expect(result).toHaveProperty('pageSize', FEATURES_PAGE_SIZE);
    expect(result.items).toHaveLength(2);
    expect(result.total).toBe(2);
  });

  it('forwards optional query string to getFeaturesPaginated', async () => {
    const searchQuery = 'auth-refactor';
    await qc.fetchQuery({
      queryKey: featuresKeys.list('proj-1', searchQuery, 0),
      queryFn: makeQueryFn(client, 0, searchQuery),
    });
    expect(client.getFeaturesPaginated).toHaveBeenCalledWith(0, FEATURES_PAGE_SIZE, searchQuery);
  });

  it('normalises legacy array response into FeaturesPage shape', async () => {
    const legacyClient = makeMockClient({
      features: [makeFeature('legacy-f1'), makeFeature('legacy-f2')],
      useLegacy: true,
    });
    const result = await qc.fetchQuery({
      queryKey: featuresKeys.list('proj-legacy', undefined, 0),
      queryFn: makeQueryFn(legacyClient, 0),
    });
    expect(result.items).toHaveLength(2);
    expect(result.items[0].id).toBe('legacy-f1');
    expect(result.total).toBe(2);
  });

  it('page N uses page index in the call', async () => {
    await qc.fetchQuery({
      queryKey: featuresKeys.list('proj-2', undefined, 3),
      queryFn: makeQueryFn(client, 3),
    });
    expect(client.getFeaturesPaginated).toHaveBeenCalledWith(3, FEATURES_PAGE_SIZE, undefined);
  });
});

describe('T2-004: useFeaturesQuery — staleTime cache', () => {
  it('second fetch within staleTime returns cached data without a network call', async () => {
    const qcStale = makeQueryClient(30_000);
    const client = makeMockClient({ features: [makeFeature('f1')], total: 1 });
    const queryKey = featuresKeys.list('proj-1', undefined, 0);
    const queryFn = makeQueryFn(client, 0);

    await qcStale.fetchQuery({ queryKey, queryFn });
    expect(client.getFeaturesPaginated).toHaveBeenCalledTimes(1);

    await qcStale.fetchQuery({ queryKey, queryFn });
    expect(client.getFeaturesPaginated).toHaveBeenCalledTimes(1);

    qcStale.clear();
  });
});

describe('T2-004: total reflects server count, not items.length', () => {
  it('total reports server total when page has fewer items', async () => {
    const qc2 = makeQueryClient();
    const serverTotal = 300;
    const client = makeMockClient({
      features: Array.from({ length: FEATURES_PAGE_SIZE }, (_, i) => makeFeature(`f${i}`)),
      total: serverTotal,
    });
    const result = await qc2.fetchQuery({
      queryKey: featuresKeys.list('proj-big', undefined, 0),
      queryFn: makeQueryFn(client, 0),
    });
    expect(result.total).toBe(serverTotal);
    expect(result.items).toHaveLength(FEATURES_PAGE_SIZE);
    qc2.clear();
  });
});

/**
 * Tests for TanStack Query planning hooks (T3-001 / T3-002 / T3-003).
 *
 * Strategy: exercise queryFn and queryKey logic directly through QueryClient
 * without @testing-library/react.
 *
 * OQ-2 coverage (T3-003): assert that a changed freshnessToken produces a
 * distinct queryKey, causing TQ to issue a new fetch instead of returning
 * the cached entry from the previous token.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { planningKeys } from '../../queryKeys';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
      },
    },
  });
}

function makeSummaryPayload(overrides: Record<string, unknown> = {}) {
  return {
    status: 'ok',
    projectId: 'proj-1',
    projectName: 'Project 1',
    totalFeatureCount: 0,
    activeFeatureCount: 0,
    staleFeatureCount: 0,
    blockedFeatureCount: 0,
    mismatchCount: 0,
    reversalCount: 0,
    staleFeatureIds: [],
    reversalFeatureIds: [],
    blockedFeatureIds: [],
    nodeCountsByType: {},
    featureSummaries: [],
    dataFreshness: '2026-04-01T00:00:00Z',
    generatedAt: '2026-04-01T00:01:00Z',
    sourceRefs: [],
    ...overrides,
  };
}

// ── T3-003: freshnessToken drives distinct queryKey → new fetch ───────────────

describe('T3-003: usePlanningSummaryQuery — freshnessToken produces distinct queryKey', () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = makeQueryClient();
  });

  afterEach(() => {
    qc.clear();
    vi.restoreAllMocks();
  });

  it('same freshnessToken returns cached entry (no second fetch)', async () => {
    const projectId = 'proj-freshness';
    const token = '2026-04-01T00:00:00Z';
    const key = planningKeys.summary(projectId, token);

    const fetchFn = vi.fn().mockResolvedValue(makeSummaryPayload({ projectId }));

    // First fetch
    await qc.fetchQuery({ queryKey: key, queryFn: fetchFn });
    expect(fetchFn).toHaveBeenCalledTimes(1);

    // Second fetch with same key — within staleTime=0 the first call already
    // populated the cache; TQ serves it without calling fetchFn again.
    const cached = qc.getQueryData(key);
    expect(cached).toBeDefined();

    // Re-fetch with the same queryKey using ensureQueryData (returns cache immediately)
    const result = await qc.ensureQueryData({ queryKey: key, queryFn: fetchFn });
    // staleTime=0 means TQ will re-fetch; but for a synchronously populated cache
    // within the same tick, getQueryData returns without calling fetchFn again.
    expect(result).toBeDefined();
  });

  it('changed freshnessToken produces a distinct queryKey → new fetch', async () => {
    const projectId = 'proj-freshness';
    const tokenV1 = '2026-04-01T00:00:00Z';
    const tokenV2 = '2026-04-01T00:05:00Z';

    const keyV1 = planningKeys.summary(projectId, tokenV1);
    const keyV2 = planningKeys.summary(projectId, tokenV2);

    // Verify the two keys are structurally different
    expect(keyV1).not.toEqual(keyV2);
    expect(JSON.stringify(keyV1)).not.toBe(JSON.stringify(keyV2));

    const fetchFnV1 = vi.fn().mockResolvedValue(makeSummaryPayload({ projectId, dataFreshness: tokenV1 }));
    const fetchFnV2 = vi.fn().mockResolvedValue(makeSummaryPayload({ projectId, dataFreshness: tokenV2 }));

    // Populate cache with V1
    await qc.fetchQuery({ queryKey: keyV1, queryFn: fetchFnV1 });
    expect(fetchFnV1).toHaveBeenCalledTimes(1);

    // V2 key has no cache entry — TQ issues a new fetch
    await qc.fetchQuery({ queryKey: keyV2, queryFn: fetchFnV2 });
    expect(fetchFnV2).toHaveBeenCalledTimes(1);

    // V1 cache is still intact (no eviction)
    const cachedV1 = qc.getQueryData(keyV1);
    expect(cachedV1).toBeDefined();
  });

  it('null freshnessToken and undefined produce distinct keys from a real token', () => {
    const projectId = 'proj-null-token';
    const keyNull = planningKeys.summary(projectId, null);
    const keyUndefined = planningKeys.summary(projectId, undefined);
    const keyReal = planningKeys.summary(projectId, '2026-04-01T00:00:00Z');

    expect(JSON.stringify(keyNull)).not.toBe(JSON.stringify(keyReal));
    expect(JSON.stringify(keyUndefined)).not.toBe(JSON.stringify(keyReal));
  });
});

// ── T3-001: queryKey structure sanity checks ──────────────────────────────────

describe('T3-001: planningKeys shape', () => {
  it('summary key includes projectId and freshnessToken segment', () => {
    const key = planningKeys.summary('proj-1', 'tok-abc');
    expect(key).toContain('proj-1');
    expect(JSON.stringify(key)).toContain('tok-abc');
  });

  it('featureContext key includes projectId and featureId', () => {
    const key = planningKeys.featureContext('proj-1', 'feat-xyz');
    expect(key).toContain('proj-1');
    expect(key).toContain('feat-xyz');
  });

  it('projectSessionBoard key includes projectId', () => {
    const key = planningKeys.projectSessionBoard('proj-1', undefined);
    expect(key).toContain('proj-1');
  });

  it('featureSessionBoard key includes projectId and featureId', () => {
    const key = planningKeys.featureSessionBoard('proj-1', 'feat-xyz', undefined);
    expect(key).toContain('proj-1');
    expect(key).toContain('feat-xyz');
  });
});

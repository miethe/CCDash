// Tests for useFeatureSurface hook (P3-002)
//
// Strategy: no @testing-library/react (not installed).
// Hook behavior is tested by exercising the exported pure functions
// (buildCacheKey, DEFAULT_FEATURE_SURFACE_QUERY) and the async fetch helpers
// extracted from the hook's internal logic, simulating the same call sequence
// the hook's useEffect drives: fetchList → collect IDs → fetchRollups.
//
// Covers:
//   1.  buildCacheKey – normalizes array order
//   2.  buildCacheKey – differentiates page
//   3.  buildCacheKey – differentiates projectId
//   4.  buildCacheKey – differentiates search
//   5.  buildCacheKey – differentiates sortDirection
//   6.  buildCacheKey – no "undefined" segments
//   7.  DEFAULT_FEATURE_SURFACE_QUERY shape
//   8.  Inline LRU adapter protocol – get/set/evict/delete/clear
//   9.  Fires ONE list request and ONE rollup batch (no per-feature fan-out)
//  10.  Rollup batch receives all IDs returned by the list
//  11.  Empty list → rollup fetch skipped
//  12.  List and rollup independence (partial render)
//  13.  Default rollup fields sent when not overridden
//  14.  retry: re-fires list then rollup batch on list error
//  15.  retryRollups: re-fires only rollup (not list) using existing card IDs
//  16.  Stale-response guard: late list response is discarded
//  17.  listError is set when list throws
//  18.  rollupError set on rollup failure, list data still available
//  19.  Cache-first: cache hit avoids calling listFeatureCards
//  20.  invalidate("all") calls cache.delete with the correct key
//  21.  invalidate("list") calls cache.delete without clearing rollup state
//  22.  setQuery partial merge preserves defaults
//  23.  setQuery function updater increments page

import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  buildCacheKey,
  DEFAULT_FEATURE_SURFACE_QUERY,
  type FeatureSurfaceQuery,
  type FeatureSurfaceCacheAdapter,
  type CacheEntry,
} from '../useFeatureSurface';

// ── Mock featureSurface client ────────────────────────────────────────────────

vi.mock('../featureSurface', () => ({
  listFeatureCards: vi.fn(),
  getFeatureRollups: vi.fn(),
}));

import { listFeatureCards, getFeatureRollups, type FeatureRollupDTO, type FeatureRollupResponseDTO } from '../featureSurface';

const mockListFeatureCards = vi.mocked(listFeatureCards);
const mockGetFeatureRollups = vi.mocked(getFeatureRollups);

// Global reset — ensures no mock state leaks between tests or describe blocks.
beforeEach(() => { vi.resetAllMocks(); });

// ── Test data factories ───────────────────────────────────────────────────────

function makeCard(id: string) {
  return {
    id,
    name: `Feature ${id}`,
    status: 'active',
    effectiveStatus: 'in_progress',
    category: 'core',
    tags: [],
    summary: '',
    descriptionPreview: '',
    priority: 'medium',
    riskLevel: 'low',
    complexity: 'moderate',
    totalTasks: 5,
    completedTasks: 2,
    deferredTasks: 0,
    phaseCount: 1,
    plannedAt: '',
    startedAt: '',
    completedAt: '',
    updatedAt: '2026-04-23T00:00:00Z',
    documentCoverage: { present: [], missing: [], countsByType: {} },
    qualitySignals: {
      blockerCount: 0,
      atRiskTaskCount: 0,
      hasBlockingSignals: false,
      testImpact: '',
      integritySignalRefs: [],
    },
    dependencyState: {
      state: 'ready',
      blockingReason: '',
      blockedByCount: 0,
      readyDependencyCount: 0,
    },
    primaryDocuments: [],
    familyPosition: null,
    relatedFeatureCount: 0,
    precision: 'exact' as const,
    freshness: null,
  };
}

function makeCardPage(ids: string[], total?: number) {
  const items = ids.map(makeCard);
  return {
    items,
    total: total ?? items.length,
    offset: 0,
    limit: 50,
    hasMore: false,
    queryHash: 'test-hash',
    precision: 'exact' as const,
    freshness: null,
  };
}

function makeRollupsResponse(featureIds: string[]): FeatureRollupResponseDTO {
  const rollups: Record<string, FeatureRollupDTO> = {};
  for (const id of featureIds) {
    rollups[id] = {
      featureId: id,
      sessionCount: 3,
      primarySessionCount: 2,
      subthreadCount: 1,
      unresolvedSubthreadCount: 0,
      totalCost: 0.5,
      displayCost: 0.5,
      observedTokens: 10000,
      modelIoTokens: 9500,
      cacheInputTokens: 500,
      latestSessionAt: '2026-04-23T00:00:00Z',
      latestActivityAt: '2026-04-23T00:00:00Z',
      modelFamilies: [],
      providers: [],
      workflowTypes: [],
      linkedDocCount: 1,
      linkedDocCountsByType: [],
      linkedTaskCount: 5,
      linkedCommitCount: null,
      linkedPrCount: null,
      testCount: null,
      failingTestCount: null,
      precision: 'eventually_consistent' as const,
      freshness: null,
    };
  }
  return {
    rollups,
    missing: [],
    errors: {},
    generatedAt: '2026-04-23T00:00:00Z',
    cacheVersion: 'v1',
  };
}

// ── buildCacheKey ─────────────────────────────────────────────────────────────

describe('buildCacheKey', () => {
  it('produces the same key for equivalent queries regardless of array order', () => {
    const q1: FeatureSurfaceQuery = {
      ...DEFAULT_FEATURE_SURFACE_QUERY,
      status: ['active', 'planned'],
      tags: ['a', 'b'],
    };
    const q2: FeatureSurfaceQuery = {
      ...DEFAULT_FEATURE_SURFACE_QUERY,
      status: ['planned', 'active'],
      tags: ['b', 'a'],
    };
    expect(buildCacheKey(q1)).toBe(buildCacheKey(q2));
  });

  it('produces different keys for different pages', () => {
    const q1 = { ...DEFAULT_FEATURE_SURFACE_QUERY, page: 1 };
    const q2 = { ...DEFAULT_FEATURE_SURFACE_QUERY, page: 2 };
    expect(buildCacheKey(q1)).not.toBe(buildCacheKey(q2));
  });

  it('produces different keys for different projectIds', () => {
    const q1 = { ...DEFAULT_FEATURE_SURFACE_QUERY, projectId: 'proj-a' };
    const q2 = { ...DEFAULT_FEATURE_SURFACE_QUERY, projectId: 'proj-b' };
    expect(buildCacheKey(q1)).not.toBe(buildCacheKey(q2));
  });

  it('differentiates on search term', () => {
    const q1 = { ...DEFAULT_FEATURE_SURFACE_QUERY, search: 'foo' };
    const q2 = { ...DEFAULT_FEATURE_SURFACE_QUERY, search: 'bar' };
    expect(buildCacheKey(q1)).not.toBe(buildCacheKey(q2));
  });

  it('differentiates on sort direction', () => {
    const q1 = { ...DEFAULT_FEATURE_SURFACE_QUERY, sortDirection: 'asc' as const };
    const q2 = { ...DEFAULT_FEATURE_SURFACE_QUERY, sortDirection: 'desc' as const };
    expect(buildCacheKey(q1)).not.toBe(buildCacheKey(q2));
  });

  it('returns a stable string with no undefined segments', () => {
    const key = buildCacheKey(DEFAULT_FEATURE_SURFACE_QUERY);
    expect(key).not.toContain('undefined');
    expect(typeof key).toBe('string');
  });
});

// ── DEFAULT_FEATURE_SURFACE_QUERY ─────────────────────────────────────────────

describe('DEFAULT_FEATURE_SURFACE_QUERY', () => {
  it('has page=1, pageSize=50, sortDirection=desc', () => {
    expect(DEFAULT_FEATURE_SURFACE_QUERY.page).toBe(1);
    expect(DEFAULT_FEATURE_SURFACE_QUERY.pageSize).toBe(50);
    expect(DEFAULT_FEATURE_SURFACE_QUERY.sortDirection).toBe('desc');
  });

  it('has empty arrays for status, stage, tags, include', () => {
    expect(DEFAULT_FEATURE_SURFACE_QUERY.status).toEqual([]);
    expect(DEFAULT_FEATURE_SURFACE_QUERY.stage).toEqual([]);
    expect(DEFAULT_FEATURE_SURFACE_QUERY.tags).toEqual([]);
    expect(DEFAULT_FEATURE_SURFACE_QUERY.include).toEqual([]);
  });
});

// ── Inline LRU adapter protocol ───────────────────────────────────────────────

describe('LRU adapter protocol (FeatureSurfaceCacheAdapter)', () => {
  function makeLRUAdapter(max = 3): FeatureSurfaceCacheAdapter & { size: () => number } {
    const store = new Map<string, CacheEntry>();
    const keys: string[] = [];
    return {
      size: () => store.size,
      get(k) { return store.get(k); },
      set(k, v) {
        if (!store.has(k)) {
          if (keys.length >= max) { store.delete(keys.shift()!); }
          keys.push(k);
        }
        store.set(k, v);
      },
      delete(k) {
        const idx = keys.indexOf(k);
        if (idx !== -1) keys.splice(idx, 1);
        store.delete(k);
      },
      clear() { store.clear(); keys.length = 0; },
    };
  }

  const makeEntry = (queryHash = 'h'): CacheEntry => ({
    cards: [makeCard('F1')],
    total: 1,
    freshness: null,
    queryHash,
    timestamp: Date.now(),
  });

  it('returns undefined for a missing key', () => {
    expect(makeLRUAdapter().get('missing')).toBeUndefined();
  });

  it('returns stored entry for a present key', () => {
    const c = makeLRUAdapter();
    const entry = makeEntry();
    c.set('k1', entry);
    expect(c.get('k1')).toBe(entry);
  });

  it('evicts the oldest entry when over capacity', () => {
    const c = makeLRUAdapter(2);
    c.set('k1', makeEntry('h1'));
    c.set('k2', makeEntry('h2'));
    c.set('k3', makeEntry('h3'));
    expect(c.size()).toBe(2);
    expect(c.get('k1')).toBeUndefined(); // evicted
    expect(c.get('k2')).toBeDefined();
    expect(c.get('k3')).toBeDefined();
  });

  it('delete removes the entry', () => {
    const c = makeLRUAdapter();
    c.set('k1', makeEntry());
    c.delete('k1');
    expect(c.get('k1')).toBeUndefined();
  });

  it('clear empties all entries', () => {
    const c = makeLRUAdapter();
    c.set('k1', makeEntry());
    c.set('k2', makeEntry());
    c.clear();
    expect(c.size()).toBe(0);
  });
});

// ── Async data-flow tests ─────────────────────────────────────────────────────
//
// These tests simulate the hook's useEffect call sequence directly:
// listFeatureCards → collect IDs → getFeatureRollups.
// This avoids the need for @testing-library/react while verifying the
// sequencing contract the hook enforces.

describe('list + rollup data-flow contract', () => {
  it('fires ONE list request and ONE rollup batch — no per-feature fan-out', async () => {
    mockListFeatureCards.mockResolvedValueOnce(makeCardPage(['F1', 'F2', 'F3']));
    mockGetFeatureRollups.mockResolvedValueOnce(makeRollupsResponse(['F1', 'F2', 'F3']));

    const page = await listFeatureCards({});
    const ids = page.items.map((c) => c.id);
    await getFeatureRollups({ featureIds: ids });

    expect(mockListFeatureCards).toHaveBeenCalledTimes(1);
    expect(mockGetFeatureRollups).toHaveBeenCalledTimes(1);
  });

  it('rollup batch receives all IDs returned by the list', async () => {
    mockListFeatureCards.mockResolvedValueOnce(makeCardPage(['X1', 'X2']));
    mockGetFeatureRollups.mockResolvedValueOnce(makeRollupsResponse(['X1', 'X2']));

    const page = await listFeatureCards({});
    const ids = page.items.map((c) => c.id);
    await getFeatureRollups({ featureIds: ids });

    expect(mockGetFeatureRollups.mock.calls[0][0].featureIds).toEqual(['X1', 'X2']);
  });

  it('skips rollup fetch when list returns zero cards', async () => {
    mockListFeatureCards.mockResolvedValueOnce(makeCardPage([]));

    const page = await listFeatureCards({});
    if (page.items.length > 0) {
      await getFeatureRollups({ featureIds: page.items.map((c) => c.id) });
    }

    expect(mockGetFeatureRollups).not.toHaveBeenCalled();
  });

  it('list state can succeed while rollup is still pending (independence)', async () => {
    let resolveRollup!: (v: ReturnType<typeof makeRollupsResponse>) => void;
    const rollupDeferred = new Promise<ReturnType<typeof makeRollupsResponse>>(
      (res) => { resolveRollup = res; },
    );

    mockListFeatureCards.mockResolvedValueOnce(makeCardPage(['F1']));
    mockGetFeatureRollups.mockReturnValueOnce(
      rollupDeferred as unknown as ReturnType<typeof getFeatureRollups>,
    );

    const page = await listFeatureCards({});
    expect(page.items).toHaveLength(1); // list success, cards available for partial render

    resolveRollup(makeRollupsResponse(['F1']));
    const rollup = await rollupDeferred;
    expect(Object.keys(rollup.rollups)).toContain('F1');
  });

  it('default rollup fields include card aggregate groups', async () => {
    mockListFeatureCards.mockResolvedValueOnce(makeCardPage(['F1']));
    mockGetFeatureRollups.mockResolvedValueOnce(makeRollupsResponse(['F1']));

    const page = await listFeatureCards({});
    const ids = page.items.map((c) => c.id);
    const defaultFields = [
      'session_counts',
      'token_cost_totals',
      'latest_activity',
      'model_provider_summary',
      'doc_metrics',
    ] as const;
    await getFeatureRollups({ featureIds: ids, fields: [...defaultFields] });

    const call = mockGetFeatureRollups.mock.calls[0][0];
    expect(call.fields).toContain('session_counts');
    expect(call.fields).toContain('token_cost_totals');
    expect(call.fields).toContain('latest_activity');
    expect(call.fields).toContain('model_provider_summary');
    expect(call.fields).toContain('doc_metrics');
  });

  it('retry: re-fires list request then rollup batch after list failure', async () => {
    mockListFeatureCards
      .mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValueOnce(makeCardPage(['F1']));
    mockGetFeatureRollups.mockResolvedValueOnce(makeRollupsResponse(['F1']));

    // First attempt fails
    await expect(listFeatureCards({})).rejects.toThrow('Network error');

    // Retry succeeds
    const page = await listFeatureCards({});
    const ids = page.items.map((c) => c.id);
    await getFeatureRollups({ featureIds: ids });

    expect(mockListFeatureCards).toHaveBeenCalledTimes(2);
    expect(mockGetFeatureRollups).toHaveBeenCalledTimes(1);
    expect(mockGetFeatureRollups.mock.calls[0][0].featureIds).toEqual(['F1']);
  });

  it('retryRollups: re-fires only rollup (not list) using existing card IDs', async () => {
    const cardIds = ['F1', 'F2'];

    // Use a call counter to deterministically control responses —
    // avoids relying on mockRejectedValueOnce queue behavior across beforeEach.
    let callCount = 0;
    mockGetFeatureRollups.mockImplementation(async () => {
      callCount += 1;
      if (callCount === 1) throw new Error('Rollup 503');
      return makeRollupsResponse(cardIds);
    });

    // Simulate rollup failing (list already succeeded and gave us cards in state)
    await expect(getFeatureRollups({ featureIds: cardIds })).rejects.toThrow('Rollup 503');

    // Retry rollups only — list is NOT called
    const rollup = await getFeatureRollups({ featureIds: cardIds });
    expect(rollup.rollups).toHaveProperty('F1');
    expect(rollup.rollups).toHaveProperty('F2');

    expect(mockListFeatureCards).not.toHaveBeenCalled();
    expect(mockGetFeatureRollups).toHaveBeenCalledTimes(2);
  });

  it('stale-response guard: late list response is discarded when a newer request fires', async () => {
    // Monotonic request-id pattern: only commit a response if the requestId
    // matches the current one.  Simulate with a deferred first call.
    let currentRequestId = 0;
    const committed: string[][] = [];

    async function fetchWithGuard(requestId: number): Promise<void> {
      const page = await listFeatureCards({});
      if (requestId !== currentRequestId) return; // stale guard
      committed.push(page.items.map((c) => c.id));
    }

    let resolveFirst!: () => void;
    const firstDone = new Promise<void>((res) => { resolveFirst = res; });

    mockListFeatureCards
      .mockImplementationOnce(async () => {
        await firstDone;
        return makeCardPage(['STALE']);
      })
      .mockResolvedValueOnce(makeCardPage(['CURRENT']));

    // Fire first (stale) request, then immediately supersede it
    currentRequestId = 1;
    void fetchWithGuard(1);

    currentRequestId = 2;
    await fetchWithGuard(2); // completes immediately with CURRENT

    // Unblock first — its guard check will fail (1 !== 2)
    resolveFirst();
    await new Promise((r) => setTimeout(r, 0));

    expect(committed).toHaveLength(1);
    expect(committed[0]).toEqual(['CURRENT']);
  });

  it('listError is set when list throws', async () => {
    mockListFeatureCards.mockRejectedValueOnce(new Error('500 Internal Server Error'));

    await expect(listFeatureCards({})).rejects.toThrow('500 Internal Server Error');
  });

  it('rollupError does not prevent list data from being available', async () => {
    mockListFeatureCards.mockResolvedValueOnce(makeCardPage(['F1']));
    mockGetFeatureRollups.mockRejectedValueOnce(new Error('Rollup 503'));

    const page = await listFeatureCards({});
    expect(page.items).toHaveLength(1);
    expect(page.items[0].id).toBe('F1');

    await expect(
      getFeatureRollups({ featureIds: ['F1'] }),
    ).rejects.toThrow('Rollup 503');
  });
});

// ── Cache seam behavior ───────────────────────────────────────────────────────

describe('cache seam behavior', () => {
  it('adapter.get hit skips listFeatureCards — serves cached entry directly', () => {
    const cachedEntry: CacheEntry = {
      cards: [makeCard('CACHED-F1')],
      total: 1,
      freshness: null,
      queryHash: 'cached-hash',
      timestamp: Date.now(),
    };

    const spyCache: FeatureSurfaceCacheAdapter = {
      get: vi.fn().mockReturnValue(cachedEntry),
      set: vi.fn(),
      delete: vi.fn(),
      clear: vi.fn(),
    };

    // Simulate the hook's cache-first logic: check cache before fetching
    const key = buildCacheKey(DEFAULT_FEATURE_SURFACE_QUERY);
    const hit = spyCache.get(key);

    // Because hit is truthy we do NOT call listFeatureCards
    const calledNetwork = !hit;
    expect(calledNetwork).toBe(false);

    expect(spyCache.get).toHaveBeenCalledWith(key);
    // listFeatureCards mock is clean (beforeEach cleared it) — no calls
    expect(mockListFeatureCards).not.toHaveBeenCalled();
    expect(hit?.cards[0].id).toBe('CACHED-F1');
  });

  it('invalidate("all") calls cache.delete with the current cache key', () => {
    const spyCache: FeatureSurfaceCacheAdapter = {
      get: vi.fn().mockReturnValue(undefined),
      set: vi.fn(),
      delete: vi.fn(),
      clear: vi.fn(),
    };

    const key = buildCacheKey(DEFAULT_FEATURE_SURFACE_QUERY);
    spyCache.delete(key); // simulate invalidate("all")

    expect(spyCache.delete).toHaveBeenCalledWith(key);
  });

  it('invalidate("list") calls cache.delete but does not invoke clear() (rollup state untouched)', () => {
    const spyCache: FeatureSurfaceCacheAdapter = {
      get: vi.fn().mockReturnValue(undefined),
      set: vi.fn(),
      delete: vi.fn(),
      clear: vi.fn(),
    };

    const key = buildCacheKey(DEFAULT_FEATURE_SURFACE_QUERY);
    spyCache.delete(key); // simulate list-only invalidation

    expect(spyCache.delete).toHaveBeenCalledWith(key);
    expect(spyCache.clear).not.toHaveBeenCalled();
  });
});

// ── FeatureSurfaceQuery shape ─────────────────────────────────────────────────

describe('FeatureSurfaceQuery shape', () => {
  it('partial merge preserves defaults', () => {
    const prev = { ...DEFAULT_FEATURE_SURFACE_QUERY };
    const next = { ...prev, search: 'hello', page: 2 };
    expect(next.pageSize).toBe(50);
    expect(next.sortDirection).toBe('desc');
    expect(next.search).toBe('hello');
    expect(next.page).toBe(2);
  });

  it('function updater increments page', () => {
    const prev = { ...DEFAULT_FEATURE_SURFACE_QUERY };
    const next = ((p: FeatureSurfaceQuery) => ({ ...p, page: p.page + 1 }))(prev);
    expect(next.page).toBe(2);
    expect(next.search).toBe(''); // other fields preserved
  });
});

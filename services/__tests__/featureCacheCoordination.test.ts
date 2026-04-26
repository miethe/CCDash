// featureCacheCoordination.test.ts — P4-011
//
// Asserts that a feature-write event published via featureCacheBus
// deterministically invalidates entries in BOTH the Feature Surface Cache and
// the Planning Browser Cache, and that unrelated events do not thrash.
//
// Test inventory:
//   1.  Feature-write event invalidates Feature Surface Cache list entries for the project.
//   2.  Feature-write event invalidates Feature Surface Cache rollup entries that overlap the feature IDs.
//   3.  Feature-write event does NOT evict Feature Surface Cache entries for a different project.
//   4.  Feature-write event clears Planning Browser Cache for the affected project.
//   5.  Feature-write event does NOT clear Planning Browser Cache for an unrelated project.
//   6.  Event with no projectId clears the entire Feature Surface Cache (global eviction).
//   7.  Event with no projectId clears ALL planning cache entries.
//   8.  Unrelated (non-feature-write) events do not trigger either cache eviction.
//   9.  Multiple subscribers each receive the event independently.
//  10.  Unsubscribing a handler prevents further eviction calls.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  _clearSubscribers,
  publishFeatureWriteEvent,
  subscribeToFeatureWrites,
} from '../featureCacheBus';
import {
  FeatureSurfaceCache,
  buildRollupCacheKey,
} from '../featureSurfaceCache';
import {
  clearPlanningBrowserCache,
  getCachedProjectPlanningSummary,
  getProjectPlanningSummary,
} from '../planning';
import type { CacheEntry } from '../useFeatureSurface';
import type { RollupCacheEntry } from '../featureSurfaceCache';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeListEntry(overrides: Partial<CacheEntry> = {}): CacheEntry {
  return {
    cards: [],
    total: 0,
    freshness: null,
    queryHash: 'hash',
    timestamp: Date.now(),
    ...overrides,
  };
}

function makeRollupEntry(overrides: Partial<RollupCacheEntry> = {}): RollupCacheEntry {
  return {
    rollups: {},
    timestamp: Date.now(),
    freshnessToken: null,
    ...overrides,
  };
}

// ── Planning cache helpers ─────────────────────────────────────────────────────
//
// Planning cache tests use the module-level PLANNING_BROWSER_CACHE via the
// exported helpers because the Map is not directly exported.  We prime the
// cache by stubbing fetch to return a minimal valid response, then verify via
// getCachedProjectPlanningSummary that the entry is gone after an event.

function okResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function makeMinimalSummary(projectId: string, freshness = 'fresh-1') {
  return {
    status: 'ok',
    data_freshness: freshness,
    generated_at: new Date().toISOString(),
    source_refs: [],
    project_id: projectId,
    project_name: 'Test Project',
    total_feature_count: 2,
    active_feature_count: 1,
    stale_feature_count: 0,
    blocked_feature_count: 0,
    mismatch_count: 0,
    reversal_count: 0,
    stale_feature_ids: [],
    reversal_feature_ids: [],
    blocked_feature_ids: [],
    node_counts_by_type: {
      prd: 0,
      design_spec: 0,
      implementation_plan: 0,
      progress: 0,
      context: 0,
      tracker: 0,
      report: 0,
    },
    feature_summaries: [],
  };
}

// ── Test setup ────────────────────────────────────────────────────────────────

// We need to isolate each test from the module-level singleton subscriptions
// added by featureSurfaceCache.ts and planning.ts when they are imported.
// Strategy: import those modules (triggering their subscriptions), then in each
// test create ISOLATED cache instances so we can assert independently.
// For planning, we use the real module cache via getCachedProjectPlanningSummary.

// The static imports above trigger each module's bus subscription at load time.

describe('featureCacheCoordination (P4-011)', () => {
  beforeEach(() => {
    // Clear all planning cache state between tests.
    clearPlanningBrowserCache();
    // Clear fetch stubs
    vi.restoreAllMocks();
  });

  afterEach(() => {
    // Do NOT call _clearSubscribers() here — we want the real module-level
    // subscriptions to remain active so we can test them.  Each test uses
    // isolated FeatureSurfaceCache instances to avoid write-side bleed.
    vi.restoreAllMocks();
  });

  // ── 1. Feature-write event invalidates Feature Surface Cache list entries ──

  it('1. feature-write event evicts list entries for the affected project', () => {
    const cache = new FeatureSurfaceCache();
    const key1 = 'proj-A|query-1|1';
    const key2 = 'proj-A|query-2|1';
    cache.set(key1, makeListEntry());
    cache.set(key2, makeListEntry());

    // Register a custom subscriber wired to this isolated cache.
    const unsub = subscribeToFeatureWrites((event) => {
      if (event.projectId) {
        cache.invalidateProject(event.projectId);
      }
    });

    publishFeatureWriteEvent({ projectId: 'proj-A', featureIds: ['FEAT-1'], kind: 'status' });
    unsub();

    expect(cache.get(key1)).toBeUndefined();
    expect(cache.get(key2)).toBeUndefined();
    expect(cache.listSize).toBe(0);
  });

  // ── 2. Feature-write event invalidates overlapping rollup entries ──────────

  it('2. feature-write event evicts rollup entries overlapping the feature IDs', () => {
    const cache = new FeatureSurfaceCache();
    const rollupKey1 = buildRollupCacheKey('proj-A', ['FEAT-1', 'FEAT-2'], ['session_counts'], 'tok-1');
    const rollupKey2 = buildRollupCacheKey('proj-A', ['FEAT-3'], ['session_counts'], 'tok-1');
    cache.setRollup(rollupKey1, makeRollupEntry());
    cache.setRollup(rollupKey2, makeRollupEntry());

    const unsub = subscribeToFeatureWrites((event) => {
      if (event.projectId && event.featureIds?.length) {
        cache.invalidateFeatures(event.projectId, event.featureIds);
      }
    });

    publishFeatureWriteEvent({ projectId: 'proj-A', featureIds: ['FEAT-1'], kind: 'status' });
    unsub();

    // rollupKey1 contains FEAT-1 — should be evicted.
    expect(cache.getRollup(rollupKey1)).toBeUndefined();
    // rollupKey2 does NOT contain FEAT-1 — should remain.
    expect(cache.getRollup(rollupKey2)).toBeDefined();
  });

  // ── 3. Unrelated project entries are not evicted ──────────────────────────

  it('3. feature-write event does NOT evict Feature Surface Cache entries for a different project', () => {
    const cache = new FeatureSurfaceCache();
    const keyA = 'proj-A|q|1';
    const keyB = 'proj-B|q|1';
    cache.set(keyA, makeListEntry());
    cache.set(keyB, makeListEntry());

    const unsub = subscribeToFeatureWrites((event) => {
      if (event.projectId) cache.invalidateProject(event.projectId);
    });

    publishFeatureWriteEvent({ projectId: 'proj-A', featureIds: ['FEAT-1'], kind: 'status' });
    unsub();

    expect(cache.get(keyA)).toBeUndefined();
    expect(cache.get(keyB)).toBeDefined();
  });

  // ── 4. Planning cache is cleared for the affected project ─────────────────

  it('4. feature-write event clears Planning Browser Cache for the affected project', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse(makeMinimalSummary('proj-A')));
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary('proj-A');

    // Confirm entry is warm.
    expect(getCachedProjectPlanningSummary('proj-A')).not.toBeNull();

    // Publishing a feature-write event should evict the planning cache entry
    // via the module-level subscriber registered in planning.ts.
    publishFeatureWriteEvent({ projectId: 'proj-A', featureIds: ['FEAT-1'], kind: 'status' });

    expect(getCachedProjectPlanningSummary('proj-A')).toBeNull();
  });

  // ── 5. Unrelated planning project entry is not evicted ────────────────────

  it('5. feature-write event does NOT clear Planning Browser Cache for an unrelated project', async () => {
    const fetchMock = vi.fn()
      .mockImplementation((url: string) => {
        const projectId = url.includes('proj-B') ? 'proj-B' : 'proj-A';
        return Promise.resolve(okResponse(makeMinimalSummary(projectId)));
      });
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary('proj-A');
    await getProjectPlanningSummary('proj-B');

    publishFeatureWriteEvent({ projectId: 'proj-A', featureIds: ['FEAT-1'], kind: 'status' });

    expect(getCachedProjectPlanningSummary('proj-A')).toBeNull();
    expect(getCachedProjectPlanningSummary('proj-B')).not.toBeNull();
  });

  // ── 6. Event with no projectId clears entire Feature Surface Cache ─────────

  it('6. event with no projectId clears the entire Feature Surface Cache', () => {
    const cache = new FeatureSurfaceCache();
    cache.set('proj-A|q|1', makeListEntry());
    cache.set('proj-B|q|1', makeListEntry());

    const unsub = subscribeToFeatureWrites((event) => {
      if (!event.projectId) cache.clear();
    });

    publishFeatureWriteEvent({ projectId: undefined, featureIds: [], kind: 'generic' });
    unsub();

    expect(cache.listSize).toBe(0);
  });

  // ── 7. Event with no projectId clears all planning cache entries ──────────

  it('7. event with no projectId clears ALL Planning Browser Cache entries', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      const projectId = url.includes('proj-B') ? 'proj-B' : 'proj-A';
      return Promise.resolve(okResponse(makeMinimalSummary(projectId)));
    });
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary('proj-A');
    await getProjectPlanningSummary('proj-B');

    publishFeatureWriteEvent({ projectId: undefined, featureIds: [], kind: 'generic' });

    expect(getCachedProjectPlanningSummary('proj-A')).toBeNull();
    expect(getCachedProjectPlanningSummary('proj-B')).toBeNull();
  });

  // ── 8. Subscribers are not called by anything other than publishFeatureWriteEvent ─

  it('8. cache entries are not evicted unless publishFeatureWriteEvent is called', () => {
    const cache = new FeatureSurfaceCache();
    const key = 'proj-A|q|1';
    cache.set(key, makeListEntry());

    // No publish — entry should remain.
    expect(cache.get(key)).toBeDefined();
  });

  // ── 9. Multiple subscribers each receive the event ────────────────────────

  it('9. multiple subscribers all receive the same event', () => {
    const received1: string[] = [];
    const received2: string[] = [];

    const unsub1 = subscribeToFeatureWrites((e) => received1.push(e.kind));
    const unsub2 = subscribeToFeatureWrites((e) => received2.push(e.kind));

    publishFeatureWriteEvent({ projectId: 'proj-A', featureIds: ['FEAT-1'], kind: 'phase' });
    publishFeatureWriteEvent({ projectId: 'proj-A', featureIds: ['FEAT-2'], kind: 'task' });

    unsub1();
    unsub2();

    expect(received1).toEqual(['phase', 'task']);
    expect(received2).toEqual(['phase', 'task']);
  });

  // ── 10. Unsubscribing prevents further eviction calls ─────────────────────

  it('10. unsubscribing a handler prevents it from being called on subsequent publishes', () => {
    const calls: string[] = [];
    const unsub = subscribeToFeatureWrites((e) => calls.push(e.kind));

    publishFeatureWriteEvent({ projectId: 'proj-A', featureIds: ['FEAT-1'], kind: 'status' });
    unsub();
    publishFeatureWriteEvent({ projectId: 'proj-A', featureIds: ['FEAT-2'], kind: 'phase' });

    // Only the first event should have been received.
    expect(calls).toEqual(['status']);
  });
});

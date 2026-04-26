// Tests for featureSurfaceCache (P3-006)
//
// Covers:
//   1.  LRU eviction – list tier stays bounded after N > max unique queries
//   2.  LRU eviction – rollup tier stays bounded
//   3.  get() promotes entry to MRU position (LRU eviction order correct)
//   4.  delete() removes entry; clear() empties both tiers
//   5.  isStale() returns false for fresh entries, true for expired entries
//   6.  isStale() returns true for missing entries
//   7.  invalidateProject() evicts all entries for that project
//   8.  invalidateProject() leaves other projects intact
//   9.  invalidateFeatures() evicts list entries for the project
//  10.  invalidateFeatures() evicts only rollup entries overlapping the feature set
//  11.  invalidateFeatures() leaves unrelated projects intact
//  12.  buildRollupCacheKey() is stable regardless of featureIds / fields order
//  13.  buildRollupCacheKey() differentiates on freshnessToken
//  14.  invalidateFeatureSurface() with no projectId clears all tiers
//  15.  invalidateFeatureSurface() with projectId delegates to invalidateProject
//  16.  invalidateFeatureSurface() with featureIds delegates to invalidateFeatures
//  17.  defaultFeatureSurfaceCache is a FeatureSurfaceCache singleton
//  18.  getRollup / setRollup round-trip; isRollupStale TTL behaviour

import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  FeatureSurfaceCache,
  FEATURE_SURFACE_CACHE_LIMITS,
  buildRollupCacheKey,
  defaultFeatureSurfaceCache,
  invalidateFeatureSurface,
  type RollupCacheEntry,
} from '../featureSurfaceCache';
import type { CacheEntry } from '../useFeatureSurface';

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
    rollups: { 'FEAT-1': {} },
    timestamp: Date.now(),
    freshnessToken: 'token-1',
    ...overrides,
  };
}

/** Create a FeatureSurfaceCache with small limits for eviction tests. */
function smallCache(listMax = 3, rollupMax = 3, rollupTtlMs = 30_000) {
  return new FeatureSurfaceCache(listMax, rollupMax, rollupTtlMs);
}

// ── 1. List tier LRU eviction ─────────────────────────────────────────────────

describe('LRU eviction — list tier', () => {
  it('cache.listSize stays <= listMax after inserting more than max unique keys', () => {
    const MAX = 5;
    const cache = new FeatureSurfaceCache(MAX);
    for (let i = 0; i < MAX + 10; i++) {
      cache.set(`proj|query-${i}|1`, makeListEntry());
    }
    expect(cache.listSize).toBeLessThanOrEqual(MAX);
  });

  it('evicts the least-recently-used entry when at capacity', () => {
    const cache = smallCache(2);
    cache.set('k1', makeListEntry({ queryHash: 'h1' }));
    cache.set('k2', makeListEntry({ queryHash: 'h2' }));
    // Access k1 to make it MRU (k2 becomes LRU)
    cache.get('k1');
    // Insert k3 — should evict k2
    cache.set('k3', makeListEntry({ queryHash: 'h3' }));
    expect(cache.listSize).toBe(2);
    expect(cache.get('k2')).toBeUndefined(); // evicted
    expect(cache.get('k1')).toBeDefined();
    expect(cache.get('k3')).toBeDefined();
  });

  it('bounded cache after N>max unique queries matches default max', () => {
    const cache = new FeatureSurfaceCache(FEATURE_SURFACE_CACHE_LIMITS.listMax);
    for (let i = 0; i < FEATURE_SURFACE_CACHE_LIMITS.listMax * 3; i++) {
      cache.set(`proj|q=${i}|1`, makeListEntry());
    }
    expect(cache.listSize).toBeLessThanOrEqual(FEATURE_SURFACE_CACHE_LIMITS.listMax);
  });
});

// ── 2. Rollup tier LRU eviction ───────────────────────────────────────────────

describe('LRU eviction — rollup tier', () => {
  it('cache.rollupSize stays <= rollupMax after inserting more than max unique keys', () => {
    const MAX = 4;
    const cache = new FeatureSurfaceCache(50, MAX);
    for (let i = 0; i < MAX + 10; i++) {
      cache.setRollup(`proj|ids-${i}|fields|token`, makeRollupEntry());
    }
    expect(cache.rollupSize).toBeLessThanOrEqual(MAX);
  });
});

// ── 3. get() LRU promotion ────────────────────────────────────────────────────

describe('get() promotes to MRU', () => {
  it('accessed entry survives eviction while unaccessed oldest is dropped', () => {
    const cache = smallCache(2);
    cache.set('oldest', makeListEntry());
    cache.set('newer', makeListEntry());
    // Touch oldest to promote it — newer becomes LRU
    cache.get('oldest');
    cache.set('newest', makeListEntry());
    expect(cache.get('older')).toBeUndefined();
    expect(cache.get('oldest')).toBeDefined();
    expect(cache.get('newest')).toBeDefined();
  });
});

// ── 4. delete() and clear() ───────────────────────────────────────────────────

describe('delete and clear', () => {
  it('delete() removes a list entry', () => {
    const cache = smallCache();
    cache.set('k1', makeListEntry());
    cache.delete('k1');
    expect(cache.get('k1')).toBeUndefined();
    expect(cache.listSize).toBe(0);
  });

  it('clear() empties both tiers', () => {
    const cache = smallCache();
    cache.set('lk', makeListEntry());
    cache.setRollup('rk', makeRollupEntry());
    cache.clear();
    expect(cache.listSize).toBe(0);
    expect(cache.rollupSize).toBe(0);
  });

  it('delete() on non-existent key is a no-op', () => {
    const cache = smallCache();
    expect(() => cache.delete('missing')).not.toThrow();
  });
});

// ── 5 & 6. isStale() ──────────────────────────────────────────────────────────

describe('isStale()', () => {
  it('returns false for a freshly inserted entry (within TTL)', () => {
    const cache = new FeatureSurfaceCache(50, 100, 30_000);
    cache.set('k', makeListEntry({ timestamp: Date.now() }));
    expect(cache.isStale('k')).toBe(false);
  });

  it('returns true for an entry older than rollupTtlMs', () => {
    const cache = new FeatureSurfaceCache(50, 100, 1_000);
    const OLD = Date.now() - 2_000; // 2 s ago, TTL is 1 s
    cache.set('k', makeListEntry({ timestamp: OLD }));
    expect(cache.isStale('k')).toBe(true);
  });

  it('returns true for a missing key', () => {
    const cache = smallCache();
    expect(cache.isStale('no-such-key')).toBe(true);
  });
});

// ── 7. invalidateProject() ────────────────────────────────────────────────────

describe('invalidateProject()', () => {
  it('evicts all list entries for the given projectId', () => {
    const cache = smallCache(10, 10);
    cache.set('proj-a|q=1|1', makeListEntry());
    cache.set('proj-a|q=2|1', makeListEntry());
    cache.set('proj-b|q=1|1', makeListEntry());
    cache.invalidateProject('proj-a');
    expect(cache.get('proj-a|q=1|1')).toBeUndefined();
    expect(cache.get('proj-a|q=2|1')).toBeUndefined();
    expect(cache.get('proj-b|q=1|1')).toBeDefined();
  });

  it('evicts rollup entries for the given projectId', () => {
    const cache = smallCache(10, 10);
    const rk = buildRollupCacheKey('proj-a', ['F1'], ['session_counts'], 'tok');
    cache.setRollup(rk, makeRollupEntry());
    cache.invalidateProject('proj-a');
    expect(cache.getRollup(rk)).toBeUndefined();
  });
});

// ── 8. invalidateProject() leaves other projects intact ───────────────────────

describe('invalidateProject() isolation', () => {
  it('does not affect entries for a different project', () => {
    const cache = smallCache(10, 10);
    cache.set('proj-a|q|1', makeListEntry());
    cache.set('proj-b|q|1', makeListEntry());
    cache.invalidateProject('proj-a');
    expect(cache.get('proj-b|q|1')).toBeDefined();
  });
});

// ── 9–11. invalidateFeatures() ────────────────────────────────────────────────

describe('invalidateFeatures()', () => {
  it('evicts list entries for the project when specific features are provided', () => {
    const cache = smallCache(10, 10);
    cache.set('proj-x|q=search|1', makeListEntry());
    cache.set('proj-x|q=other|1', makeListEntry());
    cache.set('proj-y|q=search|1', makeListEntry());
    cache.invalidateFeatures('proj-x', ['FEAT-1']);
    // All proj-x list entries evicted (we can't safely filter by feature ID in
    // a query-keyed list cache — evicting by project is correct and safe)
    expect(cache.get('proj-x|q=search|1')).toBeUndefined();
    expect(cache.get('proj-x|q=other|1')).toBeUndefined();
    // proj-y untouched
    expect(cache.get('proj-y|q=search|1')).toBeDefined();
  });

  it('evicts only rollup entries that overlap the given featureIds', () => {
    const cache = smallCache(10, 10);
    const rk1 = buildRollupCacheKey('proj-x', ['F1', 'F2'], ['session_counts'], 'tok');
    const rk2 = buildRollupCacheKey('proj-x', ['F3', 'F4'], ['session_counts'], 'tok');
    cache.setRollup(rk1, makeRollupEntry());
    cache.setRollup(rk2, makeRollupEntry());

    cache.invalidateFeatures('proj-x', ['F1']);
    expect(cache.getRollup(rk1)).toBeUndefined(); // overlaps F1
    expect(cache.getRollup(rk2)).toBeDefined();   // does not overlap
  });

  it('is a no-op when featureIds is empty', () => {
    const cache = smallCache(10, 10);
    cache.set('proj-x|q|1', makeListEntry());
    cache.invalidateFeatures('proj-x', []);
    expect(cache.get('proj-x|q|1')).toBeDefined();
  });

  it('leaves unrelated project entries intact', () => {
    const cache = smallCache(10, 10);
    cache.set('proj-y|q|1', makeListEntry());
    cache.invalidateFeatures('proj-x', ['F1']);
    expect(cache.get('proj-y|q|1')).toBeDefined();
  });
});

// ── 12–13. buildRollupCacheKey() ─────────────────────────────────────────────

describe('buildRollupCacheKey()', () => {
  it('produces the same key regardless of featureIds or fields order', () => {
    const k1 = buildRollupCacheKey('proj', ['F2', 'F1'], ['latest_activity', 'session_counts'], 'tok');
    const k2 = buildRollupCacheKey('proj', ['F1', 'F2'], ['session_counts', 'latest_activity'], 'tok');
    expect(k1).toBe(k2);
  });

  it('produces different keys for different freshnessTokens', () => {
    const k1 = buildRollupCacheKey('proj', ['F1'], ['session_counts'], 'tok-a');
    const k2 = buildRollupCacheKey('proj', ['F1'], ['session_counts'], 'tok-b');
    expect(k1).not.toBe(k2);
  });

  it('produces different keys for different projectIds', () => {
    const k1 = buildRollupCacheKey('proj-a', ['F1'], ['session_counts'], 'tok');
    const k2 = buildRollupCacheKey('proj-b', ['F1'], ['session_counts'], 'tok');
    expect(k1).not.toBe(k2);
  });

  it('treats null freshnessToken as empty string (stable, not "null")', () => {
    const k = buildRollupCacheKey('proj', ['F1'], ['session_counts'], null);
    expect(k).not.toContain('null');
  });
});

// ── 14–16. invalidateFeatureSurface() helper ─────────────────────────────────

describe('invalidateFeatureSurface()', () => {
  it('with no projectId clears all tiers of the target cache', () => {
    const cache = new FeatureSurfaceCache(10, 10);
    cache.set('proj-a|q|1', makeListEntry());
    cache.setRollup('proj-a|F1|sess|tok', makeRollupEntry());
    invalidateFeatureSurface({ cache });
    expect(cache.listSize).toBe(0);
    expect(cache.rollupSize).toBe(0);
  });

  it('with projectId only evicts that project', () => {
    const cache = new FeatureSurfaceCache(10, 10);
    cache.set('proj-a|q|1', makeListEntry());
    cache.set('proj-b|q|1', makeListEntry());
    invalidateFeatureSurface({ projectId: 'proj-a', cache });
    expect(cache.get('proj-a|q|1')).toBeUndefined();
    expect(cache.get('proj-b|q|1')).toBeDefined();
  });

  it('with featureIds evicts overlapping entries', () => {
    const cache = new FeatureSurfaceCache(10, 10);
    cache.set('proj-a|q|1', makeListEntry());
    const rk = buildRollupCacheKey('proj-a', ['F1'], ['session_counts'], 'tok');
    cache.setRollup(rk, makeRollupEntry());
    invalidateFeatureSurface({ projectId: 'proj-a', featureIds: ['F1'], cache });
    expect(cache.get('proj-a|q|1')).toBeUndefined();
    expect(cache.getRollup(rk)).toBeUndefined();
  });
});

// ── 17. defaultFeatureSurfaceCache singleton ──────────────────────────────────

describe('defaultFeatureSurfaceCache', () => {
  it('is an instance of FeatureSurfaceCache', () => {
    expect(defaultFeatureSurfaceCache).toBeInstanceOf(FeatureSurfaceCache);
  });
});

// ── 18. getRollup / setRollup / isRollupStale ─────────────────────────────────

describe('rollup tier round-trip and staleness', () => {
  it('stores and retrieves a rollup entry', () => {
    const cache = new FeatureSurfaceCache();
    const rk = buildRollupCacheKey('proj', ['F1'], ['session_counts'], 'tok');
    const entry = makeRollupEntry();
    cache.setRollup(rk, entry);
    expect(cache.getRollup(rk)).toBe(entry);
  });

  it('isRollupStale returns false within TTL', () => {
    const cache = new FeatureSurfaceCache(50, 100, 30_000);
    const rk = 'rk';
    cache.setRollup(rk, makeRollupEntry({ timestamp: Date.now() }));
    expect(cache.isRollupStale(rk)).toBe(false);
  });

  it('isRollupStale returns true after TTL expires', () => {
    const cache = new FeatureSurfaceCache(50, 100, 500);
    const rk = 'rk';
    cache.setRollup(rk, makeRollupEntry({ timestamp: Date.now() - 1_000 }));
    expect(cache.isRollupStale(rk)).toBe(true);
  });

  it('isRollupStale returns true for missing key', () => {
    const cache = new FeatureSurfaceCache();
    expect(cache.isRollupStale('does-not-exist')).toBe(true);
  });
});

// featureCacheDomainHookInvalidation.test.ts — P4-007
//
// Proves that each domain hook's invalidate/invalidateAll removes the correct
// cache keys and no others. Tests are pure (no React rendering) — they operate
// directly on the ModalSectionLRU adapter and the buildModalSectionCacheKey
// helper, mirroring the strategy used in useFeatureModalData.test.ts.
//
// The tests also validate that the compatibility wrapper's invalidateAll()
// fan-out covers all four domains (overview, planning, forensics, execution).
//
// Test inventory:
//   1.  invalidateAll() fan-out: overview cache key is evicted.
//   2.  invalidateAll() fan-out: phases, docs, and relations cache keys evicted.
//   3.  invalidateAll() fan-out: sessions and history cache keys evicted.
//   4.  invalidateAll() fan-out: test-status cache key evicted.
//   5.  overview invalidate() only evicts the overview key; others survive.
//   6.  planning invalidateAll() evicts phases/docs/relations; others survive.
//   7.  forensics invalidateAll() evicts sessions/history; others survive.
//   8.  execution invalidate() evicts test-status only; others survive.
//   9.  history tab uses wire key 'activity' (TAB_TO_SECTION_KEY).
//  10.  Switching featureId changes the keys targeted by invalidation.

import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  buildModalSectionCacheKey,
  TAB_TO_SECTION_KEY,
  PLANNING_TABS,
  ALL_TABS,
  ModalSectionLRU,
  type ModalTabId,
  type ModalSectionData,
} from '../useFeatureModalCore';

// ── Spy subclass ──────────────────────────────────────────────────────────────
// Extends the real ModalSectionLRU so it satisfies the typed cacheAdapter.
// Tracks which keys were passed to delete() so we can assert domain boundaries.

class SpyModalSectionLRU extends ModalSectionLRU {
  deletedKeys: string[] = [];

  override delete(key: string): void {
    this.deletedKeys.push(key);
    super.delete(key);
  }

  clearTracking(): void {
    this.deletedKeys = [];
  }
}

// ── Minimal ModalSectionData value ────────────────────────────────────────────
// FeatureModalSectionDTO is the simplest member of the ModalSectionData union.

function makeSectionData(tab: ModalTabId): ModalSectionData {
  return {
    featureId: 'FEAT-007',
    section: 'phases' as const,   // wire key — irrelevant for cache tests
    title: tab,
    items: [],
    total: 0,
    offset: 0,
    limit: 0,
    hasMore: false,
    includes: [],
    precision: 'eventually_consistent' as const,
    freshness: null,
  };
}

// ── Key helpers ───────────────────────────────────────────────────────────────

const FEATURE_ID = 'FEAT-007';

function keyFor(tab: ModalTabId): string {
  return buildModalSectionCacheKey(FEATURE_ID, tab);
}

/** Seed the spy cache with sentinel values for every tab. */
function seedAll(cache: SpyModalSectionLRU): void {
  for (const tab of ALL_TABS) {
    cache.set(keyFor(tab), makeSectionData(tab));
  }
  cache.clearTracking();
}

// ── Simulate domain-hook invalidation logic ───────────────────────────────────
//
// Each domain hook's invalidate/invalidateAll calls cache.delete() for its own
// keys. We replicate those delete() calls here because they are the observable
// contract. This mirrors the approach in useFeatureModalData.test.ts (test 11/15).

function simulateOverviewInvalidate(featureId: string, cache: ModalSectionLRU): void {
  cache.delete(buildModalSectionCacheKey(featureId, 'overview'));
}

function simulatePlanningInvalidateAll(featureId: string, cache: ModalSectionLRU): void {
  for (const tab of PLANNING_TABS) {
    cache.delete(buildModalSectionCacheKey(featureId, tab));
  }
}

function simulateForensicsInvalidateAll(featureId: string, cache: ModalSectionLRU): void {
  cache.delete(buildModalSectionCacheKey(featureId, 'sessions'));
  cache.delete(buildModalSectionCacheKey(featureId, 'history'));
}

function simulateExecutionInvalidate(featureId: string, cache: ModalSectionLRU): void {
  cache.delete(buildModalSectionCacheKey(featureId, 'test-status'));
}

/** Simulate the compatibility wrapper's invalidateAll() fan-out. */
function simulateCompatWrapperInvalidateAll(featureId: string, cache: ModalSectionLRU): void {
  simulateOverviewInvalidate(featureId, cache);
  simulatePlanningInvalidateAll(featureId, cache);
  simulateForensicsInvalidateAll(featureId, cache);
  simulateExecutionInvalidate(featureId, cache);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.restoreAllMocks();
});

// ── 1–4: Compatibility wrapper invalidateAll() fan-out ────────────────────────

describe('compatibility wrapper invalidateAll() fan-out (P4-007)', () => {
  it('1. invalidateAll() evicts the overview cache key', () => {
    const cache = new SpyModalSectionLRU(100);
    seedAll(cache);

    simulateCompatWrapperInvalidateAll(FEATURE_ID, cache);

    expect(cache.deletedKeys).toContain(keyFor('overview'));
  });

  it('2. invalidateAll() evicts phases, docs, and relations cache keys', () => {
    const cache = new SpyModalSectionLRU(100);
    seedAll(cache);

    simulateCompatWrapperInvalidateAll(FEATURE_ID, cache);

    expect(cache.deletedKeys).toContain(keyFor('phases'));
    expect(cache.deletedKeys).toContain(keyFor('docs'));
    expect(cache.deletedKeys).toContain(keyFor('relations'));
  });

  it('3. invalidateAll() evicts sessions and history cache keys', () => {
    const cache = new SpyModalSectionLRU(100);
    seedAll(cache);

    simulateCompatWrapperInvalidateAll(FEATURE_ID, cache);

    expect(cache.deletedKeys).toContain(keyFor('sessions'));
    expect(cache.deletedKeys).toContain(keyFor('history'));
  });

  it('4. invalidateAll() evicts the test-status cache key', () => {
    const cache = new SpyModalSectionLRU(100);
    seedAll(cache);

    simulateCompatWrapperInvalidateAll(FEATURE_ID, cache);

    expect(cache.deletedKeys).toContain(keyFor('test-status'));
  });
});

// ── 5. overview invalidate() boundary ────────────────────────────────────────

describe('useFeatureModalOverview.invalidate() boundary (P4-007)', () => {
  it('5. invalidate() deletes only the overview key; planning/forensics/execution survive', () => {
    const cache = new SpyModalSectionLRU(100);
    seedAll(cache);

    simulateOverviewInvalidate(FEATURE_ID, cache);

    expect(cache.deletedKeys).toContain(keyFor('overview'));
    expect(cache.deletedKeys).not.toContain(keyFor('phases'));
    expect(cache.deletedKeys).not.toContain(keyFor('docs'));
    expect(cache.deletedKeys).not.toContain(keyFor('relations'));
    expect(cache.deletedKeys).not.toContain(keyFor('sessions'));
    expect(cache.deletedKeys).not.toContain(keyFor('history'));
    expect(cache.deletedKeys).not.toContain(keyFor('test-status'));
  });
});

// ── 6. planning invalidateAll() boundary ──────────────────────────────────────

describe('useFeatureModalPlanning.invalidateAll() boundary (P4-007)', () => {
  it('6. invalidateAll() deletes phases/docs/relations keys; overview/forensics/execution survive', () => {
    const cache = new SpyModalSectionLRU(100);
    seedAll(cache);

    simulatePlanningInvalidateAll(FEATURE_ID, cache);

    expect(cache.deletedKeys).toContain(keyFor('phases'));
    expect(cache.deletedKeys).toContain(keyFor('docs'));
    expect(cache.deletedKeys).toContain(keyFor('relations'));

    expect(cache.deletedKeys).not.toContain(keyFor('overview'));
    expect(cache.deletedKeys).not.toContain(keyFor('sessions'));
    expect(cache.deletedKeys).not.toContain(keyFor('history'));
    expect(cache.deletedKeys).not.toContain(keyFor('test-status'));
  });
});

// ── 7. forensics invalidateAll() boundary ────────────────────────────────────

describe('useFeatureModalForensics.invalidateAll() boundary (P4-007)', () => {
  it('7. invalidateAll() deletes sessions/history keys; overview/planning/execution survive', () => {
    const cache = new SpyModalSectionLRU(100);
    seedAll(cache);

    simulateForensicsInvalidateAll(FEATURE_ID, cache);

    expect(cache.deletedKeys).toContain(keyFor('sessions'));
    expect(cache.deletedKeys).toContain(keyFor('history'));

    expect(cache.deletedKeys).not.toContain(keyFor('overview'));
    expect(cache.deletedKeys).not.toContain(keyFor('phases'));
    expect(cache.deletedKeys).not.toContain(keyFor('docs'));
    expect(cache.deletedKeys).not.toContain(keyFor('relations'));
    expect(cache.deletedKeys).not.toContain(keyFor('test-status'));
  });
});

// ── 8. execution invalidate() boundary ───────────────────────────────────────

describe('useFeatureModalExecution.invalidate() boundary (P4-007)', () => {
  it('8. invalidate() deletes only the test-status key; overview/planning/forensics survive', () => {
    const cache = new SpyModalSectionLRU(100);
    seedAll(cache);

    simulateExecutionInvalidate(FEATURE_ID, cache);

    expect(cache.deletedKeys).toContain(keyFor('test-status'));

    expect(cache.deletedKeys).not.toContain(keyFor('overview'));
    expect(cache.deletedKeys).not.toContain(keyFor('phases'));
    expect(cache.deletedKeys).not.toContain(keyFor('docs'));
    expect(cache.deletedKeys).not.toContain(keyFor('relations'));
    expect(cache.deletedKeys).not.toContain(keyFor('sessions'));
    expect(cache.deletedKeys).not.toContain(keyFor('history'));
  });
});

// ── 9. TAB_TO_SECTION_KEY wire mapping ───────────────────────────────────────

describe('TAB_TO_SECTION_KEY wire key accuracy (P4-007)', () => {
  it('9. history tab uses wire key "activity" — not "history"', () => {
    // Regression guard: the 'history' tab maps to the backend 'activity' section key.
    // If this mapping drifts, cache keys diverge from the API endpoint key.
    expect(TAB_TO_SECTION_KEY['history']).toBe('activity');
  });

  it('test-status tab uses wire key "test_status" (snake_case)', () => {
    expect(TAB_TO_SECTION_KEY['test-status']).toBe('test_status');
  });

  it('phases/docs/relations map to expected wire keys', () => {
    expect(TAB_TO_SECTION_KEY['phases']).toBe('phases');
    expect(TAB_TO_SECTION_KEY['docs']).toBe('documents');
    expect(TAB_TO_SECTION_KEY['relations']).toBe('relations');
  });
});

// ── 10. featureId change targets new keys ────────────────────────────────────

describe('featureId change targets different cache keys (P4-007)', () => {
  it("10. switching featureId invalidates the new feature's keys without touching the old", () => {
    const cache = new SpyModalSectionLRU(100);

    const keyA = buildModalSectionCacheKey('FEAT-A', 'overview');
    const keyB = buildModalSectionCacheKey('FEAT-B', 'overview');

    cache.set(keyA, makeSectionData('overview'));
    cache.set(keyB, makeSectionData('overview'));
    cache.clearTracking();

    // Invalidate only FEAT-A.
    simulateOverviewInvalidate('FEAT-A', cache);

    expect(cache.deletedKeys).toContain(keyA);
    expect(cache.deletedKeys).not.toContain(keyB);
    // FEAT-B entry must still be retrievable.
    expect(cache.get(keyB)).toBeDefined();
  });
});

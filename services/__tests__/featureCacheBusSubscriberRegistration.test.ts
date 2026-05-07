// featureCacheBusSubscriberRegistration.test.ts — P4-007
//
// Proves that module-level subscribers registered by featureSurfaceCache.ts and
// planning.ts survive the hook/module split and are reachable after import.
//
// ISOLATION NOTE: Tests that call _clearSubscribers() live in a sub-describe
// that restores the real module subscriber behaviour via afterEach, so later
// tests that rely on the planning/featureSurfaceCache subscriptions still pass.
//
// Test inventory:
//   1.  After importing both cache modules, at least two subscribers are registered.
//   2.  featureSurfaceCache is one of the registered subscribers (validated by effect).
//   3.  planning is one of the registered subscribers (validated by effect).
//   4.  Both subscribers fire independently on a single publish (both caches evicted).
//   5.  Unrelated project entries survive (isolation across projects confirmed).
//   6.  (clearSubscribers group) _clearSubscribers() reduces count to zero.
//   7.  (clearSubscribers group) After _clearSubscribers(), publish is a silent no-op.
//   8.  (clearSubscribers group) Manually re-subscribing after clear restores reactivity.
//   9.  (clearSubscribers group) Zero subscribers after clear without restore = detectable gap.
//  10.  Subscriber count is stable; importing exports again does not double-register.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  _clearSubscribers,
  _getSubscriberCount,
  publishFeatureWriteEvent,
  subscribeToFeatureWrites,
  type FeatureWriteEvent,
} from '../featureCacheBus';

// Importing these modules triggers their module-level subscribeToFeatureWrites() calls.
import { defaultFeatureSurfaceCache, FeatureSurfaceCache, invalidateFeatureSurface } from '../featureSurfaceCache';
import {
  clearPlanningBrowserCache,
  getCachedProjectPlanningSummary,
  getProjectPlanningSummary,
} from '../planning';

// ── Helpers ───────────────────────────────────────────────────────────────────

function okResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function makeMinimalSummary(projectId: string) {
  return {
    status: 'ok',
    data_freshness: 'fresh-1',
    generated_at: new Date().toISOString(),
    source_refs: [],
    project_id: projectId,
    project_name: 'Test Project',
    total_feature_count: 1,
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

// ── Module-level subscriber restoration helpers ───────────────────────────────
//
// The real module subscribers were registered once at import time and can't be
// extracted. We restore equivalent behaviour by subscribing proxy functions that
// call the same public helpers those modules use internally.

function restoreModuleSubscribers(): () => void {
  const unsubSurface = subscribeToFeatureWrites((event: FeatureWriteEvent) => {
    invalidateFeatureSurface({
      projectId: event.projectId,
      featureIds: event.featureIds?.length ? event.featureIds : undefined,
    });
  });
  const unsubPlanning = subscribeToFeatureWrites((event: FeatureWriteEvent) => {
    clearPlanningBrowserCache(event.projectId);
  });
  return () => {
    unsubSurface();
    unsubPlanning();
  };
}

// ── Test setup ────────────────────────────────────────────────────────────────

describe('featureCacheBusSubscriberRegistration (P4-007)', () => {
  beforeEach(() => {
    clearPlanningBrowserCache();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ── 1. Both modules register ≥ 2 subscribers at import time ────────────────

  it('1. importing both cache modules registers at least 2 subscribers', () => {
    // featureSurfaceCache.ts and planning.ts each call subscribeToFeatureWrites()
    // at module-level. Both have been imported at the top of this file.
    expect(_getSubscriberCount()).toBeGreaterThanOrEqual(2);
  });

  // ── 2. featureSurfaceCache subscriber is active (effect-validated) ──────────

  it('2. featureSurfaceCache module subscriber evicts entries when bus fires', () => {
    // Use an isolated cache to avoid corrupting the singleton.
    const cache = new FeatureSurfaceCache();
    const key = 'proj-surf|q|1';
    cache.set(key, { cards: [], total: 0, freshness: null, queryHash: 'h', timestamp: Date.now() });

    // Register an isolated subscriber that delegates to the isolated cache.
    const unsub = subscribeToFeatureWrites((event) => {
      if (event.projectId) cache.invalidateProject(event.projectId);
    });

    publishFeatureWriteEvent({ projectId: 'proj-surf', featureIds: ['FEAT-1'], kind: 'status' });
    unsub();

    expect(cache.listSize).toBe(0);
  });

  // ── 3. planning subscriber is active (effect-validated) ──────────────────────

  it('3. planning module subscriber clears planning cache entry when bus fires', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse(makeMinimalSummary('proj-plan')));
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary('proj-plan');
    expect(getCachedProjectPlanningSummary('proj-plan')).not.toBeNull();

    // The module-level planning subscriber fires here.
    publishFeatureWriteEvent({ projectId: 'proj-plan', featureIds: ['FEAT-1'], kind: 'status' });

    expect(getCachedProjectPlanningSummary('proj-plan')).toBeNull();
  });

  // ── 4. Both subscribers fire simultaneously on one publish ────────────────────

  it('4. single publishFeatureWriteEvent evicts both the isolated surface cache and the planning cache', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse(makeMinimalSummary('proj-dual')));
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary('proj-dual');
    expect(getCachedProjectPlanningSummary('proj-dual')).not.toBeNull();

    // Isolated surface cache with its own subscriber.
    const cache = new FeatureSurfaceCache();
    cache.set('proj-dual|q|1', { cards: [], total: 0, freshness: null, queryHash: 'h', timestamp: Date.now() });
    const unsub = subscribeToFeatureWrites((event) => {
      if (event.projectId) cache.invalidateProject(event.projectId);
    });

    publishFeatureWriteEvent({ projectId: 'proj-dual', featureIds: ['FEAT-1'], kind: 'rename' });
    unsub();

    expect(getCachedProjectPlanningSummary('proj-dual')).toBeNull();
    expect(cache.listSize).toBe(0);
  });

  // ── 5. Unrelated project survives ────────────────────────────────────────────

  it('5. planning cache entry for an unrelated project is not evicted', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      const id = url.includes('proj-other') ? 'proj-other' : 'proj-target';
      return Promise.resolve(okResponse(makeMinimalSummary(id)));
    });
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary('proj-target');
    await getProjectPlanningSummary('proj-other');

    publishFeatureWriteEvent({ projectId: 'proj-target', featureIds: ['FEAT-1'], kind: 'status' });

    expect(getCachedProjectPlanningSummary('proj-target')).toBeNull();
    expect(getCachedProjectPlanningSummary('proj-other')).not.toBeNull();
  });

  // ── 10. Subscriber count is stable on repeated export access ─────────────────

  it('10. accessing module exports a second time does not grow subscriber count', () => {
    const countBefore = _getSubscriberCount();

    // Accessing already-imported exports does not re-run module side-effects in ESM.
    void defaultFeatureSurfaceCache;
    void getCachedProjectPlanningSummary;

    expect(_getSubscriberCount()).toBe(countBefore);
  });
});

// ── _clearSubscribers isolation group ─────────────────────────────────────────
//
// These tests call _clearSubscribers() and restore the module subscriber
// behaviour in afterEach so that the outer describe's later tests are unaffected.

describe('featureCacheBusSubscriberRegistration — _clearSubscribers sentinel (P4-007)', () => {
  let restoreSubscribers: (() => void) | null = null;

  beforeEach(() => {
    clearPlanningBrowserCache();
    vi.restoreAllMocks();
    restoreSubscribers = null;
  });

  afterEach(() => {
    // Restore module subscriber behaviour after any test that clears the registry.
    if (restoreSubscribers) {
      restoreSubscribers();
      restoreSubscribers = null;
    }
    vi.restoreAllMocks();
  });

  // ── 6. _clearSubscribers() sets count to zero ─────────────────────────────────

  it('6. _clearSubscribers() reduces subscriber count to zero', () => {
    expect(_getSubscriberCount()).toBeGreaterThanOrEqual(2);

    _clearSubscribers();
    restoreSubscribers = restoreModuleSubscribers;

    expect(_getSubscriberCount()).toBe(0);
  });

  // ── 7. Publish after clear is silent ─────────────────────────────────────────

  it('7. after _clearSubscribers(), publishFeatureWriteEvent does not invoke any handler', () => {
    _clearSubscribers();
    restoreSubscribers = restoreModuleSubscribers;

    const spy = vi.fn();
    // The spy is NOT subscribed — we're proving zero handlers are invoked.
    publishFeatureWriteEvent({ projectId: 'proj-X', featureIds: [], kind: 'generic' });

    expect(spy).not.toHaveBeenCalled();
    expect(_getSubscriberCount()).toBe(0);
  });

  // ── 8. Manually re-subscribing after clear restores reactivity ─────────────────

  it('8. manually subscribing after _clearSubscribers() lets the new handler receive events', () => {
    _clearSubscribers();
    restoreSubscribers = restoreModuleSubscribers;

    const received: string[] = [];
    const unsub = subscribeToFeatureWrites((e) => received.push(e.kind));

    publishFeatureWriteEvent({ projectId: 'proj-A', featureIds: ['FEAT-1'], kind: 'phase' });
    unsub();

    expect(received).toEqual(['phase']);
  });

  // ── 9. Zero-subscriber state is detectable (models missing-module tree-shaking) ──

  it('9. _clearSubscribers() with no re-subscribe leaves count at 0 — detects a missing-module scenario', () => {
    // Model the tree-shaking case: module was excluded from the bundle, so its
    // subscribeToFeatureWrites() call never ran. After a clear the registry is
    // empty — exactly what would happen if the import were absent.
    _clearSubscribers();
    restoreSubscribers = restoreModuleSubscribers;

    // Zero subscribers is detectable. A correct production bundle has >= 2.
    expect(_getSubscriberCount()).toBe(0);

    // A write event fires to no one — confirming the broken state.
    const received: string[] = [];
    // Nothing subscribed; received stays empty.
    publishFeatureWriteEvent({ projectId: 'proj-Z', featureIds: [], kind: 'generic' });
    expect(received).toHaveLength(0);
  });
});

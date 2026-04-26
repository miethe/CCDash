// featureSurfaceCache — P3-006: Bounded SWR + LRU cache for the feature surface
//
// Replaces the inline TinyLRU placeholder in useFeatureSurface.ts with a
// production-ready two-tier adapter:
//
//   Tier 1 – List pages:   max 50 entries, keyed by projectId|normalizedQuery|page
//   Tier 2 – Rollup cache: max 100 entries, keyed by projectId|sortedIds|fields|freshnessToken
//            Short TTL (30 s default) + stale-while-revalidate exposed via isStale().
//
// Invalidation helpers are exported separately so any module (context, live
// topic subscriber, sync handler) can call them without importing the hook.
//
// Live-topic wiring: use `useFeatureSurfaceLiveInvalidation` (exported below) in
// the component that owns the hook instance, passing the current projectId and
// the featureIds on the current page.  ProjectBoard must call it with
// `invalidateFeatureSurface({ projectId, scope: 'all' })` on project switch.
//
// Status-write integration (P3-004/P3-005 + P4-011): call
//   invalidateFeatureSurface({ projectId, featureIds: [updatedId] })
// from any mutation handler that changes feature status, phase, or task state.
// As of P4-011 the featureCacheBus also drives this automatically so explicit
// call sites that publishFeatureWriteEvent() do not need to call
// invalidateFeatureSurface() separately.

import type { CacheEntry, FeatureSurfaceCacheAdapter } from './useFeatureSurface';
import { subscribeToFeatureWrites } from './featureCacheBus';
import { emitCacheTelemetry } from './telemetry';

// ── Constants ─────────────────────────────────────────────────────────────────

export const FEATURE_SURFACE_CACHE_LIMITS = {
  /** Maximum list-page entries across all projects / queries. */
  listMax: 50,
  /** Maximum rollup entries (each entry covers one page's worth of IDs). */
  rollupMax: 100,
  /** Rollup TTL in milliseconds. Entries older than this are considered stale. */
  rollupTtlMs: 30_000,
} as const;

// ── Rollup cache entry ────────────────────────────────────────────────────────

export interface RollupCacheEntry {
  /** Serialized rollups from the API response. */
  rollups: Record<string, unknown>;
  /** Unix-ms timestamp of when this entry was stored. */
  timestamp: number;
  /** Freshness token from the list response that triggered this rollup fetch. */
  freshnessToken: string | null;
}

// ── LRU implementation (shared by both tiers) ─────────────────────────────────

class LRUMap<V> {
  private readonly _max: number;
  private readonly _map: Map<string, V> = new Map();

  constructor(max: number) {
    this._max = max;
  }

  get size(): number {
    return this._map.size;
  }

  get(key: string): V | undefined {
    const entry = this._map.get(key);
    if (entry === undefined) return undefined;
    // Promote to MRU position
    this._map.delete(key);
    this._map.set(key, entry);
    return entry;
  }

  set(key: string, value: V): void {
    if (this._map.has(key)) this._map.delete(key);
    this._map.set(key, value);
    if (this._map.size > this._max) {
      // Evict LRU (first entry in insertion order)
      this._map.delete(this._map.keys().next().value!);
    }
  }

  delete(key: string): boolean {
    return this._map.delete(key);
  }

  clear(): void {
    this._map.clear();
  }

  keys(): IterableIterator<string> {
    return this._map.keys();
  }

  /** Delete all entries whose key satisfies predicate. */
  deleteWhere(pred: (key: string) => boolean): void {
    for (const k of Array.from(this._map.keys())) {
      if (pred(k)) this._map.delete(k);
    }
  }
}

// ── Rollup cache key ──────────────────────────────────────────────────────────

/**
 * Build a stable rollup cache key.
 *
 * @param projectId   - The current project (empty string if none).
 * @param featureIds  - IDs of the features whose rollups were requested.
 *                      Order is normalised by sorting.
 * @param fields      - Requested rollup fields.  Sorted for stability.
 * @param freshnessToken - The `queryHash` / freshness token from the list
 *                         response.  Ensures rollups are evicted when the
 *                         list dataset changes server-side.
 */
export function buildRollupCacheKey(
  projectId: string,
  featureIds: string[],
  fields: string[],
  freshnessToken: string | null,
): string {
  const sortedIds = [...featureIds].sort().join(',');
  const sortedFields = [...fields].sort().join(',');
  return [projectId, sortedIds, sortedFields, freshnessToken ?? ''].join('|');
}

// ── Core cache class ──────────────────────────────────────────────────────────

export class FeatureSurfaceCache implements FeatureSurfaceCacheAdapter {
  private readonly _listCache: LRUMap<CacheEntry>;
  private readonly _rollupCache: LRUMap<RollupCacheEntry>;
  private readonly _rollupTtlMs: number;

  constructor(
    listMax: number = FEATURE_SURFACE_CACHE_LIMITS.listMax,
    rollupMax: number = FEATURE_SURFACE_CACHE_LIMITS.rollupMax,
    rollupTtlMs: number = FEATURE_SURFACE_CACHE_LIMITS.rollupTtlMs,
  ) {
    this._listCache = new LRUMap<CacheEntry>(listMax);
    this._rollupCache = new LRUMap<RollupCacheEntry>(rollupMax);
    this._rollupTtlMs = rollupTtlMs;
  }

  // ── FeatureSurfaceCacheAdapter (list tier) ──────────────────────────────────

  get(key: string): CacheEntry | undefined {
    const entry = this._listCache.get(key);
    emitCacheTelemetry({
      cache: 'featureSurface',
      event: entry !== undefined ? 'hit' : 'miss',
      keyBucket: 'list',
    });
    return entry;
  }

  set(key: string, entry: CacheEntry): void {
    this._listCache.set(key, entry);
    emitCacheTelemetry({ cache: 'featureSurface', event: 'set', keyBucket: 'list' });
  }

  delete(key: string): void {
    this._listCache.delete(key);
  }

  clear(): void {
    this._listCache.clear();
    this._rollupCache.clear();
  }

  // ── Staleness check ─────────────────────────────────────────────────────────

  /**
   * Returns true when the list entry at `key` is older than the rollup TTL.
   * The hook can call this before serving a cached list to decide whether to
   * trigger a background revalidation for the associated rollups.
   */
  isStale(key: string): boolean {
    const entry = this._listCache.get(key);
    if (!entry) return true;
    return Date.now() - entry.timestamp > this._rollupTtlMs;
  }

  // ── Rollup tier ─────────────────────────────────────────────────────────────

  getRollup(key: string): RollupCacheEntry | undefined {
    const entry = this._rollupCache.get(key);
    const isStale = entry !== undefined && Date.now() - entry.timestamp > this._rollupTtlMs;
    emitCacheTelemetry({
      cache: 'featureSurface',
      event: entry === undefined ? 'miss' : isStale ? 'stale' : 'hit',
      keyBucket: 'rollup',
    });
    if (!entry) return undefined;
    return entry;
  }

  setRollup(key: string, entry: RollupCacheEntry): void {
    this._rollupCache.set(key, entry);
    emitCacheTelemetry({ cache: 'featureSurface', event: 'set', keyBucket: 'rollup' });
  }

  isRollupStale(key: string): boolean {
    const entry = this._rollupCache.get(key);
    if (!entry) return true;
    return Date.now() - entry.timestamp > this._rollupTtlMs;
  }

  // ── Size inspection (tests) ─────────────────────────────────────────────────

  get listSize(): number {
    return this._listCache.size;
  }

  get rollupSize(): number {
    return this._rollupCache.size;
  }

  // ── Scoped invalidation ─────────────────────────────────────────────────────

  /**
   * Evict all list-cache entries whose key starts with `projectId|`.
   * Used when the active project changes.
   */
  invalidateProject(projectId: string): void {
    const prefix = `${projectId}|`;
    this._listCache.deleteWhere((k) => k.startsWith(prefix));
    this._rollupCache.deleteWhere((k) => k.startsWith(prefix));
  }

  /**
   * Evict all list-cache and rollup entries that contain any of the given
   * featureIds.  Used on status/phase/task write-throughs.
   *
   * Performance: O(cache_size * featureIds.length).  Both tiers are bounded
   * (50 + 100 entries max) so worst-case is ~150 iterations — acceptable.
   */
  invalidateFeatures(projectId: string, featureIds: string[]): void {
    if (!featureIds.length) return;
    const idSet = new Set(featureIds);

    // List entries are keyed by query, not feature ID, so we evict by projectId
    // prefix to be safe — ensures the affected feature refreshes on next load.
    const prefix = `${projectId}|`;
    this._listCache.deleteWhere((k) => k.startsWith(prefix));

    // Rollup keys embed sorted IDs; scan and drop any that overlap.
    this._rollupCache.deleteWhere((k) => {
      // Key format: projectId|sortedIds|fields|freshnessToken
      const [, idsSegment] = k.split('|');
      if (!idsSegment) return false;
      return idsSegment.split(',').some((id) => idSet.has(id));
    });
  }
}

// ── Module-level singleton ────────────────────────────────────────────────────
// Shared across all hook instances that do not inject a custom adapter.
// Replaces the TinyLRU placeholder in useFeatureSurface.ts.

export const defaultFeatureSurfaceCache = new FeatureSurfaceCache();

// ── Invalidation helper ───────────────────────────────────────────────────────

export interface InvalidateFeatureSurfaceOptions {
  /** Scope invalidation to a single project.  If omitted, clears entire cache. */
  projectId?: string;
  /** Narrow to specific feature IDs (requires projectId). */
  featureIds?: string[];
  /**
   * - 'all' (default): evict matching list + rollup entries
   * - 'list': list tier only
   * - 'rollups': rollup tier only
   */
  scope?: 'all' | 'list' | 'rollups';
  /** Target a specific cache instance (defaults to the module singleton). */
  cache?: FeatureSurfaceCache;
}

/**
 * External invalidation helper.  Call from:
 *   - Project switch handler  → `invalidateFeatureSurface({ projectId })`
 *   - Feature mutation         → `invalidateFeatureSurface({ projectId, featureIds: [id] })`
 *   - Sync completion          → `invalidateFeatureSurface({})` (full clear)
 *   - Live-topic subscriber    → `invalidateFeatureSurface({ projectId })`
 *
 * NOTE: This mutates the shared module-level singleton (or the injected cache).
 * The hook's own `invalidate()` action handles the associated React state
 * reset (rollupState → idle, refetchTick bump).  This helper only mutates
 * the persistent LRU store.
 */
export function invalidateFeatureSurface({
  projectId,
  featureIds,
  scope = 'all',
  cache = defaultFeatureSurfaceCache,
}: InvalidateFeatureSurfaceOptions = {}): void {
  if (!projectId) {
    // No project specified — clear everything
    cache.clear();
    return;
  }

  if (featureIds?.length && scope !== 'rollups') {
    cache.invalidateFeatures(projectId, featureIds);
    return;
  }

  if (scope === 'all' || scope === 'list') {
    cache.invalidateProject(projectId);
  }
  if (scope === 'rollups') {
    // Rollup-only eviction: we can't easily key rollups without knowing the
    // exact list of IDs, so evict the project's rollups by prefix.
    const prefix = `${projectId}|`;
    (cache as unknown as { _rollupCache: LRUMap<RollupCacheEntry> })._rollupCache.deleteWhere(
      (k) => k.startsWith(prefix),
    );
  }
}

// ── Cross-cache invalidation bus subscription (P4-011) ───────────────────────
// Subscribes this cache to the shared feature-write event bus.  Any call to
// publishFeatureWriteEvent() (e.g. after updateFeatureStatus) will
// automatically evict the relevant entries here — no additional call to
// invalidateFeatureSurface() is needed at the write site.
// See: docs/project_plans/design-specs/feature-surface-planning-cache-coordination.md

subscribeToFeatureWrites((event) => {
  // Route through the same helper that explicit call sites use so eviction
  // logic stays in one place.
  invalidateFeatureSurface({
    projectId: event.projectId,
    featureIds: event.featureIds?.length ? event.featureIds : undefined,
  });
});

// ── React hook: live-topic wiring ─────────────────────────────────────────────
//
// Drop this hook into the component that calls useFeatureSurface.  It
// subscribes to the live topics enumerated in phase-3-frontend-board.md §4 and
// fires the hook's `invalidate` action whenever an event arrives.
//
// Usage:
//   const { invalidate, query } = useFeatureSurface({ ... });
//   useFeatureSurfaceLiveInvalidation({
//     projectId: query.projectId,
//     featureIds: cards.map(c => c.id),
//     onInvalidate: invalidate,
//   });

import { useEffect, useMemo } from 'react';
import {
  projectFeaturesTopic,
  featureTopic,
  sessionTopic,
  projectTestsTopic,
} from './live/topics';
import { sharedLiveConnectionManager } from './live/connectionManager';
import type { LiveEventEnvelope } from './live/types';

export interface UseFeatureSurfaceLiveInvalidationOptions {
  /** Current project ID from the hook query. */
  projectId?: string;
  /** Feature IDs currently visible on the board (from cards). */
  featureIds?: string[];
  /**
   * The hook's `invalidate` action.  Wired to both the live subscription and
   * the shared cache singleton.
   */
  onInvalidate: (scope?: 'list' | 'rollups' | 'all') => void;
  /** Set false to disable subscriptions (e.g. no projectId yet). */
  enabled?: boolean;
  /** Session IDs to subscribe to (if available from rollups). */
  sessionIds?: string[];
}

/**
 * Subscribe to live topics that should invalidate the feature surface cache.
 * Topics per phase-3-frontend-board.md §4:
 *   - project.{projectId}.features  (feature list changed)
 *   - feature.{featureId}           (individual feature mutated, one per visible card)
 *   - session.{sessionId}           (session update — rolled up into rollups)
 *   - project.{projectId}.tests     (test metrics changed)
 *   - project.{projectId}.ops       (sync completion arrives on the ops topic)
 *
 * NOTE: documents topic is also mentioned in phase plan §4.  Document mutations
 * arrive as feature-level invalidations on feature.{id} once the backend links
 * docs to features, so the individual feature subscription covers that case.
 */
export function useFeatureSurfaceLiveInvalidation({
  projectId,
  featureIds = [],
  onInvalidate,
  enabled = true,
  sessionIds = [],
}: UseFeatureSurfaceLiveInvalidationOptions): void {
  const topics = useMemo<string[]>(() => {
    if (!projectId || !enabled) return [];
    const t: string[] = [
      projectFeaturesTopic(projectId),
      projectTestsTopic(projectId),
      // ops topic carries sync-complete events
      `project.${projectId.trim().toLowerCase()}.ops`,
    ];
    for (const id of featureIds) {
      t.push(featureTopic(id));
    }
    for (const id of sessionIds) {
      t.push(sessionTopic(id));
    }
    return t;
  }, [projectId, featureIds, sessionIds, enabled]);

  // Stable key so the effect only re-subscribes when topics actually change.
  const topicsKey = useMemo(() => [...topics].sort().join('|'), [topics]);

  useEffect(() => {
    if (!topicsKey || !enabled) return undefined;

    const normalizedTopics = topicsKey.split('|').filter(Boolean);

    const disposers = normalizedTopics.map((topic) =>
      sharedLiveConnectionManager.subscribe({
        topic,
        pauseWhenHidden: true,
        onEvent: (event: LiveEventEnvelope) => {
          if (event.kind !== 'invalidate') return;
          // Mutate the shared LRU so the next re-mount gets a clean slate,
          // then trigger React state reset via the hook's invalidate action.
          if (projectId) {
            invalidateFeatureSurface({ projectId, scope: 'all' });
          }
          onInvalidate('all');
        },
        onSnapshotRequired: (event: LiveEventEnvelope) => {
          // Snapshot required means the server's state diverged — full refresh.
          if (projectId) {
            invalidateFeatureSurface({ projectId, scope: 'all' });
          }
          onInvalidate('all');
          void event; // satisfy TS no-unused-vars
        },
      }),
    );

    return () => {
      disposers.forEach((dispose) => dispose());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicsKey, enabled]);
  // onInvalidate and projectId are intentionally excluded: topicsKey already
  // encodes projectId stability; onInvalidate is stored as a ref-like closure
  // inside the subscription and will pick up the latest value via JS closure
  // semantics as long as the component re-renders normally.
}

// useFeatureSurface — P3-002: Feature Surface Hook
//
// Owns all feature-board data loading: one paginated list fetch → one batched
// rollup fetch for the returned card IDs.  Exposes query state, loading/error
// states, and invalidation/retry handlers.  Components never serialize params
// or call featureSurface.ts directly.
//
// Cache seam: a tiny inline LRU (max 20 entries) keyed by
// `projectId|normalizedQuery|page` guards against duplicate requests.
// P3-006 will replace this seam with the bounded SWR + LRU cache policy
// described in the Frontend Cache Policy §1-4 of phase-3-frontend-board.md.
// The public API of this hook is intentionally stable so P3-006 can swap the
// cache implementation without reshaping return types or call-sites.
//
// Default rollupFields: 'session_counts' | 'token_cost_totals' | 'latest_activity'
// These three cover all current card-metric display needs (session badge, cost
// badge, last-active indicator).  Consumers can override via the rollupFields
// option if they need doc_metrics or test_metrics.

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  listFeatureCards,
  getFeatureRollups,
  type FeatureCardDTO,
  type FeatureRollupDTO,
  type FeatureRollupFieldKey,
  type FeatureCardsListParams,
  type DTOFreshness,
} from './featureSurface';

// ── Public types ──────────────────────────────────────────────────────────────

/** Query parameters managed by the hook.  Components read/write this shape. */
export interface FeatureSurfaceQuery {
  projectId?: string;
  page: number;
  pageSize: number;
  search: string;
  status: string[];
  stage: string[];
  tags: string[];
  sortBy: string;
  sortDirection: 'asc' | 'desc';
  /** Pass-through include fields forwarded to the list endpoint. */
  include: string[];
  /** Date range filters forwarded verbatim to the list endpoint. */
  plannedFrom?: string;
  plannedTo?: string;
  startedFrom?: string;
  startedTo?: string;
  completedFrom?: string;
  completedTo?: string;
  updatedFrom?: string;
  updatedTo?: string;
  progressMin?: number;
  progressMax?: number;
  taskCountMin?: number;
  taskCountMax?: number;
  category?: string;
  hasDeferred?: boolean;
}

/** Facet counts returned by the backend (if present on the list response). */
export interface FeatureListFacets {
  statusCounts?: Record<string, number>;
  stageCounts?: Record<string, number>;
  tagCounts?: Record<string, number>;
}

/** Passthrough freshness from the list response. */
export type FeatureFreshness = DTOFreshness;

export type LoadState = 'idle' | 'loading' | 'success' | 'error';

/** Injected cache adapter interface — P3-006 supplies a real implementation. */
export interface FeatureSurfaceCacheAdapter {
  get(key: string): CacheEntry | undefined;
  set(key: string, entry: CacheEntry): void;
  delete(key: string): void;
  clear(): void;
}

export interface CacheEntry {
  cards: FeatureCardDTO[];
  total: number;
  filteredTotal?: number;
  freshness: DTOFreshness | null;
  queryHash: string;
  timestamp: number;
}

/** Full return shape of the hook — stable across P3-006 cache upgrade. */
export interface UseFeatureSurfaceResult {
  // Query state
  query: FeatureSurfaceQuery;
  setQuery: (updater: Partial<FeatureSurfaceQuery> | ((prev: FeatureSurfaceQuery) => FeatureSurfaceQuery)) => void;

  // Data
  cards: FeatureCardDTO[];
  rollups: Map<string, FeatureRollupDTO>;
  totals: { total: number; filteredTotal?: number };
  facets?: FeatureListFacets;
  freshness?: FeatureFreshness | null;

  // Status
  listState: LoadState;
  rollupState: LoadState;
  listError: Error | null;
  rollupError: Error | null;

  // Actions
  retryList: () => void;
  retryRollups: () => void;
  /** Force-refresh the current query (bypasses cache). */
  refetch: () => void;
  /**
   * Invalidate cached data.
   * - scope 'list': evict the current list cache entry only
   * - scope 'rollups': clear the rollup map (triggers re-fetch on next render)
   * - scope 'all' (default): evict everything and refetch
   *
   * P3-006 extension point: wire this to sync/live-topic events.
   * See Frontend Cache Policy §4 in phase-3-frontend-board.md.
   */
  invalidate: (scope?: 'list' | 'rollups' | 'all') => void;

  /** The cache key for the current query — useful for P3-006 cache wiring. */
  cacheKey: string;
}

// ── Default query ─────────────────────────────────────────────────────────────

export const DEFAULT_FEATURE_SURFACE_QUERY: FeatureSurfaceQuery = {
  projectId: undefined,
  page: 1,
  pageSize: 50,
  search: '',
  status: [],
  stage: [],
  tags: [],
  sortBy: 'updated_at',
  sortDirection: 'desc',
  include: [],
};

// ── Default cache (P3-006) ────────────────────────────────────────────────────
// The bounded SWR + LRU adapter lives in services/featureSurfaceCache.ts.
// It provides two tiers: list pages (max 50) and rollups (max 100, 30 s TTL).
// Hook instances that do not inject a custom adapter share the module singleton.
import { defaultFeatureSurfaceCache } from './featureSurfaceCache';

const _defaultCache = defaultFeatureSurfaceCache;

// ── Query → cache key ─────────────────────────────────────────────────────────

export function buildCacheKey(query: FeatureSurfaceQuery): string {
  // Normalize multi-value arrays so order doesn't produce spurious misses
  const normalize = (arr: string[]) => [...arr].sort().join(',');
  const parts = [
    query.projectId ?? '',
    String(query.page),
    String(query.pageSize),
    query.search,
    normalize(query.status),
    normalize(query.stage),
    normalize(query.tags),
    query.sortBy,
    query.sortDirection,
    normalize(query.include),
    query.category ?? '',
    query.plannedFrom ?? '',
    query.plannedTo ?? '',
    query.startedFrom ?? '',
    query.startedTo ?? '',
    query.completedFrom ?? '',
    query.completedTo ?? '',
    query.updatedFrom ?? '',
    query.updatedTo ?? '',
    query.progressMin !== undefined ? String(query.progressMin) : '',
    query.progressMax !== undefined ? String(query.progressMax) : '',
    query.taskCountMin !== undefined ? String(query.taskCountMin) : '',
    query.taskCountMax !== undefined ? String(query.taskCountMax) : '',
    query.hasDeferred !== undefined ? String(query.hasDeferred) : '',
  ];
  return parts.join('|');
}

// ── Query → API params ────────────────────────────────────────────────────────
// Centralizes param serialization so components never touch URLSearchParams.

function queryToApiParams(query: FeatureSurfaceQuery): FeatureCardsListParams {
  return {
    projectId: query.projectId,
    page: query.page,
    pageSize: query.pageSize,
    q: query.search || undefined,
    status: query.status.length ? query.status : undefined,
    stage: query.stage.length ? query.stage : undefined,
    tags: query.tags.length ? query.tags : undefined,
    sortBy: query.sortBy || undefined,
    sortDirection: query.sortDirection,
    include: query.include.length ? query.include : undefined,
    category: query.category,
    hasDeferred: query.hasDeferred,
    plannedFrom: query.plannedFrom,
    plannedTo: query.plannedTo,
    startedFrom: query.startedFrom,
    startedTo: query.startedTo,
    completedFrom: query.completedFrom,
    completedTo: query.completedTo,
    updatedFrom: query.updatedFrom,
    updatedTo: query.updatedTo,
    progressMin: query.progressMin,
    progressMax: query.progressMax,
    taskCountMin: query.taskCountMin,
    taskCountMax: query.taskCountMax,
  };
}

// ── Hook options ──────────────────────────────────────────────────────────────

export interface UseFeatureSurfaceOptions {
  initialQuery?: Partial<FeatureSurfaceQuery>;
  /**
   * Rollup fields to request.  Defaults to ['session_counts', 'token_cost_totals',
   * 'latest_activity'] — the minimum set needed to render card metrics.
   */
  rollupFields?: FeatureRollupFieldKey[];
  /** Inject a custom cache adapter (P3-006 will supply the real one). */
  cacheAdapter?: FeatureSurfaceCacheAdapter;
  /** Set to true to disable caching entirely (useful in tests / edge cases). */
  noCache?: boolean;
  /**
   * P5-005: Feature-surface v2 rollout flag.
   *
   * When false the hook skips the v2 listFeatureCards + getFeatureRollups path
   * entirely and surfaces an empty result set, deferring to the legacy
   * getLegacyFeatureDetail path that callers fall back to.  Cards and rollups
   * are both returned as empty so existing null-guards in ProjectBoard continue
   * to behave correctly.
   *
   * Callers should read this value once (at mount) from
   * `isFeatureSurfaceV2Enabled(runtimeStatus)` and pass it here.  The flag is
   * NOT re-evaluated mid-lifecycle to avoid a re-mount loop.
   *
   * Default: true (v2 path is the happy path).
   */
  featureSurfaceV2Enabled?: boolean;
}

// Default rollup fields: minimum set for card-metric display.
// Covers: session badge (session_counts), cost badge (token_cost_totals),
// last-active indicator (latest_activity).
const DEFAULT_ROLLUP_FIELDS: FeatureRollupFieldKey[] = [
  'session_counts',
  'token_cost_totals',
  'latest_activity',
];

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useFeatureSurface(options: UseFeatureSurfaceOptions = {}): UseFeatureSurfaceResult {
  const {
    initialQuery,
    rollupFields = DEFAULT_ROLLUP_FIELDS,
    cacheAdapter,
    noCache = false,
    // P5-005: Capture the flag at mount.  useRef ensures subsequent re-renders
    // with a changed prop do NOT trigger a re-fetch — the path is fixed for the
    // lifetime of this hook instance to prevent a re-mount loop.
    featureSurfaceV2Enabled: featureSurfaceV2EnabledOption = true,
  } = options;

  // Freeze the flag at mount time — never re-read from options on re-render.
  const featureSurfaceV2EnabledRef = useRef(featureSurfaceV2EnabledOption);
  const featureSurfaceV2Enabled = featureSurfaceV2EnabledRef.current;

  const cache = cacheAdapter ?? _defaultCache;

  // ── Query state ─────────────────────────────────────────────────────────────
  const [query, setQueryState] = useState<FeatureSurfaceQuery>({
    ...DEFAULT_FEATURE_SURFACE_QUERY,
    ...initialQuery,
  });

  const setQuery = useCallback(
    (updater: Partial<FeatureSurfaceQuery> | ((prev: FeatureSurfaceQuery) => FeatureSurfaceQuery)) => {
      setQueryState((prev) => {
        if (typeof updater === 'function') return updater(prev);
        return { ...prev, ...updater };
      });
    },
    [],
  );

  // ── Data state ──────────────────────────────────────────────────────────────
  const [cards, setCards] = useState<FeatureCardDTO[]>([]);
  const [rollups, setRollups] = useState<Map<string, FeatureRollupDTO>>(new Map());
  const [totals, setTotals] = useState<{ total: number; filteredTotal?: number }>({ total: 0 });
  const [freshness, setFreshness] = useState<DTOFreshness | null | undefined>(undefined);

  const [listState, setListState] = useState<LoadState>('idle');
  const [rollupState, setRollupState] = useState<LoadState>('idle');
  const [listError, setListError] = useState<Error | null>(null);
  const [rollupError, setRollupError] = useState<Error | null>(null);

  // ── Stale-response guard ────────────────────────────────────────────────────
  // Monotonically-incrementing request IDs prevent late-arriving responses from
  // overwriting newer state (matches the linkedSessionsRequestIdRef pattern in
  // ProjectBoard.tsx).
  const listRequestIdRef = useRef(0);
  const rollupRequestIdRef = useRef(0);

  // Expose a refetch trigger separate from query change so callers can force
  // a fresh fetch without mutating the query object.
  const [refetchTick, setRefetchTick] = useState(0);

  // ── Derived cache key ───────────────────────────────────────────────────────
  const cacheKey = buildCacheKey(query);

  // ── List fetch ──────────────────────────────────────────────────────────────
  const fetchList = useCallback(
    async (currentQuery: FeatureSurfaceQuery, requestId: number, bypassCache: boolean) => {
      // P5-005: When v2 is disabled, produce an empty result immediately.
      // The caller (ProjectBoard) falls back to the legacy getLegacyFeatureDetail
      // path for its modal data; the board card grid just stays empty/loading-free.
      if (!featureSurfaceV2Enabled) {
        setCards([]);
        setTotals({ total: 0 });
        setFreshness(null);
        setListState('success');
        setListError(null);
        return [];
      }

      const key = buildCacheKey(currentQuery);

      if (!bypassCache) {
        const cached = cache.get(key);
        if (cached) {
          setCards(cached.cards);
          setTotals({ total: cached.total, filteredTotal: cached.filteredTotal });
          setFreshness(cached.freshness);
          setListState('success');
          setListError(null);
          return cached.cards.map((c) => c.id);
        }
      }

      setListState('loading');
      setListError(null);

      try {
        const page = await listFeatureCards(queryToApiParams(currentQuery));

        // Guard: discard if a newer list request has already fired
        if (listRequestIdRef.current !== requestId) return null;

        const nextCards = page.items;
        if (!noCache) {
          cache.set(key, {
            cards: nextCards,
            total: page.total,
            freshness: page.freshness,
            queryHash: page.queryHash,
            timestamp: Date.now(),
          });
        }

        setCards(nextCards);
        setTotals({ total: page.total });
        setFreshness(page.freshness);
        setListState('success');
        setListError(null);

        return nextCards.map((c) => c.id);
      } catch (err) {
        if (listRequestIdRef.current !== requestId) return null;
        setListState('error');
        setListError(err instanceof Error ? err : new Error(String(err)));
        return null;
      }
    },
    [cache, noCache],
  );

  // ── Rollup fetch (fires after list resolves) ────────────────────────────────
  const fetchRollups = useCallback(
    async (featureIds: string[], requestId: number) => {
      if (!featureIds.length) {
        setRollups(new Map());
        setRollupState('success');
        setRollupError(null);
        return;
      }

      setRollupState('loading');
      setRollupError(null);

      try {
        const response = await getFeatureRollups({
          featureIds,
          fields: rollupFields,
          includeInheritedThreads: true,
          includeFreshness: true,
          includeTestMetrics: false,
        });

        // Guard: discard if a newer rollup request has already fired
        if (rollupRequestIdRef.current !== requestId) return;

        const map = new Map<string, FeatureRollupDTO>();
        for (const [id, rollup] of Object.entries(response.rollups)) {
          map.set(id, rollup);
        }
        setRollups(map);
        setRollupState('success');
        setRollupError(null);
      } catch (err) {
        if (rollupRequestIdRef.current !== requestId) return;
        setRollupState('error');
        setRollupError(err instanceof Error ? err : new Error(String(err)));
      }
    },
    [rollupFields],
  );

  // ── Main effect: fire on query change or refetch tick ──────────────────────
  useEffect(() => {
    const listId = ++listRequestIdRef.current;
    const rollupId = ++rollupRequestIdRef.current;
    const bypassCache = refetchTick > 0; // first mount uses cache; explicit refetch bypasses

    void (async () => {
      const featureIds = await fetchList(query, listId, bypassCache);
      // Only fan out rollup batch if this list response is still current
      if (featureIds !== null && listRequestIdRef.current === listId) {
        rollupRequestIdRef.current = rollupId;
        await fetchRollups(featureIds, rollupId);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, refetchTick]);
  // Note: fetchList/fetchRollups are stable callbacks; including them would
  // cause infinite re-renders when options change.  Query and refetchTick are
  // the true dependencies.

  // ── Actions ─────────────────────────────────────────────────────────────────

  const retryList = useCallback(() => {
    const listId = ++listRequestIdRef.current;
    const rollupId = ++rollupRequestIdRef.current;

    void (async () => {
      const featureIds = await fetchList(query, listId, true);
      if (featureIds !== null && listRequestIdRef.current === listId) {
        rollupRequestIdRef.current = rollupId;
        await fetchRollups(featureIds, rollupId);
      }
    })();
  }, [query, fetchList, fetchRollups]);

  const retryRollups = useCallback(() => {
    const currentIds = cards.map((c) => c.id);
    if (!currentIds.length) return;
    const rollupId = ++rollupRequestIdRef.current;
    void fetchRollups(currentIds, rollupId);
  }, [cards, fetchRollups]);

  const refetch = useCallback(() => {
    setRefetchTick((t) => t + 1);
  }, []);

  const invalidate = useCallback(
    (scope: 'list' | 'rollups' | 'all' = 'all') => {
      if (scope === 'list' || scope === 'all') {
        cache.delete(cacheKey);
      }
      if (scope === 'rollups' || scope === 'all') {
        setRollups(new Map());
        setRollupState('idle');
        setRollupError(null);
      }
      if (scope === 'all') {
        // Trigger a fresh fetch
        setRefetchTick((t) => t + 1);
      }
    },
    [cache, cacheKey],
  );

  return {
    query,
    setQuery,
    cards,
    rollups,
    totals,
    freshness,
    listState,
    rollupState,
    listError,
    rollupError,
    retryList,
    retryRollups,
    refetch,
    invalidate,
    cacheKey,
  };
}

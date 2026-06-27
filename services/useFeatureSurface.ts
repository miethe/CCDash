// useFeatureSurface — T3-004: Feature Surface Hook (TanStack Query internals)
//
// Owns all feature-board data loading: one paginated list fetch → one batched
// rollup fetch for the returned card IDs.  Exposes query state, loading/error
// states, and invalidation/retry handlers.  Components never serialize params
// or call featureSurface.ts directly.
//
// T3-004 migration: replaced hand-rolled LRU + request-id guard with two
// TanStack Query tiers:
//   list-tier   → useQuery keyed featureSurfaceKeys.list(…), staleTime: 0
//   rollup-tier → useQuery keyed featureSurfaceKeys.rollup(…), staleTime: 30_000
//
// invalidate(scope) → queryClient.invalidateQueries on the appropriate key subset.
//
// The public API of this hook is intentionally stable across the TQ migration.
//
// Default rollupFields: 'session_counts' | 'token_cost_totals' | 'latest_activity'
// These three cover all current card-metric display needs (session badge, cost
// badge, last-active indicator).  Consumers can override via the rollupFields
// option if they need doc_metrics or test_metrics.

import { useCallback, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import {
  listFeatureCards,
  getFeatureRollups,
  type FeatureCardDTO,
  type FeatureRollupDTO,
  type FeatureRollupFieldKey,
  type FeatureCardsListParams,
  type DTOFreshness,
} from './featureSurface';
import { featureSurfaceKeys } from './queryKeys';

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

/** Injected cache adapter interface — kept for API compatibility. */
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

/** Full return shape of the hook — stable across TQ migration. */
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
   * - scope 'list': invalidate the current list query key
   * - scope 'rollups': invalidate rollup query keys for the current project
   * - scope 'all' (default): invalidate all featureSurface keys for the project
   */
  invalidate: (scope?: 'list' | 'rollups' | 'all') => void;

  /** The cache key for the current query — useful for external cache wiring. */
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

// ── Query → stable serialized params object for TQ key ────────────────────────
// Produces a plain object that TQ can serialize for cache identity.

function queryToKeyParams(query: FeatureSurfaceQuery): Record<string, unknown> {
  const normalize = (arr: string[]) => [...arr].sort();
  return {
    pageSize: query.pageSize,
    search: query.search || null,
    status: normalize(query.status),
    stage: normalize(query.stage),
    tags: normalize(query.tags),
    sortBy: query.sortBy,
    sortDirection: query.sortDirection,
    include: normalize(query.include),
    category: query.category ?? null,
    plannedFrom: query.plannedFrom ?? null,
    plannedTo: query.plannedTo ?? null,
    startedFrom: query.startedFrom ?? null,
    startedTo: query.startedTo ?? null,
    completedFrom: query.completedFrom ?? null,
    completedTo: query.completedTo ?? null,
    updatedFrom: query.updatedFrom ?? null,
    updatedTo: query.updatedTo ?? null,
    progressMin: query.progressMin ?? null,
    progressMax: query.progressMax ?? null,
    taskCountMin: query.taskCountMin ?? null,
    taskCountMax: query.taskCountMax ?? null,
    hasDeferred: query.hasDeferred ?? null,
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
  /** Kept for API compatibility — not used; TQ is the cache layer. */
  cacheAdapter?: FeatureSurfaceCacheAdapter;
  /** Kept for API compatibility — not used; TQ handles cache bypassing via refetch. */
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

// Default rollup fields for board cards.
const DEFAULT_ROLLUP_FIELDS: FeatureRollupFieldKey[] = [
  'session_counts',
  'token_cost_totals',
  'latest_activity',
  'model_provider_summary',
  'doc_metrics',
];

// ── List query result shape ───────────────────────────────────────────────────

interface ListQueryData {
  cards: FeatureCardDTO[];
  total: number;
  filteredTotal?: number;
  freshness: DTOFreshness | null;
  queryHash: string;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useFeatureSurface(options: UseFeatureSurfaceOptions = {}): UseFeatureSurfaceResult {
  const {
    initialQuery,
    rollupFields = DEFAULT_ROLLUP_FIELDS,
    // P5-005: Capture the flag at mount.  useRef ensures subsequent re-renders
    // with a changed prop do NOT trigger a re-fetch — the path is fixed for the
    // lifetime of this hook instance to prevent a re-mount loop.
    featureSurfaceV2Enabled: featureSurfaceV2EnabledOption = true,
  } = options;

  // Freeze the flag at mount time — never re-read from options on re-render.
  const featureSurfaceV2EnabledRef = useRef(featureSurfaceV2EnabledOption);
  const featureSurfaceV2Enabled = featureSurfaceV2EnabledRef.current;

  const queryClient = useQueryClient();

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

  // ── Derived values ───────────────────────────────────────────────────────────
  const projectId = query.projectId ?? '';
  const cacheKey = buildCacheKey(query);

  // ── List-tier query ──────────────────────────────────────────────────────────
  // T4-005: staleTime: 30_000 — the list is considered fresh for 30 s so
  // remounts within that window skip a redundant network fetch.  SSE-driven
  // invalidation (queryClient.invalidateQueries) still triggers an immediate
  // refetch when SSE is active, so freshness is not degraded in that path.

  const listQuery = useQuery<ListQueryData, Error>({
    queryKey: featureSurfaceKeys.list(projectId, queryToKeyParams(query), query.page),
    queryFn: async (): Promise<ListQueryData> => {
      const page = await listFeatureCards(queryToApiParams(query));
      return {
        cards: page.items,
        total: page.total,
        freshness: page.freshness ?? null,
        queryHash: page.queryHash ?? '',
      };
    },
    staleTime: 30_000,
    enabled: !!projectId && featureSurfaceV2Enabled,
  });

  // Derive list values from TQ result
  const cards: FeatureCardDTO[] = featureSurfaceV2Enabled
    ? (listQuery.data?.cards ?? [])
    : [];
  const totals = featureSurfaceV2Enabled
    ? { total: listQuery.data?.total ?? 0, filteredTotal: listQuery.data?.filteredTotal }
    : { total: 0 };
  const freshness = featureSurfaceV2Enabled ? (listQuery.data?.freshness ?? null) : null;

  const listState: LoadState = !featureSurfaceV2Enabled
    ? 'success'
    : listQuery.isLoading
      ? 'loading'
      : listQuery.isError
        ? 'error'
        : listQuery.data !== undefined
          ? 'success'
          : 'idle';

  const listError = listQuery.error ?? null;

  // ── Rollup-tier query ─────────────────────────────────────────────────────────
  // Keyed by the sorted feature IDs from the current list result + freshnessToken.
  // staleTime: 30_000 — rollups are considered fresh for 30 seconds (matches old TTL).
  // Only fires when we have a non-empty list result.

  const cardIds = cards.map((c) => c.id);
  const freshnessToken = freshness?.sourceRevision ?? freshness?.cacheVersion ?? null;

  const rollupQuery = useQuery<Map<string, FeatureRollupDTO>, Error>({
    queryKey: featureSurfaceKeys.rollup(projectId, cardIds, freshnessToken),
    queryFn: async (): Promise<Map<string, FeatureRollupDTO>> => {
      const response = await getFeatureRollups({
        featureIds: cardIds,
        fields: rollupFields,
        includeInheritedThreads: true,
        includeFreshness: true,
        includeTestMetrics: false,
      });
      const map = new Map<string, FeatureRollupDTO>();
      for (const [id, rollup] of Object.entries(response.rollups)) {
        map.set(id, rollup);
      }
      return map;
    },
    staleTime: 30_000,
    enabled: !!projectId && featureSurfaceV2Enabled && cardIds.length > 0,
  });

  // Derive rollup values
  const rollups: Map<string, FeatureRollupDTO> = featureSurfaceV2Enabled
    ? (rollupQuery.data ?? new Map())
    : new Map();

  const rollupState: LoadState = !featureSurfaceV2Enabled || cardIds.length === 0
    ? 'success'
    : rollupQuery.isLoading
      ? 'loading'
      : rollupQuery.isError
        ? 'error'
        : rollupQuery.data !== undefined
          ? 'success'
          : 'idle';

  const rollupError = rollupQuery.error ?? null;

  // ── Actions ─────────────────────────────────────────────────────────────────

  const retryList = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: featureSurfaceKeys.list(projectId, queryToKeyParams(query), query.page),
    });
  }, [queryClient, projectId, query]);

  const retryRollups = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: featureSurfaceKeys.rollup(projectId, cardIds, freshnessToken),
    });
  }, [queryClient, projectId, cardIds, freshnessToken]);

  const refetch = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: featureSurfaceKeys.all(projectId),
    });
  }, [queryClient, projectId]);

  const invalidate = useCallback(
    (scope: 'list' | 'rollups' | 'all' = 'all') => {
      if (scope === 'list') {
        void queryClient.invalidateQueries({
          queryKey: featureSurfaceKeys.list(projectId, queryToKeyParams(query), query.page),
        });
      } else if (scope === 'rollups') {
        void queryClient.invalidateQueries({
          queryKey: featureSurfaceKeys.rollup(projectId, cardIds, freshnessToken),
        });
      } else {
        // scope === 'all'
        void queryClient.invalidateQueries({
          queryKey: featureSurfaceKeys.all(projectId),
        });
      }
    },
    [queryClient, projectId, query, cardIds, freshnessToken],
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

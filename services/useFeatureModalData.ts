// useFeatureModalData — P4-002: Feature Modal Per-Section Data Hook
//
// Provides independent, lazily-loaded query state for each modal tab/section.
// Each section has its own loading/error/stale/retry lifecycle, AbortController,
// and monotonic request ID so stale responses never overwrite fresher state.
//
// ── Cache decision ────────────────────────────────────────────────────────────
// We define a sibling ModalSectionCache (LRU, max 120 entries) rather than
// reusing defaultFeatureSurfaceCache for two reasons:
//   1. Different eviction semantics: modal sections are per-(featureId, section,
//      params) and have no concept of "list pages" or "rollup TTL".  Folding them
//      into the two-tier list/rollup cache would require adding a third tier or
//      overloading list-tier semantics, increasing coupling.
//   2. Different cardinality: the board shows up to 50 features per page; the
//      modal is opened one feature at a time.  A dedicated 120-entry cache
//      (7 sections × ~17 simultaneously open features) keeps memory predictable
//      without polluting the board's 50+100-entry budget.
// The cache key format: `{featureId}|{section}|{paramsHash}` — same composition
// rule as useFeatureSurface's `{projectId}|{query}|{page}`.
//
// ── Public API ────────────────────────────────────────────────────────────────
// useFeatureModalData(featureId, options) → ModalSectionStore
//
// ModalSectionStore is a Record keyed by ModalTabId; each section exposes:
//   { status, data, error, requestId, load(), retry(), invalidate() }
//
// Top-level helpers on the returned object:
//   prefetch(section)   — warm cache without switching active section state
//   markStale(section?) — transition loaded section(s) to 'stale'
//   invalidateAll()     — clear cache entries for all sections of this feature

import { useCallback, useEffect, useReducer, useRef, useState } from 'react';

import {
  getFeatureModalOverview,
  getFeatureModalSection,
  getFeatureLinkedSessionPage,
  type FeatureModalOverviewDTO,
  type FeatureModalSectionDTO,
  type LinkedFeatureSessionPageDTO,
  type FeatureModalSectionKey,
  type FeatureModalSectionParams,
  type LinkedSessionPageParams,
} from './featureSurface';

// ── Tab/section identifiers ───────────────────────────────────────────────────
// 'test-status' maps to the wire 'test_status' section key.
// 'history' maps to the wire 'activity' section key.
// 'overview' is served by the dedicated /modal endpoint, not /modal/{section}.

export type ModalTabId =
  | 'overview'
  | 'phases'
  | 'docs'
  | 'relations'
  | 'sessions'
  | 'test-status'
  | 'history';

const TAB_TO_SECTION_KEY: Record<Exclude<ModalTabId, 'overview' | 'sessions'>, FeatureModalSectionKey> = {
  phases: 'phases',
  docs: 'documents',
  relations: 'relations',
  'test-status': 'test_status',
  history: 'activity',
};

// ── Section data union ────────────────────────────────────────────────────────

export type ModalSectionData =
  | FeatureModalOverviewDTO         // overview
  | FeatureModalSectionDTO          // phases | docs | relations | test-status | history
  | LinkedFeatureSessionPageDTO;    // sessions

// ── Per-section query state ───────────────────────────────────────────────────

export type SectionStatus = 'idle' | 'loading' | 'success' | 'error' | 'stale';

export interface SectionState {
  status: SectionStatus;
  data: ModalSectionData | null;
  error: Error | null;
  /** Monotonic request ID of the last completed (or in-flight) load. */
  requestId: number;
}

/** Slice of the public API returned per-section. */
export interface SectionHandle extends SectionState {
  /** Start loading this section (no-op if already loading). */
  load: () => void;
  /** Force a reload regardless of current status. */
  retry: () => void;
  /** Evict this section's cache entry and reset to idle. */
  invalidate: () => void;
}

// ── Session pagination accumulator state ─────────────────────────────────────
// Separate from the per-section SectionState because pagination accumulates
// across multiple fetch calls (append semantics vs. replace semantics).
// The sessions SectionHandle carries the first-page data; this supplementary
// state tracks the full accumulated list and paging cursor.

export interface SessionPaginationState {
  /** All accumulated session items across pages fetched so far. */
  accumulatedItems: import('./featureSurface').LinkedFeatureSessionDTO[];
  /** Total server-reported count (from the most recent page response). */
  serverTotal: number;
  /** Whether more pages are available. */
  hasMore: boolean;
  /** Whether a load-more fetch is currently in flight. */
  isLoadingMore: boolean;
  /** Cursor / offset to pass to the next page fetch. */
  nextCursor: string | null;
  nextOffset: number;
}

// ── Reducer ───────────────────────────────────────────────────────────────────

type SectionAction =
  | { type: 'LOAD_START'; tab: ModalTabId; requestId: number }
  | { type: 'LOAD_SUCCESS'; tab: ModalTabId; requestId: number; data: ModalSectionData }
  | { type: 'LOAD_ERROR'; tab: ModalTabId; requestId: number; error: Error }
  | { type: 'MARK_STALE'; tab: ModalTabId }
  | { type: 'INVALIDATE'; tab: ModalTabId }
  | { type: 'RESET_ALL' };

type SectionStateMap = Record<ModalTabId, SectionState>;

const INITIAL_SECTION: SectionState = {
  status: 'idle',
  data: null,
  error: null,
  requestId: 0,
};

const ALL_TABS: ModalTabId[] = [
  'overview',
  'phases',
  'docs',
  'relations',
  'sessions',
  'test-status',
  'history',
];

function makeInitialState(): SectionStateMap {
  return Object.fromEntries(ALL_TABS.map((t) => [t, { ...INITIAL_SECTION }])) as SectionStateMap;
}

function sectionReducer(state: SectionStateMap, action: SectionAction): SectionStateMap {
  switch (action.type) {
    case 'LOAD_START':
      return {
        ...state,
        [action.tab]: {
          ...state[action.tab],
          status: 'loading',
          error: null,
          requestId: action.requestId,
        },
      };

    case 'LOAD_SUCCESS':
      // Stale-request guard: only apply if this requestId is current.
      if (state[action.tab].requestId !== action.requestId) return state;
      return {
        ...state,
        [action.tab]: {
          status: 'success',
          data: action.data,
          error: null,
          requestId: action.requestId,
        },
      };

    case 'LOAD_ERROR':
      if (state[action.tab].requestId !== action.requestId) return state;
      return {
        ...state,
        [action.tab]: {
          ...state[action.tab],
          status: 'error',
          error: action.error,
          requestId: action.requestId,
        },
      };

    case 'MARK_STALE': {
      const current = state[action.tab];
      // Only transition from success → stale; other states are left alone.
      if (current.status !== 'success') return state;
      return {
        ...state,
        [action.tab]: { ...current, status: 'stale' },
      };
    }

    case 'INVALIDATE':
      return {
        ...state,
        [action.tab]: { ...INITIAL_SECTION },
      };

    case 'RESET_ALL':
      return makeInitialState();

    default:
      return state;
  }
}

// ── Simple bounded LRU cache for modal section payloads ───────────────────────
// Max 120 entries: 7 sections × ~17 concurrently-cached features.
// Keyed by `{featureId}|{section}|{paramsHash}`.

const MODAL_SECTION_CACHE_MAX = 120;

export class ModalSectionLRU {
  private readonly _max: number;
  private readonly _map: Map<string, ModalSectionData> = new Map();

  constructor(max: number) {
    this._max = max;
  }

  get(key: string): ModalSectionData | undefined {
    const v = this._map.get(key);
    if (v === undefined) return undefined;
    this._map.delete(key);
    this._map.set(key, v);
    return v;
  }

  set(key: string, value: ModalSectionData): void {
    if (this._map.has(key)) this._map.delete(key);
    this._map.set(key, value);
    if (this._map.size > this._max) {
      this._map.delete(this._map.keys().next().value!);
    }
  }

  delete(key: string): void {
    this._map.delete(key);
  }

  /** Evict all keys starting with prefix. */
  deleteByPrefix(prefix: string): void {
    for (const k of Array.from(this._map.keys())) {
      if (k.startsWith(prefix)) this._map.delete(k);
    }
  }

  clear(): void {
    this._map.clear();
  }

  get size(): number {
    return this._map.size;
  }
}

/** Module-level singleton shared across all hook instances. */
export const modalSectionCache = new ModalSectionLRU(MODAL_SECTION_CACHE_MAX);

// ── Cache key helpers ─────────────────────────────────────────────────────────

export function buildModalSectionCacheKey(
  featureId: string,
  tab: ModalTabId,
  params?: SessionPageParams | FeatureModalSectionParams,
): string {
  const paramsHash =
    params && Object.keys(params).length > 0
      ? Object.entries(params)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([k, v]) => `${k}=${v}`)
          .join('&')
      : '';
  return `${featureId}|${tab}|${paramsHash}`;
}

// ── Session page params ───────────────────────────────────────────────────────

export interface SessionPageParams {
  limit?: number;
  offset?: number;
  cursor?: string;
}

// ── Hook options ──────────────────────────────────────────────────────────────

export interface UseFeatureModalDataOptions {
  /**
   * Inject a custom cache (e.g. for tests).  Defaults to the module singleton.
   * Passing `null` disables caching entirely.
   */
  cacheAdapter?: ModalSectionLRU | null;
  /** Default params forwarded to section section endpoints. */
  sectionParams?: FeatureModalSectionParams;
  /** Default params forwarded to the sessions endpoint. */
  sessionParams?: SessionPageParams;
}

// ── Return type ───────────────────────────────────────────────────────────────

export type ModalSectionStore = {
  [K in ModalTabId]: SectionHandle;
} & {
  /**
   * Warm the cache for `section` without touching active state or triggering
   * a re-render beyond the cache write.  If already cached, this is a no-op.
   * Used by P4-006 live refresh to speculatively load adjacent tabs.
   */
  prefetch: (section: ModalTabId) => Promise<void>;

  /**
   * Transition an already-loaded section to 'stale' without fetching.
   * If no section is specified, all loaded sections are marked stale.
   * P4-006 calls this on inactive tabs when a live invalidation arrives.
   */
  markStale: (section?: ModalTabId) => void;

  /**
   * Evict cache entries for all sections of this feature and reset reducer
   * state to idle.  Causes next load() call per section to re-fetch.
   */
  invalidateAll: () => void;

  // ── P4-004: Session pagination ───────────────────────────────────────────
  /**
   * Accumulated session pagination state across all pages loaded so far.
   * `sessions.data` still holds the first-page DTO for backwards compatibility;
   * use `sessionPagination.accumulatedItems` for the full list.
   */
  sessionPagination: SessionPaginationState;

  /**
   * Fetch the next page of linked sessions and append to `sessionPagination.accumulatedItems`.
   * No-op if `hasMore` is false or `isLoadingMore` is true.
   */
  loadMoreSessions: () => Promise<void>;
};

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useFeatureModalData(
  featureId: string | null | undefined,
  options: UseFeatureModalDataOptions = {},
): ModalSectionStore {
  const {
    cacheAdapter,
    sectionParams = {},
    sessionParams = {},
  } = options;

  // When cacheAdapter is explicitly null, disable caching.
  const noCache = cacheAdapter === null;
  const cache = noCache ? null : (cacheAdapter ?? modalSectionCache);

  // ── Reducer state ─────────────────────────────────────────────────────────
  const [state, dispatch] = useReducer(sectionReducer, undefined, makeInitialState);

  // ── Per-section monotonic request counters ─────────────────────────────────
  // Keyed by ModalTabId.  Each load() increments its section's counter before
  // the async call so that `LOAD_SUCCESS` / `LOAD_ERROR` reducer guards work.
  const requestCounters = useRef<Record<ModalTabId, number>>(
    Object.fromEntries(ALL_TABS.map((t) => [t, 0])) as Record<ModalTabId, number>,
  );

  // ── AbortController registry ───────────────────────────────────────────────
  // One AbortController per section; replaced on every new load() call.
  const abortControllers = useRef<Partial<Record<ModalTabId, AbortController>>>({});

  // ── P4-004: Session pagination accumulator ────────────────────────────────
  const INITIAL_SESSION_PAGINATION: SessionPaginationState = {
    accumulatedItems: [],
    serverTotal: 0,
    hasMore: false,
    isLoadingMore: false,
    nextCursor: null,
    nextOffset: 0,
  };

  const [sessionPagination, setSessionPagination] = useState<SessionPaginationState>(
    () => ({ ...INITIAL_SESSION_PAGINATION }),
  );

  // AbortController dedicated to load-more fetches (separate from fetchSection's registry).
  const loadMoreAbortRef = useRef<AbortController | null>(null);

  // ── Reset on featureId change ──────────────────────────────────────────────
  const prevFeatureIdRef = useRef<string | null | undefined>(featureId);
  useEffect(() => {
    if (prevFeatureIdRef.current === featureId) return;
    prevFeatureIdRef.current = featureId;

    // Abort all in-flight requests for the previous feature.
    for (const ctrl of Object.values(abortControllers.current)) {
      ctrl?.abort();
    }
    abortControllers.current = {};

    // Abort any in-flight load-more.
    loadMoreAbortRef.current?.abort();
    loadMoreAbortRef.current = null;

    // Bump all counters so any late-arriving responses are ignored.
    for (const tab of ALL_TABS) {
      requestCounters.current[tab]++;
    }

    dispatch({ type: 'RESET_ALL' });
    setSessionPagination({ ...INITIAL_SESSION_PAGINATION });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [featureId]);

  // ── Abort in-flight on unmount ─────────────────────────────────────────────
  useEffect(() => {
    return () => {
      for (const ctrl of Object.values(abortControllers.current)) {
        ctrl?.abort();
      }
      loadMoreAbortRef.current?.abort();
    };
  }, []);

  // ── Core fetch dispatcher ──────────────────────────────────────────────────

  const fetchSection = useCallback(
    async (
      tab: ModalTabId,
      force: boolean,
      /**
       * When true the result is written to cache but NOT dispatched to the
       * reducer — used by prefetch() to warm the cache silently.
       */
      cacheOnly: boolean,
    ): Promise<void> => {
      if (!featureId) return;

      const cacheKey = buildModalSectionCacheKey(
        featureId,
        tab,
        tab === 'sessions' ? sessionParams : sectionParams,
      );

      // Cache-hit fast path (skip if force or cacheOnly with existing data).
      if (!force && !cacheOnly && cache) {
        const cached = cache.get(cacheKey);
        if (cached !== undefined) {
          const reqId = ++requestCounters.current[tab];
          dispatch({ type: 'LOAD_START', tab, requestId: reqId });
          dispatch({ type: 'LOAD_SUCCESS', tab, requestId: reqId, data: cached });
          return;
        }
      }
      // prefetch: if already cached, do nothing.
      if (cacheOnly && cache && cache.get(cacheKey) !== undefined) return;

      // Abort previous in-flight request for this section.
      abortControllers.current[tab]?.abort();
      const ctrl = new AbortController();
      abortControllers.current[tab] = ctrl;

      const reqId = ++requestCounters.current[tab];

      if (!cacheOnly) {
        dispatch({ type: 'LOAD_START', tab, requestId: reqId });
      }

      try {
        let data: ModalSectionData;

        if (tab === 'overview') {
          data = await getFeatureModalOverview(featureId);
        } else if (tab === 'sessions') {
          const p: LinkedSessionPageParams = {
            limit: sessionParams.limit,
            offset: sessionParams.offset ?? (sessionParams.cursor ? undefined : 0),
          };
          data = await getFeatureLinkedSessionPage(featureId, p);
        } else {
          const sectionKey = TAB_TO_SECTION_KEY[tab as keyof typeof TAB_TO_SECTION_KEY];
          data = await getFeatureModalSection(featureId, sectionKey, sectionParams);
        }

        // Stale-request guard: if a newer request fired while we were awaiting,
        // skip the dispatch AND the cache write.  A stale response must not
        // overwrite a newer result already stored by the winning request.
        const isStillCurrent = requestCounters.current[tab] === reqId;

        if (isStillCurrent) {
          if (!noCache && cache) {
            cache.set(cacheKey, data);
          }
          if (!cacheOnly) {
            dispatch({ type: 'LOAD_SUCCESS', tab, requestId: reqId, data });
            // P4-004: seed the session pagination accumulator from the first page.
            if (tab === 'sessions') {
              const page = data as LinkedFeatureSessionPageDTO;
              setSessionPagination({
                accumulatedItems: page.items,
                serverTotal: page.total,
                hasMore: page.hasMore,
                isLoadingMore: false,
                nextCursor: page.nextCursor,
                nextOffset: page.offset + page.items.length,
              });
            }
          }
        } else if (cacheOnly && !noCache && cache) {
          // prefetch: even if another request is in flight, populate cache
          // only for cacheOnly (prefetch) calls where there is no dispatch race.
          cache.set(cacheKey, data);
        }
      } catch (err) {
        if (ctrl.signal.aborted) return; // intentional abort; ignore
        const isStillCurrent = requestCounters.current[tab] === reqId;
        if (!cacheOnly && isStillCurrent) {
          dispatch({
            type: 'LOAD_ERROR',
            tab,
            requestId: reqId,
            error: err instanceof Error ? err : new Error(String(err)),
          });
        }
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [featureId, cache, noCache],
    // sectionParams/sessionParams intentionally excluded: they are shallow
    // objects passed at call-site; referential stability is the caller's
    // responsibility.  Including them would cause unnecessary re-creation of
    // fetchSection on every render when callers inline the objects.
  );

  // ── Per-section action builders ───────────────────────────────────────────

  const buildHandle = useCallback(
    (tab: ModalTabId): SectionHandle => {
      const sectionState = state[tab];
      return {
        ...sectionState,
        load: () => {
          if (sectionState.status === 'loading') return;
          void fetchSection(tab, false, false);
        },
        retry: () => {
          void fetchSection(tab, true, false);
        },
        invalidate: () => {
          if (!featureId) return;
          const cacheKey = buildModalSectionCacheKey(
            featureId,
            tab,
            tab === 'sessions' ? sessionParams : sectionParams,
          );
          cache?.delete(cacheKey);
          dispatch({ type: 'INVALIDATE', tab });
        },
      };
    },
    [state, featureId, fetchSection, cache, sessionParams, sectionParams],
  );

  // ── P4-004: loadMoreSessions ──────────────────────────────────────────────

  const loadMoreSessions = useCallback(async (): Promise<void> => {
    if (!featureId) return;
    if (!sessionPagination.hasMore || sessionPagination.isLoadingMore) return;

    // Abort any previous load-more in flight.
    loadMoreAbortRef.current?.abort();
    const ctrl = new AbortController();
    loadMoreAbortRef.current = ctrl;

    setSessionPagination(prev => ({ ...prev, isLoadingMore: true }));

    try {
      const p: LinkedSessionPageParams = {
        limit: sessionParams.limit,
        offset: sessionPagination.nextOffset,
      };
      const page = await getFeatureLinkedSessionPage(featureId, p);

      if (ctrl.signal.aborted) return;

      setSessionPagination(prev => ({
        accumulatedItems: [...prev.accumulatedItems, ...page.items],
        serverTotal: page.total,
        hasMore: page.hasMore,
        isLoadingMore: false,
        nextCursor: page.nextCursor,
        nextOffset: prev.nextOffset + page.items.length,
      }));
    } catch (err) {
      if (ctrl.signal.aborted) return;
      setSessionPagination(prev => ({ ...prev, isLoadingMore: false }));
    }
  // sessionPagination intentionally spread into deps via hasMore/isLoadingMore/nextOffset
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [featureId, sessionPagination.hasMore, sessionPagination.isLoadingMore, sessionPagination.nextOffset, sessionParams.limit]);

  // ── Top-level helpers ─────────────────────────────────────────────────────

  const prefetch = useCallback(
    async (section: ModalTabId): Promise<void> => {
      await fetchSection(section, false, true);
    },
    [fetchSection],
  );

  const markStale = useCallback(
    (section?: ModalTabId): void => {
      if (section !== undefined) {
        dispatch({ type: 'MARK_STALE', tab: section });
      } else {
        for (const tab of ALL_TABS) {
          dispatch({ type: 'MARK_STALE', tab });
        }
      }
    },
    [],
  );

  const invalidateAll = useCallback((): void => {
    if (!featureId) return;
    cache?.deleteByPrefix(`${featureId}|`);
    dispatch({ type: 'RESET_ALL' });
  }, [featureId, cache]);

  // ── Assemble return object ────────────────────────────────────────────────

  return {
    overview: buildHandle('overview'),
    phases: buildHandle('phases'),
    docs: buildHandle('docs'),
    relations: buildHandle('relations'),
    sessions: buildHandle('sessions'),
    'test-status': buildHandle('test-status'),
    history: buildHandle('history'),
    prefetch,
    markStale,
    invalidateAll,
    sessionPagination,
    loadMoreSessions,
  };
}

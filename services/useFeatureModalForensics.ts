// useFeatureModalForensics — forensics domain data hook (P4-002)
//
// Owns the 'sessions' and 'history' tabs.
// The sessions tab carries the full SessionPaginationState accumulator
// (load-more / append semantics). The history tab loads via the standard
// getFeatureModalSection endpoint with wire key 'activity'.
//
// Domain: forensics
// Tabs owned: sessions, history
//
// Used directly by SessionsTab and HistoryTab components that only need
// forensics-domain data. Also composed internally by useFeatureModalData
// (compatibility wrapper).

import { useCallback, useEffect, useReducer, useRef, useState } from 'react';

import {
  getFeatureModalSection,
  getFeatureLinkedSessionPage,
  getLegacyFeatureLinkedSessions,
  type FeatureModalSectionDTO,
  type FeatureModalSectionKey,
  type FeatureModalSectionParams,
  type LinkedFeatureSessionPageDTO,
  type LinkedSessionPageParams,
} from './featureSurface';

import {
  buildModalSectionCacheKey,
  makeTabInitialState,
  partialSectionReducer,
  FORENSICS_TABS,
  TAB_TO_SECTION_KEY,
  INITIAL_SECTION,
  INITIAL_SESSION_PAGINATION,
  type ModalSectionLRU,
  type ModalTabId,
  type SectionHandle,
  type SectionState,
  type SessionPaginationState,
  type SessionPageParams,
  type PartialSectionStateMap,
} from './useFeatureModalCore';

// ── Public options ────────────────────────────────────────────────────────────

export interface UseFeatureModalForensicsOptions {
  /** Inject a custom cache (e.g. for tests). Passing `null` disables caching. */
  cacheAdapter?: ModalSectionLRU | null;
  /** Default params forwarded to section endpoints. */
  sectionParams?: FeatureModalSectionParams;
  /** Default params forwarded to the sessions endpoint. */
  sessionParams?: SessionPageParams;
  featureSurfaceV2Enabled?: boolean;
}

// ── Return type ───────────────────────────────────────────────────────────────

export interface FeatureModalForensicsStore {
  sessions: SectionHandle;
  history: SectionHandle;

  /**
   * Accumulated session pagination state across all pages loaded so far.
   * `sessions.data` holds the first-page DTO for backwards compatibility;
   * use `sessionPagination.accumulatedItems` for the full list.
   */
  sessionPagination: SessionPaginationState;

  /**
   * Fetch the next page of linked sessions and append to
   * `sessionPagination.accumulatedItems`. No-op when `hasMore` is false
   * or `isLoadingMore` is true.
   */
  loadMoreSessions: () => Promise<void>;

  /** Warm the cache for a forensics tab without triggering a re-render. */
  prefetch: (tab: 'sessions' | 'history') => Promise<void>;
  /** Transition a loaded forensics tab to 'stale'. If omitted, all forensics tabs are marked. */
  markStale: (tab?: 'sessions' | 'history') => void;
  /** Evict all forensics tabs' cache entries and reset to idle. */
  invalidateAll: () => void;
}

type ForensicsTab = 'sessions' | 'history';

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useFeatureModalForensics(
  featureId: string | null | undefined,
  options: UseFeatureModalForensicsOptions = {},
): FeatureModalForensicsStore {
  const {
    cacheAdapter,
    sectionParams = {},
    sessionParams = {},
    featureSurfaceV2Enabled: featureSurfaceV2EnabledOption = true,
  } = options;

  const featureSurfaceV2EnabledRef = useRef(featureSurfaceV2EnabledOption);
  const featureSurfaceV2Enabled = featureSurfaceV2EnabledRef.current;

  const noCache = cacheAdapter === null;
  const cache = noCache ? null : (cacheAdapter ?? null);

  const [state, dispatch] = useReducer(
    partialSectionReducer,
    undefined,
    () => makeTabInitialState(FORENSICS_TABS) as PartialSectionStateMap,
  );

  const requestCounters = useRef<Record<string, number>>(
    Object.fromEntries(FORENSICS_TABS.map((t) => [t, 0])),
  );

  const abortControllers = useRef<Partial<Record<ModalTabId, AbortController>>>({});

  // ── Session pagination accumulator ────────────────────────────────────────
  const [sessionPagination, setSessionPagination] = useState<SessionPaginationState>(
    () => ({ ...INITIAL_SESSION_PAGINATION }),
  );

  const loadMoreAbortRef = useRef<AbortController | null>(null);

  // ── Reset on featureId change ──────────────────────────────────────────────
  const prevFeatureIdRef = useRef<string | null | undefined>(featureId);
  useEffect(() => {
    if (prevFeatureIdRef.current === featureId) return;
    prevFeatureIdRef.current = featureId;

    for (const ctrl of Object.values(abortControllers.current)) ctrl?.abort();
    abortControllers.current = {};

    loadMoreAbortRef.current?.abort();
    loadMoreAbortRef.current = null;

    for (const tab of FORENSICS_TABS) requestCounters.current[tab]++;

    dispatch({ type: 'RESET_TABS', tabs: FORENSICS_TABS });
    setSessionPagination({ ...INITIAL_SESSION_PAGINATION });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [featureId]);

  // ── Abort on unmount ───────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      for (const ctrl of Object.values(abortControllers.current)) ctrl?.abort();
      loadMoreAbortRef.current?.abort();
    };
  }, []);

  // ── Core fetch ─────────────────────────────────────────────────────────────

  const fetchSection = useCallback(
    async (tab: ForensicsTab, force: boolean, cacheOnly: boolean): Promise<void> => {
      if (!featureId) return;

      const paramsForKey = tab === 'sessions' ? sessionParams : sectionParams;
      const cacheKey = buildModalSectionCacheKey(featureId, tab, paramsForKey);

      if (!force && !cacheOnly && cache) {
        const cached = cache.get(cacheKey);
        if (cached !== undefined) {
          const reqId = ++requestCounters.current[tab];
          dispatch({ type: 'LOAD_START', tab, requestId: reqId });
          dispatch({ type: 'LOAD_SUCCESS', tab, requestId: reqId, data: cached });
          if (tab === 'sessions') {
            const page = cached as LinkedFeatureSessionPageDTO;
            setSessionPagination({
              accumulatedItems: page.items,
              serverTotal: page.total,
              hasMore: page.hasMore,
              isLoadingMore: false,
              nextCursor: page.nextCursor,
              nextOffset: page.offset + page.items.length,
            });
          }
          return;
        }
      }
      if (cacheOnly && cache && cache.get(cacheKey) !== undefined) return;

      abortControllers.current[tab]?.abort();
      const ctrl = new AbortController();
      abortControllers.current[tab] = ctrl;

      const reqId = ++requestCounters.current[tab];
      if (!cacheOnly) dispatch({ type: 'LOAD_START', tab, requestId: reqId });

      try {
        let data: LinkedFeatureSessionPageDTO | FeatureModalSectionDTO;

        if (!featureSurfaceV2Enabled) {
          if (tab === 'sessions') {
            const raw = await getLegacyFeatureLinkedSessions<unknown[]>(featureId);
            const items = Array.isArray(raw) ? raw : [];
            data = {
              items: items as LinkedFeatureSessionPageDTO['items'],
              total: items.length,
              offset: 0,
              limit: items.length,
              hasMore: false,
              nextCursor: null,
              enrichment: {
                includes: [],
                logsRead: false,
                commandCountIncluded: false,
                taskRefsIncluded: false,
                threadChildrenIncluded: false,
              },
              precision: 'eventually_consistent' as const,
              freshness: null,
            } satisfies LinkedFeatureSessionPageDTO;
          } else {
            const sectionKey = TAB_TO_SECTION_KEY[tab as keyof typeof TAB_TO_SECTION_KEY];
            data = {
              featureId,
              section: sectionKey as FeatureModalSectionKey,
              title: '',
              items: [],
              total: 0,
              offset: 0,
              limit: 0,
              hasMore: false,
              includes: [],
              precision: 'eventually_consistent' as const,
              freshness: null,
            } satisfies FeatureModalSectionDTO;
          }
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

        if (ctrl.signal.aborted) return;

        const isStillCurrent = requestCounters.current[tab] === reqId;
        if (isStillCurrent) {
          if (!noCache && cache) cache.set(cacheKey, data);
          if (!cacheOnly) {
            dispatch({ type: 'LOAD_SUCCESS', tab, requestId: reqId, data });
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
          cache.set(cacheKey, data);
        }
      } catch (err) {
        if (ctrl.signal.aborted) return;
        if (!cacheOnly && requestCounters.current[tab] === reqId) {
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
  );

  // ── loadMoreSessions ──────────────────────────────────────────────────────

  const loadMoreSessions = useCallback(async (): Promise<void> => {
    if (!featureId) return;
    if (!sessionPagination.hasMore || sessionPagination.isLoadingMore) return;

    loadMoreAbortRef.current?.abort();
    const ctrl = new AbortController();
    loadMoreAbortRef.current = ctrl;

    setSessionPagination((prev) => ({ ...prev, isLoadingMore: true }));

    try {
      const p: LinkedSessionPageParams = {
        limit: sessionParams.limit,
        offset: sessionPagination.nextOffset,
      };
      const page = await getFeatureLinkedSessionPage(featureId, p);

      if (ctrl.signal.aborted) return;

      setSessionPagination((prev) => ({
        accumulatedItems: [...prev.accumulatedItems, ...page.items],
        serverTotal: page.total,
        hasMore: page.hasMore,
        isLoadingMore: false,
        nextCursor: page.nextCursor,
        nextOffset: prev.nextOffset + page.items.length,
      }));
    } catch (err) {
      if (ctrl.signal.aborted) return;
      setSessionPagination((prev) => ({ ...prev, isLoadingMore: false }));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [featureId, sessionPagination.hasMore, sessionPagination.isLoadingMore, sessionPagination.nextOffset, sessionParams.limit]);

  // ── Handle builder ─────────────────────────────────────────────────────────

  const buildHandle = useCallback(
    (tab: ForensicsTab): SectionHandle => {
      const paramsForKey = tab === 'sessions' ? sessionParams : sectionParams;
      const sectionState: SectionState = state[tab] ?? INITIAL_SECTION;
      return {
        ...sectionState,
        load: () => {
          if (sectionState.status === 'loading') return;
          void fetchSection(tab, false, false);
        },
        retry: () => void fetchSection(tab, true, false),
        invalidate: () => {
          if (!featureId) return;
          cache?.delete(buildModalSectionCacheKey(featureId, tab, paramsForKey));
          dispatch({ type: 'INVALIDATE', tab });
        },
      };
    },
    [state, featureId, fetchSection, cache, sectionParams, sessionParams],
  );

  // ── Top-level helpers ─────────────────────────────────────────────────────

  const prefetch = useCallback(
    async (tab: ForensicsTab): Promise<void> => {
      await fetchSection(tab, false, true);
    },
    [fetchSection],
  );

  const markStale = useCallback(
    (tab?: ForensicsTab): void => {
      if (tab !== undefined) {
        dispatch({ type: 'MARK_STALE', tab });
      } else {
        for (const t of FORENSICS_TABS) {
          dispatch({ type: 'MARK_STALE', tab: t });
        }
      }
    },
    [],
  );

  const invalidateAll = useCallback((): void => {
    if (!featureId) return;
    cache?.delete(buildModalSectionCacheKey(featureId, 'sessions', sessionParams));
    cache?.delete(buildModalSectionCacheKey(featureId, 'history', sectionParams));
    dispatch({ type: 'RESET_TABS', tabs: FORENSICS_TABS });
    setSessionPagination({ ...INITIAL_SESSION_PAGINATION });
  }, [featureId, cache, sectionParams, sessionParams]);

  return {
    sessions: buildHandle('sessions'),
    history: buildHandle('history'),
    sessionPagination,
    loadMoreSessions,
    prefetch,
    markStale,
    invalidateAll,
  };
}

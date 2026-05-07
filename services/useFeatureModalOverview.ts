// useFeatureModalOverview — shared-shell domain data hook (P4-002)
//
// Owns the 'overview' tab: fetches FeatureModalOverviewDTO (card + rollup + description).
//
// Domain: shared-shell
// Tabs owned: overview
//
// Used directly by OverviewTab components that only need overview data.
// Also composed internally by useFeatureModalData (compatibility wrapper).

import { useCallback, useEffect, useReducer, useRef } from 'react';

import {
  getFeatureModalOverview,
  getLegacyFeatureDetail,
  type FeatureModalOverviewDTO,
} from './featureSurface';

import {
  buildModalSectionCacheKey,
  makeTabInitialState,
  partialSectionReducer,
  OVERVIEW_TABS,
  INITIAL_SECTION,
  type ModalSectionLRU,
  type ModalTabId,
  type SectionHandle,
  type SectionState,
  type PartialSectionStateMap,
} from './useFeatureModalCore';

// ── Public options ────────────────────────────────────────────────────────────

export interface UseFeatureModalOverviewOptions {
  /** Inject a custom cache (e.g. for tests). Passing `null` disables caching. */
  cacheAdapter?: ModalSectionLRU | null;
  featureSurfaceV2Enabled?: boolean;
}

// ── Return type ───────────────────────────────────────────────────────────────

export interface FeatureModalOverviewStore {
  overview: SectionHandle;
  /** Warm the cache without triggering a re-render. */
  prefetch: () => Promise<void>;
  /** Transition the loaded overview to 'stale' without fetching. */
  markStale: () => void;
  /** Evict the cache entry and reset to idle. */
  invalidate: () => void;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useFeatureModalOverview(
  featureId: string | null | undefined,
  options: UseFeatureModalOverviewOptions = {},
): FeatureModalOverviewStore {
  const {
    cacheAdapter,
    featureSurfaceV2Enabled: featureSurfaceV2EnabledOption = true,
  } = options;

  // Freeze the v2 flag at mount to avoid re-mount loops.
  const featureSurfaceV2EnabledRef = useRef(featureSurfaceV2EnabledOption);
  const featureSurfaceV2Enabled = featureSurfaceV2EnabledRef.current;

  const noCache = cacheAdapter === null;
  const cache = noCache ? null : (cacheAdapter ?? null);

  const [state, dispatch] = useReducer(
    partialSectionReducer,
    undefined,
    () => makeTabInitialState(OVERVIEW_TABS) as PartialSectionStateMap,
  );

  const requestCounters = useRef<Record<string, number>>(
    Object.fromEntries(OVERVIEW_TABS.map((t) => [t, 0])),
  );

  const abortControllers = useRef<Partial<Record<ModalTabId, AbortController>>>({});

  // ── Reset on featureId change ──────────────────────────────────────────────
  const prevFeatureIdRef = useRef<string | null | undefined>(featureId);
  useEffect(() => {
    if (prevFeatureIdRef.current === featureId) return;
    prevFeatureIdRef.current = featureId;

    for (const ctrl of Object.values(abortControllers.current)) ctrl?.abort();
    abortControllers.current = {};

    for (const tab of OVERVIEW_TABS) requestCounters.current[tab]++;

    dispatch({ type: 'RESET_TABS', tabs: OVERVIEW_TABS });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [featureId]);

  // ── Abort on unmount ───────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      for (const ctrl of Object.values(abortControllers.current)) ctrl?.abort();
    };
  }, []);

  // ── Core fetch ─────────────────────────────────────────────────────────────

  const fetchOverview = useCallback(
    async (force: boolean, cacheOnly: boolean): Promise<void> => {
      const tab: ModalTabId = 'overview';
      if (!featureId) return;

      const cacheKey = buildModalSectionCacheKey(featureId, tab);

      // Cache-hit fast path
      if (!force && !cacheOnly && cache) {
        const cached = cache.get(cacheKey);
        if (cached !== undefined) {
          const reqId = ++requestCounters.current[tab];
          dispatch({ type: 'LOAD_START', tab, requestId: reqId });
          dispatch({ type: 'LOAD_SUCCESS', tab, requestId: reqId, data: cached });
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
        let data: FeatureModalOverviewDTO;

        if (!featureSurfaceV2Enabled) {
          const raw = await getLegacyFeatureDetail<unknown>(featureId);
          data = raw as FeatureModalOverviewDTO;
        } else {
          data = await getFeatureModalOverview(featureId);
        }

        if (ctrl.signal.aborted) return;

        const isStillCurrent = requestCounters.current[tab] === reqId;
        if (isStillCurrent) {
          if (!noCache && cache) cache.set(cacheKey, data);
          if (!cacheOnly) dispatch({ type: 'LOAD_SUCCESS', tab, requestId: reqId, data });
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

  // ── Assemble return object ─────────────────────────────────────────────────

  const overviewState: SectionState = state['overview'] ?? INITIAL_SECTION;

  const overview: SectionHandle = {
    ...overviewState,
    load: () => {
      if (overviewState.status === 'loading') return;
      void fetchOverview(false, false);
    },
    retry: () => void fetchOverview(true, false),
    invalidate: () => {
      if (!featureId) return;
      cache?.delete(buildModalSectionCacheKey(featureId, 'overview'));
      dispatch({ type: 'INVALIDATE', tab: 'overview' });
    },
  };

  const prefetch = useCallback(async () => {
    await fetchOverview(false, true);
  }, [fetchOverview]);

  const markStale = useCallback(() => {
    dispatch({ type: 'MARK_STALE', tab: 'overview' });
  }, []);

  const invalidate = useCallback(() => {
    if (!featureId) return;
    cache?.delete(buildModalSectionCacheKey(featureId, 'overview'));
    dispatch({ type: 'INVALIDATE', tab: 'overview' });
  }, [featureId, cache]);

  return { overview, prefetch, markStale, invalidate };
}

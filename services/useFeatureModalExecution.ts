// useFeatureModalExecution — execution domain data hook (P4-002)
//
// Owns the 'test-status' tab. Fetches the test-status section DTO and exposes
// the execution gate state derived from it.
//
// Domain: execution
// Tabs owned: test-status
//
// Used directly by TestStatusTab components that only need execution-domain
// data. Also composed internally by useFeatureModalData (compatibility wrapper).

import { useCallback, useEffect, useReducer, useRef } from 'react';

import {
  getFeatureModalSection,
  type FeatureModalSectionDTO,
  type FeatureModalSectionKey,
  type FeatureModalSectionParams,
} from './featureSurface';

import {
  buildModalSectionCacheKey,
  makeTabInitialState,
  partialSectionReducer,
  EXECUTION_TABS,
  TAB_TO_SECTION_KEY,
  INITIAL_SECTION,
  type ModalSectionLRU,
  type ModalTabId,
  type SectionHandle,
  type SectionState,
  type PartialSectionStateMap,
} from './useFeatureModalCore';

// ── Public options ────────────────────────────────────────────────────────────

export interface UseFeatureModalExecutionOptions {
  /** Inject a custom cache (e.g. for tests). Passing `null` disables caching. */
  cacheAdapter?: ModalSectionLRU | null;
  /** Default params forwarded to section endpoints. */
  sectionParams?: FeatureModalSectionParams;
  featureSurfaceV2Enabled?: boolean;
}

// ── Return type ───────────────────────────────────────────────────────────────

export interface FeatureModalExecutionStore {
  'test-status': SectionHandle;
  /** Warm the cache without triggering a re-render. */
  prefetch: () => Promise<void>;
  /** Transition the loaded test-status section to 'stale'. */
  markStale: () => void;
  /** Evict the test-status cache entry and reset to idle. */
  invalidate: () => void;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useFeatureModalExecution(
  featureId: string | null | undefined,
  options: UseFeatureModalExecutionOptions = {},
): FeatureModalExecutionStore {
  const {
    cacheAdapter,
    sectionParams = {},
    featureSurfaceV2Enabled: featureSurfaceV2EnabledOption = true,
  } = options;

  const featureSurfaceV2EnabledRef = useRef(featureSurfaceV2EnabledOption);
  const featureSurfaceV2Enabled = featureSurfaceV2EnabledRef.current;

  const noCache = cacheAdapter === null;
  const cache = noCache ? null : (cacheAdapter ?? null);

  const [state, dispatch] = useReducer(
    partialSectionReducer,
    undefined,
    () => makeTabInitialState(EXECUTION_TABS) as PartialSectionStateMap,
  );

  const requestCounters = useRef<Record<string, number>>(
    Object.fromEntries(EXECUTION_TABS.map((t) => [t, 0])),
  );

  const abortControllers = useRef<Partial<Record<ModalTabId, AbortController>>>({});

  // ── Reset on featureId change ──────────────────────────────────────────────
  const prevFeatureIdRef = useRef<string | null | undefined>(featureId);
  useEffect(() => {
    if (prevFeatureIdRef.current === featureId) return;
    prevFeatureIdRef.current = featureId;

    for (const ctrl of Object.values(abortControllers.current)) ctrl?.abort();
    abortControllers.current = {};

    for (const tab of EXECUTION_TABS) requestCounters.current[tab]++;

    dispatch({ type: 'RESET_TABS', tabs: EXECUTION_TABS });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [featureId]);

  // ── Abort on unmount ───────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      for (const ctrl of Object.values(abortControllers.current)) ctrl?.abort();
    };
  }, []);

  // ── Core fetch ─────────────────────────────────────────────────────────────

  const fetchTestStatus = useCallback(
    async (force: boolean, cacheOnly: boolean): Promise<void> => {
      const tab: ModalTabId = 'test-status';
      if (!featureId) return;

      const cacheKey = buildModalSectionCacheKey(featureId, tab, sectionParams);

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
        let data: FeatureModalSectionDTO;

        if (!featureSurfaceV2Enabled) {
          const sectionKey = TAB_TO_SECTION_KEY['test-status'];
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
        } else {
          const sectionKey = TAB_TO_SECTION_KEY['test-status'];
          data = await getFeatureModalSection(featureId, sectionKey, sectionParams);
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

  const tab: ModalTabId = 'test-status';
  const sectionState: SectionState = state[tab] ?? INITIAL_SECTION;

  const testStatusHandle: SectionHandle = {
    ...sectionState,
    load: () => {
      if (sectionState.status === 'loading') return;
      void fetchTestStatus(false, false);
    },
    retry: () => void fetchTestStatus(true, false),
    invalidate: () => {
      if (!featureId) return;
      cache?.delete(buildModalSectionCacheKey(featureId, tab, sectionParams));
      dispatch({ type: 'INVALIDATE', tab });
    },
  };

  const prefetch = useCallback(async () => {
    await fetchTestStatus(false, true);
  }, [fetchTestStatus]);

  const markStale = useCallback(() => {
    dispatch({ type: 'MARK_STALE', tab: 'test-status' });
  }, []);

  const invalidate = useCallback(() => {
    if (!featureId) return;
    cache?.delete(buildModalSectionCacheKey(featureId, tab, sectionParams));
    dispatch({ type: 'INVALIDATE', tab });
  }, [featureId, cache, sectionParams, tab]);

  return {
    'test-status': testStatusHandle,
    prefetch,
    markStale,
    invalidate,
  };
}

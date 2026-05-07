// useFeatureModalPlanning — planning domain data hook (P4-002)
//
// Owns the 'phases', 'docs', and 'relations' tabs.
//
// Domain: planning
// Tabs owned: phases, docs, relations
//
// Used directly by PhasesTab, DocsTab, and RelationsTab components that only
// need planning-domain data. Also composed internally by useFeatureModalData
// (compatibility wrapper).

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
  PLANNING_TABS,
  TAB_TO_SECTION_KEY,
  INITIAL_SECTION,
  type ModalSectionLRU,
  type ModalTabId,
  type SectionHandle,
  type SectionState,
  type PartialSectionStateMap,
} from './useFeatureModalCore';

// ── Public options ────────────────────────────────────────────────────────────

export interface UseFeatureModalPlanningOptions {
  /** Inject a custom cache (e.g. for tests). Passing `null` disables caching. */
  cacheAdapter?: ModalSectionLRU | null;
  /** Default params forwarded to section endpoints. */
  sectionParams?: FeatureModalSectionParams;
  featureSurfaceV2Enabled?: boolean;
}

// ── Return type ───────────────────────────────────────────────────────────────

export interface FeatureModalPlanningStore {
  phases: SectionHandle;
  docs: SectionHandle;
  relations: SectionHandle;
  /** Warm the cache for a planning tab without triggering a re-render. */
  prefetch: (tab: 'phases' | 'docs' | 'relations') => Promise<void>;
  /** Transition a loaded planning tab to 'stale'. If omitted, all planning tabs are marked. */
  markStale: (tab?: 'phases' | 'docs' | 'relations') => void;
  /** Evict all planning tabs' cache entries and reset to idle. */
  invalidateAll: () => void;
}

type PlanningTab = 'phases' | 'docs' | 'relations';

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useFeatureModalPlanning(
  featureId: string | null | undefined,
  options: UseFeatureModalPlanningOptions = {},
): FeatureModalPlanningStore {
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
    () => makeTabInitialState(PLANNING_TABS) as PartialSectionStateMap,
  );

  const requestCounters = useRef<Record<string, number>>(
    Object.fromEntries(PLANNING_TABS.map((t) => [t, 0])),
  );

  const abortControllers = useRef<Partial<Record<ModalTabId, AbortController>>>({});

  // ── Reset on featureId change ──────────────────────────────────────────────
  const prevFeatureIdRef = useRef<string | null | undefined>(featureId);
  useEffect(() => {
    if (prevFeatureIdRef.current === featureId) return;
    prevFeatureIdRef.current = featureId;

    for (const ctrl of Object.values(abortControllers.current)) ctrl?.abort();
    abortControllers.current = {};

    for (const tab of PLANNING_TABS) requestCounters.current[tab]++;

    dispatch({ type: 'RESET_TABS', tabs: PLANNING_TABS });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [featureId]);

  // ── Abort on unmount ───────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      for (const ctrl of Object.values(abortControllers.current)) ctrl?.abort();
    };
  }, []);

  // ── Core fetch ─────────────────────────────────────────────────────────────

  const fetchSection = useCallback(
    async (tab: PlanningTab, force: boolean, cacheOnly: boolean): Promise<void> => {
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
          };
        } else {
          const sectionKey = TAB_TO_SECTION_KEY[tab as keyof typeof TAB_TO_SECTION_KEY];
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

  // ── Handle builder ─────────────────────────────────────────────────────────

  const buildHandle = useCallback(
    (tab: PlanningTab): SectionHandle => {
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
          cache?.delete(buildModalSectionCacheKey(featureId, tab, sectionParams));
          dispatch({ type: 'INVALIDATE', tab });
        },
      };
    },
    [state, featureId, fetchSection, cache, sectionParams],
  );

  // ── Top-level helpers ─────────────────────────────────────────────────────

  const prefetch = useCallback(
    async (tab: PlanningTab): Promise<void> => {
      await fetchSection(tab, false, true);
    },
    [fetchSection],
  );

  const markStale = useCallback(
    (tab?: PlanningTab): void => {
      if (tab !== undefined) {
        dispatch({ type: 'MARK_STALE', tab });
      } else {
        for (const t of PLANNING_TABS) {
          dispatch({ type: 'MARK_STALE', tab: t });
        }
      }
    },
    [],
  );

  const invalidateAll = useCallback((): void => {
    if (!featureId) return;
    for (const tab of PLANNING_TABS) {
      cache?.delete(buildModalSectionCacheKey(featureId, tab, sectionParams));
    }
    dispatch({ type: 'RESET_TABS', tabs: PLANNING_TABS });
  }, [featureId, cache, sectionParams]);

  return {
    phases: buildHandle('phases'),
    docs: buildHandle('docs'),
    relations: buildHandle('relations'),
    prefetch,
    markStale,
    invalidateAll,
  };
}

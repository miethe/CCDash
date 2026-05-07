// useFeatureModalData — compatibility wrapper (P4-002)
//
// This file is the public-API surface that all existing imports depend on.
// It re-exports all shared infrastructure from useFeatureModalCore, then
// composes the four domain-scoped hooks into the original ModalSectionStore
// interface so no existing call-site needs to change.
//
// Domain hooks (independently importable):
//   - useFeatureModalOverview  (shared-shell: overview)
//   - useFeatureModalPlanning  (planning: phases, docs, relations)
//   - useFeatureModalForensics (forensics: sessions, history)
//   - useFeatureModalExecution (execution: test-status)
//
// ── Public API (unchanged) ────────────────────────────────────────────────────
// useFeatureModalData(featureId, options) → ModalSectionStore
//
// ModalSectionStore is a Record keyed by ModalTabId; each section exposes:
//   { status, data, error, requestId, load(), retry(), invalidate() }
//
// Top-level helpers on the returned object:
//   prefetch(section)   — warm cache without switching active section state
//   markStale(section?) — transition loaded section(s) to 'stale'
//   invalidateAll()     — clear cache entries for all sections of this feature

// ── Re-export all shared infrastructure ───────────────────────────────────────
// Tests and consumers import these from useFeatureModalData and must continue
// to do so without changes.

export {
  // Cache
  ModalSectionLRU,
  modalSectionCache,
  buildModalSectionCacheKey,
  // Tab constants
  ALL_TABS,
  TAB_TO_SECTION_KEY,
  OVERVIEW_TABS,
  PLANNING_TABS,
  FORENSICS_TABS,
  EXECUTION_TABS,
  // State helpers
  INITIAL_SECTION,
  makeInitialState,
  makeTabInitialState,
  sectionReducer,
  partialSectionReducer,
  // Pagination
  INITIAL_SESSION_PAGINATION,
} from './useFeatureModalCore';

export type {
  // Identifiers
  ModalTabId,
  // Data
  ModalSectionData,
  // State
  SectionStatus,
  SectionState,
  SectionHandle,
  SectionStateMap,
  PartialSectionStateMap,
  // Pagination
  SessionPaginationState,
  // Options
  SessionPageParams,
  UseFeatureModalDataOptions,
  // Reducer
  SectionAction,
} from './useFeatureModalCore';

// ── Domain hook imports ───────────────────────────────────────────────────────

import { useCallback } from 'react';
import { useFeatureModalOverview } from './useFeatureModalOverview';
import { useFeatureModalPlanning } from './useFeatureModalPlanning';
import { useFeatureModalForensics } from './useFeatureModalForensics';
import { useFeatureModalExecution } from './useFeatureModalExecution';

import type {
  ModalTabId,
  SectionHandle,
  SessionPaginationState,
  UseFeatureModalDataOptions,
} from './useFeatureModalCore';

import { modalSectionCache } from './useFeatureModalCore';

// ── Return type ───────────────────────────────────────────────────────────────

export type ModalSectionStore = {
  [K in ModalTabId]: SectionHandle;
} & {
  /**
   * Warm the cache for `section` without touching active state or triggering
   * a re-render beyond the cache write.  If already cached, this is a no-op.
   */
  prefetch: (section: ModalTabId) => Promise<void>;

  /**
   * Transition an already-loaded section to 'stale' without fetching.
   * If no section is specified, all loaded sections are marked stale.
   */
  markStale: (section?: ModalTabId) => void;

  /**
   * Evict cache entries for all sections of this feature and reset reducer
   * state to idle.  Causes next load() call per section to re-fetch.
   */
  invalidateAll: () => void;

  /**
   * Accumulated session pagination state across all pages loaded so far.
   * `sessions.data` still holds the first-page DTO for backwards compatibility;
   * use `sessionPagination.accumulatedItems` for the full list.
   */
  sessionPagination: SessionPaginationState;

  /**
   * Fetch the next page of linked sessions and append to
   * `sessionPagination.accumulatedItems`.  No-op if `hasMore` is false or
   * `isLoadingMore` is true.
   */
  loadMoreSessions: () => Promise<void>;
};

// ── Compatibility wrapper hook ────────────────────────────────────────────────

export function useFeatureModalData(
  featureId: string | null | undefined,
  options: UseFeatureModalDataOptions = {},
): ModalSectionStore {
  const {
    cacheAdapter,
    sectionParams = {},
    sessionParams = {},
    featureSurfaceV2Enabled = true,
  } = options;

  // Resolve the shared cache adapter: undefined → singleton, null → disabled.
  const resolvedCache = cacheAdapter === null ? null : (cacheAdapter ?? modalSectionCache);

  // ── Domain hooks ───────────────────────────────────────────────────────────

  const overviewStore = useFeatureModalOverview(featureId, {
    cacheAdapter: resolvedCache,
    featureSurfaceV2Enabled,
  });

  const planningStore = useFeatureModalPlanning(featureId, {
    cacheAdapter: resolvedCache,
    sectionParams,
    featureSurfaceV2Enabled,
  });

  const forensicsStore = useFeatureModalForensics(featureId, {
    cacheAdapter: resolvedCache,
    sectionParams,
    sessionParams,
    featureSurfaceV2Enabled,
  });

  const executionStore = useFeatureModalExecution(featureId, {
    cacheAdapter: resolvedCache,
    sectionParams,
    featureSurfaceV2Enabled,
  });

  // ── Cross-domain prefetch ─────────────────────────────────────────────────

  const prefetch = useCallback(
    async (section: ModalTabId): Promise<void> => {
      switch (section) {
        case 'overview':
          return overviewStore.prefetch();
        case 'phases':
        case 'docs':
        case 'relations':
          return planningStore.prefetch(section);
        case 'sessions':
        case 'history':
          return forensicsStore.prefetch(section);
        case 'test-status':
          return executionStore.prefetch();
        default:
          section satisfies never;
      }
    },
    [overviewStore, planningStore, forensicsStore, executionStore],
  );

  // ── Cross-domain markStale ────────────────────────────────────────────────

  const markStale = useCallback(
    (section?: ModalTabId): void => {
      if (section === undefined) {
        // Mark all domains stale.
        overviewStore.markStale();
        planningStore.markStale();
        forensicsStore.markStale();
        executionStore.markStale();
      } else {
        switch (section) {
          case 'overview':
            overviewStore.markStale();
            break;
          case 'phases':
          case 'docs':
          case 'relations':
            planningStore.markStale(section);
            break;
          case 'sessions':
          case 'history':
            forensicsStore.markStale(section);
            break;
          case 'test-status':
            executionStore.markStale();
            break;
          default:
            section satisfies never;
        }
      }
    },
    [overviewStore, planningStore, forensicsStore, executionStore],
  );

  // ── Cross-domain invalidateAll ────────────────────────────────────────────

  const invalidateAll = useCallback((): void => {
    overviewStore.invalidate();
    planningStore.invalidateAll();
    forensicsStore.invalidateAll();
    executionStore.invalidate();
  }, [overviewStore, planningStore, forensicsStore, executionStore]);

  // ── Assemble return object ────────────────────────────────────────────────

  return {
    // Shared-shell
    overview: overviewStore.overview,
    // Planning
    phases: planningStore.phases,
    docs: planningStore.docs,
    relations: planningStore.relations,
    // Forensics
    sessions: forensicsStore.sessions,
    history: forensicsStore.history,
    // Execution
    'test-status': executionStore['test-status'],
    // Cross-domain helpers
    prefetch,
    markStale,
    invalidateAll,
    // Session pagination (forensics domain, exposed at store level for BC)
    sessionPagination: forensicsStore.sessionPagination,
    loadMoreSessions: forensicsStore.loadMoreSessions,
  };
}

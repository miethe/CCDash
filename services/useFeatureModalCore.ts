// useFeatureModalCore — shared infrastructure for feature modal domain hooks
//
// Contains ALL types, the LRU cache class, the reducer, and helper constants
// shared by the four domain-scoped hooks:
//   - useFeatureModalOverview  (shared-shell: overview)
//   - useFeatureModalPlanning  (planning: phases, docs, relations)
//   - useFeatureModalForensics (forensics: sessions, history)
//   - useFeatureModalExecution (execution: test-status)
//
// useFeatureModalData.ts re-exports everything from here via:
//   export { … } from './useFeatureModalCore';
// so existing `import { … } from './useFeatureModalData'` call-sites continue
// to work without any changes.
//
// P4-002: extracted from the monolithic useFeatureModalData.ts.
// Do NOT import from useFeatureModalData.ts in this file — that would create
// a circular dependency.

import type {
  FeatureModalOverviewDTO,
  FeatureModalSectionDTO,
  LinkedFeatureSessionPageDTO,
  FeatureModalSectionKey,
  FeatureModalSectionParams,
  LinkedFeatureSessionDTO,
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

export const TAB_TO_SECTION_KEY: Record<
  Exclude<ModalTabId, 'overview' | 'sessions'>,
  FeatureModalSectionKey
> = {
  phases: 'phases',
  docs: 'documents',
  relations: 'relations',
  'test-status': 'test_status',
  history: 'activity',
};

// ── Tab domain groups ─────────────────────────────────────────────────────────

export const OVERVIEW_TABS: readonly ModalTabId[] = ['overview'] as const;
export const PLANNING_TABS: readonly ModalTabId[] = ['phases', 'docs', 'relations'] as const;
export const FORENSICS_TABS: readonly ModalTabId[] = ['sessions', 'history'] as const;
export const EXECUTION_TABS: readonly ModalTabId[] = ['test-status'] as const;

export const ALL_TABS: ModalTabId[] = [
  'overview',
  'phases',
  'docs',
  'relations',
  'sessions',
  'test-status',
  'history',
];

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

export interface SessionPaginationState {
  /** All accumulated session items across pages fetched so far. */
  accumulatedItems: LinkedFeatureSessionDTO[];
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

export const INITIAL_SESSION_PAGINATION: SessionPaginationState = {
  accumulatedItems: [],
  serverTotal: 0,
  hasMore: false,
  isLoadingMore: false,
  nextCursor: null,
  nextOffset: 0,
};

// ── Hook options (shared base) ────────────────────────────────────────────────

export interface SessionPageParams {
  limit?: number;
  offset?: number;
  cursor?: string;
}

export interface UseFeatureModalDataOptions {
  cacheAdapter?: ModalSectionLRU | null;
  sectionParams?: FeatureModalSectionParams;
  sessionParams?: SessionPageParams;
  featureSurfaceV2Enabled?: boolean;
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

// ── Reducer ───────────────────────────────────────────────────────────────────

export type SectionStateMap = Record<ModalTabId, SectionState>;

export const INITIAL_SECTION: SectionState = {
  status: 'idle',
  data: null,
  error: null,
  requestId: 0,
};

export function makeInitialState(): SectionStateMap {
  return Object.fromEntries(ALL_TABS.map((t) => [t, { ...INITIAL_SECTION }])) as SectionStateMap;
}

export function makeTabInitialState(tabs: readonly ModalTabId[]): Record<string, SectionState> {
  return Object.fromEntries(tabs.map((t) => [t, { ...INITIAL_SECTION }]));
}

export type SectionAction =
  | { type: 'LOAD_START'; tab: ModalTabId; requestId: number }
  | { type: 'LOAD_SUCCESS'; tab: ModalTabId; requestId: number; data: ModalSectionData }
  | { type: 'LOAD_ERROR'; tab: ModalTabId; requestId: number; error: Error }
  | { type: 'MARK_STALE'; tab: ModalTabId }
  | { type: 'INVALIDATE'; tab: ModalTabId }
  | { type: 'RESET_TABS'; tabs: readonly ModalTabId[] }
  | { type: 'RESET_ALL' };

// Full-store reducer (used by the compatibility wrapper).
export function sectionReducer(state: SectionStateMap, action: SectionAction): SectionStateMap {
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

    case 'RESET_TABS': {
      const patch: Partial<SectionStateMap> = {};
      for (const tab of action.tabs) {
        patch[tab] = { ...INITIAL_SECTION };
      }
      return { ...state, ...patch };
    }

    case 'RESET_ALL':
      return makeInitialState();

    default:
      return state;
  }
}

// Partial-store reducer for domain hooks operating on a subset of tabs.
export type PartialSectionStateMap = Partial<Record<ModalTabId, SectionState>>;

export function partialSectionReducer(
  state: PartialSectionStateMap,
  action: SectionAction,
): PartialSectionStateMap {
  switch (action.type) {
    case 'LOAD_START': {
      const cur = state[action.tab] ?? INITIAL_SECTION;
      return {
        ...state,
        [action.tab]: {
          ...cur,
          status: 'loading',
          error: null,
          requestId: action.requestId,
        },
      };
    }

    case 'LOAD_SUCCESS': {
      const cur = state[action.tab] ?? INITIAL_SECTION;
      if (cur.requestId !== action.requestId) return state;
      return {
        ...state,
        [action.tab]: {
          status: 'success',
          data: action.data,
          error: null,
          requestId: action.requestId,
        },
      };
    }

    case 'LOAD_ERROR': {
      const cur = state[action.tab] ?? INITIAL_SECTION;
      if (cur.requestId !== action.requestId) return state;
      return {
        ...state,
        [action.tab]: {
          ...cur,
          status: 'error',
          error: action.error,
          requestId: action.requestId,
        },
      };
    }

    case 'MARK_STALE': {
      const current = state[action.tab];
      if (!current || current.status !== 'success') return state;
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

    case 'RESET_TABS': {
      const patch: PartialSectionStateMap = {};
      for (const tab of action.tabs) {
        patch[tab] = { ...INITIAL_SECTION };
      }
      return { ...state, ...patch };
    }

    case 'RESET_ALL': {
      const fresh: PartialSectionStateMap = {};
      for (const tab of Object.keys(state) as ModalTabId[]) {
        fresh[tab] = { ...INITIAL_SECTION };
      }
      return fresh;
    }

    default:
      return state;
  }
}

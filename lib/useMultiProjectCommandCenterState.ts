/**
 * MPCC-404: URL-addressable state hook for the multi-project command center.
 *
 * Encapsulates all URL search-param read/write for the portfolio view:
 *   - view mode  (board | list)          → ?view=
 *   - project IDs filter                 → ?projects= (comma-separated)
 *   - group filter                       → ?group=
 *   - session board grouping dimension   → ?session_group=
 *   - selected card session ID           → ?card=
 *   - modal target (featureId)           → ?feature=
 *   - work-item status filter            → ?status=
 *   - work-item kind filter              → ?kind=
 *   - free-text search                   → ?q=
 *   - sort key                           → ?sort=
 *   - page                               → ?page=
 *   - page size                          → ?page_size=
 *   - hide done items                    → ?hide_done= (omitted = default ON)
 *
 * Design rules:
 *   - Param names use snake_case to match backend query param conventions.
 *   - All reads are defensive (unknown param values fall back to defaults).
 *   - setters use replace: true to avoid polluting history with every
 *     filter keystroke; the caller can opt into push by passing push: true.
 *   - State is READ-ONLY with respect to active project — this hook never
 *     calls setActiveProject or any project mutation.
 *   - Works with React Router v6 useSearchParams (HashRouter in this app).
 *
 * Reload invariant: all filters survive a page reload because they live in
 * the URL hash fragment.  A detail card or modal target likewise survives
 * reload so deep-links are bookmarkable.
 *
 * hideDone default: when ?hide_done= is ABSENT the default is TRUE (hide done
 * items). An explicit ?hide_done=false overrides this.  This matches Issue-2
 * requirements (default-on, URL-addressable, survives reload).
 */

import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { PlanningBoardGroupingMode } from '../types';

// ─── Constants ────────────────────────────────────────────────────────────────

export type MultiProjectViewMode = 'board' | 'list';

const VALID_VIEW_MODES: ReadonlySet<string> = new Set<MultiProjectViewMode>(['board', 'list']);
/** Extends PlanningBoardGroupingMode with 'project' for multi-project portfolio grouping. */
export type MultiProjectGroupingMode = PlanningBoardGroupingMode | 'project';

const VALID_SESSION_GROUPINGS: ReadonlySet<string> = new Set<MultiProjectGroupingMode>([
  'state',
  'project',
  'feature',
  'phase',
  'agent',
  'model',
]);

const PARAM = {
  VIEW: 'view',
  PROJECTS: 'projects',
  GROUP: 'group',
  SESSION_GROUP: 'session_group',
  CARD: 'card',
  FEATURE: 'feature',
  STATUS: 'status',
  KIND: 'kind',
  SEARCH: 'q',
  SORT: 'sort',
  PAGE: 'page',
  PAGE_SIZE: 'page_size',
  HIDE_DONE: 'hide_done',
} as const;

// ─── Parsed state shape ───────────────────────────────────────────────────────

export interface MultiProjectCommandCenterUrlState {
  /** Board (Kanban columns) or list view. */
  viewMode: MultiProjectViewMode;
  /** Project IDs to include.  Empty array = all visible projects. */
  projectIds: string[];
  /** Group label filter. */
  group: string | null;
  /** Session board grouping dimension. */
  sessionGrouping: MultiProjectGroupingMode;
  /** Currently selected session card ID. */
  selectedCardId: string | null;
  /** Feature ID for the detail modal. */
  modalFeatureId: string | null;
  /** Work-item status filter. */
  status: string | null;
  /** Work-item kind filter. */
  kind: string | null;
  /** Free-text search. */
  search: string | null;
  /** Sort key (backend-level). Defaults to 'last_activity' when absent. */
  sort: string | null;
  /** 1-based page number. */
  page: number;
  /** Items per page. */
  pageSize: number;
  /**
   * When true (default when param absent), backend excludes terminal-status items.
   * Explicitly set to false via ?hide_done=false to show all items.
   */
  hideDone: boolean;
}

// ─── Setter options ───────────────────────────────────────────────────────────

export interface SetParamOptions {
  /** Push a new history entry instead of replacing.  Default: false (replace). */
  push?: boolean;
}

// ─── Hook return type ─────────────────────────────────────────────────────────

export interface UseMultiProjectCommandCenterStateReturn {
  /** Fully parsed current URL state. */
  state: MultiProjectCommandCenterUrlState;

  /** Set view mode (board | list). */
  setViewMode(mode: MultiProjectViewMode, opts?: SetParamOptions): void;

  /** Set the project IDs filter.  Pass [] to clear (show all). */
  setProjectIds(ids: string[], opts?: SetParamOptions): void;

  /** Set group label filter.  Pass null to clear. */
  setGroup(group: string | null, opts?: SetParamOptions): void;

  /** Set session board grouping dimension (includes 'project' for portfolio grouping). */
  setSessionGrouping(grouping: MultiProjectGroupingMode, opts?: SetParamOptions): void;

  /** Select a card by session ID.  Pass null to deselect. */
  setSelectedCardId(cardId: string | null, opts?: SetParamOptions): void;

  /** Open feature detail modal.  Pass null to close. */
  setModalFeatureId(featureId: string | null, opts?: SetParamOptions): void;

  /** Set work-item status filter.  Pass null to clear. */
  setStatus(status: string | null, opts?: SetParamOptions): void;

  /** Set work-item kind filter.  Pass null to clear. */
  setKind(kind: string | null, opts?: SetParamOptions): void;

  /** Set free-text search.  Pass null / '' to clear. */
  setSearch(search: string | null, opts?: SetParamOptions): void;

  /** Set sort key.  Pass null to use backend default (last_activity). */
  setSort(sort: string | null, opts?: SetParamOptions): void;

  /** Navigate to a specific page. */
  setPage(page: number, opts?: SetParamOptions): void;

  /** Change page size (resets page to 1). */
  setPageSize(pageSize: number, opts?: SetParamOptions): void;

  /**
   * Set hideDone.  When true (default), terminal-status items are excluded.
   * Pass false to show all items (writes ?hide_done=false to URL).
   */
  setHideDone(hideDone: boolean, opts?: SetParamOptions): void;

  /**
   * Reset all filters to defaults while preserving view mode.
   * Does NOT clear card / modal selections.
   */
  resetFilters(opts?: SetParamOptions): void;

  /**
   * Close the detail modal and deselect any card.
   * Useful for modal-dismiss handlers.
   */
  closeDetail(opts?: SetParamOptions): void;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function parsePositiveInt(raw: string | null, fallback: number): number {
  if (!raw) return fallback;
  const n = parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

function parseViewMode(raw: string | null): MultiProjectViewMode {
  if (raw && VALID_VIEW_MODES.has(raw)) return raw as MultiProjectViewMode;
  return 'board';
}

function parseSessionGrouping(raw: string | null): MultiProjectGroupingMode {
  if (raw && VALID_SESSION_GROUPINGS.has(raw)) return raw as MultiProjectGroupingMode;
  return 'state';
}

function parseProjectIds(raw: string | null): string[] {
  if (!raw) return [];
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

function nullable(raw: string | null): string | null {
  return raw && raw.trim() ? raw.trim() : null;
}

/**
 * Parse ?hide_done= with default-ON semantics.
 * - Absent → true (default: hide done items)
 * - 'false' → false (explicitly show done items)
 * - anything else → true
 */
function parseHideDone(raw: string | null): boolean {
  if (raw === null) return true; // default ON
  return raw !== 'false';
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

/**
 * Reads and writes the multi-project command center URL state.
 *
 * Must be rendered inside a React Router <Router> (HashRouter in this app).
 * All setters are stable references (useCallback with searchParams deps).
 *
 * Usage:
 *   const { state, setViewMode, setProjectIds, ... } = useMultiProjectCommandCenterState();
 */
export function useMultiProjectCommandCenterState(): UseMultiProjectCommandCenterStateReturn {
  const [searchParams, setSearchParams] = useSearchParams();

  // ── Parse current state from URL ────────────────────────────────────────────
  const state: MultiProjectCommandCenterUrlState = {
    viewMode: parseViewMode(searchParams.get(PARAM.VIEW)),
    projectIds: parseProjectIds(searchParams.get(PARAM.PROJECTS)),
    group: nullable(searchParams.get(PARAM.GROUP)),
    sessionGrouping: parseSessionGrouping(searchParams.get(PARAM.SESSION_GROUP)),
    selectedCardId: nullable(searchParams.get(PARAM.CARD)),
    modalFeatureId: nullable(searchParams.get(PARAM.FEATURE)),
    status: nullable(searchParams.get(PARAM.STATUS)),
    kind: nullable(searchParams.get(PARAM.KIND)),
    search: nullable(searchParams.get(PARAM.SEARCH)),
    // Default sort is 'last_activity' — when absent from URL, use null here and
    // resolve the default in toCommandCenterFilters / toToolbarFilters callers.
    sort: nullable(searchParams.get(PARAM.SORT)),
    page: parsePositiveInt(searchParams.get(PARAM.PAGE), 1),
    pageSize: parsePositiveInt(searchParams.get(PARAM.PAGE_SIZE), 50),
    hideDone: parseHideDone(searchParams.get(PARAM.HIDE_DONE)),
  };

  // ── Generic param setter helper ─────────────────────────────────────────────
  const apply = useCallback(
    (
      updater: (params: URLSearchParams) => void,
      opts: SetParamOptions = {},
    ) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          updater(next);
          return next;
        },
        { replace: !opts.push },
      );
    },
    [setSearchParams],
  );

  // ── Setters ─────────────────────────────────────────────────────────────────

  const setViewMode = useCallback(
    (mode: MultiProjectViewMode, opts?: SetParamOptions) => {
      apply((p) => {
        if (mode === 'board') p.delete(PARAM.VIEW);
        else p.set(PARAM.VIEW, mode);
      }, opts);
    },
    [apply],
  );

  const setProjectIds = useCallback(
    (ids: string[], opts?: SetParamOptions) => {
      apply((p) => {
        const filtered = ids.filter(Boolean);
        if (filtered.length === 0) p.delete(PARAM.PROJECTS);
        else p.set(PARAM.PROJECTS, filtered.join(','));
        // Filter change → reset to page 1.
        p.delete(PARAM.PAGE);
      }, opts);
    },
    [apply],
  );

  const setGroup = useCallback(
    (group: string | null, opts?: SetParamOptions) => {
      apply((p) => {
        if (!group) p.delete(PARAM.GROUP);
        else p.set(PARAM.GROUP, group);
        p.delete(PARAM.PAGE);
      }, opts);
    },
    [apply],
  );

  const setSessionGrouping = useCallback(
    (grouping: MultiProjectGroupingMode, opts?: SetParamOptions) => {
      apply((p) => {
        if (grouping === 'state') p.delete(PARAM.SESSION_GROUP);
        else p.set(PARAM.SESSION_GROUP, grouping);
      }, opts);
    },
    [apply],
  );

  const setSelectedCardId = useCallback(
    (cardId: string | null, opts?: SetParamOptions) => {
      apply((p) => {
        if (!cardId) p.delete(PARAM.CARD);
        else p.set(PARAM.CARD, cardId);
      }, opts);
    },
    [apply],
  );

  const setModalFeatureId = useCallback(
    (featureId: string | null, opts?: SetParamOptions) => {
      apply((p) => {
        if (!featureId) p.delete(PARAM.FEATURE);
        else p.set(PARAM.FEATURE, featureId);
      }, opts);
    },
    [apply],
  );

  const setStatus = useCallback(
    (status: string | null, opts?: SetParamOptions) => {
      apply((p) => {
        if (!status) p.delete(PARAM.STATUS);
        else p.set(PARAM.STATUS, status);
        p.delete(PARAM.PAGE);
      }, opts);
    },
    [apply],
  );

  const setKind = useCallback(
    (kind: string | null, opts?: SetParamOptions) => {
      apply((p) => {
        if (!kind) p.delete(PARAM.KIND);
        else p.set(PARAM.KIND, kind);
        p.delete(PARAM.PAGE);
      }, opts);
    },
    [apply],
  );

  const setSearch = useCallback(
    (search: string | null, opts?: SetParamOptions) => {
      apply((p) => {
        if (!search || !search.trim()) p.delete(PARAM.SEARCH);
        else p.set(PARAM.SEARCH, search.trim());
        p.delete(PARAM.PAGE);
      }, opts);
    },
    [apply],
  );

  const setSort = useCallback(
    (sort: string | null, opts?: SetParamOptions) => {
      apply((p) => {
        // 'last_activity' is the default — omit it from URL to keep URLs clean.
        if (!sort || sort === 'last_activity') p.delete(PARAM.SORT);
        else p.set(PARAM.SORT, sort);
        // Sort change should reset to page 1.
        p.delete(PARAM.PAGE);
      }, opts);
    },
    [apply],
  );

  const setPage = useCallback(
    (page: number, opts?: SetParamOptions) => {
      apply((p) => {
        if (page <= 1) p.delete(PARAM.PAGE);
        else p.set(PARAM.PAGE, String(page));
      }, opts);
    },
    [apply],
  );

  const setPageSize = useCallback(
    (pageSize: number, opts?: SetParamOptions) => {
      apply((p) => {
        if (pageSize === 50) p.delete(PARAM.PAGE_SIZE);
        else p.set(PARAM.PAGE_SIZE, String(pageSize));
        // Page size change resets to page 1.
        p.delete(PARAM.PAGE);
      }, opts);
    },
    [apply],
  );

  const setHideDone = useCallback(
    (hideDone: boolean, opts?: SetParamOptions) => {
      apply((p) => {
        // true is the default — omit from URL to keep URLs clean.
        if (hideDone) p.delete(PARAM.HIDE_DONE);
        else p.set(PARAM.HIDE_DONE, 'false');
        p.delete(PARAM.PAGE);
      }, opts);
    },
    [apply],
  );

  const resetFilters = useCallback(
    (opts?: SetParamOptions) => {
      apply((p) => {
        p.delete(PARAM.PROJECTS);
        p.delete(PARAM.GROUP);
        p.delete(PARAM.STATUS);
        p.delete(PARAM.KIND);
        p.delete(PARAM.SEARCH);
        p.delete(PARAM.SORT);
        p.delete(PARAM.PAGE);
        // Reset hide_done to default (on) by deleting the param.
        p.delete(PARAM.HIDE_DONE);
        // Keep view mode, session grouping, and detail selections intact.
      }, opts);
    },
    [apply],
  );

  const closeDetail = useCallback(
    (opts?: SetParamOptions) => {
      apply((p) => {
        p.delete(PARAM.CARD);
        p.delete(PARAM.FEATURE);
      }, opts);
    },
    [apply],
  );

  return {
    state,
    setViewMode,
    setProjectIds,
    setGroup,
    setSessionGrouping,
    setSelectedCardId,
    setModalFeatureId,
    setStatus,
    setKind,
    setSearch,
    setSort,
    setPage,
    setPageSize,
    setHideDone,
    resetFilters,
    closeDetail,
  };
}

// ─── Derived helpers ──────────────────────────────────────────────────────────

/**
 * Extracts the filter fields from URL state into a shape compatible with
 * MultiProjectCommandCenterFilters (used by the TanStack Query hook).
 * Call this to bridge URL state → query params without manual mapping.
 *
 * sort defaults to 'last_activity' when absent from URL state.
 * hideDone defaults to true (omit done items) — explicit false is forwarded.
 */
export function toCommandCenterFilters(
  state: MultiProjectCommandCenterUrlState,
): {
  projectIds?: string[];
  status?: string;
  kind?: string;
  group?: string;
  search?: string;
  sort?: string;
  page?: number;
  pageSize?: number;
  hideDone?: boolean;
} {
  return {
    projectIds: state.projectIds.length > 0 ? state.projectIds : undefined,
    status: state.status ?? undefined,
    kind: state.kind ?? undefined,
    group: state.group ?? undefined,
    search: state.search ?? undefined,
    // Use 'last_activity' as default sort when sort is null.
    sort: state.sort ?? 'last_activity',
    page: state.page !== 1 ? state.page : undefined,
    pageSize: state.pageSize !== 50 ? state.pageSize : undefined,
    hideDone: state.hideDone,
  };
}

/**
 * Extracts the filter fields from URL state into a shape compatible with
 * MultiProjectSessionBoardFilters (used by the TanStack Query hook).
 */
export function toSessionBoardFilters(
  state: MultiProjectCommandCenterUrlState,
): {
  projectIds?: string[];
  group?: string;
  groupBy?: string;
  page?: number;
  pageSize?: number;
} {
  return {
    projectIds: state.projectIds.length > 0 ? state.projectIds : undefined,
    group: state.group ?? undefined,
    groupBy: state.sessionGrouping !== 'state' ? state.sessionGrouping : undefined,
    page: state.page !== 1 ? state.page : undefined,
    pageSize: state.pageSize !== 50 ? state.pageSize : undefined,
  };
}

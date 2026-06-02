/**
 * TanStack Query hooks for the planning domain.
 *
 * T3-001: Three hooks backed by the plain async fetch helpers in services/planning.ts.
 *
 * OQ-2 resolution: freshnessToken is folded into the queryKey for
 * usePlanningSummaryQuery.  When the backend dataFreshness field changes on
 * the next polling cycle, TQ treats the new key as a distinct cache entry and
 * issues a fresh fetch — no stale timer needed.  staleTime is therefore 0 for
 * the summary hook.  The other two hooks (featureContext, sessionBoard) do not
 * carry an externally supplied freshness signal and use staleTime: 30_000.
 *
 * Fetch logic is NOT re-implemented here; this module delegates to the plain
 * async helpers exported from services/planning.ts (getProjectPlanningSummary,
 * getFeaturePlanningContext, getSessionBoard, getFeatureSessionBoard).
 */

import { useQuery } from '@tanstack/react-query';
import type { PlanningBoardGroupingMode, ProjectPlanningSummary, ProjectPlanningGraph, PlanningAgentSessionBoard, PlanningCommandCenterPage } from '../../types';
import {
  getProjectPlanningSummary,
  getFeaturePlanningContext,
  getSessionBoard,
  getFeatureSessionBoard,
  adaptPlanningSummary,
  adaptPlanningGraph,
  adaptPlanningAgentSessionBoard,
} from '../planning';
import {
  getPlanningCommandCenter,
  PlanningCommandCenterApiError,
  type PlanningCommandCenterQuery,
} from '../planningCommandCenter';
import type {
  WireProjectPlanningSummary,
  WireProjectPlanningGraph,
  WirePlanningAgentSessionBoard,
  PlanningAgentSessionBoardPaginated,
} from '../planning';
import { apiRequestJson } from '../apiClient';
import { planningKeys } from '../queryKeys';

// ── usePlanningSummaryQuery ───────────────────────────────────────────────────

export interface UsePlanningSummaryQueryOptions {
  projectId: string | null | undefined;
  /**
   * OQ-2: Backend dataFreshness token.  Pass the token from the most recent
   * response; when it changes TQ issues a new fetch automatically.
   * Typically sourced from the previous summary's `dataFreshness` field.
   */
  freshnessToken?: string | null;
  /** Set false to suppress the query (e.g. project not yet loaded). */
  enabled?: boolean;
}

/**
 * Project-level planning health counts and per-feature summaries.
 *
 * Replaces the manual `cacheProjectPlanningSummary` / `onRevalidated` /
 * `getCachedProjectPlanningSummary` pattern.  TQ provides dedup, background
 * refresh, and loading state at no extra cost.
 *
 * T4-016: staleTime raised from 0 to 30_000 (30 s).
 * The freshnessToken key segment is still the primary invalidation signal —
 * when the token changes TQ issues a fresh fetch for the new key regardless of
 * staleTime.  The non-zero staleTime prevents unnecessary re-fetches on every
 * Planning mount when the token has not changed.
 */
export function usePlanningSummaryQuery({
  projectId,
  freshnessToken,
  enabled = true,
}: UsePlanningSummaryQueryOptions) {
  return useQuery({
    queryKey: planningKeys.summary(projectId ?? '', freshnessToken),
    queryFn: () => {
      if (!projectId) throw new Error('projectId is required');
      return getProjectPlanningSummary(projectId);
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
  });
}

// ── usePlanningFeatureContextQuery ────────────────────────────────────────────

export interface UsePlanningFeatureContextQueryOptions {
  projectId: string | null | undefined;
  featureId: string | null | undefined;
  /** Set false to suppress the query. */
  enabled?: boolean;
}

/**
 * Per-feature planning subgraph, status provenance, and phase context.
 *
 * Replaces the manual PLANNING_FEATURE_CONTEXT_CACHE Map + inFlight dedup.
 * TQ handles concurrent-call dedup and stale-while-revalidate automatically.
 */
export function usePlanningFeatureContextQuery({
  projectId,
  featureId,
  enabled = true,
}: UsePlanningFeatureContextQueryOptions) {
  return useQuery({
    queryKey: planningKeys.featureContext(projectId ?? '', featureId ?? ''),
    queryFn: () => {
      if (!featureId) throw new Error('featureId is required');
      return getFeaturePlanningContext(featureId, { projectId: projectId ?? undefined });
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: !!projectId && !!featureId && enabled,
  });
}

// ── usePlanningSessionBoardQuery ──────────────────────────────────────────────

export interface UsePlanningSessionBoardQueryOptions {
  projectId: string | null | undefined;
  grouping?: PlanningBoardGroupingMode;
  /**
   * Opaque cursor returned as ``nextCursor`` in a prior response.
   * Omit (or pass null/undefined) to fetch the first page.
   * T4-001: FE must tolerate nextCursor being absent in the response.
   */
  cursor?: string | null;
  /**
   * Maximum number of sessions per page.
   * Defaults to 500 (backend default) for backward compatibility.
   * Pass a smaller value (e.g. 50–100) for faster initial loads.
   */
  limit?: number;
  /** Set false to suppress the query. */
  enabled?: boolean;
}

/**
 * Project-wide Planning Agent Session Board (sessions grouped by
 * the chosen dimension).
 *
 * Replaces the manual PLANNING_SESSION_BOARD_CACHE Map + inFlight dedup in
 * getSessionBoard().
 *
 * Pagination (T4-001): pass ``cursor`` + ``limit`` for server-side paging.
 * Omitting both preserves the legacy single-page behavior.
 */
export function usePlanningSessionBoardQuery({
  projectId,
  grouping,
  cursor,
  limit,
  enabled = true,
}: UsePlanningSessionBoardQueryOptions) {
  // Extend the base key with pagination params so different pages occupy
  // distinct cache entries.  planningKeys.projectSessionBoard is not called
  // with extra args to stay compatible with queryKeys.ts (not owned here).
  const baseKey = planningKeys.projectSessionBoard(projectId ?? '', grouping);
  const paginationSegment =
    cursor != null || typeof limit === 'number'
      ? { cursor: cursor ?? null, limit: limit ?? null }
      : undefined;
  const queryKey = paginationSegment != null ? [...baseKey, paginationSegment] : baseKey;

  return useQuery({
    queryKey,
    queryFn: () => {
      if (!projectId) throw new Error('projectId is required');
      return getSessionBoard(projectId, grouping, { cursor: cursor ?? null, limit });
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
  });
}

// ── usePlanningFeatureSessionBoardQuery ───────────────────────────────────────

export interface UsePlanningFeatureSessionBoardQueryOptions {
  projectId: string | null | undefined;
  featureId: string | null | undefined;
  grouping?: PlanningBoardGroupingMode;
  /**
   * Opaque cursor returned as ``nextCursor`` in a prior response.
   * Omit (or pass null/undefined) to fetch the first page.
   * T4-001: FE must tolerate nextCursor being absent in the response.
   */
  cursor?: string | null;
  /**
   * Maximum number of sessions per page.
   * Defaults to 500 (backend default) for backward compatibility.
   */
  limit?: number;
  /** Set false to suppress the query. */
  enabled?: boolean;
}

/**
 * Feature-scoped Planning Agent Session Board.
 *
 * Replaces the manual PLANNING_SESSION_BOARD_CACHE Map + inFlight dedup in
 * getFeatureSessionBoard().
 *
 * Pagination (T4-001): pass ``cursor`` + ``limit`` for server-side paging.
 * Omitting both preserves the legacy single-page behavior.
 */
export function usePlanningFeatureSessionBoardQuery({
  projectId,
  featureId,
  grouping,
  cursor,
  limit,
  enabled = true,
}: UsePlanningFeatureSessionBoardQueryOptions) {
  // Extend the base key with pagination params so different pages occupy
  // distinct cache entries.  planningKeys.featureSessionBoard is not called
  // with extra args to stay compatible with queryKeys.ts (not owned here).
  const baseKey = planningKeys.featureSessionBoard(projectId ?? '', featureId ?? '', grouping);
  const paginationSegment =
    cursor != null || typeof limit === 'number'
      ? { cursor: cursor ?? null, limit: limit ?? null }
      : undefined;
  const queryKey = paginationSegment != null ? [...baseKey, paginationSegment] : baseKey;

  return useQuery({
    queryKey,
    queryFn: () => {
      if (!featureId) throw new Error('featureId is required');
      return getFeatureSessionBoard(featureId, projectId ?? undefined, grouping, { cursor: cursor ?? null, limit });
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: !!projectId && !!featureId && enabled,
  });
}

// ── usePlanningViewQuery ──────────────────────────────────────────────────────

/**
 * Wire shape for GET /api/agent/planning/view?include=graph,session_board.
 *
 * summary is always present; graph and session_board are present only when
 * their respective include= segments are specified.
 *
 * The backend returns snake_case throughout — this interface reflects the raw
 * wire format.  usePlanningViewQuery adapts the payload to camelCase via the
 * adapter functions exported from services/planning.ts before returning it
 * as PlanningViewBundleDTO.  The backend does NOT pre-adapt field names.
 */
interface WirePlanningViewBundle {
  project_id: string;
  summary: WireProjectPlanningSummary;
  graph?: WireProjectPlanningGraph;
  session_board?: WirePlanningAgentSessionBoard;
}

/** Fully adapted (camelCase) planning view bundle returned by usePlanningViewQuery. */
export interface PlanningViewBundleDTO {
  projectId: string;
  summary: ProjectPlanningSummary;
  graph?: ProjectPlanningGraph;
  session_board?: PlanningAgentSessionBoard;
}

export interface UsePlanningViewQueryOptions {
  projectId: string | null | undefined;
  /** When true, the graph sub-payload is requested via include=graph. */
  includeGraph?: boolean;
  /** When true, the session_board sub-payload is requested via include=session_board. */
  includeSessionBoard?: boolean;
  /** Set false to suppress the query. */
  enabled?: boolean;
}

/**
 * T5-007: Fat-read planning view bundle.
 *
 * Cold Planning load issues ONE above-fold request.  Heavy sub-payloads
 * (graph, session_board) are fetched on demand by setting includeGraph /
 * includeSessionBoard = true — this changes the query key, triggering a new
 * fetch with the extended include= param.
 *
 * Query key includes the sorted include array so that graph-loaded and
 * non-graph states occupy distinct cache entries.
 */
export function usePlanningViewQuery({
  projectId,
  includeGraph = false,
  includeSessionBoard = false,
  enabled = true,
}: UsePlanningViewQueryOptions) {
  // Build stable include array from boolean flags
  const include: string[] = [];
  if (includeGraph) include.push('graph');
  if (includeSessionBoard) include.push('session_board');

  // Sort for stable cache identity (already sorted by flag order, but explicit)
  const sortedInclude = [...include].sort() as readonly string[];

  return useQuery<PlanningViewBundleDTO>({
    queryKey: planningKeys.view(projectId ?? '', sortedInclude),
    queryFn: async (): Promise<PlanningViewBundleDTO> => {
      if (!projectId) throw new Error('projectId is required');
      const params = new URLSearchParams();
      params.set('project_id', projectId);
      if (sortedInclude.length > 0) {
        params.set('include', sortedInclude.join(','));
      }
      // Fetch the raw wire payload — the backend returns snake_case throughout.
      // We adapt each sub-payload using the adapter functions from services/planning.ts
      // before returning a fully camelCase PlanningViewBundleDTO to consumers.
      const wire = await apiRequestJson<WirePlanningViewBundle>(
        `/api/agent/planning/view?${params.toString()}`,
      );
      return {
        projectId: wire.project_id ?? '',
        summary: adaptPlanningSummary(wire.summary),
        ...(wire.graph != null ? { graph: adaptPlanningGraph(wire.graph) } : {}),
        ...(wire.session_board != null ? { session_board: adaptPlanningAgentSessionBoard(wire.session_board) } : {}),
      };
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
  });
}

// ── usePlanningCommandCenterQuery ─────────────────────────────────────────────

export interface UsePlanningCommandCenterQueryOptions {
  projectId?: string | null;
  q?: string;
  status?: string;
  phase?: number;
  sortBy?: string;
  sortDirection?: 'asc' | 'desc';
  /** Current page (1-based). Defaults to 1. */
  page?: number;
  /** Items per page. Defaults to 50. */
  pageSize?: number;
  /** Background refetch interval in ms. Omit to disable automatic polling. */
  refetchInterval?: number;
  /** Set false to suppress the query. */
  enabled?: boolean;
}

/**
 * T4-002 / T4-014: TanStack Query hook for the V1 single-project command center.
 *
 * Replaces the manual useEffect + local LoadState + cancellation pattern in
 * PlanningCommandCenter.tsx with standard TQ loading/error/data derivation.
 *
 * staleTime: 30_000 — matches other planning hooks.
 * The full filter + pagination set is in the query key so filter/page changes
 * produce distinct cache entries without manual invalidation.
 */
export function usePlanningCommandCenterQuery({
  projectId,
  q,
  status,
  phase,
  sortBy,
  sortDirection,
  page,
  pageSize,
  refetchInterval,
  enabled = true,
}: UsePlanningCommandCenterQueryOptions = {}) {
  const filters: PlanningCommandCenterQuery = {
    projectId: projectId ?? undefined,
    q,
    status,
    phase,
    sortBy,
    sortDirection,
    page,
    pageSize,
  };

  return useQuery<PlanningCommandCenterPage, PlanningCommandCenterApiError>({
    queryKey: planningKeys.commandCenter(projectId ?? '', {
      q,
      status,
      phase,
      sortBy,
      sortDirection,
      page,
      pageSize,
    }),
    queryFn: () => getPlanningCommandCenter(filters),
    staleTime: 30_000,
    gcTime: 300_000,
    refetchInterval,
    refetchIntervalInBackground: false,
    enabled: !!projectId && enabled,
  });
}

// ── useMultiProjectCommandCenterQuery ─────────────────────────────────────────

import type {
  MultiProjectCommandCenterResponse,
  MultiProjectSessionBoardResponse,
} from '../../types';
import {
  fetchMultiProjectCommandCenter,
  fetchMultiProjectSessionBoard,
  type MultiProjectCommandCenterQuery,
  type MultiProjectSessionBoardQuery,
} from '../multiProjectPlanningCommandCenter';
import {
  multiProjectPlanningKeys,
  type MultiProjectCommandCenterFilters,
  type MultiProjectSessionBoardFilters,
} from '../queryKeys';
import { MULTI_PROJECT_COMMAND_CENTER_ENABLED, MULTI_PROJECT_COMMAND_CENTER_ENABLED_DEFAULT } from '../../constants';
import { useLaunchCapabilitiesQuery } from './capabilities';

export interface UseMultiProjectCommandCenterQueryOptions {
  /**
   * Filter + pagination parameters forwarded to the aggregate endpoint.
   * Changing any field produces a new cache entry (all fields are in the key).
   */
  filters?: MultiProjectCommandCenterFilters;
  /**
   * Whether the project list is ready (at least one project known).
   * The query is gated on flag AND projectListReady to avoid spurious fetches
   * before the project list has loaded.
   */
  projectListReady?: boolean;
  /** Set false to explicitly suppress the query. */
  enabled?: boolean;
}

/**
 * MPCC-403 / P5-001: TanStack Query hook for the multi-project aggregate command center.
 *
 * Gated on:
 *   1. Runtime caps.multiProjectCommandCenterEnabled (P5-001 runtime flag, replaces
 *      build-time MULTI_PROJECT_COMMAND_CENTER_ENABLED as the authoritative gate).
 *      Falls back to MULTI_PROJECT_COMMAND_CENTER_ENABLED_DEFAULT when caps are
 *      not yet loaded, ensuring the feature stays off by default until confirmed.
 *      The build-time MULTI_PROJECT_COMMAND_CENTER_ENABLED constant is retained as
 *      an emergency override only.
 *   2. projectListReady (project list has resolved — avoids fetching before
 *      the project scope is known)
 *   3. enabled prop (explicit suppression)
 *
 * staleTime: 30_000 — soft-TTL matches existing planning hooks.
 * The query key includes all filter fields so any filter change invalidates
 * and re-fetches automatically.
 *
 * Never mutates the active project.  Read-only.
 */
export function useMultiProjectCommandCenterQuery({
  filters = {},
  projectListReady = true,
  enabled = true,
}: UseMultiProjectCommandCenterQueryOptions = {}) {
  const { data: caps } = useLaunchCapabilitiesQuery();
  // P5-001: prefer runtime caps; fall back to build-time DEFAULT (not the Vite env
  // flag) so the feature stays off until the server explicitly enables it.
  const runtimeEnabled =
    caps?.multiProjectCommandCenterEnabled ??
    MULTI_PROJECT_COMMAND_CENTER_ENABLED_DEFAULT;

  return useQuery<MultiProjectCommandCenterResponse>({
    queryKey: multiProjectPlanningKeys.commandCenter(filters),
    queryFn: (): Promise<MultiProjectCommandCenterResponse> => {
      const fetchQuery: MultiProjectCommandCenterQuery = {
        projectIds: filters.projectIds,
        status: filters.status,
        kind: filters.kind,
        group: filters.group,
        search: filters.search,
        page: filters.page,
        pageSize: filters.pageSize,
        sort: filters.sort,
      };
      return fetchMultiProjectCommandCenter(fetchQuery);
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: runtimeEnabled && projectListReady && enabled,
  });
}

// ── useMultiProjectSessionBoardQuery ──────────────────────────────────────────

export interface UseMultiProjectSessionBoardQueryOptions {
  /** Filter + pagination parameters forwarded to the aggregate session-board endpoint. */
  filters?: MultiProjectSessionBoardFilters;
  /**
   * Whether the project list is ready (at least one project known).
   * Prevents fetching before project scope resolves.
   */
  projectListReady?: boolean;
  /** Set false to explicitly suppress the query. */
  enabled?: boolean;
}

/**
 * MPCC-403 / P5-001: TanStack Query hook for the multi-project aggregate session board.
 *
 * Gated on runtime caps.multiProjectCommandCenterEnabled (P5-001) +
 * projectListReady + enabled.  Falls back to MULTI_PROJECT_COMMAND_CENTER_ENABLED_DEFAULT
 * when caps are loading.
 * staleTime: 30_000 — consistent with single-project session board hooks.
 *
 * Never mutates the active project.  Read-only.
 */
export function useMultiProjectSessionBoardQuery({
  filters = {},
  projectListReady = true,
  enabled = true,
}: UseMultiProjectSessionBoardQueryOptions = {}) {
  const { data: caps } = useLaunchCapabilitiesQuery();
  const runtimeEnabled =
    caps?.multiProjectCommandCenterEnabled ??
    MULTI_PROJECT_COMMAND_CENTER_ENABLED_DEFAULT;

  return useQuery<MultiProjectSessionBoardResponse>({
    queryKey: multiProjectPlanningKeys.sessionBoard(filters),
    queryFn: (): Promise<MultiProjectSessionBoardResponse> => {
      const fetchQuery: MultiProjectSessionBoardQuery = {
        projectIds: filters.projectIds,
        group: filters.group,
        groupBy: filters.groupBy as MultiProjectSessionBoardQuery['groupBy'],
        activeWindowMinutes: filters.activeWindowMinutes,
        includeWorkers: filters.includeWorkers,
        page: filters.page,
        pageSize: filters.pageSize,
        includeStale: filters.includeStale,
      };
      return fetchMultiProjectSessionBoard(fetchQuery);
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: runtimeEnabled && projectListReady && enabled,
  });
}

// ── usePortfolioRollupQuery ───────────────────────────────────────────────────

/**
 * Wire shape for GET /api/agent/planning/portfolio/rollup?project_ids=
 * Backend returns snake_case throughout.
 */
interface PortfolioProjectWire {
  project_id: string;
  display: string;
  status_counts: Record<string, number>;
  active_sessions: number;
  changed_recently: boolean;
  needs_attention: boolean;
  token_total: number;
}

interface PortfolioAttentionWire {
  active_now: string[];
  changed_recently: string[];
  needs_attention: string[];
  next_work: string[];
}

interface PortfolioRollupWire {
  projects: PortfolioProjectWire[];
  attention: PortfolioAttentionWire;
  generated_at: string;
}

/** Adapted camelCase shape returned to consumers. */
export interface PortfolioProject {
  projectId: string;
  display: string;
  /** Status counts keyed by status string (e.g. 'active', 'blocked', 'done'). */
  statusCounts: Record<string, number>;
  activeSessions: number;
  changedRecently: boolean;
  needsAttention: boolean;
  tokenTotal: number;
}

export interface PortfolioAttention {
  activeNow: string[];
  changedRecently: string[];
  needsAttention: string[];
  nextWork: string[];
}

export interface PortfolioRollupDTO {
  projects: PortfolioProject[];
  attention: PortfolioAttention;
  generatedAt: string;
}

function adaptPortfolioRollup(wire: PortfolioRollupWire): PortfolioRollupDTO {
  return {
    projects: (wire.projects ?? []).map((p) => ({
      projectId: p.project_id ?? '',
      display: p.display ?? '',
      statusCounts: p.status_counts ?? {},
      activeSessions: p.active_sessions ?? 0,
      changedRecently: p.changed_recently ?? false,
      needsAttention: p.needs_attention ?? false,
      tokenTotal: p.token_total ?? 0,
    })),
    attention: {
      activeNow: wire.attention?.active_now ?? [],
      changedRecently: wire.attention?.changed_recently ?? [],
      needsAttention: wire.attention?.needs_attention ?? [],
      nextWork: wire.attention?.next_work ?? [],
    },
    generatedAt: wire.generated_at ?? '',
  };
}

export interface UsePortfolioRollupQueryOptions {
  /** Project IDs to include in the rollup. Omit for all projects. */
  projectIds?: string[];
  /** Set false to suppress the query. */
  enabled?: boolean;
}

/**
 * P5-001 / AC-1: Portfolio-level rollup across all (or selected) projects.
 *
 * Fetches GET /api/agent/planning/portfolio/rollup?project_ids=
 * Returns the four attention lenses (active now / changed recently /
 * needs attention / next work) plus per-project statusCounts and tokenTotal.
 *
 * This is an above-fold request — staleTime: 30_000, no polling.
 * Resilience: all fields have defined FE fallbacks (missing → empty/zero).
 */
export function usePortfolioRollupQuery({
  projectIds,
  enabled = true,
}: UsePortfolioRollupQueryOptions = {}) {
  return useQuery<PortfolioRollupDTO>({
    queryKey: multiProjectPlanningKeys.portfolioRollup(projectIds),
    queryFn: async (): Promise<PortfolioRollupDTO> => {
      const params = new URLSearchParams();
      if (projectIds && projectIds.length > 0) {
        params.set('project_ids', projectIds.join(','));
      }
      const qs = params.toString();
      const url = `/api/agent/planning/portfolio/rollup${qs ? `?${qs}` : ''}`;
      const wire = await apiRequestJson<PortfolioRollupWire>(url);
      return adaptPortfolioRollup(wire);
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled,
  });
}

// ── useNextWorkQuery ──────────────────────────────────────────────────────────

/** Wire shape for a single next-work item from the backend. */
interface NextWorkItemWire {
  feature_id: string;
  project_id: string;
  rank: number;
  readiness: number;
  next_phase: number | null;
  blockers: string[];
  story_points: number | null;
  command: string | null;
}

interface NextWorkResponseWire {
  items: NextWorkItemWire[];
  next_cursor: string | null;
}

/** Adapted camelCase next-work item. */
export interface NextWorkItem {
  featureId: string;
  projectId: string;
  rank: number;
  readiness: number;
  nextPhase: number | null;
  blockers: string[];
  storyPoints: number | null;
  command: string | null;
}

export interface NextWorkResponse {
  items: NextWorkItem[];
  nextCursor: string | null;
}

function adaptNextWorkResponse(wire: NextWorkResponseWire): NextWorkResponse {
  return {
    items: (wire.items ?? []).map((i) => ({
      featureId: i.feature_id ?? '',
      projectId: i.project_id ?? '',
      rank: i.rank ?? 0,
      readiness: i.readiness ?? 0,
      nextPhase: i.next_phase ?? null,
      blockers: i.blockers ?? [],
      storyPoints: i.story_points ?? null,
      command: i.command ?? null,
    })),
    nextCursor: wire.next_cursor ?? null,
  };
}

export interface UseNextWorkQueryOptions {
  /** Project IDs to scope results. Omit for all projects. */
  projectIds?: string[];
  /** Maximum items per page. */
  limit?: number;
  /** Opaque cursor from a prior response. Omit for first page. */
  cursor?: string | null;
  /** Set false to suppress the query. */
  enabled?: boolean;
}

/**
 * P5-001 / AC-1: Next-work queue across projects.
 *
 * Fetches GET /api/agent/planning/next-work?project_ids=&limit=&cursor=
 * Returns ranked next-work items with readiness, blockers, and suggested command.
 *
 * This is a below-fold / on-demand request — staleTime: 30_000.
 * Resilience: all fields have defined FE fallbacks (missing → empty/zero/null).
 */
export function useNextWorkQuery({
  projectIds,
  limit,
  cursor,
  enabled = true,
}: UseNextWorkQueryOptions = {}) {
  return useQuery<NextWorkResponse>({
    queryKey: multiProjectPlanningKeys.nextWork({ projectIds, limit, cursor }),
    queryFn: async (): Promise<NextWorkResponse> => {
      const params = new URLSearchParams();
      if (projectIds && projectIds.length > 0) {
        params.set('project_ids', projectIds.join(','));
      }
      if (typeof limit === 'number') params.set('limit', String(limit));
      if (cursor) params.set('cursor', cursor);
      const qs = params.toString();
      const url = `/api/agent/planning/next-work${qs ? `?${qs}` : ''}`;
      const wire = await apiRequestJson<NextWorkResponseWire>(url);
      return adaptNextWorkResponse(wire);
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled,
  });
}

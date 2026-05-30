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
import type { PlanningBoardGroupingMode, ProjectPlanningSummary, ProjectPlanningGraph, PlanningAgentSessionBoard } from '../../types';
import {
  getProjectPlanningSummary,
  getFeaturePlanningContext,
  getSessionBoard,
  getFeatureSessionBoard,
  adaptPlanningSummary,
  adaptPlanningGraph,
  adaptPlanningAgentSessionBoard,
} from '../planning';
import type {
  WireProjectPlanningSummary,
  WireProjectPlanningGraph,
  WirePlanningAgentSessionBoard,
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
 * staleTime: 0 — the freshnessToken key segment drives re-fetching, not a
 * timer.  A changed token means a new queryKey which triggers a fresh fetch.
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
    staleTime: 0,
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
  /** Set false to suppress the query. */
  enabled?: boolean;
}

/**
 * Project-wide Planning Agent Session Board (all sessions grouped by
 * the chosen dimension).
 *
 * Replaces the manual PLANNING_SESSION_BOARD_CACHE Map + inFlight dedup in
 * getSessionBoard().
 */
export function usePlanningSessionBoardQuery({
  projectId,
  grouping,
  enabled = true,
}: UsePlanningSessionBoardQueryOptions) {
  return useQuery({
    queryKey: planningKeys.projectSessionBoard(projectId ?? '', grouping),
    queryFn: () => {
      if (!projectId) throw new Error('projectId is required');
      return getSessionBoard(projectId, grouping);
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
  /** Set false to suppress the query. */
  enabled?: boolean;
}

/**
 * Feature-scoped Planning Agent Session Board.
 *
 * Replaces the manual PLANNING_SESSION_BOARD_CACHE Map + inFlight dedup in
 * getFeatureSessionBoard().
 */
export function usePlanningFeatureSessionBoardQuery({
  projectId,
  featureId,
  grouping,
  enabled = true,
}: UsePlanningFeatureSessionBoardQueryOptions) {
  return useQuery({
    queryKey: planningKeys.featureSessionBoard(projectId ?? '', featureId ?? '', grouping),
    queryFn: () => {
      if (!featureId) throw new Error('featureId is required');
      return getFeatureSessionBoard(featureId, projectId ?? undefined, grouping);
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
import { MULTI_PROJECT_COMMAND_CENTER_ENABLED } from '../../constants';

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
 * MPCC-403: TanStack Query hook for the multi-project aggregate command center.
 *
 * Gated on:
 *   1. MULTI_PROJECT_COMMAND_CENTER_ENABLED (env-var flag)
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
    enabled: MULTI_PROJECT_COMMAND_CENTER_ENABLED && projectListReady && enabled,
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
 * MPCC-403: TanStack Query hook for the multi-project aggregate session board.
 *
 * Gated on MULTI_PROJECT_COMMAND_CENTER_ENABLED + projectListReady + enabled.
 * staleTime: 30_000 — consistent with single-project session board hooks.
 *
 * Never mutates the active project.  Read-only.
 */
export function useMultiProjectSessionBoardQuery({
  filters = {},
  projectListReady = true,
  enabled = true,
}: UseMultiProjectSessionBoardQueryOptions = {}) {
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
    enabled: MULTI_PROJECT_COMMAND_CENTER_ENABLED && projectListReady && enabled,
  });
}

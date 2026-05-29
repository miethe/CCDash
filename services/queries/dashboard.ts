/**
 * TanStack Query hooks for the dashboard bundle endpoint.
 *
 * T5-005: useDashboardBundleQuery — fat-read backed by GET /api/v1/dashboard
 *
 * One call on cold Dashboard load replaces the separate useSessionsQuery +
 * useTasksQuery pair.  staleTime: 10_000 matches the backend @memoized_query
 * TTL for live task counts.
 *
 * Resilience contract (AC-R-P2):
 *   - sessions missing  → [] (empty list, Dashboard shows empty state)
 *   - task_counts missing → {} (zero counts, badges show 0)
 */

import { useQuery } from '@tanstack/react-query';
import { apiRequestJson } from '../apiClient';
import { dashboardKeys } from '../queryKeys';

// ── DTO shapes (mirrors backend DashboardBundleDTO) ───────────────────────────

/**
 * Wire shape returned by GET /api/v1/dashboard → ClientV1Envelope[DashboardBundleDTO].
 * Fields are snake_case to match the backend serialization.
 */
export interface SessionCardDTO {
  session_id: string;
  title: string | null;
  status: string | null;
  started_at: string | null;
  ended_at: string | null;
  model: string | null;
  total_cost: number | null;
  total_tokens: number | null;
  feature_id: string | null;
  root_session_id: string | null;
}

export interface DashboardBundleDTO {
  project_id: string;
  sessions: SessionCardDTO[];
  task_counts: Record<string, number>;
}

/** ClientV1Envelope wrapper shape. */
interface ClientV1Envelope<T> {
  data: T;
  meta?: Record<string, unknown>;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export interface UseDashboardBundleQueryOptions {
  projectId: string | null | undefined;
  /** Set false to suppress the query (e.g. project not yet loaded). */
  enabled?: boolean;
}

export interface DashboardBundleResult {
  sessions: SessionCardDTO[];
  taskCounts: Record<string, number>;
  isLoading: boolean;
  error: Error | null;
}

/**
 * Fetches the dashboard fat-read bundle in a single request.
 *
 * Returns { sessions, taskCounts, isLoading, error }.
 *
 * AC-R-P2 resilience:
 *   - taskCounts ?? {} — missing field yields empty map; badges show 0
 *   - sessions ?? []  — missing field yields empty array; list shows empty state
 */
export function useDashboardBundleQuery({
  projectId,
  enabled = true,
}: UseDashboardBundleQueryOptions): DashboardBundleResult {
  const query = useQuery({
    queryKey: dashboardKeys.bundle(projectId ?? ''),
    queryFn: async (): Promise<DashboardBundleDTO> => {
      if (!projectId) throw new Error('projectId is required');
      const envelope = await apiRequestJson<ClientV1Envelope<DashboardBundleDTO>>(
        '/api/v1/dashboard',
      );
      return envelope.data;
    },
    staleTime: 10_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
  });

  const raw = query.data;
  return {
    // AC-R-P2: null/undefined fields degrade to empty defaults
    sessions: raw?.sessions ?? [],
    taskCounts: raw?.task_counts ?? {},
    isLoading: query.isPending,
    error: query.error as Error | null,
  };
}

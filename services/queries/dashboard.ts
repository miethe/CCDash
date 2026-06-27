/**
 * TanStack Query hooks for the dashboard bundle endpoint.
 *
 * T5-005: useDashboardBundleQuery — fat-read backed by GET /api/v1/dashboard
 *
 * One call on cold Dashboard load replaces the separate useSessionsQuery +
 * useTasksQuery pair.  staleTime: 10_000 matches the backend @memoized_query
 * TTL for live task counts.
 *
 * T4-011: useDashboardChartQuery — replaces the imperative useEffect that called
 * getSessionCostCalibration + getSeries (cost + velocity).
 *
 * T4-011 / T4-006-1: useLiveAgentsCountQuery — replaces the manual setInterval
 * useLiveAgentsCount hook with a visibility-aware refetchInterval.
 *
 * Resilience contract (AC-R-P2):
 *   - sessions missing  → [] (empty list, Dashboard shows empty state)
 *   - task_counts missing → {} (zero counts, badges show 0)
 *   - chart data missing → { chartData: [], costCalibration: null }
 *   - live count missing → null (render "--" not "0")
 */

import { useQuery } from '@tanstack/react-query';
import { apiFetch, apiRequestJson } from '../apiClient';
import { analyticsService } from '../analytics';
import { dashboardKeys } from '../queryKeys';
import type { SessionCostCalibrationSummary } from '../../types';

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
  // Phase 5 detection facts (optional/nullable; the bundle may omit them — a
  // missing value is a contract state, surfaced as "not detected", never an error).
  context_window?: string | null;
  skill_name?: string | null;
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

// ── Chart series + calibration ─────────────────────────────────────────────────

export interface DashboardChartPoint {
  date: string;
  cost: number;
  velocity: number;
}

export interface DashboardChartResult {
  chartData: DashboardChartPoint[];
  costCalibration: SessionCostCalibrationSummary | null;
  isLoading: boolean;
  isError: boolean;
}

/**
 * T4-011: Fetches cost calibration + cost/velocity series in parallel.
 *
 * Replaces the imperative useEffect in Dashboard.tsx that called
 * getSessionCostCalibration() + getSeries() and stored results in local state.
 *
 * Resilience:
 *   - calibration failure → costCalibration: null (calibration info shows 0s)
 *   - series failure      → chartData: [] (chart shows empty state)
 */
export function useDashboardChartQuery({
  projectId,
  enabled = true,
}: {
  projectId: string | null | undefined;
  enabled?: boolean;
}): DashboardChartResult {
  const query = useQuery<DashboardChartResult>({
    queryKey: dashboardKeys.chart(projectId ?? ''),
    queryFn: async (): Promise<DashboardChartResult> => {
      const [calibrationResult, costSeriesResult, velocitySeriesResult] = await Promise.allSettled([
        analyticsService.getSessionCostCalibration(),
        analyticsService.getSeries({ metric: 'session_cost', period: 'daily', limit: 120 }),
        analyticsService.getSeries({ metric: 'task_velocity', period: 'daily', limit: 120 }),
      ]);

      const costCalibration =
        calibrationResult.status === 'fulfilled' ? calibrationResult.value : null;
      const costSeries =
        costSeriesResult.status === 'fulfilled' ? costSeriesResult.value : null;
      const velocitySeries =
        velocitySeriesResult.status === 'fulfilled' ? velocitySeriesResult.value : null;

      let chartData: DashboardChartPoint[] = [];
      if (costSeries || velocitySeries) {
        const byDate = new Map<string, DashboardChartPoint>();
        for (const point of costSeries?.items || []) {
          const date = String(point.captured_at || '').slice(0, 10);
          if (!date) continue;
          const current = byDate.get(date) || { date, cost: 0, velocity: 0 };
          current.cost = Number(point.value || 0);
          byDate.set(date, current);
        }
        for (const point of velocitySeries?.items || []) {
          const date = String(point.captured_at || '').slice(0, 10);
          if (!date) continue;
          const current = byDate.get(date) || { date, cost: 0, velocity: 0 };
          current.velocity = Number(point.value || 0);
          byDate.set(date, current);
        }
        chartData = Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date));
      }

      return { chartData, costCalibration, isLoading: false, isError: false };
    },
    staleTime: 60_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
  });

  return {
    chartData: query.data?.chartData ?? [],
    costCalibration: query.data?.costCalibration ?? null,
    isLoading: query.isPending,
    isError: query.isError,
  };
}

// ── Live active-agents count ───────────────────────────────────────────────────

/**
 * T4-011 / T4-006-1: Replaces the manual setInterval-based useLiveAgentsCount hook.
 *
 * Uses useQuery with refetchInterval: 10_000 for visibility-aware polling.
 * refetchIntervalInBackground defaults to false so background tabs don't thrash
 * the API (~5400 req / 15-hour idle prevented).
 *
 * Resilience (R-P2): returns null on pending/error — caller renders "--" not "0".
 */
export function useLiveAgentsCountQuery(): number | null {
  const query = useQuery<number | null>({
    queryKey: dashboardKeys.liveCount(),
    queryFn: async (): Promise<number | null> => {
      const res = await apiFetch('/api/agent/live/active-count');
      if (!res.ok) return null;
      const data = await res.json() as { count?: unknown };
      const raw = data?.count;
      return typeof raw === 'number' ? raw : null;
    },
    staleTime: 0,
    gcTime: 30_000,
    refetchInterval: 10_000,
    // visibility-aware: stops polling when tab is hidden (default false)
    refetchIntervalInBackground: false,
  });

  // isPending (no data yet) or error → null (resilience contract)
  if (query.isPending || query.isError) return null;
  return query.data ?? null;
}

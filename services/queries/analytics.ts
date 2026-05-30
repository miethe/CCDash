/**
 * TanStack Query hooks for the analytics domain.
 *
 * T5-007 (best-effort): useAnalyticsOverviewQuery — above-fold analytics
 * backed by GET /api/analytics/overview-bundle.
 *
 * This replaces the manual analyticsService.getOverview() + getSeries() calls
 * in Dashboard.tsx / AnalyticsDashboard.tsx for the above-fold KPI cards.
 */

import { useQuery } from '@tanstack/react-query';
import { apiRequestJson } from '../apiClient';
import { analyticsKeys } from '../queryKeys';
import type { AnalyticsOverview } from '../../types';

// ── DTO shapes (mirrors backend AnalyticsOverviewBundleDTO) ───────────────────

export interface AnalyticsOverviewBundleDTO {
  project_id: string;
  kpis: AnalyticsOverview['kpis'];
  top_models: Array<{ name: string; usage: number }>;
  range: AnalyticsOverview['range'];
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export interface UseAnalyticsOverviewQueryOptions {
  projectId: string | null | undefined;
  /** Set false to suppress the query. */
  enabled?: boolean;
}

/**
 * Above-fold analytics overview bundle.
 *
 * One request per Analytics view load.  Tab-specific breakdowns remain lazy
 * and are fetched on demand by AnalyticsDashboard.tsx.
 *
 * Resilience:
 *   - kpis missing   → {} (KPI cards show 0)
 *   - top_models missing → [] (model chart shows empty)
 */
export function useAnalyticsOverviewQuery({
  projectId,
  enabled = true,
}: UseAnalyticsOverviewQueryOptions) {
  return useQuery<AnalyticsOverviewBundleDTO>({
    queryKey: analyticsKeys.overviewBundle(projectId ?? ''),
    queryFn: async (): Promise<AnalyticsOverviewBundleDTO> => {
      if (!projectId) throw new Error('projectId is required');
      return apiRequestJson<AnalyticsOverviewBundleDTO>(
        `/api/analytics/overview-bundle?project_id=${encodeURIComponent(projectId)}`,
      );
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
  });
}

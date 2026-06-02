/**
 * TanStack Query hooks for the analytics domain.
 *
 * T5-007 (best-effort): useAnalyticsOverviewQuery — above-fold analytics
 * backed by GET /api/analytics/overview-bundle.
 *
 * T4-012: Individual domain hooks for AnalyticsDashboard.tsx, replacing the
 * 7-parallel-fetch Promise.all useEffect (getOverview, getNotifications,
 * getArtifacts, getCorrelation, getSessionCostCalibration, getUsageAttribution,
 * getUsageAttributionCalibration) and the per-tab drilldown useEffect.
 *
 * Each hook is individually enabled (no shared loading gate), so a slow
 * endpoint cannot block the others.  The component renders progressively as
 * each query settles.
 *
 * Resilience: every hook returns a safe empty/null fallback so the component
 * never crashes on missing fields.
 */

import { useQuery } from '@tanstack/react-query';
import { apiRequestJson } from '../apiClient';
import { analyticsKeys } from '../queryKeys';
import { analyticsService } from '../analytics';
import type { ArtifactRankingsResponse } from '../analytics';
import type {
  AnalyticsOverview,
  AnalyticsArtifactsResponse,
  AnalyticsCorrelationItem,
  Notification,
  SessionCostCalibrationSummary,
  SessionUsageAggregateResponse,
  SessionUsageCalibrationSummary,
  SessionUsageDrilldownResponse,
} from '../../types';

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

// ── T4-012: AnalyticsDashboard per-domain hooks ───────────────────────────────

/** Shared options shape for project-scoped analytics queries. */
interface AnalyticsQueryOptions {
  projectId: string | null | undefined;
  enabled?: boolean;
}

/**
 * T4-012: Full analytics overview (not the bundle — the raw /api/analytics/overview).
 * Used by AnalyticsDashboard overview tab.  Decoupled from other domain queries.
 */
export function useAnalyticsFullOverviewQuery({ projectId, enabled = true }: AnalyticsQueryOptions) {
  return useQuery<AnalyticsOverview | null>({
    queryKey: analyticsKeys.overview(projectId ?? ''),
    queryFn: async (): Promise<AnalyticsOverview | null> => {
      try {
        return await analyticsService.getOverview();
      } catch {
        return null;
      }
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
    // null is a valid "empty" result — treat it as success
    placeholderData: null,
  });
}

/**
 * T4-012: Notifications (recent alerts) for the overview tab.
 */
export function useAnalyticsNotificationsQuery({ projectId, enabled = true }: AnalyticsQueryOptions) {
  return useQuery<Notification[]>({
    queryKey: analyticsKeys.notifications(projectId ?? ''),
    queryFn: async (): Promise<Notification[]> => {
      try {
        return await analyticsService.getNotifications();
      } catch {
        return [];
      }
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
    placeholderData: [],
  });
}

/**
 * T4-012: Artifacts analytics — type/source/model breakdown.
 * Used by artifacts + models_tools + features tabs.
 */
export function useAnalyticsArtifactsQuery({ projectId, enabled = true }: AnalyticsQueryOptions) {
  return useQuery<AnalyticsArtifactsResponse | null>({
    queryKey: analyticsKeys.artifacts(projectId ?? ''),
    queryFn: async (): Promise<AnalyticsArtifactsResponse | null> => {
      try {
        return await analyticsService.getArtifacts({ limit: 200 });
      } catch {
        return null;
      }
    },
    staleTime: 60_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
    placeholderData: null,
  });
}

/**
 * T4-012: Session ↔ feature correlation table.
 */
export function useAnalyticsCorrelationQuery({ projectId, enabled = true }: AnalyticsQueryOptions) {
  return useQuery<AnalyticsCorrelationItem[]>({
    queryKey: analyticsKeys.correlation(projectId ?? ''),
    queryFn: async (): Promise<AnalyticsCorrelationItem[]> => {
      try {
        const result = await analyticsService.getCorrelation();
        return result.items || [];
      } catch {
        return [];
      }
    },
    staleTime: 60_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
    placeholderData: [],
  });
}

/**
 * T4-012: Session cost calibration summary.
 * Used by overview + correlation tabs.
 */
export function useAnalyticsCostCalibrationQuery({ projectId, enabled = true }: AnalyticsQueryOptions) {
  return useQuery<SessionCostCalibrationSummary | null>({
    queryKey: analyticsKeys.costCalibration(projectId ?? ''),
    queryFn: async (): Promise<SessionCostCalibrationSummary | null> => {
      try {
        return await analyticsService.getSessionCostCalibration();
      } catch {
        return null;
      }
    },
    staleTime: 60_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
    placeholderData: null,
  });
}

/**
 * T4-012: Usage attribution aggregate rows.
 * Only runs when usageAttributionAvailable is true.
 */
export function useAnalyticsUsageAttributionQuery({
  projectId,
  enabled = true,
}: AnalyticsQueryOptions) {
  return useQuery<SessionUsageAggregateResponse | null>({
    queryKey: analyticsKeys.usageAttribution(projectId ?? ''),
    queryFn: async (): Promise<SessionUsageAggregateResponse | null> => {
      try {
        return await analyticsService.getUsageAttribution({ limit: 24 });
      } catch {
        return null;
      }
    },
    staleTime: 60_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
    placeholderData: null,
  });
}

/**
 * T4-012: Usage attribution calibration summary.
 * Only runs when usageAttributionAvailable is true.
 */
export function useAnalyticsUsageCalibrationQuery({
  projectId,
  enabled = true,
}: AnalyticsQueryOptions) {
  return useQuery<SessionUsageCalibrationSummary | null>({
    queryKey: analyticsKeys.usageCalibration(projectId ?? ''),
    queryFn: async (): Promise<SessionUsageCalibrationSummary | null> => {
      try {
        return await analyticsService.getUsageAttributionCalibration();
      } catch {
        return null;
      }
    },
    staleTime: 60_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
    placeholderData: null,
  });
}

// ── P5-007: Artifact Rankings hook ───────────────────────────────────────────

/**
 * P5-007: Ranked artifact intelligence for the FeatureDetailShell Artifacts tab.
 *
 * Wraps analyticsService.fetchArtifactRankings keyed by
 * analyticsKeys.artifactRankings(projectId) so that invalidation is handled by
 * the shared key (matching the sibling analytics surface).
 *
 * staleTime: 60_000 — ranking data changes slowly; aligned with the analytics
 * domain convention.
 *
 * Resilience: returns null on any error; callers must supply a fallback.
 */
export interface UseArtifactRankingsQueryParams {
  collection?: string;
  user?: string;
  period?: string;
  artifactType?: string;
  workflow?: string;
  recommendationType?: string;
  offset?: number;
  limit?: number;
}

export interface UseArtifactRankingsQueryOptions extends AnalyticsQueryOptions {
  params?: UseArtifactRankingsQueryParams;
}

export function useArtifactRankingsQuery({
  projectId,
  params,
  enabled = true,
}: UseArtifactRankingsQueryOptions) {
  return useQuery<ArtifactRankingsResponse | null>({
    queryKey: analyticsKeys.artifactRankings(projectId ?? ''),
    queryFn: async (): Promise<ArtifactRankingsResponse | null> => {
      if (!projectId) throw new Error('projectId is required');
      try {
        return await analyticsService.fetchArtifactRankings({
          project: projectId,
          ...params,
        });
      } catch {
        return null;
      }
    },
    staleTime: 60_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
    placeholderData: null,
  });
}

/**
 * T4-012: Per-entity attribution drilldown.
 * Keyed by entityType + entityId so each selection gets its own cache slot.
 * Enabled only when an entity is selected.
 */
export function useAnalyticsUsageDrilldownQuery({
  projectId,
  entityType,
  entityId,
  enabled = true,
}: AnalyticsQueryOptions & {
  entityType: string | null;
  entityId: string | null;
}) {
  return useQuery<SessionUsageDrilldownResponse | null>({
    queryKey: analyticsKeys.usageDrilldown(projectId ?? '', entityType, entityId),
    queryFn: async (): Promise<SessionUsageDrilldownResponse | null> => {
      if (!entityType || !entityId) return null;
      try {
        return await analyticsService.getUsageAttributionDrilldown({
          entityType,
          entityId,
          limit: 30,
        });
      } catch {
        return null;
      }
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: !!projectId && !!entityType && !!entityId && enabled,
    placeholderData: null,
  });
}

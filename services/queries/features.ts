/**
 * TanStack Query hooks for the features domain.
 *
 * T2-004: useFeaturesQuery — offset-paginated list backed by
 *   GET /api/features?view=cards&page=N
 *
 * Paginated shape: { items: Feature[], total, page, pageSize }
 *
 * The useData().features facade reads from this hook's TQ cache via a shim
 * in DataContext.tsx so non-migrated consumers continue working unchanged.
 *
 * ProjectBoard legacy path reads from useFeaturesQuery page 0 for the
 * apiFeatures fallback used in modal lookups and category derivation.
 */

import { useQuery } from '@tanstack/react-query';
import { useDataClient } from '../../contexts/DataClientContext';
import { isFeatureLiveUpdatesEnabled } from '../live/config';
import { featuresKeys } from '../queryKeys';
import type { Feature } from '../../types';
import type { PaginatedResponse } from '../../contexts/dataContextShared';

export const FEATURES_PAGE_SIZE = 100;

// ── Paginated shape ────────────────────────────────────────────────────────────

export interface FeaturesPage {
  items: Feature[];
  total: number;
  page: number;
  pageSize: number;
}

// ── useFeaturesQuery ───────────────────────────────────────────────────────────

export interface UseFeaturesQueryOptions {
  projectId: string | null | undefined;
  query?: string;
  page?: number;
  /** Set to false to suppress the query (e.g. auth not yet resolved). */
  enabled?: boolean;
}

/**
 * Offset-paginated query for the feature list.
 *
 * Returns `{ items, total, page, pageSize }`. Consumers read `items` for list
 * render and `total` for counts — not the raw array length.
 *
 * ProjectBoard reads page=0 for its legacy `apiFeatures` fallback path.
 * The v2 surface uses `useFeatureSurface` independently.
 */
export function useFeaturesQuery({
  projectId,
  query,
  page = 0,
  enabled = true,
}: UseFeaturesQueryOptions) {
  const client = useDataClient();

  return useQuery<FeaturesPage>({
    queryKey: featuresKeys.list(projectId ?? '', query, page),
    queryFn: async (): Promise<FeaturesPage> => {
      const raw = await client.getFeaturesPaginated(page, FEATURES_PAGE_SIZE, query);
      if (Array.isArray(raw)) {
        return {
          items: raw,
          total: raw.length,
          page,
          pageSize: FEATURES_PAGE_SIZE,
        };
      }
      const paginated = raw as PaginatedResponse<Feature>;
      return {
        items: paginated.items ?? [],
        total: paginated.total ?? 0,
        page,
        pageSize: FEATURES_PAGE_SIZE,
      };
    },
    staleTime: 30_000,
    enabled: !!projectId && enabled,
    // T4-005: poll every 30 s when live-features (SSE) are disabled;
    // SSE-driven invalidation handles sub-30 s freshness when SSE is on.
    // SSE gate supersedes poll when enabled.
    refetchInterval: isFeatureLiveUpdatesEnabled() ? false : 30_000,
  });
}

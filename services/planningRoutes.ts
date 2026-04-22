// Centralized planning route helpers.
// All planning URL construction goes through these functions so that path
// conventions are enforced in one place.

export const PLANNING_FEATURE_MODAL_TABS = [
  'overview',
  'phases',
  'docs',
  'relations',
  'sessions',
  'history',
  'test-status',
] as const;

export type PlanningFeatureModalTab = (typeof PLANNING_FEATURE_MODAL_TABS)[number];

export function isPlanningFeatureModalTab(value: string): value is PlanningFeatureModalTab {
  return PLANNING_FEATURE_MODAL_TABS.includes(value as PlanningFeatureModalTab);
}

export interface PlanningRouteFeatureModalState {
  featureId: string;
  tab: PlanningFeatureModalTab;
}

/**
 * URL that opens the ProjectBoard with the FeatureModal focused on a feature.
 * Navigates to /board?feature=<id>&tab=<tab>.
 */
export function planningFeatureModalHref(
  featureId: string,
  tab: PlanningFeatureModalTab = 'overview',
): string {
  return `/board?feature=${encodeURIComponent(featureId)}&tab=${tab}`;
}

/**
 * Route-local planning URL that opens the shared feature modal inside /planning.
 * The board modal URL above remains available for explicit board navigation.
 */
export function planningRouteFeatureModalHref(
  featureId: string,
  tab: PlanningFeatureModalTab = 'overview',
): string {
  return `/planning?feature=${encodeURIComponent(featureId)}&modal=feature&tab=${tab}`;
}

export function resolvePlanningRouteFeatureModalState(
  searchParams: URLSearchParams,
): PlanningRouteFeatureModalState | null {
  if (searchParams.get('modal') !== 'feature') return null;

  const featureId = searchParams.get('feature');
  if (!featureId) return null;

  const rawTab = searchParams.get('tab') ?? 'overview';
  return {
    featureId,
    tab: isPlanningFeatureModalTab(rawTab) ? rawTab : 'overview',
  };
}

export function setPlanningRouteFeatureModalSearch(
  searchParams: URLSearchParams,
  featureId: string,
  tab: PlanningFeatureModalTab = 'overview',
): string {
  const next = new URLSearchParams(searchParams);
  next.set('feature', featureId);
  next.set('modal', 'feature');
  next.set('tab', tab);

  const search = next.toString();
  return search ? `?${search}` : '';
}

export function removePlanningRouteFeatureModalSearch(
  searchParams: URLSearchParams,
): string {
  const next = new URLSearchParams(searchParams);
  next.delete('feature');
  next.delete('modal');
  next.delete('tab');

  const search = next.toString();
  return search ? `?${search}` : '';
}

/**
 * URL for the full-page planning detail for a feature.
 * Navigates to /planning/feature/<id>.
 */
export function planningFeatureDetailHref(featureId: string): string {
  return `/planning/feature/${encodeURIComponent(featureId)}`;
}

/**
 * URL for the artifact drill-down page.
 * Navigates to /planning/artifacts/<type>.
 */
export function planningArtifactsHref(type: string): string {
  return `/planning/artifacts/${encodeURIComponent(type)}`;
}

// ── P13-003: Planning filter params ───────────────────────────────────────────

export type PlanningStatusBucket =
  | 'blocked'
  | 'review'
  | 'active'
  | 'planned'
  | 'shaping'
  | 'completed'
  | 'deferred'
  | 'stale_or_mismatched';

export type PlanningSignal = 'blocked' | 'stale' | 'mismatch';

export const PLANNING_STATUS_BUCKETS: PlanningStatusBucket[] = [
  'blocked', 'review', 'active', 'planned', 'shaping',
  'completed', 'deferred', 'stale_or_mismatched',
];

export const PLANNING_SIGNALS: PlanningSignal[] = ['blocked', 'stale', 'mismatch'];

export function isPlanningStatusBucket(value: string): value is PlanningStatusBucket {
  return PLANNING_STATUS_BUCKETS.includes(value as PlanningStatusBucket);
}

export function isPlanningSignal(value: string): value is PlanningSignal {
  return PLANNING_SIGNALS.includes(value as PlanningSignal);
}

export interface PlanningFilterState {
  statusBucket: PlanningStatusBucket | null;
  signal: PlanningSignal | null;
}

export function resolvePlanningFilterState(searchParams: URLSearchParams): PlanningFilterState {
  const rawBucket = searchParams.get('statusBucket');
  const rawSignal = searchParams.get('signal');
  return {
    statusBucket: rawBucket && isPlanningStatusBucket(rawBucket) ? rawBucket : null,
    signal: rawSignal && isPlanningSignal(rawSignal) ? rawSignal : null,
  };
}

// ── P13-003: usePlanningFilter hook ───────────────────────────────────────────
// Appended here to avoid an extra file; planningRoutes.ts is already a pure
// barrel-style module. The hook is tree-shaken when not used.

import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

export function usePlanningFilter(): {
  filter: PlanningFilterState;
  setStatusBucket: (bucket: PlanningStatusBucket) => void;
  setSignal: (signal: PlanningSignal) => void;
  clearFilter: () => void;
} {
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = resolvePlanningFilterState(searchParams);

  const setStatusBucket = useCallback(
    (bucket: PlanningStatusBucket) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (next.get('statusBucket') === bucket) {
          next.delete('statusBucket');
        } else {
          next.set('statusBucket', bucket);
        }
        return next;
      });
    },
    [setSearchParams],
  );

  const setSignal = useCallback(
    (signal: PlanningSignal) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (next.get('signal') === signal) {
          next.delete('signal');
        } else {
          next.set('signal', signal);
        }
        return next;
      });
    },
    [setSearchParams],
  );

  const clearFilter = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete('statusBucket');
      next.delete('signal');
      return next;
    });
  }, [setSearchParams]);

  return { filter, setStatusBucket, setSignal, clearFilter };
}

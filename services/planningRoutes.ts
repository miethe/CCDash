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

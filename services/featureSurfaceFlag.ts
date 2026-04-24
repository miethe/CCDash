// featureSurfaceFlag.ts — P5-005: Feature Surface v2 Rollout Flag
//
// Reads the `featureSurfaceV2Enabled` field from the runtime health payload
// (populated by /api/health via CCDASH_FEATURE_SURFACE_V2_ENABLED) and exposes
// a single typed predicate consumed by useFeatureSurface and useFeatureModalData.
//
// Design constraints:
//   - Flag is checked ONCE at hook mount; not re-read on every render.
//   - Default is TRUE (v2 path is the happy path).
//   - When the backend omits the field (old build, offline), the FE treats it as
//     enabled so new deployments default to v2 without explicit config.
//   - This module has no side-effects; it only reads an already-normalised object.
//   - Legacy client functions (getLegacyFeatureDetail / getLegacyFeatureLinkedSessions)
//     remain untouched; retirement is handled in P5-006.
//
// Usage:
//   import { isFeatureSurfaceV2Enabled } from './featureSurfaceFlag';
//   const v2 = isFeatureSurfaceV2Enabled(runtimeStatus);

import type { RuntimeStatus } from './runtimeProfile';

/**
 * Returns true when the v2 feature-surface data path is enabled.
 *
 * Accepts a `RuntimeStatus | null` so callers can pass the value directly from
 * AppRuntimeContext without a null-guard at call-site.  When the status is null
 * (not yet loaded) the function defaults to true — hooks will optimistically
 * start the v2 fetch path, which is the correct default for new installs.
 *
 * The runtime health payload populates `featureSurfaceV2Enabled` from the
 * `CCDASH_FEATURE_SURFACE_V2_ENABLED` environment variable (default: true).
 * Setting it to false causes this function to return false, which makes both
 * `useFeatureSurface` and `useFeatureModalData` fall back to the legacy
 * `getLegacyFeatureDetail` / `getLegacyFeatureLinkedSessions` paths.
 */
export function isFeatureSurfaceV2Enabled(
  runtimeStatus: Pick<RuntimeStatus, 'featureSurfaceV2Enabled'> | null | undefined,
): boolean {
  if (runtimeStatus == null) {
    // Not yet loaded — optimistically enable v2 to avoid a blank-board flash.
    return true;
  }
  // normalizeRuntimeStatus guarantees this field is always a boolean, but
  // defensive handling covers:
  //   - objects received before normalizeRuntimeStatus has run
  //   - old runtime builds that predate the field
  // In either case default to true (v2 is the happy path).
  if (typeof runtimeStatus.featureSurfaceV2Enabled !== 'boolean') {
    return true;
  }
  return runtimeStatus.featureSurfaceV2Enabled;
}

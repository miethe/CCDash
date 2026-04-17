/**
 * Pure helper utilities for the Planning Control Plane UI.
 * These are kept separate from components so they can be tested
 * without pulling in the full component dependency tree.
 */

import type { PhaseContextItem } from '../types';

/**
 * Node type ordering used to sort lineage nodes for display.
 * Matches the ordering in PlanningNodeDetail.
 */
export const PLANNING_NODE_TYPE_ORDER = [
  'design_spec',
  'prd',
  'implementation_plan',
  'progress',
  'context',
  'tracker',
  'report',
] as const;

/**
 * Returns the "active" phase from a list of PhaseContextItems:
 * - first phase whose effectiveStatus is in_progress or active
 * - falling back to first non-completed phase
 * - falling back to phases[0]
 * - returning null if phases is empty
 */
export function computeActivePhase(phases: PhaseContextItem[]): PhaseContextItem | null {
  if (!phases || phases.length === 0) return null;
  const active = phases.find(
    p => p.effectiveStatus === 'in_progress' || p.effectiveStatus === 'active',
  );
  if (active) return active;
  const nonDone = phases.find(
    p => p.effectiveStatus !== 'done' && p.effectiveStatus !== 'deferred',
  );
  return nonDone ?? phases[0] ?? null;
}

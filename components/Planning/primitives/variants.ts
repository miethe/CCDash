/**
 * Variant helper functions for planning status chips and readiness pills.
 * These map domain status strings to the badge variant tokens used by StatusChip
 * and BatchReadinessPill.
 */

export type StatusChipVariant = 'neutral' | 'ok' | 'warn' | 'error' | 'info';
export type ReadinessVariant = 'ok' | 'warn' | 'error' | 'neutral';

/**
 * Map a planning node rawStatus / effectiveStatus string to a StatusChip variant.
 */
export function statusVariant(status: string): StatusChipVariant {
  const s = status.toLowerCase();
  if (['complete', 'completed', 'done', 'active', 'in_progress'].some(v => s.includes(v))) return 'ok';
  if (['blocked', 'stale', 'reversed', 'mismatch'].some(v => s.includes(v))) return 'error';
  if (['pending', 'waiting', 'deferred'].some(v => s.includes(v))) return 'warn';
  return 'neutral';
}

/**
 * Map a PlanningPhaseBatchReadinessState string to a StatusChip variant.
 */
export function readinessVariant(r: string): ReadinessVariant {
  if (r === 'ready') return 'ok';
  if (r === 'blocked') return 'error';
  if (r === 'waiting') return 'warn';
  return 'neutral';
}

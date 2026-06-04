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

// ── Last-activity display ─────────────────────────────────────────────────────

export interface LastActivityDisplay {
  /** Short human-readable label: relative if <24h, absolute otherwise. */
  label: string;
  /** Full locale string suitable for use as a tooltip title attribute. */
  title: string;
}

/**
 * Format a last-activity ISO timestamp into a display label and tooltip.
 *
 * Returns null when iso is null, empty, or unparseable.
 *
 * Relative (< 24 h):
 *   - < 5 s  → "just now"
 *   - < 60 s → "Ns ago"
 *   - < 60 m → "Nm ago"
 *   - < 24 h → "Nh ago"
 *
 * Absolute (≥ 24 h): `date.toLocaleString()`.
 *
 * `title` is always `date.toLocaleString()` for a full tooltip.
 */
export function formatLastActivity(iso?: string | null): LastActivityDisplay | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;

  const title = d.toLocaleString();
  const secs = Math.floor((Date.now() - d.getTime()) / 1000);

  if (secs < 86_400) {
    // < 24 hours — relative label
    let label: string;
    if (secs < 5) {
      label = 'just now';
    } else if (secs < 60) {
      label = `${secs}s ago`;
    } else {
      const mins = Math.floor(secs / 60);
      if (mins < 60) {
        label = `${mins}m ago`;
      } else {
        const hrs = Math.floor(mins / 60);
        label = `${hrs}h ago`;
      }
    }
    return { label, title };
  }

  // ≥ 24 hours — absolute label
  return { label: title, title };
}

/**
 * PlanningArtifactChipRow — T2-003
 *
 * Renders the 8-artifact composition chip row for the planning home page.
 * Each chip shows glyph, label, and count derived from nodeCountsByType.
 * Clicking a chip navigates to /planning/artifacts/:type where a
 * drill-down page exists; for types without a drill-down (SPIKE, PHASE, TRK)
 * the chip still navigates so future pages can land there.
 *
 * Ends with a corpus summary text block showing total indexed docs + refs.
 */

import { useNavigate } from 'react-router-dom';
import { ArtifactChip } from './primitives';
import type { PlanningNodeCountsByType } from '../../types';
import { planningArtifactsHref } from '../../services/planningRoutes';

// ── Artifact row config ───────────────────────────────────────────────────────

interface ArtifactRowItem {
  /** ArtifactToken key passed to <ArtifactChip kind=…> */
  kind: string;
  /** Route segment for /planning/artifacts/:type */
  routeType: string;
  /** Count derived from PlanningNodeCountsByType; 0 if not available */
  count: number;
}

/**
 * Map from the 8 chip display slots to backend counts.
 * - SPEC  → designSpec
 * - SPIKE → not yet in PlanningNodeCountsByType; always 0
 * - PRD   → prd
 * - PLAN  → implementationPlan
 * - PHASE → progress (one progress file per phase)
 * - CTX   → context
 * - TRK   → tracker
 * - REP   → report
 */
function buildArtifactItems(counts: PlanningNodeCountsByType): ArtifactRowItem[] {
  return [
    { kind: 'spec',                route: 'design-specs',         count: counts.designSpec          ?? 0 },
    { kind: 'spike',               route: 'spikes',               count: 0                               },
    { kind: 'prd',                 route: 'prds',                 count: counts.prd                 ?? 0 },
    { kind: 'implementation_plan', route: 'implementation-plans', count: counts.implementationPlan  ?? 0 },
    { kind: 'progress',            route: 'phases',               count: counts.progress            ?? 0 },
    { kind: 'context',             route: 'contexts',             count: counts.context             ?? 0 },
    { kind: 'tracker',             route: 'trackers',             count: counts.tracker             ?? 0 },
    { kind: 'report',              route: 'reports',              count: counts.report              ?? 0 },
  ].map(({ kind, route, count }) => ({ kind, routeType: route, count }));
}

/** Total artifact nodes across all types. */
function totalArtifactCount(counts: PlanningNodeCountsByType): number {
  return (
    (counts.designSpec ?? 0) +
    (counts.prd ?? 0) +
    (counts.implementationPlan ?? 0) +
    (counts.progress ?? 0) +
    (counts.context ?? 0) +
    (counts.tracker ?? 0) +
    (counts.report ?? 0)
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

interface PlanningArtifactChipRowProps {
  nodeCountsByType: PlanningNodeCountsByType;
  /** Total cross-document reference links resolved by the backend (optional). */
  totalRefs?: number;
}

export function PlanningArtifactChipRow({
  nodeCountsByType,
  totalRefs,
}: PlanningArtifactChipRowProps) {
  const navigate = useNavigate();
  const items = buildArtifactItems(nodeCountsByType);
  const total = totalArtifactCount(nodeCountsByType);
  const refs = totalRefs ?? 0;

  return (
    <div
      className="flex flex-wrap items-center gap-x-1.5 gap-y-2"
      data-testid="planning-artifact-chip-row"
      role="list"
      aria-label="Artifact composition"
    >
      {items.map(({ kind, routeType, count }) => (
        <div key={kind} role="listitem">
          <ArtifactChip
            kind={kind}
            count={count}
            size="sm"
            onClick={() => navigate(planningArtifactsHref(routeType))}
            aria-label={`${kind} artifacts: ${count}`}
          />
        </div>
      ))}

      {/* Divider */}
      <span
        aria-hidden="true"
        className="mx-1 h-3.5 w-px self-center"
        style={{ background: 'var(--line-1)' }}
      />

      {/* Corpus summary text */}
      <span
        className="planning-mono planning-tnum select-none whitespace-nowrap"
        style={{ fontSize: 10.5, color: 'var(--ink-3)' }}
        data-testid="planning-corpus-summary"
        aria-label={`${total} docs indexed, ${refs} refs resolved`}
      >
        {total} docs indexed
        {refs > 0 && (
          <>
            {' · '}
            {refs} refs resolved
          </>
        )}
      </span>
    </div>
  );
}

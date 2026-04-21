import type { ButtonHTMLAttributes } from 'react';

import type { PlanningNode, PlanningNodeType } from '@/types';
import { cn } from '@/lib/utils';

// ── Artifact-identity token lookup ─────────────────────────────────────────

interface ArtifactIdentity {
  short: string;
  color: string;
}

const ARTIFACT_IDENTITY: Record<PlanningNodeType, ArtifactIdentity> = {
  design_spec:         { short: 'SPEC',  color: 'var(--spec)' },
  prd:                 { short: 'PRD',   color: 'var(--prd)'  },
  implementation_plan: { short: 'PLAN',  color: 'var(--plan)' },
  progress:            { short: 'PHASE', color: 'var(--prog)' },
  context:             { short: 'CTX',   color: 'var(--ctx)'  },
  tracker:             { short: 'TRK',   color: 'var(--trk)'  },
  report:              { short: 'REP',   color: 'var(--rep)'  },
};

// ── Status dot color lookup ────────────────────────────────────────────────

function resolveStatusDotColor(status: string): string {
  switch (status) {
    case 'completed':    return 'var(--ok)';
    case 'in-progress':
    case 'in_progress':  return 'var(--plan)';
    case 'blocked':      return 'var(--err)';
    case 'approved':     return 'var(--prd)';
    case 'draft':        return 'var(--ink-2)';
    case 'superseded':
    case 'deprecated':
    case 'future':       return 'var(--ink-3)';
    default:             return 'var(--ink-2)';
  }
}

// ── Mute logic ────────────────────────────────────────────────────────────

function isMuted(status: string): boolean {
  return status === 'completed' || status === 'superseded' || status === 'deprecated';
}

// ── DocChip ───────────────────────────────────────────────────────────────

export interface DocChipProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  node: PlanningNode;
}

/**
 * DocChip renders a single planning artifact node as a clickable lane chip.
 *
 * Anatomy:
 *   [ TYPE-LABEL ]  [ truncated title ]  [status dot]
 *
 * Muted (opacity + bg washout) when status is completed/superseded/deprecated.
 * Status dot color reflects the node's effectiveStatus.
 * Clicking fires the button's onClick (caller passes onNodeClick wired up).
 */
export function DocChip({ node, className, style, ...props }: DocChipProps) {
  const identity = ARTIFACT_IDENTITY[node.type] ?? { short: node.type.toUpperCase(), color: 'var(--ink-2)' };
  const status = node.effectiveStatus || node.rawStatus || 'draft';
  const muted = isMuted(status);
  const dotColor = resolveStatusDotColor(status);

  // Derive display title: use node.title, or fall back to last path segment
  const displayTitle =
    node.title ||
    (node.path ? node.path.split('/').pop() ?? node.path : node.id);

  return (
    <button
      type="button"
      title={node.path || node.title}
      aria-label={`${identity.short} ${displayTitle}, status ${status}`}
      className={cn('planning-mono', className)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 7,
        padding: '5px 9px',
        borderRadius: 5,
        background: muted
          ? `color-mix(in oklab, ${identity.color} 6%, var(--bg-2))`
          : `linear-gradient(180deg, color-mix(in oklab, ${identity.color} 18%, var(--bg-2)), color-mix(in oklab, ${identity.color} 10%, var(--bg-2)))`,
        border: `1px solid color-mix(in oklab, ${identity.color} 35%, var(--line-1))`,
        cursor: 'pointer',
        fontFamily: 'inherit',
        textAlign: 'left',
        minWidth: 0,
        width: '100%',
        opacity: status === 'superseded' ? 0.5 : 1,
        color: muted ? 'var(--ink-3)' : 'var(--ink-0)',
        transition: 'opacity 120ms ease, background 120ms ease',
        ...style,
      }}
      {...props}
    >
      {/* Type label */}
      <span
        aria-hidden="true"
        style={{
          fontSize: 9,
          letterSpacing: '0.08em',
          color: muted ? 'var(--ink-3)' : identity.color,
          flexShrink: 0,
          textTransform: 'uppercase' as const,
        }}
      >
        {identity.short}
      </span>

      {/* Truncated title */}
      <span
        style={{
          fontSize: 11,
          color: muted ? 'var(--ink-3)' : 'var(--ink-1)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap' as const,
          flex: 1,
          minWidth: 0,
        }}
      >
        {displayTitle}
      </span>

      {/* Status dot */}
      <span
        className="planning-dot"
        aria-hidden="true"
        style={{ background: dotColor, flexShrink: 0 }}
      />
    </button>
  );
}

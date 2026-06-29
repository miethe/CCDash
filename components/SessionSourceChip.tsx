/**
 * SessionSourceChip — maps AgentSession.source discriminator to a compact badge.
 *
 * Phase 6: session source attribution (additive/optional field).
 * Phase 3 (Codex): 'codex' source added; platformType fallback for pre-Phase-3 payloads.
 *
 * Resilience contract:
 *  - source === undefined → renders nothing (missing optional field is a contract state, not a bug).
 *  - source === null && platformType === 'Codex' → derives codex chip (Phase-3 backward compat).
 *  - source === null && platformType !== 'Codex' → renders nothing.
 *  - Unknown string source value → falls back to SOURCE_META.unknown gracefully.
 *
 * SessionUnattributedBadge: rendered when projectId === '' (empty string sentinel).
 *  - Orthogonal to origin: an Unattributed session is still Codex origin.
 *  - cwd prop shown as tooltip/subtext so user knows which repo was unmatched.
 */

import React from 'react';
import { HardDrive, Radio, GitBranch, HelpCircle, Terminal, FolderX } from 'lucide-react';

import { Badge } from './ui/badge';
import { cn } from '../lib/utils';

export type SessionSourceValue = 'codex' | 'filesystem' | 'remote' | 'entire' | 'unknown';

type SourceMeta = {
  label: string;
  tooltip: string;
  tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger';
  icon: React.ComponentType<{ size?: number; className?: string }>;
};

const SOURCE_META: Record<SessionSourceValue, SourceMeta> = {
  codex: {
    label: 'Codex',
    tooltip: 'Session originated from OpenAI Codex',
    tone: 'warning',
    icon: Terminal,
  },
  filesystem: {
    label: 'Local file',
    tooltip: 'Session sourced from local filesystem',
    tone: 'neutral',
    icon: HardDrive,
  },
  remote: {
    label: 'Remote ingest',
    tooltip: 'Session ingested from a remote source',
    tone: 'info',
    icon: Radio,
  },
  entire: {
    label: 'Entire checkpoint',
    tooltip: 'Session captured as an entire-state checkpoint',
    tone: 'info',
    icon: GitBranch,
  },
  unknown: {
    label: 'Unknown',
    tooltip: 'Session source could not be determined',
    tone: 'neutral',
    icon: HelpCircle,
  },
};

/**
 * Derive the effective source value from source + platformType.
 * Returns null when no chip should be rendered.
 */
export function deriveEffectiveSource(
  source: SessionSourceValue | null | undefined,
  platformType?: string | null,
): SessionSourceValue | null {
  if (source !== undefined && source !== null) return source;
  // source absent or null: attempt fallback from platformType
  if ((platformType || '').trim().toLowerCase() === 'codex') return 'codex';
  return null;
}

export interface SessionSourceChipProps {
  source?: SessionSourceValue | null;
  /** Fallback: when source is absent/null, derive from platformType (Phase-3 compat). */
  platformType?: string | null;
  /** Compact size for dense contexts like session cards. */
  compact?: boolean;
  className?: string;
}

/**
 * Renders a labelled badge for AgentSession.source.
 * Returns null when no chip should be rendered (see resilience contract above).
 */
export const SessionSourceChip: React.FC<SessionSourceChipProps> = ({
  source,
  platformType,
  compact = false,
  className,
}) => {
  const effectiveSource = deriveEffectiveSource(source, platformType);
  if (effectiveSource === null) return null;

  const meta = SOURCE_META[effectiveSource] ?? SOURCE_META.unknown;
  const Icon = meta.icon;

  return (
    <Badge
      tone={meta.tone}
      size={compact ? 'sm' : 'md'}
      title={meta.tooltip}
      className={cn(className)}
    >
      <Icon size={10} className="shrink-0" aria-hidden="true" />
      <span>{meta.label}</span>
    </Badge>
  );
};

// ── Unattributed badge ────────────────────────────────────────────────────────

export interface SessionUnattributedBadgeProps {
  /** The working directory of the Codex session; shown in tooltip. */
  cwd?: string | null;
  compact?: boolean;
  className?: string;
}

/**
 * Badge rendered when a session's projectId === '' (empty string sentinel).
 * Orthogonal to origin — an Unattributed session is still Codex origin.
 */
export const SessionUnattributedBadge: React.FC<SessionUnattributedBadgeProps> = ({
  cwd,
  compact = false,
  className,
}) => {
  const cwdLabel = (cwd || '').trim();
  const tooltip = cwdLabel
    ? `Unattributed — working directory did not match any registered project\nCwd: ${cwdLabel}`
    : 'Unattributed — working directory did not match any registered project';

  return (
    <Badge
      tone="warning"
      size={compact ? 'sm' : 'md'}
      title={tooltip}
      className={cn('border-amber-500/50 bg-amber-500/10 text-amber-300', className)}
    >
      <FolderX size={10} className="shrink-0" aria-hidden="true" />
      <span>Unattributed</span>
    </Badge>
  );
};

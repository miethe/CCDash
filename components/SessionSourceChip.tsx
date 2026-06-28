/**
 * SessionSourceChip — maps AgentSession.source discriminator to a compact badge.
 *
 * Phase 6: session source attribution (additive/optional field).
 * Resilience contract: source === undefined → renders nothing (missing optional
 * field is a contract state, not a bug).
 */

import React from 'react';
import { HardDrive, Radio, GitBranch, HelpCircle } from 'lucide-react';

import { Badge } from './ui/badge';
import { cn } from '../lib/utils';

type SessionSource = 'filesystem' | 'remote' | 'entire' | 'unknown';

type SourceMeta = {
  label: string;
  tooltip: string;
  tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger';
  icon: React.ComponentType<{ size?: number; className?: string }>;
};

const SOURCE_META: Record<SessionSource, SourceMeta> = {
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

export interface SessionSourceChipProps {
  source?: SessionSource;
  /** Compact size for dense contexts like session cards. */
  compact?: boolean;
  className?: string;
}

/**
 * Renders a labelled badge for AgentSession.source.
 * Returns null when source is undefined (resilience-by-default).
 */
export const SessionSourceChip: React.FC<SessionSourceChipProps> = ({
  source,
  compact = false,
  className,
}) => {
  if (source === undefined) return null;

  const meta = SOURCE_META[source] ?? SOURCE_META.unknown;
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

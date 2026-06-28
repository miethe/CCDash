/**
 * IngestHealthBadge — summarizes per-source ingest health into a single badge.
 *
 * Phase 6: daemon/ingest health surface (additive/optional).
 *
 * Worst-state-wins priority: disconnected > backed_up > connected > idle.
 * Empty/absent ingestSources → renders neutral "Local only" state (not an error).
 *
 * Resilience contract: never throws; missing or empty ingestSources is a
 * contract state (pre-v36 backend), rendered as neutral "Local only".
 */

import React from 'react';
import { Wifi, WifiOff, Clock, Radio } from 'lucide-react';

import { Badge } from './ui/badge';
import { cn } from '../lib/utils';
import type { IngestSourceHealth } from '../services/apiClient';

type IngestState = IngestSourceHealth['state'];

type IngestStateMeta = {
  label: string;
  tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger';
  icon: React.ComponentType<{ size?: number; className?: string }>;
};

/** Higher number = worse state; drives worst-state-wins reduction. */
const STATE_PRIORITY: Record<IngestState, number> = {
  disconnected: 3,
  backed_up: 2,
  connected: 1,
  idle: 0,
};

const STATE_META: Record<IngestState, IngestStateMeta> = {
  disconnected: { label: 'Disconnected', tone: 'danger', icon: WifiOff },
  backed_up: { label: 'Backed up', tone: 'warning', icon: Clock },
  connected: { label: 'Connected', tone: 'success', icon: Wifi },
  idle: { label: 'Idle', tone: 'neutral', icon: Radio },
};

const EMPTY_META: IngestStateMeta & { tooltip: string } = {
  label: 'Local only',
  tone: 'neutral',
  icon: Radio,
  tooltip: 'No remote ingest sources configured',
};

export interface IngestHealthBadgeProps {
  ingestSources?: IngestSourceHealth[];
  className?: string;
}

/**
 * Derives the worst-state badge from an ingestSources array.
 *
 * - Empty / undefined → neutral "Local only"
 * - disconnected present → danger
 * - backed_up present (no disconnected) → warning
 * - connected present (no worse) → success
 * - all idle → neutral "Idle"
 */
export const IngestHealthBadge: React.FC<IngestHealthBadgeProps> = ({
  ingestSources,
  className,
}) => {
  const sources = Array.isArray(ingestSources) ? ingestSources : [];

  if (sources.length === 0) {
    const Icon = EMPTY_META.icon;
    return (
      <Badge tone={EMPTY_META.tone} title={EMPTY_META.tooltip} className={cn(className)}>
        <Icon size={10} className="shrink-0" aria-hidden="true" />
        <span>{EMPTY_META.label}</span>
      </Badge>
    );
  }

  // Worst-state-wins reduction (no initializer — safe because sources.length > 0 here)
  const worstSource = sources.reduce((worst, current) => {
    const worstPriority = STATE_PRIORITY[worst.state] ?? 0;
    const currentPriority = STATE_PRIORITY[current.state] ?? 0;
    return currentPriority > worstPriority ? current : worst;
  });

  const meta = STATE_META[worstSource.state] ?? STATE_META.idle;
  const Icon = meta.icon;

  // Tooltip: per-source source_id + state + lag
  const tooltipLines = sources.map((s) => {
    const lagText = s.lag_seconds !== null && s.lag_seconds !== undefined
      ? ` (${s.lag_seconds}s lag)`
      : '';
    return `${s.source_id}: ${s.state}${lagText}`;
  });
  const tooltip = `Ingest sources:\n${tooltipLines.join('\n')}`;

  return (
    <Badge tone={meta.tone} title={tooltip} className={cn(className)}>
      <Icon size={10} className="shrink-0" aria-hidden="true" />
      <span>Ingest: {meta.label}</span>
      {sources.length > 1 && (
        <span className="font-normal opacity-80">({sources.length})</span>
      )}
    </Badge>
  );
};

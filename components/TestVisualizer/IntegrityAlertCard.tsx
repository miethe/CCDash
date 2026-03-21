import React, { useMemo, useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronRight, GitCommit, FileCode2 } from 'lucide-react';

import { TestIntegritySignal } from '../../types';
import { AlertSurface } from '../ui/surface';
import { Badge } from '../ui/badge';

interface IntegrityAlertCardProps {
  signal: TestIntegritySignal;
  className?: string;
  defaultExpanded?: boolean;
}

const severityStyles: Record<string, string> = {
  high: 'border-l-danger',
  medium: 'border-l-warning',
  low: 'border-l-info',
};

const toTitle = (value: string): string =>
  value
    .split('_')
    .filter(Boolean)
    .map(token => token[0].toUpperCase() + token.slice(1))
    .join(' ');

export const IntegrityAlertCard: React.FC<IntegrityAlertCardProps> = ({
  signal,
  className = '',
  defaultExpanded = false,
}) => {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const severityClass = severityStyles[signal.severity] ?? severityStyles.medium;
  const prettyDetails = useMemo(() => JSON.stringify(signal.details ?? {}, null, 2), [signal.details]);

  return (
    <AlertSurface
      intent={signal.severity === 'high' ? 'danger' : signal.severity === 'medium' ? 'warning' : 'info'}
      className={`border-l-4 ${severityClass} p-4 ${className}`.trim()}
      aria-label={`Integrity signal ${signal.signalType}`}
    >
      <button
        type="button"
        className="flex w-full items-start justify-between gap-3 text-left"
        onClick={() => setExpanded(prev => !prev)}
        aria-expanded={expanded}
      >
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <AlertTriangle size={14} className="text-warning-foreground" aria-hidden="true" />
            <Badge size="sm" tone={signal.severity === 'high' ? 'danger' : signal.severity === 'medium' ? 'warning' : 'info'} className="uppercase tracking-wide">
              {signal.severity}
            </Badge>
            <Badge size="sm" tone="neutral">
              {toTitle(signal.signalType)}
            </Badge>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <GitCommit size={12} aria-hidden="true" />
              {signal.gitSha.slice(0, 7)}
            </span>
            <span className="inline-flex items-center gap-1 break-all">
              <FileCode2 size={12} aria-hidden="true" />
              {signal.filePath}
            </span>
            <span>{new Date(signal.createdAt).toLocaleString()}</span>
          </div>
        </div>
        {expanded ? <ChevronDown size={16} className="text-muted-foreground" /> : <ChevronRight size={16} className="text-muted-foreground" />}
      </button>

      {expanded && (
        <div className="mt-3 rounded-lg border border-panel-border bg-surface-overlay/70 p-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Details</p>
          <pre className="overflow-x-auto whitespace-pre-wrap break-words font-mono text-[11px] text-panel-foreground">{prettyDetails}</pre>
        </div>
      )}
    </AlertSurface>
  );
};

export type { IntegrityAlertCardProps };

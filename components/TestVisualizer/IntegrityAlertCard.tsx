import React, { useMemo, useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronRight, GitCommit, FileCode2 } from 'lucide-react';

import { TestIntegritySignal } from '../../types';

interface IntegrityAlertCardProps {
  signal: TestIntegritySignal;
  className?: string;
  defaultExpanded?: boolean;
}

const severityStyles: Record<string, string> = {
  high: 'border-l-rose-500',
  medium: 'border-l-amber-500',
  low: 'border-l-indigo-500',
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
    <article
      className={`rounded-xl border border-slate-800 border-l-4 bg-slate-900 p-4 ${severityClass} ${className}`.trim()}
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
            <AlertTriangle size={14} className="text-amber-400" aria-hidden="true" />
            <span className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-300">
              {signal.severity}
            </span>
            <span className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 text-[10px] font-semibold text-slate-300">
              {toTitle(signal.signalType)}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
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
        {expanded ? <ChevronDown size={16} className="text-slate-500" /> : <ChevronRight size={16} className="text-slate-500" />}
      </button>

      {expanded && (
        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Details</p>
          <pre className="overflow-x-auto whitespace-pre-wrap break-words font-mono text-[11px] text-slate-300">{prettyDetails}</pre>
        </div>
      )}
    </article>
  );
};

export type { IntegrityAlertCardProps };
